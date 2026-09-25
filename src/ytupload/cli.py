"""Command-line interface.

Run ``python -m ytupload --help`` for usage.

``--dry-run`` deliberately needs no credentials: it assembles and validates the
request exactly as a real run would, then prints it instead of sending it. That makes
it a genuine rehearsal, and it costs no API quota.
"""

from __future__ import annotations

import argparse
import json
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
from .presets import PRESETS
from .shadowplay import format_capture_date
from .uploader import MAX_UPLOADS_PER_RUN, QUOTA_PER_UPLOAD, YoutubeUploader

_MIB = 1024 * 1024


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

    pending = uploader.find_new_videos(folder, extensions=_split_tags(args.ext) or [".mp4"])
    if not pending:
        print("nothing new to upload.")
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
        except Exception as error:  # noqa: BLE001
            # One bad video must not abandon the rest of the batch.
            print(f"  failed: {error}", file=sys.stderr)
            failures += 1

    if args.dry_run:
        print("\ndry run: nothing was uploaded.")
    return 1 if failures else 0


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
        "--notify", action="store_true", help="notify subscribers (default: off)"
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
        "--limit",
        type=int,
        default=MAX_UPLOADS_PER_RUN,
        help=f"max uploads this run (capped at {MAX_UPLOADS_PER_RUN} by daily quota)",
    )
    _add_metadata_args(batch)
    _add_common(batch)
    batch.set_defaults(func=cmd_batch)

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
