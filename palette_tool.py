#!/usr/bin/env python3
"""porypal-fe8: an FE8-oriented palette tool.

A focused command-line tool for the ``fireemblem8u`` decomp graphics pipeline.
It does two things:

* ``extract`` -- quantize a PNG down to <=16 representative colours and write a
  GBA-style JASC ``.pal`` palette (the format the decomp's hundreds of ``.pal``
  files use, which ``tools/gbagfx`` converts to ``.gbapal``).
* ``apply`` -- remap every pixel of a PNG to its nearest colour in a given
  ``.pal`` and save an indexed PNG (ready for ``gbagfx`` to turn into ``.4bpp``).

The colour-quantization idea (k-means over pixels in a perceptual colour space)
and the JASC ``.pal`` round-trip are inspired by Loxed's Porypal
(https://github.com/Loxed/porypal). Porypal is GPL-3.0 and Pokemon-specific;
this is a clean, independent reimplementation of just that reusable core,
distributed under the MIT license. Credit to Loxed for the approach.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Sequence, Tuple

import numpy as np
from PIL import Image

# Maximum number of colours in a GBA 16-colour (4bpp) palette.
GBA_MAX_COLORS = 16

RGB = Tuple[int, int, int]


# ---------------------------------------------------------------------------
# JASC .pal I/O
# ---------------------------------------------------------------------------
def read_pal(path: str) -> List[RGB]:
    """Read a JASC-PAL file and return a list of (R, G, B) tuples.

    The JASC format is::

        JASC-PAL
        0100
        <count>
        R G B
        ...

    Raises ValueError if the file is not a well-formed JASC palette.
    """
    with open(path, "r", encoding="utf-8") as fh:
        lines = [line.strip() for line in fh.read().splitlines()]

    # Drop trailing blank lines (decomp pals often end with one).
    while lines and lines[-1] == "":
        lines.pop()

    if len(lines) < 3:
        raise ValueError(f"{path}: too short to be a JASC palette")
    if lines[0] != "JASC-PAL":
        raise ValueError(f"{path}: missing 'JASC-PAL' magic header")
    if lines[1] != "0100":
        raise ValueError(f"{path}: unexpected version '{lines[1]}' (expected 0100)")

    try:
        count = int(lines[2])
    except ValueError as exc:
        raise ValueError(f"{path}: invalid colour count '{lines[2]}'") from exc

    colour_lines = lines[3:]
    if len(colour_lines) < count:
        raise ValueError(
            f"{path}: header declares {count} colours but only "
            f"{len(colour_lines)} colour lines are present"
        )

    colours: List[RGB] = []
    for i in range(count):
        parts = colour_lines[i].split()
        if len(parts) != 3:
            raise ValueError(
                f"{path}: colour line {i + 1} ('{colour_lines[i]}') is not 'R G B'"
            )
        try:
            r, g, b = (int(p) for p in parts)
        except ValueError as exc:
            raise ValueError(
                f"{path}: colour line {i + 1} has non-integer component"
            ) from exc
        for value, name in ((r, "R"), (g, "G"), (b, "B")):
            if not 0 <= value <= 255:
                raise ValueError(
                    f"{path}: {name}={value} on colour line {i + 1} out of range 0..255"
                )
        colours.append((r, g, b))

    return colours


def write_pal(path: str, colours: Sequence[RGB]) -> None:
    """Write a list of (R, G, B) tuples to a JASC-PAL file.

    Uses CRLF (``\\r\\n``) line endings: that is what the decomp's ``.pal``
    files use, and ``gbagfx`` rejects LF-only palettes ("LF line endings aren't
    supported"). ``newline=""`` stops Python from re-translating them.
    """
    if not colours:
        raise ValueError("refusing to write an empty palette")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("JASC-PAL\r\n")
        fh.write("0100\r\n")
        fh.write(f"{len(colours)}\r\n")
        for r, g, b in colours:
            fh.write(f"{r} {g} {b}\r\n")


# ---------------------------------------------------------------------------
# Colour space: sRGB <-> Oklab
# ---------------------------------------------------------------------------
# Oklab (https://bottosson.github.io/posts/oklab/) is a perceptually uniform
# colour space, so Euclidean distance in it matches human perception far better
# than raw RGB. We cluster and find nearest colours in Oklab.
def _srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    """Convert sRGB in [0, 1] to linear-light RGB."""
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def rgb_to_oklab(rgb_u8: np.ndarray) -> np.ndarray:
    """Convert an (N, 3) array of 0..255 sRGB values to (N, 3) Oklab."""
    rgb = _srgb_to_linear(rgb_u8.astype(np.float64) / 255.0)
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]

    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

    l_ = np.cbrt(l)
    m_ = np.cbrt(m)
    s_ = np.cbrt(s)

    return np.stack(
        [
            0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
        ],
        axis=1,
    )


# ---------------------------------------------------------------------------
# K-means quantization
# ---------------------------------------------------------------------------
def _kmeans(
    points: np.ndarray,
    k: int,
    *,
    weights: np.ndarray | None = None,
    seed: int = 0,
    max_iter: int = 100,
) -> np.ndarray:
    """Run weighted k-means on (N, D) points; return (k, D) cluster centres.

    ``weights`` (length N, default all-ones) lets a single point stand in for
    many identical ones -- e.g. clustering an image's distinct colours weighted
    by how many pixels have each, which is equivalent to clustering every pixel
    but far cheaper. Uses k-means++ seeding for stable, good-quality centres.
    ``k`` is clamped to the number of distinct points so we never produce empty
    clusters.
    """
    rng = np.random.default_rng(seed)
    n = points.shape[0]
    k = min(k, n)
    if weights is None:
        weights = np.ones(n, dtype=np.float64)

    # k-means++ initialisation (sampling weighted by D^2 * pixel count).
    centres = np.empty((k, points.shape[1]), dtype=points.dtype)
    centres[0] = points[rng.integers(n)]
    closest_sq = np.sum((points - centres[0]) ** 2, axis=1)
    for i in range(1, k):
        scored = closest_sq * weights
        total = scored.sum()
        if total <= 0:
            # All remaining points coincide with chosen centres; pad arbitrarily.
            centres[i] = points[rng.integers(n)]
        else:
            centres[i] = points[rng.choice(n, p=scored / total)]
        new_dist = np.sum((points - centres[i]) ** 2, axis=1)
        closest_sq = np.minimum(closest_sq, new_dist)

    labels = np.zeros(n, dtype=np.int64)
    for _ in range(max_iter):
        # Assign each point to the nearest centre.
        dists = np.sum((points[:, None, :] - centres[None, :, :]) ** 2, axis=2)
        new_labels = np.argmin(dists, axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        # Recompute centres as the weighted mean of their members; keep empties put.
        for c in range(k):
            mask = labels == c
            w = weights[mask]
            wsum = w.sum()
            if wsum > 0:
                centres[c] = (points[mask] * w[:, None]).sum(axis=0) / wsum

    return centres


def quantize_image(img: Image.Image, n_colors: int) -> List[RGB]:
    """Return up to ``n_colors`` representative RGB colours for ``img``.

    Clusters the image's distinct colours -- weighted by how many pixels carry
    each, so common colours dominate -- in Oklab for perceptual accuracy, then
    maps each centre back to the nearest *actual* image colour so every palette
    entry exists in the source. Weighting the distinct colours is equivalent to
    clustering every pixel but costs only as much as the (small) palette of
    distinct colours.
    """
    if n_colors < 1:
        raise ValueError("n_colors must be >= 1")

    rgb = np.asarray(img.convert("RGB"), dtype=np.uint8).reshape(-1, 3)
    unique, counts = np.unique(rgb, axis=0, return_counts=True)

    if len(unique) <= n_colors:
        # Already within budget -- keep every colour, sorted for determinism.
        ordered = unique[np.lexsort((unique[:, 2], unique[:, 1], unique[:, 0]))]
        return [tuple(int(v) for v in row) for row in ordered]

    # Cluster the distinct colours, weighted by pixel frequency, in Oklab space.
    unique_lab = rgb_to_oklab(unique)
    centres_lab = _kmeans(unique_lab, n_colors, weights=counts.astype(np.float64))

    # Snap each cluster centre to the nearest real image colour (in Oklab).
    palette: List[RGB] = []
    seen = set()
    for centre in centres_lab:
        idx = int(np.argmin(np.sum((unique_lab - centre) ** 2, axis=1)))
        colour = tuple(int(v) for v in unique[idx])
        if colour not in seen:
            seen.add(colour)
            palette.append(colour)

    palette.sort()
    return palette


# ---------------------------------------------------------------------------
# Apply a palette to an image
# ---------------------------------------------------------------------------
def apply_palette(img: Image.Image, palette: Sequence[RGB]) -> Image.Image:
    """Remap every pixel of ``img`` to its nearest palette colour (in Oklab).

    Returns a paletted ('P' mode) image whose colours are exactly ``palette``,
    so ``gbagfx`` can convert it to indexed GBA graphics.
    """
    if not palette:
        raise ValueError("cannot apply an empty palette")
    if len(palette) > 256:
        raise ValueError("a paletted PNG supports at most 256 colours")

    rgb = np.asarray(img.convert("RGB"), dtype=np.uint8)
    h, w, _ = rgb.shape
    flat = rgb.reshape(-1, 3)

    pal_arr = np.asarray(palette, dtype=np.uint8)
    pixels_lab = rgb_to_oklab(flat)
    pal_lab = rgb_to_oklab(pal_arr)

    dists = np.sum((pixels_lab[:, None, :] - pal_lab[None, :, :]) ** 2, axis=2)
    indices = np.argmin(dists, axis=1).astype(np.uint8)

    out = Image.fromarray(indices.reshape(h, w), mode="P")
    # PIL palettes hold 256 entries; pad the unused tail with zeros.
    flat_palette: List[int] = []
    for r, g, b in palette:
        flat_palette.extend((r, g, b))
    flat_palette.extend([0] * (256 * 3 - len(flat_palette)))
    out.putpalette(flat_palette)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cmd_extract(args: argparse.Namespace) -> int:
    if not 1 <= args.n <= GBA_MAX_COLORS:
        print(
            f"error: -n must be between 1 and {GBA_MAX_COLORS} "
            f"(a GBA 4bpp palette holds at most {GBA_MAX_COLORS} colours)",
            file=sys.stderr,
        )
        return 2
    img = Image.open(args.input)
    palette = quantize_image(img, args.n)
    write_pal(args.output, palette)
    print(f"wrote {args.output}: {len(palette)} colours")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    palette = read_pal(args.palette)
    img = Image.open(args.input)
    out = apply_palette(img, palette)
    out.save(args.output)
    print(f"wrote {args.output}: remapped to {len(palette)} palette colours")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="porypal-fe8",
        description="FE8 palette tool: PNG <-> 16-colour JASC .pal.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_extract = sub.add_parser(
        "extract",
        help="quantize a PNG to <=16 colours and write a JASC .pal",
    )
    p_extract.add_argument("input", help="input PNG path")
    p_extract.add_argument("-o", "--output", required=True, help="output .pal path")
    p_extract.add_argument(
        "-n",
        type=int,
        default=GBA_MAX_COLORS,
        help=f"max colours (1..{GBA_MAX_COLORS}, default {GBA_MAX_COLORS})",
    )
    p_extract.set_defaults(func=cmd_extract)

    p_apply = sub.add_parser(
        "apply",
        help="remap a PNG to a .pal palette and save an indexed PNG",
    )
    p_apply.add_argument("input", help="input PNG path")
    p_apply.add_argument("palette", help="JASC .pal path")
    p_apply.add_argument("-o", "--output", required=True, help="output PNG path")
    p_apply.set_defaults(func=cmd_apply)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
