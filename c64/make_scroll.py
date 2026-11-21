#!/usr/bin/env python3
# SID Jukebox C64
# Copyright (C) 2026 Stephan83c
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version. It is
# distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.
"""Génère scroll.s : lettres du scroller (8 pixels de large x 16 de haut = 2 caractères superposés).

Les formes viennent de la vraie police du C64 (chargen_set1.bin, extraite de VICE) doublée en hauteur
(8 lignes -> 16). Le texte est ici : un octet par colonne de 8 pixels (0 = espace, n = n-ième lettre
distincte, $FF = fin). Codes de caractères utilisés : 64 + 2 * (n - 1) (haut) et +1 (bas) pour n <= 32, 168 + 2 * (n - 33) au-delà.
"""
TEXT = "          SID JUKEBOX  ***  PRESS SPACE FOR THE NEXT TUNE  ***          "   # texte de secours (le vrai vient du serveur : scroll.txt)
rom = open("chargen_set1.bin", "rb").read()

HEADER = (
    "; SID Jukebox C64\n; Copyright (C) 2026 Stephan83c\n; SPDX-License-Identifier: GPL-3.0-or-later\n;\n"
    "; This program is free software: you can redistribute it and/or modify it under the\n"
    "; terms of the GNU General Public License as published by the Free Software Foundation,\n"
    "; either version 3 of the License, or (at your option) any later version. It is\n"
    "; distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.\n")

def screen_code(ch):
    if "A" <= ch <= "Z":
        return ord(ch) - 64
    return ord(ch)            # chiffres, ponctuation : même code que l'ASCII

# Alphabet FIXE (45 glyphes) : le texte reçu du serveur est traduit avec la même table (voir main.c).
# Les 32 premiers vont aux codes $40-$7F, les suivants (/ ' : et les chiffres) aux codes $A8-$C1 (play.s).
order = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ*.,!?-/':0123456789")
assert set(TEXT) - {" "} <= set(order), set(TEXT) - set(order)
glyphs = bytearray()
for ch in order:
    g = rom[screen_code(ch) * 8: screen_code(ch) * 8 + 8]
    rows = [g[y // 2] for y in range(16)]    # 8 lignes doublées : 16 lignes (toute la hauteur des deux cases)
    glyphs += bytes(rows[:8]) + bytes(rows[8:])       # case du haut, puis case du bas
stream = [0 if ch == " " else order.index(ch) + 1 for ch in TEXT] + [0xFF]

def dump(name, data, per=16):
    out = [name + ":"]
    for i in range(0, len(data), per):
        out.append("        .byte " + ", ".join(f"${b:02X}" for b in data[i:i + per]))
    return "\n".join(out)

with open("scroll.s", "w") as f:
    f.write(HEADER + "; généré par make_scroll.py\n        .export scr_glyphs, scrtext\n        .rodata\n")
    f.write(dump("scr_glyphs", glyphs, 8) + "\n" + dump("scrtext", stream) + "\n")
print(len(order), "lettres distinctes :", "".join(order), "|", len(TEXT), "colonnes de texte")
