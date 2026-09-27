"""Locating the OAuth client secret."""

from ytupload.auth import find_client_secret


def test_the_expected_name_wins(tmp_path):
    expected = tmp_path / "secret.json"
    expected.write_text("{}", encoding="utf-8")
    (tmp_path / "client_secret_123.apps.googleusercontent.com.json").write_text("{}")
    assert find_client_secret(expected) == expected


def test_googles_download_name_is_accepted(tmp_path):
    """Cloud Console names the file for you; requiring a rename is a pointless
    step every user has to be told about."""
    downloaded = tmp_path / "client_secret_123.apps.googleusercontent.com.json"
    downloaded.write_text("{}", encoding="utf-8")
    assert find_client_secret(tmp_path / "secret.json") == downloaded


def test_missing_returns_the_expected_path_for_the_error_message(tmp_path):
    expected = tmp_path / "secret.json"
    assert find_client_secret(expected) == expected


def test_the_newest_style_name_is_picked_deterministically(tmp_path):
    for name in ("client_secret_b.json", "client_secret_a.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    assert find_client_secret(tmp_path / "secret.json").name == "client_secret_a.json"
