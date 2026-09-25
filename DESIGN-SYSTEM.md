# Brighton Weekend design system

This describes the look the app already has and fixes it in one place. The
source of truth is the token block at the top of `css/app.css`. The page
`design-system.html` shows every token and component rendered with the real
stylesheet, so open it after any style change.

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
| Social chip | `.social-chip` › `.social-icon.heart/.ticket/.profile` | Counts on cards and names in the group roster. |
| Status pill | `.happening-summary-pill` / `.happening-status` + `.going` / `.interested` | Happenings only. |
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
5. **Check `design-system.html`** and a 390px-wide phone view after changes.
