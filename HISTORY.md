# Historique du projet

Construit le 18 novembre 2026, d'une conversation à l'autre, sur un C64 Ultimate (firmware 1.1.0) et un PC
Linux. Ce fichier raconte comment on est arrivé là, y compris les impasses ; `git log` donne le détail
des versions.

## Départ

L'idée : un jukebox SID en ligne dans l'esprit de *Belote LAN C64* (serveur Python asyncio, client C64,
réseau par l'UCI de l'Ultimate). Contrainte retenue : pas de synchronisation, un tirage aléatoire par client.

## Étapes

1. **Les morceaux** : la HVSC #85 (61 157 fichiers `.sid`, 81 Mo compressés) et ses durées
   (`Songlengths.md5`). Un SID est du code 6502 : le C64 le joue tel quel, rien à décoder.
2. **Tri** (`indexer.py`) : en-têtes PSID/RSID, rejet des morceaux injouables par notre lecteur.
   Premier tri : 54 841 retenus ; il a baissé à chaque contrainte ajoutée (voir plus bas).
3. **Serveur + client PC** : protocole texte `RANDOM`/`GET`. Premier test sur le matériel avec l'API REST
   de l'Ultimate (`runners:sidplay`) : le serveur et le tri étaient bons, sans client C64.
4. **Client C64** (cc65 + assembleur), à partir du `uci.c` de *Belote LAN C64*. Premiers pièges :
   la ROM du BASIC visible au moment du saut en `$Bxxx` ; le saut de ligne envoyé comme un retour chariot ;
   les littéraux convertis par cc65 (`'|'`, `'a'`) ; la RAM sous le KERNAL qu'on ne peut pas relire.
   Règle de sûreté retenue après lecture des notes d'un autre projet : aucun socket ouvert pendant la lecture.
5. **Temps écoulé** (mis à jour par le lecteur, une fois par seconde) et **recherche** par artiste/titre
   (touche S ; le serveur filtre, les jokers SQL sont neutralisés).
6. **Effets** : capter les écritures vers le SID (E/S en RAM pendant l'appel du morceau), simuler l'ADSR.
   Plusieurs versions successives, jugées trop laides ou trop grosses, puis simplifiées :
   spectre + vu-mètres verticaux, puis vu-mètres horizontaux, puis traits fins au pixel près avec un jeu
   de caractères personnalisé en banque VIC 3.
7. **Thème** : logo géant (lettres 16×16 faites avec une police grasse), couleurs arc-en-ciel qui défilent.
   Un fond dégradé par barres raster a été essayé puis retiré (jugé laid) ; un défaut instructif au
   passage : les changements de couleur en pleine ligne laissent un pixel gris sur le VIC-II.
8. **Scroller de démo** : scroll matériel `$D016` limité à sa ligne par deux interruptions raster, lettres
   de 12 pixels (la police du C64 étirée), le nom de l'auteur dedans.
9. **NTSC** : essayé sur l'Ultimate réglé en NTSC (réglage `System Mode`, par l'API REST, puis remis en PAL).
   Le client a continué de jouer pendant le changement de mode et l'interruption raster tournait bien à
   60 images/s. Défaut trouvé et corrigé : la durée était comptée avec la cadence de la machine ; le
   serveur envoie maintenant la cadence du morceau (50 ou 60, d'après l'horloge de son en-tête) et le
   client compte les images avec elle. Reste vrai, et normal : un morceau PAL joué sur une machine NTSC
   va environ 20 % plus vite et un peu plus aigu, comme sur un vrai C64. Non vérifié : l'aspect de
   l'écran en NTSC (je ne vois pas l'écran) et l'oreille.
10. **Mise en page** : texte à gauche, blocs répartis sur les 25 lignes, ligne des touches sur les 40
   colonnes.

11. **Serveur public** (v1.1) : le serveur tourne sur un VPS (`boombass.net:6474`), client réglé sur ce nom.
   Pas de root sur la machine : processus détaché en attendant que l'administrateur active `linger` pour un
   service `systemd --user`, comme le serveur de belote qui y tourne déjà. Le dépôt GitHub (privé à l'époque, public depuis le
   2026-11-18) est cloné sur le serveur avec une clé de déploiement en lecture seule.
12. **Vu-mètres en arc-en-ciel** : dégradé fixe sur les 32 cases (rouge à violet, jamais de noir).
13. **Texte du scroller fourni par le serveur** (`scroll.txt`, relu à chaque morceau, alphabet fixe de
   32 glyphes, 150 caractères). Le client était plein (le premier essai dépassait de 680 octets) : texte de
   secours ramené de 423 à 72 colonnes, texte du serveur converti sur place dans le tampon d'en-tête.
   Marge restante : 7 octets.

## v1.6 : SEARCH, adresse sans port, port 6475 fermé (2026-11-20)

- **S=FIND devient S=SEARCH.** Une remarque sur Reddit : « FIND » laisse croire qu'on obtient une liste de morceaux, alors que
  la touche *filtre le tirage aléatoire* (les morceaux suivants sont tirés au hasard parmi ceux dont l'artiste ou le titre
  contient le texte). Libellé corrigé sur la page web (aide en français et en anglais, avec cette précision) et dans le client.
  La ligne d'état `FILTER:` devient `SEARCH:` (même largeur). `SEARCH` est plus long que `FIND` : la ligne des touches passe à
  un seul espace entre les groupes et commence à la colonne 1 (37 colonnes ; avec deux espaces elle en ferait 41 sur 40).
- **Recherche sans résultat plus lisible.** Avant : un message rouge de 2 s, puis `SEARCH: ALL` sans explication (testé avec
  « momo » : le seul morceau correspondant est marqué incompatible, donc jamais proposé). Maintenant : `NO MATCH: <texte>` en
  rouge et `PLAYING ANY TUNE INSTEAD` pendant environ 5 s, puis `SEARCH: ALL (NO MATCH)` sur le morceau suivant (+112 octets,
  client à 8 425 octets, image `$AF00-$CEE8`). Vérifié sur l'Ultimate le 2026-11-20 (recherches « momo » : sans résultat, et « hubbard » : avec résultat) ; non testable en VICE, la version démo n'ayant pas de réseau.
- **Page web sans numéro de port** : `https://sidbox.boombass.net` (alias DNS vers le VPS + Caddy en reverse proxy, certificat
  Let's Encrypt renouvelé seul). Le jukebox TCP (6474) ne change pas. Détails dans `BaseC64/fiches/reseau-protocole.md`.
- **Port 6475 fermé de l'extérieur** : `web.py --host 127.0.0.1 --trust-proxy` (l'IP des visiteurs vient de `X-Forwarded-For`,
  ajouté par Caddy ; sans cela tous auraient l'IP `127.0.0.1` et la pause par IP jouerait contre tout le monde), et le port est
  retiré de `firewalld`. L'ancienne adresse `http://boombass.net:6475` ne répond plus ; `deploy/jukeweb.service` est à jour.
- **Textes du scroller** : adresse `HTTPS://SIDBOX.BOOMBASS.NET` et `V1.6 IS AVAILABLE`, sur le serveur (`scroll.txt`) et dans le
  texte de secours du client (l'ancienne adresse n'aurait plus fonctionné).
- Constaté en passant : `web.py` ne répond qu'à `GET` (un `HEAD` renvoie 501) ; sans effet pour un navigateur.
- Premiers utilisateurs extérieurs le 2026-11-20 : 3 adresses IP distinctes en trois jours dans le journal du service, dont deux
  autres que celle du développeur (47 connexions).

## Le catalogue selon la place prise par le client

Plus le client est gros, plus il monte dans la mémoire et moins il reste de place pour les morceaux.

| Début du client (`HISTART`) | Morceaux jouables | Ce qui l'a fait grossir |
|---|---|---|
| `$C000` | 45 137 | première version |
| `$B000` | 44 859 | temps écoulé, recherche, effets |
| `$AF00` | 44 811 | logo et jeu de caractères |
| `$AC00` | 44 671 | scroller 8 pixels |
| `$A900` | 44 555 | scroller 12 pixels |
| `$A700` | 44 503 | 13 glyphes de plus au scroller (`/` `'` `:` `0-9`) |
| `$AF00` | 44 703 | v1.5 : client réécrit avec Oscar64 (titre et scroller agrandis, version) ; ajout au tri des 108 « unpacker » (rejetés) |

Motifs de rejet (version actuelle) : plage mémoire incompatible, morceaux cadencés par un timer CIA,
RSID, trop gros (> 16 Ko), multi-SID, sans routine de lecture, **décompresseur au démarrage** (voir plus bas).

## Impasses et leçons

- Le moniteur à distance de VICE a servi à trouver trois bugs (un `BRK` dans un mauvais rip de la HVSC,
  une adresse relue sous la ROM, des instructions modifiées en cours de route) ; sans lui, on aurait tâtonné.
- Un morceau de démo qui plante n'est pas forcément la faute du lecteur : *Thrust* (HVSC) a un en-tête
  qui ne correspond pas à son code.
- **Des morceaux se décompressent dans la mémoire du client.** 108 « worktunes » de `Blues_Muz` (Gallefoss, Røstøen…) ont une
  `init` qui est un décompresseur : elle lit ses données à la fin du fichier et les décompresse en descendant depuis `$CFFF`,
  donc par-dessus le client ($A700-$CFFF). Le client est écrasé, le processeur exécute des données et le C64 se fige avant
  l'affichage du lecteur (écran d'info resté en mode texte, `D018=$15`). Trouvé le 2026-11-18 en reproduisant dans VICE
  (*Piano - 25W05*), en suivant l'init pas à pas puis en lisant les pointeurs de copie `$AE/$FB`. L'indexeur les rejette
  (`unpacker` : code commençant par `SEI / LDA #$35 / STA $01 / JSR`). Une vraie parade générale demanderait d'émuler
  l'`init` et de refuser tout morceau qui écrit au-dessus de `HISTART` : à faire si d'autres cas apparaissent.
- **La pile C de cc65 était dans la zone des morceaux.** Le démarrage de cc65 place le sommet de la pile à
  `__MAIN_START__ + __MAIN_SIZE__` ; avec notre configuration (zone `MAIN` de 64 octets pour le lanceur BASIC) cela
  donnait `$084D` : chaque appel de fonction écrasait `$082D-$0847`, donc le début des 156 morceaux chargés à `$0800`.
  Ceux dont le code d'initialisation tombait là (*Alright*, *Dark Ages*) plantaient le lecteur ; les autres ne s'en
  apercevaient pas. Trouvé le 2026-11-18 avec le moniteur de VICE (point d'arrêt sur écriture, puis lecture de
  `sp` en `$02-$03`). Corrigé par `c64/stack.s` : un constructeur replace la pile à `__HIMEM__` ($D000).
  Le soupçon « le SID est mauvais » était faux : la comparaison avec d'autres morceaux au même format l'a montré.
- Des instructions du type `sta $0000,x` dont on modifie l'adresse doivent être forcées en absolu
  (`a:$0000,x`), sinon l'assembleur les code sur 2 octets.

## Passage à Oscar64 (2026-11-19)

Le client C est passé de cc65 à **Oscar64**, sans changer le lecteur (`play.s`, `logo.s`, `scroll.s` restent en ca65) :
`client.c` assemble `console.c` (remplace conio), `uci.c` et `main.c` ; `build.sh` lie d'abord le lecteur à `HISTART`
(`asm.bin`), génère les adresses de ses variables pour le C, compile en deux passes (la première donne la taille de
l'image que le copieur du démarrage recopie de `$0900` vers `HISTART`). `boot.s`, `stack.s` (la pile d'Oscar64 est en haut
de la zone résidente) et `jukebox.cfg` ont disparu. Essais préalables : `-Oirs -Cl` de cc65 et llvm-mos ne gagnaient rien ;
Oscar64 libère environ 2 Ko (fin de l'image en `$C538` au lieu de `$CCFD` avec `HISTART=$A700`). Même comportement vérifié
dans VICE (démo) et sur l'Ultimate (morceau reçu du serveur public, lecture). `HISTART` peut monter jusqu'à `$AF00`
(`$B000` ne tient plus avec le titre agrandi ; 308 morceaux de plus après réindexation) mais le serveur servirait alors des morceaux
qui écraseraient les clients `$A700` : il fallait que le client annonce sa limite, fait en v1.5 (commande `RANDOM2 <fin> [motif]`, le serveur filtre sur `end_addr` ; `RANDOM` simple reste limité à `$A6FF` pour les clients v1.3.x et v1.4 ; un client v1.5 face à un serveur plus ancien repasse en `RANDOM` simple, ce qui reste sûr puisque ces morceaux finissent avant `$A700`). Les notes sur cc65 ci-dessus restent vraies pour l'historique (v1.3.3 et avant).

## À faire / idées

- **Changer l'adresse et le port du serveur** sans recompiler : aujourd'hui `SERVEUR_IP` et `SERVEUR_PORT`
  sont fixés dans le `Makefile` à la compilation (valeurs actuelles : `boombass.net`, `6474`). Piste : champ
  modifiable au clavier, comme dans *Belote LAN C64* (touche F3).
- Code sous licence MIT (ajoutée après la v1.1, ne couvre pas les morceaux de la HVSC) ; dépôt GitHub public : `Stephan83c/jukebox-sid-c64` (historique nettoyé avant la publication).
- Le texte du scroller ne change qu'au morceau suivant ; un rafraîchissement en cours de lecture
  demanderait un accès réseau pendant le morceau (risque pour la synchronisation).
- Plus de glyphes au scroller : alphabet de 45 glyphes (A-Z, `* . , ! ? - / ' :`, 0-9). Il reste 18 codes libres (`$C2-$DF`, 15 glyphes possibles), 16 octets par glyphe, 236 octets de marge.
- Tester les touches ESPACE / Q / S / C / V sur le matériel (seules les commandes de lecture ont été
  vérifiées à distance) et l'enchaînement à la fin d'un morceau en durée normale.
- Série de morceaux au hasard pour repérer ceux qui plantent le lecteur, puis resserrer le tri.
- Un chat (écarté pour l'instant : la page zéro et les sockets sont les deux obstacles).
- Serveur public en ligne depuis la v1.1 : l'équipe HVSC a répondu le 2026-11-19 « It's all ok for us, please go on with your project. » (avis favorable, pas une licence : les droits restent aux compositeurs).
