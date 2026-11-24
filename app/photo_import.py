"""Photo -> paper v1.1: OCR a page image with the remote Unlimited-OCR-2 model and
structure the result into a paper JSON.

The OCR model (vLLM, OpenAI-compatible) returns one block per line:

    <PAGE><BLOCK>title<LEVEL1>[x0, y0, x1, y1]<FORK>text of the block
    <BLOCK>text[x0, y0, x1, y1]<FORK>...
    <BLOCK>image[x0, y0, x1, y1]<FORK>

Block types seen in practice: ``title`` (with an optional ``<LEVELn>``), ``text`` and
``image`` (a picture with no text).  Coordinates live in the model's internal square
canvas (both axes span about 997 units regardless of the image aspect ratio), so
mapping them back to pixels is ``round(coord / 997 * side)``.

Everything here is standard library only: the server must stay dependency free, so
figure crops are cut out of the uploaded PNG by hand (see ``crop_png``).
"""

import base64
import hashlib
import json
import os
import re
import struct
import urllib.error
import urllib.request
import zlib

OCR_BASE = os.environ.get("OCR_BASE_URL", "http://192.168.2.185:8000/v1")
OCR_MODEL = os.environ.get("OCR_MODEL", "unlimited-ocr-2")
OCR_INSTRUCTION = os.environ.get("OCR_INSTRUCTION", "Multi page parsing.")
OCR_TIMEOUT = int(os.environ.get("OCR_TIMEOUT", "600"))
# The server runs with max_model_len=32768.  Measured: an A4@300dpi page costs ~900
# prompt tokens and ~1200 output tokens (30 blocks), so 8192 is a comfortable ceiling.
OCR_MAX_TOKENS = int(os.environ.get("OCR_MAX_TOKENS", "8192"))

# Light-weight chat model that turns the OCR blocks into structured questions.
STRUCT_BASE = os.environ.get("STRUCT_BASE_URL", "http://192.168.2.198:7863/v1")
STRUCT_KEY = os.environ.get("STRUCT_API_KEY", "test_keyu")
STRUCT_MODEL = os.environ.get("STRUCT_MODEL", "global:hy4flash-free")
STRUCT_TIMEOUT = int(os.environ.get("STRUCT_TIMEOUT", "300"))
STRUCT_MAX_TOKENS = int(os.environ.get("STRUCT_MAX_TOKENS", "8192"))

# The model renders every page onto a square canvas; both axes span this many units.
OCR_CANVAS = 997.0
# Grow figure boxes a little: the model's boxes are tight and the mapping is not exact.
FIGURE_PAD = 0.012

BLOCK_RE = re.compile(
    r"<BLOCK>(?P<kind>[a-z_]+)(?:<LEVEL(?P<level>\d+)>)?\s*"
    r"\[\s*(?P<x0>-?\d+)\s*,\s*(?P<y0>-?\d+)\s*,\s*(?P<x1>-?\d+)\s*,\s*(?P<y1>-?\d+)\s*\]"
    r"<FORK>(?P<text>.*?)(?=<BLOCK>|<PAGE>|\Z)",
    re.S,
)

Q_START_RE = re.compile(r"^\s*(\d{1,3})\s*[.)]\s+(.+)$")
OPT_SPLIT_RE = re.compile(r"\(([A-E])\)\s*")
OPT_LINE_RE = re.compile(r"^\s*\(?([A-E])\)?\s*[.)]?\s+(.+)$")
ANS_HEAD_RE = re.compile(r"^\s*(?:answer\s*keys?|answers?|keys?)\s*:?\s*$", re.I)
ANS_PAIR_RE = re.compile(r"(\d{1,3})\s*[.)]?\s*([A-E]|-?\d+(?:\.\d+)?)")
INLINE_ANS_RE = re.compile(r"^\s*answer\s*:\s*(.+?)\s*$", re.I)


def _clean(text):
    text = text.replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def parse_ocr_text(text):
    """Split the raw model output into blocks: {page, kind, level, bbox, text}."""
    blocks = []
    page = 1
    for part in re.split(r"(<PAGE>)", text):
        if part == "<PAGE>":
            page += 1 if blocks else 0
            continue
        for m in BLOCK_RE.finditer(part):
            kind = m.group("kind")
            level = m.group("level")
            body = _clean(m.group("text"))
            blocks.append({
                "page": page,
                "kind": kind,
                "level": int(level) if level else None,
                "bbox": [int(m.group("x0")), int(m.group("y0")),
                         int(m.group("x1")), int(m.group("y1"))],
                "text": body,
            })
    return blocks


def ocr_image(data, base_url=None, model=None, instruction=None, timeout=None):
    """Send one PNG/JPEG page to the OCR model and return its raw text."""
    base = (base_url or OCR_BASE).rstrip("/")
    mime = "image/jpeg" if data[:2] == b"\xff\xd8" else "image/png"
    uri = "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii"))
    payload = {
        "model": model or OCR_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": uri}},
            {"type": "text", "text": instruction or OCR_INSTRUCTION},
        ]}],
        "max_tokens": OCR_MAX_TOKENS,
        "temperature": 0,
    }
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or OCR_TIMEOUT) as resp:
            obj = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise ValueError("OCR request failed: HTTP %s %s" % (exc.code, detail))
    except urllib.error.URLError as exc:
        raise ValueError("OCR server unreachable: %s" % exc.reason)
    try:
        return obj["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise ValueError("OCR response has no message content")


def split_options(text):
    """'（A) 1 (B) 2 ...' or 'A. 1  B. 2' -> [(letter, text), ...]."""
    text = text.strip()
    marks = [(m.start(), m.group(1)) for m in OPT_SPLIT_RE.finditer(text)]
    if len(marks) >= 2:
        out = []
        for i, (pos, letter) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
            body = text[pos:end]
            body = OPT_SPLIT_RE.sub("", body, count=1).strip()
            out.append((letter, body))
        return out
    m = OPT_LINE_RE.match(text)
    if m and len(text) < 400:
        return [(m.group(1), m.group(2).strip())]
    return []


def structure_blocks(blocks):
    """Group OCR blocks into (title, questions).

    Each question: {n, lines, choices: {letter: text}, answer, figures: [bbox, ...]}.
    A block can carry several lines (the OCR merges a stem with its options), so
    every block is expanded into lines before parsing.
    """
    title = None
    questions = []
    current = None
    in_answers = False
    answers = {}

    def consume(text, kind, level):
        nonlocal title, current, in_answers
        if ANS_HEAD_RE.match(text) or (kind == "title" and re.search(r"\bkey\b", text, re.I)):
            in_answers = True
            return
        if in_answers:
            for m in ANS_PAIR_RE.finditer(text):
                answers[int(m.group(1))] = m.group(2)
            return
        if title is None and (kind == "title" or level):
            title = text[:120]
            return
        m = Q_START_RE.match(text)
        if m:
            current = {"n": int(m.group(1)), "lines": [m.group(2).strip()],
                       "choices": {}, "answer": "", "figures": []}
            questions.append(current)
            return
        opts = split_options(text)
        if opts and current is not None:
            for letter, body in opts:
                current["choices"].setdefault(letter, body)
            return
        m_ans = INLINE_ANS_RE.match(text)
        if m_ans and current is not None:
            current["answer"] = m_ans.group(1).strip()
            return
        if current is not None:
            current["lines"].append(text)
        elif title is None:
            title = text[:120]

    for b in blocks:
        if b["kind"] == "image":
            if current is not None:
                current["figures"].append(b["bbox"])
            continue
        lines = [ln.strip() for ln in (b["text"] or "").split("\n") if ln.strip()]
        for i, line in enumerate(lines):
            consume(line, b["kind"] if i == 0 else "text", b["level"] if i == 0 else None)

    for q in questions:
        if not q["answer"] and q["n"] in answers:
            q["answer"] = answers[q["n"]]
        q["question"] = _join_lines(q["lines"])
        q["lines"] = []
    return title, questions


def _join_lines(lines):
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not out:
            out = line
            continue
        joiner = "\n" if out.endswith((":", "：")) or line.startswith(("(", "$")) else " "
        out += joiner + line
    return re.sub(r"[ \t]{2,}", " ", out).strip()


STRUCT_PROMPT = """You convert raw OCR blocks of a scanned exam page into a clean exam paper.

Input: one block per line, in reading order:
[index] kind (x0,y0,x1,y1) :: text
`kind` is one of title, text, image (an image block is a figure and has no text).

Rules:
- Merge blocks that continue the same sentence; a question stem may span several blocks.
- A question starts with a number like "1." "2)" "Q3."; keep the stem without the number.
- Option lines look like "(A) ... (B) ..." and may be on one line or split over blocks: split them per letter.
- The OCR may put a table inside <table>...</table> with the cells run together, e.g.
  "<table>xf(x)03254769</table>" or "<table>xf(x)-4-2-2-16384</table>". Rebuild it as a real
  HTML table inside the stem: <table><tr><th>x</th><th>f(x)</th></tr><tr><td>0</td><td>3</td></tr>...</table>.
  The leading labels are the header row; the numbers that follow are the cells in row-major order
  (two columns when the header has two labels). Keep every value exactly as read; never drop,
  merge or invent a cell, and never leave a bare <table> tag without <tr>/<td> rows.
- A heading "Answer Key" / "Answers" is followed by answers like "1. C 2. 10 3. B": use them to fill `answer`.
- Keep math exactly as OCR gave it (LaTeX inside $...$ stays). Never solve, verify or rewrite a problem.
- Attach a figure to the question that refers to a figure (e.g. "in the figure below") or that sits right next to the image block; put its block index in `figure_block`.
- type: multiple_choice when options exist and the answer is a letter; integer_answer when the answer is an integer; numeric when it is a decimal; proof otherwise.
- Skip headers, footers, page numbers, instructions and anything that is not a question.

Return JSON only, no prose and no code fences:
{"title": "...", "questions": [{"n": 1, "type": "multiple_choice", "question": "...", "choices": {"A": "...", "B": "..."}, "answer": "C", "figure_block": 5}]}
Omit "choices" when there are none; use null for a missing answer or figure_block."""


def blocks_to_lines(blocks):
    """Compact one-line-per-block rendering used as the chat model input."""
    out = []
    for i, b in enumerate(blocks):
        x0, y0, x1, y1 = b["bbox"]
        kind = b["kind"] + ("%d" % b["level"] if b["level"] else "")
        out.append("[%d] %s (%d,%d,%d,%d) :: %s"
                   % (i, kind, x0, y0, x1, y1, b["text"] or "<figure>"))
    return "\n".join(out)


def _post_json(url, payload, headers, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers=dict({"Content-Type": "application/json"}, **headers), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise ValueError("HTTP %s %s" % (exc.code, exc.read().decode("utf-8", "replace")[:300]))
    except urllib.error.URLError as exc:
        raise ValueError("unreachable: %s" % exc.reason)


def _json_from_text(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the reply")
    return json.loads(text[start:end + 1])


def structure_with_llm(blocks, base_url=None, api_key=None, model=None,
                       max_tokens=None, timeout=None):
    """Turn OCR blocks into questions with a small chat model.

    Returns (title, questions) in the same shape as ``structure_blocks``.  Raises
    ``ValueError`` when the model is unreachable or answers with unusable JSON.
    """
    if not blocks:
        raise ValueError("no blocks to structure")
    payload = {
        "model": model or STRUCT_MODEL,
        "messages": [
            {"role": "system", "content": STRUCT_PROMPT},
            {"role": "user", "content": blocks_to_lines(blocks)},
        ],
        "max_tokens": max_tokens or STRUCT_MAX_TOKENS,
        "temperature": 0,
    }
    headers = {}
    key = api_key if api_key is not None else STRUCT_KEY
    if key:
        headers["Authorization"] = "Bearer " + key
    obj = _post_json((base_url or STRUCT_BASE).rstrip("/") + "/chat/completions",
                     payload, headers, timeout or STRUCT_TIMEOUT)
    try:
        content = obj["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise ValueError("structure model returned no content")
    data = _json_from_text(content)
    raw_questions = data.get("questions")
    if not isinstance(raw_questions, list) or not raw_questions:
        raise ValueError("structure model returned no questions")

    questions = []
    for idx, raw in enumerate(raw_questions, 1):
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("question") or "").strip()
        if not text:
            continue
        choices = raw.get("choices") or {}
        if isinstance(choices, list):
            letters = "ABCDE"
            choices = {letters[i]: str(c) for i, c in enumerate(choices) if str(c).strip()}
        elif isinstance(choices, dict):
            choices = {str(k).upper(): str(v).strip() for k, v in choices.items() if str(v).strip()}
        else:
            choices = {}
        figures = []
        block_idx = raw.get("figure_block")
        if isinstance(block_idx, int) and 0 <= block_idx < len(blocks):
            if blocks[block_idx]["kind"] == "image":
                figures.append(blocks[block_idx]["bbox"])
        answer = raw.get("answer")
        answer = "" if answer is None else str(answer).strip()
        qtype = str(raw.get("type") or "").strip()
        if qtype not in ("multiple_choice", "integer_answer", "numeric", "proof"):
            qtype = question_type(choices, answer)
        questions.append({
            "n": idx,
            "lines": [],
            "question": text,
            "choices": choices,
            "answer": answer,
            "figures": figures,
            "type": qtype,
        })
    if not questions:
        raise ValueError("structure model produced no usable question")
    return str(data.get("title") or "").strip()[:120], questions


def apply_answer_key(blocks, questions):
    """Fill empty answers from an 'Answer Key' / 'Answers' section, in place.

    The chat model often skips the key, so this deterministic pass runs after it.
    Returns the number of answers filled.
    """
    if not questions:
        return 0
    answers = {}
    in_key = False
    for b in blocks:
        if b["kind"] == "image":
            continue
        text = b["text"]
        if not text:
            continue
        if ANS_HEAD_RE.match(text) or re.match(r"^\s*(?:answer\s*keys?|answers?)\b", text, re.I):
            in_key = True
            tail = re.sub(r"^\s*(?:answer\s*keys?|answers?)\s*:?\s*", "", text, flags=re.I)
            if tail:
                text = tail
            else:
                continue
        if not in_key:
            continue
        for m in ANS_PAIR_RE.finditer(text):
            answers[int(m.group(1))] = m.group(2)
    if not answers:
        return 0
    changed = 0
    for q in questions:
        got = answers.get(q["n"])
        if not got:
            continue
        choices = q.get("choices") or {}
        if len(choices) >= 2:
            # A printed key for a multiple-choice item is a single letter.
            if not re.fullmatch(r"[A-E]", got):
                continue
            if q.get("answer") != got:
                q["answer"] = got
                changed += 1
            if q.get("type") != "multiple_choice":
                q["type"] = "multiple_choice"
            continue
        # Free-form items: the key may hold a whole rule ("f(x) = x + 3"), which
        # is not a checkable answer, and proof items have no answer at all.
        if q.get("type") == "proof":
            continue
        if q.get("answer") != got:
            q["answer"] = got
            changed += 1
    return changed


def question_type(choices, answer):
    if len(choices) >= 2 and re.fullmatch(r"[A-E]", answer or ""):
        return "multiple_choice"
    if re.fullmatch(r"-?\d{1,15}", answer or ""):
        return "integer_answer"
    if re.fullmatch(r"-?\d+(?:\.\d+)?", answer or ""):
        return "numeric"
    return "proof"


def _scale(coord, side):
    return int(round(coord / OCR_CANVAS * side))


def figure_box(bbox, width, height):
    """Model bbox -> pixel box on the page, padded and clamped."""
    x0, y0, x1, y1 = bbox
    px0, py0 = _scale(x0, width), _scale(y0, height)
    px1, py1 = _scale(x1, width), _scale(y1, height)
    pad_x = int(width * FIGURE_PAD)
    pad_y = int(height * FIGURE_PAD)
    px0 = max(0, px0 - pad_x)
    py0 = max(0, py0 - pad_y)
    px1 = min(width, px1 + pad_x)
    py1 = min(height, py1 + pad_y)
    if px1 - px0 < 8 or py1 - py0 < 8:
        return None
    return [px0, py0, px1, py1]


def build_paper(title, questions, paper_id="photo_1", page_ref=None, figures=None):
    """Turn structured questions into a paper v1.1 dict.

    ``figures`` maps question number -> {"src": ..., "width": ..., "height": ...}.
    """
    figures = figures or {}
    out = []
    for i, q in enumerate(questions, 1):
        choices = q["choices"]
        letters = sorted(choices)
        item = {
            "n": i,
            "type": q.get("type") or question_type(choices, q["answer"]),
            "question": q["question"],
            "points": 1,
        }
        if letters:
            item["choices"] = {L: choices[L] for L in letters}
        if q["answer"]:
            item["answer"] = q["answer"]
        fig = figures.get(q["n"])
        if fig:
            item["figure"] = {
                "kind": "image",
                "state": "ready",
                "placement": "prompt",
                "src": fig["src"],
                "width": fig["width"],
                "height": fig["height"],
                "alt": "Figure for question %d" % i,
            }
            if fig.get("sha256"):
                item["figure"]["sha256"] = fig["sha256"]
        if page_ref:
            item["source"] = page_ref
        out.append(item)
    return {
        "format_version": "1.1",
        "paper_version": 1,
        "id": paper_id,
        "title": title or "Photo import",
        "total_points": sum(q["points"] for q in out),
        "generator": {"kind": "photo_ocr", "model": OCR_MODEL, "seed": None},
        "questions": out,
    }


# --- PNG cropping (standard library only) ------------------------------------------

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _png_chunks(data):
    if not data.startswith(PNG_SIG):
        raise ValueError("not a PNG file")
    pos = len(PNG_SIG)
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        yield ctype, body
        pos += 12 + length
        if ctype == b"IEND":
            break


def image_size(data):
    """(width, height) for a PNG or JPEG blob."""
    if data.startswith(PNG_SIG):
        width, height = struct.unpack(">II", data[16:24])
        return width, height
    if data[:2] == b"\xff\xd8":
        pos = 2
        while pos + 9 < len(data):
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height, width = struct.unpack(">HH", data[pos + 5:pos + 9])
                return width, height
            (length,) = struct.unpack(">H", data[pos + 2:pos + 4])
            pos += 2 + length
        raise ValueError("could not read JPEG size")
    raise ValueError("only PNG and JPEG images are supported")


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter(raw, width, height, channels):
    stride = width * channels
    out = bytearray(height * stride)
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        ftype = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if ftype == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                up_left = prev[i - channels] if i >= channels else 0
                line[i] = (line[i] + _paeth(left, prev[i], up_left)) & 0xFF
        elif ftype != 0:
            raise ValueError("unsupported PNG filter type %d" % ftype)
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out, stride


def _chunk(ctype, body):
    return (struct.pack(">I", len(body)) + ctype + body
            + struct.pack(">I", zlib.crc32(ctype + body) & 0xFFFFFFFF))


def crop_png(data, box):
    """Crop ``box`` = [x0, y0, x1, y1] out of a PNG and return PNG bytes."""
    ihdr = None
    idat = []
    palette = b""
    for ctype, body in _png_chunks(data):
        if ctype == b"IHDR":
            ihdr = body
        elif ctype == b"IDAT":
            idat.append(body)
        elif ctype == b"PLTE":
            palette = body
    if ihdr is None or not idat:
        raise ValueError("PNG has no IHDR/IDAT")
    width, height, depth, color_type, _comp, _filt, interlace = struct.unpack(">IIBBBBB", ihdr)
    if depth != 8 or interlace != 0:
        raise ValueError("only 8-bit non-interlaced PNG is supported (got depth %d)" % depth)
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if not channels:
        raise ValueError("unsupported PNG color type %d" % color_type)
    raw = zlib.decompress(b"".join(idat))
    pixels, stride = _unfilter(raw, width, height, channels)

    x0, y0, x1, y1 = [int(v) for v in box]
    x0 = max(0, min(x0, width - 1))
    y0 = max(0, min(y0, height - 1))
    x1 = max(x0 + 1, min(x1, width))
    y1 = max(y0 + 1, min(y1, height))
    new_w, new_h = x1 - x0, y1 - y0

    rows = bytearray()
    for y in range(y0, y1):
        start = y * stride + x0 * channels
        rows += b"\x00" + pixels[start:start + new_w * channels]

    ihdr_out = struct.pack(">IIBBBBB", new_w, new_h, 8, color_type, 0, 0, 0)
    chunks = [PNG_SIG, _chunk(b"IHDR", ihdr_out)]
    if palette:
        chunks.append(_chunk(b"PLTE", palette))
    chunks.append(_chunk(b"IDAT", zlib.compress(bytes(rows), 6)))
    chunks.append(_chunk(b"IEND", b""))
    return b"".join(chunks)


def structure_questions(blocks, use_llm=True, llm_base=None, llm_key=None,
                        llm_model=None):
    """OCR blocks -> (title, questions). Shared by the CLI and the web API."""
    title, questions = "", []
    if use_llm:
        try:
            title, questions = structure_with_llm(
                blocks, base_url=llm_base, api_key=llm_key, model=llm_model)
        except (ValueError, KeyError, IndexError):
            title, questions = "", []
    if not questions:
        title, questions = structure_blocks(blocks)
    # The chat model tends to drop the answer key, so fill it deterministically.
    apply_answer_key(blocks, questions)
    return title, questions


def crop_figures(data, width, height, questions, figures_dir=None):
    """Crop every question figure out of the page image -> (files, figures)."""
    files = {}
    figures = {}
    for q in questions:
        if not q["figures"]:
            continue
        box = figure_box(q["figures"][0], width, height)
        if not box:
            continue
        name = "q%02d.png" % q["n"]
        try:
            blob = crop_png(data, box)
        except ValueError:
            continue
        files[name] = blob
        figures[q["n"]] = {
            "src": "%s/%s" % (figures_dir or "figures", name),
            "width": box[2] - box[0],
            "height": box[3] - box[1],
            "sha256": hashlib.sha256(blob).hexdigest(),
        }
    return files, figures


def import_blocks(data, width, height, blocks, paper_id="photo_1",
                  figures_dir=None, page_ref=None, use_llm=True, llm_base=None,
                  llm_key=None, llm_model=None):
    """Already-OCR'd blocks -> (paper dict, figure files {name: bytes})."""
    title, questions = structure_questions(
        blocks, use_llm=use_llm, llm_base=llm_base, llm_key=llm_key,
        llm_model=llm_model)
    files, figures = crop_figures(data, width, height, questions, figures_dir)
    return build_paper(title, questions, paper_id=paper_id, page_ref=page_ref,
                       figures=figures), files


def import_photo(data, width, height, paper_id="photo_1", base_url=None, model=None,
                 figures_dir=None, page_ref=None, use_llm=True, llm_base=None,
                 llm_key=None, llm_model=None):
    """Full pipeline: image bytes -> (paper dict, figure files {name: bytes}).

    The OCR blocks are structured by the small chat model by default; pass
    ``use_llm=False`` to fall back to the pure regex structurer.
    """
    raw = ocr_image(data, base_url=base_url, model=model)
    blocks = parse_ocr_text(raw)
    return import_blocks(data, width, height, blocks, paper_id=paper_id,
                         figures_dir=figures_dir, page_ref=page_ref,
                         use_llm=use_llm, llm_base=llm_base, llm_key=llm_key,
                         llm_model=llm_model)
