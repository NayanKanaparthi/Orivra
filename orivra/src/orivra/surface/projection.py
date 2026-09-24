"""One response, two projections - and the text one is enough to navigate with.

**Why this module exists.** A real Claude Desktop run on 2026-09-18 reached a cited answer
about a Harbor export mismatch and could not use the graph at all. Nothing was broken: it read
messages, cited them, and answered. But `orivra_graph` and `orivra_expand` returned
`text=""`, and that client consumed text content. So the two tools that make this a graph
product were, to that client, calls that returned nothing - no query id to carry forward, no
statement of whether a graph existed, no page contents, no continuation, and no next call.
The client did the only thing left: it searched and read mail, which the legacy tools already
did before any of this was built.

MCP says a tool result MAY carry `structuredContent` and MUST be interpretable from its
content blocks. Building the surface so the second is empty makes the first mandatory in
practice, which is the same mistake the resource path made and the tools-first guarantee was
written to prevent. `docs/PRODUCT_CONTRACT.md` R-07 says it directly: an affordance "MUST work
through ordinary tool calls".

**The rule this module enforces.** `OrivraResponse` holds the answer once. `structured()` and
`text()` are both computed from that one object, so a fact reaches the wire in both forms or
in neither - there is no second place to add a field and forget the other. The text projection
carries, for every tool: the query id, whether a graph exists and what it holds, the contents
of whatever page was returned, the continuation when there is one, and the executable next
calls with their arguments already filled in.

**It is not a summary.** A summary of a page is a thing a caller cannot act on. Every line
that names something names it by the identifier the next call takes, and every `next:` line is
a tool name followed by the exact JSON arguments to send.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from mailweave.envelope.vocab import ToolName
from orivra.contracts import OrivraToolName

#: How many ids a suggested `mailweave_get_messages` call carries. Gmail's own per-fetch
#: ceiling is 50; this is smaller because the line is meant to be read as well as executed, and
#: the count of what was left out is printed beside it so nothing is hidden by the trim.
SUGGESTED_IDS: Final[int] = 10

#: Separates the Orivra block from MailWeave's own container mirror, so a reader can tell which
#: server wrote which half and a parser can split on a stable string.
DIVIDER: Final[str] = "--- gmail container (mailweave) ---"


def _args(arguments: Mapping[str, Any]) -> str:
    """Arguments as a client would send them: compact, sorted, valid JSON."""
    return json.dumps(dict(arguments), separators=(",", ":"), sort_keys=True, default=str)


def _call(name: str, arguments: Mapping[str, Any]) -> str:
    return f"  {name} {_args(arguments)}"


@dataclass(frozen=True)
class OrivraResponse:
    """One tool's answer. `structured()` and `text()` are two views of this same object.

    `mirror` is MailWeave's own text for a container it returned, carried through unchanged
    rather than re-rendered: two renderings of one envelope are two things that can disagree,
    and the legacy wire contract is that MailWeave's text is MailWeave's.
    """

    tool: OrivraToolName
    body: dict[str, Any] = field(default_factory=dict)
    mirror: str = ""

    def structured(self) -> dict[str, Any]:
        return self.body

    def text(self) -> str:
        lines = _RENDERERS[self.tool](self.body)
        if self.mirror:
            lines = [*lines, "", DIVIDER, self.mirror]
        return "\n".join(lines)


# -- per-tool renderers, each reading only the body ---------------------------------------------


def _ask(body: Mapping[str, Any]) -> list[str]:
    query_id = str(body.get("query_id", ""))
    graph = body.get("graph") or {}
    lines = [f"orivra_ask  query_id={query_id}"]

    counts = graph.get("counts")
    if counts:
        holds = "yes" if graph.get("holds_evidence") else "no"
        lines.append(
            f"graph: built  nodes={counts.get('nodes')} edges={counts.get('edges')} "
            f"omitted={counts.get('omitted')}  holds_evidence={holds}"
        )
        if graph.get("why_no_evidence"):
            lines.append(f"  {graph['why_no_evidence']}")
        by_relation = counts.get("by_relation") or {}
        if by_relation:
            lines.append(
                "  relations: "
                + ", ".join(f"{name}={count}" for name, count in sorted(by_relation.items()))
            )
    else:
        lines.append(f"graph: not built  {graph.get('routing', '')}".rstrip())

    for link in body.get("graph", {}).get("unresolved_links") or ():
        lines.append(f"  unresolved link: {link.get('url')} ({link.get('why', '')})")

    lines.extend(_allocation(body.get("allocation") or {}))
    lines.extend(_compaction("graph block", graph.get("compacted") or {}))
    lines.extend(_compaction("stage budget", (body.get("budget") or {}).get("compacted") or {}))

    if counts and query_id:
        # **Every selection, every time, and no de-duplication against the lines above.** A
        # call that also appears in a compaction record is still a call this list should name:
        # a reader scanning `next:` for what to do should not have to have read the record to
        # find the selection it moved into, and a parser taking the same line twice makes the
        # same call twice.
        lines.append("next:")
        moved = {
            entry.get("recover", {}).get("args", {}).get("select")
            for entry in (graph.get("compacted") or {}).get("moved") or ()
        }
        selections = ["edges", "nodes", "omissions"]
        if graph.get("unresolved_links") or "links" in moved:
            selections.append("links")
        for select in selections:
            lines.append(
                _call(OrivraToolName.GRAPH.value, {"query_id": query_id, "select": select})
            )
    return lines


def _allocation(block: Mapping[str, Any]) -> list[str]:
    """What this response was allowed to spend, and - if it bit - what to call instead.

    **In the text, not only the structured half.** The whole point of the sizing work is a
    client that reads text content; a caller told nothing about the allocation cannot tell a
    mailbox with no answer from a container with no room, and those need different next moves.
    """
    if not block:
        return []
    lines = [
        f"allocation: container={block.get('container_chars')} "
        f"reserve={block.get('orivra_reserve_chars')} cap={block.get('host_cap_chars')}"
    ]
    nothing = block.get("disclosed_nothing")
    if not nothing:
        return lines
    lines.append(
        f"  disclosed no message from {nothing.get('sources_reached')} source(s) reached: "
        f"{nothing.get('why', '')}"
    )
    recover = nothing.get("recover") or {}
    if recover.get("tool"):
        lines.append(f"  {recover.get('gets', '')}".rstrip())
        lines.append(_call(str(recover["tool"]), recover.get("args") or {}))
    return lines


def _compaction(what: str, block: Mapping[str, Any]) -> list[str]:
    """One line per list this response set aside, each with the call that serves it."""
    if not block:
        return []
    lines = [f"compacted {what}: {block.get('why', '')}".rstrip()]
    recover = block.get("recover")
    if recover and recover.get("tool"):
        lines.append(_call(str(recover["tool"]), recover.get("args") or {}))
    for entry in block.get("moved") or ():
        lines.append(f"  {entry.get('field')}: {entry.get('count')} record(s), by")
        hop = entry.get("recover") or {}
        if hop.get("tool"):
            lines.append(_call(str(hop["tool"]), hop.get("args") or {}))
    return lines


def _graph(body: Mapping[str, Any]) -> list[str]:
    query_id = str(body.get("query_id", ""))
    select = str(body.get("select", ""))
    items = body.get("items") or []
    returned_from = body.get("returned_from", 0)
    total = body.get("total", 0)
    lines = [
        f"orivra_graph  query_id={query_id} select={select} "
        f"revision={body.get('revision')} state={body.get('state')}"
    ]
    upper = returned_from + len(items)
    last = max(upper - 1, returned_from)
    lines.append(f"items {returned_from}-{last} of {total}  view={body.get('view')}")

    disclosure = body.get("disclosure") or {}
    if body.get("narrowed_by_live_check"):
        lines.append("  narrowed by the live access check on this read")
    if disclosure.get("source_backed_nodes") == 0:
        lines.append(
            "  this graph holds no source-backed node, so there is nothing here to disclose. "
            "That is a fact about the graph, not about your access"
        )

    for item in items:
        lines.append("  " + _item_line(select, item))

    if body.get("state") == "oversized" and body.get("oversized"):
        over = body["oversized"]
        lines.append(
            f"  OVERSIZED {over.get('identity')} at position {over.get('position')} is "
            f"{over.get('chars')} chars against a {over.get('budget')} budget; the cursor "
            "has stepped past it"
        )

    lines.extend(_graph_next(body, query_id, select))
    return lines


def _item_line(select: str, item: Mapping[str, Any]) -> str:
    if select == "edges":
        support = ",".join(
            str(one.get("native_id")) for one in (item.get("support") or ()) if one.get("native_id")
        )
        confidence = item.get("confidence")
        held = f" confidence={confidence.get('value')}" if isinstance(confidence, Mapping) else ""
        return (
            f"{item.get('source')} -{item.get('relation')}-> {item.get('target')}  "
            f"[{item.get('origin')}/{item.get('assertion')}{held}]"
            + (f" support={support}" if support else "")
        )
    if select == "nodes":
        return (
            f"{item.get('node_id')}  kind={item.get('kind')} depth={item.get('depth')} "
            f"freshness={(item.get('freshness') or {}).get('state')}"
        )
    if select == "links":
        # **Its own branch, because it falls through to the omission line otherwise** and an
        # omission line asks an unresolved link three questions it has no answer to: it has no
        # handle, no cause and no count. The first `select=links` page rendered thirteen rows
        # as thirteen copies of `(presence-free) cause=None count=None` - structurally a page,
        # and nothing at all to a client that reads text.
        return f"{item.get('url')}  from={item.get('from')}  {item.get('why', '')}".rstrip()
    recover = item.get("recover") or {}
    handle = item.get("what") or ""
    tail = f"  recover: {recover.get('tool')} {_args(recover.get('args') or {})}" if recover else ""
    return (
        f"{handle or '(presence-free)'}  cause={item.get('cause')} count={item.get('count')}" + tail
    )


def _graph_next(body: Mapping[str, Any], query_id: str, select: str) -> list[str]:
    lines: list[str] = []
    following: list[str] = []
    cursor = body.get("next_cursor")
    if cursor is not None:
        following.append(
            _call(
                OrivraToolName.GRAPH.value,
                {
                    "query_id": query_id,
                    "select": select,
                    "cursor": cursor,
                    "view": body.get("view"),
                },
            )
        )
    if select == "omissions":
        for item in body.get("items") or []:
            if item.get("recover") and item.get("what"):
                following.append(
                    _call(
                        OrivraToolName.EXPAND.value,
                        {"query_id": query_id, "handle": item["what"]},
                    )
                )
    if following:
        lines.append("next:")
        lines.extend(following)
    return lines


def _expand(body: Mapping[str, Any]) -> list[str]:
    query_id = str(body.get("query_id", ""))
    added = body.get("added") or {}
    counts = added.get("counts") or {}
    lines = [
        f"orivra_expand  query_id={query_id} handle={body.get('handle')} "
        f"revision={body.get('revision')}"
    ]
    executed = body.get("executed") or {}
    if executed:
        lines.append(f"executed: {executed.get('tool')} {_args(executed.get('args') or {})}")

    if added.get("shed"):
        lines.append(
            f"added: {counts.get('nodes')} node(s), {counts.get('edges')} relation(s) - the "
            "delta did not fit this response and was not repeated; read it with orivra_graph"
        )
    else:
        lines.append(
            f"added: {len(added.get('nodes') or ())} node(s), "
            f"{len(added.get('edges') or ())} relation(s)"
        )
        for node in added.get("nodes") or ():
            lines.append(f"  + {node.get('node_id')}")

    graph = body.get("graph") or {}
    lines.append(
        f"graph now: nodes={graph.get('nodes')} edges={graph.get('edges')} "
        f"omitted={graph.get('omitted')} hops={graph.get('hops_taken')}"
    )
    cache = body.get("cache") or {}
    if cache:
        lines.append(
            f"cache: consulted={cache.get('consulted')} outcome={cache.get('outcome')} "
            f"reason={cache.get('reason')}"
        )

    unread = _unread_ids(body)
    if unread:
        lines.append(
            f"{len(unread)} recovered row(s) are stubs and carry no text. Recovering a branch "
            "is not reading it"
        )

    lines.append("next:")
    lines.append(_call(OrivraToolName.GRAPH.value, {"query_id": query_id, "select": "edges"}))
    if unread:
        lines.append(
            _call(
                ToolName.GET_MESSAGES.value,
                {"message_ids": unread[:SUGGESTED_IDS], "view": "body_clean"},
            )
        )
        if len(unread) > SUGGESTED_IDS:
            lines.append(
                f"  ({len(unread) - SUGGESTED_IDS} further id(s) not listed above; they are "
                "in orivra_graph select=nodes)"
            )
    return lines


def _unread_ids(body: Mapping[str, Any]) -> list[str]:
    unread = body.get("text_not_read") or {}
    return [
        str(one).removeprefix("gmail/message/")
        for one in unread.get("nodes") or ()
        if str(one).startswith("gmail/message/")
    ]


def _sources(body: Mapping[str, Any]) -> list[str]:
    lines = ["orivra_sources"]
    for row in body.get("sources") or ():
        lines.append(f"  {row.get('connector')}: {row.get('state')}  {row.get('detail', '')}")
    return lines


_RENDERERS: Final[dict[OrivraToolName, Any]] = {
    OrivraToolName.ASK: _ask,
    OrivraToolName.GRAPH: _graph,
    OrivraToolName.EXPAND: _expand,
    OrivraToolName.SOURCES: _sources,
}


def composed_cost(rendered: Mapping[str, Any], select: str) -> int:
    """What one page item costs in **both** projections, which is what the host is handed.

    The paginator charged the structured item alone, so adding a text projection would have
    spent characters no budget knew about and pushed a full page past the host cap. Charging
    both keeps one budget honest: the page holds fewer items and the rest stay reachable
    through the continuation, which is what a page is for. Nothing is dropped and the cap does
    not move.
    """
    return len(json.dumps(rendered, default=str)) + len(_item_line(select, rendered)) + 3


__all__ = ["DIVIDER", "SUGGESTED_IDS", "OrivraResponse", "composed_cost"]
