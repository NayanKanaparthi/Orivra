"""Walk one live Gmail question through the four Orivra tools, read-only, and print what it found.

    python tools/dev/gmail_walk.py --client mailweave-server-oauth.json --query "<question>"

**The demonstration the release claims, executed rather than described.** `ask` builds a graph
from one response, `graph` pages the actual relations through the tool boundary (never a
resource - a client with no resource support is the case the tools-first guarantee exists
for), `expand` follows one of the graph's own handles, and `graph` is read again so the
difference is visible as relations rather than as a count.

**Read-only, and structurally so.** It uses the server credential, whose only Gmail scope is
`gmail.readonly`, and it calls exactly four tools, all of them annotated read-only on the
surface. It inserts nothing, deletes nothing, sends nothing and writes no file: everything
goes to stdout, so where the evidence lands is the operator's decision
(`python tools/dev/gmail_walk.py ... > walk.json`), which is `python -m orivra`'s rule and the
reason `tools/guards`' disk-write sweep has nothing to refuse here.

**No message text, no tokens, no secrets.** The record is identities, relation names, origins,
freshness states and counts - the same discipline the equivalence runner keeps. Subjects and
bodies are deliberately absent: this shows that the graph is coherent, not what the mail says.

Exit status is 0 when the walk completed, 1 when it could not - a question whose graph was not
built, or a graph carrying no recoverable handle to follow. Both are honest outcomes about a
particular mailbox and neither is a defect, so the reason is printed rather than raised.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from mailweave.envelope.vocab import ToolName
from mailweave.surface.runtime import announce, start
from orivra.contracts import OrivraToolName
from orivra.registry import ConnectorRegistry
from orivra.surface.server import call
from orivra.surface.service import OrivraService

#: How many recovered messages the content step reads. A bound, not a policy: the point is to
#: show that text is reachable, and reading a forty-message thread to prove it would spend the
#: demonstration's budget on repetition.
MAX_BODIES: Final[int] = 5


def _structured(result: Any, what: str) -> dict[str, Any]:
    if result.is_error:
        raise SystemExit(f"{what} was declined: {result.content}")
    payload = result.structured_content
    if not isinstance(payload, dict):
        raise SystemExit(f"{what} returned no structured content")
    return dict(payload)


def _pages(service: OrivraService, query_id: str, select: str) -> list[dict[str, Any]]:
    """Every page of one selection, following the cursor with the view token it came with.

    The continuation is bound to the view, not to the revision alone: the live access gate can
    change what is disclosed with no merge and no revision bump, and a cursor honoured across
    that would silently skip or repeat evidence. This loop is what a client does, so a stale
    view here is a refusal here rather than a wrong answer downstream.
    """
    items: list[dict[str, Any]] = []
    cursor: int | None = 0
    view: str | None = None
    while cursor is not None:
        arguments: dict[str, Any] = {"query_id": query_id, "select": select}
        if cursor:
            arguments |= {"cursor": cursor, "view": view}
        page = _structured(
            call(service, OrivraToolName.GRAPH.value, arguments), f"orivra_graph[{select}]"
        )
        items.extend(dict(one) for one in page["items"])
        if page["state"] == "oversized":
            # Recoverable and explicit: one item does not fit the response cap, the page says
            # which and why, and the cursor still advances past it. Silence here would be a
            # caller who never learns the item exists.
            items.append({"oversized": page["oversized"]})
        cursor, view = page["next_cursor"], page["view"]
    return items


def _relations(edges: list[Mapping[str, Any]]) -> dict[str, Any]:
    """What the relations are, split the way a reader has to be able to split them."""
    by_relation = Counter(str(one["relation"]) for one in edges if "relation" in one)
    by_origin = Counter(
        f"{one['origin']}/{one['assertion']}" for one in edges if "origin" in one
    )
    return {
        "total": sum(by_relation.values()),
        "by_relation": dict(sorted(by_relation.items())),
        "by_origin_and_assertion": dict(sorted(by_origin.items())),
        "relations": [
            {
                "source": one["source"],
                "relation": one["relation"],
                "target": one["target"],
                "origin": one["origin"],
                "assertion": one["assertion"],
                "method": one["method"],
                "support": [reference.get("native_id") for reference in one["support"]],
                "confidence": one.get("confidence"),
                "freshness": one["freshness"]["state"],
            }
            for one in edges
            if "relation" in one
        ],
    }


def _answer_accounting(answer: Mapping[str, Any]) -> dict[str, Any]:
    """What the answer itself disclosed and left out - the contract's unit, not the graph's.

    The contract does not require a first response to carry evidence. C-01's observable is that
    every id the search returned is **reachable** in the response, and its violation is an id
    that "appears in no form in the response and no `withheld` record names it". R-06 requires
    withheld content to be visible rather than a bare number, and R-07 requires every partiality
    statement to sit next to an executable call. All three are about accounting and
    recoverability; none of them is about the first response being full.

    So the walk records the accounting, and the criteria below ask the contract's question.
    """
    gmail = answer.get("gmail") or {}
    sources = gmail.get("sources") or []
    disclosed = sum(len(one.get("messages") or ()) for one in sources)
    not_included: list[dict[str, Any]] = []
    for block in gmail.get("not_included_sources") or []:
        for source in block.get("sources") or []:
            not_included.append(
                {
                    "thread_id": source.get("thread_id"),
                    "stated_total": source.get("stated_total"),
                    "rank": source.get("rank"),
                    "has_affordance": bool(source.get("affordance")),
                }
            )
    report = gmail.get("retrieval_report") or {}
    asked = gmail.get("asked_for") or {}
    return {
        "disclosed_messages": disclosed,
        "disclosed_threads": len(sources),
        "stated_totals": [one.get("stated_total") for one in sources],
        "not_included_sources": not_included,
        "every_not_included_source_carries_a_call": all(
            one["has_affordance"] for one in not_included
        ),
        "omission_summary": gmail.get("omission"),
        "rungs_executed": report.get("rungs"),
        "term_coverage": asked.get("term_coverage"),
        "constraints_dropped": asked.get("dropped"),
        "partial": gmail.get("partial"),
    }


def _select_branch(answer: Mapping[str, Any], handles: Sequence[str]) -> tuple[str, dict[str, Any]]:
    """Which branch to follow, and why - **the answer's own ranking, never a second one.**

    The first wiring took `handles[0]`, which is the order the omission list happens to be
    written in. Against a real mailbox that selected a thread with 42 messages that the
    question was not about, and the demonstration then spent its one expansion on it.

    `not_included_sources` carries `rank`: "a source A.9a step 7 split off keeps the rank it
    was mapped at, so the entries are written best first". That is the retrieval's own
    judgement of relevance to *this* query, already made, already disclosed. Reading it is not
    a second ranking and introduces no scoring of any kind - which matters, because comparing
    a scored candidate against an unscored one is exactly what ADV-110 forbids.

    Three rules, tried in order, and the one that fired is recorded:

    1. the best-ranked source the answer could not include, when a handle recovers it;
    2. a thread the answer *did* disclose, partially - the question reached it, and the
       handle recovers the rest;
    3. the first recoverable handle, recorded as a fallback so a reader knows relevance did
       not choose this one.
    """
    gmail = answer.get("gmail") or {}
    # handle -> thread id. A handle can name a segment (`gmail/thread/t-1#5-15`), so the id is
    # taken off the prefix rather than assumed to be the whole of it.
    by_thread = _handle_threads(handles)

    ranked: list[tuple[int, str]] = []
    for block in gmail.get("not_included_sources") or []:
        for source in block.get("sources") or []:
            thread = source.get("thread_id")
            rank = source.get("rank")
            if thread is None:
                continue
            ranked.append((rank if rank is not None else 1_000_000, thread))
    for _, thread in sorted(ranked):
        for handle in handles:
            if by_thread.get(handle) == thread:
                return handle, {
                    "handle": handle,
                    "thread_id": thread,
                    "rank": next((r for r, t in sorted(ranked) if t == thread), None),
                    "candidates_considered": [
                        {"thread_id": t, "rank": None if r >= 1_000_000 else r}
                        for r, t in sorted(ranked)[:5]
                    ],
                    "rule": "best_ranked_not_included",
                    "why": (
                        "the answer ranked this source and could not include it; "
                        "not_included_sources is written best-first and this is the best of "
                        "them that a handle recovers"
                    ),
                }

    disclosed = [one.get("thread_id") for one in gmail.get("sources") or []]
    for thread in disclosed:
        for handle in handles:
            if by_thread.get(handle) == thread:
                return handle, {
                    "handle": handle,
                    "thread_id": thread,
                    "rule": "partially_disclosed_thread",
                    "why": (
                        "the answer disclosed part of this thread, so the question reached it; "
                        "the handle recovers the part that did not fit"
                    ),
                }

    return handles[0], {
        "handle": handles[0],
        "thread_id": by_thread.get(handles[0]),
        "rule": "first_recoverable_fallback",
        "why": (
            "no omitted source carried a rank this walk could match to a handle and no "
            "partially disclosed thread had one either, so this is list order rather than "
            "relevance. Read the expansion below as a mechanism demonstration, not as an "
            "answer to the question"
        ),
    }


def _handle_threads(handles: Sequence[str]) -> dict[str, str]:
    """Each handle's thread id, without inventing one for a handle that has none.

    A handle may name a segment of a thread - `gmail/thread/t-1#5-15` - so the id is the part
    before the fragment rather than the whole of the suffix.
    """
    out: dict[str, str] = {}
    for handle in handles:
        if handle.startswith("gmail/thread/"):
            out[handle] = handle.removeprefix("gmail/thread/").split("#", 1)[0]
    return out


def walk(
    service: OrivraService,
    query: str,
    *,
    view: str,
    calls: Counter[str] | None = None,
    round_index: int = 1,
) -> tuple[dict[str, Any], int]:
    """ask -> inspect -> expand -> inspect, through the shipped surface every time.

    `calls` is the tally `_counting` installed, if one was. It is read **per step** rather
    than per walk, because the two thread reads in a round are different things: the answer's
    retrieval reads a thread and the expansion reads one, only the second has a cache seat,
    and a single total for the round would credit the cache with a call it never avoided.
    """
    record: dict[str, Any] = {"kind": "orivra-gmail-walk", "query": query, "view": view}

    def since_last() -> dict[str, int]:
        if calls is None:
            return {}
        taken = dict(sorted(calls.items()))
        calls.clear()
        return taken

    since_last()

    answer = _structured(
        call(service, OrivraToolName.ASK.value, {"query": query, "view": view, "graph": True}),
        "orivra_ask",
    )
    query_id = answer["query_id"]
    graph = answer.get("graph", {})
    record["step_1_ask"] = {
        "query_id": query_id,
        "graph_built": bool(graph.get("counts")),
        # **Built and holds evidence are two questions.** A graph of one thread node is built
        # and carries nothing a relation can rest on; the live Harbor run reported
        # `nodes: 1` and the next call returned an empty page.
        "holds_evidence": graph.get("holds_evidence"),
        "why_no_evidence": graph.get("why_no_evidence"),
        "routing": graph.get("routing"),
        "counts": graph.get("counts"),
        "unresolved_links": graph.get("unresolved_links", []),
        "resource_link": answer.get("resource_link"),
        # **The answer's own accounting, beside the graph's.** The graph counts say what the
        # graph holds; these say what the *answer* disclosed and what it left out, which is
        # what the contract's reachability rule (§4 I-1, R-06, R-07) is actually about. Counts,
        # identities and ranks only.
        "answer": _answer_accounting(answer),
        "gmail_calls": since_last(),
    }
    if not graph.get("counts"):
        record["stopped"] = (
            "this question routed to no graph, so there is nothing to inspect or expand. "
            "The routing line above says why"
        )
        return record, 1

    before = _pages(service, query_id, "edges")
    record["step_2_inspect"] = {
        "nodes": _pages(service, query_id, "nodes"),
        "edges": _relations(before),
        "omissions": _pages(service, query_id, "omissions"),
        "gmail_calls": since_last(),
    }

    handles = [
        one["what"]
        for one in record["step_2_inspect"]["omissions"]
        if isinstance(one, dict) and one.get("recover")
    ]
    if not handles:
        record["stopped"] = (
            "this graph left nothing out that it can get back, so there is no handle to "
            "follow. A complete answer is a legitimate outcome, not a failed walk"
        )
        return record, 1

    chosen, selection = _select_branch(answer, handles)
    record["step_3_selection"] = selection

    expanded = _structured(
        call(
            service,
            OrivraToolName.EXPAND.value,
            {"query_id": query_id, "handle": chosen},
        ),
        "orivra_expand",
    )
    record["step_3_expand"] = {
        "handle": chosen,
        "executed": expanded["executed"],
        "revision": expanded["revision"],
        "added": {
            # **`shed` and `detail` travel.** Dropping them is what turned a delta the tool
            # explicitly said it had shed into an empty projection with no reason, which a
            # reader of the Harbor record could only read as "the expansion recovered nothing".
            "shed": expanded["added"].get("shed"),
            "counts": expanded["added"].get("counts"),
            "detail": expanded["added"].get("detail"),
            "nodes": [one["node_id"] for one in expanded["added"]["nodes"]],
            "edges": _relations(expanded["added"]["edges"])["by_relation"],
            "already_held": expanded["added"]["already_held"],
        },
        "graph": expanded["graph"],
        "narrowed_by_live_check": expanded["narrowed_by_live_check"],
        "text_not_read": expanded.get("text_not_read"),
        "unresolved_links": expanded.get("unresolved_links", []),
        # Carried, not summarised. `consulted` distinguishes a cache that was never asked from
        # one that was asked and missed, and only the tool knows which.
        "cache": expanded.get("cache"),
        "disclosure": expanded.get("disclosure"),
        # **The number the structure cache is about.** `threads.get` and no `history.list`
        # is a source read; `history.list` and no `threads.get` is an entry served after a
        # change-feed walk found nothing. Both together mean the walk saw a change, or could
        # not finish looking, and sent this call back to the source - which is the correct
        # outcome and not a cache failure.
        "gmail_calls": since_last(),
    }

    after = _pages(service, query_id, "edges")
    was = {(one["source"], one["relation"], one["target"]) for one in before if "relation" in one}
    now = {(one["source"], one["relation"], one["target"]) for one in after if "relation" in one}
    record["step_4_inspect_again"] = {
        "edges": _relations(after),
        "gained": sorted(f"{a} -{r}-> {b}" for a, r, b in now - was),
        "lost": sorted(f"{a} -{r}-> {b}" for a, r, b in was - now),
        "omissions": _pages(service, query_id, "omissions"),
        "gmail_calls": since_last(),
    }
    if was - now:
        record["step_4_inspect_again"]["note"] = (
            "relations present before the expansion are absent after it. A merge only adds, "
            "so this is the live access gate narrowing what may be disclosed - which is "
            "checked on every page rather than once per graph"
        )

    record["step_5_content"] = _read_recovered_bodies(service, record, view=view, query=query)
    record["step_5_content"]["gmail_calls"] = since_last()
    record["criteria"] = _criteria(record, round_index=round_index)
    return record, 0


def _read_recovered_bodies(
    service: OrivraService, record: Mapping[str, Any], *, view: str, query: str
) -> dict[str, Any]:
    """Read the bodies of the messages the expansion recovered, through the shipped surface.

    **A thread map recovers a branch's shape, not its text.** Every row it returns is a `stub`,
    which is why `orivra_expand` reports them under `text_not_read` and draws no `obs.said.*`
    relation for them. A walk that stopped there ended on structural edges - who replied to
    whom - and called that a demonstration. It is not one: "message A replied to message B"
    does not answer a question, and a reader cannot check an answer that no text supports.

    `mailweave_get_messages` is one of the four legacy tools on this same surface, read-only
    like the rest, and it takes message ids and a depth. So the content is one call away and
    the call is inside the boundary being demonstrated.

    **Ids only, never text, leave this function.** The record stays pasteable into a review.
    """
    unread = (record.get("step_3_expand", {}) or {}).get("text_not_read") or {}
    ids = [
        one.removeprefix("gmail/message/")
        for one in unread.get("nodes", ())
        if one.startswith("gmail/message/")
    ]
    if not ids:
        return {
            "requested": [],
            "reached_content": False,
            "query_term_overlap": None,
            "why": (
                "the expansion reported no unread rows, so there was nothing to read. Either "
                "the graph already held these bodies or the expansion recovered nothing"
            ),
        }
    # **Thread order, and the record says so.** `text_not_read` lists the recovered rows in the
    # order the thread map returned them, so this reads the branch's first few. That is
    # arbitrary with respect to the question - in a fourteen-message thread the sentence that
    # names a fix is as likely to be last as first. It is left arbitrary rather than "improved"
    # because choosing which messages answer a question is ranking, this walk does not rank,
    # and a selection rule invented here would be a second ranker disagreeing with the one that
    # shipped. `query_term_overlap` below is a hint about a bad draw and nothing more: it is
    # informational, graded by nothing, and Path B is where a client that can read is asked
    # whether the right messages were reached.
    wanted = ids[:MAX_BODIES]
    result = call(
        service, ToolName.GET_MESSAGES.value, {"message_ids": wanted, "view": view}
    )
    if result.is_error:
        return {
            "requested": wanted,
            "reached_content": False,
            "query_term_overlap": None,
            "why": f"mailweave_get_messages declined: {result.content}",
        }
    payload = result.structured_content or {}
    with_text = 0
    depths: Counter[str] = Counter()
    coverage: dict[str, list[str]] = {}
    for source in payload.get("sources") or []:
        for message in source.get("messages") or []:
            depths[str(message.get("depth"))] += 1
            coverage[str(message.get("id"))] = list(message.get("constraint_coverage") or ())
            content = message.get("content") or {}
            if isinstance(content, Mapping) and content.get("text"):
                with_text += 1
    return {
        "requested": wanted,
        "returned": sum(depths.values()),
        "depths": dict(sorted(depths.items())),
        "messages_with_text": with_text,
        "reached_content": with_text > 0,
        "selection": {
            "rule": "thread_order",
            "bound": MAX_BODIES,
            "of_recovered": len(ids),
            "why": (
                "the first rows the thread map returned, capped. Arbitrary with respect to the "
                "question by design: choosing which messages answer it is ranking, and this "
                "walk does not rank. `query_term_overlap` may hint at a bad draw; it is "
                "informational and nothing is graded on it"
            ),
        },
        "query_term_overlap": _query_term_overlap(query, payload),
        "server_constraint_coverage": coverage,
        "why": (
            "read through mailweave_get_messages on the same surface, at the walk's own view. "
            "Counts and depths only: no message text is in this record"
        ),
    }


#: Words that carry no discriminating power in a question. Deliberately tiny: a long stoplist
#: is a second query analyser, and this is a check on the walk rather than a retrieval stage.
STOPWORDS: frozenset[str] = frozenset(
    {
        "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
        "the", "this", "that", "these", "those", "and", "but", "for", "with",
        "from", "into", "about", "was", "were", "been", "being", "does", "did",
        "have", "has", "had", "its", "it", "them", "they", "you", "your", "our",
    }
)


def _query_term_overlap(query: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """How many of the question's longer words appear in the retrieved text. **Informational.**

    **This is a measurement, not a finding, and nothing here grades the walk on it.** It was a
    criterion for one revision and that was wrong twice over. It cannot establish relevance: a
    thread can repeat "Harbor", "export" and "mismatch" in every message and never say what
    caused either. And it cannot establish correctness: the words in an answer are not the
    answer. Worse, it failed on function words the question happened to contain - "exact",
    "resolved" - which say nothing about whether the right messages were read, so a correct
    walk could be marked undemonstrated because a mail said "fixed" instead of "resolved".

    So the numbers are kept and the verdict is dropped. They are worth keeping because they are
    cheap and they occasionally say something a reader can act on - every term missing from a
    fourteen-message thread is a hint that the five rows read were the wrong five - but that is
    a hint to a person, not a judgement by this script.

    **Deciding whether these messages state the cause and the fix is reading.** This server
    makes zero generative calls by construction, so the walk does not attempt it and does not
    approximate it. Path B in `docs/GMAIL_PREVIEW_DEMO.md` is where that question is put to a
    client that can read.

    Matching is lowercase substring on tokens of four characters or more. Crude on purpose: a
    smarter matcher would be a second query analyser whose disagreements with the first would
    become the subject instead of the demonstration.
    """
    terms = sorted(
        {
            token
            for token in re.findall(r"[a-z0-9]+", query.lower())
            if len(token) >= 4 and token not in STOPWORDS
        }
    )
    per_term: dict[str, int] = dict.fromkeys(terms, 0)
    per_message: dict[str, int] = {}
    for source in payload.get("sources") or []:
        for message in source.get("messages") or []:
            content = message.get("content") or {}
            text = content.get("text") if isinstance(content, Mapping) else None
            if not text:
                continue
            lowered = str(text).lower()
            hits = [term for term in terms if term in lowered]
            per_message[str(message.get("id"))] = len(hits)
            for term in hits:
                per_term[term] += 1
    found = [term for term, count in per_term.items() if count]
    best = max(per_message.values(), default=0)
    return {
        "informational": True,
        "terms": terms,
        "messages_per_term": per_term,
        "terms_found": found,
        "terms_missing": [term for term in terms if term not in found],
        "best_single_message_terms": best,
        "caveat": (
            "word overlap between the question and the retrieved text. It establishes neither "
            "relevance nor correctness, it is graded by nothing, and a missing word is often "
            "just a synonym - 'resolved' against a mail that says 'fixed'. Whether these "
            "messages state the cause and the exact fix is a reading of them, which this walk "
            "does not make and does not claim"
        ),
    }


def _criteria(record: Mapping[str, Any], *, round_index: int = 1) -> dict[str, Any]:
    """What the walk set out to demonstrate, each one answered yes or no.

    **Running is not demonstrating.** The Harbor run exited 0 with a graph that disclosed no
    node, a delta that was silently shed, a cache that was never consulted and a branch chosen
    by list order - and nothing in its output said any of that had gone wrong. A demonstration
    that cannot fail cannot be evidence, so every criterion is stated and answered here, and
    `main` exits non-zero when one of them is not met even though every call succeeded.
    """
    ask = record.get("step_1_ask", {})
    inspect = record.get("step_2_inspect", {})
    selection = record.get("step_3_selection", {})
    expand = record.get("step_3_expand", {})
    again = record.get("step_4_inspect_again", {})

    cache = expand.get("cache") or {}
    accounting = ask.get("answer") or {}
    content = record.get("step_5_content", {})
    overlap = content.get("query_term_overlap") or {}
    relations = (inspect.get("edges", {}).get("relations") or []) + (
        again.get("edges", {}).get("relations") or []
    )
    omissions = inspect.get("omissions") or []
    recoverable = [one for one in omissions if isinstance(one, dict) and one.get("recover")]
    checks = {
        # **The contract's rule, not a stricter one invented here.** C-01's observable is that
        # every id the search returned is *reachable* in the response; its violation is an id
        # that appears in no form and that no record names. R-07 requires each partiality
        # statement to sit next to an executable call. Neither requires the first response to
        # carry evidence, so neither does this. What it does require is that the way back
        # exists and works, which is what is checked: records carry calls, and following one
        # produced nodes.
        "evidence_reachable": {
            "met": bool(recoverable)
            and bool(expand.get("added", {}).get("nodes") or expand.get("added", {}).get("counts"))
            and accounting.get("every_not_included_source_carries_a_call", True),
            "why": (
                "every source the answer left out is named by a record carrying an executable "
                "call, and following one recovered nodes (contract C-01 reachability, R-07)"
            ),
        },
        "relations_visible_through_tools": {
            "met": bool(relations),
            "why": (
                "orivra_graph returned actual relations, not counts, with no resource read - "
                "at some point in the walk, which is what progressive disclosure means"
            ),
        },
        "branch_chosen_by_relevance": {
            "met": selection.get("rule") in {
                "best_ranked_not_included",
                "partially_disclosed_thread",
            },
            "why": "the branch followed was the answer's own best-ranked one, not list order",
        },
        "expansion_delta_accounted": {
            "met": bool(expand.get("added", {}).get("nodes"))
            or bool(expand.get("added", {}).get("shed")),
            "why": (
                "the expansion either carried its delta or said it was shed, and where to "
                "read it instead"
            ),
        },
        "graph_grew": {
            "met": bool(again.get("gained")),
            "why": "the second inspection shows relations the first did not",
        },
        # **Consulted and answered coherently - never "did it hit".** A fresh fetch after a
        # change feed that saw a change, ran out of pages or found an expired watermark is the
        # cache working exactly as designed; failing the demonstration for it would be reading
        # a safe fallback as a defect. Reuse is reported under `observations.cache_reuse`,
        # where it belongs: it is a performance fact, not a correctness one.
        "cache_behaved_correctly": {
            "met": bool(cache.get("consulted"))
            and cache.get("outcome") in {"hit", "miss", "expired", "unverified"}
            and (cache.get("outcome") != "hit" or cache.get("reason") == "unchanged"),
            "why": (
                "the structure cache was consulted and gave a defined outcome, and it served "
                "an entry only on a conclusive, unchanged change-feed walk. A fresh fetch on "
                "any other reason is correct behaviour, not a failure"
            ),
        },
        "reached_message_content": {
            "met": bool(content.get("reached_content")),
            "why": "the walk read the recovered messages' bodies, not only their structure",
        },
    }
    # Reported, never blocking: the contract permits an empty first response provided the
    # accounting and the affordances are there. Losing sight of it would be the other error, so
    # it stays in the record as an observation with the numbers beside it.
    observations = {
        "first_response_held_evidence": bool(ask.get("holds_evidence")),
        "first_response_disclosed_messages": accounting.get("disclosed_messages"),
        "sources_left_out": len(accounting.get("not_included_sources") or []),
        "recoverable_omissions": len(recoverable),
        # **Reuse, reported and never graded.** Whether an entry was served is a fact about
        # this process's history - round 1 has nothing to reuse by construction - and a fresh
        # fetch on a change, an inconclusive walk or an expired watermark is the safe path
        # working. `cache_behaved_correctly` above is the criterion; this is the number.
        "cache_reuse": {
            "served_from_cache": cache.get("outcome") == "hit",
            "reason": cache.get("reason"),
            "rebaselined": cache.get("rebaselined"),
            "round": round_index,
            "why_not_a_criterion": (
                "a safe fresh fetch is not a wrong answer. Reuse depends on whether anything "
                "was cached yet and on what the change feed found, neither of which is a "
                "statement about whether this walk worked"
            ),
        },
        "query_term_overlap": overlap,
        "why_this_is_not_a_criterion": (
            "the contract requires reachability with an executable call, not a full first "
            "response: C-01's violation is an id that appears in no form and that no record "
            "names, and R-07's requirement is that every partiality statement carries the call "
            "that retrieves it. An empty first graph whose omissions all carry working handles "
            "is progressive disclosure (C-06), so it is recorded here rather than failed above"
        ),
    }
    unmet = sorted(
        name
        for name, one in checks.items()
        if one.get("applicable", True) and not one["met"]
    )
    return {
        "checks": checks,
        "observations": observations,
        "unmet": unmet,
        "demonstrated": not unmet,
        "note": (
            "Every call in this walk succeeded; that is execution. These are the demonstration "
            "criteria, which are a different question. Structural edges are not counted as an "
            "answer: `reached_message_content` is the criterion that asks whether any text "
            "supports what the graph says."
        ),
    }


def _counting(service: Any) -> Counter[str]:
    """Count the two Gmail calls the structure cache is about, and nothing else.

    **Read-only and additive**: each wrapper forwards to the real method and increments a
    tally. Nothing is suppressed, substituted or replayed, so a counted run makes exactly the
    calls an uncounted one makes - which is the only way the numbers below mean anything.

    It wraps the *client opener* rather than the adapter, so what is counted is what reached
    Gmail rather than what this process intended to send.
    """
    calls: Counter[str] = Counter()
    opener: Callable[[], Any] = service.open_client

    def open_client() -> Any:
        client = opener()
        fetch = client.get_thread
        probe = client.liveness_of_threads

        def get_thread(*args: Any, **kwargs: Any) -> Any:
            calls["threads.get"] += 1
            return fetch(*args, **kwargs)

        def liveness_of_threads(*args: Any, **kwargs: Any) -> Any:
            calls["history.list"] += 1
            return probe(*args, **kwargs)

        client.get_thread = get_thread
        client.liveness_of_threads = liveness_of_threads
        return client

    service.open_client = open_client
    return calls


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python tools/dev/gmail_walk.py",
        description=(
            "Walk one live Gmail question through orivra_ask, orivra_graph, orivra_expand "
            "and orivra_graph again. Read-only; prints identities, never message text."
        ),
    )
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--query", required=True)
    parser.add_argument("--view", default="body_clean", choices=["stub", "snippet", "body_clean"])
    parser.add_argument(
        "--rounds",
        type=int,
        default=1,
        help=(
            "ask the same question this many times in one process. The structure cache lives "
            "for the life of a process, so a second round is what makes its reuse visible: "
            "round 1's expansion reads the thread, round 2's walks the change feed instead"
        ),
    )
    arguments = parser.parse_args(argv)

    if arguments.rounds < 1:
        parser.error("--rounds is at least 1")

    runtime = start(config_path=arguments.config, client_path=arguments.client)
    try:
        announce(runtime.report)
        calls = _counting(runtime.service)
        # **One registry, and therefore one cache, across the rounds.** Building a second
        # would be building a second cache, and every round would read cold - which would
        # measure the construction rather than the caching.
        service = OrivraService(registry=ConnectorRegistry.from_runtime(runtime))
        rounds: list[dict[str, Any]] = []
        record: dict[str, Any] = {}
        status = 0
        for index in range(arguments.rounds):
            record, status = walk(
                service,
                arguments.query,
                view=arguments.view,
                calls=calls,
                round_index=index + 1,
            )
            expansion = record.get("step_3_expand", {}).get("gmail_calls", {})
            criteria = record.get("criteria", {})
            rounds.append(
                {
                    "round": index + 1,
                    "expansion_gmail_calls": expansion,
                    "branch": record.get("step_3_selection", {}),
                    "cache": (record.get("step_3_expand", {}) or {}).get("cache"),
                    "criteria": criteria,
                    "stopped": record.get("stopped"),
                }
            )
            branch = record.get("step_3_selection", {})
            print(
                f"round {index + 1}: expansion made {expansion} | "
                f"branch {branch.get('thread_id')} by {branch.get('rule')} | "
                f"unmet {criteria.get('unmet', ['(not evaluated)'])}",
                file=sys.stderr,
            )
    finally:
        runtime.close()
    demonstrated = all(one.get("criteria", {}).get("demonstrated") for one in rounds)
    if arguments.rounds > 1:
        record["rounds"] = rounds
        record["what_the_rounds_show"] = (
            "the structure cache lives for the life of this process, and these counts are "
            "the expansion's alone - the answer's own thread read is step 1's and has no "
            "cache seat. A round whose expansion shows `history.list` and no `threads.get` "
            "was served from the cache, "
            "revalidated by a change-feed walk that reads a different resource from the one "
            "the entry holds. A round showing `threads.get` read the source, either because "
            "nothing was cached yet or because the walk saw a change or could not finish "
            "looking - none of which serve the entry"
        )
    if "stopped" in record:
        print(record["stopped"], file=sys.stderr)
    print(json.dumps(record, indent=2, sort_keys=True))
    if status:
        return status
    # **Execution and demonstration are separate answers and get separate exit codes.** Every
    # call can succeed while the thing the walk exists to show did not happen - which is what
    # the Harbor run did, exiting 0 on a graph that disclosed nothing. 0 means demonstrated;
    # 2 means it ran and the criteria were not met, with `criteria.unmet` naming which.
    if not demonstrated:
        unmet = sorted(
            {name for one in rounds for name in one.get("criteria", {}).get("unmet", ())}
        )
        print(
            f"the walk completed and the demonstration criteria were NOT met: {unmet}. "
            "See `criteria` in the record for what each one asks",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
