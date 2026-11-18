#!/usr/bin/env python3
"""Génère scroll.s : lettres du scroller (8 pixels de large x 12 de haut = 2 caractères superposés).

Les formes viennent de la vraie police du C64 (chargen_set1.bin, extraite de VICE) étirée en hauteur
(8 lignes -> 12). Le texte est ici : un octet par colonne de 8 pixels (0 = espace, n = n-ième lettre
distincte, $FF = fin). Codes de caractères utilisés : 64 + 2 * (n - 1) (haut) et +1 (bas).
"""
TEXT = ("          JUKEBOX SID  ***  A SID RADIO FOR THE COMMODORE 64 ULTIMATE  ***  "
        "CODED BY STEPHAN  ***  "
        "TUNES FROM THE HIGH VOLTAGE SID COLLECTION  ***  "
        "PRESS S TO SEARCH BY ARTIST OR TITLE  ***  PRESS SPACE FOR THE NEXT TUNE  ***  "
        "PRESS V TO SWITCH THE VU METERS ON OR OFF  ***  PRESS Q TO QUIT  ***  "
        "STEPHAN PRESENTS JUKEBOX SID  ***  "
        "GREETINGS TO THE C64 SCENE  ***  KEEP THE SID ALIVE  ***  MADE BY STEPHAN  ***          ")
rom = open("chargen_set1.bin", "rb").read()

def screen_code(ch):
    if "A" <= ch <= "Z":
        return ord(ch) - 64
    return ord(ch)            # chiffres, ponctuation : même code que l'ASCII

order = sorted(set(TEXT) - {" "})
assert len(order) <= 32, order
glyphs = bytearray()
for ch in order:
    g = rom[screen_code(ch) * 8: screen_code(ch) * 8 + 8]
    rows = [0] * 16
    for y in range(12):                      # 8 lignes étirées en 12, centrées dans 16
        rows[2 + y] = g[y * 8 // 12]
    glyphs += bytes(rows[:8]) + bytes(rows[8:])       # case du haut, puis case du bas
glyphs += bytes(512 - len(glyphs))           # complété à 512 octets (32 lettres)
stream = [0 if ch == " " else order.index(ch) + 1 for ch in TEXT] + [0xFF]

def dump(name, data, per=16):
    out = [name + ":"]
    for i in range(0, len(data), per):
        out.append("        .byte " + ", ".join(f"${b:02X}" for b in data[i:i + per]))
    return "\n".join(out)

with open("scroll.s", "w") as f:
    f.write("; généré par make_scroll.py\n        .export scr_glyphs, scrtext\n        .rodata\n")
    f.write(dump("scr_glyphs", glyphs, 8) + "\n" + dump("scrtext", stream) + "\n")
print(len(order), "lettres distinctes :", "".join(order), "|", len(TEXT), "colonnes de texte")
