// UI for stegsurvive.html. All image work happens in stegsurvive.worker.js (Pyodide + the real package).
const $ = (id) => document.getElementById(id);
const worker = new Worker("stegsurvive.worker.js");
let nextId = 0, caps = null, hideFile = null, revealFile = null, lastMessage = "", lastPassword = "";
const pending = new Map();

worker.onmessage = (e) => {
  if (e.data.status) { $("status").textContent = e.data.status; return; }
  const p = pending.get(e.data.id);
  pending.delete(e.data.id);
  e.data.ok ? p.resolve(e.data.result) : p.reject(new Error(e.data.error));
};
function run(cmd, args = {}, transfer = []) {
  return new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, cmd, args }, transfer);
  });
}

// tabs
for (const name of ["hide", "reveal"]) {
  $("tab-" + name).onclick = () => {
    for (const n of ["hide", "reveal"]) {
      $("tab-" + n).setAttribute("aria-selected", String(n === name));
      $("pane-" + n).hidden = n !== name;
    }
  };
}

// file pickers with drag and drop
function picker(name, onFile) {
  const drop = $("drop-" + name), input = $("file-" + name);
  input.onchange = () => input.files[0] && onFile(input.files[0]);
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => {
    e.preventDefault(); drop.classList.remove("over");
    const f = e.dataTransfer.files[0];
    if (f) onFile(f);
  };
}
function preview(img, file) {
  img.src = URL.createObjectURL(file);
  img.hidden = false;
}
picker("hide", (f) => { hideFile = f; preview($("preview-hide"), f); $("drop-hide-text").innerHTML = "<b>" + escapeHtml(f.name) + "</b> (click to change)"; update(); });
picker("reveal", (f) => { revealFile = f; preview($("preview-reveal"), f); update(); });

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// capacity counter and button state
function capacity() {
  if (!caps) return 64;
  if (!$("pw-hide").value) return caps.plain;
  return $("aes").checked ? caps.aes : caps.xor;
}
function update() {
  const used = new TextEncoder().encode($("msg").value).length, cap = capacity();
  $("counter").textContent = used + " / " + cap + " bytes" + ($("pw-hide").value ? ($("aes").checked ? " (AES-GCM)" : " (password)") : "");
  $("counter").classList.toggle("over", used > cap);
  $("aes-wrap").hidden = !$("pw-hide").value;
  $("xor-note").hidden = !$("pw-hide").value || $("aes").checked;
  $("btn-hide").disabled = !caps || !hideFile || used === 0 || used > cap;
  $("btn-reveal").disabled = !caps || !revealFile;
}
for (const id of ["msg", "pw-hide", "aes"]) $(id).addEventListener("input", update);

function showError(id, text) {
  $(id).textContent = text;
  $(id).hidden = !text;
}
function kb(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.round(n / 1024) + " KB"; }

async function hide(file, message, password, opts = {}) {
  const bytes = await file.arrayBuffer();
  return run("hide", {
    bytes, message, password, aes: opts.aes ?? $("aes").checked,
    resize: opts.resize ?? $("resize").checked, format: opts.format ?? document.querySelector("input[name=fmt]:checked").value,
  }, [bytes]);
}
async function reveal(blob, password) {
  const bytes = await blob.arrayBuffer();
  return run("reveal", { bytes, password }, [bytes]);
}

$("btn-hide").onclick = async () => {
  showError("err-hide", "");
  $("btn-hide").disabled = true;
  const message = $("msg").value, password = $("pw-hide").value;
  try {
    const t0 = performance.now();
    const r = await hide(hideFile, message, password);
    const fmt = document.querySelector("input[name=fmt]:checked").value;
    const blob = new Blob([r.bytes], { type: fmt === "png" ? "image/png" : "image/jpeg" });
    lastMessage = message; lastPassword = password;
    $("img-before").src = $("preview-hide").src;
    $("img-after").src = URL.createObjectURL(blob);
    $("download").href = $("img-after").src;
    $("download").download = hideFile.name.replace(/\.[^.]*$/, "") + ".stegsurvive." + (fmt === "png" ? "png" : "jpg");
    $("stats").textContent = r.width + " x " + r.height + " px, " + kb(r.size) + ", PSNR " + r.psnr.toFixed(1) + " dB, "
      + ((performance.now() - t0) / 1000).toFixed(1) + " s";
    $("verified").textContent = r.verified ? "verified: the message reads back from this file" : "warning: the saved file did not read back; try PNG";
    $("verified").className = "badge " + (r.verified ? "ok" : "fail");
    $("notes").innerHTML = r.notes.map((n) => '<p class="note">' + escapeHtml(n) + "</p>").join("");
    $("whatsapp-result").textContent = "";
    $("result-hide").hidden = false;
  } catch (err) {
    showError("err-hide", err.message);
  }
  update();
};

$("btn-whatsapp").onclick = async () => {
  $("btn-whatsapp").disabled = true;
  try {
    const r = await run("whatsapp", { password: lastPassword, message: lastMessage });
    $("whatsapp-result").textContent = (r.ok ? "PASS: " : "FAIL: ") + "after a WhatsApp-style trip (" + r.width + " x " + r.height
      + " px, JPEG quality " + r.quality + ") the message " + (r.ok ? "still reads back." : "was lost.");
  } catch (err) {
    $("whatsapp-result").textContent = err.message;
  }
  $("btn-whatsapp").disabled = false;
};

$("btn-reveal").onclick = async () => {
  $("btn-reveal").disabled = true;
  $("result-reveal").hidden = false;
  $("secret").hidden = true;
  showError("err-reveal", "");
  try {
    const r = await reveal(revealFile, $("pw-reveal").value);
    if (r.ok) {
      $("secret-text").textContent = r.isText ? r.text : "(binary, hex) " + r.text;
      $("secret").hidden = false;
    } else {
      showError("err-reveal", r.error.charAt(0).toUpperCase() + r.error.slice(1) + "."
        + ($("pw-reveal").value ? "" : " If it was hidden with a password, enter it and try again."));
    }
  } catch (err) {
    showError("err-reveal", err.message);
  }
  update();
};
$("btn-copy").onclick = () => navigator.clipboard.writeText($("secret-text").textContent);

// start Python
run("init").then((c) => { caps = c; update(); if (new URLSearchParams(location.search).has("selftest")) selftest(); })
  .catch((err) => { $("status").textContent = "Could not start Python: " + err.message; });

// ?selftest=1: reveal the bundled example, then hide and reveal on a generated image
async function selftest() {
  const out = $("selftest");
  out.hidden = false;
  const log = (line) => { out.textContent += line + "\n"; };
  try {
    const ex = await (await fetch("examples/secret.jpg")).blob();
    const r1 = await reveal(ex, "");
    log((r1.ok && r1.text === "meet at the old bridge, 6pm" ? "PASS" : "FAIL") + " reveal examples/secret.jpg: " + (r1.text || r1.error));

    const c = document.createElement("canvas");
    c.width = 1280; c.height = 800;
    const g = c.getContext("2d"), d = g.createImageData(c.width, c.height);
    let seed = 1;
    const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
    for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) {
      const i = (y * c.width + x) * 4, n = rnd() * 60;
      d.data[i] = 60 + x / 8 + n; d.data[i + 1] = 90 + y / 6 + n; d.data[i + 2] = 140 + n; d.data[i + 3] = 255;
    }
    g.putImageData(d, 0, 0);
    const png = await new Promise((res) => c.toBlob(res, "image/png"));
    const file = new File([png], "selftest.png", { type: "image/png" });
    const t0 = performance.now();
    const h = await hide(file, "selftest 123", "", { aes: false, resize: true, format: "jpeg" });
    log((h.verified ? "PASS" : "FAIL") + " hide 1280x800 -> JPEG: PSNR " + h.psnr.toFixed(1) + " dB, " + ((performance.now() - t0) / 1000).toFixed(1) + " s");
    const r2 = await reveal(new Blob([h.bytes]), "");
    log((r2.ok && r2.text === "selftest 123" ? "PASS" : "FAIL") + " reveal hidden JPEG: " + (r2.text || r2.error));
    lastMessage = "selftest 123"; lastPassword = "";
    const w = await run("whatsapp", { password: "", message: "selftest 123" });
    log((w.ok ? "PASS" : "FAIL") + " simulated WhatsApp " + w.width + "x" + w.height + " q" + w.quality);
    const hx = await hide(file, "obfuscated only", "pw0", { aes: false, resize: true, format: "jpeg" });
    const rx = await reveal(new Blob([hx.bytes]), "pw0");
    log((rx.ok && rx.text === "obfuscated only" ? "PASS" : "FAIL") + " password without AES round trip: " + (rx.text || rx.error));
    const h2 = await hide(file, "secret with aes", "pw1", { aes: true, resize: true, format: "png" });
    const r3 = await reveal(new Blob([h2.bytes]), "pw1");
    const r4 = await reveal(new Blob([h2.bytes]), "wrong");
    log((r3.ok && r3.text === "secret with aes" && !r4.ok ? "PASS" : "FAIL") + " AES password round trip, wrong password: " + (r4.error || "accepted!"));
  } catch (err) {
    log("FAIL selftest error: " + err.message);
  }
  log("DONE");
}
