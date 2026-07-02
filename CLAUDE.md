# CLAUDE.md

This file provides guidance to Claude Code when working at the repository root.

## Repository Purpose

This repository is a sandbox experimentation workspace. The top level documents
how sandboxes are organized and operated. Application code is encapsulated under
`app/`, and reusable host-side tools live under `tools/`.

## Layout

- `app/`: sample FastAPI app, app-specific `.env` files, tests, and app
  documentation. Docker Sandbox setup also writes app-owned generated files
  there when used for this sample app.
- `app/src/app/`: sample app source package.
- `tools/setup-docker-sandbox/`: reusable Docker Sandbox setup/start CLI.
- `tools/cloudflare-sandbox/`: reusable Cloudflare Sandbox setup/start tool,
  Worker service, local launcher, and tests.
- `tools/`: location for future sandbox-related tools.

## Commands

Root-level tool commands:

```bash
uv tool install ./tools/setup-docker-sandbox
uv tool install --reinstall ./tools/setup-docker-sandbox
cd tools/setup-docker-sandbox
uv run pytest
cd ../cloudflare-sandbox
npm install
npm run test:unit
npm run typecheck
```

Sample app commands:

```bash
cd app
uv sync
PYTHONPATH=src uv run uvicorn app.main:app --reload
uv run pytest
```

Docker Sandbox setup for the sample app should also run from `app/` so app-owned
configuration stays under `app/`:

```bash
cd app
setup-docker-sandbox
start-docker-sandbox
```

Cloudflare Sandbox setup follows the same app-owned boundary:

```bash
cd app
setup-cloudflare-sandbox
cf-sandbox-service   # run in another terminal
start-cloudflare-sandbox
```

When a new sandbox is needed, choose the create option from the
`start-docker-sandbox` sandbox selection menu. If run inside a Git repository,
it defaults to `sbx create --clone` from the Git root so the sandbox workspace
covers the full repository even when started from `app/`.

## Tool Boundary

`tools/setup-docker-sandbox` is a separate reusable Python package. It must stay
generic and must not hardcode this sample app's environment variable names or
provider choices.

The tool writes:

- `proxy-secrets.env`: host-side Docker Sandbox service/custom/registry secret
  values. Never pass this into sandbox processes.
- `runtime.env`: values intentionally visible to sandbox processes.
- `sandbox-secrets.toml`: non-secret setup decisions.

`start-docker-sandbox` does not manage the app's `.env`; the app runner or
sandbox agent should create `.env` from `.env.example` only for variables that
are not already present in the process environment. Pass agent arguments after
`--`, such as `start-docker-sandbox -- --continue`, to resume a prior agent
conversation.

The tool package also contains an internal Codex skill at
`tools/setup-docker-sandbox/skills/setup-docker-sandbox-agent`. Keep that skill
aligned with CLI prompts and secret-handling behavior whenever the tool workflow
changes.

`tools/cloudflare-sandbox` is a separate Node/Worker package. It should preserve
the app/runtime boundary: setup reads the app `.env`, writes app-owned generated
Cloudflare files, writes local Worker secrets to the tool's ignored `.dev.vars`,
`cf-sandbox-service` runs the local Wrangler service, and start attaches locally
through the Wrangler container. Do not pass `cloudflare-proxy-secrets.env` into
sandbox processes.
