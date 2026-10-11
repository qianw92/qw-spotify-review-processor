"""Spend guardrails shared by every paid call.

- Every call is appended to budget/spend_ledger.csv (provider kept separate).
- Before dispatch, the caller reserves a worst-case cost; the call is refused if
  spent + reserved + this reservation would exceed the run cap or the project cap.
- Costs use list prices from budget/budget.json; free-plan credits are never subtracted.
"""
import csv
import datetime
import json
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "budget" / "spend_ledger.csv"
CONFIG = ROOT / "budget" / "budget.json"
FIELDS = ["ts", "provider", "model", "purpose", "request_id", "input_tokens", "output_tokens",
          "price_in_per_m", "price_out_per_m", "cost_usd"]


_LEDGER_LOCK = threading.Lock()


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
    with _LEDGER_LOCK, open(LEDGER, "a", newline="", encoding="utf-8") as f:
        new = f.tell() == 0
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({"ts": datetime.datetime.now().isoformat(timespec="seconds"), "provider": provider, "model": model,
                    "purpose": purpose, "request_id": request_id, "input_tokens": input_tokens,
                    "output_tokens": output_tokens, "price_in_per_m": pin, "price_out_per_m": pout,
                    "cost_usd": f"{usd:.8f}"})
    return usd


class Guard:
    """One spend ledger per run, shared by every worker.

    Workers reserve a worst-case cost BEFORE dispatch. New work is refused when
    spent + already reserved (in flight) + this reservation would exceed the run cap or the project cap.
    """

    def __init__(self, run_cap_usd):
        self.project_cap = config()["project_cap_usd"]
        self.run_cap = run_cap_usd
        self.start_total = spent()
        self.run_spent = 0.0
        self.reserved = 0.0
        self._lock = threading.Lock()

    def _would_exceed(self, amount):
        if self.run_spent + self.reserved + amount > self.run_cap:
            return (f"run cap ${self.run_cap:.4f} would be exceeded (spent ${self.run_spent:.6f} + in flight "
                    f"${self.reserved:.6f} + next ${amount:.6f})")
        if self.start_total + self.run_spent + self.reserved + amount > self.project_cap:
            return f"project cap ${self.project_cap:.2f} would be exceeded"
        return None

    def check(self, reservation_usd):
        with self._lock:
            reason = self._would_exceed(reservation_usd)
        if reason:
            raise BudgetExceeded(reason)

    def reserve(self, amount):
        with self._lock:
            reason = self._would_exceed(amount)
            if reason:
                raise BudgetExceeded(reason)
            self.reserved += amount

    def release(self, amount):
        with self._lock:
            self.reserved -= amount

    def add(self, usd):
        with self._lock:
            self.run_spent += usd
