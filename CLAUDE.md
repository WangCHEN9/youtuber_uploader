# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

`ytupload` uploads videos to YouTube via the Data API v3. Its real job is uploading
**Dota 2 offlane (position 3) gameplay** captured with NVIDIA ShadowPlay from
`C:\Users\CHEN\Videos\NVIDIA\Dota 2\`.

**To actually upload a Dota 2 video, use the `dota2-upload` skill** in
`.claude/skills/dota2-upload/`. It carries the title and description conventions. This
file is about changing the code.

## Layout

```
src/ytupload/
  metadata.py    VideoMetadata dataclass + validation + request body
  shadowplay.py  parse capture timestamps out of filenames
  tracker.py     UploadTracker (done) + ResumableSessionStore (in flight)
  auth.py        OAuth2 -> authorized service object
  uploader.py    YoutubeUploader: resumable upload, playlists, thumbnails
  presets.py     named metadata defaults (dota-offlane)
  video.py       ffmpeg: duration probing, frame extraction
  thumbnail.py   Pillow: compose a thumbnail from a frame
  archive.py     move uploaded captures into 'uploaded/'
  cli.py         argparse entry point
tests/           pytest; no network, no credentials
```

Each module has one job. Keep it that way: if a change makes `uploader.py` know about
Dota, it belongs in `presets.py` or the skill instead.

## Working here

```bash
.venv/Scripts/python.exe -m pytest        # tests
.venv/Scripts/python.exe -m ytupload ...  # run the CLI
```

`__init__.py` re-exports only dependency-free modules. Do not import `uploader` or
`auth` there — that would make the package unimportable without the Google libraries
installed, and the tests depend on being able to import without them.

## Decisions worth not re-litigating

These were deliberate. If you are about to undo one, say why first.

- **Uploads are resumable and chunked.** Non-resumable multipart uploads cannot
  survive a multi-gigabyte file. This is the single most important property of the
  tool. The old `socket.setdefaulttimeout(30000)` was a symptom of lacking it, and
  was deleted; do not reintroduce a global socket timeout.
- **`notifySubscribers` is a query parameter**, not a body field. In the body the API
  silently ignores it. `VideoMetadata.to_request_body()` deliberately omits it, and a
  test enforces that.
- **The scope is `youtube.force-ssl`**, not `youtube.upload`. The narrower scope
  cannot touch playlists, thumbnails, or post-upload edits. Narrowing it breaks
  features; widening further is unnecessary.
- **Tokens are JSON, not pickle.** Pickle executes code on load and breaks across
  library upgrades.
- **Metadata is validated before any network call**, so a bad title costs no quota and
  produces a readable error instead of an opaque HTTP 400.
- **`uploaded_files.txt` reads only field `[0]` of each tab-separated line**, which
  keeps the legacy bare-path format working. Do not change the read side without
  keeping that.
- **Resumable sessions are keyed by path *and* size.** A re-encoded file is different
  bytes and must not resume into an old session.
- **`--dry-run` must never require credentials.** It is the rehearsal path, and
  demanding auth would defeat it.
- **No blanket `*.txt` in `.gitignore`.** It previously hid `requirements.txt`. State
  files are ignored by name.
- **Hero identification is done by reading frames, not by computer vision.** Template
  matching against a hero-icon library breaks on HUD skins, resolutions and every new
  hero patch, and needs a database maintained forever. `ytupload frames` extracts
  stills and Claude reads them. Always confirm the reading with the user before it
  reaches a public title.
- **ffmpeg is resolved at call time**, preferring a system binary and falling back to
  the `imageio-ffmpeg` wheel. Do not hardcode a path.
- **`is_long_enough()` returns True when the duration cannot be read.** Refusing to
  upload because a probe failed is worse than uploading something short.
- **Archiving never overwrites.** A name collision gets a `-2` suffix; the existing
  file is an earlier upload and destroying it is unrecoverable.
- **Playlist, thumbnail and archive failures warn rather than raise.** By that point
  the upload has succeeded, and losing the run over a tidiness step would be wrong.

## Constraints

- **Quota: 10,000 units/day.** Upload 1,600, playlist insert 50, thumbnail set 50.
  About 6 uploads per day. Do not raise `MAX_UPLOADS_PER_RUN` without asking.
- **Default privacy is `public`** — the user chose this. A careless `batch` run
  publishes immediately, so keep `--dry-run` prominent in anything you write.
- **ffmpeg ships with the venv** via `imageio-ffmpeg`, so commands must run through
  `.venv/Scripts/python.exe`. There is no `ffprobe` in that wheel: `probe_duration`
  falls back to parsing ffmpeg's own output, so do not assume ffprobe exists.
- **Default min duration is 600s (10 min).** Below that a capture is a clip, not a
  match. The user chose this threshold.
- **Never commit** `secret/`, `token_*.json`, `uploaded_files.txt`,
  `.upload_sessions.json`.

## Testing

Tests must not upload, authenticate, or hit the network. `YoutubeUploader` takes a
`service=` argument for injecting a fake. For anything touching the real API, use
`--dry-run` and have the user confirm — a real upload burns a sixth of the daily quota
and publishes to a live channel.

## Design record

`docs/superpowers/specs/2026-09-25-dota2-uploader-design.md` records why the 2026-09
rewrite happened and what was decided.
