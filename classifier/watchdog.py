"""Keep the v2 classification running even when everything around it dies.

The classifier itself is resumable: it appends one JSON line per question and
skips the questions that are already done. What it cannot survive is its own
process disappearing (DSH restart, Windows OOM killer, a batch aborting because
the inference server went away mid-run).

This watchdog does exactly one thing: if the work is not finished and nothing is
running it, start it again. It never touches the data files.

    python -m classifier.watchdog             # loop until the work is done
    python -m classifier.watchdog --once      # single check, useful in a cron
    python -m classifier.watchdog --dry-run   # report what it would do
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "classifier" / "out"
PID_FILE = OUT / "runner.pid"
LOG = OUT / "watchdog.log"

TICK_S = 60
MAX_RESTARTS = 40


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def target_counts() -> dict[str, int]:
    """How many questions every bank v2 file holds, keyed by output stem."""
    counts: dict[str, int] = {}
    v2 = ROOT / "bank" / "v2"
    if not v2.is_dir():
        return counts
    for f in sorted(v2.glob("*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a broken bank must not stop the loop
            continue
        counts[f.stem] = len(doc.get("variants") or [])
    return counts


def done_counts() -> dict[str, int]:
    """Finished questions per bank, counting each qid once (last write wins)."""
    done: dict[str, int] = {}
    for f in sorted(OUT.glob("*_v2.jsonl")):
        stem = f.name[: -len("_v2.jsonl")]
        latest: dict[str, bool] = {}
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            qid = row.get("qid") or ""
            latest[qid] = (row.get("classification") or {}).get("state") == "done"
        done[stem] = sum(1 for ok in latest.values() if ok)
    return done


def pid_alive(pid: int) -> bool:
    """tasklist instead of os.kill: os.kill(pid, 0) terminates on Windows."""
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:  # noqa: BLE001
        return False
    return str(pid) in out


def runner_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip() or 0) or None
    except ValueError:
        return None


def server_ok() -> tuple[bool, str]:
    sys.path.insert(0, str(ROOT))
    from classifier import llm  # imported late so --once works without it

    cfg = json.loads((ROOT / "classifier" / "config.json").read_text(encoding="utf-8"))
    client = llm.Client(cfg["endpoint"], cfg["model"], cfg["params"], retries=1, timeout_s=15)
    return client.health()


def start_runner(concurrency: int) -> int | None:
    """Launch run_all fully detached so it outlives this watchdog and the shell."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    runner_log = (OUT / "run_all.out.log").open("a", encoding="utf-8")
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        [sys.executable, "-m", "classifier.run_all", "--only-v2",
         "--concurrency", str(concurrency)],
        cwd=str(ROOT), stdout=runner_log, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True,
    )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    return proc.pid


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="restart the v2 classifier if it died")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--concurrency", type=int, default=10)
    args = ap.parse_args(argv)

    restarts = 0
    while True:
        targets = target_counts()
        done = done_counts()
        pending = {k: targets[k] - done.get(k, 0) for k in targets}
        left = sum(v for v in pending.values() if v > 0)
        detail = ", ".join(f"{k} {done.get(k, 0)}/{targets[k]}" for k in targets)

        if left <= 0:
            log(f"all v2 banks finished ({detail}) - watchdog exiting")
            return 0

        pid = runner_pid()
        if pid and pid_alive(pid):
            log(f"runner alive (pid {pid}); {detail}; {left} left")
            if args.once or args.dry_run:
                return 0
            time.sleep(TICK_S)
            continue

        ok, why = server_ok()
        if not ok:
            log(f"runner is gone and the inference server is down ({why}); waiting")
            if args.once or args.dry_run:
                return 2
            time.sleep(TICK_S)
            continue

        if restarts >= MAX_RESTARTS:
            log(f"giving up after {restarts} restarts; {detail}; {left} left")
            return 1
        if args.dry_run:
            log(f"dry-run: would restart runner ({detail}; {left} left)")
            return 0

        log(f"runner is gone; restarting it ({detail}; {left} left)")
        new_pid = start_runner(args.concurrency)
        restarts += 1
        log(f"started pid {new_pid} (restart #{restarts})")
        if args.once:
            return 0
        time.sleep(TICK_S)


if __name__ == "__main__":
    sys.exit(main())
