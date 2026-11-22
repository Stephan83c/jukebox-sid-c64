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

## v1.9 : hauteur juste en PAL/NTSC, norme affichée (2026-11-22)

- **Hauteur** (suite de la demande Reddit du 2026-11-20 : « le SID sait s'il est PAL, ajuste en conséquence »). L'horloge du SID suit la
  machine (PAL 985 kHz, NTSC 1 023 kHz) : un morceau de l'autre norme sonnait 3,8 % trop aigu (NTSC) ou trop grave (PAL). `fixpitch`
  (`play.s`), appelée par `sync_sid` quand la cadence du morceau diffère de celle de la machine, corrige les fréquences des 3 voix dans la
  copie « shadow » : v -/+ (v + v/4)/32 = x0,961 ou x1,039 (plafond $FFFF), à peu près 0,2 % d'écart avec le rapport exact. Sans
  vu-mètres la copie est quand même utilisée quand les normes diffèrent (morceau avec E/S en RAM : voir le cas Riparian).
  Mesuré par capture HDMI : rapport de hauteur NTSC/PAL 1,038 -> 1,000 (9 morceaux de la HVSC, 5 à 50 Hz et 4 à 60 Hz : 0,998-1,001) ;
  enchaînement *Cyberworm* (50 Hz) puis *Zack's Stew* (60 Hz) sans redémarrer, machine PAL : 1,000 ; 20 min NTSC + 10 min PAL de
  lecture réelle sans plantage.
- **Affichage** : après le temps, la norme de la machine puis la cadence du morceau (`PAL  60HZ`, `NTSC 50HZ`).
- **Place** : `stacksize(256)` -> `64` (la pile logicielle d'Oscar64 n'est jamais utilisée : aucune référence dans le code généré ; 61 octets
  de frames statiques seulement). Sauvegarde de la page zéro (`zpsave`, 256 octets) déplacée en `$D200`, RAM sous les E/S
  (accès avec `$01 = $34` sous `sei`) : `$E000-$F3FF` avait été essayé, mais chaque page y est écrite par 20 à 50 morceaux
  (mesuré par `sidcheck`), `$D200` par 2. Image `$AF00-$CEB7`, environ 240 octets libres.
- **Gels** : *El Joe* figeait le lecteur (`play` sans fin, E/S en RAM). `sidcheck.c` émule le lecteur sur toute la base
  (44 676 morceaux en 18 s) : 285 morceaux dangereux (écriture ou exécution dans le client, vecteurs, init/play sans fin)
  ajoutés à `bad_tunes.txt` ; plus *Horror City* (muet). Test : 20 min de « Next » automatique toutes les 1,3 à 5 s, sans gel.
  Parade dans le client : l'interruption du CIA1 est réactivée avant chaque accès réseau (les délais réseau comptent sur
  l'horloge du KERNAL). Bug évité en route : `fixpitch` (dans l'IRQ) partageait `tmp/tmp2` avec les vu-mètres.
- **Serveur** : `QUIT` comptait dans le limiteur (15 morceaux/min réels) ; 8 connexions accrochées bloquaient l'IP 5 min.
  `QUIT`/`STATS` ne comptent plus, inactivité 30 s, la plus ancienne connexion coupée par RST. Le client affiche
  `SERVER BUSY, WAIT...` sur `ERR|trop de requetes` (avant : « NO MATCH » et la recherche effacée). `make_demo.py` produit aussi `DEMO_FPS`.

## v1.8 : tempo juste en NTSC, plus de place (2026-11-21)

- **Tempo PAL/NTSC** (demande d'un utilisateur américain sur Reddit, 2026-11-20 : sur son Ultimate en NTSC les morceaux PAL
  allaient 20 % trop vite). Le lecteur appelait le morceau à chaque image vidéo, donc à 60 Hz en NTSC. Maintenant
  `play.s` mesure la cadence de la machine au début de chaque morceau (raster qui monte ou non au-delà de la ligne 288)
  et appelle le morceau à sa propre cadence (champ `fps` du serveur) avec un accumulateur : une image sur six sans appel
  en NTSC pour un morceau 50 Hz, parfois deux appels en PAL pour un morceau 60 Hz. Le temps écoulé et la durée comptent
  les appels réels (`tframes`) ; les effets visuels restent à la cadence de la machine (`frames`).
  Mesuré avec une clé de capture HDMI (même morceau, *Zoids*, redémarré en PAL puis en NTSC) : facteur de vitesse
  NTSC/PAL 1,005 (un tempo +20 % ressortirait à 1,2), identique sur ARMSID et sur UltiSID ; trois morceaux
  enchaînés avec bascule NTSC -> PAL entre deux : le tempo suit. La hauteur, elle, reste 3,8 % plus aiguë en NTSC
  (rapport mesuré 1,038) : l'horloge du SID n'était pas corrigée (fait en v1.9).
  Limite : la cadence de la machine n'est mesurée qu'au début d'un morceau ; changer de mode vidéo en cours de morceau
  ne se corrige qu'au morceau suivant.
- **Place** : le lecteur a grossi, le client ne tenait plus à `$AF00`. Récupéré : `hdr` 340 -> 300, `cmd` 80 -> 64,
  `uci_statut` 40 -> 16, tampon de commande partagé avec le tampon de lecture (`chunk` 120), `cy * 40` et `secs * fps`
  sans la routine de multiplication (56 octets). Image `$AF00-$CE7C` ; le client tient jusqu'à `$AF40`, soit 64 octets
  de marge avec la pile à 256. Piège : Oscar64 exige de placer la pile entière (`stacksize`) dans la région, le message
  d'erreur est seulement « Cannot place stack section ».
- **Éprouvé** : environ 25 minutes de lecture continue sur le vrai C64U sans plantage ni retour au BASIC.

## v1.7 : V ne change plus de morceau (2026-11-21)

- **Issue #1** (signalée sur GitHub) : la touche V inversait `vis_on` mais laissait `rejouer` à 0, donc le morceau
  suivant était demandé au serveur. Maintenant `rejouer = 1`, comme pour L : le même morceau repart de 0:00 avec
  le nouveau réglage (le lecteur ne lit `vis_on` qu'au démarrage d'un morceau ; un basculement à chaud demanderait
  de modifier `play.s`). Testé sur le C64U le 2026-11-21.
- **Issue #2** (`?SYNTAX ERROR IN 10`, retour au BASIC 3 s après le début d'un morceau) : en attente de précisions
  du rapporteur (morceau concerné). Non corrigée.

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

## Limite de débit : les refus ne comptent plus (2026-11-20)

- Constaté lors d'un test de charge (50 connexions depuis une IP) : `req_ok` notait la requête avant de la tester, donc un
  client bloqué qui insistait prolongeait son blocage (la fenêtre de 60 s ne se vidait jamais, retour à la normale ~2 min).
  Maintenant seules les requêtes acceptées sont notées (30/min/IP inchangé). Vérifié en local ; à déployer sur le VPS
  (`git pull` + `systemctl --user restart jukebox`, hors lecture d'un C64).
- Test de charge du 2026-11-20 : 4 connexions simultanées OK ; 50 simultanées depuis une IP : 8 servies, 42 refusées
  (`MAX_CONN_IP`, fermeture sans message) ; 50 étalées sur 25-50 s : environ 15 servies (2 commandes par connexion avec QUIT).

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

- **(Fait en v1.8 pour le tempo ; reste la hauteur) Lecteur indifférent au NTSC/PAL** (demandé par un utilisateur américain sur Reddit, 2026-11-20 : sur son Ultimate réglé en NTSC,
  les morceaux PAL vont environ 20 % trop vite ; il a dû repasser en PAL). Cause : le lecteur appelle le morceau une fois par
  image vidéo (`play.s`, interruption raster), donc à 60 Hz sur une machine NTSC ; comme sur un vrai C64, c'est « normal ». Piste
  pour le tempo : appeler le morceau à sa propre cadence (50 ou 60 Hz, que le serveur envoie déjà) en sautant 1 image sur 6 en
  NTSC, ou en ajoutant un appel de temps en temps en PAL. La hauteur (horloge du SID, environ 3,8 % d'écart) est une étape à part :
  il faudrait recalculer les fréquences écrites au SID. **À ne pas commencer avant que la v1.6 ait fait ses preuves** (décision du
  2026-11-20). Réponse faite à l'utilisateur : PAL pour l'instant, « peut-être une version future ».
- **Changer l'adresse et le port du serveur** sans recompiler : aujourd'hui `SERVEUR_IP` et `SERVEUR_PORT`
  sont fixés dans le `Makefile` à la compilation (valeurs actuelles : `boombass.net`, `6474`). Piste : champ
  modifiable au clavier, comme dans *Belote LAN C64* (touche F3).
- Code sous licence MIT (ajoutée après la v1.1, ne couvre pas les morceaux de la HVSC) ; dépôt GitHub public : `Stephan83c/jukebox-sid-c64` (historique nettoyé avant la publication).
- Passage de MIT à GPL v3 le 2026-11-22 (auteur unique) ; les versions déjà publiées restent sous MIT. Le fichier `LICENSE` contient désormais le texte GPLv3.
- Le texte du scroller ne change qu'au morceau suivant ; un rafraîchissement en cours de lecture
  demanderait un accès réseau pendant le morceau (risque pour la synchronisation).
- Plus de glyphes au scroller : alphabet de 45 glyphes (A-Z, `* . , ! ? - / ' :`, 0-9). Il reste 18 codes libres (`$C2-$DF`, 15 glyphes possibles), 16 octets par glyphe, 236 octets de marge.
- Tester les touches ESPACE / Q / S / C / V sur le matériel (seules les commandes de lecture ont été
  vérifiées à distance) et l'enchaînement à la fin d'un morceau en durée normale.
- Série de morceaux au hasard pour repérer ceux qui plantent le lecteur, puis resserrer le tri.
- Un chat (écarté pour l'instant : la page zéro et les sockets sont les deux obstacles).
- Serveur public en ligne depuis la v1.1 : l'équipe HVSC a répondu le 2026-11-19 « It's all ok for us, please go on with your project. » (avis favorable, pas une licence : les droits restent aux compositeurs).
