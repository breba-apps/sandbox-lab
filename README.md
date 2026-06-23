# Job Title Inferrer

A minimal [FastAPI](https://fastapi.tiangolo.com/) service with a single endpoint
that infers a job title from a job description using the
[OpenAI API](https://platform.openai.com/). Managed with [uv](https://docs.astral.sh/uv/).

## Setup

```bash
# Install dependencies (creates .venv automatically)
uv sync

# Configure secrets
cp .env.example .env
# then edit .env and set OPENAI_API_KEY
```

## Run

```bash
uv run uvicorn app.main:app --reload
```

Interactive docs are then available at http://127.0.0.1:8000/docs.

## API

### `POST /infer-title`

**Request body**

```json
{ "job_description": "Design and maintain scalable data pipelines and our warehouse." }
```

**Response**

```json
{ "job_title": "Data Engineer" }
```

Example:

```bash
curl -X POST http://127.0.0.1:8000/infer-title \
  -H "Content-Type: application/json" \
  -d '{"job_description": "Design and maintain scalable data pipelines."}'
```

| Status | Meaning                                              |
| ------ | ---------------------------------------------------- |
| 200    | Title inferred successfully                          |
| 422    | Invalid request body (e.g. empty `job_description`)  |
| 500    | `OPENAI_API_KEY` not configured                      |
| 502    | OpenAI request failed or returned an empty title    |

## Configuration

All settings are read from environment variables / `.env` (see `.env.example`):

| Variable                  | Default       | Description                     |
| ------------------------- | ------------- | ------------------------------- |
| `OPENAI_API_KEY`          | _(required)_  | OpenAI API key                  |
| `OPENAI_MODEL`            | `gpt-4o-mini` | Model used for inference        |
| `REQUEST_TIMEOUT_SECONDS` | `30`          | OpenAI client request timeout   |

## Tests

```bash
uv run pytest
```

Tests are fully offline — the OpenAI client is faked via FastAPI dependency
overrides, so no API key or network access is required.
