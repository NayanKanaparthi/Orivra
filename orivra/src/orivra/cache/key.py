"""The cache key: every dimension that can change an entry's meaning, and none that cannot.

Plan §5.4, implemented rather than paraphrased:

    CacheKey = (principal, connector, native_id, content_version, permission_hash,
                model_id@revision | None, extraction_schema_version, redaction_policy, kind)

**No dimension is optional**, and each is there because its absence is a specific way to serve
the wrong thing:

* `principal` - two users of one machine never share an entry.
* `content_version` - a vector computed over revision 6 is not an answer about revision 7.
* `permission_hash` - an entry written under one access state is not readable under another.
  Note what this does **not** do, which §5.3 is emphatic about: a matching hash proves the
  entry *was written* under that state, not that the state still holds. The key never
  authorises a serve; `revalidate` does, against a live probe.
* `model_id@revision` - a model upgrade must not read old vectors, and `None` is a real value
  for kinds no model touched rather than a missing one.
* `extraction_schema_version` and `redaction_policy` - the same bytes, read by a different
  schema or redacted by a different policy, mean different things.
* `kind` - so a vector and a structure entry for one message cannot collide.

The tuple is stored beside its hash because a key you cannot read back is a key nobody can
audit, and the first question after a wrong serve is always "what was this keyed on".
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final


class CacheKind(StrEnum):
    """What an entry holds. Plan §5.1's cached category, and nothing outside it.

    Message and document **text is not here and cannot be**, which is §5.1's rule: v1 avoids
    the encrypted-index question by not persisting text at all. `OBSERVED_EDGE` is safe
    because an observed edge is a relation between two ids and carries no body; an *inferred*
    edge is deliberately absent, being recomputable and cheap.
    """

    VECTOR = "vector"
    METADATA = "metadata"
    STRUCTURE = "structure"
    OBSERVED_EDGE = "observed_edge"
    ENTITY_CANDIDATE = "entity_candidate"
    NEGATIVE = "negative"


@dataclass(frozen=True)
class CacheKey:
    """One entry's full identity, hashed, with the tuple kept for audit."""

    principal: str
    connector: str
    native_id: str
    content_version: str
    permission_hash: str
    extraction_schema_version: str
    redaction_policy: str
    kind: CacheKind
    #: `None` is a value, not an absence: it means no model was involved in producing this
    #: entry, which is true of structure and metadata and false of a vector.
    model_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "principal",
            "connector",
            "native_id",
            "content_version",
            "permission_hash",
            "extraction_schema_version",
            "redaction_policy",
        ):
            if not getattr(self, name):
                raise ValueError(
                    f"cache key dimension {name!r} is empty. No dimension is optional (plan "
                    "§5.4): an entry keyed on fewer dimensions than can change its meaning is "
                    "an entry that will be served for a question it does not answer"
                )
        if self.kind is CacheKind.VECTOR and self.model_id is None:
            raise ValueError(
                "a vector entry with no model_id would be read back after a model upgrade as "
                "though the new model had produced it"
            )

    @property
    def tuple_form(self) -> dict[str, Any]:
        return {
            "principal": self.principal,
            "connector": self.connector,
            "native_id": self.native_id,
            "content_version": self.content_version,
            "permission_hash": self.permission_hash,
            "model_id": self.model_id,
            "extraction_schema_version": self.extraction_schema_version,
            "redaction_policy": self.redaction_policy,
            "kind": self.kind.value,
        }

    @property
    def hash(self) -> str:
        return hashlib.sha256(json.dumps(self.tuple_form, sort_keys=True).encode()).hexdigest()


#: The version of the shape this codebase extracts a response into - nodes, edges, depths,
#: reasons. A cached structure entry is a claim in *this* vocabulary, so a change to it must
#: not read back old entries as though the new extractor had produced them. Bumped by hand,
#: deliberately: a value derived from a file digest would move on a comment edit and throw the
#: cache away for a change that did not alter a single field.
EXTRACTION_SCHEMA_VERSION: Final[str] = "orivra/evidence-graph@1"


def structure_key(
    *,
    principal: str,
    connector: str,
    native_id: str,
    revision: str,
    permission_hash: str,
    redaction_policy: str,
) -> CacheKey:
    """The key for one container's structure, with every §5.4 dimension supplied.

    A named builder rather than nine keyword arguments at each call site, because the failure
    this guards against is a call site that quietly stops passing one of them - and a key with
    a dimension missing is a key that will be served for a question it does not answer. The
    `__post_init__` refuses an empty string; this refuses the omission a default would hide.
    """
    return CacheKey(
        principal=principal,
        connector=connector,
        native_id=native_id,
        content_version=revision,
        permission_hash=permission_hash,
        extraction_schema_version=EXTRACTION_SCHEMA_VERSION,
        redaction_policy=redaction_policy,
        kind=CacheKind.STRUCTURE,
        model_id=None,
    )


__all__ = ["EXTRACTION_SCHEMA_VERSION", "CacheKey", "CacheKind", "structure_key"]
