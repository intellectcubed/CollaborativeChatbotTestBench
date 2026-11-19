"""Where things live, and the settings the driver reads from the environment (.env in the container).

Secrets (the Anthropic key) are read here and used only by the model client. They are never written to a file,
shown on the page, or logged.
"""

import os
from pathlib import Path

ROOT = Path(os.environ.get("DRIVER_ROOT", Path(__file__).resolve().parents[2]))
PROMPTS = ROOT / "prompts" / "bot"
CONFIG = ROOT / "config"
SCENARIOS = ROOT / "scenarios"
RUNS = ROOT / "runs"


def api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None


def budget_cap_usd() -> float:
    return float(os.environ.get("BOT_BUDGET_USD", "5"))


def roster_csv() -> Path:
    """The chat's roster file (name, sender_id, squad). By default the chatbot project's GroupMe roster, next to this one."""
    default = ROOT.parent / "CollaborativeAIChatbot" / "data" / "groupme_87780377_roster.csv"
    return Path(os.environ.get("ROSTER_CSV") or default)


def calendar_test_url() -> str:
    return os.environ.get("CALENDAR_TEST_URL", "http://localhost:7007")
