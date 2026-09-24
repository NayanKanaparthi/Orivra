"""R-MCP-039, certified: a `body_full` read at the cap's edge never reaches the caller as -32603.

**The defect.** A `mailweave_get_messages` read at `view: body_full` of a message too large to
carry unabridged: the A.9a ladder withheld the only named row, `expand` built a zero-evidence
envelope, the response model refused it, and the caller got `-32603 Internal server error` -
a defect report about the server, for a request that was fine. Reachable on real mail, filed in
round 28, reproduced here: at `5e86229` the first call below raises `MCPError(-32603)`.

**The fix, in two parts that were built for other reasons and meet here.** The ladder's
emptiness gate (`_carries_nothing`, round 29) turns "every named row withheld" into a declared
`budget_exhausted` decline instead of an empty envelope. The recovery chain then makes that
decline *executable*: `view` is a narrowing dimension, `body_full` → `body_clean`, and the
cleaned body of the same message is served. What v0.1 promises for this shape is therefore
exactly the owner's sentence: the requested evidence, or a truthful, machine-readable,
executable decline - never `-32603`.

The replant `R-MCP-039-the-emptiness-gate-is-removed` in `tests/fixtures/replants.py` removes
the gate and is caught by `test_a_body_full_read_at_the_edge_never_raises_internal_error`.
"""

from __future__ import annotations

import json

import pytest

from mailweave.constants import HOST_RESULT_CHAR_CAP
from mailweave.envelope.measure import rendered_chars
from mailweave.surface.partition import rendered_of
from mailweave.surface.recovery import MAX_RECOVERY_STEPS
from mailweave.surface.server import call
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.test_mcp_surface_round24 import make_service, structured_of

MESSAGE = "m1" + "f" * 14
THREAD = "t1" + "f" * 14


def one_large_message(words: int) -> SyntheticMailbox:
    body = " ".join(f"word{i}" for i in range(words))
    return SyntheticMailbox(
        messages=(
            Msg(
                id=MESSAGE,
                thread_id=THREAD,
                sender="a@example.test",
                subject="a large message",
                body=body,
                internal_date_ms=epoch_ms(2026, 8, 1),
                to=("b@example.test",),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )


#: Bodies from "would fit once but not twice" (the mirror renders a body_full body in both
#: halves) up to far beyond the cap. Every one used to be -32603.
SIZES = (2_000, 3_500, 8_000)


@pytest.mark.parametrize("words", SIZES)
def test_a_body_full_read_at_the_edge_never_raises_internal_error(words: int) -> None:
    """Fails at `5e86229` with `MCPError(-32603)`. Here: a declared decline, never a raise."""
    result = call(
        make_service(one_large_message(words)),
        "mailweave_get_messages",
        {"message_ids": [MESSAGE], "view": "body_full"},
    )
    assert result.is_error, "a body that does not fit unabridged must decline, not be cut"
    payload = structured_of(result)
    assert payload["code"] == "budget_exhausted"
    assert payload["declined"] is True
    # Machine-readable and executable: the narrowing is declared and the retry is a real call.
    assert payload["narrowing"] == {
        "dimension": "view",
        "applied": "body_full",
        "proposed": "body_clean",
        "kind": "narrower",
    }
    assert payload["retry_with"] == {
        "tool": "mailweave_get_messages",
        "args": {"message_ids": [MESSAGE], "view": "body_clean"},
    }
    assert payload["terminal"] is False


@pytest.mark.parametrize("words", SIZES)
def test_following_the_decline_serves_the_cleaned_body_within_the_cap(words: int) -> None:
    """The chain: body_full declines, body_clean serves, inside the host cap, in one hop."""
    box = one_large_message(words)
    name, args = "mailweave_get_messages", {"message_ids": [MESSAGE], "view": "body_full"}
    hops = 0
    result = call(make_service(box), name, args)
    while result.is_error:
        retry = structured_of(result)["retry_with"]
        assert retry is not None, structured_of(result)["remediation"]
        hops += 1
        assert hops <= MAX_RECOVERY_STEPS
        name, args = retry["tool"], dict(retry["args"])
        result = call(make_service(box), name, args)
    assert hops == 1
    payload = structured_of(result)
    rows = [row for source in payload["sources"] for row in source["messages"]]
    assert [row["id"] for row in rows] == [MESSAGE]
    assert rows[0]["depth"] == "body_clean"
    mirrored = rendered_of(result)
    assert rendered_chars(mirrored.structured, mirrored.text) <= HOST_RESULT_CHAR_CAP


def test_a_body_clean_read_that_cannot_fit_is_a_final_refusal_not_a_loop() -> None:
    """The end of the `view` dimension is declared as final: no snippet offered as a body."""
    from mailweave.surface.recovery import narrower_call

    step = narrower_call(
        "mailweave_get_messages", {"message_ids": [MESSAGE], "view": "body_clean"}, top_thread=None
    )
    assert step is None


def test_the_declined_call_is_reported_in_band_with_no_exception_reaching_the_transport() -> None:
    """The precise thing the finding was about: the failure is a *result*, not a raise."""
    box = one_large_message(3_500)
    try:
        result = call(
            make_service(box),
            "mailweave_get_messages",
            {"message_ids": [MESSAGE], "view": "body_full"},
        )
    except Exception as escaped:  # pragma: no cover - the assertion is that this never runs
        pytest.fail(f"an exception escaped the tool handler: {type(escaped).__name__}: {escaped}")
    assert result.is_error
    assert "Internal server error" not in json.dumps(structured_of(result))


@pytest.mark.parametrize("words", SIZES)
def test_a_read_by_map_id_and_positions_gets_the_same_view_hop(words: int) -> None:
    """R-V01-010 (recheck): the `map_id` + `positions` form of the same read was declared
    final at `body_full` with no `view` hop offered. The same chain, through the served map."""
    box = one_large_message(words)
    service = make_service(box)
    mapped = structured_of(call(service, "mailweave_thread_map", {"thread_id": THREAD}))
    map_id = mapped["sources"][0]["map_id"]
    name, args = "mailweave_get_messages", {"map_id": map_id, "positions": [0], "view": "body_full"}
    hops = 0
    result = call(service, name, args)
    assert result.is_error, "the fixture is sized to decline at body_full"
    while result.is_error:
        payload = structured_of(result)
        assert payload["terminal"] is False, payload["remediation"]
        retry = payload["retry_with"]
        assert retry is not None
        hops += 1
        assert hops <= MAX_RECOVERY_STEPS
        name, args = retry["tool"], dict(retry["args"])
        result = call(service, name, args)
    assert hops == 1 and args == {"map_id": map_id, "positions": [0], "view": "body_clean"}
    rows = [row for source in structured_of(result)["sources"] for row in source["messages"]]
    assert [row["id"] for row in rows] == [MESSAGE] and rows[0]["depth"] == "body_clean"
