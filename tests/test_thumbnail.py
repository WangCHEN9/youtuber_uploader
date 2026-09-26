"""Building thumbnails from gameplay frames."""

import pytest
from PIL import Image

from ytupload.thumbnail import MAX_BYTES, THUMBNAIL_SIZE, ThumbnailError, make_thumbnail
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


def test_win_and_loss_produce_different_images(frame, tmp_path):
    won = make_thumbnail(frame, tmp_path / "won.jpg", headline="X", won=True)
    lost = make_thumbnail(frame, tmp_path / "lost.jpg", headline="X", won=False)
    assert won.read_bytes() != lost.read_bytes()


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
