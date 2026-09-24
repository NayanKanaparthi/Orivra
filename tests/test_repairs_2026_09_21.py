"""The four bounded repairs of 2026-09-21, each held through the shipped tool boundary.

Five exploratory runs on the Desktop surface produced two defects confirmed in source and
one finding about the wire, and the repairs here are exactly those and nothing wider:

  1. **The request deadline is enforced**, across the HTTP request, its retries and every
     sequential fetch of a read - not only the sleeps between retries, which was all
     `max_server_ms` bounded before. A stalled request or a long read now ends at the
     allowance with a decline that carries a strictly narrower retry.
  2. **A Gmail fault's decline says what can be done about it.** Every typed fault used to
     decline as `retry_with: null, terminal: false`; now `terminal` is read off the fault's
     type and a `recovery` token says which of four things the caller can do. A 404 on an
     identifier is final and names the endpoint; it does not probe whether the identifier
     is a thread and does not say so.
  3. **Every row says who its `From` header named and when Gmail received it**, with the
     provenance of both stated on the row - so a reader is not left to read attribution
     out of body text, and does not read an absent key as "no timestamps".
  4. **A call's lifecycle is recorded, opt-in**, on both surfaces: a start line and an end
     line per call, shapes of arguments and never their values.

And the two gaps the first four left, closed the same day (sections 5 and 6):

  5. **The deadline holds at the socket.** A body that trickles inside every read window, and
     a token exchange that runs before the first attempt, both walked past the allowance the
     per-attempt timeout enforced. Now every socket operation is clamped to what is left of
     the call (`net/deadline.py`), driven here through the real `httpx`/`httpcore` stack over a
     scripted socket on a real clock; the end line records the allowance and the overrun, and
     `tools/dev/check_calls.py` refuses a late decline whatever its outcome.
  6. **The diagnostic names nothing the server does not publish.** The start line is written
     before validation, so a key or a string the caller sent is not content it may carry: keys
     are named only when the tool's schema publishes them, strings only when the schema
     publishes an enum the value belongs to.

Every test here drives `mailweave.surface.server.call` (or Orivra's `call`, which reaches
the same partition) over the shipped client and `httpx.MockTransport`: the socket is the
only thing replaced.
"""

from __future__ import annotations

import json
import socket
import ssl
import stat
import tempfile
import time
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpcore
import httpx
import pytest
from httpcore._backends.sync import SyncStream

from mailweave import diagnostics
from mailweave.constants import MAX_SERVER_MS
from mailweave.diagnostics import Lifecycle, shape_of, surface_of
from mailweave.envelope.wire import Attribution, AttributionProvenance, MessageRow
from mailweave.errors import EgressBlocked, ErrorCode
from mailweave.gmail import StaticToken
from mailweave.gmail.client import GmailClient, TokenProvider
from mailweave.gmail.faults import (
    GmailAuthExpired,
    GmailDeadlineExceeded,
    GmailRateLimited,
    GmailRequestRejected,
    GmailResponseUnexpected,
    GmailTransportFailure,
    GmailUnavailable,
    RecoveryKind,
)
from mailweave.gmail.meter import CallMeter
from mailweave.gmail.retry import MIN_ATTEMPT_MS, BackoffPolicy, Deadline
from mailweave.handles.cache import ThreadMapCache
from mailweave.handles.keys import HandleKey
from mailweave.net.deadline import bounded_transport, installed_backend
from mailweave.net.egress import AllowlistTransport, build_client
from mailweave.surface import service as service_module
from mailweave.surface.partition import RECOVERY_TOKENS, REFUSAL_KEYS
from mailweave.surface.server import call
from mailweave.surface.service import MailweaveService
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.test_mcp_surface_round24 import ACCOUNT, MARKER, TOKEN, mailbox

# --- a service whose clock and socket are both the test's ---------------------------------


class FakeClock:
    """A monotonic clock the transport advances, so a 'slow' request costs no wall time."""

    def __init__(self) -> None:
        self.now_ms = 1_000.0

    def __call__(self) -> float:
        return self.now_ms

    def advance(self, ms: float) -> None:
        self.now_ms += ms


class Wire:
    """A transport over the synthetic mailbox that can stall, fail, and record."""

    def __init__(self, box: SyntheticMailbox, clock: FakeClock) -> None:
        self.box = box
        self.clock = clock
        self.requests: list[httpx.Request] = []
        self.timeouts: list[float | None] = []
        self.remaining_at_request: list[float] = []
        self.deadline: Deadline | None = None
        #: (path fragment -> ms) advance the clock this much per matching request.
        self.stall: dict[str, float] = {}
        #: (path fragment -> status) answer matching requests with this status instead.
        self.status: dict[str, int] = {}
        #: (path fragment -> exception) raise this from the transport instead.
        self.raises: dict[str, Exception] = {}
        self.matched = 0

    def _read_timeout(self, request: httpx.Request) -> float | None:
        timeout = request.extensions.get("timeout")
        if not isinstance(timeout, dict):
            return None
        return timeout.get("read")

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.timeouts.append(self._read_timeout(request))
        if self.deadline is not None:
            self.remaining_at_request.append(self.deadline.remaining_ms())
        path = request.url.path
        for fragment, ms in self.stall.items():
            if fragment in path:
                self.matched += 1
                self.clock.advance(ms)
        for fragment, failure in self.raises.items():
            if fragment in path:
                raise failure
        for fragment, status in self.status.items():
            if fragment in path:
                return httpx.Response(status, json={"error": {"code": status, "status": "X"}})
        return self.box.handler(request)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def make(
    box: SyntheticMailbox, wire: Wire, clock: FakeClock, *, sleeper: Callable[[float], None]
) -> MailweaveService:
    def open_client() -> GmailClient:
        client = GmailClient(
            token=StaticToken(TOKEN),
            http=build_client(inner=wire.transport()),
            meter=CallMeter(),
            policy=BackoffPolicy(),
            sleeper=sleeper,
            jitterer=lambda: 0.5,
        )
        return client

    service = MailweaveService(
        open_client=open_client,
        account_hash=ACCOUNT,
        handle_key=HandleKey(material=b"k" * 32, epoch=0),
        cache=ThreadMapCache(),
        now=lambda: datetime.now(UTC),
        clock_ms=clock,
    )
    # The deadline the service binds is what the wire measures against.
    original = service._open_client_for_call

    def opened(budget_ms: float | None = None) -> GmailClient:
        client = original(budget_ms)
        wire.deadline = client.deadline
        return client

    service._open_client_for_call = opened  # type: ignore[method-assign]
    return service


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def box() -> SyntheticMailbox:
    return mailbox()


@pytest.fixture
def wire(box: SyntheticMailbox, clock: FakeClock) -> Wire:
    return Wire(box, clock)


@pytest.fixture
def slept() -> list[float]:
    return []


@pytest.fixture
def service(
    box: SyntheticMailbox, wire: Wire, clock: FakeClock, slept: list[float]
) -> MailweaveService:
    def sleeper(seconds: float) -> None:
        slept.append(seconds * 1000.0)
        clock.advance(seconds * 1000.0)

    return make(box, wire, clock, sleeper=sleeper)


def structured(result: Any) -> dict[str, Any]:
    assert isinstance(result.structured_content, dict)
    return result.structured_content


def text_of(result: Any) -> str:
    return "\n".join(block.text for block in result.content if hasattr(block, "text"))


def vendor_ids(service: MailweaveService) -> list[str]:
    found = structured(call(service, "mailweave_search", {"query": f'"{MARKER}"'}))
    return [row["id"] for source in found["sources"] for row in source["messages"]]


# --- 1. the deadline ------------------------------------------------------------------------


def test_a_sequential_read_stops_at_the_allowance_and_declines_with_a_narrower_read(
    service: MailweaveService, wire: Wire, clock: FakeClock
) -> None:
    """Four `body_full` messages, each costing 3 s on the wire, against a 7.7 s allowance.

    Before: four fetches ran to completion whatever they cost, because nothing on the read
    path had a clock. Now the third `messages.get` is not started - the allowance is spent -
    and the call declines `budget_exhausted` with the same messages at a shallower view as
    its retry, which is a strictly cheaper request.
    """
    ids = vendor_ids(service)[:4]
    assert len(ids) == 4
    wire.requests.clear()
    wire.stall = {"/messages/": 3_000.0}
    result = call(service, "mailweave_get_messages", {"message_ids": ids, "view": "body_full"})
    assert result.is_error, text_of(result)
    refusal = structured(result)
    assert refusal["code"] == ErrorCode.BUDGET_EXHAUSTED.value
    assert refusal["recovery"] == "narrow"
    assert refusal["terminal"] is False
    assert refusal["retry_with"] is not None
    assert refusal["retry_with"]["tool"] == "mailweave_get_messages"
    assert refusal["retry_with"]["args"]["view"] == "body_clean"
    assert refusal["narrowing"]["dimension"] == "view"
    # The wire saw fewer message fetches than were asked for: the deadline stopped the loop.
    fetched = [r for r in wire.requests if "/messages/" in r.url.path]
    assert 1 <= len(fetched) < 4, [r.url.path for r in wire.requests]
    assert "allowance" in refusal["remediation"]


def test_every_attempt_carries_a_timeout_no_larger_than_what_is_left(
    service: MailweaveService, wire: Wire
) -> None:
    """The per-request timeout is the smaller of the client ceiling and the remaining
    allowance, on every request of the call - not the client's 30 s on each."""
    ids = vendor_ids(service)[:2]
    wire.requests.clear()
    wire.timeouts.clear()
    wire.remaining_at_request.clear()
    wire.stall = {"/messages/": 2_000.0}
    call(service, "mailweave_get_messages", {"message_ids": ids, "view": "body_clean"})
    assert wire.timeouts, "no request reached the wire"
    for timeout, left in zip(wire.timeouts, wire.remaining_at_request, strict=True):
        assert timeout is not None, "a bound deadline must set a per-request timeout"
        assert timeout <= 30.0
        assert timeout * 1000.0 <= left + 1.0, (timeout, left)
    # And it shrinks as the allowance is spent.
    first, last = wire.timeouts[0], wire.timeouts[-1]
    assert first is not None and last is not None and last < first


def test_a_transport_timeout_past_the_deadline_is_reported_as_the_deadline(
    service: MailweaveService, wire: Wire, clock: FakeClock
) -> None:
    """A read timeout that fires because the deadline bounded it is the deadline's fault,
    not a transport failure to be retried three more times."""
    ids = vendor_ids(service)[:1]
    wire.requests.clear()

    def stall_then_time_out(request: httpx.Request) -> httpx.Response:
        wire.requests.append(request)
        if "/messages/" in request.url.path:
            clock.advance(MAX_SERVER_MS)
            raise httpx.ReadTimeout("read timed out", request=request)
        return wire.box.handler(request)

    service_wire = httpx.MockTransport(stall_then_time_out)
    original_open = service.open_client

    def open_client() -> GmailClient:
        client = original_open()
        client._http = build_client(inner=service_wire)
        return client

    service.open_client = open_client
    result = call(service, "mailweave_get_messages", {"message_ids": ids, "view": "body_clean"})
    assert result.is_error
    refusal = structured(result)
    assert refusal["code"] == ErrorCode.BUDGET_EXHAUSTED.value
    assert "did not complete inside the call's wall-clock allowance" in refusal["remediation"]
    attempts = [r for r in wire.requests if "/messages/" in r.url.path]
    assert len(attempts) == 1, "no retry after the deadline cut the request"


def test_retry_sleeps_are_bounded_by_the_live_allowance(
    service: MailweaveService, wire: Wire, clock: FakeClock, slept: list[float]
) -> None:
    """A 503 is retried, and each sleep is bounded by what is left *now*, not by what was
    left when the request began. With the allowance nearly spent there is no sleep at all:
    the retry budget reports itself spent and the 503 is declined as the upstream condition
    it was - `retry_later`, not final - having slept into nothing."""
    ids = vendor_ids(service)[:1]
    slept.clear()
    wire.status = {"/messages/": 503}
    wire.stall = {"/messages/": MAX_SERVER_MS - MIN_ATTEMPT_MS - 10.0}
    result = call(service, "mailweave_get_messages", {"message_ids": ids, "view": "body_clean"})
    assert result.is_error
    refusal = structured(result)
    assert refusal["code"] == ErrorCode.UPSTREAM_UNAVAILABLE.value
    assert refusal["recovery"] == "retry_later"
    assert not slept, f"slept {slept} ms with the allowance spent"
    # And with room, the sleeps happen and each one fits inside what was left.
    slept.clear()
    wire.stall = {}
    call(service, "mailweave_get_messages", {"message_ids": ids, "view": "body_clean"})
    assert slept, "a 503 with room is retried with a backoff"
    assert all(0 < pause <= MAX_SERVER_MS for pause in slept)


def test_a_thread_map_with_no_narrower_form_declines_retry_later_not_terminal(
    service: MailweaveService, wire: Wire
) -> None:
    """One `threads.get` has no narrower request, so the decline says the same call may
    succeed later and that it is not final - rather than `retry_with: null` and silence."""
    # The profile read that precedes every map spends the allowance, so the one
    # `threads.get` is refused before it starts: the mock transport cannot be interrupted,
    # so the boundary is exercised at the attempt that follows a spent clock.
    wire.stall = {"/profile": MAX_SERVER_MS + 1.0}
    result = call(service, "mailweave_thread_map", {"thread_id": "t-vendor"})
    assert result.is_error
    refusal = structured(result)
    assert refusal["code"] == ErrorCode.BUDGET_EXHAUSTED.value
    assert refusal["recovery"] == "retry_later"
    assert refusal["terminal"] is False
    assert refusal["retry_with"] is None
    assert "not a final refusal" in refusal["remediation"]


def test_a_search_is_bounded_by_both_published_clocks_together(
    service: MailweaveService, wire: Wire
) -> None:
    """The search's allowance is `max_server_ms + max_semantic_ms`: the accountant charges
    semantic work to the second without charging the first, so the network deadline is the
    sum a caller was told the call could take."""
    call(service, "mailweave_search", {"query": f'"{MARKER}"'})
    assert wire.deadline is not None
    from mailweave.constants import MAX_SEMANTIC_MS

    assert wire.deadline.budget_ms == float(MAX_SERVER_MS + MAX_SEMANTIC_MS)


def test_a_client_with_no_deadline_bound_keeps_the_client_default_timeout(
    box: SyntheticMailbox,
) -> None:
    """The CLI's one-shot calls and the preflight probes bind none, and behave as before."""
    seen: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions.get("timeout"))
        return box.handler(request)

    client = GmailClient(
        token=StaticToken(TOKEN),
        http=build_client(inner=httpx.MockTransport(handler), timeout=30.0),
        meter=CallMeter(),
        policy=BackoffPolicy(),
        sleeper=lambda _s: None,
        jitterer=lambda: 0.5,
    )
    assert client.deadline is None
    client.get_profile()
    assert seen and seen[0] == {"connect": 30.0, "read": 30.0, "write": 30.0, "pool": 30.0}


def test_the_deadline_refuses_before_an_attempt_that_cannot_finish() -> None:
    clock = FakeClock()
    deadline = Deadline(budget_ms=200.0, clock_ms=clock)
    assert not deadline.expired()
    clock.advance(200.0 - MIN_ATTEMPT_MS + 1.0)
    assert deadline.expired()
    assert deadline.remaining_ms() < MIN_ATTEMPT_MS
    with pytest.raises(ValueError):
        Deadline(budget_ms=0.0, clock_ms=clock)


def test_the_read_allowance_is_the_published_figure_and_a_smaller_one_binds(
    box: SyntheticMailbox, wire: Wire, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`MAX_SERVER_MS` is what a read binds; a process that lowers the constant lowers the
    allowance, which is how a real-clock check of the boundary can be run in seconds."""
    service = make(box, wire, clock, sleeper=lambda _s: None)
    call(service, "mailweave_thread_map", {"thread_id": "t-vendor"})
    assert wire.deadline is not None and wire.deadline.budget_ms == float(MAX_SERVER_MS)
    monkeypatch.setattr(service_module, "MAX_SERVER_MS", 900)
    call(service, "mailweave_thread_map", {"thread_id": "t-vendor"})
    assert wire.deadline is not None and wire.deadline.budget_ms == 900.0


# --- 2. the fault declines ------------------------------------------------------------------


def test_a_404_on_an_identifier_is_final_names_the_endpoint_and_does_not_probe(
    service: MailweaveService, wire: Wire
) -> None:
    """The observed defect. A thread identifier passed as a message identifier 404s; the
    decline is `terminal: true, recovery: none`, names `messages.get`, and says nothing about
    what the identifier might otherwise be. No `threads.get` is attempted to find out."""
    wire.status = {"/messages/": 404}
    wire.requests.clear()
    result = call(
        service, "mailweave_get_messages", {"message_ids": ["t-vendor"], "view": "snippet"}
    )
    assert result.is_error
    refusal = structured(result)
    assert refusal["code"] == ErrorCode.PARTIAL_SOURCE_FAILURE.value
    assert refusal["terminal"] is True
    assert refusal["recovery"] == "none"
    assert refusal["retry_with"] is None
    assert "messages.get" in refusal["remediation"]
    assert "final refusal" in refusal["remediation"]
    assert "thread" not in refusal["remediation"].lower().replace("threads.get", "")
    assert not any("/threads/" in r.url.path for r in wire.requests), "probed the thread"
    # The two sentences no longer run together ("404 This condition ...").
    assert "404 This" not in refusal["remediation"]
    assert "recovery: none" in text_of(result)


def test_a_401_is_final_and_says_the_owner_must_reauthorise(
    service: MailweaveService, wire: Wire
) -> None:
    wire.status = {"/messages/": 401}
    result = call(service, "mailweave_get_messages", {"message_ids": ["v-1"], "view": "snippet"})
    refusal = structured(result)
    assert refusal["code"] == ErrorCode.AUTH_REAUTH_REQUIRED.value
    assert refusal["terminal"] is True
    assert refusal["recovery"] == "reauthorise"
    assert "mailweave auth login" in refusal["remediation"]


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (429, ErrorCode.UPSTREAM_RATE_LIMITED),
        (503, ErrorCode.UPSTREAM_UNAVAILABLE),
    ],
)
def test_a_persisting_upstream_condition_is_retry_later_and_not_final(
    service: MailweaveService, wire: Wire, status: int, code: ErrorCode
) -> None:
    wire.status = {"/messages/": status}
    result = call(service, "mailweave_get_messages", {"message_ids": ["v-1"], "view": "snippet"})
    refusal = structured(result)
    assert refusal["code"] == code.value
    assert refusal["terminal"] is False
    assert refusal["recovery"] == "retry_later"
    assert refusal["retry_with"] is None
    assert "may succeed later" in refusal["remediation"]


def test_a_refused_host_is_final_while_a_dropped_connection_is_not(
    service: MailweaveService, wire: Wire
) -> None:
    wire.raises = {"/messages/": EgressBlocked("host not on the allowlist")}
    result = call(service, "mailweave_get_messages", {"message_ids": ["v-1"], "view": "snippet"})
    refusal = structured(result)
    assert refusal["code"] == ErrorCode.UPSTREAM_UNAVAILABLE.value
    assert refusal["terminal"] is True
    assert refusal["recovery"] == "none"

    wire.raises = {"/messages/": httpx.ConnectError("refused")}
    result = call(service, "mailweave_get_messages", {"message_ids": ["v-1"], "view": "snippet"})
    refusal = structured(result)
    assert refusal["code"] == ErrorCode.UPSTREAM_UNAVAILABLE.value
    assert refusal["terminal"] is False
    assert refusal["recovery"] == "retry_later"


def test_every_fault_type_declares_its_recovery_and_terminal_agrees() -> None:
    """The classification lives on the type, beside the code, so the partition reads it."""
    from mailweave.gmail.rates import GmailEndpoint

    endpoint = GmailEndpoint.MESSAGES_GET
    cases: list[tuple[Any, RecoveryKind, bool]] = [
        (GmailAuthExpired("x", endpoint=endpoint), RecoveryKind.REAUTHORISE, True),
        (GmailRateLimited("x", endpoint=endpoint), RecoveryKind.RETRY_LATER, False),
        (GmailUnavailable("x", endpoint=endpoint), RecoveryKind.RETRY_LATER, False),
        (GmailRequestRejected("x", endpoint=endpoint), RecoveryKind.NONE, True),
        (GmailResponseUnexpected("x", endpoint=endpoint), RecoveryKind.NONE, True),
        (GmailTransportFailure("x", endpoint=endpoint), RecoveryKind.RETRY_LATER, False),
        (
            GmailDeadlineExceeded("x", endpoint=endpoint, budget_ms=1.0, elapsed_ms=1.0),
            RecoveryKind.NARROW,
            False,
        ),
    ]
    for fault, recovery, terminal in cases:
        assert fault.recovery is recovery, type(fault).__name__
        assert fault.terminal is terminal, type(fault).__name__
    blocked = GmailTransportFailure("x", endpoint=endpoint)
    blocked.__cause__ = EgressBlocked("no")
    assert blocked.recovery is RecoveryKind.NONE and blocked.terminal


def test_every_refusal_carries_a_recovery_token_from_the_closed_vocabulary(
    service: MailweaveService, wire: Wire
) -> None:
    assert "recovery" in REFUSAL_KEYS
    wire.status = {"/messages/": 404}
    result = call(service, "mailweave_get_messages", {"message_ids": ["v-1"], "view": "snippet"})
    refusal = structured(result)
    assert set(REFUSAL_KEYS) <= set(refusal)
    assert refusal["recovery"] in RECOVERY_TOKENS
    # A narrowing decline is `narrow` and carries the retry; the two agree.
    wire.status = {}
    wire.stall = {"/messages/": 3_000.0}
    ids = vendor_ids(service)[:4]
    result = call(service, "mailweave_get_messages", {"message_ids": ids, "view": "body_full"})
    refusal = structured(result)
    assert refusal["recovery"] == "narrow" and refusal["retry_with"] is not None


# --- 3. attribution and chronology on the wire ------------------------------------------------


def _attributed_box() -> SyntheticMailbox:
    """A thread whose From headers cover the four provenance states a row can be in."""
    named = Msg(
        id="a-1",
        thread_id="t-attr",
        sender='"Ana Lee" <Ana@Team.example>',
        subject="Attribution",
        body=f"The {MARKER} is here.",
        internal_date_ms=epoch_ms(2026, 3, 1),
        to=("bo@team.example",),
    )
    bare = Msg(
        id="a-2",
        thread_id="t-attr",
        sender="bo@team.example",
        subject="Re: Attribution",
        body="A reply with a bare address.",
        internal_date_ms=epoch_ms(2026, 3, 2),
        to=("ana@team.example",),
        in_reply_to="<a-1@mail.invalid>",
    )
    two = Msg(
        id="a-3",
        thread_id="t-attr",
        sender="cy@team.example, dee@team.example",
        subject="Re: Attribution",
        body="Two senders on one header.",
        internal_date_ms=epoch_ms(2026, 3, 3),
        to=("ana@team.example",),
        in_reply_to="<a-2@mail.invalid>",
    )
    return SyntheticMailbox(messages=(named, bare, two), now_ms=epoch_ms(2026, 9, 3))


def test_every_row_states_who_its_from_header_named_and_where_that_came_from() -> None:
    clock = FakeClock()
    box = _attributed_box()
    wire = Wire(box, clock)
    service = make(box, wire, clock, sleeper=lambda _s: None)
    result = call(service, "mailweave_thread_map", {"thread_id": "t-attr"})
    assert not result.is_error, text_of(result)
    rows = {
        row["id"]: row for source in structured(result)["sources"] for row in source["messages"]
    }
    assert set(rows) == {"a-1", "a-2", "a-3"}

    named = rows["a-1"]["attribution"]
    assert named["provenance"] == "from_header"
    assert named["address"] == "ana@team.example", "folded for comparison"
    assert named["stated_addresses"] == 1
    assert "Ana Lee" in named["display_name"]["text"], "fenced, and the name inside the fence"
    assert named["display_name"]["trust"] == "untrusted_third_party"
    assert named["display_name"]["source"] == "gmail_header"

    bare = rows["a-2"]["attribution"]
    assert bare["provenance"] == "from_header"
    assert bare["address"] == "bo@team.example"
    assert bare["display_name"] is None

    two = rows["a-3"]["attribution"]
    assert two["provenance"] == "from_header_multiple"
    assert two["address"] == "cy@team.example"
    assert two["stated_addresses"] == 2

    for row in rows.values():
        assert row["headers_observed"] is True
        assert row["internal_date"] is not None
        assert row["internal_date_provenance"] == "gmail_internal_date"


def test_a_search_row_carries_the_same_attribution_as_a_map_row() -> None:
    """One implementation for both surfaces, so they cannot disagree."""
    clock = FakeClock()
    box = _attributed_box()
    wire = Wire(box, clock)
    service = make(box, wire, clock, sleeper=lambda _s: None)
    found = structured(call(service, "mailweave_search", {"query": f'"{MARKER}"'}))
    rows = {row["id"]: row for source in found["sources"] for row in source["messages"]}
    assert rows["a-1"]["attribution"]["address"] == "ana@team.example"
    assert rows["a-1"]["attribution"]["provenance"] == "from_header"
    assert rows["a-1"]["internal_date_provenance"] == "gmail_internal_date"


def test_the_attribution_block_asserts_no_identity_and_rests_on_an_observation() -> None:
    """No `sender`, `author` or `verified` field exists; an address needs the header behind
    it; and a row that read no headers cannot claim one."""
    assert {"provenance", "address", "display_name", "stated_addresses"} == set(
        Attribution.model_fields
    )
    for forbidden in ("sender", "author", "verified", "identity", "person"):
        assert forbidden not in Attribution.model_fields
    with pytest.raises(ValueError, match="addr-spec"):
        Attribution(provenance=AttributionProvenance.FROM_HEADER, address="a sentence")
    with pytest.raises(ValueError, match="neither is a fact"):
        Attribution(provenance=AttributionProvenance.HEADERS_NOT_OBSERVED, address="a@b.example")
    with pytest.raises(ValueError, match="exactly one"):
        Attribution(
            provenance=AttributionProvenance.FROM_HEADER, address="a@b.example", stated_addresses=2
        )
    unobserved = MessageRow.model_fields["attribution"].get_default(call_default_factory=True)
    assert unobserved.provenance is AttributionProvenance.HEADERS_NOT_OBSERVED


def test_a_row_with_no_observation_says_so_for_both_facts(
    service: MailweaveService, wire: Wire
) -> None:
    """The stub rows of a thread map that a search inventories without fetching headers carry
    `headers_not_observed` and `internal_date: null` with `not_observed` - both stated, neither
    implied by an absent key."""
    found = structured(call(service, "mailweave_search", {"query": f'"{MARKER}"'}))
    rows = [row for source in found["sources"] for row in source["messages"]]
    unobserved = [row for row in rows if not row["headers_observed"]]
    observed = [row for row in rows if row["headers_observed"]]
    assert observed, "the fixture's hit rows observe headers"
    for row in unobserved:
        assert row["attribution"] == {
            "provenance": "headers_not_observed",
            "address": None,
            "display_name": None,
            "stated_addresses": 0,
        }
    for row in rows:
        assert "internal_date" in row
        assert row["internal_date_provenance"] in ("gmail_internal_date", "not_observed")
        assert (row["internal_date"] is None) == (row["internal_date_provenance"] == "not_observed")


# --- 4. the call lifecycle diagnostic ---------------------------------------------------------


@pytest.fixture
def diagnostic(tmp_path: Path) -> Iterator[Path]:
    path = tmp_path / "diag" / "calls.jsonl"
    diagnostics.use(Lifecycle(path))
    yield path
    diagnostics.use(None)


def lines_of(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_every_call_writes_a_start_and_an_end_with_its_outcome(
    service: MailweaveService, wire: Wire, diagnostic: Path
) -> None:
    from mcp.shared.exceptions import MCPError

    ids = vendor_ids(service)[:2]
    call(service, "mailweave_thread_map", {"thread_id": "t-vendor"})
    call(service, "mailweave_get_messages", {"message_ids": ids, "view": "snippet"})
    call(service, "mailweave_get_attachment", {"message_id": "v-3", "part_id": "1"})
    wire.status = {"/messages/": 404}
    call(service, "mailweave_get_messages", {"message_ids": ["t-vendor"], "view": "snippet"})
    with pytest.raises(MCPError):
        call(service, "mailweave_get_messages", {"message_ids": "not-a-list"})

    lines = lines_of(diagnostic)
    starts = [line for line in lines if line["event"] == "start"]
    ends = [line for line in lines if line["event"] == "end"]
    assert len(starts) == len(ends) == 6
    assert [s["tool"] for s in starts] == [
        "mailweave_search",
        "mailweave_thread_map",
        "mailweave_get_messages",
        "mailweave_get_attachment",
        "mailweave_get_messages",
        "mailweave_get_messages",
    ]
    for start, end in zip(starts, ends, strict=True):
        assert start["call"] == end["call"]
        assert start["surface"] == end["surface"] == "mailweave"
        assert end["elapsed_ms"] >= 0
        datetime.fromisoformat(start["ts"])
    outcomes = [e["outcome"] for e in ends]
    assert outcomes == ["served", "served", "served", "served", "declined", "protocol_error"]
    declined = ends[4]
    assert declined["code"] == "partial_source_failure"
    assert declined["terminal"] is True and declined["recovery"] == "none"
    assert ends[5]["fault"] == "MCPError"


def test_the_diagnostic_carries_shapes_and_never_a_value_from_the_call(
    service: MailweaveService, wire: Wire, diagnostic: Path
) -> None:
    """A query with a marker, message identifiers, a handle, and a body marker in the
    mailbox: none of them reaches the file. Only the keys and the shapes do."""
    query_marker = "ZQ7MARKERQUERY"
    call(service, "mailweave_search", {"query": f'"{MARKER}" {query_marker}'})
    ids = vendor_ids(service)[:3]
    found = structured(call(service, "mailweave_search", {"query": f'"{MARKER}"'}))
    handle = found["sources"][0]["map_id"]
    call(service, "mailweave_get_messages", {"message_ids": ids, "view": "body_clean"})
    call(service, "mailweave_thread_map", {"map_id": handle})
    call(
        service,
        "mailweave_search",
        {"query": f'"{MARKER}"', "budget": {"max_hit_threads": 3}, "pool": {"scope": "auto"}},
    )
    raw = diagnostic.read_text(encoding="utf-8")
    assert query_marker not in raw
    assert MARKER not in raw
    for message_id in ids:
        assert message_id not in raw
    assert handle not in raw
    assert "t-vendor" not in raw
    assert TOKEN not in raw
    lines = lines_of(diagnostic)
    shapes = [(line["tool"], line["shape"]) for line in lines if line["event"] == "start"]
    assert shapes[0] == ("mailweave_search", {"query": "str"})
    assert ("mailweave_get_messages", {"message_ids": "list[3]", "view": "body_clean"}) in shapes
    assert ("mailweave_thread_map", {"map_id": "str"}) in shapes
    assert shapes[-1] == (
        "mailweave_search",
        {"query": "str", "budget": {"max_hit_threads": "int"}, "pool": {"scope": "auto"}},
    )


def test_the_diagnostic_is_off_unless_asked_for_and_the_file_is_owner_only(
    service: MailweaveService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diagnostics.use(None)
    monkeypatch.delenv(diagnostics.ENV_VAR, raising=False)
    assert diagnostics.lifecycle().enabled is False
    call(service, "mailweave_thread_map", {"thread_id": "t-vendor"})
    assert not list(tmp_path.iterdir())

    diagnostics.use(None)
    target = tmp_path / "on" / "calls.jsonl"
    monkeypatch.setenv(diagnostics.ENV_VAR, str(target))
    assert diagnostics.lifecycle().enabled is True
    call(service, "mailweave_thread_map", {"thread_id": "t-vendor"})
    diagnostics.use(None)
    assert target.exists()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert len(lines_of(target)) == 2


def test_the_orivra_surface_writes_the_same_lines_under_its_own_name(
    diagnostic: Path,
) -> None:
    from orivra.contracts.vocab import ConnectorId
    from orivra.gmail_adapter import GmailAdapter
    from orivra.registry import ConnectorRegistry
    from orivra.surface.server import call as orivra_call
    from orivra.surface.service import OrivraService
    from tests.test_mcp_surface_round24 import make_service

    scope = "https://www.googleapis.com/auth/gmail.readonly"
    adapter = GmailAdapter(service=make_service(mailbox()), granted_scopes=(scope,))
    orivra = OrivraService(registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}))
    result = orivra_call(orivra, "orivra_ask", {"query": f'"{MARKER}"', "view": "snippet"})
    assert not result.is_error, text_of(result)
    legacy = orivra_call(orivra, "mailweave_thread_map", {"thread_id": "t-vendor"})
    assert not legacy.is_error
    lines = lines_of(diagnostic)
    by_tool = [(line["event"], line["surface"], line["tool"]) for line in lines]
    assert ("start", "orivra", "orivra_ask") in by_tool
    assert ("end", "orivra", "orivra_ask") in by_tool
    assert ("start", "mailweave", "mailweave_thread_map") in by_tool
    assert ("end", "mailweave", "mailweave_thread_map") in by_tool
    assert surface_of("orivra_graph") == "orivra" and surface_of("mailweave_search") == "mailweave"
    assert MARKER not in diagnostic.read_text(encoding="utf-8")


def test_shape_of_names_only_published_keys_and_carries_only_published_enum_members() -> None:
    """Read against `mailweave_search`'s published schema, which is what the surface passes."""
    from mailweave.envelope.vocab import ToolName
    from mailweave.surface.tools import SPEC_BY_NAME

    schema = SPEC_BY_NAME[ToolName.SEARCH].input_schema
    shaped = shape_of(
        {
            "query": "who approved the rollout",
            "view": "snippet",
            "message_ids": ["1a0", "1b1"],
            "budget": {"max_hit_threads": 4, "notes": "free text"},
            "pool": {"scope": "auto", "window": "not a member"},
            "flag": True,
            "count": 7,
            "nothing": None,
            "the subject line as a key": 1,
        },
        schema,
    )
    assert shaped.fields == {
        "query": "str",
        "view": "snippet",
        "budget": {"max_hit_threads": "int", "<unknown>": 1},
        "pool": {"scope": "auto", "window": "str"},
    }
    # `message_ids`, `flag`, `count`, `nothing` and the sentence are not search keys.
    assert shaped.unknown_keys == 5
    # And with no schema, nothing is named at all.
    bare = shape_of({"view": "snippet", "query": "x"}, None)
    assert bare.fields == {} and bare.unknown_keys == 2


# --- the deadline on a real clock and a real socket ------------------------------------------


@pytest.mark.network
def test_a_silent_upstream_is_cut_at_the_allowance_on_a_real_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loopback only, and marked `network` because it opens a socket: the default job
    deselects it, `pytest -m network -k silent_upstream` runs it in about a second.

    The fake-clock tests above prove the logic; this proves the mechanism that the logic
    relies on - that the bounded read timeout handed to the transport is what cuts a request
    that never answers - with a listener that accepts and never replies, a socket that honours
    the timeout the way httpcore does, and a 1 s allowance. Before this repair the same call
    waited 30 s per attempt, four attempts, per message.
    """
    import socket
    import threading
    import time

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)
    port = listener.getsockname()[1]
    held: list[socket.socket] = []

    def accept_and_hold() -> None:
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            held.append(conn)

    threading.Thread(target=accept_and_hold, daemon=True).start()
    box = mailbox()

    class SilentUpstream(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            if "/messages/" not in request.url.path:
                return box.handler(request)
            read = request.extensions["timeout"]["read"]
            sock = socket.create_connection(("127.0.0.1", port), timeout=read)
            sock.settimeout(read)
            try:
                sock.sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
                sock.recv(1)
            except TimeoutError as timed_out:
                raise httpx.ReadTimeout("read timed out", request=request) from timed_out
            finally:
                sock.close()
            raise AssertionError("the listener never answers")

    def open_client() -> GmailClient:
        return GmailClient(
            token=StaticToken(TOKEN),
            http=build_client(inner=SilentUpstream()),
            meter=CallMeter(),
            policy=BackoffPolicy(),
            jitterer=lambda: 0.5,
        )

    service = MailweaveService(
        open_client=open_client,
        account_hash=ACCOUNT,
        handle_key=HandleKey(material=b"k" * 32, epoch=0),
        cache=ThreadMapCache(),
        now=lambda: datetime.now(UTC),
    )
    monkeypatch.setattr(service_module, "MAX_SERVER_MS", 1000)
    try:
        started = time.monotonic()
        result = call(
            service, "mailweave_get_messages", {"message_ids": ["v-1", "v-2"], "view": "body_clean"}
        )
        elapsed = time.monotonic() - started
    finally:
        listener.close()
        for conn in held:
            conn.close()
    assert result.is_error
    refusal = structured(result)
    assert refusal["code"] == ErrorCode.BUDGET_EXHAUSTED.value
    assert refusal["recovery"] == "narrow" and refusal["terminal"] is False
    assert elapsed < 2.5, f"took {elapsed:.2f}s against a 1 s allowance"


# --- a schema that admits every shape the ladder can emit ------------------------------------


def test_the_compacted_budget_is_a_shape_the_published_schema_admits() -> None:
    """Found by repair 3, fixed beside it. Rows grew an attribution block; a near-cap Orivra
    answer compacted its budget to fit; the digest the compaction ladder has emitted since
    2026-09-19 was never in the published output schema. Both forms validate now, and a
    third shape would fail here before it reached a client."""
    import jsonschema

    from orivra.surface.service import _budget_digest
    from orivra.surface.tools import _BUDGET

    stages = {
        "stages": [
            {"stage": "retrieval_ms", "connector": "gmail", "limit_ms": None, "measured_on": "x"},
            {"stage": "graph_ms", "connector": None, "limit_ms": None, "unmeasured_because": "y"},
        ]
    }
    jsonschema.validate(stages, _BUDGET)
    digest = _budget_digest(stages)
    jsonschema.validate(digest, _BUDGET)
    assert digest["measured"] == ["retrieval_ms"] and digest["unmeasured"] == ["graph_ms"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"measured": []}, _BUDGET)


# =============================================================================================
# 5. the deadline at the socket: slow streams, the token exchange, and the recorded overrun
# =============================================================================================
#
# These run the **real** `httpx` client and `httpcore` connection pool over a scripted socket
# rather than an `httpx.MockTransport`: a mock transport answers above the socket, so nothing
# it does can show whether a socket read is bounded. The scripted socket honours a read
# timeout the way a socket does - it waits up to the timeout for the next scripted byte and
# raises `httpcore.ReadTimeout` when the byte is later than that - and the clock is real.
# Budgets are hundreds of milliseconds so the suite pays for the property once, cheaply.


class ScriptedSocket(httpcore.NetworkStream):
    """A socket answering from a script, one HTTP exchange per request written into it."""

    def __init__(self, backend: ScriptedBackend) -> None:
        self._backend = backend
        self._request = b""
        #: (seconds to wait before this chunk is available, the chunk)
        self._pending: deque[tuple[float, bytes]] = deque()

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._request += buffer
        head, sep, body = self._request.partition(b"\r\n\r\n")
        if not sep:
            return
        declared = 0
        for line in head.split(b"\r\n")[1:]:
            name, _, value = line.partition(b":")
            if name.strip().lower() == b"content-length":
                declared = int(value.strip())
        if len(body) < declared:
            return
        self._request = b""
        self._pending.extend(self._backend.respond(head, body[:declared]))

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        if not self._pending:
            # Nothing scripted: the peer is silent. A socket would wait the timeout.
            if timeout is None:
                raise AssertionError("a read with no timeout against a silent peer")
            time.sleep(timeout)
            raise httpcore.ReadTimeout("scripted peer sent nothing inside the timeout")
        delay, chunk = self._pending[0]
        if timeout is not None and delay > timeout:
            time.sleep(timeout)
            self._pending[0] = (delay - timeout, chunk)
            raise httpcore.ReadTimeout("scripted chunk arrived after the timeout")
        time.sleep(delay)
        self._pending.popleft()
        if len(chunk) > max_bytes:
            self._pending.appendleft((0.0, chunk[max_bytes:]))
        return chunk[:max_bytes]

    def close(self) -> None:
        self._pending.clear()

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        return self

    def get_extra_info(self, info: str) -> Any:
        return None


class ScriptedBackend(httpcore.NetworkBackend):
    """Answers each HTTP request from the synthetic mailbox, with delays by path fragment.

    `first_byte_s` holds the whole response back that long; `trickle` sends it `chunk` bytes
    at a time with `gap_s` between chunks. Both keyed by a path fragment, so a stalled token
    endpoint and a trickling `messages.get` are one line each in the test that needs them.
    """

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self._handler = handler
        self.first_byte_s: dict[str, float] = {}
        self.trickle: dict[str, tuple[int, float]] = {}
        self.requests: list[str] = []
        self.timeouts: list[float | None] = []
        self.connections = 0

    def respond(self, head: bytes, body: bytes) -> list[tuple[float, bytes]]:
        request_line, *header_lines = head.decode("latin-1").split("\r\n")
        method, target, _ = request_line.split(" ", 2)
        headers = dict(line.split(":", 1) for line in header_lines if ":" in line)
        host = headers.get("Host", headers.get("host", "")).strip()
        request = httpx.Request(
            method,
            f"https://{host}{target}",
            headers={key.strip(): value.strip() for key, value in headers.items()},
            content=body,
        )
        self.requests.append(request.url.path)
        response = self._handler(request)
        payload = response.content
        wire = (
            f"HTTP/1.1 {response.status_code} OK\r\n"
            f"Content-Type: {response.headers.get('content-type', 'application/json')}\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("latin-1") + payload
        delay = 0.0
        for fragment, seconds in self.first_byte_s.items():
            if fragment in request.url.path:
                delay = seconds
        for fragment, (chunk, gap_s) in self.trickle.items():
            if fragment in request.url.path:
                pieces = [wire[i : i + chunk] for i in range(0, len(wire), chunk)]
                return [(delay, pieces[0]), *((gap_s, piece) for piece in pieces[1:])]
        return [(delay, wire)]

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        self.connections += 1
        self.timeouts.append(timeout)
        return ScriptedSocket(self)

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        raise AssertionError("no unix socket is opened here")

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def socket_client(backend: ScriptedBackend) -> httpx.Client:
    """`build_client` with its socket layer replaced by the script - and nothing else."""
    inner = bounded_transport(network_backend=backend)
    assert installed_backend(inner) is not None
    return build_client(inner=inner, timeout=30.0)


def socket_service(
    backend: ScriptedBackend,
    *,
    token: TokenProvider | None = None,
    http: httpx.Client | None = None,
) -> MailweaveService:
    session = http if http is not None else socket_client(backend)

    def open_client() -> GmailClient:
        return GmailClient(
            token=token if token is not None else StaticToken(TOKEN),
            http=session,
            meter=CallMeter(),
            policy=BackoffPolicy(),
            jitterer=lambda: 0.5,
        )

    return MailweaveService(
        open_client=open_client,
        account_hash=ACCOUNT,
        handle_key=HandleKey(material=b"k" * 32, epoch=0),
        cache=ThreadMapCache(),
        now=lambda: datetime.now(UTC),
    )


#: The most a call may run past its allowance in these tests, on a real clock. Derived in
#: `docs/RETEST_2026-09-21.md` §"The tolerance": the clamp fires at the allowance to within a
#: socket timeout's granularity, and what follows is raising the fault, building the refusal
#: and writing the end line - milliseconds. The loaded suite is a slower machine than the
#: retest's, so the figure here is the retest's figure and not a tighter one.
OVERRUN_TOLERANCE_MS: int = 750


def test_the_shipped_client_is_built_on_a_deadline_bounded_socket() -> None:
    """`build_client()` with no inner transport - the runtime's own construction - carries the
    clamp. A test that installed the clamp itself would prove nothing about the server."""
    client = build_client(timeout=30.0)
    try:
        transport = client._transport
        assert isinstance(transport, AllowlistTransport)
        assert installed_backend(transport.inner) is not None
    finally:
        client.close()


def test_a_trickling_body_is_cut_at_the_allowance_on_a_real_clock(
    monkeypatch: pytest.MonkeyPatch, diagnostic: Path
) -> None:
    """Every chunk arrives inside the read window; the whole body does not arrive inside the
    call. Before: the per-attempt `httpx` read timeout saw a byte every 40 ms and waited for
    all of them. Now the socket's own reads are clamped to what is left of the call, and the
    read that would cross the allowance is the one that times out."""
    box = mailbox()
    backend = ScriptedBackend(box.handler)
    backend.trickle = {"/messages/": (24, 0.04)}
    service = socket_service(backend)
    monkeypatch.setattr(service_module, "MAX_SERVER_MS", 400)
    started = time.monotonic()
    result = call(
        service, "mailweave_get_messages", {"message_ids": ["v-1", "v-2"], "view": "body_clean"}
    )
    elapsed_ms = (time.monotonic() - started) * 1000.0
    assert result.is_error, text_of(result)
    refusal = structured(result)
    assert refusal["code"] == ErrorCode.BUDGET_EXHAUSTED.value
    # Two ids: the narrower call is one of them, a strictly cheaper read in time as well as
    # in size. (A single id at `body_clean` has no narrower form in the schedule and would
    # decline `retry_later`; that schedule is `surface/recovery.py`'s and is not changed here.)
    assert refusal["recovery"] == "narrow" and refusal["terminal"] is False
    assert refusal["retry_with"]["args"]["message_ids"] == ["v-1"]
    assert 380 <= elapsed_ms <= 400 + OVERRUN_TOLERANCE_MS, f"{elapsed_ms:.0f} ms"
    # The watermark's `profile`, then the first message's read; the deadline refused the second.
    assert backend.requests == [
        "/gmail/v1/users/me/profile",
        "/gmail/v1/users/me/messages/v-1",
    ], backend.requests
    end = [line for line in lines_of(diagnostic) if line["event"] == "end"][-1]
    assert end["allowance_ms"] == 400
    assert end["overrun_ms"] <= OVERRUN_TOLERANCE_MS, end
    assert end["outcome"] == "declined" and end["code"] == "budget_exhausted"


def test_a_trickling_body_that_fits_the_allowance_is_served_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The clamp shortens waits; it does not shorten bodies. A body that trickles in inside
    the allowance is read to its end and served - so the cut above is the deadline's doing and
    not a chunked read being mistaken for a truncated one."""
    box = mailbox()
    backend = ScriptedBackend(box.handler)
    backend.trickle = {"/messages/": (256, 0.005)}
    service = socket_service(backend)
    monkeypatch.setattr(service_module, "MAX_SERVER_MS", 4_000)
    result = call(service, "mailweave_get_messages", {"message_ids": ["v-1"], "view": "body_clean"})
    assert not result.is_error, text_of(result)
    rows = [row for source in structured(result)["sources"] for row in source["messages"]]
    assert [row["id"] for row in rows] == ["v-1"]
    assert rows[0]["content"] is not None


def test_a_stalled_token_exchange_is_the_allowance_and_not_a_refused_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, diagnostic: Path
) -> None:
    """The exchange runs before the first Gmail attempt, on the same session. Before: it ran
    under the token endpoint's own 30 s, outside the deadline, and a timeout there surfaced as
    `ConsentFailed` -> `auth_reauth_required, terminal` - the owner sent to re-consent for a
    token endpoint that was slow. Now the exchange's socket reads are clamped to the call and
    the cut is reported as what it was: the allowance, `retry_later`, not terminal."""
    from pydantic import SecretStr

    from mailweave.auth.consent import InstalledClient, StoredTokenProvider
    from mailweave.auth.tokenstore import StoredCredentials, TokenStore
    from mailweave.constants import SERVER_SCOPES

    box = mailbox()

    def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "ya29.A-TOKEN-THE-TEST-NEVER-RECEIVES",
                    "expires_in": 3599,
                    "scope": " ".join(SERVER_SCOPES),
                    "token_type": "Bearer",
                },
            )
        return box.handler(request)

    backend = ScriptedBackend(upstream)
    backend.first_byte_s = {"/token": 10.0}
    session = socket_client(backend)
    store = TokenStore(tmp_path / "state" / "credentials.json")
    store.ensure_directory()
    store.save(
        StoredCredentials(
            client_id="1234.apps.googleusercontent.com",
            refresh_token=SecretStr("1//REFRESH-TOKEN-FOR-A-TEST"),
            scopes=tuple(SERVER_SCOPES),
            salt_hex="ab" * 16,
            obtained_at="2026-09-01T00:00:00Z",
        )
    )
    provider = StoredTokenProvider(
        client=InstalledClient(
            client_id="1234.apps.googleusercontent.com",
            client_secret=SecretStr("GOCSPX-A-CLIENT-SECRET-FOR-A-TEST"),
            path=Path("mailweave-server-oauth.json"),
        ),
        store=store,
        http=session,
    )
    service = socket_service(backend, token=provider, http=session)
    monkeypatch.setattr(service_module, "MAX_SERVER_MS", 400)
    started = time.monotonic()
    # Two ids at `body_clean`: a call that *has* a narrower form. The decline must still be
    # `retry_later`, because no narrower Gmail request makes the token endpoint answer sooner.
    result = call(
        service, "mailweave_get_messages", {"message_ids": ["v-1", "v-2"], "view": "body_clean"}
    )
    elapsed_ms = (time.monotonic() - started) * 1000.0
    assert result.is_error, text_of(result)
    refusal = structured(result)
    assert refusal["code"] == ErrorCode.BUDGET_EXHAUSTED.value, refusal
    assert refusal["recovery"] == "retry_later" and refusal["terminal"] is False
    assert refusal["retry_with"] is None
    assert "auth login" not in text_of(result)
    assert "token endpoint did not answer" in text_of(result)
    assert 380 <= elapsed_ms <= 400 + OVERRUN_TOLERANCE_MS, f"{elapsed_ms:.0f} ms"
    assert backend.requests == ["/token"], backend.requests
    raw = diagnostic.read_text(encoding="utf-8")
    assert "REFRESH-TOKEN" not in raw and "GOCSPX" not in raw
    end = [line for line in lines_of(diagnostic) if line["event"] == "end"][-1]
    assert end["code"] == "budget_exhausted" and end["recovery"] == "retry_later"


def test_the_deadline_fault_reads_its_recovery_off_the_phase() -> None:
    from mailweave.gmail.faults import DeadlinePhase
    from mailweave.gmail.rates import GmailEndpoint

    request = GmailDeadlineExceeded(
        "x", endpoint=GmailEndpoint.MESSAGES_GET, budget_ms=100, elapsed_ms=130
    )
    credential = GmailDeadlineExceeded(
        "x",
        endpoint=GmailEndpoint.MESSAGES_GET,
        budget_ms=100,
        elapsed_ms=90,
        phase=DeadlinePhase.CREDENTIAL,
    )
    assert request.phase is DeadlinePhase.REQUEST and request.recovery is RecoveryKind.NARROW
    assert credential.recovery is RecoveryKind.RETRY_LATER
    assert not request.terminal and not credential.terminal
    assert request.overrun_ms == 30 and credential.overrun_ms == 0


def test_a_refused_token_exchange_is_still_a_refused_grant() -> None:
    """The narrowing above is exactly the deadline's timeout and nothing wider: an exchange
    the endpoint refuses leaves the client as `ConsentFailed`, with `mailweave auth login`."""
    from pydantic import SecretStr

    from mailweave.auth.consent import ConsentFailed, InstalledClient, StoredTokenProvider
    from mailweave.auth.tokenstore import StoredCredentials, TokenStore
    from mailweave.constants import SERVER_SCOPES

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(400, json={"error": "invalid_grant"})
        raise AssertionError("no Gmail request is made without a token")

    store_dir = Path(tempfile.mkdtemp()) / "state"
    store = TokenStore(store_dir / "credentials.json")
    store.ensure_directory()
    store.save(
        StoredCredentials(
            client_id="1234.apps.googleusercontent.com",
            refresh_token=SecretStr("1//REFRESH-TOKEN-FOR-A-TEST"),
            scopes=tuple(SERVER_SCOPES),
            salt_hex="ab" * 16,
            obtained_at="2026-09-01T00:00:00Z",
        )
    )
    session = build_client(inner=httpx.MockTransport(handler))
    provider = StoredTokenProvider(
        client=InstalledClient(
            client_id="1234.apps.googleusercontent.com",
            client_secret=SecretStr("GOCSPX-A-CLIENT-SECRET-FOR-A-TEST"),
            path=Path("mailweave-server-oauth.json"),
        ),
        store=store,
        http=session,
    )
    from mailweave.net import deadline as bound

    client = GmailClient(token=provider, http=session, meter=CallMeter())
    with bound.call_scope():
        client.bind_deadline(Deadline(budget_ms=5_000, clock_ms=lambda: time.monotonic() * 1000))
        with pytest.raises(ConsentFailed, match="auth login"):
            client.get_profile()


def test_the_end_line_records_the_allowance_and_a_late_decline_is_recorded_as_late(
    service: MailweaveService, wire: Wire, clock: FakeClock, tmp_path: Path
) -> None:
    """The fake clock is given to the writer too, so the end line's arithmetic is checkable.

    A served call bound `MAX_SERVER_MS` and ran no time at all: `overrun_ms: 0`. A single
    request the mock transport holds for 9 s cannot be cut by anything - the mock answers
    above the socket - and declines `budget_exhausted` 1.3 s late: `overrun_ms: 1300`, on a
    line whose outcome is a decline. The checker below refuses that line; the decline does
    not excuse it.
    """
    path = tmp_path / "late" / "calls.jsonl"
    diagnostics.use(Lifecycle(path, clock_ms=clock))
    try:
        call(service, "mailweave_thread_map", {"thread_id": "t-vendor"})
        ids = vendor_ids(service)[:1]
        assert ids
        wire.stall = {"/messages/": 9_000.0}
        wire.requests.clear()
        result = call(service, "mailweave_get_messages", {"message_ids": ids, "view": "snippet"})
    finally:
        diagnostics.use(None)
    assert result.is_error
    assert structured(result)["code"] == ErrorCode.BUDGET_EXHAUSTED.value
    ends = [line for line in lines_of(path) if line["event"] == "end"]
    served = ends[0]
    assert served["outcome"] == "served"
    assert served["allowance_ms"] == MAX_SERVER_MS and served["overrun_ms"] == 0
    late = ends[-1]
    assert late["outcome"] == "declined" and late["code"] == "budget_exhausted"
    assert late["allowance_ms"] == MAX_SERVER_MS
    assert late["elapsed_ms"] == 9_000 and late["overrun_ms"] == 9_000 - MAX_SERVER_MS
    # And a call that never bound a deadline - refused in argument parsing - carries none.
    diagnostics.use(Lifecycle(path, clock_ms=clock))
    try:
        with pytest.raises(Exception, match="view is required"):
            call(service, "mailweave_get_messages", {"message_ids": "not-a-list"})
    finally:
        diagnostics.use(None)
    parsed_only = [line for line in lines_of(path) if line["event"] == "end"][-1]
    assert parsed_only["outcome"] == "protocol_error"
    assert "allowance_ms" not in parsed_only and "overrun_ms" not in parsed_only


def test_the_checker_refuses_a_late_budget_exhausted_and_a_start_without_an_end() -> None:
    """`tools/dev/check_calls.py` is what the retest reads the file with, so its rule is
    executed here: a decline that arrived late fails on its overrun, whatever its code; a
    served call that ran over fails the same way; an unended call fails; and the tolerance is
    the only thing that can pass a late line, by the number it states."""
    from tools.dev.check_calls import check, render

    def line(**fields: Any) -> str:
        return json.dumps({"ts": "2026-09-21T00:00:00.000+00:00", **fields})

    text = "\n".join(
        [
            line(event="start", call="a", surface="mailweave", tool="mailweave_search", shape={}),
            line(
                event="end",
                call="a",
                surface="mailweave",
                tool="mailweave_search",
                elapsed_ms=13_900,
                allowance_ms=13_700,
                overrun_ms=200,
                outcome="served",
            ),
            line(event="start", call="b", surface="mailweave", tool="mailweave_get_messages"),
            line(
                event="end",
                call="b",
                surface="mailweave",
                tool="mailweave_get_messages",
                elapsed_ms=240_000,
                allowance_ms=7_700,
                overrun_ms=232_300,
                outcome="declined",
                code="budget_exhausted",
                terminal=False,
                recovery="narrow",
            ),
            line(event="start", call="c", surface="orivra", tool="orivra_ask", shape={}),
            line(event="start", call="d", surface="mailweave", tool="mailweave_thread_map"),
            line(
                event="end",
                call="d",
                surface="mailweave",
                tool="mailweave_thread_map",
                elapsed_ms=12,
                outcome="protocol_error",
                fault="MCPError",
            ),
        ]
    )
    report = check(text, tolerance_ms=750)
    assert not report.ok
    assert [timing.call_id for timing in report.late] == ["b"]
    assert [timing.call_id for timing in report.unended] == ["c"]
    assert [timing.call_id for timing in report.unbounded] == ["d"]
    rendered = render(report, tolerance_ms=750)
    assert "b" in rendered and "budget_exhausted" in rendered and "LATE" in rendered
    assert "started, never ended" in rendered
    # The served overrun of 200 ms passes at 750 and fails at 100: the number is the rule.
    assert [timing.call_id for timing in check(text, tolerance_ms=100).late] == ["a", "b"]
    # A file where every call ended inside its allowance holds.
    clean = "\n".join(
        [
            line(event="start", call="a", surface="mailweave", tool="mailweave_search", shape={}),
            line(
                event="end",
                call="a",
                surface="mailweave",
                tool="mailweave_search",
                elapsed_ms=6_100,
                allowance_ms=13_700,
                overrun_ms=0,
                outcome="served",
            ),
        ]
    )
    assert check(clean, tolerance_ms=0).ok
    with pytest.raises(ValueError):
        check(clean, tolerance_ms=-1)


def test_the_call_scope_resets_the_published_deadline_when_the_call_ends(
    service: MailweaveService,
) -> None:
    """A deadline one call published cannot clamp the next call's sockets: `in_band` scopes it.
    Read through the socket layer's own accessor, which is what the clamp reads."""
    from mailweave.net import deadline as bound

    assert bound.bound_allowance() is None
    call(service, "mailweave_thread_map", {"thread_id": "t-vendor"})
    assert bound.bound_allowance() is None
    with bound.call_scope():
        bound.publish(Deadline(budget_ms=1_000, clock_ms=lambda: 0.0))
        assert bound.bound_allowance() is not None
        assert bound.clamp(30.0) == 1.0 and bound.clamp(None) == 1.0
    assert bound.bound_allowance() is None
    assert bound.clamp(30.0) == 30.0 and bound.clamp(None) is None


# =============================================================================================
# 6. the diagnostic names nothing the server does not publish
# =============================================================================================


def test_malformed_arguments_reach_the_start_line_as_counts_and_never_as_content(
    service: MailweaveService, diagnostic: Path
) -> None:
    """Through the tool boundary, before validation refuses them: a sentence as a key, a
    sentence under an enum key, a sentence under a nested unknown key, and an integer that is
    not a width. None of it is in the file; the published keys and the counts are."""
    from mcp.shared.exceptions import MCPError

    key_marker = "KMARKER the subject line of a private message"
    value_marker = "VMARKER a query the owner typed"
    nested_marker = "NMARKER free text inside budget"
    with pytest.raises(MCPError):
        call(
            service,
            "mailweave_search",
            {
                "query": value_marker,
                "view": value_marker,
                key_marker: 1,
                "budget": {"max_server_ms": 8_675_309, nested_marker: "x", "max_hit_threads": 2},
                "pool": {"scope": "recency"},
            },
        )
    with pytest.raises(MCPError):
        call(service, "mailweave_get_messages", {"message_ids": value_marker, "view": "stub"})
    raw = diagnostic.read_text(encoding="utf-8")
    for marker in (key_marker, value_marker, nested_marker, "KMARKER", "VMARKER", "NMARKER"):
        assert marker not in raw
    assert "8675309" not in raw
    starts = [line for line in lines_of(diagnostic) if line["event"] == "start"]
    assert starts[0]["tool"] == "mailweave_search"
    assert starts[0]["shape"] == {
        "query": "str",
        "view": "str",
        "budget": {"max_server_ms": "int", "max_hit_threads": "int", "<unknown>": 1},
        "pool": {"scope": "recency"},
    }
    assert starts[0]["unknown_keys"] == 1
    assert starts[1]["shape"] == {"message_ids": "str", "view": "stub"}
    assert "unknown_keys" not in starts[1]
    ends = [line for line in lines_of(diagnostic) if line["event"] == "end"]
    assert [end["outcome"] for end in ends] == ["protocol_error", "protocol_error"]


def test_the_orivra_surface_redacts_against_its_own_published_schema(diagnostic: Path) -> None:
    from mcp.shared.exceptions import MCPError

    from orivra.contracts.vocab import ConnectorId
    from orivra.gmail_adapter import GmailAdapter
    from orivra.registry import ConnectorRegistry
    from orivra.surface.server import call as orivra_call
    from orivra.surface.service import OrivraService
    from tests.test_mcp_surface_round24 import make_service

    scope = "https://www.googleapis.com/auth/gmail.readonly"
    adapter = GmailAdapter(service=make_service(mailbox()), granted_scopes=(scope,))
    orivra = OrivraService(registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}))
    marker = "OMARKER something the caller wrote"
    with pytest.raises(MCPError):
        orivra_call(
            orivra, "orivra_ask", {"query": marker, "view": marker, "sources": [marker], marker: 1}
        )
    with pytest.raises(MCPError):
        orivra_call(orivra, f"orivra_{marker}", {"query": "x"})
    raw = diagnostic.read_text(encoding="utf-8")
    assert "OMARKER" not in raw
    starts = [line for line in lines_of(diagnostic) if line["event"] == "start"]
    assert len(starts) == 1, "an unknown tool is refused before the partition and leaves no line"
    assert starts[0]["surface"] == "orivra" and starts[0]["tool"] == "orivra_ask"
    assert starts[0]["shape"] == {"query": "str", "view": "str", "sources": "list[1]"}
    assert starts[0]["unknown_keys"] == 1


def test_a_start_line_with_no_schema_names_neither_the_tool_nor_a_key(tmp_path: Path) -> None:
    path = tmp_path / "bare" / "calls.jsonl"
    writer = Lifecycle(path)
    record = writer.start("a tool name the caller invented", {"view": "snippet"}, schema=None)
    writer.end(record, outcome="protocol_error", fault="MCPError")
    raw = path.read_text(encoding="utf-8")
    assert "invented" not in raw and "snippet" not in raw
    start = lines_of(path)[0]
    assert start["tool"] == diagnostics.UNREGISTERED_TOOL
    assert start["shape"] == {} and start["unknown_keys"] == 1


def test_booleans_and_enums_are_carried_only_where_the_schema_publishes_them() -> None:
    schema = {
        "type": "object",
        "properties": {
            "flag": {"type": "boolean"},
            "kind": {"enum": ["a", "b"]},
            "free": {"type": "string"},
            "nested": {"type": "object", "properties": {"deep": {"enum": ["x"]}}},
        },
    }
    shaped = shape_of(
        {
            "flag": True,
            "kind": "b",
            "free": "b",
            "nested": {"deep": "x", "other": {"deeper": "x"}},
            "wild": False,
        },
        schema,
    )
    assert shaped.fields == {
        "flag": True,
        "kind": "b",
        "free": "str",
        "nested": {"deep": "x", "<unknown>": 1},
    }
    assert shaped.unknown_keys == 1
    # A boolean under a key the schema types as something else is a shape, not a value.
    assert shape_of({"kind": True}, schema).fields == {"kind": "bool"}


def test_the_first_semantic_query_carries_its_cold_load_and_the_checker_sets_it_aside(
    tmp_path: Path,
) -> None:
    """PF-4 keeps the model load outside every per-query budget. A first query that paid it
    is late by that much on its end line, the line says how much, and the checker measures
    the call net of it - and only of it."""
    from mailweave.semantic.interface import SemanticBackend
    from tests.test_injection_ws14 import BAIT_QUERY, _bait_registry, _paraphrase_corpus
    from tests.test_semantic_rung import make_service as semantic_service
    from tests.test_semantic_rung import measured_profile
    from tools.dev.check_calls import check

    clock = FakeClock()
    registry = _bait_registry()
    service = semantic_service(
        _paraphrase_corpus(bait=False, noise=2), registry=registry, profile=measured_profile()
    )
    service.clock_ms = clock
    original_acquire = registry.acquire

    def slow_first_load(name: str | None = None) -> SemanticBackend:
        if not registry.is_built():
            clock.advance(5_410.0)
        return original_acquire(name)

    registry.acquire = slow_first_load  # type: ignore[method-assign]
    path = tmp_path / "cold" / "calls.jsonl"
    diagnostics.use(Lifecycle(path, clock_ms=clock))
    try:
        first = call(service, "mailweave_search", {"query": BAIT_QUERY})
        second = call(service, "mailweave_search", {"query": BAIT_QUERY})
    finally:
        diagnostics.use(None)
    assert not first.is_error and not second.is_error
    ends = [line for line in lines_of(path) if line["event"] == "end"]
    assert ends[0]["cold_load_ms"] == 5_410 and "cold_load_ms" not in ends[1]
    assert ends[0]["elapsed_ms"] >= 5_410 and ends[0]["overrun_ms"] == 0
    # Push the first call over its allowance by exactly the load, and the checker passes it
    # net of the load; without the load line it would not.
    over = dict(ends[0])
    over["elapsed_ms"] = over["allowance_ms"] + 5_410 + 100
    over["overrun_ms"] = 5_410 + 100
    start = json.dumps({"event": "start", "call": over["call"], "tool": over["tool"]})
    assert check(start + "\n" + json.dumps(over), tolerance_ms=750).ok
    del over["cold_load_ms"]
    assert not check(start + "\n" + json.dumps(over), tolerance_ms=750).ok


# =============================================================================================
# 7. a spent deadline refuses the socket operation; it never hands the socket a zero
# =============================================================================================
#
# The retest of 2026-09-22 failed on `ValueError: do_handshake_on_connect should not be
# specified for non-blocking sockets` from `httpcore`'s `start_tls`: the clamp had handed the
# handshake a timeout of `0.0`, which is not "fire at once" but "non-blocking", and the
# `ValueError` is mapped by nothing and left the client as an internal error. These tests
# run the real `httpcore.SyncStream` over a real socket (one end of a `socketpair`, so no
# network) and spend the deadline at each boundary in turn.


class _RealSocketBackend(httpcore.NetworkBackend):
    """`connect_tcp` hands back a real `httpcore.SyncStream` over a real socket.

    The peer end is held by the test and never speaks. `spend` is called at the boundary
    named by `spend_at`, so the deadline is spent exactly before that operation starts: after
    the connect for `"tls"`, after the handshake for `"write"`, and so on. `entered` records
    which real operations the inner stream actually executed, which is how a test shows the
    refusal happened *before* the transport was touched.
    """

    def __init__(self, spend: Callable[[], None], *, spend_at: str) -> None:
        self._spend = spend
        self._spend_at = spend_at
        self.entered: list[str] = []
        self.peers: list[socket.socket] = []

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        if self._spend_at == "connect":
            raise AssertionError("connect_tcp was entered after the deadline was spent")
        self.entered.append("connect")
        ours, theirs = socket.socketpair()
        self.peers.append(theirs)
        if self._spend_at == "tls":
            self._spend()
        backend = self
        real = SyncStream(ours)

        class Recording(httpcore.NetworkStream):
            def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
                backend.entered.append("read")
                return real.read(max_bytes, timeout=timeout)

            def write(self, buffer: bytes, timeout: float | None = None) -> None:
                backend.entered.append("write")
                real.write(buffer, timeout=timeout)
                if backend._spend_at == "read":
                    backend._spend()

            def close(self) -> None:
                real.close()

            def start_tls(
                self,
                ssl_context: ssl.SSLContext,
                server_hostname: str | None = None,
                timeout: float | None = None,
            ) -> httpcore.NetworkStream:
                backend.entered.append("tls")
                if backend._spend_at == "tls":
                    # The real handshake, on the real socket, with the timeout the clamp
                    # chose: this is the line the retest died on, and the point of the
                    # `tls` case is that it is never reached.
                    return real.start_tls(
                        ssl_context, server_hostname=server_hostname, timeout=timeout
                    )
                # The other boundaries lie past the handshake, and a silent peer cannot
                # complete one, so the handshake is stood in for and the stream stays real.
                if backend._spend_at == "write":
                    backend._spend()
                return self

            def get_extra_info(self, info: str) -> Any:
                return real.get_extra_info(info)

        return Recording()

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        raise AssertionError("no unix socket is opened here")

    def sleep(self, seconds: float) -> None:
        raise AssertionError("httpcore should not sleep here")

    def close_peers(self) -> None:
        for peer in self.peers:
            peer.close()


def _clocked_socket_service(backend: httpcore.NetworkBackend, clock: FakeClock) -> MailweaveService:
    session = build_client(inner=bounded_transport(network_backend=backend), timeout=30.0)

    def open_client() -> GmailClient:
        return GmailClient(
            token=StaticToken(TOKEN),
            http=session,
            meter=CallMeter(),
            policy=BackoffPolicy(),
            sleeper=lambda _s: None,
            jitterer=lambda: 0.5,
        )

    return MailweaveService(
        open_client=open_client,
        account_hash=ACCOUNT,
        handle_key=HandleKey(material=b"k" * 32, epoch=0),
        cache=ThreadMapCache(),
        now=lambda: datetime.now(UTC),
        clock_ms=clock,
    )


@pytest.mark.parametrize("boundary", ["tls", "write", "read"])
def test_a_deadline_spent_immediately_before_a_socket_operation_is_refused_as_the_deadline(
    boundary: str, diagnostic: Path
) -> None:
    """The retest's failure, reproduced on the real `httpcore` stream and refused.

    `tls` is the observed case: the allowance is spent between the connect and the
    handshake (name resolution and the connect itself run under the clamp, but the connect's
    timeout was fixed before resolution began, so a slow resolver lands the handshake at
    zero). `write` and `read` are the same rule at the next two boundaries. In every case the
    operation is refused before the transport is entered, the refusal is the transport's own
    typed timeout, and the call declines `budget_exhausted` - never a bare exception.
    """
    clock = FakeClock()
    backend = _RealSocketBackend(lambda: clock.advance(2_000.0), spend_at=boundary)
    service = _clocked_socket_service(backend, clock)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(service_module, "MAX_SERVER_MS", 1_000)
        try:
            result = call(service, "mailweave_thread_map", {"thread_id": "t-vendor"})
        finally:
            backend.close_peers()
    assert result.is_error, text_of(result)
    refusal = structured(result)
    assert refusal["code"] == ErrorCode.BUDGET_EXHAUSTED.value, refusal
    assert refusal["recovery"] in ("narrow", "retry_later") and refusal["terminal"] is False
    # The refused operation was never entered on the real stream.
    assert boundary not in backend.entered, backend.entered
    end = [line for line in lines_of(diagnostic) if line["event"] == "end"][-1]
    assert end["outcome"] == "declined" and end["code"] == "budget_exhausted"
    assert end["sockets"] == 1 and "connect_ms" in end


def test_a_deadline_spent_before_the_connect_refuses_the_connect() -> None:
    """The connect boundary: `connect_tcp` is refused with `ConnectTimeout` and the inner
    backend is never asked to open a socket."""
    clock = FakeClock()

    class Untouchable(httpcore.NetworkBackend):
        def connect_tcp(self, *args: Any, **kwargs: Any) -> httpcore.NetworkStream:
            raise AssertionError("the inner backend was entered after the deadline was spent")

    service = _clocked_socket_service(Untouchable(), clock)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(service_module, "MAX_SERVER_MS", 1_000)
        original = service._open_client_for_call

        def opened(budget_ms: float | None = None) -> GmailClient:
            client = original(budget_ms)
            # Spend the allowance after the client is bound and before its first request:
            # `_request`'s own pre-attempt check would refuse at under MIN_ATTEMPT_MS, so
            # leave exactly that much - enough to start the attempt, none for the socket.
            clock.advance(1_000.0 - MIN_ATTEMPT_MS)
            assert client.deadline is not None and not client.deadline.expired()

            def spend_at_connect(*args: Any, **kwargs: Any) -> httpcore.NetworkStream:
                raise AssertionError("unreachable")

            return client

        service._open_client_for_call = opened  # type: ignore[method-assign]
        # The connect is refused only once the deadline reads zero at the socket, so take
        # the remaining MIN_ATTEMPT_MS away at the socket boundary itself.
        from mailweave.net import deadline as bound

        real_allowance = bound.allowance

        def allowance_spending_first(op: bound.Operation, timeout: float | None) -> float | None:
            if op is bound.Operation.CONNECT:
                clock.advance(MIN_ATTEMPT_MS)
            return real_allowance(op, timeout)

        patch.setattr(bound, "allowance", allowance_spending_first)
        result = call(service, "mailweave_thread_map", {"thread_id": "t-vendor"})
    assert result.is_error, text_of(result)
    assert structured(result)["code"] == ErrorCode.BUDGET_EXHAUSTED.value


def test_allowance_refuses_each_operation_with_its_own_typed_timeout_and_never_a_zero() -> None:
    from mailweave.net import deadline as bound

    clock = FakeClock()
    spent = Deadline(budget_ms=100, clock_ms=clock)
    clock.advance(100.0)
    with bound.call_scope():
        bound.publish(spent)
        with pytest.raises(httpcore.ConnectTimeout):
            bound.allowance(bound.Operation.CONNECT, 30.0)
        with pytest.raises(httpcore.ConnectTimeout):
            bound.allowance(bound.Operation.TLS, 30.0)
        with pytest.raises(httpcore.WriteTimeout):
            bound.allowance(bound.Operation.WRITE, None)
        with pytest.raises(httpcore.ReadTimeout):
            bound.allowance(bound.Operation.READ, 30.0)
        with pytest.raises(httpcore.ReadTimeout):
            bound.clamp(30.0)
        # With time left, the clamp is a positive number and never zero.
        live = Deadline(budget_ms=100, clock_ms=clock)
        bound.publish(live)
        assert bound.allowance(bound.Operation.READ, 30.0) == 0.1
        assert bound.allowance(bound.Operation.WRITE, None) == 0.1
        clock.advance(99.9999)
        value = bound.allowance(bound.Operation.TLS, 30.0)
        assert value is not None and value > 0.0
    # And with no deadline bound, every operation passes its timeout through.
    assert bound.allowance(bound.Operation.CONNECT, 30.0) == 30.0
    assert bound.allowance(bound.Operation.READ, None) is None


def test_the_end_line_says_where_a_calls_wall_clock_went_at_the_socket(
    diagnostic: Path,
) -> None:
    """`sockets`, `connect_ms`, `tls_ms`, `write_ms`, `read_ms`: the figures that would have
    said, on 2026-09-22, whether the time was spent resolving a name, shaking hands, or
    waiting for Gmail. Driven over the scripted socket, where the read wait is scripted."""
    box = mailbox()
    backend = ScriptedBackend(box.handler)
    backend.first_byte_s = {"/threads/": 0.12}
    service = socket_service(backend)
    result = call(service, "mailweave_thread_map", {"thread_id": "t-vendor"})
    assert not result.is_error, text_of(result)
    end = [line for line in lines_of(diagnostic) if line["event"] == "end"][-1]
    assert end["outcome"] == "served"
    assert end["sockets"] >= 1
    for key in ("connect_ms", "tls_ms", "write_ms", "read_ms"):
        assert key in end and end[key] >= 0, end
    assert end["read_ms"] >= 110, end
    assert end["read_ms"] <= end["elapsed_ms"]


# =============================================================================================
# 8. every client that makes a request inside a call answers to its own clock
# =============================================================================================
#
# Read from the source while investigating retest run 1, and fixed on the same day. Two
# findings, both about clients opened inside a tool call *without* going through
# `_open_client_for_call`: they ran under no deadline, and - because the clamp was published
# per client and left in the call's context - their sockets were clamped by whichever deadline
# the previous client had published, spent or not. Whether either produced run 1's timings is
# not established here; that is run 2's diagnostics file to say.


def test_a_client_with_no_deadline_is_never_clamped_by_another_clients_spent_deadline(
    diagnostic: Path,
) -> None:
    """Inside one call scope: client A binds a deadline and spends it; client B, opened
    with no deadline, then makes a request. B's sockets must answer to B's clock (none),
    not to A's spent one - before this fix B's first socket operation was refused (or, worse,
    handed a zero) under A's deadline, and B's own `_request` could not read the cut as a
    deadline because it had none."""
    from mailweave.net import deadline as bound

    clock = FakeClock()
    box = mailbox()
    backend = ScriptedBackend(box.handler)
    session = socket_client(backend)

    def client() -> GmailClient:
        return GmailClient(token=StaticToken(TOKEN), http=session, meter=CallMeter())

    with bound.call_scope():
        first = client()
        first.bind_deadline(Deadline(budget_ms=1_000, clock_ms=clock))
        first.get_profile()
        clock.advance(1_000.0)  # A's allowance is now spent.
        with pytest.raises(GmailDeadlineExceeded):
            first.get_profile()
        assert bound.bound_allowance() is None, "a request's publication outlives the request"
        second = client()  # no deadline of its own
        profile = second.get_profile()
        assert profile.email_address
    # And the same with B bound to a live deadline while A's is spent: B's clock rules.
    with bound.call_scope():
        spent = client()
        spent.bind_deadline(Deadline(budget_ms=1_000, clock_ms=clock))
        clock.advance(1_000.0)
        live = client()
        live.bind_deadline(Deadline(budget_ms=5_000, clock_ms=clock))
        assert live.get_profile().email_address
        with pytest.raises(GmailDeadlineExceeded):
            spent.get_profile()


def test_every_adapter_request_runs_under_an_allowance_of_its_own(diagnostic: Path) -> None:
    """The Orivra adapter's own Gmail requests - its ids-only ladder, container reads, item
    fetches, history walk and version probe - each open a client with a deadline bound, so
    no request inside `orivra_ask` or `orivra_expand` runs unbounded. Checked by wrapping the
    service's `open_client` and inspecting every client the adapter was handed."""
    from orivra.adapter import NativeQuery
    from orivra.contracts import ChangeMarker, ConnectorId, RefKind
    from orivra.gmail_adapter import GmailAdapter
    from tests.test_mcp_surface_round24 import make_service

    service = make_service(mailbox())
    opened: list[GmailClient] = []
    original = service.open_client

    def observed() -> GmailClient:
        client = original()
        opened.append(client)
        return client

    service.open_client = observed
    scope = "https://www.googleapis.com/auth/gmail.readonly"
    adapter = GmailAdapter(service=service, granted_scopes=(scope,))
    hits = adapter.search(NativeQuery(connector=ConnectorId.GMAIL, query="vendor"))
    assert hits.ids and hits.container_ids
    adapter.container(adapter.reference(hits.container_ids[0], kind=RefKind.THREAD))
    adapter.items(tuple(adapter.reference(one) for one in hits.ids[:2]))
    version = adapter.version_of(adapter.reference(hits.ids[0]))
    adapter.changes_since(ChangeMarker(connector=ConnectorId.GMAIL, marker=version.revision))
    assert len(opened) >= 5, len(opened)
    unbound = [client for client in opened if client.deadline is None]
    assert not unbound, f"{len(unbound)} of {len(opened)} adapter clients bound no deadline"
    for client in opened:
        assert client.deadline is not None
        assert client.deadline.budget_ms == MAX_SERVER_MS


def test_the_start_line_says_how_long_the_call_queued_and_the_end_line_how_many_deadlines(
    tmp_path: Path,
) -> None:
    """`queued_ms`: the wait behind the one-call-at-a-time lock, which `elapsed_ms` does not
    include and a client's clock does. `deadlines`: how many retrievals bound an allowance,
    so an `orivra_ask` measured against a sum says how many terms the sum has."""
    from orivra.contracts.vocab import ConnectorId
    from orivra.gmail_adapter import GmailAdapter
    from orivra.registry import ConnectorRegistry
    from orivra.surface.server import call as orivra_call
    from orivra.surface.service import OrivraService
    from tests.test_mcp_surface_round24 import make_service

    clock = FakeClock()
    path = tmp_path / "queue" / "calls.jsonl"
    writer = Lifecycle(path, clock_ms=clock)
    diagnostics.use(writer)
    try:
        scope = "https://www.googleapis.com/auth/gmail.readonly"
        adapter = GmailAdapter(service=make_service(mailbox()), granted_scopes=(scope,))
        orivra = OrivraService(registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}))
        arrived = clock()
        clock.advance(2_500.0)  # the call waited this long for the lock
        with writer.queued_since(arrived):
            result = orivra_call(orivra, "orivra_ask", {"query": f'"{MARKER}"', "view": "snippet"})
        assert not result.is_error, text_of(result)
        # A second call with no arrival recorded carries no queue figure.
        orivra_call(orivra, "mailweave_thread_map", {"thread_id": "t-vendor"})
    finally:
        diagnostics.use(None)
    lines = lines_of(path)
    starts = [line for line in lines if line["event"] == "start"]
    ends = [line for line in lines if line["event"] == "end"]
    assert starts[0]["tool"] == "orivra_ask" and starts[0]["queued_ms"] == 2_500
    assert "queued_ms" not in starts[1]
    assert ends[0]["deadlines"] >= 1 and ends[0]["allowance_ms"] >= MAX_SERVER_MS
    assert ends[0]["allowance_ms"] % 100 == 0
    assert ends[1]["deadlines"] == 1 and ends[1]["allowance_ms"] == MAX_SERVER_MS
