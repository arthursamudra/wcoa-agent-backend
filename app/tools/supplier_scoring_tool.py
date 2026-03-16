from __future__ import annotations
from typing import Any

def score_supplier_option(*, total_cost: float | None, npv: float | None, min_cash: float | None, liquidity_breached: bool, lead_time_days: int | None) -> dict[str, float | None]:
    # Higher is better. Weighted for finance-first WCOA use case.
    if total_cost is None and npv is None:
        return {
            'score': None,
            'costScore': None,
            'npvScore': None,
            'liquidityScore': None,
            'speedScore': None,
        }

    cost_score = None if total_cost is None else max(0.0, min(10.0, 10.0 - (total_cost / 1_000_000.0)))
    npv_score = None if npv is None else max(0.0, min(10.0, npv / 1_000_000.0))
    liquidity_score = 1.0 if liquidity_breached else (9.0 if (min_cash or 0) > 0 else 6.0)
    speed_score = 5.0 if lead_time_days is None else max(1.0, min(10.0, 10.0 - (lead_time_days / 10.0)))

    components = [v for v in (cost_score, npv_score, liquidity_score, speed_score) if v is not None]
    final_score = round(sum(components) / len(components), 4) if components else None
    return {
        'score': final_score,
        'costScore': None if cost_score is None else round(cost_score, 4),
        'npvScore': None if npv_score is None else round(npv_score, 4),
        'liquidityScore': round(liquidity_score, 4),
        'speedScore': round(speed_score, 4),
    }


def rank_supplier_options(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (row.get('score') is None, -(row.get('score') or -1e9), row.get('total_cost') or float('inf')))
