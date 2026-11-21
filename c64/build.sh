#!/bin/bash
# SID Jukebox C64
# Copyright (C) 2026 Stephan83c
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version. It is
# distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.
# Construit le client C64 : lecteur en assembleur (ca65/ld65) + partie C (Oscar64). Appelé par le Makefile.
# Usage : ./build.sh [demo]   Variables : OSC, OSCINC, VERSION, HISTART, SERVEUR_IP, SERVEUR_PORT, MAX_SECS, VIS
set -e
cd "$(dirname "$0")"
mkdir -p build
OSC=${OSC:-oscar64}
OSCINC=${OSCINC:-$(dirname "$(command -v "$OSC")")/../include}
VERSION=${VERSION:-1.8}
IP=${SERVEUR_IP:-boombass.net}; PORT=${SERVEUR_PORT:-6474}; MAXS=${MAX_SECS:-1000}; VIS=${VIS:-1}
if [ "$1" = demo ]; then
  RUN=$((0x9800)); DEF="-DDEMO"; OUT=build/demo.prg     # le morceau intégré (demo.bin) occupe le bas de la mémoire
else
  RUN=$((${HISTART:-0xA700})); DEF=""; OUT=build/jukebox.prg
fi

# 1. partie assembleur, liée à l'adresse d'exécution (la version s'affiche en haut à droite de l'écran de lecture)
echo ".define VERSION_TXT \"$VERSION\"" > build/version.inc
for f in play logo scroll; do ca65 -t c64 -I build $f.s -o build/$f.o; done
ld65 -C asm.cfg -D __HISTART__=$RUN -o build/asm.bin -Ln build/asm.lbl build/play.o build/logo.o build/scroll.o

# 2. adresses des variables partagées avec le C
{
  echo "/* généré par build.sh */"
  echo "#define ASMSIZE $(stat -c %s build/asm.bin)"
  for s in init_addr:unsigned play_addr:unsigned frames_max:unsigned song_nr:"unsigned char" fps:"unsigned char" vis_on:"unsigned char" scr_ok:"unsigned char" scr_ptr:"unsigned char *"; do
    n=${s%%:*}; t=${s#*:}; a=$(grep "\._$n\$" build/asm.lbl | awk '{print $2}')
    echo "#define $n (*($t *)0x$a)"
  done
  echo "#define PLAY_RUN_ADDR 0x$(grep '\._play_run$' build/asm.lbl | awk '{print $2}')"
} > build/asmsyms.h

# 3. partie C : deux passes, la première donne la taille exacte de l'image à recopier (IMGEND)
LIMITE=$(printf '%04X' $((RUN - 1)))
IMG=0x2000
for pass in 1 2; do
  $OSC -Os -tf=prg -i=$OSCINC -i=build -i=. -o=$OUT -DRUN=$RUN -DIMGEND=$IMG $DEF \
     -DSERVEUR_IP="\"$IP\"" -DSERVEUR_PORT=$PORT -DMAX_SECS=$MAXS -DVIS_DEFAULT=$VIS -DVERSION="\"$VERSION\"" -DLIMITE="\"$LIMITE\"" client.c > build/oscar.log 2>&1 \
     || { cat build/oscar.log; exit 1; }
  if [ $pass = 1 ]; then
    IMG=$(awk '/^regions/{f=1} f && /, main$/{gsub(",","",$5); print "0x"$5; exit}' ${OUT%.prg}.map)
  fi
done
ls -l $OUT
printf 'mémoire : image $%04X-$%04X, pile jusqu'"'"'à $D000\n' $RUN $((RUN + IMG - 0x0900))
