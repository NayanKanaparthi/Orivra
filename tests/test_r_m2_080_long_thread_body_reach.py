"""R-M2-080, closed: an identified message deep in a long thread is read through the offers.

**Known-target reachability, labelled as such.** Every test here knows which message it wants
(`EVIDENCE`) and follows the offers that could carry it. That is reachability of a known
target - the property the 2026-09-13 sem-off rerun found missing - and it is *not* query-driven
discovery, which is a separate property measured by the diagnostic and never by a driver that
is handed the answer.

The shape the rerun found (regression evidence, kept as a record of the old wire rather than
as a live assertion): a thread map that could not fit its messages as ~744-character stub
rows under the 25,000-character cap collapsed them into one run whose only affordance was
"fetch all N as snippets"; the snippet response collapsed again and offered snippet subsets;
the chain never narrowed to a message. Since the navigation redesign (2026-09-14) the map is a
*page* - rows for one window of positions, compact runs pointing at the other pages, member
ids listed once - and a named id is readable by name.

The last test is the guard the repair must keep: every served response under the host cap in
the host's unit, measured with the production `rendered_chars`; every map source accounting
for every position; an unexpected decline is a failure of this guard, never a silent pass;
follow-ups measured the same way; membership checked by identity.
"""

from __future__ import annotations

import json
from typing import Any

from mailweave.constants import HOST_RESULT_CHAR_CAP
from mailweave.envelope.measure import rendered_chars
from mailweave.surface.partition import rendered_of
from mailweave.surface.server import call
from mailweave.surface.service import MailweaveService
from mailweave_harness.evaluation.boundary import Served, call_tool, follow_boundary
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.test_mcp_surface_round24 import make_service, structured_of

LONG = 90
DEEP = 75
FACT = "Position: the Lantern agreement carries a ninety-day notice period, agreed at review."
WORDS = ("brillig", "slithy", "toves", "outgrabe", "mimsy", "borogrove", "mome", "raths")


def _long_thread() -> SyntheticMailbox:
    rows = [
        Msg(
            id=f"l-m{index:03d}",
            thread_id="l-th",
            sender=f"a{index % 3}@team.example",
            subject="Lantern terms" if index == 0 else "Re: Lantern terms",
            body=(
                FACT
                if index == DEEP
                else f"Lantern note {index}: "
                + " ".join(WORDS[(index + k) % len(WORDS)] for k in range(40))
            ),
            internal_date_ms=epoch_ms(2026, 8, 1) + index * 3_600_000,
            to=("b@team.example",),
            in_reply_to=(f"<l-m{index - 1:03d}@mail.invalid>" if index else None),
        )
        for index in range(LONG)
    ]
    return SyntheticMailbox(messages=tuple(rows), now_ms=epoch_ms(2026, 9, 3))


EVIDENCE = f"l-m{DEEP:03d}"


def _service() -> MailweaveService:
    return make_service(_long_thread())


def _size(result: Any) -> int:
    mirrored = rendered_of(result)
    return rendered_chars(mirrored.structured, mirrored.text)


def test_the_map_of_a_long_thread_is_a_page_that_names_every_member_once() -> None:
    """The corrected shape, as regression evidence against the one the rerun found: rows for
    one page, one run for the rest that lists each member id once and points at a page - not
    at a snippet read of every member - and the deep message named in the inventory."""
    served = call_tool(_service(), "mailweave_thread_map", {"thread_id": "l-th"})
    assert isinstance(served, Served)
    source = served.payload["sources"][0]
    assert source["stated_total"] == LONG
    assert source["messages"], "a page carries rows"
    assert source["page"] == 0 and source["pages"] > 1
    runs = source["collapsed_runs"]
    assert len(runs) == 1 and runs[0]["count"] == LONG - source["page_size"]
    assert runs[0]["affordance"]["tool"] == "mailweave_thread_map"
    assert runs[0]["affordance"]["args"] == {"thread_id": "l-th", "page": 1}
    assert runs[0]["member_ids"].count(EVIDENCE) == 1
    assert EVIDENCE in served.surfaced_ids()
    assert EVIDENCE not in served.content_by_id()
    mirrored = rendered_of(call(_service(), "mailweave_thread_map", {"thread_id": "l-th"}))
    rendered = json.dumps(mirrored.structured) + mirrored.text
    assert rendered.count(EVIDENCE) == 1, "the id renders once on the wire, in the inventory"


def test_a_message_identified_by_position_in_a_long_thread_can_be_read_by_following_offers() -> (
    None
):
    """Known-target reachability through the search. Search names the thread; the map or its
    inventory names the message; the offers lead to its body; all within the standing budget."""
    reach, merged, trace, first = follow_boundary(
        _service(),
        query="Lantern notice",
        required=frozenset({EVIDENCE}),
        quotes={EVIDENCE: FACT},
    )
    assert first is not None
    assert EVIDENCE in reach.surfaced_only | reach.after_expansion, (
        "the message was never even named"
    )
    assert reach.after_expansion == frozenset({EVIDENCE}), (
        f"not delivered: stopped on {reach.stopped} after {len(reach.calls)} calls; "
        f"exceptions={reach.exceptions}\n" + "\n".join(trace.lines[-6:])
    )
    assert FACT in merged.get(EVIDENCE, ""), "the content in hand is the message's own"
    assert not reach.exceptions


def test_the_maps_own_offers_lead_to_a_body_without_the_search() -> None:
    """Known-target reachability from the map itself: one hop at a time, the offers reach the
    message, and every hop is measured against the cap."""
    service = _service()
    served = call_tool(service, "mailweave_thread_map", {"thread_id": "l-th"})
    assert isinstance(served, Served)
    frontier = [served]
    seen: set[str] = set()
    for hops in range(1, 5):
        offers = [one for src in frontier for one in src.offers(frozenset({EVIDENCE}))]
        fresh = []
        for one in offers:
            key = str(one)
            if key not in seen:
                seen.add(key)
                fresh.append(one)
        assert fresh, "no response offered anything that could carry the message"
        nxt = []
        for one in fresh:
            result = call(service, str(one["tool"]), dict(one["args"]))
            assert not result.is_error, structured_of(result).get("remediation")
            assert _size(result) <= HOST_RESULT_CHAR_CAP
            got = call_tool(service, str(one["tool"]), dict(one["args"]))
            assert isinstance(got, Served)
            if EVIDENCE in got.content_by_id():
                assert FACT in got.content_by_id()[EVIDENCE]
                assert hops <= 2, "a named id is one read away from the map"
                return
            nxt.append(got)
        frontier = nxt
    raise AssertionError("four hops of the map's own offers never carried the body")


def test_the_repair_keeps_every_response_under_the_cap_and_fully_accounted() -> None:
    """The guard. Every served response of the map, the search and their follow-ups stays
    under the host cap in the unit the host enforces - the production `rendered_chars` against
    the configured `HOST_RESULT_CHAR_CAP`, not the sum of two forms against twice the cap -
    and every map source accounts for every position. A decline here is a failure: nothing in
    this fixture is sized to decline, so an `is_error` result is the guard catching a regression,
    not a case to skip."""
    service = _service()
    pending: list[tuple[str, dict[str, Any]]] = [
        ("mailweave_thread_map", {"thread_id": "l-th"}),
        ("mailweave_search", {"query": "Lantern notice"}),
    ]
    seen: set[str] = set()
    measured = 0
    delivered: set[str] = set()
    while pending and measured < 12:
        tool, args = pending.pop(0)
        key = f"{tool} {sorted(args.items())}"
        if key in seen:
            continue
        seen.add(key)
        result = call(service, tool, args)
        assert not result.is_error, (tool, args, structured_of(result).get("remediation"))
        measured += 1
        assert _size(result) <= HOST_RESULT_CHAR_CAP, (tool, args, _size(result))
        payload = structured_of(result)
        for source in payload["sources"]:
            members = [mid for run in source["collapsed_runs"] for mid in run["member_ids"]]
            assert len(set(members)) == len(members), "a member listed twice across runs"
            if source.get("map_id") is None:
                continue
            accounted = (
                len(source["messages"]) + len(set(members)) + len(set(source["withheld_here"]))
            )
            assert accounted == source["stated_total"], (source["thread_id"], accounted)
            ids = (
                {row["id"] for row in source["messages"]}
                | set(members)
                | set(source["withheld_here"])
            )
            assert ids == {f"l-m{index:03d}" for index in range(LONG)}, "membership by identity"
        served = call_tool(service, tool, args)
        assert isinstance(served, Served)
        delivered |= set(served.content_by_id())
        for offer in served.offers(frozenset({EVIDENCE})):
            pending.append((str(offer["tool"]), dict(offer["args"])))
    assert measured >= 3, "the follow-ups were measured, not only the first responses"
    assert EVIDENCE in delivered
