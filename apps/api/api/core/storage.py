"""Object storage for template artwork — the only module that knows the bucket.

Cloudflare R2 through boto3's S3 client. Nothing outside this file constructs a
key prefix, an endpoint, or a client; callers pass a key and get bytes.

Two deliberate omissions:

**No public URL and no presigned GET.** The PDF renderer cannot fetch a URL at
all — `_pdf_link_callback` refuses every scheme, which is the control that stops
a template author turning a render into a server-side request — so a URL would
be useless to the one consumer that matters. The dashboard reads images back
through an authenticated API route instead. One transport, one auth story, and
a presigned URL that cannot be revoked never exists.

**No local-filesystem fallback.** See the config block: a storage backend that
silently changes between dev and production is the failure mode this codebase
keeps producing.
"""

from __future__ import annotations

import logging
from typing import Optional

from api.core.config import (
    R2_ACCESS_KEY_ID,
    R2_ACCOUNT_ID,
    R2_BUCKET,
    R2_ENDPOINT,
    R2_SECRET_ACCESS_KEY,
    STORAGE_AVAILABLE,
    STORAGE_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)

_client = None


class StorageError(RuntimeError):
    """The object store could not be reached, or refused the operation."""


def storage_available() -> bool:
    """Whether credentials are configured. NOT whether the bucket answers.

    Four environment variables being present is a different claim from the
    bucket being reachable with the right secret — a typo'd key is present and
    wrong. `head_bucket()` is the claim that matters and it costs a network
    round trip, so callers that need it ask for it explicitly.
    """
    return STORAGE_AVAILABLE


def _endpoint_url() -> str:
    return R2_ENDPOINT or f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"


def get_client():
    """Lazily build the S3 client. Raises StorageError when unconfigured."""
    global _client
    if not STORAGE_AVAILABLE:
        raise StorageError("Object storage is not configured.")
    if _client is None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise StorageError("boto3 is not installed.") from exc

        _client = boto3.client(
            "s3",
            endpoint_url=_endpoint_url(),
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            # R2 ignores regions but botocore insists on one being set.
            region_name="auto",
            config=Config(
                connect_timeout=STORAGE_TIMEOUT_SEC,
                read_timeout=STORAGE_TIMEOUT_SEC,
                retries={"max_attempts": 2, "mode": "standard"},
                signature_version="s3v4",
            ),
        )
    return _client


def put_object(key: str, data: bytes, content_type: str) -> None:
    """Store bytes. Raises StorageError rather than returning a status.

    Callers write the object BEFORE inserting the row that names it: in that
    order an unreachable bucket leaves no row pointing at nothing, and the worst
    outcome is an orphaned object nobody references.
    """
    try:
        get_client().put_object(
            Bucket=R2_BUCKET, Key=key, Body=data, ContentType=content_type
        )
    except StorageError:
        raise
    except Exception as exc:
        logger.exception("Object store write failed for %s", key)
        raise StorageError(f"Could not store the object: {exc}") from exc


def get_object(key: str) -> bytes:
    try:
        response = get_client().get_object(Bucket=R2_BUCKET, Key=key)
        return response["Body"].read()
    except StorageError:
        raise
    except Exception as exc:
        logger.exception("Object store read failed for %s", key)
        raise StorageError(f"Could not read the object: {exc}") from exc


def delete_object(key: str) -> None:
    try:
        get_client().delete_object(Bucket=R2_BUCKET, Key=key)
    except StorageError:
        raise
    except Exception as exc:
        logger.exception("Object store delete failed for %s", key)
        raise StorageError(f"Could not delete the object: {exc}") from exc


def bucket_reachable() -> Optional[str]:
    """None when the bucket answers, otherwise why it did not.

    This is the check `storage_available()` cannot make. `/api/health` reports
    it so a wrong secret shows up as a dependency failure rather than as a 500
    on the first customer upload — scripts/smoke_test.sh is read-only and can
    never exercise a write path.
    """
    if not STORAGE_AVAILABLE:
        return "not configured"
    try:
        get_client().head_bucket(Bucket=R2_BUCKET)
        return None
    except Exception as exc:
        return str(exc)
