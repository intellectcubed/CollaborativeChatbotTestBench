"""The model client: the Anthropic Messages API over HTTP, with a budget that stops every model call once it is spent.

Prices come from config/model_prices.json. A model with no price set is refused, so the cost is never guessed.
The API key is sent in a request header only. Errors never include the key, the headers, or the request body.
"""

import json
import logging
import threading
from pathlib import Path

import httpx

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
log = logging.getLogger("driver.llm")


class BudgetExceeded(Exception):
    """The global budget is spent. No more model calls are made."""


class PriceMissing(Exception):
    """No price is set for this model in config/model_prices.json."""


class LlmError(Exception):
    """The model service refused or failed a call."""


def load_prices(path: Path) -> dict:
    if not path.exists():
        return {}
    return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}


def cost_of(usage: dict, model: str, prices: dict) -> float:
    price = prices.get(model) or {}
    if price.get("input_per_mtok") is None or price.get("output_per_mtok") is None:
        raise PriceMissing(model)
    return (usage.get("input_tokens", 0) * price["input_per_mtok"]
            + usage.get("output_tokens", 0) * price["output_per_mtok"]) / 1_000_000


class Budget:
    """Money spent across all runs, kept in a file so a restart does not reset it."""

    def __init__(self, cap_usd: float, path: Path) -> None:
        self.cap = cap_usd
        self.path = path
        self._lock = threading.Lock()
        self.spent = float(json.loads(path.read_text())["spent_usd"]) if path.exists() else 0.0

    def check(self) -> None:
        if self.spent >= self.cap:
            raise BudgetExceeded(f"budget reached: ${self.spent:.2f} of ${self.cap:.2f} spent")

    def add(self, usd: float) -> None:
        with self._lock:
            self.spent += usd
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"spent_usd": round(self.spent, 6)}))


def _api_error(resp: httpx.Response) -> str:
    try:
        message = resp.json().get("error", {}).get("message") or ""
    except ValueError:
        message = ""
    return message[:300]


class LlmClient:
    def __init__(self, api_key: str, prices: dict, budget: Budget, http: httpx.Client | None = None) -> None:
        self._key = api_key
        self.prices = prices
        self.budget = budget
        self.http = http or httpx.Client(timeout=120.0)

    def _priced(self, model: str) -> bool:
        price = self.prices.get(model) or {}
        return price.get("input_per_mtok") is not None and price.get("output_per_mtok") is not None

    def call(self, *, model: str, system: str, messages: list, tools: list, max_tokens: int,
             temperature: float | None) -> dict:
        self.budget.check()
        if not self._priced(model):
            raise PriceMissing(model)  # refused before any call is made
        body = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages, "tools": tools}
        # temperature is not sent: the API refuses it for these models ("deprecated for this model"), so the
        # temperature settings in a goal file are kept for reference only.
        headers = {"x-api-key": self._key, "anthropic-version": API_VERSION, "content-type": "application/json"}
        try:
            resp = self.http.post(API_URL, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise LlmError(f"model service not reachable: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            # The API's own error message says what was wrong (for example a parameter it refuses). It does not
            # contain the key, so it is safe to show and to log.
            detail = _api_error(resp)
            log.warning("model %s refused: HTTP %s: %s", model, resp.status_code, detail)
            raise LlmError(f"model call refused: HTTP {resp.status_code}: {detail}")
        data = resp.json()
        cost = cost_of(data.get("usage", {}), model, self.prices)
        self.budget.add(cost)
        log.info("model %s: stop=%s in=%s out=%s cost=$%.5f", model, data.get("stop_reason"),
                 data.get("usage", {}).get("input_tokens"), data.get("usage", {}).get("output_tokens"), cost)
        return {"content": data.get("content", []), "stop_reason": data.get("stop_reason"),
                "usage": data.get("usage", {}), "cost": cost}
