"""Does a candidate `max_server_ms` change what an ordinary search comes back with?

**The question, exactly.** PF-21 measured the network: the slowest endpoint's p90 is the unit
a wall-clock deadline is spent in, and `MAX_HTTP_REQUESTS x that p90` is an upper bound on
what a deadline would ever need to be. A bound is not a default. This runs the same neutral
searches under the **shipped** figure, a candidate and that bound, and reports what differed.

**Why there are three arms and not two.** The first version of this module compared the
candidate against the bound alone, on queries that made four Gmail requests, and reported
"adoptable" - which was true and meaningless: at four requests neither deadline was reached,
so the two were never distinguished. A comparison that cannot fail is not a comparison. The
shipped 2,000 ms is now an arm precisely so the run has to *demonstrate* that the deadline
matters at all before it may conclude anything about which larger value to take, and
`judge` refuses adoption when the baseline behaved the same as the other two.

**What it will not do.** It names no evaluation question, reads no evaluator file, and takes
its queries from the caller apart from one pre-registered structural query. It reports; it
does not choose. It attributes a refusal to a cause only from what the refusal itself said.

Numbers and closed-vocabulary tokens, plus the ids of a synthetic test mailbox - a reviewer
has to be able to check that two arms returned the *same* evidence. No mail text is recorded.
"""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from mailweave.constants import HOST_RESULT_CHAR_CAP, MAX_HTTP_REQUESTS
from mailweave.envelope.measure import rendered_chars
from mailweave.envelope.vocab import BudgetCapName, Depth
from mailweave.surface.partition import rendered_of
from mailweave.surface.rendering import is_the_recommended_expansion
from mailweave.surface.server import call
from mailweave.surface.service import MailweaveService

#: The shipped figure, as an arm. Passed explicitly rather than by omitting the argument, so
#: all three arms travel the identical code path and differ in one integer.
#: **Pinned to 2,000, the value that shipped when runs 1, 2 and 3 were taken.**
#:
#: This read `MAX_SERVER_MS` so the baseline arm was always whatever shipped, and that was
#: right while the shipped value was the thing under test. The owner's adoption of 7,700 on
#: 2026-09-09 makes it wrong: `ARMS` would become `(7,700, 7,700, 12,300)`, two identical arms
#: and a counterbalanced order over a duplicate, which is not a comparison. Pinning the
#: historical figure keeps every record already written meaning what it said. A future run
#: against a new candidate re-registers this deliberately, as round 30 re-registered the
#: queries.
BASELINE_MS = 2_000
CANDIDATE_MS = 7_700
UPPER_BOUND_MS = 12_300

#: Ascending, which is the order they are *reported* in and never the order they are *run* in.
ARMS: tuple[int, ...] = (BASELINE_MS, CANDIDATE_MS, UPPER_BOUND_MS)

#: How many times each (query, arm) pair is measured. Three is the smallest number that lets
#: every arm occupy every position in the running order exactly once, which is the point:
#: one network hiccup lands on one position, not on one arm.
DEFAULT_REPEATS = 3


@dataclass(frozen=True)
class QuerySpec:
    """One search to run under every arm, and the budget it is run with.

    `max_hit_threads` is here because the deadline only becomes visible on a query that makes
    many sequential calls, and on a small mailbox the way to get one is to let a wide query
    answer instead of being refused for width. It is a published budget key, so this is an
    argument a client could send, not a lever this harness reaches around the server for.
    """

    query: str
    max_hit_threads: int | None = None

    @property
    def label(self) -> str:
        if self.max_hit_threads is None:
            return self.query
        return f"{self.query} [hit_threads={self.max_hit_threads}]"

    def budget(self, deadline_ms: int) -> dict[str, int]:
        budget = {"max_server_ms": deadline_ms}
        if self.max_hit_threads is not None:
            budget["max_hit_threads"] = self.max_hit_threads
        return budget


#: **Pre-registered before the run.** Date operators and a published budget key: they need no
#: knowledge of what is in the mailbox, and the cap is what makes a wide query answerable so
#: that its body fetches and thread maps actually spend the clock. Registered here rather than
#: passed on a command line so they cannot be swapped for something that behaved better.
#:
#: **Re-registered for run 3 (round 30), and the reason is on the record.** Runs 1 and 2 asked
#: whether a longer deadline changed anything and could not tell, because every arm declined on
#: the host character cap rather than on the clock - R-MCP-033. That is fixed and the broad
#: response now serves at 8,748 characters, so the clock is finally the thing being measured.
#: The object of study is therefore the exact call that failed live v0.1 acceptance, at the
#: width it failed at, rather than the width-3 approximation of it:
#:
#:   * `after:2026/09/01 [hit_threads=1]` - the acceptance call, verbatim. Under the shipped
#:     2,000 ms it returned zero sources and zero matched rows in 2,252 ms over six requests
#:     (`validation-records/rmcp033-acceptance-hit-threads-1.json`).
#:   * `after:2026/09/01 [hit_threads=3]` - carried forward unchanged from runs 1 and 2, so the
#:     new record is comparable with the two that came before it rather than a fresh start.
#:   * `after:2026/09/08 [hit_threads=1]` - **the narrow control.** Its date range is a subset
#:     of the other two's in any mailbox, so it is narrower by construction and needs no more
#:     knowledge of the mailbox than they do. It carries **the acceptance call's width**, which
#:     makes breadth the only difference between the two and is a correction: at the published
#:     width of twelve it could issue twelve `threads.get` calls where the acceptance call
#:     issues one, so the "control" could be more deadline-constrained than the thing it
#:     controls for (R-V30-007). It answers "does the chosen default cost latency or change
#:     results where the deadline was never the constraint": a candidate that is right leaves
#:     this query's evidence identical to the baseline's and does not spend materially longer
#:     producing it.
#:
#: The arms are **not** re-registered: 2,000 shipped, 7,700 candidate, 12,300 upper bound, as
#: registered in round 28. Adding an arm after seeing a failure is how a measurement becomes a
#: justification.
PRE_REGISTERED: tuple[QuerySpec, ...] = (
    QuerySpec("after:2026/09/01", max_hit_threads=1),
    QuerySpec("after:2026/09/01", max_hit_threads=3),
    QuerySpec("after:2026/09/08", max_hit_threads=1),
)

#: **The one query whose result the adoption rule is actually about** (round 30, R-V30-008).
#: `informative` is counted per label, so "at least one informative query" bound *some* label
#: and not this one: a run where the acceptance call returned zero rows under all three arms
#: while the other two labels behaved could return `adoptable: true`. That is the exact failure
#: the re-registration exists to prevent, so the acceptance label is named here and the verdict
#: requires it by name.
ACCEPTANCE_LABEL: str = "after:2026/09/01 [hit_threads=1]"

#: Cap names a refusal's own text may name. Used only to record *what the refusal said*, never
#: to decide what caused it.
_CAP_NAMES: tuple[str, ...] = tuple(cap.value for cap in BudgetCapName)


@dataclass(frozen=True)
class Decline:
    """What a refusal actually said, recorded verbatim enough to tell causes apart.

    **No cause is inferred here.** Round 28's first run guessed that a pair of refusals were
    R-MCP-033's width limit; that was probably right and it was still a guess, so this records
    the code, the remediation text and the retry the response offered, and lists which cap
    names the remediation itself mentions. A reader attributes; this reports.
    """

    code: str | None
    remediation: str
    retry_with: Mapping[str, Any] | None
    caps_named_in_remediation: tuple[str, ...]

    @classmethod
    def of(cls, payload: Mapping[str, Any]) -> Decline:
        remediation = str(payload.get("remediation") or "")
        return cls(
            code=payload.get("code"),
            remediation=remediation,
            retry_with=payload.get("retry_with"),
            caps_named_in_remediation=tuple(name for name in _CAP_NAMES if name in remediation),
        )

    def as_record(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "remediation": self.remediation,
            "retry_with": dict(self.retry_with) if self.retry_with else None,
            "caps_named_in_remediation": list(self.caps_named_in_remediation),
        }


@dataclass(frozen=True)
class ArmResult:
    """One search, under one deadline, on one repeat."""

    label: str
    deadline_ms: int
    repeat: int
    #: Where this arm sat in that repeat's running order. Recorded so a reader can check for
    #: an order effect rather than take the counterbalancing on trust.
    position: int
    decline: Decline | None
    evidence: tuple[tuple[str, str], ...]
    partial: bool
    withheld: tuple[tuple[str, str], ...]
    not_included: int
    budget_caps_hit: tuple[str, ...]
    http_requests: int
    api_calls: int
    quota_units: int
    #: The two clocks, kept apart: the search itself, and the follow-up expansion call which is
    #: a second tool call and has nothing to do with the search's deadline.
    search_wall_ms: int
    expansion_wall_ms: int | None
    rendered_chars: int
    recommendation: Mapping[str, Any] | None
    recommendation_executed: bool | None
    recommendation_returned: tuple[tuple[str, str], ...]

    @property
    def declined(self) -> bool:
        return self.decline is not None

    @property
    def hit_the_clock(self) -> bool:
        return BudgetCapName.MAX_SERVER_MS.value in self.budget_caps_hit

    def as_record(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "deadline_ms": self.deadline_ms,
            "repeat": self.repeat,
            "position": self.position,
            "declined": self.declined,
            "decline": self.decline.as_record() if self.decline else None,
            "evidence": [list(pair) for pair in self.evidence],
            "partial": self.partial,
            "withheld": [list(pair) for pair in self.withheld],
            "not_included_sources": self.not_included,
            "budget_caps_hit": list(self.budget_caps_hit),
            "http_requests": self.http_requests,
            "api_calls": self.api_calls,
            "quota_units": self.quota_units,
            "search_wall_ms": self.search_wall_ms,
            "expansion_wall_ms": self.expansion_wall_ms,
            "rendered_chars": self.rendered_chars,
            "host_char_cap": HOST_RESULT_CHAR_CAP,
            "recommendation": dict(self.recommendation) if self.recommendation else None,
            "recommendation_executed": self.recommendation_executed,
            "recommendation_returned": [list(p) for p in self.recommendation_returned],
        }


def _evidence_of(payload: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (row["id"], row["depth"])
            for source in payload.get("sources", ())
            for row in source.get("messages", ())
            if row.get("role") == "matched"
        )
    )


def _rows_of(payload: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(
        (row["id"], row["depth"])
        for source in payload.get("sources", ())
        for row in source.get("messages", ())
    )


def run_arm(
    service: MailweaveService,
    *,
    spec: QuerySpec,
    deadline_ms: int,
    repeat: int,
    position: int,
    execute_recommendation: bool,
) -> ArmResult:
    """One search under one deadline, through the shipped `call` - the only path a client has.

    The deadline is a **budget argument**, not an edited constant: `apply_floor` clamps
    `max_server_ms` from below only, so a caller may raise it, and a validation that edited the
    published figure would be measuring a build nobody has reviewed.
    """
    started = time.monotonic()
    result = call(
        service, "mailweave_search", {"query": spec.query, "budget": spec.budget(deadline_ms)}
    )
    search_wall_ms = int((time.monotonic() - started) * 1000)
    payload = result.structured_content or {}
    if result.is_error:
        return ArmResult(
            label=spec.label,
            deadline_ms=deadline_ms,
            repeat=repeat,
            position=position,
            search_wall_ms=search_wall_ms,
            decline=Decline.of(payload),
            evidence=(),
            partial=False,
            withheld=(),
            not_included=0,
            budget_caps_hit=(),
            http_requests=-1,
            api_calls=-1,
            quota_units=-1,
            expansion_wall_ms=None,
            rendered_chars=-1,
            recommendation=None,
            recommendation_executed=None,
            recommendation_returned=(),
        )
    mirrored = rendered_of(result)
    report = payload.get("retrieval_report") or {}
    counters = report.get("counters") or {}
    offers = [
        offer
        for offer in payload.get("affordances", ())
        if is_the_recommended_expansion(payload, offer)
    ]
    recommendation = offers[0] if offers else None
    executed: bool | None = None
    expansion_wall_ms: int | None = None
    returned: tuple[tuple[str, str], ...] = ()
    if recommendation is not None and execute_recommendation:
        began = time.monotonic()
        follow_up = call(service, recommendation["tool"], dict(recommendation["args"]))
        expansion_wall_ms = int((time.monotonic() - began) * 1000)
        executed = not follow_up.is_error
        if executed:
            named = set(recommendation["args"]["message_ids"])
            returned = tuple(
                pair for pair in _rows_of(follow_up.structured_content or {}) if pair[0] in named
            )
    return ArmResult(
        label=spec.label,
        deadline_ms=deadline_ms,
        repeat=repeat,
        position=position,
        search_wall_ms=search_wall_ms,
        decline=None,
        evidence=_evidence_of(payload),
        partial=bool(payload.get("partial")),
        withheld=tuple((record["id"], record["cap"]) for record in payload.get("withheld", ())),
        not_included=len(payload.get("not_included_sources", ())),
        budget_caps_hit=tuple(report.get("budget_caps_hit") or ()),
        http_requests=int(counters.get("http_requests", -1)),
        api_calls=int(counters.get("api_calls", -1)),
        quota_units=int(counters.get("quota_units", -1)),
        expansion_wall_ms=expansion_wall_ms,
        rendered_chars=rendered_chars(mirrored.structured, mirrored.text),
        recommendation=recommendation,
        recommendation_executed=executed,
        recommendation_returned=returned,
    )


def running_order(repeat: int, query_index: int) -> tuple[int, ...]:
    """The arms, rotated by repeat **and** by query. A Latin square in both directions.

    Warm state is the bias this exists to defeat: whichever arm runs last meets the warmest
    connection, so no arm may consistently run last. Rotating on the sum of the two indices
    means that over three repeats and any number of queries each arm occupies each position
    an equal number of times, and never the same position twice in a row for one query.
    """
    shift = (repeat + query_index) % len(ARMS)
    return ARMS[shift:] + ARMS[:shift]


@dataclass
class Comparison:
    arms: list[ArmResult] = field(default_factory=list)

    def observations(self, label: str, deadline_ms: int) -> list[ArmResult]:
        return [arm for arm in self.arms if arm.label == label and arm.deadline_ms == deadline_ms]

    @property
    def labels(self) -> list[str]:
        seen: list[str] = []
        for arm in self.arms:
            if arm.label not in seen:
                seen.append(arm.label)
        return seen


def compare(
    service: MailweaveService,
    *,
    specs: Sequence[QuerySpec],
    repeats: int = DEFAULT_REPEATS,
    execute_recommendation: bool = True,
) -> Comparison:
    """Every query under every arm, `repeats` times, counterbalanced."""
    comparison = Comparison()
    for repeat in range(repeats):
        for query_index, spec in enumerate(specs):
            for position, deadline_ms in enumerate(running_order(repeat, query_index)):
                comparison.arms.append(
                    run_arm(
                        service,
                        spec=spec,
                        deadline_ms=deadline_ms,
                        repeat=repeat,
                        position=position,
                        execute_recommendation=execute_recommendation,
                    )
                )
    return comparison


@dataclass(frozen=True)
class Verdict:
    """The registered adoption rule, applied. Every condition reported on its own."""

    stable: bool
    equivalent_evidence: bool
    candidate_never_hit_the_clock: bool
    no_asymmetric_decline: bool
    baseline_shows_a_difference: bool
    informative_queries: int
    #: Whether `ACCEPTANCE_LABEL` was one of them. Adoption requires it, not merely a count
    #: (R-V30-008): the deadline is being chosen for the call that failed live acceptance, and
    #: a rule satisfied by two other queries would choose it on evidence about something else.
    acceptance_query_informative: bool
    differences: tuple[str, ...]
    uninformative: tuple[str, ...]
    baseline_evidence: tuple[str, ...]

    @property
    def adoptable(self) -> bool:
        return (
            self.stable
            and self.equivalent_evidence
            and self.candidate_never_hit_the_clock
            and self.no_asymmetric_decline
            and self.baseline_shows_a_difference
            and self.informative_queries > 0
            and self.acceptance_query_informative
        )

    def as_record(self) -> dict[str, Any]:
        return {
            "adoptable": self.adoptable,
            "stable": self.stable,
            "equivalent_evidence": self.equivalent_evidence,
            "candidate_never_hit_the_clock": self.candidate_never_hit_the_clock,
            "no_asymmetric_decline": self.no_asymmetric_decline,
            "baseline_shows_a_difference": self.baseline_shows_a_difference,
            "informative_queries": self.informative_queries,
            "acceptance_query_informative": self.acceptance_query_informative,
            "acceptance_query": ACCEPTANCE_LABEL,
            "differences": list(self.differences),
            "uninformative": list(self.uninformative),
            "baseline_evidence": list(self.baseline_evidence),
        }


#: The published depths in disclosure order, so "shallower" is one comparison. Written out
#: rather than imported from the server's private `_DEPTH_ORDER` so that a depth added there
#: without a thought for this rule shows up here as an unknown rather than silently ranking.
_DEPTH_ORDER: Final[tuple[str, ...]] = (
    Depth.STUB.value,
    Depth.SNIPPET.value,
    Depth.BODY_CLEAN.value,
    Depth.BODY_FULL.value,
    Depth.RAW.value,
)


def _depth_rank(depth: str) -> int:
    """Where a depth sits on the ladder. An unrecognised one ranks below every known depth,
    so a depth this harness has never heard of is treated as *less* evidence and reported,
    never quietly accepted as equivalent."""
    try:
        return _DEPTH_ORDER.index(depth)
    except ValueError:
        return -1


#: Everything one repetition of a (query, arm) pair must agree with itself about. Matched rows
#: alone were not enough: a run whose repeats agreed about the evidence but disagreed about
#: `partial`, what was withheld, how many sources were left out, or which caps were hit is a
#: run whose result state is unstable, and an unstable result state cannot choose a default.
_FINGERPRINT_FIELDS: Final[tuple[str, ...]] = (
    "declined",
    "matched evidence",
    "partial",
    "withheld",
    "not_included",
    "budget_caps_hit",
)


def _fingerprint(arm: ArmResult) -> tuple[Any, ...]:
    """The stability fingerprint, in `_FINGERPRINT_FIELDS` order. `withheld` and
    `budget_caps_hit` are sorted because neither is emitted in a promised order and a
    reordering is not an instability."""
    return (
        arm.declined,
        arm.evidence,
        arm.partial,
        tuple(sorted(arm.withheld)),
        arm.not_included,
        tuple(sorted(arm.budget_caps_hit)),
    )


def _completeness(arm: ArmResult) -> tuple[Any, ...]:
    """How complete an arm says its own result is. Identical matched rows are not equivalence
    if one arm reports the result as partial, withholds more, or drops more sources: the
    caller is being told a different thing about what it did not get."""
    return (arm.partial, tuple(sorted(arm.withheld)), arm.not_included)


def _instability(observations: Sequence[ArmResult]) -> str | None:
    """Which fields the repeats of one (query, arm) disagreed about, or `None` if none did."""
    if not observations:
        return "no observations"
    first = _fingerprint(observations[0])
    disagreed = sorted(
        {
            _FINGERPRINT_FIELDS[index]
            for arm in observations[1:]
            for index, (mine, theirs) in enumerate(zip(_fingerprint(arm), first, strict=True))
            if mine != theirs
        }
    )
    if not disagreed:
        return None
    return "repeats disagree about " + ", ".join(disagreed)


def _stable(observations: Sequence[ArmResult]) -> bool:
    """Every repeat of one (query, arm) agreed with itself about all of `_FINGERPRINT_FIELDS`."""
    return _instability(observations) is None


def _materially_less(baseline: ArmResult, bound: ArmResult) -> str | None:
    """Is the baseline's evidence materially less than the bound's, **counting depth**?

    A strict subset of `(id, depth)` pairs cannot see this. `("m1", "stub")` and
    `("m1", "body_clean")` are not in a subset relation in either direction, so a message that
    arrived as a stub under 2,000 ms and whole under the bound would have made the two sets
    merely *different* and the rule would have found no difference to report. Keyed on the
    message id instead: for every id the bound returned, the baseline is materially less if it
    does not have that id at all, or has it at a shallower depth.
    """
    theirs = dict(bound.evidence)
    ours = dict(baseline.evidence)
    missing = sorted(message_id for message_id in theirs if message_id not in ours)
    shallower = sorted(
        (message_id, ours[message_id], theirs[message_id])
        for message_id in theirs
        if message_id in ours and _depth_rank(ours[message_id]) < _depth_rank(theirs[message_id])
    )
    if not missing and not shallower:
        return None
    parts = []
    if missing:
        parts.append(f"did not return {missing}")
    if shallower:
        named = ", ".join(
            f"{mid} as {had} where the bound had {want}" for mid, had, want in shallower
        )
        parts.append(f"returned {named}")
    return "; ".join(parts)


def _note(into: list[str], line: str) -> None:
    """Append unless it is already there: three repeats of one query saying the same thing is
    one finding, not three."""
    if line not in into:
        into.append(line)


def judge(comparison: Comparison) -> Verdict:
    """**Registered before the run.** The candidate is adoptable only when all of:

      * **stable** - every repeat of every (query, arm) agreed with itself about declining, the
        matched evidence, `partial`, what was withheld, how many sources were not included, and
        which budget caps were hit. One network fluctuation must not be able to choose a
        default, so a pair that disagreed with itself stops the run rather than being averaged;
      * **equivalent evidence** - on **every repeat** of every query, the candidate's matched
        evidence is the same ids at the same depths as the bound's, *and* the two report the
        same `partial`, `withheld` and `not_included` state. Identical matched rows are not
        equivalence when one arm tells the caller its result is less complete;
      * **the candidate never hit the clock** - `max_server_ms` appears in no repetition's
        `budget_caps_hit`, not merely in the first one's;
      * **no asymmetric decline between candidate and bound** - one refusing where the other
        answered is a difference whatever else matched, in any repetition;
      * **the baseline showed a practical difference** - on at least one informative query, and
        in every repetition of it, the shipped 2,000 ms declined, hit the clock, came back
        partial where the bound did not, or returned materially less evidence than the bound -
        *materially* counting depth, so the same message arriving as a stub under the baseline
        and as `body_clean` under the bound is less evidence. Without this the run has not
        shown the deadline matters, and a comparison that cannot fail decides nothing;
      * **at least one informative query** - one where, in every repetition, candidate and bound
        both returned identical, **non-empty** matched evidence at identical depths and the same
        completeness. An empty result is equally empty under any deadline;
      * **and the acceptance query is one of them** (round 30, R-V30-008). The condition above
        is counted per label, so two well-behaved queries could satisfy it while
        `ACCEPTANCE_LABEL` - the call that failed live v0.1 acceptance, and the only reason
        this run exists - returned zero rows under every arm. A deadline chosen on evidence
        about other queries is a deadline chosen on the wrong evidence.

    Every condition is judged across **all** repetitions, not the first one. Stability makes
    those agree in a healthy run; a rule that reads `[0]` would depend on that having held.

    **A query both arms declined is uninformative, not a difference**, and no cause is
    attributed to it here: what the refusals said is recorded and a reader attributes it.
    """
    differences: list[str] = []
    uninformative: list[str] = []
    baseline_evidence: list[str] = []
    stable = True
    equivalent = True
    never_hit = True
    symmetric = True
    baseline_differs = False
    informative = 0
    acceptance_informative = False

    for label in comparison.labels:
        runs = {ms: comparison.observations(label, ms) for ms in ARMS}
        for ms, observations in runs.items():
            wobble = _instability(observations)
            if wobble is not None:
                stable = False
                _note(
                    differences,
                    f"{label!r} at {ms} ms: {wobble} - "
                    f"declined={[a.declined for a in observations]}, "
                    f"evidence sizes={[len(a.evidence) for a in observations]}",
                )

        # Requirement 1, third clause: *any* candidate repetition that hit the wall blocks.
        for arm in runs[CANDIDATE_MS]:
            if arm.hit_the_clock:
                never_hit = False
                _note(
                    differences,
                    f"{label!r}: the candidate hit max_server_ms on repeat {arm.repeat}",
                )

        by_repeat = {ms: {arm.repeat: arm for arm in runs[ms]} for ms in ARMS}
        shared = sorted(
            set(by_repeat[BASELINE_MS])
            & set(by_repeat[CANDIDATE_MS])
            & set(by_repeat[UPPER_BOUND_MS])
        )
        if not shared:
            continue

        comparable = True
        baseline_showed_it = True
        found_here: list[str] = []
        for repeat in shared:
            baseline = by_repeat[BASELINE_MS][repeat]
            candidate = by_repeat[CANDIDATE_MS][repeat]
            bound = by_repeat[UPPER_BOUND_MS][repeat]

            if candidate.declined and bound.declined:
                said = candidate.decline
                named = list(said.caps_named_in_remediation) if said else []
                _note(
                    uninformative,
                    f"{label!r}: candidate and bound both declined "
                    f"(code={said.code if said else None}; remediation names {named}). "
                    "Says nothing about the deadline; cause not attributed here",
                )
                comparable = False
                continue
            if candidate.declined != bound.declined:
                symmetric = False
                refused, answered = (
                    ("candidate", "bound") if candidate.declined else ("bound", "candidate")
                )
                _note(
                    differences,
                    f"{label!r}: the {refused} declined where the {answered} answered "
                    f"(repeat {repeat})",
                )
                comparable = False
                continue

            if candidate.evidence != bound.evidence:
                equivalent = False
                comparable = False
                _note(
                    differences,
                    f"{label!r}: evidence differs - candidate {list(candidate.evidence)} "
                    f"vs bound {list(bound.evidence)}",
                )
                continue
            if _completeness(candidate) != _completeness(bound):
                equivalent = False
                comparable = False
                _note(
                    differences,
                    f"{label!r}: the same matched rows reported as a different result - "
                    f"candidate partial={candidate.partial}, withheld={len(candidate.withheld)}, "
                    f"not_included={candidate.not_included}; bound partial={bound.partial}, "
                    f"withheld={len(bound.withheld)}, not_included={bound.not_included}",
                )
                continue
            if not candidate.evidence:
                comparable = False
                _note(
                    uninformative,
                    f"{label!r}: both answered with no matched evidence; equally empty under "
                    "any deadline",
                )
                continue

            if baseline.declined:
                _note(found_here, f"{label!r}: baseline declined where the bound answered")
            elif baseline.hit_the_clock:
                _note(found_here, f"{label!r}: baseline hit max_server_ms")
            elif (less := _materially_less(baseline, bound)) is not None:
                _note(
                    found_here,
                    f"{label!r}: baseline returned materially less evidence than the bound "
                    f"({less})",
                )
            elif baseline.partial and not bound.partial:
                _note(found_here, f"{label!r}: baseline came back partial, the bound did not")
            else:
                baseline_showed_it = False

        if comparable:
            informative += 1
            if label == ACCEPTANCE_LABEL:
                acceptance_informative = True
            if baseline_showed_it:
                baseline_differs = True
                for line in found_here:
                    _note(baseline_evidence, line)

    return Verdict(
        stable=stable,
        equivalent_evidence=equivalent,
        candidate_never_hit_the_clock=never_hit,
        no_asymmetric_decline=symmetric,
        baseline_shows_a_difference=baseline_differs,
        informative_queries=informative,
        acceptance_query_informative=acceptance_informative,
        differences=tuple(differences),
        uninformative=tuple(uninformative),
        baseline_evidence=tuple(baseline_evidence),
    )


def write_record(comparison: Comparison, verdict: Verdict, out_dir: Path, *, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    path.write_text(
        json.dumps(
            {
                "schema": 2,
                "arms_ms": {
                    "baseline_shipped": BASELINE_MS,
                    "candidate": CANDIDATE_MS,
                    "upper_bound": UPPER_BOUND_MS,
                },
                "max_http_requests": MAX_HTTP_REQUESTS,
                "repeats_counterbalanced": True,
                "adoption_rule": judge.__doc__,
                "verdict": verdict.as_record(),
                "arms": [arm.as_record() for arm in comparison.arms],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _median(values: Sequence[int]) -> int:
    return int(statistics.median(values)) if values else -1


def render(comparison: Comparison, verdict: Verdict) -> str:
    """One row per (query, arm), aggregated over repeats."""
    lines = [
        f"baseline {BASELINE_MS} ms (shipped) | candidate {CANDIDATE_MS} ms | "
        f"upper bound {UPPER_BOUND_MS} ms",
        "",
        f"{'query':<34}{'ms':>7}{'n':>3}{'evid':>6}{'depths':>22}{'caps':>16}"
        f"{'part':>6}{'wh':>4}{'http':>6}{'search':>8}{'expand':>8}{'chars':>7}{'rec':>5}",
    ]
    for label in comparison.labels:
        for deadline_ms in ARMS:
            observations = comparison.observations(label, deadline_ms)
            if not observations:
                continue
            first = observations[0]
            walls = [arm.search_wall_ms for arm in observations]
            if first.declined:
                code = first.decline.code if first.decline else "?"
                lines.append(
                    f"{label[:33]:<34}{deadline_ms:>7}{len(observations):>3}  DECLINED {code}"
                    f"   (median search {_median(walls)} ms)"
                )
                continue
            depths = ",".join(sorted({depth for _mid, depth in first.evidence})) or "-"
            expansions = [
                arm.expansion_wall_ms for arm in observations if arm.expansion_wall_ms is not None
            ]
            rec = (
                "-"
                if first.recommendation is None
                else ("ok" if first.recommendation_executed else "FAIL")
            )
            lines.append(
                f"{label[:33]:<34}{deadline_ms:>7}{len(observations):>3}{len(first.evidence):>6}"
                f"{depths[:21]:>22}{','.join(first.budget_caps_hit)[:15] or '-':>16}"
                f"{'yes' if first.partial else 'no':>6}{len(first.withheld):>4}"
                f"{first.http_requests:>6}{_median(walls):>8}"
                f"{(_median(expansions) if expansions else 0):>8}"
                f"{first.rendered_chars:>7}{rec:>5}"
            )
    lines += [
        "",
        f"adoptable: {verdict.adoptable}   "
        f"(stable={verdict.stable}, informative={verdict.informative_queries}, "
        f"baseline_shows_a_difference={verdict.baseline_shows_a_difference})",
    ]
    for note in verdict.baseline_evidence:
        lines.append(f"  baseline:      {note}")
    for difference in verdict.differences:
        lines.append(f"  difference:    {difference}")
    for note in verdict.uninformative:
        lines.append(f"  uninformative: {note}")
    return "\n".join(lines)
