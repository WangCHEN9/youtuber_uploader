"""Full-bleed hero thumbnails with circular item badges.

This is the layout most Dota channels converge on, and for a good reason: YouTube
already prints the title underneath the thumbnail, so words inside the image are
duplicated effort competing for the same attention. The art carries the frame, and
small circular badges say which items or abilities the video is really about.

Text is supported but off by default.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from .thumbnail import (
    MAX_BYTES,
    THUMBNAIL_SIZE,
    ThumbnailError,
    _draw_text_with_shadow,
    _fit_font,
    _save_under_size_limit,
    _shade,
    _trim_transparent,
)

#: Badge geometry, as fractions of the canvas height.
BADGE_DIAMETER = 0.27
BADGE_GAP = 0.04
BADGE_MARGIN_X = 0.035


def _radial_backdrop(
    size: Tuple[int, int], color: Tuple[int, int, int]
) -> Image.Image:
    """A dark ground with a broad glow behind where the hero will stand."""
    width, height = size
    # Near-black ground. The hero and the glow supply the colour; a saturated
    # backdrop competes with the art and reads as cheap.
    background = Image.new("RGB", size, _shade(color, 0.06))

    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [width * 0.34, -height * 0.20, width * 1.05, height * 1.20],
        fill=_shade(color, 0.60) + (115,),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(int(height * 0.16)))
    combined = Image.alpha_composite(background.convert("RGBA"), glow)

    # Vignette the corners so the eye lands on the hero.
    vignette = Image.new("L", size, 0)
    ImageDraw.Draw(vignette).ellipse(
        [-width * 0.25, -height * 0.25, width * 1.25, height * 1.25], fill=255
    )
    vignette = vignette.filter(ImageFilter.GaussianBlur(int(height * 0.18)))
    darkened = Image.new("RGBA", size, (0, 0, 0, 120))
    darkened.putalpha(Image.eval(vignette, lambda value: 120 - int(value * 0.47)))
    return Image.alpha_composite(combined, darkened).convert("RGB")


def _rim_glow(
    art: Image.Image, color: Tuple[int, int, int], spread: int, strength: float = 0.85
) -> Image.Image:
    """A coloured halo matching the hero's silhouette.

    Built from the art's own alpha channel, so it hugs the character rather than
    being a generic blob behind them. Composited *under* the art, this is what
    separates the hero from the background and gives the frame its depth.
    """
    alpha = art.getchannel("A").filter(ImageFilter.GaussianBlur(spread))
    glow = Image.new("RGBA", art.size, color + (0,))
    glow.putalpha(alpha.point(lambda value: int(value * strength)))
    return glow


def _grade(image: Image.Image, contrast: float = 1.12, saturation: float = 1.08):
    """A light colour grade: the render is lit flat for a menu, not for a thumbnail."""
    from PIL import ImageEnhance

    image = ImageEnhance.Contrast(image).enhance(contrast)
    return ImageEnhance.Color(image).enhance(saturation)


def _circular_badge(
    icon_path: Path, diameter: int, ring_color: Tuple[int, int, int]
) -> Image.Image:
    """Render one icon as a glowing circular badge."""
    try:
        icon = Image.open(icon_path).convert("RGBA")
    except OSError as error:
        raise ThumbnailError(f"could not read badge icon {icon_path}: {error}") from error

    # Item icons are 88x64 and abilities 128x128, so cover-crop to a square first
    # rather than squashing the artwork.
    side = min(icon.size)
    left = (icon.width - side) // 2
    top = (icon.height - side) // 2
    icon = icon.crop((left, top, left + side, top + side))
    inner = int(diameter * 0.82)
    icon = icon.resize((inner, inner), Image.LANCZOS)

    canvas = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))

    # Dark disc behind the icon so bright art still reads as a badge.
    disc = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    ImageDraw.Draw(disc).ellipse([0, 0, diameter - 1, diameter - 1], fill=(8, 12, 18, 235))
    canvas = Image.alpha_composite(canvas, disc)

    offset = (diameter - inner) // 2
    mask = Image.new("L", (inner, inner), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, inner - 1, inner - 1], fill=255)
    canvas.paste(icon, (offset, offset), mask)

    ring = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    ring_width = max(int(diameter * 0.045), 3)
    ImageDraw.Draw(ring).ellipse(
        [ring_width // 2, ring_width // 2, diameter - ring_width // 2, diameter - ring_width // 2],
        outline=ring_color + (255,),
        width=ring_width,
    )
    glow = ring.filter(ImageFilter.GaussianBlur(ring_width * 2))
    canvas = Image.alpha_composite(canvas, glow)
    return Image.alpha_composite(canvas, ring)


def make_splash_thumbnail(
    hero_art_path: Path,
    output_path: Path,
    badge_paths: Sequence[Path] = (),
    accent: Tuple[int, int, int] = (70, 200, 220),
    headline: Optional[str] = None,
    subtitle: Optional[str] = None,
) -> Path:
    """Compose a full-bleed hero thumbnail with circular badges down the left.

    No text is drawn unless *headline* is given: YouTube renders the title directly
    beneath the thumbnail, so repeating it inside the image wastes the space.

    Nothing here can encode the match result.
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

    if _is_opaque(art):
        # A rectangular image (a wallpaper, a screenshot) has no silhouette for the
        # rim glow to hug, so compositing it as a cut-out would look like a pasted
        # panel. Use it full-bleed instead, and let the vignette do the framing.
        canvas = _full_bleed(art, THUMBNAIL_SIZE).convert("RGBA")
    else:
        canvas = _compose_cutout(art, THUMBNAIL_SIZE, accent)

    return _finish(canvas, output_path, badge_paths, accent, headline, subtitle)


def _is_opaque(art: Image.Image, threshold: int = 250) -> bool:
    """Whether the image is effectively a rectangle rather than a cut-out."""
    if "A" not in art.mode:
        return True
    alpha = art.getchannel("A")
    minimum, _ = alpha.getextrema()
    return minimum >= threshold


def _full_bleed(art: Image.Image, size: Tuple[int, int]) -> Image.Image:
    """Cover-crop the image to fill the canvas, then vignette the corners."""
    width, height = size
    target_ratio = width / height
    source = art.convert("RGB")
    if source.width / source.height > target_ratio:
        new_width = int(source.height * target_ratio)
        left = (source.width - new_width) // 2
        source = source.crop((left, 0, left + new_width, source.height))
    else:
        new_height = int(source.width / target_ratio)
        top = (source.height - new_height) // 2
        source = source.crop((0, top, source.width, top + new_height))
    source = source.resize(size, Image.LANCZOS)

    vignette = Image.new("L", size, 0)
    ImageDraw.Draw(vignette).ellipse(
        [-width * 0.20, -height * 0.20, width * 1.20, height * 1.20], fill=255
    )
    vignette = vignette.filter(ImageFilter.GaussianBlur(int(height * 0.16)))
    shade = Image.new("RGBA", size, (0, 0, 0, 0))
    shade.putalpha(Image.eval(vignette, lambda value: 135 - int(value * 0.53)))
    return Image.alpha_composite(source.convert("RGBA"), shade).convert("RGB")


def _compose_cutout(
    art: Image.Image, size: Tuple[int, int], accent: Tuple[int, int, int]
) -> Image.Image:
    """Place a transparent hero render over a themed backdrop, with rim lighting."""
    width, height = size
    canvas = _radial_backdrop(size, accent).convert("RGBA")

    # Hero fills the frame vertically and sits right of centre, leaving the left
    # third clear for badges.
    art = _trim_transparent(art)
    target_height = int(height * 1.14)
    scale = target_height / art.height
    art = art.resize((max(int(art.width * scale), 1), target_height), Image.LANCZOS)
    art_x = int(width * 0.56) - art.width // 2
    art_y = height - art.height + int(height * 0.07)

    # Two halos under the hero: a wide soft one for atmosphere, a tight bright one
    # that reads as rim light. Both follow the silhouette.
    canvas.alpha_composite(
        _rim_glow(art, _shade(accent, 1.25), int(height * 0.07), 0.55), (art_x, art_y)
    )
    canvas.alpha_composite(
        _rim_glow(art, (255, 255, 255), int(height * 0.012), 0.42), (art_x, art_y)
    )
    canvas.alpha_composite(art, (art_x, art_y))

    return canvas


def _finish(
    canvas: Image.Image,
    output_path: Path,
    badge_paths: Sequence[Path],
    accent: Tuple[int, int, int],
    headline: Optional[str],
    subtitle: Optional[str],
) -> Path:
    """Badges, grade, optional text and save. Shared by both composition paths."""
    width, height = THUMBNAIL_SIZE

    badges: List[Image.Image] = []
    diameter = int(height * BADGE_DIAMETER)
    for icon_path in badge_paths[:3]:  # More than three stops reading as a set.
        badges.append(_circular_badge(Path(icon_path), diameter, accent))

    if badges:
        scrim = Image.new("RGBA", THUMBNAIL_SIZE, (0, 0, 0, 0))
        scrim_draw = ImageDraw.Draw(scrim)
        for column in range(int(width * 0.48)):
            alpha = int(150 * (1 - column / (width * 0.48)) ** 1.2)
            scrim_draw.line([(column, 0), (column, height)], fill=(0, 0, 0, alpha))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), scrim)

        gap = int(height * BADGE_GAP)
        total = len(badges) * diameter + (len(badges) - 1) * gap
        top = (height - total) // 2
        left = int(width * BADGE_MARGIN_X)
        for index, badge in enumerate(badges):
            canvas.alpha_composite(badge, (left, top + index * (diameter + gap)))

    canvas = _grade(canvas.convert("RGB"))

    if headline:
        draw = ImageDraw.Draw(canvas)
        margin = int(width * 0.035)
        usable = int(width * 0.42)
        headline_font = _fit_font(draw, headline.upper(), usable, start_size=92)
        baseline = int(height * 0.78)
        _draw_text_with_shadow(
            draw, (margin, baseline), headline.upper(), headline_font, (255, 255, 255)
        )
        if subtitle:
            subtitle_font = _fit_font(draw, subtitle, usable, start_size=40)
            _draw_text_with_shadow(
                draw,
                (margin, baseline + headline_font.size + 10),
                subtitle,
                subtitle_font,
                (220, 220, 220),
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _save_under_size_limit(canvas, output_path)
    return output_path
