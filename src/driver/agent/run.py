"""One bot run, end to end, in a background thread:

1. the tester writes a one-line plan (no posting yet);
2. the judge commits to its checks and takes its `before` images of the days in question;
3. the tester holds the conversation with the chatbot, through its tools;
4. the driver takes the `after` images;
5. the judge gives a verdict on each check, from the transcript and the images.

Models are called through driver.llm; tools run in driver.agent.tools. Only one run at a time, across the batch and
bot tabs, through driver.lock.gate.
"""

import json
import logging
import threading
from datetime import date, datetime
from pathlib import Path

from driver import config
from driver.agent import scenario as scen
from driver.agent.run_state import RunContext, Stopped, diff_text, real_name_map
from driver.agent.tools import CONVERSATION_TOOLS, JUDGE_TOOLS, PLAN_TOOLS, Deps, dispatch
from driver.calendar_test import GuardRefused, CalendarService
from driver.llm import BudgetExceeded, LlmClient, LlmError, PriceMissing
from driver.lock import gate

log = logging.getLogger("driver.bot")

NOISE_TEXT = {
    "none": "No noise. Post only what the goal needs.",
    "some": "While the conversation goes on, post a few unrelated messages from other personas.",
    "heavy": "While the conversation goes on, post many messages from several personas, some touching the same squad or day.",
}


class RunBusy(Exception):
    """Another run is going (a batch run or a bot run)."""


class ConfigError(Exception):
    """A run cannot start: a setting is missing."""


def run_loop(ctx: RunContext, llm: LlmClient, deps: Deps, *, model: str, system: str, messages: list, tools: list,
             max_turns: int, max_tokens: int, temperature: float | None, done) -> str:
    """Ask the model, run the tool calls it asks for, and repeat until `done()` or a limit."""
    for _ in range(max_turns):
        ctx.check_stop()
        resp = llm.call(model=model, system=system, messages=messages, tools=tools,
                        max_tokens=max_tokens, temperature=temperature)
        ctx.spent_usd += resp["cost"]
        ctx.emit("model", model=model, stop_reason=resp.get("stop_reason"), cost_usd=round(resp["cost"], 5),
                 input_tokens=resp["usage"].get("input_tokens"), output_tokens=resp["usage"].get("output_tokens"))
        if ctx.spent_usd > ctx.max_cost_usd:
            raise Stopped("run cost limit reached")
        messages.append({"role": "assistant", "content": resp["content"]})
        uses = [b for b in resp["content"] if b.get("type") == "tool_use"]
        if not uses:
            ctx.emit("tool_call", name=None, note="the model answered with text and no tool call")
            return "no tool call"
        results = []
        for use in uses:
            out = dispatch(ctx, deps, tools, use["name"], use.get("input") or {})
            ctx.emit("tool_call", name=use["name"], result=ctx.scrub(json.dumps(out, default=str))[:300])
            log.info("tool %s -> %s", use["name"], "error" if "error" in out else "ok")
            results.append({"type": "tool_result", "tool_use_id": use["id"], "content": json.dumps(out)})
        messages.append({"role": "user", "content": results})
        if done():
            return "done"
    return "turn limit reached"


def add_user_text(messages: list, text: str) -> list:
    """Add text to the conversation. If the last turn is a user turn (tool results), the text joins it."""
    if messages and messages[-1]["role"] == "user":
        content = messages[-1]["content"]
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        messages[-1] = {"role": "user", "content": content + [{"type": "text", "text": text}]}
    else:
        messages.append({"role": "user", "content": text})
    return messages


def transcript_text(ctx: RunContext) -> str:
    lines = []
    for ev in ctx.events:
        if ev["kind"] == "post":
            lines.append(f"[post as {ev['persona']} ({ev['squad']}), setting {ev['setting']}, sent_at {ev['sent_at']}, "
                         f"trace {ev['trace_id']}] {ctx.scrub(ev['text'])}")
        elif ev["kind"] == "reply":
            lines.append(f"[chatbot reply, trace {ev['trace_id']}, {ev['reply_kind']} via {ev['channel']}, {ev['status']}] "
                         f"{ev['text']}")
        elif ev["kind"] == "setup":
            lines.append(f"[setup {ev['action']} {ev['date']} {ev['start']}-{ev['end']} squad {ev['squad']}, "
                         f"live {ev['live']}]")
        elif ev["kind"] == "finish":
            lines.append(f"[tester finished: passed={ev['passed']}] {ev['reason']}")
    return "\n".join(lines) or "(no messages were posted)"


class BotManager:
    def __init__(self, *, replay, llm: LlmClient | None, scenarios_dir: Path = config.SCENARIOS,
                 runs_dir: Path = config.RUNS, calendar_url: str | None = None, poll_s: float = 1.0,
                 calendar=None) -> None:
        self.replay = replay
        self.calendar_override = calendar  # tests pass a fake here; the page never does
        self.llm = llm
        self.scenarios_dir = scenarios_dir
        self.runs_dir = runs_dir
        self.calendar_url = calendar_url
        self.poll_s = poll_s
        self.state = "idle"  # idle | running | done | stopped | error
        self.reason = ""
        self.ctx: RunContext | None = None
        self.goal_name = ""
        self._lock = threading.Lock()

    # ---- starting

    def start(self, goal: dict) -> None:
        errors = scen.validate(goal)
        if errors:
            raise ValueError("; ".join(errors))
        if self.llm is None:
            raise ConfigError("ANTHROPIC_API_KEY is not set in .env, so the bot cannot call a model")
        for model in {goal["models"]["tester"], goal["models"]["judge"]}:
            if not self.llm._priced(model):
                raise PriceMissing(model)
        if self.llm.budget.spent >= self.llm.budget.cap:
            raise BudgetExceeded(f"budget reached: ${self.llm.budget.spent:.2f} of ${self.llm.budget.cap:.2f} spent")
        calendar = self.calendar_override or CalendarService(self.calendar_url or config.calendar_test_url())  # guard
        members = self.replay.members()
        sender_ids = {m["member"]: str(m["sender_id"]) for m in members}
        for p in set(goal["personas"]):
            if p not in sender_ids:
                raise ValueError(f"{p} is not on the chatbot's roster")
        squad_of = {m["member"]: str(m.get("squad", "")) for m in members}
        personas = {p: squad_of[p] for p in [goal["my_squad"]] + [x for x in goal["personas"] if x != goal["my_squad"]]}
        window = goal["window"]
        with self._lock:
            if self.state == "running":
                raise RunBusy("a bot run is already going")
            if not gate.acquire("bot"):
                raise RunBusy(f"another run is going: {gate.owner}")
            try:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                ctx = RunContext(
                    folder=self.runs_dir / f"{goal['name']}-{stamp}",
                    personas=personas,
                    window_start=date.fromisoformat(window["start"]),
                    window_end=date.fromisoformat(window["end"]),
                    gate=date.fromisoformat(goal["gate_date"]),
                    live=bool(goal["live"]),
                    setup_allowed=bool(goal["setup_allowed"]),
                    posting_allowed=set(goal["posting_allowed"]),
                    max_messages=int(goal["limits"]["max_messages"]),
                    max_cost_usd=float(goal["limits"]["max_cost_usd"]),
                    reply_timeout_s=float(goal["limits"]["reply_timeout_s"]),
                    real_names=real_name_map(members),
                )
                ctx.days.add(ctx.gate.isoformat())
            except Exception:
                gate.release("bot")
                raise
            self.ctx, self.goal_name = ctx, goal["name"]
            self.state, self.reason = "running", ""
        names = {m["member"]: m.get("name", "") for m in members}
        deps = Deps(replay=self.replay, calendar=calendar, sender_ids=sender_ids, poll_s=self.poll_s, names=names)
        threading.Thread(target=self._execute, args=(ctx, deps, goal), daemon=True).start()

    def stop(self) -> bool:
        if self.state == "running" and self.ctx is not None:
            self.ctx.stopped = "stopped by you"
            return True
        return False

    def status(self, since: int = 0) -> dict:
        ctx = self.ctx
        events = ctx.events[since:] if ctx else []
        return {"state": self.state, "reason": self.reason, "goal": self.goal_name,
                "run": ctx.folder.name if ctx else "", "next": len(ctx.events) if ctx else 0,
                "events": events, "plan": ctx.plan if ctx else None,
                "checks": ctx.checks if ctx else [], "verdicts": ctx.verdicts if ctx else [],
                "verdict_summary": ctx.verdict_summary if ctx else "",
                "finished": ctx.finished if ctx else None,
                "run_spent_usd": round(ctx.spent_usd, 4) if ctx else 0.0,
                "budget_spent_usd": round(self.llm.budget.spent, 4) if self.llm else None,
                "budget_cap_usd": self.llm.budget.cap if self.llm else None}

    # ---- the run

    def _system(self, *parts: str) -> str:
        return "\n\n---\n\n".join((config.PROMPTS / p).read_text(encoding="utf-8") for p in parts)

    def _tester_system(self, goal: dict, ctx: RunContext) -> str:
        personas = "; ".join(f"{p} (squad {s})" for p, s in ctx.personas.items())
        run = (f"## This run\n\n"
               f"Personas you may write as (pseudonyms only): {personas}. My squad: {goal['my_squad']}.\n"
               f"Window: {ctx.window_start} to {ctx.window_end}. Gate date (the day the request is about): {ctx.gate}.\n"
               f"Posting settings allowed: {', '.join(sorted(ctx.posting_allowed))}. "
               f"Setup changes allowed: {'yes' if ctx.setup_allowed else 'no'}. "
               f"Live calendar: {'yes' if ctx.live else 'no'}.\n"
               f"Noise: {NOISE_TEXT[goal['noise']]}\n\n"
               f"Goal: {goal['goal']}\n\nStop when: {goal['stop_condition']}\n")
        return self._system("system.md", "domain.md", "chat_conventions.md") + "\n\n---\n\n" + run

    def _judge_system(self) -> str:
        return self._system("judge.md", "domain.md", "chat_conventions.md")

    def _judge_pre_text(self, ctx: RunContext, goal: dict) -> str:
        results = "\n".join(f"- {r}" for r in goal["expected_results"])
        return (f"The tester's plan: {ctx.plan}\n\n"
                f"Expected results (judge only):\n{results}\n\n"
                f"Gate date: {ctx.gate}. Days in question so far: {', '.join(sorted(ctx.days))}.\n\n"
                "First take a snapshot labelled before for the days in question. Then call submit_checks with one check "
                "per expected result, plus any others these imply. Do not judge yet.")

    def _judge_post_text(self, ctx: RunContext) -> str:
        diffs = []
        for day in sorted(ctx.days):
            diffs.append(f"### {day}\n```\n{diff_text(ctx.snapshots.get(('before', day)), ctx.snapshots.get(('after', day)))}\n```")
        finished = ctx.finished or {"passed": None, "reason": "the tester did not call finish"}
        return ("The run has finished.\n\nTranscript:\n" + transcript_text(ctx) +
                f"\n\nThe tester finished with: {json.dumps(finished)}\n\n"
                "Calendar before and after, per day in question:\n" + "\n".join(diffs) +
                "\n\nNow give one verdict for each of your checks with submit_verdicts: evidence first, then the reason.")

    def _snapshot(self, ctx: RunContext, deps: Deps, label: str, iso_day: str) -> None:
        ctx.save_snapshot(label, iso_day, deps.calendar.raw_day(date.fromisoformat(iso_day)))

    def _execute(self, ctx: RunContext, deps: Deps, goal: dict) -> None:
        outcome, reason = "done", ""
        tester_model, judge_model = goal["models"]["tester"], goal["models"]["judge"]
        t_temp, j_temp = goal["temperature"].get("tester"), goal["temperature"].get("judge", 0.0)
        ctx.emit("note", text=f"run {goal['name']} started")
        try:
            tester_sys = self._tester_system(goal, ctx)
            # 1. the plan
            msgs = [{"role": "user", "content": "Before you post anything, call submit_plan with one line: what you will "
                                                "try to change, and on which day."}]
            run_loop(ctx, self.llm, deps, model=tester_model, system=tester_sys, messages=msgs, tools=PLAN_TOOLS,
                     max_turns=3, max_tokens=512, temperature=t_temp, done=lambda: ctx.plan is not None)
            if ctx.plan is None:
                raise Stopped("the tester did not write a plan")
            # 2. the judge's checks and the before images
            judge_sys = self._judge_system()
            judge_msgs = [{"role": "user", "content": self._judge_pre_text(ctx, goal)}]
            run_loop(ctx, self.llm, deps, model=judge_model, system=judge_sys, messages=judge_msgs, tools=JUDGE_TOOLS,
                     max_turns=8, max_tokens=2048, temperature=j_temp, done=lambda: bool(ctx.checks))
            if not ctx.checks:
                raise Stopped("the judge did not commit to its checks")
            for day in sorted(ctx.days):
                if ("before", day) not in ctx.snapshots:
                    self._snapshot(ctx, deps, "before", day)
            # 3. the conversation
            msgs = [{"role": "user", "content": "Begin. Post your first message when you are ready."}]
            run_loop(ctx, self.llm, deps, model=tester_model, system=tester_sys, messages=msgs, tools=CONVERSATION_TOOLS,
                     max_turns=int(goal["limits"]["max_turns"]), max_tokens=1024, temperature=t_temp,
                     done=lambda: ctx.finished is not None)
            if ctx.finished is None:
                ctx.emit("note", text="the tester ended without calling finish")
            # 4. the after images
            for day in sorted(ctx.days):
                self._snapshot(ctx, deps, "after", day)
            # 5. the verdicts
            judge_msgs = add_user_text(judge_msgs, self._judge_post_text(ctx))
            run_loop(ctx, self.llm, deps, model=judge_model, system=judge_sys, messages=judge_msgs, tools=JUDGE_TOOLS,
                     max_turns=8, max_tokens=2048, temperature=j_temp, done=lambda: bool(ctx.verdicts))
            if not ctx.verdicts:
                ctx.emit("note", text="the judge gave no verdicts")
        except Stopped as stop:
            outcome, reason = "stopped", stop.reason
            ctx.emit("stop", reason=reason)
            log.warning("run %s stopped: %s", goal["name"], reason)
        except (BudgetExceeded, PriceMissing, LlmError, GuardRefused) as exc:
            outcome, reason = "stopped", str(exc)
            ctx.emit("stop", reason=reason)
            log.warning("run %s stopped: %s", goal["name"], reason)
        except Exception as exc:
            # The page gets only the type name. The full traceback goes to the container log, where you can read it.
            outcome, reason = "error", f"unexpected error: {type(exc).__name__}"
            ctx.emit("stop", reason=reason)
            log.exception("run %s failed", goal["name"])
        finally:
            self._write_files(ctx, goal, outcome, reason)
            gate.release("bot")
            with self._lock:
                self.state, self.reason = outcome, reason

    def _write_files(self, ctx: RunContext, goal: dict, outcome: str, reason: str) -> None:
        summary = {"goal": goal["name"], "status": outcome, "reason": reason, "tester_model": goal["models"]["tester"],
                   "judge_model": goal["models"]["judge"], "messages_posted": ctx.messages_posted,
                   "run_cost_usd": round(ctx.spent_usd, 4), "finished": ctx.finished, "passed_checks":
                   sum(1 for v in ctx.verdicts if v["verdict"] == "pass"), "checks": len(ctx.checks)}
        (ctx.folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        lines = [f"# Run {goal['name']}", "", f"Status: {outcome}" + (f" ({reason})" if reason else ""), "",
                 "## Plan", ctx.plan or "(none)", "", "## Checks and verdicts"]
        verdicts = {v["id"]: v for v in ctx.verdicts}
        for c in ctx.checks:
            v = verdicts.get(c["id"], {})
            lines.append(f"- **{c['id']}** {c['check']}  \n  verdict: {v.get('verdict', 'none')}; {v.get('reason', '')}  \n"
                         f"  evidence: {v.get('evidence', '')}")
        lines += ["", f"Judge's summary: {ctx.verdict_summary}", "", "## Calendar difference"]
        for day in sorted(ctx.days):
            lines += [f"### {day}", "```", diff_text(ctx.snapshots.get(("before", day)),
                                                     ctx.snapshots.get(("after", day))), "```"]
        lines += ["", "## Conversation", "```", transcript_text(ctx), "```"]
        (ctx.folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
