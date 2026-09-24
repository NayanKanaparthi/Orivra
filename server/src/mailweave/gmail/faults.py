"""Typed transport failures. No bare exception crosses this layer (AD D.11).

Every failure the Gmail client can produce is one of these, and every one of them carries
the D.11 `ErrorCode` the layer above will surface it under - so the in-band / tool-error
partition is decided by the failure's own type rather than by whoever catches it.

**What these never carry.** No response body, no Gmail `error.message`, no request headers,
no query string. That is not caution, it is two separate rules:

  * `error.message` is free text chosen by the remote side and is echoed back from the
    request - a `messages.list` 400 quotes the `q` that failed, and AD A.11's default
    profile stores query text as features plus a salted hash, never raw;
  * an access token lives in the `Authorization` header, so a failure that renders the
    request renders the credential (RR SEC-04).

What a failure does carry is the endpoint, the HTTP status, the number of attempts made,
and - for a rate limit - the machine-readable `reason` slug, which is a closed vocabulary
token and cannot be prose. `reason` is admitted only if it is a slug by
`constants.clean_slug`; anything else is dropped rather than reported, because a field that
accepts a sentence is a field that carries one (R-SEC-030, one layer out). That checker is
shared with the consent flow's OAuth `error` code, which is the same shape at another layer -
and which spelled it `str.isidentifier()` until round 11's standing-cycle sweep, a predicate
that accepts Arabic and CJK identifiers Google does not emit.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from mailweave.constants import clean_slug
from mailweave.errors import EgressBlocked, ErrorCode, MailweaveError
from mailweave.gmail.rates import GmailEndpoint

#: `reason` values Gmail uses for quota exhaustion. Documented on the Gmail usage-limits
#: page; the 403 spellings matter because Gmail has historically returned **403** rather
#: than 429 for per-user rate limiting, and reading a 403 as an auth failure would send the
#: user to re-consent for a condition that a backoff fixes.
#:
#: **This set is a preflight question, not a fact.** Which status and which slug a real
#: mailbox produces under load is exactly what PF-3 observes, and PF-3 records the raw
#: (status, reason) pairs it sees so this set can be corrected from data.
RATE_LIMIT_REASONS: Final[frozenset[str]] = frozenset(
    {
        "rateLimitExceeded",
        "userRateLimitExceeded",
        "quotaExceeded",
        "dailyLimitExceeded",
        "backendError",  # only ever paired with a 5xx; listed so the pairing is visible
    }
)


def clean_reason(value: object) -> str | None:
    """The `reason` slug, or `None`. Never prose, never a value from a body."""
    return clean_slug(value)


class RecoveryKind(StrEnum):
    """What a caller can do about a fault, stated by the fault's own type (2026-09-21).

    Before this, the surface's `GmailFault` clause minted every decline with `retry_with:
    null` and `terminal: false` - the one combination `surface/recovery.py` is written to
    exclude, because a caller cannot tell a final refusal from a refusal that merely offers
    nothing. The decision belongs on the fault, beside its D.11 code, for the same reason the
    code does: so the partition is decided by the failure's type rather than by whoever
    catches it.

    * `NARROW` - a strictly smaller request of the same kind may return evidence; the decline
      carries it as `retry_with` when the surface can build one.
    * `RETRY_LATER` - the same request may succeed later; nothing smaller helps. No
      `retry_with`, because a retry that repeats the failed call is not a narrowing, and the
      decline says so instead of saying nothing.
    * `REAUTHORISE` - the owner has to act (`mailweave auth login`); the server cannot.
    * `NONE` - no request this server can make will return evidence for this call.

    `terminal` on the wire is `True` for `REAUTHORISE` and `NONE`: the server's chain has
    ended either way, and `recovery` says which of the two it is.
    """

    NARROW = "narrow"
    RETRY_LATER = "retry_later"
    REAUTHORISE = "reauthorise"
    NONE = "none"


class DeadlinePhase(StrEnum):
    """Which wait a `GmailDeadlineExceeded` was raised from."""

    #: The Gmail request itself, in any of its steps, or the sum of them.
    REQUEST = "request"
    #: The access-token exchange at the token endpoint, before the first attempt.
    CREDENTIAL = "credential"


class GmailFault(MailweaveError):
    """Base class for every failure the Gmail client raises.

    A caller can write one `except GmailFault` and know that nothing else escapes the
    client - which is the property "no bare exceptions crossing the layer" actually names.
    `tests/test_gmail_client.py::test_every_failure_path_raises_a_gmail_fault` holds it.
    """

    #: The D.11 code this fault surfaces under. Subclasses set it; the base has none,
    #: because a fault with no code is a fault the response layer cannot render.
    code: ErrorCode
    #: What a caller can do about it. Subclasses set it; the base has none, for the same
    #: reason it has no code.
    recovery: RecoveryKind

    @property
    def terminal(self) -> bool:
        """Whether this server's recovery chain has ended for the call that raised this."""
        return self.recovery in (RecoveryKind.REAUTHORISE, RecoveryKind.NONE)

    def __init__(
        self,
        message: str,
        *,
        endpoint: GmailEndpoint,
        status: int | None = None,
        attempts: int = 1,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.endpoint = endpoint
        self.status = status
        self.attempts = attempts
        self.reason = clean_reason(reason)


class GmailAuthExpired(GmailFault):
    """401, or a 403 that is not a rate limit: the grant is gone or was never sufficient."""

    code = ErrorCode.AUTH_REAUTH_REQUIRED
    recovery = RecoveryKind.REAUTHORISE


class GmailRateLimited(GmailFault):
    """429, or a 403 with a quota `reason`, still failing after the retry bound.

    In-band (D.11): the rungs that did run still produced truthful evidence, so this is a
    field on a successful response beside the rungs not reached - never a bare failure.
    """

    code = ErrorCode.UPSTREAM_RATE_LIMITED
    recovery = RecoveryKind.RETRY_LATER


class GmailUnavailable(GmailFault):
    """5xx persisting past the retry bound. A tool error: the whole call is unanswerable."""

    code = ErrorCode.UPSTREAM_UNAVAILABLE
    recovery = RecoveryKind.RETRY_LATER


class GmailRequestRejected(GmailFault):
    """400 or 404 - a request this client built that Gmail refused.

    Surfaced as `partial_source_failure` because that is D.11's entry for a sub-request
    failing inside a fan-out, which is where a 400/404 actually reaches a user: one thread
    of twelve is gone and the other eleven are still a truthful answer.

    **When the whole call is one request, the whole call is gone**, and the recovery is
    `NONE`: retrying the same identifier returns the same 404, and no narrower form of the
    request names a different identifier. The observed instance (2026-09-21) was a thread
    identifier passed to `messages.get`. Whether that identifier is a thread is **not**
    probed here and not asserted on the decline: the server does not reinterpret what the
    caller named, it says which endpoint refused it and stops.

    The `history.list` 404 is **not** this: an expired `startHistoryId` is a declared
    re-baseline (AD D.9) and is handled in the client as a result, not an exception.
    """

    code = ErrorCode.PARTIAL_SOURCE_FAILURE
    recovery = RecoveryKind.NONE


class GmailTransportFailure(GmailFault):
    """The request never completed: connection error, timeout, or a refused host.

    `httpx` raises a dozen distinct exception types and `EgressBlocked` is a thirteenth;
    all of them arrive here so that a caller's single `except GmailFault` is the truth.
    The originating exception is kept as `__cause__` - it is a network condition, not a
    response, so it carries nothing mail-derived.

    The recovery depends on which: a connection that did not complete may complete later,
    and a host the egress allowlist refuses will be refused every time, so `recovery` reads
    the cause rather than claiming one answer for both.
    """

    code = ErrorCode.UPSTREAM_UNAVAILABLE

    @property
    def recovery(self) -> RecoveryKind:  # type: ignore[override]
        blocked = isinstance(self.__cause__, EgressBlocked)
        return RecoveryKind.NONE if blocked else RecoveryKind.RETRY_LATER


class GmailResponseUnexpected(GmailFault):
    """The response was well-formed but describes a different call than the one made.

    The instance that matters today: `messages.get(id=X)` answering with a message whose
    `id` is not `X`. Nothing downstream re-checks that, and an id substituted here would
    enter disclosure as though the caller had asked for it.
    """

    code = ErrorCode.PARTIAL_SOURCE_FAILURE
    recovery = RecoveryKind.NONE


class GmailDeadlineExceeded(GmailFault):
    """The call's wall-clock allowance ran out before this request could be started or
    completed (2026-09-21).

    Raised by `GmailClient._request` when the bound `Deadline` has less than
    `MIN_ATTEMPT_MS` left before an attempt, or when an attempt's bounded HTTP timeout fires
    and the deadline is spent. It is the enforcement of `max_server_ms` at the network layer:
    before it, the cap bounded retry sleeps and nothing else, so a stalled Gmail request or a
    long sequential read ran to `attempts × timeout` per message with the cap constraining
    only the pauses between them.

    `budget_exhausted` is the D.11 code, because that is what happened: a declared budget was
    spent. In a fan-out it would be in-band; nothing in the retrieval stack catches it today,
    so it aborts the call and the surface declines with the same narrowing chain a size
    refusal gets - fewer messages, or a shallower view, or a narrower search - which is a
    strictly smaller request that costs strictly less time. When no narrowing exists (a
    single `threads.get`), the recovery is `RETRY_LATER` and the decline says so.

    **`phase` says which wait spent the allowance** (second repair, same day), and the
    recovery reads it. `REQUEST` is a Gmail request: connect, handshake, the wait for the
    response or the reading of its body, or the sum of them across a sequential read, and a
    narrower call is a cheaper one. `CREDENTIAL` is the token exchange that runs before the
    first attempt: no narrowing of the Gmail request makes the token endpoint answer sooner,
    so the recovery is `RETRY_LATER`, and it is emphatically not `REAUTHORISE` - a slow
    token endpoint is not a refused grant, and sending the owner to `mailweave auth login`
    for it would be the same misreport R-MCP-006 closed, from the other side.
    """

    code = ErrorCode.BUDGET_EXHAUSTED

    def __init__(
        self,
        message: str,
        *,
        endpoint: GmailEndpoint,
        attempts: int = 0,
        budget_ms: float,
        elapsed_ms: float,
        phase: DeadlinePhase = DeadlinePhase.REQUEST,
    ) -> None:
        super().__init__(message, endpoint=endpoint, attempts=attempts)
        self.budget_ms = budget_ms
        self.elapsed_ms = elapsed_ms
        self.phase = phase

    @property
    def recovery(self) -> RecoveryKind:  # type: ignore[override]
        if self.phase is DeadlinePhase.CREDENTIAL:
            return RecoveryKind.RETRY_LATER
        return RecoveryKind.NARROW

    @property
    def overrun_ms(self) -> float:
        """How far past the allowance the call was when this was raised. Zero when the
        deadline was read as spent before anything ran over it."""
        return max(0.0, self.elapsed_ms - self.budget_ms)
