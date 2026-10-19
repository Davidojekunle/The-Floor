# Design system (v2)

This is plain CSS with custom-property tokens: no Tailwind and no component library. The visual reference is the v2 prototype (https://claude.ai/artifact/3Mj1cbT9jywWVAfmpo7cwo). The first mockup is retired because it was too cluttered.

The code lives in `frontend-v2/src/styles/`:
- `tokens.css`: colours, fonts, radii. This file is the source of truth for values.
- `base.css`: reset and typography.
- `components.css`: shared classes.

Never write a raw hex colour in a component.

## Principles (why the design looks the way it does)

1. **One primary action per view.** Only one accent (blue) button per screen, or per stage row. Everything secondary goes in a "…" menu.
2. **Fewer choices, faster decisions** (Hick's law). The top bar has 2–4 tabs. Features that aren't built are **hidden**, not shown as "soon".
3. **Progressive disclosure.** Show detail on demand. "Needs your attention" appears only when something needs you. Editing, removing and blocking open a focused dialog. Optional form fields (description, parallel stages) stay hidden until asked for.
4. **Colour means state, nothing else.** The page is neutral. Teal = action, amber = blocked or waiting on you, red = overdue or destructive, green = done.
5. **Group related things, separate the rest** (Gestalt proximity). One list per section. Use tabs (People / Tags) instead of side-by-side panels.
6. **Calm layout.** One column, max 840px wide (600px for simple pages), generous vertical rhythm (32px between sections, 40px page top padding).
7. **Recognition over recall.** Locked stages say what they're waiting on. Dialogs restate exactly what will happen ("They'll lose access to Studio Alpha straight away").

## Identity

- **Name:** The Floor. The logo is a dark rounded square with a thin amber and black hazard-tape band along the bottom. It's the only place the tape pattern appears.
- **Font:** Bricolage Grotesque (`--font-display`) for h1/h2; Hanken Grotesk (`--font`, 400–700) for the UI; DM Mono (`--mono`) for dates, counts, "2/3" and invite links. See floor-brand for the scale.
- **Icons:** Phosphor (regular; bold for 12–13px) via `<Icon name>` in `src/components/Icon.tsx`. Never Lucide.
- **Type scale:** h1 26px/600, h2 16px/600, body 14px, meta 13px, labels and eyebrows 12px.

## Semantic colour map

| Meaning | Tokens | Used for |
|---|---|---|
| Action | `--accent`, `--accent-soft` | Primary buttons, focus rings, in-progress stages, links |
| Done | `--ok`, `--ok-soft` | Done stages, finished progress bars |
| Waiting on you / blocked | `--attn`, `--attn-dot`, `--attn-soft` | Pending counts, blocked stages and reasons |
| Late / destructive | `--danger`, `--danger-soft` | Overdue text, delete/remove/decline confirm buttons, form errors |
| Neutral | `--text`, `--text-2`, `--text-3`, `--subtle`, `--border` | Everything else |

Stage status looks the same everywhere (timeline marker, status pill, dot):

| Status | Look |
|---|---|
| locked | dashed grey ring |
| todo | grey ring |
| in_progress | accent ring with a dot |
| blocked | amber with "!" |
| done | green with ✓ |

## Components

| Component | Class | Rules |
|---|---|---|
| Button | `.btn` + `.primary` / `.ghost` / `.danger` / `.danger-outline`, sizes `.sm` / `.block` | Use "Signing in…" while pending and disable to block double submits. |
| Field | `.field` > `label` + `.input` / `.select` / `.textarea` + `.hint` or `.err` | The label sits above. Errors set `aria-invalid` and are linked with `aria-describedby`. |
| List | `.list` > `.row` > `.main` (`.title`, `.meta`) + end slot | Rows at least 60px tall, separated by hairlines. Clickable rows get hover and keyboard focus. |
| "…" menu | `.menu-wrap` > `.icon-btn` + `.menu` | Holds secondary and destructive actions. Destructive items are red and come last, after a divider. |
| Dialog | `.overlay` > `.dialog` | Title states the question. Body says the consequence. Actions sit right: ghost Cancel + one primary or danger button. Esc and backdrop click close it. |
| Segmented control | `.seg` | Filters (All / Involves me / Overdue) and local tabs (People / Tags). |
| Progress bar | `.bar` | Lists show `stages_done/stages_total`. The stage timeline appears only in task detail. |
| Count | `.count` (amber pill) | Only for "people or tasks waiting on you". |
| Toast | `.toast` | Bottom centre, about 2.5s, `role="status"`, one sentence naming what happened. |
| Empty state | `.empty` | A heading, one sentence, and at most one button. |

## Layout v3 (built 2026-10-18)

Code: `components/Shell.tsx`, `components/Sheet.tsx`, `lib/spring.ts`, `styles/shell.css`, `pages/RoomHomePage.tsx`. Phone breakpoint: **760px** (`PHONE_QUERY` in `lib/useMedia.ts`).

- **One shell for every signed-in page** (not the invite page). It fills the viewport (`100dvh`), and the **pane scrolls**, not the page. The pane resets its scroll on navigation.
- **Desktop: a dark sidebar** (dark in both themes) for one room at a time.
  - **Top:** a room switcher (initial, name, role ▾). An amber number counts *other* rooms that need you. Its menu lists your rooms (bold when unread, amber count when waiting on you), then All rooms, New room and Open an invite link.
  - **Pages:** My work, then the room's pages (Home, Chat, Calendar, Members, Requests\*, Templates\*, Settings\*), with counts. \* = by permission.
  - **Bottom:** your account (Sign out, Sign out everywhere) and the collapse button.
  - **Collapse:** a 68px icon strip, toggled by the button or `Ctrl + \`, remembered. Labels become tooltips and counts become dots.
- **Outside a room** (My work, All rooms), the shell keeps showing the **last room** (`lib/lastRoom.ts`).
  - `/` and sign-in open the last room, or the rooms list if there isn't one.
- **Phone:**
  - **Top bar:** translucent, with content scrolling under it. Room switcher on the left, avatar on the right.
  - **Tab bar:** Home · Chat · My work · Calendar · More. More opens a sheet with Members, Requests, Templates, Settings and All rooms. Outside a room: Rooms · My work.
  - **While typing,** the tab bar hides (`:has(:focus)`).
- **Sheets:** on phones, every `Menu` becomes an action sheet (with Cancel) and every `Dialog` becomes a bottom sheet (main action on top, full-width 50px buttons). Pages need no changes.
  - Drag the top down; when the content doesn't scroll, the whole sheet is a handle. It follows the finger 1:1 and rubber-bands past the top.
  - **Release** uses Apple's momentum projection: a flick closes it, a slow drag springs back.
  - **Springs** are critically damped (no bounce), with a little bounce only after an upward flick.
  - Escape and the scrim close it downward. Reduced motion: no slide.
- **Phone ergonomics:**
  - 44px targets.
  - 16px inputs, so iOS doesn't zoom on focus.
  - Press feedback is scale(.97) on `:active`.
  - Safe-area insets (`viewport-fit=cover`), and `interactive-widget=resizes-content`.
  - `prefers-reduced-transparency` and `prefers-contrast: more` make the bars solid.
- **Home:** two columns up to 1240px.
  - **Left:** tasks grouped Overdue / This week / Later / Done (collapsed), with All / Involves me.
  - **Right (320px):** Needs your attention, Your next steps (with stage actions), Your proposals, then Coming up and Recent activity.
  - **Below 1180px:** the first three move above the tasks and the last two go below.
  - **On phones:** the last two are hidden (the groups and the Chat tab cover them).
- **Chat** fills the pane (`.pane-scroll.fill`); only the message list scrolls.
- See also the `apple-design` skill (`.claude/skills/apple-design/`) for motion, sheets and materials.

## Landing page (built 2026-10-18)

Code: `src/landing/` (`LandingPage.tsx`, `StageDemo.tsx`, `useReveal.ts`) and `styles/landing.css`. It's built with the `apple-design` skill.

- **`/` is public:** visitors see the landing page; signed-in users go to their last room.
  - `auth/sessionHint.ts` lets returning users skip a flash of the landing page while the refresh runs, and shows visitors the page at once.
- **Sections:** a translucent sticky bar (its edge appears only once scrolled), a hero with a **working demo** (hand a task along three stages; the progress bar is an interruptible spring, scaleX on the compositor), How it works (3 steps), Features (6), a final call to action, and a footer.
- **Calls to action:** Create your room → `/register`, Sign in → `/login`. "Have an invite link? Open it" reveals a field that goes to `/join/:code` (sign-in first if needed, then back to the invite).
  - The sign-in page logo links back to `/`.
- **Type:**
  - Display text is `clamp(2.5rem, 8.5vw, 4.5rem)`, line-height 1.02, tracking -0.04em.
  - Titles use -0.03em; body text is near 0.
- **Motion:**
  - Sections rise 12px into place once as they scroll into view.
  - The glow behind the hero is static.
  - Reduced motion: nothing moves. Reduced transparency and high contrast: a solid bar.

## Accessibility

- Visible focus ring on everything interactive.
- Status is always text **and** colour.
- Menus use `aria-haspopup` / `aria-expanded`. Dialogs use `role="dialog"` and `aria-modal`.
- Inputs set `autocomplete`.
- Respect `prefers-reduced-motion`.
