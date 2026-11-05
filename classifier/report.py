"""Build a single-file HTML review page for classifier output.

The classifier writes one JSONL per bank under ``classifier/out/``. Each row
carries the question, its ``classification``, its ``difficulty`` and (when the
model spotted something wrong) an ``issue`` object. This module turns those
rows into one self-contained HTML page so a human can scan problems fast.

Two ways to use it:

    python -m classifier.report                 # writes classifier/out/report.html
    python -m classifier.report --serve         # http://127.0.0.1:8021, rebuilt per request

``--serve`` re-reads the JSONL on every request, so refreshing the page while a
batch is running shows the new rows. The page also self-refreshes every N
seconds (toggle in the toolbar) -- that is the "watch it live" mode.

Rows that were classified under the retired 1-5 scale are skipped by default
(``--all-scales`` keeps them); they are labelled ``legacy5`` and would otherwise
mix two incompatible difficulty scales in one table.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "classifier" / "out"
CURRENT_SCALE = "amc20"

SEVERITY_ORDER = {"blocker": 0, "warn": 1}
CODE_LABELS = {
    "missing_figure": "缺图",
    "broken_latex": "LaTeX 坏",
    "truncated_stem": "题干截断",
    "answer_not_in_choices": "答案不在选项里",
    "duplicate_choices": "选项重复",
    "missing_choices": "缺选项",
    "missing_answer": "缺答案",
    "missing_solution": "缺解析",
    "not_a_problem": "不像题目",
    "solution_inside_stem": "解析混进题干",
}


# ---------------------------------------------------------------- row loading
def _iter_jsonl(path: Path):
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def load_rows(out_dir: Path = OUT_DIR, all_scales: bool = False) -> tuple[dict, list]:
    """Return ({qid: row}, [bank files seen]). Last line per qid wins."""
    by_qid: dict[str, dict] = {}
    banks: list[str] = []
    for path in sorted(out_dir.glob("*.jsonl")):
        banks.append(path.stem)
        for row in _iter_jsonl(path):
            qid = row.get("qid")
            if not qid:
                continue
            scale = (row.get("difficulty") or {}).get("scale") or "legacy5"
            if not all_scales and scale != CURRENT_SCALE:
                continue
            row["_bank_file"] = path.stem
            by_qid[qid] = row
    return by_qid, banks


def _row_issue(row: dict) -> dict | None:
    issue = row.get("issue")
    if not isinstance(issue, dict):
        return None
    if not issue.get("code"):
        return None
    return issue


def summarize(rows: list[dict]) -> dict:
    codes: dict[str, dict] = {}
    sev = {"blocker": 0, "warn": 0}
    by_bank: dict[str, int] = {}
    levels: dict[int, int] = {}
    pending = 0
    for row in rows:
        level = (row.get("difficulty") or {}).get("level")
        if isinstance(level, int):
            levels[level] = levels.get(level, 0) + 1
        cls = row.get("classification") or {}
        if cls.get("state") == "pending" or not cls:
            pending += 1
        issue = _row_issue(row)
        if not issue:
            continue
        code = issue.get("code") or "unknown"
        bucket = codes.setdefault(code, {"count": 0, "blocker": 0, "warn": 0})
        bucket["count"] += 1
        severity = issue.get("severity") if issue.get("severity") in sev else "warn"
        bucket[severity] += 1
        sev[severity] += 1
        bank = row.get("_bank_file") or "?"
        by_bank[bank] = by_bank.get(bank, 0) + 1
    return {
        "total": len(rows),
        "with_issue": sum(b["count"] for b in codes.values()),
        "severity": sev,
        "codes": codes,
        "by_bank": by_bank,
        "levels": levels,
        "pending": pending,
    }


# ------------------------------------------------------------------- rendering
def _choices_list(raw) -> list[str]:
    """Bank v1 stores choices as a list; bank v2 (papers) stores the same thing
    as an {"A": ..., "B": ...} mapping. The page renders a list, so flatten to
    one form here - a dict reaching the browser used to blow up the whole
    render (TypeError: r.choices.map is not a function) and leave the page blank.
    """
    if isinstance(raw, dict):
        return [f"{k}. {v}" for k, v in raw.items()]
    if isinstance(raw, list):
        return [str(c) for c in raw]
    return []


def _payload(rows: list[dict]) -> list[dict]:
    """Trim rows down to what the page actually shows (keeps the file small)."""
    out = []
    for row in rows:
        issue = _row_issue(row)
        cls = row.get("classification") or {}
        diff = row.get("difficulty") or {}
        out.append({
            "qid": row.get("qid"),
            "bank": row.get("_bank_file"),
            "source": row.get("source"),
            "position": row.get("position"),
            "type": row.get("type"),
            "question": row.get("question") or "",
            "choices": _choices_list(row.get("choices")),
            "answer": row.get("answer"),
            "solution": (row.get("solution") or "")[:1200],
            "has_figure": bool(row.get("figure")),
            "level": diff.get("level"),
            "score": diff.get("score"),
            "band": diff.get("band"),
            "primary": cls.get("primary"),
            "tags": [t.get("id") if isinstance(t, dict) else t for t in (cls.get("tags") or [])],
            "state": cls.get("state") or "none",
            "why": (row.get("llm") or {}).get("why"),
            "issue": issue,
        })
    out.sort(key=lambda r: (
        SEVERITY_ORDER.get((r["issue"] or {}).get("severity"), 9),
        r["bank"] or "",
        r["position"] or 0,
    ))
    return out


PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>题目问题检查</title>
<style>
  :root {
    --bg:#0f1218; --panel:#161b23; --panel2:#1d232d; --line:#2a323e;
    --ink:#e6ebf2; --ink2:#9aa7b8; --ink3:#67748a;
    --blocker:#ff6b6b; --warn:#e0a63c; --ok:#4fb286; --accent:#5b9cf8;
  }
  * { box-sizing:border-box; }
  html,body { margin:0; background:var(--bg); color:var(--ink);
    font:14px/1.55 -apple-system,"Segoe UI",Helvetica,Arial,"Microsoft YaHei",sans-serif; }
  header { position:sticky; top:0; z-index:9; background:rgba(15,18,24,.94);
    backdrop-filter:blur(6px); border-bottom:1px solid var(--line); padding:10px 18px; }
  h1 { font-size:15px; margin:0 0 8px; font-weight:650; letter-spacing:.3px; }
  h1 small { color:var(--ink3); font-weight:400; margin-left:10px; font-size:12px; }
  .stats { display:flex; flex-wrap:wrap; gap:14px; font-size:12.5px; color:var(--ink2); margin-bottom:9px; }
  .stats b { color:var(--ink); font-weight:650; }
  .stats .b-blocker b { color:var(--blocker); }
  .stats .b-warn b { color:var(--warn); }
  .bar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
  .chip { border:1px solid var(--line); background:var(--panel); color:var(--ink2);
    border-radius:999px; padding:3px 10px; font-size:12.5px; cursor:pointer; user-select:none; }
  .chip:hover { border-color:var(--accent); color:var(--ink); }
  .chip.on { background:var(--accent); border-color:var(--accent); color:#08101c; font-weight:650; }
  .chip .n { opacity:.7; margin-left:5px; font-variant-numeric:tabular-nums; }
  input[type=search], select { background:var(--panel); color:var(--ink); border:1px solid var(--line);
    border-radius:7px; padding:4px 9px; font-size:13px; outline:none; }
  input[type=search] { min-width:210px; }
  input[type=search]:focus, select:focus { border-color:var(--accent); }
  label.tiny { font-size:12.5px; color:var(--ink2); display:inline-flex; align-items:center; gap:5px; }
  main { padding:14px 18px 60px; }
  .row { border:1px solid var(--line); border-radius:10px; background:var(--panel);
    margin-bottom:9px; overflow:hidden; }
  .row.blocker { border-left:3px solid var(--blocker); }
  .row.warn { border-left:3px solid var(--warn); }
  .head { display:flex; gap:10px; align-items:baseline; padding:9px 12px; cursor:pointer; }
  .head:hover { background:var(--panel2); }
  .code { font-size:11.5px; font-weight:650; padding:1px 7px; border-radius:5px;
    background:var(--panel2); border:1px solid var(--line); white-space:nowrap; }
  .row.blocker .code { color:var(--blocker); border-color:#4a2429; }
  .row.warn .code { color:var(--warn); border-color:#4a3c1e; }
  .where { color:var(--ink3); font-size:12px; white-space:nowrap; }
  .stem { color:var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; min-width:0; }
  .lvl { font-variant-numeric:tabular-nums; color:var(--ink2); font-size:12px; white-space:nowrap; }
  .note { padding:0 12px 10px 12px; color:var(--warn); font-size:13px; }
  .detail { display:none; padding:0 12px 14px; border-top:1px solid var(--line); background:var(--panel2); }
  .row.open .detail { display:block; }
  .detail h4 { font-size:11.5px; text-transform:uppercase; letter-spacing:.6px;
    color:var(--ink3); margin:12px 0 4px; font-weight:650; }
  pre { margin:0; white-space:pre-wrap; word-break:break-word; font:13px/1.5 ui-monospace,Consolas,monospace; color:var(--ink); }
  .meta { display:flex; flex-wrap:wrap; gap:6px; margin-top:6px; }
  .tag { font-size:11.5px; color:var(--ink2); background:var(--panel); border:1px solid var(--line);
    border-radius:5px; padding:1px 7px; }
  .tag.p { color:var(--accent); border-color:#28405f; }
  .done { margin-left:auto; font-size:12px; color:var(--ink3); white-space:nowrap; }
  .done input { vertical-align:-2px; margin-right:4px; }
  .row.checked { opacity:.42; }
  .empty { color:var(--ink3); padding:40px 0; text-align:center; }
  .live { font-size:12px; color:var(--ok); }
  .live.off { color:var(--ink3); }
</style>
</head>
<body>
<header>
  <h1>题目问题检查<small id="meta"></small></h1>
  <div class="stats" id="stats"></div>
  <div class="bar">
    <span class="chip on" data-sev="all">全部</span>
    <span class="chip" data-sev="blocker">blocker</span>
    <span class="chip" data-sev="warn">warn</span>
    <select id="bank"></select>
    <select id="state">
      <option value="all">所有题目状态</option>
      <option value="pending">只看 pending</option>
      <option value="done">只看已分类</option>
    </select>
    <input type="search" id="q" placeholder="搜题干 / 来源 / qid">
    <label class="tiny"><input type="checkbox" id="hideDone"> 隐藏已勾选</label>
    <label class="tiny"><input type="checkbox" id="auto" checked> 自动刷新</label>
    <span class="live" id="live"></span>
  </div>
</header>
<main><div id="list"></div><div class="empty" id="empty" style="display:none">没有符合条件的题目</div></main>
<script id="data" type="application/json">__DATA__</script>
<script>
const RAW = JSON.parse(document.getElementById('data').textContent);
const CODES = __CODES__;
const META = __META__;
const KEY = 'mt_issue_checked_v1';
let checked = new Set();
try { checked = new Set(JSON.parse(localStorage.getItem(KEY) || '[]')); } catch (e) {}
let sev = 'all', bank = 'all', state = 'all', needle = '', hideDone = false;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function chipLabel(code) { return CODES[code] || code; }

function buildFilters() {
  const banks = [...new Set(RAW.map(r => r.bank))].sort();
  $('bank').innerHTML = '<option value="all">全部题库</option>' +
    banks.map(b => `<option value="${esc(b)}">${esc(b)} (${RAW.filter(r => r.bank === b).length})</option>`).join('');
}

function stats() {
  const shown = filtered().length;
  $('stats').innerHTML =
    `<span>题目 <b>${RAW.length}</b></span>` +
    `<span class="b-blocker">blocker <b>${META.severity.blocker}</b></span>` +
    `<span class="b-warn">warn <b>${META.severity.warn}</b></span>` +
    `<span>有上报 <b>${META.with_issue}</b></span>` +
    `<span>当前显示 <b>${shown}</b></span>` +
    `<span>标尺 <b>${esc(META.scale)}</b></span>`;
  $('meta').textContent = `生成于 ${META.built_at} · 题库 ${META.banks.join(' / ')}`;
}

function filtered() {
  const n = needle.toLowerCase();
  return RAW.filter(r => {
    if (sev !== 'all' && (r.issue || {}).severity !== sev) return false;
    if (bank !== 'all' && r.bank !== bank) return false;
    if (state !== 'all' && r.state !== state) return false;
    if (hideDone && checked.has(r.qid)) return false;
    if (!n) return true;
    return (r.question + ' ' + (r.source || '') + ' ' + r.qid).toLowerCase().includes(n);
  });
}

function card(r) {
  const sevCls = (r.issue || {}).severity || '';
  const code = r.issue ? `<span class="code">${esc(chipLabel(r.issue.code))}</span>` : '';
  const note = r.issue && r.issue.note ? `<div class="note">${esc(r.issue.note)}</div>` : '';
  const lvl = r.level == null ? '–' : `L${r.level}`;
  const tags = (r.tags || []).map(t => `<span class="tag">${esc(t)}</span>`).join('');
  const primary = r.primary ? `<span class="tag p">${esc(r.primary)}</span>` : '';
  const choices = (Array.isArray(r.choices) ? r.choices : []).map((c, i) =>
    `<div>${String.fromCharCode(65 + i)}. ${esc(c)}</div>`).join('');
  return `<div class="row ${sevCls} ${checked.has(r.qid) ? 'checked' : ''}" data-qid="${esc(r.qid)}">
    <div class="head">
      <span class="code" style="${r.issue ? '' : 'display:none'}"></span>
      ${code}
      <span class="where">${esc(r.bank)} · ${esc(r.source || '')}</span>
      <span class="stem">${esc(r.question)}</span>
      <span class="lvl">${lvl}${r.score != null ? ' · ' + Number(r.score).toFixed(1) : ''}</span>
      <label class="done"><input type="checkbox" class="chk" ${checked.has(r.qid) ? 'checked' : ''}>已处理</label>
    </div>
    ${note}
    <div class="detail">
      <h4>题干</h4><pre>${esc(r.question)}</pre>
      ${choices ? `<h4>选项</h4><pre>${choices}</pre>` : ''}
      <h4>答案</h4><pre>${esc(r.answer == null ? '（无）' : r.answer)}</pre>
      ${r.solution ? `<h4>解析（截断 1200 字）</h4><pre>${esc(r.solution)}</pre>` : '<h4>解析</h4><pre>（无）</pre>'}
      <h4>分类</h4>
      <div class="meta">${primary}${tags}${r.has_figure ? '<span class="tag">带图</span>' : ''}
        <span class="tag">${esc(r.state)}</span>
        <span class="tag">${esc(r.type || '')}</span>
        <span class="tag">${esc(r.qid)}</span></div>
      ${r.why ? `<h4>模型理由</h4><pre>${esc(r.why)}</pre>` : ''}
    </div>
  </div>`;
}

function render() {
  const rows = filtered();
  $('list').innerHTML = rows.map(card).join('');
  $('empty').style.display = rows.length ? 'none' : 'block';
  stats();
  document.querySelectorAll('.row').forEach(el => {
    el.querySelector('.head').addEventListener('click', (ev) => {
      if (ev.target.classList.contains('chk')) return;
      el.classList.toggle('open');
    });
    const chk = el.querySelector('.chk');
    chk.addEventListener('change', () => {
      const qid = el.dataset.qid;
      if (chk.checked) checked.add(qid); else checked.delete(qid);
      el.classList.toggle('checked', chk.checked);
      try { localStorage.setItem(KEY, JSON.stringify([...checked])); } catch (e) {}
    });
  });
}

document.querySelectorAll('[data-sev]').forEach(c => c.addEventListener('click', () => {
  document.querySelectorAll('[data-sev]').forEach(x => x.classList.remove('on'));
  c.classList.add('on');
  sev = c.dataset.sev;
  render();
}));
$('bank').addEventListener('change', e => { bank = e.target.value; render(); });
$('state').addEventListener('change', e => { state = e.target.value; render(); });
$('q').addEventListener('input', e => { needle = e.target.value; render(); });
$('hideDone').addEventListener('change', e => { hideDone = e.target.checked; render(); });

// live mode: only meaningful when served (file:// reload is fine too)
const served = location.protocol.startsWith('http');
let tick = 15;
$('live').textContent = served ? `自动刷新 ${tick}s` : '本地文件，手动刷新';
if (!served) { $('auto').checked = false; $('auto').disabled = true; $('live').className = 'live off'; }
setInterval(() => {
  if (!$('auto').checked) { $('live').textContent = '自动刷新已暂停'; return; }
  tick -= 1;
  $('live').textContent = `自动刷新 ${Math.max(tick, 0)}s`;
  if (tick <= 0) location.reload();
}, 1000);

buildFilters();
render();
</script>
</body>
</html>
"""


def render_html(rows: list[dict], banks: list[str], all_scales: bool) -> str:
    summary = summarize(list(rows.values()))
    payload = _payload(list(rows.values()))
    meta = {
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "banks": banks,
        "scale": "*" if all_scales else CURRENT_SCALE,
        "severity": summary["severity"],
        "with_issue": summary["with_issue"],
    }
    page = PAGE
    page = page.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    page = page.replace("__CODES__", json.dumps(CODE_LABELS, ensure_ascii=False))
    page = page.replace("__META__", json.dumps(meta, ensure_ascii=False))
    return page


def build(out_path: Path, all_scales: bool, all_rows: bool) -> tuple[int, int]:
    rows, banks = load_rows(OUT_DIR, all_scales=all_scales)
    if not all_rows:
        rows = {qid: r for qid, r in rows.items() if _row_issue(r)}
    html_text = render_html(rows, banks, all_scales)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_text, encoding="utf-8", newline="\n")
    summary = summarize(list(rows.values()))
    return len(rows), summary["with_issue"]


def serve(port: int, all_scales: bool, all_rows: bool) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path.split("?")[0] not in ("/", "/report.html", "/index.html"):
                self.send_error(404)
                return
            try:
                rows, banks = load_rows(OUT_DIR, all_scales=all_scales)
                if not all_rows:
                    rows = {qid: r for qid, r in rows.items() if _row_issue(r)}
                body = render_html(rows, banks, all_scales).encode("utf-8")
            except Exception as exc:  # keep the server alive, show the error
                body = f"<pre>render failed: {exc}</pre>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):  # quieter console
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[serve] http://127.0.0.1:{port}/  (Ctrl+C to stop)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("[serve] stopped", flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="HTML review page for classifier issues")
    ap.add_argument("--out", default=str(OUT_DIR / "report.html"), help="output html path")
    ap.add_argument("--serve", action="store_true", help="serve on http://127.0.0.1:<port>/ and rebuild per request")
    ap.add_argument("--port", type=int, default=8021)
    ap.add_argument("--all-scales", action="store_true", help="include rows classified with the retired 1-5 scale")
    ap.add_argument("--all-rows", action="store_true", help="embed clean rows too (default: only rows with an issue)")
    args = ap.parse_args(argv)

    if args.serve:
        serve(args.port, args.all_scales, args.all_rows)
        return 0

    count, issues = build(Path(args.out), args.all_scales, args.all_rows)
    print(f"[report] rows={count} with_issue={issues} -> {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
