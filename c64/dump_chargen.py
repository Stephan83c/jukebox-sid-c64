#!/usr/bin/env python3
# SID Jukebox C64
# Copyright (C) 2026 Stephan83c
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version. It is
# distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.
"""Extrait le jeu de caractères du C64 (1 Ko, majuscules/graphiques) de VICE vers chargen_set1.bin.

Nécessaire seulement pour regénérer scroll.s avec make_scroll.py. On ne livre pas la ROM : on la lit
dans l'émulateur installé sur la machine (x64sc doit exister), par son moniteur à distance.
"""
import re
import socket
import subprocess
import time

PORT = 6510
vice = subprocess.Popen(["x64sc", "-default", "+sound", "-warp", "-remotemonitor",
                         "-remotemonitoraddress", f"ip4://127.0.0.1:{PORT}"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(6)
    s = socket.create_connection(("127.0.0.1", PORT), timeout=5)

    def cmd(c, wait=0.5):
        s.sendall((c + "\n").encode())
        time.sleep(wait)
        s.settimeout(0.6)
        out = b""
        try:
            while True:
                d = s.recv(65536)
                if not d:
                    break
                out += d
        except Exception:
            pass
        return out.decode("latin-1")

    cmd("", 0.5)
    cmd("bank rom")                       # la ROM des caractères est en $D000 dans la banque "rom"
    data = bytearray()
    for base in range(0xD000, 0xD400, 0x100):
        rows = {}
        for line in cmd("m %04x %04x" % (base, base + 0xFF), 0.5).splitlines():
            m = re.match(r">C:([0-9a-f]{4})\s+((?:[0-9a-f]{2}\s+)+)", line)
            if m:
                rows[int(m.group(1), 16)] = bytes(int(x, 16) for x in m.group(2).split())
        for a in sorted(rows):
            data += rows[a]
    assert len(data) == 1024, len(data)
    assert data[8:16] == bytes([0x18, 0x3C, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00]), "pas la lettre A ?"
    open("chargen_set1.bin", "wb").write(data)
    print("chargen_set1.bin écrit (1024 octets)")
finally:
    vice.terminate()
