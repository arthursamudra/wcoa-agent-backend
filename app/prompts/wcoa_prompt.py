from __future__ import annotations

from typing import Any

from app.services.evaluator import DeterministicEvaluation

SYSTEM_PROMPT = """
You are WCOA, the Working Capital Optimization Agent.

You support procurement decisions using deterministic financial tools plus tenant dataset context.

RULES:
- Treat deterministic tool outputs and evaluation results as the source of truth.
- Do not invent suppliers, prices, discounts, payment terms, lead times, risks, or financial metrics.
- If data is missing, weak, or ambiguous, state that explicitly in assumptions, questions, or data_quality_flags.
- Prefer the deterministic best option unless there is a clear data-quality reason not to.
- Return ONLY one valid JSON object.
- Do NOT return markdown.
- Do NOT return code fences.
- Do NOT return prose before or after the JSON.
- Your response must begin with { and end with }.

Return JSON using EXACTLY this schema:
{
  "decision": "string",
  "options": [
    {
      "supplier": "string",
      "rationale": "string",
      "estimatedUnitPrice": 0,
      "estimatedTotalCost": 0,
      "paymentTerms": "string",
      "leadTime": "string",
      "workingCapitalImpact": "string",
      "risks": ["string"]
    }
  ],
  "assumptions": ["string"],
  "questions": ["string"],
  "next_actions": ["string"],
  "data_quality_flags": ["string"]
}

FIELD RULES:
- decision: a concise recommendation summary
- options: ordered best to worst, with the first option as the recommended one
- estimatedUnitPrice: numeric only
- estimatedTotalCost: numeric only
- paymentTerms: text such as "30 days"
- leadTime: text such as "7 days"
- workingCapitalImpact: concise text summary from deterministic facts
- risks / assumptions / questions / next_actions / data_quality_flags: arrays of strings
- If a value is unavailable, use:
  - null for numeric fields if needed
  - empty array for list fields
  - a short explicit statement for text fields

Do not include any keys outside this schema.
"""


def _safe_number(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        num = float(value)
        return int(num) if num.is_integer() else num
    except Exception:
        return None


def build_deterministic_context_payload(
    prompt: str,
    evaluation: DeterministicEvaluation,
    schema_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    best_option = evaluation.best_option or {}

    normalized_best_option = {
        "supplier": best_option.get("supplier"),
        "estimatedUnitPrice": _safe_number(
            best_option.get("unit_price")
            or best_option.get("estimatedUnitPrice")
            or best_option.get("price_per_unit")
        ),
        "estimatedTotalCost": _safe_number(
            best_option.get("total_price")
            or best_option.get("estimatedTotalCost")
            or best_option.get("total_cost")
        ),
        "paymentTerms": str(
            best_option.get("payment_terms")
            or best_option.get("paymentTerms")
            or ""
        ),
        "leadTime": str(
            best_option.get("lead_time")
            or best_option.get("leadTime")
            or ""
        ),
        "workingCapitalImpact": str(
            best_option.get("working_capital_impact")
            or best_option.get("workingCapitalImpact")
            or ""
        ),
        "score": _safe_number(best_option.get("score")),
        "npv": _safe_number(best_option.get("npv")),
        "discountPercent": _safe_number(
            best_option.get("discount_percent")
            or best_option.get("discountPercent")
        ),
        "bnplImpact": best_option.get("bnpl_impact") or best_option.get("bnplImpact"),
    }

    return {
        "request": {
            "prompt": prompt,
            "quantity": evaluation.request_quantity,
        },
        "canonical_summary": evaluation.canonical_summary,
        "schema_summary": schema_summary or {},
        "financial_context": evaluation.financial_context,
        "tool_results": evaluation.tool_results,
        "suppliers_considered": evaluation.suppliers_considered[:25],
        "evaluations": evaluation.evaluations[:10],
        "best_option": normalized_best_option,
        "data_quality_flags": evaluation.data_quality_flags,
        "instructions": {
            "ranking_source": "Use deterministic evaluations sorted by score descending.",
            "best_option_source": "Use deterministic best_option as the recommended option unless it is null.",
            "explanation_scope": "Explain liquidity, NPV, payment timing, BNPL, discounts, and supplier ranking only from supplied deterministic facts.",
            "response_format": "Return only JSON matching the required schema.",
        },
    }