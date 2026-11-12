"""The test calendar, and the only way the driver reaches a calendar.

The guard is in code: any address other than the test calendar (port 7007, a local host) is refused, including
production (port 8007). Reads are `get_schedule_day`. Changes are `addShift` and `noCrew`, and a change is only a
preview unless the caller asks for a live one. Rollback is not exposed to the bot.
"""

import json
from datetime import date
from urllib.parse import urlparse

import httpx

TEST_PORT = 7007
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "host.docker.internal"}
CHANGE_ACTIONS = {"addShift", "noCrew"}


class GuardRefused(Exception):
    """A request was refused by the calendar guard. Nothing was sent."""


class CalendarError(Exception):
    """The calendar service refused or failed a request."""


def check_url(url: str) -> str:
    parts = urlparse(url)
    if parts.port != TEST_PORT or parts.hostname not in ALLOWED_HOSTS:
        raise GuardRefused(f"calendar address refused: only the test calendar (port {TEST_PORT}) is allowed")
    return url.rstrip("/") + "/"


class CalendarService:
    def __init__(self, base_url: str, http: httpx.Client | None = None, timeout: float = 15.0) -> None:
        self.base = check_url(base_url)
        self.http = http or httpx.Client(timeout=timeout)

    def _get(self, action: str, **params) -> dict:
        try:
            resp = self.http.get(self.base, params={"action": action, **params})
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CalendarError(f"{action}: {type(exc).__name__}") from exc
        if not data.get("success"):
            raise CalendarError(f"{action}: {data.get('message') or data.get('error') or 'service reported failure'}")
        return data

    def raw_day(self, day: date) -> dict:
        """The calendar's own answer for one day, unchanged. This is what snapshots store."""
        return self._get("get_schedule_day", date=day.strftime("%Y%m%d"))

    def change(self, action: str, day: date, start: str, end: str, squad: int, live: bool) -> dict:
        if action not in CHANGE_ACTIONS:
            raise GuardRefused(f"calendar action {action!r} is not allowed")
        return self._get(action, date=day.strftime("%Y%m%d"), shift_start=start, shift_end=end,
                         squad=squad, preview="False" if live else "True")


def day_schedule(raw: dict) -> dict | str:
    """The day as a parsed object if possible, otherwise the raw text."""
    text = raw.get("day_schedule") or ""
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text
