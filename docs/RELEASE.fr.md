# Publier une nouvelle version du client

Procédure à suivre dans cet ordre. Les commandes `make` se lancent dans `c64/`.

1. **Version** : la changer partout *avant* de compiler : `c64/Makefile` (`VERSION`), `c64/build.sh` (valeur par défaut),
   titre de `c64/README.txt`, et une entrée en tête de `HISTORY.md`.
2. **Scroller** : `scroll.txt` et `d_scroll` dans `c64/main.c` (`Vx.y IS AVAILABLE`), en gardant la même longueur de
   texte : le client est plein.
3. **Documentation** : si une touche ou un comportement change, corriger `c64/README.txt`, `README.md` et
   `README.fr.md` (tableau des touches).
4. **Compiler** : `make OSC=~/oscar64/bin/oscar64`, puis vérifier la version :
   `strings build/jukebox.prg | grep "JUKEBOX V"`.
5. **Déployer sur le C64 Ultimate** : `make deploy`, seulement *après* l'étape 1, sinon l'écran affiche l'ancienne
   version. Contrôler la version en haut à droite de l'écran de lecture.
6. **Commit, tag, push** : `git commit`, `git tag vX.Y`, `git push origin main vX.Y`, une fois tout prêt. Ne pas
   déplacer le tag après coup.
7. **Release GitHub** : `gh release create vX.Y` (notes en français et en anglais) *d'abord*, puis
   `make release TAG=vX.Y` qui joint le zip. Vérifier avec `cmp` que le `jukebox-sid.prg` du zip est identique à
   `c64/build/jukebox.prg`, celui qui a été déployé.
8. **Serveur public** : `git pull`. Le `scroll.txt` du serveur peut différer de celui du dépôt : le vérifier avant de
   l'écraser. Un tag déplacé n'est récupéré qu'avec `git fetch --tags --force`.
9. **Issues** : commenter avec le lien de la release, et fermer celles qui sont corrigées.
