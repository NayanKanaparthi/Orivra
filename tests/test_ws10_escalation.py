"""WS-10: escalation policy, budgets, stopping and outcome, driven end to end.

Same standing as `tests/test_lexical_ladder.py` and `tests/test_thread_map_round20.py`: the
real client, the real ledger, real URL construction, the real retry ladder and the real
egress allowlist, with `httpx.MockTransport` where the socket would be and
`tests/conftest.py` denying `socket.connect` for every test here. The clock is injected, so
no test's result depends on how fast the machine it ran on was.

**The shape space, and the commonality that collapses it.** Seven rungs times three outcomes
times the mid-rung timeout contract is a large space, and a list of tests over it is a list
of chances to have missed one - this project's most repeated defect, found seventeen times.
What every cell has in common is not its rung and not its outcome:

    every rung of the ladder is, at every moment, in exactly one of three accounted
    states - ran, not applicable, or blocked - and the response's `rungs`, `not_tried`,
    `budget_caps_hit` and `outcome` are all read off that one record rather than derived a
    second time.

`test_every_rung_is_accounted_for_in_exactly_one_state` asserts that over `SHAPES`, and
`test_the_shape_matrix_reaches_every_state_and_every_outcome_it_asserts_about` asserts the
matrix **reaches** every state and every outcome the clauses talk about. That second test is
R-RETR-058's lesson written down: round 21's commonality property ran over a matrix
containing no cache-served answer and no clean redemption, so four of its eight clauses could
not fail, and planting BLOCKER ADV-002's own defect left it green. A property is evidence
only over a population that reaches it, and the non-vacuity assertions here read the
**answers** rather than the names the shapes were built under.

No fixture here carries real or realistic personal mail: addresses use the reserved
`.example` and `.invalid` TLDs (RFC 2606/6761) and every subject and body is invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from mailweave.constants import (
    FLOOR_QUOTA_UNITS,
    MAX_API_CALLS,
    MAX_CONCURRENT_QUERIES,
    MAX_HTTP_REQUESTS,
    MAX_QUOTA_UNITS,
    MAX_QUOTA_UNITS_SEMANTIC,
    MAX_SEMANTIC_MS,
    MAX_SERVER_MS,
)
from mailweave.envelope import DispositionLedger
from mailweave.envelope.reasons import RungId
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import (
    BLOCKING_NOT_TRIED,
    PUBLISHED_NOT_TRIED,
    BudgetCapName,
    NotTriedWhy,
    Outcome,
    Sufficiency,
    WithheldCap,
)
from mailweave.envelope.wire import RetrievalReport
from mailweave.gmail.client import GmailClient, StaticToken
from mailweave.gmail.meter import CallMeter
from mailweave.gmail.rates import GmailEndpoint
from mailweave.gmail.retry import BackoffPolicy
from mailweave.net.egress import build_client
from mailweave.policy import (
    LADDER,
    PUBLISHED_ORDER,
    BudgetAccountant,
    BudgetRefused,
    BudgetRequest,
    CapBreach,
    Governor,
    LadderAccount,
    RungAccount,
    RungState,
    StopInputs,
    StopRule,
    apply_floor,
    blocked_by,
    first_rule_that_fires,
    not_applicable,
    outcome_of,
    rule_1_stops,
    rule_1b_stops,
    rule_2_stops,
    stopped_on_evidence,
)
from mailweave.retrieval.assemble import assemble
from mailweave.retrieval.ladder import LadderRunner
from mailweave.retrieval.signals import AnswerTypePresence, ExactBranch, ExactSignal
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms

NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)
UTC_ZONE = ZoneInfo("UTC")
TOKEN = "ya29.synthetic-ws10-token"
DOCUMENT = Path(__file__).resolve().parents[1] / "docs" / "ARCHITECTURE_DECISION.md"

#: One term carried by exactly one message of each of the three threads below, so a single
#: query is hit-bearing across all of them.
MARKER = "quillevant"
#: A term no message carries. The zero-evidence case.
ABSENT = "sprindle"


def msgid(name: str) -> str:
    return f"<{name}@mail.invalid>"


# --- the mailbox --------------------------------------------------------------------------


def corpus() -> tuple[Msg, ...]:
    return (
        Msg(
            id="a1",
            thread_id="t-alpha",
            sender="Ana Ito <ana@team.example>",
            subject="Rack order",
            body=f"the {MARKER} opening note",
            internal_date_ms=epoch_ms(2026, 5, 1),
            to=("bo@team.example",),
        ),
        Msg(
            id="a2",
            thread_id="t-alpha",
            sender="Bo Ng <bo@team.example>",
            subject="Re: Rack order",
            body="a reply that settles it",
            internal_date_ms=epoch_ms(2026, 5, 2),
            in_reply_to=msgid("a1"),
            to=("ana@team.example",),
        ),
        Msg(
            id="b1",
            thread_id="t-beta",
            sender="Cai Ode <cai@team.example>",
            subject="Unrelated matter",
            body=f"a second {MARKER} thread",
            internal_date_ms=epoch_ms(2026, 5, 3),
        ),
        Msg(
            id="c1",
            thread_id="t-gamma",
            sender="Dee Ren <dee@team.example>",
            subject="A third matter",
            body=f"a third {MARKER} thread",
            internal_date_ms=epoch_ms(2026, 5, 4),
        ),
        # A hit whose named reply parent is in **another** thread, so L4 has something to
        # expand on. Without it every shape leaves L4 `not_applicable` and the clauses about
        # a structural rung's budget are asserted over a rung that never plans a probe.
        Msg(
            id="d1",
            thread_id="t-delta",
            sender="Eli Poe <eli@team.example>",
            subject="Re: A fourth matter",
            body=f"a fourth {MARKER} thread whose parent is filed elsewhere",
            internal_date_ms=epoch_ms(2026, 5, 5),
            in_reply_to=msgid("e1"),
        ),
        Msg(
            id="e1",
            thread_id="t-epsilon",
            sender="Fay Quo <fay@team.example>",
            subject="A fourth matter",
            body="the parent, filed in a thread of its own",
            internal_date_ms=epoch_ms(2026, 5, 6),
        ),
    )


def mailbox(**overrides: object) -> SyntheticMailbox:
    return SyntheticMailbox(messages=corpus(), now_ms=epoch_ms(2026, 9, 3), **overrides)  # type: ignore[arg-type]


def make_client(box: SyntheticMailbox) -> GmailClient:
    return GmailClient(
        token=StaticToken(TOKEN),
        http=build_client(inner=box.transport()),
        meter=CallMeter(),
        policy=BackoffPolicy(),
        sleeper=lambda _seconds: None,
        jitterer=lambda: 0.5,
    )


class FakeClock:
    """A monotonic clock in milliseconds that only moves when a test moves it.

    The timeout contract is the part of WS-10 that most needs executing rather than
    reasoning about, and a test that measured real elapsed time would be a test whose result
    depends on the machine it ran on. `advance` is the only thing that moves this.
    """

    def __init__(self, start_ms: float = 0.0) -> None:
        self.ms = start_ms

    def __call__(self) -> float:
        return self.ms

    def advance(self, by_ms: float) -> None:
        self.ms += by_ms


class TickingClock(FakeClock):
    """A clock that advances by a fixed amount on every reading.

    This is how the mid-rung stop is reached without a `time.sleep`: the accountant reads the
    clock once per probe, so a tick per reading makes the deadline arrive after a known
    number of probes rather than after an unknown number of milliseconds.
    """

    def __init__(self, tick_ms: float) -> None:
        super().__init__(0.0)
        self._tick = tick_ms

    def __call__(self) -> float:
        value = self.ms
        self.ms += self._tick
        return value


# --- AD D.3's rules, in the order the document prints them --------------------------------


def test_the_published_order_is_the_order_the_document_prints() -> None:
    """`PUBLISHED_ORDER` is read against `docs/ARCHITECTURE_DECISION.md` D.3, not memory.

    D.3's own header says the previous ordering *was* the bug (ADV-004), and round 16 then
    got the same section wrong in the other direction. An order that a reader has to check
    by eye is an order this project has twice failed to check by eye, so this test parses the
    document's own numbered list and compares it with the tuple the code iterates.
    """
    section = DOCUMENT.read_text().split("### D.3 Escalation ladder, budgets, stopping rules")[1]
    section = section.split("### D.4")[0]
    printed = tuple(re.findall(r"^(\d+b?)\.\s", section, flags=re.MULTILINE))
    assert printed == ("0", "1", "1b", "2", "3", "4", "5", "6"), printed
    assert tuple(rule.value for rule in PUBLISHED_ORDER) == tuple(
        f"D.3-{number}" for number in printed
    )


def signals(
    *,
    branch: ExactBranch | None = None,
    fired: bool = False,
    present: bool | None = None,
    hit_count: int = 0,
    term_coverage: float = 1.0,
    drop_depth: int = 0,
    sufficiency: Sufficiency | None = None,
    cap_exhausted: bool = False,
    evidence: int = 0,
) -> StopInputs:
    return StopInputs(
        exact=ExactSignal(
            fired=fired or branch is not None,
            branch=branch,
            phrase_tokens=0,
            hit_count=hit_count,
            verified_locally=branch is not None,
        ),
        answer_type=AnswerTypePresence(answer_type=None, present=present, examined=0),
        hit_count=hit_count,
        term_coverage=term_coverage,
        constraint_drop_depth=drop_depth,
        sufficiency=sufficiency,
        cap_exhausted=cap_exhausted,
        evidence_count=evidence,
    )


def test_rule_two_does_not_carry_rule_one_bs_escape() -> None:
    """Round 16's defect, executed: rule 2's fourth conjunct is `present is True`.

    R-RETR-007. The conjunct was written as rule 1b's "or the query carries no answer-type
    cue" escape - `present is not False` - and `present is None` is what every ordinary
    non-interrogative query produces, so the stop fired on almost all of them and switched
    L1b off for exactly the threads it exists for. The tri-state is what makes the difference
    load-bearing rather than pedantic, so all three values are asserted here.
    """
    for present, rule_2_expected, rule_1b_expected in (
        (True, True, True),
        (None, False, True),
        (False, False, False),
    ):
        inputs = signals(branch=ExactBranch.E_B, fired=True, present=present, hit_count=2)
        assert rule_2_stops(inputs) is rule_2_expected, present
        assert rule_1b_stops(inputs) is rule_1b_expected, present


def test_rule_one_stops_unconditionally_and_rule_one_b_does_not() -> None:
    """ADV-004's asymmetry: a message id cannot match a confident-looking wrong message.

    Branch E-a stops whatever `answer_type_presence` says; branches E-b and E-c do not.
    """
    for present in (True, None, False):
        e_a = signals(branch=ExactBranch.E_A, present=present, hit_count=1)
        assert rule_1_stops(e_a) is True, present
        e_b = signals(branch=ExactBranch.E_B, present=present, hit_count=1)
        assert rule_1_stops(e_b) is False, present
    assert rule_1b_stops(signals(branch=ExactBranch.E_B, present=False, hit_count=1)) is False


def test_the_first_rule_that_fires_is_the_first_one_in_the_documents_order() -> None:
    """When several rules are simultaneously true, the earliest published one is returned.

    Constructed so rules 1, 1b, 2, 3 and 5 all hold at once. An if-chain that had been
    reordered by one line would return a later rule here; the evaluator iterates
    `PUBLISHED_ORDER` and looks each predicate up, so it cannot.
    """
    everything = signals(
        branch=ExactBranch.E_A,
        fired=True,
        present=True,
        hit_count=1,
        sufficiency=Sufficiency.SUFFICIENT,
        cap_exhausted=True,
    )
    assert first_rule_that_fires(everything) is StopRule.RULE_1
    without_e_a = signals(
        branch=ExactBranch.E_B,
        fired=True,
        present=True,
        hit_count=1,
        sufficiency=Sufficiency.SUFFICIENT,
        cap_exhausted=True,
    )
    assert first_rule_that_fires(without_e_a) is StopRule.RULE_1B
    only_cap = signals(cap_exhausted=True)
    assert first_rule_that_fires(only_cap) is StopRule.RULE_5
    assert first_rule_that_fires(signals()) is None


# --- AD A.7's caps, and the recoverability floor ------------------------------------------


def test_every_published_cap_is_a_constant_this_module_enforces() -> None:
    """A.7's cap table against the code, so a cap can be enforced or absent but not implied.

    The values are quoted from the architecture rather than imported into the expectation,
    for the reason `test_outcome_od2.py` quotes OD-2's vocabulary: a change to the
    implementation's constants cannot silently redefine what this test is checking.
    """
    assert (MAX_QUOTA_UNITS, MAX_QUOTA_UNITS_SEMANTIC) == (1_200, 2_400)
    assert (MAX_API_CALLS, MAX_HTTP_REQUESTS) == (80, 24)
    # `max_server_ms` is the one published cap this project has moved from its architecture
    # value. 2,000 was a [DESIGN] planning figure; 7,700 is the owner-selected operational
    # default adopted on 2026-09-09 after live acceptance failed twice on 2,000 and deadline
    # run 3 measured the three arms. The quoted expectation moves with the decision, which is
    # the point of quoting it: this line is where such a move has to be acknowledged.
    assert (MAX_SERVER_MS, MAX_SEMANTIC_MS) == (7_700, 6_000)
    assert MAX_CONCURRENT_QUERIES == 2
    assert FLOOR_QUOTA_UNITS == 845
    budget = apply_floor(BudgetRequest())
    assert budget.max_quota_units == MAX_QUOTA_UNITS
    assert apply_floor(BudgetRequest(), semantic=True).max_quota_units == MAX_QUOTA_UNITS_SEMANTIC


def test_a_budget_below_the_floor_is_clamped_up_and_the_clamp_is_declared() -> None:
    """AD-03: never accepted-and-then-overrun, and never silently refused."""
    clamped = apply_floor(BudgetRequest(max_quota_units=100))
    assert clamped.max_quota_units == FLOOR_QUOTA_UNITS
    assert clamped.clamp is not None
    assert clamped.clamp.requested == 100
    assert clamped.clamp.applied == FLOOR_QUOTA_UNITS
    assert clamped.clamp.why
    assert clamped.block.clamped is clamped.clamp


def test_a_budget_at_or_above_the_floor_is_honoured_verbatim_with_no_clamp() -> None:
    """The floor clamps from below only: there is no ceiling on a caller's own quota."""
    for requested in (FLOOR_QUOTA_UNITS, FLOOR_QUOTA_UNITS + 1, MAX_QUOTA_UNITS * 10):
        applied = apply_floor(BudgetRequest(max_quota_units=requested))
        assert applied.max_quota_units == requested
        assert applied.clamp is None


def test_no_request_declares_no_clamp() -> None:
    assert apply_floor(BudgetRequest()).clamp is None


def test_the_governor_admits_up_to_its_limit_and_refuses_by_name() -> None:
    """AD A.5c: `process_quota_refused` is a named class, not latency with no name on it."""
    governor = Governor()
    clock = FakeClock()
    admitted = [
        governor.admit(meter=CallMeter(), now_ms=clock) for _ in range(MAX_CONCURRENT_QUERIES)
    ]
    assert len(admitted) == MAX_CONCURRENT_QUERIES
    with pytest.raises(BudgetRefused) as refusal:
        governor.admit(meter=CallMeter(), now_ms=clock)
    assert refusal.value.cap is BudgetCapName.PROCESS_QUOTA_REFUSED
    governor.release()
    assert governor.admit(meter=CallMeter(), now_ms=clock) is not None


def test_the_governor_releases_even_when_the_query_raises() -> None:
    governor = Governor()
    with pytest.raises(RuntimeError), governor.query(meter=CallMeter(), now_ms=FakeClock()):
        raise RuntimeError("the query failed")
    assert governor.in_flight == 0


def test_a_time_cap_is_reported_before_a_call_cap_when_both_would_fire() -> None:
    """A query that ran out of time ran out however cheap the next call is.

    Reporting `max_api_calls` for a request that timed out would send the caller to raise the
    wrong number, so the order of the checks is the order of the answers' usefulness.
    """
    meter = CallMeter()
    for _ in range(MAX_API_CALLS + 5):
        meter.record_attempt(GmailEndpoint.MESSAGES_LIST)
    clock = FakeClock()
    accountant = BudgetAccountant(meter, apply_floor(BudgetRequest()), now_ms=clock)
    breach = accountant.check((GmailEndpoint.MESSAGES_LIST,))
    assert breach is not None and breach.cap is BudgetCapName.MAX_API_CALLS
    clock.advance(MAX_SERVER_MS)
    timed_out = accountant.check((GmailEndpoint.MESSAGES_LIST,))
    assert timed_out is not None and timed_out.cap is BudgetCapName.MAX_SERVER_MS
    assert timed_out.why is NotTriedWhy.TIMEOUT
    assert accountant.caps_hit == (BudgetCapName.MAX_API_CALLS, BudgetCapName.MAX_SERVER_MS)


def test_every_cap_breach_carries_the_call_that_would_raise_it() -> None:
    """AD-03: a cap without an affordance is a dead end reported as a fact."""
    clock = FakeClock()
    accountant = BudgetAccountant(
        CallMeter(), apply_floor(BudgetRequest(max_quota_units=FLOOR_QUOTA_UNITS)), now_ms=clock
    )
    clock.advance(MAX_SERVER_MS + 1)
    breach = accountant.check()
    assert breach is not None
    assert breach.affordance.args == {"budget": {"max_server_ms": MAX_SERVER_MS * 2}}
    assert breach.withheld_cap.value == "max_server_ms"


def test_the_semantic_deadline_is_a_separate_cap_from_the_lexical_one() -> None:
    """AD A.7: "separate by design" - one deadline over both would strangle one of them."""
    clock = FakeClock()
    accountant = BudgetAccountant(CallMeter(), apply_floor(BudgetRequest()), now_ms=clock)
    clock.advance(MAX_SERVER_MS - 1)
    assert accountant.check() is None
    accountant.enter_semantic()
    clock.advance(MAX_SEMANTIC_MS - 1)
    assert accountant.check() is None
    clock.advance(2)
    breach = accountant.check()
    assert breach is not None and breach.cap is BudgetCapName.MAX_SEMANTIC_MS


def test_the_accountant_refuses_before_the_spend_and_not_after_it() -> None:
    """AD A.7: a budget is never accepted-and-then-overrun.

    The accountant is asked whether the *next* call fits, so a run under a two-call budget
    makes two calls and not three - and the assertion is over the meter, which counts what
    left the process.
    """
    meter = CallMeter()
    accountant = BudgetAccountant(
        meter,
        apply_floor(BudgetRequest(max_api_calls=2)),
        now_ms=FakeClock(),
    )
    spent = 0
    while accountant.check((GmailEndpoint.MESSAGES_LIST,)) is None:
        meter.record_attempt(GmailEndpoint.MESSAGES_LIST)
        spent += 1
        assert spent < 10, "the accountant never refused"
    assert spent == 2
    assert meter.reading().api_calls == 2


# --- the `not_tried` vocabulary, and round 22's ruling on it ------------------------------


def test_the_vocabulary_is_the_published_one_plus_exactly_one_argued_addition() -> None:
    """AD D.2's list, and round 22's `stopped_on_evidence`, kept visible as an addition.

    The literals are quoted from AD D.2 rather than imported, so a change to the enum cannot
    silently redefine what this test is checking. The addition is argued in `NotTriedWhy`'s
    own docstring and recorded in `docs/reviews/ROUND_22/IMPLEMENTER.md`; this test exists so
    that a *second* addition cannot arrive without somebody making the same case.
    """
    assert {member.value for member in PUBLISHED_NOT_TRIED} == {
        "not_applicable",
        "budget",
        "cap",
        "timeout",
        "error",
    }
    assert {member.value for member in NotTriedWhy} - {
        member.value for member in PUBLISHED_NOT_TRIED
    } == {"stopped_on_evidence"}


def test_not_applicable_is_the_only_reason_compatible_with_not_found() -> None:
    """OD-2's partition, derived as a complement rather than listed twice."""
    assert frozenset(NotTriedWhy) - {NotTriedWhy.NOT_APPLICABLE} == BLOCKING_NOT_TRIED
    assert NotTriedWhy.STOPPED_ON_EVIDENCE in BLOCKING_NOT_TRIED


def test_a_rung_the_policy_declined_carries_the_call_that_would_run_it() -> None:
    """The operational half of the ruling: `stopped_on_evidence` has a remedy and the other
    non-blocking value cannot have one."""
    declined = stopped_on_evidence(RungId.L5, query="vendor")
    assert declined.why is NotTriedWhy.STOPPED_ON_EVIDENCE
    assert declined.affordance is not None
    # Round 24: the affordance carries the caller's own query as well as the rung, because
    # `mailweave_search` requires one and contract R-07 asks for a call rather than a delta.
    assert declined.affordance.args == {"query": "vendor", "force_rungs": ["L5"]}
    assert not_applicable(RungId.L5).affordance is None


def test_the_two_impossible_rung_records_cannot_be_built() -> None:
    """A blocked rung with no way to reach it, and an inapplicable rung offering one."""
    with pytest.raises(ValueError, match="the call that would reach it"):
        RungAccount(rung=RungId.L5, state=RungState.BLOCKED, why=NotTriedWhy.BUDGET)
    with pytest.raises(ValueError, match="no call reaches"):
        RungAccount(
            rung=RungId.L5,
            state=RungState.NOT_APPLICABLE,
            why=NotTriedWhy.NOT_APPLICABLE,
            affordance=stopped_on_evidence(RungId.L5, query="vendor").affordance,
        )
    with pytest.raises(ValueError, match="two accounts of one fact"):
        RungAccount(rung=RungId.L5, state=RungState.RAN, why=NotTriedWhy.BUDGET)
    with pytest.raises(ValueError, match="one value OD-2 makes compatible"):
        RungAccount(
            rung=RungId.L5,
            state=RungState.BLOCKED,
            why=NotTriedWhy.NOT_APPLICABLE,
            affordance=stopped_on_evidence(RungId.L5, query="vendor").affordance,
        )


# --- OD-2's three-way outcome, over the whole space ---------------------------------------


def complete_account(**overrides: RungAccount) -> LadderAccount:
    """Every rung of `LADDER` accounted for, `not_applicable` unless a test says otherwise."""
    by_rung = {rung: not_applicable(rung) for rung in LADDER}
    for name, account in overrides.items():
        by_rung[RungId[name]] = account
    return LadderAccount(accounts=tuple(by_rung.values()))


def _quota_breach() -> CapBreach:
    """One `CapBreach`, built the way the accountant builds one, for the unit-level tests."""
    meter = CallMeter()
    for _ in range(3):
        meter.record_attempt(GmailEndpoint.THREADS_GET)
    accountant = BudgetAccountant(
        meter, apply_floor(BudgetRequest(max_quota_units=FLOOR_QUOTA_UNITS)), now_ms=FakeClock()
    )
    breach = accountant.check((GmailEndpoint.THREADS_GET,) * 30)
    assert breach is not None and breach.cap is BudgetCapName.MAX_QUOTA_UNITS
    return breach


def test_not_found_needs_every_condition_and_each_one_alone_withholds_it() -> None:
    """OD-2, as a conjunction with an assertion per conjunct.

    `not_found` is the only outcome in the vocabulary that can be a lie about the mailbox, so
    each way of making it one is executed separately rather than as one combined negative.
    """
    account = complete_account()
    assert (
        outcome_of(account=account, disclosed=0, evidence=0, hits=0, caps_hit=())
        is Outcome.NOT_FOUND
    )
    withheld_by: dict[str, dict[str, object]] = {
        "a rung blocked by a cap": {
            "account": complete_account(L5=blocked_by(RungId.L5, _quota_breach()))
        },
        "a rung the policy declined on evidence": {
            "account": complete_account(L5=stopped_on_evidence(RungId.L5, query="vendor"))
        },
        "a cap in budget_caps_hit": {"caps_hit": (BudgetCapName.MAX_QUOTA_UNITS,)},
        "a hit nothing disclosed, i.e. a withheld record": {"hits": 1},
        "a page nobody fetched": {"unfetched_pages": True},
    }
    for because, override in withheld_by.items():
        arguments: dict[str, object] = {
            "account": account,
            "disclosed": 0,
            "evidence": 0,
            "hits": 0,
            **override,
        }
        assert outcome_of(**arguments) is Outcome.INCONCLUSIVE, because  # type: ignore[arg-type]


def test_a_ladder_missing_a_rung_entirely_cannot_say_not_found() -> None:
    """OD-2's "actually executed and exhausted" over a ladder that does not have the rung.

    L5, L6 and LR are not built. There is no honest `not_tried[].why` for that - one value
    would claim the rung could not have helped and the other five would claim some call
    reaches it - so the rung is **absent** from the account and `outcome_of` reads the
    absence. This is the clause that keeps `not_found` off the wire today, and it is a rule
    rather than a caller's discipline.
    """
    unbuilt = {RungId.L5, RungId.L6, RungId.LR}
    partial = LadderAccount(
        accounts=tuple(not_applicable(rung) for rung in LADDER if rung not in unbuilt)
    )
    assert not partial.covers(LADDER)
    assert outcome_of(account=partial, disclosed=0, evidence=0, hits=0) is Outcome.INCONCLUSIVE
    # ...and the same evidence over a complete ladder is `not_found`, so the clause is doing
    # the work rather than something else in the function.
    assert (
        outcome_of(account=complete_account(), disclosed=0, evidence=0, hits=0) is Outcome.NOT_FOUND
    )


def test_answered_needs_disclosure_and_evidence_the_query_itself_produced() -> None:
    """I-4's confident-but-wrong shape: rows without query evidence are not an answer."""
    account = complete_account()
    assert outcome_of(account=account, disclosed=3, evidence=2, hits=3) is Outcome.ANSWERED
    assert outcome_of(account=account, disclosed=3, evidence=0, hits=3) is Outcome.INCONCLUSIVE
    assert (
        outcome_of(account=account, disclosed=3, evidence=2, hits=3, unfetched_pages=True)
        is Outcome.INCONCLUSIVE
    )


# --- the shape matrix, and the one property every shape shares ----------------------------


@dataclass(frozen=True)
class Shape:
    """One whole query, run end to end under one budget, and what it produced."""

    envelope: Envelope
    box: SyntheticMailbox
    api_calls: int
    budget: BudgetRequest

    @property
    def report(self) -> RetrievalReport:
        return self.envelope.retrieval_report


def answer(
    query: str,
    *,
    budget: BudgetRequest | None = None,
    clock: FakeClock | None = None,
    box: SyntheticMailbox | None = None,
) -> Shape:
    """One query, through the real ladder and the real assembly, under one budget."""
    box = box if box is not None else mailbox()
    client = make_client(box)
    ledger = DispositionLedger()
    accountant = BudgetAccountant(
        client.meter, apply_floor(budget or BudgetRequest()), now_ms=clock or FakeClock()
    )
    run = LadderRunner(client, ledger, accountant=accountant).run(query, now=NOW, zone=UTC_ZONE)
    envelope = assemble(run, client=client, ledger=ledger, accountant=accountant)
    return Shape(
        envelope=envelope,
        box=box,
        api_calls=client.meter.reading().api_calls,
        budget=budget or BudgetRequest(),
    )


def shapes() -> dict[str, Shape]:
    """Every shape the commonality below asserts about, built from conditions not from a list.

    The conditions are the three states a rung can be in and the outcomes they produce, and
    each entry says which of them it exists to reach. What this matrix reaches is asserted
    over the **answers** in
    `test_the_shape_matrix_reaches_every_state_and_every_outcome_it_asserts_about`, never
    over these keys - which is R-RETR-058's lesson: round 21's equivalent asserted over the
    dict keys, so four clauses of its property could not fail and BLOCKER ADV-002's own
    defect left it green.
    """
    built: dict[str, Shape] = {}

    # Ordinary hit-bearing query: L0/L1 run, L2/L3 are declined because evidence exists.
    built["answered/plain"] = answer(MARKER)
    # A query naming an operator and a term: L1b decomposes, so a rung that only runs on a
    # multi-constraint query is in the RAN state somewhere in the matrix.
    built["answered/decomposed"] = answer(f"from:ana@team.example {MARKER}")
    # Zero evidence: L2 and L3 run, because there is nothing to stop for.
    built["empty/relaxed"] = answer(f"from:ana@team.example {ABSENT}")
    # Zero evidence and nothing to relax: L2 has no plannable drop at all.
    built["empty/unrelaxable"] = answer(ABSENT)
    # An exact-operator lookup: D.3 rule 1 halts the ladder at L0, so every later rung is
    # `stopped_on_evidence` rather than `not_applicable`.
    built["answered/exact"] = answer(f"rfc822msgid:{msgid('a1')}")
    # The budget stops the ladder before its first probe: every rung is blocked by a cap.
    built["blocked/before_the_first_probe"] = answer(MARKER, budget=BudgetRequest(max_api_calls=0))
    # The budget stops the ladder mid-way: L0 and L1 ran, the map stage did not.
    built["blocked/before_the_maps"] = answer(MARKER, budget=BudgetRequest(max_api_calls=2))
    # The deadline arrives while the ladder is running. The clock ticks per reading, so the
    # stop lands at a known probe rather than after an unknown number of milliseconds.
    built["blocked/timeout"] = answer(
        f"from:ana@team.example {ABSENT}", clock=TickingClock(MAX_SERVER_MS / 2)
    )
    # ...and the deadline arriving **between two probes of one rung**, which is the mid-rung
    # case: that rung is in `rungs` and in `not_tried` at once, and both are true. A third of
    # the deadline per clock reading is what puts the stop inside L1b's two-probe plan; the
    # matrix asserts the shape was reached rather than trusting the arithmetic.
    built["blocked/mid_rung"] = answer(
        f"from:ana@team.example {ABSENT}", clock=TickingClock(MAX_SERVER_MS / 3)
    )
    # A budget under the floor, clamped up and declared.
    built["answered/clamped"] = answer(MARKER, budget=BudgetRequest(max_quota_units=10))
    # The budget stops **L4** - the structural rung, which is neither a lexical probe nor a
    # map. Without this shape the accountant is asserted at three of its four consultation
    # points, which is exactly "one shape validated, peers trusted" inside the round's own
    # budget work. It is also the only shape that discloses sources *and* names a cap, which
    # is D.3 rule 5's own case: an answer beside a route not taken.
    built["blocked/structural"] = answer(MARKER, budget=BudgetRequest(max_api_calls=9))
    return built


#: Built once. Every one of these runs a whole query end to end, and the property below reads
#: them all rather than re-running them per clause.
SHAPES: dict[str, Shape] = shapes()


def test_every_rung_is_accounted_for_in_exactly_one_state() -> None:
    """The one property every shape shares, asserted over all of them at once.

    A list of tests over seven rungs times three outcomes times the timeout contract is a
    list of chances to have missed one. What every cell has in common is the account:

        every rung of the ladder is in exactly one of three states, the state is recorded
        when the rung is reached, and `rungs`, `not_tried`, `budget_caps_hit` and `outcome`
        are all read off that one record.

    Each clause below is one way that could be false.
    """
    for name, shape in SHAPES.items():
        report = shape.report
        because = f"shape {name}"

        # (a) Totality, and the one case where a rung is legitimately in both lists.
        #
        #     A rung in *neither* is a rung the response has no account of - the silence
        #     `not_tried` exists to break. A rung in both is the **mid-rung** case and it is
        #     not two accounts of one fact: the probes that ran produced evidence the reader
        #     must be able to see, and the probes that did not are work the caller is owed a
        #     call for. `Envelope` refuses a `rungs` that omits a rung which admitted ids, so
        #     a mid-rung stop reported only as `not_tried` is unbuildable - which is how this
        #     clause came to be written as disjointness first and corrected by execution.
        ran_rungs = {rung.value for rung in report.rungs}
        untried = {entry.rung for entry in report.not_tried}
        lexical = {rung.value for rung in (RungId.L0, RungId.L1, RungId.L1B, RungId.L2, RungId.L3)}
        assert lexical <= (ran_rungs | untried), because
        for both in ran_rungs & untried:
            entry = next(e for e in report.not_tried if e.rung == both)
            assert entry.why in BLOCKING_NOT_TRIED, f"{because}: {both} ran and was not tried"
            assert any(scan.rung.value == both for scan in report.scan_scope), (
                f"{because}: {both} is in `rungs` and must have a declared probe to show for it"
            )

        # (b) `not_applicable` is exactly the reason with no affordance. No budget reaches a
        #     rung that does not apply, and every other reason has a call that does.
        for entry in report.not_tried:
            assert (entry.why is NotTriedWhy.NOT_APPLICABLE) == (entry.affordance is None), (
                f"{because}: {entry.rung}:{entry.why.value}"
            )

        # (c) A cap named in `not_tried` is a cap named in `budget_caps_hit`, and **the
        #     affordance is the one that reaches what that reason blocked**. An affordance
        #     that merely exists is not AD-03's: a rung a cap stopped needs the call that
        #     raises *that cap*, and a rung the policy declined needs `force_rungs`. Offering
        #     `force_rungs` for a budget stop sends the caller to re-run a rung under the
        #     same exhausted budget, which reaches nothing - the dead-end-reported-as-a-fact
        #     shape wearing an affordance.
        by_cap = {NotTriedWhy.CAP, NotTriedWhy.TIMEOUT, NotTriedWhy.BUDGET}
        if any(entry.why in by_cap for entry in report.not_tried):
            assert report.budget_caps_hit, because
        named_caps = {cap.value for cap in report.budget_caps_hit}
        for entry in report.not_tried:
            if entry.why in by_cap:
                assert entry.affordance is not None
                raised = entry.affordance.args.get("budget")
                assert isinstance(raised, dict), f"{because}: {entry.rung} offers no budget"
                assert set(raised) <= named_caps, (
                    f"{because}: {entry.rung} offers {sorted(raised)} for caps {named_caps}"
                )
            elif entry.why is NotTriedWhy.STOPPED_ON_EVIDENCE:
                assert entry.affordance is not None
                assert entry.affordance.args.get("force_rungs") == [entry.rung], because

        # (d) OD-2. `not_found` exactly when nothing was left untried for a blocking reason,
        #     no cap fired, nothing was withheld and no page went unfetched.
        blocking = any(entry.why in BLOCKING_NOT_TRIED for entry in report.not_tried)
        unfetched = any(entry.more_pages for entry in report.scan_scope)
        if report.outcome is Outcome.NOT_FOUND:
            assert not blocking and not report.budget_caps_hit, because
            assert not shape.envelope.withheld and not unfetched, because
        if blocking or report.budget_caps_hit or shape.envelope.withheld or unfetched:
            assert report.outcome is not Outcome.NOT_FOUND, because

        # (e) `answered` is a claim that the query was answered.
        if report.outcome is Outcome.ANSWERED:
            assert shape.envelope.sources, because
            assert any(source.messages for source in shape.envelope.sources), because

        # (f) `hit_count_per_rung` covers exactly the rungs listed as having run, and is
        #     read off the ledger rather than accepted as an argument - so a rung that
        #     admitted ids and was left out of `rungs` cannot be assembled at all.
        counts = dict(zip(report.rungs, report.hit_count_per_rung, strict=True))
        assert {rung.value for rung in counts} == ran_rungs, because

        # (g) The timeout contract's first two clauses: what was retrieved is emitted, and
        #     the unfinished work is `not_tried` under the cap's own reason. A rung that
        #     admitted ids and is *also* blocked is the mid-rung case, and it is the ids that
        #     must survive - `H = disclosed u withheld` is the ledger's and is certified on
        #     every build, so reaching this line at all is the emission half.
        if report.budget_caps_hit:
            assert report.outcome is Outcome.INCONCLUSIVE, because

        # (h) The spend never exceeded the applied budget, and the applied budget was never
        #     below the floor.
        applied = apply_floor(shape.budget)
        assert report.counters.api_calls <= applied.max_api_calls, because
        assert report.counters.quota_units <= applied.max_quota_units, because
        assert applied.max_quota_units >= FLOOR_QUOTA_UNITS, because
        if shape.envelope.budget.clamped is not None:
            assert shape.envelope.budget.clamped.applied == FLOOR_QUOTA_UNITS, because

        # (i) Nothing retrieved is lost, in any shape. This is the ledger's certificate
        #     rather than a second computation, and it is asserted here because the whole
        #     timeout contract rests on it.
        certificate = shape.envelope.disposition
        assert certificate.hit_count == (
            certificate.disclosed_hits + len(certificate.withheld_ids)
        ), because


def test_the_shape_matrix_reaches_every_state_and_every_outcome_it_asserts_about() -> None:
    """R-RETR-058's lesson, applied to this round's own commonality test.

    Every assertion here is over a **produced answer** rather than over the names in
    `SHAPES`. Round 21's equivalent asserted `{"handle_stale/warm", ...} <= set(shapes)` -
    which is a statement about how the shapes were built - while no shape it built ever
    served from the cache or came back clean, so four clauses of the property could not fail
    and planting BLOCKER ADV-002's own defect left the whole thing green.

    Each assertion names the clause it keeps honest, so a matrix that stops reaching a shape
    reports which clause has just gone vacuous rather than silently asserting nothing.
    """
    reports = [shape.report for shape in SHAPES.values()]
    entries = [entry for report in reports for entry in report.not_tried]

    # Clause (a): a rung in each of the three states, somewhere in the matrix.
    assert any(report.rungs for report in reports), "clause (a): a rung that RAN"
    assert any(e.why is NotTriedWhy.NOT_APPLICABLE for e in entries), "clause (a)/(b): absent"
    assert any(e.why in BLOCKING_NOT_TRIED for e in entries), "clause (a)/(b): BLOCKED"

    # Clause (b): both sides of the affordance biconditional.
    assert any(e.affordance is None for e in entries), "clause (b)'s no-affordance side"
    assert any(e.affordance is not None for e in entries), "clause (b)'s affordance side"

    # Clause (b)/(c): each blocking reason the built ladder can produce, and the ruling's own.
    produced = {entry.why for entry in entries}
    assert NotTriedWhy.STOPPED_ON_EVIDENCE in produced, "round 22's ruling, actually produced"
    assert NotTriedWhy.CAP in produced or NotTriedWhy.BUDGET in produced, "a cap-blocked rung"
    assert NotTriedWhy.TIMEOUT in produced, "clause (c)/(g): a rung blocked by the deadline"

    # Clause (c), (g), (h): a run that hit a cap, and one that did not.
    assert any(report.budget_caps_hit for report in reports), "clause (c): a cap actually hit"
    assert any(not report.budget_caps_hit for report in reports), "clause (c)'s other side"
    assert any(
        cap in {BudgetCapName.MAX_SERVER_MS, BudgetCapName.MAX_SEMANTIC_MS}
        for report in reports
        for cap in report.budget_caps_hit
    ), "clause (g): a *time* cap, not only a call cap"

    # Clause (d), (e): every outcome the built ladder can reach, reached.
    outcomes = {report.outcome for report in reports}
    assert Outcome.ANSWERED in outcomes, "clause (e)"
    assert Outcome.INCONCLUSIVE in outcomes, "clause (d)"
    # `not_found` is deliberately absent and its absence is asserted, not assumed: L5, L6 and
    # LR are unbuilt, so no response of this build may claim exhaustion. The rule that keeps
    # it off the wire is executed by
    # `test_a_ladder_missing_a_rung_entirely_cannot_say_not_found`, and the day those rungs
    # exist this assertion is what will fail and say so.
    assert Outcome.NOT_FOUND not in outcomes, (
        "no response of this build may say not_found while L5, L6 and LR are unbuilt; if "
        "this fails, the ladder grew a rung and the matrix should now reach not_found"
    )

    # Clause (h): a clamped budget and an unclamped one.
    assert any(s.envelope.budget.clamped is not None for s in SHAPES.values()), "clause (h) clamp"
    assert any(s.envelope.budget.clamped is None for s in SHAPES.values()), "clause (h) no clamp"

    # Clause (i): a response that withheld something, and one that did not.
    assert any(s.envelope.withheld for s in SHAPES.values()), "clause (i): a withheld record"
    assert any(not s.envelope.withheld for s in SHAPES.values()), "clause (i)'s other side"

    # Clause (d)'s "a cap fired and something was still disclosed" case - D.3 rule 5's own
    # shape, and the one where `answered` would be the tempting wrong answer.
    assert any(
        report.budget_caps_hit and s.envelope.sources
        for s, report in ((s, s.report) for s in SHAPES.values())
    ), "clause (d): a cap fired over a response that had disclosed something"
    # ...and L4 blocked by a cap, so the accountant is witnessed at the structural rung too.
    assert any(
        entry.rung == RungId.L4.value and entry.why in BLOCKING_NOT_TRIED
        for report in reports
        for entry in report.not_tried
    ), "the structural rung, blocked by a budget"

    # Clause (a)'s "in both lists" branch. Without a shape that reaches it, that branch is a
    # loop over an empty set and the mid-rung contract is asserted by nothing.
    assert any(
        {rung.value for rung in report.rungs} & {entry.rung for entry in report.not_tried}
        for report in reports
    ), "clause (a)'s mid-rung branch: a rung that ran part-way and is reported both ways"


# --- the mid-rung timeout contract, named and executed ------------------------------------


def test_a_budget_that_stops_the_maps_emits_what_it_retrieved_and_withholds_the_rest() -> None:
    """The three clauses of the mid-rung contract, in one run. A timeout is not permission
    to forget.

      * **emit what was retrieved** - the probes that ran are in `scan_scope` and their ids
        are in `H`;
      * **unfinished work becomes `not_tried`** - the rungs that did not run carry the cap's
        own reason and the call that raises it;
      * **undisclosed members of `H` become withheld** - by the ledger's set difference,
        which this layer reads rather than recomputes.
    """
    shape = answer(MARKER, budget=BudgetRequest(max_api_calls=2))
    report = shape.report
    envelope = shape.envelope

    assert report.scan_scope, "the probes that ran are declared"
    assert envelope.disposition.hit_count, "and their ids are in H"
    assert report.budget_caps_hit == (BudgetCapName.MAX_API_CALLS,)
    blocked = [e for e in report.not_tried if e.why in BLOCKING_NOT_TRIED]
    assert blocked, "the unfinished work is reported"
    assert all(e.affordance is not None for e in blocked)
    # Nothing was disclosed, so by A.7a's identity every hit is a withheld record - and each
    # one names the cap that cost it and carries the call that raises it.
    assert not envelope.sources
    assert envelope.withheld
    assert {record.cap for record in envelope.withheld} == {WithheldCap.MAX_API_CALLS}
    assert all(record.affordance is not None for record in envelope.withheld)
    assert report.outcome is Outcome.INCONCLUSIVE


def test_a_rung_stopped_part_way_keeps_the_probes_that_ran() -> None:
    """The mid-rung case at the *rung* rather than at the map stage.

    L2 plans one probe per droppable constraint. Under a budget that expires between them,
    the probes that ran keep their ids and their `scan_scope` entries, and the rung is
    reported blocked - not `not_applicable`, and not silently complete.
    """
    box = mailbox()
    client = make_client(box)
    ledger = DispositionLedger()
    clock = TickingClock(MAX_SERVER_MS / 3)
    accountant = BudgetAccountant(client.meter, apply_floor(BudgetRequest()), now_ms=clock)
    run = LadderRunner(client, ledger, accountant=accountant).run(
        f"from:ana@team.example {ABSENT}", now=NOW, zone=UTC_ZONE
    )
    partial = [e for e in run.executions if e.skipped is NotTriedWhy.TIMEOUT and e.executed]
    stopped = [e for e in run.executions if e.skipped is NotTriedWhy.TIMEOUT]
    assert stopped, "the deadline arrived while the ladder was running"
    assert partial, (
        "no rung was stopped part-way, so the loop below would assert nothing - the tick "
        "must land between two probes of one rung, not between two rungs"
    )
    assert run.rungs_cut_short == tuple(e.rung for e in partial)
    for execution in partial:
        assert len(execution.executed) < len(execution.planned), "part-way, not all-or-nothing"
        assert execution.affordance is not None
        assert execution.cap in {BudgetCapName.MAX_SERVER_MS, BudgetCapName.MAX_SEMANTIC_MS}
    # Whatever the probes that ran observed is still in the ledger.
    assert ledger.scan_scope, "the probes that ran are declared"


def test_no_response_this_build_can_produce_says_not_found() -> None:
    """The exit condition, over every shape in the matrix and the empty cases besides.

    "No response says `not_found` when it stopped looking" is the round's exit condition, and
    while L5, L6 and LR are unbuilt every response of this build has stopped looking. This is
    the end-to-end half; `test_a_ladder_missing_a_rung_entirely_cannot_say_not_found` is the
    rule that produces it.
    """
    for name, shape in SHAPES.items():
        assert shape.report.outcome is not Outcome.NOT_FOUND, name
    for query in (ABSENT, f'"{ABSENT} nothing that matches"', f"subject:{ABSENT} {ABSENT}"):
        result = answer(query)
        assert not result.envelope.sources, query
        assert result.report.outcome is Outcome.INCONCLUSIVE, query
