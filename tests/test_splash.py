"""Full-bleed splash layout with circular badges."""

import pytest
from PIL import Image

from ytupload.splash import make_splash_thumbnail
from ytupload.thumbnail import MAX_BYTES, THUMBNAIL_SIZE, ThumbnailError, feathered_cutout
from ytupload.video import extract_frame


@pytest.fixture
def art(tmp_path):
    """Stand-in hero art: an RGBA image with transparent margins, like a real render."""
    image = Image.new("RGBA", (800, 900), (0, 0, 0, 0))
    image.paste((180, 90, 40, 255), (200, 150, 600, 800))
    path = tmp_path / "art.png"
    image.save(path)
    return path


@pytest.fixture
def badge(tmp_path):
    """Stand-in item icon at Valve's actual 88x64 item dimensions."""
    path = tmp_path / "badge.png"
    Image.new("RGBA", (88, 64), (60, 120, 200, 255)).save(path)
    return path


def test_produces_youtube_sized_output(art, tmp_path):
    out = make_splash_thumbnail(art, tmp_path / "t.jpg")
    assert Image.open(out).size == THUMBNAIL_SIZE


def test_stays_under_the_size_limit(art, tmp_path):
    out = make_splash_thumbnail(art, tmp_path / "t.jpg")
    assert out.stat().st_size <= MAX_BYTES


def test_badges_change_the_image(art, badge, tmp_path):
    plain = make_splash_thumbnail(art, tmp_path / "plain.jpg")
    badged = make_splash_thumbnail(art, tmp_path / "badged.jpg", badge_paths=[badge])
    assert plain.read_bytes() != badged.read_bytes()


def test_non_square_badge_icons_are_not_squashed(art, badge, tmp_path):
    """Item icons are 88x64; they must be cover-cropped, not stretched to a circle."""
    out = make_splash_thumbnail(art, tmp_path / "t.jpg", badge_paths=[badge])
    assert Image.open(out).size == THUMBNAIL_SIZE


def test_at_most_three_badges_are_drawn(art, badge, tmp_path):
    """More than three stops reading as a set, so extras are dropped, not crammed."""
    three = make_splash_thumbnail(art, tmp_path / "3.jpg", badge_paths=[badge] * 3)
    five = make_splash_thumbnail(art, tmp_path / "5.jpg", badge_paths=[badge] * 5)
    assert three.read_bytes() == five.read_bytes()


def test_no_text_is_drawn_by_default(art, tmp_path):
    """YouTube prints the title beneath the thumbnail; repeating it wastes space."""
    plain = make_splash_thumbnail(art, tmp_path / "plain.jpg")
    titled = make_splash_thumbnail(art, tmp_path / "titled.jpg", headline="MARS")
    assert plain.read_bytes() != titled.read_bytes()


def test_missing_art_raises(tmp_path):
    with pytest.raises(ThumbnailError, match="hero art not found"):
        make_splash_thumbnail(tmp_path / "nope.png", tmp_path / "t.jpg")


def test_unreadable_badge_raises(art, tmp_path):
    junk = tmp_path / "junk.png"
    junk.write_bytes(b"not an image")
    with pytest.raises(ThumbnailError, match="badge icon"):
        make_splash_thumbnail(art, tmp_path / "t.jpg", badge_paths=[junk])


def test_make_splash_thumbnail_takes_no_result_argument():
    import inspect

    parameters = inspect.signature(make_splash_thumbnail).parameters
    assert "won" not in parameters
    assert "result" not in parameters


# --------------------------------------------------------------- cutouts


def test_cutout_is_rgba_with_transparent_corners(long_video, tmp_path):
    """The radial fade is what removes terrain without needing segmentation."""
    frame = extract_frame(long_video, 1.0, tmp_path / "f.jpg")
    cut = feathered_cutout(frame, tmp_path / "c.png", size=0.4)
    image = Image.open(cut)
    assert image.mode == "RGBA"
    assert image.getpixel((0, 0))[3] == 0          # corner fully transparent
    centre = (image.width // 2, image.height // 2)
    assert image.getpixel(centre)[3] == 255        # centre fully opaque


def test_cutout_is_square(long_video, tmp_path):
    frame = extract_frame(long_video, 1.0, tmp_path / "f.jpg")
    cut = feathered_cutout(frame, tmp_path / "c.png", output_size=600)
    assert Image.open(cut).size == (600, 600)


def test_cutout_clamps_to_the_frame_at_the_edges(long_video, tmp_path):
    """A centre near the border must not produce an out-of-bounds crop."""
    frame = extract_frame(long_video, 1.0, tmp_path / "f.jpg")
    assert feathered_cutout(frame, tmp_path / "c.png", center=(0.02, 0.98)).exists()


def test_cutout_of_a_non_image_raises(tmp_path):
    junk = tmp_path / "junk.jpg"
    junk.write_bytes(b"not an image")
    with pytest.raises(ThumbnailError):
        feathered_cutout(junk, tmp_path / "c.png")
