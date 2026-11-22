"""Scan files, directories and stdin for invisible Unicode."""
import dataclasses
import os
import re
import shutil
import sys
import tempfile
from typing import Iterator, NamedTuple

from unseen.rules import Finding, find, kind_for

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}
IGNORE_MARKER = "unseen: ignore"
# Binary-looking files with these extensions are only counted; other binary files get a warning.
BINARY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".pdf", ".zip", ".gz", ".tgz", ".xz",
               ".bz2", ".7z", ".jar", ".whl", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".mov",
               ".wav", ".ogg", ".so", ".dylib", ".dll", ".exe", ".class", ".pyc", ".o", ".a", ".bin"}
EOL = re.compile("[\r\n]")


class Result(NamedTuple):
    findings: list[Finding]
    files: int
    ignored: int
    errors: list[str]
    fixed: list[str]
    binary: int = 0
    links: int = 0


def _raise(exc: OSError):
    raise exc


def iter_files(paths: list[str]) -> Iterator[str]:
    """Expand directories (sorted, SKIP_DIRS pruned); pass files, symlinks and '-' through.

    Symlinks are yielded, never followed, so scan() can count and skip them.
    """
    for path in paths:
        if path == "-" or os.path.islink(os.path.normpath(path)) or not os.path.isdir(path):
            if path != "-" and not os.path.lexists(path):
                raise FileNotFoundError(2, "No such file or directory", path)
            yield path
            continue
        for root, dirs, files in os.walk(path, onerror=_raise):
            links = [x for x in dirs if os.path.islink(os.path.join(root, x))]
            dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and x not in links)
            for name in sorted(files + links):
                full = os.path.normpath(os.path.join(root, name))
                if os.path.islink(full) or os.path.isfile(full):  # skips sockets, FIFOs
                    yield full


BOMS = ((b"\xff\xfe\x00\x00", "utf-32-le"), (b"\x00\x00\xfe\xff", "utf-32-be"),
        (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"))
LOUD = re.compile("[\U000E0000-\U000E007F\u202a-\u202e\u2066-\u2069]")


def decode(data: bytes) -> tuple[str, str] | None:
    """(text, codec) that round-trips the bytes; None only for binary data with no tag or bidi characters.

    The BOM stays in the text as U+FEFF at offset 0 (exempt there), so writing back keeps it.
    Undecodable bytes become surrogate escapes, so a stray Latin-1 byte cannot hide a whole file.
    """
    for bom, codec in BOMS:
        if data.startswith(bom):
            try:
                return data.decode(codec), codec
            except UnicodeDecodeError:
                break
    text = data.decode("utf-8", "surrogateescape")
    head = data[:8192]
    # ponytail: NUL and invalid-byte ratios of the first 8 KB; use a magic-number check if real files misfire
    escaped = sum(1 for c in text[:8192] if "\udc80" <= c <= "\udcff")
    if (head.count(0) * 10 > len(head) or escaped * 3 > len(head)) and not LOUD.search(text):
        return None
    return text, "utf-8"


def read_text(path: str) -> tuple[str, str] | None:
    """decode() of a file, or of stdin for '-'."""
    if path == "-":
        return decode(sys.stdin.buffer.read())
    with open(path, "rb") as f:
        return decode(f.read())


def scan_text(text: str, path: str, strict: bool = False,
              allow: frozenset[int] = frozenset()) -> tuple[list[Finding], int]:
    """Findings for one text, minus those the ignore marker silences (returned as a count).

    The marker never silences a failing tag or bidi finding: those are the payloads it would hide.
    A line ends at LF or CR, so a CR-only file is not one long line.
    """
    kept, ignored = [], 0
    for f in find(text, kind_for(path), strict, allow):
        lo = max(text.rfind("\n", 0, f.start), text.rfind("\r", 0, f.start)) + 1
        eol = EOL.search(text, f.end)
        silenced = IGNORE_MARKER in text[lo:eol.start() if eol else len(text)]
        if silenced and not (f.level == "fail" and f.category in ("tag", "bidi")):
            ignored += 1
        else:
            kept.append(dataclasses.replace(f, path=path))
    return kept, ignored


def fix_text(text: str, findings: list[Finding]) -> str:
    """Text with every failing run removed; homoglyph letters are never deleted."""
    out, pos = [], 0
    for f in sorted(findings, key=lambda f: f.start):
        if f.level == "fail" and f.category != "homoglyph" and f.start >= pos:
            out.append(text[pos:f.start])
            pos = f.end
    out.append(text[pos:])
    return "".join(out)


def _write_atomic(path: str, text: str, codec: str) -> None:
    """Replace the file a path (or symlink) points to, keeping its mode."""
    target = os.path.realpath(path)
    tmp = tempfile.NamedTemporaryFile(dir=os.path.dirname(target), prefix=".unseen-", delete=False)
    try:
        with tmp:
            tmp.write(text.encode(codec, "surrogateescape"))
        shutil.copymode(target, tmp.name)
        os.replace(tmp.name, target)
    except BaseException:
        os.unlink(tmp.name)
        raise


def scan(paths: list[str], strict: bool = False, allow: frozenset[int] = frozenset(), fix: bool = False) -> Result:
    findings, errors, fixed, files, ignored, binary, links = [], [], [], 0, 0, 0, 0
    for top in paths:
        try:
            for path in iter_files([top]):
                if path != "-" and os.path.islink(os.path.normpath(path)):
                    links += 1  # never followed: the target is scanned on its own if it is in the tree
                    continue
                name = "<stdin>" if path == "-" else path
                try:
                    decoded = read_text(path)
                except OSError as exc:
                    errors.append(f"unseen: cannot read {path}: {exc.strerror or exc}")
                    continue
                if decoded is None and os.path.splitext(path)[1].lower() in BINARY_EXTS:
                    binary += 1
                    continue
                files += 1
                if decoded is None:
                    findings.append(Finding(1, 1, 0, 0, 0, "binary file, not scanned", "skipped",
                                            "fail" if strict else "warn", path=name))
                    continue
                text, codec = decoded
                fs, n = scan_text(text, name, strict, allow)
                findings += fs
                ignored += n
                new = fix_text(text, fs) if fix and path != "-" else text
                if new != text:
                    try:
                        _write_atomic(path, new, codec)
                        fixed.append(path)
                    except OSError as exc:
                        errors.append(f"unseen: cannot fix {path}: {exc.strerror or exc}")
        except OSError as exc:
            errors.append(f"unseen: cannot read {exc.filename or top}: {exc.strerror or exc}")
    return Result(findings, files, ignored, errors, fixed, binary, links)
