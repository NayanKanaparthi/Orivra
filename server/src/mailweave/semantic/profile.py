"""The semantic rung's operating parameters, and where each one came from.

AD D.5 prices the pool at `threads.get(format=metadata)` = 40 u and builds pool text from
`subject + from/to addresses + Gmail snippet`. **PF-2 is blocking on whether that snippet
exists**, because the REST Format enum documents METADATA as returning "only email message
ID, labels, and email headers" and never mentions `snippet`. D.5 is explicit that a missing
snippet is *"a design change, not a cost change"*: with stage A's input reduced to subject
plus participants, SC §4's own worked example - query "postpone the launch", evidence
"We'll push go-live into Q4" - is invisible, and stage A degrades to a near-random
shortlist selector on exactly the family that justifies the rung.

## What this module does about a preflight that has not run

It does **not** assume the snippet is there.

D.5 names the primary fallback and says it is "the branch PF-2 should be expected to take":
`threads.get(format=full)` at the **same 40 u** (quota is per method, not per format), pool
text becomes `subject + participants + first 400 chars of cleaned body`, and
`max_pool_threads` drops **25 → 15** until PF-4/PF-4b measure the parse-and-embed cost.

So an un-run PF-2 selects that fallback, and the profile records that it was selected
**without measurement**. This is not a guess dressed as a default. The fallback depends on
no unverified fact - `format=full` returns bodies, which is what the branch needs - and it
is strictly weaker in bound (15 threads, not 25) and strictly stronger in text quality than
the snippet path. Choosing the safe branch and declaring the choice is the opposite of
picking a plausible number so a test goes green.

`Provenance` carries which it was, and `declaration()` renders the sentence T-RO1 requires
in **every** semantic response. A reduced bound that is not declared is the failure mode
T-RO1 exists to prevent: a caller cannot tell a small answer from a small search.

## Why the profile is a value and not module-level constants

`constants.py` holds the *design* values traceable to AD. The profile holds what this
process will actually do, which depends on records on disk. Keeping them apart is what lets
a test construct a measured profile without monkeypatching a `Final`, and what stops a
measured value from silently becoming the new design value without anyone editing AD.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final

from mailweave import constants


class PoolTextMode(StrEnum):
    """What stage A actually embeds, per D.5's branch table."""

    #: `subject + from/to addresses + Gmail snippet`, from `threads.get(format=metadata)`.
    #: Available only when PF-2 observed a per-message snippet.
    SNIPPET = "subject+participants+snippet"
    #: D.5's primary fallback: `threads.get(format=full)`, same 40 u, pool text is
    #: `subject + participants + first 400 chars of cleaned body`.
    BODY_HEAD = "subject+participants+body-head-400"
    #: The second fallback, only if PF-1 shows `threads.get(format=full)` itself truncates:
    #: bounded `messages.get(format=metadata)` per row at 20 u, pool hard-bounded to 60.
    METADATA_ROWS = "subject+participants+metadata-rows"


class Basis(StrEnum):
    MEASURED = "measured"
    ASSUMED = "assumed"


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a value came from, in the same shape the Orivra budget uses.

    `basis` is never inferred from whether a record happened to be present at import time;
    it is set by the loader that read the record, so a value can never claim to be measured
    because a file existed.
    """

    basis: Basis
    #: For MEASURED: the preflight record id, e.g. "PF-2-metadata-headers".
    #: For ASSUMED: the governing clause, e.g. "AD D.5 primary fallback".
    source: str
    #: For MEASURED: the run date. For ASSUMED: why this value rather than another.
    detail: str

    def __post_init__(self) -> None:
        if not self.source or not self.detail:
            raise ValueError("a provenance with no source or no detail explains nothing")


#: D.4a's body-head bound for pool text, per D.5's fallback branch.
POOL_BODY_HEAD_CHARS: Final[int] = 400

#: D.5: the reduced bound that travels with the `format=full` fallback until PF-4/PF-4b
#: measure the parse-and-embed cost. Marked [DESIGN] in AD, and declared per T-RO1.
FALLBACK_MAX_POOL_THREADS: Final[int] = 15

#: D.5's hard bound on the second fallback: 60 rows x 20 u = 1,200 u.
METADATA_ROWS_MAX_POOL_MESSAGES: Final[int] = 60


@dataclass(frozen=True, slots=True)
class SemanticProfile:
    """What this process will do, and what each parameter's warrant is."""

    pool_text_mode: PoolTextMode
    pool_text_provenance: Provenance
    max_pool_threads: int
    max_pool_messages: int
    max_rerank_pairs: int
    max_semantic_ms: int
    bounds_provenance: Provenance

    def __post_init__(self) -> None:
        for name in (
            "max_pool_threads",
            "max_pool_messages",
            "max_rerank_pairs",
            "max_semantic_ms",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive int, got {value!r}")
        if self.pool_text_mode is PoolTextMode.METADATA_ROWS and (
            self.max_pool_messages > METADATA_ROWS_MAX_POOL_MESSAGES
        ):
            raise ValueError(
                "the metadata-rows fallback is hard-bounded to "
                f"{METADATA_ROWS_MAX_POOL_MESSAGES} rows (1,200 u); "
                f"got {self.max_pool_messages}"
            )

    @property
    def measured(self) -> bool:
        """True only when *both* the branch and the bounds were measured.

        A profile whose branch was measured but whose bounds were assumed is not a measured
        profile, and calling it one is how an assumed number acquires a citation.
        """
        return (
            self.pool_text_provenance.basis is Basis.MEASURED
            and self.bounds_provenance.basis is Basis.MEASURED
        )

    def narrowed(self, *, max_threads: int | None, max_messages: int | None) -> SemanticProfile:
        """This profile with a caller's pool bounds applied. **Lowering only.**

        The same direction `max_hit_threads` and `max_disclosed_tokens` run in, and for the
        same reason: the declared bound is the *most* this server will read, so a caller
        asking for more gets the declared one and a caller asking for fewer gets what they
        asked for. A caller cannot widen the pool past a measurement, which is what would
        make `bounds_provenance.basis = measured` a false statement about the run that
        actually happened.

        **The provenance is rewritten when a value actually moves**, never when the caller's
        request was a no-op. A narrowed bound is no longer the measured one, and a
        declaration that went on citing PF-4 for a number PF-4 did not produce would be
        exactly the citation-for-an-unmeasured-value this module exists to prevent.
        """
        threads = min(max_threads, self.max_pool_threads) if max_threads else self.max_pool_threads
        messages = (
            min(max_messages, self.max_pool_messages) if max_messages else self.max_pool_messages
        )
        if threads == self.max_pool_threads and messages == self.max_pool_messages:
            return self
        moved = []
        if threads != self.max_pool_threads:
            moved.append(f"max_pool_threads {self.max_pool_threads}->{threads}")
        if messages != self.max_pool_messages:
            moved.append(f"max_pool_messages {self.max_pool_messages}->{messages}")
        return replace(
            self,
            max_pool_threads=threads,
            max_pool_messages=messages,
            bounds_provenance=Provenance(
                basis=Basis.ASSUMED,
                source="caller-supplied pool bounds",
                detail=(
                    "narrowed by the caller from "
                    f"{self.bounds_provenance.basis.value} ({self.bounds_provenance.source}): "
                    + ", ".join(moved)
                ),
            ),
        )

    def declaration(self) -> str:
        """The T-RO1 sentence. Appears in every semantic response, measured or not."""
        return (
            f"pool text: {self.pool_text_mode.value}; "
            f"max_pool_threads={self.max_pool_threads} "
            f"({self.pool_text_provenance.basis.value}, {self.pool_text_provenance.source}); "
            f"max_pool_messages={self.max_pool_messages}, "
            f"shortlist k={self.max_rerank_pairs} "
            f"({self.bounds_provenance.basis.value}, {self.bounds_provenance.source})"
        )


def unmeasured_profile() -> SemanticProfile:
    """D.5's primary fallback, taken deliberately because PF-2 has not run.

    Not a default in the sense `constants.py`'s docstring warns about. The values are the
    ones AD names for this branch, and the profile says out loud that nobody measured them.
    """
    return SemanticProfile(
        pool_text_mode=PoolTextMode.BODY_HEAD,
        pool_text_provenance=Provenance(
            basis=Basis.ASSUMED,
            source="AD D.5 primary fallback",
            detail=(
                "PF-2 has not run, so the presence of a per-message snippet under "
                "format=metadata is unverified; threads.get(format=full) needs no such "
                "fact and costs the same 40 u"
            ),
        ),
        max_pool_threads=FALLBACK_MAX_POOL_THREADS,
        max_pool_messages=constants.MAX_POOL_MESSAGES,
        max_rerank_pairs=constants.MAX_RERANK_PAIRS,
        max_semantic_ms=constants.MAX_SEMANTIC_MS,
        bounds_provenance=Provenance(
            basis=Basis.ASSUMED,
            source="AD D.5 [DESIGN] / constants.py",
            detail=(
                "PF-4 has not run, so max_semantic_ms, max_pool_messages and "
                "max_rerank_pairs are the uncalibrated design values and "
                "max_pool_threads carries D.5's reduced 25->15 fallback bound"
            ),
        ),
    )
