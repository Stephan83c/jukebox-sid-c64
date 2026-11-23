#!/usr/bin/env python3
"""Proxy de pannes entre le C64 et le serveur jukebox (SPEC-v2.md §9.3 : serveur figé ou coupé à chaque étape réseau).

    panne.py --ecoute 6464 --serveur 127.0.0.1:6465 --duree 10 --ctrl FICHIER

Chaque connexion lit le mode dans FICHIER (une ligne), puis le remet à « pass » : un mode ne vaut que pour une connexion.
--duree N remplace la durée annoncée des morceaux par N secondes (enchaînement automatique sans toucher au clavier).

Modes :
  pass               relais normal
  ferme_accept       fermeture (FIN) dès l'acceptation
  rst_accept         RST dès l'acceptation
  ferme_cmd          commande lue, fermeture sans réponse
  muet               commande lue, aucune réponse, socket gardé ouvert (délai « première ligne » 10 s)
  entete_fige        25 premiers octets de l'en-tête (sans LF), puis plus rien (délai « données » 5 s)
  entete_ferme       idem puis fermeture
  morceau_fige       en-tête + moitié du morceau, puis plus rien
  morceau_ferme      idem puis fermeture
  morceau_rst        idem puis RST
  relais_fige        en-tête + morceau + moitié du bloc de relais, puis plus rien
  relais_ferme       idem puis fermeture
  get3:ID            la commande du C64 est remplacée par « GET3 ID » (faire jouer un morceau précis)
  lent               tout, par paquets de 200 octets espacés de 4 s (sous le délai de 5 s : doit réussir)
Dans les modes « fige » et « muet », le proxy note ce que le C64 envoie ensuite (QUIT attendu) et quand il ferme.
"""
import argparse
import socket
import struct
import threading
import time
from pathlib import Path

MODES = ("pass ferme_accept rst_accept ferme_cmd muet entete_fige entete_ferme morceau_fige morceau_ferme morceau_rst "
         "relais_fige relais_ferme lent").split()


def log(cid, msg):
    print(f"{time.strftime('%H:%M:%S')} [{cid}] {msg}", flush=True)


def rst(s):
    s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    s.close()


def lire_ligne(s):
    buf = b""
    while not buf.endswith(b"\n"):
        c = s.recv(1)
        if not c:
            break
        buf += c
    return buf


def lire_n(s, n):
    buf = b""
    while len(buf) < n:
        c = s.recv(n - len(buf))
        if not c:
            break
        buf += c
    return buf


def observer(cid, c, t0, limite=60):
    """Après une panne « figée » : ce que le C64 envoie, et quand il ferme."""
    c.settimeout(1)
    recu = b""
    while time.time() - t0 < limite:
        try:
            d = c.recv(256)
        except socket.timeout:
            continue
        except OSError as e:
            log(cid, f"C64 : erreur {e} après {time.time() - t0:.1f} s")
            break
        if not d:
            log(cid, f"C64 a fermé après {time.time() - t0:.1f} s ; reçu {recu!r}")
            c.close()
            return
        recu += d
        log(cid, f"C64 -> {d!r} à {time.time() - t0:.1f} s")
    log(cid, f"C64 n'a PAS fermé en {limite} s ; reçu {recu!r}")
    c.close()


def traiter(cid, c, mode, serveur, duree):
    t0 = time.time()
    log(cid, f"connexion de {c.getpeername()[0]}, mode {mode}")
    if mode == "ferme_accept":
        c.close(); log(cid, "fermé (FIN)"); return
    if mode == "rst_accept":
        rst(c); log(cid, "RST"); return
    cmd = lire_ligne(c)
    log(cid, f"commande {cmd!r}")
    if mode == "ferme_cmd":
        c.close(); log(cid, "fermé sans réponse"); return
    if mode == "muet":
        observer(cid, c, time.time()); return
    if mode.startswith("get3:"):
        cmd = f"GET3 {mode[5:]}\n".encode()
        log(cid, f"commande remplacée par {cmd!r}")
    s = socket.create_connection(serveur)
    s.sendall(cmd)
    entete = lire_ligne(s)
    champs = entete.rstrip(b"\n").split(b"|")
    taille = trelais = 0
    if champs[0] == b"OK3":
        taille, trelais = int(champs[2]), int(champs[10])
        if duree:
            champs[3] = str(duree).encode()
        entete = b"|".join(champs) + b"\n"
    corps = lire_n(s, taille + trelais)
    s.sendall(b"QUIT\n")
    s.close()
    log(cid, f"réponse {champs[0].decode(errors='replace')} id {champs[1].decode(errors='replace') if len(champs) > 1 else '?'} "
             f"morceau {taille} o, relais {trelais} o : {entete[:60]!r}")
    tout = entete + corps
    coupe = {"entete_fige": 25, "entete_ferme": 25,
             "morceau_fige": len(entete) + taille // 2, "morceau_ferme": len(entete) + taille // 2,
             "morceau_rst": len(entete) + taille // 2,
             "relais_fige": len(entete) + taille + trelais // 2, "relais_ferme": len(entete) + taille + trelais // 2}
    if mode in coupe:
        if mode.startswith("relais") and trelais == 0:
            log(cid, "ATTENTION : morceau sans relais, la coupure tombe en fin de morceau")
        n = coupe[mode]
        c.sendall(tout[:n])
        log(cid, f"{n} / {len(tout)} octets envoyés, puis {mode.split('_')[1]}")
        if mode.endswith("_ferme"):
            c.close(); return
        if mode.endswith("_rst"):
            rst(c); return
        observer(cid, c, time.time()); return
    if mode == "lent":
        for i in range(0, len(tout), 200):
            c.sendall(tout[i:i + 200])
            time.sleep(4)
        log(cid, f"{len(tout)} octets envoyés lentement")
    else:
        c.sendall(tout)
    # fin normale : le client envoie QUIT et ferme
    observer(cid, c, time.time(), limite=20)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ecoute", type=int, default=6464)
    ap.add_argument("--serveur", default="127.0.0.1:6465")
    ap.add_argument("--duree", type=int, default=0)
    ap.add_argument("--ctrl", required=True)
    a = ap.parse_args()
    h, p = a.serveur.rsplit(":", 1)
    ctrl = Path(a.ctrl)
    if not ctrl.exists():
        ctrl.write_text("pass\n")
    ls = socket.socket()
    ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ls.bind(("0.0.0.0", a.ecoute))
    ls.listen(8)
    log(0, f"écoute {a.ecoute} -> {a.serveur}, durée {a.duree or 'inchangée'}")
    n = 0
    while True:
        c, _ = ls.accept()
        n += 1
        mode = ctrl.read_text().strip() or "pass"
        if mode not in MODES and not mode.startswith("get3:"):
            log(n, f"mode inconnu {mode!r}, pass")
            mode = "pass"
        ctrl.write_text("pass\n")
        threading.Thread(target=traiter, args=(n, c, mode, (h, int(p)), a.duree), daemon=True).start()


if __name__ == "__main__":
    main()
