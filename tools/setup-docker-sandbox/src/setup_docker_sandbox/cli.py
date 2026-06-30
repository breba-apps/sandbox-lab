from __future__ import annotations

import argparse
import sys
from pathlib import Path

from setup_docker_sandbox.docker import (
    BUILT_IN_SERVICES,
    list_sandboxes_result,
    run_docker_commands,
    sbx_available,
)
from setup_docker_sandbox.envfiles import load_env_file
from setup_docker_sandbox.models import Decision, EnvEntry, Mode, Scope
from setup_docker_sandbox.planner import (
    append_generated_env_to_gitignore,
    gitignore_covers_generated_env,
    load_existing_decisions,
    merge_existing_decision,
    write_outputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="setup-docker-sandbox",
        description="Configure Docker Sandbox secrets from a generic .env file.",
    )
    parser.add_argument("--env-file", default=".env", help="Env file to read. Default: .env")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without writing or running sbx.")
    return parser


def prompt(message: str, *, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{message}{suffix}: ").strip()
    if value:
        return value
    if default is not None:
        return default
    return ""


def prompt_choice(message: str, choices: list[tuple[str, str]], *, default: str) -> str:
    print(message)
    for key, label in choices:
        print(f"  {key}) {label}")
    allowed = {key for key, _ in choices}
    while True:
        answer = prompt("Choose", default=default).lower()
        if answer in allowed:
            return answer
        print(f"Please choose one of: {', '.join(sorted(allowed))}")


def prompt_sandbox_name() -> str | None:
    sandbox_result = list_sandboxes_result(Path.cwd())
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
        print("Create or start a sandbox for this workspace, then rerun setup-docker-sandbox.")
        return None

    print("Docker Sandboxes for this workspace")
    for index, name in enumerate(sandboxes, start=1):
        print(f"  {index}) {name}")

    while True:
        answer = prompt("Choose sandbox to use", default="1").lower()
        if answer.isdigit():
            index = int(answer)
            if 1 <= index <= len(sandboxes):
                return sandboxes[index - 1]
        print(f"Please choose 1-{len(sandboxes)}.")


def prompt_scope() -> tuple[Scope, str | None]:
    answer = prompt_choice(
        "Default Docker Sandbox scope",
        [
            ("s", "sandbox-scoped, recommended"),
            ("g", "global, applies to new sandboxes"),
            ("h", "host-only where Docker supports it"),
        ],
        default="s",
    )
    if answer == "g":
        return Scope.GLOBAL, None
    if answer == "h":
        return Scope.HOST, None
    return Scope.SANDBOX, None


def decision_for_entry(entry: EnvEntry, default_scope: Scope, sandbox_name: str | None) -> Decision:
    print(f"\nVariable: {entry.name}")
    answer = prompt_choice(
        "How should this value be handled?",
        [
            ("s", "safe runtime env var"),
            ("b", "built-in service secret"),
            ("c", "custom egress secret"),
            ("u", "unsafe runtime secret visible to the app/sandbox"),
            ("r", "registry credential"),
            ("k", "skip"),
        ],
        default="u",
    )

    if answer == "s":
        return Decision(entry.name, entry.value, Mode.SAFE_ENV)
    if answer == "b":
        service = prompt_built_in_service()
        return Decision(
            entry.name,
            entry.value,
            Mode.SERVICE_SECRET,
            scope=default_scope,
            sandbox_name=sandbox_name,
            service=service,
        )
    if answer == "c":
        host = prompt("Destination host for custom proxy injection, e.g. api.example.com")
        return Decision(
            entry.name,
            entry.value,
            Mode.CUSTOM_SECRET,
            scope=default_scope,
            sandbox_name=sandbox_name,
            host=host,
        )
    if answer == "r":
        registry = prompt("Registry host, e.g. ghcr.io")
        username = prompt("Registry username, blank if not needed", default="")
        return Decision(
            entry.name,
            entry.value,
            Mode.REGISTRY_SECRET,
            scope=default_scope,
            sandbox_name=sandbox_name,
            registry=registry,
            username=username or None,
        )
    if answer == "k":
        return Decision(entry.name, entry.value, Mode.SKIP)
    return Decision(
        entry.name,
        entry.value,
        Mode.UNSAFE_RUNTIME,
        scope=default_scope,
        sandbox_name=sandbox_name,
    )


def prompt_built_in_service() -> str:
    choices = [(str(index), service) for index, service in enumerate(BUILT_IN_SERVICES, start=1)]
    print("Built-in Docker Sandbox services")
    for key, label in choices:
        print(f"  {key}) {label}")
    allowed = {key for key, _ in choices}
    while True:
        answer = prompt("Choose service number or name").lower()
        if answer in BUILT_IN_SERVICES:
            return answer
        if answer in allowed:
            return BUILT_IN_SERVICES[int(answer) - 1]
        print("Choose one of the listed service names or numbers.")


def print_decision(decision: Decision) -> None:
    if decision.mode is Mode.SKIP:
        print(f"{decision.name}: skipped")
    elif decision.mode is Mode.SERVICE_SECRET:
        print(f"{decision.name}: built-in service secret for {decision.service}, scope={decision.scope.value}")
    elif decision.mode is Mode.CUSTOM_SECRET:
        print(f"{decision.name}: custom egress secret for {decision.host}, scope={decision.scope.value}")
    elif decision.mode is Mode.REGISTRY_SECRET:
        print(f"{decision.name}: registry credential for {decision.registry}, scope={decision.scope.value}")
    elif decision.mode is Mode.SAFE_ENV:
        print(f"{decision.name}: runtime.env safe value")
    else:
        print(f"{decision.name}: runtime.env secret value")


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

    if not entries:
        print(f"{env_path} contains no variables", file=sys.stderr)
        return 2

    default_scope, sandbox_name = prompt_scope()
    existing_decisions = load_existing_decisions(root)
    if existing_decisions:
        print(f"Reusing saved decisions for {len(existing_decisions)} variable(s).")

    decisions = []
    for entry in entries:
        existing = existing_decisions.get(entry.name)
        if existing is not None:
            decision = merge_existing_decision(entry, existing, sandbox_name=sandbox_name)
        else:
            decision = decision_for_entry(entry, default_scope, sandbox_name)
        decisions.append(decision)
        print_decision(decision)

    if not gitignore_covers_generated_env(root):
        print("Warning: proxy-secrets.env/runtime.env do not appear to be covered by .gitignore.")
        if prompt("Append proxy-secrets.env and runtime.env to .gitignore?", default="y").lower() in {"y", "yes"}:
            print(append_generated_env_to_gitignore(root, dry_run=args.dry_run))

    for message in write_outputs(root, decisions, dry_run=args.dry_run):
        print(message)

    if not sbx_available():
        print("Warning: sbx was not found on PATH; Docker Sandbox commands were not run.")
        return 0

    if any(decision.scope is Scope.SANDBOX for decision in decisions):
        print("Sandbox-scoped Docker commands are applied by start-docker-sandbox.")

    for message in run_docker_commands(
        decisions,
        dry_run=args.dry_run,
    ):
        print(message)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
