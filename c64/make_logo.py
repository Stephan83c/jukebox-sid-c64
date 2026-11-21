#!/usr/bin/env python3
# SID Jukebox C64
# Copyright (C) 2026 Stephan83c
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version. It is
# distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.
"""Génère logo.s : les lettres géantes du titre (16 x 24 pixels = 2 x 3 caractères).

Les formes viennent de la même police que le scroller (la vraie police du C64, chargen_set1.bin extraite de VICE
par dump_chargen.py), agrandie : chaque point de la lettre 8x8 devient un bloc de 2 x 3 pixels. Chaque lettre est
découpée en 6 caractères 8x8 (2 colonnes, 3 lignes). Codes de caractères : $80-$A7 pour les 40 premiers, puis
$C2-$D5 pour les 20 suivants (voir play.s).
"""
TEXT = "SID JUKEBOX"
COL0 = 9                      # première colonne du logo à l'écran (11 lettres x 2 = 22 colonnes)
CODES = list(range(0x80, 0xA8)) + list(range(0xC2, 0xE0))      # codes libres, dans l'ordre
rom = open("chargen_set1.bin", "rb").read()

HEADER = (
    "; SID Jukebox C64\n; Copyright (C) 2026 Stephan83c\n; SPDX-License-Identifier: GPL-3.0-or-later\n;\n"
    "; This program is free software: you can redistribute it and/or modify it under the\n"
    "; terms of the GNU General Public License as published by the Free Software Foundation,\n"
    "; either version 3 of the License, or (at your option) any later version. It is\n"
    "; distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.\n")

def screen_code(ch):
    return ord(ch) - 64 if "A" <= ch <= "Z" else ord(ch)

def letter(ch):
    """16 colonnes x 24 lignes de 0/1."""
    g = rom[screen_code(ch) * 8: screen_code(ch) * 8 + 8]
    px = []
    for y in range(24):
        row = g[y // 3]
        px.append([(row >> (7 - x // 2)) & 1 for x in range(16)])
    return px

def cell(px, cx, cy):
    out = []
    for y in range(8):
        b = 0
        for x in range(8):
            b = (b << 1) | px[cy * 8 + y][cx * 8 + x]
        out.append(b)
    return out

glyphs, rows = [], ([], [], [])
n = 0
for ch in TEXT:
    if ch == " ":
        for r in rows:
            r += [32, 32]
        continue
    px = letter(ch)
    for cy in range(3):
        for cx in range(2):
            glyphs += cell(px, cx, cy)
    for cy in range(3):
        k = 6 * n + 2 * cy
        rows[cy].extend([CODES[k], CODES[k + 1]])
    n += 1

assert 6 * n <= len(CODES), "trop de lettres distinctes"
ng = len(glyphs)

def bytes_(name, data):
    lines = [f"{name}:"]
    for i in range(0, len(data), 8):
        lines.append("        .byte " + ", ".join(f"${b:02X}" for b in data[i:i + 8]))
    return "\n".join(lines)

with open("logo.s", "w") as f:
    f.write(HEADER + "; généré par make_logo.py\n        .export logo_glyphs, logo_row0, logo_row1, logo_row2, LOGO_COL, LOGO_NGLYPH\n")
    f.write(f"LOGO_COL = {COL0}\nLOGO_NGLYPH = {ng}\n        .rodata\n")
    f.write(bytes_("logo_glyphs", glyphs) + "\n")
    for i, r in enumerate(rows):
        f.write(bytes_(f"logo_row{i}", r) + "\n")
print(n, "lettres,", ng, "octets de formes")
