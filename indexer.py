#!/usr/bin/env python3
"""Indexe la HVSC dans une base SQLite pour le jukebox C64.

Usage :
    python3 indexer.py /chemin/vers/C64Music [-o jukebox.db]
                       [--max-size 16384] [--max-addr 0xCFFF]
                       [--min-load 0x0400] [--allow-rsid]

Pour chaque .sid : lit l'en-tête PSID/RSID, retrouve la durée dans
DOCUMENTS/Songlengths.md5 (clé = MD5 du fichier complet), décide si le morceau
est « compatible » avec le lecteur C64 et note la raison du rejet sinon.
Tout est stocké (même les rejetés) : le serveur filtre avec `compatible = 1`.
"""
import argparse
import hashlib
import sqlite3
import struct
import sys
from pathlib import Path


def parse_time(s: str) -> float:
    """'mm:ss[.SSS]' -> secondes."""
    m, _, sec = s.partition(":")
    return int(m) * 60 + float(sec)


def load_songlengths(path: Path) -> dict[str, list[float]]:
    """MD5 -> liste des durées (une par sous-morceau)."""
    db: dict[str, list[float]] = {}
    for line in path.read_text(encoding="latin-1").splitlines():
        line = line.strip()
        if not line or line[0] in ";[" or "=" not in line:
            continue
        key, _, val = line.partition("=")
        try:
            db[key.lower()] = [parse_time(t) for t in val.split()]
        except ValueError:
            pass
    return db


def cstr(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("latin-1").strip()


def parse_sid(data: bytes):
    """Retourne un dict avec les infos de l'en-tête, ou None si illisible."""
    if len(data) < 0x76 or data[:4] not in (b"PSID", b"RSID"):
        return None
    magic = data[:4].decode()
    version, data_off, load, init, play, songs, start, speed = struct.unpack(">HHHHHHHI", data[4:22])
    info = {
        "format": magic,
        "version": version,
        "title": cstr(data[0x16:0x36]),
        "author": cstr(data[0x36:0x56]),
        "released": cstr(data[0x56:0x76]),
        "init": init,
        "play": play,
        "songs": songs,
        "start_song": start or 1,
        "speed": speed,
        "flags": 0,
        "sid2": 0,
        "sid3": 0,
    }
    if version >= 2 and len(data) >= 0x7C:
        info["flags"] = struct.unpack(">H", data[0x76:0x78])[0]
        info["sid2"] = data[0x7A]
        info["sid3"] = data[0x7B] if version >= 4 else 0
    payload = len(data) - data_off
    code_off = data_off
    if load == 0:  # l'adresse est dans les deux premiers octets des données
        if payload < 2:
            return None
        load = data[data_off] | (data[data_off + 1] << 8)
        payload -= 2
        code_off += 2
    info["head"] = bytes(data[code_off:code_off + 6])     # premiers octets du code du morceau
    info["load"] = load
    info["end"] = load + payload - 1
    info["payload"] = payload
    f = info["flags"]
    info["mus"] = bool(f & 1)
    info["clock"] = {0: "?", 1: "PAL", 2: "NTSC", 3: "PAL+NTSC"}[(f >> 2) & 3]
    info["model"] = {0: "?", 1: "6581", 2: "8580", 3: "6581+8580"}[(f >> 4) & 3]
    return info


# SEI ; LDA #$35 ; STA $01 ; JSR : enveloppe de morceaux compressés (ex. les « worktunes » de Blues_Muz) dont
# l'init décompresse vers le haut de la mémoire. 108 morceaux de la HVSC #85, tous dans ce cas (vérifié dans VICE).
UNPACKER_HEAD = bytes.fromhex("78a935850120")


def reject_reason(info, size, a) -> str | None:
    if info["format"] == "RSID" and not a.allow_rsid:
        return "rsid"
    if info["mus"]:
        return "mus"
    if info["sid2"] or info["sid3"]:
        return "multisid"
    if size > a.max_size:
        return "too_big"
    if info["load"] < a.min_load or info["end"] > a.max_addr:
        return "bad_range"
    if info["end"] > 0xFFFF:
        return "bad_range"
    if info["songs"] < 1:
        return "no_songs"
    if info["play"] == 0:
        return "play0"          # le morceau installe lui-même son interruption
    if info["head"] == UNPACKER_HEAD:
        return "unpacker"       # décompresse ses données jusqu'à $CFFF : écraserait le client C64
    bit = min(info["start_song"], 32) - 1
    if (info["speed"] >> bit) & 1:
        return "cia"            # cadencé par le timer CIA, pas à chaque image
    return None


SCHEMA = """
CREATE TABLE tunes (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,      -- relatif à C64Music, ex. MUSICIANS/H/Hubbard_Rob/Commando.sid
    md5 TEXT NOT NULL,
    format TEXT, version INTEGER,
    title TEXT, author TEXT, released TEXT,
    load_addr INTEGER, end_addr INTEGER, init_addr INTEGER, play_addr INTEGER,
    songs INTEGER, start_song INTEGER,
    clock TEXT, model TEXT,
    size INTEGER,
    seconds REAL,                   -- durée du sous-morceau de départ (NULL si inconnue)
    compatible INTEGER NOT NULL,
    reject TEXT
);
CREATE INDEX tunes_ok ON tunes(compatible);
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="dossier C64Music de la HVSC")
    ap.add_argument("-o", "--output", type=Path, default=Path("jukebox.db"))
    ap.add_argument("--max-size", type=lambda x: int(x, 0), default=16384, help="taille max du fichier (octets)")
    ap.add_argument("--min-load", type=lambda x: int(x, 0), default=0x0800, help="adresse de chargement minimale")
    ap.add_argument("--max-addr", type=lambda x: int(x, 0), default=0xBFFF, help="dernière adresse utilisable (le client C64 occupe $C000-$CFFF)")
    ap.add_argument("--allow-rsid", action="store_true", help="garder aussi les RSID")
    a = ap.parse_args()

    sl_path = a.root / "DOCUMENTS" / "Songlengths.md5"
    if not sl_path.exists():
        sys.exit(f"Introuvable : {sl_path}")
    lengths = load_songlengths(sl_path)
    print(f"{len(lengths)} entrées dans Songlengths.md5")

    if a.output.exists():
        a.output.unlink()
    con = sqlite3.connect(a.output)
    con.executescript(SCHEMA)

    stats: dict[str, int] = {}
    rows = []
    files = sorted(p for p in a.root.rglob("*") if p.suffix.lower() == ".sid")
    for p in files:
        data = p.read_bytes()
        info = parse_sid(data)
        rel = p.relative_to(a.root).as_posix()
        if info is None:
            stats["illisible"] = stats.get("illisible", 0) + 1
            continue
        md5 = hashlib.md5(data).hexdigest()
        durs = lengths.get(md5)
        secs = None
        if durs:
            secs = durs[min(info["start_song"], len(durs)) - 1]
        why = reject_reason(info, len(data), a)
        stats[why or "ok"] = stats.get(why or "ok", 0) + 1
        rows.append((
            rel, md5, info["format"], info["version"],
            info["title"], info["author"], info["released"],
            info["load"], info["end"], info["init"], info["play"],
            info["songs"], info["start_song"], info["clock"], info["model"],
            len(data), secs, 0 if why else 1, why,
        ))
    con.executemany(
        "INSERT INTO tunes (path, md5, format, version, title, author, released,"
        " load_addr, end_addr, init_addr, play_addr, songs, start_song, clock, model,"
        " size, seconds, compatible, reject) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    con.commit()

    total = len(rows)
    nolen = con.execute("SELECT COUNT(*) FROM tunes WHERE compatible=1 AND seconds IS NULL").fetchone()[0]
    print(f"\n{total} fichiers indexés -> {a.output}")
    for k, v in sorted(stats.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<10} {v:>6}  ({100 * v / max(total, 1):.1f} %)")
    print(f"\nCompatibles sans durée connue : {nolen} (le serveur utilisera une durée par défaut)")
    con.close()


if __name__ == "__main__":
    main()
