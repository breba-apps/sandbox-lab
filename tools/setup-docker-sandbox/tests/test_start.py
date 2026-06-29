import subprocess

from setup_docker_sandbox.models import Decision, EnvEntry, Mode
from setup_docker_sandbox.start import detect_divergence


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
