"""One run at a time across the batch tab and the bot tab. Both post to the same chatbot history, so they must not overlap."""

import threading


class RunGate:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.owner: str | None = None

    def acquire(self, owner: str) -> bool:
        with self._lock:
            if self.owner is None:
                self.owner = owner
                return True
            return False

    def release(self, owner: str) -> None:
        with self._lock:
            if self.owner == owner:
                self.owner = None

    def reset(self) -> None:
        with self._lock:
            self.owner = None


gate = RunGate()
