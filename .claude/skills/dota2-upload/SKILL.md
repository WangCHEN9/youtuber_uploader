---
name: dota2-upload
description: Use when the user wants to upload a Dota 2 gameplay video to YouTube - identifying the hero from the video, writing the title, description, tags and chapters, building a thumbnail, then uploading and archiving the file. Triggers on "upload my dota game", "upload my latest dota 2 video", "put this match on youtube", "make a thumbnail for", or any mention of a ShadowPlay capture.
---

# Uploading a Dota 2 video

## The channel

| | |
|---|---|
| Name | **Yoda Dota** |
| Handle | `@yodaofflane` |
| Mascot | the user's cat, Yoda - the channel is named after the cat, not Star Wars |
| Player | Immortal, position 3 (offlane). In-game ID: Yoda |

Keep the rank out of titles and thumbnails; it belongs in the channel description.
Lean the visual identity on the cat, never on Star Wars imagery.

Every thumbnail should carry the mascot via `--brand-image`, so the channel is
recognisable in a sidebar.


The user plays **position 3 (offlane)**. Captures come from NVIDIA ShadowPlay:

```
C:\Users\CHEN\Videos\NVIDIA\Dota 2\
```

Run everything from the repo, using its venv:

```bash
cd C:\Users\CHEN\github\youtuber_uploader
.venv/Scripts/python.exe -m ytupload <command>
```

Filenames look like `Dota 2 2026.09.25 - 21.59.04.14.mp4` — a capture timestamp and
nothing more. The tool extracts the date automatically. **Everything else you get by
looking at the video.**

## Workflow

### 1. Find the video, and skip the clips

```bash
.venv/Scripts/python.exe -m ytupload frames "<video path>"
```

This prints the duration and extracts three stills. **Anything under 10 minutes is a
clip or a misfire, not a match** — say so and confirm before going further. `batch`
applies that 10-minute rule automatically.

If several captures are new, ask which one. Never assume the newest is the one meant.

### 2. Identify the hero by reading the frames

`frames` writes three stills to `.frames/<video name>/`. **Read them as images.**

- **`scoreboard.jpg`** — sampled near the end, so it usually catches the post-game
  screen. This is the richest single frame: your hero, all ten picks, K/D/A, net
  worth, match duration, and who won, all at once. Start here.
- **`midgame.jpg`** — a teamfight or push, typically. Good thumbnail material.
- **`laning.jpg`** — the early lane, which shows what you were up against.

From these, work out: **your hero**, the **enemy offlane matchup**, the **result**,
and the **final score**. If the capture starts mid-game or the end screen is missing,
say what you could and could not determine.

**Always show the user what you concluded before using it.** Misreading a portrait is
easy, and a confidently wrong hero name in a public title is worse than one question.
Ask for anything the frames cannot tell you — notable moments, item timings, how the
game actually felt.

If you need a different moment, grab it directly:

```bash
.venv/Scripts/python.exe -m ytupload frames "<video>" --at 1320
```

### 3. Cut it down (optional, ask first)

A full match is 40+ minutes. To cut it to a watchable highlight edit:

```bash
.venv/Scripts/python.exe -m ytupload cut "<video>" --target-minutes 25 --dry-run
```

`--dry-run` prints the cut plan and renders nothing. Show it to the user. Drop
`--dry-run` to render to `<name> - cut.mp4`, then upload **that** file.

- The laning phase is kept whole (`--lane-minutes`, default 10), because that is
  what offlane viewers come for. The rest is ranked by audio loudness and kill-
  counter activity, and the quietest parts are dropped.
- Game start is detected automatically; it is not the start of the recording.
- The target is a **cap, not a quota** — a quiet match produces a shorter video
  rather than one padded with farming.
- Analysis takes ~2 minutes; rendering a 25-minute 1440p60 edit takes a few
  minutes on the GPU.

**Always watch or spot-check the result before uploading.** The detector is a
heuristic; it can cut a quiet gank or keep a loud nothing.

### 3. Write the metadata

**Keep the result out of the title too.** "41 Minute Comeback" and "Brutal Loss"
both spoil it. Tease the matchup and the hero instead.

**Title** — aim for **60–70 characters** (hard cap is 100, but search truncates near
70). Front-load hero and role, then the hook. No all-caps, no manufactured outrage.

Good:
```
Mars Offlane vs Morphling and Hoodwink | Dota 2 Position 3
Tidehunter Into a Double Melee Lane | Dota 2 Offlane Gameplay
```

Avoid: `Dota 2 2026.09.25 - 21.59.04.14`, `INSANE GAME!!! MUST WATCH`, and anything
naming the outcome.

**Description** — write to a temp file, pass `--description-file`:

1. **Hook, 1–2 sentences.** Only the first ~150 characters show in search, so put the
   matchup and the outcome there.
2. **A short paragraph** on how the game went.
3. **Chapters**, if you have timestamps.

YouTube only makes chapters when **the first is `0:00`**, there are **at least three**,
and each is **10 seconds or longer**. If you cannot meet all three, write plain
timestamps and do not call them chapters.

Do not write the recording date, the "Position 3 / offlane" line, or the subscribe
line — `--preset dota-offlane` appends those. Writing them yourself duplicates them.

**Tags** — only what is specific to this video: hero names, the enemy laner, the
patch, the theme. The preset already supplies `Dota 2`, `Dota2`, `dota 2 gameplay`,
`offlane`, `position 3`, `pos 3`, `offlaner`, `ranked`. Budget is 500 characters
total, so 5–8 extra tags is about right.

### 4. Build a thumbnail

**Never reveal the result** — not in the image, not in the text, not in the title.

**Default: splash style, hero art, no text.** YouTube prints the title directly under
the thumbnail, so words inside the image duplicate it and compete for the same glance.
Let the art carry the frame and use circular badges to say what the video is about.

```bash
.venv/Scripts/python.exe -m ytupload thumbnail --hero "Mars"   --badges "blink,mars_arena_of_blood"   --brand-image brand/yoda.png   --out mars-thumb.jpg
```

- `--badges` takes up to three items or abilities. Items are plain names (`blink`,
  `black king bar`, `assault cuirass`); abilities use their internal name
  (`mars_arena_of_blood`). Pick the ones the game actually turned on.
- The background colour is sampled from the hero art, so each hero themes itself.
- `--brand-image` puts the channel mascot in the bottom-right corner, diagonally
  opposite the badges. Use it on every thumbnail for a consistent identity.
- `--style portrait` switches to the hero-beside-large-text layout.
- `--with-text` adds the headline to a splash thumbnail. Usually leave it off.

Art is downloaded from Valve's CDN and cached in `.heroart/`. Use display names
(`"Shadow Fiend"`, `"Nature's Prophet"`); irregular Valve slugs are handled.

**Official hero promo art usually looks better than the stock render.** Valve's CDN
render is lit flat for a menu; the hero-release artwork is composed and lit for
impact. If the user has such an image, pass it with `--hero-image` — an opaque
rectangular image is detected and used full-bleed, while a transparent PNG is
composited as a cut-out with rim lighting. Both get the vignette, the sampled
accent colour and the badges.

#### Custom cosmetics

The official render shows **default cosmetics**. To show the user's own set:

1. **Best quality** — ask them for a screenshot from the in-game **Armory or Hero
   Demo**, where the hero is rendered large and front-on with their items. Then:
   `--hero-image their-screenshot.png`.
2. **From the match, no extra work** — cut the hero out of a gameplay frame:

```bash
.venv/Scripts/python.exe -c "from ytupload.thumbnail import feathered_cutout;   feathered_cutout('.frames/<name>/midgame.jpg', 'cut.png', center=(0.42, 0.33), size=0.20)"
```

   `center` is the hero's position as a fraction of the frame; look at the frame to
   find it. The radial fade removes the terrain and the floating health bar. **Expect
   noticeably softer art**: the in-game model is only ~160px tall even at 1440p, and
   the top-down angle never looks like hero art. Offer option 1 first.

**Frame mode** still exists for a specific moment:

```bash
.venv/Scripts/python.exe -m ytupload thumbnail "<video>" --headline "Mars" --at 1200
```

Frames past 80% of the match are refused as spoilers. The HUD is cropped automatically.

**Look at the result before using it.**

### 5. Dry run, confirm, upload

**Always `--dry-run` first** and show the user. Privacy defaults to **public**, so an
unreviewed run publishes immediately.

```bash
.venv/Scripts/python.exe -m ytupload upload "<video>" \
  --title "<title>" \
  --description-file "<desc file>" \
  --tags "Centaur Warrunner,Timbersaw,comeback" \
  --preset dota-offlane \
  --thumbnail "<thumb.jpg>" \
  --archive \
  --dry-run
```

Get explicit approval, then re-run without `--dry-run`.

`--archive` moves the file to `...\Dota 2\uploaded\` once the upload succeeds. It is a
same-drive rename, so it is instant even at 8 GB, and the new location is recorded so
it is never re-uploaded.

Uploads are resumable and print progress. An 8 GB capture takes a while — that is
normal, not a hang. **If interrupted, re-running the same command resumes** from where
it stopped; the session stays valid about a week.

On success you get the URL, the video is added to the **`Dota 2 - Offlane`** playlist
(created if needed), and the upload is recorded.

## Things that will bite you

- **Quota is 6 uploads per day.** Each costs 1,600 units of 10,000. A playlist add and
  a thumbnail set cost 50 each. Exceeding it returns 403 until midnight Pacific. Never
  batch-upload speculatively.
- **Custom thumbnails need a verified YouTube account.** If `--thumbnail` warns, the
  video still uploaded fine; only the thumbnail failed.
- **The playlist and thumbnail steps never fail the upload.** They warn. If you see a
  warning, the video is safely up — fix the extra separately.
- **`frames` and `thumbnail` need no credentials and cost no quota.** Run them freely.
- **The `scoreboard.jpg` review frame shows the result.** That is fine for working out
  what happened, but it must never become a thumbnail.
- **ffmpeg comes from the venv** (`imageio-ffmpeg`), so commands must use
  `.venv/Scripts/python.exe`, not a system Python.

## Batch mode

For several captures at once. Titles fall back to the filename, which is poor — prefer
uploading individually with real titles unless the user explicitly wants a dump.

```bash
.venv/Scripts/python.exe -m ytupload batch "C:\Users\CHEN\Videos\NVIDIA\Dota 2" \
  --preset dota-offlane --privacy unlisted --archive --dry-run
```

Skips anything already uploaded, anything under 10 minutes, and anything already in
`uploaded\`. Use `--min-duration 0` to include short clips.
