from __future__ import annotations

from pathlib import Path

from setup_docker_sandbox.envfiles import write_env_file
from setup_docker_sandbox.manifest import write_manifest
from setup_docker_sandbox.models import Decision, EnvEntry, Mode


def split_entries(decisions: list[Decision]) -> tuple[list[EnvEntry], list[EnvEntry]]:
    safe: list[EnvEntry] = []
    unsafe: list[EnvEntry] = []
    for decision in decisions:
        entry = EnvEntry(name=decision.name, value=decision.value)
        if decision.mode is Mode.SAFE_ENV:
            safe.append(entry)
        elif decision.mode in {
            Mode.SERVICE_SECRET,
            Mode.CUSTOM_SECRET,
            Mode.UNSAFE_RUNTIME,
            Mode.REGISTRY_SECRET,
        }:
            unsafe.append(entry)
    return safe, unsafe


def write_outputs(
    directory: Path,
    decisions: list[Decision],
    *,
    dry_run: bool,
) -> list[str]:
    safe_entries, unsafe_entries = split_entries(decisions)
    messages = [
        f"write {directory / 'safe.env'} ({len(safe_entries)} entries)",
        f"write {directory / 'unsafe.env'} ({len(unsafe_entries)} entries)",
        f"write {directory / 'sandbox-secrets.toml'}",
    ]
    if dry_run:
        return [f"dry-run: {message}" for message in messages]

    write_env_file(directory / "safe.env", safe_entries)
    write_env_file(directory / "unsafe.env", unsafe_entries)
    write_manifest(directory / "sandbox-secrets.toml", decisions)
    return messages


def gitignore_covers_unsafe_env(root: Path) -> bool:
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return False
    lines = [
        line.strip()
        for line in gitignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return any(line in {"unsafe.env", "*.env", ".env.*", "*.local"} for line in lines)


def append_unsafe_env_to_gitignore(root: Path, *, dry_run: bool) -> str:
    gitignore = root / ".gitignore"
    if dry_run:
        return f"dry-run: append unsafe.env to {gitignore}"

    existing = ""
    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8")

    prefix = "" if not existing or existing.endswith("\n") else "\n"
    gitignore.write_text(f"{existing}{prefix}unsafe.env\n", encoding="utf-8")
    return f"append unsafe.env to {gitignore}"
