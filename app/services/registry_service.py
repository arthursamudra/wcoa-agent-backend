from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Tenant, DatasetRegistry, DatasetStatus, SourceType, AuditLog, AuditEventType

log = structlog.get_logger()


async def ensure_tenant(session: AsyncSession, tenant_id: str) -> None:
    res = await session.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    t = res.scalar_one_or_none()
    if t:
        return
    session.add(Tenant(tenant_id=tenant_id, tenant_name=None))
    session.add(AuditLog(tenant_id=tenant_id, event_type=AuditEventType.TENANT_CREATED, event_metadata={"tenantId": tenant_id}))
    await session.commit()


async def create_dataset(session: AsyncSession, tenant_id: str, created_by: str | None, correlation_id: str | None, ttl_hours: int | None = None, source: SourceType = SourceType.DIRECT_UPLOAD) -> DatasetRegistry:
    await ensure_tenant(session, tenant_id)
    ttl = ttl_hours or settings.DEFAULT_TENANT_TTL_HOURS
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl)
    ds = DatasetRegistry(
        tenant_id=tenant_id,
        status=DatasetStatus.REGISTERED,
        source=source,
        expires_at=expires_at,
        created_by=created_by,
        correlation_id=correlation_id,
    )
    session.add(ds)
    await session.flush()

    session.add(AuditLog(
        tenant_id=tenant_id,
        dataset_id=ds.dataset_id,
        event_type=AuditEventType.DATASET_CREATED,
        correlation_id=correlation_id,
        event_metadata={"datasetId": str(ds.dataset_id), "expiresAt": expires_at.isoformat()},
        actor=created_by,
    ))
    await session.commit()
    await session.refresh(ds)
    return ds


async def get_dataset(session: AsyncSession, tenant_id: str, dataset_id: uuid.UUID) -> DatasetRegistry | None:
    res = await session.execute(select(DatasetRegistry).where(DatasetRegistry.dataset_id == dataset_id))
    ds = res.scalar_one_or_none()
    if not ds:
        return None
    if ds.tenant_id != tenant_id:
        return None
    return ds


async def mark_upload_authorized(session: AsyncSession, tenant_id: str, dataset_id: uuid.UUID, raw_object_key: str, correlation_id: str | None, actor: str | None) -> None:
    now = datetime.now(timezone.utc)
    await session.execute(
        update(DatasetRegistry)
        .where(DatasetRegistry.dataset_id == dataset_id, DatasetRegistry.tenant_id == tenant_id)
        .values(upload_authorized_at=now, raw_object_key=raw_object_key)
    )
    session.add(AuditLog(
        tenant_id=tenant_id, dataset_id=dataset_id,
        event_type=AuditEventType.UPLOAD_AUTHORIZED,
        correlation_id=correlation_id,
        actor=actor,
        event_metadata={"rawObjectKey": raw_object_key},
    ))
    await session.commit()


async def update_processing_state(session: AsyncSession, tenant_id: str, dataset_id: uuid.UUID, status: DatasetStatus, **kwargs) -> None:
    await session.execute(
        update(DatasetRegistry)
        .where(DatasetRegistry.dataset_id == dataset_id, DatasetRegistry.tenant_id == tenant_id)
        .values(status=status, **kwargs)
    )
    await session.commit()


async def add_audit(session: AsyncSession, tenant_id: str | None, dataset_id: uuid.UUID | None, event_type: AuditEventType, actor: str | None, correlation_id: str | None, metadata: dict | None = None, source_ip: str | None = None) -> None:
    session.add(AuditLog(
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        event_type=event_type,
        actor=actor,
        correlation_id=correlation_id,
        event_metadata=metadata or {},
        source_ip=source_ip,
    ))
    await session.commit()
