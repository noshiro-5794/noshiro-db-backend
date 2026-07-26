import threading
import time


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
