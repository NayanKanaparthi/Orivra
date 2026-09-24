"""Pages of a thread map: the width, the count, and the continuation to the next one.

**One arithmetic, read by every producer that names a page** (navigation redesign,
2026-09-14). A thread map is served in pages of `page_size` positions: the page's positions
as stub rows, every other page as a compact run pointing at a page. A search's collapsed runs
point at pages too, and a read's inventory runs do. All three name a page by index, so all
three must agree on the width - a run that said "page 3" against a width the map did not use
would land the reader on positions the run did not cover.

**The width is a function of the thread map a `mailweave_thread_map` call observes and the
published ceilings, and of nothing else.** Not of the request that asked, not of the bodies a
search happens to hold, and not of which `threads.get` rows this call has in hand. Two things
make that true:

  * every caller hands this module the map a `thread_map` call would build - the one whose
    participant index was scanned over *snippets* (`structure.threadmap.snippet_observed_text`).
    The search path holds a map scanned over fetched bodies, whose `mentioned` citations differ
    (R-M2-081/082, the independent review of 2026-09-14), so it builds the snippet map for
    this purpose rather than passing its own;
  * the probe the width is bisected on is an **upper bound over every page** of that map,
    not page 0: rows charged at the thread's longest id and its widest INJ-05 record
    (`ThreadMap.auth_record_chars`, carried with the map so an LRU-served map agrees), the
    run inventory at the longest id, the participant index whole rather than narrowed to any
    page's rows, the widest continuation the thread can render (its handle at the schema
    bound), the second run a page after the first carries, and the in-band note a page served
    through a handle carries when its probe could not look. Every real page costs at most
    that, so every page fits what the probe fits.

The bisection runs on the same `Layout` estimate the A.9a ladder runs on; the estimate is
conservative by certification (`test_a_collapsed_run_is_charged_at_or_above_what_it_renders`,
the round-26 shape matrix), and every served response is measured again as rendered before it
is handed over. No constant is tuned to a fixture.

**A page's continuation is verified; a run's page is a pointer** (continuation correctness,
2026-09-15). The `thread` continuation from page *k* to page *k+1* names the response's own
`map_id` (`mailweave_thread_map(map_id, page)`), so following it redeems the handle under AD
A.10 before anything is paged, and page *k+1* is served only when three things hold: the
liveness probe saw nothing touch the thread (or could not look - `handle_stale_unverifiable`,
in band, with the page fetched live), the thread's messages and order still digest to the
handle's, and the width the map is paged at is the width the handle signed
(`HandlePayload.page_sizes`, checked by `surface.service`). A message added or removed
anywhere fails the digest whatever the probe saw; a touch the probe sees, a relabel included,
is `handle_stale`; a width that moved with the thread unchanged - only a server whose paging
constants changed under the handle can do that - is `handle_stale` too; an aged handle is
`handle_expired`. Every refusal carries the re-derivation, page 0 by `thread_id`, as the
explicit restart. A continuation is therefore never served from a starting position other
than the one it was issued with, and a traversal cannot skip or repeat a position without
being told to start again. A server which mints no handle offers no `thread` continuation:
a page it named by thread and index is one nothing could verify (the shipped server always
holds a key - `handles.keys.ensure_handle_key` - so this is the test double's state).

The `collapsed_runs[]` on every path keep the pointer form, `mailweave_thread_map(thread_id,
page)` for the page the run's first position falls in *as the thread stood at `fetched_at`*.
That is a choice, recorded: a map page carries at most two runs (the positions before its
rows and the positions after), and a handle on each would cost about two rows of width; a
read's inventory or a search's runs may carry many, and one run form on every path is what
lets a page named by a search be the page the map serves. A pointer followed after the thread
moved is served - page *j* of the thread as it now stands, stating its own `page`,
`page_size`, `pages`, `stated_total` and `fetched_at` and listing every id of the thread once,
so a member that moved is locatable there - but nothing about a run is a claim that the page
is unchanged, and a walk built on pointers is not a traversal contract.

**What a page does not remove: the total-thread-size limit.** Every page carries the whole
remaining member inventory - each id of every other page, once, in its runs - so a page's
cost has a floor that grows with the thread, and a thread whose inventory alone exceeds the
host cap has no page that fits: `page_size` returns 1 and the map declines through the
ladder's own refusal. At Gmail's 16-character ids that is on the order of 800-1,000 messages
(`test_r_mcp_033_round29`'s 1,000-message decline). Paging bounds the *rows* a response
carries, not the inventory; it is not size-independent pagination, and a map of a thread
past that limit is a declared limit of the inline surface, not a page further on.
"""

from __future__ import annotations

from typing import Final

from mailweave.constants import HOST_RESULT_CHAR_CAP
from mailweave.disclosure.ladder import Ceilings
from mailweave.disclosure.layout import Band, Layout, PlannedRow, PlannedRun, PlannedSource
from mailweave.envelope.fence import close_marker, mint_nonce, open_marker
from mailweave.envelope.measure import (
    DISPLAY_NAME_CHARS,
    DISPLAY_NAME_TOKENS,
    PARTICIPANT_CITATION_CHARS,
    PARTICIPANT_CITATION_TOKENS,
    PARTICIPANT_STRUCTURAL_CHARS,
    PARTICIPANT_STRUCTURAL_TOKENS,
    collapsed_run_chars,
    collapsed_run_tokens,
    continuation_chars,
    error_entry_chars,
    request_echo_chars,
)
from mailweave.envelope.vocab import Depth, ToolName
from mailweave.envelope.wire import (
    Affordance,
    AskedFor,
    Continuation,
    ErrorEntry,
    ParsedQuerySummary,
)
from mailweave.errors import ErrorCode
from mailweave.handles.mint import widest_handle_chars
from mailweave.structure.threadmap import ThreadMap

#: A nonce of the shape every response mints, for the width of a fence around a display
#: name. Its value is irrelevant; its length is what the bound needs.
_NONCE_SHAPE: Final[str] = mint_nonce()

#: The ceilings a thread map is always served under. `mailweave_thread_map` takes no budget
#: argument, so a page is sized against the published token ceiling and the host's character
#: cap and nothing else - which is what lets a search or a read name a page a later map call
#: will serve identically.
MAP_CEILINGS: Final[Ceilings] = Ceilings(host_chars=HOST_RESULT_CHAR_CAP)

#: The echo a thread map's `asked_for` renders to, measured once off the block itself: a
#: map names no ids and no query, so this is the same for every map.
_MAP_ECHO: Final[int] = request_echo_chars(
    AskedFor(
        parsed=ParsedQuerySummary(operators={ToolName.THREAD_MAP.value: "whole thread"}),
        enforced=(ToolName.THREAD_MAP.value,),
        dropped=(),
        term_coverage=1.0,
        constraint_drop_depth=0,
    ),
    (),
)


def pages_of(total: int, width: int) -> int:
    """How many pages of `width` a thread of `total` messages has; one for an empty thread."""
    return max(1, -(-total // max(width, 1)))


def page_of(position: int, width: int) -> int:
    """The page a position falls in."""
    return position // max(width, 1)


def next_page(
    thread_id: str, total: int, page: int, width: int, *, map_id: str | None
) -> Continuation | None:
    """The `thread` continuation from `page` to the page after it.

    `None` on the last page, and `None` when this response minted no `map_id`: the
    continuation is the handle form, `mailweave_thread_map(map_id, page)`, so that following
    it is a redemption - verified against the thread's state before a page is served - and a
    page nothing could verify is not offered as the remainder of anything. Its `positions`
    state the page's span in the state the handle names.
    """
    start = (page + 1) * width
    if start >= total or map_id is None:
        return None
    end = min(start + width, total) - 1
    return Continuation(
        scope="thread",
        thread_id=thread_id,
        positions=(start, end),
        remaining=end - start + 1,
        affordance=Affordance(tool=ToolName.THREAD_MAP, args={"map_id": map_id, "page": page + 1}),
    )


def _probe(thread_map: ThreadMap, *, width: int) -> PlannedSource:
    """A page of `width` rows priced at or above any real page of this map.

    Synthetic ids of the thread's longest width stand in for the rows' and the runs' ids, so
    the charge does not depend on which page is asked for; the participant index is bounded
    separately (`_index_bound`) for the same reason. Nothing here is served.
    """
    total = len(thread_map.order)
    widest = max((len(message_id) for message_id in thread_map.order), default=1)
    stand_in = "x" * widest
    auth = "x" * thread_map.auth_record_chars
    # The widest attribution any row will carry, charged the way `row_chars` and `row_tokens`
    # charge a real row - once as JSON, once on the mirror line (2026-09-22). The name
    # stand-in is the thread's longest display name at its most words (one-letter words,
    # the bound `_index_bound` uses), so the token charge covers the wordiest name; the
    # address stand-in is the rest of the widest attribution, so the two together cost the
    # widest row's characters whichever row holds the name and whichever the address.
    # `attribution_chars` is measured as the wire escapes it, so a name full of quotes or
    # non-ASCII is covered by the JSON half of the charge.
    if thread_map.attribution_chars:
        words = max(1, thread_map.display_name_chars // 2 + 1)
        name = " ".join(["x"] * words) if thread_map.display_name_chars else ""
        address = "x" * max(1, thread_map.attribution_chars - len(name))
    else:
        name = address = ""
    rows = tuple(
        PlannedRow(
            id=stand_in,
            position=index,
            band=Band.REQUESTED,
            depth=Depth.STUB,
            auth_record=auth,
            from_address=address,
            from_display=name,
        )
        for index in range(min(width, total))
    )
    rest = total - len(rows)
    runs = (
        (PlannedRun(start=len(rows), end=total - 1, member_ids=tuple([stand_in] * rest)),)
        if rest > 0
        else ()
    )
    return PlannedSource(
        thread_id=thread_map.thread_id,
        rank=0,
        hit_bearing=False,
        rows=rows,
        runs=runs,
        participants=(),
    )


def _widest_continuation(thread_map: ThreadMap) -> Continuation:
    """A continuation rendering at least as wide as any real one of this thread.

    The handle is a stand-in of `widest_handle_chars` - every payload field at its schema
    bound - rather than any handle this response will mint: the width must not move with the
    digits of a `historyId` or the epoch of a key, or page *k* would not be page *k* from one
    response to the next. Charged whether or not this server mints handles, so the width is
    a function of the thread state and the published bounds alone.
    """
    total = len(thread_map.order)
    handle = "x" * widest_handle_chars(thread_map.thread_id)
    return Continuation(
        scope="thread",
        thread_id=thread_map.thread_id,
        positions=(total, total),
        remaining=1,
        affordance=Affordance(tool=ToolName.THREAD_MAP, args={"map_id": handle, "page": total}),
    )


def _unverifiable_note(thread_id: str) -> int:
    """The in-band note a page served through a handle carries when the liveness probe could
    not look (`handle_stale_unverifiable`, AD D.11's one in-band handle class), as
    `surface.service._redeem` writes it. Charged on every page, whether or not this one is
    served through a handle: a continuation is, and every page must fit what page 0 fits."""
    return error_entry_chars(
        ErrorEntry(
            code=ErrorCode.HANDLE_STALE_UNVERIFIABLE,
            scope=f"thread:{thread_id}",
            affordance=Affordance(tool=ToolName.THREAD_MAP, args={"thread_id": thread_id}),
        )
    )


def _index_bound(thread_map: ThreadMap, *, width: int) -> tuple[int, int]:
    """What the participant index of *any* page of `width` rows can cost, in tokens and chars.

    A page carries the thread's index narrowed to its rows (`participants_within`): every
    citation of a row on the page, and every address with at least one such citation, with
    that address's display names. So the widest page costs at most the `width` most-cited
    messages' citations, plus as many of the dearest address records as `width` messages can
    bring in - each address charged its structure, its address, and its distinct display
    names at the thread's longest (`ThreadMap.display_name_chars`), fenced. This is computed
    off the map alone, so an LRU-served map agrees with a fetched one.
    """
    index = thread_map.participants.by_address
    cites: dict[str, int] = dict.fromkeys(thread_map.order, 0)
    parties: dict[str, set[str]] = {message_id: set() for message_id in thread_map.order}
    for address, facts in index.items():
        for role in ("authored", "coauthored", "addressed", "reply_to", "mentioned"):
            for message_id in getattr(facts, role):
                if message_id in cites:
                    cites[message_id] += 1
                    parties[message_id].add(address)
    fence_overhead = len(open_marker(_NONCE_SHAPE)) + len(close_marker(_NONCE_SHAPE))
    name_chars = DISPLAY_NAME_CHARS + fence_overhead + thread_map.display_name_chars
    name_tokens = DISPLAY_NAME_TOKENS + max(1, thread_map.display_name_chars // 2 + 1)
    address_chars = sorted(
        (
            PARTICIPANT_STRUCTURAL_CHARS + len(address) + facts.distinct_display_names * name_chars
            for address, facts in index.items()
        ),
        reverse=True,
    )
    address_tokens = sorted(
        (
            PARTICIPANT_STRUCTURAL_TOKENS + facts.distinct_display_names * name_tokens
            for facts in index.values()
        ),
        reverse=True,
    )
    cite_chars = sorted(
        (
            count * (PARTICIPANT_CITATION_CHARS + len(message_id))
            for message_id, count in cites.items()
        ),
        reverse=True,
    )
    cite_tokens = sorted(
        (count * PARTICIPANT_CITATION_TOKENS for count in cites.values()), reverse=True
    )
    brought = sorted((len(one) for one in parties.values()), reverse=True)
    addresses = min(len(index), sum(brought[:width]))
    return (
        sum(cite_tokens[:width]) + sum(address_tokens[:addresses]),
        sum(cite_chars[:width]) + sum(address_chars[:addresses]),
    )


def page_size(thread_map: ThreadMap, *, ceilings: Ceilings = MAP_CEILINGS) -> int:
    """The widest page of this thread's map whose upper-bound estimate fits both ceilings.

    At least 1; a width of 1 for a thread whose inventory alone does not fit is not a page
    that fits, and the map of such a thread declines through the ladder's own refusal - the
    declared limit of the inline map.
    """
    total = len(thread_map.order)
    if total <= 1:
        return max(total, 1)
    continuation = continuation_chars(_widest_continuation(thread_map)) + _unverifiable_note(
        thread_map.thread_id
    )
    # A page after the first carries one more run than the probe does.
    second_run_tokens = collapsed_run_tokens(0)
    second_run_chars = collapsed_run_chars((), thread_map.thread_id)

    def fits(width: int) -> bool:
        index_tokens, index_chars = _index_bound(thread_map, width=width)
        layout = Layout(
            sources=(_probe(thread_map, width=width),),
            # The probe accounts for every position as a row or a run member by construction;
            # its ids are stand-ins, so the real ids must not be charged as withheld records.
            accounted_ids=frozenset(),
            floor_ids=frozenset(),
            hit_ids=frozenset(),
            request_echo_chars=_MAP_ECHO + continuation,
            evidence_is_the_map=True,
            ceiling_applied=ceilings.normal,
        )
        if layout.cost() + index_tokens + second_run_tokens > ceilings.normal:
            return False
        return (
            ceilings.host_chars is None
            or layout.chars() + index_chars + second_run_chars <= ceilings.host_chars
        )

    if fits(total):
        return total
    if not fits(1):
        return 1
    low, high = 1, total  # fits(low) and not fits(high)
    while high - low > 1:
        mid = (low + high) // 2
        if fits(mid):
            low = mid
        else:
            high = mid
    return low


__all__ = [
    "MAP_CEILINGS",
    "next_page",
    "page_of",
    "page_size",
    "pages_of",
]
