"""Metadata validation: catching locally what YouTube would reject remotely."""

import pytest

from ytupload.metadata import (
    DESCRIPTION_MAX_CHARS,
    GAMING_CATEGORY_ID,
    TAGS_MAX_TOTAL_CHARS,
    TITLE_MAX_CHARS,
    MetadataError,
    VideoMetadata,
)


def test_minimal_metadata_is_valid():
    VideoMetadata(title="Centaur offlane vs Timbersaw").validate()


def test_empty_title_is_rejected():
    with pytest.raises(MetadataError, match="title is empty"):
        VideoMetadata(title="   ").validate()


def test_title_at_the_limit_is_accepted():
    VideoMetadata(title="x" * TITLE_MAX_CHARS).validate()


def test_title_one_over_the_limit_is_rejected():
    with pytest.raises(MetadataError, match="limit is 100"):
        VideoMetadata(title="x" * (TITLE_MAX_CHARS + 1)).validate()


def test_description_over_the_limit_is_rejected():
    with pytest.raises(MetadataError, match="description is"):
        VideoMetadata(
            title="ok", description="x" * (DESCRIPTION_MAX_CHARS + 1)
        ).validate()


def test_angle_brackets_are_rejected():
    with pytest.raises(MetadataError, match="YouTube rejects"):
        VideoMetadata(title="Dota 2 <best> game").validate()


def test_tags_are_limited_by_total_characters_not_count():
    # Many short tags are fine...
    VideoMetadata(title="ok", tags=["ab"] * 50).validate()
    # ...but the total character budget still applies.
    with pytest.raises(MetadataError, match="tags total"):
        VideoMetadata(title="ok", tags=["x" * 100] * 6).validate()


def test_tags_exactly_at_the_limit_are_accepted():
    VideoMetadata(title="ok", tags=["x" * TAGS_MAX_TOTAL_CHARS]).validate()


def test_unknown_privacy_is_rejected():
    with pytest.raises(MetadataError, match="privacy"):
        VideoMetadata(title="ok", privacy="secret").validate()


def test_all_problems_are_reported_together():
    """One run should surface every issue, not just the first."""
    with pytest.raises(MetadataError) as caught:
        VideoMetadata(title="", privacy="nope").validate()
    message = str(caught.value)
    assert "title is empty" in message
    assert "privacy" in message


def test_request_body_shape():
    body = VideoMetadata(
        title="Centaur offlane",
        description="A comeback.",
        tags=["Dota 2", "offlane"],
        privacy="public",
    ).to_request_body()

    assert body["snippet"]["title"] == "Centaur offlane"
    assert body["snippet"]["categoryId"] == GAMING_CATEGORY_ID
    assert body["status"]["privacyStatus"] == "public"
    assert body["status"]["selfDeclaredMadeForKids"] is False


def test_request_body_omits_notify_subscribers():
    """It is a query parameter; in the body the API silently ignores it."""
    body = VideoMetadata(title="ok").to_request_body()
    assert "notifySubscribers" not in body
    assert "notifySubscribers" not in body["snippet"]
    assert "notifySubscribers" not in body["status"]


def test_request_body_validates_before_returning():
    with pytest.raises(MetadataError):
        VideoMetadata(title="").to_request_body()
