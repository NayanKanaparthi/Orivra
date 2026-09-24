"""R-M2-108: thread membership is decided on routes, not on the first admission.

`HitOrigin` records where an id *entered* `H`, and a second sighting deliberately does not move
it. `hit_threads` grouped on that record, so an id whose first admission was a `threads.get` -
which is how D.5's pool reads every row of a thread it touches - and which a *later*
`messages.list` also listed was skipped by the grouping entirely. Its thread could go unplanned,
and where the thread was planned by a sibling id, `listed_ids` under-reported what the ladder had
actually listed.

The demotion predicate directly above it (`pool_listed_only`) was rewritten onto `AdmissionRoute`
during A16 for exactly this reason, and the grouping was left behind. Two halves of one rule
reading two different provenance records is the defect; this file holds them on the same one.

**Why it matters beyond the tier.** The threads this function plans are what `max_hit_threads`
cuts, and the surviving plans are the seed set the M3 query-time graph is built over. A thread
missing here is a thread the graph cannot reach, and the omission would not be accounted for
anywhere - it was never a candidate.

Corpus-independent: every observation below is constructed.
"""

from __future__ import annotations

from mailweave.envelope.disposition import (
    AdmissionRoute,
    DispositionLedger,
    ObservedEndpoint,
)
from mailweave.policy.account import LADDER as PUBLISHED_LADDER
from mailweave.retrieval.assemble import hit_threads
from mailweave.trace.schema import RungId
from tests.fixtures import envelope_kit as kit

TERM = "launch"
RECENCY_Q = "after:1750000000"


def _pool_read_then_listed() -> DispositionLedger:
    """The trap, in the order that springs it.

    `m-pooled` enters `H` through the pool's `threads.get` (clause H-thr), so its origin's
    endpoint is `THREADS_GET` for ever. A later lexical `messages.list` returns it too. Only the
    route set knows that second fact.
    """
    ledger = DispositionLedger()
    ledger.record_thread(
        kit.observed_thread(("m-pooled", "m-sibling"), thread_id="t-pool"), rung=RungId.L5
    )
    ledger.record_list_page(
        kit.fetched(("m-pooled",), thread_ids={"m-pooled": "t-pool"}),
        rung=RungId.L1,
        query=TERM,
    )
    return ledger


def test_the_fixture_springs_the_first_admission_trap() -> None:
    """Asserted first: a fixture where the origin already said `messages.list` proves nothing."""
    ledger = _pool_read_then_listed()
    assert ledger.origins["m-pooled"].endpoint is ObservedEndpoint.THREADS_GET
    assert (
        AdmissionRoute(ObservedEndpoint.MESSAGES_LIST, RungId.L1, TERM) in ledger.routes["m-pooled"]
    )


def test_an_id_the_pool_read_first_and_a_lexical_rung_listed_is_a_hit_of_its_thread() -> None:
    """The regression. Grouping on the origin dropped this id and, with it, its thread."""
    plans = {plan.thread_id: plan for plan in hit_threads(_pool_read_then_listed())}
    assert "t-pool" in plans, "the thread a lexical rung listed into was not planned at all"
    assert "m-pooled" in plans["t-pool"].listed_ids
    assert "m-pooled" in plans["t-pool"].hit_ids


def test_a_thread_read_and_never_listed_is_still_not_a_hit_thread() -> None:
    """The other direction, unchanged: thread membership is not a listing and never made a row
    evidence. Reading routes must not turn `threads.get` into an admission route of its own."""
    ledger = DispositionLedger()
    ledger.record_thread(kit.observed_thread(("m-a", "m-b"), thread_id="t-read"), rung=RungId.L5)
    assert hit_threads(ledger) == ()


def test_the_thread_takes_the_earliest_listing_rung_across_routes_not_the_first_one() -> None:
    """The rung attribution, which this function's own contract calls "the ladder position of the
    earliest rung that admitted a hit in the thread".

    Read off the first admission, a thread the L5 recency probe happened to see before an L1 term
    match reported as L5 - a route attribution decided by arrival order, in the field a reader
    uses to see which route produced the evidence.
    """
    ledger = DispositionLedger()
    ledger.record_list_page(
        kit.fetched(("m1",), thread_ids={"m1": "t1"}), rung=RungId.L5, query=RECENCY_Q
    )
    ledger.record_list_page(
        kit.fetched(("m1",), thread_ids={"m1": "t1"}), rung=RungId.L1, query=TERM
    )
    assert ledger.origins["m1"].rung is RungId.L5, "the fixture must exercise the trap"
    (plan,) = hit_threads(ledger)
    assert plan.rung is RungId.L1
    assert PUBLISHED_LADDER.index(RungId.L1) < PUBLISHED_LADDER.index(RungId.L5)


def test_an_id_with_no_listing_route_at_all_joins_no_thread() -> None:
    """A history arrival is its own plan's hit (`_recency_plans`), not a listing, so it must not
    be folded in here by the route rewrite."""
    ledger = DispositionLedger()
    ledger.record_history_additions(
        kit.history_additions(("m-new",), thread_ids={"m-new": "t-new"})
    )
    assert all(plan.thread_id != "t-new" for plan in hit_threads(ledger))
