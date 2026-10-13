#!/usr/bin/env sh
# Run MockTest Maker.
#
#   sh scripts/start.sh         # Python server on http://localhost:8000
#                               # (serves app/web/dist if built, else the legacy UI)
#   sh scripts/start.sh --dev   # + Vite dev server on http://localhost:5173 (HMR, /api proxied)
set -e

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SERVER="$ROOT/app/server.py"
WEB="$ROOT/app/web"

resolve_python() {
    if [ -n "${PYTHON:-}" ]; then echo "$PYTHON"; return; fi
    if [ -x "$ROOT/.venv/bin/python" ]; then echo "$ROOT/.venv/bin/python"; return; fi
    if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then echo "$ROOT/.venv/Scripts/python.exe"; return; fi
    echo python
}
PY=$(resolve_python)

case "${1:-}" in
    --dev)
        command -v npm >/dev/null 2>&1 || { echo "npm not found on PATH. Install Node.js 20+ first." >&2; exit 1; }
        echo "[dev] Python API on http://localhost:8000 ..."
        "$PY" "$SERVER" &
        API_PID=$!
        trap 'kill "$API_PID" 2>/dev/null || true' EXIT INT TERM
        cd "$WEB" && npm run dev
        ;;
    *)
        [ -f "$WEB/dist/index.html" ] || echo "[start] app/web/dist not built - serving legacy UI. Run scripts/build.sh."
        echo "[start] http://localhost:8000"
        exec "$PY" "$SERVER"
        ;;
esac
