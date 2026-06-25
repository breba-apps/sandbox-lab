"""Unit tests for the R2 storage layer."""

import json

import pytest
from botocore.exceptions import BotoCoreError

from app.storage import InferenceStorageError, store_inference_record
from tests.conftest import FakeS3Client


@pytest.mark.asyncio
async def test_store_inference_record_writes_expected_body():
    client = FakeS3Client()

    key = await store_inference_record(
        client=client,
        bucket="test-bucket",
        job_description="Build and maintain data pipelines.",
        job_title="Data Engineer",
    )

    assert client.last_call["Bucket"] == "test-bucket"
    assert client.last_call["Key"] == key
    assert key.startswith("inferences/") and key.endswith(".json")
    assert json.loads(client.last_call["Body"]) == {
        "job_description": "Build and maintain data pipelines.",
        "job_title": "Data Engineer",
    }


@pytest.mark.asyncio
async def test_store_inference_record_raises_on_client_error():
    client = FakeS3Client(exc=BotoCoreError())

    with pytest.raises(InferenceStorageError):
        await store_inference_record(
            client=client,
            bucket="test-bucket",
            job_description="Some description.",
            job_title="Some Title",
        )
