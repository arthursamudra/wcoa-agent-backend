from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException

from app.db.models import DatasetStatus, AuditEventType
from app.db.session import AsyncSessionLocal
from app.services import cos_service
from app.services.orchestrator_service import run_wcoa_chat
from app.services.registry_service import get_dataset, update_processing_state, add_audit
from app.services.watsonx_service import WatsonxError
from app.utils.schemas import ChatRequest, ChatResponse

log = structlog.get_logger()
router = APIRouter(tags=["chat"])


def _build_missing_dataset_response() -> dict[str, Any]:
    return {
        "decision": "Dataset required before WCOA can evaluate suppliers.",
        "options": [],
        "assumptions": [],
        "questions": ["Please provide a valid datasetId or register/upload a dataset first."],
        "next_actions": ["Call /datasets/register or /datasets/create, upload/process the file, then call /chat again."],
        "data_quality_flags": ["datasetId missing"],
    }


def _build_compact_response(full_result: dict[str, Any]) -> dict[str, Any]:
    structured = full_result.get("structured") or {}
    deterministic = full_result.get("deterministic") or {}

    best_option = deterministic.get("best_option") or {}
    structured_options = structured.get("options") or []

    recommended_option = structured_options[0] if structured_options else {}

    return {
        "decision": structured.get("decision"),
        "recommendedSupplier": best_option.get("supplier") or recommended_option.get("supplier"),
        "recommendedOption": {
            "supplier": best_option.get("supplier") or recommended_option.get("supplier"),
            "estimatedUnitPrice": best_option.get("unit_price") or recommended_option.get("estimatedUnitPrice"),
            "estimatedTotalCost": best_option.get("total_cost") or recommended_option.get("estimatedTotalCost"),
            "paymentTermsDays": best_option.get("payment_days"),
            "paymentTerms": recommended_option.get("paymentTerms"),
            "workingCapitalImpact": recommended_option.get("workingCapitalImpact"),
            "score": best_option.get("score"),
            "npv": best_option.get("npv"),
            "liquidityBreached": best_option.get("liquidity_breached"),
        },
        "alternativeOptions": structured_options[1:] if len(structured_options) > 1 else [],
        "risks": recommended_option.get("risks", []),
        "assumptions": structured.get("assumptions", []),
        "questions": structured.get("questions", []),
        "next_actions": structured.get("next_actions", []),
        "data_quality_flags": structured.get("data_quality_flags", []),
    }


async def _run_chat_internal(req: ChatRequest) -> tuple[str | None, dict[str, Any]]:
    if not req.datasetId:
        return None, _build_missing_dataset_response()

    prompt = req.prompt or " ".join(m.content for m in req.messages if m.role == "user").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt or user message is required")

    dataset_uuid = uuid.UUID(req.datasetId)

    async with AsyncSessionLocal() as session:
        ds = await get_dataset(session, req.tenantId, dataset_uuid)
        if not ds:
            await add_audit(session, req.tenantId, dataset_uuid, AuditEventType.AUTHZ_FAILURE, req.actor, req.correlationId)
            raise HTTPException(status_code=404, detail="dataset not found")

        if ds.status != DatasetStatus.READY:
            raise HTTPException(status_code=409, detail=f"dataset not ready: {ds.status}")

        if ds.expires_at <= datetime.now(timezone.utc):
            await update_processing_state(
                session,
                req.tenantId,
                dataset_uuid,
                DatasetStatus.EXPIRED,
                expired_at=datetime.now(timezone.utc),
            )
            await add_audit(session, req.tenantId, dataset_uuid, AuditEventType.DATASET_EXPIRED, req.actor, req.correlationId)
            raise HTTPException(status_code=410, detail="dataset expired")

        if not ds.canonical_object_key:
            raise HTTPException(status_code=500, detail="canonical missing")

        canonical_bytes = cos_service.get_object_bytes(ds.canonical_object_key)
        schema_summary_bytes = cos_service.get_object_bytes(ds.schema_summary_key) if ds.schema_summary_key else None

        await add_audit(
            session,
            req.tenantId,
            dataset_uuid,
            AuditEventType.DATASET_USED_FOR_CHAT,
            req.actor,
            req.correlationId,
            metadata={"canonicalKey": ds.canonical_object_key},
        )

        try:
            result = run_wcoa_chat(
                canonical_bytes=canonical_bytes,
                prompt=prompt,
                user_messages=req.messages,
                schema_summary_bytes=schema_summary_bytes,
                temperature=req.temperature,
            )
        except WatsonxError as exc:
            log.warning("chat_inference_failed", err=str(exc), datasetId=req.datasetId)
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return req.datasetId, result


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    dataset_id, full_result = await _run_chat_internal(req)
    compact_result = _build_compact_response(full_result) if dataset_id else full_result
    return ChatResponse(datasetId=dataset_id, response=compact_result)


@router.post("/chat/debug", response_model=ChatResponse)
async def chat_debug(req: ChatRequest):
    dataset_id, full_result = await _run_chat_internal(req)
    return ChatResponse(datasetId=dataset_id, response=full_result)