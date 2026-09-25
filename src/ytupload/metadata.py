"""Video metadata: the thing we are uploading, independent of how we upload it.

Every limit here is enforced server-side by the YouTube Data API. Checking locally
turns an opaque ``HttpError 400`` into a message that names the offending field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

TITLE_MAX_CHARS = 100
DESCRIPTION_MAX_CHARS = 5000
TAGS_MAX_TOTAL_CHARS = 500

#: ``20`` is YouTube's "Gaming" category.
GAMING_CATEGORY_ID = "20"

PRIVACY_CHOICES = ("public", "unlisted", "private")

#: YouTube rejects angle brackets in titles and descriptions outright.
FORBIDDEN_CHARS = ("<", ">")


class MetadataError(ValueError):
    """Metadata that the YouTube API would reject."""


@dataclass
class VideoMetadata:
    """Everything YouTube needs to know about a video, minus the bytes."""

    title: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    privacy: str = "public"
    category_id: str = GAMING_CATEGORY_ID
    made_for_kids: bool = False

    def validate(self) -> None:
        """Raise :class:`MetadataError` listing every problem found, not just the first."""
        problems: List[str] = []

        if not self.title.strip():
            problems.append("title is empty")
        elif len(self.title) > TITLE_MAX_CHARS:
            problems.append(
                f"title is {len(self.title)} chars, limit is {TITLE_MAX_CHARS}"
            )

        if len(self.description) > DESCRIPTION_MAX_CHARS:
            problems.append(
                f"description is {len(self.description)} chars, "
                f"limit is {DESCRIPTION_MAX_CHARS}"
            )

        for char in FORBIDDEN_CHARS:
            if char in self.title:
                problems.append(f"title contains {char!r}, which YouTube rejects")
            if char in self.description:
                problems.append(f"description contains {char!r}, which YouTube rejects")

        tag_chars = sum(len(tag) for tag in self.tags)
        if tag_chars > TAGS_MAX_TOTAL_CHARS:
            problems.append(
                f"tags total {tag_chars} chars, limit is {TAGS_MAX_TOTAL_CHARS}"
            )

        if self.privacy not in PRIVACY_CHOICES:
            problems.append(
                f"privacy {self.privacy!r} is not one of {', '.join(PRIVACY_CHOICES)}"
            )

        if problems:
            raise MetadataError("; ".join(problems))

    def to_request_body(self) -> Dict[str, Any]:
        """Build the ``videos.insert`` request body, validating first.

        ``notifySubscribers`` is deliberately absent: the API defines it as a query
        parameter, so placing it here would be silently ignored.
        """
        self.validate()
        return {
            "snippet": {
                "title": self.title,
                "description": self.description,
                "tags": self.tags,
                "categoryId": self.category_id,
            },
            "status": {
                "privacyStatus": self.privacy,
                "selfDeclaredMadeForKids": self.made_for_kids,
            },
        }
