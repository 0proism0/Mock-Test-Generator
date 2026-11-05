"""Probe the local OpenAI-compatible server: model id, thinking controls, JSON mode.

Run: python classifier/probe_server.py
Prints ASCII only (console is GBK).
"""
from __future__ import annotations

import json
import time
import urllib.request

BASE = "http://192.168.2.103:20300/v1"
MODEL = "qwen3.8-27b"


def post(path: str, payload: dict, timeout: int = 180) -> tuple[int, dict | str]:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]
    except Exception as e:  # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}"


def show(tag: str, status: int, body) -> None:
    print(f"\n=== {tag} === status={status}")
    if not isinstance(body, dict):
        print("  body:", body)
        return
    msg = body.get("choices", [{}])[0].get("message", {})
    print("  keys:", sorted(msg.keys()))
    for k in ("reasoning_content", "reasoning"):
        if msg.get(k):
            print(f"  {k}: {len(msg[k])} chars, head={msg[k][:80]!r}")
    print("  content:", (msg.get("content") or "")[:160].replace("\n", " "))
    print("  usage:", body.get("usage"))


BASIC = [
    {"role": "system", "content": "You classify math problems. Reply with JSON only."},
    {"role": "user", "content": "Classify: 'How many positive divisors does 360 have?' Reply with {\"topic\": \"...\"}."},
]


def main() -> None:
    t0 = time.time()
    status, body = post("/chat/completions", {"model": MODEL, "messages": BASIC, "max_tokens": 200})
    print(f"[a] plain chat: {time.time() - t0:.1f}s")
    show("a plain", status, body)

    for tag, extra in [
        ("b reasoning_effort=low", {"reasoning_effort": "low"}),
        ("c chat_template_kwargs enable_thinking=false", {"chat_template_kwargs": {"enable_thinking": False}}),
        ("d reasoning_effort=none", {"reasoning_effort": "none"}),
        ("e enable_thinking=false top-level", {"enable_thinking": False}),
    ]:
        t0 = time.time()
        payload = {"model": MODEL, "messages": BASIC, "max_tokens": 200, **extra}
        status, body = post("/chat/completions", payload)
        print(f"[{tag}] {time.time() - t0:.1f}s")
        show(tag, status, body)

    schema = {
        "type": "object",
        "properties": {
            "primary": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "difficulty": {"type": "integer", "minimum": 1, "maximum": 5},
        },
        "required": ["primary", "tags", "difficulty"],
        "additionalProperties": False,
    }
    t0 = time.time()
    status, body = post("/chat/completions", {
        "model": MODEL,
        "messages": BASIC,
        "max_tokens": 300,
        "reasoning_effort": "low",
        "response_format": {"type": "json_schema", "json_schema": {"name": "cls", "schema": schema, "strict": True}},
    })
    print(f"[f json_schema] {time.time() - t0:.1f}s")
    show("f json_schema", status, body)

    t0 = time.time()
    status, body = post("/chat/completions", {
        "model": MODEL,
        "messages": BASIC,
        "max_tokens": 300,
        "reasoning_effort": "low",
        "response_format": {"type": "json_object"},
    })
    print(f"[g json_object] {time.time() - t0:.1f}s")
    show("g json_object", status, body)


if __name__ == "__main__":
    main()
