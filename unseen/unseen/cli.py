"""Command line: unseen scan | hide | reveal."""
import argparse
import os
import re
import sys

from unseen.report import render, summary
from unseen.scan import read_text, scan
from unseen.tags import hide, reveal

CP = re.compile(r"^(?:[Uu]\+)?([0-9A-Fa-f]{4,6})$")


def parse_cp(s: str) -> int:
    m = CP.match(s)
    if not m or int(m.group(1), 16) > 0x10FFFF:
        raise argparse.ArgumentTypeError("expected U+XXXX")
    return int(m.group(1), 16)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="unseen", description="Find invisible Unicode that hides prompt injection.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="scan files, directories or - (stdin); exit 1 on failing findings")
    s.add_argument("paths", nargs="*", default=["."])
    s.add_argument("--format", choices=("text", "json", "github"), default="text")
    s.add_argument("--fix", action="store_true", help="strip failing characters in place")
    s.add_argument("--strict", action="store_true", help="treat warnings as failures")
    s.add_argument("--allow", type=parse_cp, action="append", default=[], metavar="U+XXXX",
                   help="never report this code point (repeatable)")
    h = sub.add_parser("hide", help="encode ASCII text as invisible tag characters")
    h.add_argument("text")
    h.add_argument("--cover", default="", help="visible text to put in front")
    r = sub.add_parser("reveal", help="decode tag-character messages from a file or - (stdin)")
    r.add_argument("path", nargs="?", default="-")
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    argv = sys.argv[1:] if argv is None else list(argv)
    if "--" in argv:  # after "--", "-" is a file named "-", not stdin
        i = argv.index("--") + 1
        argv[i:] = [os.path.join(os.curdir, x) if x == "-" else x for x in argv[i:]]
    a = _parser().parse_args(argv)

    if a.cmd == "hide":
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")  # tag chars must survive a cp1252 redirect on Windows
        try:
            print(a.cover + hide(a.text))
        except ValueError:
            print("unseen: hide only encodes printable ASCII", file=sys.stderr)
            return 2
        return 0

    if a.cmd == "reveal":
        try:
            decoded = read_text(a.path)
        except OSError as exc:
            print(f"unseen: cannot read {a.path}: {exc.strerror or exc}", file=sys.stderr)
            return 2
        if decoded is None:
            print(f"unseen: {a.path} is binary", file=sys.stderr)
            return 2
        msgs = reveal(decoded[0])
        for m in msgs:
            print(m)
        if not msgs:
            print("unseen: nothing hidden", file=sys.stderr)
        return 0 if msgs else 1

    if a.fix and "-" in a.paths:
        print("unseen: --fix cannot be used with stdin", file=sys.stderr)
        return 2
    r = scan(a.paths, a.strict, frozenset(a.allow), a.fix)
    sys.stdout.write(render(a.format, r.findings, r.files, r.ignored, r.binary, r.links))
    for e in r.errors:
        print(e, file=sys.stderr)
    if a.format != "json":
        print(summary(r.findings, r.files, r.ignored, r.binary, r.links), file=sys.stderr)
        if r.fixed:
            print(f"unseen: fixed {len(r.fixed)} file(s)", file=sys.stderr)
    if r.errors:
        return 2
    return 1 if any(f.level == "fail" for f in r.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
