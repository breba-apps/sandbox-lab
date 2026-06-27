from pathlib import Path

from setup_docker_sandbox.envfiles import load_env_file, quote_env_value, write_env_file
from setup_docker_sandbox.models import EnvEntry


def test_load_env_file_uses_dotenv_parser(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "PLAIN=value",
                'QUOTED="hello world"',
                "EMPTY=",
                "# ignored",
            ]
        ),
        encoding="utf-8",
    )

    entries = load_env_file(env_file)

    assert entries == [
        EnvEntry("PLAIN", "value"),
        EnvEntry("QUOTED", "hello world"),
        EnvEntry("EMPTY", ""),
    ]


def test_quote_env_value_quotes_only_when_needed() -> None:
    assert quote_env_value("abc_123./:@%+-") == "abc_123./:@%+-"
    assert quote_env_value("") == '""'
    assert quote_env_value("hello world") == '"hello world"'
    assert quote_env_value('hello "world"') == '"hello \\"world\\""'


def test_write_env_file_redacts_nothing_but_quotes_values(tmp_path: Path) -> None:
    env_file = tmp_path / "safe.env"

    write_env_file(
        env_file,
        [
            EnvEntry("A", "1"),
            EnvEntry("B", "hello world"),
        ],
    )

    assert env_file.read_text(encoding="utf-8") == 'A=1\nB="hello world"\n'
