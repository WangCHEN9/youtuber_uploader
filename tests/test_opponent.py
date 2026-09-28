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
    assert 0.4 < OPPONENT_SCALE < 1.0


def test_the_opponent_is_darkened_not_hidden():
    """Darkening keeps the silhouette readable; hiding it defeats the purpose."""
    assert 0.2 < OPPONENT_DARKEN < 0.8


def test_the_opponent_clears_the_badge_column():
    """Badges sit on the left edge. An opponent centred there is half-covered.

    Regression: at 0.20 the opponent's face landed behind a badge.
    """
    from ytupload.splash import BADGE_MARGIN_X, BADGE_X_STEP

    badge_right_edge = BADGE_MARGIN_X + BADGE_X_STEP + 0.19  # ~one badge wide
    assert OPPONENT_CENTRE_X > badge_right_edge


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
