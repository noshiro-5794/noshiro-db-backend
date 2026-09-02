import threading
import time
from contextlib import suppress

from django.conf import settings
from django.core.cache import cache


class RateLimiter:
    def __init__(self, interval: float) -> None:
        self.interval = max(0.0, interval)
        self.lock = threading.Lock()
        self.last_time = 0.0

    def acquire(self) -> None:
        with self.lock:
            now = time.monotonic()
            remaining = self.interval - (now - self.last_time)
            if remaining > 0:
                time.sleep(remaining)
            self.last_time = time.monotonic()


class DistributedRateLimiter:
    """A small Redis/cache-backed interval limiter shared by all workers."""

    def __init__(
        self,
        name: str,
        interval: float,
        *,
        lock_ttl: int = 10,
        allow_fallback: bool | None = None,
    ) -> None:
        self.name = name
        self.interval = max(0.0, interval)
        self.lock_ttl = max(2, lock_ttl)
        self._fallback = RateLimiter(interval)
        self.allow_fallback = (
            settings.DEBUG if allow_fallback is None else allow_fallback
        )

    def acquire(self) -> None:
        if self.interval <= 0:
            return
        lock_key = f"noshiro:provider-rate:{self.name}:lock"
        next_key = f"noshiro:provider-rate:{self.name}:next"
        while True:
            try:
                acquired = cache.add(lock_key, "1", timeout=self.lock_ttl)
            except Exception:
                # Local development/tests may not have Redis. Production fails
                # fast instead of bursting past the provider's rate limit; the
                # campaign retry/backoff machinery then retries the step.
                if self.allow_fallback:
                    self._fallback.acquire()
                    return
                raise
            if not acquired:
                time.sleep(0.02)
                continue
            try:
                now = time.time()
                next_at = float(cache.get(next_key) or 0.0)
                if next_at > now:
                    time.sleep(next_at - now)
                    now = time.time()
                cache.set(
                    next_key,
                    now + self.interval,
                    timeout=max(60, int(self.interval * 10)),
                )
                return
            finally:
                with suppress(Exception):
                    cache.delete(lock_key)
