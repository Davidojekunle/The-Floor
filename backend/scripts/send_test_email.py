"""Send one test email with the current email settings (SMTP or Resend), straight away. Nothing is stored in the database.

    cd backend
    python -m scripts.send_test_email you@example.com

Uses EMAIL_FROM and the SMTP_* or RESEND_API_KEY settings from the environment or backend/.env. Prints OK, or FAILED: and why.
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
    if s.email_backend not in ("smtp", "resend"):
        print(f"FAILED: EMAIL_BACKEND is {s.email_backend!r}. Set EMAIL_BACKEND=smtp or resend to send real email.")
        return 1
    via = "the Resend API" if s.email_backend == "resend" else f"{s.smtp_host}:{s.smtp_port}"
    text, html_body = email_service.render(
        "Test email from The Floor",
        ["If you can read this, The Floor can send email.", f"Sent from {s.email_from} through {via}."],
    )
    email = OutboxEmail(to_address=argv[0], subject="Test email from The Floor", text_body=text, html_body=html_body,
                        category="security", headers={})
    tls = "" if s.email_backend == "resend" else f" (STARTTLS {'on' if s.smtp_starttls else 'off'})"
    print(f"Sending to {argv[0]} from {s.email_from} via {via}{tls}...")
    try:
        email_service.backend().send(email)
    except Exception as e:  # errors say what the server answered; they don't include the password or key
        print(f"FAILED: {type(e).__name__}: {e}")
        return 1
    print("OK: sent. Check the inbox (and spam).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
