# Practice challenges

Five small files, each hiding one flag with a different technique. Try to find each flag yourself first, then
run `stegsweep` on it. Every cover picture is drawn by [`make_examples.py`](make_examples.py), so the files are
free to share and you can regenerate them with `python examples/make_examples.py` (needs Pillow).

| File | Size | Hint |
|---|---|---|
| [01-sky.png](01-sky.png) | 2.6 KB | The picture is fine. Some of its pixels are lying a tiny bit. |
| [02-sunset.jpg](02-sunset.jpg) | 7.7 KB | The image ends before the file does. |
| [03-night.png](03-night.png) | 2.4 KB | Someone left a note, but `strings` will not show it. |
| [04-beep.wav](04-beep.wav) | 15.7 KB | Listen closely to the quietest bit. |
| [05-mountains.jpg](05-mountains.jpg) | 7.3 KB | Ask the camera. Mind the text encoding. |

<details>
<summary>01-sky.png: technique and flag</summary>

Least significant bit of each R, G, B value, read row by row, most significant bit first (zsteg `b1,rgb,lsb,xy`).
Flag: `flag{lsb_in_the_sky}`
</details>

<details>
<summary>02-sunset.jpg: technique and flag</summary>

A deflated zip archive is appended after the JPEG end-of-image marker; `flag.txt` inside holds the flag. Because
the zip is compressed, the flag is not visible in the raw bytes.
Flag: `picoCTF{z1p_4ft3r_th3_3nd}`
</details>

<details>
<summary>03-night.png: technique and flag</summary>

A compressed PNG text chunk (`zTXt`) named `Comment`.
Flag: `CTF{c0mpr3ss3d_c0mm3nts}`
</details>

<details>
<summary>04-beep.wav: technique and flag</summary>

Least significant bit of each 16-bit audio sample, most significant bit first.
Flag: `flag{l1st3n_t0_th3_l0w_b1ts}`
</details>

<details>
<summary>05-mountains.jpg: technique and flag</summary>

The Windows `XPComment` EXIF tag, stored as UTF-16, so the flag is not a plain ASCII string.
Flag: `HTB{3x1f_t4lk5_t00}`
</details>
