#!/usr/bin/env sh
# Auto-rebuild the React front-end on every change (vite build --watch -> app/web/dist).
# Leave it running while you edit app/web, then refresh http://localhost:8000.
#
# Usage:  sh scripts/watch.sh
set -e

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WEB="$ROOT/app/web"

command -v npm >/dev/null 2>&1 || {
    echo "npm not found on PATH. Install Node.js 20+ first." >&2
    exit 1
}

cd "$WEB"
if [ ! -d node_modules ]; then
    echo "[watch] npm ci"
    npm ci
fi
echo "[watch] vite build --watch -> app/web/dist (Ctrl+C to stop)"
npm run build:watch
