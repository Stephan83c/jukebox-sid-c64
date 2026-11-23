# SPEC v2.0 : SID Jukebox pour C64 Ultimate (brouillon à valider)

Rédigée le 2026-11-22 à partir des bugs de la v1.9 (voir `BaseC64/bugs.md`, entrées du 2026-11-22) et des mesures faites
sur la base (44 390 morceaux jouables). `SPEC.md` reste la description de la v1.x en production ; ce document est le contrat
de la v2.0, qui **refait tout** : outil d'analyse, base, serveur, protocole et client.

Les mots **DOIT** et **NE DOIT PAS** marquent les exigences testées ; « devrait » marque un objectif.

---

## 1. Objectifs

Par ordre de priorité :

1. **Le C64 ne se bloque jamais.** Quel que soit le morceau ou l'état du serveur, il finit toujours par afficher un
   message et passer au morceau suivant, ou par rendre la main proprement (Q). Aucun gel, aucun retour sauvage au BASIC.
2. **Le son est exact.** Le morceau écrit lui-même dans le vrai SID, dans l'ordre et avec les valeurs qu'il a choisis,
   vu-mètres actifs ou non. Seule différence admise : 16 à 17 cycles de plus par écriture SID (§5).
3. **Les fonctions de la v1.9 sont toutes conservées** (§7.4), en particulier les vu-mètres par voix et la correction
   PAL/NTSC.
4. **Le plus de morceaux possible**, sans jamais sacrifier 1 ou 2.

### Hors périmètre (inchangé)

C64 sans Ultimate, RSID, multi-SID, morceaux cadencés par un timer CIA, `play = 0`, réseau actif pendant la lecture.

### Leçons de la v1.x qui fondent cette spec

| Constat (2026-11-22) | Conséquence pour la v2.0 |
|---|---|
| 152 morceaux laissent `$01 = $37` en rendant la main ; le lecteur, sous la ROM du BASIC, part en `READY.` (*Adidas Football*) | init/play appelés **depuis une zone toujours en RAM**, `$01` remis par le client (§7.3) |
| 1 543 morceaux écrivent en `$0200-$0333`, dont 529 sur le vecteur clavier `$028F` ; l'IRQ suivante saute dans l'écran (*Stormy Night*) | contrat d'état complet : tout ce que le morceau peut abîmer est sauvé et restauré (§7.2) |
| Capture des écritures SID en RAM : 34 185 morceaux (77 %) écrivent deux valeurs dans le même registre de contrôle dans une image ; seule la dernière arrivait au SID (*Gunfight*) | **plus de capture** : relais d'écriture SID (§5) |
| Serveur figé : le client attendait sans fin à `CONNECTING...` | délai maximal sur chaque attente réseau (§7.7) |
| `sidcheck` ne voyait ni `$01` laissé modifié, ni les pages 2-3 | l'analyse vérifie **tout l'état** que le client restaure (§4) |
| Oscar64 a supprimé du code vivant (touche S) selon la forme d'un `return __asm` | client en un seul langage maîtrisé, contrôle automatique des tailles et des symboles (§8, décision D1) |

---

## 2. Architecture

| Composant | Rôle | Nouveau en v2.0 |
|---|---|---|
| `indexer.py` | lit la HVSC, règles statiques (§3), remplit `jukebox.db` | colonnes v2 |
| `sidscan` (C) | **émule chaque morceau** dans les conditions exactes du client v2 ; rend le verdict (§4) et la liste des écritures SID (§5) ; remplace `sidcheck` | oui |
| `server.py` | tirage, limites, texte du scroller, protocole v1 **et** v2 ; fabrique le bloc de relais (§5.4, §6) | `RANDOM3` |
| `web.py` | page web du texte du scroller (§6.4) | inchangé |
| client C64 | réseau UCI, écrans, lecteur | réécrit |
| outils de test | banc VICE automatique (§9.2), `client_pc.py` | banc versionné |

L'analyse est **faite hors ligne une fois** (base de 44 k morceaux : environ 20 s sur 12 processus) et stockée dans la base. Le
serveur ne fait aucune émulation : il lit la base et assemble des octets.

---

## 3. Règles statiques (`indexer.py`)

Inchangées par rapport à `SPEC.md` §4 (`rsid`, `mus`, `multisid`, `too_big`, `bad_range`, `no_songs`, `play0`, `unpacker`, `cia`,
`entry_range`, `known_bad`), avec `--max-addr = HISTART - 1` de la v2.0. Elles écartent vite le plus gros ; le verdict final est
celui de `sidscan`.

---

## 4. Analyse par émulation (`sidscan`)

### 4.1 Conditions d'émulation (DOIVENT être celles du client v2)

- ROM BASIC et KERNAL réelles, RAM initialisée comme le client la laisse (client présent de `HISTART` à `$CFFF`).
- `init` appelé avec `A = sous-morceau - 1`, `X = Y = 0`, `$01 = $36` (E/S visibles : le morceau écrit au vrai SID), drapeau I mis,
  `$02A6` = norme du morceau (§7.6).
- Puis `N` appels de `play` (défaut 10 000 = 200 s à 50 Hz ; au minimum la durée du morceau si elle est connue), chacun entré avec
  `$01 = $36`.
- Lectures d'E/S simulées : raster `$D011/$D012` qui avance, timers CIA qui décomptent, `$D41B/$D41C` qui varient (un morceau qui
  attend le raster DOIT passer).
- Relevé, pour init et pour play séparément : adresses écrites, lues (hors lecture d'instruction), exécutées ; écritures SID avec
  l'adresse et l'opcode de l'instruction ; valeur de `$01` au retour ; durée en cycles.

### 4.2 Verdict

Un morceau est **refusé** (`compatible = 0`, raison dans `reject`) si l'émulation montre (l'absence de relais complet n'est **pas** une raison de refus, §5.5) :

| Raison | Règle |
|---|---|
| `scan_client` | écriture ou exécution dans `HISTART..$CFFF` |
| `scan_save` | écriture dans une zone de sauvegarde du client sous les E/S (§7.1) ou dans `$FFFA-$FFFF` |
| `scan_initlong` | `init` ne rend pas la main en 2 s émulées |
| `scan_playlong` | un appel de `play` dépasse 15 000 cycles, ou 7 000 pour un morceau 60 Hz (deux appels possibles dans une image PAL, §7.6) |
| `scan_jam` | instruction de blocage, `BRK`, saut hors de la mémoire du morceau et des ROM |
| `scan_silent` | aucune écriture SID pendant `init` + 300 appels |

Sont **acceptés et gérés par le client** (plus de refus) : `$01` laissé modifié, écritures en `$0200-$03FF`, en page zéro, dans la pile,
dans les registres CIA/VIC.

### 4.3 Données stockées (table `scan`, une ligne par morceau et par sous-morceau joué)

`tune_id, song, scan_version, histart, calls, verdict, reject, complet, relay_addr, relay_len, nsites, nrelais, init_cycles, play_max,
port_init, port_play, lit_02a6, verif, relais (« adresse:opcode » dans l'ordre des relais), autres (sites non relayés et raison)`.
Implémentation : `sidscan.c` (émulateur) et `scan_db.py` (lancement en parallèle, remplissage de la table).

`scan_version` DOIT changer à chaque modification de `sidscan` ou de la carte mémoire du client ; le serveur ne sert que les lignes
de la version courante.

---

## 5. Relais d'écriture SID (cœur de la v2.0)

### 5.1 Principe

Chaque instruction du morceau qui écrit dans le SID est remplacée, **dans les octets envoyés par le serveur**, par un `JSR` de même
longueur vers un **relais** de 7 octets qui fait l'écriture d'origine, puis la même écriture dans une **copie** de 32 octets :

```
site d'origine :   8D 04 D4      STA $D404        devient   20 lo hi   JSR relais_k
relais_k :         8D 04 D4      STA $D404        (écriture d'origine, au vrai SID)
                   8D 04 cc      STA copie+4      (copie pour les vu-mètres et la hauteur)
                   60            RTS
```

`STA`/`STX`/`STY`, `JSR` et `RTS` ne touchent ni A, X, Y ni les drapeaux : le morceau ne voit aucune différence, sauf le temps
(16 à 17 cycles de plus par écriture) et 2 octets de pile.

### 5.2 Instructions remplaçables

| Opcode | Mode | Relais |
|---|---|---|
| `8D` / `8E` / `8C` | `STA` / `STX` / `STY` absolu | même opcode vers `copie + (adresse & $1F)` |
| `9D` / `99` | `STA` absolu,X / absolu,Y | même opcode, base `copie + (base & $1F)` |

Un site est **remplaçable** seulement si :
- sa base est dans `$D400-$D41F` et toutes les adresses effectives observées aussi (pas de miroir `$D420+`, pas de débordement de
  l'index hors de la copie) ;
- il est **dans les octets envoyés** (`chargement..fin`) : un lecteur recopié ailleurs par `init` (ex. *Adidas Football*) ou exécuté en
  page zéro (*Dark Ages*) n'est pas remplaçable (raison `copie`) ;
- ses 3 octets ne sont jamais écrits (code auto-modifié) ni lus comme des données pendant l'émulation ;
- aucun saut ne tombe au milieu de l'instruction.

Mesure (2026-11-22, 1 500 appels) : **43 375 morceaux (97,7 %)** ont tous leurs sites remplaçables ; 16 sites par morceau en médiane,
25 au 95ᵉ centile, 32 au 99ᵉ, 210 au maximum. Non remplaçables : écriture indirecte (125 morceaux), code auto-modifié (411),
octets relus (429).

### 5.2 bis Vérification par double émulation

Pour chaque morceau accepté qui a des relais, `sidscan` rejoue le morceau **modifié** (sites remplacés, bloc de relais en place, fabrication
identique au §5.4) et DOIT obtenir : la même suite d'écritures au SID (registre, valeur, dans l'ordre, empreinte sur tout le passage),
aucun plantage, et, si `complet = 1`, une copie égale aux dernières valeurs écrites. Résultat dans `verif` (`ok`, `diff`, `plante`,
`copie`). Le serveur NE DOIT servir des relais que pour `verif = ok` ; sinon le morceau part sans relais (§5.5).

### 5.3 Bloc de relais

```
relay_addr :  copie   32 octets   (registres $D400-$D41F vus par le morceau, mis à 0 avant init)
              relais  7 × n octets
```

- `n` DOIT être ≤ 48 (bloc ≤ 368 octets) ; au-delà, seuls les 48 sites les plus exécutés pendant l'émulation sont relayés (repli §5.5).
- `relay_addr` est choisi par `sidscan` dans `$0800..HISTART-1` : bloc contigu **jamais écrit, lu ni exécuté** par le morceau
  pendant l'émulation, hors de `chargement..fin`. Préférence : juste après la fin du morceau, sinon juste avant le chargement,
  sinon le premier trou assez grand.

### 5.4 Fabrication par le serveur

Pour une réponse `RANDOM3`, le serveur :
1. lit le code du morceau ;
2. remplace chaque site par `20 lo hi` vers son relais ;
3. fabrique le bloc (copie à zéro + relais) ;
4. envoie les deux (§6).

Le serveur NE DOIT PAS modifier un octet qui n'est pas un site listé par `sidscan` pour la `scan_version` courante.

Implémentation (étape 2, 2026-11-22) : `server.py` `build_relays()`, octet pour octet comme `fabriquer()` de `sidscan.c` (même
fonction pour la 2e émulation et pour `sidscan --dump`). Le serveur contrôle chaque site avant de le remplacer (opcode du fichier égal
à celui de la liste, base dans `$D400-$D41F`, bloc hors du morceau et ≥ `$0800`) ; au moindre écart le morceau part sans relais
(journal `relais refusés`). Relais servis seulement si `verif = ok` et si le bloc tient sous la limite `<fin>` du client.

### 5.5 Repli (morceaux sans relais complet, 2,3 %) — décision D3

Un morceau dont au moins un site n'est pas remplaçable (§5.2), ou qui a plus de 48 sites, ou pour lequel aucune zone libre ne
convient (§5.3), **reste jouable** :

- il est toujours joué **directement** : son exact, comme pour les autres ;
- les sites remplaçables sont relayés quand même (**relais partiels**) : la copie ne contient que ce qu'ils écrivent, les
  vu-mètres sont donc incomplets (une voix peut rester immobile) ;
- s'il n'y a aucune zone libre pour le bloc, pas de relais du tout : vu-mètres immobiles ;
- **pas de correction de hauteur PAL/NTSC** (la copie incomplète donnerait des fréquences fausses) ; le tempo reste corrigé ;
- le serveur l'indique par `complet = 0` dans l'en-tête (§6).

Aucun morceau n'est écarté pour cette seule raison.

---

## 6. Serveur, protocole et scroller

### 6.1 Protocole v2 (`RANDOM3`)

Les commandes v1 (`RANDOM`, `RANDOM2`, `GET`, `STATS`, `QUIT`) restent servies à l'identique pour les clients v1.x.

```
RANDOM3 <fin> [motif]
GET3 <id>
```

Réponse :

```
OK3|id|taille|secondes|images/s|sous-morceau|chargement|init|play|relais|taille_relais|complet|titre|auteur|année|scroller\n
<taille octets : code du morceau, sites déjà remplacés>
<taille_relais octets : bloc de relais, à copier à l'adresse relais>
```

- `complet` = 1 si tous les sites du morceau sont relayés, 0 sinon (§5.5) ; le client ne corrige la hauteur que si `complet = 1`.
- `relais = 0` et `taille_relais = 0` : pas de relais (§5.5), `complet = 0`.
- Le client DOIT refuser la réponse (et passer au suivant, socket vivant) si : `taille = 0`, chargement < `$0800`,
  `chargement + taille > HISTART`, bloc de relais hors de `$0800..HISTART-1` ou qui chevauche le morceau, `taille_relais > 368`,
  sous-morceau = 0, un champ numérique illisible.
- Toutes les règles d'encodage de `SPEC.md` §3 restent (ASCII sans accents, motif ≤ 40 caractères, scroller 150 caractères).
- `GET3 <id>` : la limite est `HISTART - 1` de l'analyse servie (`SCAN_HISTART` de `server.py`).
- Nombres de l'en-tête en décimal, comme en v1. Erreurs : `ERR|aucun morceau`, `ERR|limite invalide`,
  `ERR|commande indisponible` (base sans table `scan`).
- Limites du serveur : §6.2.

### 6.2 Serveur (`server.py`) — comportement de la v1.9 conservé

- Un seul processus `asyncio`, **aucun état partagé entre clients** ; la base SQLite est ouverte au démarrage (tout changement de
  `jukebox.db` demande un redémarrage, après avoir vérifié dans le journal qu'aucun C64 n'est connecté).
- Tirage : un morceau `compatible = 1` au hasard (commandes v2 : en plus, ligne `scan` du sous-morceau de départ avec
  `verdict = ok`, pour la `scan_version` la plus récente de `SCAN_HISTART`/`SCAN_CALLS`, constantes en tête de `server.py`), qui tient sous la limite
  `<fin>` envoyée par le client ; avec motif, recherche sans casse ni accents dans l'auteur et le titre (jokers SQL neutralisés).
  Durée : celle de la base (Songlengths HVSC), 180 s si inconnue.
- Textes envoyés au C64 : translittérés sans accents (`ø` -> `o`, `æ` -> `ae`, `ß` -> `ss`…), ASCII 32-95.
- Limites (constantes en tête de `server.py`) :

| Limite | Valeur |
|---|---|
| connexions simultanées par IP | 8 ; IP pleine : la **plus ancienne** connexion est coupée par un vrai RST (`SO_LINGER` à 0, l'Ultimate ignore parfois un FIN) |
| connexions simultanées au total | 200 |
| morceaux demandés par IP et par minute | 30 (`QUIT` et `STATS` ne comptent pas) |
| délai pour la première commande | 20 s |
| inactivité entre deux commandes | 30 s |
| longueur d'une commande | 1 024 octets |
| limite `<fin>` minimale acceptée | `$0900` |
| clé de limitation | IPv4 telle quelle ; IPv6 réduite à son bloc /64 |

- Les compteurs sont en mémoire : un redémarrage les remet à zéro.
- Clients v1.x : `RANDOM` sans limite vaut `$A6FF` ; `RANDOM2` et `GET` inchangés ; ils ne reçoivent jamais de morceau modifié.
- **Protection des clients v1.9 (décision D9, 2026-11-22)** : le client v1.9 publié reste tel quel (D7), mais le serveur cesse de
  lui envoyer les morceaux qui font planter son lecteur, repérés par `sidscan` :
  - `$01` laissé avec la ROM BASIC visible (`$01 & 3 = 3`) par `init` ou `play` : retour à `READY.` (*Adidas Football*) ;
  - écriture dans `$028F/$0290` (vecteur clavier KEYLOG) : gel à `CONNECTING...` (*Stormy Night*) ;
  - écriture dans les vecteurs `$0314-$0333` (IRQ, BRK, NMI, vecteurs du KERNAL).
  Les commandes v1 (`RANDOM`, `RANDOM2`, `GET`) excluent ces morceaux ; les commandes v2 les servent (le client v2.0 restaure
  `$01` et les pages 2-3). Sans table `scan`, le serveur sert comme avant. À mesurer avant de l'activer : nombre de morceaux retirés
  aux clients v1.9 (estimation : 152 pour `$01`, 529 pour `$028F`, 10 pour les vecteurs, mesures `sidcheck` du 2026-11-22).
- **Réintégration des morceaux écartés à la main** (`known_bad` acceptés par l'analyse, 80 au 2026-11-22) : par un indicateur
  propre à la v2 (lu par `RANDOM3`/`GET3`), **jamais** en remettant `compatible = 1`, qui les enverrait aussi aux clients v1.9
  (certains plantent leur lecteur, ex. *Riparian*).
- Exploitation : service `systemd --user` (`deploy/jukebox.service`, durci), journal par `journalctl --user -u jukebox`, mise à jour par
  `git pull` puis redémarrage, base remplacée par `update_db.sh` (avec les tables `scan` en v2.0). L'utilisateur fait lui-même les
  opérations sur le serveur public.
- Nouveau en v2.0 : fabrication du morceau modifié et du bloc de relais (§5.4) ; `STATS` peut ajouter la `scan_version`
  (`STATS|compatibles|total|version`, champ ignoré par les anciens clients).

### 6.3 Texte du scroller — comportement de la v1.9 conservé

- Le serveur ajoute le texte en **dernier champ** de chaque réponse `OK`/`OK3` ; il le relit **à chaque morceau** (aucun redémarrage
  pour le changer).
- Source : `data/scroll_user.txt` (proposé par la page web) s'il a **moins d'une heure** (date du fichier), sinon `scroll.txt` (message
  par défaut, local au serveur, hors git ; modèle `scroll.txt.example`).
- Alphabet : `A-Z 0-9 * . , ! ? - / ' :` et espace (45 glyphes) ; tout autre caractère devient une espace, espaces multiples réduites,
  **150 caractères** au plus.
- Côté C64 (§7.4) : le texte reçu est converti en indices de glyphes ; s'il manque ou est vide, le client affiche son texte intégré
  (qui annonce la version courante : à mettre à jour à chaque version, comme `scroll.txt` du serveur).

### 6.4 Page web du scroller (`web.py`) — inchangée en v2.0

- Processus **séparé** du serveur de morceaux (on peut le redémarrer sans toucher aux connexions des C64), bibliothèque standard
  seule, aucun accès à la base ni aux morceaux ; il n'écrit que dans `data/`.
- Servi en HTTPS derrière un proxy inverse ; le service écoute sur `127.0.0.1` avec `--trust-proxy` (lecture de `X-Forwarded-For`).
  Le port direct n'est pas ouvert, volontairement.
- Règles d'un nouveau texte : majuscules forcées, apostrophes des claviers de téléphone converties, même alphabet que le serveur,
  3 à 150 caractères, mots de `banned_words.txt` refusés, IP de `banned_ips.txt` refusées.
- Débit : **une modification toutes les 3 minutes pour tout le monde** (pause globale) et toutes les 3 minutes par IP ; 30 requêtes
  par IP et par minute ; 64 connexions traitées en même temps ; corps de requête ≤ 1 024 octets.
- Anti-robots : champ piège et jeton signé (formulaire rempli en plus de 3 s et moins d'une heure).
- Journal de chaque changement : `web_changes.log`. Page en français et en anglais (choix par `Accept-Language` ou lien), texte
  courant affiché en couleurs.
- Service `systemd --user` `deploy/jukeweb.service`.

---

## 7. Client C64

### 7.1 Carte mémoire (cible ; `HISTART` fixé à l'étape 5 du plan)

| Zone | Contenu |
|---|---|
| `$0801-$08FF` | démarrage, copie de l'image résidente |
| `$0800..HISTART-1` | morceau + bloc de relais |
| `HISTART..$BFFF` | **rien qui s'exécute pendant ou juste après un appel du morceau** (la ROM BASIC peut y revenir) |
| `$C000-$CFFF` | lecteur : appel du morceau, IRQ, retour ; tout code exécuté entre l'appel et la remise de `$01` |
| `$D000-$DFFF` (RAM sous les E/S) | sauvegardes : page zéro `$D200`, pages 2-3 `$D800-$D9FF`, réserve `$D100`, `$D300`, `$DA00-$DBFF` (aucun morceau ne les écrit, mesuré) |
| `$F400-$FFFF` | affichage de lecture (écran, caractères), vecteurs RAM `$FFFA-$FFFF` |

Règle : le code qui s'exécute entre `JSR init/play` et le retour en état connu DOIT être en `$C000-$CFFF` (ou en page zéro/pile, interdit
ici). Le reste du client peut être sous la ROM BASIC.

### 7.2 Contrat d'état autour du morceau

Avant `init`, le client DOIT sauvegarder, et après la fin du morceau (ou en cas d'abandon) restaurer :

| Élément | Action |
|---|---|
| page zéro `$02-$FF` | sauvée, restaurée |
| pages `$0200-$03FF` (variables et vecteurs KERNAL, `$028F`, `$0314-$0333`) | sauvées, restaurées |
| `$01` | remis après **chaque** appel (§7.3) |
| `$02A6` (indicateur PAL/NTSC du KERNAL) | mis à la norme du morceau avant `init`, restauré avec les pages 2-3 (§7.6) |
| CIA1 | ICR : sources coupées pendant le morceau ; à la fin timer A remis à la valeur KERNAL, CRA/CRB, DDR A/B, port A `$FF`, ICR `$81` |
| CIA2 | ICR `$7F` (aucune NMI d'un morceau ne doit survivre), timers arrêtés, DDR A et banque VIC remis |
| VIC | `$D011`, `$D016`, `$D018`, `$D01A`, `$D015` (sprites), couleurs ; `$D019` acquitté |
| SID | silence (volume 0, gates coupés) à la fin |
| drapeaux | `CLD` après chaque appel ; I géré par le client |
| pile | pointeur de pile sauvé avant init, restauré à la fin |

Un test automatique (§9.2) DOIT comparer tout cet état avant et après un morceau.

### 7.3 Appel du morceau

```
appel (en $C000-$CFFF) :  LDA #sous-morceau-1 / JSR init      (ou JSR play depuis l'IRQ)
                          LDX $01 / STX port_laisse            (pour le journal de test)
                          LDA #$36 / STA $01 / CLD
```

- Le morceau est toujours appelé avec `$01 = $36` (E/S visibles, ROM BASIC coupée, KERNAL présent).
- `$01 = $34` n'est plus utilisé pour jouer (fin de la capture).
- L'IRQ de lecture DOIT être en `$C000-$CFFF` et rendre la main par un chemin qui ne dépend pas de la ROM BASIC.
- Choix de l'étape 3 (SIDBox2, 2026-11-22) : **entre deux appels, le lecteur tourne avec `$01 = $35`** (KERNAL coupé) et son IRQ
  arrive directement par le vecteur matériel `$FFFE` (en RAM) : un morceau qui écrase `$0314`, `$028F` ou toute la page 3 ne
  peut plus dérouter le lecteur. Une IRQ survenue **pendant** un appel (morceau qui fait `CLI`) est acquittée et ignorée :
  par `$FFFE` si le morceau a coupé le KERNAL (drapeau `incall`), par `$0314` sinon. NMI ignorées (`$FFFA` et `$0318`).
- Piège : le jeu de caractères de l'écran de lecture (`$F800-$FFFF`) recouvre `$FFFA-$FFFF` ; les vecteurs DOIVENT être
  réécrits après sa copie (ce sont les derniers octets de la forme du caractère `$FF`, jamais affiché).
- Après chaque appel : copie des 25 premiers octets de la copie du bloc de relais dans `shadow` (vu-mètres), puis, si
  `complet = 1` et normes différentes, correction de `shadow` et réécriture des 6 registres de fréquence (§7.6).

### 7.4 Fonctions (identiques à la v1.9)

Logo animé, scroller (texte du serveur ou de la page web, §6.3 : alphabet de 45 glyphes, lettres de 12 pixels de haut sur les lignes 19-20, défilement fin de 2 pixels par image par `$D016` limité à ces lignes par deux interruptions raster, couleurs qui tournent), titre/auteur/année, temps écoulé et durée, norme
`PAL 50HZ`/`NTSC 60HZ`, vu-mètres par voix (V), boucle (L), recherche (S, `NO MATCH`), suivant (ESPACE), quitter (Q : `GOODBYE` puis
reset), messages `CONNECTING...`, `SERVER BUSY, WAIT...`, `FAILED, RETRYING...`, `ULTIMATE LOCKED: POWER CYCLE IT`,
`ENABLE COMMAND INTERFACE`. Le morceau est appelé à sa cadence (50/60) quelle que soit la machine (accumulateur de la v1.8).

### 7.5 Vu-mètres

- Les vu-mètres lisent la **copie** du bloc de relais (même modèle d'enveloppe que la v1.9 : gate, ADSR simulés par voix, pas
  d'attaque et de déclin des tables `astep`/`dstep`).
- Morceau sans relais complet : vu-mètres incomplets ou immobiles (§5.5).
- Option (D5) : les relais des registres de contrôle notent aussi les fronts montants du gate, pour que les vu-mètres voient les notes
  relancées dans une même image.

### 7.6 Normes PAL/NTSC (comportement de la v1.9, repris à l'identique sauf mention « nouveau »)

Historique : tempo corrigé en v1.8 (demande d'un utilisateur américain sur Reddit le 2026-11-20 : les morceaux PAL allaient 20 % trop
vite sur son Ultimate en NTSC), hauteur corrigée et norme affichée en v1.9. Mesures dans `BaseC64/mesures.md` (2026-11-21 et 22).

**Données.** Le serveur envoie `images/s` = **60 si l'horloge de l'en-tête PSID est `NTSC`, 50 sinon** (`PAL`, `PAL+NTSC`, inconnue).
Cette valeur sert à la fois de cadence d'appel du morceau et de norme de référence pour la hauteur.

**Norme de la machine** (`mfps`), mesurée **au début de chaque morceau** (le client survit donc à un changement de `System Mode`
entre deux morceaux, testé en v1.8) : attendre que le raster passe la ligne 256 (`$D011` bit 7) ; si le raster revient en haut avant
d'atteindre la ligne 288 (`$D012 ≥ $20` avec bit 7), c'est NTSC (60), sinon PAL (50). La mesure se fait interruptions coupées, avant
l'appel de `init`, et ne dépend pas du morceau.

**Tempo** : le morceau est appelé à **sa** cadence, pas à celle de la machine. À chaque image vidéo, `acc += images/s` ; tant que
`acc ≥ mfps` : `acc -= mfps` et un appel de `play`.
- Morceau 50 Hz sur machine NTSC : 5 appels pour 6 images (une image sur six sans appel).
- Morceau 60 Hz sur machine PAL : 6 appels pour 5 images (une image sur cinq avec **deux** appels).
- Le temps écoulé et la durée comptent les **appels** du morceau (`tframes`), divisés par `images/s` : le temps affiché est celui du
  morceau. Durée maximale : `secondes × images/s` appels, `secondes` plafonné à `MAX_SECS` (1 000 s).
- Mesuré (capture HDMI) : facteur de vitesse NTSC/PAL 1,005 (1,000 à 1,010 sur 9 morceaux), identique sur ARMSID et UltiSID.
- Conséquence pour l'analyse (nouveau) : un morceau 60 Hz peut être appelé deux fois dans la même image PAL ; `sidscan` DOIT vérifier que
  2 × `play_cycles_max` (relais compris) tient dans le budget de l'image PAL.

**Hauteur** : l'horloge du SID suit celle de la machine (PAL 985 248 Hz, NTSC 1 022 727 Hz, rapport 1,038). Quand `images/s ≠ mfps`,
les fréquences des 3 voix (`$D400/01`, `$D407/08`, `$D40E/0F`) sont corrigées :
- morceau PAL sur machine NTSC : `v - (v + v/4)/32` = ×0,9609 (idéal 0,9634, écart -4 cents) ;
- morceau NTSC sur machine PAL : `v + (v + v/4)/32` = ×1,0391 (idéal 1,0380, écart +2 cents), plafonné à `$FFFF`.
- Calcul sur 16 bits sans multiplication (décalages et additions, comme `fixpitch` de la v1.9), dans l'IRQ.
- Mesuré (capture HDMI) : rapport de hauteur NTSC/PAL 1,038 sans correction, **0,998 à 1,001** avec (9 morceaux, 5 à 50 Hz et 4 à 60 Hz) ;
  enchaînement *Cyberworm* (50 Hz) puis *Zack's Stew* (60 Hz) sans redémarrer : 1,000 ; 20 min en NTSC et 10 min en PAL sans plantage.
- Non corrigés (comme en v1.9) : durées ADSR (3,8 % d'écart, inaudible), largeur d'impulsion (sans effet sur la hauteur), filtre.
- **v2.0** : la correction s'applique en réécrivant les 6 registres de fréquence juste après chaque `play`, à partir de la copie du bloc
  de relais (le morceau a déjà écrit les valeurs non corrigées au vrai SID). Fenêtre non corrigée : au plus la durée de `play`
  (< 1 ms en général), à vérifier par capture et à l'oreille (§9.3). **Seulement si `complet = 1`** (§5.5).

**Indicateur PAL/NTSC du KERNAL (nouveau).** 569 morceaux lisent `$02A6` (1 = PAL, 0 = NTSC) pendant `init` ou leurs premiers appels
(mesure `sidscan`, 2026-11-22) pour s'adapter eux-mêmes à la machine. Avec la correction du lecteur, ils seraient corrigés **deux
fois** sur une machine de l'autre norme (défaut probable de la v1.9 en NTSC, jamais observé). Le client DOIT donc mettre `$02A6` à la
norme **du morceau** (1 si `images/s` = 50, 0 si 60) avant `init`, et le restaurer à la fin (pages 2-3, §7.2). `sidscan` émule avec la
même valeur.

**Affichage** : sur la ligne du temps (ligne 10, colonne 21), la norme de la machine puis la cadence du morceau, en gris (`$0C`) :
`PAL  50HZ`, `PAL  60HZ`, `NTSC 50HZ`, `NTSC 60HZ`.

**Tests** (§9.3) : passage en NTSC par l'API REST (`PUT /v1/configs/U64 Specific Settings/System Mode?value=NTSC`, non persistant ;
toujours remettre PAL à la fin) ; capture HDMI (clé MS2109, `/dev/video0` + ALSA `hw:3,0`, fermer OBS) ; morceaux de référence :
*Zoids* (50 Hz), *Axel F* (60 Hz, id 114), ids 45902, 45002, 42363, 25851, 36187 (50 Hz) et 4102, 51766, 45179, 45210 (60 Hz) ;
plus un morceau qui lit `$02A6` (à choisir dans la liste de `sidscan`). *Für Elise* (id 556) est un mauvais morceau de test (presque
silencieux après 3 s).

Hors périmètre : PAL-N (Drean) et ancien NTSC à 64 cycles par ligne, que le C64 Ultimate ne produit pas.

### 7.7 Réseau et délais

- Toutes les règles de sûreté UCI de `SPEC.md` §5.3 restent (aucun socket ouvert pendant la lecture, ne plus toucher un socket après -1,
  pas de reset pendant un téléchargement).
- **Chaque attente a une limite** : réponse à une commande UCI, ouverture (30 s), première ligne de réponse du serveur (10 s), données
  (5 s sans octet). Dépassement : fermer (si permis), `FAILED, RETRYING...`, nouvel essai après 3 s.
- L'horloge des délais DOIT fonctionner même si l'IRQ ne tourne pas (D4).

### 7.8 Garde-fou

Un morceau qui ne rend pas la main malgré l'analyse (matériel ≠ émulation) DOIT être abandonné : si `init` dure plus de 2 s, ou si `play`
ne rend pas la main pendant 25 images, le client restaure l'état (§7.2) et passe au suivant en signalant l'id. Mécanisme : décision D6.

---

## 8. Chaîne de compilation et contrôles

- Kick Assembler pour tout le client (D1, décidé) ; carte mémoire décrite dans un seul fichier.
- La construction DOIT échouer si : du code de la liste « exécuté autour du morceau » est hors de `$C000-$CFFF`, l'image dépasse
  `$CFFF - pile`, une zone de sauvegarde chevauche autre chose, une fonction attendue manque dans la table des symboles.
- `HISTART`, `--max-addr`, la limite envoyée dans `RANDOM3` et `scan_version` sont **générés depuis une seule valeur**.

---

## 9. Tests

### 9.1 Analyse

`sidscan` sur toute la base après chaque changement du client ou de l'outil : comptes par verdict, nombre de relais, comparaison avec
la version précédente (aucun morceau ne doit passer de refusé à accepté sans explication).

### 9.2 Banc VICE automatique (sans réseau)

Le vrai client en `HISTART`, morceau et bloc de relais chargés par le moniteur distant (`-remotemonitor`), appel du lecteur, puis
relevés automatiques : le lecteur tourne toujours, le temps avance, retour propre à la fin, **état §7.2 identique avant et après**,
écritures SID au vrai SID identiques (ordre et valeurs) à une exécution sans relais. Morceaux de non-régression :

| id | Morceau | Ce qu'il vérifie |
|---|---|---|
| 13636 | Adidas Football (Matthew Cannon) | `$01 = $37` au retour |
| 6301 | Stormy Night (Kim Andersen) | pages 2-3, vecteur `$028F` |
| 28342 | Gunfight (Jens-Christian Huus) | écritures doubles dans une image (son exact) |
| 31049, 27436 | Alright, Dark Ages | chargés en `$0800`, init bas |
| 42363 | Cyberworm (Phobos) | morceau de démo de référence |
| 24668 | Riparian (Goto80) | init qui attend `$D012` (doit passer en v2.0) |
| 22618 | City of Love (Extended Edition) | gel inexpliqué sur C64U : à rejouer |
| 44694, 3663 | El Joe, Horror City | `play` sans fin, muet sur C64U |

### 9.3 Matériel (C64 Ultimate)

- Touches ESPACE, S (avec et sans résultat), L, V, Q à la main.
- Endurance : 100 morceaux enchaînés automatiquement sans intervention, puis relecture de l'état par l'API REST.
- Serveur figé ou coupé pendant chaque étape réseau : le client affiche `FAILED, RETRYING...` et repart.
- NTSC : procédure et morceaux de référence du §7.6 ; hauteur et tempo par capture HDMI, dans les deux sens.
- Son : comparaison à l'oreille V actif/inactif sur Gunfight (doit être identique).

---

## 10. Plan

| # | Étape | Terminée quand |
|---|---|---|
| 1 | `sidscan` (à partir de `sidcheck`) : conditions §4.1, verdict, sites, `relay_addr` ; table `scan` | comptes sur toute la base, morceaux de non-régression conformes |
| 2 | Serveur : `RANDOM3`/`GET3`, fabrication du bloc ; tests par `test_v3.py` (référence `sidscan --dump`, serveur local, relecture et contrôles §6.1) | octets identiques à la fabrication de référence. **Fait le 2026-11-22** : 43 974 morceaux avec relais identiques, 317 sans relais servis tels quels |
| 3 | Client, lecteur seul (démo sans réseau) : appel §7.3, contrat §7.2, relais, vu-mètres, hauteur | banc VICE §9.2 vert sur toute la liste. **Fait le 2026-11-22** (`SIDBox2_C64/tools/banc.py`, 3 passages par morceau dont un dans l'autre norme) : 11 morceaux verts, *El Joe* refusé par l'analyse |
| 4 | Client, réseau : UCI, délais §7.7, garde-fou §7.8 | §9.3 sauf endurance. **Pannes du serveur à chaque étape réseau : faites le 2026-11-23**, toutes tenues (`SIDBox2_C64/tools/panne.py`, détail dans `SIDBox2_C64/docs/etape4.md`) ; restent NTSC et endurance (étape 6) |
| 5 | Mesure de taille, choix de `HISTART`, réindexation, `scan_version` | morceaux jouables comptés et comparés à la v1.9 |
| 5 bis | Protection des clients v1.9 (D9, §6.2) : `sidscan` relève les écritures en `$028F/$0290` et `$0314-$0333` (nouvelle colonne, `scan_version` + 1) ; le serveur exclut ces morceaux et ceux qui laissent la ROM BASIC visible des commandes v1 ; `test_v3.py` le vérifie | nombre de morceaux retirés aux clients v1.9 mesuré et accepté par l'utilisateur, test vert |
| 6 | Endurance, NTSC, docs (README FR/EN, HISTORY), mise à jour du VPS par l'utilisateur, release v2.0 | §9.3 complet |

---

## 11. Décisions à prendre

| # | Question | Proposition |
|---|---|---|
| D1 | Client | **Décidé le 2026-11-22 : SIDBox2 (`~/Projet_C64/SIDBox2_C64`), tout en assembleur Kick Assembler.** Le lecteur v1.8 y est déjà porté à l'identique (étape 1 de SIDBox2) ; il sera adapté au §7 (appel en `$C000-$CFFF`, relais, contrat d'état) |
| D2 | `HISTART` | décidé à l'étape 5 ; la règle §7.1 impose au moins `$C000-$CFFF` pour le lecteur |
| D3 | Morceaux sans relais complet (2,3 %) | **Décidé le 2026-11-22 : joués en direct (son exact), relais partiels, vu-mètres incomplets, pas de correction de hauteur, champ `complet = 0`** (§5.5) |
| D4 | Horloge des délais réseau indépendante de l'IRQ | horloge TOD du CIA1 (fréquence à vérifier sur le C64U) ou comptage de lignes raster |
| D5 | Fronts de gate dans les relais | à faire si la place le permet (relais de contrôle de 10 octets) |
| D6 | Garde-fou | NMI du CIA2 armé par le client pendant `init`/`play` (incompatible avec un morceau qui utilise les NMI : à mesurer par `sidscan`) ou simple refus par l'analyse |
| D7 | Corrections v1.9 du 2026-11-22 (tremplins, pages 2-3) | **Décidé le 2026-11-22 : abandonnées, la v1.9 reste à l'état publié.** Patch gardé pour référence : `SIDBox2_C64/docs/v1.9-corrections-non-publiees.patch` (piège Oscar64 compris, voir `BaseC64/bugs.md`) |
| D8 | Durée d'émulation `N` | 10 000 appels (200 s) ; plus long si le temps de calcul le permet |
| D9 | Protéger les clients v1.9 restés en service | **Décidé le 2026-11-22 : oui**, par le serveur (§6.2, étape 5 bis) ; le client v1.9 n'est pas modifié |
