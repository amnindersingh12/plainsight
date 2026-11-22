#!/usr/bin/env python3
"""Render real terminal output as a terminal-window SVG for the READMEs.

usage: python3 scripts/term_svg.py OUT.svg [--title T] [--hl REGEX] < transcript.txt
Lines starting with "$ " are commands; lines matching --hl are highlighted.
"""
import argparse, html, re, sys

FONT, LH, CW, PAD, BAR = 14, 20, 8.43, 18, 30   # font px, line height, mono char width, padding, title bar

def esc(s):
    return html.escape(s).replace(" ", "&#160;")   # SVG collapses plain spaces

def render(lines, title, hl):
    w = int(max(60, *(len(l) for l in lines)) * CW + 2 * PAD)
    h = len(lines) * LH + 2 * PAD + BAR
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
           f'<rect width="{w}" height="{h}" rx="10" fill="#0d1117"/>',
           f'<rect width="{w}" height="{BAR}" rx="10" fill="#161b22"/><rect y="{BAR - 10}" width="{w}" height="10" fill="#161b22"/>',
           *(f'<circle cx="{18 + i * 20}" cy="15" r="6" fill="{c}"/>' for i, c in enumerate(("#ff5f56", "#ffbd2e", "#27c93f"))),
           f'<text x="{w / 2}" y="20" fill="#8b949e" font-family="sans-serif" font-size="12" text-anchor="middle">{html.escape(title)}</text>',
           f'<g font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,DejaVu Sans Mono,monospace" font-size="{FONT}">']
    for i, line in enumerate(lines):
        y = BAR + PAD + (i + 1) * LH - 5
        if line.startswith("$ "):
            body = f'<tspan fill="#3fb950">$ </tspan><tspan fill="#e6edf3">{esc(line[2:])}</tspan>'
        else:
            color = "#f2cc60" if hl and re.search(hl, line) else "#c9d1d9"
            body = f'<tspan fill="{color}">{esc(line)}</tspan>'
        out.append(f'<text x="{PAD}" y="{y}">{body}</text>')
    out += ["</g>", "</svg>"]
    return "\n".join(out) + "\n"

if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("out"); a.add_argument("--title", default="terminal"); a.add_argument("--hl")
    args = a.parse_args()
    text = sys.stdin.read().expandtabs(8).rstrip("\n")
    # never let control or invisible characters into the image source
    text = "".join(c if c == "\n" or (c.isprintable() and not 0xE0000 <= ord(c) <= 0xE007F) else "?" for c in text)
    open(args.out, "w", encoding="utf-8").write(render(text.split("\n"), args.title, args.hl))
