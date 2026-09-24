"""`Entity` and `EntityCandidate`: identity is deterministic; likeness is a candidate.

`structure/participants.py` settled this for one source: **identity is an address, never a
display name.** Plan §4.6 carries the rule across sources, and the carrying is where it gets
interesting - "Alex" in Slack and `alex@company.com` in Gmail are the same person often
enough that a system is tempted to decide, and wrong often enough that deciding is a defect.

So Orivra does not decide. Two entities merge only when a **deterministic key** is shared -
the same address appears as a Slack user's profile email and as a Gmail sender - or when a
source states the link explicitly. Everything else is an `EntityCandidate`: disclosed as a
likeness, never acted on. **A candidate never affects retrieval, ranking or edge
construction**, which is a property the graph builder has to honour and this module makes
statable: a candidate carries no edge and no score that anything downstream reads.
"""

from __future__ import annotations

import hashlib
from typing import Self

from pydantic import Field, model_validator

from orivra.contracts.edges import Confidence
from orivra.contracts.refs import Frozen, SourceReference
from orivra.contracts.vocab import CandidateBasis, CandidateStatus, ConnectorId


class DeterministicKey(Frozen):
    """A key two sources can independently produce for the same person, and agree.

    Gmail: the address. Slack: `(workspace, user_id)`, and the profile email when the token
    can read it. Drive: the `emailAddress` on a permission. Nothing else is a key - and in
    particular a display name is not, because two people share one constantly and one person
    changes theirs at will.
    """

    connector: ConnectorId
    kind: str = Field(min_length=1, max_length=32, pattern=r"^[a-z_]+$")
    value: str = Field(min_length=1, max_length=320)

    @model_validator(mode="after")
    def _a_key_is_normalised_where_the_source_says_it_may_be(self) -> Self:
        """Addresses fold case; opaque ids do not.

        An address is case-insensitive in its domain and, in practice for every provider
        Orivra reads, in its local part too - so `Alex@Company.com` and `alex@company.com`
        are one key. A Slack `user_id` is opaque and folding it would merge two accounts that
        differ only by case, which is a thing an opaque id space is entitled to do.
        """
        if self.kind == "address" and self.value != self.value.casefold():
            raise ValueError(
                "an address key is stored folded; two spellings of one address that hash "
                "differently are two identities for one person, which is the merge failure "
                "in reverse"
            )
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            f"{self.connector.value}\x1f{self.kind}\x1f{self.value}".encode()
        ).hexdigest()[:12]


class Entity(Frozen):
    """A confirmed identity: one or more deterministic keys that a source made equal."""

    entity_id: str = Field(min_length=1, max_length=256)
    keys: tuple[DeterministicKey, ...] = Field(min_length=1)
    display_names: tuple[str, ...] = ()
    """Untrusted, and **never a key**. Carried so a response can show a human-readable name
    beside an identity that was established some other way."""

    @model_validator(mode="after")
    def _the_entity_id_is_derived_from_its_keys(self) -> Self:
        """Derived, so two builders that saw the same keys produce the same entity.

        A builder-chosen id would make the identity depend on which query found the person
        first, and a cached graph would then disagree with a fresh one about who is who.
        """
        expected = (
            "entity/"
            + hashlib.sha256(
                "\x1e".join(sorted(key.digest for key in self.keys)).encode()
            ).hexdigest()[:16]
        )
        if self.entity_id != expected:
            raise ValueError(
                f"entity_id {self.entity_id!r} is not the digest of its keys ({expected!r}); "
                "an identity whose id depends on who built it disagrees with itself across "
                "two queries"
            )
        return self


class EntityCandidate(Frozen):
    """A likeness between two entities. **Never a merge** (plan §4.6).

    It is disclosed so an agent can see that "Alex in Slack" and `alex@company.com` might be
    one person *without Orivra having decided it*. Nothing downstream reads it: no edge is
    built from it, no ranking consults it, no retrieval widens because of it.
    """

    left: str = Field(min_length=1, max_length=256)
    right: str = Field(min_length=1, max_length=256)
    basis: CandidateBasis
    evidence: tuple[SourceReference, ...] = Field(min_length=1)
    confidence: Confidence
    status: CandidateStatus = CandidateStatus.CANDIDATE

    @model_validator(mode="after")
    def _a_candidate_relates_two_different_entities(self) -> Self:
        if self.left == self.right:
            raise ValueError(
                "a candidate relates an entity to itself; that is not a likeness, and if "
                "the two ids really are one the merge already happened deterministically"
            )
        return self

    @model_validator(mode="after")
    def _only_a_source_confirms_a_candidate(self) -> Self:
        """`CONFIRMED_BY_SOURCE` requires the basis that a source actually stated it.

        A high-confidence display-name match is still a display-name match. Letting a score
        promote a candidate to confirmed is exactly the "no rule promotes an inferred
        relation to an observed one" rule, in the entity layer.
        """
        if (
            self.status is CandidateStatus.CONFIRMED_BY_SOURCE
            and self.basis is not CandidateBasis.EXPLICIT_LINK
        ):
            raise ValueError(
                f"a candidate on basis {self.basis.value!r} is marked confirmed_by_source; "
                "only a source stating the link explicitly confirms one, and no confidence "
                "promotes a likeness into an identity"
            )
        return self


__all__ = ["DeterministicKey", "Entity", "EntityCandidate"]
