"""The web API: a fresh page closes the batch, and a close is refused while a run is going."""

import json

from fastapi.testclient import TestClient

from driver.web.app import create_app

LINE = '{"id": "a", "created_at": "2026-03-14T13:00:00-04:00", "member": "Member-7", "text": "34 is good Saturday"}'


class Client:
    """Replay stand-in: every trace stays busy, so a run keeps going until it is stopped."""

    def members(self):
        return [{"member": "Member-7", "sender_id": "111", "name": "Pat", "squad": "34"}]

    def send(self, *a, **k):
        return {"status": "enqueued", "trace_id": "t1"}

    def trace(self, trace_id):
        return {"status": "enqueued"}

    def outbox(self, trace_id):
        return []


def open_batch(http):
    r = http.post("/api/batch/open", json={"name": "march", "content": LINE})
    assert r.status_code == 200


def test_close_clears_an_idle_batch():
    http = TestClient(create_app(client=Client(), poll_s=0.001, timeout_s=5))
    open_batch(http)
    assert http.get("/api/batch").json()["name"] == "march"
    assert http.post("/api/batch/close").status_code == 200
    assert http.get("/api/batch").json()["name"] is None


def test_close_is_refused_while_a_run_is_going():
    http = TestClient(create_app(client=Client(), poll_s=0.001, timeout_s=5))
    open_batch(http)
    assert http.post("/api/batch/run", json={"mode": "all"}).status_code == 200
    assert http.post("/api/batch/close").status_code == 409
    assert http.get("/api/batch").json()["name"] == "march"
    http.post("/api/batch/stop")
