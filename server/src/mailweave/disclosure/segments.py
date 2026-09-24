"""The segment map: AD §E.2's **experimental** second navigational level (DISC-05).

**Experimental means three things here, and all three are executable.** It is built; it is
labelled; and it is removable in one edit because nothing else in the package depends on it
- `segment_of` returns `None` for every thread below the boundary, and a `None` segment
simply does not appear in a collapsed run's affordance arguments.

`ARCHITECTURE_DECISION.md` §E.2 names the gate that decides it: **DISC-05**, measured by
`EVALUATION_PLAN.md` §7.5.1's depth arm (PD-DEPTH-N1 vs PD-DEPTH-N at the PF-6 token
boundary), published at CG-PD. If the depth-*n* versus depth-*n−1* comparison shows no win,
large threads get declared truncation plus an affordance and this module is deleted. That is
this criterion's own remedy and it is not a scope reduction.

**Neither number in this module is invented.**

* The size boundary is *derived*: a flat map costs `STUB_ROW_TOKEN_ESTIMATE` per message,
  and it stops fitting when that exceeds the normal ceiling. So the boundary is
  `NORMAL_CEILING_TOKENS // STUB_ROW_TOKEN_ESTIMATE`, computed from two published figures
  rather than chosen. PF-6 sets both of those figures from the measured host cap, so the
  boundary moves with them instead of having to be re-registered.
* The temporal discontinuity that ends a segment is `E4_TEMPORAL_PROXIMITY_SECONDS` - the
  same published day the E4 fill uses, reused rather than duplicated, for the same reason:
  a day is the finest interval Gmail's own date operators can express (AD A.6).

**Temporal, not arithmetic.** AD A.9(6) puts segmentation under E3 - *temporal*
segmentation - so a segment ends where the conversation paused, never every N messages. A
thread with no pause is one segment however long it is, which is the honest answer: there is
no second navigational level to offer over a conversation that never stopped.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from mailweave.constants import NORMAL_CEILING_TOKENS
from mailweave.disclosure.weights import E4_TEMPORAL_PROXIMITY_SECONDS
from mailweave.envelope.measure import STUB_ROW_TOKEN_ESTIMATE

#: `True` while §E.2 lists this level as experimental. Read by the response builder so the
#: label travels with the feature rather than living only in a document.
SEGMENT_MAP_IS_EXPERIMENTAL: Final[bool] = True

#: The thread length at and above which a flat map no longer fits the normal ceiling.
#: Derived, not registered: see the module docstring.
FLAT_MAP_MESSAGE_BOUNDARY: Final[int] = NORMAL_CEILING_TOKENS // STUB_ROW_TOKEN_ESTIMATE


def segment_boundaries(
    order: Sequence[str], internal_dates: Mapping[str, int | None]
) -> tuple[int, ...]:
    """The 0-based positions at which a new temporal segment starts, `(0, ...)`.

    A message whose `internalDate` this response did not observe never starts a segment: a
    boundary drawn at an unknown time would be a claim about when the conversation paused,
    made out of an absence.
    """
    if not order:
        return ()
    starts = [0]
    previous: int | None = None
    for position, message_id in enumerate(order):
        stamp = internal_dates.get(message_id)
        if stamp is None:
            continue
        if previous is not None and (stamp - previous) >= E4_TEMPORAL_PROXIMITY_SECONDS * 1000:
            starts.append(position)
        previous = stamp
    return tuple(sorted(set(starts)))


def segment_of(
    position: int,
    *,
    stated_total: int,
    order: Sequence[str],
    internal_dates: Mapping[str, int | None],
) -> int | None:
    """Which segment a thread position falls in, or `None` for a thread below the boundary.

    `None` is the depth-*n−1* answer - a flat map with declared truncation and an affordance
    - and it is what every thread gets until the thread is long enough for a flat map not to
    fit. That is the arm DISC-05 compares against, so the two levels are both reachable from
    one code path rather than one of them being hypothetical.
    """
    if stated_total < FLAT_MAP_MESSAGE_BOUNDARY:
        return None
    starts = segment_boundaries(order, internal_dates)
    if len(starts) < 2:
        return None
    index = 0
    for segment, start in enumerate(starts):
        if position >= start:
            index = segment
    return index
