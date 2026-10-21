"""Security headers on every HTTP response (plain ASGI, so WebSockets pass straight through).

The content security policy allows only this site for scripts, styles, fonts and API calls. The one
exception is the result players (YouTube, Vimeo, Loom, Google Drive/Docs, Instagram, TikTok, Canva),
which may be framed. Images and videos may come from any https address, because a result can be a link
to one. Inline style attributes are allowed: React sets them for widths, colours and positions.
"""

FRAME_SOURCES = (
    "https://www.youtube-nocookie.com https://player.vimeo.com https://www.loom.com https://drive.google.com "
    "https://docs.google.com https://www.instagram.com https://www.tiktok.com https://www.canva.com"
)


def csp(host: str) -> str:
    # 'self' covers same-origin WebSockets in current browsers; the explicit ws/wss entries cover older Safari.
    live = f" wss://{host} ws://{host}" if host else ""
    return "; ".join((
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob: https:",
        "media-src 'self' blob: https:",
        "font-src 'self' data:",
        f"connect-src 'self'{live}",
        f"frame-src {FRAME_SOURCES}",
        "worker-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ))


class SecurityHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        host = headers.get("host", "")
        https = scope.get("scheme") == "https"

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                extra = [
                    (b"content-security-policy", csp(host).encode("latin-1")),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
                    (b"cross-origin-opener-policy", b"same-origin"),
                ]
                if https:  # only over https: a browser ignores HSTS on plain http anyway
                    extra.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                present = {k.lower() for k, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [(k, v) for k, v in extra if k not in present]
            await send(message)

        await self.app(scope, receive, send_with_headers)
