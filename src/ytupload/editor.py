"""Cutting a full match down to a watchable highlight edit.

The goal is not to detect kills accurately. It is to drop the least interesting
half of the midgame, which only needs a *relative* ranking of how eventful each
second is. That tolerance matters: a precise detector would be fragile, whereas a
noisy ranking still puts the fights above the farming.

Two signals are combined, both cheap:

**Audio**, as dB relative to a rolling baseline. Absolute loudness is a poor
discriminator because game audio is mixed to a fairly constant level, but a rise
*against its own local baseline* tracks fights well.

**The kill counters**, which sit at fixed positions in the HUD. Sampling only
keyframes and diffing those two small regions finds the moments the score moved,
with no OCR and no model. The clock between them is deliberately excluded: it
ticks every second and would otherwise register as constant change.
"""

from __future__ import annotations

import array
import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .video import VideoError, find_ffmpeg, probe_duration

Segment = Tuple[float, float]

# --- HUD geometry, as fractions of frame width/height -----------------------
# Measured on a 2560x1440 capture. Fractions rather than pixels so other capture
# resolutions work without change.
SCORE_STRIP = (0.4238, 0.0, 0.1172, 0.0444)  # x, y, w, h covering both counters
#: Columns of that strip holding the two counters. The clock sits between them
#: and is excluded, because it changes every second.
COUNTER_BANDS = ((0.2667, 0.3867), (0.9067, 1.0))

#: Dota counts down for 90 seconds between the HUD appearing and creeps spawning.
PREGAME_SECONDS = 90.0

#: Seconds of lead-in kept before the horn.
LEAD_IN = 15.0

DEFAULT_TARGET_MINUTES = 25.0
DEFAULT_LANE_MINUTES = 10.0

#: Segment shaping. These exist to keep each kept piece a coherent *scene*
#: rather than a clip of the kill itself. Early values were far too tight (6s of
#: padding, 10s minimum) and the result dropped viewers into the middle of fights
#: with no idea why anyone was there, then cut away before the outcome.
#:
#: A teamfight's run-up - the rotation, the positioning, the ward going down - is
#: most of what makes it readable, and it happens well before anyone dies.
MIN_SEGMENT = 30.0
PAD_BEFORE = 25.0
PAD_AFTER = 15.0

#: Generous, so related action becomes one continuous scene instead of several
#: rapid cuts. With the padding above, events within roughly a minute merge.
MERGE_GAP = 25.0

#: The run-up to the end of play, kept in every edit regardless of the target.
#: The user's rule: a match video must show how it ended. It is reserved before
#: anything is ranked, because the final push is often quieter on the kill
#: counter than the fights before it and would otherwise lose the ranking.
FINALE_SECONDS = 90.0

#: Kept after the HUD disappears. The score strip dims the moment the Ancient
#: falls, so this is the explosion and the "Victory" banner, not the menus.
VICTORY_SECONDS = 10.0

AUDIO_RATE = 8000

#: YouTube's recommended upload bitrate for 1440p60. Exceeding it costs upload
#: time and gains nothing, because YouTube re-encodes on ingest regardless.
MAX_BITRATE_MBPS = 24


class EditError(RuntimeError):
    """The edit could not be planned or rendered."""


@dataclass
class Analysis:
    """Everything measured from the video, before any decision is made."""

    duration: float
    game_start: float
    interest: List[float]
    #: When the Ancient fell, or None if no HUD was found (then a fixed tail trim
    #: is used instead).
    game_end: Optional[float] = None


# --------------------------------------------------------------------- audio


def audio_levels(video_path: Path, ffmpeg: Optional[str] = None) -> List[float]:
    """Per-second loudness in dB. Decodes audio only, so it is fast even on 8 GB."""
    ffmpeg = ffmpeg or find_ffmpeg()
    result = subprocess.run(
        [
            ffmpeg, "-v", "error", "-i", str(video_path),
            "-vn", "-ac", "1", "-ar", str(AUDIO_RATE), "-f", "s16le", "-",
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise EditError("could not read the audio track")

    samples = array.array("h")
    samples.frombytes(result.stdout[: len(result.stdout) // 2 * 2])

    levels: List[float] = []
    for index in range(len(samples) // AUDIO_RATE):
        chunk = samples[index * AUDIO_RATE : (index + 1) * AUDIO_RATE]
        mean_square = sum(value * value for value in chunk) / len(chunk)
        levels.append(20 * math.log10(max(math.sqrt(mean_square), 1.0)))
    return levels


def _smooth(values: Sequence[float], window: int) -> List[float]:
    out: List[float] = []
    for index in range(len(values)):
        start = max(0, index - window)
        end = min(len(values), index + window + 1)
        out.append(sum(values[start:end]) / (end - start))
    return out


def relative_loudness(levels: Sequence[float]) -> List[float]:
    """Loudness above each moment's own rolling baseline."""
    near = _smooth(levels, 3)
    baseline = _smooth(levels, 60)
    return [near[i] - baseline[i] for i in range(len(levels))]


# ----------------------------------------------------------------- hud strip


def extract_score_strip(
    video_path: Path, workdir: Path, ffmpeg: Optional[str] = None
) -> List[Tuple[float, Path]]:
    """Extract the kill-counter strip from every keyframe.

    ``-skip_frame nokey`` decodes only keyframes, which is what makes this
    affordable: a full decode of 40 minutes of 1440p60 would not be.
    """
    ffmpeg = ffmpeg or find_ffmpeg()
    workdir = Path(workdir)
    # Windows deletes asynchronously, so rmtree raises "directory is not empty"
    # whenever a handle is still open. Tolerate that, then clear leftover frames
    # individually: stale frames from a previous run would corrupt the analysis.
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)
    for stale in workdir.glob("*.jpg"):
        try:
            stale.unlink()
        except OSError:
            pass

    fps = _frame_rate(video_path, ffmpeg)
    x, y, w, h = SCORE_STRIP
    crop = f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},scale=150:32"

    result = subprocess.run(
        [
            ffmpeg, "-v", "error", "-skip_frame", "nokey", "-copyts",
            "-i", str(video_path),
            "-vf", crop, "-vsync", "0", "-frame_pts", "true", "-q:v", "4",
            str(workdir / "%d.jpg"),
        ],
        capture_output=True,
    )
    frames = sorted(workdir.glob("*.jpg"), key=lambda p: int(p.stem))
    if not frames:
        raise EditError(f"no frames extracted: {result.stderr.decode(errors='replace')[:200]}")
    # -frame_pts writes the presentation timestamp in frames, not seconds.
    return [(int(p.stem) / fps, p) for p in frames]


def _frame_rate(video_path: Path, ffmpeg: str) -> float:
    result = subprocess.run(
        [ffmpeg, "-i", str(video_path)], capture_output=True, text=True, errors="replace"
    )
    for token in result.stderr.split(","):
        if "fps" in token:
            try:
                return float(token.strip().split()[0])
            except (ValueError, IndexError):
                continue
    return 60.0


def _bands(image):
    """The two counter regions, thresholded so only the digits survive."""
    width = image.width
    out = []
    for left, right in COUNTER_BANDS:
        band = image.crop((int(width * left), 0, int(width * right), image.height))
        out.append(band.point(lambda value: 255 if value > 150 else 0))
    return out


def _looks_like_hud(path: Path) -> Optional[bool]:
    """Whether a score-strip crop shows the in-game HUD; None if unreadable.

    The strip is a dark panel carrying a little bright text. Loading screens,
    the victory banner (which dims it) and the post-game menus all fail this.
    """
    from PIL import Image

    try:
        pixels = list(Image.open(path).convert("L").get_flattened_data())
    except OSError:
        return None
    count = len(pixels)
    mean = sum(pixels) / count
    bright = sum(1 for value in pixels if value > 200) / count
    return mean < 110 and 0.004 < bright < 0.18


def detect_game_end(samples: Sequence[Tuple[float, Path]]) -> Optional[float]:
    """Return when play ended: the last frame of the last sustained HUD run.

    The mirror of :func:`detect_game_start`. Found from the HUD rather than by
    trimming a fixed tail, because how long the recording runs on after the
    Ancient falls varies, and a fixed trim once cut the winning push off.
    """
    run_end: Optional[float] = None
    run_length = 0
    for timestamp, path in reversed(samples):
        looks_like_hud = _looks_like_hud(path)
        if looks_like_hud is None:
            continue

        if looks_like_hud:
            if run_end is None:
                run_end = timestamp
            run_length += 1
            if run_length >= 8:  # sustained, not one lucky menu frame
                return run_end
        else:
            run_end = None
            run_length = 0
    return None


def detect_game_start(samples: Sequence[Tuple[float, Path]]) -> Optional[float]:
    """Return the estimated time of game clock 0:00.

    The HUD is absent during the intro cinematic and hero loading, and its score
    strip is a dark panel carrying a little bright text. The first sustained run
    of such frames is the moment the HUD appears; creeps spawn
    ``PREGAME_SECONDS`` later.
    """
    run_start: Optional[float] = None
    run_length = 0
    for timestamp, path in samples:
        looks_like_hud = _looks_like_hud(path)
        if looks_like_hud is None:
            continue

        if looks_like_hud:
            if run_start is None:
                run_start = timestamp
            run_length += 1
            if run_length >= 8:  # sustained, not one lucky frame
                return run_start + PREGAME_SECONDS
        else:
            run_start = None
            run_length = 0
    return None


def score_activity(
    samples: Sequence[Tuple[float, Path]], duration: float
) -> List[float]:
    """Per-second activity derived from changes in the kill counters."""
    from PIL import Image, ImageChops

    activity = [0.0] * int(duration + 1)
    previous = None
    for timestamp, path in samples:
        try:
            current = _bands(Image.open(path).convert("L"))
        except OSError:
            continue
        if previous is not None:
            changed = 0
            for before, after in zip(previous, current):
                difference = ImageChops.difference(before, after)
                changed += sum(1 for value in difference.get_flattened_data() if value > 100)
            index = int(timestamp)
            if changed > 6 and 0 <= index < len(activity):
                activity[index] = max(activity[index], min(changed / 20.0, 3.0))
        previous = current
    return activity


def spread_activity(activity: Sequence[float]) -> List[float]:
    """Widen each spike into the seconds around it: a fight has a run-up."""
    out = [0.0] * len(activity)
    for index, value in enumerate(activity):
        if value <= 0:
            continue
        for offset in range(-14, 9):
            position = index + offset
            if 0 <= position < len(out):
                out[position] = max(out[position], value * (1 - abs(offset) / 20))
    return out


# -------------------------------------------------------------------- analysis


def analyse(
    video_path: Path, workdir: Path, ffmpeg: Optional[str] = None
) -> Analysis:
    """Measure the video. Makes no editing decisions."""
    video_path = Path(video_path)
    duration = probe_duration(video_path)
    if duration is None:
        raise EditError(f"could not read the duration of {video_path}")

    levels = audio_levels(video_path, ffmpeg)
    loudness = relative_loudness(levels)

    samples = extract_score_strip(video_path, workdir, ffmpeg)
    game_start = detect_game_start(samples)
    if game_start is None:
        # No HUD found: fall back to the start rather than refusing to work.
        game_start = 0.0
    game_end = detect_game_end(samples)
    activity = spread_activity(score_activity(samples, duration))

    length = int(duration)
    interest = [
        max(loudness[i] if i < len(loudness) else 0.0, 0.0) * 0.6
        + (activity[i] if i < len(activity) else 0.0) * 2.0
        for i in range(length)
    ]
    return Analysis(
        duration=duration, game_start=game_start, interest=interest, game_end=game_end
    )


# --------------------------------------------------------------------- planning


def _segments_above(
    interest: Sequence[float], threshold: float, start: float, end: float
) -> List[Segment]:
    keep: List[Segment] = []
    index = int(start)
    limit = int(end)
    while index < limit:
        if interest[index] >= threshold:
            begin = max(start, index - PAD_BEFORE)
            while index < limit and interest[index] >= threshold:
                index += 1
            finish = min(end, index + PAD_AFTER)
            if keep and begin - keep[-1][1] <= MERGE_GAP:
                keep[-1] = (keep[-1][0], finish)
            else:
                keep.append((begin, finish))
        else:
            index += 1
    return [(a, b) for a, b in keep if b - a >= MIN_SEGMENT]


def plan(
    analysis: Analysis,
    target_minutes: float = DEFAULT_TARGET_MINUTES,
    lane_minutes: float = DEFAULT_LANE_MINUTES,
    tail_trim: float = 40.0,
) -> List[Segment]:
    """Choose which parts to keep.

    The finale - the run-up to the end of play - is reserved first and is in
    every edit. The laning phase is kept whole from just before the horn, unless
    the finale leaves too little room, in which case laning is what gives way.
    What lies between is ranked by interest and the threshold is solved by
    bisection so the total lands on the target.

    Play ends at ``analysis.game_end`` when the HUD was found. Otherwise
    *tail_trim* drops a fixed tail, which is the post-game scoreboard and
    reward screens rather than play.
    """
    start = max(analysis.game_start - LEAD_IN, 0.0)
    lane_end = min(analysis.game_start + lane_minutes * 60, analysis.duration)
    if analysis.game_end is not None:
        end = min(analysis.game_end + VICTORY_SECONDS, analysis.duration)
    else:
        end = analysis.duration - tail_trim
    end = max(end, lane_end)
    target = target_minutes * 60

    finale_start = max(end - FINALE_SECONDS, lane_end, end - target)
    finale = [(finale_start, end)] if end > finale_start else []
    finale_length = end - finale_start

    if lane_end - start >= target - finale_length:
        # Laning and the finale already fill the budget.
        return [(start, start + max(target - finale_length, 0.0))] + finale

    budget = target - (lane_end - start) - finale_length

    def fits(threshold: float) -> bool:
        """Whether this threshold produces an edit within the budget."""
        segments = _segments_above(analysis.interest, threshold, lane_end, finale_start)
        return sum(b - a for a, b in segments) <= budget

    # `high` must be a threshold that definitely fits, because it is what gets
    # returned. The comparison is >=, so the ceiling has to sit strictly above
    # every value or the very first iteration already breaks the invariant and an
    # over-budget cut can be returned when nothing fits.
    low = 0.0
    high = (max(analysis.interest) if analysis.interest else 1.0) + 1.0
    for _ in range(40):
        middle = (low + high) / 2
        if fits(middle):
            high = middle
        else:
            low = middle

    highlights = _segments_above(analysis.interest, high, lane_end, finale_start)
    if highlights and finale and highlights[-1][1] >= finale_start:
        # A fight running into the final push is one scene. They only touch, so
        # merging adds no runtime.
        finale = [(highlights.pop()[0], end)]
    return [(start, lane_end)] + highlights + finale


def describe(segments: Sequence[Segment]) -> str:
    """Human-readable cut list."""
    def stamp(seconds: float) -> str:
        return f"{int(seconds // 60)}:{int(seconds % 60):02d}"

    lines = [f"  {stamp(a)} - {stamp(b)}   ({b - a:.0f}s)" for a, b in segments]
    total = sum(b - a for a, b in segments)
    lines.append(f"  total: {total / 60:.1f} min across {len(segments)} segments")
    return "\n".join(lines)


# -------------------------------------------------------------------- rendering


def has_nvenc(ffmpeg: Optional[str] = None) -> bool:
    ffmpeg = ffmpeg or find_ffmpeg()
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, errors="replace"
    )
    return "h264_nvenc" in result.stdout


def render(
    video_path: Path,
    segments: Sequence[Segment],
    output_path: Path,
    workdir: Path,
    ffmpeg: Optional[str] = None,
    quality: int = 26,
    on_progress=None,
) -> Path:
    """Cut the segments out and join them into one file.

    Each segment is re-encoded so cuts are frame-accurate rather than snapping to
    keyframes, then the pieces are concatenated with a stream copy. NVENC is used
    when present, which is the difference between minutes and most of an hour on
    1440p60 footage.
    """
    ffmpeg = ffmpeg or find_ffmpeg()
    video_path = Path(video_path)
    output_path = Path(output_path)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    if not segments:
        raise EditError("nothing to render: the cut list is empty")

    # Without a ceiling, NVENC at a low cq happily spends *more* bits than the
    # source, so the cut ends up barely smaller than the original. YouTube
    # recommends 24 Mbps for 1440p60 and re-encodes everything anyway, so
    # anything above that is upload time bought for nothing.
    cap = ["-maxrate", f"{MAX_BITRATE_MBPS}M", "-bufsize", f"{MAX_BITRATE_MBPS * 2}M"]
    if has_nvenc(ffmpeg):
        video_args = [
            "-c:v", "h264_nvenc", "-preset", "p5",
            "-rc", "vbr", "-cq", str(quality), "-b:v", "0", *cap,
        ]
    else:
        video_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(quality), *cap]

    pieces: List[Path] = []
    for index, (begin, finish) in enumerate(segments):
        piece = workdir / f"part{index:03d}.mp4"
        command = [
            ffmpeg, "-v", "error", "-y",
            "-ss", f"{begin:.3f}", "-i", str(video_path), "-t", f"{finish - begin:.3f}",
            *video_args,
            "-c:a", "aac", "-b:a", "192k",
            "-avoid_negative_ts", "make_zero",
            str(piece),
        ]
        result = subprocess.run(command, capture_output=True, text=True, errors="replace")
        if result.returncode != 0 or not piece.exists():
            raise EditError(
                f"segment {index} ({begin:.0f}s-{finish:.0f}s) failed: "
                f"{result.stderr.strip()[:300]}"
            )
        pieces.append(piece)
        if on_progress:
            on_progress(index + 1, len(segments))

    listing = workdir / "parts.txt"
    listing.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in pieces), encoding="utf-8"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            ffmpeg, "-v", "error", "-y", "-f", "concat", "-safe", "0",
            "-i", str(listing), "-c", "copy", str(output_path),
        ],
        capture_output=True, text=True, errors="replace",
    )
    if result.returncode != 0 or not output_path.exists():
        raise EditError(f"joining segments failed: {result.stderr.strip()[:300]}")

    shutil.rmtree(workdir, ignore_errors=True)
    return output_path


def save_plan(segments: Sequence[Segment], path: Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps([list(s) for s in segments], indent=2), encoding="utf-8")
    return path

# -------------------------------------------------------------------- chapters

#: YouTube only renders chapters when the first is 0:00, there are at least
#: three, and each runs 10 seconds or longer.
MIN_CHAPTERS = 3
MIN_CHAPTER_SECONDS = 10.0


def timestamp(seconds: float) -> str:
    """Format as M:SS, or H:MM:SS past an hour, which is what YouTube parses."""
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def chapters_for(
    segments: Sequence[Segment], game_start: float
) -> List[Tuple[float, float]]:
    """Map each kept scene to (position in the edit, in-game clock).

    Cutting makes the in-game clock jump, which is exactly the orientation a
    viewer loses. Pairing each chapter with the real game time gives it back.
    """
    # One chapter per kept scene, marked at the cut. Offsetting the mark past
    # the run-up was tried and reverted: it pushed each scene's opening seconds
    # into the previous chapter, so the sections on the progress bar no longer
    # lined up with the edit at all. A chapter is a scene; label it as one.
    chapters: List[Tuple[float, float]] = []
    elapsed = 0.0
    for begin, end in segments:
        chapters.append((elapsed, max(begin - game_start, 0.0)))
        elapsed += end - begin
    return chapters


def render_chapters(
    chapters: Sequence[Tuple[float, float]],
    labels: Optional[Sequence[str]] = None,
) -> str:
    """Render chapters as the timestamp list YouTube parses from a description.

    Without *labels* each chapter is named after its in-game clock. That is
    accurate but dull: the tool cannot know what happened, so the intent is that
    the labels are replaced with real descriptions before publishing.
    """
    if len(chapters) < MIN_CHAPTERS:
        return ""

    lines: List[str] = []
    for index, (position, game_clock) in enumerate(chapters):
        if labels and index < len(labels) and labels[index].strip():
            text = labels[index].strip()
        elif index == 0:
            text = "Laning phase"
        else:
            text = f"Game clock {timestamp(game_clock)}"
        # The first chapter must start at 0:00 or YouTube ignores the whole set.
        lines.append(f"{timestamp(position if index else 0)} {text}")
    return "\n".join(lines)


def write_chapters(
    segments: Sequence[Segment], game_start: float, path: Path
) -> Optional[Path]:
    """Write a chapters file beside the edit, or None if there are too few."""
    text = render_chapters(chapters_for(segments, game_start))
    if not text:
        return None
    path = Path(path)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def full_video_chapters(
    segments: Sequence[Segment], game_start: float
) -> Tuple[List[Tuple[float, float]], List[str]]:
    """Chapters for the *uncut* recording: one mark where each planned scene starts.

    The user chose to upload whole matches rather than a cut, because a cut can
    lose something that mattered. The same plan still finds the fights and the
    ending; here it only decides where the chapter marks go, and nothing is
    dropped. Marks are in the recording's own timeline.
    """
    chapters: List[Tuple[float, float]] = []
    labels: List[str] = []
    lane_start = segments[0][0] if segments else 0.0
    # The loading screen and pre-game countdown get their own chapter, unless it
    # would be shorter than YouTube's minimum, which would void every chapter.
    if lane_start >= MIN_CHAPTER_SECONDS:
        chapters.append((0.0, 0.0))
        labels.append("Pre-game")
    for index, (begin, _) in enumerate(segments):
        chapters.append((begin, max(begin - game_start, 0.0)))
        labels.append("Laning phase" if index == 0 else "")
    return chapters, labels


def write_full_video_chapters(
    segments: Sequence[Segment], game_start: float, path: Path
) -> Optional[Path]:
    """Write chapters for the uncut recording, or None if there are too few."""
    chapters, labels = full_video_chapters(segments, game_start)
    text = render_chapters(chapters, labels)
    if not text:
        return None
    path = Path(path)
    path.write_text(text + "\n", encoding="utf-8")
    return path
