# porypal-fe8

A small, FE8-oriented palette CLI for the
[`fireemblem8u`](https://github.com/FireEmblemUniverse/fireemblem8u) decomp
graphics pipeline. It does two things:

- **`extract`** — quantize a PNG down to **≤16 colours** and write a GBA-style
  **JASC `.pal`** palette.
- **`apply`** — remap every pixel of a PNG to its nearest colour in a given
  `.pal` and save an **indexed PNG**, ready for `gbagfx`.

It is a focused, clean reimplementation of the *reusable core* of
[Loxed's Porypal](https://github.com/Loxed/porypal) — k-means colour
quantization in a perceptual colour space (Oklab) plus JASC `.pal` I/O — with
all the Pokémon-specific and UI parts dropped. See
[Credits & license](#credits--license).

## Why this exists (honest note)

For day-to-day FE8 graphics work you usually **do not need this tool**:

- [**Usenti**](https://www.coranac.com/projects/usenti/) handles palette
  editing, reduction, and indexed-PNG export interactively.
- The decomp's own **`gbagfx`** already converts between `.png`, `.pal`,
  `.gbapal`, and `.4bpp`.

`porypal-fe8` is for **batch / automated quantization** — e.g. scripting the
reduction of many full-colour PNGs to 16-colour palettes in a build or asset
pipeline, where a headless CLI is more convenient than a GUI.

## Install

Requires Python 3.9+.

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
# optional: install the `porypal-fe8` console command
pip install .
```

Without installing, you can run the module directly:

```sh
python3 palette_tool.py extract IN.png -o OUT.pal
```

## Usage

### Extract a palette

```sh
porypal-fe8 extract IN.png -o OUT.pal [-n 16]
```

Quantizes `IN.png` to at most `-n` colours (default 16, the GBA 4bpp limit) and
writes a JASC `.pal`:

```
JASC-PAL
0100
16
115 131 164
255 255 255
...
```

### Apply a palette

```sh
porypal-fe8 apply IN.png PALETTE.pal -o OUT.png
```

Remaps every pixel of `IN.png` to the nearest colour in `PALETTE.pal` (nearest
in Oklab) and saves an indexed (`P`-mode) PNG whose colours are exactly the
palette.

## How it fits the FE8 pipeline

The decomp stores graphics as PNGs and JASC `.pal` palettes, and its Makefile
drives `gbagfx` to turn those into the GBA's native formats:

```
            porypal-fe8 extract              gbagfx (pal2gbapal)
   IN.png ───────────────────────▶  OUT.pal ───────────────────▶  .gbapal   (32 bytes for 16 colours)

            porypal-fe8 apply                gbagfx (png2gbagfx)
   IN.png ───────────────────────▶  OUT.png ───────────────────▶  .4bpp
   (+ .pal)                         (indexed)
```

Relevant Makefile rules in the decomp:

```make
%.gbapal: %.pal ; $(PAL2GBAPAL) $< $@
%.gbapal: %.png ; $(GBAGFX) $< $@
```

A 16-colour JASC `.pal` converts to exactly **32 bytes** of `.gbapal`
(16 colours × 2 bytes, the GBA's 15-bit BGR555 format). Palettes are written
with **CRLF** line endings to match the decomp's `.pal` files — `gbagfx`
rejects LF-only palettes. See the
[`fireemblem8u`](https://github.com/FireEmblemUniverse/fireemblem8u) repo and
[`gbagfx`](https://github.com/pret/pokeemerald/tree/master/tools/gbagfx) for the
full graphics flow.

## How it works

- **Quantization** clusters the image's pixels with **k-means++** in **Oklab**,
  a perceptually uniform colour space, so the chosen colours match how the eye
  groups them. Each cluster centre is then snapped to the nearest *actual*
  colour in the source image, so every palette entry really occurs in the PNG.
  If the image already has ≤ N colours, they are kept verbatim.
- **Apply** assigns each pixel to the nearest palette colour, again measured in
  Oklab.

## Credits & license

The colour-quantization approach and JASC `.pal` round-trip are **inspired by**
[Loxed's Porypal](https://github.com/Loxed/porypal). Porypal is licensed under
the **GPL-3.0**, which is incompatible with this project's MIT license, so
**no Porypal source code was copied** — this is an independent reimplementation
of the high-level idea only. Credit and thanks to Loxed.

porypal-fe8 itself is released under the [MIT License](LICENSE).
