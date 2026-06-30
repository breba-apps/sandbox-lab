# setup-docker-sandbox

Interactive CLI for preparing Docker Sandbox credentials from any project's `.env`
file.

The tool does not assume variable names. For each `.env` entry it asks whether the
value is safe runtime configuration, a built-in service secret, a custom egress
secret, an unsafe runtime secret, a registry credential, or should be skipped.

## Install

From this repository:

```bash
uv tool install ./tools/setup-docker-sandbox
```

From a GitHub repository:

```bash
uv tool install git+https://github.com/OWNER/REPO.git#subdirectory=tools/setup-docker-sandbox
```

After PyPI publication:

```bash
uv tool install setup-docker-sandbox
```

## Use

Run it from the project that owns the `.env` file:

```bash
setup-docker-sandbox
start-docker-sandbox
setup-docker-sandbox --env-file .env.local
setup-docker-sandbox --dry-run
```

When sandbox-scoped setup is selected, the CLI records that the decision should
be applied to a sandbox later. It does not store a concrete sandbox name in
`sandbox-secrets.toml`; `start-docker-sandbox` chooses or creates the sandbox
instance at application time.

The tool writes:

- `proxy-secrets.env`: host-side proxy/service/custom/registry secret values used to reapply Docker Sandbox secrets.
- `runtime.env`: only values intentionally visible to sandbox processes (`safe_env` plus `unsafe_runtime`).
- `sandbox-secrets.toml`: non-secret setup decisions for repeatable future runs.
  Sandbox-scoped decisions are intentionally not bound to one sandbox name.

If these generated files are not already covered by `.gitignore`,
`setup-docker-sandbox` appends the missing entries automatically.

`proxy-secrets.env` contains real secrets and must be treated like `.env`. Do not
pass it to `sbx exec --env-file`; those values should stay host-side. If you
need runtime env for a process, use `runtime.env` and only after confirming every
value in it is intended to be visible to that process.

On later runs, the CLI reuses saved decisions from `sandbox-secrets.toml` and
values from `proxy-secrets.env` / `runtime.env`. It only asks classification
questions for new `.env` variables, then reapplies all known sandbox secrets to
the selected workspace sandbox and rewrites both generated env files.

## Docker Sandbox Commands

The CLI uses stdin for Docker Sandbox commands that support it, such as built-in
service secrets and registry credentials. Custom egress secrets use Docker's
experimental `sbx secret set-custom` without `--value`, so Docker prompts for the
secret instead of exposing it in command arguments.

## Starting Sandboxes

Use `start-docker-sandbox` instead of calling `sbx run` directly when the app
needs runtime environment variables.

The command:

- lists Docker Sandboxes for the current workspace and asks which one to use
- offers to create a new sandbox from the same selection menu
- compares `.env` with `proxy-secrets.env`, `runtime.env`, and `sandbox-secrets.toml`
- asks before updating generated files when `.env` diverges
- reapplies Docker Sandbox service/custom/registry secrets for the selected sandbox
- writes `runtime.env` values into a managed block in `/etc/sandbox-persistent.sh`
- starts or attaches with `sbx run --name <sandbox>`

Only `runtime.env` values are written into the sandbox. `proxy-secrets.env`
remains host-side.

When you choose the create option, `start-docker-sandbox` creates the sandbox
before applying the saved config. In a Git repository, creation defaults to
`sbx create --clone` using the Git root as the sandbox workspace, even when the
command is run from a nested app directory.

## Agent Skill

The package includes an internal Codex skill at
`skills/setup-docker-sandbox-agent`. It tells an agent how to inspect project
context, classify `.env` entries, drive this CLI without asking a human for every
prompt, and report the resulting Docker Sandbox setup safely.
