"""S3-compatible object storage (Phase 5, PRD §10.2 / §7.1).

One module. Same client serves AWS S3 in prod and MinIO in dev — only the
endpoint URL differs. PRD §4.5 picks Render hosting + AWS-friendly tooling;
MinIO in docker-compose keeps `docker compose up` self-contained.

Key shape: ``{org_id}/documents/{document_id}/{original_filename}``. The
org_id prefix isn't a security boundary (RLS on the Postgres row is), it's
just for human readability when poking at the bucket.
"""

from __future__ import annotations

import contextlib
from contextlib import asynccontextmanager
from uuid import UUID

import aiobotocore.session

from app.config import get_settings

_session = aiobotocore.session.get_session()


@asynccontextmanager
async def _s3_client():
    s = get_settings()
    async with _session.create_client(
        "s3",
        endpoint_url=s.s3_endpoint_url,
        region_name=s.s3_region,
        aws_access_key_id=s.s3_access_key_id,
        aws_secret_access_key=s.s3_secret_access_key,
    ) as client:
        yield client


def document_key(org_id: UUID, document_id: UUID, original_filename: str) -> str:
    return f"{org_id}/documents/{document_id}/{original_filename}"


async def ensure_bucket() -> None:
    """Create the dev bucket if it doesn't exist. In prod the bucket is
    created out-of-band (Terraform / CloudFormation / by hand); this call is
    safe in either case — it short-circuits on the AlreadyOwnedByYou /
    BucketAlreadyExists error."""
    s = get_settings()
    async with _s3_client() as client:
        try:
            await client.head_bucket(Bucket=s.s3_bucket)
        except client.exceptions.ClientError:
            # Another process beat us to it — fine.
            with contextlib.suppress(client.exceptions.ClientError):
                await client.create_bucket(Bucket=s.s3_bucket)


async def store_file(
    *, org_id: UUID, document_id: UUID, original_filename: str, data: bytes, content_type: str
) -> str:
    """Upload bytes, return the storage_key."""
    s = get_settings()
    key = document_key(org_id, document_id, original_filename)
    async with _s3_client() as client:
        await client.put_object(
            Bucket=s.s3_bucket, Key=key, Body=data, ContentType=content_type
        )
    return key


async def get_file(storage_key: str) -> bytes:
    """Read object bytes."""
    s = get_settings()
    async with _s3_client() as client:
        resp = await client.get_object(Bucket=s.s3_bucket, Key=storage_key)
        async with resp["Body"] as stream:
            return await stream.read()


async def delete_file(storage_key: str) -> None:
    s = get_settings()
    async with _s3_client() as client:
        await client.delete_object(Bucket=s.s3_bucket, Key=storage_key)
