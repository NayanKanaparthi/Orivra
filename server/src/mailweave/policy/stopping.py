"""AD D.3's stopping rules, **in their published order**, written once (WS-10).

**Why the order is the module.** D.3's own header says the previous ordering *was* the bug
(ADV-004): rule 1 fired before anything consulted `answer_type_presence`, so the
architecture's only answer to T-RC2 was switched off on precisely the confident-but-wrong
cases it was built for. Round 16 then made the mirror-image mistake in the other direction -
it imported rule 1b's "or the query carries no answer-type cue" escape into rule 2, where
neither D.3 nor A.7's L1 row puts it, and switched L1b off for almost every ordinary query
because `present is None` is what a non-interrogative query produces (R-RETR-007). Two
rounds, two orderings, one document. So the order is data here, `PUBLISHED_ORDER` is
asserted against D.3's text by a test that reads the document, and every rule is a separate
named predicate that can be executed on its own.

**One derivation, not two.** `mailweave.retrieval.ladder` evaluates the subset of D.3 the
lexical rungs can reach - rules 0, 1, 1b and 2 - and it does so by calling the predicates
below rather than by restating them. The rules the lexical rungs cannot reach (3, 4, 5, 6)
are evaluated by the policy layer over the whole run. Both readers share these functions,
so the conjunct that cost round 16 a round cannot come apart between them.

Nothing in this module reads a clock, a meter or a mailbox. A stop rule is a predicate over
signals that have already been computed, which is what makes it testable at every rung
without a network.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from mailweave.constants import L1_STOP_MAX_HITS
from mailweave.envelope.vocab import Sufficiency
from mailweave.retrieval.signals import AnswerTypePresence, ExactBranch, ExactSignal


class StopRule(StrEnum):
    """D.3's rules, by the label the trace and `LadderStop.rule` already carry.

    Rules 0 and 4 are in this enum although neither is a *stop*: rule 0 is an ordering
    obligation and rule 4 is an escalation. They are here because D.3 numbers them in one
    sequence and the sequence is the thing that has twice been got wrong; an enum that held
    only the stops would let the two non-stops drift out of the order without anything
    noticing.
    """

    #: Not a stop. `answer_type_presence` is computed on L0's hits **before any stop rule is
    #: tested**, and recorded whether or not it changes the outcome.
    RULE_0 = "D.3-0"
    #: `exact_signal_match` on branch E-a - `rfc822msgid:` with `hit_count == 1`. STOP after
    #: L0 unconditionally. Identity resolution: there is nothing to escalate *to*.
    RULE_1 = "D.3-1"
    #: Branch E-b or E-c. STOP after L0 **only if** `answer_type_presence` is true or the
    #: query carries no answer-type cue. A phrase or an identifier can match a
    #: confident-looking wrong message; a message id cannot.
    RULE_1B = "D.3-1b"
    #: `hit_count in [1,5]` and full term coverage and no drop depth and
    #: `answer_type_presence`. STOP after L1.
    RULE_2 = "D.3-2"
    #: Any rung returning `sufficiency == sufficient`. STOP.
    RULE_3 = "D.3-3"
    #: Not a stop. Zero hits after L3, or weak coverage with paraphrase risk, or a
    #: `non_lexical` tier-1 confidence, or `answer_type_presence == false`: escalate to
    #: L4/L5.
    RULE_4 = "D.3-4"
    #: Any cap exhausted: stop, emit, name the cap plus untried rungs with affordances, and
    #: emit a `withheld` record for every hit the cap prevented from being disclosed. The
    #: outcome is **`inconclusive`**, never `not_found`.
    RULE_5 = "D.3-5"
    #: Never a bare empty result. An empty result always carries `outcome`, and the outcome
    #: is `not_found` only on D.2's exhaustion case - otherwise `inconclusive`.
    RULE_6 = "D.3-6"


#: D.3's published sequence. Iterated in this order by `first_rule_that_fires`, and asserted
#: against the architecture document itself by
#: `test_the_published_order_is_the_order_the_document_prints`.
PUBLISHED_ORDER: Final[tuple[StopRule, ...]] = (
    StopRule.RULE_0,
    StopRule.RULE_1,
    StopRule.RULE_1B,
    StopRule.RULE_2,
    StopRule.RULE_3,
    StopRule.RULE_4,
    StopRule.RULE_5,
    StopRule.RULE_6,
)

#: The rules that halt the ladder. Rule 0 is an ordering obligation and rule 4 escalates;
#: rule 6 is a rule about the *shape* of an empty answer rather than about when to stop.
HALTING_RULES: Final[frozenset[StopRule]] = frozenset(
    {StopRule.RULE_1, StopRule.RULE_1B, StopRule.RULE_2, StopRule.RULE_3, StopRule.RULE_5}
)


@dataclass(frozen=True)
class StopInputs:
    """Everything D.3's rules read, and nothing else.

    A frozen record rather than the `LadderRun` itself, so a rule cannot reach past its own
    inputs into the run and quietly acquire a dependency the document does not give it -
    which is how rule 2 acquired rule 1b's escape.
    """

    exact: ExactSignal
    answer_type: AnswerTypePresence
    #: What this rung's own pages returned. D.3's `hit_count`, which is the page's count and
    #: not the delta into `H` (see `ExecutedProbe`).
    hit_count: int
    term_coverage: float
    constraint_drop_depth: int
    #: `sufficiency` as the rung reported it, or `None` when no rung has reported one.
    sufficiency: Sufficiency | None = None
    #: True when a budget cap has been exhausted. The cap object itself is the accountant's.
    cap_exhausted: bool = False
    #: Evidence found so far, across the rungs that enforced the whole parse.
    evidence_count: int = 0
    #: D.3 rule 4's `paraphrase_risk >= theta` disjunct. `None` while theta is [PRE-REG at G0]
    #: and nothing computes it; see `rule_4_escalates`.
    paraphrase_risk_over_threshold: bool | None = None
    #: D.3 rule 4's `tier-1 confidence non_lexical` disjunct. `None` for the same reason.
    tier_one_non_lexical: bool | None = None


def rule_1_stops(inputs: StopInputs) -> bool:
    """Branch E-a only, and unconditionally. `rfc822msgid:` with exactly one hit.

    "No structural, semantic or ranking rung may run" (SEM-04, RANK-01). It does **not**
    consult `answer_type_presence`: a message id cannot match a confident-looking wrong
    message, which is exactly the asymmetry ADV-004 restored.
    """
    return inputs.exact.branch is ExactBranch.E_A


def rule_1b_stops(inputs: StopInputs) -> bool:
    """Branches E-b and E-c, with D.3's own escape.

    `not blocks_stop` is `present is not False`: stop when the answer type is present, **or
    when the query carries no answer-type cue at all**. That escape is written into rule 1b
    in the document and into no other rule, which is the whole of `test_rule_two_does_not_
    carry_rule_one_bs_escape`.
    """
    return inputs.exact.fired and not inputs.answer_type.blocks_stop


def rule_2_stops(inputs: StopInputs) -> bool:
    """All four conjuncts, and the fourth is `present is True` - **not** `is not False`.

    CONS-036 added the fourth conjunct to A.7's L1 row so the two statements would stop
    disagreeing inside one document. R-RETR-007 then found the conjunct written as rule 1b's
    escape, which made the stop fire on almost every ordinary query - `present is None` is
    what a non-interrogative query produces - and turned whether a thread whose evidence is
    split across two messages was found at all on the query's *grammar*.
    """
    return (
        1 <= inputs.hit_count <= L1_STOP_MAX_HITS
        and inputs.term_coverage == 1.0
        and inputs.constraint_drop_depth == 0
        and inputs.answer_type.present is True
    )


def rule_3_stops(inputs: StopInputs) -> bool:
    """Any rung returning `sufficiency == sufficient`."""
    return inputs.sufficiency is Sufficiency.SUFFICIENT


def rule_4_escalates(inputs: StopInputs) -> bool:
    """Escalate to L4/L5. Four disjuncts, of which **two are not computable today**.

    `hit_count == 0` after L3 and `answer_type_presence == false` are computed and are what
    this project's escalation currently fires on. `paraphrase_risk >= theta` needs a theta
    that is [PRE-REG at G0], and `tier-1 confidence non_lexical` needs a tier-1 confidence
    signal that belongs to WS-09. Both arrive here as `None` and are treated as *not firing*
    rather than as false - and the difference matters at the reader, not here: a rung skipped
    because an uncomputed disjunct did not fire is not `not_applicable`, and
    `LadderAccount` records it as such. Writing them in as `False` would be the claim wider
    than the code, one disjunct at a time.
    """
    return (
        inputs.evidence_count == 0
        or inputs.answer_type.present is False
        or inputs.paraphrase_risk_over_threshold is True
        or inputs.tier_one_non_lexical is True
    )


def rule_5_stops(inputs: StopInputs) -> bool:
    """Any cap exhausted. The outcome is `inconclusive`, never `not_found` (D.2, OD-2)."""
    return inputs.cap_exhausted


#: The predicate for each rule, keyed by rule, so `first_rule_that_fires` iterates
#: `PUBLISHED_ORDER` and looks each one up rather than restating the sequence as an
#: if-chain. An if-chain is how an order gets edited by one line.
_PREDICATE: Final[dict[StopRule, object]] = {
    StopRule.RULE_1: rule_1_stops,
    StopRule.RULE_1B: rule_1b_stops,
    StopRule.RULE_2: rule_2_stops,
    StopRule.RULE_3: rule_3_stops,
    StopRule.RULE_5: rule_5_stops,
}


def first_rule_that_fires(inputs: StopInputs) -> StopRule | None:
    """The first **halting** rule that fires, in D.3's published order, or `None`.

    Rules 0, 4 and 6 are skipped here because none of them halts: rule 0 is an obligation
    discharged before this function is ever called, rule 4 escalates, and rule 6 is a
    statement about what an empty answer must carry. They stay in `PUBLISHED_ORDER` so the
    sequence this iterates is the document's own and not a filtered copy of it.
    """
    for rule in PUBLISHED_ORDER:
        predicate = _PREDICATE.get(rule)
        if predicate is None:
            continue
        assert callable(predicate)
        if predicate(inputs):
            return rule
    return None
