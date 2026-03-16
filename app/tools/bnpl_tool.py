from __future__ import annotations

def compute_bnpl_financing_cost(amount: float | None, bnpl_rate: float | None) -> float:
    if amount is None:
        return 0.0
    rate = float(bnpl_rate or 0.0)
    if rate <= 0:
        return 0.0
    return round(amount * rate / 100.0, 4)


def apply_bnpl_cost_adjustment(amount: float | None, bnpl_rate: float | None) -> float | None:
    if amount is None:
        return None
    return round(amount + compute_bnpl_financing_cost(amount, bnpl_rate), 4)
