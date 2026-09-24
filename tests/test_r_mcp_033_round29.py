"""R-MCP-033, certified: the bookkeeping-overflow class, closed by execution (round 29).

Two shapes, because the finding had two forms and the round found a third on the way:

  * **the live shape** - forty-five messages across a few threads that `max_hit_threads`
    capped away, which came back from the real mailbox on 2026-09-08 as forty-five
    per-message records, zero rows, zero sources, and a refusal (`validation-records/`);
  * **many single-message threads** - where grouping cannot help (a group of one costs more
    than naming it) and what overflowed instead was `not_included_sources[]`, sixteen entries
    each carrying its own copy of one 253-character sentence.

The third form was the `partial_source_failure` reason, which embedded a list of ids and was
copied onto every record of its thread; it is bounded now and certified in
`test_omission_sizing_round29.py`.

**REG-01 / REG-02.** `test_the_live_shape_*` fails against `5e86229`, the last commit before
this round: the same call declines there with `budget_exhausted`. The demonstration is
recorded in `docs/reviews/ROUND_29/IMPLEMENTER.md`.

Every assertion here is about the wire a client receives, through the shipped `call`. No
fixture carries real or realistic mail.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

from mailweave.constants import HOST_RESULT_CHAR_CAP, MAX_HIT_THREADS
from mailweave.envelope.measure import rendered_chars
from mailweave.surface.partition import rendered_of
from mailweave.surface.recovery import MAX_RECOVERY_STEPS
from mailweave.surface.server import call
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.omission import (
    not_included_entries,
    not_included_whys,
    withheld_message_count,
    withheld_threads,
)
from tests.test_mcp_surface_round24 import make_service, structured_of

TERM = "plinth"
BODY = "The " + TERM + " arrived on the ninth and the invoice followed."


def few_threads_many_messages(*, threads: int = 18, per_thread: int = 3) -> SyntheticMailbox:
    """`threads` hit-bearing threads of `per_thread` matching messages each.

    At `max_hit_threads: 3`, fifteen of eighteen threads are capped away and their forty-five
    messages are withheld - exactly the live shape's numbers.
    """
    messages: list[Msg] = []
    for t in range(threads):
        thread_id = f"th{t:03d}ffffffffffff"
        for m in range(per_thread):
            messages.append(
                Msg(
                    id=f"m{t:03d}{m:02d}ffffffffff",
                    thread_id=thread_id,
                    sender=f"sender{t}@example.test",
                    subject=f"{TERM} thread {t}",
                    body=BODY,
                    internal_date_ms=epoch_ms(2026, 9, 1) + (t * 100 + m) * 60_000,
                    to=("me@example.test",),
                )
            )
    return SyntheticMailbox(messages=tuple(messages), now_ms=epoch_ms(2026, 9, 3))


def _served(result: Any) -> dict[str, Any]:
    assert not result.is_error, json.dumps(structured_of(result))[:600]
    return structured_of(result)


def _matched_rows(payload: dict[str, Any]) -> int:
    return sum(
        1
        for source in payload["sources"]
        for row in source["messages"]
        if row.get("role") == "matched"
    )


def _rendered(result: Any) -> int:
    mirrored = rendered_of(result)
    return rendered_chars(mirrored.structured, mirrored.text)


# --- the live shape ----------------------------------------------------------------------------


def test_the_live_shape_forty_five_withheld_across_few_threads_now_serves_mail() -> None:
    """**Requirements 1, 2, 6, 7 on the exact numbers the live mailbox produced.**

    Fails at `5e86229` with `budget_exhausted` (REG-01/REG-02). Here: served, with mail, inside
    the host cap, with every one of the forty-five withheld messages accounted for as a
    counted group whose count a client can read as a field.
    """
    box = few_threads_many_messages()
    result = call(
        make_service(box), "mailweave_search", {"query": TERM, "budget": {"max_hit_threads": 3}}
    )
    payload = _served(result)
    assert payload["sources"], "no sources at all"
    assert _matched_rows(payload) >= 1, "no matched mail"
    assert _rendered(result) <= HOST_RESULT_CHAR_CAP
    # The fifteen capped threads, three messages each, every one a counted group with the call
    # that reaches it. The ladder may split one of the three *mapped* threads off as well to
    # fit - that is a fourth kind of omission and it is accounted for the same way, which the
    # H-accounting test below holds - but the forty-five are exactly these.
    capped = {f"th{t:03d}ffffffffffff" for t in range(3, 18)}
    groups = {group["thread_id"]: group for group in payload["withheld_groups"]}
    assert capped <= set(groups), sorted(capped - set(groups))
    for thread_id in capped:
        group = groups[thread_id]
        assert group["message_count"] == 3
        assert group["cap"] == "max_hit_threads"
        assert group["affordance"]["tool"] == "mailweave_thread_map"
    assert withheld_message_count(payload) >= 45
    assert set(groups).isdisjoint({record["thread_id"] for record in payload["withheld"]}), (
        "a thread was both grouped and named"
    )
    # Requirement 2: the counts as fields, not only in prose - and they agree with the records.
    omission = payload["omission"]
    assert omission["withheld_messages"] == withheld_message_count(payload)
    assert omission["withheld_by_cap"]["max_hit_threads"] == 45
    assert omission["withheld_threads"] == len(groups)
    assert sum(omission["withheld_by_cap"].values()) == omission["withheld_messages"]
    assert payload["partial"] is True


def test_h_equals_disclosed_union_withheld_over_the_original_identities() -> None:
    """Requirement 3 / 7, read off the wire: disclosed rows plus withheld messages is every
    message the fixture holds, with nothing counted twice and nothing dropped."""
    box = few_threads_many_messages()
    payload = _served(
        call(
            make_service(box), "mailweave_search", {"query": TERM, "budget": {"max_hit_threads": 3}}
        )
    )
    disclosed = {row["id"] for source in payload["sources"] for row in source["messages"]}
    named = {record["id"] for record in payload["withheld"]}
    assert disclosed.isdisjoint(named)
    counted = sum(group["message_count"] for group in payload["withheld_groups"])
    assert len(disclosed) + len(named) + counted == 18 * 3
    # Every withheld thread is reachable: named as a group or a record, with a call.
    assert {f"th{t:03d}ffffffffffff" for t in range(3, 18)} <= withheld_threads(payload)
    # And every thread the fixture holds is either a source, a group, or a record: nothing
    # simply absent.
    sources = {source["thread_id"] for source in payload["sources"]}
    assert sources | withheld_threads(payload) == {f"th{t:03d}ffffffffffff" for t in range(18)}


def test_max_hit_threads_genuinely_bounds_the_emitted_response() -> None:
    """Requirement 4: a tighter cap makes the response smaller, and maps fewer threads.

    Before this round it moved ids from disclosed to withheld and charged each one a full
    record, so the response did not shrink at all (26,060 characters at cap 3 and at cap 1,
    live). Now a capped thread costs one group.
    """
    box = few_threads_many_messages()
    sizes: dict[int, int] = {}
    widths: dict[int, int] = {}
    for cap in (6, 3, 1):
        result = call(
            make_service(box),
            "mailweave_search",
            {"query": TERM, "budget": {"max_hit_threads": cap}},
        )
        payload = _served(result)
        # The cap bounds how many threads are *mapped*; the ladder may still split a mapped
        # one to fit, so the count is at most the cap and never above it.
        assert 1 <= len(payload["sources"]) <= cap, (cap, len(payload["sources"]))
        assert _matched_rows(payload) >= 1
        sizes[cap] = _rendered(result)
        widths[cap] = len(payload["sources"])
        assert sizes[cap] <= HOST_RESULT_CHAR_CAP
    # What "genuinely bounds" means, stated exactly (R-V01 review, requirement 3): the cap
    # bounds the *width* - no more threads mapped than it allows, fewer at a tighter cap
    # whenever the mailbox has more - and the response is inside the host cap at every width.
    # The rendered size is **not** monotone in the middle and is not claimed to be: the room a
    # tighter cap frees is spent on depth for the threads that remain, which is the right use
    # of it. It is smaller at width 1 than at width 6 because there is less to spend it on.
    #
    # **The width comparison is strict only between the ends** (round 31). Two bounds are in
    # play - `max_hit_threads` and the A.9a ladder - and only the first is what this test is
    # about. Once INJ-05's identity fields are charged, the cap-3 layout is 30,320 estimated
    # characters and the ladder splits it to one source, so the middle figure stops reporting
    # the cap and starts reporting the ladder. Asserting `widths[3] > widths[1]` would then be
    # asserting a fact about the ladder's arithmetic under the name of the cap. The property
    # the cap owns is held instead: width never rises as the cap tightens, width never exceeds
    # the cap (asserted per cap above), and tightening it from 6 to 1 strictly reduces the
    # width - the ends, where the cap is what binds.
    assert widths[6] >= widths[3] >= widths[1], widths
    assert widths[6] > widths[1], widths
    assert sizes[1] < sizes[6], sizes


def test_the_recovery_chain_from_the_live_shape_terminates_in_evidence() -> None:
    """Requirement 5 (strong): from the published width, follow `retry_with` until served.

    Bounded by `MAX_RECOVERY_STEPS`, no hop repeats a call, and the end is a served response
    with matched mail inside the cap. With this round's fix the first call already serves; the
    loop is kept so the property holds whichever hop serves first.
    """
    box = few_threads_many_messages()
    name, args = "mailweave_search", {"query": TERM}
    seen = [(name, dict(args))]
    result = call(make_service(box), name, args)
    hops = 0
    while result.is_error:
        payload = structured_of(result)
        retry = payload["retry_with"]
        assert retry is not None, ("the chain ended without evidence", payload["remediation"])
        hops += 1
        assert hops <= MAX_RECOVERY_STEPS, seen
        name, args = retry["tool"], dict(retry["args"])
        assert (name, args) not in seen, ("a repeated call", seen)
        seen.append((name, args))
        result = call(make_service(box), name, args)
    payload = _served(result)
    assert _matched_rows(payload) >= 1
    assert _rendered(result) <= HOST_RESULT_CHAR_CAP


# --- many single-message threads --------------------------------------------------------------


def test_many_single_message_threads_state_the_shared_reason_once() -> None:
    """The second form. Grouping does not apply - a group of one costs more than a record -
    so what has to not repeat is the not-included explanation, and it does not."""
    from tests.test_round27 import multi_thread_mailbox

    box = multi_thread_mailbox(threads=20)
    result = call(make_service(box), "mailweave_search", {"query": TERM})
    payload = _served(result)
    assert _matched_rows(payload) >= 1
    assert _rendered(result) <= HOST_RESULT_CHAR_CAP
    entries = not_included_entries(payload)
    whys = not_included_whys(payload)
    assert entries, "the fixture must split sources, or this asserts nothing"
    assert len(whys) == 1, whys  # one reason, one block, however many sources it covers
    assert len(entries) == len({entry["thread_id"] for entry in entries})
    assert all(entry["affordance"]["tool"] == "mailweave_thread_map" for entry in entries)
    assert payload["omission"]["not_included_sources"] == len(entries)


# --- no compression lets an empty answer pass ---------------------------------------------------


def test_no_compression_lets_an_empty_answer_be_served_as_success() -> None:
    """Requirement 5 of phase 1. A single thread too large for any arrangement of it must not
    come back `is_error: false` with no mail - the cheapness of grouping made that possible
    for one build of this round, and `_carries_nothing` is what refuses it.

    **Amended 2026-09-15 (R-M2-093).** "Any arrangement" now includes the one A.7a always
    allowed and the last resort never tried: the source's hits carried as collapsed-run
    members, which are present. A thread the ladder can carry that way is served with them
    (the test below, and `tests/test_integration_repair_2026_09_15.py`); this shape is one
    too large even as a run, so the refusal it holds is the one that is still right."""
    from tests.test_round27 import multi_thread_mailbox

    box = multi_thread_mailbox(threads=1, per_thread=900, words=5)
    result = call(make_service(box), "mailweave_search", {"query": TERM})
    assert result.is_error, "an answer with no evidence was served as success"
    payload = structured_of(result)
    assert "carries no mail" in payload["remediation"]
    # And the refusal is not a dead end: it offers a different tool, or says it is final.
    assert payload["retry_with"] is not None or payload["terminal"] is True


def test_a_thread_the_ladder_can_carry_as_a_run_is_served_as_membership_not_refused() -> None:
    """The shape the pre-amendment version of the test above used: three hundred long
    matching messages in one thread. Every row is a hit and a floor member and the top five
    were protected above stub depth, so the last resort used to split the only source and
    refuse the emptied answer. Under the amendment it is served with every hit present as a
    run member, its depth reduction declared, and the executable ways back named - and
    nothing in it is content: `messages` is empty and the run is an inventory."""
    from tests.test_round27 import multi_thread_mailbox

    box = multi_thread_mailbox(threads=1, per_thread=300, words=1500)
    result = call(make_service(box), "mailweave_search", {"query": TERM})
    payload = _served(result)
    assert _rendered(result) <= HOST_RESULT_CHAR_CAP
    (source,) = payload["sources"]
    assert source["messages"] == []
    members = {mid for run in source["collapsed_runs"] for mid in run["member_ids"]}
    assert len(members) == 300 == source["included"] == source["included_as_stub"]
    assert payload["partial"] is True and payload["truncated_by"] == "mailweave"
    tools = {offer["tool"] for offer in payload["affordances"]}
    assert {"mailweave_thread_map", "mailweave_get_messages"} <= tools


@pytest.mark.parametrize("cap", [MAX_HIT_THREADS, 3, 1])
def test_a_served_search_never_carries_zero_matched_rows_when_it_had_hits(cap: int) -> None:
    box = few_threads_many_messages()
    result = call(
        make_service(box), "mailweave_search", {"query": TERM, "budget": {"max_hit_threads": cap}}
    )
    if result.is_error:
        pytest.skip("declined; the emptiness property is about served responses")
    assert _matched_rows(structured_of(result)) >= 1


# --- the repair pass, after the consolidated v0.1 review ----------------------------------------
#
# Each of these is one of the review's HIGH findings, reproduced by its own probe and held.


def single_message_threads(
    *, threads: int, html: bool = False, attach: bool = False
) -> SyntheticMailbox:
    messages = [
        Msg(
            id=f"m{t:03d}ffffffffffff",
            thread_id=f"th{t:03d}ffffffffffff",
            sender=f"sender{t}@example.test",
            subject=f"{TERM} {t}",
            body=BODY,
            internal_date_ms=epoch_ms(2026, 9, 1) + t * 60_000,
            to=("me@example.test",),
            html_alternative=f"<p>{BODY}</p>" if html else None,
            has_attachment=attach,
        )
        for t in range(threads)
    ]
    return SyntheticMailbox(messages=tuple(messages), now_ms=epoch_ms(2026, 9, 3))


@pytest.mark.parametrize("threads", (30, 45, 60))
def test_many_single_message_hit_threads_at_width_one_serve_with_a_tail(threads: int) -> None:
    """R-V01-007. Forty-five one-message threads capped away at `max_hit_threads: 1` were
    forty-four groups of ~500 characters and a refusal. Past `MAX_WITHHELD_GROUPS_NAMED` the
    rest fold into one exact tail per cap, with the call that widens the cap."""
    from mailweave.constants import MAX_WITHHELD_GROUPS_NAMED

    result = call(
        make_service(single_message_threads(threads=threads)),
        "mailweave_search",
        {"query": TERM, "budget": {"max_hit_threads": 1}},
    )
    payload = _served(result)
    assert _matched_rows(payload) >= 1
    assert _rendered(result) <= HOST_RESULT_CHAR_CAP
    groups = payload["withheld_groups"]
    tail = payload["withheld_tail"]
    assert len(groups) == MAX_WITHHELD_GROUPS_NAMED
    assert len(tail) == 1 and tail[0]["cap"] == "max_hit_threads"
    assert tail[0]["thread_count"] == threads - 1 - MAX_WITHHELD_GROUPS_NAMED
    assert tail[0]["message_count"] == tail[0]["thread_count"]
    assert tail[0]["affordance"]["tool"] == "mailweave_search"
    assert tail[0]["affordance"]["args"]["budget"]["max_hit_threads"] == MAX_HIT_THREADS
    # H accounting over the tail: named + grouped + folded == every message not disclosed.
    assert withheld_message_count(payload) + tail[0]["message_count"] == threads - 1
    assert payload["omission"]["withheld_messages"] == threads - 1
    assert payload["omission"]["withheld_threads"] == threads - 1


def test_a_folded_thread_is_not_listed_in_affordances_but_its_widening_call_is() -> None:
    """R-V01-002/007 together: one call per named group, one per tail, none per folded thread."""
    payload = _served(
        call(
            make_service(single_message_threads(threads=60)),
            "mailweave_search",
            {"query": TERM, "budget": {"max_hit_threads": 1}},
        )
    )
    offers = payload["affordances"]
    assert len(offers) == len({json.dumps(o, sort_keys=True) for o in offers}), "a duplicate call"
    maps = [o for o in offers if o["tool"] == "mailweave_thread_map"]
    assert len(maps) == len(payload["withheld_groups"])
    assert any(o == payload["withheld_tail"][0]["affordance"] for o in offers)


@pytest.mark.parametrize("shape", ("html", "attach"))
def test_real_mail_shapes_are_estimated_at_or_above_what_they_render(shape: str) -> None:
    """R-V01-003: `multipart/alternative` and attachment rows declare reductions and
    attachment blocks the estimate did not charge. Held end to end through the shipped cap:
    a served response is inside it, and the rendered measurement is what refuses otherwise."""
    box = single_message_threads(threads=8, html=shape == "html", attach=shape == "attach")
    result = call(make_service(box), "mailweave_search", {"query": TERM})
    payload = _served(result)
    assert _matched_rows(payload) >= 1
    assert _rendered(result) <= HOST_RESULT_CHAR_CAP


def test_a_thread_map_of_a_thread_too_large_to_map_declines_and_never_raises() -> None:
    """R-V01-006: when the map's only source cannot be carried, before the repair ROUTE-01
    refused the emptied envelope as `-32603`. Now: a declared decline.

    The size moved with the navigation redesign (2026-09-14): a map is served as pages, so a
    450-message thread - the original fixture - is now one page of rows and a compact
    inventory of the rest, well inside the cap. What cannot fit is a thread whose *inventory*
    alone - every member id listed once - exceeds the host's cap: the declared limit of the
    inline map, around 800-1,000 messages at Gmail's 16-character ids. That thread declines,
    and the decline is the certified one.
    """
    from tests.test_round27 import multi_thread_mailbox

    box = multi_thread_mailbox(threads=1, per_thread=1_000, words=10)
    result = call(make_service(box), "mailweave_thread_map", {"thread_id": "th000fffffffffff"})
    assert result.is_error
    payload = structured_of(result)
    assert payload["code"] == "budget_exhausted"
    assert payload["terminal"] is True and payload["retry_with"] is None


def test_the_type_level_token_measure_agrees_with_the_layout_and_bounds_the_wire() -> None:
    """R-V01-008: `measure_tokens` had no term for groups and counted blocks as entries, so
    it fell below the wire on every grouped response while its single-source tests passed."""
    from mailweave.envelope.measure import measure_tokens, wire_tokens
    from tests.test_mcp_surface_round24 import make_service as _svc

    box = few_threads_many_messages()
    service = _svc(box)
    # Reach the envelope object itself, not the wire: the service's search returns it.
    from mailweave.surface.arguments import parse_search
    from mailweave.surface.rendering import render

    envelope = service.search(parse_search({"query": TERM, "budget": {"max_hit_threads": 3}}))
    mirrored = render(envelope)
    assert measure_tokens(envelope) >= wire_tokens(mirrored.structured, mirrored.text), (
        measure_tokens(envelope),
        wire_tokens(mirrored.structured, mirrored.text),
    )


# --- the records that carry the query (R-V01-013(a)) ------------------------------------------


LONG_QUERIES = (
    TERM,
    TERM + " " + "x" * 200,
    TERM + ' subject:"a \\"quoted\\" phrase" ' + "x" * 800,
)


def _estimate_and_rendered(
    monkeypatch: pytest.MonkeyPatch, box: SyntheticMailbox, args: dict[str, Any]
) -> tuple[int, int, dict[str, Any]]:
    """The ladder's finished estimate beside what the wire rendered, with the host cap lifted
    so the comparison is made on a served response whatever its size."""
    import mailweave.disclosure.plan as plan
    import mailweave.surface.partition as partition
    from mailweave.disclosure.ladder import run_ladder

    finished: list[Any] = []
    original = run_ladder

    def spy(layout: Any, **kwargs: Any) -> Any:
        degraded, steps = original(layout, **kwargs)
        finished.append(degraded)
        return degraded, steps

    import mailweave.surface.service as service

    monkeypatch.setattr(plan, "run_ladder", spy)
    monkeypatch.setattr(partition, "HOST_RESULT_CHAR_CAP", 10**9)
    # The ladder declines against the same cap; lift it too, so the shape is served and the
    # estimate and the wire can be compared on the response itself.
    lifted = replace(service.SERVED_CEILINGS, host_chars=10**9)
    monkeypatch.setattr(service, "SERVED_CEILINGS", lifted)
    result = call(make_service(box), "mailweave_search", args)
    payload = _served(result)
    assert finished, "the ladder did not run"
    return finished[-1].chars(), _rendered(result), payload


@pytest.mark.parametrize("cap", ("max_api_calls", "max_server_ms"))
@pytest.mark.parametrize("query", LONG_QUERIES)
def test_budget_cap_shapes_are_estimated_at_or_above_what_they_render_at_any_query_length(
    monkeypatch: pytest.MonkeyPatch, query: str, cap: str
) -> None:
    """R-V01-013(a). A budget or clock cap files one record per message in every thread it
    stopped the server mapping, and each record's affordance is the caller's own search -
    query included - so the record grows with the query. `WITHHELD_RECORD_CHARS` was measured
    at a six-character query and charged nothing for its length: twenty-four such records
    were 2,458 under at a 407-character query and 12,858 under at 807. The zero-record form
    (`max_server_ms` exhausted before any map) was under too: `retrieval_report.not_tried[]`
    and the breached cap's `affordances[]` entry carry the query and were not charged.

    Held through the shipped path with the host cap lifted, at the demo query, a 200-character
    one and an 800-character one with escaped quotes, on both the record-bearing and the
    zero-record shape: the estimate is never below the wire.
    """
    box = few_threads_many_messages(threads=12, per_thread=2)
    limit = 3 if cap == "max_api_calls" else 1
    estimate, rendered, payload = _estimate_and_rendered(
        monkeypatch, box, {"query": query, "budget": {cap: limit}}
    )
    assert cap in payload["retrieval_report"]["budget_caps_hit"]
    assert estimate >= rendered, (len(query), cap, estimate, rendered, rendered - estimate)
    for record in payload["withheld"]:
        if record["cap"] == cap:
            assert record["affordance"]["args"]["query"] == query


@pytest.mark.parametrize("query", LONG_QUERIES[1:])
def test_a_long_query_budget_decline_still_terminates_in_a_served_response(query: str) -> None:
    """The chain contract holds for the query-bearing shape: a long query under a budget cap
    declines at the published width (the estimate now charges the query per record) and the
    retry narrows `max_hit_threads` until the accounting fits. The budget still forbids the
    maps, so the served response is the truthful capped one - every hit accounted for, no
    source, `partial`, `inconclusive` - and not a success."""
    box = few_threads_many_messages(threads=12, per_thread=2)
    name = "mailweave_search"
    args: dict[str, Any] = {"query": query, "budget": {"max_api_calls": 3}}
    seen: list[tuple[str, dict[str, Any]]] = [(name, dict(args))]
    result = call(make_service(box), name, args)
    hops = 0
    while result.is_error:
        payload = structured_of(result)
        assert payload["code"] == "budget_exhausted"
        retry = payload["retry_with"]
        assert retry is not None, ("the chain ended without a served response", payload)
        hops += 1
        assert hops <= MAX_RECOVERY_STEPS, seen
        name, args = retry["tool"], dict(retry["args"])
        assert (name, args) not in seen, ("a repeated call", seen)
        assert args["query"] == query and args["budget"]["max_api_calls"] == 3, "carried through"
        seen.append((name, args))
        result = call(make_service(box), name, args)
    payload = _served(result)
    assert _rendered(result) <= HOST_RESULT_CHAR_CAP
    assert payload["partial"] is True
    assert payload["retrieval_report"]["outcome"] != "answered"
    assert payload["sources"] == []
    assert withheld_message_count(payload) == 24
