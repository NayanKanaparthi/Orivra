"""Where a built graph lives for its ten minutes, and why that is not a store.

MCP revision 2026-07-28 is stateless: there is no session to hang a graph on. So `orivra_ask`
mints a `query_id`, the client passes it back, and `orivra_expand` and the `orivra://queries/`
resources address the graph under it. That is a **statelessness accommodation**, not a cache
and not a database:

* It holds only what one query built, and only until `built_at + ttl`.
* Nothing is written to disk. A restart loses every graph, which is correct - a handle that
  survived a restart would be a promise this server did not make.
* Nothing is shared between accounts. The key is the `query_id`, minted per call, and a
  caller who does not hold one cannot enumerate what is here.

**Expiry is checked on read, never on a timer.** A sweeper that ran between a caller's two
calls would make the same handle work and then not work for reasons the caller cannot see; a
read-time check makes the answer a function of the clock alone, which is the thing a caller
can reason about. Eviction of the expired is a side effect of reading, plus a bound on how
many graphs may be held at once so a long-running server cannot grow without limit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from orivra.contracts import QueryGraph

#: How many graphs one process holds at once. Small: a graph is one in-flight question's
#: working set, and a server holding hundreds is a server that has stopped discarding them.
DEFAULT_CAPACITY: int = 32


def _now() -> datetime:
    return datetime.now(UTC)


class GraphExpired(LookupError):
    """The `query_id` was real and its graph is gone.

    A distinct type from "never existed" **for the server's own reasoning, not the caller's**.
    What the caller is told is the same either way: the two are distinguishable from outside
    only by timing, and a response that said "expired" would confirm that some query with that
    id once ran - which is a fact about somebody's traffic.
    """


@dataclass
class QueryGraphStore:
    """Built graphs, by `query_id`, for `ttl`."""

    capacity: int = DEFAULT_CAPACITY
    now: Callable[[], datetime] = _now
    _held: dict[str, QueryGraph] = field(default_factory=dict, repr=False)

    def put(self, graph: QueryGraph) -> None:
        self._evict_expired()
        if len(self._held) >= self.capacity:
            # Oldest by build time, which is also the one closest to expiring anyway. Not LRU:
            # a graph's worth here is how long it has left, not how recently it was read.
            oldest = min(self._held.values(), key=lambda held: held.built_at)
            self._held.pop(oldest.query_id, None)
        self._held[graph.query_id] = graph

    def get(self, query_id: str) -> QueryGraph:
        """The graph, or `GraphExpired` - and the same error for gone and never-was."""
        self._evict_expired()
        graph = self._held.get(query_id)
        if graph is None:
            raise GraphExpired(
                "no graph is held for this query_id. A graph lives for ten minutes after the "
                "response that built it; ask again to get a current one"
            )
        return graph

    def _evict_expired(self) -> None:
        instant = self.now()
        for query_id in [
            held.query_id for held in self._held.values() if held.expires_at <= instant
        ]:
            self._held.pop(query_id, None)

    def __len__(self) -> int:
        self._evict_expired()
        return len(self._held)


__all__ = ["DEFAULT_CAPACITY", "GraphExpired", "QueryGraphStore"]
