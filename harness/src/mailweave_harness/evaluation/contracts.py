"""The scoring contract: one explicit decision table per clause.

**Why a table and not a rule.** The previous repair answered the runner review by applying one
generic precondition - "the factor must have executed" - to every clause it touched. The
independent recheck showed what that costs: the product's own gate forbids the cross-encoder on
exact-lookup queries, so requiring it to have run on F1 made H2 permanently unevaluable (N-1),
and an instrument that counted the selector being *consulted* let a selector that admitted
nothing count as having acted (N-2). A uniform rule cannot express "this feature is supposed
not to run here" and "this feature ran but chose nothing", and both are things the clauses have
to say.

So each clause declares its own table. Four columns, and they are separate questions:

  * **coverage** - how many cases of which families, on which arms, a verdict needs.
  * **validity** - which instruments must be present and agreeing for the observations to
    count. Missing instrumentation invalidates the comparison; it never filters quietly down
    to the cases that happen to be instrumented.
  * **execution** - what the clause expects of the factor: that it ran on the candidate arm,
    that it is *prohibited* and correctly did not, or that the question does not arise.
  * **verdicts** - the conditions for HOLDS, FALSIFIED and NOT_EVALUABLE, written out.

**The registered hypotheses and falsifiers are unchanged.** Every `quoted` string below is
copied from `docs/ORIVRA_V1_PLAN.md:877-879` and this module may not paraphrase one. What is
written here is how the runner decides them, which was previously distributed across five
hundred lines of `hypotheses.py` and nowhere stated.

**Absolute invariants are not symmetric** (N-3). A verified violation falsifies on the case it
was seen on: one embedding call on one F1 case is the event H1 says does not happen. A HOLDS is
a statement about the registered corpus and needs the registered coverage, all of it validly
observed. The two branches therefore carry different coverage rules, which is the thing a
single `floor` field could not say.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum


class Kind(StrEnum):
    """What shape of claim the clause is."""

    #: A forbidden event. Any verified occurrence falsifies; a pass is a statement about the
    #: whole registered corpus.
    INVARIANT = "invariant"
    #: Two arms, one quantity. Needs both sides, the registered n, and a factor that acted.
    COMPARISON = "comparison"


class Execution(StrEnum):
    """What the clause expects of the factor on the candidate arm."""

    #: The factor must be evidenced as having acted, or the pair did not vary what it claims
    #: to vary and no difference is attributable to it.
    REQUIRED = "required"
    #: The product's own policy forbids the factor on this family. **Zero invocations is the
    #: correct state**, and the clause must not treat it as missing evidence (N-1).
    PROHIBITED = "prohibited"
    #: The clause is about something else and does not read execution at all.
    NOT_APPLICABLE = "not_applicable"


class Instrument(StrEnum):
    """Which layer of instrumentation a clause's observations rest on.

    Five layers, kept apart because they license different conclusions (N-2):
    availability, eligibility, invocation, admission, delivery. A clause names the ones it
    needs; naming `ADMITTED` does not pull in `DELIVERED`, and that is the point - rows the
    disclosure ladder compressed away were still selected, and a comparison about them must
    still be able to reveal a failure.
    """

    #: (1) the arm's semantic backend loaded.
    BACKEND = "backend_available"
    #: (3) the semantic seam counted calls on this run.
    SEMANTIC_SEAM = "semantic_seam"
    #: (4) the disclosure selector's admitted-row count was recorded.
    SELECTION_ADMITTED = "selection_admitted"
    #: the candidate pool needed for `cut_loss`.
    POOL = "pool"
    #: the row order the response delivered, needed to compare orderings.
    ORDER = "order"


@dataclass(frozen=True)
class Coverage:
    """How much of the registered corpus a verdict rests on.

    `families` are read from `cases.REGISTERED_N`, so a number cannot be chosen here and
    cannot be lowered once a result is in hand.
    """

    families: tuple[str, ...]
    #: Whether both arms must carry the registered n, or only the candidate. A comparison
    #: needs both sides; an invariant is a statement about the candidate arm's own behaviour.
    both_arms: bool = True


@dataclass(frozen=True)
class ClauseContract:
    """One clause's decision table."""

    name: str
    #: **Verbatim from the registered falsifier.** Not paraphrased here, ever.
    quoted: str
    hypothesis: str
    kind: Kind
    coverage: Coverage
    #: Instruments that must be present, and *on every case the clause scores*. Partial
    #: instrumentation invalidates the comparison rather than narrowing it to the instrumented
    #: subset (N-6).
    validity: tuple[Instrument, ...]
    execution: Execution
    #: Which factor `execution` is about. `None` exactly when `execution` is NOT_APPLICABLE,
    #: because naming a factor a clause has no expectation of is how a generic precondition
    #: gets reattached later: the name sits there looking like something to check.
    factor: str | None = None

    def __post_init__(self) -> None:
        expects = self.execution is not Execution.NOT_APPLICABLE
        if expects != (self.factor is not None):
            raise ValueError(
                f"{self.name}: execution={self.execution.value} and factor={self.factor!r} "
                "disagree about whether this clause expects anything of a factor"
            )
    #: Plain-language statements of the three verdicts, printed in the decision table and
    #: asserted by the contract tests so the prose and the code cannot drift.
    holds_when: str = ""
    falsified_when: str = ""
    not_evaluable_when: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)


#: ---------------------------------------------------------------------------------------
#: H1. `ORIVRA_V1_PLAN.md:877`: "Semantic escalation recovers at least one class of evidence
#: lexical retrieval misses, at zero cost on exact-lookup families." Falsified if "F4/F11
#: recall does not rise over the lexical arm, **or** embedding calls appear on F1/F2 traces".
F4_RECALL = ClauseContract(
    name="F4-recall-rises",
    quoted="F4/F11 recall does not rise over the lexical arm",
    hypothesis="H1",
    kind=Kind.COMPARISON,
    coverage=Coverage(("semantic_paraphrase",)),
    validity=(Instrument.BACKEND, Instrument.SEMANTIC_SEAM),
    execution=Execution.REQUIRED,
    factor="semantic",
    holds_when="candidate recall is strictly above the lexical arm's, over the registered n",
    falsified_when=(
        "candidate recall is not above the lexical arm's, with the registered n on both arms, "
        "every case instrumented, and stage-A embedding evidenced as having run"
    ),
    not_evaluable_when=(
        "fewer than the registered n on either arm, or the candidate arm's backend did not "
        "load, or any scored case is uninstrumented, or embedding never ran"
    ),
    notes=(
        "N-4. This clause had no execution check at all, so an arm whose backend never loaded "
        "produced recall identical to the lexical arm and 'does not rise' falsified H1 - the "
        "original RR-03 scenario with the verdict moved from one clause to another.",
    ),
)

F11_RECALL = ClauseContract(
    name="F11-recall-rises",
    quoted="F4/F11 recall does not rise over the lexical arm",
    hypothesis="H1",
    kind=Kind.COMPARISON,
    coverage=Coverage(("semantic_lexical_trap",)),
    validity=(Instrument.BACKEND, Instrument.SEMANTIC_SEAM),
    execution=Execution.REQUIRED,
    factor="semantic",
    holds_when=F4_RECALL.holds_when,
    falsified_when=F4_RECALL.falsified_when,
    not_evaluable_when=F4_RECALL.not_evaluable_when,
)

NO_EMBEDDING = ClauseContract(
    name="no-embedding-on-F1-F2",
    quoted="embedding calls appear on F1/F2 traces",
    hypothesis="H1",
    kind=Kind.INVARIANT,
    coverage=Coverage(("exact_lookup", "sender_date"), both_arms=False),
    validity=(Instrument.SEMANTIC_SEAM,),
    execution=Execution.NOT_APPLICABLE,
    holds_when=(
        "no call on any case, **and** the registered n of both F1 and F2 ran on the candidate "
        "arm with every case instrumented"
    ),
    falsified_when="any instrumented case counted an embedding or rerank call. No floor",
    not_evaluable_when=(
        "no violation was seen and the registered coverage was not met, or a scored case was "
        "uninstrumented, or the two instruments disagreed"
    ),
    notes=(
        "N-3. The two branches are not symmetric and they carry different coverage rules. One "
        "call is the forbidden event, so it falsifies where it is seen. 'No call appeared' on "
        "one F1 case and zero F2 cases is not evidence of zero cost on exact-lookup families.",
    ),
)

#: ---------------------------------------------------------------------------------------
#: H2. `:878`: "Bounded reranking improves top-of-list precision on ambiguous families without
#: changing exact-match families." Falsified if "F16 `cut_loss` does not fall, **or** F1
#: ordering changes, **or** F12 regresses".
F16_CUT_LOSS = ClauseContract(
    name="F16-cut-loss-falls",
    quoted="F16 `cut_loss` does not fall",
    hypothesis="H2",
    kind=Kind.COMPARISON,
    coverage=Coverage(("ranking_stress",)),
    validity=(Instrument.SEMANTIC_SEAM, Instrument.POOL),
    execution=Execution.REQUIRED,
    factor="rerank",
    holds_when="candidate cut_loss is below the baseline's, over the registered n",
    falsified_when=(
        "candidate cut_loss is not below the baseline's, with the registered n, a measured "
        "pool on both arms and the cross-encoder evidenced as having run on the candidate"
    ),
    not_evaluable_when=(
        "fewer than the registered n, an unmeasured or impossible pool, partial "
        "instrumentation, or the cross-encoder never ran on this family"
    ),
    notes=(
        "F16 is the family reranking is *meant* to act on, so REQUIRED belongs here and "
        "nowhere else in H2.",
    ),
)

F1_ORDERING = ClauseContract(
    name="F1-ordering-unchanged",
    quoted="F1 ordering changes",
    hypothesis="H2",
    kind=Kind.INVARIANT,
    coverage=Coverage(("exact_lookup",)),
    validity=(Instrument.ORDER,),
    execution=Execution.PROHIBITED,
    factor="rerank",
    holds_when=(
        "no F1 case ordered differently between the two arms, over the registered n on both"
    ),
    falsified_when="any F1 case ordered differently between the arms. No floor",
    not_evaluable_when=(
        "no difference was seen and the registered n was not met on both arms, or an arm "
        "delivered no comparable order"
    ),
    notes=(
        "N-1, and the largest defect the recheck found. The previous repair required the "
        "cross-encoder to have run on F1 before this clause could be read. The product's own "
        "gate returns `prohibited_by=EXACT_SIGNAL_MATCH` on an exact-signal hit, so a correct "
        "server records zero rerank calls on every F1 case - and the clause was therefore "
        "NOT_EVALUABLE on every campaign, which made H2 unable to HOLD at all. Worse, an "
        "actual F1 reorder was reported as an isolation note rather than as the falsifier. "
        "Execution here is PROHIBITED: not running is the mechanism that keeps ordering "
        "unchanged, and the clause reads the registered falsifier as written.",
    ),
)

F12_CONTROL = ClauseContract(
    name="F12-does-not-regress",
    quoted="F12 (semantic negative control) regresses",
    hypothesis="H2",
    kind=Kind.COMPARISON,
    coverage=Coverage(("semantic_negative_control",)),
    validity=(),
    execution=Execution.NOT_APPLICABLE,
    holds_when="candidate recall is not below the baseline's, over the registered n on both",
    falsified_when="candidate recall is below the baseline's, with the registered n on both",
    not_evaluable_when="fewer than the registered n on either arm",
    notes=(
        "N-1's second half, which the recheck flagged as plausible and did not demonstrate. "
        "F12 is a **control**: the claim is that reranking does not hurt it. Requiring the "
        "reranker to have run on the control before checking it was not hurt is the same "
        "error as F1's, and the exact-signal gate fires here too. So execution is not read.",
    ),
)

#: ---------------------------------------------------------------------------------------
#: H3. `:879`: "Query-aware disclosure selects the answering message more often than
#: position-based selection, without dropping the reply-chain floor." Falsified if "F3
#: position-flatness does not improve, **or** F17 reversal recall drops".
F3_FLATNESS = ClauseContract(
    name="F3-flatness-improves",
    quoted="F3 position-flatness does not improve",
    hypothesis="H3",
    kind=Kind.COMPARISON,
    coverage=Coverage(("buried_evidence",)),
    validity=(Instrument.SELECTION_ADMITTED,),
    execution=Execution.REQUIRED,
    factor="selection",
    holds_when=(
        "the candidate arm's spread across sweep positions is lower than the baseline's, over "
        "the registered n and at least two positions on both arms"
    ),
    falsified_when=(
        "the spread is not lower, with the registered n, two positions, every case "
        "instrumented and the selector evidenced as having admitted rows"
    ),
    not_evaluable_when=(
        "fewer than the registered n, fewer than two positions, partial instrumentation, or "
        "the selector admitted no rows on the candidate arm"
    ),
)

F17_REVERSAL = ClauseContract(
    name="F17-reversal-holds",
    quoted="F17 reversal recall drops in the query-aware arm",
    hypothesis="H3",
    kind=Kind.COMPARISON,
    coverage=Coverage(("decision_reversal",)),
    validity=(Instrument.SELECTION_ADMITTED,),
    execution=Execution.REQUIRED,
    factor="selection",
    holds_when=(
        "candidate recall is at or above the baseline's - the falsifier is a *drop* - over the "
        "registered n, with the selector evidenced as having admitted rows"
    ),
    falsified_when="candidate recall is below the baseline's, with coverage and execution met",
    not_evaluable_when=(
        "fewer than the registered n, partial instrumentation, or the selector admitted no "
        "rows on the candidate arm"
    ),
    notes=(
        "N-2. The selection instrument used to count the selector being *consulted*, which "
        "`plan_thread` does for every planned thread before the ladder decides anything - so "
        "it was non-zero on every case of every arm, and two wire-identical arms (R-M2-098) "
        "were graded HOLDS as a null effect. Rows admitted is the factor acting. Rows "
        "*delivered* is deliberately not required: a row the ladder compressed away was still "
        "selected, and the comparison must stay able to reveal that failure.",
    ),
)

CONTRACTS: tuple[ClauseContract, ...] = (
    F4_RECALL,
    F11_RECALL,
    NO_EMBEDDING,
    F16_CUT_LOSS,
    F1_ORDERING,
    F12_CONTROL,
    F3_FLATNESS,
    F17_REVERSAL,
)

BY_NAME: dict[str, ClauseContract] = {one.name: one for one in CONTRACTS}


def for_hypothesis(hypothesis: str) -> tuple[ClauseContract, ...]:
    return tuple(one for one in CONTRACTS if one.hypothesis == hypothesis)


def render() -> str:
    """The decision tables as text, for the record and for a reader who is not reading code."""
    lines: list[str] = []
    for hypothesis in ("H1", "H2", "H3"):
        lines.append(f"## {hypothesis}")
        for one in for_hypothesis(hypothesis):
            lines += [
                "",
                f"### {one.name} ({one.kind.value})",
                f"* falsifier, as registered: \"{one.quoted}\"",
                f"* coverage: {', '.join(one.coverage.families)}"
                f"{' on both arms' if one.coverage.both_arms else ' on the candidate arm'}, at "
                "the registered n",
                f"* validity: {', '.join(x.value for x in one.validity) or 'none beyond the run'}",
                f"* execution: {one.execution.value}"
                + (f" ({one.factor})" if one.factor else ""),
                f"* HOLDS when: {one.holds_when}",
                f"* FALSIFIED when: {one.falsified_when}",
                f"* NOT_EVALUABLE when: {one.not_evaluable_when}",
            ]
            lines += [f"* note: {note}" for note in one.notes]
        lines.append("")
    return "\n".join(lines)


__all__ = [
    "BY_NAME",
    "CONTRACTS",
    "ClauseContract",
    "Coverage",
    "Execution",
    "Instrument",
    "Kind",
    "for_hypothesis",
    "render",
]
