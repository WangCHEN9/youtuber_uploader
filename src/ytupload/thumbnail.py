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

#: A single fixed accent. Deliberately not win/loss coloured: a thumbnail that
#: signals the result spoils the video before it is watched.
ACCENT = (220, 60, 45)
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


#: Fractions of a Dota 2 frame occupied by HUD rather than gameplay: the top hero
#: bar and clock, and the bottom ability bar, minimap and inventory. Trimming these
#: keeps the text band over gameplay instead of over blurred interface.
#: The top trim must clear the kill score as well as the hero bar: a visible score
#: is a spoiler, so this is deliberately generous.
DOTA_HUD_TRIM_TOP = 0.09
DOTA_HUD_TRIM_BOTTOM = 0.24


def _trim(image: Image.Image, top_fraction: float, bottom_fraction: float) -> Image.Image:
    """Crop *fraction* off the top and bottom of the image."""
    width, height = image.size
    top = int(height * max(top_fraction, 0))
    bottom = height - int(height * max(bottom_fraction, 0))
    if bottom - top < 80:  # Refuse to trim away essentially everything.
        return image
    return image.crop((0, top, width, bottom))


def make_thumbnail(
    frame_path: Path,
    output_path: Path,
    headline: str,
    subtitle: Optional[str] = None,
    trim_top: float = 0.0,
    trim_bottom: float = 0.0,
) -> Path:
    """Compose a thumbnail from a gameplay frame plus overlaid text.

    *headline* should be two or three words (a hero name, typically). *subtitle* is
    smaller supporting text such as the matchup.

    Nothing here encodes the match result, by design. The caller is responsible for
    choosing a source frame that does not reveal it either.

    *trim_top* and *trim_bottom* crop fractions off the source before framing. For
    gameplay footage this is what stops the text band landing on the HUD: see
    ``DOTA_HUD_TRIM_TOP`` and ``DOTA_HUD_TRIM_BOTTOM``.
    """
    frame_path = Path(frame_path)
    output_path = Path(output_path)
    if not frame_path.is_file():
        raise ThumbnailError(f"frame not found: {frame_path}")

    try:
        base = Image.open(frame_path).convert("RGB")
    except OSError as error:
        raise ThumbnailError(f"could not read {frame_path}: {error}") from error

    if trim_top or trim_bottom:
        base = _trim(base, trim_top, trim_bottom)

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
        [margin, baseline - 30, margin + 140, baseline - 16], fill=ACCENT
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


# ------------------------------------------------------------ hero art layout


def _shade(color: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
    return tuple(max(0, min(255, int(channel * factor))) for channel in color)


def _gradient_background(
    size: Tuple[int, int], color: Tuple[int, int, int]
) -> Image.Image:
    """A diagonal wash from a dark tint of *color* into near-black."""
    width, height = size
    top = _shade(color, 0.55)
    bottom = _shade(color, 0.12)
    background = Image.new("RGB", size, bottom)
    draw = ImageDraw.Draw(background)
    for row in range(height):
        ratio = row / max(height - 1, 1)
        draw.line(
            [(0, row), (width, row)],
            fill=tuple(
                int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)
            ),
        )
    return background


def _trim_transparent(image: Image.Image) -> Image.Image:
    """Crop to the non-transparent content, so the hero is not lost in empty space."""
    if image.mode != "RGBA":
        return image
    bbox = image.getchannel("A").getbbox()
    return image.crop(bbox) if bbox else image


def make_hero_thumbnail(
    hero_art_path: Path,
    output_path: Path,
    headline: str,
    subtitle: Optional[str] = None,
    accent: Optional[Tuple[int, int, int]] = None,
) -> Path:
    """Compose a thumbnail from hero art rather than gameplay footage.

    Because no frame of the match appears, this cannot spoil the result. The hero
    fills the right-hand side; the text occupies the left.
    """
    hero_art_path = Path(hero_art_path)
    output_path = Path(output_path)
    if not hero_art_path.is_file():
        raise ThumbnailError(f"hero art not found: {hero_art_path}")

    try:
        art = Image.open(hero_art_path).convert("RGBA")
    except OSError as error:
        raise ThumbnailError(f"could not read {hero_art_path}: {error}") from error

    width, height = THUMBNAIL_SIZE
    theme = accent or ACCENT
    canvas = _gradient_background(THUMBNAIL_SIZE, theme).convert("RGBA")

    # A soft glow behind the hero lifts them off the background.
    glow = Image.new("RGBA", THUMBNAIL_SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [width * 0.42, -height * 0.25, width * 1.12, height * 1.25],
        fill=_shade(theme, 0.85) + (120,),
    )
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(90)))

    # Hero art: trimmed to content, scaled to overflow the bottom edge slightly so
    # it reads as a cut-out rather than a floating sticker.
    art = _trim_transparent(art)
    target_height = int(height * 1.06)
    scale = target_height / art.height
    art = art.resize(
        (max(int(art.width * scale), 1), target_height), Image.LANCZOS
    )
    art_x = int(width * 0.60) - art.width // 4
    canvas.alpha_composite(art, (art_x, height - art.height + int(height * 0.04)))

    # Darken the left third so the text always has a ground to sit on.
    scrim = Image.new("RGBA", THUMBNAIL_SIZE, (0, 0, 0, 0))
    scrim_draw = ImageDraw.Draw(scrim)
    for column in range(int(width * 0.70)):
        alpha = int(190 * (1 - column / (width * 0.70)) ** 0.8)
        scrim_draw.line([(column, 0), (column, height)], fill=(0, 0, 0, alpha))
    canvas = Image.alpha_composite(canvas, scrim).convert("RGB")

    draw = ImageDraw.Draw(canvas)
    margin = 60
    usable = int(width * 0.58)

    headline_text = headline.strip().upper()
    headline_font = _fit_font(draw, headline_text, usable, start_size=118)

    subtitle_text = (subtitle or "").strip()
    subtitle_font = (
        _fit_font(draw, subtitle_text, usable, start_size=46) if subtitle_text else None
    )
    subtitle_height = (subtitle_font.size + 20) if subtitle_font else 0

    block_height = headline_font.size + subtitle_height
    baseline = (height - block_height) // 2

    draw.rectangle(
        [margin, baseline - 34, margin + 150, baseline - 20], fill=theme
    )
    _draw_text_with_shadow(draw, (margin, baseline), headline_text, headline_font, TEXT)
    if subtitle_font is not None:
        _draw_text_with_shadow(
            draw,
            (margin, baseline + headline_font.size + 14),
            subtitle_text,
            subtitle_font,
            (222, 222, 222),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _save_under_size_limit(canvas, output_path)
    return output_path
