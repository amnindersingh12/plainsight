# Changelog

All notable changes to the three packages in this repository. Versions are per package; release tags
(`v0.1.0`, `v0.2.0`, ...) cover the whole repository.

## v0.2.0 - 2026-11-22

- unseen 0.2.0: the GitHub Action also scans pull request, issue, comment, review and discussion text
  (`event-text` input, default on), and a new `unseen event [event.json]` command does the same locally.
  Hidden instructions in a PR description or issue are the most direct way to reach an AI agent.
- Browser demo of unseen (GitHub Pages): paste text, see hidden characters and decoded messages; runs
  entirely in the browser. CI checks it against the Python rules on every push.
- All packages: PyPI metadata (license expression, classifiers, project URLs) and a trusted-publishing
  release workflow, so `pip install unseen-scan`, `pip install stegsweep` and `pip install stegsurvive` work
  once published.
- CI: tests run on Linux, Windows and macOS (Python 3.10 and 3.13 for unseen and stegsweep, 3.12 for
  stegsurvive), plus a packaging check (`python -m build` and `twine check --strict`).
- stegsweep: tests close image files and read reports as UTF-8, so they also pass on Windows.

## v0.1.1 - 2026-11-22

- unseen 0.1.1: a file with a binary extension whose first bytes match that format's signature (PNG, JPEG,
  GIF, PDF, ZIP, ...) is treated as binary, even when compressed bytes happen to decode to a bidi or tag
  character. A text file that is only named like a binary is still scanned.
- Docs: new READMEs with real demos and step-by-step guides; stegsurvive ships a decodable example
  (`stegsurvive/examples/secret.jpg`), stegsweep ships five practice CTF challenges (`stegsweep/examples/`).

## v0.1.0 - 2026-11-22

First release of the three tools in one repository.

- unseen 0.1.0: finds invisible Unicode (tag characters, bidi controls, zero-width characters,
  variation-selector smuggling, invisible fillers) and decodes hidden tag-character messages. CLI,
  GitHub Action, pre-commit hook. Standard library only.
- stegsurvive 0.1.0: hides up to 64 bytes (56 with the built-in password mode) in an image so it survives
  JPEG q60-95, resizing to 50/75% and WebP, at about 46 dB PSNR. Reed-Solomon error correction, optional
  AES-GCM, survival benchmark.
- stegsweep 0.1.0: one-command CTF steganography triage with a ranked summary and an HTML report.
