"""The scoring primitives of EP §6, callable and unit-tested.

**Reproducible means two things here**, and both are properties of these functions rather
than of the runner that calls them: the same transcript and the same manifest produce the
same number, and every number is derived from harness-measured or manifest-scored fields
only. EP §6.3's rule - *headline metrics derive only from harness-measured + manifest-scored
fields* - is enforced by these signatures: nothing below takes a self-reported figure, so a
self-reported figure cannot reach a headline through them.

**Three rates are returned together and cannot be separated.** `false_not_found`,
`hallucinated_found` and `inconclusive` are one object, because each can be improved by
making another worse: a system that never says "not found" has an FNF of zero and a
hallucinated-found rate of one. EP §6.1 states that they are always reported together;
`OutcomeRates` is that sentence made unskippable.

**`inconclusive` is not a false "not found".** It asserts no nonexistence. It is reported as
its own rate, alongside the other two, which is OD-2's extension to the preserved block.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

#: Whitespace normalisation for quote matching. A disclosure that re-wrapped a line is still
#: a disclosure; a disclosure that dropped a word is not.
_WHITESPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Whitespace-collapsed, stripped. The comparison EP §6.1 specifies for `disclosed(e)`."""
    return _WHITESPACE.sub(" ", text).strip()


class Terminal(StrEnum):
    """EP §6.1's classification vocabulary, with OD-2's fourth value."""

    ANSWERED = "answered"
    NOT_FOUND = "not_found"
    INCONCLUSIVE = "inconclusive"
    OTHER = "other"


@dataclass(frozen=True)
class Disclosure:
    """What one response actually disclosed, as the harness measured it.

    `content_by_id` holds only text the response carried as message content. A stub or a
    snippet-only row is **not** a disclosure (EP §6.1) and belongs in `surfaced_ids`, which
    is why the two are separate fields rather than one set with a flag.
    """

    content_by_id: Mapping[str, str]
    surfaced_ids: frozenset[str] = frozenset()
    tokens_returned: int = 0
    distractor_tokens: int = 0
    evidence_tokens: int = 0


def disclosed(disclosure: Disclosure, message_id: str, quote: str) -> bool:
    """EP §6.1's `disclosed(e)`: the response carries this message's quote span, attributable
    to that message.

    Attributable, which is why the join is by id and not by scanning the whole response for
    the quote: a quote that appears under another message's row is that message's content,
    and counting it would credit a retrieval that returned the wrong evidence.
    """
    carried = disclosure.content_by_id.get(message_id)
    if carried is None:
        return False
    return normalise(quote) in normalise(carried)


def evidence_recall(disclosure: Disclosure, required: Mapping[str, str]) -> float:
    """`|{e in E : disclosed(e)}| / |E|`, per case.

    A case with no required evidence raises rather than returning 1.0: a recall of one over
    an empty requirement is a number that looks like success and measures nothing, and the
    case that produced it is a case that was mis-specified.
    """
    if not required:
        raise ValueError(
            "evidence recall over an empty requirement set; the case requires nothing, so "
            "the figure would be 1.0 for every system including one that returned nothing"
        )
    found = sum(
        1 for message_id, quote in required.items() if disclosed(disclosure, message_id, quote)
    )
    return found / len(required)


def case_recall_strict(
    disclosure: Disclosure,
    *,
    must_retrieve: Mapping[str, str],
    any_of: Mapping[str, str] | None = None,
) -> bool:
    """1 iff **all** `must_retrieve` evidence is disclosed; for `any_of`, at least one."""
    if any_of:
        satisfied = any(
            disclosed(disclosure, message_id, quote) for message_id, quote in any_of.items()
        )
        if not satisfied:
            return False
    return all(
        disclosed(disclosure, message_id, quote) for message_id, quote in must_retrieve.items()
    )


def surfaced_not_disclosed(disclosure: Disclosure, required: Iterable[str]) -> frozenset[str]:
    """Evidence the response named without carrying: a legitimate progressive-disclosure
    state, reported separately because recall is only earned when the content arrives."""
    return frozenset(
        message_id
        for message_id in required
        if message_id in disclosure.surfaced_ids and message_id not in disclosure.content_by_id
    )


def relevant_token_fraction(disclosure: Disclosure) -> float:
    """Evidence-message tokens over all disclosed content tokens.

    Zero disclosed tokens returns 0.0 rather than raising: a response that disclosed nothing
    has a relevant fraction of nothing, which is a real measurement of a real response, and
    the recall metric is where its emptiness is scored.
    """
    if disclosure.tokens_returned <= 0:
        return 0.0
    return disclosure.evidence_tokens / disclosure.tokens_returned


@dataclass(frozen=True)
class OutcomeRates:
    """The three rates EP §6.1 requires to be reported together.

    Together, because each can be improved by making another worse. A system that never says
    "not found" scores a perfect FNF and a terrible hallucinated-found rate.

    A system that says "inconclusive" to everything scores a perfect FNF and the **worst
    possible** hallucinated-found rate, because EP §6.1 defines that control as the fraction
    of unanswerable cases *not* classified `not_found` - and "inconclusive" is not
    `not_found`. An earlier draft of this paragraph said such a system "scores perfectly on
    both", which is the opposite of what the code does, in the one place explaining why the
    three numbers must be read together (review finding R-M1-022).
    """

    false_not_found: float
    hallucinated_found: float
    inconclusive: float
    answerable: int
    unanswerable: int

    def render(self) -> str:
        return (
            f"FNF {self.false_not_found:.3f} over {self.answerable} answerable | "
            f"hallucinated-found {self.hallucinated_found:.3f} over {self.unanswerable} "
            f"controls | inconclusive {self.inconclusive:.3f}"
        )


def outcome_rates(
    *, answerable: Sequence[Terminal], unanswerable: Sequence[Terminal]
) -> OutcomeRates:
    """FNF, its paired control, and the inconclusive rate - computed in one call.

    One call and one object, so neither half can be reported without the other. `inconclusive`
    is excluded from FNF because it asserts no nonexistence (OD-2), and is reported as its own
    rate rather than folded into `other`, where it would be invisible.
    """
    if not answerable:
        raise ValueError(
            "no answerable cases: FNF over an empty set is undefined, and reporting 0.0 "
            "would read as a system that never wrongly said not-found"
        )
    if not unanswerable:
        raise ValueError(
            "no unanswerable controls: FNF without its paired hallucinated-found rate can "
            "be improved by never saying not-found, which EP §6.1 forbids reporting alone"
        )
    false_not_found = sum(1 for one in answerable if one is Terminal.NOT_FOUND) / len(answerable)
    hallucinated = sum(1 for one in unanswerable if one is not Terminal.NOT_FOUND) / len(
        unanswerable
    )
    everything = [*answerable, *unanswerable]
    inconclusive = sum(1 for one in everything if one is Terminal.INCONCLUSIVE) / len(everything)
    return OutcomeRates(
        false_not_found=false_not_found,
        hallucinated_found=hallucinated,
        inconclusive=inconclusive,
        answerable=len(answerable),
        unanswerable=len(unanswerable),
    )


@dataclass(frozen=True)
class Partiality:
    """The normalised record EP §6.2's assertions run over.

    `claimed_total` **is** the response's `stated_total` (CONS-023): one quantity with two
    names across the measurement boundary. The mapping is stated here because P1a is scored
    *through* this record, which is exactly where an adapter bug would hide.
    """

    claimed_total: int | None
    included_ids: frozenset[str]
    payload_ids: frozenset[str]
    more_available_signal: bool
    role_tags: Mapping[str, str]
    reason_tags: Mapping[str, str]
    derived_ids: frozenset[str] = frozenset()
    derived_tagged_ids: frozenset[str] = frozenset()


#: Contract R-02's closed seven-value set. P4 is scored across all seven, because the
#: Revision-1 three-value set was narrower than the contract it was measuring (CONS-008).
ROLE_VALUES: frozenset[str] = frozenset(
    {"matched", "context", "parent", "child", "requested", "stub", "derived"}
)


def partiality_assertions(
    record: Partiality, *, true_length: int, evidence_ids: frozenset[str] = frozenset()
) -> dict[str, bool]:
    """P1, P1a, P2, P3, P4 and P5, as booleans, over one case.

    **P2 and P3 are mechanical self-consistency assertions and their bar is 1.00**, not
    ≥0.98: "the response's own account of what it contains is accurate" either holds or is a
    defect (CONS-011). That bar belongs to the runner; what belongs here is that the two are
    computed from the payload rather than from anything the response asserts about itself.
    """
    disclosed_count = len(record.payload_ids)
    return {
        "P1": record.claimed_total is not None,
        "P1a": record.claimed_total == true_length,
        "P2": record.included_ids == record.payload_ids,
        "P3": (
            record.more_available_signal
            if disclosed_count < true_length
            else not record.more_available_signal
        ),
        "P4": all(
            record.role_tags.get(one) in ROLE_VALUES and bool(record.reason_tags.get(one))
            for one in record.payload_ids
        )
        and all(
            record.role_tags.get(one) == "matched" for one in evidence_ids & record.payload_ids
        ),
        "P5": record.derived_ids <= record.derived_tagged_ids,
    }


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """The 95% Wilson interval EP §6.1 asks for on every aggregate.

    Wilson rather than normal-approximation, because the aggregates here are small-n and
    often near 0 or 1, which is exactly where the normal approximation produces bounds
    outside [0, 1] and a reader concludes the harness is broken.
    """
    if trials <= 0:
        raise ValueError("a confidence interval over zero trials states nothing")
    if not 0 <= successes <= trials:
        raise ValueError(f"{successes} successes in {trials} trials")
    proportion = successes / trials
    denominator = 1 + z * z / trials
    centre = (proportion + z * z / (2 * trials)) / denominator
    spread = (
        z
        * math.sqrt(proportion * (1 - proportion) / trials + z * z / (4 * trials * trials))
        / denominator
    )
    return (max(0.0, centre - spread), min(1.0, centre + spread))


__all__ = [
    "ROLE_VALUES",
    "Disclosure",
    "OutcomeRates",
    "Partiality",
    "Terminal",
    "case_recall_strict",
    "disclosed",
    "evidence_recall",
    "normalise",
    "outcome_rates",
    "partiality_assertions",
    "relevant_token_fraction",
    "surfaced_not_disclosed",
    "wilson_interval",
]
