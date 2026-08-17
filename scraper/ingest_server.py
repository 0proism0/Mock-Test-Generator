"""Local ingest server: receives AoPS wiki batches from the browser fetch loop.

Endpoints (CORS + Private-Network-Access enabled):
  GET  /ping            -> {"ok": true}
  POST /result          -> body: {"slug": ..., "pages": {title: content, ...}}
                           appends to raw/aops_wiki/<slug>.jsonl, updates state.json
  GET  /status          -> scraper/state.json summary

Run: .venv/bin/python scraper/ingest_server.py  (port 8791)
"""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw" / "aops_wiki"
RAW_DIR.mkdir(parents=True, exist_ok=True)
STATE = ROOT / "scraper" / "state.json"
LOCK = threading.Lock()
COUNTS = {}


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/ping":
            body = json.dumps({"ok": True, "counts": COUNTS}).encode()
            self.send_response(200)
        elif self.path == "/status":
            body = STATE.read_bytes() if STATE.exists() else b"{}"
            self.send_response(200)
        else:
            body = b"{}"
            self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/result":
            self.send_response(404)
            self._cors()
            self.end_headers()
            return
        n = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(n) or b"{}")
        slug = re.sub(r"[^a-z0-9_]", "", data.get("slug", "misc"))
        pages = data.get("pages", {})
        with LOCK:
            with (RAW_DIR / f"{slug}.jsonl").open("a") as f:
                for title, content in pages.items():
                    if content:
                        f.write(json.dumps({"title": title, "content": content}, ensure_ascii=False) + "\n")
            COUNTS[slug] = COUNTS.get(slug, 0) + sum(1 for c in pages.values() if c)
        body = json.dumps({"ok": True, "counts": COUNTS}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("ingest server on 127.0.0.1:8791", flush=True)
    HTTPServer(("127.0.0.1", 8791), Handler).serve_forever()
