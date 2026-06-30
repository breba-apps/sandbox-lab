"""FastAPI application exposing a single job-title inference endpoint."""

from botocore.client import BaseClient
from fastapi import Depends, FastAPI, HTTPException, status
from openai import AsyncOpenAI, OpenAIError

from .config import Settings, get_settings
from .dependencies import get_openai_client, get_r2_client
from .schemas import InferTitleRequest, InferTitleResponse
from .service import JobTitleInferenceError, infer_job_title
from .storage import InferenceStorageError, store_inference_record

app = FastAPI(
    title="Job Title Inferrer",
    description="Infers a job title from a job description using OpenAI.",
    version="0.1.0",
)


@app.post("/infer-title", response_model=InferTitleResponse)
async def infer_title(
    request: InferTitleRequest,
    client: AsyncOpenAI = Depends(get_openai_client),
    r2_client: BaseClient = Depends(get_r2_client),
    settings: Settings = Depends(get_settings),
) -> InferTitleResponse:
    """Infer the most appropriate job title for the supplied description."""
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OPENAI_API_KEY is not configured.",
        )
    if not (
        settings.r2_account_id
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.r2_bucket_name
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="R2 storage is not configured.",
        )

    try:
        title = await infer_job_title(
            client=client,
            job_description=request.job_description,
            model=settings.openai_model,
        )
    except JobTitleInferenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except OpenAIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI request failed: {exc}",
        ) from exc

    try:
        await store_inference_record(
            client=r2_client,
            bucket=settings.r2_bucket_name,
            job_description=request.job_description,
            job_title=title,
        )
    except InferenceStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return InferTitleResponse(job_title=title)
