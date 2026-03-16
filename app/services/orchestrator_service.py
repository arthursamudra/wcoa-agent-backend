from __future__ import annotations

import json
from typing import Any

from app.services.evaluator import evaluate_canonical
from app.services.prompt_builder import build_messages
from app.services.watsonx_service import chat_completion
from app.utils.schemas import ChatMessage


def run_wcoa_chat(
    *,
    canonical_bytes: bytes,
    prompt: str,
    user_messages: list[ChatMessage],
    schema_summary_bytes: bytes | None,
    temperature: float | None,
) -> dict[str, Any]:
    schema_summary = None
    if schema_summary_bytes:
        try:
            schema_summary = json.loads(schema_summary_bytes.decode('utf-8'))
        except Exception:
            schema_summary = None

    effective_prompt = prompt or ' '.join(m.content for m in user_messages if m.role == 'user').strip()
    evaluation = evaluate_canonical(canonical_bytes, effective_prompt)
    messages = build_messages(
        prompt=effective_prompt,
        user_messages=user_messages,
        evaluation=evaluation,
        schema_summary=schema_summary,
    )
    model_result = chat_completion(messages, temperature=temperature)
    model_result['deterministic'] = {
        'best_option': evaluation.best_option,
        'evaluations': evaluation.evaluations,
        'tool_results': evaluation.tool_results,
        'data_quality_flags': evaluation.data_quality_flags,
        'request_quantity': evaluation.request_quantity,
    }
    return model_result
