#!/usr/bin/env python3
"""Serveur jukebox SID : tirage aléatoire, un morceau par demande, sans état partagé.

Protocole texte (une commande par ligne, réponses terminées par \\n) :
    RANDOM [motif]   -> OK|id|taille|secondes|images/s|sous-morceau|chargement|init|play|titre|auteur|année\\n
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
from pathlib import Path

log = logging.getLogger("jukebox")
DEFAULT_SECONDS = 180


def clean(s: str) -> str:
    """Pas de '|' ni de retour ligne dans les champs texte."""
    return " ".join((s or "").replace("|", "/").split())


class Jukebox:
    def __init__(self, db: Path, root: Path):
        self.con = sqlite3.connect(db, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.root = root

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


async def send_tune(w: asyncio.StreamWriter, jb: Jukebox, row):
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
    head = "OK|%d|%d|%d|%d|%d|%d|%d|%d|%s|%s|%s\n" % (
        row["id"], len(data), secs, fps, row["start_song"],
        row["load_addr"], row["init_addr"], row["play_addr"],
        clean(row["title"]), clean(row["author"]), clean(row["released"]))
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
                await send_tune(w, jb, row)
            elif cmd == "GET" and arg.isdigit():
                await send_tune(w, jb, jb.get(int(arg)))
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
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=6474)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    jb = Jukebox(a.db, a.root)
    srv = await asyncio.start_server(lambda r, w: handle(r, w, jb), a.host, a.port)
    ok, total = jb.stats()
    log.info("jukebox sur %s:%d, %d morceaux compatibles sur %d", a.host, a.port, ok, total)
    async with srv:
        await srv.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
