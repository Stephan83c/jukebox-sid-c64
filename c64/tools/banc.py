#!/usr/bin/env python3
"""Banc VICE automatique, sans réseau (SPEC-v2.md §9.2) : le vrai lecteur v2.0, un morceau chargé par le moniteur distant.

Pour chaque morceau, trois passages dans VICE :
  R : morceau modifié + bloc de relais, tel que le sert RANDOM3 (fabrication de server.tune3), machine de la norme du morceau ;
  D : morceau d'origine, sans relais (lecture directe), même norme ;
  X : comme R, sur une machine de l'AUTRE norme : vitesse (le morceau appelé à sa cadence : 6 images pour 5 appels ou 5 pour 6)
      et hauteur (après chaque appel, les 6 registres de fréquence réécrits avec la correction de la v1.9 si complet = 1).
Contrôles : le lecteur rend la main à la durée prévue (temps écoulé = durée), le KERNAL tourne ensuite (horloge $A0-$A2),
l'état §7.2 est identique avant et après (page zéro, pages 2-3, VIC, CIA, pile, $01), et la suite des écritures au SID
(pilote son « dump » de VICE : registre, valeur, dans l'ordre) est la même en R, en D et en X (corrections retirées).

    tools/banc.py [--secs 30] [ID ...]      (sans ID : morceaux de non-régression du §9.2)
"""
import argparse
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
J = Path(os.environ.get("JUKEBOX", str(Path(__file__).resolve().parents[2])))
H = Path(os.environ.get("HVSC", str(Path(__file__).resolve().parents[3] / "hvsc" / "C64Music")))
sys.path.insert(0, str(J))
import server  # noqa: E402

REG = [13636, 6301, 28342, 31049, 27436, 42363, 24668, 22618, 44694, 3663]
PRG = ROOT / "build" / "demo.prg"
# variables que l'IRQ du KERNAL change d'elle-même (horloge, clavier, curseur) : ignorées dans la comparaison
KERNAL_IRQ = {0xA0, 0xA1, 0xA2, 0x91, 0xC5, 0xCB, 0xCC, 0xCD, 0xCE, 0xCF, 0xF5, 0xF6, 0x0287, 0x028D, 0x028E}


def symbols():
    txt = (ROOT / "build" / "demo.sym").read_text()
    return {m[0]: int(m[1], 16) for m in re.findall(r"^\.label (\w+)=\$([0-9a-fA-F]+)", txt, re.M)}


class Vice:
    def __init__(self, ntsc, dump, port):
        self.p = subprocess.Popen(["x64sc", "-default", "-ntsc" if ntsc else "-pal", "-warp", "-sound", "-sounddev", "dump",
                                   "-soundarg", str(dump), "-remotemonitor", "-remotemonitoraddress", "127.0.0.1:%d" % port],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                self.s = socket.create_connection(("127.0.0.1", port), timeout=5)
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("moniteur VICE injoignable")

    def cmd(self, c, w=0.15):
        self.s.sendall((c + "\n").encode())
        time.sleep(w)
        out = b""
        self.s.settimeout(0.3)
        try:
            while True:
                b = self.s.recv(65536)
                if not b:
                    break
                out += b
        except socket.timeout:
            pass
        return out.decode("latin-1")

    def mem(self, a, n):
        v = []
        for line in self.cmd("m %04x %04x" % (a, a + n - 1), 0.3).splitlines():
            m = re.search(r">C:([0-9a-f]{4})  (.*)", line)   # 16 octets en 4 groupes, puis 3 espaces et l'ASCII
            if m:
                v += [int(x, 16) for x in m.group(2).split("   ")[0].split()]
        if len(v) < n:
            raise RuntimeError("lecture mémoire incomplète en %04X" % a)
        return v[:n]

    def poke(self, a, bs):
        for k in range(0, len(bs), 32):
            self.cmd("> %04x " % (a + k) + " ".join("%02x" % b for b in bs[k:k + 32]), 0.05)

    def regs(self):
        out = self.cmd("r", 0.2)
        m = re.search(r"\.;([0-9a-f]{4}) ([0-9a-f]{2}) ([0-9a-f]{2}) ([0-9a-f]{2}) ([0-9a-f]{2})", out)
        return dict(pc=int(m[1], 16), a=int(m[2], 16), x=int(m[3], 16), y=int(m[4], 16), sp=int(m[5], 16)) if m else {}

    def go(self):
        self.s.sendall(b"x\n")
        time.sleep(0.1)

    def quit(self):
        try:
            self.s.sendall(b"quit\n")
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


def sp_loop(v, sym):
    """Pointeur de pile relevé quand le processeur est dans une boucle d'attente du banc (jmp *), pas au milieu d'une IRQ
    du KERNAL (qui empile 6 octets)."""
    loops = {sym["bench_wait"]}
    loops |= {a for a in range(sym["bench"], sym["bench_ret"])}
    for _ in range(40):
        r = v.regs()
        if r.get("pc") in loops:
            return r["sp"]
        v.go()
        time.sleep(0.05)
    return None


def state(v):
    """État §7.2 lisible sans effet de bord (pas de lecture des ICR des CIA)."""
    st = {}
    mem = v.mem(0x0002, 0x3FE)
    for k, b in enumerate(mem):
        st[0x0002 + k] = b
    io = v.mem(0xD000, 0x30)
    for r, mask in ((0x11, 0x7F), (0x15, 0xFF), (0x16, 0xFF), (0x18, 0xFF), (0x1A, 0x0F), (0x20, 0x0F), (0x21, 0x0F)):
        st["VIC $D0%02X" % r] = io[r] & mask
    c1 = v.mem(0xDC00, 0x10)
    c2 = v.mem(0xDD00, 0x10)
    st["CIA1 DDRA"], st["CIA1 DDRB"], st["CIA1 CRA"], st["CIA1 CRB"] = c1[2], c1[3], c1[14] & 0xEF, c1[15] & 0xEF
    st["CIA2 PRA&3"], st["CIA2 DDRA"], st["CIA2 CRA"], st["CIA2 CRB"] = c2[0] & 3, c2[2], c2[14] & 0xEF, c2[15] & 0xEF
    st["$01"] = v.mem(0x0001, 1)[0]
    return st


def sid_writes(dump):
    w = []
    for line in Path(dump).read_text().splitlines():
        f = line.split()
        if len(f) == 3 and f[0].isdigit():
            w.append((int(f[1]), int(f[2])))
    return w


def fixpitch(v, up):
    """Correction de hauteur du lecteur (v1.9, §7.6) : v ± (v + v/4)/32, plafonnée à $FFFF."""
    d = (v + (v >> 2)) >> 5
    return min(v + d, 0xFFFF) if up else v - d


def strip_fix(ws, up):
    """Retire de la suite des écritures SID les réécritures de fréquence du lecteur (6 écritures $D400/01/07/08/0E/0F
    dont les valeurs sont la correction des dernières valeurs écrites par le morceau). Rend (écritures du morceau, nombre)."""
    regs = [0] * 32
    out, nfix, i = [], 0, 0
    while i < len(ws):
        blk = ws[i:i + 6]
        if [r for r, _ in blk] == [0, 1, 7, 8, 14, 15]:
            exp = []
            for b in (0, 7, 14):
                w = fixpitch(regs[b] | regs[b + 1] << 8, up)
                exp += [w & 255, w >> 8]
            if [x for _, x in blk] == exp:
                nfix += 1
                i += 6
                continue
        r, x = ws[i]
        regs[r & 31] = x
        out.append(ws[i])
        i += 1
    return out, nfix


def passage(tid, row, relays, secs, sym, tmp, port, cross=False, synth=None):
    """cross : machine de l'autre norme que le morceau (vitesse et hauteur corrigées par le lecteur).
    synth : (chargement, octets) d'un morceau artificiel (test du garde-fou) à la place du morceau de la base."""
    if synth:
        row = dict(load_addr=synth[0], init_addr=synth[0], play_addr=synth[0] + 3, clock="PAL", start_song=1)
        raw = synth[1]
    else:
        raw = server.tune_code(server.Jukebox.payload(JB, row))
    if relays:
        code, rz, block, complet = server.tune3(JB, row, server.SCAN_HISTART - 1)
    else:
        code, rz, block, complet = raw, 0, b"", 0
    load = row["load_addr"]
    fps = 60 if row["clock"] == "NTSC" else 50
    tag = "%d%d%d" % (tid, relays, cross)
    ft, fr, dump = tmp / ("t%s.prg" % tag), tmp / ("r%s.prg" % tag), tmp / ("d%s.txt" % tag)
    ft.write_bytes(bytes((load & 255, load >> 8)) + code)
    fr.write_bytes(bytes((rz & 255, rz >> 8)) + block)
    v = Vice((fps == 60) != cross, dump, port)
    res = {"rz": rz, "complet": complet}
    try:
        time.sleep(2.5)                                   # démarrage du KERNAL (en accéléré)
        v.cmd('l "%s" 0' % PRG, 1.0)
        v.cmd("g %04x" % sym["bench_setup"], 0.1)
        time.sleep(0.5)
        v.cmd('l "%s" 0' % ft, 0.5)
        if block:
            v.cmd('l "%s" 0' % fr, 0.3)
        fmax = secs * fps
        p = [row["init_addr"] & 255, row["init_addr"] >> 8, row["play_addr"] & 255, row["play_addr"] >> 8]
        v.poke(sym["_init_addr"], p)
        v.poke(sym["_frames_max"], [fmax & 255, fmax >> 8])
        v.poke(sym["_song_nr"], [row["start_song"]])
        v.poke(sym["_fps"], [fps])
        v.poke(sym["_vis_on"], [1])
        v.poke(sym["_scr_ok"], [0])
        v.poke(sym["_relay"], [rz & 255, rz >> 8])
        v.poke(sym["_complet"], [complet])
        v.poke(sym["bench_done"], [0, ])
        # état volatil du KERNAL au repos (horloge, clavier, curseur) : deux relevés à 1 s d'écart
        a = state(v)
        v.go()
        time.sleep(1.0)
        b = state(v)
        volatile = {k for k in a if a[k] != b[k]} | KERNAL_IRQ
        before = b
        sp0 = sp_loop(v, sym)
        volatile |= set(range(0x0100, 0x0101 + sp0))      # pile libre (sous le pointeur) : pas de l'état
        v.cmd("r pc=%04x" % sym["bench"], 0.1)
        v.go()
        t0 = time.time()
        done = 0
        while time.time() - t0 < secs + 60:
            time.sleep(1.0)
            done = v.mem(sym["bench_done"], 1)[0]
            v.go()
            if done:
                break
        res["done"] = done
        res["wall"] = time.time() - t0
        time.sleep(0.3)
        after = state(v)
        res["ret"] = v.mem(sym["bench_ret"], 1)[0]
        tf = v.mem(sym["tframes"], 2)
        res["tframes"] = tf[0] | tf[1] << 8
        res["fmax"] = fmax
        fr_ = v.mem(sym["frames"], 2)
        res["frames"] = fr_[0] | fr_[1] << 8
        res["mfps"] = v.mem(sym["mfps"], 1)[0]
        res["port_init"], res["port_play"] = v.mem(sym["port_init"], 2)
        res["sp"] = (sp0, sp_loop(v, sym))
        j1 = v.mem(0x00A0, 3)
        v.go()
        time.sleep(0.5)
        j2 = v.mem(0x00A0, 3)
        res["kernal"] = j1 != j2
        res["block"] = v.mem(rz, len(block)) if block else []
        res["diff"] = {k: (before[k], after[k]) for k in before if k not in volatile and before[k] != after[k]}
        res["volatile"] = len(volatile)
    finally:
        v.quit()
    res["sid"] = sid_writes(dump)
    return res


def main():
    global JB
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", type=int)
    ap.add_argument("--secs", type=int, default=30, help="durée jouée (secondes du morceau)")
    ap.add_argument("--port", type=int, default=6510)
    ap.add_argument("--garde-fou", action="store_true", help="teste seulement le garde-fou (§7.8) : init puis play sans fin")
    a = ap.parse_args()
    JB = server.Jukebox(J / "jukebox.db", H)
    sym = symbols()
    fails = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if a.garde_fou:
            # $1000 init, $1003 play : « JMP * » à l'endroit testé, RTS ailleurs ; le morceau écrit au SID avant de boucler
            for name, code in (("init sans fin", bytes.fromhex("4c0010" "60eaea")),
                               ("play sans fin", bytes.fromhex("60eaea" "a90f8d18d44c0810"))):
                x = passage(0, None, 0, 10, sym, tmp, a.port, synth=(0x1000, code))
                ok = x["done"] and x["ret"] == 6 and x["kernal"] and not x["diff"] and x["sp"][0] == x["sp"][1]
                fails += not ok
                print("garde-fou, %s : retour %s, appels %d, KERNAL %s, état %s, pile %s  %s" % (
                    name, x.get("ret"), x.get("tframes", -1), "vivant" if x.get("kernal") else "figé",
                    "identique" if not x.get("diff") else x["diff"], x.get("sp"), "OK" if ok else "ÉCHEC"))
            print("RÉSULTAT :", "OK" if not fails else "%d échec(s)" % fails)
            sys.exit(1 if fails else 0)
        for tid in a.ids or REG:
            row = JB.get3(tid)
            if row is None:            # écarté à la main (known_bad) mais accepté par l'analyse : testé quand même
                row = JB.con.execute(JB.SELECT3.replace("t.compatible = 1 AND ", "") + " AND t.id = ?",
                                     (JB.scan_version, server.SCAN_HISTART, server.SCAN_CALLS, tid)).fetchone()
                if row is not None:
                    print("%5d  (écarté à la main, accepté par l'analyse : testé)" % tid)
            if row is None:
                print("%5d  refusé par l'analyse (non servi en v2) : ignoré" % tid)
                continue
            r = passage(tid, row, 1, a.secs, sym, tmp, a.port)
            d = passage(tid, row, 0, a.secs, sym, tmp, a.port)
            x = passage(tid, row, 1, a.secs, sym, tmp, a.port, cross=True)
            fps = 60 if row["clock"] == "NTSC" else 50
            pb = []
            for name, x_ in (("R", r), ("D", d), ("X", x)):
                if x_["done"] and x_["mfps"] != (fps if name != "X" else 110 - fps):
                    pb.append("%s: norme de la machine mesurée %d" % (name, x_["mfps"]))
            # X : vitesse (appels du morceau à sa cadence) et hauteur (réécritures corrigées après chaque appel)
            if x["done"]:
                if abs(x["frames"] * fps - x["tframes"] * x["mfps"]) > 2 * x["mfps"]:
                    pb.append("X: vitesse fausse (%d images pour %d appels)" % (x["frames"], x["tframes"]))
                xs, nfix = strip_fix(x["sid"], fps == 60)
                want = x["tframes"] + 1 if r["complet"] else 0          # après init et après chaque appel de play
                if nfix != want:
                    pb.append("X: %d corrections de hauteur au lieu de %d" % (nfix, want))
                if xs != r["sid"]:
                    pb.append("X: écritures du morceau différentes de R")
            for name, x in (("R", r), ("D", d), ("X", x)):
                if not x["done"]:
                    pb.append("%s: pas de retour" % name)
                    continue
                if x["ret"] != 0 or x["tframes"] != x["fmax"]:
                    pb.append("%s: retour %d, %d appels sur %d" % (name, x["ret"], x["tframes"], x["fmax"]))
                if not x["kernal"]:
                    pb.append("%s: KERNAL figé après le retour" % name)
                if x["sp"][0] != x["sp"][1]:
                    pb.append("%s: pile %s" % (name, x["sp"]))
                if x["diff"]:
                    pb.append("%s: état modifié %s" % (name, ", ".join(
                        "%s %02X>%02X" % ("$%04X" % k if isinstance(k, int) else k, *x["diff"][k]) for k in list(x["diff"])[:8])))
            same = r["sid"] == d["sid"]
            if not same:
                n = next((k for k, (p, q) in enumerate(zip(r["sid"], d["sid"])) if p != q), min(len(r["sid"]), len(d["sid"])))
                pb.append("écritures SID différentes à la n° %d (R %d, D %d écritures)" % (n, len(r["sid"]), len(d["sid"])))
            fails += bool(pb)
            print("%5d  %-24.24s %d Hz, relais $%04X complet %d, %d écritures SID, $01 %02X/%02X, autre norme %d/%d images/appels  %s" % (
                tid, row["title"], fps, r["rz"], r["complet"], len(r["sid"]), r["port_init"], r["port_play"],
                x["frames"], x["tframes"], "OK" if not pb else "ÉCHEC : " + " ; ".join(pb)))
    print("RÉSULTAT :", "OK" if not fails else "%d morceau(x) en échec" % fails)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
