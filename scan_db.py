#!/usr/bin/env python3
# SID Jukebox C64
# Copyright (C) 2026 Stephan83c
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version. It is
# distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.
"""Analyse v2.0 : lance sidscan sur les morceaux de la base et remplit la table « scan » (SPEC-v2.md §4.3).

Morceaux analysés : ceux qui passent les règles statiques (compatible = 1) et ceux écartés à la main (known_bad),
pour les réévaluer. Le sous-morceau joué est le sous-morceau de départ ; images/s = 60 si l'horloge est NTSC, 50 sinon.

    python3 scan_db.py --root ../hvsc/C64Music [--histart AF00] [--calls 10000] [--jobs 12] [--ids 13636,6301]

Ne touche pas aux colonnes de la table « tunes ». Les lignes d'une même (version, histart, appels) sont remplacées.
Compiler sidscan avant : cc -O2 -o sidscan sidscan.c
"""
import argparse
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLS = ("tune_id song verdict reject complet relay_addr relay_len nsites nrelais init_cycles play_max "
        "port_init port_play lit_02a6 verif relais autres").split()

SCHEMA = """CREATE TABLE IF NOT EXISTS scan (
    tune_id INTEGER NOT NULL, song INTEGER NOT NULL,
    scan_version INTEGER NOT NULL, histart INTEGER NOT NULL, calls INTEGER NOT NULL,
    verdict TEXT NOT NULL,          -- ok / ko
    reject TEXT,                    -- raison du refus (scan_client, scan_save, scan_jam, scan_initlong, scan_playlong, scan_silent)
    complet INTEGER NOT NULL,       -- 1 = toutes les écritures SID relayées (§5.5)
    relay_addr INTEGER NOT NULL, relay_len INTEGER NOT NULL,
    nsites INTEGER NOT NULL, nrelais INTEGER NOT NULL,
    init_cycles INTEGER, play_max INTEGER,   -- play_max : cycles du plus long appel, relais compris
    port_init INTEGER, port_play INTEGER,    -- $01 laissé par le morceau
    lit_02a6 INTEGER,                        -- lit l'indicateur PAL/NTSC du KERNAL
    verif TEXT,                     -- 2e émulation avec les relais : ok, diff, plante, copie, -
    relais TEXT,                    -- « adresse:opcode » dans l'ordre des relais (ce que le serveur remplace)
    autres TEXT,                    -- sites non relayés « adresse:opcode:raison »
    PRIMARY KEY (tune_id, song, scan_version, histart, calls))"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=HERE / "jukebox.db")
    ap.add_argument("--root", type=Path, required=True, help="dossier C64Music de la HVSC")
    ap.add_argument("--sidscan", type=Path, default=HERE / "sidscan")
    ap.add_argument("--histart", default="AF00", help="HISTART du client, en hexadécimal")
    ap.add_argument("--calls", type=int, default=10000, help="appels de play émulés (D8)")
    ap.add_argument("--jobs", type=int, default=12)
    ap.add_argument("--ids", help="liste d'id séparés par des virgules (sinon toute la base)")
    a = ap.parse_args()

    version = int(subprocess.run([str(a.sidscan), "--version"], capture_output=True, text=True, check=True).stdout)
    histart = int(a.histart, 16)
    con = sqlite3.connect(a.db)
    con.execute(SCHEMA)
    q = ("SELECT id, path, start_song, clock FROM tunes WHERE (compatible = 1 OR reject = 'known_bad')")
    args = ()
    if a.ids:
        ids = [int(i) for i in a.ids.split(",")]
        q = "SELECT id, path, start_song, clock FROM tunes WHERE id IN (%s)" % ",".join("?" * len(ids))
        args = ids
    rows = con.execute(q + " ORDER BY id", args).fetchall()
    lines = ["%d|%s|%d|%d\n" % (i, a.root / p, s or 1, 60 if c == "NTSC" else 50) for i, p, s, c in rows]
    print("sidscan version %d, HISTART $%04X, %d appels, %d morceaux, %d processus"
          % (version, histart, a.calls, len(lines), a.jobs), file=sys.stderr)

    t = time.time()
    # Entrées et sorties par fichiers : avec des tubes, sidscan bloque dès que sa sortie dépasse 64 Ko
    # tant que l'entrée n'a pas été entièrement écrite (interblocage constaté le 2026-11-22).
    parts = [p for p in (lines[k::a.jobs] for k in range(a.jobs)) if p]
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        procs = []
        for k, part in enumerate(parts):
            fin = Path(tmp) / ("in%d" % k)
            fin.write_text("".join(part))
            with open(fin) as i, open(Path(tmp) / ("out%d" % k), "w") as o:
                procs.append(subprocess.Popen([str(a.sidscan), "%04X" % histart, str(a.calls)], stdin=i, stdout=o))
        for k, pr in enumerate(procs):
            pr.wait()
            if pr.returncode:
                sys.exit("sidscan a échoué (code %d)" % pr.returncode)
            out += (Path(tmp) / ("out%d" % k)).read_text().splitlines()

    recs = []
    for ln in out:
        f = ln.split("|")
        if len(f) != len(COLS):
            sys.exit("ligne illisible : " + ln[:200])
        d = dict(zip(COLS, f))
        recs.append((int(d["tune_id"]), int(d["song"]), version, histart, a.calls, d["verdict"], d["reject"] or None,
                     int(d["complet"]), int(d["relay_addr"], 16), int(d["relay_len"]), int(d["nsites"]), int(d["nrelais"]),
                     int(d["init_cycles"]), int(d["play_max"]), int(d["port_init"], 16), int(d["port_play"], 16),
                     int(d["lit_02a6"]), d["verif"], d["relais"], d["autres"]))
    with con:
        con.executemany("INSERT OR REPLACE INTO scan VALUES (%s)" % ",".join("?" * 20), recs)

    n = len(recs)
    ok = [r for r in recs if r[5] == "ok"]
    print("%d morceaux analysés en %.0f s" % (n, time.time() - t))
    print("acceptés : %d ; refusés : %d" % (len(ok), n - len(ok)))
    for k, v in Counter(r[6] for r in recs if r[5] == "ko").most_common():
        print("  %-14s %d" % (k, v))
    print("acceptés avec relais complet : %d ; partiel : %d ; sans relais : %d"
          % (sum(1 for r in ok if r[7]), sum(1 for r in ok if not r[7] and r[11]), sum(1 for r in ok if not r[11])))
    print("vérification (2e émulation) : %s" % dict(Counter(r[17] for r in ok)))
    print("lisent $02A6 : %d ; laissent $01 modifié : %d"
          % (sum(1 for r in ok if r[16]), sum(1 for r in ok if r[14] != 0x36 or r[15] != 0x36)))


if __name__ == "__main__":
    main()
