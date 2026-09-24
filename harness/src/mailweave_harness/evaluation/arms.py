"""The arms, what each one isolates, and the two things a run measures separately.

## The arms are a 2x2, and the labels say what they isolate rather than what they resemble

An earlier version of this file called the no-backend arm `lexical-v0.1`. That was wrong, and
the correction matters more than the name: **the current server with its semantic backend absent
is not the released v0.1**, and a comparison labelled as though it were would attribute several
things to semantic retrieval that semantic retrieval did not do.

Measured against the `v0.1` tag (`d15158d`), the no-backend arm still carries, and v0.1 did not:

  * **the LR freshness rung** and its watermark - a whole retrieval rung that *adds* messages;
  * **mechanical ranking**, which runs on every query whatever the backend does. `rungs` on a
    no-backend run still names `L6`, verified rather than assumed. Turning the backend off turns
    off stage-A embedding and the stage-B cross-encoder; it does not turn off ranking;
  * **the nine-rung ladder**, against v0.1's five;
  * **R-M2-001's fix**: `addresses_in_header` returned `(display name, address)` and the E4
    fill unpacked it backwards, so the participant component - the highest-weighted query-derived
    signal - could only fire by coincidence in v0.1. The no-backend arm's query-aware fill is
    therefore *better* than v0.1's, and a comparison against v0.1 would credit that fix to
    semantics;
  * **the disclosure estimate as re-measured in rounds 25-31**, including INJ-05's per-row
    identity charge. At the same ceiling, a different amount fits.

So the factorial below isolates **one factor per arm against `full`**, and nothing here claims to
reproduce v0.1. Running the released v0.1 is a separate arm needing a second checkout and its own
environment; `M2_EVALUATION_HANDOFF.md` says what that would cost and what it would add.

## First response and expansion-reached are different measurements

A row can be *surfaced* - named, positioned, with an executable call beside it - without its
content being carried. That is progressive disclosure working. It is also **not** the same as the
caller having read the message, and scoring it as though it were would credit MailWeave for
evidence nobody received. So every case is measured twice: what one call put in the reader's
hands, and what following the response's own affordances reached. `Reach` carries both, plus the
ids that stayed surfaced-only after expansion and the ids no response ever named.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Any, TypeVar

from mailweave.envelope.fence import unfence
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import Depth, Outcome, ToolName
from mailweave.envelope.wire import Affordance
from mailweave.semantic.interface import SemanticBackend, Vector
from mailweave.surface.arguments import parse_get_messages, parse_search, parse_thread_map
from mailweave.surface.service import MailweaveService
from mailweave.trace.schema import PersonalTrace
from mailweave.trace.sink import TraceSink
from mailweave_harness.evaluation.cases import ResolvedCase
from mailweave_harness.evaluation.observe import FetchLog
from mailweave_harness.seed.metrics import Disclosure, Partiality, Terminal

_TERMINALS: Mapping[Outcome, Terminal] = {
    Outcome.ANSWERED: Terminal.ANSWERED,
    Outcome.NOT_FOUND: Terminal.NOT_FOUND,
    Outcome.INCONCLUSIVE: Terminal.INCONCLUSIVE,
}

#: How many **hops** the recovery driver will take for one case: the first response is hop 0,
#: the calls it offers are hop 1, the calls *those* responses offer are hop 2, and so on.
#: Bounded because an unbounded driver measures the harness's patience rather than the
#: product's recoverability, and because `recovery_chain` in the shipped suite is bounded at
#: the same order.
MAX_RECOVERY_ROUNDS = 4

#: The **total** number of follow-up calls the driver will execute for one case, across every
#: hop. This is the bound `test_expansion_is_bounded_and_never_repeats_a_call` has enforced
#: since the driver was written (`MAX_RECOVERY_ROUNDS * 8`); it is named here so the driver
#: holds it directly rather than by accident of how many offers a response happens to make.
#: Not raised (R-M2-078): the repair follows affordances the driver used to ignore, under the
#: budget that was already in force.
MAX_RECOVERY_CALLS = MAX_RECOVERY_ROUNDS * 8


T = TypeVar("T")


def in_retrieval_order(offers: Sequence[tuple[int | None, T]]) -> list[T]:
    """The discovery walk's order: retrieval's rank where the wire states one (R-M2-096).

    **2026-09-15.** Withheld groups used to be written sorted by thread id and split-off
    sources in the order step 7 split them (lowest-ranked first), and the driver walked groups
    before not-included sources, so the position of a thread in the walk was an accident of
    its id and of which block it landed in - the evidence's map was 29th of 31 offers on a
    lexical arm and never reached on the semantic one. The wire now carries `rank` on both
    kinds of entry, the ledger's rank being the retrieval's own order for the threads that
    had one, and the driver walks them **as one sequence in ascending rank**.

    Deterministic for threads without a rank: they follow every ranked one, in the order the
    wire listed them - and the wire's own order for the unranked is the arrangement's, by
    thread id and cap - so the same response walks the same way every time. Nothing here
    reads a wanted id, a corpus position or a case label: the walk is the response's rank and
    nothing else, and the known-target rule (`_recovery_calls`) is applied *before* this and
    separately from it.
    """
    ranked = sorted(
        ((rank, index, offer) for index, (rank, offer) in enumerate(offers) if rank is not None),
        key=lambda entry: (entry[0], entry[1]),
    )
    unranked = [offer for rank, offer in offers if rank is None]
    return [offer for _rank, _index, offer in ranked] + unranked


class Measured(StrEnum):
    """Why a number is, or is not, a number - reported per case and per metric.

    The four are kept apart because they license different conclusions and collapsing any two
    of them is how a report comes to say more than it knows:

      * `MEASURED` - the run completed and the quantity is computable.
      * `FAILED` - **the product failed**: the call declined, or raised, or returned an
        envelope the harness could not read. This counts against the arm.
      * `INCONCLUSIVE` - the run completed and the quantity cannot be decided from it. The
        commonest shape is evidence surfaced but never carried, with expansion not attempted.
        This counts against nobody and must not be read as a pass or a failure.
      * `UNMEASURED` - **the instrument was absent.** No trace sink, so no candidate pool, so
        no `cut_loss`; no position-based arm, so no H3. Nothing about the product is stated.
    """

    MEASURED = "measured"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    UNMEASURED = "unmeasured"


class Factor(StrEnum):
    """The things an arm may vary from `full`."""

    SEMANTIC = "semantic_rungs"
    SELECTION = "disclosure_selection"
    #: D.7's second tier alone, with stage-A embedding left on. Added 2026-09-16 because H2
    #: had no exercised comparison: `SEMANTIC` turns the embedding **and** the cross-encoder
    #: off together, so `full` against `sem-off` could not attribute anything to reranking.
    RERANK = "cross_encoder"


@dataclass(frozen=True)
class ArmSpec:
    """One configuration, and an honest statement of what comparing it to `full` isolates."""

    name: str
    semantic: bool
    fixed_window: bool
    isolates: str
    does_not_isolate: str
    #: D.7's second tier. `False` bypasses the cross-encoder and leaves everything else - the
    #: embedding, the shortlist, candidate generation, the disclosure policy and every
    #: configured budget - exactly as `full` has them.
    cross_encoder: bool = True

    @property
    def factors(self) -> frozenset[Factor]:
        """Which factors differ from `full`. More than one differing means the arm isolates
        none of them, which `isolates` must then say in words."""
        out: set[Factor] = set()
        if not self.semantic:
            out.add(Factor.SEMANTIC)
        if self.fixed_window:
            out.add(Factor.SELECTION)
        if not self.cross_encoder:
            out.add(Factor.RERANK)
        return frozenset(out)


_SHARED = (
    "the LR freshness rung, mechanical ranking (which runs on every query whatever the "
    "backend does), the nine-rung ladder, R-M2-001's participant-component fix, and the "
    "disclosure estimate as re-measured in rounds 25-31. None of those is v0.1's, so no arm "
    "here is the released v0.1"
)

FULL = ArmSpec(
    name="full",
    semantic=True,
    fixed_window=False,
    isolates=(
        "nothing; this is the shipped default and the reference every other arm is read against"
    ),
    does_not_isolate="-",
)

SEM_OFF = ArmSpec(
    name="sem-off",
    semantic=False,
    fixed_window=False,
    isolates=(
        "the semantic rungs: stage-A embedding retrieval (L5) and the stage-B cross-encoder "
        "(L6's second tier). Everything else is held identical to `full`"
    ),
    does_not_isolate=_SHARED,
)

FIXED_WINDOW = ArmSpec(
    name="fixed-window",
    semantic=True,
    fixed_window=True,
    isolates=(
        "the disclosure selector: A.9(3)'s query-aware E4 fill against Baseline F's fixed "
        "+/-2 window (DISC-02, EP §8.8), at the same ceiling and measured by the same estimate"
    ),
    does_not_isolate=_SHARED,
)

#: **H2's matched comparison, and the minimum that makes H2 measurable at all.**
#: `full` against this differs in exactly one thing: whether D.7's second tier runs. Stage-A
#: embedding is on in both, so both build the same pool and the same shortlist from the same
#: candidates; the corpus, the candidate-generation policy, the disclosure policy and every
#: configured budget are `full`'s. The bypass is genuine - no backend is acquired for the
#: rerank and no pair is scored - and the ordering that stands is D.7's registered first tier,
#: `mailweave/mechanical-v1`, not a stand-in built from invented numbers.
NO_RERANK = ArmSpec(
    name="no-rerank",
    semantic=True,
    fixed_window=False,
    cross_encoder=False,
    isolates=(
        "D.7's second tier, the cross-encoder, and nothing else: stage-A embedding runs on "
        "both sides, so this is the only pair in which a difference can be attributed to "
        "reranking (EP H2). `sem-off` cannot do it - that arm removes the embedding too"
    ),
    does_not_isolate=_SHARED,
)

BOTH_OFF = ArmSpec(
    name="sem-off+fixed-window",
    semantic=False,
    fixed_window=True,
    isolates=(
        "**nothing on its own** - two factors differ from `full` at once. It is the closest "
        "configuration to v0.1's *behaviour* and it is still not v0.1's code; it is here to "
        "read the two single-factor arms against, not to attribute anything"
    ),
    does_not_isolate=_SHARED,
)

#: The arms. `full` and the three single-factor arms are what H1-H3 read - H1 against
#: `sem-off`, **H2 against `no-rerank`**, H3 against `fixed-window`; `BOTH_OFF` is the corner,
#: run when the campaign wants the semantic x selection interaction and skipped when it does
#: not. This is deliberately **not** a full factorial: three factors would be eight arms, and
#: the interactions nobody has a hypothesis about are not worth a campaign's cost.
SPECS: tuple[ArmSpec, ...] = (FULL, SEM_OFF, NO_RERANK, FIXED_WINDOW, BOTH_OFF)

#: `(hypothesis, the pair that measures it)`. One factor apart in every case, which
#: `tests/test_h2_rerank_arm.py` holds: a hypothesis whose pair differs in two things is a
#: hypothesis nothing in this harness can attribute.
HYPOTHESIS_PAIRS: Mapping[str, tuple[str, str]] = {
    "H1": (FULL.name, SEM_OFF.name),
    "H2": (FULL.name, NO_RERANK.name),
    "H3": (FULL.name, FIXED_WINDOW.name),
}


class CountingBackend:
    """A pass-through proxy that counts what the seam was asked for.

    Wrapped around the real backend rather than reading the response's `rungs`, because those
    are a self-reported route field: a server that forgot to name L5 would report zero
    embedding calls while making them, and H1's second falsifier - *embedding calls appear on
    F1/F2 traces* - would then be checked against the one field the defect had already broken.
    """

    def __init__(self, inner: SemanticBackend) -> None:
        self._inner = inner
        self.embed_calls = 0
        self.embed_texts = 0
        self.rerank_calls = 0
        self.rerank_pairs = 0

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    @property
    def model_revision(self) -> str:
        return self._inner.model_revision

    def embed(self, texts: Sequence[str]) -> Sequence[Vector]:
        self.embed_calls += 1
        self.embed_texts += len(texts)
        return self._inner.embed(texts)

    def rerank(self, query: str, candidates: Sequence[str]) -> Sequence[float]:
        self.rerank_calls += 1
        self.rerank_pairs += len(candidates)
        return self._inner.rerank(query, candidates)

    def reset(self) -> None:
        self.embed_calls = self.embed_texts = self.rerank_calls = self.rerank_pairs = 0

    def snapshot(self) -> dict[str, int]:
        """The four counts as of now.

        N-5. The counter spans the first response *and* every expansion call `follow` makes,
        while the response's own `semantic_cost` block describes the first response alone.
        Comparing the two was therefore comparing different call sets, and a reranking
        expansion would have read as a disagreement on a correct run. `run_case` takes this
        before `follow` and the cross-check uses only what it returns.
        """
        return {
            "embed_calls": self.embed_calls,
            "embed_texts": self.embed_texts,
            "rerank_calls": self.rerank_calls,
            "rerank_pairs": self.rerank_pairs,
        }


class CountingSelector:
    """A `disclosure.Selector` that counts the times it decided a thread's fill. RR-04.

    The semantic seam had a counting proxy and the selection seam had none, so the runner held
    no evidence at all that H3's factor ever executed - and the review's reading of that gap
    was to infer non-execution from identical wire output. That inference is wrong in both
    directions: two selectors can agree on a thread, and a selector that never ran also agrees
    with everything. The count is the only thing that separates them, so the runner counts.

    Wraps rather than replaces: the decision is the wrapped selector's, unchanged, and the
    product is not touched. `name` is delegated so the experiment log still records the arm's
    own selector name.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.select_calls = 0
        self.rows_admitted = 0

    @property
    def name(self) -> str:
        return str(self._inner.name)

    def select(self, thread: Any, query: Any) -> Mapping[str, Any]:
        self.select_calls += 1
        chosen: Mapping[str, Any] = self._inner.select(thread, query)
        self.rows_admitted += len(chosen)
        return chosen

    def reset(self) -> None:
        self.select_calls = self.rows_admitted = 0

    def snapshot(self) -> tuple[int, int]:
        """`(consultations, rows admitted)` as of now. N-5: the first response's share."""
        return (self.select_calls, self.rows_admitted)


@dataclass
class TraceCursor:
    """Only the records this case wrote, read from where the last case stopped.

    Two reasons it is not `sink.read_all()`. **Correctness first:** a case writes one trace
    per call, and `follow` makes more calls after the first response, so the last record in
    the file is generally an expansion call with no semantic block - reading it would report
    `cut_loss` unmeasured on every case where the ladder did reach L5, which is precisely the
    case H2 is about. The first semantic record written by *this* case is the retrieval that
    produced the response. **Cost second:** re-parsing the whole file per case is quadratic
    in the campaign's length, and the campaign is the thing this is for.
    """

    sink: TraceSink
    offset: int = 0

    def __post_init__(self) -> None:
        """Start at the file's current end, not at 0. RR-13.

        `TraceSink` opens with `O_APPEND` and the CLI's default trace root is a fixed path, so
        a campaign run into a root an earlier campaign used began reading that campaign's
        records: the first case took another run's pool and scored `cut_loss` against it,
        while `pool_source` still said "semantic pool exposed in the trace". Three of five arms
        diverged in the reviewer's probe. Seeking to the end costs nothing on a fresh root and
        is the difference between a measurement and a coincidence on a reused one.
        """
        if self.offset == 0 and self.sink.path.exists():
            self.offset = self.sink.path.stat().st_size

    def take(self) -> tuple[PersonalTrace, ...]:
        path = self.sink.path
        if not path.exists():
            return ()
        with path.open("r", encoding="utf-8") as handle:
            handle.seek(self.offset)
            fresh = handle.read()
            self.offset = handle.tell()
        return tuple(
            PersonalTrace.model_validate_json(line) for line in fresh.splitlines() if line.strip()
        )


@dataclass(frozen=True)
class Arm:
    """One configuration under test, and the instruments attached to it."""

    spec: ArmSpec
    service: MailweaveService
    counter: CountingBackend | None = None
    #: The selection seam's instrument. `None` means the arm's selector was not wrapped, and
    #: every clause about disclosure selection on this arm is then UNMEASURED rather than
    #: graded (RR-04).
    selector: CountingSelector | None = None
    #: Layer (1). `False` when this arm's semantic backend did not load, `None` when the arm
    #: has none by design or nobody checked. A semantic arm whose backend did not load is not
    #: a lexical arm with zero calls, and the clauses need to be able to tell them apart (N-4).
    backend_available: bool | None = None
    trace_sink: TraceSink | None = None
    cursor: TraceCursor | None = None
    #: EP §6.4's pool fallback, observed at the network layer. Required on the lexical
    #: arm: without it that arm can never have a pool, and `cut_loss` - the only thing
    #: EP lets a reranker be justified by - would be unmeasurable on the very arm the
    #: reranker has to beat.
    fetch_log: FetchLog | None = None

    def __post_init__(self) -> None:
        if self.trace_sink is not None and self.cursor is None:
            object.__setattr__(self, "cursor", TraceCursor(self.trace_sink))

    @property
    def name(self) -> str:
        return self.spec.name


@dataclass(frozen=True)
class Reach:
    """Where each required message ended up, in two separately reported stages.

    **A recovery that raised is not a recovery that found nothing** (R-M2-078). `exceptions`
    names every follow-up call that raised, by tool and exception class, and `stopped`
    says why the driver stopped - the evidence was in hand, no response offered a call it had
    not already made, the call budget ran out, or the hop budget did. A reader of an
    `after_expansion` of zero can then tell a product that declined from a product that was
    never asked, which the previous driver reported identically.
    """

    first_response: frozenset[str] = frozenset()
    after_expansion: frozenset[str] = frozenset()
    surfaced_only: frozenset[str] = frozenset()
    never_named: frozenset[str] = frozenset()
    rounds: int = 0
    calls: tuple[str, ...] = ()
    #: EP §6.4's `levels_traversed_to_answer`: distinct disclosure levels crossed before the
    #: evidence was in hand. The first response is level 1; each executed call adds one.
    levels: int = 1
    #: Every follow-up call that raised, as `"<tool>: <ExceptionClass>"`, in execution order.
    exceptions: tuple[str, ...] = ()
    #: Why the driver stopped. One of `evidence_in_hand`, `no_new_affordances`,
    #: `call_budget`, `hop_budget`, or `""` when no expansion was attempted.
    stopped: str = ""
    state: Measured = Measured.MEASURED

    @property
    def expansion_gained(self) -> frozenset[str]:
        """Evidence that expansion put in hand and the first response did not."""
        return self.after_expansion - self.first_response


@dataclass(frozen=True)
class CaseRun:
    """Everything one case produced on one arm. Nothing here is a verdict."""

    case_id: str
    family: str
    arm: str
    terminal: Terminal
    #: **The first response only.** `reach` carries what expansion added.
    disclosure: Disclosure
    partiality: tuple[Partiality, ...] = ()
    reach: Reach = field(default_factory=Reach)
    order: tuple[str, ...] = ()
    #: **`None` means the instrument was absent, and is never 0.** RR-03. These used to be
    #: written `0 if arm.counter is None else arm.counter.embed_calls`, so an arm whose
    #: semantic backend never loaded recorded zero embedding calls and H1's
    #: `no-embedding-on-F1-F2` clause read that zero as a measurement and reported HOLDS. A
    #: clause that reads one of these must check `factor_state` first.
    embed_calls: int | None = 0
    embed_texts: int | None = 0
    rerank_calls: int | None = 0
    rerank_pairs: int | None = 0
    # ---------------------------------------------------------------- the five layers, apart
    #
    # N-2 and N-5. Five different facts about one factor, and collapsing any two of them is
    # how the last repair came to grade a selector that never admitted a row as one that ran.
    # In order: was there a backend to use at all, was the feature eligible on this case, was
    # it invoked, did it choose anything, and did what it chose survive to the reader.
    #
    #: (0) **Configuration.** Whether this arm is *declared* to run the semantic path at all,
    #: taken from its `ArmSpec`. Not a measurement - a fact about how the arm was built. It is
    #: separate from (1) because `backend_available=None` alone cannot tell "a lexical arm has
    #: no backend to be unavailable" from "nobody checked", and the two license opposite
    #: readings: an absent seam instrument on `sem-off` is the arm having no seam, while an
    #: absent one on `full` is a blind spot. `None` means the arm did not declare, and a run
    #: that did not declare is held to the strict reading.
    semantic_arm: bool | None = None
    #: (1) **Availability.** `False` when the arm's semantic backend did not load. `None` when
    #: nobody asked - the arm has no semantic backend by design, or the runner did not check.
    backend_available: bool | None = None
    #: (2) **Eligibility.** `False` when the product's own gate forbade the feature on this
    #: case - `EXACT_SIGNAL_MATCH` on an exact-lookup hit, say. **A prohibited feature that did
    #: not run is the product working**, and a clause about that family must not read the zero
    #: as missing evidence (N-1).
    rerank_eligible: bool | None = None
    #: (3) **Invocation.** Times the arm's disclosure selector was *consulted*. `plan_thread`
    #: calls the selector for every planned thread before the ladder decides anything, so this
    #: is greater than zero on every case of every arm and is **not** evidence the factor
    #: acted (N-2).
    select_calls: int | None = None
    #: (4) **Admission.** Rows the selector actually chose. This is the factor acting.
    rows_admitted: int | None = None
    #: (5) **Delivery.** FILL-band rows that reached the response. Lower than (4) whenever the
    #: ladder compressed or dropped them - which is a *result*, not a missing measurement, so
    #: no clause may require this to be non-zero before letting a comparison reveal failure.
    fill_rows_delivered: int | None = None
    #: What the response itself said the semantic path cost, independent of the seam counter.
    #: RR-03: the brief claims the two are compared; they were not recorded together, so
    #: nothing could compare them afterwards either.
    semantic_cost: Mapping[str, int] | None = None
    #: The seam counts **for the first response alone**, taken before `follow` runs. N-5: the
    #: cumulative counters above span expansion too, and `semantic_cost` describes the first
    #: response, so the cross-check compares these and not those.
    first_response_calls: Mapping[str, int] | None = None
    pool_ids: frozenset[str] | None = None
    #: Which clause of EP §6.4 `pool_ids` came from, so a `cut_loss` can be read back to the
    #: measurement that produced it rather than taken on trust.
    pool_source: str | None = None
    latency_ms: float = 0.0
    declined: str | None = None
    position: int | None = None
    thread_lengths: Mapping[str, int] = field(default_factory=dict)
    #: The string actually issued to the substrate, where an arm derives one from the case's
    #: question rather than passing it through (the primitive floor's `pf-q-1`). Empty for
    #: arms that issue the question as written.
    query_issued: str = ""
    state: Measured = Measured.MEASURED

    @property
    def pool_state(self) -> Measured:
        """`cut_loss` is UNMEASURED without a trace sink, never zero."""
        if self.state is Measured.FAILED:
            return Measured.FAILED
        return Measured.MEASURED if self.pool_ids is not None else Measured.UNMEASURED

    @property
    def selection_state(self) -> Measured:
        """Whether the selection seam was instrumented on this run.

        Kept apart from `counter_state` because they are two instruments on two factors, and
        a clause about disclosure selection may not fall back on evidence about embedding.
        **Instrumented is not the same as effective** - see `selection_acted`.
        """
        if self.state is Measured.FAILED:
            return Measured.FAILED
        return Measured.MEASURED if self.rows_admitted is not None else Measured.UNMEASURED

    @property
    def selection_acted(self) -> bool | None:
        """Did the selector *choose* anything on this case. Layer (4), not layer (3). N-2.

        `select_calls > 0` says the planner consulted the selector, which it does for every
        thread it plans before the ladder decides anything - so it is true on every case of
        every arm and says nothing. Rows admitted is the factor acting.

        Deliberately **not** `fill_rows_delivered > 0`: rows the ladder compressed away were
        still selected, and a comparison whose candidate arm selected rows may reveal a
        failure in what happened to them.
        """
        return None if self.rows_admitted is None else self.rows_admitted > 0

    @property
    def counter_state(self) -> Measured:
        """Whether the semantic seam was instrumented on this run at all. RR-03.

        `UNMEASURED` is the whole point: an absent instrument licenses no statement, and in
        particular does not license "zero embedding calls". A clause whose falsifier is about
        calls appearing or not appearing must return NOT_EVALUABLE on UNMEASURED rather than
        reading the absence as a zero.
        """
        if self.state is Measured.FAILED:
            return Measured.FAILED
        return Measured.MEASURED if self.embed_calls is not None else Measured.UNMEASURED

    def cross_check(self) -> tuple[Measured, str]:
        """Seam counts against the response's own `semantic_cost`, over the same calls. N-5.

        Three outcomes and they are not two. `MEASURED` with an empty note means both
        instruments were present, described the same calls, and agreed. `UNMEASURED` means one
        of them was absent - and that is the common case, because the wire block is `None` on
        every response that did not escalate, which is every F1 and F2 case. The previous
        version returned `None` there and the clause detail then claimed the numbers had been
        "cross-checked against the responses' own semantic_cost", which was not true of any
        case the clause reads. `FAILED` means both were present and disagreed.

        Compared: embedded texts and reranked pairs, both as counts, both **first response
        only**, because that is what the wire block describes.
        """
        if self.first_response_calls is None:
            # The split is missing, so the two instruments cannot be compared call for call.
            # One relation survives anyway and it is worth keeping: the wire block describes a
            # subset of what the seam counted, so a first-response count can never exceed the
            # seam total. `wire > total` is a contradiction no split would explain away, and
            # reporting it `UNMEASURED` would file a verified disagreement as an absent one.
            if self.semantic_cost is not None:
                over = [
                    f"{field}: seam total {total}, wire first-response {wire}"
                    for field, total in (
                        ("embed_texts", self.embed_texts),
                        ("rerank_pairs", self.rerank_pairs),
                    )
                    for wire in (self.semantic_cost.get(field),)
                    if total is not None and wire is not None and wire > total
                ]
                if over:
                    return (
                        Measured.FAILED,
                        "; ".join(over)
                        + " - the first response is part of the run, so its count cannot "
                        "exceed the run's",
                    )
            return (Measured.UNMEASURED, "the semantic seam was not instrumented on this run")
        if self.semantic_cost is None:
            return (
                Measured.UNMEASURED,
                "the response carried no semantic_cost block, which is what a response that "
                "did not escalate looks like. Nothing is cross-checked on this case",
            )
        rows = (
            ("embed_texts", self.first_response_calls.get("embed_texts")),
            ("rerank_pairs", self.first_response_calls.get("rerank_pairs")),
        )
        clashes = [
            f"{field}: seam {seam}, wire {self.semantic_cost.get(field)}"
            for field, seam in rows
            if seam is not None
            and self.semantic_cost.get(field) is not None
            and seam != self.semantic_cost.get(field)
        ]
        if clashes:
            return (Measured.FAILED, "; ".join(clashes))
        return (Measured.MEASURED, "")


def _semantic_cost(envelope: Envelope) -> dict[str, int] | None:
    """The response's own account of what the semantic path cost. RR-03.

    A second instrument for the same quantity the seam counter measures, read off the wire
    rather than off the object graph the harness wrapped. `CaseRun.cross_check` compares them
    over the same calls; recording only one of them is how the brief came to claim a comparison
    that nothing performed.
    """
    cost = envelope.retrieval_report.semantic_cost
    if cost is None:
        return None
    return {
        "embed_texts": cost.embed_texts,
        "rerank_pairs": cost.rerank_pairs,
        "escalated": int(cost.escalated),
    }


def _fill_rows_delivered(envelope: Envelope) -> int:
    """FILL-band rows that reached the reader. Layer (5). N-2.

    Read off the response rather than off the selector, because the two are different facts:
    the selector admits rows and the disclosure ladder decides how many of them survive the
    budget. A row admitted and then compressed away is the ladder working, and the comparison
    it belongs to must still be allowed to run.
    """
    return sum(
        1
        for source in envelope.sources
        for row in source.messages
        if getattr(row, "band", None) is not None and str(row.band) == "fill"
    )


def _rerank_eligible(envelope: Envelope) -> bool | None:
    """Layer (2): whether the product's own gate allowed the cross-encoder on this case. N-1.

    `None` when the response says nothing about it. `False` when a prohibition fired - an
    exact-signal match on an exact-lookup query is the one that matters here, because it is
    the mechanism that keeps F1 ordering unchanged. **A prohibited feature that did not run is
    the product behaving correctly**, and the previous repair read that zero as missing
    evidence and made H2 permanently unevaluable.
    """
    report = envelope.retrieval_report
    cost = report.semantic_cost
    prohibited = getattr(cost, "prohibited_by", None) if cost is not None else None
    if prohibited:
        return False
    for entry in report.not_tried:
        reason = f"{getattr(entry, 'reason', '')}{getattr(entry, 'rung', '')}".lower()
        if "exact" in reason and "match" in reason:
            return False
    return None if cost is None else True


def _content_by_id(envelope: Envelope) -> dict[str, str]:
    """Only text the response carried as message content (EP §6.1).

    A stub or a snippet-only row is **not** a disclosure. Snippets are excluded and counted as
    surfaced instead: a snippet is Gmail's ~200-character preview, a case's quote span is
    generally not in it, and crediting recall for one would score a retrieval that did not put
    the evidence in the reader's hands.
    """
    out: dict[str, str] = {}
    for source in envelope.sources:
        for row in source.messages:
            if row.content is None or row.depth.value in {"stub", "snippet"}:
                continue
            out[row.id] = unfence(envelope.fence_nonce, row.content.text)
    return out


def _surfaced_ids(envelope: Envelope) -> frozenset[str]:
    ids: set[str] = set()
    for source in envelope.sources:
        ids.update(row.id for row in source.messages)
        ids.update(member for run in source.collapsed_runs for member in run.member_ids)
    ids.update(record.id for record in envelope.withheld)
    return frozenset(ids)


def _partiality_of(envelope: Envelope) -> tuple[Partiality, ...]:
    out: list[Partiality] = []
    for source in envelope.sources:
        payload = frozenset(row.id for row in source.messages) | frozenset(
            member for run in source.collapsed_runs for member in run.member_ids
        )
        out.append(
            Partiality(
                claimed_total=source.stated_total,
                included_ids=payload,
                payload_ids=payload,
                more_available_signal=envelope.partial,
                role_tags={row.id: row.role.value for row in source.messages},
                reason_tags={row.id: row.reason.render() for row in source.messages},
            )
        )
    return tuple(out)


def _tokens(text: str) -> int:
    return len(text.split())


def _recovery_calls(
    envelope: Envelope, wanted: frozenset[str], *, named_reads: bool = True
) -> list[Affordance]:
    """Every executable call this response offers that could carry one of `wanted`.

    Read off the response rather than constructed, which is the point: R-07 says a partiality
    statement sits next to an executable call, and a driver that built its own calls would be
    measuring the harness's ingenuity instead of the product's recoverability.

    One stated rule beside that, the same one `boundary.Served.offers` states (navigation
    redesign, 2026-09-14): **a named id is readable by name.** A collapsed run lists its
    members' ids so the inventory is inspectable, and the call that reads a listed id is
    `mailweave_get_messages(message_ids=[id], view="body_clean")` - D.1's contract for a
    message the caller can name. The driver makes it for a wanted id it finds in a run. This
    is a known-target rule and the driver that uses it measures known-target reachability.
    A continuation that names a wanted id, or spans a wanted id's position, is followed too.
    """
    offers: list[Affordance] = []
    positions_wanted: set[int] = set()
    for source in envelope.sources:
        for row in source.messages:
            if row.id in wanted and row.unabridged is not None:
                offers.append(row.unabridged)
                positions_wanted.add(row.position)
        for run in source.collapsed_runs:
            held = wanted & frozenset(run.member_ids)
            if not held:
                continue
            offers.append(run.affordance)
            for one in sorted(held):
                positions_wanted.add(run.positions[0] + run.member_ids.index(one))
                if not named_reads:
                    continue
                offers.append(
                    Affordance(
                        tool=ToolName.GET_MESSAGES,
                        args={"message_ids": [one], "view": Depth.BODY_CLEAN.value},
                    )
                )
    for record in envelope.withheld:
        if record.id in wanted:
            offers.append(record.affordance)
    # `getattr`, because the R-M2-078 tests script responses as bare namespaces from before
    # the field existed; the shipped `Envelope` always carries it.
    for continuation in getattr(envelope, "continuations", ()):
        span = continuation.positions
        spans_wanted = span is not None and any(
            span[0] <= position <= span[1] for position in positions_wanted
        )
        if (frozenset(continuation.message_ids) & wanted) or spans_wanted:
            offers.append(continuation.affordance)
    # **The discovery walk, in retrieval's order** (R-M2-096): groups and not-included
    # sources as one sequence by the rank the wire carries, unranked ones after. `getattr`
    # for the same reason as above: the shipped models carry `rank`, the scripted ones may not.
    offers.extend(
        in_retrieval_order(
            [(getattr(group, "rank", None), group.affordance) for group in envelope.withheld_groups]
            + [
                (getattr(entry, "rank", None), entry.affordance)
                for entry in envelope.not_included_entries
            ]
        )
    )
    offers.extend(envelope.affordances)
    return offers


def _execute(service: MailweaveService, affordance: Affordance) -> Envelope | Exception:
    """Run one offered call through the shipped service, and hand back what happened.

    **The exception comes back, not `None`** (R-M2-078). This used to swallow every raise and
    return `None`, so a `get_messages` that raised on every reply (R-M2-077) was recorded as a
    call that returned nothing, and the case was scored as evidence the product never reached
    rather than as a product that failed when asked. A tool this driver does not know how to
    call is returned as the `ValueError` it is, for the same reason.
    """
    args = dict(affordance.args)
    try:
        if affordance.tool is ToolName.GET_MESSAGES:
            return service.get_messages(parse_get_messages(args))
        if affordance.tool is ToolName.THREAD_MAP:
            return service.thread_map(parse_thread_map(args))
        if affordance.tool is ToolName.SEARCH:
            return service.search(parse_search(args))
    except Exception as failure:
        return failure
    return ValueError(f"the driver cannot execute a {affordance.tool.value} affordance")


def _call_key(affordance: Affordance) -> str:
    """The identity under which a call is never made twice.

    Tool and arguments, canonically serialised. A `thread_map` is keyed by its thread and
    segment, so the same map reached from two responses is one call; a `get_messages` by
    `map_id` is keyed by the handle it was given, which a later map of the same thread mints
    afresh - so two handles to one thread are two calls here, and the total call budget is
    what stops that from running away rather than this key.
    """
    return json.dumps({"t": affordance.tool.value, "a": dict(affordance.args)}, sort_keys=True)


def follow(
    service: MailweaveService,
    envelope: Envelope,
    *,
    required: frozenset[str],
    first_content: Mapping[str, str],
    quotes: Mapping[str, str],
    rounds: int = MAX_RECOVERY_ROUNDS,
    calls: int = MAX_RECOVERY_CALLS,
    named_reads: bool = True,
) -> tuple[Reach, dict[str, str]]:
    """Follow the responses' own affordances until the required evidence is in hand or bounded.

    **No call is invented, no call is repeated, and every response is read** (R-M2-078). The
    driver executes what the responses offered - the first one, and every one a follow-up call
    returned - breadth-first: hop 1 is what the first response offers, hop 2 is what those
    responses offer, and so on to `rounds` hops. It used to read the first response only, so
    a search that named the evidence's thread in `not_included_sources`, whose map then
    surfaced the evidence and offered the call that fetches it, stopped one hop short every
    time and reported the evidence as never reached.

    Two bounds, both stated: `rounds` hops of depth and `calls` executions in total. A call is
    identified by `_call_key` and never made twice, which is also what keeps a map that
    offers the search that offered the map from cycling. What stops the driver is recorded in
    `Reach.stopped`; a follow-up that raised is recorded in `Reach.exceptions` by tool and
    class rather than treated as a response that carried nothing.
    """
    from mailweave_harness.seed.metrics import disclosed

    def carried(content: Mapping[str, str]) -> frozenset[str]:
        """EP §6.1's `disclosed`, called rather than restated.

        Two implementations of one rule is the defect class this repository keeps finding, and
        this is the rule every recall figure rests on.
        """
        snapshot = Disclosure(content_by_id=dict(content))
        return frozenset(mid for mid in required if disclosed(snapshot, mid, quotes.get(mid, "")))

    merged = dict(first_content)
    first = carried(merged)
    surfaced = set(_surfaced_ids(envelope))
    seen_calls: set[str] = set()
    executed: list[str] = []
    exceptions: list[str] = []
    levels = 1
    stopped = ""
    frontier: list[Envelope] = [envelope]
    if not (required - first):
        stopped = "evidence_in_hand"
        frontier = []
    for _hop in range(rounds):
        if not frontier:
            break
        outstanding = required - carried(merged)
        if not outstanding:
            stopped = "evidence_in_hand"
            break
        offers: list[Affordance] = []
        for source in frontier:
            for one in _recovery_calls(source, frozenset(outstanding), named_reads=named_reads):
                key = _call_key(one)
                if key in seen_calls:
                    continue
                seen_calls.add(key)
                offers.append(one)
        if not offers:
            stopped = "no_new_affordances"
            break
        next_frontier: list[Envelope] = []
        for affordance in offers:
            if len(executed) >= calls:
                stopped = "call_budget"
                break
            got = _execute(service, affordance)
            executed.append(affordance.tool.value)
            if isinstance(got, Exception):
                exceptions.append(f"{affordance.tool.value}: {type(got).__name__}")
                continue
            levels += 1
            surfaced |= _surfaced_ids(got)
            merged.update(_content_by_id(got))
            next_frontier.append(got)
            if not (required - carried(merged)):
                stopped = "evidence_in_hand"
                break
        if stopped:
            break
        frontier = next_frontier
    else:
        if not stopped:
            stopped = "hop_budget"
    if not stopped and frontier == []:
        # The last hop returned no response to read: nothing left to follow.
        stopped = "no_new_affordances"
    after = carried(merged)
    still_surfaced = frozenset(required & surfaced) - after
    # **A recovery call that raised and evidence still out of hand is the product failing.**
    # Not INCONCLUSIVE, which is the state for "the response named it and the driver could
    # not get it under its budget", and not MEASURED-with-zero, which is the state for "the
    # product answered and the answer did not carry it".
    if after or not (required - after):
        state = Measured.MEASURED
    elif exceptions:
        state = Measured.FAILED
    elif still_surfaced or stopped in {"call_budget", "hop_budget"}:
        state = Measured.INCONCLUSIVE
    else:
        state = Measured.MEASURED
    return (
        Reach(
            first_response=first,
            after_expansion=after,
            surfaced_only=still_surfaced,
            never_named=frozenset(required) - surfaced,
            rounds=len(executed),
            calls=tuple(executed),
            levels=levels,
            exceptions=tuple(exceptions),
            stopped=stopped,
            state=state,
        ),
        merged,
    )


def build_arm(
    spec: ArmSpec,
    service: MailweaveService,
    *,
    counter: CountingBackend | None = None,
    traces_root: Path | None = None,
    fetch_log: FetchLog | None = None,
    backend_available: bool | None = None,
) -> Arm:
    """Assemble one arm and attach its instruments. **One copy, used by every caller.**

    RR-06. The live campaign and the dry run each built arms their own way, and the
    differences were exactly where the instrument gaps were: the live path created its
    counter lazily inside a registry factory that only ran if the backend loaded, the dry
    run created it eagerly; the live path handed every arm the production watermark, the dry
    run handed none. The docstring said the two differed "in exactly two places". Whatever
    the dry run is cited as evidence of, it has to be evidence about the arms the campaign
    runs, so both callers come through here.

    RR-07: the watermark is **per arm**, written under the traces root. Arms run interleaved,
    so a shared file meant every arm after the first read whatever the previous one left, and
    the file involved was the production state directory `mailweave serve` uses - so a desktop
    session between runs changed the campaign's starting state and the campaign changed the
    server's.
    """
    sink = None if traces_root is None else TraceSink(traces_root / spec.name)
    if sink is not None:
        service.trace_sink = sink
    if traces_root is not None:
        service.watermark_path = traces_root / spec.name / "watermark.json"
        service.watermark_path.parent.mkdir(parents=True, exist_ok=True)
    # **The effective selector, not the injected one.** `MailweaveService.selector = None`
    # means the shipped `QueryAwareFill` (`assemble.py:3331`), so an arm that injects nothing
    # would otherwise carry no instrument at all - and the candidate arm of every H3
    # comparison is exactly that arm. Naming the default here makes the runner's instrument
    # depend on a line of the product rather than on the absence of one, so
    # `tests/test_runner_repair_2026_09_17.py` asserts the two agree.
    from mailweave.disclosure.plan import QueryAwareFill

    wrapped = CountingSelector(
        QueryAwareFill() if service.selector is None else service.selector
    )
    service.selector = wrapped
    # Layer (1), recorded rather than inferred. A semantic arm the caller could not warm is
    # `False`; a lexical arm is `None`, because it has no backend to be unavailable.
    availability = backend_available
    if availability is None and spec.semantic:
        availability = counter is not None
    return Arm(
        spec=spec,
        service=service,
        counter=counter,
        selector=wrapped,
        backend_available=availability,
        trace_sink=sink,
        fetch_log=fetch_log,
    )


def run_case(arm: Arm, resolved: ResolvedCase, *, expand: bool = True) -> CaseRun:
    """Run one case on one arm and take every measurement, without judging any of it."""
    if arm.counter is not None:
        arm.counter.reset()
    if arm.selector is not None:
        arm.selector.reset()
    started = perf_counter()
    first_calls: dict[str, int] | None = None
    first_selection: tuple[int, int] | None = None
    try:
        envelope = arm.service.search(parse_search({"query": resolved.case.query}))
    except Exception as failure:
        # **RR-09. Drain before returning.** A search that raised has still fetched, and the
        # log and the trace cursor are per-arm and cumulative: leaving them full made the
        # failed case's traffic the *next* case's candidate pool, which is the pool EP §6.4
        # scores `cut_loss` against. The measured leak was 96 foreign ids in the next case's
        # pool. Nothing is folded into this case either - a case that failed has no pool.
        if arm.fetch_log is not None:
            arm.fetch_log.take()
        if arm.cursor is not None:
            arm.cursor.take()
        return CaseRun(
            case_id=resolved.case.case_id,
            family=resolved.case.family,
            arm=arm.name,
            terminal=Terminal.OTHER,
            disclosure=Disclosure(content_by_id={}),
            embed_calls=None if arm.counter is None else arm.counter.embed_calls,
            rerank_calls=None if arm.counter is None else arm.counter.rerank_calls,
            latency_ms=(perf_counter() - started) * 1000,
            declined=f"{type(failure).__name__}: {failure}",
            position=None if resolved.case.position is None else resolved.case.position.target_pos,
            thread_lengths=dict(resolved.thread_lengths),
            state=Measured.FAILED,
            reach=Reach(never_named=frozenset(resolved.required), state=Measured.FAILED),
        )
    elapsed = (perf_counter() - started) * 1000
    # N-5: taken here, before `follow`. Everything after this point is expansion work and
    # belongs to a different call set from the one `semantic_cost` describes.
    if arm.counter is not None:
        first_calls = arm.counter.snapshot()
    if arm.selector is not None:
        first_selection = arm.selector.snapshot()

    # **Drained here, before `follow`.** The pool is the first response's candidate set;
    # expansion calls fetch more messages, and folding those in would credit the retrieval
    # with evidence the reader had to go and ask for.
    observed = frozenset() if arm.fetch_log is None else arm.fetch_log.take()
    content = _content_by_id(envelope)
    required = frozenset(resolved.required)
    reach = Reach(never_named=required - _surfaced_ids(envelope))
    if expand and required:
        reach, _merged = follow(
            arm.service,
            envelope,
            required=required,
            first_content=content,
            quotes=resolved.required,
        )
    payload = json.dumps(envelope.model_dump(mode="json"))
    disclosure = Disclosure(
        content_by_id=content,
        surfaced_ids=_surfaced_ids(envelope),
        tokens_returned=_tokens(payload),
        distractor_tokens=sum(
            _tokens(text) for mid, text in content.items() if mid in resolved.distractor_ids
        ),
        evidence_tokens=sum(_tokens(text) for mid, text in content.items() if mid in required),
    )
    if arm.fetch_log is not None:
        # Drop what expansion fetched. Not folded into `observed` above, and not discarded
        # silently either: leaving it in the log would make it the *next* case's pool.
        arm.fetch_log.take()
    # EP §6.4, in its own order: the exposed candidate set where there is one, the network
    # layer otherwise. **An empty `pool_ids` is not an exposed pool** - every search emits a
    # `semantic` block whether or not the semantic rungs ran, and reading the empty one as a
    # pool scores `pool_recall = 0` against a recall of 1 and yields a negative `cut_loss`,
    # which the metric's own model forbids.
    pool_ids: frozenset[str] | None = None
    pool_source: str | None = None
    if arm.cursor is not None:
        for record in arm.cursor.take():
            if record.semantic is not None and record.semantic.pool_ids:
                pool_ids = frozenset(record.semantic.pool_ids)
                pool_source = "semantic pool exposed in the trace (EP §6.4 first clause)"
                break
    if pool_ids is None and observed:
        pool_ids = observed
        pool_source = "ids observed at the network layer (EP §6.4 second clause)"
    terminal = _TERMINALS.get(envelope.retrieval_report.outcome, Terminal.OTHER)
    return CaseRun(
        case_id=resolved.case.case_id,
        family=resolved.case.family,
        arm=arm.name,
        terminal=terminal,
        disclosure=disclosure,
        partiality=_partiality_of(envelope),
        reach=reach,
        order=tuple(row.id for source in envelope.sources for row in source.messages),
        embed_calls=None if arm.counter is None else arm.counter.embed_calls,
        embed_texts=None if arm.counter is None else arm.counter.embed_texts,
        rerank_calls=None if arm.counter is None else arm.counter.rerank_calls,
        rerank_pairs=None if arm.counter is None else arm.counter.rerank_pairs,
        select_calls=None if first_selection is None else first_selection[0],
        rows_admitted=None if first_selection is None else first_selection[1],
        fill_rows_delivered=_fill_rows_delivered(envelope),
        semantic_arm=arm.spec.semantic,
        backend_available=arm.backend_available,
        rerank_eligible=_rerank_eligible(envelope),
        semantic_cost=_semantic_cost(envelope),
        first_response_calls=first_calls,
        pool_ids=pool_ids,
        pool_source=pool_source,
        latency_ms=elapsed,
        position=None if resolved.case.position is None else resolved.case.position.target_pos,
        thread_lengths=dict(resolved.thread_lengths),
        state=Measured.MEASURED,
    )


def run_all(
    arms: Sequence[Arm],
    resolved: Sequence[ResolvedCase],
    *,
    expand: bool = True,
    on_case: Callable[[CaseRun], None] | None = None,
) -> tuple[CaseRun, ...]:
    """Every case on every arm, interleaved per case (EP §4.6's ordering rule).

    Interleaved rather than arm-by-arm: running one arm to completion and then the other puts
    index warmth and time of day inside the comparison.
    """
    out: list[CaseRun] = []
    for one in resolved:
        for arm in arms:
            run = run_case(arm, one, expand=expand)
            out.append(run)
            if on_case is not None:
                on_case(run)
    return tuple(out)


def retitle(run: CaseRun, arm: str) -> CaseRun:
    """A run relabelled onto another arm's name, for a report that merges two sources."""
    return replace(run, arm=arm)


def as_json(run: CaseRun) -> dict[str, Any]:
    return {
        "case_id": run.case_id,
        "family": run.family,
        "arm": run.arm,
        "state": run.state.value,
        "terminal": run.terminal.value,
        "first_response_evidence": sorted(run.reach.first_response),
        "expansion_reached_evidence": sorted(run.reach.after_expansion),
        "expansion_gained": sorted(run.reach.expansion_gained),
        "surfaced_never_carried": sorted(run.reach.surfaced_only),
        "never_named": sorted(run.reach.never_named),
        "levels_traversed": run.reach.levels,
        "recovery_calls": list(run.reach.calls),
        # RR-03. `null` here means the seam was not instrumented on this run and is not the
        # same fact as 0. `counter_state` says which, and `semantic_cost` is the second
        # instrument a later reader needs to cross-check the first.
        "embed_calls": run.embed_calls,
        "embed_texts": run.embed_texts,
        "rerank_calls": run.rerank_calls,
        "rerank_pairs": run.rerank_pairs,
        "counter_state": run.counter_state.value,
        "first_response_calls": None if run.first_response_calls is None
        else dict(run.first_response_calls),
        "semantic_arm": run.semantic_arm,
        "backend_available": run.backend_available,
        "rerank_eligible": run.rerank_eligible,
        "select_calls": run.select_calls,
        "rows_admitted": run.rows_admitted,
        "fill_rows_delivered": run.fill_rows_delivered,
        "selection_state": run.selection_state.value,
        "semantic_cost": None if run.semantic_cost is None else dict(run.semantic_cost),
        "cross_check": {"state": run.cross_check()[0].value, "detail": run.cross_check()[1]},
        "pool_state": run.pool_state.value,
        "pool_source": run.pool_source,
        "tokens_returned": run.disclosure.tokens_returned,
        "evidence_tokens": run.disclosure.evidence_tokens,
        "distractor_tokens": run.disclosure.distractor_tokens,
        "latency_ms": round(run.latency_ms, 1),
        "declined": run.declined,
    }


__all__ = [
    "BOTH_OFF",
    "FIXED_WINDOW",
    "FULL",
    "MAX_RECOVERY_ROUNDS",
    "SEM_OFF",
    "SPECS",
    "Arm",
    "ArmSpec",
    "CaseRun",
    "CountingBackend",
    "CountingSelector",
    "Factor",
    "Measured",
    "Reach",
    "TraceCursor",
    "as_json",
    "build_arm",
    "follow",
    "retitle",
    "run_all",
    "run_case",
]
