"""The three sizing constants round 29 changed, certified against every reason variant.

**Why this file exists.** Round 29 changed `WITHHELD_RECORD_CHARS`, `NOT_INCLUDED_SOURCE_CHARS`
and added `WITHHELD_GROUP_CHARS` and `NOT_INCLUDED_BLOCK_CHARS`, each from a measurement. Three
measured constants in one round is the pattern that should make a reviewer suspicious, and the
owner said so: they are provisional until certified against every reason variant a record can
carry and against the supported identifier-width boundaries. This file is that certification.

The method is the one round 27 used and the one that found the defect: render the record, its
affordance's twin in `affordances[]` and its mirror lines through the **real** renderer, count
the characters, and require the charge to be at or above the count. Not a script in a
docstring - a test, so the day a reason sentence grows or a mirror line gains a word, the
constant that no longer bounds it fails here rather than in a host's silent truncation.

**What was wrong before.** `WITHHELD_RECORD_CHARS` was measured in round 27 against the
token-ceiling reason (46 characters) and charged for the host-cap reason too (282). Under by a
flat 225 at every width. It was invisible because `NOT_INCLUDED_SOURCE_CHARS` over-charged by
~500 in the other direction, and every shape had both. Correcting the one exposed the other.
That is exactly the failure this file is built to catch: one variant validated, its peers
trusted.

No fixture here carries real or realistic mail.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mailweave.constants import HOST_RESULT_CHAR_CAP, MAX_GMAIL_NUMERIC_ID_DIGITS
from mailweave.disclosure.ladder import HOST_CAP_WHY
from mailweave.envelope.measure import (
    NOT_INCLUDED_BLOCK_CHARS,
    affordance_echo_chars,
    json_string_chars,
    not_included_block_chars,
    not_included_chars,
    withheld_chars,
    withheld_group_chars,
)
from mailweave.envelope.vocab import Depth, ToolName, WithheldCap
from mailweave.envelope.wire import (
    Affordance,
    NotIncludedBlock,
    NotIncludedSource,
    WithheldGroup,
    WithheldRecord,
)
from mailweave.surface.rendering import _residue_lines

#: The identifier widths the wire accepts. Gmail's ids are 16 hexadecimal characters in
#: practice; the wire enforces only `min_length=1`, and numeric ids are bounded at
#: `MAX_GMAIL_NUMERIC_ID_DIGITS`. So the boundaries are 1, the observed 16, the numeric cap,
#: and 30 as the width round 27 measured to - anything the estimate holds at all four of, it
#: holds at every width between by linearity of the charge.
WIDTHS = (1, 16, MAX_GMAIL_NUMERIC_ID_DIGITS, 30)

_BOUND = HOST_CAP_WHY.format(cap=HOST_RESULT_CHAR_CAP)

#: **Every `why` a withheld record can carry, at its longest.** Each is the sentence the code
#: builds, with every numeric fill at the widest value it can take. A variant missing from this
#: list is a variant the constant is not certified against, so the list is closed below.
WITHHELD_WHYS: dict[str, str] = {
    "step_8_row": (
        "A.9a step 8: this message could not be carried even as a collapsed-run member within "
        "the ceiling stated in omission.bound"
    ),
    "step_7_split_single": (
        "A.9a step 7: this source was split off to fit the ceiling stated in omission.bound"
    ),
    "max_hit_threads": ("99999 hit-bearing threads; 99999 mapped at max_hit_threads=99999"),
    "max_source_threads": (
        "99999 threads recovered by structural expansion; 99999 mapped at max_source_threads=99999"
    ),
    "budget_cap": ("max_quota_units: 999999999 of 999999999; this thread's map was not fetched"),
    "partial_source_failure": (
        "this thread could not be mapped; not_included_sources says why for thread " + "t" * 30
    ),
}

#: The reasons a group or a not-included block can carry: thread-granular caps only.
GROUP_WHYS: dict[str, str] = {
    k: v
    for k, v in WITHHELD_WHYS.items()
    if k in ("step_7_split_single", "max_hit_threads", "max_source_threads")
}
BLOCK_WHYS: dict[str, str] = {
    "step_7": WITHHELD_WHYS["step_7_split_single"],
    "unmappable_omitted": (
        "the source returned this thread without 99999 of its matching message(s), out of "
        "99999 it enumerated, so no map of it can be shown; the withheld records name the "
        "messages"
    ),
    "unmappable_unplaced": (
        "the source stated no chronological position for 99999 of this thread's messages, so "
        "it cannot be shown in order; the withheld records name the messages"
    ),
}


def _twin(affordance: Affordance) -> int:
    """The affordance's own entry in `affordances[]`, which every record also costs.

    Serialised with the default separators, which is what the wire uses (R-V01-013: the
    first version used compact separators and under-measured every record by 21-25).
    """
    return len(json.dumps(affordance.model_dump(mode="json")))


def _mirror(structured: dict[str, Any]) -> int:
    """The mirror lines the real renderer emits for this residue, plus their newlines."""
    lines = _residue_lines(structured)
    return sum(len(line) + 1 for line in lines)


def _entry(model: Any) -> int:
    return len(json.dumps(model.model_dump(mode="json")))


#: The affordance each record variant really carries on the wire (R-V01-013(a): the first
#: census certified the budget-cap variant with a thread map, and the real one is the caller's
#: own search, query included, so the record's size grows with the query).
QUERIES = ("q", "after:2026/09/01", "q" * 300, 'subject:"a \\"quoted\\" phrase" ' + "x" * 800)


def _record_affordance(variant: str, *, thread_id: str, message_id: str, query: str) -> Affordance:
    if "step" in variant or "partial" in variant:
        return Affordance(
            tool=ToolName.GET_MESSAGES,
            args={"message_ids": [message_id], "view": Depth.BODY_CLEAN.value},
        )
    if variant == "budget_cap":
        return Affordance(
            tool=ToolName.SEARCH, args={"query": query, "budget": {"max_quota_units": 999999999}}
        )
    return Affordance(tool=ToolName.THREAD_MAP, args={"thread_id": thread_id})


@pytest.mark.parametrize("query", QUERIES)
@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("variant", sorted(WITHHELD_WHYS))
def test_a_withheld_record_is_charged_at_or_above_what_it_renders(
    variant: str, width: int, query: str
) -> None:
    thread_id, message_id = "t" * width, "m" * width
    affordance = _record_affordance(
        variant, thread_id=thread_id, message_id=message_id, query=query
    )
    record = WithheldRecord(
        id=message_id,
        thread_id=thread_id,
        cap=WithheldCap.DISCLOSED_TOKEN_CEILING,
        why=WITHHELD_WHYS[variant],
        affordance=affordance,
    )
    dumped = record.model_dump(mode="json")
    structured = {"withheld": [dumped], "affordances": [affordance.model_dump(mode="json")]}
    measured = _entry(record) + _twin(affordance) + _mirror(structured)
    if affordance.tool is ToolName.SEARCH:
        # A budget-cap record carries the query once, and the call in `affordances[]` that
        # every record under that cap shares carries it again - charged once for all of them
        # by `request_echo_chars`, at its exact serialised size, not once per record.
        # This is the layout's own arithmetic for one record under a breached cap.
        charged = withheld_chars(message_id, width, json_string_chars(query)) + (
            affordance_echo_chars(affordance)
        )
    else:
        charged = withheld_chars(message_id, width)
    assert charged >= measured, (variant, width, len(query), charged, measured, measured - charged)


def test_a_query_is_charged_at_its_escaped_length() -> None:
    """A query with quotes renders longer than it reads; `json_string_chars` is what the
    estimate charges, so a quoted query cannot slip under the record's or the tail's charge."""
    plain, quoted = "x" * 10, '"' * 10
    assert json_string_chars(plain) == 10
    assert json_string_chars(quoted) == 20 == len(json.dumps(quoted)) - 2


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("variant", sorted(GROUP_WHYS))
def test_a_withheld_group_is_charged_at_or_above_what_it_renders(variant: str, width: int) -> None:
    thread_id = "t" * width
    affordance = Affordance(tool=ToolName.THREAD_MAP, args={"thread_id": thread_id})
    group = WithheldGroup(
        thread_id=thread_id,
        cap=WithheldCap.MAX_HIT_THREADS,
        why=GROUP_WHYS[variant],
        message_count=99999,
        affordance=affordance,
    )
    structured = {
        "withheld_groups": [group.model_dump(mode="json")],
        "affordances": [affordance.model_dump(mode="json")],
    }
    measured = _entry(group) + _twin(affordance) + _mirror(structured)
    charged = withheld_group_chars(width)
    assert charged >= measured, (variant, width, charged, measured, measured - charged)


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("variant", sorted(BLOCK_WHYS))
def test_a_not_included_block_and_its_entries_are_charged_at_or_above_what_they_render(
    variant: str, width: int
) -> None:
    """The block once plus one entry each, against the block charge plus the entry charge.

    Measured with several entries rather than one, so an entry's marginal cost is what is
    certified and the block's fixed cost cannot hide inside a single entry's slack.
    """
    entries = []
    affordances = []
    for index in range(5):
        thread_id = ("t" * width)[:-1] + str(index) if width > 1 else str(index)
        affordance = Affordance(tool=ToolName.THREAD_MAP, args={"thread_id": thread_id})
        entries.append(
            NotIncludedSource(thread_id=thread_id, stated_total=99999, affordance=affordance)
        )
        affordances.append(affordance)
    block = NotIncludedBlock(why=BLOCK_WHYS[variant], sources=tuple(entries))
    structured = {
        "not_included_sources": [block.model_dump(mode="json")],
        "affordances": [a.model_dump(mode="json") for a in affordances],
    }
    measured = _entry(block) + sum(_twin(a) for a in affordances) + _mirror(structured)
    charged = not_included_block_chars() + 5 * not_included_chars(width)
    assert charged >= measured, (variant, width, charged, measured, measured - charged)


def test_the_block_charge_is_the_constant_and_the_constant_bounds_the_longest_reason() -> None:
    """The block's own cost is flat, and the reason it must bound is the longest one."""
    assert not_included_block_chars() == NOT_INCLUDED_BLOCK_CHARS
    longest = max(len(why) for why in BLOCK_WHYS.values())
    assert longest < NOT_INCLUDED_BLOCK_CHARS, (NOT_INCLUDED_BLOCK_CHARS, longest)


def test_no_reason_variant_embeds_the_host_cap_sentence_any_more() -> None:
    """The point of `omission.bound`: the 206-character explanation is stated once, there.

    A reason that still embeds it has reintroduced the repetition this round removed, and
    every record carrying that reason pays for it again. This is what keeps the certified
    constants from quietly ceasing to bound the reasons they were certified against.
    """
    for name, why in {**WITHHELD_WHYS, **BLOCK_WHYS}.items():
        assert _BOUND not in why, name
        assert "the host's" not in why, name


# --- the repair pass (R-V01-005, R-V01-007): the run member's third copy, and the tail ------

from mailweave.envelope.measure import collapsed_run_chars, withheld_tail_chars  # noqa: E402
from mailweave.envelope.wire import CollapsedRun, WithheldTail  # noqa: E402


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("members", (1, 5, 50, 300))
@pytest.mark.parametrize("path", ("search", "expansion"))
def test_a_collapsed_run_is_charged_at_or_above_what_it_renders(
    members: int, width: int, path: str
) -> None:
    """R-V01-005, re-certified against the two run forms the wire actually carries.

    **Navigation redesign (2026-09-14).** A run's affordance no longer lists its members: the
    search path names a page of the thread's map (`thread_map(thread_id, page)`, twinned in
    `affordances[]`), the expansion path names a page too (not twinned). A member's id therefore renders **once**, in `member_ids`, and
    `COLLAPSED_RUN_MEMBER_ID_COPIES` says so. The charge is certified here against both forms
    at every id width, and against the wider of the two scaffolds.
    """
    if members > 10**width:
        pytest.skip("more members than distinct ids of this width")
    ids = [str(i).rjust(width, "0")[-width:] for i in range(members)]
    thread_id = "t" * width
    if path == "search":
        affordance = Affordance(tool=ToolName.THREAD_MAP, args={"thread_id": thread_id, "page": 12})
        twin = _twin(affordance)
        why = "A.9a step 5: stub run collapsed to fit the declared ceiling"
    else:
        affordance = Affordance(tool=ToolName.THREAD_MAP, args={"thread_id": thread_id, "page": 12})
        twin = 0
        why = WithheldCap.MAP_PAGE.value
    run = CollapsedRun(
        positions=(3, 3 + members - 1),
        count=members,
        member_ids=tuple(ids),
        affordance=affordance,
        why=why,
    )
    mirror = (
        len(
            f"  collapsed positions 3-{3 + members - 1}: {members} messages not shown, "
            "expand with mailweave_thread_map"
        )
        + 1
        + (len("next call mailweave_thread_map") + 1 if twin else 0)
    )
    measured = _entry(run) + twin + mirror
    charged = collapsed_run_chars(ids, thread_id)
    assert charged >= measured, (path, members, width, charged, measured, measured - charged)


def test_a_run_member_is_charged_the_copies_the_wire_carries() -> None:
    """The constant is a measurement, not a choice: one copy, in `member_ids`, on both paths."""
    from mailweave.envelope.measure import COLLAPSED_RUN_MEMBER_ID_COPIES

    assert COLLAPSED_RUN_MEMBER_ID_COPIES == 1


@pytest.mark.parametrize("query_chars", (1, 7, 100, 300, 1_000))
def test_a_withheld_tail_is_charged_at_or_above_what_it_renders(query_chars: int) -> None:
    """R-V01-007: the tail's widening call carries the query twice; every count at its
    widest; the longest thread-cap reason."""
    affordance = Affordance(
        tool=ToolName.SEARCH,
        args={"query": "q" * query_chars, "budget": {"max_hit_threads": 12}},
    )
    tail = WithheldTail(
        cap=WithheldCap.MAX_HIT_THREADS,
        why=WITHHELD_WHYS["max_source_threads"],
        thread_count=99999,
        message_count=99999,
        affordance=affordance,
    )
    structured = {
        "withheld_tail": [tail.model_dump(mode="json")],
        "affordances": [affordance.model_dump(mode="json")],
    }
    measured = _entry(tail) + _twin(affordance) + _mirror(structured)
    charged = withheld_tail_chars(query_chars)
    assert charged >= measured, (query_chars, charged, measured, measured - charged)
