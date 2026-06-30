import subprocess

from setup_docker_sandbox.models import Decision, EnvEntry, Mode
from setup_docker_sandbox.start import detect_divergence, prompt_new_sandbox_name


def test_detect_divergence_finds_new_changed_and_removed_values() -> None:
    divergence = detect_divergence(
        [
            EnvEntry("PORT", "9000"),
            EnvEntry("NEW_KEY", "new"),
        ],
        {
            "PORT": Decision("PORT", "8000", Mode.SAFE_ENV),
            "OLD_KEY": Decision("OLD_KEY", "old", Mode.SAFE_ENV),
        },
    )

    assert divergence.missing_decisions == ["NEW_KEY"]
    assert divergence.stale_values == ["PORT"]
    assert divergence.removed_from_env == ["OLD_KEY"]


def test_detect_divergence_empty_when_values_match() -> None:
    divergence = detect_divergence(
        [EnvEntry("PORT", "8000")],
        {"PORT": Decision("PORT", "8000", Mode.SAFE_ENV)},
    )

    assert not divergence.has_changes()


def test_prompt_new_sandbox_name_creates_clone_sandbox(monkeypatch, tmp_path) -> None:
    calls = []
    answers = iter(["new-sandbox", "claude", "y"])

    monkeypatch.setattr("setup_docker_sandbox.start.discover_git_root", lambda root: tmp_path)
    monkeypatch.setattr("setup_docker_sandbox.start.default_sandbox_workspace", lambda root, clone: tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    def fake_create_sandbox(**kwargs):
        calls.append(kwargs)
        return "created sandbox new-sandbox"

    monkeypatch.setattr("setup_docker_sandbox.start.create_sandbox", fake_create_sandbox)

    assert prompt_new_sandbox_name(root=tmp_path / "app", dry_run=True) == "new-sandbox"
    assert calls == [
        {
            "name": "new-sandbox",
            "agent": "claude",
            "workspace": tmp_path,
            "clone": True,
            "dry_run": True,
        }
    ]
