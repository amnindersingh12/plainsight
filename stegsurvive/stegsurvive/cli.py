"""stegsurvive command line: hide, reveal, bench."""
import argparse
import getpass
import os
import sys
import warnings

import numpy as np
from PIL import Image, ImageOps

from . import CAPACITY, RevealError, _flatten, core, hide, reveal
from .attacks import ATTACKS


def _password(args):
    return getpass.getpass("Password: ") if args.password else None


def _rgb(img):
    return np.asarray(_flatten(ImageOps.exif_transpose(img))[0].convert("RGB"))


def _hide(args):
    with Image.open(args.input) as src:
        out = hide(src, args.message, _password(args))
        psnr = core.psnr(_rgb(src), _rgb(out))
    if args.output.lower().endswith((".jpg", ".jpeg")):
        out.convert("RGB").save(args.output, quality=95)
    else:
        out.save(args.output)
    print(f"hid {len(args.message.encode('utf-8'))} bytes in {args.output} (PSNR {psnr:.1f} dB)")
    return 0


def _reveal(args):
    try:
        with Image.open(args.input) as img:
            msg = reveal(img, _password(args))
    except RevealError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print(msg.decode("utf-8", "replace"))
    print("PASS", file=sys.stderr)
    return 0


def _bench(args):
    msg = os.urandom(CAPACITY)
    with Image.open(args.input) as src:
        stego = hide(src, msg)
        print(f"PSNR {core.psnr(_rgb(src), _rgb(stego)):.1f} dB")
    ref = core.cell_soft(_rgb(stego), core.DEFAULT_KEY) > 0
    ok = True
    for name, required, fn in ATTACKS:
        att = fn(stego)
        ber = float(np.mean((core.cell_soft(np.asarray(att), core.DEFAULT_KEY) > 0) != ref)) \
            if min(att.size) >= core.GRID else 1.0
        try:
            passed = reveal(att) == msg
        except RevealError:
            passed = False
        ok &= passed or not required
        print(f"{name:<16} {'required' if required else 'measured':<9} BER {ber:.4f}  {'PASS' if passed else 'FAIL'}")
    return 0 if ok else 1


def main(argv=None):
    p = argparse.ArgumentParser(prog="stegsurvive", description="Hidden messages that survive recompression.")
    sub = p.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hide", help=f"hide a message (max {CAPACITY} bytes) in an image")
    h.add_argument("input")
    h.add_argument("message")
    h.add_argument("-o", "--output", required=True, help="output image; .png keeps it lossless")
    h.add_argument("--password", action="store_true",
                   help="prompt for a password: AES-GCM with stegsurvive[crypto] installed, "
                        "otherwise obfuscation only (a keyed XOR, not encryption)")
    r = sub.add_parser("reveal", help="print the hidden message; PASS/FAIL on stderr")
    r.add_argument("input")
    r.add_argument("--password", action="store_true", help="prompt for a password")
    b = sub.add_parser("bench", help="simulate recompression/resizing attacks and print a table")
    b.add_argument("input")
    args = p.parse_args(argv)
    warnings.formatwarning = lambda msg, *_a, **_k: f"warning: {msg}\n"
    try:
        return {"hide": _hide, "reveal": _reveal, "bench": _bench}[args.cmd](args)
    except (OSError, ValueError, TypeError, Image.DecompressionBombError) as e:  # bad file/image, too long
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
