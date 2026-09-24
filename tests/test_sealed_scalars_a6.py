"""Amendment A6: sealed observations carry named scalars, and no mail text (round 8).

A6's final form is binding: sealed observations widen to carry the named scalar fields the
class-O audit identified - `stated_total`, `position`, `internal_date`, `history_id`,
`fetched_at` - and **not** whole response bodies, because mail text is excluded from what a
seal retains under OD-4 and `SCOPE_CORRECTION.md` A.3.

Three groups of test, and they are three different claims:

  * **the exclusion is structural.** Every field A6 adds is an `int` or a single-line
    string of at most `MAX_SEALED_SCALAR_CHARS`. A body does not fit, a subject does not
    fit reliably, and a value carrying a newline is refused outright. This is checked by
    reflection over the seal's own state rather than by reading its docstring;
  * **the fields are derived, not asserted.** Two caller-supplied parameters are gone;
    three more are now held to the observed value exactly where round 7 could only bound
    them.
  * **what A6 does not buy.** It closes *misstatement* - a caller stating a different value
    for something the system observed. It does nothing about *fabrication* - a caller
    minting an observation that never happened - which is A1's external witness and cannot
    be closed in-process at all. The last test in this file executes that distinction so
    the limit is a measured fact rather than a paragraph.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import Enum

import pytest
from pydantic import ValidationError

from mailweave.envelope import (
    Depth,
    DispositionLedger,
    EnvelopeBuilder,
    MailboxProvenance,
    MessageRow,
    Outcome,
    Role,
    RungId,
    Source,
    Sufficiency,
)
from mailweave.envelope.disposition import (
    MAX_SEALED_PAGE_TOKEN_CHARS,
    MAX_SEALED_SCALAR_CHARS,
    FetchedIds,
    ObservedEndpoint,
    ObservedThread,
)
from mailweave.envelope.response import Envelope
from mailweave.errors import DispositionInvariantError
from tests.fixtures import envelope_kit as kit

#: A body, as a caller trying to park one in the ledger would supply it.
MAIL_TEXT = (
    "Thanks for the update on this.\n"
    "\n"
    "Once the negotiations concluded, the legal team wrote:\n"
    "\n"
    "We should have a decision by end of week either way.\n"
)


# --- the retention claim, checked rather than promised ---------------------------------


def test_no_widened_seal_field_can_hold_mail_text() -> None:
    """R-SEC's question, answered by construction: the seal has nowhere to put a body.

    Every string a sealed observation accepts is bounded and single-line, so the attempt
    fails at the constructor rather than being stored and later noticed. Both refusals are
    exercised - the length bound and the newline bound - because a caller with a short
    excerpt defeats only the first.
    """
    for field, value in (
        ("history_id", MAIL_TEXT),
        ("fetched_at", MAIL_TEXT),
    ):
        with pytest.raises(DispositionInvariantError, match=r"A6|line break|bound"):
            FetchedIds(
                ids=["m1"],
                endpoint=ObservedEndpoint.THREADS_GET,
                thread_id="t1",
                **{field: value},  # type: ignore[arg-type]
            )
    with pytest.raises(DispositionInvariantError, match="line break"):
        FetchedIds(
            ids=["m1"],
            endpoint=ObservedEndpoint.THREADS_GET,
            thread_id="t1",
            internal_dates={"m1": "one line\nand another"},
        )
    with pytest.raises(DispositionInvariantError, match="bound"):
        FetchedIds(
            ids=["m1"],
            endpoint=ObservedEndpoint.THREADS_GET,
            thread_id="t1",
            internal_dates={"m1": "x" * (MAX_SEALED_SCALAR_CHARS + 1)},
        )


#: Every `__slots__` entry that can hold a string, and the constructor call that writes it.
#: This table is what makes the reflection below a **coverage** claim rather than a
#: well-formed-fixture claim: each probe is routed at exactly one slot, so a slot whose bound
#: is missing fails here by name.
#:
#: A slot absent from this table must hold something that is not a string, and the test
#: asserts that too - so adding a string-bearing field to `FetchedIds` without a bound fails
#: in the round it is added rather than in a review six rounds on, which is what round 8's
#: version of this test said and did not do.
STRING_BEARING_SLOTS: dict[str, Callable[[str], FetchedIds]] = {
    "_ids": lambda probe: FetchedIds(
        ids=[probe], endpoint=ObservedEndpoint.THREADS_GET, thread_id="t1"
    ),
    "_thread_id": lambda probe: FetchedIds(
        ids=["m1"], endpoint=ObservedEndpoint.THREADS_GET, thread_id=probe
    ),
    "_thread_ids": lambda probe: FetchedIds(
        ids=["m1"],
        endpoint=ObservedEndpoint.MESSAGES_LIST,
        page_size=25,
        thread_ids={"m1": probe},
    ),
    "_next_page_token": lambda probe: FetchedIds(
        ids=["m1"],
        endpoint=ObservedEndpoint.MESSAGES_LIST,
        page_size=25,
        next_page_token=probe,
    ),
    "_history_id": lambda probe: FetchedIds(
        ids=["m1"], endpoint=ObservedEndpoint.THREADS_GET, thread_id="t1", history_id=probe
    ),
    "_fetched_at": lambda probe: FetchedIds(
        ids=["m1"], endpoint=ObservedEndpoint.THREADS_GET, thread_id="t1", fetched_at=probe
    ),
    "_internal_dates": lambda probe: FetchedIds(
        ids=["m1"],
        endpoint=ObservedEndpoint.THREADS_GET,
        thread_id="t1",
        internal_dates={"m1": probe},
    ),
}


@pytest.mark.parametrize("slot", sorted(STRING_BEARING_SLOTS))
def test_no_string_bearing_slot_of_the_seal_accepts_mail_text(slot: str) -> None:
    """Every string the seal can retain, attacked at the slot that retains it (R-SEC-031).

    Round 8's version of this test walked `__slots__` over one well-formed observation and
    asserted the values it found were bounded. That is not the same claim: `_ids`,
    `_thread_id` and `_thread_ids` were explicitly exempted while carrying **no bound at
    all**, and `_next_page_token` was skipped silently because the fixture is a `threads.get`
    and has none - so the docstring's "a future field of the wrong shape fails here" was
    true of no field it actually checked.

    This version routes three probes at each slot by name: a five-line body, one long line,
    and a value whose only defect is a U+2028 that `str.splitlines()` calls a line break. A
    slot with no bound fails on all three, and it fails identified.
    """
    build = STRING_BEARING_SLOTS[slot]
    for probe, why in (
        (MAIL_TEXT, "a five-line body"),
        ("x" * 4096, "one very long line"),
        ("one line\u2028and a second", "a non-ASCII line boundary"),
    ):
        with pytest.raises(DispositionInvariantError):
            build(probe)
            pytest.fail(f"{slot} accepted {why}")


def test_every_slot_of_the_seal_is_either_probed_or_cannot_hold_a_string() -> None:
    """The other half of the coverage claim: no slot is silently out of scope.

    A string-bearing slot is in `STRING_BEARING_SLOTS` and attacked above. Every other slot
    has to demonstrate it holds something that is not a string - an int, a bool, or a
    non-string enum - on a fully populated observation. Together the two halves say "every
    string this object can retain is bounded", which is what round 8's docstring claimed and
    its exemption list contradicted.
    """
    observation = kit.fully_observed_thread(["m1", "m2", "m3"], "t1", stated_total=9)
    for slot in FetchedIds.__slots__:
        if slot in STRING_BEARING_SLOTS:
            continue
        value = getattr(observation, slot)
        if isinstance(value, Enum):
            # A closed vocabulary is not a place text can go: `ObservedEndpoint` is a
            # `StrEnum`, so it is a `str` by inheritance and can only ever be one of its
            # three members. Named here rather than skipped silently, which is the habit
            # R-SEC-031 was filed against.
            assert list(type(value)), f"{slot} is an enum with no members to be limited to"
            continue
        assert not isinstance(value, str), (
            f"{slot} holds a string and is not in STRING_BEARING_SLOTS, so nothing attacks "
            "it: a seal that can hold one unbounded string can hold mail text (OD-4)"
        )
        if isinstance(value, Mapping):
            for entry in dict(value).values():
                assert not isinstance(entry, str), f"{slot} maps to unprobed strings"


def test_the_seal_retains_nothing_but_bounded_scalars_and_bounded_ids() -> None:
    """And the values a real observation does carry are all bounded, checked by reflection.

    The complement of the two tests above: they say the constructor refuses bad values, this
    says the values a well-formed observation retains are within the same bounds - so a path
    that stored something *around* the constructor would still be caught. The line check uses
    `str.splitlines()` rather than looking for `\n`, because sharing the constructor's old
    blind spot is how a reflection test proves a guarantee it does not have (R-SEC-029).
    """
    observation = kit.fully_observed_thread(["m1", "m2", "m3"], "t1", stated_total=9)

    def is_a_bounded_string(value: str) -> bool:
        return len(value) <= MAX_SEALED_PAGE_TOKEN_CHARS and value.splitlines() == [value]

    for slot in FetchedIds.__slots__:
        value = getattr(observation, slot)
        if isinstance(value, bool | int) or value is None:
            continue
        if isinstance(value, str):
            assert is_a_bounded_string(value), f"{slot} retains an unbounded string"
            continue
        if isinstance(value, tuple):
            for entry in value:
                assert isinstance(entry, str) and is_a_bounded_string(entry)
            continue
        for key, entry in dict(value).items():
            assert isinstance(key, str) and is_a_bounded_string(key)
            assert isinstance(entry, int) or (
                isinstance(entry, str) and is_a_bounded_string(entry)
            ), f"{slot}[{key!r}] retains something that is not a bounded scalar"


def test_the_certificate_carries_the_scalars_and_still_no_text() -> None:
    """What travels to the envelope is the same bounded set, not a second, wider copy."""
    ledger = DispositionLedger()
    ledger.record_thread(kit.fully_observed_thread(["m1", "m2"], "t1"), rung=RungId.L4)
    certificate = ledger.certify(["m1", "m2"])
    assert certificate.observed_positions == {"m1": 0, "m2": 1}
    assert set(certificate.observed_internal_dates) == {"m1", "m2"}
    facts = certificate.observed_thread_facts["t1"]
    assert facts == ObservedThread(
        thread_id="t1",
        stated_total=2,
        history_id="99120034",
        fetched_at=kit.FETCHED_AT,
    )
    for value in (*certificate.observed_internal_dates.values(), facts.history_id):
        assert value is not None and len(value) <= MAX_SEALED_SCALAR_CHARS


# --- the two parameters that are gone ---------------------------------------------------


def test_the_two_class_o_parameters_no_longer_exist() -> None:
    """`MessageRow.internal_date` and `Source.history_id`, removed rather than checked.

    Round 7 filed both as `open`: caller-supplied facts of a Gmail response with nothing to
    compare them against and no reader inside the model. A6 seals them, so there is no
    longer a place to put a wrong value - the same shape `MessageRow.thread_id` took in
    round 7 and `note_withheld`'s `thread_id` in round 6.
    """
    assert "internal_date" not in MessageRow.model_fields
    assert "history_id" not in Source.model_fields
    # `extra="forbid"`, so the removal is a refusal rather than a silently ignored keyword.
    with pytest.raises(ValidationError, match="internal_date"):
        MessageRow(  # type: ignore[call-arg]
            mailbox=MailboxProvenance.of(("INBOX",)),
            id="m1",
            position=0,
            internal_date="1756557731000",
            role=Role.MATCHED,
            reason=kit.query_reason(),
            depth=Depth.STUB,
            unabridged=kit.unabridged("m1"),
        )
    with pytest.raises(ValidationError, match="history_id"):
        Source(  # type: ignore[call-arg]
            thread_id="t1",
            stated_total=0,
            included=0,
            included_as_stub=0,
            fetched_at=kit.FETCHED_AT,
            history_id="99120034",
        )


def test_the_removed_fields_still_reach_the_wire_derived_from_the_observation() -> None:
    """The reader's view is unchanged; only the place a wrong value could live is gone."""
    import json

    ledger = DispositionLedger()
    ledger.record_thread(
        kit.fully_observed_thread(["m1", "m2"], "t1", stated_total=2), rung=RungId.L4
    )
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    nonce = builder.fence_nonce
    builder.add_source(
        kit.source(
            "t1",
            [kit.row("m1", "t1", 0, nonce=nonce), kit.row("m2", "t1", 1, nonce=nonce)],
            stated_total=2,
        )
    )
    envelope = builder.build(
        outcome=Outcome.ANSWERED,
        rungs=(RungId.L4,),
        sufficiency=Sufficiency.SUFFICIENT,
        counters=kit.counters(),
    )
    payload = json.loads(envelope.model_dump_json())
    source = payload["sources"][0]
    assert source["history_id"] == "99120034"
    rows = {row["id"]: row for row in source["messages"]}
    assert rows["m1"]["internal_date"] == "1756557731000"
    assert rows["m2"]["internal_date"] == "1756557791000"
    assert rows["m1"]["internal_date_provenance"] == "gmail_internal_date"
    assert rows["m2"]["internal_date_provenance"] == "gmail_internal_date"
    # D.2's order: the derived fields sit where the schema sketch puts them, not appended.
    order = list(rows["m1"])
    assert order.index("internal_date") == order.index("position") + 1
    assert list(source).index("history_id") == list(source).index("verified_at") + 1


def test_an_unobserved_id_gets_a_null_internal_date_and_says_it_was_not_observed() -> None:
    """ "This response does not know" and "this response says none" are different facts.

    Until 2026-09-21 the distinction was carried by omitting the key. Four of five
    exploratory runs read the omission as "rows carry no timestamps" and ordered threads by
    identifier instead, so the distinction now travels as a provenance token beside an
    always-present value: `internal_date: null` with `internal_date_provenance:
    "not_observed"` is "does not know", and only an observed row says
    `"gmail_internal_date"`. Same fact, stated rather than implied.
    """
    import json

    ledger = DispositionLedger()
    ledger.record_thread(kit.observed_thread(["m1"], "t1"), rung=RungId.L4)
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    nonce = builder.fence_nonce
    builder.add_source(kit.source("t1", [kit.row("m1", "t1", 0, nonce=nonce)], stated_total=1))
    envelope = builder.build(
        outcome=Outcome.ANSWERED,
        rungs=(RungId.L4,),
        sufficiency=Sufficiency.SUFFICIENT,
        counters=kit.counters(),
    )
    payload = json.loads(envelope.model_dump_json())
    row = payload["sources"][0]["messages"][0]
    assert "internal_date" in row and row["internal_date"] is None
    assert row["internal_date_provenance"] == "not_observed"
    assert "history_id" not in payload["sources"][0]


# --- the three parameters that stayed, now checked against the observation ---------------


def _envelope_with(observation: FetchedIds, make_source: Callable[[str], Source]) -> Envelope:
    """Observe a thread, disclose the source `make_source` builds, and assemble.

    The source is built from the builder's own nonce rather than a literal, because the
    envelope refuses unfenced content - a real constraint with nothing to do with A6, which
    would otherwise mask the refusal each test below is actually about.
    """
    ledger = DispositionLedger()
    ledger.record_thread(observation, rung=RungId.L4)
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    builder.add_source(make_source(builder.fence_nonce))
    builder.add_affordance(kit.thread_affordance("t1"))
    return builder.build(
        outcome=Outcome.ANSWERED,
        rungs=(RungId.L4,),
        sufficiency=Sufficiency.SUFFICIENT,
        counters=kit.counters(),
    )


def _source(
    *, stated_total: int, positions: tuple[int, ...], fetched_at: str
) -> Callable[[str], Source]:
    def make(nonce: str) -> Source:
        rows = tuple(
            kit.row(f"m{index + 1}", "t1", position, nonce=nonce)
            for index, position in enumerate(positions)
        )
        return Source(
            thread_id="t1",
            stated_total=stated_total,
            included=len(rows),
            included_as_stub=0,
            fetched_at=fetched_at,
            messages=rows,
        )

    return make


def test_a_stated_total_the_observation_did_not_state_is_refused() -> None:
    """Round 7 could only bound this below; A6 makes it total where the seal carries it."""
    observation = kit.fully_observed_thread(["m1", "m2"], "t1", stated_total=9)
    with pytest.raises(DispositionInvariantError, match="thread length"):
        _envelope_with(
            observation,
            _source(stated_total=2, positions=(0, 1), fetched_at=kit.FETCHED_AT),
        )


def test_a_row_moved_off_its_observed_position_is_refused() -> None:
    """The clearest class-O case in the round 7 audit, now checked exactly (A3 + A6)."""
    observation = kit.fully_observed_thread(["m1", "m2"], "t1", stated_total=9)
    with pytest.raises(DispositionInvariantError, match="position"):
        _envelope_with(
            observation,
            _source(stated_total=9, positions=(0, 5), fetched_at=kit.FETCHED_AT),
        )


def test_a_collapsed_run_that_does_not_span_its_members_observed_positions_is_refused() -> None:
    """The same fact one disposition to the left (R-ARCH-013's shape)."""
    observation = kit.fully_observed_thread(["m1", "m2", "m3"], "t1", stated_total=9)
    run = kit.collapsed_run(4, ["m2", "m3"], "t1")

    def source(nonce: str) -> Source:
        return Source(
            thread_id="t1",
            stated_total=9,
            included=3,
            included_as_stub=2,
            fetched_at=kit.FETCHED_AT,
            messages=(kit.row("m1", "t1", 0, nonce=nonce),),
            collapsed_runs=(run,),
        )

    with pytest.raises(DispositionInvariantError, match="observed at position"):
        _envelope_with(observation, source)


def test_a_fetch_time_the_call_did_not_have_is_refused() -> None:
    """R-DISC-005 stopped a stamp that is not an instant; A6 stops one that is not *this*."""
    observation = kit.fully_observed_thread(["m1"], "t1", stated_total=1)
    with pytest.raises(DispositionInvariantError, match="fetch time"):
        _envelope_with(
            observation,
            _source(stated_total=1, positions=(0,), fetched_at="2026-08-31T09:00:00Z"),
        )


# --- the seal's own refusals -------------------------------------------------------------


def test_a_partial_or_alien_scalar_map_is_refused() -> None:
    """The rule `thread_ids` has followed since R-DISC-009, applied to A6's maps."""
    with pytest.raises(DispositionInvariantError, match="did not return"):
        kit.observed_thread(["m1"], "t1", positions={"m1": 0, "ghost": 1}, stated_total=2)
    with pytest.raises(DispositionInvariantError, match="some of its"):
        kit.observed_thread(["m1", "m2"], "t1", positions={"m1": 0}, stated_total=2)


def test_a_listing_page_cannot_state_a_thread_length_or_a_position() -> None:
    """A page of a result set is not a thread, and has neither of those facts to state."""
    with pytest.raises(DispositionInvariantError, match="cannot state a thread"):
        FetchedIds(
            ids=["m1"],
            endpoint=ObservedEndpoint.MESSAGES_LIST,
            page_size=50,
            stated_total=4,
        )
    with pytest.raises(DispositionInvariantError, match="cannot state a message's position"):
        FetchedIds(
            ids=["m1"],
            endpoint=ObservedEndpoint.MESSAGES_LIST,
            page_size=50,
            positions={"m1": 0},
        )


def test_a_thread_cannot_be_shorter_than_the_response_that_returned_it() -> None:
    with pytest.raises(DispositionInvariantError, match="cannot be shorter"):
        kit.observed_thread(["m1", "m2", "m3"], "t1", stated_total=2)


def test_two_positions_for_one_slot_in_one_observation_are_refused() -> None:
    with pytest.raises(DispositionInvariantError, match="same position"):
        kit.observed_thread(["m1", "m2"], "t1", positions={"m1": 1, "m2": 1}, stated_total=4)


def test_two_observations_that_disagree_about_a_sealed_scalar_are_refused() -> None:
    """R-DISC-009's rule, applied to the scalars A6 seals: fill a gap, refuse a conflict."""
    ledger = DispositionLedger()
    ledger.record_thread(kit.observed_thread(["m1"], "t1", stated_total=7), rung=RungId.L4)
    with pytest.raises(DispositionInvariantError, match="disagree about stated_total"):
        ledger.record_thread(kit.observed_thread(["m1"], "t1", stated_total=9), rung=RungId.L4)

    positions = DispositionLedger()
    positions.record_thread(
        kit.observed_thread(["m1"], "t1", positions={"m1": 0}, stated_total=4), rung=RungId.L4
    )
    with pytest.raises(DispositionInvariantError, match="disagree about position"):
        positions.record_thread(
            kit.observed_thread(["m1"], "t1", positions={"m1": 3}, stated_total=4), rung=RungId.L4
        )


def test_a_later_observation_fills_a_scalar_an_earlier_one_did_not_carry() -> None:
    """Filling is not overwriting, and the ordinary ladder needs it.

    A `messages.list` page carries no thread length; the `threads.get` that follows does.
    Without this the fact would be unavailable for every thread reached through a search.
    """
    ledger = DispositionLedger()
    ledger.record_list_page(
        kit.fetched(["m1"], thread="t1"), rung=RungId.L1, query="from:amy launch"
    )
    assert ledger.observed_thread_facts["t1"].stated_total is None
    ledger.record_thread(kit.observed_thread(["m1"], "t1", stated_total=7), rung=RungId.L4)
    assert ledger.observed_thread_facts["t1"].stated_total == 7


# --- what A6 does not buy ----------------------------------------------------------------


def test_a6_closes_misstatement_and_does_nothing_about_fabrication() -> None:
    """The limit, executed rather than asserted in a document.

    A caller that **misstates** a scalar the system observed is refused - that is every
    test above. A caller that **fabricates the observation** states the scalar and the id
    together, and the envelope agrees with it perfectly, because the thing it checks
    against is the fabrication. Widening the seal moved the assertion one layer down; it
    did not make the assertion checkable, and nothing in this process can. That is
    amendment A1's content witness (WS-13/WS-16), and it is not built.
    """
    ledger = DispositionLedger()
    ledger.record_thread(
        kit.fully_observed_thread(["ghost-1", "ghost-2"], "t-invented", stated_total=2),
        rung=RungId.L4,
    )
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    nonce = builder.fence_nonce
    builder.add_source(
        kit.source(
            "t-invented",
            [
                kit.row("ghost-1", "t-invented", 0, nonce=nonce),
                kit.row("ghost-2", "t-invented", 1, nonce=nonce, depth=Depth.STUB),
            ],
            stated_total=2,
        )
    )
    envelope = builder.build(
        outcome=Outcome.ANSWERED,
        rungs=(RungId.L4,),
        sufficiency=Sufficiency.SUFFICIENT,
        counters=kit.counters(),
    )
    assert envelope.partial is False, (
        "a wholly fabricated observation still builds a confident envelope; A6 closes "
        "misstatement, and only A1's external witness closes fabrication"
    )
