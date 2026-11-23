#!/usr/bin/env python3
"""Prépare un morceau du jukebox pour la version démo (sans réseau), tel que le servirait RANDOM3 (SPEC-v2.md §5.4, §6.1) :
build/tune.bin (code brut, sites d'écriture SID remplacés), build/relay.bin (bloc de relais) et build/tune.inc (constantes).
La fabrication est celle du serveur (server.tune3 du dépôt du jukebox).

    tools/mktune.py ID      (JUKEBOX = dossier du jukebox, HVSC = dossier C64Music, si différents)
"""
import os
import re
import sys
import unicodedata
from pathlib import Path

J = Path(os.environ.get("JUKEBOX", str(Path(__file__).resolve().parents[2])))
H = Path(os.environ.get("HVSC", str(Path(__file__).resolve().parents[3] / "hvsc" / "C64Music")))
OUT = Path(__file__).resolve().parent.parent / "build"
sys.path.insert(0, str(J))
import server  # noqa: E402

jb = server.Jukebox(J / "jukebox.db", H)
r = jb.get3(int(sys.argv[1]))
if r is None:
    sys.exit("id inconnu ou refusé par l'analyse")
code, rz, block, complet = server.tune3(jb, r, server.SCAN_HISTART - 1)
OUT.mkdir(exist_ok=True)
(OUT / "tune.bin").write_bytes(code)
(OUT / "relay.bin").write_bytes(block)


def clean(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r'[^A-Z0-9 .,!?\-/\':*]', " ", s)[:30]


fps = 60 if r["clock"] == "NTSC" else 50
(OUT / "tune.inc").write_text(f'''// généré par tools/mktune.py (id {r["id"]})
.const TUNE_LOAD = ${r["load_addr"]:04X}
.const TUNE_INIT = ${r["init_addr"]:04X}
.const TUNE_PLAY = ${r["play_addr"]:04X}
.const TUNE_SIZE = {len(code)}
.const TUNE_FPS = {fps}
.const TUNE_SONG = {r["start_song"]}
.const TUNE_SECS = 60
.const RELAY_ADDR = ${rz:04X}
.const RELAY_LEN = {len(block)}
.const RELAY_COMPLET = {complet}
.const TUNE_TITLE = "{clean(r["title"])}"
.const TUNE_AUTHOR = "{clean(r["author"])}"
.const TUNE_RELEASED = "{clean(r["released"])}"
''')
print(r["id"], r["title"], f'load ${r["load_addr"]:04X} end ${r["end_addr"]:04X} init ${r["init_addr"]:04X} '
      f'play ${r["play_addr"]:04X} {fps} Hz, relais ${rz:04X} ({len(block)} octets), complet {complet}')
