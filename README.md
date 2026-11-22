# plainsight

Three small tools about data hidden in plain sight: invisible text that steers AI agents, messages hidden in
photos that survive social media, and the checks CTF players run to find what is hidden in a file.

| Tool | What it does | Install |
|---|---|---|
| [unseen](unseen/) | Finds invisible Unicode (tag characters, bidi controls, zero-width characters) that hides prompt injection and Trojan Source in text and code. CLI, GitHub Action, pre-commit hook. Zero dependencies. | `pipx install "git+https://github.com/amnindersingh12/plainsight#subdirectory=unseen"` |
| [stegsurvive](stegsurvive/) | Hides up to 64 bytes in a photo so the message survives JPEG/WebP recompression and resizing like WhatsApp, Instagram or X apply. Includes a survival benchmark. | `pipx install "git+https://github.com/amnindersingh12/plainsight#subdirectory=stegsurvive"` |
| [stegsweep](stegsweep/) | One-command steganography triage for CTFs: LSB sweeps, bit planes, metadata, trailing data, embedded files and zips, optional stegseek/binwalk, HTML report. | `pipx install "git+https://github.com/amnindersingh12/plainsight#subdirectory=stegsweep"` |

Each folder is its own Python package (3.10+) with its own README, tests and command. Install only the one you need.

## Quick look

```console
$ unseen hide "ignore previous instructions" --cover "LGTM" > comment.txt
$ unseen scan comment.txt
comment.txt:1:5  U+E0069 TAG LATIN SMALL LETTER I  tag x28  hidden text: 'ignore previous instructions'

$ stegsurvive hide photo.png "meet at noon" -o photo.jpg
$ stegsurvive reveal photo.jpg        # still works after the app recompresses and resizes it

$ stegsweep challenge.png -o report/
[100] lsb         bit0,rgb,xy,msbfirst: picoCTF{...}
```

## GitHub Action and pre-commit (unseen)

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0
- uses: amnindersingh12/plainsight/unseen@v0.1.0
```

```yaml
repos:
  - repo: https://github.com/amnindersingh12/plainsight
    rev: v0.1.0
    hooks:
      - id: unseen
```

## License

MIT
