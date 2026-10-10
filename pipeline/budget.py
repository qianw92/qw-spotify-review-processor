"""Spend guardrails shared by every paid call.

- Every call is appended to budget/spend_ledger.csv (provider kept separate).
- Before dispatch, the caller reserves a worst-case cost; the call is refused if
  spent + reserved + this reservation would exceed the run cap or the project cap.
- Costs use list prices from budget/budget.json; free-plan credits are never subtracted.
"""
import csv
import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "budget" / "spend_ledger.csv"
CONFIG = ROOT / "budget" / "budget.json"
FIELDS = ["ts", "provider", "model", "purpose", "request_id", "input_tokens", "output_tokens",
          "price_in_per_m", "price_out_per_m", "cost_usd"]


class BudgetExceeded(RuntimeError):
    pass


def config():
    return json.loads(CONFIG.read_text())


def price(provider):
    p = config()["providers"][provider]
    return p["price_in_per_m"], p["price_out_per_m"]


def cost(provider, input_tokens, output_tokens):
    pin, pout = price(provider)
    return input_tokens * pin / 1e6 + output_tokens * pout / 1e6


def spent(provider=None):
    if not LEDGER.exists():
        return 0.0
    rows = csv.DictReader(open(LEDGER, encoding="utf-8"))
    return sum(float(r["cost_usd"]) for r in rows if provider is None or r["provider"] == provider)


def record(provider, model, purpose, request_id, input_tokens, output_tokens):
    pin, pout = price(provider)
    usd = cost(provider, input_tokens, output_tokens)
    new = not LEDGER.exists()
    with open(LEDGER, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({"ts": datetime.datetime.now().isoformat(timespec="seconds"), "provider": provider, "model": model,
                    "purpose": purpose, "request_id": request_id, "input_tokens": input_tokens,
                    "output_tokens": output_tokens, "price_in_per_m": pin, "price_out_per_m": pout,
                    "cost_usd": f"{usd:.8f}"})
    return usd


class Guard:
    """Tracks one run's spend against its own cap and the project cap."""

    def __init__(self, run_cap_usd):
        self.project_cap = config()["project_cap_usd"]
        self.run_cap = run_cap_usd
        self.start_total = spent()
        self.run_spent = 0.0

    def check(self, reservation_usd):
        if self.run_spent + reservation_usd > self.run_cap:
            raise BudgetExceeded(f"run cap ${self.run_cap:.4f} would be exceeded "
                                 f"(spent ${self.run_spent:.6f} + next ${reservation_usd:.6f})")
        if self.start_total + self.run_spent + reservation_usd > self.project_cap:
            raise BudgetExceeded(f"project cap ${self.project_cap:.2f} would be exceeded")

    def add(self, usd):
        self.run_spent += usd
