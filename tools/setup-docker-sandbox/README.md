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
setup-docker-sandbox --env-file .env.local
setup-docker-sandbox --dry-run
```

When sandbox-scoped setup is selected, the CLI lists existing Docker Sandboxes
for the current workspace from `sbx` and requires selecting one from the list.

The tool writes:

- `safe.env`: values the user marked as safe runtime environment variables.
- `unsafe.env`: sensitive values, including proxied and unsafe runtime secrets.
- `sandbox-secrets.toml`: non-secret setup decisions for repeatable future runs.

`unsafe.env` contains real secrets and must be treated like `.env`.

## Docker Sandbox Commands

The CLI uses stdin for Docker Sandbox commands that support it, such as built-in
service secrets and registry credentials. Custom egress secrets use Docker's
experimental `sbx secret set-custom` without `--value`, so Docker prompts for the
secret instead of exposing it in command arguments.

## Agent Skill

The package includes an internal Codex skill at
`skills/setup-docker-sandbox-agent`. It tells an agent how to inspect project
context, classify `.env` entries, drive this CLI without asking a human for every
prompt, and report the resulting Docker Sandbox setup safely.
