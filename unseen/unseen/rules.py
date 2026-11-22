"""Classify invisible and deceptive Unicode and apply the default fail/warn policy."""
import bisect
import itertools
import os
import re
import unicodedata
from dataclasses import dataclass

from unseen.tags import decode_tags, is_rgi_flag


@dataclass(frozen=True)
class Finding:
    line: int
    col: int
    start: int
    end: int
    cp: int
    name: str
    category: str
    level: str
    hidden: str = ""
    path: str = ""


PROSE_EXTS = {".md", ".markdown", ".txt", ".rst", ".html", ".htm", ".adoc"}
ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF}
BIDI = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A))
OTHER = {"Cf": "format", "Co": "private-use", "Cn": "unassigned"}
# Blank-looking letters and marks that pass as identifiers or hide inside words (Hangul fillers, CGJ,
# Mongolian variation selectors and vowel separator, braille blank).
FILLERS = {0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800} | set(range(0x180B, 0x1810))
JOINING_SCRIPTS = {"ARABIC", "SYRIAC", "NKO", "MONGOLIAN", "DEVANAGARI", "BENGALI", "GURMUKHI", "GUJARATI",
                   "ORIYA", "TAMIL", "TELUGU", "KANNADA", "MALAYALAM", "SINHALA"}
EMOJI_VS_BASES = set(map(ord, "#*0123456789")) | {0xA9, 0xAE, 0x203C, 0x2049, 0x2122, 0x2139, 0x24C2, 0x3030,
                                                   0x303D, 0x3297, 0x3299}
SPACELESS_SCRIPTS = {"THAI", "LAO", "KHMER", "MYANMAR"}
# ponytail: Extended_Pictographic below U+1F000, by hand (2600-27BF taken whole); embed emoji-data.txt if it misfires
EMOJI_BMP = (EMOJI_VS_BASES - set(map(ord, "#*0123456789"))) | {0xFE0F, 0x20E3} | {
    cp for lo, hi in ((0x2194, 0x2199), (0x21A9, 0x21AA), (0x231A, 0x231B), (0x2328, 0x2328), (0x2388, 0x2388),
                      (0x23CF, 0x23CF), (0x23E9, 0x23F3), (0x23F8, 0x23FA), (0x25AA, 0x25AB), (0x25B6, 0x25B6),
                      (0x25C0, 0x25C0), (0x25FB, 0x25FE), (0x2600, 0x27BF), (0x2934, 0x2935), (0x2B05, 0x2B07),
                      (0x2B1B, 0x2B1C), (0x2B50, 0x2B50), (0x2B55, 0x2B55))
    for cp in range(lo, hi + 1)}
TEXT_VS_SCRIPTS = {"CJK", "MONGOLIAN", "MYANMAR", "PHAGS-PA"}
NON_ASCII = re.compile(r"[^\x00-\x7f]+")
WORD = re.compile(r"\w+")


def kind_for(path: str) -> str:
    """'prose' for documentation file types, else 'code' (the stricter side)."""
    return "prose" if os.path.splitext(path)[1].lower() in PROSE_EXTS else "code"


def _script(c: str) -> str:
    return unicodedata.name(c, "").split(" ", 1)[0]


def _is_emoji(c: str) -> bool:
    cp = ord(c) if c else -1
    return 0x1F000 <= cp <= 0x1FAFF or cp in EMOJI_BMP


def _category(cp: int) -> str | None:
    if 0xE0000 <= cp <= 0xE007F:
        return "tag"
    if cp in ZERO_WIDTH:
        return "zero-width"
    if cp in BIDI:
        return "bidi"
    if 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF:
        return "variation-selector"
    if cp in FILLERS:
        return "filler"
    return OTHER.get(unicodedata.category(chr(cp)))


def _vs_ok(base: str, run: str) -> bool:
    # ponytail: range heuristic instead of StandardizedVariants.txt; embed the table if false positives are reported
    if len(run) != 1 or not base:
        return False
    cp, b = ord(run), ord(base)
    if cp >= 0xE0100:
        return False
    if cp >= 0xFE0E:
        return _is_emoji(base) or b in EMOJI_VS_BASES
    return (_script(base) in TEXT_VS_SCRIPTS or 0x2200 <= b <= 0x22FF or 0x2A00 <= b <= 0x2AFF
            or (base, run) == ("0", "\ufe00"))


def _level(category: str, run: str, prev: str, nxt: str, kind: str) -> str | None:
    """'fail', 'warn', or None when the run is a legitimate use."""
    if category == "tag":
        return None if is_rgi_flag(prev, run) else "fail"
    if category == "zero-width":
        if run in ("\u200c", "\u200d") and (
                _is_emoji(prev) and _is_emoji(nxt)
                or prev and nxt and _script(prev) in JOINING_SCRIPTS and _script(nxt) in JOINING_SCRIPTS):
            return None
        if run == "\u200b" and prev and nxt and _script(prev) in SPACELESS_SCRIPTS and _script(nxt) == _script(prev):
            return None  # word break in a script written without spaces
        return "fail"
    if category == "bidi":
        return "fail" if kind == "code" else "warn"
    if category == "variation-selector":
        return None if _vs_ok(prev, run) else "fail"
    if category == "filler":
        if kind == "code":
            return "fail"
        return None if not run.strip("\u2800") else "warn"  # braille blank is a normal space in braille prose
    if category == "format":
        return "fail" if kind == "code" or len(run) > 1 else "warn"
    return "warn"


def find(text: str, kind: str = "code", strict: bool = False, allow: frozenset[int] = frozenset()) -> list[Finding]:
    """All findings in text, sorted by start offset."""
    if text.isascii():
        return []
    line_starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def make(start, end, cp, category, level, hidden=""):
        n = bisect.bisect_right(line_starts, start)
        if strict:
            level = "fail"
        return Finding(n, start - line_starts[n - 1] + 1, start, end, cp, unicodedata.name(chr(cp), "<unnamed>"),
                       category, level, hidden)

    def cat_at(i):
        cp = ord(text[i])
        if cp in allow or (i == 0 and cp == 0xFEFF):
            return None
        return _category(cp)

    out = []
    for m in NON_ASCII.finditer(text):
        i = m.start()
        for category, group in itertools.groupby(range(m.start(), m.end()), cat_at):
            n = sum(1 for _ in group)
            start, i = i, i + n
            if category is None:
                continue
            run = text[start:i]
            level = _level(category, run, text[start - 1] if start else "", text[i:i + 1], kind)
            if level:
                out.append(make(start, i, ord(run[0]), category, level,
                                decode_tags(run) if category == "tag" else ""))

    for w in WORD.finditer(text):
        word = w.group()
        if word.isascii():
            continue
        scripts = [_script(c) for c in word if c.isalpha()]
        if "LATIN" in scripts:
            for j, c in enumerate(word):
                if c.isalpha() and _script(c) in ("CYRILLIC", "GREEK") and ord(c) not in allow:
                    out.append(make(w.start() + j, w.start() + j + 1, ord(c), "homoglyph", "warn"))
                    break
    return sorted(out, key=lambda f: f.start)
