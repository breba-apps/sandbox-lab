from pathlib import Path

from setup_docker_sandbox.manifest import write_manifest
from setup_docker_sandbox.models import Decision, Mode, Scope
from setup_docker_sandbox.planner import (
    append_unsafe_env_to_gitignore,
    gitignore_covers_unsafe_env,
    split_entries,
    write_outputs,
)


def test_split_entries_sends_safe_and_sensitive_values_to_expected_files() -> None:
    decisions = [
        Decision("PORT", "8000", Mode.SAFE_ENV),
        Decision("API_KEY", "secret", Mode.CUSTOM_SECRET, host="api.example.com"),
        Decision("DATABASE_URL", "secret-url", Mode.UNSAFE_RUNTIME),
        Decision("IGNORED", "x", Mode.SKIP),
    ]

    safe, unsafe = split_entries(decisions)

    assert [entry.name for entry in safe] == ["PORT"]
    assert [entry.name for entry in unsafe] == ["API_KEY", "DATABASE_URL"]


def test_write_outputs_supports_dry_run_without_writing(tmp_path: Path) -> None:
    messages = write_outputs(
        tmp_path,
        [Decision("PORT", "8000", Mode.SAFE_ENV)],
        dry_run=True,
    )

    assert all(message.startswith("dry-run:") for message in messages)
    assert not (tmp_path / "safe.env").exists()
    assert not (tmp_path / "unsafe.env").exists()
    assert not (tmp_path / "sandbox-secrets.toml").exists()


def test_write_outputs_writes_repeatability_files(tmp_path: Path) -> None:
    decisions = [
        Decision("PORT", "8000", Mode.SAFE_ENV),
        Decision(
            "API_KEY",
            "actual-api-token",
            Mode.CUSTOM_SECRET,
            scope=Scope.SANDBOX,
            sandbox_name="demo",
            host="api.example.com",
        ),
    ]

    write_outputs(tmp_path, decisions, dry_run=False)

    assert (tmp_path / "safe.env").read_text(encoding="utf-8") == "PORT=8000\n"
    assert (tmp_path / "unsafe.env").read_text(encoding="utf-8") == "API_KEY=actual-api-token\n"
    manifest = (tmp_path / "sandbox-secrets.toml").read_text(encoding="utf-8")
    assert 'name = "API_KEY"' in manifest
    assert 'host = "api.example.com"' in manifest
    assert "actual-api-token" not in manifest


def test_write_manifest_never_writes_secret_values(tmp_path: Path) -> None:
    manifest = tmp_path / "sandbox-secrets.toml"

    write_manifest(
        manifest,
        [
            Decision(
                "TOKEN",
                "super-secret-value",
                Mode.SERVICE_SECRET,
                service="openai",
            )
        ],
    )

    text = manifest.read_text(encoding="utf-8")
    assert "TOKEN" in text
    assert "super-secret-value" not in text


def test_gitignore_covers_unsafe_env_for_env_globs(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(".env\n.env.*\n", encoding="utf-8")

    assert gitignore_covers_unsafe_env(tmp_path)


def test_append_unsafe_env_to_gitignore(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("# secrets\n", encoding="utf-8")

    message = append_unsafe_env_to_gitignore(tmp_path, dry_run=False)

    assert "append unsafe.env" in message
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "# secrets\nunsafe.env\n"


def test_append_unsafe_env_to_gitignore_dry_run(tmp_path: Path) -> None:
    message = append_unsafe_env_to_gitignore(tmp_path, dry_run=True)

    assert message.startswith("dry-run:")
    assert not (tmp_path / ".gitignore").exists()
