# Dota 2 Upload Workflow — Design

**Date**: 2026-09-25
**Status**: Approved

## Problem

`youtuber_uploader` (last touched 2026-01) uploads videos using the filename as both
title and description. It is used for Dota 2 gameplay captured with NVIDIA ShadowPlay,
where filenames look like `Dota 2 2026.09.25 - 21.59.04.14.mp4` — a recording timestamp
carrying no information about hero, role, or outcome. Recordings are large (~8 GB).

Two things are therefore broken for the intended use:

1. **Uploads of this size cannot succeed reliably.** `MediaFileUpload` is constructed
   without `resumable=True`, so the whole file goes in one multipart HTTP request with
   no retry, no progress, and no recovery. The 8.3-hour `socket.setdefaulttimeout(30000)`
   in `main.py` is a symptom of this.
2. **There is no way to supply good metadata.** Title and description are hardcoded to
   the filename, so every video would be published as `Dota 2 2026.09.25 - 21.59.04.14`.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Metadata source | Written per-video by Claude | Filenames carry no content info; OpenDota would need a match ID per video and produces templated prose. Quality is the goal. |
| OAuth scope | `youtube.force-ssl` | `youtube.upload` cannot set thumbnails, touch playlists, or edit a description after upload. Re-consent once now rather than hit the ceiling later. |
| Interface | CLI + in-repo Claude skill | The CLI is the mechanism; the skill is the memory, so conventions survive across sessions. |
| Default privacy | `public` | User's choice. Mitigated by `--dry-run` and an echoed privacy line before upload. |
| Video duration / trimming | Out of scope | `ffmpeg`/`ffprobe` are not installed and adding them is not needed for upload. |

## Architecture

    cli.py            argument parsing, metadata assembly, --dry-run
      └── main.py     YoutubeUploader: validation, resumable upload, playlist, thumbnail
            └── GoogleService.py   OAuth2 -> authorized service object

### GoogleService.py
- Token storage moves from pickle to `token_youtube_v3.json` (`Credentials.to_json()`).
  Pickle is fragile across library upgrades and executes code on load.
- Scope widened to `youtube.force-ssl`. A stored token lacking the new scope is detected
  via `has_scopes()` and discarded so consent re-runs, instead of failing as a late 403.
- `run_local_server(port=0)`, which avoids the `redirect_uri_mismatch` failure the README
  currently devotes two sections to.
- Authentication failures raise rather than returning `None`.

### main.py
- `MediaFileUpload(..., chunksize=8MB, resumable=True)` driven by a `next_chunk()` loop
  reporting percentage and MB transferred.
- Exponential backoff on retriable failures (HTTP 500/502/503/504 and socket errors).
- The resumable session URI is persisted to `.upload_sessions.json`, keyed by path+size.
  Resumable sessions stay valid ~1 week, so an interrupted 8 GB upload continues rather
  than restarting.
- `socket.setdefaulttimeout(30000)` removed — obsolete once uploads are resumable.
- `notifySubscribers` moved from the request body to a query parameter. It is defined by
  the API as a parameter, so in the body it was silently ignored.
- Metadata validated before the API call: title <= 100 chars, description <= 5000, tags
  <= 500 chars total, no angle brackets. Prevents opaque HTTP 400s.
- Tracking file read once into a set instead of re-read per loop iteration.
- Per-video `try/except` so one failure does not abort a batch.
- New: `set_thumbnail()`, `find_or_create_playlist()`, `add_to_playlist()`.
- New: `parse_shadowplay_datetime()` for `Dota 2 YYYY.MM.DD - HH.MM.SS.NN.mp4`.

### cli.py

    python cli.py upload "<file>" --title "..." --description-file desc.md \
      --tags "dota 2,offlane,position 3" --playlist "Dota 2 - Offlane" \
      --privacy public [--thumbnail t.png] [--dry-run]

`--description-file` rather than an inline string: descriptions are long and multi-line,
and shell-quoting them is error-prone.

### .claude/skills/dota2-upload/SKILL.md
Encodes the position-3 offlane defaults and tag set, ShadowPlay filename parsing, title
conventions, the description skeleton, and the exact command.

## Testing

A real upload cannot be used for verification: the user's only recording is being
uploaded manually, OAuth credentials do not yet exist on this machine, and uploads cost
1,600 quota units each against a 10,000/day budget.

- Unit tests: metadata validation limits, ShadowPlay date parsing, tracking-file dedupe,
  session-resume key derivation.
- `--dry-run` against a small dummy file to confirm the request body is assembled
  correctly, consuming no quota.
- OAuth flow verified by the user against real credentials (planned: 2026-09-26).

## Known blockers

- `secret/secret.json` is absent; the user will create OAuth credentials on 2026-09-26.
- No Python environment with the Google client libraries exists on this machine
  (Python 3.14 present, no conda). `requirements.txt` will be added.
