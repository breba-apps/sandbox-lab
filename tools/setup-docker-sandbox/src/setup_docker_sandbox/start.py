from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from setup_docker_sandbox.cli import (
    decision_for_entry,
    print_decision,
    prompt,
)
from setup_docker_sandbox.docker import (
    create_sandbox,
    default_sandbox_workspace,
    discover_git_root,
    apply_persistent_runtime_env,
    list_sandboxes_result,
    run_docker_commands,
    run_sandbox,
    sbx_available,
)
from setup_docker_sandbox.envfiles import load_env_file
from setup_docker_sandbox.models import Decision, EnvEntry, Scope
from setup_docker_sandbox.planner import (
    load_existing_decisions,
    merge_existing_decision,
    runtime_entries,
    write_outputs,
)


@dataclass(frozen=True)
class Divergence:
    missing_decisions: list[str]
    stale_values: list[str]
    removed_from_env: list[str]

    def has_changes(self) -> bool:
        return bool(self.missing_decisions or self.stale_values or self.removed_from_env)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="start-docker-sandbox",
        description="Refresh sandbox runtime env and start the workspace Docker Sandbox.",
    )
    parser.add_argument("--env-file", default=".env", help="Env file to compare. Default: .env")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without writing or running sbx.")
    return parser


def detect_divergence(entries: list[EnvEntry], decisions: dict[str, Decision]) -> Divergence:
    env_values = {entry.name: entry.value for entry in entries}
    missing = [name for name in env_values if name not in decisions]
    stale = [
        name
        for name, value in env_values.items()
        if name in decisions and decisions[name].value != value
    ]
    removed = [name for name in decisions if name not in env_values]
    return Divergence(missing, stale, removed)


def print_divergence(divergence: Divergence) -> None:
    print("Derived sandbox env files differ from .env.")
    if divergence.missing_decisions:
        print("New .env variables:")
        for name in divergence.missing_decisions:
            print(f"  - {name}")
    if divergence.stale_values:
        print("Changed .env values:")
        for name in divergence.stale_values:
            print(f"  - {name}")
    if divergence.removed_from_env:
        print("No longer present in .env:")
        for name in divergence.removed_from_env:
            print(f"  - {name}")


def reconcile_decisions(
    entries: list[EnvEntry],
    existing_decisions: dict[str, Decision],
    *,
    scope: Scope,
    sandbox_name: str | None,
) -> list[Decision]:
    decisions: list[Decision] = []
    for entry in entries:
        existing = existing_decisions.get(entry.name)
        if existing is not None:
            decision = merge_existing_decision(entry, existing, sandbox_name=sandbox_name)
        else:
            decision = decision_for_entry(entry, scope, sandbox_name)
        decisions.append(decision)
        print_decision(decision)
    return decisions


def prompt_new_sandbox_name(*, root: Path, dry_run: bool) -> str | None:
    git_root = discover_git_root(root)
    default_name = git_root.name if git_root is not None else root.name
    name = prompt("New sandbox name", default=default_name)
    if not name:
        print("Sandbox name is required.")
        return None

    agent = prompt("Agent", default="claude")
    if not agent:
        print("Agent is required.")
        return None

    clone = False
    if git_root is not None:
        answer = prompt("Use clone mode from Git root", default="y").lower()
        clone = answer in {"y", "yes"}
    else:
        print("No Git repository found; creating a mounted-workspace sandbox.")

    workspace = default_sandbox_workspace(root, clone=clone)
    try:
        print(
            create_sandbox(
                name=name,
                agent=agent,
                workspace=workspace,
                clone=clone,
                dry_run=dry_run,
            )
        )
    except Exception as exc:
        print(f"Failed to create sandbox {name}: {exc}")
        return None
    return name


def prompt_sandbox_name_or_create(*, root: Path, dry_run: bool) -> str | None:
    sandbox_result = list_sandboxes_result(root)
    sandboxes = sandbox_result.names
    if not sandboxes:
        if sandbox_result.error:
            print(f"Could not list existing Docker Sandboxes: {sandbox_result.error}")
            if sandbox_result.all_names:
                print("Sandboxes found outside this workspace:")
                for name in sandbox_result.all_names:
                    print(f"  - {name}")
        else:
            print("No Docker Sandboxes found for this workspace.")
        return prompt_new_sandbox_name(root=root, dry_run=dry_run)

    create_index = len(sandboxes) + 1
    print("Docker Sandboxes for this workspace")
    for index, name in enumerate(sandboxes, start=1):
        print(f"  {index}) {name}")
    print(f"  {create_index}) Create new sandbox")

    while True:
        answer = prompt("Choose sandbox to use", default="1").lower()
        if answer.isdigit():
            index = int(answer)
            if 1 <= index <= len(sandboxes):
                return sandboxes[index - 1]
            if index == create_index:
                return prompt_new_sandbox_name(root=root, dry_run=dry_run)
        if answer in {"c", "create", "new"}:
            return prompt_new_sandbox_name(root=root, dry_run=dry_run)
        print(f"Please choose 1-{create_index}.")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path.cwd()
    env_path = Path(args.env_file)
    if not env_path.is_absolute():
        env_path = root / env_path

    try:
        entries = load_env_file(env_path)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    sandbox_name = prompt_sandbox_name_or_create(root=root, dry_run=args.dry_run)
    if sandbox_name is None:
        return 2

    existing_decisions = load_existing_decisions(root)
    divergence = detect_divergence(entries, existing_decisions)
    if divergence.has_changes():
        print_divergence(divergence)
        answer = prompt("Update derived env files before starting?", default="y").lower()
        if answer not in {"y", "yes"}:
            print("Canceled. Run setup-docker-sandbox to reconcile before starting.")
            return 1
        decisions = reconcile_decisions(
            entries,
            existing_decisions,
            scope=Scope.SANDBOX,
            sandbox_name=sandbox_name,
        )
        for message in write_outputs(root, decisions, dry_run=args.dry_run):
            print(message)
    else:
        decisions = [
            merge_existing_decision(entry, existing_decisions[entry.name], sandbox_name=sandbox_name)
            for entry in entries
            if entry.name in existing_decisions
        ]
        print("Derived env files are up to date.")

    if not sbx_available():
        print("sbx was not found on PATH.", file=sys.stderr)
        return 2

    for message in run_docker_commands(decisions, dry_run=args.dry_run):
        print(message)

    runtime = runtime_entries(decisions)
    print(
        apply_persistent_runtime_env(
            sandbox_name,
            [(entry.name, entry.value) for entry in runtime],
            dry_run=args.dry_run,
        )
    )
    print(run_sandbox(sandbox_name, dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
