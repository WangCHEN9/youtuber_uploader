"""OAuth2 for the YouTube Data API v3.

Credentials are stored as JSON rather than pickle. Pickle files break across library
upgrades and execute arbitrary code when loaded, neither of which is acceptable for a
file that lives beside the code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

#: ``force-ssl`` covers uploading *and* playlists, thumbnails, and post-upload edits.
#: The narrower ``youtube.upload`` scope can only create videos.
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

API_NAME = "youtube"
API_VERSION = "v3"

DEFAULT_CLIENT_SECRET_FILE = Path("secret/secret.json")
DEFAULT_TOKEN_FILE = Path("token_youtube_v3.json")


class AuthError(RuntimeError):
    """Authentication could not be completed."""


def find_client_secret(path: Path = DEFAULT_CLIENT_SECRET_FILE) -> Path:
    """Locate the OAuth client secret file.

    Google Cloud Console downloads these as
    ``client_secret_<id>.apps.googleusercontent.com.json``, so accept that name
    as well rather than making every user rename the file by hand.

    Returns *path* unchanged when nothing is found, so the caller can raise an
    error naming the location the user expected.
    """
    path = Path(path)
    if path.is_file():
        return path
    candidates = sorted(path.parent.glob("client_secret*.json"))
    return candidates[0] if candidates else path


def _load_credentials(token_file: Path, scopes: Sequence[str]) -> Credentials | None:
    """Load stored credentials, or ``None`` if they are missing or unusable."""
    if not token_file.exists():
        return None
    try:
        credentials = Credentials.from_authorized_user_file(str(token_file), list(scopes))
    except (ValueError, OSError):
        return None

    # A token minted under narrower scopes cannot be refreshed into wider ones.
    # Detect that here so the user re-consents now, instead of meeting a confusing
    # 403 later when the first playlist or thumbnail call is made.
    if not credentials.has_scopes(list(scopes)):
        return None

    if credentials.valid:
        return credentials

    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            return credentials
        except RefreshError:
            return None

    return None


def get_credentials(
    client_secret_file: Path = DEFAULT_CLIENT_SECRET_FILE,
    token_file: Path = DEFAULT_TOKEN_FILE,
    scopes: Sequence[str] = YOUTUBE_SCOPES,
) -> Credentials:
    """Return usable credentials, running the browser consent flow if required."""
    token_file = Path(token_file)
    credentials = _load_credentials(token_file, scopes)

    if credentials is None:
        client_secret_file = find_client_secret(client_secret_file)
        if not client_secret_file.exists():
            raise AuthError(
                f"OAuth client secret not found at {client_secret_file}.\n"
                "Create an OAuth 2.0 Client ID of type 'Desktop app' at\n"
                "  https://console.cloud.google.com/apis/credentials\n"
                f"then save the downloaded JSON to {client_secret_file}."
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret_file), list(scopes)
        )
        # port=0 picks a free loopback port. Desktop-app credentials accept any
        # loopback port, which sidesteps the redirect_uri_mismatch error entirely.
        #
        # prompt="select_account consent" forces the account chooser every time.
        # Without it Google silently reuses the last account, and an account with
        # a Brand Account channel will quietly authorise the personal channel
        # instead - which means uploading to the wrong channel with no warning.
        credentials = flow.run_local_server(
            port=0, prompt="select_account consent"
        )

    token_file.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def build_youtube_service(
    client_secret_file: Path = DEFAULT_CLIENT_SECRET_FILE,
    token_file: Path = DEFAULT_TOKEN_FILE,
    scopes: Sequence[str] = YOUTUBE_SCOPES,
):
    """Return an authorized YouTube Data API v3 service object."""
    credentials = get_credentials(client_secret_file, token_file, scopes)
    return build(API_NAME, API_VERSION, credentials=credentials)
