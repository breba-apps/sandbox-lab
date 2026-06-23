"""Shared FastAPI dependencies."""

from functools import lru_cache

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
