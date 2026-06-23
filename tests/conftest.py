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
