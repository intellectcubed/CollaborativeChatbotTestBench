"""Client for the replay tool's HTTP API. The contract is in docs/design/client-rules.md."""

import httpx

WORKING = {"received", "enqueued"}  # trace statuses that mean "still being processed"


class ReplayError(Exception):
    """The replay tool refused a request, or could not be reached."""


class ReplayClient:
    def __init__(self, base_url: str, http: httpx.Client | None = None, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self._http = http or httpx.Client(base_url=self.base_url, timeout=timeout)

    def _get(self, path: str):
        try:
            r = self._http.get(path)
        except httpx.HTTPError as exc:
            raise ReplayError(f"replay tool not reachable: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise ReplayError(f"GET {path}: {r.status_code}")
        return r.json()

    def members(self) -> list[dict]:
        """Roster: sender_id, member (pseudonym), squad, name. Real names: local use only."""
        return self._get("/api/members")

    def send(self, sender_id: str, text: str, sent_at: str, live_calendar: bool) -> dict:
        """Post one message. Returns {"status": ..., "trace_id": ...} at once, before the chatbot has replied."""
        body = {"sender_id": sender_id, "text": text, "sent_at": sent_at, "live_calendar": live_calendar}
        try:
            r = self._http.post("/api/send", json=body)
        except httpx.HTTPError as exc:
            raise ReplayError(f"replay tool not reachable: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            detail = r.json().get("detail", "") if r.headers.get("content-type", "").startswith("application/json") else ""
            raise ReplayError(f"send refused ({r.status_code}) {detail}".strip())
        return r.json()

    def trace(self, trace_id: str) -> dict:
        return self._get(f"/api/traces/{trace_id}")

    def outbox(self, trace_id: str) -> list[dict]:
        return self._get(f"/api/traces/{trace_id}/outbox")
