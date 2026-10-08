"""Live Gemini cost tracking.

Prices are USD per 1M tokens from https://ai.google.dev/gemini-api/docs/pricing (standard paid tier, checked
2026-10-01). Output tokens already include thinking tokens (pydantic-ai maps thoughtsTokenCount into them).
Update PRICES if Google changes them; unknown models are counted in tokens but not priced.
"""
from __future__ import annotations

import threading
from datetime import date

FLASH_PROMO_END = date(2026, 12, 31)


def price_per_m(model: str, input_tokens: int, today: date | None = None) -> tuple[float, float] | None:
    today = today or date.today()
    if model.startswith("gemini-3.8-flash"):
        return (0.75, 3.75) if today <= FLASH_PROMO_END else (1.50, 7.50)
    if model.startswith("gemini-3.1-pro"):
        return (2.0, 12.0) if input_tokens <= 200_000 else (4.0, 18.0)
    return None


class CostMeter:
    """Thread-safe. add() is called after every model call; prints one console line per call."""

    def __init__(self, label: str = "", echo: bool = True):
        self.label, self.echo = label, echo
        self.input = self.output = self.calls = 0
        self.usd = 0.0
        self.unpriced_calls = 0
        self.by_model: dict[str, dict] = {}
        self.events: list[dict] = []
        self._lock = threading.Lock()

    def add(self, stage: str, model: str, usage) -> float | None:
        i, o = int(usage.input_tokens or 0), int(usage.output_tokens or 0)
        p = price_per_m(model, i)
        cost = None if p is None else (i * p[0] + o * p[1]) / 1_000_000
        with self._lock:
            self.calls += 1
            self.input += i
            self.output += o
            m = self.by_model.setdefault(model, {"calls": 0, "input": 0, "output": 0, "usd": 0.0})
            m["calls"] += 1
            m["input"] += i
            m["output"] += o
            if cost is None:
                self.unpriced_calls += 1
            else:
                self.usd += cost
                m["usd"] += cost
            self.events.append({"n": self.calls, "stage": stage, "model": model, "in": i, "out": o,
                                "usd": None if cost is None else round(cost, 6), "totalUsd": round(self.usd, 6)})
            line = (f"[cost{' ' + self.label if self.label else ''}] {stage:<22} {model:<22} "
                    f"in {i:>7,}  out {o:>7,}  {'$%.4f' % cost if cost is not None else 'unpriced':>9}"
                    f"   | total {self.calls} calls  in {self.input:,}  out {self.output:,}  ${self.usd:.4f}")
        if self.echo:
            print(line, flush=True)
        return cost

    def snapshot(self) -> dict:
        with self._lock:
            return {"calls": self.calls, "inputTokens": self.input, "outputTokens": self.output,
                    "usd": round(self.usd, 4), "unpricedCalls": self.unpriced_calls,
                    "byModel": {k: {**v, "usd": round(v["usd"], 4)} for k, v in self.by_model.items()},
                    "events": list(self.events)}

    def summary_line(self) -> str:
        s = self.snapshot()
        extra = f" (+{s['unpricedCalls']} unpriced calls)" if s["unpricedCalls"] else ""
        return (f"[cost{' ' + self.label if self.label else ''}] DONE  {s['calls']} calls  in {s['inputTokens']:,}  "
                f"out {s['outputTokens']:,}  total ${s['usd']:.4f}{extra}")
