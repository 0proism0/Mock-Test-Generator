"""Anti-crawler defense practice for MockTest — the 5-layer bot model.

Implements, in pure stdlib Python, the layers a single HTTP server can own:

  L2 browser-environment : signed proof-of-human cookie issued only after a
                           JS challenge runs in a real browser
  L3 behavior            : mouse-dynamics entropy (move count, interval
                           variance, dwell time) verified server-side
  L4 application logic   : honeypot endpoints (/honeypot, /api/trap) +
                           robots.txt trap rules; graded challenge (only
                           suspicious fingerprints must solve it)
  L5 infrastructure      : per-fingerprint (IP+UA hash) sliding-window rate
                           limits and temporary bans; JSONL audit log

The protocol-layer items (JA3/JA4 TLS fingerprint, HTTP/2 fingerprint) need a
TLS-terminating edge in front — see docs/anti-crawler.md for the Nginx
sketch. Everything here works on plain localhost HTTP for practice.

Nothing here is production-hardened; it exists so the defense layers can be
seen, probed, and evaded-by-curl in a safe local setup.
"""
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET_FILE = ROOT / "botguard.secret"
LOG_FILE = ROOT / "botguard.log"
BAN_SECONDS = 300           # temporary graded ban
LOGIN_WINDOW = 300.0        # brute-force memory
LOGIN_MAX_FAILS = 5

# Master switch. The human check was built as a practice lab (see
# docs/anti-crawler.md); it is OFF by default so daily use has no friction.
# Restart the server with MOCKTEST_BOTGUARD=1 to turn the challenge back on.
ENABLED = os.environ.get("MOCKTEST_BOTGUARD", "") == "1"

# --- secret (persists across restarts so cookies survive; gitignored) ----------


def _load_secret():
    if SECRET_FILE.exists():
        return SECRET_FILE.read_bytes()
    s = secrets.token_bytes(32)
    SECRET_FILE.write_bytes(s)
    try:
        SECRET_FILE.chmod(0o600)
    except OSError:
        pass
    return s


SECRET = _load_secret()

# --- fingerprint: IP + UA hash (multi-factor, not IP alone) ---------------------


def fp(ip, ua):
    raw = f"{ip}|{(ua or '')[:200]}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]

# --- signed, expiring proof-of-human cookie --------------------------------------


def make_token(fingerprint, nonce, ttl=3600):
    exp = int(time.time()) + ttl
    msg = f"{fingerprint}|{nonce}|{exp}".encode()
    sig = hmac.new(SECRET, msg, hashlib.sha256).hexdigest()[:32]
    return f"{fingerprint}.{nonce}.{exp}.{sig}"


def check_token(token, fingerprint):
    try:
        f, _nonce, exp, sig = token.split(".")
    except (ValueError, AttributeError):
        return False
    if f != fingerprint or time.time() > int(exp):
        return False
    msg = f"{f}|{_nonce}|{exp}".encode()
    expect = hmac.new(SECRET, msg, hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(sig, expect)

# --- one-time challenge nonces -----------------------------------------------------


_nonces = {}
_nonces_lock = threading.Lock()


def issue_nonce():
    n = secrets.token_hex(8)
    with _nonces_lock:
        _nonces[n] = time.time() + 300
    return n


def redeem_nonce(n):
    with _nonces_lock:
        ts = _nonces.pop(n, None)
    return ts is not None and time.time() <= ts

# --- sliding-window rate limit per fingerprint -------------------------------------


_buckets = {}
_buckets_lock = threading.Lock()


def rate_limit(fingerprint, max_hits=60, window=10.0):
    now = time.time()
    with _buckets_lock:
        hits = [t for t in _buckets.get(fingerprint, []) if now - t < window]
        if len(hits) >= max_hits:
            _buckets[fingerprint] = hits
            return False
        hits.append(now)
        _buckets[fingerprint] = hits
    return True

# --- graded bans + audit log --------------------------------------------------------


_bans = {}
_bans_lock = threading.Lock()


def ban(fingerprint, reason, path=""):
    if not ENABLED:
        log({"event": "honeypot_hit_ignored_disabled", "reason": reason, "path": path,
             "fp": fingerprint})
        return
    until = time.time() + BAN_SECONDS
    with _bans_lock:
        _bans[fingerprint] = until
    log({"event": "ban", "reason": reason, "path": path,
         "fp": fingerprint, "until": int(until)})


def is_banned(fingerprint):
    with _bans_lock:
        until = _bans.get(fingerprint)
    return until is not None and time.time() < until


def log(rec):
    rec["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass

# --- login brute-force memory (graded challenge after N fails) ------------------------


_login_fails = {}
_login_lock = threading.Lock()


def note_login_fail(fingerprint, username):
    key = f"{fingerprint}|{username}"
    now = time.time()
    with _login_lock:
        fails = [t for t in _login_fails.get(key, []) if now - t < LOGIN_WINDOW]
        fails.append(now)
        _login_fails[key] = fails
        return len(fails) >= LOGIN_MAX_FAILS


def login_needs_challenge(fingerprint, username):
    key = f"{fingerprint}|{username}"
    now = time.time()
    with _login_lock:
        fails = [t for t in _login_fails.get(key, []) if now - t < LOGIN_WINDOW]
    return len(fails) >= LOGIN_MAX_FAILS


def clear_login_fails(fingerprint, username):
    with _login_lock:
        _login_fails.pop(f"{fingerprint}|{username}", None)

# --- the JS challenge page (L2+L3 in one) ----------------------------------------------


CHALLENGE_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>MockTest anti-bot check</title>
<style>
 body{font-family:system-ui,sans-serif;background:#f4f1e8;color:#22332b;
      display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
 .card{background:#fffef9;border:1px solid #b8c6bd;border-radius:10px;padding:32px 40px;max-width:420px;text-align:center}
 h2{margin:0 0 6px;font-size:20px} p{color:#5c6f64;font-size:14px}
 #mv{font-variant-numeric:tabular-nums;font-weight:600}
 button{margin-top:14px;padding:10px 22px;border:0;border-radius:8px;background:#315c4b;color:#fff;font-size:15px;cursor:pointer}
</style></head><body>
<div class="card">
  <h2>Human check</h2>
  <p>Move your mouse over this page for a moment — we are sampling
     <b>mouse dynamics</b> (moves: <span id="mv">0</span>) to tell humans
     from scripts. Nothing leaves your browser except counts.</p>
  <p id="msg">sampling&hellip;</p>
  <button id="go" type="button" onclick="submit()">Verify and continue</button>
</div>
<script>
const NONCE = "__NONCE__";
const NEXT = new URLSearchParams(location.search).get("next") || "/";
let moves = 0, last = 0, intervals = [], t0 = performance.now();
document.addEventListener("mousemove", () => {
  const t = performance.now();
  if (last) intervals.push(t - last);
  last = t; moves++;
  document.getElementById("mv").textContent = moves;
});
function variance(a) {
  if (a.length < 2) return 0;
  const m = a.reduce((x, y) => x + y) / a.length;
  return a.reduce((s, x) => s + (x - m) * (x - m), 0) / a.length;
}
function submit() {
  const dwell = (performance.now() - t0) / 1000;
  fetch("/api/challenge/verify?next=" + encodeURIComponent(NEXT), {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({nonce: NONCE, moves, dwell, variance: variance(intervals)}),
  }).then(r => r.json()).then(d => {
    if (d.ok) { document.getElementById("msg").textContent = "verified — reloading";
                location.href = d.next || "/"; }
    else { document.getElementById("msg").textContent = d.error || "failed — keep moving the mouse"; }
  }).catch(e => { document.getElementById("msg").textContent = String(e); });
}
setTimeout(() => { if (moves >= 5) submit(); }, 2000);  // auto-pass once entropy looks human
</script></body></html>
"""

# minimum behavior evidence a "human" must produce
MIN_MOVES = 5
MIN_DWELL = 1.2
MIN_VARIANCE = 0.01     # perfectly uniform intervals => scripted
