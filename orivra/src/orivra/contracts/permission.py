"""What an edge requires of a caller: a **conjunction**, per source, never a union.

Owner decision on review finding R-M1-016, and it settles a question the first design got
wrong in a way that could not be patched: `EvidenceEdge` carried one `PermissionContext`, and
`PermissionContext.covers` is false whenever the connectors differ, so a Gmail-to-Drive edge
was unconstructible. Orivra v1's premise is evidence spanning three sources, so that was
execution disproving a stated premise rather than a bug.

**The shape, stated exactly.** An edge carries one `PermissionRequirement` per
`(connector, principal)` it rests on, and **all of them must hold**. Three things follow, and
each is the opposite of a shortcut somebody would otherwise take:

* **Not one synthetic context.** Collapsing three sources into a single context would need a
  scope vocabulary that spans them, and there is none - a Gmail scope and a Slack token kind
  are not comparable quantities. A synthetic context is a fabricated authority.
* **Not a union.** A union asks "does the caller hold any of these?", which is the question
  that lets Drive access stand in for Slack access. The conjunction asks "does the caller
  hold *every* one of these?", which is the only question whose answer is safe.
* **Within one source, a set of required scopes is still a conjunction.** All of them are
  needed; grouping them under one requirement is bookkeeping, not weakening.

**A hash is cache identity and never authority.** `PermissionRequirement.hash` and
`requirement_digest` may take part in a cache key, because two reads under the same grant are
the same read. Neither answers "may this caller see it now?", which is a question about the
present and is answered only by `release`, against a live check.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, Self

from pydantic import Field, model_validator

from orivra.contracts.refs import Frozen, PermissionContext, SourceReference
from orivra.contracts.vocab import ConnectorId


class PermissionRequirement(Frozen):
    """Everything one `(connector, principal)` must grant for an edge to be released.

    Derived from the references the edge rests on rather than declared beside them - a
    requirement a builder could type is a requirement a builder could understate.
    """

    connector: ConnectorId
    principal: str = Field(min_length=1, max_length=128)
    scope_set: tuple[str, ...] = Field(min_length=1)
    capability: tuple[str, ...] = ()
    applies_to: tuple[str, ...] = Field(min_length=1)
    """The node ids this requirement stands for. Kept so a refusal can be accounted for
    internally at the right granularity; **never published** - see `permission.py`'s rule
    that a refused edge discloses nothing about what it rested on."""

    @model_validator(mode="after")
    def _the_sets_are_canonical(self) -> Self:
        for name, values in (
            ("scope_set", self.scope_set),
            ("capability", self.capability),
            ("applies_to", self.applies_to),
        ):
            if any(not value or value.strip() != value for value in values):
                raise ValueError(f"{name} carries an empty or untrimmed entry")
            if list(values) != sorted(set(values)):
                raise ValueError(
                    f"{name} must be sorted and de-duplicated: it is a digest input, and two "
                    "requirements that differ only in order are one requirement"
                )
        return self

    @property
    def hash(self) -> str:
        """Stable identity for a cache key. **Not authority.** See the module docstring."""
        joined = "\x1f".join(
            (self.connector.value, self.principal, *self.scope_set, "|", *self.capability)
        )
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]

    def satisfied_by(self, held: PermissionContext) -> bool:
        """Whether a context the caller currently holds meets this requirement.

        A **necessary** condition and never a sufficient one: it compares what was granted,
        which is a fact about a consent screen, and says nothing about whether the items
        still exist or are still shared with this caller. `release` asks both questions.
        """
        return (
            held.connector is self.connector
            and held.principal == self.principal
            and set(self.scope_set) <= set(held.scope_set)
            and set(self.capability) <= set(held.capability)
        )


def requirements_of(references: Iterable[SourceReference]) -> tuple[PermissionRequirement, ...]:
    """The conjunction one set of references produces, grouped by `(connector, principal)`.

    Grouped rather than one-per-reference because that is the unit a live check can answer:
    an authorisation question is asked of a grant, and two Gmail messages read under one
    grant are one question. Sorted, so an edge built twice from the same references produces
    the same conjunction and the same cache identity.
    """
    grouped: dict[tuple[ConnectorId, str], dict[str, set[str]]] = {}
    for reference in references:
        key = (reference.connector, reference.permission.principal)
        bucket = grouped.setdefault(key, {"scopes": set(), "capability": set(), "nodes": set()})
        bucket["scopes"].update(reference.permission.scope_set)
        bucket["capability"].update(reference.permission.capability)
        bucket["nodes"].add(reference.node_id)
    return tuple(
        PermissionRequirement(
            connector=connector,
            principal=principal,
            scope_set=tuple(sorted(bucket["scopes"])),
            capability=tuple(sorted(bucket["capability"])),
            applies_to=tuple(sorted(bucket["nodes"])),
        )
        for (connector, principal), bucket in sorted(
            grouped.items(), key=lambda item: (item[0][0].value, item[0][1])
        )
    )


def requirement_digest(requirements: Sequence[PermissionRequirement]) -> str:
    """One digest over a whole conjunction, for a cache key. **Not authority.**"""
    return hashlib.sha256(
        "\x1e".join(sorted(one.hash for one in requirements)).encode("utf-8")
    ).hexdigest()[:12]


class AccessProbe(Protocol):
    """The live check. **Both questions, because they fail differently.**

    `authorizes` asks whether the caller's current grant meets a requirement - a fact about
    consent, which can be revoked or narrowed since the edge was built. `can_access` asks
    whether this caller can reach this item **now** - a fact about sharing and existence,
    which changes without any grant changing: a Drive file unshared, a Slack channel left, a
    message deleted. An edge released on the first alone would survive every one of those.
    """

    def authorizes(self, requirement: PermissionRequirement) -> bool: ...

    def can_access(self, reference: SourceReference) -> bool: ...


@dataclass(frozen=True)
class Release:
    """Whether an edge may be returned to this caller, and - internally only - why not.

    `refused_by` and `refused_reference` exist for the disposition ledger, which needs `H`
    complete and the certificate honest. **Neither is published**: naming the requirement
    that failed names the source, and naming the reference names the document. The published
    form is `permission_safe_omission`, which carries a connector and a cause and nothing
    else.
    """

    granted: bool
    refused_by: PermissionRequirement | None = None
    refused_reference: SourceReference | None = None

    @property
    def why_internal(self) -> str:
        if self.granted:
            return "every requirement holds and every reference is reachable"
        if self.refused_by is not None:
            return f"requirement {self.refused_by.connector.value}/{self.refused_by.hash} failed"
        if self.refused_reference is not None:
            return f"reference {self.refused_reference.node_id} is not currently reachable"
        return "refused"  # pragma: no cover - one of the two is always set


def release(
    requirements: Sequence[PermissionRequirement],
    references: Sequence[SourceReference],
    probe: AccessProbe,
) -> Release:
    """The gate. **An edge is returned only if every answer is yes.**

    Every requirement authorised, and every reference - both endpoints and all supporting
    evidence - currently reachable. The first failure short-circuits, because a caller who
    fails one requirement gets nothing either way and probing the rest spends calls on a
    question already settled.

    This is the only function in the repository that may decide an edge is releasable, and it
    takes a live probe rather than a stored hash. A stored hash answers "was this read under
    the same conditions?", which is a question about the past.
    """
    if not requirements:
        raise ValueError(
            "an edge with no permission requirements would be released to everyone; a "
            "conjunction over an empty set is vacuously true, which is the one arithmetic "
            "this gate must not inherit"
        )
    for requirement in requirements:
        if not probe.authorizes(requirement):
            return Release(granted=False, refused_by=requirement)
    for reference in references:
        if not probe.can_access(reference):
            return Release(granted=False, refused_reference=reference)
    return Release(granted=True)


__all__ = [
    "AccessProbe",
    "PermissionRequirement",
    "Release",
    "release",
    "requirement_digest",
    "requirements_of",
]
