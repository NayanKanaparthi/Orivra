"""Round 18, end to end: the region a query named, and the region a row came from.

Four behaviours are asserted here against the whole client-and-ladder stack, with an
`httpx.MockTransport` where the socket would be, because each of them was reported as a
*disclosure* rather than as a plan: what reached the wire was only half the finding, and the
other half was what the response then said about the rows.

  * **A query that declared a region is answered inside it** (OD-5 points 2 and 3, A9-A2,
    R-RETR-026). A negated location is the region declaration, not a filter inside one, so no
    probe of any rung may drop it and no rung may widen out of it.
  * **Every disclosed row states the region its own labels put it in** (OD-5 point 1, A9-A1).
    Derived from `labelIds`, never from the `q` that found the row.
  * **A negated phrase is excluded, not searched for** (R-RETR-027).
  * **A route enforces only what its own `q` carried whole** (R-RETR-028), at L0 as at every
    other rung.

The plan-layer sweeps live in `tests/test_lexical_ladder.py` beside the invariant they
enforce; the replants that make each of these fail when it is removed live in
`tests/test_replants.py`.

No fixture here carries real or realistic mail: every address is in the reserved `.example`
or `.invalid` TLDs (RFC 2606/6761) and every subject and body is invented for the structural
property the test is about.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from mailweave.constants import (
    ANYWHERE_OPERATOR,
    MAILBOX_LOCATION_PREFIX,
    REGION_LABEL_BY_OPERATOR,
    WIDENING_MAILBOX_OPERATORS,
    matchable_content_of,
    region_name,
)
from mailweave.envelope.disposition import DispositionLedger
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import Role
from mailweave.envelope.wire import MailboxProvenance, MessageRow
from mailweave.gmail import BackoffPolicy, CallMeter, GmailClient, StaticToken
from mailweave.net.egress import build_client
from mailweave.query import analyse
from mailweave.retrieval.assemble import assemble, report_affordances
from mailweave.retrieval.ladder import LadderRunner
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.test_lexical_ladder import NARROWING_MAILBOX_LOCATIONS

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
UTC_ZONE = ZoneInfo("UTC")
TOKEN = "ya29.SECRET-ACCESS-TOKEN-NEVER-IN-A-ROUND-18-FIXTURE"

#: One invented word, present in exactly one message per region. A query for it therefore
#: distinguishes the regions by which rows come back, which is what every assertion below
#: turns on.
MARKER = "borogrove"

#: A phrase present in exactly one message and in no other. Three content tokens, which is
#: A.8a branch E-b's published bar, so the negated form exercises the branch as well as the
#: constraint.
PHRASE = "quadrant notice zephyr"

#: A colon-carrying phrase, present in exactly one message. Round 17's Part-2 fix is what
#: newly routed this spelling into the path that discarded polarity, so it is asserted beside
#: the colon-free one rather than trusted to behave like it (R-RETR-027).
COLON_PHRASE = "Re: quadrant notice"

#: A word present **only** outside the default mailbox, so a query for it finds nothing until
#: A.7 L3's published step runs. Without it the broadening never fires and a test that claims
#: to exercise it would be asserting over a run that did not.
HIDDEN = "grimble"


def spread_mailbox() -> SyntheticMailbox:
    """One marker word in the inbox, in spam and in trash, plus unrelated filler.

    Three regions and one word is the whole design: any probe that leaves the region the
    query named shows up as an extra row, and the row says which region it came from.
    """
    return SyntheticMailbox(
        messages=(
            Msg(
                id="r-in",
                thread_id="t-in",
                sender="ops@team.example",
                subject="Programme note",
                body=f"The {MARKER} entry is on the agenda.",
                internal_date_ms=epoch_ms(2026, 6, 3),
                labels=("INBOX", "UNREAD"),
            ),
            Msg(
                id="r-sp",
                thread_id="t-sp",
                sender="bulk@parts.invalid",
                subject="Offer",
                body=f"A {MARKER} offer nobody asked for, filed under {HIDDEN}.",
                internal_date_ms=epoch_ms(2026, 6, 4),
                labels=("SPAM",),
            ),
            Msg(
                id="r-tr",
                thread_id="t-tr",
                sender="old@parts.invalid",
                subject="Discarded",
                body=f"A discarded {MARKER} note about {HIDDEN}.",
                internal_date_ms=epoch_ms(2026, 6, 5),
                labels=("TRASH",),
            ),
            Msg(
                id="r-ph",
                thread_id="t-ph",
                sender="qa@team.example",
                subject="Notice",
                body=f"The {PHRASE} is recorded here and nowhere else.",
                internal_date_ms=epoch_ms(2026, 6, 6),
                labels=("INBOX",),
            ),
            Msg(
                id="r-cl",
                thread_id="t-cl",
                sender="qa@team.example",
                subject="Reply notice",
                body=f"{COLON_PHRASE} was filed, and zephyr with it.",
                internal_date_ms=epoch_ms(2026, 6, 7),
                labels=("INBOX",),
            ),
            Msg(
                id="r-no",
                thread_id="t-no",
                sender="qa@team.example",
                subject="Other notice",
                body="A note carrying zephyr and nothing else of interest.",
                internal_date_ms=epoch_ms(2026, 6, 7),
                labels=("INBOX",),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )


def answer(query: str, box: SyntheticMailbox | None = None) -> tuple[SyntheticMailbox, Envelope]:
    box = spread_mailbox() if box is None else box
    client = GmailClient(
        token=StaticToken(TOKEN),
        http=build_client(inner=box.transport()),
        meter=CallMeter(),
        policy=BackoffPolicy(),
        sleeper=lambda _seconds: None,
        jitterer=lambda: 0.5,
    )
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run(query, now=NOW, zone=UTC_ZONE)
    return box, assemble(run, client=client, ledger=ledger)


def rows(envelope: Envelope) -> list[MessageRow]:
    return [row for source in envelope.sources for row in source.messages]


def matched(envelope: Envelope) -> list[MessageRow]:
    return [row for row in rows(envelope) if row.role is Role.MATCHED]


# --- Part 1: the region the query named --------------------------------------------------


def test_a_query_that_excluded_a_region_never_reads_it_and_never_discloses_a_row_from_it() -> None:
    """`-in:spam` never searches spam, and the sweep is over the location family.

    **The finding this closes, measured end to end** (R-RETR-026). A query excluding the spam
    mailbox reached the widening operator with `includeSpamTrash=true`, and the spam message
    the caller had ruled out came back `role: matched` under `outcome: answered`. The drop was
    declared, so the response did not lie about the *constraint* - it returned, as matches,
    exactly the messages the query excluded, which is the exit condition's other half.

    Three assertions, and they are three different ways of being wrong:

      * no request sets `includeSpamTrash` unless the caller's own query widened;
      * no `q` on the wire drops the exclusion the caller wrote;
      * no disclosed row - matched **or** stub - comes from a region the caller excluded.

    The third is the one the schema change makes checkable at all: before `MessageRow.mailbox`
    it could only be asked of the fixture, by knowing which ids were planted where.
    """
    for location in (
        *NARROWING_MAILBOX_LOCATIONS,
        *(region_name(o) for o in WIDENING_MAILBOX_OPERATORS),
    ):
        fragment = f"-{MAILBOX_LOCATION_PREFIX}{location}"
        box, envelope = answer(f"{fragment} {MARKER}")
        excluded = region_name(fragment)
        assert [flag for _q, flag in box.queries] == [False] * len(box.queries), (fragment,)
        assert all(fragment in q for q, _flag in box.queries), (fragment, box.queries)
        for row in rows(envelope):
            assert row.mailbox.regions is not None, (fragment, row.id)
            assert excluded not in row.mailbox.regions, (fragment, row.id, row.mailbox.regions)


def test_a_query_that_named_a_region_positively_is_answered_inside_it() -> None:
    """The other polarity, and it is the same rule (OD-5 point 2).

    `in:spam <marker>` is a caller asking about spam. It is answered from spam - so the flag
    *is* set, and it is set because the caller's own query widened - and no rung replaces the
    region with the whole mailbox, which would answer a question the caller did not ask.
    """
    box, envelope = answer(f"{WIDENING_MAILBOX_OPERATORS[1]} {MARKER}")
    assert all(flag for _q, flag in box.queries), box.queries
    assert [row.id for row in matched(envelope)] == ["r-sp"]
    assert matched(envelope)[0].mailbox.regions == ("spam",)
    assert not any(q.startswith(ANYWHERE_OPERATOR) for q, _flag in box.queries), box.queries

    _box, inbox_scoped = answer(f"{MAILBOX_LOCATION_PREFIX}inbox {MARKER}")
    assert [row.id for row in matched(inbox_scoped)] == ["r-in"]
    assert matched(inbox_scoped)[0].mailbox.regions == ()


def test_the_published_broadening_still_reaches_spam_when_no_region_was_named() -> None:
    """A.7 L3's step survives, and the rows it admits say where they came from (A9-A3).

    R-RETR's reasoned verdict was to keep this step: it fires only after the default mailbox
    has returned nothing, spam and trash are the caller's own mailbox, and "we found nothing"
    over a message sitting in the caller's spam folder is the false negative this project
    exists to remove. What was missing is the row-level disclosure, and that is what is
    asserted here beside it: the response is `answered`, the rows are `matched`, and each one
    states the region it is in without a reader parsing a reason string.
    """
    box, envelope = answer(HIDDEN)
    assert any(flag for _q, flag in box.queries), box.queries
    found = {row.id: row.mailbox.regions for row in matched(envelope)}
    assert found == {"r-sp": ("spam",), "r-tr": ("trash",)}
    outside = [row.id for row in matched(envelope) if row.mailbox.outside_the_default_mailbox]
    assert sorted(outside) == ["r-sp", "r-tr"]
    assert envelope.retrieval_report.outcome.value == "answered"


# --- Part 0: provenance is a field, derived from the labels -------------------------------


def test_every_disclosed_row_states_the_region_its_own_labels_place_it_in() -> None:
    """`MessageRow.mailbox` is a projection of `labelIds`, and of nothing else (OD-5 point 1).

    The claim has to be checkable against the response rather than against the fixture, so
    both halves are asserted: the labels the row reports are the labels the mailbox holds, and
    the regions are `mailbox_regions_of` of exactly those labels. A provenance computed any
    other way - from the `q`, from the `includeSpamTrash` flag, from the rung - would pass a
    test that only checked the regions.
    """
    box, envelope = answer(HIDDEN)
    holdings = {message.id: message.labels for message in box.messages}
    # **The oracle is written out, not computed by the function under test.** Asserting
    # `row.mailbox.regions == mailbox_regions_of(row.mailbox.labels)` is a tautology: emptying
    # the derivation satisfies both sides at once, which the replant harness proved by
    # planting exactly that and finding this test green (R10). The expected value for each
    # planted id is therefore stated here, and `mailbox_regions_of` is checked separately,
    # against the label vocabulary, in
    # `test_a_provenance_cannot_state_a_region_its_labels_do_not_carry`.
    expected = {"r-in": (), "r-sp": ("spam",), "r-tr": ("trash",), "r-ph": (), "r-no": ()}
    disclosed = rows(envelope)
    assert disclosed, "the sweep is not vacuous"
    assert {row.id for row in disclosed} & {"r-sp", "r-tr"}, [row.id for row in disclosed]
    for row in disclosed:
        assert row.mailbox.observed is True, row.id
        assert row.mailbox.labels == holdings[row.id], row.id
        assert row.mailbox.regions == expected[row.id], row.id
        assert row.mailbox.outside_the_default_mailbox == bool(expected[row.id]), row.id


def test_a_rows_provenance_does_not_change_with_the_query_that_found_it() -> None:
    """The same message, found three ways, reports one provenance.

    This is the property that separates "derived from what was observed" from "derived from
    the caller", and it is the only one that fails for *every* wrong derivation at once: a
    provenance read off the probe's `includeSpamTrash`, off the rung, or off the `q` all
    change when the query does, and the labels do not.
    """
    seen = []
    for query in (
        HIDDEN,
        f"{WIDENING_MAILBOX_OPERATORS[1]} {MARKER}",
        f"{ANYWHERE_OPERATOR} {MARKER}",
    ):
        _box, envelope = answer(query)
        row = next(r for r in rows(envelope) if r.id == "r-sp")
        seen.append(row.mailbox.model_dump(mode="json"))
    assert seen[0] == seen[1] == seen[2]
    assert seen[0]["regions"] == ["spam"]


def test_a_provenance_cannot_state_a_region_its_labels_do_not_carry() -> None:
    """`regions` is computed, so there is no place to put a value that disagrees.

    The structural half of OD-5 point 1: the model refuses `regions` as an input, which is why
    "derived from the observed labels" is a property of the type rather than a convention the
    one producer happens to follow.
    """
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MailboxProvenance.model_validate({"observed": True, "labels": [], "regions": ["spam"]})
    with pytest.raises(ValidationError):
        MailboxProvenance(observed=False, labels=("SPAM",))
    # **The third state is an absence, not an empty set** (round 19, R-RETR-039). `()` would
    # be the claim "these labels place the message in neither region", which needs labels.
    assert MailboxProvenance.unobserved().regions is None
    assert MailboxProvenance.unobserved().outside_the_default_mailbox is None
    for operator, label in REGION_LABEL_BY_OPERATOR.items():
        assert MailboxProvenance.of((label,)).regions == (region_name(operator),)


def test_the_region_label_vocabulary_is_the_widening_operator_vocabulary() -> None:
    """One region vocabulary, two spellings, checked rather than trusted (R-ARCH-031).

    A region added to the operator table and forgotten in the label table would make every
    row from it report no provenance while every probe about it worked, which is the quietest
    possible version of this round's finding.
    """
    assert set(REGION_LABEL_BY_OPERATOR) == set(WIDENING_MAILBOX_OPERATORS) - {ANYWHERE_OPERATOR}
    assert all(label.isupper() for label in REGION_LABEL_BY_OPERATOR.values())


# --- Part 2: a negated phrase is an exclusion --------------------------------------------


def test_a_negated_phrase_is_excluded_rather_than_searched_for() -> None:
    """R-RETR-027, end to end and in both spellings.

    The colon-free form was wrong before round 17 and the colon-carrying form became wrong
    *because* of round 17's own fix, which newly routed it into the path that discarded
    polarity. Both are asserted, because asserting one and trusting the other is the shape
    that produced this finding.
    """
    for written, carrier in ((PHRASE, "r-ph"), (COLON_PHRASE, "r-cl")):
        query = f'-"{written}" zephyr'
        _box, envelope = answer(query)
        found = {row.id for row in matched(envelope)}
        assert carrier not in found, (query, found)
        assert "r-no" in found, (query, found)
        parsed = analyse(query, now=NOW, zone=UTC_ZONE)
        assert parsed.render().startswith("-"), query
        assert parsed.excluded_phrases == (written,) and parsed.phrases == (), query

    # The positive form still matches the one message that has the phrase.
    _box, positive = answer(f'"{PHRASE}"')
    assert [row.id for row in matched(positive)] == ["r-ph"]


# --- Part 3: enforcement is what the executed q carried ----------------------------------


def test_a_route_that_executed_one_fragment_does_not_report_the_constraint_enforced() -> None:
    """R-RETR-028 at L0, where D.3 rule 1b then freezes whatever the rung claimed.

    The stop is the reason this one mattered more than its siblings: rule 1b halts the ladder,
    so no later rung can correct the claim, and the response shipped `term_coverage 1.0` and
    `sufficiency: sufficient` over a row satisfying part of the query. The claim now falls with
    the coverage, and the row's own `constraint_coverage` falls with it.
    """
    box = SyntheticMailbox(
        messages=(
            Msg(
                id="i-1",
                thread_id="t-id",
                sender="proc@team.example",
                subject="Order",
                body="Reference PO-2026-0041 was raised against the framework.",
                internal_date_ms=epoch_ms(2026, 3, 2),
                labels=("INBOX",),
            ),
            Msg(
                id="i-2",
                thread_id="t-other",
                sender="qa@team.example",
                subject="Unrelated",
                body="A note carrying zephyr and nothing else.",
                internal_date_ms=epoch_ms(2026, 3, 3),
                labels=("INBOX",),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )
    _box, envelope = answer("PO-2026-0041 zephyr", box)
    assert [q for q, _flag in _box.queries] == ['"PO-2026-0041"']
    assert envelope.asked_for.enforced == ()
    assert envelope.asked_for.term_coverage == 0.0
    assert [d.constraint for d in envelope.asked_for.dropped] == ["terms"]
    assert [(row.id, row.constraint_coverage) for row in matched(envelope)] == [("i-1", ())]

    # The control: when the identifier **is** the whole constraint, the claim stands.
    _box2, whole = answer("PO-2026-0041", box)
    assert whole.asked_for.enforced == ("terms",)
    assert whole.asked_for.term_coverage == 1.0
    assert [(row.id, row.constraint_coverage) for row in matched(whole)] == [("i-1", ("terms",))]


# --- Part 5: a zero-evidence report offers the call that would reach a rung ---------------


def test_a_zero_evidence_report_offers_the_call_that_would_reach_a_rung() -> None:
    """R-RETR-032, and the offer is executed rather than asserted to exist.

    ROUTE-01's acceptance enumerates five things and the fifth is affordances; over every
    zero-evidence response the reviewer produced, `envelope.affordances` was `[]` and
    `empty_diagnosis.affordance` was `None`, including for the report class whose whole
    purpose is to say what to do instead. AD-03 requires an affordance to be a concrete call
    that would reach the untried rung, so this test **runs each offered call** and asserts it
    reaches Gmail - which is the difference between an affordance and a suggestion.
    """
    for query in ("thread:1837abf", "(zephyr OR borogrove)", "{zephyr borogrove}"):
        box, envelope = answer(query)
        assert box.queries == [], query
        offers = envelope.affordances
        assert offers, query
        diagnosis = envelope.retrieval_report.empty_diagnosis
        assert diagnosis is not None and diagnosis.affordance is not None, query
        for offer in offers:
            follow_up = offer.args["query"]
            assert isinstance(follow_up, str)
            next_box, _next_envelope = answer(follow_up)
            assert next_box.queries, (query, follow_up)


def test_a_report_with_nothing_to_offer_offers_nothing() -> None:
    """R-RETR-023's rule survives: an offer that changes nothing is not minted.

    The class this round added an offer for and the class it deliberately did not are asserted
    together, because "always mint something" is the defect the previous round removed.
    """
    for query in ('""', "the and of", "?", "subject:", "subject:''"):
        parsed = analyse(query, now=NOW, zone=UTC_ZONE)
        assert report_affordances(parsed) == (), query

    # **A query naming only where to look is one of them, since round 19** (R-RETR-040). It
    # used to be offered the same refused query with an empty `terms` slot beside it, which
    # reaches no rung and sends no request - a promise of recoverability the response cannot
    # keep, which contract I-4 counts as worse than offering none. The only call that helps
    # is a different question and MailWeave does not invent one.
    scoped = analyse(ANYWHERE_OPERATOR, now=NOW, zone=UTC_ZONE)
    assert report_affordances(scoped) == ()


# --- the residue this round narrowed, stated as a test ------------------------------------


def test_a_token_of_marks_controls_or_separators_names_nothing_to_match() -> None:
    """R-RETR-029's derivable half, executed over a generated family rather than a list.

    Round 17 removed exactly one Unicode general category and its docstring called that "a
    structural question ... what, once everything that is not content is removed, is left for
    Gmail to match?". The categories are now asked of the runtime one by one, and the family
    is generated by sweeping the BMP for members of each rather than by naming code points -
    so a character the standard adds is covered without an edit.

    **The residue is asserted as residue, not glossed.** `Default_Ignorable_Code_Point` is not
    exposed by `unicodedata` in this runtime, so U+3164 HANGUL FILLER - which NFKC-folds to a
    category `Lo` character - is still content. That is executed here as a *known* value, so
    the day it changes this test says so rather than a review finding it again.
    """
    import unicodedata

    from mailweave.constants import NON_MATCHING_CHARACTER_CATEGORIES

    swept: dict[str, int] = {}
    for code in range(0x0000, 0x10000):
        character = chr(code)
        category = unicodedata.category(character)
        if category not in NON_MATCHING_CHARACTER_CATEGORIES:
            continue
        swept[category] = swept.get(category, 0) + 1
        assert matchable_content_of(character) == "", (hex(code), category)
        assert matchable_content_of(f"-{character}") == "", (hex(code), category)
        assert matchable_content_of(f'"{character}"') == "", (hex(code), category)
    assert set(swept) >= {"Cc", "Cf", "Cn", "Co", "Cs", "Mn", "Zs"}, swept
    assert sum(swept.values()) > 1000, swept

    # A character with content is still content, in the same sweep's vocabulary.
    assert matchable_content_of("a") == "a"
    assert matchable_content_of("é") == "é"

    # The named residue, executed rather than described.
    assert matchable_content_of("ㅤ") != ""
    assert matchable_content_of("⠀") != ""


def test_a_negated_operator_with_a_quoted_value_is_not_a_probe_of_its_own() -> None:
    """One tokenisation, read by the parser and by the predicate family (round 18).

    **My own finding, and it is this round's instance of the shape it was sent to fix.**
    `carries_nothing_to_select_by('-from:x')` was `True`, so a negated participant was
    correctly refused as a decomposition probe of its own; the same predicate split
    `-from:"Amy Smith"` on whitespace into `-from:"Amy` and `Smith"`, found no negation on the
    second piece, and returned `False`. So the identical constraint, written with a value that
    happens to contain a space, became an L1b unit whose `q` asks Gmail for the whole mailbox
    minus one sender - R-RETR-006's shape, through the spelling nobody checked.

    `constants.query_tokens` is now the one splitter and `query.operators.tokenise` reads it,
    so the parser and the predicates cannot disagree about how many tokens a fragment is. The
    sweep is over the operator family in both polarities, with a quoted multi-word value,
    because a fix asserted on `from:` alone would be the same defect again.
    """
    from mailweave.query import OperatorName, carries_nothing_to_select_by
    from mailweave.query.analysis import decomposition_units_of, selects_something

    for operator in OperatorName:
        fragment = f'-{operator.value}:"two words"'
        assert carries_nothing_to_select_by(fragment), fragment
        assert not selects_something(fragment), fragment
        parsed = analyse(f"{fragment} rollout", now=NOW, zone=UTC_ZONE)
        units = decomposition_units_of(parsed.constraints)
        # Never a unit of its own. A *region* declaration is still carried onto every unit -
        # that is the asymmetry rule, and it is the opposite question from this one.
        assert all(unit.fragment != fragment for unit in units), (fragment, units)
    # The positive form still selects, so the fix narrows nothing it should not.
    assert selects_something('from:"two words"')


def test_a_calendar_invalid_date_is_carried_to_gmail_and_the_double_does_not_crash() -> None:
    """R-RETR-033: the double raised where MailWeave is deliberately silent.

    A.6a has MailWeave carry a date it cannot resolve into a window unchanged and let Gmail
    judge it - `parsed.window is None`, the fragment goes onto the wire, and the ladder plans
    around it. The test double matched the *shape* of a date and then called `datetime`, which
    raises for month 13, so an ordinary typo crashed every end-to-end harness that uses it and
    no end-to-end statement about this documented case was establishable by anyone. The
    double now answers "I cannot judge this value", which is what it already answers for a
    value whose shape it does not recognise.
    """
    for written in ("after:2026/13/45", "before:2026/02/31", "after:0000/01/01"):
        parsed = analyse(f"{written} zephyr", now=NOW, zone=UTC_ZONE)
        assert parsed.window is None, written
        box, envelope = answer(f"{written} zephyr")
        assert any(written in q for q, _flag in box.queries), (written, box.queries)
        assert envelope.retrieval_report.outcome.value in {"answered", "inconclusive"}, written


# --- the unasserted-fix sweep's two findings, closed -------------------------------------


def test_a_constraint_whose_pieces_the_cap_never_probed_is_not_reported_enforced() -> None:
    """R-RETR-024(c)'s fix was **unasserted**, and this is round 18's sweep finding it.

    `_decomposition_enforced` credits a constraint to the L1b rung only when *every* unit of
    it was probed. With more units than `MAX_DECOMPOSITION_PROBES` the cap cuts the plan
    short, so the intersection is a superset of the true one and a thread carrying no message
    with the fourth word is disclosed - which is the documented precision cost of the cap.
    What round 17 fixed is that the response stopped reporting the constraint enforced over
    it. Nothing asserted that: planting the clause out left the whole suite green
    (round 18's sweep, S7).

    Four bare words is the smallest shape that reaches it: four units, three probes, one word
    never sent. The response must not claim `terms`, and the thread must still be recovered -
    both halves, because a fix that closed the claim by losing the recall would satisfy an
    assertion about the claim alone.
    """
    from mailweave.constants import MAX_DECOMPOSITION_PROBES

    words = ("rollout", "cutover", "handover", "vendor")
    assert len(words) > MAX_DECOMPOSITION_PROBES
    box = SyntheticMailbox(
        messages=tuple(
            Msg(
                id=f"c-{index}",
                thread_id="t-cap",
                sender="ops@team.example",
                subject=f"Part {index}",
                body=f"This message carries {word} and nothing else of interest.",
                internal_date_ms=epoch_ms(2026, 4, index + 1),
                labels=("INBOX",),
            )
            for index, word in enumerate(words)
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )
    _box, envelope = answer(" ".join(words), box)
    assert [source.thread_id for source in envelope.sources] == ["t-cap"], "still recovered"
    assert envelope.asked_for.enforced == (), envelope.asked_for.enforced
    assert envelope.asked_for.term_coverage == 0.0
    assert all(row.constraint_coverage == () for row in matched(envelope))


def test_a_row_never_names_a_constraint_the_parse_did_not_produce() -> None:
    """R-DISC-006's filter, executed directly because nothing reaches it end to end.

    `constraint_coverage_of` filters the admitting probe's `enforced` list down to names the
    parse produced, so a row can never claim a constraint the caller did not write. Round 18's
    sweep planted the filter out and the whole suite stayed green (S12) - and the reason is
    honest rather than alarming: since every rung now derives `enforced` from
    `constraints_carried_whole` over `parsed.constraints`, a foreign name has no reachable
    producer. The guard is defence in depth, so it is executed **at the function** rather than
    left as a clause with no test, which is the shape round 17 disclosed for its own P2 and
    which a later change to any rung could quietly make reachable again.
    """
    from mailweave.retrieval.signals import constraint_coverage_of

    parsed = analyse("from:ana@team.example rollout", now=NOW, zone=UTC_ZONE)
    known = {constraint.name for constraint in parsed.constraints}
    assert known == {"from", "terms"}
    assert constraint_coverage_of(
        parsed, admitted_by={"m1": ("from", "label", "terms")}, message_id="m1"
    ) == ("from", "terms")
    assert constraint_coverage_of(parsed, admitted_by={"m1": ("label",)}, message_id="m1") == ()
    assert constraint_coverage_of(parsed, admitted_by={}, message_id="m1") == ()
