"""Push the repo to GitHub via the Git Data API (works when git's port 443 is blocked).

Uses the token from `gh auth token`. Creates blobs for all git-tracked files,
then a tree + commit, and fast-forwards the main ref.
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
REPO = "LOLandXD/Mock-Test-Generator"
API = f"https://api.github.com/repos/{REPO}/git"

token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
H = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def api(method, path, **kw):
    r = requests.request(method, f"{API}{path}", headers=H, json=kw.get("json"), timeout=60)
    if r.status_code >= 300:
        print("API ERROR", method, path, r.status_code, r.text[:300])
        sys.exit(1)
    return r.json()


def main():
    files = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).split()
    print(len(files), "files to push")
    entries = []
    for i, f in enumerate(files):
        data = (ROOT / f).read_bytes()
        blob = api("POST", "/blobs", json={"content": base64.b64encode(data).decode(), "encoding": "base64"})
        entries.append({"path": f, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(files)} blobs")
    head = api("GET", "/ref/heads/main")
    tree = api("POST", "/trees", json={"base_tree": head["object"]["sha"], "tree": entries})
    commit = api("POST", "/commits", json={
        "message": "MockTest Maker: 21 competitions, 5300+ problems, variant generator, web app",
        "tree": tree["sha"], "parents": [head["object"]["sha"]]})
    api("PATCH", "/refs/heads/main", json={"sha": commit["sha"]})
    print("PUSHED", commit["sha"][:8], f"-> https://github.com/{REPO}/commit/{commit['sha']}")


if __name__ == "__main__":
    main()
