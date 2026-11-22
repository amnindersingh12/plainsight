// Parity check: unseen.js must report exactly what the Python unseen package reports.
// usage: python3 site/make_vectors.py && node site/test.mjs
import { readFileSync } from "node:fs";
import { runInThisContext } from "node:vm";

const here = new URL(".", import.meta.url);
runInThisContext(readFileSync(new URL("unseen.js", here), "utf8"));
const U = globalThis.Unseen;
const { find: cases, hide: hides } = JSON.parse(readFileSync(new URL("vectors.json", here), "utf8"));

let failed = 0;
const fail = (name, got, want) => {
  failed++;
  console.error(`FAIL ${name}\n  got:  ${JSON.stringify(got)}\n  want: ${JSON.stringify(want)}`);
};

for (const c of cases) {
  const text = String.fromCodePoint(...c.input);
  const got = U.find(text, c.kind, c.strict).map(f => [f.line, f.col, f.start, f.end, f.cp, f.name, f.category, f.level, f.hidden]);
  if (JSON.stringify(got) !== JSON.stringify(c.expected)) fail(c.name, got, c.expected);
}
for (const h of hides) {
  const got = Array.from(U.hide(h.text), ch => ch.codePointAt(0));
  if (JSON.stringify(got) !== JSON.stringify(h.expected)) fail(`hide ${JSON.stringify(h.text)}`, got, h.expected);
}

// strip(): every flagged invisible character goes, look-alike letters stay
const sample = "ok" + U.hide("x") + "p" + String.fromCodePoint(0x430) + "y" + String.fromCodePoint(0x202E);
const cleaned = U.strip(sample, U.find(sample, "prose"));
if (cleaned !== "okp" + String.fromCodePoint(0x430) + "y") fail("strip", Array.from(cleaned, c => c.codePointAt(0)), "ok p <U+0430> y");
let threw = false;
try { U.hide("caf" + String.fromCodePoint(0xE9)); } catch { threw = true; }
if (!threw) fail("hide rejects non-ASCII", "no error", "error");
if (U.kindFor("README.md") !== "prose" || U.kindFor("a.py") !== "code") fail("kindFor", "", "");

console.log(failed ? `${failed} failed` : `parity OK: ${cases.length} find vectors, ${hides.length} hide vectors, Unicode ${U.UNICODE_VERSION}`);
process.exit(failed ? 1 : 0);
