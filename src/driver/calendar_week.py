"""The Bot tab's week preview: seven days of the test calendar, as shift lines, and what changed between reads.

Reads only. Each day is the calendar's `get_schedule_day` answer (calendar_test.CalendarService.raw_day), parsed into
lines of `start, end, squads`. The test calendar gives each shift `start_time`, `end_time` and `segments`; each segment
is one line, with its own squads, and `active: false` is No Crew. Other spellings (the tests' fake) are accepted too,
and a day that cannot be read falls back to its raw text.
"""

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from driver.calendar_test import CalendarError, GuardRefused, day_schedule

MAX_TRACKED_DAYS = 42  # days kept for change detection: the weeks viewed most recently, about six


def sunday_of(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _hhmm(text: str) -> str:
    digits = re.sub(r"\D", "", str(text))
    return digits.zfill(4)[:4] if digits else ""


def _squad(entry) -> dict | None:
    """One squad on a shift: {"id": 43, "no_crew": False}. Accepts a number or a dict."""
    if isinstance(entry, (int, str)) and str(entry).strip():
        return {"id": str(entry).strip(), "no_crew": False}
    if not isinstance(entry, dict):
        return None
    sid = entry.get("id", entry.get("squad", entry.get("number")))
    if sid is None:
        return None
    status = str(entry.get("status", "")).lower().replace("_", " ")
    no_crew = entry.get("active") is False or bool(entry.get("no_crew")) or status == "no crew"
    return {"id": str(sid), "no_crew": no_crew}


def _span(entry: dict) -> tuple[str, str] | None:
    start = entry.get("start_time", entry.get("start", entry.get("shift_start")))
    end = entry.get("end_time", entry.get("end", entry.get("shift_end")))
    if start is None or end is None:
        name = str(entry.get("name", entry.get("shift", entry.get("time", ""))))
        parts = re.split(r"\s*[-–]\s*", name.strip())
        if len(parts) != 2:
            return None
        start, end = parts
    return _hhmm(start), _hhmm(end)


def _lines_of(entry) -> list[dict] | None:
    """The lines for one shift. A shift with segments gives one line per segment (a split shift); otherwise one."""
    if not isinstance(entry, dict):
        return None
    parts = entry.get("segments") if isinstance(entry.get("segments"), list) and entry["segments"] else [entry]
    lines = []
    for part in parts:
        span = _span(part) if isinstance(part, dict) else None
        if span is None:
            return None
        squads = [x for x in (_squad(q) for q in part.get("squads") or []) if x]
        lines.append({"start": span[0], "end": span[1], "squads": squads})
    return lines


def shift_lines(raw: dict) -> list[dict] | None:
    """The day's shift lines in the calendar's own order, or None when the answer cannot be read as shifts.
    The order is kept: a night shift can be listed as 1800-0000 then 0000-0600."""
    parsed = day_schedule(raw)
    if not isinstance(parsed, dict):
        return None
    shifts = parsed.get("shifts")
    if not isinstance(shifts, list):
        return None
    lines = []
    for entry in shifts:
        got = _lines_of(entry)
        if got is None:
            return None
        lines.extend(got)
    return lines


def line_text(line: dict) -> str:
    squads = ", ".join(s["id"] + (" (No Crew)" if s["no_crew"] else "") for s in line["squads"]) or "—"
    return f"{line['start']}–{line['end']} {squads}"


def _key(line: dict) -> tuple:
    return line["start"], line["end"], tuple((s["id"], s["no_crew"]) for s in line["squads"])


def day_change(before: list[dict] | None, after: list[dict] | None) -> dict | None:
    """What changed on one day, or None. Lists the lines that are new, and the lines that went."""
    if before is None or after is None:
        return None
    old, new = {_key(ln): ln for ln in before}, {_key(ln): ln for ln in after}
    added = [line_text(new[k]) for k in new if k not in old]
    removed = [line_text(old[k]) for k in old if k not in new]
    if not added and not removed:
        return None
    return {"added": added, "removed": removed}


class WeekReader:
    """Reads weeks for the page and remembers the last read of each day, to say what changed since."""

    def __init__(self, calendar_factory) -> None:
        self._factory = calendar_factory  # called at the first read, so a bad address is reported, not fatal at start
        self._calendar = None
        self._last: dict[str, list[dict] | None] = {}  # iso date -> lines at the last read, most recent last
        self._lock = threading.Lock()

    def _read_day(self, calendar, day: date) -> dict:
        try:
            raw = calendar.raw_day(day)
        except (CalendarError, GuardRefused) as exc:
            return {"date": day.isoformat(), "lines": None, "raw": None, "error": str(exc)}
        lines = shift_lines(raw)
        text = None
        if lines is None:  # not readable as shifts: the page shows the text instead
            parsed = day_schedule(raw)
            text = parsed if isinstance(parsed, str) else json.dumps(parsed)
        return {"date": day.isoformat(), "lines": lines, "raw": text, "error": None}

    def read(self, start: date, recheck: bool = False) -> dict:
        """The week from `start` (moved back to its Sunday). With recheck, the other days read recently are read
        again too, so a change outside the week shown can be reported. Changes compare each day with its last read."""
        sunday = sunday_of(start)
        week = [sunday + timedelta(days=i) for i in range(7)]
        with self._lock:
            others = [date.fromisoformat(d) for d in self._last if recheck and date.fromisoformat(d) not in week]
        try:
            if self._calendar is None:
                self._calendar = self._factory()
            calendar = self._calendar
        except GuardRefused as exc:
            return {"start": sunday.isoformat(),
                    "days": [{"date": d.isoformat(), "lines": None, "raw": None, "error": str(exc)} for d in week],
                    "changes": []}
        with ThreadPoolExecutor(max_workers=7) as pool:
            results = list(pool.map(lambda d: self._read_day(calendar, d), week + others))
        changes = []
        with self._lock:
            for res in results:
                if res["error"] is not None:
                    continue
                iso = res["date"]
                if iso in self._last:
                    change = day_change(self._last[iso], res["lines"])
                    if change:
                        changes.append({"date": iso, "in_week": date.fromisoformat(iso) in week, **change})
                    del self._last[iso]  # re-insert below, so the dict keeps the most recent reads last
                self._last[iso] = res["lines"]
            while len(self._last) > MAX_TRACKED_DAYS:
                del self._last[next(iter(self._last))]
        return {"start": sunday.isoformat(), "days": results[:7], "changes": sorted(changes, key=lambda c: c["date"])}

    def forget(self) -> None:
        with self._lock:
            self._last.clear()
