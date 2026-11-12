"""The bot: guard, tools, the run order, limits, and the run lock. The model, the replay tool and the calendar are fakes."""

import json
import time
from datetime import date
from pathlib import Path

import pytest

from driver.agent import scenario as scen
from driver.agent.run import BotManager, RunBusy, transcript_text
from driver.agent.run_state import RunContext, real_name_map
from driver.agent.tools import Deps, dispatch, CONVERSATION_TOOLS, JUDGE_POST_TOOLS
from driver.batches.files import parse
from driver.batches.runner import Runner
from driver.calendar_test import GuardRefused, CalendarService
from driver.llm import Budget, BudgetExceeded, PriceMissing
from driver.lock import gate

MEMBERS = [
    {"member": "Member-2", "sender_id": "222", "name": "Pat Example", "squad": "54"},
    {"member": "Member-7", "sender_id": "777", "name": "Sam Example", "squad": "34"},
]
TESTER, JUDGE = "claude-sonnet-5-5", "claude-opus-5-5"


# ---- fakes

class FakeReplay:
    def __init__(self, status="done"):
        self.sent = []
        self.status = status

    def members(self):
        return MEMBERS

    def send(self, sender_id, text, sent_at, live_calendar):
        self.sent.append({"sender_id": sender_id, "text": text, "sent_at": sent_at, "live": live_calendar})
        return {"status": "enqueued", "trace_id": f"t{len(self.sent)}"}

    def trace(self, trace_id):
        return {"trace_id": trace_id, "status": self.status, "steps": [{"name": "reply", "output": {"lines": ["x"]}}]}

    def outbox(self, trace_id):
        return [{"kind": "clarify", "text": "Which night?", "channel": "replay", "status": "sent", "error": None}]


class FakeCalendar:
    def __init__(self):
        self.changed = False
        self.calls = []

    def raw_day(self, day):
        shifts = [{"name": "18:00 - 06:00", "squads": [{"id": 54, "active": not self.changed}]}]
        return {"success": True, "day_schedule": json.dumps({"day": day.isoformat(), "shifts": shifts})}

    def change(self, action, day, start, end, squad, live):
        self.calls.append({"action": action, "live": live, "squad": squad})
        if live:
            self.changed = True
        return {"changeId": "c1"}


class FakeLlm:
    """Scripted: each model gets a list of responses. A response is a list of content blocks."""

    def __init__(self, budget: Budget, scripts: dict, cost: float = 0.01, prices: bool = True):
        self.budget = budget
        self.scripts = {k: list(v) for k, v in scripts.items()}
        self.cost = cost
        self.prices = prices
        self.calls = []

    def _priced(self, model):
        return self.prices

    def call(self, *, model, system, messages, tools, max_tokens, temperature):
        self.budget.check()
        self.calls.append({"model": model, "tools": [t["name"] for t in tools]})
        self.budget.add(self.cost)
        queue = self.scripts.get(model) or []
        if not queue:
            raise AssertionError(f"no scripted response left for {model}")
        return {"content": queue.pop(0), "stop_reason": "tool_use", "usage": {}, "cost": self.cost}


def use(name, inp, n=[0]):
    n[0] += 1
    return {"type": "tool_use", "id": f"u{n[0]}", "name": name, "input": inp}


def goal(**over) -> dict:
    base = scen.default_goal()
    base.update({
        "name": "no_crew_multi_day",
        "goal": "Tell the chatbot your squad will have no crew Friday night. Answer its questions.",
        "stop_condition": "Stop when the chatbot has the hours, or after four exchanges.",
        "expected_results": ["Squad 54 has no crew Friday 1800 to 0600 after the run."],
        "my_squad": "Member-2",
        "personas": ["Member-2"],
        "window": {"start": "2026-11-01", "end": "2026-11-30"},
        "gate_date": "2026-11-06",
    })
    base.update(over)
    return base


def wait_done(manager: BotManager, timeout: float = 10.0) -> None:
    end = time.monotonic() + timeout
    while manager.state == "running" and time.monotonic() < end:
        time.sleep(0.01)
    assert manager.state != "running", "run did not finish"


def manager_for(tmp_path: Path, scripts: dict, replay=None, calendar=None, budget_cap=10.0, cost=0.01, prices=True):
    budget = Budget(budget_cap, tmp_path / "spend.json")
    llm = FakeLlm(budget, scripts, cost=cost, prices=prices)
    cal = calendar or FakeCalendar()
    m = BotManager(replay=replay or FakeReplay(), llm=llm, scenarios_dir=tmp_path / "scenarios",
                   runs_dir=tmp_path / "runs", poll_s=0.001, calendar=cal)
    return m, llm


def happy_scripts():
    tester = [
        [use("submit_plan", {"plan": "Remove squad 54 for Friday night, 1800 to 0600."})],
        [use("post_message", {"member": "Member-2", "text": "54 won't have a crew Friday night",
                              "sent_at": "2026-11-04T18:00:00-05:00", "setting": "wait"})],
        [use("post_message", {"member": "Member-2", "text": "Whole night", "sent_at": "2026-11-04T18:05:00-05:00"})],
        [use("finish", {"passed": True, "reason": "the chatbot asked and got the hours"})],
    ]
    judge = [
        [use("take_snapshot", {"label": "before", "dates": ["2026-11-06"]})],
        [use("submit_checks", {"checks": [{"id": "c1", "check": "Friday 1800-0600 shows squad 54 with no crew",
                                           "look_at": "after snapshot for 2026-11-06"}]})],
        [use("submit_verdicts", {"verdicts": [{"id": "c1", "verdict": "pass", "evidence": "after: active false",
                                               "reason": "the diff shows squad 54 inactive"}], "summary": "1 of 1 passed"})],
    ]
    return {TESTER: tester, JUDGE: judge}


# ---- the calendar guard

@pytest.mark.parametrize("url", ["http://localhost:8007", "http://localhost:8007/", "http://example.com:7007",
                                 "https://calendar.example.org"])
def test_guard_refuses_production_and_anything_else(url):
    with pytest.raises(GuardRefused):
        CalendarService(url)


def test_guard_allows_the_test_calendar():
    assert CalendarService("http://localhost:7007").base == "http://localhost:7007/"
    assert CalendarService("http://host.docker.internal:7007").base == "http://host.docker.internal:7007/"


def test_guard_refuses_a_change_action_it_does_not_know():
    cal = CalendarService("http://localhost:7007")
    with pytest.raises(GuardRefused):
        cal.change("rollback", date(2026, 11, 6), "1800", "0600", 54, live=False)


# ---- names and scrubbing

def test_real_names_become_pseudonyms_before_text_reaches_a_model(tmp_path):
    ctx = RunContext(folder=tmp_path / "r", personas={"Member-2": "54"}, window_start=date(2026, 11, 1),
                     window_end=date(2026, 11, 30), gate=date(2026, 11, 6), live=False, setup_allowed=False,
                     posting_allowed={"wait"}, max_messages=5, max_cost_usd=1, reply_timeout_s=1,
                     real_names=real_name_map(MEMBERS))
    assert "Pat" not in ctx.scrub("Pat Example says hi") and "Member-2" in ctx.scrub("Pat Example says hi")


# ---- tools

def ctx_for(tmp_path, **over):
    base = dict(folder=tmp_path / "r", personas={"Member-2": "54"}, window_start=date(2026, 11, 1),
                window_end=date(2026, 11, 30), gate=date(2026, 11, 6), live=False, setup_allowed=False,
                posting_allowed={"wait", "none"}, max_messages=2, max_cost_usd=1, reply_timeout_s=1,
                real_names={})
    base.update(over)
    return RunContext(**base)


def deps_for(replay=None, calendar=None):
    return Deps(replay=replay or FakeReplay(), calendar=calendar or FakeCalendar(),
                sender_ids={"Member-2": "222", "Member-7": "777"}, poll_s=0.001)


def test_a_post_outside_the_window_is_refused(tmp_path):
    ctx, deps = ctx_for(tmp_path), deps_for()
    out = dispatch(ctx, deps, CONVERSATION_TOOLS, "post_message",
                   {"member": "Member-2", "text": "x", "sent_at": "2026-12-01T18:00:00-05:00"})
    assert "outside the window" in out["error"] and deps.replay.sent == []


def test_a_persona_not_in_the_run_is_refused(tmp_path):
    ctx, deps = ctx_for(tmp_path), deps_for()
    out = dispatch(ctx, deps, CONVERSATION_TOOLS, "post_message",
                   {"member": "Member-7", "text": "x", "sent_at": "2026-11-04T18:00:00-05:00"})
    assert "not a persona" in out["error"] and deps.replay.sent == []


def test_a_posting_setting_not_allowed_is_refused(tmp_path):
    ctx, deps = ctx_for(tmp_path, posting_allowed={"wait"}), deps_for()
    out = dispatch(ctx, deps, CONVERSATION_TOOLS, "post_message",
                   {"member": "Member-2", "text": "x", "sent_at": "2026-11-04T18:00:00-05:00", "setting": "none"})
    assert "not allowed" in out["error"]


def test_a_post_after_the_gate_date_goes_through_with_a_warning(tmp_path):
    ctx, deps = ctx_for(tmp_path), deps_for()
    out = dispatch(ctx, deps, CONVERSATION_TOOLS, "post_message",
                   {"member": "Member-2", "text": "Friday night", "sent_at": "2026-11-07T10:00:00-05:00", "setting": "none"})
    assert out["warning"].startswith("sent_at is after the gate date") and len(deps.replay.sent) == 1


def test_setup_changes_are_refused_unless_allowed(tmp_path):
    ctx, deps = ctx_for(tmp_path, setup_allowed=False), deps_for()
    out = dispatch(ctx, deps, CONVERSATION_TOOLS, "set_calendar",
                   {"action": "noCrew", "date": "2026-11-06", "start": "1800", "end": "0600", "squad": 54})
    assert "not allowed" in out["error"] and deps.calendar.calls == []


def test_a_setup_change_in_a_preview_run_does_not_change_the_calendar(tmp_path):
    cal = FakeCalendar()
    ctx, deps = ctx_for(tmp_path, setup_allowed=True, live=False), deps_for(calendar=cal)
    dispatch(ctx, deps, CONVERSATION_TOOLS, "set_calendar",
             {"action": "noCrew", "date": "2026-11-06", "start": "1800", "end": "0600", "squad": 54})
    assert cal.calls[0]["live"] is False and cal.changed is False


def test_a_live_setup_change_is_made_on_the_test_calendar(tmp_path):
    cal = FakeCalendar()
    ctx, deps = ctx_for(tmp_path, setup_allowed=True, live=True), deps_for(calendar=cal)
    dispatch(ctx, deps, CONVERSATION_TOOLS, "set_calendar",
             {"action": "noCrew", "date": "2026-11-06", "start": "1800", "end": "0600", "squad": 54})
    assert cal.changed is True
    assert (ctx.folder / "snapshots" / "setup1-before_2026-11-06.json").exists()
    assert (ctx.folder / "snapshots" / "setup1-after_2026-11-06.json").exists()


def test_a_verdict_without_evidence_is_unclear(tmp_path):
    ctx, deps = ctx_for(tmp_path), deps_for()
    ctx.checks = [{"id": "c1", "check": "x", "look_at": ""}]
    dispatch(ctx, deps, JUDGE_POST_TOOLS, "submit_verdicts",
             {"verdicts": [{"id": "c1", "verdict": "pass", "evidence": "", "reason": "looks fine"}], "summary": "s"})
    assert ctx.verdicts[0]["verdict"] == "unclear"


def test_verdicts_must_cover_every_check(tmp_path):
    ctx, deps = ctx_for(tmp_path), deps_for()
    ctx.checks = [{"id": "c1", "check": "x", "look_at": ""}, {"id": "c2", "check": "y", "look_at": ""}]
    out = dispatch(ctx, deps, JUDGE_POST_TOOLS, "submit_verdicts",
                   {"verdicts": [{"id": "c1", "verdict": "pass", "evidence": "e", "reason": "r"}], "summary": "s"})
    assert "exactly one verdict" in out["error"] and ctx.verdicts == []


# ---- a whole run

def test_a_run_plans_then_judge_commits_then_converses_then_judges(tmp_path):
    m, llm = manager_for(tmp_path, happy_scripts())
    m.start(goal())
    wait_done(m)
    assert m.state == "done", m.reason
    kinds = [e["kind"] for e in m.ctx.events]
    assert kinds.index("plan") < kinds.index("checks") < kinds.index("post")
    assert kinds.index("snapshot") < kinds.index("post")  # the before image comes before any post
    assert kinds.index("post") < kinds.index("finish") < kinds.index("verdict")
    assert m.ctx.verdicts[0]["verdict"] == "pass"
    assert (m.ctx.folder / "snapshots" / "before_2026-11-06.json").exists()
    assert (m.ctx.folder / "snapshots" / "after_2026-11-06.json").exists()
    assert (m.ctx.folder / "report.md").exists() and (m.ctx.folder / "summary.json").exists()


def test_the_tester_never_sees_the_expected_results(tmp_path):
    m, llm = manager_for(tmp_path, happy_scripts())
    m.start(goal())
    wait_done(m)
    tester_system = m._tester_system(goal(), m.ctx)
    assert "Squad 54 has no crew Friday" not in tester_system  # the expected results are not in the tester's prompt


def test_the_tester_is_limited_to_the_conversation_tools_after_the_plan(tmp_path):
    m, llm = manager_for(tmp_path, happy_scripts())
    m.start(goal())
    wait_done(m)
    names = [c["tools"] for c in llm.calls if c["model"] == TESTER]
    assert names[0] == ["submit_plan"] and "post_message" in names[1]


def test_a_run_stops_when_the_cost_limit_is_reached(tmp_path):
    m, _ = manager_for(tmp_path, happy_scripts(), cost=0.01)
    g = goal(limits={"max_messages": 12, "max_turns": 30, "reply_timeout_s": 1, "max_cost_usd": 0.005})
    m.start(g)
    wait_done(m)
    assert m.state == "stopped" and "cost limit" in m.reason


def test_the_global_budget_refuses_a_start(tmp_path):
    m, _ = manager_for(tmp_path, happy_scripts(), budget_cap=0.0)
    with pytest.raises(BudgetExceeded):
        m.start(goal())


def test_a_model_without_a_price_refuses_a_start(tmp_path):
    m, _ = manager_for(tmp_path, happy_scripts(), prices=False)
    with pytest.raises(PriceMissing):
        m.start(goal())


def test_a_persona_not_on_the_roster_refuses_a_start(tmp_path):
    m, _ = manager_for(tmp_path, happy_scripts())
    with pytest.raises(ValueError):
        m.start(goal(personas=["Member-2", "Member-99"], my_squad="Member-2"))


# ---- the shared run lock

def test_a_batch_run_cannot_start_while_a_bot_run_holds_the_gate():
    gate.acquire("bot")
    runner = Runner(FakeReplay(), parse('{"id": "a", "created_at": "2026-03-14T13:00:00-04:00", "member": "Member-2", "text": "x"}'),
                    {"Member-2": {"sender_id": "222", "name": "P", "squad": "54"}}, poll_s=0.001)
    with pytest.raises(RuntimeError, match="another run is going"):
        runner.start("all")


def test_a_bot_run_cannot_start_while_a_batch_run_holds_the_gate(tmp_path):
    gate.acquire("batch")
    m, _ = manager_for(tmp_path, happy_scripts())
    with pytest.raises(RunBusy):
        m.start(goal())
    gate.release("batch")


def test_the_gate_is_released_when_a_bot_run_ends(tmp_path):
    m, _ = manager_for(tmp_path, happy_scripts())
    m.start(goal())
    wait_done(m)
    assert gate.owner is None


# ---- errors from the model are visible, with the API's own message

def test_a_refused_model_call_says_why(tmp_path):
    import httpx
    from driver.llm import LlmClient, LlmError, Budget
    from driver.llm import LlmError as _E

    def handler(request):
        return httpx.Response(400, json={"type": "error", "error": {"type": "invalid_request_error",
                                                                     "message": "`temperature` is deprecated for this model."}})
    client = LlmClient("test-key", {"m": {"input_per_mtok": 1, "output_per_mtok": 1}},
                       Budget(10, tmp_path / "s.json"), http=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(LlmError) as exc:
        client.call(model="m", system="s", messages=[], tools=[], max_tokens=10, temperature=None)
    assert "HTTP 400" in str(exc.value) and "deprecated" in str(exc.value)
    assert "test-key" not in str(exc.value)


def test_the_page_shows_the_real_member_and_id_but_the_model_never_sees_them(tmp_path):
    m, llm = manager_for(tmp_path, happy_scripts())
    m.start(goal())
    wait_done(m)
    posts = [e for e in m.ctx.events if e["kind"] == "post"]
    assert posts[0]["name"] == "Pat Example" and posts[0]["sender_id"] == "222"  # what GroupMe would show
    text_for_judge = transcript_text(m.ctx)
    assert "Pat Example" not in text_for_judge and "222" not in text_for_judge  # pseudonyms only
    assert "Member-2" in text_for_judge
