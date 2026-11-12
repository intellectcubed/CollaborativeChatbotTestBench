"""Goal files: one JSON file per goal in scenarios/. The system prompt is not in a goal file; it is global."""

import json
import re
from pathlib import Path

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,60}$")
NOISE = {"none", "some", "heavy"}
SETTINGS = {"wait", "thread", "none", "sync"}
DEFAULT_LIMITS = {"max_messages": 12, "max_turns": 30, "reply_timeout_s": 120, "max_cost_usd": 0.5}


def default_goal() -> dict:
    return {
        "name": "",
        "goal": "",
        "stop_condition": "",
        "expected_results": [],
        "my_squad": "",
        "personas": [],
        "window": {"start": "", "end": ""},
        "gate_date": "",
        "noise": "none",
        "posting_allowed": ["wait", "thread", "none", "sync"],
        "setup_allowed": False,
        "live": False,
        "models": {"tester": "claude-sonnet-5-5", "judge": "claude-opus-5-5"},
        "temperature": {"tester": 0.7, "judge": 0.0},
        "limits": dict(DEFAULT_LIMITS),
    }


def validate(goal: dict) -> list[str]:
    errors = []
    if not NAME.match(goal.get("name") or ""):
        errors.append("name: use lower case letters, digits, '-' or '_' (for example no_crew_multi_day)")
    if not (goal.get("goal") or "").strip():
        errors.append("goal: say what the bot should try")
    if not goal.get("my_squad"):
        errors.append("my squad: choose the persona the bot writes as first")
    if goal.get("my_squad") and goal["my_squad"] not in goal.get("personas", []):
        errors.append("personas: must include my squad's member")
    if goal.get("noise") not in NOISE:
        errors.append("noise: none, some or heavy")
    for setting in goal.get("posting_allowed", []):
        if setting not in SETTINGS:
            errors.append(f"posting_allowed: unknown setting {setting}")
    window = goal.get("window") or {}
    if not window.get("start") or not window.get("end") or window["start"] > window["end"]:
        errors.append("window: a start and an end date, start first")
    if not goal.get("gate_date"):
        errors.append("gate date: the day the request is about")
    if not goal.get("expected_results"):
        errors.append("expected results: at least one, for the judge")
    if not goal.get("stop_condition"):
        errors.append("stop condition: when the run is finished")
    return errors


def path_for(scenarios_dir: Path, name: str) -> Path:
    if not NAME.match(name or ""):
        raise ValueError("invalid goal name")
    return scenarios_dir / f"{name}.json"


def load(scenarios_dir: Path, name: str) -> dict:
    return json.loads(path_for(scenarios_dir, name).read_text(encoding="utf-8"))


def save(scenarios_dir: Path, goal: dict) -> Path:
    path = path_for(scenarios_dir, goal.get("name", ""))
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(goal, indent=2) + "\n", encoding="utf-8")
    return path


def names(scenarios_dir: Path) -> list[str]:
    if not scenarios_dir.exists():
        return []
    return sorted(p.stem for p in scenarios_dir.glob("*.json"))
