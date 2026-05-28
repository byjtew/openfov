"""Generate `resources/icons/openfov.ico`.

Run as: `python tools/generate_icon.py`

Designed for the lo-fi visual brand: dark teal disc, big bold "FOV"
wordmark, with a stylized "viewing field" arc sketched behind it. Plays
nicely against both Windows light and dark taskbars.

Drawn entirely procedurally with Pillow — no external bitmaps needed.
The output is a multi-resolution `.ico` (16, 24, 32, 48, 64, 128, 256)
so Windows scales correctly across taskbar, alt-tab, file explorer, and
notification area.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter


# Colors — slightly elevated against grey, OK on light & dark backgrounds.
BG_OUTER = (32, 38, 46, 255)        # deep slate
BG_INNER_TOP = (52, 174, 158, 255)  # teal
BG_INNER_BOT = (34, 102, 122, 255)
HUD_LINE = (190, 240, 230, 200)
TEXT = (240, 248, 250, 255)


def _radial_disc(size: int) -> Image.Image:
    """The dark slate background disc with subtle inner glow."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(1, size // 32)
    draw.ellipse((pad, pad, size - pad, size - pad), fill=BG_OUTER)
    return img


def _inner_disc(size: int) -> Image.Image:
    """Teal inner disc; the visual focal point. Vertical gradient."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(1, size // 8)
    # Build the gradient by stamping concentric ellipses (cheap, no scipy).
    steps = max(8, size // 6)
    for i in range(steps):
        t = i / steps
        r, g, b, a = (
            int(BG_INNER_TOP[0] * (1 - t) + BG_INNER_BOT[0] * t),
            int(BG_INNER_TOP[1] * (1 - t) + BG_INNER_BOT[1] * t),
            int(BG_INNER_TOP[2] * (1 - t) + BG_INNER_BOT[2] * t),
            255,
        )
        bbox = (
            pad + i * (size - 2 * pad) // (2 * steps),
            pad + i * (size - 2 * pad) // steps,
            size - pad - i * (size - 2 * pad) // (2 * steps),
            size - pad,
        )
        draw.ellipse(bbox, fill=(r, g, b, a))
    return img


def _viewing_arc(size: int) -> Image.Image:
    """A field-of-view arc sketched behind the wordmark."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = size // 2
    cy = int(size * 0.62)
    radius = int(size * 0.36)
    width = max(2, size // 64)
    bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
    # FOV cone: arc from ~210 to ~330 degrees (looking down/away).
    draw.arc(bbox, start=210, end=330, fill=HUD_LINE, width=width)
    # Two boundary rays.
    for theta_deg in (210, 330):
        theta = math.radians(theta_deg)
        x2 = cx + int(radius * 1.3 * math.cos(theta))
        y2 = cy + int(radius * 1.3 * math.sin(theta))
        draw.line((cx, cy, x2, y2), fill=HUD_LINE, width=width)
    return img


def _wordmark(size: int) -> Image.Image:
    """Bold 'FOV' lettering centered."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Try a system bold font; fall back to Pillow's default.
    text = "FOV"
    font: ImageFont.ImageFont
    candidates = [
        ("arialbd.ttf", int(size * 0.42)),
        ("ariblk.ttf", int(size * 0.42)),
        ("seguibl.ttf", int(size * 0.42)),
        ("DejaVuSans-Bold.ttf", int(size * 0.42)),
    ]
    font = None  # type: ignore[assignment]
    for name, pt in candidates:
        try:
            font = ImageFont.truetype(name, pt)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    # Center via textbbox (Pillow >=9.2).
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size - tw) // 2 - bbox[0]
    y = int(size * 0.30) - bbox[1]
    draw.text((x, y), text, font=font, fill=TEXT)
    return img


def render(size: int) -> Image.Image:
    """Stack: outer disc -> inner gradient -> arc -> wordmark."""
    canvas = _radial_disc(size)
    canvas = Image.alpha_composite(canvas, _inner_disc(size))
    canvas = Image.alpha_composite(canvas, _viewing_arc(size))
    canvas = Image.alpha_composite(canvas, _wordmark(size))
    # Soft outer shadow / anti-alias polish at small sizes.
    if size <= 32:
        canvas = canvas.filter(ImageFilter.SMOOTH)
    return canvas


def main() -> int:
    out_dir = Path(__file__).resolve().parents[1] / "resources" / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    layers = [render(s) for s in sizes]

    ico_path = out_dir / "openfov.ico"
    # Pillow's ICO writer chooses a base image and embeds resized copies.
    # Passing the 256-px image as the base + sizes for the entry table
    # produces a clean multi-resolution .ico.
    layers[-1].save(ico_path, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"Wrote {ico_path}  ({ico_path.stat().st_size} bytes)")

    # Also dump a 256-px PNG for any docs / README use.
    png_path = out_dir / "openfov.png"
    layers[-1].save(png_path, format="PNG")
    print(f"Wrote {png_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
