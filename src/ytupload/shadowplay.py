"""Parse NVIDIA ShadowPlay capture filenames.

ShadowPlay names recordings after the game and the moment capture stopped::

    Dota 2 2026.09.25 - 21.59.04.14.mp4
             ^date^     ^ time ^ ^^ counter

The filename says nothing about hero, role, or outcome, so it can supply the match
date for a description but never a usable title.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

_CAPTURE_PATTERN = re.compile(
    r"(?P<year>\d{4})\.(?P<month>\d{2})\.(?P<day>\d{2})"
    r"\s*-\s*"
    r"(?P<hour>\d{2})\.(?P<minute>\d{2})\.(?P<second>\d{2})"
)


def parse_capture_time(name: str) -> Optional[datetime]:
    """Return the capture timestamp encoded in *name*, or ``None`` if absent.

    Accepts a bare filename or a full path. Returns ``None`` rather than raising,
    because a non-ShadowPlay filename is a normal case, not an error.
    """
    match = _CAPTURE_PATTERN.search(Path(name).name)
    if match is None:
        return None
    parts = {key: int(value) for key, value in match.groupdict().items()}
    try:
        return datetime(**parts)
    except ValueError:
        # Matched the shape but not a real date, e.g. "2026.13.45 - 99.99.99".
        return None


def format_capture_date(name: str) -> Optional[str]:
    """Return the capture date as ``25 September 2026``, or ``None``."""
    captured = parse_capture_time(name)
    if captured is None:
        return None
    return captured.strftime("%d %B %Y").lstrip("0")
