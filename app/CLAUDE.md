# CLAUDE.md

This file provides guidance to Claude Code when working on the sample FastAPI
application in this directory.

## Project Overview

Job Title Inferrer is a minimal FastAPI service with one endpoint,
`POST /infer-title`. It infers a job title from a free-text job description using
the OpenAI Responses API, then persists the `job_description`/`job_title` pair to
Cloudflare R2 through the S3-compatible API.

## Commands

Run these commands from `app/`.

```bash
uv sync
cp .env.example .env

PYTHONPATH=src uv run uvicorn app.main:app --reload
uv run pytest
uv run pytest tests/test_service.py
uv run pytest tests/test_api.py::test_infer_title_missing_api_key_returns_500
```

Tests are fully offline. Both the OpenAI client and the R2 client are faked
through FastAPI dependency overrides, so no API key, R2 credentials, or network
access is needed for `pytest`.

## Architecture

Request flow:

```text
src/app/main.py -> src/app/service.py -> src/app/storage.py
```

The response is only returned after inference and storage both succeed.

- `src/app/config.py`: `Settings` loads `OPENAI_API_KEY`, `OPENAI_MODEL`,
  `REQUEST_TIMEOUT_SECONDS`, and the `R2_*` settings from environment variables
  or `.env`.
- `src/app/dependencies.py`: builds cached OpenAI and boto3 S3-compatible R2
  clients. The R2 client points at
  `https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com` with `region_name="auto"`.
  Its botocore `Config` pins `request_checksum_calculation` and
  `response_checksum_validation` to `when_required`; keep this or R2 uploads can
  break with newer botocore defaults. Client factories are overridden in tests
  through `app.dependency_overrides[...]`; prefer that over patching internals.
- `src/app/service.py`: owns the OpenAI call. It calls
  `client.responses.create(model, instructions=SYSTEM_PROMPT, input=job_description)`,
  strips wrapping whitespace and quotes from the returned title, and raises
  `JobTitleInferenceError` for empty model output.
- `src/app/storage.py`: owns the R2 `put_object` call. boto3 is sync, so storage
  runs in Starlette's threadpool. Each record is written as JSON
  `{"job_description": ..., "job_title": ...}` to `inferences/<uuid>.json`.
  There is no listing or lookup endpoint, so keys only need to be unique.
- `src/app/main.py`: owns the HTTP route and status-code mapping. Order matters:
  missing `OPENAI_API_KEY` or any missing `R2_*` setting returns `500`;
  OpenAI/model failures return `502`; R2 write failures return `502`; pydantic
  validation returns `422`. The R2 write happens before the response, so a `200`
  guarantees the record was stored.
- `src/app/schemas.py`: request/response pydantic models.
- `tests/conftest.py`: fake OpenAI and R2 clients used by unit and API tests.
  The fakes record the last call and can be configured to return fixed values or
  raise exceptions.

## Status Code Contract

| Status | Meaning |
| --- | --- |
| 200 | Title inferred and stored successfully |
| 422 | Invalid request body, such as an empty `job_description` |
| 500 | `OPENAI_API_KEY` or any `R2_*` setting not configured |
| 502 | OpenAI request failed, returned an empty title, or the R2 write failed |

Preserve this contract when touching `src/app/main.py`; it is covered by
`tests/test_api.py`.

## Sandbox Env Handling

Run `setup-docker-sandbox` and `start-docker-sandbox` from this `app/` directory
when configuring this sample app. App-specific `.env`, `runtime.env`,
`proxy-secrets.env`, and `sandbox-secrets.toml` belong here, not at repository
root.

For R2/boto3, the app uses boto3's default addressing behavior. Do not force
path-style addressing unless that becomes an explicit app requirement.
