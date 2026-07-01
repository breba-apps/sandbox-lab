from pathlib import Path

from setup_docker_sandbox.manifest import load_manifest, write_manifest
from setup_docker_sandbox.models import Decision, EnvEntry, Mode, Scope
from setup_docker_sandbox.planner import (
    append_generated_env_to_gitignore,
    gitignore_covers_generated_env,
    load_existing_decisions,
    merge_existing_decision,
    missing_generated_gitignore_entries,
    proxy_secret_entries,
    runtime_entries,
    write_outputs,
)


def test_runtime_entries_excludes_proxy_managed_secrets() -> None:
    entries = runtime_entries(
        [
            Decision("PORT", "8000", Mode.SAFE_ENV),
            Decision("OPENAI_API_KEY", "secret", Mode.SERVICE_SECRET, service="openai"),
            Decision("API_KEY", "secret", Mode.CUSTOM_SECRET, host="api.example.com"),
            Decision("DATABASE_URL", "secret-url", Mode.UNSAFE_RUNTIME),
        ]
    )

    assert [entry.name for entry in entries] == ["PORT", "DATABASE_URL"]


def test_proxy_secret_entries_excludes_runtime_values() -> None:
    entries = proxy_secret_entries(
        [
            Decision("PORT", "8000", Mode.SAFE_ENV),
            Decision("OPENAI_API_KEY", "secret", Mode.SERVICE_SECRET, service="openai"),
            Decision("API_KEY", "secret", Mode.CUSTOM_SECRET, host="api.example.com"),
            Decision("DATABASE_URL", "secret-url", Mode.UNSAFE_RUNTIME),
            Decision("GHCR_TOKEN", "secret", Mode.REGISTRY_SECRET, registry="ghcr.io"),
        ]
    )

    assert [entry.name for entry in entries] == ["OPENAI_API_KEY", "API_KEY", "GHCR_TOKEN"]


def test_write_outputs_supports_dry_run_without_writing(tmp_path: Path) -> None:
    messages = write_outputs(
        tmp_path,
        [Decision("PORT", "8000", Mode.SAFE_ENV)],
        dry_run=True,
    )

    assert all(message.startswith("dry-run:") for message in messages)
    assert not (tmp_path / "proxy-secrets.env").exists()
    assert not (tmp_path / "runtime.env").exists()
    assert not (tmp_path / "sandbox-secrets.toml").exists()


def test_write_outputs_writes_repeatability_files(tmp_path: Path) -> None:
    decisions = [
        Decision("PORT", "8000", Mode.SAFE_ENV),
        Decision("DATABASE_URL", "secret-url", Mode.UNSAFE_RUNTIME),
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

    assert (
        tmp_path / "proxy-secrets.env"
    ).read_text(encoding="utf-8") == "API_KEY=actual-api-token\n"
    assert (tmp_path / "runtime.env").read_text(encoding="utf-8") == "PORT=8000\nDATABASE_URL=secret-url\n"
    manifest = (tmp_path / "sandbox-secrets.toml").read_text(encoding="utf-8")
    assert 'name = "API_KEY"' in manifest
    assert 'host = "api.example.com"' in manifest
    assert "sandbox_name" not in manifest
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


def test_load_manifest_reads_non_secret_decisions(tmp_path: Path) -> None:
    manifest = tmp_path / "sandbox-secrets.toml"
    write_manifest(
        manifest,
        [
            Decision(
                "OPENAI_API_KEY",
                "secret",
                Mode.SERVICE_SECRET,
                scope=Scope.SANDBOX,
                sandbox_name="old-sandbox",
                service="openai",
            )
        ],
    )

    decisions = load_manifest(manifest)

    assert decisions["OPENAI_API_KEY"].value == ""
    assert decisions["OPENAI_API_KEY"].mode is Mode.SERVICE_SECRET
    assert decisions["OPENAI_API_KEY"].service == "openai"
    assert decisions["OPENAI_API_KEY"].sandbox_name is None


def test_manifest_round_trips_network_url(tmp_path: Path) -> None:
    manifest = tmp_path / "sandbox-secrets.toml"
    write_manifest(
        manifest,
        [
            Decision(
                "DATABASE_URL",
                "secret-url",
                Mode.UNSAFE_RUNTIME,
                scope=Scope.SANDBOX,
                network_url="db.example.com:443",
            )
        ],
    )

    decisions = load_manifest(manifest)

    assert decisions["DATABASE_URL"].network_url == "db.example.com:443"


def test_load_existing_decisions_combines_manifest_and_env_values(tmp_path: Path) -> None:
    write_outputs(
        tmp_path,
        [
            Decision("PORT", "8000", Mode.SAFE_ENV),
            Decision("TOKEN", "secret", Mode.SERVICE_SECRET, service="openai"),
        ],
        dry_run=False,
    )

    decisions = load_existing_decisions(tmp_path)

    assert decisions["PORT"].value == "8000"
    assert decisions["TOKEN"].value == "secret"
    assert decisions["TOKEN"].mode is Mode.SERVICE_SECRET


def test_load_existing_decisions_reads_legacy_safe_and_unsafe_env(tmp_path: Path) -> None:
    write_manifest(
        tmp_path / "sandbox-secrets.toml",
        [
            Decision("PORT", "8000", Mode.SAFE_ENV),
            Decision("TOKEN", "secret", Mode.SERVICE_SECRET, service="openai"),
        ],
    )
    (tmp_path / "safe.env").write_text("PORT=8000\n", encoding="utf-8")
    (tmp_path / "unsafe.env").write_text("TOKEN=secret\n", encoding="utf-8")

    decisions = load_existing_decisions(tmp_path)

    assert decisions["PORT"].value == "8000"
    assert decisions["TOKEN"].value == "secret"


def test_load_existing_decisions_ignores_manifest_entries_without_values(tmp_path: Path) -> None:
    write_manifest(
        tmp_path / "sandbox-secrets.toml",
        [Decision("TOKEN", "secret", Mode.SERVICE_SECRET, service="openai")],
    )

    assert load_existing_decisions(tmp_path) == {}


def test_merge_existing_decision_updates_value_and_current_sandbox() -> None:
    existing = Decision(
        "TOKEN",
        "old",
        Mode.SERVICE_SECRET,
        scope=Scope.SANDBOX,
        sandbox_name="old-sandbox",
        service="openai",
    )

    decision = merge_existing_decision(
        EnvEntry("TOKEN", "new"),
        existing,
        sandbox_name="current-sandbox",
    )

    assert decision.value == "new"
    assert decision.service == "openai"
    assert decision.sandbox_name == "current-sandbox"


def test_gitignore_covers_generated_env_for_env_globs(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.env\nsandbox-secrets.toml\n", encoding="utf-8")

    assert gitignore_covers_generated_env(tmp_path)


def test_gitignore_reports_only_missing_generated_files(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.env\n", encoding="utf-8")

    assert missing_generated_gitignore_entries(tmp_path) == ["sandbox-secrets.toml"]


def test_append_generated_env_to_gitignore(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("# secrets\nproxy-secrets.env\n", encoding="utf-8")

    message = append_generated_env_to_gitignore(tmp_path, dry_run=False)

    assert "append runtime.env, sandbox-secrets.toml" in message
    assert (
        tmp_path / ".gitignore"
    ).read_text(encoding="utf-8") == "# secrets\nproxy-secrets.env\nruntime.env\nsandbox-secrets.toml\n"


def test_append_generated_env_to_gitignore_dry_run(tmp_path: Path) -> None:
    message = append_generated_env_to_gitignore(tmp_path, dry_run=True)

    assert message.startswith("dry-run:")
    assert not (tmp_path / ".gitignore").exists()
