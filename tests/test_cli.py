"""Command-line surface.

These exist because a syntax error in cli.py once survived a full green test run:
nothing imported the module. Importing it and building the parser is the floor.
"""

import pytest

from ytupload import cli


def test_cli_module_imports():
    """The floor: a broken cli.py must fail here, not in front of the user."""
    assert cli.main is not None


def test_parser_builds():
    assert cli.build_parser() is not None


@pytest.mark.parametrize(
    "command", ["upload", "batch", "frames", "thumbnail", "auth"]
)
def test_every_command_parses_help(command):
    """--help exits 0 for each subcommand, proving its arguments are well formed."""
    with pytest.raises(SystemExit) as caught:
        cli.build_parser().parse_args([command, "--help"])
    assert caught.value.code == 0


def test_upload_requires_a_title():
    with pytest.raises(SystemExit):
        cli.main(["upload", "some.mp4"])


def test_thumbnail_accepts_hero_without_a_video():
    """Hero mode needs no video file, so the positional must be optional."""
    args = cli.build_parser().parse_args(["thumbnail", "--hero", "Mars"])
    assert args.hero == "Mars"
    assert args.video is None


def test_thumbnail_without_hero_or_video_is_rejected():
    with pytest.raises(SystemExit):
        cli.main(["thumbnail"])


def _thumbnail_args(*extra):
    return cli.build_parser().parse_args(["thumbnail", "--hero", "Mars", *extra])


def test_hero_art_prefers_a_local_wallpaper(tmp_path):
    wallpaper = tmp_path / "mars.jpg"
    wallpaper.write_bytes(b"x")
    assert cli._resolve_hero_art(_thumbnail_args(), wallpaper_dir=tmp_path) == wallpaper


def test_no_wallpaper_flag_skips_the_wallpaper(tmp_path, monkeypatch):
    (tmp_path / "mars.jpg").write_bytes(b"x")
    render = tmp_path / "render.png"
    monkeypatch.setattr(cli, "fetch_hero_art", lambda hero: render)
    args = _thumbnail_args("--no-wallpaper")
    assert cli._resolve_hero_art(args, wallpaper_dir=tmp_path) == render


def test_hero_art_falls_back_to_the_render(tmp_path, monkeypatch):
    render = tmp_path / "render.png"
    monkeypatch.setattr(cli, "fetch_hero_art", lambda hero: render)
    assert cli._resolve_hero_art(_thumbnail_args(), wallpaper_dir=tmp_path) == render


def test_explicit_hero_image_beats_the_wallpaper(tmp_path):
    (tmp_path / "mars.jpg").write_bytes(b"x")
    chosen = tmp_path / "chosen.png"
    chosen.write_bytes(b"x")
    args = _thumbnail_args("--hero-image", str(chosen))
    assert cli._resolve_hero_art(args, wallpaper_dir=tmp_path) == chosen


def test_upload_parses_a_full_argument_set():
    args = cli.build_parser().parse_args([
        "upload", "v.mp4",
        "--title", "T",
        "--tags", "a,b",
        "--preset", "dota-offlane",
        "--privacy", "unlisted",
        "--thumbnail", "t.jpg",
        "--archive",
        "--dry-run",
    ])
    assert args.thumbnail == "t.jpg"   # regression: --thumbnail was once unregistered
    assert args.archive is True
    assert args.privacy == "unlisted"


def test_upload_exposes_every_attribute_its_handler_reads():
    """Guards against a handler reading an argument the parser never defined."""
    args = cli.build_parser().parse_args(["upload", "v.mp4", "--title", "T"])
    for attribute in (
        "title", "description", "description_file", "tags", "preset", "playlist",
        "privacy", "made_for_kids", "thumbnail", "notify", "archive", "dry_run",
        "client_secret", "token_file",
    ):
        assert hasattr(args, attribute), f"parser is missing --{attribute}"


def test_batch_exposes_every_attribute_its_handler_reads():
    args = cli.build_parser().parse_args(["batch", "folder"])
    for attribute in ("ext", "min_duration", "archive", "dry_run", "title", "preset"):
        assert hasattr(args, attribute), f"parser is missing --{attribute}"


def test_batch_defaults_to_the_ten_minute_floor():
    args = cli.build_parser().parse_args(["batch", "folder"])
    assert args.min_duration == 600


def test_privacy_defaults_to_public():
    args = cli.build_parser().parse_args(["upload", "v.mp4", "--title", "T"])
    assert args.privacy == "public"


def test_thumbnail_has_no_result_flags():
    """A win/loss flag would put the outcome on the thumbnail, spoiling the video."""
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["thumbnail", "--hero", "Mars", "--won"])
