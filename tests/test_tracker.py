"""Upload tracking and resumable-session persistence."""

import json

from ytupload.tracker import ResumableSessionStore, UploadTracker


# ------------------------------------------------------------- UploadTracker


def test_unknown_file_is_not_uploaded(tmp_path):
    tracker = UploadTracker(tmp_path / "uploaded.txt")
    assert tracker.already_uploaded(tmp_path / "a.mp4") is False


def test_recorded_file_is_remembered(tmp_path):
    tracker = UploadTracker(tmp_path / "uploaded.txt")
    video = tmp_path / "a.mp4"
    tracker.record(video, "abc123")
    assert tracker.already_uploaded(video) is True


def test_record_survives_a_new_tracker_instance(tmp_path):
    path = tmp_path / "uploaded.txt"
    video = tmp_path / "a.mp4"
    UploadTracker(path).record(video, "abc123")
    assert UploadTracker(path).already_uploaded(video) is True


def test_legacy_bare_path_format_is_still_read(tmp_path):
    """Older versions wrote one bare path per line, with no video ID."""
    path = tmp_path / "uploaded.txt"
    video = tmp_path / "old.mp4"
    path.write_text(f"{video}\n", encoding="utf-8")

    tracker = UploadTracker(path)
    assert tracker.already_uploaded(video) is True


def test_new_format_stores_the_video_id(tmp_path):
    path = tmp_path / "uploaded.txt"
    UploadTracker(path).record(tmp_path / "a.mp4", "xyz789")
    assert "xyz789" in path.read_text(encoding="utf-8")


def test_blank_lines_are_ignored(tmp_path):
    path = tmp_path / "uploaded.txt"
    path.write_text("\n\n   \n", encoding="utf-8")
    assert UploadTracker(path).uploaded == set()


def test_the_file_is_read_only_once(tmp_path):
    """The cache is what stops the old per-iteration re-read of the whole file."""
    path = tmp_path / "uploaded.txt"
    video = tmp_path / "a.mp4"
    path.write_text(f"{video}\n", encoding="utf-8")

    tracker = UploadTracker(path)
    assert tracker.already_uploaded(video) is True

    path.write_text("", encoding="utf-8")  # change disk out from under it
    assert tracker.already_uploaded(video) is True  # served from cache


# ------------------------------------------------------ ResumableSessionStore


def _make_video(tmp_path, name="a.mp4", size=1024):
    video = tmp_path / name
    video.write_bytes(b"x" * size)
    return video


def test_no_session_for_an_unseen_file(tmp_path):
    store = ResumableSessionStore(tmp_path / "sessions.json")
    assert store.get(_make_video(tmp_path)) is None


def test_saved_session_is_returned(tmp_path):
    store = ResumableSessionStore(tmp_path / "sessions.json")
    video = _make_video(tmp_path)
    store.save(video, "https://upload.example/session/1")
    assert store.get(video) == "https://upload.example/session/1"


def test_session_is_invalidated_when_the_file_size_changes(tmp_path):
    """A re-encoded file is different bytes; resuming into it would corrupt it."""
    store = ResumableSessionStore(tmp_path / "sessions.json")
    video = _make_video(tmp_path, size=1024)
    store.save(video, "https://upload.example/session/1")

    video.write_bytes(b"y" * 2048)
    assert store.get(video) is None


def test_clear_removes_the_session(tmp_path):
    store = ResumableSessionStore(tmp_path / "sessions.json")
    video = _make_video(tmp_path)
    store.save(video, "https://upload.example/session/1")
    store.clear(video)
    assert store.get(video) is None


def test_clearing_an_absent_session_is_harmless(tmp_path):
    store = ResumableSessionStore(tmp_path / "sessions.json")
    store.clear(_make_video(tmp_path))  # must not raise


def test_a_corrupt_session_file_does_not_block_uploading(tmp_path):
    path = tmp_path / "sessions.json"
    path.write_text("{ not json", encoding="utf-8")
    store = ResumableSessionStore(path)
    assert store.get(_make_video(tmp_path)) is None


def test_sessions_for_different_files_coexist(tmp_path):
    store = ResumableSessionStore(tmp_path / "sessions.json")
    first = _make_video(tmp_path, "a.mp4", 100)
    second = _make_video(tmp_path, "b.mp4", 200)
    store.save(first, "uri-a")
    store.save(second, "uri-b")
    assert store.get(first) == "uri-a"
    assert store.get(second) == "uri-b"


def test_saving_the_same_uri_twice_leaves_one_entry(tmp_path):
    path = tmp_path / "sessions.json"
    store = ResumableSessionStore(path)
    video = _make_video(tmp_path)
    store.save(video, "uri-a")
    store.save(video, "uri-a")
    assert len(json.loads(path.read_text(encoding="utf-8"))) == 1
