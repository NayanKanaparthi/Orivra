"""The desktop beta's onboarding, offline: the flow, the surface, and the two `--events` commands.

What is held here, with fakes only where the real thing needs a person or the network:

  * **the surface** - the extension publishes the product's tools as `orivra serve` does,
    byte for byte, and one setup tool beside them; before setup a product tool answers with
    an error naming the setup tool, and after it the call is the product's own (§1);
  * **the flow** - `Setup.advance` starts the download and the consent as the product's own
    commands with this installation's paths, shows the link with the explanation a person
    needs before opening it, reports progress, and verifies through the injected bring-up;
    it starts nothing twice, recovers from every failure by starting that step again, and a
    credential Google refuses leads to a new link rather than a loop (§2);
  * **the reconnect** - a product refusal whose recovery is `reauthorise` passes through
    untouched, gains the beta's note, and sends setup back to consent (§3);
  * **the commands** - `setup-models --events` over a real lock and a scripted model host
    reports plan, byte progress, per-file outcome and done, verifies on a second run, and
    refuses bytes the lock does not describe; `auth login --events` reports the link and the
    grant and never a secret (§4).

The consent listener and the model host are not faked in `docs/DESKTOP_BETA.md`'s clean-install
proof, which runs the built bundle as a fresh user; this file is the part that can run offline.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from mailweave import cli
from mailweave.auth.consent import ConsentFailed, LoginReport
from mailweave.auth.profile import Profile
from mailweave.auth.tokenstore import StoredCredentials, TokenStore
from mailweave.constants import SERVER_SCOPES
from mailweave.models import provision
from mailweave.surface.runtime import Runtime, StartupReport
from orivra.desktop import server as desktop_server
from orivra.desktop import texts
from orivra.desktop.paths import DesktopPaths
from orivra.desktop.setup import BringUpFailed, Setup
from orivra.surface.server import tool_list
from tests.test_orivra_text_only_protocol import _service

# --- fakes -----------------------------------------------------------------------------------


class ScriptedChild:
    """A child process whose events the test appends, and whose exit the test decides."""

    def __init__(self, arguments: Sequence[str]) -> None:
        self.arguments = list(arguments)
        self._events: list[dict[str, Any]] = []
        self.code: int | None = None
        self.terminated = False

    def say(self, event: str, **fields: Any) -> None:
        self._events.append({"event": event, **fields})

    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def returncode(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.terminated = True
        self.code = -15 if self.code is None else self.code


class Spawns:
    """Records every child the flow starts; a new consent child prints its link at once."""

    def __init__(self) -> None:
        self.children: list[ScriptedChild] = []
        self.link_number = 0

    def __call__(self, arguments: Sequence[str], _label: str) -> ScriptedChild:
        child = ScriptedChild(arguments)
        if arguments[:2] == ["auth", "login"]:
            self.link_number += 1
            child.say(
                "authorization_url",
                url=f"https://accounts.google.com/o/oauth2/v2/auth?link={self.link_number}",
                port=40000 + self.link_number,
                timeout_s=300.0,
            )
        self.children.append(child)
        return child

    def of(self, command: str) -> list[ScriptedChild]:
        return [one for one in self.children if one.arguments[0] == command]


LOCK_FILES = {"weights.bin": 3 * (1 << 20), "vocab.txt": 1024}


def _write_lock(path: Path) -> dict[str, bytes]:
    """A real lock over two small files, returning the bytes a model host would serve."""
    served = {
        name: bytes([index + 1]) * size for index, (name, size) in enumerate(LOCK_FILES.items())
    }
    lock = {
        "schema": 1,
        "models": {
            "stage_a_default.python-st": {
                "repo_id": "example/tiny-encoder",
                "revision": "a" * 40,
                "license": "MIT",
                "pinned_at": "2026-09-23T00:00:00+00:00",
                "artifact_set": "python-st",
                "runtime": "sentence-transformers",
                "files": [
                    {
                        "name": name,
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                    for name, data in served.items()
                ],
            }
        },
    }
    path.write_text(json.dumps(lock))
    return served


@pytest.fixture
def paths(tmp_path: Path) -> DesktopPaths:
    bundle = tmp_path / "bundle"
    (bundle / "config").mkdir(parents=True)
    _write_lock(bundle / "models.lock")
    return DesktopPaths(bundle=bundle, home=tmp_path / "home")


def _grant(paths: DesktopPaths, *, obtained_at: str = "2026-09-23T10:00:00+00:00") -> None:
    """What a successful `auth login` leaves behind: a real credential store."""
    TokenStore(paths.credentials).save(
        StoredCredentials(
            client_id="beta-client.apps.googleusercontent.com",
            refresh_token=SecretStr("1//refresh-token-never-rendered"),
            scopes=SERVER_SCOPES,
            salt_hex="00" * 16,
            obtained_at=obtained_at,
        )
    )


def _install_models(paths: DesktopPaths) -> None:
    from mailweave.models.lock import load_lock
    from mailweave.models.paths import model_dir

    lock = load_lock(paths.lock)
    for key, locked in lock.models.items():
        directory = model_dir(key, locked.revision, paths.models)
        directory.mkdir(parents=True, exist_ok=True)
        for entry in locked.files:
            (directory / entry.name).write_bytes(b"\0" * entry.bytes)


class BringUps:
    """A bring-up that serves the product over the synthetic mailbox, or fails as told."""

    def __init__(self) -> None:
        self.calls = 0
        self.fail_with: Exception | None = None

    def __call__(self, _paths: DesktopPaths) -> Any:
        self.calls += 1
        if self.fail_with is not None:
            raise self.fail_with
        service = _service()
        runtime = Runtime(
            service=service.registry.gmail().service,
            report=StartupReport(
                client_id="beta-client.apps.googleusercontent.com",
                account="tester@example.com",
                profile=Profile.PERSONAL,
                granted_scopes=SERVER_SCOPES,
                token_path=Path("/nowhere/credentials.json"),
                handles_enabled=True,
            ),
            close=lambda: None,
        )
        return runtime, service, ("example/tiny-encoder@aaaaaaaaaaaa",)


def _setup(paths: DesktopPaths) -> tuple[Setup, Spawns, BringUps]:
    spawns, bring_ups = Spawns(), BringUps()
    return Setup(paths, spawn=spawns, bring_up=bring_ups), spawns, bring_ups


# --- §1 the surface ----------------------------------------------------------------------------


def test_the_extension_publishes_the_products_tools_unchanged_and_one_setup_tool() -> None:
    product = [tool.model_dump() for tool in tool_list().tools]
    published = [tool.model_dump() for tool in desktop_server.desktop_tools()]
    assert published[: len(product)] == product, "a product tool is described differently"
    assert [tool["name"] for tool in published[len(product) :]] == [texts.SETUP_TOOL_NAME]
    setup_tool = desktop_server.SETUP_TOOL
    assert setup_tool.annotations is not None
    assert setup_tool.annotations.read_only_hint is False, "setup stores a credential"
    assert setup_tool.annotations.destructive_hint is False


def test_before_setup_a_product_tool_says_so_and_names_the_setup_tool(paths: DesktopPaths) -> None:
    setup, spawns, bring_ups = _setup(paths)
    result = desktop_server.call(setup, "orivra_ask", {"query": "anything"})
    assert result.is_error
    assert result.structured_content is None
    text = result.content[0].text  # type: ignore[union-attr]
    assert texts.SETUP_TOOL_NAME in text and "not set up" in text
    assert spawns.children == [], "a product tool starts no setup step by itself"
    assert bring_ups.calls == 0


def test_after_setup_a_product_tool_is_the_products_own_call(paths: DesktopPaths) -> None:
    _grant(paths)
    _install_models(paths)
    setup, _spawns, bring_ups = _setup(paths)
    result = desktop_server.call(setup, "orivra_ask", {"query": "rollout window slipped"})
    assert bring_ups.calls == 1
    assert not result.is_error, result.content
    assert isinstance(result.structured_content, dict)
    assert len(result.content) == 1, "nothing is added to a served product result"


# --- §2 the flow -------------------------------------------------------------------------------


def test_the_first_call_starts_both_steps_with_this_installations_paths(
    paths: DesktopPaths,
) -> None:
    setup, spawns, _ = _setup(paths)
    text = setup.advance()
    (models,) = spawns.of("setup-models")
    assert models.arguments == [
        "setup-models",
        "--events",
        "--lock",
        str(paths.lock),
        "--models-dir",
        str(paths.models),
    ]
    (consent,) = spawns.of("auth")
    assert consent.arguments == [
        "auth",
        "login",
        "--events",
        "--client",
        str(paths.client),
        "--state-dir",
        str(paths.state),
    ]
    assert "https://accounts.google.com/o/oauth2/v2/auth?link=1" in text
    for needed in (
        "hasn't verified this app",
        "has not yet completed Google's verification",
        f"{texts.UNVERIFIED_USER_CAP} new users in total",
        "does not expire on a schedule",
        "six months unused",
        "password changes",
        "5 minutes",
        str(paths.credentials),
        "cannot send, delete, label or change anything",
        *SERVER_SCOPES,
    ):
        assert needed in text, needed
    # The beta's Google application is External and In production, not Testing (2026-09-24):
    # there is no test-user list to be on and no seven-day clock, so the text claims neither.
    for testing_only in ("test user", "7 days", "seven days", "organiser has added"):
        assert testing_only not in text, testing_only


def test_calling_again_starts_nothing_twice_and_reports_progress(paths: DesktopPaths) -> None:
    setup, spawns, _ = _setup(paths)
    setup.advance()
    (models,) = spawns.of("setup-models")
    models.say("plan", models=["stage_a_default.python-st"], total_bytes=sum(LOCK_FILES.values()))
    models.say(
        "progress",
        model="stage_a_default.python-st",
        file="weights.bin",
        done=1 << 20,
        file_total=3 << 20,
    )
    text = setup.advance()
    assert len(spawns.of("setup-models")) == 1 and len(spawns.of("auth")) == 1
    assert "Models: downloading, 33%" in text and "now weights.bin" in text
    assert "link=1" in text, "the link still waiting is shown again, not replaced"


def test_setup_finishes_by_itself_once_both_steps_are_done(paths: DesktopPaths) -> None:
    setup, spawns, bring_ups = _setup(paths)
    setup.advance()
    (models,) = spawns.of("setup-models")
    (consent,) = spawns.of("auth")
    for name in LOCK_FILES:
        models.say("file", model="stage_a_default.python-st", state="fetched", file=name)
    models.say("done")
    models.code = 0
    _grant(paths)
    consent.say("granted", account="tester@example.com", granted_scopes=list(SERVER_SCOPES))
    consent.code = 0
    text = setup.advance()
    assert bring_ups.calls == 1
    assert text.startswith("Orivra is ready.")
    assert "connected as tester@example.com, read-only" in text
    assert "granted 2026-09-23 10:00 UTC" in text
    assert "It has no expiry date" in text and "around 2026-09-30" not in text
    assert "Ask a question" in text
    assert setup.ready is not None
    assert desktop_server.call(setup, "orivra_sources", {}).is_error is False


def test_a_failed_consent_is_reported_and_a_new_link_is_issued(paths: DesktopPaths) -> None:
    setup, spawns, _ = _setup(paths)
    setup.advance()
    (consent,) = spawns.of("auth")
    consent.say(
        "failed", reason="auth login: no redirect arrived on the loopback listener within 300s"
    )
    consent.code = 1
    text = setup.advance()
    assert "the last attempt did not finish - auth login: no redirect arrived" in text
    assert len(spawns.of("auth")) == 2 and "link=2" in text


def test_a_failed_download_is_reported_and_started_again(paths: DesktopPaths) -> None:
    setup, spawns, _ = _setup(paths)
    setup.advance()
    (models,) = spawns.of("setup-models")
    models.say("failed", reason="setup-models: ConnectError: [Errno 8] nodename nor servname")
    models.code = 1
    text = setup.advance()
    assert "the last download failed (setup-models: ConnectError" in text
    assert "started again" in text
    assert text.count("ConnectError") == 1, "the failure is reported once, not twice"
    assert len(spawns.of("setup-models")) == 2
    assert text.count("Orivra answers with two local models") == 0, "the plan is shown once"
    # And when the retried download fails too, the status says so once, with what to do.
    spawns.of("setup-models")[-1].say("failed", reason="setup-models: ConnectError: again")
    spawns.of("setup-models")[-1].code = 1
    later = setup.advance()
    assert "started again" in later and len(spawns.of("setup-models")) == 3


def test_a_credential_google_refuses_leads_to_a_new_link_not_a_loop(paths: DesktopPaths) -> None:
    _grant(paths)
    _install_models(paths)
    setup, spawns, bring_ups = _setup(paths)
    bring_ups.fail_with = ConsentFailed(
        "the token endpoint refused the exchange: invalid_grant. The stored grant is expired"
    )
    text = setup.advance()
    assert bring_ups.calls == 1, "one refused bring-up, then consent - not a retry loop"
    assert "invalid_grant" in text
    assert len(spawns.of("auth")) == 1 and "link=1" in text
    assert spawns.of("setup-models") == [], "the models were fine and are not downloaded again"
    # The person consents again: the next call verifies once more and is ready.
    bring_ups.fail_with = None
    (consent,) = spawns.of("auth")
    consent.say("granted", account="tester@example.com")
    consent.code = 0
    assert setup.advance().startswith("Orivra is ready.")
    assert bring_ups.calls == 2


def test_models_the_loader_refuses_are_downloaded_again(paths: DesktopPaths) -> None:
    _grant(paths)
    _install_models(paths)
    setup, spawns, bring_ups = _setup(paths)
    bring_ups.fail_with = BringUpFailed("models", "local model load failed: digest mismatch")
    text = setup.advance()
    assert bring_ups.calls == 1
    assert len(spawns.of("setup-models")) == 1, text
    assert spawns.of("auth") == [], "the credential was not the problem"


def test_an_unreachable_gmail_is_a_retry_not_a_new_consent(paths: DesktopPaths) -> None:
    from mailweave.gmail.faults import GmailFault
    from mailweave.gmail.rates import GmailEndpoint

    _grant(paths)
    _install_models(paths)
    setup, spawns, bring_ups = _setup(paths)
    bring_ups.fail_with = GmailFault(
        "users.getProfile could not be reached", endpoint=GmailEndpoint.GET_PROFILE
    )
    text = setup.advance()
    assert "Last check: users.getProfile could not be reached" in text
    assert spawns.children == []


# --- §3 the reconnect --------------------------------------------------------------------------


def test_a_reauthorise_refusal_passes_through_gains_the_note_and_returns_to_consent(
    paths: DesktopPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcp.types as types

    _grant(paths)
    _install_models(paths)
    setup, spawns, _ = _setup(paths)
    refusal = types.CallToolResult(
        content=[
            types.TextContent(type="text", text="auth_reauth_required: run mailweave auth login")
        ],
        structured_content={"code": "auth_reauth_required", "recovery": "reauthorise"},
        is_error=True,
    )
    monkeypatch.setattr(desktop_server, "orivra_call", lambda *_args: refusal)
    result = desktop_server.call(setup, "orivra_ask", {"query": "x"})
    assert result.is_error
    assert result.structured_content == refusal.structured_content, "passed through untouched"
    assert result.content[0] == refusal.content[0]
    assert result.content[-1].text == texts.REAUTHORISE_NOTE  # type: ignore[union-attr]
    assert "revoked" in texts.REAUTHORISE_NOTE and "six months unused" in texts.REAUTHORISE_NOTE
    assert "7 days" not in texts.REAUTHORISE_NOTE and "test" not in texts.REAUTHORISE_NOTE
    assert setup.ready is None
    text = setup.advance()
    assert "Google no longer accepts the stored authorization" in text
    assert len(spawns.of("auth")) == 1


# --- §4 the two commands, with --events -----------------------------------------------------


def _scripted_host(served: dict[str, bytes]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        if name not in served:
            return httpx.Response(404)
        return httpx.Response(200, content=served[name])

    return httpx.MockTransport(handler)


def _run_events(argv: list[str]) -> tuple[int, list[dict[str, Any]]]:
    out = io.StringIO()
    code = cli.setup_models(
        catalog_path=Path("unused"),
        lock_path=Path(argv[0]),
        models_dir=Path(argv[1]),
        pin_targets=None,
        status_only=False,
        smoke=False,
        events=True,
        out=out,
    )
    return code, [json.loads(line) for line in out.getvalue().splitlines()]


def test_setup_models_events_report_plan_progress_files_and_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "models.lock"
    served = _write_lock(lock_path)
    original = provision._client
    monkeypatch.setattr(provision, "_client", lambda inner=None: original(_scripted_host(served)))
    code, events = _run_events([str(lock_path), str(tmp_path / "models")])
    assert code == 0
    kinds = [event["event"] for event in events]
    assert kinds[0] == "plan" and kinds[-1] == "done"
    assert events[0]["total_bytes"] == sum(LOCK_FILES.values())
    progress = [event for event in events if event["event"] == "progress"]
    assert progress, "a download that moves reports that it moves"
    assert progress[-1]["done"] == progress[-1]["file_total"]
    assert all(event["done"] <= event["file_total"] for event in progress)
    fetched = {event["file"]: event["state"] for event in events if event["event"] == "file"}
    assert fetched == dict.fromkeys(LOCK_FILES, "fetched")
    # A second run downloads nothing and verifies everything.
    code, again = _run_events([str(lock_path), str(tmp_path / "models")])
    assert code == 0
    assert {
        event["file"]: event["state"] for event in again if event["event"] == "file"
    } == dict.fromkeys(LOCK_FILES, "ok")
    assert not [event for event in again if event["event"] == "progress"]


def test_setup_models_events_refuse_bytes_the_lock_does_not_describe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "models.lock"
    served = _write_lock(lock_path)
    served["vocab.txt"] = b"x" * LOCK_FILES["vocab.txt"]  # right size, wrong bytes
    original = provision._client
    monkeypatch.setattr(provision, "_client", lambda inner=None: original(_scripted_host(served)))
    code, events = _run_events([str(lock_path), str(tmp_path / "models")])
    assert code == 1
    assert events[-1]["event"] == "failed"
    assert "do not match the lock" in events[-1]["reason"]


def test_auth_login_events_report_the_link_and_the_grant_and_never_a_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = tmp_path / "client.json"
    client.write_text(
        json.dumps({"installed": {"client_id": "beta.apps", "client_secret": "GOCSPX-never-shown"}})
    )
    client.chmod(0o600)

    class Receiver:
        port = 45678

        def wait_for_redirect(self) -> str:
            return "unused"

        def close(self) -> None:
            pass

    def run_login(**kwargs: Any) -> LoginReport:
        kwargs["wait_for_code"]("https://accounts.google.com/o/oauth2/v2/auth?x=1", "state")
        return LoginReport(
            client_id="beta.apps",
            client_path=client,
            requested_scopes=SERVER_SCOPES,
            granted_scopes=SERVER_SCOPES,
            scopes_verified=True,
            account="tester@example.com",
            profile=Profile.PERSONAL,
            token_path=tmp_path / "state" / "credentials.json",
            refresh_token_stored=True,
            obtained_at=datetime(2026, 9, 23, tzinfo=UTC).isoformat(),
        )

    monkeypatch.setattr(cli, "LoopbackReceiver", Receiver)
    monkeypatch.setattr(cli, "run_login", run_login)
    out = io.StringIO()
    code = cli.auth_login(
        client_path=client,
        state_dir=tmp_path / "state",
        dry_run=False,
        expected_account=None,
        events=True,
        out=out,
    )
    assert code == 0
    events = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [event["event"] for event in events] == ["authorization_url", "granted"]
    assert events[0]["port"] == 45678 and events[0]["timeout_s"] == 300.0
    assert events[1]["account"] == "tester@example.com"
    assert events[1]["granted_scopes"] == list(SERVER_SCOPES)
    assert "GOCSPX-never-shown" not in out.getvalue()

    def refused(**_kwargs: Any) -> LoginReport:
        raise ConsentFailed(
            "the loopback redirect was refused: authorization failed: access_denied"
        )

    monkeypatch.setattr(cli, "run_login", refused)
    out = io.StringIO()
    assert (
        cli.auth_login(
            client_path=client,
            state_dir=tmp_path / "state",
            dry_run=False,
            expected_account=None,
            events=True,
            out=out,
        )
        == 1
    )
    (failed,) = [json.loads(line) for line in out.getvalue().splitlines()]
    assert failed == {
        "event": "failed",
        "reason": "auth login: the loopback redirect was refused: authorization failed: "
        "access_denied",
    }
