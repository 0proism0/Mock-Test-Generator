# Anti-crawler defense practice — the 5-layer model on MockTest (localhost)

This project doubles as a hands-on lab for the classic bot-defense stack.
The **attacker side** is `scraper/shsid_crawler.py` (a working Moodle
crawler); the **defender side** is `app/botguard.py` + guards in
`app/server.py`. Everything runs locally; the audit trail lands in
`botguard.log` (JSONL, gitignored).

## Layer map

### L1 — Network/protocol (edge-only) 🔶 partially applicable

JA3/JA4 TLS-fingerprint and HTTP/2-fingerprint checks run where TLS
terminates. Our stdlib server speaks plain HTTP on localhost, so this layer
is documented rather than enforced. On a real deployment, terminate at
Nginx and reject non-browser fingerprints before they reach the app:

```nginx
# sketch: JA3 needs an Nginx module or a sidecar that computes the
# fingerprint and passes it on; here we at least enforce HTTP/2 and
# reject known scripting clients by UA as a poor-man's stand-in.
if ($http_user_agent ~* (python-requests|curl/|wget/|scrapy)) {
    return 403;
}
```

For practice purposes, `_bot_gate()` applies the UA portion of this idea
*inside* the app: self-declared scripts get a 4x tighter rate budget.

### L2 — Browser environment ✅

`/challenge` serves a page that must execute JavaScript, sample real
`mousemove` events, and POST the evidence to `/api/challenge/verify`.
Only then does the server set `bg_t`, an HMAC-signed, expiring,
fingerprint-bound cookie. Scripts that never run JS never get the cookie;
endpoints behind `_bot_gate()` refuse them (`403` JSON for fetch/curl, a
`303` redirect to the challenge for browsers).

### L3 — Behavior ✅ (mouse dynamics)

The challenge verifies three behavioral signals server-side:

| signal | bot giveaway | minimum |
|---|---|---|
| mouse-move count | headless/no input | ≥ 5 moves |
| dwell time | instant submit | ≥ 1.2 s |
| move-interval variance | perfectly uniform intervals (scripted loops) | > 0.01 |

This is the teacher's "ideal bezier curves / uniform intervals" test in
miniature. Evasion idea to try in the lab: replay recorded human mouse
logs — does uniform-interval detection still catch naive replay?

### L4 — Application logic ✅

- **Honeypots**: `/honeypot` and `/api/trap` return 404 to everyone, but
  touching them grade-bans the fingerprint for 5 minutes. The SHSID page
  renders an invisible `.shsid-trap` link (`display:none`) that only
  parsers follow.
- **robots.txt trap**: `Disallow: /honeypot` + `/api/trap`. Compliant
  crawlers never see the trap; anything that hits it has admitted it
  ignores robots.txt.
- **Graded challenge**: nothing forces every user through the challenge —
  only sensitive endpoints (`/shsid-files/*`), hot login fingerprints, and
  rate-limited fingerprints are asked to prove humanity. Low-risk traffic
  flows untouched.
- **Login brute-force ladder**: 5 failed logins per (fingerprint, user)
  per 5 min → subsequent attempts require a valid `bg_t` cookie.

### L5 — Infrastructure/strategy ✅ (local adaptation)

- **Fingerprint ≠ IP**: identity is `sha256(ip + user-agent)`, so a ban on
  one script doesn't lock out the human on the same machine (crucial on
  localhost where every client shares 127.0.0.1).
- **Sliding-window rate limits** per fingerprint: 30 hits/10 s for
  browsers, 4 hits/10 s for self-declared scripts.
- **Graded bans**: 5-minute ban, not permanent — and every decision is
  logged with its reason for review (`botguard.log`).
- Static IP blocklists are deliberately *absent* (residential/proxy IPs
  make them useless); the design mirrors AWS WAF Bot Control's
  "not IP-based" philosophy at toy scale.

## Try to break it (lab exercises)

```bash
# 1. raw curl: challenged
curl -b /tmp/jar http://localhost:8020/shsid-files/...
#    -> 403 {"error": "human check required"}

# 2. take the challenge in a real browser (or Playwright with mouse moves)
#    -> bg_t cookie set -> downloads work for 1 h

# 3. touch the honeypot with a test UA -> that fingerprint is banned 5 min
curl -A "lab-test-crawler/1.0" http://localhost:8020/honeypot
curl -A "lab-test-crawler/1.0" http://localhost:8020/shsid-files/x  # 403 banned

# 4. brute force a login -> after 5 tries, challenge required
for i in $(seq 6); do curl -X POST http://localhost:8020/api/login \
  -H 'Content-Type: application/json' -d '{"username":"x","password":"y"}'; done

# 5. read the audit trail
cat botguard.log
```
