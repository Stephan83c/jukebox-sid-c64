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
   service `systemd --user`, comme le serveur de belote qui y tourne déjà. Le dépôt GitHub (privé) est
   cloné sur le serveur avec une clé de déploiement en lecture seule.
12. **Vu-mètres en arc-en-ciel** : dégradé fixe sur les 32 cases (rouge à violet, jamais de noir).
13. **Texte du scroller fourni par le serveur** (`scroll.txt`, relu à chaque morceau, alphabet fixe de
   32 glyphes, 150 caractères). Le client était plein (le premier essai dépassait de 680 octets) : texte de
   secours ramené de 423 à 72 colonnes, texte du serveur converti sur place dans le tampon d'en-tête.
   Marge restante : 7 octets.

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

Motifs de rejet (version actuelle) : plage mémoire incompatible, morceaux cadencés par un timer CIA,
RSID, trop gros (> 16 Ko), multi-SID, sans routine de lecture.

## Impasses et leçons

- Le moniteur à distance de VICE a servi à trouver trois bugs (un `BRK` dans un mauvais rip de la HVSC,
  une adresse relue sous la ROM, des instructions modifiées en cours de route) ; sans lui, on aurait tâtonné.
- Un morceau de démo qui plante n'est pas forcément la faute du lecteur : *Thrust* (HVSC) a un en-tête
  qui ne correspond pas à son code.
- Des instructions du type `sta $0000,x` dont on modifie l'adresse doivent être forcées en absolu
  (`a:$0000,x`), sinon l'assembleur les code sur 2 octets.

## À faire / idées

- **Changer l'adresse et le port du serveur** sans recompiler : aujourd'hui `SERVEUR_IP` et `SERVEUR_PORT`
  sont fixés dans le `Makefile` à la compilation (valeurs actuelles : `boombass.net`, `6474`). Piste : champ
  modifiable au clavier, comme dans *Belote LAN C64* (touche F3).
- Code sous licence MIT (ajoutée après la v1.1, ne couvre pas les morceaux de la HVSC) ; dépôt GitHub privé : `Stephan83c/jukebox-sid-c64`.
- Le texte du scroller ne change qu'au morceau suivant ; un rafraîchissement en cours de lecture
  demanderait un accès réseau pendant le morceau (risque pour la synchronisation).
- Plus de glyphes au scroller : alphabet de 45 glyphes (A-Z, `* . , ! ? - / ' :`, 0-9). Il reste 18 codes libres (`$C2-$DF`, 15 glyphes possibles), 16 octets par glyphe, 236 octets de marge.
- Tester les touches ESPACE / Q / S / C / V sur le matériel (seules les commandes de lecture ont été
  vérifiées à distance) et l'enchaînement à la fin d'un morceau en durée normale.
- Série de morceaux au hasard pour repérer ceux qui plantent le lecteur, puis resserrer le tri.
- Un chat (écarté pour l'instant : la page zéro et les sockets sont les deux obstacles).
- Serveur public en ligne depuis la v1.1 : la question des droits des morceaux (HVSC) reste à régler.
