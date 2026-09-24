"""Round 27: the three things between the estimate and real mail.

Every test here drives the **served** path - `surface.server.call`, the only path a client
has - because all three defects this round fixes were invisible from one layer down:

  * `Reduction` and `MessageRow` each held the rule "a reduction must declare a size", and
    only one of them held the list of kinds that are declarations rather than removals. Every
    unit test of `content` passed and every unit test of `envelope` passed, and an ordinary
    `multipart/alternative` message - a text part and an HTML part, which is most real mail -
    made `mailweave_search` answer `-32603 "this is a defect in this server"` (R-MCP-023);
  * `layout_chars` was certified against `rendered_chars` over ten shapes that were
    single-source on every one of them, and was not a bound the moment a response carried
    more than two threads (R-MCP-024, R-MCP-030);
  * the `retry_with` a declined search handed back named a budget key the same server's
    argument reader refused, so the one call offered as the way out came back `-32602`
    (R-MCP-025).

The three rules of round 25 and 26 still govern: no test compares a derivation with itself; a
fixture is the shape the mailbox produces rather than the shape the assertion needs; and a
size claim is measured on the rendered form. Round 27 adds a fourth, which is what all three
findings have in common: **a rule written twice is a rule that will disagree with itself**, so
each fix here deletes a copy rather than correcting one.

No fixture carries real or realistic personal mail. Addresses use the reserved `.example` and
`.invalid` TLDs (RFC 2606/6761) and every subject, body and filename is invented.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from mailweave.constants import HOST_RESULT_CHAR_CAP
from mailweave.content.reductions import Reduction, ReductionKind
from mailweave.disclosure.layout import widest_thread_id
from mailweave.envelope.measure import rendered_chars
from mailweave.policy.budget import WITHHELD_CAP_OF
from mailweave.surface.arguments import (
    BUDGET_KEYS,
    parse_get_messages,
    parse_search,
    parse_thread_map,
)
from mailweave.surface.partition import rendered_of
from mailweave.surface.recovery import narrower_call
from mailweave.surface.server import call
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.omission import not_included_entries, withheld_threads
from tests.test_mcp_surface_round24 import make_service, structured_of
from tests.test_round26 import FILLER, TERM

# =============================================================================================
# Part 1 - the message format every inbox is full of (R-MCP-023)
# =============================================================================================

#: The three declared charsets round 26's review named, plus the shape that is not a charset
#: problem at all. `ISO-8859-8-I` is a real registered name Python cannot resolve, `unicode`
#: is what several clients send when they mean UTF-8, and `UNKNOWN-8BIT` is RFC 1428's
#: placeholder for "the gateway did not know". All three arrive in ordinary mail.
UNRESOLVABLE_CHARSETS = ("ISO-8859-8-I", "unicode", "UNKNOWN-8BIT")

ORDINARY_SHAPES: dict[str, dict[str, Any]] = {
    "multipart/alternative": {
        "html_alternative": "<html><body><p>plinth brillig</p></body></html>"
    },
    **{f"declared charset {name}": {"declared_charset": name} for name in UNRESOLVABLE_CHARSETS},
    "alternative with an unresolvable charset": {
        "html_alternative": "<p>plinth slithy</p>",
        "declared_charset": "ISO-8859-8-I",
    },
    "alternative whose bytes are not UTF-8": {
        "html_alternative": "<p>plinth café</p>",
        "declared_charset": "iso-8859-1",
        "body_encoding": "iso-8859-1",
    },
}


def _one_message(**shape: Any) -> SyntheticMailbox:
    return SyntheticMailbox(
        messages=(
            Msg(
                id="m-alt-0001",
                thread_id="th-alt-01",
                sender="ana@team.example",
                subject="quarterly cadence review",
                body=" ".join([TERM, *FILLER]),
                internal_date_ms=epoch_ms(2026, 8, 1),
                to=("rob@team.example",),
                **shape,
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )


@pytest.mark.parametrize("name", sorted(ORDINARY_SHAPES))
@pytest.mark.parametrize(
    ("tool", "arguments"),
    (
        ("mailweave_search", {"query": TERM}),
        ("mailweave_get_messages", {"message_ids": ["m-alt-0001"], "view": "body_clean"}),
    ),
)
def test_an_ordinary_message_shape_is_served(
    name: str, tool: str, arguments: Mapping[str, Any]
) -> None:
    """**R-MCP-023.** The commonest message format there is, through the tools that carry it.

    Before this round every one of these twelve calls answered `-32603 "this is a defect in
    this server"`: the content layer emitted a reduction declaring that the HTML alternative
    was not used for `body_clean` - `removed_chars=0`, no count, because nothing was removed
    from the part that *was* used - and the wire layer refused any zero-size reduction without
    knowing which kinds are declarations. The defect had survived twenty-six rounds because
    `tests/fixtures/mailbox.py` could not emit a `multipart/alternative` payload at all, so no
    test in the suite had ever served one.
    """
    result = call(make_service(_one_message(**ORDINARY_SHAPES[name])), tool, dict(arguments))
    assert not result.is_error, json.dumps(structured_of(result))[:400]


@pytest.mark.parametrize("name", sorted(ORDINARY_SHAPES))
def test_the_reduction_is_declared_rather_than_merely_survived(name: str) -> None:
    """The fix is not "stop refusing" - the record still has to reach the reader.

    A row that dropped the reduction instead of carrying it would pass the test above and be
    the DISC-03 defect the refused validator existed to prevent, so what the shape produces is
    asserted rather than only that it produces something.
    """
    result = call(
        make_service(_one_message(**ORDINARY_SHAPES[name])), "mailweave_search", {"query": TERM}
    )
    payload = structured_of(result)
    kinds = {
        reduction["kind"]
        for source in payload["sources"]
        for row in source["messages"]
        for reduction in row["reductions"]
    }
    expected = set()
    if "html_alternative" in ORDINARY_SHAPES[name]:
        expected.add(ReductionKind.ALTERNATIVE_PART_UNUSED.value)
    if ORDINARY_SHAPES[name].get("declared_charset") in UNRESOLVABLE_CHARSETS:
        expected.add(ReductionKind.UNKNOWN_CHARSET.value)
    assert expected <= kinds, (name, sorted(kinds))


def test_the_zero_size_rule_is_asked_for_rather_than_restated() -> None:
    """The structural half: one rule, one place, and the row asks the record.

    Round 26's review found this by reading the two validators side by side, not by running
    anything, because nothing ran the shape. The guard against it coming back is not another
    fixture - it is that the second copy no longer exists, which is what this asserts by
    driving a record of every exempt kind through `MessageRow`'s own validator.
    """
    exempt = Reduction(
        kind=ReductionKind.ALTERNATIVE_PART_UNUSED,
        removed_chars=0,
        mime="text/html",
        bytes=412,
        detail="part 1 not used for body_clean",
    )
    assert not exempt.is_a_silent_reduction
    silent = Reduction(kind=ReductionKind.QUOTED, removed_chars=0, count=3, stripper="q")
    assert not silent.is_a_silent_reduction


# =============================================================================================
# Part 2 - the estimate, on the dimension it was never varied over (R-MCP-024, R-MCP-030)
# =============================================================================================


def _message_id(thread: int, index: int, width: int) -> str:
    return f"m{thread:03d}{index:03d}" + "e" * max(0, width - 7)


def multi_thread_mailbox(
    *,
    threads: int,
    per_thread: int = 1,
    words: int = 40,
    senders: int = 1,
    recipients: int = 1,
    thread_id_chars: int = 16,
    message_id_chars: int = 16,
) -> SyntheticMailbox:
    """Several ordinary threads, in the shape Gmail sends them.

    **Every keyword is a dimension round 26's matrix held constant**, and `threads` is the one
    the estimate failed on. `thread_id_chars` and `message_id_chars` are here because a Gmail
    id is longer than a fixture's and both constants this round sets are charged off id
    length: a matrix that used only the double's own short ids would certify a bound that does
    not hold on the mailbox the demonstration runs against.
    """
    rows = []
    for thread in range(threads):
        thread_id = f"th{thread:03d}" + "f" * max(0, thread_id_chars - 5)
        for index in range(per_thread):
            message_id = _message_id(thread, index, message_id_chars)
            rows.append(
                Msg(
                    id=message_id,
                    thread_id=thread_id,
                    sender=f"a{(thread * per_thread + index) % senders}@team.example",
                    subject=(
                        "project cadence review" if index == 0 else "Re: project cadence review"
                    ),
                    body=" ".join(
                        [TERM, *(FILLER[(index + k) % len(FILLER)] for k in range(words))]
                    ),
                    internal_date_ms=epoch_ms(2026, 8, 1) + (thread * 100 + index) * 3_600_000,
                    to=tuple(f"r{k}@team.example" for k in range(recipients)),
                    # The parent's **real** id, padding included. An `In-Reply-To` naming an
                    # id no message carries is a different fixture - an unresolved reply
                    # parent, which puts declared-gap machinery on the wire - and one that
                    # arrived here by accident once, reading as a 250-character-per-row
                    # estimate error that was the fixture's and not the product's.
                    in_reply_to=(
                        f"<{_message_id(thread, index - 1, message_id_chars)}@mail.invalid>"
                        if index
                        else None
                    ),
                )
            )
    return SyntheticMailbox(messages=tuple(rows), now_ms=epoch_ms(2026, 9, 3))


class _CapturedLadder:
    """The layout the A.9a ladder finished with, so the inequality can be asserted directly.

    Round 26 held the *consequence* - "no served response crosses the cap" - because reaching
    the layout from a served response means reaching around `assemble`. Holding the
    consequence is what let R-MCP-024 ship: the surface's own backstop refuses an over-cap
    result, so an estimate that under-charges turns into a **refusal** rather than an over-cap
    response, and a test that skips errors sees a clean run. This captures the layout instead,
    so the property the constants are for is the property under test.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import mailweave.disclosure.plan as plan
        import mailweave.surface.expansion as expansion

        self.layout: Any = None

        # **Both producers, because there are two.** `assemble` reaches the ladder through
        # `plan` and `mailweave_thread_map` reaches it through `expansion`, and a spy on one
        # of them would have made half this matrix assert nothing while reporting a pass -
        # which is the shape of R-MCP-030 itself.
        for module in (plan, expansion):
            original = module.run_ladder

            def spy(layout: Any, _original: Any = original, **kwargs: Any) -> Any:
                finished, steps = _original(layout, **kwargs)
                self.layout = finished
                return finished, steps

            monkeypatch.setattr(module, "run_ladder", spy)


#: The matrix. Source count is varied first and hardest, because it is the dimension round 26
#: held at one on every shape; id lengths are varied because both constants are charged off
#: them; body length and sender count are varied because they were the dimensions round 26
#: *did* vary and a change to the constants must not break what already held.
ESTIMATE_SHAPES: tuple[tuple[str, dict[str, int]], ...] = (
    ("1 thread", {"threads": 1}),
    ("1 thread, 5 messages", {"threads": 1, "per_thread": 5}),
    ("2 threads", {"threads": 2}),
    ("3 threads", {"threads": 3}),
    ("3 threads, 3 messages", {"threads": 3, "per_thread": 3}),
    ("4 threads", {"threads": 4}),
    ("5 threads", {"threads": 5}),
    ("6 threads", {"threads": 6}),
    ("8 threads", {"threads": 8}),
    ("10 threads", {"threads": 10}),
    ("12 threads", {"threads": 12}),
    ("16 threads", {"threads": 16}),
    ("20 threads", {"threads": 20}),
    ("short ids", {"threads": 8, "thread_id_chars": 5, "message_id_chars": 7}),
    ("long ids", {"threads": 8, "thread_id_chars": 30, "message_id_chars": 30}),
    ("long thread ids only", {"threads": 10, "thread_id_chars": 40, "message_id_chars": 7}),
    ("short bodies", {"threads": 10, "words": 8}),
    ("long bodies", {"threads": 4, "words": 200}),
    ("many senders", {"threads": 6, "per_thread": 3, "senders": 18, "recipients": 6}),
)


@pytest.mark.parametrize(("name", "shape"), ESTIMATE_SHAPES, ids=[n for n, _ in ESTIMATE_SHAPES])
@pytest.mark.parametrize("tool", ("mailweave_search", "mailweave_thread_map"))
def test_the_character_estimate_is_at_or_above_the_rendered_result(
    name: str, shape: dict[str, int], tool: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**R-MCP-024, as the inequality and not as its consequence.**

    `layout_chars` is what the A.9a ladder shrinks against and `rendered_chars` is the thing
    itself, and the first has to be at or above the second: an estimate that under-charges
    either hands a host a response it will cut where nothing can declare the cut, or - once
    round 26 added the surface backstop - turns an answerable query into a refusal. Measured
    at 1,100 characters per source it was under by 12 to 1,513 on every multi-source response
    and crossed below the rendered size at **three threads**.

    A response that declines is not skipped here: it is asserted about. The ladder's own
    estimate is what a decline is decided on, so a decline whose estimate was wrong is exactly
    the failure this test exists to catch.
    """
    captured = _CapturedLadder(monkeypatch)
    box = multi_thread_mailbox(**shape)
    # The thread id is derived from the shape rather than written out: a literal would name a
    # thread only the default-width shapes have, and `mailweave_thread_map` would then refuse
    # the call before the ladder ran on exactly the shapes this matrix exists to vary.
    thread_id_chars = shape.get("thread_id_chars", 16)
    arguments: dict[str, Any] = (
        {"query": TERM}
        if tool == "mailweave_search"
        else {"thread_id": "th000" + "f" * max(0, thread_id_chars - 5)}
    )
    result = call(make_service(box), tool, arguments)
    if captured.layout is None:
        # The ladder raised rather than returned, which is A.9a exhausting its steps. There is
        # no finished layout to price and no rendered form to price it against; what is
        # checked is that the call really did decline, so a shape that silently stopped
        # exercising the ladder cannot read as a pass.
        assert result.is_error, (name, tool, "no layout and no decline")
        return
    estimate = captured.layout.chars()
    if result.is_error:
        # A decline is decided on the estimate, so the estimate still has to be honest about
        # the response it refused to send.
        assert estimate > HOST_RESULT_CHAR_CAP, (name, tool, estimate)
        return
    mirrored = rendered_of(result)
    rendered = rendered_chars(mirrored.structured, mirrored.text)
    assert rendered <= HOST_RESULT_CHAR_CAP, (name, tool, rendered)
    assert estimate >= rendered, (name, tool, estimate, rendered, estimate - rendered)


#: The shapes a search cannot answer with mail today. **Empty since round 29.**
#:
#: It held three entries, each marked `xfail(strict=True, reason="R-MCP-033: bookkeeping
#: crowds out the mail")`, and every one of them came off by *passing* rather than by being
#: edited out: `many senders` when withholdings began to be written at the granularity of the
#: call that recovers them, `16 threads` and `20 threads` when the reason shared by every
#: `not_included_sources[]` entry stopped being repeated once per entry. A strict xfail that
#: starts passing fails the suite, which is why this list could not quietly outlive the
#: defect - and did not.
#:
#: Kept as an empty set rather than deleted, with the parametrisation that reads it, so the
#: next shape that cannot be answered with mail is recorded here and named rather than
#: skipped.
WITHOUT_MAIL_TODAY: frozenset[str] = frozenset()


@pytest.mark.parametrize(
    ("name", "shape"),
    [
        pytest.param(
            name,
            shape,
            marks=(
                pytest.mark.xfail(strict=True, reason="R-MCP-033: bookkeeping crowds out the mail")
                if name in WITHOUT_MAIL_TODAY
                else ()
            ),
        )
        for name, shape in ESTIMATE_SHAPES
    ],
    ids=[n for n, _ in ESTIMATE_SHAPES],
)
def test_a_search_that_is_served_carries_mail(name: str, shape: dict[str, int]) -> None:
    """The half of R-MCP-024 that `if result.is_error: continue` hid.

    A response can be inside every cap and carry nothing, and round 26's certifying test would
    have called that a pass. What a served search owes its caller is at least one message it
    can read - so this asserts on the payload, and the shapes it does not hold for are named
    in the round report rather than skipped here.
    """
    result = call(make_service(multi_thread_mailbox(**shape)), "mailweave_search", {"query": TERM})
    assert not result.is_error, (name, json.dumps(structured_of(result))[:400])
    payload = structured_of(result)
    rows = sum(len(source["messages"]) for source in payload["sources"])
    assert rows >= 1, (name, json.dumps(payload)[:400])


def test_the_charged_thread_id_width_covers_every_withheld_record_actually_emitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`widest_thread_id`'s claim, checked against the records the response really carried.

    This is the property the charge rests on, and the first form of it was wrong: the widest
    id the *layout* could see is not a bound, because a thread `max_hit_threads` capped away
    never becomes a source and is never split off, and its messages are withheld records all
    the same. The layout is now told the width by the producer, off the same ledger field the
    records are built from - so the check is that the number charged covers every id emitted,
    over shapes that reach both the cap and A.9a step 7.
    """
    for shape in ({"threads": 16}, {"threads": 20}, {"threads": 10}, {"threads": 8}):
        captured = _CapturedLadder(monkeypatch)
        result = call(
            make_service(multi_thread_mailbox(**shape)), "mailweave_search", {"query": TERM}
        )
        if result.is_error:
            continue
        payload = structured_of(result)
        emitted = [len(record["thread_id"]) for record in payload["withheld"]]
        if not emitted:
            continue
        assert widest_thread_id(captured.layout) >= max(emitted), (shape, emitted)


# =============================================================================================
# Part 3 - the way out that the server refused (R-MCP-025)
# =============================================================================================

PARSER_BY_TOOL = {
    "mailweave_search": parse_search,
    "mailweave_get_messages": parse_get_messages,
    # Round 29: a declined search's chain changes tool to a thread map at its narrowest.
    "mailweave_thread_map": parse_thread_map,
}


def _budget_caps_this_server_can_mint() -> set[str]:
    """Every budget key an affordance this server builds can carry, read from the builders.

    Two builders mint one: `policy.budget._raise_to`, over the caps `WITHHELD_CAP_OF` maps -
    which is where a breached cap's raise affordance comes from - and
    `surface.recovery.narrower_call`, which is the one a decline hands back. Read from them
    rather than listed, because a list is the third copy of a thing that already disagreed
    with itself twice.
    """
    minted = {cap.value for cap in WITHHELD_CAP_OF}
    step = narrower_call("mailweave_search", {"query": TERM}, top_thread=None)
    assert step is not None
    narrower = step.affordance
    budget = narrower.args.get("budget")
    assert isinstance(budget, dict), narrower
    minted |= set(budget)
    return minted


def test_every_budget_cap_this_server_can_mint_is_a_key_it_accepts() -> None:
    """**R-MCP-025.** An affordance that cannot execute is contract I-2's violation (c).

    `max_hit_threads` was a published `BudgetCapName`, a field of `AppliedBudget` and the cap
    `narrower_call` narrowed a search by - and was not a key `parse_search` accepted, so the
    single call a declined search offered as the way out came back `-32602 unknown budget
    key`. The parser already carried the rule this test states, in a comment beside `max_ms`:
    naming one spelling of a cap and not the other "would have made an affordance this server
    minted invalid at the tool that minted it".
    """
    accepted = set(BUDGET_KEYS)
    assert _budget_caps_this_server_can_mint() <= accepted, sorted(
        _budget_caps_this_server_can_mint() - accepted
    )


@pytest.mark.parametrize("cap", sorted(_budget_caps_this_server_can_mint()))
def test_each_minted_budget_cap_parses_as_the_call_that_carries_it(cap: str) -> None:
    """The same property, executed rather than compared: the parser is asked.

    Membership of `BUDGET_KEYS` is one gate; `_Reader` is another, and a key on the list that
    the reader then refused for its type or its bound would fail in the same place with the
    same error. So the minted shape is run through the real parser.
    """
    request = parse_search({"query": TERM, "budget": {cap: 1}})
    assert request.query == TERM


def test_the_retry_a_declined_search_hands_back_executes_and_returns_mail() -> None:
    """The affordance, taken from a real decline and **called** - now along the whole chain.

    No test in the suite executed a minted `retry_with` before round 27, which is why a
    published affordance and a published argument list could disagree for a whole round while
    every test passed. Round 29 changed the fixture and the claim together: twenty one-message
    threads no longer decline at all (R-MCP-033 is what made them decline), so the shape that
    declines now is a single thread too large for any arrangement of it, and the assertion is
    the recovery contract's - following `retry_with` from that decline ends, within
    `MAX_RECOVERY_STEPS`, in a served response or a final refusal, never in a repeat.

    `tests/test_recovery_chain_round29.py` holds the contract in full; this keeps round 27's
    claim in round 27's file, executed against the shape that now exercises it.
    """
    from mailweave.surface.recovery import MAX_RECOVERY_STEPS

    # Since 2026-09-15 (R-M2-093) a thread the ladder can carry as a collapsed run is served
    # with its hits as run members, so "too large for any arrangement" means too large even
    # as a run: nine hundred messages, whose inventory alone is over the cap.
    box = multi_thread_mailbox(threads=1, per_thread=900, words=5)
    service = make_service(box)
    name, args = "mailweave_search", {"query": TERM}
    seen: list[tuple[str, dict[str, Any]]] = [(name, dict(args))]
    result = call(service, name, args)
    assert result.is_error, "this fixture must actually decline, or this asserts nothing"
    hops = 0
    while result.is_error:
        payload = structured_of(result)
        retry = payload["retry_with"]
        if retry is None:
            assert payload["terminal"] is True, payload
            break
        hops += 1
        assert hops <= MAX_RECOVERY_STEPS, seen
        assert retry["tool"] in PARSER_BY_TOOL, retry
        name, args = retry["tool"], dict(retry["args"])
        assert (name, args) not in seen, ("the chain repeated a call", seen)
        seen.append((name, args))
        result = call(make_service(box), name, args)
    assert hops >= 1, "the decline offered no retry at all on a shape with a thread to map"


def test_the_narrowed_search_is_a_narrowing_and_not_a_different_question() -> None:
    """`max_hit_threads` lowers and does not raise, and the threads it drops are not dropped.

    The cap is the caller's, so it can only reduce what this server maps - a caller asking for
    more than the published figure gets the published figure. And every thread it stops from
    being mapped becomes a `withheld` record naming this cap with the call that reaches it,
    which is what makes the narrowing recoverable rather than lossy (contract I-1, I-4).
    """
    box = multi_thread_mailbox(threads=20)
    payload = structured_of(
        call(
            make_service(box),
            "mailweave_search",
            {"query": TERM, "budget": {"max_hit_threads": 2}},
        )
    )
    assert len(payload["sources"]) <= 2, payload["sources"]
    # Round 29: a thread the width cap left unmapped is accounted for as a **group** - one
    # entry per thread with its count and its map call - whatever its size (R-V01-007).
    capped = [g for g in payload["withheld_groups"] if g["cap"] == "max_hit_threads"]
    assert capped, payload["withheld_groups"]
    for group in capped:
        assert group["affordance"]["tool"] == "mailweave_thread_map"
        assert group["message_count"] >= 1
    assert not [r for r in payload["withheld"] if r["cap"] == "max_hit_threads"]

    # Asking for more than the published figure is honoured downward, not upward.
    wide = parse_search({"query": TERM, "budget": {"max_hit_threads": 10_000}})
    from mailweave.constants import MAX_HIT_THREADS
    from mailweave.policy.budget import apply_floor

    assert apply_floor(wide.budget).max_hit_threads == MAX_HIT_THREADS


@pytest.mark.parametrize(
    ("threads", "tool", "arguments"),
    (
        (3, "mailweave_search", {"query": TERM}),
        (10, "mailweave_search", {"query": TERM}),
        (1, "mailweave_thread_map", {"thread_id": "th000" + "f" * 11}),
    ),
)
def test_every_affordance_a_served_response_carries_parses_at_the_tool_it_names(
    threads: int, tool: str, arguments: Mapping[str, Any]
) -> None:
    """The general form: nothing a response hands a reader is a call this server refuses.

    R-MCP-025 was one instance. What made it survive a round is that the response's
    `affordances[]` block, the `withheld` records' affordances and the `not_included_sources`
    entries' affordances were all built and none of them were ever run back through the
    parser they name. `mailweave_thread_map`'s own arguments are not parsed here - the two
    tools with a parser in `PARSER_BY_TOOL` are - and that gap is the round report's, not a
    silent one.
    """
    result = call(make_service(multi_thread_mailbox(threads=threads)), tool, dict(arguments))
    if result.is_error:
        pytest.skip("this shape declines; the decline's own retry is executed above")
    payload = structured_of(result)
    affordances = [
        *payload["affordances"],
        *(record["affordance"] for record in payload["withheld"]),
        *(entry["affordance"] for entry in not_included_entries(payload)),
        *(group["affordance"] for group in payload.get("withheld_groups") or ()),
        *(
            row["unabridged"]
            for source in payload["sources"]
            for row in source["messages"]
            if row.get("unabridged")
        ),
    ]
    assert affordances, "this shape carries no affordance; it asserts nothing"
    for affordance in affordances:
        parser = PARSER_BY_TOOL.get(affordance["tool"])
        if parser is None:
            continue
        parser(dict(affordance["args"]))


# =============================================================================================
# Part 4 - the source A.9a step 8 emptied and left standing (R-MCP-032)
# =============================================================================================


@pytest.mark.parametrize("threads", (8, 10, 12, 16, 20, 26))
def test_no_response_carries_a_source_that_includes_none_of_its_messages(threads: int) -> None:
    """**R-MCP-032**, found by fixing R-MCP-024 and reachable without it.

    A.9a step 8 withholds rows one at a time and never asked what a source had left, so it
    could take a thread's last row and emit the source anyway - `included: 0 of 1`, with no
    affordance naming the thread, which contract R-07 refuses at the envelope. That refusal
    reaches a caller as `-32603 "this is a defect in this server"`: the same shape as
    R-MCP-023, one layer further on. It became reachable on ordinary wide searches the moment
    the character estimate was corrected, because a truthful estimate degrades further than an
    optimistic one - which is the general hazard in fixing an under-estimate and the reason
    this is tested across the whole width of the matrix rather than at the one shape that
    first showed it.
    """
    result = call(
        make_service(multi_thread_mailbox(threads=threads)), "mailweave_search", {"query": TERM}
    )
    if result.is_error:
        payload = structured_of(result)
        assert payload.get("declined") is True, payload
        return
    payload = structured_of(result)
    for source in payload["sources"]:
        assert source["messages"] or source["collapsed_runs"], source


def test_an_emptied_source_leaves_as_a_split_rather_than_vanishing() -> None:
    """Retiring it is a disposition, not a deletion: the thread is still named and reachable.

    The distinction matters because "the source is gone" and "the source left and said so" are
    the two halves of I-1 and I-4, and a fix that simply dropped the emptied source would pass
    the test above while losing the thread. So this asserts the other side: whatever thread
    the response stopped carrying as a source is named in `not_included_sources[]` with a map
    affordance, and every one of its messages is a `withheld` record.
    """
    box = multi_thread_mailbox(threads=12)
    result = call(make_service(box), "mailweave_search", {"query": TERM})
    if result.is_error:
        pytest.skip("this shape declines; the property is exercised by the served widths")
    payload = structured_of(result)
    named = {source["thread_id"] for source in payload["sources"]}
    named |= {entry["thread_id"] for entry in not_included_entries(payload)}
    omitted_threads = withheld_threads(payload)
    # Every thread a withheld record or group is about is either still a source, or named as
    # one this response did not include - never simply absent.
    capped = {
        record["thread_id"] for record in payload["withheld"] if record["cap"] == "max_hit_threads"
    } | {
        group["thread_id"]
        for group in payload.get("withheld_groups") or ()
        if group["cap"] == "max_hit_threads"
    }
    assert omitted_threads <= named | capped, sorted(omitted_threads - named)
    for entry in not_included_entries(payload):
        assert entry["affordance"]["tool"] == "mailweave_thread_map", entry
