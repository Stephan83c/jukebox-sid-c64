#!/usr/bin/env python3
# SID Jukebox C64
# Copyright (C) 2026 Stephan83c
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version. It is
# distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.
"""Serveur SID Jukebox : tirage aléatoire, un morceau par demande, sans état partagé.

Protocole texte (une commande par ligne, réponses terminées par \\n) :
    RANDOM [motif]   -> OK|id|taille|secondes|images/s|sous-morceau|chargement|init|play|titre|auteur|année|scroller\\n
                        + <taille> octets de code brut (sans en-tête PSID), à copier à l'adresse de chargement
                        (motif : sous-chaîne cherchée dans l'auteur ou le titre, sans tenir compte de la casse)
                        Clients anciens (v1.3.x, v1.4) : seuls les morceaux finissant avant $A700 sont proposés.
    RANDOM2 <fin> [motif]  -> idem, mais <fin> (4 chiffres hexadécimaux, ex. AEFF) est la dernière adresse que le
                        client laisse aux morceaux (HISTART - 1) : seuls les morceaux qui finissent au plus tard
                        à cette adresse sont proposés (client v1.5 et suivants).
    GET <id>         -> idem pour un morceau précis
    RANDOM3 <fin> [motif]  -> v2.0 (SPEC-v2.md §6.1) :
                        OK3|id|taille|secondes|images/s|sous-morceau|chargement|init|play|relais|taille_relais|complet|titre|auteur|année|scroller\n
                        + <taille> octets de code (sites d'écriture SID remplacés par JSR vers les relais)
                        + <taille_relais> octets : bloc de relais à copier à l'adresse <relais> (0 et 0 : pas de relais)
                        Seuls les morceaux acceptés par l'analyse sidscan (table « scan ») sont proposés.
    GET3 <id>        -> idem pour un morceau précis
    STATS            -> STATS|compatibles|total\\n
    QUIT             -> ferme la connexion
    erreur           -> ERR|message\\n
"""
import argparse
import asyncio
import ipaddress
import logging
import socket
import sqlite3
import struct
import time
import unicodedata
from pathlib import Path

log = logging.getLogger("jukebox")
DEFAULT_SECONDS = 180
MAX_CONN_IP = 8          # connexions simultanées par IP (un C64 en prend une)
MAX_CONN = 200           # connexions simultanées au total
REQ_WINDOW, REQ_MAX = 60, 30      # morceaux demandés par IP et par minute (QUIT et STATS ne comptent pas)
FIRST_LINE_TIMEOUT = 20  # secondes pour envoyer la première commande (sinon on coupe)
IDLE_TIMEOUT = 30        # secondes d'attente entre deux commandes (le client ferme avant de jouer : une connexion muette est perdue)
MAX_LINE = 1024          # taille maximale d'une commande
LEGACY_MAX_ADDR = 0xA6FF  # fin de zone des clients qui envoient RANDOM sans limite (HISTART $A700)
MIN_MAX_ADDR = 0x0900     # limite minimale acceptée pour RANDOM2 et RANDOM3 (en dessous, rien ne tient)
# Analyse servie aux commandes v2 (table « scan ») : HISTART et nombre d'appels de l'analyse ; la version est la plus
# récente présente dans la base pour ces deux valeurs. HISTART définitif fixé à l'étape 5 de SPEC-v2.md.
SCAN_HISTART = 0xAF00
SCAN_CALLS = 10000
MAX_RELAYS = 48           # SPEC-v2.md §5.3 : bloc de 32 + 7 × 48 = 368 octets au plus
COPY_LEN = 32
RELAY_OPS = (0x8D, 0x8E, 0x8C, 0x9D, 0x99)   # STA/STX/STY absolu, STA absolu,X / absolu,Y (§5.2)


def ipkey(ip: str) -> str:
    """Clé de limitation : l'IPv4 telle quelle, l'IPv6 réduite à son bloc /64 (un abonné en a des milliards)."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return ip[:64]
    if a.version == 6:
        if a.ipv4_mapped:
            return str(a.ipv4_mapped)
        return str(ipaddress.ip_network((a, 64), strict=False))
    return str(a)


_TRANSLIT = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ß": "ss",
                           "đ": "d", "Đ": "D", "ł": "l", "Ł": "L", "þ": "th", "Þ": "TH", "ð": "d", "Ð": "D",
                           "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def clean(s: str) -> str:
    """Pas de '|' ni de retour ligne dans les champs texte ; accents retirés (le C64 n'affiche que l'ASCII)."""
    s = unicodedata.normalize("NFKD", (s or "").translate(_TRANSLIT))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.replace("|", "/").split())


SCROLL_ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789*.,!?-/': ")
SCROLL_MAX = 150


def scroll_text(path: Path) -> str:
    """Texte du scroller : relu à chaque morceau, réduit à l'alphabet du C64 (A-Z 0-9 * . , ! ? - / ' :),
    sur une seule ligne, 150 caractères au plus, avec 10 espaces avant et après (le texte entre par la droite). Fichier absent ou vide : le C64 garde son texte."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    raw = unicodedata.normalize("NFKD", raw).upper()       # é -> E
    txt = "".join(c if c in SCROLL_ALPHABET else " " for c in raw)
    txt = " ".join(txt.split())[:SCROLL_MAX].strip()
    return " " * 10 + txt + " " * 10 if txt else ""


def build_relays(code: bytes, load: int, relais: str, rz: int) -> tuple[bytes, bytes]:
    """Fabrication du morceau modifié (SPEC-v2.md §5.4), octet pour octet comme sidscan (fabriquer()).

    relais : « adresse:opcode » séparés par des virgules, dans l'ordre des relais (colonne scan.relais).
    Rend (code modifié, bloc de relais). Le bloc : copie de 32 octets à zéro, puis pour chaque site k, en rz + 32 + 7k :
    « op base / op rz+(base & $1F) / RTS » ; le site devient « JSR rz + 32 + 7k ». Aucun autre octet n'est modifié.
    ValueError si la liste ne correspond pas au fichier (le morceau part alors sans relais)."""
    sites = [(int(a, 16), int(o, 16)) for a, o in (x.split(":") for x in relais.split(","))]
    if not 0 < len(sites) <= MAX_RELAYS:
        raise ValueError("nombre de relais")
    n = COPY_LEN + 7 * len(sites)
    end = load + len(code) - 1
    if rz < 0x0800 or not (rz + n - 1 < load or rz > end) or rz + n > 0x10000:
        raise ValueError("bloc de relais mal placé")
    m = bytearray(code)
    block = bytearray(n)
    for k, (ad, op) in enumerate(sites):
        i = ad - load
        if op not in RELAY_OPS or i < 0 or i + 3 > len(m) or m[i] != op:
            raise ValueError("site %04X introuvable" % ad)
        base = m[i + 1] | m[i + 2] << 8
        if not 0xD400 <= base <= 0xD41F:
            raise ValueError("site %04X hors du SID" % ad)
        st, cp = rz + COPY_LEN + 7 * k, rz + (base & 0x1F)
        block[COPY_LEN + 7 * k:COPY_LEN + 7 * k + 7] = bytes((op, base & 255, base >> 8, op, cp & 255, cp >> 8, 0x60))
        m[i:i + 3] = bytes((0x20, st & 255, st >> 8))
    return bytes(m), bytes(block)


def tune_code(data: bytes) -> bytes:
    """Code brut d'un fichier PSID : sans l'en-tête (ni l'adresse de chargement intégrée)."""
    off = (data[6] << 8) | data[7]
    if (data[8] << 8 | data[9]) == 0:
        off += 2
    return data[off:]


class Jukebox:
    def __init__(self, db: Path, root: Path, scroll: Path | None = None,
                 scroll_user: Path | None = None, scroll_ttl: int = 3600):
        self.scroll_default = scroll
        self.scroll_user = scroll_user
        self.scroll_ttl = scroll_ttl
        # base ouverte en lecture seule : le serveur n'écrit jamais dedans (update_db.sh la remplace de l'extérieur)
        self.con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False)
        self.con.create_function("fold", 1, clean, deterministic=True)   # recherche sur le texte tel qu'affiché (sans accents)
        self.conns: dict[str, list] = {}                 # connexions ouvertes par IP (StreamWriter, de la plus ancienne à la plus récente)
        self.total = 0
        self.reqs: dict[str, list[float]] = {}           # horodatage des commandes récentes par IP
        self.con.row_factory = sqlite3.Row
        self.root = root
        self.scan_version = None                         # analyse servie aux commandes v2 (None : RANDOM3/GET3 refusés)
        if self.con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='scan'").fetchone():
            self.scan_version = self.con.execute("SELECT MAX(scan_version) FROM scan WHERE histart=? AND calls=?",
                                                 (SCAN_HISTART, SCAN_CALLS)).fetchone()[0]

    @property
    def scroll(self) -> Path | None:
        """Texte proposé par les utilisateurs (page web) s'il a moins de scroll_ttl secondes,
        sinon texte par défaut. L'âge du fichier est l'heure du dernier changement."""
        u = self.scroll_user
        try:
            if u and time.time() - u.stat().st_mtime < self.scroll_ttl:
                return u
        except OSError:
            pass
        d = self.scroll_default
        if d and not d.exists():                         # scroll.txt est local (hors git) : sinon le modèle du dépôt
            d = d.with_name(d.name + ".example")
        return d

    def admit(self, ip: str, w) -> bool:
        """Ouvre une place pour cette IP. IP pleine : on coupe sa plus ancienne connexion (l'Ultimate laisse parfois
        des connexions à moitié fermées, qui bloqueraient toute la maison) ; serveur plein : refus."""
        lst = self.conns.setdefault(ip, [])
        if len(lst) >= MAX_CONN_IP:
            old = lst.pop(0)
            self.total -= 1
            log.info("IP %s pleine : coupure de la plus ancienne connexion", ip)
            cut(old)
        if self.total >= MAX_CONN:
            if not lst:
                del self.conns[ip]
            return False
        lst.append(w)
        self.total += 1
        return True

    def leave(self, ip: str, w):
        lst = self.conns.get(ip, [])
        if w in lst:                 # absente si elle a déjà été coupée par admit()
            lst.remove(w)
            self.total -= 1
        if not lst:
            self.conns.pop(ip, None)

    def req_ok(self, ip: str) -> bool:
        now = time.time()
        h = [t for t in self.reqs.get(ip, []) if now - t < REQ_WINDOW]
        self.reqs[ip] = h
        if len(self.reqs) > 5000:
            self.reqs = {k: v for k, v in self.reqs.items() if v and now - v[-1] < REQ_WINDOW}
        if len(h) >= REQ_MAX:
            return False        # un refus n'est pas noté : le blocage ne se prolonge pas si le client insiste
        h.append(now)
        return True

    def pick(self, pattern: str | None = None, max_addr: int = LEGACY_MAX_ADDR):
        if pattern:
            esc = pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like = f"%{esc}%"
            return self.con.execute(
                "SELECT * FROM tunes WHERE compatible=1 AND end_addr<=? AND (fold(author) LIKE ? ESCAPE '\\' OR fold(title) LIKE ? ESCAPE '\\')"
                " ORDER BY RANDOM() LIMIT 1", (max_addr, like, like)).fetchone()
        return self.con.execute(
            "SELECT * FROM tunes WHERE compatible=1 AND end_addr<=? ORDER BY RANDOM() LIMIT 1", (max_addr,)).fetchone()

    SELECT3 = ("SELECT t.*, s.complet AS s_complet, s.relay_addr, s.relay_len, s.nrelais, s.verif, s.relais AS s_relais"
               " FROM tunes t JOIN scan s ON s.tune_id = t.id AND s.song = t.start_song"
               " AND s.scan_version = ? AND s.histart = ? AND s.calls = ?"
               " WHERE t.compatible = 1 AND s.verdict = 'ok'")

    def pick3(self, pattern: str | None, max_addr: int):
        args = [self.scan_version, SCAN_HISTART, SCAN_CALLS, max_addr]
        q = self.SELECT3 + " AND t.end_addr <= ?"
        if pattern:
            esc = pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            q += " AND (fold(t.author) LIKE ? ESCAPE '\\' OR fold(t.title) LIKE ? ESCAPE '\\')"
            args += [f"%{esc}%"] * 2
        return self.con.execute(q + " ORDER BY RANDOM() LIMIT 1", args).fetchone()

    def get3(self, tune_id: int):
        return self.con.execute(self.SELECT3 + " AND t.id = ?",
                                (self.scan_version, SCAN_HISTART, SCAN_CALLS, tune_id)).fetchone()

    def get(self, tune_id: int):
        return self.con.execute("SELECT * FROM tunes WHERE id=? AND compatible=1", (tune_id,)).fetchone()

    def stats(self):
        return self.con.execute("SELECT SUM(compatible), COUNT(*) FROM tunes").fetchone()

    def payload(self, row) -> bytes:
        # le chemin vient de notre propre base, mais on vérifie quand même qu'il reste sous la racine
        p = (self.root / row["path"]).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("chemin hors racine")
        return p.read_bytes()


async def send_tune(w: asyncio.StreamWriter, jb: Jukebox, row, scroll: Path | None = None):
    if row is None:
        w.write(b"ERR|aucun morceau\n")
        return
    data = tune_code(jb.payload(row))      # le C64 reçoit le code brut, sans en-tête PSID
    secs = int(row["seconds"] or DEFAULT_SECONDS)
    fps = 60 if row["clock"] == "NTSC" else 50     # cadence pour laquelle le morceau est écrit
    head = "OK|%d|%d|%d|%d|%d|%d|%d|%d|%s|%s|%s|%s\n" % (
        row["id"], len(data), secs, fps, row["start_song"],
        row["load_addr"], row["init_addr"], row["play_addr"],
        clean(row["title"])[:40], clean(row["author"])[:40], clean(row["released"])[:20],
        scroll_text(scroll) if scroll else "")
    w.write(head.encode("latin-1", "replace") + data)


def tune3(jb: Jukebox, row, max_addr: int) -> tuple[bytes, int, bytes, int]:
    """Code, adresse du bloc de relais, bloc et « complet » d'un morceau v2 (SPEC-v2.md §5.4, §5.5).
    Relais servis seulement si la 2e émulation de sidscan les a vérifiés (verif = ok) et si le bloc tient sous max_addr ;
    sinon le morceau part tel quel (relais 0, complet 0) et sera joué en direct."""
    data = tune_code(jb.payload(row))
    if row["verif"] != "ok" or not row["nrelais"]:
        return data, 0, b"", 0
    rz, n = row["relay_addr"], row["relay_len"]
    if rz + n - 1 > max_addr:
        return data, 0, b"", 0
    try:
        code, block = build_relays(data, row["load_addr"], row["s_relais"], rz)
        if len(block) != n:
            raise ValueError("taille du bloc %d au lieu de %d" % (len(block), n))
    except ValueError as e:
        log.warning("relais refusés pour %d (%s) : %s", row["id"], row["path"], e)
        return data, 0, b"", 0
    return code, rz, block, row["s_complet"]


async def send_tune3(w: asyncio.StreamWriter, jb: Jukebox, row, max_addr: int, scroll: Path | None = None):
    if row is None:
        w.write(b"ERR|aucun morceau\n")
        return
    code, rz, block, complet = tune3(jb, row, max_addr)
    secs = int(row["seconds"] or DEFAULT_SECONDS)
    fps = 60 if row["clock"] == "NTSC" else 50
    head = "OK3|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%s|%s|%s|%s\n" % (
        row["id"], len(code), secs, fps, row["start_song"],
        row["load_addr"], row["init_addr"], row["play_addr"], rz, len(block), complet,
        clean(row["title"])[:40], clean(row["author"])[:40], clean(row["released"])[:20],
        scroll_text(scroll) if scroll else "")
    w.write(head.encode("latin-1", "replace") + code + block)


def cut(w):
    """Coupe une connexion par un vrai RST (SO_LINGER à 0) : un simple close() envoie un FIN, que l'Ultimate peut ignorer."""
    try:
        sock = w.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        w.transport.abort()
    except Exception:
        pass


async def handle(r: asyncio.StreamReader, w: asyncio.StreamWriter, jb: Jukebox):
    peer = w.get_extra_info("peername")
    ip = ipkey(peer[0]) if peer else "?"
    if not jb.admit(ip, w):
        log.info("refusé %s (trop de connexions)", peer)
        w.close()
        return
    log.info("connexion %s", peer)
    first = True
    try:
        while True:
            line = await asyncio.wait_for(r.readline(), timeout=FIRST_LINE_TIMEOUT if first else IDLE_TIMEOUT)
            first = False
            if not line:
                break
            cmd, _, arg = line.decode("latin-1").strip().partition(" ")
            cmd = cmd.upper()
            arg = arg.strip()
            if cmd not in ("QUIT", "STATS") and not jb.req_ok(ip):
                w.write(b"ERR|trop de requetes\n")
                await w.drain()
                continue
            if cmd == "RANDOM":
                row = jb.pick(arg[:40] or None)
                if row:
                    log.info("%s RANDOM %r -> %s", peer, arg, row["path"])
                await send_tune(w, jb, row, jb.scroll)
            elif cmd == "RANDOM2":
                lim, _, pat = arg.partition(" ")
                if len(lim) != 4 or any(c not in "0123456789abcdefABCDEF" for c in lim) or int(lim, 16) < MIN_MAX_ADDR:
                    w.write(b"ERR|limite invalide\n")
                else:
                    row = jb.pick(pat.strip()[:40] or None, int(lim, 16))
                    if row:
                        log.info("%s RANDOM2 %s %r -> %s", peer, lim.upper(), pat.strip(), row["path"])
                    await send_tune(w, jb, row, jb.scroll)
            elif cmd in ("RANDOM3", "GET3") and jb.scan_version is None:
                w.write(b"ERR|commande indisponible\n")
            elif cmd == "RANDOM3":
                lim, _, pat = arg.partition(" ")
                if len(lim) != 4 or any(c not in "0123456789abcdefABCDEF" for c in lim) or int(lim, 16) < MIN_MAX_ADDR:
                    w.write(b"ERR|limite invalide\n")
                else:
                    row = jb.pick3(pat.strip()[:40] or None, int(lim, 16))
                    if row:
                        log.info("%s RANDOM3 %s %r -> %s", peer, lim.upper(), pat.strip(), row["path"])
                    await send_tune3(w, jb, row, int(lim, 16), jb.scroll)
            elif cmd == "GET3" and arg.isdigit():
                await send_tune3(w, jb, jb.get3(int(arg)), SCAN_HISTART - 1, jb.scroll)
            elif cmd == "GET" and arg.isdigit():
                await send_tune(w, jb, jb.get(int(arg)), jb.scroll)
            elif cmd == "STATS":
                ok, total = jb.stats()
                w.write(f"STATS|{ok}|{total}\n".encode())
            elif cmd == "QUIT":
                break
            else:
                w.write(b"ERR|commande inconnue\n")
            await w.drain()
    except (asyncio.TimeoutError, ConnectionError, ValueError):     # ValueError : ligne plus longue que MAX_LINE
        pass
    except Exception:
        log.exception("erreur avec %s", peer)
    finally:
        jb.leave(ip, w)
        w.close()
        log.info("déconnexion %s", peer)


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=Path("jukebox.db"))
    ap.add_argument("--root", type=Path, required=True, help="dossier C64Music")
    ap.add_argument("--scroll", type=Path, default=Path(__file__).resolve().parent / "scroll.txt",
                    help="texte du scroller (relu à chaque morceau)")
    ap.add_argument("--scroll-user", type=Path, default=Path(__file__).resolve().parent / "data" / "scroll_user.txt",
                    help="texte écrit par web.py ; remplacé par --scroll après --scroll-ttl secondes")
    ap.add_argument("--scroll-ttl", type=int, default=3600)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=6474)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    jb = Jukebox(a.db, a.root, a.scroll, a.scroll_user, a.scroll_ttl)
    srv = await asyncio.start_server(lambda r, w: handle(r, w, jb), a.host, a.port, limit=MAX_LINE)
    ok, total = jb.stats()
    log.info("jukebox sur %s:%d, %d morceaux compatibles sur %d ; analyse v2 : %s", a.host, a.port, ok, total,
             "version %d (HISTART $%04X, %d appels)" % (jb.scan_version, SCAN_HISTART, SCAN_CALLS)
             if jb.scan_version is not None else "absente (RANDOM3/GET3 refusés)")
    async with srv:
        await srv.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
