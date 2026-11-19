"""The chat's roster, from the GroupMe roster file: each member's real name, sender id and squad.

The Bot tab simulates a client of the chat, so it shows and sends real names. The file is read on each request, so an
edit to it shows on the next page load. Real names still never go to the bot's models (see driver.agent.run_state).
"""

import csv
from pathlib import Path


class RosterError(Exception):
    """The roster file is missing or cannot be read."""


def squad_key(squad: str):
    """Squads sort as numbers when they are numbers: 9 before 34."""
    return (0, int(squad), "") if squad.isdigit() else (1, 0, squad)


def load(path: Path) -> list[dict]:
    """Rows of {name, sender_id, squad}, sorted by name. Columns: name, sender_id, squad (a header row is needed)."""
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError as exc:
        raise RosterError(f"roster file not readable: {path.name} ({type(exc).__name__})") from exc
    members = []
    for n, row in enumerate(rows, 2):
        name = (row.get("name") or "").strip()
        sender_id = (row.get("sender_id") or "").strip()
        squad = (row.get("squad") or "").strip()
        if not name or not sender_id or not squad:
            raise RosterError(f"{path.name}: line {n} needs a name, a sender_id and a squad")
        members.append({"name": name, "sender_id": sender_id, "squad": squad})
    return sorted(members, key=lambda m: m["name"].lower())


def first_of_squad(members: list[dict], squad: str) -> dict | None:
    """The squad's first member in name order."""
    return next((m for m in members if m["squad"] == squad), None)
