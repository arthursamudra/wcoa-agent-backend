from __future__ import annotations

import json
from typing import Any

from app.prompts.wcoa_prompt import SYSTEM_PROMPT, build_deterministic_context_payload
from app.services.evaluator import DeterministicEvaluation
from app.utils.schemas import ChatMessage


def build_messages(
    *,
    prompt: str,
    user_messages: list[ChatMessage],
    evaluation: DeterministicEvaluation,
    schema_summary: dict[str, Any] | None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    deterministic_context = build_deterministic_context_payload(
        prompt, evaluation, schema_summary
    )

    if user_messages:
        messages.extend([m.model_dump() for m in user_messages])
    elif prompt:
        messages.append({"role": "user", "content": prompt})
    else:
        messages.append(
            {
                "role": "user",
                "content": "Evaluate the procurement request using the provided deterministic context.",
            }
        )

    messages.append(
        {
            "role": "user",
            "content": (
                "Deterministic evaluation results and tenant dataset context in JSON. "
                "Use this as the factual basis for the answer and return only JSON:\n"
                + json.dumps(deterministic_context, ensure_ascii=False)
            ),
        }
    )

    return messages