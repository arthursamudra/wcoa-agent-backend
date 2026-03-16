from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.tools import (
    apply_bnpl_cost_adjustment,
    apply_discount,
    compute_npv,
    rank_supplier_options,
    score_supplier_option,
    simulate_cashflow_impact,
)


@dataclass
class SupplierScenario:
    supplier: str
    scenario: str
    unit_price: float | None
    quantity: float
    total_cost: float | None
    payment_days: int | None
    lead_time_days: int | None
    discount_percent: float
    bnpl_rate: float
    npv: float | None
    min_cash: float | None
    liquidity_breached: bool
    score: float | None
    tool_outputs: dict[str, Any]
    risk_flags: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "supplier": self.supplier,
            "scenario": self.scenario,
            "unit_price": self.unit_price,
            "quantity": self.quantity,
            "total_cost": self.total_cost,
            "payment_days": self.payment_days,
            "lead_time_days": self.lead_time_days,
            "discount_percent": self.discount_percent,
            "bnpl_rate": self.bnpl_rate,
            "npv": self.npv,
            "min_cash": self.min_cash,
            "liquidity_breached": self.liquidity_breached,
            "score": self.score,
            "tool_outputs": self.tool_outputs,
            "risk_flags": self.risk_flags,
        }


@dataclass
class DeterministicEvaluation:
    request_quantity: float
    suppliers_considered: list[dict[str, Any]]
    financial_context: dict[str, Any]
    tool_results: dict[str, Any]
    evaluations: list[dict[str, Any]]
    best_option: dict[str, Any] | None
    data_quality_flags: list[str]
    canonical_summary: dict[str, Any]


# ---------- public entrypoint ----------

def evaluate_canonical(canonical_bytes: bytes, prompt: str) -> DeterministicEvaluation:
    canonical = json.loads(canonical_bytes.decode("utf-8"))
    sheets = canonical.get("sheets", {})

    suppliers, supplier_flags = _extract_suppliers(sheets)
    financials, financial_flags = _extract_financials(sheets)
    quantity = extract_requested_quantity(prompt)

    scenarios: list[SupplierScenario] = []
    tool_results: dict[str, Any] = {
        "discount_tool": [],
        "bnpl_tool": [],
        "npv_tool": [],
        "cashflow_tool": [],
        "supplier_scoring_tool": [],
    }

    for supplier in suppliers:
        supplier_name = str(
            supplier.get("supplier")
            or supplier.get("vendor")
            or supplier.get("name")
            or "Unknown Supplier"
        )
        scenario_name = str(supplier.get("scenario") or "base")

        row_quantity = _to_float(supplier.get("quantity"))
        effective_quantity = quantity if quantity and quantity > 0 else (row_quantity or 1.0)

        unit_price = _to_float(supplier.get("unit_price"))
        quoted_total_cost = _to_float(supplier.get("total_cost"))
        base_total = quoted_total_cost
        if base_total is None and unit_price is not None:
            base_total = unit_price * effective_quantity

        discount_pct = _to_float(supplier.get("discount_percent")) or 0.0
        discounted_total = apply_discount(base_total, discount_pct)

        bnpl_rate = _to_float(supplier.get("bnpl_rate")) or 0.0
        adjusted_total = apply_bnpl_cost_adjustment(discounted_total, bnpl_rate)

        payment_days = _to_int(supplier.get("payment_days"))
        lead_time_days = _to_int(supplier.get("lead_time_days"))

        npv = compute_npv(
            adjusted_total,
            payment_days,
            financials.get("costOfCapital", 0.12),
        )

        cashflow = simulate_cashflow_impact(financials, adjusted_total, payment_days)

        scoring = score_supplier_option(
            total_cost=adjusted_total,
            npv=npv,
            min_cash=_to_float(cashflow.get("minCash")),
            liquidity_breached=bool(cashflow.get("liquidityBreached")),
            lead_time_days=lead_time_days,
        )

        risk_flags = _risk_flags(supplier, bool(cashflow.get("liquidityBreached")))

        tool_outputs = {
            "discount_tool": {
                "base_total": base_total,
                "discount_percent": discount_pct,
                "discounted_total": discounted_total,
            },
            "bnpl_tool": {
                "bnpl_rate": bnpl_rate,
                "bnpl_adjusted_total": adjusted_total,
            },
            "npv_tool": {
                "payment_days": payment_days,
                "cost_of_capital": financials.get("costOfCapital", 0.12),
                "npv": npv,
            },
            "cashflow_tool": cashflow,
            "supplier_scoring_tool": scoring,
        }

        tool_results["discount_tool"].append({"supplier": supplier_name, **tool_outputs["discount_tool"]})
        tool_results["bnpl_tool"].append({"supplier": supplier_name, **tool_outputs["bnpl_tool"]})
        tool_results["npv_tool"].append({"supplier": supplier_name, **tool_outputs["npv_tool"]})
        tool_results["cashflow_tool"].append({"supplier": supplier_name, **cashflow})
        tool_results["supplier_scoring_tool"].append({"supplier": supplier_name, **scoring})

        scenarios.append(
            SupplierScenario(
                supplier=supplier_name,
                scenario=scenario_name,
                unit_price=unit_price,
                quantity=effective_quantity,
                total_cost=adjusted_total,
                payment_days=payment_days,
                lead_time_days=lead_time_days,
                discount_percent=discount_pct,
                bnpl_rate=bnpl_rate,
                npv=npv,
                min_cash=_to_float(cashflow.get("minCash")),
                liquidity_breached=bool(cashflow.get("liquidityBreached")),
                score=_to_float(scoring.get("score")),
                tool_outputs=tool_outputs,
                risk_flags=risk_flags,
            )
        )

    ranked = rank_supplier_options([s.as_dict() for s in scenarios])
    best = ranked[0] if ranked else None

    canonical_summary = {
        "sheet_names": list(sheets.keys()),
        "sheet_count": len(sheets),
        "supplier_count": len(suppliers),
        "detected_finance_fields": sorted(
            k for k, v in financials.items() if v and k not in ("ap", "ar", "obligations")
        ),
    }

    return DeterministicEvaluation(
        request_quantity=quantity,
        suppliers_considered=suppliers,
        financial_context=financials,
        tool_results=tool_results,
        evaluations=ranked,
        best_option=best,
        data_quality_flags=supplier_flags + financial_flags,
        canonical_summary=canonical_summary,
    )


# ---------- prompt quantity ----------

def extract_requested_quantity(prompt: str) -> float:
    match = re.search(r"\b(\d+(?:\.\d+)?)\b", prompt or "")
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return 1.0


# ---------- supplier extraction ----------

def _extract_suppliers(sheets: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    flags: list[str] = []
    supplier_rows: list[dict[str, Any]] = []

    for sheet_name, sheet_payload in sheets.items():
        rows = sheet_payload.get("rows", []) or []
        if not rows:
            continue

        normalized = _normalize_rows(rows)
        normalized_suppliers = [_normalize_supplier_row(r) for r in normalized]

        supplierish = any(
            any(
                key in row
                for key in (
                    "supplier",
                    "vendor",
                    "unit_price",
                    "total_cost",
                    "payment_days",
                    "lead_time_days",
                    "discount_percent",
                    "bnpl_rate",
                )
            )
            for row in normalized_suppliers[:10]
        ) or any(tok in sheet_name.lower() for tok in ("supplier", "vendor", "quote", "pricing"))

        if supplierish:
            supplier_rows.extend([r for r in normalized_suppliers if r.get("supplier")])

    if not supplier_rows:
        flags.append("No supplier-like rows detected; recommendations may be generic.")
        return [], flags

    if all(_to_float(r.get("unit_price")) is None for r in supplier_rows):
        flags.append("unit_price missing for all suppliers.")
    if all(_to_float(r.get("total_cost")) is None for r in supplier_rows):
        flags.append("total_cost missing for all suppliers.")
    if all(_to_int(r.get("payment_days")) is None for r in supplier_rows):
        flags.append("payment_days missing for all suppliers.")
    if all(_to_int(r.get("lead_time_days")) is None for r in supplier_rows):
        flags.append("lead_time_days missing for all suppliers.")

    return supplier_rows[:200], flags


def _normalize_supplier_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "supplier": _pick_first(row, "supplier", "vendor", "name", "suppliername", "vendorname"),
        "scenario": _pick_first(row, "scenario", "case", "option") or "base",
        "unit_price": _pick_first(row, "unit_price", "unitprice", "price_per_unit", "price"),
        "quantity": _pick_first(row, "quantity", "qty", "units"),
        "total_cost": _pick_first(row, "total_cost", "quoted_total_cost", "total", "totalprice", "amount"),
        "payment_days": _pick_first(
            row,
            "payment_days",
            "payment_day",
            "payment_term_days",
            "paymenttermdays",
            "payment_terms",
            "paymentterms",
        ),
        "lead_time_days": _pick_first(
            row,
            "lead_time_days",
            "leadtime_days",
            "lead_time",
            "leadtime",
            "delivery_days",
            "deliverydays",
        ),
        "discount_percent": _pick_first(
            row,
            "discount_percent",
            "discountpercent",
            "discount",
            "discount_pct",
            "discountpct",
        ),
        "discount_days": _pick_first(row, "discount_days", "discountdays"),
        "bnpl_rate": _pick_first(row, "bnpl_rate", "bnplrate", "financing_rate", "financingrate"),
        "bnpl_days": _pick_first(row, "bnpl_days", "bnpldays"),
    }


# ---------- financial extraction ----------

def _extract_financials(sheets: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    flags: list[str] = []
    financials: dict[str, Any] = {
        "openingCash": 0.0,
        "liquidityBuffer": 0.0,
        "costOfCapital": 0.12,
        "ap": [],
        "ar": [],
        "obligations": [],
    }

    for sheet_name, sheet_payload in sheets.items():
        rows = sheet_payload.get("rows", []) or []
        if not rows:
            continue

        normalized = _normalize_rows(rows)
        for row in normalized:
            _capture_scalar_financials(financials, row)
            _capture_cashflow_row(financials, row)

    if financials["openingCash"] == 0.0:
        flags.append("Opening cash not found explicitly; defaulted to 0.")
    if financials["liquidityBuffer"] == 0.0:
        flags.append("Liquidity buffer not found explicitly; defaulted to 0.")
    if financials.get("costOfCapital", 0.12) == 0.12:
        flags.append("Cost of capital not found explicitly; defaulted to 0.12.")

    return financials, flags


def _capture_scalar_financials(financials: dict[str, Any], row: dict[str, Any]) -> None:
    # Handle key-value shaped financial rows:
    # {"key":"openingCash","value":"4000000.0","notes":""}
    kv_key = _normalize_token(row.get("key"))
    kv_value = _to_float(row.get("value"))

    if kv_key and kv_value is not None:
        if kv_key in ("openingcash", "opening_cash", "cashonhand", "cash_on_hand"):
            financials["openingCash"] = kv_value
            return
        if kv_key in ("liquiditybuffer", "liquidity_buffer", "minimumcashbuffer", "minimum_cash_buffer"):
            financials["liquidityBuffer"] = kv_value
            return
        if kv_key in ("costofcapital", "cost_of_capital", "discount_rate", "discountrate", "wacc"):
            financials["costOfCapital"] = kv_value if kv_value < 1 else kv_value / 100.0
            return

    # Handle scalar columns if they ever appear directly
    for key, value in row.items():
        val = _to_float(value)
        if val is None:
            continue

        norm_key = _normalize_token(key)
        if norm_key in ("openingcash", "opening_cash", "cashonhand", "cash_on_hand") and not financials.get("openingCash"):
            financials["openingCash"] = val
        elif norm_key in ("liquiditybuffer", "liquidity_buffer", "minimumcashbuffer", "minimum_cash_buffer") and not financials.get("liquidityBuffer"):
            financials["liquidityBuffer"] = val
        elif norm_key in ("costofcapital", "cost_of_capital", "discount_rate", "discountrate", "wacc") and financials.get("costOfCapital", 0.12) == 0.12:
            financials["costOfCapital"] = val if val < 1 else val / 100.0


def _capture_cashflow_row(financials: dict[str, Any], row: dict[str, Any]) -> None:
    # First handle direct typed rows if they exist
    kind = str(row.get("type") or row.get("flow_type") or row.get("category") or "").strip().lower()
    amount = _to_float(row.get("amount"))
    due_in_days = _to_int(row.get("due_in_days") or row.get("dueindays") or row.get("days") or row.get("day"))

    if amount is not None and due_in_days is not None and kind:
        target = None
        if kind in ("ap", "accounts_payable", "payable"):
            target = "ap"
        elif kind in ("ar", "accounts_receivable", "receivable"):
            target = "ar"
        elif kind in ("obligation", "obligations", "expense", "opex"):
            target = "obligations"
        if target:
            financials[target].append({"amount": amount, "dueInDays": due_in_days})
            return

    # Then handle key-value style rows from your uploaded Financials sheet
    # e.g. key=AP_Cloud, value=2200000.0, notes=12.0
    kv_key = str(row.get("key") or "").strip()
    kv_key_norm = _normalize_token(kv_key)
    kv_amount = _to_float(row.get("value"))
    kv_days = _to_int(row.get("notes"))

    if not kv_key_norm or kv_amount is None or kv_days is None:
        return

    target = None
    if kv_key_norm.startswith("ap_") or kv_key_norm.startswith("ap"):
        target = "ap"
    elif kv_key_norm.startswith("ar_") or kv_key_norm.startswith("ar"):
        target = "ar"
    else:
        # treat other obligations like Payroll, GST, rent etc. as obligations
        target = "obligations"

    financials[target].append(
        {
            "label": kv_key,
            "amount": kv_amount,
            "dueInDays": kv_days,
        }
    )


# ---------- helpers ----------

def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        cleaned: dict[str, Any] = {}
        for key, value in row.items():
            norm_key = re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")
            if norm_key:
                cleaned[norm_key] = value
        if cleaned:
            normalized.append(cleaned)
    return normalized


def _risk_flags(supplier: dict[str, Any], liquidity_breached: bool) -> list[str]:
    flags: list[str] = []

    if liquidity_breached:
        flags.append("Liquidity buffer breached under this scenario.")

    lead = _to_int(supplier.get("lead_time_days"))
    if lead is not None and lead > 45:
        flags.append("Long lead time may impact service levels.")

    payment_days = _to_int(supplier.get("payment_days"))
    if payment_days is not None and payment_days < 15:
        flags.append("Short payment terms may tighten near-term cashflow.")

    if _to_float(supplier.get("unit_price")) is None and _to_float(supplier.get("total_cost")) is None:
        flags.append("Commercial pricing data incomplete for this supplier.")

    return flags


def _pick_first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, "", "null"):
            return row[key]
    return None


def _normalize_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "", str(value).strip().lower())


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    text = (
        text.replace(",", "")
        .replace("₹", "")
        .replace("$", "")
        .replace("%", "")
    )

    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    parsed = _to_float(value)
    return int(parsed) if parsed is not None else None