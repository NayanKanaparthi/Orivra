"""The bounded cache, and the rule that a key is never permission to serve.

Plan §5.1's cached category only: vectors, normalised metadata, source-native structure,
observed edges, entity candidates and bounded negative results. **No message text, no document
text, no derived summaries, no inferred edges** - v1 avoids the encrypted-index question by not
persisting text at all, and inferred fragments are recomputable.

Three things make it safe to keep, and each is a refusal rather than a convention:

**The key is the whole identity** (`cache.key`), so an entry written under one principal,
content version, permission state, model or schema cannot be read under another.

**A key is never authority.** §5.3: a matching `permission_hash` proves an entry *was written*
under an access state, not that the state still holds - access can be revoked with nothing here
noticing. So `get` takes a **live revalidation callable** and will not return a value without
one that answers yes. A revalidation that cannot be completed does not fall back to the cached
value; it reports `UNVERIFIED` and the caller degrades to a fresh read.

**Bounds are per kind and per entry.** A TTL per kind so an abandoned workspace decays rather
than persisting, plus a total entry count so a long-running process cannot grow without limit.
Negative entries carry minutes, not hours, because absence is the most expensive thing to be
wrong about.

This implementation is **in-memory**. The plan's on-disk form is SQLite under
`~/.local/share/orivra/cache/` at 0700/0600, and that is a separate piece of work with its own
file-permission tests; what is here is the key, the bounds and the revalidation contract, which
are the parts the correctness of a disk store would rest on. The gap is named rather than
implied: nothing in this module writes to disk, and `orivra purge` has nothing to delete yet.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from orivra.cache.key import CacheKey, CacheKind

#: Per-kind retention. Bounded even when nothing upstream changed, which is §5.2's rule that an
#: abandoned workspace decays. A negative result gets minutes because being wrong about absence
#: is the expensive direction.
TTL_BY_KIND: dict[CacheKind, timedelta] = {
    CacheKind.VECTOR: timedelta(days=7),
    CacheKind.METADATA: timedelta(days=1),
    CacheKind.STRUCTURE: timedelta(days=1),
    CacheKind.OBSERVED_EDGE: timedelta(days=1),
    CacheKind.ENTITY_CANDIDATE: timedelta(hours=12),
    CacheKind.NEGATIVE: timedelta(minutes=5),
}

DEFAULT_CAPACITY: int = 4096


class Serve(StrEnum):
    """Why a read did or did not produce a value. Four outcomes, not two."""

    HIT = "hit"
    #: No entry under this key. Includes every key-dimension change - a new revision, a new
    #: model, a different principal - which is what makes those invalidations structural rather
    #: than a deletion somebody has to remember to perform.
    MISS = "miss"
    #: The entry existed and aged out.
    EXPIRED = "expired"
    #: The entry existed and the live access check said no, or could not be completed. **Never
    #: falls back to the value**: §5.3's degradation is fresh read, resync, or an explicit
    #: inconclusive, and the cached value is not on that list.
    UNVERIFIED = "unverified"


class RevalidationReason(StrEnum):
    """Why a revalidation said what it said. One value per distinct fact, never a catch-all.

    `ACCESS_CHANGED` is one member of this set and not its default. It used to be the only
    sentence an unsuccessful revalidation could produce, which made every inconclusive change
    feed look like a caller who had lost permission.
    """

    #: The check completed and found nothing had moved. The only reason that serves.
    UNCHANGED = "unchanged"
    #: The feed observed a change to this item. Conclusive whatever else the walk missed.
    CHANGED = "changed"
    #: The walk could not establish that nothing changed - it ran out of pages, or stopped
    #: short. Not "nothing changed", and not a change either.
    INCONCLUSIVE = "inconclusive"
    #: The watermark this entry is keyed on is older than the source retains, so the feed
    #: cannot be walked from it at all. The remembered watermark has to be re-baselined; the
    #: entry is not servable and repeating the walk will not help.
    WATERMARK_EXPIRED = "watermark_expired"
    #: The caller may no longer see this item. The one reason that is about access.
    ACCESS_CHANGED = "access_changed"
    #: The check raised. A check that did not finish is not a yes.
    PROBE_FAILED = "probe_failed"
    #: No reason was supplied. Only reachable from a caller that has not been updated.
    UNSTATED = "unstated"

    @property
    def calls_for_rebaseline(self) -> bool:
        """Whether the *watermark*, rather than the entry, is what went wrong."""
        return self is RevalidationReason.WATERMARK_EXPIRED


@dataclass(frozen=True)
class Revalidation:
    """One live check's answer, with the reason it gave rather than a bare yes or no."""

    ok: bool
    reason: RevalidationReason
    detail: str
    #: True when the caller should discard the watermark it keyed on rather than retry. Read
    #: off the reason so the two cannot disagree.
    rebaseline: bool = False

    def __post_init__(self) -> None:
        if self.ok and self.reason is not RevalidationReason.UNCHANGED:
            raise ValueError(
                f"a revalidation that says yes carries reason {self.reason.value!r}; the only "
                "reason to serve a stored entry is that nothing changed"
            )
        object.__setattr__(self, "rebaseline", self.reason.calls_for_rebaseline)


#: What `BoundedCache.get` requires of its revalidator.
Revalidator = Callable[[CacheKey], "Revalidation"]


@dataclass(frozen=True)
class Read:
    outcome: Serve
    value: Any = None
    why: str = ""
    #: The revalidation's own reason, when one ran. `UNSTATED` when the outcome was decided
    #: before any check - a miss or an expiry - because those are facts about the store rather
    #: than about the source.
    reason: RevalidationReason = RevalidationReason.UNSTATED
    #: True when what went stale is the watermark rather than the entry.
    rebaseline: bool = False

    @property
    def usable(self) -> bool:
        return self.outcome is Serve.HIT


@dataclass
class _Entry:
    key: CacheKey
    value: Any
    written_at: datetime


@dataclass
class BoundedCache:
    """Entries by key hash, bounded by kind TTL and by total count."""

    now: Callable[[], datetime]
    capacity: int = DEFAULT_CAPACITY
    _entries: dict[str, _Entry] = field(default_factory=dict, repr=False)

    def put(self, key: CacheKey, value: Any) -> None:
        self._evict_expired()
        if len(self._entries) >= self.capacity and key.hash not in self._entries:
            oldest = min(self._entries.values(), key=lambda one: one.written_at)
            self._entries.pop(oldest.key.hash, None)
        self._entries[key.hash] = _Entry(key=key, value=value, written_at=self.now())

    def get(self, key: CacheKey, *, revalidate: Revalidator) -> Read:
        """A value only when the entry exists, is in date, **and** a live check says yes.

        `revalidate` is required rather than optional, and it is a callable rather than a flag,
        because the question it answers is about now. A signature that let a caller omit it
        would make the safe path the one you have to remember.

        **It returns a `Revalidation`, not a bool, and that is a correctness fix rather than
        ergonomics.** A bool has one false, and this check has at least four: the change feed
        saw a change, the walk could not finish looking, the watermark is older than the
        source retains, or the caller genuinely may not see it any more. They were all
        reported as the last one - "written under an access state that no longer holds" - so a
        live run whose history walk simply could not complete was told its access had changed.
        Only one of those four is about access, and only one of them calls for re-baselining.
        """
        # **This key first, then the sweep.** Running the sweep first deleted the entry being
        # asked about and the lookup then reported `MISS` - so a caller could not tell "never
        # cached" from "cached and aged out", and those license different next steps: a miss
        # says compute it, an expiry says it was computed and went stale, which is what you
        # want to know when diagnosing churn or a TTL that is too short.
        entry = self._entries.get(key.hash)
        if entry is not None and self._expired(entry):
            self._entries.pop(key.hash, None)
            self._evict_expired()
            return Read(Serve.EXPIRED, why=f"{key.kind.value} entries expire on a bounded TTL")
        self._evict_expired()
        if entry is None:
            return Read(Serve.MISS, why="no entry under this key")
        try:
            decision = revalidate(key)
        except Exception as failed:
            return Read(
                Serve.UNVERIFIED,
                why=(
                    "the revalidation could not be completed "
                    f"({type(failed).__name__}), and a check that did not finish is not a "
                    "yes. Degrade to a fresh read rather than serving this"
                ),
                reason=RevalidationReason.PROBE_FAILED,
            )
        if not decision.ok:
            return Read(
                Serve.UNVERIFIED,
                why=decision.detail,
                reason=decision.reason,
                rebaseline=decision.rebaseline,
            )
        return Read(Serve.HIT, value=entry.value, reason=decision.reason, why=decision.detail)

    def invalidate_native(self, *, connector: str, native_id: str) -> int:
        """Drop every entry for one source item, whatever kind or version. Returns the count.

        What a change feed calls: Gmail's `history.list` names a message that moved, and the
        vectors, metadata and structure keyed on its older version all stop being answers about
        it. Keyed lookups would miss them, because the feed reports the id and not the version
        the cache happens to hold.
        """
        doomed = [
            hashed
            for hashed, entry in self._entries.items()
            if entry.key.connector == connector and entry.key.native_id == native_id
        ]
        for hashed in doomed:
            self._entries.pop(hashed, None)
        return len(doomed)

    def purge(self) -> int:
        """Everything. `orivra purge`'s whole job."""
        count = len(self._entries)
        self._entries.clear()
        return count

    def _expired(self, entry: _Entry) -> bool:
        return self.now() - entry.written_at >= TTL_BY_KIND[entry.key.kind]

    def _evict_expired(self) -> None:
        for hashed in [hashed for hashed, entry in self._entries.items() if self._expired(entry)]:
            self._entries.pop(hashed, None)

    def __len__(self) -> int:
        self._evict_expired()
        return len(self._entries)


__all__ = ["DEFAULT_CAPACITY", "TTL_BY_KIND", "BoundedCache", "Read", "Serve"]
