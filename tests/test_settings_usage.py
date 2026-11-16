"""The global Live Calendar setting, the token totals and the budget, and the page itself."""

from fastapi.testclient import TestClient

from driver.llm import Budget
from driver.web.app import create_app
from tests.test_web import LINE, Client


def test_live_calendar_starts_off_and_is_one_setting(tmp_path):
    http = TestClient(create_app(client=Client(), poll_s=0.01, ui_dist=tmp_path))
    assert http.get("/api/settings").json() == {"live": False}
    assert http.put("/api/settings", json={"live": True}).json() == {"live": True}
    assert http.get("/api/settings").json() == {"live": True}


def test_live_calendar_cannot_change_while_a_batch_runs(tmp_path):
    http = TestClient(create_app(client=Client(), poll_s=0.01, ui_dist=tmp_path))
    http.post("/api/batch/open", json={"name": "march", "content": LINE})
    http.post("/api/batch/run", json={"mode": "all"})
    assert http.put("/api/settings", json={"live": True}).status_code == 409
    http.post("/api/batch/stop")


def test_a_batch_run_uses_the_global_setting_not_the_request(tmp_path):
    client = Client()
    seen = []
    client.send = lambda sender_id, text, sent_at, live_calendar: seen.append(live_calendar) or {"status": "enqueued", "trace_id": "t1"}
    http = TestClient(create_app(client=client, poll_s=0.01, ui_dist=tmp_path))
    http.put("/api/settings", json={"live": True})
    http.post("/api/batch/open", json={"name": "march", "content": LINE})
    http.post("/api/batch/run", json={"mode": "current"})
    http.post("/api/batch/stop")
    assert seen and all(seen)


def test_budget_tokens_are_counted_and_reset_without_touching_the_money(tmp_path):
    b = Budget(5.0, tmp_path / "spend.json")
    b.add(0.25, tokens_in=1200, tokens_out=300)
    b.add(0.10, tokens_in=50, tokens_out=20)
    b.reset_tokens()
    assert (b.tokens_in, b.tokens_out) == (0, 0)
    assert round(b.spent, 2) == 0.35  # the cap still counts what was spent
    again = Budget(5.0, tmp_path / "spend.json")  # saved to the file
    assert round(again.spent, 2) == 0.35 and (again.tokens_in, again.tokens_out) == (0, 0)


def test_usage_endpoint_without_a_key_says_so(tmp_path):
    http = TestClient(create_app(client=Client(), poll_s=0.01, ui_dist=tmp_path))
    body = http.get("/api/usage").json()
    assert body["key_set"] is False and body["cap_usd"] is None
    assert http.post("/api/usage/reset").status_code == 200


def test_the_page_says_when_it_is_not_built(tmp_path):
    http = TestClient(create_app(client=Client(), poll_s=0.01, ui_dist=tmp_path))
    r = http.get("/")
    assert r.status_code == 503 and "not built" in r.text
