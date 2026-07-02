# Decisions

## 2026-06-10: Split Browser Bridge Startup From Agent Startup

### Context

The original local `sagent`/`sclaude`/`scodex` launcher used the browser WebSocket path, `/ws/<session>`, to start a Sandbox and run `sandbox/setup`. That path always destroyed the existing session and started `codex app-server`, even when the requested command was Claude or a shell.

This made concurrent or resumable CLI use unsafe:

- multiple agents using the same session raced on `sandbox.destroy()`;
- a Claude run could be replaced by a Codex run using the same default session;
- local container selection picked the newest container when more than one sandbox existed;
- CLI startup paid the cost of starting the browser-only Codex app-server bridge.

### Decision

Introduce `POST /sandbox/<session>/start` as the agent startup path.

The endpoint:

- prepares the Sandbox without starting `codex app-server`;
- sets dummy provider env vars used by the egress proxy;
- writes `/tmp/sandbox-session-name` for local container selection;
- optionally checks out a repo into `/workspace`;
- reuses existing sandbox state by default;
- destroys and recreates the sandbox only when `reset` is true.

Keep `/ws/<session>` as the browser bridge path. It still destroys the session on connect, starts `codex app-server`, and bridges JSON-RPC frames through the handler pipeline.

### Consequences

- Local CLI startup no longer depends on the browser WebSocket bridge.
- `sclaude` and `scodex` can reuse a sandbox until `SANDBOX_SLEEP_AFTER` when `--reset` is not passed.
- Local Docker attachment can select the correct container by session marker instead of newest container.
- The startup endpoint is deployable; only the current Node launcher attachment method is local-development specific.
- Browser reconnect behavior remains clean and deterministic.

### Revisit Criteria

- When adding deployed agent attachment support.
- If browser users need resumable sessions instead of clean reconnects.
- If Cloudflare Sandbox exposes a first-class container attach/exec mechanism that can replace local Docker probing.

## 2026-06-10: Keep Real Provider Credentials Outside The Container

### Context

The Sandbox runs untrusted or semi-trusted agent commands. Provider credentials should not be visible inside the container, but Codex and Claude CLIs still require some credential-shaped state to start non-interactively.

### Decision

The container receives dummy credentials and provider base URLs. The Worker egress handlers inject real provider credentials only when outbound requests target allowed provider hosts.

Codex bootstrap writes/login-seeds from `OPENAI_API_KEY=proxy-injected`. Claude bootstrap writes dummy OAuth credentials under `~/.claude` and marks onboarding complete.

### Consequences

- Real OpenAI and Anthropic secrets remain in Worker env and do not enter the container.
- Egress tests must verify both allowlisted provider behavior and deny-by-default blocked hosts.
- CLI bootstrap tests should assert dummy credential shape without embedding real local secrets.

### Revisit Criteria

- If provider CLIs add a supported non-interactive auth mode compatible with proxy injection.
- If Anthropic API-key mode needs first-class launcher support beyond OAuth-shaped Claude credentials.
