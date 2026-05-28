"""Generate `docs/smartscreen.png` — a labeled mockup of the Windows
SmartScreen 'Windows protected your PC' dialog. We use this until
someone captures a real screenshot during install. Looks close enough
to the actual UI that users recognize it.

Run as: `python tools/generate_smartscreen_mockup.py`
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 700
HEIGHT = 360
BG = (250, 250, 252, 255)
PANEL = (255, 255, 255, 255)
HEADER = (32, 32, 32, 255)
BODY = (60, 60, 60, 255)
LINK = (0, 99, 177, 255)
ACCENT = (32, 87, 156, 255)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Try a stack of Segoe UI / DejaVu / default."""
    candidates = [
        ("segoeuib.ttf" if bold else "segoeui.ttf", size),
        ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size),
        ("arial.ttf", size),
    ]
    for name, pt in candidates:
        try:
            return ImageFont.truetype(name, pt)
        except OSError:
            continue
    return ImageFont.load_default()


def render() -> Image.Image:
    img = Image.new("RGBA", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)

    # Card shadow.
    card_rect = (40, 28, WIDTH - 40, HEIGHT - 28)
    shadow_rect = (44, 36, WIDTH - 36, HEIGHT - 20)
    d.rectangle(shadow_rect, fill=(220, 220, 224, 255))
    d.rectangle(card_rect, fill=PANEL)

    title_font = _font(20, bold=True)
    body_font = _font(13)
    link_font = _font(13, bold=True)
    button_font = _font(13, bold=True)

    # Title.
    d.text((68, 58), "Windows protected your PC", font=title_font, fill=HEADER)

    # Body text.
    body = (
        "Microsoft Defender SmartScreen prevented an unrecognized\n"
        "app from starting. Running this app might put your PC at risk.\n\n"
        "App:       OpenFOV-0.9.0-setup.exe\n"
        "Publisher: Unknown publisher"
    )
    d.multiline_text((68, 100), body, font=body_font, fill=BODY, spacing=6)

    # "More info" link.
    d.text((68, 232), "More info", font=link_font, fill=LINK)

    # Highlight callout pointing at More info -> Run anyway.
    callout_x = 200
    callout_y = 226
    # Arrow.
    d.line((callout_x, callout_y + 8, callout_x + 110, callout_y + 8),
           fill=ACCENT, width=2)
    d.polygon([
        (callout_x + 110, callout_y + 2),
        (callout_x + 120, callout_y + 8),
        (callout_x + 110, callout_y + 14),
    ], fill=ACCENT)
    d.text((callout_x + 128, callout_y + 1),
           "click here, then \"Run anyway\"",
           font=body_font, fill=ACCENT)

    # Footer buttons.
    btn_y = HEIGHT - 80
    # Don't run (primary).
    d.rectangle((WIDTH - 250, btn_y, WIDTH - 140, btn_y + 36), fill=(225, 230, 238, 255))
    d.text((WIDTH - 238, btn_y + 9), "Don't run", font=button_font, fill=HEADER)
    # Run anyway (disabled until you click More info).
    d.rectangle((WIDTH - 130, btn_y, WIDTH - 60, btn_y + 36),
                fill=(238, 238, 238, 255))
    d.text((WIDTH - 122, btn_y + 9), "Cancel", font=button_font, fill=(140, 140, 140))

    # Note at bottom of image.
    note_font = _font(11)
    d.text(
        (40, HEIGHT - 22),
        "This is a mockup of the real Windows SmartScreen dialog. Click More info -> Run anyway.",
        font=note_font, fill=(150, 150, 150, 255),
    )

    return img


def main() -> int:
    out = Path(__file__).resolve().parents[1] / "docs" / "smartscreen.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    render().save(out, "PNG")
    print(f"Wrote {out}  ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
