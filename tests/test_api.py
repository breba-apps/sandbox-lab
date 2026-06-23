"""Integration tests for the /infer-title endpoint."""

import pytest
from fastapi.testclient import TestClient
from openai import APIError

from app.config import Settings, get_settings
from app.dependencies import get_openai_client
from app.main import app
from tests.conftest import FakeAsyncOpenAI


def _override_settings(api_key: str = "test-key", model: str = "gpt-4o-mini") -> Settings:
    return Settings(openai_api_key=api_key, openai_model=model)


@pytest.fixture
def client_factory():
    """Build a TestClient with overridable OpenAI client and settings."""
    created: list[TestClient] = []

    def _make(fake_openai: FakeAsyncOpenAI, settings: Settings | None = None) -> TestClient:
        app.dependency_overrides[get_openai_client] = lambda: fake_openai
        app.dependency_overrides[get_settings] = lambda: settings or _override_settings()
        tc = TestClient(app)
        created.append(tc)
        return tc

    yield _make
    app.dependency_overrides.clear()


def test_infer_title_success(client_factory):
    tc = client_factory(FakeAsyncOpenAI(output_text="Data Scientist"))

    resp = tc.post("/infer-title", json={"job_description": "Build ML models from data."})

    assert resp.status_code == 200
    assert resp.json() == {"job_title": "Data Scientist"}


def test_infer_title_validation_error_on_empty_description(client_factory):
    tc = client_factory(FakeAsyncOpenAI())

    resp = tc.post("/infer-title", json={"job_description": ""})

    assert resp.status_code == 422


def test_infer_title_missing_field(client_factory):
    tc = client_factory(FakeAsyncOpenAI())

    resp = tc.post("/infer-title", json={})

    assert resp.status_code == 422


def test_infer_title_missing_api_key_returns_500(client_factory):
    tc = client_factory(FakeAsyncOpenAI(), settings=_override_settings(api_key=""))

    resp = tc.post("/infer-title", json={"job_description": "Lead a team of engineers."})

    assert resp.status_code == 500
    assert "OPENAI_API_KEY" in resp.json()["detail"]


def test_infer_title_empty_model_output_returns_502(client_factory):
    tc = client_factory(FakeAsyncOpenAI(output_text="   "))

    resp = tc.post("/infer-title", json={"job_description": "A vague description."})

    assert resp.status_code == 502


def test_infer_title_openai_error_returns_502(client_factory):
    error = APIError("boom", request=None, body=None)
    tc = client_factory(FakeAsyncOpenAI(exc=error))

    resp = tc.post("/infer-title", json={"job_description": "Something went wrong upstream."})

    assert resp.status_code == 502
