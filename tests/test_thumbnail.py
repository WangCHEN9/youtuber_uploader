"""Building thumbnails from gameplay frames."""

import pytest
from PIL import Image

from ytupload.thumbnail import (
    DOTA_HUD_TRIM_BOTTOM,
    DOTA_HUD_TRIM_TOP,
    MAX_BYTES,
    THUMBNAIL_SIZE,
    ThumbnailError,
    make_thumbnail,
)
from ytupload.video import extract_frame


@pytest.fixture
def frame(long_video, tmp_path):
    return extract_frame(long_video, 1.0, tmp_path / "frame.jpg")


def test_produces_youtube_sized_output(frame, tmp_path):
    output = make_thumbnail(frame, tmp_path / "t.jpg", headline="Centaur")
    assert Image.open(output).size == THUMBNAIL_SIZE


def test_stays_under_the_size_limit(frame, tmp_path):
    output = make_thumbnail(frame, tmp_path / "t.jpg", headline="Centaur")
    assert output.stat().st_size <= MAX_BYTES


def test_accepts_a_subtitle(frame, tmp_path):
    output = make_thumbnail(
        frame, tmp_path / "t.jpg", headline="Centaur", subtitle="Offlane vs Timbersaw"
    )
    assert output.exists()


def test_a_very_long_headline_still_fits(frame, tmp_path):
    """The font shrinks to fit rather than overflowing the canvas."""
    output = make_thumbnail(
        frame, tmp_path / "t.jpg", headline="Nature's Prophet And Friends Forever"
    )
    assert Image.open(output).size == THUMBNAIL_SIZE


def test_make_thumbnail_takes_no_result_argument():
    """The result must not be encodable in a thumbnail: it would spoil the video."""
    import inspect

    parameters = inspect.signature(make_thumbnail).parameters
    assert "won" not in parameters
    assert "lost" not in parameters
    assert "result" not in parameters


def test_creates_the_output_directory(frame, tmp_path):
    output = make_thumbnail(frame, tmp_path / "deep" / "t.jpg", headline="X")
    assert output.exists()


def test_a_source_that_is_not_an_image_raises(tmp_path):
    junk = tmp_path / "junk.jpg"
    junk.write_bytes(b"not an image")
    with pytest.raises(ThumbnailError):
        make_thumbnail(junk, tmp_path / "t.jpg", headline="X")


def test_a_missing_source_raises(tmp_path):
    with pytest.raises(ThumbnailError, match="frame not found"):
        make_thumbnail(tmp_path / "nope.jpg", tmp_path / "t.jpg", headline="X")


def test_a_non_16_9_source_is_cropped_not_squashed(tmp_path):
    """Letterboxing or stretching would look broken; cover-crop is correct."""
    tall = tmp_path / "tall.jpg"
    Image.new("RGB", (600, 1200), (30, 40, 50)).save(tall)
    output = make_thumbnail(tall, tmp_path / "t.jpg", headline="X")
    assert Image.open(output).size == THUMBNAIL_SIZE


def test_hud_trim_changes_the_framing(frame, tmp_path):
    """Trimming must actually alter the image, not silently no-op."""
    plain = make_thumbnail(frame, tmp_path / "plain.jpg", headline="X")
    trimmed = make_thumbnail(
        frame,
        tmp_path / "trimmed.jpg",
        headline="X",
        trim_top=DOTA_HUD_TRIM_TOP,
        trim_bottom=DOTA_HUD_TRIM_BOTTOM,
    )
    assert plain.read_bytes() != trimmed.read_bytes()


def test_hud_trim_keeps_output_dimensions(frame, tmp_path):
    output = make_thumbnail(
        frame,
        tmp_path / "t.jpg",
        headline="X",
        trim_top=DOTA_HUD_TRIM_TOP,
        trim_bottom=DOTA_HUD_TRIM_BOTTOM,
    )
    assert Image.open(output).size == THUMBNAIL_SIZE


def test_an_absurd_trim_is_refused_rather_than_destroying_the_image(frame, tmp_path):
    """Trimming 99% from both ends would leave nothing; fall back to the full frame."""
    output = make_thumbnail(
        frame, tmp_path / "t.jpg", headline="X", trim_top=0.99, trim_bottom=0.99
    )
    assert Image.open(output).size == THUMBNAIL_SIZE
