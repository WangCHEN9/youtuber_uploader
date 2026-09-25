"""Building YouTube thumbnails from a gameplay frame.

A thumbnail is mostly read at a few hundred pixels wide in a sidebar, so the design
rules are severe: very few words, very large type, and enough contrast that the text
survives whatever is behind it.

YouTube requires 1280x720 or larger, 16:9, and under 2 MB.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

THUMBNAIL_SIZE = (1280, 720)
MAX_BYTES = 2 * 1024 * 1024

#: Windows font candidates, heaviest first. Thin fonts vanish at sidebar size.
_FONT_CANDIDATES: Sequence[str] = (
    r"C:\Windows\Fonts\impact.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
)

ACCENT = (220, 60, 45)       # Dire red
ACCENT_WIN = (120, 190, 70)  # Radiant green
TEXT = (255, 255, 255)
SHADOW = (0, 0, 0)


class ThumbnailError(RuntimeError):
    """The thumbnail could not be built."""


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    # Pillow's default font does not scale, so this is a poor but working fallback.
    return ImageFont.load_default()


def _fit_font(
    draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int
) -> ImageFont.FreeTypeFont:
    """Shrink the font until *text* fits within *max_width*."""
    size = start_size
    while size > 16:
        font = _load_font(size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 4
    return _load_font(16)


def _cover(image: Image.Image, size: Tuple[int, int]) -> Image.Image:
    """Scale and centre-crop *image* to exactly *size*, preserving aspect ratio."""
    target_ratio = size[0] / size[1]
    width, height = image.size
    if width / height > target_ratio:
        new_width = int(height * target_ratio)
        left = (width - new_width) // 2
        image = image.crop((left, 0, left + new_width, height))
    else:
        new_height = int(width / target_ratio)
        top = (height - new_height) // 2
        image = image.crop((0, top, width, top + new_height))
    return image.resize(size, Image.LANCZOS)


def _draw_text_with_shadow(
    draw: ImageDraw.ImageDraw,
    position: Tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: Tuple[int, int, int],
) -> None:
    """Text with a hard offset shadow, which reads over any background."""
    x, y = position
    for offset_x, offset_y in ((4, 4), (3, 3)):
        draw.text((x + offset_x, y + offset_y), text, font=font, fill=SHADOW)
    draw.text((x, y), text, font=font, fill=fill)


def make_thumbnail(
    frame_path: Path,
    output_path: Path,
    headline: str,
    subtitle: Optional[str] = None,
    won: Optional[bool] = None,
) -> Path:
    """Compose a thumbnail from a gameplay frame plus overlaid text.

    *headline* should be two or three words (a hero name, typically). *subtitle* is
    smaller supporting text such as the matchup. *won* tints the accent bar green or
    red; ``None`` leaves it neutral.
    """
    frame_path = Path(frame_path)
    output_path = Path(output_path)
    if not frame_path.is_file():
        raise ThumbnailError(f"frame not found: {frame_path}")

    try:
        base = Image.open(frame_path).convert("RGB")
    except OSError as error:
        raise ThumbnailError(f"could not read {frame_path}: {error}") from error

    canvas = _cover(base, THUMBNAIL_SIZE)

    # A darkened, slightly blurred band along the bottom so text never competes
    # with gameplay detail behind it.
    width, height = THUMBNAIL_SIZE
    band_top = int(height * 0.55)
    band = canvas.crop((0, band_top, width, height)).filter(
        ImageFilter.GaussianBlur(6)
    )
    canvas.paste(band, (0, band_top))

    scrim = Image.new("RGBA", THUMBNAIL_SIZE, (0, 0, 0, 0))
    scrim_draw = ImageDraw.Draw(scrim)
    for offset in range(band_top, height):
        # Linear ramp to 80% opacity at the bottom edge.
        alpha = int(205 * (offset - band_top) / (height - band_top))
        scrim_draw.line([(0, offset), (width, offset)], fill=(0, 0, 0, alpha))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), scrim).convert("RGB")

    draw = ImageDraw.Draw(canvas)
    margin = 56
    usable = width - margin * 2

    accent = ACCENT if won is None else (ACCENT_WIN if won else ACCENT)

    headline_text = headline.strip().upper()
    headline_font = _fit_font(draw, headline_text, usable, start_size=132)
    headline_height = headline_font.size

    subtitle_font = None
    subtitle_height = 0
    subtitle_text = (subtitle or "").strip()
    if subtitle_text:
        subtitle_font = _fit_font(draw, subtitle_text, usable, start_size=54)
        subtitle_height = subtitle_font.size + 18

    baseline = height - margin - subtitle_height - headline_height

    # Accent bar: a fixed visual anchor in the corner of every thumbnail.
    draw.rectangle(
        [margin, baseline - 30, margin + 140, baseline - 16], fill=accent
    )

    _draw_text_with_shadow(draw, (margin, baseline), headline_text, headline_font, TEXT)
    if subtitle_font is not None:
        _draw_text_with_shadow(
            draw,
            (margin, baseline + headline_height + 12),
            subtitle_text,
            subtitle_font,
            (225, 225, 225),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _save_under_size_limit(canvas, output_path)
    return output_path


def _save_under_size_limit(image: Image.Image, output_path: Path) -> None:
    """Save as JPEG, stepping quality down until it fits YouTube's 2 MB cap."""
    for quality in (92, 85, 78, 70, 60):
        image.save(output_path, "JPEG", quality=quality, optimize=True)
        if output_path.stat().st_size <= MAX_BYTES:
            return
    raise ThumbnailError(
        f"thumbnail still exceeds {MAX_BYTES} bytes at the lowest quality setting"
    )
