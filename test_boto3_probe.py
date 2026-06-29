"""Minimal boto3/R2 PUT probe for Docker Sandbox proxy debugging.

This intentionally uses the same R2 environment variable names as the app.
It prints endpoint and object metadata, but never prints credential values.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback

import boto3
from botocore.config import Config


REQUIRED_ENV = [
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_NAME",
]


def require_env() -> dict[str, str]:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        print(f"missing required env vars: {', '.join(missing)}", file=sys.stderr)
        raise SystemExit(2)

    return {name: os.environ[name] for name in REQUIRED_ENV}


def main() -> int:
    env = require_env()
    endpoint = f"https://{env['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
    key = f"sandbox-boto3-probe/{int(time.time())}.json"
    body = json.dumps({"probe": "sandbox-boto3", "ts": int(time.time())}).encode()

    print("endpoint:", endpoint)
    print("bucket:", env["R2_BUCKET_NAME"])
    print("key:", key)

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=env["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            connect_timeout=5,
            read_timeout=20,
            retries={"max_attempts": 1},
        ),
    )

    try:
        response = s3.put_object(
            Bucket=env["R2_BUCKET_NAME"],
            Key=key,
            Body=body,
            ContentType="application/json",
        )
    except Exception:
        print("PUT FAILED")
        traceback.print_exc()
        return 1

    print("PUT OK")
    print("status:", response["ResponseMetadata"]["HTTPStatusCode"])
    print("etag:", response.get("ETag"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
