"""The recovery chain contract (round 29, R-MCP-033 requirements 4 and 5, strong reading).

**The bound and the schedule are tested before the chain is wired in**, as the owner required:
`MAX_RECOVERY_STEPS` is derived from the narrowing schedule, and this file holds the
derivation, so the constant cannot drift from the schedule it bounds. The end-to-end tests
below then follow real declines through the shipped `call` and hold the four properties -
bounded, monotonic, cycle-free, terminal - by execution.

The fixture the whole round is about, forty-five messages across a few threads that used to
come back as forty-five bookkeeping records and no mail, is driven here too: its chain must
terminate in a served response carrying matched mail.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mailweave.constants import HOST_RESULT_CHAR_CAP, MAX_HIT_THREADS, MAX_MESSAGE_IDS_PER_RETRY
from mailweave.envelope.vocab import ToolName
from mailweave.surface import recovery
from mailweave.surface.recovery import (
    GET_MESSAGES_CHAIN_STEPS,
    MAX_RECOVERY_STEPS,
    SEARCH_CHAIN_STEPS,
    SEARCH_HALVING_STEPS,
    THREAD_MAP_CHAIN_STEPS,
    Narrowing,
    applied_hit_threads,
    halvings_to_one,
    is_the_same_call,
    narrower_call,
)

# --- the bound, derived before anything follows it -------------------------------------------


def test_the_step_bound_is_derived_from_the_schedule() -> None:
    """Each tool's chain is a sum over its schedule; the bound is the largest of them.

    Written as the sums rather than as numbers, so a change to `MAX_HIT_THREADS` or
    `MAX_MESSAGE_IDS_PER_RETRY` that lengthens a schedule fails here and has to be accounted
    for. The first draft added a segment hop after a search's tool change; the tightness test
    below showed the schedule never makes it. The review then added the `message_ids`
    dimension for reads (R-V01-010), which was the longest chain there was - until the
    cause-directed search (2026-09-15, R-M2-095), whose hops reduce the width by as little
    as one, so its longest chain is one hop per width below the published figure plus the
    tool change. The halving schedule is the search's chain without a cause.
    """
    assert halvings_to_one(MAX_HIT_THREADS) + 1 == SEARCH_HALVING_STEPS
    assert (MAX_HIT_THREADS - 1) + 1 == SEARCH_CHAIN_STEPS
    assert SEARCH_HALVING_STEPS <= SEARCH_CHAIN_STEPS
    assert 1 + 1 + halvings_to_one(MAX_MESSAGE_IDS_PER_RETRY) == GET_MESSAGES_CHAIN_STEPS
    # Navigation redesign (2026-09-14): a map is already the page that fits; nothing narrower.
    assert THREAD_MAP_CHAIN_STEPS == 0
    assert max(SEARCH_CHAIN_STEPS, GET_MESSAGES_CHAIN_STEPS, THREAD_MAP_CHAIN_STEPS) == (
        MAX_RECOVERY_STEPS
    )
    assert halvings_to_one(12) == 3  # 12 -> 6 -> 3 -> 1
    assert halvings_to_one(50) == 5  # 50 -> 25 -> 12 -> 6 -> 3 -> 1
    assert halvings_to_one(1) == 0


@given(st.integers(min_value=1, max_value=10_000))
def test_halving_always_reaches_one_and_never_stalls(applied: int) -> None:
    steps = halvings_to_one(applied)
    assert steps <= applied.bit_length()
    value, seen = applied, [applied]
    while value > 1:
        value = max(1, value // 2)
        assert value < seen[-1], "a hop that does not strictly reduce is a hop that can loop"
        seen.append(value)
    assert len(seen) - 1 == steps


# --- the pure schedule: every branch is one strict step on one declared dimension ------------


def _search(query: str = "q", **budget: int) -> dict[str, Any]:
    return {"query": query, "budget": budget} if budget else {"query": query}


@pytest.mark.parametrize("requested", [None, 12, 7, 2, 1, 0, -5, 99])
def test_the_applied_width_is_the_callers_clamped_and_never_raised(requested: int | None) -> None:
    args = _search() if requested is None else _search(max_hit_threads=requested)
    applied = applied_hit_threads(args)
    assert 1 <= applied <= MAX_HIT_THREADS
    if requested is not None and 1 <= requested <= MAX_HIT_THREADS:
        assert applied == requested


def test_a_search_narrows_by_halving_and_declares_it() -> None:
    step = narrower_call(ToolName.SEARCH.value, _search(max_hit_threads=12), top_thread="t1")
    assert step is not None
    assert step.affordance.args == {"query": "q", "budget": {"max_hit_threads": 6}}
    assert step.narrowing == Narrowing("max_hit_threads", 12, 6)


def test_a_search_that_omitted_the_width_was_applied_at_the_published_figure() -> None:
    step = narrower_call(ToolName.SEARCH.value, _search(), top_thread=None)
    assert step is not None and step.narrowing.applied == MAX_HIT_THREADS


def test_a_search_at_width_one_changes_dimension_to_a_thread_map() -> None:
    """**The exact defect.** Round 28 offered `max_hit_threads: 1` back to a caller who had
    asked for `max_hit_threads: 1`. Now the search has nowhere narrower to go, so the next hop
    is a different tool on the one thread the search ranked highest, and the decline says
    that is what changed."""
    step = narrower_call(ToolName.SEARCH.value, _search(max_hit_threads=1), top_thread="t9")
    assert step is not None
    assert step.affordance.tool is ToolName.THREAD_MAP
    # Navigation redesign (2026-09-14): the map hop names the thread; the map it returns is a
    # page sized to fit, so no `segment` rides along (a segment map declined terminally).
    assert step.affordance.args == {"thread_id": "t9"}
    assert step.narrowing.dimension == "tool"


def test_a_search_at_width_one_with_no_thread_to_map_ends_the_chain() -> None:
    """No smaller legal request can produce evidence: `None`, so the decline carries
    `retry_with: null` rather than a call that would fail again."""
    assert narrower_call(ToolName.SEARCH.value, _search(max_hit_threads=1), top_thread=None) is None


def test_a_thread_map_has_nowhere_narrower_to_go_whether_or_not_it_has_segments() -> None:
    """Navigation redesign (2026-09-14). R-V01-010 offered `segment: 0` to a segmented thread;
    the independent review found a segment map of a long thread declines terminally (R-M2-081,
    R-M2-085), and a map is now served as a page sized to fit - the smallest map there is. A
    map that still does not fit is a thread whose inventory alone exceeds the cap, and the
    honest answer is final, in both the segmented and the flat case."""
    for segmented in (True, False):
        step = narrower_call(
            ToolName.THREAD_MAP.value, {"thread_id": "t1"}, top_thread=None, segmented=segmented
        )
        assert step is None, segmented
    again = narrower_call(
        ToolName.THREAD_MAP.value,
        {"thread_id": "t1", "segment": 0},
        top_thread=None,
        segmented=True,
    )
    assert again is None


def test_a_read_narrows_its_view_first_and_then_halves_its_ids() -> None:
    """R-V01-010: twelve ids at `stub` used to be declared final when eleven would serve."""
    ids = [f"m{i}" for i in range(12)]
    full = narrower_call(
        ToolName.GET_MESSAGES.value, {"message_ids": ids, "view": "body_full"}, top_thread=None
    )
    assert full is not None and full.narrowing == Narrowing("view", "body_full", "body_clean")
    assert full.affordance.args["message_ids"] == ids  # the ids are untouched on a view hop
    fewer = narrower_call(
        ToolName.GET_MESSAGES.value, {"message_ids": ids, "view": "stub"}, top_thread=None
    )
    assert fewer is not None and fewer.narrowing == Narrowing("message_ids", 12, 6)
    assert fewer.affordance.args == {"message_ids": ids[:6], "view": "stub"}
    one = narrower_call(
        ToolName.GET_MESSAGES.value, {"message_ids": ids[:1], "view": "stub"}, top_thread=None
    )
    assert one is None, "one id at the shallowest view is the end of the chain"


def test_a_read_by_map_id_and_positions_runs_the_same_schedule() -> None:
    """R-V01-010 (recheck): the `map_id` + `positions` form fell through every branch and was
    declared final at `body_full` with no `view` hop. Same schedule, `positions` halved."""
    args = {"map_id": "map-token", "positions": list(range(12)), "view": "body_full"}
    full = narrower_call(ToolName.GET_MESSAGES.value, args, top_thread=None)
    assert full is not None and full.narrowing == Narrowing("view", "body_full", "body_clean")
    assert full.affordance.args == {**args, "view": "body_clean"}
    fewer = narrower_call(ToolName.GET_MESSAGES.value, {**args, "view": "stub"}, top_thread=None)
    assert fewer is not None and fewer.narrowing == Narrowing("positions", 12, 6)
    assert fewer.affordance.args == {
        "map_id": "map-token",
        "positions": list(range(6)),
        "view": "stub",
    }
    many = narrower_call(
        ToolName.GET_MESSAGES.value,
        {**args, "positions": list(range(400)), "view": "stub"},
        top_thread=None,
    )
    assert many is not None and many.narrowing == Narrowing("positions", 400, 50)
    one = narrower_call(
        ToolName.GET_MESSAGES.value, {**args, "positions": [3], "view": "stub"}, top_thread=None
    )
    assert one is None


def test_every_other_argument_travels_unchanged_on_a_retry() -> None:
    """R-V01-009: a retry is the failed call with one dimension reduced, not a rebuilt call
    that drops the caller's other budget keys, scan, relax, or view."""
    args = {
        "query": "q",
        "budget": {"max_hit_threads": 4, "max_disclosed_tokens": 620, "max_server_ms": 7700},
        "scan": "all",
        "relax": False,
    }
    step = narrower_call(ToolName.SEARCH.value, args, top_thread="t1")
    assert step is not None
    assert step.affordance.args == {
        **args,
        "budget": {"max_hit_threads": 2, "max_disclosed_tokens": 620, "max_server_ms": 7700},
    }


@given(
    width=st.integers(min_value=1, max_value=MAX_HIT_THREADS),
    top=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
)
@settings(max_examples=200)
def test_no_retry_ever_repeats_the_failed_arguments(width: int, top: str | None) -> None:
    """Requirement 5, first clause, as a property over every width and every top thread."""
    args = _search(max_hit_threads=width)
    step = narrower_call(ToolName.SEARCH.value, args, top_thread=top)
    if step is not None:
        assert not is_the_same_call(ToolName.SEARCH.value, args, step.affordance)


def _follow(name: str, args: dict[str, Any], **hints: Any) -> int:
    seen = [(name, dict(args))]
    hops = 0
    while (step := narrower_call(name, args, **hints)) is not None:
        hops += 1
        assert hops <= MAX_RECOVERY_STEPS, seen
        name, args = step.affordance.tool.value, dict(step.affordance.args)
        assert (name, args) not in seen, "the schedule repeated a call"
        seen.append((name, args))
    return hops


def _one_narrower_cause(width: int) -> Any:
    """A cause whose table says exactly one width fits: the one just below `width`. The
    slowest cause-directed chain there is, one decrement per hop."""
    from mailweave.disclosure.ladder import RefusalCause, RefusalKind
    from mailweave.disclosure.layout import CostTerms

    terms = CostTerms(
        unit="chars",
        structural=1,
        echo=0,
        expansion=0,
        sources=0,
        records=0,
        groups=0,
        tails=0,
        not_included=0,
    )
    return RefusalCause(
        kind=RefusalKind.EMPTY,
        unit="chars",
        cap=HOST_RESULT_CHAR_CAP,
        terms=terms,
        groups_by_cap={},
        folded_by_cap={},
        width=width,
        top_thread="t1",
        fits_at={width - 1: HOST_RESULT_CHAR_CAP} if width > 1 else {},
        refused_at=tuple(range(width - 2, 0, -1)),
    )


def _follow_directed(name: str, args: dict[str, Any]) -> int:
    seen = [(name, dict(args))]
    hops = 0
    while True:
        width = applied_hit_threads(args) if name == ToolName.SEARCH.value else 1
        step = narrower_call(name, args, top_thread="t1", cause=_one_narrower_cause(width))
        if step is None:
            return hops
        hops += 1
        assert hops <= MAX_RECOVERY_STEPS, seen
        name, args = step.affordance.tool.value, dict(step.affordance.args)
        assert (name, args) not in seen, "the schedule repeated a call"
        seen.append((name, args))


def test_following_the_pure_schedule_from_the_top_ends_within_the_bound() -> None:
    """The schedule alone, without a server: from each tool's widest request, count the hops.
    Each tool's bound must be tight - exactly reached - or it is a bound on nothing. The
    search has two schedules since R-M2-095: the halving one, without a cause, and the
    cause-directed one, whose slowest form - a cause that says only the next width down fits,
    at every hop - is the search's bound."""
    halving = _follow(
        ToolName.SEARCH.value, _search(max_hit_threads=MAX_HIT_THREADS), top_thread="t1"
    )
    assert halving == SEARCH_HALVING_STEPS, halving
    search = _follow_directed(ToolName.SEARCH.value, _search(max_hit_threads=MAX_HIT_THREADS))
    assert search == SEARCH_CHAIN_STEPS, search
    reads = _follow(
        ToolName.GET_MESSAGES.value,
        {"message_ids": [f"m{i}" for i in range(300)], "view": "body_full"},
        top_thread=None,
    )
    assert reads == GET_MESSAGES_CHAIN_STEPS, reads
    maps = _follow(ToolName.THREAD_MAP.value, {"thread_id": "t1"}, top_thread=None, segmented=True)
    assert maps == THREAD_MAP_CHAIN_STEPS, maps
    assert max(search, reads, maps) == MAX_RECOVERY_STEPS


def test_the_guard_is_the_direct_form_of_the_cycle_free_property() -> None:
    """`is_the_same_call` compares tool and arguments exactly, and nothing else."""
    from mailweave.envelope.wire import Affordance

    same = Affordance(tool=ToolName.SEARCH, args={"query": "q", "budget": {"max_hit_threads": 1}})
    assert is_the_same_call(ToolName.SEARCH.value, _search(max_hit_threads=1), same)
    assert not is_the_same_call(ToolName.SEARCH.value, _search(max_hit_threads=2), same)
    assert not is_the_same_call(ToolName.THREAD_MAP.value, {"thread_id": "q"}, same)


def test_the_bound_is_a_public_constant_with_a_documented_derivation() -> None:
    # Twelve since 2026-09-15 (R-M2-095): a cause-directed search chain can reduce the
    # width by one per hop, from the published 12 to 1, then change tool. Seven before.
    assert recovery.MAX_RECOVERY_STEPS == 12
    assert "halving" in (recovery.__doc__ or "") and "widest" in (recovery.__doc__ or "")
    assert str(HOST_RESULT_CHAR_CAP)  # imported for the end-to-end half below
