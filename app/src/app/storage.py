"""Persistence of inference requests/responses to Cloudflare R2."""

import json
from uuid import uuid4

from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError
from starlette.concurrency import run_in_threadpool


class InferenceStorageError(RuntimeError):
    """Raised when persisting an inference record to R2 fails."""


async def store_inference_record(
    client: BaseClient,
    bucket: str,
    job_description: str,
    job_title: str,
) -> str:
    """Persist a job_description/job_title pair to R2 and return the object key.

    Raises:
        InferenceStorageError: If the underlying R2 PutObject call fails.
    """
    key = f"inferences/{uuid4()}.json"
    body = json.dumps(
        {"job_description": job_description, "job_title": job_title}
    ).encode("utf-8")

    try:
        await run_in_threadpool(
            client.put_object,
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
    except (BotoCoreError, ClientError) as exc:
        raise InferenceStorageError(f"Failed to store inference record in R2: {exc}") from exc

    return key
