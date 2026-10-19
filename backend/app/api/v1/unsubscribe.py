"""Unsubscribe links in emails. Scanner-safe: opening the link (GET) changes nothing; only a POST does.

Mail apps' own unsubscribe buttons POST here directly (RFC 8058 one-click), using the
List-Unsubscribe and List-Unsubscribe-Post headers on every notification email.
These are pages for browsers and mail apps, not part of the frontend's API, so they're left out of OpenAPI.
"""
import html
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.services import notification_email
from app.services import notification_service as notes

router = APIRouter()
TOKEN = Annotated[str, Query(max_length=1000, description="From the email's link")]


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        status_code=status,
        content=(
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="color-scheme" content="light dark"><meta name="robots" content="noindex">'
            f"<title>{html.escape(title)} · Taskroom</title>"
            "<style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.5;"
            "max-width:480px;margin:10vh auto;padding:0 16px}button{font:inherit;padding:10px 18px;border:0;"
            "border-radius:6px;background:#2f5bd3;color:#fff;font-weight:600;cursor:pointer}</style></head>"
            f"<body><h1>{html.escape(title)}</h1>{body}</body></html>"
        ),
    )


def _bad_link() -> HTMLResponse:
    return _page("This link doesn't work", "<p>It may have been copied incompletely. You can change which emails "
                 "you get in Taskroom, under notification settings.</p>", status=400)


@router.get("/unsubscribe", response_class=HTMLResponse, include_in_schema=False)
def unsubscribe_page(token: TOKEN, db: Session = Depends(get_db)):
    """Shows what will be turned off, with a confirm button. Changes nothing by itself."""
    parsed = notification_email.read_unsubscribe_token(token)
    if parsed is None or db.get(User, parsed[0]) is None:
        return _bad_link()
    label = notification_email.LABEL[parsed[1]]
    return _page(
        "Turn off these emails?",
        f"<p>You'll stop getting emails for <strong>{html.escape(label)}</strong>. The bell in Taskroom keeps "
        "working, and security emails (like password changes) always arrive.</p>"
        f'<form method="post" action="?token={html.escape(token)}"><button type="submit">Turn them off</button></form>',
    )


@router.post("/unsubscribe", response_class=HTMLResponse, include_in_schema=False)
def unsubscribe(token: TOKEN, db: Session = Depends(get_db)):
    """Turns that category off. Used by the page's button and by mail apps (RFC 8058). Safe to repeat."""
    parsed = notification_email.read_unsubscribe_token(token)
    user = db.get(User, parsed[0]) if parsed else None
    if user is None:
        return _bad_link()
    notes.update_settings(db, user, {parsed[1]: False})
    label = notification_email.LABEL[parsed[1]]
    return _page("Done", f"<p>You won't get emails for {html.escape(label)} any more. "
                 "You can turn them back on in Taskroom, under notification settings.</p>")
