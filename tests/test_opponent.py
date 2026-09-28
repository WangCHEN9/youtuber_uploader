"""The lane opponent in a splash thumbnail.

This exists so a one-hero channel's thumbnails are not all identical: the hero
may be the same every game, but the matchup is not.
"""

import pytest
from PIL import Image

from ytupload.splash import (
    OPPONENT_CENTRE_X,
    OPPONENT_DARKEN,
    OPPONENT_SCALE,
    make_splash_thumbnail,
)
from ytupload.thumbnail import THUMBNAIL_SIZE, ThumbnailError


def _render(path, colour=(200, 90, 40)):
    image = Image.new("RGBA", (800, 900), (0, 0, 0, 0))
    image.paste(colour + (255,), (200, 150, 600, 800))
    image.save(path)
    return path


@pytest.fixture
def hero(tmp_path):
    return _render(tmp_path / "hero.png")


@pytest.fixture
def opponent(tmp_path):
    return _render(tmp_path / "opponent.png", (60, 110, 200))


def test_the_opponent_changes_the_image(hero, opponent, tmp_path):
    alone = make_splash_thumbnail(hero, tmp_path / "alone.jpg")
    versus = make_splash_thumbnail(
        hero, tmp_path / "vs.jpg", opponent_art_path=opponent
    )
    assert alone.read_bytes() != versus.read_bytes()


def test_output_dimensions_are_unchanged(hero, opponent, tmp_path):
    out = make_splash_thumbnail(hero, tmp_path / "t.jpg", opponent_art_path=opponent)
    assert Image.open(out).size == THUMBNAIL_SIZE


def test_two_different_opponents_give_two_different_thumbnails(hero, tmp_path):
    """The whole point: same hero, different matchup, distinguishable image."""
    first = _render(tmp_path / "a.png", (60, 110, 200))
    second = _render(tmp_path / "b.png", (40, 180, 90))
    a = make_splash_thumbnail(hero, tmp_path / "a.jpg", opponent_art_path=first)
    b = make_splash_thumbnail(hero, tmp_path / "b.jpg", opponent_art_path=second)
    assert a.read_bytes() != b.read_bytes()


def test_the_opponent_is_smaller_than_the_hero():
    """Smaller, but genuinely a second subject rather than a background shape."""
    assert 0.7 < OPPONENT_SCALE < 1.0


def test_the_opponent_is_darkened_not_hidden():
    """Darkening separates the two heroes; hiding one defeats the purpose."""
    assert 0.6 < OPPONENT_DARKEN < 0.9


def test_badges_leave_the_left_column_when_an_opponent_is_present():
    """With two heroes the left column belongs to the opponent.

    The first design kept the big diagonal badge stack and tucked the opponent
    behind it. Badges now shrink into a bottom row instead.
    """
    from ytupload.splash import BADGE_DIAMETERS, BADGE_ROW_DIAMETER, BADGE_ROW_Y

    assert BADGE_ROW_DIAMETER < min(BADGE_DIAMETERS.values())
    assert BADGE_ROW_Y > 0.6, "the badge row belongs at the bottom, clear of both heroes"


def test_the_two_heroes_occupy_opposite_halves():
    """Two thumbnails of the same hero only differ if the frame itself differs.

    Regression: the opponent used to be small, dark and behind the badges. It
    changed about 8% of the pixels and two Mars thumbnails still looked
    identical at sidebar size.
    """
    from ytupload.splash import HERO_CENTRE_X_VERSUS

    assert OPPONENT_CENTRE_X < 0.4
    assert HERO_CENTRE_X_VERSUS > 0.6
    assert HERO_CENTRE_X_VERSUS - OPPONENT_CENTRE_X > 0.35


def test_the_opponent_is_bright_enough_to_identify():
    """Darkened to a silhouette, the opponent adds nothing a viewer can read."""
    assert OPPONENT_DARKEN >= 0.65


def test_the_hero_still_dominates_the_right_half(hero, opponent, tmp_path):
    """The right half must be the player's hero, not the opponent."""
    out = make_splash_thumbnail(hero, tmp_path / "t.jpg", opponent_art_path=opponent)
    image = Image.open(out)
    right = image.crop((760, 200, 1100, 600)).convert("RGB")
    pixels = list(right.getdata())
    warm = sum(1 for r, g, b in pixels if r > b + 20)
    assert warm > len(pixels) * 0.5, "the opponent has taken over the hero's side"


def test_unreadable_opponent_art_raises(hero, tmp_path):
    junk = tmp_path / "junk.png"
    junk.write_bytes(b"not an image")
    with pytest.raises(ThumbnailError, match="opponent art"):
        make_splash_thumbnail(hero, tmp_path / "t.jpg", opponent_art_path=junk)


def test_no_opponent_is_the_default(hero, tmp_path):
    out = make_splash_thumbnail(hero, tmp_path / "t.jpg")
    assert Image.open(out).size == THUMBNAIL_SIZE
