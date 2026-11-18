# Mettre à jour la base des morceaux (`jukebox.db`)

🇫🇷 Français · [🇬🇧 English](UPDATE_DB.md)

La base se reconstruit en entier avec `indexer.py` à partir d'une HVSC plus récente (le script supprime
l'ancien fichier de sortie). Les identifiants de morceaux changent à chaque fois ; sans importance, le C64
demande toujours un morceau au hasard.

## Raccourci : `update_db.sh`

```sh
./update_db.sh /chemin/vers/C64Music            # réindexe, envoie, redémarre, teste
./update_db.sh /chemin/vers/C64Music --local-only   # réindexe seulement (rien n'est envoyé)
```

Il fait les étapes 2 à 4 ci-dessous, avec des garde-fous : la base est construite dans un fichier neuf et
n'est adoptée que si elle garde au moins 90 % des morceaux de l'ancienne (sauvegarde `jukebox.db.bak`) ; il
attend qu'aucun C64 ne soit connecté avant de redémarrer (`--force` pour passer outre) ; il demande
confirmation avant l'envoi (`--yes` pour l'éviter) et teste le serveur à la fin. Réglages par variables
d'environnement (`SERVER`, `SSH_PORT`, `REMOTE_DIR`, `PORT`, `MAX_ADDR`…), voir l'en-tête du script.
Les étapes à la main restent valables.

## 1. Récupérer la nouvelle HVSC

Version complète sur <https://hvsc.c64.org/> (la base actuelle vient de la #85). Remplacer tout le dossier
`C64Music` est plus sûr que d'appliquer les archives de mise à jour. `DOCUMENTS/Songlengths.md5` fait partie
de l'archive : l'indexeur s'en sert pour les durées.

## 2. Réindexer (sur le PC)

```sh
cp jukebox.db jukebox.db.bak                      # filet de sécurité
python3 indexer.py /chemin/vers/C64Music -o jukebox.db --max-addr 0xA8FF
```

`--max-addr` doit rester égal à `HISTART - 1` (`c64/Makefile`) et à `MEM_HAUT` (`c64/main.c`) : au-dessus,
c'est la mémoire du client C64. Le script affiche le nombre de morceaux retenus et les raisons de rejet
(RSID, trop gros, multi-SID, cadencé par un timer CIA…). Avec la HVSC #85 : environ 44 555 morceaux jouables.

## 3. Envoyer sur le serveur

`C64Music/` et `jukebox.db` ne sont pas dans git : copie manuelle. Les deux doivent correspondre (la base
contient des chemins vers les fichiers de `C64Music`).

```sh
rsync -az --delete -e "ssh -p 22" /chemin/vers/C64Music <compte>@<serveur>:jukebox/
rsync -az -e "ssh -p 22" jukebox.db <compte>@<serveur>:jukebox/
```

`--delete` supprime sur le serveur les fichiers qui ne sont plus dans la nouvelle HVSC.

## 4. Redémarrer le serveur

Il garde la base ouverte : un redémarrage est nécessaire.

```sh
systemctl --user restart jukebox
```

Les connexions durent environ une seconde par morceau ; vérifier tout de même dans le journal
(`journalctl --user -u jukebox -n 5`) qu'aucun C64 n'est connecté. Tester ensuite :

```sh
python3 client_pc.py --host <serveur> --port 6474
```

## Si le client C64 change de taille

Un client plus gros monte plus haut en mémoire : il faut alors baisser `HISTART` (`c64/Makefile`),
`MEM_HAUT` (`c64/main.c`) et `--max-addr` ensemble, puis réindexer ; le catalogue perd quelques morceaux
(voir le tableau de `HISTORY.md`).

## Droits d'auteur

La HVSC est à usage privé (`DOCUMENTS/Disclaimer.txt`) ; héberger un serveur public reste à régler avec
l'équipe HVSC ou les compositeurs.
