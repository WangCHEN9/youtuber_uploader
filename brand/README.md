# Channel brand assets

Put the channel mascot here as `yoda.png` — a photo of the cat the channel is
named after.

```bash
python -m ytupload thumbnail --hero "Mars" --badges "blink" --brand-image brand/yoda.png
```

It is rendered as a circular mark in the bottom-right corner of every thumbnail,
diagonally opposite the ability badges.

## What makes a good mascot image

- **Square-ish framing.** It is cover-cropped to a circle, so anything far from
  the centre is lost.
- **The face filling most of the frame.** At 17% of the thumbnail height it is
  roughly 120px on screen, and smaller again in a sidebar.
- **Good separation from the background.** A busy background turns to mush at
  that size.

A transparent PNG is not required here: the mark is masked to a circle anyway.
