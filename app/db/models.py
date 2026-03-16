from __future__ import annotations

import enum
import uuid
from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, Enum, ForeignKey, Text, BigInteger
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy import Index


class Base(DeclarativeBase):
    pass


class DatasetStatus(str, enum.Enum):
    REGISTERED = "REGISTERED"
    RAW_UPLOADED = "RAW_UPLOADED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    DELETED = "DELETED"


class SourceType(str, enum.Enum):
    DIRECT_UPLOAD = "DIRECT_UPLOAD"
    SAS_INGEST = "SAS_INGEST"
    API_PUSH = "API_PUSH"


class AuditEventType(str, enum.Enum):
    TENANT_CREATED = "TENANT_CREATED"
    DATASET_CREATED = "DATASET_CREATED"
    UPLOAD_AUTHORIZED = "UPLOAD_AUTHORIZED"
    RAW_UPLOADED = "RAW_UPLOADED"
    PROCESSING_STARTED = "PROCESSING_STARTED"
    PROCESSING_COMPLETED = "PROCESSING_COMPLETED"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    RAW_DELETED = "RAW_DELETED"
    DATASET_USED_FOR_CHAT = "DATASET_USED_FOR_CHAT"
    DATASET_EXPIRED = "DATASET_EXPIRED"
    DATASET_DELETED = "DATASET_DELETED"
    AUTHZ_FAILURE = "AUTHZ_FAILURE"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    RATE_LIMITED = "RATE_LIMITED"


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = {"schema": "wcoa"}

    tenant_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ACTIVE")
    kms_key_crn: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class DatasetRegistry(Base):
    __tablename__ = "dataset_registry"
    __table_args__ = (
        Index("idx_dataset_tenant_status", "tenant_id", "status"),
        Index("idx_dataset_tenant_created", "tenant_id", "created_at"),
        Index("idx_dataset_expires_at", "expires_at"),
        {"schema": "wcoa"},
    )

    dataset_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("wcoa.tenants.tenant_id"), nullable=False)

    status: Mapped[DatasetStatus] = mapped_column(Enum(DatasetStatus, name="dataset_status", schema="wcoa"), nullable=False, default=DatasetStatus.REGISTERED)
    source: Mapped[SourceType] = mapped_column(Enum(SourceType, name="source_type", schema="wcoa"), nullable=False, default=SourceType.DIRECT_UPLOAD)

    raw_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_summary_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_report_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    canonical_sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    schema_hash: Mapped[str | None] = mapped_column(String, nullable=True)

    raw_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    canonical_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    row_counts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    column_counts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    upload_authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String, nullable=True)

    last_error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    ingestion_request_id: Mapped[str | None] = mapped_column(String, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_tenant_ts", "tenant_id", "event_ts"),
        Index("idx_audit_dataset_ts", "dataset_id", "event_ts"),
        Index("idx_audit_type_ts", "event_type", "event_ts"),
        {"schema": "wcoa"},
    )

    event_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str | None] = mapped_column(String, nullable=True)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    event_type: Mapped[AuditEventType] = mapped_column(Enum(AuditEventType, name="audit_event_type", schema="wcoa"), nullable=False)
    event_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    actor: Mapped[str | None] = mapped_column(String, nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)

    correlation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True)

    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
