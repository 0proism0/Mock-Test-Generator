"""Automatic classification + difficulty rating for bank questions.

Runs one model call per question against the local Qwen box, resolves the answer
against taxonomy/amc-v1.json, and writes results that already conform to paper
format v1.1 (`classification` + `difficulty` objects).

Usage (from repo root):

  python -m classifier.classify --bank amc10 --sample 8          # smoke test
  python -m classifier.classify --bank amc10 --limit 100         # first 100
  python -m classifier.classify --bank amc10 --v2                # figure bank
  python -m classifier.classify --bank amc8 --dry-run            # prompt only
  python -m classifier.classify --stats                          # what ran so far

Output: classifier/out/<bank>.jsonl (resumable, append-only, one line per qid)
        classifier/out/<bank>.paper.json (paper v1.1 slice, validator-ready)

Every line records the model's raw answer next to the resolved ids, so a bad
resolution can be audited (and re-resolved) without paying for the model again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import llm as llm_mod
from . import taxonomy as tax_mod
from .difficulty import combine as combine_mod
from .difficulty import prior as prior_mod

ROOT = Path(__file__).resolve().parent.parent

# Defects a grader may report from looking at the text alone (never by solving it).
ISSUE_CODES = {
    "missing_figure": "the statement refers to a figure that is not there",
    "broken_latex": "formula/markup is garbled or cut mid-expression",
    "truncated_stem": "the statement stops before the question is complete",
    "answer_not_in_choices": "the recorded answer is not among the choices",
    "duplicate_choices": "two choices are identical",
    "missing_choices": "a multiple-choice item has no choices",
    "missing_answer": "no answer is recorded",
    "missing_solution": "no solution is recorded",
    "not_a_problem": "the text is not a problem (title page, answer list, fragment)",
    "solution_inside_stem": "solution text is mixed into the statement",
}
ISSUE_SEVERITIES = {"blocker", "warn"}


def normalize_issue(raw) -> dict | None:
    """Coerce the model's ``issue`` field into ``{code, severity, note}`` or None.

    Unknown codes are kept but marked so a human can see the model went off-road,
    rather than silently dropping a report.
    """
    if not raw:
        return None
    if isinstance(raw, str):
        raw = {"code": raw}
    if not isinstance(raw, dict):
        return None
    code = str(raw.get("code") or "").strip().lower().replace(" ", "_")
    if not code or code in {"none", "null", "ok", "no_issue"}:
        return None
    severity = str(raw.get("severity") or "").strip().lower()
    if severity not in ISSUE_SEVERITIES:
        severity = "warn" if code in ISSUE_CODES else "blocker"
    note = " ".join(str(raw.get("note") or "").split())[:200] or None
    out = {"code": code, "severity": severity, "note": note}
    if code not in ISSUE_CODES:
        out["unknown_code"] = True
    return out


def load_config() -> dict:
    cfg = json.loads((ROOT / "classifier" / "config.json").read_text(encoding="utf-8"))
    cfg["paths"] = {k: str(ROOT / v) for k, v in cfg["paths"].items()}
    return cfg


def read_rows(path: Path) -> list[dict]:
    """Read a result file, keeping only the latest row per qid (last write wins).

    The jsonl is append-only and pending rows are retried on the next run, so the
    same qid can legitimately appear more than once.
    """
    latest: dict[str, dict] = {}
    order: list[str] = []
    skipped = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            # A hard kill can cut the last line mid-write. Skipping it keeps the
            # file resumable; that question is simply classified again.
            skipped += 1
            continue
        qid = row.get("qid") or f"line{len(order)}"
        if qid not in latest:
            order.append(qid)
        latest[qid] = row
    if skipped:
        print(f"[resume] skipped {skipped} truncated line(s) in {path.name}")
    return [latest[q] for q in order]


def resolve_paths(cfg: dict, args) -> list[Path]:
    bank_dir = Path(cfg["paths"]["bank_v2"] if args.v2 else cfg["paths"]["bank"])
    if args.file:
        return [Path(args.file)]
    if args.bank:
        pattern = f"{args.bank}*.json" if not args.v2 else f"{args.bank}*.json"
        return sorted(p for p in bank_dir.glob(pattern) if _is_bank_file(p))
    return sorted(p for p in bank_dir.glob("*.json") if _is_bank_file(p))


def _is_bank_file(p: Path) -> bool:
    """Skip the *.v1.json migrations.

    Each bank file has a v1.0 twin holding the same questions, so globbing
    ``amc8*.json`` would return every question twice (the same trap
    ``app/server.py:bank_files`` guards against).
    """
    return p.suffix == ".json" and not p.name.endswith(".v1.json")


def question_qid(v: dict) -> str:
    """Stable id for a question: the bank's own qid, or a content hash.

    Position is NOT usable as a fallback: it is only the slot in the original
    paper, so every year's "Problem 1" would collapse onto one id and the
    resumable output would lose almost every question.
    """
    qid = (v.get("qid") or "").strip()
    if qid:
        return qid
    key = (str(v.get("source") or "") + "\0" + str(v.get("question") or "")).encode("utf-8")
    return "q" + hashlib.sha1(key).hexdigest()[:12]


def iter_variants(path: Path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    competition = doc.get("competition") or doc.get("slug") or path.stem
    variants = doc.get("variants") or []
    positions = max((int(v.get("position") or 0) for v in variants), default=25) or 25
    for v in variants:
        yield competition, positions, v


def build_system(tax: tax_mod.Taxonomy, prompt_path: Path) -> str:
    template = prompt_path.read_text(encoding="utf-8")
    return template.replace("{CATALOG}", tax.catalog())


def build_user(competition: str, positions: int, v: dict) -> str:
    payload = {
        "competition": competition,
        "position": v.get("position"),
        "positions_in_paper": positions,
        "type": v.get("type"),
        "question": (v.get("question") or "").strip(),
        "choices": v.get("choices"),
        "answer": v.get("answer"),
        "solution": (v.get("solution") or "").strip()[:1200] or None,
        "has_figure": bool(v.get("figure")),
    }
    return "Label this problem:\n\n" + json.dumps(payload, ensure_ascii=False, indent=1)


def normalize_tags(raw, tax: tax_mod.Taxonomy, primary: str | None) -> list[dict]:
    """Accept ["id", ...] or [{"id":..,"weight":..}] and return schema-ready tags."""
    items: list[tuple[str, float | None]] = []
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, str):
                items.append((entry, None))
            elif isinstance(entry, dict) and entry.get("id"):
                items.append((str(entry["id"]), entry.get("weight")))
    out: list[dict] = []
    seen: set[str] = set()
    if primary:
        out.append({"id": primary, "weight": 1.0})
        seen.add(primary)
    default_weights = [0.9, 0.6, 0.45, 0.3]
    for raw_id, weight in items:
        resolved = tax.resolve(raw_id, near=primary.rsplit(".", 1)[0] if primary and "." in primary else None)
        if not resolved or resolved in seen:
            continue
        w = weight if isinstance(weight, (int, float)) and 0 < float(weight) <= 1 else default_weights[min(len(out), 3)]
        out.append({"id": resolved, "weight": round(float(w), 2)})
        seen.add(resolved)
        if len(out) >= 8:
            break
    return out


def _salvage_fields(text: str) -> dict:
    """Recover the few fields we need from a reply that will not parse."""
    if not text:
        return {}
    out: dict = {}
    m = re.search(r'"primary"\s*:\s*"([^"]+)"', text)
    if m:
        out["primary"] = m.group(1)
    m = re.search(r'"difficulty"\s*:\s*(-?\d+(?:\.\d+)?)', text)
    if m:
        try:
            out["difficulty"] = int(round(float(m.group(1))))
        except ValueError:
            pass
    m = re.search(r'"difficulty_confidence"\s*:\s*(\d+(?:\.\d+)?)', text)
    if m:
        try:
            out["difficulty_confidence"] = float(m.group(1))
        except ValueError:
            pass
    m = re.search(r'"tags"\s*:\s*\[(.*?)(?:\]|$)', text, re.S)
    if m:
        found = re.findall(r'"([^"]+)"', m.group(1))
        if found:
            out["tags"] = found[:6]
    m = re.search(r'"why"\s*:\s*"([^"]*)"?', text)
    if m:
        out["why"] = m.group(1)[:200]
    return out


def classify_one(client: llm_mod.Client, system: str, competition: str, positions: int,
                 v: dict, tax: tax_mod.Taxonomy) -> dict:
    qid = question_qid(v)
    reply = client.chat([
        {"role": "system", "content": system},
        {"role": "user", "content": build_user(competition, positions, v)},
    ])
    data = reply.json() or {}
    repaired = bool(data.pop("_repaired", False))
    if not data:
        # Second-chance salvage: even a badly cut reply usually spells out the
        # primary id and the level before it runs out of room.
        data = _salvage_fields(reply.content)
        repaired = bool(data)
    parse_ok = bool(data)
    raw_primary = data.get("primary")
    raw_tags = data.get("tags") or []

    primary = tax.resolve(raw_primary) if raw_primary else None
    if primary and tax.level.get(primary) == 1:
        primary = None  # a bare domain is not a valid primary; let tags decide
    if primary is None:
        for entry in raw_tags:
            cand = tax.resolve(entry if isinstance(entry, str) else str(entry.get("id", "")))
            if cand and tax.level.get(cand, 1) > 1:
                primary = cand
                break
    tags = normalize_tags(raw_tags, tax, primary)

    cls = None
    if primary:
        cls = {
            "state": "done",
            "primary": primary,
            "tags": tags,
            "source": "model",
            "confidence": round(float(data.get("difficulty_confidence") or 0.5), 2),
            "reviewed": False,
            "note": (data.get("why") or "")[:200] or None,
        }
    else:
        cls = {"state": "pending", "note": "model answer did not resolve to any taxonomy id"}

    llm_level = data.get("difficulty")
    if not isinstance(llm_level, int) or not 1 <= llm_level <= 60:
        try:
            llm_level = int(round(float(llm_level)))
        except Exception:  # noqa: BLE001
            llm_level = None
    diff = combine_mod.combine(
        competition=competition,
        position=v.get("position"),
        positions=positions,
        source=v.get("source"),
        llm_level=llm_level,
        llm_confidence=data.get("difficulty_confidence"),
    )

    return {
        "qid": qid,
        "bank": competition,
        "position": v.get("position"),
        "source": v.get("source"),
        "classification": cls,
        "difficulty": diff,
        "issue": normalize_issue(data.get("issue")),
        "llm": {
            "repaired": repaired,
            "level": llm_level,
            "confidence": data.get("difficulty_confidence"),
            "why": data.get("why"),
            "raw_primary": raw_primary,
            "raw_tags": raw_tags,
            "parse_ok": parse_ok,
            "raw_reply": None if parse_ok else (reply.content or "")[:400],
        },
        "usage": {"completion_tokens": reply.completion_tokens,
                  "reasoning_tokens": reply.reasoning_tokens},
        "latency_s": round(reply.latency_s, 2),
    }


def _content_hash(questions: list) -> str:
    """Reuse the validator so the hash rules never drift between the two."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("validate_paper", ROOT / "scripts" / "validate_paper.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.content_hash(questions)


def paper_from_results(rows: list[dict], tax: tax_mod.Taxonomy, title: str, paper_id: str,
                       paper_dir: Path) -> dict:

    questions = []
    for i, row in enumerate(rows, 1):
        q = {
            "n": i,
            "qid": row["qid"],
            "type": row.get("type") or "multiple_choice",
            "question": row.get("question") or "",
            "points": row.get("points") or 6,
        }
        if row.get("choices"):
            q["choices"] = row["choices"]
            q["answer"] = row.get("answer")
        else:
            q["answer"] = row.get("answer") or ""
        if row.get("solution"):
            q["solution"] = row["solution"]
        q["source"] = row.get("source")
        q["classification"] = row["classification"]
        q["difficulty"] = row["difficulty"]
        if row.get("figure"):
            fig = dict(row["figure"])
            src = fig.get("src")
            if src and not src.startswith("http"):
                target = (ROOT / "bank" / "v2" / src).resolve()
                fig["src"] = Path(os.path.relpath(target, paper_dir)).as_posix()
            q["figure"] = fig
        if row.get("issue"):
            # x-* is the schema's escape hatch: a defect note that is not part of
            # the paper itself and must not affect content_hash.
            q["x-issue"] = row["issue"]
        questions.append(q)

    return {
        "format_version": "1.1",
        "paper_version": 1,
        "id": paper_id,
        "title": title,
        "taxonomy": {"id": tax.id, "version": tax.version},
        "instructions": "Generated by classifier/classify.py for validation only.",
        "time_limit_min": 75,
        "total_points": sum(q["points"] for q in questions),
        "questions": questions,
        "content_hash": _content_hash(questions),
    }


def report_issues(out_dir: Path, sample_per_code: int = 3) -> int:
    """Print the defects the grader reported, grouped by code, newest data only."""
    rows = []
    for f in sorted(out_dir.glob("*.jsonl")):
        rows.extend(read_rows(f))
    flagged = [r for r in rows if r.get("issue")]
    if not flagged:
        print(f"no defects reported ({len(rows)} questions scanned)")
        return 0

    by_code: dict[str, list[dict]] = {}
    for r in flagged:
        by_code.setdefault(r["issue"]["code"], []).append(r)

    print(f"defects reported: {len(flagged)} / {len(rows)} questions "
          f"({len(flagged) * 100.0 / max(1, len(rows)):.1f}%)")
    print(f"{'count':>6}  {'blocker':>7}  code")
    for code, items in sorted(by_code.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        blk = sum(1 for r in items if r["issue"]["severity"] == "blocker")
        mark = "" if code in ISSUE_CODES else "  (unknown code)"
        print(f"{len(items):6d}  {blk:7d}  {code}{mark}")

    lines = ["# classifier 上报的题目问题", "",
             f"扫描 {len(rows)} 题，其中 {len(flagged)} 题被标记有问题。", ""]
    for code, items in sorted(by_code.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        title = ISSUE_CODES.get(code, "unknown code")
        lines += [f"## `{code}` — {title}（{len(items)} 题）", ""]
        for r in items[:sample_per_code * 4]:
            q = " ".join((r.get("question") or "").split())[:260]
            lines.append(f"- **{r.get('source')}** ({r['issue']['severity']}) — {r.get('note') or r['issue'].get('note') or ''}")
            lines.append(f"  > {q}")
        lines.append("")

    print()
    for code, items in sorted(by_code.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print(f"--- {code} ({len(items)})")
        for r in items[:sample_per_code]:
            note = r["issue"].get("note") or ""
            print(f"  {r.get('source')} [{r['issue']['severity']}] {note}")
            print(f"    {' '.join((r.get('question') or '').split())[:160]}")
    md = out_dir / "issues.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwritten: {md}")
    return 0


def norm_question(text: str) -> str:
    """Whitespace-insensitive fingerprint used to spot the same problem in two banks.

    The v1 and v2 banks overlap heavily for AMC 10/12 (same problems, different
    scrape), so a second call would buy nothing.
    """
    return re.sub(r"\s+", "", text or "")


def build_reuse_index(out_dir: Path) -> dict[str, dict]:
    """Map fingerprint -> an already-classified row from any earlier bank.

    Rows written on a retired difficulty scale are skipped: their taxonomy labels are
    still fine, but copying them would inject stale levels into a new-scale run.
    """
    idx: dict[str, dict] = {}
    for f in sorted(out_dir.glob("*.jsonl")):
        for row in read_rows(f):
            if (row.get("classification") or {}).get("state") != "done":
                continue
            if (row.get("difficulty") or {}).get("scale") != prior_mod.SCALE:
                continue
            key = norm_question(row.get("question") or "")
            if key and key not in idx:
                idx[key] = row
    return idx


def reuse_row(hit: dict, competition: str, positions: int, v: dict) -> dict:
    """Copy a previous verdict onto this bank's copy of the same question.

    Only the taxonomy labels are portable; the difficulty is recomputed because
    its prior depends on the competition and the slot in the paper.
    """
    llm = hit.get("llm") or {}
    diff = combine_mod.combine(
        competition=competition,
        position=v.get("position"),
        positions=positions,
        source=v.get("source"),
        llm_level=llm.get("level"),
        llm_confidence=llm.get("confidence"),
    )
    return {
        "qid": question_qid(v),
        "bank": competition,
        "position": v.get("position"),
        "source": v.get("source"),
        "classification": dict(hit["classification"]),
        "difficulty": diff,
        "issue": hit.get("issue"),
        "llm": {
            "repaired": repaired,**llm, "reused_from": hit.get("qid")},
        "usage": {"completion_tokens": 0, "reasoning_tokens": 0},
        "latency_s": 0.0,
        "type": v.get("type"),
        "question": v.get("question"),
        "choices": v.get("choices"),
        "answer": v.get("answer"),
        "points": v.get("points"),
        "solution": v.get("solution"),
        "figure": v.get("figure"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Classify + rate bank questions with the local model.")
    ap.add_argument("--bank", help="bank slug prefix, e.g. amc10")
    ap.add_argument("--file", help="explicit bank json path")
    ap.add_argument("--v2", action="store_true", help="read bank/v2 instead of bank/")
    ap.add_argument("--sample", type=int, help="take N evenly spaced variants")
    ap.add_argument("--limit", type=int, help="stop after N classified questions")
    ap.add_argument("--positions", help="only these original paper positions, e.g. 1,10,15,25")
    ap.add_argument("--dry-run", action="store_true", help="print the first prompt, no calls")
    ap.add_argument("--stats", action="store_true", help="summarise existing output files")
    ap.add_argument("--force", action="store_true", help="redo qids already in the output")
    ap.add_argument("--redo-pending", action="store_true",
                    help="only retry the questions recorded as pending in the output")
    ap.add_argument("--issues", action="store_true",
                    help="list the defects the model reported, grouped by code")
    ap.add_argument("--concurrency", type=int, help="parallel requests (default: config run.concurrency)")
    ap.add_argument("--no-reuse", action="store_true",
                    help="re-call the model even when the same question is already "
                         "classified in another bank (v1 and v2 overlap heavily)")
    args = ap.parse_args(argv)

    cfg = load_config()
    out_dir = Path(cfg["paths"]["out"])
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.stats:
        for f in sorted(out_dir.glob("*.jsonl")):
            rows = read_rows(f)
            done = sum(1 for r in rows if r["classification"].get("state") == "done")
            lv = {}
            for r in rows:
                if r["classification"].get("state") != "done":
                    continue
                k = r["difficulty"]["level"]
                lv[k] = lv.get(k, 0) + 1
            flagged = sum(1 for r in rows if r.get("issue"))
            blockers = sum(1 for r in rows if (r.get("issue") or {}).get("severity") == "blocker")
            extra = f", issues={flagged} (blocker={blockers})" if flagged else ""
            print(f"{f.name}: {len(rows)} questions, classified={done}, "
                  f"pending={len(rows) - done}, levels={dict(sorted(lv.items()))}{extra}")
        return 0

    if args.issues:
        return report_issues(out_dir)

    tax = tax_mod.load(cfg["paths"]["taxonomy"])
    system = build_system(tax, ROOT / "classifier" / "prompts" / "classify.md")

    if args.dry_run:
        paths = resolve_paths(cfg, args)
        if not paths:
            print("no bank files matched")
            return 2
        first_comp, positions, first_var = next(iter_variants(paths[0]))
        print(f"system prompt: {len(system)} chars (~{len(system) // 4} tokens)")
        print(f"catalog nodes: {len(tax.nodes)}")
        print("--- user message ---")
        print(build_user(first_comp, positions, first_var)[:1200])
        return 0

    paths = resolve_paths(cfg, args)
    if not paths:
        print("no bank files matched")
        return 2
    print(f"bank files: {[p.name for p in paths]}")

    # v2 gets its own file: the two banks hold different (and partly overlapping)
    # questions, and mixing them would let a v2 row silently overwrite a v1 row
    # with the same content qid.
    _stem = (args.bank or paths[0].stem) + ("_v2" if args.v2 else "")
    out_path = out_dir / f"{_stem}.jsonl"
    done_ids = set()
    pending_ids = set()
    if out_path.exists() and not args.force:
        for row in read_rows(out_path):
            # Only finished rows count as done: a pending row is a question the model
            # failed on, and it must be retried instead of being frozen forever.
            if (row.get("classification") or {}).get("state") == "done":
                done_ids.add(row["qid"])
            else:
                pending_ids.add(row["qid"])
        print(f"resume: {len(done_ids)} already classified, "
              f"{len(pending_ids)} pending will be retried in {out_path.name}")

    work: list[tuple[str, int, dict]] = []
    seen_qid: set[str] = set()
    want_pos = set()
    if args.positions:
        want_pos = {int(x) for x in str(args.positions).replace(" ", "").split(",") if x}
    for path in paths:
        for competition, positions, v in iter_variants(path):
            qid = question_qid(v)
            if qid in done_ids or qid in seen_qid:
                continue
            if args.redo_pending and qid not in pending_ids:
                continue
            if want_pos and int(v.get("position") or 0) not in want_pos:
                continue
            if not (v.get("question") or "").strip():
                continue
            seen_qid.add(qid)
            work.append((competition, positions, v))
    if args.sample:
        step = max(1, len(work) // args.sample)
        work = work[::step][: args.sample]
    if args.limit:
        work = work[: args.limit]

    reuse_idx: dict[str, dict] = {} if args.no_reuse else build_reuse_index(out_dir)
    reused, todo = [], []
    for item in work:
        hit = reuse_idx.get(norm_question(item[2].get("question") or ""))
        (reused if hit is not None else todo).append((item, hit) if hit is not None else item)
    work = todo
    print(f"to classify: {len(work)} (reused from other banks: {len(reused)})")

    client = llm_mod.Client(cfg["endpoint"], cfg["model"], cfg["params"],
                            retries=cfg["run"]["retries"], timeout_s=cfg["run"]["timeout_s"])
    # Refuse to start against a dead server: every request would burn its full
    # timeout, so a hung box used to look like "very slow progress" for hours.
    ok, why = client.health()
    if not ok:
        print(f"[abort] inference server unreachable: {why}")
        print("[abort] rows already classified are saved; re-run the same command later")
        raise RuntimeError(f"inference server unreachable: {why}")
    rows: list[dict] = []
    t0 = time.time()
    conc = int(args.concurrency or cfg["run"]["concurrency"])
    with out_path.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=conc) as pool:
        for (competition, positions, v), hit in reused:
            row = reuse_row(hit, competition, positions, v)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows.append(row)
        if reused:
            fh.flush()
        futures = {pool.submit(classify_one, client, system, c, n, v, tax): v for c, n, v in work}
        for i, fut in enumerate(as_completed(futures), 1):
            v = futures[fut]
            try:
                row = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"  [{i}/{len(work)}] FAIL pos{v.get('position')}: {e}")
                continue
            row["type"] = v.get("type")
            row["question"] = v.get("question")
            row["choices"] = v.get("choices")
            row["answer"] = v.get("answer")
            row["points"] = v.get("points")
            row["solution"] = v.get("solution")
            row["figure"] = v.get("figure")
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            rows.append(row)
            cls = row["classification"]
            print(f"  [{i}/{len(work)}] pos{v.get('position')} L{row['difficulty']['level']} "
                  f"{cls.get('primary') or 'PENDING'} {row['latency_s']}s")

    print(f"done in {time.time() - t0:.1f}s; client stats: {client.stats()}")

    if rows:
        all_rows = rows
        if out_path.exists():
            all_rows = read_rows(out_path)
        stem = (args.bank or paths[0].stem)
        paper_path = out_dir / f"{stem}_smoke.json"
        paper = paper_from_results(all_rows, tax, f"{stem} classifier smoke",
                                    f"{stem}_smoke", out_dir)
        paper_path.write_text(json.dumps(paper, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"paper written: {paper_path.relative_to(ROOT)} ({len(paper['questions'])} questions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
