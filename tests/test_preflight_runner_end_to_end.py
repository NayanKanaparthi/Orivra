"""The preflight runner, driven end to end against the fake transport (round 12, part 1).

Round 11 authored six probes and unit-tested every `analyse` half. Nothing ever drove
`run_probes` itself: R-SEC-041 found that its first, unconditional line - `sample_mailbox`,
whose default `query=""` violates `ScanScopeEntry`'s `min_length=1` - raised
`pydantic.ValidationError` before any probe body ran, for every invocation, whichever probe
was selected. `mailweave-preflight --run` therefore could not complete a single Gmail call.

This file is the missing arm. It stands a whole mailbox up behind the real client - real URL
construction, real repeated `metadataHeaders` key, real bearer header, real retry ladder,
real egress allowlist, with an `httpx.MockTransport` where the socket would be - and runs
every registered probe through `run_probes`, then writes the record the way `--run` does.

**What this can and cannot establish.** It establishes that the runner completes, that each
probe's measure half composes with its analyse half over responses of the documented shape,
and that the record the run writes survives OD-4's content check. It establishes nothing
about Gmail: every verdict below is a verdict about a fixture. That is the point - the next
failure the owner sees should be a finding about their mailbox rather than a defect here.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from mailweave.gmail import BackoffPolicy, CallMeter, GmailClient, StaticToken
from mailweave.net.egress import build_client
from mailweave_harness.preflight import REGISTRY, Verdict, assert_record_is_content_free, measure
from mailweave_harness.preflight.probes import headers, threads
from mailweave_harness.preflight.runner import record_results, run_probes
from mailweave_harness.preflight.scope import MailboxScope
from tests.fixtures import gmail_shapes as shapes
from tests.fixtures.gmail_shapes import FakeGmail, json_response

TOKEN = "ya29.SECRET-ACCESS-TOKEN-NEVER-IN-A-PREFLIGHT-RECORD"

#: Thread row counts, one per thread id in the listing fixture. Deliberately all different:
#: `PF-thread-size-ceiling` fails when three threads sit at one exact maximum, so a double
#: that answered every `threads.get` with the same shape would report a Gmail thread cap
#: that is really an artefact of the double. Derived from `[DISCOVERY] THREAD_METADATA`;
#: only the number of rows differs.
THREAD_ROWS: dict[str, int] = {"t100": 2, "t200": 1, "t300": 3}


def thread_body(thread_id: str, rows: int) -> dict[str, Any]:
    """A `Thread` of `rows` messages, in `THREAD_METADATA`'s shape, for `thread_id`."""
    template = shapes.THREAD_METADATA["messages"][0]
    messages = []
    for index in range(rows):
        message = json.loads(json.dumps(template))
        message["id"] = f"{thread_id}-m{index}"
        message["threadId"] = thread_id
        message["internalDate"] = str(1735689600000 + index * 3600000)
        if index:
            # Every reply after the first carries RFC threading headers. Without them no
            # thread in this double could exhibit reply-header survival, and PF-2 would
            # report INCONCLUSIVE for the question the whole probe exists to ask - which is
            # exactly what the first live run did, for exactly this reason. A double that
            # cannot exhibit the property under test cannot be evidence about it.
            parent = f"<{thread_id}-m{index - 1}@example.invalid>"
            message["payload"]["headers"].extend(
                [
                    {"name": "In-Reply-To", "value": parent},
                    {"name": "References", "value": parent},
                ]
            )
        messages.append(message)
    return {
        "id": thread_id,
        "historyId": "99120034",
        "snippet": shapes.THREAD_METADATA["snippet"],
        "messages": messages,
    }


def message_metadata(message_id: str) -> dict[str, Any]:
    """[DISCOVERY] `messages.get(format=metadata)` - id, labels and headers, no body.

    Carries an RFC822 `Message-ID`, which is what the freshness probe's id-exact search
    needs; a metadata response without one makes `find_by_id` answer False for every
    message, which is a different measurement from the one PF-freshness-raw is taking.
    """
    return {
        "id": message_id,
        "threadId": "t100",
        "labelIds": ["INBOX"],
        "historyId": "99120050",
        "payload": {
            "partId": "",
            "mimeType": "text/plain",
            "headers": [
                {"name": "Message-ID", "value": f"<{message_id}@mail.example>"},
                {"name": "Subject", "value": "Quarterly planning"},
            ],
        },
    }


def strip_to_ids_and_labels(thread: dict[str, Any]) -> dict[str, Any]:
    """`THREAD_METADATA_NO_INTERNAL_DATE`'s shape, over an arbitrary thread.

    The shipped fixture carries its own message ids; PF-2 compares the two arms *by id*, so
    a pessimistic arm built from a different fixture shares no message with the full arm and
    the probe correctly reports INCONCLUSIVE rather than FAIL. Deriving the pessimistic arm
    from the same thread is what makes the comparison happen at all.
    """
    return {
        "id": thread["id"],
        "historyId": thread["historyId"],
        "messages": [
            {"id": message["id"], "threadId": message["threadId"], "labelIds": ["INBOX"]}
            for message in thread["messages"]
        ],
    }


def message_full(message_id: str) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(json.dumps(shapes.MESSAGE_FULL))
    body["id"] = message_id
    return body


@dataclass
class PreflightMailbox:
    """Every endpoint the runner touches, answered from the recorded shapes.

    One behaviour beyond replaying: an endpoint called `refuse_after` times **in a row**
    starts answering 429. PF-3 drives one endpoint at a time to refusal, so a consecutive
    streak is what that phase looks like from the transport's side, and counting streaks
    rather than lifetime totals keeps the budgets independent of how many calls the five
    other probes happened to make first.
    """

    refuse_after: dict[str, int] = field(default_factory=dict)
    thread_rows: dict[str, int] = field(default_factory=lambda: dict(THREAD_ROWS))
    #: When set, `format=metadata` answers in `THREAD_METADATA_NO_INTERNAL_DATE`'s shape -
    #: id and labels, no headers, no snippet, no internalDate - which is what the Format
    #: enum's own text says METADATA returns. G1's pessimistic branch.
    metadata_is_ids_and_labels_only: bool = False
    calls: Counter[str] = field(default_factory=Counter)
    _streak_key: str = ""
    _streak: int = 0

    # -- routing ------------------------------------------------------------------------

    def handler(self, request: httpx.Request) -> httpx.Response:
        key = FakeGmail.key_for(request.url.path)
        if key != self._streak_key:
            self._streak_key, self._streak = key, 0
        self._streak += 1
        self.calls[key] += 1
        budget = self.refuse_after.get(key)
        if budget is not None and self._streak > budget:
            return json_response(429, shapes.error_body(429, "rateLimitExceeded"))
        return self.respond(key, request)

    def respond(self, key: str, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if key == "messages.list":
            return json_response(200, self.listing(params))
        if key == "messages.get":
            message_id = request.url.path.rsplit("/", 1)[-1]
            if params.get("format") == "metadata":
                return json_response(200, message_metadata(message_id))
            return json_response(200, message_full(message_id))
        if key == "threads.get":
            thread_id = request.url.path.rsplit("/", 1)[-1]
            body = thread_body(thread_id, self.thread_rows.get(thread_id, 2))
            if params.get("format") == "metadata" and self.metadata_is_ids_and_labels_only:
                body = strip_to_ids_and_labels(body)
            return json_response(200, body)
        if key == "history.list":
            return json_response(200, shapes.HISTORY_PAGE)
        if key == "profile":
            return json_response(200, shapes.PROFILE)
        raise AssertionError(f"the runner reached an endpoint this double does not serve: {key}")

    def listing(self, params: httpx.QueryParams) -> dict[str, Any]:
        query = params.get("q") or ""
        if query.startswith("rfc822msgid:"):
            # An id-exact search returns the one message, on a single page.
            return {"messages": [{"id": "18f0a1", "threadId": "t100"}], "resultSizeEstimate": 1}
        if params.get("pageToken"):
            return shapes.MESSAGES_LIST_PAGE_2
        return shapes.MESSAGES_LIST_PAGE_1

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def make_client(mailbox: PreflightMailbox) -> GmailClient:
    """The shipped client; only the socket is replaced."""
    return GmailClient(
        token=StaticToken(TOKEN),
        http=build_client(inner=mailbox.transport()),
        meter=CallMeter(),
        policy=BackoffPolicy(),
        sleeper=lambda _seconds: None,
        jitterer=lambda: 0.5,
    )


#: PF-3 drives each endpoint until it is refused. Descending in the published rank order
#: (history.list cheapest, threads.get dearest) so the probe's primary falsifier - rank
#: order - is exercised rather than trivially satisfied. The absolute numbers are small on
#: purpose: they make the inferred per-call cost disagree with the published table, which is
#: the *other* half of PF-3's judgement, so both halves are visibly reached.
QUOTA_STREAKS: dict[str, int] = {
    "history.list": 40,
    "messages.list": 24,
    "messages.get": 12,
    "threads.get": 8,
}


def run_everything(mailbox: PreflightMailbox) -> dict[str, Any]:
    client = make_client(mailbox)
    try:
        results = run_probes(
            client,
            exclusive_window=True,
            freshness_window_s=0.01,
            freshness_poll_s=0.05,
        )
    finally:
        client.close()
    return {result.spec.id: result for result in results}


def test_every_registered_probe_runs_end_to_end_against_the_fake_transport() -> None:
    """R-SEC-041's regression, at the level the finding was about.

    Before the fix this raised `pydantic.ValidationError` from `run_probes`' first line -
    `sample_mailbox`'s `query=""` against `ScanScopeEntry.q`'s `min_length=1` - so no probe
    ran and no verdict existed. The assertion that matters is the first one: every result.
    """
    mailbox = PreflightMailbox(refuse_after=dict(QUOTA_STREAKS))

    by_id = run_everything(mailbox)

    assert sorted(by_id) == sorted(probe.id for probe in REGISTRY)
    assert len(by_id) == len(REGISTRY) == 7  # PF-21 joined in round 28
    for probe_id, result in by_id.items():
        assert isinstance(result.verdict, Verdict), probe_id


def test_each_probe_reaches_the_verdict_its_fixtures_imply() -> None:
    """Every verdict here is a verdict about a fixture, and each is named rather than left
    to be read off a pass/fail count."""
    mailbox = PreflightMailbox(refuse_after=dict(QUOTA_STREAKS))

    by_id = run_everything(mailbox)

    # The metadata arm and the full arm carry the same headers, snippet and internalDate,
    # which is G1's optimistic branch. A real mailbox decides which branch is true.
    pf2 = by_id["PF-2-metadata-headers"]
    assert pf2.verdict is Verdict.PASS
    # A PASS is only reachable because the double's threads actually carry reply headers.
    # Both questions must be exercised, not merely un-failed.
    assert pf2.findings["reply_header_verdict"] == "pass"
    assert pf2.findings["snippet_verdict"] == "pass"
    assert pf2.findings["reply_header_bearing_messages_compared"] >= 1
    # The selector takes the largest thread first, so the 3-row one, not the smallest id.
    assert pf2.findings["thread_selection"] == "deterministic-largest-first-reply-bearing"
    # threads.get never returns fewer rows than messages.list attributed to the thread.
    completeness = by_id["PF-1-thread-completeness"]
    assert completeness.verdict is Verdict.PASS
    assert completeness.findings["threads_compared"] == 3
    # Three threads of three different sizes: a tail, not a cap.
    ceiling = by_id["PF-thread-size-ceiling"]
    assert ceiling.verdict is Verdict.PASS
    assert ceiling.findings["histogram"] == {"1": 1, "2": 1, "3": 1}
    # The sampled bodies are ASCII, so the question this probe asks was never exercised.
    strip = by_id["PF-cf-strip-damage"]
    assert strip.verdict is Verdict.INCONCLUSIVE
    assert strip.findings["bodies_examined"] == 4
    # Arrivals were seen and every one became findable, so raw numbers and never a claim.
    freshness = by_id["PF-freshness-raw"]
    assert freshness.verdict is Verdict.OBSERVATION_ONLY
    assert freshness.findings["arrivals_observed"] == 2
    assert freshness.findings["never_found_within_window"] == 0
    # Every endpoint was driven to a real 429 through the real retry ladder.
    quota = by_id["PF-3-quota-units"]
    observed = quota.findings["observed"]
    assert [row["calls_completed"] for row in observed.values()] == [40, 24, 12, 8]
    assert all(row["refused"] for row in observed.values())
    assert all(row["refusal_status"] == 429 for row in observed.values())
    assert quota.findings["rank_order_holds"] is True
    # The counts are a hundredth of the published table's, so the *other* half of PF-3's
    # judgement - agreement with the published per-call cost - fails, which is what a real
    # disagreement would look like and is why the verdict is a FAIL about a fixture.
    assert sorted(quota.findings["outside_agreement_factor"]) == sorted(observed)
    assert quota.verdict is Verdict.FAIL


def test_a_real_finding_travels_out_of_the_runner_rather_than_a_defect_in_it() -> None:
    """The pessimistic G1 branch: `format=metadata` returns neither snippet nor internalDate.

    This is the branch AD F PF-2 says would execute, and the point of the runner working is
    that the owner sees *this* rather than a `ValidationError` from our own first line.
    """
    mailbox = PreflightMailbox(
        refuse_after=dict(QUOTA_STREAKS), metadata_is_ids_and_labels_only=True
    )

    by_id = run_everything(mailbox)

    headers = by_id["PF-2-metadata-headers"]
    assert headers.verdict is Verdict.FAIL
    assert headers.findings["messages_losing_internal_date_under_metadata"] > 0
    assert headers.findings["messages_losing_snippet_under_metadata"] > 0
    # Only headers the full arm shows the message actually carries count as dropped, which
    # is PF-2's own pre-registered rule. The double's replies now carry RFC threading
    # headers, so a metadata arm that strips everything drops those too - and this is the
    # reply-header FAIL path, reached end to end rather than asserted about.
    assert sorted(headers.findings["headers_dropped_by_metadata"]) == [
        "date",
        "from",
        "in-reply-to",
        "message-id",
        "references",
        "subject",
    ]
    assert headers.findings["reply_linking_headers_dropped"] == ["in-reply-to", "references"]
    assert headers.findings["reply_header_verdict"] == "fail"
    # **Absent from both arms is not a drop; it is the list of headers this probe could not
    # say anything about.** `Reply-To` and `Authentication-Results` join it in round 31
    # because WS-14's INJ-05 asks the thread-map fetch for them, and this double carries
    # neither - which is the honest state and the reason the entry exists: PF-2 against real
    # Gmail is what will say whether `format=metadata` returns them, exactly as it did for
    # `Cc`. Until it runs, the server treats their presence as unverified.
    assert sorted(headers.findings["headers_absent_from_both_arms"]) == [
        "authentication-results",
        "cc",
        "in-reply-to",
        "references",
        "reply-to",
        "to",
    ]


def test_the_run_writes_a_record_that_survives_the_od4_content_check(tmp_path: Path) -> None:
    """`--run` ends in `record_results`; a run that cannot be recorded has not completed."""
    mailbox = PreflightMailbox(refuse_after=dict(QUOTA_STREAKS))
    client = make_client(mailbox)
    try:
        results = run_probes(
            client, exclusive_window=True, freshness_window_s=0.01, freshness_poll_s=0.05
        )
    finally:
        client.close()

    summary = record_results(results, tmp_path)

    written = sorted(path.name for path in tmp_path.glob("*.json"))
    assert written == sorted(f"{probe.id}.json" for probe in REGISTRY)
    for path in tmp_path.glob("*.json"):
        assert_record_is_content_free(json.loads(path.read_text(encoding="utf-8")))
    whole_run = summary.read_text(encoding="utf-8") + "".join(
        path.read_text(encoding="utf-8") for path in tmp_path.glob("*.json")
    )
    assert TOKEN not in whole_run
    for probe in REGISTRY:
        assert probe.id in summary.read_text(encoding="utf-8")


def test_a_single_probe_selection_also_gets_past_the_first_gmail_call() -> None:
    """R-SEC's reproduction verbatim: one unrelated probe selected, and it still crashed."""
    mailbox = PreflightMailbox()
    client = make_client(mailbox)
    try:
        results = run_probes(client, selected=["PF-cf-strip-damage"])
    finally:
        client.close()

    assert [result.spec.id for result in results] == ["PF-cf-strip-damage"]


def test_the_sample_walk_sends_a_query_gmail_and_the_wire_schema_both_accept() -> None:
    """The defect in one line: an empty `q` is refused by `ScanScopeEntry` before the wire.

    Asserted at the transport rather than at the model, because the finding was that the
    *call* never happened - a test of the model alone would have passed all round 11.
    """
    mailbox = PreflightMailbox()
    client = make_client(mailbox)
    sent: list[str] = []
    original = mailbox.respond

    def record(key: str, request: httpx.Request) -> httpx.Response:
        if key == "messages.list":
            sent.append(request.url.params.get("q") or "")
        return original(key, request)

    mailbox.respond = record  # type: ignore[method-assign]
    try:
        run_probes(client, selected=["PF-1-thread-completeness"])
    finally:
        client.close()

    assert sent, "no messages.list call was made at all"
    assert all(query for query in sent), f"an empty q reached the wire: {sent}"


def test_pf3_still_refuses_to_run_without_the_declared_exclusive_window() -> None:
    """PF-16 is enforced, and the Part 1 fix did not open a way around it."""
    from mailweave_harness.preflight.runner import ExclusiveWindowRequired

    mailbox = PreflightMailbox()
    client = make_client(mailbox)
    try:
        with pytest.raises(ExclusiveWindowRequired):
            run_probes(client, selected=["PF-3-quota-units"])
    finally:
        client.close()


# --- part 6: the two ways of saying "where to look" travel as one value ----------------------


def record_listing_calls(mailbox: PreflightMailbox) -> list[tuple[str, str | None]]:
    """Capture `(q, includeSpamTrash)` as the transport actually received them.

    At the transport, not at `MailboxScope`: the finding this guards is that the pair can be
    *supplied* separately, so a test that asks the enum what it holds asserts the pairing
    against the same table that defines it. What has to be true is what left the process.
    """
    seen: list[tuple[str, str | None]] = []
    original = mailbox.respond

    def record(key: str, request: httpx.Request) -> httpx.Response:
        if key == "messages.list":
            params = request.url.params
            seen.append((params.get("q") or "", params.get("includeSpamTrash")))
        return original(key, request)

    mailbox.respond = record  # type: ignore[method-assign]
    return seen


@pytest.mark.parametrize("scope", list(MailboxScope), ids=lambda s: s.name.lower())
def test_both_mailbox_scopes_reach_the_wire_as_one_agreeing_pair(scope: MailboxScope) -> None:
    """Both members of the enum, driven end to end - the `in:anywhere` arm included.

    Part 1 wrote `unfiltered_query(include_spam_trash=True) -> "in:anywhere"` and nothing in
    the tree ever passed `True`: the branch was reachable in principle, carefully documented,
    and executed by nothing. Here each scope is run through the real client, the real URL
    construction and the real allowlist transport, and what is asserted is the *pair* the
    request carried - which is the thing that could not previously be wrong in one half only.
    """
    mailbox = PreflightMailbox()
    client = make_client(mailbox)
    seen = record_listing_calls(mailbox)
    try:
        observation = measure.measure_threads(client, salt=b"a fixed test salt", scope=scope)
    finally:
        client.close()

    assert seen, "no messages.list call was made at all"
    for query, include_spam_trash in seen:
        assert query == scope.query
        assert (include_spam_trash == "true") is scope.include_spam_trash
        # Stated independently of the enum as well, because the two assertions above read
        # their expectation off the same table that produced the request: they would agree
        # with each other even if the table itself paired `in:anywhere` with a parameter
        # that excludes spam and trash, which is the state this is all about.
        assert ("in:anywhere" in query) is (include_spam_trash == "true")
    findings = threads.analyse_completeness(observation).findings
    assert findings["include_spam_trash"] is scope.include_spam_trash
    assert findings["listing_query"] == scope.query


def test_no_listing_in_a_whole_run_can_send_the_two_settings_out_of_step() -> None:
    """The invariant over every `messages.list` a full run makes, not only the walks.

    PF-1 compares two endpoints "at the same includeSpamTrash setting", which is a comparison
    of nothing if a walk asks the search index for `in:anywhere` while telling the request
    parameter to exclude spam and trash. The id-exact `rfc822msgid:` search PF-freshness-raw
    makes carries neither spelling, which is itself agreement: both settings then mean the
    same default mailbox.
    """
    mailbox = PreflightMailbox(refuse_after=dict(QUOTA_STREAKS))
    client = make_client(mailbox)
    seen = record_listing_calls(mailbox)
    try:
        run_probes(client, exclusive_window=True, freshness_window_s=0.01, freshness_poll_s=0.05)
    finally:
        client.close()

    assert len(seen) > 1
    for query, include_spam_trash in seen:
        asked_for_everything = "in:anywhere" in query
        parameter_says_everything = include_spam_trash == "true"
        assert asked_for_everything is parameter_says_everything, (
            f"a listing sent q={query!r} with includeSpamTrash={include_spam_trash!r}: the "
            "two settings describe different mailboxes"
        )


# --- PF-2 thread selection (2026-09-11) -------------------------------------------------


class _RecordingThreads:
    """A client stand-in that answers `get_thread` from prepared bodies and counts calls."""

    def __init__(self, bodies: dict[str, dict[str, Any]]) -> None:
        self._bodies = bodies
        self.fetched: list[tuple[str, str]] = []

    def get_thread(self, _ledger, *, thread_id, rung, message_format, metadata_headers=None):
        self.fetched.append((thread_id, message_format))
        from mailweave.gmail import Thread

        return SimpleNamespace(thread=Thread.model_validate(self._bodies[thread_id]))


def _selection_client() -> _RecordingThreads:
    # t200 has the smallest id and one message; t300 is the largest thread. The old
    # selector took sorted(ids)[0] -> t200, which is how run 1 drew a one-message thread.
    return _RecordingThreads(
        {thread_id: thread_body(thread_id, rows) for thread_id, rows in THREAD_ROWS.items()}
    )


def test_the_selector_takes_the_largest_thread_not_the_smallest_id() -> None:
    client = _selection_client()
    by_message = {f"{t}-m{i}": t for t, rows in THREAD_ROWS.items() for i in range(rows)}

    choice = measure.choose_reply_bearing_thread(client, thread_by_message=by_message)

    assert choice is not None
    assert choice.thread_id == "t300"
    assert choice.selection == "deterministic-largest-first-reply-bearing"
    assert choice.candidates_probed == 1
    assert client.fetched == [("t300", "full")]


def test_the_selector_skips_threads_that_cannot_exhibit_the_property() -> None:
    # Only t200 exists and it is one message with no reply headers, so nothing can answer
    # the reply question. The selector says so rather than pretending it chose well.
    client = _RecordingThreads({"t200": thread_body("t200", 1)})

    choice = measure.choose_reply_bearing_thread(client, thread_by_message={"t200-m0": "t200"})

    assert choice is not None
    assert choice.selection == "deterministic-largest-first-none-reply-bearing"
    verdict = headers.analyse(
        measure.measure_metadata_headers(
            client,
            thread_id=choice.thread_id,
            full_arm=choice.full_arm,
            selection=choice.selection,
            candidates_probed=choice.candidates_probed,
        )
    )
    assert verdict.findings["reply_header_verdict"] == "inconclusive"
    assert verdict.verdict is not Verdict.PASS


def test_the_selectors_full_arm_is_reused_rather_than_refetched() -> None:
    # Two threads.get calls are two instants: a message delivered between them lands in one
    # arm only and reads as a header the metadata arm dropped.
    client = _selection_client()
    by_message = {f"{t}-m{i}": t for t, rows in THREAD_ROWS.items() for i in range(rows)}
    choice = measure.choose_reply_bearing_thread(client, thread_by_message=by_message)
    assert choice is not None
    client.fetched.clear()

    measure.measure_metadata_headers(client, thread_id=choice.thread_id, full_arm=choice.full_arm)

    assert client.fetched == [("t300", "metadata")]


def test_a_mailbox_with_no_threads_selects_nothing_rather_than_guessing() -> None:
    assert measure.choose_reply_bearing_thread(_selection_client(), thread_by_message={}) is None


def test_an_operator_supplied_thread_id_is_measured_without_any_selection_probes() -> None:
    """The path the rerun command takes. Untested code is not a command to hand someone."""
    mailbox = PreflightMailbox(refuse_after=dict(QUOTA_STREAKS))
    client = make_client(mailbox)
    try:
        results = run_probes(
            client,
            selected=["PF-2-metadata-headers"],
            headers_thread_id="t300",
        )
    finally:
        client.close()
    assert len(results) == 1
    findings = results[0].findings
    assert findings["thread_selection"] == "operator-supplied-thread-id"
    assert findings["candidate_threads_probed"] == 0
    assert findings["reply_header_verdict"] == "pass"
    assert findings["reply_header_bearing_messages_compared"] >= 1
