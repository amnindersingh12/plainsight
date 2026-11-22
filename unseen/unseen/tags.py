"""Unicode tag characters (U+E0000-U+E007F): encode, decode, and the emoji-flag exception."""
import re

TAG_RUN = re.compile("[\U000E0000-\U000E007F]+")
CANCEL_TAG = "\U000E007F"


def hide(text: str) -> str:
    """Encode printable ASCII as invisible tag characters."""
    if not all(" " <= c <= "~" for c in text):
        raise ValueError("hide only encodes printable ASCII (0x20-0x7E)")
    return "".join(chr(0xE0000 + ord(c)) for c in text)


def decode_tags(s: str) -> str:
    """Map U+E0020-U+E007E back to ASCII, dropping everything else."""
    return "".join(chr(ord(c) - 0xE0000) for c in s if 0xE0020 <= ord(c) <= 0xE007E)


RGI_FLAG_TAGS = frozenset(hide(c) + CANCEL_TAG for c in ("gbeng", "gbsct", "gbwls"))


def is_rgi_flag(prev: str, run: str) -> bool:
    """True for the three RGI subdivision flags (England, Scotland, Wales)."""
    return prev == "\U0001F3F4" and run in RGI_FLAG_TAGS


def reveal(text: str) -> list[str]:
    """Decoded message of every tag run that is not an RGI flag."""
    out = []
    for m in TAG_RUN.finditer(text):
        prev = text[m.start() - 1] if m.start() else ""
        msg = decode_tags(m.group())
        if msg and not is_rgi_flag(prev, m.group()):
            out.append(msg)
    return out
