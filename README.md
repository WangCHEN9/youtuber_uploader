# ytupload

Upload gameplay videos to YouTube with **resumable uploads** and metadata worth reading.

Built for NVIDIA ShadowPlay captures of Dota 2 offlane games, but nothing here is
Dota-specific except one optional preset.

## Why not just use YouTube Studio

- **Resumable, chunked uploads.** Multi-gigabyte captures survive a dropped
  connection; re-running the same command continues where it stopped.
- **Metadata from the command line**, so a script or an assistant can write a real
  title, description, chapters and tags instead of a capture timestamp.
- **No duplicate uploads.** Completed uploads are recorded and skipped.
- **Playlists and thumbnails** handled in the same run.

## Setup

### 1. Google Cloud project

1. Create a project at <https://console.cloud.google.com/>.
2. Enable **YouTube Data API v3**.
3. Under *APIs & Services → Credentials*, create an **OAuth 2.0 Client ID** of type
   **Desktop app**.
4. Download the JSON and save it as `secret/secret.json`.

You do not need to register a redirect URI. The tool binds a random loopback port,
which desktop-app credentials accept — this is what avoids the `redirect_uri_mismatch`
error.

### 2. Install

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -e .
```

Requires Python 3.9 or newer.

### 3. Authorize

```bash
python -m ytupload auth
```

A browser window opens once. On success it prints your channel name and writes
`token_youtube_v3.json`. Confirm your account can upload at
<https://www.youtube.com/verify>.

## Usage

### One video

```bash
python -m ytupload upload "C:\Users\CHEN\Videos\NVIDIA\Dota 2\Dota 2 2026.09.25 - 21.59.04.14.mp4" \
  --title "Centaur Offlane vs Timbersaw - 41 Minute Comeback | Dota 2 Pos 3" \
  --description-file description.md \
  --tags "Centaur Warrunner,Timbersaw,comeback" \
  --preset dota-offlane \
  --dry-run
```

`--dry-run` validates everything and prints the exact request without uploading. It
needs no credentials and costs no quota. **Drop it to upload for real.**

> Privacy defaults to `public`. Use `--privacy unlisted` or `--privacy private` to stage
> a video instead of publishing it.

### A folder

```bash
python -m ytupload batch "C:\Users\CHEN\Videos\NVIDIA\Dota 2" --preset dota-offlane
```

Skips anything already uploaded, stops at the daily quota, and keeps going if one
video fails. Titles fall back to the filename, so prefer `upload` when the title
matters.

### Useful options

| Option | Purpose |
|---|---|
| `--description-file` | Read the description from a file. Preferred: descriptions are long and multi-line. |
| `--preset dota-offlane` | Adds offlane tags, the `Dota 2 - Offlane` playlist, and a description footer. |
| `--playlist "Name"` | Add to a playlist, creating it if absent. |
| `--thumbnail path.png` | Set a custom thumbnail (requires a verified account). |
| `--privacy` | `public` (default), `unlisted`, or `private`. |
| `--notify` | Notify subscribers. Off by default. |
| `--dry-run` | Rehearse without uploading or authenticating. |

## Quota

A default project gets **10,000 units per day**. An upload costs **1,600**, so about
**6 uploads per day**; playlist and thumbnail calls cost 50 each. Past that the API
returns 403 until the quota resets at midnight Pacific.

## Files it writes

| File | Contents | Committed? |
|---|---|---|
| `secret/secret.json` | OAuth client secret | No |
| `token_youtube_v3.json` | Your credentials | No |
| `uploaded_files.txt` | Completed uploads, tab separated | No |
| `.upload_sessions.json` | In-progress resumable sessions | No |

All four are git-ignored. Never commit them.

## Layout

```
src/ytupload/
  metadata.py    what is being uploaded, and its validation
  shadowplay.py  parsing NVIDIA capture filenames
  tracker.py     what has been uploaded, and what is half-uploaded
  auth.py        OAuth2
  uploader.py    resumable upload, playlists, thumbnails
  presets.py     reusable metadata defaults
  cli.py         command-line interface
```

## Tests

```bash
pip install pytest
pytest
```

The suite covers metadata validation, filename parsing, and persistence. It performs
no uploads and needs no credentials.

## License

MIT. See [LICENSE](LICENSE).
