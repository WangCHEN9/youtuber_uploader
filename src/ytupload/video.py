"""Reading video files: duration and still frames.

Uses ffmpeg. A system ffmpeg on PATH wins if present; otherwise the binary shipped
by the ``imageio-ffmpeg`` wheel is used, which needs no admin rights to install.

Only ffmpeg is required. ``ffprobe`` is used when available, but duration falls back
to parsing ffmpeg's own output, because the imageio-ffmpeg wheel ships ffmpeg alone.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

#: Below this, a capture is a clip or a misfire rather than a match.
DEFAULT_MIN_DURATION_SECONDS = 600  # 10 minutes

_DURATION_PATTERN = re.compile(
    r"Duration:\s*(?P<hours>\d+):(?P<minutes>\d{2}):(?P<seconds>\d{2}\.?\d*)"
)


class VideoError(RuntimeError):
    """ffmpeg is unavailable, or a video could not be read."""


def find_ffmpeg() -> str:
    """Return a usable ffmpeg executable path."""
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg
    except ImportError as error:  # pragma: no cover - depends on install
        raise VideoError(
            "ffmpeg not found. Install it, or run: pip install imageio-ffmpeg"
        ) from error
    return imageio_ffmpeg.get_ffmpeg_exe()


def find_ffprobe() -> Optional[str]:
    """Return ffprobe if the system has one. It is an optimisation, not a requirement."""
    return shutil.which("ffprobe")


def _run(command: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, errors="replace")


def probe_duration(video_path: Path) -> Optional[float]:
    """Return the video duration in seconds, or ``None`` if it cannot be determined.

    Reads container metadata only, so it is fast even on multi-gigabyte files.
    """
    video_path = Path(video_path)
    if not video_path.is_file():
        raise VideoError(f"not a file: {video_path}")

    ffprobe = find_ffprobe()
    if ffprobe:
        result = _run([
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(video_path),
        ])
        if result.returncode == 0:
            try:
                value = json.loads(result.stdout)["format"]["duration"]
                return float(value)
            except (KeyError, ValueError, json.JSONDecodeError):
                pass  # Fall through to the ffmpeg parse below.

    # ffmpeg with no output target exits non-zero but still prints the duration.
    result = _run([find_ffmpeg(), "-i", str(video_path)])
    match = _DURATION_PATTERN.search(result.stderr)
    if match is None:
        return None
    return (
        int(match.group("hours")) * 3600
        + int(match.group("minutes")) * 60
        + float(match.group("seconds"))
    )


def format_duration(seconds: Optional[float]) -> str:
    """Render seconds as ``H:MM:SS`` or ``M:SS``, or ``unknown``."""
    if seconds is None:
        return "unknown"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def is_long_enough(
    video_path: Path, minimum_seconds: float = DEFAULT_MIN_DURATION_SECONDS
) -> bool:
    """Whether the video is worth uploading.

    An unreadable duration returns ``True``: refusing to upload because the probe
    failed would be worse than uploading something short.
    """
    duration = probe_duration(video_path)
    if duration is None:
        return True
    return duration >= minimum_seconds


def extract_frame(
    video_path: Path, timestamp_seconds: float, output_path: Path, width: int = 1280
) -> Path:
    """Write a single still frame from *timestamp_seconds* to *output_path*."""
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = _run([
        find_ffmpeg(),
        # -ss before -i seeks by keyframe index rather than decoding from the
        # start, which is the difference between instant and several minutes.
        "-ss", f"{max(timestamp_seconds, 0):.3f}",
        "-i", str(video_path),
        "-frames:v", "1",
        "-vf", f"scale={width}:-2",
        # Some frames carry a limited-range colour tag that the mjpeg encoder
        # refuses ("Non full-range YUV is non-standard"), failing the whole
        # extraction. Forcing the JPEG-range pixel format accepts them all.
        "-pix_fmt", "yuvj420p",
        "-q:v", "2",
        "-y", str(output_path),
    ])
    if result.returncode != 0 or not output_path.exists():
        raise VideoError(
            f"could not extract a frame at {timestamp_seconds:.0f}s: "
            f"{result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'unknown error'}"
        )
    return output_path


def extract_review_frames(video_path: Path, output_dir: Path) -> List[Path]:
    """Extract frames chosen to identify what happened in the match.

    Ordered most informative first. The post-game scoreboard is the single richest
    frame: heroes, scores, duration and outcome all at once. It is sampled slightly
    before the very end, since captures often trail off into a menu or black frames.
    """
    duration = probe_duration(video_path)
    output_dir = Path(output_dir)

    if duration is None:
        offsets = {"early": 120.0}
    else:
        offsets = {
            "scoreboard": max(duration - 25, 0),   # post-game screen
            "midgame": duration * 0.55,            # a teamfight, likely
            "laning": min(duration * 0.10, 420),   # the lane matchup
        }

    frames: List[Path] = []
    for name, offset in offsets.items():
        target = output_dir / f"{name}.jpg"
        try:
            frames.append(extract_frame(video_path, offset, target))
        except VideoError:
            continue  # A single unreadable offset must not sink the whole set.
    return frames
