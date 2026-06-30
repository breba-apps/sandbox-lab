"""Unit tests for the inference service layer."""

import pytest

from app.service import JobTitleInferenceError, infer_job_title
from tests.conftest import FakeAsyncOpenAI


@pytest.mark.asyncio
async def test_infer_job_title_returns_stripped_title():
    client = FakeAsyncOpenAI(output_text='  "Data Engineer"  \n')

    title = await infer_job_title(
        client=client,
        job_description="Build and maintain data pipelines.",
        model="gpt-4o-mini",
    )

    assert title == "Data Engineer"


@pytest.mark.asyncio
async def test_infer_job_title_passes_model_and_input():
    client = FakeAsyncOpenAI(output_text="Product Manager")

    await infer_job_title(
        client=client,
        job_description="Own the roadmap and coordinate with engineering.",
        model="gpt-4o-mini",
    )

    call = client.responses.last_call
    assert call["model"] == "gpt-4o-mini"
    assert call["input"] == "Own the roadmap and coordinate with engineering."
    assert "instructions" in call


@pytest.mark.asyncio
async def test_infer_job_title_raises_on_empty_response():
    client = FakeAsyncOpenAI(output_text="   ")

    with pytest.raises(JobTitleInferenceError):
        await infer_job_title(
            client=client,
            job_description="Some description.",
            model="gpt-4o-mini",
        )
