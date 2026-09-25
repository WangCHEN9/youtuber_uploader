"""Persistent state: what we already uploaded, and what is half-uploaded.

Two separate concerns, two separate files:

``uploaded_files.txt``
    Append-only record of completed uploads, so a re-run skips them.

``.upload_sessions.json``
    Resumable session URIs for uploads still in flight. YouTube keeps a resumable
    session alive for roughly a week, so an interrupted multi-gigabyte upload can
    continue instead of restarting from byte zero.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Set

DEFAULT_TRACKING_FILE = Path("uploaded_files.txt")
DEFAULT_SESSION_FILE = Path(".upload_sessions.json")


class UploadTracker:
    """Remembers which files have been uploaded.

    The on-disk format is tab separated: ``path<TAB>video_id<TAB>iso8601``. Older
    versions of this tool wrote a bare path per line, so only the first field is
    read back -- legacy files keep working unchanged.
    """

    def __init__(self, path: Path = DEFAULT_TRACKING_FILE) -> None:
        self.path = Path(path)
        self._uploaded: Optional[Set[str]] = None

    @property
    def uploaded(self) -> Set[str]:
        """The set of already-uploaded paths, read from disk once and cached."""
        if self._uploaded is None:
            self._uploaded = self._read()
        return self._uploaded

    def _read(self) -> Set[str]:
        if not self.path.exists():
            return set()
        entries: Set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            first_field = line.split("\t")[0].strip()
            if first_field:
                entries.add(first_field)
        return entries

    def already_uploaded(self, video_path: Path) -> bool:
        return str(video_path) in self.uploaded

    def record(self, video_path: Path, video_id: str = "") -> None:
        """Append a completed upload and update the in-memory cache."""
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        line = f"{video_path}\t{video_id}\t{timestamp}\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        self.uploaded.add(str(video_path))


class ResumableSessionStore:
    """Maps a video file to the resumable upload session URI that is in progress.

    Keyed by path *and* size: if the file is re-encoded or replaced, the old session
    no longer describes those bytes and must not be resumed into.
    """

    def __init__(self, path: Path = DEFAULT_SESSION_FILE) -> None:
        self.path = Path(path)

    @staticmethod
    def key_for(video_path: Path) -> str:
        video_path = Path(video_path)
        try:
            size = video_path.stat().st_size
        except OSError:
            size = 0
        return f"{video_path}|{size}"

    def _read_all(self) -> Dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt session file must never block an upload; start over.
            return {}
        return data if isinstance(data, dict) else {}

    def _write_all(self, data: Dict[str, str]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get(self, video_path: Path) -> Optional[str]:
        return self._read_all().get(self.key_for(video_path))

    def save(self, video_path: Path, session_uri: str) -> None:
        data = self._read_all()
        key = self.key_for(video_path)
        if data.get(key) == session_uri:
            return  # Unchanged; avoid rewriting the file on every chunk.
        data[key] = session_uri
        self._write_all(data)

    def clear(self, video_path: Path) -> None:
        data = self._read_all()
        if data.pop(self.key_for(video_path), None) is not None:
            self._write_all(data)
