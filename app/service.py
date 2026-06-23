"""Business logic for inferring a job title via the OpenAI API."""

from openai import AsyncOpenAI

SYSTEM_PROMPT = (
    "You are an expert HR analyst. Given a job description, respond with the single "
    "most appropriate, concise, industry-standard job title that the description is "
    "for. Respond with ONLY the job title text — no quotes, no punctuation, no "
    "explanation, and no surrounding sentences."
)


class JobTitleInferenceError(RuntimeError):
    """Raised when the model fails to produce a usable job title."""


async def infer_job_title(
    client: AsyncOpenAI,
    job_description: str,
    model: str,
) -> str:
    """Infer a job title for ``job_description`` using the OpenAI Responses API.

    Args:
        client: An async OpenAI client.
        job_description: The free-text job description to analyze.
        model: The OpenAI model identifier to use.

    Returns:
        The inferred job title as a stripped string.

    Raises:
        JobTitleInferenceError: If the model returns an empty response.
    """
    response = await client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=job_description,
    )

    title = (response.output_text or "").strip().strip('"').strip()
    if not title:
        raise JobTitleInferenceError("The model returned an empty job title.")

    return title
