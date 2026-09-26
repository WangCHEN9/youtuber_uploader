"""Fetching official Dota 2 hero art.

Valve publishes hero renders on a public CDN. They are cached locally after the first
fetch, so building a thumbnail for a hero you have used before needs no network.

Hero names map to Valve's internal slugs, which are frequently *not* the display name:
Shadow Fiend is ``nevermore``, Timbersaw is ``shredder``, Doom is ``doom_bringer``.
The irregular ones are listed explicitly; everything else follows the obvious rule.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional

DEFAULT_CACHE_DIR = Path(".heroart")

#: Tried in order. The first is a large transparent render, which is what makes a
#: thumbnail look deliberate rather than like a scraped icon.
_URL_TEMPLATES: List[str] = [
    "https://cdn.cloudflare.steamstatic.com/apps/dota2/videos/dota_react/heroes/renders/{slug}.png",
    "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/crops/{slug}.png",
    "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/{slug}.png",
    "https://cdn.akamai.steamstatic.com/apps/dota2/images/heroes/{slug}_vert.jpg",
]

#: Display name -> Valve slug, for every hero whose slug is not simply the lowercased
#: name with underscores. Valve froze many slugs at the hero's original DotA name.
_IRREGULAR_SLUGS = {
    "anti-mage": "antimage",
    "antimage": "antimage",
    "shadow fiend": "nevermore",
    "nevermore": "nevermore",
    "timbersaw": "shredder",
    "doom": "doom_bringer",
    "clockwerk": "rattletrap",
    "nature's prophet": "furion",
    "natures prophet": "furion",
    "necrophos": "necrolyte",
    "wraith king": "skeleton_king",
    "queen of pain": "queenofpain",
    "vengeful spirit": "vengefulspirit",
    "windranger": "windrunner",
    "zeus": "zuus",
    "magnus": "magnataur",
    "io": "wisp",
    "outworld destroyer": "obsidian_destroyer",
    "outworld devourer": "obsidian_destroyer",
    "underlord": "abyssal_underlord",
    "treant protector": "treant",
    "centaur warrunner": "centaur",
    "lifestealer": "life_stealer",
    "world tree": "treant",
}


class HeroArtError(RuntimeError):
    """Hero art could not be obtained."""


def hero_slug(hero_name: str) -> str:
    """Return Valve's asset slug for a hero display name."""
    cleaned = hero_name.strip().lower()
    if cleaned in _IRREGULAR_SLUGS:
        return _IRREGULAR_SLUGS[cleaned]
    # Drop apostrophes and hyphens, then collapse whitespace into underscores.
    cleaned = re.sub(r"['’\-]", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9\s_]", "", cleaned)
    return re.sub(r"\s+", "_", cleaned.strip())


def _download(url: str, destination: Path, timeout: float = 30.0) -> bool:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "ytupload"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return False
            data = response.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
    if len(data) < 2000:  # An error page rather than an image.
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return True


def fetch_hero_art(
    hero_name: str, cache_dir: Path = DEFAULT_CACHE_DIR
) -> Path:
    """Return a local path to *hero_name*'s art, downloading it if not cached."""
    slug = hero_slug(hero_name)
    if not slug:
        raise HeroArtError(f"could not derive a hero slug from {hero_name!r}")

    cache_dir = Path(cache_dir)
    cached = cache_dir / f"{slug}.png"
    if cached.is_file():
        return cached

    for template in _URL_TEMPLATES:
        if _download(template.format(slug=slug), cached):
            return cached

    raise HeroArtError(
        f"no art found for {hero_name!r} (tried slug {slug!r}).\n"
        "Check the hero spelling, or supply your own image with --hero-image."
    )


def available_offline(hero_name: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> bool:
    """Whether this hero's art is already cached."""
    return (Path(cache_dir) / f"{hero_slug(hero_name)}.png").is_file()


def dominant_color(
    image_path: Path, fallback: tuple = (40, 45, 60)
) -> tuple:
    """Return a representative colour from the art, for theming the background.

    Fully transparent pixels are ignored, and very dark or washed-out pixels are
    skipped so the result is the hero's actual colour rather than their shadow.
    """
    from PIL import Image

    try:
        image = Image.open(image_path).convert("RGBA")
    except OSError:
        return fallback

    image = image.resize((64, 64))
    best: Optional[tuple] = None
    best_score = -1.0
    for red, green, blue, alpha in image.getdata():
        if alpha < 200:
            continue
        brightness = (red + green + blue) / 3
        if brightness < 45 or brightness > 225:
            continue
        saturation = max(red, green, blue) - min(red, green, blue)
        if saturation > best_score:
            best_score = saturation
            best = (red, green, blue)
    return best or fallback
