"""`mapping_digest`: the fingerprint of the maps a handle was minted over (AD A.10).

**What the digest covers is a decision, not a detail.** A handle says "this is a map of
these threads, as they were at `fetched_at`". Redemption's step 4 recomputes the digest over
the maps it fetched and calls a mismatch `handle_stale`, so anything inside the digest is
something a *change in* will be reported to the caller as *the mailbox having moved*. A
value that varies for any other reason therefore produces `handle_stale` for a thread
nothing changed in, which is a false statement in the one field a caller trusts to be
conservative.

So the digest covers exactly the facts that are a function of **the thread**:

  * which threads, and how many messages each stated (`stated_total`);
  * each message's id, its chronological `position`, its `linkage`, its `reply_parent_id`
    and its `can_be_a_parent` - the reply forest and the order, which `reply_tree` derives
    from RFC headers alone and `_thread_scalars` from `internalDate` alone;
  * `tied_on_internal_date`, because a tie is a fact about the thread's stamps and it
    changes what the position claim is worth.

**And it deliberately does not cover `Source.participants`** (R-RETR-051). The participant
index is *not* a function of the thread alone: the mention half is scanned in the text this
response observed, and a row whose body was fetched is scanned over the whole body while a
row that only ever had a `snippet` is scanned over about two hundred characters. Round 21
fixed the narrowing that made this worse - the scanner was handed the quote-stripped
`default_view`, so quoted mentions were invisible *and* the row reported itself scanned -
but fixing it does not make the index thread-only: disclosure depth still decides how much
text each row contributed. Two redemptions of one handle at different depths would therefore
digest differently, and the response would say `handle_stale` about a mailbox that had not
moved. The authorship half *is* thread-only and could be digested; splitting the block in
two to digest half of it would put a rule here that the participant index does not itself
enforce, which is the kind of coupling that rots. It is out, whole, and this paragraph is
why.

**Ids are hashed, not carried.** The digest is a hex string on a handle a caller holds, so
it must not be a channel: it is a SHA-256 over a canonical JSON rendering, truncated to 128
bits, and nothing about a thread is recoverable from it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any, Final

from mailweave.structure.threadmap import ThreadMap

#: Hex characters of digest carried on a handle. 32 is 128 bits: a collision is what would
#: let a *changed* map redeem as unchanged, and 128 bits is the standard floor for that.
DIGEST_HEX_CHARS: Final[int] = 32

#: Bumped whenever the *set of facts* the digest covers changes. Two servers on different
#: versions of that set would otherwise disagree about whether a thread had moved, and the
#: disagreement would surface as `handle_stale` with no cause. It is part of the digest input
#: rather than beside it, so an old handle cannot be compared against a new rule at all.
DIGEST_SCHEMA: Final[int] = 1


def _thread_facts(thread_map: ThreadMap) -> dict[str, Any]:
    """One thread's digestible facts, in chronological order throughout."""
    links = thread_map.structure.by_id
    return {
        "thread_id": thread_map.thread_id,
        "stated_total": thread_map.stated_total,
        "tied": sorted(thread_map.tied_on_internal_date),
        "messages": [
            {
                "id": message_id,
                "position": thread_map.positions[message_id],
                "linkage": links[message_id].linkage.value,
                "parent": links[message_id].parent_id,
                "can_be_a_parent": links[message_id].can_be_a_parent,
            }
            for message_id in thread_map.order
        ],
    }


def mapping_digest(maps: Sequence[ThreadMap]) -> str:
    """The digest of a set of thread maps, independent of the order they are given in.

    Sorted by `thread_id` because the *set* of threads is what a handle names: two
    redemptions that fetch the same threads in a different order have observed the same
    mailbox, and a digest that disagreed would report a change nobody made.
    """
    payload = {
        "schema": DIGEST_SCHEMA,
        "threads": [_thread_facts(one) for one in sorted(maps, key=lambda m: m.thread_id)],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:DIGEST_HEX_CHARS]
