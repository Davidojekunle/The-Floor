---
name: floor-ui
description: UI/UX rules, user flows, and design system for The Floor frontend (frontend-v2/src). Use before designing, building, restyling, or reviewing any screen, component, or user flow, and whenever the spec, backend, or mockup might disagree about what the UI should do.
---

> **Where the code lives:** new work goes in `frontend-v2/` (port 5174, proxies `/api` to the backend). The original `frontend/` is kept as-is for the teammate's version; don't edit it unless asked.

# The Floor: UI/UX skill

The Floor is a group task manager built around **rooms**. One user can be head in one room, temp head in another, and a plain member in a third. Work is split into **tasks** made of **stages** that hand off in order.

This skill is the single source of UI truth for the frontend. Before you build or change a screen:

1. Find the flow in [references/flows.md](references/flows.md). Build every state it lists, including empty, loading, error, and no-permission states.
2. Check what the backend actually returns in [references/backend-truth.md](references/backend-truth.md). Never design around a field or endpoint that isn't listed there.
3. Style it with [references/design-system.md](references/design-system.md). Use tokens, never raw colours.
4. Run the contradiction check below and log anything new in [references/contradictions.md](references/contradictions.md).

## Source precedence

When sources disagree, trust them in this order:

1. **Backend code** (`backend/app/`): what the server actually does today.
2. **`/docs` (OpenAPI)** at `http://localhost:8000/docs`.
3. **Backend progress update** (handoff doc): it lags behind the code.
4. **Technical Specification v1**: the product intent. Use it for flows that aren't built yet.
5. **The mockup**: the visual direction, not a data contract.

If 1 and 4 disagree on product behaviour, don't silently pick one. Log it in `contradictions.md` and ask the user.

## Non-negotiable rules

**Permissions**
- Gate every action with `useCan('<permission>')` from the room's `permissions[]`. Never branch on `my_role` for access. Use `my_role` only for display, such as the role badge.
- Hide controls the user can't use. Don't show them disabled. Exception: a feature that's coming soon may appear once in navigation with a "soon" tag.
- For stage status buttons, render only what's in `stage.allowed_statuses`. Never compute stage transitions on the client.
- On a `403`, show the server's `message` in a toast and refetch the room, because permissions may have changed.

**Multi-room**
- The room ID lives in the URL (`/rooms/:roomId/...`) and in every React Query key.
- Clear the whole query cache on logout and on a session-expired 401.
- A `404` on any room resource means "not an active member" (removed, pending, or never joined). Show "You don't have access to this room", refetch `/me`, and offer a link to My rooms.

**Errors**
- Switch on `error.code`, not the HTTP status. Login failure is `INVALID_CREDENTIALS`, which is not a session expiry and must never redirect.
- Map `fields` errors to friendly text per field, falling back to the server text. Field keys can be nested, e.g. `stages.2.due_date`.
- Never show a raw validation message like "String should have at least 8 characters" when a friendlier one is known.

**Confirmations and feedback**
- Confirm destructive actions **inline** (a confirm panel in place), never with `window.confirm`. Destructive actions: remove member, delete tag, delete task, delete stage, regenerate invite, reject.
- Every mutation ends in visible feedback: a toast naming what happened ("Tola joined Studio Alpha"), or an updated row.
- Stage and task mutations return the **full updated task**. Replace the task in the cache from the response instead of refetching.

**Dates**
- The API sends ISO UTC. Display in the user's profile timezone (`/me.timezone`), not the browser's.
- A due date the user picks as a day means the **end of that day in their profile timezone**, converted to UTC before sending. See flows.md → Dates.

**Copy**
- Write from the user's side: "Ask to join", "Let in", "Report a blocker", "Mark done".
- Name the room in messages that cross rooms ("in Studio Alpha").
- Errors say what happened and what to do next. No apologies, no "Oops".

## Contradiction check (run before shipping a screen)

For the screen you're building, answer each question. Every "no" is a contradiction to fix or log.

1. Does every field the design shows exist in the response schema in `backend-truth.md`? Lists especially: `TaskListItem` is much thinner than `TaskDetail`.
2. Does every action map to a real endpoint and a real permission string?
3. Does the copy promise only behaviour the backend has? For example, don't say "they'll be notified" while notifications don't exist.
4. Is every error code that endpoint can return handled with specific copy?
5. Are the screen's states (empty, loading, error, no access, removed mid-session) all designed?
6. Does it match the spec's permission matrix? If the backend is stricter or looser, log it.
7. Does it use only tokens and components from `design-system.md`?

Log each finding in `references/contradictions.md` with a severity (blocker, needs a decision, or cosmetic) and an owner (frontend, backend, or product).

## Build order

The backend now has tasks, stages, and templates, so the build order is:

1. Shared foundation: tokens, base components, the API client using `error.code`, cache clearing on logout.
2. Auth, My rooms, Join via link, Room shell with switcher.
3. Members and tags, Join requests, Settings (invite only).
4. Task list (room overview), Task detail with stage actions, Create task with stage builder, Templates.
5. Wait for the backend before building: proposals (phase 4), temp head grant (phase 5), chat (phase 6), My tasks / My calendar, notifications.
