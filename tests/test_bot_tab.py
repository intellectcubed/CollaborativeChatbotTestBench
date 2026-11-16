"""The Bot tab's backend: the week preview, manual chat, and Time Between for bot runs. Replay and calendar are fakes."""

import json
import time
from datetime import date

from fastapi.testclient import TestClient

from driver.agent import scenario as scen
from driver.agent.tools import CONVERSATION_TOOLS, dispatch
from driver.calendar_test import CalendarError
from driver.calendar_week import WeekReader, day_change, line_text, shift_lines, sunday_of
from driver import roster
from driver.api.replay import ReplayError
from driver.lock import gate
from driver.manual import ManualChat
from driver.web.app import create_app
from driver.agent.run import transcript_text
from tests.test_bot import FakeReplay, ctx_for, deps_for

ROSTER = [
    {"member": "Member-2", "sender_id": "222", "name": "Pat Example", "squad": "43"},
    {"member": "Member-3", "sender_id": "333", "name": "Lee Example", "squad": "43"},
    {"member": "Member-7", "sender_id": "777", "name": "Sam Example", "squad": "34"},
]


def raw(shifts) -> dict:
    return {"success": True, "day_schedule": json.dumps({"day": "2026-03-11", "shifts": shifts})}


NIGHT = [{"name": "18:00 - 06:00", "squads": [{"id": 34, "active": True}, {"id": 43, "active": True}]}]
SPLIT = [
    {"name": "18:00 - 19:00", "squads": [{"id": 34, "active": True}, {"id": 43, "active": True}]},
    {"name": "19:00 - 20:00", "squads": [{"id": 34, "active": True}, {"id": 43, "active": False}]},
    {"name": "20:00 - 06:00", "squads": [{"id": 34, "active": True}, {"id": 43, "active": True}]},
]


class WeekCalendar:
    """Calendar stand-in: one schedule for every day, except days set on their own, and days that fail."""

    def __init__(self):
        self.default = NIGHT
        self.days = {}
        self.failing = set()
        self.reads = []

    def raw_day(self, day):
        self.reads.append(day)
        if day in self.failing:
            raise CalendarError("get_schedule_day: service reported failure")
        return raw(self.days.get(day, self.default))


class ChatReplay(FakeReplay):
    def members(self):
        return ROSTER

    def trace(self, trace_id):
        return {"trace_id": trace_id, "status": "done"}

    def outbox(self, trace_id):
        return [{"kind": "ack", "text": "Got it: 43 has no crew 1900-2000.", "channel": "replay", "status": "sent"}]


# ---- reading a day

def test_a_day_reads_as_shift_lines():
    lines = shift_lines(raw(SPLIT))
    assert [line_text(ln) for ln in lines] == [
        "1800–1900 34, 43", "1900–2000 34, 43 (No Crew)", "2000–0600 34, 43"]


def test_the_test_calendars_shape_one_line_per_segment_in_its_own_order():
    # as the test calendar (port 7007) answers: shifts with segments; the night is listed 1800-0000 then 0000-0600
    day = [
        {"name": "Day Shift", "start_time": "06:00", "end_time": "18:00", "tango": 54,
         "segments": [{"start_time": "06:00", "end_time": "18:00", "squads": [{"id": 54, "territories": [34], "active": True}]}]},
        {"name": "18:00 - 00:00 Shift", "start_time": "18:00", "end_time": "00:00", "tango": 43,
         "segments": [{"start_time": "18:00", "end_time": "19:00", "squads": [{"id": 42, "active": True}, {"id": 43, "active": True}]},
                      {"start_time": "19:00", "end_time": "00:00", "squads": [{"id": 42, "active": True}, {"id": 43, "active": False}]}]},
        {"name": "00:00 - 06:00 Shift", "start_time": "00:00", "end_time": "06:00", "tango": 42,
         "segments": [{"start_time": "00:00", "end_time": "06:00", "squads": [{"id": 42, "active": True}]}]},
    ]
    assert [line_text(ln) for ln in shift_lines(raw(day))] == [
        "0600–1800 54", "1800–1900 42, 43", "1900–0000 42, 43 (No Crew)", "0000–0600 42"]


def test_a_shift_with_no_squads_and_other_spellings():
    lines = shift_lines(raw([{"start": "0600", "end": "1800", "squads": []},
                             {"shift": "1800-0600", "squads": [54, {"squad": 61, "status": "No Crew"}]}]))
    assert [line_text(ln) for ln in lines] == ["0600–1800 —", "1800–0600 54, 61 (No Crew)"]


def test_a_day_that_is_not_shifts_reads_as_none():
    assert shift_lines({"success": True, "day_schedule": "closed for training"}) is None
    assert shift_lines(raw([{"squads": [1]}])) is None


def test_the_split_shift_change():
    change = day_change(shift_lines(raw(NIGHT)), shift_lines(raw(SPLIT)))
    assert change == {"added": ["1800–1900 34, 43", "1900–2000 34, 43 (No Crew)", "2000–0600 34, 43"],
                      "removed": ["1800–0600 34, 43"]}
    assert day_change(shift_lines(raw(NIGHT)), shift_lines(raw(NIGHT))) is None


def test_sunday_of():
    assert sunday_of(date(2026, 3, 11)) == date(2026, 3, 8)  # a Wednesday
    assert sunday_of(date(2026, 3, 8)) == date(2026, 3, 8)


# ---- the week

def test_a_week_is_seven_days_from_sunday_and_reports_changes():
    cal = WeekCalendar()
    reader = WeekReader(lambda: cal)
    first = reader.read(date(2026, 3, 11))
    assert first["start"] == "2026-03-08"
    assert [d["date"] for d in first["days"]] == [f"2026-03-{n:02d}" for n in range(8, 15)]
    assert first["changes"] == []  # nothing to compare with yet
    cal.days[date(2026, 3, 11)] = SPLIT
    again = reader.read(date(2026, 3, 8))
    assert [c["date"] for c in again["changes"]] == ["2026-03-11"]
    assert again["changes"][0]["in_week"] is True
    assert reader.read(date(2026, 3, 8))["changes"] == []  # compared with the last read, not the first


def test_recheck_finds_a_change_outside_the_week_shown():
    cal = WeekCalendar()
    reader = WeekReader(lambda: cal)
    reader.read(date(2026, 3, 15))  # viewed the next week once
    reader.read(date(2026, 3, 8))
    cal.days[date(2026, 3, 19)] = SPLIT
    assert reader.read(date(2026, 3, 8))["changes"] == []  # without recheck, only this week is read
    out = reader.read(date(2026, 3, 8), recheck=True)
    assert [(c["date"], c["in_week"]) for c in out["changes"]] == [("2026-03-19", False)]
    assert len(out["days"]) == 7


def test_a_day_that_fails_is_reported_and_the_others_still_show():
    cal = WeekCalendar()
    cal.failing.add(date(2026, 3, 10))
    days = WeekReader(lambda: cal).read(date(2026, 3, 8))["days"]
    failed = [d for d in days if d["error"]]
    assert [d["date"] for d in failed] == ["2026-03-10"]
    assert all(d["lines"] for d in days if not d["error"])


def test_the_week_endpoint():
    http = TestClient(create_app(client=ChatReplay(), poll_s=0.001, timeout_s=2, calendar=WeekCalendar()))
    r = http.get("/api/calendar/week", params={"start": "2026-03-11"})
    assert r.status_code == 200
    body = r.json()
    assert body["start"] == "2026-03-08" and len(body["days"]) == 7
    assert body["days"][0]["lines"][0] == {"start": "1800", "end": "0600",
                                           "squads": [{"id": "34", "no_crew": False}, {"id": "43", "no_crew": False}]}


# ---- manual chat

CSV = """name,sender_id,squad
Pat Example,222,43
Lee Example,333,43
Sam Example,777,34
Alex Example,555,43
"""


def roster_csv(tmp_path):
    path = tmp_path / "roster.csv"
    path.write_text(CSV, encoding="utf-8")
    return path


def chat_for(tmp_path, replay=None, timeout_s=2):
    path = roster_csv(tmp_path)
    return ManualChat(replay or ChatReplay(), lambda: roster.load(path), poll_s=0.001, timeout_s=timeout_s)


def app_for(tmp_path, replay=None):
    return TestClient(create_app(client=replay or ChatReplay(), poll_s=0.001, timeout_s=2, calendar=WeekCalendar(),
                                 roster_path=roster_csv(tmp_path)))


def wait_manual(chat: ManualChat):
    chat.wait_idle(5)
    assert not chat.waiting


def test_the_roster_file_is_sorted_by_name_and_squads_sort_as_numbers(tmp_path):
    rows = roster.load(roster_csv(tmp_path))
    assert [m["name"] for m in rows] == ["Alex Example", "Lee Example", "Pat Example", "Sam Example"]
    assert sorted({"43", "9", "34"}, key=roster.squad_key) == ["9", "34", "43"]
    assert roster.first_of_squad(rows, "43")["name"] == "Alex Example"


def test_a_roster_file_with_a_missing_column_is_refused(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("name,sender_id,squad\nPat Example,,43\n", encoding="utf-8")
    for path in (bad, tmp_path / "missing.csv"):
        try:
            roster.load(path)
        except roster.RosterError:
            continue
        raise AssertionError("not refused")


def test_the_message_goes_with_the_members_sender_id_name_and_squad(tmp_path):
    replay = ChatReplay()
    chat = chat_for(tmp_path, replay)
    chat.send("43", "Lee Example", "no crew from 1900 to 2000 for 43", "2026-03-10T09:00", live=True)
    wait_manual(chat)
    sent = replay.sent[0]
    assert (sent["sender_id"], sent["name"], sent["squad"]) == ("333", "Lee Example", "43")
    assert sent["sent_at"] == "2026-03-10T09:00:00-04:00"  # New York time, daylight saving
    assert sent["live"] is True
    post, reply = chat.status()["events"]
    assert (post["kind"], post["name"], post["squad"], post["source"]) == ("post", "Lee Example", "43", "manual")
    assert (reply["kind"], reply["trace_id"], reply["squad"]) == ("reply", post["trace_id"], "43")


def test_a_squad_alone_sends_as_its_first_member_by_name(tmp_path):
    replay = ChatReplay()
    chat = chat_for(tmp_path, replay)
    chat.send("43", None, "hi", "2026-03-10T09:05", live=False)
    wait_manual(chat)
    assert (replay.sent[0]["sender_id"], replay.sent[0]["name"]) == ("555", "Alex Example")


def test_a_name_outside_the_squad_or_off_the_roster_is_refused(tmp_path):
    chat = chat_for(tmp_path)
    for squad, name in (("43", "Sam Example"), ("43", "Nobody"), ("99", None)):
        try:
            chat.send(squad, name, "hi", "2026-03-10T09:00", live=False)
        except ValueError:
            continue
        raise AssertionError(f"not refused: {squad} {name}")


def test_manual_send_holds_the_run_gate_until_the_reply(tmp_path):
    class Slow(ChatReplay):
        def __init__(self):
            super().__init__()
            self.release = False

        def trace(self, trace_id):
            return {"status": "done" if self.release else "enqueued"}

    replay = Slow()
    chat = chat_for(tmp_path, replay, timeout_s=5)
    chat.send("43", None, "first", "2026-03-10T09:00", live=False)
    assert gate.owner == "manual"
    assert not gate.acquire("batch")
    replay.release = True
    wait_manual(chat)
    assert gate.owner is None


def test_manual_send_is_refused_while_another_run_holds_the_gate(tmp_path):
    gate.acquire("bot")
    r = app_for(tmp_path).post("/api/manual/send", json={"squad": "43", "text": "hi", "sent_at": "2026-03-10T09:00"})
    assert r.status_code == 409


def test_manual_endpoints_send_then_clear(tmp_path):
    http = app_for(tmp_path)
    assert http.post("/api/manual/send", json={"squad": "43", "text": "", "sent_at": "2026-03-10T09:00"}).status_code == 422
    r = http.post("/api/manual/send", json={"squad": "43", "name": "Pat Example", "text": "hi", "sent_at": "2026-03-10T09:00"})
    assert r.status_code == 200
    sent = r.json()  # the send answer carries the trace id, before the reply is read, and what the bubble shows
    assert sent["trace_id"]
    assert (sent["sent_at"], sent["name"], sent["squad"]) == ("2026-03-10T09:00:00-04:00", "Pat Example", "43")
    end = time.monotonic() + 5
    while http.get("/api/manual/status").json()["waiting"] and time.monotonic() < end:
        time.sleep(0.01)
    s = http.get("/api/manual/status").json()
    assert [e["kind"] for e in s["events"]] == ["post", "reply"]
    assert http.post("/api/manual/clear").status_code == 200
    after = http.get("/api/manual/status").json()
    assert after["events"] == [] and after["session"] == s["session"] + 1


def test_the_roster_endpoint_gives_names_from_the_file_and_member_ids_from_the_chatbot(tmp_path):
    rows = app_for(tmp_path).get("/api/roster").json()
    assert [r["name"] for r in rows] == ["Alex Example", "Lee Example", "Pat Example", "Sam Example"]
    by_name = {r["name"]: r for r in rows}
    assert by_name["Pat Example"] == {"name": "Pat Example", "sender_id": "222", "squad": "43", "member": "Member-2"}
    assert by_name["Alex Example"]["member"] is None  # not on the chatbot's roster


def test_the_roster_endpoint_works_without_the_replay_tool(tmp_path):
    class Down(ChatReplay):
        def members(self):
            raise ReplayError("replay tool not reachable: ConnectError")

    rows = app_for(tmp_path, Down()).get("/api/roster").json()
    assert len(rows) == 4 and all(r["member"] is None for r in rows)


# ---- Time Between in bot runs

def post(ctx, deps, sent_at, text="x"):
    return dispatch(ctx, deps, CONVERSATION_TOOLS, "post_message",
                    {"member": "Member-2", "text": text, "sent_at": sent_at, "setting": "none"})


def test_time_between_spaces_posts_on_the_same_day(tmp_path):
    ctx, deps = ctx_for(tmp_path, time_between_min=5, max_messages=5), deps_for()
    post(ctx, deps, "2026-11-04T18:00:00-05:00")
    post(ctx, deps, "2026-11-04T18:47:00-05:00")  # the bot's own time is replaced on the same day
    post(ctx, deps, "2026-11-05T09:00:00-05:00")  # a later day starts from the bot's time
    post(ctx, deps, "2026-11-05T09:30:00-05:00")
    times = [p["sent_at"] for p in deps.replay.sent]
    assert times == ["2026-11-04T18:00:00-05:00", "2026-11-04T18:05:00-05:00",
                     "2026-11-05T09:00:00-05:00", "2026-11-05T09:05:00-05:00"]


def test_no_time_between_keeps_the_bots_times(tmp_path):
    ctx, deps = ctx_for(tmp_path, max_messages=5), deps_for()
    post(ctx, deps, "2026-11-04T18:00:00-05:00")
    post(ctx, deps, "2026-11-04T18:47:00-05:00")
    assert deps.replay.sent[1]["sent_at"] == "2026-11-04T18:47:00-05:00"


def test_time_between_is_checked_in_the_goal():
    g = scen.default_goal()
    assert g["time_between_min"] == 5
    for bad in (-1, "5", True):
        g["time_between_min"] = bad
        assert any(e.startswith("time between") for e in scen.validate(g))


# ---- a finished turn with no message still shows its reply title

class Silent(ChatReplay):
    """The chatbot acts (or not) and says nothing."""

    def outbox(self, trace_id):
        return []


class NotTaken(ChatReplay):
    def send(self, *a, **k):
        super().send(*a, **k)
        return {"status": "ignored", "trace_id": "t-ignored"}


def test_a_manual_turn_with_no_message_ends_with_a_title_only_reply(tmp_path):
    chat = chat_for(tmp_path, Silent())
    chat.send("43", None, "thanks all", "2026-03-10T09:00", live=False)
    wait_manual(chat)
    post, done = chat.status()["events"]
    assert done["kind"] == "reply" and done["no_message"] is True and done["text"] == ""
    assert (done["trace_id"], done["trace_status"], done["squad"]) == (post["trace_id"], "done", "43")


def test_a_message_the_chatbot_did_not_take_also_ends_with_a_title(tmp_path):
    chat = chat_for(tmp_path, NotTaken())
    chat.send("43", None, "hi", "2026-03-10T09:00", live=False)
    wait_manual(chat)
    post, done = chat.status()["events"]
    assert post["trace_id"] == "t-ignored"
    assert (done["no_message"], done["trace_status"]) == (True, "ignored")


def test_a_bot_post_with_no_reply_message_ends_with_a_title(tmp_path):
    class SilentBot(FakeReplay):
        def trace(self, trace_id):
            return {"status": "done"}

        def outbox(self, trace_id):
            return []

    ctx, deps = ctx_for(tmp_path, max_messages=5), deps_for(replay=SilentBot())
    out = dispatch(ctx, deps, CONVERSATION_TOOLS, "post_message",
                   {"member": "Member-2", "text": "ok", "sent_at": "2026-11-04T18:00:00-05:00"})
    assert out["replies"] == []
    reply = [e for e in ctx.events if e["kind"] == "reply"]
    assert len(reply) == 1 and reply[0]["no_message"] is True and reply[0]["trace_status"] == "done"
    assert "with no message" in transcript_text(ctx)  # the judge's transcript reads it too


# ---- the chatbot's model tokens, from the trace, on the reply

STEPS = [{"name": "llm:classify", "output": {"input_tokens": 1200, "output_tokens": 40}},
         {"name": "pii", "output": {}},
         {"name": "llm:reply", "output": {"input_tokens": 800, "output_tokens": 160}}]
TOKENS = {"input": 2000, "output": 200, "calls": 2}


class Counted(ChatReplay):
    def trace(self, trace_id):
        return {"trace_id": trace_id, "status": "done", "steps": STEPS}

    def outbox(self, trace_id):
        return [{"kind": "clarify", "text": "Which night?", "channel": "replay", "status": "sent"},
                {"kind": "ack", "text": "Noted.", "channel": "replay", "status": "sent"}]


def test_a_manual_reply_carries_the_tokens_once(tmp_path):
    chat = chat_for(tmp_path, Counted())
    chat.send("43", None, "no crew friday", "2026-03-10T09:00", live=False)
    wait_manual(chat)
    first, second = [e for e in chat.status()["events"] if e["kind"] == "reply"]
    assert first["tokens"] == TOKENS and second["tokens"] is None


def test_a_finish_with_no_message_carries_the_tokens(tmp_path):
    class CountedSilent(Counted):
        def outbox(self, trace_id):
            return []

    chat = chat_for(tmp_path, CountedSilent())
    chat.send("43", None, "thanks", "2026-03-10T09:00", live=False)
    wait_manual(chat)
    done = chat.status()["events"][-1]
    assert done["no_message"] is True and done["tokens"] == TOKENS


def test_a_bot_reply_carries_the_tokens_but_the_tester_does_not_see_them(tmp_path):
    class CountedBot(FakeReplay):
        def trace(self, trace_id):
            return {"status": "done", "steps": STEPS}

        def outbox(self, trace_id):
            return [{"kind": "ack", "text": "Noted.", "channel": "replay", "status": "sent"}]

    ctx, deps = ctx_for(tmp_path, max_messages=5), deps_for(replay=CountedBot())
    out = dispatch(ctx, deps, CONVERSATION_TOOLS, "post_message",
                   {"member": "Member-2", "text": "ok", "sent_at": "2026-11-04T18:00:00-05:00"})
    assert "tokens" not in json.dumps(out)
    assert [e["tokens"] for e in ctx.events if e["kind"] == "reply"] == [TOKENS]
