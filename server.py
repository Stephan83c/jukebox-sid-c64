#!/usr/bin/env python3
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
    STATS            -> STATS|compatibles|total\\n
    QUIT             -> ferme la connexion
    erreur           -> ERR|message\\n
"""
import argparse
import asyncio
import ipaddress
import logging
import sqlite3
import time
import unicodedata
from pathlib import Path

log = logging.getLogger("jukebox")
DEFAULT_SECONDS = 180
MAX_CONN_IP = 8          # connexions simultanées par IP (un C64 en prend une)
MAX_CONN = 200           # connexions simultanées au total
REQ_WINDOW, REQ_MAX = 60, 30      # commandes par IP et par minute
FIRST_LINE_TIMEOUT = 20  # secondes pour envoyer la première commande (sinon on coupe)
IDLE_TIMEOUT = 300       # secondes d'attente entre deux commandes (un C64 reste connecté pendant un morceau)
MAX_LINE = 1024          # taille maximale d'une commande
LEGACY_MAX_ADDR = 0xA6FF  # fin de zone des clients qui envoient RANDOM sans limite (HISTART $A700)
MIN_MAX_ADDR = 0x0900     # limite minimale acceptée pour RANDOM2 (en dessous, rien ne tient)


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


def clean(s: str) -> str:
    """Pas de '|' ni de retour ligne dans les champs texte."""
    return " ".join((s or "").replace("|", "/").split())


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


class Jukebox:
    def __init__(self, db: Path, root: Path, scroll: Path | None = None,
                 scroll_user: Path | None = None, scroll_ttl: int = 3600):
        self.scroll_default = scroll
        self.scroll_user = scroll_user
        self.scroll_ttl = scroll_ttl
        # base ouverte en lecture seule : le serveur n'écrit jamais dedans (update_db.sh la remplace de l'extérieur)
        self.con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False)
        self.conns: dict[str, int] = {}                  # connexions ouvertes par IP
        self.total = 0
        self.reqs: dict[str, list[float]] = {}           # horodatage des commandes récentes par IP
        self.con.row_factory = sqlite3.Row
        self.root = root

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
        return self.scroll_default

    def admit(self, ip: str) -> bool:
        """Ouvre une place pour cette IP, ou refuse si l'IP ou le serveur est plein."""
        if self.total >= MAX_CONN or self.conns.get(ip, 0) >= MAX_CONN_IP:
            return False
        self.conns[ip] = self.conns.get(ip, 0) + 1
        self.total += 1
        return True

    def leave(self, ip: str):
        self.total -= 1
        if self.conns[ip] <= 1:
            del self.conns[ip]
        else:
            self.conns[ip] -= 1

    def req_ok(self, ip: str) -> bool:
        now = time.time()
        h = [t for t in self.reqs.get(ip, []) if now - t < REQ_WINDOW]
        h.append(now)
        self.reqs[ip] = h
        if len(self.reqs) > 5000:
            self.reqs = {k: v for k, v in self.reqs.items() if v and now - v[-1] < REQ_WINDOW}
        return len(h) <= REQ_MAX

    def pick(self, pattern: str | None = None, max_addr: int = LEGACY_MAX_ADDR):
        if pattern:
            esc = pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like = f"%{esc}%"
            return self.con.execute(
                "SELECT * FROM tunes WHERE compatible=1 AND end_addr<=? AND (author LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\')"
                " ORDER BY RANDOM() LIMIT 1", (max_addr, like, like)).fetchone()
        return self.con.execute(
            "SELECT * FROM tunes WHERE compatible=1 AND end_addr<=? ORDER BY RANDOM() LIMIT 1", (max_addr,)).fetchone()

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
    data = jb.payload(row)
    # on enlève l'en-tête PSID (et l'adresse de chargement intégrée) : le C64 reçoit le code brut
    off = (data[6] << 8) | data[7]
    if (data[8] << 8 | data[9]) == 0:
        off += 2
    data = data[off:]
    secs = int(row["seconds"] or DEFAULT_SECONDS)
    fps = 60 if row["clock"] == "NTSC" else 50     # cadence pour laquelle le morceau est écrit
    head = "OK|%d|%d|%d|%d|%d|%d|%d|%d|%s|%s|%s|%s\n" % (
        row["id"], len(data), secs, fps, row["start_song"],
        row["load_addr"], row["init_addr"], row["play_addr"],
        clean(row["title"])[:40], clean(row["author"])[:40], clean(row["released"])[:20],
        scroll_text(scroll) if scroll else "")
    w.write(head.encode("latin-1", "replace") + data)


async def handle(r: asyncio.StreamReader, w: asyncio.StreamWriter, jb: Jukebox):
    peer = w.get_extra_info("peername")
    ip = ipkey(peer[0]) if peer else "?"
    if not jb.admit(ip):
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
            if not jb.req_ok(ip):
                w.write(b"ERR|trop de requetes\n")
                await w.drain()
                continue
            cmd, _, arg = line.decode("latin-1").strip().partition(" ")
            cmd = cmd.upper()
            arg = arg.strip()
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
        jb.leave(ip)
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
    log.info("jukebox sur %s:%d, %d morceaux compatibles sur %d", a.host, a.port, ok, total)
    async with srv:
        await srv.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
