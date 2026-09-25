"""Reading duration and frames out of real video files via ffmpeg."""

import pytest

from ytupload.video import (
    VideoError,
    extract_frame,
    extract_review_frames,
    format_duration,
    is_long_enough,
    probe_duration,
)


# ------------------------------------------------------------ format_duration


def test_formats_minutes_and_seconds():
    assert format_duration(90) == "1:30"


def test_formats_hours_when_present():
    assert format_duration(3725) == "1:02:05"


def test_formats_unknown_duration():
    assert format_duration(None) == "unknown"


def test_formats_zero():
    assert format_duration(0) == "0:00"


# -------------------------------------------------------------- probe_duration


def test_probes_a_real_duration(short_video):
    duration = probe_duration(short_video)
    assert duration == pytest.approx(3, abs=0.5)


def test_probing_a_missing_file_raises(tmp_path):
    with pytest.raises(VideoError, match="not a file"):
        probe_duration(tmp_path / "nope.mp4")


def test_probing_a_non_video_returns_none(tmp_path):
    junk = tmp_path / "not-a-video.mp4"
    junk.write_bytes(b"definitely not h264")
    assert probe_duration(junk) is None


# --------------------------------------------------------------- is_long_enough


def test_short_capture_is_rejected(short_video):
    assert is_long_enough(short_video, minimum_seconds=600) is False


def test_capture_above_the_threshold_is_accepted(long_video):
    assert is_long_enough(long_video, minimum_seconds=5) is True


def test_unreadable_duration_is_allowed_through(tmp_path):
    """Failing to probe must not silently discard a real match."""
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video")
    assert is_long_enough(junk, minimum_seconds=600) is True


# --------------------------------------------------------------- extract_frame


def test_extracts_a_frame(long_video, tmp_path):
    output = extract_frame(long_video, 1.0, tmp_path / "frame.jpg")
    assert output.exists()
    assert output.stat().st_size > 0


def test_creates_the_output_directory(long_video, tmp_path):
    output = extract_frame(long_video, 1.0, tmp_path / "deep" / "nested" / "f.jpg")
    assert output.exists()


def test_negative_timestamp_is_clamped(long_video, tmp_path):
    assert extract_frame(long_video, -5, tmp_path / "f.jpg").exists()


def test_extracting_from_a_non_video_raises(tmp_path):
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video")
    with pytest.raises(VideoError):
        extract_frame(junk, 1.0, tmp_path / "f.jpg")


# -------------------------------------------------------- extract_review_frames


def test_review_frames_cover_the_match(long_video, tmp_path):
    frames = extract_review_frames(long_video, tmp_path)
    assert len(frames) == 3
    assert {frame.stem for frame in frames} == {"scoreboard", "midgame", "laning"}
    assert all(frame.stat().st_size > 0 for frame in frames)


def test_review_frames_degrade_rather_than_fail(tmp_path):
    """An unreadable file yields no frames, but must not raise."""
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video")
    assert extract_review_frames(junk, tmp_path) == []
