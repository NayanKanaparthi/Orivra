"""Round 19: a region is what an operator *does*, and a row says what was observed.

Three claims are executed here, each against the whole client-and-ladder stack with an
`httpx.MockTransport` where the socket would be:

  * **the region asymmetry is decided from the operator registry** (OD-5 point 3, A9-A2,
    R-RETR-035/036/037). Round 18 stated the rule correctly and implemented it as one lexical
    prefix, so it generalised over *values written under `in:`* and not over *region-selecting
    operators*. The tests below assert the classification against a written-out oracle, and
    the sweeps that consume it are generated from `KIND_BY_OPERATOR` so that an operator
    registered tomorrow is covered without an edit here;
  * **provenance is stated only where it was observed** (OD-5 point 1, A9-A1, R-RETR-038/039).
    Every row carries it, stubs included; a row whose labels no observation stated says so and
    never reports a negative;
  * **an affordance is a call that executes** (I-4, ROUTE-01's fifth element, R-RETR-040).
    Every offer any branch mints is executed here and asserted to reach Gmail, and the offers
    that are deliberately not minted are asserted absent with the reason.

No fixture here carries real or realistic mail: every address is in the reserved `.example`
or `.invalid` TLDs (RFC 2606/6761), every subject and body is invented for the structural
property under test, and the vocabulary is nonsense chosen for this round
(`vellichor tarnhelm quillon sable-8821`).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from pydantic import ValidationError

from mailweave.constants import (
    ANYWHERE_OPERATOR,
    NEGATION_PREFIX,
    SPAM_OPERATOR,
    TRASH_OPERATOR,
    operator_token,
    query_tokens,
)
from mailweave.envelope.disposition import DispositionLedger
from mailweave.envelope.reasons import RungId
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import Depth, Linkage, Role
from mailweave.envelope.wire import MailboxProvenance, MessageRow
from mailweave.gmail import BackoffPolicy, CallMeter, GmailClient, StaticToken
from mailweave.net.egress import build_client
from mailweave.query import (
    KIND_BY_OPERATOR,
    OperatorKind,
    OperatorName,
    analyse,
    declares_the_search_region,
    operator_of,
)
from mailweave.retrieval.assemble import (
    assemble,
    report_affordances,
    without_the_region_it_named,
)
from mailweave.retrieval.ladder import (
    LADDER,
    BroadeningRung,
    LadderRunner,
    RelaxationRung,
    plan_ladder,
    why_this_q_is_not_a_probe,
)
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.test_lexical_ladder import REGION_DECLARING_FRAGMENTS

NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)
UTC_ZONE = ZoneInfo("UTC")
TOKEN = "ya29.SECRET-ACCESS-TOKEN-NEVER-IN-A-ROUND-19-FIXTURE"

#: The three `q` spellings that put spam or trash into a listing's scope, **written out** as
#: this test module's own oracle. `mailweave.constants` holds the product's copy and the
#: request-time coupling derives `includeSpamTrash` from it; asserting a probe's flag against
#: that same derivation would compare a function with itself, and emptying it would satisfy
#: both sides at once. Three literals here cost a line and cannot do that.
WIDENING_SPELLINGS: frozenset[str] = frozenset({"in:anywhere", "in:spam", "in:trash"})

#: One invented word, planted once per region, so a probe that left the region the query
#: named shows up as an extra row rather than as an argument about the fixture.
MARKER = "vellichor"

#: A word planted only outside the default mailbox, so the published broadening is the only
#: step that can find it. Without it a test claiming to exercise L3 would assert over a run
#: that never reached it.
HIDDEN = "tarnhelm"


def spread() -> SyntheticMailbox:
    """The marker in the inbox, in spam, in trash, under a user label and under a tab."""
    return SyntheticMailbox(
        messages=(
            Msg(
                id="q-in",
                thread_id="t-in",
                sender="ops@team.example",
                subject="Agenda",
                body=f"The {MARKER} item is listed.",
                internal_date_ms=epoch_ms(2026, 7, 1),
                labels=("INBOX",),
            ),
            Msg(
                id="q-sp",
                thread_id="t-sp",
                sender="bulk@parts.invalid",
                subject="Offer",
                body=f"A {MARKER} offer, filed beside {HIDDEN}.",
                internal_date_ms=epoch_ms(2026, 7, 2),
                labels=("SPAM",),
            ),
            Msg(
                id="q-tr",
                thread_id="t-tr",
                sender="old@parts.invalid",
                subject="Discarded",
                body=f"A discarded {MARKER} note about {HIDDEN}.",
                internal_date_ms=epoch_ms(2026, 7, 3),
                labels=("TRASH",),
            ),
            Msg(
                id="q-lb",
                thread_id="t-lb",
                sender="lead@team.example",
                subject="Filed",
                body=f"The {MARKER} record for the programme.",
                internal_date_ms=epoch_ms(2026, 7, 4),
                labels=("INBOX", "QUILLON"),
            ),
            Msg(
                id="q-ct",
                thread_id="t-ct",
                sender="news@parts.example",
                subject="Bulletin",
                body=f"A {MARKER} bulletin.",
                internal_date_ms=epoch_ms(2026, 7, 5),
                labels=("INBOX", "CATEGORY_UPDATES"),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 12),
    )


def mixed_thread() -> SyntheticMailbox:
    """One thread whose members sit in three different places, and one hit inside it.

    The stub half of OD-5 point 1 needs exactly this shape: a thread map that carries members
    from spam and trash into an otherwise ordinary thread, so the rows the response discloses
    as *stubs* are the ones whose provenance a reader most needs.
    """
    return SyntheticMailbox(
        messages=(
            Msg(
                id="m-1",
                thread_id="t-mix",
                sender="ana@team.example",
                subject="Programme",
                body=f"Opening note about {MARKER}.",
                internal_date_ms=epoch_ms(2026, 7, 10),
                labels=("INBOX",),
            ),
            Msg(
                id="m-2",
                thread_id="t-mix",
                sender="bulk@parts.invalid",
                subject="Re: Programme",
                body="A reply that was filed away.",
                internal_date_ms=epoch_ms(2026, 7, 11),
                labels=("TRASH",),
            ),
            Msg(
                id="m-3",
                thread_id="t-mix",
                sender="noise@parts.invalid",
                subject="Re: Programme",
                body="A reply nobody wanted.",
                internal_date_ms=epoch_ms(2026, 7, 12),
                labels=("SPAM",),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 12),
    )


def client_for(
    box: SyntheticMailbox, *, transport: httpx.MockTransport | None = None
) -> GmailClient:
    return GmailClient(
        token=StaticToken(TOKEN),
        http=build_client(inner=transport if transport is not None else box.transport()),
        meter=CallMeter(),
        policy=BackoffPolicy(),
        sleeper=lambda _seconds: None,
        jitterer=lambda: 0.5,
    )


def answer(
    query: str,
    box: SyntheticMailbox | None = None,
    *,
    transport: httpx.MockTransport | None = None,
) -> tuple[SyntheticMailbox, Envelope]:
    mailbox = box if box is not None else spread()
    client = client_for(mailbox, transport=transport)
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run(query, now=NOW, zone=UTC_ZONE)
    return mailbox, assemble(run, client=client, ledger=ledger)


def rows(envelope: Envelope) -> list[MessageRow]:
    return [row for source in envelope.sources for row in source.messages]


def parse(query: str):  # type: ignore[no-untyped-def]
    return analyse(query, now=NOW, zone=UTC_ZONE)


# --- Part 1: the region asymmetry is decided from the registry ----------------------------

#: What each operator of the lexicon **does**, written out. This is the oracle
#: `declares_the_search_region` is checked against, and it is written rather than derived
#: because deriving it would compare the predicate with the mapping the predicate reads -
#: `f(x) == f(x)`, satisfied by emptying both sides at once, which is the vacuity this
#: project's own reviewer has planted successfully twice.
#:
#: It is deliberately a **partial** oracle, asserted over the operators it names rather than
#: over the whole enum. An operator registered tomorrow must be covered by the behavioural
#: sweeps without anyone editing a test, and an oracle asserted total here would make a
#: newly registered operator fail this test rather than pass those.
WHAT_EACH_OPERATOR_DOES: dict[str, bool] = {
    # selects the region the search runs over: where a message is filed
    "in": True,
    "label": True,
    "category": True,
    # filters within whatever region is searched: a property of the message itself
    "is": False,
    "has": False,
    "list": False,
    "filename": False,
    "from": False,
    "to": False,
    "cc": False,
    "bcc": False,
    "deliveredto": False,
    "subject": False,
    "after": False,
    "before": False,
    "older_than": False,
    "newer_than": False,
    "size": False,
    "larger": False,
    "smaller": False,
    "rfc822msgid": False,
}


def test_the_region_predicate_reads_what_an_operator_does_not_how_it_is_spelled() -> None:
    """A9-A2 verbatim, executed against a written-out oracle (R-RETR-036).

    Round 18's predicate was `token.startswith(MAILBOX_LOCATION_PREFIX)`, so it answered a
    question about *spelling* while its docstring described a category. The two disagree in
    both directions and both directions are asserted here: an operator that selects a region
    without being spelled `in:` is a region declaration, and an operator spelled with some
    other prefix that only filters is not.
    """
    for name, selects in WHAT_EACH_OPERATOR_DOES.items():
        value = "spam" if selects else "unread"
        for polarity in ("", NEGATION_PREFIX):
            fragment = f"{polarity}{name}:{value}"
            assert declares_the_search_region(fragment) is selects, fragment

    # Every entry agrees with the kind the registry gives it, so an operator whose *kind*
    # changes fails here rather than silently changing what a probe carries.
    for name, selects in WHAT_EACH_OPERATOR_DOES.items():
        registered = KIND_BY_OPERATOR[OperatorName(name)] is OperatorKind.REGION
        assert registered is selects, name

    # **And the oracle is a subset assertion, deliberately.** Asserting it total over
    # `OperatorName` would mean that registering a new operator fails this test until someone
    # edits it - the enumeration this round removed, wearing a test's clothes. It was written
    # that way first and `tests/test_new_operator_round19.py` caught it, which is what that
    # file is for. The floor is anti-vacuity: the lexicon had twenty-one members when this was
    # written and every one of them is named above. What makes a *new* operator state what it
    # does is `test_the_kind_map_is_total_over_the_lexicon`; what makes it covered is that the
    # sweeps read the registry.
    assert set(WHAT_EACH_OPERATOR_DOES) <= {name.value for name in OperatorName}
    assert len(WHAT_EACH_OPERATOR_DOES) >= 21


def test_a_fragment_that_names_no_operator_and_no_value_declares_no_region() -> None:
    """The two ways a region declaration can be absent, and one of them is a phrase."""
    assert declares_the_search_region("label:") is False
    assert declares_the_search_region('label:""') is False
    assert declares_the_search_region('"in:spam"') is False
    assert declares_the_search_region("vellichor") is False
    assert declares_the_search_region("") is False
    assert operator_of('"9:30 standup"') is None
    assert operator_of("thread:1837abf") is None
    assert operator_of("IN:INBOX") is OperatorName.IN


def test_a_grouped_region_declaration_is_the_operator_it_groups() -> None:
    """R-RETR-035: a group holding one operator is that operator, at the parse and on the wire.

    The predicate family already agreed with this - `operator_token` strips Gmail's grouping
    punctuation - and the parser did not, so the fragment never became a constraint, the
    broadening gate never saw a region, and the published whole-mailbox step ran over a query
    that had excluded one. `(-in:spam) vellichor` returned the spam and trash messages as
    `role: matched` under `outcome: answered`.
    """
    for written in (f"({NEGATION_PREFIX}{SPAM_OPERATOR})", f"{NEGATION_PREFIX}({SPAM_OPERATOR})"):
        parsed = parse(f"{written} {MARKER}")
        assert [(c.name, c.fragments) for c in parsed.constraints] == [
            ("in", (f"{NEGATION_PREFIX}{SPAM_OPERATOR}",)),
            ("terms", (MARKER,)),
        ], written
        assert parsed.passthrough == (), written

        box, envelope = answer(f"{written} {MARKER}")
        assert box.queries == [(f"{NEGATION_PREFIX}{SPAM_OPERATOR} {MARKER}", False)], written
        assert sorted(row.id for row in rows(envelope)) == ["q-ct", "q-in", "q-lb"], written


def test_a_region_the_parse_could_not_carry_still_stops_the_broadening() -> None:
    """R-RETR-035's multi-token half and R-RETR-037, closed by one clause.

    A group holding several tokens cannot be re-emitted: `-(a OR b)` is `-a AND -b`, and
    distributing the negation is regrouping a boolean, which this parser deliberately does not
    do. A fullwidth spelling reaches the same place from the other side - `operator_token`
    NFKC-normalises and `tokenise` does not, which is a normalisation policy question for A.6.
    Neither is allowed to end in the whole mailbox: the broadening step reads the query's own
    tokens, so a region the parse dropped is still a region the caller named.
    """
    unparseable = (
        f"{NEGATION_PREFIX}({SPAM_OPERATOR} OR {TRASH_OPERATOR}) {MARKER}",
        f"({NEGATION_PREFIX}{SPAM_OPERATOR} {NEGATION_PREFIX}{TRASH_OPERATOR}) {MARKER}",
        f"{NEGATION_PREFIX}ＩＮ：ＳＰＡＭ {MARKER}",
        f"ＩＮ：ＳＰＡＭ {MARKER}",
    )
    for query in unparseable:
        box, envelope = answer(query)
        assert [flag for _q, flag in box.queries] == [False] * len(box.queries), query
        assert not any(ANYWHERE_OPERATOR in q for q, _flag in box.queries), (query, box.queries)
        for row in rows(envelope):
            assert row.mailbox.regions == (), (query, row.id, row.mailbox.regions)


def test_a_label_that_names_a_system_mailbox_is_a_region_declaration() -> None:
    """R-RETR-036's reachable half, end to end, in the shape the reviewer measured it in.

    `-label:spam <term>` sent the exclusion at L1, dropped it at L2, widened past it at L3 with
    `includeSpamTrash=true`, and disclosed the spam and trash messages as `role: matched` under
    `outcome: answered`. The fix is not a two-value vocabulary of Gmail's system labels - which
    is exactly the enumeration A9 forbids - but the operator's registered kind, so it holds for
    `label:inbox` and for a system label Gmail names next year without an edit.
    """
    for region in (SPAM_OPERATOR, TRASH_OPERATOR):
        label = f"label:{region.split(':', 1)[1]}"
        box, envelope = answer(f"{NEGATION_PREFIX}{label} {MARKER}")
        assert [flag for _q, flag in box.queries] == [False] * len(box.queries), label
        assert all(f"{NEGATION_PREFIX}{label}" in q for q, _flag in box.queries), box.queries
        for row in rows(envelope):
            assert row.mailbox.regions == (), (label, row.id, row.mailbox.regions)

    # And a user's own label is carried by the same rule, which is what it costs: the query is
    # answered inside the label and never widened out of it.
    box, envelope = answer(f"label:quillon {MARKER}")
    assert [row.id for row in rows(envelope)] == ["q-lb"]
    assert not any(ANYWHERE_OPERATOR in q for q, _flag in box.queries), box.queries


def test_a_refused_region_drop_is_reported_untried_and_costs_no_probe() -> None:
    """The region is not relaxable, and the response says so rather than absorbing it.

    This is the cost side of the conservative reading, asserted so that it is a decision rather
    than a surprise: the drop stays in `drop_order`, is named in `untried_drops`, is offered no
    budget, and the probe it would have used is not spent.
    """
    parsed = parse(f"label:quillon {MARKER}")
    rung = RelaxationRung()
    assert rung.plannable_drops(parsed) == ()
    assert rung.plan(parsed) == ()
    assert set(rung.drop_order(parsed)) == {"label", "terms"}

    _box, envelope = answer(f"label:quillon {HIDDEN}")
    diagnosis = envelope.retrieval_report.empty_diagnosis
    assert diagnosis is not None
    assert diagnosis.untried_drops == ("label", "terms")
    assert diagnosis.tried == ()


def _widening_tokens(text: str) -> set[str]:
    """The tokens of `text` that name spam or trash as a place to look, polarity kept."""
    return {
        operator_token(token)
        for token in query_tokens(text)
        if operator_token(token).lstrip(NEGATION_PREFIX) in WIDENING_SPELLINGS
    }


def test_no_probe_of_the_whole_region_family_enters_a_region_the_query_excluded() -> None:
    """My own adversarial sweep over the registry's region operators and four spellings.

    The population is generated - every operator registered `OperatorKind.REGION`, in both
    polarities, written bare and in each of Gmail's two groupings - and the oracle is the one
    thing that matters at the wire: a probe may not set `includeSpamTrash` unless the caller's
    own query widened, and it may not carry a region fragment the caller did not write.
    """
    checked = 0
    for fragment in REGION_DECLARING_FRAGMENTS:
        spellings = (fragment, f"({fragment})", f"{{{fragment}}}")
        for spelling in spellings:
            for body in (MARKER, f"{MARKER} quillon", f"from:ana@team.example {MARKER}"):
                query = f"{spelling} {body}"
                parsed = parse(query)
                widened = any(
                    operator_token(token) in WIDENING_SPELLINGS for token in query_tokens(query)
                )
                wrote = _widening_tokens(query)
                for probe in plan_ladder(parsed):
                    checked += 1
                    assert probe.include_spam_trash is widened, (query, probe.rung, probe.query)
                    # The narrowing half: a probe may carry only the widening spellings the
                    # caller wrote, in the polarity the caller wrote them in.
                    assert _widening_tokens(probe.query) <= wrote, (query, probe.query)
    assert checked > 400, checked


def split_thread() -> SyntheticMailbox:
    """One thread whose *scope* one message satisfies and whose *term* another carries.

    The founding bug's own shape, written for a scope rather than for two terms: `label:X term`
    matches nothing at L1 because Gmail's `q` is message-scoped (RO F2), and L1b is what
    recovers it - by probing each constraint separately and intersecting on `threadId`.
    """
    return SyntheticMailbox(
        messages=(
            Msg(
                id="s-1",
                thread_id="t-split",
                sender="ana@team.example",
                subject="Opening",
                body="a note carrying nothing to find",
                internal_date_ms=epoch_ms(2026, 7, 1),
                labels=("INBOX", "QUILLON"),
            ),
            Msg(
                id="s-2",
                thread_id="t-split",
                sender="bo@team.example",
                subject="Re: Opening",
                body=f"the {MARKER} answer",
                internal_date_ms=epoch_ms(2026, 7, 2),
                labels=("SENT",),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 12),
    )


def test_what_the_conservative_reading_costs_is_declared_and_one_call_from_recovered() -> None:
    """The price of registering `label:` as a region, executed rather than asserted in prose.

    A scope is carried onto **every** probe (OD-5 point 3, A9-A2), so a query that names a
    label and one term has one decomposition unit rather than two - and the thread whose label
    is on one message and whose term is on another is no longer recovered. Round 18 recovered
    it, because it read a label as a filter; that is the same reading which let `-label:spam`
    be relaxed away and widened past. This round takes the other side of that trade, and the
    trade is only defensible if the loss is **declared** and **recoverable**, which is what is
    asserted here:

      * the response does not claim to have answered - it is `inconclusive`, names the drop it
        did not try, and does not report the label enforced over rows it never saw;
      * the affordance it carries is the call that finds the thread, and executing it does.

    If a later round obtains Gmail's system-label vocabulary (R-GMAIL, A.6), `label:` can split
    into the system labels that are regions and the user's own that are filters, and this cost
    goes away for the second kind. Until then it is a cost this test keeps visible.
    """
    box = split_thread()
    _box, envelope = answer(f"label:quillon {MARKER}", box)
    assert rows(envelope) == []
    assert envelope.retrieval_report.outcome.value == "inconclusive"
    diagnosis = envelope.retrieval_report.empty_diagnosis
    assert diagnosis is not None and "label" in diagnosis.untried_drops
    assert [offer.args for offer in envelope.affordances] == [{"query": MARKER}]

    # And the offered call recovers the thread the scoped query could not reach.
    _recovered_box, recovered = answer(MARKER, split_thread())
    assert sorted(row.id for row in rows(recovered)) == ["s-1", "s-2"]
    assert recovered.retrieval_report.outcome.value == "answered"

    # The control: a filtering operator over the same split thread still decomposes, so the
    # loss is the region rule's and not decomposition breaking.
    _control_box, control = answer(f"from:ana@team.example {MARKER}", split_thread())
    assert sorted(row.id for row in rows(control)) == ["s-1", "s-2"]


# --- Part 2: provenance is stated only where it was observed ------------------------------


def test_a_stub_row_states_the_region_its_own_labels_place_it_in() -> None:
    """OD-5 point 1 for the shape that motivates the field (R-RETR-038).

    A thread map can carry a spam reply into an otherwise ordinary thread, and those members
    are disclosed as **stubs**. Round 18's own report named that as the reason provenance had
    to be on the row rather than on the response - and removing it from every non-hit row left
    all 2,271 tests green, because the only test that read a row's provenance had a fixture in
    which every disclosed row was a hit.

    The expected regions are written out per planted id, not computed from the row's own
    labels: `row.regions == mailbox_regions_of(row.labels)` is satisfied by emptying the
    derivation, which is what the replant harness proved by doing it.
    """
    _box, envelope = answer(MARKER, mixed_thread())
    disclosed = {row.id: row for row in rows(envelope)}
    assert set(disclosed) == {"m-1", "m-2", "m-3"}
    assert [row.role for row in disclosed.values() if row.role is Role.STUB], (
        "the sweep is not vacuous"
    )

    expected_regions = {"m-1": (), "m-2": ("trash",), "m-3": ("spam",)}
    expected_roles = {"m-1": Role.MATCHED, "m-2": Role.STUB, "m-3": Role.STUB}
    for message_id, row in disclosed.items():
        assert row.role is expected_roles[message_id], message_id
        assert row.mailbox.observed is True, message_id
        assert row.mailbox.regions == expected_regions[message_id], message_id
        assert row.mailbox.outside_the_default_mailbox is bool(expected_regions[message_id])


def test_a_row_without_a_mailbox_provenance_is_not_representable() -> None:
    """OD-5 point 1 says *every* `MessageRow`, so the field is required by declaration.

    Defaulting it left the suite green (R-RETR-038, plant X1): nothing asserted that a row must
    carry the field at all, so the requiredness was a comment beside a declaration rather than
    a property anything held.
    """
    payload = {
        "id": "m-1",
        "position": 1,
        "role": Role.STUB.value,
        "reason": {"kind": "thread_member", "thread_id": "t-mix", "position": 1},
        "depth": Depth.STUB.value,
        "linkage": Linkage.HEADERS_UNOBSERVED.value,
        "unabridged": {"tool": "mailweave_get_messages", "args": {"ids": ["m-1"]}},
    }
    with pytest.raises(ValidationError):
        MessageRow.model_validate(payload)
    with_provenance = {**payload, "mailbox": {"observed": False}}
    assert MessageRow.model_validate(with_provenance).mailbox.observed is False


def test_a_response_that_observed_no_labels_says_so_and_states_no_negative() -> None:
    """R-RETR-039: `observed` had no product producer and the derived field read as a negative.

    Driven through the real client and the real `assemble`, behind a transport that removes
    `labelIds` from every `threads.get` message - which is the shape a `format=metadata`
    response may have (PF-2, R-GMAIL). Before this round every such row reported
    `observed: true`, `regions: []` and `outside_the_default_mailbox: false`: a positive claim
    about a message's location derived from an observation that stated nothing.
    """
    box = mixed_thread()
    inner = box.handler

    def stripping(request: httpx.Request) -> httpx.Response:
        response = inner(request)
        if "/threads/" in str(request.url.path):
            payload = json.loads(response.content)
            for message in payload.get("messages", []):
                message.pop("labelIds", None)
            return httpx.Response(response.status_code, json=payload, request=request)
        return response

    _box, envelope = answer(MARKER, box, transport=httpx.MockTransport(stripping))
    disclosed = rows(envelope)
    assert {row.id for row in disclosed} == {"m-1", "m-2", "m-3"}
    for row in disclosed:
        assert row.mailbox.observed is False, row.id
        assert row.mailbox.labels == (), row.id
        assert row.mailbox.regions is None, row.id
        assert row.mailbox.outside_the_default_mailbox is None, row.id

    # A stated empty list is a different fact and still reads as an observation.
    stated = MailboxProvenance.of(())
    assert (stated.observed, stated.regions, stated.outside_the_default_mailbox) == (
        True,
        (),
        False,
    )


def test_the_unobserved_state_is_on_the_wire_as_an_absence() -> None:
    """A reader of the JSON can tell "not spam" from "not known" (amendment A6's discipline)."""
    known = MailboxProvenance.of(("SPAM",)).model_dump(mode="json")
    unknown = MailboxProvenance.unobserved().model_dump(mode="json")
    assert known == {
        "observed": True,
        "labels": ["SPAM"],
        "regions": ["spam"],
        "outside_the_default_mailbox": True,
    }
    assert unknown == {
        "observed": False,
        "labels": [],
        "regions": None,
        "outside_the_default_mailbox": None,
    }


# --- Part 3: an affordance is a call that executes -----------------------------------------


#: Every query shape that reaches a branch of the affordance minting, one per branch, with the
#: branch named. The test below executes what each one mints rather than asserting its shape,
#: so an offer that reaches no rung fails here - which is the whole of AD-03.
AFFORDANCE_BRANCHES: dict[str, str] = {
    "report/unproven_operator": "thread:1837abf",
    "report/unparsed_syntax": f"({MARKER} OR quillon)",
    "report/unparsed_syntax_braced": f"{{{MARKER} quillon}}",
    "recovery/region_named_positively": f"in:sent {HIDDEN}",
    "recovery/region_named_by_label": f"label:quillon {HIDDEN}",
    "recovery/region_named_by_category": f"category:updates {HIDDEN}",
    "diagnosis/budget_bound": (
        "from:nobody@team.example to:nobody@team.example cc:nobody@team.example "
        "subject:kickoff after:2026/01/01 is:unread has:attachment "
        f'"a phrase never written" {HIDDEN}'
    ),
}


def test_every_offer_any_branch_mints_is_executed_and_reaches_gmail() -> None:
    """R-RETR-040: one of the four offer kinds did not reach Gmail, and the test listed three.

    `{"query": "in:anywhere", "terms": []}` was minted for a query naming only where to look.
    Executed, it sent no request: no tool in this tree takes a `terms` argument and the region
    alone is the listing `why_this_q_is_not_a_probe` refuses. It is gone, and this test is
    generated from the branch table rather than from a list of queries, so a branch added later
    is executed the day it is added.

    An offer carrying a `query` is executed and must reach Gmail. An offer carrying a `relax`
    budget is not a query, so what is asserted of it is the thing that makes it concrete: a
    drop the rung really would plan at that budget.
    """
    executed = 0
    for branch, query in AFFORDANCE_BRANCHES.items():
        _box, envelope = answer(query)
        offers = list(envelope.affordances)
        diagnosis = envelope.retrieval_report.empty_diagnosis
        if diagnosis is not None and diagnosis.affordance is not None:
            offers.append(diagnosis.affordance)
        assert offers, branch
        for offer in offers:
            follow_up = offer.args.get("query")
            if follow_up is None:
                budget = offer.args.get("relax")
                assert isinstance(budget, dict) and "max_probes" in budget, branch
                assert RelaxationRung().plannable_drops(parse(query)), branch
                continue
            assert isinstance(follow_up, str)
            assert why_this_q_is_not_a_probe(follow_up) is None, (branch, follow_up)
            next_box, _next = answer(follow_up)
            assert next_box.queries, (branch, follow_up)
            executed += 1
    assert executed >= len(AFFORDANCE_BRANCHES) - 1, executed


def test_a_scoped_query_that_found_nothing_carries_the_call_that_drops_the_scope() -> None:
    """The recall the region rule costs is handed back as a concrete call (I-4, R-RETR-041).

    `in:sent <term>` named two untried drops and four untried rungs and offered nothing.
    `in:unread <term>` is the sharper case: it names a message *state* under Gmail's location
    prefix, so this round's conservative reading treats it as a region and withholds the whole
    recovery ladder from it. That is a recall loss, it is not closable without a vocabulary of
    Gmail's locations that nothing here can establish, and what makes it recoverable is that
    the response says what to call instead.
    """
    for query, expected in (
        (f"in:sent {HIDDEN}", HIDDEN),
        (f"in:unread {HIDDEN}", HIDDEN),
        (f"in:inbox {HIDDEN}", HIDDEN),
        (f"label:quillon {HIDDEN}", HIDDEN),
        (f"in:inbox from:ana@team.example {HIDDEN}", f"from:ana@team.example {HIDDEN}"),
    ):
        _box, envelope = answer(query)
        assert [offer.args for offer in envelope.affordances] == [{"query": expected}], query
        diagnosis = envelope.retrieval_report.empty_diagnosis
        assert diagnosis is not None and diagnosis.affordance is not None, query
        assert diagnosis.affordance.args == {"query": expected}, query


def test_nothing_offered_would_undo_an_exclusion_the_caller_wrote() -> None:
    """The one thing a recovery offer may never be: a proposal to read what was excluded.

    The call it would name is scope-free, and A.7 L3's published step widens a scope-free query
    to the whole mailbox - so offering it is not neutral. If that is judged too conservative it
    is a decision for the orchestrator, and ROUTE-01's acceptance needs the exception written
    into it, because as written it is unmeetable for this class.
    """
    for query in (
        f"{NEGATION_PREFIX}{SPAM_OPERATOR} {HIDDEN}",
        f"{NEGATION_PREFIX}{TRASH_OPERATOR} {HIDDEN}",
        f"{NEGATION_PREFIX}label:spam {HIDDEN}",
        f"in:inbox {NEGATION_PREFIX}{SPAM_OPERATOR} {HIDDEN}",
    ):
        parsed = parse(query)
        assert without_the_region_it_named(parsed) is None, query
        _box, envelope = answer(query)
        assert envelope.affordances == (), query
        diagnosis = envelope.retrieval_report.empty_diagnosis
        assert diagnosis is None or diagnosis.affordance is None, query

    # And the grouped spelling of an exclusion is not offered a de-grouped call either: the
    # strip that reaches an asserted second region from a negated group would name the region
    # the caller excluded, minted by MailWeave rather than written by the caller.
    grouped = parse(f"{NEGATION_PREFIX}({SPAM_OPERATOR} OR {TRASH_OPERATOR}) {HIDDEN}")
    assert report_affordances(grouped) == ()
    assert without_the_region_it_named(grouped) is None
    _box, grouped_envelope = answer(
        f"{NEGATION_PREFIX}({SPAM_OPERATOR} OR {TRASH_OPERATOR}) {HIDDEN}"
    )
    assert grouped_envelope.affordances == ()


#: Zero-evidence shapes, chosen to span the ways a query can fail to find anything: bare terms,
#: an unparsed boolean, each polarity of a region declaration under each region-selecting
#: operator, a participant, a phrase, a date and an unprovable operator.
ZERO_EVIDENCE_SHAPES: tuple[str, ...] = (
    "zzalpha",
    "zzalpha zzbeta",
    "zzalpha OR zzbeta",
    "(zzalpha OR zzbeta)",
    "{zzalpha zzbeta}",
    "in:inbox zzalpha",
    "in:sent zzalpha",
    "in:unread zzalpha",
    "in:nowhere zzalpha",
    "label:quillon zzalpha",
    "category:updates zzalpha",
    f"{NEGATION_PREFIX}{SPAM_OPERATOR} zzalpha",
    f"{NEGATION_PREFIX}label:spam zzalpha",
    f"({NEGATION_PREFIX}{TRASH_OPERATOR}) zzalpha",
    "from:nobody@parts.example zzalpha",
    "subject:zzalpha zzbeta",
    '"zzalpha zzbeta here"',
    "newer_than:2d zzalpha",
    "thread:1837abf",
    "zzalpha -zzbeta",
)


def test_a_zero_evidence_response_offers_nothing_only_when_nothing_would_help() -> None:
    """The half of ROUTE-01 that a percentage cannot state (R-RETR-040).

    "100% of zero-evidence responses carry affordances" is unmeetable as written and R-RETR
    measured 11.3%; minting something for the rest is what R-RETR-023 removed, because an offer
    that changes nothing is a promise the response cannot keep. So the property asserted here is
    the one that has content: a response carries an offer **unless** there is no call to make -
    every untried drop is one the rung refuses at any budget, and the query named no region that
    could be dropped without undoing an exclusion.

    Every offer that carries a query is executed, and the response's own diagnosis must agree
    with the envelope: an affordance in one and not the other is two statements about one fact.
    """
    zero, offered, silent = 0, 0, []
    for query in ZERO_EVIDENCE_SHAPES:
        _box, envelope = answer(query, spread())
        if rows(envelope):
            continue
        zero += 1
        diagnosis = envelope.retrieval_report.empty_diagnosis
        offers = list(envelope.affordances)
        if diagnosis is not None and diagnosis.affordance is not None:
            offers.append(diagnosis.affordance)
        if offers:
            offered += 1
            for offer in offers:
                follow_up = offer.args.get("query")
                if follow_up is None:
                    continue
                assert isinstance(follow_up, str)
                next_box, _next = answer(str(follow_up), spread())
                assert next_box.queries, (query, follow_up)
            continue
        # No offer: prove there was none to make. Two things must hold, and between them they
        # are the whole of "nothing would help": no drop the response reports as untried is one
        # a probe could reach at any budget, and the query named no region that could be
        # dropped without undoing an exclusion.
        silent.append(query)
        parsed = parse(query)
        untried = () if diagnosis is None else diagnosis.untried_drops
        assert not set(untried) & set(RelaxationRung().plannable_drops(parsed)), query
        assert without_the_region_it_named(parsed) is None, query
        # The report class's own offers either do not exist for this query or name the very
        # query the ladder already executed, which is the "changes nothing" R-RETR-023 removed
        # rather than a missing affordance.
        for offer in report_affordances(parsed):
            assert offer.args == {"query": parsed.render()}, (query, offer.args)
    assert zero >= 15, zero
    assert offered, "the sweep is not vacuous"
    assert silent, "the silent class is real and is asserted rather than assumed"


def test_the_ladder_still_broadens_a_query_that_named_no_region_at_all() -> None:
    """A9-A3: the published step survives every narrowing above (OD-5 point 2).

    Asserted beside them because "no probe enters a region the query excluded" is trivially
    satisfiable by never leaving the inbox, and that would remove the recovery this project
    exists to provide.
    """
    box, envelope = answer(HIDDEN)
    assert any(flag for _q, flag in box.queries), box.queries
    found = {row.id: row.mailbox.regions for row in rows(envelope) if row.role is Role.MATCHED}
    assert found == {"q-sp": ("spam",), "q-tr": ("trash",)}
    assert envelope.retrieval_report.outcome.value == "answered"
    assert RungId.L3 in envelope.retrieval_report.rungs

    unscoped = BroadeningRung().plan(parse(f"is:unread {MARKER}"))
    assert [probe.query for probe in unscoped] == [f"{ANYWHERE_OPERATOR} {MARKER}"]
    assert len(LADDER) == 5
