"""The integration repair of 2026-09-15 (R1-R4), held on corpus-independent shapes.

R1 (R-M2-094): sizing and wire emission derive group membership, foldability and tails from
one arrangement (`envelope.grouping.arrange_groups`), on overlapping pool/overflow sets, on
several cap types, with and without a backend, and the estimate is at or above the actual
serialized size on every shape - including the round-27 matrix run with a backend, which had
never been inside it.

Nothing here reads a diagnostic case, an expected evidence id or a corpus position to decide
anything; the fixtures are generated, and the properties are the code's own contracts.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from mailweave.constants import HOST_RESULT_CHAR_CAP, MAX_HIT_THREADS, MAX_WITHHELD_GROUPS_NAMED
from mailweave.disclosure.layout import named_groups, tail_entries
from mailweave.envelope.grouping import GroupKey, arrange_groups
from mailweave.envelope.measure import rendered_chars
from mailweave.envelope.vocab import WithheldCap
from mailweave.semantic.interface import BackendRegistry
from mailweave.surface.partition import rendered_of
from mailweave.surface.server import call
from tests.fixtures.eval_dummy import _service, _WordBackend
from tests.fixtures.mailbox import Msg, SyntheticMailbox
from tests.test_mcp_surface_round24 import make_service, structured_of
from tests.test_round27 import ESTIMATE_SHAPES, TERM, _CapturedLadder, multi_thread_mailbox

HIT = WithheldCap.MAX_HIT_THREADS
POOL = WithheldCap.MAX_POOL_THREADS
CEIL = WithheldCap.DISCLOSED_TOKEN_CEILING

# --- R1 part 1: the arrangement itself -----------------------------------------------------


def _keys(*specs: tuple[str, WithheldCap]) -> list[GroupKey]:
    return list(specs)


def test_below_the_bound_every_group_is_named_in_rank_order() -> None:
    keys = _keys(("b", HIT), ("a", POOL), ("c", CEIL))
    arranged = arrange_groups(keys, foldable={HIT}, rank_of={"c": 0, "b": 1}, bound=10)
    assert arranged.named == (("c", CEIL), ("b", HIT), ("a", POOL))
    assert arranged.tail_count == 0


def test_past_the_bound_fixed_groups_are_always_named_and_only_foldable_caps_fold() -> None:
    fixed = [(f"p{i:02d}", POOL) for i in range(5)] + [(f"s{i:02d}", CEIL) for i in range(3)]
    foldable = [(f"h{i:02d}", HIT) for i in range(6)]
    arranged = arrange_groups(fixed + foldable, foldable={HIT}, bound=10)
    assert len(arranged.named) == 10
    assert all(key in arranged.named for key in fixed), "a fixed group folded"
    assert sum(1 for key in arranged.named if key[1] is HIT) == 2
    assert arranged.folded == {HIT: tuple(sorted(foldable)[2:])}
    assert arranged.tail_count == 1


def test_more_fixed_groups_than_the_bound_names_every_fixed_group_and_folds_every_foldable() -> (
    None
):
    fixed = [(f"p{i:02d}", POOL) for i in range(30)]
    foldable = [(f"h{i:02d}", HIT) for i in range(4)]
    arranged = arrange_groups(fixed + foldable, foldable={HIT}, bound=MAX_WITHHELD_GROUPS_NAMED)
    assert len(arranged.named) == 30, "the fixed groups are named however many there are"
    assert arranged.folded == {HIT: tuple(sorted(foldable))}


def test_one_thread_under_two_caps_is_two_groups_and_a_duplicate_key_is_one() -> None:
    arranged = arrange_groups([("t", HIT), ("t", POOL), ("t", HIT)], foldable={HIT}, bound=10)
    assert arranged.named == (("t", HIT), ("t", POOL))


def test_unranked_threads_follow_every_ranked_one_deterministically() -> None:
    keys = _keys(("z", POOL), ("m", POOL), ("a", HIT), ("k", HIT))
    arranged = arrange_groups(keys, foldable={HIT}, rank_of={"k": 3, "z": 1}, bound=10)
    assert arranged.named == (("z", POOL), ("k", HIT), ("a", HIT), ("m", POOL))
    again = arrange_groups(reversed(keys), foldable={HIT}, rank_of={"k": 3, "z": 1}, bound=10)
    assert again == arranged, "the order does not depend on the order the keys were given in"


def test_the_layout_counts_are_the_arrangements_counts() -> None:
    from mailweave.disclosure.layout import Layout

    keys = frozenset(
        [(f"p{i:02d}", POOL) for i in range(20)] + [(f"h{i:02d}", HIT) for i in range(10)]
    )
    layout = Layout(
        sources=(),
        accounted_ids=frozenset(),
        floor_ids=frozenset(),
        hit_ids=frozenset(),
        groups=keys,
        foldable_caps=frozenset({HIT}),
    )
    arranged = arrange_groups(keys, foldable={HIT})
    assert named_groups(layout) == len(arranged.named) == 24
    assert tail_entries(layout) == arranged.tail_count == 1


# --- R1 part 2: estimate against render, with a backend, on every round-27 shape ---------------


def _semantic_service(box: SyntheticMailbox) -> Any:
    vocabulary = sorted(
        {word for message in box.messages for word in message.body.lower().split()}
    )[:24]
    registry = BackendRegistry()
    backend = _WordBackend(vocabulary)
    registry.register("dummy", lambda made=backend: made, default=True)
    return _service(box, registry)


def _wire_groups(payload: dict[str, Any]) -> tuple[int, int]:
    return len(payload.get("withheld_groups", ())), len(payload.get("withheld_tail", ()))


@pytest.mark.parametrize(("name", "shape"), ESTIMATE_SHAPES, ids=[n for n, _ in ESTIMATE_SHAPES])
@pytest.mark.parametrize("backend", ("none", "word"))
def test_the_estimate_bounds_the_render_with_and_without_a_backend(
    name: str, shape: dict[str, int], backend: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Round 27's inequality, now with the semantic rung inside the matrix (R-M2-097): the
    ladder's estimate is at or above the rendered size, and the groups it charged are the
    groups the wire named, on every shape, whether or not a backend is registered."""
    captured = _CapturedLadder(monkeypatch)
    box = multi_thread_mailbox(**shape)
    service = make_service(box) if backend == "none" else _semantic_service(box)
    result = call(service, "mailweave_search", {"query": TERM})
    payload = structured_of(result)
    if captured.layout is None:
        assert result.is_error, (name, backend, "no layout and no decline")
        return
    estimate = captured.layout.chars()
    if result.is_error:
        assert "renders" not in str(payload.get("remediation", "")), (
            name,
            backend,
            "refused on render: the estimate admitted what the wire could not carry",
        )
        assert estimate > HOST_RESULT_CHAR_CAP or "carries no mail" in str(
            payload.get("remediation")
        )
        return
    mirrored = rendered_of(result)
    rendered = rendered_chars(mirrored.structured, mirrored.text)
    assert rendered <= HOST_RESULT_CHAR_CAP, (name, backend, rendered)
    assert estimate >= rendered, (name, backend, estimate, rendered, estimate - rendered)
    groups, tails = _wire_groups(payload)
    assert named_groups(captured.layout) == groups, (name, backend, "groups charged != named")
    assert tail_entries(captured.layout) == tails, (name, backend, "tails charged != written")


# --- R1 part 3: the causal mechanism, corpus-independent - a wide pool over lexical overflow --


def _wide_pool_mailbox(
    *, threads: int = 28, hit_threads: int = 27, hit_messages: int = 1, other_messages: int = 1
) -> SyntheticMailbox:
    """Many recent threads, a query term in the first `hit_threads` of them. Every thread is
    inside the pool's default recency window, so the pool's recency probe lists all of them;
    the term makes `hit_threads` of them hit-bearing. With more hit-bearing threads than the
    pool can read, some are overflow *and* pool candidates the pool never reads - the
    overlapping set R-M2-094 was found on; with large non-hit threads, the pool's own row cap
    fires and the pool-only threads are grouped under it."""
    now = datetime.now(UTC)
    rows: list[Msg] = []
    for thread in range(threads):
        thread_id = f"w{thread:03d}" + "f" * 11
        hit = thread < hit_threads
        for index in range(hit_messages if hit else other_messages):
            stamp = now - timedelta(days=1 + thread, minutes=index)
            body = (
                f"{TERM} update {thread} {index}: cadence review and the numbers we agreed"
                if hit and index == 0
                else f"plain note {thread} {index} about the depot roster and a calendar"
            )
            rows.append(
                Msg(
                    id=f"w{thread:03d}m{index:03d}" + "e" * 6,
                    thread_id=thread_id,
                    sender=f"a{thread % 5}@team.example",
                    subject="cadence review" if index == 0 else "Re: cadence review",
                    body=body,
                    internal_date_ms=int(stamp.timestamp() * 1000),
                    to=("b@team.example",),
                )
            )
    return SyntheticMailbox(messages=tuple(rows), now_ms=int(now.timestamp() * 1000))


def _hit_thread_ids(hit_threads: int) -> set[str]:
    return {f"w{thread:03d}" + "f" * 11 for thread in range(hit_threads)}


def _served_wide_pool(
    monkeypatch: pytest.MonkeyPatch, box: SyntheticMailbox, width: int
) -> tuple[dict[str, Any], Any]:
    captured = _CapturedLadder(monkeypatch)
    # The term is conclusive at L1, so D.3 rule 4 would not escalate to the pool on its own;
    # `force_rungs` is the published way to run the rung, and the property under test is
    # what the pool's bookkeeping does once it has run, not when it runs. The width is
    # narrowed so the response is served: the property is about what is served.
    result = call(
        _semantic_service(box),
        "mailweave_search",
        {"query": TERM, "force_rungs": ["L5"], "budget": {"max_hit_threads": width}},
    )
    payload = structured_of(result)
    assert not result.is_error, payload.get("remediation")
    assert "L5" in payload["retrieval_report"]["rungs"]
    assert captured.layout is not None
    mirrored = rendered_of(result)
    assert captured.layout.chars() >= rendered_chars(mirrored.structured, mirrored.text)
    groups, tails = _wire_groups(payload)
    assert named_groups(captured.layout) == groups, "groups charged != groups named"
    assert tail_entries(captured.layout) == tails, "tails charged != tails written"
    return payload, captured.layout


def test_a_thread_beyond_the_width_that_the_pool_never_read_keeps_the_width_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The overlapping set: a hit-bearing thread beyond `max_hit_threads` that the semantic
    pool also listed and never read is written under `max_hit_threads` - the cap that stopped
    it, whose groups fold - not under a pool note that never folds; and the estimate charged
    exactly the groups and tails the wire carries."""
    hit_threads = 27
    payload, _layout = _served_wide_pool(
        monkeypatch, _wide_pool_mailbox(hit_threads=hit_threads), 3
    )
    hit_bearing = _hit_thread_ids(hit_threads)
    sources = {source["thread_id"] for source in payload["sources"]}
    split = {e["thread_id"] for block in payload["not_included_sources"] for e in block["sources"]}
    overflow = hit_bearing - sources - split
    assert len(overflow) >= 20, "too few overflow threads to overlap the pool's reads"
    by_thread: dict[str, set[str]] = {}
    for group in payload["withheld_groups"]:
        by_thread.setdefault(group["thread_id"], set()).add(group["cap"])
    pool_read = payload["retrieval_report"]["pool"]["thread_count"]
    assert pool_read < len(hit_bearing), "the pool read every hit thread; nothing overlaps"
    for thread in overflow:
        assert by_thread.get(thread, {HIT.value}) == {HIT.value}, (thread, by_thread.get(thread))
    for tail in payload["withheld_tail"]:
        assert tail["cap"] == HIT.value
    named_overflow = sum(1 for thread in overflow if thread in by_thread)
    folded = sum(tail["thread_count"] for tail in payload["withheld_tail"])
    assert named_overflow + folded == len(overflow), (
        "an overflow thread is neither named nor folded"
    )


def test_pool_only_threads_are_named_under_the_pools_cap_and_charged_as_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Threads only the pool's recency probe listed - read and passed over by the shortlist,
    or never read past the pool's own caps - are groups under the pool's caps: always named,
    because no call widens those caps, and charged as named rather than foldable (the
    R-M2-094 under-charge). Every one of them is charged, and none is a hit-bearing thread."""
    box = _wide_pool_mailbox(threads=25, hit_threads=3, hit_messages=1, other_messages=20)
    payload, layout = _served_wide_pool(monkeypatch, box, 2)
    pool_only_caps = {
        POOL.value,
        WithheldCap.MAX_POOL_MESSAGES.value,
        WithheldCap.MAX_RERANK_PAIRS.value,
    }
    pool_caps = {
        group["thread_id"] for group in payload["withheld_groups"] if group["cap"] in pool_only_caps
    }
    assert pool_caps, "no pool-only thread was grouped under a pool cap; the shape proves nothing"
    assert all(cap.value not in pool_only_caps for cap in layout.foldable_caps)
    assert not (pool_caps & _hit_thread_ids(3)), "a hit-bearing thread under a pool cap"
    keys = {(group["thread_id"], group["cap"]) for group in payload["withheld_groups"]}
    assert {(thread, cap.value) for thread, cap in layout.groups} >= keys, (
        "the wire named a group the layout did not charge"
    )


def test_the_wide_pool_shape_is_never_refused_on_render(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whatever the ladder decides on a wide pool, it decides on an estimate the wire agrees
    with: the host-cap backstop (`declared_result`) never fires, because the estimate no
    longer counts as foldable what the wire names one by one. A decline here is the ladder's
    own, with a retry; a served response is inside the cap."""
    for threads, hit_threads, others in ((40, 16, 4), (60, 20, 1), (60, 5, 8), (28, 27, 1)):
        captured = _CapturedLadder(monkeypatch)
        box = _wide_pool_mailbox(threads=threads, hit_threads=hit_threads, other_messages=others)
        result = call(
            _semantic_service(box), "mailweave_search", {"query": TERM, "force_rungs": ["L5"]}
        )
        payload = structured_of(result)
        if result.is_error:
            assert "renders" not in str(payload.get("remediation", "")), (threads, hit_threads)
            assert payload.get("retry_with") is not None or payload.get("terminal"), (
                threads,
                hit_threads,
            )
            continue
        mirrored = rendered_of(result)
        rendered = rendered_chars(mirrored.structured, mirrored.text)
        assert rendered <= HOST_RESULT_CHAR_CAP
        assert captured.layout is not None and captured.layout.chars() >= rendered


# --- R2: the last evidence-bearing source of a search collapses before it leaves --------------
#
# R-M2-093. A.9a step 7's main loop cannot take a source holding floor members and step 8 may
# not touch one, so a search whose only remaining evidence-bearing source has protected rows
# that do not fit beside the fixed bookkeeping reached the last resort - which split the
# source off and emptied the answer, and `_carries_nothing` then refused it. The repair gives
# the last resort a first move: every row of that source goes to stub depth and collapses into
# declared runs, which A.7a counts as present. Search only: an explicit read's evidence is the
# map or the rows the caller named, and neither is ever collapsed by it.


class _CapturedRun:
    """The finished layout **and** the declared steps of a search's ladder run."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import mailweave.disclosure.plan as plan

        self.layout: Any = None
        self.steps: tuple[Any, ...] = ()
        original = plan.run_ladder

        def spy(layout: Any, **kwargs: Any) -> Any:
            finished, steps = original(layout, **kwargs)
            self.layout, self.steps = finished, steps
            return finished, steps

        monkeypatch.setattr(plan, "run_ladder", spy)


class _CollapseSpy:
    """Every call of the last resort's first move, with whether it changed the layout."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import mailweave.disclosure.ladder as ladder

        self.calls: list[tuple[str, bool]] = []
        original = ladder._last_source_to_runs

        def spy(layout: Any, source: Any) -> Any:
            out = original(layout, source)
            self.calls.append((source.thread_id, out is not layout))
            return out

        monkeypatch.setattr(ladder, "_last_source_to_runs", spy)


def _last_source_mailbox() -> SyntheticMailbox:
    """Thirty threads of five matching messages. Every row of the mapped thread is a hit and a
    floor member, the top five are protected at snippet depth (step 3), and the nineteen
    hit-bearing threads beyond a width of one are the fixed bookkeeping beside it - more than
    the cap leaves for five protected rows. No diagnostic case, evidence id or corpus position
    decides anything here; the shape is the mechanism's."""
    return multi_thread_mailbox(threads=30, per_thread=5, words=40)


def _first_search(service: Any, width: int = 1) -> Any:
    return call(service, "mailweave_search", {"query": TERM, "budget": {"max_hit_threads": width}})


def test_without_the_collapse_this_shape_empties_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shape exercises the repaired branch and nothing else: with the first move switched
    off, the last resort splits the only evidence-bearing source and the ladder refuses the
    emptied response - the pre-repair outcome, stated so the served response below is known
    to be the collapse's doing."""
    import mailweave.disclosure.ladder as ladder

    monkeypatch.setattr(ladder, "_last_source_to_runs", lambda layout, source: layout)
    result = _first_search(make_service(_last_source_mailbox()))
    payload = structured_of(result)
    assert result.is_error, "the shape no longer reaches the last resort"
    assert "carries no mail" in str(payload.get("remediation")), payload.get("remediation")


def test_the_last_evidence_bearing_source_collapses_into_runs_and_the_hits_survive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _CapturedRun(monkeypatch)
    spy = _CollapseSpy(monkeypatch)
    box = _last_source_mailbox()
    result = _first_search(make_service(box))
    payload = structured_of(result)
    assert not result.is_error, payload.get("remediation")
    assert spy.calls and any(changed for _, changed in spy.calls), "the first move never ran"
    layout = captured.layout
    assert layout is not None
    # Every hit the response kept is present, as a run member: nothing was split away.
    (source,) = payload["sources"]
    assert source["messages"] == [], "a protected row survived the collapse at depth"
    (run,) = source["collapsed_runs"]
    members = set(run["member_ids"])
    thread_of = {message.id: message.thread_id for message in box.messages}
    kept_hits = {mid for mid in layout.hit_ids if thread_of[mid] == source["thread_id"]}
    assert kept_hits and members >= kept_hits, sorted(kept_hits - members)
    assert layout.hit_ids & layout.present_ids >= frozenset(kept_hits)
    assert not layout.split_off, "the last resort split a source it had collapsed"
    assert run["count"] == len(run["member_ids"]) == source["included"]
    # The depth reduction is declared, on step 7, as what it was.
    seventh = [step for step in captured.steps if step.precedence == 7]
    assert seventh, [step.name for step in captured.steps]
    assert "collapsed into declared runs" in seventh[-1].detail, seventh[-1].detail
    assert "row(s) reduced in depth" in seventh[-1].detail, seventh[-1].detail
    assert "split off" not in seventh[-1].detail, seventh[-1].detail
    assert payload["truncated_by"] == "mailweave"
    assert payload["partial"] is True
    assert source["included_as_stub"] == source["included"]


def test_the_collapsed_hits_are_recoverable_by_the_calls_the_response_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Executable recovery: the run's own map call serves the thread, and the recommended
    read names every collapsed hit and returns each at the body depth evidence is read at."""
    box = _last_source_mailbox()
    service = make_service(box)
    payload = structured_of(_first_search(service))
    (source,) = payload["sources"]
    (run,) = source["collapsed_runs"]
    members = list(run["member_ids"])
    mapped = structured_of(
        call(service, run["affordance"]["tool"], dict(run["affordance"]["args"]))
    )
    assert mapped.get("remediation") is None, mapped.get("remediation")
    (mapped_source,) = mapped["sources"]
    listed = {row["id"] for row in mapped_source["messages"]} | {
        mid for one in mapped_source.get("collapsed_runs", ()) for mid in one["member_ids"]
    }
    assert listed >= set(members)
    reads = [
        offer
        for offer in payload["affordances"]
        if offer["tool"] == "mailweave_get_messages"
        and set(offer["args"].get("message_ids", ())) >= set(members)
    ]
    assert reads, "no recommended read names the collapsed hits"
    read = structured_of(call(service, "mailweave_get_messages", dict(reads[0]["args"])))
    rows = {row["id"]: row for src in read["sources"] for row in src["messages"]}
    assert set(rows) >= set(members), sorted(set(members) - set(rows))
    for mid in members:
        assert rows[mid]["depth"] in ("body_clean", "body_full"), (mid, rows[mid]["depth"])
        assert rows[mid]["content"]["text"]


def test_run_membership_is_surfaced_but_never_counted_as_content_in_hand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The harness's own rule (EP §6.1), applied to the served shape: the members are
    surfaced ids the driver may follow, and none of them is content delivered."""
    from mailweave_harness.evaluation.boundary import Served

    payload = structured_of(_first_search(make_service(_last_source_mailbox())))
    served = Served(tool="mailweave_search", args={"query": TERM}, payload=payload)
    (source,) = payload["sources"]
    members = frozenset(source["collapsed_runs"][0]["member_ids"])
    assert served.surfaced_ids() >= members
    assert not (set(served.content_by_id()) & members)
    assert served.offers(members), "the run offers no call for its members"


def test_explicit_reads_of_the_same_thread_are_never_collapsed_by_the_first_move(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The explicit-read contract stands: a map of the thread and a named read of its
    messages, through the same server, are served as the request asked, and the first move
    changes no layout on either path."""
    spy = _CollapseSpy(monkeypatch)
    box = _last_source_mailbox()
    service = make_service(box)
    payload = structured_of(_first_search(service))
    (source,) = payload["sources"]
    members = list(source["collapsed_runs"][0]["member_ids"])
    thread_id = source["thread_id"]
    spy.calls.clear()
    mapped = structured_of(call(service, "mailweave_thread_map", {"thread_id": thread_id}))
    assert mapped.get("remediation") is None, mapped.get("remediation")
    assert {row["id"] for row in mapped["sources"][0]["messages"]} >= set(members), (
        "the map did not list the thread's rows as rows"
    )
    for view in ("stub", "body_clean"):
        read = structured_of(
            call(service, "mailweave_get_messages", {"message_ids": members, "view": view})
        )
        assert read.get("remediation") is None, (view, read.get("remediation"))
        rows = {row["id"]: row for src in read["sources"] for row in src["messages"]}
        assert set(rows) == set(members), (view, sorted(set(members) ^ set(rows)))
        assert all(row["depth"] == view for row in rows.values()), (
            view,
            {mid: row["depth"] for mid, row in rows.items()},
        )
        assert not any(src.get("collapsed_runs") for src in read["sources"]), view
    assert not any(changed for _, changed in spy.calls), spy.calls


def test_the_first_move_leaves_a_map_and_a_requested_row_alone() -> None:
    """Directly, on the layout: with `evidence_is_the_map` the function returns the very
    layout it was given; in a search layout a `Band.REQUESTED` row keeps its depth while its
    neighbours go to stub and collapse around it."""
    from mailweave.disclosure.ladder import _last_source_to_runs
    from mailweave.disclosure.layout import Band, Layout, PlannedRow, PlannedSource
    from mailweave.envelope.vocab import Depth

    def row(index: int, band: Band) -> PlannedRow:
        return PlannedRow(
            id=f"m{index}",
            position=index,
            band=band,
            depth=Depth.BODY_CLEAN,
            body=f"body {index} " * 20,
            snippet=f"snippet {index}",
        )

    rows = tuple(row(i, Band.REQUESTED if i == 2 else Band.EVIDENCE) for i in range(6))
    source = PlannedSource(thread_id="t", rank=0, hit_bearing=True, rows=rows)
    ids = frozenset(r.id for r in rows)
    search = Layout(sources=(source,), accounted_ids=ids, floor_ids=ids, hit_ids=ids)
    read = replace(search, evidence_is_the_map=True)
    assert _last_source_to_runs(read, source) is read

    collapsed = _last_source_to_runs(search, source)
    (rebuilt,) = collapsed.sources
    requested = [r for r in rebuilt.rows if r.band is Band.REQUESTED]
    assert [r.id for r in requested] == ["m2"]
    assert requested[0].depth is Depth.BODY_CLEAN
    assert all(r.band is Band.REQUESTED for r in rebuilt.rows), "a non-requested row kept depth"
    run_members = {mid for run in rebuilt.runs for mid in run.member_ids}
    assert run_members == ids - {"m2"}
    assert [(run.start, run.end) for run in rebuilt.runs] == [(0, 1), (3, 5)]
    assert rebuilt.present_ids == ids, "a row vanished in the collapse"


# --- R3: the refusal says what it was made of, and the retry reduces that -------------------
#
# R-M2-095. `DisclosureLadderExhausted` carried a message, the top thread and the width, and
# the recovery halved `max_hit_threads` on every search decline whatever the ladder had
# refused for - three declines at the same refusal, then the map, on every lost semantic case.
# Now the refusal carries a `RefusalCause`: the binding unit and cap, the refused layout's cost
# by term, the groups by cap, the top thread's smallest inventory, and the ladder's own answer
# at every narrower width. The retry is the widest width that fits, and when none does the
# hop to the map is declared a change of scope.


def _broad_query_mailbox(
    *, threads: int = 45, top: int = 60, others: int = 1, words: int = 30, id_chars: int = 16
) -> SyntheticMailbox:
    """R-M2-076's shape without a corpus: one thread of `top` matching messages that ranks
    first, and `threads - 1` more matching threads of `others` each. Twelve are mapped, the
    rest are groups, and the ladder splits every mapped source but the first; the first,
    collapsed to one run, still does not fit beside the bookkeeping the width leaves - an
    emptiness refusal at the published width whose cause is a *width* the ladder can name.

    **Message ids at Gmail's own width, 16, rather than 20 (2026-09-22).** Every row and every
    run member is charged its id several times over, and when the text mirror gained each
    row's attribution and chronology lines the widest width that fits the retry's fixture
    fell from 6 to 5 of an applied 11 - exactly the halving
    `test_the_retry_is_the_widest_width_that_fits_and_keeps_every_other_argument` holds the
    retry to beat. Measured: at 16 the widest width is 6 again, at 12 it is 7, and at 20 it is
    5; the applied width stays 11 (the call budget still stops the mapping one short) and
    the other two tests' shapes are unchanged. A 20-character id was wider than any Gmail
    issues, so the fixture moved toward the real width, not away from it."""
    now = datetime.now(UTC)
    rows: list[Msg] = []
    for thread in range(threads):
        for index in range(top if thread == 0 else others):
            stamp = now - timedelta(days=1 + thread, minutes=index)
            rows.append(
                Msg(
                    id=(f"m{thread:03d}{index:04d}" + "e" * id_chars)[:id_chars],
                    thread_id=f"th{thread:03d}" + "f" * 11,
                    sender=f"a{thread % 4}@team.example",
                    subject=f"{TERM} thread {thread}" if index == 0 else f"Re: {TERM} thread",
                    body=" ".join([TERM, *(f"w{(index + k) % 17}" for k in range(words))]),
                    internal_date_ms=int(stamp.timestamp() * 1000),
                    to=("b@team.example",),
                )
            )
    return SyntheticMailbox(messages=tuple(rows), now_ms=int(now.timestamp() * 1000))


def _inventory_too_large_mailbox() -> SyntheticMailbox:
    """Five small matching threads, newest first, and one of nine hundred matching messages
    that ranks first. Its inventory alone - nine hundred run members - is over the cap, so no
    width of the search fits: the honest retry changes tool, and says so."""
    now = datetime.now(UTC)
    rows: list[Msg] = []

    def message(thread: int, index: int, body: str, days: int) -> Msg:
        stamp = now - timedelta(days=days, minutes=index)
        return Msg(
            id=(f"m{thread:03d}{index:04d}" + "e" * 20)[:20],
            thread_id=f"th{thread:03d}" + "f" * 11,
            sender="a@team.example",
            subject=f"{TERM} note",
            body=body,
            internal_date_ms=int(stamp.timestamp() * 1000),
            to=("b@team.example",),
        )

    for thread in range(1, 6):
        rows.append(message(thread, 0, f"{TERM} short note {thread}", 1))
    for index in range(900):
        rows.append(message(0, index, f"{TERM} entry {index} of the long log", 10))
    return SyntheticMailbox(messages=tuple(rows), now_ms=int(now.timestamp() * 1000))


def _declined(service: Any, args: dict[str, Any]) -> dict[str, Any]:
    result = call(service, "mailweave_search", args)
    payload = structured_of(result)
    assert result.is_error, "the shape no longer declines; it proves nothing"
    return payload


def test_a_refusal_carries_its_cause_in_the_binding_unit_with_its_terms_and_its_table() -> None:
    payload = _declined(make_service(_broad_query_mailbox()), {"query": TERM})
    cause = payload["cause"]
    assert cause["kind"] == "empty"
    assert cause["unit"] == "chars" and cause["cap"] == HOST_RESULT_CHAR_CAP
    terms = cause["terms"]
    assert terms["unit"] == "chars"
    assert terms["sources"] == 0, "an emptiness refusal carries no source"
    assert terms["total"] == sum(
        terms[key]
        for key in (
            "structural",
            "echo",
            "expansion",
            "sources",
            "records",
            "groups",
            "tails",
            "not_included",
        )
    )
    assert terms["groups"] > 0 and terms["not_included"] > 0, terms
    assert cause["groups_by_cap"].get(CEIL.value, 0) >= 1, cause["groups_by_cap"]
    assert cause["groups_by_cap"].get(HIT.value, 0) >= 1, cause["groups_by_cap"]
    assert cause["width"] == MAX_HIT_THREADS
    assert cause["top_thread"] == cause["residual_thread"]
    assert cause["residual"] is not None and cause["residual"] > 0
    # The one thing an emptiness flag could not say: which term did not fit.
    assert terms["total"] + cause["residual"] > cause["cap"]
    assert terms["total"] <= cause["cap"], "the bookkeeping alone fitted; the residual did not"
    widths = {int(w) for w in cause["fits_at"]} | set(cause["refused_at"])
    assert widths == set(range(1, MAX_HIT_THREADS)), sorted(widths)
    assert all(cost <= cause["cap"] for cost in cause["fits_at"].values())
    for sentence in ("The bookkeeping alone is", "smallest inventory"):
        assert sentence in payload["remediation"], payload["remediation"]


def test_the_causes_table_is_what_the_real_call_does_at_each_width() -> None:
    """`fits_at` is the ladder run over a hypothetical; this holds it against the shipped
    producer at every width it names: where the table says the search fits, the real call
    serves inside the cap, and where it says the ladder refused, the real call declines."""
    box = _broad_query_mailbox()
    payload = _declined(make_service(box), {"query": TERM})
    cause = payload["cause"]
    assert cause["fits_at"] and cause["refused_at"], "a table with only one answer proves less"
    for width, cost in cause["fits_at"].items():
        result = call(
            make_service(box),
            "mailweave_search",
            {"query": TERM, "budget": {"max_hit_threads": int(width)}},
        )
        assert not result.is_error, (width, structured_of(result).get("remediation"))
        mirrored = rendered_of(result)
        assert rendered_chars(mirrored.structured, mirrored.text) <= HOST_RESULT_CHAR_CAP
        assert cost <= cause["cap"]
    for width in cause["refused_at"]:
        result = call(
            make_service(box),
            "mailweave_search",
            {"query": TERM, "budget": {"max_hit_threads": int(width)}},
        )
        assert result.is_error, (width, "the table said refused; the call served")


def test_the_retry_is_the_widest_width_that_fits_and_keeps_every_other_argument() -> None:
    args = {
        "query": TERM,
        "view": "snippet",
        "scan": {"max_pages": 2},
        "budget": {"max_hit_threads": MAX_HIT_THREADS, "max_api_calls": 40},
    }
    payload = _declined(make_service(_broad_query_mailbox()), args)
    cause = payload["cause"]
    # The width in effect is the cause's, not the argument's: the call budget beside the
    # width can stop the mapping short of it, and the dimension narrowed is the one in effect.
    applied = cause["width"]
    widest = max(int(w) for w, cost in cause["fits_at"].items() if cost <= cause["cap"])
    narrowing = payload["narrowing"]
    assert narrowing == {
        "dimension": "max_hit_threads",
        "applied": applied,
        "proposed": widest,
        "kind": "narrower",
    }
    assert widest > applied // 2, "the halving would have given up more scope"
    retry = payload["retry_with"]
    assert retry["tool"] == "mailweave_search"
    assert retry["args"] == {
        **args,
        "budget": {"max_hit_threads": widest, "max_api_calls": 40},
    }
    assert "widest width" in payload["remediation"]


def test_when_no_width_fits_the_hop_is_a_declared_change_of_scope() -> None:
    box = _inventory_too_large_mailbox()
    payload = _declined(make_service(box), {"query": TERM})
    cause = payload["cause"]
    assert cause["kind"] == "empty" and cause["width"] > 1
    assert not cause["fits_at"]
    assert set(cause["refused_at"]) == set(range(1, cause["width"]))
    assert cause["residual"] > cause["cap"], "the inventory alone is over the cap"
    assert payload["narrowing"] == {
        "dimension": "tool",
        "applied": "mailweave_search",
        "proposed": "mailweave_thread_map",
        "kind": "scope_change",
    }
    assert payload["retry_with"] == {
        "tool": "mailweave_thread_map",
        "args": {"thread_id": cause["top_thread"]},
    }
    text = payload["remediation"]
    assert "change of scope" in text and "not accounted for" in text, text
    assert f"{cause['width'] - 1} hit-bearing thread(s)" in text, text


def test_the_directed_chain_makes_progress_within_the_budgets_the_halving_had() -> None:
    """Progress without a wider budget: from the same decline, the cause-directed chain
    reaches a served response in one hop where the pure halving schedule needs more, and
    the served response keeps more of the search's width. Both chains run through the
    shipped server; the halving one is the schedule without a cause, as `narrower_call`
    still produces it."""
    from mailweave.surface.recovery import narrower_call
    from mailweave_harness.evaluation.arms import MAX_RECOVERY_ROUNDS

    box = _broad_query_mailbox()
    first = _declined(make_service(box), {"query": TERM})
    # Directed: follow the wire.
    directed_hops = 0
    result = call(make_service(box), "mailweave_search", {"query": TERM})
    args: dict[str, Any] = {"query": TERM}
    while result.is_error:
        retry = structured_of(result)["retry_with"]
        assert retry is not None and retry["tool"] == "mailweave_search"
        args = dict(retry["args"])
        result = call(make_service(box), "mailweave_search", args)
        directed_hops += 1
        assert directed_hops <= MAX_RECOVERY_ROUNDS
    directed_width = len(structured_of(result)["sources"]) + sum(
        len(block["sources"]) for block in structured_of(result)["not_included_sources"]
    )
    # Halving: the schedule without a cause, executed against the same server.
    halving_hops = 0
    args = {"query": TERM}
    result = call(make_service(box), "mailweave_search", args)
    while result.is_error:
        step = narrower_call(
            "mailweave_search",
            args,
            top_thread=first["cause"]["top_thread"],
            hit_threads=structured_of(result)["cause"]["width"],
        )
        assert step is not None and step.affordance.tool.value == "mailweave_search"
        args = dict(step.affordance.args)
        result = call(make_service(box), "mailweave_search", args)
        halving_hops += 1
        assert halving_hops <= MAX_RECOVERY_ROUNDS
    halving_width = len(structured_of(result)["sources"]) + sum(
        len(block["sources"]) for block in structured_of(result)["not_included_sources"]
    )
    assert directed_hops == 1, directed_hops
    assert directed_hops <= halving_hops
    assert directed_width >= halving_width, (directed_width, halving_width)
    assert directed_width > MAX_HIT_THREADS // 2


def test_a_cause_directs_the_recovery_without_a_server() -> None:
    """The pure choice, on a hand-made cause: the widest fitting width under the applied one,
    or - refused everywhere - the map as a scope change; and a cause with no table leaves
    the halving schedule exactly as it was."""
    from mailweave.disclosure.ladder import RefusalCause, RefusalKind
    from mailweave.disclosure.layout import CostTerms
    from mailweave.surface.recovery import (
        NarrowingKind,
        narrower_call,
        widest_width_that_fits,
    )

    terms = CostTerms(
        unit="chars",
        structural=2600,
        echo=2000,
        expansion=0,
        sources=0,
        records=0,
        groups=12000,
        tails=600,
        not_included=4600,
    )

    def cause(**table: Any) -> RefusalCause:
        return RefusalCause(
            kind=RefusalKind.EMPTY,
            unit="chars",
            cap=25_000,
            terms=terms,
            groups_by_cap={},
            folded_by_cap={},
            width=12,
            top_thread="top",
            residual_thread="top",
            residual=3_500,
            fits_at=table.get("fits_at", {}),
            refused_at=table.get("refused_at", ()),
        )

    fits = cause(fits_at={3: 24_000, 5: 24_900, 7: 25_100, 11: 24_990}, refused_at=(10, 9, 8))
    assert widest_width_that_fits(fits, below=12) == 11
    assert widest_width_that_fits(fits, below=11) == 5, "7 is over the cap; 5 is the widest under"
    assert widest_width_that_fits(fits, below=3) is None
    args = {"query": "q", "view": "snippet", "budget": {"max_hit_threads": 12}}
    step = narrower_call("mailweave_search", args, top_thread="top", hit_threads=12, cause=fits)
    assert step is not None
    assert step.affordance.args == {**args, "budget": {"max_hit_threads": 11}}
    assert step.narrowing.proposed == 11 and step.narrowing.kind is NarrowingKind.NARROWER
    assert "widest width" in step.why

    none = cause(refused_at=tuple(range(11, 0, -1)))
    step = narrower_call("mailweave_search", args, top_thread="top", hit_threads=12, cause=none)
    assert step is not None
    assert step.affordance.tool.value == "mailweave_thread_map"
    assert step.narrowing.kind is NarrowingKind.SCOPE_CHANGE
    assert "change of scope" in step.why and "11 hit-bearing thread(s)" in step.why
    assert (
        narrower_call("mailweave_search", args, top_thread=None, hit_threads=12, cause=none) is None
    ), "no width fits and there is no thread to map: the chain ends"

    blank = cause()
    step = narrower_call("mailweave_search", args, top_thread="top", hit_threads=12, cause=blank)
    assert step is not None and step.narrowing.proposed == 6, "no table: the halving schedule"
    assert step.why == ""


# --- R4: retrieval's rank on the offers, and a walk that follows it --------------------------
#
# R-M2-096. Withheld groups were written sorted by thread id and split-off sources in the order
# step 7 split them, and the driver walked groups before not-included sources: a thread's place
# in the walk was its id's alphabetical position and the block it landed in. Both entry kinds
# now carry `rank` - the retrieval's own order for the threads that had one - the wire writes
# ranked entries in that order, and the driver walks both kinds as one sequence by rank, the
# unranked after, in the order listed.


def test_the_wire_carries_retrieval_rank_and_writes_ranked_entries_in_that_order() -> None:
    payload = structured_of(
        call(
            make_service(_broad_query_mailbox()),
            "mailweave_search",
            {"query": TERM, "budget": {"max_hit_threads": 4}},
        )
    )
    assert payload.get("remediation") is None, payload.get("remediation")
    entries = [e for block in payload["not_included_sources"] for e in block["sources"]]
    groups = payload["withheld_groups"]
    assert entries and groups
    entry_ranks = [e["rank"] for e in entries]
    assert all(isinstance(rank, int) for rank in entry_ranks)
    assert entry_ranks == sorted(entry_ranks), "split-off sources are not in rank order"
    ranked_groups = [g["rank"] for g in groups if g.get("rank") is not None]
    assert ranked_groups == sorted(ranked_groups), "ranked groups are not in rank order"
    # A thread mapped and then split off ranks above every thread the width cap left unmapped.
    overflow = [g["rank"] for g in groups if g["cap"] == HIT.value]
    assert overflow and max(entry_ranks) < min(overflow)
    # The mapped source itself outranks them all.
    assert min(entry_ranks) > 0 and payload["sources"][0]["thread_id"] not in {
        e["thread_id"] for e in entries
    }


def test_pool_only_groups_have_no_rank_and_follow_every_ranked_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    box = _wide_pool_mailbox(threads=25, hit_threads=3, hit_messages=1, other_messages=20)
    payload, _layout = _served_wide_pool(monkeypatch, box, 2)
    groups = payload["withheld_groups"]
    pool_caps = {
        POOL.value,
        WithheldCap.MAX_POOL_MESSAGES.value,
        WithheldCap.MAX_RERANK_PAIRS.value,
    }
    ranks = [g.get("rank") for g in groups]
    assert any(g["cap"] in pool_caps for g in groups), "no pool-only group; proves nothing"
    for group in groups:
        if group["cap"] in pool_caps:
            assert group.get("rank") is None, group
    first_unranked = next(i for i, rank in enumerate(ranks) if rank is None)
    assert all(rank is not None for rank in ranks[:first_unranked])
    assert all(rank is None for rank in ranks[first_unranked:]), ranks


def test_the_driver_walks_groups_and_entries_as_one_sequence_by_rank_then_the_unranked() -> None:
    """On a hand-made wire: scrambled ranks across both blocks, an unranked group and an
    unranked entry, a wanted id in a run. The walk is by rank across both blocks; the
    unranked follow in the order listed; the known-target offers come first and do not
    reorder the walk; and the same wire walks the same way twice."""
    from mailweave_harness.evaluation.arms import in_retrieval_order
    from mailweave_harness.evaluation.boundary import Served

    def offer(thread: str) -> dict[str, Any]:
        return {"tool": "mailweave_thread_map", "args": {"thread_id": thread}}

    payload = {
        "fence_nonce": "mw-test",
        "sources": [
            {
                "thread_id": "src",
                "messages": [],
                "collapsed_runs": [
                    {
                        "positions": [0, 1],
                        "count": 2,
                        "member_ids": ["want", "other"],
                        "affordance": offer("src"),
                    }
                ],
            }
        ],
        "withheld": [],
        "continuations": [],
        "withheld_groups": [
            {
                "thread_id": "g-rank5",
                "cap": "max_hit_threads",
                "rank": 5,
                "affordance": offer("g5"),
            },
            {"thread_id": "g-none-a", "cap": "max_pool_threads", "affordance": offer("ga")},
            {
                "thread_id": "g-rank1",
                "cap": "max_hit_threads",
                "rank": 1,
                "affordance": offer("g1"),
            },
            {
                "thread_id": "g-none-b",
                "cap": "max_pool_threads",
                "rank": None,
                "affordance": offer("gb"),
            },
        ],
        "not_included_sources": [
            {
                "why": "split",
                "sources": [
                    {"thread_id": "n-rank3", "rank": 3, "affordance": offer("n3")},
                    {"thread_id": "n-rank0", "rank": 0, "affordance": offer("n0")},
                    {"thread_id": "n-none", "affordance": offer("nn")},
                ],
            }
        ],
        "affordances": [{"tool": "mailweave_search", "args": {"query": "q"}}],
    }
    served = Served(tool="mailweave_search", args={"query": "q"}, payload=payload)
    walk = [o["args"].get("thread_id", o["tool"]) for o in served.offers(frozenset())]
    assert walk == ["n0", "g1", "n3", "g5", "ga", "gb", "nn", "mailweave_search"]
    assert walk == [o["args"].get("thread_id", o["tool"]) for o in served.offers(frozenset())]
    known = [o["args"].get("thread_id", o["tool"]) for o in served.offers(frozenset({"want"}))]
    assert known[:2] == ["src", "mailweave_get_messages"], known
    assert known[2:] == walk, "a wanted id changed the discovery walk"
    assert in_retrieval_order([(2, "b"), (None, "z"), (0, "a"), (2, "b2"), (None, "y")]) == [
        "a",
        "b",
        "b2",
        "z",
        "y",
    ]


# --- The independent review's findings (2026-09-15), held ------------------------------------


def _inventory_too_large_ranked_last_mailbox() -> SyntheticMailbox:
    """The review's F1 shape: the nine-hundred-message thread carries the *last* thread id,
    so the producer's cut order (`th000`..`th004`, then `th005`) and the ranking's order
    (`th005` first - the thread with by far the most hits) disagree. At every narrower
    width the producer maps small threads only and serves; a table that demoted by rank
    kept `th005` and refused at every width, and the chain ended in a terminal map."""
    now = datetime.now(UTC)
    rows: list[Msg] = []

    def message(thread: int, index: int, body: str, days: int) -> Msg:
        stamp = now - timedelta(days=days, minutes=index)
        return Msg(
            id=(f"m{thread:03d}{index:04d}" + "e" * 20)[:20],
            thread_id=f"th{thread:03d}" + "f" * 11,
            sender="a@team.example",
            subject=f"{TERM} note",
            body=body,
            internal_date_ms=int(stamp.timestamp() * 1000),
            to=("b@team.example",),
        )

    for thread in range(5):
        rows.append(message(thread, 0, f"{TERM} short note {thread}", 1))
    for index in range(900):
        rows.append(message(5, index, f"{TERM} entry {index} of the long log", 10))
    return SyntheticMailbox(messages=tuple(rows), now_ms=int(now.timestamp() * 1000))


def _table_matches_the_real_call(box: SyntheticMailbox, args: dict[str, Any]) -> dict[str, Any]:
    payload = _declined(make_service(box), args)
    cause = payload["cause"]
    for width in cause["fits_at"]:
        result = call(
            make_service(box),
            "mailweave_search",
            {**args, "budget": {**args.get("budget", {}), "max_hit_threads": int(width)}},
        )
        assert not result.is_error, (
            width,
            "table: fits; call:",
            structured_of(result).get("remediation"),
        )
    for width in cause["refused_at"]:
        result = call(
            make_service(box),
            "mailweave_search",
            {**args, "budget": {**args.get("budget", {}), "max_hit_threads": int(width)}},
        )
        assert result.is_error, (width, "table: refused; call: served")
    return payload


def test_the_table_follows_the_producers_cut_order_not_the_rankings_order() -> None:
    """Review F1. The width cap cuts the producer's order; the ranking reorders the mapped
    threads afterwards. The hypothetical demotes by the cut order (`mapped_at`), so its
    answer is the real call's at every width - here, every narrower width serves - and the
    retry is a narrower search, never a scope change to a map that would decline."""
    payload = _table_matches_the_real_call(
        _inventory_too_large_ranked_last_mailbox(), {"query": TERM}
    )
    cause = payload["cause"]
    assert cause["width"] > 1
    assert not cause["refused_at"], cause["refused_at"]
    assert {int(w) for w in cause["fits_at"]} == set(range(1, cause["width"]))
    assert payload["narrowing"]["dimension"] == "max_hit_threads"
    assert payload["narrowing"]["kind"] == "narrower"
    assert payload["narrowing"]["proposed"] == cause["width"] - 1
    assert payload["retry_with"]["tool"] == "mailweave_search"


def test_a_source_outside_the_cut_is_never_demoted_and_a_layout_without_a_cut_has_no_table() -> (
    None
):
    from mailweave.disclosure.ladder import _initial_at_width
    from mailweave.disclosure.layout import Band, Layout, PlannedRow, PlannedSource
    from mailweave.envelope.vocab import Depth

    def source(thread: str, rank: int, mapped_at: int | None) -> PlannedSource:
        row = PlannedRow(id=f"{thread}-m", position=0, band=Band.EVIDENCE, depth=Depth.STUB)
        return PlannedSource(
            thread_id=thread, rank=rank, hit_bearing=True, rows=(row,), mapped_at=mapped_at
        )

    # Ranked first, cut last: demoted at every width below 3; the sibling (no cut order) never.
    sources = (source("big", 0, 2), source("a", 1, 0), source("b", 2, 1), source("sib", 3, None))
    ids = frozenset(f"{s.thread_id}-m" for s in sources)
    layout = Layout(sources=sources, accounted_ids=ids, floor_ids=frozenset(), hit_ids=ids)
    at_two = _initial_at_width(layout, 2)
    assert at_two is not None
    assert [s.thread_id for s in at_two.sources] == ["a", "b", "sib"]
    assert "big-m" not in at_two.hit_ids and "big-m" in at_two.grouped_ids
    assert ("big", HIT) in at_two.groups
    assert _initial_at_width(layout, 3) is None, "nothing demoted is not a narrower width"
    unranked = Layout(
        sources=tuple(source(t, i, None) for i, t in enumerate("xyz")),
        accounted_ids=ids,
        floor_ids=frozenset(),
        hit_ids=ids,
    )
    assert _initial_at_width(unranked, 1) is None


def _last_hits_without_a_floor_mailbox() -> SyntheticMailbox:
    """The review's F2 shape: one twenty-message thread with no reply headers, so its four
    matching messages have no floor beside them and step 8 may withhold them; long enough
    bodies that they are the room's problem; thirty one-message matching threads for the
    bookkeeping. At width 2 with `view: body_clean`, step 8 used to withhold the four hits
    one record at a time and hand the emptiness gate a response the last resort would have
    collapsed into one run and served."""
    now = datetime.now(UTC)
    rows: list[Msg] = []
    filler = " ".join(f"w{k % 23}" for k in range(120))
    for index in range(20):
        stamp = now - timedelta(days=1, minutes=index)
        rows.append(
            Msg(
                id=(f"t000m{index:04d}" + "e" * 20)[:20],
                thread_id="t000" + "f" * 12,
                sender="a@team.example",
                subject="log",
                body=f"{TERM} {filler}" if index < 4 else f"plain {filler}",
                internal_date_ms=int(stamp.timestamp() * 1000),
                to=("b@team.example",),
            )
        )
    for thread in range(1, 31):
        stamp = now - timedelta(days=2 + thread)
        rows.append(
            Msg(
                id=(f"t{thread:03d}m0000" + "e" * 20)[:20],
                thread_id=f"t{thread:03d}" + "f" * 12,
                sender="a@team.example",
                subject=f"{TERM} note",
                body=f"{TERM} note {thread}",
                internal_date_ms=int(stamp.timestamp() * 1000),
                to=("b@team.example",),
            )
        )
    return SyntheticMailbox(messages=tuple(rows), now_ms=int(now.timestamp() * 1000))


def test_step_8_never_withholds_the_last_matched_message_and_the_collapse_is_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review F2. The rule the emptiness gate states is applied at step 8 too: a hit leaves
    only while another hit stays present. So `_step_8_would_fit` no longer answers yes by
    emptying the answer, the last resort collapses the source, and the response is served
    with the hits as run members rather than refused as empty."""
    captured = _CapturedRun(monkeypatch)
    spy = _CollapseSpy(monkeypatch)
    box = _last_hits_without_a_floor_mailbox()
    result = call(
        make_service(box),
        "mailweave_search",
        {"query": TERM, "budget": {"max_hit_threads": 2}, "view": "body_clean"},
    )
    payload = structured_of(result)
    assert not result.is_error, payload.get("remediation")
    assert any(changed for _, changed in spy.calls), "the collapse was never reached"
    layout = captured.layout
    assert layout is not None
    assert layout.hit_ids & layout.present_ids, "no hit present on a served response"
    top = next(source for source in payload["sources"] if source["thread_id"].startswith("t000"))
    members = {mid for run in top["collapsed_runs"] for mid in run["member_ids"]}
    hits_in_top = {mid for mid in layout.hit_ids if mid.startswith("t000m")}
    assert hits_in_top and hits_in_top <= members, sorted(hits_in_top - members)
    assert not [record for record in payload["withheld"] if record["id"] in hits_in_top]
    mirrored = rendered_of(result)
    assert rendered_chars(mirrored.structured, mirrored.text) <= HOST_RESULT_CHAR_CAP


def test_step_8_alone_keeps_one_hit_present_on_the_layout() -> None:
    """Directly: step 8 asked to take everything it may leaves the last present hit."""
    from mailweave.disclosure.ladder import Ceilings, step_8_withheld_record
    from mailweave.disclosure.layout import Band, Layout, PlannedRow, PlannedSource
    from mailweave.envelope.vocab import Depth

    rows = tuple(
        PlannedRow(
            id=f"m{i}",
            position=i,
            band=Band.EVIDENCE,
            depth=Depth.BODY_CLEAN,
            body=" ".join(f"w{k}" for k in range(80)),
            snippet="s",
        )
        for i in range(4)
    )
    source = PlannedSource(thread_id="t", rank=0, hit_bearing=True, rows=rows)
    ids = frozenset(r.id for r in rows)
    layout = Layout(
        sources=(source,), accounted_ids=ids, floor_ids=frozenset(), hit_ids=ids, ceiling_applied=1
    )
    taken = step_8_withheld_record(layout, Ceilings(normal=1, overflow=1, host_chars=1))
    assert len(taken.hit_ids & taken.present_ids) == 1
    assert set(taken.withheld_ids) == ids - (taken.hit_ids & taken.present_ids)


def test_the_estimate_arranges_the_groups_by_the_rank_the_ledger_writes_them_by() -> None:
    """Review F4. With two foldable caps, which keys fold - and so how many tails there are -
    depends on the order; the layout carries the ledger's ranks so the estimate counts the
    arrangement the wire writes."""
    from mailweave.disclosure.layout import Layout, named_groups, tail_entries

    src = WithheldCap.MAX_SOURCE_THREADS
    keys = frozenset(
        [("x", HIT), ("y", src), ("z", src)] + [(f"p{i:02d}", POOL) for i in range(23)]
    )
    unranked = Layout(
        sources=(),
        accounted_ids=frozenset(),
        floor_ids=frozenset(),
        groups=keys,
        foldable_caps=frozenset({HIT, src}),
    )
    ranked = replace(unranked, ranks=(("y", 0),))
    assert named_groups(unranked) == named_groups(ranked) == MAX_WITHHELD_GROUPS_NAMED
    assert tail_entries(unranked) == 1 and tail_entries(ranked) == 2
    for layout in (unranked, ranked):
        arranged = arrange_groups(
            layout.groups, foldable=layout.foldable_caps, rank_of=dict(layout.ranks)
        )
        assert tail_entries(layout) == arranged.tail_count
