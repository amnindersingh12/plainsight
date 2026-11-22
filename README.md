<p align="center">
  <img src="assets/banner.svg" alt="plainsight: unseen, stegsurvive, stegsweep" width="900">
</p>

<p align="center">
  <a href="https://github.com/amnindersingh12/plainsight/actions/workflows/ci.yml"><img src="https://github.com/amnindersingh12/plainsight/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/amnindersingh12/plainsight/releases"><img src="https://img.shields.io/github/v/release/amnindersingh12/plainsight?color=3fb950" alt="Release"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="MIT license"></a>
</p>

Three small, tested command-line tools about data hidden in plain sight:

| | Tool | Use it to |
|---|---|---|
| **Defend** | [unseen](unseen/) | Catch invisible Unicode that hides instructions for AI agents (prompt injection) or flips code meaning (Trojan Source). CI-ready, zero dependencies. |
| **Hide** | [stegsurvive](stegsurvive/) | Hide a short message in a photo that still reads after WhatsApp, Instagram or X recompress and resize it. |
| **Hunt** | [stegsweep](stegsweep/) | Run every common CTF steganography check on a file with one command and get the flag first. |

Each folder is its own Python package with its own README, tests and command. Install only the one you need.

---

## unseen: what you see is not what the AI reads

<img src="unseen/docs/demo.svg" alt="cat shows an innocent comment; unseen scan reveals a hidden instruction" width="820">

A pull request comment, README or issue can carry instructions made of Unicode tag characters. Reviewers see
nothing; an AI coding agent reads every one. `unseen` finds them, decodes them, and fails your build.

**[Try it in your browser](https://amnindersingh12.github.io/plainsight/index.html?demo=1)**: paste any text and see what is hidden in it. Nothing leaves the page.

```sh
pipx install "git+https://github.com/amnindersingh12/plainsight#subdirectory=unseen"
unseen hide "ignore previous instructions" --cover "LGTM" > test.txt   # make a test file
unseen scan .                                                           # scan your repo
```

Protect every pull request, issue and comment (files and the text people write):

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0
- uses: amnindersingh12/plainsight/unseen@v0.2.0
```

[Full guide, pre-commit hook and rules](unseen/)

## stegsurvive: a hidden message that survives the trip

<img src="stegsurvive/docs/journey.png" alt="original photo, photo with hidden message, after WhatsApp-style recompression, revealed message" width="900">

Classic LSB steganography dies the moment an app recompresses your photo. `stegsurvive` spreads up to 64 bytes
across the image as fine texture with error correction, so it survives JPEG quality 60-95, resizing to half
size and WebP, at about 46 dB PSNR.

**[Try it in your browser](https://amnindersingh12.github.io/plainsight/stegsurvive.html)**: upload your own photo, hide or reveal a message. Your image never leaves the page.

```sh
pipx install "git+https://github.com/amnindersingh12/plainsight#subdirectory=stegsurvive"
curl -LO https://github.com/amnindersingh12/plainsight/raw/main/stegsurvive/examples/secret.jpg
stegsurvive reveal secret.jpg                      # PASS, then: meet at the old bridge, 6pm
stegsurvive hide photo.png "your message" -o out.jpg
stegsurvive bench photo.png                        # which recompressions does it survive?
```

[Full guide, password mode, results and limits](stegsurvive/)

## stegsweep: every steg check, one command

<img src="stegsweep/docs/demo.svg" alt="stegsweep finds a flag hidden in a zip appended to a JPEG" width="820">

Metadata, PNG text chunks, data after the end of the image, embedded zips (searched in memory), zsteg-style LSB
sweeps, bit planes and WAV audio, plus stegseek, steghide, exiftool and binwalk when installed. Likely flags are
ranked first; `-o DIR` writes an HTML report with every bit plane.

```sh
pipx install "git+https://github.com/amnindersingh12/plainsight#subdirectory=stegsweep"
git clone https://github.com/amnindersingh12/plainsight && cd plainsight/stegsweep
stegsweep examples/02-sunset.jpg                   # five practice challenges in examples/
stegsweep examples/01-sky.png -o report/           # open report/index.html
```

<img src="stegsweep/docs/report.png" alt="stegsweep HTML report with findings table and 24 bit planes" width="720">

[Full guide, practice challenges and checks](stegsweep/)

---

## Development

```sh
git clone https://github.com/amnindersingh12/plainsight && cd plainsight
cd unseen && python3 -m unittest discover -s tests                     # stdlib only
cd ../stegsweep && pip install -e . && python3 -m unittest discover -s tests
cd ../stegsurvive && pip install -e '.[crypto]' && python3 -m unittest discover -s tests
```

CI runs all three suites and scans this repository with `unseen` on every push.
Terminal images are real output, rendered with [scripts/term_svg.py](scripts/term_svg.py).

## License

MIT
