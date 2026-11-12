#!/bin/sh
# Start the SHSID LinkedClassroom crawler as a background daemon.
# Credentials come from ./shsid_credentials (gitignored, chmod 600).
# Logs to raw/shsid/crawler.log. Stop with: pkill -f shsid_crawler
set -e
cd "$(dirname "$0")/.."

if [ ! -f shsid_credentials ]; then
    echo "missing shsid_credentials — copy shsid_credentials.example and fill it in" >&2
    exit 1
fi

set -a
. ./shsid_credentials
set +a

if [ -z "$SHSID_USER" ] || [ -z "$SHSID_PASS" ]; then
    echo "SHSID_USER / SHSID_PASS empty in shsid_credentials" >&2
    exit 1
fi

mkdir -p raw/shsid
INTERVAL="${SHSID_INTERVAL:-30}"

if pgrep -f "shsid_crawler.py.*--watch" >/dev/null 2>&1; then
    echo "crawler is already running (pkill -f shsid_crawler to stop)"
    exit 0
fi

nohup .venv/bin/python -u scraper/shsid_crawler.py \
    --download --watch --interval "$INTERVAL" \
    >> raw/shsid/crawler.log 2>&1 &
echo "crawler started (pid $!), log: raw/shsid/crawler.log, every ${INTERVAL} min"
