"""The listing seam: a caller cannot obtain fetched IDs without recording them (H1).

R-ORCH-001, restated: `H` was whatever a caller passed to `record_list_page`, so a rung
that fetched 100 IDs and recorded 10 produced a valid certificate with `H=10`,
`withheld=0` and ninety retrieved messages invisible. The set difference was never wrong;
its input was.

These tests are about **impossibility**, not about the happy path. Each one is an attempt
to write the probe R-ORCH ran, using only the supported API, and each asserts on the wall
it hits.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mailweave.envelope import (
    DispositionLedger,
    EnvelopeBuilder,
    FetchedIds,
    ObservedEndpoint,
    Outcome,
    RungId,
    Sufficiency,
)
from mailweave.envelope.disposition import _RECORD_TOKEN
from mailweave.errors import DispositionInvariantError
from mailweave.retrieval import RecordedListing, RecordingListTransport
from tests.fixtures import envelope_kit as kit


def gmail_returned(ids: list[str]) -> RecordingListTransport:
    """A stand-in `messages.list` that returns `ids`, shaped as WS-02's client must be."""

    def fetch(*, query: str, page_size: int, page_token: str | None) -> FetchedIds:
        return FetchedIds(
            ids=ids,
            endpoint=ObservedEndpoint.MESSAGES_LIST,
            page_size=page_size,
            more_pages=False,
        )

    return RecordingListTransport(fetch)


def hundred_ids() -> list[str]:
    return [f"real-hit-{index}" for index in range(100)]


# --- the probe R-ORCH ran, rewritten against the seam ---------------------------------------


def test_the_transport_hands_back_no_id_a_caller_could_drop() -> None:
    """R-ORCH-001's probe cannot be written: `list_messages` returns counts, not IDs."""
    fetched = hundred_ids()
    ledger = DispositionLedger()
    listing = gmail_returned(fetched).list_messages(
        ledger, rung=RungId.L1, query="from:amy launch", page_size=100
    )

    assert isinstance(listing, RecordedListing)
    assert listing.ids_recorded == len(fetched)
    assert ledger.hit_ids == set(fetched)

    # Nothing reachable from the returned object is, or contains, a message ID.
    reachable: list[Any] = [getattr(listing, name) for name in vars(listing)]
    reachable.extend(
        getattr(listing.scan_scope, name) for name in type(listing.scan_scope).model_fields
    )
    flat = {str(value) for value in reachable}
    assert not (flat & set(fetched))


def test_under_recording_now_raises_instead_of_certifying_a_shrunken_hit_set() -> None:
    """The same attack from the other side: keep the ten, ship them, and be refused.

    Before this seam the build succeeded with `H=10` and `withheld=0`. Now `H` is the
    hundred the transport fetched, so the ninety undisclosed IDs are a residue with no
    cap record and certification fails, naming them.
    """
    fetched = hundred_ids()
    ledger = DispositionLedger()
    gmail_returned(fetched).list_messages(
        ledger, rung=RungId.L1, query="from:amy launch", page_size=100
    )

    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    rows = [
        kit.row(mid, "t1", position, nonce=builder.fence_nonce)
        for position, mid in enumerate(fetched[:10])
    ]
    builder.add_source(kit.source("t1", rows, stated_total=10))

    with pytest.raises(DispositionInvariantError) as failure:
        builder.build(
            outcome=Outcome.ANSWERED,
            rungs=(RungId.L1,),
            sufficiency=Sufficiency.SUFFICIENT,
            counters=kit.counters(),
        )
    message = str(failure.value)
    assert "real-hit-50" in message
    assert "no withheld record" in message


# --- the seal itself -------------------------------------------------------------------------


def test_a_fetched_page_has_no_public_member_that_yields_an_id() -> None:
    fetched = hundred_ids()
    page = FetchedIds(
        ids=fetched,
        endpoint=ObservedEndpoint.MESSAGES_LIST,
        page_size=100,
        next_page_token="tok-1",
    )

    public = {name: getattr(page, name) for name in dir(page) if not name.startswith("_")}
    assert set(public) == {
        "endpoint",
        "more_pages",
        "next_page_token",
        "page_size",
        "recorded",
        "size",
        "thread_id",
    }
    assert not ({str(value) for value in public.values()} & set(fetched))
    assert page.size == len(fetched)

    with pytest.raises(TypeError):
        list(page)  # type: ignore[call-overload]


def test_opening_a_page_without_the_ledgers_token_is_refused() -> None:
    page = FetchedIds(ids=["m1"], endpoint=ObservedEndpoint.MESSAGES_LIST, page_size=100)
    with pytest.raises(DispositionInvariantError) as failure:
        page._release(object())
    assert "under-counted" in str(failure.value)
    assert page.recorded is False
    # And with the ledger's own token it opens, which is what makes the refusal above a
    # capability check rather than a function that never returns anything.
    assert page._release(_RECORD_TOKEN) == ("m1",)
    assert page.recorded is True


def test_the_ledger_does_not_accept_a_bare_id_list() -> None:
    """The signature is the fix: `H` is fed by pages, never by a list a caller assembled."""
    ledger = DispositionLedger()
    with pytest.raises((AttributeError, TypeError)):
        ledger.record_list_page(["m1", "m2"], rung=RungId.L1, query="q")  # type: ignore[arg-type]
    with pytest.raises((AttributeError, TypeError)):
        ledger.record_history_additions(["h1"])  # type: ignore[arg-type]
    # Amendment A2 added a third intake; it takes the same sealed type and no other.
    with pytest.raises((AttributeError, TypeError)):
        ledger.record_thread(["m1"], rung=RungId.L5)  # type: ignore[arg-type]
    assert ledger.hit_ids == frozenset()


def test_a_fetcher_that_returns_a_bare_list_is_refused_by_the_transport() -> None:
    transport = RecordingListTransport(
        lambda *, query, page_size, page_token: ["m1", "m2"]  # type: ignore[arg-type,return-value]
    )
    with pytest.raises(TypeError) as failure:
        transport.list_messages(DispositionLedger(), rung=RungId.L1, query="q", page_size=100)
    assert "FetchedIds" in str(failure.value)


def test_the_scan_scope_entry_is_read_off_the_page_not_off_the_caller() -> None:
    """A caller cannot describe the page as smaller than the one that entered `H`."""
    fetched = hundred_ids()
    ledger = DispositionLedger()
    listing = gmail_returned(fetched).list_messages(
        ledger, rung=RungId.L1, query="q", page_size=100
    )
    entry = listing.scan_scope
    assert entry.ids_returned == len(fetched) == len(ledger.hit_ids)
    assert entry.page_size == 100
    assert ledger.scan_scope == (entry,)


def test_history_additions_take_the_same_seal() -> None:
    def fetch_history(*, start_history_id: str, page_token: str | None) -> FetchedIds:
        return FetchedIds(ids=["h1", "h2", "h3"], endpoint=ObservedEndpoint.HISTORY_LIST)

    transport = RecordingListTransport(
        lambda *, query, page_size, page_token: FetchedIds(
            ids=[], endpoint=ObservedEndpoint.MESSAGES_LIST, page_size=page_size
        ),
        fetch_history=fetch_history,
    )
    ledger = DispositionLedger()
    recorded = transport.list_history_additions(ledger, start_history_id="9001")
    assert recorded == 3
    assert ledger.hit_ids == {"h1", "h2", "h3"}
    assert {origin.clause for origin in ledger.origins.values()} == {"H-hist"}


def test_a_thread_observation_takes_the_same_seal() -> None:
    """Amendment A2's seam: `threads.get` records through the transport like everything else.

    Without it a rung building AD D.5's thread-wise pool would have to mint the observation
    itself, which is the ordinary way to under-record and the shape R-ORCH-001 attacked.
    The transport returns a count; there is still no method here that yields an id.
    """

    def fetch_thread(*, thread_id: str) -> FetchedIds:
        return FetchedIds(
            ids=["r1", "r2", "r3", "r4"],
            endpoint=ObservedEndpoint.THREADS_GET,
            thread_id=thread_id,
        )

    transport = RecordingListTransport(
        lambda *, query, page_size, page_token: FetchedIds(
            ids=[], endpoint=ObservedEndpoint.MESSAGES_LIST, page_size=page_size
        ),
        fetch_thread=fetch_thread,
    )
    ledger = DispositionLedger()
    recorded = transport.get_thread(ledger, thread_id="t-42", rung=RungId.L5)

    assert recorded == 4
    assert ledger.hit_ids == {"r1", "r2", "r3", "r4"}
    assert {origin.clause for origin in ledger.origins.values()} == {"H-thr"}
    assert ledger.scan_scope == (), "a threads.get is not a query and invents no scan scope"


def test_a_thread_fetcher_that_returns_a_bare_list_is_refused_by_the_transport() -> None:
    """The third seam takes the same shape check as the two listing ones."""
    transport = RecordingListTransport(
        lambda *, query, page_size, page_token: FetchedIds(
            ids=[], endpoint=ObservedEndpoint.MESSAGES_LIST, page_size=page_size
        ),
        fetch_thread=lambda *, thread_id: ["m1", "m2"],  # type: ignore[arg-type,return-value]
    )
    with pytest.raises(TypeError) as failure:
        transport.get_thread(DispositionLedger(), thread_id="t1", rung=RungId.L5)
    assert "FetchedIds" in str(failure.value)


def test_a_thread_fetcher_returning_the_wrong_endpoint_is_refused() -> None:
    """A fetcher that mislabels its own call would put ids into the wrong A.7a clause."""
    transport = RecordingListTransport(
        lambda *, query, page_size, page_token: FetchedIds(
            ids=[], endpoint=ObservedEndpoint.MESSAGES_LIST, page_size=page_size
        ),
        fetch_thread=lambda *, thread_id: FetchedIds(
            ids=["m1"], endpoint=ObservedEndpoint.MESSAGES_LIST, page_size=100
        ),
    )
    ledger = DispositionLedger()
    with pytest.raises(TypeError) as failure:
        transport.get_thread(ledger, thread_id="t1", rung=RungId.L5)
    assert "threads.get" in str(failure.value)
    assert ledger.hit_ids == frozenset()


def test_a_transport_without_a_thread_fetcher_says_so_rather_than_guessing() -> None:
    ledger = DispositionLedger()
    with pytest.raises(ValueError, match="thread fetcher"):
        gmail_returned([]).get_thread(ledger, thread_id="t1", rung=RungId.L5)


# --- the property, over arbitrary pages -------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    pages=st.lists(
        st.lists(st.text(alphabet="abcdef0123456789", min_size=3, max_size=6), max_size=8),
        min_size=1,
        max_size=5,
    ),
    keep=st.integers(min_value=0, max_value=8),
)
def test_h_is_always_everything_the_transport_fetched(pages: list[list[str]], keep: int) -> None:
    """However many pages a rung fetches, and however few it tries to keep, `H` is all of them.

    The caller here is deliberately hostile: it wants to record only `keep` IDs per page.
    It has no way to express that, because the page it is given cannot be opened and the
    transport records before it returns.
    """
    ledger = DispositionLedger()
    everything: set[str] = set()
    for index, ids in enumerate(pages):
        everything |= set(ids)
        transport = RecordingListTransport(
            lambda *, query, page_size, page_token, _ids=ids: FetchedIds(
                ids=_ids, endpoint=ObservedEndpoint.MESSAGES_LIST, page_size=page_size
            )
        )
        listing = transport.list_messages(
            ledger, rung=RungId.L1, query=f"probe-{index}", page_size=100
        )
        # The hostile caller's best attempt: it can only look at counts.
        assert listing.ids_recorded == len(ids)
        assert min(keep, len(ids)) <= listing.ids_recorded
    assert ledger.hit_ids == everything
