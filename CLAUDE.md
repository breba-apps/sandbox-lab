# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Job Title Inferrer: a minimal FastAPI service with a single endpoint (`POST /infer-title`) that
infers a job title from a free-text job description using the OpenAI Responses API, then persists
the `job_description`/`job_title` pair to a Cloudflare R2 bucket via the S3-compatible API (boto3).
Dependencies and the virtualenv are managed with `uv`.

## Commands

```bash
# Install dependencies (creates .venv automatically)
uv sync

# Configure secrets (required before running, not before testing)
cp .env.example .env   # then set OPENAI_API_KEY and the R2_* variables

# Run the dev server
uv run uvicorn app.main:app --reload   # docs at http://127.0.0.1:8000/docs

# Run the full test suite
uv run pytest

# Run a single test file / test
uv run pytest tests/test_service.py
uv run pytest tests/test_api.py::test_infer_title_missing_api_key_returns_500

# Test the standalone Docker Sandbox setup CLI package
cd tools/setup-docker-sandbox
uv run pytest
```

Tests are fully offline: both the OpenAI client and the R2 client are faked via FastAPI
dependency overrides (`app.dependency_overrides`), so no API key, R2 credentials, or network
access is needed to run `pytest`.

## Architecture

Request flow: `app/main.py` (route) → `app/service.py` (OpenAI inference) → `app/storage.py`
(R2 write) — in that order; the response is only returned after both succeed.

- **`app/config.py`** — `Settings` (pydantic-settings) loads `OPENAI_API_KEY`, `OPENAI_MODEL`
  (default `gpt-4o-mini`), `REQUEST_TIMEOUT_SECONDS`, and `R2_ACCOUNT_ID`/`R2_ACCESS_KEY_ID`/
  `R2_SECRET_ACCESS_KEY`/`R2_BUCKET_NAME` from env vars / `.env`. `get_settings()` is `lru_cache`d
  and exposed as a FastAPI dependency.
- **`app/dependencies.py`** — `get_openai_client()` builds an `lru_cache`d `AsyncOpenAI` client.
  `get_r2_client()` builds an `lru_cache`d boto3 S3 client pointed at
  `https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com` with `region_name="auto"`. Its `Config` pins
  `request_checksum_calculation`/`response_checksum_validation` to `"when_required"` — newer
  botocore versions (≥1.36) default to trailing checksums on S3 calls that R2's S3-compatible API
  doesn't support, so this must stay set or uploads break. Both client factories are overridden in
  tests via `app.dependency_overrides[...]` instead of patching/mocking internals.
- **`app/service.py`** — `infer_job_title()` is the only place that talks to OpenAI. It calls
  `client.responses.create(model, instructions=SYSTEM_PROMPT, input=job_description)` and raises
  `JobTitleInferenceError` if the model returns empty output.
- **`app/storage.py`** — `store_inference_record()` is the only place that talks to R2. boto3 is
  sync, so the `put_object` call is run via Starlette's `run_in_threadpool` to avoid blocking the
  event loop; it raises `InferenceStorageError` on `BotoCoreError`/`ClientError`. Each record is
  written as a JSON object (`{"job_description": ..., "job_title": ...}`) to a UUID-keyed object
  at `inferences/<uuid>.json` — there's no listing/lookup endpoint, so the key only needs to be
  unique, not derivable.
- **`app/main.py`** — single route `POST /infer-title`. Order matters: missing `OPENAI_API_KEY` or
  any missing `R2_*` setting → `500`; `JobTitleInferenceError`/`OpenAIError` during inference → `502`;
  `InferenceStorageError` during the R2 write → `502` (write happens before the response, so a `200`
  guarantees the record was stored); pydantic validation produces `422`s.
- **`app/schemas.py`** — `InferTitleRequest` (`job_description`, 1–20,000 chars) /
  `InferTitleResponse` (`job_title`) pydantic models.
- **`tests/conftest.py`** — `FakeAsyncOpenAI`/`FakeResponses` and `FakeS3Client` fakes that record
  the last call and can be configured with a fixed return value or an exception to raise; used by
  both unit tests (service/storage layers) and integration tests (API layer via dependency override).

## Status code contract

| Status | Meaning |
| --- | --- |
| 200 | Title inferred and stored successfully |
| 422 | Invalid request body (e.g. empty `job_description`) |
| 500 | `OPENAI_API_KEY` or any `R2_*` setting not configured |
| 502 | OpenAI request failed, returned an empty title, or the R2 write failed |

Preserve this contract when touching `app/main.py` — it's covered directly by `tests/test_api.py`.

## Standalone Docker Sandbox Setup CLI

`tools/setup-docker-sandbox` is a separate reusable Python package that installs the
`setup-docker-sandbox` command. It is intentionally generic: it must not hardcode this
repo's environment variable names or provider names. The CLI asks how to handle every
`.env` entry, writes `proxy-secrets.env` for host-side Docker Sandbox secret
values, writes `runtime.env` for values intentionally visible to sandbox processes,
and stores only non-secret setup decisions in `sandbox-secrets.toml`.
Later runs reuse saved decisions and only prompt for new `.env` variables.
Never pass `proxy-secrets.env` to `sbx exec --env-file`; it contains
proxy-managed secrets that should not enter the sandbox.

Built-in Docker Sandbox service secrets use `sbx secret set` via stdin. Custom egress
secrets use `sbx secret set-custom` without `--value`, so Docker prompts for the
secret instead of exposing it in command arguments.

The tool package also contains an internal Codex skill at
`tools/setup-docker-sandbox/skills/setup-docker-sandbox-agent`. Keep that skill
aligned with CLI prompts and secret handling behavior whenever the tool workflow
changes.
