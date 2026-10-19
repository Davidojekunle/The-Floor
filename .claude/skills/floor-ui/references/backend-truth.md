# Backend truth

Verified against `backend/app/` on 2026-10-17. If you change the backend, update this file. If this file and the code disagree, the code wins. Fix this file.

All paths are under `/api/v1`. Every `/rooms/{room_id}/...` route returns `404 NOT_FOUND` unless the caller is an **active** member.

## Endpoints that exist

| Area | Endpoint | Permission |
|---|---|---|
| Auth | `POST /auth/register` → 201 `UserOut` (no token) | public |
| | `POST /auth/login` → `{access_token, token_type, expires_in}` | public |
| | `GET /me` → user + `rooms: RoomSummary[]` | any |
| Rooms | `POST /rooms` `{name}` → 201 `RoomOut` | any |
| | `GET /rooms` → paginated `RoomSummary` | any |
| | `GET /rooms/{id}` → `RoomOut` | member |
| | `POST /rooms/{id}/invite/regenerate` → `{invite_code}` | `invite.manage` |
| Join | `GET /join/{code}` → `JoinPreview` | any |
| | `POST /join/{code}` → 201 `{membership_id, room_id, status}` | any |
| | `GET /rooms/{id}/join-requests` (oldest first) | `join.manage` |
| | `POST /rooms/{id}/join-requests/{mid}/approve` / `reject` | `join.manage` |
| Tags | `GET /rooms/{id}/tags` (limit default 100) | member |
| | `POST`, `PATCH /{tag_id}`, `DELETE /{tag_id}` | `tag.manage` |
| Members | `GET /rooms/{id}/members?tag=` | member |
| | `PATCH /rooms/{id}/members/{mid}` `{tag_ids}` (replaces all) | `tag.manage` |
| | `DELETE /rooms/{id}/members/{mid}` → 204 | `member.remove` |
| Tasks | `GET /rooms/{id}/tasks?from&to&status&assignee&tag&overdue` (limit ≤ 500) | member |
| | `POST /rooms/{id}/tasks` → 201 `TaskDetail` | `task.create` |
| | `GET`, `PATCH`, `DELETE /rooms/{id}/tasks/{task_id}` | GET: member. PATCH/DELETE: `task.create` |
| Stages | `POST /rooms/{id}/tasks/{tid}/stages` → `TaskDetail` | `stage.edit` |
| | `PATCH .../stages/{sid}` (title, tag, assignees, due, parallel, position) → `TaskDetail` | `stage.edit` |
| | `PUT .../stages/{sid}/status` `{status, blocked_reason?}` → `TaskDetail` | participant or `stage.edit` |
| | `DELETE .../stages/{sid}` → `TaskDetail` (409 `LAST_STAGE` if only one) | `stage.edit` |
| Templates | `GET /rooms/{id}/templates`, `GET /{tid}` | member |
| | `POST`, `PATCH /{tid}` (stages replace all), `DELETE /{tid}` | `task.create` |
| | `POST /rooms/{id}/templates/{tid}/apply` `{title, description?, start_date?, due_date}` → 201 `TaskDetail` | `task.create` |

| My work | `GET /me/tasks?scope&actionable&room&from&to&status&overdue&blocked` → `MyTask` items (list item + `room` + `my_stages[]`) | any |

Both task lists also accept `blocked=true`. Phase 2b and Phase 3 both shipped on 2026-10-18, with 310 backend tests passing. The Phase 3 stats endpoint was dropped, and there are no stage-level calendar entries.

**`/me/tasks` rules:**
- `scope`: `mine` (default) or `all`.
- `actionable=true` means one of my stages is todo, in progress or blocked.
- A stage can be both assigned to me *and* carry my tag. `assigned_to_me: false` means I'm in only through the tag.
- Rooms where I'm pending, rejected or removed contribute nothing, and `room=<that id>` returns 404.
- `limit` goes up to 500.

**Due dates (agreed):** a picked day means 23:59:59 that day in the user's **profile** timezone, converted to UTC (26 Oct in Africa/Lagos becomes `…-10-26T22:59:59Z`). The same rule applies to stage due dates. Display uses the viewer's profile timezone.

**Behaviours confirmed by the backend team:**
- Dates without a timezone get 422. Always send UTC with `Z`.
- `assignee=<id>` for a non-member returns an empty list, not an error.
- Re-sending the same status returns 200 without touching `updated_at`.
- Reordering, inserting or deleting stages re-evaluates only locked or todo stages.
- Applying a template copies its stages. Later template edits never change existing tasks.

## Phase 4: proposals (shipped 2026-10-18)

- `POST /rooms/{id}/tasks` by a member (`task.propose` only) → 201 with `approval_status: "pending"`.
- `POST …/tasks/{tid}/approve`, `…/reject` (optional `{reason}`, up to 500 characters), and `…/resubmit`. All return the task and are safe to repeat.
- **Task detail** adds `approved_by, submitted_at, decided_at, decided_by, rejection_reason, can_edit, can_delete, can_resubmit, can_decide`.
- **List items** (room lists and `/me/tasks`) add `created_by, submitted_at, decided_at, rejection_reason`.
- **List filters:**
  - `approval_status` takes several values (`pending,rejected`) and defaults to `approved`. An unknown value gives 422.
  - `sort=submitted_at` sorts oldest first.
  - `/me/tasks?approval_status=pending,rejected` returns **my own** proposals across rooms.
- **Rooms in `/me` and `/rooms`** add `pending_join_requests` and `pending_proposals`, which sum to `pending_count`.
- **Rules:**
  - Another member's proposal is a 404 everywhere.
  - Proposal stages have `allowed_statuses: []`, and status changes give 409 `TASK_NOT_APPROVED`.
  - Rejecting or resubmitting an approved task gives 409 `ALREADY_APPROVED`.
  - The proposer's rights end at approval.
  - Proposals never appear on calendars, in My work, or in `mine_actionable`.

## Phase 5: temporary head (shipped 2026-10-18)

- `PUT /rooms/{id}/members/{membership_id}/temp-head` `{expires_at}` → the updated member. Grant, extend and shorten are all this one call.
- `DELETE …/temp-head` → 204, safe to repeat.
- Head only (`tempHead.manage`). A temp head gets 403, even for themselves.
- **Limits:** the end date must be in the future, and no later than the end of the 90th day after today in the granting head's profile timezone. Otherwise 422 `fields.expires_at`. Targeting the head gives 409 `ALREADY_HEAD`. Inactive or unknown members give 404.
- `MemberOut.temp_head_expires_at` and `RoomSummary.temp_head_expires_at` exist. The members list accepts `role=head|temp_head|member`.
- Several temp heads can exist at once. Whatever they did as temp head stays after the role ends.

## Phase 6a: room chat (shipped 2026-10-18)

- `GET /rooms/{id}/messages?before|after&limit(≤100, default 50)&task_id` → `{items (newest first), has_more, last_read_message_id}`. `after` returns the messages **immediately after** the cursor, so loop while `has_more`. Using both `before` and `after` gives 422.
- `POST /rooms/{id}/messages` `{body (1–4000), task_id?, stage_id?}` → 201 message. A task or stage that's missing, a proposal, or in another room gives 422 `fields.task_id` / `fields.stage_id`.
- `DELETE /rooms/{id}/messages/{mid}` → 204 soft delete (`deleted: true`, body/refs/event null). Safe to repeat. Allowed for your own messages, or anyone's with `chat.delete_any`.
- `POST /rooms/{id}/messages/read` `{up_to?}` → 204.
- **Message:** `id, type (user|system), sender, body, task {id,title}, stage {id,title}, event {type, actor, subject, detail}, created_at, deleted, can_delete`.
- **Rooms in `/me` and `/rooms`:** add `unread_messages`, which excludes your own messages, deleted ones, and messages about your own actions.
- **Pending, rejected or removed members** get 404 on chat. Events from before the chat migration aren't backfilled, so an existing room starts with an empty chat.

## Phase 6b: progress updates (shipped 2026-10-18, migration 0008)

- `GET /rooms/{id}/tasks/{tid}/stages/{sid}/updates?before&limit(≤100, default 20)` → `{items (newest first), has_more}`. Page older with `before=<last id>`; an unknown cursor gives 422 `fields.before`.
- `GET /rooms/{id}/tasks/{tid}/updates?before&limit` → the same page shape for the whole task (all stages).
- `POST …/stages/{sid}/updates` `{note (1–2000, trimmed), link_url? (http/https with a host, ≤2000), share_to_chat?}` → 201 update. A proposal gives 409 `TASK_NOT_APPROVED`. Non-participants without `stage.edit` get 403. A bad link gives 422 `VALIDATION_ERROR` `fields.link_url`.
  - `share_to_chat` also posts a user chat message linked to the task and stage, with body `note` or `note
link`. It's a separate message: deleting the update leaves it.
  - Any stage status can take updates, including locked and done.
- `DELETE …/stages/{sid}/updates/{uid}` → 204. Safe to repeat. Allowed for the author, or anyone with `stage.edit`.
- **UpdateOut:** `id, stage {id,title}, author {id,name}, note, link_url, created_at, can_delete`.
- **StageOut** gains `update_count`. There's **no** `can_post_update` flag: the UI uses `involves_me || can('stage.edit')` on approved tasks, which is the server's own rule.
- Deleting a stage or task deletes its updates.

## Phase 7: live updates over WebSockets (shipped and verified end to end 2026-10-18)

- `ws(s)://<api>/api/v1/ws`, one socket per tab. The first message is `{"type":"auth","token"}`, sent within 10 s. The server replies `{"type":"ready","rooms":[…]}`.
- **Close 4401** means a bad or expired token: the session is over, the same as a REST 401. There are no refresh tokens yet; they're planned straight after phase 7, and then the client refreshes and reconnects.
- **Keep-alive:** the server sends protocol-level pings every 20 s, and browsers answer them themselves. The client sends nothing. An app-level `{"type":"ping"}` → `pong` is optional.
- **Best effort:** nothing is replayed. After every reconnect, refetch what's on screen.
- **Hints only:** every event is `{type, room_id, at, …ids}`.

| type | extra | to | client |
|---|---|---|---|
| message_created | message_id | room members | chat catch-up (`after=`); throttled `/me` |
| message_deleted | message_id | room members | mark deleted locally; throttled `/me` |
| task_changed | task_id | who can see it (proposals: proposer + approvers) | invalidate task, `['tasks', room]`, `me-tasks`; `/me` |
| task_deleted | task_id | who could see it | same as above (the task page refetches and shows "doesn't exist") |
| task_updates_changed | task_id, stage_id | who can see it | invalidate `['updates', room, task]` and the task |
| room_changed | — | members (also on temp-head expiry, within 30 s) | invalidate room, members, tags, join-requests, tasks, me-tasks; `/me` |
| room_access_lost | — | the removed person | invalidate room (→ no-access screen); `/me`; toast |
| room_access_granted | — | the approved person | `/me` (the room appears); toast with the room name |
| join_request_rejected | — | the rejected person | invalidate join-preview; toast |

- Single process (`--workers 1`) until Redis fan-out exists. Sockets hold no DB connection.
- **Client:** `src/live/` (`liveSocket.ts`, `LiveProvider.tsx`, `liveContext.ts`). While the socket is down, the phase 6 polling runs as before.
  - Chat polls every 4 s.
  - `/me` polls every 30 s, every 5 min while the socket is up.
  - Dev proxy: `ws: true`, target `127.0.0.1`.

## Refresh tokens (shipped 2026-10-18, migration 0009)

- **Access token:** 15 min, kept in memory only (`auth/tokenStorage.ts`). **Refresh token:** httpOnly cookie `tr_refresh` with `Path=/api/v1/auth`, `SameSite=Lax`, 30 days since last use, replaced on every refresh.
- `POST /auth/login` (sets the cookie), `POST /auth/refresh` → `{access_token, token_type, expires_in, me}` (`me` = the `GET /me` body), `POST /auth/logout` → 204 (safe to repeat), `POST /auth/logout-all` → 204 (needs the bearer token).
  - **All four need `X-Taskroom-Client: web`** (403 without it) **and `credentials: "include"`**.
- Every refresh failure is 401 UNAUTHENTICATED, and the cookie is cleared. A session ends only when a replaced token is used after its replacement was **also** used. A lost response just cancels the unused replacement. Tabs refreshing within 30 s of each other are fine.
- Auth runs before any route code, so a 401 never wrote anything and retrying is safe.
- **Socket:** send `{"type":"auth","token"}` on the open socket after each refresh → `{"type":"reauthed","expires_at"}`. A different user's or a bad token closes it with 4401. 4401 → refresh → reconnect.
- **Dev:** the app and the API must use the same host name (or a proxy; v2 uses the Vite proxy). `localhost` ↔ `127.0.0.1` is cross-site and the cookie won't be sent.
- **Client:** `auth/session.ts`.
  - One refresh in flight at a time, with a Web Lock across tabs.
  - A BroadcastChannel shares new tokens and sign-outs between tabs.
  - Refreshes 60 s before expiry.
  - A network error or 5xx on page load shows "Can't reach The Floor" (not sign in).

## L4: notifications (shipped 2026-10-18, migration 0012)

- `/me` gains `unread_notifications`, the bell's badge.
- `GET /me/notifications?unread=&before=&limit=` → `{items (newest first), has_more}`.
  - Each item: `id, type, title (ready to show), room {id,name}, task {id,title}, stage {id,title}, actor, data, created_at, read`.
  - `data`: `proposal_rejected` → `{reason}`; `temp_head_granted` → `{expires_at}`; `stages_unassigned` → `{stages: [{task_id, task_title, stage_id, stage_title}]}`.
- `POST /me/notifications/read {up_to?}` (none = all) and `POST /me/notifications/{id}/read`, both → 204.
- `GET` and `PATCH /me/notification-settings`: `email_enabled, requests, decisions, assignments, daily_digest`.
  - `PUT` / `DELETE .../muted-rooms/{room_id}`: muted rooms send no bell items and no emails.
- **Live:** `notification_created {room_id | null, notification_id}`. Unsubscribe is a server-rendered page (`/api/v1/unsubscribe`, GET shows a button and POST acts).
- **Client:**
  - `pages/NotificationsPage.tsx` (`/notifications`): All / Unread, Mark all as read, Show older.
    - Each item is a button: it marks itself read and opens where it's about (task, requests or room). Items about a room that's gone just mark read.
    - Desktop: a sidebar "Notifications" item with a count. Phone: a bell in the top bar.
  - **Email switches:** Account page (`room/useNotificationSettings.ts`, optimistic). "Mute this room": each room's Settings.
  - `components/Switch.tsx` is an accessible `role=switch` row.
  - **Gotcha:** never use `msg` as a modifier class, because `.msg` is the chat message layout. Badges use `is-msg`.

## L3: account (shipped 2026-10-18, migration 0011)

- `/me` gains `theme` (`system` / `light` / `dark`) and `pending_email`.
- `PATCH /me` `{name?, timezone?, theme?}` → the full `/me`. Send only what changes; null isn't allowed.
- `POST /auth/change-password` `{current_password, new_password}` → 200 with a fresh `{access_token, expires_in}`. This browser's session is kept; every other session ends at once.
  - Wrong current password: **401 INVALID_CREDENTIALS** (`fields.current_password`).
  - Same as the current password: 422 `fields.new_password`.
- `POST /auth/change-email` `{new_email, current_password}` → 202. It emails a confirm link (24 h) to the new address and a "this wasn't me" cancel link to the old one.
  - `DELETE /auth/change-email` cancels (signed in).
  - `POST /auth/confirm-email` `{token, current_password}` → 204 (no sign-in needed).
  - `POST /auth/cancel-email-change` `{token}` → 204.
  - Address taken: 409 `fields.new_email`. A bad link: 400 `EMAIL_TOKEN_INVALID`.
- **Live:** `account_changed`, with `room_id: null`, goes to all your tabs.
- All `/auth/*` calls need `X-Taskroom-Client: web` (`session: true` in `apiRequest`). Per-user limit: 5 per hour each.
- **Client gotcha:** a 401 with `INVALID_CREDENTIALS` is a form error. `apiRequest` only refreshes or signs out on other 401s.
- **Client:**
  - `pages/AccountPage.tsx` (`/account`, from "Account settings" in the account menu) has Profile (name, time zone), Appearance (System / Light / Dark: instant, saved, synced live), Email (with a pending banner and cancel), Password, and Sign out everywhere.
  - `pages/EmailPages.tsx` (`/confirm-email` with the password, `/cancel-email-change` with a button only) strips the token from the URL.
  - `lib/theme.ts`, plus an inline script in `index.html`, applies the cached theme before the first paint.

## L2: email, forgotten password, rate limits, immediate sign-out (shipped 2026-10-18)

- **Forgot password:**
  - `POST /auth/forgot-password {email}` → always 202, the same for unknown emails. At most 3 emails per account per hour; extra requests still get 202 and send nothing.
  - `POST /auth/reset-password {token, new_password ≥ 8}` → 204, and every session ends. A bad, used, cancelled or expired link gives 400 `RESET_TOKEN_INVALID`.
  - There's no endpoint to check a link before submitting.
  - Both calls need `X-Taskroom-Client: web`.
  - **Link:** `{Origin if in CORS_ORIGINS, else FRONTEND_URL}/reset-password?token=…`. Dev `.env` now lists the 5174 origins.
- **Email:** `EMAIL_BACKEND=console` prints to the API terminal. Every email is also stored in the `outbox` table (handy in tests).
- **Rate limits:** 429 `RATE_LIMITED` with `Retry-After` (exposed for CORS).
  - Login: 100/min per IP and 5/min per email. Register: 50/h per IP and 3/h per email. Refresh: 300/min per IP and 10/min per session.
  - Live connections: 200/min per IP and 10/min per user; over the limit, the socket closes with 4429.
  - Chat: 30/min per room. Joins: 10/h. Everything else: 300/min per user.
- **Immediate sign-out:** `sessions_valid_after` is set by reset and logout-all. Tokens with `iat` before it get 401 (the comparison is inclusive).
- **Client:**
  - Pages: `pages/PasswordPages.tsx` (`/forgot-password`, `/reset-password`, which strips the token from the URL and sets no-referrer).
  - Sign-in has a "Forgot password?" link and shows a notice after a reset.
  - `ApiError.retryAfter`, with RATE_LIMITED messages like "Try again in N seconds".
  - Refresh waits out a 429 instead of showing "can't reach". The socket backs off about 30 s on 4429.

## L1: room lifecycle (shipped 2026-10-18)

- `POST /rooms/{id}/leave` → 204.
  - Any member except the head: the head gets 409 `HEAD_MUST_TRANSFER`.
  - Membership becomes `left`. Tags, temp head and stage assignments are cleared.
  - A system message (`member_left`) posts.
- `POST /rooms/{id}/transfer-head` `{membership_id}` → the room, with your new role. Needs `head.transfer`.
  - The target's temp-head grant ends.
  - A system message (`head_transferred`; actor = old head, subject = new head) posts.
  - Bad target: 422 `fields.membership_id`.
- `DELETE /rooms/{id}` `{confirm_name}` → 204. Needs `room.delete`. Case and spacing are ignored; a wrong name gives 422 `fields.confirm_name`. Everything in the room is removed.
- **Live:** `room_access_lost` carries `reason` (`removed`, `left`, `room_deleted`).
- **Client:**
  - `room/RoomLifecycle.tsx` holds the dialogs. Settings is open to every member: invite link (by permission), Transfer headship, Leave, Delete. The Members "…" menu has "Make head".
  - `room/roomExits.ts` records why a room went away, so the room page and the sidebar switch at once and toasts say why. A tab's own exits aren't announced twice.

## Endpoints that do NOT exist yet (no UI beyond a "soon" nav item)

notifications outside the app, `PATCH /me` (available on request; password change will come with it), delete room, rename room, leave room, edit profile or timezone, password reset.

## Shapes the UI depends on

**RoomSummary** (`/me.rooms`, `GET /rooms`): `id, name, my_role, pending_count, mine_actionable` (tasks where one of my stages is todo, in progress or blocked). Has **no** `member_count` and **no** temp-head expiry.

**MyStage** (`/me/tasks` → `my_stages[]`): `id, title, status, step, due_date, is_overdue, allowed_statuses, tag, assigned_to_me, blocked_reason`. Status changes still go through the room-scoped `PUT .../status`.

**RoomOut**: `id, name, my_role, temp_head_expires_at, permissions[], member_count, invite_code (null unless invite.manage), created_at`.

**JoinPreview**: `room_name, member_count, already_requested, already_member`. Has no "rejected" flag. A rejected user just sees both flags false and can ask again.

**MemberOut**: `membership_id, user{id,name}, role (effective), status:"active", tags[{id,name}], joined_at`. Has **no** temp-head expiry and **no** email. Sorted head first, then by name.

**TagOut**: `id, name, member_count`.

**TaskListItem** (lists and calendar): `id, title, start_date, due_date, approval_status, status, progress (0–100 int), stages_done, stages_total, current_stage_title, is_overdue, is_blocked, involves_me`.
It has **no** per-stage statuses, assignees, tag, or `created_by`. A per-stage segmented bar can't be drawn from a list response.

**TaskDetail**: everything in the list item, plus `room_id, description, current_stage_ids[], created_by, created_at, updated_at, completed_at, stages[]`.

**StageOut**: `id, title, position, step, parallel_with_previous, status, blocked_reason, unlocked_early, tag, assignees[], due_date, is_overdue, completed_at, completed_by, involves_me, allowed_statuses[], can_update_status, update_count`.

**Task status** (computed): `not_started | in_progress | done`. **Approval**: `pending | approved | rejected`; only `approved` exists until phase 4.

## Stage rules (from `stage_logic.py`)

- A stage with `parallel_with_previous: true` shares a **step** with the stage before it. Stages in a step unlock together. The first stage can't be parallel.
- A stage unlocks (`locked → todo`) when every earlier step is `done`. Unlocking is automatic. The client never does it.
- Transitions that `allowed_statuses` can return:

| From | To | Who |
|---|---|---|
| locked | todo, in_progress | `stage.override_lock` only ("unlock early"; sets `unlocked_early`) |
| todo | in_progress, done | participant or `stage.edit` |
| in_progress | todo, done, blocked (reason required, ≤300 chars) | participant or `stage.edit` |
| blocked | in_progress | participant or `stage.edit` |
| done | in_progress ("reopen") | `stage.override_lock`, and only if no later step has started |

- A **participant** is an assignee, or a member who holds the stage's tag.
- Setting the same status again returns 200 (idempotent).
- A stage due date can't be after the task due date. A task's start can't be after its due date. A task has 1 to 30 stages.
- Progress = done stages ÷ total stages, rounded, as an integer percent.
- `current_stage_title` joins parallel stage titles with ", ".

## Error codes

| HTTP | `code` | When |
|---|---|---|
| 401 | `INVALID_CREDENTIALS` | Wrong email or password on login. Show inline and never redirect. |
| 401 | `UNAUTHENTICATED` | Missing, expired, or invalid token. Clear the session, go to login, and keep the `from` path. |
| 403 | `FORBIDDEN` | No permission. The message says why ("Only a head or temp head can reopen a stage."). |
| 404 | `NOT_FOUND` | Not found, or not an active member. |
| 409 | `CONFLICT` | Duplicate tag or template name, or email already registered (has `fields.email`). |
| 409 | `ALREADY_MEMBER`, `ALREADY_REQUESTED` | Join request. |
| 409 | `REQUEST_NOT_PENDING` | Approving a rejected request, or the reverse. |
| 409 | `MEMBER_NOT_ACTIVE` | Removing someone who isn't active. |
| 409 | `INVALID_TRANSITION` | A stage move that isn't allowed from the current status. |
| 409 | `LATER_STAGES_STARTED` | Reopening a stage after a later step started. |
| 409 | `LAST_STAGE` | Deleting a task's only stage. |
| 422 | `VALIDATION_ERROR` | `fields` keyed by path, e.g. `name`, `stages.1.due_date`, `blocked_reason`. |
| 500 | `SERVER_ERROR` | Generic error with a retry. |

## Session

The JWT lasts 60 minutes (`expires_in: 3600`), and there's no refresh token. Expect mid-session expiry. Keep form drafts in component state and return the user to `from` after logging in again.

## Seed data

`cd backend && python -m scripts.seed` creates a demo room with a head, two members with tags, one pending join request, a "Video shoot" template, and a three-stage task. The password is `password123`.
