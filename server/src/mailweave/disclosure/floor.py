"""The E2 reply-chain floor: absolute in membership, declared in depth (AD A.9(2), OD-3).

**The guarantee, in the two halves OD-3 splits it into.**

*Membership is absolute.* Every reply parent and every direct child of every evidence
message is present in the response - as a row or as a declared collapsed-run member, never
absent and never a bare count. No step of the A.9a degradation ladder may remove one; the
ladder's driver checks that after **every** step rather than inside any of them
(`ladder.assert_floor_intact`).

*Depth is earned.* A floor member is present at `snippet` when this response observed text
for it and at `stub` when it did not. It is **promoted** to `body_clean` only when the
promotion rule below says the evidence depends on it. OD-3's arithmetic is why: a
40-message thread with six hits needs about 11,200 tokens to show every hit and the whole
chain at readable length against a 9,000-token ceiling, and the arithmetic does not close.

## The promotion rule, stated once

> A floor member is promoted above its base depth **only when the evidence message it hangs
> off cannot be read without it**. Dependence is one of exactly three mechanical relations,
> tested in the published order below; the first that holds is the one recorded. A floor
> member for which none holds stays at its base depth and says so.

1. **`QUOTATION`** - the member is the evidence message's **reply parent**, and the
   evidence message's own annotated body carries a `quoted` or `forwarded` span (A7). The
   evidence's text literally incorporates text it did not write, so reading the evidence at
   body depth while its parent is a snippet is reading half of a quotation.
2. **`CONTRADICTION`** - the member is a **direct child** of the evidence message, and the
   text this response observed for it carries a token of A.8a's published decision lexicon.
   This is T-CD2's own shape: the quiet later reply that reverses the decision the
   higher-scoring messages support.
3. **`CONSTRAINT_CARRIER`** - the member satisfies a constraint of the *query* that the
   evidence message does not. Gmail evaluates `q` message-scoped (RO F2), so a thread can
   answer a two-condition question with two messages and no single message matches; the
   neighbour that carries the other condition is part of the evidence rather than context
   around it.

## Where it says no, and why that matters more than where it says yes

The rule is written so that the **ordinary** neighbour is refused. A direct child that
merely replies - "Thanks, will do." - is a floor member, is always present, is cheap to
promote, and is *not* promoted: it carries no decision cue, it covers no constraint the
parent misses, and it is a child so the quotation clause cannot reach it. If every floor
member were promoted "because the evidence might depend on it", this would be a fixed
window of unbounded radius wearing a query-aware name, which is exactly what RR DISC-01's
degenerate-strategy guard is for.
`test_the_promotion_rule_refuses_an_ordinary_adjacent_reply` is that case, executed.

Two of the three clauses read the query (`CONSTRAINT_CARRIER` directly; `CONTRADICTION`
through the lexicon that also drives A.8a's answer-type predicate), and one reads only the
observation (`QUOTATION`). None of them reads a fixture feature, a thread id, a subject
line or a corpus.

## What a missing input does

A clause whose input this response does not hold does not fire, and does not fire
negatively either. If the evidence message's body was never fetched there is no annotation
to read, so `QUOTATION` cannot hold - and the row then says `dependence: None` rather than
claiming the evidence does not quote. "We did not see" is not "there was nothing", which is
the same rule `MailboxProvenance.unobserved()` states about labels.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from mailweave.content.annotate import AnnotatedBody, SpanClass
from mailweave.envelope.vocab import Depth, FloorDependence, FloorRelation
from mailweave.query.analysis import DECISION_VERBS, content_tokens

#: The spans whose presence in the *evidence* message's body means that message
#: incorporates text it did not write. A7's own classes; the pair is named here rather than
#: at the use site so a class added to `SpanClass` later has to be considered.
INCORPORATED_SPANS: Final[frozenset[SpanClass]] = frozenset({SpanClass.QUOTED, SpanClass.FORWARDED})

#: The base depth of a floor member this response holds text for. **Snippet, not stub**,
#: and A.9a's honesty note is the reason: a reversing reply is typically short, so at
#: snippet depth the reversal is commonly *visible* rather than merely counted. That is the
#: claim the floor actually supports; "the agent will notice" is not.
FLOOR_BASE_DEPTH: Final[Depth] = Depth.SNIPPET

#: The depth a promoted floor member reaches, when this response holds a body for it.
FLOOR_PROMOTED_DEPTH: Final[Depth] = Depth.BODY_CLEAN


@dataclass(frozen=True)
class FloorMember:
    """One message the floor keeps, and why - both the relation and the dependence.

    `dependence is None` is the commonest and most important value in this module: it is
    the rule saying no, recorded rather than left as an absence.
    """

    message_id: str
    relation: FloorRelation
    #: The evidence message this member hangs off. A member reachable from two evidence
    #: messages is recorded against the first in thread order, so the reason names one
    #: anchor rather than an arbitrary one.
    anchor_id: str
    dependence: FloorDependence | None

    @property
    def promoted(self) -> bool:
        return self.dependence is not None


@dataclass(frozen=True)
class EvidenceFacts:
    """What the promotion rule reads about one evidence message.

    `body` is `None` when this response fetched no body for the hit, which is a real state:
    `max_body_fetches` is a published cap (A.7) and a hit beyond it is disclosed at reduced
    depth rather than withheld.
    """

    message_id: str
    body: AnnotatedBody | None
    constraint_coverage: frozenset[str]


@dataclass(frozen=True)
class MemberFacts:
    """What the promotion rule reads about one candidate floor member."""

    message_id: str
    observed_text: str | None
    constraint_coverage: frozenset[str]


def incorporates_text_it_did_not_write(body: AnnotatedBody | None) -> bool:
    """A7 clause of the rule: does this body carry quoted or forwarded spans?

    Reads the annotation rather than the text, which is the whole of A7: the classifier's
    judgement is a structured fact of the object, so this predicate is a set membership
    test and not a regex over mail.
    """
    if body is None:
        return False
    return any(span.classification in INCORPORATED_SPANS for span in body.spans)


def carries_a_decision_cue(text: str | None) -> bool:
    """A.8a's published lexicon, over text this response actually observed."""
    if text is None:
        return False
    return bool(frozenset(content_tokens(text)) & DECISION_VERBS)


def dependence_of(
    *, relation: FloorRelation, evidence: EvidenceFacts, member: MemberFacts
) -> FloorDependence | None:
    """The promotion rule, executed. Three clauses in published order, first hit wins.

    Returns `None` - *the rule saying no* - whenever no clause holds. That is the branch
    the module's docstring is about and the one
    `test_the_promotion_rule_refuses_an_ordinary_adjacent_reply` pins.
    """
    if relation is FloorRelation.PARENT and incorporates_text_it_did_not_write(evidence.body):
        return FloorDependence.QUOTATION
    if relation is FloorRelation.CHILD and carries_a_decision_cue(member.observed_text):
        return FloorDependence.CONTRADICTION
    if member.constraint_coverage - evidence.constraint_coverage:
        return FloorDependence.CONSTRAINT_CARRIER
    return None


def floor_of(
    *,
    evidence_ids: Iterable[str],
    order: Sequence[str],
    parent_of: Mapping[str, str | None],
    children_of: Mapping[str, Sequence[str]],
    evidence: Mapping[str, EvidenceFacts],
    members: Mapping[str, MemberFacts],
) -> tuple[FloorMember, ...]:
    """Every reply parent and direct child of every evidence message, with its dependence.

    `order` is the thread's chronological order (amendment A3), and it decides two things
    that would otherwise be arbitrary: which anchor a member reachable from two evidence
    messages is recorded against, and the order of the returned tuple. Both are facts of
    the thread rather than of a dict's iteration.

    **An evidence message that is itself another evidence message's parent or child IS a
    floor member** (round 25, R-DISC-021). Round 23 skipped it - "it is already present at
    evidence depth, and a second record for it would be a second disposition for one
    message (A.7a)" - and the first half of that sentence is true while the conclusion is
    not. `floor_of`'s output is two things at once: the list of members whose *depth* the
    promotion rule decides, and the set the A.9a ladder may never remove. Skipping a hit
    removed it from the second as well as the first, so A.9a step 8 - whose only guard is
    `row.id not in floor_ids` - could withhold a disclosed hit's direct child, and the
    surviving hit's reply chain had a hole in it filled by a bare pointer. Reproduced: a
    60-message chain in which every message matched produced an **empty** floor.

    A.7a is satisfied by the *banding*, not by the omission: `plan_thread` tests
    `message_id in thread.hit_ids` before it tests floor membership, so a hit stays in
    `Band.EVIDENCE` and gets exactly one row. `dependence` is `None` for such a member
    because promotion is a statement about depth and a hit is already at evidence depth;
    the record exists to state the *relation*, which is what membership is about.
    """
    hits = frozenset(evidence_ids)
    position = {message_id: index for index, message_id in enumerate(order)}
    seen: dict[str, FloorMember] = {}
    for anchor_id in sorted(hits, key=lambda mid: position.get(mid, len(order))):
        anchor = evidence.get(anchor_id)
        if anchor is None:
            continue
        for member_id, relation in _neighbours(anchor_id, parent_of, children_of):
            if member_id in seen:
                continue
            member = members.get(member_id)
            if member is None:
                continue
            seen[member_id] = FloorMember(
                message_id=member_id,
                relation=relation,
                anchor_id=anchor_id,
                dependence=(
                    None
                    if member_id in hits
                    else dependence_of(relation=relation, evidence=anchor, member=member)
                ),
            )
    return tuple(
        seen[message_id]
        for message_id in sorted(seen, key=lambda mid: position.get(mid, len(order)))
    )


def _neighbours(
    anchor_id: str,
    parent_of: Mapping[str, str | None],
    children_of: Mapping[str, Sequence[str]],
) -> list[tuple[str, FloorRelation]]:
    """A.9(2)'s neighbourhood of one evidence message: its reply parent and direct children."""
    related: list[tuple[str, FloorRelation]] = []
    parent = parent_of.get(anchor_id)
    if parent is not None:
        related.append((parent, FloorRelation.PARENT))
    related.extend((child_id, FloorRelation.CHILD) for child_id in children_of.get(anchor_id, ()))
    return related


def floor_pairs_of(
    *,
    evidence_ids: Iterable[str],
    parent_of: Mapping[str, str | None],
    children_of: Mapping[str, Sequence[str]],
    known_ids: Iterable[str],
) -> tuple[tuple[str, str], ...]:
    """**Every** `(evidence message, floor member)` obligation A.9(2) creates, not one per member.

    `floor_of` records a member reachable from two evidence messages against the first in
    thread order, which is right for the *reason* a row carries and wrong for the *guarantee*:
    the member is owed to both, and a ladder step that could see only the first obligation
    would happily drop the member once the first anchor left. The A.9a driver's floor gate
    reads these pairs, so it can allow the one lawful removal - a member leaving together
    with every evidence message that needs it - and refuse every other.
    """
    known = frozenset(known_ids)
    pairs: set[tuple[str, str]] = set()
    for anchor_id in evidence_ids:
        for member_id, _relation in _neighbours(anchor_id, parent_of, children_of):
            if member_id in known:
                pairs.add((anchor_id, member_id))
    return tuple(sorted(pairs))
