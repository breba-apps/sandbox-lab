---
name: setup-docker-sandbox-agent
description: Use when an AI agent needs to configure Docker Sandbox secrets for a project using the local setup-docker-sandbox CLI, especially from .env files, without relying on a human to answer every prompt. Guides agents through inspecting project config, classifying each env var, driving the interactive CLI, preserving proxy-secrets.env/runtime.env/sandbox-secrets.toml, and avoiding accidental secret exposure.
---

# Setup Docker Sandbox Agent

## Purpose

Use this skill to let an agent perform Docker Sandbox secret setup for a repo with the `setup-docker-sandbox` CLI. The agent should make defensible classifications from project context, ask the user only for missing secret values or high-risk ambiguity, and never print secret values.

## Workflow

1. Confirm the CLI is installed:

```bash
setup-docker-sandbox --help
```

If unavailable and this repo contains `tools/setup-docker-sandbox`, install or reinstall it:

```bash
uv tool install --reinstall ./tools/setup-docker-sandbox
```

2. Inspect local context before prompting:

- Read `.env.example`, `.env`, `.env.local`, README/setup docs, app config files, and Docker Sandbox notes if present.
- Identify every env var the selected env file contains.
- Determine likely use from code, not variable names alone.
- Do not print `.env` values.

3. Choose the Docker Sandbox scope:

- Prefer sandbox-scoped setup for project-specific credentials.
- Use host-only only when the host `sbx` command needs the credential and the sandbox/agent should not.
- Use global only when the user explicitly wants many future sandboxes to inherit the credential.
- Sandbox-scoped setup records reusable decisions. It does not bind the project config to one concrete sandbox name; `start-docker-sandbox` selects or creates the sandbox later.

4. Run the CLI and answer prompts as the agent:

```bash
setup-docker-sandbox
```

Do not expect a final plan screen. The CLI asks questions while it runs, records the answer for each variable, writes `proxy-secrets.env` / `runtime.env` / `sandbox-secrets.toml`, and runs supported global or host-side `sbx secret` commands. Sandbox-scoped Docker secret commands are applied by `start-docker-sandbox` after a concrete sandbox is selected or created.

On later runs, the CLI reuses existing decisions from `sandbox-secrets.toml` and values from `proxy-secrets.env` / `runtime.env`; it only asks about new `.env` variables and rewrites generated env files. Agents should still inspect new variables before answering.

5. Classify each env var:

- `safe runtime env var`: Non-sensitive config the sandbox/app can read, such as ports, model names, log levels, feature flags, public URLs, bucket names, account IDs, and timeouts.
- `built-in service secret`: A Docker-supported service secret. Use this before custom egress when the credential is for one of: `anthropic`, `aws`, `cursor`, `droid`, `github`, `google`, `groq`, `mistral`, `nebius`, `openai`, `openrouter`, `xai`. The tool stores it with `sbx secret set [-g | sandbox] SERVICE` via stdin, so the secret is not put in argv.
- `custom egress secret`: A non-built-in outbound API credential where the app can use a placeholder env var and Docker can replace the placeholder in request headers for one or more destination hosts. The CLI uses `sbx secret set-custom` without `--value`, so Docker prompts for the secret instead of exposing it in command arguments.
- `unsafe runtime secret`: A real secret the app or SDK must read locally, such as database URLs, JWT signing secrets, encryption keys, AWS/R2/S3 signing credentials, or credentials used to compute request signatures.
- `registry credential`: Token/password for a container registry such as `ghcr.io`, Docker Hub, ECR, ACR, or Artifact Registry.
- `skip`: Values not needed for Docker Sandbox setup.

When uncertain whether a secret can use a built-in service or custom egress, choose `unsafe runtime secret` unless code clearly shows simple outbound header/token usage compatible with Docker proxy injection.

For prompt answers:

- scope: `s`, `g`, or `h`
- variable handling: `s`, `b`, `c`, `u`, `r`, or `k`
- built-in service: service name or number from the CLI list
- custom egress host: the exact outbound host, such as `api.example.com`
- registry host: the exact registry host, such as `ghcr.io`
- registry username: only if required

6. Review redacted output:

- Confirm `proxy-secrets.env` contains only values that should stay host-side for Docker Sandbox service/custom/registry setup.
- Confirm `runtime.env` contains only values intentionally visible to sandbox processes.
- Confirm `sandbox-secrets.toml` contains no secret values.
- Confirm no command output includes real secret values.

7. Prefer built-in service secrets over custom egress when the service is supported. Built-in service and registry secrets are supplied via stdin; custom egress uses Docker's own prompt path.

8. Validate:

- Run `git status --short` and ensure generated secret files are ignored or intentionally untracked.
- Run the project’s existing tests if setup changes could affect local behavior.
- If `sbx ls` fails, run `sbx diagnose` or report the auth failure clearly.

## Starting Sandboxes

Use `start-docker-sandbox` when the user wants to start or attach to the agent sandbox for app work:

```bash
start-docker-sandbox
```

The command lists sandboxes for the current workspace and includes an option to
create a new sandbox from the same menu. It detects divergence between `.env`
and generated files, asks before updating generated files, reapplies Docker
Sandbox service/custom/registry secrets, writes only `runtime.env` values into a
managed block in `/etc/sandbox-persistent.sh`, then runs
`sbx run --name <sandbox>`.

When the create option is selected in a Git repository, creation defaults to
clone mode from the Git root, even if the CLI is run from a nested project
directory such as `app/`.

Do not manually pass `proxy-secrets.env` into the sandbox. It is host-only.
When the app needs `.env`, create it from `.env.example` only for variables that
are not already present in the process environment. Do not copy real
proxy-managed secret values into `.env`; use harmless placeholders only for
proxy-injected names that must exist locally.
Use `start-docker-sandbox -- --continue` when the user asks to resume the
agent's previous conversation.

## Agent Decision Rules

- Never echo `.env` values, command stdin secrets, or full contents of `proxy-secrets.env`.
- Never pass `proxy-secrets.env` to `sbx exec --env-file`; it contains proxy-managed secrets that must not enter the sandbox.
- Use `runtime.env` only when a process intentionally needs runtime-visible values, and only after checking its contents by variable name, not by value.
- Do not assume provider-specific names. Use code and docs to classify behavior.
- Ask the user only when a value is missing, an external host cannot be inferred, or a credential exposure choice is high risk.
- Treat `proxy-secrets.env` like `.env`: local-only, secret-bearing, and not suitable for commits.
- Treat `runtime.env` as secret-bearing when it includes `unsafe_runtime` values.
- Treat `sandbox-secrets.toml` as repeatability metadata only; it must not contain secret values.
- Prefer built-in service secrets over custom egress when the service is supported by `sbx secret set`.
- Use custom egress only for non-built-in services where request-header placeholder replacement is compatible.
- For SDKs that sign requests locally, such as S3-compatible clients, use unsafe runtime secrets rather than custom egress.
- For registry credentials, explain that sandbox-scoped/global registry access may be visible inside the sandbox Docker config.

## Final Response

Report:

- scope and sandbox name used
- number of vars written to `proxy-secrets.env` and `runtime.env`
- built-in service, custom egress, and registry secrets configured or skipped
- any secrets that remain runtime-visible
- whether generated env files are ignored by git
- validation commands run
