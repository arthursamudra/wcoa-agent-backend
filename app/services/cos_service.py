from __future__ import annotations

import hashlib
from typing import Any

import ibm_boto3
from ibm_botocore.client import Config

from app.core.config import settings


def _cos_client():
    return ibm_boto3.client(
        "s3",
        aws_access_key_id=settings.COS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.COS_SECRET_ACCESS_KEY,
        endpoint_url=settings.COS_ENDPOINT,
        region_name="us-south",
        config=Config(signature_version="s3v4"),
    )


def build_object_key(tenant_id: str, dataset_id: str, kind: str, filename: str) -> str:
    safe_filename = filename.replace("/", "_")
    return f"tenants/{tenant_id}/datasets/{dataset_id}/{kind}/{safe_filename}"


def presign_put_url(object_key: str, expires_seconds: int | None = None) -> str:
    client = _cos_client()
    ttl = expires_seconds or settings.COS_PRESIGN_EXPIRES_SECONDS
    return client.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": settings.COS_BUCKET, "Key": object_key},
        ExpiresIn=ttl,
        HttpMethod="PUT",
    )


def head_object(object_key: str) -> dict[str, Any]:
    client = _cos_client()
    return client.head_object(Bucket=settings.COS_BUCKET, Key=object_key)


def get_object_bytes(object_key: str) -> bytes:
    client = _cos_client()
    resp = client.get_object(Bucket=settings.COS_BUCKET, Key=object_key)
    return resp["Body"].read()


def put_object_bytes(object_key: str, data: bytes, content_type: str = "application/json") -> dict[str, Any]:
    client = _cos_client()
    return client.put_object(
        Bucket=settings.COS_BUCKET,
        Key=object_key,
        Body=data,
        ContentType=content_type,
        ContentMD5=md5_base64(data),
    )


def delete_object(object_key: str) -> None:
    client = _cos_client()
    client.delete_object(Bucket=settings.COS_BUCKET, Key=object_key)


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def md5_base64(data: bytes) -> str:
    import base64

    digest = hashlib.md5(data).digest()  # noqa: S324 - used only for integrity header
    return base64.b64encode(digest).decode("ascii")
