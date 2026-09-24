"""H2's matched comparison: the cross-encoder on, and genuinely bypassed, with nothing else moved.

**Why this file exists.** H2 is *"bounded reranking improves top-of-list precision on ambiguous
families without changing exact-match families"*. Until 2026-09-16 the harness had no pair that
could measure it: `ArmSpec.semantic` turned stage-A embedding **and** D.7's second tier off
together, so `full` against `sem-off` removed two things at once and could attribute nothing to
reranking. `no-rerank` is the missing arm - embedding on, cross-encoder absent - and this file
holds the three properties that make the pair worth running:

  * **both arms embed, and only one reranks.** Proved twice over: by counting what the backend
    seam was actually asked for, and by the response's own `semantic_cost` block, which is what
    a reader of a campaign record has. A test that trusted only the second would be checking a
    self-reported field; one that trusted only the first would not establish that the response
    says what happened.
  * **the bypass is an absence, not a substitute.** No backend is acquired for the rerank, no
    pair is scored, and **no score is invented**: the ordering that stands is D.7's registered
    first tier, `mailweave/mechanical-v1`, exactly as on any response whose gate declined.
  * **RANK-01's prohibitions are identical on both arms.** An `rfc822msgid:` route, an
    `exact_signal_match` and a single hit each stop the tier on the arm that *has* it, so those
    families cannot contribute a difference to H2 - which is the second half of the hypothesis,
    "without changing exact-match families", made checkable.

Corpus-independent throughout: generated mailboxes, no diagnostic case, no expected evidence id.
Nothing here is a held-out acceptance question and nothing here scores retrieval quality; H2's
*answer* comes from an independently authored case file, and this file is about whether the
instrument can carry it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from mailweave.envelope.reasons import RungId
from mailweave.ranking.gate import RerankProhibition
from mailweave.ranking.mechanical import MECHANICAL_METHOD
from mailweave.retrieval.ranking import RankingState
from mailweave.semantic.interface import BackendRegistry
from mailweave.surface.arguments import parse_search
from mailweave.surface.service import MailweaveService
from mailweave_harness.evaluation.arms import (
    FULL,
    HYPOTHESIS_PAIRS,
    NO_RERANK,
    SPECS,
    CountingBackend,
)
from tests.fixtures.eval_dummy import _WordBackend
from tests.fixtures.mailbox import Msg, SyntheticMailbox
from tests.test_semantic_rung import make_service, measured_profile

#: Two terms, so `term_coverage` can fall below one and D.7's partial-coverage signal is
#: reachable; spread over several threads, so the thread-concentration signal is too.
QUERY = "quarterly plinth"
VOCABULARY = sorted({"quarterly", "plinth", "roster", "depot", "cadence", "figure", "review"})


def _ambiguous_mailbox() -> SyntheticMailbox:
    """Several threads that each partially match, which is what D.7's gate is for.

    Deliberately ambiguous rather than answerable: this file measures whether the tier runs and
    what the response says about it, never whether the right message came back.
    """
    now = datetime.now(UTC)
    rows: list[Msg] = []
    for thread in range(4):
        for index in range(3):
            stamp = now - timedelta(days=3 + thread, minutes=60 - index)
            body = (
                f"the quarterly figure on the depot {thread}"
                if index == 1
                else f"plinth roster cadence note {thread}{index}"
            )
            rows.append(
                Msg(
                    id=f"t{thread}-m{index}",
                    thread_id=f"t{thread}",
                    sender="bo@team.example",
                    subject="cadence review",
                    body=body,
                    internal_date_ms=int(stamp.timestamp() * 1000),
                    to=("cy@team.example",),
                    in_reply_to=None if index == 0 else f"<t{thread}-m{index - 1}@mail.invalid>",
                )
            )
    return SyntheticMailbox(messages=tuple(rows), now_ms=int(now.timestamp() * 1000))


def _one_hit_mailbox() -> SyntheticMailbox:
    """A single message carrying the term, for RANK-01's `hit_count_is_one`."""
    now = datetime.now(UTC)
    return SyntheticMailbox(
        messages=(
            Msg(
                id="solo-m0",
                thread_id="solo",
                sender="bo@team.example",
                subject="cadence review",
                body="the quarterly plinth was signed off",
                internal_date_ms=int((now - timedelta(days=2)).timestamp() * 1000),
                to=("cy@team.example",),
            ),
        ),
        now_ms=int(now.timestamp() * 1000),
    )


class _Pair:
    """The two arms, built through one construction so only the factor differs.

    The counter is per arm and wraps the *same* deterministic backend, so the shortlist either
    arm builds is the same shortlist: `no-rerank` is `full` with D.7's second tier taken away,
    not a different retriever.
    """

    def __init__(self, box: SyntheticMailbox) -> None:
        self.box = box
        self.counters: dict[str, CountingBackend] = {}
        self.services: dict[str, MailweaveService] = {}
        for spec in (FULL, NO_RERANK):
            counter = CountingBackend(_WordBackend(VOCABULARY))
            registry = BackendRegistry()
            registry.register("dummy", lambda made=counter: made, default=True)
            self.counters[spec.name] = counter
            self.services[spec.name] = make_service(
                box, registry=registry, profile=measured_profile()
            )
            # The one factor. Everything else - corpus, candidate generation, the disclosure
            # selector, every configured budget - is whatever `make_service` gives both.
            object.__setattr__(self.services[spec.name], "cross_encoder", spec.cross_encoder)

    def search(self, **request: Any) -> dict[str, Any]:
        args = {"query": QUERY, "force_rungs": ["L5"], **request}
        return {
            name: service.search(parse_search(dict(args)))
            for name, service in self.services.items()
        }


def _cost(envelope: Any) -> Any:
    return envelope.retrieval_report.semantic_cost


def test_the_two_arms_differ_in_exactly_one_factor() -> None:
    """The pair H2 is read from, checked as a pair. A hypothesis whose arms differ in two
    things is a hypothesis this harness cannot attribute, which is what `sem-off` was for H2
    before `no-rerank` existed."""
    by_name = {spec.name: spec for spec in SPECS}
    for hypothesis, (left, right) in HYPOTHESIS_PAIRS.items():
        assert left in by_name and right in by_name, (hypothesis, left, right)
        differing = by_name[left].factors ^ by_name[right].factors
        assert len(differing) == 1, (hypothesis, sorted(one.value for one in differing))
    assert HYPOTHESIS_PAIRS["H2"] == (FULL.name, NO_RERANK.name)
    assert NO_RERANK.semantic is True, "the bypass arm must still embed, or it is `sem-off`"
    assert NO_RERANK.fixed_window == FULL.fixed_window, "the disclosure policy must be held"


def test_both_arms_embed_and_only_one_reranks() -> None:
    """**The instrumented proof of what executed**, at the seam and on the wire.

    The counters are the ground truth: they sit on the backend and record what it was asked
    for. The `semantic_cost` block is what a campaign record carries, so it is checked against
    them - a response that under-reported its own rerank would break H2's falsifier before H2
    was measured.
    """
    pair = _Pair(_ambiguous_mailbox())
    served = pair.search()
    full, bypass = pair.counters[FULL.name], pair.counters[NO_RERANK.name]

    assert full.embed_calls > 0 and bypass.embed_calls > 0, (
        f"both arms must embed: full={full.embed_calls}, bypass={bypass.embed_calls}"
    )
    assert full.embed_texts == bypass.embed_texts, (
        "the arms embedded different amounts of text, so they did not build the same pool"
    )
    assert full.rerank_calls > 0, (
        "the cross-encoder did not run on `full`, so this fixture exercises nothing"
    )
    assert bypass.rerank_calls == 0 and bypass.rerank_pairs == 0, (
        f"the bypass arm reranked {bypass.rerank_calls} time(s)"
    )

    # And the response says so, in the block a reader of a record has.
    assert _cost(served[FULL.name]).rerank_pairs == full.rerank_pairs
    assert _cost(served[NO_RERANK.name]).rerank_pairs == 0
    assert _cost(served[FULL.name]).escalated and _cost(served[NO_RERANK.name]).escalated, (
        "both arms escalated to L5; `escalated` is not `rerank_pairs > 0` and must not become it"
    )
    assert _cost(served[NO_RERANK.name]).embed_texts > 0


def test_the_bypass_keeps_the_registered_ordering_and_invents_no_score() -> None:
    """The bypass is D.7's first tier standing alone, which is a state the contract already
    has a name for. Nothing is simulated: a fabricated score would show up here as a
    cross-encoder `ordering_method`, or as a row carrying a `Score` no model produced."""
    served = _Pair(_ambiguous_mailbox()).search()
    assert _cost(served[NO_RERANK.name]).ordering_method == MECHANICAL_METHOD
    # **`model` still names the embedder, and should.** `SemanticCost.model` is "the model
    # reached", and on this arm one was: stage-A embedded the pool. It is `rerank_pairs` and
    # `ordering_method` that say whether a cross-encoder touched the order - which is the
    # distinction that block's own docstring draws, and the reason `escalated` is not
    # `rerank_pairs > 0`.
    assert _cost(served[NO_RERANK.name]).model is not None
    assert _cost(served[NO_RERANK.name]).model == _cost(served[FULL.name]).model, (
        "the arms reached different models, so they are not the same retriever"
    )
    for source in served[NO_RERANK.name].sources:
        for row in source.messages:
            assert row.score is None, (row.id, row.score)
    # L6 is still named as a rung: its first tier ran and ordered the candidates. A response
    # that dropped L6 here would be claiming it did no ranking while shipping a ranked list.
    assert RungId.L6 in served[NO_RERANK.name].retrieval_report.rungs


def test_nothing_held_constant_moved() -> None:
    """Corpus, candidate generation, disclosure policy and configured budgets are the same on
    both sides; only D.7's second tier differs. Asserted on the wire rather than assumed from
    the construction, because a factor that leaked would leak here."""
    served = _Pair(_ambiguous_mailbox()).search()
    left, right = served[FULL.name].retrieval_report, served[NO_RERANK.name].retrieval_report
    assert left.scan_scope == right.scan_scope, "the two arms scanned different things"
    assert (left.pool is None) == (right.pool is None)
    if left.pool is not None and right.pool is not None:
        assert (left.pool.message_count, left.pool.thread_count) == (
            right.pool.message_count,
            right.pool.thread_count,
        ), "the arms built different pools, so the comparison is not matched"
    assert left.budget_caps_hit == right.budget_caps_hit
    assert set(left.rungs) == set(right.rungs)


def test_a_downstream_difference_is_reported_rather_than_hidden() -> None:
    """**The honesty property, and the reason this is not a "responses are identical" test.**

    The arms are *supposed* to be able to differ downstream - that is what H2 would measure.
    What must never happen is a difference the response does not account for: if the two
    orderings are not the same, the two `ordering_method` values must not be the same either,
    because that field is the whole of a reader's ability to tell a reranked response from one
    the mechanical tier ordered (the wire's own note: the rows can be byte-identical and only
    their order differ).
    """
    served = _Pair(_ambiguous_mailbox()).search()
    order = {
        name: [source.thread_id for source in envelope.sources] for name, envelope in served.items()
    }
    methods = {name: _cost(envelope).ordering_method for name, envelope in served.items()}
    if order[FULL.name] != order[NO_RERANK.name]:
        assert methods[FULL.name] != methods[NO_RERANK.name], (
            f"the arms ordered {order} differently and both reported {methods[FULL.name]!r}"
        )


@pytest.mark.parametrize(
    ("label", "request_args", "box", "prohibition"),
    [
        (
            "identifier route",
            {"query": "rfc822msgid:<t1-m1@mail.invalid>"},
            _ambiguous_mailbox,
            RerankProhibition.IDENTIFIER_ROUTE,
        ),
        (
            "single hit",
            {"query": QUERY},
            _one_hit_mailbox,
            RerankProhibition.SINGLE_HIT,
        ),
    ],
)
def test_rank_01s_prohibitions_hold_identically_on_both_arms(
    label: str, request_args: dict[str, Any], box: Any, prohibition: RerankProhibition
) -> None:
    """**"Without changing exact-match families", made checkable.**

    On a prohibited route the tier does not run on the arm that has it either, so those
    families contribute no difference to H2 - and if one ever did, this pair would be
    measuring the prohibition rather than the reranker. The counters are what prove it: a
    prohibition honoured only in the report would still have scored the pairs.
    """
    pair = _Pair(box())
    pair.search(**request_args)
    for name, counter in pair.counters.items():
        assert counter.rerank_calls == 0, f"{label}: {name} scored pairs on a prohibited route"


def test_a_prohibition_is_not_reachable_past_by_forcing_the_rung() -> None:
    """`force_rungs` adds a rung; it does not overrule RANK-01. Held on both arms, because a
    caller who could force the tier on `full` and not on `no-rerank` would be comparing two
    different policies."""
    pair = _Pair(_ambiguous_mailbox())
    pair.search(query="rfc822msgid:<t1-m1@mail.invalid>", force_rungs=["L6"])
    for name, counter in pair.counters.items():
        assert counter.rerank_calls == 0, name


def test_forcing_the_rung_does_not_resurrect_a_bypassed_tier() -> None:
    """The bypass is the arm's configuration, like Baseline F's selector - not a per-request
    preference. If a request could turn it back on, the arm under measurement would not be the
    arm that was configured, and a campaign could not say which policy produced its numbers."""
    pair = _Pair(_ambiguous_mailbox())
    pair.search(force_rungs=["L5", "L6"])
    assert pair.counters[FULL.name].rerank_calls > 0, "the fixture does not reach the tier"
    assert pair.counters[NO_RERANK.name].rerank_calls == 0


def test_the_bypass_is_off_by_default_everywhere_it_can_be_constructed() -> None:
    """The shipped server reranks. A default that flipped would turn every production response
    into the bypass arm and nothing on the wire would call it one."""
    import inspect

    from mailweave.retrieval import assemble as assemble_module
    from mailweave.retrieval import ranking as ranking_module
    from mailweave.surface import runtime as runtime_module

    for owner in (
        inspect.signature(ranking_module.rank),
        inspect.signature(assemble_module.assemble),
        inspect.signature(runtime_module.start),
    ):
        assert owner.parameters["cross_encoder"].default is True
    assert MailweaveService.cross_encoder is True
    assert FULL.cross_encoder is True


def test_the_ranking_states_are_the_two_the_comparison_needs() -> None:
    """Named states, not incidental ones: `full` reaches the second tier and `no-rerank`
    reports the first tier standing alone. Read off the ranking rung directly so a change in
    how the wire summarises it cannot quietly turn this into a tautology."""
    import mailweave.retrieval.assemble as assemble_module
    from mailweave.retrieval.ranking import rank as real

    seen: dict[int, RankingState] = {}

    def spy(*args: Any, **kwargs: Any) -> Any:
        run = real(*args, **kwargs)
        seen[len(seen)] = run.state
        return run

    pair = _Pair(_ambiguous_mailbox())
    with pytest.MonkeyPatch.context() as patch:
        # Patched where it is *called*: `assemble` binds the name at import, so patching
        # `ranking.rank` alone would leave the caller on the original.
        patch.setattr(assemble_module, "rank_candidates", spy)
        pair.search()
    assert RankingState.RERANKED in seen.values(), seen
    assert RankingState.MECHANICAL_ONLY in seen.values(), seen
