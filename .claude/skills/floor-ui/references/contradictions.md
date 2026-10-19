# Contradictions log

These compare the Technical Specification v1, the Backend Progress Update (handoff), the backend code, the mockup, and the current frontend. The check was first run on 2026-10-17.

**Severity:**
- **Blocker:** the UI can't be built as designed.
- **Decision:** someone must choose.
- **Drift:** a document is out of date; fix the document.
- **Cosmetic:** minor.

Status is **open** until it's resolved. When resolved, note how and when.

## Backend vs the UI design (data the design needs but the API doesn't return)

| # | Contradiction | Severity | Owner | Suggested resolution |
|---|---|---|---|---|
| C1 | The mockup's **"Your stages"** (member home) needs the caller's stages across a room's tasks. The API only has `GET /tasks?assignee=me`, which returns tasks without stages. Building it needs one `GET /tasks/{id}` per task (N+1). | ~~Blocker~~ **Resolved 2026-10-18** | Backend | `GET /me/tasks?room={id}` returns `my_stages[]`. `frontend-v2/src/room/useMyStages.ts` now uses it. |
| C2 | The mockup draws a **segmented pipeline** (one segment per stage) in task lists. `TaskListItem` has only `stages_done/stages_total/progress`. | Decision | Frontend + Backend | Either use a plain progress bar in lists (no backend change), or add `stage_statuses: string[]` to `TaskListItem`. Recommend adding it: it's cheap and is the app's most distinctive visual. |
| C3 | The mockup's task rows say **"Now: Edit · Video Editor"** (current stage plus owner). The list has `current_stage_title` only. | Cosmetic | Frontend | Show the title only in lists, and the owner in detail. |
| C4 | The mockup shows **"Temp head until Oct 24"** on other people's rows in Members. `MemberOut` has no expiry. | Cosmetic | Frontend (or Backend) | Show the badge without a date, or add `temp_head_expires_at` to `MemberOut` (needed anyway for the phase 5 revoke UI). |
| C5 | The mockup lobby cards show **member counts** and **"Temp head until…"**. `RoomSummary` has neither. | Decision | Backend | Add `member_count` and `temp_head_expires_at` to `RoomSummary`, or drop them from the cards. |
| C6 | The mockup overview stat says **"Blocked stages"**. The API gives `is_blocked` per task, not a stage count. | Cosmetic | Frontend | Relabel it "Blocked tasks". |

## Spec vs backend

| # | Contradiction | Severity | Owner | Suggested resolution |
|---|---|---|---|---|
| C7 | Spec decision 8: "**head** can mark stages parallel". The backend lets anyone with `stage.edit` do it (head **and temp head**), which matches the spec's own permission matrix ("Create and edit stages: Head, Temp head"). The spec contradicts itself. | Drift | Product | Treat the matrix as correct and update decision 8. |
| C8 | Spec data model: `Stage.parallel_group` (nullable). The backend uses `parallel_with_previous: bool` plus computed `step`. | Drift | Product | Update the spec. The UI uses "Runs alongside the previous stage". |
| C9 | Spec Task has no `start_date`. The backend has optional `start_date`, so tasks can span days on the calendar. | Drift | Product | Update the spec. The UI shows spans. |
| C10 | Spec API: stage status changes go through `PATCH .../stages/{sid}`. The backend uses `PUT .../tasks/{tid}/stages/{sid}/status`, nested under the task. | Drift | Product | Update the spec. The frontend follows the backend. |
| C11 | Spec "Time: store UTC, display in user's timezone", but nothing defines what a **due date** means (a moment or a day). The backend stores a full datetime. The spec's timezone test priority depends on this. | **Resolved 2026-10-18** | Product + Backend | Agreed with the backend: a picked day is sent as 23:59:59 on that day in the **profile** timezone (from `/me`), converted to UTC. The same rule applies to stage due dates. A future time picker sends the exact instant. Display uses the viewer's profile timezone. Implemented in `frontend-v2/src/lib/dates.ts` (`endOfDayIso`). |
| C12 | The spec says stage "**returns to its previous state** when cleared" from blocked. The backend always returns to `in_progress`. These are equivalent today, because only `in_progress → blocked` is allowed. | Cosmetic | — | No action; note it in case `todo → blocked` is ever added. |
| C13 | The spec doesn't say a reopen is refused once later stages have started. The backend refuses it (`LATER_STAGES_STARTED`). | Drift | Product | Add it to the spec. The UI explains it. |
| C14 | The spec allows a member to **propose** (`task.propose` is in their permissions). `POST /tasks` requires `task.create`, so members get 403. The proposal endpoint doesn't exist yet. | Drift (known, phase 4) | Backend | Until then, the "Propose a task" entry is a "soon" item only. |
| C15 | Spec section 1: rooms have chat and "tasks appear on a calendar". The user's timezone can't be changed after registration (no profile endpoint), so travellers see wrong days. | Decision | Product | The backend offers a small `PATCH /me` whenever we ask. Until then, show the timezone in the user menu. |

## Handoff document vs backend code (the handoff is out of date)

| # | Contradiction | Severity | Owner |
|---|---|---|---|
| C16 | The handoff says phase 2b (tasks, stages, templates) is "Next". It's **built**: routes, schemas, and tests exist. | Drift | Backend: publish an update with task and stage shapes |
| C17 | The handoff says a wrong-password login is `401 UNAUTHENTICATED`. The backend returns `401 INVALID_CREDENTIALS`. The frontend should switch on the code. | Drift | Backend: fix the doc |
| C18 | The handoff's error code list omits `INVALID_CREDENTIALS, ALREADY_MEMBER, ALREADY_REQUESTED, REQUEST_NOT_PENDING, MEMBER_NOT_ACTIVE, INVALID_TRANSITION, LATER_STAGES_STARTED, LAST_STAGE`. | Drift | Backend: fix the doc |
| C19 | The handoff says the seed script "is not built yet". `backend/scripts/seed.py` exists. | Drift | Backend: fix the doc |
| C20 | The handoff lists "deleting a tag un-tags stages" and "removing a member releases stage assignments" as planned. Both are **done** (`tag_service.delete_tag`, `member_service.remove_member`). | Drift | Backend: fix the doc |
| C21 | The handoff says a list `limit` max is 100. Tasks allow up to 500 (for calendar windows). | Drift | Backend: fix the doc |
| C22 | The handoff refers to a **Frontend Handoff v1** (screens 1–13, task shapes). That document hasn't been shared with the frontend work. | Decision | Product: share it or retire it |

## Mockup vs truth (fix in the mockup or the build)

| # | Contradiction | Severity | Resolution |
|---|---|---|---|
| C23 | Mockup Settings shows a **Room name** editor (disabled). There's no endpoint, and the handoff says not to build UI for missing endpoints. | Cosmetic | Remove it from the build. |
| C24 | The mockup's proposal reject toast says "**will see why**". No rejection reason existed in the spec. | Cosmetic | Phase 4 adds an *optional* reason. Copy: "'{title}' was rejected." Add "Tola will see your reason" only when a reason was given. |
| C25 | The mockup's remove-member confirm mentions tags only. The backend also **unassigns them from stages** and **ends any temp-head grant**. | Cosmetic | Use the full copy from flows.md F6. |
| C26 | The mockup lets members click **Start / Mark done** on overview stages. That needs C1 resolved, otherwise only task detail can do it. | Blocker (via C1) | Ship stage actions in task detail first. Add the overview list after C1. |
| C27 | The mockup members **Propose a task** form submits successfully. The endpoint doesn't exist (C14). | Cosmetic | Build it as a "soon" entry. |

## Phase 3 Contract Preview vs the v2 design (proposal, not built)

| # | Contradiction | Severity | Owner | Suggested resolution |
|---|---|---|---|---|
| C33 | The v2 "Your stages" rows say *why* a stage is yours ("Research tag" vs "Assigned to you") and show blocked reasons. Proposed `my_stages[]` has neither `tag`, an assignee flag, nor `blocked_reason`. | **Resolved 2026-10-18** | Backend | All three fields are in `my_stages[]`. |
| C34 | v2 "Needs your attention" lists blocked and overdue tasks **by name**. `task-stats` gives counts only, and the room task list has an `overdue` filter but **no `blocked` filter**. | **Resolved 2026-10-18** | Backend | `blocked=true` exists on both lists. `RoomSummary.mine_actionable` was added too. |
| C35 | A stage status change from My Tasks returns a room-scoped `TaskDetail`, not a `/me/tasks` item. The cache can't be patched from the response. | Cosmetic | Frontend | Invalidate `['me','tasks']` after the mutation. |
| C36 | The contract builds on a "Phase 2b contract, section 11 amendments" that the frontend work hasn't seen. | **Resolved 2026-10-18** | Product | The backend says it matches what we already use: limit 500, per-stage `involves_me`, the first-stage parallel rule, the 409 codes, and the field paths. The full Phase 2b doc is being shared. |
| C37 | Contract examples use due times like `17:00Z`, while C11 was open. | **Resolved 2026-10-18** | — | Settled by C11. |

## Phase 4 (proposals) vs the v2 frontend: shipped 2026-10-18

| # | Contradiction | Severity | Owner | Suggested resolution |
|---|---|---|---|---|
| C38 | Proposers may edit and withdraw their own pending or rejected proposal without `task.create`/`stage.edit`. The UI gates Edit and Delete on room permissions, so it would hide them from proposers. The skill says the server decides and the client never works out rules. | **Resolved** | Backend | `can_edit`, `can_delete`, `can_resubmit`, `can_decide` are on the task detail. `TaskPage`/`EditTaskPage` use only these. |
| C39 | The approvals list should say "Proposed 2 hours ago" and sort by when it was (re)submitted. The list item gets `created_by` but no time, and a resubmit doesn't change `created_at`. | **Resolved** | Backend | `submitted_at` on list items, plus `sort=submitted_at`. A resubmit rejoins the queue. |
| C40 | "My proposals" should show pending **and** rejected together, with the rejection reason. `approval_status` takes one value, and `rejection_reason` is only on the detail. | **Resolved** | Backend | Multi-value `approval_status` on both lists. `rejection_reason` and `decided_at` are on list items. |
| C41 | The Requests tab badge uses `pending_count`, which will now include proposals. | **Resolved** | Frontend | Room home uses `pending_join_requests` and `pending_proposals` separately. The tab badge uses `pending_count` (their sum). |
| C42 | The skill (F13) said the spec has no rejection reason. Phase 4 adds an optional one (up to 500 characters). | Drift | Frontend | F13 updated. Reject dialog has an optional reason field. |

## Phase 5 (temporary head) vs the v2 frontend: shipped 2026-10-18

| # | Contradiction | Severity | Owner | Suggested resolution |
|---|---|---|---|---|
| C43 | The 90-day cap is measured as 90×24h from now, but the agreed day rule sends **23:59:59 on the picked day**. Picking "the day 90 days from today" overshoots by up to 24 hours and gets a 422 for a date the picker offered. | **Resolved** | Backend | The cap is now the end of the 90th day after today in the granting head's profile timezone. The picker offers today + 90. |
| C44 | The room list and switcher can't show "Temp head until Oct 24": `RoomSummary` has no `temp_head_expires_at` (follows on from C5). A temp head only sees their end date inside the room. | **Resolved** | Backend | `RoomSummary.temp_head_expires_at` shipped. The room list and switcher show it. |
| C45 | The remove-member dialog doesn't say that removing a temp head also ends their grant. | **Resolved** | Frontend | Done in `MembersPage`. |
| C4 | (Earlier) other members' temp-head expiry wasn't on `MemberOut`. | **Resolved** | Backend | `temp_head_expires_at` is added to each member. |

## Phase 6 (chat, progress updates) vs the v2 frontend: 6a chat and 6b updates shipped 2026-10-18

| # | Contradiction | Severity | Owner | Suggested resolution |
|---|---|---|---|---|
| C46 | `after=<id>` is "newest first" with a `limit`. If more than `limit` messages arrive between polls, it's unclear whether the page holds the ones **right after** the cursor or the **latest** ones. If it's the latest, the client skips a gap and never knows. | **Resolved (6a)** | Backend | Shipped exactly so: `after` returns the `limit` messages immediately after the cursor. `useChat` loops while `has_more`. The original ask was to define `after` as: the `limit` messages immediately after the cursor (closest to it), ordered newest first, with `has_more` meaning more exist after the newest one returned. The client then repeats `after=<newest returned>` until `has_more` is false, with no gaps. |
| C47 | `POST /messages/read` marks "everything up to now". A message that arrives between our last fetch and the mark call is marked read without being seen. There's also no way to draw a "New messages" line where the user stopped reading. | **Resolved (6a)** | Backend | `POST /messages/read {up_to}` and `MessagePage.last_read_message_id` shipped. The chat marks up to the newest message seen at the bottom. |
| C48 | `event` has an `actor` but no **target**. "Ada made Femi a temporary head" and "Ada approved Kemi's request" (member_joined) involve two people, and `detail` is untyped. | **Resolved (6a)** | Backend | One schema per event type with `actor`, `subject` and a typed `detail`. The UI shows `body` and links the task title. |
| C49 | The task page would benefit from "Messages about this task", but `GET /messages` can't filter by task. | **Resolved (6a)** | Backend | `task_id` filter shipped. A "Messages about this task" view on the task page is possible; not built yet. |
| C51 | `StageOut` has no `can_post_update` flag, unlike every other action. The UI repeats the server's rule (`involves_me` or `stage.edit`, approved task). | Minor | Backend | Add `can_post_update` to `StageOut` so the client doesn't copy a rule. Until then, a 403 is handled by the shared error handler. |
| C50 | Unread counts only come from `/me`. Outside the chat, badges update only when `/me` is fetched. | **Resolved** | Frontend | `AuthProvider` refreshes `/me` every 30s while visible and on focus. |

## Phase 7 (live updates over WebSockets) contract vs the v2 frontend: reviewed, locked and shipped 2026-10-18

| # | Contradiction | Severity | Owner | Suggested resolution |
|---|---|---|---|---|
| C52 | The preview says to close with 4401 when the token expires and "reconnect with a new token". There are no refresh tokens: the access token lasts 60 minutes and the client can't get a new one. | **Resolved** | Backend + Product | 4401 = session over (same as a 401). Refresh tokens come in a small batch after phase 7. |
| C53 | The preview says badges are refreshed through `room_changed` → `/me`. But `pending_count`, `mine_actionable` and `unread_messages` also change on `task_changed` and `message_created`, and `/me` costs 7 queries (about 1.1 s today). | **Resolved** | Backend + Frontend | The backend measured `/me` at about 13 ms with a local DB, so no new endpoint. The client throttles `/me` to once per 2.5 s. Against Supabase (about 120 ms per query) it's slower, but still fine when throttled. |
| C54 | Temp-head grants expire with time, so no request triggers an event. Permissions in the UI stay stale until a 403. | **Resolved** | Backend | The server checks every 30 s and sends `room_changed` for expired grants. |
| C55 | Join requests: the requester isn't a member, so they get nothing when approved or rejected. Decision 5 says events start at once, but nothing tells the client to load the new room. | **Resolved** | Backend | Added `room_access_granted` and `join_request_rejected` (to that person only). |
| C56 | Client ping every 25 s with a 60 s silence limit. Chrome throttles timers in hidden tabs to once a minute after 5 minutes, so background tabs will be dropped and reconnect over and over. | **Resolved** | Backend | Protocol pings from the server every 20 s; no client ping and no app-level silence limit. |
| C57 | "One socket per user": every tab opens its own socket. | **Resolved** | Backend | Several sockets per user are supported. |
| C58 | Section 5 describes the old frontend: v2 has no `useRoomUpdates` and doesn't poll task lists. v2 polls chat every 4 s, the latest chat page every 60 s, and `/me` every 30 s. | **Resolved** | Backend | Section 5 was replaced. |
| C59 | `message_deleted` says "refetch that message's page". There's no endpoint for one message. | **Resolved** | Backend | Mark it deleted locally. |
| C60 | Each socket must not hold a database connection. The pool is 15 and every DB round trip takes about 120 ms; one connection per socket would starve REST at about 15 users. | **Resolved** | Backend | One short session at auth. Events are queued on the session and handed to the hub after commit, thread-safely. |
| C61 | Single process in memory: running uvicorn with more than one worker would quietly lose cross-worker events. | **Resolved** | Backend | `--workers 1` is in the run instructions. |

## Refresh tokens (open item A) vs the v2 frontend: reviewed, amended (doc section 11) and shipped 2026-10-18; client built and browser-tested

| # | Contradiction | Severity | Owner | Suggested resolution |
|---|---|---|---|---|
| C62 | Every 15 minutes the socket is closed with 4401 at token expiry, and the phase 7 rule says to refetch every open screen after each reconnect. That means a full refetch every 15 min in every tab, plus a short window where events are missed. | **Resolved** | Backend | Socket re-auth shipped (`reauthed`). The client re-auths after every refresh. |
| C63 | Reuse detection with only a 30 s grace: if a refresh response is lost (network drop, laptop sleep mid-request), the browser keeps the old cookie. The next refresh more than 30 s later ends the whole session, and a real user is logged out as if their token were stolen. | **Resolved** | Backend + Product | Fixed: a family ends only when the old token is replayed after its replacement was also used. |
| C64 | Section 7 of the phase 7 announcement told everyone to use `127.0.0.1` in `VITE_API_URL`. A frontend opened at `localhost:5173` calling `127.0.0.1:8000` is **cross-site** (different hosts), so a `SameSite=Lax` cookie isn't sent. Refresh would always fail in dev. | **Resolved** | Backend + old frontend | The tip is withdrawn for VITE_API_URL. The README says: same host name, or a proxy. |
| C65 | Page load: the refresh returns only a token, so the client needs `refresh` then `/me` before anything can render: two sequential round trips (about 2 s against Supabase today). | **Resolved** | Backend | The refresh response includes `me`. Page load is one call. |
| C66 | 401 then refresh then retry is only safe if a 401 always means nothing happened. | **Resolved** | Backend | Confirmed and tested by the backend. |
| C67 | Should login also require `X-Taskroom-Client: web`? It sets a cookie, so a forged cross-site login (login CSRF) is possible in principle. | **Resolved** | Backend | Login requires the header too (breaking for the old `frontend/`). |
| C68 | With Web Locks alone, a tab that waited still refreshes again with the new cookie (one extra rotation per tab). | **Resolved** | Frontend | Done in `auth/session.ts`. |
| C69 | Network error or 5xx on refresh (offline, server restart) must not log the user out. Only a 401 ends the session. | **Resolved** | Frontend | Done: the "Can't reach The Floor" screen with retry. |

## Room lifecycle, account, email and notifications (L1 to L4) contract v2 → v3 vs the v2 frontend: v2 reviewed, v3 merged C70–C76 and C79 (C77 and C78 stay with us); v3 reviewed 2026-10-18, not built

| # | Contradiction | Severity | Owner | Suggested resolution |
|---|---|---|---|---|
| C70 | **Email-change takeover by typo.** `confirm-email` needs only the token. If someone types a wrong new address, its owner can click the link, complete the change, then use "forgot password" on their own address and take over the account. The old address is only notified. The response also hands them the full `/me`. | **Resolved (v3)** | Backend | Password at confirm too; confirm returns 204; a cancel link goes to the old address (v3). |
| C71 | **Unsubscribe by GET.** Mail scanners and link previewers (Outlook Safe Links, Gmail proxies) open links automatically, so people get unsubscribed without clicking. | **Resolved (v3)** | Backend | GET shows a confirm button; POST and RFC 8058 one-click (v3). |
| C72 | **"Every other session ends" on password change or reset** revokes refresh tokens, but access tokens stay valid for up to 15 min, and open sockets until expiry. An attacker the user is trying to lock out keeps access meanwhile. | **Resolved (v3)** | Backend | `sessions_valid_after` and sockets closed with 4401; change-password returns a fresh token for this tab (v3). |
| C73 | Events addressed to a user, not a room (`account_changed`, `notification_created`), may have no `room_id`. The v2 socket drops events without one. | **Resolved (v3)** | Frontend + Backend | `room_id` is always present, null for user events (v3). Frontend: accept null. |
| C74 | `room_access_lost` doesn't say why. A deleted room shows "isn't one of your rooms any more", the same as a removal. | **Resolved (v3)** | Backend | `reason`: removed / left / room_deleted (v3). |
| C75 | `muted_rooms` is set by PATCHing the whole list. Two tabs (or a tab and an unsubscribe) muting different rooms overwrite each other. | **Resolved (v3)** | Backend | Per-room PUT/DELETE muted-rooms (v3). |
| C76 | `FRONTEND_URL` is one value, but there are two frontends in dev (5173 old, 5174 v2). Links in emails only open one. | **Resolved (v3)** | Both | Links use the request Origin if it's in CORS_ORIGINS (v3). Add the 5174 origins to CORS_ORIGINS. |
| C77 | Token-in-URL pages (`/reset-password`, `/confirm-email`): the token sits in the address bar and history. | Minor | Frontend | Read the token, then `history.replaceState` to remove it. `<meta name="referrer" content="no-referrer">` on those pages. |
| C78 | `DELETE /rooms/{id}` with a JSON body: allowed, but some proxies and CDNs drop DELETE bodies. | Cosmetic | Backend | Fine with fetch. Consider `POST /rooms/{id}/delete` if it ever goes behind such a proxy. |
| C79 | Leaving releases the leaver's stage assignments, so a stage can end up with no one. Nobody is told. | **Resolved (v3)** | Product | `stages_unassigned` notification to the head (v3). |

### v3 review (2026-10-18)

| # | Contradiction | Severity | Owner | Suggested resolution |
|---|---|---|---|---|
| C80 | **Per-IP limits vs shared networks.** A school, office or mobile network puts many people behind one IP. A class registering together hits "register 5/hour/IP" at the 6th student, and logging in together hits "login 10/min/IP". "Refresh 30/min/IP" and "WS 20/min/IP" are hit when ~30 people open the app around 9:00. | **Blocker for classes** | Backend | Per-IP limits only as a loose flood guard (e.g. register 50/h, login 100/min, refresh 300/min, WS 200/min per IP). Rely on per-email, per-account, per-user and per-refresh-family limits for the real protection. |
| C81 | A 429 on `/auth/refresh` (or a WS 4429) is a normal, temporary state. The v2 client treats a non-401 refresh failure as "unreachable" and shows "Can't reach The Floor". | Major (ours) | Frontend | Wait for `Retry-After`, then retry. Say "Busy, retrying in N s" instead of "can't reach". On WS 4429, back off for at least 30 s. |
| C82 | `Retry-After` isn't readable by cross-origin frontends unless exposed. The old `frontend/` calls the API cross-origin; v2 is same-origin through the proxy. | Minor | Backend | Add `expose_headers=["Retry-After"]` to CORSMiddleware. |
| C83 | `sessions_valid_after` in whole seconds: the comparison must be `iat >= valid_after`, or the fresh token returned by change-password (issued the same second) is rejected. | Minor | Backend | Confirm it's inclusive, and test it. |
| C84 | The "cancel email change" and "confirm email" links open frontend pages. Those pages must not act on load (scanners that run JS). | Minor (ours) | Frontend | Both pages show a button. Confirm also needs the password field. |
| C85 | `backend/.env` `CORS_ORIGINS` has only 5173. With v3's origin-based links, reset emails requested from v2 (5174) fall back to `FRONTEND_URL`. | Setup | Us | Add `http://localhost:5174, http://127.0.0.1:5174` to `CORS_ORIGINS`. |

## Current frontend vs this skill

| # | Contradiction | Severity | Resolution |
|---|---|---|---|
| C28 | `RoomSettingsPage` uses `window.confirm`. The skill requires inline confirms. | Cosmetic | Fix during the rebuild. |
| C29 | `registerPage` always goes to `/rooms` and loses the invite link (`from`). This breaks F3. | Blocker | Navigate to `state.from`. |
| C30 | The API client keys on HTTP status, and logout doesn't clear the React Query cache. | Blocker | Switch on `error.code`, and call `queryClient.clear()` on logout and on 401. |
| C31 | `ProtectedRoute` saves only `location.pathname` as `from`, so query strings are lost. | Cosmetic | Save `pathname + search`. |
| C32 | Approving a join request doesn't refresh the room (`member_count` goes stale). | Cosmetic | Call `refreshRoom()` on success. |
