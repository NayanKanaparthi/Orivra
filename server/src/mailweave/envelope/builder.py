"""Assembly of a response envelope from a disposition ledger and its sources.

The builder is the only supported path to an `Envelope`, and it computes the two things
a caller must not be trusted to compute:

  * `disclosed` - read off the sources actually being shipped, never accepted as an argument;
  * `scan_scope` / `shortlist` - taken from the ledger, so the response's account of what
    it scanned cannot drift from the definition of `H` it was accumulated under.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence

from mailweave.constants import NORMAL_CEILING_TOKENS
from mailweave.envelope.disposition import DispositionLedger
from mailweave.envelope.fence import fence, mint_nonce
from mailweave.envelope.reasons import RungId
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import BudgetCapName, Outcome, Sufficiency
from mailweave.envelope.wire import (
    Affordance,
    AskedFor,
    BudgetBlock,
    Ceiling,
    Content,
    Continuation,
    Counters,
    EmptyDiagnosis,
    ErrorEntry,
    NotIncludedBlock,
    NotIncludedSource,
    NotTriedEntry,
    OmissionSummary,
    PoolBlock,
    RetrievalReport,
    SemanticCost,
    Source,
)


class EnvelopeBuilder:
    """Collects sources and metadata, then certifies and assembles one response."""

    def __init__(
        self,
        ledger: DispositionLedger,
        *,
        asked_for: AskedFor,
        fence_nonce: str | None = None,
        ceiling: Ceiling | None = None,
    ) -> None:
        self._ledger = ledger
        self._asked_for = asked_for
        self._nonce = fence_nonce or mint_nonce()
        self._ceiling = ceiling or Ceiling(
            normal=NORMAL_CEILING_TOKENS, applied=NORMAL_CEILING_TOKENS
        )
        self._sources: list[Source] = []
        self._not_included: list[tuple[str, NotIncludedSource]] = []
        self._bound: str | None = None
        self._affordances: list[Affordance] = []
        self._continuations: list[Continuation] = []
        self._errors: list[ErrorEntry] = []
        self._budget = BudgetBlock()
        self._truncated = False

    # -- accumulation -----------------------------------------------------------------

    @property
    def fence_nonce(self) -> str:
        return self._nonce

    @property
    def sources(self) -> tuple[Source, ...]:
        """The sources accumulated so far, read-only.

        A tuple rather than the list, so a caller counting rows cannot append one: the
        builder is the only thing that decides what is in a response, which is the same
        reason `_disclosed_ids` is computed here rather than accepted.
        """
        return tuple(self._sources)

    def fence_content(self, text: str, *, trust: object, source: object) -> Content:
        """Build a `Content` block with this response's fence already applied."""
        from mailweave.envelope.vocab import ContentSource, Trust

        assert isinstance(trust, Trust)
        assert isinstance(source, ContentSource)
        return Content(trust=trust, source=source, text=fence(self._nonce, text))

    def add_source(self, source: Source) -> None:
        self._sources.append(source)

    def add_not_included_source(self, entry: NotIncludedSource, *, why: str) -> None:
        """File one source this response does not carry, under the reason it does not.

        The reason arrives beside the entry and is stored beside it; `build` groups entries
        that share one into a single block, so a sentence that applies to sixteen sources is
        written once and the sixteen threads, counts and recovery calls all survive
        (round 29, R-MCP-033).
        """
        self._not_included.append((why, entry))

    def state_the_binding_ceiling(self, sentence: str) -> None:
        """Record, once, which ceiling A.9a reduced this response to fit (round 29)."""
        self._bound = sentence

    def _not_included_blocks(self) -> tuple[NotIncludedBlock, ...]:
        """The entries grouped by their reason, in the order the reasons were first filed.

        Insertion order rather than sorted, because the order entries were filed in is the
        order the ladder reached them, and a reader following the response reads the reason
        that applied first, first.
        """
        by_why: dict[str, list[NotIncludedSource]] = {}
        for why, entry in self._not_included:
            by_why.setdefault(why, []).append(entry)
        return tuple(
            NotIncludedBlock(why=why, sources=tuple(entries)) for why, entries in by_why.items()
        )

    def add_continuation(self, continuation: Continuation) -> None:
        """Access to a remainder this response did not carry. Never the same one twice."""
        if continuation in self._continuations:
            return
        self._continuations.append(continuation)

    def add_affordance(self, affordance: Affordance) -> None:
        """Offer a call, once. A second identical offer is the same offer (R-V01-002).

        Idempotent, because the producers that offer a thread map for a split source do so
        from more than one place - the not-included entry and every withheld message of the
        thread - and a response carried one `affordances[]` entry per message, four hundred
        identical calls for a four-hundred-message source, none of them charged. Refusing a
        duplicate would raise on a legitimate second producer; dropping it is what a reader
        would do.
        """
        if affordance in self._affordances:
            return
        self._affordances.append(affordance)

    def add_error(self, error: ErrorEntry) -> None:
        self._errors.append(error)

    def set_budget(self, budget: BudgetBlock) -> None:
        self._budget = budget

    def set_ceiling(self, ceiling: Ceiling) -> None:
        """Declare the ceiling this response was assembled against (A.9a step 6, D.2).

        Set rather than passed at construction because the applied ceiling is an **output**
        of the A.9a ladder: the normal 9,000-token ceiling is raised to the declared 12,000
        overflow if and only if E2 floor membership cannot be carried within it, and that is
        not known until the ladder has run. `Envelope` then measures the assembled payload
        against whatever is declared here, so declaring a larger one buys nothing except an
        accurate `ceiling{}` block.
        """
        self._ceiling = ceiling

    def mark_self_truncated(self) -> None:
        """DISC-06: MailWeave is the author of its own truncation, and says so.

        This sets the *declaration*. It does not make the response fit, and it no longer
        buys any exemption from the ceiling: `Envelope` measures the assembled payload and
        refuses both an oversized response and a truncation claim with no removal behind
        it (see `response.Envelope._self_truncation_is_verified_against_the_ceiling`).
        Call it after the A.9a ladder has run, not instead of running it.
        """
        self._truncated = True

    # -- assembly ---------------------------------------------------------------------

    def _disclosed_ids(self) -> frozenset[str]:
        ids: set[str] = set()
        for source in self._sources:
            ids |= source.disclosed_ids
        return frozenset(ids)

    def build(
        self,
        *,
        outcome: Outcome,
        rungs: Sequence[RungId],
        sufficiency: Sufficiency,
        counters: Counters,
        pool: PoolBlock | None = None,
        semantic_cost: SemanticCost | None = None,
        not_tried: Iterable[NotTriedEntry] = (),
        empty_diagnosis: EmptyDiagnosis | None = None,
        budget_caps_hit: Iterable[BudgetCapName] = (),
    ) -> Envelope:
        """Certify the disposition, then assemble the envelope.

        `hit_count_per_rung` is not a parameter: it is the number of ids each rung's
        observations admitted into `H`, which the ledger already knows.

        Raises `DispositionInvariantError` if any retrieved ID would leave the payload
        without a withheld record, and `ResponseCeilingExceeded` if the assembled response
        exceeds its own declared ceiling or claims a truncation it did not perform. Both
        are raised by `Envelope`'s own validators, not by this method: assembling through
        the builder is convenient, not the thing that makes the response honest.
        """
        certificate = self._ledger.certify(self._disclosed_ids())

        # R-DISC-011 sweep: `hit_count_per_rung` is a count *of `H`*, and every id in `H`
        # carries the rung whose observation admitted it - so it is read off the ledger
        # here rather than accepted as an argument. `rungs` stays a parameter because a
        # rung that executed and returned nothing is real and leaves no trace in `H`;
        # `Envelope` refuses a `rungs` that omits a rung which did admit ids.
        counted = certificate.hits_per_rung
        report = RetrievalReport(
            outcome=outcome,
            rungs=tuple(rungs),
            hit_count_per_rung=tuple(counted.get(rung, 0) for rung in rungs),
            scan_scope=self._ledger.scan_scope,
            pool=pool,
            shortlist=self._ledger.shortlist,
            semantic_cost=semantic_cost,
            not_tried=tuple(not_tried),
            empty_diagnosis=empty_diagnosis,
            budget_caps_hit=tuple(budget_caps_hit),
            sufficiency=sufficiency,
            counters=counters,
        )

        incomplete = any(not s.complete_as_reported for s in self._sources)
        unfetched = any(e.more_pages for e in report.scan_scope)
        partial = bool(
            certificate.withheld
            # **Round 29.** A response whose only omissions are grouped is still partial.
            # Reading `partial` off the named half alone would have made compaction quietly
            # change I-2's answer, which is the one thing compaction must not touch.
            or certificate.withheld_groups
            or certificate.withheld_tail
            or incomplete
            or self._not_included
            or unfetched
            or self._truncated
            # A `requested` continuation names part of the request this response does
            # not carry (navigation redesign, 2026-09-14): an omission with its call.
            or any(one.scope == "requested" for one in self._continuations)
        )
        # The calls of the groups the ledger *named*, and of each tail, listed once each
        # (round 29). A folded group's call is not listed: its recovery is the tail's.
        for group in certificate.withheld_groups:
            self.add_affordance(group.affordance)
        for tail in certificate.withheld_tail:
            self.add_affordance(tail.affordance)
        by_cap: Counter[str] = Counter()
        for record in certificate.withheld:
            by_cap[record.cap.value] += 1
        for group in certificate.withheld_groups:
            by_cap[group.cap.value] += group.message_count
        for tail in certificate.withheld_tail:
            by_cap[tail.cap.value] += tail.message_count

        envelope = Envelope(
            fence_nonce=self._nonce,
            asked_for=self._asked_for,
            sources=tuple(self._sources),
            not_included_sources=self._not_included_blocks(),
            partial=partial,
            affordances=tuple(self._affordances),
            continuations=tuple(self._continuations),
            retrieval_report=report,
            withheld=certificate.withheld,
            withheld_groups=certificate.withheld_groups,
            withheld_tail=certificate.withheld_tail,
            omission=OmissionSummary(
                withheld_messages=len(certificate.withheld_ids),
                withheld_by_cap=dict(by_cap),
                withheld_threads=len(certificate.withheld_groups)
                + sum(tail.thread_count for tail in certificate.withheld_tail),
                not_included_sources=len(self._not_included),
                bound=self._bound,
            ),
            ceiling=self._ceiling,
            errors=tuple(self._errors),
            budget=self._budget,
            truncated_by="mailweave" if self._truncated else None,
            disposition=certificate,
        )

        return envelope
