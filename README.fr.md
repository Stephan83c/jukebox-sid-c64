# SID Jukebox pour C64 Ultimate

🇫🇷 Français · [🇬🇧 English](README.md)

Un jukebox en ligne façon *Belote LAN C64* : le **C64 Ultimate** demande un morceau SID au hasard à un
serveur, le reçoit par le réseau de l'Ultimate (UCI/TCP) et le **joue lui-même** (le 6510 exécute le code
du morceau, comme à l'époque). Pas de synchronisation entre les clients : chacun a son tirage.

L'écran de lecture : logo géant, titre / artiste / année, temps écoulé, trois vu-mètres (un par voix du
SID, en dégradé arc-en-ciel), scroller de démo dont le texte vient du serveur, touches.

![Écran de lecture (émulateur VICE)](docs/screenshot.png)

*L'écran de lecture, capturé dans l'émulateur VICE (version démo) : titre arc-en-ciel, vu-mètres, scroller piloté par le serveur, version dans le coin.*

```
 ┌────────────┐   texte, TCP :6474    ┌──────────────────────┐
 │  serveur   │ ◄───────────────────► │  C64 Ultimate        │
 │ server.py  │   RANDOM [motif]      │  c64/ (Oscar64 + 6502)  │
 │ jukebox.db │ ──► OK|…|code brut    │  UCI : sockets TCP   │
 └─────┬──────┘                       └──────────────────────┘
       │ indexer.py
 ┌─────┴──────┐
 │ HVSC (SID) │   ~61 000 fichiers, durées : Songlengths.md5
 └────────────┘
```

## Démarrage rapide

Prérequis : Python 3 (`c64/chargen_set1.bin` seulement pour regénérer le logo et le scroller, voir `dump_chargen.py`), `7z`, **Oscar64** (compilateur C, `make OSC=/chemin/oscar64`) et **cc65** (`ca65`/`ld65`, pour le lecteur), un C64 Ultimate
avec l'API REST et la *Command Interface* activées. VICE est facultatif (tests sans matériel).

```sh
# 1. la HVSC (à télécharger sur https://hvsc.c64.org/) puis l'index des morceaux jouables
python3 indexer.py /chemin/vers/C64Music -o jukebox.db --max-addr 0xAEFF

# 2. le serveur (port 6474)
python3 server.py --root /chemin/vers/C64Music

# 3. le client C64 : adapter SERVEUR_IP et ULTIMATE dans c64/Makefile (ou en ligne de commande)
cd c64
make SERVEUR_IP=boombass.net SERVEUR_PORT=6474 ULTIMATE=192.168.1.27 deploy
```

`--max-addr` doit rester égal à `HISTART - 1` du Makefile (et à `MEM_HAUT` de `main.c`, qui suit `HISTART` tout seul) : c'est la limite
haute des morceaux, le client occupe la mémoire au-dessus.

## Mettre le serveur en ligne

```sh
python3 server.py --root /chemin/vers/C64Music --port 6474      # 0.0.0.0 par défaut
```

- Ouvrir le port TCP dans le pare-feu (`firewall-cmd --add-port=6474/tcp --permanent`) et chez l'hébergeur.
- Sans accès root, un service `systemd --user` convient (`~/.config/systemd/user/jukebox.service`,
  `Restart=on-failure`) ; pour qu'il survive à la fermeture de session et au redémarrage, un administrateur
  doit lancer `sudo loginctl enable-linger <compte>`.
- Mettre à jour la base des morceaux après une nouvelle HVSC : [docs/UPDATE_DB.fr.md](docs/UPDATE_DB.fr.md).
- Mise à jour depuis GitHub : `git pull` dans le dossier du serveur (clé de déploiement en lecture seule
  si le dépôt est privé), puis redémarrer le serveur.

## Texte du scroller

Le texte vient du fichier **`scroll.txt`** à côté de `server.py` (option `--scroll`). Il est relu à chaque
requête : on le modifie sans redémarrer, et le nouveau texte arrive **au morceau suivant** (le C64 ne
contacte pas le serveur pendant la lecture).

- Alphabet : `A-Z 0-9 * . , ! ? - / ' :` (45 glyphes) ; minuscules mises en majuscules, accents retirés, le reste
  devient un espace.
- 150 caractères au plus ; le serveur ajoute 10 espaces avant et après.
- Fichier absent ou vide : le C64 affiche son court texte intégré.

## Touches

| Touche | Effet |
|---|---|
| `SPACE` | morceau suivant |
| `S` | recherche par artiste ou titre : les morceaux suivants sont tirés au hasard parmi les résultats (RETURN valide, RUN/STOP annule, RETURN seul = tout, donc efface la recherche ; rien trouvé : `NO MATCH` puis un morceau au hasard) |
| `L` | boucle on/off : rejoue le même morceau à la fin (le morceau repart quand on la change) |
| `V` | vu-mètres on/off (pris en compte au morceau suivant) |
| `Q` | quitte (retour au BASIC) |

## Le protocole (texte, une commande par ligne)

```
RANDOM [motif]  ->  OK|id|taille|secondes|images/s|sous-morceau|chargement|init|play|titre|auteur|année|scroller\n
                    + <taille> octets de code brut (sans en-tête PSID)
RANDOM2 <fin> [motif]  ->  idem ; <fin> = dernière adresse laissée aux morceaux par le client (HISTART - 1), 4 chiffres
                    hexadécimaux, ex. AEFF : seuls les morceaux qui finissent au plus tard à cette adresse sont
                    proposés (client v1.5+)
GET <id>        ->  idem pour un morceau précis
STATS           ->  STATS|compatibles|total
erreur          ->  ERR|message
```

Les clients antérieurs à la v1.5 envoient `RANDOM` simple : le serveur ne leur propose alors que des morceaux finissant avant `$A700`. Un client v1.5+ face à un serveur sans `RANDOM2` (réponse `ERR|commande inconnue`) repasse en `RANDOM` simple. Le dernier champ est le texte du scroller (voir plus bas). Débogable avec `nc`. Le motif cherche dans l'artiste ou le titre, sans tenir compte de la casse.

## Comment ça marche

- **Tri (`indexer.py`)** : lit l'en-tête de chaque `.sid`, retrouve la durée par le MD5 du fichier dans
  `Songlengths.md5`, et marque `compatible` les morceaux que le lecteur sait jouer : PSID (pas RSID), un
  seul SID, cadencé par l'image (pas par un timer CIA), routine de lecture présente, tient entre
  `$0800` et `HISTART-1`, 16 Ko au plus. Les rejets et leur raison restent en base.
- **Lecteur (`c64/play.s`)** : une interruption raster par image appelle la routine du morceau. Pendant
  la lecture la page zéro appartient au morceau (sauvegardée avant, restaurée après) et le clavier est lu
  directement sur la matrice.
- **Vu-mètres** : les registres du SID sont en écriture seule. Pendant l'appel du morceau, `$D000-$DFFF`
  est mis en RAM ; les écritures vers le SID y tombent, on les copie dans un tampon puis vers la vraie
  puce. À partir du tampon on simule l'enveloppe (ADSR) de chaque voix.
- **Affichage** : écran de lecture en banque VIC 3 (`$F400`, caractères `$F800`, RAM sous le KERNAL),
  avec un jeu de caractères fait pour l'occasion (traits fins des vu-mètres, logo, lettres du scroller).
  Le scroller utilise le scroll matériel `$D016`, limité à ses deux lignes par deux interruptions raster.
- **Carte mémoire** : `$0800-(HISTART-1)` morceau ; `HISTART-$CFFF` client ; `$F400-$FFFF` affichage.
  Le client est presque plein (7 octets de marge dans le BSS à la v1.1) : toute nouvelle fonction se paie
  en mémoire, d'où le texte de secours très court et la conversion du scroller sur place dans l'en-tête.

## Pièges de l'Ultimate (appris à la dure)

- **Ne jamais redéployer / réinitialiser le C64 avec un socket ouvert** : l'interface de commande de
  l'Ultimate peut se bloquer jusqu'à une coupure de courant. Le client ne garde aucun socket ouvert
  pendant la lecture ; pour redéployer, attendre la ligne « déconnexion » dans le journal du serveur.
- Après une erreur de lecture réseau (-1), ne plus écrire ni fermer ce socket.
- La partie C est compilée avec Oscar64 (littéraux ASCII sans conversion ; le lecteur est assemblé à part avec ca65).
  Oscar64 garde ses temporaires en page zéro `$02-$63`, que le lecteur sauvegarde et restaure autour du morceau.
- La RAM sous le KERNAL ne peut pas être relue par le processeur (il voit la ROM) : tout ce qu'on doit
  relire vit dans un tampon ordinaire.
- Changer une couleur du VIC-II en pleine ligne laisse un pixel gris : si on le fait, que ce soit dans
  la bordure.

## Fichiers

| | |
|---|---|
| `indexer.py` | indexe la HVSC dans `jukebox.db` (SQLite) |
| `update_db.sh` | réindexe + envoie + redémarre + teste, avec garde-fous ([doc](docs/UPDATE_DB.fr.md)) |
| `server.py` | serveur asyncio : tirage, recherche, envoi du code brut et du texte du scroller |
| `scroll.txt` | texte du scroller, relu à chaque morceau |
| `client_pc.py` | client de test (PC) ; envoie aussi un SID à l'Ultimate par son API REST |
| `c64/client.c`, `main.c`, `uci.c`, `console.c` | client (Oscar64) : réseau (UCI), interface, recherche ; `console.c` écrit directement en RAM écran |
| `c64/play.s` | lecteur PSID, vu-mètres, scroller, logo |
| `c64/asm.cfg`, `build.sh` | carte mémoire du lecteur et construction en deux passes (chargé en `$0801`, un petit copieur de `client.c` le recopie à `HISTART`) |
| `c64/make_logo.py`, `make_scroll.py` | génèrent `logo.s` et `scroll.s` (données commitées ; alphabet fixe de 45 glyphes) |
| `c64/dump_chargen.py` | extrait la ROM des caractères de VICE pour `make_scroll.py` |
| `c64/make_demo.py` | version démo sans réseau (`make demo`), pour tester dans VICE |

## Licence et droits d'auteur

Le code est publié sous [licence MIT](LICENSE). Les morceaux de la HVSC sont protégés ; leur usage hors écoute privée est soumis au droit d'auteur
(voir `DOCUMENTS/Disclaimer.txt` de la HVSC). Ce dépôt ne contient aucun morceau ni la ROM du C64 ;
le serveur public a été soumis à l'équipe HVSC, qui a répondu le 2026-11-19 : « It's all ok for us, please go on with your
project. » C'est l'avis favorable de l'équipe, pas une licence : les droits restent aux compositeurs.
