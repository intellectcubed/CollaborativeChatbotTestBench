"""The driver's web server: serves the page and the JSON it uses. Settings come from the environment (.env)."""

import os
from datetime import date
from pathlib import Path

import logging

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from driver.api.replay import ReplayClient, ReplayError
from driver.batches.files import BatchError, is_groupme_export, parse, parse_groupme
from driver import config
from driver.agent import scenario as scen
from driver.agent.run import BotManager, ConfigError, RunBusy
from driver.batches.runner import Runner
from driver.calendar_test import CalendarService, GuardRefused
from driver.calendar_week import WeekReader
from driver.manual import ManualBusy, ManualChat
from driver import roster as roster_file
from driver.llm import Budget, BudgetExceeded, LlmClient, PriceMissing, load_prices

# The React build (ui/, built with `npm run build`). Outside src/, so the development mount of ./src does not hide it.
UI_DIST = Path(os.environ.get("UI_DIST") or Path(__file__).resolve().parents[3] / "ui" / "dist")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class OpenRequest(BaseModel):
    name: str
    content: str


class CheckRequest(BaseModel):
    checked: bool


class SelectRequest(BaseModel):
    index: int


class RunRequest(BaseModel):
    mode: str  # all | range | current (the selected row)
    start: date | None = None
    end: date | None = None


class ManualSendRequest(BaseModel):
    squad: str
    name: str | None = None  # a member's real name from the roster file; empty: the squad's first member by name
    text: str
    sent_at: str  # YYYY-MM-DDTHH:MM, New York time when there is no offset


class SettingsRequest(BaseModel):
    live: bool  # the Live Calendar checkbox: applies to batch runs and bot runs alike


def create_app(client: ReplayClient | None = None, poll_s: float = 1.0, timeout_s: float = 120.0,
               ui_dist: Path | None = None, calendar=None, roster_path: Path | None = None) -> FastAPI:
    client = client or ReplayClient(os.environ.get("REPLAY_URL", "http://localhost:8001"))
    app = FastAPI(title="chatbot driver")
    dist = ui_dist or UI_DIST
    holder: dict[str, Runner | None] = {"runner": None}
    key = config.api_key()
    llm = LlmClient(key, load_prices(config.CONFIG / "model_prices.json"),
                    Budget(config.budget_cap_usd(), config.RUNS / "spend.json")) if key else None
    bot = BotManager(replay=client, llm=llm, poll_s=poll_s, calendar=calendar)
    roster_csv = roster_path or config.roster_csv()
    manual = ManualChat(client, lambda: roster_file.load(roster_csv), poll_s=poll_s, timeout_s=timeout_s)
    # The week preview reads the test calendar only; CalendarService refuses any other address.
    week = WeekReader(lambda: calendar or CalendarService(config.calendar_test_url()))
    # One global setting, in memory. It starts off, so a restart never turns live calendar changes on.
    settings_state = {"live": False}

    def current() -> Runner:
        if holder["runner"] is None:
            raise HTTPException(404, "no batch is open")
        return holder["runner"]

    def batch_busy() -> bool:
        runner = holder["runner"]
        return runner is not None and runner.state != "idle"

    def bot_busy() -> bool:
        return bot.status(0).get("state") == "running"

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/", response_class=HTMLResponse)
    def page():
        index = dist / "index.html"
        if not index.is_file():
            return HTMLResponse("<p>The page is not built. In the ui folder, run: npm install, then npm run build.</p>",
                                status_code=503)
        return FileResponse(index)

    @app.get("/api/settings")
    def get_settings():
        return {"live": settings_state["live"]}

    @app.put("/api/settings")
    def put_settings(req: SettingsRequest):
        if req.live != settings_state["live"] and (batch_busy() or bot_busy() or manual.waiting):
            raise HTTPException(409, "stop the run before changing the Live Calendar setting")
        settings_state["live"] = req.live
        return {"live": settings_state["live"]}

    @app.get("/api/usage")
    def usage():
        """Tokens used by the driver's own model calls (the bot), and the budget. Batch runs use the chatbot's models."""
        if llm is None:
            return {"tokens_in": 0, "tokens_out": 0, "spent_usd": None, "cap_usd": None, "key_set": False}
        b = llm.budget
        return {"tokens_in": b.tokens_in, "tokens_out": b.tokens_out, "spent_usd": round(b.spent, 4),
                "cap_usd": b.cap, "key_set": True}

    @app.post("/api/usage/reset")
    def usage_reset():
        """Clears the token counts. The money spent is not cleared: the budget cap still applies."""
        if llm is None:
            return {"ok": True}
        llm.budget.reset_tokens()
        return {"ok": True}

    @app.post("/api/batch/open")
    def open_batch(req: OpenRequest):
        runner = holder["runner"]
        if runner is not None and runner.state != "idle":
            raise HTTPException(409, "stop the current run before opening another batch")
        try:
            members = {m["member"]: m for m in client.members()}
        except ReplayError as exc:
            raise HTTPException(502, str(exc))
        try:
            if is_groupme_export(req.content):
                pseudonym_for = {str(m["sender_id"]): p for p, m in members.items()}
                batch = parse_groupme(req.content, default_name=req.name, pseudonym_for=pseudonym_for)
            else:
                batch = parse(req.content, default_name=req.name)
        except BatchError as exc:
            raise HTTPException(422, exc.errors)
        unknown = sorted({m.member for m in batch.messages if m.member not in members})
        holder["runner"] = Runner(client, batch, members, poll_s=poll_s, timeout_s=timeout_s)
        return {"name": batch.name, "messages": len(batch.messages),
                "warnings": batch.notes + [f"{u} is not on the roster: those lines will fail" for u in unknown]}

    @app.get("/api/batch")
    def get_batch(since: int = -1):
        """The status, and the rows that changed after version `since`. A negative since gives every row."""
        runner = holder["runner"]
        if runner is None:
            return {"batch_id": None, "version": 0, "name": None, "description": "", "state": "none", "live": False,
                    "current": None, "pending": 0, "total": 0, "lines": []}
        return runner.snapshot(since)

    @app.post("/api/batch/lines/{index}")
    def check_line(index: int, req: CheckRequest):
        runner = current()
        if not 0 <= index < len(runner.lines):
            raise HTTPException(404, "no such line")
        try:
            runner.set_checked(index, req.checked)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))
        return {"ok": True}

    @app.post("/api/batch/select")
    def select(req: SelectRequest):
        runner = current()
        if not 0 <= req.index < len(runner.lines):
            raise HTTPException(404, "no such line")
        try:
            runner.select(req.index)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))
        return {"ok": True}

    @app.post("/api/batch/run")
    def run(req: RunRequest):
        if req.mode not in ("all", "range", "current"):
            raise HTTPException(422, "mode must be all, range or current")
        if req.mode == "range" and (req.start is None or req.end is None):
            raise HTTPException(422, "a range needs a start and an end date")
        runner = current()
        live = settings_state["live"]  # the Live Calendar checkbox, global
        try:
            if req.mode == "current":
                runner.start_current(live=live)
            else:
                runner.start(req.mode, req.start, req.end, live=live)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))
        return {"ok": True}

    @app.post("/api/batch/pause")
    def pause():
        current().pause()
        return {"ok": True}

    @app.post("/api/batch/resume")
    def resume():
        current().resume()
        return {"ok": True}

    @app.post("/api/batch/stop")
    def stop():
        current().stop()
        return {"ok": True}

    @app.post("/api/batch/close")
    def close():
        runner = holder["runner"]
        if runner is not None and runner.state != "idle":
            raise HTTPException(409, "stop the run before closing the batch")
        holder["runner"] = None
        return {"ok": True}

    @app.post("/api/batch/reset")
    def reset():
        try:
            current().reset()
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))
        return {"ok": True}

    @app.get("/api/roster")
    def roster():
        """The chat's members from the roster file: real name, sender id and squad, sorted by name. Each also has the
        chatbot's member id (`member`, e.g. Member-2) when the replay tool can be reached: the bot's runs use it, so
        that no real name reaches a model. Without the file, the replay tool's own roster is used."""
        try:
            pseudonym = {str(m["sender_id"]): m["member"] for m in client.members()}
            replay_error = ""
        except ReplayError as exc:
            pseudonym, replay_error = {}, str(exc)
        try:
            rows = roster_file.load(roster_csv)
        except roster_file.RosterError as exc:
            if replay_error:
                raise HTTPException(502, f"{exc}; {replay_error}")
            rows = sorted(({"name": m.get("name") or m["member"], "sender_id": str(m["sender_id"]),
                            "squad": str(m.get("squad", ""))} for m in client.members()), key=lambda m: m["name"].lower())
        return [{**m, "member": pseudonym.get(m["sender_id"])} for m in rows]

    @app.get("/api/bot/goals")
    def goal_names():
        return scen.names(config.SCENARIOS)

    @app.get("/api/bot/goals/{name}")
    def goal_load(name: str):
        try:
            return scen.load(config.SCENARIOS, name)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, "no such goal")

    @app.put("/api/bot/goals/{name}")
    def goal_save(name: str, goal: dict = Body(...)):
        goal["name"] = name
        errors = scen.validate(goal)
        if errors:
            raise HTTPException(422, errors)
        scen.save(config.SCENARIOS, goal)
        return {"ok": True, "name": name}

    @app.post("/api/bot/go")
    def bot_go(goal: dict = Body(...)):
        goal["live"] = settings_state["live"]  # the global Live Calendar setting overrides the goal file's
        try:
            bot.start(goal)
        except ValueError as exc:
            raise HTTPException(422, str(exc).split("; "))
        except RunBusy as exc:
            raise HTTPException(409, str(exc))
        except (ConfigError, PriceMissing, BudgetExceeded, GuardRefused) as exc:
            raise HTTPException(400, str(exc))
        return {"ok": True}

    @app.post("/api/bot/stop")
    def bot_stop():
        if not bot.stop():
            raise HTTPException(409, "no bot run is going")
        return {"ok": True}

    @app.get("/api/bot/status")
    def bot_status(since: int = 0):
        return bot.status(since)

    # ---- the Bot tab's week preview (reads only)

    @app.get("/api/calendar/week")
    def calendar_week(start: date, recheck: bool = False):
        """Seven days from the Sunday of `start`, and what changed since each day was last read. With recheck, the
        other days read recently are read again too, so a change outside this week is reported."""
        return week.read(start, recheck=recheck)

    # ---- manual chat on the Bot tab

    @app.post("/api/manual/send")
    def manual_send(req: ManualSendRequest):
        try:
            sent = manual.send(req.squad, req.name, req.text, req.sent_at, live=settings_state["live"])
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        except roster_file.RosterError as exc:
            raise HTTPException(503, str(exc))
        except ManualBusy as exc:
            raise HTTPException(409, str(exc))
        except ReplayError as exc:
            raise HTTPException(502, str(exc))
        return {"ok": True, **sent}  # trace_id: the id the chatbot gave this message

    @app.get("/api/manual/status")
    def manual_status(since: int = 0):
        return manual.status(since)

    @app.post("/api/manual/clear")
    def manual_clear():
        try:
            manual.clear()
        except ManualBusy as exc:
            raise HTTPException(409, str(exc))
        return {"ok": True}

    return app


app = create_app()
