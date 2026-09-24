"""R-M2-113: an embedding failure after the pool's probes have run cannot emit a response.

**Not part of A16, and deliberately filed on its own.** D.5 declares a deterministic fallback
for a semantic backend that is unusable: the rung reports itself not tried with an `error`
reason and the ladder continues. What happens instead, whenever the failure comes *after*
`SemanticRunner._build_pool` has sent its probes, is a `DispositionInvariantError` out of the
envelope's own validator - so the caller gets no response at all, fallback or otherwise.

The mechanism, and it is two correct rules meeting:

  * `_build_pool` sends the pool's `messages.list` probes at `RungId.L5`, so every id they
    return is admitted to `H` under L5 (AD A.7a, and ADV-109 names the step-(b) probes by
    hand). That is right and no repair may undo it.
  * `assemble._rungs_run` names L5 in `retrieval_report.rungs` only when
    `semantic.state is SemanticState.RAN`. `UNAVAILABLE` is not `RAN`, so L5 is omitted.

`Envelope._the_per_rung_hit_counts_are_the_ledgers_own` then finds a rung that admitted ids and
is absent from `rungs`, and refuses the response - which is the validator doing exactly its
job. The defect is upstream of it: a rung that sent probes and admitted ids **ran**, and the
embedding failure is an error on a rung that ran, not a reason it was never tried.

**Reproduced at HEAD as well**, so this predates A16 and is not caused by it. **Repaired
2026-09-16 as its own bounded change**, separate from A16 and made after A16's paired
measurement was captured: `assemble` asks the ledger whether L5's probes admitted anything, and

  * `_rungs_run` names L5 when they did - a rung that admitted ids **ran**, whatever became of
    it afterwards;
  * `_l5_not_tried` stands down for that rung, so the response never claims one rung both ran
    and was never tried;
  * the reason travels instead as D.11's in-band `semantic_unavailable` `errors[]` entry,
    carrying the call that would run the rung again.

**Nothing else moves, and the tests below are mostly about that.** The probes' ids stay in `H`
with their origins, `certify` disposes of every one of them exactly as before, no cap is minted
or removed, and the lexical ladder's own evidence is untouched. `SemanticState.BLOCKED` reaches
`rungs` and `not_tried` by the same rule - its ids are in `H` too - but mints no `errors[]`
entry, because a pool budget breach is already named in `budget_caps_hit` through
`semantic.cap` and reporting it twice would be a second claim about one event.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from mailweave.envelope.reasons import RungId
from mailweave.envelope.vocab import NotTriedWhy, Role
from mailweave.errors import ErrorCode
from mailweave.semantic.interface import (
    BackendRegistry,
    BackendUnavailable,
    SemanticError,
    Vector,
)
from mailweave.surface.arguments import parse_search
from tests.fixtures.mailbox import Msg, SyntheticMailbox
from tests.test_semantic_rung import make_service, measured_profile

TERM = "plinth"


class _BrokenBackend:
    """Loads, then fails at stage A - D.5's `BackendUnavailable` after the pool is built.

    The failure has to be *after* the probes: a backend that cannot be acquired at all never
    reaches `_build_pool`, admits nothing, and falls back exactly as declared. That case works
    and is not what this file is about.
    """

    model_id = "test/broken"
    model_revision = "0" * 40

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        raise SemanticError("weights unreadable")

    def rerank(self, query: str, candidates: Sequence[str]) -> list[float]:
        return [0.0 for _ in candidates]


class _UnacquirableBackend:
    """Cannot be acquired at all - the path that already fell back correctly."""

    model_id = "test/absent"
    model_revision = "0" * 40

    def __init__(self) -> None:
        raise BackendUnavailable("no weights on this machine")

    def embed(self, texts: Sequence[str]) -> list[Vector]:  # pragma: no cover - never reached
        raise AssertionError("acquired a backend that refuses to be acquired")

    def rerank(
        self, query: str, candidates: Sequence[str]
    ) -> list[float]:  # pragma: no cover - never reached
        raise AssertionError("acquired a backend that refuses to be acquired")


def _registry() -> BackendRegistry:
    registry = BackendRegistry()
    registry.register("test/broken", _BrokenBackend, default=True)
    return registry


def _unacquirable() -> BackendRegistry:
    registry = BackendRegistry()
    registry.register("test/absent", _UnacquirableBackend, default=True)
    return registry


def _mailbox() -> SyntheticMailbox:
    """Three recent threads matching no term, so the pool's step-(c) probe is what admits them
    and the lexical rungs contribute nothing. Generated, not a corpus case."""
    now = datetime.now(UTC)
    rows: list[Msg] = []
    for thread in range(3):
        for index in range(3):
            stamp = now - timedelta(days=2, minutes=60 - index)
            rows.append(
                Msg(
                    id=f"t{thread}-m{index}",
                    thread_id=f"t{thread}",
                    sender="bo@team.example",
                    subject="roster",
                    body=f"unrelated note {thread}{index}",
                    internal_date_ms=int(stamp.timestamp() * 1000),
                    to=("cy@team.example",),
                    in_reply_to=None if index == 0 else f"<t{thread}-m{index - 1}@mail.invalid>",
                )
            )
    return SyntheticMailbox(messages=tuple(rows), now_ms=int(now.timestamp() * 1000))


def _lexical_mailbox() -> SyntheticMailbox:
    """The same shape with one message the query's own term matches, so the lexical ladder has
    an answer of its own to deliver when the rung fails."""
    now = datetime.now(UTC)
    rows: list[Msg] = []
    for index in range(3):
        stamp = now - timedelta(days=2, minutes=60 - index)
        rows.append(
            Msg(
                id=f"t9-m{index}",
                thread_id="t9",
                sender="bo@team.example",
                subject="roster",
                body=f"the {TERM} was signed off" if index == 1 else f"unrelated note {index}",
                internal_date_ms=int(stamp.timestamp() * 1000),
                to=("cy@team.example",),
                in_reply_to=None if index == 0 else f"<t9-m{index - 1}@mail.invalid>",
            )
        )
    return SyntheticMailbox(messages=tuple(rows), now_ms=int(now.timestamp() * 1000))


def _search() -> Any:
    service = make_service(_mailbox(), registry=_registry(), profile=measured_profile())
    return service.search(parse_search({"query": TERM, "force_rungs": ["L5"]}))


def test_the_probes_admitted_ids_before_the_embedding_failed() -> None:
    """The precondition, asserted on its own so nothing below can be satisfied by a fixture
    that never ran the pool: the failing backend is reached **after** L5's probes have put ids
    into `H` at L5."""
    envelope = _search()
    report = envelope.retrieval_report
    counts = dict(zip(report.rungs, report.hit_count_per_rung, strict=True))
    assert counts.get(RungId.L5, 0) > 0, counts


def test_the_declared_fallback_is_delivered() -> None:
    """R-M2-113, repaired. D.5 promises the rung declines and the ladder's own answer is
    emitted; before the repair the envelope's validator refused the response instead and the
    caller got nothing."""
    envelope = _search()
    report = envelope.retrieval_report
    assert RungId.L5 in report.rungs, [rung.value for rung in report.rungs]
    assert report.outcome is not None
    # The rung is not claimed to have run *and* to have been untried.
    assert RungId.L5.value not in {entry.rung for entry in report.not_tried}, report.not_tried


def test_the_failure_is_reported_in_band_with_an_executable_way_back() -> None:
    """The reason did not disappear with the `not_tried` entry. D.11 puts
    `semantic_unavailable` on the in-band side, and AD-03 requires an affordance to be a call a
    caller can actually make."""
    envelope = _search()
    entries = [one for one in envelope.errors if one.code is ErrorCode.SEMANTIC_UNAVAILABLE]
    assert len(entries) == 1, envelope.errors
    entry = entries[0]
    assert "embedding" in entry.scope, entry.scope
    assert entry.affordance is not None
    parse_search(dict(entry.affordance.args))


def test_every_id_the_probes_admitted_is_still_accounted() -> None:
    """**The accounting half, which the repair must not touch.** A.7a's identity is
    `H == disclosed union withheld`, and `certify` refuses a response where it does not hold -
    so a repair that quietly dropped the probes' ids to make the rung reportable would fail
    here rather than pass silently. Checked on the wire, not on the ledger."""
    envelope = _search()
    disclosed = {row.id for source in envelope.sources for row in source.messages}
    named = {record.id for record in envelope.withheld}
    grouped = sum(group.message_count for group in envelope.withheld_groups)
    report = envelope.retrieval_report
    total = sum(report.hit_count_per_rung)
    assert total > 0
    assert len(disclosed | named) + grouped >= total, (
        f"H is {total}; the response accounts for {len(disclosed)} disclosed, {len(named)} "
        f"named and {grouped} grouped"
    )


def test_no_cap_is_minted_by_the_fallback() -> None:
    """Caps are untouched. An embedding failure is not a budget event, and the repair must not
    make one appear - `budget_caps_hit` is what a caller reads to decide whether to raise a
    bound, and a cap that never fired would send them at the wrong lever."""
    envelope = _search()
    assert envelope.retrieval_report.budget_caps_hit == (), (
        envelope.retrieval_report.budget_caps_hit
    )


def test_a_backend_that_fails_before_the_pool_is_unchanged() -> None:
    """**The boundary that keeps the repair from widening.** A backend that cannot be acquired
    at all never reaches `_build_pool`, admits nothing, and is `not_tried[error]` with L5
    absent from `rungs` - D.5's fallback as it already worked. The repair keys on ids having
    been admitted, so this path must be exactly as it was."""
    service = make_service(_mailbox(), registry=_unacquirable(), profile=measured_profile())
    envelope = service.search(parse_search({"query": TERM, "force_rungs": ["L5"]}))
    report = envelope.retrieval_report
    assert RungId.L5 not in report.rungs, [rung.value for rung in report.rungs]
    untried = {entry.rung: entry.why for entry in report.not_tried}
    assert untried.get(RungId.L5.value) is NotTriedWhy.ERROR, untried
    assert not [one for one in envelope.errors if one.code is ErrorCode.SEMANTIC_UNAVAILABLE]


def test_the_lexical_evidence_still_reaches_the_caller() -> None:
    """**Existing evidence, preserved — the point of having a fallback at all.**

    A mailbox where the lexical ladder *does* find the term, so there is an answer to lose.
    The backend fails after the pool's probes have run; the ladder's own matched messages must
    still be in the response as evidence. Before the repair this response did not exist: the
    envelope refused it, and the lexical answer went down with the rung that failed.

    The comparison is against this run's own lexical hits rather than against a second
    retrieval without L5, which would be a different retrieval: the pool's probes admit ids
    that a no-pool run never sees, and those ids are `context` by A.9(5) either way.
    """
    service = make_service(_lexical_mailbox(), registry=_registry(), profile=measured_profile())
    envelope = service.search(parse_search({"query": TERM, "force_rungs": ["L5"]}))
    rows = {row.id: row for source in envelope.sources for row in source.messages}
    assert "t9-m1" in rows, sorted(rows)
    assert rows["t9-m1"].role is Role.MATCHED, rows["t9-m1"].role
    assert envelope.retrieval_report.outcome is not None
    assert [one.code for one in envelope.errors if one.code is ErrorCode.SEMANTIC_UNAVAILABLE]
