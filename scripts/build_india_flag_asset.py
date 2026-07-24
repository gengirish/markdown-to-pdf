#!/usr/bin/env python3
"""Render a public-domain Flag of India PNG with an authentic 24-spoke Ashoka
Chakra, for embedding in the sports handout certificate (xhtml2pdf cannot
rasterise SVG, so we ship a PNG asset).

The design follows the flag specification: three equal horizontal bands
(India saffron / white / India green) in a 3:2 ratio, with a navy-blue
24-spoke Ashoka Chakra centred on the white band at 3/4 of the band height.

Drawn at 4x and downsampled with LANCZOS for smooth, anti-aliased edges.

Usage:
    python scripts/build_india_flag_asset.py
    python scripts/build_india_flag_asset.py --out public/branding/india-flag.png --width 900
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent

SAFFRON = (255, 153, 51)     # #FF9933
WHITE = (255, 255, 255)
GREEN = (19, 136, 8)         # #138808
NAVY = (0, 0, 128)           # #000080  Ashoka Chakra


def draw_chakra(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float) -> None:
    """24-spoke Ashoka Chakra centred at (cx, cy) with outer radius r."""
    rim_w = max(int(r * 0.055), 1)
    # Outer rim.
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=NAVY, width=rim_w)
    # Hub.
    hub = r * 0.14
    draw.ellipse([cx - hub, cy - hub, cx + hub, cy + hub], fill=NAVY)
    # 24 spokes + rim dots between them.
    spoke_w = max(int(r * 0.028), 1)
    inner = r * 0.90
    dot_r = r * 0.035
    for i in range(24):
        ang = math.radians(i * 15.0)
        c, s = math.cos(ang), math.sin(ang)
        draw.line(
            [cx + hub * c, cy + hub * s, cx + inner * c, cy + inner * s],
            fill=NAVY, width=spoke_w,
        )
        # Small rim pin, offset half a step, sitting just inside the rim.
        dang = math.radians(i * 15.0 + 7.5)
        dc, ds = math.cos(dang), math.sin(dang)
        dx, dy = cx + inner * dc, cy + inner * ds
        draw.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r], fill=NAVY)


def build_flag(width: int = 900) -> Image.Image:
    scale = 4
    W = width * scale
    H = int(W * 2 / 3)  # 3:2 flag ratio
    band = H // 3
    img = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, band], fill=SAFFRON)
    draw.rectangle([0, band, W, 2 * band], fill=WHITE)
    draw.rectangle([0, 2 * band, W, H], fill=GREEN)
    # Chakra: 3/4 of the white-band height.
    r = (band * 0.75) / 2
    draw_chakra(draw, W / 2, band * 1.5, r)
    # Thin outer keyline so the flag reads on a light page.
    draw.rectangle([0, 0, W - 1, H - 1], outline=(210, 210, 210), width=scale)
    return img.resize((width, int(width * 2 / 3)), Image.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="public/branding/india-flag.png")
    parser.add_argument("--width", type=int, default=900)
    args = parser.parse_args()
    out = (REPO_ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    build_flag(args.width).save(out, format="PNG", optimize=True)
    print(f"Wrote {out}  ({out.stat().st_size / 1024:.0f} KB, {args.width}px wide)")


if __name__ == "__main__":
    main()
