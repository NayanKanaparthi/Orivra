"""The one record every rung of the ladder appears in, and what the response reads off it.

**The commonality, stated once, because it is what makes seven rungs times three outcomes
times the timeout contract one shape instead of twenty-one.**

    Every rung of the ladder is, at every moment, in exactly one of three accounted states -
    **ran**, **not applicable**, or **blocked** - the state is decided before the rung is
    reached and recorded when it is; and the response's `rungs`, `not_tried`,
    `budget_caps_hit` and `outcome` are all read off that one record rather than derived a
    second time from the run.

From that one shape, five things follow for the whole ladder at once, and one test executes
them over every rung in every state rather than one test per cell
(`tests/test_ws10_escalation.py::test_every_rung_is_accounted_for_in_exactly_one_state`):

  * **total** - `rungs_run` and `not_tried` partition the ladder. A rung in neither is a rung
    the response has no account of, which is the silence `not_tried` exists to break; a rung
    in both is two accounts of one fact;
  * **blocked implies reachable** - a rung blocked by budget, cap, timeout or error carries
    the affordance that would reach it (AD-03). `not_applicable` carries none and can carry
    none: no budget reaches a rung that does not apply;
  * **blocked implies a named cap** - every `cap`/`timeout` entry names a cap that is also in
    `budget_caps_hit`, so the two blocks cannot disagree about whether a budget was hit;
  * **the outcome follows from the record** - `not_found` exactly when no rung is untried for
    a blocking reason, no cap fired, nothing is withheld and no page is unfetched. Otherwise
    `inconclusive`, or `answered` when something was disclosed. OD-2, computed in one place;
  * **a rung that did not run costs nothing** - no `not_tried` rung appears in the ledger's
    per-rung hit counts.

**What this module deliberately does not do.** It does not compute `withheld`: that is
`DispositionLedger.certify`'s, over the ids every observation recorded, and a second
computation here would be the shape the disposition seal exists to prevent. It reads the
ledger's answer and refuses to say `not_found` over it.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from mailweave.envelope.reasons import RungId
from mailweave.envelope.vocab import (
    BLOCKING_NOT_TRIED,
    BudgetCapName,
    NotTriedWhy,
    Outcome,
    ToolName,
)
from mailweave.envelope.wire import Affordance, NotTriedEntry
from mailweave.policy.budget import CapBreach


class RungState(StrEnum):
    """The three states a rung can be in, and there is no fourth.

    `BLOCKED` covers all five blocking `why` values at once - budget, cap, timeout, error and
    `stopped_on_evidence` - because what they have in common is the thing the account is
    about: the rung was applicable and did not run, so the response owes the caller a way to
    reach it. Which of the five it was is carried by `RungAccount.why`.
    """

    RAN = "ran"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"


def force_rungs(rung: RungId, *, query: str) -> Affordance:
    """WS-15's `force_rungs`, which "can only add rungs" (AD D.1, implementation plan WS-15).

    The affordance for a rung the policy declined to run on the strength of evidence it had
    already found. It is the operational half of round 22's `stopped_on_evidence` ruling: the
    value exists because there is a call that gets you the rung, and `not_applicable` has no
    such call. Minted here so every producer of that value mints the same one.

    **`query` is required, and round 24 made it so.** Contract R-07 calls an affordance "a
    concrete, executable call", and `{"force_rungs": ["L2"]}` is not one: `mailweave_search`
    requires a query, so a client following this affordance verbatim would have sent a call
    the surface refuses. Nothing detected that until WS-15 gave the arguments a schema and
    `test_every_affordance_this_server_mints_is_a_valid_argument` ran every minted
    affordance through the parser of the tool it names.
    """
    return Affordance(tool=ToolName.SEARCH, args={"query": query, "force_rungs": [rung.value]})


@dataclass(frozen=True)
class RungAccount:
    """One rung's state, with everything the response needs to say about it.

    Validated on construction rather than at the reader, so the two impossible records - a
    blocked rung with no reason, and a `not_applicable` rung carrying an affordance - cannot
    be built at all.
    """

    rung: RungId
    state: RungState
    #: `None` exactly when the rung ran. Never `not_applicable` on a `BLOCKED` rung.
    why: NotTriedWhy | None = None
    affordance: Affordance | None = None
    #: The cap that blocked this rung, when a cap did. Carried so `budget_caps_hit` and
    #: `not_tried` cannot disagree about which cap fired.
    cap: BudgetCapName | None = None
    #: How many probes of this rung's plan ran before it was stopped. Non-zero with
    #: `state=BLOCKED` is the **mid-rung** case: work was retrieved and the remainder is
    #: `not_tried`, which is the timeout contract's first two clauses.
    probes_executed: int = 0
    probes_planned: int = 0

    def __post_init__(self) -> None:
        if self.state is RungState.RAN:
            if self.why is not None or self.affordance is not None:
                raise ValueError(
                    f"{self.rung.value} ran, so it has no `not_tried` reason and no "
                    "affordance to reach it; a rung that ran and is also reported as not "
                    "tried is two accounts of one fact"
                )
            return
        if self.why is None:
            raise ValueError(f"{self.rung.value} did not run and no reason is recorded")
        if self.state is RungState.NOT_APPLICABLE:
            if self.why is not NotTriedWhy.NOT_APPLICABLE:
                raise ValueError(
                    f"{self.rung.value} is recorded not-applicable with why={self.why.value}; "
                    "the two are one fact and disagreeing is how a blocked rung comes to look "
                    "like an inapplicable one, which is exactly the OD-2 distinction"
                )
            if self.affordance is not None:
                raise ValueError(
                    f"{self.rung.value} could not have helped this query, so no call reaches "
                    "it; an affordance here offers the caller a budget that changes nothing"
                )
            return
        if self.why not in BLOCKING_NOT_TRIED:
            raise ValueError(
                f"{self.rung.value} is blocked with why={self.why.value}, which is the one "
                "value OD-2 makes compatible with not_found"
            )
        if self.affordance is None:
            raise ValueError(
                f"{self.rung.value} was applicable and did not run, so the response owes the "
                "caller the call that would reach it (AD-03)"
            )

    @property
    def entry(self) -> NotTriedEntry | None:
        """This rung's `not_tried` line, or `None` when it ran."""
        if self.state is RungState.RAN or self.why is None:
            return None
        return NotTriedEntry(rung=self.rung.value, why=self.why, affordance=self.affordance)

    @property
    def partially_executed(self) -> bool:
        """The mid-rung shape: some of this rung's plan ran and the rest did not."""
        return self.state is RungState.BLOCKED and 0 < self.probes_executed < self.probes_planned


def blocked_by(rung: RungId, breach: CapBreach) -> RungAccount:
    """The account for a rung a cap stopped. One constructor, so no cap invents its own."""
    return RungAccount(
        rung=rung,
        state=RungState.BLOCKED,
        why=breach.why,
        affordance=breach.affordance,
        cap=breach.cap,
    )


def stopped_on_evidence(rung: RungId, *, query: str) -> RungAccount:
    """The account for a rung a D.3 stop rule made unnecessary. Round 22's ruling, applied.

    `query` is the caller's own, because the affordance this account carries has to be a
    call `mailweave_search` accepts and that tool requires one (round 24).
    """
    return RungAccount(
        rung=rung,
        state=RungState.BLOCKED,
        why=NotTriedWhy.STOPPED_ON_EVIDENCE,
        affordance=force_rungs(rung, query=query),
    )


def not_applicable(rung: RungId) -> RungAccount:
    return RungAccount(rung=rung, state=RungState.NOT_APPLICABLE, why=NotTriedWhy.NOT_APPLICABLE)


def ran(rung: RungId, *, probes: int = 0) -> RungAccount:
    return RungAccount(
        rung=rung, state=RungState.RAN, probes_executed=probes, probes_planned=probes
    )


#: The rungs AD A.7 publishes, in the order the ladder attempts them. L7 is disclosure
#: assembly rather than retrieval and has no `RungId`.
LADDER: Final[tuple[RungId, ...]] = (
    RungId.L0,
    RungId.L1,
    RungId.L1B,
    RungId.L2,
    RungId.L3,
    RungId.LR,
    RungId.L4,
    RungId.L5,
    RungId.L6,
)


@dataclass(frozen=True)
class LadderAccount:
    """Every rung's state for one query, and the three response fields read off it."""

    accounts: tuple[RungAccount, ...]

    def __post_init__(self) -> None:
        seen = [account.rung for account in self.accounts]
        if len(set(seen)) != len(seen):
            raise ValueError("a rung appears twice in the account; each rung has one state")

    @property
    def by_rung(self) -> Mapping[RungId, RungAccount]:
        return {account.rung: account for account in self.accounts}

    @property
    def rungs_run(self) -> tuple[RungId, ...]:
        return tuple(a.rung for a in self.accounts if a.state is RungState.RAN)

    @property
    def not_tried(self) -> tuple[NotTriedEntry, ...]:
        return tuple(entry for a in self.accounts if (entry := a.entry) is not None)

    @property
    def blocked(self) -> tuple[RungAccount, ...]:
        return tuple(a for a in self.accounts if a.state is RungState.BLOCKED)

    @property
    def caps_named(self) -> tuple[BudgetCapName, ...]:
        """Every cap named by a blocked rung, deduplicated, in first-blocked order."""
        ordered: list[BudgetCapName] = []
        for account in self.accounts:
            if account.cap is not None and account.cap not in ordered:
                ordered.append(account.cap)
        return tuple(ordered)

    def covers(self, ladder: Collection[RungId] = LADDER) -> bool:
        """Every rung of `ladder` has exactly one account here. Totality, as a predicate."""
        return {a.rung for a in self.accounts} >= set(ladder)


def outcome_of(
    *,
    account: LadderAccount,
    disclosed: int,
    evidence: int,
    hits: int,
    caps_hit: Iterable[BudgetCapName] = (),
    unfetched_pages: bool = False,
    applicable: Collection[RungId] = LADDER,
) -> Outcome:
    """OD-2's three-way outcome, computed in one place from the record above.

    **The honesty centre of WS-10, so the rule is written as the document writes it.**
    `not_found` **only** when no applicable rung is untried for budget, cap, timeout or
    error - and, under round 22's ruling, not while one is untried because the policy stopped
    on evidence either - *and* `budget_caps_hit` is empty. Otherwise `inconclusive`.
    MailWeave never claims a mailbox does not contain something when it simply stopped
    looking.

    Two further conditions come from OD-2's own word "exhausted" rather than from its list of
    causes, and both are already refused by `RetrievalReport`/`Envelope`'s validators. They
    are computed here as well, and that is deliberate rather than duplicated: the validator's
    job is to refuse a dishonest response, and this function's job is to produce an honest
    one. A producer that emitted `not_found` and relied on a validator to convert it would be
    a producer with no opinion, and the first response it got wrong would be an exception
    rather than an answer.

      * **withheld** - a withheld record is retrieved evidence. Saying nothing was found
        contradicts the response's own `withheld` array. It is passed here as `hits`, the
        size of `H`, and **not** as a withheld count, because computing one would mean
        computing `H - disclosed` a second time: that set difference is
        `DispositionLedger.certify`'s and two derivations of it can disagree, which is the
        shape the disposition seal exists to prevent. The identity that makes `hits` the
        right input is A.7a's own: `H = disclosed u withheld`, and this clause is reached
        only when nothing was disclosed, so every hit is a withheld record;
      * **unfetched pages** - ids on pages nobody fetched were never examined, so the
        applicable path was not exhausted;
      * **a rung with no account at all** - `applicable` is the ladder OD-2 measures
        exhaustion against, and a rung this build does not have cannot have been "actually
        executed and exhausted". Today L5, L6 and LR are unbuilt, so `not_found` is
        unreachable end to end and this function says so **by the rule** rather than by the
        caller remembering not to ask for it. There is no honest `not_tried[].why` for "this
        rung does not exist yet" - `not_applicable` claims it could not have helped and
        `budget` claims a budget would reach it - so the absence is read as an absence
        instead of written as a reason. When WS-12 and WS-13 land, `not_found` becomes
        reachable with no change here.

    `answered` needs something disclosed, *and* evidence the query itself produced, *and* no
    cap having fired. The second is I-4's confident-but-wrong shape: a response carrying only
    the threads a broad L1b probe obliged the ledger to disclose has rows and no evidence.
    The third is D.3 rule 5 read as it is written - a cap makes the outcome `inconclusive`,
    not merely not-`not_found` - and it is the clause that keeps a partial answer from
    contradicting its own `budget` block.
    """
    caps = tuple(caps_hit) or account.caps_named
    if caps:
        # **D.3 rule 5, verbatim: "Any cap exhausted => stop, emit, name the cap plus untried
        # rungs with affordances ... The outcome is `inconclusive`, never `not_found`."** Not
        # only never `not_found`: `inconclusive`. A response that disclosed three threads and
        # ran out of budget before L4 has an answer *and* a route it did not take, and the
        # document settles which of the two the outcome names. `answered` beside a named cap
        # would be the response contradicting its own `budget` block, which is the shape
        # R-RETR-016 found beside `more_pages`.
        return Outcome.INCONCLUSIVE
    if disclosed and evidence and not unfetched_pages:
        return Outcome.ANSWERED
    if disclosed:
        # Something is in the payload, so it is not a "found nothing" answer whatever else
        # is true - and the run's own account already refutes `answered`.
        return Outcome.INCONCLUSIVE
    stopped_looking = any(entry.why in BLOCKING_NOT_TRIED for entry in account.not_tried)
    if stopped_looking or caps or hits or unfetched_pages:
        return Outcome.INCONCLUSIVE
    if not account.covers(applicable):
        return Outcome.INCONCLUSIVE
    return Outcome.NOT_FOUND
