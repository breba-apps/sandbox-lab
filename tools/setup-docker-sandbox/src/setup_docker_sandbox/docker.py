from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess

from setup_docker_sandbox.models import Decision, DockerCommand, Mode, Scope


@dataclass(frozen=True)
class SandboxListResult:
    names: list[str]
    error: str | None = None
    all_names: list[str] | None = None


BUILT_IN_SERVICES = [
    "anthropic",
    "aws",
    "cursor",
    "droid",
    "github",
    "google",
    "groq",
    "mistral",
    "nebius",
    "openai",
    "openrouter",
    "xai",
]


def sbx_available() -> bool:
    return shutil.which("sbx") is not None


def list_sandboxes(root: Path | None = None) -> list[str]:
    return list_sandboxes_result(root).names


def list_sandboxes_result(root: Path | None = None) -> SandboxListResult:
    if not sbx_available():
        return SandboxListResult([], "sbx was not found on PATH")

    candidates = [
        ["sbx", "ls", "--json"],
    ]
    if root is None:
        candidates.append(["sbx", "ls", "--quiet"])

    last_error: str | None = None
    for argv in candidates:
        try:
            result = subprocess.run(
                argv,
                text=True,
                capture_output=True,
                check=True,
            )
        except FileNotFoundError:
            return SandboxListResult([], "sbx was not found on PATH")
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            last_error = f"{' '.join(argv)} failed: {detail}"
            continue
        if "--json" in argv:
            all_names = parse_sandbox_json(result.stdout)
            names = parse_sandbox_json(result.stdout, root=root)
            if root is not None and not names and all_names:
                return SandboxListResult(
                    names,
                    f"found sandboxes, but none matched workspace {root.resolve()}",
                    all_names=all_names,
                )
            return SandboxListResult(names, all_names=all_names)
        else:
            names = parse_sandbox_list(result.stdout)
            return SandboxListResult(names, all_names=names)
    return SandboxListResult([], last_error)


def parse_sandbox_json(output: str, root: Path | None = None) -> list[str]:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return []

    if isinstance(payload, dict):
        for key in ("sandboxes", "items", "data"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break

    if not isinstance(payload, list):
        return []

    names: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        workspace = sandbox_workspace(item)
        if root is not None:
            if not workspace or not workspace_matches(workspace, root):
                continue
        name = item.get("name") or item.get("Name") or item.get("sandbox") or item.get("Sandbox")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return list(dict.fromkeys(names))


def workspace_matches(workspace: str, root: Path) -> bool:
    normalized_workspace = workspace.strip()
    if not normalized_workspace:
        return False

    resolved_root = root.resolve()
    if normalized_workspace == str(resolved_root):
        return True

    workspace_path = Path(normalized_workspace).expanduser()
    try:
        resolved_workspace = workspace_path.resolve()
        if resolved_workspace == resolved_root:
            return True
        if resolved_root.is_relative_to(resolved_workspace):
            return True
    except OSError:
        pass

    return normalized_workspace.rstrip("/").split("/")[-1] == resolved_root.name


def sandbox_workspace(item: dict) -> str | None:
    direct_keys = (
        "workspace",
        "workspaces",
        "Workspace",
        "Workspaces",
        "workspace_path",
        "workspacePath",
        "WorkspacePath",
        "workspaceDir",
        "WorkspaceDir",
        "path",
        "Path",
    )
    for key in direct_keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for nested in value:
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
                found = workspace_from_nested(nested)
                if found:
                    return found

    nested = item.get("workspace") or item.get("Workspace")
    if isinstance(nested, dict):
        value = workspace_from_nested(nested)
        if value:
            return value
    return workspace_from_nested(item)


def workspace_from_nested(value: object) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if isinstance(nested, str) and nested.strip() and (
                "workspace" in lowered
                or lowered in {"path", "dir", "hostpath", "host_path", "source"}
            ):
                return nested.strip()
            if "workspace" in lowered:
                found = workspace_from_nested(nested)
                if found:
                    return found
        for nested in value.values():
            found = workspace_from_nested(nested)
            if found:
                return found
    if isinstance(value, list):
        for nested in value:
            found = workspace_from_nested(nested)
            if found:
                return found
    return None


def parse_sandbox_list(output: str) -> list[str]:
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    if not lines:
        return []

    first_tokens = lines[0].split()
    name_index: int | None = None
    for index, token in enumerate(first_tokens):
        if token.upper() in {"NAME", "NAMES", "SANDBOX"}:
            name_index = index
            break

    names: list[str] = []
    for line_index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if line_index == 0 and name_index is not None:
            continue
        if set(line) <= {"-", " "}:
            continue

        parts = line.split()
        if name_index is not None and len(parts) > name_index:
            candidate = parts[name_index].strip()
        elif "\t" in line:
            candidate = line.split("\t", 1)[0].strip()
        else:
            candidate = line.split(None, 1)[0].strip()

        if not candidate or candidate in {"-", "NAME", "ID", "SANDBOX"}:
            continue
        names.append(candidate)
    return list(dict.fromkeys(names))


def scope_args(decision: Decision) -> list[str]:
    if decision.scope is Scope.GLOBAL:
        return ["-g"]
    if decision.scope is Scope.SANDBOX and decision.sandbox_name:
        return [decision.sandbox_name]
    return []


def build_docker_command(decision: Decision) -> DockerCommand | None:
    if decision.mode is Mode.SERVICE_SECRET:
        if not decision.service:
            return None
        return DockerCommand(
            argv=[
                "sbx",
                "secret",
                "set",
                *scope_args(decision),
                decision.service,
            ],
            stdin_secret=decision.value,
        )

    if decision.mode is Mode.CUSTOM_SECRET:
        if not decision.host:
            return None
        return DockerCommand(
            argv=[
                "sbx",
                "secret",
                "set-custom",
                *scope_args(decision),
                "--host",
                decision.host,
                "--env",
                decision.name,
            ],
            stdin_secret=decision.value,
        )

    if decision.mode is Mode.REGISTRY_SECRET:
        if not decision.registry:
            return None
        argv = [
            "sbx",
            "secret",
            "set",
            *scope_args(decision),
            "--registry",
            decision.registry,
            "--password-stdin",
        ]
        if decision.username:
            argv.extend(["--username", decision.username])
        return DockerCommand(argv=argv, stdin_secret=decision.value)

    return None


def run_docker_commands(
    decisions: list[Decision],
    *,
    dry_run: bool,
) -> list[str]:
    messages: list[str] = []
    for decision in decisions:
        command = build_docker_command(decision)
        if command is None:
            continue

        printable = " ".join(command.redacted_argv())
        if dry_run:
            messages.append(f"dry-run: {printable}")
            continue

        try:
            subprocess.run(
                command.argv,
                input=command.stdin_secret,
                text=True,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            messages.append(f"failed: {printable} exited with status {exc.returncode}")
            continue
        messages.append(f"ran: {printable}")
    return messages


def shell_export_line(name: str, value: str) -> str:
    return f"export {name}={shell_single_quote(value)}"


def shell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def apply_persistent_runtime_env(
    sandbox_name: str,
    entries: list[tuple[str, str]],
    *,
    dry_run: bool,
) -> str:
    if dry_run:
        return f"dry-run: update /etc/sandbox-persistent.sh in {sandbox_name} ({len(entries)} env vars)"

    block_lines = [
        "# setup-docker-sandbox managed env: begin",
        *[shell_export_line(name, value) for name, value in entries],
        "# setup-docker-sandbox managed env: end",
    ]
    managed_block = "\n".join(block_lines) + "\n"
    script = f"""set -eu
file=/etc/sandbox-persistent.sh
tmp="$(mktemp)"
touch "$file"
awk '
  /^# setup-docker-sandbox managed env: begin$/ {{ skip=1; next }}
  /^# setup-docker-sandbox managed env: end$/ {{ skip=0; next }}
  !skip {{ print }}
' "$file" > "$tmp"
cat >> "$tmp" <<'EOF_MANAGED_ENV'
{managed_block}EOF_MANAGED_ENV
cat "$tmp" > "$file"
rm -f "$tmp"
"""
    subprocess.run(
        ["sbx", "exec", sandbox_name, "bash", "-s"],
        input=script,
        text=True,
        check=True,
        capture_output=True,
    )
    return f"updated /etc/sandbox-persistent.sh in {sandbox_name} ({len(entries)} env vars)"


def run_sandbox(sandbox_name: str, *, dry_run: bool) -> str:
    if dry_run:
        return f"dry-run: sbx run --name {sandbox_name}"
    subprocess.run(["sbx", "run", "--name", sandbox_name], check=True)
    return f"started sandbox {sandbox_name}"
