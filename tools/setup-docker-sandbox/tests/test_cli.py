from setup_docker_sandbox.cli import (
    build_parser,
    collect_allowed_urls,
    decision_for_entry,
    normalize_network_url,
    prompt_sandbox_name,
    prompt_scope,
)
from setup_docker_sandbox.models import Decision, EnvEntry, Mode, Scope
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


def test_start_parser_accepts_agent_args_after_separator() -> None:
    args = build_start_parser().parse_args(["--dry-run", "--", "--continue"])

    assert args.dry_run
    assert args.agent_args == ["--", "--continue"]


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


def test_normalize_network_url_strips_scheme_and_path() -> None:
    assert normalize_network_url("https://api.example.com/v1?x=1") == "api.example.com"
    assert normalize_network_url("api.example.com:443") == "api.example.com:443"
    assert normalize_network_url("  db.example.com  ") == "db.example.com"


def test_normalize_network_url_blank_is_none() -> None:
    assert normalize_network_url("") is None
    assert normalize_network_url("   ") is None


def test_collect_allowed_urls_dedupes_in_order() -> None:
    urls = collect_allowed_urls(
        [
            Decision("A", "x", Mode.UNSAFE_RUNTIME, network_url="a.example.com"),
            Decision("B", "x", Mode.SAFE_ENV),
            Decision("C", "x", Mode.CUSTOM_SECRET, host="a.example.com", network_url="a.example.com"),
            Decision("D", "x", Mode.UNSAFE_RUNTIME, network_url="b.example.com"),
        ]
    )

    assert urls == ["a.example.com", "b.example.com"]


def test_decision_for_entry_custom_secret_records_network_url(monkeypatch) -> None:
    answers = iter(["c", "api.example.com", "api.example.com:443"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    decision = decision_for_entry(EnvEntry("API_KEY", "secret"), Scope.SANDBOX, "demo")

    assert decision.mode is Mode.CUSTOM_SECRET
    assert decision.host == "api.example.com"
    assert decision.network_url == "api.example.com:443"


def test_decision_for_entry_unsafe_secret_reuses_allowed_url(monkeypatch) -> None:
    answers = iter(["u", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    decision = decision_for_entry(
        EnvEntry("DATABASE_URL", "secret-url"),
        Scope.SANDBOX,
        "demo",
        allowed_urls=["db.example.com:5432"],
    )

    assert decision.mode is Mode.UNSAFE_RUNTIME
    assert decision.network_url == "db.example.com:5432"


def test_decision_for_entry_unsafe_secret_can_skip_network_url(monkeypatch) -> None:
    answers = iter(["u", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    decision = decision_for_entry(EnvEntry("SIGNING_KEY", "secret"), Scope.SANDBOX, "demo")

    assert decision.mode is Mode.UNSAFE_RUNTIME
    assert decision.network_url is None
