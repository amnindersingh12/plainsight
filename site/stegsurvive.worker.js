// Runs the real stegsurvive package (copied to py/stegsurvive/ by the Pages workflow) in Pyodide.
importScripts("https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.js");

const FILES = ["__init__.py", "core.py", "rs.py", "attacks.py"];
const status = (text) => postMessage({ status: text });

const GLUE = `
import io, sys, warnings, importlib
sys.path.insert(0, "/home/pyodide")
import numpy as np
from PIL import Image, ImageOps
import stegsurvive as S
from stegsurvive import core, attacks

def _load(path):
    im = Image.open(path)
    im.load()
    return im

def _rgb(img):
    return np.asarray(S._flatten(ImageOps.exif_transpose(img))[0].convert("RGB"))

def caps():
    return {"plain": S.CAPACITY, "xor": S.XOR_CAPACITY, "aes": S.AES_CAPACITY}

def reload_hashlib():
    import hashlib
    importlib.reload(hashlib)  # now backed by OpenSSL, which provides scrypt for password keys

def reload_with_crypto():
    importlib.reload(S)

def do_hide(src, dst, message, password, aes, resize, fmt):
    password = password or None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        img = ImageOps.exif_transpose(_load(src))
        if img.mode == "P":
            img = img.convert("RGBA")
        elif img.mode not in ("RGB", "RGBA", "L", "LA"):
            img = img.convert("RGB")
        if resize and max(img.size) > 2048:
            f = 2048 / max(img.size)
            img = img.resize((round(img.width * f), round(img.height * f)), Image.LANCZOS)
        saved = S.AESGCM
        if not aes:
            S.AESGCM = None  # password without AES: the package's documented obfuscation-only mode
        try:
            out = S.hide(img, message, password)
        finally:
            S.AESGCM = saved
        psnr = core.psnr(_rgb(img), _rgb(out))
        buf = io.BytesIO()
        if fmt == "jpeg":
            out.convert("RGB").save(buf, "JPEG", quality=92)
        else:
            out.save(buf, "PNG")
        data = buf.getvalue()
        try:
            verified = S.reveal(Image.open(io.BytesIO(data)), password) == message.encode("utf-8")
        except S.RevealError:
            verified = False
    with open(dst, "wb") as f:
        f.write(data)
    notes = [str(w.message) for w in caught if "cryptography is not installed" not in str(w.message)]
    return {"psnr": psnr, "verified": verified, "width": out.width, "height": out.height, "size": len(data), "notes": notes}

def do_reveal(src, password):
    try:
        msg = S.reveal(_load(src), password or None)
    except S.RevealError as e:
        return {"ok": False, "error": str(e)}
    try:
        return {"ok": True, "text": msg.decode("utf-8"), "isText": True}
    except UnicodeDecodeError:
        return {"ok": True, "text": msg.hex(), "isText": False}

def do_whatsapp(src, password, message):
    side, q = attacks.PLATFORMS["whatsapp"]
    im = attacks.jpeg(attacks.fit(_load(src), side), q)
    try:
        ok = S.reveal(im, password or None) == message.encode("utf-8")
    except S.RevealError:
        ok = False
    return {"ok": ok, "width": im.width, "height": im.height, "quality": q}
`;

let py, hasHashlib = false, hasCrypto = false;
const ready = (async () => {
  status("Loading Python in your browser (first visit downloads about 10 MB)...");
  py = await loadPyodide();
  status("Loading numpy and Pillow...");
  await py.loadPackage(["numpy", "pillow"]);
  py.FS.mkdirTree("/home/pyodide/stegsurvive");
  for (const f of FILES) {
    const r = await fetch("py/stegsurvive/" + f);
    if (!r.ok) throw new Error("could not load stegsurvive/" + f + " (" + r.status + ")");
    py.FS.writeFile("/home/pyodide/stegsurvive/" + f, await r.text());
  }
  py.runPython(GLUE);
  return call("caps");
})();

function call(name, ...args) {
  const r = py.globals.get(name)(...args);
  if (!r || typeof r.toJs !== "function") return r;  // None and plain values come back as JS values
  const out = r.toJs({ dict_converter: Object.fromEntries });
  r.destroy();
  return out;
}

async function needPassword(aes) {
  if (!hasHashlib) {
    status("Loading password support (OpenSSL)...");
    await py.loadPackage("hashlib");
    call("reload_hashlib");
    hasHashlib = true;
  }
  if (aes) await needCrypto();
}

async function needCrypto() {
  if (hasCrypto) return;
  status("Loading AES-GCM (cryptography, about 2 MB)...");
  await py.loadPackage("cryptography");
  call("reload_with_crypto");
  hasCrypto = true;
}

function friendly(err) {
  const lines = String(err && err.message || err).trim().split("\n").filter(Boolean);
  let last = lines[lines.length - 1] || "unknown error";
  if (/MemoryError|memory access out of bounds|Out of memory/i.test(last)) return "The image is too large for the browser. Keep the resize option on.";
  if (/UnidentifiedImageError/.test(last)) return "This file is not an image the browser version can read. Use JPEG, PNG or WebP.";
  return last.replace(/^[A-Za-z.]*(Error|Exception): /, "");
}

onmessage = async (e) => {
  const { id, cmd, args = {} } = e.data;
  try {
    const caps = await ready;
    let result;
    if (cmd === "init") {
      result = caps;
    } else if (cmd === "hide") {
      if (args.password) await needPassword(!!args.aes);
      py.FS.writeFile("/tmp/in", new Uint8Array(args.bytes));
      status("Hiding your message...");
      result = call("do_hide", "/tmp/in", "/tmp/out", args.message, args.password, !!args.aes, !!args.resize, args.format);
      result.bytes = py.FS.readFile("/tmp/out");
    } else if (cmd === "reveal") {
      if (args.password) await needPassword(true);
      py.FS.writeFile("/tmp/reveal", new Uint8Array(args.bytes));
      status("Looking for a hidden message...");
      result = call("do_reveal", "/tmp/reveal", args.password);
    } else if (cmd === "whatsapp") {
      status("Simulating WhatsApp (resize to 1600 px, JPEG quality 70)...");
      result = call("do_whatsapp", "/tmp/out", args.password, args.message);
    } else {
      throw new Error("unknown command " + cmd);
    }
    status("Ready.");
    postMessage({ id, ok: true, result }, result && result.bytes ? [result.bytes.buffer] : []);
  } catch (err) {
    status("Ready.");
    postMessage({ id, ok: false, error: friendly(err) });
  }
};
