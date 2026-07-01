from pathlib import Path
import subprocess

from setup_docker_sandbox.docker import (
    apply_persistent_runtime_env,
    build_docker_command,
    build_policy_command,
    create_sandbox,
    default_sandbox_workspace,
    parse_sandbox_json,
    parse_sandbox_list,
    run_docker_commands,
    run_policy_commands,
    run_sandbox,
    sandbox_workspace,
    workspace_matches,
)
from setup_docker_sandbox.models import Decision, Mode, Scope


def test_service_secret_uses_stdin() -> None:
    command = build_docker_command(
        Decision(
            "OPENAI_API_KEY",
            "service-secret",
            Mode.SERVICE_SECRET,
            scope=Scope.SANDBOX,
            sandbox_name="demo",
            service="openai",
        )
    )

    assert command is not None
    assert command.stdin_secret == "service-secret"
    assert "service-secret" not in command.argv
    assert command.argv == ["sbx", "secret", "set", "demo", "openai"]


def test_sandbox_scoped_secret_without_runtime_sandbox_is_not_runnable() -> None:
    command = build_docker_command(
        Decision(
            "OPENAI_API_KEY",
            "service-secret",
            Mode.SERVICE_SECRET,
            scope=Scope.SANDBOX,
            service="openai",
        )
    )

    assert command is None


def test_custom_secret_omits_value_from_argv() -> None:
    command = build_docker_command(
        Decision(
            "API_KEY",
            "super-secret",
            Mode.CUSTOM_SECRET,
            scope=Scope.SANDBOX,
            sandbox_name="demo",
            host="api.example.com",
        )
    )

    assert command is not None
    assert command.stdin_secret == "super-secret"
    assert "super-secret" not in command.redacted_argv()
    assert "--value" not in command.argv
    assert command.argv == [
        "sbx",
        "secret",
        "set-custom",
        "demo",
        "--host",
        "api.example.com",
        "--env",
        "API_KEY",
    ]


def test_registry_secret_uses_stdin() -> None:
    command = build_docker_command(
        Decision(
            "GHCR_TOKEN",
            "registry-secret",
            Mode.REGISTRY_SECRET,
            scope=Scope.GLOBAL,
            registry="ghcr.io",
            username="octocat",
        )
    )

    assert command is not None
    assert command.stdin_secret == "registry-secret"
    assert "registry-secret" not in command.argv
    assert command.argv == [
        "sbx",
        "secret",
        "set",
        "-g",
        "--registry",
        "ghcr.io",
        "--password-stdin",
        "--username",
        "octocat",
    ]


def test_build_policy_command_allows_network_for_sandbox() -> None:
    command = build_policy_command(
        Decision(
            "DATABASE_URL",
            "secret-url",
            Mode.UNSAFE_RUNTIME,
            scope=Scope.SANDBOX,
            sandbox_name="demo",
            network_url="db.example.com:443",
        )
    )

    assert command is not None
    assert command.stdin_secret is None
    assert command.argv == [
        "sbx",
        "policy",
        "allow",
        "network",
        "db.example.com:443",
        "--sandbox",
        "demo",
    ]


def test_build_policy_command_none_without_network_url() -> None:
    assert (
        build_policy_command(
            Decision(
                "DATABASE_URL",
                "secret-url",
                Mode.UNSAFE_RUNTIME,
                scope=Scope.SANDBOX,
                sandbox_name="demo",
            )
        )
        is None
    )


def test_build_policy_command_none_without_sandbox_name() -> None:
    assert (
        build_policy_command(
            Decision(
                "DATABASE_URL",
                "secret-url",
                Mode.UNSAFE_RUNTIME,
                scope=Scope.SANDBOX,
                network_url="db.example.com",
            )
        )
        is None
    )


def test_run_policy_commands_runs_allow_network(monkeypatch) -> None:
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(subprocess, "run", fake_run)

    messages = run_policy_commands(
        [
            Decision(
                "DATABASE_URL",
                "secret-url",
                Mode.UNSAFE_RUNTIME,
                scope=Scope.SANDBOX,
                sandbox_name="demo",
                network_url="db.example.com",
            )
        ],
        dry_run=False,
    )

    assert messages == ["ran: sbx policy allow network db.example.com --sandbox demo"]
    assert calls[0][0][0] == [
        "sbx",
        "policy",
        "allow",
        "network",
        "db.example.com",
        "--sandbox",
        "demo",
    ]


def test_run_policy_commands_dry_run_does_not_run(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr(subprocess, "run", fake_run)

    messages = run_policy_commands(
        [
            Decision(
                "DATABASE_URL",
                "secret-url",
                Mode.UNSAFE_RUNTIME,
                scope=Scope.SANDBOX,
                sandbox_name="demo",
                network_url="db.example.com",
            )
        ],
        dry_run=True,
    )

    assert messages == ["dry-run: sbx policy allow network db.example.com --sandbox demo"]


def test_run_docker_commands_runs_custom_secret_without_argv_secret(monkeypatch) -> None:
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(subprocess, "run", fake_run)

    messages = run_docker_commands(
        [
            Decision(
                "API_KEY",
                "super-secret",
                Mode.CUSTOM_SECRET,
                sandbox_name="demo",
                host="api.example.com",
            )
        ],
        dry_run=False,
    )

    assert len(messages) == 1
    assert messages[0].startswith("ran: sbx secret set-custom")
    assert calls[0][1]["input"] == "super-secret"
    assert "super-secret" not in calls[0][0][0]


def test_run_docker_commands_dry_run_redacts_secrets() -> None:
    messages = run_docker_commands(
        [
            Decision(
                "API_KEY",
                "super-secret",
                Mode.CUSTOM_SECRET,
                sandbox_name="demo",
                host="api.example.com",
            )
        ],
        dry_run=True,
    )

    assert len(messages) == 1
    assert "super-secret" not in messages[0]
    assert "--value" not in messages[0]


def test_run_docker_commands_failure_redacts_secret_argv(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(subprocess, "run", fake_run)

    messages = run_docker_commands(
        [
            Decision(
                "API_KEY",
                "super-secret",
                Mode.CUSTOM_SECRET,
                sandbox_name="demo",
                host="api.example.com",
            )
        ],
        dry_run=False,
    )

    assert len(messages) == 1
    assert "super-secret" not in messages[0]
    assert "--value" not in messages[0]


def test_parse_sandbox_list_handles_table_output() -> None:
    output = """NAME        STATUS
demo        running
other       stopped
"""

    assert parse_sandbox_list(output) == ["demo", "other"]


def test_parse_sandbox_list_uses_name_column_when_not_first() -> None:
    output = """ID          NAME        STATUS
abc123      demo        running
def456      other       stopped
"""

    assert parse_sandbox_list(output) == ["demo", "other"]


def test_parse_sandbox_list_handles_plain_output_and_dedupes() -> None:
    output = """demo
other
demo
"""

    assert parse_sandbox_list(output) == ["demo", "other"]


def test_parse_sandbox_json_filters_current_workspace(tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    output = f"""
[
  {{"name": "current", "workspace": "{tmp_path}"}},
  {{"name": "other", "workspace": "{other}"}}
]
"""

    assert parse_sandbox_json(output, root=tmp_path) == ["current"]


def test_parse_sandbox_json_matches_workspace_name(tmp_path: Path) -> None:
    output = f"""
[
  {{"name": "current", "workspace": "{tmp_path.name}"}},
  {{"name": "other", "workspace": "other"}}
]
"""

    assert parse_sandbox_json(output, root=tmp_path) == ["current"]


def test_parse_sandbox_json_matches_plural_workspaces(tmp_path: Path) -> None:
    output = f"""
{{
  "sandboxes": [
    {{
      "name": "claude-test-egress",
      "workspaces": [
        "{tmp_path}"
      ]
    }},
    {{
      "name": "clone-sandbox",
      "workspaces": [
        "{tmp_path}"
      ]
    }}
  ]
}}
"""

    assert parse_sandbox_json(output, root=tmp_path) == [
        "claude-test-egress",
        "clone-sandbox",
    ]


def test_parse_sandbox_json_excludes_rows_without_workspace_when_filtering(tmp_path: Path) -> None:
    output = '{"sandboxes": [{"name": "demo"}, {"Name": "other"}]}'

    assert parse_sandbox_json(output, root=tmp_path) == []


def test_parse_sandbox_json_includes_names_without_workspace_when_not_filtering() -> None:
    output = '{"sandboxes": [{"name": "demo"}, {"name": "demo"}, {"Name": "other"}]}'

    assert parse_sandbox_json(output) == ["demo", "other"]


def test_sandbox_workspace_supports_nested_workspace_shape() -> None:
    assert sandbox_workspace({"workspace": {"path": "/repo"}}) == "/repo"
    assert sandbox_workspace({"workspacePath": "/repo"}) == "/repo"


def test_sandbox_workspace_supports_deep_workspace_shape() -> None:
    assert sandbox_workspace({"agent": {"workspace": {"hostPath": "/repo"}}}) == "/repo"


def test_workspace_matches_path_or_basename(tmp_path: Path) -> None:
    child = tmp_path / "app"
    child.mkdir()
    assert workspace_matches(str(tmp_path), tmp_path)
    assert workspace_matches(str(tmp_path), child)
    assert workspace_matches(tmp_path.name, tmp_path)
    assert not workspace_matches("other", tmp_path)


def test_create_sandbox_uses_sbx_create_clone(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(subprocess, "run", fake_run)

    message = create_sandbox(
        name="demo",
        agent="claude",
        workspace=tmp_path,
        clone=True,
        dry_run=False,
    )

    assert message == "created sandbox demo"
    assert calls[0][0][0] == [
        "sbx",
        "create",
        "--clone",
        "--name",
        "demo",
        "claude",
        str(tmp_path),
    ]
    assert "capture_output" not in calls[0][1]


def test_create_sandbox_dry_run_does_not_run_subprocess(monkeypatch, tmp_path: Path) -> None:
    def fake_run(*args, **kwargs):
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert create_sandbox(
        name="demo",
        agent="claude",
        workspace=tmp_path,
        clone=False,
        dry_run=True,
    ) == f"dry-run: sbx create --name demo claude {tmp_path}"


def test_default_sandbox_workspace_uses_git_root_for_clone(monkeypatch, tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    monkeypatch.setattr("setup_docker_sandbox.docker.discover_git_root", lambda start: tmp_path)

    assert default_sandbox_workspace(app, clone=True) == tmp_path
    assert default_sandbox_workspace(app, clone=False) == app


def test_apply_persistent_runtime_env_uses_stdin_not_argv(monkeypatch) -> None:
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(subprocess, "run", fake_run)

    message = apply_persistent_runtime_env(
        "demo",
        [("API_KEY", "secret'with-quote")],
        dry_run=False,
    )

    assert message == "updated /etc/sandbox-persistent.sh in demo (1 env vars)"
    argv = calls[0][0][0]
    script = calls[0][1]["input"]
    assert argv == ["sbx", "exec", "demo", "bash", "-s"]
    assert "secret'with-quote" not in argv
    assert """export API_KEY='secret'"'"'with-quote'""" in script


def test_run_sandbox_passes_agent_args_after_separator(monkeypatch) -> None:
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert run_sandbox("demo", dry_run=False, agent_args=["--continue"]) == "started sandbox demo"
    assert calls[0][0][0] == ["sbx", "run", "--name", "demo", "--", "--continue"]


def test_run_sandbox_dry_run_shows_agent_args() -> None:
    assert (
        run_sandbox("demo", dry_run=True, agent_args=["--continue"])
        == "dry-run: sbx run --name demo -- --continue"
    )
