"""Moving captures aside once they are safely on YouTube.

Files move to an ``uploaded`` subfolder of wherever they already live. Staying on the
same volume matters: a same-volume move is a rename and completes instantly even for
an 8 GB capture, whereas moving across drives copies every byte.
"""

from __future__ import annotations

import shutil
from pathlib import Path

DEFAULT_ARCHIVE_DIR_NAME = "uploaded"


class ArchiveError(RuntimeError):
    """The file could not be moved."""


def archive_dir_for(video_path: Path, dir_name: str = DEFAULT_ARCHIVE_DIR_NAME) -> Path:
    return Path(video_path).parent / dir_name


def is_archived(video_path: Path, dir_name: str = DEFAULT_ARCHIVE_DIR_NAME) -> bool:
    """Whether the file already sits inside an archive folder."""
    return dir_name in Path(video_path).parts


def _unique_destination(destination: Path) -> Path:
    """Return a free path, suffixing ``-2``, ``-3`` ... if needed.

    Never overwrite: the existing file is an earlier capture that was also uploaded,
    and silently destroying it would be unrecoverable.
    """
    if not destination.exists():
        return destination
    stem, suffix, parent = destination.stem, destination.suffix, destination.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def archive_video(
    video_path: Path, dir_name: str = DEFAULT_ARCHIVE_DIR_NAME
) -> Path:
    """Move *video_path* into its ``uploaded`` folder and return the new path.

    If the file is already archived it is left alone and its path returned unchanged.
    """
    video_path = Path(video_path)
    if not video_path.is_file():
        raise ArchiveError(f"not a file: {video_path}")
    if is_archived(video_path, dir_name):
        return video_path

    target_dir = archive_dir_for(video_path, dir_name)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = _unique_destination(target_dir / video_path.name)
        shutil.move(str(video_path), str(destination))
    except OSError as error:
        raise ArchiveError(f"could not move {video_path.name}: {error}") from error
    return destination
