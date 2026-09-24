"""The lexical ladder, driven end to end against a whole mailbox behind the real client.

`tests/test_preflight_runner_end_to_end.py` did this for the preflight runner; this file does
it for WS-04. Real URL construction, real bearer header, real retry ladder, real egress
allowlist, real `DispositionLedger` - with an `httpx.MockTransport` where the socket would be,
and `tests/conftest.py` denying `socket.connect` for every test in it.

**The five rungs are tested by what they have in common, not one at a time.** This project's
recurring defect is "one shape validated, peers trusted": a guard written against the case its
author had in mind while its peers are assumed to follow. Five rungs is five shapes, so the
property that makes the ladder accountable is asserted **over the whole `LADDER` population at
once**, in `test_every_rung_shares_the_one_property_that_makes_the_ladder_accountable`, with
the population read from `LADDER` by name *and* by count so the sweep cannot be emptied by
narrowing its own scope - which is how round 12's sweep passed while covering nothing.

**The test that matters most is the issue-#296 non-reproduction.** Gmail's own MCP server
returns the right thread while omitting the message that caused the match, with no truncation
marker. That bug is why this project exists, and there are two ways it can happen:

  * MailWeave drops it - `test_the_message_that_caused_the_match_is_in_the_response_even_
    though_it_is_the_oldest` asserts directly that it does not, on a nine-message thread whose
    only match is the oldest message;
  * **Gmail** drops it - the `threads.get` for a thread comes back without a message the
    `messages.list` for the same query returned. `test_a_thread_map_that_omits_one_of_its_own_
    hits_is_withheld_rather_than_shipped` executes that, and the thread gets A.7a's own
    disposition: not a `Source`, every id observed in it withheld under
    `partial_source_failure` with a retrieval affordance. Round 15 refused the whole response
    instead, on the stated grounds that A.7a's answer was not expressible in the shipped
    schema - which was false (R-RETR-010), and amendment A8's text now says so. What is
    genuinely inexpressible is one number, `Source.stated_total` for that thread.

No fixture here carries real or realistic personal mail: addresses use the reserved `.example`
and `.invalid` TLDs (RFC 2606/6761) and every subject and body is invented for the structural
property the test is about. `test_no_fixture_in_this_file_carries_anything_that_could_be_real_
mail` executes that rather than asserting it.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from mailweave.constants import (
    ANYWHERE_OPERATOR,
    DEFAULT_PAGE_SIZE,
    MAILBOX_LOCATION_PREFIX,
    MAX_BODY_FETCHES_L1,
    MAX_BROADENING_PROBES,
    MAX_DECOMPOSITION_PROBES,
    MAX_HIT_THREADS,
    SPAM_OPERATOR,
    WIDENING_MAILBOX_OPERATORS,
    carriage_token,
    carries_no_content,
    is_the_widening_mailbox_operator,
    matchable_content_of,
    max_relax_probes,
    query_tokens,
    widens_beyond_the_default_mailbox,
)
from mailweave.envelope.disposition import DispositionLedger, ObservedEndpoint
from mailweave.envelope.reasons import GmailQueryMatch, RungId
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import (
    Depth,
    EmptyDiagnosisStatus,
    NotTriedWhy,
    Outcome,
    Role,
    WithheldCap,
)
from mailweave.errors import QueryNotSearchable
from mailweave.gmail import BackoffPolicy, CallMeter, GmailClient, StaticToken
from mailweave.net.egress import build_client
from mailweave.query import (
    KIND_BY_OPERATOR,
    AnswerType,
    OperatorKind,
    OperatorName,
    ParsedQuery,
    analyse,
    carries_nothing_to_select_by,
    declares_the_search_region,
)
from mailweave.query.analysis import (
    TERMS_CONSTRAINT,
    VACUOUS_TOKEN_CONSTRAINT,
    constraints_carried_whole,
    dropped_declarations,
    search_region_of,
    selects_something,
)
from mailweave.retrieval.assemble import STRUCTURAL_SIMILARITY_RUNG, assemble, hit_threads
from mailweave.retrieval.ladder import (
    LADDER,
    LADDER_RUNGS,
    BroadeningRung,
    DecompositionRung,
    ExactOperatorRung,
    FilteredRung,
    LadderRun,
    LadderRunner,
    Probe,
    RelaxationRung,
    plan_ladder,
    why_this_q_is_not_a_probe,
)
from mailweave.retrieval.signals import ExactBranch
from tests.fixtures.mailbox import Msg, SyntheticMailbox, UnimplementedOperator, epoch_ms
from tests.fixtures.source_trees import parsed as parse_module
from tests.fixtures.source_trees import source_files
from tests.test_query_analysis import FIDELITY_TABLE

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
UTC_ZONE = ZoneInfo("UTC")
TOKEN = "ya29.SECRET-ACCESS-TOKEN-NEVER-IN-A-LADDER-FIXTURE"

#: The phrase the issue-#296 thread's oldest message carries, and no other message does.
#: Three content tokens after stopword removal, which is A.8a branch E-b's published bar.
ANCIENT_PHRASE = "rollout window slipped"


# --- the mailbox -------------------------------------------------------------------------


def ancient_thread() -> tuple[Msg, ...]:
    """The issue-#296 shape: a nine-message thread whose only match is the oldest message.

    Eight months of later traffic sit on top of it. A tool that returns "the thread" by
    taking its recent messages returns eight messages, none of which is the answer, and says
    nothing about the ninth. That is the bug, and it is the one this fixture exists to make
    reproducible.
    """
    oldest = Msg(
        id="anc-1",
        thread_id="t-ancient",
        sender="ana@team.example",
        subject="Vendor selection",
        body=f"The {ANCIENT_PHRASE} to the second week of April.",
        internal_date_ms=epoch_ms(2026, 1, 6),
        to=("bo@team.example",),
    )
    later = tuple(
        Msg(
            id=f"anc-{index}",
            thread_id="t-ancient",
            sender="bo@team.example" if index % 2 else "cy@team.example",
            subject="Re: Vendor selection",
            body=f"Adding note {index} for the record.",
            internal_date_ms=epoch_ms(2026, 6, index),
            to=("ana@team.example",),
        )
        for index in range(2, 10)
    )
    return (oldest, *later)


def split_thread() -> tuple[Msg, ...]:
    """The L1b shape (PF-9): two constraints satisfied by two *different* messages.

    `from:dev@team.example cutover` matches no single message here. Gmail's `q` is
    message-scoped (RO F2), so L1 returns nothing however correct the parse was; the
    constraint lives across `spl-1` and `spl-2`, which is what decomposition recovers.
    """
    return (
        Msg(
            id="spl-1",
            thread_id="t-split",
            sender="dev@team.example",
            subject="Migration kickoff",
            body="Starting the workstream on the second.",
            internal_date_ms=epoch_ms(2026, 3, 2),
            to=("ops@team.example",),
        ),
        Msg(
            id="spl-2",
            thread_id="t-split",
            sender="ops@team.example",
            subject="Re: Migration kickoff",
            body="Cutover scheduled for 2026/04/14 at midnight.",
            internal_date_ms=epoch_ms(2026, 3, 5),
            to=("dev@team.example",),
        ),
        Msg(
            id="spl-3",
            thread_id="t-split",
            sender="qa@team.example",
            subject="Re: Migration kickoff",
            body="Acknowledged with no further changes.",
            internal_date_ms=epoch_ms(2026, 3, 6),
            to=("ops@team.example",),
        ),
        Msg(
            id="spl-4",
            thread_id="t-split",
            sender="ops@team.example",
            subject="Re: Migration kickoff",
            body="Adding the checklist.",
            internal_date_ms=epoch_ms(2026, 3, 9),
            to=("qa@team.example",),
        ),
    )


def terms_thread() -> tuple[Msg, ...]:
    """The founding bug's **commonest** shape: two bare words, two messages, one thread.

    `"rollout cutover"` is what a user types. Both words are residual free text, so the parse
    produces one `terms` constraint - and until round 16 that made k=1, put L1b's plan at
    empty, reported the rung `not_applicable`, and left this thread unfindable by any rung
    (R-RETR-008). Round 15's L1b fixture passes because its constraints happen to be an
    operator plus a term; this one has no operator to lean on.
    """
    return (
        Msg(
            id="trm-1",
            thread_id="t-terms",
            sender="ops@team.example",
            subject="Programme note",
            body="The rollout is on the agenda for the review.",
            internal_date_ms=epoch_ms(2026, 2, 3),
            to=("qa@team.example",),
        ),
        Msg(
            id="trm-2",
            thread_id="t-terms",
            sender="qa@team.example",
            subject="Re: Programme note",
            body="Handover is pencilled in for the second week.",
            internal_date_ms=epoch_ms(2026, 2, 6),
            to=("ops@team.example",),
        ),
    )


def stop_thread() -> tuple[Msg, ...]:
    """One message that matches at L1 and carries a date-like token, for D.3 rule 2.

    Both halves are load-bearing: the query must *match* (a stop with no hits is not the
    rule) and the hit must carry the answer type (`present is True` is the fourth conjunct).
    `answer_type_presence` is measured on the hit's text, so a fixture that does not match
    reports `present: False` for the wrong reason and would pass a weaker test.
    """
    return (
        Msg(
            id="stp-1",
            thread_id="t-stop",
            sender="dev@team.example",
            subject="Schedule",
            body="The vendor decision landed on 2026/04/14 and was recorded.",
            internal_date_ms=epoch_ms(2026, 4, 14),
            to=("qa@team.example",),
        ),
    )


def dense_thread() -> tuple[Msg, ...]:
    """Six messages that each satisfy **both** constraints of one query, by themselves.

    The case `Decomposition`'s docstring bounds: every id a decomposition probe would name
    here was already admitted by an earlier probe, so both probes contribute nothing new and
    the intersection is empty - while every one of those messages is in `H` and disclosed.
    Six rather than two, because L1 must not stop (D.3 rule 2 caps its stop at five hits) or
    L1b would never run at all.
    """
    return tuple(
        Msg(
            id=f"dns-{index}",
            thread_id="t-dense",
            sender="bulkops@team.example",
            subject="Roster",
            body=f"Roster entry {index} for the duty rotation.",
            internal_date_ms=epoch_ms(2026, 5, index),
            to=("qa@team.example",),
        )
        for index in range(1, 7)
    )


#: Fourteen single-message threads sharing one term, which is two more than `MAX_HIT_THREADS`.
#: Two more, not one, so the overflow is a set rather than a boundary case that a fencepost
#: error would satisfy.
BULK_THREADS = 14


def bulk_threads() -> tuple[Msg, ...]:
    return tuple(
        Msg(
            id=f"blk-{index:02d}",
            thread_id=f"t-bulk-{index:02d}",
            sender=f"vendor{index:02d}@supplier.example",
            subject="Statement",
            body=f"Procurement statement number {index:02d}.",
            internal_date_ms=epoch_ms(2026, 7, 1 + index),
            to=("ops@team.example",),
        )
        for index in range(1, BULK_THREADS + 1)
    )


def mailbox() -> SyntheticMailbox:
    """One mailbox, rebuilt per test so a call log is never shared between assertions."""
    return SyntheticMailbox(
        messages=(
            *ancient_thread(),
            *split_thread(),
            *terms_thread(),
            *dense_thread(),
            *bulk_threads(),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )


def make_client(box: SyntheticMailbox) -> GmailClient:
    """The shipped client. Only the socket is replaced."""
    return GmailClient(
        token=StaticToken(TOKEN),
        http=build_client(inner=box.transport()),
        meter=CallMeter(),
        policy=BackoffPolicy(),
        sleeper=lambda _seconds: None,
        jitterer=lambda: 0.5,
    )


def parse(query: str) -> ParsedQuery:
    return analyse(query, now=NOW, zone=UTC_ZONE)


def drive(
    query: str, *, box: SyntheticMailbox | None = None
) -> tuple[SyntheticMailbox, GmailClient, DispositionLedger, LadderRun]:
    """Run the whole ladder for `query` and hand back everything an assertion may need."""
    box = mailbox() if box is None else box
    client = make_client(box)
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run(query, now=NOW, zone=UTC_ZONE)
    return box, client, ledger, run


def answer(query: str, *, box: SyntheticMailbox | None = None) -> tuple[SyntheticMailbox, Envelope]:
    """`drive`, then assemble the envelope: the whole of WS-04's exit condition."""
    box, client, ledger, run = drive(query, box=box)
    return box, assemble(run, client=client, ledger=ledger)


def rows_of(envelope: Envelope, thread_id: str) -> dict[str, Role]:
    source = next(s for s in envelope.sources if s.thread_id == thread_id)
    return {row.id: row.role for row in source.messages}


# --- the queries the corpus is driven with -------------------------------------------------
#
# Each is here because it puts a *different* rung into the executed set. The commonality
# sweep below reads this table and then checks that between them every member of `LADDER`
# executed at least once, so a query removed from the table fails the sweep rather than
# quietly shrinking it.

CORPUS: dict[str, str] = {
    "exact_phrase_stops_at_l0": f'"the {ANCIENT_PHRASE}"',
    "filtered_single_rung": "procurement",
    "decomposition_recovers_the_thread": "from:dev@team.example cutover",
    "decomposition_recovers_two_bare_words": "rollout pencilled",
    "relaxation_and_broadening_on_zero_hits": 'from:nobody@team.example "a phrase never written"',
    "relaxation_finds_the_restoring_drop": 'from:ops@team.example "a phrase never written"',
}


# --- what all five rungs have in common ----------------------------------------------------


def test_the_ladder_population_is_the_five_rungs_the_architecture_names() -> None:
    """Read by name and by count, so no later test can be satisfied by an empty population."""
    assert [type(rung) for rung in LADDER] == [
        ExactOperatorRung,
        FilteredRung,
        DecompositionRung,
        RelaxationRung,
        BroadeningRung,
    ]
    assert LADDER_RUNGS == (RungId.L0, RungId.L1, RungId.L1B, RungId.L2, RungId.L3)
    assert len(LADDER) == 5
    assert len(set(LADDER_RUNGS)) == 5


def test_every_rung_shares_the_one_property_that_makes_the_ladder_accountable() -> None:
    """The single test the five rungs are covered by, rather than five tests of one rung each.

    A rung is a *plan* plus an *execution*, and the plan is a pure function of the parsed
    query. Four things follow for all five at once, and all four are asserted here over the
    whole corpus:

      * **enumerable** - every probe that ran was in `plan_ladder(parsed)`, computed before
        anything was sent. ROUTE-03 asks this of L2 only; it is true of the ladder;
      * **reproducible** - the same `(query, now, zone)` yields the same plan, from a second
        independent parse. Nothing in a plan reads a clock, a counter or a previous rung;
      * **accountable** - `H` is exactly the set of ids the *mailbox* returned to the probes
        that ran. The witness is the fixture's own `returned_ids` log, taken outside the
        process, not the ladder's account of itself;
      * **declared** - every executed probe left a `ScanScopeEntry` carrying that probe's own
        `q`, its rung and its page counts, and the `includeSpamTrash` on the wire equals the
        one derived from the probe's query.

    The population is `LADDER`, and the final assertion is that between them the corpus
    executed every member of it - so this sweep cannot pass by covering nothing.
    """
    executed_rungs: set[RungId] = set()
    for name, query in CORPUS.items():
        parsed = parse(query)
        planned = plan_ladder(parsed)

        # reproducible: a second parse of the same inputs plans the same probes.
        again = plan_ladder(analyse(query, now=NOW, zone=UTC_ZONE))
        assert [(p.rung, p.query) for p in again] == [(p.rung, p.query) for p in planned], name

        box, _client, ledger, run = drive(query)
        ran = run.executed_probes
        executed_rungs |= set(run.rungs_run)

        # enumerable: nothing was sent that was not listable first.
        listed = {(probe.rung, probe.query) for probe in planned}
        assert {(e.probe.rung, e.probe.query) for e in ran} <= listed, name
        # ...and the plan a rung published is exactly what that rung executed, in order.
        for execution in run.executions:
            if execution.skipped is None:
                assert [e.probe for e in execution.executed] == list(execution.planned), name

        # declared: one scan-scope entry per executed probe, carrying its own q and rung.
        entries = [(entry.q, entry.rung) for entry in ledger.scan_scope]
        assert entries == [(e.probe.query, e.probe.rung) for e in ran], name
        # ...and the wire agrees about the mailbox scope the probe derived from its own q.
        assert box.queries == [(e.probe.query, e.probe.include_spam_trash) for e in ran], name

        # accountable: `H` is the mailbox's own record of what it handed back, and nothing
        # in this module could have shrunk it - `list_messages` records the page before the
        # ladder sees a count.
        returned: set[str] = set()
        for _q, ids in box.returned_ids:
            returned |= set(ids)
        assert ledger.hit_ids == frozenset(returned), name
        assert all(
            ledger.origins[message_id].endpoint is ObservedEndpoint.MESSAGES_LIST
            for message_id in returned
        ), name

    assert executed_rungs == set(LADDER_RUNGS), (
        f"the corpus executed {sorted(executed_rungs)}; this sweep is only worth its name "
        f"if every rung of {sorted(LADDER_RUNGS)} is in it"
    )


def test_a_probe_derives_its_mailbox_scope_from_its_own_query_and_cannot_disagree() -> None:
    """R-SEC-051's coupling, at the rung that is entitled to leave the default mailbox.

    L3's broadening probe is the only one in the ladder whose `q` widens the mailbox. The
    flag is not stated beside it; it is read off the string that will be sent, so the pair
    cannot come apart. `GmailClient._fetch_list_page` raises on a disagreeing pair, and the
    end-to-end run below would fail there if it ever did.
    """
    parsed = parse('from:nobody@team.example "a phrase never written"')
    broadening = BroadeningRung().plan(parsed)

    widening = [probe for probe in broadening if probe.include_spam_trash]
    assert len(widening) == 1
    assert all(
        not probe.include_spam_trash for probe in plan_ladder(parsed) if probe not in widening
    )

    box, _client, _ledger, run = drive('from:nobody@team.example "a phrase never written"')
    assert (widening[0].query, True) in box.queries
    assert RungId.L3 in run.rungs_run


def test_a_probe_with_an_empty_query_cannot_be_constructed() -> None:
    """A listing with no `q` asks Gmail for the whole mailbox, which is not a relaxation."""
    with pytest.raises(ValueError, match="empty q"):
        Probe(rung=RungId.L2, query="   ", why="nothing left")


#: Every spelling of the widening operator the round-12/13 evasions found, plus the plain
#: one. Read from `constants` rather than written out, because a second hand-typed copy of a
#: scope operator is the shape this repository keeps finding (R-SEC-051, R-SEC-058).
SCOPE_ONLY_SPELLINGS: tuple[str, ...] = (
    ANYWHERE_OPERATOR,
    ANYWHERE_OPERATOR.upper(),
    f"({ANYWHERE_OPERATOR})",
    f"  {ANYWHERE_OPERATOR}  ",
    f"{ANYWHERE_OPERATOR} {SPAM_OPERATOR}",
)


@pytest.mark.parametrize("query", SCOPE_ONLY_SPELLINGS)
def test_a_probe_that_is_only_a_mailbox_scope_operator_cannot_be_constructed(
    query: str,
) -> None:
    """R-RETR-006, BLOCKER: the shape that walked around the empty-`q` refusal.

    `Probe.__post_init__` refused an empty `q` because "a listing with no query asks Gmail
    for the whole mailbox". A `q` that is *only* the widening operator asks for the same
    thing plus spam and trash, and it is a non-empty string, so it passed - and round 15's
    `BroadeningRung` composed exactly that whenever the parse left no fragment to widen.
    Sixty threads of an untouched mailbox came back as `role: matched` under
    `outcome: answered` and `term_coverage: 1.0`.

    Parametrised over the spellings the mailbox-scope coupling has been evaded in twice
    before, because "one shape validated, peers trusted" is what a single-case guard here
    would be.
    """
    with pytest.raises(ValueError, match="only a mailbox-scope operator"):
        Probe(rung=RungId.L3, query=query, why="broadening", enforced=("terms",))


def test_a_scope_operator_beside_a_fragment_of_the_query_is_still_a_probe() -> None:
    """The other half, so the guard refuses the empty broadening and not broadening itself.

    A.7 L3 broadens the query into the whole mailbox; what it may not do is *replace* the
    query with the mailbox. `in:` plus a term is the first; `in:` alone is the second.
    """
    probe = Probe(
        rung=RungId.L3,
        query=f"{ANYWHERE_OPERATOR} procurement",
        why="broadening",
        enforced=("terms",),
    )
    assert probe.include_spam_trash is True


#: Queries that select nothing: every fragment either says *where* to look or *what to
#: leave out*. Parametrised over the same spellings as `SCOPE_ONLY_SPELLINGS`, because a
#: guard that reads one spelling of an operator has been evaded here twice before.
SELECTS_NOTHING_SPELLINGS: tuple[str, ...] = (
    f"{ANYWHERE_OPERATOR} -cutover",
    f"{ANYWHERE_OPERATOR.upper()} -cutover",
    f"({ANYWHERE_OPERATOR}) -from:ana@team.example",
    f"{ANYWHERE_OPERATOR} -cutover -rollout",
    f"{ANYWHERE_OPERATOR} {SPAM_OPERATOR} -is:unread",
)


@pytest.mark.parametrize("query", SELECTS_NOTHING_SPELLINGS)
def test_a_probe_that_leaves_the_mailbox_and_only_excludes_cannot_be_constructed(
    query: str,
) -> None:
    """R-RETR-006's peer, found in round 16's own fix for R-RETR-006.

    The round-16 rule was "the broadening probe is planned only when it carries a fragment
    of the query". `-cutover` **is** a fragment of the query, so the rule let through the
    same request with a disguise on: the scope operator conjoined with a negation asks Gmail
    for spam and trash minus a few messages. Executed against a mailbox whose inbox all
    mentioned the term, `mailweave_search("-cutover")` put that probe on the wire and
    returned eight spam messages as `role: matched` under `outcome: answered` and
    `term_coverage: 1.0` - R-RETR-006's own three failures, in the shape its fix left
    standing.

    A scope operator says where; a negation says what not; neither says what. Refused at
    construction rather than only at the rung, so no later rung can re-derive the policy
    wrongly - which is the same two-place argument the bare-scope refusal above makes.
    """
    with pytest.raises(ValueError, match="must ask for something"):
        Probe(rung=RungId.L3, query=query, why="broadening", enforced=("terms",))


def test_a_query_that_only_excludes_is_not_broadened_into_spam_and_trash() -> None:
    """The same fact at the wire, on the query a user would actually type.

    Every inbox message says "cutover" and the spam does not, so L1 finds nothing and L3 is
    reached - which is the only way the broadening probe runs at all, and is why the
    fixture is built this way rather than asserted on a plan.

    What is asserted is the **negative**: no request leaves the default mailbox, so no spam
    or trash id enters `H`. L1 still executes the user's own query verbatim inside their own
    mailbox, which is what they asked for; what it must not do is widen a query that named
    nothing to find.
    """
    box = SyntheticMailbox(
        messages=tuple(
            Msg(
                id=f"exc-{index:02d}",
                thread_id=f"t-exc-{index:02d}",
                sender="ana@team.example",
                subject="Notice",
                body=("Cutover notice." if index % 5 else "Unrelated bulk notice."),
                internal_date_ms=epoch_ms(2026, 5, 1) + index * 1000,
                to=("bo@team.example",),
                labels=("INBOX",) if index % 5 else ("SPAM",),
            )
            for index in range(1, 21)
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )
    _box, client, ledger, run = drive("-cutover", box=box)

    assert [widened for _q, widened in box.queries] == [False]
    assert box.queries == [("-cutover", False)]
    assert run.rungs_run == (RungId.L1,)
    assert ledger.hit_ids == frozenset()

    envelope = assemble(run, client=client, ledger=ledger)
    assert envelope.sources == ()
    assert envelope.retrieval_report.outcome is Outcome.INCONCLUSIVE


#: Queries whose parse produces **no constraint at all**: a boolean expression MailWeave
#: does not regroup, a grouped one, a `{...}` group, an all-stopword query, punctuation, and
#: - round 17's additions - the tokens that name nothing for Gmail to match. R-RETR
#: reproduced several of these; the others are peers, here because a fix for the reported
#: shapes alone is this project's recurring defect.
UNSEARCHABLE_QUERIES: tuple[str, ...] = (
    "(rollout OR escalation)",
    "(rollout)",
    "{from:ana@team.example from:bo@team.example}",
    "the and of",
    "?",
    '""',
    '" "',
    "subject:",
)


@pytest.mark.parametrize("query", UNSEARCHABLE_QUERIES)
def test_a_query_the_parser_produces_nothing_from_is_reported_not_scanned(query: str) -> None:
    """R-RETR-006 at the wire, and R-RETR-022 at the response: **no Gmail call, and a report**.

    The first assertion is `box.queries == []`, and it is unchanged. A parse that yielded no
    constraint is a parse failure, and round 15 answered it by listing the whole mailbox with
    `includeSpamTrash=true` - reading spam and trash for a query that asked for neither, and
    reporting the results as matches. There is nothing to narrow by, so there is nothing to
    widen either.

    The second is round 17's, and it is the difference between not *searching* and not
    *answering*. Round 16 raised, so a caller got no envelope at all - which fails ROUTE-01's
    own sentence ("a no-evidence outcome is a structured report, never an empty set or a
    nonexistence claim") more completely than the bare empty payload the criterion was
    written against. The response now names the parse, every token it dropped and why, all
    five rungs as not tried, and an `empty_diagnosis`: a report a caller can act on, built
    with no Gmail call and with no false statement about what executed.
    """
    box = mailbox()
    client = make_client(box)
    ledger = DispositionLedger()

    run = LadderRunner(client, ledger).run(query, now=NOW, zone=UTC_ZONE)

    assert box.queries == [], (query, box.queries)
    assert ledger.hit_ids == frozenset()
    assert client.meter.reading().api_calls == 0
    assert run.rungs_run == ()
    assert set(run.rungs_skipped) == set(LADDER_RUNGS)

    envelope = assemble(run, client=client, ledger=ledger)
    report = envelope.retrieval_report
    assert envelope.sources == ()
    assert report.outcome is Outcome.INCONCLUSIVE
    assert report.rungs == ()
    assert {entry.rung for entry in report.not_tried} == {
        *(rung.value for rung in LADDER_RUNGS),
        RungId.L4.value,
        STRUCTURAL_SIMILARITY_RUNG,
        # L6 joined this set when the ranking rung was built. It is `not_applicable` and
        # carries no affordance, which is the honest account of a rung with nothing to
        # order: D.7 scopes mechanical ranking to "whenever more than one candidate is
        # disclosed", and this response discloses none. A rung with no account at all -
        # which is what L6 had for one draft, being named neither in `rungs` nor here - is
        # the state `LadderAccount.covers` is built to notice.
        RungId.L6.value,
    }
    assert all(entry.why is NotTriedWhy.NOT_APPLICABLE for entry in report.not_tried)
    assert report.empty_diagnosis is not None
    # Every reason the parse can give travels in the response rather than in an exception
    # message, which is what "structured report" means and what the raise could not do.
    declared = {name for name, _why in dropped_declarations(parse(query))}
    assert declared, query
    assert declared <= {entry.constraint for entry in envelope.asked_for.dropped}
    assert all(entry.why for entry in envelope.asked_for.dropped)


def test_a_query_that_asked_for_nothing_at_all_is_refused_rather_than_reported() -> None:
    """The one query that still raises, and the line round 17 drew (ROUTE-01, Part 5).

    Everything the parser cannot search gets a structured report - except a query that asked
    for nothing. There is no parse to show, no token to declare dropped, no constraint to
    relax and no rung whose non-application means anything, so every field of the report
    would describe a search with no subject: `term_coverage` reads 1.0 because nothing was
    dropped (nothing was asked), and the diagnosis reads `complete` because there was no drop
    to try. Together they say "MailWeave looked and found nothing" about a question nobody
    put, which is the nonexistence claim ROUTE-01 forbids in its other half.

    Both directions are asserted, so the line cannot be satisfied by refusing everything or
    by reporting on everything.
    """
    for empty in ("", "   ", "\t\n"):
        box = mailbox()
        client = make_client(box)
        with pytest.raises(QueryNotSearchable) as raised:
            LadderRunner(client, DispositionLedger()).run(empty, now=NOW, zone=UTC_ZONE)
        assert box.queries == []
        assert str(raised.value)

    box = mailbox()
    client = make_client(box)
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run("the and of", now=NOW, zone=UTC_ZONE)
    assert assemble(run, client=client, ledger=ledger).retrieval_report.rungs == ()


@pytest.mark.parametrize("query", UNSEARCHABLE_QUERIES)
def test_no_rung_plans_a_probe_for_a_query_the_parser_produced_nothing_from(
    query: str,
) -> None:
    """The same fact one level down, over the whole `LADDER` rather than at the runner.

    The refusal in `run_parsed` is a policy; this is the property that makes the policy
    redundant. Asserted over the population read from `LADDER` by count, so a rung added
    later is covered by this test rather than by whoever remembers it.
    """
    parsed = parse(query)
    assert parsed.constraints == ()
    assert len(LADDER) == 5
    for rung in LADDER:
        assert rung.plan(parsed) == (), (query, rung.rung)
    assert plan_ladder(parsed) == ()


#: Queries whose parse produces a constraint apiece and still names nothing to **find**:
#: a bare widening scope operator in its plain, capitalised and doubled spellings, and the
#: same request with an exclusion attached as a disguise. R-RETR-006 reported the shape
#: MailWeave *composed*; this is the shape a caller can type, and round 16's first fix for
#: the composed one turned it into an uncaught `ValueError` out of `plan_ladder`.
UNPROBEABLE_QUERIES: tuple[str, ...] = (
    ANYWHERE_OPERATOR,
    SPAM_OPERATOR,
    ANYWHERE_OPERATOR.upper(),
    f"{ANYWHERE_OPERATOR} {SPAM_OPERATOR}",
    f"{ANYWHERE_OPERATOR} -cutover",
    f"{SPAM_OPERATOR} -from:ana@team.example",
)


@pytest.mark.parametrize("query", UNPROBEABLE_QUERIES)
def test_a_query_that_names_only_where_to_look_is_reported_not_scanned(query: str) -> None:
    """The declared inability, on the class `parsed.constraints` cannot see.

    These parse to an `in` constraint - so the round-16 refusal keyed on "no constraint at
    all" let them through - and they still name nothing to find. Answering one means listing
    the mailbox, spam and trash included, and reporting the result as matches: R-RETR-006's
    three failures reached from the caller's side instead of from L3's.

    The assertion that matters is unchanged: **no Gmail call at all**. What round 17 adds is
    that the caller gets the reason as a response instead of as an exception, and that the
    response does not claim to have enforced the constraint it never sent: the `in`
    constraint parsed, no rung executed, so `enforced` is empty and the drop names why
    nothing could be planned.
    """
    box = mailbox()
    client = make_client(box)
    ledger = DispositionLedger()

    run = LadderRunner(client, ledger).run(query, now=NOW, zone=UTC_ZONE)

    assert box.queries == [], (query, box.queries)
    assert ledger.hit_ids == frozenset()
    assert client.meter.reading().api_calls == 0
    # Non-empty constraints is what tells this class apart from `UNSEARCHABLE_QUERIES`, and
    # it is asserted so the two tests cannot collapse into one that covers only the first.
    assert parse(query).constraints != ()
    assert plan_ladder(parse(query)) == ()

    envelope = assemble(run, client=client, ledger=ledger)
    assert envelope.sources == ()
    assert envelope.retrieval_report.rungs == ()
    assert envelope.retrieval_report.not_tried != ()
    assert envelope.asked_for.enforced == ()
    assert envelope.asked_for.term_coverage == 0.0
    assert {entry.constraint for entry in envelope.asked_for.dropped} >= {
        c.name for c in parse(query).constraints
    }


def test_a_query_naming_where_to_look_and_what_to_find_is_searched_in_that_scope() -> None:
    """The other half, so the refusal above cannot be satisfied by refusing everything.

    A widening scope operator **with** something to look for is a legitimate query and is
    executed as written: one probe, the user's own `q`, and `includeSpamTrash` derived from
    it rather than declared beside it. The broadening rung then plans nothing, because a
    probe identical to L1's own query is not a broadening of it.
    """
    query = f"{ANYWHERE_OPERATOR} {ANCIENT_PHRASE}"
    box, _client, ledger, run = drive(query)

    assert box.queries[0] == (query, True)
    assert RungId.L1 in run.rungs_run
    assert ledger.hit_ids
    # L3 would have re-sent L1's own query; it does not plan one.
    assert BroadeningRung().plan(parse(query)) == ()
    assert box.queries.count((query, True)) == 1


def test_a_query_the_parser_carried_none_of_does_not_report_full_coverage() -> None:
    """LEX-02's number, on the queries that used to divide zero by zero and report 1.0."""
    for query in ("(rollout OR escalation)", "the and of", "?"):
        parsed = parse(query)
        assert parsed.term_coverage(parsed.constraints) == 0.0, query
        assert "unsearchable_query" in dict(dropped_declarations(parsed)), query
    # ...and a query that genuinely asked for nothing still reports 1.0, because nothing
    # was dropped. The two are the same arithmetic and only one of them is a failure.
    blank = parse("   ")
    assert blank.term_coverage(blank.constraints) == 1.0
    assert dropped_declarations(blank) == ()


#: Parse shapes chosen to make each rung's `plan` do something different: an exact candidate,
#: an unresolvable date, a participant to widen, a phrase, an unknown operator, and a query
#: with more constraints than the relaxation budget.
WELL_FORMED_CASES: tuple[str, ...] = (
    "procurement",
    "from:dev@team.example cutover",
    "rollout after:notadate",
    "rollout after:2026/05/01 before:2026/06/01 from:ana@team.example",
    'rfc822msgid:<anc-1@mail.invalid> "the rollout window slipped" INV-2026-0041',
    "from:a@team.example to:b@team.example cc:c@team.example subject:kickoff "
    'label:vendors is:unread has:attachment "three word phrase" widget',
    "rollout OR fallback",
    "thread:abc rollout",
)


@pytest.mark.parametrize("query", WELL_FORMED_CASES)
def test_every_probe_of_every_rung_names_only_constraints_the_parse_produced(query: str) -> None:
    """A second property common to all five rungs, and the one LEX-02 counts at zero.

    Whatever a rung does to the query, its account of itself is written in the parse's own
    vocabulary: `enforced` and `dropped` name parsed constraints, they never overlap, and
    together they never claim a constraint the user did not write. A probe that named a
    constraint it did not carry is a signal silently dropped while the response says it was
    enforced - which is the one number LEX-02 sets to zero.

    The last clause is checked only for the rungs that carry fragments verbatim. L3 rewrites
    them by design - a date window becomes a wider one, `from:x` becomes `{from:x to:x}` - so
    a fragment-presence check would be asserting that broadening does not broaden.
    """
    parsed = parse(query)
    names = set(parsed.constraint_names)
    verbatim = {RungId.L0, RungId.L1, RungId.L1B, RungId.L2}

    planned = plan_ladder(parsed)
    assert planned, query

    for probe in planned:
        assert set(probe.enforced) <= names, (query, probe.rung, probe.enforced)
        assert set(probe.dropped) <= names, (query, probe.rung, probe.dropped)
        assert not set(probe.enforced) & set(probe.dropped), (query, probe.rung)
        assert probe.relaxes is (probe.rung is RungId.L2), (query, probe.rung)
        if probe.rung not in verbatim:
            continue
        for name in probe.enforced:
            constraint = parsed.constraint(name)
            assert constraint is not None
            assert any(fragment in probe.query for fragment in constraint.fragments), (
                query,
                probe.rung,
                name,
            )


def test_a_date_operator_mailweave_cannot_resolve_is_still_carried_when_l3_broadens() -> None:
    """The silent drop the `enforced`/`q` coupling was written against, executed.

    `after:notadate` is an operator MailWeave carries but cannot turn into a window - Gmail
    judges the value, we do not. L3 widens date constraints by replacing them with a wider
    window, and with no window to widen the constraint used to vanish from the broadened `q`
    while `enforced` went on naming it. It is carried unchanged instead.
    """
    parsed = parse("from:ana@team.example rollout after:notadate")
    assert parsed.window is None

    widened = BroadeningRung().plan(parsed)[0]
    assert "{from:ana@team.example to:ana@team.example}" in widened.query
    assert "after:notadate" in widened.query
    assert "after" in widened.enforced


def test_a_negated_participant_is_not_widened_into_its_own_opposite() -> None:
    """A.7 L3's `from:` -> `from|to` widens what an operator selects. A negation selects
    nothing, so there is nothing there to widen.

    `{-from:x to:x}` reads "not from x, or to x", which is nearly every message in a mailbox
    and is a different question from the one the user asked. It was reachable: paired with a
    mailbox-scope operator the user wrote, it composed a probe that *passed* the
    select-something check on the strength of its `to:` half and asked Gmail for spam and
    trash - R-RETR-006's shape once more, arrived at through the widening step rather than
    through the whole-mailbox one.
    """
    # A date gives the widening step something to change, so the probe below is the
    # widened one rather than the whole-mailbox one.
    negated = parse("-from:ana@team.example rollout after:2026/05/01")
    widened = BroadeningRung().plan(negated)[0]
    assert "-from:ana@team.example" in widened.query
    assert "{" not in widened.query
    assert "from" in widened.enforced

    # The positive operator beside it is still widened, so this is not a blanket exemption.
    both = parse("from:bo@team.example -from:ana@team.example rollout")
    query = BroadeningRung().plan(both)[0].query
    assert "{from:bo@team.example to:bo@team.example}" in query
    assert "-from:ana@team.example" in query

    # And with nothing else to select by, the rung plans nothing rather than a listing.
    assert BroadeningRung().plan(parse("-from:ana@team.example")) == ()


def test_no_query_the_operator_lexicon_can_spell_makes_a_rung_raise() -> None:
    """The standing form of "one shape validated, peers trusted", for the plan layer.

    `Probe.__post_init__` refuses a `q` that is a listing rather than a probe, which is the
    R-RETR-006 fix; every rung that composes a `q` out of a subset of the query's fragments
    must therefore decline to plan one, or an ordinary query becomes an uncaught
    `ValueError` out of `plan_ladder`. Round 16 got that right at L2 and L3 and wrong at
    L1b, and wrong again at L1, and the two shapes were found by sweeping rather than by
    thinking of them: over a 2,300-query cross-product of ordinary operator spellings, 757
    raised before the fix - 712 at L1b, 64 at L1 and 106 at L3, counted by which rungs raise
    rather than by query, so the three classes overlap and do not sum to 757.

    The vocabulary is **derived** - every spelling in `FIDELITY_TABLE`, which is itself bound
    to `OperatorName` by `test_the_fidelity_table_covers_every_operator_the_lexicon_claims`,
    plus each one negated, plus the widening scope operators and a few free-text shapes - so
    an operator added to the lexicon is swept without anyone remembering to add it here.

    **Scope, stated because it is a real bound:** singles and ordered pairs, not triples. A
    defect needing three fragments at once would not be seen here.
    """
    pieces = [written for written, _ in FIDELITY_TABLE.values()]
    pieces += [f"-{written}" for written in list(pieces)]
    pieces += sorted(WIDENING_MAILBOX_OPERATORS)
    pieces += ["rollout", "-cutover", f'"{ANCIENT_PHRASE}"', "the", "?"]

    swept = 0
    for first in pieces:
        for second in ("", *pieces):
            query = f"{first} {second}".strip()
            parsed_query = analyse(query, now=NOW, zone=UTC_ZONE)
            swept += 1
            try:
                planned = plan_ladder(parsed_query)
            except Exception as raised:  # pragma: no cover - the assertion is the report
                raise AssertionError(f"plan_ladder({query!r}) raised {raised!r}") from raised
            for probe in planned:
                # No rung plans a listing: the structural refusal never has a subject.
                assert why_this_q_is_not_a_probe(probe.query) is None, (query, probe.query)
                # And a rung that composes a `q` out of a *subset* of the query's fragments
                # is held to the wider rule, because nobody asked for what it composed.
                if probe.rung is not RungId.L1:
                    assert not carries_nothing_to_select_by(probe.query), (query, probe.query)
    # Anti-vacuity: the swept vocabulary is the lexicon's, not a list somebody maintains, and
    # the sweep is not empty. `test_the_fidelity_table_covers_every_operator_the_lexicon_claims`
    # is what binds that table to `OperatorName`, so an operator added there arrives here.
    assert {written for written, _ in FIDELITY_TABLE.values()} <= set(pieces)
    assert swept == len(pieces) * (1 + len(pieces)) > 2000, swept


#: Locations a caller can write with Gmail's location operator. The *narrowing* spellings:
#: the widening three are `WIDENING_MAILBOX_OPERATORS` and are read from there. Written as a
#: named vocabulary rather than one literal because the round-16 test that was supposed to
#: close this gap asserted over the single widening spelling its fix already covered, and
#: every narrowing one behaved exactly as its own docstring forbade (R-RETR-021).
NARROWING_MAILBOX_LOCATIONS: tuple[str, ...] = (
    "inbox",
    "sent",
    "drafts",
    "chats",
    "starred",
    "important",
    "scheduled",
)

#: A representative value for **every member of `OperatorName`**, so a sweep over the family
#: is generated from Gmail's own operator set rather than from the operators a finding
#: happened to name. A member added to the enum without a value here fails
#: `test_the_operator_family_vocabulary_covers_every_operator_this_parser_knows`, which is
#: the same "published and total" discipline `RELAXATION_ORDER` already has: an operator that
#: sorted itself out of a sweep by being new is exactly how "one shape validated, its peers
#: trusted" keeps happening in this repository.
OPERATOR_FAMILY_VALUES: dict[str, str] = {
    "from": "ana@team.example",
    "to": "bo@team.example",
    "cc": "cai@team.example",
    "bcc": "dee@team.example",
    "deliveredto": "eve@team.example",
    "subject": "vendor",
    "after": "2026/05/01",
    "before": "2026/06/01",
    "older_than": "2d",
    "newer_than": "7d",
    "label": "projecta",
    "category": "updates",
    "in": "inbox",
    "is": "unread",
    "has": "attachment",
    "list": "ops@parts.example",
    "filename": "plan.pdf",
    "size": "1000000",
    "larger": "5M",
    "smaller": "9M",
    "rfc822msgid": "<a1@mail.invalid>",
}

#: Every operator the registry declares region-selecting. Read from `KIND_BY_OPERATOR`, which
#: is the field that says what an operator does and is total over `OperatorName`, so an
#: operator registered `OperatorKind.REGION` tomorrow joins every sweep below with no edit
#: here. Round 18's population was `MAILBOX_LOCATION_PREFIX` plus a written list of the values
#: written under it, which covered *a new value under one prefix* and not *a new region
#: operator* - the gap R-RETR-036 registered one to prove.
REGION_DECLARING_OPERATORS: tuple[OperatorName, ...] = tuple(
    name for name in OperatorName if KIND_BY_OPERATOR[name] is OperatorKind.REGION
)

#: Every region declaration this lexicon can write, positively. Three sources and they answer
#: different questions: the locations a caller writes under Gmail's location operator, the
#: widening spellings of it, and one fragment per registered region-selecting operator.
POSITIVE_REGION_FRAGMENTS: tuple[str, ...] = (
    *(f"{MAILBOX_LOCATION_PREFIX}{location}" for location in NARROWING_MAILBOX_LOCATIONS),
    *WIDENING_MAILBOX_OPERATORS,
    *(f"{name.value}:{OPERATOR_FAMILY_VALUES[name.value]}" for name in REGION_DECLARING_OPERATORS),
)

#: The same set in both polarities. Polarity decides *which* region a fragment declares and
#: never whether it declares one, so every sweep over region declarations runs over both.
REGION_DECLARING_FRAGMENTS: tuple[str, ...] = (
    *POSITIVE_REGION_FRAGMENTS,
    *(f"-{fragment}" for fragment in POSITIVE_REGION_FRAGMENTS),
)


#: Every operator of the family beside a bare term, in both polarities. The term is what makes
#: each of these a *probe* rather than a listing, so the sweep exercises the rungs rather than
#: the refusal.
OPERATOR_FAMILY_BODIES: tuple[str, ...] = tuple(
    f"{polarity}{name}:{value} cutover"
    for name, value in OPERATOR_FAMILY_VALUES.items()
    for polarity in ("", "-")
)

#: The text shapes the ladder's rungs turn on, beside the operator family: one word, two
#: words, a qualifying phrase, an identifier, a negated term, a negated phrase.
TEXT_BODIES: tuple[str, ...] = (
    "rollout",
    "rollout cutover",
    "rollout cutover handover",
    f'"{ANCIENT_PHRASE}"',
    f'"{ANCIENT_PHRASE}" cutover',
    f'-"{ANCIENT_PHRASE}" cutover',
    "PO-2026-0041 cutover",
    "rollout -cutover handover",
)


def test_the_operator_family_vocabulary_covers_every_operator_this_parser_knows() -> None:
    """The sweep's population is `OperatorName`, and it is read by name **and** by count.

    Round 12's sweep passed while covering nothing, because its population was a list that
    could be narrowed without failing anything. `OPERATOR_FAMILY_VALUES` is the population of
    every family sweep in this round, so it is held to the enum exactly: an operator added
    without a value here would silently leave the region invariant, the enforcement
    derivation and the end-to-end region audit untested for that operator.
    """
    assert set(OPERATOR_FAMILY_VALUES) == {member.value for member in OperatorName}
    assert len(OPERATOR_FAMILY_BODIES) == 2 * len(OperatorName)


def regions_of_probe(probe: Probe) -> set[str]:
    """Every region this probe's own `q` declares, in comparable form."""
    return {
        carriage_token(token)
        for token in query_tokens(probe.query)
        if declares_the_search_region(token)
    }


def regions_a_probe_added(probe: Probe, wrote: tuple[str, ...]) -> set[str]:
    """The regions a probe declares that the query did not write.

    **This is what identifies A.7 L3's widening step, and it identifies it by what the step
    does.** The round-17 test recognised it by a string prefix - "the `q` begins with the
    widening operator" - which is true of L1's own query when the caller wrote that operator
    themselves, and is true of a probe that widens *and then restricts*. R-RETR-021's defect,
    planted back, left that test green for exactly this reason (R-RETR-031). A probe that
    changed the region is a probe whose region set is not the query's, and that is a question
    about the probe rather than about how its string starts.
    """
    return regions_of_probe(probe) - {carriage_token(fragment) for fragment in wrote}


def test_every_probe_the_ladder_composes_searches_the_region_the_query_named() -> None:
    """**The asymmetry rule, enforced once over the operator family** (OD-5, A9, R-RETR-026).

        A probe composed from a subset of a query's fragments searches the region the query
        named. The fragments it may leave out are exactly the **filters** - the ones that
        constrain messages *within* whatever region is searched - because omitting one can
        only widen the match inside that region. It may not leave out a fragment that
        **declares the region**, in either polarity, because omitting one does not widen
        anything: it moves the probe to a different region. The only rung allowed to change
        the region is the one whose published step is to replace it (AD A.7 L3); it replaces
        it wholesale, it declares the replacement, and it runs only when the query declared no
        region at all.

    **Why the sweep is over the family and not over two operator names.** Round 17 stated the
    asymmetry over three *token classes* and put every negation in the "may be left out"
    class, which is true of `-from:x` and false of a negated location - so a query excluding
    the spam mailbox was answered with the widening operator and `includeSpamTrash=true`
    (R-RETR-026). Enumerating the two location spellings would have been the fourteenth
    instance of that same shape, so the filter half of the sweep is generated from **every
    member of `OperatorName`**, in both polarities.

    **And the region half is generated from the registry, which is round 19's correction**
    (R-RETR-036). It used to be generated from one lexical prefix and a hand-written list of
    the values written under it, so what the sweep actually covered was *a new value under
    `in:`* - and a reviewer registered a new region-selecting operator exactly as an
    implementer would, found it dropped from every unit, relaxed away and widened out of, and
    the whole suite green. The population is now every operator `KIND_BY_OPERATOR` declares
    `OperatorKind.REGION`, written with the value `OPERATOR_FAMILY_VALUES` already requires
    of every member of the lexicon, in both polarities and in the four grouping spellings. An
    operator registered `REGION` tomorrow is swept the day it is registered, with no edit
    here and none to any oracle below.

    Four properties, and the last two are round 18's:

      * every region fragment the query wrote is in the probe's `q`;
      * `include_spam_trash` agrees with the query's own render, on every rung;
      * **the narrowing half** (R-RETR-031): no probe names a region the query did not write.
        The round-17 test asserted only that widening fragments were carried, so a probe that
        *added* `in:inbox` was invariant-clean;
      * **L3's exemption is a positive assertion rather than a `continue`** (R-RETR-031). The
        round-17 branch waved through any L3 probe whose `q` began with the widening operator,
        so R-RETR-021's own defect - a probe that declares a widening and restricts - left it
        green. A widening probe must now carry no other region fragment at all, which is what
        "replaces it wholesale" says.
    """
    regions = ["", *REGION_DECLARING_FRAGMENTS]
    bodies = [*OPERATOR_FAMILY_BODIES, *TEXT_BODIES]

    checked = 0
    swept_operators: set[str] = set()
    for region in regions:
        for body in bodies:
            query = f"{region} {body}".strip()
            parsed_query = parse(query)
            swept_operators |= {operator.name.value for operator in parsed_query.operators}
            wrote = search_region_of(parsed_query.constraints)
            written_regions = {carriage_token(fragment) for fragment in wrote}
            widened_query = widens_beyond_the_default_mailbox(parsed_query.render())
            for rung in LADDER:
                for probe in rung.plan(parsed_query):
                    checked += 1
                    added = regions_a_probe_added(probe, wrote)
                    if added:
                        # A probe that changed the region. Exactly one rung may, exactly one
                        # step of it may, and all four conditions are asserted rather than
                        # waved through: it is L3, it must genuinely widen, it may only run
                        # over a query that declared no region, and "replaces wholesale"
                        # means every region fragment it carries is the widening operator.
                        assert probe.rung is RungId.L3, (query, probe.rung, probe.query)
                        assert probe.include_spam_trash, (query, probe.query)
                        assert not wrote, (query, probe.query)
                        assert all(
                            is_the_widening_mailbox_operator(token)
                            for token in query_tokens(probe.query)
                            if declares_the_search_region(token)
                        ), (query, probe.query)
                        continue
                    for fragment in wrote:
                        assert fragment in probe.query, (query, probe.rung, probe.query)
                    assert probe.include_spam_trash == widened_query, (
                        query,
                        probe.rung,
                        probe.query,
                    )
                    # The narrowing half: a probe may not name a region the query did not.
                    assert regions_of_probe(probe) <= written_regions, (
                        query,
                        probe.rung,
                        probe.query,
                    )

    # Anti-vacuity, four ways. The sweep is not empty; it ranges over the whole ladder as
    # `LADDER` defines it; it really reaches the scoped shapes; and it really covered the
    # operator family rather than the two spellings the finding named.
    assert len(LADDER) == 5
    assert checked > 400, checked
    assert swept_operators == {member.value for member in OperatorName}, swept_operators
    scoped = parse(f"{ANYWHERE_OPERATOR} rollout cutover")
    assert len(DecompositionRung().plan(scoped)) == 2
    assert all(p.include_spam_trash for p in DecompositionRung().plan(scoped))


def test_a_probe_enforces_only_the_constraints_its_own_q_carries_whole() -> None:
    """**`enforced` is one derivation, read by every rung** (OD-5 point 5, R-RETR-028).

    A probe enforces a constraint exactly when its own `q` carries every fragment of it. That
    is a sentence about the string a rung is about to send, so it is answered from the string
    by `constraints_carried_whole` - and this sweep is what makes "a rung added later inherits
    it" true rather than hoped for: a sixth rung that hand-declares an `enforced` list fails
    here the moment it is added to `LADDER`, for every query in the family.

    **The defect.** Round 17 established the rule at L1b and L3 and wrote it into each of them
    separately. L0 kept its own value, so `PO-2026-0041 zephyr` executed one fragment of the
    `terms` constraint, halted the ladder under D.3 rule 1b - which forbids any later rung
    from correcting the claim - and reported `enforced ('terms',)`, `term_coverage 1.0`,
    `sufficiency: sufficient` and a row whose `constraint_coverage` repeated the claim, over a
    message that does not contain "zephyr". The reviewer planted the honest value and all
    2,248 tests stayed green, which is why this test exists at all.

    The two L0 branches are asserted by name as well as by sweep, because they are the shapes
    the finding was reported on and a sweep that happened to miss them would read as covering
    them.
    """
    checked = 0
    for body in (*OPERATOR_FAMILY_BODIES, *TEXT_BODIES):
        for region in ("", ANYWHERE_OPERATOR, f"-{ANYWHERE_OPERATOR}", "in:inbox"):
            parsed_query = parse(f"{region} {body}".strip())
            for rung in LADDER:
                for probe in rung.plan(parsed_query):
                    checked += 1
                    assert probe.enforced == constraints_carried_whole(
                        probe.query, parsed_query.constraints
                    ), (parsed_query.raw, probe.rung, probe.query, probe.enforced)
                    assert not set(probe.enforced) & set(probe.dropped), (
                        parsed_query.raw,
                        probe.rung,
                    )
    assert len(LADDER) == 5
    assert checked > 400, checked

    # Branch E-c: an identifier beside another term is one fragment of `terms`, not `terms`.
    fragmentary = ExactOperatorRung().plan(parse("PO-2026-0041 zephyr"))
    assert [(p.query, p.enforced) for p in fragmentary] == [('"PO-2026-0041"', ())]
    # ... and when the identifier **is** the whole constraint, it is enforced. A.8a branch
    # E-c executes it quoted, which narrows what it matches and never widens it.
    whole = ExactOperatorRung().plan(parse("PO-2026-0041"))
    assert [(p.query, p.enforced) for p in whole] == [('"PO-2026-0041"', (TERMS_CONSTRAINT,))]

    # **An independent oracle, because the sweep above compares one derivation with itself.**
    # `probe.enforced == constraints_carried_whole(...)` is satisfied by *any* consistent
    # derivation, including a broken one: the replant harness planted a `carriage_token` that
    # strips Gmail's grouping punctuation - so a member of L3's `{from:x to:x}` disjunction
    # reads as the `from:x` the caller wrote - and the sweep stayed green. These values are
    # written out rather than computed.
    widened = BroadeningRung().plan(parse("from:ana@team.example zephyr"))
    disjunction = next(p for p in widened if p.query.startswith("{"))
    assert disjunction.enforced == (TERMS_CONSTRAINT,), disjunction
    assert "from" in disjunction.dropped, disjunction
    unwidened = FilteredRung().plan(parse("from:ana@team.example zephyr"))[0]
    assert unwidened.enforced == ("from", TERMS_CONSTRAINT), unwidened

    # Branch E-b: the first of two phrases is one fragment of `phrase`, not `phrase`.
    two_phrases = ExactOperatorRung().plan(parse(f'"{ANCIENT_PHRASE}" "quadrant notice zephyr"'))
    assert [(p.query, p.enforced) for p in two_phrases] == [(f'"{ANCIENT_PHRASE}"', ())]
    one_phrase = ExactOperatorRung().plan(parse(f'"{ANCIENT_PHRASE}"'))
    assert [(p.query, p.enforced) for p in one_phrase] == [(f'"{ANCIENT_PHRASE}"', ("phrase",))]


def test_a_query_that_named_a_region_is_never_widened_out_of_it() -> None:
    """`-in:spam` never searches spam, over the whole location family (OD-5 points 2 and 3).

    The half of R-RETR-026 that a plan-layer invariant cannot state as a membership test:
    L3's published step is *allowed* to change the region, so the invariant above exempts it
    - and the exemption is only sound because the step no longer runs over a query that
    declared a region. This asserts the gate itself, in both polarities, for every location
    spelling, and it asserts the consequence a caller actually experiences: no probe of the
    whole ladder leaves the default mailbox unless the query itself did.

    **The mutation this defends against is R-RETR-026 verbatim.** Deleting the gate in
    `BroadeningRung._anywhere` restores `in:anywhere borogrove` for a query that excluded the
    spam mailbox; deleting the polarity strip in `declares_the_search_region` restores it for
    the negated half alone. Both are replanted in
    `tests/test_replants.py::test_every_behaviour_these_rounds_changed_fails_a_test_when_it_is_removed`.
    """
    for fragment in REGION_DECLARING_FRAGMENTS:
        for body in ("borogrove", "rollout cutover", "from:ana@team.example cutover"):
            parsed_query = parse(f"{fragment} {body}")
            wrote = search_region_of(parsed_query.constraints)
            planned = plan_ladder(parsed_query)
            changed = [probe for probe in planned if regions_a_probe_added(probe, wrote)]
            assert changed == [], (fragment, body, [p.query for p in planned])
            asked_for_spam_trash = widens_beyond_the_default_mailbox(parsed_query.render())
            for probe in planned:
                assert probe.include_spam_trash == asked_for_spam_trash, (
                    fragment,
                    body,
                    probe.rung,
                    probe.query,
                )
                assert fragment in probe.query, (fragment, body, probe.rung, probe.query)


def test_a_broadening_probe_does_not_carry_a_narrower_scope_than_the_one_it_widens_to() -> None:
    """A broadening probe never searches a narrower region than the one it declares.

    **Round 18 closes this by removing the case rather than by fixing the composition**
    (OD-5 point 2, A9-A3). Round 16 conjoined the widening operator with the caller's own
    location and searched the narrower one while declaring it had widened (R-RETR-021); round
    17 replaced the location, which stopped the probe from lying about where it searched but
    left it searching a region the caller had ruled out - declared as a drop, and still the
    spam the caller excluded (R-RETR-026). A.7 L3's step widens the scope of a query that did
    not name one; a query that named one has already answered the question the step exists to
    ask. So a location in the query, in either polarity, means **no whole-mailbox probe at
    all**, and the property this test is named for holds because the shape cannot be built.

    The two things that still have to be true when the step *does* run are asserted here as
    well: it widens (the flag is set) and it carries no region fragment of its own.
    """
    for fragment in REGION_DECLARING_FRAGMENTS:
        narrowed = parse(f"{fragment} is:unread")
        assert BroadeningRung().plan(narrowed) == (), fragment

    # With no region named, the step runs, widens, and carries nothing that narrows it.
    unscoped = parse("is:unread cutover")
    broadened = BroadeningRung().plan(unscoped)
    assert [p.query for p in broadened] == [f"{ANYWHERE_OPERATOR} cutover"]
    assert broadened[0].include_spam_trash is True
    assert "is" in broadened[0].dropped and "is" not in broadened[0].enforced
    assert [
        token
        for token in query_tokens(broadened[0].query)
        if declares_the_search_region(token) and not is_the_widening_mailbox_operator(token)
    ] == []


# --- issue #296: the bug this project exists to fix ----------------------------------------


def test_the_message_that_caused_the_match_is_in_the_response_even_though_it_is_the_oldest() -> (
    None
):
    """Issue #296, asserted directly: the matching message is present, at a named position.

    Gmail's own MCP server returns the right thread while omitting the message that caused
    the match, with no truncation marker and no withheld record. The fixture is that exact
    shape - nine messages, the only match is eight months older than the other eight - and
    the assertions are the three things the bug destroys: the matching message is a row, it
    is named as *matched* with the mechanical reason that admitted it, and the map carries
    every other message of the thread so a reader can see there is nothing behind it.
    """
    box, envelope = answer(f'"the {ANCIENT_PHRASE}"')

    source = next(s for s in envelope.sources if s.thread_id == "t-ancient")
    row = next(r for r in source.messages if r.id == "anc-1")

    assert row.role is Role.MATCHED
    assert isinstance(row.reason, GmailQueryMatch)
    assert row.reason.query == f'"the {ANCIENT_PHRASE}"'
    assert row.reason.rung is RungId.L0
    assert row.depth is Depth.BODY_CLEAN
    assert row.content is not None
    assert ANCIENT_PHRASE in row.content.text

    # the whole thread is carried, so "included == stated_total" is a number rather than a
    # promise, and the response is not partial because nothing is missing from it.
    assert source.stated_total == len(ancient_thread())
    assert source.included == source.stated_total
    assert {r.id for r in source.messages} == {m.id for m in ancient_thread()}
    assert envelope.withheld == ()
    assert envelope.partial is False
    assert envelope.retrieval_report.outcome is Outcome.ANSWERED
    assert box.calls["threads.get"] == 1


def test_the_oldest_message_is_at_position_zero_and_the_positions_are_chronological() -> None:
    """The other half of #296: a present message at a wrong position is still not findable.

    **The array order is asserted too, and that is a round-16 addition rather than a
    flourish.** Round 15 computed a row's position from the same `sorted` that laid the rows
    out, so the two could not disagree and reversing the sort moved both - which is how
    R-RETR's "chronological order reversed" plant was caught, in the test above this one.
    Fixing R-RETR-009 separated them: `position` is now read from the seal, so reversing the
    layout leaves every position correct and only the array wrong. Executed: with the sort
    key negated, that test still passes. A reader who takes `messages[]` in the order it
    arrives would read the thread backwards while every row states the right number, and the
    two halves of one statement disagreeing is worse than either being wrong alone.
    """
    _box, envelope = answer(f'"the {ANCIENT_PHRASE}"')

    source = next(s for s in envelope.sources if s.thread_id == "t-ancient")
    by_position = sorted(source.messages, key=lambda row: row.position)

    assert by_position[0].id == "anc-1"
    assert [row.position for row in by_position] == list(range(len(ancient_thread())))
    # The array a reader iterates is the order the positions state, not a second ordering.
    assert list(source.messages) == by_position


def test_an_exact_message_id_returns_that_message_at_body_depth_on_one_rung() -> None:
    """EV-05's first sentence and LEX-04's cost bar, on the deepest message of a long thread.

    "For a deep message *m* in a long thread: `rfc822msgid:<m>` through MailWeave returns a
    response in which *m* is present at body depth." That is the acceptance clause, executed
    against a fixture; the live-account half is R-GMAIL's and is named as unreachable in the
    round's deliverable. LEX-04's `rungs executed = 1` rides along, because branch E-a is the
    only stop the architecture allows to be unconditional.
    """
    box, envelope = answer("rfc822msgid:<anc-1@mail.invalid>")

    row = next(r for source in envelope.sources for r in source.messages if r.id == "anc-1")
    assert row.depth is Depth.BODY_CLEAN
    assert row.role is Role.MATCHED
    assert row.content is not None and ANCIENT_PHRASE in row.content.text

    assert envelope.retrieval_report.rungs == (RungId.L0,)
    assert envelope.retrieval_report.counters.api_calls <= 3
    assert box.calls["messages.list"] == 1
    # No special case: the id-exact route is the ordinary L0 probe with the ordinary
    # `messages.list`, which is what REG-03's anti-special-casing sweep is about.
    assert box.queries == [("rfc822msgid:<anc-1@mail.invalid>", False)]


def test_a_row_the_date_window_does_not_contain_is_declared_rather_than_passed_off() -> None:
    """EV-05's second sentence, at the width this round can actually establish.

    "a `newer_than:1d`-style recency query returns only messages consistent with the filter,
    or explicitly declares the ones that are not and why". LR - the rung that reconciles
    recency against `history.list` - is WS-12 and does not exist, so what is asserted here is
    the lexical half: for every id the mailbox handed over, if its `internalDate` falls
    outside the declared `window_utc`, the response either withholds it with a reason, or
    discloses it with a `constraint_coverage` that does **not** claim the date constraint.
    Neither branch lets an out-of-window message pass as a match.
    """
    box, envelope = answer("newer_than:60d procurement")
    window = envelope.asked_for.parsed.window_utc
    assert window is not None and "start" in window

    start_ms = int(datetime.fromisoformat(window["start"]).timestamp() * 1000)
    handed_over: set[str] = set()
    for _q, ids in box.returned_ids:
        handed_over |= set(ids)
    outside = {
        message.id
        for message in box.messages
        if message.id in handed_over and message.internal_date_ms < start_ms
    }
    assert outside, "the fixture must contain a message the window excludes"

    withheld = {record.id: record for record in envelope.withheld}
    grouped_threads = {group.thread_id: group for group in envelope.withheld_groups}
    rows = {row.id: row for source in envelope.sources for row in source.messages}
    for message_id in outside:
        if message_id in withheld:
            assert withheld[message_id].why
            assert withheld[message_id].affordance.args
            continue
        if message_id in envelope.withheld_ids:
            # Round 29: withheld inside a thread-granular group; the group carries the why
            # and the call, and the certificate still names the id (`withheld_ids`).
            thread = envelope.disposition.observed_threads[message_id]
            assert thread in grouped_threads and grouped_threads[thread].affordance.args
            continue
        assert "newer_than" not in rows[message_id].constraint_coverage


def test_every_matched_row_names_the_constraints_its_admitting_query_enforced() -> None:
    """LEX-02's last clause: `constraint_coverage` on every disclosed message, from the probe.

    Derived from the `q` that admitted the id rather than from anything believed about the
    message, and filtered to constraints the parse produced - so a row cannot name a
    constraint the user did not write, and cannot claim one its admitting query did not
    carry.

    **The rule is asserted, not the shape of one answer.** A row's coverage is checked
    against the probe that admitted it, fragment by fragment: it names a constraint exactly
    when the admitting `q` carried every fragment of that constraint. That is what makes the
    empty case a *result* rather than a hole - a decomposition probe carrying one term of a
    two-term `terms` constraint enforces no constraint whole, so its rows carry no coverage
    and their `reason` carries the `q` instead. An earlier version of this test asserted
    "every matched row has non-empty coverage", which is a statement about the corpus that
    happened to hold, and would have been satisfied by naming `terms` for a message that
    matched half of it (R-RETR-008's fix, and the overclaim it must not introduce).
    """
    seen_matched = 0
    seen_covered = 0
    seen_uncovered = 0
    for name, query in CORPUS.items():
        parsed = parse(query)
        names = set(parsed.constraint_names)
        _box, client, ledger, run = drive(query)
        envelope = assemble(run, client=client, ledger=ledger)

        for source in envelope.sources:
            for row in source.messages:
                if row.role is not Role.MATCHED:
                    # A thread-context row makes no claim about the query, so it makes none.
                    assert row.constraint_coverage == (), (name, row.id)
                    continue
                seen_matched += 1
                assert set(row.constraint_coverage) <= names, (name, row.id)

                admitting = ledger.origins[row.id].query
                assert admitting is not None, (name, row.id)
                carried_whole = {
                    constraint.name
                    for constraint in parsed.constraints
                    if all(fragment in admitting for fragment in constraint.fragments)
                }
                assert set(row.constraint_coverage) <= carried_whole, (
                    name,
                    row.id,
                    admitting,
                )
                if row.constraint_coverage:
                    seen_covered += 1
                else:
                    seen_uncovered += 1
                    # The mechanical account is still there: the q that admitted it.
                    assert isinstance(row.reason, GmailQueryMatch), (name, row.id)
                    assert row.reason.query == admitting, (name, row.id)

    # Asserted over the corpus rather than per query - and both branches asserted, so this
    # cannot pass by covering only the shape that was easy.
    assert seen_matched > 0
    assert seen_covered > 0
    assert seen_uncovered > 0, (
        "no corpus query produced a row admitted by a *piece* of a constraint, so the "
        "branch R-RETR-008's fix introduced is untested by this sweep"
    )


def test_a_decomposition_probe_is_not_reported_as_a_dropped_constraint() -> None:
    """L1b splits the query; it does not abandon any part of it (`Probe.relaxes`).

    `newer_than:60d procurement` matches at L1 with both constraints enforced. L1b still runs
    - L1's eleven hits are past D.3 rule 2's stop - and its per-constraint probes admit three
    further messages that satisfy only the terms. Reading those probes as drops named
    `newer_than` in `asked_for.dropped` and reported `term_coverage` at 0.5 for a query
    nothing had been dropped from. The per-row `constraint_coverage` is where that partial
    satisfaction belongs, and it is still there.
    """
    _box, envelope = answer("newer_than:60d procurement")

    assert envelope.asked_for.dropped == ()
    assert envelope.asked_for.term_coverage == 1.0
    assert envelope.asked_for.constraint_drop_depth == 0

    coverages = {
        row.id: set(row.constraint_coverage)
        for source in envelope.sources
        for row in source.messages
        if row.role is Role.MATCHED
    }
    assert {"newer_than", "terms"} in coverages.values()
    assert any(cover == {"terms"} for cover in coverages.values())


def test_no_id_the_ladder_observed_leaves_the_response_without_a_disposition() -> None:
    """I-1, over every query in the corpus at once, from the fixture's side of the wire.

    `H == disclosed union withheld` is enforced inside `Envelope`, so a test that only built
    an envelope would be asserting that the seal ran. This asserts the *content* of the two
    sets against the mailbox's own record of which ids it handed over - a witness standing
    outside the process, which is what amendment A1 asks for and what the seal alone cannot
    be.
    """
    for name, query in CORPUS.items():
        box, envelope = answer(query)

        handed_over: set[str] = set()
        for _q, ids in box.returned_ids:
            handed_over |= set(ids)

        disclosed = envelope.disclosed_ids
        # Round 29: `withheld_ids` is every withheld id, named one by one or standing inside
        # a counted group - the invariant is over ids and did not narrow when the wire did.
        withheld = envelope.withheld_ids
        assert handed_over <= disclosed | withheld, name
        assert not (disclosed & withheld), name
        for record in envelope.withheld:
            assert record.affordance.mentions(record.id, record.thread_id), name
        for group in envelope.withheld_groups:
            assert group.affordance.args.get("thread_id") == group.thread_id, name


@dataclass
class OmittingMailbox(SyntheticMailbox):
    """A mailbox whose `threads.get` drops one message its own `messages.list` returned."""

    omit: str = "anc-1"

    def thread(self, thread_id: str) -> tuple[Msg, ...]:
        return tuple(m for m in super().thread(thread_id) if m.id != self.omit)


def test_a_thread_map_that_omits_one_of_its_own_hits_is_withheld_rather_than_shipped() -> None:
    """The #296 signature arriving **from Gmail**, and A.7a's own answer to it.

    `messages.list` returns `anc-1` for the phrase; `threads.get("t-ancient")` comes back
    without it. That is the source disagreeing with itself, and MailWeave must not repeat
    it. It does not - and it no longer refuses the whole response either (R-RETR-010): the
    thread is not made a `Source`, every id observed in it becomes a `partial_source_failure`
    withheld record with a `mailweave_get_messages` affordance, and the disagreement is named
    in a `not_included_sources` entry.

    What remains genuinely inexpressible is **one number**: a `Source` for this thread would
    have to state `stated_total` as exactly what the observation stated (amendment A6) *and*
    at least the distinct ids observed in it, and nine-and-at-least-ten has no solution. A
    `NotIncludedSource` states no total instead, which is what `stated_total: None` is for.
    Amendment A8's claim that A.7a's answer as a whole was "not expressible in the shipped
    schema" was wider than that, and its text has been corrected.
    """
    box = OmittingMailbox(messages=mailbox().messages, now_ms=epoch_ms(2026, 9, 3))
    client = make_client(box)
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run(f'"the {ANCIENT_PHRASE}"', now=NOW, zone=UTC_ZONE)

    assert ledger.hit_ids == {"anc-1"}
    envelope = assemble(run, client=client, ledger=ledger)

    assert [source.thread_id for source in envelope.sources] == []
    withheld = {record.id: record for record in envelope.withheld}
    assert "anc-1" in withheld
    assert {record.cap for record in envelope.withheld} == {WithheldCap.PARTIAL_SOURCE_FAILURE}
    # **Round 29 moved the sentence and kept the fact.** The explanation used to sit on every
    # record for the thread - a list of ids, copied once per id, unbounded. It is now stated
    # once on the thread's `not_included_sources[]` block, in the caller's terms (the issue
    # number is a reviewer's reference and lives in `assemble.py` beside the sentence), and
    # each record refers the reader to it by thread.
    for record in envelope.withheld:
        assert "not_included_sources" in record.why and "t-ancient" in record.why
        assert record.affordance.mentions(record.id, record.thread_id)

    split_off = {entry.thread_id: entry for entry in envelope.not_included_entries}
    assert "t-ancient" in split_off
    assert split_off["t-ancient"].stated_total is None
    reasons = {
        source.thread_id: block.why
        for block in envelope.not_included_sources
        for source in block.sources
    }
    assert "without 1 of its matching message(s)" in reasons["t-ancient"], reasons
    assert envelope.partial is True
    assert envelope.retrieval_report.outcome is not Outcome.ANSWERED


def test_one_self_disagreeing_thread_does_not_deny_the_other_five() -> None:
    """R-RETR-010's blast radius: the cost of the old refusal, measured.

    Five threads retrieved correctly plus one thread that disagrees with itself used to
    produce **no envelope at all**. A8 recorded that as "safe"; it is safe about the one
    thread and unsafe about every other query the mailbox can answer. A source that cannot
    describe itself is one thread's disposition, not the response's.
    """
    healthy = tuple(
        Msg(
            id=f"hlt-{index}",
            thread_id=f"t-healthy-{index}",
            sender="ana@team.example",
            subject="Statement",
            body="Procurement statement for the record.",
            internal_date_ms=epoch_ms(2026, 5, index),
            to=("bo@team.example",),
        )
        for index in range(1, 6)
    )
    disagreeing = (
        Msg(
            id="bad-1",
            thread_id="t-bad",
            sender="cy@team.example",
            subject="Statement",
            body="Procurement statement for the record.",
            internal_date_ms=epoch_ms(2026, 5, 9),
            to=("bo@team.example",),
        ),
        Msg(
            id="bad-2",
            thread_id="t-bad",
            sender="bo@team.example",
            subject="Re: Statement",
            body="Acknowledged with no changes.",
            internal_date_ms=epoch_ms(2026, 5, 10),
            to=("cy@team.example",),
        ),
    )
    box = OmittingMailbox(
        messages=(*healthy, *disagreeing), now_ms=epoch_ms(2026, 9, 3), omit="bad-1"
    )
    _box, client, ledger, run = drive("procurement", box=box)
    envelope = assemble(run, client=client, ledger=ledger)

    assert {source.thread_id for source in envelope.sources} == {
        f"t-healthy-{index}" for index in range(1, 6)
    }
    assert {record.id for record in envelope.withheld} == {"bad-1", "bad-2"}
    assert [entry.thread_id for entry in envelope.not_included_entries] == ["t-bad"]
    assert envelope.partial is True


def test_a_thread_whose_order_cannot_be_derived_is_not_placed_in_an_invented_one() -> None:
    """R-RETR-009: the order the seal deliberately refused to invent, not invented here.

    `_thread_scalars` omits the position map for a whole thread when any message row carries
    no `internalDate` - PF-2's suspected `format=metadata` shape - and records why, "because
    inventing them would be the failure this project exists to prevent". Round 15's assembly
    then computed positions from its own sort key, which with every date missing degenerates
    to **alphabetical order by message id**, and presented the result as amendment A3's
    0-based index into chronological order: on this fixture the matched, chronologically
    first message was reported at position 1 of 2.

    A position is a claim, so a thread MailWeave cannot place is withheld with the reason
    the observation gave, rather than disclosed in an order nobody derived. The contrasting
    run is asserted on the same fixture, so what changed is the flag and not the mailbox.
    """
    messages = (
        Msg(
            id="m-zulu",
            thread_id="t-order",
            sender="ana@team.example",
            subject="Vendor",
            body="First in time, last in the alphabet. Procurement.",
            internal_date_ms=epoch_ms(2026, 1, 5),
            to=("bo@team.example",),
        ),
        Msg(
            id="m-alpha",
            thread_id="t-order",
            sender="bo@team.example",
            subject="Re: Vendor",
            body="Second in time, first in the alphabet.",
            internal_date_ms=epoch_ms(2026, 6, 5),
            to=("ana@team.example",),
        ),
    )

    dated = SyntheticMailbox(messages=messages, now_ms=epoch_ms(2026, 9, 3))
    _box, client, ledger, run = drive("procurement", box=dated)
    envelope = assemble(run, client=client, ledger=ledger)
    source = next(s for s in envelope.sources if s.thread_id == "t-order")
    assert [(row.id, row.position) for row in source.messages] == [("m-zulu", 0), ("m-alpha", 1)]

    undated = SyntheticMailbox(
        messages=messages, now_ms=epoch_ms(2026, 9, 3), metadata_returns_internal_date=False
    )
    _box2, client2, ledger2, run2 = drive("procurement", box=undated)
    envelope2 = assemble(run2, client=client2, ledger=ledger2)

    assert envelope2.sources == ()
    assert {record.id for record in envelope2.withheld} == {"m-zulu", "m-alpha"}
    assert {record.cap for record in envelope2.withheld} == {WithheldCap.PARTIAL_SOURCE_FAILURE}
    for record in envelope2.withheld:
        assert "not_included_sources" in record.why and "t-order" in record.why
        assert record.affordance.mentions(record.id, record.thread_id)
    split_off = {entry.thread_id: entry for entry in envelope2.not_included_entries}
    assert split_off["t-order"].stated_total == 2
    reasons = {
        source.thread_id: block.why
        for block in envelope2.not_included_sources
        for source in block.sources
    }
    assert "chronological position" in reasons["t-order"], reasons
    assert envelope2.partial is True


# --- L1b: the rung the originating bug's shape needs ----------------------------------------


def test_gmail_cannot_match_a_constraint_spread_across_two_messages_of_one_thread() -> None:
    """RO F2, executed against the double before L1b is credited with recovering from it.

    The double implements Gmail's message-scoped conjunction and refuses an operator it does
    not evaluate, so this is a statement about the fixture's fidelity rather than about the
    ladder. Without it, L1b's recovery could be an artefact of a generous double.
    """
    box = mailbox()
    assert box.search("from:dev@team.example cutover", include_spam_trash=False) == ()
    assert {m.id for m in box.search("from:dev@team.example", include_spam_trash=False)} == {
        "spl-1"
    }
    assert {m.id for m in box.search("cutover", include_spam_trash=False)} == {"spl-2"}


def test_l1b_recovers_a_thread_whose_constraints_live_in_different_messages() -> None:
    """The cross-message-constraint case of the plan's acceptance column (PF-9's shape).

    L1 matches nothing, because there is no single message carrying both constraints. L1b
    sends one `messages.list` per constraint, intersects on `threadId`, and the thread comes
    back - with both of the messages that jointly satisfy the query present as rows.
    """
    _box, client, ledger, run = drive("from:dev@team.example cutover")

    l1 = next(e for e in run.executions if e.rung is RungId.L1)
    assert l1.skipped is None
    assert sum(entry.ids_returned for entry in l1.executed) == 0

    assert run.decomposition is not None
    assert run.decomposition.intersection == {"t-split"}
    assert set(run.decomposition.threads_by_constraint) == {"from", "terms"}
    assert run.decomposition.union >= {"t-split"}

    envelope = assemble(run, client=client, ledger=ledger)
    rows = rows_of(envelope, "t-split")
    assert {"spl-1", "spl-2"} <= set(rows)
    assert rows["spl-1"] is Role.MATCHED
    assert rows["spl-2"] is Role.MATCHED
    assert envelope.retrieval_report.outcome is Outcome.ANSWERED
    assert RungId.L1B in envelope.retrieval_report.rungs


def test_two_bare_words_in_two_messages_of_one_thread_are_recovered() -> None:
    """R-RETR-008: the founding bug's **commonest** shape, which had no rung at all.

    `"rollout pencilled"` is what a user types. Both words are residual free text, so the
    parse produces one `terms` constraint - and one constraint is not two, so L1b's plan was
    empty, the rung was reported `not_applicable`, and the thread whose two messages carry
    one word each was findable by nothing. L1 cannot match it: Gmail's `q` is message-scoped
    (RO F2), asserted below rather than assumed.

    The fix is in the constraint model, not in this rung: `terms` is still **one** relaxation
    unit and is now **two** decomposition units.
    """
    box = mailbox()
    assert box.search("rollout pencilled", include_spam_trash=False) == ()

    _box, client, ledger, run = drive("rollout pencilled")

    assert [c.name for c in run.parsed.constraints] == ["terms"]
    l1 = next(e for e in run.executions if e.rung is RungId.L1)
    assert sum(entry.ids_returned for entry in l1.executed) == 0

    assert RungId.L1B in run.rungs_run
    assert run.decomposition is not None
    assert run.decomposition.intersection == {"t-terms"}
    assert set(run.decomposition.threads_by_constraint) == {
        "terms[rollout]",
        "terms[pencilled]",
    }

    envelope = assemble(run, client=client, ledger=ledger)
    rows = rows_of(envelope, "t-terms")
    assert rows == {"trm-1": Role.MATCHED, "trm-2": Role.MATCHED}
    assert envelope.retrieval_report.outcome is Outcome.ANSWERED


def test_decomposition_splits_every_constraint_kind_whose_fragments_bind_separately() -> None:
    """The fix is at the constraint model, so it is asserted there rather than on `terms`.

    A fix that worked for two words and not for three, or for words and not for a repeated
    operator, would be the eleventh instance of "one shape validated, peers trusted". The
    rule is one sentence - one unit per fragment, unless the kind binds its fragments to one
    message - and this executes it across the kinds a query can actually produce.
    """
    three_words = parse("rollout pencilled handover")
    assert [c.name for c in three_words.constraints] == ["terms"]
    assert [u.label for u in three_words.decomposition_units] == [
        "terms[rollout]",
        "terms[pencilled]",
        "terms[handover]",
    ]

    repeated_operator = parse("from:ana@team.example from:bo@team.example")
    assert [c.name for c in repeated_operator.constraints] == ["from"]
    assert [u.fragment for u in repeated_operator.decomposition_units] == [
        "from:ana@team.example",
        "from:bo@team.example",
    ]
    assert len(DecompositionRung().plan(repeated_operator)) == 2

    two_phrases = parse('"a phrase never written" "another phrase never written"')
    assert [c.name for c in two_phrases.constraints] == ["phrase"]
    assert len(two_phrases.decomposition_units) == 2

    # ...and the kind that must NOT split, because its fragments bind one message jointly:
    # a thread with a message after the start and another before the end holds no message
    # inside the window, so intersecting the halves would name threads nothing satisfies.
    #
    # Asserted over the **parse**, not per constraint. A written-out window is two
    # constraints of one fragment each, so "each date constraint is one unit" was true and
    # let the halves be intersected anyway - the peer this round's own fix for R-RETR-008
    # first missed. `test_a_date_window_is_one_unit_whether_it_is_written_out_or_derived`
    # carries the reasoning; here is what it costs the rung.
    window = parse("rollout after:2026/05/01 before:2026/06/01")
    assert [c.kind for c in window.constraints].count(OperatorKind.DATE.value) == 2
    assert [u.label for u in window.decomposition_units] == ["after+before", "terms"]
    assert [p.query for p in DecompositionRung().plan(window)] == [
        "after:2026/05/01 before:2026/06/01",
        "rollout",
    ]


def test_l1b_probes_are_one_per_constraint_and_capped_by_the_cost_row() -> None:
    """A.7's L1b row is `<=3 x 5 u`, so the cap is three probes, one per constraint."""
    few = DecompositionRung().plan(parse("from:dev@team.example cutover"))
    assert [probe.enforced for probe in few] == [("from",), ("terms",)]

    many = DecompositionRung().plan(
        parse("from:dev@team.example to:ops@team.example subject:kickoff cutover")
    )
    assert len(many) == MAX_DECOMPOSITION_PROBES
    assert len({probe.query for probe in many}) == MAX_DECOMPOSITION_PROBES


def test_l1b_does_not_run_for_a_query_with_nothing_to_decompose() -> None:
    """One **unit** cannot be spread across two messages, so the rung does not apply.

    One constraint is no longer the test - `"rollout pencilled"` is one constraint and two
    units - but a single content word still is, and `not_applicable` is true of it.
    """
    assert DecompositionRung().plan(parse("procurement")) == ()
    assert len(parse("procurement").decomposition_units) == 1
    _box, _client, _ledger, run = drive("procurement")
    assert RungId.L1B in run.rungs_skipped


def test_the_l1_stop_does_not_switch_off_the_rung_that_feeds_l1() -> None:
    """R-RETR-007: two unrelated hits used to hide the thread the project exists to find.

    `from:dev@team.example cutover` against a mailbox holding the split thread **and** two
    single-message threads that satisfy both constraints alone. L1 returns those two, D.3
    rule 2's stop fired on them, and `run_parsed`'s short-circuit skipped L1b - which had a
    non-empty plan and is the only rung that can see `t-split` - then reported it
    `not_applicable`, which in OD-2's vocabulary is the claim that it could not have helped.
    The response said `answered` / `sufficient` with the answer missing.

    A.7's table gives L1b's Stop/escalate column as "feeds L1", so a stop at L1 halts the
    ladder *after* L1b.

    **The stop must actually fire, and asserting that is the whole test.** Two things were
    changed for this finding - the fourth conjunct, and where the stop halts - and a fixture
    without an answer-type cue exercises only the first: `present is None` blocks the stop,
    L1b runs because nothing stopped the ladder, and the assertion below passes without the
    `halts_after` half existing at all. Reverting `halts_after` to `L1` was a planted defect
    this test did not catch until `run.stop_rule` was asserted, which is "a claim wider than
    the code" arriving inside a test rather than a docstring. So the noise carries a
    date-like token and the query carries the cue, and `stop_rule == "D.3-2"` is asserted
    before anything else.
    """
    noise = tuple(
        Msg(
            id=f"noi-{index}",
            thread_id=f"t-noise-{index}",
            sender="dev@team.example",
            subject="Status",
            body=f"Cutover note {index} landed on 2026/04/0{index} for another programme.",
            internal_date_ms=epoch_ms(2026, 4, index),
            to=("qa@team.example",),
        )
        for index in (1, 2)
    )
    box = SyntheticMailbox(messages=(*split_thread(), *noise), now_ms=epoch_ms(2026, 9, 3))
    _box, client, ledger, run = drive("when was the cutover from:dev@team.example", box=box)

    l1 = next(e for e in run.executions if e.rung is RungId.L1)
    assert sum(entry.ids_returned for entry in l1.executed) == 2, "the noise must match at L1"
    # D.3 rule 2 fires on the two unrelated hits - which is the finding's own precondition,
    # not an incidental detail - and the ladder halts after L1b rather than after L1.
    assert run.answer_type.present is True
    assert run.stop_rule == "D.3-2"
    assert run.stopped_after is RungId.L1
    assert RungId.L1B in run.rungs_run
    assert {RungId.L2, RungId.L3} <= set(run.rungs_skipped)

    envelope = assemble(run, client=client, ledger=ledger)
    assert {"spl-1", "spl-2"} <= set(rows_of(envelope, "t-split"))

    # ...and the shape R-RETR reported verbatim, where the stop does not fire because the
    # query carries no cue. Same mailbox, same evidence: whether the thread is found must
    # not turn on the query's grammar, which is what it used to do.
    _box2, client2, ledger2, uncued = drive("from:dev@team.example cutover", box=box)
    assert uncued.stop_rule is None
    assert RungId.L1B in uncued.rungs_run
    assert {"spl-1", "spl-2"} <= set(
        rows_of(assemble(uncued, client=client2, ledger=ledger2), "t-split")
    )


def test_d3_rule_2_uses_the_fourth_conjunct_the_architecture_writes() -> None:
    """The conjunct is `answer_type_presence`; it was `present is not False` (R-RETR-007).

    D.3 rule **1b** carries the "or the query carries no answer-type cue" escape and rule 2
    does not, and the tri-state makes that load-bearing rather than pedantic: `present is
    None` is every ordinary non-interrogative query, so the escape fired the stop on almost
    all of them. Both directions are asserted, on one mailbox, so the difference is the
    predicate and not the fixture.
    """

    def run_for(query: str) -> LadderRun:
        box = SyntheticMailbox(messages=stop_thread(), now_ms=epoch_ms(2026, 9, 3))
        _box, _client, _ledger, run = drive(query, box=box)
        return run

    # A cue whose token class is present in the hit: `present is True`, the stop fires.
    cued = run_for("when was the vendor decision from:dev@team.example")
    assert cued.answer_type is not None
    assert cued.answer_type.answer_type is AnswerType.DATE_LIKE
    assert cued.answer_type.present is True
    assert cued.stop_rule == "D.3-2"

    # No cue at all: `present is None`, which is a third state and not a true one.
    uncued = run_for("vendor decision from:dev@team.example")
    assert uncued.answer_type.present is None
    assert uncued.stop_rule is None


def test_a_stop_at_l1_still_halts_the_rungs_that_escalate_from_it() -> None:
    """The other half of "feeds L1": a stop is still a stop for L2 and L3.

    Widening the L1b exemption into "the stop stops nothing" would be the inverse defect.

    **What this test does and does not establish, because the difference was measured.**
    Planting `halted = False` - the stop halting nothing at all - leaves this test green, so
    the assertion below is not what holds L2 and L3 back here. `_should_run` is: it gates
    them on `evidence_count == 0`, and every D.3 stop needs hits to fire, so a stop and an
    evidence count above zero always arrive together. The two guards are genuinely redundant
    **for L2 and L3**, and this test pins the observable behaviour rather than the mechanism.

    The mechanism is load-bearing for exactly one rung - **L1b**, which `_should_run` lets
    run unconditionally, so only the stop can hold it - and the same plant is caught there,
    by `test_an_exact_signal_stop_at_l0_halts_every_later_rung_including_l1b`. That is where
    "the exemption is read from the rung order rather than from a flag a later rung could
    set for itself" is executed; it is written here because a reader of this test would
    otherwise take its name for that evidence, which is the claim-wider-than-the-code
    pattern arriving inside a test.
    """
    box = SyntheticMailbox(messages=stop_thread(), now_ms=epoch_ms(2026, 9, 3))
    _box, _client, _ledger, run = drive(
        "when was the vendor decision from:dev@team.example", box=box
    )

    assert run.stop_rule == "D.3-2"
    assert run.stopped_after is RungId.L1
    assert RungId.L1B in run.rungs_run
    assert {RungId.L2, RungId.L3} <= set(run.rungs_skipped)
    # The redundancy above, asserted rather than assumed: if a later round gates L1b on
    # evidence, or ungates L2 and L3, this stops being true and the reader is told here.
    assert run.evidence_count > 0


def test_an_exact_signal_stop_at_l0_halts_every_later_rung_including_l1b() -> None:
    """D.3 rule 1's own sentence: "no structural, semantic or ranking rung may run".

    L1b feeds L1; it does not feed L0's identity resolution. LEX-04's `rungs executed = 1`
    is the number this protects, and it is the one an over-wide reading of R-RETR-007's fix
    would have cost.
    """
    _box, _client, _ledger, run = drive(f'"the {ANCIENT_PHRASE}"')

    assert run.stop_rule == "D.3-1b"
    assert run.rungs_run == (RungId.L0,)
    assert RungId.L1B in run.rungs_skipped


def test_l1b_can_only_under_name_a_thread_whose_messages_are_already_in_H() -> None:
    """The bound `Decomposition`'s docstring claims, executed on the case that reaches it.

    A decomposition probe reports the ids it was the **first** to admit into `H`, because the
    transport hands back counts rather than ids. So a thread drops out of the intersection
    exactly when one probe's whole contribution to it was already recorded by an earlier one -
    which means a single message satisfied both constraints. The claim is that this costs
    precision about which rung gets the credit and cannot cost a message.

    `from:bulkops@team.example roster` is that case: L1 matches all six messages of
    `t-dense` by itself and admits them, so **both** decomposition probes contribute nothing
    new, the intersection is empty - and all six are in `H`, disclosed, and rows of the
    response.
    """
    box, client, ledger, run = drive("from:bulkops@team.example roster")

    dense = {message.id for message in dense_thread()}
    l1b = next(e for e in run.executions if e.rung is RungId.L1B)
    assert l1b.skipped is None, "the bound is only reachable when L1b actually runs"
    assert [entry.ids_returned for entry in l1b.executed] == [len(dense), len(dense)]
    assert l1b.ids_admitted == frozenset(), "both probes were beaten to every id by L1"

    assert run.decomposition is not None
    assert run.decomposition.intersection == frozenset()
    assert run.decomposition.union == frozenset()
    assert dense <= ledger.hit_ids

    envelope = assemble(run, client=client, ledger=ledger)
    assert dense <= envelope.disclosed_ids
    assert envelope.withheld == ()
    assert box.calls["threads.get"] == 1


# --- L2: relaxation, enumerable before it is sent -------------------------------------------


def test_a_relaxation_that_would_leave_nothing_to_select_by_is_untried_not_sent() -> None:
    """L2's own sentence, applied to the shape it did not test for.

    The rung already declines a drop whose remaining constraints render an **empty** `q`,
    "because a listing with no query asks Gmail for the whole mailbox rather than for a
    relaxation of this one". Dropping `from` out of `from:ana@team.example -cutover` leaves
    `-cutover`, which is not empty and is not a relaxation either: it is the same mailbox
    listing minus a few messages. Same sentence, one shape further out - the peer that a
    check written as `if not rendered.strip()` cannot see.

    The drop is **untried**, not absent: `untried_drops` reads what was probed rather than
    what was planned, so `empty_diagnosis` still names it and ROUTE-04's third state holds.
    """
    parsed = parse("from:ana@team.example -cutover")
    assert [c.name for c in parsed.constraints] == ["from", "terms"]
    # Dropping `terms` leaves a real probe; dropping `from` would leave only an exclusion.
    assert [p.query for p in RelaxationRung().plan(parsed)] == ["from:ana@team.example"]
    assert RelaxationRung().drop_order(parsed) == ("from", "terms")
    assert RelaxationRung().untried_drops(parsed, probed={"terms"}) == ("from",)


def test_a_truncated_decomposition_page_drops_a_thread_the_bound_does_not_cover() -> None:
    """R-RETR-013: the precondition the documented L1b bound left out, executed.

    The bound is "a thread drops out of the intersection only when one message satisfied
    both parts, and those ids are in `H` already". It holds given complete pages, and
    `max_pages_per_query = 1` is precisely the case where a page is not complete: a probe
    matching more than `page_size` messages never observes the rest, so a thread behind the
    page drops out with **no** message satisfying both parts and with its ids not in `H` at
    all.

    The test asserts the loss rather than a fix. The page budget is A.7's decision and not
    this round's, and the response declares the truncation in `scan_scope` - which is what
    the outcome assertion below is about (R-RETR-016).
    """
    bulk = tuple(
        Msg(
            id=f"pag-{index:03d}",
            thread_id=f"t-pag-{index:03d}",
            sender="ana@team.example",
            subject="Notice",
            body="Rollout notice, pencilled for the record.",
            internal_date_ms=epoch_ms(2026, 1, 1) + index * 1000,
            to=("bo@team.example",),
        )
        for index in range(1, DEFAULT_PAGE_SIZE + 20)
    )
    # Both decomposition probes are truncated, and the answering thread sorts behind the
    # first page of each - so neither of its messages is observed by either probe.
    answering = (
        Msg(
            id="zz-1",
            thread_id="t-answer",
            sender="ana@team.example",
            subject="Programme",
            body="Rollout is the subject of this one.",
            internal_date_ms=epoch_ms(2026, 8, 1),
            to=("bo@team.example",),
        ),
        Msg(
            id="zz-2",
            thread_id="t-answer",
            sender="bo@team.example",
            subject="Re: Programme",
            body="Pencilled for the second week.",
            internal_date_ms=epoch_ms(2026, 8, 2),
            to=("ana@team.example",),
        ),
    )
    box = SyntheticMailbox(messages=(*bulk, *answering), now_ms=epoch_ms(2026, 9, 3))
    _box, client, ledger, run = drive("rollout pencilled", box=box)

    rollout_probe = next(
        entry
        for entry in run.executed_probes
        if entry.probe.rung is RungId.L1B and entry.probe.query == "rollout"
    )
    assert rollout_probe.more_pages is True
    assert "zz-1" not in ledger.hit_ids

    assert run.decomposition is not None
    assert "t-answer" not in run.decomposition.intersection

    envelope = assemble(run, client=client, ledger=ledger)
    # Not disclosed, not withheld - the ids were never observed, so there is nothing for the
    # disposition ledger to account for. What the response *does* say is that pages remain.
    assert "zz-1" not in envelope.disclosed_ids | {r.id for r in envelope.withheld}
    assert any(entry.more_pages for entry in envelope.retrieval_report.scan_scope)
    assert envelope.retrieval_report.outcome is Outcome.INCONCLUSIVE
    assert envelope.partial is True


def test_a_run_that_declares_pages_remaining_does_not_also_report_answered() -> None:
    """R-RETR-016: `answered` is a claim, and `scan_scope` had already refuted it.

    A run whose probes report `more_pages` has said in its own scan scope that pages it did
    not fetch may hold the answer. Reporting `answered` beside that is the response
    contradicting its own declaration - and it happened on a run where the answering thread
    was never observed at all. WS-10 owns `outcome` policy in full; this is the narrow case
    where the field is emitted this round.
    """
    crowd = tuple(
        Msg(
            id=f"crw-{index:03d}",
            thread_id=f"t-crw-{index:03d}",
            sender="ana@team.example",
            subject="Notice",
            body="Procurement notice for the record.",
            internal_date_ms=epoch_ms(2026, 1, 1) + index * 1000,
            to=("bo@team.example",),
        )
        for index in range(1, DEFAULT_PAGE_SIZE + 20)
    )
    box = SyntheticMailbox(messages=crowd, now_ms=epoch_ms(2026, 9, 3))
    _box, client, ledger, run = drive("procurement", box=box)
    envelope = assemble(run, client=client, ledger=ledger)

    assert any(entry.more_pages for entry in run.executed_probes)
    assert envelope.disclosed_ids, "rows are still disclosed; only the claim changes"
    assert envelope.retrieval_report.outcome is Outcome.INCONCLUSIVE


def test_every_probe_l2_would_send_is_listable_before_any_of_them_is_sent() -> None:
    """ROUTE-03's enumerability, asserted as an equality rather than as a containment.

    The point is not that the executed probes were *among* the planned ones - a rung that
    planned the whole mailbox and sent one probe would satisfy that. It is that the published
    plan and the executed sequence are the same list, in the same order, with the constraint
    each step dropped named on it.
    """
    query = 'from:nobody@team.example "a phrase never written"'
    parsed = parse(query)
    planned = RelaxationRung().plan(parsed)

    assert [probe.dropped for probe in planned] == [("from",), ("phrase",)]
    assert [probe.query for probe in planned] == [
        '"a phrase never written"',
        "from:nobody@team.example",
    ]

    _box, _client, _ledger, run = drive(query)
    execution = next(e for e in run.executions if e.rung is RungId.L2)

    assert execution.skipped is None
    assert [e.probe for e in execution.executed] == list(planned)
    assert [(step.dropped, step.q) for step in run.relaxation] == [
        (probe.dropped[0], probe.query) for probe in planned
    ]


def test_relaxation_drops_exactly_one_constraint_per_probe() -> None:
    """ "Drop ONE constraint per step" (A.7 L2). A probe that dropped two is not a diagnosis."""
    parsed = parse('from:dev@team.example subject:kickoff cutover "a phrase never written"')
    names = set(parsed.constraint_names)

    for probe in RelaxationRung().plan(parsed):
        assert len(probe.dropped) == 1
        assert set(probe.enforced) == names - set(probe.dropped)


def test_the_relax_probe_budget_binds_at_min_k_six_and_names_what_it_did_not_reach() -> None:
    """`max_relax_probes = min(k, 6)` (ADV-105), with the untried drops reported not absorbed.

    Nine constraints, **none of which declares the region**, so what this measures is the
    budget. It used to write `label:vendors` among them, and since round 19 a label declares
    the region and its drop is refused at any budget - so the count would have measured the
    refusal instead. That refusal has its own test, beside the rule that produces it
    (`test_a_refused_region_drop_is_reported_untried_and_costs_no_probe`).
    """
    parsed = parse(
        "from:a@team.example to:b@team.example cc:c@team.example subject:kickoff "
        'after:2026/01/01 is:unread has:attachment "three word phrase" widget'
    )
    rung = RelaxationRung()
    planned = rung.plan(parsed)

    assert len(parsed.constraints) == 9
    assert len(planned) == max_relax_probes(len(parsed.constraints)) == 6
    probed = {probe.dropped[0] for probe in planned}
    untried = rung.untried_drops(parsed, probed=probed)
    assert set(untried) | probed == set(parsed.constraint_names)
    assert not set(untried) & probed
    assert set(rung.drop_order(parsed)) == set(parsed.constraint_names)


def test_a_drop_no_probe_reached_is_untried_even_when_the_budget_was_not_the_reason() -> None:
    """The other door onto ADV-105's defect, closed: "not probed" is not "probed and failed".

    A query with one constraint has one relaxation, and dropping it renders an empty `q` -
    which asks Gmail for the whole mailbox rather than for a relaxation of this query, so no
    probe is planned and L2 executes nothing. Answering from the plan would report *every
    drop tried, none restored*, which is precisely the conflation the third state exists to
    prevent. It is `incomplete`, and `untried_drops` names the drop.
    """
    _box, envelope = answer("nothinginthismailbox")
    diagnosis = envelope.retrieval_report.empty_diagnosis

    assert diagnosis is not None
    assert diagnosis.status is EmptyDiagnosisStatus.INCOMPLETE
    assert diagnosis.tried == ()
    assert diagnosis.untried_drops == ("terms",)
    assert envelope.retrieval_report.outcome is Outcome.INCONCLUSIVE


def test_a_response_that_found_something_carries_no_empty_diagnosis() -> None:
    """ROUTE-04 scopes the field to zero-hit outcomes; a diagnosis of a non-empty result
    would assert "no single dropped constraint restores results" about a query whose
    constraints were never relaxed."""
    _box, found = answer("procurement")
    assert found.retrieval_report.empty_diagnosis is None

    _box2, empty = answer('from:nobody@team.example "a phrase never written"')
    assert empty.retrieval_report.empty_diagnosis is not None


# --- L3: broadening -------------------------------------------------------------------------


def test_broadening_is_bounded_at_two_probes_and_both_steps_are_named() -> None:
    """A.7's L3 row is `<=2 x 5 u`: the widened query and the whole-mailbox one."""
    planned = BroadeningRung().plan(parse('from:nobody@team.example "a phrase never written"'))

    assert len(planned) == MAX_BROADENING_PROBES
    assert "{from:nobody@team.example to:nobody@team.example}" in planned[0].query
    assert planned[1].include_spam_trash is True


def test_broadening_widens_the_date_window_rather_than_dropping_it() -> None:
    """ "dates x4" (A.7 L3). A dropped window is L2's job and reports a different thing."""
    parsed = parse("procurement after:2026/07/05 before:2026/07/09")
    assert parsed.window is not None
    widened = BroadeningRung().plan(parsed)[0]

    assert "after:2026/07/05" not in widened.query
    assert "after:" in widened.query and "before:" in widened.query
    original_span = parsed.window.end_ms, parsed.window.start_ms
    assert original_span[0] is not None and original_span[1] is not None


# --- the escalation policy between the lexical rungs -----------------------------------------


def test_the_ladder_stops_after_l0_when_a_verified_phrase_matched() -> None:
    """D.3 rule 1b: a locally-verified phrase with no answer-type cue stops the ladder."""
    _box, _client, _ledger, run = drive(f'"the {ANCIENT_PHRASE}"')

    assert run.stop_rule == "D.3-1b"
    assert run.stopped_after is RungId.L0
    assert run.exact_signal.fired is True
    assert run.exact_signal.verified_locally is True
    assert run.rungs_run == (RungId.L0,)
    assert set(run.rungs_skipped) == {RungId.L1, RungId.L1B, RungId.L2, RungId.L3}


def test_a_missing_answer_type_refuses_the_l0_stop_that_would_otherwise_fire() -> None:
    """D.3 rule 1b and ADV-004's ordering fix, executed on the case they exist for.

    The previous ordering had rule 1 kill the whole ladder on `exact_signal_match` *before*
    anything consulted `answer_type_presence` - which switched off the architecture's only
    answer to T-RC2 on exactly the confident-but-wrong results T-RC2 is about. Here the
    phrase matches, locally verifies, and would stop the ladder; the query asks *when*, the
    hit carries no date-like token, and the stop is refused.
    """
    _box, _client, _ledger, run = drive('when did "no further changes"')

    assert run.exact_signal.fired is True
    assert run.exact_signal.branch is ExactBranch.E_B
    assert run.answer_type.answer_type is AnswerType.DATE_LIKE
    assert run.answer_type.present is False
    assert run.answer_type.blocks_stop is True

    assert run.stop_rule is None
    assert run.stopped_after is None
    assert RungId.L1 in run.rungs_run


def test_the_same_stop_fires_when_the_answer_type_is_there() -> None:
    """The other half, so the veto above is a signal rather than a switch that is always on."""
    _box, _client, _ledger, run = drive('when did "cutover scheduled for 2026/04/14"')

    assert run.exact_signal.branch is ExactBranch.E_B
    assert run.answer_type.answer_type is AnswerType.DATE_LIKE
    assert run.answer_type.present is True
    assert run.stop_rule == "D.3-1b"
    assert run.stopped_after is RungId.L0


def test_a_query_with_no_answer_type_cue_is_a_third_state_and_not_a_missing_one() -> None:
    """D.3 rule 1b turns on "or the query carries no answer-type cue", so it is a value."""
    _box, _client, _ledger, run = drive(f'"the {ANCIENT_PHRASE}"')

    assert run.answer_type.answer_type is None
    assert run.answer_type.present is None
    assert run.answer_type.blocks_stop is False
    assert run.answer_type.as_trace_fields() == {
        "answer_type": None,
        "present": None,
        "texts_examined": run.answer_type.examined,
    }


def test_relaxation_and_broadening_run_only_when_nothing_was_found() -> None:
    """D.3 rule 4 applied at the first rung that can act on it, both directions asserted."""
    _box, _client, _ledger, empty = drive('from:nobody@team.example "a phrase never written"')
    assert set(empty.rungs_run) == {RungId.L0, RungId.L1, RungId.L1B, RungId.L2, RungId.L3}
    assert empty.evidence_count == 0

    _box2, _client2, _ledger2, found = drive("procurement")
    assert found.evidence_count == BULK_THREADS
    assert RungId.L2 in found.rungs_skipped
    assert RungId.L3 in found.rungs_skipped


def test_a_rung_that_did_not_run_is_reported_under_the_closed_vocabulary() -> None:
    """AD D.2: `not_tried[].why` is `not_applicable`, `budget | cap | timeout | error`, or
    round 22's argued addition `stopped_on_evidence`.

    **The set is no longer the singleton it was** (WS-10). Every rung that did not run used to
    be reported `not_applicable`, including rungs that were applicable and were merely not
    needed - a claim wider than the code in the field OD-2's whole distinction is built on.
    The three reasons this query can produce are asserted individually below, and each is
    paired with whether it carries an affordance, because that pairing is the operational
    difference the ruling rests on.
    """
    _box, envelope = answer("procurement")
    report = envelope.retrieval_report

    assert report.not_tried
    produced = {entry.why for entry in report.not_tried}
    assert produced <= {NotTriedWhy.NOT_APPLICABLE, NotTriedWhy.STOPPED_ON_EVIDENCE}
    assert NotTriedWhy.NOT_APPLICABLE in produced
    for entry in report.not_tried:
        assert (entry.why is NotTriedWhy.NOT_APPLICABLE) == (entry.affordance is None), entry.rung
    named = {entry.rung for entry in report.not_tried}
    assert named <= {
        *(rung.value for rung in LADDER_RUNGS),
        RungId.L4.value,
        STRUCTURAL_SIMILARITY_RUNG,
    }
    # L5/L6/LR are absent rather than claimed not-applicable: they are not built, and saying
    # they could not have helped would be the false half of the OD-2 distinction. **L4 is now
    # present**, because round 20 built it: for this query every mapped thread linked every
    # reply, so there was no unresolved parent to expand on, and `not_applicable` is then the
    # true statement rather than the false one.
    assert not named & {RungId.L5.value, RungId.L6.value, RungId.LR.value}
    assert RungId.L4.value in named


def test_no_row_this_round_produces_carries_a_number() -> None:
    """RANK-03: "Scores are never fabricated for lexical hits" (AD A.8, CTX Sec 20).

    Ranking is L6 and it is not built, so nothing in this ladder knows anything about a
    message that could order it - `messages.list` returns `id` and `threadId` and no more
    (RO F1). Asserted rather than left to the assembly's docstring, because `MessageRow.score`
    is an optional field with no validator behind it: nothing in the envelope refuses a
    fabricated score, so the only thing keeping one out is that no code path writes one, and
    that is a property worth executing.
    """
    for name, query in CORPUS.items():
        _box, envelope = answer(query)
        for source in envelope.sources:
            for row in source.messages:
                assert row.score is None, (name, row.id)
        assert envelope.retrieval_report.shortlist is None, name
        assert envelope.retrieval_report.pool is None, name


def test_this_round_never_claims_not_found() -> None:
    """OD-2: `not_found` needs no applicable rung untried, and L4/L5/L6/LR are not built."""
    for name, query in CORPUS.items():
        _box, envelope = answer(query)
        assert envelope.retrieval_report.outcome is not Outcome.NOT_FOUND, name


# --- empty_diagnosis: ADV-105's three states -------------------------------------------------


def test_empty_diagnosis_names_the_single_drop_that_restores_results() -> None:
    """State one: a probed drop produced hits, and the affordance re-runs without it.

    The diagnosis survives its own success, which is the part that is easy to get wrong. The
    relaxation found two messages, so the response carries rows and reports `answered` - and
    if the field were suppressed by "something was found" the caller would be handed evidence
    with no statement that the query they wrote matched none of it. The two facts are both
    on the wire: the drop is named in `asked_for.dropped`, and `constraint_drop_depth` counts
    it.
    """
    _box, envelope = answer('from:ops@team.example "a phrase never written"')
    diagnosis = envelope.retrieval_report.empty_diagnosis

    assert diagnosis is not None
    assert diagnosis.status is EmptyDiagnosisStatus.COMPLETE
    assert diagnosis.restores == "phrase"
    assert diagnosis.untried_drops == ()
    assert diagnosis.affordance is not None
    assert diagnosis.affordance.args == {"constraints": {"phrase": None}}

    assert envelope.retrieval_report.outcome is Outcome.ANSWERED
    assert "phrase" in {entry.constraint for entry in envelope.asked_for.dropped}
    assert envelope.asked_for.constraint_drop_depth == 1
    assert envelope.asked_for.term_coverage < 1.0


def test_empty_diagnosis_reports_that_no_single_drop_restores_results() -> None:
    """State two, which is a real finding rather than an absence of one."""
    _box, envelope = answer('from:nobody@team.example "a phrase never written"')
    diagnosis = envelope.retrieval_report.empty_diagnosis

    assert diagnosis is not None
    assert diagnosis.status is EmptyDiagnosisStatus.COMPLETE
    assert diagnosis.restores is None
    assert set(diagnosis.tried) == {"from", "phrase"}
    assert diagnosis.untried_drops == ()


def test_empty_diagnosis_says_incomplete_when_the_probe_budget_ran_out() -> None:
    """State three (ADV-105). Conflating this with state two was the defect being repaired."""
    query = (
        "from:nobody@team.example to:nobody@team.example cc:nobody@team.example "
        'subject:kickoff after:2026/01/01 is:unread has:attachment "a phrase never written" widget'
    )
    _box, envelope = answer(query)
    diagnosis = envelope.retrieval_report.empty_diagnosis

    assert diagnosis is not None
    assert diagnosis.status is EmptyDiagnosisStatus.INCOMPLETE
    assert diagnosis.restores is None
    assert len(diagnosis.tried) == max_relax_probes(9)
    assert diagnosis.untried_drops
    assert diagnosis.affordance is not None


# --- caps: what the ladder gives up, and how it says so ---------------------------------------


def test_hits_beyond_max_hit_threads_become_withheld_records_with_an_affordance() -> None:
    """A.7a's worked example, executed: a cap produces a record, never a silent drop."""
    box, envelope = answer("procurement")

    assert len(envelope.sources) == MAX_HIT_THREADS
    assert box.calls["threads.get"] == MAX_HIT_THREADS
    # Round 29: a thread the cap left unmapped is one counted **group** with its map call -
    # the record A.7a's example describes, written at the granularity of the call that
    # recovers it (R-MCP-033). Nothing is dropped: the certificate still names every id.
    capped = [g for g in envelope.withheld_groups if g.cap.value == "max_hit_threads"]
    assert len(capped) == BULK_THREADS - MAX_HIT_THREADS
    for group in capped:
        assert str(BULK_THREADS) in group.why
        assert group.affordance.args == {"thread_id": group.thread_id}
        assert group.message_count >= 1
    assert len(envelope.withheld_ids) >= BULK_THREADS - MAX_HIT_THREADS
    assert envelope.partial is True


def test_a_hit_beyond_max_body_fetches_is_a_stub_row_and_not_a_withheld_record() -> None:
    """A.7a: "depth reduction is not omission". Confusing them makes withheld lists useless.

    **What WS-11 changed here, and why the name still fits.** A hit whose body the published
    `max_body_fetches` cap stopped this run from fetching used to be disclosed at `stub`
    depth. It is now disclosed at whatever depth the text this response *holds* supports -
    `snippet` where the observation carried one, `stub` where it did not - because a depth is
    a statement about text that exists (`PlannedRow.__post_init__`) and disclosing a snippet
    as a stub understates what the response contains. The property this test is named for is
    unchanged and is the one asserted: a capped hit is **reduced in depth, never withheld**,
    and it carries the affordance that fetches the rest.
    """
    _box, envelope = answer("procurement")

    matched = [
        row for source in envelope.sources for row in source.messages if row.role is Role.MATCHED
    ]
    at_body = [row for row in matched if row.depth is Depth.BODY_CLEAN]
    reduced = [row for row in matched if row.depth is not Depth.BODY_CLEAN]

    assert len(at_body) == MAX_BODY_FETCHES_L1
    assert reduced
    assert {row.depth for row in reduced} <= {Depth.SNIPPET, Depth.STUB}
    withheld = {record.id for record in envelope.withheld}
    for row in reduced:
        assert row.id not in withheld
        assert row.unabridged is not None
        assert row.unabridged.mentions(row.id)


def test_the_thread_the_decomposition_named_is_mapped_before_its_broad_probes_threads() -> None:
    """L1b's intersection is its answer; its single-constraint pages are not (`prefer`)."""
    _box, _client, ledger, run = drive("from:dev@team.example cutover")
    assert run.decomposition is not None

    ranked = hit_threads(ledger, prefer=run.decomposition.intersection)
    assert ranked[0].thread_id == "t-split"


# --- the claims this round's docstrings make about their own coverage --------------------------


def _suite_test_names() -> tuple[set[str], set[str]]:
    """Every test function name and every test module name the suite really contains."""
    functions: set[str] = set()
    modules: set[str] = set()
    for path in Path("tests").rglob("test_*.py"):
        modules.add(path.stem)
        functions.update(re.findall(r"^\s*def (test_\w+)", path.read_text(encoding="utf-8"), re.M))
    return functions, modules


def _tests_named_in(tree: ast.Module) -> set[str]:
    """Every `test_...` identifier a module's string constants mention.

    Read off `ast.Constant` rather than the raw text, so an identifier appearing in *code*
    (`latest_history_id` and friends) is not mistaken for a citation. A wrapped identifier is
    one identifier: `test_a_very_long_\n    name` is how a 100-column formatter leaves it, and
    a sweep that missed those would let exactly the longest names - the ones most likely to be
    aspirational - through.

    **`\b` in front, added when the sweep grew a third tree.** Without it, `test_ts` inside
    `latest_ts` - Slack's own field name, written in an `orivra` docstring - was read as a
    citation of a test nobody had written. The docstring above already named this hazard for
    code identifiers and the pattern only guarded against it there; a sweep that reports a
    docstring's prose as a broken citation trains readers to disbelieve it, which is the one
    thing a standing sweep cannot afford.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.update(re.findall(r"\btest_[A-Za-z0-9_]+", re.sub(r"\n\s*", "", node.value)))
    return found


def _unresolved_citations(named: dict[str, set[str]]) -> dict[str, list[str]]:
    functions, modules = _suite_test_names()
    return {
        name: sorted(paths)
        for name, paths in named.items()
        if name not in functions and name not in modules
    }


def test_every_test_a_source_docstring_names_exists() -> None:
    """The second recurring defect, closed mechanically: a claim wider than the code.

    A module docstring that names the test proving its claim is only worth the name if the
    test exists. Round 15's own modules named four tests that did not, one of them the
    commonality sweep above. This reads every string constant in both source trees and
    requires every `test_...` identifier in them to resolve.
    """
    named: dict[str, set[str]] = {}
    for path in source_files():
        for name in _tests_named_in(parse_module(path)):
            named.setdefault(name, set()).add(str(path))

    assert _unresolved_citations(named) == {}, (
        f"source docstrings name tests that do not exist: {_unresolved_citations(named)}. A "
        "docstring that cites its own evidence is a claim; the citation has to resolve."
    )
    assert "test_every_rung_shares_the_one_property_that_makes_the_ladder_accountable" in named
    assert len(named) > 30, "the sweep found almost no citations; it is reading the wrong thing"


def test_the_citation_sweep_fires_on_a_planted_instance() -> None:
    """A sweep that has never fired is a sweep nobody has tested (round 11's rule).

    The planted module carries both shapes the sweep must catch - a plain citation and one a
    formatter wrapped mid-identifier - beside a real citation that must survive.
    """
    planted = ast.parse(
        '"""A module.\n\n'
        "Proved by `test_a_name_that_was_never_written`, and by\n"
        "`test_another_name_that_was_\n    never_written`, and by\n"
        '`test_every_test_a_source_docstring_names_exists`.\n"""\n'
        "latest_test_history_id = 1\n"
    )
    named = {name: {"planted.py"} for name in _tests_named_in(planted)}

    assert set(_unresolved_citations(named)) == {
        "test_a_name_that_was_never_written",
        "test_another_name_that_was_never_written",
    }
    assert "test_every_test_a_source_docstring_names_exists" in named


# --- the fixtures themselves --------------------------------------------------------------


def test_no_fixture_in_this_file_carries_anything_that_could_be_real_mail() -> None:
    """Executed rather than asserted in prose (EP Sec 5.2, and the work order's own line)."""
    text = mailbox().as_json()
    addresses = set(re.findall(r"[\w.+-]+@[\w.-]+", text))

    assert addresses
    for address in addresses:
        assert address.endswith((".example", ".invalid")), address
    # Deliberately shaped to ignore `internalDate` epochs, which are long digit runs and
    # are the *point* of the fixture: what is refused is a formatted identifier - a phone
    # number, a card, a national id - which always carries separators or a country prefix.
    assert not re.search(r"\+\d[\d ()-]{7,}\d", text)
    assert not re.search(r"\b\d{3}[.\- ]\d{3}[.\- ]\d{4}\b", text)
    assert not re.search(r"\b\d{3}[.\- ]\d{2}[.\- ]\d{4}\b", text)
    assert not re.search(r"\b(?:\d{4}[ -]){3}\d{4}\b", text)


def test_the_double_refuses_an_operator_it_does_not_evaluate() -> None:
    """A double that ignored an operator would widen the query and pass for the wrong reason."""
    with pytest.raises(UnimplementedOperator):
        mailbox().search("larger:5M", include_spam_trash=False)


def test_the_whole_run_reaches_gmail_only_through_the_endpoints_the_ladder_declares() -> None:
    """LEX-01 is partly a statement about which call comes first, which a counter cannot make."""
    box, _envelope = answer("from:dev@team.example cutover")

    assert set(box.call_log) <= {"messages.list", "messages.get", "threads.get"}
    assert box.call_log[0] == "messages.list"
    assert box.call_log.index("threads.get") > box.call_log.index("messages.list")


@pytest.mark.parametrize("query", sorted(CORPUS.values()))
def test_every_corpus_query_produces_a_conforming_envelope(query: str) -> None:
    """The exit condition of WS-04, per query: MailWeave answers, and the envelope validates."""
    _box, envelope = answer(query)

    assert envelope.retrieval_report.rungs
    assert envelope.retrieval_report.scan_scope
    assert envelope.retrieval_report.counters.api_calls > 0
    assert envelope.asked_for.term_coverage <= 1.0
    assert envelope.model_dump(mode="json")["schema_version"] == 2


def test_a_token_that_names_nothing_to_match_is_not_a_probe_however_it_is_spelled() -> None:
    """R-RETR-017, BLOCKER: the predicate is about **selection**, not about spelling.

    `mailweave_search('""')` reproduced R-RETR-006's three failures exactly - wire
    `('in:anywhere ""', True)`, six spam and four trash messages disclosed as
    `role: matched`, `outcome: answered`, `term_coverage: 1.0`. An empty quoted phrase is a
    non-empty string, is not a scope operator and is not a negation, so it passed every check
    round 16 had and became a probeable constraint.

    The fix is not eight new cases. `matchable_content_of` asks what a token would give Gmail
    to look for, so the rule holds for spellings nobody enumerated - which is the property
    the two named-shape predicates beside it cannot have. The assertion below is therefore in
    two halves: the shapes that were reported, **and** a generated family of them, including
    one built from a Unicode format character this file never names, so a token that is
    invisible tomorrow is covered without an edit here.
    """
    reported = (
        '""',
        '" "',
        '"\t"',
        '"\xa0"',
        '"​"',
        '""""',
        'subject:""',
        'subject:" "',
        "subject:",
        "label:",
        "is:",
        "in:",
        "has:",
        "from:",
        'from:""',
        "(subject:)",
    )
    # Every Unicode format character the runtime knows about, not a transcribed list of five.
    invisible = "".join(chr(point) for point in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD))
    generated = (invisible, f'"{invisible}"', f"subject:{invisible}", f'label:"{invisible}"')

    for written in (*reported, *generated):
        assert matchable_content_of(written.split()[0] if written.split() else written) == "", (
            written
        )
        assert carries_no_content(written), written
        assert why_this_q_is_not_a_probe(written) is not None, written
        with pytest.raises(ValueError):
            Probe(rung=RungId.L1, query=written, why="planted")

        parsed_query = parse(written)
        assert parsed_query.constraints == (), written
        assert plan_ladder(parsed_query) == (), written
        # It is dropped **and declared**, so `term_coverage` moves with it (LEX-02). A
        # grouped spelling reaches Gmail's grouping syntax first and is declared under that
        # name instead, which is the older rule and is equally a declaration.
        declared = {name for name, _why in dropped_declarations(parsed_query)}
        assert declared, written
        if not parsed_query.passthrough:
            assert parsed_query.vacuous_tokens != (), written
            assert VACUOUS_TOKEN_CONSTRAINT in declared, written

    # Beside real content it is a declared drop rather than a refusal, and the rest of the
    # query is executed: a paste artefact must not cost the caller their question.
    beside = parse('report "" 2026')
    assert [c.name for c in beside.constraints] == ["terms"]
    assert beside.render() == "report 2026"
    assert beside.term_coverage(beside.constraints) == 0.5
    assert VACUOUS_TOKEN_CONSTRAINT in {n for n, _ in dropped_declarations(beside)}

    # The same sentence one layer down, at the *fragment* level, where `selects_something`
    # decides what may be a decomposition unit. Asserted directly rather than through a
    # parse, because the parse layer now removes these tokens before a constraint is built:
    # the clause is the rule stated where a rung composes a `q` out of a subset of the
    # query's fragments, and a rule that is never executed is a claim.
    for fragment in ('""', '" "', "subject:", 'label:""', "\u200b"):
        assert not selects_something(fragment), fragment
        assert carries_nothing_to_select_by(fragment), fragment

    # And nothing here refuses a token that *does* select. The anti-vacuity half.
    for selecting in ('"rollout cutover"', "subject:vendor", "-cutover", "rollout", "is:unread"):
        assert matchable_content_of(selecting) != "", selecting
        assert not carries_no_content(selecting), selecting
    # A negation names something and still selects nothing - the two predicates answer two
    # questions, and the anti-vacuity half must not blur them.
    for positive in ('"rollout cutover"', "subject:vendor", "rollout", "is:unread"):
        assert selects_something(positive), positive
    assert not selects_something("-cutover")

    # The BLOCKER at the wire: nothing is sent, and nothing is disclosed.
    box = mailbox()
    client = make_client(box)
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run('""', now=NOW, zone=UTC_ZONE)
    assert box.queries == []
    envelope = assemble(run, client=client, ledger=ledger)
    assert envelope.sources == ()
    assert envelope.retrieval_report.outcome is Outcome.INCONCLUSIVE
    assert envelope.asked_for.term_coverage == 0.0


def test_a_route_that_widened_a_constraint_does_not_report_it_enforced() -> None:
    """R-RETR-020: `enforced` is what the executed rungs enforced, not the parse minus L2.

    Two shapes, and neither is a relaxation, which is why the round-16 derivation could not
    see them. A run whose only evidence came from **L3's whole-mailbox probe** reported
    `enforced=('from','terms')`, `dropped=[]` and `term_coverage: 1.0` while the single row
    was a message from a different sender that L3 had admitted after dropping `from:`. And a
    D.3 rule 1b **stop at L0** reported `enforced=('phrase','terms')` for a run whose only
    executed `q` was the phrase, because a rung that never ran cannot have dropped anything.
    "Not a relaxation" was being read as "was enforced".

    A response that states it enforced a constraint it did not is the round-15 blocker's
    class: not the wrong rows, but the response lying about them. So a constraint is enforced
    only when a route the response rests on carried it - and a **widening** is not carrying:
    A.7 L3 replaces a participant with `{from|to}` and a window with one four times as long,
    and a hit admitted by either need not satisfy what the user wrote.
    """
    # L3-only recovery: nothing matches `from:`, and the whole-mailbox probe finds the term.
    box = SyntheticMailbox(
        messages=(
            Msg(
                id="sp-1",
                thread_id="t-sp",
                sender="marketing@vendor.invalid",
                subject="Offer",
                body="Cutover pricing this month.",
                internal_date_ms=epoch_ms(2026, 6, 1),
                labels=("SPAM",),
            ),
            Msg(
                id="in-1",
                thread_id="t-in",
                sender="ana@team.example",
                subject="Roster",
                body="Duty rotation for the week.",
                internal_date_ms=epoch_ms(2026, 6, 2),
                to=("ops@team.example",),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )
    _box, envelope = answer("from:bob@team.example cutover", box=box)
    assert [row.id for source in envelope.sources for row in source.messages] == ["sp-1"]
    assert "from" not in envelope.asked_for.enforced
    dropped = {entry.constraint: entry.why for entry in envelope.asked_for.dropped}
    assert "from" in dropped
    assert RungId.L3.value in dropped["from"]
    assert envelope.asked_for.term_coverage < 1.0
    assert envelope.asked_for.constraint_drop_depth >= 1

    # The L0 stop: the phrase was executed and the terms constraint never was.
    _box, stopped = answer(f'"the {ANCIENT_PHRASE}" cutover')
    assert "phrase" in stopped.asked_for.enforced
    assert TERMS_CONSTRAINT not in stopped.asked_for.enforced
    assert TERMS_CONSTRAINT in {entry.constraint for entry in stopped.asked_for.dropped}
    assert stopped.asked_for.term_coverage < 1.0

    # The widening step itself, at the plan layer: a participant it turned into a
    # disjunction, and a window it multiplied, are given up rather than enforced.
    widened = BroadeningRung().plan(parse("from:ana@team.example rollout after:2026/05/01"))[0]
    assert "from" in widened.dropped and "from" not in widened.enforced
    assert "after" in widened.dropped and "after" not in widened.enforced
    assert TERMS_CONSTRAINT in widened.enforced


def test_a_decomposition_that_never_intersected_does_not_report_the_query_enforced() -> None:
    """R-RETR-024: L1b enforces through its intersection, and only through its intersection.

    A decomposition probe is deliberately broad - one word of two - so every thread it
    touches enters `H` and is disclosed. When some thread satisfies **every** unit, the rung
    really did enforce the constraint those units decompose, and the response may say so.
    When no thread does, the rows are threads that matched a fragment, and a response-level
    `term_coverage: 1.0` over them says the query was answered when it was not.

    The `t-terms` thread carries "rollout" in one message and "handover" in another, so
    `rollout handover` intersects and `rollout escalation` cannot: nothing in the mailbox
    says "escalation" at all. Both are asserted, because a rule that never credits the rung
    would pass the second assertion and fail the product.
    """
    _box, intersected = answer("rollout handover")
    assert intersected.sources, "the split thread must be found at all"
    assert TERMS_CONSTRAINT in intersected.asked_for.enforced
    assert intersected.asked_for.term_coverage == 1.0

    _box, fragmentary = answer("rollout escalation")
    assert TERMS_CONSTRAINT not in fragmentary.asked_for.enforced
    assert fragmentary.asked_for.term_coverage < 1.0
    assert fragmentary.retrieval_report.outcome is Outcome.INCONCLUSIVE
    # Whatever rows the ledger obliged, none of them claims to satisfy the whole constraint.
    for source in fragmentary.sources:
        for row in source.messages:
            assert TERMS_CONSTRAINT not in row.constraint_coverage

    # And the A.7 cap is a drop with a rung beside it, not an inference from `scan_scope`:
    # four units against three probes means one piece of `terms` was never sent.
    capped = parse("from:dev@team.example rollout cutover handover")
    assert len(capped.decomposition_units) == 4
    assert len(DecompositionRung().plan(capped)) == MAX_DECOMPOSITION_PROBES
    _box, over_cap = answer("from:dev@team.example rollout cutover handover")
    assert TERMS_CONSTRAINT not in over_cap.asked_for.enforced


def test_a_drop_no_budget_can_reach_is_not_offered_a_budget() -> None:
    """R-RETR-023: an affordance is a call that would reach the untried rung (AD-03).

    The commonest query shape there is - one bare word, one quoted phrase - has one
    constraint, so `max_relax_probes(1) == 1` and the budget is already at its ceiling; and
    `RelaxationRung.plan` declines the only probe at **any** budget, because dropping the
    only constraint renders an empty `q`, which is a listing rather than a relaxation. The
    diagnosis nevertheless shipped `{"relax": {"max_probes": 1}}`, offering exactly the
    budget the run already had. Following it changes nothing, which is what AD-03 forbids.

    The drop stays in `untried_drops` - it was not tried, and reporting that is the point of
    the field - and the offer is withheld. The second half of the assertion is the control: a
    query whose untried drop the budget *could* reach still gets the offer, so this is not a
    rule that removes affordances.
    """
    for single in ("teleportation", f'"a {ANCIENT_PHRASE} nobody wrote"'):
        _box, envelope = answer(single)
        diagnosis = envelope.retrieval_report.empty_diagnosis
        assert diagnosis is not None, single
        assert diagnosis.status is EmptyDiagnosisStatus.INCOMPLETE, single
        assert diagnosis.untried_drops != (), single
        assert diagnosis.affordance is None, single
        assert RelaxationRung().plan(parse(single)) == (), single
        assert RelaxationRung().plannable_drops(parse(single)) == (), single

    # The control: with more constraints than the probe budget, the untried drops are ones a
    # larger budget would reach, and the offer is minted.
    crowded = (
        "from:dev@team.example to:ops@team.example cc:qa@team.example "
        "subject:migration label:vendors is:unread has:attachment teleportation"
    )
    assert len(parse(crowded).constraints) > max_relax_probes(len(parse(crowded).constraints))
    _box, envelope = answer(crowded)
    diagnosis = envelope.retrieval_report.empty_diagnosis
    assert diagnosis is not None
    assert diagnosis.status is EmptyDiagnosisStatus.INCOMPLETE
    assert diagnosis.affordance is not None
    # Round 24: the offer carries the caller's own query beside the probe budget,
    # because `mailweave_search` requires one and an affordance is a call (R-07).
    assert diagnosis.affordance.args == {
        "query": parse(crowded).raw,
        "relax": {"max_probes": len(parse(crowded).constraints)},
    }
    assert RelaxationRung().plannable_drops(parse(crowded)) != ()


def test_a_probe_whose_rows_an_earlier_probe_admitted_still_counts_as_a_route() -> None:
    """`_routes` reads the page's own count, not the admission delta - and here is why.

    The transport hands back counts rather than ids, so `ExecutedProbe.ids_admitted` is a
    **delta**: what this probe was the first to record. A probe whose page returned rows an
    earlier probe had already admitted therefore reports an empty delta while having matched
    exactly what the response discloses. `_asked_for` has read `ids_returned` for a
    relaxation since round 16 for this reason; extending the account to every rung had to
    read the same number, and reading the delta instead silently drops such a probe - and its
    enforcement - out of the response's account of itself.

    Here `from:dev@… from:ops@… cutover` matches nothing at L1 (the parts are in different
    messages of `t-split`), L1b's two participant probes admit `spl-1` and `spl-2`, and its
    `cutover` probe returns `spl-2` and admits **nothing new**. That last probe carries the
    whole `terms` constraint, so `terms` is enforced; on the delta it would have been
    reported dropped by a route that had in fact matched.
    """
    box, envelope = answer("from:dev@team.example from:ops@team.example cutover")
    executed = {q for q, _spam in box.queries}
    assert "cutover" in executed

    _box, _client, _ledger, run = drive("from:dev@team.example from:ops@team.example cutover")
    overlapping = [
        entry
        for entry in run.executed_probes
        if entry.probe.rung is RungId.L1B and entry.probe.query == "cutover"
    ]
    assert len(overlapping) == 1
    assert overlapping[0].ids_returned > 0
    assert overlapping[0].ids_admitted == frozenset(), (
        "the fixture no longer produces the overlap this test is about"
    )

    assert TERMS_CONSTRAINT in envelope.asked_for.enforced
    assert TERMS_CONSTRAINT not in {entry.constraint for entry in envelope.asked_for.dropped}
