"""Request and response models for the API."""

from pydantic import BaseModel, Field


class InferTitleRequest(BaseModel):
    """Incoming request carrying the job description to analyze."""

    job_description: str = Field(
        ...,
        min_length=1,
        max_length=20_000,
        description="Free-text description of the role.",
        examples=[
            "We are looking for someone to design, build, and maintain scalable "
            "data pipelines, manage our warehouse, and support analytics teams."
        ],
    )


class InferTitleResponse(BaseModel):
    """Inferred job title for a given description."""

    job_title: str = Field(..., description="The inferred job title.")
