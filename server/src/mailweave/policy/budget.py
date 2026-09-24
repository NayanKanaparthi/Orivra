"""WS-10's budgets: the A.7 caps enforced in code, under a process-wide governor.

**What a budget is here, and what it is not.** `CallMeter` counts; this refuses. The
separation is AD A.5b's and it is load-bearing: a counter that could refuse would put the
ladder's policy inside the transport, where nobody reviewing the ladder would look for it.
So an accountant *reads* a meter and a clock, and answers one question - may this rung spend
what it is about to spend - with an answer that names the cap when it is no.

**The three things a cap must produce, every time, or it is not enforced.** AD A.7's own
sentence: "Exhausting any cap produces a `budget` block naming the cap, the rungs not
reached, and the affordances that would reach them - **and, per A.7a, a `withheld` record for
every hit the cap prevented from being disclosed**." So a `CapBreach` carries the cap's name
*and* the call that would raise it, and it is a type rather than a boolean, because a
boolean cannot carry either. The withheld record is the ledger's and stays there
(`DispositionLedger` is WS-04's; this module does no disposition accounting).

**Every refusal is before the spend, never after it.** `charge_for` is asked before the call
goes out. A budget checked afterwards is a report, and A.7's rule is that a budget is
"never accepted-and-then-overrun".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Final

from pydantic import JsonValue

from mailweave.constants import (
    FLOOR_QUOTA_UNITS,
    MAX_API_CALLS,
    MAX_BODY_FETCHES_L1,
    MAX_CONCURRENT_QUERIES,
    MAX_HIT_THREADS,
    MAX_HTTP_REQUESTS,
    MAX_POOL_MESSAGES,
    MAX_POOL_THREADS,
    MAX_QUOTA_UNITS,
    MAX_QUOTA_UNITS_SEMANTIC,
    MAX_RECENCY_FETCH,
    MAX_RERANK_PAIRS,
    MAX_SEMANTIC_MS,
    MAX_SERVER_MS,
    MAX_SOURCE_THREADS,
)
from mailweave.envelope.vocab import BudgetCapName, NotTriedWhy, ToolName, WithheldCap
from mailweave.envelope.wire import Affordance, BudgetBlock, BudgetClamp
from mailweave.gmail.meter import CallMeter
from mailweave.gmail.rates import PUBLISHED_QUOTA_UNITS, GmailEndpoint

#: The caps that stop the clock rather than the counter. Kept as a set because the
#: `not_tried` reason for a time cap is `timeout` and for every other cap it is `cap`, and
#: deriving that from membership is one fact in one place (R-ARCH-031).
TIME_CAPS: Final[frozenset[BudgetCapName]] = frozenset(
    {BudgetCapName.MAX_SERVER_MS, BudgetCapName.MAX_SEMANTIC_MS}
)

#: The `withheld` cap each budget cap files a record under (AD A.7a). Only the caps that can
#: stop a response mid-flight are here; the rest are shape caps whose withheld records are
#: filed by the code that applies them.
WITHHELD_CAP_OF: Final[dict[BudgetCapName, WithheldCap]] = {
    BudgetCapName.MAX_QUOTA_UNITS: WithheldCap.MAX_QUOTA_UNITS,
    BudgetCapName.MAX_API_CALLS: WithheldCap.MAX_API_CALLS,
    BudgetCapName.MAX_HTTP_REQUESTS: WithheldCap.MAX_API_CALLS,
    BudgetCapName.MAX_SERVER_MS: WithheldCap.MAX_SERVER_MS,
    BudgetCapName.MAX_SEMANTIC_MS: WithheldCap.MAX_SEMANTIC_MS,
}


class BudgetRefused(Exception):
    """The process-wide governor declined to admit this query at all (AD A.5c, D.11)."""

    def __init__(self, message: str, *, cap: BudgetCapName) -> None:
        super().__init__(message)
        self.cap = cap


@dataclass(frozen=True)
class CapBreach:
    """One cap, exhausted, with everything AD A.7 requires a caller to be told.

    A boolean would carry none of it. The three fields are the three the architecture names:
    which cap, what it would take to get past it, and - through `why` - which member of the
    `not_tried` vocabulary this makes the rungs it stopped.
    """

    cap: BudgetCapName
    #: The call that would reach what this cap prevented. AD-03: a cap without an affordance
    #: is a dead end reported as a fact.
    affordance: Affordance
    limit: int
    spent: int

    @property
    def why(self) -> NotTriedWhy:
        """`timeout` for the two time caps, `cap` for the rest. Derived, never listed twice."""
        return NotTriedWhy.TIMEOUT if self.cap in TIME_CAPS else NotTriedWhy.CAP

    @property
    def withheld_cap(self) -> WithheldCap:
        """The `withheld` record's cap name, so A.7a's clause is not a second decision."""
        return WITHHELD_CAP_OF[self.cap]

    def rendered(self) -> str:
        return f"{self.cap.value}: {self.spent} of {self.limit}"


def _raise_to(cap: BudgetCapName, value: int, *, query: str | None) -> Affordance:
    """The affordance that raises one cap. One shape, so no cap can acquire a private one.

    `query` is the caller's own `q`, carried since round 24 because `mailweave_search`
    requires one: `{"budget": {...}}` alone names a delta and not a call, and contract R-07
    asks for a call. `None` is still representable - an accountant constructed without a
    query, which is every unit test of this module - and the affordance then carries the
    budget alone, which is what it always did.
    """
    budget: JsonValue = {cap.value: value}
    if query is None:
        return Affordance(tool=ToolName.SEARCH, args={"budget": budget})
    return Affordance(tool=ToolName.SEARCH, args={"query": query, "budget": budget})


@dataclass(frozen=True)
class BudgetRequest:
    """What a caller asked for. Every field optional; `None` means "the published default".

    Separate from `AppliedBudget` because the floor clamp has to be able to report both
    numbers (AD A.7's `budget_clamped{requested, applied, why}`), and one mutable object
    holding "what you asked for" and "what you got" in turn can only report the second.
    """

    max_quota_units: int | None = None
    max_api_calls: int | None = None
    max_http_requests: int | None = None
    max_server_ms: int | None = None
    max_semantic_ms: int | None = None
    #: **Round 27, R-MCP-025.** `max_hit_threads` is the cap this server's own decline
    #: affordance narrows a search by, and it was not a field a caller could set: the
    #: `retry_with` a decline handed back was refused by the tool that minted it with
    #: `-32602 unknown budget key`, which is contract I-2's proof-of-violation (c) - an
    #: affordance that cannot execute. It is here for the reason the `max_ms` /
    #: `max_server_ms` pair below is: every cap name an affordance this server mints can
    #: carry has to be a cap the tool it names accepts.
    max_hit_threads: int | None = None
    max_recency_fetch: int | None = None


@dataclass(frozen=True)
class AppliedBudget:
    """The caps this query actually runs under, after AD A.7's recoverability-floor clamp.

    **The clamp is upward and it is declared** (AD-03, D.11). A client may lower budgets and
    may not lower them below `floor_quota_units = 845`, which is L0 + L1 + the hit maps +
    L1b + L2 + L3 + the RetrievalReport - the cost of a response that can still be recovered
    from. A request under the floor is raised to it and the raise is reported in the
    response's `budget` block; it is never accepted-and-then-overrun, and never silently
    refused. `BudgetClamp`'s own validators refuse a clamp that lowers and a clamp landing
    below the floor, so the *only* representable clamp is the one A.7 describes.

    `semantic` widens `max_quota_units` to A.7's semantic-escalated figure. It is a property
    of the query's route rather than of the caller's request, so it is applied when the
    policy decides to escalate rather than accepted as an argument.
    """

    max_quota_units: int
    max_api_calls: int
    max_http_requests: int
    max_server_ms: int
    max_semantic_ms: int
    max_hit_threads: int = MAX_HIT_THREADS
    max_source_threads: int = MAX_SOURCE_THREADS
    max_pool_threads: int = MAX_POOL_THREADS
    max_pool_messages: int = MAX_POOL_MESSAGES
    max_rerank_pairs: int = MAX_RERANK_PAIRS
    max_recency_fetch: int = MAX_RECENCY_FETCH
    max_body_fetches: int = MAX_BODY_FETCHES_L1
    clamp: BudgetClamp | None = None

    @property
    def block(self) -> BudgetBlock:
        """The response's `budget` block. The clamp is the only thing in it that can be set."""
        return BudgetBlock(clamped=self.clamp)


def apply_floor(request: BudgetRequest, *, semantic: bool = False) -> AppliedBudget:
    """AD A.7's caps, with the requested quota budget clamped **up** to the floor.

    Three cases and they are three different sentences, which is why this is a function with
    a test per case rather than a `max()` inline at a call site:

      * no request - the published default applies and there is no clamp to declare;
      * a request at or above the floor - honoured verbatim, no clamp;
      * a request below the floor - raised to exactly `FLOOR_QUOTA_UNITS`, and
        `budget_clamped{requested, applied, why}` says so on the wire.

    A request *above* the published default is honoured too. A.7 clamps from below only: the
    floor exists so a response stays recoverable, and there is no corresponding ceiling in
    the architecture for a caller who wants to spend more of their own quota.
    """
    default_quota = MAX_QUOTA_UNITS_SEMANTIC if semantic else MAX_QUOTA_UNITS
    requested = request.max_quota_units
    clamp: BudgetClamp | None = None
    if requested is None:
        applied_quota = default_quota
    elif requested >= FLOOR_QUOTA_UNITS:
        applied_quota = requested
    else:
        applied_quota = FLOOR_QUOTA_UNITS
        clamp = BudgetClamp(
            requested=requested,
            applied=FLOOR_QUOTA_UNITS,
            why=(
                f"a budget below the published recoverability floor of {FLOOR_QUOTA_UNITS} "
                "quota units cannot pay for L0, L1, the hit-bearing thread maps, L1b, L2, L3 "
                "and the retrieval report, so a response under it could not be recovered "
                "from. Raised to the floor rather than accepted and overrun (AD A.7, AD-03)"
            ),
        )
    return AppliedBudget(
        max_quota_units=applied_quota,
        max_api_calls=request.max_api_calls if request.max_api_calls is not None else MAX_API_CALLS,
        max_http_requests=(
            request.max_http_requests
            if request.max_http_requests is not None
            else MAX_HTTP_REQUESTS
        ),
        max_server_ms=(
            request.max_server_ms if request.max_server_ms is not None else MAX_SERVER_MS
        ),
        max_semantic_ms=(
            request.max_semantic_ms if request.max_semantic_ms is not None else MAX_SEMANTIC_MS
        ),
        # **Lowering only** (round 27, R-MCP-025), the direction `max_disclosed_tokens` runs
        # in and for the same reason: the published figure is the most this server will map,
        # so a caller asking for more gets the published one and a caller asking for fewer
        # gets what they asked for. The threads it does not map are not dropped - they become
        # `withheld` records naming this cap, with the thread-map call that reaches them.
        max_hit_threads=(
            min(request.max_hit_threads, MAX_HIT_THREADS)
            if request.max_hit_threads is not None
            else MAX_HIT_THREADS
        ),
        # **`max_recency_fetch` raises as well as lowers, and it is the one width key that
        # does.** The others bound how much of what Gmail already returned this server will
        # *disclose*; this one bounds how many messages it will fetch to find out whether
        # they answer the query at all, and D.9 prices that at 20 u each. A caller willing to
        # spend their own quota to see arrivals the index has not caught up with is spending
        # it on retrieval, not on a wider response - and the `max_quota_units` cap still
        # bounds the total either way.
        max_recency_fetch=(
            request.max_recency_fetch
            if request.max_recency_fetch is not None
            else MAX_RECENCY_FETCH
        ),
        clamp=clamp,
    )


#: What one rung is about to spend, in the two currencies a cap is measured in. Endpoints
#: rather than units, so the quota arithmetic is `PUBLISHED_QUOTA_UNITS`' and not a second
#: copy of it (AD A.5b: a unit figure is a multiplication of a published table).
Spend = tuple[GmailEndpoint, ...]


class BudgetAccountant:
    """One query's budget, nested inside the process-wide governor (AD A.7, A.5c).

    Reads a `CallMeter` for what has been spent and a monotonic clock for how long it has
    taken. Refuses **before** the spend, and every refusal is a `CapBreach` naming the cap
    and the call that would raise it.

    The clock is injected. A test that measured real elapsed time would be a test whose
    result depends on the machine it runs on, and the timeout contract is the part of WS-10
    that most needs to be executed rather than reasoned about.
    """

    __slots__ = (
        "_budget",
        "_caps_hit",
        "_lexical_started_ms",
        "_meter",
        "_now_ms",
        "_query",
        "_semantic",
        "_semantic_spent_ms",
        "_started_ms",
    )

    def __init__(
        self,
        meter: CallMeter,
        budget: AppliedBudget,
        *,
        now_ms: Callable[[], float],
        query: str | None = None,
    ) -> None:
        self._meter = meter
        self._budget = budget
        self._now_ms = now_ms
        #: The caller's own `q`, so a cap's affordance is a call rather than a delta. Optional
        #: because this class is constructed in unit tests that have no query; the affordance
        #: then carries the budget alone, exactly as it did before round 24.
        self._query = query
        self._started_ms = now_ms()
        self._lexical_started_ms = self._started_ms
        self._caps_hit: list[BudgetCapName] = []
        self._semantic = False
        self._semantic_spent_ms = 0.0

    @property
    def budget(self) -> AppliedBudget:
        return self._budget

    @property
    def caps_hit(self) -> tuple[BudgetCapName, ...]:
        """Every cap this query exhausted, in the order it hit them, each named once."""
        return tuple(self._caps_hit)

    @property
    def elapsed_ms(self) -> float:
        """Against whichever cap is current. Semantic time accumulates across entries."""
        current = self._now_ms() - self._started_ms
        return self._semantic_spent_ms + current if self._semantic else current

    @property
    def semantic_spent_ms(self) -> float:
        """Semantic wall clock this query has already left behind, in completed intervals."""
        return self._semantic_spent_ms

    def enter_semantic(self) -> None:
        """Switch the wall-clock cap to `max_semantic_ms` (AD A.7: "separate by design").

        L5 and L6 are CPU-bound and L0-L4 are RTT-bound, so one deadline over both would
        either strangle the semantic rung or give the lexical ones six seconds of slack. The
        two are separate caps in the architecture and separate here.

        **`max_semantic_ms` bounds the query's semantic work, not one rung's.** L5 runs
        before the response is assembled and L6 runs inside the assembly, so they enter and
        leave this clock separately - and a version that reset the start instant on each
        entry would give each rung its own full six seconds, which is a budget of twelve
        wearing the published number's name. `leave_semantic` therefore *accumulates*, and
        `elapsed_ms` under the semantic cap reads accumulated-plus-current.
        """
        if self._semantic:
            return
        self._semantic = True
        self._lexical_started_ms = self._started_ms
        self._started_ms = self._now_ms()

    def leave_semantic(self) -> None:
        """Switch back to `max_server_ms`, **without charging it for the semantic work**.

        "Separate by design" cuts both ways and the second half is easy to miss. L5 runs
        between the lexical ladder and disclosure assembly, and assembly is RTT-bound work
        under `max_server_ms` like the ladder before it - so something has to put the server
        clock back, and it has to put it back where it *would* have been had the semantic
        rung taken no time at all. Restoring the saved start instant would charge the server
        budget for six seconds of CPU work the architecture says it does not pay for;
        leaving the semantic cap in place would time the thread maps against a budget
        written for embeddings. The start instant therefore moves forward by exactly the
        semantic interval, which is the only arithmetic that makes both caps mean what A.7
        says they mean.

        Idempotent, because the rung has several early returns and each one leaves.
        """
        if not self._semantic:
            return
        self._semantic = False
        interval = self._now_ms() - self._started_ms
        self._semantic_spent_ms += interval
        self._started_ms = self._lexical_started_ms + interval

    def _time_cap(self) -> tuple[BudgetCapName, int]:
        return (
            (BudgetCapName.MAX_SEMANTIC_MS, self._budget.max_semantic_ms)
            if self._semantic
            else (BudgetCapName.MAX_SERVER_MS, self._budget.max_server_ms)
        )

    def _record(self, cap: BudgetCapName) -> None:
        if cap not in self._caps_hit:
            self._caps_hit.append(cap)

    def check(self, spend: Spend = ()) -> CapBreach | None:
        """May the query spend `spend` next? `None` for yes, a `CapBreach` for no.

        **The order of the checks is the order of the answers' usefulness, and the time cap
        comes first.** A query that has run out of time has run out however cheap the next
        call is, and reporting `max_api_calls` for a request that timed out would send the
        caller to raise the wrong number. Every cap that fires is recorded, so a response
        that hit two names two.
        """
        time_cap, time_limit = self._time_cap()
        elapsed = self.elapsed_ms
        if elapsed >= time_limit:
            self._record(time_cap)
            return CapBreach(
                cap=time_cap,
                affordance=_raise_to(time_cap, time_limit * 2, query=self._query),
                limit=time_limit,
                spent=int(elapsed),
            )
        reading = self._meter.reading()
        units = sum(PUBLISHED_QUOTA_UNITS[endpoint] for endpoint in spend)
        checks: tuple[tuple[BudgetCapName, int, int], ...] = (
            (
                BudgetCapName.MAX_QUOTA_UNITS,
                self._budget.max_quota_units,
                reading.quota_units_diagnostic + units,
            ),
            (
                BudgetCapName.MAX_API_CALLS,
                self._budget.max_api_calls,
                reading.api_calls + len(spend),
            ),
            (
                BudgetCapName.MAX_HTTP_REQUESTS,
                self._budget.max_http_requests,
                reading.http_requests + len(spend),
            ),
        )
        for cap, limit, would_be in checks:
            if would_be > limit:
                self._record(cap)
                return CapBreach(
                    cap=cap,
                    affordance=_raise_to(cap, limit * 2, query=self._query),
                    limit=limit,
                    spent=would_be,
                )
        return None


@dataclass
class Governor:
    """The process-wide half of AD A.5c: how many queries may be in flight at once.

    Two states and they are two different D.11 codes, which is why this returns one or
    raises the other rather than blocking: `process_quota_wait` is a query admitted after a
    wait, `process_quota_refused` is one that was not admitted. A governor that silently
    queued would report neither, and the caller would see latency with no name on it.

    `max_concurrent_queries` is 2 (AD A.7). This is a counter rather than a semaphore
    because MailWeave's MCP surface is single-process and stdio-serial; a semaphore would
    imply a blocking wait this server never performs.
    """

    limit: int = MAX_CONCURRENT_QUERIES
    _in_flight: int = field(default=0, init=False)

    @property
    def in_flight(self) -> int:
        return self._in_flight

    def admit(
        self, request: BudgetRequest | None = None, *, meter: CallMeter, now_ms: Callable[[], float]
    ) -> BudgetAccountant:
        """Admit one query and hand it its own accountant, or refuse with the D.11 code.

        The per-query accountant is created **here** rather than by the caller, so a query
        that was never admitted has no accountant to spend through. That is the nesting AD
        A.7 asks for expressed as a construction rule rather than as a convention.
        """
        if self._in_flight >= self.limit:
            raise BudgetRefused(
                f"this process is already serving {self._in_flight} concurrent queries and "
                f"max_concurrent_queries is {self.limit}; the query was refused rather than "
                "queued, so the wait is not reported as latency with no name on it "
                "(AD A.5c, D.11 process_quota_refused)",
                cap=BudgetCapName.PROCESS_QUOTA_REFUSED,
            )
        self._in_flight += 1
        return BudgetAccountant(meter, apply_floor(request or BudgetRequest()), now_ms=now_ms)

    def release(self) -> None:
        self._in_flight = max(0, self._in_flight - 1)

    def query(
        self, request: BudgetRequest | None = None, *, meter: CallMeter, now_ms: Callable[[], float]
    ) -> _AdmittedQuery:
        """`with governor.query(...) as accountant:` - admission and release as one scope."""
        return _AdmittedQuery(self, request, meter, now_ms)


class _AdmittedQuery:
    """The context manager `Governor.query` returns. Releases even when the query raises."""

    __slots__ = ("_governor", "_meter", "_now_ms", "_request")

    def __init__(
        self,
        governor: Governor,
        request: BudgetRequest | None,
        meter: CallMeter,
        now_ms: Callable[[], float],
    ) -> None:
        self._governor = governor
        self._request = request
        self._meter = meter
        self._now_ms = now_ms

    def __enter__(self) -> BudgetAccountant:
        return self._governor.admit(self._request, meter=self._meter, now_ms=self._now_ms)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._governor.release()
