# Adding a new avatar

## The rule

**Selection is approval.** When the user picks an image, that exact file is the
avatar's artwork. Don't redraw it, replace it with an SVG, make a placeholder or
regenerate a "similar" version. The scripts record its SHA-256 fingerprint, and
validation fails if the artwork changes afterwards.

## House style

- One friendly, painterly subject (an animal, plant, creature or object),
  front-on and centred, filling most of the frame.
- Bold, saturated colours on a plain dark navy background. The circle is filled
  with the artwork's own edge colour, so a plain dark background gives a clean
  result.
- Square: ideally 1024×1024, at least 512×512 (192×192 is the hard minimum).
  PNG, JPG or WebP.
- No text, border or ring: the app draws the outline.
- Original artwork only: no recognisable characters, mascots or logos.

The standardise step keeps the central 86% of the image and shows it at 88% of
the circle, so leave some background around the subject.

## Choosing an id and label

- **id**: lowercase words joined by hyphens, e.g. `red-fox`. It must not already
  be in `PROFILE_ICONS` (index.html) or used by a file in `profile-icons/`.
  `bee` and `bumblebee` are retired.
- **label**: the name shown in the app, e.g. `Red Fox`. Letters, numbers,
  spaces, `&`, `(`, `)` and `-` only, up to 40 characters.

## Option A: on GitHub (no tools needed)

1. Upload the artwork to `profile-icons/` on `main`. Any file name works.
2. Go to **Actions → Add avatar → Run workflow**, and enter the id, label and
   the uploaded file's name.

The run stores the artwork as `profile-icons/<id>.<ext>`, registers it, makes
the standard 192px circle in `profile-icons/standardized/`, validates every
avatar and commits to `main`. GitHub Pages publishes it about a minute later.

## Option B: from a clone (or with Claude)

```sh
cp ~/Downloads/fox-final.png profile-icons/
node scripts/add-avatar.mjs --id=red-fox --label="Red Fox" --file=fox-final.png
npm install --no-save sharp
node scripts/standardize-avatars.mjs
node scripts/validate-avatars.mjs
```

Look at `profile-icons/standardized/<id>.png` before committing. If the crop
cuts the subject off, choose different artwork rather than editing it. Then
commit `index.html` and `profile-icons/` on a branch and open a pull request.

## What the scripts do

| Script | Job |
|---|---|
| `add-avatar.mjs` | Checks the id, label, file type and size; stores the artwork as `profile-icons/<id>.<ext>` (same bytes); adds the avatar to `PROFILE_ICONS`, `PROFILE_LABELS` and `PROFILE_ICON_FILES` in index.html and to `avatar-manifest.json`. Changes nothing if a check fails. |
| `standardize-avatars.mjs` | Makes `profile-icons/standardized/<id>.png` (192px, circular, transparent outside) for every avatar and points the app at those files. The manifest keeps `source` and `source_sha256` (the selected artwork) and `file` and `sha256` (what the app shows). |
| `validate-avatars.mjs` | Fails if any avatar's file is missing or either fingerprint has changed. |

## Database

Nothing to do. Since `supabase/v60-avatar-ids.sql`, the database accepts any
well-formed avatar id, and the app's own list decides which avatars exist.
