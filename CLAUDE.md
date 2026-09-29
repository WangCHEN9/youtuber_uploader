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
  editor.py      highlight detection, cut planning, NVENC rendering
  thumbnail.py   Pillow: compose a thumbnail from hero art or a frame
  heroart.py     fetch and cache hero renders, item and ability icons
  splash.py      full-bleed hero layout with circular badges (the default)
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
- **No blanket `*.txt` in `.gitignore`.** One used to hide a tracked file that
  nobody noticed was missing. State files are ignored by name instead.
- **Dependencies live only in `pyproject.toml`.** A `requirements.txt` duplicating
  them was removed: nothing installed from it, and two lists drift.
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
- **A thumbnail must never reveal the match result.** There is deliberately no
  win/loss parameter on `make_thumbnail`, a test asserts its absence, and frame mode
  refuses stills from the last 20% of a match. Do not add a result option back.
- **The cut analysis workdir is keyed on the process id, not just the video
  name.** Two concurrent runs of the same video used to delete each other's
  extracted frames mid-analysis, which produced a silently short, wrong edit
  rather than an error. Keep it unique per run.
- **Never use plain `shutil.rmtree` on a directory ffmpeg may have touched.**
  Windows deletes asynchronously and raises WinError 145 while a handle is open.
  Use `ignore_errors=True` and then clear stale files individually.
- **Segment padding is deliberately generous** (25s before, 15s after, 30s
  minimum, 25s merge gap). The first version used 6/6/10/5 and the user reported
  the edit as abrupt: it dropped viewers into the middle of fights with no idea
  why anyone was there, then cut away before the outcome. A fight's run-up is
  most of what makes it readable and happens well before anyone dies. Do not
  tighten these to fit more moments in.
- **No segment-count cap.** One was tried and removed: it made --target-minutes
  do nothing once the ceiling was reached. The padding and merge gap already
  produce few, long scenes, which is what actually matters.
- **`longUploadsStatus` must be `allowed`, not `eligible`.** `eligible` means the
  channel *could* enable uploads over 15 minutes but has not. YouTube accepts an
  over-length upload from such a channel and then deletes the video, so the whole
  transfer is wasted with no error at upload time. A 3.8 GB upload was lost this
  way; `require_upload_length()` and a test now guard it.
- **Always print the destination channel before uploading.** An account owning a
  Brand Account channel silently authorises the *personal* channel, and OAuth
  reuses the last account unless `prompt=select_account` forces the chooser.
- **Playlist and thumbnail failures are warnings, not errors.** Both failed on the
  first real upload (a transient 409, and a 403 because the channel was not yet
  verified for custom thumbnails) and the video was still fine.
- **Chapter marks sit on the cut: one chapter per scene.** Offsetting them past
  the run-up was tried and reverted, because it pushed each scene's opening
  seconds into the previous chapter and misaligned every section from the edit.
  The first mark must be exactly 0:00 or YouTube drops every chapter.
- **The cut planner ranks, it does not detect.** The goal is dropping the least
  interesting half of the midgame, which needs only a relative ranking. A precise
  kill detector would be more fragile and buy nothing. Do not "improve" it into
  one.
- **The clock is excluded from the kill-counter crop.** It sits between the two
  counters and ticks every second, so including it makes every sample look like a
  change.
- **The bisection ceiling must sit strictly above max(interest).** The threshold
  comparison is `>=`, and the returned bound is `high`, so a ceiling *at* the
  maximum lets an over-budget cut be returned when nothing fits. A test covers it.
- **The ending is in every edit.** The user's rule: a match video must show how
  it ended. The last 90s of play (`FINALE_SECONDS`) are reserved before anything
  is ranked, and laning gives way first if the budget is tiny. The end of play
  is found from the HUD disappearing (`detect_game_end`), not a fixed tail
  trim: a 40s trim once cut a 57-minute game off eight seconds before the
  Ancient fell, and the uploaded video never showed the win.
- **The target is a cap, not a quota.** Never pad an edit with filler to reach the
  requested runtime; a quiet match should produce a shorter video.
- **Splash branches on transparency.** An opaque image (a wallpaper, promo art, a
  screenshot) is used full-bleed, because it has no silhouette for the rim glow to
  follow and would otherwise read as a pasted panel. A transparent render is
  composited as a cut-out with rim lighting. `_is_opaque()` decides.
- **The left scrim is only drawn when there are badges.** Dimming a clean image for
  badges that are not there just makes it worse.
- **Splash style draws no text by default.** YouTube prints the title beneath the
  thumbnail already; repeating it inside the image competes with itself. Do not make
  text the default.
- **The brand mark sits bottom-right, diagonally opposite the badges.** They can
  then never collide regardless of badge count. It is also deliberately smaller
  than any badge: it is identity, not information.
- **At most three badges.** More stops reading as a set. Extras are dropped silently.
- **Hero art is the default thumbnail source.** It cannot spoil anything, needs no
  video, and themes itself from colours sampled out of the art.
- **Valve hero slugs are irregular** (Shadow Fiend is `nevermore`, Doom is
  `doom_bringer`). `heroart._IRREGULAR_SLUGS` holds the exceptions; extend it rather
  than changing the default transform.
- **tests/test_cli.py must keep importing cli.py.** A syntax error there once survived
  a fully green run because nothing imported the module.

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
