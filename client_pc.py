#!/usr/bin/env python3
"""Client de test : demande un morceau au serveur, puis le joue.

    client_pc.py                      # tire un morceau, l'enregistre dans ./recus/
    client_pc.py --pattern Hubbard    # tirage restreint
    client_pc.py --ultimate 192.168.1.27 --play   # envoie le SID à l'Ultimate (API REST)
    client_pc.py --local --play       # le joue avec sidplayfp sur ce PC
"""
import argparse
import re
import socket
import subprocess
import urllib.request
from pathlib import Path


def recv_line(s: socket.socket) -> bytes:
    buf = b""
    while not buf.endswith(b"\n"):
        c = s.recv(1)
        if not c:
            raise ConnectionError("connexion fermée")
        buf += c
    return buf[:-1]


def recv_exact(s: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        c = s.recv(n - len(buf))
        if not c:
            raise ConnectionError("connexion fermée")
        buf += c
    return buf


def fetch(host: str, port: int, pattern: str):
    with socket.create_connection((host, port), timeout=10) as s:
        s.sendall(f"RANDOM {pattern}\n".encode().rstrip() + b"\n")
        head = recv_line(s).decode("latin-1").split("|")
        if head[0] != "OK":
            raise SystemExit(f"Erreur serveur : {head[1:]}")
        # OK|id|taille|secondes|images/s|sous-morceau|chargement|init|play|titre|auteur|année|scroller
        _, tid, size, secs, fps, song, load, init, play, title, author, released, *_ = head
        data = recv_exact(s, int(size))
        s.sendall(b"QUIT\n")
    return dict(id=int(tid), seconds=int(secs), fps=int(fps), song=int(song), title=title,
                author=author, released=released, data=data,
                load=int(load), init=int(init), play=int(play))


def play_on_ultimate(ip: str, tune: dict):
    """POST /v1/runners:sidplay avec le fichier SID en corps (API REST de l'Ultimate)."""
    # l'API attend un vrai fichier SID : on reconstruit un en-tête PSID v2 minimal
    import struct
    hdr = b"PSID" + struct.pack(">HHHHHHHI", 2, 0x7C, 0, tune["init"], tune["play"], tune["song"], tune["song"], 0)
    hdr += tune["title"].encode("latin-1", "replace")[:31].ljust(32, b"\0")
    hdr += tune["author"].encode("latin-1", "replace")[:31].ljust(32, b"\0")
    hdr += tune["released"].encode("latin-1", "replace")[:31].ljust(32, b"\0")
    hdr += struct.pack(">HBBBB", 0, 0, 0, 0, 0)
    body = hdr + struct.pack("<H", tune["load"]) + tune["data"]
    url = f"http://{ip}/v1/runners:sidplay?songnr={tune['song']}"
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, r.read().decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6474)
    ap.add_argument("--pattern", default="")
    ap.add_argument("--ultimate", metavar="IP")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--play", action="store_true")
    ap.add_argument("--out", type=Path, default=Path("recus"))
    a = ap.parse_args()

    t = fetch(a.host, a.port, a.pattern)
    print(f"#{t['id']}  {t['title']}  -  {t['author']}  ({t['released']})  "
          f"{t['seconds'] // 60}:{t['seconds'] % 60:02d}  {len(t['data'])} octets")
    a.out.mkdir(exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", t["title"])[:40] or "morceau"
    f = a.out / f"{t['id']}_{name}.sid"
    f.write_bytes(t["data"])
    print(f"enregistré : {f}  (charge ${t['load']:04X}, init ${t['init']:04X}, play ${t['play']:04X})")

    if a.play and a.ultimate:
        status, body = play_on_ultimate(a.ultimate, t)
        print("Ultimate :", status, body.strip().replace("\n", " "))
    elif a.play and a.local:
        print("--local n'est plus pris en charge : le serveur envoie du code brut, sans en-tête SID")


if __name__ == "__main__":
    main()
