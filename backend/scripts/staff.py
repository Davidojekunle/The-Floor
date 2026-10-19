"""Who can open the admin page. Staff is never granted through the API, only here.

    cd backend
    python -m scripts.staff list
    python -m scripts.staff add you@example.com
    python -m scripts.staff remove you@example.com

Uses DATABASE_URL from the environment or backend/.env, so point it at the database you mean.
"""
import sys

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.user import User


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("list", "add", "remove") or (argv[0] != "list" and len(argv) != 2):
        print(__doc__)
        return 2
    with SessionLocal() as db:
        if argv[0] == "list":
            staff = db.scalars(select(User).where(User.is_staff.is_(True)).order_by(User.email)).all()
            print("\n".join(f"{u.email}  ({u.name})" for u in staff) or "Nobody is staff yet.")
            return 0
        email = argv[1].strip().lower()
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            print(f"No account with the email {email}. Sign up first, then run this again.")
            return 1
        user.is_staff = argv[0] == "add"
        db.commit()
        print(f"{user.email} {'can now open' if user.is_staff else 'can no longer open'} the admin page.")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
