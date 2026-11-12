"""Batch files: one message per line, in the format described in docs/design/chatbot-driver.md (section 2).

{"kind": "batch", "name": "...", "description": "..."}          <- optional first line
{"id": "batch-0001", "created_at": "2026-03-14T13:00:00-04:00", "member": "Member-7", "text": "..."}

Times without an offset are read as New York time, as the replay tool reads them.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
REQUIRED = ("id", "created_at", "member", "text")


class BatchError(ValueError):
    """The file cannot be opened. `errors` lists every problem, with line numbers."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class Message:
    id: str
    created_at: datetime  # always timezone-aware, in New York time
    member: str  # roster pseudonym, for example Member-7
    text: str


@dataclass
class Batch:
    name: str
    description: str
    messages: list[Message] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # what was skipped when a raw export was read


def parse(content: str, default_name: str = "batch") -> Batch:
    """Read a batch from text. Raises BatchError listing every problem; nothing is partly opened."""
    name, description = default_name, ""
    messages: list[Message] = []
    errors: list[str] = []
    seen: set[str] = set()
    first = True
    for number, raw in enumerate(content.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"line {number}: not JSON ({exc.msg})")
            continue
        if not isinstance(obj, dict):
            errors.append(f"line {number}: expected a JSON object")
            continue
        if first and obj.get("kind") == "batch":
            name = str(obj.get("name") or name)
            description = str(obj.get("description") or "")
            first = False
            continue
        first = False
        missing = [k for k in REQUIRED if not obj.get(k)]
        if missing:
            errors.append(f"line {number}: missing {', '.join(missing)}")
            continue
        try:
            when = datetime.fromisoformat(str(obj["created_at"]))
        except ValueError:
            errors.append(f"line {number}: created_at is not an ISO time")
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=NY)
        message_id = str(obj["id"])
        if message_id in seen:
            errors.append(f"line {number}: duplicate id {message_id}")
            continue
        seen.add(message_id)
        messages.append(Message(message_id, when.astimezone(NY), str(obj["member"]), str(obj["text"])))
    if errors:
        raise BatchError(errors)
    return Batch(name, description, messages)


def is_groupme_export(content: str) -> bool:
    """True when the first line is a raw GroupMe export line (it has sender_id and sender_type)."""
    for raw in content.splitlines():
        if raw.strip():
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                return False
            return isinstance(obj, dict) and "sender_id" in obj and "sender_type" in obj
    return False


def parse_groupme(content: str, default_name: str, pseudonym_for: dict[str, str]) -> Batch:
    """Read a raw GroupMe export (one JSON object per line) into a batch.

    Sender IDs are replaced by roster pseudonyms here, in memory. Nothing is written to disk, and names
    and sender IDs are not kept. Only user messages with text from roster senders are kept; the rest
    are counted in `notes`. `pseudonym_for` maps sender ID (as a string) to pseudonym.
    """
    messages: list[Message] = []
    errors: list[str] = []
    seen: set[str] = set()
    skipped = {"system or bot messages": 0, "deleted messages": 0, "messages with no text": 0,
               "messages from senders not on the roster": 0}
    for number, raw in enumerate(content.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"line {number}: not JSON ({exc.msg})")
            continue
        if not isinstance(obj, dict):
            errors.append(f"line {number}: expected a JSON object")
            continue
        if obj.get("sender_type") != "user":
            skipped["system or bot messages"] += 1
            continue
        if obj.get("deleted_at"):
            skipped["deleted messages"] += 1
            continue
        text = obj.get("text")
        if not text:
            skipped["messages with no text"] += 1
            continue
        member = pseudonym_for.get(str(obj.get("sender_id")))
        if member is None:
            skipped["messages from senders not on the roster"] += 1
            continue
        message_id = str(obj.get("id") or "")
        if not message_id:
            errors.append(f"line {number}: missing id")
            continue
        if message_id in seen:
            errors.append(f"line {number}: duplicate id {message_id}")
            continue
        try:
            when = datetime.fromtimestamp(int(obj["created_at"]), NY)
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            errors.append(f"line {number}: created_at is not a Unix time")
            continue
        seen.add(message_id)
        messages.append(Message(message_id, when, member, str(text)))
    if errors:
        raise BatchError(errors)
    messages.sort(key=lambda m: m.created_at)  # stable: equal times keep file order
    notes = [f"skipped {n} {what}" for what, n in skipped.items() if n]
    return Batch(default_name, "GroupMe export, sender IDs replaced by roster pseudonyms", messages, notes)

