"""Uploading videos to YouTube, resumably.

The central design point: uploads use ``resumable=True`` and are driven chunk by
chunk. A non-resumable upload must complete in a single unbroken HTTP request, which
is not a realistic proposition for multi-gigabyte gameplay captures.
"""

from __future__ import annotations

import http.client
import random
import socket
import sys
import time
from pathlib import Path
from typing import Callable, Iterable, List, Optional

import httplib2
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .archive import ArchiveError, archive_video, is_archived
from .auth import DEFAULT_CLIENT_SECRET_FILE, DEFAULT_TOKEN_FILE, build_youtube_service
from .metadata import VideoMetadata
from .tracker import ResumableSessionStore, UploadTracker
from .video import is_long_enough

#: Transient server-side failures worth retrying, per YouTube's own guidance.
RETRIABLE_STATUS_CODES = (500, 502, 503, 504)

RETRIABLE_EXCEPTIONS = (
    httplib2.HttpLib2Error,
    IOError,
    http.client.NotConnected,
    http.client.IncompleteRead,
    http.client.ImproperConnectionState,
    http.client.CannotSendRequest,
    http.client.CannotSendHeader,
    http.client.ResponseNotReady,
    http.client.BadStatusLine,
    socket.error,
    socket.timeout,
)

#: Quota costs in units.
#: See https://developers.google.com/youtube/v3/determine_quota_cost
QUOTA_PER_UPLOAD = 1600
QUOTA_PER_PLAYLIST_INSERT = 50
QUOTA_PER_THUMBNAIL_SET = 50
DAILY_QUOTA = 10_000

#: How many uploads a default project daily quota allows.
MAX_UPLOADS_PER_RUN = DAILY_QUOTA // QUOTA_PER_UPLOAD

#: YouTube caps uploads at 15 minutes until the account is phone-verified.
UNVERIFIED_LIMIT_SECONDS = 15 * 60

#: 8 MiB balances request overhead against how much is re-sent after a failed chunk.
CHUNK_SIZE = 8 * 1024 * 1024

MAX_RETRIES = 10

ProgressCallback = Callable[[int, int], None]

_MIB = 1024 * 1024


def _default_progress(uploaded_bytes: int, total_bytes: int) -> None:
    percent = (uploaded_bytes / total_bytes * 100) if total_bytes else 0.0
    print(
        f"  {percent:5.1f}%  "
        f"{uploaded_bytes / _MIB:,.0f} / {total_bytes / _MIB:,.0f} MiB",
        flush=True,
    )


class UploadError(RuntimeError):
    """An upload failed and is not worth retrying."""


class YoutubeUploader:
    """Uploads videos to the authenticated user YouTube channel."""

    def __init__(
        self,
        client_secret_file: Path = DEFAULT_CLIENT_SECRET_FILE,
        token_file: Path = DEFAULT_TOKEN_FILE,
        tracker: Optional[UploadTracker] = None,
        sessions: Optional[ResumableSessionStore] = None,
        service=None,
    ) -> None:
        # ``service`` is injectable so tests never need real credentials.
        self.service = service or build_youtube_service(client_secret_file, token_file)
        self.tracker = tracker or UploadTracker()
        self.sessions = sessions or ResumableSessionStore()

    # ------------------------------------------------------------------ upload

    def upload_video(
        self,
        video_path: Path,
        metadata: VideoMetadata,
        notify_subscribers: bool = False,
        on_progress: Optional[ProgressCallback] = None,
    ) -> str:
        """Upload one video and return its YouTube video ID.

        Metadata is validated before any network call, so a bad title costs nothing.
        """
        video_path = Path(video_path)
        if not video_path.is_file():
            raise UploadError(f"not a file: {video_path}")

        body = metadata.to_request_body()  # validates; raises MetadataError

        media = MediaFileUpload(str(video_path), chunksize=CHUNK_SIZE, resumable=True)
        request = self.service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
            # A query parameter, not a body field. Placed in the body it is ignored.
            notifySubscribers=notify_subscribers,
        )

        # Resume a previous attempt at these exact bytes, if one is still open.
        previous_uri = self.sessions.get(video_path)
        if previous_uri:
            request.resumable_uri = previous_uri
            print(f"  resuming previous upload session for {video_path.name}")

        response = self._run_resumable(request, video_path, on_progress)
        video_id = response.get("id", "")
        self.sessions.clear(video_path)
        self.tracker.record(video_path, video_id)
        return video_id

    def _run_resumable(
        self,
        request,
        video_path: Path,
        on_progress: Optional[ProgressCallback],
    ) -> dict:
        """Drive a resumable request to completion, retrying transient failures."""
        progress = on_progress or _default_progress
        total_bytes = video_path.stat().st_size
        response = None
        attempt = 0

        while response is None:
            try:
                status, response = request.next_chunk()
            except HttpError as error:
                if error.resp.status not in RETRIABLE_STATUS_CODES:
                    raise
                attempt = self._back_off(attempt, f"HTTP {error.resp.status}")
                continue
            except RETRIABLE_EXCEPTIONS as error:
                attempt = self._back_off(attempt, type(error).__name__)
                continue

            # A chunk landed: reset the retry budget and persist the session URI so
            # a later run can resume rather than restart.
            attempt = 0
            if request.resumable_uri:
                self.sessions.save(video_path, request.resumable_uri)
            if status:
                progress(status.resumable_progress, total_bytes)

        progress(total_bytes, total_bytes)
        return response

    @staticmethod
    def _back_off(attempt: int, reason: str) -> int:
        """Sleep with exponential backoff and jitter; raise once retries run out."""
        attempt += 1
        if attempt > MAX_RETRIES:
            raise UploadError(f"giving up after {MAX_RETRIES} retries ({reason})")
        # Jitter prevents synchronised retries from re-colliding.
        delay = random.uniform(0, 2**attempt)
        print(f"  {reason}; retry {attempt}/{MAX_RETRIES} in {delay:.1f}s", flush=True)
        time.sleep(delay)
        return attempt

    def channel(self) -> dict:
        """Return the authorised channel's id, title, handle and upload limit.

        Costs one quota unit. Worth it before any upload: a Google account with
        a Brand Account channel can silently authorise the *personal* channel,
        and a large upload landing there is tedious to undo.
        """
        response = (
            self.service.channels().list(part="snippet,status", mine=True).execute()
        )
        items = response.get("items", [])
        if not items:
            raise UploadError("this account has no YouTube channel")
        snippet = items[0]["snippet"]
        return {
            "id": items[0]["id"],
            "title": snippet.get("title", ""),
            "handle": snippet.get("customUrl", ""),
            # "allowed" means videos over 15 minutes are accepted. "eligible"
            # does NOT: it means the channel could enable them but has not, and
            # an over-length upload is accepted and then deleted by YouTube.
            "long_uploads": items[0].get("status", {}).get("longUploadsStatus", ""),
        }

    def require_upload_length(self, duration_seconds: Optional[float]) -> None:
        """Refuse an over-length upload the channel cannot actually keep.

        An unverified channel accepts a long upload and YouTube deletes it
        afterwards, so the whole transfer is wasted with no error at upload
        time. Checking first costs nothing.
        """
        if duration_seconds is None or duration_seconds <= UNVERIFIED_LIMIT_SECONDS:
            return
        status = self.channel()["long_uploads"]
        if status == "allowed":
            return
        raise UploadError(
            f"this video is {duration_seconds / 60:.0f} minutes, but the channel "
            f"cannot accept uploads over {UNVERIFIED_LIMIT_SECONDS / 60:.0f} minutes "
            f"(longUploadsStatus is {status!r}, not 'allowed').\n"
            "YouTube would accept the upload and then delete the video. Verify the "
            "account at https://www.youtube.com/verify first -- note that "
            "'eligible' means able to enable this, not enabled."
        )

    def require_channel(self, expected: str) -> dict:
        """Abort unless the authorised channel matches *expected*.

        Accepts either the channel title or its handle, with or without a
        leading ``@``, compared case-insensitively.
        """
        channel = self.channel()
        wanted = expected.strip().lstrip("@").lower()
        actual = {
            channel["title"].strip().lower(),
            channel["handle"].strip().lstrip("@").lower(),
        }
        if wanted not in actual:
            raise UploadError(
                f"authorised as {channel['title']!r} (@{channel['handle'].lstrip('@')}), "
                f"but {expected!r} was expected.\n"
                "Re-run 'ytupload auth' and pick the right channel at the account "
                "chooser, or revoke access at "
                "https://myaccount.google.com/permissions first."
            )
        return channel

    def archive_uploaded(self, video_path: Path) -> Optional[Path]:
        """Move an uploaded video into its ``uploaded`` folder; return the new path.

        The destination is recorded in the tracker as well as the source. A later
        scan that encounters the moved file must recognise it as already uploaded
        rather than treating the new path as a new video.

        Failure here is reported but never raised: the upload already succeeded, and
        a file that did not move is a tidiness problem, not a lost video.
        """
        try:
            new_path = archive_video(video_path)
        except ArchiveError as error:
            print(f"  warning: {error}", file=sys.stderr)
            return None

        if new_path != Path(video_path):
            self.tracker.record(new_path)
            print(f"  moved to {new_path.parent.name}/")
        return new_path

    # --------------------------------------------------------------- playlists

    def find_playlist(self, title: str) -> Optional[str]:
        """Return the ID of the caller playlist named *title*, case-insensitively."""
        wanted = title.strip().lower()
        request = self.service.playlists().list(part="snippet", mine=True, maxResults=50)
        while request is not None:
            response = request.execute()
            for item in response.get("items", []):
                if item["snippet"]["title"].strip().lower() == wanted:
                    return item["id"]
            request = self.service.playlists().list_next(request, response)
        return None

    def create_playlist(
        self, title: str, description: str = "", privacy: str = "public"
    ) -> str:
        response = (
            self.service.playlists()
            .insert(
                part="snippet,status",
                body={
                    "snippet": {"title": title, "description": description},
                    "status": {"privacyStatus": privacy},
                },
            )
            .execute()
        )
        return response["id"]

    def find_or_create_playlist(self, title: str, privacy: str = "public") -> str:
        existing = self.find_playlist(title)
        if existing:
            return existing
        print(f"  creating playlist {title!r}")
        return self.create_playlist(title, privacy=privacy)

    def add_to_playlist(self, video_id: str, playlist_id: str) -> None:
        self.service.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()

    # -------------------------------------------------------------- thumbnails

    def set_thumbnail(self, video_id: str, thumbnail_path: Path) -> None:
        """Attach a custom thumbnail. Requires a verified YouTube account."""
        thumbnail_path = Path(thumbnail_path)
        if not thumbnail_path.is_file():
            raise UploadError(f"thumbnail not found: {thumbnail_path}")
        self.service.thumbnails().set(
            videoId=video_id, media_body=MediaFileUpload(str(thumbnail_path))
        ).execute()

    # ------------------------------------------------------------------- batch

    def find_new_videos(
        self,
        folder: Path,
        extensions: Iterable[str] = (".mp4",),
        min_duration_seconds: Optional[float] = None,
        skip_archived: bool = True,
    ) -> List[Path]:
        """Return not-yet-uploaded videos under *folder*, oldest first.

        Sorting by name puts ShadowPlay captures in chronological order, because
        their timestamp format sorts lexicographically.

        When *min_duration_seconds* is given, clips shorter than that are excluded:
        captures below roughly ten minutes are misfires rather than matches.
        """
        folder = Path(folder)
        found: List[Path] = []
        for extension in extensions:
            found.extend(folder.glob(f"**/*{extension}"))

        candidates = [
            path
            for path in found
            if not self.tracker.already_uploaded(path)
            and not (skip_archived and is_archived(path))
        ]

        if min_duration_seconds:
            candidates = [
                path
                for path in candidates
                if is_long_enough(path, min_duration_seconds)
            ]

        return sorted(candidates, key=lambda path: path.name)
