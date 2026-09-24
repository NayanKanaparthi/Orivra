"""The thread-map LRU, specified (AD A.10 "The LRU, specified").

Before ADV-002 this cache had no TTL, no size and no invalidation rule anywhere in the
document, which is how it came to be the thing a `handle_stale` check was run against. Every
one of those is now a number in this module and a test beside it.

  * **Key** `(thread_id, history_id_at_fetch)`. The `historyId` is *in the key*, so an entry
    is never a claim about "this thread now": it is a claim about this thread at one point
    in Gmail's own history, and a redemption whose handle names a different `historyId`
    misses rather than hits.
  * **TTL 60 s**, **64 entries**, evicted least-recently-used.
  * **Evicted on staleness**: any `handle_stale` naming a thread drops every entry for that
    thread, and any `handle_stale_unverifiable` drops them too - because "the probe could
    not tell" is not a reason to keep serving what the probe was going to check.

**`fetched_at` is the entry's own fetch time and is never restamped.** The cache stores the
stamp the observation sealed and hands back that same string however many times the entry is
served. `verified_at` is added by the *redemption*, from the liveness probe that ran on this
call, and it is a second field rather than a rewrite of the first: *this content was read at
T0; it was verified unchanged at T1*. Both are true. Restamping `fetched_at` to now would
assert a freshness the response does not have, and - the sharper half - would make a handle
that cannot expire, since expiry is measured from `fetched_at`.

**The cache is not a verification and cannot become one.** Nothing here is consulted by AD
A.10 step 2: the liveness probe reads `history.list`, a different resource, so a cache hit
cannot make it pass. What the cache saves is step 3's `threads.get`, and only when step 2
came back clean.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from mailweave.structure.threadmap import ThreadMap

#: Seconds an entry may be served for. AD A.10 [DESIGN]; always <= a handle's own ttl, which
#: `MIN_HANDLE_TTL_SECONDS` holds handles to from the other side.
CACHE_TTL_SECONDS: Final[int] = 60

#: How many thread maps the cache holds. AD A.10.
MAX_CACHED_THREAD_MAPS: Final[int] = 64


@dataclass(frozen=True)
class CachedThreadMap:
    """One thread map as it was read, with the stamp of the read that produced it.

    `fetched_at` is a string carried verbatim from `RecordedThread.fetched_at` - the stamp
    the observation sealed - rather than a `datetime` this module formats. One time is one
    fact; a re-rendered copy is a second one that can differ in its last digits, and
    `Envelope` refuses a `Source.fetched_at` that differs from the observation's by
    microseconds.
    """

    thread_map: ThreadMap
    fetched_at: str
    history_id: str
    #: When this entry was put in the cache. Distinct from `fetched_at`, and used only for
    #: the TTL: the two agree today because an entry is stored as soon as it is fetched, and
    #: they are separate fields so that stays a fact rather than an assumption.
    stored_at: datetime


class ThreadMapCache:
    """A bounded, expiring, thread-keyed cache of maps. In-process, never on disk.

    Not a Pydantic model and not sealed: nothing here reaches the wire. What it hands back is
    a `ThreadMap` the caller then represents, and a `fetched_at` string it must carry
    unchanged.
    """

    __slots__ = ("_entries", "_max_entries", "_ttl")

    def __init__(
        self,
        *,
        max_entries: int = MAX_CACHED_THREAD_MAPS,
        ttl_seconds: int = CACHE_TTL_SECONDS,
    ) -> None:
        if max_entries < 1:
            raise ValueError("a cache holds at least one entry")
        if ttl_seconds < 1:
            raise ValueError("a cache entry lives for at least one second")
        self._entries: OrderedDict[tuple[str, str], CachedThreadMap] = OrderedDict()
        self._max_entries = max_entries
        self._ttl = timedelta(seconds=ttl_seconds)

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def keys(self) -> tuple[tuple[str, str], ...]:
        """Every live key, least-recently-used first. For tests and for the trace."""
        return tuple(self._entries)

    def get(self, *, thread_id: str, history_id: str, now: datetime) -> CachedThreadMap | None:
        """The entry for this thread **at this `historyId`**, or `None`.

        An entry past its TTL is dropped rather than returned, here rather than at insertion
        time: a cache that expires only on write keeps serving a stale entry for as long as
        nothing new arrives, which is precisely the traffic pattern a quiet mailbox has.
        """
        key = (thread_id, history_id)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if now.astimezone(UTC) - entry.stored_at >= self._ttl:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return entry

    def put(self, entry: CachedThreadMap) -> None:
        """Store one map, evicting the least recently used once the bound is reached."""
        key = (entry.thread_map.thread_id, entry.history_id)
        self._entries[key] = entry
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def evict_thread(self, thread_id: str) -> int:
        """Drop every entry for one thread, at any `historyId`. Returns how many went.

        Called on `handle_stale` and on `handle_stale_unverifiable` alike. The second is the
        one worth stating: the probe did not find a change, it failed to look, and an entry
        kept on that basis is an entry nothing is checking.
        """
        doomed = [key for key in self._entries if key[0] == thread_id]
        for key in doomed:
            del self._entries[key]
        return len(doomed)
