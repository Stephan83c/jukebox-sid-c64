#!/usr/bin/env python3
"""Génère scroll.s : lettres du scroller (8 pixels de large x 12 de haut = 2 caractères superposés).

Les formes viennent de la vraie police du C64 (chargen_set1.bin, extraite de VICE) étirée en hauteur
(8 lignes -> 12). Le texte est ici : un octet par colonne de 8 pixels (0 = espace, n = n-ième lettre
distincte, $FF = fin). Codes de caractères utilisés : 64 + 2 * (n - 1) (haut) et +1 (bas) pour n <= 32, 168 + 2 * (n - 33) au-delà.
"""
TEXT = "          SID JUKEBOX  ***  PRESS SPACE FOR THE NEXT TUNE  ***          "   # texte de secours (le vrai vient du serveur : scroll.txt)
rom = open("chargen_set1.bin", "rb").read()

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
    rows = [0] * 16
    for y in range(12):                      # 8 lignes étirées en 12, centrées dans 16
        rows[2 + y] = g[y * 8 // 12]
    glyphs += bytes(rows[:8]) + bytes(rows[8:])       # case du haut, puis case du bas
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
