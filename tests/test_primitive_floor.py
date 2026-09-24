"""The primitive-tools floor: what it is, what it is not, and that it runs.

The label is the load-bearing part. `EVALUATION_PLAN.md` §4.5 item 8 makes a primitive-tools
**agent** mandatory at every gate because it is the arm most able to falsify MailWeave's added
value. What is built here is a fixed policy - run the query verbatim, read the top N, stop - and
calling it Baseline E would overstate the pressure MailWeave has been under, which is the one
direction an evaluation must not err in.
"""

from __future__ import annotations

import pytest

from mailweave.constants import MAX_BODY_FETCHES_L0, MAX_RERANK_PAIRS
from mailweave.gmail import BackoffPolicy, CallMeter, GmailClient, StaticToken
from mailweave.net.egress import build_client
from mailweave_harness.evaluation import Measured, resolve_against
from mailweave_harness.evaluation.primitive import (
    BUDGETS,
    GENEROUS,
    TIGHT,
    PrimitiveTools,
)
from mailweave_harness.evaluation.primitive import run_all as floor_runs
from tests.fixtures.eval_dummy import TOKEN, dummy_case_file, dummy_manifest, mailbox_of


@pytest.fixture(scope="module")
def floor() -> tuple[PrimitiveTools, list[object]]:
    manifest = dummy_manifest()
    box, report = mailbox_of(manifest)
    client = GmailClient(
        token=StaticToken(TOKEN),
        http=build_client(inner=box.transport()),
        meter=CallMeter(),
        policy=BackoffPolicy(),
        sleeper=lambda _seconds: None,
        jitterer=lambda: 0.5,
    )
    cases = dummy_case_file(manifest)
    resolved = [resolve_against(case, manifest=manifest, report=report) for case in cases.cases]
    return PrimitiveTools(client=client), resolved


def test_the_floor_is_not_named_after_baseline_e() -> None:
    """A fixed policy cannot reformulate and makes no decisions. Naming it Baseline E would
    claim a falsification pressure nobody applied."""
    for budget in BUDGETS:
        assert "baseline" not in budget.name.lower()
        assert budget.name.startswith("primitive-floor")


def test_the_two_budgets_are_pre_registered_against_mailweaves_own_bounds() -> None:
    """A floor given less than MailWeave spends would be a straw one, and EP asks for two
    variants without fixing the numbers - so they are fixed here, before any run, against
    published constants rather than against a result."""
    assert TIGHT.gets == MAX_BODY_FETCHES_L0
    assert GENEROUS.gets == MAX_RERANK_PAIRS
    assert GENEROUS.gets > TIGHT.gets
    for budget in BUDGETS:
        assert str(budget.gets) in budget.why


def test_the_substrate_offers_exactly_two_operations() -> None:
    """A substrate that could also map threads or expand would be a smaller MailWeave, and the
    comparison would stop meaning anything."""
    public = {name for name in vars(PrimitiveTools) if not name.startswith("_")}
    assert public == {"search", "get"}


def test_the_floor_runs_every_case_and_reports_what_it_read(
    floor: tuple[PrimitiveTools, list[object]],
) -> None:
    tools, resolved = floor
    runs = floor_runs(tools, resolved)  # type: ignore[arg-type]
    assert len(runs) == len(resolved) * len(BUDGETS)
    assert all(one.state is not Measured.FAILED for one in runs), [
        (one.case_id, one.declined) for one in runs if one.declined
    ]
    assert {one.arm for one in runs} == {budget.name for budget in BUDGETS}


def test_the_floor_has_no_expansion_stage_and_says_so(
    floor: tuple[PrimitiveTools, list[object]],
) -> None:
    """Its budget *is* its expansion: every `get` is a round it spent. Reporting an
    expansion gain would credit it with a recovery mechanism it does not have."""
    tools, resolved = floor
    for run in floor_runs(tools, resolved):  # type: ignore[arg-type]
        assert run.reach.after_expansion == run.reach.first_response
        assert run.reach.expansion_gained == frozenset()


def test_the_floor_misses_evidence_mailweave_reaches(
    floor: tuple[PrimitiveTools, list[object]],
) -> None:
    """The contrast the floor exists to produce, on the dummy corpus.

    `dummy-escalates` runs a query whose bare terms Gmail ANDs, so the verbatim query matches
    nothing and the floor never names the evidence. MailWeave's ladder relaxes the query and
    reaches it. **This is a dummy corpus and the number means nothing about real retrieval** -
    what it establishes is that the comparison is capable of showing a difference at all,
    which a floor that matched MailWeave everywhere could not.
    """
    tools, resolved = floor
    runs = {one.case_id: one for one in floor_runs(tools, resolved) if one.arm == TIGHT.name}  # type: ignore[arg-type]
    escalating = runs["selftest-escalates"]
    assert escalating.reach.first_response == frozenset()
    assert escalating.reach.never_named, "the floor surfaced it after all, so this shows nothing"


def test_the_floor_cannot_be_scored_on_the_false_not_found_rate(
    floor: tuple[PrimitiveTools, list[object]],
) -> None:
    """It has no OD-2 outcome: it never says "not found", it returns what it read.

    `ANSWERED`/`INCONCLUSIVE` is the honest projection onto the shared enum, and the absence of
    `NOT_FOUND` is why EP §6.1's false-not-found rate is not a number this arm can have.
    """
    tools, resolved = floor
    terminals = {one.terminal.value for one in floor_runs(tools, resolved)}  # type: ignore[arg-type]
    assert "not_found" not in terminals
