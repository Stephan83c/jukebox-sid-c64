# Étape 1 : portage du lecteur (2026-11-21)

**Fait** : `ref/v1.8/play.s`, `logo.s`, `scroll.s` portés en Kick Assembler (`src/player.asm`, `logo.asm`, `scroll.asm`,
`player_bss.asm`), avec un programme principal de démonstration (`src/main.asm`) qui joue un morceau intégré, sans réseau.

## Méthode

Conversion mécanique du code ca65 (script jetable), puis relecture : commentaires `;` en `//`, étiquettes locales `@x` en `l_x`
(chaque routine, entre deux étiquettes globales, devient un bloc `{ }`), `a:$0000` en `lda.abs`, `.res` en `.fill` dans un segment
`virtual` (BSS sans octets dans le fichier), `scrcode` en `.encoding "screencode_upper"` + `.text`, macro `bar` déplacée en tête
(Kick ne définit pas de macro dans un bloc). L'ordre des données est celui de ld65 : code, RODATA du lecteur, logo, scroller, puis BSS.

## Vérifications (critères du SPEC §9)

| Test | Résultat |
|---|---|
| Code assemblé comparé à `asm.bin` de la v1.8 (version « 1.8 », liée en `$AF00`) | **identique octet pour octet : 3 223 octets** (`$AF00-$BB96`), BSS `$BB97-$BD2D` aux mêmes adresses |
| Image recopiée en `$AF00` après démarrage, comparée au fichier | 8 octets différents sur 3 227 : les 4 opérandes modifiés par le code (`init`, `play`, 2 fois chacun), normal |
| Cadence de la machine mesurée par le lecteur (`mfps`) | 50 (PAL), comme la v1.8 |
| Effets (VICE, 5 relevés) | les hauteurs de vu-mètres (`vh`) varient, le temps avance (`00:37`), logo et scroller animés, version affichée |
| Taille | lecteur 3 223 octets avec la version « 1.8 » (3 227 avec « 2.0-DEV ») : **identique à la v1.8** (c'est le même code) |

**Test sur l'Ultimate (2026-11-21, `make deploy`, lecture de la mémoire par l'API REST)** : image du lecteur en `$AF00` identique au fichier (8 octets d'opérandes modifiés, comme dans VICE) ; `mfps` = 50 (PAL) ; sur 6 relevés espacés d'environ 1 s, `frames` avance de 53 par relevé et `tframes` le suit (cadence du morceau tenue), les hauteurs de vu-mètres `vh` varient. **Non vérifié** : le son à l'oreille et l'aspect de l'écran de lecture (la mémoire sous le KERNAL n'est pas lisible par l'API).

## Ce que ça n'apporte pas encore

Pas de gain de mémoire : la partie assembleur de la v1.8 faisait déjà 3 223 octets. Le gain attendu est dans la partie C (réseau, écrans,
recherche, touches : environ 2 Ko), à réécrire aux étapes 2 à 4.

## Disposition du fichier de démonstration (dev)

`$0801` BASIC · `$0810` programme (`main.asm`, 452 octets) · `$3000` image du lecteur (liée en `$AF00`, recopiée au démarrage) ·
`$4000` morceau (recopié à son adresse). Le fichier fait 17 921 octets à cause des trous ; ce n'est pas la taille finale.
`tools/mktune.py ID` choisit le morceau (par défaut : 51972, Thrust).
