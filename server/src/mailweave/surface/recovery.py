"""The recovery chain: what a decline offers next, and the proof that following it ends.

**Round 29, R-MCP-033 requirements 4 and 5, the strong reading.** A refusal that hands back a
`retry_with` is making a promise: *do this instead and you will get further*. Round 28's first
diagnostic broke that promise in the simplest way possible - a search declined at
`max_hit_threads: 1` and offered `max_hit_threads: 1` back - and a client that trusted it would
have looped without end. So the chain is now a contract with four properties, each held by a
test rather than by intent:

  * **bounded** - a client following `retry_with` from any decline reaches a served response
    or a final refusal within `MAX_RECOVERY_STEPS` hops;
  * **monotonic** - every retry strictly reduces one *declared* limiting dimension, and the
    decline says which dimension and from what to what (`Narrowing`), so a reader can check
    the claim rather than take it;
  * **cycle-free** - no retry repeats arguments already attempted. This follows from
    monotonicity over finite dimensions, and is also enforced directly: a retry that would
    equal the failed call is never emitted;
  * **terminal** - when no smaller legal request can return evidence, the decline carries
    `retry_with: null` and says so. A final refusal is an answer; a misleading retry is not.

A `mailweave_get_messages` read joins the chain on one dimension, `view`: a `body_full` that
cannot be carried unabridged narrows to `body_clean`, and a `body_clean` that cannot either is
final (R-MCP-039). One hop; it does not lengthen the bound.

**The dimensions, in the order they are narrowed.** A search narrows `max_hit_threads`.
**From a refusal that says what it was made of** (2026-09-15, R-M2-095: `RefusalCause`), the
retry is the *widest* narrower width at which the ladder's own arithmetic says the same search
fits - the ladder was asked, at every narrower width, over the same retrieval - so the caller
keeps as much of the scope as fits and the threads beyond it are withheld groups with their
map calls, not gone. When no width fits, narrowing is not offered at all: the next hop changes
*tool* to a `mailweave_thread_map` of the highest-ranked hit thread, and the decline says that
this is a **change of scope** - the other hit-bearing threads the search retrieved are not in
that map - rather than a narrower form of the same call (`NarrowingKind`). Without a cause -
the pure schedule, and the render backstop - a search narrows by halving from whatever was
applied down to 1 (12 → 6 → 3 → 1) and then changes tool, as before. A map is served as a page
sized to fit (navigation redesign, 2026-09-14), so it is the smallest map there is: a map that
still does not fit is a thread whose inventory alone exceeds the cap - the declared limit - and
the decline is final. The chain named AD E.2's `segment: 0` here until the independent review
of 2026-09-14 found a segment map of a long thread declines terminally (R-M2-081, R-M2-085); it
names no segment now.

**Neither kind of retry is a continuation.** A continuation (`continuations[]`) rides on a
*served* response and asks for the rest of the same result; a retry rides on a *decline* and
asks for something smaller (narrower) or something else (a scope change). The chain never
presents one as the other.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from mailweave.constants import MAX_HIT_THREADS, MAX_MESSAGE_IDS_PER_RETRY
from mailweave.disclosure.ladder import RefusalCause
from mailweave.envelope.vocab import Depth, ToolName
from mailweave.envelope.wire import Affordance


def halvings_to_one(applied: int) -> int:
    """How many strict halvings take `applied` down to 1. Zero when it already is."""
    steps = 0
    while applied > 1:
        applied = max(1, applied // 2)
        steps += 1
    return steps


#: The longest chain each tool can produce, **derived from its schedule**:
#:   * a search narrows `max_hit_threads` from the published width to 1, then changes tool.
#:     Every hop is a strict reduction, and a cause-directed hop reduces by as little as one
#:     (the widest width that fits), so the longest chain is one hop per width below the
#:     published figure plus the tool change; the pure halving schedule is shorter
#:     (`SEARCH_HALVING_STEPS`) and is a case of it;
#:   * a read of named messages narrows `view` once (`body_full` -> `body_clean`), cuts its id
#:     list to `MAX_MESSAGE_IDS_PER_RETRY` if it was longer, then halves it to 1;
#:   * a thread map has nowhere narrower to go: it is already the page that fits.
#: `MAX_RECOVERY_STEPS` is the largest of the three. Each is held tight by a test that follows
#: its schedule and requires exactly this many hops, so a bound that is merely safe fails.
SEARCH_HALVING_STEPS: Final[int] = halvings_to_one(MAX_HIT_THREADS) + 1
SEARCH_CHAIN_STEPS: Final[int] = (MAX_HIT_THREADS - 1) + 1
GET_MESSAGES_CHAIN_STEPS: Final[int] = 1 + 1 + halvings_to_one(MAX_MESSAGE_IDS_PER_RETRY)
THREAD_MAP_CHAIN_STEPS: Final[int] = 0

#: The most `retry_with` hops a client can be asked to follow from any decline before it holds
#: either a served response or a final refusal. Twelve, for the published figures: a search
#: whose every cause-directed hop reduces the width by one, from 12 to 1, and then maps
#: (the read chain is seven: one `view` hop, one cut to fifty, five halvings). In practice a
#: cause-directed chain is two hops - the decline, then the width the ladder said fits - and
#: the bound is what holds if the ladder's answer at a narrower width were ever wrong.
MAX_RECOVERY_STEPS: Final[int] = max(
    SEARCH_CHAIN_STEPS, GET_MESSAGES_CHAIN_STEPS, THREAD_MAP_CHAIN_STEPS
)


class NarrowingKind(StrEnum):
    """What a retry is, relative to the call that failed (R-M2-095).

    A **narrower** retry is the failed call with one dimension reduced: what it leaves out is
    accounted for on the response it returns (a width cap's groups carry their map calls).
    A **scope change** is a different call over part of the failed call's scope - a map of one
    thread where a search of many was refused - and what it leaves out is not accounted for
    on its response at all, which is why the decline says so.
    """

    NARROWER = "narrower"
    SCOPE_CHANGE = "scope_change"


@dataclass(frozen=True)
class Narrowing:
    """The one dimension a retry reduces, stated so the reduction can be checked.

    `proposed` is strictly narrower than `applied` on `dimension`: a smaller integer, or a
    change of tool from a search to a single thread's map. It travels on the decline beside
    `retry_with`, so requirement 5's "every retry reduces a declared limiting dimension" is
    declared on the wire rather than asserted in a docstring.
    """

    dimension: str
    applied: Any
    proposed: Any
    kind: NarrowingKind = NarrowingKind.NARROWER

    def as_json(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "applied": self.applied,
            "proposed": self.proposed,
            "kind": self.kind.value,
        }


@dataclass(frozen=True)
class Recovery:
    affordance: Affordance
    narrowing: Narrowing
    #: Why this dimension, in one sentence for the decline's remediation. Empty for the pure
    #: schedule, whose reason is the schedule.
    why: str = ""


def widest_width_that_fits(cause: RefusalCause, *, below: int) -> int | None:
    """The widest `max_hit_threads` under `below` at which the ladder said the search fits.

    Read off `cause.fits_at`, which the ladder filled by running itself at every narrower
    width; `None` when it refused at every one, or when the cause carries no table (an
    expansion, or a search already at width 1).
    """
    fitting = [
        width for width, cost in cause.fits_at.items() if width < below and cost <= cause.cap
    ]
    return max(fitting) if fitting else None


def applied_hit_threads(arguments: Mapping[str, Any]) -> int:
    """The `max_hit_threads` the server applied to this request - the caller's, clamped.

    Computed from the arguments by the same rule `apply_floor` uses (lowering only, never
    raising), so the decline and the service agree about what was applied without the decline
    having to reach into the service. A request that said nothing was served at the published
    figure.
    """
    budget = arguments.get("budget")
    requested = budget.get("max_hit_threads") if isinstance(budget, Mapping) else None
    if isinstance(requested, bool) or not isinstance(requested, int) or requested < 1:
        return MAX_HIT_THREADS
    return min(requested, MAX_HIT_THREADS)


def narrower_call(
    name: str,
    arguments: Mapping[str, Any],
    *,
    top_thread: str | None,
    hit_threads: int | None = None,
    segmented: bool | None = None,
    cause: RefusalCause | None = None,
) -> Recovery | None:
    """The retry a decline may offer, or `None` when the chain has ended.

    **Every argument the caller sent travels unchanged except the one being narrowed**
    (R-V01-009). The first version rebuilt the retry from the query and the narrowed key
    alone, so a caller's `max_disclosed_tokens`, `view`, `scan`, `relax` and every other
    budget key were silently dropped - the decline declared one reduction while the retry
    widened everything else. A retry is the failed call with one dimension reduced, and it is
    built by copying the failed call and changing that dimension.

    `top_thread` is the highest-ranked hit-bearing thread the failed call retrieved, if any;
    it is what the search-to-map hop names. `hit_threads` is how many hit-bearing threads it
    actually mapped: **the dimension narrowed is the width in effect, not the width allowed**.
    A search of a mailbox with one matching thread runs at an effective width of 1 whatever
    `max_hit_threads` says, and halving the cap from 12 to 1 changes nothing about what it
    returns (requirement 5: a retry must reduce a dimension that is *limiting*). `segmented`
    says whether the failed thread map's thread has segments at all; a `segment: 0` retry on a
    thread with no segments returns the same whole map and is not a narrowing (R-V01-010).

    `cause` (2026-09-15, R-M2-095) is what the ladder refused *for*, with its own answer at
    every narrower width. With it, a search retries at the **widest width that fits** - the
    least of the scope given up - and, when no width fits, goes straight to the map hop and
    says that is a change of scope; the halving below is the schedule without a cause.

    The guard at the bottom is the direct form of the cycle-free property: whatever the
    branches did, a retry equal to the failed call is not returned.
    """
    recovery: Recovery | None = None
    if name == ToolName.SEARCH.value and isinstance(arguments.get("query"), str):
        applied = applied_hit_threads(arguments)
        if hit_threads is not None and hit_threads >= 1:
            applied = min(applied, hit_threads)
        fit = None if cause is None else widest_width_that_fits(cause, below=applied)
        directed = cause is not None and (bool(cause.fits_at) or bool(cause.refused_at))
        if applied > 1 and (fit is not None or not directed):
            proposed = max(1, applied // 2) if fit is None else fit
            budget = dict(arguments.get("budget") or {})
            budget["max_hit_threads"] = proposed
            why = (
                ""
                if fit is None or cause is None
                else (
                    f"The retry narrows max_hit_threads to {proposed}, the widest width at "
                    f"which this ladder's own arithmetic fits the same search "
                    f"({cause.fits_at[proposed]} of {cause.cap} {cause.unit}); the "
                    f"{applied - proposed} hit-bearing thread(s) beyond it are withheld "
                    "groups on that response, each with its map call. Every other argument "
                    "of this call travels unchanged."
                )
            )
            recovery = Recovery(
                affordance=Affordance(tool=ToolName.SEARCH, args={**arguments, "budget": budget}),
                narrowing=Narrowing("max_hit_threads", applied, proposed),
                why=why,
            )
        elif top_thread is not None:
            why = ""
            if directed and cause is not None and applied > 1:
                why = (
                    f"No narrower width of this search fits: this ladder refuses it at every "
                    f"max_hit_threads from {applied - 1} down to 1 over the same retrieval. The "
                    f"retry maps {top_thread}, the highest-ranked hit thread, and that is a "
                    f"change of scope, not a narrower form of this search: the other "
                    f"{applied - 1} hit-bearing thread(s) this search retrieved are not in "
                    "that map and are not accounted for on it."
                )
            recovery = Recovery(
                affordance=Affordance(tool=ToolName.THREAD_MAP, args={"thread_id": top_thread}),
                narrowing=Narrowing(
                    "tool",
                    ToolName.SEARCH.value,
                    ToolName.THREAD_MAP.value,
                    kind=NarrowingKind.SCOPE_CHANGE,
                ),
                why=why,
            )
    elif name == ToolName.GET_MESSAGES.value and (
        isinstance(arguments.get("message_ids"), list)
        or isinstance(arguments.get("positions"), list)
    ):
        # **Both ways of naming the messages** (R-V01-010, recheck): a read by `map_id` plus
        # `positions` used to fall through every branch and be declared final at `body_full`
        # with the `view` hop never offered. The schedule is the same for both forms; only
        # the key that is halved differs.
        key = "message_ids" if isinstance(arguments.get("message_ids"), list) else "positions"
        ids = list(arguments[key])
        view = arguments.get("view")
        if view == Depth.BODY_FULL.value:
            # **R-MCP-039.** The one narrower legal read of the same messages is the cleaned
            # body, which drops quoted history and markup and is often the difference.
            recovery = Recovery(
                affordance=Affordance(
                    tool=ToolName.GET_MESSAGES,
                    args={**arguments, "view": Depth.BODY_CLEAN.value},
                ),
                narrowing=Narrowing("view", Depth.BODY_FULL.value, Depth.BODY_CLEAN.value),
            )
        elif len(ids) > 1:
            # **R-V01-010.** Twelve ids at `stub` used to be declared final when eleven
            # would have served. Read fewer at a time: the first half, in the caller's order,
            # so a client that wants the rest asks for the rest - and never more than
            # `MAX_MESSAGE_IDS_PER_RETRY`, so the chain is bounded whatever was named.
            kept = ids[: max(1, min(len(ids) // 2, MAX_MESSAGE_IDS_PER_RETRY))]
            recovery = Recovery(
                affordance=Affordance(tool=ToolName.GET_MESSAGES, args={**arguments, key: kept}),
                narrowing=Narrowing(key, len(ids), len(kept)),
            )
    # A thread map is already the page that fits (`disclosure.pages`); a map that does not
    # fit is one whose inventory alone exceeds the cap, and no narrower map exists. `segmented`
    # is accepted so the exception that carries it needs no change, and decides nothing.
    del segmented
    if recovery is not None and is_the_same_call(name, arguments, recovery.affordance):
        return None
    return recovery


def is_the_same_call(name: str, arguments: Mapping[str, Any], affordance: Affordance) -> bool:
    """Whether following `affordance` would repeat exactly the call that just failed."""
    return affordance.tool.value == name and dict(affordance.args) == dict(arguments)
