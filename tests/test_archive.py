"""Moving captures into the uploaded folder."""

import pytest

from ytupload.archive import (
    ArchiveError,
    archive_dir_for,
    archive_video,
    is_archived,
)


def _make_file(directory, name="capture.mp4", content=b"data"):
    path = directory / name
    path.write_bytes(content)
    return path


def test_moves_into_an_uploaded_subfolder(tmp_path):
    video = _make_file(tmp_path)
    moved = archive_video(video)

    assert moved.parent == tmp_path / "uploaded"
    assert moved.exists()
    assert not video.exists()


def test_contents_are_preserved(tmp_path):
    video = _make_file(tmp_path, content=b"gameplay bytes")
    assert archive_video(video).read_bytes() == b"gameplay bytes"


def test_creates_the_folder_when_absent(tmp_path):
    video = _make_file(tmp_path)
    assert not (tmp_path / "uploaded").exists()
    archive_video(video)
    assert (tmp_path / "uploaded").is_dir()


def test_an_already_archived_file_is_left_alone(tmp_path):
    archive = tmp_path / "uploaded"
    archive.mkdir()
    video = _make_file(archive)

    assert archive_video(video) == video
    assert video.exists()


def test_a_name_collision_never_overwrites(tmp_path):
    """The existing file is an earlier upload; destroying it is unrecoverable."""
    archive = tmp_path / "uploaded"
    archive.mkdir()
    existing = _make_file(archive, content=b"first")

    video = _make_file(tmp_path, content=b"second")
    moved = archive_video(video)

    assert moved != existing
    assert existing.read_bytes() == b"first"
    assert moved.read_bytes() == b"second"
    assert moved.name == "capture-2.mp4"


def test_repeated_collisions_keep_counting(tmp_path):
    archive = tmp_path / "uploaded"
    archive.mkdir()
    _make_file(archive)
    (archive / "capture-2.mp4").write_bytes(b"x")

    moved = archive_video(_make_file(tmp_path))
    assert moved.name == "capture-3.mp4"


def test_missing_file_raises(tmp_path):
    with pytest.raises(ArchiveError, match="not a file"):
        archive_video(tmp_path / "nope.mp4")


def test_is_archived_detection(tmp_path):
    assert is_archived(tmp_path / "uploaded" / "a.mp4") is True
    assert is_archived(tmp_path / "a.mp4") is False


def test_archive_dir_is_a_sibling_of_the_file(tmp_path):
    """Same volume, so the move is a rename rather than an 8 GB copy."""
    video = tmp_path / "a.mp4"
    assert archive_dir_for(video) == tmp_path / "uploaded"
    assert archive_dir_for(video).drive == video.drive
