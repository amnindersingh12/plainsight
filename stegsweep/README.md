# stegsweep

One command, every steg check: local CTF steganography triage.

## Demo

Real output on the synthetic files from `python tests/fixtures.py demo/` (no optional tools installed):

```
$ stegsweep demo/lsb.png
stegsweep: lsb.png (png, 288 bytes)
[100] lsb         bit0,rgb,xy,msbfirst: picoCTF{l5b_15_n0t_s3cr3t}
[ 50] lsb         bit0,r,xy,msbfirst: text "^5?QE#v2\"
notes: exiftool not installed, skipped; binwalk not installed, skipped
$ stegsweep demo/zip.jpg
stegsweep: zip.jpg (jpeg, 786 bytes)
[100] strings     raw: picoCTF{l5b_15_n0t_s3cr3t}
[ 80] signature   zip at 0x286
[ 80] trailing    140 bytes after JPEG EOI at 0x286 (zip data)
[ 10] strings     4 printable strings (8+ chars)
notes: exiftool not installed, skipped; binwalk not installed, skipped; steghide not installed, skipped
```

## Install

```
pipx install "git+https://github.com/amnindersingh12/plainsight#subdirectory=stegsweep"
```

Python 3.10+. The only dependency is Pillow.

## Usage

```
stegsweep FILE [-o DIR] [--wordlist FILE] [--flag-format REGEX]
```

- `FILE`: the image, audio or other file to triage.
- `-o DIR`: save extracted data, bit-plane images and `DIR/index.html` (findings plus all bit planes, one static
  file, no JavaScript). Without `-o` nothing is written.
- `--wordlist FILE`: passphrase list for stegseek (for example rockyou.txt).
- `--flag-format REGEX`: what a flag looks like, for example `'picoCTF\{.*?\}'`. The default matches common
  formats such as `flag{...}`, `picoCTF{...}`, `HTB{...}`, `THM{...}` and `XYZctf{...}`; text glued in front
  of a known name (`flag.txtpicoCTF{...}`) is trimmed. A custom regex is used as-is.

The terminal shows at most 15 ranked findings, likely flags first, then notes. Exit code 0 means the sweep ran;
2 means bad arguments or an unreadable input.

If they are installed, stegsweep also runs exiftool (the file goes in on stdin, so a crafted file name cannot
reach it: CVE-2022-23935), binwalk (`-e`, needs `-o` and binwalk 2.3.4 or newer: CVE-2022-4510), steghide
(empty passphrase) and stegseek (with `--wordlist`). Missing tools are skipped with a note.

## How it works

The file is read once (up to 200 MiB) and every check works on those bytes. A check that fails on a broken
file becomes a note; the sweep goes on.

- **Metadata:** PNG text chunks, JPEG comments, XMP and EXIF, searched for flags.
- **Hidden data:** bytes after the PNG `IEND` chunk or the JPEG `EOI` marker (found by walking the structure, so
  EXIF thumbnails do not count), embedded zip, png, jpg, pdf, 7z, gzip and ELF signatures, and printable strings.
  A carved file runs to the next signature (a zip to its end-of-central-directory record), at most 200 MiB in
  total.
- **Inside zips:** embedded zips are opened in memory and every member is searched for flags and text (at most
  50 MiB per member and 200 MiB in all, so zip bombs stop at the cap). Encrypted members are listed with a hint
  to crack them (zip2john, fcrackzip). Members are saved only under `-o`, with generated names.
- **PNG structure:** CRC mismatches, unknown chunks and truncation.
- **LSB sweep (zsteg-style):** for lossless images, every channel order, bit planes 0-2, bits 0-1 together
  (zsteg `b2`, for 3- and 4-channel orders), row or column order, MSB- or LSB-first bit packing; each stream is checked for flags, file signatures and readable text. WAV
  audio gets the same for sample LSBs.
- **Bit planes (stegsolve-style):** all 8 planes of every channel saved as images in the report.
- **External tools:** run without a shell, with a timeout and an absolute input path (exiftool reads stdin);
  their output files are read, never executed.

## Limitations

- LSB extraction scans the first 1 MiB per configuration, and about 14 s goes into a 12 Mpx RGBA image.
- 16-bit images (16-bit PNG, 16-bit TIFF) are reduced to 8 bits first, so their LSBs are not checked.
- No JPEG DCT-domain steg detection except through steghide or stegseek.
- Images over 40 Mpx are refused before decoding; inputs over 200 MiB are refused.
- Ranking is heuristic: a high score means "look here first", not proof.
- Reusing a `-o` directory leaves files from earlier runs on disk; the report lists only the current run.

## Prior art

stegsweep runs the common first checks in one go; for deep work the dedicated tools are better:

- [zsteg](https://github.com/zed-0xff/zsteg): the LSB sweep this copies, with more configurations (Ruby).
- [stegsolve](https://github.com/zardus/ctf-tools/tree/master/stegsolve): interactive bit-plane viewer (Java).
- [binwalk](https://github.com/ReFirmLabs/binwalk): real embedded-file carving and extraction.
- [exiftool](https://exiftool.org/): complete metadata reading.
- [steghide](https://steghide.sourceforge.net/) and [stegseek](https://github.com/RickdeJager/stegseek):
  extraction and fast passphrase cracking for steghide.
- [pngcheck](http://www.libpng.org/pub/png/apps/pngcheck.html): thorough PNG structure checks.
- [Aperi'Solve](https://www.aperisolve.com/): runs many of these tools as a website; the file must be uploaded.

## See also

- [unseen](../unseen): scan text for invisible Unicode used in AI prompt injection.
- [stegsurvive](../stegsurvive): hidden messages that survive social media recompression.

## License

MIT
