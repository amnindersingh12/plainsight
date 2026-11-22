"""Optional external tools, run only when installed. Their output files are read, never executed."""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .core import (MAX_EXTRACT_BYTES, MAX_TOOL_OUTPUT, SCORE_FILE, SCORE_FLAG, SCORE_INFO, SCORE_NOTE, TOOL_TIMEOUT,
                   Finding, clean, find_flags)

STEG_KINDS = ("jpeg", "bmp", "wav")


def _call(args: list[str], data: bytes | None = None) -> str:
    """stdout and stderr together; stdin is `data` or empty."""
    stdin = {"input": data} if data is not None else {"stdin": subprocess.DEVNULL}
    r = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=TOOL_TIMEOUT, check=False,
                       **stdin)
    return r.stdout.decode(errors="replace")[:MAX_TOOL_OUTPUT]


def _flags(text: str, flag_re: re.Pattern[str]) -> list[str]:
    return find_flags(text.encode("latin-1", "replace"), flag_re)


def _read_capped(path: Path) -> tuple[int, bytes] | None:
    if not path.is_file():
        return None
    with open(path, "rb") as fh:
        return os.fstat(fh.fileno()).st_size, fh.read(MAX_EXTRACT_BYTES)


def _extracted(tool: str, title: str, out: Path, flag_re: re.Pattern[str]) -> list[Finding]:
    got = _read_capped(out)
    if got is None:
        return []
    size, blob = got
    flags = find_flags(blob, flag_re)
    return ([Finding(tool, clean(f"{tool}: {flag}"), SCORE_FLAG) for flag in flags]
            + [Finding(tool, clean(f"{title}, extracted {size} bytes"), SCORE_FILE, blob=blob, name=out.name)])


def _exiftool(data: bytes, flag_re) -> list[Finding]:
    text = _call(["exiftool", "-a", "-u", "-g1", "-"], data)  # stdin, not a file name: CVE-2022-23935 (< 12.38)
    flags = _flags(text, flag_re)
    if flags:
        return [Finding("exiftool", clean(f"exiftool: {flag}"), SCORE_FLAG, text) for flag in flags]
    tags = sum(1 for line in text.splitlines() if " : " in line)
    return [Finding("exiftool", f"exiftool: {tags} tags (see report)", SCORE_INFO, text)]


def _files(d: Path) -> set[str]:
    return {os.path.join(root, f) for root, _, files in os.walk(d) for f in files}  # os.walk skips symlinked dirs


def _binwalk(p: str, out_dir: Path) -> list[Finding]:
    m = re.search(r"(?i)binwalk v?(\d+)\.(\d+)\.(\d+)", _call(["binwalk", "--help"]))
    if not m or tuple(map(int, m.groups())) < (2, 3, 4):  # older -e has a path traversal: CVE-2022-4510
        why = f"version {'.'.join(m.groups())}" if m else "unknown version"
        return [Finding("external", f"binwalk -e skipped: {why}, need >= 2.3.4 (CVE-2022-4510)", SCORE_NOTE)]
    dest = out_dir / "binwalk"
    before = _files(dest)
    text = _call(["binwalk", "-e", "-C", str(dest), p])
    n = len(_files(dest) - before)  # this run only; a reused -o dir keeps earlier extractions
    return [Finding("binwalk", f"binwalk: extracted {n} files to binwalk/", SCORE_INFO, text)]


def _steghide(p: str, flag_re) -> list[Finding]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "steghide.out"
        _call(["steghide", "extract", "-sf", p, "-p", "", "-xf", str(out), "-f"])
        return _extracted("steghide", "steghide: empty passphrase", out, flag_re)


def _stegseek(p: str, wordlist: Path, flag_re) -> list[Finding]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "stegseek.out"
        text = _call(["stegseek", p, str(wordlist.resolve()), str(out)])
        m = re.search(r'Found passphrase: "(.*)"', text)
        return _extracted("stegseek", f'stegseek: passphrase "{m.group(1) if m else "?"}"', out, flag_re)


def run_external(path: Path, data: bytes, kind: str, out_dir: Path | None, wordlist: Path | None, flag_re) -> list[Finding]:
    p = str(path.resolve())  # absolute, so a file named "-x" cannot become an option
    steg = kind in STEG_KINDS
    tools = [("exiftool", True, lambda: _exiftool(data, flag_re)),
             ("binwalk", True, lambda: _binwalk(p, out_dir)),
             ("steghide", steg, lambda: _steghide(p, flag_re)),
             ("stegseek", steg and wordlist is not None, lambda: _stegseek(p, wordlist, flag_re))]
    out = []
    for tool, applies, fn in tools:
        if not applies:
            continue
        if shutil.which(tool) is None:
            out.append(Finding("external", f"{tool} not installed, skipped", SCORE_NOTE))
        elif tool == "binwalk" and out_dir is None:
            out.append(Finding("external", "binwalk -e skipped: needs -o", SCORE_NOTE))
        else:
            try:
                out += fn()
            except subprocess.TimeoutExpired:
                out.append(Finding("external", f"{tool} timed out after {TOOL_TIMEOUT}s", SCORE_NOTE))
            except OSError as exc:
                out.append(Finding("external", clean(f"{tool} failed: {exc}"), SCORE_NOTE))
    return out
