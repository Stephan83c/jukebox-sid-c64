#!/usr/bin/env python3
"""Génère logo.s : les lettres géantes (16x16 pixels = 4 caractères) du titre.

Chaque lettre est dessinée avec une police grasse du PC, seuillée en noir et blanc, puis découpée en
4 caractères 8x8 (haut-gauche, haut-droit, bas-gauche, bas-droit). Utilisation : make_logo.py [police.ttf]
"""
import sys
from PIL import Image, ImageDraw, ImageFont

TEXT = "JUKEBOX SID"
FONT = sys.argv[1] if len(sys.argv) > 1 else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SIZE = int(sys.argv[2]) if len(sys.argv) > 2 else 19
COL0 = 9                      # première colonne du logo à l'écran (11 lettres x 2 = 22 colonnes)
BASE = 0x80                   # premier code de caractère personnalisé

font = ImageFont.truetype(FONT, SIZE)

def letter(ch):
    im = Image.new("L", (16, 16), 0)
    d = ImageDraw.Draw(im)
    bb = d.textbbox((0, 0), ch, font=font)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    d.text(((16 - w) // 2 - bb[0], (16 - h) // 2 - bb[1]), ch, font=font, fill=255)
    return [[1 if im.getpixel((x, y)) > 110 else 0 for x in range(16)] for y in range(16)]

def cell(px, cx, cy):
    out = []
    for y in range(8):
        b = 0
        for x in range(8):
            b = (b << 1) | px[cy * 8 + y][cx * 8 + x]
        out.append(b)
    return out

glyphs, cells0, cells1 = [], [], []
n = 0
for ch in TEXT:
    if ch == " ":
        cells0 += [32, 32]
        cells1 += [32, 32]
        continue
    px = letter(ch)
    for row in px:
        pass
    for cy in range(2):
        for cx in range(2):
            glyphs += cell(px, cx, cy)
    code = BASE + 4 * n
    cells0 += [code, code + 1]
    cells1 += [code + 2, code + 3]
    n += 1
    if "-v" in sys.argv:
        print(ch)
        for row in px:
            print("".join("#" if v else "." for v in row))

def bytes_(name, data):
    lines = [f"{name}:"]
    for i in range(0, len(data), 8):
        lines.append("        .byte " + ", ".join(f"${b:02X}" for b in data[i:i + 8]))
    return "\n".join(lines)

with open("logo.s", "w") as f:
    f.write("; généré par make_logo.py\n        .export logo_glyphs, logo_row0, logo_row1, LOGO_COL, LOGO_NGLYPH\n")
    f.write(f"LOGO_COL = {COL0}\nLOGO_NGLYPH = {len(glyphs)}\n        .rodata\n")
    f.write(bytes_("logo_glyphs", glyphs) + "\n")
    f.write(bytes_("logo_row0", cells0) + "\n")
    f.write(bytes_("logo_row1", cells1) + "\n")
print(n, "lettres,", len(glyphs), "octets de formes")
