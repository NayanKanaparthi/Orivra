"""One arrangement of the thread-granular withholdings, read by the estimate and the wire.

**Why one function** (R-M2-094, 2026-09-15). The ledger decided which `withheld_groups[]`
entries a response names and which fold into a `withheld_tail[]` count, and the disclosure
layout decided how many groups to *charge* - by a second arithmetic over two counts
(`grouped_threads`, `foldable_grouped_threads`) the producer seeded beside the ledger's own
cap notes. The two disagreed the first time the sets overlapped: a thread beyond
`max_hit_threads` that the semantic pool also never read was counted twice and counted as
foldable, while the ledger filed it under a pool cap that never folds. The wire named fifty
groups where the estimate charged twenty-four, and the response was refused at the host cap
for a size the ladder never saw.

So the arrangement is computed here, once, from the same inputs on both sides: the set of
`(thread, cap)` groups, the caps a tail recovery was filed for, and the naming bound. The
layout carries the groups as keys rather than as counts and asks this function how many it
will name; the ledger hands its groups to the same function and emits exactly what it
returns. There is no second formula to maintain.

**The rule is the ledger's rule, unchanged.** Every group under a cap with no widening call
is named, always: a count with no way out is not an omission record, it is a number. Past the
naming bound, foldable groups take the room the fixed ones leave and the rest fold into one
tail per cap, whose count is exact and whose affordance is the widening call the producer
filed. Within the named groups the wire order is the retrieval rank the producer supplied,
unranked threads after every ranked one, ties by thread id and then cap - so a client walking
the offers walks them best first, and two responses over one mailbox walk them the same way
(R-M2-096).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field

from mailweave.constants import MAX_WITHHELD_GROUPS_NAMED
from mailweave.envelope.vocab import WithheldCap

#: One thread-granular withholding: the thread and the cap that filed it. Two caps on one
#: thread are two groups, because they are two statements with two ways out.
GroupKey = tuple[str, WithheldCap]


def order_key(key: GroupKey, rank_of: Mapping[str, int] | None) -> tuple[int, int, str, str]:
    """Wire order: ranked threads by rank, then unranked threads, ties by thread id and cap."""
    thread_id, cap = key
    rank = None if rank_of is None else rank_of.get(thread_id)
    return (0 if rank is not None else 1, rank if rank is not None else 0, thread_id, cap.value)


@dataclass(frozen=True)
class GroupArrangement:
    """What the wire names and what it folds, in the order it will write them."""

    named: tuple[GroupKey, ...]
    #: `{cap: the groups its tail counts}`, in wire order within each cap; the tails
    #: themselves are written in cap-value order.
    folded: Mapping[WithheldCap, tuple[GroupKey, ...]] = field(default_factory=dict)

    @property
    def tails(self) -> tuple[WithheldCap, ...]:
        return tuple(sorted(self.folded, key=lambda cap: cap.value))

    @property
    def tail_count(self) -> int:
        return len(self.folded)


def arrange_groups(
    groups: Iterable[GroupKey],
    *,
    foldable: AbstractSet[WithheldCap],
    rank_of: Mapping[str, int] | None = None,
    bound: int = MAX_WITHHELD_GROUPS_NAMED,
) -> GroupArrangement:
    """Name and fold the groups. Pure; the same answer for the same inputs on either side."""
    keys = sorted(set(groups), key=lambda key: order_key(key, rank_of))
    if len(keys) <= bound:
        return GroupArrangement(named=tuple(keys))
    fixed = [key for key in keys if key[1] not in foldable]
    fold = [key for key in keys if key[1] in foldable]
    room = max(0, bound - len(fixed))
    kept = fold[:room]
    folded: dict[WithheldCap, list[GroupKey]] = {}
    for key in fold[room:]:
        folded.setdefault(key[1], []).append(key)
    named = sorted([*fixed, *kept], key=lambda key: order_key(key, rank_of))
    return GroupArrangement(
        named=tuple(named),
        folded={cap: tuple(members) for cap, members in folded.items()},
    )


__all__ = ["GroupArrangement", "GroupKey", "arrange_groups", "order_key"]
