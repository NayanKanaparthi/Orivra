"""The recovery driver, run through the shipped MCP call boundary.

## Why a second driver, and what it measures that the first could not

`arms.run_case` drives `MailweaveService` directly. That is the right seam for measuring what
one call puts in a reader's hands, and the wrong seam for measuring recovery: when the A.9a
ladder cannot fit a response, the service *raises* `DisclosureLadderExhausted`, while the
surface a client actually talks to - `surface/server.py::call` - turns that raise into a
declared refusal carrying `retry_with`, the failed call with one dimension reduced
(`recovery.narrower_call`, R-MCP-033). A driver on the service seam sees the raise and scores
the product as failed; a client at the boundary receives a next call. The six declines in
the 2026-09-13 diagnostic were scored on the service seam, so the recovery contract that
exists for exactly that decline was never measured.

This driver executes every call - the case's own search, every refusal retry, every
expansion - through `server.call`, reads the wire form a client reads, follows what the wire
offers, and counts every one of those calls against one budget.

## What is counted, and against what

`TOTAL_CALLS = 1 + arms.MAX_RECOVERY_CALLS`: the case's own search is call one, and refusal
retries and expansions share the remaining `MAX_RECOVERY_CALLS`, which is the follow-up budget
the service-seam driver has always had. `arms.MAX_RECOVERY_ROUNDS` bounds depth the same way
it always has, and a refusal retry is one level deeper like any other executed call. Nothing
is raised: a decline chain of four narrowings that then answers has used four of its levels,
and the report says so rather than pretending the retries were free.

## Three things the report keeps apart

  * **delivered** - the required evidence's content is in hand, EP §6.1, after the driver
    followed what it was given. This is the only number that is evidence.
  * **recoverable** - a decline was turned into a served response somewhere in the chain.
    That is the recovery contract working, and it is not evidence of anything else: a
    served response that carries nothing useful is still a served response.
  * **measurable** - the case ended in a named state (`Reach.stopped`) rather than in a
    raise. Every case should be measurable now; that is a property of the driver, not of
    the product, and it must never be read as R-M2-076 being resolved.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Final

import mcp.types as types

from mailweave.envelope.fence import unfence
from mailweave.envelope.vocab import Outcome
from mailweave.surface.server import call
from mailweave.surface.service import MailweaveService
from mailweave_harness.evaluation.arms import (
    _TERMINALS,
    MAX_RECOVERY_CALLS,
    MAX_RECOVERY_ROUNDS,
    Arm,
    CaseRun,
    Measured,
    Reach,
    in_retrieval_order,
)
from mailweave_harness.evaluation.cases import ResolvedCase
from mailweave_harness.seed.metrics import Disclosure, Terminal, disclosed

#: The case's own search plus the follow-up budget the service-seam driver has always had.
TOTAL_CALLS: Final[int] = 1 + MAX_RECOVERY_CALLS

CONTENT_DEPTHS: Final[frozenset[str]] = frozenset({"body_clean", "body_full"})


# --------------------------------------------------------------------------- the wire, read

@dataclass(frozen=True)
class Served:
    """A served response, as the wire carries it. Only what the driver reads."""

    tool: str
    args: dict[str, Any]
    payload: Mapping[str, Any]

    @property
    def nonce(self) -> str:
        return str(self.payload.get("fence_nonce", ""))

    @property
    def outcome(self) -> str:
        report = self.payload.get("retrieval_report") or {}
        return str(report.get("outcome", ""))

    def content_by_id(self) -> dict[str, str]:
        """EP §6.1: only text carried as message content at a body depth."""
        out: dict[str, str] = {}
        for source in self.payload.get("sources", ()):
            for row in source.get("messages", ()):
                content = row.get("content")
                if content is None or row.get("depth") not in CONTENT_DEPTHS:
                    continue
                out[str(row["id"])] = unfence(self.nonce, str(content.get("text", "")))
        return out

    def surfaced_ids(self) -> frozenset[str]:
        ids: set[str] = set()
        for source in self.payload.get("sources", ()):
            ids.update(str(row["id"]) for row in source.get("messages", ()))
            for run in source.get("collapsed_runs", ()):
                ids.update(str(one) for one in run.get("member_ids", ()))
        ids.update(str(record["id"]) for record in self.payload.get("withheld", ()))
        return frozenset(ids)

    def offers(self, wanted: frozenset[str], *, named_reads: bool = True) -> list[dict[str, Any]]:
        """Every executable call this response offers that could carry one of `wanted`.

        The same rule as `arms._recovery_calls`, read off the wire: a row's `unabridged`
        when the row is wanted; a collapsed run's affordance when it holds a wanted id; a
        withheld record's when it is wanted; every withheld group's, not-included source's
        and top-level affordance; and, since the navigation redesign (2026-09-14), a
        continuation that names a wanted id or spans a wanted id's position. Nothing is
        invented - with one stated rule, which is the tool contract rather than an invention:

        **A named id is readable by name.** A collapsed run lists its members' ids so that
        the inventory is inspectable (R-06); the call that reads a listed id is
        `mailweave_get_messages(message_ids=[id], view="body_clean")`, D.1's own contract for
        a message the caller can name, and a client holding the id makes exactly that call. The
        driver makes it for a wanted id it finds in a run's inventory, at the depth evidence is
        scored at (EP §6.1). This is a *known-target* rule: it requires knowing which id is
        wanted, and a driver that has that is measuring reachability of a known target, never
        query-driven discovery - `follow_boundary` is labelled accordingly. `named_reads=False`
        switches the rule off, so a run can be measured with the listed affordances alone and
        the two contributions - the wire's and the rule's - reported apart.
        """
        out: list[dict[str, Any]] = []
        positions_wanted: set[int] = set()
        for source in self.payload.get("sources", ()):
            for row in source.get("messages", ()):
                if str(row["id"]) in wanted and row.get("unabridged"):
                    out.append(dict(row["unabridged"]))
                    positions_wanted.add(int(row.get("position", -1)))
            for run in source.get("collapsed_runs", ()):
                members = [str(one) for one in run.get("member_ids", ())]
                held = wanted & set(members)
                if not held:
                    continue
                if run.get("affordance"):
                    out.append(dict(run["affordance"]))
                start = int((run.get("positions") or (0, 0))[0])
                for one in sorted(held):
                    positions_wanted.add(start + members.index(one))
                    if not named_reads:
                        continue
                    out.append(
                        {
                            "tool": "mailweave_get_messages",
                            "args": {"message_ids": [one], "view": "body_clean"},
                        }
                    )
        for record in self.payload.get("withheld", ()):
            if str(record["id"]) in wanted and record.get("affordance"):
                out.append(dict(record["affordance"]))
        for continuation in self.payload.get("continuations", ()):
            offer = continuation.get("affordance")
            if not offer:
                continue
            named = {str(one) for one in continuation.get("message_ids", ())}
            span = continuation.get("positions")
            spans_wanted = bool(span) and any(
                int(span[0]) <= position <= int(span[1]) for position in positions_wanted
            )
            if (named & wanted) or spans_wanted:
                out.append(dict(offer))
        # **The discovery walk, in retrieval's order** (R-M2-096): the same rule as
        # `arms.in_retrieval_order`, read off the wire's `rank` fields.
        walk: list[tuple[int | None, dict[str, Any]]] = []
        for group in self.payload.get("withheld_groups", ()):
            if group.get("affordance"):
                walk.append((_rank_of(group), dict(group["affordance"])))
        for block in self.payload.get("not_included_sources", ()):
            for entry in block.get("sources", ()):
                if entry.get("affordance"):
                    walk.append((_rank_of(entry), dict(entry["affordance"])))
        out.extend(in_retrieval_order(walk))
        out.extend(dict(one) for one in self.payload.get("affordances", ()))
        return out


def _rank_of(entry: Mapping[str, Any]) -> int | None:
    """The wire's `rank`, or `None` when absent or not an integer: an unranked entry."""
    rank = entry.get("rank")
    return rank if isinstance(rank, int) and not isinstance(rank, bool) else None


@dataclass(frozen=True)
class Declined:
    """A declared refusal, as the wire carries it (`partition.declined`)."""

    tool: str
    args: dict[str, Any]
    code: str
    retry_with: dict[str, Any] | None
    narrowing: Mapping[str, Any] | None
    terminal: bool

    def render_narrowing(self) -> str:
        if not self.narrowing:
            return ""
        return f"{self.narrowing.get('dimension')}:{self.narrowing.get('applied')}->{self.narrowing.get('proposed')}"


@dataclass(frozen=True)
class Raised:
    """A call that left the boundary as an exception. At this seam that is a defect."""

    tool: str
    args: dict[str, Any]
    exception: str


Result = Served | Declined | Raised


def call_tool(service: MailweaveService, tool: str, args: Mapping[str, Any]) -> Result:
    """One call through `server.call`, classified the way a client would classify it."""
    try:
        result: types.CallToolResult = call(service, tool, dict(args))
    except Exception as failure:
        return Raised(tool=tool, args=dict(args), exception=type(failure).__name__)
    structured = result.structured_content
    if not isinstance(structured, dict):
        return Raised(tool=tool, args=dict(args), exception="NoStructuredContent")
    if result.is_error or structured.get("declined"):
        return Declined(
            tool=tool, args=dict(args), code=str(structured.get("code", "")),
            retry_with=(dict(structured["retry_with"]) if structured.get("retry_with") else None),
            narrowing=structured.get("narrowing"),
            terminal=bool(structured.get("terminal", False)),
        )
    return Served(tool=tool, args=dict(args), payload=structured)


def _outcome(raw: str) -> Outcome | None:
    try:
        return Outcome(raw)
    except ValueError:
        return None


def _key(tool: str, args: Mapping[str, Any]) -> str:
    return json.dumps({"t": tool, "a": dict(args)}, sort_keys=True)


# ------------------------------------------------------------------------------ the driver

@dataclass
class Trace:
    """What the driver did, in order, one line per executed call."""

    lines: list[str] = field(default_factory=list)
    served: int = 0
    declined: int = 0
    raised: int = 0
    recovered: bool = False  # a decline was followed by a served response
    terminal_refusals: int = 0

    def add(self, kind: str, result: Result, note: str = "") -> None:
        if isinstance(result, Served):
            self.served += 1
            what = f"served outcome={result.outcome}"
        elif isinstance(result, Declined):
            self.declined += 1
            self.terminal_refusals += int(result.terminal)
            what = f"declined {result.code}" + (f" retry {result.render_narrowing()}" if result.retry_with else " terminal")
        else:
            self.raised += 1
            what = f"raised {result.exception}"
        short = {k: (v if not isinstance(v, list) else f"[{len(v)} ids]") for k, v in result.args.items()}
        self.lines.append(f"{kind:<9} {result.tool.removeprefix('mailweave_'):<12} {short} -> {what}{(' ' + note) if note else ''}")


def follow_boundary(
    service: MailweaveService,
    *,
    query: str,
    required: frozenset[str],
    quotes: Mapping[str, str],
    rounds: int = MAX_RECOVERY_ROUNDS,
    total_calls: int = TOTAL_CALLS,
    named_reads: bool = True,
) -> tuple[Reach, dict[str, str], Trace, Served | None]:
    """The case's search and everything it leads to, through the boundary, under one budget.

    **Known-target reachability.** `required` steers the walk: a row's, a run's, a record's
    and a continuation's offer is followed only when it could carry a required id, while every
    group, not-included and top-level affordance is followed unconditionally (they name no
    ids). So what this measures is whether a client that knows what it wants can reach it
    through what the responses offer, never whether a client would discover it. `named_reads`
    is the inventory rule of `Served.offers`; off, the walk follows listed affordances only.

    Breadth-first over served responses, exactly as `arms.follow`; a declined response
    contributes its `retry_with` as its one offer (an executable call, R-07), so a refusal
    chain is walked the way a client walks it and every step of it is a call. No call is
    made twice. The first served response is returned separately, because the first-response
    measurements are about it.
    """

    def carried(content: Mapping[str, str]) -> frozenset[str]:
        snapshot = Disclosure(content_by_id=dict(content))
        return frozenset(mid for mid in required if disclosed(snapshot, mid, quotes.get(mid, "")))

    trace = Trace()
    seen: set[str] = set()
    merged: dict[str, str] = {}
    surfaced: set[str] = set()
    exceptions: list[str] = []
    executed: list[str] = []
    levels = 1
    stopped = ""
    first_served: Served | None = None
    first_content: dict[str, str] = {}

    initial_key = _key("mailweave_search", {"query": query})
    seen.add(initial_key)
    result = call_tool(service, "mailweave_search", {"query": query})
    executed.append("mailweave_search")
    trace.add("initial", result)
    frontier: list[Result] = [result]
    if isinstance(result, Served):
        first_served = result
        first_content = result.content_by_id()
        merged.update(first_content)
        surfaced |= result.surfaced_ids()
    elif isinstance(result, Raised):
        exceptions.append(f"mailweave_search: {result.exception}")

    first = carried(merged)
    if required and not (required - first):
        stopped = "evidence_in_hand"
        frontier = []
    if not required:
        # A control: the first served response is the measurement; walk the refusal chain
        # only, so a decline becomes the served not-found a client would reach.
        pass

    for _hop in range(rounds):
        if not frontier:
            break
        outstanding = required - carried(merged)
        if required and not outstanding:
            stopped = "evidence_in_hand"
            break
        offers: list[tuple[str, dict[str, Any], str]] = []
        for source in frontier:
            if isinstance(source, Declined):
                if source.retry_with is not None:
                    offers.append((str(source.retry_with["tool"]), dict(source.retry_with["args"]), "retry"))
                continue
            if isinstance(source, Served):
                if not required:
                    continue  # a control follows nothing but its refusal chain
                for one in source.offers(frozenset(outstanding), named_reads=named_reads):
                    offers.append((str(one["tool"]), dict(one["args"]), "expand"))
        fresh = []
        for tool, args, kind in offers:
            key = _key(tool, args)
            if key in seen:
                continue
            seen.add(key)
            fresh.append((tool, args, kind))
        if not fresh:
            stopped = "no_new_affordances" if not any(
                isinstance(one, Declined) and one.terminal for one in frontier) else "terminal_refusal"
            break
        next_frontier: list[Result] = []
        for tool, args, kind in fresh:
            if len(executed) >= total_calls:
                stopped = "call_budget"
                break
            got = call_tool(service, tool, args)
            executed.append(tool)
            trace.add(kind, got)
            if isinstance(got, Raised):
                exceptions.append(f"{tool}: {got.exception}")
                continue
            levels += 1
            if isinstance(got, Declined):
                next_frontier.append(got)
                continue
            if kind == "retry":
                trace.recovered = True
            if first_served is None:
                first_served = got
                first_content = got.content_by_id()
            surfaced |= got.surfaced_ids()
            merged.update(got.content_by_id())
            next_frontier.append(got)
            if required and not (required - carried(merged)):
                stopped = "evidence_in_hand"
                break
        if stopped:
            break
        frontier = next_frontier
    else:
        if not stopped:
            stopped = "hop_budget"
    if not stopped:
        stopped = "no_new_affordances"

    after = carried(merged)
    still_surfaced = frozenset(required & surfaced) - after
    if not required:
        state = Measured.MEASURED if first_served is not None else Measured.FAILED
    elif after:
        state = Measured.MEASURED
    elif exceptions:
        state = Measured.FAILED
    elif still_surfaced or stopped in {"call_budget", "hop_budget"}:
        state = Measured.INCONCLUSIVE
    else:
        state = Measured.MEASURED
    reach = Reach(
        first_response=carried(first_content),
        after_expansion=after,
        surfaced_only=still_surfaced,
        never_named=frozenset(required) - surfaced,
        rounds=len(executed) - 1,
        calls=tuple(executed),
        levels=levels,
        exceptions=tuple(exceptions),
        stopped=stopped,
        state=state,
    )
    return reach, merged, trace, first_served


def run_case_boundary(
    arm: Arm, resolved: ResolvedCase, *, named_reads: bool = True
) -> tuple[CaseRun, Trace]:
    """One case on one arm, through the boundary. The `CaseRun` is scored like any other."""
    if arm.counter is not None:
        arm.counter.reset()
    started = perf_counter()
    required = frozenset(resolved.required)
    reach, _merged, trace, first = follow_boundary(
        arm.service,
        query=resolved.case.query,
        required=required,
        quotes=resolved.required,
        named_reads=named_reads,
    )
    elapsed = (perf_counter() - started) * 1000
    if arm.fetch_log is not None:
        arm.fetch_log.take()
    if first is None:
        # No served response anywhere in the chain: the terminal refusal, or a raise.
        return CaseRun(
            case_id=resolved.case.case_id, family=resolved.case.family, arm=arm.name,
            terminal=Terminal.OTHER, disclosure=Disclosure(content_by_id={}),
            reach=reach, latency_ms=elapsed,
            declined=("terminal refusal: " + "; ".join(trace.lines[-1:])) if trace.declined else
                     ("raised: " + ", ".join(reach.exceptions)),
            embed_calls=0 if arm.counter is None else arm.counter.embed_calls,
            rerank_calls=0 if arm.counter is None else arm.counter.rerank_calls,
            thread_lengths=dict(resolved.thread_lengths),
            state=Measured.FAILED if reach.exceptions else Measured.INCONCLUSIVE,
        ), trace
    content = first.content_by_id()
    payload = json.dumps(first.payload)
    disclosure = Disclosure(
        content_by_id=content,
        surfaced_ids=first.surfaced_ids(),
        tokens_returned=len(payload.split()),
        distractor_tokens=sum(len(t.split()) for m, t in content.items() if m in resolved.distractor_ids),
        evidence_tokens=sum(len(t.split()) for m, t in content.items() if m in required),
    )
    parsed = _outcome(first.outcome)
    terminal = Terminal.OTHER if parsed is None else _TERMINALS.get(parsed, Terminal.OTHER)
    return CaseRun(
        case_id=resolved.case.case_id, family=resolved.case.family, arm=arm.name,
        terminal=terminal, disclosure=disclosure, reach=reach,
        order=tuple(str(row["id"]) for s in first.payload.get("sources", ()) for row in s.get("messages", ())),
        embed_calls=0 if arm.counter is None else arm.counter.embed_calls,
        embed_texts=0 if arm.counter is None else arm.counter.embed_texts,
        rerank_calls=0 if arm.counter is None else arm.counter.rerank_calls,
        rerank_pairs=0 if arm.counter is None else arm.counter.rerank_pairs,
        latency_ms=elapsed,
        thread_lengths=dict(resolved.thread_lengths),
        state=Measured.MEASURED,
    ), trace


__all__ = [
    "CONTENT_DEPTHS", "TOTAL_CALLS", "Declined", "Raised", "Served", "Trace",
    "call_tool", "follow_boundary", "run_case_boundary",
]
