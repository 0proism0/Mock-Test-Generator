"""Minimal OpenAI-compatible chat client — stdlib only (repo rule: no new deps).

Why not the openai SDK: the target server is a local inference box speaking the
/v1 dialect, and the repo keeps the backend dependency-free. urllib is enough.

Server quirks discovered by probe_server.py (do not "optimise" these away):
  * reasoning_effort="low" keeps thinking on but shorter (that is what we want).
  * reasoning_effort="none" / chat_template_kwargs.enable_thinking=false turns it
    fully off.
  * response_format json_schema / json_object produce CORRUPTED content on this
    build (e.g. '{"primary":": "'). So we never use structured outputs; we ask
    for JSON in the prompt and repair locally in extract_json().
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request


class ChatError(RuntimeError):
    pass


def _starved(reply: "Reply", budget: int) -> bool:
    """True when the token budget ran out before the model finished answering.

    The reasoning and the answer share one budget, so hard problems die in two
    ways: content == "" (thinking ate everything) or content == a truncated
    half-JSON. The server tells us which via finish_reason == "length"; the
    token comparison is only a fallback for servers that omit it. Either way the
    fix is the same: retry with a bigger budget instead of recording a failure.
    """
    if not budget:
        return False
    if reply.finish_reason == "length":
        return True
    return not reply.content.strip() and reply.completion_tokens >= budget * 0.98


class Reply:
    __slots__ = ("content", "reasoning", "usage", "latency_s", "finish_reason")

    def __init__(self, content: str, reasoning: str, usage: dict, latency_s: float,
                 finish_reason: str = ""):
        self.content = content
        self.reasoning = reasoning
        self.usage = usage or {}
        self.latency_s = latency_s
        self.finish_reason = finish_reason

    @property
    def reasoning_tokens(self) -> int:
        return int((self.usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)

    @property
    def completion_tokens(self) -> int:
        return int(self.usage.get("completion_tokens") or 0)

    def json(self) -> dict | None:
        return extract_json(self.content)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> dict | None:
    """Pull the first decodable JSON object out of a chat reply.

    Handles: bare JSON, ```json fences, prose before/after the object, trailing
    commas. Returns None when nothing decodes.
    """
    if not text:
        return None
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for cand in candidates:
        cand = cand.strip()
        obj = _try(cand)
        if obj is not None:
            return obj
        # scan balanced braces, largest first
        for chunk in sorted(_balanced_objects(cand), key=len, reverse=True):
            obj = _try(chunk)
            if obj is not None:
                return obj
        # last resort: the object was cut off mid-write
        repaired = _repair_truncated(cand)
        if repaired:
            obj = _try(repaired)
            if obj is not None:
                obj["_repaired"] = True
                return obj
    return None


def _try(text: str) -> dict | None:
    for variant in (text, re.sub(r",\s*([}\]])", r"\1", text)):
        try:
            value = json.loads(variant)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(value, dict):
            return value
    return None


def _repair_truncated(text: str) -> str | None:
    """Close a JSON object that the output limit cut in half.

    A starved reply usually still contains every field we need - only the
    closing quotes/braces are missing. Instead of paying for another generation
    we close them syntactically and decode what we got.
    """
    start = text.find("{")
    if start < 0:
        return None
    s = text[start:]
    out = s
    for _ in range(6):
        stack, in_str, open_at = _scan_json(out)
        if not in_str:
            break
        # The cut landed inside a string. Drop that whole fragment: a half
        # written value (or a half written key) cannot be repaired, but
        # everything before it can.
        cut = out.rfind(",", 0, open_at)
        brk = max(out.rfind("{", 0, open_at), out.rfind("[", 0, open_at))
        cut = max(cut, brk)
        if cut <= 0:
            return None
        out = out[:cut]
    stack, in_str, _ = _scan_json(out)
    if in_str:
        return None
    out = re.sub(r",\s*$", "", out.rstrip())
    if out.endswith(":"):
        cut = max(out.rfind(","), out.rfind("{"), out.rfind("["))
        if cut <= 0:
            return None
        out = re.sub(r",\s*$", "", out[:cut].rstrip())
        stack, _, _ = _scan_json(out)
    for ch in reversed(stack):
        out += "}" if ch == "{" else "]"
    return out


def _scan_json(s: str) -> tuple[list[str], bool, int]:
    """Return (open brackets, still inside a string, index where that string opened)."""
    stack: list[str] = []
    in_str = False
    esc = False
    open_at = -1
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            open_at = i
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()
    return stack, in_str, open_at


def _balanced_objects(text: str) -> list[str]:
    out, depth, start = [], 0, None
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                out.append(text[start : i + 1])
    return out


class Client:
    def __init__(self, endpoint: str, model: str, params: dict | None = None,
                 retries: int = 4, timeout_s: int = 180):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.params = dict(params or {})
        self.retries = retries
        self.timeout_s = timeout_s
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.reasoning_tokens = 0
        self.cached_tokens = 0
        self.starved_retries = 0
        # Consecutive transport failures. A hung inference server used to cost
        # retries*timeout_s (12 min) per question, so bail out once it is
        # clearly not coming back instead of grinding through the whole batch.
        self.fail_streak = 0
        self.dead_after = 3

    def chat(self, messages: list[dict], **overrides) -> Reply:
        payload = {"model": self.model, "messages": messages, **self.params, **overrides}
        last = "no attempt"
        for attempt in range(self.retries):
            budget = int(payload.get("max_tokens") or 0)
            t0 = time.time()
            try:
                req = urllib.request.Request(
                    self.endpoint + "/chat/completions",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    body = json.loads(resp.read().decode())
                msg = body["choices"][0]["message"]
                choice = body["choices"][0]
                reply = Reply(choice["message"].get("content") or "",
                              choice["message"].get("reasoning_content") or "",
                              body.get("usage") or {}, time.time() - t0,
                              choice.get("finish_reason") or "")
                self._account(reply.usage)
                self.fail_streak = 0
                if _starved(reply, budget) and attempt + 1 < self.retries:
                    # Give the reasoning room to finish instead of failing the
                    # item - but cap it: classification only needs ~150 output
                    # tokens, so a 6k-token "thinking" run means the model is
                    # looping, not computing. At the cap we turn thinking off
                    # rather than asking for an even longer generation.
                    self.starved_retries += 1
                    payload["max_tokens"] = min(4096, max(budget * 2, 1600))
                    if payload["max_tokens"] >= 4096:
                        payload["reasoning_effort"] = "none"
                    last = (f"truncated at max_tokens={budget} "
                            f"(finish_reason={reply.finish_reason or '?'}, "
                            f"reasoning={reply.reasoning_tokens})")
                    continue
                return reply
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}: {e.read().decode()[:200]}"
            except Exception as e:  # noqa: BLE001
                last = f"{type(e).__name__}: {e}"
            self.fail_streak += 1
            if self.fail_streak >= self.dead_after:
                raise ChatError(
                    f"inference server looks down ({self.fail_streak} consecutive "
                    f"transport failures, last: {last})")
            time.sleep(min(10.0, 1.5 * (attempt + 1)) ** 1.3 * 0.6)
        raise ChatError(f"chat failed after {self.retries} attempts: {last}")

    def _account(self, usage: dict) -> None:
        self.calls += 1
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        self.reasoning_tokens += int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
        self.cached_tokens += int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)

    def health(self, timeout_s: int = 10) -> tuple[bool, str]:
        """Cheap liveness probe: does /v1/models answer at all?"""
        try:
            with urllib.request.urlopen(self.endpoint + "/models", timeout=timeout_s) as resp:
                body = json.loads(resp.read().decode())
            ids = [m.get("id") for m in (body.get("data") or [])]
            if self.model not in ids:
                return False, f"model {self.model!r} not served; available: {ids}"
            return True, f"model {self.model} ok"
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"

    def stats(self) -> dict:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cached_prompt_tokens": self.cached_tokens,
            "starved_retries": self.starved_retries,
        }
