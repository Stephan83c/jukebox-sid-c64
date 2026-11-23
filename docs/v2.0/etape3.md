# Étape 3 de SPEC-v2.md : lecteur v2.0 seul, sans réseau (2026-11-22)

**Fait** : `src/player.asm` réécrit sur la base du portage de la v1.8 (étape 1) avec les ajouts de la v1.9 (correction de hauteur,
norme affichée) et le contrat de la v2.0 (`~/Projet_C64/SidJukebox_C64/jukebox/SPEC-v2.md` §7) :

- morceau appelé avec `$01 = $36` (plus de capture) ; après chaque appel, copie du bloc de relais -> `shadow` (vu-mètres) et,
  si `complet = 1` et normes différentes, réécriture des 6 registres de fréquence corrigés ;
- vitesse : accumulateur de la v1.8 inchangé (le morceau est appelé à sa cadence, 50 ou 60, quelle que soit la machine) ;
- contrat d'état §7.2 : page zéro en `$D200`, pages 2-3 en `$D800-$D9FF` (RAM sous les E/S), VIC, CIA 1 (valeurs IOINIT),
  CIA 2, `$02A6` à la norme du morceau, pile ;
- entre deux appels : `$01 = $35`, IRQ par `$FFFE` ; IRQ pendant un appel acquittée et ignorée ; NMI ignorées ;
- tout le lecteur en `$C000-$CF34` (code, données, variables ; contrôlé à l'assemblage) ; 3 722 octets d'image.

Démo : `tools/mktune.py ID` (fabrication du serveur, `server.tune3`) puis `make`. Interface : `_relay`, `_complet` en plus de la v1.8.

## Banc VICE (`tools/banc.py`, SPEC-v2.md §9.2)

Trois passages par morceau (VICE accéléré, moniteur distant, pilote son `dump` qui journalise chaque écriture SID) :
R (relais, norme du morceau), D (sans relais), X (relais, autre norme). Contrôles : retour à la durée prévue, KERNAL vivant
ensuite, état §7.2 identique avant/après, pile, norme mesurée, écritures SID R = D = X (corrections retirées), vitesse en X
(images/appels = 6/5 ou 5/6), une correction de hauteur juste après init et après chaque appel quand `complet = 1`.

| Morceaux | Résultat (30 s chacun) |
|---|---|
| 13636, 6301, 28342, 31049, 27436, 42363, 114, 4102 | verts (Adidas : `$01 = $37` laissé, sans relais ; Dark Ages : relais partiels) |
| 24668, 22618, 3663 (écartés à la main, acceptés par l'analyse) | verts |
| 44694 *El Joe* | refusé par l'analyse (`scan_playlong`) : non testé |

Deux défauts du banc trouvés en route (voir `BaseC64/bugs.md`) : les vecteurs `$FFFA-$FFFF` écrasés par le jeu de caractères
(défaut du lecteur, corrigé) et le programme d'appel du banc écrasé par un morceau chargé en `$0800` (déplacé en `$C000`).

**Non vérifié** : le son à l'oreille et l'écran sur l'Ultimate (étape 4, avec le réseau) ; garde-fou §7.8 (étape 4).
