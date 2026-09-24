"""A real MCP client that reads **only text content**, completing the whole walk.

**The run this exists for.** On 2026-09-18 a Claude Desktop session reached a cited answer
about a Harbor export mismatch and never used the graph. Nothing errored. `orivra_graph` and
`orivra_expand` returned `text=""`, that client consumes text content, and so the two tools
that make this a graph product returned, to it, nothing at all: no query id to carry forward,
no page, no continuation, no next call. It fell back to searching and reading mail, which the
legacy tools did before any of this existed.

Every offline test passed throughout, because every one of them read `structured_content`.

So this consumer cannot. `_text` is the only accessor it has, and the calls it makes are
**parsed out of the text it was given** rather than constructed here: it takes a line like
`  orivra_graph {"query_id":"q-…","select":"edges"}` and sends exactly that JSON. If the text
projection stops naming a call, or names one with the wrong arguments, the walk stops here
rather than in front of somebody.

It runs over `mcp`'s own client, framing and dispatcher against the shipped `build_server`
loop - the same arrangement `test_mcp_surface_round24` uses for the legacy surface - so what
is exercised is the protocol, not a shim this repository wrote.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any

import anyio
import pytest
from mcp import Client
from mcp.shared.memory import create_client_server_memory_streams

from mailweave.constants import HOST_RESULT_CHAR_CAP
from mailweave.envelope.measure import rendered_chars
from orivra.contracts import ConnectorId
from orivra.gmail_adapter import GmailAdapter
from orivra.registry import ConnectorRegistry
from orivra.surface.projection import DIVIDER
from orivra.surface.server import build_server
from orivra.surface.service import OrivraService
from tests.test_mcp_surface_round24 import (
    Msg,
    SyntheticMailbox,
    epoch_ms,
    mailbox,
    make_service,
)

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
QUESTION = "Larch pricing draft"
TARGET_REVISION = "2026-07-28"

#: Tight enough that the answer leaves a recoverable branch, so the walk has somewhere to go.
BUDGET = 5

#: The one ask every test starts from, so a change to it changes every walk at once.
ASK = {"query": QUESTION, "view": "body_clean"}


class _Transport:
    def __init__(self, service: OrivraService) -> None:
        self._server = build_server(service)
        self._cm: Any = None

    @asynccontextmanager
    async def _connect(self) -> Any:
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            server_read, server_write = server_streams

            async def run() -> None:
                await self._server.run(
                    server_read,
                    server_write,
                    self._server.create_initialization_options(),
                    raise_exceptions=True,
                )

            async with anyio.create_task_group() as group:
                group.start_soon(run)
                try:
                    yield client_streams
                finally:
                    await client_streams[1].aclose()
                    await server_write.aclose()
                    group.cancel_scope.cancel()

    async def __aenter__(self) -> Any:
        self._cm = self._connect()
        return await self._cm.__aenter__()

    async def __aexit__(self, *exc: Any) -> None:
        assert self._cm is not None
        await self._cm.__aexit__(*exc)
        self._cm = None


def drive(service: OrivraService, script: Callable[[Client], Any]) -> Any:
    async def main() -> Any:
        async with Client(
            _Transport(service), mode=TARGET_REVISION, raise_exceptions=True
        ) as client:
            return await script(client)

    return anyio.run(main)


def _service(max_nodes: int = BUDGET) -> OrivraService:
    adapter = GmailAdapter(service=make_service(mailbox()), granted_scopes=(SCOPE,))
    return OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}),
        max_graph_nodes=max_nodes,
    )


# -- the consumer: text in, calls out, structured_content never touched -------------------------


def _text(result: Any) -> str:
    """Every text block of a result, joined. **The only accessor this consumer has.**"""
    assert not result.is_error, result.content
    blocks = [block.text for block in result.content if getattr(block, "type", None) == "text"]
    assert blocks, "the result carried no text content at all"
    return "\n".join(blocks)


def _calls(text: str, tool: str) -> list[dict[str, Any]]:
    """Every executable call the text offers for `tool`, as its own arguments.

    Parsed, never constructed: the arguments are the JSON the server printed. A test that
    built the next call itself would pass on a text projection that named nothing.
    """
    found: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        prefix = f"{tool} {{"
        if stripped.startswith(prefix):
            found.append(json.loads(stripped[len(tool) :].strip()))
    return found


def _field(text: str, key: str) -> str:
    for line in text.splitlines():
        for token in line.split():
            if token.startswith(f"{key}="):
                return token.split("=", 1)[1]
    raise AssertionError(f"the text never stated {key}=; a caller cannot carry it forward")


# -- the walk -----------------------------------------------------------------------------------


def test_a_text_only_client_completes_ask_graph_expand_and_a_content_read() -> None:
    """ask -> graph -> expand -> read bodies, with `structured_content` never read once."""

    async def script(client: Client) -> dict[str, Any]:
        log: list[str] = []

        # 1. ask. The id and the next call must both be in the text.
        answer = _text(await client.call_tool("orivra_ask", ASK))
        log.append("orivra_ask")
        query_id = _field(answer, "query_id")
        assert query_id.startswith("q-")
        assert "graph:" in answer, "the text never said whether a graph exists"

        # 2. graph, by executing a call the answer printed rather than one built here.
        offered = _calls(answer, "orivra_graph")
        assert offered, "the answer offered no executable orivra_graph call"
        edges = next(one for one in offered if one.get("select") == "edges")
        assert edges["query_id"] == query_id
        page = _text(await client.call_tool("orivra_graph", edges))
        log.append("orivra_graph[edges]")
        assert " -obs." in page or " -inf." in page, "the page named no relation"
        assert "items " in page, "the page did not say which items it held"

        # Continuations, if the page offered one, are followed the same way.
        seen = 1
        following = [one for one in _calls(page, "orivra_graph") if one.get("cursor") is not None]
        while following and seen < 10:
            page = _text(await client.call_tool("orivra_graph", following[0]))
            log.append("orivra_graph[continuation]")
            seen += 1
            following = [
                one for one in _calls(page, "orivra_graph") if one.get("cursor") is not None
            ]

        # 3. omissions, then the expand call the omission line printed.
        omissions = next(one for one in offered if one.get("select") == "omissions")
        listing = _text(await client.call_tool("orivra_graph", omissions))
        log.append("orivra_graph[omissions]")
        expands = _calls(listing, "orivra_expand")
        assert expands, "no omission offered an executable orivra_expand call"
        expanded = _text(await client.call_tool("orivra_expand", expands[0]))
        log.append("orivra_expand")
        assert "added:" in expanded, "the expansion never said what it added"

        # 4. the content read, from the call the expansion printed.
        reads = _calls(expanded, "mailweave_get_messages")
        assert reads, (
            "the expansion recovered stub rows and offered no call to read their bodies, so a "
            "text-only client ends on structure - which is where the Desktop run ended"
        )
        bodies = _text(await client.call_tool("mailweave_get_messages", reads[0]))
        log.append("mailweave_get_messages")
        assert bodies.strip(), "the content read returned no text"
        return {"log": log, "query_id": query_id}

    out = drive(_service(), script)
    # The sequence itself, not `... or "mailweave_get_messages" in log`: the fixture mailbox
    # and the budget are fixed, so the walk is deterministic, and an `or` that accepts any log
    # ending in a content read would pass on a run that never reached the graph at all - which
    # is the exact run this file exists to catch.
    assert out["log"] == [
        "orivra_ask",
        "orivra_graph[edges]",
        "orivra_graph[omissions]",
        "orivra_expand",
        "mailweave_get_messages",
    ]


def test_every_orivra_tool_returns_text_a_caller_can_act_on() -> None:
    """No Orivra tool may answer a text-reading client with nothing.

    The failure was not an error. It was two tools returning `text=""`, which a client reads
    as "this call said nothing" and routes around.
    """

    async def script(client: Client) -> dict[str, str]:
        answer = _text(await client.call_tool("orivra_ask", ASK))
        query_id = _field(answer, "query_id")
        out = {"orivra_ask": answer}
        out["orivra_sources"] = _text(await client.call_tool("orivra_sources", {}))
        out["orivra_graph"] = _text(
            await client.call_tool("orivra_graph", {"query_id": query_id, "select": "nodes"})
        )
        listing = _text(
            await client.call_tool("orivra_graph", {"query_id": query_id, "select": "omissions"})
        )
        expands = _calls(listing, "orivra_expand")
        out["orivra_expand"] = _text(await client.call_tool("orivra_expand", expands[0]))
        return out

    texts = drive(_service(), script)
    for name, text in texts.items():
        assert text.strip(), f"{name} answered a text-only client with nothing"
        assert text.splitlines()[0].startswith(name), (
            f"{name}'s text does not say which tool wrote it"
        )


def _volatile(payload: Any) -> set[str]:
    """Exactly the strings this response declared as nonce, handle or freshness stamp.

    `orivra.equivalence` already names the three families in which two correct MailWeave
    responses to one question legitimately differ, and nothing else may differ. Collecting
    the **values the response itself declared** - never a pattern guessed from the text -
    is what keeps the comparison below byte-exact everywhere else: an `orivra_` line could
    not hide inside a mark, because no mark is placed except over a value read off a
    `fence_nonce`, `map_id` or `fetched_at`/`verified_at`/`observed_at` key.
    """
    from orivra.equivalence import HANDLE_KEYS, TIMESTAMP_KEYS

    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if (
                    key in {"fence_nonce", *HANDLE_KEYS, *TIMESTAMP_KEYS}
                    and isinstance(value, str)
                    and value
                ):
                    found.add(value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return found


def _marked(text: str, volatile: set[str]) -> str:
    for value in sorted(volatile, key=len, reverse=True):
        text = text.replace(value, "<volatile>")
    return text


def test_the_legacy_mailweave_tools_keep_their_own_wire_contract() -> None:
    """Orivra's block is Orivra's. The legacy four are what they were, to the byte.

    `orivra serve` publishes MailWeave's four unchanged, from MailWeave's own handlers; a
    projection added here that leaked into them would be a change to a shipped contract made
    by a server that only hosts it.

    "To the byte" needs the one qualification `orivra/equivalence.py` already argues for at
    length: MailWeave mints a fresh fence nonce per response, stamps freshness from the real
    clock and signs handles that embed both, so *two correct responses to the same question
    differ byte-for-byte* and a test demanding otherwise would fail for correct reasons.
    `_volatile` marks those declared values on both sides and nothing else, so every other
    character still has to match.

    This is the guard, not the consumer: reading `structured_content` here is what makes the
    marking exact. The walk above never touches it.
    """
    from mailweave.surface.arguments import parse_search
    from mailweave.surface.rendering import render

    service = _service()

    async def script(client: Client) -> tuple[str, set[str]]:
        result = await client.call_tool("mailweave_search", {"query": QUESTION})
        return _text(result), _volatile(result.structured_content)

    through, through_volatile = drive(service, script)
    direct = render(service.registry.gmail().service.search(parse_search({"query": QUESTION})))

    assert _marked(through, through_volatile) == _marked(direct.text, _volatile(direct.structured))
    assert "orivra_" not in through, "an Orivra line reached a legacy tool's text"
    assert DIVIDER not in through, "Orivra's divider reached a legacy tool's text"


@pytest.mark.parametrize("select", ["edges", "nodes", "omissions"])
def test_a_graph_page_states_its_own_continuation_in_text(select: str) -> None:
    """A page a caller cannot continue is a page that silently ends the walk."""

    async def script(client: Client) -> tuple[str, int]:
        answer = _text(await client.call_tool("orivra_ask", ASK))
        query_id = _field(answer, "query_id")
        page = _text(
            await client.call_tool("orivra_graph", {"query_id": query_id, "select": select})
        )
        executable = sum(
            len(_calls(page, tool))
            for tool in ("orivra_graph", "orivra_expand", "mailweave_get_messages")
        )
        return page, executable

    page, offered = drive(_service(), script)
    assert f"select={select}" in page
    assert "view=" in page, "no view token, so no cursor can be presented with one"
    if "next:" in page:
        # Which call continues a page depends on what it holds: another `orivra_graph` with a
        # cursor for a page that is truncated, an `orivra_expand` for an omission that names a
        # recovery. Requiring `orivra_graph` specifically failed the omissions selection for
        # offering the *right* call, which is a test asserting a shape rather than the claim.
        assert offered >= 1, "the page said there was more and named no call to get it"


# -- the near-cap walk: the shape two live Desktop runs died on ---------------------------------

NEAR_CAP_QUESTION = "Larch pricing draft"

#: Eight threads of three long messages each. **Not a fixture that already fits**: composed the
#: way `orivra_ask` composed before 2026-09-19 - MailWeave's container fitted to the whole
#: 25,000-character cap, Orivra's block added on top of it - this renders past the cap and the
#: ask declines. `test_the_near_cap_fixture_really_does_reproduce_the_failure` proves that
#: rather than asserting it, so this file cannot quietly become a test of a small mailbox.
#:
#: **Re-measured 2026-09-22, body repeats 8 to 4.** The text mirror gained every row's
#: attribution and chronology lines and the response its attribution note, and the estimate
#: charges both, so at 8 repeats the third row no longer fitted the container and the
#: container at the whole cap rendered 17,786 - the old composition came to 24,022, inside the
#: cap, and the guard below failed for the right reason. Measured on the shipped tools: three
#: rows fit at 1 to 6 repeats (the old composition is 26,610 to 27,990, over the cap at every
#: one); at 7 and above two rows fit and it is not. 4 is the middle of that window: the
#: container at the cap renders 21,202 and the old composition 27,438.
NEAR_CAP_THREADS = 8
NEAR_CAP_PER_THREAD = 3
NEAR_CAP_BODY_REPEATS = 4
NEAR_CAP_NODES = 14


def _near_cap_mailbox() -> SyntheticMailbox:
    base = mailbox()
    rows = [
        Msg(
            id=f"{thread:02x}{index:02x}beef{thread:02x}{index:02x}",
            thread_id=f"t-larch-{thread}",
            sender=f"p{index % 3}@team.example",
            subject=f"Larch pricing draft {thread}",
            body=(
                "The Larch pricing draft needs the revised figures before we publish. "
                * NEAR_CAP_BODY_REPEATS
            ),
            internal_date_ms=epoch_ms(2026, 1 + thread, 1 + index),
            to=("ana@team.example",),
            in_reply_to=(
                f"<{thread:02x}{index - 1:02x}beef{thread:02x}{index - 1:02x}@mail.invalid>"
                if index
                else None
            ),
        )
        for thread in range(NEAR_CAP_THREADS)
        for index in range(NEAR_CAP_PER_THREAD)
    ]
    return SyntheticMailbox(messages=(*base.messages, *rows), now_ms=base.now_ms)


def _near_cap_service() -> OrivraService:
    adapter = GmailAdapter(service=make_service(_near_cap_mailbox()), granted_scopes=(SCOPE,))
    return OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}),
        max_graph_nodes=NEAR_CAP_NODES,
    )


def _size(result: Any) -> int:
    """The whole serialized result, both halves, exactly as the host is handed it."""
    text = "\n".join(
        block.text for block in result.content if getattr(block, "type", None) == "text"
    )
    return rendered_chars(result.structured_content or {}, text)


def test_the_near_cap_fixture_really_does_reproduce_the_failure() -> None:
    """The guard on the guard: prove this mailbox overruns, rather than assuming it.

    A near-cap regression whose fixture has quietly shrunk below the cap is a test that passes
    for the wrong reason and reports nothing. So the failing composition is reconstructed from
    two shipped calls: `mailweave_search`, which is still fitted to the whole cap and is
    therefore exactly the container the old code composed with, plus this ask's own block,
    which is what it added on top. If that sum is not over the cap, the fixture is too small
    and this file's other near-cap test is not testing what it says.
    """

    async def script(client: Client) -> tuple[int, int, int]:
        ask = await client.call_tool("orivra_ask", {"query": NEAR_CAP_QUESTION})
        payload = dict(ask.structured_content or {})
        # **Orivra's block exactly, which is not `whole - container`.** The text half of an ask
        # is Orivra's own lines *and* MailWeave's mirror, and the mirror is already counted
        # inside `mailweave_search`'s own size below. Subtracting only the container's
        # structured half would carry the mirror into both terms and inflate the old
        # composition by several thousand characters - which would make this guard pass on a
        # fixture that never overran.
        head = _text(ask).partition(DIVIDER)[0]
        block = len(json.dumps({k: v for k, v in payload.items() if k != "gmail"}, default=str))
        block += len(head)
        search = await client.call_tool("mailweave_search", {"query": NEAR_CAP_QUESTION})
        return _size(ask), block, _size(search)

    whole, block, at_full_cap = drive(_near_cap_service(), script)
    assert block > 0, "the ask carried no block of its own, so there is nothing to reproduce"
    assert at_full_cap + block > HOST_RESULT_CHAR_CAP, (
        f"this fixture composes to {at_full_cap + block} the old way (container {at_full_cap} "
        f"at the whole cap, plus a {block}-character block), which is inside the "
        f"{HOST_RESULT_CHAR_CAP} cap - it no longer reproduces the failure and the near-cap "
        "walk below is passing on a mailbox that always fitted"
    )
    assert whole <= HOST_RESULT_CHAR_CAP, "the repaired composition is over the cap"


def test_a_text_only_client_completes_the_whole_walk_on_a_near_cap_answer() -> None:
    """ask -> graph -> expand -> content read, at the size that used to refuse.

    Every call is parsed out of the text the previous response printed, and every response is
    measured whole - `structuredContent` and text together, which is what the host is handed -
    against the cap. The walk is the product's claim; the measurement is the thing two Desktop
    runs disproved.
    """

    async def script(client: Client) -> dict[str, Any]:
        sizes: list[int] = []
        log: list[str] = []

        ask = await client.call_tool("orivra_ask", {"query": NEAR_CAP_QUESTION})
        sizes.append(_size(ask))
        answer = _text(ask)
        log.append("orivra_ask")
        # Read rather than discarded: an answer whose text does not carry the id is one a
        # text-only client cannot address anything to, whatever else it says.
        assert _field(answer, "query_id").startswith("q-")
        assert "graph: built" in answer, f"no graph was built at the cap:\n{answer}"

        offered = _calls(answer, "orivra_graph")
        assert offered, "the answer offered no executable orivra_graph call"
        edges = next(one for one in offered if one.get("select") == "edges")
        page = await client.call_tool("orivra_graph", edges)
        sizes.append(_size(page))
        edge_text = _text(page)
        log.append("orivra_graph[edges]")
        assert " -obs." in edge_text or " -inf." in edge_text, "the page named no relation"

        omissions = next(one for one in offered if one.get("select") == "omissions")
        listing = await client.call_tool("orivra_graph", omissions)
        sizes.append(_size(listing))
        log.append("orivra_graph[omissions]")
        expands = _calls(_text(listing), "orivra_expand")
        assert expands, "no omission offered an executable orivra_expand call"

        expanded = await client.call_tool("orivra_expand", expands[0])
        sizes.append(_size(expanded))
        expanded_text = _text(expanded)
        log.append("orivra_expand")
        assert "added:" in expanded_text, "the expansion never said what it added"

        reads = _calls(expanded_text, "mailweave_get_messages")
        assert reads, (
            "the expansion recovered stub rows and offered no call to read their bodies, so a "
            "text-only client ends on structure - which is where the Desktop runs ended"
        )
        bodies = await client.call_tool("mailweave_get_messages", reads[0])
        sizes.append(_size(bodies))
        log.append("mailweave_get_messages")
        assert _text(bodies).strip(), "the content read returned no text"
        return {"log": log, "sizes": sizes}

    out = drive(_near_cap_service(), script)
    assert out["log"] == [
        "orivra_ask",
        "orivra_graph[edges]",
        "orivra_graph[omissions]",
        "orivra_expand",
        "mailweave_get_messages",
    ]
    over = [size for size in out["sizes"] if size > HOST_RESULT_CHAR_CAP]
    assert not over, f"responses over the {HOST_RESULT_CHAR_CAP} cap: {over}"
    assert max(out["sizes"]) > HOST_RESULT_CHAR_CAP * 0.9, (
        f"the largest response in this walk was {max(out['sizes'])}, comfortably inside the "
        "cap - this is no longer a near-cap walk"
    )


def test_whatever_the_block_sets_aside_is_named_with_the_call_that_serves_it() -> None:
    """Compaction is only honest if the text says what moved and how to get it back."""

    async def script(client: Client) -> dict[str, Any]:
        ask = await client.call_tool("orivra_ask", {"query": NEAR_CAP_QUESTION})
        answer = _text(ask)
        served: dict[str, Any] = {"text": answer, "pages": {}}
        for compacted in _calls(answer, "orivra_graph"):
            select = compacted.get("select")
            page = await client.call_tool("orivra_graph", compacted)
            served["pages"][select] = (_text(page), _size(page))
        for sources in _calls(answer, "orivra_sources"):
            served["sources"] = _text(await client.call_tool("orivra_sources", sources))
        return served

    served = drive(_near_cap_service(), script)
    text = served["text"]
    if "compacted" in text:
        # Every list the block gave up names a count and a call, and the call was made above.
        assert "record(s), by" in text or "orivra_sources {}" in text, (
            "the text says something was compacted and does not say what or how to get it"
        )
    for select, (page_text, size) in served["pages"].items():
        assert page_text.strip(), f"the {select} page answered a text-only client with nothing"
        assert size <= HOST_RESULT_CHAR_CAP, f"the {select} page is over the cap at {size}"


# -- the links selection, which compaction depends on -------------------------------------------


LINKS_QUESTION = "Larch pricing draft"


def _links_service() -> OrivraService:
    """Bodies carrying URLs no node in the graph can represent.

    `unresolved_links` is the one list in the block that had nowhere else to live: the omission
    records were always servable by `orivra_graph select=omissions`, so compacting them costs a
    call, while compacting these would have lost them. `Selection.LINKS` is what makes the
    compaction honest, so it needs a walk of its own.
    """
    base = mailbox()
    rows = [
        Msg(
            id=f"aa{index:02x}beefaa{index:02x}",
            thread_id="t-links",
            sender="p@team.example",
            subject="Larch pricing draft",
            body=(
                f"The Larch pricing draft is at https://docs.example.com/larch-{index} and "
                f"also https://vendor.example.org/quote-{index}, please review. "
            )
            * 3,
            internal_date_ms=epoch_ms(2026, 2, 1 + index),
            to=("ana@team.example",),
            in_reply_to=(
                f"<aa{index - 1:02x}beefaa{index - 1:02x}@mail.invalid>" if index else None
            ),
        )
        for index in range(4)
    ]
    box = SyntheticMailbox(messages=(*base.messages, *rows), now_ms=base.now_ms)
    adapter = GmailAdapter(service=make_service(box), granted_scopes=(SCOPE,))
    return OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}), max_graph_nodes=10
    )


def test_the_links_page_renders_links_rather_than_empty_omission_lines() -> None:
    """A page that is structurally right and textually empty is the failure being repaired.

    The first `select=links` page returned thirteen rows and rendered every one of them as
    `(presence-free)  cause=None count=None`, because the item renderer fell through to the
    omission branch - which asks a link for a handle, a cause and a count, and a link has none
    of the three. To a client reading text that page said nothing thirteen times, which is the
    same defect as `text=""` wearing a different hat.
    """

    async def script(client: Client) -> tuple[str, str, int]:
        ask = await client.call_tool("orivra_ask", {"query": LINKS_QUESTION})
        answer = _text(ask)
        offered = _calls(answer, "orivra_graph")
        links = [one for one in offered if one.get("select") == "links"]
        assert links, f"the answer never offered the links page:\n{answer}"
        page = await client.call_tool("orivra_graph", links[0])
        return answer, _text(page), _size(page)

    _answer, page, size = drive(_links_service(), script)
    assert size <= HOST_RESULT_CHAR_CAP
    rows = [line for line in page.splitlines() if line.startswith("  http")]
    assert rows, f"no link rendered as a link:\n{page}"
    assert "(presence-free)" not in page, "a link was rendered as an omission with nothing in it"
    for row in rows:
        assert " from=" in row, f"a link did not say which message carried it: {row}"
