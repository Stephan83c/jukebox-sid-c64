#!/usr/bin/env python3
# SID Jukebox C64
# Copyright (C) 2026 Stephan83c
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version. It is
# distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.
"""Écarte d'une base existante les morceaux dont init/play sont hors de la mémoire des morceaux.
Même règle que `entry_range` dans indexer.py, sans réindexer (issue #2).
Usage : python3 fix_entry_range.py [jukebox.db] [--max-addr 0xAEFF] [--min-load 0x0800]
"""
import argparse, sqlite3
ap = argparse.ArgumentParser()
ap.add_argument("db", nargs="?", default="jukebox.db")
ap.add_argument("--max-addr", type=lambda x: int(x, 0), default=0xAEFF)
ap.add_argument("--min-load", type=lambda x: int(x, 0), default=0x0800)
a = ap.parse_args()
c = sqlite3.connect(a.db)
c.execute("UPDATE tunes SET compatible=0, reject='entry_range' WHERE compatible=1 AND "
          "(init_addr<? OR init_addr>? OR play_addr<? OR play_addr>?)",
          (a.min_load, a.max_addr, a.min_load, a.max_addr))
print(c.total_changes, "morceau(x) écarté(s)")
c.commit()
print(c.execute("SELECT SUM(compatible) FROM tunes").fetchone()[0], "morceaux jouables")
