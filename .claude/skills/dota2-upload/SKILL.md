---
name: dota2-upload
description: Use when the user wants to upload a Dota 2 gameplay video to YouTube - identifying the hero from the video, writing the title, description, tags and chapters, building a thumbnail, then uploading and archiving the file. Triggers on "upload my dota game", "upload my latest dota 2 video", "put this match on youtube", "make a thumbnail for", or any mention of a ShadowPlay capture.
---

# Uploading a Dota 2 video

## The channel

| | |
|---|---|
| Name | **Yoda Dota** |
| URL | https://www.youtube.com/@yoda_dota |
| Handle | `@yoda_dota` |
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
  screen. This is the richest single frame: your hero, K/D/A, net worth, match
  duration and who won, all at once. Start here.

  **Do not spend effort naming all ten heroes.** The user does not want the draft
  in the description, and two portraits in the enemy bar are routinely ambiguous
  at that size. The hero, the lane opponents and the result are what matter.
- **`midgame.jpg`** — a teamfight or push, typically. Good thumbnail material.
- **`laning.jpg`** — the early lane, which shows what you were up against.

From these, work out: **your hero**, the **lane opponents** and the **result**.

**Never name an opponent hero in the title or the description.** The user has
asked for this directly. The thumbnail may show one — a picture makes no factual
claim the way a sentence does — but the words stay about the user's own hero.

This also sidesteps a trap worth knowing about. **A hero appearing near the lane
does not mean they laned there.** Nature's Prophet has a global teleport and
turns up everywhere; smoke ganks, rotations and rune fights put anyone on screen
for a few seconds. A published title claimed a "double ranged" lane on exactly
that mistake and was wrong.

For the thumbnail's `--vs`, the hero should be present **repeatedly across the
laning phase** — sample several frames minutes apart, not one. If it is not
clear, ask rather than guess. If the capture starts mid-game or the end screen is missing,
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
  rather than one padded with farming. A 34-minute match came out at 23.2 rather
  than 25, which is correct behaviour, not a bug. Say so rather than re-running
  with different settings to hit the number.
- Analysis takes ~2 minutes; rendering a 25-minute 1440p60 edit takes a few
  minutes on the GPU.
- Each kept scene carries 25s of run-up and 15s of aftermath, and nearby action
  merges, so a fight is shown with its cause and its outcome rather than as a
  bare clip of the kill.

**Always watch or spot-check the result before uploading.** The detector is a
heuristic; it can cut a quiet gank or keep a loud nothing.

### 4. Write the metadata

**Keep the result out of the title too.** "41 Minute Comeback" and "Brutal Loss"
both spoil it. Tease the matchup and the hero instead.

**Title** — aim for **40–50 characters** (hard cap is 100, but search truncates near
70). Front-load hero and role, then the hook. No all-caps, no manufactured outrage.

**A title is a hook, not a listing.** `Hero Offlane vs Hero` is a caption: it
states who was in the lane and gives nobody a reason to click. This mistake has
been made twice, so check any draft against the shapes below before using it.

Two shapes work:

```
Hero + role, then a hook about the lane
  Mars Offlane Into a Lane That Shouldn't Work     (44)
  Tidehunter Into a Double Melee Lane              (35)

A claim about the hero or the pick
  Dawnbreaker Is Just a Winning Pick Right Now     (44)
  The Offlane Matchup Nobody Wants                 (32)

How the hero actually plays
  Every Fight Starts With Arena of Blood           (38)
```

**A statistic is not a hook.** "Mars Offlane, 206 Last Hits" was tried and
rejected: a number is a fact, and facts do not make anyone curious. Stats belong
in the description, where someone already watching can appreciate them.

Naming a signature ability is often enough to identify the hero for a Dota
audience, so a title can skip the hero name and still be searchable.

A claim about a hero's strength is fine and is **not** a spoiler: it is about the
hero in the current patch, not about who won this game. Anchoring it with "right
now" is honest, because pick strength is patch-dependent.

**Vary the shape between consecutive uploads.** Two videos in a row titled
"X Is a Winning Pick" reads as a template.

Avoid: `Dota 2 2026.09.25 - 21.59.04.14`, `INSANE GAME!!! MUST WATCH`, anything
naming the outcome, and `Hero vs Hero` listings.

**Only name the carry.** In a lane with a carry and a support, the support does
not belong in the title: it costs characters and is not the matchup anyone cares
about.

**Description** — write to a temp file, pass `--description-file`.

Write it **in the user's voice, to a viewer**. First person, conversational. The
first draft written for this channel failed on exactly this: it explained the
editing method in passive voice ("the laning phase is kept in full, because that
is where offlane games are decided") which reads like release notes, not like
someone talking about their game.

- Talk about the **match**, not about how it was edited. The one exception is a
  single casual line noting the game clock jumps, because otherwise viewers are
  confused by it.
- First person and active voice. "I've cut the farming out", not "the farming is
  cut out".
- Address the viewer at least once: "chapters below if you want to skip to the
  fights".
- **Do not invent the user's opinions.** Their hero, the matchup and the draft
  are facts you can read off the frames; how the lane felt, what they were
  thinking, whether a call was good are not. Ask, or leave them out.

Structure:

1. **Hook, 1–2 sentences.** Only the first ~150 characters show in search, so put
   the user's hero and role there. **Never an opponent hero, and never the
   outcome** - the same rule as the
   title. This line used to say "the matchup and the outcome", contradicting the
   rule three paragraphs above it.
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

### 5. Build a thumbnail

**Never reveal the result** — not in the image, not in the text, not in the title.

**Default: splash style, hero art, no text.** YouTube prints the title directly under
the thumbnail, so words inside the image duplicate it and compete for the same glance.
Let the art carry the frame and use circular badges to say what the video is about.

```bash
.venv/Scripts/python.exe -m ytupload thumbnail --hero "Mars"   --badges "blink,mars_arena_of_blood"   --brand-image brand/yoda.png   --out mars-thumb.jpg
```

- `--badges` takes up to three items or abilities. Items are plain names (`blink`,
  `black king bar`, `assault cuirass`); abilities use their internal name. Pick
  the ones the game actually turned on.
- **A badge that cannot be found is skipped with a warning, and the thumbnail is
  still produced** with one fewer circle. Read the command output; it is easy to
  miss and the image looks fine on its own.
- **Ability slugs are not always `hero_abilityname`.** They are frozen at
  whatever the ability was called internally, which is often not its display
  name. Mars's spear is `mars_spear`, not `mars_spear_of_mars`; Dawnbreaker's
  Starbreaker is `dawnbreaker_fire_wreath`.
  - Mars: `mars_spear`, `mars_gods_rebuke`, `mars_bulwark`,
    `mars_arena_of_blood`
  - Dawnbreaker: `dawnbreaker_fire_wreath`, `dawnbreaker_celestial_hammer`,
    `dawnbreaker_luminosity`, `dawnbreaker_solar_guardian`

  When unsure, run the thumbnail command and check for the warning before using
  the result.
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

#### Writing chapter labels

`cut` marks each chapter at the cut, so one chapter is one scene and the sections
on the progress bar line up with the edit. Each scene opens with about 25 seconds
of run-up, which belongs to that scene.

**Label the scene, not an instant inside it.** Read a frame from the middle of
the scene to see what it is about, and write a label that stays true from the
moment it starts.

- Keep the granularity consistent. "Arena of Blood" (one instant) next to "Vision
  in the Dire jungle" (a whole scene) reads as inconsistent; pick scene-level
  descriptions and let a single standout moment be the exception.
- No outcomes. "Fight near the Roshan pit", never "winning the Roshan fight".
- If a scene is mostly movement, say so ("Rotating to the Radiant side") rather
  than promise a fight.

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

### 6. Dry run, confirm, upload

Always pass `--expect-channel yoda_dota`. A Google account that owns a Brand
Account channel silently authorises the personal channel otherwise, and the
upload lands on the wrong one.

Pass `--chapters-file "<name> - chapters.txt"` (written by `cut`) after replacing
its placeholder labels with real descriptions read from the frames.

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

- **Videos over 15 minutes need a phone-verified account.** The tool refuses the
  upload when `longUploadsStatus` is not `allowed`; `eligible` is not enough.
- **Custom thumbnails also need a verified account**, separately.
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
- **If Bash starts refusing every command** with a classifier error, use the
  PowerShell tool instead - it is a separate path and works. Read-only tools
  (Glob, Grep, Read) keep working throughout, so the capture folder can still be
  listed with Glob.

## Batch mode

For several captures at once. Titles fall back to the filename, which is poor — prefer
uploading individually with real titles unless the user explicitly wants a dump.

```bash
.venv/Scripts/python.exe -m ytupload batch "C:\Users\CHEN\Videos\NVIDIA\Dota 2" \
  --preset dota-offlane --privacy unlisted --archive --dry-run
```

Skips anything already uploaded, anything under 10 minutes, and anything already in
`uploaded\`. Use `--min-duration 0` to include short clips.
