from __future__ import annotations
import math

def annual_to_daily_rate(annual_rate: float | None) -> float:
    rate = float(annual_rate or 0.0)
    if rate <= 0:
        return 0.0
    return rate / 365.0


def compute_npv(amount: float | None, payment_day: int | None, annual_cost_of_capital: float | None) -> float | None:
    if amount is None:
        return None
    day = int(payment_day or 0)
    daily = annual_to_daily_rate(annual_cost_of_capital)
    if daily <= 0 or day <= 0:
        return round(amount, 4)
    return round(amount / math.pow(1 + daily, day), 4)
