"""AD D.11's in-band / tool-error partition, as the only two shapes a tool call can take.

**The partition rule, stated once and read from data everywhere else.**

> Anything that still permits a truthful partial answer is an **in-band field on a
> successful response**. Only a condition that makes the whole call unanswerable is an
> **MCP tool error**.

There is a third thing, and it is not part of that partition at all: a **protocol error**.
An unknown tool, or arguments that do not form a call, never reaches this module - the
server raises `MCPError` and the JSON-RPC layer answers. The three are distinguishable by a
client without reading any prose:

  * *declared result* - `isError: false`, `structuredContent` is a MailWeave response, and
    whatever went partly wrong is a field inside it (`errors[]`, `withheld[]`,
    `budget.clamped`, `budget_caps_hit`, `not_tried[]`);
  * *declared refusal* - `isError: true`, `structuredContent` names one D.11 code, the
    remediation, and the call that would work;
  * *protocol error* - a JSON-RPC error object; no result at all.

Which side a code sits on is **never decided here**. `ERROR_SURFACE` in `mailweave.errors`
is the table, `declined` asserts against it, and a code that moves between surfaces moves
this module with it without an edit. That is what makes the partition a contract rather
than a convention: there is one table, and the two producers both read it.

`Surface.STARTUP_FAILURE` is a third value in that table and it is **not deliverable**.
`auth_profile_underivable` means the server may not serve at all, so turning it into a tool
result would be the server answering a call it has no derived redaction profile for. It
raises here rather than being rendered.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import mcp.types as types

from mailweave.constants import HOST_RESULT_CHAR_CAP
from mailweave.envelope.measure import rendered_chars
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import Role
from mailweave.envelope.wire import Affordance
from mailweave.errors import ERROR_SURFACE, ErrorCode, MailweaveError, Surface
from mailweave.surface.recovery import Narrowing
from mailweave.surface.rendering import Rendered, render

#: What a refusal's `structuredContent` carries. Four keys, constant, and every value a
#: closed-vocabulary token or a string this server wrote - no mail-derived text reaches a
#: refusal, which is what keeps MCP-05's grep gate true of the error path as well as of the
#: tool metadata.
REFUSAL_KEYS: Final[tuple[str, ...]] = (
    "declined",
    "code",
    "remediation",
    "retry_with",
    "narrowing",
    "terminal",
    "recovery",
)

#: What a refusal says a caller can do (2026-09-21). Closed vocabulary, on every refusal.
#: `terminal` answers "has this server's chain ended?"; this answers "and then what?" -
#: the two together are what let a caller tell a final refusal from one that offers nothing.
#: Mirrors `gmail.faults.RecoveryKind` for the Gmail-originated declines and is set
#: directly by the others.
RECOVERY_TOKENS: Final[tuple[str, ...]] = ("narrow", "retry_later", "reauthorise", "none")


class HostCapExceeded(MailweaveError):
    top_thread: str | None = None
    hit_threads: int | None = None
    segmented: bool | None = None
    #: A recovery the raiser has already worked out, for a caller `narrower_call` cannot
    #: narrow on its own.
    #:
    #: **No `mailweave_*` path sets this**, and the decline builder falls back to
    #: `narrower_call` whenever it is `None`, so the four legacy tools behave exactly as
    #: before. It exists for a tool outside that set: `orivra_ask` takes a search's arguments
    #: and adds a block of its own, `narrower_call` branches on the tool name and has no
    #: branch for it, so an oversized `orivra_ask` was declared final and the caller was
    #: handed a refusal with nothing to do about it. The raiser there knows the one fact that
    #: decides the retry - whether the container alone would have fitted - and this is where
    #: it says so.
    recovery: object | None = None

    """The rendered result is larger than the host will accept, in the host's own unit.

    **The last check before the wire** (round 26, R-DISC-033, R-MCP-021). The A.9a ladder
    fits the *estimate* of the rendered size, and the estimate is held above the rendered form
    by a test rather than by hope; this is the measurement of the thing itself, on the object
    the client is handed, and it exists because an estimate that is wrong in the wrong
    direction is exactly how a response reaches a host over its cap.

    Raised rather than served, because there is no third option. The host cuts an over-cap
    result **above the SDK**, outside the protocol, so the server cannot observe the cut, tell
    the caller it happened, or leave a withheld record for what went - which is why
    `truncated_by: null` on such a response is not a bug a later layer repairs. `call` turns
    this into a declared refusal with an executable narrower retry.
    """


def declared_result(envelope: Envelope) -> types.CallToolResult:
    """A served response: the in-band half of the partition, whatever it says went wrong.

    `is_error` is `False` even for a response whose `errors[]` is non-empty, whose
    `withheld[]` is long, or whose budget was clamped. That is the rule, not an oversight: a
    response that carries a truthful partial answer *is* an answer, and flagging it as an
    error would tell a model to retry or give up on a payload it should be reading.

    **And it is measured in the host's unit before it is handed over.** See `HostCapExceeded`.
    """
    mirrored = render(envelope)
    size = rendered_chars(mirrored.structured, mirrored.text)
    if size > HOST_RESULT_CHAR_CAP:
        oversized = HostCapExceeded(
            f"this response renders {size} characters against the host's "
            f"{HOST_RESULT_CHAR_CAP}-character result cap. The A.9a ladder is run against an "
            "estimate of the rendered size and this measurement of the rendered size itself "
            "disagrees with it, so the response is refused rather than handed to a host that "
            "would cut it where nothing can declare the cut"
        )
        # The first source carrying a matched message, for the recovery chain's search-to-map
        # hop (round 29). Sources are emitted in retrieval rank order, so first is top.
        bearing = [
            source.thread_id
            for source in envelope.sources
            if any(row.role is Role.MATCHED for row in source.messages)
        ]
        oversized.top_thread = bearing[0] if bearing else None
        oversized.hit_threads = len(bearing)
        raise oversized
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=mirrored.text)],
        structured_content=mirrored.structured,
        is_error=False,
    )


def declined(
    code: ErrorCode,
    *,
    message: str,
    affordance: Affordance | None = None,
    unanswerable: bool = False,
    narrowing: Narrowing | None = None,
    terminal: bool = False,
    cause: Mapping[str, Any] | None = None,
    recovery: str | None = None,
) -> types.CallToolResult:
    """A refusal: the tool-error half of the partition, named by its D.11 code.

    `recovery` (2026-09-21) is one of `RECOVERY_TOKENS`. Left `None`, it is derived: a
    decline carrying `retry_with` is `narrow`; a terminal one is `none`; one with neither is
    `retry_later`, which is the state that used to be reported as nothing at all. A caller
    that passes it explicitly says something the derivation cannot know - `reauthorise`.

    `cause` (2026-09-15, R-M2-095) is the ladder's own account of a size or emptiness
    refusal - the binding unit and cap, the cost by term, the groups by cap, and its answer at
    every narrower width - as `RefusalCause.as_json` renders it. Machine-readable beside the
    prose, so a client choosing between the retry and its own alternative has the numbers.

    `narrowing` and `terminal` are round 29's recovery contract on the wire. A retry carries
    the dimension it reduces and from what to what, so "every retry reduces a declared
    limiting dimension" is declared rather than asserted. A decline with no retry says
    whether that is because the chain has *ended* - no smaller legal request can return
    evidence - so a caller can tell a final refusal from a refusal that merely offers nothing.

    An MCP *tool* error rather than a JSON-RPC error, because the tool was found and its
    arguments were a call - what failed is the retrieval, and the spec's own guidance is
    that such a failure is reported inside the result so the model can see it and
    self-correct.

    `unanswerable` is the one door out of `ERROR_SURFACE`'s in-band side, and it is narrow on
    purpose (round 25, R-MCP-001). D.11's table says where a code travels **when there is a
    response for it to travel on**: `upstream_rate_limited` and `partial_source_failure` are
    in-band because the rungs that did run still produced truthful evidence. When the same
    condition aborts the whole call there is no evidence and no response - the fault came out
    of the retrieval stack as an exception - and answering `isError: false` with nothing in it
    would be the partition's own lie. The caller passes this flag only from a handler that
    caught the fault *instead of* an envelope, and the message says so.
    """
    surface = ERROR_SURFACE[code]
    if surface is Surface.IN_BAND and not unanswerable:
        raise ValueError(
            f"{code.value} is in-band in D.11: it travels as a field on a served response, "
            "and reporting it as a tool error would tell a caller the call failed when it "
            "returned a truthful partial answer"
        )
    if surface is Surface.IN_BAND:
        joined = message if message.endswith((".", "!", "?")) else f"{message}."
        message = (
            f"{joined} This condition is in-band in AD D.11 and travels on a served "
            "response; this call produced none, so there is no partial answer to carry it."
        )
    if surface is Surface.STARTUP_FAILURE:
        raise ValueError(
            f"{code.value} is a startup failure in D.11: the server does not serve, so "
            "there is no call for it to be the result of"
        )
    if recovery is None:
        recovery = "narrow" if affordance is not None else ("none" if terminal else "retry_later")
    if recovery not in RECOVERY_TOKENS:
        raise ValueError(f"recovery must be one of {RECOVERY_TOKENS}, not {recovery!r}")
    if terminal and recovery == "none":
        message = (
            f"{message} No narrower request this server can offer would return evidence "
            "for this call, so no retry is offered: this is a final refusal, not a retry "
            "that would fail again."
        )
    elif terminal and recovery == "reauthorise":
        message = (
            f"{message} No request this server can make will return evidence until the "
            "owner re-authorises; the instruction above is the whole of the recovery."
        )
    elif recovery == "retry_later":
        message = (
            f"{message} No narrower request would help - the same call may succeed later - "
            "so no retry is offered now. This is not a final refusal."
        )
    structured: dict[str, Any] = {
        "declined": True,
        "code": code.value,
        "remediation": message,
        "retry_with": (None if affordance is None else affordance.model_dump(mode="json")),
        "narrowing": (None if narrowing is None else narrowing.as_json()),
        "terminal": terminal,
        "recovery": recovery,
        "cause": None if cause is None else dict(cause),
    }
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=_refusal_text(structured))],
        structured_content=structured,
        is_error=True,
    )


def _refusal_text(structured: dict[str, Any]) -> str:
    """The text mirror of a refusal, projected from its structured form like any other.

    Same rule as `rendering.text_of`: the text is built out of the mapping the client is
    also receiving, so a refusal cannot say one thing in the structured form and another in
    the text.
    """
    lines = [
        f"declined: {structured['code']}",
        f"remediation: {structured['remediation']}",
        f"recovery: {structured['recovery']}",
    ]
    retry = structured["retry_with"]
    if retry is not None:
        lines.append(f"retry with {retry['tool']} and arguments {retry['args']}")
    return "\n".join(lines)


def refusal_facts(result: types.CallToolResult) -> dict[str, Any]:
    """The refusal a result carries, for a caller (or a test) that wants to branch on it."""
    structured = result.structured_content
    if not result.is_error or not isinstance(structured, dict):
        raise ValueError("this result is not a declared refusal")
    return dict(structured)


def rendered_of(result: types.CallToolResult) -> Rendered:
    """The two forms a result actually carries, paired for a parity check."""
    structured = result.structured_content
    assert isinstance(structured, dict)
    text = "\n".join(block.text for block in result.content if isinstance(block, types.TextContent))
    return Rendered(structured=structured, text=text)
