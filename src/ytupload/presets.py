"""Reusable metadata presets.

Kept in one place so the CLI and the Dota 2 Claude skill cannot drift apart: both
read their defaults from here rather than repeating tag lists in prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

#: Tags applied to every Dota 2 upload. YouTube allows 500 characters of tags in
#: total, so these deliberately leave room for per-video hero and matchup tags.
DOTA_BASE_TAGS: List[str] = [
    "Dota 2",
    "Dota2",
    "dota 2 gameplay",
    "offlane",
    "position 3",
    "pos 3",
    "offlaner",
    "ranked",
]


@dataclass(frozen=True)
class Preset:
    """A named bundle of defaults the CLI can apply."""

    name: str
    tags: List[str]
    playlist: str
    description_footer: str


DOTA_OFFLANE = Preset(
    name="dota-offlane",
    tags=DOTA_BASE_TAGS,
    playlist="Dota 2 - Offlane",
    description_footer=(
        "Position 3 / offlane gameplay.\n"
        "Subscribe for more Dota 2 offlane matches."
    ),
)

PRESETS: Dict[str, Preset] = {DOTA_OFFLANE.name: DOTA_OFFLANE}
