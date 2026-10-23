"""Email "Confirm your email" to every account that hasn't confirmed yet. For accounts made before confirmation
existed; new sign-ups get it automatically. Queued in the outbox, so the running app sends them.

    cd backend
    python -m scripts.send_verification            # who would get it (sends nothing)
    python -m scripts.send_verification --send     # queue the emails

Uses DATABASE_URL and FRONTEND_URL from the environment or backend/.env, so point it at the database you mean.
"""
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.user import User
from app.services import account_service


def main(argv: list[str]) -> int:
    send = argv == ["--send"]
    if argv and not send:
        print(__doc__)
        return 2
    base = get_settings().frontend_url.rstrip("/")
    with SessionLocal() as db:
        users = list(db.scalars(select(User).where(User.email_verified_at.is_(None)).order_by(User.created_at)))
        for u in users:
            print(f"{u.email}  ({u.name})")
            if send:
                account_service.send_verification(db, u, base)
        if send:
            db.commit()
    print(f"\n{len(users)} unconfirmed. " + (f"Queued, with links to {base}." if send else "Nothing sent: add --send."))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
