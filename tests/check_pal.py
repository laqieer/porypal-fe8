#!/usr/bin/env python3
"""Validate that a file is a well-formed JASC palette with <=16 colours.

Self-contained (no project imports) so it independently checks the output of
``porypal-fe8 extract``. Exits non-zero with a message on any failure.
Reads the path given as argv[1] (default ``tmp.pal``).
"""

import sys

MAX_COLORS = 16


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "tmp.pal"
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    while lines and lines[-1].strip() == "":
        lines.pop()

    assert len(lines) >= 3, f"{path}: too short to be a JASC palette"
    assert lines[0] == "JASC-PAL", f"{path}: bad magic header {lines[0]!r}"
    assert lines[1] == "0100", f"{path}: bad version {lines[1]!r}"

    count = int(lines[2])
    assert count <= MAX_COLORS, (
        f"{path}: header declares {count} colours (> {MAX_COLORS})"
    )

    colour_lines = lines[3:]
    assert len(colour_lines) == count, (
        f"{path}: header says {count} colours but {len(colour_lines)} present"
    )

    for i, line in enumerate(colour_lines, 1):
        parts = line.split()
        assert len(parts) == 3, f"{path}: colour line {i} is not 'R G B': {line!r}"
        for p in parts:
            v = int(p)
            assert 0 <= v <= 255, f"{path}: component {v} on line {i} out of 0..255"

    print(f"{path}: valid JASC palette with {count} colours (<= {MAX_COLORS})")


if __name__ == "__main__":
    main()
