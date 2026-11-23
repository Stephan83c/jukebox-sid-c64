#!/usr/bin/env python3
# SID Jukebox C64
# Copyright (C) 2026 Stephan83c
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version. It is
# distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.
"""Tests de l'étape 2 de SPEC-v2.md : fabrication des relais par le serveur et protocole RANDOM3/GET3.

1. Référence : sidscan --dump fabrique le code modifié et le bloc de relais avec la fonction de sa 2e émulation.
   Sa sortie doit aussi être identique à la table « scan » (sinon la base ne correspond pas à l'outil).
2. Fabrication : server.tune3() doit rendre exactement les mêmes octets, pour chaque morceau servi avec relais ;
   les morceaux sans relais servis doivent partir tels quels (fichier sans en-tête).
3. Protocole : un serveur lancé en local (port libre) répond à GET3, RANDOM3 (avec et sans motif, limites diverses),
   aux commandes v1 et à STATS ; chaque réponse OK3 est relue et contrôlée comme le fera le client (§6.1).

    python3 test_v3.py --root ../hvsc/C64Music [--ids 13636,6301] [--jobs 15]
"""
import argparse
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import server

HERE = Path(__file__).resolve().parent
REG = [13636, 6301, 28342, 31049, 27436, 42363, 24668, 22618, 44694, 3663]   # morceaux de non-régression (§9)
fails = 0


def check(cond, msg):
    global fails
    if not cond:
        fails += 1
        if fails <= 30:
            print("ÉCHEC :", msg)
    return cond


def run_sidscan(sidscan, lines, jobs, dump):
    parts = [p for p in (lines[k::jobs] for k in range(jobs)) if p]
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        procs = []
        for k, part in enumerate(parts):
            fin = Path(tmp) / ("in%d" % k)
            fin.write_text("".join(part))
            with open(fin) as i, open(Path(tmp) / ("out%d" % k), "w") as o:
                procs.append(subprocess.Popen([str(sidscan), "%04X" % server.SCAN_HISTART, str(server.SCAN_CALLS),
                                               "--dump", str(dump)], stdin=i, stdout=o))
        for k, pr in enumerate(procs):
            if pr.wait():
                sys.exit("sidscan a échoué")
            out += (Path(tmp) / ("out%d" % k)).read_text().splitlines()
    return out


def recv_exact(s, n):
    buf = b""
    while len(buf) < n:
        c = s.recv(n - len(buf))
        if not c:
            raise ConnectionError("connexion fermée")
        buf += c
    return buf


def recv_line(s):
    buf = b""
    while not buf.endswith(b"\n"):
        buf += recv_exact(s, 1)
    return buf[:-1].decode("latin-1")


def read_ok3(s, fin):
    """Lit une réponse OK3 et applique les contrôles du client (§6.1). Rend (en-tête, code, bloc) ou None."""
    head = recv_line(s).split("|")
    if head[0] != "OK3":
        return head, None, None
    if not check(len(head) == 16, "OK3 : %d champs" % len(head)):
        return head, None, None
    tid, size, secs, fps, song, load, init, play, rz, rlen, complet = (int(x) for x in head[1:12])
    code = recv_exact(s, size)
    block = recv_exact(s, rlen)
    check(size > 0 and load >= 0x0800 and load + size - 1 <= fin, "%d : morceau hors zone" % tid)
    check(song > 0 and fps in (50, 60) and secs > 0, "%d : champs" % tid)
    check(complet in (0, 1) and rlen <= 32 + 7 * server.MAX_RELAYS, "%d : complet/taille_relais" % tid)
    if rlen:
        check(rz >= 0x0800 and rz + rlen - 1 <= fin and (rz + rlen - 1 < load or rz > load + size - 1),
              "%d : bloc de relais mal placé" % tid)
    else:
        check(rz == 0 and complet == 0, "%d : sans relais mais relais=%d complet=%d" % (tid, rz, complet))
    check(len(head[15]) <= 170, "%d : scroller trop long" % tid)
    return head, code, block


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=HERE / "jukebox.db")
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--sidscan", type=Path, default=HERE / "sidscan")
    ap.add_argument("--jobs", type=int, default=12)
    ap.add_argument("--ids", help="id séparés par des virgules (sinon tous les morceaux servis en v2)")
    a = ap.parse_args()

    jb = server.Jukebox(a.db, a.root)
    if jb.scan_version is None:
        sys.exit("pas d'analyse dans la base pour HISTART $%04X et %d appels" % (server.SCAN_HISTART, server.SCAN_CALLS))
    q = jb.SELECT3
    args = [jb.scan_version, server.SCAN_HISTART, server.SCAN_CALLS]
    if a.ids:
        ids = [int(i) for i in a.ids.split(",")]
        q += " AND t.id IN (%s)" % ",".join("?" * len(ids))
        args += ids
    rows = {r["id"]: r for r in jb.con.execute(q, args)}
    scanrows = {r[0]: r[1:] for r in sqlite3.connect(a.db).execute(
        "SELECT tune_id, verdict, complet, relay_addr, relay_len, nrelais, verif, relais FROM scan"
        " WHERE scan_version=? AND histart=? AND calls=?", args[:3])}
    print("analyse v%d, %d morceaux servis en v2" % (jb.scan_version, len(rows)))

    # 0. protection des clients v1 (D9, §6.2), réintégration known_bad_v2, cohérence de HISTART (§8)
    con = sqlite3.connect(a.db)
    v1_exclus = [r[0] for r in con.execute(
        "SELECT t.id FROM tunes t JOIN scan s ON s.tune_id = t.id AND s.song = t.start_song AND s.scan_version = ?"
        " AND s.histart = ? AND s.calls = ? WHERE t.compatible = 1 AND s.v1_risque > 0 ORDER BY t.id", args[:3])]
    if check(jb.v1_where != "", "colonne v1_risque absente : analyse antérieure à la version 2"):
        check(all(jb.get(i) is None for i in v1_exclus), "GET v1 sert un morceau v1_risque")
        n_v1 = con.execute("SELECT COUNT(*) FROM tunes WHERE compatible = 1").fetchone()[0]
        n_serv = jb.con.execute("SELECT COUNT(*) FROM tunes WHERE compatible = 1" + jb.v1_where, jb.v1_args).fetchone()[0]
        check(n_serv == n_v1 - len(v1_exclus), "tirage v1 : %d servis pour %d - %d" % (n_serv, n_v1, len(v1_exclus)))
        ex = set(v1_exclus)
        check(all(r is not None and r["id"] not in ex for r in (jb.pick(None, 0xAEFF) for _ in range(300))),
              "RANDOM2 tire un morceau refusé aux clients v1")
    kb2 = [r[0] for r in con.execute("SELECT id FROM tunes WHERE reject = 'known_bad_v2'")]
    kb2_ok = [i for i in kb2 if jb.get3(i) is not None]
    check(all(jb.get(i) is None for i in kb2), "known_bad_v2 servi à un client v1")
    hs = {"server.py": server.SCAN_HISTART}
    m = re.search(r'--histart", default="([0-9A-Fa-f]+)"', (HERE / "scan_db.py").read_text())
    hs["scan_db.py"] = int(m.group(1), 16) if m else None
    m = re.search(r"MAX_ADDR=\$\{MAX_ADDR:-0x([0-9A-Fa-f]+)\}", (HERE / "update_db.sh").read_text())
    hs["update_db.sh"] = int(m.group(1), 16) + 1 if m else None
    for mm in (HERE / "c64" / "src" / "memmap.asm", HERE.parent.parent / "SIDBox2_C64" / "src" / "memmap.asm"):
        if mm.exists():
            m = re.search(r"\.const HISTART = \$([0-9A-Fa-f]+)", mm.read_text())
            hs[mm.name] = int(m.group(1), 16) if m else None
            break
    check(len(set(hs.values())) == 1, "HISTART incohérent : %s" % {k: v and "$%04X" % v for k, v in hs.items()})
    print("0. v1 : %d morceaux refusés aux clients v1 (D9) ; known_bad_v2 : %d servis en v2 sur %d ; HISTART $%04X dans %s"
          % (len(v1_exclus), len(kb2_ok), len(kb2), server.SCAN_HISTART, ", ".join(hs)))

    # 1. référence
    with tempfile.TemporaryDirectory() as ref:
        ref = Path(ref)
        t = time.time()
        lines = ["%d|%s|%d|%d\n" % (i, a.root / r["path"], r["start_song"], 60 if r["clock"] == "NTSC" else 50)
                 for i, r in sorted(rows.items())]
        out = run_sidscan(a.sidscan, lines, a.jobs, ref)
        print("1. référence sidscan : %d morceaux en %.0f s" % (len(out), time.time() - t))
        for ln in out:
            f = ln.split("|")
            tid = int(f[0])
            got = (f[2], int(f[4]), int(f[5], 16), int(f[6]), int(f[8]), f[14], f[15])
            check(got == tuple(scanrows[tid]), "%d : sidscan ne redonne pas la ligne de la table scan" % tid)

        # 2. fabrication
        n_rel = n_sans = n_eq = 0
        for tid, r in sorted(rows.items()):
            code, rz, block, complet = server.tune3(jb, r, server.SCAN_HISTART - 1)
            fc, fr = ref / ("%d.code" % tid), ref / ("%d.relay" % tid)
            if r["verif"] == "ok" and r["nrelais"]:
                n_rel += 1
                if check(fc.exists(), "%d : pas de référence" % tid):
                    eq = code == fc.read_bytes() and block == fr.read_bytes()
                    n_eq += eq
                    check(eq, "%d : octets différents de la référence" % tid)
                check(rz == r["relay_addr"] and complet == r["s_complet"], "%d : relais/complet" % tid)
            else:
                n_sans += 1
                raw = server.tune_code(jb.payload(r))
                check(code == raw and rz == 0 and block == b"" and complet == 0, "%d : morceau sans relais modifié" % tid)
        print("2. fabrication : %d avec relais (%d identiques à la référence), %d sans relais" % (n_rel, n_eq, n_sans))

        # 3. protocole (≤ 28 demandes de morceaux : limite de 30 par minute et par IP)
        with socket.socket() as p:
            p.bind(("127.0.0.1", 0))
            port = p.getsockname()[1]
        srv = subprocess.Popen([sys.executable, str(HERE / "server.py"), "--db", str(a.db), "--root", str(a.root),
                                "--host", "127.0.0.1", "--port", str(port)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                try:
                    s = socket.create_connection(("127.0.0.1", port), timeout=10)
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                sys.exit("serveur injoignable")
            with s:
                ids = [i for i in REG if i in rows][:8] or list(rows)[:8]
                for tid in ids:
                    s.sendall(b"GET3 %d\n" % tid)
                    head, code, block = read_ok3(s, server.SCAN_HISTART - 1)
                    if check(code is not None, "GET3 %d : %s" % (tid, head)):
                        fc, fr = ref / ("%d.code" % tid), ref / ("%d.relay" % tid)
                        if fc.exists():
                            check(code == fc.read_bytes() and block == fr.read_bytes(), "GET3 %d : octets" % tid)
                        else:
                            check(code == server.tune_code(jb.payload(rows[tid])) and not block, "GET3 %d : octets" % tid)
                nok = 0
                for fin, pat in (("AEFF", ""), ("AEFF", ""), ("AEFF", ""), ("AEFF", ""), ("AEFF", "hubbard"),
                                 ("AEFF", "galway"), ("9FFF", ""), ("9FFF", ""), ("1FFF", ""), ("0FFF", ""),
                                 ("AEFF", "zzzzqqqq")):
                    s.sendall(("RANDOM3 %s %s\n" % (fin, pat)).encode())
                    head, code, block = read_ok3(s, int(fin, 16))
                    if pat == "zzzzqqqq":
                        check(head == ["ERR", "aucun morceau"], "RANDOM3 motif absent : %s" % head)
                    elif check(code is not None, "RANDOM3 %s %s : %s" % (fin, pat, head)):
                        nok += 1
                        if pat:
                            check(pat in (head[12] + " " + head[13]).lower(), "RANDOM3 motif %s : %s" % (pat, head[12:14]))
                for bad in ("RANDOM3", "RANDOM3 08FF", "RANDOM3 XYZW", "GET3 999999"):
                    s.sendall(bad.encode() + b"\n")
                    head = recv_line(s).split("|")
                    check(head[0] == "ERR", "%s : %s" % (bad, head))
                s.sendall(b"RANDOM2 AEFF\n")
                head = recv_line(s).split("|")
                if check(head[0] == "OK" and len(head) == 13, "RANDOM2 : %s" % head[:3]):
                    recv_exact(s, int(head[2]))
                for tid in v1_exclus[:3]:          # D9 : un morceau à risque pour les clients v1 leur est refusé
                    s.sendall(b"GET %d\n" % tid)
                    head = recv_line(s).split("|")
                    check(head[0] == "ERR", "GET %d (v1_risque) : %s" % (tid, head[:3]))
                s.sendall(b"STATS\n")
                head = recv_line(s).split("|")
                check(head[0] == "STATS" and len(head) == 3, "STATS : %s" % head)
                s.sendall(b"QUIT\n")
            print("3. protocole : %d GET3, %d RANDOM3 servis, erreurs et commandes v1 contrôlées" % (len(ids), nok))
        finally:
            srv.terminate()
            srv.wait()

    print("RÉSULTAT :", "OK" if not fails else "%d échec(s)" % fails)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
