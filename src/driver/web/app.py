"""The driver's web server: serves the page and the JSON it uses. Settings come from the environment (.env)."""

import os
from datetime import date
from pathlib import Path

import logging

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from driver.api.replay import ReplayClient, ReplayError
from driver.batches.files import BatchError, is_groupme_export, parse, parse_groupme
from driver import config
from driver.agent import scenario as scen
from driver.agent.run import BotManager, ConfigError, RunBusy
from driver.batches.runner import Runner
from driver.calendar_test import GuardRefused
from driver.llm import Budget, BudgetExceeded, LlmClient, PriceMissing, load_prices

PAGE = Path(__file__).with_name("page.html")
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
    live: bool = False  # off: the calendar is only previewed for these messages


def create_app(client: ReplayClient | None = None, poll_s: float = 1.0, timeout_s: float = 120.0) -> FastAPI:
    client = client or ReplayClient(os.environ.get("REPLAY_URL", "http://localhost:8001"))
    app = FastAPI(title="chatbot driver")
    holder: dict[str, Runner | None] = {"runner": None}
    key = config.api_key()
    llm = LlmClient(key, load_prices(config.CONFIG / "model_prices.json"),
                    Budget(config.budget_cap_usd(), config.RUNS / "spend.json")) if key else None
    bot = BotManager(replay=client, llm=llm, poll_s=poll_s)

    def current() -> Runner:
        if holder["runner"] is None:
            raise HTTPException(404, "no batch is open")
        return holder["runner"]

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def page():
        return PAGE.read_text(encoding="utf-8")

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
        try:
            if req.mode == "current":
                runner.start_current(live=req.live)
            else:
                runner.start(req.mode, req.start, req.end, live=req.live)
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
        """Pseudonyms, squads and names, for the page only. Names are never sent to a model."""
        return [{"member": m["member"], "squad": m.get("squad", ""), "name": m.get("name", "")}
                for m in client.members()]

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

    return app


app = create_app()
