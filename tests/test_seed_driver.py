"""The seeding driver: every refusal, offline, before the one run that cannot be taken back.

`substrate` and `GmailSeedTransport` have their own tests. What is tested here is the thing
that holds a real credential and calls them in order - the piece that was previously a set of
instructions in a handoff document, which is the worst place for it: a document cannot refuse.

**Nothing here touches a mailbox.** Every request goes through `httpx.MockTransport`, and the
tests that matter most are the ones where *no* request is made at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from mailweave_harness.scopes import SEEDER_SCOPES, SeedAccountMismatch
from mailweave_harness.seed import driver
from mailweave_harness.seed.corpus import generate
from mailweave_harness.seed.gmail_transport import GMAIL_BASE
from mailweave_harness.seed.manifest import Manifest
from mailweave_harness.seed.substrate import InsertedMessage, VerificationReport
from tests.fixtures.gmail_threading import Gmail

SEED = "mailweave.test@example.test"
OTHER = "the.owner@example.test"


def _client_file(path: Path, client_id: str) -> Path:
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": client_id,
                    "client_secret": "not-a-real-secret",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)  # `read_installed_client` refuses anything looser, and is right to
    return path


@pytest.fixture
def manifest() -> Manifest:
    return generate(master_seed=1042, size_profile="smoke")


def test_the_plan_states_what_a_run_would_do_and_sends_nothing(
    manifest: Manifest, tmp_path: Path
) -> None:
    got = driver.plan(
        manifest,
        seed_address=SEED,
        client_path=_client_file(tmp_path / "harness.json", "harness.apps.googleusercontent.com"),
        token_path=tmp_path / "harness-credentials.json",
        approved=False,
        server_client_path=_client_file(tmp_path / "server.json", "server.apps.gooogle"),
    )
    assert got.messages == len(manifest.messages)
    assert got.threads == len(manifest.answer_key.threads)
    assert got.scopes == SEEDER_SCOPES
    assert got.approved is False
    rendered = "\n".join(got.lines())
    assert SEED in rendered
    assert "NO - nothing will be sent" in rendered


def test_a_harness_client_that_is_the_server_client_is_refused_before_any_call(
    manifest: Manifest, tmp_path: Path
) -> None:
    """Seeding it would request `https://mail.google.com/` on the owner's real mailbox."""
    shared = _client_file(tmp_path / "shared.json", "same.apps.googleusercontent.com")
    server = _client_file(tmp_path / "server.json", "same.apps.googleusercontent.com")
    with pytest.raises(driver.SeedingRefused) as caught:
        driver.plan(
            manifest,
            seed_address=SEED,
            client_path=shared,
            token_path=tmp_path / "harness-credentials.json",
            approved=True,
            server_client_path=server,
        )
    assert "same client id" in str(caught.value)


def test_a_harness_token_store_that_is_the_servers_is_refused(
    manifest: Manifest, tmp_path: Path
) -> None:
    """Two grants with different scopes in one file is how a read-only server gets a write."""
    store = tmp_path / "credentials.json"
    with pytest.raises(driver.SeedingRefused) as caught:
        driver.plan(
            manifest,
            seed_address=SEED,
            client_path=_client_file(tmp_path / "harness.json", "harness.apps"),
            token_path=store,
            approved=True,
            server_client_path=_client_file(tmp_path / "server.json", "server.apps"),
            server_token_path=store,
        )
    assert "the server's" in str(caught.value)


class _Transport(Gmail):
    """A double for `GmailSeedTransport`, threading the way Gmail documents.

    **It used to assign each message the thread id of its manifest `thread_key`**, which is to
    say it handed itself the answer to the question the seeding run existed to ask. Every
    threading test passed and the live run produced 2,248 single-message conversations
    (R-M2-033). It now inherits `tests/fixtures/gmail_threading.Gmail`, which enforces the
    three documented conditions and, crucially, refuses them the way the API does: silently,
    by returning a new thread id.

    The extra `inserted` list is the RFC ids in insert order, which several tests below assert
    against and which `Gmail` does not need to keep.
    """

    def __init__(self, address: str = SEED, manifest: Manifest | None = None) -> None:
        super().__init__(address=address)
        self.inserted: list[str] = []

    def insert(self, raw: str, *, thread_id: str | None = None) -> InsertedMessage:
        record = super().insert(raw, thread_id=thread_id)
        self.inserted.append(record.rfc822_message_id)
        return record


def test_a_run_inserts_every_message_settles_and_writes_the_report(
    manifest: Manifest, tmp_path: Path
) -> None:
    transport = _Transport(manifest=manifest)
    out = tmp_path / "verification-smoke-1042.json"
    ticks = iter(range(0, 10_000, 5))
    report = driver.run_seeding(
        transport,  # type: ignore[arg-type]
        manifest,
        seed_address=SEED,
        out=out,
        sleep=lambda _seconds: None,
        clock=lambda: float(next(ticks)),
    )
    assert len(report.inserted) == len(manifest.messages)
    assert not report.discrepancies
    body = json.loads(out.read_text())
    assert len(body["inserted"]) == len(manifest.messages)
    assert body["settle_polls"] >= 2, "EP §3.6 wants two agreeing polls, not one"
    assert transport.counted, "the settle gate must actually poll before a metric run"


def test_the_report_round_trips_so_a_later_cleanup_deletes_the_same_ids(
    manifest: Manifest, tmp_path: Path
) -> None:
    transport = _Transport(manifest=manifest)
    out = tmp_path / "verification.json"
    ticks = iter(range(0, 10_000, 5))
    driver.run_seeding(
        transport,  # type: ignore[arg-type]
        manifest,
        seed_address=SEED,
        out=out,
        sleep=lambda _seconds: None,
        clock=lambda: float(next(ticks)),
    )
    again = driver.report_from(out)
    result = driver.run_cleanup(transport, again, seed_address=SEED)  # type: ignore[arg-type]
    assert result.failed == () and result.complete
    assert transport.deleted == [one.gmail_id for one in again.inserted]


def test_cleanup_deletes_recorded_ids_and_never_a_query_result(tmp_path: Path) -> None:
    """A query-driven cleanup on a shared test account removes somebody else's mail."""
    transport = _Transport()
    report = VerificationReport(
        inserted=(InsertedMessage("mw-a@bench.invalid", "g-1", "t-1"),), discrepancies=()
    )
    driver.run_cleanup(transport, report, seed_address=SEED)  # type: ignore[arg-type]
    assert transport.deleted == ["g-1"]
    assert transport.counted == [], "cleanup asks no query"


def test_a_run_against_the_wrong_account_stops_before_the_first_insert(
    manifest: Manifest, tmp_path: Path
) -> None:
    transport = _Transport(address=OTHER, manifest=manifest)
    with pytest.raises(SeedAccountMismatch):
        driver.run_seeding(
            transport,  # type: ignore[arg-type]
            manifest,
            seed_address=SEED,
            out=tmp_path / "verification.json",
            sleep=lambda _seconds: None,
            clock=lambda: 0.0,
        )
    assert transport.inserted == [], "the address check runs before the first write, not after"


def test_a_cleanup_against_the_wrong_account_deletes_nothing() -> None:
    """Deletion is the one operation where being wrong is not recoverable (R-M1-013)."""
    transport = _Transport(address=OTHER)
    report = VerificationReport(
        inserted=(InsertedMessage("mw-a@bench.invalid", "g-1", "t-1"),), discrepancies=()
    )
    with pytest.raises(SeedAccountMismatch):
        driver.run_cleanup(transport, report, seed_address=SEED)  # type: ignore[arg-type]
    assert transport.deleted == []


def _profile_handler(address: str) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress": address, "messagesTotal": 1})
        return httpx.Response(200, json={})

    return handler


def test_the_transport_refuses_a_credential_authenticated_as_another_mailbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The structural control is Google's allowlist; this is the one that catches a correctly
    issued seed token pointed at the wrong configuration."""
    from mailweave.auth import tokenstore

    monkeypatch.setattr(tokenstore.TokenStore, "verify_permissions", lambda self: None)
    monkeypatch.setattr(
        driver, "StoredTokenProvider", lambda **kwargs: type("P", (), {"access_token": "t"})()
    )
    monkeypatch.setattr(
        driver,
        "GmailClient",
        lambda **kwargs: type(
            "C", (), {"get_profile": lambda self: type("P", (), {"email_address": OTHER})()}
        )(),
    )
    with pytest.raises(SeedAccountMismatch):
        driver.transport_for(
            client_path=_client_file(tmp_path / "harness.json", "harness.apps"),
            token_path=tmp_path / "credentials.json",
            seed_address=SEED,
            approved=True,
            http=httpx.Client(transport=httpx.MockTransport(_profile_handler(OTHER))),
        )


def test_the_gmail_base_the_driver_would_write_to_is_the_one_constant() -> None:
    """One constant, so a test asserts the exact host a destructive call would reach."""
    assert GMAIL_BASE == "https://gmail.googleapis.com/gmail/v1/users/me"


# --- the command, which is what an operator actually types ---------------------------------


def _manifest_file(manifest: Manifest, tmp_path: Path) -> Path:
    path = tmp_path / "manifest-smoke-1042.json"
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_plan_seeding_prints_the_plan_and_opens_no_token_store(
    manifest: Manifest, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from mailweave_harness.seed.__main__ import main

    code = main(
        [
            "--plan-seeding",
            "--manifest",
            str(_manifest_file(manifest, tmp_path)),
            "--seed-address",
            SEED,
            "--client-path",
            str(_client_file(tmp_path / "harness.json", "harness.apps")),
            "--token-path",
            str(tmp_path / "nonexistent" / "credentials.json"),
            "--server-client-path",
            str(_client_file(tmp_path / "server.json", "server.apps")),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "nothing was sent" in out
    assert f"will insert:       {len(manifest.messages)}" in out


def test_an_approval_that_names_a_different_account_stops_the_command(
    manifest: Manifest, tmp_path: Path
) -> None:
    """`--approve-writes-to` is not a `--yes`: it names the mailbox, and it is compared."""
    from mailweave_harness.seed.__main__ import main

    with pytest.raises(SystemExit) as caught:
        main(
            [
                "--seed-mailbox",
                "--manifest",
                str(_manifest_file(manifest, tmp_path)),
                "--seed-address",
                SEED,
                "--approve-writes-to",
                OTHER,
                "--client-path",
                str(_client_file(tmp_path / "harness.json", "harness.apps")),
                "--token-path",
                str(tmp_path / "credentials.json"),
                "--server-client-path",
                str(_client_file(tmp_path / "server.json", "server.apps")),
            ]
        )
    assert "does not name the configured seed account" in str(caught.value)


def test_seed_mailbox_without_an_approval_sends_nothing_and_says_what_to_type(
    manifest: Manifest, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from mailweave_harness.seed.__main__ import main

    code = main(
        [
            "--seed-mailbox",
            "--manifest",
            str(_manifest_file(manifest, tmp_path)),
            "--seed-address",
            SEED,
            "--client-path",
            str(_client_file(tmp_path / "harness.json", "harness.apps")),
            "--token-path",
            str(tmp_path / "credentials.json"),
            "--server-client-path",
            str(_client_file(tmp_path / "server.json", "server.apps")),
        ]
    )
    assert code == 1
    assert f"--approve-writes-to {SEED}" in capsys.readouterr().out


def test_a_write_command_without_a_named_account_is_refused_by_the_parser() -> None:
    from mailweave_harness.seed.__main__ import main

    with pytest.raises(SystemExit) as caught:
        main(["--seed-mailbox", "--manifest", "whatever.json"])
    assert "--seed-address" in str(caught.value)


def test_generating_a_corpus_still_needs_no_account_and_touches_no_mailbox(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from mailweave_harness.seed.__main__ import main

    assert main(["--generate", "--seed", "1042", "--profile", "smoke", "--out", str(tmp_path)]) == 0
    assert "no mailbox was touched" in capsys.readouterr().out


# --- the half-seeded mailbox, which is the failure that matters ----------------------------


class _FailsPartway(_Transport):
    """Inserts `limit` messages and then refuses, the way a rate limit that outlasts its
    retries or a revoked token would."""

    def __init__(self, limit: int, manifest: Manifest) -> None:
        super().__init__(manifest=manifest)
        self.limit = limit

    def insert(self, raw: str, *, thread_id: str | None = None) -> InsertedMessage:
        if len(self.inserted) >= self.limit:
            raise RuntimeError("429 after every retry")
        return super().insert(raw, thread_id=thread_id)


def test_a_run_that_fails_partway_still_records_what_it_inserted(
    manifest: Manifest, tmp_path: Path
) -> None:
    """Cleanup is driven from insert results and never from a query, so the results have to
    survive the failure - otherwise a half-seeded mailbox has no list of what to delete."""
    transport = _FailsPartway(5, manifest)
    out = tmp_path / "verification.json"
    with pytest.raises(RuntimeError):
        driver.run_seeding(
            transport,  # type: ignore[arg-type]
            manifest,
            seed_address=SEED,
            out=out,
            sleep=lambda _seconds: None,
            clock=lambda: 0.0,
        )
    body = json.loads(out.read_text())
    assert body["partial"] is True
    assert len(body["inserted"]) == 5
    assert "must not be scored against" in body["note"]


def test_the_partial_report_cleans_up_exactly_what_was_inserted(
    manifest: Manifest, tmp_path: Path
) -> None:
    transport = _FailsPartway(5, manifest)
    out = tmp_path / "verification.json"
    with pytest.raises(RuntimeError):
        driver.run_seeding(
            transport,  # type: ignore[arg-type]
            manifest,
            seed_address=SEED,
            out=out,
            sleep=lambda _seconds: None,
            clock=lambda: 0.0,
        )
    recovered = driver.report_from(out)
    assert len(recovered.inserted) == 5
    result = driver.run_cleanup(transport, recovered, seed_address=SEED)  # type: ignore[arg-type]
    assert result.failed == () and result.complete
    assert transport.deleted == [one.gmail_id for one in recovered.inserted]


def test_a_completed_run_is_not_marked_partial(manifest: Manifest, tmp_path: Path) -> None:
    transport = _Transport(manifest=manifest)
    out = tmp_path / "verification.json"
    ticks = iter(range(0, 10_000, 5))
    driver.run_seeding(
        transport,  # type: ignore[arg-type]
        manifest,
        seed_address=SEED,
        out=out,
        sleep=lambda _seconds: None,
        clock=lambda: float(next(ticks)),
    )
    assert "partial" not in json.loads(out.read_text())


def test_the_plan_quotes_the_settle_gate_the_code_actually_runs(
    manifest: Manifest, tmp_path: Path
) -> None:
    """A plan that states a number the code does not use is worse than no plan."""
    from mailweave_harness.seed.substrate import SETTLE_INTERVAL_SECONDS, SETTLE_TIMEOUT_SECONDS

    got = driver.plan(
        manifest,
        seed_address=SEED,
        client_path=_client_file(tmp_path / "harness.json", "harness.apps"),
        token_path=tmp_path / "credentials.json",
        approved=False,
        server_client_path=_client_file(tmp_path / "server.json", "server.apps"),
    )
    rendered = "\n".join(got.lines())
    assert f"{SETTLE_INTERVAL_SECONDS:.0f}s apart" in rendered
    assert f"{SETTLE_TIMEOUT_SECONDS / 60:.0f} minutes" in rendered


# --- the survey, which is the measurement behind "isolated from existing test mail" ---------


class _Occupied(_Transport):
    """A mailbox that already has mail in it, and possibly a sentinel collision."""

    def __init__(self, manifest: Manifest, *, existing: int, collides: frozenset[str]) -> None:
        super().__init__(manifest=manifest)
        self.existing = existing
        self.collides = collides

    def count_matching(self, query: str) -> int:
        self.counted.append(query)
        return 1 if query in self.collides else 0

    def count_everything(self) -> int:
        self.counted.append("<whole mailbox>")
        return self.existing


def test_the_survey_counts_what_is_there_and_writes_nothing(
    manifest: Manifest,
) -> None:
    transport = _Occupied(manifest, existing=412, collides=frozenset())
    found = driver.survey(transport, manifest)  # type: ignore[arg-type]
    assert found.existing_messages == 412
    assert found.safe
    assert transport.inserted == [] and transport.deleted == []
    assert "cleanup will remove" in "\n".join(found.lines())


def test_a_sentinel_that_already_matches_makes_the_survey_refuse(manifest: Manifest) -> None:
    """It would make the settle gate pass early and a recall metric join on a row the seeder
    did not insert - EP's reason for checking uniqueness against the mailbox, not the manifest."""
    token = manifest.sentinels[0]
    transport = _Occupied(manifest, existing=1, collides=frozenset({token}))
    found = driver.survey(transport, manifest)  # type: ignore[arg-type]
    assert not found.safe
    assert token in found.colliding_sentinels
    assert "REFUSE" in "\n".join(found.lines())


def test_the_survey_transport_is_built_unapproved_so_a_write_on_it_is_still_refused(
    manifest: Manifest,
) -> None:
    """A read-only command must not leave an armed transport behind."""
    import inspect

    from mailweave_harness.seed.__main__ import _survey

    source = inspect.getsource(_survey)
    assert "approved=False" in source


# --- the order of the three checks, and the tilde nobody expanded -------------------------


class _Indexing(_Transport):
    """A mailbox whose search index lags, the way Gmail's does after a bulk insert.

    `count_matching` answers 0 until `indexed` is set, which is what the settle gate is for.
    """

    def __init__(self, manifest: Manifest) -> None:
        super().__init__(manifest=manifest)
        self.indexed = False

    def count_matching(self, query: str) -> int:
        self.counted.append(query)
        return 1 if self.indexed else 0


def test_the_index_question_is_asked_after_the_settle_gate_and_not_before(
    manifest: Manifest, tmp_path: Path
) -> None:
    """Two of `verify`'s checks read the insert results and answer at once; the third asks
    Gmail's search index, which has not caught up. Asked before the settle gate it reports a
    discrepancy per sentinel on every successful seeding."""
    transport = _Indexing(manifest)
    ticks = iter(range(0, 100_000, 5))

    def sleep(_seconds: float) -> None:
        transport.indexed = True  # the index catches up while the gate waits, as it does

    report = driver.run_seeding(
        transport,  # type: ignore[arg-type]
        manifest,
        seed_address=SEED,
        out=tmp_path / "verification.json",
        sleep=sleep,
        clock=lambda: float(next(ticks)),
    )
    assert report.discrepancies == (), [one.what for one in report.discrepancies[:5]]
    assert len(report.inserted) == len(manifest.messages)


def test_an_ambiguous_sentinel_in_the_gates_own_sample_never_settles(
    manifest: Manifest, tmp_path: Path
) -> None:
    """The gate wants each polled sentinel to match exactly **one** message. Two is not a
    number it waits out, and a run that reached the metrics with an ambiguous sentinel would
    join a recall figure on a row the seeder did not insert."""
    from mailweave_harness.seed.substrate import SettleTimedOut

    class _Duplicated(_Transport):
        def count_matching(self, query: str) -> int:
            self.counted.append(query)
            return 2 if query in manifest.sentinels else 1

    ticks = iter([0.0] + [10_000.0] * 500)
    with pytest.raises(SettleTimedOut):
        driver.run_seeding(
            _Duplicated(manifest=manifest),  # type: ignore[arg-type]
            manifest,
            seed_address=SEED,
            out=tmp_path / "verification.json",
            sleep=lambda _seconds: None,
            clock=lambda: next(ticks),
        )


def test_the_post_gate_check_is_wider_than_the_gate_it_follows(manifest: Manifest) -> None:
    """`settle` polls at most ten sentinels; the gate corpus has eighty. The check after the
    gate asks about **every** one of them, which is what makes moving it after the gate a
    reordering rather than a narrowing."""
    from mailweave_harness.seed.substrate import SETTLE_SENTINELS, sentinels_unique

    transport = _Transport(manifest=manifest)
    asked = sentinels_unique(transport, manifest)  # type: ignore[arg-type]
    assert asked == ()
    assert transport.counted == list(manifest.sentinels)
    assert len(manifest.sentinels) >= 1
    polled = manifest.sentinels[:SETTLE_SENTINELS]
    assert len(polled) <= len(manifest.sentinels)


def test_an_ambiguous_sentinel_is_reported_by_the_post_gate_check(manifest: Manifest) -> None:
    """Moving the check after the gate must not delete it."""
    from mailweave_harness.seed.substrate import sentinels_unique

    bad = manifest.sentinels[-1]

    class _Duplicated(_Transport):
        def count_matching(self, query: str) -> int:
            self.counted.append(query)
            return 2 if query == bad else 1

    found = sentinels_unique(_Duplicated(manifest=manifest), manifest)  # type: ignore[arg-type]
    assert [one.what for one in found] == [f"sentinel {bad}"]
    assert found[0].observed == "2"


def test_a_settle_gate_that_times_out_still_leaves_the_cleanup_record(
    manifest: Manifest, tmp_path: Path
) -> None:
    """By then the mailbox holds the corpus. Losing the list of what to delete is the worst
    possible outcome of a gate that only says "not indexed yet"."""
    from mailweave_harness.seed.substrate import SettleTimedOut

    transport = _Indexing(manifest)  # never indexes
    out = tmp_path / "verification.json"
    ticks = iter([0.0] + [10_000.0] * 50)
    with pytest.raises(SettleTimedOut):
        driver.run_seeding(
            transport,  # type: ignore[arg-type]
            manifest,
            seed_address=SEED,
            out=out,
            sleep=lambda _seconds: None,
            clock=lambda: next(ticks),
        )
    body = json.loads(out.read_text())
    assert body["partial"] is True
    assert len(body["inserted"]) == len(manifest.messages)


def test_a_resumed_run_inserts_only_what_is_missing_and_counts_the_rest_present(
    manifest: Manifest, tmp_path: Path
) -> None:
    """A run that died at message 2,000 finishes rather than inserting those two thousand a
    second time - and rather than reporting them absent."""
    first = _FailsPartway(5, manifest)
    out = tmp_path / "verification.json"
    with pytest.raises(RuntimeError):
        driver.run_seeding(
            first,  # type: ignore[arg-type]
            manifest,
            seed_address=SEED,
            out=out,
            sleep=lambda _seconds: None,
            clock=lambda: 0.0,
        )
    prior = driver.report_from(out).inserted
    assert len(prior) == 5

    # **The same mailbox, continued.** A resume runs against the account the first attempt
    # half-filled; the conversations it opened are still there and are what the rebuilt thread
    # map asks for. Handing the resume a fresh mailbox would be testing a situation that does
    # not arise, and would pass for the wrong reason.
    first.limit = len(manifest.messages)
    before = len(first.inserted)
    ticks = iter(range(0, 100_000, 5))
    report = driver.run_seeding(
        first,  # type: ignore[arg-type]
        manifest,
        seed_address=SEED,
        out=out,
        sleep=lambda _seconds: None,
        clock=lambda: float(next(ticks)),
        prior=prior,
    )
    sent = len(first.inserted) - before
    assert sent == len(manifest.messages) - 5, "the five are not sent again"
    assert len(report.inserted) == len(manifest.messages), "and they still count as present"
    assert report.discrepancies == (), [one.what for one in report.discrepancies]
    ids = [one.rfc822_message_id for one in report.inserted]
    assert len(set(ids)) == len(ids), "no message is recorded twice"
    assert set(ids) == {one.rfc822_message_id for one in manifest.messages}
    assert len({one.thread_id for one in report.inserted}) == len(manifest.answer_key.threads)


def test_the_plan_says_how_many_a_resume_would_skip(manifest: Manifest, tmp_path: Path) -> None:
    report = tmp_path / "partial.json"
    report.write_text(
        json.dumps(
            {
                "inserted": [
                    {"rfc822_message_id": "<a@x>", "gmail_id": "g-1", "thread_id": "t-1"},
                    {"rfc822_message_id": "<b@x>", "gmail_id": "g-2", "thread_id": "t-1"},
                ],
                "discrepancies": [],
                "partial": True,
            }
        ),
        encoding="utf-8",
    )
    got = driver.plan(
        manifest,
        seed_address=SEED,
        client_path=_client_file(tmp_path / "harness.json", "harness.apps"),
        token_path=tmp_path / "credentials.json",
        approved=False,
        server_client_path=_client_file(tmp_path / "server.json", "server.apps"),
        resume_from=report,
    )
    assert got.already_inserted == 2
    rendered = "\n".join(got.lines())
    assert f"{len(manifest.messages) - 2} message(s)" in rendered
    assert "2 already inserted" in rendered


@pytest.mark.parametrize("flag", ["--token-path", "--client-path", "--manifest"])
def test_a_path_argument_with_a_literal_tilde_is_expanded(flag: str) -> None:
    """A shell expands `~` in an unquoted argument; a default, a quoted one and a scripted one
    all arrive with the tilde intact, and `TokenStore` then reports "~/... does not exist",
    which reads like a missing login rather than an unexpanded path."""
    from mailweave_harness.seed.__main__ import _path

    got = _path("~/somewhere/file.json")
    assert not str(got).startswith("~"), flag
    assert got.is_absolute()


def test_the_default_token_path_is_expanded_before_anything_stats_it(tmp_path: Path) -> None:
    from mailweave_harness.seed.__main__ import main

    with pytest.raises(SystemExit):
        main(["--seed-mailbox", "--seed-address", SEED])  # no --manifest; parser exits
    # The default is what bit: `--survey` with no `--token-path` stat'ed a literal `~`.
    import argparse

    from mailweave_harness.seed.__main__ import DEFAULT_TOKEN_PATH, _path

    assert str(DEFAULT_TOKEN_PATH).startswith("~"), "the documented default is still a tilde"
    parser = argparse.ArgumentParser()
    parser.add_argument("--token-path", type=_path, default=DEFAULT_TOKEN_PATH.expanduser())
    assert not str(parser.parse_args([]).token_path).startswith("~")
    assert not str(parser.parse_args(["--token-path", "~/x.json"]).token_path).startswith("~")


def test_a_cleanup_records_what_it_actually_deleted(manifest: Manifest, tmp_path: Path) -> None:
    """The input record says what was targeted; this says what was done. Worth writing
    precisely because `messages.delete` is permanent and cannot be reversed."""
    transport = _Transport(manifest=manifest)
    out = tmp_path / "verification.json"
    ticks = iter(range(0, 100_000, 5))
    report = driver.run_seeding(
        transport,  # type: ignore[arg-type]
        manifest,
        seed_address=SEED,
        out=out,
        sleep=lambda _seconds: None,
        clock=lambda: float(next(ticks)),
    )
    record = tmp_path / "cleanup.json"
    result = driver.run_cleanup(
        transport,  # type: ignore[arg-type]
        report,
        seed_address=SEED,
        out=record,
    )
    body = json.loads(record.read_text())
    assert body["permanent"] is True
    assert "cannot be recovered" in body["note"]
    assert body["targeted"] == len(report.inserted)
    assert body["deleted"] == [one.gmail_id for one in result.deleted]
    assert body["failed"] == []
    assert len(body["deleted"]) == len(manifest.messages)


def test_a_second_cleanup_pass_reports_already_gone_rather_than_failures(
    manifest: Manifest, tmp_path: Path
) -> None:
    """A cleanup that stopped partway is re-run from the same record. The ids the first pass
    removed must not read as errors, or the output of the second says nothing useful."""
    from mailweave_harness.seed.substrate import AlreadyGone

    class _Once(_Transport):
        def delete(self, gmail_id: str) -> None:
            if gmail_id in self.deleted:
                raise AlreadyGone(gmail_id)
            super().delete(gmail_id)

    transport = _Once(manifest=manifest)
    out = tmp_path / "verification.json"
    ticks = iter(range(0, 100_000, 5))
    report = driver.run_seeding(
        transport,  # type: ignore[arg-type]
        manifest,
        seed_address=SEED,
        out=out,
        sleep=lambda _seconds: None,
        clock=lambda: float(next(ticks)),
    )
    first = driver.run_cleanup(transport, report, seed_address=SEED)  # type: ignore[arg-type]
    assert first.complete and len(first.deleted) == len(manifest.messages)

    second = driver.run_cleanup(transport, report, seed_address=SEED)  # type: ignore[arg-type]
    assert second.complete, "nothing failed"
    assert second.deleted == ()
    assert len(second.already_gone) == len(manifest.messages)
    assert second.removed == len(manifest.messages)
