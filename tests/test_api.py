"""Integration tests for the /infer-title endpoint."""

import json

import pytest
from botocore.exceptions import BotoCoreError
from fastapi.testclient import TestClient
from openai import APIError

from app.config import Settings, get_settings
from app.dependencies import get_openai_client, get_r2_client
from app.main import app
from tests.conftest import FakeAsyncOpenAI, FakeS3Client


def _override_settings(api_key: str = "test-key", model: str = "gpt-4o-mini") -> Settings:
    return Settings(
        openai_api_key=api_key,
        openai_model=model,
        r2_account_id="test-account",
        r2_access_key_id="test-access-key",
        r2_secret_access_key="test-secret-key",
        r2_bucket_name="test-bucket",
    )


@pytest.fixture
def client_factory():
    """Build a TestClient with overridable OpenAI client, R2 client, and settings."""
    created: list[TestClient] = []

    def _make(
        fake_openai: FakeAsyncOpenAI,
        settings: Settings | None = None,
        fake_r2: FakeS3Client | None = None,
    ) -> TestClient:
        app.dependency_overrides[get_openai_client] = lambda: fake_openai
        app.dependency_overrides[get_r2_client] = lambda: fake_r2 or FakeS3Client()
        app.dependency_overrides[get_settings] = lambda: settings or _override_settings()
        tc = TestClient(app)
        created.append(tc)
        return tc

    yield _make
    app.dependency_overrides.clear()


def test_infer_title_success(client_factory):
    fake_r2 = FakeS3Client()
    tc = client_factory(FakeAsyncOpenAI(output_text="Data Scientist"), fake_r2=fake_r2)

    resp = tc.post("/infer-title", json={"job_description": "Build ML models from data."})

    assert resp.status_code == 200
    assert resp.json() == {"job_title": "Data Scientist"}
    assert fake_r2.last_call["Bucket"] == "test-bucket"
    assert json.loads(fake_r2.last_call["Body"]) == {
        "job_description": "Build ML models from data.",
        "job_title": "Data Scientist",
    }


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


def test_infer_title_missing_r2_config_returns_500(client_factory):
    settings = Settings(openai_api_key="test-key", r2_bucket_name="")
    tc = client_factory(FakeAsyncOpenAI(), settings=settings)

    resp = tc.post("/infer-title", json={"job_description": "Lead a team of engineers."})

    assert resp.status_code == 500
    assert "R2" in resp.json()["detail"]


def test_infer_title_r2_write_failure_returns_502(client_factory):
    fake_r2 = FakeS3Client(exc=BotoCoreError())
    tc = client_factory(FakeAsyncOpenAI(output_text="Data Scientist"), fake_r2=fake_r2)

    resp = tc.post("/infer-title", json={"job_description": "Build ML models from data."})

    assert resp.status_code == 502


def test_infer_title_empty_model_output_returns_502(client_factory):
    tc = client_factory(FakeAsyncOpenAI(output_text="   "))

    resp = tc.post("/infer-title", json={"job_description": "A vague description."})

    assert resp.status_code == 502


def test_infer_title_openai_error_returns_502(client_factory):
    error = APIError("boom", request=None, body=None)
    tc = client_factory(FakeAsyncOpenAI(exc=error))

    resp = tc.post("/infer-title", json={"job_description": "Something went wrong upstream."})

    assert resp.status_code == 502
