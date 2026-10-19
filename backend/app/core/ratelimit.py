"""In-memory sliding-window rate limits (single process; Redis later with no contract change)."""
import ipaddress
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import RateLimited


class Limiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque] = defaultdict(deque)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def hit(self, key: str, limit: int, window: float) -> None:
        """Count one attempt; raise RateLimited when over the limit. No-op when limits are off."""
        if not get_settings().rate_limit_enabled:
            return
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                raise RateLimited(retry_after=q[0] + window - now + 1)
            q.append(now)

    def would_allow(self, key: str, limit: int, window: float) -> bool:
        """Count one attempt and say whether it fits, without raising (for silent limits)."""
        try:
            self.hit(key, limit, window)
            return True
        except RateLimited:
            return False


limiter = Limiter()

MINUTE, HOUR = 60, 3600


def _is_trusted(addr: str, trusted: list[str]) -> bool:
    """Exact IPs or CIDR ranges ("10.0.0.0/8"): hosts like Render forward from addresses that change."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    for entry in trusted:
        try:
            if ip in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def client_ip(request: Request) -> str:
    """The connection's address, or X-Forwarded-For only when the connection is from a trusted proxy."""
    peer = request.client.host if request.client else "unknown"
    trusted = get_settings().trusted_proxies_list
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded or not _is_trusted(peer, trusted):
        return peer
    # walk right to left, skipping our own proxies: the first address that isn't one is the client
    for hop in reversed([h.strip() for h in forwarded.split(",") if h.strip()]):
        if not _is_trusted(hop, trusted):
            return hop
    return peer
