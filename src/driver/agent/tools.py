"""The tools the models can call. Each one is an ordinary Python function; the model only sees its schema and result.

A tool never raises into the model loop. A refusal comes back as {"error": "..."}, so the model can read it and
adjust. The one exception is Stopped, which ends the run and is allowed to propagate.
"""

import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from driver.agent.run_state import RunContext, Stopped
from driver.api.replay import WORKING, ReplayError
from driver.calendar_test import CalendarError, GuardRefused, day_schedule

NY = ZoneInfo("America/New_York")
FINAL_REPLY_STATUSES = {"pending"}  # outbox rows still being sent: read the outbox again


@dataclass
class Deps:
    replay: object  # ReplayClient-like: members, send, trace, outbox
    calendar: object  # TestCalendar-like: raw_day, change
    sender_ids: dict  # pseudonym -> sender id; sent to the chatbot as GroupMe would, never to a model
    poll_s: float = 1.0
    names: dict = field(default_factory=dict)  # pseudonym -> real name; shown on the page only, never to a model


def _err(message: str) -> dict:
    return {"error": message}


def _day(text: str) -> date:
    return date.fromisoformat(text)


def _parse_when(text: str) -> datetime:
    when = datetime.fromisoformat(text)
    if when.tzinfo is None:
        when = when.replace(tzinfo=NY)
    return when.astimezone(NY)


# ---- posting and reading the chat

def _wait_for(ctx: RunContext, deps: Deps, trace_id: str) -> tuple[str, list[dict]]:
    deadline = time.monotonic() + ctx.reply_timeout_s
    status = "enqueued"
    while True:
        ctx.check_stop()
        status = deps.replay.trace(trace_id).get("status", "unknown")
        if status not in WORKING:
            break
        if time.monotonic() > deadline:
            return "still processing", []
        time.sleep(deps.poll_s)
    while True:
        rows = deps.replay.outbox(trace_id)
        if not any(r.get("status") in FINAL_REPLY_STATUSES for r in rows) or time.monotonic() > deadline:
            return status, rows
        time.sleep(deps.poll_s)


def list_personas(ctx: RunContext, deps: Deps, _inp: dict) -> dict:
    return {"personas": [{"member": p, "squad": s} for p, s in ctx.personas.items()]}


def post_message(ctx: RunContext, deps: Deps, inp: dict) -> dict:
    member = inp.get("member") or ""
    text = (inp.get("text") or "").strip()
    setting = inp.get("setting") or "wait"
    if member not in ctx.personas:
        return _err(f"{member!r} is not a persona for this run")
    if setting not in ctx.posting_allowed:
        return _err(f"posting setting {setting!r} is not allowed for this run")
    if not text:
        return _err("text is empty")
    try:
        when = _parse_when(inp.get("sent_at") or "")
    except ValueError:
        return _err("sent_at must be an ISO 8601 time, for example 2026-11-04T18:30:00-05:00")
    if not ctx.window_start <= when.date() <= ctx.window_end:
        return _err(f"sent_at is outside the window {ctx.window_start} to {ctx.window_end}")
    if ctx.messages_posted >= ctx.max_messages:
        return _err("the message limit for this run is reached")
    ctx.check_stop()
    warning = f"sent_at is after the gate date {ctx.gate}" if when.date() > ctx.gate else None
    try:
        sent = deps.replay.send(deps.sender_ids[member], text, when.isoformat(), ctx.live)
    except (ReplayError, KeyError) as exc:
        return _err(f"send refused: {exc}")
    ctx.messages_posted += 1
    trace_id = sent.get("trace_id")
    ctx.emit("post", persona=member, name=deps.names.get(member, ""), sender_id=deps.sender_ids[member],
             squad=ctx.personas[member], text=text, setting=setting,
             sent_at=when.isoformat(), trace_id=trace_id, send_status=sent.get("status"), warning=warning)
    if sent.get("status") != "enqueued" or setting == "none":
        return {"trace_id": trace_id, "status": sent.get("status"), "replies": [],
                "note": "not waiting for a reply" if setting == "none" else "the chatbot did not take this message",
                **({"warning": warning} if warning else {})}
    try:
        final, rows = _wait_for(ctx, deps, trace_id)
    except ReplayError as exc:
        return _err(f"could not read the reply: {exc}")
    replies = []
    for row in rows:
        reply = {"reply_kind": row.get("kind"), "text": ctx.scrub(row.get("text") or ""),
                 "channel": row.get("channel"), "status": row.get("status"), "error": row.get("error")}
        replies.append(reply)
        ctx.emit("reply", trace_id=trace_id, **reply)
    return {"trace_id": trace_id, "status": final, "replies": replies,
            **({"warning": warning} if warning else {})}


# ---- the calendar

def read_calendar(ctx: RunContext, deps: Deps, inp: dict) -> dict:
    try:
        day = _day(inp.get("date") or "")
    except ValueError:
        return _err("date must be YYYY-MM-DD")
    ctx.days.add(day.isoformat())
    try:
        raw = deps.calendar.raw_day(day)
    except (CalendarError, GuardRefused) as exc:
        return _err(str(exc))
    ctx.emit("tool", name="read_calendar", date=day.isoformat())
    return {"date": day.isoformat(), "day": ctx.scrub(json.dumps(day_schedule(raw)))}


def set_calendar(ctx: RunContext, deps: Deps, inp: dict) -> dict:
    if not ctx.setup_allowed:
        return _err("setup changes are not allowed for this run")
    action = inp.get("action") or ""
    try:
        day = _day(inp.get("date") or "")
        squad = int(inp.get("squad"))
    except (TypeError, ValueError):
        return _err("date must be YYYY-MM-DD and squad a number")
    start, end = str(inp.get("start") or ""), str(inp.get("end") or "")
    if len(start) != 4 or len(end) != 4 or not (start + end).isdigit():
        return _err("start and end must be HHMM, for example 1800 and 0600")
    ctx.days.add(day.isoformat())
    n = sum(1 for e in ctx.events if e["kind"] == "setup") + 1
    try:
        before = deps.calendar.raw_day(day)
        ctx.save_snapshot(f"setup{n}-before", day.isoformat(), before)
        result = deps.calendar.change(action, day, start, end, squad, live=ctx.live)
        after = deps.calendar.raw_day(day)
        ctx.save_snapshot(f"setup{n}-after", day.isoformat(), after)
    except (CalendarError, GuardRefused) as exc:
        return _err(str(exc))
    ctx.emit("setup", action=action, date=day.isoformat(), start=start, end=end, squad=squad,
             live=ctx.live, result=ctx.scrub(json.dumps(result)[:400]))
    return {"ok": True, "live": ctx.live, "note": "preview only: the calendar was not changed" if not ctx.live else "changed"}


# ---- the tester's finish

def finish(ctx: RunContext, deps: Deps, inp: dict) -> dict:
    ctx.finished = {"passed": bool(inp.get("passed")), "reason": str(inp.get("reason") or "")}
    ctx.emit("finish", passed=ctx.finished["passed"], reason=ctx.finished["reason"])
    return {"ok": True}


# ---- the tester's plan (one line, before any posting)

def submit_plan(ctx: RunContext, deps: Deps, inp: dict) -> dict:
    ctx.plan = str(inp.get("plan") or "").strip()
    if not ctx.plan:
        return _err("the plan is empty")
    ctx.emit("plan", text=ctx.plan)
    return {"ok": True}


# ---- the judge's tools

def take_snapshot(ctx: RunContext, deps: Deps, inp: dict) -> dict:
    label = str(inp.get("label") or "").strip()
    if not label or not label.replace("-", "").replace("_", "").isalnum():
        return _err("label: letters, digits, '-' or '_'")
    saved = []
    for text in inp.get("dates") or []:
        try:
            day = _day(text)
            raw = deps.calendar.raw_day(day)
        except (ValueError, CalendarError, GuardRefused) as exc:
            return _err(f"{text}: {exc}")
        ctx.days.add(day.isoformat())
        ctx.save_snapshot(label, day.isoformat(), raw)
        saved.append(day.isoformat())
    ctx.emit("snapshot", label=label, dates=saved)
    return {"label": label, "saved": saved}


def read_trace(ctx: RunContext, deps: Deps, inp: dict) -> dict:
    try:
        trace = deps.replay.trace(str(inp.get("trace_id") or ""))
    except ReplayError as exc:
        return _err(str(exc))
    steps = [{"name": s.get("name"), "output": s.get("output"), "error": s.get("error")} for s in trace.get("steps", [])]
    return {"trace_id": trace.get("trace_id"), "status": trace.get("status"),
            "steps": ctx.scrub(json.dumps(steps, default=str))[:6000]}


def submit_checks(ctx: RunContext, deps: Deps, inp: dict) -> dict:
    checks = inp.get("checks") or []
    ids = [c.get("id") for c in checks if isinstance(c, dict)]
    if not checks or len(ids) != len(checks) or len(set(ids)) != len(ids) or not all(c.get("check") for c in checks):
        return _err("give a list of checks, each with a unique id and a check")
    ctx.checks = [{"id": c["id"], "check": c["check"], "look_at": c.get("look_at", "")} for c in checks]
    ctx.emit("checks", checks=ctx.checks)
    return {"ok": True, "checks": len(ctx.checks)}


def submit_verdicts(ctx: RunContext, deps: Deps, inp: dict) -> dict:
    rows = inp.get("verdicts") or []
    wanted = {c["id"] for c in ctx.checks}
    got = [r.get("id") for r in rows if isinstance(r, dict)]
    if set(got) != wanted or len(got) != len(set(got)):
        return _err(f"give exactly one verdict for each check id: {sorted(wanted)}")
    cleaned = []
    for r in rows:
        verdict = r.get("verdict")
        if verdict not in ("pass", "fail", "unclear"):
            return _err(f"verdict for {r.get('id')} must be pass, fail or unclear")
        evidence = (r.get("evidence") or "").strip()
        reason = (r.get("reason") or "").strip()
        if not evidence:  # no evidence means unclear, whatever the judge said
            verdict = "unclear"
            reason = ("no evidence given. " + reason).strip()
        cleaned.append({"id": r["id"], "verdict": verdict, "evidence": evidence, "reason": reason})
    ctx.verdicts = cleaned
    ctx.verdict_summary = str(inp.get("summary") or "")
    ctx.emit("verdict", verdicts=cleaned, summary=ctx.verdict_summary)
    return {"ok": True}


# ---- schemas the models see

def _tool(name: str, description: str, properties: dict, required: list) -> dict:
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": properties, "required": required}}


DATE = {"type": "string", "description": "YYYY-MM-DD, New York calendar date"}

PLAN_TOOLS = [
    _tool("submit_plan", "Say, in one line, what you will try to change and on which day. Call this first, before any post.",
          {"plan": {"type": "string"}}, ["plan"]),
]

CONVERSATION_TOOLS = [
    _tool("list_personas", "The personas you may write as, with their squads.", {}, []),
    _tool("post_message", "Post a message to the chat as one persona. Waits for the chatbot's reply unless setting is none.",
          {"member": {"type": "string", "description": "a persona pseudonym from list_personas"},
           "text": {"type": "string"},
           "sent_at": {"type": "string", "description": "ISO 8601 New York time with offset, inside the window"},
           "setting": {"type": "string", "enum": ["wait", "thread", "none", "sync"]}},
          ["member", "text", "sent_at"]),
    _tool("read_calendar", "Read the test calendar for one day.", {"date": DATE}, ["date"]),
    _tool("set_calendar", "Change the test calendar. Only when setup is allowed. Preview only unless the run is live.",
          {"action": {"type": "string", "enum": ["addShift", "noCrew"]}, "date": DATE,
           "start": {"type": "string", "description": "HHMM"}, "end": {"type": "string", "description": "HHMM"},
           "squad": {"type": "integer"}},
          ["action", "date", "start", "end", "squad"]),
    _tool("finish", "End the run. Call this when the stop condition is reached or a limit stops you.",
          {"passed": {"type": "boolean"}, "reason": {"type": "string"}}, ["passed", "reason"]),
]

JUDGE_PRE_TOOLS = [
    _tool("take_snapshot", "Save the raw calendar for days in question, under a label such as before.",
          {"label": {"type": "string"}, "dates": {"type": "array", "items": DATE}}, ["label", "dates"]),
    _tool("read_calendar", "Read the test calendar for one day (read only).", {"date": DATE}, ["date"]),
    _tool("read_trace", "Read the chatbot's steps for one trace (read only).", {"trace_id": {"type": "string"}}, ["trace_id"]),
    _tool("submit_checks", "Commit to your checks. Give one id and one check for each expected result, plus any others the results imply.",
          {"checks": {"type": "array", "items": {"type": "object", "properties": {
              "id": {"type": "string"}, "check": {"type": "string"}, "look_at": {"type": "string"}},
              "required": ["id", "check"]}}}, ["checks"]),
]

JUDGE_POST_TOOLS = [
    _tool("take_snapshot", "Save the raw calendar for days in question, under a label such as after.",
          {"label": {"type": "string"}, "dates": {"type": "array", "items": DATE}}, ["label", "dates"]),
    _tool("read_calendar", "Read the test calendar for one day (read only).", {"date": DATE}, ["date"]),
    _tool("read_trace", "Read the chatbot's steps for one trace (read only).", {"trace_id": {"type": "string"}}, ["trace_id"]),
    _tool("submit_verdicts", "Give one verdict for each check id, with its evidence and a short reason, and a summary.",
          {"verdicts": {"type": "array", "items": {"type": "object", "properties": {
              "id": {"type": "string"}, "verdict": {"type": "string", "enum": ["pass", "fail", "unclear"]},
              "evidence": {"type": "string"}, "reason": {"type": "string"}},
              "required": ["id", "verdict", "evidence", "reason"]}},
           "summary": {"type": "string"}}, ["verdicts", "summary"]),
]

# The judge uses one tool list for its whole run. Changing the tools between its two calls makes the API refuse the
# second call (the thinking blocks are bound to the request they came from).
JUDGE_TOOLS = JUDGE_PRE_TOOLS + [t for t in JUDGE_POST_TOOLS if t["name"] == "submit_verdicts"]

FUNCTIONS = {
    "submit_plan": submit_plan,
    "list_personas": list_personas,
    "post_message": post_message,
    "read_calendar": read_calendar,
    "set_calendar": set_calendar,
    "finish": finish,
    "take_snapshot": take_snapshot,
    "read_trace": read_trace,
    "submit_checks": submit_checks,
    "submit_verdicts": submit_verdicts,
}


def dispatch(ctx: RunContext, deps: Deps, allowed: list[dict], name: str, inp: dict) -> dict:
    """Run one tool call. Only the tools in `allowed` for this role can run."""
    if name not in {t["name"] for t in allowed}:
        return _err(f"tool {name!r} is not available to you")
    try:
        return FUNCTIONS[name](ctx, deps, inp or {})
    except Stopped:
        raise
    except Exception as exc:  # a tool must not crash the run; the model sees the error and can adjust
        return _err(f"{name} failed: {type(exc).__name__}")
