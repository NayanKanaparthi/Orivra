"""Round 9, part 2: the three holes in A6's retention claim, each closed by execution.

The round-8 work order gated on "A6 landed with **mail text provably excluded**". It had
not. A reviewer put a real English sentence on the JSON wire under a Gmail metadata field
name - including on a **stub row**, whose entire architectural purpose is to disclose
nothing - and the mechanism A6's own docstring called "what stops the interesting attempt"
turned out to check two characters out of seven.

**R-SEC-029.** The line-break refusal checked `\\n` and `\\r` only; U+2028, U+2029, U+0085,
U+000B and U+000C passed untouched. It now compares against `str.splitlines()`, which the
runtime maintains, rather than against a set somebody typed out.

**R-SEC-030.** `history_id` and `internal_date` took any 64-character single-line string,
while `fetched_at` beside them was instant-checked. They are now checked against the decimal
shape Gmail actually returns.

**R-SEC-031.** `_ids`, `_thread_id` and `_thread_ids` carried no bound at all, and the
round-8 reflection test exempted them while claiming broader protection. They are bounded,
and the exemption is gone.

Every probe below is written as an attack rather than as a unit test of the fix: it puts
real prose in the field and asserts the seal refuses it. Each one is verified to fail
against the round-8 behaviour - the reintroduction counts are in
`docs/reviews/ROUND_09/HANDOFF.md`.

No personal mail content appears here. Every sentence is invented for this repository.
"""

from __future__ import annotations

import pytest

from mailweave.envelope import Depth, DispositionLedger, RungId
from mailweave.envelope.disposition import (
    MAX_SEALED_SCALAR_CHARS,
    FetchedIds,
    ObservedEndpoint,
    _is_one_line,
)
from mailweave.errors import DispositionInvariantError
from tests.fixtures import envelope_kit as kit

#: The reviewer's payload: one line, 49 characters, no `\n` or `\r`. It cleared every round-8
#: check and reached the wire verbatim under two different metadata field names.
SNIPPET = "Please review the attached NDA before end of day."

#: Five lines of prose, for the id fields R-SEC-031 found unbounded.
MAIL_TEXT = (
    "Thanks for the update on this.\n"
    "\n"
    "Once the negotiations concluded, the legal team wrote:\n"
    "\n"
    "We should have a decision by end of week either way.\n"
)

#: Every code point `str.splitlines()` treats as a line break and round 8's check did not.
#: Listed here as *test data* rather than as the implementation's definition, which is the
#: whole point of R-SEC-029: the code asks the runtime, and the test asks whether the code
#: agrees with the runtime on each of these.
NON_ASCII_LINE_BOUNDARIES = (" ", " ", "", "", "")


def observation(**scalars: object) -> FetchedIds:
    return FetchedIds(
        ids=["m1"],
        endpoint=ObservedEndpoint.THREADS_GET,
        thread_id="t1",
        **scalars,  # type: ignore[arg-type]
    )


# --- R-SEC-029: every line boundary, not the two somebody remembered ---------------------


@pytest.mark.parametrize("boundary", NON_ASCII_LINE_BOUNDARIES, ids=lambda c: f"U+{ord(c):04X}")
def test_a_sealed_scalar_refuses_every_unicode_line_boundary(boundary: str) -> None:
    """R-SEC-029's reproduction, one code point at a time.

    The reviewer's probe was `"Line one" + chr(0x2028) + "Line two - the real second
    sentence"`: 54 characters, genuinely two lines, and accepted as "a single line". Python
    reports two lines for every boundary below, and so, now, does the seal.

    The value is also a valid digit string on either side of the break, so the *only* thing
    that can refuse it is the line-break check - a digit-shape check alone would pass it.
    """
    two_lines = f"175655773100{boundary}9912003"
    assert len(two_lines.splitlines()) == 2, "the premise: Python calls this two lines"
    assert "\n" not in two_lines and "\r" not in two_lines, "and round 8's check saw one"
    with pytest.raises(DispositionInvariantError, match="line break"):
        observation(history_id=two_lines)
    with pytest.raises(DispositionInvariantError, match="line break"):
        observation(internal_dates={"m1": two_lines})
    with pytest.raises(DispositionInvariantError, match="line break"):
        observation(fetched_at=two_lines)


def test_the_line_check_is_the_runtimes_definition_and_not_a_transcribed_list() -> None:
    """The property that covers the *next* boundary character, not only today's five.

    A hand-listed set is a snapshot of what its author knew, and this project has now been
    caught four times by "one shape checked, the rest silently absent". So the predicate is
    checked against `str.splitlines()` itself across the whole code-point range that can
    plausibly matter, rather than against the five R-SEC-029 named: if a future Unicode
    revision adds a boundary and CPython honours it, the seal honours it too, and this test
    is what says so.
    """
    for code_point in range(0x0000, 0x3000):
        character = chr(code_point)
        probe = f"a{character}b"
        assert _is_one_line(probe) is (probe.splitlines() == [probe]), (
            f"the seal disagrees with str.splitlines() about U+{code_point:04X}"
        )
    assert _is_one_line("one line") is True
    # A trailing break is a break: `"one\n".splitlines()` is `["one"]`, so a length check
    # against `splitlines()` would have passed this.
    assert _is_one_line("one\n") is False
    assert len("one\n".splitlines()) == 1, "which is exactly why the check compares lists"


# --- R-SEC-030: a metadata field has a shape, and prose is not it ------------------------


def test_a_real_sentence_cannot_be_sealed_as_gmail_metadata() -> None:
    """The central round-8 finding, reproduced and refused.

    49 characters, one line, no control characters: it cleared the length bound and the
    newline bound, because those were the only two checks `history_id` and `internal_date`
    had. `fetched_at` alone resisted, because it was the only one of the three checked
    against a real shape.
    """
    assert len(SNIPPET) <= MAX_SEALED_SCALAR_CHARS and SNIPPET.splitlines() == [SNIPPET]
    with pytest.raises(DispositionInvariantError, match="not the shape Gmail returns"):
        observation(history_id=SNIPPET)
    with pytest.raises(DispositionInvariantError, match="not the shape Gmail returns"):
        observation(internal_dates={"m1": SNIPPET})


@pytest.mark.parametrize(
    "value",
    [
        "1756557731000abc",  # digits with a tail
        "abc",  # no digits at all
        "-1756557731000",  # a sign is not a Gmail id
        "1.756557731e12",  # scientific notation
        " 1756557731000",  # leading space
        "1756557731000 ",  # trailing space
        "0x1a2b3c",  # hex, which a `historyId` is not
        "١٧٥٦٥٥٧٧٣١٠٠٠",  # Arabic-Indic digits: `str.isdigit()` says True
        "²",  # a superscript: `str.isdigit()` says True
        "١",  # one Arabic-Indic digit
        "9" * 21,  # wider than a uint64 can render
    ],
    ids=lambda value: repr(value)[:24],
)
def test_only_the_decimal_shape_gmail_returns_is_accepted(value: str) -> None:
    """Including the two shapes a `str.isdigit()` check would have let through.

    `"١٣".isdigit()` is `True` and `"²".isdigit()` is `True`, and neither is anything Gmail
    emits. Writing the check as "digits" rather than as "ASCII decimal digits" would be this
    project's own pattern committed inside the fix for it, so both are probed by name.
    """
    with pytest.raises(DispositionInvariantError, match="not the shape Gmail returns"):
        observation(history_id=value)
    with pytest.raises(DispositionInvariantError, match="not the shape Gmail returns"):
        observation(internal_dates={"m1": value})


def test_the_real_values_are_still_accepted() -> None:
    """The other direction: a fix that refused Gmail's own output would be worse than the hole."""
    sealed = observation(
        history_id="99120034",
        internal_dates={"m1": "1756557731000"},
        fetched_at=kit.FETCHED_AT,
        stated_total=1,
        positions={"m1": 0},
    )
    assert sealed.size == 1
    # A uint64 at full width is 20 digits, and that is the widest real value there is.
    observation(history_id="1" + "8" * 19)


def test_a_stub_rows_internal_date_can_only_be_a_timestamp() -> None:
    """The depth-ceiling half of R-SEC-030, closed by the shape check and stated on the record.

    The reviewer's sharpest probe was a `Depth.STUB` row - `content is None` by construction,
    because a stub discloses nothing - whose `internal_date` on the wire was the full
    sentence. The row is still written with an `internal_date`, and that is a decision rather
    than an oversight: with the shape check the field can only be a decimal millisecond
    count, which is the same class of bookkeeping scalar as the `position` a stub already
    carries. Contract R-04's stub tier withholds *content*, and a timestamp is not content.

    What is closed is the channel. This test is the executable form of that argument: the
    sentence cannot be sealed, so it cannot be written onto a stub row, so the stub row
    discloses a number or nothing.
    """
    with pytest.raises(DispositionInvariantError, match="not the shape Gmail returns"):
        FetchedIds(
            ids=["stub1"],
            endpoint=ObservedEndpoint.THREADS_GET,
            thread_id="t1",
            stated_total=1,
            positions={"stub1": 0},
            internal_dates={"stub1": SNIPPET},
        )

    ledger = DispositionLedger()
    ledger.record_thread(
        FetchedIds(
            ids=["stub1"],
            endpoint=ObservedEndpoint.THREADS_GET,
            thread_id="t1",
            stated_total=1,
            positions={"stub1": 0},
            internal_dates={"stub1": "1756557731000"},
            history_id="99120034",
            fetched_at=kit.FETCHED_AT,
        ),
        rung=RungId.L4,
    )
    certificate = ledger.certify(["stub1"])
    assert certificate.observed_internal_dates["stub1"] == "1756557731000"
    nonce = "n" * 12
    stub = kit.row("stub1", "t1", 0, nonce=nonce, depth=Depth.STUB)
    assert stub.content is None


# --- R-SEC-031: the id fields the reflection test exempted -------------------------------


def test_the_seals_id_fields_carry_a_bound_now() -> None:
    """R-SEC-031's reproduction: five lines of prose stored verbatim as a message id.

    Not new to A6 - `FetchedIds` has held these fields since amendment A2 in round 4 - and
    reachable only through the same in-process construction A1's residual already covers. It
    is closed anyway, because the round-8 test that exempted them said in its own docstring
    that "a future field of the wrong shape fails here", and a guarantee that exempts the
    fields most naturally shaped to carry text is not the guarantee it claims.
    """
    with pytest.raises(DispositionInvariantError, match="short single-line string"):
        FetchedIds(ids=[MAIL_TEXT], endpoint=ObservedEndpoint.THREADS_GET, thread_id="t1")
    with pytest.raises(DispositionInvariantError, match="short single-line string"):
        FetchedIds(ids=["m1"], endpoint=ObservedEndpoint.THREADS_GET, thread_id=MAIL_TEXT)
    with pytest.raises(DispositionInvariantError, match="short single-line string"):
        FetchedIds(
            ids=["m1"],
            endpoint=ObservedEndpoint.MESSAGES_LIST,
            page_size=25,
            thread_ids={"m1": MAIL_TEXT},
        )
    # One long line clears the newline check and is still refused on length.
    with pytest.raises(DispositionInvariantError, match="short single-line string"):
        FetchedIds(
            ids=["x" * (MAX_SEALED_SCALAR_CHARS + 1)],
            endpoint=ObservedEndpoint.THREADS_GET,
            thread_id="t1",
        )
    # And a boundary character the round-8 check would have missed, in an id.
    with pytest.raises(DispositionInvariantError, match="short single-line string"):
        FetchedIds(
            ids=["m1 still the same id, honestly"],
            endpoint=ObservedEndpoint.THREADS_GET,
            thread_id="t1",
        )
    # An empty id is not an id.
    with pytest.raises(DispositionInvariantError, match="cannot record an id"):
        FetchedIds(ids=[""], endpoint=ObservedEndpoint.THREADS_GET, thread_id="t1")
    # The ids this repository and every reviewer probe actually use are unaffected.
    assert (
        FetchedIds(
            ids=["m1", "ghost-1"], endpoint=ObservedEndpoint.THREADS_GET, thread_id="t1"
        ).size
        == 2
    )
