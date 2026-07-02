# Cloudflare Sandbox Tool

Runs coding agents inside a [Cloudflare Sandbox](https://developers.cloudflare.com/sandbox/) with a Worker-controlled egress boundary. This package provides the Cloudflare runtime alternative for the root sandbox lab:

```bash
setup-cloudflare-sandbox
start-cloudflare-sandbox
```

The Worker service still includes the inherited browser Codex app-server bridge, but the primary tool workflow is the local setup/start path. The app remains agnostic: setup is run from the app directory, generated app config stays under the app directory, and proxy/signing secrets stay outside the sandbox container.

```
Browser                     Worker (middleman)              Sandbox Container
 ─────────────           ─────────────────────          ──────────────────────
│             │ WebSocket │  handler pipeline  │ WebSocket │ codex app-server  │
│  Client UI  │◄─────────►│  (inspect/rewrite/ │◄────────►│ :4500             │
│             │           │   intercept)       │          │                   │
│             │           │  egress handlers   │          │ OPENAI_BASE_URL=  │
│             │           │  ┌───────────────┐ │          │ http://api.openai │
│             │           │  │api.openai.com │──► inject API key ──► OpenAI
│             │           │  │github.com     │──► upgrade to HTTPS ──► GitHub
│             │           │  │* (catch-all)  │──► 403 Forbidden
│             │           │  └───────────────┘ │
│             │           │                     │
│             │           │  enableInternet=false│
│             │           │  interceptHttps=true │
```

## Tool Quick Start

From the sample app directory:

```bash
npm install -g ./tools/cloudflare-sandbox   # from the repository root, first time
cd app
setup-cloudflare-sandbox
cf-sandbox-service                          # run in another terminal
start-cloudflare-sandbox
```

`setup-cloudflare-sandbox` reads `.env`, asks how each variable should be handled, and writes:

| File | Purpose |
| --- | --- |
| `cloudflare-runtime.env` | Values intentionally visible to the Cloudflare Sandbox container |
| `cloudflare-proxy-secrets.env` | Host-side proxy/signing values copied into this tool's ignored `.dev.vars` for local Worker runs |
| `cloudflare-sandbox.toml` | Non-secret setup decisions |

`cf-sandbox-service` starts the local Wrangler service and streams its output.
Keep it running in one terminal. `start-cloudflare-sandbox` does not start
Wrangler; it fails with startup instructions when the service is not reachable.
When the service is running, `start-cloudflare-sandbox` prepares/reuses a
Cloudflare Sandbox session, checks out the configured repo into `/workspace`,
and attaches locally with `docker exec`.

Pass agent arguments after `--`:

```bash
start-cloudflare-sandbox -- --continue
start-cloudflare-sandbox --shell
start-cloudflare-sandbox --no-tty -- echo OK
```

## Worker Development

```bash
cp .dev.vars.example .dev.vars   # add your OPENAI_API_KEY
npm install
npm run dev
```

Open `http://localhost:8787`. Enter a session name, optionally a repo URL, and click **Connect**.

The first run builds the Docker container (2-3 minutes). Subsequent runs reuse the cached image.

> **Note:** The setup command can generate `.dev.vars` from the app-owned Cloudflare config. Do not commit `.dev.vars`.

## Local sandbox agent CLI

With `wrangler dev` running, use the Node helper to start a Sandbox session,
optionally clone a GitHub repo into `/workspace`, and attach an interactive
command to the local development container with `docker exec`:

```bash
npm run sagent -- --repo https://github.com/org/repo -- bash
npm run sclaude -- --repo https://github.com/org/repo
npm run scodex -- --repo https://github.com/org/repo
```

The helper starts the sandbox through `POST /sandbox/<session>/start`. That
endpoint is not tied to local development; it prepares the Sandbox without
using the browser WebSocket bridge or starting `codex app-server`. This Node
helper then attaches to the local Wrangler container with `docker exec` as
`appuser` in `/workspace`. A deployed client can use the same startup endpoint
and attach through a deployment-specific mechanism. Existing sandbox state is
reused until `SANDBOX_SLEEP_AFTER`; pass `--reset` to destroy and recreate the
sandbox before attaching.

For automation, pass `--no-tty` so the helper uses non-interactive
`docker exec -i` instead of `docker exec -it`:

```bash
npm run sagent -- --session cli-test --no-setup --no-tty -- sh -lc 'echo CLI_OK'
```

`start-cloudflare-sandbox` wraps this lower-level helper for normal app usage.
It assumes `cf-sandbox-service` or `npm run dev` is already running.

If `--repo` is omitted, the helper tries to use the current directory's
`origin` remote. SSH-style GitHub remotes such as
`git@github.com:org/repo.git` are converted to HTTPS before checkout.

`sclaude` requires `CLAUDE_CODE_OAUTH_TOKEN` (subscription auth from
`claude setup-token`) or `ANTHROPIC_API_KEY` in `.dev.vars`. The container
receives only `ANTHROPIC_BASE_URL=http://api.anthropic.com` and a dummy
credential; the Worker injects the real one when egressing to Anthropic.

Claude and Codex are launched in full-permission mode because the Cloudflare
Sandbox is the external security boundary:

- Claude: `--dangerously-skip-permissions`
- Codex: `--dangerously-bypass-approvals-and-sandbox`

## Deploy

```bash
wrangler secret put OPENAI_API_KEY
npm run deploy
```

## Configuration

Environment variables (set in `.dev.vars` locally, `wrangler secret` in production):

| Variable              | Required | Description                                                                                  |
| --------------------- | -------- | -------------------------------------------------------------------------------------------- |
| `OPENAI_API_KEY`      | yes      | Injected into sandbox HTTP/HTTPS requests via the egress proxy. Never reaches the container. |
| `CLAUDE_CODE_OAUTH_TOKEN`| no    | Subscription auth for `sclaude` (token from `claude setup-token`). Injected as a Bearer credential. Never reaches the container. |
| `ANTHROPIC_API_KEY`   | no       | API-key auth for `sclaude`. Injected as `x-api-key`. Never reaches the container.            |
| `AUTH_TOKEN`          | no       | If set, clients must provide `Authorization: Bearer <token>` or `?token=<token>`.            |
| `SANDBOX_SLEEP_AFTER` | no       | How long the container stays alive after the last request. Default: `1m`.                    |

The generated app-side `cloudflare-runtime.env` values are sent to
`POST /sandbox/<session>/start` and installed with `sandbox.setEnvVars(...)`.
Proxy/signing variables are passed into the container only as placeholders such
as `proxy-injected`; the real values live in the Worker environment.

## How it works

See [`architecture.md`](architecture.md) for durable architecture context and
[`decisions.md`](decisions.md) for decision history and revisit criteria.

### Sandbox subclass

The Worker exports a `Sandbox` subclass with two security settings:

```typescript
export class Sandbox extends BaseSandbox<Env> {
  enableInternet = false; // block direct internet at the network level
  interceptHttps = true; // intercept HTTPS via Cloudflare CA cert injection
}
```

- **`enableInternet = false`** — disables direct outbound network access from the container. Only traffic handled by `outboundByHost` or `outbound` handlers can leave.
- **`interceptHttps = true`** — injects a Cloudflare CA certificate into the container so HTTPS traffic flows through the same egress handlers as HTTP. Without this, HTTPS would bypass the proxy.

### Session lifecycle

Browser clients connect to `/ws/<session-name>`. The session name maps to a Sandbox Durable Object instance. On connect, the Worker:

1. Destroys any existing sandbox for that session (clean slate)
2. Starts the Codex app-server process inside the container
3. Bridges WebSocket frames between the browser and container through the handler pipeline

The client then runs the connection flow:

1. `sandbox/setup` — clone a git repo into `/workspace` (optional)
2. `initialize` / `initialized` — Codex protocol handshake
3. `thread/start` — create a single conversation thread
4. `turn/start` — send prompts, receive streamed responses

Each browser session operates a single thread. On disconnect, the sandbox sleeps after `SANDBOX_SLEEP_AFTER`. Reconnecting with the same browser session name destroys and recreates it.

Agent/CLI clients use `POST /sandbox/<session-name>/start` instead. That path
sets the proxy environment and writes a session marker for container selection,
but does not start `codex app-server` or destroy the sandbox unless `--reset`
is passed.

### Handler pipeline

Every JSON-RPC message flowing through the WebSocket bridge passes through a composable handler pipeline. Each handler can **pass through** (return the message), **rewrite** (return a modified copy), or **intercept** (return `null` after responding via the context object).

```typescript
type MessageHandler = (msg: JsonRpcMessage, ctx: HandlerContext) => JsonRpcMessage | null;

const pipeline = compose(
  log(),                    // observe all traffic
  enforceModel('gpt-5.4'), // force model on thread/turn start
  enforcePolicy({...}),    // override approval + sandbox policies
  sandboxSetup(sandbox),   // intercept sandbox/setup
  sandboxExec(sandbox),    // intercept sandbox/exec
  autoApprove()            // auto-approve tool execution requests
);
```

Built-in handlers (defined in `src/rpc.ts`):

| Handler            | Direction     | Action                                                                           |
| ------------------ | ------------- | -------------------------------------------------------------------------------- |
| `log()`            | both          | Log every message to the Workers console                                         |
| `enforceModel(m)`  | client→server | Force model on `thread/start` and `turn/start`                                   |
| `enforcePolicy(o)` | client→server | Override approval/sandbox policy on `turn/start`, `thread/start`, `command/exec` |
| `autoApprove()`    | server→client | Auto-approve `commandExecution` and `fileChange` requests                        |

Custom handlers (defined in `src/index.ts`):

| Handler           | Direction     | Action                                                                 |
| ----------------- | ------------- | ---------------------------------------------------------------------- |
| `sandboxSetup(s)` | client→server | Intercept `sandbox/setup` — wipe `/workspace` and `gitCheckout` a repo |
| `sandboxExec(s)`  | client→server | Intercept `sandbox/exec` — run a shell command, return stdout/stderr   |

### Egress control

The Sandbox subclass combines three layers of network control to minimize data exfiltration risk:

1. **`enableInternet = false`** — blocks all direct outbound connections at the network level. Raw TCP to hosts not in `outboundByHost` is refused.
2. **`interceptHttps = true`** — HTTPS traffic is intercepted via a Cloudflare-injected CA certificate, so it flows through the same handlers as HTTP.
3. **`outboundByHost` + `outbound`** — application-level allowlist with a deny-by-default catch-all.

| Host             | Protocol     | Action                                                             |
| ---------------- | ------------ | ------------------------------------------------------------------ |
| `api.openai.com` | HTTP + HTTPS | Allowed — Worker injects `OPENAI_API_KEY` and upgrades to HTTPS    |
| `api.anthropic.com` | HTTP + HTTPS | Allowed — Worker injects `CLAUDE_CODE_OAUTH_TOKEN` (Bearer) or `ANTHROPIC_API_KEY` (`x-api-key`) and upgrades to HTTPS |
| `platform.claude.com` | HTTPS      | Allowed — Claude Code OAuth validation; Worker injects `CLAUDE_CODE_OAUTH_TOKEN` (Bearer) |
| `github.com`     | HTTP + HTTPS | Allowed — upgrades to HTTPS (needed for `sandbox/setup` git clone), injects `GITHUB_TOKEN` when present |
| Common coding hosts | HTTP + HTTPS | Allowed — GitHub assets, package registries, OS package mirrors, Docker registries, language toolchains, CDN hosts, and certificate validation hosts |
| `*.r2.cloudflarestorage.com` | HTTP + HTTPS | Allowed only when generated config includes the host — Worker signs with R2 credentials using SigV4 |
| Everything else  | HTTP + HTTPS | Blocked with `403 Forbidden`                                       |
| Non-HTTP traffic | Raw TCP      | Blocked by `enableInternet = false` for non-allowed hosts          |

The container never sees the real provider keys. It uses provider base URLs and
placeholder credentials such as `proxy-injected` so requests flow through the
egress proxy. The Worker swaps in token credentials for token-header APIs and
resigns allowed R2/S3 requests with Worker-side SigV4 credentials.

> **Note:** DNS resolution is unrestricted, but without network access to blocked hosts, DNS alone does not enable data exfiltration.

### Browser client

`public/index.html` is a single-file vanilla HTML/CSS/JS client with a dark terminal-meets-chat aesthetic:

- **Session gate** — enter a session name and optional repo URL (persisted in localStorage)
- **Streaming chat** — agent messages stream in via `item/agentMessage/delta` with a blinking cursor
- **Tool call grid** — command executions and file changes render in a two-column grid with collapsible output, exit codes, duration, and color-coded diffs
- **JSON-RPC log** — toggleable side panel showing raw protocol traffic for debugging

The WebSocket endpoint is injected into the HTML via `HTMLRewriter` setting a `data-ws-endpoint` attribute on the `<html>` element.

## Testing

### Unit and launcher tests

```bash
npm run test:unit
```

Runs fast Node tests under `test/` for the local launcher, Claude/Codex
bootstrap wrappers, and fake CLI execution. These tests do not require Docker,
Wrangler, network access, or API credentials.

### WebSocket integration test

```bash
npm test
npm run test:integration:web
```

Runs unit tests, then starts `wrangler dev`, waits for readiness, and runs the
WebSocket integration suite. The integration tests connect to `/ws/<session>`
and exercise bridge behavior such as `initialize`, `thread/start`,
`sandbox/setup`, `sandbox/exec`, session isolation, and reconnect reset.

`./run-integration-tests.sh` remains as a compatibility wrapper around
`test/run-integration-tests.sh`.

### Egress validation

```bash
npm run test:egress                     # starts wrangler dev, runs egress checks
node test-egress.mjs                    # against an already-running localhost:8787
WS_URL=wss://your-app.workers.dev/ws/test node test-egress.mjs  # against production
```

Validates egress constraints from inside the container:

- `api.openai.com` returns 200 with API key injected (container only has dummy key)
- `github.com` returns 301 (allowed)
- `example.com` and `httpbin.org` return 403 (blocked)
- Response body contains "Forbidden by egress policy"

When deployed with `interceptHttps = true`, HTTPS requests to blocked hosts also return 403. With `enableInternet = false`, raw TCP connections to non-allowed hosts time out.

## Code structure

```
codex-app-server/
├── Dockerfile               cloudflare/sandbox:0.12.3-python + appuser + agent CLIs
├── wrangler.jsonc            Worker + Sandbox Durable Object + container config
├── .dev.vars.example         Environment variable template
├── architecture.md           Durable architecture context
├── decisions.md              Architecture decision history
├── scripts/
│   └── sandbox-agent.mjs      Local sagent/sclaude/scodex launcher
├── src/
│   ├── index.ts              Worker: Sandbox subclass, egress proxy, WebSocket bridge, agent startup endpoint
│   └── rpc.ts                JSON-RPC types + composable handler pipeline
├── public/
│   └── index.html            Browser client (session gate, streaming chat, tool grid)
├── test/                     Node unit tests and Wrangler-backed integration tests
├── test-egress.mjs           Egress constraint validation test
└── run-integration-tests.sh  Test runner (starts wrangler dev, runs test, tears down)
```
