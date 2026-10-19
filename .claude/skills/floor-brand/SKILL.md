---
name: floor-brand
description: The Floor's visual identity and the rules that keep it from looking like generic AI-generated UI ("AI slop"). Use for any change to typography, fonts, colour, spacing, cards, labels, icons, landing/marketing pages, or when the user says the app looks generic, templated, or like AI slop. Works with floor-ui (screens and flows) and apple-design (motion, materials).
---

# The Floor: brand and anti-slop rules

The Floor is where a team hands work along, stage by stage: a shop floor, not a dashboard. It should feel
**made by people who care about type**, calm and confident, closer to a well-set printed schedule or a
station departure board than to a SaaS template.

## Why it looked like AI slop (don't reintroduce these)

| Tell | Instead |
| --- | --- |
| **Geist / Inter everywhere**, one family doing every job | A deliberate pairing (see the chosen direction below): one face with character for display, a workhorse for UI, a mono for figures |
| Every heading the same weight (600) and tracking | A real scale: size, weight **and** tracking change together (apple-design §15) |
| `UPPERCASE TRACKED EYEBROW` labels over every block | Sentence-case labels in the UI face at a smaller size, or nothing. At most one eyebrow per page, never on cards |
| A bordered, rounded card around every group | Use space and hairline rules first. Cards only for things you can pick up (a task, a sheet, a dialog) |
| Teal-on-near-black with a soft radial glow | Colour carries meaning (attention, overdue, done), not decoration. No gradient glows, no blurred blobs |
| Icons in tinted rounded squares next to every line | Icons only where they help scanning; plain glyphs, aligned to the text baseline |
| Generic hero copy ("Every X, Y by Y") and three-feature grids | Show the actual product doing its job; specific copy about stages, heads and hand-offs |
| Numbers in proportional figures, dates as loose text | Tabular figures for counts, progress and dates; a mono for IDs, times and "3/5" |
| Pill badges on everything | Counts as plain numbers where possible; a badge only when something needs the person |

## Typography system

Defined as tokens in `frontend-v2/src/styles/tokens.css`. Components use the tokens, never font names.

- `--font-display`: headings h1 and h2, the landing hero, big numbers. Has character.
- `--font`: the UI workhorse: body, buttons, inputs, lists, chat.
- `--mono`: figures that must line up: times, dates in tables, counts, "2/3", IDs.
- **Scale**, one ratio (about 1.25), in rem, with tracking that tightens as size grows and leading that loosens as it shrinks:

| Token | Size | Weight | Leading | Tracking | Use |
| --- | --- | --- | --- | --- | --- |
| `--t-display` | clamp(2.5rem, 7vw, 4.25rem) | display face | 1.0 | -0.035em | landing hero only |
| `--t-h1` | 1.75rem | display face | 1.1 | -0.025em | page titles |
| `--t-h2` | 1.25rem | display face | 1.2 | -0.015em | section titles |
| `--t-h3` | 1rem | UI 600 | 1.3 | -0.005em | group labels, card titles |
| `--t-body` | 0.9375rem | UI 400 | 1.55 | 0 | body, lists |
| `--t-small` | 0.8125rem | UI 400/500 | 1.45 | 0.005em | meta, hints |
| `--t-micro` | 0.75rem | UI 500 | 1.4 | 0.01em | badges, timestamps |

- **Phone:** same faces; h1 drops to 1.5rem. Inputs stay at 16px (iOS zoom).
- `font-variant-numeric: tabular-nums` on every count, progress, time and date column.
- Load fonts from Google Fonts with `display=swap`, and only the weights in use.

## Colour

- Neutrals carry the UI; the accent is for **actions and "in progress"** only.
- Meaning colours stay: amber = waiting on you, red = overdue, green = done.
- Dark mode is a warm or neutral dark, not blue-black, and never a glowing gradient.

## Layout and detail

- Hierarchy from **type and space** before boxes. Hairline rules (`1px var(--border)`) separate rows; a card
  needs a reason.
- One primary button per view. Secondary actions are quiet (ghost or text).
- Align to a 4px grid; keep spacing values from the existing tokens.
- Copy: plain, specific, sentence case. Name things by what they are ("Your next steps", not "Overview").

## Process for any visual change

1. Read this file and the current tokens.
2. For changes to fonts, colour or the overall look: build a **specimen** first (`frontend-v2/public/type-lab.html`
   style), with the same real UI snippets in each option, and let the user pick. Don't decide taste alone.
3. Apply through tokens; then sweep for the tells in the table above (uppercase eyebrows, card-in-card, glows).
4. Screenshot desktop (1280x800) and phone (390x844), light and dark, and check them before reporting.

## Chosen direction

**Grotesk**, chosen by the user on 2026-10-19 from `frontend-v2/public/type-lab.html`, applied in `tokens.css` and `index.html`.

- `--font-display`: **Bricolage Grotesque** 650, `opsz` 48. h1 1.75rem / -0.03em, h2 1.2rem / -0.02em.
- `--font`: **Hanken Grotesk** 400/500/600/700, body 15px.
- `--mono`: **DM Mono** 400/500, for dates, counts and "2/3".
- **Colour:** neutral greys (no blue cast), **cobalt** accent (#2448c8 light, #8ea3ff dark), and a neutral near-black
  sidebar whose active item is a subtle white tint, not a filled accent.
- **Icons:** Phosphor regular, inlined in `Icon.tsx` (bold for 12–13px). Lucide was ruled out because it's the shadcn default.
- **Counts:** plain numbers in the sidebar and menus, with amber when something is waiting on you. Badges only on the phone tab bar.

Why: the user liked the v2 layout. The generic feel came from Geist everywhere, teal-on-dark, hand-drawn icons and
filled count pills.
