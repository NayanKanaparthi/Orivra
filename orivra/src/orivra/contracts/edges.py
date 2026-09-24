"""`EvidenceEdge`: observed and inferred can never look alike (plan §4.5).

**A span that matches the source proves the text exists. It does not prove the relationship
is correct.** That sentence is the whole of this module. The first draft of the design had
one `observed` category, which put `reply_to` - a fact read out of an `In-Reply-To` header -
beside `supersedes_stated` - a sentence a human typed - as though Orivra knew both to the
same standard. It does not, and a reader given one label for both would reasonably conclude
otherwise.

So the observed category is split, and the split is carried by the relation's own value
rather than by a field a builder fills in:

* **`obs.meta.*` - metadata.** Facts of the source's own data structures: an `In-Reply-To`
  header, thread membership, a revision chain, channel membership, an authorship field.
  Read, never interpreted. **These are the only relations Orivra asserts on its own
  authority.**
* **`obs.said.*` - source-stated.** Claims a human made inside content Orivra is reading.
  Orivra reports *that the source asserts this*; it never reports that Orivra verified it.
  Emitting one requires four things, each of which must arrive with its evidence rather than
  as a boolean (`StatedAssertionCheck`): the verbatim span, matched; the target identified
  uniquely; the clause cleared of negation, quotation, hypothetical and interrogative cues;
  and the asserting node named.
* **`inf.*` - derived.** Orivra's own inference, always with spans, always with a confidence
  and a versioned method, never presented as a fact of the source.

There is no `caused` relation in either namespace, and **no rule promotes an inferred
relation to an observed one**.

**Permission is checked over the whole edge, not over its endpoints.** An edge whose
assertion rests on a third document the caller cannot read is not emittable even when both
endpoints are readable, because the edge itself would disclose what that document says. That
is why `support` carries every reference that was read to assert the edge - the two
endpoints among them - and why the validator refuses an edge any of whose supporting
references falls outside the context it is published under.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from orivra.contracts.nodes import DerivationMethod, Span
from orivra.contracts.permission import (
    PermissionRequirement,
    requirement_digest,
    requirements_of,
)
from orivra.contracts.refs import FreshnessStatus, Frozen, SourceReference
from orivra.contracts.vocab import Assertion, ConnectorId, EdgeOrigin, Relation


class Confidence(Frozen):
    """How strongly an inferred relation is held, and by what.

    `basis` is a sentence, not a category: a number with no account of what produced it is a
    number readers will calibrate against nothing. `value` is bounded to `[0, 1]` and is
    never compared across methods - two methods' 0.8 are not the same 0.8, which is why the
    method rides along.
    """

    method: DerivationMethod
    value: float = Field(ge=0.0, le=1.0)
    basis: str = Field(min_length=1, max_length=400)


class TargetResolution(Frozen):
    """Which node a source-stated span points at, and how sure that is (rule 2 of §4.5).

    "This supersedes the earlier version", in a scope holding three earlier versions, does
    **not** identify a target. The honest outcomes are an inferred
    `inf.potentially_supersedes` with the ambiguity recorded, or no edge at all - never an
    observed edge pointed at whichever candidate was first in a list.

    `considered` is the full candidate set the resolver had in scope, kept because the
    interesting failure is the one where the set was too small: a resolver that saw one
    candidate resolves "uniquely" every time.
    """

    resolved_to: str | None = Field(default=None, min_length=1, max_length=256)
    considered: tuple[str, ...] = ()
    referring_text: str = Field(min_length=1, max_length=400)
    """The words inside the span that do the pointing - "the earlier version", "the July
    draft", a message-id. Quoted so a reader can judge the resolution rather than trust it."""

    @model_validator(mode="after")
    def _a_resolution_names_one_of_the_candidates_it_considered(self) -> Self:
        if self.resolved_to is None:
            return self
        if self.resolved_to not in self.considered:
            raise ValueError(
                f"target {self.resolved_to!r} was not among the candidates the resolver "
                f"considered ({list(self.considered)}); a target found outside the "
                "candidate set is a resolution nothing constrained"
            )
        return self

    @property
    def unique(self) -> bool:
        """Whether exactly one candidate was identified. Zero and many both fail."""
        return self.resolved_to is not None


class ClauseClearance(Frozen):
    """The negation, quotation, hypothetical and interrogative gate (rule 3 of §4.5).

    Four sentences must each fail to produce an edge:

    * "we are **not** withdrawing the approval" - negation;
    * a quoted block reproducing **someone else's** withdrawal - quotation;
    * "**if** certification fails we **would** withdraw" - hypothetical and conditional;
    * "**should we** withdraw?" - interrogative.

    The recogniser runs over de-quoted, de-signature content, because `content/quotes.py`
    already separates quoted regions and a rule that ignored that separation would attribute
    a correspondent's sentence to the sender. The evidence is kept: `clause` is the region
    that was scanned, and `cues_found` is what the scan saw. A clearance with cues in it is
    refused here, so "we ran the check and ignored it" is not a state this type can hold.

    `language` is required and only `en` clears. The cue sets are English; a clause in
    another language produces no recognised cue and would otherwise clear *because* the
    recogniser does not speak it, which is the failure mode that looks most like success.
    """

    clause: str = Field(min_length=1, max_length=2000)
    language: str = Field(min_length=2, max_length=8)
    cues_found: tuple[str, ...] = ()
    span_class_signals: tuple[str, ...] = Field(min_length=1)
    """The `AnnotatedSpan.signal` of every span the candidate overlapped, so a reader can see
    the region was original content and by what signal it was classified so."""

    @model_validator(mode="after")
    def _a_clearance_with_cues_in_it_is_not_a_clearance(self) -> Self:
        if self.cues_found:
            raise ValueError(
                f"clause clearance records cues {list(self.cues_found)}; a span whose clause "
                "carries a negation, quotation, hypothetical or interrogative cue does not "
                "produce a source-stated edge. Downgrade it to an inferred relation with "
                "the cue recorded, or emit nothing"
            )
        if self.language != "en":
            raise ValueError(
                f"clause clearance is in {self.language!r}; the cue sets are English, and a "
                "clause in another language clears because the recogniser does not speak it "
                "rather than because it is free of cues"
            )
        return self


class StatedAssertionCheck(Frozen):
    """The four gates a `obs.said.*` edge passes, each carrying its own evidence.

    Booleans would be cheaper and would be worth nothing: a builder that sets four `True`s
    has passed nothing, and the model could not tell. Each gate therefore arrives as the
    artifact that proves it - the matched span, the resolution with its candidate set, the
    scanned clause with its cue list, the asserting node's id - and the validators below
    check them against each other rather than accepting a claim.
    """

    span: Span
    target: TargetResolution
    clearance: ClauseClearance
    asserted_by: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def _the_gates_are_about_the_same_span(self) -> Self:
        if self.span.text not in self.clearance.clause:
            raise ValueError(
                "the cleared clause does not contain the span it is supposed to be the "
                "clause of; a clearance computed over other text clears nothing"
            )
        if self.target.referring_text not in self.span.text:
            raise ValueError(
                "the referring text is not inside the span; the words that do the pointing "
                "must be words the span actually preserved. The two values are not echoed "
                "here: both are verbatim runs of message body, and a validation report that "
                "quotes them puts mail into an error string (R-SEC-043)"
            )
        if not self.target.unique:
            raise ValueError(
                f"the span identifies the relationship but not its target: "
                f"{len(self.target.considered)} candidates were in scope and none was "
                "uniquely identified. A source-stated edge names one node; the honest "
                "alternatives are an inferred relation with the ambiguity recorded, or no "
                "edge"
            )
        return self


class EvidenceEdge(Frozen):
    """One relation between two nodes, with everything a reader needs to discount it."""

    edge_id: str = Field(min_length=1, max_length=256)
    source: str = Field(min_length=1, max_length=256)
    target: str = Field(min_length=1, max_length=256)
    relation: Relation
    support: tuple[SourceReference, ...] = Field(min_length=1)
    """Every reference that was read to assert this, **including both endpoints**.

    Endpoints are in `support` rather than being looked up in the graph so the permission
    rule is decidable from the edge alone: an edge is a thing that gets serialised, cached
    and passed around, and a rule that needs a second object to evaluate is a rule that gets
    evaluated in one place and skipped in the next.
    """

    spans: tuple[Span, ...] = ()
    stated: StatedAssertionCheck | None = None
    confidence: Confidence | None = None
    method: DerivationMethod
    requires: tuple[PermissionRequirement, ...] = Field(min_length=1)
    """**A conjunction of per-source requirements, and never a union** (owner decision on
    R-M1-016). One entry per `(connector, principal)` the edge rests on; all must hold.

    This was a single `PermissionContext`, and `PermissionContext.covers` is false across
    connectors, so a Gmail-to-Drive edge was unconstructible - the schema could not express
    the thing v1 exists to do. It is derived from `support` by `requirements_of`, and the
    validator below re-derives it and refuses a mismatch, so a builder cannot understate what
    an edge needs.

    Holding a requirement is **not** permission to serve. `orivra.contracts.permission.release`
    is the only function that decides that, and it takes a live probe.
    """

    freshness: FreshnessStatus

    # -- what the relation fixes, rather than what a builder may claim -------------------

    @property
    def origin(self) -> EdgeOrigin:
        """Read off the relation. Not a field, and so not something a builder can set."""
        return self.relation.origin

    @property
    def assertion(self) -> Assertion:
        """Read off the relation. Not a field, and so not something a builder can set."""
        return self.relation.assertion

    @property
    def recomputable(self) -> bool:
        """Inferred edges are recomputable; observed ones are facts of the source.

        Also read off the relation. An observed edge marked recomputable would invite a
        cache to rebuild a source fact from a model.
        """
        return self.origin is EdgeOrigin.INFERRED

    @property
    def cache_identity(self) -> str:
        """A digest over the whole conjunction, for a cache key. **Never authority.**

        Two reads under the same grants are the same read, which is what a cache key needs to
        know. Whether *this* caller may see the result now is a different question, asked of
        `permission.release` against a live probe, and answered "no" for a file that was
        unshared five minutes ago under an unchanged grant.
        """
        return requirement_digest(self.requires)

    @property
    def connectors(self) -> tuple[ConnectorId, ...]:
        """Every source this edge rests on, in requirement order. A cross-source edge names
        more than one, which is the case the first design could not represent at all."""
        return tuple(one.connector for one in self.requires)

    @property
    def asserted_by(self) -> str | None:
        """Who said it - source-stated edges only, and never absent on one."""
        return None if self.stated is None else self.stated.asserted_by

    # -- validators ---------------------------------------------------------------------

    @model_validator(mode="after")
    def _an_edge_joins_two_different_nodes(self) -> Self:
        if self.source == self.target:
            raise ValueError(
                f"edge {self.relation.value} joins {self.source!r} to itself; a self-edge "
                "states a relation between one node and one node, which is a property and "
                "not a relation"
            )
        return self

    @model_validator(mode="after")
    def _an_inferred_relation_quotes_and_scores_and_an_observed_one_does_not(self) -> Self:
        if self.origin is EdgeOrigin.INFERRED:
            if not self.spans:
                raise ValueError(
                    f"inferred relation {self.relation.value} carries no spans; an inference "
                    "with nothing quoted behind it is an assertion a reader cannot check"
                )
            if self.confidence is None:
                raise ValueError(
                    f"inferred relation {self.relation.value} carries no confidence; the "
                    "difference between an inference and a fact is that the inference says "
                    "how strongly it is held"
                )
            return self
        if self.confidence is not None:
            raise ValueError(
                f"observed relation {self.relation.value} carries a confidence; a fact of "
                "the source scored like an inference reads as an inference that was "
                "promoted, and no rule promotes one"
            )
        return self

    @model_validator(mode="after")
    def _a_source_stated_assertion_arrives_with_its_four_gates(self) -> Self:
        """Rules 1-4 of §4.5, refused rather than warned about."""
        if self.assertion is Assertion.SOURCE_STATED:
            if self.stated is None:
                raise ValueError(
                    f"{self.relation.value} is a claim a human made in content, and it "
                    "arrives with no StatedAssertionCheck: no matched span, no identified "
                    "target, no cleared clause and nobody named as having said it. A span "
                    "matching the source proves the text exists; it does not prove the "
                    "relationship is correct"
                )
            if self.stated.target.resolved_to != self.target:
                raise ValueError(
                    f"the span resolves to {self.stated.target.resolved_to!r} and the edge "
                    f"points at {self.target!r}; an edge aimed somewhere other than where "
                    "its own evidence points is the failure the target rule exists to catch"
                )
            if self.stated.span not in self.spans:
                raise ValueError(
                    "the checked span is not among the edge's spans; the quotation a reader "
                    "is shown must be the quotation the gates were run over"
                )
            if self.stated.asserted_by not in {self.source, self.target}:
                raise ValueError(
                    f"asserted_by {self.stated.asserted_by!r} is neither endpoint; the "
                    "asserting node is the one whose content carries the span"
                )
            return self
        if self.stated is not None:
            raise ValueError(
                f"{self.relation.value} is a {self.assertion.value} relation and carries a "
                "source-stated check; running the stated-assertion gates over a metadata "
                "fact or an inference labels it as something a human said"
            )
        if self.assertion is Assertion.METADATA and self.spans:
            raise ValueError(
                f"metadata relation {self.relation.value} carries spans; a header field or "
                "a revision chain is not quoted from content, and attaching a quotation to "
                "one invites a reader to check the fact against text that did not produce it"
            )
        return self

    @model_validator(mode="after")
    def _the_conjunction_is_the_one_its_own_support_produces(self) -> Self:
        """The edge-visibility rule of plan §4.2, in the form the owner settled.

        Both endpoints **and every supporting reference**, each accounted for by a
        requirement the edge carries. An edge whose assertion rests on a third document the
        caller cannot read is not emittable even when both endpoints are readable, because
        the edge would disclose what that document says.

        `requires` is **re-derived here and compared**, not accepted. A builder that typed a
        narrower conjunction than its own support implies would be a builder that understated
        what the edge needs, and understating it is how a Drive requirement quietly stops
        being asked about.

        What this validator does **not** do is decide whether the edge may be served. That is
        `permission.release`, against a live probe, and the two are kept apart deliberately:
        this one is about what the edge rests on, which is fixed at construction; that one is
        about what the caller can see, which is a question about now.
        """
        by_node = {reference.node_id: reference for reference in self.support}
        for role, node_id in (("source", self.source), ("target", self.target)):
            if node_id not in by_node:
                raise ValueError(
                    f"the {role} endpoint {node_id!r} is not among the edge's supporting "
                    "references; endpoints are carried in support so the requirement set is "
                    "decidable from the edge alone"
                )
        derived = requirements_of(self.support)
        if tuple(sorted(one.hash for one in derived)) != tuple(
            sorted(one.hash for one in self.requires)
        ):
            raise ValueError(
                "the edge's permission conjunction is not the one its own support produces. "
                "It is derived from the references the edge rests on, and a conjunction "
                "narrower than that understates what a caller must hold - which is how a "
                "second source's requirement stops being asked about"
            )
        covered = {node for one in self.requires for node in one.applies_to}
        missing = sorted({reference.node_id for reference in self.support} - covered)
        if missing:
            raise ValueError(
                f"{len(missing)} supporting reference(s) are covered by no requirement; "
                "every reference an edge rests on is somebody's to authorise"
            )
        return self

    @model_validator(mode="after")
    def _an_unservable_edge_is_not_an_edge(self) -> Self:
        if not self.freshness.servable:
            raise ValueError(
                f"edge freshness is {self.freshness.state.value!r}; a relation whose "
                "verification failed is withheld with an OmissionRecord, not served with a "
                "caveat"
            )
        return self

    @model_validator(mode="after")
    def _every_span_belongs_to_an_endpoint(self) -> Self:
        endpoints = {self.source, self.target}
        for span in self.spans:
            if span.node_id not in endpoints:
                raise ValueError(
                    f"span quotes {span.node_id!r}, which is neither endpoint of this edge; "
                    "a quotation from a third node is support and belongs in support, not "
                    "in the edge's own quotations"
                )
        return self


__all__ = [
    "ClauseClearance",
    "Confidence",
    "EvidenceEdge",
    "StatedAssertionCheck",
    "TargetResolution",
]
