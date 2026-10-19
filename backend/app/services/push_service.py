"""Browser push (Web Push with VAPID): the bell's third channel, for when The Floor isn't open.

Pushes are queued during a request and sent only after the commit, on a small thread pool, so a slow push
service never holds up the request. A push service that says the subscription is gone (404/410) gets it deleted.
What gets pushed follows the same rules as email: not your own actions, not muted rooms, and only the
categories (requests, decisions, work for you) the person has switched on.
"""
import base64
import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid01
from sqlalchemy import delete, event, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.models.push import PushSubscription, ServerKey
from app.models.user import User

logger = logging.getLogger("taskroom")

_PENDING = "push_pending"
_KEY_NAME = "vapid_private_pem"
MAX_PER_USER = 10  # browsers; the oldest goes when an 11th turns push on

# Only real browser push services, so a subscription can't point the server at an arbitrary URL.
PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "push.services.mozilla.com",
              "web.push.apple.com", "notify.windows.com", "push.apple.com")

_lock = threading.Lock()
_vapid: Vapid01 | None = None
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="push")


# ================================================================== keys

def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def vapid(db: Session) -> Vapid01:
    """The server's push key: VAPID_PRIVATE_KEY (PEM) if set, else one made on first use and kept in the database."""
    global _vapid
    if _vapid is not None:
        return _vapid
    with _lock:
        if _vapid is not None:
            return _vapid
        pem = get_settings().vapid_private_key.replace("\\n", "\n").strip()
        if not pem:
            row = db.get(ServerKey, _KEY_NAME)
            if row is None:
                key = ec.generate_private_key(ec.SECP256R1())
                pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()).decode()
                try:
                    with db.begin_nested():
                        db.add(ServerKey(name=_KEY_NAME, value=pem))
                    db.commit()
                except IntegrityError:  # another process made one first: use theirs
                    db.rollback()
                    pem = db.get(ServerKey, _KEY_NAME).value
            else:
                pem = row.value
        _vapid = Vapid01.from_pem(pem.encode())
        return _vapid


def public_key(db: Session) -> str:
    """For the browser's pushManager.subscribe(applicationServerKey): the raw P-256 point, base64url."""
    point = vapid(db).public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return _b64url(point)


# ================================================================== subscriptions

def _check_endpoint(endpoint: str) -> None:
    url = urlparse(endpoint)
    host = (url.hostname or "").lower()
    if url.scheme != "https" or not any(host == h or host.endswith("." + h) for h in PUSH_HOSTS):
        raise ValidationFailed("That isn't a browser push address.", fields={"endpoint": "Not a known push service."})


def subscribe(db: Session, user: User, *, endpoint: str, p256dh: str, auth: str, user_agent: str | None) -> None:
    _check_endpoint(endpoint)
    row = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if row is None:
        row = PushSubscription(id=uuid.uuid4(), endpoint=endpoint)
        db.add(row)
    row.user_id, row.p256dh, row.auth = user.id, p256dh, auth
    row.user_agent = (user_agent or "")[:300] or None
    db.flush()
    extra = db.scalars(
        select(PushSubscription.id).where(PushSubscription.user_id == user.id)
        .order_by(PushSubscription.created_at.desc()).offset(MAX_PER_USER)
    ).all()
    if extra:
        db.execute(delete(PushSubscription).where(PushSubscription.id.in_(extra)))
    db.commit()


def unsubscribe(db: Session, user: User, endpoint: str) -> None:
    db.execute(delete(PushSubscription).where(PushSubscription.user_id == user.id, PushSubscription.endpoint == endpoint))
    db.commit()


def forget_all(db: Session, user_id) -> None:
    """Sign out everywhere: no device should keep getting this account's notifications. The caller commits.
    A browser that signs back in and still has push on re-registers itself."""
    db.execute(delete(PushSubscription).where(PushSubscription.user_id == user_id))


# ================================================================== sending

def queue(db: Session, user_id, *, title: str, body: str | None, url: str, tag: str) -> None:
    if not get_settings().push_enabled:
        return
    if not db.scalar(select(exists().where(PushSubscription.user_id == user_id))):
        return  # no browser registered: don't wake the pool
    db.info.setdefault(_PENDING, []).append((user_id, {"title": title, "body": body, "url": url, "tag": tag}))


@event.listens_for(Session, "after_commit")
def _send_after_commit(session: Session) -> None:
    pending = session.info.pop(_PENDING, None)
    if pending:
        _pool.submit(_deliver, session.get_bind(), pending)


@event.listens_for(Session, "after_rollback")
def _discard(session: Session) -> None:
    session.info.pop(_PENDING, None)


def _deliver(bind, pending) -> None:
    try:
        deliver(bind, pending)
    except Exception:
        logger.exception("push delivery failed")


def deliver(bind, pending) -> int:
    """Send each queued push to every browser its person registered. Returns how many were accepted."""
    from pywebpush import WebPushException, webpush

    sent = 0
    with Session(bind=bind, expire_on_commit=False) as db:
        key = vapid(db)
        subject = get_settings().vapid_subject
        gone: list = []
        for user_id, payload in pending:
            for sub in db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)).all():
                try:
                    webpush(
                        subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                        data=json.dumps(payload),
                        vapid_private_key=key,
                        vapid_claims={"sub": subject},
                        ttl=60 * 60 * 24,
                        timeout=10,
                    )
                    sent += 1
                except WebPushException as e:
                    status = getattr(e.response, "status_code", None)
                    if status in (404, 410):
                        gone.append(sub.id)  # the browser dropped it (uninstalled, permission revoked)
                    else:
                        logger.warning("push to %s failed: %s", urlparse(sub.endpoint).hostname, e)
                except Exception as e:  # network trouble: try again with the next notification
                    logger.warning("push to %s failed: %s", urlparse(sub.endpoint).hostname, e)
        if gone:
            db.execute(delete(PushSubscription).where(PushSubscription.id.in_(gone)))
            db.commit()
    return sent
