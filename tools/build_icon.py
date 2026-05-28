"""Generate `resources/icons/openfov.ico` from the FOV-cone logo concept.

Why this script exists
----------------------
The brand mark is the FOV-cone concept that was approved during the
logo selection pass — a dark rounded-square tile holding a head circle
silhouette and a translucent teal field-of-view cone projecting from
the front of the face.

We render it directly with Pillow's `ImageDraw` (rather than rasterizing
the SVG via cairosvg/rsvg) for two reasons:

1. No extra system dependency — Pillow ships with the runtime venv.
2. Every ICO sub-image is drawn natively at its target size, so the
   shapes stay crisp at 16 / 24 / 32 / 48 / 64 / 128 / 256 px. A single
   high-res raster downsampled to 16 px would muddy the cone outline.

Run via:
    python tools/build_icon.py

Output: `resources/icons/openfov.ico`. The script also dumps a 256 px
PNG next to it as a debugging aid.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


# Source viewBox of the concept SVG (concept-1-fov-cone). We render to
# arbitrary pixel sizes by scaling these coordinates uniformly.
_VBX = 256

# Geometry in the source viewBox. Every value here was hand-tuned in
# the SVG and copied verbatim — keep this in sync if the SVG changes.
_TILE_RADIUS = 40
# Everything is shifted ~6 px left so the head+cone composition is
# horizontally centered in the 256-px canvas. Without this the head sits
# noticeably right of center because the cone's reach extends almost to
# the tile's right edge.
_HEAD_CX, _HEAD_CY, _HEAD_R = 86, 128, 52
_CONE_APEX = (99, 128)
# Wider FOV cone: ~68° total angle. Earlier 44° version felt cramped.
_CONE_TOP = (226, 45)
_CONE_BOT = (226, 211)

# Colors (RGBA). The cone fill is teal at ~18% alpha so the tile color
# shows through faintly — same effect as the SVG's fill-opacity.
_BG = (82, 90, 100, 255)           # #525a64 — neutral mid-grey tile
_HEAD_FILL = (10, 13, 16, 255)     # #0a0d10
_HEAD_STROKE = (255, 255, 255, 255)  # pure #ffffff for max pop
# Cone is now a *solid* teal block (was 18% alpha) with a darker teal
# outline framing it — same hue family, much higher visual weight.
_CONE_FILL = (52, 174, 158, 255)              # #34ae9e — bright teal
_CONE_STROKE = (31, 119, 104, 255)            # #1f7768 — darker teal


def _scaled(value: float, size: int) -> float:
    """Map a coordinate from the 256-unit viewBox to the target size."""
    return value * size / _VBX


def render(size: int) -> Image.Image:
    """Render the logo at `size x size`.

    Strategy: draw at 4x the target into an RGBA buffer with antialiased
    geometry, then downsample with Lanczos. The 4x oversample gives the
    cone outline the cleanest edge at small icon sizes — Pillow's
    `ImageDraw` doesn't natively antialias `polygon`/`line`, so this is
    how we get smooth slopes.
    """
    scale = 4
    work = size * scale
    img = Image.new("RGBA", (work, work), (0, 0, 0, 0))

    # Separate alpha-composited layers per shape — keeps the cone's
    # translucent fill from contaminating the head fill where they
    # overlap.
    tile = Image.new("RGBA", (work, work), (0, 0, 0, 0))
    cone = Image.new("RGBA", (work, work), (0, 0, 0, 0))
    head = Image.new("RGBA", (work, work), (0, 0, 0, 0))

    # --- tile (rounded square background) ---
    d = ImageDraw.Draw(tile)
    r = round(_scaled(_TILE_RADIUS, work))
    d.rounded_rectangle(
        (0, 0, work - 1, work - 1),
        radius=r,
        fill=_BG,
    )

    # --- cone (fill + outlines) ---
    d = ImageDraw.Draw(cone)
    apex = (_scaled(_CONE_APEX[0], work), _scaled(_CONE_APEX[1], work))
    top = (_scaled(_CONE_TOP[0], work), _scaled(_CONE_TOP[1], work))
    bot = (_scaled(_CONE_BOT[0], work), _scaled(_CONE_BOT[1], work))
    d.polygon([apex, top, bot], fill=_CONE_FILL)
    # Stroke the two slanted edges (the right side is implicit at the
    # edge of the tile, so we don't draw it — matches the SVG). Stroke
    # weights sit between "subtle" and "billboard" (cone 8 px @ 256,
    # head 7 px @ 256) so the silhouette reads clearly at icon sizes
    # without feeling chunky on the larger renders.
    stroke_w = max(3, round(_scaled(8, work)))
    d.line([apex, top], fill=_CONE_STROKE, width=stroke_w)
    d.line([apex, bot], fill=_CONE_STROKE, width=stroke_w)

    # --- head circle (fill + stroke) ---
    d = ImageDraw.Draw(head)
    cx, cy = _scaled(_HEAD_CX, work), _scaled(_HEAD_CY, work)
    rad = _scaled(_HEAD_R, work)
    head_stroke_w = max(3, round(_scaled(7, work)))
    bbox = (cx - rad, cy - rad, cx + rad, cy + rad)
    d.ellipse(bbox, fill=_HEAD_FILL, outline=_HEAD_STROKE, width=head_stroke_w)

    # Composite in source order so the cone sits over the tile and the
    # head sits over the cone (the cone's apex is "behind" the head
    # outline, but we want the head fill to mask the cone — drawing
    # head last achieves that).
    img = Image.alpha_composite(img, tile)
    img = Image.alpha_composite(img, cone)
    img = Image.alpha_composite(img, head)

    # Downsample to the requested size. Lanczos is the right kernel
    # for "I have a high-quality source and want a sharp small icon."
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "resources" / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)
    ico_path = out_dir / "openfov.ico"
    png_path = out_dir / "openfov.png"

    # Windows ICO container sizes — each gets its own native draw so
    # small ones don't muddy from a downsampled large raster.
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [render(s) for s in sizes]

    # The largest image is the "primary" — Pillow saves the rest as
    # additional sub-images via the `sizes` parameter on the primary.
    primary = images[-1]
    primary.save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
    )

    # Dump a standalone PNG for previewing without an ICO viewer.
    primary.save(png_path, format="PNG")

    print(f"Wrote {ico_path} ({ico_path.stat().st_size} bytes)")
    print(f"Wrote {png_path} ({png_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
