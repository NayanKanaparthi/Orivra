"""The round-1 command line: credential hygiene, and an honest refusal for what is absent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mailweave.auth import StoredCredentials, TokenStore, new_salt
from mailweave.cli import main
from mailweave.config import load_config
from mailweave.freshness import WatermarkFile

SECRET = "client-secret-value-that-must-never-be-printed"


def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "client_id": "read-client.apps.googleusercontent.example",
                "client_secret": SECRET,
                "state_dir": str(tmp_path / "state"),
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def seed_store(tmp_path: Path) -> TokenStore:
    store = TokenStore(tmp_path / "state" / "credentials.json")
    store.save(
        StoredCredentials(
            client_id="read-client.apps.googleusercontent.example",
            refresh_token="1//refresh",  # type: ignore[arg-type]
            salt_hex=new_salt().hex(),
            obtained_at="2026-08-30T00:00:00Z",
        )
    )
    return store


def test_doctor_reports_a_healthy_setup_without_printing_the_secret(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = config_file(tmp_path)
    seed_store(tmp_path)
    assert main(["--config", str(path), "doctor"]) == 0
    out = capsys.readouterr().out
    assert "token store: ok" in out
    assert SECRET not in out
    assert "gmail.readonly" in out


def test_doctor_fails_on_an_over_permissive_token_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = config_file(tmp_path)
    store = seed_store(tmp_path)
    store.path.chmod(0o644)
    assert main(["--config", str(path), "doctor"]) == 1
    assert "PROBLEM" in capsys.readouterr().out


def test_doctor_reports_a_missing_config_rather_than_crashing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--config", str(tmp_path / "absent.json"), "doctor"]) == 1
    assert "config: FAIL" in capsys.readouterr().out


def test_purge_removes_the_store_and_is_idempotent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = config_file(tmp_path)
    store = seed_store(tmp_path)
    assert main(["--config", str(path), "purge"]) == 0
    assert not store.path.exists()
    assert main(["--config", str(path), "purge"]) == 0
    assert "nothing to purge" in capsys.readouterr().out


def test_purge_removes_the_watermark_too(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD D.9 says `mailweave purge` deletes the watermark, so purge has to mean all of it.

    A purge that removed the credential and left a persisted `historyId` stamp behind would
    leave the user a file they were told is removable. It is not a credential and not mail
    content, but it is persisted state about their mailbox.
    """
    path = config_file(tmp_path)
    seed_store(tmp_path)
    watermark = WatermarkFile(load_config(path).watermark_path)
    watermark.observe(address="someone@example.com", history_id="99120034")
    assert watermark.path.exists()

    assert main(["--config", str(path), "purge"]) == 0

    assert not watermark.path.exists()
    assert str(watermark.path) in capsys.readouterr().out


def test_auth_needs_a_subcommand(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Round 1's `mailweave auth` refused with an explanation; round 11 built `auth login`."""
    with pytest.raises(SystemExit):
        main(["auth"])
    assert "login" in capsys.readouterr().err


def test_auth_login_names_the_client_file_it_could_not_find(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["auth", "login", "--client", str(tmp_path / "absent.json")]) == 1
    printed = capsys.readouterr().out
    assert "absent.json" in printed
    assert "--client" in printed


def test_auth_login_dry_run_sends_nothing_and_states_the_scope_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The owner can read exactly what the real run will do before running it.

    The offline test fixture denies every outbound connection, so a dry run that reached the
    network would fail here rather than passing quietly.
    """
    client = tmp_path / "mailweave-server-oauth.json"
    client.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "read-client.apps.googleusercontent.example",
                    "client_secret": SECRET,
                }
            }
        ),
        encoding="utf-8",
    )
    client.chmod(0o600)

    assert (
        main(
            [
                "auth",
                "login",
                "--client",
                str(client),
                "--state-dir",
                str(tmp_path / "state"),
                "--dry-run",
            ]
        )
        == 0
    )
    printed = capsys.readouterr().out
    assert "https://www.googleapis.com/auth/gmail.readonly" in printed
    assert "GRANTED scope set is read back" in printed
    assert SECRET not in printed
