"""The recovery driver through the shipped MCP call boundary (`evaluation.boundary`).

What a client receives on a decline is not an exception: `server.call` turns
`DisclosureLadderExhausted` into a declared refusal carrying `retry_with`. A driver on the
service seam scored that as the product failing; this driver walks the refusal chain the way
a client does and counts every call - the search, each retry, each expansion - against one
budget. These tests hold the classification, the accounting and the three-way report apart.
"""

from __future__ import annotations

import re

import pytest

from mailweave.surface.arguments import parse_thread_map
from mailweave_harness.evaluation import boundary
from mailweave_harness.evaluation.arms import MAX_RECOVERY_CALLS, MAX_RECOVERY_ROUNDS, Measured
from mailweave_harness.evaluation.boundary import (
    TOTAL_CALLS,
    Declined,
    Raised,
    Served,
    call_tool,
    follow_boundary,
)
from mailweave_harness.seed.corpus import generate
from tests.fixtures import eval_dummy
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.test_mcp_surface_round24 import make_service


@pytest.fixture(scope="module")
def corpus():
    manifest = generate(master_seed=4311, size_profile="sample")
    box, report = eval_dummy.mailbox_of(manifest)
    arm = next(one for one in eval_dummy.dummy_arms(manifest, box) if one.name == "sem-off")
    return manifest, box, arm


def test_the_total_budget_is_the_search_plus_the_follow_up_budget_already_in_force() -> None:
    assert TOTAL_CALLS == 1 + MAX_RECOVERY_CALLS
    assert MAX_RECOVERY_CALLS == MAX_RECOVERY_ROUNDS * 8


# --- classification at the boundary -------------------------------------------------------


def test_a_served_call_a_declined_call_and_a_raise_are_told_apart(corpus) -> None:
    manifest, box, arm = corpus
    served = call_tool(arm.service, "mailweave_thread_map", {"thread_id": "t-t0036"})
    assert isinstance(served, Served)
    assert served.outcome == "answered"
    # An unknown tool leaves the boundary as a JSON-RPC error, which is a raise here.
    raised = call_tool(arm.service, "mailweave_no_such_tool", {"x": 1})
    assert isinstance(raised, Raised)


def _declining_query(corpus) -> tuple[str, Declined]:
    """A question the boundary declines with a retry, found from the corpus's own subjects.

    Long conversations reached by an entity name decline on this corpus; which entity does
    it is a property of the corpus, so it is searched for rather than hard-coded, and the
    test fails loudly if none does.
    """
    manifest, box, arm = corpus
    subjects = [one.subject for one in manifest.answer_key.threads if one.family in {"F13", "F17", "F3"}]
    # **The decline this file is about is the narrowing one.** A budget decline can also come
    # back proposing a different tool - a thread map for one conversation - and that is a
    # scope change, not a narrowing: it carries no `max_hit_threads` to shrink and the walk
    # below is not the thing that follows it. Taking whichever decline came first made the
    # test a statement about which subject the corpus happens to list first, and a corpus
    # change flipped it. The shape is searched for, and the search still fails loudly.
    for subject in subjects[:24]:
        entity = next((re.sub(r"[^A-Za-z]", "", w) for w in subject.split() if w[:1].isupper() and len(w) > 3), None)
        if not entity:
            continue
        question = f"Who carries contractual liability under the {entity} agreement?"
        result = call_tool(arm.service, "mailweave_search", {"query": question})
        if (
            isinstance(result, Declined)
            and result.retry_with is not None
            and result.retry_with.get("tool") == "mailweave_search"
            and result.narrowing
            and result.narrowing.get("dimension") == "max_hit_threads"
        ):
            return question, result
    raise AssertionError(
        "no entity question declined with a max_hit_threads narrowing retry on this corpus"
    )


def test_a_decline_carries_the_retry_a_client_would_receive(corpus) -> None:
    _question, declined = _declining_query(corpus)
    assert declined.code == "budget_exhausted"
    assert declined.retry_with is not None and declined.retry_with["tool"] == "mailweave_search"
    assert declined.narrowing and declined.narrowing["dimension"] == "max_hit_threads"
    assert declined.render_narrowing().startswith("max_hit_threads:")


# --- the walk, and its accounting -------------------------------------------------------------


def test_the_retry_is_followed_and_every_call_is_counted_once(corpus) -> None:
    manifest, box, arm = corpus
    question, declined = _declining_query(corpus)
    reach, merged, trace, first = follow_boundary(
        arm.service, query=question, required=frozenset({"never-this-id"}), quotes={"never-this-id": "x"},
    )
    assert trace.lines[0].startswith("initial")
    assert trace.declined >= 1
    assert trace.recovered, "the retry was never followed to a served response"
    assert first is not None, "no served response anywhere in the chain"
    # Every executed call is in `calls`, the search first, and none beyond the budget.
    assert reach.calls[0] == "mailweave_search"
    assert len(reach.calls) == len(trace.lines) <= TOTAL_CALLS
    assert reach.rounds == len(reach.calls) - 1
    assert reach.stopped in {"call_budget", "hop_budget", "no_new_affordances", "terminal_refusal"}


def test_no_call_is_made_twice_across_the_walk(corpus) -> None:
    manifest, box, arm = corpus
    question, _ = _declining_query(corpus)
    _reach, _merged, trace, _first = follow_boundary(
        arm.service, query=question, required=frozenset({"never-this-id"}), quotes={"never-this-id": "x"},
    )
    seen = set()
    for line in trace.lines:
        key = line.split(" -> ")[0].split(None, 1)[1]  # tool + args, without the kind and the outcome
        assert key not in seen, f"repeated call: {key}"
        seen.add(key)


def test_a_control_walks_only_its_refusal_chain(corpus) -> None:
    """With nothing required there is nothing to expand toward: the driver turns a decline
    into the served response a client would reach, and stops."""
    manifest, box, arm = corpus
    question, _ = _declining_query(corpus)
    reach, _merged, trace, first = follow_boundary(
        arm.service, query=question, required=frozenset(), quotes={},
    )
    assert first is not None
    assert all(line.split()[0] in {"initial", "retry"} for line in trace.lines), trace.lines
    assert reach.state is Measured.MEASURED


# --- the wire, read the way the service-seam readers read an envelope -----------------------


def test_the_wire_readers_agree_with_the_envelope_readers(corpus) -> None:
    from mailweave_harness.evaluation.arms import _content_by_id, _recovery_calls, _surfaced_ids

    manifest, box, arm = corpus
    envelope = arm.service.thread_map(parse_thread_map({"thread_id": "t-t0036"}))
    served = call_tool(arm.service, "mailweave_thread_map", {"thread_id": "t-t0036"})
    assert isinstance(served, Served)
    assert served.surfaced_ids() == _surfaced_ids(envelope)
    assert served.content_by_id() == _content_by_id(envelope)
    wanted = frozenset({"g-t0036-008"})
    wire = [(one["tool"], one["args"]) for one in served.offers(wanted)]
    seam = [(one.tool.value, dict(one.args)) for one in _recovery_calls(envelope, wanted)]
    assert wire == seam


def test_snippets_and_stubs_are_surfaced_and_not_content(corpus) -> None:
    manifest, box, arm = corpus
    served = call_tool(arm.service, "mailweave_get_messages", {"message_ids": ["g-t0036-008"], "view": "snippet"})
    assert isinstance(served, Served)
    assert "g-t0036-008" in served.surfaced_ids()
    assert "g-t0036-008" not in served.content_by_id()
    body = call_tool(arm.service, "mailweave_get_messages", {"message_ids": ["g-t0036-008"], "view": "body_clean"})
    assert isinstance(body, Served)
    assert "g-t0036-008" in body.content_by_id()


def test_delivered_is_measured_on_content_not_on_recovery() -> None:
    """A one-thread mailbox: the search is served, the evidence is a stub row with an
    `unabridged` call, and delivery happens only when the body is in hand."""
    rows = [
        Msg(id=f"b-m{i:03d}", thread_id="b-th", sender="a@team.example",
            subject="Wexford terms" if i == 0 else "Re: Wexford terms",
            body=("Measured tolerance on Wexford exceeded specification at 86.8mm." if i == 6
                  else f"Wexford housekeeping {i}, nothing decided yet."),
            internal_date_ms=epoch_ms(2026, 8, 1) + i * 3_600_000, to=("b@team.example",),
            in_reply_to=(f"<b-m{i - 1:03d}@mail.invalid>" if i else None))
        for i in range(12)
    ]
    service = make_service(SyntheticMailbox(messages=tuple(rows), now_ms=epoch_ms(2026, 9, 3)))
    quote = "Measured tolerance on Wexford exceeded specification at 86.8mm."
    reach, merged, trace, first = follow_boundary(
        service, query="Wexford tolerance", required=frozenset({"b-m006"}), quotes={"b-m006": quote},
    )
    assert first is not None
    assert reach.after_expansion == frozenset({"b-m006"})
    assert reach.stopped == "evidence_in_hand"
    assert not trace.recovered, "nothing declined, so nothing was recovered"
    assert "b-m006" in merged
