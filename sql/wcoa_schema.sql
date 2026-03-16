CREATE SCHEMA IF NOT EXISTS wcoa;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE t.typname='dataset_status' AND n.nspname='wcoa') THEN
    CREATE TYPE wcoa.dataset_status AS ENUM ('REGISTERED','RAW_UPLOADED','PROCESSING','READY','FAILED','EXPIRED','DELETED');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE t.typname='source_type' AND n.nspname='wcoa') THEN
    CREATE TYPE wcoa.source_type AS ENUM ('DIRECT_UPLOAD','SAS_INGEST','API_PUSH');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE t.typname='audit_event_type' AND n.nspname='wcoa') THEN
    CREATE TYPE wcoa.audit_event_type AS ENUM (
      'TENANT_CREATED','DATASET_CREATED','UPLOAD_AUTHORIZED','RAW_UPLOADED','PROCESSING_STARTED','PROCESSING_COMPLETED','PROCESSING_FAILED','RAW_DELETED',
      'DATASET_USED_FOR_CHAT','DATASET_EXPIRED','DATASET_DELETED','AUTHZ_FAILURE','VALIDATION_FAILURE','RATE_LIMITED'
    );
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS wcoa.tenants (
  tenant_id TEXT PRIMARY KEY,
  tenant_name TEXT,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  kms_key_crn TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION wcoa.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_tenants_updated_at') THEN
    CREATE TRIGGER trg_tenants_updated_at
    BEFORE UPDATE ON wcoa.tenants
    FOR EACH ROW EXECUTE FUNCTION wcoa.set_updated_at();
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS wcoa.dataset_registry (
  dataset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id TEXT NOT NULL REFERENCES wcoa.tenants(tenant_id) ON DELETE RESTRICT,
  status wcoa.dataset_status NOT NULL DEFAULT 'REGISTERED',
  source wcoa.source_type NOT NULL DEFAULT 'DIRECT_UPLOAD',

  raw_object_key TEXT,
  canonical_object_key TEXT,
  schema_summary_key TEXT,
  processing_report_key TEXT,

  raw_sha256 TEXT,
  canonical_sha256 TEXT,
  schema_hash TEXT,

  raw_size_bytes BIGINT,
  canonical_size_bytes BIGINT,

  row_counts JSONB,
  column_counts JSONB,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  upload_authorized_at TIMESTAMPTZ,
  raw_uploaded_at TIMESTAMPTZ,
  processing_started_at TIMESTAMPTZ,
  processed_at TIMESTAMPTZ,
  raw_deleted_at TIMESTAMPTZ,
  last_accessed_at TIMESTAMPTZ,

  expires_at TIMESTAMPTZ NOT NULL,
  expired_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,

  created_by TEXT,
  correlation_id TEXT,

  last_error_code TEXT,
  last_error_message TEXT,

  ingestion_request_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_dataset_tenant_status ON wcoa.dataset_registry(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_dataset_tenant_created ON wcoa.dataset_registry(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dataset_expires_at ON wcoa.dataset_registry(expires_at);

CREATE UNIQUE INDEX IF NOT EXISTS uq_dataset_tenant_ingestion_req
  ON wcoa.dataset_registry(tenant_id, ingestion_request_id)
  WHERE ingestion_request_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS wcoa.audit_log (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id TEXT,
  dataset_id UUID,
  event_type wcoa.audit_event_type NOT NULL,
  event_ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor TEXT,
  source_ip TEXT,
  user_agent TEXT,
  correlation_id TEXT,
  request_id TEXT,
  metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_audit_tenant_ts ON wcoa.audit_log(tenant_id, event_ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_dataset_ts ON wcoa.audit_log(dataset_id, event_ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_type_ts ON wcoa.audit_log(event_type, event_ts DESC);
