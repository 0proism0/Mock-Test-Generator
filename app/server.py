"""MockTest Maker — localhost web app.

Run:  .venv/bin/python app/server.py  (then open http://localhost:8020)
Stdlib only. Serves tests from tests/*.json, generates new tests from bank/<slug>_*.json.
"""
import hashlib
import io
import json
import mimetypes
import os
import random
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys_path = str(Path(__file__).resolve().parent)
if sys_path not in os.sys.path:
    os.sys.path.insert(0, sys_path)
from latex_wrap import wrap_bare_math

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
BANK = ROOT / "bank"
# Version 2 banks: one JSON per competition slug, questions may carry figures.
# They sit beside the classic banks so both versions stay selectable; a missing
# file simply means "this competition has no figure bank yet".
BANK_V2 = BANK / "v2"
BANK_V2_FIGURES = BANK_V2 / "figures"
BANK_VERSIONS = (1, 2)
# Topic taxonomy (paper format v1.1): questions carry classification tags that
# point at taxonomy/<id>.json. The UI only needs id -> label.
TAXONOMY_DIR = ROOT / "taxonomy"
DEFAULT_TAXONOMY = "amc-v1"
STATIC = ROOT / "app" / "static"
SHSID_DIR = ROOT / "raw" / "shsid"  # crawled by scraper/shsid_crawler.py (OpenSHSID port)
WEB_DIST = ROOT / "app" / "web" / "dist"  # built React app (see app/web); legacy STATIC is the fallback
RESULTS = ROOT / "results.jsonl"
# User-filed "this question is broken" reports: append-only JSONL, gitignored.
REPORTS_FILE = ROOT / "reports.jsonl"
REPORT_REASONS = (
    "wrong_statement", "wrong_answer", "wrong_solution", "broken_latex",
    "missing_figure", "duplicate_choices", "not_a_problem", "other",
)
REPORT_NOTE_MAX = 600
USERS_DIR = ROOT / "users"
USERS_FILE = ROOT / "users.json"
SESSIONS_FILE = ROOT / "sessions.json"
SESSION_DAYS = 7
# Default 8020 (8000 is commonly taken by other local dev servers); override with MOCKTEST_PORT.
PORT = int(os.environ.get("MOCKTEST_PORT", "8020"))

COMP_META = {  # slug -> (display name, n_q, tlim, category, rounds, family)
    "amc8": ("AMC 8", 25, 40, "Math", None, "AMC"),
    "amc10": ("AMC 10", 25, 75, "Math", None, "AMC"),
    "amc12": ("AMC 12", 25, 75, "Math", None, "AMC"),
    "aime": ("AIME", 15, 180, "Math", None, "AIME"),
    "imo": ("IMO", 6, 270, "Math", None, "IMO"),
    "usamo": ("USAMO", 6, 270, "Math", None, "USAMO"),
    "putnam": ("Putnam", 12, 360, "Math", None, "Putnam"),
    "apmo": ("APMO", 5, 240, "Math", None, "APMO"),
    "hmmt": ("HMMT", 10, 50, "Math", {"General": (10, 50), "Theme": (10, 50)}, "HMMT"),
    "mathcounts": ("MATHCOUNTS", 30, 40, "Math", {"Sprint": (30, 40), "Target": (8, 24), "Team": (10, 20)}, "MATHCOUNTS"),
    "smt": ("SMT", 25, 110, "Math", {"General": (25, 110), "Algebra": (10, 50), "Calculus": (10, 50), "Discrete": (10, 50), "Geometry": (10, 50), "Team": (15, 50)}, "SMT"),
    "pumac": ("PUMaC", 8, 60, "Math", {"Algebra": (8, 60), "Geometry": (8, 60), "Combinatorics": (8, 60), "Number Theory": (8, 60), "Individual Finals": (4, 60), "Team": (15, 90), "Power": (11, 90)}, "PUMaC"),
    "bmt": ("BMT", 25, 90, "Math", {"General": (25, 90), "Algebra": (11, 60), "Calculus": (11, 60), "Discrete": (11, 60), "Geometry": (11, 60), "Guts": (27, 75), "Power": (3, 60), "Individual": (25, 60), "Team": (24, 60)}, "BMT"),
    "bmmt": ("BMMT", 20, 60, "Math", {"Individual": (20, 60), "Team": (19, 60)}, "BMMT"),
    "cmimc": ("CMIMC", 10, 60, "Math", {"Algebra": (10, 50), "Combinatorics": (10, 50), "Geometry": (10, 50), "Computer Science": (10, 50), "Team": (10, 30)}, "CMIMC"),
    "comc": ("COMC", 8, 150, "Math", None, "COMC"),
    "cmo": ("CMO", 5, 180, "Math", None, "CMO"),
    "usamts": ("USAMTS", 5, 240, "Math", None, "USAMTS"),
    "ukmt": ("UKMT", 25, 60, "Math", None, "UKMT"),
    "mathkangaroo": ("Math Kangaroo", 10, 45, "Math", None, "Math Kangaroo"),
    "fma": ("F=ma", 25, 75, "Physics", None, "F=ma"),
    "physicsbowl": ("Physics Bowl", 40, 45, "Physics", None, "Physics Bowl"),
    "usapho": ("USAPhO", 6, 180, "Physics", None, "USAPhO"),
    "bpho_r1": ("BPhO Round 1", 10, 60, "Physics", None, "BPhO"),
    "bpho_r2": ("BPhO Round 2", 4, 180, "Physics", None, "BPhO"),
    "ipho": ("IPhO", 3, 300, "Physics", {"Theory": (3, 300)}, "IPhO"),
    "sat_physics": ("SAT Physics", 75, 60, "Physics", None, "SAT Physics"),
    "ap_physics1": ("AP Physics 1", 50, 90, "Physics", None, "AP Physics"),
    "ap_physics2": ("AP Physics 2", 50, 90, "Physics", None, "AP Physics"),
    "ap_physics_c_mech": ("AP Physics C: Mechanics", 35, 45, "Physics", None, "AP Physics C"),
    "ap_physics_c_em": ("AP Physics C: E&M", 35, 45, "Physics", None, "AP Physics C"),
    "gre_physics": ("GRE Physics", 100, 170, "Physics", None, "GRE Physics"),
}

ROUND_PATTERNS = {  # slug -> regex extracting round name from a variant's source string
    "mathcounts": r"(Sprint|Target|Team)",
    "hmmt": r"(General|Theme)",
    "smt": r"SMT (\w+) Problem",
    "pumac": r"PUMaC ([\w ]+?) Problem",
    "bmt": r"(?:BMT|BmMT) (\w+) Problem",
    "bmmt": r"BMMT (\w+) Problem",
    "cmimc": r"CMIMC ([\w ]+?) Problem",
}

# Default points per question for competitions where every problem has the same weight.
# Competitions not listed here fall back to 1 point per question.
DEFAULT_POINTS = {
    "amc8": 1,
    "amc10": 6,
    "amc12": 6,
    "aime": 1,
    "fma": 1,
    "physicsbowl": 1,
    "hmmt": 1,
    "smt": 1,
    "bmmt": 1,
}

CATEGORY_ORDER = ["Math", "Physics", "Chemistry", "Biology", "Informatics",
                  "Astronomy & Earth", "Economics", "Linguistics", "Other"]


# ---------- Auth helpers ----------

def _load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return salt, key


def _verify_password(password, salt, key):
    _, check = _hash_password(password, salt)
    return secrets.compare_digest(key, check)


def _read_users():
    return {u["username"]: u for u in _load_json(USERS_FILE, [])}


def _write_users(users):
    _save_json(USERS_FILE, list(users.values()))


def _read_sessions():
    now = time.time()
    sessions = _load_json(SESSIONS_FILE, [])
    # drop expired
    return {s["id"]: s for s in sessions if s.get("expires_at", 0) > now}


def _write_sessions(sessions):
    _save_json(SESSIONS_FILE, list(sessions.values()))


def _make_session(username):
    sessions = _read_sessions()
    sid = secrets.token_urlsafe(32)
    sessions[sid] = {
        "id": sid,
        "username": username,
        "expires_at": time.time() + SESSION_DAYS * 86400,
    }
    _write_sessions(sessions)
    return sid


def _delete_session(sid):
    sessions = _read_sessions()
    sessions.pop(sid, None)
    _write_sessions(sessions)


def _parse_cookies(cookie_header):
    if not cookie_header:
        return {}
    out = {}
    for part in cookie_header.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            out[k] = v
    return out


def current_user(cookie_header):
    cookies = _parse_cookies(cookie_header)
    sid = cookies.get("session_id")
    if not sid:
        return None
    sessions = _read_sessions()
    s = sessions.get(sid)
    if not s:
        return None
    touch_user(s["username"])
    return s["username"]


# --- online presence (in-memory; single process) ---
ONLINE_WINDOW = 90  # seconds without a request => offline
_active = {}        # username -> last request timestamp
_active_lock = threading.Lock()


def touch_user(username):
    if username:
        with _active_lock:
            _active[username] = time.time()


def is_online(username):
    with _active_lock:
        ts = _active.get(username)
    return bool(ts and time.time() - ts < ONLINE_WINDOW)


# --- friends & chat storage ---
FRIENDS_FILE = ROOT / "friends.json"
MESSAGES_FILE = ROOT / "messages.jsonl"
_store_lock = threading.Lock()

# --- PK (1v1 battle / race) storage ---
PK_DIR = ROOT / "pk"
PK_LEVELS = {"easy": (0.0, 0.4), "medium": (0.4, 0.75), "hard": (0.75, 1.001)}
PK_INVITE_TTL_S = 300  # pending challenges expire after 5 minutes
CLASSES_FILE = ROOT / "classes.json"
CLASS_REPORTS_FILE = ROOT / "class_reports.jsonl"


def _read_classes():
    return _load_json(CLASSES_FILE, {})


def _write_classes(d):
    _save_json(CLASSES_FILE, d)


# --- school documents storage ---
SCHOOL_DOCS_FILE = ROOT / "school_docs.json"
SCHOOL_DOCS_DIR = ROOT / "school_docs"
DOC_MAX_BYTES = 25 * 1024 * 1024  # 25 MB raw
DOC_CATEGORIES = ["science", "physics", "chemistry", "biology", "math",
                  "computer science", "english", "history", "geography", "other"]
DOC_MIME = {
    "pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword", "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel", "csv": "text/csv", "txt": "text/plain; charset=utf-8",
    "md": "text/markdown; charset=utf-8", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
}


def _read_school_docs():
    return _load_json(SCHOOL_DOCS_FILE, {})


def _write_school_docs(d):
    _save_json(SCHOOL_DOCS_FILE, d)


def _doc_file(doc):
    return SCHOOL_DOCS_DIR / f"{doc['id']}.{doc['ext']}"


def _norm_school(s):
    return " ".join((s or "").split()).casefold()


def _user_school_entry(user):
    """(display_name, normalized) of the user's school, or (None, None)."""
    u = _read_users().get(user) or {}
    s = (u.get("school") or "").strip()
    return (s, _norm_school(s)) if s else (None, None)


def _doc_visible_to(doc, school_norm):
    return _norm_school(doc.get("school")) == school_norm


# ---------- worksheets (upload a text/json/pdf/image file -> printable worksheet) ----------
WORKSHEETS_DIR = ROOT / "worksheets"
WS_MAX_BYTES = 10 * 1024 * 1024  # 10 MB raw (pdf/images)
WS_TEXT_MAX_BYTES = 1024 * 1024  # 1 MB for text files
WS_EXTS = ("txt", "md", "json", "docx", "pdf", "png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff")
WS_TEXT_EXTS = ("txt", "md", "json")
WS_IMAGE_EXTS = ("png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff")
WS_Q_RE = re.compile(r"^\s*(?:#{1,6}\s*)?(?:q(?:uestion)?\s*)?(?:第\s*)?(\d{1,3})(?:\s*题)?\s*[、.)）:：]\s*", re.I)
WS_CHOICE_RE = re.compile(r"^\s*([A-Ea-e])[.)．]\s+")
WS_ANS_SECTION_RE = re.compile(r"^\s*#*\s*(?:answers?|answer key|keys?|答案|参考答案|解答)\s*[:：]?\s*$", re.I)
WS_ANS_ENTRY_RE = re.compile(r"^\s*(\d{1,3})[.)．\、]\s+(.+)$")
WS_INLINE_ANS_RE = re.compile(r"^\s*\**\s*(?:answer|答案)\s*[:：]\s*\**\s*(.+?)\s*$", re.I)


def parse_worksheet_text(text, fallback_title):
    """Parse numbered questions from plain text / markdown.

    Questions start with '1.' / '2)' / 'Q3.' / '## 4.'; choices are lines 'A.'–'E.';
    an 'Answers:' section ('1. B', '2) 42') or an inline 'Answer: …' last line
    fills in answers. Returns (title, items).
    """
    title = None
    questions = {}   # original number -> {"lines": [], "choices": {letter: text}}
    answers = {}     # original number -> answer text
    section = None   # None | "answers"
    order = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if title is None:
            m_head = re.match(r"^\s*#\s+(.+)$", line)
            if m_head:
                title = m_head.group(1).strip()[:120]
                continue
        if WS_ANS_SECTION_RE.match(line):
            section = "answers"
            continue
        m_ans = WS_ANS_ENTRY_RE.match(line)
        if section == "answers" and m_ans:
            answers[int(m_ans.group(1))] = m_ans.group(2).strip()
            continue
        m_q = WS_Q_RE.match(line)
        if m_q and section != "answers":
            n = int(m_q.group(1))
            if n not in questions:
                questions[n] = {"lines": [], "choices": {}}
                order.append(n)
            rest = line[m_q.end():].strip()
            if rest:
                questions[n]["lines"].append(rest)
            continue
        m_c = WS_CHOICE_RE.match(line)
        if section != "answers" and order and m_c:
            questions[order[-1]]["choices"][m_c.group(1).upper()] = line[m_c.end():].strip()
            continue
        if section != "answers" and order:
            questions[order[-1]]["lines"].append(line)
    items = []
    for n in order:
        q = questions[n]
        lines = list(q["lines"])
        while lines and not lines[-1].strip():
            lines.pop()
        ans = answers.get(n, "")
        if lines:
            m_inline = WS_INLINE_ANS_RE.match(lines[-1])
            if m_inline:
                ans = ans or m_inline.group(1).strip()
                lines.pop()
        body = "\n".join(lines).strip()
        if not body and not q["choices"]:
            continue
        letters = sorted(q["choices"])
        choices = [q["choices"][L] for L in letters] if letters else []
        items.append({"question": body, "choices": choices, "answer": ans,
                      "solution": "", "points": 1})
    if not items:
        raise ValueError("no questions found — number your questions 1. 2. 3. …")
    return (title or fallback_title), items


def parse_worksheet_json(text, fallback_title):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}")
    raw = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(raw, list) or not raw:
        raise ValueError('JSON must be a list of questions or {"questions": [...]}')
    items = []
    for i, q in enumerate(raw, 1):
        if not isinstance(q, dict) or not str(q.get("question", "")).strip():
            raise ValueError(f"question {i} is missing a non-empty 'question' field")
        choices = q.get("choices") or []
        if not isinstance(choices, list):
            raise ValueError(f"question {i}: 'choices' must be a list")
        pts = q.get("points")
        items.append({
            "question": str(q["question"]).strip(),
            "choices": [str(c).strip() for c in choices if str(c).strip()],
            "answer": str(q.get("answer", "")).strip(),
            "solution": str(q.get("solution", "")).strip(),
            "points": pts if isinstance(pts, (int, float)) else 1,
        })
    title = ""
    if isinstance(data, dict):
        title = str(data.get("title", "")).strip()[:120]
    return (title or fallback_title), items


def extract_pdf_text(blob):
    """Pull the embedded text layer out of a PDF (no OCR).

    Needs the optional 'pypdf' package (same ad-hoc dep as the scrapers).
    Scanned PDFs have no text layer — raise with a clear hint instead of
    silently producing garbage.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("PDF support needs pypdf — run: pip install pypdf")
    try:
        reader = PdfReader(io.BytesIO(blob))
    except Exception as e:
        raise ValueError(f"could not read PDF: {e}")
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    if not text.strip():
        raise ValueError("this PDF has no text layer (it looks scanned) — "
                         "upload a text-based PDF or a .txt/.md file instead")
    return text


def extract_docx_text(blob):
    """Extract text from a .docx (Office Open XML) using only the stdlib.

    Reads word/document.xml and rebuilds one line per paragraph. Embedded
    images are IGNORED — scans inside docx get a clear error instead of
    being sent to any AI/OCR service (this pipeline never uses tokens).
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
        xml = zf.read("word/document.xml")
    except zipfile.BadZipFile:
        raise ValueError("could not read .docx — is it a real Word document?")
    except KeyError:
        raise ValueError("this .docx has no word/document.xml — unsupported file")
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise ValueError(f"could not parse the .docx content: {e}")
    lines = []
    for p in root.iter(W + "p"):
        lines.append("".join(t.text or "" for t in p.iter(W + "t")))
    text = "\n".join(lines)
    if not text.strip():
        raise ValueError("no text found in this .docx (it looks like scanned images) — "
                         "type the questions as .txt/.md instead; uploads are never sent to an AI")
    return text


def extract_image_text(blob, ext):
    """OCR an image with the Tesseract CLI (no tokens, no extra Python deps).

    Math OCR is rough — fractions/exponents often come out mangled — so the
    result still goes through the normal text parser and may need cleanup.
    """
    if not shutil.which("tesseract"):
        raise ValueError("image OCR needs the Tesseract CLI — install it, e.g.: brew install tesseract")
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
        f.write(blob)
        tmp = f.name
    try:
        proc = subprocess.run(["tesseract", tmp, "stdout", "--psm", "6"],
                              capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise ValueError("OCR timed out")
    finally:
        os.unlink(tmp)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise ValueError("OCR found no text in this image")
    return proc.stdout.decode("utf-8", "replace")


def generate_worksheet(filename, blob, owner):
    ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
    if ext not in WS_EXTS:
        raise ValueError(f"file type .{ext or '?'} not supported — use "
                         f"{', '.join('.' + e for e in WS_EXTS)}")
    limit = WS_TEXT_MAX_BYTES if ext in WS_TEXT_EXTS else WS_MAX_BYTES
    if len(blob) > limit:
        raise ValueError(f"file too large (max {limit // (1024 * 1024)} MB)")
    if ext in WS_TEXT_EXTS:
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("file must be UTF-8 text")
    elif ext == "pdf":
        text = extract_pdf_text(blob)
    elif ext == "docx":
        text = extract_docx_text(blob)
    else:
        text = extract_image_text(blob, ext)
    fallback = re.sub(r"\.([a-z0-9]+)$", "", filename, flags=re.I).replace("_", " ").strip()[:120] or "Worksheet"
    if ext == "json":
        title, items = parse_worksheet_json(text, fallback)
    else:
        title, items = parse_worksheet_text(text, fallback)
    ws = {
        "id": secrets.token_hex(8),
        "title": title,
        "owner": owner,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "questions": [dict(n=i, **it) for i, it in enumerate(items, 1)],
        "total_points": sum(it["points"] for it in items),
    }
    WORKSHEETS_DIR.mkdir(exist_ok=True)
    (WORKSHEETS_DIR / f"{ws['id']}.json").write_text(
        json.dumps(ws, ensure_ascii=False, indent=1), encoding="utf-8")
    return ws


# ---------- SHSID papers (crawled LinkedClassroom files, see scraper/shsid_crawler.py) ----------
SHSID_FILE_EXTS = ("pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "zip",
                   "png", "jpg", "jpeg", "txt", "md", "tex")


def _shsid_index():
    """Enriched raw/shsid/index.json: per downloaded file add size and ext.
    Missing index (crawler never ran) is not an error — the UI shows a hint."""
    f = SHSID_DIR / "index.json"
    if not f.exists():
        return {"courses": []}
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {"courses": []}
    for course in doc.get("courses", []):
        for sec in course.get("sections", []):
            for act in sec.get("activities", []):
                files = []
                for rel in act.get("downloaded", []):
                    p = SHSID_DIR.parent.parent / rel  # rel is raw/shsid/...
                    if not p.exists():
                        continue
                    ext = p.suffix.lstrip(".").lower()
                    if ext not in SHSID_FILE_EXTS:
                        continue
                    files.append({"path": rel, "name": p.name, "ext": ext,
                                  "size": p.stat().st_size})
                act["files"] = files
    return doc


def _shsid_file_path(rel):
    """Resolve a raw/shsid/... path with traversal guard; None when invalid."""
    if not rel.startswith("raw/shsid/"):
        return None
    p = (ROOT / rel).resolve()
    try:
        p.relative_to(SHSID_DIR.resolve())
    except ValueError:
        return None
    return p if p.is_file() else None


def _pk_game_path(gid):
    return PK_DIR / f"{gid}.json"


def _read_pk(gid):
    f = _pk_game_path(gid)
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_pk(game):
    PK_DIR.mkdir(exist_ok=True)
    with _store_lock:
        _pk_game_path(game["id"]).write_text(json.dumps(game, ensure_ascii=False), encoding="utf-8")


def _pk_result_for(user, test_id):
    for r in reversed(read_results(user)):
        if r.get("test_id") == test_id:
            return r
    return None


def pk_game_view(game, user):
    """Game dict from `user`'s perspective, with live scores."""
    other = game["opponent"] if user == game["challenger"] else game["challenger"]
    view = {
        "id": game["id"], "opponent": other, "me": user,
        "role": "challenger" if user == game["challenger"] else "opponent",
        "slug": game["slug"], "difficulty": game["difficulty"],
        "status": game["status"], "created_at": game.get("created_at"),
        "test_id": game.get("test_id"),
    }
    mine = theirs = None
    if game.get("test_id"):
        mine = _pk_result_for(user, game["test_id"])
        theirs = _pk_result_for(other, game["test_id"])
    view["my"] = _pk_score_view(mine)
    view["their"] = _pk_score_view(theirs)
    if game["status"] == "active":
        if mine and theirs:
            view["status"] = "done"
        elif mine or theirs:
            view["status"] = "submitted"  # one side finished
    if view["status"] in ("done",):
        ms, ts = view["my"], view["their"]
        if ms["done"] and ts["done"]:
            mp = ms["score"] / ms["total"] if ms["total"] else 0
            tp = ts["score"] / ts["total"] if ts["total"] else 0
            view["winner"] = "me" if mp > tp else ("them" if tp > mp else "draw")
        else:
            view["winner"] = "me" if ms["done"] else "them"
    return view


def _pk_score_view(rec):
    if not rec:
        return {"done": False, "score": None, "total": rec and rec.get("total"), "answered": 0}
    return {"done": True, "score": rec.get("score"), "total": rec.get("total"),
            "answered": rec.get("answered", 0)}


def _pk_maybe_expire(game):
    """Lazily expire pending games older than the invite TTL. Returns game."""
    if game.get("status") != "pending":
        return game
    try:
        created = time.mktime(time.strptime(game.get("created_at", ""), "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return game
    if time.time() - created > PK_INVITE_TTL_S:
        game["status"] = "expired"
        _write_pk(game)
    return game


def _pk_user_in(game, user):
    if game.get("mode") == "race":
        return user in game.get("players", [])
    return user in (game.get("challenger"), game.get("opponent"))


def _pk_pending_for(game, user):
    """True if `user` still needs to respond to this pending game."""
    if game.get("mode") == "race":
        return (user in game.get("players", []) and user != game.get("host")
                and user not in game.get("accepted", []))
    return game.get("opponent") == user


def pk_race_view(game, user):
    """Race game view with live standings (score desc, then duration asc)."""
    view = {"id": game["id"], "mode": "race", "host": game["host"], "me": user,
            "is_host": user == game["host"],
            "slug": game["slug"], "difficulty": game["difficulty"],
            "status": game["status"], "created_at": game.get("created_at"),
            "test_id": game.get("test_id"),
            "players": game.get("players", []), "accepted": game.get("accepted", []),
            "invited": [p for p in game.get("players", []) if p not in game.get("accepted", [])]}
    standings = []
    for p in game.get("accepted", []):
        rec = _pk_result_for(p, game["test_id"]) if game.get("test_id") else None
        standings.append({"user": p, "done": bool(rec),
                          "score": rec and rec.get("score"), "total": rec and rec.get("total"),
                          "duration_s": rec and rec.get("duration_s"),
                          "answered": (rec and rec.get("answered", 0)) or 0})
    standings.sort(key=lambda s: (not s["done"], -(s["score"] or 0), s["duration_s"] or 9e9))
    view["standings"] = standings
    if view["status"] == "active" and standings and all(s["done"] for s in standings):
        view["status"] = "done"
    view["winner"] = standings[0]["user"] if (view["status"] == "done" and standings and standings[0]["done"]) else None
    return view


def build_pk_test(game):
    """Generate the shared PK test and drop it into both players' test dirs.

    Difficulty = position window (same ratios as the UI difficulty labels):
    easy r<=0.4, medium r<=0.75, hard beyond. Returns True on success.
    """
    slug = game["slug"]
    if slug not in COMP_META:
        return False
    name, n_q, tlim, category, rounds, family = COMP_META[slug]
    if rounds:  # round-based competitions not supported in PK for now
        return False
    lo, hi = PK_LEVELS.get(game["difficulty"], PK_LEVELS["medium"])
    by_pos = {}
    for v in load_bank(slug):
        by_pos.setdefault(v["position"], []).append(v)
    positions = [p for p in range(1, n_q + 1) if lo < p / n_q <= hi]
    if not positions or any(p not in by_pos for p in positions):
        return False
    questions = []
    total_points = 0
    for i, pos in enumerate(positions, 1):
        v = random.choice(by_pos[pos])
        pts = v.get("points") or points_for(slug, None, pos)
        total_points += pts
        questions.append({
            "n": i, "source": v["source"], "question": v["question"],
            "choices": v.get("choices"), "answer": v["answer"], "solution": v.get("solution"),
            "type": v.get("type", "integer_answer" if slug == "aime" else "multiple_choice"),
            "points": pts,
        })
    level_name = game["difficulty"].capitalize()
    test_id = f"pk_{game['id']}"
    is_race = game.get("mode") == "race"
    if is_race:
        recipients = list(game.get("accepted", []))
    else:
        recipients = [game["challenger"], game["opponent"]]
    for username in recipients:
        if is_race:
            title = f"🏁 Race — {name} · {level_name}"
            instr = (f"{len(questions)} questions · PK race with {len(recipients)} players. "
                     f"Difficulty: {level_name}.")
        else:
            other = game["opponent"] if username == game["challenger"] else game["challenger"]
            title = f"⚔️ PK vs {other} — {name} · {level_name}"
            instr = f"{len(questions)} questions · PK battle vs {other}. Difficulty: {level_name}."
        test = {
            "id": test_id,
            "competition": f"PK — {name}",
            "category": category,
            "title": title,
            "instructions": instr,
            "time_limit_min": max(5, round(tlim * len(questions) / n_q)),
            "total_points": total_points,
            "questions": questions,
        }
        tdir = _tests_dir(username)
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / f"{test_id}.json").write_text(json.dumps(test, ensure_ascii=False), encoding="utf-8")
    game["test_id"] = test_id
    game["status"] = "active"
    game["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return True


def _read_friends():
    return _load_json(FRIENDS_FILE, {})


def _write_friends(d):
    _save_json(FRIENDS_FILE, d)


def _friend_entry(d, user):
    return d.setdefault(user, {"friends": [], "incoming": [], "outgoing": []})


def read_messages(a, b, since=0, limit=200):
    """Messages exchanged between users a and b, ts > since, last `limit`."""
    if not MESSAGES_FILE.exists():
        return []
    out = []
    with _store_lock:
        for line in MESSAGES_FILE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                m = json.loads(line)
            except Exception:
                continue
            pair = {m.get("frm"), m.get("to")}
            if pair == {a, b} and m.get("ts", 0) > since:
                out.append(m)
    return out[-limit:]


def append_message(frm, to, text):
    m = {"ts": time.time(), "frm": frm, "to": to, "text": text}
    with _store_lock:
        with MESSAGES_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    return m


def user_paths(username):
    """Per-user storage directories."""
    base = USERS_DIR / username
    return base / "tests", base / "results.jsonl"


def round_allows_proofs(variants):
    """Allow proof problems in a round only when they are a tiny minority.

    Rule: include proofs if the round has at most 2 proof questions and at
    least 10 non-proof questions (i.e. '1-2 proof questions and tens of others').
    """
    n_total = len(variants)
    n_proof = sum(1 for v in variants if v.get("type") == "proof")
    return n_proof <= 2 and n_total - n_proof >= 10


def is_eligible(v, allow_proof=False):
    """A variant may be used only if it has a solution.

    Proof problems are excluded unless the round explicitly allows them.
    """
    if not v.get("solution"):
        return False
    if v.get("type") == "proof" and not allow_proof:
        return False
    return True


def points_for(slug, round_name, position):
    """Return the point value for a question in its actual contest format."""
    # Round-specific overrides
    if slug == "mathcounts":
        return 2 if round_name == "Target" else 1
    if round_name:
        # Most subject/team rounds award 1 point per problem.
        return 1
    pts = DEFAULT_POINTS.get(slug)
    if pts is not None:
        return pts
    # Special per-position rules for competitions not in DEFAULT_POINTS
    if slug == "mathkangaroo":
        # Approximation for the 10-question bank: 1-3 -> 3 pts, 4-7 -> 4 pts, 8-10 -> 5 pts
        return 3 if position <= 3 else 4 if position <= 7 else 5
    if slug == "ukmt":
        # SMC-style scoring: first 15 questions 4 pts, last 10 questions 5 pts
        return 4 if position <= 15 else 5
    return 1


def _tests_dir(user=None):
    if not user:
        return TESTS
    udir, _ = user_paths(user)
    udir.mkdir(parents=True, exist_ok=True)
    return udir


def _results_file(user=None):
    if not user:
        return RESULTS
    _, rfile = user_paths(user)
    rfile.parent.mkdir(parents=True, exist_ok=True)
    return rfile


def _practice_file(user):
    base = ROOT / "users" / user
    base.mkdir(parents=True, exist_ok=True)
    return base / "practice.json"


def _clean_details(details):
    """Sanitize the per-question result detail array: [{n, given, ok}]."""
    if not isinstance(details, list):
        return []
    out = []
    for d in details[:200]:
        if not isinstance(d, dict):
            continue
        try:
            out.append({
                "n": int(d.get("n")),
                "given": str(d.get("given", ""))[:100],
                "ok": bool(d.get("ok")),
            })
        except (TypeError, ValueError):
            continue
    return out


def _classification_file(test_id):
    """Per-test question classification, written by teachers (kp/diff/note per question n)."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(test_id))[:80]
    return TESTS / f"{safe}.cls.json"


def _load_classification(test_id):
    try:
        return json.loads(_classification_file(test_id).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _clean_classification(items):
    """Sanitize {n: {kp, diff, note}} from the teacher editor."""
    out = {}
    if not isinstance(items, dict):
        return out
    for k, v in items.items():
        if not isinstance(v, dict):
            continue
        try:
            n = int(k)
        except (TypeError, ValueError):
            continue
        entry = {}
        kp = str(v.get("kp", "")).strip()[:80]
        note = str(v.get("note", "")).strip()[:300]
        if kp:
            entry["kp"] = kp
        if note:
            entry["note"] = note
        try:
            diff = int(v.get("diff"))
            if 1 <= diff <= 5:
                entry["diff"] = diff
        except (TypeError, ValueError):
            pass
        out[str(n)] = entry
    return out


def list_tests(user=None):
    out = []
    tests_dir = _tests_dir(user)
    for f in sorted(tests_dir.glob("*.json")):
        if f.name.endswith(".meta.json"):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if str(d.get("id", "")).startswith("pk_"):
                continue  # PK battles live in the PK tab, not My Tests
            out.append({
                "id": d["id"], "title": d["title"], "competition": d["competition"],
                "n_questions": len(d["questions"]), "time_limit_min": d.get("time_limit_min"),
            })
        except Exception:
            continue
    return out


def used_sources(user=None):
    """Sources already consumed by previously generated tests (no-overlap rule)."""
    used = set()
    tests_dir = _tests_dir(user)
    for f in tests_dir.glob("*_rand_*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            for q in d.get("questions", []):
                if q.get("source"):
                    used.add(q["source"])
        except Exception:
            continue
    return used


def round_of(slug, source):
    pat = ROUND_PATTERNS.get(slug)
    if not pat:
        return None
    m = re.search(pat, source or "")
    if not m:
        return None
    r = m.group(1)
    return {"Nt": "Number Theory", "Combo": "Combinatorics"}.get(r, r)


def wrap_variant(v):
    """Normalise bare LaTeX in a variant's texts so KaTeX renders them."""
    for k in ("question", "solution", "explanation"):
        if isinstance(v.get(k), str):
            v[k] = wrap_bare_math(v[k])
    ch = v.get("choices")
    if isinstance(ch, list):
        v["choices"] = [wrap_bare_math(c) if isinstance(c, str) else c for c in ch]
    elif isinstance(ch, dict):
        v["choices"] = {k: wrap_bare_math(c) if isinstance(c, str) else c
                        for k, c in ch.items()}
    return v


_bank_cache = {}  # (slug, version) -> wrapped, eligible variants (banks are static at runtime)


_taxonomy_cache = {}


def load_taxonomy(tax_id=None):
    """Flatten taxonomy/<id>.json into the small label map the UI needs.

    Nodes are nested (domain -> topic -> tag); the client wants a flat
    {id: {en, zh, level}} map so it can label a question without walking.
    """
    tax_id = tax_id or DEFAULT_TAXONOMY
    if tax_id in _taxonomy_cache:
        return _taxonomy_cache[tax_id]
    path = TAXONOMY_DIR / f"{tax_id}.json"
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    nodes = {}

    def walk(items, depth):
        for item in items or []:
            node_id = item.get("id")
            if not node_id:
                continue
            label = item.get("label") or {}
            nodes[node_id] = {
                "en": label.get("en") or node_id,
                "zh": label.get("zh") or label.get("en") or node_id,
                "level": depth,
            }
            walk(item.get("children"), depth + 1)

    walk(doc.get("roots"), 1)
    out = {
        "id": doc.get("id", tax_id),
        "version": doc.get("version"),
        "name": doc.get("name"),
        "levels": doc.get("levels"),
        "nodes": nodes,
    }
    _taxonomy_cache[tax_id] = out
    return out


def bank_files(slug, version=1):
    """Files backing one bank version; empty when that version is not installed.

    Version 1 is the classic layout (bank/<slug>_<set>.json). Version 2 is the
    figure-carrying import (bank/v2/<slug>.json, see scripts/import_papers.py).
    """
    if version == 2:
        f = BANK_V2 / f"{slug}.json"
        return [f] if f.exists() else []
    return [f for f in sorted(BANK.glob(f"{slug}_*.json")) if not f.name.endswith(".v1.json")]


def load_bank(slug, round_name=None, version=1):
    """All eligible variants for a slug (optionally restricted to a round).

    Excludes variants without a solution. Proof problems are excluded unless
    that round has only a tiny minority of proofs (<=2) plus many other questions.
    Results are cached: latex wrapping every variant on every request is far
    too slow (list_banks hits this for all competitions at once).
    """
    key = (slug, version)
    if key not in _bank_cache:
        out = []
        for f in bank_files(slug, version):
            # bank/*.v1.json are the same problems migrated to paper-format v1.0
            # (see scripts/migrate_banks.py). They are parallel copies, not extra
            # banks: loading both would duplicate every variant.
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                variants = d.get("variants", [])
                # Proof eligibility is per-round, not per-file: a bank file can mix
                # answer-key rounds (proofs excluded) with proof-based rounds (Power).
                groups = {}
                for v in variants:
                    groups.setdefault(round_of(slug, v.get("source", "")), []).append(v)
                for vs in groups.values():
                    allow_proof = round_allows_proofs(vs)
                    out.extend(wrap_variant(v) for v in vs if is_eligible(v, allow_proof=allow_proof))
            except Exception:
                continue
        _bank_cache[key] = out
    variants = _bank_cache[key]
    if round_name:
        variants = [v for v in variants if round_of(slug, v.get("source")) == round_name]
    return variants


def _with_versions(card, v2_variants):
    """Attach figure-bank availability to a generator card."""
    card["versions"] = [1, 2] if v2_variants else [1]
    card["v2_variants"] = len(v2_variants)
    card["v2_figures"] = sum(1 for v in v2_variants if v.get("figure"))
    return card


def list_banks(user=None):
    """Generator cards: one per competition (or per round for round-based ones).

    Only counts eligible variants (with solution; proofs allowed only when that
    round has just a few proofs and many other questions).
    """
    used = used_sources(user)
    out = []
    for slug, meta in COMP_META.items():
        name, n_q, tlim, category, rounds, family = meta
        v2_all = load_bank(slug, version=2)
        if rounds:
            for rname, (rn_q, rn_tlim) in rounds.items():
                rv = load_bank(slug, round_name=rname)
                if not rv:
                    continue
                v2_rv = [v for v in v2_all if round_of(slug, v.get("source")) == rname]
                pos_src = {}
                for v in rv:
                    pos_src.setdefault(v["position"], set()).add(v.get("source"))
                ready = len(pos_src) >= rn_q
                min_unused = min((len(s - used) for s in pos_src.values()), default=0)
                out.append(_with_versions({
                    "slug": slug, "round": rname, "name": f"{name} — {rname}",
                    "category": category, "family": family, "n_questions": rn_q, "time_limit_min": rn_tlim,
                    "ready": ready, "total_variants": len(rv),
                    "positions_covered": len(pos_src), "tests_remaining": min_unused,
                    "real": slug.startswith("bpho"),
                }, v2_rv))
        else:
            rv = load_bank(slug)
            pos_src = {}
            for v in rv:
                pos_src.setdefault(v["position"], set()).add(v.get("source"))
            ready = len(pos_src) >= n_q
            counts = [len(s) for p, s in pos_src.items() if p <= n_q]
            min_src = min(counts, default=0)
            counts_unused = [len(s - used) for p, s in pos_src.items() if p <= n_q]
            out.append(_with_versions({
                "slug": slug, "round": None, "name": name, "category": category, "family": family,
                "n_questions": n_q, "time_limit_min": tlim, "ready": ready,
                "total_variants": len(rv), "positions_covered": len(pos_src),
                "tests_remaining": min(counts_unused, default=0), "tests_total": min_src,
                "real": slug.startswith("bpho"),
            }, v2_all))
    # Only expose competitions/rounds that can actually be generated right now.
    return [b for b in out if b["ready"]]


# --------------------------------------------------------------- question bank browser
#
# The generator only ever looks at *eligible* variants (see load_bank), but the
# bank browser is an exploration tool: it must show every question on disk,
# including the ones a test would skip (no solution, proofs, unclassified).

_qindex_cache = {"stamp": None, "rows": []}


def _slug_of(stem):
    """Competition slug for a bank file stem (longest COMP_META key that prefixes it)."""
    best = None
    for key in COMP_META:
        if stem == key or stem.startswith(key + "_"):
            if best is None or len(key) > len(best):
                best = key
    return best or stem.rsplit("_", 1)[0]


def _comp_label(slug):
    meta = COMP_META.get(slug)
    return meta[0] if meta else slug


def _bank_index_files():
    """(slug, version, path) for every bank file on disk: classic + figure bank."""
    files = []
    for f in sorted(BANK.glob("*.json")):
        if f.name.endswith(".v1.json"):
            continue  # parallel copies of the same problems (see load_bank)
        files.append((_slug_of(f.stem), 1, f))
    for f in sorted(BANK_V2.glob("*.json")):
        files.append((_slug_of(f.stem), 2, f))
    return files


def _choices_list(raw):
    """Bank v1 stores choices as a list, bank v2 as an {A: text} object."""
    if isinstance(raw, dict):
        return [f"{k}. {v}" for k, v in raw.items()]
    if isinstance(raw, list):
        return [c if isinstance(c, str) else json.dumps(c) for c in raw]
    return []


def _figure_url(figure):
    """Bank-relative figure path -> the /figures/... URL the browser can fetch."""
    if not isinstance(figure, dict):
        return figure or None
    out = dict(figure)
    src = out.get("src")
    if isinstance(src, str) and src and not src.startswith("/"):
        out["src"] = "/" + src.lstrip("./")
    return out


def build_qindex():
    """Flat index of every question in every bank file, cached until files change."""
    files = _bank_index_files()
    stamp = tuple()
    try:
        stamp = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for _, _, p in files)
    except OSError:
        stamp = None  # a file vanished mid-scan; rebuild next time
    if stamp is not None and _qindex_cache["stamp"] == stamp:
        return _qindex_cache["rows"]
    rows = []
    for slug, version, path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        comp = _comp_label(slug) or doc.get("competition") or slug
        set_name = doc.get("set") or ""
        for v in doc.get("variants") or []:
            text = v.get("question") or ""
            cls = v.get("classification") or {}
            diff = v.get("difficulty") or {}
            primary = cls.get("primary")
            primary = primary if isinstance(primary, str) else None
            level = diff.get("level")
            level = level if isinstance(level, int) else None
            tags = [t.get("id") for t in (cls.get("tags") or [])
                    if isinstance(t, dict) and isinstance(t.get("id"), str)]
            qid = v.get("qid") or "q" + hashlib.sha1(
                f"{v.get('source', '')}\0{text}".encode("utf-8")).hexdigest()[:12]
            rows.append({
                "id": f"{slug}:{version}:{qid}",
                "qid": qid,
                "bank": path.stem,
                "slug": slug,
                "version": version,
                "competition": comp,
                "set": set_name,
                "position": v.get("position"),
                "source": v.get("source") or "",
                "type": v.get("type") or "",
                "points": v.get("points"),
                "question": text,
                "question_zh": v.get("question_zh") or "",
                "choices": _choices_list(v.get("choices")),
                "answer": v.get("answer") if isinstance(v.get("answer"), str) else "",
                "solution": v.get("solution") or "",
                "solution_zh": v.get("solution_zh") or "",
                "primary": primary,
                "domain": primary.split(".")[0] if primary else None,
                "tags": tags,
                "level": level,
                "band": diff.get("band") if isinstance(diff.get("band"), str) else None,
                "has_figure": bool(v.get("figure")),
                "figure": _figure_url(v.get("figure")),
                "has_solution": bool(v.get("solution")),
            })
    _qindex_cache["stamp"] = stamp
    _qindex_cache["rows"] = rows
    return rows


def _as_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


_hay_cache = {}


def _qindex_haystack(r):
    """Lowercased text blob for one row (cached: searching 12k questions repeatedly)."""
    hay = _hay_cache.get(r["id"])
    if hay is None:
        hay = " ".join((
            r["question"], r["question_zh"], r["source"],
            " ".join(r["choices"]), r["answer"], r["solution"],
        )).lower()
        _hay_cache[r["id"]] = hay
    return hay


def search_questions(query=None, comps=None, version=None, domain=None, topic=None,
                     level_min=None, level_max=None, qtype=None, figure=None,
                     classified=None, sort="default", limit=30, offset=0):
    """Filter the whole bank. Returns a page plus facet counts for the UI."""
    rows = build_qindex()
    needle = (query or "").strip().lower()

    def matches(r):
        if needle and needle not in _qindex_haystack(r):
            return False
        if comps and r["slug"] not in comps:
            return False
        if version and r["version"] != version:
            return False
        if domain and r["domain"] != domain:
            return False
        if topic:
            ids = [r["primary"]] + r["tags"] if r["primary"] else r["tags"]
            if not any(i and (i == topic or i.startswith(topic + ".")) for i in ids):
                return False
        if level_min is not None and (r["level"] is None or r["level"] < level_min):
            return False
        if level_max is not None and (r["level"] is None or r["level"] > level_max):
            return False
        if qtype and r["type"] != qtype:
            return False
        if figure is not None and r["has_figure"] != figure:
            return False
        if classified is not None and bool(r["primary"]) != classified:
            return False
        return True

    hits = [r for r in rows if matches(r)]
    if sort == "level_asc":
        hits.sort(key=lambda r: (r["level"] is None, r["level"] or 0, r["slug"], r["position"] or 0))
    elif sort == "level_desc":
        hits.sort(key=lambda r: (r["level"] is None, -(r["level"] or 0), r["slug"], r["position"] or 0))
    elif sort == "position":
        hits.sort(key=lambda r: (r["slug"], r["position"] or 0, r["source"]))
    else:  # default: grouped by competition, then original paper order
        hits.sort(key=lambda r: (r["slug"], r["version"], r["position"] or 0, r["source"]))

    limit = max(1, min(200, limit or 30))
    offset = max(0, offset or 0)
    page = hits[offset:offset + limit]

    comp_facet, domain_facet, level_facet, type_facet = {}, {}, {}, {}
    for r in rows:
        if needle and needle not in _qindex_haystack(r):
            continue
        comp_facet[r["slug"]] = comp_facet.get(r["slug"], 0) + 1
        type_facet[r["type"] or "unknown"] = type_facet.get(r["type"] or "unknown", 0) + 1
        if r["domain"]:
            domain_facet[r["domain"]] = domain_facet.get(r["domain"], 0) + 1
        if r["level"] is not None:
            level_facet[str(r["level"])] = level_facet.get(str(r["level"]), 0) + 1
    return {
        "total": len(hits),
        "limit": limit,
        "offset": offset,
        "counts": {
            "all": len(rows),
            "competition": dict(sorted(comp_facet.items(), key=lambda kv: -kv[1])),
            "competition_labels": {k: _comp_label(k) for k in comp_facet},
            "domain": dict(sorted(domain_facet.items(), key=lambda kv: -kv[1])),
            "level": dict(sorted(level_facet.items(), key=lambda kv: int(kv[0]))),
            "type": dict(sorted(type_facet.items(), key=lambda kv: -kv[1])),
        },
        "items": page,
    }


def generate_test(slug, round_name=None, user=None, version=1):
    """Assemble a new mock: one eligible variant per position, never reusing a source
    that appeared in any previously generated test.

    ``version`` picks the bank: 1 = classic, 2 = figure bank (bank/v2/<slug>.json).
    Returns None if any required position has no eligible variant (proof problems
    and problems without a solution are excluded), which is what lets the HTTP
    layer fall back from version 2 to version 1.
    """
    name, n_q, tlim, category, rounds, family = COMP_META[slug]
    if rounds:
        if not round_name or round_name not in rounds:
            return None
        n_q, tlim = rounds[round_name]
        display = f"{name} — {round_name}"
    else:
        display = name
    used = used_sources(user)
    by_pos, by_pos_unused = {}, {}
    for v in load_bank(slug, version=version):
        if rounds and round_of(slug, v.get("source")) != round_name:
            continue
        by_pos.setdefault(v["position"], {})[v["source"]] = v
        if v["source"] not in used:
            by_pos_unused.setdefault(v["position"], {})[v["source"]] = v
    # All positions 1..n_q must have at least one eligible variant.
    if set(range(1, n_q + 1)) - set(by_pos.keys()):
        return None
    # A test drawn from the figure bank must show at least one figure, otherwise
    # the "with figures" choice looks broken for that draw.
    forced_pos = None
    if version == 2:
        fig_positions = [
            pos for pos in range(1, n_q + 1)
            if any(v.get("figure") for v in by_pos.get(pos, {}).values())
        ]
        if fig_positions:
            forced_pos = random.choice(fig_positions)
    questions = []
    reused = 0
    total_points = 0
    for pos in range(1, n_q + 1):
        # Prefer unused sources; do not fall back to already-used sources.
        pool = by_pos_unused.get(pos)
        if not pool:
            reused += 1
            pool = by_pos[pos]
        v = None
        if pos == forced_pos:
            fig_pool = {s: x for s, x in pool.items() if x.get("figure")}
            if not fig_pool:
                fig_pool = {s: x for s, x in by_pos[pos].items() if x.get("figure")}
            if fig_pool:
                v = random.choice(list(fig_pool.values()))
        if v is None:
            v = random.choice(list(pool.values()))
        pts = v.get("points") or points_for(slug, round_name, pos)
        total_points += pts
        figure = v.get("figure")
        if figure:
            # Stored tests must be self-contained: turn the bank-relative path into
            # a URL the browser can fetch from /figures/...
            figure = dict(figure)
            src = figure.get("src")
            if src and not src.startswith("/"):
                figure["src"] = "/" + src
        q = {
            "n": pos, "source": v["source"], "question": v["question"],
            "choices": v.get("choices"), "answer": v["answer"], "solution": v.get("solution"),
            "type": v.get("type", "integer_answer" if slug == "aime" else "multiple_choice"),
            "points": pts,
            "figure": figure,
        }
        # Topic classification and difficulty travel with the question: they are
        # annotations on the bank (see scripts/apply_classification.py), so a
        # generated paper stays filterable/analysable without re-guessing.
        for key in ("classification", "difficulty"):
            if v.get(key):
                q[key] = v[key]
        questions.append(q)
    integer = slug in ("aime", "mathcounts")
    calc = " · Calculator allowed" if slug.startswith("bpho") else " · No calculator"
    tests_dir = _tests_dir(user)
    n_existing = len(list(tests_dir.glob(f"{slug}_rand_*.json")))
    point_line = f"{total_points} points total."
    instr_extra = ("Answers are integers from 000 to 999. " + point_line if integer
                   else point_line)
    gen_time = time.strftime("%Y-%m-%d %H:%M")
    test = {
        "id": f"{slug}_rand_{n_existing + 1:02d}",
        "competition": display,
        "category": category,
        "bank_version": version,
        "title": f"{display} — Random Mock #{n_existing + 1} · {gen_time}",
        "instructions": f"{n_q} questions · {tlim} minutes{calc}. " + instr_extra,
        "time_limit_min": tlim,
        "total_points": total_points,
        "questions": questions,
    }
    (tests_dir / f"{test['id']}.json").write_text(
        json.dumps(test, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    test["reused_positions"] = reused
    return test


def _diff_level(q):
    """Extract the numeric difficulty level (partner's amc20 1-20 scale) from a question/variant."""
    d = (q or {}).get("difficulty") or {}
    try:
        return float(d.get("level"))
    except (TypeError, ValueError):
        return None


def build_similar_test(user, items):
    """Build a practice test from the same banks, at the positions the student got wrong.

    Each item is {test_id, n}. The original test is looked up (user dir then global),
    the bank slug is recovered from the test id (`<slug>_rand_...`), and for every
    requested position one sibling variant (same position, different source) is drawn.
    Falls back to the original question itself when the bank has no sibling.
    """
    questions = []
    total_points = 0
    sources = set()
    for item in items:
        tid = re.sub(r"[^A-Za-z0-9_-]", "", str(item.get("test_id", "")))[:80]
        n = int(item.get("n"))
        f = None
        tdir = _tests_dir(user)
        if (tdir / f"{tid}.json").exists():
            f = tdir / f"{tid}.json"
        elif (TESTS / f"{tid}.json").exists():
            f = TESTS / f"{tid}.json"
        if not f:
            continue
        try:
            tdata = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        orig = next((q for q in tdata.get("questions", []) if q.get("n") == n), None)
        if not orig:
            continue
        slug = tid.split("_rand_")[0]
        if slug not in COMP_META:
            continue
        q = dict(orig)
        version = tdata.get("bank_version", 1)
        try:
            bank = load_bank(slug, version=version)
            siblings = [v for v in bank if v.get("source") != orig.get("source")]
            pick = None
            # 1) same topic (classifier tag) AND closest difficulty level — the
            #    partner's amc20 scale makes 'similar' precise, not just 'same chapter'
            orig_tag = (orig.get("classification") or {}).get("primary")
            orig_level = _diff_level(orig)
            if orig_level is None:
                # older tests lack embedded fields — recover from the bank by source
                orig_v = next((v for v in bank if v.get("source") == orig.get("source")), None)
                orig_tag = orig_tag or ((orig_v or {}).get("classification") or {}).get("primary")
                orig_level = _diff_level(orig_v)
            if orig_tag:
                same_topic = [v for v in siblings
                              if (v.get("classification") or {}).get("primary") == orig_tag]
                if same_topic:
                    def _key(v):
                        lv = _diff_level(v)
                        dl = abs(lv - orig_level) if (lv is not None and orig_level is not None) else 999
                        return (dl, abs(int(v.get("position", n)) - n))
                    same_topic.sort(key=_key)
                    pick = random.choice(same_topic[:3])
            # 2) fallback: same position, different source (classic difficulty-ramp match)
            if pick is None:
                same_pos = [v for v in siblings if v.get("position") == n]
                if same_pos:
                    pick = random.choice(same_pos)
            if pick is None and siblings:
                pick = random.choice(siblings)
            if pick:
                figure = pick.get("figure")
                if figure:
                    figure = dict(figure)
                    src = figure.get("src")
                    if src and not src.startswith("/"):
                        figure["src"] = "/" + src
                q = {
                    "n": n, "source": pick["source"], "question": pick["question"],
                    "choices": pick.get("choices"), "answer": pick["answer"],
                    "solution": pick.get("solution"),
                    "type": pick.get("type", orig.get("type", "multiple_choice")),
                    "points": orig.get("points", 1),
                    "figure": figure,
                }
                for key in ("classification", "difficulty"):
                    if pick.get(key):
                        q[key] = pick[key]
        except Exception:
            pass  # keep the original question if the bank can't be read
        if q["source"] in sources:
            continue
        sources.add(q["source"])
        total_points += q.get("points", 1)
        questions.append(q)
    if not questions:
        raise ValueError("no questions could be matched to a bank — similar practice unavailable")
    questions.sort(key=lambda q: q["n"])
    n_q = len(questions)
    tlim = max(5, min(75, 3 * n_q))
    gen_time = time.strftime("%Y-%m-%d %H:%M")
    test = {
        "id": f"similar_{secrets.token_hex(4)}",
        "competition": "Similar Practice",
        "category": "Math",
        "title": f"Similar Practice — {n_q} questions · {gen_time}",
        "instructions": f"{n_q} questions · {tlim} minutes. Same positions as your missed questions, fresh variants.",
        "time_limit_min": tlim,
        "total_points": total_points,
        "questions": questions,
    }
    (_tests_dir(user) / f"{test['id']}.json").write_text(
        json.dumps(test, ensure_ascii=False, indent=1), encoding="utf-8")
    return test


def read_results(user=None):
    rfile = _results_file(user)
    if not rfile.exists():
        return []
    out = []
    for line in rfile.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def compute_stats(user=None):
    results = [r for r in read_results(user)
               if not str(r.get("test_id", "")).startswith("pk_")]
    per_comp = {}
    for r in results:
        c = per_comp.setdefault(r["competition"], {"attempts": 0, "scores": []})
        c["attempts"] += 1
        if r.get("total"):
            c["scores"].append(r["score"] / r["total"] * 100)
    comps = []
    for name, c in sorted(per_comp.items()):
        comps.append({
            "competition": name,
            "attempts": c["attempts"],
            "avg_pct": round(sum(c["scores"]) / len(c["scores"]), 1) if c["scores"] else None,
            "best_pct": round(max(c["scores"]), 1) if c["scores"] else None,
        })
    graded = [r for r in results if r.get("total")]
    return {
        "total_attempts": len(results),
        "total_questions_answered": sum(r.get("answered", 0) for r in results),
        "avg_pct": round(sum(r["score"] / r["total"] * 100 for r in graded) / len(graded), 1) if graded else None,
        "per_competition": comps,
    }


def read_reports(limit=200, user=None):
    """Newest-first slice of reports.jsonl, optionally only one user's."""
    if not REPORTS_FILE.exists():
        return []
    rows = []
    try:
        with REPORTS_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue  # a half-written line from a crash: skip, never explode
                if user is not None and rec.get("user") != user:
                    continue
                rows.append(rec)
    except OSError:
        return []
    rows.reverse()
    return rows[:limit]


def append_report(rec):
    REPORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _store_lock:
        with REPORTS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


class Handler(BaseHTTPRequestHandler):
    def _read_body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def _cookie(self, name, value=None, max_age=None, clear=False):
        if clear:
            return f"{name}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"
        return f"{name}={value}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict"

    def _send(self, body, ctype="application/json", code=200, cookies=None):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if cookies:
            for c in cookies:
                self.send_header("Set-Cookie", c)
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, f):
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(f.read_bytes(), ctype)

    def _serve_figure(self, path):
        """Serve SVGs referenced by figure-bank questions (bank/v2/figures)."""
        from urllib.parse import unquote
        rel = unquote(path[len("/figures/"):])
        root = BANK_V2_FIGURES.resolve()
        target = (BANK_V2_FIGURES / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            self._send('{"error": "bad path"}', code=400)
            return
        if target.is_file():
            self._send_file(target)
        else:
            self._send('{"error": "figure not found"}', code=404)

    def _serve_web(self, path):
        """Serve the built React app from app/web/dist; unknown paths fall back to its index.html (SPA routing)."""
        index = WEB_DIST / "index.html"
        if not index.exists():
            return False
        rel = path.lstrip("/") or "index.html"
        target = (WEB_DIST / rel).resolve()
        try:
            target.relative_to(WEB_DIST.resolve())
        except ValueError:
            return False  # path traversal attempt
        self._send_file(target if target.is_file() else index)
        return True

    def _user(self):
        return current_user(self.headers.get("Cookie"))

    def do_HEAD(self):  # noqa: N802
        """HEAD support for file endpoints (link checkers, fetch probes)."""
        from urllib.parse import urlparse, unquote
        user = self._user()
        path = urlparse(self.path).path
        m = re.match(r"^/shsid-files/(.+)$", path)
        if not user:
            self.send_response(401)
            self.end_headers()
            return
        if not m:
            self.send_response(404)
            self.end_headers()
            return
        p = _shsid_file_path("raw/shsid/" + unquote(m.group(1)))
        if not p:
            self.send_response(404)
            self.end_headers()
            return
        mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        inline = mime == "application/pdf" or mime.startswith("image/")
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(p.stat().st_size))
        disp = "inline" if inline else "attachment"
        self.send_header("Content-Disposition", f'{disp}; filename="{p.name}"')
        self.end_headers()

    def _test_file(self, test_id, user):
        tests_dir = _tests_dir(user)
        f = tests_dir / f"{test_id}.json"
        if f.exists():
            return f
        # fallback to global tests for backward compatibility
        f = TESTS / f"{test_id}.json"
        if f.exists():
            return f
        # teachers may open any student's test (e.g. to classify its questions)
        u = _read_users().get(user) or {}
        if u.get("role") == "teacher":
            safe = re.sub(r"[^A-Za-z0-9_-]", "", str(test_id))[:80]
            for d in USERS_DIR.glob(f"*/tests/{safe}.json"):
                return d
        return None

    def do_GET(self):
        path = self.path.split("?")[0]
        user = self._user()
        if path == "/":
            index = WEB_DIST / "index.html"
            if index.exists():
                self._send_file(index)
            else:
                self._send((STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/legacy":
            self._send((STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/me":
            info = {"user": user}
            if user:
                u = _read_users().get(user) or {}
                info["role"] = u.get("role", "student")
                if u.get("school"):
                    info["school"] = u["school"]
            self._send(json.dumps(info))
        elif path == "/api/tests":
            self._send(json.dumps(list_tests(user)))
        elif path == "/api/banks":
            self._send(json.dumps(list_banks(user)))
        elif path == "/api/taxonomy":
            from urllib.parse import parse_qs
            wanted = (parse_qs(self.path.partition("?")[2]).get("id") or [None])[0]
            tax_doc = load_taxonomy(wanted)
            if tax_doc is None:
                self._send('{"error": "taxonomy not found"}', code=404)
            else:
                self._send(json.dumps(tax_doc))
        elif path == "/api/questions":
            # Bank browser: search + filter over every question on disk.
            from urllib.parse import parse_qs
            qs = parse_qs(self.path.partition("?")[2])
            one = lambda k: (qs.get(k) or [None])[0]  # noqa: E731
            def flag(name):
                raw = one(name)
                if raw is None or raw == "":
                    return None
                return raw not in ("0", "false", "no")
            page = search_questions(
                query=one("q"),
                comps=[c for c in (qs.get("comp") or []) if c] or None,
                version=_as_int(one("v")),
                domain=one("domain"),
                topic=one("topic"),
                level_min=_as_int(one("level_min")),
                level_max=_as_int(one("level_max")),
                qtype=one("type"),
                figure=flag("figure"),
                classified=flag("classified"),
                sort=one("sort") or "default",
                limit=_as_int(one("limit"), 30) or 30,
                offset=_as_int(one("offset"), 0) or 0,
            )
            self._send(json.dumps(page, ensure_ascii=False), "application/json; charset=utf-8")
        elif path.startswith("/figures/"):
            self._serve_figure(path)
        elif m := re.match(r"^/api/generate/([a-z0-9_]+)(?:/(.+))?$", path):
            from urllib.parse import unquote, parse_qs
            slug = m.group(1)
            rnd = unquote(m.group(2)) if m.group(2) else None
            query = parse_qs(self.path.partition("?")[2])
            try:
                wanted = int((query.get("v") or ["1"])[0])
            except ValueError:
                wanted = 1
            wanted = 2 if wanted == 2 else 1
            used_version, fell_back = wanted, False
            test = generate_test(slug, rnd, user, version=wanted)
            if not test and wanted == 2:
                # The figure bank is optional: if it is missing or incomplete for
                # this competition, serve a classic test instead of failing.
                test = generate_test(slug, rnd, user, version=1)
                used_version, fell_back = 1, True
            if test:
                self._send(json.dumps({"ok": True, "id": test["id"],
                                       "bank_version": used_version,
                                       "fallback": fell_back}))
            else:
                self._send('{"error": "bank incomplete for this competition"}', code=400)
        elif path == "/api/reports":
            # Problem reports filed from the bank browser / test runner.
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                from urllib.parse import parse_qs
                qs = parse_qs(self.path.partition("?")[2])
                limit = _as_int((qs.get("limit") or ["50"])[0], 50) or 50
                limit = max(1, min(200, limit))
                rows = read_reports(limit=limit, user=user)
                self._send(json.dumps({"reports": rows, "count": len(rows)}, ensure_ascii=False),
                           "application/json; charset=utf-8")
        elif path == "/api/announcements":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                f = ROOT / "announcements.json"
                try:
                    items = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
                except Exception:
                    items = []
                self._send(json.dumps({"announcements": items}))
        elif path == "/api/friends":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                d = _read_friends()
                mine = _friend_entry(d, user)
                friends = [{"username": f, "online": is_online(f)} for f in mine["friends"]]
                self._send(json.dumps({
                    "friends": friends,
                    "incoming": mine["incoming"],
                    "outgoing": mine["outgoing"],
                }))
        elif m := re.match(r"^/api/chat/([a-z0-9_]+)$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                other = m.group(1)
                mine = _friend_entry(_read_friends(), user)
                if other not in mine["friends"]:
                    self._send('{"error": "not friends"}', code=403)
                else:
                    from urllib.parse import parse_qs, urlparse
                    qs = parse_qs(urlparse(self.path).query)
                    try:
                        since = float(qs.get("since", [0])[0])
                    except ValueError:
                        since = 0
                    msgs = read_messages(user, other, since)
                    self._send(json.dumps({"messages": msgs, "online": is_online(other)}))
        elif path == "/api/pk":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                games = []
                if PK_DIR.exists():
                    for f in sorted(PK_DIR.glob("*.json")):
                        try:
                            g = json.loads(f.read_text(encoding="utf-8"))
                        except Exception:
                            continue
                        if _pk_user_in(g, user):
                            games.append(_pk_maybe_expire(g))
                games.sort(key=lambda g: g.get("created_at", ""), reverse=True)
                views = [(pk_race_view if g.get("mode") == "race" else pk_game_view)(g, user) for g in games[:50]]
                self._send(json.dumps({
                    "games": views,
                    "levels": sorted(PK_LEVELS),
                }))
        elif path == "/api/pk/invites":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                invites = []
                if PK_DIR.exists():
                    for f in PK_DIR.glob("*.json"):
                        try:
                            g = json.loads(f.read_text(encoding="utf-8"))
                        except Exception:
                            continue
                        g = _pk_maybe_expire(g)
                        if g.get("status") == "pending" and _pk_pending_for(g, user):
                            if g.get("mode") == "race":
                                others = [p for p in g.get("players", [])
                                          if p not in (user, g.get("host"))]
                                invites.append({"game_id": g["id"], "mode": "race",
                                                "from": g.get("host"), "others": others,
                                                "slug": g.get("slug"), "difficulty": g.get("difficulty")})
                            else:
                                invites.append({"game_id": g["id"], "mode": "duel",
                                                "from": g.get("challenger"),
                                                "slug": g.get("slug"), "difficulty": g.get("difficulty")})
                invites.sort(key=lambda i: i["game_id"])
                self._send(json.dumps({"count": len(invites), "invites": invites}))
        elif path == "/api/friends/badge":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                mine = _friend_entry(_read_friends(), user)
                self._send(json.dumps({"count": len(mine.get("incoming", []))}))
        elif m := re.match(r"^/api/pk/([a-z0-9_]+)$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                g = _read_pk(m.group(1))
                if not g or not _pk_user_in(g, user):
                    self._send('{"error": "not found"}', code=404)
                else:
                    g = _pk_maybe_expire(g)
                    view = pk_race_view(g, user) if g.get("mode") == "race" else pk_game_view(g, user)
                    self._send(json.dumps(view))
        elif path == "/api/results":
            # PK attempts show up in the PK tab history, not in My Tests
            results = [r for r in read_results(user)
                       if not str(r.get("test_id", "")).startswith("pk_")]
            self._send(json.dumps(results))
        elif path == "/api/practice":
            if not user:
                self._send('{"guest": true}')
            else:
                self._send(json.dumps(_load_json(_practice_file(user), {})))
        elif path == "/api/classes":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                classes = _read_classes()
                teaching = [{"code": c["code"], "name": c["name"], "school": c["school"],
                             "students": c.get("students", [])}
                            for c in classes.values() if c.get("teacher") == user]
                joined = [{"code": c["code"], "name": c["name"], "school": c["school"],
                           "teacher": c.get("teacher")}
                          for c in classes.values() if user in c.get("students", [])]
                self._send(json.dumps({"teaching": teaching, "joined": joined}))
        elif m := re.match(r"^/api/class/([A-Za-z0-9_-]+)/reports$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                c = _read_classes().get(m.group(1))
                if not c or c.get("teacher") != user:
                    self._send('{"error": "not found"}', code=404)
                else:
                    reps = []
                    if CLASS_REPORTS_FILE.exists():
                        for line in CLASS_REPORTS_FILE.read_text(encoding="utf-8").splitlines():
                            if not line.strip():
                                continue
                            try:
                                r = json.loads(line)
                            except Exception:
                                continue
                            if r.get("class_id") == c["code"]:
                                reps.append(r)
                    self._send(json.dumps({"reports": list(reversed(reps))[:200]}))
        elif path == "/api/schools":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                seen = {}
                for u in _read_users().values():
                    if u.get("role", "student") == "teacher" and (u.get("school") or "").strip():
                        seen.setdefault(_norm_school(u["school"]), u["school"].strip())
                self._send(json.dumps({"schools": sorted(seen.values(), key=str.casefold)}))
        elif path == "/api/school/docs":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                _, norm = _user_school_entry(user)
                if not norm:
                    self._send('{"error": "join a school first"}', code=403)
                else:
                    from urllib.parse import parse_qs, urlparse
                    qs = parse_qs(urlparse(self.path).query)
                    cat = (qs.get("category", [""])[0] or "").strip().lower()
                    docs = [d for d in _read_school_docs().values() if _doc_visible_to(d, norm)]
                    if cat:
                        docs = [d for d in docs if d.get("category") == cat]
                    docs.sort(key=lambda d: (d.get("category", ""), d.get("chapter", "").casefold(),
                                             d.get("title", "").casefold(), d.get("uploaded_at", "")))
                    self._send(json.dumps({"categories": DOC_CATEGORIES, "docs": docs}))
        elif m := re.match(r"^/api/school/docs/([a-f0-9]+)/download$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                doc = _read_school_docs().get(m.group(1))
                _, norm = _user_school_entry(user)
                if not doc or not norm or not _doc_visible_to(doc, norm):
                    self._send('{"error": "not found"}', code=404)
                else:
                    f = _doc_file(doc)
                    if not f.exists():
                        self._send('{"error": "file missing"}', code=404)
                    else:
                        from urllib.parse import parse_qs, urlparse
                        qs = parse_qs(urlparse(self.path).query)
                        inline = qs.get("inline", [""])[0] == "1" and doc["ext"] in ("pdf", "png", "jpg", "jpeg", "txt", "md")
                        disp = "inline" if inline else "attachment"
                        name = doc.get("filename") or f"{doc['title']}.{doc['ext']}"
                        name = name.replace("\\", "_").replace('"', "_")
                        data = f.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", DOC_MIME.get(doc["ext"], "application/octet-stream"))
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header("Content-Disposition", f'{disp}; filename="{name}"')
                        self.end_headers()
                        self.wfile.write(data)
        elif path == "/api/stats":
            self._send(json.dumps(compute_stats(user)))
        elif m := re.match(r"^/api/test/([a-z0-9_]+)$", path):
            f = self._test_file(m.group(1), user)
            if f and f.exists():
                self._send(f.read_bytes())
            else:
                self._send('{"error": "not found"}', code=404)
        elif m := re.match(r"^/api/test/([a-z0-9_]+)/classify$", path):
            tid = m.group(1)
            self._send(json.dumps({"items": _load_classification(tid)}, ensure_ascii=False))
        elif path == "/api/shsid":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                self._send(json.dumps(_shsid_index(), ensure_ascii=False))
        elif m := re.match(r"^/shsid-files/(.+)$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
                return
            from urllib.parse import unquote
            p = _shsid_file_path("raw/shsid/" + unquote(m.group(1)))
            if not p:
                self._send('{"error": "not found"}', code=404)
                return
            data = p.read_bytes()
            mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
            inline = mime == "application/pdf" or mime.startswith("image/")
            disp = "inline" if inline else "attachment"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f'{disp}; filename="{p.name}"')
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/worksheets":
            out = []
            if user and WORKSHEETS_DIR.exists():
                files = sorted(WORKSHEETS_DIR.glob("*.json"),
                               key=lambda p: p.stat().st_mtime, reverse=True)
                for f in files:
                    try:
                        d = json.loads(f.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    if d.get("owner") == user:
                        out.append({"id": d["id"], "title": d["title"],
                                    "n_questions": len(d.get("questions", [])),
                                    "created_at": d.get("created_at", "")})
            self._send(json.dumps(out, ensure_ascii=False))
        elif m := re.match(r"^/api/worksheet/([a-f0-9]{8,16})$", path):
            f = WORKSHEETS_DIR / f"{m.group(1)}.json"
            if f.exists():
                self._send(f.read_bytes())
            else:
                self._send('{"error": "not found"}', code=404)
        elif not path.startswith("/api/") and self._serve_web(path):
            pass  # React SPA asset or client-side route
        else:
            self._send('{"error": "not found"}', code=404)

    def do_POST(self):
        path = self.path.split("?")[0]
        user = self._user()
        if path == "/api/register":
            data = self._read_body()
            username = (data.get("username") or "").strip().lower()
            password = data.get("password") or ""
            if not username or not password:
                self._send(json.dumps({"error": "username and password required"}), code=400)
                return
            if not re.fullmatch(r"[a-z0-9_]{3,32}", username):
                self._send(json.dumps({"error": "username must be 3-32 chars, lowercase letters/numbers/underscore"}), code=400)
                return
            users = _read_users()
            if username in users:
                self._send(json.dumps({"error": "username taken"}), code=409)
                return
            role = data.get("role") or "student"
            if role not in ("student", "teacher"):
                role = "student"
            school = (data.get("school") or "").strip()[:80]
            if role == "teacher" and not school:
                self._send(json.dumps({"error": "school / organization name required for teacher accounts"}), code=400)
                return
            salt, key = _hash_password(password)
            users[username] = {"username": username, "salt": salt, "key": key,
                               "role": role, "created_at": time.strftime("%Y-%m-%d %H:%M:%S")}
            if school:
                users[username]["school"] = school
            _write_users(users)
            sid = _make_session(username)
            self._send(json.dumps({"ok": True, "user": username}), cookies=[self._cookie("session_id", sid, SESSION_DAYS * 86400)])
        elif path == "/api/login":
            data = self._read_body()
            username = (data.get("username") or "").strip().lower()
            password = data.get("password") or ""
            users = _read_users()
            u = users.get(username)
            if not u or not _verify_password(password, u["salt"], u["key"]):
                self._send('{"error": "invalid username or password"}', code=401)
                return
            sid = _make_session(username)
            self._send(json.dumps({"ok": True, "user": username}), cookies=[self._cookie("session_id", sid, SESSION_DAYS * 86400)])
        elif path == "/api/logout":
            cookies = _parse_cookies(self.headers.get("Cookie"))
            sid = cookies.get("session_id")
            if sid:
                _delete_session(sid)
            self._send(json.dumps({"ok": True}), cookies=[self._cookie("session_id", clear=True)])
        elif m := re.match(r"^/api/test/([a-z0-9_]+)/classify$", path):
            u = _read_users().get(user) or {}
            if u.get("role", "student") != "teacher":
                self._send('{"error": "teachers only"}', code=403)
                return
            data = self._read_body()
            items = _clean_classification(data.get("items"))
            _classification_file(m.group(1)).write_text(
                json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
            self._send('{"ok": true}')
        elif path == "/api/practice_similar":
            if not user:
                self._send('{"error": "login required"}', code=401)
                return
            data = self._read_body()
            items = data.get("items")
            if not isinstance(items, list) or not items:
                self._send('{"error": "no items"}', code=400)
                return
            try:
                ws = build_similar_test(user, items[:25])
                self._send(json.dumps({"ok": True, "id": ws["id"]}))
            except ValueError as e:
                self._send(json.dumps({"error": str(e)}), code=400)
        elif path == "/api/report":
            # "This question is broken": one JSONL row per report, guests allowed.
            try:
                data = self._read_body()
            except Exception:
                self._send('{"error": "bad json"}', code=400)
                return
            qid = str(data.get("qid") or "").strip()
            reason = str(data.get("reason") or "").strip()
            if not qid:
                self._send('{"error": "qid required"}', code=400)
                return
            if reason not in REPORT_REASONS:
                self._send('{"error": "unknown reason"}', code=400)
                return
            rec = {
                "id": "rep" + time.strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(3),
                "qid": qid[:200],
                "reason": reason,
                "note": str(data.get("note") or "").strip()[:REPORT_NOTE_MAX],
                "bank": str(data.get("bank") or "")[:80],
                "version": _as_int(data.get("version")),
                "source": str(data.get("source") or "")[:200],
                "competition": str(data.get("competition") or "")[:60],
                # keep a snippet so triage works without the banks at hand
                "question": str(data.get("question") or "")[:400],
                "user": user,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "open",
            }
            try:
                append_report(rec)
            except OSError as exc:
                self._send(json.dumps({"error": "could not save report: %s" % exc}), code=500)
                return
            self._send(json.dumps({"ok": True, "id": rec["id"]}))
        elif path == "/api/result":
            if not user:
                # guests can take tests but results aren't persisted
                self._send('{"ok": true, "guest": true}')
                return
            try:
                data = self._read_body()
                rfile = _results_file(user)
                rec = {
                    "test_id": data.get("test_id"),
                    "title": data.get("title"),
                    "competition": data.get("competition"),
                    "score": data.get("score"),
                    "total": data.get("total"),
                    "answered": data.get("answered", 0),
                    "duration_s": data.get("duration_s"),
                    "details": _clean_details(data.get("details")),
                    "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "user": user,
                }
                rfile.parent.mkdir(parents=True, exist_ok=True)
                with rfile.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                # push a report copy to every class this student belongs to
                try:
                    mine = [c for c in _read_classes().values() if user in c.get("students", [])]
                    if mine:
                        total = rec.get("total")
                        pct = round(rec["score"] / total * 100, 1) if total else None
                        with _store_lock:
                            with CLASS_REPORTS_FILE.open("a", encoding="utf-8") as f:
                                for c in mine:
                                    rep = {"class_id": c["code"], "student": user,
                                           "test_id": rec.get("test_id"), "title": rec.get("title"),
                                           "competition": rec.get("competition"),
                                           "score": rec.get("score"), "total": total, "pct": pct,
                                           "answered": rec.get("answered", 0),
                                           "duration_s": rec.get("duration_s"),
                                           "submitted_at": rec.get("submitted_at")}
                                    f.write(json.dumps(rep, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                self._send('{"ok": true}')
            except Exception as e:
                self._send(json.dumps({"error": str(e)}), code=400)
        elif m := re.match(r"^/api/friends/(request|accept|decline|remove)$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                data = self._read_body()
                other = (data.get("username") or "").strip().lower()
                users = _read_users()
                action = m.group(1)
                if not other or other == user:
                    self._send('{"error": "invalid username"}', code=400)
                elif other not in users:
                    self._send('{"error": "user not found"}', code=404)
                else:
                    d = _read_friends()
                    mine = _friend_entry(d, user)
                    theirs = _friend_entry(d, other)
                    if action == "request":
                        if other in mine["friends"]:
                            self._send('{"error": "already friends"}', code=409)
                        elif user in theirs["incoming"] or other in mine["outgoing"]:
                            self._send('{"error": "request already sent"}', code=409)
                        else:
                            mine["outgoing"].append(other)
                            theirs["incoming"].append(user)
                            _write_friends(d)
                            self._send('{"ok": true}')
                    elif action in ("accept", "decline"):
                        if user not in theirs["outgoing"] or other not in mine["incoming"]:
                            self._send('{"error": "no such request"}', code=404)
                        else:
                            theirs["outgoing"].remove(user)
                            mine["incoming"].remove(other)
                            if action == "accept":
                                if other not in mine["friends"]:
                                    mine["friends"].append(other)
                                if user not in theirs["friends"]:
                                    theirs["friends"].append(user)
                            _write_friends(d)
                            self._send('{"ok": true}')
                    else:  # remove
                        if other not in mine["friends"]:
                            self._send('{"error": "not friends"}', code=404)
                        else:
                            mine["friends"].remove(other)
                            if user in theirs["friends"]:
                                theirs["friends"].remove(user)
                            _write_friends(d)
                            self._send('{"ok": true}')
        elif m := re.match(r"^/api/chat/([a-z0-9_]+)$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                other = m.group(1)
                mine = _friend_entry(_read_friends(), user)
                if other not in mine["friends"]:
                    self._send('{"error": "not friends"}', code=403)
                else:
                    data = self._read_body()
                    text = (data.get("text") or "").strip()[:500]
                    if not text:
                        self._send('{"error": "empty message"}', code=400)
                    else:
                        msg = append_message(user, other, text)
                        self._send(json.dumps({"ok": True, "message": msg}))
        elif path == "/api/class/create":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                u = _read_users().get(user) or {}
                if u.get("role", "student") != "teacher":
                    self._send('{"error": "teacher account required"}', code=403)
                else:
                    data = self._read_body()
                    name = (data.get("name") or "").strip()[:60]
                    code = (data.get("code") or "").strip().upper().replace(" ", "-")
                    if not name or not re.fullmatch(r"[A-Z0-9_-]{3,24}", code):
                        self._send(json.dumps({"error": "class name and a 3-24 char code (letters/numbers/-_) required"}), code=400)
                    else:
                        classes = _read_classes()
                        if code in classes:
                            self._send(json.dumps({"error": "code already taken"}), code=409)
                        else:
                            classes[code] = {"code": code, "name": name,
                                             "school": u.get("school", ""),
                                             "teacher": user, "students": [],
                                             "created_at": time.strftime("%Y-%m-%d %H:%M:%S")}
                            _write_classes(classes)
                            self._send(json.dumps({"ok": True, "code": code}))
        elif path == "/api/class/join":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                data = self._read_body()
                code = (data.get("code") or "").strip().upper().replace(" ", "-")
                classes = _read_classes()
                c = classes.get(code)
                if not c:
                    self._send(json.dumps({"error": "invalid class code"}), code=404)
                elif user == c.get("teacher"):
                    self._send(json.dumps({"error": "you teach this class"}), code=400)
                else:
                    if user not in c["students"]:
                        c["students"].append(user)
                        _write_classes(classes)
                    self._send(json.dumps({"ok": True, "name": c["name"], "school": c["school"]}))
        elif m := re.match(r"^/api/pk/(challenge|respond|start)$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                data = self._read_body()
                action = m.group(1)
                if action == "challenge":
                    mode = data.get("mode") or "duel"
                    slug = (data.get("slug") or "").strip()
                    difficulty = (data.get("difficulty") or "").strip()
                    if slug not in COMP_META or COMP_META[slug][4]:
                        self._send(json.dumps({"error": "competition not available for PK"}), code=400)
                    elif difficulty not in PK_LEVELS:
                        self._send(json.dumps({"error": "invalid difficulty"}), code=400)
                    else:
                        gid = secrets.token_hex(8)
                        now = time.strftime("%Y-%m-%d %H:%M:%S")
                        if mode == "race":
                            ops = [o.strip().lower() for o in (data.get("opponents") or []) if isinstance(o, str)][:20]
                            ops = [o for o in dict.fromkeys(ops) if o and o != user]
                            mine = _friend_entry(_read_friends(), user)
                            if not ops or any(o not in mine["friends"] for o in ops):
                                self._send(json.dumps({"error": "pick at least one friend to invite"}), code=403)
                                return
                            game = {"id": gid, "mode": "race", "host": user,
                                    "players": [user] + ops, "accepted": [user],
                                    "slug": slug, "difficulty": difficulty,
                                    "status": "pending", "test_id": None, "created_at": now}
                        else:
                            opponent = (data.get("opponent") or "").strip().lower()
                            mine = _friend_entry(_read_friends(), user)
                            if opponent not in mine["friends"]:
                                self._send(json.dumps({"error": "not friends"}), code=403)
                                return
                            game = {"id": gid, "challenger": user, "opponent": opponent,
                                    "slug": slug, "difficulty": difficulty,
                                    "status": "pending", "test_id": None, "created_at": now}
                        _write_pk(game)
                        self._send(json.dumps({"ok": True, "id": gid}))
                elif action == "start":
                    gid = (data.get("game_id") or "").strip()
                    game = _read_pk(gid)
                    if not game or game.get("mode") != "race" or game.get("host") != user:
                        self._send('{"error": "not found"}', code=404)
                    elif game["status"] != "pending":
                        self._send('{"error": "already started"}', code=409)
                    elif len(game.get("accepted", [])) < 2:
                        self._send(json.dumps({"error": "need at least 2 accepted players"}), code=400)
                    elif build_pk_test(game):
                        _write_pk(game)
                        self._send(json.dumps({"ok": True, "test_id": game["test_id"]}))
                    else:
                        self._send('{"error": "could not build test for this competition"}', code=400)
                else:
                    gid = (data.get("game_id") or "").strip()
                    accept = bool(data.get("accept"))
                    game = _read_pk(gid)
                    if not game or not _pk_user_in(game, user):
                        self._send('{"error": "not found"}', code=404)
                    elif game["status"] != "pending":
                        self._send('{"error": "already responded"}', code=409)
                    elif game.get("mode") == "race":
                        if accept:
                            if user not in game["accepted"]:
                                game["accepted"].append(user)
                            _write_pk(game)
                            self._send('{"ok": true}')
                        else:
                            game["players"].remove(user)
                            if len(game["players"]) <= 1:
                                game["status"] = "declined"
                            _write_pk(game)
                            self._send('{"ok": true}')
                    elif not accept:
                        game["status"] = "declined"
                        _write_pk(game)
                        self._send('{"ok": true}')
                    elif build_pk_test(game):
                        _write_pk(game)
                        self._send(json.dumps({"ok": True, "test_id": game["test_id"]}))
                    else:
                        self._send('{"error": "could not build test for this competition"}', code=400)
        elif path == "/api/school/join":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                data = self._read_body()
                want = (data.get("school") or "").strip()[:80]
                if not want:
                    self._send('{"error": "school name required"}', code=400)
                else:
                    want_norm = _norm_school(want)
                    display = None
                    for u in _read_users().values():
                        if u.get("role", "student") == "teacher" and _norm_school(u.get("school")) == want_norm:
                            display = u["school"].strip()
                            break
                    if not display:
                        self._send('{"error": "no teacher found for that school — check the name"}', code=404)
                    else:
                        with _store_lock:
                            users = _read_users()
                            users[user]["school"] = display
                            _write_users(users)
                        self._send(json.dumps({"ok": True, "school": display}))
        elif path == "/api/school/leave":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                with _store_lock:
                    users = _read_users()
                    users[user].pop("school", None)
                    _write_users(users)
                self._send('{"ok": true}')
        elif path == "/api/school/docs/upload":
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                u = _read_users().get(user) or {}
                if u.get("role", "student") != "teacher":
                    self._send('{"error": "teacher account required"}', code=403)
                else:
                    school, norm = _user_school_entry(user)
                    if not norm:
                        self._send('{"error": "teacher account has no school"}', code=400)
                    else:
                        try:
                            import base64
                            data = self._read_body()
                            category = (data.get("category") or "").strip().lower()
                            chapter = (data.get("chapter") or "").strip()[:80]
                            title = (data.get("title") or "").strip()[:120]
                            raw_name = os.path.basename(data.get("filename") or "")[:120]
                            ext = raw_name.rsplit(".", 1)[1].lower() if "." in raw_name else ""
                            if category not in DOC_CATEGORIES:
                                self._send(json.dumps({"error": "invalid category"}), code=400)
                            elif not chapter:
                                self._send(json.dumps({"error": "chapter required"}), code=400)
                            elif ext not in DOC_MIME:
                                self._send(json.dumps({"error": "file type not allowed"}), code=400)
                            else:
                                blob = base64.b64decode(data.get("data_b64") or "", validate=True)
                                if not blob:
                                    self._send(json.dumps({"error": "empty file"}), code=400)
                                elif len(blob) > DOC_MAX_BYTES:
                                    self._send(json.dumps({"error": "file too large (max 25 MB)"}), code=400)
                                else:
                                    doc_id = secrets.token_hex(8)
                                    doc = {"id": doc_id, "school": school, "category": category,
                                           "chapter": chapter,
                                           "title": title or raw_name.rsplit(".", 1)[0] or doc_id,
                                           "filename": raw_name, "ext": ext, "size": len(blob),
                                           "uploader": user,
                                           "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S")}
                                    SCHOOL_DOCS_DIR.mkdir(exist_ok=True)
                                    _doc_file(doc).write_bytes(blob)
                                    with _store_lock:
                                        docs = _read_school_docs()
                                        docs[doc_id] = doc
                                        _write_school_docs(docs)
                                    self._send(json.dumps({"ok": True, "id": doc_id}))
                        except Exception as e:
                            self._send(json.dumps({"error": str(e)}), code=400)
        elif m := re.match(r"^/api/school/docs/([a-f0-9]+)/edit$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                u = _read_users().get(user) or {}
                if u.get("role", "student") != "teacher":
                    self._send('{"error": "teacher account required"}', code=403)
                else:
                    _, norm = _user_school_entry(user)
                    docs = _read_school_docs()
                    doc = docs.get(m.group(1))
                    if not doc or not norm or not _doc_visible_to(doc, norm):
                        self._send('{"error": "not found"}', code=404)
                    else:
                        data = self._read_body()
                        category = (data.get("category") or doc["category"]).strip().lower()
                        if category not in DOC_CATEGORIES:
                            self._send(json.dumps({"error": "invalid category"}), code=400)
                        else:
                            doc["category"] = category
                            if "chapter" in data:
                                doc["chapter"] = (data.get("chapter") or "").strip()[:80] or doc["chapter"]
                            if "title" in data:
                                doc["title"] = (data.get("title") or "").strip()[:120] or doc["title"]
                            with _store_lock:
                                docs = _read_school_docs()
                                if m.group(1) in docs:
                                    docs[m.group(1)] = doc
                                    _write_school_docs(docs)
                            self._send('{"ok": true}')
        elif m := re.match(r"^/api/school/docs/([a-f0-9]+)/delete$", path):
            if not user:
                self._send('{"error": "login required"}', code=401)
            else:
                u = _read_users().get(user) or {}
                if u.get("role", "student") != "teacher":
                    self._send('{"error": "teacher account required"}', code=403)
                else:
                    _, norm = _user_school_entry(user)
                    docs = _read_school_docs()
                    doc = docs.get(m.group(1))
                    if not doc or not norm or not _doc_visible_to(doc, norm):
                        self._send('{"error": "not found"}', code=404)
                    else:
                        with _store_lock:
                            docs = _read_school_docs()
                            docs.pop(m.group(1), None)
                            _write_school_docs(docs)
                        try:
                            _doc_file(doc).unlink()
                        except OSError:
                            pass
                        self._send('{"ok": true}')
        elif path == "/api/worksheet/generate":
            try:
                import base64
                data = self._read_body()
                raw_name = os.path.basename(data.get("filename") or "")[:120]
                blob = base64.b64decode(data.get("data_b64") or "", validate=True)
                ws = generate_worksheet(raw_name, blob, user or "")
                self._send(json.dumps(ws, ensure_ascii=False))
            except Exception as e:
                self._send(json.dumps({"error": str(e)}), code=400)
        elif path == "/api/practice":
            if not user:
                self._send('{"ok": true, "guest": true}')
                return
            data = self._read_body()
            drill = re.sub(r"[^a-z]", "", str(data.get("drill", "")))[:20]
            level = str(data.get("level", ""))[:10]
            pct = float(data.get("pct") or 0)
            time_s = float(data.get("time_s") or 0)
            if not drill or level not in ("easy", "medium", "hard"):
                self._send(json.dumps({"error": "bad request"}), code=400)
                return
            pfile = _practice_file(user)
            with _store_lock:
                stats = _load_json(pfile, {})
                d = stats.setdefault(drill, {}).setdefault(level, {
                    "best_pct": 0, "best_time": None, "sessions": 0, "streak": 0})
                new_best_pct = pct > d["best_pct"]
                new_best_time = d["best_time"] is None or (pct >= 100 and time_s < d["best_time"])
                d["best_pct"] = max(d["best_pct"], pct)
                if new_best_time:
                    d["best_time"] = time_s
                d["sessions"] += 1
                d["streak"] = d["streak"] + 1 if pct >= 80 else 0
                _save_json(pfile, stats)
            self._send(json.dumps({"ok": True, "stats": stats,
                                   "new_best_pct": new_best_pct, "new_best_time": new_best_time}))
        else:
            self._send('{"error": "not found"}', code=404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"MockTest Maker → http://localhost:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
