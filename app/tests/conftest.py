"""Shared test fixtures and fakes."""

from types import SimpleNamespace

import pytest


class FakeResponses:
    """Stand-in for ``client.responses`` that records the last call."""

    def __init__(self, output_text: str = "Software Engineer", exc: Exception | None = None):
        self.output_text = output_text
        self.exc = exc
        self.last_call: dict | None = None

    async def create(self, **kwargs):
        self.last_call = kwargs
        if self.exc is not None:
            raise self.exc
        return SimpleNamespace(output_text=self.output_text)


class FakeAsyncOpenAI:
    """Minimal async OpenAI client double exposing only ``.responses``."""

    def __init__(self, output_text: str = "Software Engineer", exc: Exception | None = None):
        self.responses = FakeResponses(output_text=output_text, exc=exc)


@pytest.fixture
def fake_client() -> FakeAsyncOpenAI:
    """A fake OpenAI client that returns a fixed job title."""
    return FakeAsyncOpenAI()


class FakeS3Client:
    """Stand-in for a boto3 S3 client that records the last ``put_object`` call."""

    def __init__(self, exc: Exception | None = None):
        self.exc = exc
        self.last_call: dict | None = None

    def put_object(self, **kwargs):
        self.last_call = kwargs
        if self.exc is not None:
            raise self.exc
        return {}


@pytest.fixture
def fake_r2_client() -> FakeS3Client:
    """A fake R2 (S3-compatible) client that records calls and succeeds by default."""
    return FakeS3Client()
