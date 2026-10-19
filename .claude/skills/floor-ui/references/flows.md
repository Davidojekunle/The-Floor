# User flows

Each flow lists who uses it, the steps, the API calls, and every state the UI must handle. **Status** says whether the backend supports it today.

UX principles behind these flows:
- **Show the next action.** Each role opens a room and immediately sees what needs them: the head sees requests and blocked work, a member sees their own stages.
- **Never strand the user.** Every dead end (invalid link, no access, removed, expired session) offers one clear way forward.
- **Keep state visible.** Pending, blocked, locked, and overdue each have a distinct look, and the user never has to infer them.
- **Undo is rare, so confirm in place.** Destructive actions get an inline confirmation that says exactly what will be lost.
- **Server decides, client displays.** Permissions, allowed stage moves, progress, and overdue flags all come from the API.

---

## F1. Sign up, log in, session expiry
**Who:** everyone. **Status:** built.

1. A logged-out user hits any protected URL → redirect to `/login`, keeping `state.from` (path **and** query).
2. Log in → `POST /auth/login` → store the token → `GET /me` → navigate to `from`, or `/rooms`.
3. "Create one" switches to register (name, email, password ≥ 8). Pass `from` through. `POST /auth/register` sends the browser timezone, then logs in automatically, then navigates to `from`.

States:
- Wrong credentials (`INVALID_CREDENTIALS`): inline "Incorrect email or password." Keep the email and clear the password.
- Email taken (409 with `fields.email`): show it under the email field, with a "Log in instead" link.
- Weak password (422 `fields.password`): "Use at least 8 characters."
- Server unreachable (`NETWORK_ERROR`): "Can't reach The Floor. Check your connection and try again."
- **Session expired mid-use** (`UNAUTHENTICATED` on any call): clear the token and query cache, then go to login with `from` = the current path and a banner "Your session ended. Log in to carry on." Keep unsaved form text where possible.

Edge: an already logged-in user who visits `/login` or `/register` is sent to `from` or `/rooms`.

## F2. My rooms (lobby)
**Who:** everyone. **Status:** built.

The data is `GET /me` → `rooms[]` (sorted by name). Each card shows the room name, a role badge, and the `pending_count` badge where it's above 0. Click → `/rooms/:id`.

- **Empty state** (no rooms): show two equal paths, "Start a room" (create form) and "Have an invite link? Paste it here". This is the first screen for every invitee and every new head, so it must not look broken.
- **Create room**: name 1–100 chars, trimmed. `POST /rooms` → refresh `/me` → open the new room on its **Settings → Invite** step, because the head's next job is inviting people.
- **Paste invite link**: accept a full URL or a bare code. Parse the last path segment and navigate to `/join/:code`. This is client-only.

Data gap: cards can't show member counts or temp-head expiry, because `RoomSummary` doesn't include them (see contradictions C5).

## F3. Joining by invite link
**Who:** invitee. **Status:** built.

1. The head copies the link `https://<app>/join/<code>` from Settings and shares it outside the app (WhatsApp, email).
2. The invitee opens it.
   - **Logged out** → login or register → back to `/join/<code>`. Register is the common case here, so it must preserve `from` too.
3. `GET /join/{code}` → a preview card with the room name and member count.
4. The card's state:
   - `already_member` → "You're already in this room", with an **Open room** button.
   - `already_requested` → "Request sent. Waiting for the head to let you in." Don't fetch the room, which would 404.
   - Neither → **Ask to join {room}**. On `POST /join/{code}` 201, switch to the waiting state.
   - 404 → "This invite link doesn't work. It may have been replaced. Ask the room's head for the current link." with **Go to my rooms**.
5. Approval → the room appears in `/me.rooms`. There's no notification yet, so the waiting copy must tell the user to check My rooms later.

Rejection: the invitee isn't told. On their next visit the preview shows "Ask to join" again (both flags false). Don't promise "you'll be notified" anywhere.

## F4. Reviewing join requests
**Who:** `join.manage` (head). **Status:** built.

- Entry points: the badge on the room card, the badge in the rail nav, and a banner on the overview ("3 people are waiting to join").
- List: `GET /rooms/{id}/join-requests` (oldest first, paginated by 20). Each row: avatar, name, "Requested 2 hours ago" (relative, with the exact time on hover), **Reject** and **Let in**.
- Let in → approve → remove the row, then refresh `/me` (badge), the room (`member_count`), and the members list. Toast: "Ifeoma joined Studio Alpha".
- Reject → inline confirm ("Reject Daniel's request? They can ask again with the same link.") → reject → toast.
- `REQUEST_NOT_PENDING` → "Someone already handled this request." Refresh the list.
- If the last item on page 2 or later is removed, step back a page.
- Empty: "No one is waiting. Share the invite link to bring people in." with **Get invite link**.

## F5. Switching rooms
**Who:** anyone in two or more rooms. **Status:** built.

- The switcher sits at the top of the rail, showing the current room name and your role in it. The menu lists all rooms with role and badge, plus **All rooms**.
- Switching navigates to the same sub-page in the new room only if you're allowed there. Otherwise it goes to the overview, e.g. switching from Settings in a head room to a member room.
- Room-scoped UI state (filters, open editors, drafts) resets on switch.

## F6. Members and tags
**Who:** everyone views. `tag.manage` / `member.remove` (head) edits. **Status:** built.

View: `GET /members` with tag filter chips ("Everyone · 6", "Video Editor · 2"). Each row: avatar, name, role badge, tag chips, joined date. Mark your own row "(you)".

Head actions:
- **Edit tags** → inline chip picker for every room tag → **Save** sends `PATCH {tag_ids}` with the full set, and the returned member replaces the row.
- **Remove** (hidden on the head's own row) → inline confirm: "Remove Tola from Studio Alpha? They lose access straight away, their tags are cleared, and they're unassigned from their stages here." → `DELETE` → remove the row and refresh the room's `member_count`.
- **Tags panel**: create (1–50 chars; a case-insensitive duplicate gives 409 → "There's already a tag called Editor"), rename inline, delete with confirm ("Delete 'Sound'? 1 person and 3 stages lose this tag. The stages stay.").

Member view: read-only chips. The tags panel explains what tags are for.

Edge: a member removed while viewing → their next call 404s → F16.

## F7. Invite link management
**Who:** `invite.manage` (head). **Status:** built.

- Settings → Invite: a read-only field with the full URL and a **Copy** button. Copy shows "Copied" for 2 s. If the clipboard fails, select the text and say "Press Ctrl+C to copy".
- **Make a new link** → inline confirm: "The current link stops working immediately. Anyone who hasn't used it yet will need the new one." → `POST /invite/regenerate` → refetch the room → toast.
- Hide Settings entirely when `invite_code` is null. Don't show rename or delete room (no endpoints).

## F8. Creating a task
**Who:** `task.create` (head, temp head). **Status:** built.

Entry: **New task** on the room overview or task list. Two starts:
- **From a template**: pick a template → title, optional description, optional start, required due date → `POST /templates/{tid}/apply`. Stages copy title, tag, and parallel flag but have **no assignees or stage due dates**, so open the new task's detail view right after, with a hint "Assign people to each stage".
- **From scratch**: the task builder.

Task builder:
1. Title (≤ 200), description (≤ 5000, optional), start date (optional), due date (required).
2. Stage list, minimum 1 and maximum 30. Each stage: title (≤ 120), **owner** (a tag, specific people, or both; at least one is recommended but not required), optional due date (must be ≤ task due), and a **"Runs alongside the previous stage"** toggle (disabled on the first stage).
3. A live preview of the pipeline, showing steps and which stages unlock together.
4. **Create task** → `POST /tasks`. Map `fields` like `stages.2.due_date` onto the right stage row and scroll to the first error.
5. On success → task detail, with a toast "Task created. {first step stages} can start now."

The people picker lists active members only (`GET /members`). The tag picker uses `GET /tags`. Show member counts next to tags ("Video Editor · 2 people") so the head knows who a tag-assigned stage reaches. Warn if a tag has 0 people: "No one has this tag yet."

## F9. Working on a stage (the core loop)
**Who:** stage participants (assignee or tag holder); heads and temp heads on any stage. **Status:** built.

Where it happens: task detail (every stage), and "Your stages" on the room overview. See C1: the overview list needs a backend change to do this efficiently, so ship stage actions in task detail first.

Render one button per entry in `stage.allowed_statuses`, labelled by transition:

| From → To | Button | Extra |
|---|---|---|
| todo → in_progress | **Start** (primary) | |
| todo → done | **Mark done** | Secondary; a quick finish for small stages |
| in_progress → done | **Mark done** (primary) | |
| in_progress → blocked | **Report a blocker** | Inline reason field, required, ≤ 300 chars: "What's stopping you?" |
| in_progress → todo | **Move back to To do** | Behind a "More" menu |
| blocked → in_progress | **Clear blocker** | |
| locked → todo / in_progress | **Unlock early** / **Unlock and start** | Overrides only. Confirm: "This skips the wait for {previous step}." |
| done → in_progress | **Reopen** | Overrides only. `LATER_STAGES_STARTED` → "A later stage has already started. Reopen that one first." |

After any change, replace the task with the returned `TaskDetail`. Toasts:
- Done, next step unlocked: "Edit is done. Color grade can start now."
- Done, task finished: "Brand launch video is complete."
- Blocked: "Drafts is marked as blocked. The head can see it on the overview."

Locked stages with no buttons show **why**: "Waiting on Shoot". A stage with `can_update_status: false` that isn't locked gets no buttons and no explanation needed. Don't show a disabled button.

Blocked stages are highlighted wherever they appear (tape styling) and show `blocked_reason`.

## F10. Managing a task's structure
**Who:** `stage.edit` / `task.create` (head, temp head). **Status:** built.

- Edit task: title, description, start date, due date. `PATCH` sends changed fields only; send `null` to clear start or description. Error "Due date can't be earlier than a stage's due date" → highlight the conflicting stage.
- Stage edits from the task detail: rename, change owner (tag/people), due date, parallel toggle, **reorder** (drag or up/down → `PATCH position`), add (`POST`, optional insert position), delete (confirm; `LAST_STAGE` → "A task needs at least one stage").
- Delete task: confirm with the title ("Delete 'Brand launch video' and its 4 stages? This can't be undone.") → back to the list.
- Save as template (client-side composition): `POST /templates` with the current stage titles, tags, and parallel flags.

## F11. Room overview and task list
**Who:** everyone; the content adapts to permissions. **Status:** built (with data gaps).

Order of sections, by who's looking:
- **Has `join.manage`**: join request banner → stats (open tasks, blocked tasks, overdue tasks) → **your stages** if any → all tasks.
- **Has `task.create` but not `join.manage`** (temp head): expiry banner (`temp_head_expires_at`) → your stages → all tasks. The proposals queue arrives in phase 4.
- **Member**: your stages → all tasks (spec: everyone sees every approved task). Stats are personal: stages you can work on, stages waiting on others, due soon.

Task list: `GET /tasks` with filter chips **All / Involves me (`assignee=me`) / Overdue / Done**, plus a tag filter. Rows show title, current stage, a progress bar (`progress`, `stages_done/stages_total`), a due date, and overdue/blocked flags. The list can't draw per-stage segments (C2), so use a plain progress bar in lists and the segmented pipeline only in task detail.

Empty states:
- Head: "No tasks yet. Create the first one, or start from a template."
- Member: "Nothing here yet. Tasks the head creates will show up here."

## F12. Calendar
**Who:** everyone. **Status:** built in `frontend-v2`: the room Calendar tab, and My work → Calendar (`/me/tasks`, "My tasks" or "Everything in my rooms").

- A custom month grid (`components/MonthCalendar.tsx`), not FullCalendar, so it uses the design tokens directly. On phones it shows dots plus a list of the selected day's tasks.
- It queries the visible 6-week grid: `from` = midnight of the first grid day and `to` = midnight after the last, both in the profile timezone, with `limit=500`.
- Each task sits on its due day. `start_date` spans aren't drawn yet. Add them if heads start using start dates.
- Colour by state (overdue, blocked, done) with the same tokens as lists. Click opens task detail.
- Users can't drag to reschedule in v1. If added later, it's a `PATCH due_date` gated by `task.create`.

## F12b. My work
**Who:** everyone. **Status:** built (`/my-work`, the "My work" link in the top bar with the summed `mine_actionable` count).

- **"Ready for you":** todo, in-progress and blocked stages, ordered blocked → in progress → to do, then overdue first, then by due date.
- **"Coming up":** locked stages, each saying "Waiting on {current stage}".
- Each row shows the stage, task, room, "via {tag}" when the stage reaches you through a tag, and the due date. Stage actions work in place, using the room ID from the item.
- After any stage change, refresh `/me` so the "for you" counts update.

## F13. Proposals: member suggests a task
**Status: built (Phase 4 shipped 2026-10-18).** Drive every button from the task's `can_edit` / `can_delete` / `can_resubmit` / `can_decide` flags, never from room roles.

Target flow, per the contract:
- **Member, has `task.propose` but not `task.create`:**
  - Home shows **Propose a task**, which opens the *same* New task form. The page says "The head will review this before anyone sees it", and the button reads **Send for approval**.
  - The response comes back with `approval_status: "pending"`. Toast: "Sent for approval." Then open the proposal's page.
- **Proposal page (proposer):**
  - A status banner: "Waiting for approval", or "Not approved: {rejection_reason}".
  - Edit and **Withdraw** (= delete) while pending or rejected. **Resubmit** when rejected.
  - Stages show no actions, because `allowed_statuses` is empty.
- **"Your proposals"** on room home (member): pending and rejected, each with its status and reason. A My work section across rooms uses `/me/tasks?approval_status=…`.
- **Approvers (`task.approve`):**
  - Home "Needs your attention" shows "2 tasks proposed".
  - The **Requests** tab gets two sections, **People** (join requests) and **Tasks** (proposals, oldest first, "Proposed by Tola · 2 hours ago").
  - The proposal page has **Approve** (primary) and **Reject**, which opens a dialog with an *optional* reason ("Tola will see this").
  - Approvers can edit before approving.
- **Badges:** the Requests tab uses `pending_join_requests` + `pending_proposals`. Don't use `pending_count` alone for "join requests" any more.
- **Errors:** `TASK_NOT_APPROVED` → "This task isn't approved yet." `ALREADY_APPROVED` → "This task was already approved". Refresh after either.
- **Proposals never appear** on calendars, in My work, or in "for you" counts. No notifications exist, so copy never says "they'll be notified".

## F14. Temporary head
**Status: built (Phase 5 shipped 2026-10-18).** `room/TempHeadDialog.tsx` plus the Members page "…" menu.

Target flow, per the contract (`PUT` / `DELETE /rooms/{id}/members/{membership_id}/temp-head`, head only via `tempHead.manage`):
- **Grant** (Members → "…" on a member's row → **Make temporary head**):
  - The dialog says what the role allows and what it doesn't: "Can create, approve and assign tasks. Can't manage joins, tags or members."
  - It offers end-date presets (**1 week**, **2 weeks**, **Pick a date**) plus a date input. A picked day is sent as 23:59:59 that day in the head's profile timezone.
  - Toast: "Femi is a temporary head until Fri, Oct 31."
- **On the row:** a "Temp head · until Oct 31" badge. The "…" menu changes to **Change end date** (same dialog; `PUT` replaces the date) and **End now** (confirm, then `DELETE`).
- **Several temp heads** can exist at once. There's no cap in the UI.
- **The temp head's view:** the "You're a temporary head until …" line on room home already exists. When the grant ends, the next room fetch returns member permissions. A stale button gets a 403, which `useActionError` turns into a toast plus a room refresh.
- **Not shown:** grant history, notifications to the member, or headship transfer.
- **Errors:**
  - 422 `fields.expires_at` goes on the date field ("Pick a date within the next 90 days").
  - 409 `ALREADY_HEAD`: hide the option on the head's own row, so it can't happen.
  - 404: the member left, so refresh the list.
- **Picker limits:** `min` = today, `max` = today + 90 days (the server measures the cap by day).

## F15. Room chat
**Status: built (6a shipped 2026-10-18)**: `pages/ChatPage.tsx` plus `room/useChat.ts`. It currently sits under the top bar, full-bleed. With layout v3 it moves into the sidebar shell unchanged. Polling now, WebSockets in phase 7 with the same shapes.

- **Where:** a **Chat** tab in each room, after Calendar. It shows the unread count (`unread_messages`) like Requests does. The room switcher and room list show unread counts too, and the app polls `/me` every 30 seconds while visible.
- **Layout: Slack's main pane, not a card.** The user rejected a boxed chat inside the page column (2026-10-18) because it felt like a window.
  - The chat fills all the space under the tabs, edge to edge, with no border and no page title. The page never scrolls; only the message list does.
  - A slim channel header holds "# Room name", a one-line description, and a member avatar stack with the count (opens Members).
  - Messages are full-width rows (36px rounded-square avatars, bold name, time). Follow-ups from the same person show their time in the avatar column on hover. Hovering a row tints it and shows a floating action bar at its top-right.
  - Day dividers are a centred pill on a line that sticks to the top while scrolling that day. "New" is a red line with the label on the right.
  - The composer is a rounded box pinned to the bottom, with a tool row inside it (link a task, plus a send button that's active only with text) and a small "Enter to send · Shift + Enter for a new line" hint.
  - A linked task shows as an attachment with a grey left bar and the task title, not a chip.
  - The newest message sits at the bottom, with day separators ("Today", "Yesterday", "Mon, Oct 20").
  - User messages are left-aligned with avatar, name and time. Consecutive messages from the same person within 5 minutes are grouped under one name.
  - **System messages** are one quiet grey line with a small icon ("Femi finished Script on Product promo video"). The task and stage are links.
  - A **"New messages"** line marks where the user stopped reading (needs C47).
- **Composer:** stays at the bottom. Enter sends and Shift+Enter adds a new line, up to 4000 characters, with a counter after 3500. **Link a task** picks an approved task, then optionally one of its stages, and shows "↳ Product promo video · Shoot" above the input, removable. The send button is disabled while the message is empty.
- **Sending:** add the message optimistically, greyed with "Sending…". Replace it with the server's message on 201. On failure show "Not sent · Try again".
- **Polling:**
  - While the Chat tab is open and visible, call `GET /messages?after=<newest id>` every 4 seconds. Repeat while `has_more` is true (C46).
  - Every 60 seconds, refetch the latest page to pick up deletions.
  - Pause while the tab is hidden.
  - Scrolling to the top loads `before=<oldest id>`, keeping the scroll position.
  - Auto-scroll only when the user is already at the bottom. Otherwise show a "↓ N new messages" button.
- **Read:** call `POST /messages/read` when the chat opens and again after new messages arrive while it's visible. Then refresh `/me` so badges clear.
- **Delete:** in the "…" menu on hover (always visible on touch), only when `can_delete`. It asks for confirmation, then the message shows *Message deleted* in place.
- **Errors:** 404 means lost access (F16). 422 with `fields.task_id`/`stage_id` means the linked task was deleted or isn't visible; drop the link and say so.
- **Empty state:** "No messages yet. Say hello, or share an update on a task." Activity appears here automatically.

## F15b. Progress updates on stages
**Status: built (`room/StageUpdates.tsx`). Shared updates show in chat with their link clickable.**

- **On the task page:** each stage shows "3 updates" (`update_count`) as a link that expands the stage's updates inline: newest first, author, time, note and an optional link.
- **Posting:** participants (or `stage.edit`) see **Post an update** under the stage's actions. It opens a small form: note (1 to 2000 characters), an optional link (`https://…`, checked before sending), and a checkbox **Also post to room chat** (`share_to_chat`).
- **Task feed:** a task-wide **Updates** section at the bottom of the task page (`GET …/updates`), with "Load more".
- **Delete:** the author or `stage.edit` deletes from the update's "…" menu after a confirmation. The update disappears.
- **Proposals:** no updates, so hide the button (the API returns 409 `TASK_NOT_APPROVED`).
- **Links** open in a new tab with `rel="noopener noreferrer"`. Show the domain, not the full URL.

## F16. Losing access or permissions mid-session
**Status:** built (backend behaviour).
- **Removed from a room** → any room call 404s → full-page state "You no longer have access to {room name if cached}" → refetch `/me` → **Go to my rooms**.
- **Permissions shrank** (temp head expired) → a 403 on an action → toast the server message, refetch the room, and the nav and buttons update.
- **Room switcher contains a stale room** → selecting it 404s → same as removal.

## Dates (applies to F8, F10, F11, F12)

- Users pick **days**, not times, for due dates. Convert "Oct 24" to **23:59:59 on Oct 24 in the user's profile timezone**, then to UTC.
- Display every date in the profile timezone (`/me.timezone`), formatted relatively when close: "Due today", "Due tomorrow", "Due Fri, Oct 24", "3 days overdue".
- This convention was **agreed with the backend on 2026-10-18** and applies to stage due dates too. Spec test priority 5 (tasks near midnight land on the right day) depends on it. It's implemented in `frontend-v2/src/lib/dates.ts`.
