#!/usr/bin/env python3
# SID Jukebox C64
# Copyright (C) 2026 Stephan83c
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version. It is
# distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.
"""Génère demo.bin / demo.h / demo.s à partir d'un morceau du serveur (pour tester l'affichage dans VICE)."""
import socket, sys
tid = sys.argv[1] if len(sys.argv) > 1 else "27162"
s = socket.create_connection(("127.0.0.1", 6474), timeout=10)
s.sendall(f"GET {tid}\n".encode())
f = s.makefile("rb")
h = f.readline().decode("latin-1").rstrip("\n").split("|")
assert h[0] == "OK", h
_, i, size, secs, song, load, init, play, title, author, rel = h
data = f.read(int(size))
open("demo.bin", "wb").write(data)
open("demo.h", "w").write(f'''#define DEMO_LOAD {load}u
#define DEMO_INIT {init}u
#define DEMO_PLAY {play}u
#define DEMO_SIZE {size}u
#define DEMO_SECS {secs}u
#define DEMO_TITLE "{title.upper()}"
#define DEMO_AUTHOR "{author.upper()}"
#define DEMO_RELEASED "{rel.upper()}"
''')
open("demo.s", "w").write('        .export _demo_data\n        .rodata\n_demo_data: .incbin "demo.bin"\n')
print(h[7:], size, "octets")
