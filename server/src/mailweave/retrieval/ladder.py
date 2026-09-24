"""The lexical ladder: L0, L1, L1b, L2, L3 (AD A.2 step 2, A.6, A.7, D.3).

**What the five rungs have in common, stated once because it is the property that matters.**
A rung is a *plan* plus an *execution*, and the plan is a pure function of the parsed query:

    plan_ladder(parsed) -> every Probe every rung would send, before any of them is sent.

From that one shape, four things follow for all five rungs at once, and one test executes
them over the whole ladder rather than five tests executing them one rung at a time
(`tests/test_lexical_ladder.py::test_every_rung_shares_the_one_property_that_makes_the_
ladder_accountable`):

  * **enumerable** - ROUTE-03 asks this of L2 only; it is true of the whole ladder, so the
    probes L2 *would* send are listable before it sends them and so are everybody else's;
  * **reproducible** - the same `(query, now, zone)` produces the same plan, because
    nothing in a plan reads a clock, a counter or a previous rung's rows;
  * **accountable** - a rung executes a probe only through `GmailClient.list_messages`,
    which records the page into the `DispositionLedger` at the moment of the call. There is
    no path in this module that fetches ids without recording them, because there is no
    path in this module that fetches anything else;
  * **declared** - every executed probe leaves a `ScanScopeEntry` carrying the exact `q`,
    its own `RungId` and the page's own counts, so the response's account of what it
    scanned is the ledger's rather than this module's.

**What a rung is not.** It is not a policy about budgets, and it does not decide the
response's `outcome`. Those are WS-10's `budget_accountant` and the D.3 stopping rules in
full; what is here is the subset of D.3 that the lexical rungs alone can evaluate - rules 0,
1, 1b and 2 - and the escalation between lexical rungs. Rungs L4/L5/L6/LR do not exist yet
and this module does not pretend to have skipped them for a reason it can name.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar, Final
from zoneinfo import ZoneInfo

from mailweave.constants import (
    ANYWHERE_OPERATOR,
    BROADENING_DATE_FACTOR,
    DEFAULT_PAGE_SIZE,
    MAX_BODY_FETCHES_L0,
    MAX_BODY_FETCHES_L1,
    MAX_BROADENING_PROBES,
    MAX_DECOMPOSITION_PROBES,
    MAX_PAGES_PER_QUERY,
    carries_no_content,
    carries_nothing_but_mailbox_scope,
    max_relax_probes,
    widens_beyond_the_default_mailbox,
)
from mailweave.content.payload import MessagePayload
from mailweave.content.pipeline import ProcessedMessage, process_message
from mailweave.envelope.disposition import DispositionLedger
from mailweave.envelope.reasons import RungId
from mailweave.envelope.vocab import BudgetCapName, NotTriedWhy, ToolName
from mailweave.envelope.wire import Affordance
from mailweave.errors import ContentProcessingError, MailweaveError, QueryNotSearchable
from mailweave.gmail.client import GmailClient
from mailweave.gmail.rates import GmailEndpoint
from mailweave.policy.account import force_rungs
from mailweave.policy.budget import BudgetAccountant, CapBreach
from mailweave.policy.stopping import (
    StopInputs,
    StopRule,
    rule_1_stops,
    rule_1b_stops,
    rule_2_stops,
)
from mailweave.query.analysis import (
    PHRASE_CONSTRAINT,
    RELAXATION_ORDER,
    TERMS_CONSTRAINT,
    Constraint,
    ConstraintUnit,
    ParsedQuery,
    analyse,
    carries_nothing_to_select_by,
    constraints_carried_whole,
    region_declarations_of,
    search_region_of,
)
from mailweave.query.operators import (
    OperatorKind,
    OperatorName,
    declares_the_search_region,
    operator_of,
)
from mailweave.retrieval.signals import (
    AnswerTypePresence,
    ExactSignal,
    evaluate_answer_type_presence,
    evaluate_exact_signal,
)


def widen_scan(query: str, *, max_pages: int = MAX_PAGES_PER_QUERY + 2) -> Affordance:
    """The widening affordance every listing carries (GMAIL-04, A.7a).

    `GmailClient.list_messages` requires one before the first HTTP call, because
    `more_pages: true` without one is non-conforming and a caller cannot know in advance
    whether Gmail will send a page token.

    **A function of the query rather than a constant, since round 24.** The constant it
    replaces carried `{"scan": {"max_pages": n}}` and no query, which is not a call
    `mailweave_search` accepts - contract R-07's "concrete, executable call" failing on the
    most-minted affordance in the system. The caller's own `q` is what makes it executable,
    and it is a fact the listing already has.
    """
    return Affordance(tool=ToolName.SEARCH, args={"query": query, "scan": {"max_pages": max_pages}})


def why_this_q_is_not_a_probe(query: str) -> str | None:
    """Why this `q` is a **listing** rather than a probe, or `None` when it is a probe.

    One statement, read twice and for two different purposes: `Probe.__post_init__` raises
    on it, which makes the shape unrepresentable, and `FilteredRung.plan` declines to plan
    on it, which keeps the refusal from being a crash on an ordinary query. That pairing is
    the module's existing rule - "this one decides not to plan, which is a policy; that one
    makes the object unrepresentable" - written once instead of twice.

    **The rule here is deliberately narrower than `carries_nothing_to_select_by`**, and the
    difference is who wrote the query. This predicate judges the *user's own* `q`, so
    `-cutover` passes it: "everything except cutover" is a listing of the default mailbox
    and it is the listing the user asked for, which MailWeave has no business refusing. The
    rungs that compose a `q` out of a *subset* of the query's fragments - L1b's units, L2's
    drops, L3's broadening - read the wider predicate instead, because nobody asked for
    what they composed and a subset that selects nothing is a whole-mailbox read charged to
    a query that named something.

    Three shapes are refused. A `q` that names only **where** to look - a member of
    `WIDENING_MAILBOX_OPERATORS` and nothing else, in any of the case, grouping and fullwidth
    spellings `carries_nothing_but_mailbox_scope` normalises. A `q` that names only where to
    look and what to leave out while leaving the default mailbox, which asks Gmail for spam
    and trash minus a few messages on behalf of a query that named nothing to find. And -
    round 17's - a `q` **none of whose tokens names anything to match at all**, which is the
    empty `q` wearing quotes: an empty quoted phrase, a quoted space, `subject:` with no
    value, two empty phrases running together, a run of zero-width characters. That third
    one is not a narrower listing the user asked for, the way
    `-cutover` is; it filters nothing, so Gmail answers it with the entire mailbox exactly as
    an empty `q` does, which is what the first check already refuses under its own name
    (R-RETR-017). The operators are not spelled here: `mailweave.constants` writes them once
    and `test_no_module_spells_a_mailbox_scope_operator_outside_the_scope_enum` reads prose.
    """
    if not query.strip():
        return (
            "a probe with an empty q is not a probe: `ScanScopeEntry` refuses it, and a "
            "listing with no query asks Gmail for the whole mailbox"
        )
    if carries_no_content(query):
        return (
            f"a probe whose tokens name nothing to match is not a probe: {query!r} filters "
            "nothing, so Gmail answers it with the whole mailbox exactly as an empty q "
            "does. An empty quoted phrase is syntactically a phrase and semantically "
            "nothing, and an operator written with no value names no value; neither is a "
            "narrower listing the caller asked for (AD A.7 L3, R-RETR-017)"
        )
    if carries_nothing_but_mailbox_scope(query):
        return (
            f"a probe whose q is only a mailbox-scope operator is not a probe: {query!r} "
            "carries no fragment of the query and asks Gmail for the whole mailbox, "
            "spam and trash included, exactly as an empty q does. A rung that cannot "
            "narrow must not widen to everything instead (AD A.7 L3, R-RETR-006)"
        )
    if widens_beyond_the_default_mailbox(query) and carries_nothing_to_select_by(query):
        return (
            f"a probe that leaves the default mailbox must ask for something: {query!r} "
            "names only where to look and what to leave out, so it asks Gmail for spam "
            "and trash minus a few messages. The check above refuses the bare scope "
            "operator; this refuses the same request with a fragment of the query "
            "attached as a disguise (AD A.7 L3, R-RETR-006's peer shape)"
        )
    return None


@dataclass(frozen=True)
class Probe:
    """One `messages.list` a rung would execute, fully determined before it is sent.

    The field is `query` rather than `q` because the two mailbox-scope settings must travel
    on one object: round 12's coupling (R-SEC-051) requires `include_spam_trash` to be read
    off the same value the query came from, and `test_the_two_scope_settings_cannot_be_
    supplied_independently` fails the build on a call site that supplies them separately. A
    `Probe` is a stronger form of that pairing than the harness's `MailboxScope`, because
    its flag is **derived from** its query rather than declared beside it.
    """

    rung: RungId
    query: str
    why: str
    #: Constraints this probe carries into its `q`.
    enforced: tuple[str, ...] = ()
    #: Constraints this probe does **not** carry. Two rungs produce a non-empty value here
    #: and they mean different things, which is what `relaxes` is for.
    dropped: tuple[str, ...] = ()
    #: Whether not carrying `dropped` means the *query* gave those constraints up.
    #:
    #: True at L2 and nowhere else. A decomposition probe (L1b) also carries one constraint
    #: at a time, but its siblings carry the rest and the intersection puts them back - so
    #: reading its `dropped` as an abandonment made `asked_for.dropped` name a constraint L1
    #: had enforced and matched on, and dragged `term_coverage` down with it. The two cases
    #: are told apart here rather than by a rung check at the reader, because a reader that
    #: knows which rungs abandon constraints is a second copy of this fact.
    relaxes: bool = False
    #: The decomposition unit this probe carries, when it carries one (L1b, and nowhere
    #: else). Two probes for two pieces of one constraint are two labels; `enforced` cannot
    #: tell them apart because a piece of a constraint enforces no constraint whole.
    unit: str | None = None

    def __post_init__(self) -> None:
        refusal = why_this_q_is_not_a_probe(self.query)
        if refusal is not None:
            raise ValueError(refusal)

    @property
    def include_spam_trash(self) -> bool:
        """Derived from this probe's own query, never stated beside it (R-SEC-051).

        The `in:` operator and the request parameter are independent inputs and nothing on
        Gmail's side makes them agree; `GmailClient._fetch_list_page` refuses a disagreeing
        pair. Deriving it here means a rung cannot compose a widening query and forget the
        flag - there is only one value and it is read off the string that will be sent.
        """
        return widens_beyond_the_default_mailbox(self.query)


class LexicalRung(ABC):
    """A rung of the lexical ladder: a plan, and a statement of when it does not apply."""

    rung: ClassVar[RungId]

    @abstractmethod
    def plan(self, parsed: ParsedQuery) -> tuple[Probe, ...]:
        """Every probe this rung would send for `parsed`, in the order it would send them."""

    def not_applicable(self, parsed: ParsedQuery) -> bool:
        return not self.plan(parsed)


def _ordered_for_relaxation(parsed: ParsedQuery) -> tuple[Constraint, ...]:
    """The query's constraints in `RELAXATION_ORDER`, ties broken by the order written.

    Published and total: every constraint kind this parser produces appears in
    `RELAXATION_ORDER`, and `test_the_relaxation_order_covers_every_constraint_kind_this_
    parser_produces` fails if a kind is added without a place in it - otherwise a new kind
    would sort to the front or the back by accident and the "documented order" ROUTE-03
    requires would be a property of `list.sort`.
    """
    rank = {name: index for index, name in enumerate(RELAXATION_ORDER)}
    return tuple(
        sorted(
            parsed.constraints,
            key=lambda constraint: (
                rank.get(constraint.kind, len(rank)),
                parsed.constraints.index(constraint),
            ),
        )
    )


class ExactOperatorRung(LexicalRung):
    """L0: the query's exact-operator form, and nothing else (A.7 L0, A.8a).

    One probe at most. Which one is decided by A.8a's branch precedence, so the query L0
    executes is the query the strongest available branch would need to fire on: an
    `rfc822msgid:` verbatim, else a qualifying quoted phrase as a Gmail quoted phrase, else
    a structured identifier as a quoted single-token query. Those are A.8a's own words for
    what each branch requires to have been *executed*, which is why the rung is written from
    them rather than from a convenient superset.

    **The branch fragment is carried in the region the query named**, like every other probe
    the ladder composes out of a subset of the query's fragments - see
    `decomposition_units_of` for the invariant and why it is stated there. Without it,
    a query naming the spam mailbox and a qualifying phrase probed the *default* mailbox at
    L0, could match an inbox message the query's own scope excluded, and D.3 rule 1b could
    then halt the ladder on it before L1 ever applied the scope. Carrying it can only narrow where
    the stop fires, which is the conservative direction.

    **The residue this leaves against A.8a's letter, named rather than glossed.** Branch E-c
    says the identifier is "executed as a quoted single-token query", and a `q` of
    a widening operator beside a quoted identifier is two tokens. The identifier is still
    executed as a quoted token and `evaluate_exact_signal` still finds it, so the branch fires
    as A.8a intends;
    what has changed is that it fires over the region the caller asked about instead of a
    different one. Whether A.8a's wording should be read as forbidding the scope conjunct is
    an architecture question and is recorded for the orchestrator, not decided here (AL 8).
    """

    rung = RungId.L0

    def _in_scope(self, parsed: ParsedQuery, query: str) -> str:
        region = search_region_of(parsed.constraints)
        return " ".join((*region, query))

    def _branch(self, parsed: ParsedQuery, fragment: str, why: str) -> Probe:
        """One L0 probe, with `enforced` **derived from the `q` it is about to send**.

        The branch fragment is one fragment of one constraint, and round 17's rule - a
        constraint is enforced only by a route that carried it whole - was written for L1b
        and L3 and never reached here (R-RETR-028). `PO-2026-0041 zephyr` executed
        `"PO-2026-0041"`, halted under D.3 rule 1b so no later rung could correct it, and
        reported `enforced ('terms',)` at `term_coverage 1.0` and `sufficiency: sufficient`
        over a row that does not contain "zephyr"; the same shape at branch E-b claimed the
        whole `phrase` constraint from the first of two phrases. The rule is now read from
        the string by `constraints_carried_whole`, which is the one place that knows it, so
        this rung cannot hold a different opinion and a rung written later inherits it.
        """
        query = self._in_scope(parsed, fragment)
        return Probe(
            rung=self.rung,
            query=query,
            why=why,
            enforced=constraints_carried_whole(query, parsed.constraints),
        )

    def plan(self, parsed: ParsedQuery) -> tuple[Probe, ...]:
        msgid = parsed.rfc822msgid
        if msgid is not None:
            return (
                self._branch(
                    parsed,
                    msgid.render(),
                    "exact lookup by RFC 822 message id (A.8a branch E-a)",
                ),
            )
        for phrase in parsed.qualifying_phrases:
            return (
                self._branch(
                    parsed,
                    f'"{phrase}"',
                    "verbatim quoted phrase, locally verified on the hits (A.8a branch E-b)",
                ),
            )
        for identifier in parsed.identifiers:
            return (
                self._branch(
                    parsed,
                    f'"{identifier.token}"',
                    f"structured identifier ({identifier.kind.value}) as a quoted "
                    "single-token query (A.8a branch E-c)",
                ),
            )
        return ()


class FilteredRung(LexicalRung):
    """L1: every provable operator plus the residual terms, as one Gmail `q` (A.7 L1).

    It plans nothing for a query that is a listing rather than a probe, and it **declines**
    rather than raising: a bare widening mailbox-scope operator is an ordinary Gmail query a
    caller can type, and answering one with an uncaught `ValueError` out of `plan_ladder` is
    a crash rather than the declared inability this round is about. `run_parsed` turns the
    empty ladder plan into the structured report ROUTE-01 requires, with the reason attached
    (round 17; before it, into an exception). Executed by
    `test_a_query_that_names_only_where_to_look_is_reported_not_scanned`.
    """

    rung = RungId.L1

    def plan(self, parsed: ParsedQuery) -> tuple[Probe, ...]:
        rendered = parsed.render()
        if why_this_q_is_not_a_probe(rendered) is not None:
            return ()
        return (
            Probe(
                rung=self.rung,
                query=rendered,
                why="every provable operator and residual term, as one message-scoped query",
                enforced=constraints_carried_whole(rendered, parsed.constraints),
            ),
        )


class DecompositionRung(LexicalRung):
    """L1b: one `messages.list` per decomposition unit, intersected on `threadId` (A.6, A.7).

    This rung exists because of RO F2, which is the fact the whole project turns on: Gmail's
    `q` is **message-scoped**, so every term must match within a single message and there is
    no thread operator (RO F3). A query whose parts are jointly satisfied by *different
    messages of one thread* therefore matches nothing at L1, however correct the parse was.
    Decomposition is the answer, and A.6 makes it "a first-class rung, not a fallback".

    **It plans over `parsed.decomposition_units`, not over constraints, and that is the
    difference between covering the founding bug and covering a corner of it**
    (R-RETR-008). All residual terms are one `terms` constraint - correctly, because
    dropping the query's subject is one relaxation step rather than one per word - so
    `"rollout cutover"`, two bare words spread across two messages of one thread, had k=1,
    planned nothing, and was reported `not_applicable`: the commonest shape of the bug this
    project exists to fix, unrecoverable, while round 15's fixture passed because its
    constraints happened to be an operator plus a term. A constraint now answers two
    different questions separately - how it is dropped, and how it is probed - and the
    change is at the constraint model rather than at this rung, so it holds for a repeated
    operator (`from:a from:b`) and a multi-phrase query for the same reason and by the same
    code. `test_two_bare_words_in_two_messages_of_one_thread_are_recovered` and
    `test_decomposition_splits_every_constraint_kind_whose_fragments_bind_separately`
    execute it.

    Capped at `MAX_DECOMPOSITION_PROBES` by A.7's cost row. With more units than that the
    intersection is taken over the first three in written order, which yields a *superset*
    of the true intersection - the candidate threads are then resolved by their thread maps
    - so the cap costs precision and never recall.
    """

    rung = RungId.L1B

    def plan(self, parsed: ParsedQuery) -> tuple[Probe, ...]:
        units = parsed.decomposition_units
        if len(units) < 2:
            return ()
        probes: list[Probe] = []
        for unit in units[:MAX_DECOMPOSITION_PROBES]:
            if not unit.fragment.strip():
                continue
            probes.append(self._probe(parsed, unit))
        return tuple(probes) if len(probes) >= 2 else ()

    def _probe(self, parsed: ParsedQuery, unit: ConstraintUnit) -> Probe:
        """One unit's probe. `enforced` names no constraint the unit carries only in part.

        A probe that carried one term of a two-term `terms` constraint and reported
        `enforced=("terms",)` would put that name into the row's `constraint_coverage` -
        the claim "this message satisfied the query's terms" - for a message carrying one
        of them. The wire vocabulary has no spelling for half a constraint, so the probe
        claims nothing about it and the row's `reason` carries the `q` that admitted it,
        which is the mechanical truth and is narrower than the query rather than wider.

        A unit carrying *several* whole constraints - a written-out date window - enforces
        all of them, and the row's coverage names all of them, because the message really
        did satisfy every one: it is inside the window.

        **The query's mailbox scope is on every unit's `q` and is therefore enforced by
        every one of these probes** (R-RETR-019). A row admitted by a scoped unit probe really
        is in the region the query named, so naming the scope constraint in its coverage is
        a claim the probe carried; `decomposition_units_of` composes the fragment and states
        the invariant.
        """
        enforced = constraints_carried_whole(unit.fragment, parsed.constraints)
        carried = frozenset(enforced)
        return Probe(
            rung=self.rung,
            query=unit.fragment,
            why=(
                f"decomposed unit {unit.label!r}; Gmail q is message-scoped, so parts of a "
                "query spread across a thread are intersected on threadId client-side "
                "(RO F2, AD A.6)"
            ),
            enforced=enforced,
            dropped=tuple(
                other.name for other in parsed.constraints if carried and other.name not in carried
            ),
            unit=unit.label,
        )


class RelaxationRung(LexicalRung):
    """L2: drop exactly one constraint per probe, in the published order (A.7 L2, ROUTE-03).

    "Dumb, ordered, and logged - which is what makes it recoverable." The order is
    `RELAXATION_ORDER`, the count is `max_relax_probes(k) = min(k, 6)`, and a probe whose
    remaining constraints render an empty `q` is not planned, because a listing with no
    query asks Gmail for the whole mailbox rather than for a relaxation of this one.

    **That sentence covers one more shape than the code used to test for.** A `q` of
    `-cutover` is not empty and is not a relaxation either: what remains after the drop says
    only what to leave out, so Gmail answers with the mailbox minus a few messages. The
    condition is now the rung's own sentence rather than a proxy for it
    (`carries_nothing_to_select_by`), and the drop is reported as untried, which is what
    `untried_drops` takes `probed` as a parameter for. Executed by
    `test_a_relaxation_that_would_leave_nothing_to_select_by_is_untried_not_sent`.

    **And a third shape, which is round 18's: the region is not relaxable.** A drop that
    removes a fragment declaring the search region does not widen the search inside the
    region the caller named - it moves it to a different region, where it can return exactly
    the messages a negated spam scope excluded. `_relaxed_query` refuses it for that reason
    and `untried_drops` reports it, which is the same treatment a drop no budget can reach
    already gets (OD-5 point 3, A9-A2).
    """

    rung = RungId.L2

    def __init__(self, *, max_probes: int | None = None) -> None:
        """`max_probes` is WS-15's `relax.max_probes`, and it can only add probes.

        `None` is the published cap. A value is passed through `max_relax_probes`, which
        takes the larger of the two, so a caller cannot use this argument to make a
        relaxation *narrower* than the one they would have got without it - the same
        discipline `force_rungs` runs under, for the same reason.
        """
        self._max_probes = max_probes

    def _relaxed_query(self, parsed: ParsedQuery, dropped: str) -> str | None:
        """The `q` that drops `dropped`, or `None` when this rung will never send it.

        The rung's own sentence, written once and read twice: `plan` skips what it returns
        `None` for, and `plannable_drops` asks the same question without building probes, so
        `empty_diagnosis` cannot offer a budget for a drop the rung declines whatever the
        budget is (R-RETR-023). Two callers reading one expression is the point - a second
        copy of "would this be planned?" is how the affordance came to promise a probe the
        planner had already refused.
        """
        kept = tuple(c for c in parsed.constraints if c.name != dropped)
        rendered = parsed.render(kept)
        if not rendered.strip() or carries_nothing_to_select_by(rendered):
            return None
        if search_region_of(kept) != search_region_of(parsed.constraints):
            # **The region is not relaxable** (OD-5 point 3, A9-A2). Relaxation widens
            # *within* the region the caller named, which is why dropping a filter is a
            # recoverable false negative; dropping the region does not widen anything, it
            # searches somewhere else - and for `-in:spam` or `in:spam` that somewhere else
            # is a region the caller either excluded or did not ask about. The rung declares
            # what it drops, so this is not a silent refusal: the drop stays in `drop_order`,
            # is reported in `untried_drops`, and is offered no budget, which is the same
            # shape `plannable_drops` already gives a drop no budget can reach (R-RETR-023).
            return None
        return rendered

    def plannable_drops(self, parsed: ParsedQuery) -> tuple[str, ...]:
        """Every drop this rung would send a probe for at an unbounded budget.

        The complement is the class ADV-105's schema cannot name: a drop that is not untried
        because the budget ran out but because there is no probe to send - dropping the only
        constraint of a one-constraint query renders an empty `q`, which is a listing rather
        than a relaxation. `_empty_diagnosis` uses this to decide whether raising the budget
        is a thing a caller could usefully be offered.
        """
        return tuple(
            constraint.name
            for constraint in _ordered_for_relaxation(parsed)
            if self._relaxed_query(parsed, constraint.name) is not None
        )

    def plan(self, parsed: ParsedQuery) -> tuple[Probe, ...]:
        ordered = _ordered_for_relaxation(parsed)
        probes: list[Probe] = []
        for candidate in ordered[: max_relax_probes(len(ordered), self._max_probes)]:
            kept = tuple(c for c in parsed.constraints if c.name != candidate.name)
            rendered = self._relaxed_query(parsed, candidate.name)
            if rendered is None:
                continue
            probes.append(
                Probe(
                    rung=self.rung,
                    query=rendered,
                    why=f"relaxation: dropped constraint {candidate.name!r} (AD A.7 L2)",
                    enforced=tuple(c.name for c in kept),
                    dropped=(candidate.name,),
                    relaxes=True,
                )
            )
        return tuple(probes)

    def drop_order(self, parsed: ParsedQuery) -> tuple[str, ...]:
        """Every constraint whose single drop is a relaxation, in the published order."""
        return tuple(constraint.name for constraint in _ordered_for_relaxation(parsed))

    def untried_drops(self, parsed: ParsedQuery, *, probed: Collection[str]) -> tuple[str, ...]:
        """`empty_diagnosis.untried_drops`: the drops in `drop_order` that `probed` misses.

        Reported rather than absorbed: ADV-105's defect was that "the probe budget ran out"
        and "no single drop restores results" were the same shape in the schema, and they
        are different findings.

        **`probed` is a parameter, and that is the whole point.** There are two ways a drop
        goes untried and only one of them is the budget: `min(k, 6)` cuts the plan short, and
        separately a rung that never executed - because an earlier rung found evidence, or
        because dropping the query's only constraint would render an empty `q` - probed
        nothing at all. A function that answered from the plan alone would report the second
        case as "every drop was tried and none restored results", which is ADV-105's defect
        reintroduced through the other door. The caller passes what actually ran.
        """
        already = frozenset(probed)
        return tuple(name for name in self.drop_order(parsed) if name not in already)


@dataclass(frozen=True)
class Broadening:
    """One L3 step: the `q` it composed, and what that `q` did and did not carry.

    Three fields rather than two, and the third is round 17's (R-RETR-020). A broadening
    step **replaces** constraints with wider forms - a window `BROADENING_DATE_FACTOR` times
    as long, a participant turned into a disjunction, a named mailbox location turned into
    the whole mailbox - and a wider form is not the constraint the user wrote. Recording only
    "the string and the constraints it carried" left the replaced ones indistinguishable from
    the carried ones, so `asked_for.enforced` named a constraint no probe had applied and
    `constraint_drop_depth` stayed at 0 for a route that had abandoned one.
    """

    query: str
    enforced: tuple[str, ...]
    given_up: tuple[str, ...]


def _broadening(query: str, parsed: ParsedQuery) -> Broadening:
    """One L3 step, with what it enforced and what it gave up **read off its own `q`**.

    Both of A.7 L3's steps replace constraints with wider forms - a window
    `BROADENING_DATE_FACTOR` times as long, a participant turned into `{from:x to:x}`, a
    named location turned into the whole mailbox - and a wider form is not the constraint the
    caller wrote (R-RETR-020). Round 17 stated that rule twice, once inside each step, from
    the constraint kinds each step happened to be looking at. It is one sentence about the
    composed string, so it is answered from the string by `constraints_carried_whole`, which
    is the same derivation L0, L1, L1b and L2 read. A step added to this rung later inherits
    it instead of restating it, and `test_a_probe_enforces_only_the_constraints_its_own_q_
    carries_whole` fails if any of them stops.
    """
    enforced = constraints_carried_whole(query, parsed.constraints)
    carried = frozenset(enforced)
    return Broadening(
        query=query,
        enforced=enforced,
        given_up=tuple(c.name for c in parsed.constraints if c.name not in carried),
    )


class BroadeningRung(LexicalRung):
    """L3: at most two broadening probes (A.7 L3: whole mailbox, dates x4, `from:`->`from|to`).

    Both steps are named and both are bounded by the cost row's two probes:

      * **widen** - the date window becomes `BROADENING_DATE_FACTOR` times as long about its
        own centre, and every participant operator becomes a `{from:x to:x}` group, which is
        A.7's "`from:` -> `from|to`". Planned only when it differs from L1's own query;
      * **anywhere** - `ANYWHERE_OPERATOR` plus the query's text constraints, which is the
        only probe in this ladder that leaves the default mailbox. Its `includeSpamTrash` is
        derived from the query by `Probe.include_spam_trash`, so the two cannot disagree.
        **It is planned only when it carries a fragment of the query that selects**
        (R-RETR-006): a broadening of nothing is not a broadening, and the scope operator on
        its own is a request for the whole mailbox, spam and trash included, on behalf of a
        query none of whose content was executed. "That selects" is the round-16 half:
        `-cutover` is a fragment of the query, and the scope operator conjoined with it is
        the same whole mailbox with a disguise on - which is what it returned, eight spam
        messages as `role: matched` under `outcome: answered` for a query that named nothing
        to find. `Probe.__post_init__` refuses that shape as well, so it cannot come back
        through another rung. Executed by
        `test_a_query_that_only_excludes_is_not_broadened_into_spam_and_trash`.

    The operator itself is **not spelled here**. It is `mailweave.constants.ANYWHERE_OPERATOR`,
    written once, because the request parameter and the `in:` operator are two independent
    ways of saying the same thing and a second hand-typed copy is how they come to disagree
    (R-SEC-051; `test_no_module_spells_a_mailbox_scope_operator_outside_the_scope_enum`).
    """

    rung = RungId.L3

    def _widened(self, parsed: ParsedQuery) -> Broadening:
        """The widened query **and the constraints it carried**, computed together.

        One function returning both, because they are one fact. Returning only the string and
        letting the caller state `enforced` separately is how the two came apart: a date
        constraint whose value MailWeave could not resolve into a window (`after:notadate` -
        Gmail judges it, we do not) was dropped from the query while `enforced` went on
        claiming every constraint, which is the silently-dropped signal LEX-02 counts at zero
        tolerance. An unwidenable date constraint is now carried unchanged instead.

        **A constraint this rung *widens* is not a constraint it enforces** (R-RETR-020).
        Both of A.7 L3's widening steps replace a constraint with something strictly larger -
        a window `BROADENING_DATE_FACTOR` times as long, a participant turned into
        `{from:x to:x}` - so a hit admitted by this probe need not satisfy the constraint the
        user wrote, and a message from January 2025 can come back under `newer_than:7d`. The
        rung used to report those constraints `enforced` on the strength of having *carried
        something derived from* them, which is the same class of over-claim as reporting a
        constraint L2 abandoned. They are reported as `dropped` here and named with this
        rung; `Probe.relaxes` stays false, because a broadening is not the query giving a
        constraint up in the sense ROUTE-03 enumerates.
        """
        fragments: list[str] = []
        widenable_dates = parsed.window is not None
        for constraint in parsed.constraints:
            if constraint.kind == OperatorKind.DATE.value and widenable_dates:
                # Replaced by the x4 window below - which is wider than what was asked for,
                # so the constraint is not enforced by this probe. `_broadening` reads that
                # off the composed `q` rather than being told it here.
                continue
            if constraint.kind == OperatorKind.PARTICIPANT.value:
                for fragment in constraint.fragments:
                    if carries_nothing_to_select_by(fragment):
                        # A **negated** participant is carried unchanged. A.7 L3's
                        # `from:` -> `from|to` widens the set of messages a participant
                        # operator selects; a negation selects nothing, and the disjunction
                        # of it is not a broader version of the same question but a
                        # different one - `{-from:x to:x}` is "not from x, or to x", which
                        # is nearly every message there is. Executed by
                        # `test_a_negated_participant_is_not_widened_into_its_own_opposite`.
                        fragments.append(fragment)
                        continue
                    # **Which operator this fragment writes is read through the registry**,
                    # not by splitting the string on a colon (round 19's standing sweep). The
                    # fragments here are `ParsedOperator.render()`'s own output, so the two
                    # agree today; the difference is that this one keeps agreeing if a
                    # fragment ever arrives in another spelling, and a fragment no documented
                    # operator can be read out of is carried unchanged rather than widened
                    # into a disjunction of a name nobody wrote.
                    name = operator_of(fragment)
                    if name is None:
                        fragments.append(fragment)
                        continue
                    _, _, value = fragment.partition(":")
                    other = OperatorName.TO if name is OperatorName.FROM else OperatorName.FROM
                    fragments.append(f"{{{name.value}:{value} {other.value}:{value}}}")
                continue
            fragments.extend(constraint.fragments)
        if parsed.window is not None:
            fragments = [
                operator.render()
                for operator in parsed.window.widened(BROADENING_DATE_FACTOR).operators()
            ] + fragments
        query = " ".join(fragment for fragment in fragments if fragment)
        return _broadening(query, parsed)

    def _anywhere(self, parsed: ParsedQuery) -> Broadening:
        """The whole-mailbox query and the constraints it carried, or **nothing**.

        Returns an empty query when the parse leaves no fragment to widen the scope *of*.
        A.7 L3 broadens the query; it does not replace it with the mailbox. Round 15's
        version composed `ANYWHERE_OPERATOR` with an empty fragment list and shipped the
        result: `mailweave_search("(rollout OR escalation)")`, `("the and of")`, `("  ")`
        and a zero-hit `("newer_than:30d")` each put a bare scope operator and
        `includeSpamTrash=true` on the wire, and the sixty threads that came back were
        reported as matches of a query whose terms were never sent, under
        `outcome: answered` and `term_coverage: 1.0` (R-RETR-006, BLOCKER).

        `Probe.__post_init__` refuses the shape as well, so it cannot come back through
        another rung. Refusing it in two places is not a duplicated check: this one decides
        *not to plan*, which is a policy; that one makes the object unrepresentable, which
        is what stops the next rung from re-deriving the policy wrongly.

        **Every fragment that declares the search region is replaced, not only the widening
        ones** (R-RETR-021). The round-16 version replaced the three members of
        `WIDENING_MAILBOX_OPERATORS` and conjoined every other location the user could
        write, so a query naming the inbox produced a probe that set `includeSpamTrash=true`,
        declared in `scan_scope` that it had widened to everywhere, and searched the inbox -
        a broadening probe that does not broaden, costing a Gmail call to re-observe what L1
        observed (I-3). Since round 19 the vocabulary is the operator registry rather than a
        lexical prefix, so a region-selecting operator nobody has registered yet is replaced
        too. The gate below makes this filter unreachable for a query that declared a region
        at all, and it is kept because "replaces it wholesale" is a property of this step
        rather than a consequence of its caller.

        **A location that was replaced is not a location that was enforced** (R-RETR-020).
        The constraint is carried only when the user's own fragments were already the
        widening operator, because "search everywhere" is not a way of having searched spam:
        it is a wider question, and reporting the narrower one `enforced` is the same
        over-claim as reporting a constraint L2 abandoned.

        **The `label:` residue is closed rather than named** (round 19, R-RETR-036). A label
        can be a user's own or one of Gmail's system mailboxes; `KIND_BY_OPERATOR` registers
        the operator `REGION` on the conservative reading, so a query naming a label is a
        query that named a region and this step declines on it. What that costs is recall on
        a user's own label, and the response carries the concrete call that recovers it.
        """
        if region_declarations_of(parsed):
            # **The caller declared a region, so there is no region left for this step to
            # replace** (OD-5 point 2, A9-A3). A.7 L3's published step widens the *scope* of
            # a query that did not name one; a query that named one - positively or
            # negatively - has already answered the question this step exists to ask, and
            # widening it answers a different question. `-in:spam borogrove` reached
            # `in:anywhere borogrove` with `includeSpamTrash=true` and returned the excluded
            # spam message as `role: matched` under `outcome: answered` (R-RETR-026);
            # `in:inbox borogrove` did the same from the other polarity, declaring the drop
            # but searching a region the caller had ruled out. The test for it is
            # `test_a_query_that_named_a_region_is_never_widened_out_of_it`, which sweeps
            # both polarities over the whole location family.
            return Broadening(query="", enforced=(), given_up=())
        wanted = {TERMS_CONSTRAINT, PHRASE_CONSTRAINT, OperatorKind.TEXT.value}
        chosen = [c for c in parsed.constraints if c.kind in wanted]
        if not chosen:
            chosen = [c for c in parsed.constraints if c.kind != OperatorKind.DATE.value]
        fragments = [
            fragment
            for constraint in chosen
            for fragment in constraint.fragments
            if not declares_the_search_region(fragment)
        ]
        broadened = " ".join([ANYWHERE_OPERATOR, *fragments])
        if carries_nothing_to_select_by(broadened):
            return Broadening(query="", enforced=(), given_up=())
        return _broadening(broadened, parsed)

    def plan(self, parsed: ParsedQuery) -> tuple[Probe, ...]:
        baseline = parsed.render()
        probes: list[Probe] = []
        widened = self._widened(parsed)
        if widened.query.strip() and widened.query != baseline:
            probes.append(
                Probe(
                    rung=self.rung,
                    query=widened.query,
                    why=(
                        f"broadening: date window x{BROADENING_DATE_FACTOR} and "
                        "from: widened to from|to (AD A.7 L3)"
                    ),
                    enforced=widened.enforced,
                    dropped=widened.given_up,
                )
            )
        anywhere = self._anywhere(parsed)
        # `!= baseline` for the same reason the widening step has it: a probe identical to
        # L1's own query is not a broadening of it. It arises when the user wrote the
        # widening scope operator themselves, and sending it again costs a Gmail call and a
        # second `scan_scope` entry to re-observe what L1 already observed (I-3).
        if anywhere.query.strip() and anywhere.query != baseline:
            probes.append(
                Probe(
                    rung=self.rung,
                    query=anywhere.query,
                    why=(
                        f"broadening: {ANYWHERE_OPERATOR} over the query's text "
                        "constraints (AD A.7 L3)"
                    ),
                    enforced=anywhere.enforced,
                    dropped=anywhere.given_up,
                )
            )
        return tuple(probes[:MAX_BROADENING_PROBES])


#: The ladder, in execution order. The population of the commonality test is read from
#: here, by name **and** by count, so the sweep cannot be emptied by narrowing its scope -
#: which is how round 12's sweep passed while covering nothing (round 13's finding).
LADDER: Final[tuple[LexicalRung, ...]] = (
    ExactOperatorRung(),
    FilteredRung(),
    DecompositionRung(),
    RelaxationRung(),
    BroadeningRung(),
)

LADDER_RUNGS: Final[tuple[RungId, ...]] = tuple(rung.rung for rung in LADDER)


def _blocked(
    rung: RungId,
    planned: tuple[Probe, ...],
    breach: CapBreach,
    *,
    executed: tuple[ExecutedProbe, ...] = (),
) -> RungExecution:
    """One rung's record when a cap stopped it, whether before its first probe or part-way.

    One constructor for both, because they are one state: the rung was applicable, it did
    not finish, and the response owes the caller the cap's name and the call that raises it.
    Whether any of its probes ran is `executed`, and the ids those probes admitted are
    already in `H` - the accountant is consulted before a probe, never after it, so nothing
    is charged for a call that did not go out and nothing observed is dropped.
    """
    return RungExecution(
        rung=rung,
        planned=planned,
        executed=executed,
        skipped=breach.why,
        cap=breach.cap,
        affordance=breach.affordance,
    )


def plan_ladder(parsed: ParsedQuery) -> tuple[Probe, ...]:
    """Every probe the whole ladder would send, in order, before any of them is sent."""
    return tuple(probe for rung in LADDER for probe in rung.plan(parsed))


@dataclass(frozen=True)
class ExecutedProbe:
    """One probe that ran, with what it put into `H` and where those ids live.

    Two counts, and they are different questions:

      * `ids_returned` is **the page's own hit count** - what this `q` matched, whether or
        not an earlier probe had already recorded those ids. It is what D.3's `hit_count`
        means and what a relaxation step logs, because "dropping `from:` restored results"
        is a statement about what the relaxed query matched;
      * `ids_admitted` is what this probe was the **first** to put into `H`. It is what the
        disposition ledger will account for, and it is a delta by construction - the seam
        hands back counts, never ids, so a probe cannot report ids an earlier one recorded.
    """

    probe: Probe
    ids_returned: int
    ids_admitted: frozenset[str]
    threads: frozenset[str]
    thread_of: Mapping[str, str]
    more_pages: bool


@dataclass(frozen=True)
class RungExecution:
    """One rung's plan and what came of it. `skipped` is set when the rung did not run.

    **`skipped` is a `NotTriedWhy` rather than a string, and round 22 is why** (WS-10, and
    the vocabulary question round 15 left open). It used to be the literal
    `"not_applicable"` for all three ways a rung can fail to run - it had no plan, a D.3
    stop had already settled the query, or the policy declined it because evidence already
    existed - and `assemble` turned every one of them into `not_tried[].why =
    not_applicable`. Two of those three are not inapplicable rungs: they are rungs that were
    applicable and were not needed, and telling a caller "this could not have helped" about
    them is a claim wider than the code in the field OD-2's whole distinction is built on.
    `NotTriedWhy.STOPPED_ON_EVIDENCE` carries the second and third, with the `force_rungs`
    affordance the first cannot have.

    A `skipped` of `budget`, `cap` or `timeout` is the mid-rung case: `executed` then holds
    the probes that ran before the accountant refused, and they are kept. A timeout is not
    permission to forget.
    """

    rung: RungId
    planned: tuple[Probe, ...]
    executed: tuple[ExecutedProbe, ...] = ()
    skipped: NotTriedWhy | None = None
    #: The cap that stopped this rung, when a cap did. `None` for every other `skipped`.
    cap: BudgetCapName | None = None
    #: The call that would reach this rung. `None` exactly when `skipped` is
    #: `not_applicable`, because no budget reaches a rung that does not apply.
    affordance: Affordance | None = None

    def __post_init__(self) -> None:
        if self.skipped is None:
            if self.cap is not None or self.affordance is not None:
                raise ValueError(f"{self.rung.value} ran; it has no cap and no affordance")
            return
        if (self.skipped is NotTriedWhy.NOT_APPLICABLE) != (self.affordance is None):
            raise ValueError(
                f"{self.rung.value} skipped as {self.skipped.value}: `not_applicable` is "
                "exactly the reason no call reaches, so it is exactly the reason with no "
                "affordance (AD-03, OD-2)"
            )

    @property
    def ids_admitted(self) -> frozenset[str]:
        return frozenset().union(*(e.ids_admitted for e in self.executed), frozenset())

    @property
    def threads(self) -> frozenset[str]:
        return frozenset().union(*(e.threads for e in self.executed), frozenset())


@dataclass(frozen=True)
class LadderStop:
    """One D.3 stop: the rule, the rung whose evidence fired it, and where the ladder halts.

    **`halts_after` is not always `fired_after`, and that is A.7's table rather than a
    licence** (R-RETR-007). L1b's Stop/escalate column reads "feeds L1": it is part of L1's
    answer rather than an escalation from it, because the threads it exists for - the ones
    whose parts are satisfied by *different messages*, which Gmail's message-scoped `q`
    cannot match at all (RO F2) - contribute zero hits to L1 whether or not other threads
    did. So D.3 rule 2's stop after L1 halts the ladder after L1b, and the rung this
    project exists for is not switched off by the other threads' good luck.

    D.3 rules 1 and 1b are identity resolution at L0 and halt everything, which is rule 1's
    own sentence: "no structural, semantic or ranking rung may run".
    """

    rule: str
    fired_after: RungId
    halts_after: RungId


@dataclass(frozen=True)
class RelaxationStep:
    """ROUTE-03's log line: the constraint dropped, the query sent, the hits it produced."""

    dropped: str
    q: str
    hit_count: int


@dataclass(frozen=True)
class Decomposition:
    """L1b's intersection, and the honest bound on what it can name.

    `threads_by_constraint` records, per decomposed constraint, the threads of the ids that
    probe was the **first** to admit into `H`. That "first" is a property of the disposition
    seal rather than a choice: `_admit` records an id's origin once, and the transport hands
    back counts rather than ids, so there is no supported way to ask which ids a *later*
    probe returned that an earlier one had already recorded.

    What that costs is bounded, **and the bound has two preconditions rather than one**
    (R-RETR-013). Given that every probe's page was complete, a thread can drop out of the
    intersection only when a probe's entire contribution to it consists of ids an earlier
    probe already admitted - which means one single message satisfied both parts. Those ids
    are in `H` already, so the thread is hit-bearing whatever this intersection says, and
    the disposition ledger will disclose or withhold every one of them. That much was
    stated, and `test_l1b_can_only_under_name_a_thread_whose_messages_are_already_in_H`
    executes it.

    The precondition that was *not* stated is the page budget. `max_pages_per_query = 1`,
    so a probe matching more than `page_size` messages sees only the first page: a thread
    whose message sits behind that page contributes nothing to that probe's set, drops out
    of the intersection with **no** single message satisfying both parts, and its ids are
    not in `H` at all - nothing "already admitted" and nothing for the ledger to account
    for, because the ids were never observed. The loss is upstream of the disposition seal
    and the response declares it as `more_pages` in `scan_scope` rather than as a withheld
    record. `test_a_truncated_decomposition_page_drops_a_thread_the_bound_does_not_cover`
    executes the case the claim used to be read as excluding.
    """

    threads_by_constraint: Mapping[str, frozenset[str]]
    intersection: frozenset[str]
    union: frozenset[str]


@dataclass
class LadderRun:
    """One complete lexical ladder execution, and everything the envelope needs from it."""

    parsed: ParsedQuery
    executions: tuple[RungExecution, ...]
    exact_signal: ExactSignal
    answer_type: AnswerTypePresence
    stop_rule: str | None
    stopped_after: RungId | None
    #: The cap that stopped this run, if one did (D.3 rule 5). Set by the accountant, never
    #: by a rung: a rung reports what it did, and whether it may spend is the accountant's.
    stopped_by: CapBreach | None = None
    bodies: dict[str, ProcessedMessage] = field(default_factory=dict)
    relaxation: tuple[RelaxationStep, ...] = ()
    decomposition: Decomposition | None = None
    untried_drops: tuple[str, ...] = ()
    admitted_by: dict[str, tuple[str, ...]] = field(default_factory=dict)
    body_fetch_failures: dict[str, str] = field(default_factory=dict)

    @property
    def rungs_run(self) -> tuple[RungId, ...]:
        """Every rung that sent at least one probe, **including one a cap cut short**.

        A rung stopped part-way is in this list *and* in `not_tried`, and both are true: it
        produced evidence the reader must be able to see, and its remainder did not run so
        the caller is owed the call that finishes it. `Envelope` refuses a `rungs` that omits
        a rung which admitted ids - which is the invariant that found this: a mid-rung stop
        that reported the rung only as `not_tried` made the response unbuildable, because a
        route that produced evidence and is not listed is a route the reader cannot see
        (EV-01, PART-01).
        """
        return tuple(e.rung for e in self.executions if e.skipped is None or e.executed)

    @property
    def rungs_skipped(self) -> tuple[RungId, ...]:
        return tuple(e.rung for e in self.executions if e.skipped is not None)

    @property
    def rungs_cut_short(self) -> tuple[RungId, ...]:
        """The mid-rung shape: rungs whose plan was split by a cap. In both lists, by design."""
        return tuple(
            e.rung
            for e in self.executions
            if e.skipped is not None and e.executed and len(e.executed) < len(e.planned)
        )

    @property
    def executed_probes(self) -> tuple[ExecutedProbe, ...]:
        return tuple(e for execution in self.executions for e in execution.executed)

    @property
    def hit_count(self) -> int:
        """How many distinct ids the lexical rungs put into `H`. Not the same as evidence."""
        return len(frozenset().union(*(e.ids_admitted for e in self.executions), frozenset()))

    @property
    def evidence_count(self) -> int:
        """How many hits the ladder has *found*, which is not how many ids it has observed.

        The two diverge at L1b and it matters, because the escalation gate reads this one.
        A decomposition probe is deliberately broad - `from:ana` alone can match a hundred
        messages that have nothing to do with the query - and every one of those ids enters
        `H` and will be disclosed or withheld. Counting them as evidence would switch L2 and
        L3 off for exactly the queries they exist for: the ladder would look like it had
        found something when what it had found was one half of the question.

        So L1b contributes **its intersection**, which is its answer, and the other rungs
        contribute their pages' own hit counts.
        """
        return self._evidence(LADDER_RUNGS)

    @property
    def unrelaxed_evidence_count(self) -> int:
        """Evidence found by the routes that carried **every** constraint of the query.

        L0, L1 and L1b each enforce the whole parse; L2 drops one constraint and L3 widens
        the remaining ones, so their hits answer a question the user did not ask. ROUTE-04's
        "zero-hit outcome" - the state in which "which single drop restores results?" has a
        subject at all - is this number being zero, and `evidence_count` cannot express it:
        after a relaxation succeeds the two disagree, which is precisely the case the
        empty-result diagnosis exists for.
        """
        return self._evidence((RungId.L0, RungId.L1, RungId.L1B))

    def _evidence(self, rungs: Collection[RungId]) -> int:
        total = 0
        for execution in self.executions:
            if execution.rung not in rungs or execution.rung is RungId.L1B:
                continue
            total += sum(entry.ids_returned for entry in execution.executed)
        if self.decomposition is not None and RungId.L1B in rungs:
            total += len(self.decomposition.intersection)
        return total

    @property
    def evidence_ids(self) -> frozenset[str]:
        """The ids `evidence_count` refers to, as far as `H` can name them.

        "As far as `H` can name them" is exact rather than hedged: a probe reports the ids it
        was the first to admit, so an id an earlier probe recorded is counted by
        `evidence_count` (which reads the page) and absent here (which reads the delta).
        That is why this drives body fetching - a best-effort list of what to open - and not
        the disposition, which is the ledger's and is total.
        """
        found: set[str] = set()
        intersection = (
            self.decomposition.intersection if self.decomposition is not None else frozenset()
        )
        for execution in self.executions:
            for entry in execution.executed:
                if execution.rung is RungId.L1B:
                    found |= {
                        message_id
                        for message_id in entry.ids_admitted
                        if entry.thread_of.get(message_id) in intersection
                    }
                else:
                    found |= entry.ids_admitted
        return frozenset(found)


class LadderRunner:
    """Executes the ladder against one Gmail client and one disposition ledger.

    The ledger is a constructor argument rather than a return value because it is the thing
    that must outlive the run: `withheld := H - disclosed` is computed from it at envelope
    time, over the ids **every** rung observed, and a runner that handed back its own hit
    list would be the shape the whole seal exists to prevent.
    """

    def __init__(
        self,
        client: GmailClient,
        ledger: DispositionLedger,
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = MAX_PAGES_PER_QUERY,
        accountant: BudgetAccountant | None = None,
        forced: Collection[RungId] = (),
        relax_max_probes: int | None = None,
    ) -> None:
        self._client = client
        self._ledger = ledger
        self._page_size = page_size
        self._max_pages = max_pages
        #: WS-15's `force_rungs`, as a set this runner reads and never writes. **It can
        #: only add** (AD D.1): `_should_run` returns `True` for a forced rung and is
        #: otherwise unchanged, so the rungs that ran with a forcing set are a superset of
        #: the rungs that ran without it, for every query. It cannot remove a rung, cannot
        #: lower a budget, and cannot reach past a cap - a cap that has already stopped the
        #: query blocks a forced rung exactly as it blocks an unforced one, because the
        #: `run.stopped_by` branch is tested before this one and D.3 rule 5 is not a policy
        #: decision a caller may overrule. Forcing a rung this build does not contain is
        #: not represented here at all: `LADDER` has five members and a set intersected
        #: with it cannot name a sixth. The surface declares that in band instead.
        self._forced = frozenset(forced)
        #: WS-15's `relax.max_probes`. `None` leaves `LADDER` alone; a value substitutes one
        #: rung instance for another in this runner's own copy of the ladder, so the module
        #: constant every other caller reads is untouched. `max_relax_probes` takes the
        #: larger of the published cap and this, so the argument can only add probes.
        self._relax_max_probes = relax_max_probes
        #: WS-10's per-query budget. **Optional, and the default is no budget rather than an
        #: unlimited one**: a runner constructed without one behaves exactly as every runner
        #: before WS-10 did, so the caps arrive at the call sites that opt into them rather
        #: than changing what every existing caller costs. `assemble` and the MCP surface
        #: pass one; a unit test of a rung's planning does not need to.
        self._accountant = accountant

    # -- execution ---------------------------------------------------------------------

    @property
    def ladder(self) -> tuple[LexicalRung, ...]:
        """This runner's ladder: `LADDER`, with L2 re-instanced when a probe cap was asked for.

        A copy rather than a mutation, because `LADDER` is a module constant several other
        modules read and a runner that edited it would change what every other caller plans.
        """
        if self._relax_max_probes is None:
            return LADDER
        return tuple(
            RelaxationRung(max_probes=self._relax_max_probes) if rung.rung is RungId.L2 else rung
            for rung in LADDER
        )

    def _execute(self, probe: Probe) -> ExecutedProbe:
        before = self._ledger.hit_ids
        run = self._client.list_messages(
            self._ledger,
            rung=probe.rung,
            query=probe.query,
            widening_affordance=widen_scan(probe.query),
            page_size=self._page_size,
            max_pages=self._max_pages,
            include_spam_trash=probe.include_spam_trash,
        )
        admitted = self._ledger.hit_ids - before
        origins = self._ledger.origins
        thread_of = {
            message_id: thread
            for message_id in admitted
            if (thread := origins[message_id].thread_id) is not None
        }
        return ExecutedProbe(
            probe=probe,
            ids_returned=run.ids_recorded,
            ids_admitted=admitted,
            threads=frozenset(thread_of.values()),
            thread_of=thread_of,
            more_pages=run.more_pages,
        )

    def _fetch_bodies(self, run: LadderRun, ids: Sequence[str], *, cap: int) -> None:
        """Fetch and process up to `cap` bodies, for the local checks that need text.

        A.8a branch E-b verifies its phrase locally and A.8b's `answer_type_presence` reads
        the hits, so both need text before any stop rule is evaluated (D.3 rule 0). The cap
        is A.7's `max_body_fetches`; a hit beyond it is **disclosed as a stub row**, not
        withheld - depth reduction is not omission (A.7a).

        Ids are taken in sorted order, which is deterministic and is **not a ranking**:
        `messages.list` returns only `id` and `threadId` (RO F1), so at this point nothing
        in the process knows anything about these messages that could order them. Ranking is
        L6 and it does not exist yet.

        **The accountant is consulted per body, and a body is a Gmail call like any other**
        (WS-10). It is asked here rather than only around the probes because A.7's caps are
        per *query*, not per rung: a run that spent its whole `max_api_calls` on
        `messages.get` has spent it, and a budget that bounded probes and not bodies would
        be a budget the response could overrun without any cap firing. A body the budget
        stopped is not lost - the id is in `H`, the ledger will disclose or withhold it, and
        the run's `stopped_by` is what makes the response name the cap.
        """
        for message_id in sorted(ids):
            if len(run.bodies) >= cap:
                return
            if message_id in run.bodies or message_id in run.body_fetch_failures:
                continue
            if self._accountant is not None:
                breach = self._accountant.check((GmailEndpoint.MESSAGES_GET,))
                if breach is not None:
                    run.stopped_by = breach
                    return
            try:
                message = self._client.get_message(message_id, message_format="full")
            except MailweaveError as failure:
                run.body_fetch_failures[message_id] = type(failure).__name__
                continue
            if message.payload is None:
                run.body_fetch_failures[message_id] = "no payload returned"
                continue
            try:
                run.bodies[message_id] = process_message(
                    MessagePayload.model_validate(
                        {
                            "id": message.id,
                            "threadId": message.thread_id,
                            "internalDate": message.internal_date,
                            "snippet": message.snippet or "",
                            "payload": message.payload,
                        }
                    )
                )
            except ContentProcessingError as failure:
                run.body_fetch_failures[message_id] = type(failure).__name__

    def _texts(self, run: LadderRun) -> tuple[str, ...]:
        """The default view of every body fetched so far, plus its subject.

        The **default view** rather than the raw body (amendment A7): `body_clean` is the
        whole text with classified spans, and the default view is the `original` spans -
        which is the quote-stripped text A.8b requires the predicate be measured against.
        """
        return tuple(
            f"{processed.subject or ''}\n{processed.default_view}"
            for processed in run.bodies.values()
        )

    # -- the run -----------------------------------------------------------------------

    def run(self, query: str, *, now: datetime, zone: ZoneInfo | None = None) -> LadderRun:
        """Execute the ladder for `query`, stopping by the D.3 rules the rungs can evaluate."""
        parsed = analyse(query, now=now, zone=zone)
        return self.run_parsed(parsed)

    def run_parsed(self, parsed: ParsedQuery) -> LadderRun:
        """Execute the ladder for an already-parsed query, or return the run that executed nothing.

        A query no rung can turn into a probe is still not sent to Gmail - round 15 answered
        one by sending the mailbox instead (R-RETR-006) - but **not sending anything and not
        answering at all are different things**, and round 16 made them the same. Refusing
        every unplannable query with an exception took ROUTE-01's "a no-evidence outcome is a
        structured report, never an empty set or a nonexistence claim" and produced something
        weaker than the bare empty result the criterion was written against: no response.

        So the ladder returns a **run in which every rung is `not_applicable`**, which is the
        rare case in which that is literally true of all five, and `assemble` turns it into
        the report A.2 and D.3 rule 6 require: the parse, every token dropped with its
        reason, every rung named as not tried, an `empty_diagnosis`, and the affordances.
        Zero Gmail calls either way - `plan_ladder` is consulted before any probe executes.

        **The one query that still raises is the one there is nothing to report about.** An
        empty or whitespace-only `q` asked for nothing at all: there is no parse to show, no
        token to declare dropped, and no rung whose non-application means anything, so every
        field of the report would describe a search that had no subject - `term_coverage`
        would read 1.0 and the diagnosis `complete`, which together say "I looked and found
        nothing" about a question nobody asked. A refusal naming the empty input is the
        honest answer; a report would be a fabricated one. `QueryNotSearchable`'s docstring
        carries the line and where it is drawn.

        **The condition for planning nothing is the empty ladder plan, not the empty
        constraint list**, and the difference is a second class of query: a bare widening
        mailbox-scope operator, and one paired with an exclusion, each parse to a constraint
        apiece and still name nothing to find, so `parsed.constraints` is non-empty and every
        rung declines. Read from `plan_ladder`, the rule covers both classes and cannot come
        apart from what the rungs actually planned.
        """
        if not plan_ladder(parsed):
            if not parsed.raw.strip():
                raise QueryNotSearchable(
                    "the query is empty, so there is nothing to search for and nothing to "
                    "report about: no parse, no constraint, no token to declare dropped and "
                    "no rung whose non-application means anything (AD A.2, ROUTE-01)"
                )
            return LadderRun(
                parsed=parsed,
                executions=tuple(
                    RungExecution(rung=rung.rung, planned=(), skipped=NotTriedWhy.NOT_APPLICABLE)
                    for rung in self.ladder
                ),
                exact_signal=ExactSignal(
                    fired=False, branch=None, phrase_tokens=0, hit_count=0, verified_locally=False
                ),
                answer_type=AnswerTypePresence(
                    answer_type=parsed.answer_type, present=None, examined=0
                ),
                stop_rule=None,
                stopped_after=None,
                untried_drops=RelaxationRung().untried_drops(parsed, probed=()),
            )
        executions: list[RungExecution] = []
        run = LadderRun(
            parsed=parsed,
            executions=(),
            exact_signal=ExactSignal(
                fired=False, branch=None, phrase_tokens=0, hit_count=0, verified_locally=False
            ),
            answer_type=AnswerTypePresence(
                answer_type=parsed.answer_type, present=None, examined=0
            ),
            stop_rule=None,
            stopped_after=None,
        )
        order = {rung: index for index, rung in enumerate(LADDER_RUNGS)}
        stop: LadderStop | None = None
        for rung in self.ladder:
            run.executions = tuple(executions)
            planned = rung.plan(parsed)
            if not planned:
                # Nothing to run: this rung could not have helped this query at all. The one
                # `skipped` value OD-2 makes compatible with `not_found`, and the one that
                # carries no affordance.
                executions.append(
                    RungExecution(rung=rung.rung, planned=(), skipped=NotTriedWhy.NOT_APPLICABLE)
                )
                continue
            if run.stopped_by is not None:
                # A cap already stopped this query. Every remaining rung is blocked by the
                # same cap and says so, with the call that would raise it (D.3 rule 5).
                executions.append(_blocked(rung.rung, planned, run.stopped_by))
                continue
            # **A rung the caller forced runs past the halt as well as past the gate**
            # (WS-15). `stopped_on_evidence` is exactly the state a D.3 stop rule produces,
            # and it is the state whose affordance this server mints, so a `force_rungs`
            # that could not reach past a stop would be an affordance that reaches nothing.
            # The cap branch above is **not** overridden and must not be: D.3 rule 5 is a
            # budget, and a caller may add work inside their budget rather than around it.
            # Nor does this reach D.3 rule 1's architectural prohibition, which forbids the
            # *structural, semantic and ranking* rungs after an identity resolution
            # (SEM-04, RANK-01): `LADDER` holds the five lexical rungs and none of the three.
            forced = rung.rung in self._forced
            halted = stop is not None and order[rung.rung] > order[stop.halts_after]
            if not forced and (halted or not self._should_run(rung.rung, run)):
                # **The rung was applicable and was not needed** - a D.3 stop rule had
                # already settled the query, or the escalation gate found evidence. That is
                # not `not_applicable`; see `RungExecution` and `NotTriedWhy`.
                executions.append(
                    RungExecution(
                        rung=rung.rung,
                        planned=planned,
                        skipped=NotTriedWhy.STOPPED_ON_EVIDENCE,
                        affordance=force_rungs(rung.rung, query=parsed.raw),
                    )
                )
                continue
            # **The mid-rung contract.** The accountant is asked before each probe, so a rung
            # stopped part-way keeps the probes that ran: the ids they admitted are in `H`
            # and the ledger will disclose or withhold every one of them. The rest of the
            # plan becomes `not_tried` under the cap's own reason. A timeout is not
            # permission to forget what was already retrieved.
            executed_probes: list[ExecutedProbe] = []
            breach: CapBreach | None = None
            for probe in planned:
                breach = (
                    None
                    if self._accountant is None
                    else self._accountant.check((GmailEndpoint.MESSAGES_LIST,))
                )
                if breach is not None:
                    break
                executed_probes.append(self._execute(probe))
            executed = tuple(executed_probes)
            if breach is not None:
                run.stopped_by = breach
                executions.append(_blocked(rung.rung, planned, breach, executed=executed))
            else:
                executions.append(RungExecution(rung=rung.rung, planned=planned, executed=executed))
            run.executions = tuple(executions)
            for entry in executed:
                for message_id in entry.ids_admitted:
                    run.admitted_by[message_id] = entry.probe.enforced
            if breach is not None:
                continue
            fired = self._after_rung(rung, run, executed)
            if fired is not None and stop is None:
                stop = fired
                run.stop_rule = fired.rule
                run.stopped_after = fired.fired_after
        run.executions = tuple(executions)
        # A.7's `max_body_fetches` again, at the end: L0 and L1 fetch bodies because the
        # stop rules need text before they can be tested, and a recovery rung's evidence
        # would otherwise reach disclosure with no body ever opened - so a message L2 or L3
        # found would be a stub in the response while an identical message L1 found was at
        # `body_clean`. That is a depth that depends on which rung got there, which is not a
        # property anybody asked for.
        self._fetch_bodies(run, sorted(run.evidence_ids), cap=MAX_BODY_FETCHES_L1)
        # One writer, and it reads what *ran* rather than what was planned: a drop L2 never
        # probed is untried whether the budget cut it, the rung never executed, or dropping
        # the query's only constraint would have rendered an empty `q`.
        run.untried_drops = RelaxationRung().untried_drops(
            parsed, probed={step.dropped for step in run.relaxation}
        )
        return run

    def _should_run(self, rung: RungId, run: LadderRun) -> bool:
        """The escalation policy between lexical rungs, dumb and written down.

        Three gates, one sentence each. Two of them are the two branches below; the
        third - "a stop has already halted the ladder" - is `LadderStop.halts_after` in
        `run_parsed`, which is checked against the rung order and so is not restated here.

          * **L0 and L1** run whenever they have a plan;
          * **L1b** runs whenever it has a plan, and **is not gated by any evidence count or
            by the D.3 rule 2 stop**. Its purpose is threads Gmail's message-scoped `q`
            cannot match *at all* (RO F2), and those threads contribute zero hits to L1
            whether or not other threads did - so gating it on the total hit count would
            switch it off precisely when the query it exists for also matched something
            else. Round 15 made that argument and then gated it on the L1 stop anyway,
            which is the same gate one step further out: two unrelated single-message hits
            fired D.3 rule 2, L1b was skipped with a non-empty plan, the split thread was
            never searched, and the response reported `answered` / `sufficient` with L1b
            marked `not_applicable` - the claim that the only rung that could have found it
            could not have helped (R-RETR-007). The docstring that stood here, "if L1's
            evidence was sufficient there is nothing to decompose for", was false in exactly
            that case: L1's evidence was two other threads. A.7's table calls L1b "feeds
            L1", and it now does;
          * **a rung the caller forced** runs whenever it has a plan. This is the first
            branch rather than the last because it is an addition to the policy and never a
            subtraction from it: putting it first can only turn a `False` into a `True`, and
            putting it last would leave it unable to do even that on the rungs that already
            return early. `force_rungs` is how an affordance re-runs a rung the policy
            declined on evidence (`NotTriedWhy.STOPPED_ON_EVIDENCE`), and the one thing it
            must never do is make a response smaller than the same query got without it;
          * **L2 and L3** run when nothing has been found at all - D.3 rule 4's
            `hit_count == 0`, applied at the first rung that can act on it. This is also
            what makes ROUTE-04's diagnosis exist: the relaxation probes *are* the diagnosis.

        The alternative - running every rung every time - would satisfy recall and fail I-3
        (adaptive cost) and AD-04's simple-family ceiling, which is the inverse failure the
        rubric pairs with recall for exactly this reason.
        """
        if rung in self._forced:
            return True
        if rung in {RungId.L0, RungId.L1, RungId.L1B}:
            return True
        return run.evidence_count == 0

    def _stop_inputs(self, run: LadderRun, *, hit_count: int) -> StopInputs:
        """The signals D.3's rules read, assembled once per evaluation.

        `constraint_drop_depth` is `run.parsed.passthrough` rather than a count: a
        passthrough parse is one whose constraints were not all carried, which is what a
        non-zero drop depth means at this rung. The two lexical evaluations both go through
        here, so neither can quietly read a signal the other does not.
        """
        return StopInputs(
            exact=run.exact_signal,
            answer_type=run.answer_type,
            hit_count=hit_count,
            term_coverage=run.parsed.term_coverage(run.parsed.constraints),
            constraint_drop_depth=1 if run.parsed.passthrough else 0,
            evidence_count=run.evidence_count,
        )

    def _after_rung(
        self, rung: LexicalRung, run: LadderRun, executed: Sequence[ExecutedProbe]
    ) -> LadderStop | None:
        """Apply the D.3 rules this rung can evaluate. Returns the stop it fired, if any.

        The rules themselves are `mailweave.policy.stopping`'s - WS-10 owns D.3's order and
        its predicates, and this module owns which of them a lexical rung is in a position to
        evaluate. The subset is rules 0, 1, 1b and 2; rules 3, 4, 5 and 6 need signals no
        lexical rung produces and are evaluated by the policy layer over the whole run.
        """
        if rung.rung is RungId.L0:
            hits = frozenset().union(*(e.ids_admitted for e in executed), frozenset())
            returned = sum(entry.ids_returned for entry in executed)
            self._fetch_bodies(run, sorted(hits), cap=MAX_BODY_FETCHES_L0)
            # D.3 rule 0: `answer_type_presence` is computed on L0's hits BEFORE any stop
            # rule is tested. The previous ordering had rule 1 kill the ladder first, which
            # disabled the architecture's only answer to T-RC2 on the confident-but-wrong
            # cases it exists for (ADV-004).
            run.answer_type = evaluate_answer_type_presence(run.parsed, self._texts(run))
            run.exact_signal = evaluate_exact_signal(
                run.parsed,
                executed_query=executed[0].probe.query if executed else "",
                hit_count=returned,
                hit_texts=self._texts(run),
            )
            inputs = self._stop_inputs(run, hit_count=returned)
            if rule_1_stops(inputs):
                # D.3 rule 1: identity resolution. Nothing escalates from it and nothing
                # feeds it, so the ladder halts where the rule fired.
                return LadderStop(
                    rule=StopRule.RULE_1.value, fired_after=RungId.L0, halts_after=RungId.L0
                )
            if rule_1b_stops(inputs):
                # D.3 rule 1b carries its own "or the query carries no answer-type cue"
                # escape, which is why this conjunct is `not blocks_stop` and rule 2's is
                # not. **Both predicates live in `mailweave.policy.stopping`**, which is
                # WS-10's single copy of D.3: two rounds have got the difference between
                # these two rules wrong, and a rule written out twice is a rule that can be
                # edited once (R-ARCH-031).
                return LadderStop(
                    rule=StopRule.RULE_1B.value, fired_after=RungId.L0, halts_after=RungId.L0
                )
            return None
        if rung.rung is RungId.L1:
            hits = frozenset().union(*(e.ids_admitted for e in executed), frozenset())
            returned = sum(entry.ids_returned for entry in executed)
            self._fetch_bodies(run, sorted(hits), cap=MAX_BODY_FETCHES_L1)
            run.answer_type = evaluate_answer_type_presence(run.parsed, self._texts(run))
            # D.3 rule 2, with all four conjuncts - the fourth is the one A.7's L1 row and
            # D.3 disagreed about for a whole document revision (CONS-036).
            #
            # **The fourth conjunct is `answer_type_presence`, which is `present is True`**
            # (R-RETR-007). It was `not answer_type.blocks_stop`, i.e. `present is not
            # False`, which is rule **1b**'s "or the query carries no answer-type cue"
            # escape imported into rule 2 - where neither D.3 nor A.7's L1 row puts it. The
            # tri-state makes the difference load-bearing rather than pedantic: `present is
            # None` is every ordinary non-interrogative query, so the escape made the stop
            # fire on almost all of them, and whether a thread whose evidence is split
            # across two messages was found at all turned on the query's *grammar* -
            # "from:dev@team.example cutover" stopped and missed it, "when did we cutover
            # from:dev@team.example" did not stop and found it, same mailbox, same evidence.
            if rule_2_stops(self._stop_inputs(run, hit_count=returned)):
                return LadderStop(
                    rule=StopRule.RULE_2.value, fired_after=RungId.L1, halts_after=RungId.L1B
                )
            return None
        if rung.rung is RungId.L1B:
            # Keyed on the probe's **unit** rather than on the constraint it enforces: two
            # pieces of one constraint are two probes and two sets, and keying on the
            # constraint name collapsed them into one - which would have made the
            # intersection of `"rollout cutover"` the set of threads containing "cutover"
            # rather than the threads containing both (R-RETR-008).
            by_unit = {entry.probe.unit: entry.threads for entry in executed if entry.probe.unit}
            sets = list(by_unit.values())
            run.decomposition = Decomposition(
                threads_by_constraint=by_unit,
                intersection=frozenset.intersection(*sets) if sets else frozenset(),
                union=frozenset().union(*sets, frozenset()),
            )
            return None
        if rung.rung is RungId.L2:
            run.relaxation = tuple(
                RelaxationStep(
                    dropped=entry.probe.dropped[0],
                    q=entry.probe.query,
                    hit_count=entry.ids_returned,
                )
                for entry in executed
                if entry.probe.dropped
            )
            return None
        return None
