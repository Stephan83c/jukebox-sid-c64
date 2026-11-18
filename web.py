#!/usr/bin/env python3
"""Page web pour changer le texte du scroller du jukebox.

Règles : majuscules (forcées), alphabet du C64 (A-Z * . , ! ? - espace), 150 caractères au plus,
une seule modification toutes les 3 minutes pour tout le monde (pause globale). Le texte est écrit dans
scroll_user.txt ; server.py l'utilise pendant 1 heure, puis retombe sur scroll.txt (message par défaut).
L'heure du dernier changement est la date du fichier : rien à mémoriser, ça survit aux redémarrages.

Sécurité : bibliothèque standard seule, aucun accès à la base ni aux morceaux, corps de requête limité,
champ piège + jeton signé (anti-robots), débit limité par IP, liste de mots interdits (banned_words.txt),
IP bloquées (banned_ips.txt), journal de tous les changements (web_changes.log).
Derrière un proxy, --trust-proxy fait lire X-Forwarded-For ; sinon l'IP est celle de la connexion.
"""
import argparse
import hashlib
import hmac
import html
import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from server import SCROLL_ALPHABET, SCROLL_MAX

log = logging.getLogger("jukeweb")
HERE = Path(__file__).resolve().parent
MIN_LEN = 3
MAX_BODY = 1024
TOKEN_MIN_AGE = 3          # secondes : un humain met plus de temps qu'un robot à remplir le formulaire
TOKEN_MAX_AGE = 3600
RATE_WINDOW, RATE_MAX = 60, 30      # requêtes par IP et par minute

ALLOWED_TXT = "A-Z * . , ! ? - et espace"


class State:
    def __init__(self, a):
        self.a = a
        self.lock = threading.Lock()
        self.secret = secrets.token_bytes(32)
        self.hits: dict[str, list[float]] = {}

    # --- fichiers -------------------------------------------------------------------------
    def last_change(self) -> float | None:
        try:
            return self.a.user_file.stat().st_mtime
        except OSError:
            return None

    def current(self) -> tuple[str, bool]:
        """(texte affiché, vient-il d'un utilisateur et encore valable ?)"""
        t = self.last_change()
        src = self.a.user_file if t and time.time() - t < self.a.ttl else self.a.default_file
        try:
            return src.read_text(encoding="utf-8", errors="replace").strip(), src == self.a.user_file
        except OSError:
            return "", False

    def words(self) -> list[str]:
        try:
            return [w for w in (l.strip().upper() for l in
                    (HERE / "banned_words.txt").read_text(encoding="utf-8").splitlines())
                    if w and not w.startswith("#")]
        except OSError:
            return []

    def banned_ip(self, ip: str) -> bool:
        try:
            return ip in {l.split("#")[0].strip() for l in (HERE / "banned_ips.txt").read_text().splitlines()}
        except OSError:
            return False

    # --- anti-robots ----------------------------------------------------------------------
    def rate_ok(self, ip: str) -> bool:
        now = time.time()
        with self.lock:
            h = [t for t in self.hits.get(ip, []) if now - t < RATE_WINDOW]
            h.append(now)
            self.hits[ip] = h
            if len(self.hits) > 5000:       # ne pas grossir sans limite
                self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < RATE_WINDOW}
            return len(h) <= RATE_MAX

    def token(self) -> str:
        ts = str(int(time.time()))
        return ts + "." + hmac.new(self.secret, ts.encode(), hashlib.sha256).hexdigest()[:32]

    def token_ok(self, tok: str) -> bool:
        ts, _, mac = tok.partition(".")
        if not ts.isdigit() or not hmac.compare_digest(
                mac, hmac.new(self.secret, ts.encode(), hashlib.sha256).hexdigest()[:32]):
            return False
        return TOKEN_MIN_AGE <= time.time() - int(ts) <= TOKEN_MAX_AGE


def normalize(raw: str) -> str:
    raw = unicodedata.normalize("NFKD", raw).upper()
    raw = "".join(c for c in raw if not unicodedata.combining(c))     # é -> E
    return " ".join(raw.split())


def check_text(st: State, raw: str) -> tuple[str | None, str]:
    """(texte propre, message d'erreur)"""
    txt = normalize(raw)
    bad = sorted({c for c in txt if c not in SCROLL_ALPHABET})
    if bad:
        return None, "Caractères non autorisés : %s. Autorisés : %s." % (" ".join(bad)[:30], ALLOWED_TXT)
    if len(txt) < MIN_LEN:
        return None, "Texte trop court (%d caractères au moins)." % MIN_LEN
    if len(txt) > SCROLL_MAX:
        return None, "Texte trop long : %d caractères, %d au plus." % (len(txt), SCROLL_MAX)
    letters = re.sub(r"[^A-Z]", "", txt)
    if any(w in letters for w in map(lambda w: re.sub(r"[^A-Z]", "", w), st.words())):
        return None, "Ce texte contient un mot interdit."
    return txt, ""


def write_atomic(path: Path, text: str):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".scroll.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)          # un lecteur voit l'ancien fichier ou le nouveau, jamais un demi-fichier
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def fmt(s: float) -> str:
    s = int(s + 0.999)
    return "%d min %02d s" % (s // 60, s % 60) if s >= 60 else "%d s" % s


PAGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jukebox SID - scroller</title>
<style>
:root{{color-scheme:dark;--bg:#40318d;--fg:#b8b8ff;--ac:#ffd34d;--bx:#352879}}
body{{background:var(--bg);color:var(--fg);font:16px/1.5 ui-monospace,Menlo,Consolas,monospace;margin:0;padding:16px}}
main{{max-width:720px;margin:0 auto}} h1{{color:var(--ac);font-size:1.3rem}}
.cur{{background:#000;color:#7bd88f;padding:12px;word-break:break-word;border:2px solid var(--fg)}}
textarea{{width:100%;box-sizing:border-box;font:inherit;text-transform:uppercase;background:var(--bx);color:#fff;
border:2px solid var(--fg);padding:8px}}
button{{font:inherit;background:var(--ac);color:#000;border:0;padding:8px 16px;cursor:pointer}}
button:disabled{{opacity:.4;cursor:not-allowed}}
.msg{{padding:8px;margin:12px 0}} .ok{{background:#1b5e20;color:#fff}} .err{{background:#7f1d1d;color:#fff}}
small{{opacity:.85}} .hp{{position:absolute;left:-9999px}}
</style></head><body><main>
<h1>JUKEBOX SID : le scroller</h1>
<p>Texte actuel ({source}) :</p>
<p class="cur">{current}</p>
{message}
<form method="post" action="/">
<p><label for="t">Nouveau texte : majuscules, {allowed}, {max} caractères au plus.</label></p>
<textarea id="t" name="t" rows="3" maxlength="{max}" autocomplete="off" required>{value}</textarea>
<p><small><span id="n">0</span> / {max}</small></p>
<input type="hidden" name="k" value="{token}">
<input class="hp" type="text" name="site" tabindex="-1" autocomplete="off" aria-hidden="true">
<button id="b" {disabled}>Envoyer</button> <small>{wait}</small>
</form>
<p><small>Une modification toutes les 3 minutes pour tout le monde. Sans nouveau texte pendant 1 heure, le
message par défaut revient. Le nouveau texte apparaît à partir du morceau suivant, pas tout de suite.</small></p>
</main>
<script>
var t=document.getElementById('t'),n=document.getElementById('n');
function up(){{var p=t.selectionStart;t.value=t.value.toUpperCase();t.setSelectionRange(p,p);n.textContent=t.value.length}}
t.addEventListener('input',up);up();
</script></body></html>
"""


def render(st: State, message: str = "", ok: bool = False, value: str = "") -> bytes:
    cur, from_user = st.current()
    last = st.last_change()
    wait_s = max(0.0, st.a.cooldown - (time.time() - last)) if last else 0.0
    wait = "Prochain changement possible dans %s." % fmt(wait_s) if wait_s else ""
    if from_user and last:
        src = "écrit par un visiteur, retour au message par défaut dans %s" % fmt(st.a.ttl - (time.time() - last))
    else:
        src = "message par défaut"
    msg = '<div class="msg %s" role="status">%s</div>' % ("ok" if ok else "err", html.escape(message)) if message else ""
    return PAGE.format(
        source=html.escape(src), current=html.escape(cur) or "&nbsp;", message=msg, max=SCROLL_MAX,
        allowed=html.escape(ALLOWED_TXT), value=html.escape(value), token=st.token(),
        disabled="disabled" if wait_s else "", wait=html.escape(wait)).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "jukeweb"
    sys_version = ""
    timeout = 10
    st: State

    def log_message(self, fmt_, *args):
        log.info("%s %s", self.ip(), fmt_ % args)

    def ip(self) -> str:
        if self.st.a.trust_proxy:
            xff = self.headers.get("X-Forwarded-For", "")
            if xff:
                return xff.split(",")[-1].strip()[:64]       # le dernier ajout est celui de notre proxy
        return self.client_address[0]

    def reply(self, code: int, body: bytes, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def gate(self) -> bool:
        ip = self.ip()
        if self.st.banned_ip(ip):
            self.reply(403, b"interdit", "text/plain; charset=utf-8")
            return False
        if not self.st.rate_ok(ip):
            self.reply(429, b"trop de requetes", "text/plain; charset=utf-8")
            return False
        return True

    def do_GET(self):
        if not self.gate():
            return
        if self.path.split("?")[0] != "/":
            return self.reply(404, b"introuvable", "text/plain; charset=utf-8")
        self.reply(200, render(self.st))

    def do_POST(self):
        if not self.gate():
            return
        if self.path != "/":
            return self.reply(404, b"introuvable", "text/plain; charset=utf-8")
        try:
            n = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self.reply(411, b"longueur requise", "text/plain; charset=utf-8")
        if not 0 <= n <= MAX_BODY:
            return self.reply(413, b"trop gros", "text/plain; charset=utf-8")
        form = parse_qs(self.rfile.read(n).decode("utf-8", "replace"), keep_blank_values=True)
        get = lambda k: (form.get(k) or [""])[0]
        st, ip = self.st, self.ip()
        if get("site") or not st.token_ok(get("k")):
            log.info("%s refusé (robot ou formulaire trop rapide/périmé)", ip)
            return self.reply(200, render(st, "Formulaire périmé ou envoyé trop vite : réessaie."))
        txt, err = check_text(st, get("t"))
        if txt is None:
            return self.reply(200, render(st, err, value=get("t")[:SCROLL_MAX * 2]))
        with st.lock:                       # la pause est vérifiée et armée sous le même verrou
            last = st.last_change()
            wait = st.a.cooldown - (time.time() - last) if last else 0
            if wait > 0:
                return self.reply(200, render(st, "Trop tôt : encore %s avant le prochain changement." % fmt(wait),
                                              value=txt))
            write_atomic(st.a.user_file, txt)
        with open(st.a.history, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "ip": ip, "text": txt}) + "\n")
        log.info("%s nouveau texte : %s", ip, txt)
        self.reply(200, render(st, "C'est enregistré. Le texte apparaîtra au prochain morceau.", ok=True))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user-file", dest="user_file", type=Path, default=HERE / "scroll_user.txt")
    ap.add_argument("--default-file", dest="default_file", type=Path, default=HERE / "scroll.txt")
    ap.add_argument("--history", type=Path, default=HERE / "web_changes.log")
    ap.add_argument("--cooldown", type=int, default=180, help="secondes entre deux changements (global)")
    ap.add_argument("--ttl", type=int, default=3600, help="secondes avant retour au message par défaut")
    ap.add_argument("--trust-proxy", action="store_true")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=6475)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    Handler.st = State(a)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    srv.daemon_threads = True
    log.info("page du scroller sur http://%s:%d/", a.host, a.port)
    srv.serve_forever()


if __name__ == "__main__":
    main()
