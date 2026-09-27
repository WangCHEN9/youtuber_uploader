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


def test_rim_glow_separates_the_hero_from_the_background(art, tmp_path):
    """The halo follows the art's alpha, so it must react to the accent colour."""
    warm = make_splash_thumbnail(art, tmp_path / "warm.jpg", accent=(230, 90, 30))
    cool = make_splash_thumbnail(art, tmp_path / "cool.jpg", accent=(40, 170, 220))
    assert warm.read_bytes() != cool.read_bytes()


def test_output_is_rgb_jpeg(art, tmp_path):
    out = make_splash_thumbnail(art, tmp_path / "t.jpg")
    assert Image.open(out).mode == "RGB"


# ------------------------------------------------- opaque art (wallpapers)


@pytest.fixture
def wallpaper(tmp_path):
    """An opaque rectangular image, like a downloaded wallpaper."""
    image = Image.new("RGB", (2560, 1440), (30, 20, 15))
    image.paste((200, 80, 20), (800, 300, 1800, 1100))
    path = tmp_path / "wall.jpg"
    image.save(path, quality=92)
    return path


def test_opaque_art_is_detected(wallpaper, tmp_path):
    from ytupload.splash import _is_opaque

    assert _is_opaque(Image.open(wallpaper).convert("RGBA")) is True


def test_cutout_art_is_not_treated_as_opaque(art):
    from ytupload.splash import _is_opaque

    assert _is_opaque(Image.open(art)) is False


def test_wallpaper_produces_a_valid_thumbnail(wallpaper, tmp_path):
    out = make_splash_thumbnail(wallpaper, tmp_path / "t.jpg")
    assert Image.open(out).size == THUMBNAIL_SIZE
    assert out.stat().st_size <= MAX_BYTES


def test_a_non_16_9_wallpaper_is_cover_cropped(tmp_path):
    """Letterboxing or stretching would look broken."""
    tall = tmp_path / "tall.png"
    Image.new("RGB", (900, 1600), (40, 60, 90)).save(tall)
    out = make_splash_thumbnail(tall, tmp_path / "t.jpg")
    assert Image.open(out).size == THUMBNAIL_SIZE


def test_badges_work_over_a_wallpaper(wallpaper, badge, tmp_path):
    plain = make_splash_thumbnail(wallpaper, tmp_path / "p.jpg")
    badged = make_splash_thumbnail(wallpaper, tmp_path / "b.jpg", badge_paths=[badge])
    assert plain.read_bytes() != badged.read_bytes()


def test_no_badges_means_no_left_scrim(wallpaper, tmp_path):
    """A clean wallpaper should not be dimmed for badges that are not there."""
    out = make_splash_thumbnail(wallpaper, tmp_path / "t.jpg")
    image = Image.open(out)
    left = image.crop((0, 300, 60, 420)).convert("L")
    right = image.crop((1220, 300, 1280, 420)).convert("L")
    left_mean = sum(left.getdata()) / (left.width * left.height)
    right_mean = sum(right.getdata()) / (right.width * right.height)
    # Symmetric vignette: neither edge should be dramatically darker than the other.
    assert abs(left_mean - right_mean) < 25


# ------------------------------------------------------------ badge layout


def test_badges_run_down_a_diagonal_not_a_straight_column(art, badge, tmp_path):
    """Measured off the reference thumbnail: each badge steps right as it steps down."""
    from ytupload.splash import BADGE_MARGIN_X, BADGE_X_STEP

    assert BADGE_X_STEP > 0
    assert BADGE_MARGIN_X > 0
    out = make_splash_thumbnail(art, tmp_path / "t.jpg", badge_paths=[badge, badge])
    assert Image.open(out).size == THUMBNAIL_SIZE


def test_badge_diameter_shrinks_as_badges_are_added():
    """Three badges must still fit the height, so they cannot stay full size."""
    from ytupload.splash import BADGE_DIAMETERS

    assert BADGE_DIAMETERS[1] >= BADGE_DIAMETERS[2] > BADGE_DIAMETERS[3]


def test_three_badges_fit_within_the_canvas():
    from ytupload.splash import BADGE_DIAMETERS, BADGE_SPAN

    assert 3 * BADGE_DIAMETERS[3] <= BADGE_SPAN


def test_badges_are_large_enough_to_read_at_sidebar_size(art, badge, tmp_path):
    """A badge under ~20% of the height disappears in a YouTube sidebar."""
    from ytupload.splash import BADGE_DIAMETERS

    assert min(BADGE_DIAMETERS.values()) >= 0.20


# ------------------------------------------------------------- brand mark


@pytest.fixture
def mascot(tmp_path):
    path = tmp_path / "mascot.png"
    Image.new("RGB", (600, 600), (180, 150, 110)).save(path)
    return path


def test_brand_mark_changes_the_image(art, mascot, tmp_path):
    plain = make_splash_thumbnail(art, tmp_path / "p.jpg")
    branded = make_splash_thumbnail(art, tmp_path / "b.jpg", brand_path=mascot)
    assert plain.read_bytes() != branded.read_bytes()


def test_brand_mark_lands_in_the_bottom_right(art, mascot, tmp_path):
    """Diagonally opposite the badges, so the two can never collide."""
    plain = Image.open(make_splash_thumbnail(art, tmp_path / "p.jpg"))
    branded = Image.open(make_splash_thumbnail(art, tmp_path / "b.jpg", brand_path=mascot))
    box = (1140, 580, 1260, 700)
    assert list(plain.crop(box).getdata()) != list(branded.crop(box).getdata())
    # The top-left, where badges live, must be untouched by the brand mark.
    top_left = (0, 0, 120, 120)
    assert list(plain.crop(top_left).getdata()) == list(branded.crop(top_left).getdata())


def test_brand_mark_coexists_with_badges(art, mascot, badge, tmp_path):
    out = make_splash_thumbnail(
        art, tmp_path / "t.jpg", badge_paths=[badge, badge], brand_path=mascot
    )
    assert Image.open(out).size == THUMBNAIL_SIZE


def test_a_non_square_mascot_is_cropped_not_squashed(art, tmp_path):
    wide = tmp_path / "wide.png"
    Image.new("RGB", (1200, 400), (90, 120, 70)).save(wide)
    out = make_splash_thumbnail(art, tmp_path / "t.jpg", brand_path=wide)
    assert Image.open(out).size == THUMBNAIL_SIZE


def test_an_unreadable_mascot_raises(art, tmp_path):
    junk = tmp_path / "junk.png"
    junk.write_bytes(b"not an image")
    with pytest.raises(ThumbnailError, match="brand image"):
        make_splash_thumbnail(art, tmp_path / "t.jpg", brand_path=junk)


def test_brand_mark_is_small_enough_to_stay_a_mark(art, tmp_path):
    """It is identity, not information; it must not rival the hero."""
    from ytupload.splash import BADGE_DIAMETERS, BRAND_DIAMETER

    assert BRAND_DIAMETER < min(BADGE_DIAMETERS.values())
