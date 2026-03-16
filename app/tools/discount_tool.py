from __future__ import annotations

def apply_discount(amount: float | None, discount_percent: float | None) -> float | None:
    if amount is None:
        return None
    pct = float(discount_percent or 0.0)
    if pct <= 0:
        return round(amount, 4)
    return round(amount * (1 - pct / 100.0), 4)
