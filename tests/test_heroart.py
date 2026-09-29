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


# --------------------------------------------------- item and ability badges


@pytest.mark.parametrize(
    "name,expected",
    [
        ("blink", "blink"),
        ("Blink Dagger", "blink"),
        ("black_king_bar", "black_king_bar"),
        ("BKB", "black_king_bar"),
        # Valve shortened many item slugs away from the display name.
        ("Assault Cuirass", "assault"),
        ("Aghanim's Scepter", "ultimate_scepter"),
        ("Heart of Tarrasque", "heart"),
        ("Boots of Travel", "travel_boots"),
        ("Pipe of Insight", "pipe"),
        ("Eul's Scepter", "cyclone"),
        ("Linken's Sphere", "sphere"),
        # Abilities keep their full internal name.
        ("mars_arena_of_blood", "mars_arena_of_blood"),
    ],
)
def test_badge_slugs(name, expected):
    from ytupload.heroart import badge_slug

    assert badge_slug(name) == expected


# ------------------------------------------------------------ local wallpapers


def test_wallpaper_found_by_slug(tmp_path):
    from ytupload.heroart import find_wallpaper

    (tmp_path / "nevermore.jpg").write_bytes(b"x")
    assert find_wallpaper("Shadow Fiend", tmp_path) == tmp_path / "nevermore.jpg"


@pytest.mark.parametrize("filename", ["shadow_fiend.png", "shadow-fiend.webp"])
def test_wallpaper_found_by_display_name(tmp_path, filename):
    """People name files after the hero they see, not Valve's frozen slug."""
    from ytupload.heroart import find_wallpaper

    (tmp_path / filename).write_bytes(b"x")
    assert find_wallpaper("Shadow Fiend", tmp_path) == tmp_path / filename


def test_wallpaper_lookup_is_case_insensitive_on_the_extension(tmp_path):
    from ytupload.heroart import find_wallpaper

    (tmp_path / "mars.JPG").write_bytes(b"x")
    assert find_wallpaper("Mars", tmp_path) == tmp_path / "mars.JPG"


def test_wallpaper_ignores_non_images(tmp_path):
    from ytupload.heroart import find_wallpaper

    (tmp_path / "mars.txt").write_bytes(b"x")
    assert find_wallpaper("Mars", tmp_path) is None


def test_wallpaper_missing_folder_is_not_an_error(tmp_path):
    from ytupload.heroart import find_wallpaper

    assert find_wallpaper("Mars", tmp_path / "absent") is None
