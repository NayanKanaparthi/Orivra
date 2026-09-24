"""Argument validation for the four tools, and the two ways a call can be refused.

**Two refusals, and they are not the same refusal.** This module is where the D.11
partition first bites, before any Gmail call is made:

  * `ToolRefused` carries a D.11 `ErrorCode` whose `ERROR_SURFACE` entry is
    `Surface.TOOL_ERROR`. It is a *declared* refusal: MailWeave understood the request and
    declines it, and the result says which code and what the supported alternative is.
    `view: "raw"` is the one this release produces (AD D.1, ADV-208): `raw` is a real member
    of the closed depth vocabulary that is not independently requestable, so refusing it by
    name is a different statement from failing to recognise the word;
  * `ArgumentInvalid` is a **protocol** error. The arguments do not form a call at all - a
    missing `query`, both `thread_id` and `map_id`, a `view` that is not a depth. A client
    that sends one has a bug, and the JSON-RPC error is the layer that says so. It is not a
    D.11 code because D.11's vocabulary is about what happened to a retrieval, and no
    retrieval was attempted.

Getting that split wrong is the failure the work order names: a client that cannot tell
"MailWeave declined" from "MailWeave broke" from "my request was malformed".

**Every parser is total and returns a frozen request object.** Nothing downstream re-reads
the raw argument mapping, so there is exactly one place where a caller's dict becomes typed
values, and exactly one place to look for what this surface accepts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from mailweave.constants import MAX_QUERY_CHARS
from mailweave.envelope.measure import MINIMUM_DISCLOSED_TOKEN_REQUEST
from mailweave.envelope.reasons import RungId
from mailweave.envelope.vocab import Depth, ToolName
from mailweave.envelope.wire import Affordance, ErrorEntry
from mailweave.errors import ErrorCode, MailweaveError, Surface
from mailweave.policy.budget import BudgetRequest
from mailweave.surface.tools import (
    FORCE_RUNG_FAMILIES,
    FORCE_RUNG_IDS,
    SPEC_BY_NAME,
    UNREQUESTABLE_VIEW,
    ToolSpec,
    published_budget_keys,
)


class ArgumentInvalid(MailweaveError):
    """The arguments do not form a call. A JSON-RPC error, never a D.11 code."""


class ToolRefused(MailweaveError):
    """A call this server understood and declines, under a D.11 tool-error code.

    The code is checked against `ERROR_SURFACE` at construction, so an in-band code cannot
    be raised as a refusal: the partition is data, and this class reads it rather than
    re-stating it.
    """

    def __init__(
        self, *, code: ErrorCode, message: str, affordance: Affordance | None = None
    ) -> None:
        from mailweave.errors import ERROR_SURFACE

        if ERROR_SURFACE[code] is not Surface.TOOL_ERROR:
            raise ValueError(
                f"{code.value} is {ERROR_SURFACE[code].value} in D.11 and cannot be raised "
                "as a tool error; an in-band condition travels on a served response"
            )
        super().__init__(message)
        self.code = code
        self.affordance = affordance


# --- rungs ---------------------------------------------------------------------------------

#: AD D.1's four rung families mapped onto the ladder's own ids. `structural` is L4, built
#: in WS-05; the other three name rungs no code in this release contains, which is a fact
#: the *response* declares in band rather than a fact this parser hides by rejecting them.
FAMILY_RUNGS: Final[Mapping[str, RungId]] = {
    "structural": RungId.L4,
    "semantic": RungId.L5,
    "rerank": RungId.L6,
    "recency": RungId.LR,
}

#: The rungs this build actually executes. Read from the lexical ladder plus L4 rather than
#: listed, so a rung added to the ladder is runnable through `force_rungs` the day it exists.
#: The budget cap names this tool accepts. **Read from the published schema, not restated**
#: (round 28, R-MCP-025's second half). Round 27 added `max_hit_threads` here and not to the
#: schema, and this comment already claimed the two were one list while the code kept two -
#: so a client validating arguments against `inputSchema` refused the very `retry_with` a
#: declined search handed back, one layer earlier than before. There is now one list, and it
#: is the schema's; `test_every_budget_cap_this_server_can_mint_validates_against_the_schema`
#: checks the affordance builders against it with a JSON Schema validator rather than only
#: against this parser.
BUDGET_KEYS: Final[tuple[str, ...]] = published_budget_keys()

#: The keys `pool{}` accepts. A.7a's cap table names `max_pool_threads` and
#: `max_pool_messages`, and the affordances this server mints for those two caps carry
#: exactly these spellings - an affordance naming a key the schema lacks is refused by a
#: strict client one layer before this parser (R-MCP-037).
POOL_KEYS: Final[tuple[str, ...]] = ("max_threads", "max_messages")

#: The `pool{}` keys `v0.1` published that this server accepts and does **not** act on.
#:
#: **Why they are back** (2026-09-19). Both were in `v0.1`'s published `inputSchema`, and `v0.1`
#: described the whole block as changing no retrieval because the semantic rung was not built.
#: M2 built the rung and reshaped `pool{}` around it, and these two went out of the schema and
#: into `_refuse`. So a call a `v0.1` client was entitled to make - `pool: {"scope": "auto"}` -
#: started coming back `INVALID_PARAMS`. Plan §9a.2 binds "the v0.1 legacy Gmail path unchanged
#: in names, schemas, defaults and observable behaviour", and accepted-and-declared turning into
#: rejected-as-malformed is an observable change on that path however narrowly the clause is
#: read.
#:
#: **They are a separate tuple from `POOL_KEYS` on purpose.** Folding them in would make them
#: indistinguishable, in the code, from the two keys that do something, and the next reader
#: would have to trace `PoolRequest` to find out which is which. These are accepted, validated
#: against the shapes `v0.1` published, and then dropped: nothing below reads them, and
#: `PoolRequest` has no field for them to reach.
#:
#: **The no-op is declared in the published schema rather than per-response**, in each key's
#: own `description`, so a client reads it before it calls rather than discovering it in a note
#: afterwards. A per-response note would need either a `D.11` code that means "accepted and
#: inert" - and D.11 is closed, "adding a member is a schema change with a version bump" - or a
#: false reuse of `semantic_unavailable`, which was `v0.1`'s note only because the rung did not
#: exist and would be untrue now that it does.
POOL_COMPAT_KEYS: Final[tuple[str, ...]] = ("scope", "window")

#: `v0.1`'s enum for `pool.scope`, carried over verbatim. Validated rather than waved through:
#: `v0.1` refused a value outside this set, and an argument this server accepts more loosely
#: than `v0.1` did is its own compatibility break, in the other direction.
POOL_COMPAT_SCOPES: Final[tuple[str, ...]] = ("auto", "thread", "recency", "participant")


@dataclass(frozen=True)
class PoolRequest:
    """The caller's narrowing of L5's pool. `None` means the published bound applies."""

    max_threads: int | None = None
    max_messages: int | None = None


BUILT_RUNGS: Final[frozenset[RungId]] = frozenset(
    {RungId.L0, RungId.L1, RungId.L1B, RungId.L2, RungId.L3, RungId.L4, RungId.L5, RungId.L6}
)


@dataclass(frozen=True)
class SearchRequest:
    """`mailweave_search`, validated."""

    query: str
    view: Depth
    scan_max_pages: int | None
    budget: BudgetRequest
    disclosed_token_request: int | None
    #: Rungs this run must execute even where the policy would decline them. Only rungs the
    #: lexical ladder contains; a forced rung this build does not have is in `unbuilt`.
    forced: frozenset[RungId] = frozenset()
    #: L2's probe budget, which can only raise the published cap (`max_relax_probes`).
    relax_max_probes: int | None = None
    #: L4's probe budget: how many absent reply parents may be looked up.
    structural_max_probes: int | None = None
    #: L5's pool bounds, each of which can only narrow the published one.
    pool: PoolRequest = field(default_factory=lambda: PoolRequest())
    #: Declarations the response must carry in band because the caller asked for something
    #: this release does not contain. Built here, emitted by `assemble`.
    declarations: tuple[ErrorEntry, ...] = ()
    unbuilt: tuple[RungId, ...] = ()


@dataclass(frozen=True)
class ThreadMapRequest:
    thread_id: str | None
    map_id: str | None
    segment: int | None
    page: int | None = None


@dataclass(frozen=True)
class GetMessagesRequest:
    view: Depth
    message_ids: tuple[str, ...] = ()
    map_id: str | None = None
    positions: tuple[int, ...] = ()


@dataclass(frozen=True)
class GetAttachmentRequest:
    message_id: str
    part_id: str
    mode: str = "metadata"


@dataclass(frozen=True)
class _Reader:
    """One tool's arguments, read with the tool's own name in every error message."""

    spec: ToolSpec
    raw: Mapping[str, Any] = field(default_factory=dict)

    def _refuse(self, detail: str) -> ArgumentInvalid:
        return ArgumentInvalid(f"{self.spec.name.value}: {detail}")

    def unknown_keys(self) -> None:
        properties = self.spec.input_schema["properties"]
        assert isinstance(properties, dict)
        extra = sorted(set(self.raw) - set(properties))
        if extra:
            raise self._refuse(
                f"unknown argument(s) {extra}; this tool accepts {sorted(properties)}"
            )

    def string(self, key: str, *, required: bool = False) -> str | None:
        value = self.raw.get(key)
        if value is None:
            if required:
                raise self._refuse(f"{key} is required")
            return None
        if not isinstance(value, str) or not value.strip():
            raise self._refuse(f"{key} must be a non-empty string")
        return value

    def integer(self, key: str, *, minimum: int) -> int | None:
        value = self.raw.get(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise self._refuse(f"{key} must be an integer")
        if value < minimum:
            raise self._refuse(f"{key} must be >= {minimum}")
        return value

    def mapping(self, key: str) -> Mapping[str, Any]:
        value = self.raw.get(key)
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise self._refuse(f"{key} must be an object")
        return value

    def sequence(self, key: str) -> Sequence[Any] | None:
        value = self.raw.get(key)
        if value is None:
            return None
        if isinstance(value, str) or not isinstance(value, Sequence):
            raise self._refuse(f"{key} must be an array")
        return value


def _view(reader: _Reader, *, allowed: Sequence[Depth], default: Depth) -> Depth:
    """The one place `view` is read, so `raw` is refused identically on every tool.

    The order of the two checks is the whole point. `raw` is tested **before** membership of
    the tool's own enum, because `unsupported_view` is a statement about a depth this
    release declines to serve independently - and a caller who is told "raw is not one of
    [stub, snippet, body_clean, body_full]" has been told the word is unrecognised, which is
    false and sends them looking for a spelling mistake instead of reading D.1.
    """
    if "view" in reader.raw and reader.raw["view"] is None:
        # **`null` is not "absent"** (round 25, R-MCP-011). `view` is required on
        # `mailweave_get_messages` and `null` is not in its enum, but the default was
        # returned for a `None` value and the `"view" not in raw` check that follows passed
        # because the key *is* present - so `{"message_ids": [...], "view": null}` was served
        # at `body_clean`, a depth the caller did not ask for and the one that costs a
        # `messages.get(format=full)`.
        raise reader._refuse(
            "view must be one of "
            f"{', '.join(depth.value for depth in allowed)}; null is not a view, and on "
            "this tool view is required rather than defaulted"
        )
    raw = reader.raw.get("view")
    if raw is None:
        return default
    if not isinstance(raw, str):
        raise reader._refuse("view must be a string")
    if raw == UNREQUESTABLE_VIEW:
        raise ToolRefused(
            code=ErrorCode.UNSUPPORTED_VIEW,
            message=(
                f"view={UNREQUESTABLE_VIEW!r} is not independently requestable in this "
                "release (AD D.1, ADV-208). It remains the declared unabridged form of a "
                "decoding failure and is reachable only that way. The supported views on "
                f"{reader.spec.name.value} are "
                f"{', '.join(depth.value for depth in allowed)}; "
                f"{Depth.BODY_FULL.value} is the escape hatch that returns the unabridged "
                "text of any reduction this server declared."
            ),
        )
    for depth in allowed:
        if raw == depth.value:
            return depth
    raise reader._refuse(
        f"view={raw!r} is not a content depth; this tool accepts "
        f"{[depth.value for depth in allowed]}"
    )


#: Gmail's own operator spelling for each structured constraint (RO F3, `query.operators`).
#: The constraints are folded into the query string rather than carried beside it, so there
#: is exactly one parse of one query and `asked_for` describes the whole of what was asked.
_CONSTRAINT_OPERATORS: Final[Mapping[str, str]] = {
    "from": "from",
    "to": "to",
    "after": "after",
    "before": "before",
    "label": "label",
}


def _fold_constraints(query: str, constraints: Mapping[str, Any], reader: _Reader) -> str:
    parts: list[str] = []
    for key, operator in _CONSTRAINT_OPERATORS.items():
        value = constraints.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise reader._refuse(f"constraints.{key} must be a non-empty string")
        parts.append(f"{operator}:{value.strip()}")
    attachment = constraints.get("has_attachment")
    if attachment is not None:
        if not isinstance(attachment, bool):
            raise reader._refuse("constraints.has_attachment must be a boolean")
        if attachment:
            parts.append("has:attachment")
    unknown = sorted(set(constraints) - set(_CONSTRAINT_OPERATORS) - {"has_attachment"})
    if unknown:
        raise reader._refuse(f"unknown constraint(s) {unknown}")
    return " ".join([query.strip(), *parts]).strip()


def _forced_rungs(reader: _Reader) -> tuple[frozenset[RungId], tuple[RungId, ...]]:
    """`(rungs this build can force, rungs it cannot)`.

    Both spellings are accepted - D.1's four families and the `RungId` values the server's
    own `force_rungs` affordances carry - because an affordance a client copies verbatim
    must be a valid argument. `test_every_affordance_this_server_mints_is_a_valid_argument`
    is the executed form of that sentence.
    """
    values = reader.sequence("force_rungs")
    if values is None:
        return frozenset(), ()
    wanted: set[RungId] = set()
    for value in values:
        if not isinstance(value, str):
            raise reader._refuse("force_rungs entries must be strings")
        if value in FAMILY_RUNGS:
            wanted.add(FAMILY_RUNGS[value])
        elif value in FORCE_RUNG_IDS:
            wanted.add(RungId(value))
        else:
            raise reader._refuse(
                f"force_rungs entry {value!r} names no rung; accepted values are "
                f"{[*FORCE_RUNG_FAMILIES, *FORCE_RUNG_IDS]}"
            )
    return frozenset(wanted & BUILT_RUNGS), tuple(sorted(wanted - BUILT_RUNGS))


def _unbuilt_declaration(rungs: Sequence[RungId], *, why: str) -> ErrorEntry:
    """The in-band note for something a caller asked for that this release does not contain.

    **`errors[]` rather than `not_tried[]`, deliberately.** D.11 lists `semantic_unavailable`
    as surfacing in `not_tried`, and that is where it belongs the day the rung exists and is
    merely unavailable - the entry then carries the `force_rungs` affordance that reaches it,
    which D.11's own remediation column calls "once available". Today there is no call that
    reaches a rung whose runtime was never written, and `NotTriedEntry` requires a blocking
    reason to carry the affordance that would reach it. An entry naming an affordance that
    cannot work is a claim wider than the code, so the fact travels in `errors[]`, which D.2
    names as the carrier of the in-band half of this vocabulary, and carries no affordance
    because there is none to carry.
    """
    return ErrorEntry(
        code=ErrorCode.SEMANTIC_UNAVAILABLE,
        scope=f"rungs:{','.join(rung.value for rung in rungs)}:{why}",
        message_ids=(),
        affordance=None,
    )


def parse_search(raw: Mapping[str, Any]) -> SearchRequest:
    reader = _Reader(SPEC_BY_NAME[ToolName.SEARCH], raw)
    reader.unknown_keys()
    query = reader.string("query", required=True)
    assert query is not None
    if len(query) > MAX_QUERY_CHARS:
        # The schema states the same bound; a parser that trusted the schema would be
        # trusting the caller's client to enforce it. Past ~100k characters the Gmail layer
        # reached an unwrapped `httpx.InvalidURL`, and past that the query was echoed back
        # about four times over in the response (round 25, R-MCP-013).
        raise reader._refuse(
            f"query is {len(query)} characters; this server builds Gmail requests out of at "
            f"most {MAX_QUERY_CHARS}. Narrow the query, or split it into separate calls"
        )
    constraints = reader.mapping("constraints")
    budget = reader.mapping("budget")
    for key in budget:
        if key not in BUDGET_KEYS:
            raise reader._refuse(f"unknown budget key {key!r}; this tool accepts {BUDGET_KEYS}")
    scan = reader.mapping("scan")
    for key in scan:
        if key != "max_pages":
            raise reader._refuse(f"unknown scan key {key!r}")
    relax = reader.mapping("relax")
    structural = reader.mapping("structural")
    for name, block in (("relax", relax), ("structural", structural)):
        for key in block:
            if key != "max_probes":
                raise reader._refuse(f"unknown {name} key {key!r}")
    forced, unbuilt = _forced_rungs(reader)
    pool = reader.mapping("pool")
    for key in pool:
        if key not in POOL_KEYS and key not in POOL_COMPAT_KEYS:
            raise reader._refuse(
                f"unknown pool key {key!r}; this tool accepts {POOL_KEYS + POOL_COMPAT_KEYS}"
            )
    # Validated to `v0.1`'s published shapes, then dropped. See `POOL_COMPAT_KEYS`.
    if "scope" in pool and pool["scope"] not in POOL_COMPAT_SCOPES:
        raise reader._refuse(
            f"pool.scope is one of {POOL_COMPAT_SCOPES}; it was {pool['scope']!r}. The key is "
            "accepted for v0.1 compatibility and selects no scoping rule on this server"
        )
    if "window" in pool and not isinstance(pool["window"], str):
        raise reader._refuse(
            "pool.window is a string. The key is accepted for v0.1 compatibility and narrows "
            "nothing on this server"
        )
    declarations: list[ErrorEntry] = []
    if unbuilt:
        declarations.append(_unbuilt_declaration(unbuilt, why="runtime_not_built"))
    return SearchRequest(
        query=_fold_constraints(query, constraints, reader),
        view=_view(reader, allowed=(Depth.BODY_CLEAN, Depth.SNIPPET), default=Depth.BODY_CLEAN),
        scan_max_pages=_Reader(reader.spec, scan).integer("max_pages", minimum=1),
        budget=BudgetRequest(
            max_quota_units=_Reader(reader.spec, budget).integer("max_quota_units", minimum=1),
            max_api_calls=_Reader(reader.spec, budget).integer("max_api_calls", minimum=1),
            max_http_requests=_Reader(reader.spec, budget).integer("max_http_requests", minimum=1),
            # `max_ms` is AD D.1's spelling and `max_server_ms` is the cap name this
            # server's own affordances carry (`BudgetCapName`). Both are accepted and both
            # mean the same cap; naming one and not the other would have made an affordance
            # this server minted invalid at the tool that minted it.
            max_server_ms=(
                _Reader(reader.spec, budget).integer("max_ms", minimum=1)
                or _Reader(reader.spec, budget).integer("max_server_ms", minimum=1)
            ),
            max_semantic_ms=_Reader(reader.spec, budget).integer("max_semantic_ms", minimum=1),
            max_hit_threads=_Reader(reader.spec, budget).integer("max_hit_threads", minimum=1),
            max_recency_fetch=_Reader(reader.spec, budget).integer("max_recency_fetch", minimum=1),
        ),
        # **A ceiling below what a response costs before it holds anything is not a ceiling.**
        # `MINIMUM_DISCLOSED_TOKEN_REQUEST` is the response-level structure plus one row, so
        # every accepted value is one some response can actually be built inside; below it
        # the ladder would degrade to nothing and the envelope would refuse its own output.
        disclosed_token_request=_Reader(reader.spec, budget).integer(
            "max_disclosed_tokens", minimum=MINIMUM_DISCLOSED_TOKEN_REQUEST
        ),
        forced=forced,
        relax_max_probes=_Reader(reader.spec, relax).integer("max_probes", minimum=1),
        structural_max_probes=_Reader(reader.spec, structural).integer("max_probes", minimum=1),
        # **`max_threads` can only lower, like every other width key** (round 27,
        # R-MCP-025). The published figure is the widest pool this server will read; a
        # caller asking for more gets the published one and a caller asking for fewer gets
        # what they asked for. The threads it does not read are not dropped - they become
        # `withheld` records naming `max_pool_threads`, with the pool-widening call.
        pool=PoolRequest(
            max_threads=_Reader(reader.spec, pool).integer("max_threads", minimum=1),
            max_messages=_Reader(reader.spec, pool).integer("max_messages", minimum=1),
        ),
        declarations=tuple(declarations),
        unbuilt=unbuilt,
    )


def parse_thread_map(raw: Mapping[str, Any]) -> ThreadMapRequest:
    reader = _Reader(SPEC_BY_NAME[ToolName.THREAD_MAP], raw)
    reader.unknown_keys()
    thread_id = reader.string("thread_id")
    map_id = reader.string("map_id")
    if (thread_id is None) == (map_id is None):
        raise reader._refuse(
            "name the thread exactly once: thread_id for a thread you know, or map_id for "
            "a handle this server minted"
        )
    segment = reader.integer("segment", minimum=0)
    page = reader.integer("page", minimum=0)
    if segment is not None and page is not None:
        raise reader._refuse("name one of segment (temporal, AD E.2) or page (sized), not both")
    return ThreadMapRequest(thread_id=thread_id, map_id=map_id, segment=segment, page=page)


def parse_get_messages(raw: Mapping[str, Any]) -> GetMessagesRequest:
    reader = _Reader(SPEC_BY_NAME[ToolName.GET_MESSAGES], raw)
    reader.unknown_keys()
    view = _view(
        reader,
        allowed=(Depth.STUB, Depth.SNIPPET, Depth.BODY_CLEAN, Depth.BODY_FULL),
        default=Depth.BODY_CLEAN,
    )
    if "view" not in raw:
        raise reader._refuse("view is required")
    ids = reader.sequence("message_ids")
    map_id = reader.string("map_id")
    positions = reader.sequence("positions")
    if ids is not None and map_id is not None:
        raise reader._refuse(
            "name the messages once: message_ids, or map_id plus positions - not both"
        )
    if ids is not None:
        if positions is not None:
            raise reader._refuse("positions are read against a map_id, not against message_ids")
        named = tuple(dict.fromkeys(ids))
        if not named or any(not isinstance(one, str) or not one.strip() for one in named):
            raise reader._refuse("message_ids must be a non-empty array of non-empty strings")
        return GetMessagesRequest(view=view, message_ids=named)
    if map_id is None or positions is None:
        raise reader._refuse(
            "name the messages: either message_ids, or map_id together with positions"
        )
    wanted: list[int] = []
    for one in positions:
        if isinstance(one, bool) or not isinstance(one, int) or one < 0:
            raise reader._refuse("positions must be an array of 0-based integers")
        if one not in wanted:
            wanted.append(one)
    if not wanted:
        raise reader._refuse("positions must not be empty")
    return GetMessagesRequest(view=view, map_id=map_id, positions=tuple(wanted))


def parse_get_attachment(raw: Mapping[str, Any]) -> GetAttachmentRequest:
    reader = _Reader(SPEC_BY_NAME[ToolName.GET_ATTACHMENT], raw)
    reader.unknown_keys()
    message_id = reader.string("message_id", required=True)
    assert message_id is not None
    part_id = raw.get("part_id")
    if not isinstance(part_id, str) or not part_id:
        # An empty string is not a part id; accepting one made `part_id: ""` behave as an
        # unknown part rather than as the malformed argument it is (round 25, R-MCP-011).
        raise reader._refuse("part_id is required and must be a non-empty string")
    mode = raw.get("mode", "metadata")
    if mode != "metadata":
        raise reader._refuse(
            f"mode={mode!r} is not offered; mode accepts only 'metadata' in this release "
            "(contract B-04), and attachment bytes are never returned"
        )
    return GetAttachmentRequest(message_id=message_id, part_id=part_id, mode="metadata")
