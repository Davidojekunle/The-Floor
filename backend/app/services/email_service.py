"""Outbox-based email: queue in the request's commit, send from a background loop."""
import asyncio
import html
import logging
import smtplib
from datetime import timedelta
from email.message import EmailMessage

import httpx
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.models.email import OutboxEmail
from app.utils.time import as_utc, utcnow

logger = logging.getLogger("taskroom.email")

MAX_ATTEMPTS = 3
BACKOFF = (timedelta(seconds=30), timedelta(minutes=2), timedelta(minutes=10))


# ------------------------------------------------------------------ building

def link_base(request: Request | None) -> str:
    """For emails caused by a request: its Origin if allowed by CORS, otherwise FRONTEND_URL."""
    settings = get_settings()
    origin = request.headers.get("origin") if request is not None else None
    if origin and origin in settings.cors_origins_list:
        return origin.rstrip("/")
    return settings.frontend_url.rstrip("/")


def render(title: str, paragraphs: list[str], button: tuple[str, str] | None = None, footer: str | None = None,
           footer_link: tuple[str, str] | None = None):
    """(text, html). Plain layout that reads well in light and dark mail apps."""
    text = [title, "", *paragraphs]
    if button:
        text += ["", f"{button[0]}: {button[1]}"]
    if footer:
        text += ["", footer]
    if footer_link:
        text += [f"{footer_link[0]}: {footer_link[1]}"]

    esc = html.escape
    body = "".join(f'<p style="margin:0 0 16px">{esc(p)}</p>' for p in paragraphs)
    if button:
        body += (
            f'<p style="margin:24px 0"><a href="{esc(button[1])}" '
            'style="display:inline-block;padding:10px 18px;border-radius:6px;background:#2f5bd3;'
            f'color:#ffffff;text-decoration:none;font-weight:600">{esc(button[0])}</a></p>'
            f'<p style="margin:0 0 16px;font-size:13px">Or open this link: {esc(button[1])}</p>'
        )
    if footer or footer_link:
        link = (f' <a href="{esc(footer_link[1])}" style="color:inherit">{esc(footer_link[0])}</a>'
                if footer_link else "")
        body += f'<p style="margin:24px 0 0;font-size:12px;opacity:.75">{esc(footer or "")}{link}</p>'
    page = (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">'
        f'</head><body style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.5;'
        f'max-width:560px;margin:0 auto;padding:24px"><h1 style="font-size:20px;margin:0 0 16px">{esc(title)}</h1>'
        f"{body}</body></html>"
    )
    return "\n".join(text), page


def queue(db: Session, *, to: str, subject: str, text: str, html_body: str, category: str,
          user_id=None, headers: dict | None = None, send_after=None) -> OutboxEmail:
    """Adds to the caller's transaction. Nothing is sent unless that transaction commits."""
    now = utcnow()
    row = OutboxEmail(
        to_address=to, subject=subject, text_body=text, html_body=html_body, category=category,
        user_id=user_id, headers=headers, created_at=now, next_attempt_at=send_after or now,
    )
    db.add(row)
    return row


# ------------------------------------------------------------------ sending

class ConsoleBackend:
    def send(self, email: OutboxEmail) -> None:
        logger.warning("\n----- EMAIL (console backend) -----\nTo: %s\nSubject: %s\n\n%s\n-----------------------------------",
                       email.to_address, email.subject, email.text_body)


class SmtpBackend:
    def send(self, email: OutboxEmail) -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = s.email_from, email.to_address, email.subject
        for name, value in (email.headers or {}).items():
            msg[name] = value
        msg.set_content(email.text_body)
        msg.add_alternative(email.html_body, subtype="html")
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password)
            smtp.send_message(msg)


class ResendBackend:
    """Resend's HTTP API. Goes out over HTTPS, so it works on hosts that block SMTP ports (Render's free tier)."""
    URL = "https://api.resend.com/emails"

    def send(self, email: OutboxEmail) -> None:
        s = get_settings()
        payload = {"from": s.email_from, "to": [email.to_address], "subject": email.subject,
                   "text": email.text_body, "html": email.html_body}
        if email.headers:
            payload["headers"] = email.headers
        r = httpx.post(self.URL, json=payload, timeout=20,
                       headers={"Authorization": f"Bearer {s.resend_api_key}", "Idempotency-Key": f"outbox-{email.id}"})
        if r.status_code >= 400:  # Resend says why (unverified domain, bad key...) in the body
            raise RuntimeError(f"Resend {r.status_code}: {r.text[:300]}")


def backend():
    kind = get_settings().email_backend
    if kind == "resend":
        return ResendBackend()
    return SmtpBackend() if kind == "smtp" else ConsoleBackend()


def deliver_pending(db: Session, limit: int = 50) -> int:
    """Send what's due. Returns how many were sent. Failures back off, and give up after 3 attempts."""
    now = utcnow()
    due = list(
        db.scalars(
            select(OutboxEmail)
            .where(OutboxEmail.sent_at.is_(None), OutboxEmail.failed_at.is_(None), OutboxEmail.next_attempt_at <= now)
            .order_by(OutboxEmail.next_attempt_at, OutboxEmail.created_at)
            .limit(limit)
        )
    )
    sender, sent = backend(), 0
    for email in due:
        try:
            sender.send(email)
            email.sent_at = utcnow()
            sent += 1
        except Exception as exc:  # network, auth, refused address...
            email.attempts += 1
            email.last_error = str(exc)[:1000]
            if email.attempts >= MAX_ATTEMPTS:
                email.failed_at = utcnow()
                logger.error("giving up on email %s to %s: %s", email.id, email.to_address, exc)
            else:
                email.next_attempt_at = utcnow() + BACKOFF[email.attempts - 1]
        db.commit()
    return sent


async def run_sender(session_factory, interval: float) -> None:
    """Background loop started with the app (one process)."""
    while True:
        from app.services import admin_service

        try:
            await run_in_threadpool(_deliver_once, session_factory)
            admin_service.loop_ran()
        except Exception as e:
            admin_service.loop_failed(e)
            logger.exception("email sender pass failed")
        await asyncio.sleep(interval)


def _deliver_once(session_factory) -> None:
    from app.services import notification_email

    gen = session_factory()
    db = next(gen)
    try:
        notification_email.tick(db)  # grouped notification emails, digests, clean-up
        deliver_pending(db)
    finally:
        gen.close()
