"""Wrap bare LaTeX runs (not inside $...$) into $...$ so KaTeX renders them.

Banks come from heterogeneous pipelines; some store raw TeX fragments without
$ delimiters, e.g. "x^{2024}+y^2=2y" or "\\frac{3}{8}". This pass clusters
"mathy" tokens (commands, scripts, numbers, single letters, operators) joined
by whitespace and wraps each cluster that contains \\, ^, or _.

Conservative by design: a cluster whose text (with brace contents and command
names removed) still contains a run of 2+ letters is treated as English prose
and left alone, so normal sentences are never wrapped.

Also normalises \\(...\\) and \\[...\\] delimiters to $...$ / $$...$$ (only
outside existing math spans), since the frontend KaTeX auto-render only
recognises $ delimiters.
"""
import re

# existing math spans are left untouched (escaped \$ excluded)
_PROTECT = re.compile(r'((?<!\\)\$\$[^$]*\$\$|(?<!\\)\$[^$]+(?<!\\)\$)')

_BRACE = r'\{(?:[^{}]|\{[^{}]*\})*\}'  # {..} with one level of nesting

_UNIT = re.compile(r"""
    \\[a-zA-Z]+(?:[ \t]*""" + _BRACE + r"""){0,3}                 # \cmd + up to 3 {..} groups
  | \\[%&$#_{}()\[\].,;:!'"~<>|*\\-]                               # single-char commands (incl \)
  | [A-Za-z0-9]+(?:\.\d+)?[_\^](?:\{[^{}]*\}|[0-9A-Za-z]+)         # x^2, 2^{3/8}, a_{n}
  | [_\^](?:\{[^{}]*\}|[0-9A-Za-z]+)                               # bare ^{...} or _{...}
  | [_\^]                                                             # bare ^ or _ (60^\circ)
  | [0-9]+(?:\.[0-9]+)?                                           # plain numbers
  | [A-Za-z]                                                      # single letters (16x\cos)
  | [+\-*/=<>|&%]                                                 # operators
  | [(),;:]                                                       # glue punctuation
""", re.X)

# space-anchored ENGLISH FUNCTION WORDS outside braces/commands => prose.
# Dictionary-based (not case-based): math identifiers like ab, rc, xyz must
# pass, while "the", "for", "gives" etc. mark real sentences.
_PROSE_WORDS = (
    'the|and|for|with|when|then|thus|hence|gives|given|since|where|which|'
    'that|this|these|those|there|their|are|was|were|is|be|been|being|'
    'have|has|had|having|will|would|can|could|should|shall|may|might|'
    'must|not|nor|but|if|else|of|to|into|onto|upon|from|by|on|at|in|'
    'per|via|as|so|such|also|note|notes|we|you|they|he|she|it|its|our|'
    'your|his|her|them|us|him|one|ones|now|first|second|third|finally|'
    'remain|remains|left|leaving|ways|value|answer|equals|plus|minus|times|'
    'over|get|gets|find|suppose|let|therefore|because|each|all|both|every|'
    'some|exactly|respectively|clearly|obviously|similarly|instead|otherwise|'
    'indeed|next|last|least|largest|smallest|maximum|minimum|than|between|'
    'among|only|even|odd|prime|divisible|integer|integers|number|equal|'
    'less|greater|smaller|larger|follows|follow|holds|hold|true|positive|'
    'negative|nonnegative|distinct|unique|possible|impossible|probability|'
    'random|expected|respect|desired|solution|solutions|rate|ratio|unit|'
    'units|speed|distance|time|mass|length|area|volume|angle|side|sides|'
    'point|points|line|lines|circle|triangle|square|figure|segment|segments'
)
_ENGLISH_WORD = re.compile(
    r'(?:^|\s)(?:' + _PROSE_WORDS + r')(?=[\s,.;:!?]|$)', re.I)
_PROSE_SET = frozenset(_PROSE_WORDS.split('|'))

_EDGE_PUNCT = ',;:!?'


def _escape_unpaired_dollars(s):
    """Backslash-escape trailing unpaired $ / $$ so protect-split can't mispair."""
    for delim in ('$$', '$'):
        n = 0
        last = -1
        i = 0
        while True:
            i = s.find(delim, i)
            if i < 0:
                break
            if s[i - 1] != '\\':
                n += 1
                last = i
            i += len(delim)
        if n % 2 == 1:
            s = s[:last] + '\\' + s[last:]
    return s


def _valid_span(p):
    """A $...$ span is invalid if it looks like prose (mispaired dollars):
    long and containing space-anchored English words outside braces/commands.
    KaTeX would show it raw, so we unwrap it and treat contents as plain text.
    """
    inner = p[2:-2] if p.startswith('$$') else p[1:-1]
    if '\n\n' in inner:
        return False  # paragraphs are never inside math
    if re.search(r'[_\^][_\^]', inner):
        return False  # corrupted scripts ($P_^=...$) would crash KaTeX
    if re.search(r'\\end\{(?:align|alignat|eqnarray|gather|multline|equation)\*?\}', inner):
        return False  # display-env closer stranded inside an inline span
    if p.startswith('$') and not p.startswith('$$') and re.search(
            r'\\begin\{(?:align|alignat|eqnarray|gather|multline|equation)\*?\}', inner):
        return False  # display envs are invalid inside inline math; unwrap so
        # _wrap_envs can re-wrap the pair in $$..$$
    if '&' in inner and not re.search(r'\\begin\{aligned', inner):
        return False  # align fragment ($r &= ...\$) is not valid inline math
    if re.search(r'\\\\\s*$', inner) and not re.search(r'\\begin\{', inner):
        return False  # trailing row-break outside an env is not valid inline
    if len(inner) <= 100:
        return True
    return not _ENGLISH_WORD.search(_clean_cluster_core(inner))


def _strip_prose_macros(seg):
    """Unwrap text-emphasis macros outside math spans: \\emph{..} -> ... etc."""
    for cmd in ('emph', 'textit', 'textbf', 'textrm'):
        seg = re.sub(r'\\' + cmd + r'\{([^{}]*)\}', r'\1', seg)
    return seg


_KNOWN_MACROS = {'ZZ': '\\mathbb{Z}', 'RR': '\\mathbb{R}', 'FF': '\\mathbb{F}',
                 'CC': '\\mathbb{C}', 'QQ': '\\mathbb{Q}'}  # Putnam number sets


_TEXT_MACROS = {'textdollar': r'\\$', 'textcent': r'\\text{\\textcent{} }',
                'textunderscore': '_', 'textasciitilde': '\\sim'}


def _expand_custom_macros(seg):
    """Expand nonstandard all-caps macros the banks use but KaTeX doesn't know:
    Putnam number sets (\\ZZ -> \\mathbb{Z}) and PUMaC named angles
    (\\IBM -> \\angle IBM; two-letter \\BM -> segment \\overline{BM})."""
    for k, v in _TEXT_MACROS.items():
        seg = seg.replace('\\' + k, v)
    def _sub(m):
        name = m.group(1)
        if name in _KNOWN_MACROS:
            return _KNOWN_MACROS[name]
        if len(name) >= 3:
            return '\\angle ' + name
        return '\\overline{' + name + '}'
    return re.sub(r'\\([A-Z]{2,})(?![a-zA-Z])', _sub, seg)


def _clean_cluster_core(text):
    core = re.sub(_BRACE, '', text)          # drop brace contents
    core = re.sub(r'\\[a-zA-Z]+', '', core)  # drop command names
    return core


_PROSE_SPLIT = re.compile(
    r'[{}]|(?:^|\s)(' + _PROSE_WORDS + r')(?![a-zA-Z])', re.I)


def _split_prose(seg, start, end):
    """Yield (st, en) sub-ranges of seg[start:end] with prose words removed.

    Only words at brace-depth 0 are cut, so \text{if } is never split.
    """
    text = seg[start:end]
    depth = 0
    last = 0
    i = 0
    for m in _PROSE_SPLIT.finditer(text):
        tok = m.group(0)
        if tok == '{':
            depth += 1
            continue
        if tok == '}':
            depth = max(0, depth - 1)
            continue
        if depth > 0 or m.group(1) is None:
            continue
        if last < m.start():
            yield start + last, start + m.start()
        last = m.end()
        i += 1
    if last < len(text):
        yield start + last, start + len(text)


def _emit_piece(seg, start, end, out):
    while start < end and seg[start] in ' \t':
        start += 1
    while end > start and seg[end - 1] in ' \t':
        end -= 1
    text = seg[start:end]
    has_env = '\\begin{' in text
    if not has_env and len(text) > 1000:
        return
    if len(text) > 2000:
        return
    if not any(c in text for c in '\\^_'):
        return
    if _ENGLISH_WORD.search(_clean_cluster_core(text)):
        return
    if '&' in text:
        if '\\begin{' in text:
            pass
        else:
            text = text.replace('&', '')  # align tab char is invalid inline
            end -= 0
    text = re.sub(r'\\\\[ \t]*$', '', text)
    if not text.strip():
        return
    end = start + len(text)  # splice by reconstructed length
    # trim edge punctuation out of the math span
    while text and text[-1] in _EDGE_PUNCT:
        end -= 1
        text = text[:-1]
    while text and text[0] in _EDGE_PUNCT:
        start += 1
        text = text[1:]
    if not text:
        return
    out.append((start, end, text))


def _wrap_segment(seg):
    seg = _ENV_TOK.sub('', seg)  # unmatched \begin/\end leftovers crash KaTeX
    clusters = []
    last_end = None
    for m in _UNIT.finditer(seg):
        if last_end is not None:
            gap = seg[last_end:m.start()]
            # only spaces/tabs bridge tokens; newlines or other text break
            # the cluster (prose line ends must not glue into math)
            if gap.strip() or '\n' in gap:
                last_end = None
        if last_end is None:
            clusters.append([m.start(), m.end()])
        else:
            clusters[-1][1] = m.end()
        last_end = m.end()
    out = []
    for start, end in clusters:
        text = seg[start:end]
        if not text or re.search(r'[_\^][_\^]', text):
            continue  # corrupted scripts (P_^=) would crash KaTeX
        # A cluster may glue prose in via single-letter tokens ("so x^{3/8}",
        # "angle is 60^\circ"); split it at prose words (brace-depth 0) and
        # wrap the math-only pieces.
        for st, en in _split_prose(seg, start, end):
            _emit_piece(seg, st, en, out)
    for start, end, text in reversed(out):
        delim = '$$' if ('\n' in text or '\\begin{' in text) else '$'
        seg = seg[:start] + delim + text + delim + seg[end:]
    return seg


def _convert_delims(seg):
    """\\(...\\) -> $...$, \\[...\\] -> $$...$$ inside a non-math segment."""
    seg = re.sub(r'\\\[(.+?)\\\]', r'$\1$', seg, flags=re.S)
    return seg


_ENV_NAMES = ('align*', 'eqnarray*', 'gather*', 'multline*', 'align', 'eqnarray',
              'gather', 'multline', 'aligned', 'split', 'alignedat', 'cases',
              'matrix', 'pmatrix', 'bmatrix', 'Bmatrix', 'vmatrix', 'Vmatrix',
              'smallmatrix', 'substack', 'subarray', 'array', 'gathered',
              'alignat*', 'alignat', 'equation*', 'equation', 'displaymath')
_ENV_TOK = re.compile(r'\\(begin|end)\{(' + '|'.join(_ENV_NAMES).replace('*', r'\*') + r')\}')


def _wrap_envs(seg):
    """Wrap \\begin{env}..\\end{env} blocks in $$..$$ (they are math by definition).

    Balance-aware single pass: pairs same-name begin/end via a stack, then
    splices outermost blocks back-to-front (nested spans are covered by the
    outer $$..$$ so they are skipped).
    """
    spans = []
    stack = []
    for m in _ENV_TOK.finditer(seg):
        kind, name = m.group(1), m.group(2)
        if kind == 'begin':
            stack.append((name, m.start()))
        else:
            for j in range(len(stack) - 1, -1, -1):
                if stack[j][0] == name:
                    spans.append((stack[j][1], m.end()))
                    del stack[j:]
                    break
    if not spans:
        return seg
    spans.sort()
    out, last = [], 0
    for st, en in spans:
        if st < last:
            continue  # nested inside an already-wrapped outer block
        out.append(seg[last:st])
        body = seg[st:en].replace('\\[', '').replace('\\]', '')
        out.append('$$' + body + '$$')
        last = en
    out.append(seg[last:])
    return ''.join(out)


_SCRIPT_BASE = re.compile(r'(^|[\s])([_\^])')


def _fix_scripts(p):
    """Inside a math span, a _ or ^ at the start or after whitespace has no
    base operand (OCR fraction debris like "_{\\omega I}") and crashes
    KaTeX; give it an empty base {}."""
    if not (p.startswith('$') and p.endswith('$')):
        return p
    if p.startswith('$$'):
        inner = p[2:-2]
    else:
        inner = p[1:-1]
    inner = _SCRIPT_BASE.sub(r'\1{}\2', inner)
    inner = re.sub(r'[_\^](?=$)', '', inner)  # dangling trailing script char
    return ('$$' if p.startswith('$$') else '$') + inner + ('$$' if p.startswith('$$') else '$')


def wrap_bare_math(s):
    if not s or ('\\' not in s and '^' not in s and '_' not in s):
        return s
    s = _expand_custom_macros(s)  # KaTeX-unknown macros would render raw anywhere
    s = re.sub(r'(?m)^\s_*TOC_*\s*$', '', s)  # wiki table-of-contents markers
    s = re.sub(r'(?mi)^\s*(?:_+|\!)?NOTOC_?\s*$', '', s)
    s = re.sub(r'(?m)^\s*_{3,}\s*$', '', s)  # decorative underscore rules
    s = re.sub(r'<asy>.*?</asy>', '', s, flags=re.S)  # diagram source code blocks
    # 1) normalise TeX delimiters (frontend KaTeX only recognises $)
    s = re.sub(r'\\\[(.+?)\\\]', r'$\1$', s, flags=re.S)
    s = re.sub(r'\\\((.+?)\\\)', r'$\1$', s, flags=re.S)
    # 2) an odd number of $ would make protect-split mispair spans
    s = _escape_unpaired_dollars(s)
    cleaned = []
    for p in _PROTECT.split(s):
        if not p:
            continue
        if p.startswith('$') and _valid_span(p):
            # stray TeX delimiters inside an existing math span are no-ops
            q = p.replace('\\[', '').replace('\\]', '')
            q = q.replace('\\(', '').replace('\\)', '')
            if q.startswith('$$'):
                # newlines inside display math break \left<newline>( ... )
                q = '$$' + q[2:-2].replace('\n', ' ') + '$$'
            cleaned.append(q)
        else:
            # invalid (prose) span: drop its $ delimiters, treat as plain text
            seg = p[2:-2] if p.startswith('$$') else p[1:-1] if p.startswith('$') else p
            seg = _strip_prose_macros(seg)
            seg = _wrap_envs(seg)
            cleaned.append(''.join(
                q if q.startswith('$') and _valid_span(q) else _wrap_segment(
                    q[2:-2] if q.startswith('$$') else q[1:-1] if q.startswith('$') else q)
                for q in _PROTECT.split(seg)))
    merged = ''.join(cleaned)
    # an inline span glued to a display span yields $$$ / $$$$ which breaks
    # pairing: $$$ -> "$ $$", $$$$ -> "$$ $$"
    merged = merged.replace('$$$$', '$$ $$').replace('$$$', '$ $$')
    while True:
        m2 = re.sub(r'(?<!\$)\$([^$]+)\$\$([^$]+)\$(?!\$)', r'$\1\2$', merged)
        if m2 == merged:
            break
        merged = m2
    # merging can glue fresh scripts back inside a span (r_{I}$ + ^{3} -> ...)
    merged = _PROTECT.sub(lambda m: _fix_scripts(m.group(0)), merged)
    return merged
