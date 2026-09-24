"""L5, the semantic rung: build a bounded pool, embed it, shortlist it (AD D.5, SEM-04).

**What this rung is allowed to be.** It fires only where the lexical ladder has run out of
ways to ask the question - D.3 rule 4 - and never where the query already resolved an
identity. The prohibitions are in code here rather than in a comment, because SEM-04 and
RANK-01 are the two rules whose violation would be invisible: a semantic rung that ran after
an `rfc822msgid:` lookup would return *plausible* messages beside the exact one, and nothing
in the response would look wrong.

**Three things it produces and one it does not.**

  * a `PoolBuild`: the rows it read, with the exact text it embedded for each;
  * a `ShortlistResult`: the top `k` by stage-A cosine, `k = max_rerank_pairs`;
  * an account of itself - ran, declined, or blocked - that `assemble` turns into
    `retrieval_report.pool`, `.shortlist` and `not_tried[]`.

It does **not** produce disclosure. The shortlist's threads become candidates for mapping
like any other hit-bearing thread; the rest of the pool is disposed of as withheld under
`max_pool_threads` / `max_pool_messages`. Pool membership is not disclosure membership, and
this module cannot make it so because it returns no rows.

**The cold load is not charged to the query's semantic budget, and that is a decision with
a measurement behind it.** PF-4 records `cold_acquire_ms = 5410` against a 6,000 ms
`MAX_SEMANTIC_MS`; a first query that had to pay it would have 590 ms left for a pool it
measured at 250 ms, and a machine 20% slower than the owner's would have none. The load is
per *process* (`BackendRegistry.acquire` memoises for the process lifetime, and
`test_the_server_process_reuses_one_backend_across_queries` executes that through the real
service), so it is a startup cost and it is reported as one: `SemanticRun.cold_load_ms`
carries it when this query was the one that paid it, `semantic_ms` never includes it, and
`mailweave serve` warms the backend before the first query so that ordinarily nobody pays it
inside a query at all. What is *not* done is pretending the first query is warm.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from mailweave.content.payload import MessagePayload
from mailweave.content.pipeline import process_message
from mailweave.diagnostics import lifecycle
from mailweave.envelope.disposition import DispositionLedger
from mailweave.envelope.reasons import RungId
from mailweave.envelope.vocab import BudgetCapName, NotTriedWhy, ToolName, WithheldCap
from mailweave.envelope.wire import Affordance, PoolBlock, Shortlist
from mailweave.errors import ContentProcessingError, MailweaveError
from mailweave.gmail.client import THREAD_MAP_HEADERS, GmailClient, RecordedThread
from mailweave.gmail.models import Message
from mailweave.gmail.rates import GmailEndpoint
from mailweave.policy.account import force_rungs
from mailweave.policy.budget import BudgetAccountant, CapBreach
from mailweave.policy.stopping import StopInputs, StopRule, rule_4_escalates
from mailweave.retrieval.ladder import LadderRun, widen_scan
from mailweave.semantic.interface import (
    REGISTRY,
    BackendRegistry,
    SemanticBackend,
    SemanticError,
    checked_embed,
)
from mailweave.semantic.pool import PoolBuild, PoolPlan, PoolRow, PoolStep, plan_pool, pool_row_text
from mailweave.semantic.profile import PoolTextMode, SemanticProfile
from mailweave.semantic.shortlist import ShortlistResult, shortlist


def _body_head_of(message: Message) -> Callable[[str], str | None]:
    """A reader of *this* message's own body head, for the branches that embed one.

    A closure over one message rather than a lookup, because `pool_row_text` is given one
    message at a time and the alternative - a map built ahead of the loop - would be a second
    place the pool's text could come from. `process_message` is D.4a's pipeline, the same one
    the response's own `body_clean` goes through, so what stage A embeds on this branch is
    the cleaned text the reader would see and not the raw bytes.
    """

    def read(message_id: str) -> str | None:
        if message_id != message.id or message.payload is None:
            return None
        try:
            processed = process_message(
                MessagePayload.model_validate(
                    {
                        "id": message.id,
                        "threadId": message.thread_id,
                        "internalDate": message.internal_date,
                        "snippet": message.snippet or "",
                        "payload": message.payload,
                    }
                )
            )
        except (ContentProcessingError, ValueError):
            # A message whose body will not parse contributes subject and participants, which
            # is weaker text and an honest amount of it. The alternative is dropping the row
            # from the pool, which would make the pool's size depend on parse failures.
            return None
        return processed.default_view

    return read


class SemanticState(StrEnum):
    """What L5 did for this query. One value, and the response reads it rather than guessing."""

    RAN = "ran"
    #: A prohibition applied: an identity resolution, an exact-signal match, or a family
    #: SEM-04 excludes. Not a budget and not a failure - the rung could not have helped.
    NOT_APPLICABLE = "not_applicable"
    #: The lexical ladder found evidence, so rule 4 did not escalate. `force_rungs` reaches it.
    STOPPED_ON_EVIDENCE = "stopped_on_evidence"
    #: A cap stopped it: quota, API calls, the clock, or the semantic clock.
    BLOCKED = "blocked"
    #: The model runtime or the weights are unavailable (D.11 `semantic_unavailable`).
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class SemanticGate:
    """Whether L5 may run for this query, and the sentence that says why not."""

    fires: bool
    state: SemanticState
    why: str

    @property
    def prohibited(self) -> bool:
        return self.state is SemanticState.NOT_APPLICABLE


#: SEM-04's excluded families, as predicates over the parse rather than as a list of query
#: shapes. A query whose every constraint is a participant or a date operator is the
#: "sender/date family": Gmail answers it exactly, and a cosine over its results would be
#: ranking an already-exact answer by resemblance to the words the user used to ask for it.
_STRUCTURAL_ONLY: Final[frozenset[str]] = frozenset(
    {"from", "to", "cc", "bcc", "after", "before", "older_than", "newer_than", "in", "label"}
)


def semantic_gate(run: LadderRun) -> SemanticGate:
    """D.5's firing condition and SEM-04's prohibitions, evaluated in prohibition-first order.

    Order matters and is not alphabetical. A prohibition is a statement that the rung *could
    not have helped*, which is the only `not_tried` reason compatible with `outcome:
    not_found`; a declined escalation is a statement that it was not *needed*, which carries
    a `force_rungs` affordance. Evaluating the escalation first would let a query that
    resolved an identity - and therefore must never reach a semantic rung - be recorded as
    merely not needed, and a caller could then force it.
    """
    if run.stop_rule == StopRule.RULE_1.value:
        return SemanticGate(
            fires=False,
            state=SemanticState.NOT_APPLICABLE,
            why=(
                "D.3 rule 1 resolved an identity; no structural, semantic or ranking rung "
                "may run after an identity resolution (SEM-04, RANK-01)"
            ),
        )
    if run.exact_signal.fired:
        return SemanticGate(
            fires=False,
            state=SemanticState.NOT_APPLICABLE,
            why=(
                f"exact_signal_match fired on branch {run.exact_signal.branch}; D.5 fires "
                "only where it is false"
            ),
        )
    if run.parsed.identifiers:
        return SemanticGate(
            fires=False,
            state=SemanticState.NOT_APPLICABLE,
            why="the query carries a structured identifier: an exact-lookup family (SEM-04)",
        )
    names = set(run.parsed.constraint_names)
    if names and names <= _STRUCTURAL_ONLY:
        return SemanticGate(
            fires=False,
            state=SemanticState.NOT_APPLICABLE,
            why=(
                "every constraint is a participant or date operator; Gmail answers this "
                "family exactly and D.5 never fires on it (SEM-04)"
            ),
        )
    if not run.parsed.search_terms and not run.parsed.phrases:
        return SemanticGate(
            fires=False,
            state=SemanticState.NOT_APPLICABLE,
            why="the query carries no free text to embed, so there is nothing to score against",
        )
    if not rule_4_escalates(_stop_inputs(run)):
        return SemanticGate(
            fires=False,
            state=SemanticState.STOPPED_ON_EVIDENCE,
            why="the lexical ladder found evidence, so D.3 rule 4 did not escalate",
        )
    return SemanticGate(fires=True, state=SemanticState.RAN, why="D.3 rule 4 escalated")


def _stop_inputs(run: LadderRun) -> StopInputs:
    """Rule 4's inputs, read off the run the lexical ladder already recorded.

    The two uncomputed disjuncts (`paraphrase_risk >= theta`, tier-1 non-lexical confidence)
    stay `None` here exactly as they do inside the ladder, so this gate cannot fire on a
    disjunct the ladder treats as not firing.
    """
    return StopInputs(
        exact=run.exact_signal,
        answer_type=run.answer_type,
        hit_count=run.hit_count,
        term_coverage=run.parsed.term_coverage(run.parsed.constraints),
        constraint_drop_depth=1 if run.parsed.passthrough else 0,
        evidence_count=run.evidence_count,
    )


@dataclass
class SemanticRun:
    """L5's whole account of itself for one query."""

    state: SemanticState
    why: str
    plan: PoolPlan | None = None
    build: PoolBuild | None = None
    result: ShortlistResult | None = None
    model_id: str | None = None
    model_revision: str | None = None
    profile: SemanticProfile | None = None
    #: Warm work only: embed(pool). Never the model load (see the module docstring).
    semantic_ms: int = 0
    #: The model load, when *this query* was the one that paid it. `None` when the process
    #: had already loaded it, which is every query after the first.
    cold_load_ms: int | None = None
    breach: CapBreach | None = None
    cap: BudgetCapName | None = None
    errors: tuple[str, ...] = ()

    @property
    def ran(self) -> bool:
        return self.state is SemanticState.RAN and self.result is not None

    @property
    def shortlist_ids(self) -> frozenset[str]:
        return frozenset() if self.result is None else self.result.selected_ids

    @property
    def pool_thread_ids(self) -> frozenset[str]:
        return frozenset() if self.build is None else frozenset(self.build.threads_read)

    @property
    def observations(self) -> Mapping[str, RecordedThread]:
        """What the pool already fetched, so `assemble` maps a pool thread without re-reading."""
        return {} if self.build is None else self.build.observations

    @property
    def not_tried_why(self) -> NotTriedWhy | None:
        """The `not_tried[].why` this state maps to, or `None` when the rung ran."""
        return {
            SemanticState.RAN: None,
            SemanticState.NOT_APPLICABLE: NotTriedWhy.NOT_APPLICABLE,
            SemanticState.STOPPED_ON_EVIDENCE: NotTriedWhy.STOPPED_ON_EVIDENCE,
            SemanticState.BLOCKED: NotTriedWhy.BUDGET,
            SemanticState.UNAVAILABLE: NotTriedWhy.ERROR,
        }[self.state]

    def affordance(self, *, query: str) -> Affordance | None:
        """The call that reaches this rung, for the states that have one.

        `not_applicable` has none and must have none - no budget reaches a rung that does
        not apply - and `NotTriedEntry` refuses a blocking reason without one, which is what
        keeps this table honest.
        """
        if self.state is SemanticState.NOT_APPLICABLE:
            return None
        if self.state is SemanticState.BLOCKED and self.breach is not None:
            return self.breach.affordance
        return force_rungs(RungId.L5, query=query)

    def pool_block(self) -> PoolBlock | None:
        """`retrieval_report.pool`, or `None` when no pool was built."""
        if self.build is None or self.plan is None:
            return None
        return PoolBlock(
            scope_rule=self.plan.scope_rule,
            thread_count=self.build.thread_count,
            message_count=self.build.message_count,
            why=self.why,
        )

    def shortlist_block(self) -> Shortlist | None:
        if self.result is None:
            return None
        return Shortlist(rule=self.result.rule, k=self.result.k, size=self.result.size)


def pool_widening(query: str, *, max_threads: int) -> Affordance:
    """The call that widens the pool: A.7a's remedy for `max_pool_threads`."""
    return Affordance(
        tool=ToolName.SEARCH, args={"query": query, "pool": {"max_threads": max_threads}}
    )


class SemanticRunner:
    """Executes L5 against one Gmail client, one ledger and one registry.

    The registry is a constructor argument so a test can hand in a fake backend without
    touching the process-wide one, and so PF-4's cold arm can reset it. Production passes
    the module-level `REGISTRY`, which is what makes the load per-process.
    """

    def __init__(
        self,
        client: GmailClient,
        ledger: DispositionLedger,
        *,
        profile: SemanticProfile,
        registry: BackendRegistry = REGISTRY,
        accountant: BudgetAccountant | None = None,
        clock_ms: Callable[[], float] | None = None,
        body_head: Callable[[str], str | None] | None = None,
    ) -> None:
        self._client = client
        self._ledger = ledger
        self._profile = profile
        self._registry = registry
        self._accountant = accountant
        self._body_head = body_head
        if clock_ms is None:
            from time import monotonic

            def clock_ms() -> float:
                return monotonic() * 1000.0

        self._clock_ms = clock_ms

    # -- the run -------------------------------------------------------------------------

    def run(self, run: LadderRun, *, now: datetime, forced: bool = False) -> SemanticRun:
        """Gate, build, embed, shortlist. Every early return is an account, never a silence."""
        gate = semantic_gate(run)
        if gate.prohibited:
            # A prohibition is never overridable. `force_rungs` "can only add rungs"; it
            # cannot add one SEM-04 forbids, and a caller who asks is told why rather than
            # obeyed.
            return SemanticRun(state=gate.state, why=gate.why, profile=self._profile)
        if not gate.fires and not forced:
            return SemanticRun(state=gate.state, why=gate.why, profile=self._profile)
        why = gate.why if gate.fires else "the caller forced the semantic rung (force_rungs)"
        # **The model load happens outside the semantic clock, and that is PF-4's own rule.**
        # "The per-query budget is WARM work only - embed(pool) + rerank(k). The cold load is
        # paid once per process and is reported separately, never folded into a per-query
        # figure." Acquiring inside `enter_semantic` charged a 5,410 ms load to a 6,000 ms
        # budget and produced `max_semantic_ms` breaches on queries that had not embedded a
        # single row - the cap firing on the one cost it was written to exclude. The load's
        # wall clock is real, so it stays on `max_server_ms` where the query's own deadline
        # lives; it is the *attribution* that was wrong, not the accounting.
        try:
            backend, cold_ms = self._acquire()
        except SemanticError as failure:
            # D.5's deterministic fallback (D6): the rung declines in band and the ladder
            # continues. A silent no-op is a BLOCKER by construction (SEM-02's guard).
            return SemanticRun(
                state=SemanticState.UNAVAILABLE,
                why=f"the local semantic backend is unavailable: {failure}",
                profile=self._profile,
                errors=(type(failure).__name__,),
            )
        # The call-diagnostics end line carries the cold load when this query paid it, so
        # the timing check can set it aside: it is outside every per-query budget by PF-4's
        # rule, and a first query that looks 5 s late is a first query that loaded a model.
        if cold_ms is not None:
            lifecycle().observe(cold_load_ms=cold_ms)

        # **The semantic clock, entered here and left on every path out.** A.7 makes
        # `max_semantic_ms` and `max_server_ms` separate caps; `enter_semantic` switches the
        # accountant to the first and `leave_semantic` puts the second back where it would
        # have been had this rung taken no time, so disclosure assembly after L5 is timed
        # against the budget written for RTT-bound work rather than the one written for
        # embeddings. It accumulates, so L6's own entry later in the query spends the same
        # six seconds rather than a second set.
        if self._accountant is not None:
            self._accountant.enter_semantic()
        try:
            return self._inside_the_semantic_clock(
                run, now=now, why=why, backend=backend, cold_ms=cold_ms
            )
        finally:
            if self._accountant is not None:
                self._accountant.leave_semantic()

    def _inside_the_semantic_clock(
        self,
        run: LadderRun,
        *,
        now: datetime,
        why: str,
        backend: SemanticBackend,
        cold_ms: int | None,
    ) -> SemanticRun:
        plan = plan_pool(
            run.parsed,
            touched_threads=self._touched_threads(run),
            profile=self._profile,
            now=now,
        )
        build, breach = self._build_pool(plan)
        if not build.rows:
            return SemanticRun(
                state=SemanticState.BLOCKED if breach is not None else SemanticState.RAN,
                why=why if breach is None else f"{why}; {breach.rendered()}",
                plan=plan,
                build=build,
                profile=self._profile,
                model_id=backend.model_id,
                model_revision=backend.model_revision,
                cold_load_ms=cold_ms,
                breach=breach,
                cap=None if breach is None else breach.cap,
            )

        started = self._clock_ms()
        try:
            vectors = checked_embed(backend, [self._query_text(run), *build.texts])
        except SemanticError as failure:
            return SemanticRun(
                state=SemanticState.UNAVAILABLE,
                why=f"the semantic backend failed while embedding the pool: {failure}",
                plan=plan,
                build=build,
                profile=self._profile,
                model_id=backend.model_id,
                model_revision=backend.model_revision,
                cold_load_ms=cold_ms,
                errors=(type(failure).__name__,),
            )
        elapsed = int(self._clock_ms() - started)
        result = shortlist(
            vectors[0],
            [
                (row.message_id, row.thread_id, vector, row.basis)
                for row, vector in zip(build.rows, vectors[1:], strict=True)
            ],
            k=self._profile.max_rerank_pairs,
        )
        # **The semantic clock is a cap like any other, and the embed is checked after the
        # work rather than before it.** There is nothing to check before: the pool's embed
        # cost is what is being bounded, and a prediction of it would be exactly the
        # assumption PF-4 exists to replace. An overrun does not discard the shortlist - the
        # work is done and the evidence is real - it names the cap so the response says what
        # cost it. The bound read is the accountant's when there is one, because a caller may
        # have lowered it; the profile's measured figure is the default underneath.
        limit = (
            self._accountant.budget.max_semantic_ms
            if self._accountant is not None
            else self._profile.max_semantic_ms
        )
        cap = BudgetCapName.MAX_SEMANTIC_MS if elapsed > limit else None
        return SemanticRun(
            state=SemanticState.RAN,
            why=why if breach is None else f"{why}; {breach.rendered()}",
            plan=plan,
            build=build,
            result=result,
            profile=self._profile,
            model_id=backend.model_id,
            model_revision=backend.model_revision,
            semantic_ms=elapsed,
            cold_load_ms=cold_ms,
            breach=breach,
            cap=cap or (None if breach is None else breach.cap),
        )

    # -- the pieces ----------------------------------------------------------------------

    def _acquire(self) -> tuple[SemanticBackend, int | None]:
        """The backend, and how long *this call* waited for it to load.

        `None` means the process had already built it, which is the ordinary case and the
        one the per-query budget is written for. A number means this query paid the startup
        cost, and the response reports it separately rather than folding it into
        `semantic_ms` - PF-4's own rule, applied where the number reaches a caller.
        """
        if self._registry.is_built():
            return self._registry.acquire(), None
        started = self._clock_ms()
        backend = self._registry.acquire()
        return backend, int(self._clock_ms() - started)

    def _query_text(self, run: LadderRun) -> str:
        """What stage A embeds for the query side: the user's own words, nothing added.

        The raw query rather than the constructed Gmail `q`: `q` carries operator syntax
        (`from:`, `after:`) that is a retrieval instruction and not a statement about
        meaning, and embedding it would score every pool row against the punctuation of the
        search rather than against the question.
        """
        return run.parsed.raw

    def _touched_threads(self, run: LadderRun) -> tuple[str, ...]:
        """Step (a): threads the lexical rungs already put a hit in, in ladder order."""
        order: list[str] = []
        for execution in run.executions:
            for entry in execution.executed:
                for thread_id in sorted(entry.threads):
                    if thread_id not in order:
                        order.append(thread_id)
        return tuple(order)

    def _spend(self, endpoint: GmailEndpoint) -> CapBreach | None:
        if self._accountant is None:
            return None
        return self._accountant.check((endpoint,))

    def _build_pool(self, plan: PoolPlan) -> tuple[PoolBuild, CapBreach | None]:
        """Send the step-(b)/(c) probes, then read threads in priority order under the caps.

        Every id every probe returns is in `H` before this function sees it: `list_messages`
        records the page into the ledger and hands back counts, and `get_thread` records
        every row of the thread. A thread this build does not read still has a disposition
        owed, and `assemble` files it under `max_pool_threads`.
        """
        candidates: list[str] = list(plan.seed_threads)
        step_of: dict[str, PoolStep] = dict.fromkeys(plan.seed_threads, PoolStep.LADDER)
        by_step: dict[str, int] = {PoolStep.LADDER.value: len(candidates)}
        probes_sent = 0
        breach: CapBreach | None = None
        for probe in plan.probes:
            breach = self._spend(GmailEndpoint.MESSAGES_LIST)
            if breach is not None:
                break
            before = self._ledger.hit_ids
            probes_sent += 1
            self._client.list_messages(
                self._ledger,
                rung=RungId.L5,
                query=probe.query,
                widening_affordance=widen_scan(probe.query),
            )
            origins = self._ledger.origins
            found = 0
            for message_id in sorted(self._ledger.hit_ids - before):
                thread_id = origins[message_id].thread_id
                if thread_id is not None and thread_id not in step_of:
                    candidates.append(thread_id)
                    # **The step recorded is the probe that first reached this thread**, not
                    # the probe class in the abstract: a thread both a participant probe and
                    # the recency probe return is a participant thread, because that is the
                    # priority order the pool was built in and the order the cap cuts from.
                    step_of[thread_id] = probe.step
                    found += 1
            by_step[probe.step.value] = by_step.get(probe.step.value, 0) + found

        rows: list[PoolRow] = []
        read: list[str] = []
        observations: dict[str, RecordedThread] = {}
        capped: dict[str, str] = {}
        unfetchable: list[str] = []
        for thread_id in candidates:
            if len(read) >= plan.max_threads:
                capped[thread_id] = WithheldCap.MAX_POOL_THREADS.value
                continue
            if len(rows) >= plan.max_messages:
                capped[thread_id] = WithheldCap.MAX_POOL_MESSAGES.value
                continue
            if breach is None:
                breach = self._spend(GmailEndpoint.THREADS_GET)
            if breach is not None:
                capped[thread_id] = breach.withheld_cap.value
                continue
            try:
                recorded = self._client.get_thread(
                    self._ledger,
                    thread_id=thread_id,
                    rung=RungId.L5,
                    # **The format follows the branch the profile declares** (AD D.5). It was
                    # hard-coded to `metadata`, and on a clean machine - where PF-2 has not
                    # run and `unmeasured_profile()` selects D.5's primary fallback - the
                    # pool then declared `subject+participants+body-head-400` in every
                    # semantic response while embedding subject and participants alone. That
                    # is the state D.5 calls "a design change, not a cost change", running
                    # silently behind a scope rule that says otherwise, with
                    # `max_pool_threads` cut 25 to 15 to pay a parse cost that never
                    # happened. `format=full` is the same 40 u - quota is per method, not per
                    # format ([VERIFIED] CD §3) - so the branch costs bytes and latency, as
                    # D.5 says, and not quota.
                    message_format=self._thread_format(),
                    metadata_headers=THREAD_MAP_HEADERS,
                )
            except MailweaveError:
                # A thread that would not fetch is not a pool member and is not silently
                # forgotten: nothing was recorded for it by this call, so it added nothing
                # to `H`, and it is named here so the candidate count and the read count can
                # be reconciled without the difference looking like a drop. Ids the
                # *participant probe* already admitted for that thread are still in `H` and
                # still owed a disposition, which `assemble` files from `capped_by`.
                unfetchable.append(thread_id)
                capped[thread_id] = WithheldCap.PARTIAL_SOURCE_FAILURE.value
                continue
            read.append(thread_id)
            observations[thread_id] = recorded
            for message in recorded.thread.messages:
                if len(rows) >= plan.max_messages:
                    break
                rows.append(self._row(message, thread_id=thread_id, step=step_of[thread_id]))
        return (
            PoolBuild(
                plan=plan,
                rows=tuple(rows),
                threads_read=tuple(read),
                observations=observations,
                capped_by=capped,
                threads_unfetchable=tuple(unfetchable),
                probes_sent=probes_sent,
                candidates=tuple(candidates),
                by_step=by_step,
            ),
            breach,
        )

    def _thread_format(self) -> str:
        """`metadata` on the snippet branch, `full` on the two that need body text."""
        return "metadata" if self._profile.pool_text_mode is PoolTextMode.SNIPPET else "full"

    def _row(self, message: Message, *, thread_id: str, step: PoolStep) -> PoolRow:
        text = pool_row_text(
            message,
            mode=self._profile.pool_text_mode,
            body_head=self._body_head or _body_head_of(message),
        )
        return PoolRow(
            message_id=message.id,
            thread_id=thread_id,
            step=step,
            text=text,
            basis=self._profile.pool_text_mode.value,
        )


__all__ = [
    "SemanticGate",
    "SemanticRun",
    "SemanticRunner",
    "SemanticState",
    "pool_widening",
    "semantic_gate",
]
