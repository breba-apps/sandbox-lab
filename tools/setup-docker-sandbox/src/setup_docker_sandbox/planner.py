from __future__ import annotations

import fnmatch
from pathlib import Path

from setup_docker_sandbox.envfiles import load_env_file
from setup_docker_sandbox.envfiles import write_env_file
from setup_docker_sandbox.manifest import load_manifest, write_manifest
from setup_docker_sandbox.models import Decision, EnvEntry, Mode

GENERATED_LOCAL_FILES = ("proxy-secrets.env", "runtime.env", "sandbox-secrets.toml")


def proxy_secret_entries(decisions: list[Decision]) -> list[EnvEntry]:
    entries: list[EnvEntry] = []
    for decision in decisions:
        if decision.mode in {
            Mode.SERVICE_SECRET,
            Mode.CUSTOM_SECRET,
            Mode.REGISTRY_SECRET,
        }:
            entries.append(EnvEntry(name=decision.name, value=decision.value))
    return entries


def runtime_entries(decisions: list[Decision]) -> list[EnvEntry]:
    entries: list[EnvEntry] = []
    for decision in decisions:
        if decision.mode in {Mode.SAFE_ENV, Mode.UNSAFE_RUNTIME}:
            entries.append(EnvEntry(name=decision.name, value=decision.value))
    return entries


def write_outputs(
    directory: Path,
    decisions: list[Decision],
    *,
    dry_run: bool,
) -> list[str]:
    proxy_entries = proxy_secret_entries(decisions)
    runtime_env_entries = runtime_entries(decisions)
    messages = [
        f"write {directory / 'proxy-secrets.env'} ({len(proxy_entries)} entries)",
        f"write {directory / 'runtime.env'} ({len(runtime_env_entries)} entries)",
        f"write {directory / 'sandbox-secrets.toml'}",
    ]
    if dry_run:
        return [f"dry-run: {message}" for message in messages]

    write_env_file(directory / "proxy-secrets.env", proxy_entries)
    write_env_file(directory / "runtime.env", runtime_env_entries)
    write_manifest(directory / "sandbox-secrets.toml", decisions)
    return messages


def load_existing_decisions(directory: Path) -> dict[str, Decision]:
    manifest_decisions = load_manifest(directory / "sandbox-secrets.toml")
    values: dict[str, str] = {}

    for env_name in ("proxy-secrets.env", "runtime.env", "safe.env", "unsafe.env"):
        path = directory / env_name
        if not path.exists():
            continue
        for entry in load_env_file(path):
            values[entry.name] = entry.value

    decisions: dict[str, Decision] = {}
    for name, decision in manifest_decisions.items():
        if name not in values:
            continue
        decisions[name] = Decision(
            name=decision.name,
            value=values[name],
            mode=decision.mode,
            scope=decision.scope,
            sandbox_name=decision.sandbox_name,
            service=decision.service,
            host=decision.host,
            registry=decision.registry,
            username=decision.username,
            network_url=decision.network_url,
        )
    return decisions


def merge_existing_decision(
    entry: EnvEntry,
    existing: Decision,
    *,
    sandbox_name: str | None,
) -> Decision:
    return Decision(
        name=entry.name,
        value=entry.value,
        mode=existing.mode,
        scope=existing.scope,
        sandbox_name=sandbox_name if existing.scope.value == "sandbox" else None,
        service=existing.service,
        host=existing.host,
        registry=existing.registry,
        username=existing.username,
        network_url=existing.network_url,
    )


def gitignore_covers_generated_env(root: Path) -> bool:
    return not missing_generated_gitignore_entries(root)


def gitignore_pattern_matches(filename: str, pattern: str) -> bool:
    return pattern == filename or fnmatch.fnmatchcase(filename, pattern)


def missing_generated_gitignore_entries(root: Path) -> list[str]:
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return list(GENERATED_LOCAL_FILES)
    lines = [
        line.strip()
        for line in gitignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return [
        filename
        for filename in GENERATED_LOCAL_FILES
        if not any(gitignore_pattern_matches(filename, line) for line in lines)
    ]


def append_generated_env_to_gitignore(root: Path, *, dry_run: bool) -> str:
    gitignore = root / ".gitignore"
    missing = missing_generated_gitignore_entries(root)
    if not missing:
        return f"{gitignore} already covers generated sandbox files"

    rendered = ", ".join(missing)
    if dry_run:
        return f"dry-run: append {rendered} to {gitignore}"

    existing = ""
    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8")

    prefix = "" if not existing or existing.endswith("\n") else "\n"
    additions = "\n".join(missing)
    gitignore.write_text(f"{existing}{prefix}{additions}\n", encoding="utf-8")
    return f"append {rendered} to {gitignore}"
