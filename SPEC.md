# SPEC : SID Jukebox pour C64 Ultimate

Spécification du projet, état de la v1.8 (2026-11-21). Elle décrit **ce que le système doit faire et les
contraintes à respecter** ; le pourquoi des choix est dans `HISTORY.md`, l'usage dans `README.md`, les
procédures dans `docs/`.

## 1. But et périmètre

Un jukebox SID en ligne : un **C64 Ultimate** demande un morceau aléatoire à un **serveur**, le reçoit par
la Command Interface (UCI, TCP) et le **joue lui-même** (le 6510 exécute le code du morceau). Pas de
synchronisation entre clients : chacun a son tirage.

Hors périmètre : C64 sans Ultimate (pas d'UCI), RSID, morceaux multi-SID, morceaux cadencés par un timer
CIA, lecture d'un morceau pendant que le réseau est actif.

## 2. Composants

| Composant | Fichiers | Rôle |
|---|---|---|
| Indexeur | `indexer.py` | lit la HVSC, classe chaque `.sid` (compatible ou rejeté + raison) dans `jukebox.db` |
| Serveur | `server.py` | protocole texte TCP, tirage, limites par IP |
| Page web | `web.py` | texte du scroller proposé par les utilisateurs |
| Client C64 | `c64/` | réseau, écrans (C, Oscar64) ; lecteur, logo, scroller (assembleur, ca65) |
| Outils | `client_pc.py`, `update_db.sh`, `fix_entry_range.py`, `ips.sh` | test, mise à jour de la base, exploitation |

Le serveur ne garde aucun état partagé entre clients. `jukebox.db` et `C64Music/` ne sont pas dans git et
doivent correspondre (la base contient les chemins des fichiers).

## 3. Protocole (TCP, texte, une commande par ligne, réponses terminées par `\n`)

| Commande | Réponse |
|---|---|
| `RANDOM [motif]` | `OK\|id\|taille\|secondes\|images/s\|sous-morceau\|chargement\|init\|play\|titre\|auteur\|année\|scroller` puis `taille` octets de code brut (en-tête PSID retiré) |
| `RANDOM2 <fin> [motif]` | idem ; `<fin>` = 4 chiffres hexadécimaux = dernière adresse laissée aux morceaux (`HISTART-1`) ; seuls les morceaux finissant au plus tard à `<fin>` sont proposés (clients v1.5+) |
| `GET <id>` | idem, pour un morceau précis (compatible seulement) |
| `STATS` | `STATS\|compatibles\|total` |
| `QUIT` | ferme la connexion |
| erreur | `ERR\|message` (`aucun morceau`, `limite invalide`, `commande inconnue`, `trop de requetes`) |

- `motif` : sous-chaîne cherchée sans casse ni accents dans l'auteur ou le titre, 40 caractères au plus ;
  les jokers SQL sont neutralisés.
- `RANDOM` sans limite vaut `$A6FF` (anciens clients v1.3-v1.4). Un client récent qui reçoit
  `ERR|commande inconnue` à `RANDOM2` retombe sur `RANDOM`.
- `images/s` = cadence du morceau (50 ou 60, d'après l'horloge de son en-tête), pas celle de la machine.
- Titres, auteurs et scroller sont envoyés **sans accents**, en ASCII (le C64 n'affiche que 32-95).
- Scroller : alphabet fixe de 32 glyphes, 150 caractères au plus, relu à chaque morceau.
- Limites du serveur : 8 connexions simultanées par IP, 200 au total, 30 commandes par IP et par minute,
  20 s pour la première commande, 300 s d'inactivité, 1024 octets par ligne, `RANDOM2` refuse une limite
  inférieure à `$0900`. Les compteurs sont gardés en mémoire : un redémarrage les remet à zéro.

## 4. Tri des morceaux (`indexer.py`)

Un morceau est `compatible` s'il passe toutes les règles ci-dessous. Tout est stocké, rejetés compris, avec
la colonne `reject`. Le serveur ne sert que `compatible = 1`.

| Raison | Règle |
|---|---|
| `rsid` | format RSID |
| `mus` | fichier MUS |
| `multisid` | deuxième ou troisième SID |
| `too_big` | fichier de plus de 16 384 octets |
| `bad_range` | chargement sous `--min-load` ($0800) ou fin au-dessus de `--max-addr` |
| `no_songs` | aucun sous-morceau |
| `play0` | `play = 0` : le morceau installe sa propre interruption |
| `unpacker` | en-tête `78 A9 35 85 01 20` : décompresse jusqu'à $CFFF et écrase le client |
| `cia` | sous-morceau de départ cadencé par un timer CIA, pas à chaque image |
| `entry_range` | `init` ou `play` hors de `--min-load`..`--max-addr` (issue #2, v1.8) |
| `known_bad` | MD5 listé dans `bad_tunes.txt` (écarté à la main ; `fix_bad_tunes.py` l'applique à une base existante) |

**Invariant** : `--max-addr` = `HISTART - 1` = `MEM_HAUT` (`c64/main.c`). Valeur actuelle : `$AEFF`.
Attention : la valeur par défaut de `indexer.py` est `$BFFF`, il faut toujours passer `--max-addr` (ou
passer par `update_db.sh`, qui le fait).

`entry_range` est volontairement large : 9 morceaux sur 25 qui ont un `play` hors plage fonctionnent
quand même (ils recopient leur code), on les perd par prudence. Le tri statique ne sait pas les distinguer.

## 5. Client C64

### 5.1 Carte mémoire

| Zone | Contenu |
|---|---|
| `$0801-$08FF` | démarrage BASIC (`SYS`) et copie de l'image résidente |
| `$0800`..`HISTART-1` | **le morceau** (chargé à son adresse) |
| `HISTART`..~`$C595` | client résident : lecteur, logo, scroller (3 631 octets) puis code C |
| ..`$D000` | pile C (descend depuis `$D000`) |
| `$D000-$DFFF` | E/S ; mappées en RAM pendant l'appel du morceau (écoute des écritures SID) |
| `$F400-$FFFF` | affichage : écran `$F400`, caractères `$F800`, banque VIC 3, RAM sous le KERNAL |

`HISTART` vaut `$AF00` (v1.8). L'image occupe `$AF00-$C595`.

**Mesure de la pile** (2026-11-21, C64 Ultimate réel, v1.8, un cycle réseau complet : fin de morceau,
connexion, téléchargement, lecture) : la pile n'a pas dépassé 256 octets sous `$D000`. Zone `$C5A5-$CEFF`
(2 395 octets) restée intacte. Elle ne couvre pas la recherche (touche S) ni les erreurs de connexion.

### 5.2 Comportement

- Cycle : connexion, demande (`RANDOM2`), réception, **fermeture du socket**, lecture, au bout de la durée
  (plafonnée par `MAX_SECS` = 1000 s) nouvelle connexion.
- Un interruption raster par image pilote le lecteur. Le morceau est appelé à **sa propre cadence** (50 ou
  60 Hz) quel que soit le mode vidéo : la cadence de la machine est mesurée au début de chaque morceau (raster
  montant au-delà de la ligne 288 = PAL). La hauteur suit l'horloge du SID (environ 4 % plus aiguë en NTSC,
  non corrigé).
- Pendant la lecture, la page zéro appartient au morceau (sauvée avant, restaurée après) ; le clavier est lu
  directement dans la matrice.
- Vérifications avant lecture : taille non nulle, chargement ≥ `$0800`, fin ≤ `MEM_HAUT`, sous-morceau ≥ 1.
- Touches : ESPACE (suivant), S (recherche), L (boucle), V (vu-mètres, rejoue le même morceau), Q (BASIC).
- Version affichée en haut à droite : `VERSION` du Makefile ; le scroller de secours et `scroll.txt` annoncent
  la version courante.

### 5.3 Contraintes de sûreté UCI (non négociables)

1. **Aucun socket ouvert pendant la lecture d'un morceau.**
2. Après une erreur de lecture (-1) ou une fermeture par l'hôte, ne plus écrire ni fermer ce socket.
3. Ne jamais réinitialiser ni redéployer pendant un téléchargement ; attendre qu'un morceau joue
   (`make deploy` quitte par F7 et vérifie le retour au BASIC).
4. Si la Command Interface est bloquée (`$DF1C` reste à `$15`), seule une coupure d'alimentation la débloque.
5. Le serveur coupe l'ancienne connexion d'une IP qui se reconnecte par un vrai RST (`SO_LINGER` à 0).

### 5.4 Chaîne de compilation

- Partie assembleur : `ca65`/`ld65` (cc65), liée à `HISTART`, donne `build/asm.bin`.
- Partie C : Oscar64, deux passes (la première mesure la taille de l'image à recopier).
- Les temporaires d'Oscar64 sont en page zéro `$02-$63` : le lecteur les sauve et les restaure autour du morceau.
- `make demo` : un morceau intégré, sans réseau (pour VICE). `make deploy` envoie sur l'Ultimate.
  VICE n'émule pas l'UCI : il ne teste ni le réseau ni la pile réseau.

## 6. Invariants à respecter ensemble

| Si on change… | …il faut aussi changer |
|---|---|
| `HISTART` (`c64/Makefile`) | `MEM_HAUT` (suit `RUN` tout seul), `--max-addr` de l'indexeur, `LIMITE` (calculée par `build.sh`), puis réindexer ou appliquer la nouvelle limite à la base |
| la taille du client | vérifier la pile restante (`$D000` moins fin d'image : ≥ 256 octets mesurés + marge) |
| une règle de tri | `indexer.py`, ce SPEC, et le script de correction de la base du serveur (`fix_entry_range.py` sert de modèle) |
| le protocole | `server.py` (en-tête), le client, README EN et FR, ce SPEC ; rester compatible avec les anciens clients (`RANDOM`) |
| la version | `Makefile`, `build.sh`, `c64/README.txt`, `HISTORY.md`, `scroll.txt` **et** `d_scroll` dans `main.c`, avant de compiler (voir `docs/RELEASE.md`) |

## 7. Exploitation

- Le serveur garde la base ouverte : tout changement de `jukebox.db` demande un redémarrage.
- Avant de redémarrer : vérifier dans le journal qu'aucun C64 n'est connecté (les connexions durent environ
  une seconde par morceau).
- Mise à jour de la base : `docs/UPDATE_DB.md`. Publication d'une version : `docs/RELEASE.md`.
- Texte du scroller : `scroll.txt` (défaut) ou `scroll_user.txt` (page web, valable 1 heure).
- La HVSC est à usage privé (`DOCUMENTS/Disclaimer.txt`) ; l'hébergement public reste à régler avec l'équipe HVSC.

## 8. Points ouverts

- **Issue #2** (`?SYNTAX ERROR IN 10`) : les 25 morceaux `entry_range` ont été écartés, cause non confirmée
  pour l'utilisateur d'origine (titre du morceau demandé).
- **Morceaux qui se figent dans `init`** : avec les vu-mètres actifs, `init` tourne avec les E/S en RAM, donc un morceau qui attend `$D012` boucle sans fin (cas de Riparian, écarté via `bad_tunes.txt`). Les autres cas ne sont connus que quand ils plantent ; une recherche d'octets sur `$D011/$D012` donne surtout des faux positifs (5 sur 5 sains).
- **Piste mémoire** : remonter `HISTART` à `$B700` (pile restante 619 octets) récupérerait 359 morceaux ; non
  fait, demande une nouvelle version du client et une mesure de la pile pendant la recherche.
- **Piste générale** non faite : émuler `init` et refuser tout morceau qui écrit au-dessus de `HISTART`.
- Texte web affiché sur le C64 : non vérifié à l'œil.
