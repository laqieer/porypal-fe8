#!/usr/bin/env python3
"""Generate a tiny PNG with >16 distinct colours for the CI extract smoke test.

Kept self-contained (Pillow only) so CI does not depend on the fireemblem8u
decomp or any fixture files. Writes the PNG path given as argv[1] (default
``tmp.png``).
"""

import sys

from PIL import Image

# 20 distinct colours -> forces `extract` to quantize down to <=16.
COLORS = [
    (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
    (255, 0, 255), (0, 255, 255), (255, 255, 255), (0, 0, 0),
    (128, 0, 0), (0, 128, 0), (0, 0, 128), (128, 128, 0),
    (128, 0, 128), (0, 128, 128), (192, 192, 192), (64, 64, 64),
    (200, 100, 50), (50, 100, 200), (100, 200, 50), (220, 20, 60),
]


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "tmp.png"
    img = Image.new("RGB", (8, 8))
    px = img.load()
    for x in range(8):
        for y in range(8):
            px[x, y] = COLORS[(x * 8 + y) % len(COLORS)]
    img.save(out)
    print(f"generated {out} ({len(COLORS)} distinct colours)")


if __name__ == "__main__":
    main()
