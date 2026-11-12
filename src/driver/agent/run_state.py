"""What one bot run holds: its settings, its events, and the calendar images.

Everything here is in memory, and each event is also appended to the run's transcript file. Real names are never
stored here; the only real-name handling is `scrub`, which turns them into pseudonyms before text reaches a model.
"""

import difflib
import json
import re
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from driver.calendar_test import day_schedule


class Stopped(Exception):
    """The run was stopped, or hit a limit. `reason` says which."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class RunContext:
    folder: Path
    personas: dict  # pseudonym -> squad
    window_start: date
    window_end: date
    gate: date
    live: bool
    setup_allowed: bool
    posting_allowed: set
    max_messages: int
    max_cost_usd: float
    reply_timeout_s: float
    real_names: dict  # real name -> pseudonym; used only by scrub
    events: list = field(default_factory=list)
    snapshots: dict = field(default_factory=dict)  # (label, iso date) -> raw calendar answer
    days: set = field(default_factory=set)  # iso dates in question
    messages_posted: int = 0
    spent_usd: float = 0.0
    stopped: str | None = None
    plan: str | None = None
    checks: list = field(default_factory=list)
    verdicts: list = field(default_factory=list)
    verdict_summary: str = ""
    finished: dict | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "snapshots").mkdir(exist_ok=True)

    def emit(self, kind: str, **data) -> dict:
        with self.lock:
            event = {"i": len(self.events), "kind": kind, "at": datetime.now().isoformat(timespec="seconds"), **data}
            self.events.append(event)
        with (self.folder / "transcript.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        return event

    def check_stop(self) -> None:
        if self.stopped:
            raise Stopped(self.stopped)

    def scrub(self, text: str) -> str:
        for real, pseudonym in self.real_names.items():
            text = re.sub(re.escape(real), pseudonym, text, flags=re.IGNORECASE)
        return text

    def save_snapshot(self, label: str, iso_day: str, raw: dict) -> None:
        with self.lock:
            self.snapshots[(label, iso_day)] = raw
        path = self.folder / "snapshots" / f"{label}_{iso_day}.json"
        path.write_text(json.dumps(raw, indent=1), encoding="utf-8")


def real_name_map(members: list[dict]) -> dict:
    """Full names, and name words of four or more letters, mapped to the member's pseudonym."""
    names = {}
    for m in members:
        real = (m.get("name") or "").strip()
        if not real or real == m["member"]:
            continue
        names[real] = m["member"]
        for word in re.findall(r"[A-Za-z]{4,}", real):
            names.setdefault(word, m["member"])
    return names


def _lines(raw: dict) -> list[str]:
    return json.dumps(day_schedule(raw), indent=1, sort_keys=True).splitlines()


def diff_text(before: dict | None, after: dict | None) -> str:
    if before is None or after is None:
        return "(no before image: this day was not in question when the run started)"
    lines = difflib.unified_diff(_lines(before), _lines(after), "before", "after", lineterm="", n=1)
    text = "\n".join(lines)
    return text or "(no change)"
