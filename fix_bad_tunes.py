#!/usr/bin/env python3
"""Écarte d'une base existante les morceaux listés dans bad_tunes.txt (raison « known_bad »), sans réindexer.
Usage : python3 fix_bad_tunes.py [jukebox.db]
"""
import sqlite3, sys
from pathlib import Path
db = sys.argv[1] if len(sys.argv) > 1 else "jukebox.db"
md5s = [l.split()[0].lower() for l in Path(__file__).with_name("bad_tunes.txt").read_text(encoding="utf-8").splitlines()
        if l.strip() and l[0] != "#"]
c = sqlite3.connect(db)
n = 0
for m in md5s:
    n += c.execute("UPDATE tunes SET compatible=0, reject='known_bad' WHERE compatible=1 AND md5=?", (m,)).rowcount
c.commit()
print(n, "morceau(x) écarté(s) sur", len(md5s), "listé(s)")
print(c.execute("SELECT SUM(compatible) FROM tunes").fetchone()[0], "morceaux jouables")
