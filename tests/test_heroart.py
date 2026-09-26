"""Hero name to Valve asset slug mapping."""

import pytest

from ytupload.heroart import hero_slug


@pytest.mark.parametrize(
    "display_name,expected",
    [
        ("Mars", "mars"),
        ("Legion Commander", "legion_commander"),
        ("Shadow Demon", "shadow_demon"),
        # Valve froze many slugs at the hero's original DotA name.
        ("Shadow Fiend", "nevermore"),
        ("Timbersaw", "shredder"),
        ("Doom", "doom_bringer"),
        ("Clockwerk", "rattletrap"),
        ("Necrophos", "necrolyte"),
        ("Wraith King", "skeleton_king"),
        ("Zeus", "zuus"),
        ("Magnus", "magnataur"),
        ("Io", "wisp"),
        ("Underlord", "abyssal_underlord"),
        ("Nature's Prophet", "furion"),
        ("Anti-Mage", "antimage"),
        ("Queen of Pain", "queenofpain"),
        ("Windranger", "windrunner"),
        ("Centaur Warrunner", "centaur"),
    ],
)
def test_slugs(display_name, expected):
    assert hero_slug(display_name) == expected


def test_slug_is_case_insensitive():
    assert hero_slug("mARS") == "mars"


def test_slug_tolerates_surrounding_whitespace():
    assert hero_slug("  Mars  ") == "mars"


def test_apostrophes_are_stripped_for_regular_heroes():
    assert hero_slug("Kez") == "kez"
