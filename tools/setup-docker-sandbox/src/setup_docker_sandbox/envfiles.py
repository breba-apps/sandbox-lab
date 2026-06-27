from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values

from setup_docker_sandbox.models import EnvEntry


def load_env_file(path: Path) -> list[EnvEntry]:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist")

    values = dotenv_values(path)
    entries: list[EnvEntry] = []
    for name, value in values.items():
        if value is None:
            value = ""
        entries.append(EnvEntry(name=name, value=value))
    return entries


def quote_env_value(value: str) -> str:
    if value == "":
        return '""'
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./:@%+-")
    if all(char in safe_chars for char in value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def write_env_file(path: Path, entries: list[EnvEntry]) -> None:
    lines = [f"{entry.name}={quote_env_value(entry.value)}" for entry in entries]
    text = "\n".join(lines)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")
