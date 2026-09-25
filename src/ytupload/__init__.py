"""Upload videos to YouTube, with metadata worth reading.

Only dependency-free modules are re-exported here. ``uploader`` and ``auth`` import
the Google client libraries, so importing them eagerly would make the whole package
unimportable — and its tests unrunnable — without credentials installed.
"""

from .metadata import MetadataError, VideoMetadata
from .presets import PRESETS
from .shadowplay import format_capture_date, parse_capture_time
from .tracker import ResumableSessionStore, UploadTracker

__all__ = [
    "MetadataError",
    "PRESETS",
    "ResumableSessionStore",
    "UploadTracker",
    "VideoMetadata",
    "format_capture_date",
    "parse_capture_time",
]

__version__ = "2.0.0"
