#!/bin/sh
# Production entrypoint (see ../Dockerfile): migrate, then run ONE uvicorn worker.
# One worker on purpose: live updates and the email sender run inside this process.
set -e

# Render sets RENDER_EXTERNAL_URL (https://<name>.onrender.com). Site and API share it, so the
# URL settings default to it; set any of them explicitly (e.g. for a custom domain) to override.
if [ -n "$RENDER_EXTERNAL_URL" ]; then
  : "${FRONTEND_URL:=$RENDER_EXTERNAL_URL}"
  : "${PUBLIC_API_URL:=$RENDER_EXTERNAL_URL}"
  : "${CORS_ORIGINS:=$RENDER_EXTERNAL_URL}"
  : "${VAPID_SUBJECT:=$RENDER_EXTERNAL_URL}" # push services (Apple's especially) want a real contact URL
  export FRONTEND_URL PUBLIC_API_URL CORS_ORIGINS VAPID_SUBJECT
fi

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
