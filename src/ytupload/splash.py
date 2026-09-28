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

#: Badge geometry, measured off a reference thumbnail. Badges run down the left on
#: a slight diagonal, large and widely spaced, rather than as a tight centred stack:
#: at sidebar size a few big circles read, and a neat column of small ones does not.
#: Diameter is a fraction of canvas height and shrinks as badges are added.
BADGE_DIAMETERS = {1: 0.36, 2: 0.34, 3: 0.25}

#: Vertical span the badge block occupies, and where its top edge sits.
BADGE_SPAN = 0.80
BADGE_TOP = 0.06

#: Left inset of the first badge, and how far each subsequent badge steps right.
BADGE_MARGIN_X = 0.028
BADGE_X_STEP = 0.041

#: Brand mark (channel mascot), bottom-right. Small enough to stay an identity
#: mark rather than compete with the hero for attention.
BRAND_DIAMETER = 0.17
BRAND_MARGIN = 0.022


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
    brand_path: Optional[Path] = None,
    opponent_art_path: Optional[Path] = None,
) -> Path:
    """Compose a full-bleed hero thumbnail with circular badges down the left.

    No text is drawn unless *headline* is given: YouTube renders the title directly
    beneath the thumbnail, so repeating it inside the image wastes the space.

    *opponent_art_path* adds the lane opponent on the left, smaller and darkened
    so it reads as the opposition rather than a second protagonist. This is the
    main defence against every thumbnail on a one-hero channel looking identical:
    the matchup changes every game even when the hero does not.

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
        canvas = _compose_cutout(art, THUMBNAIL_SIZE, accent, opponent_art_path)

    return _finish(
        canvas,
        output_path,
        badge_paths,
        accent,
        headline,
        subtitle,
        brand_path,
        versus=opponent_art_path is not None,
    )


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
    art: Image.Image,
    size: Tuple[int, int],
    accent: Tuple[int, int, int],
    opponent_art_path: Optional[Path] = None,
) -> Image.Image:
    """Place a transparent hero render over a themed backdrop, with rim lighting."""
    width, height = size
    canvas = _radial_backdrop(size, accent).convert("RGBA")

    if opponent_art_path is not None:
        canvas = _place_opponent(canvas, Path(opponent_art_path), size)

    # Hero fills the frame vertically and sits right of centre, leaving the left
    # third clear for badges.
    art = _trim_transparent(art)
    versus = opponent_art_path is not None
    target_height = int(height * (1.14 * (HERO_SCALE_VERSUS if versus else 1.0)))
    scale = target_height / art.height
    art = art.resize((max(int(art.width * scale), 1), target_height), Image.LANCZOS)
    centre = HERO_CENTRE_X_VERSUS if versus else HERO_CENTRE_X_SOLO
    art_x = int(width * centre) - art.width // 2
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


#: With an opponent, the frame becomes a two-hero split rather than one hero with
#: something tucked behind the badges.
#:
#: A first attempt kept the hero at full size and put the opponent small, dark and
#: behind the badge column. It changed about 8% of the pixels, all of them dark,
#: and two thumbnails of the same hero still looked identical at sidebar size. To
#: distinguish them the *dominant* impression has to change, which means the
#: opponent has to be genuinely half the picture.
OPPONENT_SCALE = 0.88
OPPONENT_DARKEN = 0.72
OPPONENT_CENTRE_X = 0.24

#: Where the player's hero sits once an opponent shares the frame.
HERO_CENTRE_X_SOLO = 0.56
HERO_CENTRE_X_VERSUS = 0.76
HERO_SCALE_VERSUS = 1.02

#: With both heroes present the left column is occupied, so badges become a small
#: horizontal row along the bottom-left instead.
BADGE_ROW_DIAMETER = 0.155
BADGE_ROW_Y = 0.80
BADGE_ROW_GAP = 0.012


def _place_opponent(
    canvas: Image.Image, art_path: Path, size: Tuple[int, int]
) -> Image.Image:
    """Composite the lane opponent on the left, behind where the hero will go."""
    try:
        art = Image.open(art_path).convert("RGBA")
    except OSError as error:
        raise ThumbnailError(
            f"could not read opponent art {art_path}: {error}"
        ) from error

    width, height = size
    art = _trim_transparent(art)
    target_height = int(height * 1.10 * OPPONENT_SCALE)
    scale = target_height / art.height
    art = art.resize((max(int(art.width * scale), 1), target_height), Image.LANCZOS)

    # Darkened rather than desaturated: silhouettes stay readable, and the colour
    # still hints at who it is, but nothing competes with the player's hero.
    from PIL import ImageEnhance

    rgb = ImageEnhance.Brightness(art.convert("RGB")).enhance(OPPONENT_DARKEN)
    art = Image.merge("RGBA", (*rgb.split(), art.getchannel("A")))

    art_x = int(width * OPPONENT_CENTRE_X) - art.width // 2
    art_y = height - art.height + int(height * 0.05)
    canvas.alpha_composite(art, (max(art_x, -art.width // 3), art_y))
    return canvas


def _brand_mark(image_path: Path, diameter: int) -> Image.Image:
    """A small circular brand mark, e.g. the channel's mascot.

    Deliberately plainer than an item badge: a thin light ring and a soft drop
    shadow, no dark disc. It is an identity mark, not information, so it should
    sit quietly in the corner rather than compete with the hero.
    """
    try:
        source = Image.open(image_path).convert("RGB")
    except OSError as error:
        raise ThumbnailError(f"could not read brand image {image_path}: {error}") from error

    side = min(source.size)
    left = (source.width - side) // 2
    top = (source.height - side) // 2
    source = source.crop((left, top, left + side, top + side))
    source = source.resize((diameter, diameter), Image.LANCZOS)

    canvas = Image.new("RGBA", (diameter + 16, diameter + 16), (0, 0, 0, 0))

    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([8, 10, diameter + 8, diameter + 10], fill=(0, 0, 0, 170))
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(6)))

    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, diameter - 1, diameter - 1], fill=255)
    canvas.paste(source, (8, 8), mask)

    ring_width = max(int(diameter * 0.05), 3)
    ImageDraw.Draw(canvas).ellipse(
        [8, 8, diameter + 8 - 1, diameter + 8 - 1],
        outline=(255, 255, 255, 230),
        width=ring_width,
    )
    return canvas


def _finish(
    canvas: Image.Image,
    output_path: Path,
    badge_paths: Sequence[Path],
    accent: Tuple[int, int, int],
    headline: Optional[str],
    subtitle: Optional[str],
    brand_path: Optional[Path] = None,
    versus: bool = False,
) -> Path:
    """Badges, brand mark, grade, optional text and save. Shared by both paths."""
    width, height = THUMBNAIL_SIZE

    wanted = list(badge_paths[:3])  # More than three stops reading as a set.
    # With two heroes the left column belongs to the opponent, so badges shrink
    # into a row along the bottom instead of a large diagonal stack.
    diameter = int(
        height * (BADGE_ROW_DIAMETER if versus else BADGE_DIAMETERS.get(len(wanted), 0.25))
    )
    badges: List[Image.Image] = [
        _circular_badge(Path(icon_path), diameter, accent) for icon_path in wanted
    ]

    if badges and versus:
        gap = int(width * BADGE_ROW_GAP)
        left = int(width * BADGE_MARGIN_X)
        top = int(height * BADGE_ROW_Y)
        for index, badge in enumerate(badges):
            canvas.alpha_composite(badge, (left + index * (diameter + gap), top))
    elif badges:
        scrim = Image.new("RGBA", THUMBNAIL_SIZE, (0, 0, 0, 0))
        scrim_draw = ImageDraw.Draw(scrim)
        for column in range(int(width * 0.48)):
            alpha = int(150 * (1 - column / (width * 0.48)) ** 1.2)
            scrim_draw.line([(column, 0), (column, height)], fill=(0, 0, 0, alpha))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), scrim)

        count = len(badges)
        span = int(height * BADGE_SPAN)
        gap = max((span - count * diameter) // (count - 1), 0) if count > 1 else 0
        top = int(height * BADGE_TOP)
        left = int(width * BADGE_MARGIN_X)
        step_x = int(width * BADGE_X_STEP)
        for index, badge in enumerate(badges):
            canvas.alpha_composite(
                badge,
                (left + index * step_x, top + index * (diameter + gap)),
            )

    if brand_path is not None:
        # Bottom-right: diagonally opposite the badges, so the two never collide.
        mark = _brand_mark(Path(brand_path), int(height * BRAND_DIAMETER))
        margin = int(width * BRAND_MARGIN)
        canvas = canvas.convert("RGBA")
        canvas.alpha_composite(
            mark, (width - mark.width - margin, height - mark.height - margin)
        )

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
