"""Command-line interface.

Run ``python -m ytupload --help`` for usage.

``--dry-run`` deliberately needs no credentials: it assembles and validates the
request exactly as a real run would, then prints it instead of sending it. That makes
it a genuine rehearsal, and it costs no API quota.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from .auth import (
    DEFAULT_CLIENT_SECRET_FILE,
    DEFAULT_TOKEN_FILE,
    AuthError,
    build_youtube_service,
)
from .metadata import PRIVACY_CHOICES, MetadataError, VideoMetadata
from .editor import (
    DEFAULT_LANE_MINUTES,
    DEFAULT_TARGET_MINUTES,
    EditError,
    analyse,
    describe,
    has_nvenc,
    plan,
    render,
    save_plan,
)
from .heroart import (
    HeroArtError,
    dominant_color,
    fetch_badge_icon,
    fetch_hero_art,
)
from .presets import PRESETS
from .shadowplay import format_capture_date
from .splash import make_splash_thumbnail
from .thumbnail import (
    DOTA_HUD_TRIM_BOTTOM,
    DOTA_HUD_TRIM_TOP,
    ThumbnailError,
    make_hero_thumbnail,
    make_thumbnail,
)
from .uploader import MAX_UPLOADS_PER_RUN, QUOTA_PER_UPLOAD, YoutubeUploader
from .video import (
    DEFAULT_MIN_DURATION_SECONDS,
    VideoError,
    extract_frame,
    extract_review_frames,
    format_duration,
    probe_duration,
)

_MIB = 1024 * 1024

#: Frames past this fraction of a match usually reveal the outcome, so the thumbnail
#: command refuses them unless explicitly overridden.
SPOILER_FRACTION = 0.8


# --------------------------------------------------------------------- helpers


def _split_tags(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [tag.strip() for tag in raw.split(",") if tag.strip()]


def _read_description(args: argparse.Namespace) -> str:
    if args.description_file:
        path = Path(args.description_file)
        if not path.is_file():
            raise SystemExit(f"error: description file not found: {path}")
        return path.read_text(encoding="utf-8").strip()
    return (args.description or "").strip()


def _build_metadata(
    args: argparse.Namespace, video_path: Path, title: Optional[str] = None
) -> VideoMetadata:
    """Assemble metadata from arguments, the chosen preset, and the filename.

    *title* overrides ``args.title`` so batch runs can derive a per-video title
    without mutating the shared argument namespace.
    """
    preset = PRESETS.get(args.preset) if args.preset else None

    tags = _split_tags(args.tags)
    if preset:
        # Preset tags first, then per-video tags, de-duplicated case-insensitively.
        merged: List[str] = []
        seen = set()
        for tag in list(preset.tags) + tags:
            if tag.lower() not in seen:
                seen.add(tag.lower())
                merged.append(tag)
        tags = merged

    description = _read_description(args)

    captured = format_capture_date(video_path.name)
    if captured:
        description = f"{description}\n\nRecorded {captured}.".strip()

    if preset and preset.description_footer:
        description = f"{description}\n\n{preset.description_footer}".strip()

    return VideoMetadata(
        title=title if title is not None else args.title,
        description=description,
        tags=tags,
        privacy=args.privacy,
        made_for_kids=args.made_for_kids,
    )


def _resolve_playlist(args: argparse.Namespace) -> Optional[str]:
    if args.playlist:
        return args.playlist
    preset = PRESETS.get(args.preset) if args.preset else None
    return preset.playlist if preset else None


def _print_plan(video_path: Path, metadata: VideoMetadata, playlist: Optional[str]) -> None:
    size_mib = video_path.stat().st_size / _MIB if video_path.is_file() else 0
    print(f"\nfile      : {video_path}")
    print(f"size      : {size_mib:,.0f} MiB")
    print(f"privacy   : {metadata.privacy.upper()}")
    print(f"playlist  : {playlist or '(none)'}")
    print(f"quota     : ~{QUOTA_PER_UPLOAD} units of {MAX_UPLOADS_PER_RUN} uploads/day")
    print("\nrequest body:")
    print(json.dumps(metadata.to_request_body(), indent=2, ensure_ascii=False))


# -------------------------------------------------------------------- commands


def _attach_extras(
    uploader: YoutubeUploader,
    video_id: str,
    playlist: Optional[str],
    thumbnail: Optional[str],
) -> None:
    """Best-effort post-upload steps: the video is already safely uploaded."""
    if playlist:
        try:
            playlist_id = uploader.find_or_create_playlist(playlist)
            uploader.add_to_playlist(video_id, playlist_id)
            print(f"  added to playlist {playlist!r}")
        except Exception as error:  # noqa: BLE001 - never lose a completed upload
            print(f"  warning: could not add to playlist: {error}", file=sys.stderr)

    if thumbnail:
        try:
            uploader.set_thumbnail(video_id, Path(thumbnail))
            print("  thumbnail set")
        except Exception as error:  # noqa: BLE001
            print(f"  warning: could not set thumbnail: {error}", file=sys.stderr)


def cmd_upload(args: argparse.Namespace) -> int:
    video_path = Path(args.video)
    if not video_path.is_file():
        raise SystemExit(f"error: not a file: {video_path}")

    try:
        metadata = _build_metadata(args, video_path)
        metadata.validate()
    except MetadataError as error:
        raise SystemExit(f"error: invalid metadata: {error}")

    playlist = _resolve_playlist(args)
    _print_plan(video_path, metadata, playlist)

    if args.dry_run:
        print("\ndry run: nothing was uploaded.")
        return 0

    uploader = YoutubeUploader(
        client_secret_file=Path(args.client_secret),
        token_file=Path(args.token_file),
    )
    print(f"\nuploading {video_path.name} ...")
    video_id = uploader.upload_video(
        video_path, metadata, notify_subscribers=args.notify
    )
    print(f"\ndone: https://youtu.be/{video_id}")
    _attach_extras(uploader, video_id, playlist, args.thumbnail)
    if args.archive:
        uploader.archive_uploaded(video_path)
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    folder = Path(args.folder)
    if not folder.is_dir():
        raise SystemExit(f"error: not a directory: {folder}")

    limit = min(args.limit, MAX_UPLOADS_PER_RUN)

    if args.dry_run:
        # Listing candidates needs the tracker but not the network, so build a
        # tracker-only uploader with no service rather than authenticating.
        uploader = YoutubeUploader(service=object())
    else:
        uploader = YoutubeUploader(
            client_secret_file=Path(args.client_secret),
            token_file=Path(args.token_file),
        )

    pending = uploader.find_new_videos(
        folder,
        extensions=_split_tags(args.ext) or [".mp4"],
        min_duration_seconds=args.min_duration,
    )
    if not pending:
        print("nothing new to upload.")
        if args.min_duration:
            print(
                f"(clips shorter than {format_duration(args.min_duration)} "
                "were excluded; pass --min-duration 0 to include them)"
            )
        return 0

    print(f"{len(pending)} new video(s); uploading up to {limit}.")
    playlist = _resolve_playlist(args)
    failures = 0

    for index, video_path in enumerate(pending[:limit], start=1):
        # Derived locally: assigning to args.title would leak into later iterations.
        title = args.title or video_path.stem
        try:
            metadata = _build_metadata(args, video_path, title=title)
            metadata.validate()
        except MetadataError as error:
            print(f"[{index}] skipping {video_path.name}: {error}", file=sys.stderr)
            failures += 1
            continue

        print(f"\n[{index}/{min(limit, len(pending))}] {video_path.name}")
        if args.dry_run:
            _print_plan(video_path, metadata, playlist)
            continue

        try:
            video_id = uploader.upload_video(
                video_path, metadata, notify_subscribers=args.notify
            )
            print(f"  done: https://youtu.be/{video_id}")
            _attach_extras(uploader, video_id, playlist, None)
            if args.archive:
                uploader.archive_uploaded(video_path)
        except Exception as error:  # noqa: BLE001
            # One bad video must not abandon the rest of the batch.
            print(f"  failed: {error}", file=sys.stderr)
            failures += 1

    if args.dry_run:
        print("\ndry run: nothing was uploaded.")
    return 1 if failures else 0


def cmd_frames(args: argparse.Namespace) -> int:
    """Extract stills so the hero, matchup and result can be read off the video.

    Deliberately a separate command: it needs no credentials and no quota, so it can
    be run freely before deciding what the video even is.
    """
    video_path = Path(args.video)
    if not video_path.is_file():
        raise SystemExit(f"error: not a file: {video_path}")

    output_dir = Path(args.out or Path(".frames") / video_path.stem)
    duration = probe_duration(video_path)
    print(f"duration: {format_duration(duration)}")

    try:
        if args.at is not None:
            frames = [extract_frame(video_path, args.at, output_dir / "frame.jpg")]
        else:
            frames = extract_review_frames(video_path, output_dir)
    except VideoError as error:
        raise SystemExit(f"error: {error}")

    if not frames:
        raise SystemExit("error: no frames could be extracted")

    print(f"\n{len(frames)} frame(s):")
    for frame in frames:
        print(f"  {frame}")
    return 0


def cmd_thumbnail(args: argparse.Namespace) -> int:
    """Build a thumbnail, either from hero art or from a frame of the video.

    Hero art is the default for Dota because it cannot possibly spoil the result.
    Frame mode is available when a specific moment is wanted.
    """
    if not args.hero and not args.hero_image and not args.video:
        raise SystemExit(
            "error: give --hero (recommended), --hero-image, or a video file"
        )

    headline = args.headline or args.hero or ""
    needs_text = args.style == "portrait" or args.video or args.frame
    if needs_text and not headline.strip():
        raise SystemExit("error: --headline is required for this thumbnail style")

    if args.hero or args.hero_image:
        return _hero_thumbnail(args, headline)
    return _frame_thumbnail(args, headline)


def _hero_thumbnail(args: argparse.Namespace, headline: str) -> int:
    """Compose from official hero art. Needs no video and reveals no outcome."""
    if args.hero_image:
        art = Path(args.hero_image)
        if not art.is_file():
            raise SystemExit(f"error: hero image not found: {art}")
    else:
        try:
            art = fetch_hero_art(args.hero)
        except HeroArtError as error:
            raise SystemExit(f"error: {error}")

    default_name = (args.hero or art.stem).lower().replace(" ", "-")
    output_path = Path(args.out or f"{default_name}-thumb.jpg")

    badges = []
    for badge_name in _split_tags(args.badges):
        try:
            badges.append(fetch_badge_icon(badge_name))
        except HeroArtError as error:
            print(f"warning: {error}", file=sys.stderr)

    try:
        if args.style == "splash":
            # Full-bleed art with circular badges, and no text: YouTube already
            # prints the title under the thumbnail.
            result = make_splash_thumbnail(
                art,
                output_path,
                badge_paths=badges,
                accent=dominant_color(art),
                headline=args.headline if args.with_text else None,
                subtitle=args.subtitle if args.with_text else None,
                brand_path=Path(args.brand_image) if args.brand_image else None,
            )
        else:
            result = make_hero_thumbnail(
                art,
                output_path,
                headline=headline,
                subtitle=args.subtitle,
                accent=dominant_color(art),
            )
    except ThumbnailError as error:
        raise SystemExit(f"error: {error}")

    _report_thumbnail(result)
    return 0


def _frame_thumbnail(args: argparse.Namespace, headline: str) -> int:
    """Compose from a still of the match. The caller must avoid spoiler moments."""
    video_path = Path(args.video)
    if not video_path.is_file():
        raise SystemExit(f"error: not a file: {video_path}")

    output_path = Path(args.out or f"{video_path.stem}-thumb.jpg")
    workdir = Path(".frames") / video_path.stem

    if args.frame:
        frame = Path(args.frame)
        if not frame.is_file():
            raise SystemExit(f"error: frame not found: {frame}")
    else:
        duration = probe_duration(video_path)
        at = args.at
        if at is None:
            # Past laning, well before anything that reveals the outcome.
            at = duration * 0.55 if duration else 300
        elif duration and at > duration * SPOILER_FRACTION and not args.allow_late_frame:
            late_percent = int(round((1 - SPOILER_FRACTION) * 100))
            raise SystemExit(
                "error: "
                + format_duration(at)
                + " is in the last "
                + str(late_percent)
                + "% of a "
                + format_duration(duration)
                + " match, which usually shows the result. "
                "A thumbnail must not spoil the outcome. Pick an earlier moment, "
                "use --hero instead, or pass --allow-late-frame if you are sure "
                "this frame gives nothing away."
            )
        try:
            frame = extract_frame(video_path, at, workdir / "thumb-source.jpg")
        except VideoError as error:
            raise SystemExit(f"error: {error}")

    try:
        result = make_thumbnail(
            frame,
            output_path,
            headline=headline,
            subtitle=args.subtitle,
            trim_top=0.0 if args.keep_hud else DOTA_HUD_TRIM_TOP,
            trim_bottom=0.0 if args.keep_hud else DOTA_HUD_TRIM_BOTTOM,
        )
    except ThumbnailError as error:
        raise SystemExit(f"error: {error}")

    _report_thumbnail(result)
    return 0


def _report_thumbnail(result: Path) -> None:
    print(f"thumbnail: {result}  ({result.stat().st_size / 1024:,.0f} KB)")
    print("review it before uploading; pass it with --thumbnail")


def cmd_cut(args: argparse.Namespace) -> int:
    """Cut a full match down to a highlight edit of a target length."""
    video_path = Path(args.video)
    if not video_path.is_file():
        raise SystemExit(f"error: not a file: {video_path}")

    # Unique per run: a workdir keyed only on the video name means two
    # concurrent runs delete each other's frames mid-analysis, which silently
    # produces a short, wrong edit instead of an error.
    workdir = Path(".editcache") / f"{video_path.stem}-{os.getpid()}"
    print(f"analysing {video_path.name} ...")
    try:
        analysis = analyse(video_path, workdir / "strip")
    except EditError as error:
        raise SystemExit(f"error: {error}")

    print(
        f"  duration {format_duration(analysis.duration)}"
        f"   game starts at {format_duration(analysis.game_start)}"
    )

    segments = plan(
        analysis,
        target_minutes=args.target_minutes,
        lane_minutes=args.lane_minutes,
    )
    print(f"\ncut plan (laning kept whole, then highlights):")
    print(describe(segments))

    output_path = Path(args.out or f"{video_path.stem} - cut.mp4")

    if args.dry_run:
        plan_path = save_plan(segments, workdir / "plan.json")
        print(f"\ndry run: nothing rendered. Plan saved to {plan_path}")
        return 0

    encoder = "NVENC (GPU)" if has_nvenc() else "libx264 (CPU, slower)"
    print(f"\nrendering {len(segments)} segments with {encoder} ...")

    def progress(done: int, total: int) -> None:
        print(f"  segment {done}/{total}", flush=True)

    try:
        result = render(
            video_path, segments, output_path, workdir / "parts", on_progress=progress
        )
    except EditError as error:
        raise SystemExit(f"error: {error}")

    size_gb = result.stat().st_size / (1024 ** 3)
    print(f"\ndone: {result}  ({size_gb:.2f} GB)")
    shutil.rmtree(workdir, ignore_errors=True)
    print("watch it before uploading")
    return 0


def cmd_auth(args: argparse.Namespace) -> int:
    """Run the OAuth consent flow and confirm the channel it authorized."""
    service = build_youtube_service(
        client_secret_file=Path(args.client_secret),
        token_file=Path(args.token_file),
    )
    response = service.channels().list(part="snippet", mine=True).execute()
    items = response.get("items", [])
    if not items:
        print("authorized, but this account has no YouTube channel.", file=sys.stderr)
        return 1
    print(f"authorized as: {items[0]['snippet']['title']}")
    print(f"token stored at: {args.token_file}")
    return 0


# ---------------------------------------------------------------------- parser


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--client-secret",
        default=str(DEFAULT_CLIENT_SECRET_FILE),
        help=f"OAuth client secret JSON (default: {DEFAULT_CLIENT_SECRET_FILE})",
    )
    parser.add_argument(
        "--token-file",
        default=str(DEFAULT_TOKEN_FILE),
        help=f"stored credentials (default: {DEFAULT_TOKEN_FILE})",
    )


def _add_metadata_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", help="video title (max 100 characters)")
    parser.add_argument("--description", help="description text")
    parser.add_argument(
        "--description-file",
        help="read the description from a file; preferred for long, multi-line text",
    )
    parser.add_argument("--tags", help="comma-separated tags")
    parser.add_argument(
        "--preset",
        choices=sorted(PRESETS),
        help="apply a named set of defaults (tags, playlist, description footer)",
    )
    parser.add_argument("--playlist", help="playlist title; created if it does not exist")
    parser.add_argument(
        "--privacy", choices=PRIVACY_CHOICES, default="public",
        help="default: public",
    )
    parser.add_argument(
        "--made-for-kids", action="store_true", help="declare the video made for kids"
    )
    parser.add_argument(
        "--thumbnail", help="custom thumbnail image (requires a verified account)"
    )
    parser.add_argument(
        "--notify", action="store_true", help="notify subscribers (default: off)"
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="after a successful upload, move the file into an 'uploaded' subfolder",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and print the request without uploading; needs no credentials",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ytupload", description="Upload videos to YouTube."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    upload = subparsers.add_parser("upload", help="upload a single video")
    upload.add_argument("video", help="path to the video file")
    _add_metadata_args(upload)
    _add_common(upload)
    upload.set_defaults(func=cmd_upload)

    batch = subparsers.add_parser("batch", help="upload new videos from a folder")
    batch.add_argument("folder", help="folder to scan recursively")
    batch.add_argument("--ext", default=".mp4", help="comma-separated extensions")
    batch.add_argument(
        "--min-duration",
        type=float,
        default=DEFAULT_MIN_DURATION_SECONDS,
        metavar="SECONDS",
        help=(
            "skip captures shorter than this "
            f"(default: {DEFAULT_MIN_DURATION_SECONDS:.0f}s; use 0 to keep everything)"
        ),
    )
    batch.add_argument(
        "--limit",
        type=int,
        default=MAX_UPLOADS_PER_RUN,
        help=f"max uploads this run (capped at {MAX_UPLOADS_PER_RUN} by daily quota)",
    )
    _add_metadata_args(batch)
    _add_common(batch)
    batch.set_defaults(func=cmd_batch)

    frames = subparsers.add_parser(
        "frames", help="extract stills to identify the hero, matchup and result"
    )
    frames.add_argument("video", help="path to the video file")
    frames.add_argument(
        "--at", type=float, metavar="SECONDS", help="one frame at this offset"
    )
    frames.add_argument("--out", help="output directory (default: .frames/<name>/)")
    frames.set_defaults(func=cmd_frames)

    thumbnail = subparsers.add_parser(
        "thumbnail",
        help="build a thumbnail from official hero art, or from a video frame",
    )
    thumbnail.add_argument(
        "video", nargs="?", help="video file (only needed for frame mode)"
    )
    thumbnail.add_argument(
        "--hero",
        help="hero name, e.g. \"Mars\". Uses official hero art: cannot spoil the "
        "result, and needs no video. This is the recommended mode.",
    )
    thumbnail.add_argument(
        "--hero-image", help="use this image as the hero art instead of downloading"
    )
    thumbnail.add_argument(
        "--headline", help="large text (default: the hero name)"
    )
    thumbnail.add_argument(
        "--style",
        choices=("splash", "portrait"),
        default="splash",
        help="splash: full-bleed art with circular badges and no text (default). "
        "portrait: hero beside large text.",
    )
    thumbnail.add_argument(
        "--badges",
        help="comma-separated items or abilities to show as circular badges, "
        "e.g. \"blink,mars_arena_of_blood\". Up to three.",
    )
    thumbnail.add_argument(
        "--brand-image",
        help="small circular mark in the bottom-right corner, e.g. the channel "
        "mascot. Appears on every thumbnail, so viewers recognise the channel.",
    )
    thumbnail.add_argument(
        "--with-text",
        action="store_true",
        help="draw the headline on a splash thumbnail (off by default)",
    )
    thumbnail.add_argument("--subtitle", help="smaller supporting line, e.g. the matchup")
    thumbnail.add_argument(
        "--at", type=float, metavar="SECONDS", help="take the frame at this offset"
    )
    thumbnail.add_argument("--frame", help="use this existing image instead of the video")
    thumbnail.add_argument("--out", help="output path (default: <name>-thumb.jpg)")
    thumbnail.add_argument(
        "--allow-late-frame",
        action="store_true",
        help="permit a frame from the end of the match (normally refused as a spoiler)",
    )
    thumbnail.add_argument(
        "--keep-hud",
        action="store_true",
        help="do not crop the game HUD away before framing (default: crop it)",
    )
    thumbnail.set_defaults(func=cmd_thumbnail)

    cut = subparsers.add_parser(
        "cut", help="cut a full match into a highlight edit of a target length"
    )
    cut.add_argument("video", help="path to the video file")
    cut.add_argument(
        "--target-minutes",
        type=float,
        default=DEFAULT_TARGET_MINUTES,
        help=f"target runtime (default: {DEFAULT_TARGET_MINUTES:.0f})",
    )
    cut.add_argument(
        "--lane-minutes",
        type=float,
        default=DEFAULT_LANE_MINUTES,
        help=f"minutes of laning kept whole (default: {DEFAULT_LANE_MINUTES:.0f})",
    )
    cut.add_argument("--out", help="output path (default: '<name> - cut.mp4')")
    cut.add_argument(
        "--dry-run", action="store_true", help="print the cut plan without rendering"
    )
    cut.set_defaults(func=cmd_cut)

    auth = subparsers.add_parser("auth", help="run OAuth consent and verify access")
    _add_common(auth)
    auth.set_defaults(func=cmd_auth)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "upload" and not args.title:
        parser.error("upload requires --title")

    try:
        return args.func(args)
    except AuthError as error:
        # Setup problem, not a crash: show the instructions, not a traceback.
        print(f"error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        # A resumable upload keeps its session, so a later run continues it.
        print("\ninterrupted; re-run to resume this upload.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
