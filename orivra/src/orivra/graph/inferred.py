"""Inferred relations: what this server concluded, held with a confidence and never promoted.

**This is a different thing from `orivra.graph.stated`, and the difference is who is
responsible for the claim.** A source-stated edge says a human wrote something down and a
reader may hold the author to it. An inferred edge says *this server concluded it* from
evidence it shows, and a reader may discount it. The edge model enforces the split rather than
trusting a builder: an `inf.*` relation with no spans is refused ("an inference with nothing
quoted behind it is an assertion a reader cannot check") and one with no confidence is refused
("the difference between an inference and a fact is that the inference says how strongly it is
held"), while an `obs.*` relation carrying a confidence is refused in the other direction.

**Where the inferences come from is the design's own answer, not a new one.** `resolve_target`
already says it: a reference that names no node, or names several, comes back with
`resolved_to=None` and the full candidate set, and its docstring calls that "exactly what an
`inf.potentially_supersedes` edge needs to record the ambiguity honestly". So the inferred path
is fed by the source-stated path's refusals, and only by the refusals that are about *target
ambiguity*. The other gates are not ambiguity:

* a `span` refusal means the quotation is not in the source, so there is nothing to infer from;
* a `clause` refusal means the sentence was negated, hypothetical or hedged - "we are **not**
  withdrawing the approval" states the opposite, and inferring a weak version of a claim the
  writer denied is worse than drawing nothing.

Only `target` refusals become edges here, and one per candidate the resolver considered, each
carrying the same span and a confidence whose value falls with the number of candidates.

**That confidence is a heuristic allocation, not a calibrated probability**, and `_confidence`
says so at length. `1/n` spreads one unit of belief evenly over candidates nothing
distinguishes; it does not estimate that any particular edge is true, it assumes the true
target is inside the candidate set at all, and no labelled set has been scored against this
method. A reader may order these edges against each other and must not threshold them as
probabilities or read `0.5` as a 50% hit rate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from orivra.contracts import (
    Confidence,
    DerivationMethod,
    EvidenceEdge,
    Relation,
    SourceReference,
    Span,
    requirements_of,
)
from orivra.contracts.refs import FreshnessStatus
from orivra.graph.stated import Refusal

POTENTIAL_METHOD = DerivationMethod(name="rule/ambiguous_supersede", version="1")

#: The most candidates an ambiguous reference may be spread across before this stops drawing
#: edges at all. Past it the "inference" is a list of everything in scope, which is a statement
#: about the scope rather than about the sentence - the failure `resolve_target` refuses
#: one-by-one and this refuses in bulk.
MAX_CANDIDATES: int = 4


@dataclass(frozen=True)
class InferredEdges:
    edges: tuple[EvidenceEdge, ...] = ()
    #: Refusals this path also declined, with the reason. A refusal that reaches neither path
    #: is a silence, and a reader cannot tell a silence from an absence of evidence.
    declined: tuple[tuple[Refusal, str], ...] = ()


def _confidence(candidates: int) -> Confidence:
    """`1/n`: a **heuristic allocation** across the candidate set, not a calibrated probability.

    **What this number is.** The clause named a target ambiguously and the resolver returned
    `n` candidates it could not choose between. This spreads one unit of belief evenly over
    them, because nothing in the evidence favours any one, and hands each edge its `1/n`
    share. It is an *allocation rule*, and its only real properties are that the shares sum to
    one and that each falls as the ambiguity widens.

    **What this number is not.** It is not an estimate that this edge is true, and it must not
    be read, thresholded or aggregated as one. Reading it that way would mean assuming three
    things this server has not established:

    * that the clause performs a supersession at all - the gates refuse the clear failures,
      but a gate that passes is not a measurement of how often it is right;
    * that the true target is inside the candidate set, rather than a message outside this
      response's scope entirely, in which case every share here is allocated to a wrong
      answer and they still sum to one;
    * that the candidates are equiprobable, which is an admission that nothing distinguishes
      them rather than a finding that nothing does.

    **It is uncalibrated, and nothing has measured it.** No labelled set has been scored
    against this method, so "0.5" here has no relationship to a 50% hit rate. `Confidence`
    carries its `method` precisely so that two numbers from two methods are never compared;
    this one is comparable only with itself, and only in the direction "wider ambiguity, lower
    share". Calibration is H5's question and H5 is not decided in this release.
    """
    return Confidence(
        method=POTENTIAL_METHOD,
        value=round(1.0 / candidates, 4),
        basis=(
            f"the clause states a supersession; its reference matched {candidates} messages, so "
            "this edge is one of that many mutually exclusive readings. The value is a 1/n "
            "heuristic allocation over them, not a calibrated probability that this holds: it "
            "assumes the true target is among them and that nothing separates them. No "
            "labelled set has been scored against this method and it is not comparable with "
            "another method's"
        ),
    )


def inferred_edges(
    refusals: Sequence[Refusal],
    *,
    reference_of: dict[str, SourceReference],
    freshness: FreshnessStatus,
    max_candidates: int = MAX_CANDIDATES,
) -> InferredEdges:
    """Turn target-ambiguous refusals into `inf.potentially_supersedes`, and decline the rest."""
    edges: list[EvidenceEdge] = []
    declined: list[tuple[Refusal, str]] = []
    for refusal in refusals:
        if refusal.gate != "target":
            declined.append(
                (
                    refusal,
                    f"the {refusal.gate} gate refused, which is not an ambiguity: a span that "
                    "is not in the source has nothing behind it to infer from, and a clause "
                    "the writer negated or hedged states the opposite of what a weakened "
                    "version of it would claim",
                )
            )
            continue
        # **`matched`, not `considered`** - the two target refusals are different failures and
        # only one is an ambiguity. "This supersedes the earlier version" matched nothing: it
        # points rather than names, and with a single candidate in scope an inference drawn
        # from it would carry confidence 1.0 for a phrase that identifies no message. That is
        # the scope manufacturing a referent, which `resolve_target` exists to refuse; drawing
        # a weakened version of the same mistake would undo it one layer out.
        reachable = [one for one in refusal.matched if one in reference_of]
        if not reachable:
            declined.append(
                (
                    refusal,
                    "the reference named nothing that identifies a message this graph holds. "
                    "A phrase that points rather than names has no target at any confidence, "
                    "and inventing one from how few candidates were in scope is the failure "
                    "the target gate refuses",
                )
            )
            continue
        if len(reachable) == 1:
            declined.append(
                (
                    refusal,
                    "exactly one candidate matched, so this is not an ambiguity - the target "
                    "gate refused for another reason and inferring past it would restate as a "
                    "weak claim what the gates declined to state as a strong one",
                )
            )
            continue
        if len(reachable) > max_candidates:
            declined.append(
                (
                    refusal,
                    f"the reference matched {len(reachable)} candidates, past the {max_candidates} "
                    "this rule will spread an inference across. Beyond that the edge set is a "
                    "statement about how much was in scope rather than about the sentence",
                )
            )
            continue
        confidence = _confidence(len(reachable))
        asserting = refusal.asserting_node_id
        for target in reachable:
            support = (reference_of[asserting], reference_of[target])
            edges.append(
                EvidenceEdge(
                    edge_id=(
                        f"{Relation.POTENTIALLY_SUPERSEDES.value}/{asserting}->{target}"
                        f"@{refusal.nomination.start}"
                    ),
                    source=asserting,
                    target=target,
                    relation=Relation.POTENTIALLY_SUPERSEDES,
                    support=support,
                    # The same quotation the source-stated path would have carried. An
                    # inference that showed a reader nothing to check would be an assertion.
                    spans=(_span_of(refusal, asserting),),
                    confidence=confidence,
                    method=POTENTIAL_METHOD,
                    requires=requirements_of(support),
                    freshness=freshness,
                )
            )
    return InferredEdges(edges=tuple(edges), declined=tuple(declined))


def _span_of(refusal: Refusal, node_id: str) -> Span:
    return Span(
        node_id=node_id,
        start=refusal.nomination.start,
        end=refusal.nomination.end,
        text=refusal.nomination.quoted,
    )


__all__ = ["MAX_CANDIDATES", "POTENTIAL_METHOD", "InferredEdges", "inferred_edges"]
