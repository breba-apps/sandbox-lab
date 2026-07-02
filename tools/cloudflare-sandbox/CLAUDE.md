# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
cp .dev.vars.example .dev.vars   # first-time setup: add OPENAI_API_KEY
npm install
npm run dev        # start local dev server (first run builds Docker image: 2-3 min)
npm run start      # same as dev but without the egress image override
npm run cf-sandbox-service  # run local Wrangler service via the app-facing service command
npm run setup-cloudflare-sandbox  # app-facing setup command, normally run from app/
npm run start-cloudflare-sandbox  # app-facing start command, normally run from app/
npm run typecheck  # tsc --noEmit
npm run test:unit  # fast launcher/bootstrap tests; no Docker, Wrangler, or credentials
npm test           # unit tests, then WebSocket integration tests via wrangler dev
npm run test:egress  # validate egress constraints via wrangler dev
```

Deploy:
```bash
wrangler secret put OPENAI_API_KEY
npm run deploy
```

## Architecture

This is a Cloudflare Worker that acts as a WebSocket middleman between a browser client and an OpenAI Codex `app-server` process running inside a Cloudflare Sandbox container.

Durable architecture context lives in `architecture.md`; decision history lives in `decisions.md`. Update those files when behavior, lifecycle, boundaries, or tradeoffs change.

**Key files:**
- `architecture.md` — Current system architecture, lifecycle model, egress model, and testing strategy
- `decisions.md` — Architecture decisions and revisit criteria
- `src/index.ts` — Worker entrypoint: `Sandbox` Durable Object subclass, egress handlers, WebSocket bridge, `sandboxSetup`/`sandboxExec` custom RPC handlers
- `src/rpc.ts` — JSON-RPC types and composable handler pipeline (`compose`, `log`, `enforceModel`, `enforcePolicy`, `autoApprove`)
- `public/index.html` — Single-file vanilla JS browser client
- `Dockerfile` — Container image: `cloudflare/sandbox` base + `@openai/codex` CLI
- `scripts/cf-sandbox-service.mjs` — App-facing service command that runs local Wrangler
- `scripts/setup-cloudflare-sandbox.mjs` — App-facing setup command that reads app `.env`, writes app-owned generated files, and writes local Worker `.dev.vars`
- `scripts/start-cloudflare-sandbox.mjs` — App-facing start command that requires the Worker service to already be running, prepares a session, and attaches locally
- `scripts/lib/cloudflare-config.mjs` — Shared Cloudflare env/manifest helpers
- `scripts/sandbox-agent.mjs` — Local-development `sagent`/`sclaude`/`scodex` launcher for starting a Sandbox session and `docker exec`ing into the Wrangler container
- `test/` — Node test suites split into fast unit/bootstrap tests and Wrangler-backed integration tests

**Handler pipeline:** Every JSON-RPC message through the WebSocket bridge passes through `compose(...handlers)`. Each handler returns the message (possibly rewritten), or `null` to drop it (after optionally calling `ctx.sendToClient`/`ctx.sendToServer`). Direction is `'client-to-server'` or `'server-to-client'`.

**Security model:**
- `enableInternet = false` — blocks all direct outbound TCP from the container
- `interceptHttps = true` — Cloudflare CA cert injected so HTTPS also flows through egress handlers
- `Sandbox.outboundByHost` allowlist: `api.openai.com` (injects real API key, upgrades to HTTPS), `github.com` (upgrades to HTTPS)
- `Sandbox.outbound` catch-all: returns 403
- The container uses a dummy `OPENAI_API_KEY=proxy-injected`; the real key lives only in the Worker env

**Session lifecycle:** Each `/ws/<session-name>` connects to a distinct Durable Object (`codex-<session-name>`). On every WebSocket connection, the existing sandbox is destroyed, Codex `app-server` is started fresh on port 4500, and the Worker bridges frames through the pipeline.

**Agent/CLI lifecycle:** `setup-cloudflare-sandbox`, `cf-sandbox-service`, and `start-cloudflare-sandbox` are the app-facing commands. `cf-sandbox-service` owns the local Wrangler process. `start-cloudflare-sandbox` wraps `scripts/sandbox-agent.mjs`, calls `POST /sandbox/<session>/start` to prepare the sandbox without starting the browser Codex app-server bridge, then runs `docker exec` into the marked local Wrangler container. The startup endpoint is deployable; non-local clients can attach through a deployment-specific mechanism. Existing sandbox state is reused until `SANDBOX_SLEEP_AFTER`; use `--reset` for a clean sandbox and `--no-tty` for non-interactive automation.

**Local vs. deployed behavior:** `wrangler dev` now supports full outbound interception via a TPROXY sidecar inside the sandbox's network namespace, mirroring production behavior. The dev script sets `MINIFLARE_CONTAINER_EGRESS_IMAGE` for the local container image.
