# The Floor: backend

FastAPI + PostgreSQL. Interactive API docs at `/docs` once it's running.

## First run

```bash
docker compose up -d                 # PostgreSQL (from the repo root)
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                 # then set SECRET_KEY, see below
alembic upgrade head
python -m scripts.seed               # demo room, logins printed at the end
```

`SECRET_KEY` must be at least 32 bytes. Generate one with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

On Windows, use `127.0.0.1` instead of `localhost` in `DATABASE_URL` only.
`localhost` often tries IPv6 first and waits about a second before falling back.

**Keep the frontend and API on the same host name** (both `localhost` in dev). The
session cookie is `SameSite=Lax`, so `localhost:5173` calling `127.0.0.1:8000`
counts as cross-site and the browser won't send it. In production, serve both under
one domain (for example `app.` and `api.` of the same name), or proxy the API at `/api`.

## Sessions

Login returns a 15-minute access token and sets an httpOnly `tr_refresh` cookie
(30 days, renewed on each use). `POST /api/v1/auth/refresh` gives a new access token.
The auth calls need `credentials: "include"` and the header `X-Taskroom-Client: web`.
Set `REFRESH_COOKIE_SECURE=false` for plain-http local dev, and `true` in production.

## Email

Emails (password reset, and later notifications) are written to an outbox table in
the same transaction as the change, then sent by a background loop every 5 seconds,
with 3 tries. With `EMAIL_BACKEND=console` (the default) they're printed to the
server log instead, which is where you'll find reset links in dev. For real sending,
set `EMAIL_BACKEND=smtp` and the `SMTP_*` settings (any provider: Gmail app
password, Brevo, Resend, Mailgun...).

## Account

`PATCH /api/v1/me` changes name, timezone and theme. Changing the password ends every
other session at once; changing the email needs the password twice (at request and
when confirming the link sent to the new address), and the old address gets a
"this wasn't me" cancel link. In dev, all of those links appear in the server log.

## Notifications

Every notification lands in the bell at once. Emails for them are grouped: the first
one opens a 2-minute window, and everything for the same person and category in that
window goes out as one email (skipping anything already read in the bell). The daily
digest goes out at 08:00 in each person's timezone, only when there's something in it.
All of this runs in the same background loop as the email sender, so it also needs
`EMAIL_SENDER_ENABLED=true` (the default) and one worker. Notifications are kept 90 days.

## Rate limits

Counted in memory, so they reset on restart and assume one process (see below).
Per-IP limits are deliberately loose because a whole office or campus can share one
address. Tight limits are per email address or per user. Behind a proxy, set
`TRUSTED_PROXIES` or every client looks like the proxy. Set `RATE_LIMIT_ENABLED=false`
to switch them off locally.

## Running the server

```bash
uvicorn app.main:app --reload --workers 1
```

**Run exactly one worker.** Live updates (`/api/v1/ws`) are fanned out in memory,
so every connected socket must live in the same process as the request that made
the change. More workers need Redis pub/sub first (not built yet).

The server sends WebSocket protocol pings every 20 seconds (uvicorn's default,
`--ws-ping-interval 20 --ws-ping-timeout 20`). Browsers answer them automatically,
even in background tabs, so clients don't need to ping.

## Tests

```bash
python -m pytest -q                  # in-memory SQLite, fast
TEST_DATABASE_URL=postgresql+psycopg://taskroom:taskroom@localhost:5432/taskroom_test python -m pytest -q
```

The Postgres run needs an empty `taskroom_test` database. It also runs a check that a
connected WebSocket holds no database connection, which SQLite has to skip.

## Resetting

```bash
alembic downgrade base && alembic upgrade head && python -m scripts.seed
```
