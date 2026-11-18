#!/usr/bin/env python3
"""Page web pour changer le texte du scroller du jukebox.

Règles : majuscules (forcées), alphabet du C64 (A-Z * . , ! ? - espace), 150 caractères au plus,
une seule modification toutes les 3 minutes pour tout le monde (pause globale) et toutes les 10 minutes par IP. Le texte est écrit dans
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

from server import SCROLL_ALPHABET, SCROLL_MAX, ipkey

log = logging.getLogger("jukeweb")
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"     # seul dossier où le service web a le droit d'écrire
MIN_LEN = 3
MAX_BODY = 1024
TOKEN_MIN_AGE = 3          # secondes : un humain met plus de temps qu'un robot à remplir le formulaire
TOKEN_MAX_AGE = 3600
RATE_WINDOW, RATE_MAX = 60, 30      # requêtes par IP et par minute
MAX_THREADS = 64                    # connexions traitées en même temps ; au-delà, refus immédiat

ALLOWED_TXT = "A-Z * . , ! ? - et espace"


class State:
    def __init__(self, a):
        self.a = a
        self.lock = threading.Lock()
        self.secret = secrets.token_bytes(32)
        self.hits: dict[str, list[float]] = {}
        self.ip_last: dict[str, float] = {}      # clé d'IP -> heure de son dernier changement réussi

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
            ban = {l.split("#")[0].strip() for l in (HERE / "banned_ips.txt").read_text().splitlines()}
            return ip in ban or ipkey(ip) in ban
        except OSError:
            return False

    # --- anti-robots ----------------------------------------------------------------------
    def ip_wait(self, ip: str) -> float:
        """Secondes à attendre pour cette IP (pause par IP, en plus de la pause globale). À appeler sous verrou ou en lecture seule."""
        t = self.ip_last.get(ipkey(ip))
        return max(0.0, self.a.ip_cooldown - (time.time() - t)) if t else 0.0

    def mark(self, ip: str):
        now = time.time()
        self.ip_last[ipkey(ip)] = now
        if len(self.ip_last) > 5000:
            self.ip_last = {k: t for k, t in self.ip_last.items() if now - t < self.a.ip_cooldown}

    def rate_ok(self, ip: str) -> bool:
        ip = ipkey(ip)
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


RAINBOW = ["#d9548f", "#d98a3d", "#f2e24b", "#8be36b", "#63d9c9", "#7b7cf2", "#4a4ad9", "#b44fd6"]

PAGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JUKEBOX SID - SCROLLER</title>
<style>
:root{color-scheme:dark;--bg:#000;--lb:#8b8bff;--yl:#f2f27a;--rd:#d9548f;--gr:#8be36b}
*{box-sizing:border-box}
body{background:#0b0b1e;color:var(--lb);margin:0;padding:12px;min-height:100vh;
font:18px/1.35 "C64 Pro Mono","Press Start 2P",ui-monospace,Menlo,Consolas,"DejaVu Sans Mono",monospace;
text-transform:uppercase;letter-spacing:.06em}
main{max-width:760px;margin:0 auto;background:var(--bg);padding:28px 24px 24px;
border:10px solid #3a3aa8;border-radius:6px}
h1{font-size:2.1rem;text-align:center;margin:4px 0 26px;letter-spacing:.35em;font-weight:700}
.row{margin:2px 0}.lab{color:var(--lb)}.val{color:var(--yl)}
.sp{height:22px}
.bar{height:5px;margin:7px 0;background:linear-gradient(90deg,#d9548f 0 14%,#d98a3d 14% 28%,#f2e24b 28% 42%,
#8be36b 42% 56%,#63d9c9 56% 70%,#7b7cf2 70% 84%,#4a4ad9 84% 100%)}
.scr{overflow:hidden;white-space:pre;margin:22px 0;font-size:1.5rem;font-weight:700;border-top:2px solid #1d1d55;
border-bottom:2px solid #1d1d55;padding:8px 0}
.scr span.run{display:inline-block;padding-left:100%;animation:run var(--d) linear infinite;animation-delay:calc(var(--d) * -.12)}
@keyframes run{to{transform:translateX(-100%)}}
@media (prefers-reduced-motion:reduce){.scr{white-space:normal}.scr span.run{padding:0;animation:none}}
textarea{width:100%;font:inherit;text-transform:uppercase;letter-spacing:inherit;background:#000;color:var(--yl);
border:2px solid var(--lb);padding:8px;border-radius:0;resize:vertical;caret-color:var(--gr)}
textarea:focus{outline:2px solid var(--yl);outline-offset:2px}
button{font:inherit;letter-spacing:inherit;text-transform:uppercase;background:var(--lb);color:#000;border:0;
padding:8px 18px;cursor:pointer}
button:hover:not(:disabled){background:var(--yl)}
button:disabled{opacity:.35;cursor:not-allowed}
.msg{padding:8px 10px;margin:14px 0;color:#000}.ok{background:var(--gr)}.err{background:var(--rd)}
.help{color:#6a6ad0;font-size:.8rem;line-height:1.6;text-transform:none;letter-spacing:.02em}
.keys{margin-top:24px;color:#9a9aa8}.hp{position:absolute;left:-9999px}
.cnt{color:var(--yl)}
@media (max-width:520px){body{font-size:14px;padding:6px}main{padding:18px 12px;border-width:6px}
h1{font-size:1.4rem;letter-spacing:.2em}.scr{font-size:1.1rem}}
</style></head><body><main>
<h1>@@title@@</h1>
<div class="row"><span class="lab">TEXTE:</span> <span class="val">@@source@@</span></div>
<div class="row"><span class="lab">PROCHAIN CHANGEMENT:</span> <span class="val" id="nx" data-w="@@wait@@">@@next@@</span></div>
<div class="row"><span class="lab">RETOUR AU DEFAUT:</span> <span class="val">@@reset@@</span></div>
<div class="sp"></div>
<div class="bar"></div><div class="bar"></div><div class="bar"></div>
<div class="scr" aria-label="@@current_plain@@" style="--d:@@dur@@s"><span class="run" aria-hidden="true">@@current@@</span></div>
@@message@@
<form method="post" action="/">
<div class="row"><label class="lab" for="t">NOUVEAU TEXTE:</label></div>
<textarea id="t" name="t" rows="3" maxlength="@@max@@" autocomplete="off" required>@@value@@</textarea>
<div class="row"><span class="lab">CARACTERES:</span> <span class="cnt"><span id="n">0</span> / @@max@@</span></div>
<input type="hidden" name="k" value="@@token@@">
<input class="hp" type="text" name="site" tabindex="-1" autocomplete="off" aria-hidden="true">
<div class="sp"></div>
<button id="b" @@disabled@@>ENVOYER</button>
</form>
<p class="help">Majuscules, @@allowed@@, @@max@@ caracteres au plus. Une modification toutes les 3 minutes pour
tout le monde ; sans nouveau texte pendant 1 heure, le message par defaut revient. Le texte apparait sur le C64
au morceau suivant, pas tout de suite.</p>
<div class="row keys">SPC=NEXT &nbsp; S=FIND &nbsp; C=CLEAR &nbsp; V=VIS &nbsp; Q=QUIT</div>
</main>
<script>
var t=document.getElementById('t'),n=document.getElementById('n');
function up(){var p=t.selectionStart;t.value=t.value.toUpperCase();t.setSelectionRange(p,p);n.textContent=t.value.length}
t.addEventListener('input',up);up();
var nx=document.getElementById('nx'),b=document.getElementById('b'),w=parseFloat(nx.dataset.w)||0,end=Date.now()+w*1000;
function tick(){var r=Math.ceil((end-Date.now())/1000);
if(r<=0){nx.textContent='MAINTENANT';b.disabled=false;return}
nx.textContent=r>=60?Math.floor(r/60)+' MIN '+('0'+r%60).slice(-2)+' S':r+' S';setTimeout(tick,250)}
if(w>0)tick();
</script></body></html>
"""


def rainbow(text: str, shift: int = 0) -> str:
    """Une couleur par lettre, comme le titre du jukebox sur le C64 (les espaces gardent leur place)."""
    out, i = [], 0
    for c in text:
        if c == " ":
            out.append(" ")
        else:
            out.append('<span style="color:%s">%s</span>' % (RAINBOW[(i + shift) % len(RAINBOW)], html.escape(c)))
            i += 1
    return "".join(out)


def render(st: State, ip: str, message: str = "", ok: bool = False, value: str = "") -> bytes:
    cur, from_user = st.current()
    last = st.last_change()
    wait_s = max(0.0, st.a.cooldown - (time.time() - last)) if last else 0.0
    wait_s = max(wait_s, st.ip_wait(ip))
    left = st.a.ttl - (time.time() - last) if (from_user and last) else 0.0
    msg = '<div class="msg %s" role="status">%s</div>' % ("ok" if ok else "err", html.escape(message)) if message else ""
    vals = {
        "title": rainbow("JUKEBOX SID"),
        "source": "VISITEUR" if from_user else "PAR DEFAUT",
        "next": fmt(wait_s) if wait_s else "MAINTENANT",
        "wait": "%.1f" % wait_s,
        "reset": fmt(left) if left > 0 else "-",
        "current": rainbow(cur or " ", 3),
        "current_plain": html.escape(cur, quote=True),
        "dur": str(max(12, int(len(cur) * 0.28))),
        "message": msg, "max": str(SCROLL_MAX), "allowed": html.escape(ALLOWED_TXT),
        "value": html.escape(value), "token": st.token(),
        "disabled": "disabled" if wait_s else "",
    }
    # une seule passe : le texte saisi par un visiteur n'est jamais réinterprété comme un champ
    return re.sub(r"@@(\w+)@@", lambda m: vals[m.group(1)], PAGE).encode("utf-8")


class BoundedServer(ThreadingHTTPServer):
    """Un fil par connexion, mais au plus MAX_THREADS à la fois : au-delà on ferme tout de suite."""
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.slots = threading.BoundedSemaphore(MAX_THREADS)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


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
        self.reply(200, render(self.st, self.ip()))

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
            return self.reply(200, render(st, ip, "Formulaire périmé ou envoyé trop vite : réessaie."))
        txt, err = check_text(st, get("t"))
        if txt is None:
            return self.reply(200, render(st, ip, err, value=get("t")[:SCROLL_MAX * 2]))
        with st.lock:                       # la pause est vérifiée et armée sous le même verrou
            last = st.last_change()
            wait = st.a.cooldown - (time.time() - last) if last else 0
            if wait > 0:
                return self.reply(200, render(st, ip, "Trop tôt : encore %s avant le prochain changement." % fmt(wait),
                                              value=txt))
            wait = st.ip_wait(ip)
            if wait > 0:
                return self.reply(200, render(st, ip, "Tu as déjà changé le texte : encore %s avant de pouvoir "
                                              "recommencer." % fmt(wait), value=txt))
            write_atomic(st.a.user_file, txt)
            st.mark(ip)
        with open(st.a.history, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "ip": ip, "text": txt}) + "\n")
        log.info("%s nouveau texte : %s", ip, txt)
        self.reply(200, render(st, ip, "C'est enregistré. Le texte apparaîtra au prochain morceau.", ok=True))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user-file", dest="user_file", type=Path, default=DATA / "scroll_user.txt")
    ap.add_argument("--default-file", dest="default_file", type=Path, default=HERE / "scroll.txt")
    ap.add_argument("--history", type=Path, default=DATA / "web_changes.log")
    ap.add_argument("--cooldown", type=int, default=180, help="secondes entre deux changements (global)")
    ap.add_argument("--ip-cooldown", dest="ip_cooldown", type=int, default=600,
                    help="secondes entre deux changements de la même IP (IPv6 : même bloc /64)")
    ap.add_argument("--ttl", type=int, default=3600, help="secondes avant retour au message par défaut")
    ap.add_argument("--trust-proxy", action="store_true")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=6475)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    Handler.st = State(a)
    srv = BoundedServer((a.host, a.port), Handler)
    log.info("page du scroller sur http://%s:%d/", a.host, a.port)
    srv.serve_forever()


if __name__ == "__main__":
    main()
