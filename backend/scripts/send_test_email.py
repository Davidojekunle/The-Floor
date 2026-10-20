"""Send one test email with the current SMTP settings, straight away. Nothing is stored in the database.

    cd backend
    python -m scripts.send_test_email you@example.com

Uses EMAIL_FROM and the SMTP_* settings from the environment or backend/.env. Prints OK, or FAILED: and why.
"""
import sys

from app.core.config import get_settings
from app.models.email import OutboxEmail
from app.services import email_service


def main(argv: list[str]) -> int:
    if len(argv) != 1 or "@" not in argv[0]:
        print(__doc__)
        return 2
    s = get_settings()
    if s.email_backend != "smtp":
        print(f"FAILED: EMAIL_BACKEND is {s.email_backend!r}. Set EMAIL_BACKEND=smtp to send real email.")
        return 1
    text, html_body = email_service.render(
        "Test email from The Floor",
        ["If you can read this, The Floor can send email.", f"Sent from {s.email_from} through {s.smtp_host}:{s.smtp_port}."],
    )
    email = OutboxEmail(to_address=argv[0], subject="Test email from The Floor", text_body=text, html_body=html_body,
                        category="security", headers={})
    print(f"Sending to {argv[0]} from {s.email_from} via {s.smtp_host}:{s.smtp_port} (STARTTLS {'on' if s.smtp_starttls else 'off'})...")
    try:
        email_service.SmtpBackend().send(email)
    except Exception as e:  # smtplib errors say what the server answered; they don't include the password
        print(f"FAILED: {type(e).__name__}: {e}")
        return 1
    print("OK: sent. Check the inbox (and spam).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
