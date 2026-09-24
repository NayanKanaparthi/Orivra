"""The Gmail seed transport: it exists, it is exercised, and it cannot write yet.

**No test here touches a real mailbox.** Every request goes to `httpx.MockTransport`, which is
also the point: the destructive capability is drivable end to end against a double, so its URLs,
its parameters and its refusals are checked before a live run rather than during one.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest

from mailweave_harness.pinning import SeedSession, verify_seed_account
from mailweave_harness.preflight.scope import MailboxScope
from mailweave_harness.scopes import SeedAccountMismatch
from mailweave_harness.seed.gmail_transport import (
    GMAIL_BASE,
    MAX_COUNT_PAGES,
    GmailSeedTransport,
    SeedTransportError,
    ThreadingRefused,
    WritesNotApproved,
)

SEED_ADDRESS = "mailweave.test@example.test"
RAW = (
    "Message-ID: <mw-s1-t01-m000@bench.invalid>\r\n"
    "From: ana@team.example\r\n"
    "To: bo@team.example\r\n"
    "Subject: Planning note\r\n"
    "Date: Mon, 05 Jan 2026 09:00:00 +0000\r\n"
    "\r\n"
    "the body\r\n"
)


class _Profile:
    email_address = SEED_ADDRESS


class _Credential:
    def get_profile(self) -> _Profile:
        return _Profile()


def _session() -> tuple[SeedSession, _Credential]:
    credential = _Credential()
    return verify_seed_account(credential, seed_address=SEED_ADDRESS), credential


def _transport(
    handler: Any, *, approved: bool = False
) -> tuple[GmailSeedTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    session, credential = _session()
    return (
        GmailSeedTransport(
            http=httpx.Client(transport=httpx.MockTransport(record)),
            session=session,
            credential=credential,
            access_token="ya29.NOT-A-REAL-TOKEN",
            approved_by_owner=approved,
        ),
        seen,
    )


def _ok(body: dict[str, Any]) -> Any:
    return lambda _request: httpx.Response(200, json=body)


# --- the gate ---------------------------------------------------------------------------


def test_an_unapproved_transport_refuses_to_insert_and_issues_no_request() -> None:
    """**Issues no request**, which is the half that matters. A refusal after the call has
    gone out is not a refusal, and a mailbox write cannot be taken back."""
    transport, seen = _transport(_ok({"id": "g1", "threadId": "t1"}))
    with pytest.raises(WritesNotApproved, match="approved_by_owner=True"):
        transport.insert(RAW)
    assert seen == []


def test_an_unapproved_transport_refuses_to_delete_and_issues_no_request() -> None:
    transport, seen = _transport(_ok({}))
    with pytest.raises(WritesNotApproved):
        transport.delete("g1")
    assert seen == []


def test_no_default_and_no_environment_variable_turns_writes_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The approval is an argument a human types, not a value something can supply.

    Asserted behaviourally rather than by reading the docstring: the field defaults to
    `False`, and setting every environment variable somebody might reach for changes nothing.
    A default of `True`, or a read from the environment, would let a run nobody approved look
    exactly like a run somebody did.
    """
    import dataclasses

    field = next(
        one for one in dataclasses.fields(GmailSeedTransport) if one.name == "approved_by_owner"
    )
    assert field.default is False
    for name in (
        "MAILWEAVE_SEED_APPROVED",
        "MAILWEAVE_ALLOW_WRITES",
        "APPROVED_BY_OWNER",
        "CI",
    ):
        monkeypatch.setenv(name, "1")
    transport, seen = _transport(_ok({"id": "g1", "threadId": "t1"}))
    with pytest.raises(WritesNotApproved):
        transport.insert(RAW)
    assert seen == []


def test_a_write_rechecks_the_binding_against_the_credential_in_hand() -> None:
    """Amendment A7's move: the check is at the point of use, not at construction.

    A session minted while authenticated as the seed account must not be usable by an
    operation running on a different credential, and a check that ran when the session was
    made cannot see that.
    """
    transport, seen = _transport(_ok({"id": "g1", "threadId": "t1"}), approved=True)
    transport.credential = _Credential()  # a different object: the proof no longer matches
    with pytest.raises(SeedAccountMismatch):
        transport.insert(RAW)
    assert seen == []


# --- reads -------------------------------------------------------------------------------


def test_the_authenticated_address_is_the_one_the_session_was_bound_to() -> None:
    transport, _seen = _transport(_ok({}))
    assert transport.authenticated_address() == SEED_ADDRESS


def test_count_matching_pages_and_counts_rather_than_trusting_the_estimate() -> None:
    """Gmail's `resultSizeEstimate` is an estimate, and the settle gate compares a count
    against the manifest. A number allowed to be wrong makes the gate wait forever or stop
    early, and both look like a corpus problem."""
    pages = [
        {"messages": [{"id": f"a{i}"} for i in range(3)], "nextPageToken": "p2"},
        {"messages": [{"id": "b0"}], "resultSizeEstimate": 9_999},
    ]
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[len(calls) - 1])

    transport, calls = _transport(handler)
    assert transport.count_matching("subject:whatever") == 4
    assert len(calls) == 2
    assert calls[1].url.params["pageToken"] == "p2"
    assert calls[0].url.params["q"] == "subject:whatever"


def test_an_endlessly_paging_query_is_refused_rather_than_walked() -> None:
    transport, _calls = _transport(
        _ok({"messages": [{"id": "x"}], "nextPageToken": "always-another"})
    )
    with pytest.raises(SeedTransportError, match=str(MAX_COUNT_PAGES)):
        transport.count_matching("in:anywhere")


# --- what a write would actually send -----------------------------------------------------


def test_an_approved_insert_sends_the_parameters_the_corpus_depends_on() -> None:
    """`internalDateSource=dateHeader`, because the dates **are** the measurement.

    The position sweep and every temporal family are built on `internalDate`. Letting Gmail
    stamp the insert time would collapse a corpus spanning months into one minute, and every
    number scored against it would be wrong in a way no later test can see.
    """
    transport, seen = _transport(_ok({"id": "g1", "threadId": "t1"}), approved=True)
    inserted = transport.insert(RAW)
    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url).startswith(f"{GMAIL_BASE}/messages")
    assert request.url.params["internalDateSource"] == "dateHeader"
    assert request.url.params["neverMarkSpam"] == "true"
    body = json.loads(request.content)
    assert base64.urlsafe_b64decode(body["raw"]).decode("utf-8") == RAW
    assert request.headers["Authorization"].startswith("Bearer ")
    assert inserted.gmail_id == "g1" and inserted.thread_id == "t1"


def test_the_reported_message_id_is_read_off_the_raw_message_not_echoed() -> None:
    """`substrate.verify` exists to catch a disagreement between the manifest and the mailbox,
    and it cannot catch one if the transport hands the manifest's own copy back."""
    transport, _seen = _transport(_ok({"id": "g1", "threadId": "t1"}), approved=True)
    assert transport.insert(RAW).rfc822_message_id == "<mw-s1-t01-m000@bench.invalid>"
    with pytest.raises(SeedTransportError, match="no Message-ID"):
        transport.insert("From: a@b.example\r\n\r\nbody\r\n")


def test_an_approved_delete_names_the_id_and_is_permanent() -> None:
    transport, seen = _transport(lambda _r: httpx.Response(204), approved=True)
    transport.delete("g-123")
    assert seen[0].method == "DELETE"
    assert str(seen[0].url) == f"{GMAIL_BASE}/messages/g-123"


def test_an_insert_that_names_no_id_is_refused_rather_than_recorded() -> None:
    transport, _seen = _transport(_ok({"threadId": "t1"}), approved=True)
    with pytest.raises(SeedTransportError, match="no id/threadId"):
        transport.insert(RAW)


def test_a_failing_write_raises_rather_than_returning_something() -> None:
    transport, _seen = _transport(lambda _r: httpx.Response(403, json={}), approved=True)
    with pytest.raises(SeedTransportError, match="403"):
        transport.insert(RAW)


# --- pacing: the bulk write meets a rate limit, because a bulk write always does -----------


def _paced(handler: Any, *, approved: bool = True) -> tuple[GmailSeedTransport, list[float]]:
    slept: list[float] = []
    session, credential = _session()
    transport = GmailSeedTransport(
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        session=session,
        credential=credential,
        access_token="ya29.NOT-A-REAL-TOKEN",
        approved_by_owner=approved,
        sleeper=slept.append,
        jitterer=lambda: 0.0,
    )
    return transport, slept


def _then_ok(failures: int, status: int, headers: dict[str, str] | None = None) -> Any:
    state = {"left": failures}

    def handler(_request: httpx.Request) -> httpx.Response:
        if state["left"] > 0:
            state["left"] -= 1
            return httpx.Response(status, headers=headers or {}, json={"error": "slow down"})
        return httpx.Response(200, json={"id": "g-1", "threadId": "t-1"})

    return handler


def test_a_rate_limited_insert_is_retried_rather_than_failing_the_run() -> None:
    """2,248 inserts against a per-user rate limit will meet a 429. Failing there leaves a
    half-seeded mailbox, which is the one failure the seeding path must not have."""
    transport, slept = _paced(_then_ok(2, 429))
    record = transport.insert(RAW)
    assert record.gmail_id == "g-1"
    assert len(slept) == 2
    assert slept == sorted(slept), "the backoff grows rather than hammering at a fixed rate"
    assert transport.retries == 2


def test_retry_after_wins_over_the_computed_delay() -> None:
    """Gmail knows how long its own limit has left to run; this transport does not."""
    transport, slept = _paced(_then_ok(1, 429, {"Retry-After": "30"}))
    transport.insert(RAW)
    assert slept == [30.0]


def test_a_retry_after_that_will_not_parse_falls_back_rather_than_raising() -> None:
    transport, slept = _paced(_then_ok(1, 429, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}))
    transport.insert(RAW)
    assert slept == [2.0], "the computed first delay, not a crash and not zero"


def test_the_sleep_is_capped_however_long_a_header_asks_for() -> None:
    transport, slept = _paced(_then_ok(1, 503, {"Retry-After": "86400"}))
    transport.insert(RAW)
    assert slept == [64.0]


def test_a_four_hundred_is_not_retried_because_retrying_it_is_a_loop() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400, json={"error": "bad message"})

    transport, slept = _paced(handler)
    with pytest.raises(SeedTransportError) as caught:
        transport.insert(RAW)
    assert len(calls) == 1
    assert slept == []
    assert "400" in str(caught.value)


def test_a_rate_limit_that_outlasts_the_retries_raises_and_says_how_many_it_tried() -> None:
    transport, slept = _paced(_then_ok(99, 429))
    with pytest.raises(SeedTransportError) as caught:
        transport.insert(RAW)
    assert len(slept) == transport.max_attempts - 1
    assert "attempt 6 of 6" in str(caught.value)


def test_the_transport_reports_what_it_waited() -> None:
    """A seeding run that took an hour should be able to say how much was Gmail saying wait."""
    transport, _slept = _paced(_then_ok(2, 429))
    transport.insert(RAW)
    assert transport.slept_seconds == pytest.approx(2.0 + 4.0)


def test_the_survey_count_asks_for_spam_and_trash_and_the_settle_count_does_not() -> None:
    """The `q` spelling never travels without `includeSpamTrash` beside it (round 12).

    Two different questions: "is the message this run inserted indexed yet", which is scoped
    the way a mailbox owner means their mail, and "how much is already in this account", whose
    honest answer includes the parts the default scope hides.
    """
    transport, seen = _transport(_ok({"messages": [], "resultSizeEstimate": 0}), approved=True)
    transport.count_matching("mw-sentinel-0001")
    transport.count_everything()
    scoped = [request.url.params.get("includeSpamTrash") for request in seen]
    assert scoped == ["false", "true"]
    assert seen[1].url.params.get("q") == MailboxScope.WHOLE_MAILBOX.query


# --- threading: the condition the live run never sent (R-M2-033) ---------------------------


def test_an_insert_without_a_thread_id_sends_no_thread_id() -> None:
    transport, seen = _transport(_ok({"id": "g1", "threadId": "g1"}), approved=True)
    record = transport.insert(RAW)
    assert json.loads(seen[0].content)["raw"]
    assert "threadId" not in json.loads(seen[0].content)
    assert record.thread_id == "g1"


def test_an_insert_into_a_thread_puts_the_thread_id_in_the_resource() -> None:
    """Gmail's condition 1: the target threadId is part of the `messages` resource supplied
    with the request. Not a query parameter, not a header."""
    transport, seen = _transport(_ok({"id": "g2", "threadId": "T1"}), approved=True)
    record = transport.insert(RAW, thread_id="T1")
    assert json.loads(seen[0].content)["threadId"] == "T1"
    assert seen[0].url.params.get("threadId") is None
    assert record.thread_id == "T1"


def test_a_thread_gmail_declined_raises_rather_than_returning_the_new_thread() -> None:
    """**The silent failure.** Gmail does not fail the call when it declines an association:
    it creates the message in a new thread and returns that id. A transport that returned it
    would report success 2,248 times and produce 2,248 conversations, which is what happened."""
    transport, _seen = _transport(_ok({"id": "g3", "threadId": "SOMETHING-ELSE"}), approved=True)
    with pytest.raises(ThreadingRefused) as caught:
        transport.insert(RAW, thread_id="T1")
    assert "T1" in str(caught.value)
    assert "SOMETHING-ELSE" in str(caught.value)
    assert "Subject" in str(caught.value), "it names the conditions worth checking"


def test_get_thread_reads_the_conversation_back_at_metadata_format() -> None:
    """Read-only, and the only way to answer "are these one conversation" from Gmail's side."""
    body = {"id": "T1", "messages": [{"id": "g1"}, {"id": "g2"}, {"id": "g3"}]}
    transport, seen = _transport(_ok(body), approved=False)
    assert transport.get_thread("T1") == ("g1", "g2", "g3")
    assert seen[0].url.path.endswith("/threads/T1")
    assert seen[0].url.params.get("format") == "metadata"
    assert seen[0].method == "GET"


def test_reading_a_thread_needs_no_write_approval() -> None:
    """It is a read. A rehearsal that had to arm the transport to check its own result would
    be a worse instrument than one that does not."""
    transport, _seen = _transport(_ok({"id": "T1", "messages": []}), approved=False)
    assert transport.get_thread("T1") == ()


def test_a_delete_of_a_message_that_is_gone_is_not_a_failure() -> None:
    """A cleanup of 2,252 ids can stop partway, and the record naming all of them is the only
    safe input to a second attempt. Reporting the already-removed ones as errors would make
    that attempt's output useless."""
    from mailweave_harness.seed.substrate import AlreadyGone

    transport, _seen = _transport(lambda _r: httpx.Response(404, json={}), approved=True)
    with pytest.raises(AlreadyGone):
        transport.delete("g-not-there")


def test_a_delete_refused_for_any_other_reason_is_still_a_failure() -> None:
    from mailweave_harness.seed.substrate import AlreadyGone

    transport, _seen = _transport(lambda _r: httpx.Response(403, json={}), approved=True)
    with pytest.raises(SeedTransportError) as caught:
        transport.delete("g-1")
    assert not isinstance(caught.value, AlreadyGone)


def test_delete_goes_to_the_permanent_endpoint_and_not_to_trash() -> None:
    """`messages.delete` removes the message outright. `messages/{id}/trash` would not."""
    transport, seen = _transport(_ok({}), approved=True)
    transport.delete("g-1")
    assert seen[0].method == "DELETE"
    assert seen[0].url.path.endswith("/messages/g-1")
    assert "trash" not in seen[0].url.path
