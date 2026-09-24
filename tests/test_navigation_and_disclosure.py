"""Navigation and disclosure, one correction for R-M2-076 and R-M2-080 (2026-09-14).

The properties the redesign was asked to deliver, each stated on corpus-independent fixtures
with generated variations and each measured on the wire a client receives:

  * an explicit read delivers the requested content at the requested depth, at any position
    of a thread of any tested length, by id and by map position, without requiring the whole
    surrounding map (§1);
  * a requested view is the request: a stub or snippet read of N ids returns N rows, never a
    top-k of five and never zero (§2);
  * a batch that does not fit one response is served across `requested` continuations whose
    union is the request exactly, with no id twice and a strictly smaller remainder each hop
    (§3);
  * a thread map is a page, and following `thread` continuations from page 0 visits every
    position exactly once (§4);
  * the sizes are actual: every served response is measured with `rendered_chars` against
    `HOST_RESULT_CHAR_CAP`; every map source accounts for every position; every content row
    is fenced (§1-§4, throughout);
  * a `thread` continuation names its page's own `map_id`, so one followed after the thread
    gained a message, lost one, was touched, or changed its page width is refused as
    `handle_stale` with page 0 as the explicit restart - never a page of a different state,
    never a silent gap or repeat - and a run's `thread_map(thread_id, page)` is a pointer that
    lands on a page stating its own state (§5); a server that mints no handle offers no
    `thread` continuation (§5); a `page` outside the thread is refused as an argument, never
    served as some other page (§5);
  * a scoped read references reply parents through withheld records it carries (§6);
  * a broad search whose bookkeeping used to displace evidence is measured, not promised (§7).

The R-M2-080 tests in `tests/test_r_m2_080_long_thread_body_reach.py` are the known-target
reachability half; nothing here reads the expected evidence to steer a driver.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from mcp.shared.exceptions import MCPError

from mailweave.constants import HOST_RESULT_CHAR_CAP, MAX_AUTH_RECORD_CHARS
from mailweave.envelope import measure
from mailweave.envelope.fence import is_fenced
from mailweave.envelope.measure import (
    COLLAPSED_RUN_CHARS,
    COLLAPSED_RUN_MEMBER_CHARS,
    COLLAPSED_RUN_MEMBER_ID_COPIES,
    rendered_chars,
)
from mailweave.gmail import client as gmail_client
from mailweave.handles.mint import HANDLE_TTL_SECONDS
from mailweave.surface.partition import rendered_of
from mailweave.surface.server import call
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.test_mcp_surface_round24 import _accept, make_service, structured_of

SIZES = (3, 12, 40, 90, 200, 400)
WORDS = ("brillig", "slithy", "toves", "outgrabe", "mimsy", "borogrove", "mome", "raths")
CONTENT_DEPTHS = frozenset({"body_clean", "body_full"})


def _thread(
    thread_id: str, n: int, *, words: int = 40, seed: int = 0, varied: bool = False
) -> list[Msg]:
    """`n` messages in one reply chain, each body distinct, generated from `seed`.

    `varied` is the shape the independent review asked for (finding 2): a distinct sender on
    every message, so a later page's participant index is wider than page 0's; a Gmail-width
    id; an `Authentication-Results` record; and a display name. The plain shape rotates three
    senders and uses short ids, which is the one that cannot catch a page probe that only
    priced page 0.
    """
    rng = random.Random(f"{thread_id}:{n}:{seed}")
    rows: list[Msg] = []
    for index in range(n):
        body = f"Note {index} of {thread_id}: " + " ".join(rng.choice(WORDS) for _ in range(words))
        sender = f"p{index:03d}@team.example" if varied else f"a{index % 3}@team.example"
        if varied:
            sender = f"Person {index} <{sender}>"
        rows.append(
            Msg(
                id=(f"{thread_id}-m{index:03d}" if not varied else f"{index:016x}"[-16:]),
                thread_id=thread_id,
                sender=sender,
                subject=f"Topic {thread_id}" if index == 0 else f"Re: Topic {thread_id}",
                body=body,
                internal_date_ms=epoch_ms(2026, 8, 1) + index * 3_600_000,
                to=("b@team.example",),
                in_reply_to=(f"<{thread_id}-m{index - 1:03d}@mail.invalid>" if index else None),
                authentication_results=(
                    "mx.example; spf=pass smtp.mailfrom=team.example; "
                    "dkim=pass header.i=@team.example; "
                    f"dmarc=pass (p=REJECT) header.from=team.example; seq={index}"
                    if varied
                    else None
                ),
            )
        )
    return rows


def _box(*threads: Sequence[Msg]) -> SyntheticMailbox:
    return SyntheticMailbox(
        messages=tuple(one for thread in threads for one in thread), now_ms=epoch_ms(2026, 9, 3)
    )


def _served(result: Any) -> dict[str, Any]:
    assert not result.is_error, structured_of(result).get("remediation")
    return structured_of(result)


def _size(result: Any) -> int:
    mirrored = rendered_of(result)
    return rendered_chars(mirrored.structured, mirrored.text)


def _rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [row for source in payload["sources"] for row in source["messages"]]


def _well_formed(result: Any) -> dict[str, Any]:
    """The properties every served response of this redesign must hold, measured."""
    payload = _served(result)
    assert _size(result) <= HOST_RESULT_CHAR_CAP, "over the host cap in the host's unit"
    nonce = payload["fence_nonce"]
    for source in payload["sources"]:
        rows = source["messages"]
        ids = [row["id"] for row in rows]
        members = [mid for run in source["collapsed_runs"] for mid in run["member_ids"]]
        assert len(set(ids)) == len(ids), "a row twice"
        assert not (set(ids) & set(members)), "a message both a row and a run member"
        for row in rows:
            content = row.get("content")
            if content is not None:
                assert is_fenced(nonce, content["text"]), "unfenced mail text"
        here = len(set(source["withheld_here"]))
        if source.get("map_id") is not None:
            accounted = len(rows) + len(set(members)) + here
            assert accounted == source["stated_total"], (source["thread_id"], accounted)
        else:
            # A source without a map claim is a scoped read (or served without a key): what
            # it does not carry is either a group of this thread's messages or, when nothing
            # was cut, the whole thread as rows and runs. The arithmetic closes either way.
            grouped = sum(
                group["message_count"]
                for group in payload["withheld_groups"]
                if group["thread_id"] == source["thread_id"]
            )
            assert source["included"] + here + grouped == source["stated_total"], (
                source["thread_id"],
                source["included"],
                here,
                grouped,
            )
        for run in source["collapsed_runs"]:
            _accept(run["affordance"])
    for continuation in payload["continuations"]:
        _accept(continuation["affordance"])
        assert continuation["remaining"] > 0
    for record in payload["withheld"]:
        _accept(record["affordance"])
    for group in payload["withheld_groups"]:
        _accept(group["affordance"])
    return payload


# --- §1 explicit reads at any position, by id and by map position ---------------------------


@pytest.mark.parametrize("n", SIZES)
@pytest.mark.parametrize("where", ("first", "middle", "last"))
def test_an_explicit_read_delivers_the_requested_row_at_any_position(n: int, where: str) -> None:
    """The requested row is here, with content at the requested depth, whatever the thread's
    length - and the thread rides along as a compact inventory, never as rows to degrade."""
    position = {"first": 0, "middle": n // 2, "last": n - 1}[where]
    service = make_service(_box(_thread("t", n)))
    target = f"t-m{position:03d}"
    payload = _well_formed(
        call(service, "mailweave_get_messages", {"message_ids": [target], "view": "body_clean"})
    )
    rows = _rows(payload)
    assert [row["id"] for row in rows] == [target]
    assert rows[0]["depth"] == "body_clean" and rows[0]["role"] == "requested"
    assert f"Note {position} of t" in rows[0]["content"]["text"]
    source = payload["sources"][0]
    assert source["included"] == source["stated_total"] == n
    assert source["map_id"] is not None, "a read that fits whole carries the thread's map"
    assert payload["partial"] is False and payload["truncated_by"] is None
    assert payload["continuations"] == []
    covered = {position} | {
        p
        for run in source["collapsed_runs"]
        for p in range(run["positions"][0], run["positions"][1] + 1)
    }
    assert covered == set(range(n)), "rows and runs tile the thread"


@pytest.mark.parametrize("n", (12, 90, 400))
@pytest.mark.parametrize("where", ("first", "middle", "last"))
def test_an_explicit_read_by_map_position_delivers_the_same_row(n: int, where: str) -> None:
    """The `map_id` + `positions` form of the same read, through the served map's handle."""
    position = {"first": 0, "middle": n // 2, "last": n - 1}[where]
    service = make_service(_box(_thread("t", n)))
    mapped = _well_formed(call(service, "mailweave_thread_map", {"thread_id": "t"}))
    map_id = mapped["sources"][0]["map_id"]
    payload = _well_formed(
        call(
            service,
            "mailweave_get_messages",
            {"map_id": map_id, "positions": [position], "view": "body_clean"},
        )
    )
    rows = _rows(payload)
    assert [row["id"] for row in rows] == [f"t-m{position:03d}"]
    assert rows[0]["position"] == position and rows[0]["depth"] == "body_clean"


@pytest.mark.parametrize("n", (90, 400))
def test_a_reads_size_is_bounded_by_its_inventory_not_by_the_threads_rows(n: int) -> None:
    """A read of one message in a long thread is not the map of the thread at stub depth:
    it is one row and a run inventory, and it stays far inside the cap where the old shape
    rendered 8,311 characters at 90 messages and 17,632 at 400 with the row degraded."""
    service = make_service(_box(_thread("t", n)))
    result = call(
        service,
        "mailweave_get_messages",
        {"message_ids": [f"t-m{n // 2:03d}"], "view": "body_clean"},
    )
    payload = _well_formed(result)
    assert _rows(payload)[0]["depth"] == "body_clean"
    stub_rows = [row for row in _rows(payload) if row["depth"] == "stub"]
    assert stub_rows == [], "the surrounding thread is an inventory, not rows"
    # The bound, stated as growth: from the 12-message thread to this one, the response may
    # grow by at most the declared per-member inventory charge - the id once, its quoting, and
    # a second run - never by a row's worth per message.
    small = call(
        service_small := make_service(_box(_thread("t", 12))),
        "mailweave_get_messages",
        {"message_ids": ["t-m006"], "view": "body_clean"},
    )
    del service_small
    per_member = COLLAPSED_RUN_MEMBER_CHARS + COLLAPSED_RUN_MEMBER_ID_COPIES * len("t-m000")
    assert _size(result) - _size(small) <= (n - 12) * per_member + COLLAPSED_RUN_CHARS


# --- §2 the requested view is the request ---------------------------------------------------


@pytest.mark.parametrize("view", ("stub", "snippet"))
@pytest.mark.parametrize("count", (1, 5, 10))
def test_a_requested_view_returns_every_requested_row_at_that_view(view: str, count: int) -> None:
    """R-M2-080's finding (2): `view: stub` returned zero rows because every stub was
    collapsible, and a snippet read returned a top-k of five. A requested row is the request.

    The largest count is a batch that fits one response, so no `requested` continuation
    (§3's case) is in play: **12 to 10 on 2026-09-22**, when every row gained the text
    mirror's attribution and chronology lines. Measured on this thread: at `snippet` eleven
    requested rows fit one response and twelve do not (the twelfth is served through a
    continuation), at `stub` thirteen do; 10 sits one row inside the narrower edge, and is
    still twice the top-k the finding was about.
    """
    service = make_service(_box(_thread("t", 40)))
    ids = [f"t-m{index:03d}" for index in range(3, 3 + count)]
    payload = _well_formed(
        call(service, "mailweave_get_messages", {"message_ids": ids, "view": view})
    )
    rows = _rows(payload)
    assert [row["id"] for row in rows] == ids
    assert {row["depth"] for row in rows} == {view}
    assert all(row["role"] == "requested" for row in rows)
    assert payload["continuations"] == []


# --- §3 batches that exceed one response ----------------------------------------------------


def _follow_batch(service: Any, ids: list[str], view: str) -> tuple[list[str], list[int], int]:
    """Serve a batch and follow its `requested` continuations to the end.

    Returns the delivered ids in order of delivery, the remainder sizes per hop, and the
    number of calls made. Asserts on the way what a continuation promises: each remainder is
    strictly smaller than the last, never names an id already delivered, and the chain ends.
    """
    delivered: list[str] = []
    remainders: list[int] = []
    args: dict[str, Any] = {"message_ids": ids, "view": view}
    calls = 0
    while True:
        calls += 1
        assert calls <= len(ids) + 1, "the chain does not terminate"
        payload = _well_formed(call(service, "mailweave_get_messages", args))
        rows = _rows(payload)
        assert rows, "a served response of a batch carries at least one requested row"
        for row in rows:
            assert row["depth"] == view and row["role"] == "requested"
            assert row["id"] in args["message_ids"], "a row nobody asked for"
            assert row["id"] not in delivered, "an id delivered twice"
            delivered.append(row["id"])
        continuations = [one for one in payload["continuations"] if one["scope"] == "requested"]
        assert len(continuations) <= 1
        if not continuations:
            assert payload["partial"] is False or payload["withheld_groups"] or payload["withheld"]
            return delivered, remainders, calls
        continuation = continuations[0]
        rest = list(continuation["message_ids"])
        assert continuation["remaining"] == len(rest)
        assert rest == [one for one in args["message_ids"] if one not in delivered], (
            "the remainder is the request minus what was delivered, in request order"
        )
        assert not remainders or len(rest) < remainders[-1]
        remainders.append(len(rest))
        assert payload["partial"] is True and payload["truncated_by"] == "mailweave"
        assert payload["omission"]["bound"], "a cut response names the ceiling that bound"
        args = dict(continuation["affordance"]["args"])
        assert args["view"] == view and args["message_ids"] == rest


@pytest.mark.parametrize("view", ("body_clean", "snippet"))
def test_a_batch_across_many_long_threads_is_served_whole_across_continuations(view: str) -> None:
    """Eight ids in eight sixty-message threads: the union over the chain is the request."""
    threads = [_thread(f"b{k}", 60, seed=k) for k in range(8)]
    service = make_service(_box(*threads))
    ids = [f"b{k}-m030" for k in range(8)]
    delivered, remainders, calls = _follow_batch(service, ids, view)
    assert delivered == ids, "identity, in request order - not merely the count"
    assert len(remainders) == calls - 1
    assert calls >= 2, "eight scoped rows do not fit one response at either depth"


@pytest.mark.parametrize("view", ("body_clean", "snippet", "stub"))
def test_a_batch_inside_one_long_thread_is_served_whole_across_continuations(view: str) -> None:
    """Forty ids in one 400-message thread, at three views."""
    service = make_service(_box(_thread("w", 400)))
    ids = [f"w-m{index:03d}" for index in range(10, 50)]
    delivered, remainders, calls = _follow_batch(service, ids, view)
    assert delivered == ids
    assert calls == len(remainders) + 1


def test_a_batch_that_fits_carries_no_continuation_and_every_inventory() -> None:
    """Three ids in three short threads fit whole: maps for all three, nothing cut."""
    service = make_service(_box(*(_thread(f"s{k}", 4, seed=k) for k in range(3))))
    ids = [f"s{k}-m002" for k in range(3)]
    payload = _well_formed(
        call(service, "mailweave_get_messages", {"message_ids": ids, "view": "body_clean"})
    )
    assert [row["id"] for row in _rows(payload)] == ids
    assert all(source["map_id"] is not None for source in payload["sources"])
    assert payload["continuations"] == [] and payload["partial"] is False


def test_a_cut_batch_defers_whole_threads_with_their_share_of_the_request_as_the_call() -> None:
    """A deferred thread is not carried and says so: one not-included entry and one counted
    group, each naming the read that gets that thread's share of the batch."""
    threads = [_thread(f"b{k}", 60, seed=k) for k in range(8)]
    service = make_service(_box(*threads))
    ids = [f"b{k}-m030" for k in range(8)]
    payload = _well_formed(
        call(service, "mailweave_get_messages", {"message_ids": ids, "view": "body_clean"})
    )
    carried = {source["thread_id"] for source in payload["sources"]}
    deferred = {
        entry["thread_id"]
        for block in payload["not_included_sources"]
        for entry in block["sources"]
    }
    assert carried and deferred and not (carried & deferred)
    assert carried | deferred == {f"b{k}" for k in range(8)}
    rest = set(payload["continuations"][0]["message_ids"])
    for block in payload["not_included_sources"]:
        for entry in block["sources"]:
            share = entry["affordance"]["args"]["message_ids"]
            assert (
                share
                and set(share) <= rest
                and all(one.startswith(entry["thread_id"]) for one in share)
            )
    groups = {group["thread_id"]: group for group in payload["withheld_groups"]}
    assert deferred <= set(groups)
    for thread_id in deferred:
        assert groups[thread_id]["message_count"] == 60
        assert groups[thread_id]["cap"] == "disclosed_token_ceiling"
    # The carried threads did not fit with their inventories either: scoped, so no map claim.
    for source in payload["sources"]:
        assert source["map_id"] is None
        assert source["included"] < source["stated_total"]


# --- §4 complete map traversal -------------------------------------------------------------


def _check_page(payload: dict[str, Any], thread_id: str) -> dict[str, Any] | None:
    """What every served page states, checked; the `thread` continuation off it, or `None`.

    The continuation is the **handle form** (continuation correctness, 2026-09-15): its call
    names this page's own `map_id` and the next index, so following it is a redemption
    against the state this page was served in, never a pointer into whatever the thread has
    become.
    """
    source = payload["sources"][0]
    assert source["thread_id"] == thread_id
    page, width, total = source["page"], source["page_size"], source["pages"]
    assert source["included"] == source["stated_total"]
    assert payload["partial"] is False and payload["truncated_by"] is None
    rows = source["messages"]
    assert [row["position"] for row in rows] == list(
        range(page * width, min((page + 1) * width, source["stated_total"]))
    )
    assert all(row["depth"] == "stub" and row.get("unabridged") for row in rows)
    for run in source["collapsed_runs"]:
        assert run["why"] == "map_page"
        assert 0 <= run["affordance"]["args"]["page"] < total
        assert run["affordance"]["args"]["page"] == run["positions"][0] // width
        assert run["affordance"]["args"]["thread_id"] == thread_id, "a run is a pointer"
    continuations = [one for one in payload["continuations"] if one["scope"] == "thread"]
    assert len(continuations) <= 1
    if not continuations:
        assert page == total - 1 or source["map_id"] is None, "the chain ends before the last page"
        return None
    continuation = continuations[0]
    assert source["map_id"] is not None, "a continuation is offered only with a handle"
    assert continuation["affordance"]["args"] == {"map_id": source["map_id"], "page": page + 1}
    assert continuation["positions"] == [
        (page + 1) * width,
        min((page + 2) * width, source["stated_total"]) - 1,
    ]
    assert (
        continuation["remaining"] == continuation["positions"][1] - continuation["positions"][0] + 1
    )
    return continuation


def _traverse(
    service: Any, thread_id: str, *, pages: int | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Follow `thread` continuations from page 0: the pages served, and the outstanding
    continuation when `pages` stopped the walk early (`None` when it reached the end)."""
    served: list[dict[str, Any]] = []
    args: dict[str, Any] = {"thread_id": thread_id}
    seen: set[int] = set()
    while True:
        payload = _well_formed(call(service, "mailweave_thread_map", args))
        page = payload["sources"][0]["page"]
        assert page not in seen, "a page visited twice"
        seen.add(page)
        served.append(payload)
        continuation = _check_page(payload, thread_id)
        if continuation is None:
            return served, None
        if pages is not None and len(served) >= pages:
            return served, continuation
        args = dict(continuation["affordance"]["args"])


def _pages_of(service: Any, thread_id: str) -> list[dict[str, Any]]:
    """Follow `thread` continuations from page 0 to the end, checking each page's statement."""
    served, outstanding = _traverse(service, thread_id)
    assert outstanding is None
    return served


def _ids_on(pages: Sequence[Mapping[str, Any]]) -> list[str]:
    return [row["id"] for payload in pages for row in payload["sources"][0]["messages"]]


@pytest.mark.parametrize("n", (3, 40, 90, 200, 400))
def test_following_thread_continuations_from_page_zero_visits_every_position_once(n: int) -> None:
    """The union of row ids over all pages is the thread's order, exactly and in order."""
    service = make_service(_box(_thread("t", n)))
    pages = _pages_of(service, "t")
    assert _ids_on(pages) == [f"t-m{index:03d}" for index in range(n)]
    assert len(pages) == pages[0]["sources"][0]["pages"]
    widths = {payload["sources"][0]["page_size"] for payload in pages}
    assert len(widths) == 1, (
        "the page width is a property of the thread, stated the same on every page"
    )


@pytest.mark.parametrize("varied", (False, True))
@pytest.mark.parametrize("n", (40, 200))
def test_every_page_is_reachable_directly_and_tiles_with_its_runs(n: int, varied: bool) -> None:
    """Any page asked for first: its rows plus its runs' members are the whole thread, at
    one width, every page under the cap - on the plain shape and on the one with a distinct
    sender, a Gmail-width id and an authentication record on every message."""
    messages = _thread("t", n, varied=varied)
    order = [one.id for one in messages]
    service = make_service(_box(messages))
    first = _well_formed(call(service, "mailweave_thread_map", {"thread_id": "t"}))["sources"][0]
    for page in range(first["pages"]):
        payload = _well_formed(
            call(service, "mailweave_thread_map", {"thread_id": "t", "page": page})
        )
        source = payload["sources"][0]
        assert (source["page"], source["page_size"], source["pages"]) == (
            page,
            first["page_size"],
            first["pages"],
        )
        rows = [row["id"] for row in source["messages"]]
        members = [mid for run in source["collapsed_runs"] for mid in run["member_ids"]]
        assert sorted(rows + members) == sorted(order)
        assert len(set(members)) == len(members)
        assert rows == order[page * first["page_size"] : (page + 1) * first["page_size"]]
        assert source["withheld_here"] == [], "a page withholds nothing; it is planned to fit"


def test_a_page_served_by_handle_is_the_page_served_by_thread_id() -> None:
    """The width is a property of the thread state, whichever way the state is named: page
    k through the handle (the continuation's form) carries the rows and runs page k through
    the thread id carries, including a page served from the LRU without its rows."""
    messages = _thread("t", 120, varied=True)
    service = make_service(_box(messages))
    first = _well_formed(call(service, "mailweave_thread_map", {"thread_id": "t"}))["sources"][0]
    for page in range(first["pages"]):
        by_id = _well_formed(
            call(service, "mailweave_thread_map", {"thread_id": "t", "page": page})
        )["sources"][0]
        by_handle = _well_formed(
            call(service, "mailweave_thread_map", {"map_id": first["map_id"], "page": page})
        )["sources"][0]
        assert (by_handle["page"], by_handle["page_size"], by_handle["pages"]) == (
            by_id["page"],
            by_id["page_size"],
            by_id["pages"],
        )
        assert [row["id"] for row in by_handle["messages"]] == [
            row["id"] for row in by_id["messages"]
        ]
        assert [run["member_ids"] for run in by_handle["collapsed_runs"]] == [
            run["member_ids"] for run in by_id["collapsed_runs"]
        ]


# --- §5 continuing an outstanding traversal across a change to the thread ---------------------
#
# Each test walks part of a thread, holds the continuation the last page offered, changes the
# thread, and then follows that continuation - the one an agent mid-traversal is holding - not
# a fresh walk from page 0. The property is the one the owner asked for on 2026-09-15: a
# continuation followed after the thread changed never produces a gap or a duplicate silently.
# It is refused as `handle_stale` (the freshness architecture's own class, AD A.10) with the
# re-derivation as the explicit restart, and the restart covers the new thread exactly. The
# `collapsed_runs[]` pointer form is shown beside it doing what a pointer does, so the two are
# not confused.


def _late(thread_id: str, index: int, *, dated: int, auth: str | None = None) -> Msg:
    return Msg(
        id=f"{thread_id}-late{index:03d}",
        thread_id=thread_id,
        sender="a0@team.example",
        subject=f"Re: Topic {thread_id}",
        body=f"Note late {index} of {thread_id}: arrived after the walk began",
        internal_date_ms=dated,
        to=("b@team.example",),
        authentication_results=auth,
    )


def _refused(result: Any, code: str) -> dict[str, Any]:
    """A tool error of `code`, whose restart is a call this surface accepts."""
    assert result.is_error, "served where a refusal was required"
    payload = structured_of(result)
    assert payload["code"] == code, payload
    restart = payload["retry_with"]
    assert restart is not None and restart["tool"] == "mailweave_thread_map"
    _accept(restart)
    return dict(restart)


def _restarted(
    service: Any, restart: Mapping[str, Any], expected: Sequence[str], *, width: int | None = None
) -> None:
    """The restart is page 0 of the thread as it now stands, and the walk from it is exact.

    The walk starts from the restart's own `args`, verbatim; `width`, when given, is the
    width every page of that walk must state.
    """
    args = dict(restart["args"])
    assert list(args) == ["thread_id"], "the restart is page 0 by thread id"
    first = _well_formed(call(service, "mailweave_thread_map", args))
    assert first["sources"][0]["page"] == 0
    pages = _pages_of(service, args["thread_id"])
    assert pages[0]["sources"][0]["page_size"] == first["sources"][0]["page_size"]
    assert _ids_on(pages) == list(expected)
    widths = {payload["sources"][0]["page_size"] for payload in pages}
    assert widths == {first["sources"][0]["page_size"]}
    if width is not None:
        assert widths == {width}


@pytest.mark.parametrize("where", ("before the cursor", "after the cursor"))
def test_a_continuation_after_a_message_arrives_restarts_rather_than_repeating(where: str) -> None:
    """A message that arrives mid-traversal shifts every later position. Followed as a
    pointer, page 2 would then open with a message page 1 already carried; followed as the
    continuation it is, it is refused and the walk restarts on the new thread."""
    messages = _thread("t", 90)
    box = _box(messages)
    service = make_service(box)
    walked, outstanding = _traverse(service, "t", pages=2)
    assert outstanding is not None
    width = walked[0]["sources"][0]["page_size"]
    dated = (
        messages[width + 2].internal_date_ms + 1
        if where == "before the cursor"
        else epoch_ms(2026, 9, 1)
    )
    box.add_message(_late("t", 0, dated=dated))
    expected = [one.id for one in box.thread("t")]
    assert len(expected) == 91
    if where == "before the cursor":
        assert expected.index("t-late000") < 2 * width, "the arrival is among visited positions"
    restart = _refused(
        call(service, "mailweave_thread_map", dict(outstanding["affordance"]["args"])),
        "handle_stale",
    )
    _restarted(service, restart, expected)


@pytest.mark.parametrize("where", ("before the cursor", "after the cursor"))
def test_a_continuation_after_a_message_leaves_restarts_rather_than_skipping(where: str) -> None:
    """A message that leaves mid-traversal pulls every later position back by one. Followed
    as a pointer, page 2 would then skip the message that was first on it; followed as the
    continuation it is, it is refused and the walk restarts on the new thread."""
    box = _box(_thread("t", 90))
    service = make_service(box)
    walked, outstanding = _traverse(service, "t", pages=2)
    assert outstanding is not None
    width = walked[0]["sources"][0]["page_size"]
    gone = f"t-m{3:03d}" if where == "before the cursor" else f"t-m{2 * width + 3:03d}"
    box.delete_message(gone)
    expected = [one.id for one in box.thread("t")]
    assert len(expected) == 89 and gone not in expected
    restart = _refused(
        call(service, "mailweave_thread_map", dict(outstanding["affordance"]["args"])),
        "handle_stale",
    )
    _restarted(service, restart, expected)


def test_a_continuation_across_a_width_change_restarts_at_the_new_width() -> None:
    """A message whose authentication record is far wider than any before it changes what
    every stub row of the thread is charged at, so the thread's page width shrinks. The
    outstanding continuation named page 2 at the old width; page 2 at the new width holds
    different positions. It is refused, and the restart walks the thread at one new width.

    **90 messages to 60 on 2026-09-22.** Every row is charged the text mirror's attribution
    and chronology lines, so the 90-message thread's width fell to 5 before the wide record
    arrived, and 5 wide rows still fit - the record moved nothing, and the precondition below
    caught it. Measured: the record takes the width from 6 to 5 at every length from 30 to 68
    messages, moves nothing from 69 to 104, and takes it from 5 to 4 from 105 to at least
    170. 60 is inside the first window, and the two-page walk before the change and the
    restart after it are the ones the tests beside this one make.
    """
    box = _box(_thread("t", 60, varied=True))
    service = make_service(box)
    walked, outstanding = _traverse(service, "t", pages=2)
    assert outstanding is not None
    old_width = walked[0]["sources"][0]["page_size"]
    # The widest record a row carries (`MAX_AUTH_RECORD_CHARS`; over it, the record is
    # declared oversize and costs nothing), against a fixture whose records are a third of it.
    widest = ("mx.example; " + "dkim=pass header.i=@team.example; " * 20)[:MAX_AUTH_RECORD_CHARS]
    box.add_message(_late("t", 0, dated=epoch_ms(2026, 9, 1), auth=widest))
    expected = [one.id for one in box.thread("t")]
    new_width = _well_formed(call(service, "mailweave_thread_map", {"thread_id": "t"}))["sources"][
        0
    ]["page_size"]
    assert new_width < old_width, "the change did not move the width; the test proves nothing"
    restart = _refused(
        call(service, "mailweave_thread_map", dict(outstanding["affordance"]["args"])),
        "handle_stale",
    )
    _restarted(service, restart, expected, width=new_width)


def test_a_continuation_across_a_paging_change_with_the_thread_unchanged_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one way a page width moves without the thread moving: the server's own paging
    changes under an outstanding handle (a deploy that moved a measure constant within the
    ttl). The digest fixes the messages and their order; the handle also signs the width
    the thread was paged at (`HandlePayload.page_sizes`), and a page after the first is
    refused when the recomputed width is not that one - the independent review of
    2026-09-15, finding 2. The probe sees nothing (no history record), so this is the
    paging check and nothing else; the restart walks at the new width."""
    box = _box(_thread("t", 90))
    service = make_service(box)
    walked, outstanding = _traverse(service, "t", pages=2)
    assert outstanding is not None
    old_width = walked[0]["sources"][0]["page_size"]
    monkeypatch.setattr(
        measure, "COLLAPSED_RUN_MEMBER_CHARS", measure.COLLAPSED_RUN_MEMBER_CHARS + 40
    )
    new_width = _well_formed(call(service, "mailweave_thread_map", {"thread_id": "t"}))["sources"][
        0
    ]["page_size"]
    assert new_width < old_width, "the constant did not move the width; the test proves nothing"
    assert box.history_records == [], "nothing touched the thread"
    refused = call(service, "mailweave_thread_map", dict(outstanding["affordance"]["args"]))
    restart = _refused(refused, "handle_stale")
    assert "paged differently" in structured_of(refused)["remediation"]
    _restarted(service, restart, [f"t-m{index:03d}" for index in range(90)], width=new_width)
    # Page 0 is page 0 at any width: the same handle without a page, or with page 0, serves.
    assert (
        _well_formed(
            call(service, "mailweave_thread_map", {"map_id": walked[0]["sources"][0]["map_id"]})
        )["sources"][0]["page_size"]
        == new_width
    )


def test_a_touched_thread_restarts_even_when_its_structure_is_unchanged() -> None:
    """A relabel moves no position. The handle's liveness probe still sees the thread
    touched, so the continuation restarts - the conservative side of the freshness
    architecture, stated rather than special-cased."""
    box = _box(_thread("t", 90))
    service = make_service(box)
    _walked, outstanding = _traverse(service, "t", pages=2)
    assert outstanding is not None
    box.relabel_message("t-m050", add=("STARRED",))
    expected = [one.id for one in box.thread("t")]
    restart = _refused(
        call(service, "mailweave_thread_map", dict(outstanding["affordance"]["args"])),
        "handle_stale",
    )
    _restarted(service, restart, expected)


def test_a_continuation_whose_history_cannot_be_walked_is_served_live_and_still_exact() -> None:
    """When Gmail no longer holds the handle's history window the probe cannot verify, and
    the page is fetched live with `handle_stale_unverifiable` in band (AD D.11's one in-band
    handle class). Unchanged, the walk stays exact; changed, the recomputed digest refuses it
    - the defence-in-depth branch, reached by a continuation exactly as by any redemption."""
    box = _box(_thread("t", 90))
    service = make_service(box)
    walked, outstanding = _traverse(service, "t", pages=2)
    assert outstanding is not None
    box.history_is_expired = True
    payload = _well_formed(
        call(service, "mailweave_thread_map", dict(outstanding["affordance"]["args"]))
    )
    assert [entry["code"] for entry in payload["errors"]] == ["handle_stale_unverifiable"]
    assert payload["sources"][0]["page"] == 2 and payload["sources"][0]["verified_at"] is None
    continuation = _check_page(payload, "t")
    served = [*walked, payload]
    while continuation is not None:
        payload = _well_formed(
            call(service, "mailweave_thread_map", dict(continuation["affordance"]["args"]))
        )
        served.append(payload)
        continuation = _check_page(payload, "t")
    assert _ids_on(served) == [f"t-m{index:03d}" for index in range(90)]
    # The same window, and now the thread has moved under it.
    _walked, outstanding = _traverse(service, "t", pages=2)
    assert outstanding is not None
    box.delete_message("t-m003")
    restart = _refused(
        call(service, "mailweave_thread_map", dict(outstanding["affordance"]["args"])),
        "handle_stale",
    )
    _restarted(service, restart, [one.id for one in box.thread("t")])


def test_an_expired_continuation_restarts_rather_than_paging_an_old_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A handle's age is measured from the read behind it and never restamped; a traversal
    that outlives the ttl is told to start again, not served a page nobody re-verified. One
    clock drives both the client's `fetched_at` stamp and the redemption, so the restart is
    walked under the same clock that expired the handle."""
    box = _box(_thread("t", 90))
    clock = {"now": datetime(2026, 9, 15, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(gmail_client, "_now", lambda: clock["now"].isoformat())
    service = make_service(box, now=lambda: clock["now"])
    _walked, outstanding = _traverse(service, "t", pages=2)
    assert outstanding is not None
    clock["now"] += timedelta(seconds=HANDLE_TTL_SECONDS + 1)
    restart = _refused(
        call(service, "mailweave_thread_map", dict(outstanding["affordance"]["args"])),
        "handle_expired",
    )
    _restarted(service, restart, [one.id for one in box.thread("t")])


def test_a_run_pointer_after_a_change_lands_on_a_page_that_states_its_own_state() -> None:
    """A run's `thread_map(thread_id, page)` is a pointer, not a continuation: followed after
    a message left, it is served - page 2 of the thread *as it now stands*, stating its own
    `stated_total`, `page_size`, `pages` and a fresh `fetched_at`, every id of the thread on
    it once. Which is exactly why it cannot be the continuation: the message that was first
    on page 2 is no longer on it, and a walk built on pointers would have skipped it."""
    box = _box(_thread("t", 90))
    service = make_service(box)
    # Runs span pages and name the page of their first position, so page 2's pointer is on
    # page 1 (page 0's one run covers everything after it and names page 1).
    before = _well_formed(call(service, "mailweave_thread_map", {"thread_id": "t", "page": 1}))[
        "sources"
    ][0]
    width = before["page_size"]
    pointer = next(
        run["affordance"]
        for run in before["collapsed_runs"]
        if run["affordance"]["args"]["page"] == 2
    )
    assert pointer["args"] == {"thread_id": "t", "page": 2}
    first_on_page_2 = f"t-m{2 * width:03d}"
    box.delete_message("t-m003")
    after = _well_formed(call(service, "mailweave_thread_map", dict(pointer["args"])))["sources"][0]
    assert (
        after["stated_total"] == 89
        and after["page"] == 2
        and after["fetched_at"] >= before["fetched_at"]
    )
    rows = [row["id"] for row in after["messages"]]
    members = [mid for run in after["collapsed_runs"] for mid in run["member_ids"]]
    assert sorted(rows + members) == sorted(one.id for one in box.thread("t"))
    assert first_on_page_2 not in rows, "the pointer's page no longer starts where the run said"
    assert first_on_page_2 in members, "…and the page says where that message is now"


def test_the_no_key_path_offers_no_thread_continuation_and_pages_by_pointer() -> None:
    """Without a signing key nothing can be verified, so no `map_id` is minted and no page
    offers a `thread` continuation - a continuation nothing could check is not the remainder
    of anything. Every page is still reachable through page 0's runs, the pages tile, and a
    batch still continues by its ids, which need no key."""
    service = make_service(_box(_thread("t", 90), _thread("u", 60, seed=1)))
    service.handle_key = None
    first = _well_formed(call(service, "mailweave_thread_map", {"thread_id": "t"}))
    assert first["sources"][0]["map_id"] is None
    assert first["continuations"] == []
    order = [f"t-m{index:03d}" for index in range(90)]
    # Runs span pages and name the page of their first position, so each page points at the
    # next one and a pointer walk goes page by page, checking each page's statement as it goes.
    payload, visited = first, []
    while True:
        assert payload["continuations"] == [] and payload["sources"][0]["map_id"] is None
        assert _check_page(payload, "t") is None
        source = payload["sources"][0]
        visited.extend(row["id"] for row in source["messages"])
        pointers = [
            run["affordance"]
            for run in source["collapsed_runs"]
            if run["affordance"]["args"]["page"] == source["page"] + 1
        ]
        if not pointers:
            assert source["page"] == source["pages"] - 1
            break
        payload = _well_formed(call(service, "mailweave_thread_map", dict(pointers[0]["args"])))
    assert visited == order
    ids = [f"t-m{index:03d}" for index in range(0, 40, 4)] + [
        f"u-m{index:03d}" for index in range(0, 40, 4)
    ]
    delivered, _remainders, _calls = _follow_batch(service, ids, "body_clean")
    assert delivered == ids


def test_a_page_outside_the_thread_is_refused_as_an_argument_not_served_as_another_page() -> None:
    service = make_service(_box(_thread("t", 40)))
    first = _well_formed(call(service, "mailweave_thread_map", {"thread_id": "t"}))["sources"][0]
    with pytest.raises(MCPError) as refused:
        call(service, "mailweave_thread_map", {"thread_id": "t", "page": first["pages"]})
    assert str(first["pages"]) in str(refused.value)
    with pytest.raises(MCPError):
        call(service, "mailweave_thread_map", {"thread_id": "t", "page": 0, "segment": 0})


# --- §6 a scoped read still references its reply parents through records it carries -----------


def test_a_scoped_read_names_reply_parents_it_withholds_as_records_with_their_own_call() -> None:
    """R-M2-077's rule survives the loss of the inventory: a row's `reply_parent_id` is named
    exactly when this source accounts for the parent, and a scoped source accounts for the
    parents of its rows as withheld records whose affordance reads the parent."""
    service = make_service(_box(_thread("w", 400)))
    ids = [f"w-m{index:03d}" for index in range(100, 140)]
    payload = _well_formed(
        call(service, "mailweave_get_messages", {"message_ids": ids, "view": "body_clean"})
    )
    source = payload["sources"][0]
    assert source["map_id"] is None, "a scoped source is not a map"
    rows = source["messages"]
    assert rows and rows[0]["id"] == "w-m100"
    assert rows[0]["reply_parent_id"] == "w-m099", "the first row's parent was not requested"
    assert "w-m099" in source["withheld_here"]
    records = {record["id"]: record for record in payload["withheld"]}
    assert records["w-m099"]["affordance"]["args"]["message_ids"] == ["w-m099"]
    assert records["w-m099"]["thread_id"] == "w"
    for row in rows[1:]:
        assert row["reply_parent_id"] == f"w-m{int(row['id'][-3:]) - 1:03d}"
    group = next(group for group in payload["withheld_groups"] if group["thread_id"] == "w")
    assert group["message_count"] == 400 - len(rows) - len(source["withheld_here"])
    assert group["affordance"] == {"tool": "mailweave_thread_map", "args": {"thread_id": "w"}}
    assert source["included"] + len(source["withheld_here"]) + group["message_count"] == 400


# --- §7 a broad search's bookkeeping, measured ---------------------------------------------


@pytest.mark.parametrize("varied", (False, True))
def test_a_search_runs_page_is_the_page_the_map_serves(varied: bool) -> None:
    """R-M2-081/082 (the independent review): a search's collapsed run names a page, and the
    page it names is the one a `thread_map` call serves - same width, and the run's first
    position is on it. The search's own map was scanned over bodies, the served map over
    snippets, so the width is sized on the snippet map on both paths."""
    messages = _thread("t", 120, varied=varied)
    service = make_service(_box(messages))
    result = call(service, "mailweave_search", {"query": "Note"})
    payload = _well_formed(result)
    runs = [
        (source["thread_id"], run)
        for source in payload["sources"]
        for run in source["collapsed_runs"]
    ]
    assert runs, "a 120-message hit thread does not fit as rows; the search must collapse"
    for thread_id, run in runs:
        assert run["affordance"]["tool"] == "mailweave_thread_map"
        args = dict(run["affordance"]["args"])
        assert set(args) == {"thread_id", "page"} and args["thread_id"] == thread_id
        page = _well_formed(call(service, "mailweave_thread_map", args))["sources"][0]
        assert page["page"] == args["page"]
        first, _last = run["positions"]
        assert page["page"] * page["page_size"] <= first < (page["page"] + 1) * page["page_size"]
        assert run["member_ids"][0] in {row["id"] for row in page["messages"]}


def test_a_broad_search_over_many_long_threads_is_measured_not_promised() -> None:
    """The 33-thread shape whose withheld bookkeeping consumed the cap (R-M2-076). Nothing
    here promises delivery: the search path keeps its ladder, and this measures that whatever
    it does is either served inside the host's cap, accounted, or declined with a call."""
    threads = [_thread(f"s{k:02d}", 20, seed=k) for k in range(33)]
    service = make_service(_box(*threads))
    result = call(service, "mailweave_search", {"query": "Note"})
    if result.is_error:
        payload = structured_of(result)
        assert payload["code"] == "budget_exhausted" and payload["retry_with"] is not None
        _accept(payload["retry_with"])
        return
    _well_formed(result)
