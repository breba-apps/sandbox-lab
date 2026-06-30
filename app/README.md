# Job Title Inferrer Sample App

A minimal [FastAPI](https://fastapi.tiangolo.com/) service with a single endpoint
that infers a job title from a job description using the
[OpenAI API](https://platform.openai.com/). Every successful inference is persisted
to a [Cloudflare R2](https://developers.cloudflare.com/r2/) bucket through the
S3-compatible API.

This directory is a self-contained sample application. App source lives in
`src/app`, tests live in `tests`, and local app configuration lives beside this
README.

## Setup

Run commands from this `app/` directory.

```bash
uv sync
cp .env.example .env
```

Then edit `.env` and set `OPENAI_API_KEY` and the `R2_*` variables.

## Run

```bash
PYTHONPATH=src uv run uvicorn app.main:app --reload
```

Interactive docs are then available at http://127.0.0.1:8000/docs.

## API

### `POST /infer-title`

Request body:

```json
{ "job_description": "Design and maintain scalable data pipelines and our warehouse." }
```

Response:

```json
{ "job_title": "Data Engineer" }
```

Example:

```bash
curl -X POST http://127.0.0.1:8000/infer-title \
  -H "Content-Type: application/json" \
  -d '{"job_description": "Design and maintain scalable data pipelines."}'
```

| Status | Meaning |
| --- | --- |
| 200 | Title inferred and stored successfully |
| 422 | Invalid request body, such as an empty `job_description` |
| 500 | `OPENAI_API_KEY` or R2 storage (`R2_*`) not configured |
| 502 | OpenAI request failed, returned an empty title, or the R2 write failed |

On success, the `job_description` and inferred `job_title` are written as a JSON
object to the configured R2 bucket under `inferences/<uuid>.json`. The write
happens before the response is returned, so a `200` implies the record was stored.

## Configuration

All settings are read from environment variables or `.env`:

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | required | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used for inference |
| `REQUEST_TIMEOUT_SECONDS` | `30` | OpenAI client request timeout |
| `R2_ACCOUNT_ID` | required | Cloudflare account ID used to build the R2 endpoint |
| `R2_ACCESS_KEY_ID` | required | R2 API token access key ID |
| `R2_SECRET_ACCESS_KEY` | required | R2 API token secret access key |
| `R2_BUCKET_NAME` | required | R2 bucket that inference records are written to |

## Tests

```bash
uv run pytest
```

Tests are fully offline. The OpenAI client and R2 client are faked through
FastAPI dependency overrides, so no API key, R2 credentials, or network access is
required.

## Docker Sandbox Runtime Files

When using the root `tools/setup-docker-sandbox` CLI for this app, run it from
this `app/` directory so generated app-specific files stay encapsulated here:

```bash
setup-docker-sandbox
start-docker-sandbox
```

Use `start-docker-sandbox --create` to create a new Docker Sandbox from saved
config. From this app directory, newly created clone-mode sandboxes use the
repository root as their workspace while app-specific env files remain in
`app/`.

The generated files are:

| File | Purpose |
| --- | --- |
| `proxy-secrets.env` | Host-side service/custom/registry secret values used by Docker Sandbox setup |
| `runtime.env` | Values intentionally written into the sandbox runtime environment |
| `sandbox-secrets.toml` | Non-secret setup decisions for repeatable runs |

`setup-docker-sandbox` automatically adds missing entries for these generated
files to this directory's `.gitignore`.

Do not pass `proxy-secrets.env` into sandbox processes. It is host-only and may
contain real secret values.
