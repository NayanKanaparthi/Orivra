"""AD A.9a's degradation ladder: eight steps, published order, one gate over all of them.

**The order is the contract.** A reader of the response must be able to reconstruct what
was sacrificed first, so the precedence is data - `LADDER_STEPS` - iterated by a driver that
records each step it applies in `reductions[]`-shaped `LadderStep` records and names
`disclosed_token_ceiling` in `budget_caps_hit`. A step is a total function
`(Layout, Ceilings) -> Layout`, and that uniform signature is what lets the driver, rather
than any individual step, hold the invariant:

```
 1. E4 query-scored fill        body_clean -> snippet -> stub
 2. Sibling-source stub rows    stub rows -> declared collapsed runs (with affordance)
 3. Hit bodies beyond the top-k body_clean(600) -> head-truncated body_clean(250) -> snippet
 4. E2 floor bodies             body_clean(600) -> head-truncated body_clean(250) -> snippet
 5. Hit-bearing-thread stubs    stub rows -> declared collapsed runs (never removed)
 6. Overflow ceiling 9,000 -> 12,000, declared, only for floor membership
 7. Split by source: lowest-ranked sources become declared not_included_sources[]
 8. A hit that still cannot be carried: a withheld record, cap disclosed_token_ceiling
```

**The gate, and why it lives in the driver.** `assert_floor_intact` is called on the output
of **every** step, by `run_ladder`, not inside any step. A check written inside a step is a
check that a new step can be added without; a check in the driver applies to step nine the
day step nine exists. That is this round's answer to "one shape validated, peers trusted":
the eight steps do not each get their own defence, they share one, and the test plants a
floor-losing mutation into each of the eight and asserts the same gate catches all eight
(`test_every_ladder_step_is_refused_when_it_drops_a_floor_member`).

**Nothing vanishes.** `assert_nothing_vanished` is the second driver-level gate: an id
present before a step is present after it, or is recorded as withheld, or belongs to a
source the step split off (and every accounted id of a split source becomes a withheld
record in the same move). That is contract I-1 stated over the ladder rather than only over
the finished envelope, so a step that loses a message fails where the loss happens.

**Termination.** The driver stops as soon as the layout fits the ceiling it has declared,
so degradation is the minimum the size demands rather than the maximum the ladder can do.
If the eighth step leaves it still oversized it raises `DisclosureLadderExhausted` rather
than returning something the envelope would refuse: an inability declared where it occurs,
never a response handed to the host to cut (DISC-06).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Final

from mailweave.constants import (
    BODY_CLEAN_HEAD_TRUNCATED_TOKENS,
    FLOOR_OVERFLOW_CEILING_TOKENS,
    MAX_BODY_FETCHES_L0,
    NORMAL_CEILING_TOKENS,
)
from mailweave.disclosure.layout import (
    Band,
    CostTerms,
    Layout,
    PlannedRow,
    PlannedRun,
    PlannedSource,
    chars_terms,
    token_terms,
    widest_thread_id,
)
from mailweave.envelope.grouping import arrange_groups
from mailweave.envelope.measure import (
    RESPONSE_STRUCTURAL_TOKENS,
    WITHHELD_RECORD_TOKENS,
    collapsed_run_tokens,
    row_tokens,
    withheld_chars,
)
from mailweave.envelope.vocab import Depth, WithheldCap
from mailweave.errors import MailweaveError

#: How many hit bodies A.9a step 3 protects. **Not a new number**: A.7's cap table publishes
#: `max_body_fetches` as 5 at L0 - the answer the architecture already gives to "how many
#: messages is it worth reading in full at the cheapest tier". Disclosure protects exactly
#: that many hit bodies, so the two cannot drift and no figure enters the system that was
#: chosen after seeing a benchmark.
#:
#: Which hits are the top *k* is decided by the **published E4 score** (`weights.py`), ties
#: by thread position. Deliberately not by recency and not by arrival order: EV-02's
#: degenerate-strategy guard names a fixed newest-K policy by name, and ordering by an
#: opaque Gmail id would be a coin flip presented as a ranking (RANK-03).
#:
#: **Round 25 made that sentence true** (R-DISC-026). Until this round the fill was the only
#: producer of a score and the fill never scores hits, so every evidence row carried
#: `fill_score = 0`, the tie-break *was* the selection, and the protected set was the oldest
#: *k* hits by thread position in both arms and for every query - the degenerate policy the
#: paragraph above disclaims, under the published score's name. `plan.hit_ranks` scores the
#: hits, among themselves, under amendment A11's discriminating-facts rule; where nothing in
#: the query separates them the value is 0 for all of them and thread position decides, which
#: is the same behaviour as before and is now the stated fallback rather than the whole rule.
DISCLOSURE_TOP_K_HITS: Final[int] = MAX_BODY_FETCHES_L0


class FloorMembershipLost(MailweaveError):
    """A degradation step removed a message the E2 reply-chain floor keeps (OD-3, A.9a).

    The biggest claim in this project, as an exception. Membership is absolute: a floor
    member is present as a row or as a declared collapsed-run member at every step of the
    ladder, at both ceilings, in every shape. A step that would break it fails here rather
    than producing a response whose reply chain has a hole in it.
    """


class RefusalKind(StrEnum):
    """Why the ladder refused: the two refusals a caller acts on differently (R-M2-095)."""

    #: Every published step ran and the response is still over a ceiling.
    SIZE = "size"
    #: The only arrangement that fits carries no mail.
    EMPTY = "empty"


@dataclass(frozen=True)
class RefusalCause:
    """What a refusal was made of, so the recovery beside it can be chosen rather than guessed.

    **2026-09-15, R-M2-095.** `DisclosureLadderExhausted` used to carry a message, the top
    thread and the width, and `recovery.narrower_call` halved `max_hit_threads` on every
    search decline whatever the ladder had refused *for*. On the semantic arm that narrowed
    a dimension the refusal did not live in - the pool's groups and the top source's
    protected floor are the same at every width - and spent the driver's depth reaching the
    same refusal three times over. An emptiness flag alone does not say whether the pool's
    bookkeeping or the last source's own content is what did not fit, so this carries both:

      * `terms` - the refused layout's own cost, by the term the wire renders it as, in the
        unit that bound. For an emptiness refusal that is the bookkeeping alone, because the
        layout carries no source by then; `residual` is what the last evidence-bearing source
        cost at its smallest - its runs - before it had to leave (`Layout.last_evidence_source`);
      * `groups_by_cap` - how many groups are named under each cap, so a reader can see a
        pool cap's fixed groups beside the width cap's foldable ones;
      * `fits_at` - **the ladder's own answer at every narrower width**: for each
        `max_hit_threads` below the width in effect, the estimate the ladder finished at when
        run over the same retrieval with only that many hit-bearing threads mapped, or absent
        where it refused (`refused_at`). One implementation asked a hypothetical, as
        `_step_8_would_fit` asks step 8; not a second model of the arithmetic that could
        disagree with it.

    A `RefusalCause` is data about one refusal. It names no thread as *worth* reading and
    ranks nothing; the recovery chooses a dimension from it, and the response's own ranking
    is what it always was.
    """

    kind: RefusalKind
    unit: str
    cap: int
    terms: CostTerms
    groups_by_cap: Mapping[str, int]
    folded_by_cap: Mapping[str, int]
    width: int
    top_thread: str | None
    residual_thread: str | None = None
    residual: int | None = None
    fits_at: Mapping[int, int] = field(default_factory=dict)
    refused_at: tuple[int, ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "unit": self.unit,
            "cap": self.cap,
            "terms": self.terms.as_json(),
            "groups_by_cap": dict(self.groups_by_cap),
            "folded_by_cap": dict(self.folded_by_cap),
            "width": self.width,
            "top_thread": self.top_thread,
            "residual_thread": self.residual_thread,
            "residual": self.residual,
            "fits_at": {str(width): cost for width, cost in sorted(self.fits_at.items())},
            "refused_at": list(self.refused_at),
        }


class DisclosureLadderExhausted(MailweaveError):
    """All eight A.9a steps ran and the response still exceeds its declared ceiling.

    Raised rather than returned, because the alternative is emitting a payload the host
    will cut - which is the one thing DISC-06 forbids. It is reachable only when the floor
    alone exceeds the overflow ceiling, which is the state OD-3 pre-authorises a branch for
    rather than a state this module may paper over.

    **Carries the highest-ranked hit-bearing thread it was refusing** (round 29), read off the
    layout the ladder *started* from, so the decline built from this can offer a thread map of
    the one thread most worth reading when a search has nowhere narrower to go. Read off the
    input rather than the stripped output because the output may hold nothing.
    """

    def __init__(
        self,
        message: str,
        *,
        top_thread: str | None = None,
        hit_threads: int | None = None,
        segmented: bool | None = None,
        cause: RefusalCause | None = None,
    ) -> None:
        super().__init__(message)
        self.top_thread = top_thread
        #: What the refusal was made of (R-M2-095), for the recovery to choose a dimension
        #: from. `None` from the producers that raise without a ladder run behind them.
        self.cause = cause
        #: How many hit-bearing threads the layout started with: the width in effect.
        self.hit_threads = hit_threads
        #: For a thread map: whether the thread has segments, so a `segment: 0` retry would
        #: be a narrowing rather than the same whole map again (R-V01-010). Set by the
        #: expansion producer, which is the only one that knows.
        self.segmented = segmented


@dataclass(frozen=True)
class Ceilings:
    """The published ceilings this response is held to: two in tokens, one in characters.

    **The third one is not a third budget** (round 26, R-DISC-033, R-MCP-021). `normal` and
    `overflow` are AD D.4's figures, set by PF-6, and they bound the whitespace-token estimate.
    `host_chars` is the size of the rendered `CallToolResult` an MCP host will accept, and it
    is a different quantity in a different unit: no ratio between the two is a bound, because a
    response of many short rows and one of few long ones sit at opposite ends of every such
    ratio. So the ladder fits both, and a response that cannot be brought inside either
    declines in band rather than being handed to a host that will cut it silently.
    """

    normal: int = NORMAL_CEILING_TOKENS
    overflow: int = FLOOR_OVERFLOW_CEILING_TOKENS
    #: The host's result cap, in characters, or `None` for a layout nobody is serving.
    #:
    #: **Why this one has a `None` and the other two do not.** The token ceilings are a
    #: property of the *policy*: A.9a is defined in terms of them and every consumer of a
    #: layout - the harness' arm comparison, DISC-04's efficiency ratio, the measurement
    #: probes - is measuring a policy that has them. The character cap is a property of the
    #: *host this response is being handed to*, and a layout being measured rather than served
    #: is not being handed to one. `surface.service` sets it on all four tools, which is every
    #: path by which a response reaches a client, and `surface.partition.declared_result`
    #: measures the rendered result against `HOST_RESULT_CHAR_CAP` whatever was planned - so
    #: the serving path cannot escape the cap by forgetting to ask for it, and a measurement
    #: is not distorted by a cap that does not apply to it.
    host_chars: int | None = None

    def __post_init__(self) -> None:
        if self.overflow < self.normal:
            raise ValueError(
                f"overflow ceiling {self.overflow} is below the normal ceiling {self.normal}; "
                "the overflow is a raise for floor membership, never a reduction"
            )
        if self.host_chars is not None and self.host_chars <= 0:
            raise ValueError("the host character cap is a size, and a size is positive")


@dataclass(frozen=True)
class LadderStep:
    """One applied step of the published precedence, as the response will declare it."""

    precedence: int
    name: str
    #: What it did, mechanically. Rendered into `reductions[]` and the response's own
    #: account of what it sacrificed first.
    detail: str
    rows_changed: int


# -- the depth ladders -------------------------------------------------------------------


def _to_snippet_or_stub(row: PlannedRow) -> PlannedRow:
    if row.snippet is not None:
        return replace(row, depth=Depth.SNIPPET, kept_tokens=None)
    return replace(row, depth=Depth.STUB, kept_tokens=None)


def _degrade_without_head_truncation(row: PlannedRow) -> PlannedRow | None:
    """A.9a step 1's ladder: `body_full -> body_clean -> snippet -> stub`. `None` when exhausted.

    `body_full` is only ever the top of this ladder, never a rung a step climbs to: A.9's
    tiers never plan one, and only `mailweave_get_messages(view="body_full")` does. It
    degrades to `body_clean` because that is the next published depth down, and a row that
    entered the response as the escape hatch is not exempt from the ceiling that binds
    everything beside it.
    """
    if row.depth is Depth.BODY_FULL:
        return replace(row, depth=Depth.BODY_CLEAN, kept_tokens=None)
    if row.depth is Depth.BODY_CLEAN:
        return _to_snippet_or_stub(row)
    if row.depth is Depth.SNIPPET:
        return replace(row, depth=Depth.STUB, kept_tokens=None)
    return None


def _degrade_through_head_truncation(row: PlannedRow) -> PlannedRow | None:
    """A.9a steps 3 and 4: `body_full -> body_clean(600) -> body_clean(250) -> snippet -> stub`.

    **Snippet is the preferred bottom and it is no longer the last rung** (round 25). A.9a's
    honesty note puts the floor's bottom at snippet - membership plus a snippet is the claim
    that is true - and that note still decides the *ordinary* case, because the driver stops
    degrading the moment the layout fits: a response that fits at snippet never sees this
    rung. What the note left undecided is what happens when snippet does **not** fit, and
    round 23's answer was, in order, raise the ceiling, withhold, and finally raise
    `DisclosureLadderExhausted` - so a 200-message thread every message of which matched came
    back as 200 pointers or as an exception out of the tool handler (R-DISC-020, R-DISC-023).

    A row at stub depth is present, is still a floor member, and is **collapsible into a
    declared run with an expansion affordance** (A.7a, contract R-06), which is why this rung
    turns that thread into a complete map instead of a refusal. It is a deviation from A.9a's
    written rungs and it is recorded as one: the document needs the step, and the alternative
    to writing it here was a response that says less while claiming no less.
    """
    if row.depth is Depth.BODY_FULL:
        return replace(row, depth=Depth.BODY_CLEAN, kept_tokens=None)
    if row.depth is Depth.BODY_CLEAN and row.kept_tokens is None:
        return replace(row, kept_tokens=BODY_CLEAN_HEAD_TRUNCATED_TOKENS)
    if row.depth is Depth.BODY_CLEAN:
        return _to_snippet_or_stub(row)
    if row.depth is Depth.SNIPPET:
        return replace(row, depth=Depth.STUB, kept_tokens=None)
    return None


def _degrade_band(
    layout: Layout,
    ceilings: Ceilings,
    *,
    bands: frozenset[Band],
    degrade: Callable[[PlannedRow], PlannedRow | None],
    exempt: frozenset[str] = frozenset(),
) -> Layout:
    """Degrade the rows of `bands`, worst first, until the layout fits or nothing is left.

    "Worst first" is the published E4 score ascending, then thread position descending: the
    row the query reached least, latest in the conversation, is the first to lose depth.
    Both keys are facts already in the payload, and neither is the arrival order.

    **"Fits" means fits both ceilings** (round 26, R-DISC-033). A step that stopped the moment
    the token ceiling was met left every response that was inside its token budget and outside
    the host's character cap untouched - so the driver fell through the depth steps to step 7,
    and a twelve-message thread came back as twelve withheld records and no source at all,
    when degrading its bodies to stubs would have fitted the cap with room to spare.
    """
    target = layout.ceiling_applied
    cap = ceilings.host_chars
    rows: dict[str, PlannedRow] = {row.id: row for source in layout.sources for row in source.rows}
    order = sorted(
        (row for row in rows.values() if row.band in bands and row.id not in exempt),
        key=lambda row: (row.fill_score, -row.position),
    )
    changed = 0
    # The running total is carried rather than recomputed, and a rung's effect on it is the
    # difference between the two rows' own costs - which is exact, because degrading a row
    # changes nothing else in the layout. Rebuilding and re-summing the whole response after
    # every single rung made this quadratic in the row count, and after A11's structural
    # charge the ladder degrades far more rows than it used to.
    total = layout.cost()
    # Carried alongside the token total for the same reason it is carried at all: degrading a
    # row changes that row and nothing else in the layout - not the participant index, which
    # is keyed on which rows are *present* - so the difference between the two rows' own costs
    # is exact in both units, and rebuilding the whole response after every rung was quadratic.
    total_chars = layout.chars()

    def fits() -> bool:
        return total <= target and (cap is None or total_chars <= cap)

    for row in order:
        if fits():
            break
        current = rows[row.id]
        while not fits():
            nxt = degrade(current)
            if nxt is None:
                break
            total += nxt.cost() - current.cost()
            total_chars += nxt.chars() - current.chars()
            rows[row.id] = current = nxt
            changed += 1
    if not changed:
        return layout
    return _rebuild(layout, rows)


def _rebuild(layout: Layout, rows: dict[str, PlannedRow]) -> Layout:
    return layout.with_sources(
        [source.with_rows(rows[row.id] for row in source.rows) for source in layout.sources]
    )


# -- collapsing --------------------------------------------------------------------------


def _collapsible(source: PlannedSource) -> list[PlannedRow]:
    """The rows a collapse step may take: A.9a says *stub rows*, so **every** stub row.

    A collapsed-run member is present (A.7a, R-06), which is why the floor gate passes over
    a collapse and why collapsing is the cheap step it is. The test is therefore the row's
    **depth**, not the band the planner gave it (round 25, R-DISC-030): a FILL row that step
    1 degraded to a stub, or a FLOOR row this response observed no text for, is a stub row in
    a hit-bearing thread and A.9a step 5 is written about stub rows. Reading the band instead
    meant the ladder could not recover the tokens its own earlier step had spent, which is
    how an oversized response reached step 8 with 300 uncollapsed stubs still in it.

    Nothing above stub depth is collapsible, which is what stops a floor member being
    collapsed out of a depth it earned.

    **And nothing the caller asked for is** (navigation redesign, 2026-09-14). A
    `Band.REQUESTED` row at stub depth is a stub because `view: "stub"` was the request, not
    because the map put it there; collapsing it answered `get_messages(ids, view="stub")`
    with zero rows for every request (R-M2-080). What does not fit leaves through the
    expansion path's continuation, never through this step.
    """
    return [
        row for row in source.rows if row.depth is Depth.STUB and row.band is not Band.REQUESTED
    ]


def _collapse(source: PlannedSource) -> tuple[PlannedSource, int]:
    """Collapse this source's map stubs into maximal contiguous runs (A3, R-06)."""
    taking = _collapsible(source)
    if len(taking) < 2:
        return source, 0
    by_position = sorted(taking, key=lambda row: row.position)
    runs: list[PlannedRun] = list(source.runs)
    block: list[PlannedRow] = []
    collapsed: set[str] = set()

    def flush() -> None:
        if len(block) < 2:
            block.clear()
            return
        runs.append(
            PlannedRun(
                start=block[0].position,
                end=block[-1].position,
                member_ids=tuple(row.id for row in block),
            )
        )
        collapsed.update(row.id for row in block)
        block.clear()

    for row in by_position:
        if block and row.position != block[-1].position + 1:
            flush()
        block.append(row)
    flush()
    if not collapsed:
        return source, 0
    kept = tuple(row for row in source.rows if row.id not in collapsed)
    return replace(source, rows=kept, runs=tuple(runs)), len(collapsed)


def _collapse_sources(layout: Layout, *, hit_bearing: bool) -> Layout:
    changed = 0
    sources: list[PlannedSource] = []
    for source in layout.sources:
        if source.hit_bearing is not hit_bearing:
            sources.append(source)
            continue
        rebuilt, count = _collapse(source)
        changed += count
        sources.append(rebuilt)
    if not changed:
        return layout
    return layout.with_sources(sources)


# -- the eight steps ---------------------------------------------------------------------


def step_1_query_scored_fill(layout: Layout, ceilings: Ceilings) -> Layout:
    """A.9a 1. The fill is sacrificed first, because it is what the budget bought last."""
    return _degrade_band(
        layout, ceilings, bands=frozenset({Band.FILL}), degrade=_degrade_without_head_truncation
    )


def step_2_sibling_stub_runs(layout: Layout, ceilings: Ceilings) -> Layout:
    """A.9a 2. A sibling thread's map becomes declared collapsed runs before a hit's does."""
    del ceilings
    return _collapse_sources(layout, hit_bearing=False)


def _top_k_hit_ids(layout: Layout) -> frozenset[str]:
    hits = [row for source in layout.sources for row in source.rows if row.band is Band.EVIDENCE]
    hits.sort(key=lambda row: (-row.fill_score, row.position))
    return frozenset(row.id for row in hits[:DISCLOSURE_TOP_K_HITS])


def step_3_hit_bodies_beyond_top_k(layout: Layout, ceilings: Ceilings) -> Layout:
    """A.9a 3. Hit bodies outside the protected top-k head-truncate, then drop to snippet."""
    return _degrade_band(
        layout,
        ceilings,
        bands=frozenset({Band.EVIDENCE}),
        degrade=_degrade_through_head_truncation,
        exempt=_top_k_hit_ids(layout),
    )


def step_4_floor_bodies(layout: Layout, ceilings: Ceilings) -> Layout:
    """A.9a 4. The floor's **depth** degrades here. Its membership never does."""
    return _degrade_band(
        layout,
        ceilings,
        bands=frozenset({Band.FLOOR}),
        degrade=_degrade_through_head_truncation,
    )


def step_5_hit_thread_stub_runs(layout: Layout, ceilings: Ceilings) -> Layout:
    """A.9a 5. Hit-bearing threads' stub rows become runs. Never removed, only declared."""
    del ceilings
    return _collapse_sources(layout, hit_bearing=True)


#: The steps whose exhaustion is the precondition for raising the ceiling. Derived from
#: `LADDER_STEPS` below rather than listed, so a step inserted before 6 is automatically
#: something step 6 waits for.
def _reduction_still_available(layout: Layout, ceilings: Ceilings) -> bool:
    return any(
        step.apply(layout, ceilings) != layout for step in LADDER_STEPS if step.precedence < 6
    )


def cheapest_membership_cost(layout: Layout) -> int:
    """What this response would cost if every present message were a bare stub row.

    **A counterfactual, computed, so the `ceiling{}` block can state a fact rather than a
    sentence selected by a number** (round 25, R-DISC-023). Every row drops to its cheapest
    *possible* present form - a stub row, which is still membership - and every declared run
    keeps the members it already holds. A.9a's own words are "**if and only if** the E2
    floor's *membership* cannot be carried within it", and this is that quantity.

    **It is reported and it is not a precondition, and that is a named gap rather than an
    oversight.** A.9a's rungs 3 and 4 stop at `snippet`: no published step takes a floor or
    evidence row below it, so the ladder *cannot reach* the state this function prices.
    Making the number a precondition would make the response refuse rather than degrade,
    which trades a false `why` for a missing answer. So step 6 keeps the precondition the
    architecture gives it, and `assemble._ceiling_of` puts this figure on the wire beside the
    applied ceiling, where a reader can see for themselves whether membership or depth was
    the binding constraint. The rung A.9a lacks between "floor at snippet" and "raise the
    ceiling" is an owner-visible amendment and is recorded as one.
    """
    total = RESPONSE_STRUCTURAL_TOKENS
    for source in layout.sources:
        total += row_tokens(None) * len(source.rows)
        total += sum(collapsed_run_tokens(len(run.member_ids)) for run in source.runs)
    return total


def step_6_declared_overflow(layout: Layout, ceilings: Ceilings) -> Layout:
    """A.9a 6. **The only thing that may raise the ceiling is floor membership.**

    Three conditions, and all three are checked rather than assumed from the driver's
    ordering: the ceiling is still the normal one; this response actually carries floor
    members; and steps 1-5 have nothing left to give, so the only remaining way to fit is to
    stop carrying a member. The overflow is not a budget - it is the promise that membership
    is never the thing cut.

    What round 23 did *not* do, and this round does, is state the raise truthfully:
    `cheapest_membership_cost` prices membership on its own and `assemble._ceiling_of`
    carries that figure in `ceiling.why`, so a response whose overflow bought depth rather
    than membership says so instead of asserting "E2 floor membership" from the fact that
    two numbers differ.
    """
    if layout.ceiling_applied >= ceilings.overflow:
        return layout
    if not (layout.floor_ids & layout.present_ids):
        return layout
    if _reduction_still_available(layout, ceilings):
        return layout
    # **The counterfactual A.9a's "if and only if" actually names**, now that the rungs can
    # reach it: if every message of this response were a bare stub row it would still not fit
    # the normal ceiling, so what does not fit is membership. Round 23 raised the ceiling
    # whenever steps 1-5 were exhausted and any floor member existed, which on its own fixture
    # bought snippet depth for 177 rows while membership was affordable with 1,800 tokens to
    # spare - under a `why` that said "E2 floor membership" (R-DISC-023).
    if cheapest_membership_cost(layout) <= ceilings.normal:
        return layout
    return replace(layout, ceiling_applied=ceilings.overflow)


def step_7_split_by_source(layout: Layout, ceilings: Ceilings) -> Layout:
    """A.9a 7. Whole sources leave, lowest rank first - and a source holding a floor member
    never does.

    Every accounted id of a split source becomes a `withheld` record in the same move, so
    `H ⊆ R` survives the split (contract I-1). The refusal is here **as well as** in the
    driver's gate: a step that knows it must not take something should not try, and the gate
    is what catches the day somebody edits this function.
    """
    working = layout
    while over_budget(working, ceilings) and len(working.sources) > 1:
        candidates = [
            source
            for source in working.sources
            if not (source.present_ids & working.floor_ids)
            and _may_leave_without_emptying_the_answer(source, working)
        ]
        if not candidates:
            break
        victim = max(candidates, key=lambda source: source.rank)
        split = _split_off(working, victim)
        # **Whether the split helps is a question about the binding unit** (round 26). In
        # tokens a source of one row is nearly free and its withheld records are not, so this
        # guard refused every split of a twelve-source response that was three times over the
        # host's cap in characters - where a source costs its map handle, its stamps, its
        # structural block and its mirror line, and removing one saves all of them.
        if not _shrinks(split, working, ceilings):
            break
        working = split
    return _split_a_source_whose_floor_does_not_fit(working, ceilings)


def _may_leave_without_emptying_the_answer(source: PlannedSource, layout: Layout) -> bool:
    """May this source be split off, or is it the last one carrying evidence?

    **Round 29 needs this and round 28 did not, for the same reason `_carries_nothing` does.**
    Splitting used to be expensive - every row of the split source came back as a full
    withheld record - so `_shrinks` refused most splits and the step stopped long before it
    ran out of evidence. Cost was doing the work of a rule, invisibly. Grouping made splitting
    cheap, and the step promptly split away every evidence-bearing source in a twelve-thread
    search and left a response of context with nothing matched in it.

    So the rule is written down instead of being paid for: a source carrying matched messages
    may leave only while another source still carries some. A response exists to carry
    evidence; a ladder that reaches its budget by removing all of it has not made the response
    smaller, it has made it pointless. When only one evidence-bearing source is left, the
    step declines to take it and the later steps degrade its rows instead - and if even that
    will not fit, `run_ladder` refuses rather than serving an empty answer.
    """
    if not (source.present_ids & layout.hit_ids):
        return True
    others = sum(
        1
        for other in layout.sources
        if other.thread_id != source.thread_id and (other.present_ids & layout.hit_ids)
    )
    return others > 0


def _split_off(layout: Layout, victim: PlannedSource) -> Layout:
    """Step 7: one whole source leaves, and its ids are accounted for at thread granularity.

    **Round 29, R-MCP-033.** The source is already leaving as a unit: the response emits one
    `not_included_sources[]` entry naming the thread and a `mailweave_thread_map` call that
    fetches it. Writing one withheld record per message beside that entry says the same thing
    once per message, at 516 characters each, and pointed at the same call - which is how the
    step meant to make a response smaller made it bigger. Splitting a source now costs the
    entry plus one counted group, so step 7 shrinks the response monotonically instead of
    only sometimes.

    Nothing is lost: the ids still enter `withheld_ids`, `certify` still resolves the whole
    set difference, and the group carries their exact count.
    """
    leaving = sorted(victim.present_ids & layout.accounted_ids)
    return replace(
        layout,
        sources=tuple(s for s in layout.sources if s.thread_id != victim.thread_id),
        split_off=(*layout.split_off, victim.thread_id),
        withheld_ids=(*layout.withheld_ids, *leaving),
        # One group per (thread, cap), and a split source is one thread under one cap. A
        # group of one is a group (R-V01-007): the estimate charges the shape the wire emits.
        grouped_ids=layout.grouped_ids | frozenset(leaving),
        groups=(
            layout.groups | {(victim.thread_id, WithheldCap.DISCLOSED_TOKEN_CEILING)}
            if leaving
            else layout.groups
        ),
    )


def _last_source_to_runs(layout: Layout, source: PlannedSource) -> Layout:
    """A.9a 7's last resort, first move (2026-09-15, R-M2-093): before the only
    evidence-bearing source of a **search** leaves and empties the answer, every one of its
    rows goes to stub depth and its stubs collapse into declared runs.

    **What this preserves, and why it is allowed.** A collapsed-run member is *present*
    (A.7a, R-06): the source still names every id, every hit is still a hit, every floor
    member is still in the response, and `_carries_nothing` still answers no. What is given
    up is depth - the top-k hits' protected snippets and the floor's - which the step declares
    (`row(s) reduced in depth`, `collapsed into declared runs`) and the response reports as
    `truncated_by: mailweave` with the runs' own map calls and the recommended read of the
    collapsed hits as the way back. OD-3's order holds: a response that carries its evidence
    as run members is the louder claim than an empty one, and the ladder used to prefer the
    empty one because the protected rows were not stub depth and `_collapsible` could not take
    them. Found on the semantic arm, where the shortlist's hits land in the top lexical source
    and the protection keeps it above what the cap leaves beside the bookkeeping; it is the
    ladder emptying a response it could have collapsed, whichever rung filled it.

    **Search only.** An expansion's evidence is the map or the rows the caller named
    (`evidence_is_the_map`), and a `Band.REQUESTED` row is the request itself: neither is
    ever collapsed here. The explicit-read contract (navigation redesign, 2026-09-14) is
    untouched, and run membership is not delivered content - the driver counts only rows at
    a body depth as content in hand, as before.
    """
    if layout.evidence_is_the_map:
        return layout
    rows = tuple(
        row
        if row.band is Band.REQUESTED or row.depth is Depth.STUB
        else replace(row, depth=Depth.STUB, kept_tokens=None)
        for row in source.rows
    )
    rebuilt = _collapse_whole(replace(source, rows=rows))
    if rebuilt == source:
        return layout
    return layout.with_sources(
        [rebuilt if one.thread_id == source.thread_id else one for one in layout.sources]
    )


def _collapse_whole(source: PlannedSource) -> PlannedSource:
    """Every stub row and every existing run of this source, re-cut into maximal contiguous
    runs over their union. `_collapse` only ever makes runs out of *rows*, so a stub row
    beside a run it could have joined stays a row; the last-resort collapse wants the whole
    map as runs, which is what a served map of the same thread would be."""
    taking = {row.position: row.id for row in _collapsible(source)}
    for run in source.runs:
        for offset, member in enumerate(run.member_ids):
            taking[run.start + offset] = member
    if len(taking) < 2:
        return source
    positions = sorted(taking)
    runs: list[PlannedRun] = []
    collapsed: set[str] = set()
    block: list[int] = []

    def flush() -> None:
        if len(block) >= 2:
            runs.append(
                PlannedRun(
                    start=block[0],
                    end=block[-1],
                    member_ids=tuple(taking[position] for position in block),
                )
            )
            collapsed.update(taking[position] for position in block)
        block.clear()

    for position in positions:
        if block and position != block[-1] + 1:
            flush()
        block.append(position)
    flush()
    kept = tuple(row for row in source.rows if row.id not in collapsed)
    rebuilt = replace(source, rows=kept, runs=tuple(runs))
    # A member that was in a run and is not in one now would have vanished: every old run
    # member is either in a new run or was never a run member, by construction.
    assert {m for run in source.runs for m in run.member_ids} <= collapsed
    return rebuilt


def _split_a_source_whose_floor_does_not_fit(layout: Layout, ceilings: Ceilings) -> Layout:
    """A.9a 7, last resort: a source whose **floor alone** does not fit leaves whole.

    This is the branch that used to be `DisclosureLadderExhausted` (round 25, R-DISC-020).
    Step 8 can free tokens only from rows that are not floor members; a source every one of
    whose rows is owed to a disclosed evidence message offers step 8 nothing, so without
    this the ladder ran out of steps and raised - and a query whose term is carried in a
    thread's quoted history makes every message a hit and every message a floor member, which
    is an ordinary outcome rather than an exotic one.

    Splitting the source takes the evidence **and** its floor away together, so no disclosed
    reply chain acquires a hole: A.9(2) is a statement about the hits that are still in the
    response. Every id becomes a `withheld` record with an executable affordance and the
    thread is named in `not_included_sources[]` with its `why`, which is the shape A.7a
    allows and the honest answer to "this thread does not fit": *a declared result the caller
    can act on*, not an exception out of the tool handler.

    It can empty the response of sources. That is deliberate and it is still an answer: the
    map affordance for each split thread is minted beside the record.
    """
    working = layout
    while over_budget(working, ceilings) and working.sources:
        if _step_8_would_fit(working, ceilings):
            return working
        victim = max(working.sources, key=lambda source: source.rank)
        if not _may_leave_without_emptying_the_answer(victim, working):
            # The last evidence-bearing source. Collapsed before it is split (2026-09-15):
            # a response carrying its hits as run members beats an empty one, and only if
            # the collapsed source still does not fit does the split below take it.
            collapsed = _last_source_to_runs(working, victim)
            if collapsed != working:
                working = collapsed
                continue
        split = _split_off(working, victim)
        if not _may_leave_without_emptying_the_answer(victim, working):
            # It is leaving anyway, at its smallest. Carried for the refusal's account of
            # itself (R-M2-095): the number a reader needs is what this source cost beside
            # the bookkeeping, and after the split nothing else remembers it.
            split = replace(split, last_evidence_source=victim)
        if not _shrinks(split, working, ceilings):
            # Splitting would cost more than carrying: every id of the source becomes a
            # `withheld` record, and enough records outweigh the rows they replace. Refusing
            # here is what leaves `DisclosureLadderExhausted` for the one shape that really
            # cannot be answered - a thread too large to carry even as pure membership - and
            # keeps it out of the shapes that can.
            return working
        working = split
    return working


def _step_8_would_fit(layout: Layout, ceilings: Ceilings) -> bool:
    """Whether A.9a step 8, taking everything it may, would bring this layout inside.

    Step 7 precedes step 8, so without this the split would run first and take a whole
    source away that the *next* step could have saved by withholding a handful of rows. The
    question is answered by running step 8's own function against a ceiling of zero, which
    makes it withhold every row it is allowed to - one implementation, asked a hypothetical,
    rather than a second copy of its rule that could drift from it.

    "Inside" means inside **both** ceilings from round 26 on, so the hypothetical is asked
    against a character cap of one as well: a step 8 that would fit the token ceiling and
    leave the response over the host's cap is not a reason to skip the split.
    """
    maximal = step_8_withheld_record(
        replace(layout, ceiling_applied=0), replace(ceilings, normal=0, overflow=0, host_chars=1)
    )
    return not over_budget(replace(maximal, ceiling_applied=layout.ceiling_applied), ceilings)


def step_8_withheld_record(layout: Layout, ceilings: Ceilings) -> Layout:
    """A.9a 8. The last path out of the payload - and never for a floor member.

    Candidates are worst-scoring first, and **non-hits go before hits**: a message the query
    reached least is the one a ceiling costs the caller, and a message no rung matched is
    reached less than one that did. A floor member is never a candidate, whether or not it is
    also a hit, which is the asymmetry OD-3 buys.

    A.9a names the hit case because that is the one that hurts; round 25 widened the
    candidate set to every non-floor row because the alternative was
    `DisclosureLadderExhausted` for a residue of ordinary map rows that no earlier step could
    take (R-DISC-020). Every candidate leaves as a `withheld` record with an executable
    affordance, so widening the step widens what is *declared*, never what is dropped.
    """
    if not over_budget(layout, ceilings):
        return layout
    total = layout.cost()
    total_chars = layout.chars()
    cap = ceilings.host_chars
    already = frozenset(layout.withheld_ids)
    # **And never a requested row** (navigation redesign, 2026-09-14): what the caller named,
    # or the page they asked for, leaves a response only through the expansion path's
    # continuation or a declared decline - a withheld record for the thing that was asked for
    # is R-M2-080's loop in a new place. Search never plans this band, so nothing changes there.
    candidates = sorted(
        (
            row
            for source in layout.sources
            for row in source.rows
            if row.id not in layout.floor_ids
            and row.id not in already
            and row.band is not Band.REQUESTED
        ),
        key=lambda row: (row.id in layout.hit_ids, row.fill_score, -row.position),
    )
    taken: list[str] = []
    # **And never the last matched message present** (2026-09-15, R-M2-093): a hit row may
    # leave only while another hit stays present, as a row or a run member - the same rule
    # `_carries_nothing` states for the whole ladder and `_may_leave_without_emptying_the_answer`
    # states for step 7's sources. Without it this step could withhold a last source's hits one
    # record at a time and hand the emptiness gate a response that step 7's last resort would
    # have collapsed into runs and served; `_step_8_would_fit` asks this step first, so the
    # collapse was never tried.
    hits_present = set(layout.hit_ids & layout.present_ids)
    for victim in candidates:
        if total <= layout.ceiling_applied and (cap is None or total_chars <= cap):
            break
        if victim.id in hits_present and len(hits_present) <= 1:
            continue
        # A withheld record is cheaper than the row it replaces, and this is where that is
        # *checked* rather than assumed: a step that traded a cheap disposition for a dearer
        # one would enlarge the response it is shrinking, which A11 forbids and the driver's
        # third gate would refuse outright. The record is only charged for an id this
        # response accounts for; an id outside `accounted_ids` gets no record and no charge.
        #
        # **Checked in the unit that is binding** (round 26): a record can be cheaper than its
        # row in characters and dearer in tokens, and refusing on the unit that is not the one
        # over budget is how the step declines to do the thing it exists to do.
        accounted = victim.id in layout.accounted_ids
        replaced = WITHHELD_RECORD_TOKENS if accounted else 0
        replaced_chars = withheld_chars(victim.id, widest_thread_id(layout)) if accounted else 0
        if cap is not None and total_chars > cap:
            if replaced_chars >= victim.chars():
                continue
        elif replaced >= victim.cost():
            continue
        total += replaced - victim.cost()
        total_chars += replaced_chars - victim.chars()
        taken.append(victim.id)
        hits_present.discard(victim.id)
    if not taken:
        return layout
    leaving = frozenset(taken)
    emptied = replace(
        layout,
        sources=tuple(
            source.with_rows(row for row in source.rows if row.id not in leaving)
            for source in layout.sources
        ),
        withheld_ids=(*layout.withheld_ids, *taken),
    )
    return _retire_emptied_sources(emptied)


def _retire_emptied_sources(layout: Layout) -> Layout:
    """A source this step emptied leaves as a split rather than staying on as a claim of zero.

    **Round 27, R-MCP-032.** Step 8 takes rows one at a time and does not ask what a source
    has left, so it could withhold the last row of a thread and emit the source anyway - a
    source declaring `included: 0 of 1` with no affordance naming the thread, which contract
    R-07 refuses at the envelope and which reached the caller as a `-32603` on an ordinary wide
    search once round 27's estimate let the ladder degrade that far. Retiring the source is not
    a new disposition: `_split_off` is step 7's own move, the ids are already `withheld` records
    with their affordances, and the thread gains the `not_included_sources[]` entry and map
    affordance that R-07 asks for. Nothing leaves the response that had not already left it -
    what changes is that the response now says so in the shape the contract names.

    It shrinks in both units - a source costs its map handle, its stamps and its structural
    block, a not-included entry costs a line and an affordance - so the driver's third gate
    passes it rather than having to make an exception for it.
    """
    working = layout
    for source in layout.sources:
        if not source.rows and not source.runs:
            working = _split_off(working, source)
    return working


#: A.9a step 6's precedence. Named rather than written as a literal at the two places that
#: ask "did the ladder actually remove anything?", because step 6 is the one step that
#: changes the response's declared ceiling and removes nothing from its payload.
DECLARED_OVERFLOW_STEP: Final[int] = 6


@dataclass(frozen=True)
class Step:
    """One entry of the published precedence. Data, so the order can be read and planted."""

    precedence: int
    name: str
    apply: Callable[[Layout, Ceilings], Layout]


#: AD A.9a's precedence, in the document's order. `test_the_published_precedence_is_the_one_
#: the_architecture_prints` reads the architecture document and asserts this tuple against it,
#: so the order is checked against its authority rather than against a reader's memory.
LADDER_STEPS: Final[tuple[Step, ...]] = (
    Step(1, "e4_query_scored_fill", step_1_query_scored_fill),
    Step(2, "sibling_source_stub_runs", step_2_sibling_stub_runs),
    Step(3, "hit_bodies_beyond_top_k", step_3_hit_bodies_beyond_top_k),
    Step(4, "e2_floor_bodies", step_4_floor_bodies),
    Step(5, "hit_thread_stub_runs", step_5_hit_thread_stub_runs),
    Step(6, "declared_overflow_ceiling", step_6_declared_overflow),
    Step(7, "split_by_source", step_7_split_by_source),
    Step(8, "withheld_record", step_8_withheld_record),
)


# -- the two driver-level gates ------------------------------------------------------------


def assert_floor_intact(before: Layout, after: Layout, *, precedence: int, name: str) -> None:
    """No disclosed evidence message loses a reply parent or a direct child. The round's claim.

    Checked against `before.present_ids` rather than against `floor_ids` alone so the gate
    says something true when a caller hands the ladder a layout that was already missing a
    member: this function defends what the ladder does, and the planner's own construction
    is what puts the floor in.

    **The guarantee is relative to the evidence still disclosed, and round 25 made the gate
    say so.** A.9(2) is a statement about *each hit's* neighbourhood: while a hit is in the
    payload, its reply parent and direct children are in the payload with it. A step that
    takes a whole source away - A.9a 7, which declares every id it removes in
    `not_included_sources[]` and as a `withheld` record - takes the evidence and its floor
    together and leaves no chain with a hole in it. Reading the guarantee as "these ids may
    never leave, whatever happens to the messages they are owed to" would make the only
    honest answer to a floor larger than the overflow ceiling an exception rather than a
    declared result, which is the trade R-DISC-020 refused.

    `floor_pairs` is what makes the difference expressible: it names *whose* floor each
    member is, so the gate can allow the lawful removal and refuse every other one - a
    member dropped while an evidence message that needs it is still disclosed.
    """
    kept = after.present_ids
    before_present = before.present_ids
    lost = sorted(
        {
            member
            for anchor, member in before.floor_pairs
            if anchor in kept and member in before_present and member not in kept
        }
    )
    if not lost and not before.floor_pairs:
        # A layout built without the reply tree (WS-15's expansion path builds one directly)
        # falls back to the flat set, so the gate is never silently vacuous there.
        lost = sorted((before_present & before.floor_ids) - kept)
    if lost:
        raise FloorMembershipLost(
            f"A.9a step {precedence} ({name}) removed {lost} from the payload while the "
            "evidence message(s) they hang off are still disclosed. These are reply parents "
            "or direct children of evidence messages, and the E2 floor guarantees their "
            "membership absolutely: while a hit is in the response, they are present as a row "
            "or as a declared collapsed-run member at every step and at both ceilings. Depth "
            "degrades, membership does not (OD-3, AD A.9a)"
        )


class LadderStepInflated(MailweaveError):
    """A degradation step made the response bigger. A ladder that climbs is not a ladder.

    The third driver-level gate, added in round 25. `snippet -> stub` used to raise the
    estimate - a stub was charged 40 and a snippet only its text - so step 1 took a
    9,300-token layout to 27,270 and the ladder then refused the response it had inflated.
    Amendment A11 charges a row its structure at every depth, which makes every published
    rung monotone; this gate is what makes that true of a rung nobody has written yet.
    """


def assert_cost_did_not_rise(
    before: Layout,
    after: Layout,
    *,
    precedence: int,
    name: str,
    bounds: Ceilings | None = None,
) -> None:
    """A step reduces the measured size, or it is not a degradation step (A11).

    Step 6 is exempt and is the only exemption: it changes the *ceiling*, removes nothing
    from the payload, and by construction leaves the cost identical. The exemption is named
    by `DECLARED_OVERFLOW_STEP` rather than written as a literal, so it follows the step.

    **A response is measured in two units from round 26, so "the measured size" needs saying
    exactly**: a step may not enlarge the quantity that is over budget. Where the host's
    character cap is what binds, a step that cuts characters and costs a few tokens is doing
    its job - a withheld record replacing a one-row source is the case - and refusing it would
    leave the response over the cap the host actually enforces. Where no character cap applies,
    which is every layout nobody is serving, this is exactly the token gate round 25 wrote.
    """
    if precedence == DECLARED_OVERFLOW_STEP:
        return
    if (
        bounds is not None
        and bounds.host_chars is not None
        and before.chars() > bounds.host_chars
        and after.chars() < before.chars()
    ):
        return
    if after.cost() > before.cost():
        raise LadderStepInflated(
            f"A.9a step {precedence} ({name}) took the response from {before.cost()} to "
            f"{after.cost()} estimated tokens. A degradation step reduces the measured size "
            "or it is not a degradation step: the ladder would otherwise enlarge the thing "
            "it is degrading and then refuse it (amendment A11, R-DISC-019)"
        )


def assert_nothing_vanished(before: Layout, after: Layout, *, precedence: int, name: str) -> None:
    """Contract I-1 over one step: an id that was present is present, withheld, or split off.

    The `withheld_ids` half is what makes step 7 and step 8 lawful; without it they would be
    exactly the silent drop `withheld := H - disclosed` exists to make unrepresentable.
    """
    accounted = after.present_ids | frozenset(after.withheld_ids)
    lost = sorted((before.present_ids & before.accounted_ids) - accounted)
    if lost:
        raise FloorMembershipLost(
            f"A.9a step {precedence} ({name}) dropped {lost} without a withheld record. A "
            "cap converts a hit into a withheld record with an executable affordance; it "
            "never removes it silently (contract I-1, AD A.7a)"
        )


#: The sentence a response uses to say that the **host's character cap** is what removed
#: something. One wording in one place, because three producers write it - the withheld
#: records the search path files, the ones the expansion path files, and the refusal when
#: nothing fits - and three spellings of one fact is how a reader comes to see three accounts
#: of one reduction.
HOST_CAP_WHY: Final[str] = (
    "the response did not fit the host's {cap}-character result cap. The published token "
    "ceiling does not bound the rendered response in characters, so A.9a reduced this "
    "response to fit the cap the host enforces"
)


def over_budget(layout: Layout, bounds: Ceilings) -> bool:
    """Whether this layout exceeds **either** ceiling it is held to (round 26, R-DISC-033).

    The token ceiling is A.9a's own; the character cap is the host's, and it is checked here
    rather than converted into the other unit because no conversion between them is a bound -
    a response of many short rows and one of few long ones sit at opposite ends of every
    characters-per-token ratio. A layout nobody is serving carries no character cap and this
    is exactly the token test it has always been.
    """
    if layout.cost() > layout.ceiling_applied:
        return True
    return bounds.host_chars is not None and layout.chars() > bounds.host_chars


def _chars_bind(layout: Layout, bounds: Ceilings) -> bool:
    """Whether the host's cap, rather than the token ceiling, is what this layout exceeds."""
    return bounds.host_chars is not None and layout.chars() > bounds.host_chars


def _shrinks(after: Layout, before: Layout, bounds: Ceilings) -> bool:
    """Whether a candidate reduction actually reduces the quantity that is binding.

    Step 7 and step 8 both ask this before committing: a withheld record is cheaper than the
    row it replaces in the ordinary case and dearer in some, and which is true depends on the
    unit. Answering in tokens alone is what let a twelve-source response refuse to split while
    it was three times over the host's cap in characters.
    """
    if _chars_bind(before, bounds):
        return after.chars() < before.chars()
    return after.cost() < before.cost()


def run_ladder(
    layout: Layout,
    *,
    ceilings: Ceilings | None = None,
    steps: Sequence[Step] = LADDER_STEPS,
    explain: bool = True,
) -> tuple[Layout, tuple[LadderStep, ...]]:
    """Run A.9a's precedence until the layout fits **every** ceiling it is held to.

    `steps` is a parameter so a test can substitute a deliberately broken step and watch the
    gates refuse it. It defaults to the published precedence, and the driver applies all three
    gates to the output of every step whatever is passed - which is the point: the defence is
    the driver's, so it covers a step nobody has written yet.

    **The character half** (round 26, R-DISC-033, R-MCP-020/021). The token ceiling does not
    bound the rendered response in the unit an MCP host enforces: a twelve-message thread of
    ordinary messages estimated well inside 9,000 tokens and rendered 25,358 characters against
    a 25,000-character cap, declaring `truncated_by: null`, `partial: false` and `included: 12
    of 12` about messages the host then cut. So `Ceilings` carries the host's cap when a
    response is being served, `over_budget` is the fit test in both units, and the published
    steps run until both are met - which is the same machinery, the same withheld records and
    the same affordances, reaching for one more reason.

    A layout carrying no character cap - the harness' arm comparison, DISC-04's efficiency
    ratio, any measurement - behaves exactly as it did before this round.

    A layout that cannot be brought inside raises `DisclosureLadderExhausted`, which
    `surface/server.py` turns into a declared refusal with an executable narrower retry.
    Handing it over instead would be host truncation, which DISC-06 forbids and OD-3 branch
    (ii) names as a defect.

    **`explain`** (2026-09-15, R-M2-095): a refusal carries a `RefusalCause`, and the cause's
    `fits_at` is this same function run over the same retrieval at every narrower width. Those
    inner runs pass `explain=False`: they are the hypothetical, and a hypothetical that
    explained itself would recurse.
    """
    bounds = ceilings or Ceilings()
    working = replace(
        layout,
        ceiling_applied=bounds.normal,
        host_capped=_chars_bind(replace(layout, ceiling_applied=bounds.normal), bounds),
    )
    applied: list[LadderStep] = []
    for step in steps:
        if not over_budget(working, bounds):
            break
        before = working
        after = step.apply(before, bounds)
        assert_floor_intact(before, after, precedence=step.precedence, name=step.name)
        assert_nothing_vanished(before, after, precedence=step.precedence, name=step.name)
        assert_cost_did_not_rise(
            before, after, precedence=step.precedence, name=step.name, bounds=bounds
        )
        if after == before:
            continue
        working = after
        applied.append(
            LadderStep(
                precedence=step.precedence,
                name=step.name,
                detail=_detail(before, after),
                rows_changed=_rows_changed(before, after),
            )
        )
    if over_budget(working, bounds):
        cause = (
            refusal_cause(layout, working, bounds, kind=RefusalKind.SIZE, steps=steps)
            if explain
            else None
        )
        raise DisclosureLadderExhausted(
            (
                _exhausted_by_chars(working, bounds.host_chars)
                if _chars_bind(working, bounds)
                else _exhausted(working)
            )
            + _cause_sentence(cause),
            top_thread=top_hit_thread(layout),
            hit_threads=hit_thread_count(layout),
            segmented=layout.segmented,
            cause=cause,
        )
    if _carries_nothing(working):
        cause = (
            refusal_cause(layout, working, bounds, kind=RefusalKind.EMPTY, steps=steps)
            if explain
            else None
        )
        raise DisclosureLadderExhausted(
            _exhausted_by_emptiness(working) + _cause_sentence(cause),
            top_thread=top_hit_thread(layout),
            hit_threads=hit_thread_count(layout),
            segmented=layout.segmented,
            cause=cause,
        )
    return working, tuple(applied)


def refusal_cause(
    initial: Layout,
    working: Layout,
    bounds: Ceilings,
    *,
    kind: RefusalKind,
    steps: Sequence[Step] = LADDER_STEPS,
) -> RefusalCause:
    """What this refusal was made of, and what the same ladder does at every narrower width.

    The unit is the one that bound: characters when the host's cap is what the refused layout
    exceeds, tokens otherwise (an emptiness refusal fits both, and reports the host's unit
    when a host cap is in force, the token ceiling when none is). The terms are the refused
    layout's own estimate. `fits_at` is filled only for a query layout that mapped more than
    one hit-bearing thread: an expansion has no width to narrow, and a search at width 1 has
    nowhere narrower to go on this dimension.
    """
    chars_bind = bounds.host_chars is not None and (
        kind is RefusalKind.EMPTY or _chars_bind(working, bounds)
    )
    host_cap = bounds.host_chars if bounds.host_chars is not None else 0
    cap = host_cap if chars_bind else working.ceiling_applied
    terms = chars_terms(working) if chars_bind else token_terms(working)
    arranged = arrange_groups(working.groups, foldable=working.foldable_caps)
    named: dict[str, int] = {}
    for _thread, group_cap in arranged.named:
        named[group_cap.value] = named.get(group_cap.value, 0) + 1
    folded = {group_cap.value: len(keys) for group_cap, keys in arranged.folded.items() if keys}
    last = working.last_evidence_source
    residual = None if last is None else (last.chars() if chars_bind else last.cost())
    fits_at: dict[int, int] = {}
    refused: list[int] = []
    width = hit_thread_count(initial)
    if not initial.evidence_is_the_map:
        for narrower in range(width - 1, 0, -1):
            hypothetical = _initial_at_width(initial, narrower)
            if hypothetical is None:
                continue
            try:
                finished, _steps = run_ladder(
                    hypothetical, ceilings=bounds, steps=steps, explain=False
                )
            except DisclosureLadderExhausted:
                refused.append(narrower)
                continue
            fits_at[narrower] = finished.chars() if chars_bind else finished.cost()
    return RefusalCause(
        kind=kind,
        unit="chars" if chars_bind else "tokens",
        cap=cap,
        terms=terms,
        groups_by_cap=named,
        folded_by_cap=folded,
        width=width,
        top_thread=top_hit_thread(initial),
        residual_thread=None if last is None else last.thread_id,
        residual=residual,
        fits_at=fits_at,
        refused_at=tuple(refused),
    )


def _initial_at_width(initial: Layout, width: int) -> Layout | None:
    """The layout the producer would have handed the ladder at `max_hit_threads=width`.

    The same retrieval, the same pool, the same hits: `max_hit_threads` decides only which
    threads are *mapped* - the first `width` of the producer's cut order, which every mapped
    source carries as `mapped_at` (the ranking's `rank` reorders the mapped ones afterwards
    and is not that order) - and the rest are accounted for at thread granularity under the
    width cap, one foldable group each, their ids grouped, exactly as `assemble` seeds them
    before the ladder runs. So the hypothetical keeps the sources the cut would keep and
    demotes the others to that shape. A demoted thread's hits leave `hit_ids` and its floor
    obligations leave `floor_pairs`, as they would at the producer, because the top-k
    protection (step 3) is chosen over `hit_ids`. `None` when nothing would be demoted,
    which is not a narrower width, or when the sources carry no cut order at all.

    What stays a superset, harmlessly: `accounted_ids` (at the narrower width the ledger
    would not have observed the demoted threads' full maps; here they are in `grouped_ids`
    too, so no record is charged for them either way).
    """
    demoted = [
        source
        for source in initial.sources
        if source.mapped_at is not None and source.mapped_at >= width
    ]
    if not demoted:
        return None
    gone = {source.thread_id for source in demoted}
    demoted_ids: frozenset[str] = frozenset()
    for source in demoted:
        demoted_ids |= source.present_ids
    kept_pairs = tuple(pair for pair in initial.floor_pairs if pair[0] not in demoted_ids)
    return replace(
        initial,
        sources=tuple(source for source in initial.sources if source.thread_id not in gone),
        hit_ids=initial.hit_ids - demoted_ids,
        floor_pairs=kept_pairs,
        floor_ids=initial.floor_ids - demoted_ids,
        grouped_ids=initial.grouped_ids | (demoted_ids & initial.accounted_ids),
        groups=initial.groups | {(thread_id, WithheldCap.MAX_HIT_THREADS) for thread_id in gone},
    )


def _cause_sentence(cause: RefusalCause | None) -> str:
    """The cause's terms, in the refusal's own prose, so a reader without the block has them."""
    if cause is None:
        return ""
    terms = cause.terms
    caps = ", ".join(f"{name} {count}" for name, count in sorted(cause.groups_by_cap.items()))
    parts = [
        f". The bookkeeping alone is {terms.bookkeeping} of the {cause.cap}-{cause.unit} cap "
        f"(structural {terms.structural}, request echo {terms.echo}, {terms.records} in "
        f"withheld records, {terms.groups} in named groups"
        + (f" [{caps}]" if caps else "")
        + f", {terms.tails} in tails, {terms.not_included} in not-included entries)"
    ]
    if cause.residual is not None and cause.residual_thread is not None:
        parts.append(
            f"; the top thread's smallest inventory, {cause.residual_thread} as collapsed "
            f"runs, is {cause.residual} more"
        )
    # Which narrower width fits, if any, is the recovery's sentence to say (it names the
    # retry); the table itself travels machine-readably as `cause.fits_at`.
    return "".join(parts) + "."


def hit_thread_count(layout: Layout) -> int:
    """How many sources carry a matched message: the search width actually in effect."""
    return sum(1 for source in layout.sources if source.present_ids & layout.hit_ids)


def top_hit_thread(layout: Layout) -> str | None:
    """The highest-ranked source that carries a matched message, or `None` if none does.

    Lowest `rank` is highest priority, as everywhere in the ladder (step 7 splits the
    *highest* rank first). This is the thread a search-to-map hop names.
    """
    bearing = [source for source in layout.sources if source.present_ids & layout.hit_ids]
    if not bearing:
        return None
    return min(bearing, key=lambda source: source.rank).thread_id


def _carries_nothing(working: Layout) -> bool:
    """Has the ladder converged on a response with no mail in it?

    **Round 29 needs this check, and round 28 did not, and that is worth writing down.**
    Before withholdings could be grouped, an emptied response was *expensive*: every row the
    ladder removed came back as a full `withheld` record, so a layout stripped to nothing was
    still far over the cap and `over_budget` above raised. The cost of the bookkeeping was
    acting as the guard against emptiness, by accident.

    Grouping removed that accident. A source split off whole now costs one counted group, so
    a layout with every source gone is small, legal, and worth nothing to the caller - and
    without this check the ladder would have converged on it and served it. That is a worse
    failure than the one round 29 set out to fix: R-MCP-033 was a response that declined when
    it should have answered; this would be a response that answers with nothing and does not
    say so.

    So emptiness becomes an explicit inability rather than a side effect of arithmetic. The
    condition is *evidence*, not rows: a response that kept context stubs and lost every
    matched message has not answered the question either.

    **A response with no evidence to begin with is not this.** A search that retrieved nothing
    has an honest empty answer to give - "not found" is a result - and the first version of
    this check raised on exactly that, because it read "no rows present" as the condition
    rather than "no evidence survived". The two differ precisely when there was never any
    evidence, which is the ordinary no-match case and not a failure at all.
    """
    if working.hit_ids:
        return not (working.hit_ids & working.present_ids)
    # **R-V01-006.** A thread map names no hits, so the first version of this gate never
    # fired for one: a map of a 420-message thread whose only source step 7 split off came
    # back as an emptied envelope, ROUTE-01 refused it, and the caller saw `-32603` - the
    # exact failure R-MCP-039 was about, on the second producer. For an expansion the map
    # is the evidence: accounted ids and no source left to carry any of them is nothing.
    if working.evidence_is_the_map:
        return bool(working.accounted_ids) and not working.sources
    return False


def _exhausted_by_emptiness(working: Layout) -> str:
    """The refusal when the ladder could only fit by carrying no mail (round 29).

    Deliberately a third message rather than a reuse of the two above: those say *this
    response is too large*, and a caller acts on that by asking for less. This one says *no
    response this ladder can build from what was retrieved carries any of it*, and a caller
    acts on that by asking for something different - which is why the retry minted beside it
    must change dimension rather than narrow further (R-MCP-033 requirement 5).
    """
    return (
        f"the A.9a ladder ran every published step and every arrangement that fits carries no "
        f"mail: {len(working.hit_ids)} retrieved message(s), "
        f"{len(working.hit_ids & working.present_ids)} of them present, "
        f"{len(working.split_off)} source(s) split off and "
        f"{len(working.accounted_ids - working.present_ids)} message(s) withheld. Emitting it "
        "would be an answer in shape only. DISC-06 forbids handing truncation to the host and "
        "OD-3 forbids the quieter claim: a response that fits because it carries nothing is "
        "the second of those, so this declines instead"
    )


def _exhausted(working: Layout) -> str:
    """The refusal, with *what is left* derived from the layout rather than asserted.

    Round 23's message said "the remaining payload is floor membership" whatever the
    remaining payload was; on the input R-DISC drove it with, the remainder was 310 fill and
    evidence rows and one floor member (R-DISC-020). The sentence is now counted off the
    layout, so it is a fact about this response.
    """
    rows = [row for source in working.sources for row in source.rows]
    floor = sum(1 for row in rows if row.id in working.floor_ids)
    runs = sum(len(source.runs) for source in working.sources)
    members = sum(len(run.member_ids) for source in working.sources for run in source.runs)
    return (
        f"the A.9a ladder ran every published step and the response is still "
        f"~{working.cost()} whitespace tokens against a declared ceiling of "
        f"{working.ceiling_applied}. Emitting it would hand truncation to the host, which "
        f"DISC-06 forbids. What is left is {len(rows)} row(s), of which {floor} are E2 floor "
        f"membership the ladder may never remove, and {runs} declared collapsed run(s) "
        f"carrying {members} member(s). A floor larger than the overflow ceiling is the state "
        "OD-3 pre-authorises a design change for rather than a quieter claim"
    )


def _exhausted_by_chars(working: Layout, cap: int | None) -> str:
    """The refusal when the *host's* cap is the one that cannot be met.

    Separate from `_exhausted` because the two say different things and a caller acts on them
    differently: one is about the ceiling this product publishes, the other about the size the
    host will accept, and a message naming the wrong one would send a reader to the wrong
    argument.
    """
    rows = [row for source in working.sources for row in source.rows]
    return (
        f"the A.9a ladder ran every published step and the response still estimates "
        f"~{working.chars()} characters against the host's cap of {cap}. Emitting it would "
        f"hand truncation to the host, which DISC-06 forbids and which no later layer can "
        f"declare - the cut happens above the SDK, outside the protocol. What is left is "
        f"{len(rows)} row(s), {len(working.sources)} source(s) and "
        f"{len(working.accounted_ids - working.present_ids)} withheld record(s). Ask for a "
        "narrower slice: one thread, or fewer messages of it"
    )


def _rows_changed(before: Layout, after: Layout) -> int:
    was = {row.id: (row.depth, row.kept_tokens) for source in before.sources for row in source.rows}
    now = {row.id: (row.depth, row.kept_tokens) for source in after.sources for row in source.rows}
    moved = sum(1 for mid, state in was.items() if now.get(mid) != state)
    return moved


def _detail(before: Layout, after: Layout) -> str:
    """A mechanical account of one step, from the two layouts. Never a rationale."""
    parts: list[str] = []
    if after.ceiling_applied != before.ceiling_applied:
        parts.append(f"ceiling {before.ceiling_applied} -> {after.ceiling_applied}")
    newly_split = len(after.split_off) - len(before.split_off)
    if newly_split:
        parts.append(f"{newly_split} source(s) split off")
    newly_withheld = len(after.withheld_ids) - len(before.withheld_ids)
    if newly_withheld:
        parts.append(f"{newly_withheld} message(s) withheld")
    runs_before = sum(len(s.runs) for s in before.sources)
    runs_after = sum(len(s.runs) for s in after.sources)
    members_before = sum(len(r.member_ids) for s in before.sources for r in s.runs)
    members_after = sum(len(r.member_ids) for s in after.sources for r in s.runs)
    if members_after > members_before:
        # Counted in members rather than runs: a re-cut can merge six runs into one while
        # collapsing five more rows, and "-5 collapsed run(s) declared" was arithmetic, not
        # an account (2026-09-15).
        parts.append(
            f"{members_after - members_before} message(s) collapsed into declared runs "
            f"({runs_before} -> {runs_after} run(s))"
        )
    elif runs_after != runs_before:
        parts.append(f"runs re-cut {runs_before} -> {runs_after}")
    moved = _rows_changed(before, after)
    if moved:
        parts.append(f"{moved} row(s) reduced in depth")
    parts.append(f"{before.cost()} -> {after.cost()} tokens (estimate)")
    return "; ".join(parts)
