"""Shared fixtures.

Tests that need a video generate a tiny real one with ffmpeg rather than shipping a
binary fixture. It is small and short, so the cost is a fraction of a second, and it
exercises the genuine ffmpeg code path instead of a mock.
"""

import subprocess

import pytest

from ytupload.video import find_ffmpeg


def _make_video(path, seconds, width=320, height=240):
    subprocess.run(
        [
            find_ffmpeg(), "-v", "error",
            "-f", "lavfi",
            "-i", f"testsrc=size={width}x{height}:rate=10:duration={seconds}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-y", str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


@pytest.fixture(scope="session")
def short_video(tmp_path_factory):
    """A 3-second capture: below any sane minimum duration."""
    path = tmp_path_factory.mktemp("videos") / "short.mp4"
    return _make_video(path, seconds=3)


@pytest.fixture(scope="session")
def long_video(tmp_path_factory):
    """A 12-second capture, used with a low threshold to stand in for a real match."""
    path = tmp_path_factory.mktemp("videos") / "long.mp4"
    return _make_video(path, seconds=12)
