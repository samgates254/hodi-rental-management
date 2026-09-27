"""Generate crisp multi-resolution Hodi brand marks (PNG + SVG)."""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parents[1] / "public" / "brand"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CHARCOAL = (25, 32, 42, 255)  # #19202A
TEAL = (11, 172, 170, 255)  # #0BACAA


def draw_mark(size: int) -> Image.Image:
    """
    Hodi mark on a 0–100 design grid, rendered at `size` px.

    Geometry mirrors the provided brand asset:
    - charcoal H pillars with shallow roof cuts on the upper blocks
    - teal operational ribbon through the counter-space
    """
    s = float(size)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    def poly(pts: list[tuple[float, float]], color: tuple[int, int, int, int]) -> None:
        draw.polygon([(x / 100.0 * s, y / 100.0 * s) for x, y in pts], fill=color)

    # Left upper — roof peak on outer edge
    poly([(6, 14), (10, 6), (40, 6), (40, 42), (6, 42)], CHARCOAL)

    # Left lower
    poly([(6, 52), (34, 52), (34, 94), (6, 94)], CHARCOAL)

    # Right upper — roof peak on outer edge
    poly([(60, 6), (90, 6), (94, 14), (94, 42), (60, 42)], CHARCOAL)

    # Right lower
    poly([(66, 52), (94, 52), (94, 94), (66, 94)], CHARCOAL)

    # Teal ribbon — crossbar + descending path (brand signature)
    poly(
        [
            (14, 34),
            (40, 34),
            (40, 42),
            (60, 42),
            (60, 34),
            (86, 34),
            (86, 52),
            (66, 52),
            (66, 58),
            (78, 70),
            (78, 88),
            (58, 88),
            (58, 70),
            (50, 60),
            (50, 52),
            (40, 52),
            (40, 60),
            (28, 72),
            (18, 60),
            (18, 52),
            (14, 52),
        ],
        TEAL,
    )

    return img


def supersample(size: int, factor: int = 8) -> Image.Image:
    big = draw_mark(size * factor)
    return big.resize((size, size), Image.Resampling.LANCZOS)


SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" fill="none" role="img" aria-label="Hodi">
  <title>Hodi</title>
  <!-- Left upper -->
  <path fill="#19202A" d="M6 14 L10 6 H40 V42 H6 Z"/>
  <!-- Left lower -->
  <path fill="#19202A" d="M6 52 H34 V94 H6 Z"/>
  <!-- Right upper -->
  <path fill="#19202A" d="M60 6 H90 L94 14 V42 H60 Z"/>
  <!-- Right lower -->
  <path fill="#19202A" d="M66 52 H94 V94 H66 Z"/>
  <!-- Teal ribbon -->
  <path fill="#0BACAA" d="
    M14 34 H40 V42 H60 V34 H86 V52 H66
    V58 L78 70 V88 H58 V70 L50 60 V52
    H40 V60 L28 72 L18 60 V52 H14 Z"/>
</svg>
"""


def main() -> None:
    (OUT_DIR / "hodi-mark.svg").write_text(SVG, encoding="utf-8")
    print("wrote", OUT_DIR / "hodi-mark.svg")

    for size, name in [
        (64, "hodi-mark-64.png"),
        (128, "hodi-mark-128.png"),
        (256, "hodi-mark-256.png"),
        (512, "hodi-mark-512.png"),
        (1024, "hodi-mark-1024.png"),
    ]:
        im = supersample(size, factor=8)
        path = OUT_DIR / name
        im.save(path, "PNG", optimize=True)
        print("wrote", path, im.size, path.stat().st_size)

    master = supersample(512, factor=8)
    master_path = OUT_DIR / "hodi-mark.png"
    master.save(master_path, "PNG", optimize=True)
    print("wrote", master_path, master.size)


if __name__ == "__main__":
    main()
