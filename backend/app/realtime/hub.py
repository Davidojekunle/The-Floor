"""In-memory fan-out of live events to connected WebSockets (single process).

Thread-safe: synchronous routes publish from worker threads; each socket's
send happens on the event loop that owns it.
"""
import asyncio
import logging
import threading
import uuid
from collections import defaultdict

from app.utils.time import utcnow

logger = logging.getLogger("taskroom.realtime")


class Hub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sockets: dict[uuid.UUID, set] = defaultdict(set)  # user_id -> {(websocket, loop)}

    # ---------------------------------------------------------------- connections
    def register(self, user_id: uuid.UUID, ws, loop) -> None:
        with self._lock:
            self._sockets[user_id].add((ws, loop))

    def unregister(self, user_id: uuid.UUID, ws) -> None:
        with self._lock:
            entries = self._sockets.get(user_id, set())
            for entry in [e for e in entries if e[0] is ws]:
                entries.discard(entry)
            if not entries:
                self._sockets.pop(user_id, None)

    def connected_users(self) -> set[uuid.UUID]:
        with self._lock:
            return set(self._sockets)

    def is_empty(self) -> bool:
        with self._lock:
            return not self._sockets

    def close_users(self, user_ids, code: int = 4401) -> None:
        """Close every socket of these users (sign-out everywhere). Safe from any thread."""
        with self._lock:
            targets = [(ws, loop) for uid in user_ids for ws, loop in self._sockets.get(uid, ())]
        for ws, loop in targets:
            if not loop.is_closed():
                asyncio.run_coroutine_threadsafe(self._close(ws, code), loop)

    @staticmethod
    async def _close(ws, code: int) -> None:
        try:
            await ws.close(code=code)
        except Exception:
            pass

    # ---------------------------------------------------------------- publishing
    def publish(self, events: list[tuple[dict, set]]) -> None:
        """events: [(payload, {user_id, ...})]. Safe to call from any thread."""
        if not events or self.is_empty():
            return
        at = utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        by_loop: dict = defaultdict(list)
        with self._lock:
            for payload, recipients in events:
                message = {**payload, "at": at}
                for user_id in recipients:
                    for ws, loop in self._sockets.get(user_id, ()):
                        by_loop[loop].append((ws, message))
        for loop, sends in by_loop.items():
            if loop.is_closed():
                continue
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                loop.create_task(self._send_all(sends))
            else:
                asyncio.run_coroutine_threadsafe(self._send_all(sends), loop)

    async def _send_all(self, sends) -> None:
        for ws, message in sends:
            try:
                await ws.send_json(message)
            except Exception:  # a socket that just went away; its handler will unregister it
                logger.debug("dropping event for a closed socket", exc_info=True)


hub = Hub()
