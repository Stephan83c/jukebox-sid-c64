#!/usr/bin/env bash
# SID Jukebox C64
# Copyright (C) 2026 Stephan83c
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version. It is
# distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.
# Liste les IP qui se connectent au jukebox (lecture seule, rien n'est écrit).
# Lists the IPs connecting to the jukebox (read-only, nothing is written).
#
# Usage : ./ips.sh [--web] [fichier_journal]
#   --web           ajoute les IP qui ont modifié le scroller (data/web_changes.log)
#   fichier_journal lit ce fichier (ex. srv.log) au lieu de journalctl --user -u jukebox
set -eu
cd "$(dirname "$0")"

WEB=0
SRC=""
for a in "$@"; do
    case "$a" in
        --web) WEB=1 ;;
        -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
        *) SRC="$a" ;;
    esac
done

PORT=6474
echo "== Connectés maintenant / Connected now (port $PORT) =="
if command -v ss >/dev/null; then
    ss -tn "sport = :$PORT" | awk 'NR>1 {a=$NF; sub(/:[0-9]+$/,"",a); gsub(/[\[\]]/,"",a); n[a]++}
        END {t=0; for (i in n) {printf "  %s (%d)\n", i, n[i]; t++}; if (!t) print "  aucun / none"}'
else
    echo "  (ss absent)"
fi
echo

echo "== Historique / History =="
TMP=$(mktemp); trap 'rm -f "$TMP"' EXIT
if [ -n "$SRC" ]; then cat "$SRC"; else journalctl --user -u jukebox --no-pager -o cat; fi |
awk '
    # lignes : "2026-11-21 09:40:12,345 connexion (\x27IP\x27, port)" ou "... (\x27IP\x27, port) RANDOM ..."
    match($0, /^[0-9-]+ [0-9:]+/) {
        t = substr($0, RSTART, RLENGTH)
        if (!min || t < min) min = t
        if (t > max) max = t
    }
    /connexion \(\x27/ && !/déconnexion/ || /^[0-9-]+ [0-9:,]+ \(\x27[^\x27]+\x27, [0-9]+\) RANDOM/ {
        if (!match($0, /\(\x27[^\x27]+\x27/)) next
        ip = substr($0, RSTART + 2, RLENGTH - 3)
        if ($0 ~ /\) RANDOM/) songs[ip]++
        else {
            conn[ip]++
            if (!(ip in first)) first[ip] = t
            last[ip] = t
        }
    }
    END {
        if (!min) { print "  journal vide / empty log"; exit }
        for (ip in conn) printf "%-40s %10d  %-19s  %-19s  %d\n", ip, conn[ip], first[ip], last[ip], songs[ip]
        total = 0; for (ip in conn) total++
        printf "#%d|%s|%s\n", total, min, max
    }' > "$TMP"
if [ -s "$TMP" ] && ! grep -q '^journal vide' "$TMP"; then
    printf "%-40s %10s  %-19s  %-19s  %s\n" IP connexions "première/first" "dernière/last" "morceaux/tunes"
    grep -v '^#' "$TMP" | sort -k2,2nr
    IFS='|' read -r tot dmin dmax < <(grep '^#' "$TMP")
    printf "\nTotal : %s IP, journal du %s au %s\n" "${tot#\#}" "$dmin" "$dmax"
else
    cat "$TMP"
fi

if [ "$WEB" = 1 ]; then
    echo
    echo "== Modifications du scroller / Scroller changes (web) =="
    F=data/web_changes.log
    if [ -s "$F" ]; then
        python3 -I - "$F" <<'PY'
import json, sys, collections
n = collections.Counter(); last = {}
for l in open(sys.argv[1], encoding="utf-8"):
    try: d = json.loads(l)
    except ValueError: continue
    n[d["ip"]] += 1; last[d["ip"]] = d["t"]
for ip, c in n.most_common():
    print(f"  {ip:40s} {c:4d} modif.  dernière : {last[ip]}")
PY
    else
        echo "  aucune / none"
    fi
fi
