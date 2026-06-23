"""FastAPI application exposing a single job-title inference endpoint."""

from fastapi import Depends, FastAPI, HTTPException, status
from openai import AsyncOpenAI, OpenAIError

from .config import Settings, get_settings
from .dependencies import get_openai_client
from .schemas import InferTitleRequest, InferTitleResponse
from .service import JobTitleInferenceError, infer_job_title

app = FastAPI(
    title="Job Title Inferrer",
    description="Infers a job title from a job description using OpenAI.",
    version="0.1.0",
)


@app.post("/infer-title", response_model=InferTitleResponse)
async def infer_title(
    request: InferTitleRequest,
    client: AsyncOpenAI = Depends(get_openai_client),
    settings: Settings = Depends(get_settings),
) -> InferTitleResponse:
    """Infer the most appropriate job title for the supplied description."""
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OPENAI_API_KEY is not configured.",
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

    return InferTitleResponse(job_title=title)
