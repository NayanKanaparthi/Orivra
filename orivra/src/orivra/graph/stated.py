"""Source-stated relations: what a message *says*, gated four ways before it becomes an edge.

**`obs.said.supersedes_stated` is source-stated, not inferred.** Its namespace is `obs.said`,
so the edge model fixes its origin to `observed` and its assertion to `source_stated`: it
carries spans and a `StatedAssertionCheck` and, by the model's own rule, **no confidence** -
scoring a fact of the source reads as an inference that was promoted, and no rule promotes
one. Implementing it therefore does not give this release inferred edges; those are the `inf.*`
relations and they are `orivra.graph.inferred`'s, separately.

I had this on the wrong side of the line in an earlier report. The distinction is not
bookkeeping: a source-stated edge says *a human wrote this down* and a reader may hold the
author to it; an inferred edge says *this server concluded it* and a reader may discount it.
Presenting either as the other misdescribes who is responsible for the claim.

The pipeline: nominate clauses (`recognise.supersede`), then run all four gates
(`recognise.stated.check`). Most nominations refuse, which is the gates working - a matched
verb is not evidence of a relationship, and the counts of nominations and edges are different
numbers. Refusals are returned rather than discarded: a target-ambiguity refusal is precisely
what the inferred path is for.

**Only `body_clean` rows are read.** That depth is the content pipeline's own original-text
extraction, which is what makes a single `ORIGINAL` span an honest annotation of it. A snippet
is Gmail's excerpt and may carry quoted text; a stub has none. Running the clause gate over
either would be classifying text this response never established the provenance of.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from mailweave.content.annotate import AnnotatedBody, AnnotatedSpan, SpanClass
from mailweave.envelope.vocab import Depth
from orivra.contracts import (
    DerivationMethod,
    EvidenceEdge,
    EvidenceNode,
    FreshnessStatus,
    NodeKind,
    Relation,
    SourceReference,
    requirements_of,
)
from orivra.recognise.stated import (
    Candidate,
    Refused,
    _distinguishing,
    _fold,
    check,
)
from orivra.recognise.supersede import Nomination, nominate

#: The depths whose text is the pipeline's original-content extraction.
ASSERTABLE_DEPTHS: frozenset[Depth] = frozenset({Depth.BODY_CLEAN, Depth.BODY_FULL})

SUPERSEDE_METHOD = DerivationMethod(name="rule/stated_supersede", version="1")

#: The language the clause gates are written for. `clear_clause` takes it explicitly and
#: refuses what it cannot read, rather than applying English cue lists to text that is not
#: English - which would clear a negation it could not see.
LANGUAGE = "en"


@dataclass(frozen=True)
class Refusal:
    """One nomination that did not become an edge, and which gate stopped it.

    Kept rather than dropped for two reasons. A reader asking "why is there no edge here"
    deserves the gate's own answer, and the `target` refusals are the input to the inferred
    path: an ambiguous reference is not nothing, it is a relation this server can hold with a
    confidence and cannot state as the source's.
    """

    asserting_node_id: str
    nomination: Nomination
    gate: str
    why: str
    #: Every candidate the resolver was given.
    considered: tuple[str, ...] = ()
    #: The subset whose keys actually accounted for the reference's words. **The two are not
    #: the same fact and the inferred path needs both.** `resolve_target` returns
    #: `resolved_to=None` for two different failures - a phrase that named nothing
    #: distinguishing ("the earlier version") and a phrase that named several things - and
    #: only the second is an ambiguity. Recomputed here, where the candidate objects are in
    #: hand, because `Refused` carries ids and matching needs keys.
    matched: tuple[str, ...] = ()


@dataclass(frozen=True)
class StatedEdges:
    edges: tuple[EvidenceEdge, ...] = ()
    refusals: tuple[Refusal, ...] = field(default=())


def _annotated(text: str) -> AnnotatedBody:
    """The disclosed text of a `body_clean` row, as one `ORIGINAL` span.

    Honest because of the depth: `body_clean` **is** the quote-stripped original, so saying
    the whole of it is original restates what the depth already asserts rather than adding a
    claim. `ASSERTABLE_DEPTHS` is what keeps this true - a snippet annotated this way would be
    a claim that Gmail's excerpt contains no quoted text, which nothing established.
    """
    return AnnotatedBody(
        text=text,
        spans=(
            AnnotatedSpan(
                start=0,
                end=len(text),
                classification=SpanClass.ORIGINAL,
                signal="depth=body_clean: the content pipeline's original-text extraction",
            ),
        ),
    )


def candidates_from(nodes: Sequence[EvidenceNode], *, exclude: str) -> tuple[Candidate, ...]:
    """The nodes a reference could point at, keyed by their own disclosed words.

    A writer names an earlier message by what it was about, so the message's text is the
    surface form to match against. Display names are deliberately not keys, which is
    `structure/participants.py`'s rule and `Candidate`'s own.

    The asserting node is excluded: a message does not supersede itself, and leaving it in
    would let a self-reference resolve uniquely and produce an edge the model refuses anyway.
    """
    return tuple(
        Candidate(node_id=node.node_id, keys=(node.content or "",))
        for node in nodes
        if node.kind is NodeKind.MESSAGE and node.node_id != exclude and node.content
    )


def _matching(pool: Sequence[Candidate], referring_text: str) -> tuple[str, ...]:
    """Which candidates the reference's own words account for, by `Candidate.matches`.

    The resolver's rule, reused rather than reimplemented - it is the one that a review had to
    correct once already, and a second copy would be a second thing to correct.
    """
    folded = _fold(referring_text).strip(" .,;:\"'")
    if not _distinguishing(folded):
        # A phrase built of stopwords and generic tokens names nothing. It matches whatever is
        # in scope, so reporting matches here would let scope size manufacture a referent -
        # which is what `resolve_target` refuses and what this must not undo.
        return ()
    return tuple(one.node_id for one in pool if one.matches(folded))


def stated_edges(
    nodes: Sequence[EvidenceNode],
    *,
    reference_of: dict[str, SourceReference],
    freshness: FreshnessStatus,
) -> StatedEdges:
    """Every `supersedes_stated` edge this response's own text supports, and every refusal."""
    readable = [
        node
        for node in nodes
        if node.kind is NodeKind.MESSAGE and node.depth in ASSERTABLE_DEPTHS and node.content
    ]
    edges: list[EvidenceEdge] = []
    refusals: list[Refusal] = []
    for node in readable:
        text = node.content or ""
        body = _annotated(text)
        pool = candidates_from(nodes, exclude=node.node_id)
        for nomination in nominate(text):
            outcome = check(
                body=body,
                start=nomination.start,
                end=nomination.end,
                quoted=nomination.quoted,
                asserting_node_id=node.node_id,
                referring_text=nomination.referring_text,
                candidates=pool,
                language=LANGUAGE,
            )
            if isinstance(outcome, Refused):
                refusals.append(
                    Refusal(
                        asserting_node_id=node.node_id,
                        nomination=nomination,
                        gate=outcome.gate,
                        why=outcome.why,
                        considered=tuple(outcome.candidates),
                        matched=_matching(pool, nomination.referring_text),
                    )
                )
                continue
            target = outcome.target.resolved_to
            if target is None:  # pragma: no cover - `check` returns Refused in that case
                raise AssertionError(
                    "the target gate returned a check with no resolution; the model would "
                    "refuse the edge anyway, so this is a defect here rather than a refusal"
                )
            support = (reference_of[node.node_id], reference_of[target])
            edges.append(
                EvidenceEdge(
                    edge_id=f"{Relation.SUPERSEDES_STATED.value}/{node.node_id}->{target}",
                    source=node.node_id,
                    target=target,
                    relation=Relation.SUPERSEDES_STATED,
                    support=support,
                    spans=(outcome.span,),
                    stated=outcome,
                    method=SUPERSEDE_METHOD,
                    requires=requirements_of(support),
                    freshness=freshness,
                )
            )
    return StatedEdges(edges=tuple(edges), refusals=tuple(refusals))


__all__ = [
    "ASSERTABLE_DEPTHS",
    "LANGUAGE",
    "SUPERSEDE_METHOD",
    "Refusal",
    "StatedEdges",
    "candidates_from",
    "stated_edges",
]
