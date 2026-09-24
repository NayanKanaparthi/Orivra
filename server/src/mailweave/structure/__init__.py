"""Structural retrieval computed live from thread maps (AD D.6, contract C-02, WS-05).

Three modules, one per signal, and they are separate because the failures are separate:

  * `reply_tree` - a parent is read off the child's own RFC headers or there is none;
  * `participants` - identity is an address, and authorship is not mention;
  * `threadmap` - the two above plus `internalDate` order, assembled for one thread.

Nothing here fetches, caches or persists. A map is a function of one `threads.get` response
and the positions its observation sealed, which is what makes AD D.6's "no persistent graph"
a property of the code rather than a note in a document.
"""

from __future__ import annotations

from mailweave.structure.participants import (
    ParticipantFacts,
    ParticipantIndex,
    index_participants,
    participants_of_message,
)
from mailweave.structure.reply_tree import Link, ThreadStructure, header_view, reconstruct
from mailweave.structure.threadmap import ThreadMap, build

__all__ = [
    "Link",
    "ParticipantFacts",
    "ParticipantIndex",
    "ThreadMap",
    "ThreadStructure",
    "build",
    "header_view",
    "index_participants",
    "participants_of_message",
    "reconstruct",
]
