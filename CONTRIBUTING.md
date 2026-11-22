# Contributing

Thanks for helping. Issues and pull requests are welcome; for anything larger than a small fix, open an
issue first so we can agree on the approach.

## Layout

Three independent Python packages (3.10+), one folder each, each with its own README, tests and command:

| Folder | Package on PyPI | Dependencies |
|---|---|---|
| `unseen/` | `unseen-scan` | none (standard library only, keep it that way) |
| `stegsweep/` | `stegsweep` | Pillow |
| `stegsurvive/` | `stegsurvive` | Pillow, numpy; optional `cryptography` |

## Development setup

```sh
git clone https://github.com/amnindersingh12/plainsight && cd plainsight
python3 -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate

cd unseen && python -m unittest discover -s tests && cd ..
pip install -e stegsweep && (cd stegsweep && python -m unittest discover -s tests)
pip install -e 'stegsurvive[crypto]' && (cd stegsurvive && python -m unittest discover -s tests)
```

The stegsurvive suite takes about a minute. CI runs all three suites on Linux, Windows and macOS.

## Rules for changes

- **Tests first.** A bug fix starts with a test that fails on the bug; a new check starts with a test input
  it must catch. Tests generate their own inputs (no downloaded files, no copyrighted images).
- **Keep it small.** Prefer the standard library and platform features over new dependencies, and the
  shortest change that fixes the actual cause.
- **No literal invisible characters in source.** Write them as escapes (`"\u202e"`, `"\U000e0041"`), never as
  the raw characters. Some editors and tools silently turn an escape into the real character, so run the
  self-scan before you commit:

  ```sh
  unseen/hook.py scan -- .        # must print "no findings"
  ```

  CI runs the same scan through the GitHub Action.
- **Untrusted input stays untrusted.** stegsweep must never execute extracted data, write outside its report
  directory, or read without size limits; keep the existing caps when adding checks.
- **Honest numbers.** README figures must be reproducible with the tools themselves. stegsurvive's
  real-platform results only come from real uploads (use the "stegsurvive platform result" issue form).

## Images in the READMEs

Terminal images are real command output, rendered as SVG with `scripts/term_svg.py`:

```sh
some-command 2>&1 | python3 scripts/term_svg.py tool/docs/name.svg --title "tool" --hl "PATTERN"
```

Write the transcript with `$ ` in front of each command line. Do not edit output by hand.

## Releases

1. Bump `version` in the package's `pyproject.toml` and add an entry to `CHANGELOG.md`.
2. Create a GitHub release with a new tag (`vX.Y.Z`). The `release` workflow builds every package and
   publishes new versions to PyPI through trusted publishing; versions already on PyPI are skipped.
