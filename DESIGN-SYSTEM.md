# Brighton Weekend design system

This describes the look the app already has and fixes it in one place. The
app is a single file: the source of truth is the token block at the top of the
`<style id="bw-styles">` element in `index.html`. The page
`design-system.html` renders every token and component with a copy of the same
stylesheet, so update it alongside any style change and open it to check.

## Idea

Brighton seafront after dark. The surfaces are the sea at night, in layers of
navy. The accents are the pier lights: coral for anything you can act on, and
teal for anything you have chosen. Everything else stays quiet so that event
titles and the three commitment buttons carry the screen.

## Colour

### Surfaces (darkest to lightest)

| Token | Hex | Use |
|---|---|---|
| `--bw-abyss` | `#08141F` | Page background |
| `--bw-navy` | `#0B1D2F` | Header, bottom nav, text inputs |
| `--bw-deep` | `#0F2231` | Recessed controls (commitment buttons, chips) |
| `--bw-card` | `#102536` | Cards and panels |
| `--bw-raised` | `#173347` | Icon wells, hover state |
| `--bw-line` | `#294657` | Default borders and dividers |
| `--bw-line-strong` | `#3B6074` | Hover and emphasised borders |

### Text

| Token | Hex | Use |
|---|---|---|
| `--bw-cream` | `#F3E4C9` | Primary text |
| `--bw-muted` | `#A7B5BE` | Secondary text: venue, time, notes |
| `--bw-subtle` | `#8095A3` | Tertiary text, inactive nav, empty states |

### Accents

| Token | Hex | Use |
|---|---|---|
| `--bw-coral` | `#FF7767` | Primary buttons, ticket links, active nav tab |
| `--bw-coral-ink` | `#0B1D2F` | Text on coral |
| `--bw-teal` | `#4DB6AC` | Focus ring, checkboxes, selected tiles |

Coral means "do something". Teal means "you picked this". Don't use coral for
selection or teal for actions.

### Commitment states

Each status has one colour family, used for the button, the Happenings pill,
and the person's status label, so people learn it once.

| Status | Foreground | Background | Border |
|---|---|---|---|
| Interested | `#8FE0D5` | `#153B39` | `#397A72` |
| Going (ticket bought) | `#FFD982` | `#40321A` | `#856A29` |
| Not for me | `#FFB5B0` | `#351F24` | `#7A454D` |

All foreground/background pairs meet WCAG AA for small text (measured: Interested 8.0:1, Going 9.2:1, Not for me 9.1:1). Across the palette the lowest pair is `--bw-subtle` on `--bw-navy` at 5.5:1; cream on card is 12.5:1 and text on coral is 6.6:1.

### Secondary tints and shadows

These cover the smaller pieces. With them, every colour in the app's styles
comes from a token, so a new colour scheme only needs a new set of token
values. The one exception is the Google sign-in button, which stays fixed to
Google's branding.

| Token | Value | Use |
|---|---|---|
| `--bw-mist` | `#D9E7E7` | Light text on tags, chips and Happenings names |
| `--bw-tag-bg` / `--bw-tag-line` | `#153443` / `#285365` | Genre tags, social chips |
| `--bw-commit-fg` / `--bw-commit-line` | `#C3D0D6` / `#345468` | Commitment buttons before one is chosen |
| `--bw-happen-bg` / `--bw-happen-line` | `#0F2A31` / `#285A5C` | Happenings add-event panel |
| `--bw-coral-hover` | `#FF8B7D` | Primary button hover |
| `--bw-coral-bg` / `--bw-coral-line` | `#251A1A` / `#71463F` | Coral-tinted wells (Today, events icon) |
| `--bw-coral-wash` | `#1A1719` | New-since-last-visit panel |
| `--bw-coral-glow` | coral at 16% | Halo on a shared event |
| `--bw-sold-bg` / `--bw-sold-line` | `#382022` / `#704047` | Sold out badge |
| `--bw-sticker-joy` / `--bw-sticker-beatdown` / `--bw-sticker-ink` | `#FFE14D` / `#B69CFF` / `#0B1D2F` | Promoter stickers |
| `--bw-shadow-logo`, `-logo-lg`, `-sticker`, `-nav`, `-dialog` | black shadows | Logo, sticker, bottom nav and dialog shadows |

### Light scheme: Seafront by day

People can switch to a light scheme in Settings → Colour scheme. The choice is
saved on the device as `bw_theme` and applied before the page draws, so there
is no flash. The light values live in the `:root[data-theme="light"]` block
straight after the main tokens, and override the same token names; it also
sets `color-scheme: light` so checkboxes and date pickers turn light. Coral
and teal are deeper (`#C9402F`, `#1F7A72`) so they pass contrast on a light
background, and text on coral is white. Any new colour needs a value in both
blocks.

The event pages and This weekend page use `pages.css`, which is written by
`scripts/build-event-pages.py`. It has its own short token names (`--navy`,
`--coral`, `--pass-fg` and so on); change them in the script, not the file.

## Type

One family: **Plus Jakarta Sans** (400–800), falling back to the system UI
font. Headings use tighter letter-spacing (−0.03em); body text uses −0.01em.

| Token | Size | Use |
|---|---|---|
| `--bw-text-xl` | 1.45rem | Tab headings (Comedy, Search, Settings) |
| `--bw-text-lg` | 1.0625rem | Event titles, card headings |
| `--bw-text-md` | 0.9375rem | Body, buttons, inputs |
| `--bw-text-sm` | 0.78rem | Venue and time, notes, day headings |
| `--bw-text-xs` | 0.6875rem | Chips, status labels, nav labels |

Inputs are always 16px so iOS doesn't zoom on focus. Use sentence case
everywhere, including buttons and badges ("Sold out", "Tickets").

## Shape, space, depth

- Radius: `sm` 10px (ticket link), `md` 12px (inputs, tiles), `lg` 16px
  (cards, panels), `xl` 24px (welcome card), `pill` for buttons and chips.
- Spacing steps: 4, 8, 12, 16, 24px (`--bw-space-1` … `--bw-space-5`).
- Shadows: `--bw-shadow-card` under cards, `--bw-shadow-bar` under the header.
  Panels inside cards don't get a shadow.
- Focus: `--bw-focus` (a 3px teal ring) on every interactive element.

## Components

| Component | Classes | Notes |
|---|---|---|
| Button | `.btn` + `.btn-primary` / `.btn-secondary` / `.btn-ghost` / `.btn-chip` | Use one primary per panel. Chip is the small size for row actions. |
| Event card | `.card` › `.top`, `.title`, `.meta`, `.price`, `.people`, `.commitment`, `.actions` | Built by `eventCard()` in `js/app.js`. Discover, Comedy and Search all use it. |
| Commitment control | `.commitment` › `.commit-btn.no/.yes/.bought` (+ `.selected`) | Three equal columns that never wrap. Icons hide below 360px wide. |
| Social chip | `.social-chip` › `.social-icon.heart/.going/.profile` | Counts on cards and names in the group roster. Don't use the class `ticket` here: that's the coral Tickets link. |
| Genre chips | `.genre-chips` › `.genre-chip` (`aria-pressed`, `.untagged`) | Discover filter row and Search pickers. Selected uses the teal "you picked this" colours; Untagged is dashed. Counts in `.n`. |
| Genre tag | `.genre-tag` | Under the venue on an event card, only when the event has a genre. |
| Promoter filter | `.promoter-filter` | Teal bar on Discover after tapping a promoter sticker; "Show all" clears it. |
| Promoter sticker | `.card-flags` › `.promoter-sticker.joy` | Top right of an event card for gigs by a promoter we read (`e.promoter`, mapped in `PROMOTER_STICKERS`). Tilted 6°, square-ish corners, its own colour (JOY. yellow `#FFE14D`, Beat Down violet `#B69CFF`, both with navy text): it is a label, never a button. Sits after "Sold out". |
| Ticket icon | `TICKET_ICON` in the app script (`.ticket-glyph`) | A vector ticket drawn in `currentColor`, used for Going everywhere so it looks the same on every phone. |
| Avatar | `img.avatar` | The artwork file is already a circle; CSS adds exactly one 1px outline (2px teal when selected). No boxes, rings or per-avatar variants. |
| Status pill | `.happening-summary-pill` / `.happening-status` + `.going` / `.interested` / `.pass` | Happenings only. Your own status appears once per event in `.happening-you`. |
| Panel | `.panel`, `.settings-card`, `.settings-section` | Card-coloured container for forms and settings. |
| Segmented control | `.segmented` | Two-way mode switch (Search). |
| Checkbox tile | `.choice`, `.day-choice` in `.choice-grid` / `.day-grid` | Multi-select lists. |
| Day heading | `.day` with a `<span>` for the date | "Friday 25 September". |
| Bottom nav | `.nav` › `button` (`.active`, `.has-new`) | Five tabs; `.has-new` adds a coral dot to Happenings. |

## Rules

1. **Change tokens, not components.** A new colour means a new token in
   `:root`. No hex values in component rules unless they're one-offs, like
   the Google button, which must follow Google's brand.
2. **No `!important`** and no second stylesheet that overrides the first.
   That's how v11–v41 ended up with eight stacked layers.
3. **No inline styles** in HTML or in JS templates. Add a class.
4. **Reuse `eventCard()`** for any new event list, so cards stay identical.
5. **Avatars come from `scripts/standardize-avatars.mjs`.** Add new artwork
   to `profile-icons/`, add the name to `PROFILE_ICONS`, and let the workflow
   build the circular file. Never paint frames into the artwork.
6. **Check `design-system.html`** and a 390px-wide phone view after changes.
