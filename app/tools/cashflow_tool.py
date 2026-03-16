from __future__ import annotations
from typing import Any

def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace("₹", "").replace("$", ""))
    except Exception:
        return None


def _to_int(value: Any) -> int | None:
    parsed = _to_float(value)
    return int(parsed) if parsed is not None else None


def simulate_cashflow_impact(financial_context: dict[str, Any], payment_amount: float | None, payment_day: int | None, horizon_days: int = 120) -> dict[str, Any]:
    opening_cash = _to_float(financial_context.get('openingCash')) or 0.0
    liquidity_buffer = _to_float(financial_context.get('liquidityBuffer')) or 0.0

    cash = opening_cash
    min_cash = cash
    cash_series: list[float] = []

    for day in range(1, horizon_days + 1):
        for section in ('ap', 'ar', 'obligations'):
            sign = 1 if section == 'ar' else -1
            for item in financial_context.get(section, []) or []:
                due_day = _to_int(item.get('dueInDays')) or 0
                amount = _to_float(item.get('amount')) or 0.0
                if due_day == day:
                    cash += sign * amount
        if payment_amount is not None and (payment_day or 0) == day:
            cash -= payment_amount
        min_cash = min(min_cash, cash)
        cash_series.append(round(cash, 4))

    return {
        'openingCash': round(opening_cash, 4),
        'liquidityBuffer': round(liquidity_buffer, 4),
        'minCash': round(min_cash, 4),
        'endingCash': round(cash, 4),
        'liquidityBreached': min_cash < liquidity_buffer,
        'cashSeriesPreview': cash_series[:15],
    }
