"""The Orivra tool surface: two tools published, two declared and not published.

**Two, because two are built.** M1 mounts the four `mailweave_*` tools unchanged and adds
`orivra_ask` and `orivra_sources`. `orivra_expand` and `orivra_trace` are specified below in
`PLANNED` and are **not on the surface**: a tool a client can see and this server cannot run
is a promise the next call breaks, and `test_the_planned_tools_are_not_published` holds it.

**Every claim is a `Claim`.** `mailweave.surface.tools.Claim` is reused rather than
re-declared, so a sentence in an Orivra tool description names the test that executes it
under exactly the rule the v0.1 surface already lives by: there is no prose here that is not
a claim, and a claim whose evidence is deleted or renamed fails the build.

**`outputSchema` is published for the Orivra tools and not added to MailWeave's four.**
Adding one to `mailweave_search` would change the published v0.1 surface, and "unchanged"
is the compatibility claim M1 is making. Orivra's tools are new, so they carry one from the
start and their responses carry `structuredContent` that validates against it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from mailweave.surface.tools import SEARCH, UNTRUSTED_DATA_WARNING, Claim
from orivra.contracts import ConnectorId, OrivraToolName

#: The protocol's own bound on a tool name. Checked here rather than assumed, because a
#: name over it is refused by the client and not by this server.
MAX_TOOL_NAME_CHARS: Final[int] = 64


@dataclass(frozen=True)
class OrivraToolSpec:
    """One Orivra tool, whole. Every field a compile-time constant."""

    name: OrivraToolName
    title: str
    claims: tuple[Claim, ...]
    input_schema: dict[str, object]
    output_schema: dict[str, object]

    def __post_init__(self) -> None:
        if len(self.name.value) > MAX_TOOL_NAME_CHARS:
            raise ValueError(
                f"tool name {self.name.value!r} is {len(self.name.value)} characters, over "
                f"the protocol's {MAX_TOOL_NAME_CHARS}-character bound; a client refuses it "
                "and this server would never learn why"
            )
        if not self.title:
            raise ValueError(f"tool {self.name.value} publishes no title")

    @property
    def description(self) -> str:
        return " ".join(claim.text for claim in self.claims)


# --- shared schema fragments ---------------------------------------------------------------

_SOURCES_ARGUMENT: Final[dict[str, object]] = {
    "type": "array",
    "items": {"type": "string", "enum": [connector.value for connector in ConnectorId]},
    "minItems": 1,
    "description": (
        "Which sources to search. Only 'gmail' is answerable in this release; naming a "
        "source this installation does not have returns that source's state in per_source "
        "rather than an error, because 'not configured' and 'returned nothing' are "
        "different answers and a caller must be able to tell them apart."
    ),
}

#: The Gmail container: **MailWeave's own `mailweave_search` payload, verbatim**.
#:
#: Deliberately not re-described field by field here. Two descriptions of one payload are
#: two contracts, and the one that drifts is always the copy - which is the defect this
#: repository has now found more than a dozen times. The schema says what it is and points
#: at the tool that owns it.
_GMAIL_CONTAINER: Final[dict[str, object]] = {
    "type": "object",
    "description": (
        "The Gmail evidence, which is the response mailweave_search would return for the "
        "same question, unmodified: the same envelope object, built by the same builder, "
        "measured against the same ceilings and sealed by the same disposition certificate. "
        "Its schema is mailweave_search's."
    ),
}

_PER_SOURCE: Final[dict[str, object]] = {
    "type": "array",
    "description": (
        "One entry per source this installation knows about, including the ones it does "
        "not have. state is one of ready, not_configured, auth_required, degraded, "
        "unavailable."
    ),
    "items": {
        "type": "object",
        "properties": {
            "connector": {"type": "string"},
            "state": {"type": "string"},
            "asked": {
                "type": "boolean",
                "description": (
                    "Whether this call asked this source. A connected source that was not "
                    "asked reports state 'ready' with no hits, which is not the same as a "
                    "source that was searched and found nothing."
                ),
            },
            "hits": {"type": "integer"},
            "quota_units": {"type": "integer"},
            "rungs_executed": {"type": "array", "items": {"type": "string"}},
            "caps_hit": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["connector", "state", "asked"],
    },
}

#: The budget block whole: every stage, its connector, its limit and why it is unmeasured.
_BUDGET_STAGES: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "stages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "stage": {"type": "string"},
                    "connector": {"type": ["string", "null"]},
                    "limit_ms": {"type": ["integer", "null"]},
                    "unmeasured_because": {"type": "string"},
                },
                "required": ["stage", "limit_ms"],
            },
        }
    },
    "required": ["stages"],
}

#: The budget block compacted (`service._budget_digest`): the stage names by whether they
#: were measured, and the call that returns the whole block. **This shape was reachable and
#: not published** until 2026-09-21: the compaction ladder has emitted it since the response
#: was first sized before it was built, and no fixture reached the step until every row grew
#: an attribution block and a near-cap answer compacted its budget to fit. A shape a server
#: can emit and its schema does not admit is a schema that lies, so it is admitted here.
_BUDGET_DIGEST: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "measured": {"type": "array", "items": {"type": "string"}},
        "unmeasured": {"type": "array", "items": {"type": "string"}},
        "compacted": {
            "type": "object",
            "properties": {
                "why": {"type": "string"},
                "recover": {
                    "type": "object",
                    "properties": {
                        "tool": {"type": "string"},
                        "args": {"type": "object"},
                    },
                    "required": ["tool", "args"],
                },
            },
            "required": ["why", "recover"],
        },
    },
    "required": ["measured", "unmeasured", "compacted"],
}

_BUDGET: Final[dict[str, object]] = {
    "description": (
        "Orivra's own hierarchical budget. Every stage is listed; a stage with limit_ms "
        "null did not bind and says why. Orivra does not inherit the legacy Gmail deadline: "
        "that figure was selected for one Gmail search on one connector and no figure ships "
        "here before the milestone that measures it. When an answer had to compact its budget "
        "to fit the host's cap, the block is the digest form: the stage names by whether they "
        "were measured, and the orivra_sources call that returns the whole block."
    ),
    "oneOf": [_BUDGET_STAGES, _BUDGET_DIGEST],
}


def _ask_input_schema() -> dict[str, object]:
    """`mailweave_search`'s published input schema, plus `sources`.

    **Derived, because `ask` forwards its arguments to `parse_search`** (review finding
    R-M1-010). The first draft wrote a schema by hand: it published four `view` values where
    the parser accepts two, and `additionalProperties: false` while the parser honours
    `budget`, `scan`, `constraints`, `relax`, `structural`, `pool` and forced rungs. A strict
    client therefore refused calls this server accepts, and this server accepted calls the
    schema forbids - in both directions at once. A published schema that disagrees with the
    parser behind it is worse than none, because a client trusts it.

    So the schema is the one the parser actually enforces, read off MailWeave's own spec, with
    the one argument Orivra adds. When MailWeave's changes, this changes with it.
    """
    inherited: dict[str, object] = dict(SEARCH.input_schema)
    published = inherited.get("properties")
    if not isinstance(published, dict):  # pragma: no cover - MailWeave's spec has one
        raise AssertionError(
            "mailweave_search publishes no properties block; this schema is derived from it "
            "and a hand-written substitute is what R-M1-010 was"
        )
    properties: dict[str, object] = dict(published)
    properties["sources"] = _SOURCES_ARGUMENT
    inherited["properties"] = properties
    return inherited


# --- the published tools -------------------------------------------------------------------

ASK = OrivraToolSpec(
    name=OrivraToolName.ASK,
    title="Ask across the connected sources and return the evidence",
    claims=(
        Claim(
            text=(
                "Answers a question from the sources this installation has connected, and "
                "returns the evidence each one produced together with an account of what it "
                "did."
            ),
            evidence=("test_orivra_ask_returns_the_gmail_container_and_an_account_of_it",),
        ),
        Claim(
            text=(
                "In this release only Gmail is answerable, and the Gmail evidence is exactly "
                "what mailweave_search would return for the same question: the same envelope, "
                "unmodified."
            ),
            evidence=(
                "test_the_gmail_container_is_byte_identical_to_mailweave_search",
                "test_answer_hands_back_mailweaves_own_envelope_object",
            ),
        ),
        Claim(
            text=(
                "This server never writes: no tool here can send, draft, delete, label or "
                "modify anything, and the only Gmail scope it holds is read-only."
            ),
            evidence=("test_every_orivra_tool_is_annotated_read_only_and_the_annotation_is_true",),
        ),
        Claim(
            text=(
                "per_source names every source Orivra knows about, including the ones this "
                "installation has not configured, so a source that was never looked at is "
                "never mistaken for a source that found nothing."
            ),
            evidence=("test_per_source_names_every_connector_including_absent_ones",),
        ),
        Claim(
            text=(
                "budget lists every stage that can consume wall time; a stage with limit_ms "
                "null did not bind and states why, and no stage inherits the legacy Gmail "
                "deadline."
            ),
            evidence=("test_the_declared_budget_binds_nothing_and_says_so",),
        ),
        Claim(text=UNTRUSTED_DATA_WARNING, evidence=("test_content_is_fenced_and_labelled",)),
    ),
    input_schema=_ask_input_schema(),
    output_schema={
        "type": "object",
        "properties": {
            "query_id": {
                "type": "string",
                "description": (
                    "Server-minted, and passed back by the client on a follow-up. The "
                    "protocol is stateless, so this identifier is the whole of the "
                    "continuity between one call and the next."
                ),
            },
            "gmail": _GMAIL_CONTAINER,
            "per_source": _PER_SOURCE,
            "budget": _BUDGET,
        },
        "required": ["query_id", "per_source", "budget"],
    },
)

SOURCES = OrivraToolSpec(
    name=OrivraToolName.SOURCES,
    title="List the sources this installation can search",
    claims=(
        Claim(
            text=(
                "Lists every source Orivra knows about and the state each one is in, so a "
                "caller can tell a source that is not configured from one that found "
                "nothing."
            ),
            evidence=("test_per_source_names_every_connector_including_absent_ones",),
        ),
        Claim(
            text=(
                "Reports each connected source's capabilities as this server declares them, "
                "never as it discovered them by trying: a capability learned by attempting a "
                "call has already spent that call."
            ),
            evidence=("test_capabilities_are_declared_rather_than_probed",),
        ),
        Claim(
            text=("This tool reads no mail, opens no document and makes no request to any source."),
            evidence=("test_orivra_sources_makes_no_request_to_any_source",),
        ),
    ),
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    output_schema={
        "type": "object",
        "properties": {
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "connector": {"type": "string"},
                        "state": {"type": "string"},
                        "detail": {"type": "string"},
                        "capabilities": {"type": ["object", "null"]},
                    },
                    "required": ["connector", "state", "detail"],
                },
            },
            "budget": _BUDGET,
        },
        "required": ["sources", "budget"],
    },
)

EXPAND = OrivraToolSpec(
    name=OrivraToolName.EXPAND,
    title="Follow one handle from a graph this server already built",
    claims=(
        Claim(
            text=(
                "Follows one handle out of an earlier answer's omission list - a pruned "
                "branch, a capped thread, a region never walked - and returns what it "
                "recovers under the same query_id."
            ),
            evidence=(
                "test_expansion_adds_the_recovered_nodes_to_the_graph_and_bumps_the_revision",
                "test_the_newly_available_nodes_are_readable_with_their_own_sources",
            ),
        ),
        Claim(
            text=(
                "Only handles this server minted are executable. A handle names a tool and "
                "its arguments, and this tool refuses one the graph it belongs to does not "
                "carry, so a caller cannot turn an expansion into an arbitrary call."
            ),
            evidence=("test_a_handle_the_graph_never_minted_is_refused",),
        ),
        Claim(
            text=(
                "A graph lives for ten minutes. After that the same handle reports that the "
                "query is gone rather than silently answering from a different retrieval."
            ),
            evidence=("test_an_expired_query_id_is_refused_rather_than_rebuilt",),
        ),
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query_id": {
                "type": "string",
                "description": (
                    "The query_id the answer you are expanding carried. Server-minted; there "
                    "is no session, so this identifier is the whole of the continuity."
                ),
            },
            "handle": {
                "type": "string",
                "description": (
                    "The `what` of the omission record you are following, exactly as the "
                    "answer's omission list spelled it."
                ),
            },
        },
        "required": ["query_id", "handle"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "query_id": {"type": "string"},
            "handle": {"type": "string"},
            "executed": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "args": {"type": "object"},
                    "reduces": {"type": "string"},
                },
                "required": ["tool", "args", "reduces"],
            },
            "gmail": {"type": ["object", "null"]},
            "budget": _BUDGET,
        },
        "required": ["query_id", "handle", "executed", "budget"],
    },
)

GRAPH = OrivraToolSpec(
    name=OrivraToolName.GRAPH,
    title="Read the evidence graph an answer built, a page at a time",
    claims=(
        Claim(
            text=(
                "Returns the actual nodes, edges and omissions of a graph an earlier answer "
                "built - each node with its source reference, each edge with the references "
                "it rests on - in pages that fit inside one response."
            ),
            evidence=("test_a_client_with_no_resource_support_can_read_every_edge",),
        ),
        Claim(
            text=(
                "This is the same projection the orivra://queries/{id}/graph resource serves. "
                "A client that ignores resources loses nothing but the convenience of one "
                "call."
            ),
            evidence=("test_the_paged_tool_and_the_resource_return_the_same_projection",),
        ),
        Claim(
            text=(
                "Every page re-checks this caller's current authorization and each item's "
                "current version against the source. A requirement recorded when the graph "
                "was built is not a check that it still holds."
            ),
            evidence=("test_a_narrowed_grant_withholds_edges_from_a_stored_graph",),
        ),
        Claim(
            text=(
                "A cursor is only honoured against the view it was taken from. If the graph "
                "was extended, or the access check disclosed a different set, the "
                "continuation is refused rather than resumed into positions that moved."
            ),
            evidence=(
                "test_a_cursor_is_refused_after_an_expansion_moved_the_view",
                "test_a_cursor_is_refused_after_the_live_check_changed_what_is_disclosed",
            ),
        ),
        Claim(
            text=(
                "An item too large for a whole page is named and stepped over rather than "
                "returned or dropped: the response cap is never exceeded, and the caller sees "
                "which item it could not carry."
            ),
            evidence=("test_an_item_larger_than_a_page_is_named_and_stepped_over",),
        ),
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query_id": {
                "type": "string",
                "description": "The query_id the answer carried.",
            },
            "select": {
                "type": "string",
                "enum": ["nodes", "edges", "omissions", "links"],
                "description": (
                    "Which part of the graph to read. Defaults to edges. `links` serves the "
                    "links the bodies carried that no node in this graph represents; it is "
                    "where they go when an answer's graph block was compacted to fit the "
                    "host's result cap, and the block says so when it was."
                ),
            },
            "cursor": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Where to resume, from a previous page's next_cursor. Omit for the first "
                    "page. A cursor must be presented together with that page's view token."
                ),
            },
            "view": {
                "type": "string",
                "description": (
                    "The view token the page that produced this cursor returned. Required "
                    "with a cursor: it is what lets this server tell that the positions still "
                    "mean what they meant, rather than resuming into a list an expansion or a "
                    "permission change has moved."
                ),
            },
            "node": {
                "type": "string",
                "description": (
                    "Optional. Restrict to one node and the edges touching it - branch-level "
                    "disclosure, for a caller following a thread rather than reading the "
                    "whole graph."
                ),
            },
        },
        "required": ["query_id"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "query_id": {"type": "string"},
            "revision": {"type": "integer"},
            "select": {"type": "string"},
            "items": {"type": "array", "items": {"type": "object"}},
            "total": {"type": "integer"},
            "returned_from": {"type": "integer"},
            "next_cursor": {"type": ["integer", "null"]},
            "view": {"type": "string"},
            "state": {"type": "string", "enum": ["ok", "oversized", "stale_cursor"]},
            "oversized": {"type": ["object", "null"]},
            "narrowed_by_live_check": {"type": "boolean"},
            "budget": _BUDGET,
        },
        "required": [
            "query_id",
            "revision",
            "select",
            "state",
            "items",
            "total",
            "next_cursor",
            "view",
            "budget",
        ],
    },
)

#: The tools this server publishes, in the order a client sees them.
TOOL_SPECS: Final[tuple[OrivraToolSpec, ...]] = (ASK, SOURCES, EXPAND, GRAPH)

SPEC_BY_NAME: Final[dict[OrivraToolName, OrivraToolSpec]] = {spec.name: spec for spec in TOOL_SPECS}

#: **Declared, and not published.** These arrive with M3, which is the milestone that builds
#: the query-time graph they address. They are written down here so the shape M3 has to hit
#: is on record, and `test_the_planned_tools_are_not_published` asserts that neither reaches
#: `tool_list()` - a tool a client can see and this server cannot run is a promise the next
#: call breaks.
PLANNED: Final[dict[OrivraToolName, str]] = {
    # `EXPAND` moved off this list on 2026-09-18: M3 built the query graph a handle addresses
    # and the tool is on the surface. The assertion in `orivra_handlers` is what enforces the
    # move - a tool cannot be published and planned at once - so this is not bookkeeping.
    OrivraToolName.TRACE: (
        "Returns the redacted retrieval trace for a query_id: what each source spent, what "
        "the graph did, and which entities were confirmed rather than merely candidates. "
        "Arrives with M3."
    ),
}


__all__ = [
    "ASK",
    "GRAPH",
    "MAX_TOOL_NAME_CHARS",
    "PLANNED",
    "SOURCES",
    "SPEC_BY_NAME",
    "TOOL_SPECS",
    "OrivraToolSpec",
]
