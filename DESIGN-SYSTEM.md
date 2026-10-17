# Brighton Weekend design system

The source of truth is the token block at the top of `<style id="bw-styles">`
in `index.html`, the app's only stylesheet. `design-system.html` loads that
stylesheet straight from `index.html` when it opens, so it can't drift: it shows
every token in both colour schemes, measures text contrast, and renders each
component below. Open it (from the site or a local web server) after any style
change.

The shareable event pages, This weekend, About, Privacy, Terms and 404 use a
smaller stylesheet, `pages.css` (see [Pages outside the app](#pages-outside-the-app)).

## Idea

Brighton seafront after dark. The surfaces are the sea at night, in layers of
navy. The accents are the pier lights: coral for anything you can act on, and
teal for anything you have chosen. Everything else stays quiet so that event
titles and the three commitment buttons carry the screen.

*Seafront by day* is the same design in daylight: warm sand surfaces, navy
text, and deeper coral and teal so they still read on a light background.

## Colour

Every colour in the app's styles comes from a token, and every colour token has
a value in both schemes. The light values live in `:root[data-theme="light"]`,
straight after the main block, under the same names.

### Surfaces, darkest to lightest (in the dark scheme)

| Token | After dark | By day | Use |
|---|---|---|---|
| `--bw-abyss` | `#08141F` | `#F4EFE6` | Page background |
| `--bw-navy` | `#0B1D2F` | `#FFFFFF` | Header, bottom nav, text inputs |
| `--bw-deep` | `#0F2231` | `#EFE8DC` | Recessed controls: commitment buttons, chips, tiles |
| `--bw-card` | `#102536` | `#FFFFFF` | Cards, panels, dialogs |
| `--bw-raised` | `#173347` | `#E8DFD0` | Icon wells, hover, toasts |
| `--bw-line` | `#294657` | `#D9CFBF` | Borders and dividers |
| `--bw-line-strong` | `#3B6074` | `#B9AC97` | Hover and emphasised borders |

### Text

| Token | After dark | By day | Use |
|---|---|---|---|
| `--bw-cream` | `#F3E4C9` | `#0B1D2F` | Primary text |
| `--bw-muted` | `#A7B5BE` | `#4A5B68` | Secondary text: venue, time, notes |
| `--bw-subtle` | `#8095A3` | `#5F6E79` | Tertiary text, inactive nav, empty states |

### Accents

| Token | After dark | By day | Use |
|---|---|---|---|
| `--bw-coral` | `#FF7767` | `#C9402F` | Primary buttons, Get tickets, active nav tab, This week |
| `--bw-coral-ink` | `#0B1D2F` | `#FFFFFF` | Text on coral |
| `--bw-teal` | `#4DB6AC` | `#1F7A72` | Focus ring, checkboxes, chosen tiles and chips |

Coral means "do something". Teal means "you picked this". Don't use coral for
selection or teal for actions.

### Commitment states

Each status has one colour family, used for its button, the Happenings pill and
the person's status label, so people learn it once.

| Status | Foreground | Background | Border |
|---|---|---|---|
| Interested `--bw-interested-*` | `#8FE0D5` / `#0F5B54` | `#153B39` / `#DCF1EC` | `#397A72` / `#7FC4B9` |
| Going (ticket bought) `--bw-going-*` | `#FFD982` / `#6A4700` | `#40321A` / `#FFF0C4` | `#856A29` / `#D9B24A` |
| Not for me `--bw-pass-*` | `#FFB5B0` / `#8E2B34` | `#351F24` / `#FBE4E3` | `#7A454D` / `#E2A2A6` |

(After dark / By day.) The Interested colours double as the "you picked this"
fill for chosen chips, tabs and the promoter filter bar.

### Secondary tints

| Token | After dark | By day | Use |
|---|---|---|---|
| `--bw-mist` | `#D9E7E7` | `#173347` | Text on tags, chips and Happenings names |
| `--bw-tag-bg` / `--bw-tag-line` | `#153443` / `#285365` | `#E6EEF1` / `#B8CAD2` | Genre tags, social chips |
| `--bw-commit-fg` / `--bw-commit-line` | `#C3D0D6` / `#345468` | `#3B4D5A` / `#C9BEAD` | Commitment buttons before one is chosen |
| `--bw-happen-bg` / `--bw-happen-line` | `#0F2A31` / `#285A5C` | `#E5F2EF` / `#9CCFC5` | Add an event panel on Happenings |
| `--bw-coral-hover` | `#FF8B7D` | `#B23525` | Primary button hover |
| `--bw-coral-bg` / `--bw-coral-line` | `#251A1A` / `#71463F` | `#FBE7E2` / `#E9AFA4` | Coral wells: This week, the events icon, the venue nudge border |
| `--bw-coral-wash` | `#1A1719` | `#FDF1EC` | New since your last visit |
| `--bw-suggest-bg` / `-line` / `-fg` | `#191C38` / `#4A4F8C` / `#C4C8FF` | `#EEEEFB` / `#B7B9E8` / `#3C3F8F` | "You might like" suggestion cards and their Suggested badge |
| `--bw-coral-glow` | coral at 16% | coral at 18% | Halo on a shared event |
| `--bw-sold-bg` / `--bw-sold-line` | `#382022` / `#704047` | `#FBE4E3` / `#E2A2A6` | Sold out badge |
| `--bw-sticker-joy` / `-beatdown` / `-ink` | `#FFE14D` / `#B69CFF` / `#0B1D2F` | same | Promoter stickers |
| `--bw-sticker-dicemeeple` / `-dicemeeple-ink` | `#14275F` / `#C59B22` | same | The Dice & Meeple's sticker, in their own navy and gold |
| `--bw-sparkle` / `-line` / `-glow` | `#FFD982` / `#6E5A2C` / gold at 20% | `#C8961E` / `#E3C46A` / gold at 22% | Sparkle cards: stars, edge and glow (ticket gold) |
| `--bw-scrim` | navy at 62% | same | Behind dialogs |

Shadows are tokens too, softer and navy-tinted by day: `--bw-shadow-card`
(cards), `--bw-shadow-bar` (header), `--bw-shadow-nav` (bottom nav),
`--bw-shadow-dialog` (dialogs, ⋯ menu, welcome cards), `--bw-shadow-logo` and
`-logo-lg` (app logo), `--bw-shadow-sticker` (promoter stickers). Panels inside
cards don't get a shadow.

Two places use fixed colours on purpose, and only these two: the Google sign-in
button (Google's brand), and the swatches on the two Colour scheme choices, which
preview each scheme whichever one is on.

### Choosing the scheme

Settings → Colour scheme saves the choice on the device as `bw_theme` (absent
means after dark). A one-line script in `<head>` applies it before the page
draws, so there is no flash, and sets the browser's theme colour to `#FFFFFF`
by day or `#0B1D2F` after dark. The light block also sets `color-scheme: light`,
so checkboxes and date pickers turn light.

### Contrast

Measured in `design-system.html` (WCAG AA for small text is 4.5:1):

| Pair | After dark | By day |
|---|---|---|
| Primary text on cards | 12.5:1 | 17.1:1 |
| Secondary text on cards | 7.5:1 | 7.0:1 |
| Tertiary text on the nav | 5.5:1 | 5.3:1 |
| Text on coral | 6.6:1 | 4.9:1 |
| Teal on cards | 6.4:1 | 5.1:1 |
| Interested / Going / Not for me | 8.0 / 9.2 / 9.1:1 | 6.7 / 7.4 / 6.8:1 |
| Text on tags | 10.3:1 | 11.2:1 |

The lowest pairs are text on coral and coral on navy by day (4.9:1). A new
colour pair must clear 4.5:1 in both schemes.

## Type

One family: **Plus Jakarta Sans** (400–800, served from `fonts/`), falling back
to the system UI font. Headings use tighter letter-spacing (−0.03em); body text
uses −0.01em.

| Token | Size | Use |
|---|---|---|
| `--bw-text-xl` | 1.45rem | Tab headings (Happenings, Not music, Festivals, Search, Settings) |
| `--bw-text-lg` | 1.0625rem | Event titles, card and dialog headings |
| `--bw-text-md` | 0.9375rem | Body, buttons, inputs |
| `--bw-text-sm` | 0.78rem | Venue and time, notes, day headings, ticket link |
| `--bw-text-xs` | 0.6875rem | Chips, tags, badges, status labels, nav labels |

Apart from icon glyphs, the only other sizes are the wordmark in the header
(1.28rem, 1.14rem on phones) and the welcome headings (1.9rem sign-in, 1.75rem
Welcome back).
Inputs are always at least 16px so iPhones don't zoom on focus.

## Shape, space, depth

- Radius: `--bw-radius-sm` 10px (Get tickets, ⋯ menu items), `-md` 12px
  (inputs, tiles, header buttons, toasts), `-lg` 16px (cards, panels), `-xl`
  24px (welcome cards, dialogs), `-pill` for buttons, chips and tags. Promoter
  stickers keep 4px corners: they're labels.
- Spacing steps: 4, 8, 12, 16, 24px (`--bw-space-1` … `--bw-space-5`).
- Focus: `--bw-focus`, a 3px teal ring, on every interactive element through
  `:focus-visible`.
- Motion: short colour and border transitions (0.15s) and a slight press on
  commitment buttons; all of it is switched off under `prefers-reduced-motion`.

## Layout

- Content sits in `.wrap`: up to 780px wide with a 15px gutter.
- The header is sticky; the week controls in it show only on Discover and Not
  music. The bottom nav is fixed, and `.app-main` leaves room for it
  (`--bw-nav-height`) and the phone's safe areas.
- Built for phones first. Breakpoints: 360px (commitment icons hide, two-up
  grids go to one column), 430px and 600px (tighter header), 520px (day tiles
  go four across).
- Nothing may widen the page past the screen (`overflow-x: clip`), and
  double-tap zoom is off.

## Components

| Component | Classes | Notes |
|---|---|---|
| Button | `.btn` + `.btn-primary` / `.btn-secondary` / `.btn-ghost` / `.btn-chip` / `.btn-danger` | One primary per panel. Chip is the small size for row actions; danger is for removing and deleting. `.google-btn` and `.support-btn` are one-offs. |
| Event card | `.card` › `.top` (`.title`, `.added-by`, `.meta`), `.card-flags`, `.card-tags`, `.people`, `.commitment`, `.actions` | Built by `eventCard(e, {showDate, reason})`. Discover, Not music, Search, the new-events list and You might like all use it. `showDate` adds `.card-date`; `reason` adds `.rec-reason`. Price sits in `.meta`. |
| ⋯ menu | `details.more` › `summary.cal-link`, `.more-pop` › `.more-item` (`.danger`) | Add to calendar, Share, Add a genre, Remove this event. One open at a time; opens upwards near the bottom of the screen. |
| Commitment control | `.commitment` › `.commit-btn.no/.yes/.bought` (+ `.selected`) | Three equal columns that never wrap. Icons hide below 360px wide. |
| Get tickets | `a.ticket` with `TICKET_ICON` | Coral, as wide as the row allows. Taps are counted (`data-ticket-event`). |
| Ticket icon | `TICKET_ICON` (`.ticket-glyph`) | A vector ticket in `currentColor`, used for Going everywhere so it looks the same on every phone. The calendar and share icons are drawn the same way. |
| Listing badge | `.badge.info` | "Free", "Extra show" and similar, from `e.badges`, beside the genre tag. "Sold out" is `.badge.sold` in `.card-flags`. |
| Genre tag | `.genre-tag` | Only when the event has a genre. A genre people added is a `button.genre-tag` they can tap to change. |
| Genre picker | `.genre-picker` › `.pill-wrap` › `.genre-chip` (`aria-pressed`) | Opens in the card from Add a genre. Your pick uses the "you picked this" colours. |
| Sparkle card | `.card.sparkle` › `.sparkles` (three star SVGs) | Cards of a promoter in `SPARKLE_PROMOTERS` (The Dice & Meeple): a ticket-gold edge and glow, and three small stars on the edge that twinkle in turn, one every 1.4s. With reduced motion the stars stay still. |
| Promoter sticker | `.card-flags` › `.promoter-sticker.joy` / `.beatdown` / `.dicemeeple` (with their logo, `.sticker-logo`, from `icons/promoters/the-dice-and-meeple.png`, used with their agreement) | Top right of a card for a promoter we read (`e.promoter`, mapped in `PROMOTER_STICKERS`). Tilted 6°, its own colour, navy text. Tapping it shows only that promoter's gigs on Discover; in Search, or for a promoter whose events are all on Not music (The Dice & Meeple), it opens the Promoter search. |
| Promoter filter bar | `.promoter-filter` › `.promoter-filter-label`, `.btn-chip` | Teal bar on Discover with the count for the chosen days; Show all clears it. |
| Friends line | `.people` › `.social-chip` › `.social-icon.going/.heart/.profile` | Only when friends are interested or going. Also the group roster's name chips. |
| Day heading | `h3.day` with a `<span>` for the date | "Friday 16 October". |
| Quick-time chips | `.range-chips` › `.festival-filter` (`.active`) | Tonight / This weekend / Next 7 days on Discover, where tapping the chosen chip goes back to the week; This weekend / Next 7 days / Next 30 days in Search. |
| Filter chips | `.festival-filters` › `.festival-filter` (`.active`) | Festival types and Not music's event types (Comedy, Theatre & musicals, Board games, Pub quizzes, Pub events, Other), sticky under the header. A long Not music list ends with a `.show-more` button that adds the next page. |
| New since your last visit | `.new-summary`, `.new-list` | One line on Discover until opened. |
| Venue nudge | `.venue-nudge` | Shown instead of listings when no venues are chosen. |
| Empty state | `.empty` | Short and specific: what's missing, and what to try. |
| Happenings card | `.people-card.card` › `.happening-you`, `.happening-summary` › `.happening-summary-pill`, `.happening-group` › `.happening-person` › `.happening-status` | Your own status appears once per event, then friends by group, strongest response first. |
| Group roster | `.group-roster.group-roster-bottom` | People in your groups, at the bottom of Happenings. |
| Add an event | `.custom-event-launch`, `.custom-event-panel` (`.collapsed`) | The teal-tinted panel at the top of Happenings. |
| Festival card | `.card.festival-card` › `.festival-date`, `.festival-location`, `.festival-type` | Built by `festivalCard()`; same commitment buttons and Tickets link as events. |
| Panel | `.panel`, `.settings-card`, `.settings-section` | Card-coloured containers for forms and settings. |
| Segmented control | `.segmented` (`.search-segmented` for four) | The Search modes. |
| Checkbox tiles | `.choice` in `.choice-grid`, `.day-choice` in `.day-grid`, `.venue-row` | Multi-select lists: Search venues, days, Settings venues. |
| Colour scheme choice | `.theme-choices` › `.theme-choice` (`aria-checked`) › `.theme-dots` | Two rows with a three-dot preview each. |
| Avatar | `img.avatar` | The artwork is already a circle (`profile-icons/standardized/`); CSS adds exactly one 1px outline, 2px teal when selected. No boxes, rings or per-avatar variants. `.profile-icon-grid` › `.profile-icon-option` in Settings. |
| Group rows | `.group-manager-row`, `.group-choice`, `.pin-display`, `.member-count` | Settings and the sign-up groups step. |
| Toast | `.bw-toasts` › `.bw-toast` (`.success` / `.error`) | `toast(message, tone)`. Above the bottom nav, gone after a few seconds. Never `alert()`. |
| Dialog | `dialog.bw-dialog` › `.bw-dialog-card` | `dialog({...})` / `confirmDialog({...})`, for questions and copy-a-link; `typeToConfirm` for account deletion. OK comes first in the markup (so Enter means OK) and shows last. Never `confirm()` or `prompt()`. |
| Sign-in and setup | `#welcome` › `.welcome-card` (`#authStep`, `#nameStep`, `#groupStep`) | Full screen over the app. `.checking` hides the card while a saved session is checked, so signed-in people never see it flash. |
| Welcome back | `#home` › `.home-card` › `.home-row` › `.home-icon.events/.plans/.people` | Only when friends have new plans or someone joined a group. |
| Header | `.app-brand`, `.controls` (`#prev`, `#week`, `#next`, `#today`, `#refresh`) | Logo, wordmark and slogan; the week controls below. |
| Bottom nav | `.nav` › `button` (`.active`, `.has-new`) | Six tabs: Happenings, Discover, Not music, Festivals, Search, Settings. `.has-new` adds a coral dot to Happenings. Text glyphs for icons, except the festival tent (`.nav-svg`). |
| Utilities | `.hidden`, `.note`, `.group-meta`, `.nowrap`; `body.guest` with `.member-only` / `.guest-only` | What guests and members see is switched by the class on `body`. |

## Pages outside the app

`pages.css` styles the shareable event pages (`e/<id>/`), This weekend, About,
Privacy, Terms and 404. It is written by `scripts/build-event-pages.py` from
its `STYLE` string, so change it there, not in the file. It is dark only, with
its own short token names taken from the app's dark values (`--navy`, `--card`,
`--cream`, `--coral`, `--teal`, `--pass-fg` and so on), and a few parts:
`.bar` (the header), `.card`, `.pill`, `.facts`, `.actions` with `.btn.go`
(coral) and `.btn.alt` (outline), `.list` (time, title and venue rows),
`.lede`, `.note`, `.meta`, `.notice` and tables. About, Privacy, Terms and 404
are written by hand with the same header and footer as the generated pages.

`admin.html` is a private dashboard with its own small stylesheet.

## Words

- The slogan is **Make the most of yours**.
- Sentence case everywhere, buttons and badges included ("Get tickets",
  "Sold out", "Not for me").
- Few descriptive subheadings: the content and its labels carry the screen.
- Only say what's known. A genre shows when the listing or a confident match
  gives one, never a guess and never "Untagged"; Sold out only when a ticket
  page says so.
- Empty states and errors say what happened and what to do next, in one short
  sentence.

## Rules

1. **Change tokens, not components.** A new colour is a new token in `:root`
   with a value in the light block too. No hex or rgba in component rules,
   apart from the Google button and the scheme swatches.
2. **No `!important`**, except `.hidden` and the reduced-motion switch, and no
   second stylesheet that overrides the first.
3. **No inline styles** in HTML or in JS templates. Add a class. (Only
   `design-system.html` sets colours from script, to paint its swatches.)
4. **Reuse `eventCard()`** for any new list of events, so cards stay identical.
   Festivals use `festivalCard()`.
5. **Avatars come from the scripts.** Add artwork with
   `scripts/add-avatar.mjs` (or the Add avatar workflow) and let
   `scripts/standardize-avatars.mjs` make the circle. Never paint frames into
   the artwork. See `AVATAR_CREATION.md`.
6. **Check `design-system.html`** in both schemes, and the app at 390px wide,
   after a change. Then bump `VERSION` in `sw.js` and the `sw.js?v=` number
   in `index.html`.
