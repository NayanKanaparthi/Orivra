"""Sufficiency signals (AD A.8), of which `exact_signal_match` is the pivot (A.8a).

`exact_signal_match` is the document's largest gameability lever - D.3 rules 1 and 1b, D.5's
firing condition, D.7's prohibition and A.7's L0 stop all turn on it - so the definition
here is A.8a's, closed at three branches, with the two properties that make it ungameable
checked by execution rather than asserted:

  * **there is no fourth branch.** `ExactBranch` has exactly three members and
    `test_the_exact_signal_definition_is_closed_at_three_branches` holds the enum to A.8a's
    sentence. A fourth would be an architecture amendment, not a refactor;
  * **there is no frequency dial.** A.8a withdraws "unique token" as a qualifying signal:
    "corpus frequency is never consulted, and no frequency threshold may create an exact-
    signal match". `evaluate` therefore takes no corpus, no counts and no threshold - it
    takes the parse, the query that was executed, the hit count, and the text of the hits -
    and `test_the_evaluator_takes_no_frequency_input` reads its signature to say so.

Branch **E-b** is the one that does work rather than pattern-matching: Gmail's phrase
matching is not documented as literal, so MailWeave verifies the phrase itself, as a
contiguous substring of the hit's cleaned body or subject under NFKC + case-folding +
whitespace collapse. `verified_locally` is false when that check did not pass, and a branch
that did not verify does not fire.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from mailweave.constants import (
    EXACT_IDENTIFIER_MAX_HITS,
    EXACT_MSGID_HITS,
    EXACT_PHRASE_MAX_HITS,
)
from mailweave.query.analysis import (
    AnswerType,
    ParsedQuery,
    content_tokens,
    fold,
    matches_answer_type,
)


class ExactBranch(StrEnum):
    """A.8a's three enumerated branches. There is no fourth (see the module docstring)."""

    E_A = "E-a"
    E_B = "E-b"
    E_C = "E-c"


@dataclass(frozen=True)
class ExactSignal:
    """A.8a's required trace field, recorded with its firing inputs, fired or not."""

    fired: bool
    branch: ExactBranch | None
    phrase_tokens: int
    hit_count: int
    verified_locally: bool

    def as_trace_fields(self) -> dict[str, object]:
        return {
            "fired": self.fired,
            "branch": None if self.branch is None else self.branch.value,
            "phrase_tokens": self.phrase_tokens,
            "hit_count": self.hit_count,
            "verified_locally": self.verified_locally,
        }


def _contains_phrase(phrase: str, texts: Sequence[str]) -> bool:
    """A.8a E-b's local verification: contiguous substring under NFKC + fold + collapse."""
    needle = fold(phrase)
    return any(needle in fold(text) for text in texts)


def evaluate_exact_signal(
    parsed: ParsedQuery,
    *,
    executed_query: str,
    hit_count: int,
    hit_texts: Sequence[str],
) -> ExactSignal:
    """A.8a, evaluated. True iff one of the three branches holds; false in every other case.

    Branch precedence is E-a, E-b, E-c, and it is precedence rather than an accident of
    evaluation order: a query carrying both an `rfc822msgid:` and a quoted phrase is an
    identity lookup, and only branch E-a may stop the ladder unconditionally (D.3 rule 1).
    `test_branch_precedence_is_ea_then_eb_then_ec` executes that on a query carrying all
    three candidates at once.
    """
    msgid = parsed.rfc822msgid
    if msgid is not None and msgid.render() in executed_query and hit_count == EXACT_MSGID_HITS:
        return ExactSignal(
            fired=True,
            branch=ExactBranch.E_A,
            phrase_tokens=0,
            hit_count=hit_count,
            verified_locally=False,
        )
    for phrase in parsed.qualifying_phrases:
        tokens = len(content_tokens(phrase))
        if f'"{phrase}"' not in executed_query:
            continue
        if not 1 <= hit_count <= EXACT_PHRASE_MAX_HITS:
            continue
        verified = _contains_phrase(phrase, hit_texts)
        if verified:
            return ExactSignal(
                fired=True,
                branch=ExactBranch.E_B,
                phrase_tokens=tokens,
                hit_count=hit_count,
                verified_locally=True,
            )
        return ExactSignal(
            fired=False,
            branch=None,
            phrase_tokens=tokens,
            hit_count=hit_count,
            verified_locally=False,
        )
    for identifier in parsed.identifiers:
        if f'"{identifier.token}"' not in executed_query:
            continue
        if 1 <= hit_count <= EXACT_IDENTIFIER_MAX_HITS:
            return ExactSignal(
                fired=True,
                branch=ExactBranch.E_C,
                phrase_tokens=0,
                hit_count=hit_count,
                verified_locally=False,
            )
    return ExactSignal(
        fired=False,
        branch=None,
        phrase_tokens=(
            len(content_tokens(parsed.qualifying_phrases[0])) if parsed.qualifying_phrases else 0
        ),
        hit_count=hit_count,
        verified_locally=False,
    )


@dataclass(frozen=True)
class AnswerTypePresence:
    """A.8b's signal, tri-state, computed **before any stop rule is tested** (D.3 rule 0).

    `present` is `None` when the query carries no answer-type cue, which is a different
    statement from `False` and is exactly the distinction D.3 rule 1b turns on: "STOP after
    L0 only if `answer_type_presence` is true, **or the query carries no answer-type cue**".
    Collapsing the two would either disable the rule or disable the stop.
    """

    answer_type: AnswerType | None
    present: bool | None
    examined: int

    @property
    def blocks_stop(self) -> bool:
        """Whether D.3 rule 1b must refuse to stop: a cue exists and its token class is absent."""
        return self.present is False

    def as_trace_fields(self) -> dict[str, object]:
        return {
            "answer_type": None if self.answer_type is None else self.answer_type.value,
            "present": self.present,
            "texts_examined": self.examined,
        }


def evaluate_answer_type_presence(
    parsed: ParsedQuery, hit_texts: Sequence[str]
) -> AnswerTypePresence:
    """Mechanically check whether any hit carries a token of the query's answer type (A.8b).

    Run against quote-stripped bodies, which is what the caller passes: A.8b records that
    signature blocks and un-stripped attribution lines carry date-like tokens, so a
    predicate fed raw bodies is inert as a downgrade. This function cannot enforce what it
    is fed; PF-13 measures the base rate on the corpus that will feed it.
    """
    answer_type = parsed.answer_type
    if answer_type is None:
        return AnswerTypePresence(answer_type=None, present=None, examined=len(hit_texts))
    if not hit_texts:
        return AnswerTypePresence(answer_type=answer_type, present=False, examined=0)
    present = any(matches_answer_type(answer_type, text) for text in hit_texts)
    return AnswerTypePresence(answer_type=answer_type, present=present, examined=len(hit_texts))


def constraint_coverage_of(
    parsed: ParsedQuery,
    *,
    admitted_by: Mapping[str, tuple[str, ...]],
    message_id: str,
) -> tuple[str, ...]:
    """Which of the user's constraints the query that admitted `message_id` enforced.

    Derived from the probe that put the id into `H` - `HitOrigin.query` - rather than from
    a guess about the message, because `constraint_coverage` is a claim that this message
    satisfied that part of the query and Gmail's `q` is the only thing that judged it
    (R-DISC-006). A message with no recorded admitting probe reports no coverage rather
    than a default, which is the honest answer and not an omission.
    """
    known = {constraint.name for constraint in parsed.constraints}
    return tuple(name for name in admitted_by.get(message_id, ()) if name in known)
