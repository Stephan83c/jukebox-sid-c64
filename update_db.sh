#!/usr/bin/env bash
# Met à jour la base des morceaux du serveur à partir d'une HVSC plus récente.
# Updates the server's tune database from a newer HVSC.   Doc : docs/UPDATE_DB.fr.md / docs/UPDATE_DB.md
#
# Usage : ./update_db.sh /chemin/vers/C64Music [--local-only] [--force] [--yes]
#   --local-only  réindexe sur ce PC seulement (rien n'est envoyé ni redémarré)
#   --force       redémarre le serveur même si un client est connecté
#   --yes         ne pose pas de question
# Réglages (variables d'environnement) :
#   SERVER=compte@serveur  SSH_PORT=22  REMOTE_DIR=jukebox  PORT=6474
#   MAX_ADDR=0xAEFF (= HISTART-1, voir docs)  SERVICE=jukebox  DB=./jukebox.db  MIN_RATIO=90 (% de l'ancienne base)
set -euo pipefail

SERVER=${SERVER:-compte@serveur}
SSH_PORT=${SSH_PORT:-22}
REMOTE_DIR=${REMOTE_DIR:-jukebox}
PORT=${PORT:-6474}
MAX_ADDR=${MAX_ADDR:-0xAEFF}
SERVICE=${SERVICE:-jukebox}
HERE=$(cd "$(dirname "$0")" && pwd)
DB=${DB:-$HERE/jukebox.db}
MIN_RATIO=${MIN_RATIO:-90}

LOCAL_ONLY=0; FORCE=0; YES=0; HVSC=""
for a in "$@"; do
    case $a in
        --local-only) LOCAL_ONLY=1 ;;
        --force) FORCE=1 ;;
        --yes) YES=1 ;;
        -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
        -*) echo "option inconnue : $a" >&2; exit 2 ;;
        *) HVSC=$a ;;
    esac
done
[ -n "$HVSC" ] || { sed -n '2,8p' "$0"; exit 2; }
[ -f "$HVSC/DOCUMENTS/Songlengths.md5" ] || { echo "$HVSC n'est pas un dossier C64Music (DOCUMENTS/Songlengths.md5 introuvable)" >&2; exit 1; }

count() { python3 -c "import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute('select sum(compatible) from tunes').fetchone()[0] or 0)" "$1"; }
ask() { [ "$YES" = 1 ] && return 0; read -r -p "$1 [o/N] " r; [[ $r =~ ^[oOyY] ]]; }

# --- 1. réindexation dans un fichier neuf (l'ancienne base n'est pas touchée)
NEW="$DB.new"
echo "== Réindexation de $HVSC (--max-addr $MAX_ADDR)"
python3 "$HERE/indexer.py" "$HVSC" -o "$NEW" --max-addr "$MAX_ADDR"
N_NEW=$(count "$NEW")
N_OLD=0; [ -f "$DB" ] && N_OLD=$(count "$DB")
echo "== Morceaux jouables : $N_NEW (avant : $N_OLD)"
if [ "$N_OLD" -gt 0 ] && [ $((N_NEW * 100)) -lt $((N_OLD * MIN_RATIO)) ]; then
    echo "ERREUR : la nouvelle base a moins de $MIN_RATIO % des morceaux de l'ancienne ; abandon (ancienne base intacte, $NEW conservé)." >&2
    exit 1
fi
[ "$N_NEW" -gt 0 ] || { echo "ERREUR : aucune ligne jouable." >&2; exit 1; }
[ -f "$DB" ] && cp -p "$DB" "$DB.bak"
mv "$NEW" "$DB"
echo "== Base locale mise à jour ($DB ; sauvegarde : $DB.bak)"
[ "$LOCAL_ONLY" = 1 ] && { echo "== --local-only : rien envoyé."; exit 0; }

# --- 2. envoi (une seule connexion SSH réutilisée : un seul mot de passe)
CTL=$(mktemp -u /tmp/updb-ssh.XXXXXX)
SSH=(ssh -p "$SSH_PORT" -o ControlMaster=auto -o ControlPath="$CTL" -o ControlPersist=120)
trap '"${SSH[@]}" -O exit "$SERVER" 2>/dev/null || true' EXIT
"${SSH[@]}" "$SERVER" true
ask "Envoyer C64Music et la base sur $SERVER:$REMOTE_DIR ('--delete' sur C64Music) ?" || { echo "Annulé (base locale déjà mise à jour)."; exit 1; }
echo "== Envoi de C64Music"
rsync -az --delete --info=stats1 -e "${SSH[*]}" "${HVSC%/}/" "$SERVER:$REMOTE_DIR/C64Music/"
echo "== Envoi de la base (en .new, renommée juste avant le redémarrage)"
rsync -az -e "${SSH[*]}" "$DB" "$SERVER:$REMOTE_DIR/jukebox.db.new"

# --- 3. attendre qu'aucun C64 ne soit connecté, puis redémarrer
echo "== Clients connectés ?"
for i in $(seq 1 30); do
    n=$("${SSH[@]}" "$SERVER" "ss -Htn state established '( sport = :$PORT )' | wc -l")
    [ "$n" -eq 0 ] && break
    echo "   $n connexion(s) en cours, attente ($i/30)..."; sleep 2
done
if [ "$n" -ne 0 ] && [ "$FORCE" != 1 ]; then
    echo "ERREUR : des clients sont encore connectés ; relancer plus tard ou avec --force (la base .new est déjà sur le serveur)." >&2
    exit 1
fi
echo "== Remplacement de la base et redémarrage"
"${SSH[@]}" "$SERVER" "cd $REMOTE_DIR && cp -p jukebox.db jukebox.db.bak 2>/dev/null; mv jukebox.db.new jukebox.db && systemctl --user restart $SERVICE && sleep 2 && systemctl --user is-active $SERVICE"

# --- 4. test
echo "== Test"
HOST=${SERVER#*@}
python3 "$HERE/client_pc.py" --host "$HOST" --port "$PORT" --out "$(mktemp -d)" | head -3
echo "== Terminé."
