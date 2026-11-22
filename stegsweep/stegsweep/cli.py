"""stegsweep: run every steg check on one file, print a ranked summary, optionally write an HTML report."""
import argparse
import html
import re
import sys
from pathlib import Path

from .checks import (check_metadata, check_png_chunks, check_signatures, check_strings, check_trailing,
                     check_zip_members)
from .core import (DEFAULT_FLAG_FORMAT, MAX_INPUT_BYTES, MAX_SHOWN, SCORE_NOTE, Finding, clean, open_image, rank,
                   save_artifact, sniff)
from .external import run_external
from .lsb import save_bit_planes, sweep_image, sweep_wav

IMAGE_KINDS = ("png", "jpeg", "gif", "bmp", "tiff", "webp")
LOSSLESS_KINDS = ("png", "bmp", "gif", "tiff", "webp")  # JPEG LSBs are decoder noise


def _guard(name: str, fn, *args) -> list[Finding]:
    try:
        return fn(*args)
    except Exception as exc:  # untrusted input: a broken parser becomes a note, never a crash
        return [Finding("sweep", clean(f"{name} failed: {exc}"), SCORE_NOTE)]


def sweep(path: Path, data: bytes, flag_re, wordlist: Path | None,
          out_dir: Path | None) -> tuple[list[Finding], list[Path]]:
    """Ranked findings, plus the bit-plane images written this run (only with out_dir)."""
    kind = sniff(data)
    planes: list[Path] = []
    fs = _guard("strings", check_strings, data, flag_re) + _guard("signature", check_signatures, data)
    fs += _guard("zip", check_zip_members, data, flag_re)
    if kind in ("png", "jpeg"):
        fs += _guard("trailing", check_trailing, data)
    if kind == "png":
        fs += _guard("png-chunks", check_png_chunks, data)
    if kind in IMAGE_KINDS:
        fs += _guard("metadata", check_metadata, data, flag_re)
    if kind in LOSSLESS_KINDS:
        fs += _guard("lsb", lambda: sweep_image(open_image(data), flag_re))
    if kind == "wav":
        fs += _guard("wav-lsb", sweep_wav, data, flag_re)
    if out_dir and kind in IMAGE_KINDS:
        try:
            planes = save_bit_planes(open_image(data), out_dir / "planes")
        except Exception as exc:  # same guard as the checks
            fs.append(Finding("sweep", clean(f"bit planes failed: {exc}"), SCORE_NOTE))
    fs += _guard("external", run_external, path, data, kind, out_dir, wordlist, flag_re)
    if out_dir:
        for f in list(fs):
            if f.blob is not None and f.name:
                try:
                    save_artifact(out_dir, f.name, f.blob)
                except (OSError, ValueError) as exc:
                    fs.append(Finding("sweep", clean(f"saving {f.name} failed: {exc}"), SCORE_NOTE))
                    f.name = None
    return rank(fs), planes


CSS = """body{font:14px/1.4 system-ui,sans-serif;margin:16px;color-scheme:light dark}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #8884;padding:4px 6px;text-align:left;vertical-align:top}
pre{white-space:pre-wrap;word-break:break-all;max-height:30em;overflow:auto}
.g{display:flex;flex-wrap:wrap;gap:8px}figure{margin:0}img{width:160px;border:1px solid #8884}
figcaption{text-align:center}"""


def write_report(out_dir: Path, path: Path, findings: list[Finding], planes: list[Path]) -> Path:
    e = html.escape
    rows = []
    for f in findings:
        detail = f"<details><summary>detail</summary><pre>{e(f.detail)}</pre></details>" if f.detail else ""
        link = f'<a href="{e(f.name)}">{e(f.name)}</a>' if f.blob is not None and f.name else ""
        rows.append(f"<tr><td>{f.score}</td><td>{e(f.check)}</td><td>{e(f.title)}{detail}</td><td>{link}</td></tr>")
    imgs = [f'<figure><img src="planes/{e(p.name)}" alt="{e(p.stem)}" loading="lazy" '
            f'style="image-rendering:pixelated"><figcaption>{e(p.stem)}</figcaption></figure>'
            for p in planes]
    title = e(f"stegsweep: {path.name}")
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>'
           f"<style>{CSS}</style></head><body><h1>{title}</h1>"
           f"<h2>Findings</h2><table><tr><th>score</th><th>check</th><th>finding</th><th>artifact</th></tr>"
           f"{''.join(rows)}</table>"
           + (f'<h2>Bit planes</h2><div class="g">{"".join(imgs)}</div>' if imgs else "")
           + "</body></html>\n")
    report = out_dir / "index.html"
    report.write_text(doc, encoding="utf-8", errors="replace")
    return report


def _regex(s: str) -> re.Pattern[str]:
    try:
        return re.compile(s)
    except re.error as exc:
        raise argparse.ArgumentTypeError(f"bad regex: {exc}") from None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="stegsweep", description="One command, every steg check: local CTF "
                                 "steganography triage.")
    ap.add_argument("file", type=Path)
    ap.add_argument("-o", "--output", type=Path, metavar="DIR", help="write artifacts, bit planes and index.html here")
    ap.add_argument("--wordlist", type=Path, metavar="FILE", help="passphrase list for stegseek")
    ap.add_argument("--flag-format", type=_regex, default=DEFAULT_FLAG_FORMAT, metavar="REGEX",
                    help="flag regex (default: common CTF formats like picoCTF{...})")
    a = ap.parse_args(argv)

    def fail(msg: str) -> int:
        print(f"stegsweep: {clean(msg, 300)}", file=sys.stderr)
        return 2

    try:
        if not a.file.is_file():
            return fail(f"not a regular file: {a.file}")
        if a.file.stat().st_size > MAX_INPUT_BYTES:
            return fail(f"input bigger than {MAX_INPUT_BYTES} bytes: {a.file}")
        if a.wordlist and not a.wordlist.is_file():
            return fail(f"wordlist not found: {a.wordlist}")
        if a.output and a.output.exists() and not a.output.is_dir():
            return fail(f"output exists and is not a directory: {a.output}")
        with open(a.file, "rb") as fh:
            data = fh.read(MAX_INPUT_BYTES + 1)
        if len(data) > MAX_INPUT_BYTES:
            return fail(f"input bigger than {MAX_INPUT_BYTES} bytes: {a.file}")
        if a.output:
            a.output.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return fail(str(exc))

    findings, planes = sweep(a.file, data, a.flag_format, a.wordlist, a.output)
    report = None
    if a.output:
        try:
            report = write_report(a.output, a.file, findings, planes)
        except OSError as exc:
            print(f"stegsweep: report failed: {clean(str(exc), 300)}", file=sys.stderr)

    ranked = [f for f in findings if f.score > 0]
    notes = [f.title for f in findings if f.score <= 0]
    print(f"stegsweep: {clean(a.file.name)} ({sniff(data)}, {len(data)} bytes)")
    if not ranked:
        print("no findings")
    for f in ranked[:MAX_SHOWN]:
        print(f"[{f.score:3d}] {f.check:<11} {f.title}")
    if notes:
        print("notes: " + "; ".join(notes))
    hidden = len(ranked) - MAX_SHOWN
    if hidden > 0:
        print(f"{hidden} more findings in {report}" if report else f"{hidden} more findings (use -o DIR for the full report)")
    elif report:
        print(f"report: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
