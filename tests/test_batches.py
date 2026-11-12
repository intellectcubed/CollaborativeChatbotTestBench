import threading
import time
from datetime import date

import pytest

from driver.api.replay import ReplayError
from driver.batches.files import BatchError, parse
from driver.batches.runner import Runner

HEADER = '{"kind": "batch", "name": "march", "description": "two messages"}'
A = '{"id": "a", "created_at": "2026-03-14T13:00:00-04:00", "member": "Member-7", "text": "34 is good Saturday"}'
B = '{"id": "b", "created_at": "2026-03-15T09:30:00", "member": "Member-8", "text": "54 is short Sunday"}'  # no offset: New York
MEMBERS = {"Member-7": {"sender_id": "111", "name": "Pat Example", "squad": "34"},
           "Member-8": {"sender_id": "222", "name": "Sam Example", "squad": "54"}}


class FakeClient:
    """A stand-in for the replay tool. Each trace is 'enqueued' for `busy` polls, then 'done'."""

    def __init__(self, busy=0, send_status="enqueued", outbox=None):
        self.busy, self.send_status, self._outbox = busy, send_status, outbox or []
        self.sent = []  # (sender_id, text, sent_at, live)
        self._polls = {}
        self._n = 0

    def members(self):
        return [{"member": k, **v} for k, v in MEMBERS.items()]

    def send(self, sender_id, text, sent_at, live_calendar):
        self.sent.append((sender_id, text, sent_at, live_calendar))
        self._n += 1
        trace_id = f"t{self._n}"
        self._polls[trace_id] = 0
        return {"status": self.send_status, "trace_id": trace_id}

    def trace(self, trace_id):
        self._polls[trace_id] += 1
        return {"status": "enqueued" if self._polls[trace_id] <= self.busy else "done"}

    def outbox(self, trace_id):
        return self._outbox


def runner_for(content, client=None, timeout_s=5.0):
    return Runner(client or FakeClient(), parse(content), MEMBERS, poll_s=0.001, timeout_s=timeout_s)


# ---- files

def test_parse_reads_the_header_and_treats_a_naive_time_as_new_york():
    b = parse("\n".join([HEADER, A, B]))
    assert (b.name, b.description) == ("march", "two messages")
    assert [m.id for m in b.messages] == ["a", "b"]
    assert b.messages[1].created_at.isoformat() == "2026-03-15T09:30:00-04:00"


def test_parse_reports_every_problem_and_opens_nothing():
    bad = "\n".join([A, "not json", '{"id": "c", "member": "Member-7", "text": "x"}', A])
    with pytest.raises(BatchError) as err:
        parse(bad)
    assert err.value.errors == [
        "line 2: not JSON (Expecting value)",
        "line 3: missing created_at",
        "line 4: duplicate id a",
    ]


# ---- runner

def test_run_all_sends_checked_lines_in_order_with_their_sender_ids_and_times():
    client = FakeClient(outbox=[{"kind": "clarify", "text": "Which hours?", "channel": "replay", "status": "sent"}])
    r = runner_for("\n".join([HEADER, A, B]), client)
    r.start("all", live=False)
    r.wait_idle()
    assert [s[0] for s in client.sent] == ["111", "222"]
    assert client.sent[1][2] == "2026-03-15T09:30:00-04:00"
    assert client.sent[0][3] is False  # live calendar off
    snap = r.snapshot()
    assert [ln["status"] for ln in snap["lines"]] == ["done", "done"]
    assert snap["lines"][0]["replies"][0]["text"] == "Which hours?"


def test_an_unchecked_line_is_skipped():
    client = FakeClient()
    r = runner_for("\n".join([A, B]), client)
    r.set_checked(0, False)
    r.start("all")
    r.wait_idle()
    assert [s[1] for s in client.sent] == ["54 is short Sunday"]


def test_a_range_runs_only_the_days_in_it():
    client = FakeClient()
    r = runner_for("\n".join([A, B]), client)
    r.start("range", start=date(2026, 3, 15), end=date(2026, 3, 15))
    r.wait_idle()
    assert [s[1] for s in client.sent] == ["54 is short Sunday"]


def test_run_sends_only_the_selected_row_and_selects_the_next_one():
    client = FakeClient()
    r = runner_for("\n".join([A, B]), client)
    assert r.snapshot()["current"] == 0
    r.start_current()
    r.wait_idle()
    assert len(client.sent) == 1 and client.sent[0][1] == "34 is good Saturday"
    snap = r.snapshot()
    assert [ln["status"] for ln in snap["lines"]] == ["done", "pending"]
    assert snap["current"] == 1  # selected, not run


def test_a_message_the_chatbot_never_sees_is_marked_not_processed():
    r = runner_for(A, FakeClient(send_status="dropped"))
    r.start("all")
    r.wait_idle()
    ln = r.snapshot()["lines"][0]
    assert (ln["status"], ln["trace_status"]) == ("not_processed", "dropped")


def test_an_unknown_member_fails_that_line_only():
    unknown = A.replace("Member-7", "Member-99")
    client = FakeClient()
    r = runner_for("\n".join([unknown, B]), client)
    r.start("all")
    r.wait_idle()
    statuses = [ln["status"] for ln in r.snapshot()["lines"]]
    assert statuses == ["failed", "done"]
    assert "not on the roster" in r.snapshot()["lines"][0]["error"]


def test_a_send_refused_by_the_replay_tool_fails_the_line():
    class Refusing(FakeClient):
        def send(self, *a, **k):
            raise ReplayError("send refused (404)")
    r = runner_for(A, Refusing())
    r.start("all")
    r.wait_idle()
    assert r.snapshot()["lines"][0]["error"] == "send refused (404)"


def test_a_trace_that_never_finishes_times_out_and_is_not_called_a_failure():
    r = runner_for(A, FakeClient(busy=10**6), timeout_s=0.05)
    r.start("all")
    r.wait_idle()
    assert r.snapshot()["lines"][0]["status"] == "timeout"


def test_pause_holds_the_next_message_until_resume():
    client = FakeClient()
    r = runner_for("\n".join([A, B]), client)
    r.pause()  # not running yet: no effect
    r.start("all")
    r.pause()
    time.sleep(0.05)
    sent_while_paused = len(client.sent)
    assert r.snapshot()["state"] == "paused"
    assert sent_while_paused <= 1  # at most the message already in progress
    r.resume()
    r.wait_idle()
    assert len(client.sent) == 2


def test_stop_finishes_the_message_in_progress_and_leaves_the_rest_pending():
    class Gated(FakeClient):
        """Holds the first send open, so the test can press Stop while that message is in progress."""
        def __init__(self):
            super().__init__()
            self.started, self.gate = threading.Event(), threading.Event()

        def send(self, *a, **k):
            if not self.sent:
                self.started.set()
                self.gate.wait(5)
            return super().send(*a, **k)

    client = Gated()
    r = runner_for("\n".join([A, B]), client)
    r.start("all")
    assert client.started.wait(5)
    r.stop()
    client.gate.set()
    r.wait_idle()
    assert len(client.sent) == 1  # the message in progress was finished, the next one was not sent
    assert [ln["status"] for ln in r.snapshot()["lines"]] == ["done", "pending"]
    assert r.snapshot()["state"] == "idle"


def test_only_one_run_at_a_time():
    r = runner_for("\n".join([A, B]), FakeClient(busy=50))
    r.start("all")
    with pytest.raises(RuntimeError):
        r.start("all")
    r.stop()
    r.wait_idle()


def test_reset_makes_finished_lines_runnable_again():
    client = FakeClient()
    r = runner_for(A, client)
    r.start("all")
    r.wait_idle()
    r.reset()
    r.start("all")
    r.wait_idle()
    assert len(client.sent) == 2



# ---- selecting a row, running it, and moving on

def test_selecting_a_row_sends_nothing():
    client = FakeClient()
    r = runner_for("\n".join([A, B]), client)
    r.select(1)
    assert client.sent == [] and r.snapshot()["current"] == 1


def test_the_selected_row_runs_even_if_unchecked_or_already_done():
    client = FakeClient()
    r = runner_for("\n".join([A, B]), client)
    r.set_checked(1, False)
    r.select(1)
    r.start_current()
    r.wait_idle()
    assert [s[1] for s in client.sent] == ["54 is short Sunday"]
    r.select(1)
    r.start_current()  # the same row again
    r.wait_idle()
    assert len(client.sent) == 2


def test_the_selection_stays_on_the_last_row_at_the_end():
    client = FakeClient()
    r = runner_for("\n".join([A, B]), client)
    r.select(1)
    r.start_current()
    r.wait_idle()
    assert r.snapshot()["current"] == 1


def test_run_needs_a_selected_row_and_no_run_in_progress():
    empty = runner_for(HEADER)
    with pytest.raises(RuntimeError):
        empty.start_current()
    r = runner_for("\n".join([A, B]), FakeClient(busy=50))
    r.start_current()
    with pytest.raises(RuntimeError):
        r.select(1)
    with pytest.raises(RuntimeError):
        r.start_current()
    r.stop()
    r.wait_idle()


def test_run_all_with_a_filter_runs_only_the_days_shown():
    client = FakeClient()
    r = runner_for("\n".join([A, B]), client)
    r.start("all", start=date(2026, 3, 15))  # open-ended: from March 15 on
    r.wait_idle()
    assert [s[1] for s in client.sent] == ["54 is short Sunday"]
    r2_client = FakeClient()
    r2 = runner_for("\n".join([A, B]), r2_client)
    with pytest.raises(RuntimeError):  # nothing in the filter: refused, nothing sent
        r2.start("all", start=date(2026, 3, 20))
    assert r2_client.sent == []
