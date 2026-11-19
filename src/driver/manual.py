"""Manual chat on the Bot tab: I type a message as a member of a squad, and the chatbot's replies come back.

Members come from the roster file (driver.roster): real names, sender ids and squads. The message goes to the chatbot
with that member's sender id, name and squad, as a chat client would send it.

One message at a time. While a message waits for its reply it holds the shared run gate, so a batch run or a bot run
cannot start in the middle of it. The events have the same shapes as a bot run's (`post`, `reply`, `note`), so the
page shows both the same way. The posting setting is always `wait`.
"""

import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from driver import roster as roster_file
from driver.api.replay import WORKING, ReplayError, model_tokens
from driver.lock import gate

NY = ZoneInfo("America/New_York")
PENDING_REPLY = {"pending"}  # outbox rows still being sent
NOT_TAKEN = {"dropped", "uncertain", "ignored", "duplicate"}  # send statuses that never reach the chatbot


class ManualBusy(Exception):
    """A message is still waiting for its reply, or another run holds the gate."""


def parse_when(text: str) -> datetime:
    """A time from the page. Without an offset it is New York time."""
    when = datetime.fromisoformat(text)
    if when.tzinfo is None:
        when = when.replace(tzinfo=NY)
    return when.astimezone(NY)


class ManualChat:
    def __init__(self, replay, members, poll_s: float = 1.0, timeout_s: float = 120.0) -> None:
        self.replay = replay
        self.members = members  # called for the roster rows: [{name, sender_id, squad}], sorted by name
        self.poll_s, self.timeout_s = poll_s, timeout_s
        self.events: list[dict] = []
        self.session = 0  # a new number after Clear, so the page starts again
        self.waiting = False
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    # ---- what the page calls

    def resolve(self, squad: str, name: str | None) -> dict:
        """The roster row to send as: the member named, or the squad's first member by name."""
        squad = str(squad).strip()
        members = self.members()
        if not name:
            first = roster_file.first_of_squad(members, squad)
            if first is None:
                raise ValueError(f"squad {squad} has no members on the roster")
            return first
        for m in members:
            if m["name"] == name:
                if m["squad"] != squad:
                    raise ValueError(f"{name} is in squad {m['squad']}, not {squad}")
                return m
        raise ValueError(f"{name} is not on the roster")

    def send(self, squad: str, name: str | None, text: str, sent_at: str, live: bool) -> dict:
        """Post the message now, so the trace id is known before this returns. The reply is read in a thread.
        Returns {"trace_id": ..., "status": ...} from the replay tool. A failed post raises, and nothing is left running."""
        text = (text or "").strip()
        if not text:
            raise ValueError("the message is empty")
        try:
            when = parse_when(sent_at)
        except ValueError:
            raise ValueError("sent_at must be a date and time, for example 2026-03-10T09:05")
        who = self.resolve(squad, name)
        with self._lock:
            if self.waiting:
                raise ManualBusy("wait for the reply to the last message")
            if not gate.acquire("manual"):
                raise ManualBusy(f"another run is going: {gate.owner}")
            self.waiting = True
            session = self.session
        try:
            sent = self.replay.send(who["sender_id"], text, when.isoformat(), live, name=who["name"], squad=squad)
        except Exception:
            gate.release("manual")
            with self._lock:
                self.waiting = False
            raise
        self._thread = threading.Thread(target=self._run, args=(session, who, text, when, sent), daemon=True)
        self._thread.start()
        # what the page needs to show the member's bubble at once, before the status poll brings the post event
        return {"trace_id": sent.get("trace_id"), "status": sent.get("status"), "sent_at": when.isoformat(),
                "name": who["name"], "squad": who["squad"]}

    def clear(self) -> None:
        with self._lock:
            if self.waiting:
                raise ManualBusy("wait for the reply before clearing")
            self.events = []
            self.session += 1

    def status(self, since: int = 0) -> dict:
        with self._lock:
            return {"session": self.session, "waiting": self.waiting, "next": len(self.events),
                    "events": self.events[since:]}

    def wait_idle(self, timeout: float | None = None) -> None:
        """For tests."""
        if self._thread:
            self._thread.join(timeout)

    # ---- the send, in a thread

    def _emit(self, session: int, kind: str, **data) -> None:
        with self._lock:
            if session != self.session:
                return
            self.events.append({"i": len(self.events), "kind": kind, "source": "manual", **data})

    def _run(self, session: int, who: dict, text: str, when: datetime, sent: dict) -> None:
        squad = who["squad"]
        try:
            trace_id = sent.get("trace_id")
            self._emit(session, "post", persona=who["name"], name=who["name"], squad=squad, text=text,
                       setting="wait", sent_at=when.isoformat(), trace_id=trace_id, send_status=sent.get("status"))
            if not trace_id:
                self._emit(session, "note", text=f"the chatbot did not take this message ({sent.get('status')})")
                return
            if sent.get("status") in NOT_TAKEN:  # the turn is over at once: say so, with no message
                self._done(session, trace_id, squad, when, sent.get("status"))
                return
            self._wait_and_read(session, trace_id, squad, when)
        except Exception as exc:  # the page sees the type; nothing else is lost
            self._emit(session, "note", text=f"failed: {type(exc).__name__}")
        finally:
            gate.release("manual")
            with self._lock:
                self.waiting = False

    def _wait_and_read(self, session: int, trace_id: str, squad: str, when: datetime) -> None:
        deadline = time.monotonic() + self.timeout_s
        try:
            while (status := (trace := self.replay.trace(trace_id)).get("status", "unknown")) in WORKING:
                if time.monotonic() > deadline:
                    self._emit(session, "note", text="no reply yet: timed out waiting for the chatbot", trace_id=trace_id)
                    return
                time.sleep(self.poll_s)
            while True:
                rows = self.replay.outbox(trace_id)
                if not any(r.get("status") in PENDING_REPLY for r in rows) or time.monotonic() > deadline:
                    break
                time.sleep(self.poll_s)
        except ReplayError as exc:
            self._emit(session, "note", text=f"could not read the reply: {exc}", trace_id=trace_id)
            return
        tokens = model_tokens(trace)  # the chatbot's model use for this message, shown once, on its first reply
        if not any((r.get("text") or "").strip() for r in rows):
            self._done(session, trace_id, squad, when, status, tokens)  # finished, with nothing to say
            return
        for n, row in enumerate(rows):
            self._emit(session, "reply", trace_id=trace_id, squad=squad, tokens=tokens if n == 0 else None,
                       sent_at=row.get("sent_at") or row.get("created_at") or when.isoformat(),
                       reply_kind=row.get("kind"), text=row.get("text") or "", channel=row.get("channel"),
                       status=row.get("status"), error=row.get("error"))

    def _done(self, session: int, trace_id: str, squad: str, when: datetime, status: str,
              tokens: dict | None = None) -> None:
        """The turn is finished and the chatbot sent no message (it acted, or chose not to). The page shows the
        reply's title line alone, so every message is seen to be finished."""
        self._emit(session, "reply", trace_id=trace_id, squad=squad, sent_at=when.isoformat(), text="",
                   no_message=True, trace_status=status, tokens=tokens)
