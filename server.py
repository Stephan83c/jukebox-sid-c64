#!/usr/bin/env python3
"""Serveur jukebox SID : tirage aléatoire, un morceau par demande, sans état partagé.

Protocole texte (une commande par ligne, réponses terminées par \\n) :
    RANDOM [motif]   -> OK|id|taille|secondes|images/s|sous-morceau|chargement|init|play|titre|auteur|année|scroller\\n
                        + <taille> octets de code brut (sans en-tête PSID), à copier à l'adresse de chargement
                        (motif : sous-chaîne cherchée dans l'auteur ou le titre, sans tenir compte de la casse)
    GET <id>         -> idem pour un morceau précis
    STATS            -> STATS|compatibles|total\\n
    QUIT             -> ferme la connexion
    erreur           -> ERR|message\\n
"""
import argparse
import asyncio
import logging
import sqlite3
import time
import unicodedata
from pathlib import Path

log = logging.getLogger("jukebox")
DEFAULT_SECONDS = 180


def clean(s: str) -> str:
    """Pas de '|' ni de retour ligne dans les champs texte."""
    return " ".join((s or "").replace("|", "/").split())


SCROLL_ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ*.,!?- ")
SCROLL_MAX = 150


def scroll_text(path: Path) -> str:
    """Texte du scroller : relu à chaque morceau, réduit à l'alphabet du C64 (A-Z * . , ! ? -),
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
        self.con = sqlite3.connect(db, check_same_thread=False)
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

    def pick(self, pattern: str | None = None):
        if pattern:
            esc = pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like = f"%{esc}%"
            return self.con.execute(
                "SELECT * FROM tunes WHERE compatible=1 AND (author LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\')"
                " ORDER BY RANDOM() LIMIT 1", (like, like)).fetchone()
        return self.con.execute(
            "SELECT * FROM tunes WHERE compatible=1 ORDER BY RANDOM() LIMIT 1").fetchone()

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
    log.info("connexion %s", peer)
    try:
        while True:
            line = await asyncio.wait_for(r.readline(), timeout=300)
            if not line:
                break
            cmd, _, arg = line.decode("latin-1").strip().partition(" ")
            cmd = cmd.upper()
            arg = arg.strip()
            if cmd == "RANDOM":
                row = jb.pick(arg[:40] or None)
                if row:
                    log.info("%s RANDOM %r -> %s", peer, arg, row["path"])
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
    except (asyncio.TimeoutError, ConnectionError):
        pass
    finally:
        w.close()
        log.info("déconnexion %s", peer)


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=Path("jukebox.db"))
    ap.add_argument("--root", type=Path, required=True, help="dossier C64Music")
    ap.add_argument("--scroll", type=Path, default=Path(__file__).resolve().parent / "scroll.txt",
                    help="texte du scroller (relu à chaque morceau)")
    ap.add_argument("--scroll-user", type=Path, default=Path(__file__).resolve().parent / "scroll_user.txt",
                    help="texte écrit par web.py ; remplacé par --scroll après --scroll-ttl secondes")
    ap.add_argument("--scroll-ttl", type=int, default=3600)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=6474)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    jb = Jukebox(a.db, a.root, a.scroll, a.scroll_user, a.scroll_ttl)
    srv = await asyncio.start_server(lambda r, w: handle(r, w, jb), a.host, a.port)
    ok, total = jb.stats()
    log.info("jukebox sur %s:%d, %d morceaux compatibles sur %d", a.host, a.port, ok, total)
    async with srv:
        await srv.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
