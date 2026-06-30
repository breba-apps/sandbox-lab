from setup_docker_sandbox.cli import build_parser, prompt_sandbox_name, prompt_scope
from setup_docker_sandbox.models import Scope
from setup_docker_sandbox.start import build_parser as build_start_parser


def test_cli_parser_defaults_to_dot_env() -> None:
    args = build_parser().parse_args([])

    assert args.env_file == ".env"
    assert not args.dry_run


def test_cli_parser_accepts_installable_tool_options() -> None:
    args = build_parser().parse_args(
        [
            "--env-file",
            ".env.local",
            "--dry-run",
        ]
    )

    assert args.env_file == ".env.local"
    assert args.dry_run


def test_start_parser_accepts_start_options() -> None:
    args = build_start_parser().parse_args(["--env-file", ".env.local", "--dry-run"])

    assert args.env_file == ".env.local"
    assert args.dry_run


def test_prompt_sandbox_name_selects_existing_sandbox(monkeypatch) -> None:
    from setup_docker_sandbox.docker import SandboxListResult

    monkeypatch.setattr(
        "setup_docker_sandbox.cli.list_sandboxes_result",
        lambda root=None: SandboxListResult(["one", "two"]),
    )
    monkeypatch.setattr("builtins.input", lambda _: "2")

    assert prompt_sandbox_name() == "two"


def test_prompt_sandbox_name_returns_none_without_workspace_sandboxes(monkeypatch) -> None:
    from setup_docker_sandbox.docker import SandboxListResult

    monkeypatch.setattr(
        "setup_docker_sandbox.cli.list_sandboxes_result",
        lambda root=None: SandboxListResult([]),
    )

    assert prompt_sandbox_name() is None


def test_prompt_scope_sandbox_does_not_select_concrete_sandbox(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "s")

    assert prompt_scope() == (Scope.SANDBOX, None)
