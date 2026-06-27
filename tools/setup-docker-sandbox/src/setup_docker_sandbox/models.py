from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Scope(StrEnum):
    SANDBOX = "sandbox"
    GLOBAL = "global"
    HOST = "host"


class Mode(StrEnum):
    SAFE_ENV = "safe_env"
    SERVICE_SECRET = "service_secret"
    CUSTOM_SECRET = "custom_secret"
    UNSAFE_RUNTIME = "unsafe_runtime"
    REGISTRY_SECRET = "registry_secret"
    SKIP = "skip"


@dataclass(frozen=True)
class EnvEntry:
    name: str
    value: str


@dataclass(frozen=True)
class Decision:
    name: str
    value: str
    mode: Mode
    scope: Scope = Scope.SANDBOX
    sandbox_name: str | None = None
    service: str | None = None
    host: str | None = None
    registry: str | None = None
    username: str | None = None


@dataclass(frozen=True)
class DockerCommand:
    argv: list[str]
    stdin_secret: str | None = None

    def redacted_argv(self) -> list[str]:
        return self.argv
