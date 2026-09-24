"""The shape the A.9a ladder operates on, and the one place its size is computed.

**Why a layout rather than an `Envelope`.** The ladder has to measure a response, shrink
it, and measure it again, several times, before anything is built. An `Envelope` refuses to
exist while it exceeds its ceiling (DISC-06), which is right and makes it useless as the
ladder's working representation. `Layout` is that representation: it holds exactly what
determines the response's size, it is immutable, and every step returns a new one.

**One cost function, and it is the envelope's own.** `layout_tokens` does not re-implement
`mailweave.envelope.measure.measure_tokens`; it *calls the same two functions*, `row_tokens`
and `collapsed_run_tokens`, over the same inventory of rows and runs, and adds the same
response-level constant. Two independently-written measures would let the ladder believe it
had fitted a response the envelope then refuses, which is host truncation arriving from
inside (DISC-06). `test_the_ladders_measure_and_the_envelopes_measure_are_the_same_number`
asserts the two agree on an assembled response rather than on this paragraph.

**Amendment A11's second rule lives in `row_tokens`, one layer down:** a row is charged its
structural cost at every depth, so `snippet -> stub` can no longer make the response larger.
The ladder's own driver asserts that monotonicity over every step (`ladder.run_ladder`)
rather than trusting this paragraph either.

Both are named **estimates** everywhere they appear: DISC-04's pinned tokenizer is
registered at G0, and inventing one here would make this estimate the de facto bar.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final

from mailweave.constants import (
    BODY_CLEAN_SOFT_CAP_TOKENS,
    BODY_FULL_SOFT_CAP_TOKENS,
)
from mailweave.constants import (
    MAX_BODY_FETCHES_L0 as RECOMMENDED_EXPANSION_LIMIT,
)
from mailweave.content.normalize import head_truncate
from mailweave.content.reductions import Reduction, ReductionKind
from mailweave.envelope.grouping import GroupKey, arrange_groups
from mailweave.envelope.measure import (
    NOT_INCLUDED_SOURCE_TOKENS,
    RESPONSE_STRUCTURAL_CHARS,
    RESPONSE_STRUCTURAL_TOKENS,
    SOURCE_STRUCTURAL_TOKENS,
    WITHHELD_GROUP_TOKENS,
    WITHHELD_RECORD_TOKENS,
    WITHHELD_TAIL_TOKENS,
    collapsed_run_chars,
    collapsed_run_tokens,
    declarations_chars,
    not_included_block_chars,
    not_included_chars,
    participants_chars,
    participants_tokens,
    recommended_expansion_chars,
    row_chars,
    row_tokens,
    source_chars,
    withheld_chars,
    withheld_group_chars,
    withheld_tail_chars,
)
from mailweave.envelope.vocab import Depth, WithheldCap
from mailweave.envelope.wire import AttachmentMetadata, ThreadParticipant, participants_within


class Band(StrEnum):
    """Which of A.9's tiers put a row in the payload. The ladder degrades by band.

    A closed vocabulary because A.9a's precedence is written in terms of it: step 1 is the
    fill, step 3 is hit bodies, step 4 is floor bodies, steps 2 and 5 are stub rows. A row
    with no band would be a row no step of the published precedence describes.
    """

    #: A.9(1): a message a retrieval rung matched. Disclosed at body depth by default.
    EVIDENCE = "evidence"
    #: A.9(2): the reply parent or a direct child of an evidence message.
    FLOOR = "floor"
    #: A.9(3): a message the E4 query score reached.
    FILL = "fill"
    #: A.9(4): everything else in a mapped thread - a stub row in the map.
    MAP = "map"
    #: A message the caller **named** in an explicit read, or a position of the page a
    #: thread map was asked for (navigation redesign, 2026-09-14). The request itself, so no
    #: step of the ladder collapses it into a run or degrades it below the depth asked for;
    #: what does not fit is carried by a continuation instead. Search never plans this band.
    REQUESTED = "requested"


@dataclass(frozen=True)
class PlannedRow:
    """One message as the ladder sees it: a place, a band, a depth, and the text available.

    `body` and `snippet` are what this response *holds*, not what it shows; `depth` and
    `kept_tokens` are what it shows. Keeping the two apart is what lets a step degrade a row
    without losing the ability to say how much it removed.
    """

    id: str
    position: int
    band: Band
    depth: Depth
    #: The default view of the fetched body, or `None` when no body was fetched for this
    #: message. `None` is a real state: `max_body_fetches` is a published cap (A.7).
    body: str | None = None
    #: Gmail's `snippet`, or `None` when the observation carried none.
    snippet: str | None = None
    #: How many head tokens of `body` this row shows. `None` means this depth's published
    #: soft cap from `SOFT_CAP_TOKENS`; a smaller number is a ladder step's head truncation.
    kept_tokens: int | None = None
    #: Reductions the content pipeline already declared for this message (A7, D.4a).
    base_reductions: tuple[Reduction, ...] = ()
    #: The E4 score, for rows the fill reached and for evidence rows ranked at step 3.
    #: Structural rows carry 0, which is not a claim that the query missed them.
    fill_score: int = 0
    #: The attachments the row will declare, metadata only, so the estimate can charge the
    #: block the wire carries (R-V01-003). The ladder never changes them; they are here so
    #: `chars()` can price them off the objects themselves.
    attachments: tuple[AttachmentMetadata, ...] = ()
    #: This message's `Authentication-Results` header, when the observation carried one and
    #: it is inside `MAX_AUTH_RECORD_CHARS`. Held so the ladder charges the exact string the
    #: wire will carry (INJ-05); `""` is a row that will carry no record.
    auth_record: str = ""
    #: The folded `From` address and the display name this row's attribution will carry
    #: (2026-09-21), by `structure.threadmap.from_header_of`'s rule, so the ladder charges the
    #: exact strings the wire will carry. Both `""` for a row that observed no headers.
    from_address: str = ""
    from_display: str = ""

    def __post_init__(self) -> None:
        if self.depth is Depth.SNIPPET and self.snippet is None:
            raise ValueError(
                f"row {self.id} is planned at snippet depth and this response holds no "
                "snippet for it; a depth is a statement about text that exists"
            )
        if self.depth in _BODY_DEPTHS and self.body is None:
            raise ValueError(
                f"row {self.id} is planned at {self.depth.value} and this response fetched "
                "no body for it; a depth is a statement about text that exists"
            )
        if self.depth not in _PLANNABLE_DEPTHS:
            raise ValueError(
                f"row {self.id} is planned at depth={self.depth.value}, which the disclosure "
                f"ladder does not produce; it produces {sorted(d.value for d in _PLANNABLE_DEPTHS)}"
            )

    @property
    def floor(self) -> bool:
        return self.band is Band.FLOOR

    def rendered(self) -> tuple[str | None, tuple[Reduction, ...]]:
        """The text this row discloses, and every reduction that produced it.

        The A.9a soft cap is applied here rather than by a caller, so a body longer than
        this depth's published cap cannot reach the wire uncapped and undeclared. Every
        truncation leaves a `body_head_truncated` record with its `kept_tokens` - A7's rule
        that the pipeline annotates and never silently deletes, applied to the disclosure
        half.
        """
        if self.depth is Depth.STUB:
            return None, ()
        if self.depth is Depth.SNIPPET:
            assert self.snippet is not None  # __post_init__ refuses the other case
            return self.snippet, self.base_reductions
        assert self.body is not None  # __post_init__ refuses the other case
        soft_cap = SOFT_CAP_TOKENS[self.depth]
        keep = soft_cap if self.kept_tokens is None else self.kept_tokens
        truncated = head_truncate(self.body, keep)
        if not truncated.truncated:
            return truncated.text, self.base_reductions
        why = (
            f"A.9a {self.depth.value} soft cap"
            if self.kept_tokens is None
            else "A.9a head-truncation step"
        )
        record = Reduction(
            kind=ReductionKind.BODY_HEAD_TRUNCATED,
            removed_chars=truncated.removed_chars,
            kept_tokens=truncated.kept_tokens,
            detail=why,
        )
        return truncated.text, (*self.base_reductions, record)

    def cost(self) -> int:
        """This row's share of the response, in the envelope's own estimate.

        `envelope.measure.row_tokens` is called rather than restated, so the ladder and the
        envelope cannot disagree about what a row costs. A row with no text is a stub row
        and still costs its structure (amendment A11): that is what makes every rung of the
        A.9a ladder monotone in cost as well as in depth.
        """
        text, _ = self.rendered()
        return row_tokens(
            text,
            auth=self.auth_record,
            from_address=self.from_address,
            from_display=self.from_display,
        )

    def chars(self) -> int:
        """The same row, in the unit the host enforces (round 26, R-DISC-033).

        The text is priced by measuring it rather than by a per-token conversion: this row is
        holding the exact string the wire will carry, so there is no reason to estimate it.
        """
        text, reductions = self.rendered()
        return row_chars(
            self.id,
            text,
            declared=declarations_chars(reductions, self.attachments),
            auth=self.auth_record,
            from_address=self.from_address,
            from_display=self.from_display,
        )


#: The depths that carry text out of a fetched body, and the D.4 soft cap of each. A cap
#: is read from this table rather than written at a branch, so a depth added to the
#: disclosure vocabulary either appears here or fails at construction rather than
#: silently reaching the wire uncapped.
SOFT_CAP_TOKENS: Final[Mapping[Depth, int]] = {
    Depth.BODY_CLEAN: BODY_CLEAN_SOFT_CAP_TOKENS,
    Depth.BODY_FULL: BODY_FULL_SOFT_CAP_TOKENS,
}

_BODY_DEPTHS: Final[frozenset[Depth]] = frozenset(SOFT_CAP_TOKENS)

#: What the ladder can produce. `body_full` joined it in round 24, because D.1 makes it a
#: requestable view on `mailweave_get_messages` and D.4 gives it a published soft cap: the
#: escape hatch has to travel through the same measure-and-degrade path as everything else,
#: or `get_messages(view="body_full")` would be a second route to the wire with its own
#: ceiling arithmetic - which is the one thing DISC-06 forbids. `raw` is **not** here and
#: never will be: it is not independently requestable (D.1, ADV-208) and is never inline.
_PLANNABLE_DEPTHS: Final[frozenset[Depth]] = frozenset(
    {Depth.STUB, Depth.SNIPPET, *SOFT_CAP_TOKENS}
)


@dataclass(frozen=True)
class PlannedRun:
    """A contiguous run of positions the ladder collapsed (A3, contract R-06)."""

    start: int
    end: int
    member_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"collapsed run {self.start}-{self.end} is reversed")
        if self.end - self.start + 1 != len(self.member_ids):
            raise ValueError(
                f"collapsed run {self.start}-{self.end} spans "
                f"{self.end - self.start + 1} positions and lists "
                f"{len(self.member_ids)} members"
            )


@dataclass(frozen=True)
class PlannedSource:
    """One thread as the ladder sees it, and its rank for A.9a step 7."""

    thread_id: str
    #: Lower is better. Hit-bearing threads rank above sibling threads by construction,
    #: because step 7 splits from the bottom and a thread the query matched is the last
    #: thing a size ceiling should cost the caller.
    rank: int
    hit_bearing: bool
    rows: tuple[PlannedRow, ...] = ()
    runs: tuple[PlannedRun, ...] = ()
    #: Where this thread stood in the order `max_hit_threads` cuts, or `None` outside that
    #: cut (2026-09-15, R-M2-095). `rank` is the ranking's order over the mapped threads;
    #: this is the producer's order *before* the ranking, the one a narrower width is a
    #: prefix of. Read only by the refusal's hypothetical at a narrower width.
    mapped_at: int | None = None
    #: This thread's **whole** address-keyed participant index, as the observation built it
    #: (round 26, R-DISC-032). Carried rather than counted, because what the envelope emits is
    #: the index narrowed to the messages this source still discloses, and the ladder has to
    #: charge the same narrowing it will produce - `participants_within` is that one rule, and
    #: both this cost and `Source.participants` are computed with it. Charging nothing for it,
    #: which is what round 25 did, made the ceiling blind to 82 % of the rendered response.
    participants: tuple[ThreadParticipant, ...] = ()

    @property
    def present_ids(self) -> frozenset[str]:
        """Every id this source carries at any depth, collapsed-run members included."""
        return frozenset(row.id for row in self.rows) | frozenset(
            member for run in self.runs for member in run.member_ids
        )

    @property
    def emitted_participants(self) -> tuple[ThreadParticipant, ...]:
        """The participant records this source will actually carry, by the one shared rule.

        Narrowed to the ids this source carries **as rows**, not to `present_ids`: a message
        inside a declared collapsed run is present and reachable and it is not a row, and the
        structural summary beside the index counts rows for exactly that reason
        (`assemble.structure_block`). Keeping the whole index while the rows it describes were
        collapsed would also put a block the A.9a ladder cannot shrink in front of the ladder -
        an unbounded per-thread cost with no rung that reaches it, which is how a 60-message
        mailing-list thread became unanswerable rather than merely collapsed.
        """
        return participants_within(self.participants, frozenset(row.id for row in self.rows))

    def cost(self) -> int:
        return (
            SOURCE_STRUCTURAL_TOKENS
            + sum(row.cost() for row in self.rows)
            + sum(collapsed_run_tokens(len(run.member_ids)) for run in self.runs)
            + participants_tokens(self.emitted_participants)
        )

    def chars(self) -> int:
        """The same source, in the host's unit."""
        return (
            source_chars(self.thread_id)
            + sum(row.chars() for row in self.rows)
            + sum(collapsed_run_chars(run.member_ids, self.thread_id) for run in self.runs)
            + participants_chars(self.emitted_participants)
        )

    def with_rows(self, rows: Iterable[PlannedRow]) -> PlannedSource:
        return replace(self, rows=tuple(rows))


@dataclass(frozen=True)
class Layout:
    """A whole response as the ladder sees it, plus the floor it may never break.

    `floor_ids` is carried on the layout rather than recomputed per step, and that is the
    design: the set is decided once, from the reply tree, before any degradation runs, so a
    step cannot shrink the floor and then satisfy the invariant against its own smaller
    version of it.
    """

    sources: tuple[PlannedSource, ...]
    #: Every id the retrieval ledger observed - `H` plus the thread members that came with
    #: it. Carried so the ladder can file a withheld record for each id a step removes.
    accounted_ids: frozenset[str]
    floor_ids: frozenset[str]
    #: **Every** `(evidence message, floor member)` obligation A.9(2) creates, from the reply
    #: tree, before any degradation. `floor_ids` is the flattening of this and cannot say
    #: *whose* floor a member is; the ladder's gate needs that, because the one lawful way a
    #: floor member may leave the payload is together with every evidence message it is owed
    #: to (round 25). A tuple rather than a mapping so a `Layout` stays hashable.
    floor_pairs: tuple[tuple[str, str], ...] = ()
    hit_ids: frozenset[str] = frozenset()
    #: Threads A.9a step 7 split off whole, in the order it split them.
    split_off: tuple[str, ...] = ()
    #: Ids A.9a steps 7 and 8 converted into `withheld` records.
    withheld_ids: tuple[str, ...] = ()
    ceiling_applied: int = 0
    #: How many `not_included_sources[]` entries the response already carried before the A.9a
    #: ladder ran - threads whose map disagreed with itself, which never enter the layout at
    #: all. The ladder's own step 7 adds `split_off` to them, and the two together are what the
    #: envelope will emit, so this is what makes the ladder's charge for that block equal to
    #: the envelope's rather than merely close to it (round 26, R-DISC-032).
    not_included_before: int = 0
    #: The longest thread id any **accounted** message belongs to, in characters.
    #:
    #: **Round 27, R-MCP-024.** A `withheld` record renders the thread its message is in, so
    #: the estimate has to charge for that id - and the layout cannot read it off itself: a
    #: thread capped away by `max_hit_threads` never becomes a source and is never split off,
    #: and its messages are withheld records all the same. The producers read it off
    #: `DispositionLedger.origins`, which is the same place `envelope.withheld` reads each
    #: record's thread from, so the charge and the record cannot disagree about the id.
    #:
    #: Zero for a layout built without it, which then falls back to the widest id it can see
    #: - correct whenever every accounted thread is one the layout holds, and the reason this
    #: is a width rather than a required mapping is that the ladder needs a bound, not the id.
    accounted_thread_id_chars: int = 0
    #: Ids this response will account for at **thread** granularity rather than one record
    #: each (round 29, R-MCP-033) - because the only call that recovers them names a thread,
    #: not a message. Seeded before the ladder runs with the threads `max_hit_threads` capped
    #: away and the threads whose map disagreed with itself, and extended by step 7 for every
    #: source it splits off whole.
    #:
    #: The layout charges these as `groups` group records instead of one withheld
    #: record each, which is the whole of the size change: forty-five ids from three unmapped
    #: threads cost 23,220 characters as records and 2,112 as groups. It is not a discount -
    #: `certify` still accounts for every id, and refuses unless the named records plus the
    #: group counts equal the set difference exactly.
    grouped_ids: frozenset[str] = frozenset()
    #: The `withheld_groups[]` those ids will make, one key per (thread, cap) - the same keys
    #: the ledger will group its notes by (R-M2-094, 2026-09-15). The layout used to carry
    #: two *counts* the producer seeded beside the ledger's notes, and the two arithmetics
    #: disagreed the first time a thread was under two caps. Now the producer states the
    #: keys it will file, step 7 adds `(thread, disclosed_token_ceiling)` for every source it
    #: splits, and `envelope.grouping.arrange_groups` decides on both sides how many are
    #: named and how many fold.
    groups: frozenset[GroupKey] = frozenset()
    #: The caps the producer filed a tail recovery for - the only caps whose groups can fold
    #: past the naming bound. The ledger folds by the same set (`note_tail_recovery`).
    foldable_caps: frozenset[WithheldCap] = frozenset()
    #: The rank the ledger will write the groups by, `(thread, rank)` pairs (2026-09-15,
    #: R-M2-096): the same `rank_of` the producer hands `note_rank`, carried here so the
    #: arrangement the estimate counts is the one the wire writes - which order decides, with
    #: more than one foldable cap, how many caps fold. Empty when nothing is ranked.
    ranks: tuple[tuple[str, int], ...] = ()
    #: The query's JSON-escaped length in characters, for the tail's widening call, which
    #: carries it twice (round 29), and for every record in `query_bearing_ids`, which carries
    #: it once. Zero for an expansion, which has no query and folds no tail.
    query_chars: int = 0
    #: The accounted ids whose `withheld` record carries the caller's query - the messages in
    #: every thread a budget or clock cap stopped the server mapping, whose affordance is the
    #: caller's own search at a raised cap (R-V01-013(a)). Seeded by the producer, never a
    #: source, so never touched by the ladder; charged `query_chars` each on top of the record.
    query_bearing_ids: frozenset[str] = frozenset()
    #: The rendered size of the response's account of its own request - `asked_for` and
    #: `retrieval_report.scan_scope` - measured by the producer before the ladder runs
    #: (R-V01-004). Both echo the query several times over, so a flat structural charge
    #: under-estimates by roughly eight times the query's length.
    request_echo_chars: int = 0
    #: Whether this layout answers an expansion - a thread map or a read of named messages -
    #: rather than a query (R-V01-006). A query's evidence is its hits; an expansion's evidence
    #: is what it was asked for, and for a thread map that is the map itself. The ladder's
    #: emptiness gate reads this to know what "carries nothing" means for this response.
    #: Set by `surface.expansion`; a query layout leaves it false.
    evidence_is_the_map: bool = False
    #: For a thread map: whether its thread has segments (AD §E.2), so a decline can offer
    #: `segment: 0` only where that is a smaller ask. `None` for a query layout.
    segmented: bool | None = None
    #: Whether the response this layout is for may carry a recommended expansion (round 28).
    #: Only a search does: `assemble` emits one for matched rows below the requested depth,
    #: and an expansion response never does, so charging it there would be an estimate of
    #: something the wire cannot carry. Set by `plan.disclose`, left false by `expansion`.
    recommends_expansion: bool = False
    #: Whether `ceiling_applied` was lowered below the ceiling this response was *asked* to
    #: fit because the **host's character cap** was the binding constraint (round 26,
    #: R-DISC-033). Carried so the `ceiling.why` a reader sees names the cap that actually
    #: bound rather than the caller's own argument, which for this reduction did not.
    host_capped: bool = False
    #: The last evidence-bearing source of a search, **as it left** at A.9a step 7's last
    #: resort (2026-09-15, R-M2-095): collapsed to its runs first, and split off only because
    #: even that did not fit. It is no longer in `sources` and costs nothing here; it is
    #: carried so the refusal that follows can say what the top thread's smallest inventory
    #: would have cost beside the bookkeeping, instead of an emptiness flag alone. `None`
    #: while no such split has happened.
    last_evidence_source: PlannedSource | None = None

    @property
    def named_withheld_ids(self) -> frozenset[str]:
        """Withheld ids this response will name one by one (round 29).

        The whole withheld set is still `accounted_ids - present_ids`; this is the half of it
        the wire writes out message by message, which is what the per-record charge is for.
        The other half is charged as `groups` group records. Subtracting rather than
        intersecting means an id that is somehow both grouped and present cannot be charged
        twice, and an id in neither set is still charged - the estimate never gets cheaper by
        losing track of something.
        """
        return (self.accounted_ids - self.present_ids) - self.grouped_ids

    @property
    def present_ids(self) -> frozenset[str]:
        ids: frozenset[str] = frozenset()
        for source in self.sources:
            ids |= source.present_ids
        return ids

    def cost(self) -> int:
        return layout_tokens(self)

    def chars(self) -> int:
        return layout_chars(self)

    def source(self, thread_id: str) -> PlannedSource:
        for source in self.sources:
            if source.thread_id == thread_id:
                return source
        raise KeyError(thread_id)

    def with_sources(self, sources: Sequence[PlannedSource]) -> Layout:
        return replace(self, sources=tuple(sources))


@dataclass(frozen=True)
class CostTerms:
    """One layout's estimate, in one unit, by the term the wire renders it as.

    **One arithmetic, read two ways** (2026-09-15, R-M2-095). `layout_chars` and
    `layout_tokens` are the totals of these terms and nothing else, so a refusal that reports
    its terms reports the very numbers the ladder fitted against - not a second breakdown that
    could drift from the sum. `unit` names which ceiling the terms are priced in.
    """

    unit: str
    structural: int
    echo: int
    expansion: int
    sources: int
    records: int
    groups: int
    tails: int
    not_included: int

    @property
    def total(self) -> int:
        return (
            self.structural
            + self.echo
            + self.expansion
            + self.sources
            + self.records
            + self.groups
            + self.tails
            + self.not_included
        )

    @property
    def bookkeeping(self) -> int:
        """Everything that is not mail: what the response costs before it carries a row."""
        return self.total - self.sources

    def as_json(self) -> dict[str, int | str]:
        return {
            "unit": self.unit,
            "structural": self.structural,
            "echo": self.echo,
            "expansion": self.expansion,
            "sources": self.sources,
            "records": self.records,
            "groups": self.groups,
            "tails": self.tails,
            "not_included": self.not_included,
            "total": self.total,
        }


def token_terms(layout: Layout) -> CostTerms:
    """The size estimate the ladder shrinks - the same number `measure_tokens` will report.

    The response-level constant is added here as well as there because it is part of what
    the client receives: a ladder that ignored it would fit a payload the envelope refuses
    by exactly that margin.

    **A withheld record is charged, and it is charged off the same quantity the envelope
    charges it off**: every accounted id this layout no longer carries becomes a `withheld`
    record with an affordance, which is `accounted_ids - present_ids` here and
    `envelope.withheld` there. Leaving it out let A.9a steps 7 and 8 look free, so a ladder
    that could not fit four hundred rows "fitted" four hundred pointers to them and rendered
    more wire than it started with.
    """
    return CostTerms(
        unit="tokens",
        structural=RESPONSE_STRUCTURAL_TOKENS,
        echo=0,
        expansion=0,
        sources=sum(source.cost() for source in layout.sources),
        records=WITHHELD_RECORD_TOKENS * len(layout.named_withheld_ids),
        groups=WITHHELD_GROUP_TOKENS * named_groups(layout),
        tails=WITHHELD_TAIL_TOKENS * tail_entries(layout),
        not_included=NOT_INCLUDED_SOURCE_TOKENS
        * (layout.not_included_before + len(layout.split_off)),
    )


def layout_tokens(layout: Layout) -> int:
    """The token estimate: `token_terms` summed."""
    return token_terms(layout).total


def chars_terms(layout: Layout) -> CostTerms:
    """The same inventory, priced in the unit an MCP host enforces (round 26, R-DISC-033).

    **Why the ladder needs a second unit rather than a conversion.** A response of many short
    rows and a response of few long ones sit at opposite ends of any characters-per-token
    ratio, so no ratio is a bound. The two ceilings are therefore both real, both enforced by
    `run_ladder`, and both computed off this one inventory - so a step that shrinks the
    response shrinks it in both.

    This is the **estimate**; `envelope.measure.rendered_chars` is the rendered form itself,
    and `surface.partition.declared_result` measures that before handing anything over. The
    property between them is one-directional - this number must be at or above the rendered one,
    because an estimate that under-charges is exactly how a response reaches a host over its
    cap - and it is held by consequence rather than by comparison:
    `test_the_character_estimate_bounds_the_rendered_result` drives a shape matrix through the
    shipped surface and fails if any served response comes back over the cap. Round 26's report
    carries the shape-by-shape inequality the constants were derived from.
    """
    widest = widest_thread_id(layout)
    return CostTerms(
        unit="chars",
        structural=RESPONSE_STRUCTURAL_CHARS,
        echo=layout.request_echo_chars,
        expansion=(
            recommended_expansion_chars(
                sorted(layout.hit_ids & layout.present_ids), limit=RECOMMENDED_EXPANSION_LIMIT
            )
            if layout.recommends_expansion
            else 0
        ),
        sources=sum(source.chars() for source in layout.sources),
        records=sum(
            withheld_chars(
                message_id,
                widest,
                layout.query_chars if message_id in layout.query_bearing_ids else 0,
            )
            for message_id in layout.named_withheld_ids
        ),
        groups=withheld_group_chars(widest) * named_groups(layout),
        tails=withheld_tail_chars(layout.query_chars) * tail_entries(layout),
        not_included=(
            not_included_chars(widest) * (layout.not_included_before + len(layout.split_off))
            # **Round 29.** One block per reason, charged separately from its entries. Every
            # source A.9a step 7 splits shares one sentence, so they share one block; the
            # entries a response already carried before the ladder ran each came from their
            # own thread's own failure, so each is charged a block of its own. That is the
            # conservative reading, and the estimate may only err high.
            + not_included_block_chars()
            * (layout.not_included_before + (1 if layout.split_off else 0))
        ),
    )


def layout_chars(layout: Layout) -> int:
    """The character estimate: `chars_terms` summed."""
    return chars_terms(layout).total


def named_groups(layout: Layout) -> int:
    """How many groups the wire will name one by one (round 29, R-V01-007).

    **The ledger's own arrangement, not a second arithmetic** (R-M2-094): the same
    `arrange_groups` the ledger writes its groups with, over the same keys, so the charge is
    the count the wire will carry whatever mix of caps the keys hold.
    """
    return len(
        arrange_groups(
            layout.groups, foldable=layout.foldable_caps, rank_of=dict(layout.ranks)
        ).named
    )


def tail_entries(layout: Layout) -> int:
    """How many `withheld_tail[]` entries the wire will carry: one per cap that folds."""
    return arrange_groups(
        layout.groups, foldable=layout.foldable_caps, rank_of=dict(layout.ranks)
    ).tail_count


def grouped_threads(layout: Layout) -> int:
    """How many groups the layout holds in all, named or folded."""
    return len(layout.groups)


def a_ceiling_bound(layout: Layout, *, reduced: bool) -> bool:
    """Whether a ceiling actually reduced this response, so `omission.bound` has a referent.

    **Round 30, from the live v0.1 acceptance run.** `omission.bound` was stated
    unconditionally by both producers, so a response the ladder never reduced still asserted
    "the response reached its declared token ceiling". The acceptance record is the proof of
    the shape: 8,748 characters against a 25,000-character cap, `budget_caps_hit` carrying no
    `disclosed_token_ceiling` - by the response's own accounting no ladder step ran - and
    `omission.bound` naming the token ceiling anyway, over 45 messages withheld by
    `max_hit_threads` and `max_server_ms`. A reader told the wrong cap reaches for the wrong
    argument, which is exactly the defect `_binding_ceiling` exists to prevent one layer up.

    Four ways a ceiling can bind, and this asks all four: the host cap forced the arrangement,
    step 7 split a source off, the ceiling withheld an id, or - `reduced`, the ladder ran any
    step at all. A response whose omissions are all cap-driven answers no to each, and its
    `bound` is absent, which the wire allows (`OmissionSummary.bound` is optional) and which is
    honest, because nothing such a response carries refers to it.

    **`reduced` is the fourth term and it was missing** (R-V30-005). A response the ladder
    degraded by depth alone - `body_clean` demoted to snippet or stub under a lowered
    `max_disclosed_tokens`, sometimes with a declared collapsed run - splits nothing off and
    withholds nothing, so the first three terms are all false while `truncated_by` reads
    `mailweave` and `budget_caps_hit` carries `disclosed_token_ceiling`. The ceiling plainly
    bound, and `bound` said nothing. Worse, it was asymmetric: the same depth-only reduction
    forced by the *host* cap stated its sentence, and forced by the *token ceiling* did not.
    """
    return bool(reduced or layout.host_capped or layout.split_off or layout.withheld_ids)


def widest_thread_id(layout: Layout) -> int:
    """The longest thread id this layout still knows of, in characters.

    A `withheld` record renders the thread its message belongs to, and the layout cannot always
    see that thread: A.9a step 7 removes sources (recorded in `split_off`), and a thread capped
    away by `max_hit_threads` before the ladder ran never became a source at all. So the
    producers pass `accounted_thread_id_chars`, read off the ledger the records themselves are
    built from, and this takes the widest of that and everything the layout still holds.

    Zero only for a layout with no threads and no accounted width, which is also a layout that
    can hold no withheld record.
    """
    return max(
        layout.accounted_thread_id_chars,
        *(len(source.thread_id) for source in layout.sources),
        *(len(thread_id) for thread_id in layout.split_off),
        0,
    )
