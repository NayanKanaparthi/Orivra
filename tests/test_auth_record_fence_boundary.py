"""An `Authentication-Results` record up to the bound is served, through every tool that carries it.

**The defect (Harbor run, 2026-09-23).** `orivra_ask` and two `mailweave_get_messages` calls
succeeded. Expanding the answer's thread node, and mapping that thread directly, both failed
with MailWeave's own response model refusing the response MailWeave built. Gmail had returned
the thread. The refusal came from `SenderAuthentication`.

**The cause.** The producer (`retrieval/assemble.py::_authentication_of`) compared the raw
header with `MAX_AUTH_RECORD_CHARS`, then fenced it. The model compared the *fenced* text with
the same 512. The fence adds 46 characters, so a record of 467 to 512 characters was disclosed
by the producer, charged by the estimate, and refused by the model. Offline, through
`mailweave_thread_map`:

- raw 466 was served;
- raw 467 and raw 512 were internal errors;
- raw 513 was served, as the existing oversize declaration.

**The repair.** One comparison, `constants.auth_record_fits`, applied to the header as
written. The producer, the model and the charge all use it. The model reads the record out of
its fence (`envelope.fence.fenced_text`) before measuring it, and refuses a record that is not
fenced at all. The bound, the fence, the oversize declaration and the response caps are all
unchanged.

These tests drive the shipped boundary: `mailweave.surface.server.call` and
`orivra.surface.server.call`. An internal error there raises, so a test run without the repair
fails at 467 and 512 on every path below.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mailweave.constants import HOST_RESULT_CHAR_CAP, MAX_AUTH_RECORD_CHARS
from mailweave.envelope.fence import fence, fenced_text, mint_nonce, unfence
from mailweave.envelope.measure import (
    AUTH_RECORD_CHARS,
    AUTH_RECORD_TOKENS,
    ROW_IDENTITY_CHARS,
    ROW_IDENTITY_TOKENS,
    rendered_chars,
)
from mailweave.envelope.vocab import ContentSource, Trust
from mailweave.envelope.wire import Content, SenderAuthentication
from mailweave.surface.server import call
from orivra.cache import BoundedCache
from orivra.contracts import ConnectorId
from orivra.gmail_adapter import GmailAdapter
from orivra.registry import ConnectorRegistry
from orivra.surface.server import call as orivra_call
from orivra.surface.service import OrivraService
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.test_mcp_surface_round24 import mailbox, make_service, structured_of

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SUBJECT = "Harbor export mismatch"

#: The fence `fence` puts around every piece of mail-derived text. Measured rather than
#: assumed, so a change to the markers moves the boundary cases with it.
FENCE_CHARS = len(fence(mint_nonce(), ""))

#: The four cases the diagnosis measured, derived from the constants rather than written out:
#:
#: - the last record the old check served;
#: - the first it refused;
#: - the bound itself;
#: - the first past the bound, which is declared oversize now as before.
BOUNDARY = (
    MAX_AUTH_RECORD_CHARS - FENCE_CHARS,
    MAX_AUTH_RECORD_CHARS - FENCE_CHARS + 1,
    MAX_AUTH_RECORD_CHARS,
    MAX_AUTH_RECORD_CHARS + 1,
)


def _record(length: int) -> str:
    """A plausible `Authentication-Results` value of exactly `length` characters."""
    unit = (
        "mx.google.com; dkim=pass header.i=@team.example header.s=s1; "
        "spf=pass smtp.mailfrom=team.example; dmarc=pass header.from=team.example; "
    )
    text = (unit * (length // len(unit) + 1))[: length - 1] + "e"
    assert len(text) == length
    return text


def _served(result: Any) -> dict[str, Any]:
    assert not result.is_error, json.dumps(structured_of(result))[:600]
    payload = structured_of(result)
    text = "".join(getattr(block, "text", "") for block in result.content)
    assert rendered_chars(payload, text) <= HOST_RESULT_CHAR_CAP
    return payload


def _row(payload: dict[str, Any], message_id: str) -> dict[str, Any]:
    return next(
        row
        for source in payload["sources"]
        for row in source["messages"]
        if row["id"] == message_id
    )


def _assert_carried_as_the_bound_says(
    payload: dict[str, Any], message_id: str, record: str
) -> None:
    """Disclosed verbatim, inside this response's fence, when it fits. Declared when not."""
    authentication = _row(payload, message_id)["authentication"]
    if len(record) <= MAX_AUTH_RECORD_CHARS:
        assert authentication["oversize"] is False
        carried = authentication["recorded"]
        assert carried["trust"] == Trust.UNTRUSTED_THIRD_PARTY.value
        assert carried["source"] == ContentSource.GMAIL_HEADER.value
        assert unfence(payload["fence_nonce"], carried["text"]) == record, "not verbatim"
        assert carried["text"] == fence(payload["fence_nonce"], record), "not fenced"
    else:
        assert authentication == {"recorded": None, "oversize": True}
        assert record[:80] not in json.dumps(payload), "an oversize record leaked"


# -- the model: the bound is on the record, the fence is the fence ------------------------------


def test_the_model_measures_the_record_inside_its_fence() -> None:
    nonce = mint_nonce()
    at_bound = fence(nonce, "r" * MAX_AUTH_RECORD_CHARS)
    assert len(at_bound) == MAX_AUTH_RECORD_CHARS + FENCE_CHARS
    carried = SenderAuthentication(
        recorded=Content(
            trust=Trust.UNTRUSTED_THIRD_PARTY, source=ContentSource.GMAIL_HEADER, text=at_bound
        )
    )
    assert carried.recorded is not None
    assert fenced_text(carried.recorded.text) == "r" * MAX_AUTH_RECORD_CHARS

    over = fence(nonce, "r" * (MAX_AUTH_RECORD_CHARS + 1))
    with pytest.raises(ValueError, match=f"of {MAX_AUTH_RECORD_CHARS + 1} characters exceeds"):
        SenderAuthentication(
            recorded=Content(
                trust=Trust.UNTRUSTED_THIRD_PARTY, source=ContentSource.GMAIL_HEADER, text=over
            )
        )


def test_an_unfenced_record_is_refused_rather_than_measured() -> None:
    """Measuring inside the fence must not become a way to carry a record without one."""
    with pytest.raises(ValueError, match="travels fenced"):
        SenderAuthentication(
            recorded=Content(
                trust=Trust.UNTRUSTED_THIRD_PARTY,
                source=ContentSource.GMAIL_HEADER,
                text="mx.example; spf=pass",
            )
        )


def test_fenced_text_reads_back_exactly_what_fence_wrapped() -> None:
    nonce = mint_nonce()
    for text in ("", "one line", "folded\r\n\tline", "<<<not a fence>>>", " spaced "):
        assert fenced_text(fence(nonce, text)) == text
    assert fenced_text("mx.example; spf=pass") is None
    other = mint_nonce()
    assert fenced_text(f"<<<{nonce} x {other}>>>") is None, "the two markers must match"


# -- MailWeave: the map, the read, the search ----------------------------------------------------

THREAD = "t-auth-bound"
TARGET = "m-auth-bound-1"


def _box(record: str) -> SyntheticMailbox:
    return SyntheticMailbox(
        messages=tuple(
            Msg(
                id=f"m-auth-bound-{index}",
                thread_id=THREAD,
                sender="Ana Ito <ana@team.example>",
                subject=SUBJECT,
                body=f"The {SUBJECT} note, part {index}.",
                internal_date_ms=epoch_ms(2026, 3, 1 + index),
                to=("bo@team.example",),
                authentication_results=record if f"m-auth-bound-{index}" == TARGET else None,
            )
            for index in range(3)
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )


@pytest.mark.parametrize("length", BOUNDARY)
def test_mapping_the_thread_directly_serves_the_record(length: int) -> None:
    """The Harbor run's direct lookup: `mailweave_thread_map` by thread id."""
    record = _record(length)
    payload = _served(
        call(make_service(_box(record)), "mailweave_thread_map", {"thread_id": THREAD})
    )
    _assert_carried_as_the_bound_says(payload, TARGET, record)


@pytest.mark.parametrize("length", BOUNDARY)
def test_reading_the_message_serves_the_record(length: int) -> None:
    record = _record(length)
    payload = _served(
        call(
            make_service(_box(record)),
            "mailweave_get_messages",
            {"message_ids": [TARGET], "view": "body_clean"},
        )
    )
    _assert_carried_as_the_bound_says(payload, TARGET, record)


@pytest.mark.parametrize("length", BOUNDARY)
def test_a_search_that_finds_the_message_serves_the_record(length: int) -> None:
    record = _record(length)
    payload = _served(call(make_service(_box(record)), "mailweave_search", {"query": SUBJECT}))
    _assert_carried_as_the_bound_says(payload, TARGET, record)


@pytest.mark.parametrize("length", BOUNDARY[:3])
def test_the_charge_bounds_a_disclosed_record_at_the_boundary(length: int) -> None:
    """The estimate charges the raw record plus its fence and object, and that is enough.

    Before the repair no record between 467 and 512 characters ever reached the wire, so the
    charge was never checked against one. The oracle is the rendered block, as in
    `test_injection_ws14.test_the_estimate_bounds_the_identity_block_it_added`.
    """
    record = _record(length)
    payload = _served(
        call(make_service(_box(record)), "mailweave_thread_map", {"thread_id": THREAD})
    )
    row = _row(payload, TARGET)
    block = json.dumps(
        {key: row[key] for key in ("headers_observed", "reply_to_differs", "authentication")}
    )
    assert len(block) <= ROW_IDENTITY_CHARS + AUTH_RECORD_CHARS + len(json.dumps(record))
    assert len(block[1:-1].split()) <= ROW_IDENTITY_TOKENS + AUTH_RECORD_TOKENS + len(
        record.split()
    )


# -- Orivra: the expansion the Harbor run made ---------------------------------------------------

LONG_THREAD = "t-auth-long"
#: A position the answer's disclosure sheds under its token ceiling and the thread map serves.
#: Held by the precondition in the test, not assumed: if the answer ever carries it, the test
#: says so rather than passing on the wrong path.
SHED_POSITION = 5


def _long_thread(record: str) -> tuple[Msg, ...]:
    return tuple(
        Msg(
            id=f"1a0{index:02x}a0f{index:04x}",
            thread_id=LONG_THREAD,
            sender=f"p{index % 4}@team.example",
            subject=SUBJECT,
            body=f"The {SUBJECT} is discussed at length here. " * 12,
            internal_date_ms=epoch_ms(2026, 3, 1 + index),
            to=("ana@team.example",),
            in_reply_to=(f"<1a0{index - 1:02x}a0f{index - 1:04x}@mail.invalid>" if index else None),
            authentication_results=record if index == SHED_POSITION else None,
        )
        for index in range(16)
    )


@pytest.mark.parametrize("length", BOUNDARY)
def test_expanding_the_answers_thread_node_maps_the_thread_and_serves(length: int) -> None:
    """The Harbor run's expansion: `orivra_expand` with the graph's own thread handle.

    The answer succeeds because the record's message is shed from its disclosure. The
    expansion then maps the whole thread, which builds that row. Before the repair, that is
    where the model refused.
    """
    record = _record(length)
    base = mailbox()
    service = make_service(
        SyntheticMailbox(messages=(*base.messages, *_long_thread(record)), now_ms=base.now_ms)
    )
    adapter = GmailAdapter(
        service=service, granted_scopes=(SCOPE,), cache=BoundedCache(now=service.now)
    )
    orivra = OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}), max_graph_nodes=4
    )
    answer = orivra_call(orivra, "orivra_ask", {"query": SUBJECT, "view": "snippet", "graph": True})
    assert not answer.is_error, answer.content
    asked = dict(answer.structured_content or {})
    assert record[:80] not in json.dumps(asked), (
        "precondition: the answer carried the record, so this would not test the expansion"
    )

    handle = f"gmail/thread/{LONG_THREAD}"
    expanded = orivra_call(
        orivra, "orivra_expand", {"query_id": asked["query_id"], "handle": handle}
    )
    assert not expanded.is_error, expanded.content
    delta = dict(expanded.structured_content or {})
    assert delta["executed"] == {
        "tool": "mailweave_thread_map",
        "args": {"thread_id": LONG_THREAD},
        "reduces": "breadth",
    }
    # The row was built: its message is a node of the graph now. The delta is carried when it
    # fits and shed, with a statement saying so, when it does not - at 513 the oversize row
    # is cheaper, the page is wider and the delta is shed - so the graph is asked directly.
    assert delta["added"]["shed"] in (True, False)
    shed_id = _long_thread(record)[SHED_POSITION].id
    assert f"gmail/message/{shed_id}" in _graph_nodes(orivra, asked["query_id"])
    # The graph carries no message text, and the record is message-derived text.
    assert record[:80] not in json.dumps(delta)


def _graph_nodes(orivra: OrivraService, query_id: str) -> set[str]:
    nodes: set[str] = set()
    cursor, view = 0, None
    for _ in range(20):
        args: dict[str, Any] = {"query_id": query_id, "select": "nodes"}
        if cursor:
            args |= {"cursor": cursor, "view": view}
        page = orivra_call(orivra, "orivra_graph", args)
        assert not page.is_error, page.content
        listed = dict(page.structured_content or {})
        nodes |= {item["node_id"] for item in listed["items"]}
        if listed["next_cursor"] is None:
            return nodes
        cursor, view = listed["next_cursor"], listed["view"]
    raise AssertionError("the graph did not finish paging in 20 pages")
