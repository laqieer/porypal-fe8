#!/usr/bin/env python3
"""Unit + E2E tests for palette_tool.

Run with ``pytest -v``. The gbagfx round-trip test auto-skips unless a local
``tools/gbagfx`` binary is present (so CI skips it, local runs exercise it).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import palette_tool as pt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_png(path: Path, colours, size=None) -> Path:
    """Write a PNG that tiles ``colours`` across an image; return ``path``."""
    n = len(colours)
    if size is None:
        side = max(2, int(np.ceil(np.sqrt(n))))
        size = (side, side)
    w, h = size
    img = Image.new("RGB", (w, h))
    px = img.load()
    for x in range(w):
        for y in range(h):
            px[x, y] = colours[(x * h + y) % n]
    img.save(path)
    return path


MANY_COLORS = [
    (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
    (255, 0, 255), (0, 255, 255), (255, 255, 255), (0, 0, 0),
    (128, 0, 0), (0, 128, 0), (0, 0, 128), (128, 128, 0),
    (128, 0, 128), (0, 128, 128), (192, 192, 192), (64, 64, 64),
    (200, 100, 50), (50, 100, 200), (100, 200, 50), (220, 20, 60),
]


GBAGFX_DIR = Path("/home/laqieer/fireemblem8u/tools/gbagfx")
# The built binary lives inside the tools/gbagfx directory.
GBAGFX_BIN = GBAGFX_DIR / "gbagfx"


# ---------------------------------------------------------------------------
# JASC .pal I/O
# ---------------------------------------------------------------------------
def test_pal_round_trip(tmp_path):
    colours = [(0, 0, 0), (255, 255, 255), (12, 34, 56), (200, 100, 50)]
    p = tmp_path / "rt.pal"
    pt.write_pal(str(p), colours)
    assert pt.read_pal(str(p)) == colours


def test_write_pal_uses_crlf(tmp_path):
    p = tmp_path / "crlf.pal"
    pt.write_pal(str(p), [(1, 2, 3), (4, 5, 6)])
    raw = p.read_bytes()
    assert raw.startswith(b"JASC-PAL\r\n")
    # Every line ends with CRLF; there must be no bare LF (LF not preceded by CR).
    assert b"\n" in raw
    assert raw.replace(b"\r\n", b"") .find(b"\n") == -1
    # Each physical line terminates with CRLF.
    for line in raw.split(b"\r\n")[:-1]:
        assert b"\n" not in line


def test_write_pal_rejects_empty(tmp_path):
    with pytest.raises(ValueError):
        pt.write_pal(str(tmp_path / "empty.pal"), [])


def test_read_pal_tolerates_trailing_blank_lines(tmp_path):
    p = tmp_path / "blank.pal"
    p.write_bytes(b"JASC-PAL\r\n0100\r\n2\r\n1 2 3\r\n4 5 6\r\n\r\n\r\n")
    assert pt.read_pal(str(p)) == [(1, 2, 3), (4, 5, 6)]


def _write_raw(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_read_pal_bad_magic(tmp_path):
    path = _write_raw(tmp_path, "m.pal", "NOPE-PAL\n0100\n1\n0 0 0\n")
    with pytest.raises(ValueError, match="magic"):
        pt.read_pal(path)


def test_read_pal_bad_version(tmp_path):
    path = _write_raw(tmp_path, "v.pal", "JASC-PAL\n0200\n1\n0 0 0\n")
    with pytest.raises(ValueError, match="version"):
        pt.read_pal(path)


def test_read_pal_bad_count(tmp_path):
    path = _write_raw(tmp_path, "c.pal", "JASC-PAL\n0100\nxx\n0 0 0\n")
    with pytest.raises(ValueError, match="count"):
        pt.read_pal(path)


def test_read_pal_count_exceeds_lines(tmp_path):
    path = _write_raw(tmp_path, "n.pal", "JASC-PAL\n0100\n3\n0 0 0\n1 1 1\n")
    with pytest.raises(ValueError):
        pt.read_pal(path)


def test_read_pal_non_rgb_line(tmp_path):
    path = _write_raw(tmp_path, "rgb.pal", "JASC-PAL\n0100\n1\n1 2\n")
    with pytest.raises(ValueError):
        pt.read_pal(path)


def test_read_pal_rgb_out_of_range(tmp_path):
    path = _write_raw(tmp_path, "oor.pal", "JASC-PAL\n0100\n1\n256 0 0\n")
    with pytest.raises(ValueError, match="range"):
        pt.read_pal(path)


def test_read_pal_negative_component(tmp_path):
    path = _write_raw(tmp_path, "neg.pal", "JASC-PAL\n0100\n1\n-1 0 0\n")
    with pytest.raises(ValueError, match="range"):
        pt.read_pal(path)


def test_read_pal_too_short(tmp_path):
    path = _write_raw(tmp_path, "short.pal", "JASC-PAL\n0100\n")
    with pytest.raises(ValueError):
        pt.read_pal(path)


def test_validate_pal_happy_crlf(tmp_path):
    colours = [(0, 0, 0), (255, 255, 255), (12, 34, 56)]
    p = tmp_path / "valid.pal"
    pt.write_pal(str(p), colours)
    assert pt.validate_pal(str(p)) == colours


def test_validate_pal_rejects_lf_by_default(tmp_path):
    p = tmp_path / "lf.pal"
    p.write_bytes(b"JASC-PAL\n0100\n1\n0 0 0\n")
    with pytest.raises(ValueError, match="LF-only"):
        pt.validate_pal(str(p))


def test_validate_pal_allows_lf_when_requested(tmp_path):
    p = tmp_path / "lf-ok.pal"
    p.write_bytes(b"JASC-PAL\n0100\n1\n0 0 0\n")
    assert pt.validate_pal(str(p), require_crlf=False) == [(0, 0, 0)]


def test_validate_pal_rejects_count_mismatch_extra_entry(tmp_path):
    p = tmp_path / "extra.pal"
    p.write_bytes(b"JASC-PAL\r\n0100\r\n1\r\n0 0 0\r\n1 1 1\r\n")
    with pytest.raises(ValueError, match="header declares 1"):
        pt.validate_pal(str(p))


def test_validate_pal_rejects_count_mismatch_missing_entry(tmp_path):
    p = tmp_path / "missing.pal"
    p.write_bytes(b"JASC-PAL\r\n0100\r\n2\r\n0 0 0\r\n")
    with pytest.raises(ValueError, match="declares 2"):
        pt.validate_pal(str(p))


def test_validate_pal_rejects_more_than_16_by_default(tmp_path):
    p = tmp_path / "too-many.pal"
    pt.write_pal(str(p), [(i, i, i) for i in range(17)])
    with pytest.raises(ValueError, match="exceeds"):
        pt.validate_pal(str(p))


def test_validate_pal_allows_more_than_16_when_requested(tmp_path):
    colours = [(i, i, i) for i in range(17)]
    p = tmp_path / "many-ok.pal"
    pt.write_pal(str(p), colours)
    assert pt.validate_pal(str(p), allow_more_than_16=True) == colours


# ---------------------------------------------------------------------------
# Colour space
# ---------------------------------------------------------------------------
def test_rgb_to_oklab_shape():
    arr = np.array([[0, 0, 0], [255, 255, 255], [10, 20, 30]], dtype=np.uint8)
    lab = pt.rgb_to_oklab(arr)
    assert lab.shape == (3, 3)


def test_rgb_to_oklab_deterministic():
    arr = np.array([[10, 20, 30], [200, 100, 50]], dtype=np.uint8)
    a = pt.rgb_to_oklab(arr)
    b = pt.rgb_to_oklab(arr)
    assert np.array_equal(a, b)


def test_rgb_to_oklab_grayscale_neutral():
    # Grayscale colours should have a (chroma) ~0 and b (chroma) ~0.
    arr = np.array([[0, 0, 0], [64, 64, 64], [128, 128, 128], [255, 255, 255]],
                   dtype=np.uint8)
    lab = pt.rgb_to_oklab(arr)
    assert np.allclose(lab[:, 1], 0.0, atol=1e-6)
    assert np.allclose(lab[:, 2], 0.0, atol=1e-6)


# ---------------------------------------------------------------------------
# Quantize / extract
# ---------------------------------------------------------------------------
def test_quantize_few_colours_returns_exact_set(tmp_path):
    colours = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (10, 20, 30)]
    img = Image.open(make_png(tmp_path / "few.png", colours))
    got = pt.quantize_image(img, 16)
    assert set(got) == set(colours)


def test_quantize_many_colours_bounded(tmp_path):
    img = Image.open(make_png(tmp_path / "many.png", MANY_COLORS))
    got = pt.quantize_image(img, 16)
    assert len(got) <= 16
    for c in got:
        assert len(c) == 3
        for v in c:
            assert isinstance(v, int) and 0 <= v <= 255
    # Snapped to real image colours.
    assert set(got) <= set(MANY_COLORS)


def test_quantize_honours_n_colors(tmp_path):
    img = Image.open(make_png(tmp_path / "n.png", MANY_COLORS))
    got = pt.quantize_image(img, 4)
    assert len(got) <= 4


def test_quantize_deterministic(tmp_path):
    img = Image.open(make_png(tmp_path / "det.png", MANY_COLORS))
    a = pt.quantize_image(img, 8)
    b = pt.quantize_image(img, 8)
    assert a == b


def test_quantize_rejects_zero(tmp_path):
    img = Image.open(make_png(tmp_path / "z.png", MANY_COLORS))
    with pytest.raises(ValueError):
        pt.quantize_image(img, 0)


# ---------------------------------------------------------------------------
# apply_palette
# ---------------------------------------------------------------------------
def test_apply_palette_mode_and_size(tmp_path):
    img = Image.open(make_png(tmp_path / "a.png", MANY_COLORS, size=(8, 8)))
    palette = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 0, 0)]
    out = pt.apply_palette(img, palette)
    assert out.mode == "P"
    assert out.size == img.size


def test_apply_palette_colours_subset_of_palette(tmp_path):
    img = Image.open(make_png(tmp_path / "b.png", MANY_COLORS, size=(8, 8)))
    palette = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255), (0, 0, 0)]
    out = pt.apply_palette(img, palette)
    rgb_out = out.convert("RGB")
    used = {rgb_out.getpixel((x, y))
            for x in range(rgb_out.width) for y in range(rgb_out.height)}
    assert used <= set(palette)
    # Every index must be a valid palette slot.
    idx = np.asarray(out)
    assert idx.max() < len(palette)


def test_apply_palette_rejects_empty(tmp_path):
    img = Image.open(make_png(tmp_path / "e.png", [(1, 2, 3), (4, 5, 6)]))
    with pytest.raises(ValueError):
        pt.apply_palette(img, [])


def test_apply_palette_rejects_too_many(tmp_path):
    img = Image.open(make_png(tmp_path / "t.png", [(1, 2, 3), (4, 5, 6)]))
    palette = [(i % 256, 0, 0) for i in range(257)]
    with pytest.raises(ValueError):
        pt.apply_palette(img, palette)


# ---------------------------------------------------------------------------
# CLI: parser
# ---------------------------------------------------------------------------
def test_parser_extract():
    parser = pt.build_parser()
    args = parser.parse_args(["extract", "in.png", "-o", "out.pal", "-n", "8"])
    assert args.command == "extract"
    assert args.input == "in.png"
    assert args.output == "out.pal"
    assert args.n == 8


def test_parser_apply():
    parser = pt.build_parser()
    args = parser.parse_args(["apply", "in.png", "pal.pal", "-o", "out.png"])
    assert args.command == "apply"
    assert args.input == "in.png"
    assert args.palette == "pal.pal"
    assert args.output == "out.png"


def test_parser_validate():
    parser = pt.build_parser()
    args = parser.parse_args([
        "validate", "--allow-lf", "--allow-more-than-16", "a.pal", "b.pal"
    ])
    assert args.command == "validate"
    assert args.palettes == ["a.pal", "b.pal"]
    assert args.allow_lf is True
    assert args.allow_more_than_16 is True


def test_parser_extract_default_n():
    parser = pt.build_parser()
    args = parser.parse_args(["extract", "in.png", "-o", "out.pal"])
    assert args.n == pt.GBA_MAX_COLORS


# ---------------------------------------------------------------------------
# CLI: main
# ---------------------------------------------------------------------------
def test_main_extract_happy(tmp_path):
    png = make_png(tmp_path / "in.png", MANY_COLORS)
    out = tmp_path / "out.pal"
    rc = pt.main(["extract", str(png), "-o", str(out), "-n", "16"])
    assert rc == 0
    assert out.exists()
    colours = pt.read_pal(str(out))
    assert 1 <= len(colours) <= 16


def test_main_apply_happy(tmp_path):
    png = make_png(tmp_path / "in.png", MANY_COLORS, size=(8, 8))
    pal = tmp_path / "p.pal"
    pt.write_pal(str(pal), [(255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 0, 0)])
    out = tmp_path / "out.png"
    rc = pt.main(["apply", str(png), str(pal), "-o", str(out)])
    assert rc == 0
    assert out.exists()
    assert Image.open(out).mode == "P"


def test_main_extract_bad_n_zero(tmp_path):
    png = make_png(tmp_path / "in.png", MANY_COLORS)
    rc = pt.main(["extract", str(png), "-o", str(tmp_path / "o.pal"), "-n", "0"])
    assert rc == 2


def test_main_extract_bad_n_too_high(tmp_path):
    png = make_png(tmp_path / "in.png", MANY_COLORS)
    rc = pt.main(["extract", str(png), "-o", str(tmp_path / "o.pal"), "-n", "17"])
    assert rc == 2


def test_main_extract_missing_input(tmp_path):
    rc = pt.main(["extract", str(tmp_path / "nope.png"),
                  "-o", str(tmp_path / "o.pal")])
    assert rc == 1


def test_main_apply_missing_palette(tmp_path):
    png = make_png(tmp_path / "in.png", MANY_COLORS)
    rc = pt.main(["apply", str(png), str(tmp_path / "nope.pal"),
                  "-o", str(tmp_path / "o.png")])
    assert rc == 1


def test_main_validate_happy(tmp_path):
    pal = tmp_path / "ok.pal"
    pt.write_pal(str(pal), [(0, 0, 0), (255, 255, 255)])
    assert pt.main(["validate", str(pal)]) == 0


def test_main_validate_multi_file_reports_failure(tmp_path):
    good = tmp_path / "good.pal"
    bad = tmp_path / "bad.pal"
    pt.write_pal(str(good), [(0, 0, 0)])
    bad.write_bytes(b"JASC-PAL\n0100\n1\n0 0 0\n")
    assert pt.main(["validate", str(good), str(bad)]) == 1


# ---------------------------------------------------------------------------
# E2E
# ---------------------------------------------------------------------------
def test_e2e_extract_apply_round_trip(tmp_path):
    png = make_png(tmp_path / "src.png", MANY_COLORS, size=(8, 8))
    pal = tmp_path / "out.pal"
    assert pt.main(["extract", str(png), "-o", str(pal), "-n", "16"]) == 0

    palette = pt.read_pal(str(pal))
    assert 1 <= len(palette) <= 16

    out = tmp_path / "out.png"
    assert pt.main(["apply", str(png), str(pal), "-o", str(out)]) == 0

    indexed = Image.open(out)
    assert indexed.mode == "P"
    rgb_out = indexed.convert("RGB")
    used = {rgb_out.getpixel((x, y))
            for x in range(rgb_out.width) for y in range(rgb_out.height)}
    assert used <= set(palette)


@pytest.mark.skipif(not GBAGFX_DIR.exists(), reason="gbagfx unavailable")
def test_e2e_gbagfx_round_trip(tmp_path):
    import subprocess

    if not GBAGFX_BIN.exists():
        pytest.skip("gbagfx binary not built")

    png = make_png(tmp_path / "src.png", MANY_COLORS, size=(8, 8))
    pal = tmp_path / "out.pal"
    assert pt.main(["extract", str(png), "-o", str(pal), "-n", "16"]) == 0
    # Force exactly 16 colours so the .gbapal is a full 32 bytes.
    palette = pt.read_pal(str(pal))
    while len(palette) < 16:
        palette.append((0, 0, 0))
    pt.write_pal(str(pal), palette)

    gbapal = tmp_path / "out.gbapal"
    subprocess.run([str(GBAGFX_BIN), str(pal), str(gbapal)], check=True)
    assert gbapal.stat().st_size == 32  # 16 colours x 2 bytes (BGR555)
