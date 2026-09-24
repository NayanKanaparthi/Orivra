"""`Redacted[str]`: redaction as a type, which is what makes the error path safe (AD A.11).

**Why a newtype and not a filter.** A filter runs where somebody remembered to call it. The
place mail-derived text reaches a log is almost never the place somebody remembered: it is
an exception's `repr`, a `f"{value}"` inside an error message, a `logging` call three frames
up from the code that knew the value was sensitive. SEC-06 asks that the *error path* be
clean, and a filter cannot promise that because the error path is exactly where filters are
not called.

So every mail-derived string in the process is carried in a `Redacted[str]` whose `__str__`
and `__repr__` render `<redacted:len=N:sha8=...>` under the personal profile. Exception
formatting goes through `__repr__`. An f-string goes through `__str__`. A `json.dumps` of a
model holding one goes through its serialiser. There is no formatting path that renders the
value, so there is no formatting path that leaks it.

**What survives redaction, and why those two.** The length and an eight-hex-character digest
of the value. Both are needed for the one thing traces are for - telling whether two records
are about the same string without knowing what the string is - and neither reconstructs it.
The digest is salted per process, so two runs of the same mailbox do not produce a stable
rainbow-table key for a short value like an address.
"""

from __future__ import annotations

import hashlib
import secrets
from enum import StrEnum
from typing import Any, Final

#: Per-process salt for the short digest. Regenerated on every start, so a digest is a
#: within-trace join key and never a stable identifier for a value across runs - which a
#: short unsalted digest of an address would be.
_SALT: Final[bytes] = secrets.token_bytes(16)

#: How many hex characters of the digest appear. Eight is enough to join two fields of one
#: trace and far too few to search a keyspace against.
DIGEST_CHARS: Final[int] = 8


class RedactionPolicy(StrEnum):
    """Which of AD A.11's two trace types this process emits. A **first-class field**.

    D.10 requires the policy be recorded in the trace rather than inferred from what the
    trace happens to contain. A reader who has to deduce "this looks redacted" from absent
    fields cannot tell a redacted trace from a trace of a query that found nothing.
    """

    #: SN §4.3's default and the one this server uses against a real mailbox: no snippets,
    #: no subjects, no header values, no display names, no addresses, no raw query strings.
    PERSONAL = "personal"
    #: The synthetic seed account. Mail content there is invented by the harness, so the
    #: type policy permits it; it is still never the default and never the personal profile.
    SEED = "seed"
    #: A.3's narrow gated escape hatch: `--diagnose=<finding-id>`, code-applied redaction,
    #: output under `traces/personal/diagnose/<finding-id>/`, and the flag value recorded in
    #: the trace so its use is self-documenting.
    DIAGNOSE = "diagnose"


class Redacted:
    """A mail-derived string that cannot be rendered.

    Construct it around anything that came from a mailbox. Nothing about the value reaches a
    formatting path: `__str__`, `__repr__`, `__format__` and the JSON serialiser all render
    the same placeholder. `reveal()` is the single, greppable way back to the value, and it
    exists because the *product* has to put mail text on the wire - fenced, labelled and
    inside an envelope - even though the *trace* never may.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    # -- the formatting paths, all four of them ------------------------------------------

    def __str__(self) -> str:
        return self.placeholder

    def __repr__(self) -> str:
        return self.placeholder

    def __format__(self, _spec: str) -> str:
        # Without this, `f"{value:>20}"` would fall back to `str` for an empty spec and
        # raise for a non-empty one - and a padded field in a log line is exactly the shape
        # that would have leaked. One placeholder, whatever the spec asks for.
        return self.placeholder

    @property
    def placeholder(self) -> str:
        return f"<redacted:len={len(self._value)}:sha8={self.digest}>"

    @property
    def digest(self) -> str:
        """A salted short digest: a join key within one trace, not an identifier across runs."""
        return hashlib.sha256(_SALT + self._value.encode("utf-8")).hexdigest()[:DIGEST_CHARS]

    def reveal(self) -> str:
        """The value. **The only way to it, and it is named so a sweep can find every caller.**

        A trace must never call this. The response layer must, because a fenced body is mail
        text by design. Keeping it to one method with an unmistakable name is what makes
        "who renders mail text?" a question `grep` answers.
        """
        return self._value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Redacted) and other._value == self._value

    def __hash__(self) -> int:
        return hash(self._value)


def redact(value: str | None) -> Redacted | None:
    """Wrap a mail-derived string, passing `None` through unchanged."""
    return None if value is None else Redacted(value)


def query_features(query: str) -> dict[str, Any]:
    """What a trace may say about a query: shape, never text (A.11, SN §4.3).

    "No raw query strings" is the rule, and the substitute is features plus a salted hash.
    Every number here is a property of the string's shape - how long it is, how many tokens,
    whether it carries operators or quotes - and none of them narrows the keyspace to
    anything a reader could invert.
    """
    tokens = query.split()
    return {
        "chars": len(query),
        "tokens": len(tokens),
        "has_operator": any(":" in token for token in tokens),
        "has_phrase": '"' in query,
        "has_negation": any(token.startswith("-") for token in tokens),
        "hash": Redacted(query).digest,
    }


__all__ = ["DIGEST_CHARS", "Redacted", "RedactionPolicy", "query_features", "redact"]
