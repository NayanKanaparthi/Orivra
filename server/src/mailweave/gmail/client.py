"""The Gmail client (WS-02): four id-yielding endpoints plus `getProfile`.

Built **on** `retrieval.transport.RecordingListTransport` rather than beside it. That seam
exists so a retrieval layer cannot return a bare id list, and the two obligations its
docstring places on this client are met here rather than promised:

  * **no method returns a bare id collection.** `list_messages` returns counts and a
    continuation token; `history_additions` returns counts; `get_thread` returns the thread's
    content, but only from a call that has already recorded every row it returned into the
    ledger. There is no ordering in which a caller obtains ids without `H` having grown
    first;
  * **the raw fetchers stay private and the transport is constructed here**, not by a
    caller. `_fetch_list_page`, `_fetch_thread` and `_fetch_history` are private methods and
    the transport is built in `__init__`, so nothing outside this object holds a fetcher it
    could call and decline to record.

What that buys, stated at the same width as elsewhere: it bounds *under*-recording. It does
nothing about a fabricated observation, which is A1's residue and needs the external content
witness (WS-13/WS-16). This client is exactly as trustworthy as the claim "I executed this
call", and that claim is not checkable from inside this process.

**Egress.** Every request goes through `net.build_client`'s allowlist transport, and
`check_url` is additionally called on the composed URL before the request is handed over.
The second check is not redundant: it makes the property hold for a client injected by a
caller (a probe, a test) whose transport this module did not build, and it fails closed with
`GmailTransportFailure` rather than with a foreign exception type.

**No mail text anywhere.** Nothing here logs. Errors carry an endpoint, a status, an attempt
count and a closed-vocabulary `reason` slug; response bodies, Gmail's own `error.message`
and the query string are all excluded, for the reasons `faults.py` gives.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Any, Final, Protocol

import httpx

from mailweave.auth.consent import ConsentFailed
from mailweave.constants import (
    DEFAULT_PAGE_SIZE,
    GMAIL_API_HOST,
    GMAIL_NUMERIC_ID_RE,
    MAX_GMAIL_NUMERIC_ID_DIGITS,
    MAX_PAGES_PER_QUERY,
    widens_beyond_the_default_mailbox,
)
from mailweave.envelope.disposition import DispositionLedger, FetchedIds, ObservedEndpoint
from mailweave.envelope.reasons import RungId
from mailweave.envelope.wire import Affordance, ScanScopeEntry
from mailweave.errors import EgressBlocked
from mailweave.gmail.faults import (
    RATE_LIMIT_REASONS,
    DeadlinePhase,
    GmailAuthExpired,
    GmailDeadlineExceeded,
    GmailRateLimited,
    GmailRequestRejected,
    GmailResponseUnexpected,
    GmailTransportFailure,
    GmailUnavailable,
    clean_reason,
)
from mailweave.gmail.meter import CallMeter
from mailweave.gmail.models import (
    GmailResponseMalformed,
    HistoryPage,
    Message,
    MessageListPage,
    MessageRef,
    Profile,
    Thread,
    parse_response,
)
from mailweave.gmail.rates import GmailEndpoint
from mailweave.gmail.retry import (
    BackoffPolicy,
    BackoffState,
    Deadline,
    Jitterer,
    Sleeper,
    default_jitterer,
    default_sleeper,
)
from mailweave.net import deadline as bound_deadline
from mailweave.net.egress import build_client, check_url
from mailweave.retrieval.transport import RecordedListing, RecordingListTransport

#: The API root. The host is `constants.GMAIL_API_HOST` - one of the two allowlisted runtime
#: hosts - and the `gmail/v1` path is composed separately so each endpoint literal matches
#: `constants.GMAIL_ENDPOINTS` exactly and the CI path sweep can read it.
API_ROOT: Final[str] = f"https://{GMAIL_API_HOST}/"

#: `format=metadata` header set for a thread map (AD F PF-2, D.5). `References` and
#: `In-Reply-To` are the two the reply-tree reconstruction cannot be built without, and
#: whether `metadataHeaders` really returns them is PF-2's first question.
THREAD_MAP_HEADERS: Final[tuple[str, ...]] = (
    "Message-ID",
    "In-Reply-To",
    "References",
    "Subject",
    "From",
    "To",
    "Cc",
    "Date",
    # **INJ-05's two, added when the row-level identity block was built.** `Reply-To` is a
    # routing directive the *sender* asserts, so a reply going somewhere other than the
    # apparent author is a fact a reader is owed; `Authentication-Results` is what the
    # *receiving* server recorded, and is disclosed as that and never as this server's
    # verdict. Quota is per method and not per format or per header ([VERIFIED] CD §3), so
    # asking for two more costs bytes and not units.
    #
    # **Whether `format=metadata` returns them is unverified**, exactly as PF-2 found for
    # `Cc`. The row reports what was observed and says `observed: false` otherwise; it does
    # not report their absence as a negative fact about the message.
    "Reply-To",
    "Authentication-Results",
)

#: HTTP statuses that are worth another attempt. 403 is conditional - see `_classify`.
_RETRIABLE: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})


class TokenProvider(Protocol):
    """Supplies a bearer access token. Refresh is the auth layer's job, not the client's."""

    def access_token(self) -> str: ...


@dataclass(frozen=True)
class StaticToken:
    """A token that never refreshes. For one-shot commands and the preflight probes."""

    value: str

    def access_token(self) -> str:
        return self.value

    def __repr__(self) -> str:
        """Never render the token. A credential in a traceback is a credential leaked."""
        return "StaticToken(value=<redacted>)"


@dataclass(frozen=True)
class ListingRun:
    """What one paginated `messages.list` walk did. Every member is a count or a token."""

    scan_scope: tuple[ScanScopeEntry, ...]
    pages_fetched: int
    ids_recorded: int
    more_pages: bool
    next_page_token: str | None
    fetched_at: str

    @property
    def page_budget_stopped_the_walk(self) -> bool:
        """True when paging stopped because of the budget and not because Gmail ran out.

        This is the condition `scan_scope_incomplete` (D.11) reports and the one that must
        carry a widening affordance. It is a property rather than a flag a caller sets,
        for the reason everything in this project is: a claim derived from what happened
        cannot disagree with what happened.
        """
        return self.more_pages


@dataclass(frozen=True)
class RecordedThread:
    """A `threads.get` whose every message row is already in `H` (clause H-thr, A2).

    `thread` carries message ids. That is not a hole in the seam: this object cannot be
    obtained except from `GmailClient.get_thread`, which takes a ledger and records the
    whole response before returning - so there is no order of operations in which a caller
    reads these ids without every one of them having entered `H` first. The seam's rule is
    that a listing layer cannot hand back ids it did not record, and that holds here.
    """

    thread: Thread
    ids_recorded: int
    fetched_at: str
    #: Whether chronological positions and `internalDate`s were sealed with the observation.
    scalars_observed: bool
    #: Why they were not, when they were not. `None` when they were.
    scalars_absent_because: str | None
    #: Message ids this thread stamped with an `internalDate` another of its rows also
    #: carries. Their relative position is settled by message id rather than by time, and
    #: this is what lets the response declare that instead of letting the position claim
    #: read as stronger than the evidence (`_thread_scalars`, STR-03).
    tied_on_internal_date: tuple[str, ...] = ()


#: The four `historyTypes` a handle's liveness probe asks about (AD A.10 step 2). All four,
#: because a handle says "these threads have not changed" and a thread whose message was
#: deleted, or whose labels moved, *has* changed. Asking only about additions would make
#: `handle_stale` a claim about one of the four ways a mailbox moves under a handle, stated
#: as though it covered all four - the same "one shape validated, peers trusted" this
#: project keeps finding, in the field where it would silently answer "unchanged".
LIVENESS_HISTORY_TYPES: Final[tuple[str, ...]] = (
    "messageAdded",
    "messageDeleted",
    "labelAdded",
    "labelRemoved",
)


@dataclass(frozen=True)
class ThreadChange:
    """How one thread moved between a handle's `history_id` and now, as counts.

    Counts and not ids, deliberately. This is the one shape in this client that reports on
    messages *without* recording them into a ledger, because a liveness probe is not a
    retrieval: nothing it observes is disclosed, and `history_additions` remains the recorded
    path for the LR rung that does disclose. So it may not hand back an id - the seam's rule
    is that a listing layer cannot return ids it did not record - and it does not: what comes
    out is a per-thread tally, keyed by thread ids **the caller already named in its handle**.
    """

    messages_added: int = 0
    messages_deleted: int = 0
    labels_added: int = 0
    labels_removed: int = 0

    @property
    def total(self) -> int:
        return self.messages_added + self.messages_deleted + self.labels_added + self.labels_removed

    def rendered(self) -> str:
        """The change, as the mechanical phrase `handle_stale` names it with."""
        parts = (
            (self.messages_added, "messages added"),
            (self.messages_deleted, "messages deleted"),
            (self.labels_added, "label additions"),
            (self.labels_removed, "label removals"),
        )
        return ", ".join(f"{count} {label}" for count, label in parts if count)


@dataclass(frozen=True)
class LivenessProbe:
    """What one `history.list` liveness probe established about a named set of threads.

    `expired` is Gmail's 404 on a `startHistoryId` older than its retention ([VERIFIED] RO
    F6). It is **not** "nothing changed": it is "this probe could not tell", which is what
    `handle_stale_unverifiable` says and why that class exists apart from `handle_stale`.

    `pages_exhausted` is the other way this probe can fail to be conclusive: the walk stopped
    at `max_pages` with a continuation token still outstanding, so a change on a page nobody
    fetched is a change nobody saw. Reported rather than folded into "clean", because a
    partial walk that answers "unchanged" is exactly the confident-but-wrong answer a handle
    exists to prevent.

    **Neither flag devalues a positive finding, and amendment A10 says so** (R-RETR-059).
    `touched` is built from records this walk read; an unread page can add to it and cannot
    subtract from it. So `conclusive` gates the *negative* answer only, and `saw_a_change`
    is the positive one - two properties because they are two questions, and the round that
    ran them together served a map while telling the caller the change could not be seen.
    """

    touched: Mapping[str, ThreadChange]
    expired: bool
    pages_fetched: int
    pages_exhausted: bool
    latest_history_id: str | None

    @property
    def conclusive(self) -> bool:
        """Whether this probe may say the named threads are **unchanged**.

        One direction only, and the narrowing is amendment **A10** (R-RETR-059). An
        incomplete walk devalues the *absence* of a record and nothing else: "I read one
        page of two and saw nothing" is not evidence that nothing happened. It says nothing
        about a record the walk **did** read. Reading this property as though it gated both
        answers turned a change the probe had already seen into
        `handle_stale_unverifiable` - content served under a sentence saying the change
        could not be verified, which was false twice over.
        """
        return not self.expired and not self.pages_exhausted

    @property
    def saw_a_change(self) -> bool:
        """Whether this walk **observed** a record touching a named thread above its floor.

        A positive detection is conclusive whatever remains unread, so this property is
        deliberately not conjoined with `conclusive`: `touched` is populated only from
        records this walk actually parsed, and a record that was read was read. The 404
        path returns `touched={}`, so an expired watermark can never reach here saying yes.
        """
        return bool(self.touched)


@dataclass(frozen=True)
class HistoryRun:
    """What one paginated `history.list` walk did."""

    pages_fetched: int
    ids_recorded: int
    latest_history_id: str | None
    next_page_token: str | None
    #: Gmail 404'd the `startHistoryId`: the watermark is too old and must be re-baselined.
    #: A declared re-baseline reported in the response, never a silent one (AD D.9).
    rebaseline_required: bool


@dataclass(frozen=True)
class _RawResponse:
    status: int
    body: Any


def _now() -> str:
    """An RFC 3339 instant in UTC, the shape `parse_instant` accepts."""
    return datetime.now(UTC).isoformat()


def _retry_after_ms(response: httpx.Response) -> float | None:
    """`Retry-After`, seconds form only.

    The HTTP-date form is not parsed: it depends on agreement between two clocks, and a
    skewed clock would turn a one-second wait into an hour. An unparseable header is treated
    as absent, which falls back to the exponential schedule - never to no wait at all.
    """
    raw = response.headers.get("retry-after")
    if raw is None or not raw.strip().isdigit():
        return None
    return float(raw.strip()) * 1000.0


def _error_reason(body: Any) -> str | None:
    """The machine-readable `reason` / `status` slug from a Google error envelope.

    Only the slug. `error.message` is free text the remote side chose and, on a
    `messages.list` failure, echoes the `q` that failed - which AD A.11 keeps out of every
    stored and rendered string. `clean_reason` refuses anything that is not an identifier,
    so a `reason` field carrying a sentence is dropped rather than reported.
    """
    if not isinstance(body, Mapping):
        return None
    error = body.get("error")
    if not isinstance(error, Mapping):
        return None
    details = error.get("errors")
    if isinstance(details, Sequence) and not isinstance(details, str | bytes):
        for detail in details:
            if isinstance(detail, Mapping):
                reason = clean_reason(detail.get("reason"))
                if reason is not None:
                    return reason
    return clean_reason(error.get("status"))


class GmailClient:
    """A thin typed layer over the four id-yielding endpoints plus `getProfile`."""

    def __init__(
        self,
        *,
        token: TokenProvider,
        http: httpx.Client | None = None,
        meter: CallMeter | None = None,
        policy: BackoffPolicy | None = None,
        sleeper: Sleeper | None = None,
        jitterer: Jitterer | None = None,
        user_id: str = "me",
        request_timeout_s: float = 30.0,
    ) -> None:
        self._token = token
        self._http = http if http is not None else build_client(timeout=request_timeout_s)
        #: The most one attempt may wait, whatever the deadline says. A bound `Deadline`
        #: only ever lowers it.
        self._timeout_s = request_timeout_s
        #: The wall-clock allowance of the tool call this client is serving, when one is
        #: bound (`bind_deadline`). `None` for the CLI's one-shot calls and the preflight
        #: probes, which have no clock - the same cases `BackoffState.remaining_ms` names.
        self._deadline: Deadline | None = None
        self.meter = meter if meter is not None else CallMeter()
        self._policy = policy if policy is not None else BackoffPolicy()
        self._sleep = sleeper if sleeper is not None else default_sleeper()
        self._jitter = jitterer if jitterer is not None else default_jitterer()
        self._user_id = user_id
        #: One slot, written by `_fetch_thread` and emptied by `get_thread`. The parsed
        #: thread cannot be returned from the fetcher itself: the fetcher's contract with
        #: the seam is `FetchedIds` and nothing else.
        self._pending_thread: Thread | None = None
        #: Same one-shot slot for the history page, for the same reason: the seam's fetcher
        #: contract is `FetchedIds`, so the page's `historyId` and continuation token cannot
        #: be returned from the fetcher itself.
        self._pending_history: HistoryPage | None = None

    def __repr__(self) -> str:
        """No token, no headers. A client in a traceback must not be a credential in one."""
        return f"GmailClient(user_id={self._user_id!r}, host={GMAIL_API_HOST!r})"

    def bind_deadline(self, deadline: Deadline | None) -> None:
        """Bound every request this client makes from now on by `deadline` (2026-09-21).

        Set once per tool call by the service, on the client it opened for that call. It is
        a slot on the client rather than a parameter on every method because the retrieval
        stack calls this client from fourteen sites across six modules and none of them is
        the right place to know about a clock: the deadline is a property of the *call*,
        and the client is the one object every request of the call passes through.

        **And applied at the socket layer, per request** (second repair, same day; scoped
        per request 2026-09-22). The per-attempt `httpx` timeout below bounds one socket
        operation; a body that trickles or a token exchange that hangs is many operations,
        or an operation outside the attempt. The transport `build_client` installs clamps
        every socket read, write, connect and handshake to what is left of the deadline
        `_request` publishes for its own duration (`net/deadline.py::published`), so the
        sockets always answer to the clock of the client whose request is on the wire.
        """
        self._deadline = deadline

    @property
    def deadline(self) -> Deadline | None:
        return self._deadline

    # A `RecordingListTransport` is built per call, with this call's options bound onto the
    # fetcher by `partial`. Two reasons, both deliberate.
    #
    # The seam's fetcher contract is `(query, page_size, page_token) -> FetchedIds` and
    # `(thread_id) -> FetchedIds`. A per-call option - `includeSpamTrash`, the
    # `metadataHeaders` set, the rung's remaining clock - has no place in it, and widening
    # the seam's signature to carry this client's parameters would be working around the
    # thing the round was told to build on. Binding is the alternative that leaves it alone.
    #
    # And each builder supplies **only** the fetcher its call uses, so a transport built for
    # a listing has no thread fetcher: reaching for the wrong one raises the seam's own
    # "built without a thread fetcher" error rather than a `TypeError` about a keyword.
    # Construction stays inside the client, which is where the seam's docstring puts it.

    def _listing_transport(
        self, *, include_spam_trash: bool, remaining_ms: float | None
    ) -> RecordingListTransport:
        return RecordingListTransport(
            partial(
                self._fetch_list_page,
                include_spam_trash=include_spam_trash,
                remaining_ms=remaining_ms,
            )
        )

    def _history_transport(self, *, remaining_ms: float | None) -> RecordingListTransport:
        return RecordingListTransport(
            self._fetch_list_page,
            fetch_history=partial(self._fetch_history, remaining_ms=remaining_ms),
        )

    def _thread_transport(
        self,
        *,
        message_format: str,
        metadata_headers: Sequence[str],
        remaining_ms: float | None,
        fetched_at: str,
    ) -> RecordingListTransport:
        return RecordingListTransport(
            self._fetch_list_page,
            fetch_thread=partial(
                self._fetch_thread,
                message_format=message_format,
                metadata_headers=metadata_headers,
                remaining_ms=remaining_ms,
                fetched_at=fetched_at,
            ),
        )

    # -- transport --------------------------------------------------------------------

    def _request(
        self,
        endpoint: GmailEndpoint,
        path: str,
        *,
        params: httpx.QueryParams | dict[str, str | int] | None = None,
        remaining_ms: float | None = None,
        tolerate: frozenset[int] = frozenset(),
    ) -> _RawResponse:
        """One logical Gmail call, with retries, charged to the meter attempt by attempt.

        `tolerate` names statuses returned to the caller instead of raised. It holds exactly
        one thing today - `history.list`'s 404 on an expired `startHistoryId`, which AD D.9
        makes a declared re-baseline rather than an error - and it is a parameter rather
        than a special case inside the history method so that the next tolerated status has
        to be written down at its call site.
        """
        url = API_ROOT + path
        try:
            check_url(url)
        except EgressBlocked as blocked:
            raise GmailTransportFailure(
                "the composed request URL is not on the runtime egress allowlist",
                endpoint=endpoint,
            ) from blocked
        with bound_deadline.published(self._deadline):
            return self._request_bounded(
                endpoint, url, params=params, remaining_ms=remaining_ms, tolerate=tolerate
            )

    def _request_bounded(
        self,
        endpoint: GmailEndpoint,
        url: str,
        *,
        params: httpx.QueryParams | dict[str, str | int] | None,
        remaining_ms: float | None,
        tolerate: frozenset[int],
    ) -> _RawResponse:
        """`_request`'s body, run with this client's own deadline published to the sockets."""
        state = BackoffState(policy=self._policy, remaining_ms=remaining_ms)
        deadline = self._deadline
        headers = {
            "Authorization": f"Bearer {self._bearer(endpoint, deadline)}",
            "Accept": "application/json",
        }
        while True:
            # **The deadline, read live, before every attempt** (2026-09-21). Three things
            # follow from it and none of them existed before: an attempt is not started with
            # less than `MIN_ATTEMPT_MS` left; the attempt that is started may not wait past
            # what is left; and the backoff's sleep bound is what is left *now* rather than
            # what was left when this call began. A sequential read that has spent the
            # allowance therefore raises on its next request instead of paying
            # `attempts × timeout` for each remaining message.
            timeout: Any = httpx.USE_CLIENT_DEFAULT
            if deadline is not None:
                left_ms = deadline.remaining_ms()
                if deadline.expired():
                    raise GmailDeadlineExceeded(
                        f"{endpoint.value} was not attempted: the call's wall-clock allowance "
                        f"of {int(deadline.budget_ms)} ms is spent "
                        f"({int(deadline.elapsed_ms())} ms elapsed, {state.attempts} "
                        "attempt(s) made on this request)",
                        endpoint=endpoint,
                        attempts=state.attempts,
                        budget_ms=deadline.budget_ms,
                        elapsed_ms=deadline.elapsed_ms(),
                    )
                timeout = httpx.Timeout(min(self._timeout_s, left_ms / 1000.0))
                state.remaining_ms = left_ms
            state.attempts += 1
            self.meter.record_attempt(endpoint)
            try:
                response = self._http.get(url, params=params, headers=headers, timeout=timeout)
            except httpx.InvalidURL as malformed:
                # **`httpx.InvalidURL` is not an `httpx.HTTPError`** - `issubclass` is False -
                # so it walked straight out of this layer and falsified this module's own
                # invariant, "no bare exception crosses this layer" (round 25, R-MCP-013). It
                # is raised while *building* the request, so no attempt was made, no quota was
                # spent, and retrying would rebuild the same URL: it is a request this client
                # could not form, which is what `GmailRequestRejected` means, and it is raised
                # here rather than fed to the backoff state for exactly that reason.
                raise GmailRequestRejected(
                    f"{endpoint.value} could not be formed as a request "
                    f"({type(malformed).__name__}); the arguments are too large for a Gmail "
                    "URL. No request was sent",
                    endpoint=endpoint,
                    attempts=state.attempts,
                ) from malformed
            except (httpx.HTTPError, EgressBlocked) as failure:
                # A connection that never completed is retried like a 5xx: it is the same
                # condition from the caller's point of view, and the upstream quota was
                # spent either way (A.5a). Unless the deadline is what cut it: then the
                # timeout that fired was the deadline's, retrying would be refused on the
                # next iteration anyway, and the honest fault names the allowance rather
                # than the transport.
                if (
                    deadline is not None
                    and isinstance(failure, httpx.TimeoutException)
                    and deadline.expired()
                ):
                    raise GmailDeadlineExceeded(
                        f"{endpoint.value} did not complete inside the call's wall-clock "
                        f"allowance of {int(deadline.budget_ms)} ms "
                        f"({int(deadline.elapsed_ms())} ms elapsed, {state.attempts} "
                        "attempt(s))",
                        endpoint=endpoint,
                        attempts=state.attempts,
                        budget_ms=deadline.budget_ms,
                        elapsed_ms=deadline.elapsed_ms(),
                    ) from failure
                if self._exhausted(state, retry_after_ms=None):
                    raise GmailTransportFailure(
                        f"{endpoint.value} could not be completed after {state.attempts} "
                        f"attempt(s): {type(failure).__name__}",
                        endpoint=endpoint,
                        attempts=state.attempts,
                    ) from failure
                continue
            if response.status_code == 200:
                return _RawResponse(status=200, body=self._decode(endpoint, response))
            if response.status_code in tolerate:
                return _RawResponse(status=response.status_code, body=None)
            self._classify(endpoint, response, state)

    def _bearer(self, endpoint: GmailEndpoint, deadline: Deadline | None) -> str:
        """The access token for this request, fetched inside the call's allowance.

        **`access_token()` is deliberately NOT wrapped into a `GmailFault` here**, and the
        reason is a finding of round 26 (R-MCP-017 vs R-MCP-006). It refreshes on demand, so
        D.11's most-expected condition - the [VERIFIED] 7-day Testing-status refresh clock
        expiring mid-session - is raised from this line, as `ConsentFailed` or
        `TokenStoreError`, neither of which is a `GmailFault`; that is how it used to escape
        `surface/server.py::call` as `-32603 Internal server error` with GMAIL-06's
        `mailweave auth login` instruction thrown away. R-MCP-017 offered wrapping it here as
        the principled repair. Executed, that repair **undoes R-MCP-006**:
        `surface/runtime.start` distinguishes four startup credential causes by exception
        type, and re-typing two of them as `GmailAuthExpired` collapses a refused refresh and
        a narrowed grant back into one answer - the exact over-broad reporting the previous
        round narrowed. So the condition is routed onto D.11's `auth_reauth_required` side at
        `call`, where the serving path is, and the startup path keeps the type that says
        which cause it was.

        **With one exception, which is not a re-typing** (2026-09-21, second repair). The
        exchange runs on the same transport as the Gmail requests, so under a bound deadline
        its socket waits are clamped to what is left of the call. When that clamp is what
        cut it - the exchange failed on a transport timeout and the deadline is spent - the
        condition is the allowance, not the grant: it is raised as `GmailDeadlineExceeded`
        in the `CREDENTIAL` phase, which declines `budget_exhausted` with `retry_later`.
        Reported as `ConsentFailed` it would decline `auth_reauth_required, terminal` and
        send the owner to re-consent for a token endpoint that was merely slow. A refresh
        the endpoint *refused* still leaves here as `ConsentFailed`, cause and words intact.
        """
        if deadline is None:
            return self._token.access_token()
        if deadline.expired():
            # Spent before this request began: the request's own phase, not the
            # credential's, because nothing about the exchange was tried or was slow.
            raise GmailDeadlineExceeded(
                f"{endpoint.value} was not attempted: the call's wall-clock allowance of "
                f"{int(deadline.budget_ms)} ms is spent ({int(deadline.elapsed_ms())} ms "
                "elapsed) before its first attempt",
                endpoint=endpoint,
                budget_ms=deadline.budget_ms,
                elapsed_ms=deadline.elapsed_ms(),
                phase=DeadlinePhase.REQUEST,
            )
        try:
            return self._token.access_token()
        except ConsentFailed as refused:
            timed_out = isinstance(refused.__cause__, httpx.TimeoutException)
            if timed_out and deadline.expired():
                raise GmailDeadlineExceeded(
                    f"{endpoint.value} was not attempted: the access-token exchange did not "
                    f"complete inside the call's wall-clock allowance of "
                    f"{int(deadline.budget_ms)} ms ({int(deadline.elapsed_ms())} ms "
                    "elapsed). The grant was not refused; the token endpoint did not answer "
                    "in time",
                    endpoint=endpoint,
                    budget_ms=deadline.budget_ms,
                    elapsed_ms=deadline.elapsed_ms(),
                    phase=DeadlinePhase.CREDENTIAL,
                ) from refused
            raise

    def _decode(self, endpoint: GmailEndpoint, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as failure:
            raise GmailResponseMalformed(
                f"{endpoint.value} returned a 200 whose body is not JSON "
                f"({len(response.content)} bytes). The body is not reproduced here: it is "
                "mail-derived and no mail-derived text appears in an error (AD A.11)"
            ) from failure

    def _classify(
        self, endpoint: GmailEndpoint, response: httpx.Response, state: BackoffState
    ) -> None:
        """Turn a non-200 into a retry or into the typed fault it deserves.

        The 403 branch is the one that earns its keep. Gmail has historically answered a
        per-user rate limit with **403 plus a quota `reason`**, not with 429, and reading
        that as an authorisation failure would send the owner to re-consent for a condition
        a 300 ms sleep fixes. So a 403 is a rate limit if - and only if - its machine-readable
        reason says so, and an authorisation failure otherwise. Which of the two Gmail really
        emits under load is recorded by PF-3 rather than assumed here.
        """
        body: Any = None
        try:
            body = response.json()
        except ValueError:
            body = None
        reason = _error_reason(body)
        status = response.status_code
        rate_limited = status == 429 or (status == 403 and reason in RATE_LIMIT_REASONS)
        if status == 401 or (status == 403 and not rate_limited):
            raise GmailAuthExpired(
                f"{endpoint.value} was refused with {status}: the grant is expired, revoked "
                "or insufficient. Run `mailweave auth login` to re-authorise the read-only "
                "client.",
                endpoint=endpoint,
                status=status,
                attempts=state.attempts,
                reason=reason,
            )
        if status in _RETRIABLE or rate_limited:
            if not self._exhausted(state, retry_after_ms=_retry_after_ms(response)):
                return
            if rate_limited:
                raise GmailRateLimited(
                    f"{endpoint.value} is rate limited ({status}) and is still limited after "
                    f"{state.attempts} attempt(s) within the {self._policy.max_backoff_total_ms} "
                    "ms backoff bound",
                    endpoint=endpoint,
                    status=status,
                    attempts=state.attempts,
                    reason=reason,
                )
            raise GmailUnavailable(
                f"{endpoint.value} returned {status} on every one of {state.attempts} attempt(s)",
                endpoint=endpoint,
                status=status,
                attempts=state.attempts,
                reason=reason,
            )
        raise GmailRequestRejected(
            f"{endpoint.value} was rejected with {status}",
            endpoint=endpoint,
            status=status,
            attempts=state.attempts,
            reason=reason,
        )

    def _exhausted(self, state: BackoffState, *, retry_after_ms: float | None) -> bool:
        """Sleep and report `False`, or report `True` when the retry budget is spent.

        The sleep bound is refreshed from the bound deadline first (2026-09-21): a sleep
        may not run past what is left of the call, and what is left is read now, after the
        attempt that just failed, not when the request began.
        """
        if self._deadline is not None:
            state.remaining_ms = self._deadline.remaining_ms()
        delay = state.next_delay_ms(self._jitter, retry_after_ms=retry_after_ms)
        if delay is None:
            return True
        state.sleep(delay, self._sleep)
        return False

    # -- private fetchers: the seam's inputs, never public -----------------------------

    def _fetch_list_page(
        self,
        *,
        query: str,
        page_size: int,
        page_token: str | None,
        include_spam_trash: bool = False,
        remaining_ms: float | None = None,
    ) -> FetchedIds:
        # The two settings meet here, and this is the only place they do (R-SEC-051). The
        # harness pairs them in `MailboxScope` and two AST sweeps keep call sites honest, but
        # a sweep reads what is *written*: `query=f"in:{where}"`, a concatenation, `.format`,
        # or simply omitting the flag beside `query=<scope>.query` all evade both sweeps and
        # put `q=in:anywhere` on the wire with `includeSpamTrash=false`. By the time a request
        # is built there is no spelling left to evade, only a string - so the check is here,
        # and it holds for a caller this repository has not written yet.
        if widens_beyond_the_default_mailbox(query) is not include_spam_trash:
            raise ValueError(
                f"this listing asks Gmail for {
                    'a wider' if not include_spam_trash else 'the default'
                } mailbox in q and {
                    'the default' if not include_spam_trash else 'a wider'
                } one in includeSpamTrash. The `in:` operator and the request parameter "
                "are independent inputs and nothing on Gmail's side makes them agree, so a "
                "call that widens one and not the other samples a mailbox neither setting "
                "describes - and any comparison of two endpoints 'at the same setting' is "
                "then a comparison of nothing (R-SEC-051)"
            )
        params: dict[str, str | int] = {"maxResults": page_size, "q": query}
        if include_spam_trash:
            params["includeSpamTrash"] = "true"
        if page_token:
            params["pageToken"] = page_token
        path = f"gmail/v1/users/{self._user_id}/messages"
        raw = self._request(
            GmailEndpoint.MESSAGES_LIST, path, params=params, remaining_ms=remaining_ms
        )
        page = parse_response(MessageListPage, raw.body, endpoint=GmailEndpoint.MESSAGES_LIST)
        # `resultSizeEstimate` is deliberately not read (GMAIL-04, RO F1): `more_pages` is
        # derived from the continuation token Gmail actually sent, which is the only source
        # that cannot be an estimate.
        return FetchedIds(
            ids=[row.id for row in page.messages],
            endpoint=ObservedEndpoint.MESSAGES_LIST,
            page_size=page_size,
            more_pages=page.next_page_token is not None,
            next_page_token=page.next_page_token,
            thread_ids={row.id: row.thread_id for row in page.messages},
        )

    def _fetch_thread(
        self,
        *,
        thread_id: str,
        message_format: str = "metadata",
        metadata_headers: Sequence[str] = THREAD_MAP_HEADERS,
        remaining_ms: float | None = None,
        fetched_at: str | None = None,
    ) -> FetchedIds:
        # `metadataHeaders` is a **repeated** query key, which a dict cannot express, so the
        # parameters are built as ordered pairs. Getting this wrong is silent: Gmail would
        # return one header of the eight and the reply tree would be reconstructed from a
        # fraction of its links (PF-2).
        pairs: list[tuple[str, str]] = [("format", message_format)]
        if message_format == "metadata":
            pairs.extend(("metadataHeaders", header) for header in metadata_headers)
        path = f"gmail/v1/users/{self._user_id}/threads/{thread_id}"
        raw = self._request(
            GmailEndpoint.THREADS_GET,
            path,
            params=httpx.QueryParams(tuple(pairs)),
            remaining_ms=remaining_ms,
        )
        thread = parse_response(Thread, raw.body, endpoint=GmailEndpoint.THREADS_GET)
        if thread.id != thread_id:
            raise GmailResponseUnexpected(
                "threads.get answered with a different thread than the one requested; a "
                "response that does not describe the call that was made cannot be sealed "
                "as an observation of it",
                endpoint=GmailEndpoint.THREADS_GET,
                status=200,
            )
        self._pending_thread = thread
        scalars = _thread_scalars(thread)
        return FetchedIds(
            ids=[message.id for message in thread.messages],
            endpoint=ObservedEndpoint.THREADS_GET,
            thread_id=thread.id,
            stated_total=len(thread.messages),
            positions=scalars.positions,
            internal_dates=scalars.internal_dates,
            history_id=thread.history_id,
            # **One stamp, not two** (round 15). This used to call `_now()` here while
            # `get_thread` called it again for `RecordedThread.fetched_at`, so the two
            # differed by microseconds - and the only sane use of the returned stamp is
            # `Source.fetched_at`, which `Envelope` checks against *this* one and refuses.
            # Every caller of `get_thread` would have hit that, so the stamp is taken once
            # by `get_thread` and passed in. A time is a fact of one call; two readings of
            # the clock are two facts.
            fetched_at=fetched_at if fetched_at is not None else _now(),
        )

    def _fetch_history(
        self,
        *,
        start_history_id: str,
        page_token: str | None,
        remaining_ms: float | None = None,
    ) -> FetchedIds:
        params: dict[str, str | int] = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
        }
        if page_token:
            params["pageToken"] = page_token
        path = f"gmail/v1/users/{self._user_id}/history"
        raw = self._request(
            GmailEndpoint.HISTORY_LIST,
            path,
            params=params,
            remaining_ms=remaining_ms,
            tolerate=frozenset({404}),
        )
        if raw.status == 404:
            self._pending_history = None
            return FetchedIds(ids=[], endpoint=ObservedEndpoint.HISTORY_LIST)
        page = parse_response(HistoryPage, raw.body, endpoint=GmailEndpoint.HISTORY_LIST)
        self._pending_history = page
        added = [entry.message for record in page.history for entry in record.messages_added]
        # A message can be added, labelled and added again inside one history window, so the
        # same id can appear twice on one page. The seal takes a per-id thread map, and a
        # duplicate id with the same thread is one observation of one message - deduplicated
        # here rather than at the ledger, because the ledger would be deduplicating a claim
        # this response made twice about one thing.
        # [PREFLIGHT PF-19] Google documents neither that this happens nor that it cannot,
        # so the dedup is an unexercised invariant until the live run counts repeats - and
        # a repeat carrying a *different* threadId would mean this map is the wrong shape.
        unique = {reference.id: reference.thread_id for reference in added}
        return FetchedIds(
            ids=list(unique),
            endpoint=ObservedEndpoint.HISTORY_LIST,
            more_pages=page.next_page_token is not None,
            next_page_token=page.next_page_token,
            thread_ids=unique,
        )

    # -- public surface ----------------------------------------------------------------

    def list_messages(
        self,
        ledger: DispositionLedger,
        *,
        rung: RungId,
        query: str,
        widening_affordance: Affordance,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = MAX_PAGES_PER_QUERY,
        page_token: str | None = None,
        include_spam_trash: bool = False,
        remaining_ms: float | None = None,
    ) -> ListingRun:
        """Walk `messages.list` up to the page budget, recording every page into `ledger`.

        `widening_affordance` is **required and checked before the first HTTP call**, which
        is the point of it being a positional obligation rather than an optional argument.
        `ScanScopeEntry` refuses `more_pages: true` without one (GMAIL-04) - but it refuses
        it at *record* time, after `_admit` has already put the page's ids into `H`, which
        would leave ids in `H` with no scan-scope entry describing how they got there. A
        caller cannot know in advance whether Gmail will send a continuation token, so the
        only place this can be checked safely is before the call.

        The budget is `MAX_PAGES_PER_QUERY` from the architecture, passed explicitly so a
        caller widening it via the `scan.max_pages` affordance does so visibly.
        """
        if max_pages < 1:
            raise ValueError("a listing run fetches at least one page")
        if page_size < 1:
            raise ValueError("a page size is a positive number of rows")
        entries: list[ScanScopeEntry] = []
        recorded = 0
        token = page_token
        fetched_at = _now()
        pages = 0
        listing: RecordedListing | None = None
        while pages < max_pages:
            pages += 1
            listing = self._listing_transport(
                include_spam_trash=include_spam_trash, remaining_ms=remaining_ms
            ).list_messages(
                ledger,
                rung=rung,
                query=query,
                page_size=page_size,
                page_token=token,
                affordance=widening_affordance,
                pages_fetched=pages,
            )
            entries.append(listing.scan_scope)
            recorded += listing.ids_recorded
            token = listing.next_page_token
            if not listing.more_pages:
                break
        if listing is None:  # pragma: no cover - the loop above runs at least once
            raise GmailResponseUnexpected(
                "a listing run completed without executing a page",
                endpoint=GmailEndpoint.MESSAGES_LIST,
            )
        return ListingRun(
            scan_scope=tuple(entries),
            pages_fetched=pages,
            ids_recorded=recorded,
            more_pages=listing.more_pages,
            next_page_token=listing.next_page_token,
            fetched_at=fetched_at,
        )

    def get_thread(
        self,
        ledger: DispositionLedger,
        *,
        thread_id: str,
        rung: RungId,
        message_format: str = "metadata",
        metadata_headers: Sequence[str] = THREAD_MAP_HEADERS,
        remaining_ms: float | None = None,
    ) -> RecordedThread:
        """One `threads.get`, recorded into `H` under clause H-thr before it returns (A2).

        `RecordedThread.fetched_at` and the stamp the observation seals are **the same
        string**, taken once here. They were two `_now()` calls until round 15, which made
        the returned value unusable for the one thing it is for: `Envelope` holds a
        `Source.fetched_at` to the stamp the observation recorded, so a caller that put this
        field there got a `DispositionInvariantError` naming a difference of microseconds.
        `test_the_returned_fetch_stamp_is_the_one_the_observation_sealed` executes it.
        """
        self._pending_thread = None
        fetched_at = _now()
        recorded = self._thread_transport(
            message_format=message_format,
            metadata_headers=metadata_headers,
            remaining_ms=remaining_ms,
            fetched_at=fetched_at,
        ).get_thread(ledger, thread_id=thread_id, rung=rung)
        thread = self._pending_thread
        self._pending_thread = None
        if thread is None:  # pragma: no cover - only reachable if the seam stops calling us
            raise GmailResponseUnexpected(
                "the thread observation was recorded but its parsed response is missing",
                endpoint=GmailEndpoint.THREADS_GET,
            )
        scalars = _thread_scalars(thread)
        return RecordedThread(
            thread=thread,
            ids_recorded=recorded,
            fetched_at=fetched_at,
            scalars_observed=scalars.positions is not None,
            scalars_absent_because=scalars.why_absent,
            tied_on_internal_date=scalars.tied_on_internal_date,
        )

    def history_additions(
        self,
        ledger: DispositionLedger,
        *,
        start_history_id: str,
        max_pages: int = MAX_PAGES_PER_QUERY,
        page_token: str | None = None,
        remaining_ms: float | None = None,
    ) -> HistoryRun:
        """Walk `history.list`, recording every `messagesAdded` id under clause H-hist.

        A 404 is not a failure. AD D.9: an expired `startHistoryId` means the watermark is
        older than Gmail's retention, and the answer is a **declared re-baseline** reported
        in the response. `rebaseline_required` is that declaration; `handle_stale_unverifiable`
        (D.11) is how the layer above surfaces it.
        """
        if max_pages < 1:
            raise ValueError("a history run fetches at least one page")
        self._pending_history = None
        recorded = 0
        token = page_token
        pages = 0
        latest: str | None = None
        while pages < max_pages:
            pages += 1
            recorded += self._history_transport(remaining_ms=remaining_ms).list_history_additions(
                ledger,
                start_history_id=start_history_id,
                page_token=token,
            )
            page = self._pending_history
            if page is None:
                return HistoryRun(
                    pages_fetched=pages,
                    ids_recorded=recorded,
                    latest_history_id=None,
                    next_page_token=None,
                    rebaseline_required=True,
                )
            latest = page.history_id or latest
            token = page.next_page_token
            if token is None:
                break
        return HistoryRun(
            pages_fetched=pages,
            ids_recorded=recorded,
            latest_history_id=latest,
            next_page_token=token,
            rebaseline_required=False,
        )

    def _fetch_liveness_page(
        self, *, start_history_id: str, page_token: str | None, remaining_ms: float | None
    ) -> tuple[HistoryPage | None, int]:
        """One `history.list` page for the liveness probe, or `None` for Gmail's 404.

        Separate from `_fetch_history` and **not** a `FetchedIds` fetcher, because it is not
        a retrieval: it records nothing into a ledger and returns no id. The seam's rule -
        a listing layer may not hand back ids it did not record - is kept by there being no
        id to hand back: the caller gets a parsed page that stays inside this method's own
        caller, which reduces it to per-thread counts over thread ids the caller supplied.

        `historyTypes` is a **repeated** query key. Getting that wrong is silent in exactly
        the way `metadataHeaders` was: a dict would send one type and the probe would answer
        "unchanged" about a thread whose messages had been deleted.
        """
        pairs: list[tuple[str, str]] = [("startHistoryId", start_history_id)]
        pairs.extend(("historyTypes", kind) for kind in LIVENESS_HISTORY_TYPES)
        if page_token:
            pairs.append(("pageToken", page_token))
        path = f"gmail/v1/users/{self._user_id}/history"
        raw = self._request(
            GmailEndpoint.HISTORY_LIST,
            path,
            params=httpx.QueryParams(tuple(pairs)),
            remaining_ms=remaining_ms,
            tolerate=frozenset({404}),
        )
        if raw.status == 404:
            return None, raw.status
        return parse_response(HistoryPage, raw.body, endpoint=GmailEndpoint.HISTORY_LIST), 200

    def liveness_of_threads(
        self,
        *,
        since: Mapping[str, str],
        start_history_id: str,
        max_pages: int = MAX_PAGES_PER_QUERY,
        remaining_ms: float | None = None,
    ) -> LivenessProbe:
        """AD A.10 step 2: has anything touched these threads since `start_history_id`?

        **This is the check that can actually fail, and it reads a different resource from
        the one the cache holds.** That is the whole of ADV-002: the previous design
        recomputed `mapping_digest` from the very cached map that produced it, so
        `digest(x) == digest(x)` and `handle_stale` could never fire on a cache hit. A
        `history.list` walk knows nothing about MailWeave's cache, so a cache hit cannot make
        it pass.

        Returns counts per thread, restricted to `thread_ids` - which the caller already
        holds, because they are the threads its own handle names. No id this call observed
        leaves it, so nothing enters `H` and nothing owes a disposition: a liveness probe
        discloses nothing, and `history_additions` remains the recorded path for the LR rung
        that does.

        A 404 sets `expired` (the watermark is older than Gmail's retention, RO F6) and a
        walk that stops with a continuation token outstanding sets `pages_exhausted`. Neither
        is "clean": both mean this probe could not tell **that nothing changed**, which is a
        different answer from "nothing changed" and is why `handle_stale_unverifiable` is its
        own error class. Neither touches what the walk *did* read: a record already parsed is
        a change already seen, and `saw_a_change` reports it whatever remains outstanding
        (amendment A10, R-RETR-059).

        **`since` is a floor per thread, and it is what makes this probe exact.**
        `start_history_id` has to be low enough that no change to any named thread can slip
        under it, which means the *oldest* of the named threads' own `historyId`s - and a
        walk from there necessarily also returns changes that are already reflected in the
        map the caller holds, because a thread whose last change is more recent than that
        floor has that change inside the window. Counting those would report `handle_stale`
        for a thread the handle's own map already shows correctly, on the first redemption of
        a freshly minted handle. So a record counts against a thread only when the record's
        own `historyId` is **greater than that thread's** `historyId` at fetch, which is
        exactly "this change is not in the map you hold". Comparison is numeric, not on the
        string, for the reason `_thread_scalars` now compares numerically (R-RETR-055): these
        are decimal integers and two spellings of one number are one number.
        """
        if max_pages < 1:
            raise ValueError("a liveness probe fetches at least one page")
        for value in (start_history_id, *since.values()):
            if GMAIL_NUMERIC_ID_RE.match(value) is None:
                raise ValueError(
                    "a historyId given to the liveness probe is not the shape Gmail returns: "
                    "an unsigned 64-bit integer rendered as at most "
                    f"{MAX_GMAIL_NUMERIC_ID_DIGITS} ASCII decimal digits. The value is not "
                    "quoted here (R-SEC-032). Every one of them is checked, not only the "
                    "outbound parameter: `since` is compared numerically below, and `int()` "
                    "accepts spellings this project has already been bitten by"
                )
        floors = {thread_id: int(value) for thread_id, value in since.items()}
        tallies: dict[str, list[int]] = {}
        token: str | None = None
        pages = 0
        latest: str | None = None
        while pages < max_pages:
            pages += 1
            page, _status = self._fetch_liveness_page(
                start_history_id=start_history_id, page_token=token, remaining_ms=remaining_ms
            )
            if page is None:
                return LivenessProbe(
                    touched={},
                    expired=True,
                    pages_fetched=pages,
                    pages_exhausted=False,
                    latest_history_id=None,
                )
            latest = page.history_id or latest
            for record in page.history:
                # The four lists in the order `ThreadChange`'s fields declare them, reduced
                # to the message references they carry: `messagesAdded` is modelled by its
                # own type (the LR rung reads it) and the other three share one, so the two
                # sequences have no common element type to iterate over as they stand.
                changes: tuple[tuple[MessageRef, ...], ...] = (
                    tuple(entry.message for entry in record.messages_added),
                    tuple(entry.message for entry in record.messages_deleted),
                    tuple(entry.message for entry in record.labels_added),
                    tuple(entry.message for entry in record.labels_removed),
                )
                at = int(record.id)
                for index, references in enumerate(changes):
                    for reference in references:
                        floor = floors.get(reference.thread_id)
                        if floor is not None and at > floor:
                            tallies.setdefault(reference.thread_id, [0, 0, 0, 0])[index] += 1
            token = page.next_page_token
            if token is None:
                break
        return LivenessProbe(
            touched={
                thread_id: ThreadChange(*counts) for thread_id, counts in sorted(tallies.items())
            },
            expired=False,
            pages_fetched=pages,
            pages_exhausted=token is not None,
            latest_history_id=latest,
        )

    def get_message(
        self,
        message_id: str,
        *,
        message_format: str = "full",
        remaining_ms: float | None = None,
    ) -> Message:
        """One `users.messages.get`. Not a sealed observation, and this is the reasoning.

        `ObservedEndpoint` has three members and adding a fourth is an architecture
        amendment (A2), not a convenience - so the question is whether a `messages.get`
        response can put an id into `H` that was not already there. It cannot: the response
        names exactly one message, the one the caller asked for, and the only readable
        enumeration of ids in this system is `DispositionLedger.hit_ids`. An id a caller can
        pass here is an id `H` already holds, or one that came from outside the ladder
        entirely - a redeemed handle, `mailweave inspect` - in which case the caller, not
        this endpoint, is its source.

        What the response *can* do is answer with a **different** id, and nothing downstream
        re-checks that. So this does, and refuses.

        Deliberately **not** enforced: that `message_id` is already in some ledger's `H`. It
        would be a real property, and it would break the two legitimate callers who have an
        id without a ladder run behind it. The honest statement is the one above - the
        caller is the id's source here - and it is written down rather than defended.
        """
        path = f"gmail/v1/users/{self._user_id}/messages/{message_id}"
        raw = self._request(
            GmailEndpoint.MESSAGES_GET,
            path,
            params={"format": message_format},
            remaining_ms=remaining_ms,
        )
        message = parse_response(Message, raw.body, endpoint=GmailEndpoint.MESSAGES_GET)
        if message.id != message_id:
            raise GmailResponseUnexpected(
                "messages.get answered with a different message than the one requested; the "
                "substituted id would enter disclosure as though the caller had asked for it",
                endpoint=GmailEndpoint.MESSAGES_GET,
                status=200,
            )
        return message

    def get_profile(self, *, remaining_ms: float | None = None) -> Profile:
        """`users.getProfile`. The profile-derivation (A.4) and account-pinning (B.9) input."""
        path = f"gmail/v1/users/{self._user_id}/profile"
        raw = self._request(GmailEndpoint.GET_PROFILE, path, remaining_ms=remaining_ms)
        return parse_response(Profile, raw.body, endpoint=GmailEndpoint.GET_PROFILE)

    def close(self) -> None:
        self._http.close()


@dataclass(frozen=True)
class _ThreadScalars:
    positions: dict[str, int] | None
    internal_dates: dict[str, str] | None
    why_absent: str | None
    #: Message ids sharing an `internalDate` with another row of the same thread. Their
    #: relative order is settled by message id, which is not a fact about time - see
    #: `_thread_scalars`. Empty for the ordinary thread, and declared when it is not.
    tied_on_internal_date: tuple[str, ...] = ()


def _thread_scalars(thread: Thread) -> _ThreadScalars:
    """Amendment A6's per-message scalars for a thread, or an explicit nothing.

    `positions` is a 0-based index into the thread's **chronological** order (amendment A3),
    which is `internalDate` order and not array order - AD A.2 requires strict `internalDate`
    ordering precisely because the two can differ.

    All-or-nothing, and that is the seal's rule rather than a choice made here: a per-id map
    on a sealed observation must name every id the response returned or none of them, since
    a partial map is an account of the response missing part of what it said. So if a single
    message lacks `internalDate` - which is exactly what PF-2 suspects `format=metadata`
    of - **both** maps are omitted and the reason is carried on `RecordedThread` rather than
    positions being invented for the rest. Inventing them would be the failure this project
    exists to prevent, committed by the code that reports on it.

    **The tie-break is the message id, and it used to be the array index** (round 20, WS-05).
    That is the whole of STR-03 for the shape nobody had written down: where every
    `internalDate` differs the array index decides nothing, so the sort *looked*
    order-independent and was tested as though it were - "one shape validated, peers trusted",
    at the one place amendment A3 exists to defend. Two messages of a thread stamped in the
    same millisecond are an ordinary shape (a self-copy, a list expansion, a resend), and
    under the old key their positions came out of the order Gmail happened to send the array
    in - which the API does not promise and STR-03 says chronology must never depend on. A
    message id is a fact of the response rather than of its ordering, so the position map is
    now a function of `{id: internalDate}` alone.

    It is **a** chronological order and not *the* one: with equal timestamps every relative
    order is chronologically valid, and which of them a caller sees is settled by an id rather
    than by time. `tied_on_internal_date` says so, so the position claim cannot be read as
    stronger than the evidence behind it.
    """
    if not thread.messages:
        return _ThreadScalars(positions=None, internal_dates=None, why_absent=None)
    missing = [message.id for message in thread.messages if message.internal_date is None]
    if missing:
        return _ThreadScalars(
            positions=None,
            internal_dates=None,
            why_absent=(
                f"{len(missing)} of {len(thread.messages)} message rows carried no "
                "internalDate, so no chronological order can be derived; positions and "
                "internalDates are both omitted rather than partially invented (A3, A6, "
                "and PF-2 for whether format=metadata returns internalDate at all)"
            ),
        )
    # **One derivation of "when was this message stamped", read once** (R-RETR-055). The
    # sort compared `int(internal_date)` and the tie census compared the raw *string*, so
    # two rows carrying `"01000"` and `"1000"` - equal as integers, unequal as strings, and
    # `GmailNumericId` accepts a zero-padded value - tied in the ordering and appeared in no
    # `tied_on_internal_date` entry. That is the one thing the field exists to prevent: a
    # pair whose relative order was settled by message id, presented with no declaration.
    # Two derivations of one fact is R-ARCH-031, and this is the version of it where the
    # second derivation is a `Counter` key.
    moment = {message.id: int(message.internal_date or "0") for message in thread.messages}
    order = sorted(
        range(len(thread.messages)),
        key=lambda index: (
            moment[thread.messages[index].id],
            thread.messages[index].id,
        ),
    )
    positions = {thread.messages[array_index].id: rank for rank, array_index in enumerate(order)}
    internal_dates = {
        message.id: date for message in thread.messages if (date := message.internal_date)
    }
    stamps = Counter(moment[message.id] for message in thread.messages)
    tied = tuple(
        sorted(message.id for message in thread.messages if stamps[moment[message.id]] > 1)
    )
    if len(positions) != len(thread.messages):
        # Gmail returned one id twice in one thread. That is not a shape this project can
        # seal - `positions` must be injective - and it is not a shape to paper over.
        return _ThreadScalars(
            positions=None,
            internal_dates=None,
            why_absent=(
                "this threads.get response listed the same message id more than once, so "
                "no injective position map exists for it"
            ),
        )
    return _ThreadScalars(
        positions=positions,
        internal_dates=internal_dates,
        why_absent=None,
        tied_on_internal_date=tied,
    )
