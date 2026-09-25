"""Parsing NVIDIA ShadowPlay capture filenames."""

from datetime import datetime

from ytupload.shadowplay import format_capture_date, parse_capture_time

# The real filename from the user's capture folder.
REAL_CAPTURE = "Dota 2 2026.09.25 - 21.59.04.14.mp4"


def test_parses_a_real_shadowplay_filename():
    assert parse_capture_time(REAL_CAPTURE) == datetime(2026, 9, 25, 21, 59, 4)


def test_parses_from_a_full_path():
    path = r"C:\Users\CHEN\Videos\NVIDIA\Dota 2\\" + REAL_CAPTURE
    assert parse_capture_time(path) == datetime(2026, 9, 25, 21, 59, 4)


def test_returns_none_for_an_unrelated_filename():
    assert parse_capture_time("my cool game.mp4") is None


def test_returns_none_for_a_well_shaped_but_impossible_date():
    """The pattern matches, but month 13 is not a date. Must not raise."""
    assert parse_capture_time("Dota 2 2026.13.45 - 99.99.99.01.mp4") is None


def test_directory_names_do_not_leak_into_the_match():
    """Only the filename is searched, so a dated folder cannot confuse it."""
    path = r"D:\2020.01.01 - 00.00.00\my cool game.mp4"
    assert parse_capture_time(path) is None


def test_formats_a_human_readable_date():
    assert format_capture_date(REAL_CAPTURE) == "25 September 2026"


def test_format_returns_none_when_unparseable():
    assert format_capture_date("clip.mp4") is None
