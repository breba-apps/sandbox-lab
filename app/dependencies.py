"""Shared FastAPI dependencies."""

from functools import lru_cache

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from openai import AsyncOpenAI

from .config import get_settings


@lru_cache
def get_openai_client() -> AsyncOpenAI:
    """Return a cached async OpenAI client built from settings.

    Overridden in tests via ``app.dependency_overrides``.
    """
    settings = get_settings()
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.request_timeout_seconds,
    )


@lru_cache
def get_r2_client() -> BaseClient:
    """Return a cached S3-compatible client for Cloudflare R2.

    ``request_checksum_calculation``/``response_checksum_validation`` are pinned to
    ``when_required`` because botocore's newer default integrity checks (SDKv2-style
    trailing checksums) are not supported by R2's S3-compatible API.

    Overridden in tests via ``app.dependency_overrides``.
    """
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
        config=Config(
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
