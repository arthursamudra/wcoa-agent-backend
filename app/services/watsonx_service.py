from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, List

import structlog
from pydantic import ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference

from app.core.config import settings
from app.utils.schemas import WCOAAgentResponse

log = structlog.get_logger()


class WatsonxError(Exception):
    pass


@lru_cache(maxsize=1)
def _model() -> ModelInference:
    creds = Credentials(
        url=settings.WATSONX_URL,
        api_key=settings.WATSONX_APIKEY,
    )
    return ModelInference(
        model_id=settings.WATSONX_MODEL_ID,
        credentials=creds,
        project_id=settings.WATSONX_PROJECT_ID,
        verify=settings.WATSONX_VERIFY,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(WatsonxError),
)
def chat_completion(
    messages: List[Dict[str, str]],
    *,
    temperature: float | None = None,
) -> Dict[str, Any]:
    params = {
        "temperature": settings.WCOA_CHAT_TEMPERATURE if temperature is None else temperature,
        "top_p": settings.WCOA_CHAT_TOP_P,
        "max_tokens": settings.WCOA_CHAT_MAX_TOKENS,
    }

    try:
        model = _model()
        response = model.chat(messages=messages, params=params)
        content = extract_chat_content(response)

        try:
            parsed = parse_structured_wcoa_response(content)
        except WatsonxError:
            log.warning(
                "watsonx_non_json_response",
                content_preview=content[:1000],
            )
            repaired_content = repair_json_response(content)
            parsed = parse_structured_wcoa_response(repaired_content)

        return {
            "provider": "watsonx.ai",
            "model_id": settings.WATSONX_MODEL_ID,
            "raw": response,
            "content": content,
            "structured": parsed.model_dump(),
        }

    except WatsonxError:
        raise
    except Exception as exc:
        log.warning("watsonx_chat_failed", err=str(exc))
        raise WatsonxError(str(exc)) from exc


def repair_json_response(raw_content: str) -> str:
    model = _model()

    repair_messages = [
        {
            "role": "system",
            "content": """
You are a JSON formatter for WCOA.

Convert the user's content into ONLY one valid JSON object.
Do not include markdown.
Do not include code fences.
Do not include prose before or after the JSON.

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
""".strip(),
        },
        {"role": "user", "content": raw_content},
    ]

    repair_response = model.chat(
        messages=repair_messages,
        params={
            "temperature": 0,
            "top_p": 0.1,
            "max_tokens": settings.WCOA_CHAT_MAX_TOKENS,
        },
    )
    return extract_chat_content(repair_response)


def extract_chat_content(response: Dict[str, Any]) -> str:
    try:
        choices = response.get("choices") or []
        if not choices:
            raise ValueError("No choices returned by model")

        message = choices[0].get("message") or {}
        content = message.get("content")

        if isinstance(content, list):
            content = "\n".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )

        if not isinstance(content, str) or not content.strip():
            raise ValueError("Empty chat content")

        return content.strip()

    except Exception as exc:
        raise WatsonxError(f"Unable to extract chat content: {exc}") from exc


def parse_structured_wcoa_response(content: str) -> WCOAAgentResponse:
    raw = (content or "").strip()

    if not raw:
        raise WatsonxError("Model returned empty content")

    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()

    payload = None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = raw[start : end + 1]
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError as exc:
                raise WatsonxError(
                    f"Model did not return valid JSON: {exc}. Raw content: {content!r}"
                ) from exc
        else:
            raise WatsonxError(
                f"Model did not return valid JSON. Raw content: {content!r}"
            )

    try:
        return WCOAAgentResponse.model_validate(payload)
    except ValidationError as exc:
        raise WatsonxError(
            f"Model JSON did not match WCOA schema: {exc}. Payload: {payload!r}"
        ) from exc