"""Extract text lines from BPhO PDFs with super/subscripts converted to LaTeX.

pdfplumber gives per-char size & position. Body text is 12pt; scripts are ~7pt.
Cluster BODY chars into lines by top; assign script chars to the nearest line by
baseline distance; within a line sort by x0. A script char whose baseline is
above the body baseline becomes ^{...}, below becomes _{...}.
"""
import re
import unicodedata

GREEK = {
    "𝛼": "\\alpha", "𝛽": "\\beta", "𝛾": "\\gamma", "𝛿": "\\delta",
    "𝜀": "\\varepsilon", "𝜃": "\\theta", "𝜆": "\\lambda", "𝜇": "\\mu",
    "𝜌": "\\rho", "𝜋": "\\pi", "𝜔": "\\omega", "𝜙": "\\phi", "𝜑": "\\varphi",
    "𝜂": "\\eta", "𝜉": "\\xi", "𝜏": "\\tau", "𝜅": "\\kappa", "𝜎": "\\sigma",
    "𝜈": "\\nu", "𝜒": "\\chi", "𝜓": "\\psi", "𝜁": "\\zeta",
    "𝛥": "\\Delta", "𝛴": "\\Sigma", "𝛺": "\\Omega", "𝛱": "\\Pi", "𝛤": "\\Gamma",
    "𝛬": "\\Lambda", "𝛯": "\\Xi", "𝛩": "\\Theta",
}
SPECIAL = {
    "ℎ": "h", "ℓ": "\\ell", "Ω": "\\Omega",
    "−": "-", "–": "-", "—": "---", "’": "'", "“": "``", "”": "''",
    "×": "\\times", "·": "\\cdot", "÷": "\\div",
    "≈": "\\approx", "≪": "\\ll", "≫": "\\gg", "≤": "\\le", "≥": "\\ge",
    "≠": "\\ne", "→": "\\to", "←": "\\leftarrow", "↔": "\\leftrightarrow",
    "∝": "\\propto", "°": "^\\circ", "◦": "^\\circ",
    "𝜕": "\\partial", "∇": "\\nabla", "∫": "\\int", "∑": "\\sum", "∏": "\\prod",
    "∞": "\\infty", "±": "\\pm", "∓": "\\mp",
}


def char_latex(ch):
    o = ord(ch)
    if 0x1D434 <= o <= 0x1D467:  # mathematical italic A-Z a-z
        if o <= 0x1D44D:
            return chr(o - 0x1D434 + ord('A'))
        return chr(o - 0x1D44E + ord('a'))
    if 0x1D6A8 <= o <= 0x1D7FF:  # mathematical greek/digits -> via name
        pass
    if ch in GREEK:
        return GREEK[ch]
    if ch in SPECIAL:
        return SPECIAL[ch]
    name = unicodedata.name(ch, '')
    m = None
    if 'SMALL LETTER' in name:
        m = name.split('SMALL LETTER ')[-1]
    elif 'CAPITAL LETTER' in name:
        m = name.split('CAPITAL LETTER ')[-1]
    if m:
        greek_names = {
            'ALPHA': '\\alpha', 'BETA': '\\beta', 'GAMMA': '\\gamma',
            'DELTA': '\\delta', 'EPSILON': '\\varepsilon', 'THETA': '\\theta',
            'LAMBDA': '\\lambda', 'MU': '\\mu', 'PI': '\\pi', 'RHO': '\\rho',
            'SIGMA': '\\sigma', 'OMEGA': '\\omega', 'PHI': '\\phi', 'TAU': '\\tau',
            'NU': '\\nu', 'CHI': '\\chi', 'PSI': '\\psi', 'ETA': '\\eta',
            'XI': '\\xi', 'ZETA': '\\zeta', 'KAPPA': '\\kappa', 'IOTA': '\\iota',
        }
        if m in greek_names:
            return greek_names[m]
        return m.title() if 'CAPITAL' in name else m.lower()
    return ch


def is_math_char(ch):
    o = ord(ch)
    if 0x1D434 <= o <= 0x1D467:
        return True
    if 0x1D6A8 <= o <= 0x1D7FF:
        return True
    return ch in GREEK or ch in SPECIAL


def _cluster_body_lines(chars):
    """Group body (large) chars into lines by top proximity."""
    body = [c for c in chars if c['size'] >= 9]
    body.sort(key=lambda c: c['top'])
    lines = []  # each: {'top': median_top, 'base': median_top+size, 'chars': [...]}
    for c in body:
        if lines and abs(c['top'] - lines[-1]['top']) <= 3.0:
            L = lines[-1]
            L['chars'].append(c)
            n = len(L['chars'])
            L['top'] = (L['top'] * (n - 1) + c['top']) / n
            L['base'] = (L['base'] * (n - 1) + (c['top'] + c['size'])) / n
        else:
            lines.append({'top': c['top'], 'base': c['top'] + c['size'],
                          'chars': [c]})
    # assign script chars to nearest line by baseline distance
    scripts = [c for c in chars if c['size'] < 9]
    for c in scripts:
        best, best_d = None, 1e9
        for L in lines:
            d = abs((c['top'] + c['size']) - L['base'])
            if d < best_d:
                best, best_d = L, d
        if best is not None and best_d <= 10.0:
            best['chars'].append(c)
    for L in lines:
        L['chars'].sort(key=lambda c: c['x0'])
    return lines


def line_to_latex(line):
    chars = line['chars']
    body = [c for c in chars if c['size'] >= 9] or chars
    med_size = sorted(c['size'] for c in body)[len(body) // 2]
    body_base = line['base']
    # some PDFs have no space glyphs; synthesize spaces from x-gaps instead
    synth_space = True
    out, script_buf, script_kind, math_buf = [], [], None, []
    prev_x1 = None

    def flush_script():
        nonlocal script_buf, script_kind
        if script_buf:
            content = "".join(script_buf).strip()
            if content:
                out.append(f"{script_kind}{{{content}}}")
            script_buf, script_kind = [], None

    def flush_math():
        nonlocal math_buf
        if math_buf:
            flush_script()
            out.append("$" + "".join(math_buf) + "$")
            math_buf = []

    for c in chars:
        ch = c['text']
        if synth_space and prev_x1 is not None:
            gap = c['x0'] - prev_x1
            if gap > 0.20 * med_size:
                flush_script()
                flush_math()
                out.append(' ')
        prev_x1 = c['x0'] + c.get('width', c['size'] * 0.5)
        if len(ch) > 1:
            # rare: pdfminer grouped several codepoints into one "char"
            flush_script()
            if c['size'] < med_size * 0.78:
                base = c['top'] + c['size']
                kind = '^' if base < body_base - 1.5 else '_'
                out.append(f"{kind}{{{''.join(char_latex(x) for x in ch)}}}")
            else:
                flush_math()
                out.append("".join(
                    char_latex(x) if is_math_char(x) else x for x in ch))
            continue
        if c['size'] < med_size * 0.78:
            base = c['top'] + c['size']
            kind = '^' if base < body_base - 1.5 else '_'
            if script_kind and script_kind != kind:
                flush_script()
            script_kind = kind
            script_buf.append(char_latex(ch))
        else:
            flush_script()
            if is_math_char(ch):
                math_buf.append(char_latex(ch))
            else:
                flush_math()
                out.append(ch)
    flush_script()
    flush_math()
    s = re.sub(r'\(cid:\d+\)', '', "".join(out))
    # move a script that x-sorted before its symbol: _{r}$F$ -> $F_{r}$
    s = re.sub(r'([\^_])\{([^{}]*)\}(\$\\?[A-Za-z]+\$)', r'\3\1{\2}', s)
    # merge a script right after a math span: $\ell$_{V} -> $\ell_{V}$
    s = re.sub(r'\$([^{}$]+)\$([\^_])\{([^{}]*)\}', r'$\1\2{\3}$', s)
    # wrap digit x 10^{n} powers: "4.1 x 10^{3}" -> "$4.1 \times 10^{3}$"
    s = re.sub(r'(\d+(?:\.\d+)?) x 10([\^_])\{([^{}]*)\}',
               r'$\1 \\times 10\2{\3}$', s)
    # wrap remaining bare scripted tokens: P_{p}, ms^{-1}, cm^{3} ...
    s = re.sub(r'(?<![\\A-Za-z$])([A-Za-zµΩℓ]+)([\^_])\{([^{}]*)\}',
               r'$\1\2{\3}$', s)
    # digits with scripts ("3^{2}", "10^{-3}"): -> $3^{2}$  (skip math spans)
    digit_pat = re.compile(r'(?<![\w$])((?:\d+\.?\d*)|(?:\d*\.\d+))([\^_])\{([^{}]*)\}')
    segs = re.split(r'(\$[^$]*\$)', s)
    s = "".join(seg if seg.startswith('$') else digit_pat.sub(r'$\1\2{\3}$', seg)
                for seg in segs)
    # merge adjacent math spans: $a$$b$ -> $ab$ (else KaTeX reads $$ as display)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'\$([^$]+)\$\$([^$]+)\$', r'$\1\2$', s)
    # unstick greek commands from following letters: \\pir -> \\pi r
    s = re.sub(
        r'\\(alpha|beta|gamma|delta|theta|lambda|mu|pi|rho|sigma|omega|phi|'
        r'vartheta|varphi|tau|nu|chi|psi|eta|xi|zeta|kappa|epsilon|times|'
        r'div|partial|approx)(?=[A-Za-z])', r'\\\1 ', s)
    return s


def page_text(page):
    lines = _cluster_body_lines(page.chars)
    texts = [line_to_latex(L).rstrip() for L in lines]
    return "\n".join(t for t in texts if t.strip())
