"""WS-02: the Gmail client against a fake transport (round 11).

The fake is an `httpx.MockTransport` sitting **behind the allowlist transport**, so every
test here exercises the real URL, the real query string, the real bearer header, the real
retry ladder and the real egress check. Faking the client's own methods would leave all five
untested, which is where a transport's defects live.

What each section is about:

  * the seam - a caller cannot obtain ids from a listing, and a thread's rows are in `H`
    before its content is reachable;
  * pagination - the page budget, and the widening affordance that `more_pages` requires;
  * retry - the exact delay sequence, every attempt charged, and the two bounds;
  * faults - one base class, typed codes, and no mail text or credential in any of them;
  * egress - the allowlist is consulted on every call, including through a mock.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from mailweave.constants import DEFAULT_PAGE_SIZE, GMAIL_API_HOST, MAX_PAGES_PER_QUERY
from mailweave.envelope import DispositionLedger, RungId
from mailweave.envelope.vocab import ToolName
from mailweave.envelope.wire import Affordance
from mailweave.errors import ERROR_SURFACE, ErrorCode, Surface
from mailweave.gmail import (
    BackoffPolicy,
    CallMeter,
    GmailAuthExpired,
    GmailClient,
    GmailEndpoint,
    GmailFault,
    GmailRateLimited,
    GmailRequestRejected,
    GmailResponseMalformed,
    GmailResponseUnexpected,
    GmailTransportFailure,
    GmailUnavailable,
    StaticToken,
)
from mailweave.net.egress import build_client
from tests.fixtures import gmail_shapes as shapes
from tests.fixtures.gmail_shapes import FakeGmail, json_response

TOKEN = "ya29.SECRET-ACCESS-TOKEN-NEVER-IN-A-TRACEBACK"

WIDEN = Affordance(tool=ToolName.SEARCH, args={"scan": {"max_pages": 2}})


def make_client(
    fake: FakeGmail,
    *,
    policy: BackoffPolicy | None = None,
    slept: list[float] | None = None,
    jitter: float = 0.5,
) -> GmailClient:
    """A client whose only difference from the shipped one is where the socket would be."""
    http = build_client(inner=fake.transport())
    return GmailClient(
        token=StaticToken(TOKEN),
        http=http,
        meter=CallMeter(),
        policy=policy if policy is not None else BackoffPolicy(),
        sleeper=(slept if slept is None else slept.append),
        jitterer=lambda: jitter,
    )


# --- the seam ------------------------------------------------------------------------------


def test_a_listing_returns_counts_and_a_token_and_no_ids() -> None:
    """The R-ORCH-001 probe, attempted through the shipped client rather than a stub."""
    fake = FakeGmail().queue("messages.list", json_response(200, shapes.MESSAGES_LIST_PAGE_1))
    client = make_client(fake)
    ledger = DispositionLedger()

    run = client.list_messages(ledger, rung=RungId.L1, query="from:ana", widening_affordance=WIDEN)

    assert run.ids_recorded == 3
    assert ledger.hit_ids == {"18f0a1", "18f0a2", "18f0a3"}
    for value in vars(run).values():
        assert not isinstance(value, str) or value not in ledger.hit_ids


def test_no_public_method_of_the_client_yields_an_id_collection() -> None:
    """The seam's first obligation, checked by reflection rather than by reading.

    A method that returned `list[str]` would be the whole failure this layer is built to
    make unrepresentable, so the check is mechanical: every public method's return
    annotation is inspected, and the two that carry ids at all (`get_thread`,
    `get_message`) are exactly the two that take a ledger or an id from the caller.
    """
    import inspect

    yields_ids = {"get_thread", "get_message"}
    for name, member in inspect.getmembers(GmailClient, inspect.isfunction):
        if name.startswith("_"):
            continue
        annotation = inspect.signature(member).return_annotation
        rendered = str(annotation)
        assert "list[str]" not in rendered, f"{name} returns a bare id list"
        assert "tuple[str" not in rendered, f"{name} returns a bare id collection"
        if name in yields_ids:
            parameters = set(inspect.signature(member).parameters)
            assert "ledger" in parameters or "message_id" in parameters, name


def test_a_thread_is_recorded_into_H_before_its_content_is_reachable() -> None:
    """Clause H-thr (amendment A2): there is no ordering that reads rows before recording."""
    fake = FakeGmail().queue("threads.get", json_response(200, shapes.THREAD_METADATA))
    client = make_client(fake)
    ledger = DispositionLedger()

    recorded = client.get_thread(ledger, thread_id="t100", rung=RungId.L4)

    assert recorded.ids_recorded == 2
    assert ledger.hit_ids == {"18f0a1", "18f0a2"}
    assert [message.id for message in recorded.thread.messages] == ["18f0a1", "18f0a2"]
    origins = ledger.origins
    assert origins["18f0a1"].clause == "H-thr"
    assert origins["18f0a1"].thread_id == "t100"


def test_the_returned_fetch_stamp_is_the_one_the_observation_sealed() -> None:
    """`RecordedThread.fetched_at` and the seal's stamp are one string, not two `_now()` calls.

    Two calls is what `get_thread` did until round 15, and it made the returned value unusable
    for the one thing it exists for. `Source.fetched_at` is checked against the stamp the
    observation recorded (amendment A6), so an assembler that put this field there got a
    `DispositionInvariantError` naming a difference of microseconds - a failure with nothing
    wrong behind it, on the one path WS-04 needs every time it maps a thread.
    """
    fake = FakeGmail().queue("threads.get", json_response(200, shapes.THREAD_METADATA))
    client = make_client(fake)
    ledger = DispositionLedger()

    recorded = client.get_thread(ledger, thread_id="t100", rung=RungId.L4)

    sealed = ledger.observed_thread_facts["t100"].fetched_at
    assert sealed is not None
    assert recorded.fetched_at == sealed


def test_thread_positions_are_chronological_not_array_order() -> None:
    """Amendment A3: a position is an index into `internalDate` order (AD A.2 step 4)."""
    fake = FakeGmail().queue("threads.get", json_response(200, shapes.THREAD_OUT_OF_ARRAY_ORDER))
    client = make_client(fake)
    ledger = DispositionLedger()

    recorded = client.get_thread(ledger, thread_id="t400", rung=RungId.L4)

    assert recorded.scalars_observed is True
    assert ledger.origins["m-earlier"].position == 0
    assert ledger.origins["m-later"].position == 1


def test_a_thread_without_internal_dates_seals_no_positions_and_says_why() -> None:
    """PF-2's pessimistic shape: nothing is invented and the absence is reported.

    This is the branch that would be tempting to paper over by falling back to array order.
    It is not taken: a per-id map on a sealed observation must be total or absent, and an
    invented chronology is exactly the fabrication this project exists to prevent.
    """
    fake = FakeGmail().queue(
        "threads.get", json_response(200, shapes.THREAD_METADATA_NO_INTERNAL_DATE)
    )
    client = make_client(fake)
    ledger = DispositionLedger()

    recorded = client.get_thread(ledger, thread_id="t100", rung=RungId.L4)

    assert recorded.scalars_observed is False
    assert recorded.scalars_absent_because is not None
    assert "internalDate" in recorded.scalars_absent_because
    assert ledger.origins["18f0a1"].position is None
    assert ledger.hit_ids == {"18f0a1", "18f0a2"}


def test_history_additions_enter_H_under_the_history_clause_and_deduplicate() -> None:
    fake = FakeGmail().queue("history.list", json_response(200, shapes.HISTORY_PAGE))
    client = make_client(fake)
    ledger = DispositionLedger()

    run = client.history_additions(ledger, start_history_id="99120049")

    assert run.rebaseline_required is False
    assert run.latest_history_id == "99120051"
    assert ledger.hit_ids == {"18f0b1", "18f0b2"}
    assert ledger.origins["18f0b1"].clause == "H-hist"


def test_an_expired_history_watermark_is_a_declared_rebaseline_not_an_exception() -> None:
    """[VERIFIED RO F6] + AD D.9: the 404 is reported, never silent and never a failure."""
    fake = FakeGmail().queue("history.list", json_response(404, shapes.HISTORY_EXPIRED_404))
    client = make_client(fake)
    ledger = DispositionLedger()

    run = client.history_additions(ledger, start_history_id="1")

    assert run.rebaseline_required is True
    assert run.ids_recorded == 0
    assert ledger.hit_ids == frozenset()


def test_a_history_page_does_not_stamp_its_mailbox_history_id_onto_a_thread() -> None:
    """The `historyId` of a `history.list` page is the mailbox's, not any thread's.

    The seal folds a sealed `history_id` into the *thread* facts of every id it carries, so
    sealing the page-level value here would state that thread `t500` has `historyId`
    99120051 - a fact no response asserted, and one that would then collide with the real
    value the first time a `threads.get` observed it.
    """
    fake = FakeGmail().queue("history.list", json_response(200, shapes.HISTORY_PAGE))
    client = make_client(fake)
    ledger = DispositionLedger()

    client.history_additions(ledger, start_history_id="99120049")

    assert ledger.observed_thread_facts["t500"].history_id is None


# --- pagination ---------------------------------------------------------------------------


def test_the_page_budget_stops_the_walk_and_the_residue_is_declared() -> None:
    fake = FakeGmail().queue("messages.list", json_response(200, shapes.MESSAGES_LIST_PAGE_1))
    client = make_client(fake)
    ledger = DispositionLedger()

    run = client.list_messages(ledger, rung=RungId.L1, query="from:ana", widening_affordance=WIDEN)

    assert MAX_PAGES_PER_QUERY == 1
    assert run.pages_fetched == 1
    assert run.more_pages is True
    assert run.page_budget_stopped_the_walk is True
    assert run.next_page_token == "07840618541123456789"
    assert run.scan_scope[0].affordance == WIDEN


def test_a_widened_budget_walks_pages_and_stops_when_gmail_does() -> None:
    fake = FakeGmail().queue(
        "messages.list",
        json_response(200, shapes.MESSAGES_LIST_PAGE_1),
        json_response(200, shapes.MESSAGES_LIST_PAGE_2),
    )
    client = make_client(fake)
    ledger = DispositionLedger()

    run = client.list_messages(
        ledger, rung=RungId.L1, query="from:ana", widening_affordance=WIDEN, max_pages=5
    )

    assert run.pages_fetched == 2
    assert run.more_pages is False
    assert run.ids_recorded == 4
    assert [entry.pages_fetched for entry in run.scan_scope] == [1, 2]
    assert fake.query_of(1)["pageToken"] == "07840618541123456789"


def test_the_page_size_is_sent_explicitly_and_is_what_scan_scope_reports() -> None:
    """GMAIL-04: `maxResults` is set, not defaulted, so `page_size` describes a real call."""
    fake = FakeGmail().queue("messages.list", json_response(200, shapes.MESSAGES_LIST_EMPTY))
    client = make_client(fake)
    ledger = DispositionLedger()

    run = client.list_messages(
        ledger, rung=RungId.L1, query="x", widening_affordance=WIDEN, page_size=37
    )

    assert fake.query_of(0)["maxResults"] == "37"
    assert run.scan_scope[0].page_size == 37
    assert DEFAULT_PAGE_SIZE == 100


def test_result_size_estimate_is_never_read() -> None:
    """RO F1 / GMAIL-04: `more_pages` comes from the continuation token, never the estimate.

    The fixture's estimate says 42 and the page carries no `nextPageToken`, so a client that
    believed the estimate would report more pages. It does not.
    """
    fake = FakeGmail().queue("messages.list", json_response(200, shapes.MESSAGES_LIST_PAGE_2))
    client = make_client(fake)
    ledger = DispositionLedger()

    run = client.list_messages(ledger, rung=RungId.L1, query="x", widening_affordance=WIDEN)

    assert run.more_pages is False
    # And nothing in the server tree *reads* the field. Checked with `ast` rather than with
    # a substring search, because the client's own comment explaining why it is unread would
    # fail a substring search - a grep cannot tell prose from code, which is the rule the
    # repository's guards are built on.
    import ast

    reads: list[str] = []
    for path in sorted(Path("server/src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "result_size_estimate":
                reads.append(f"{path}:{node.lineno}")
    assert reads == []


def test_a_listing_without_a_widening_affordance_cannot_be_started() -> None:
    """The check is a precondition, not a post-hoc raise, and that ordering is the point.

    `ScanScopeEntry` refuses `more_pages: true` with no affordance - but it refuses at record
    time, by which point `_admit` has already put the page's ids into `H`. Requiring the
    affordance in the signature moves the refusal before the HTTP call, so there is no state
    in which ids sit in `H` with no scan-scope entry describing how they arrived.
    """
    fake = FakeGmail().queue("messages.list", json_response(200, shapes.MESSAGES_LIST_PAGE_1))
    client = make_client(fake)
    ledger = DispositionLedger()

    with pytest.raises(TypeError):
        client.list_messages(ledger, rung=RungId.L1, query="x")  # type: ignore[call-arg]
    assert fake.requests == []


# --- retry, backoff, and the counters -----------------------------------------------------


def test_the_delay_sequence_is_exactly_the_architecture_s(monkeypatch: Any) -> None:
    """Base 250 ms, factor 2, jitter +/-25 %, deterministic under an injected jitterer."""
    slept: list[float] = []
    fake = FakeGmail().queue(
        "messages.list",
        json_response(429, shapes.error_body(429, "rateLimitExceeded")),
        json_response(429, shapes.error_body(429, "rateLimitExceeded")),
        json_response(200, shapes.MESSAGES_LIST_PAGE_2),
    )
    # jitter() == 1.0 is the top of the band: delay = exponential * 1.25.
    client = make_client(fake, slept=slept, jitter=1.0)
    ledger = DispositionLedger()

    client.list_messages(ledger, rung=RungId.L1, query="x", widening_affordance=WIDEN)

    assert [round(value * 1000, 3) for value in slept] == [312.5, 625.0]


def test_every_attempt_is_charged_including_the_one_that_429d() -> None:
    """AD A.5a: the upstream quota was spent on the refused attempt too."""
    fake = FakeGmail().queue(
        "messages.list",
        json_response(429, shapes.error_body(429, "rateLimitExceeded")),
        json_response(200, shapes.MESSAGES_LIST_PAGE_2),
    )
    client = make_client(fake, slept=[])
    ledger = DispositionLedger()

    client.list_messages(ledger, rung=RungId.L1, query="x", widening_affordance=WIDEN)

    reading = client.meter.reading()
    assert reading.http_requests == 2
    assert reading.api_calls == 2
    assert reading.quota_units_diagnostic == 10  # 2 x 5 u, published table
    assert "PF-3 not yet run" in reading.calibration


def test_the_two_counters_are_not_the_same_number(monkeypatch: Any) -> None:
    """ADV-106: `http_requests` and `api_calls` are separate increments, so a batcher can
    move one without the other. Today they agree; the meter's shape is what keeps them
    separable when it does not."""
    meter = CallMeter()
    meter.record_attempt(GmailEndpoint.MESSAGES_GET, sub_requests=10)
    reading = meter.reading()
    assert reading.http_requests == 1
    assert reading.api_calls == 10
    assert reading.quota_units_diagnostic == 200


def test_the_total_backoff_bound_binds_before_the_retry_count_does() -> None:
    """Worth stating: `max_retries = 3` is not reachable at the top of the jitter band.

    250 + 500 = 750 ms of sleeping leaves 750 ms of the 1,500 ms total, and the third delay
    is 1,000 ms before jitter. So with unfavourable jitter the client makes **two** retries,
    not three, and the tighter of A.5a's two bounds is the one that fires. That is the
    architecture's own arithmetic rather than a defect, and it is asserted so nobody later
    reads `max_retries = 3` as a promise of three.
    """
    slept: list[float] = []
    fake = FakeGmail()
    for _ in range(6):
        fake.queue("messages.list", json_response(503, shapes.error_body(503, "backendError")))
    client = make_client(fake, slept=slept, jitter=1.0)
    ledger = DispositionLedger()

    with pytest.raises(GmailUnavailable) as raised:
        client.list_messages(ledger, rung=RungId.L1, query="x", widening_affordance=WIDEN)

    assert len(slept) == 2
    assert raised.value.attempts == 3
    assert sum(slept) * 1000 <= 1500


def test_a_rung_with_less_clock_than_the_backoff_bound_gets_the_tighter_bound() -> None:
    slept: list[float] = []
    fake = FakeGmail()
    for _ in range(4):
        fake.queue("messages.list", json_response(503, shapes.error_body(503, "backendError")))
    client = make_client(fake, slept=slept, jitter=0.5)
    ledger = DispositionLedger()

    with pytest.raises(GmailUnavailable):
        client.list_messages(
            ledger, rung=RungId.L1, query="x", widening_affordance=WIDEN, remaining_ms=200.0
        )

    assert slept == []  # 250 ms does not fit in 200 ms of remaining rung clock


def test_retry_after_raises_the_delay_and_never_lowers_it() -> None:
    slept: list[float] = []
    fake = FakeGmail().queue(
        "messages.list",
        json_response(
            429, shapes.error_body(429, "rateLimitExceeded"), headers={"retry-after": "1"}
        ),
        json_response(200, shapes.MESSAGES_LIST_PAGE_2),
    )
    client = make_client(fake, slept=slept, jitter=0.5)
    ledger = DispositionLedger()

    client.list_messages(ledger, rung=RungId.L1, query="x", widening_affordance=WIDEN)

    assert slept == [1.0]  # the header's second, not the 250 ms schedule


def test_a_403_that_names_a_quota_reason_is_a_rate_limit_not_an_auth_failure() -> None:
    """Gmail has answered per-user rate limits with 403; reading it as auth would send the
    owner to re-consent for a condition a sleep fixes. Which status a real mailbox emits is
    PF-3's to record."""
    fake = FakeGmail()
    for _ in range(4):
        fake.queue(
            "messages.list",
            json_response(403, shapes.error_body(403, "userRateLimitExceeded")),
        )
    client = make_client(fake, slept=[], jitter=0.0)
    ledger = DispositionLedger()

    with pytest.raises(GmailRateLimited) as raised:
        client.list_messages(ledger, rung=RungId.L1, query="x", widening_affordance=WIDEN)

    assert raised.value.reason == "userRateLimitExceeded"
    assert raised.value.code is ErrorCode.UPSTREAM_RATE_LIMITED


def test_a_403_without_a_quota_reason_is_an_auth_failure_with_the_reauth_wording() -> None:
    """GMAIL-06: token failure is a clear re-auth instruction, never a retrieval error."""
    fake = FakeGmail().queue(
        "messages.list", json_response(403, shapes.error_body(403, "insufficientPermissions"))
    )
    client = make_client(fake)
    ledger = DispositionLedger()

    with pytest.raises(GmailAuthExpired) as raised:
        client.list_messages(ledger, rung=RungId.L1, query="x", widening_affordance=WIDEN)

    assert "mailweave auth login" in str(raised.value)
    assert raised.value.code is ErrorCode.AUTH_REAUTH_REQUIRED


# --- faults -------------------------------------------------------------------------------


def test_every_failure_path_raises_a_gmail_fault() -> None:
    """One `except GmailFault` catches everything this layer can produce."""
    cases: list[tuple[FakeGmail, type[GmailFault]]] = [
        (
            FakeGmail().queue("profile", json_response(400, shapes.LEAKY_ERROR_BODY)),
            GmailRequestRejected,
        ),
        (
            FakeGmail().queue("profile", json_response(401, shapes.error_body(401, "authError"))),
            GmailAuthExpired,
        ),
    ]
    for fake, expected in cases:
        client = make_client(fake, slept=[])
        with pytest.raises(expected) as raised:
            client.get_profile()
        assert isinstance(raised.value, GmailFault)
        assert raised.value.endpoint is GmailEndpoint.GET_PROFILE


def test_a_transport_error_arrives_as_a_gmail_fault_not_as_an_httpx_one() -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    http = build_client(inner=httpx.MockTransport(explode))
    client = GmailClient(token=StaticToken(TOKEN), http=http, sleeper=lambda _: None)

    with pytest.raises(GmailTransportFailure) as raised:
        client.get_profile()
    assert isinstance(raised.value, GmailFault)


def test_every_fault_code_is_a_real_d11_code_on_the_right_side_of_the_partition() -> None:
    """A fault whose code sits on the wrong surface would be rendered in the wrong place."""
    expected = {
        GmailAuthExpired: Surface.TOOL_ERROR,
        GmailRateLimited: Surface.IN_BAND,
        GmailUnavailable: Surface.TOOL_ERROR,
        GmailRequestRejected: Surface.IN_BAND,
        GmailTransportFailure: Surface.TOOL_ERROR,
        GmailResponseUnexpected: Surface.IN_BAND,
    }
    for fault, surface in expected.items():
        assert ERROR_SURFACE[fault.code] is surface


def test_no_part_of_a_gmail_error_body_reaches_a_mailweave_error_string() -> None:
    """AD A.11: no mail-derived text, and no query text, in any error, log or trace.

    The fixture's `error.message` echoes a `q` containing a sentence. None of it - not the
    sentence, not the address, not the word `NDA` - may appear in what MailWeave raises.
    """
    fake = FakeGmail().queue("messages.list", json_response(400, shapes.LEAKY_ERROR_BODY))
    client = make_client(fake)
    ledger = DispositionLedger()

    with pytest.raises(GmailRequestRejected) as raised:
        client.list_messages(
            ledger,
            rung=RungId.L1,
            query='from:ana "the NDA we discussed"',
            widening_affordance=WIDEN,
        )

    rendered = f"{raised.value!r} {raised.value!s} {raised.value.args!r}"
    for forbidden in ("NDA", "Tuesday", "ana@one.example", "Invalid query"):
        assert forbidden not in rendered
    assert raised.value.reason == "invalidArgument"


def test_no_access_token_appears_in_any_rendering_of_the_client_or_its_faults() -> None:
    """RR SEC-04: a credential in a traceback is a credential leaked."""
    fake = FakeGmail().queue("profile", json_response(500, shapes.error_body(500, "backendError")))
    client = make_client(fake, slept=[])

    with pytest.raises(GmailUnavailable) as raised:
        client.get_profile()

    surfaces = [repr(client), repr(StaticToken(TOKEN)), str(raised.value), repr(raised.value)]
    for surface in surfaces:
        assert TOKEN not in surface
        assert "SECRET" not in surface


def test_a_substituted_message_id_is_refused() -> None:
    """`messages.get` is not a sealed observation, so this is the only check on its id."""
    fake = FakeGmail().queue("messages.get", json_response(200, shapes.MESSAGE_FULL))
    client = make_client(fake)

    with pytest.raises(GmailResponseUnexpected):
        client.get_message("a-different-id")


def test_a_malformed_response_is_a_typed_error_not_a_pydantic_one() -> None:
    fake = FakeGmail().queue("threads.get", json_response(200, {"id": 17}))
    client = make_client(fake)
    ledger = DispositionLedger()

    with pytest.raises(GmailResponseMalformed) as raised:
        client.get_thread(ledger, thread_id="t100", rung=RungId.L4)
    assert "users.threads.get" in str(raised.value)
    assert "17" not in str(raised.value)


def test_a_200_that_is_not_json_is_a_typed_error_carrying_no_body() -> None:
    fake = FakeGmail().queue(
        "profile", httpx.Response(200, content=b"<html>rate limited by a proxy</html>")
    )
    client = make_client(fake)

    with pytest.raises(GmailResponseMalformed) as raised:
        client.get_profile()
    assert "rate limited by a proxy" not in str(raised.value)


# --- egress -------------------------------------------------------------------------------


def test_every_call_goes_to_the_allowlisted_host_over_https() -> None:
    fake = FakeGmail().queue("profile", json_response(200, shapes.PROFILE))
    client = make_client(fake)

    client.get_profile()

    url = fake.requests[0].url
    assert url.scheme == "https"
    assert url.host == GMAIL_API_HOST


def test_a_mock_transport_is_still_behind_the_allowlist() -> None:
    """`build_client(inner=...)` swaps the socket, not the check.

    If it swapped the check, every test in this file would be testing a client that has no
    allowlist - which is the way an injected-transport test suite quietly stops proving the
    property it was written for.
    """
    fake = FakeGmail()
    http = build_client(inner=fake.transport())
    with pytest.raises(Exception) as raised:
        http.get("https://evil.example/gmail/v1/users/me/profile")
    assert "egress" in str(raised.value).lower() or "allowlist" in str(raised.value).lower()
    assert fake.requests == []


def test_the_thread_map_sends_every_metadata_header_as_a_repeated_key() -> None:
    """A dict cannot express a repeated query key, and getting it wrong is silent."""
    from mailweave.gmail import THREAD_MAP_HEADERS

    fake = FakeGmail().queue("threads.get", json_response(200, shapes.THREAD_METADATA))
    client = make_client(fake)
    ledger = DispositionLedger()

    client.get_thread(ledger, thread_id="t100", rung=RungId.L4)

    sent = fake.requests[0].url.params.get_list("metadataHeaders")
    assert sent == list(THREAD_MAP_HEADERS)
    assert "References" in sent and "In-Reply-To" in sent


# --- R-SEC-051: the two mailbox-scope settings meet here, and may not disagree ---------------


def _listing(client: GmailClient, **kwargs: Any) -> None:
    client.list_messages(DispositionLedger(), rung=RungId.L1, widening_affordance=WIDEN, **kwargs)


@pytest.mark.parametrize(
    "spelling",
    [
        "in:anywhere",
        f"in:{'anywhere'}",
        "in:" + "anywhere",
        "in:{}".format("anywhere"),
        "from:ana in:anywhere",
        "in:spam",
        "in:trash",
        "IN:ANYWHERE",
        "In:Anywhere",
        "from:ana IN:SPAM",
    ],
)
def test_a_widened_query_without_the_flag_never_reaches_the_wire(spelling: str) -> None:
    """The four call shapes R-SEC-051 found, plus the ones they generalise to.

    All of them evade both AST sweeps - the flag is simply omitted, or the operator is built by
    an f-string, a concatenation or `.format`, none of which is an `ast.Constant`. Each put
    `q=in:anywhere` on the wire with `includeSpamTrash=false`: the exact disagreement
    `MailboxScope` exists to make impossible, sampling a mailbox neither setting describes.

    The check is where the request parameters are built, so by then there is no spelling left
    to evade - only a string.

    **The last three are a fifth evasion, and it was live until this round.** The guard matched
    the operators exactly, so `IN:ANYWHERE` - Gmail's operators are case-insensitive - passed
    the pairing check and reached the wire beside `includeSpamTrash=false`. Found by the
    round-13 implementer checking whether the claim beside the operator table was true of the
    code rather than by re-reading the claim.

    Nothing reaches the transport in any case: the refusal is before the call.
    """
    fake = FakeGmail().queue("messages.list", json_response(200, shapes.MESSAGES_LIST_PAGE_1))
    client = make_client(fake)

    with pytest.raises(ValueError) as raised:
        _listing(client, query=spelling)

    assert "includeSpamTrash" in str(raised.value)
    assert fake.requests == [], "the disagreeing pair reached the transport"


def test_the_flag_without_a_widened_query_is_refused_the_same_way() -> None:
    """The inverse mistake is the same defect: two settings, one mailbox, and no agreement.

    `includeSpamTrash=true` beside a default-scope `q` samples something neither describes just
    as surely, and a check that only refused one direction would be a check that had picked a
    favourite rather than one that enforces the pairing.
    """
    fake = FakeGmail().queue("messages.list", json_response(200, shapes.MESSAGES_LIST_PAGE_1))
    client = make_client(fake)

    with pytest.raises(ValueError):
        _listing(client, query="from:ana", include_spam_trash=True)
    assert fake.requests == []


@pytest.mark.parametrize(
    ("query", "include_spam_trash"),
    [
        ("-in:spam -in:trash", False),
        ("in:anywhere", True),
        ("from:ana", False),
        ("rfc822msgid:abc@example.invalid", False),
        ("in:inbox from:ana", False),
        ('"in:anywhere"', False),
        ("in:spammers", False),
        ("-IN:SPAM -IN:TRASH", False),
        ("IN:ANYWHERE", True),
    ],
)
def test_an_agreeing_pair_goes_through_unchanged(query: str, include_spam_trash: bool) -> None:
    """The refusal must not close the door on the calls this project actually makes.

    Both `MailboxScope` spellings, the freshness probe's id-exact search, an ordinary location
    operator, a *quoted* `in:anywhere` (a phrase search, not an operator), and a word that
    merely starts with one. The last two are why the check is token-wise rather than a
    substring scan: `"in:spammers"` is a search for a sender, not a request for spam.

    The last two rows are the case-folding's other half: folding may only refuse a
    *disagreeing* pair, so an agreeing one written in capitals - in either direction - still
    goes through untouched, and the query reaches the wire exactly as it was written.
    """
    fake = FakeGmail().queue("messages.list", json_response(200, shapes.MESSAGES_LIST_PAGE_1))
    client = make_client(fake)

    _listing(client, query=query, include_spam_trash=include_spam_trash)

    params = fake.query_of(0)
    assert params["q"] == query
    assert params.get("includeSpamTrash", "absent") == ("true" if include_spam_trash else "absent")
