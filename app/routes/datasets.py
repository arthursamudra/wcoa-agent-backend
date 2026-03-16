from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import structlog
from fastapi import APIRouter, HTTPException

from app.db.session import AsyncSessionLocal
from app.services import cos_service
from app.services.dataset_processor import excel_to_canonical
from app.services.registry_service import (
    create_dataset, mark_upload_authorized, get_dataset,
    update_processing_state, add_audit
)
from app.db.models import DatasetStatus, AuditEventType, SourceType
from app.core.config import settings
from app.utils.schemas import CreateDatasetRequest, CreateDatasetResponse, ProcessDatasetRequest, RegisterDatasetRequest, DatasetRegisterResponse

log = structlog.get_logger()
router = APIRouter(prefix="/datasets", tags=["datasets"])


def _normalize_filename(filename: str, fallback: str) -> str:
    candidate = Path(filename or fallback).name
    return candidate or fallback


@router.post("/create", response_model=CreateDatasetResponse)
async def create(req: CreateDatasetRequest):
    async with AsyncSessionLocal() as session:
        ds = await create_dataset(session, req.tenantId, req.createdBy, req.correlationId)
        dataset_id = str(ds.dataset_id)

        raw_key = cos_service.build_object_key(req.tenantId, dataset_id, "raw", _normalize_filename(req.originalFilename, "dataset.xlsx"))
        upload_url = cos_service.presign_put_url(raw_key)

        await mark_upload_authorized(session, req.tenantId, ds.dataset_id, raw_key, req.correlationId, req.createdBy)

        return CreateDatasetResponse(
            tenantId=req.tenantId,
            datasetId=dataset_id,
            uploadUrl=upload_url,
            rawObjectKey=raw_key,
            expiresAt=ds.expires_at.isoformat(),
            status=ds.status.value,
        )


@router.post("/register", response_model=DatasetRegisterResponse)
async def register(req: RegisterDatasetRequest):
    source_type = SourceType.SAS_INGEST if req.source.type == "azure_blob" else SourceType.DIRECT_UPLOAD
    async with AsyncSessionLocal() as session:
        ds = await create_dataset(session, req.tenantId, req.createdBy, req.correlationId, source=source_type)
        dataset_id = str(ds.dataset_id)
        filename = _normalize_filename(req.originalFilename, "dataset.xlsx")
        raw_key = cos_service.build_object_key(req.tenantId, dataset_id, "raw", filename)

        if req.source.type == "azure_blob":
            if not req.source.sasUrl:
                raise HTTPException(status_code=400, detail="sasUrl required for azure_blob source")
            await mark_upload_authorized(session, req.tenantId, ds.dataset_id, raw_key, req.correlationId, req.createdBy)
            await update_processing_state(
                session,
                req.tenantId,
                ds.dataset_id,
                DatasetStatus.PROCESSING,
                processing_started_at=datetime.now(timezone.utc),
            )
            await add_audit(session, req.tenantId, ds.dataset_id, AuditEventType.PROCESSING_STARTED, req.createdBy, req.correlationId)

            try:
                async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                    resp = await client.get(req.source.sasUrl)
                    resp.raise_for_status()
                    raw_bytes = resp.content
                if len(raw_bytes) > settings.MAX_EXCEL_BYTES:
                    raise HTTPException(status_code=413, detail="file too large")
                cos_service.put_object_bytes(raw_key, raw_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                await update_processing_state(
                    session,
                    req.tenantId,
                    ds.dataset_id,
                    DatasetStatus.RAW_UPLOADED,
                    raw_uploaded_at=datetime.now(timezone.utc),
                    raw_size_bytes=len(raw_bytes),
                    raw_sha256=cos_service.sha256_bytes(raw_bytes),
                )
                return await _process_dataset(session, req.tenantId, dataset_id, req.createdBy, req.correlationId)
            except httpx.HTTPError as exc:
                await update_processing_state(session, req.tenantId, ds.dataset_id, DatasetStatus.FAILED, last_error_code="SAS_DOWNLOAD_FAILED", last_error_message=str(exc)[:200])
                await add_audit(session, req.tenantId, ds.dataset_id, AuditEventType.PROCESSING_FAILED, req.createdBy, req.correlationId, metadata={"error": str(exc)[:200]})
                raise HTTPException(status_code=400, detail="failed to download dataset from sasUrl") from exc

        upload_url = cos_service.presign_put_url(raw_key)
        await mark_upload_authorized(session, req.tenantId, ds.dataset_id, raw_key, req.correlationId, req.createdBy)
        return DatasetRegisterResponse(
            tenantId=req.tenantId,
            datasetId=dataset_id,
            uploadUrl=upload_url,
            rawObjectKey=raw_key,
            expiresAt=ds.expires_at.isoformat(),
            status=ds.status.value,
        )


async def _process_dataset(session, tenant_id: str, dataset_id: str, actor: str | None, correlation_id: str | None):
    dataset_uuid = uuid.UUID(dataset_id)
    ds = await get_dataset(session, tenant_id, dataset_uuid)
    if not ds:
        raise HTTPException(status_code=404, detail="dataset not found")
    if ds.status in (DatasetStatus.EXPIRED, DatasetStatus.DELETED):
        raise HTTPException(status_code=410, detail="dataset expired")
    if not ds.raw_object_key:
        raise HTTPException(status_code=400, detail="raw object key missing")

    await update_processing_state(
        session, tenant_id, dataset_uuid,
        DatasetStatus.PROCESSING,
        processing_started_at=datetime.now(timezone.utc),
    )
    await add_audit(session, tenant_id, dataset_uuid, AuditEventType.PROCESSING_STARTED, actor, correlation_id)

    try:
        object_meta = cos_service.head_object(ds.raw_object_key)
        content_length = int(object_meta.get("ContentLength", 0))
        if content_length > settings.MAX_EXCEL_BYTES:
            raise HTTPException(status_code=413, detail="file too large")

        raw_bytes = cos_service.get_object_bytes(ds.raw_object_key)
        raw_sha = cos_service.sha256_bytes(raw_bytes)
        canonical = excel_to_canonical(raw_bytes)

        canonical_key = cos_service.build_object_key(tenant_id, dataset_id, "canonical", "min.json")
        schema_key = cos_service.build_object_key(tenant_id, dataset_id, "canonical", "schema_summary.json")

        cos_service.put_object_bytes(canonical_key, canonical.canonical_json, content_type="application/json")
        cos_service.put_object_bytes(schema_key, canonical.schema_summary_json, content_type="application/json")
        cos_service.delete_object(ds.raw_object_key)

        await update_processing_state(
            session, tenant_id, dataset_uuid,
            DatasetStatus.READY,
            raw_uploaded_at=ds.raw_uploaded_at or datetime.now(timezone.utc),
            raw_sha256=raw_sha,
            raw_size_bytes=len(raw_bytes),
            canonical_object_key=canonical_key,
            schema_summary_key=schema_key,
            schema_hash=canonical.schema_hash,
            row_counts=canonical.row_counts,
            column_counts=canonical.column_counts,
            canonical_size_bytes=len(canonical.canonical_json),
            processed_at=datetime.now(timezone.utc),
            raw_deleted_at=datetime.now(timezone.utc),
        )
        await add_audit(
            session,
            tenant_id,
            dataset_uuid,
            AuditEventType.PROCESSING_COMPLETED,
            actor,
            correlation_id,
            metadata={"canonicalKey": canonical_key, "schemaKey": schema_key},
        )
        await add_audit(
            session,
            tenant_id,
            dataset_uuid,
            AuditEventType.RAW_DELETED,
            actor,
            correlation_id,
            metadata={"rawKey": ds.raw_object_key},
        )

        refreshed = await get_dataset(session, tenant_id, dataset_uuid)
        return DatasetRegisterResponse(
            tenantId=tenant_id,
            datasetId=dataset_id,
            uploadUrl=None,
            rawObjectKey=ds.raw_object_key,
            expiresAt=refreshed.expires_at.isoformat() if refreshed else datetime.now(timezone.utc).isoformat(),
            status=DatasetStatus.READY.value,
        )
    except HTTPException:
        await update_processing_state(session, tenant_id, dataset_uuid, DatasetStatus.FAILED, last_error_code="HTTP", last_error_message="processing failed")
        await add_audit(session, tenant_id, dataset_uuid, AuditEventType.PROCESSING_FAILED, actor, correlation_id)
        raise
    except Exception as exc:
        await update_processing_state(session, tenant_id, dataset_uuid, DatasetStatus.FAILED, last_error_code="EX", last_error_message=str(exc)[:200])
        await add_audit(
            session,
            tenant_id,
            dataset_uuid,
            AuditEventType.PROCESSING_FAILED,
            actor,
            correlation_id,
            metadata={"error": str(exc)[:200]},
        )
        raise HTTPException(status_code=500, detail="processing failed") from exc


@router.post("/process")
async def process(req: ProcessDatasetRequest):
    async with AsyncSessionLocal() as session:
        return await _process_dataset(session, req.tenantId, req.datasetId, req.actor, req.correlationId)
