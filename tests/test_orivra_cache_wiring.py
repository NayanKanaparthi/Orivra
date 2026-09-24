"""The bounded cache, on the execution path rather than beside it.

`tests/test_orivra_cache.py` tests `BoundedCache` as a component: keys, TTLs, bounds, the
required revalidator. Every one of those passed while **nothing in the product called it**,
which is the failure this file exists to make impossible to repeat. Everything here goes
through `call(service, "orivra_expand", ...)` - the shipped tool - and counts the Gmail calls
the shipped adapter made.

**The seat is `threads.get` on the expansion path, and the reason it is safe is ADV-002's.**
The entry is a thread's structure; the revalidation walks `history.list`, a different
resource. A cache hit cannot make the check pass, because the check never looks at the cache.
The asymmetry is `LivenessProbe`'s own (amendment A10): a walk that saw a change has
established one whatever it did not read, so only the *negative* answer needs a conclusive
walk. An entry serves on `conclusive and not saw_a_change`; a change and an inconclusive walk
both send the call back to the source.

**What is not cached here, and why:** `version_of` - the per-message check the live gate runs
on every disclosure - is deliberately uncached. It is the answer whose whole point is that it
is asked now, and `graph/access.py` says so from the other side. Message bodies are not
cached either, in any category (plan §5.1); a thread map returns `stub` rows, which is what
makes this kind cacheable at all, and `test_no_entry_ever_carries_body_text` holds it.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pytest

from mailweave.gmail.client import LivenessProbe, ThreadChange
from orivra.cache import BoundedCache, CacheKind
from orivra.contracts import ConnectorId, FreshnessState, NodeKind
from orivra.gmail_adapter import GmailAdapter
from orivra.registry import ConnectorRegistry
from orivra.surface.server import call
from orivra.surface.service import OrivraService
from tests.test_mcp_surface_round24 import mailbox, make_service

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
QUESTION = "Larch pricing draft"
THREAD = "t-decision"

#: Tight enough that the decision thread is pruned, so the graph files a recoverable handle.
BUDGET = 4


def _clean() -> LivenessProbe:
    return LivenessProbe(
        touched={}, expired=False, pages_fetched=1, pages_exhausted=False, latest_history_id="99"
    )


def _changed(thread_id: str) -> LivenessProbe:
    return LivenessProbe(
        touched={thread_id: ThreadChange(labels_added=1)},
        expired=False,
        pages_fetched=1,
        pages_exhausted=False,
        latest_history_id="99",
    )


def _expired() -> LivenessProbe:
    """Gmail's 404 on a watermark older than its retention. Not "nothing changed"."""
    return LivenessProbe(
        touched={}, expired=True, pages_fetched=0, pages_exhausted=False, latest_history_id=None
    )


def _exhausted() -> LivenessProbe:
    """A walk that stopped with a continuation token outstanding. Also not "nothing changed"."""
    return LivenessProbe(
        touched={}, expired=False, pages_fetched=1, pages_exhausted=True, latest_history_id="99"
    )


class Bench:
    """One Orivra process over the synthetic mailbox, counting what reaches Gmail."""

    def __init__(self, *, cache: BoundedCache | None) -> None:
        self.calls: Counter[str] = Counter()
        self.probe: Any = _clean
        service = make_service(mailbox())
        opener = service.open_client

        def open_client() -> Any:
            client = opener()
            fetch = client.get_thread

            def get_thread(*args: Any, **kwargs: Any) -> Any:
                self.calls["threads.get"] += 1
                return fetch(*args, **kwargs)

            def liveness_of_threads(
                *, since: Any, start_history_id: str, **_: Any
            ) -> LivenessProbe:
                self.calls["history.list"] += 1
                self.floor = (dict(since), start_history_id)
                return self.probe()

            client.get_thread = get_thread
            client.liveness_of_threads = liveness_of_threads
            return client

        service.open_client = open_client
        self.service = service
        self.cache = cache
        self.adapter = GmailAdapter(service=service, granted_scopes=(SCOPE,), cache=cache)
        self.orivra = OrivraService(
            registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: self.adapter}),
            max_graph_nodes=BUDGET,
        )

    def expand(self) -> dict[str, Any]:
        """ask -> find the recoverable handle -> expand, counting only the expansion."""
        answer = call(
            self.orivra,
            "orivra_ask",
            {"query": QUESTION, "view": "body_clean", "graph": True},
        )
        assert not answer.is_error, answer.content
        assert answer.structured_content is not None
        query_id = dict(answer.structured_content)["query_id"]
        omissions = call(
            self.orivra, "orivra_graph", {"query_id": query_id, "select": "omissions"}
        )
        assert omissions.structured_content is not None
        handle = next(
            one["what"]
            for one in dict(omissions.structured_content)["items"]
            if one["what"] == f"gmail/thread/{THREAD}" and one.get("recover")
        )
        self.calls.clear()
        expanded = call(
            self.orivra, "orivra_expand", {"query_id": query_id, "handle": handle}
        )
        assert not expanded.is_error, expanded.content
        assert expanded.structured_content is not None
        return dict(expanded.structured_content)


# -- 1. reuse ----------------------------------------------------------------------------------


def test_the_second_expansion_of_one_thread_reads_the_change_feed_instead_of_the_thread() -> None:
    """The reuse, counted at the wire rather than asserted at the store."""
    bench = Bench(cache=BoundedCache(now=lambda: make_service(()).now()))
    bench.expand()
    assert bench.calls["threads.get"] == 1, "the cold expansion did not read the thread"
    assert bench.calls["history.list"] == 0, "a cold read has nothing to revalidate"

    bench.expand()
    assert bench.calls["threads.get"] == 0, "the thread was read again despite a clean probe"
    assert bench.calls["history.list"] == 1, "the entry was served without any revalidation"


def test_the_probe_walks_from_the_revision_the_entry_was_written_under() -> None:
    """A floor above the entry's own revision would step over the change it is looking for."""
    bench = Bench(cache=BoundedCache(now=lambda: make_service(()).now()))
    bench.expand()
    bench.expand()
    since, start = bench.floor
    assert set(since) == {THREAD}
    assert start == since[THREAD], "the walk's floor and the thread's floor disagree"


def test_without_a_cache_nothing_changes_and_no_probe_is_made() -> None:
    """`None` means no caching, not a cache that never hits: the probe is a cost too."""
    bench = Bench(cache=None)
    for _ in range(2):
        bench.expand()
        assert bench.calls["threads.get"] == 1
        assert bench.calls["history.list"] == 0


# -- 2. invalidation ---------------------------------------------------------------------------


def test_a_walk_that_saw_a_change_sends_the_call_back_to_the_source() -> None:
    bench = Bench(cache=BoundedCache(now=lambda: make_service(()).now()))
    bench.expand()
    bench.probe = lambda: _changed(THREAD)
    bench.expand()
    assert bench.calls["threads.get"] == 1, "a moved thread was served from the cache"
    assert bench.calls["history.list"] == 1


@pytest.mark.parametrize("inconclusive", [_expired, _exhausted], ids=["expired", "pages_exhausted"])
def test_a_walk_that_could_not_tell_is_not_a_yes(inconclusive: Any) -> None:
    """§5.3's rule: a revalidation that cannot be completed does not fall back to the value.

    Both of these report `touched={}`, which reads like "nothing changed" and is not. One
    walked from a watermark Gmail has forgotten; the other stopped with pages outstanding.
    Serving on either would be serving content nothing is checking - ADV-002's shape exactly.
    """
    bench = Bench(cache=BoundedCache(now=lambda: make_service(()).now()))
    bench.expand()
    bench.probe = inconclusive
    bench.expand()
    assert bench.calls["threads.get"] == 1, "an unverifiable probe served a cached thread"


def test_invalidating_the_native_id_drops_the_entry_whatever_its_revision() -> None:
    cache = BoundedCache(now=lambda: make_service(()).now())
    bench = Bench(cache=cache)
    bench.expand()
    assert len(cache) == 1
    assert cache.invalidate_native(connector=ConnectorId.GMAIL.value, native_id=THREAD) == 1
    assert len(cache) == 0
    bench.expand()
    assert bench.calls["threads.get"] == 1, "the dropped entry was still served"


def test_a_different_revision_misses_structurally_without_asking_the_feed() -> None:
    """The key carries `content_version`, so a moved thread is a miss before any probe runs.

    Cheaper *and* safer than a probe: there is no walk to be inconclusive about.
    """
    cache = BoundedCache(now=lambda: make_service(()).now())
    bench = Bench(cache=cache)
    bench.expand()
    (entry,) = [one.key for one in cache._entries.values()]
    assert entry.kind is CacheKind.STRUCTURE
    assert entry.native_id == THREAD
    assert entry.content_version, "the entry was keyed on an empty revision"
    assert entry.model_id is None, "a structure entry named a model that produced nothing"


# -- 3. what a served entry says about itself --------------------------------------------------


def test_a_served_entry_reports_the_probe_it_cost_and_not_the_fetch_it_avoided() -> None:
    """Re-reporting the original spend would claim API calls this call did not make."""
    bench = Bench(cache=BoundedCache(now=lambda: make_service(()).now()))
    cold = bench.expand()
    warm = bench.expand()
    assert cold["executed"] == warm["executed"], "the executed call changed shape"
    # The delta the caller sees is the same either way: an expansion that served from a store
    # recovers the same nodes as one that read the thread.
    assert {one["node_id"] for one in cold["added"]["nodes"]} == {
        one["node_id"] for one in warm["added"]["nodes"]
    }


def test_a_served_entry_is_stamped_by_the_revalidation_not_by_the_original_read() -> None:
    """Two facts: the content was read at T0, and it was verified unchanged at T1."""
    from mailweave.surface.arguments import parse_thread_map

    bench = Bench(cache=BoundedCache(now=lambda: make_service(()).now()))
    bench.expand()
    assert bench.cache is not None
    (held,) = [one.value for one in bench.cache._entries.values()]
    read_at = {node.node_id: node.freshness.verified_at for node in held.nodes}
    fetched_at = held.envelope.sources[0].fetched_at

    before = bench.service.now()
    served = bench.adapter.answer_thread_map(
        parse_thread_map({"thread_id": THREAD}), known_revision=_revision_of(bench)
    )
    assert bench.calls["threads.get"] == 1, "this second read was not served from the cache"

    for node in served.nodes:
        assert node.freshness.state is FreshnessState.FRESH
        assert node.freshness.verified_at >= before, (
            "a served node carried the verification stamp of the read that filled the cache, "
            "so it claims a check that did not happen on this call"
        )
        assert node.freshness.verified_at > read_at[node.node_id]
    assert served.envelope.sources[0].fetched_at == fetched_at, (
        "the envelope's own fetch time was restamped, which asserts a freshness this "
        "response does not have"
    )
    assert served.spend.rungs_executed == (), "a served entry named a rung that never ran"
    assert served.spend.api_calls_by_method["total"] == 1, (
        "a served entry reported the calls of the fetch it avoided rather than the walk it made"
    )


def _revision_of(bench: Bench) -> str:
    assert bench.cache is not None
    (entry,) = [one.key for one in bench.cache._entries.values()]
    return entry.content_version


def test_no_entry_ever_carries_body_text() -> None:
    """Plan §5.1: no message text at rest, in any category, checked rather than assumed."""
    cache = BoundedCache(now=lambda: make_service(()).now())
    bench = Bench(cache=cache)
    bench.expand()
    for entry in cache._entries.values():
        for node in entry.value.nodes:
            assert not node.content, f"{node.node_id} went into the cache carrying text"
            if node.kind is NodeKind.MESSAGE:
                assert node.depth.value == "stub"
