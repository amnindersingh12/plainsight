"""Render findings as text, JSON or GitHub workflow annotations."""
import json

from unseen.rules import Finding


def _message(f: Finding) -> str:
    if f.category == "skipped":
        return f.name + ("  skipped (warn)" if f.level == "warn" else "  skipped")
    msg = f"U+{f.cp:04X} {f.name}  {f.category}"
    if f.end - f.start > 1:
        msg += f" x{f.end - f.start}"
    if f.level == "warn":
        msg += " (warn)"
    if f.hidden:
        shown = f.hidden if len(f.hidden) <= 120 else f.hidden[:117] + "..."
        msg += f"  hidden text: {shown!r}"
    return msg


def _esc_data(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _esc_prop(s) -> str:
    return _esc_data(str(s)).replace(":", "%3A").replace(",", "%2C")


def render(fmt: str, findings: list[Finding], files: int, ignored: int, binary: int = 0, links: int = 0) -> str:
    if fmt == "json":
        skipped = {k: v for k, v in (("binary", binary), ("symlinks", links)) if v}
        return json.dumps({"files": files, "ignored": ignored, "skipped": skipped, "findings": [
            {"path": f.path, "line": f.line, "col": f.col, "codepoint": None if f.category == "skipped" else f"U+{f.cp:04X}", "name": f.name,
             "category": f.category, "level": f.level, "length": f.end - f.start, "hidden": f.hidden}
            for f in findings]}, indent=2) + "\n"
    if fmt == "github":
        return "".join(
            f"::{'error' if f.level == 'fail' else 'warning'} file={_esc_prop(f.path)},line={f.line},"
            f"col={f.col},title=unseen::{_esc_data(_message(f))}\n" for f in findings)
    if fmt == "text":
        return "".join(f"{f.path}:{f.line}:{f.col}  {_message(f)}\n" for f in findings)
    raise ValueError(f"unknown format {fmt!r}")


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def summary(findings: list[Finding], files: int, ignored: int, binary: int = 0, links: int = 0) -> str:
    if findings:
        fail = sum(f.level == "fail" for f in findings)
        out = f"unseen: {fail} failing, {_n(len(findings) - fail, 'warning')} in {_n(files, 'file')}"
    else:
        out = f"unseen: no findings in {_n(files, 'file')}"
    if binary:
        out += f", {_n(binary, 'binary file')} skipped"
    if links:
        out += f", {_n(links, 'symlink')} skipped"
    if ignored:
        out += f", {ignored} ignored by 'unseen: ignore'"
    return out
