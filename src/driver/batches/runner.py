"""Runs a batch: one message at a time, each waiting for its trace to finish (docs/design/client-rules.md, 5.4).

Run modes: all checked pending lines; the lines whose dates fall in a range; or one step (the next pending line).
Pause takes effect after the message in progress has finished. Stop does the same and leaves the rest pending.
"""

import threading
import uuid

from driver.lock import gate as shared_gate
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

from driver.api.replay import WORKING, ReplayClient, ReplayError
from driver.batches.files import NY, Batch, Message

Status = Literal["pending", "sending", "waiting", "done", "not_processed", "timeout", "failed", "skipped"]
FINAL_NOT_PROCESSED = {"dropped", "uncertain", "ignored", "duplicate"}  # POST /api/send statuses that never reach the chatbot


@dataclass
class Line:
    index: int
    message: Message
    checked: bool = True
    status: Status = "pending"
    trace_id: str | None = None
    trace_status: str | None = None
    replies: list[dict] = field(default_factory=list)
    error: str | None = None
    touched: int = 0  # the batch version at which this row last changed


class Runner:
    def __init__(self, client: ReplayClient, batch: Batch, members: dict[str, dict],
                 poll_s: float = 1.0, timeout_s: float = 120.0):
        self.client = client
        self.name = batch.name
        self.description = batch.description
        self.members = members  # pseudonym -> {"sender_id", "name", "squad"}
        self.poll_s, self.timeout_s = poll_s, timeout_s
        self.lines = [Line(i, m) for i, m in enumerate(batch.messages)]
        self.current: int | None = 0 if self.lines else None  # the selected row; Run sends it
        self.version = 0
        self.batch_id = uuid.uuid4().hex  # a new batch gets a new id, so the page starts again
        self.state = "idle"  # idle | running | paused
        self.live = False
        self._lock = threading.Lock()
        self._resume = threading.Event()
        self._stop = False
        self._thread: threading.Thread | None = None
        self.gate = shared_gate  # one run at a time across the batch and bot tabs

    # ---- control

    def start(self, mode: Literal["all", "range"], start: date | None = None, end: date | None = None,
              live: bool = False) -> None:
        with self._lock:
            if self.state != "idle":
                raise RuntimeError("a run is already in progress")
            queue = [ln for ln in self.lines if ln.checked and ln.status == "pending" and self._in_range(ln, start, end)]
            if not queue:
                raise RuntimeError("nothing to run: no checked, pending lines in that selection")
            self._claim()
            self._launch(queue, once=False, live=live)

    def select(self, index: int) -> None:
        """Make a row the current one. Clicking a row only selects it; nothing is sent."""
        with self._lock:
            if self.state != "idle":
                raise RuntimeError("wait for the run to finish before choosing a row")
            self.current = index

    def start_current(self, live: bool = False) -> None:
        """Send the selected row, whatever its check box and status. When it finishes, the next row is selected."""
        with self._lock:
            if self.state != "idle":
                raise RuntimeError("a run is already in progress")
            if self.current is None:
                raise RuntimeError("choose a row first")
            self._claim()
            ln = self.lines[self.current]
            ln.status, ln.trace_id, ln.trace_status, ln.replies, ln.error = "pending", None, None, [], None
            self._touch(ln)
            self._launch([ln], once=True, live=live)

    def _claim(self) -> None:
        """Called with the lock held. Refuses while a bot run holds the shared gate."""
        if not self.gate.acquire("batch"):
            raise RuntimeError(f"another run is going: {self.gate.owner}")

    def _launch(self, queue: list[Line], once: bool, live: bool) -> None:
        """Called with the lock held."""
        self.live = live
        self._stop = False
        self._resume.set()
        self.state = "running"
        self._thread = threading.Thread(target=self._loop, args=(queue, once), daemon=True)
        self._thread.start()

    def pause(self) -> None:
        with self._lock:
            if self.state == "running":
                self.state = "paused"
                self._resume.clear()

    def resume(self) -> None:
        with self._lock:
            if self.state == "paused":
                self.state = "running"
                self._resume.set()

    def stop(self) -> None:
        with self._lock:
            self._stop = True
            self._resume.set()  # wake a paused run so it can stop

    def reset(self) -> None:
        """Mark every line that is not sending as pending again, so it can be run again."""
        with self._lock:
            if self.state != "idle":
                raise RuntimeError("stop the run before resetting")
            self._touch(*self.lines)
            for ln in self.lines:
                ln.status, ln.trace_id, ln.trace_status, ln.replies, ln.error = "pending", None, None, [], None

    def set_checked(self, index: int, checked: bool) -> None:
        with self._lock:
            if self.state != "idle" and self.lines[index].status == "sending":
                raise RuntimeError("that message is being sent")
            self.lines[index].checked = checked
            self._touch(self.lines[index])

    def wait_idle(self, timeout: float | None = None) -> None:
        """For tests and scripts: wait until the run has finished."""
        if self._thread:
            self._thread.join(timeout)

    # ---- the run

    @staticmethod
    def _in_range(ln: Line, start: date | None, end: date | None) -> bool:
        day = ln.message.created_at.astimezone(NY).date()
        return (start is None or day >= start) and (end is None or day <= end)

    def _loop(self, queue: list[Line], once: bool) -> None:
        try:
            for ln in queue:
                self._resume.wait()
                if self._stop:
                    break
                self._send_one(ln)
                if once:
                    with self._lock:  # the next row becomes the selection; it is not run
                        if ln.index + 1 < len(self.lines):
                            self.current = ln.index + 1
                    break
        finally:
            self.gate.release("batch")
            with self._lock:
                self.state = "idle"
                self._stop = False

    def _send_one(self, ln: Line) -> None:
        msg = ln.message
        with self._lock:
            ln.status, ln.error = "sending", None
            self._touch(ln)
        member = self.members.get(msg.member)
        if member is None:
            self._finish(ln, "failed", error=f"{msg.member} is not on the roster")
            return
        try:
            sent = self.client.send(member["sender_id"], msg.text, msg.created_at.isoformat(), self.live)
        except ReplayError as exc:
            self._finish(ln, "failed", error=str(exc))
            return
        with self._lock:
            ln.trace_id = sent.get("trace_id")
            self._touch(ln)
        if sent.get("status") in FINAL_NOT_PROCESSED:
            self._finish(ln, "not_processed", trace_status=sent.get("status"))
            return
        with self._lock:
            ln.status = "waiting"
            self._touch(ln)
        deadline = time.monotonic() + self.timeout_s
        while True:
            try:
                trace = self.client.trace(ln.trace_id)
            except ReplayError as exc:
                self._finish(ln, "failed", error=str(exc))
                return
            if trace.get("status") not in WORKING:
                break
            if time.monotonic() > deadline:
                self._finish(ln, "timeout", trace_status=trace.get("status"))
                return
            time.sleep(self.poll_s)
        try:
            replies = self.client.outbox(ln.trace_id)
        except ReplayError as exc:
            self._finish(ln, "failed", trace_status=trace.get("status"), error=str(exc))
            return
        self._finish(ln, "done", trace_status=trace.get("status"), replies=replies)

    def _finish(self, ln: Line, status: Status, trace_status=None, replies=None, error=None) -> None:
        with self._lock:
            ln.status = status
            self._touch(ln)
            if trace_status is not None:
                ln.trace_status = trace_status
            if replies is not None:
                ln.replies = replies
            ln.error = error

    # ---- what the page shows

    # ---- what the page shows

    def _touch(self, *lines: "Line") -> None:
        """Called with the lock held: a new version, and these rows changed in it."""
        self.version += 1
        for ln in lines:
            ln.touched = self.version

    def _status_locked(self) -> dict:
        return {"batch_id": self.batch_id, "version": self.version, "name": self.name,
                "description": self.description, "state": self.state, "live": self.live, "current": self.current,
                "pending": sum(1 for ln in self.lines if ln.status == "pending" and ln.checked),
                "total": len(self.lines)}

    def _row(self, ln: Line) -> dict:
        m = ln.message
        who = self.members.get(m.member, {})
        return {
            "index": ln.index, "id": m.id, "when": m.created_at.isoformat(),
            "display_time": m.created_at.strftime("%B %-d, %Y %-I:%M:%S %p"),
            "name": who.get("name", "unknown"), "squad": who.get("squad", ""), "member": m.member,
            "text": m.text, "checked": ln.checked, "status": ln.status,
            "trace_id": ln.trace_id, "trace_status": ln.trace_status,
            "replies": [{"kind": r.get("kind"), "text": r.get("text"), "channel": r.get("channel"),
                         "status": r.get("status"), "error": r.get("error")} for r in ln.replies],
            "error": ln.error,
        }

    def status(self) -> dict:
        with self._lock:
            return self._status_locked()

    def snapshot(self, since: int = -1) -> dict:
        """The status, and the rows that changed after batch version `since` (every row when since is negative)."""
        with self._lock:
            out = self._status_locked()
            out["lines"] = [self._row(ln) for ln in self.lines if since < 0 or ln.touched > since]
            return out
