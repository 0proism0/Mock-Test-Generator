#!/usr/bin/env sh
# Build the React front-end (app/web) into app/web/dist.
# The Python server (app/server.py) serves that folder at "/" when present.
#
# Usage:  sh scripts/build.sh
set -e

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WEB="$ROOT/app/web"

command -v npm >/dev/null 2>&1 || {
    echo "npm not found on PATH. Install Node.js 20+ first." >&2
    exit 1
}

cd "$WEB"
if [ ! -d node_modules ]; then
    if [ -f package-lock.json ]; then
        echo "[build] npm ci"
        npm ci
    else
        echo "[build] npm install"
        npm install
    fi
fi
echo "[build] npm run build"
npm run build
echo "[build] done -> app/web/dist"
