"""Round 30: the two declaration inconsistencies the live v0.1 acceptance run exposed.

Both come from one live record, `validation-records/rmcp033-acceptance-hit-threads-1.json`,
taken on commit `632cfbc` against a real mailbox. Its material fields:

    budget_caps_hit: ["max_server_ms"]
    omission.withheld_by_cap: {"max_hit_threads": 44, "max_server_ms": 1}
    omission.bound: "the response reached its declared token ceiling"
    rendered_chars: 8748     (host cap 25,000)
    sources: 0, matched_rows: 0, partial: true, declined: false

Two things in that record contradict each other and the governing documents:

1. `omission.bound` names the token ceiling, while `budget_caps_hit` does not contain
   `disclosed_token_ceiling` - so by the response's own accounting no A.9a step ran and no
   ceiling reduced anything. `OmissionSummary.bound` documents itself as "`None` when the
   ladder reduced nothing", so the producers were violating the field's own contract by
   stating it unconditionally.

2. `max_hit_threads` withheld 44 of the 45 messages and is absent from `budget_caps_hit`.
   AD A.7 lists it in **Global caps per top-level query**, and AD D.11's row reads
   `budget_exhausted | in-band budget_caps_hit | a per-query cap reached`. A per-query cap
   that was reached declares itself in that list; its absence is a contract violation, not a
   second set of semantics. The A.7 note on the cap says it is "**Never** silently exceeded".

Fixing (2) also repaired an outcome defect it had been concealing. `account.outcome_of`
implements D.3 rule 5 verbatim - any cap exhausted means `inconclusive`, and `answered`
requires that no cap fired - reading the rule off `budget_caps_hit`. With the cap missing from
that list, a response that never looked at thirteen of fourteen hit-bearing threads called
itself `answered`.
"""

from __future__ import annotations

from typing import Any

import pytest

from mailweave.constants import HOST_RESULT_CHAR_CAP
from mailweave.envelope.measure import rendered_chars
from mailweave.surface.partition import rendered_of
from mailweave.surface.server import call
from tests.fixtures.mailbox import SyntheticMailbox
from tests.test_mcp_surface_round24 import make_service, structured_of
from tests.test_r_mcp_033_round29 import TERM, few_threads_many_messages, single_message_threads


def _served(result: Any) -> dict[str, Any]:
    assert not result.is_error, structured_of(result).get("remediation")
    return structured_of(result)


def _caps_that_withheld(payload: dict[str, Any]) -> set[str]:
    """Every cap named by anything in the response that accounts for a withholding."""
    return (
        {record["cap"] for record in payload["withheld"]}
        | {group["cap"] for group in payload["withheld_groups"]}
        | {entry["cap"] for entry in (payload.get("withheld_tail") or ())}
    )


#: Shapes that withhold something, driven by a width cap or a budget cap. The invariant below
#: is asserted over all of them rather than on the acceptance shape alone, because the defect
#: was a missing general rule and not a missing special case.
WITHHOLDING_SHAPES: tuple[tuple[str, SyntheticMailbox, dict[str, Any]], ...] = (
    (
        "width cap, the acceptance shape",
        few_threads_many_messages(threads=14),
        {"query": TERM, "budget": {"max_hit_threads": 1}},
    ),
    ("width cap at the published width", few_threads_many_messages(threads=18), {"query": TERM}),
    (
        "single-message threads, capped",
        single_message_threads(threads=30),
        {"query": TERM, "budget": {"max_hit_threads": 1}},
    ),
    (
        "a budget cap mid-map",
        few_threads_many_messages(threads=12, per_thread=2),
        {"query": TERM, "budget": {"max_api_calls": 16}},
    ),
)

#: A shape the A.9a ladder genuinely degrades. It withholds nothing, which is the point: it is
#: what keeps the absence of `omission.bound` meaningful by proving presence still happens.
CEILING_SHAPE = (few_threads_many_messages(threads=3, per_thread=12), {"query": TERM})


@pytest.mark.parametrize(
    "label,box,args", WITHHOLDING_SHAPES, ids=[s[0] for s in WITHHOLDING_SHAPES]
)
def test_every_cap_that_withheld_content_names_itself_in_budget_caps_hit(
    label: str, box: SyntheticMailbox, args: dict[str, Any]
) -> None:
    """AD A.7 + D.11: a per-query cap that was reached is declared in `budget_caps_hit`.

    The live record had `max_hit_threads` withholding 44 messages and naming itself in every
    one of thirteen `withheld_groups[]` entries, while `budget_caps_hit` said `max_server_ms`
    alone. A reader asking "what cost me content" was told about the one and not the
    forty-four.

    `partial_source_failure` is deliberately not required here and cannot appear: it is a
    source whose sub-request failed rather than a budget that ran out, and it has no
    `BudgetCapName`. The record that names it still carries its own cap and its own call.
    """
    payload = _served(call(make_service(box), "mailweave_search", args))
    declared = set(payload["retrieval_report"]["budget_caps_hit"])
    withheld_by = _caps_that_withheld(payload) - {"partial_source_failure"}
    assert withheld_by, f"{label}: the fixture withheld nothing, so it tests nothing"
    assert withheld_by <= declared, (label, sorted(withheld_by - declared), sorted(declared))


@pytest.mark.parametrize(
    "label,box,args", WITHHOLDING_SHAPES, ids=[s[0] for s in WITHHOLDING_SHAPES]
)
def test_a_response_that_hit_a_cap_never_calls_itself_answered(
    label: str, box: SyntheticMailbox, args: dict[str, Any]
) -> None:
    """D.3 rule 5, read off the repaired cap list: any cap exhausted means `inconclusive`.

    This is the defect the missing cap entry concealed. `outcome_of` already implemented the
    rule; it was reading a list that did not mention the cap that fired.
    """
    payload = _served(call(make_service(box), "mailweave_search", args))
    assert payload["retrieval_report"]["budget_caps_hit"], label
    assert payload["retrieval_report"]["outcome"] != "answered", label


def test_the_acceptance_shape_states_no_ceiling_it_did_not_reach() -> None:
    """The live 5.1 record's first contradiction, as a property of the served response.

    Cap-driven omissions, no ladder step, well inside the host cap: `omission.bound` is absent
    because there is no ceiling to name, and nothing in the response refers to it. The counts
    stay exact, which is what R-MCP-033 bought and what this must not cost.
    """
    payload = _served(
        call(
            make_service(few_threads_many_messages(threads=14)),
            "mailweave_search",
            {"query": TERM, "budget": {"max_hit_threads": 1}},
        )
    )
    caps = payload["retrieval_report"]["budget_caps_hit"]
    assert "disclosed_token_ceiling" not in caps, "the fixture must not reach the ceiling"
    assert payload["omission"]["bound"] is None, payload["omission"]["bound"]
    assert payload["omission"]["withheld_messages"] == sum(
        payload["omission"]["withheld_by_cap"].values()
    )
    assert "max_hit_threads" in caps


def test_a_response_the_ladder_did_reduce_still_names_the_ceiling_that_bound() -> None:
    """The other half: absence must mean something, so presence has to survive.

    A shape the ceiling genuinely degrades keeps its one shared sentence, and
    `disclosed_token_ceiling` appears in the cap list beside it - the two declarations agreeing
    is the whole point of the round.
    """
    box, args = CEILING_SHAPE
    payload = _served(call(make_service(box), "mailweave_search", args))
    caps = payload["retrieval_report"]["budget_caps_hit"]
    assert "disclosed_token_ceiling" in caps, caps
    assert payload["omission"]["bound"], "a ceiling bound and the response must say which"


def test_the_declarations_agree_on_every_shape_and_the_response_still_fits() -> None:
    """One sweep: `bound` is present exactly when the ceiling is in the cap list.

    Written as a biconditional because both directions failed at different times - stating a
    ceiling that did not bind (round 29, found live) and, before that, embedding it in every
    record instead of once.
    """
    for label, box, args in (*WITHHOLDING_SHAPES, ("the ceiling itself", *CEILING_SHAPE)):
        result = call(make_service(box), "mailweave_search", args)
        payload = _served(result)
        ceiling_fired = "disclosed_token_ceiling" in payload["retrieval_report"]["budget_caps_hit"]
        stated = payload["omission"]["bound"] is not None
        assert ceiling_fired == stated, (label, ceiling_fired, payload["omission"]["bound"])
        mirrored = rendered_of(result)
        assert rendered_chars(mirrored.structured, mirrored.text) <= HOST_RESULT_CHAR_CAP, label


def test_a_depth_only_reduction_still_names_the_ceiling_that_bound() -> None:
    """R-V30-005: the ladder can reduce by depth alone, splitting and withholding nothing.

    Found by the round-30 reviewer against the first version of `a_ceiling_bound`, which asked
    only whether the host cap bound, a source was split off, or an id was withheld. A response
    the token ceiling degrades by demoting bodies to snippets or stubs answers no to all three
    while `truncated_by` reads `mailweave` and `budget_caps_hit` carries
    `disclosed_token_ceiling`. The ceiling bound and the response said nothing about it - and
    asymmetrically, since the same demotion forced by the host cap did state its sentence.
    """
    payload = _served(
        call(
            make_service(few_threads_many_messages(threads=1, per_thread=10)),
            "mailweave_search",
            {"query": TERM, "budget": {"max_disclosed_tokens": 1_800}},
        )
    )
    assert payload["truncated_by"] == "mailweave"
    assert "disclosed_token_ceiling" in payload["retrieval_report"]["budget_caps_hit"]
    assert not payload["withheld"] and not payload["not_included_sources"], (
        "the shape under test reduces by depth alone; it must split and withhold nothing"
    )
    assert payload["omission"]["bound"], "the ceiling bound and the response must say which"


@pytest.mark.parametrize(
    "tool,per_thread,reduces",
    (
        # A thread map is planned as a page that fits (navigation redesign, 2026-09-14): a
        # 40-message thread is served as page 0 with the rest as runs, and no ceiling fires
        # on it - so it must state no bound, in either size.
        ("mailweave_thread_map", 40, False),
        ("mailweave_thread_map", 6, False),
        # A batch read of fourteen bodies in a 40-message thread does not fit whole, so the
        # fit loop cuts it and the ceiling that bound is stated; six fits, and nothing is.
        ("mailweave_get_messages", 40, True),
        ("mailweave_get_messages", 6, False),
    ),
)
def test_the_expansion_producer_states_its_bound_on_the_same_rule(
    tool: str, per_thread: int, reduces: bool
) -> None:
    """R-V30-006: the expansion half of the fix had no test and no replant.

    Reverting `surface/expansion.py`'s gate to `if True:` left a hundred tests green across ten
    files, because every other round-30 assertion goes through `mailweave_search`. `thread_map`
    and `get_messages` are the two tools that reach the other producer.

    **Both directions, or it catches nothing.** The first version of this test used only a
    thread large enough to reduce, so an unconditional `bound` satisfied it and the replant went
    uncaught. The small shape is the one that binds: nothing reduces, so a producer that states
    the sentence anyway is naming a ceiling it never reached. Since the navigation redesign a
    thread map never reduces - it is paged - so the map tool tests the small direction at both
    sizes and the read tool carries the reducing direction.
    """
    box = few_threads_many_messages(threads=1, per_thread=per_thread)
    service = make_service(box)
    if tool == "mailweave_thread_map":
        args: dict[str, Any] = {"thread_id": "th000ffffffffffff"}
    else:
        args = {
            "message_ids": [f"m000{m:02d}ffffffffff" for m in range(min(per_thread, 14))],
            "view": "body_clean",
        }
    payload = _served(call(service, tool, args))
    ceiling_fired = "disclosed_token_ceiling" in payload["retrieval_report"]["budget_caps_hit"]
    stated = payload["omission"]["bound"] is not None
    assert ceiling_fired is reduces, (tool, per_thread, "the fixture no longer tests its case")
    assert ceiling_fired == stated, (tool, per_thread, payload["omission"]["bound"])
