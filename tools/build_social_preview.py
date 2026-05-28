"""Generate the 1280×640 social preview banner for GitHub / X / Discord.

GitHub uses this exact size; it's also what most other link-preview
consumers crop to. The banner has the FOV-cone mark on the left, the
project name + one-line tagline in the middle, and the repo URL in the
bottom-right corner. Mid-grey background matches the icon tile so the
brand stays consistent across the icon, taskbar, and social shares.

Saved to `.github/social-preview.png`. Upload via repo Settings →
General → Social preview → Edit.

Run via:
    python tools/build_social_preview.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# Output size — GitHub's recommended dimensions for repo social preview.
_W, _H = 1280, 640

# Match the icon palette.
_BG = (82, 90, 100, 255)            # #525a64 — same tile color as the .ico
_HEAD_FILL = (10, 13, 16, 255)
_HEAD_STROKE = (255, 255, 255, 255)
_CONE_FILL = (52, 174, 158, 255)    # solid teal
_CONE_STROKE = (31, 119, 104, 255)  # darker teal
_TITLE_FG = (240, 244, 248, 255)
_TAGLINE_FG = (180, 188, 196, 255)
_FOOTER_FG = (120, 130, 140, 255)


def _try_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Find a sensible system font. Falls back to Pillow's default if
    nothing is available (rare on Windows). We try Segoe UI first to
    match the in-app Qt look."""
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _draw_logo(img: Image.Image, cx: int, cy: int, scale: float) -> None:
    """Render the FOV-cone mark centered on (cx, cy). Geometry mirrors
    build_icon.py but at a different scale; we keep them in lockstep
    by hand since the icon canvas and the banner have different
    aspect ratios and absolute size."""

    # Coordinates in the original 256-px icon viewBox.
    head_cx, head_cy, head_r = 86, 128, 52
    cone_apex = (99, 128)
    cone_top = (226, 45)
    cone_bot = (226, 211)
    # Center the design at (128, 128) within the viewBox; offset to (cx, cy).
    def s(x: float, y: float) -> tuple[float, float]:
        return (cx + (x - 128) * scale, cy + (y - 128) * scale)

    cone = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(cone)
    apex = s(*cone_apex)
    top = s(*cone_top)
    bot = s(*cone_bot)
    d.polygon([apex, top, bot], fill=_CONE_FILL)
    stroke_w = max(3, int(round(8 * scale)))
    d.line([apex, top], fill=_CONE_STROKE, width=stroke_w)
    d.line([apex, bot], fill=_CONE_STROKE, width=stroke_w)

    head = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(head)
    hx, hy = s(head_cx, head_cy)
    hr = head_r * scale
    head_stroke_w = max(3, int(round(7 * scale)))
    d.ellipse(
        (hx - hr, hy - hr, hx + hr, hy + hr),
        fill=_HEAD_FILL,
        outline=_HEAD_STROKE,
        width=head_stroke_w,
    )

    img.alpha_composite(cone)
    img.alpha_composite(head)


def main() -> None:
    img = Image.new("RGBA", (_W, _H), _BG)

    # Left third: FOV-cone logo. Scale 1.3 makes it ~440 px wide,
    # leaving ~770 px for text on the right.
    _draw_logo(img, cx=320, cy=320, scale=1.6)

    # Right two-thirds: title + tagline. Anchored at x=620 so the text
    # column has consistent left alignment.
    d = ImageDraw.Draw(img)
    text_x = 620

    title = "OpenFOV"
    title_font = _try_font(124, bold=True)
    d.text((text_x, 200), title, fill=_TITLE_FG, font=title_font)

    # Tagline: one line, sized to comfortably fit the column to the
    # right of the logo. 32pt with Segoe UI fits "Webcam head tracking
    # for iRacing" in well under 600 px.
    tagline = "Webcam head tracking for iRacing"
    tagline_font = _try_font(34)
    d.text((text_x, 370), tagline, fill=_TAGLINE_FG, font=tagline_font)

    # Footer URL — small, lower-right.
    footer_font = _try_font(24)
    footer = "github.com/epalosh/openfov"
    footer_bbox = d.textbbox((0, 0), footer, font=footer_font)
    footer_w = footer_bbox[2] - footer_bbox[0]
    d.text(
        (_W - footer_w - 40, _H - 50),
        footer,
        fill=_FOOTER_FG,
        font=footer_font,
    )

    out = Path(__file__).resolve().parent.parent / ".github" / "social-preview.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, format="PNG", optimize=True)
    print(f"Wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
