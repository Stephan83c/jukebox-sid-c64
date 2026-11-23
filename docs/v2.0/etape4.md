# Étape 4 de SPEC-v2.md : client réseau (2026-11-22)

**Fait** : client v2.0 complet en Kick Assembler (`src/main.asm` chargeur, `net.asm`, `client.asm`), portage de main.c/uci.c/console.c
de la v1.9 (mêmes écrans, textes, couleurs, touches), protocole `RANDOM3` (§6.1, contrôles de l'en-tête compris).

- **Carte mémoire** : `memmap.asm` (une seule valeur, `HISTART = $AF00` provisoire) ; variables du client en `HISTART`, code à la
  suite jusqu'à `$BFE4` (27 octets libres) ; lecteur `$C000-$CFA7`. Le chargeur met les variables à zéro AVANT de copier le code.
- **D4, horloge des délais** : timers A et B du CIA 2 enchaînés (65 536 cycles par unité, environ 15 par seconde), sans IRQ.
  Délais : ouverture 30 s, commande 3 s, repos 2 s, première ligne 10 s, données 5 s sans octet.
- **D6, garde-fou** : NMI du CIA 2 armée pendant chaque appel du morceau (init 3 s, play 0,53 s) ; morceau abandonné, état restauré,
  `TUNE n STUCK, SKIPPED`. Testé dans VICE (`tools/banc.py --garde-fou`).
- **Rejouer (L, V)** : le morceau est redemandé par `GET3 <id>` (copie intacte) : rejoué depuis la mémoire, un morceau qui modifie ses
  propres données sonnait autrement (constaté par l'utilisateur, défaut déjà présent en v1.9).
- Serveur sans `RANDOM3` : `SERVER WITHOUT V2.0, RETRYING...`.

## Tests sur le C64 Ultimate (serveur local, port 6464)

Connexion, `RANDOM3`, réception de l'en-tête, du morceau et du bloc de relais, socket fermé avant la lecture (UCI au repos) ;
cadence 50,12 appels/s (fréquence d'image PAL exacte) ; durée juste (236 s joués en 235,5 s entre deux connexions) ; enchaînement
automatique. Touches testées à la main par l'utilisateur : tout marche, son identique avec et sans V.
Contrôles de l'en-tête : 12 cas dans VICE (`analyser` appelé seul).

Bugs trouvés sur le matériel (voir `BaseC64/bugs.md`) : variables non mises à zéro puis effacement du code par la mise à zéro ;
comparaison 16 bits inversée (tous les en-têtes refusés).

## Pannes du serveur à chaque étape réseau (§9.3), 2026-11-23 : tout passe

`tools/panne.py` entre le C64U et le serveur local (`server.py --host 127.0.0.1 --port 6465`, proxy sur 6464, `--duree 10`).
Une panne par connexion ; à chaque fois : `FAILED, RETRYING...`, UCI au repos (`00 c9`), connexion suivante normale.

| Panne | Réaction du client |
|---|---|
| serveur arrêté (connexion refusée) | `FAILED` aussitôt, nouvel essai toutes les 3 s, reprise au retour du serveur |
| SYN ignoré (file `listen` saturée) | `CONNECTING...` 18 s (l'Ultimate abandonne seul, < 30 s), puis `FAILED` |
| FIN ou RST dès l'acceptation | `FAILED` aussitôt |
| commande lue, fermeture sans réponse | `FAILED` aussitôt |
| serveur muet après la commande | `QUIT` + fermeture à 10,0 s (délai première ligne) |
| en-tête coupé (25 octets) puis figé / fermé | `QUIT` à 5,0 s / `FAILED` aussitôt |
| moitié du morceau puis figé / FIN / RST | `QUIT` à 5,2 s / aussitôt / aussitôt |
| moitié du bloc de relais puis figé / fermé | `QUIT` à 5,3 s / aussitôt |
| envoi lent (200 octets toutes les 4 s, 168 s) | réussi, morceau joué (délai de 5 s compté depuis le dernier octet) |

Aucun morceau incomplet n'est joué. Non testé : la même chose par `GET3` (touches L/V, à la main) ; le code après l'envoi de la
commande est commun aux deux.
*Bingo* (22308), sur lequel la v1.9 s'est figée au démarrage le 2026-11-23 (RAM sauvée dans
`SidJukebox_C64/sauvegardes/gel-v1.9-bingo-2026-11-23.bin`), se joue normalement en v2.0 (`get3:22308` du proxy).

## Endurance (§9.3), 2026-11-23 : 100 morceaux enchaînés sans intervention, aucun échec

Même banc, `panne.py --duree 15` (durées raccourcies à 15 s, décision de l'utilisateur pour le temps), de 21:03 à 21:32 :
100 morceaux complets d'affilée, aucun `FAILED`, aucun morceau abandonné, chaque morceau joué 15 s. Les 2 « anomalies » du suivi
sont un défaut du script de suivi (titre avec apostrophe non reconnu, donc deux morceaux comptés comme un seul de 31 s).
État relu ensuite par l'API REST : UCI au repos (`00 c9`), compteur d'images qui avance. La lecture longue a été vérifiée à part
(236 s joués en 235,5 s, 2026-11-22).

## NTSC sur le matériel (§7.6, §9.3), 2026-11-23 : conforme

Chaque morceau joué 30 s en PAL puis en NTSC (`System Mode` par l'API REST, sans redémarrer ; `GET3` imposé par `panne.py`),
capture HDMI 25 s (`hw:3,0`), rapport de hauteur par corrélation des spectres en échelle log, vitesse par corrélation d'enveloppe.

| id | Morceau | Cadence | Hauteur NTSC/PAL | Vitesse NTSC/PAL |
|---|---|---|---|---|
| 45902 | Kupa Music | 50 Hz | 1,002 (0,99) | 1,005 (0,85) |
| 42363 | Cyberworm | 50 Hz | 1,001 (1,00) | 1,005 (0,84) |
| 114 | Axel F | 60 Hz | 1,002 (0,99) | 1,005 (0,90) |
| 4102 | Project Firestart | 60 Hz | 1,004 (0,97) | 0,995 (0,81) |
| 71 | Airwolf (lit `$02A6`) | 50 Hz | 0,999 (1,00) | 1,005 (0,74) |

Hauteur corrigée dans les deux sens (1,038 sans correction) ; *Airwolf* n'est pas corrigé deux fois (`$02A6` mis à la norme du
morceau). Vitesse 1,005 = écart connu NTSC/PAL de l'Ultimate (preuve que la bascule a bien eu lieu). Résultats identiques à la v1.9.
`System Mode` remis à PAL (vérifié).

**Reste** : vérifier à l'oreille que les relances par `GET3` sonnent comme
la première lecture.
