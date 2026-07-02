# Architecture

This project runs AI coding agents inside Cloudflare Sandbox containers behind a Worker-controlled boundary. The Worker owns session lifecycle, egress policy, credential injection, and the browser WebSocket bridge.

## System Boundaries

- **Worker (`src/index.ts`)**: HTTP/WebSocket entrypoint, Sandbox Durable Object lookup, egress allowlist, browser bridge, agent startup endpoint.
- **Sandbox container (`Dockerfile`)**: Runtime image with Codex and Claude CLIs installed. The container receives dummy credentials and provider base URLs only.
- **Browser client (`public/index.html`)**: Single-page UI that speaks Codex app-server JSON-RPC through the Worker WebSocket bridge.
- **Setup/start CLIs (`scripts/setup-cloudflare-sandbox.mjs`, `scripts/start-cloudflare-sandbox.mjs`)**: App-facing commands that generate Cloudflare runtime/proxy config, prepare a session, and attach locally.
- **Service CLI (`scripts/cf-sandbox-service.mjs`)**: Runs the local Wrangler Worker service separately from session attach.
- **Local development launcher (`scripts/sandbox-agent.mjs`)**: Lower-level helper that starts/prepares a Sandbox through the Worker and attaches to the local Wrangler container with `docker exec`.
- **Tests (`test/`)**: Fast Node tests for launcher behavior plus Wrangler-backed integration tests for Worker/Sandbox behavior.

## Session Model

Session ids are sanitized to `[a-zA-Z0-9_-]{1,64}` and map to Sandbox Durable Object names using `codex-<session>`.

There are two startup paths:

- **Browser path**: `GET /ws/<session>` upgrades to WebSocket, destroys any existing sandbox for that session, prepares a fresh sandbox, starts `codex app-server`, and bridges JSON-RPC frames through the handler pipeline.
- **Agent/CLI path**: `POST /sandbox/<session>/start` prepares a sandbox without starting `codex app-server`. It sets proxy and runtime environment variables, writes `/tmp/sandbox-session-name` for container selection, optionally checks out a repo, and only destroys the sandbox when `reset` is true.

Sandbox containers sleep after `SANDBOX_SLEEP_AFTER`, defaulting to `1m`.

## Browser Bridge

The browser bridge connects an external WebSocket client to `codex app-server` running inside the container on port `4500`.

Every JSON-RPC message passes through a composable handler pipeline:

- `log()`
- `enforceModel(...)`
- `enforcePolicy(...)`
- `sandboxSetup(...)`
- `sandboxExec(...)`
- `autoApprove()`

Handlers can pass messages through, rewrite them, or intercept them by replying directly to the client.

## Agent/CLI Attachment

The agent startup endpoint is deployable and does not assume Docker. The current Node launcher is local-development specific only at the attachment step:

1. Parse CLI options.
2. Call `POST /sandbox/<session>/start`.
3. Find the matching local Wrangler container by reading `/tmp/sandbox-session-name`.
4. Run `docker exec` with dummy provider env vars.
5. Bootstrap Codex or Claude credentials inside the container when needed.

Future deployed clients should use the same startup endpoint and attach through a deployment-specific mechanism instead of local Docker.

The app-facing `start-cloudflare-sandbox` command wraps this launcher. It reads
`cloudflare-sandbox.toml`, `cloudflare-runtime.env`, and
`cloudflare-proxy-secrets.env` from the app directory. Runtime values are sent
to the Worker and installed into the Sandbox. Proxy and signing secrets are
represented in the container as placeholders; the real values live in the
Worker environment. The local Worker service must already be running via
`cf-sandbox-service` or `npm run dev`; start does not launch Wrangler.

## Egress And Credentials

The Sandbox subclass disables direct internet access and enables HTTPS interception:

- `enableInternet = false`
- `interceptHttps = true`

Allowed hosts are implemented in `Sandbox.outboundByHost`:

- `api.openai.com`: injects `OPENAI_API_KEY`, removes Anthropic API-key headers, upgrades to HTTPS.
- `api.anthropic.com`: injects `CLAUDE_CODE_OAUTH_TOKEN` as Bearer or `ANTHROPIC_API_KEY` as `x-api-key`, upgrades to HTTPS.
- `platform.claude.com`: supports Claude Code OAuth validation with Bearer auth.
- `github.com`: upgrades to HTTPS and injects `GITHUB_TOKEN` as Basic auth when present.
- Allowed `*.r2.cloudflarestorage.com` hosts: requests are resigned with
  Worker-side R2 credentials using SigV4. The container receives placeholders
  only.

All other HTTP/HTTPS egress returns `403 Forbidden`. Provider secrets must not enter the container.

## Testing Strategy

- `npm run test:unit`: fast Node tests with fake dependencies. No Docker, Wrangler, network, or provider credentials.
- `npm run test:integration:web`: starts `wrangler dev` and verifies Worker/Sandbox behavior, including the agent startup endpoint and browser WebSocket bridge.
- `npm test`: runs unit tests, then WebSocket integration tests.
- `npm run test:egress`: runs egress validation against a Wrangler-backed sandbox.

Tests should prefer deterministic protocol and `sandbox/exec` assertions over exact model-output assertions.

## Known Follow-Ups

- Add a deployed attachment mechanism for agent/CLI clients.
- Move the remaining egress allowlist behavior fully behind generated config
  instead of hardcoded Worker handlers.
- Revisit whether `platform.claude.com` remains required for current Claude Code auth flows.
- Decide whether `sagent` should remain a Claude-defaulting alias or require an explicit command.
