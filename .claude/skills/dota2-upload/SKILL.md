---
name: dota2-upload
description: Use when the user wants to upload a Dota 2 gameplay video to YouTube - writing the title, description, tags and chapters, then running the upload. Triggers on "upload my dota game", "upload my latest dota 2 video", "put this match on youtube", or any mention of uploading a ShadowPlay capture.
---

# Uploading a Dota 2 video

The user plays **position 3 (offlane)**. Captures come from NVIDIA ShadowPlay and live in:

```
C:\Users\CHEN\Videos\NVIDIA\Dota 2\
```

Filenames look like `Dota 2 2026.09.25 - 21.59.04.14.mp4` — a capture timestamp and
nothing else. **They never tell you the hero, the matchup, or the result.** The tool
extracts the date automatically; everything else must come from the user.

## Workflow

### 1. Find the video

List the capture folder and pick the file. If more than one is new, ask which.
Never assume the newest is the one they mean.

### 2. Get the facts you cannot guess

Ask for whatever the user has not already said. Keep it to one short message:

- **Hero** they played, and the **lane matchup** faced
- **Outcome** (win/loss) and roughly how long the game ran
- **One thing that made it interesting** — a comeback, a key item timing, a teamfight
- **Timestamps**, if they have any

If they answer only some of it, write around the gaps rather than asking twice. A good
description of a game you know three facts about beats an interrogation.

### 3. Write the metadata

**Title** — aim for **60–70 characters** (the hard cap is 100, but search results
truncate around 70). Front-load hero and role, then the hook. No all-caps, no
manufactured outrage.

Good:
```
Centaur Offlane vs Timbersaw — 41 Minute Comeback | Dota 2 Pos 3
Tidehunter Into Double Melee Lane | Dota 2 Offlane Gameplay
```

Avoid: `Dota 2 2026.09.25 - 21.59.04.14`, `INSANE GAME!!! MUST WATCH`

**Description** — write it to a temp file and pass `--description-file`. Structure:

1. **Hook, 1–2 sentences.** Only the first ~150 characters show in search results, so
   put the matchup and the outcome there.
2. **A short paragraph** on how the game actually went.
3. **Chapters**, if you have timestamps.

YouTube only turns timestamps into chapters when **the first one is `0:00`**, there are
**at least three**, and each is **10 seconds or longer**. If you cannot meet all three
conditions, write plain timestamps and do not call them chapters.

Do not add the recording date, the "Position 3 / offlane" line, or the subscribe line —
`--preset dota-offlane` appends those automatically. Adding them yourself duplicates them.

**Tags** — pass only what is specific to this video: hero names, the enemy laner, the
patch, the theme. The preset already supplies `Dota 2`, `Dota2`, `dota 2 gameplay`,
`offlane`, `position 3`, `pos 3`, `offlaner`, `ranked`. The budget is 500 characters
across all tags combined, so roughly 5–8 extra tags is right.

### 4. Dry run, then confirm

**Always `--dry-run` first**, and show the user the result. Privacy defaults to
**public**, so an unreviewed run publishes immediately.

```bash
cd C:\Users\CHEN\github\youtuber_uploader
.venv/Scripts/python.exe -m ytupload upload "<video path>" \
  --title "<title>" \
  --description-file "<temp description file>" \
  --tags "Centaur Warrunner,Timbersaw,comeback,dota 2 patch 7.39" \
  --preset dota-offlane \
  --dry-run
```

Get explicit approval, then re-run without `--dry-run`.

### 5. Upload

Uploads are resumable and print progress. An 8 GB capture takes a while — that is
normal, not a hang. If it is interrupted, **re-running the same command resumes** from
where it stopped; the session URI is kept in `.upload_sessions.json` and stays valid
about a week.

On success the tool prints the video URL, adds it to the **`Dota 2 - Offlane`** playlist
(creating it if needed), and records the upload in `uploaded_files.txt` so it is never
uploaded twice.

## Things that will bite you

- **Quota is 6 uploads per day.** Each upload costs 1,600 units of a 10,000 daily
  budget. Exceeding it returns a 403 until midnight Pacific. Never batch-upload
  speculatively.
- **First run of the day needs no re-auth**, but if `token_youtube_v3.json` is missing
  or was created under the old upload-only scope, a browser consent window opens.
  Run `python -m ytupload auth` first to get that out of the way.
- **Custom thumbnails require a verified YouTube account.** If `--thumbnail` warns, the
  video is still uploaded fine; only the thumbnail failed.
- **No `ffmpeg` on this machine**, so you cannot read a video's duration or trim it.
  Ask the user for the match length instead of trying to detect it.

## Batch mode

For several captures at once. Titles fall back to the filename, which is poor — prefer
uploading individually with real titles unless the user explicitly wants them dumped.

```bash
.venv/Scripts/python.exe -m ytupload batch "C:\Users\CHEN\Videos\NVIDIA\Dota 2" \
  --preset dota-offlane --privacy unlisted --dry-run
```
