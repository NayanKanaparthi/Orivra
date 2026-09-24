"""WS-04 query analysis: the operator-parse fidelity table, and everything around it.

The plan's acceptance column asks for an **operator-parse fidelity table**: "every operator
MailWeave claims to parse, parsed". The claim is `OperatorName`, so the table below is
`parametrize`d over that enum and
`test_the_fidelity_table_covers_every_operator_the_lexicon_claims` fails if a member is
added without a row. That is the difference between a table that tests the operators
somebody remembered and one that tests the claim.

Two further properties are asserted over the *whole* table rather than per row, because
"one shape validated, peers trusted" is this project's recurring defect and a per-row
assertion is exactly that shape:

  * every token of every case is classified into exactly one `TokenRole` (nothing vanishes);
  * every parsed operator reaches L1's executed `q` in its Gmail spelling (parse fidelity is
    a statement about what is *sent*, not about a dataclass).

No case here contains real or realistic personal mail: addresses use the reserved `.example`
/ `.invalid` TLDs and every subject and body is invented.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from mailweave.constants import (
    DATE_MARGIN_DAYS,
    WIDENING_MAILBOX_OPERATORS,
    max_relax_probes,
)
from mailweave.query import (
    ANSWER_TYPE_BY_INTERROGATIVE,
    RELATIVE_EXPRESSIONS,
    RISK_FACTORS,
    STOPWORDS,
    AnswerType,
    ConfidenceTier,
    Interrogative,
    OperatorKind,
    OperatorName,
    ParsedQuery,
    TokenRole,
    analyse,
    classify_interrogative,
    dropped_declarations,
    enforced_declarations,
    matches_answer_type,
    normalise_participant,
    reference_zone,
    tokenise,
)
from mailweave.query.analysis import (
    RELAXATION_ORDER,
    ConstraintUnit,
    decomposition_units_of,
    selects_something,
)
from mailweave.query.operators import KIND_BY_OPERATOR
from mailweave.retrieval.ladder import DecompositionRung, FilteredRung, RelaxationRung

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
UTC_ZONE = ZoneInfo("UTC")


def parse(query: str, *, zone: ZoneInfo = UTC_ZONE) -> ParsedQuery:
    return analyse(query, now=NOW, zone=zone)


#: One row per documented operator: the query as a user would write it, and the value the
#: parse must recover. Values are shaped like the real thing and named from the reserved
#: test TLDs; none of them is anybody's mail.
FIDELITY_TABLE: dict[OperatorName, tuple[str, str]] = {
    OperatorName.FROM: ("from:ana@team.example", "ana@team.example"),
    OperatorName.TO: ("to:bo@team.example", "bo@team.example"),
    OperatorName.CC: ("cc:cy@team.example", "cy@team.example"),
    OperatorName.BCC: ("bcc:di@team.example", "di@team.example"),
    OperatorName.DELIVEREDTO: ("deliveredto:ops@team.example", "ops@team.example"),
    OperatorName.SUBJECT: ('subject:"rollout window"', "rollout window"),
    OperatorName.AFTER: ("after:2026/05/01", "2026/05/01"),
    OperatorName.BEFORE: ("before:2026/06/01", "2026/06/01"),
    OperatorName.OLDER_THAN: ("older_than:2d", "2d"),
    OperatorName.NEWER_THAN: ("newer_than:7d", "7d"),
    OperatorName.LABEL: ("label:vendors", "vendors"),
    OperatorName.CATEGORY: ("category:updates", "updates"),
    OperatorName.IN: ("in:inbox", "inbox"),
    OperatorName.IS: ("is:unread", "unread"),
    OperatorName.HAS: ("has:attachment", "attachment"),
    OperatorName.LIST: ("list:announce.team.example", "announce.team.example"),
    OperatorName.FILENAME: ("filename:report.pdf", "report.pdf"),
    OperatorName.SIZE: ("size:1000000", "1000000"),
    OperatorName.LARGER: ("larger:5M", "5M"),
    OperatorName.SMALLER: ("smaller:2M", "2M"),
    OperatorName.RFC822MSGID: ("rfc822msgid:<a1@mail.invalid>", "<a1@mail.invalid>"),
}


def test_the_fidelity_table_covers_every_operator_the_lexicon_claims() -> None:
    """The table is bound to the claim, not to what its author happened to think of."""
    assert set(FIDELITY_TABLE) == set(OperatorName)
    assert len(FIDELITY_TABLE) == 21


@pytest.mark.parametrize("operator", list(OperatorName), ids=lambda o: o.value)
def test_every_documented_operator_parses_to_its_name_and_value(operator: OperatorName) -> None:
    written, expected = FIDELITY_TABLE[operator]
    parsed = analyse(written, now=NOW, zone=UTC_ZONE)

    assert [o.name for o in parsed.operators] == [operator]
    assert parsed.operators[0].value == expected
    assert parsed.terms == ()
    assert parsed.unknown_operators == ()


@pytest.mark.parametrize("operator", list(OperatorName), ids=lambda o: o.value)
def test_every_parsed_operator_reaches_the_executed_query(operator: OperatorName) -> None:
    """Fidelity is a statement about what is sent, so it is asserted on L1's own `q`.

    A parse that produced the right dataclass and a `q` that lost the operator would pass a
    parse-only table and fail the user; this is the same table read at the wire.
    """
    written, _ = FIDELITY_TABLE[operator]
    parsed = analyse(written, now=NOW, zone=UTC_ZONE)

    planned = FilteredRung().plan(parsed)

    assert len(planned) == 1
    assert parsed.operators[0].render() in planned[0].query


@pytest.mark.parametrize("operator", list(OperatorName), ids=lambda o: o.value)
def test_every_operator_has_exactly_one_kind(operator: OperatorName) -> None:
    assert isinstance(KIND_BY_OPERATOR[operator], OperatorKind)


def test_the_kind_map_is_total_over_the_lexicon() -> None:
    assert set(KIND_BY_OPERATOR) == set(OperatorName)


def test_every_token_of_every_fidelity_case_is_classified_exactly_once() -> None:
    """Nothing may vanish in tokenising: a lost token is a silently dropped signal (LEX-02)."""
    for written, _ in FIDELITY_TABLE.values():
        tokens = tokenise(written)
        for token in tokens:
            assert isinstance(token.role, TokenRole)
        # Reconstruction rather than a token count: a quoted value is deliberately one
        # token, so counting whitespace-separated words would assert the wrong thing. What
        # must hold is that the query can be rebuilt from the classification.
        assert " ".join(token.text for token in tokens) == " ".join(written.split())


def test_a_negated_operator_keeps_its_polarity_through_the_render() -> None:
    parsed = parse("-label:vendors rollout")

    assert parsed.operators[0].negated is True
    assert parsed.operators[0].render() == "-label:vendors"
    assert "-label:vendors" in parsed.render()


def test_an_operator_value_with_whitespace_is_requoted_on_the_wire() -> None:
    """An unquoted multi-word value would become two tokens, one of them a free-text term."""
    parsed = parse('from:"Ana Example"')

    assert parsed.operators[0].value == "Ana Example"
    assert parsed.render() == 'from:"Ana Example"'


def test_an_operator_mailweave_cannot_prove_is_declared_and_not_executed() -> None:
    """LEX-02, on the token class that used to reach the wire unaccounted for (R-RETR-012).

    A `name:value` token outside Gmail's documented set is not an operator here. It used to
    stay a residual term - so it was **conjoined into the executed `q`**, where it can only
    narrow the search on a meaning nobody established - and it appeared in no part of
    `asked_for`: not as an operator, not as a term, not as a drop, with `term_coverage`
    reporting 1.0. The rule this parser already applies to a boolean it cannot regroup is
    the one it now applies here: do not execute what you cannot account for, and say so.
    """
    parsed = parse("thread:abc rollout")

    assert parsed.operators == ()
    assert parsed.unknown_operators == ("thread:abc",)
    assert "thread:abc" not in parsed.render()
    assert parsed.render() == "rollout"

    declared = dict(dropped_declarations(parsed))
    assert "unproven_operator" in declared
    assert "thread:abc" in declared["unproven_operator"]
    # ...and the coverage number moves with it, which is the half a declaration alone misses.
    assert parsed.term_coverage(parsed.constraints) == 0.5


def test_an_undocumented_operator_is_not_invented_as_one() -> None:
    """LEX-02: "operators used are limited to Gmail's documented set" (RO F3)."""
    parsed = parse("thread:abc rollout")

    assert parsed.operators == ()
    assert [name.value for name in OperatorName if name.value == "thread"] == []
    assert parsed.unknown_operators == ("thread:abc",)


def test_boolean_syntax_is_declared_dropped_rather_than_re_emitted_somewhere_else() -> None:
    """The one thing the parser gives up, named where it is given up (LEX-02)."""
    parsed = parse("rollout OR fallback")

    assert parsed.passthrough == ("OR",)
    assert "OR" not in parsed.render().split()
    declared = dropped_declarations(parsed)
    assert [name for name, _ in declared] == ["unparsed_syntax"]
    assert "OR" in declared[0][1]


def test_a_stopword_is_removed_from_the_wire_and_named_in_enforced() -> None:
    """Gmail's `q` is a conjunction, so an un-removed "the" is a false negative waiting."""
    parsed = parse("what did we decide about the rollout")

    assert "the" in {word for word in parsed.terms if word in STOPWORDS}
    assert "the" not in parsed.render().split()
    declared = enforced_declarations(parsed, parsed.constraints)
    assert any(entry.startswith("stopwords_removed:") for entry in declared)
    assert "the" in next(e for e in declared if e.startswith("stopwords_removed:"))


# --- participants ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "address", "display"),
    [
        ("ana@team.example", "ana@team.example", None),
        ("Ana.EXAMPLE@Team.Example", "ana.example@team.example", None),
        ("Ana Example <Ana@Team.Example>", "ana@team.example", "Ana Example"),
        ('"Ana Example" <ana@team.example>', "ana@team.example", "Ana Example"),
        ("ana", None, "ana"),
    ],
)
def test_participants_are_address_normalised_and_a_bare_name_is_not_invented_into_one(
    written: str, address: str | None, display: str | None
) -> None:
    participant = normalise_participant(OperatorName.FROM, written, negated=False)

    assert participant.address == address
    assert participant.display == display


def test_two_spellings_of_one_address_are_one_participant() -> None:
    parsed = parse("from:Ana@Team.Example to:ana@team.example")

    assert {p.address for p in parsed.participants} == {"ana@team.example"}


# --- interrogative class and answer types ----------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("when did the rollout ship", Interrogative.WHEN),
        ("how much did the vendor quote", Interrogative.HOW_MUCH),
        ("did we decide on the vendor", Interrogative.DID_WE_DECIDE),
        ("which vendor did we pick", Interrogative.DID_WE_DECIDE),
        ("who owns the rollout", Interrogative.WHO),
        ("where is the rollout doc", Interrogative.WHERE),
        ("why did the rollout slip", Interrogative.WHY),
        ("which vendor is cheapest", Interrogative.WHICH),
        ("how does the rollout work", Interrogative.HOW),
        ("what is the rollout plan", Interrogative.WHAT),
        ("rollout vendor quote", Interrogative.NONE),
    ],
)
def test_the_interrogative_table_classifies_every_class_it_publishes(
    query: str, expected: Interrogative
) -> None:
    assert classify_interrogative(query) is expected


def test_every_interrogative_class_has_a_declared_answer_type_or_a_declared_none() -> None:
    """A.8b names three answer-type-bearing classes; the rest must be *declared* as none.

    Declared rather than absent, because D.3 rule 1b distinguishes "the cue's token class is
    missing" from "there is no cue" - and a missing key would collapse the two.
    """
    assert set(ANSWER_TYPE_BY_INTERROGATIVE) == set(Interrogative)
    bearing = {k for k, v in ANSWER_TYPE_BY_INTERROGATIVE.items() if v is not None}
    assert bearing == {
        Interrogative.WHEN,
        Interrogative.HOW_MUCH,
        Interrogative.DID_WE_DECIDE,
    }


@pytest.mark.parametrize(
    ("answer_type", "present", "absent"),
    [
        (AnswerType.DATE_LIKE, "shipping on 2026/10/14", "shipping when it is ready"),
        (AnswerType.NUMERIC_CURRENCY, "the quote is $4,200", "the quote is generous"),
        (AnswerType.DECISION_VERB, "we agreed on option two", "we are still weighing it"),
    ],
)
def test_each_answer_type_fires_on_its_own_token_class_and_not_on_prose(
    answer_type: AnswerType, present: str, absent: str
) -> None:
    assert matches_answer_type(answer_type, present) is True
    assert matches_answer_type(answer_type, absent) is False


def test_a_when_question_is_not_read_as_a_decision_question() -> None:
    """The ordering in `INTERROGATIVE_PATTERNS` is load-bearing, so it is executed."""
    assert classify_interrogative("when did we decide the vendor") is Interrogative.WHEN


# --- confidence tier and paraphrase risk -----------------------------------------------


@pytest.mark.parametrize(
    ("query", "tier"),
    [
        ("rfc822msgid:<a1@mail.invalid>", ConfidenceTier.EXACT),
        ('"the rollout window slipped"', ConfidenceTier.EXACT),
        ("INV-2026-0041", ConfidenceTier.EXACT),
        ("from:ana@team.example", ConfidenceTier.FILTERED),
        ("rollout vendor", ConfidenceTier.WEAK),
        ("what about the", ConfidenceTier.NON_LEXICAL),
    ],
)
def test_every_confidence_tier_is_reachable_and_is_reached_by_its_own_case(
    query: str, tier: ConfidenceTier
) -> None:
    assert parse(query).confidence is tier


def test_paraphrase_risk_is_the_sum_of_its_published_factors_and_nothing_else() -> None:
    parsed = parse("what about it")

    assert [f.name for f in parsed.risk_factors] == [name for name, _ in RISK_FACTORS]
    assert parsed.paraphrase_risk == pytest.approx(
        sum(f.weight for f in parsed.risk_factors if f.fired)
    )


@pytest.mark.parametrize("factor", [name for name, _ in RISK_FACTORS])
def test_each_risk_factor_fires_on_a_case_and_stays_silent_on_another(factor: str) -> None:
    """Executed per factor, so a factor that can never fire is a failing test, not a comment."""
    fires = {
        "no_provable_operator": ("rollout vendor quote", "from:ana rollout vendor quote"),
        "interrogative_intent": ("when did the rollout ship", "from:ana rollout"),
        "no_exact_signal_candidate": ("rollout vendor", "rfc822msgid:<a1@mail.invalid>"),
        "few_content_terms": ("rollout", "rollout vendor quote"),
    }
    on, off = fires[factor]

    assert next(f for f in parse(on).risk_factors if f.name == factor).fired is True
    assert next(f for f in parse(off).risk_factors if f.name == factor).fired is False


def test_no_risk_factor_consults_a_corpus_or_a_count() -> None:
    """A.8a's prohibition, read at the only place a frequency dial could live."""
    parsed = parse("rollout vendor")
    assert all(isinstance(factor.weight, float) for factor in parsed.risk_factors)
    assert 0.0 <= parsed.paraphrase_risk <= 1.0


# --- A.6a time and timezone policy ------------------------------------------------------


def test_the_reference_zone_is_the_hosts_and_falls_back_to_utc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TZ", "Pacific/Auckland")
    assert str(reference_zone()) == "Pacific/Auckland"
    monkeypatch.setenv("TZ", "Not/AZone")
    assert str(reference_zone()) == "UTC"
    monkeypatch.delenv("TZ")
    assert str(reference_zone()) == "UTC"


def test_the_declared_timezone_is_the_one_actually_used() -> None:
    """A.6a rule 1: MailWeave never silently assumes the account's zone is the host's."""
    parsed = parse("rollout last week", zone=ZoneInfo("Pacific/Auckland"))

    assert parsed.timezone == "Pacific/Auckland"
    assert parsed.window is not None
    assert parsed.window.zone == "Pacific/Auckland"


def test_a_relative_window_is_emitted_twice_as_operators_and_as_window_utc() -> None:
    """A.6a rule 2: the reader can always see what was actually searched."""
    parsed = parse("rollout yesterday")

    assert parsed.window is not None
    rendered = [operator.render() for operator in parsed.window.operators()]
    assert rendered == ["after:2026/09/01", "before:2026/09/04"]
    assert parsed.window.as_wire() == {
        "start": "2026-09-01T00:00:00Z",
        "end": "2026-09-04T00:00:00Z",
    }


def test_a_relative_window_is_widened_by_the_declared_margin_and_says_so() -> None:
    parsed = parse("rollout yesterday")

    assert parsed.window is not None
    assert parsed.window.widened_days == DATE_MARGIN_DAYS
    declared = enforced_declarations(parsed, parsed.constraints)
    assert any("date_window_widened:±1d" in entry for entry in declared)


def test_an_explicit_absolute_date_is_not_widened() -> None:
    """A.6a rule 3's exception, which is the half a single test of "widening works" misses."""
    parsed = parse("rollout after:2026/05/01 before:2026/06/01")

    assert parsed.window is not None
    assert parsed.window.widened_days == 0
    assert parsed.window.as_wire() == {
        "start": "2026-05-01T00:00:00Z",
        "end": "2026-06-01T00:00:00Z",
    }
    assert not any(
        "date_window_widened" in entry
        for entry in enforced_declarations(parsed, parsed.constraints)
    )


def test_a_gmail_relative_age_operator_declares_the_instant_it_actually_cuts_at() -> None:
    """A.6a rule 2 over rule 3, on the family whose operator goes to Gmail verbatim.

    `newer_than:2d` is carried into the `q` byte for byte - LEX-02's fidelity half asserts
    exactly that, operator by operator, at L1's executed query - so MailWeave widens
    nothing here and must not say it did. It used to: `window.widened_days` was
    `DATE_MARGIN_DAYS`, `window_utc` declared a range a day wider on each side than the
    operator cuts, and `asked_for.enforced` carried the widening declaration, for a widening
    no probe performed. A message inside the declared window and outside the executed one
    was never listed, never disclosed and never withheld, while the response said it had
    been searched for (R-RETR-011). A.6a rule 2 is the rule that settles it: "the reader can
    always see what was actually searched."

    The margin is not abandoned - it is applied where MailWeave renders the boundary itself,
    which `test_a_widened_relative_expression_sends_the_widened_bound_it_declares` executes.
    """
    parsed = parse("rollout newer_than:2d")

    assert parsed.window is not None
    assert parsed.window.widened_days == 0
    assert parsed.window.start == NOW - timedelta(days=2)
    assert not any(
        "date_window_widened" in entry
        for entry in enforced_declarations(parsed, parsed.constraints)
    )
    assert "newer_than:2d" in FilteredRung().plan(parsed)[0].query


def test_a_widened_relative_expression_sends_the_widened_bound_it_declares() -> None:
    """A.6a rule 3 where it bites: the boundary MailWeave renders is the one it widens.

    The half `test_a_relative_window_is_widened_by_the_declared_margin_and_says_so` does not
    reach - it asserts the declaration - is that the widened bound is what goes to Gmail.
    Asserted at the executed `q`, because a margin that moves only `window_utc` is a claim
    about a search that did not happen.
    """
    parsed = parse("rollout yesterday")

    assert parsed.window is not None
    assert parsed.window.widened_days == DATE_MARGIN_DAYS
    executed = FilteredRung().plan(parsed)[0].query
    for operator in parsed.window.operators():
        assert operator.render() in executed


def test_the_old_relative_age_widening_is_not_reintroduced() -> None:
    parsed = parse("rollout newer_than:2d")

    assert parsed.window is not None
    assert parsed.window.widened_days == 0
    assert parsed.window.start is not None


def test_window_containment_compares_integer_epoch_milliseconds() -> None:
    """A.6a rule 4: no local-time arithmetic anywhere below the resolution step."""
    parsed = parse("rollout after:2026/05/01 before:2026/06/01")

    assert parsed.window is not None
    assert parsed.window.start_ms == 1777593600000
    assert parsed.window.contains_ms(parsed.window.start_ms) is True
    assert parsed.window.contains_ms(parsed.window.start_ms - 1) is False
    assert parsed.window.end_ms is not None
    assert parsed.window.contains_ms(parsed.window.end_ms) is False


@pytest.mark.parametrize("spelling", list(RELATIVE_EXPRESSIONS))
def test_every_published_relative_expression_resolves_to_a_window(spelling: str) -> None:
    """The table is the claim; every row of it is executed."""
    sample = spelling.replace(r"(\d{1,3})", "3")
    parsed = parse(f"rollout {sample}")

    assert parsed.window is not None, sample
    assert parsed.window.widened_days == DATE_MARGIN_DAYS
    # The expression was consumed into the window, not left behind as a term Gmail would
    # also have to match ("yesterday" is a date reference, not a word in the body).
    assert parsed.search_terms == ("rollout",), sample


def test_an_expression_outside_the_table_is_not_guessed_at() -> None:
    """ "the week we shipped" is not resolvable deterministically, so it stays a term."""
    parsed = parse("rollout the week we shipped")

    assert parsed.window is None
    assert "week" in parsed.render()


def test_a_date_operator_gmail_would_refuse_contributes_no_window_but_stays_enforced() -> None:
    parsed = parse("rollout after:notadate")

    assert parsed.window is None
    assert "after:notadate" in parsed.render()


# --- relaxation order and probe budget --------------------------------------------------


def test_a_constraint_of_several_fragments_decomposes_into_one_unit_per_fragment() -> None:
    """R-RETR-008 at the model: relaxation and decomposition are different questions.

    A constraint is **one** droppable unit - dropping the query's subject is one relaxation
    step, not one per word - and it is **as many** probeable units as it has independently
    satisfiable fragments, because Gmail's `q` is message-scoped and different messages of
    one thread can satisfy them separately (RO F2). Collapsing the two made `"rollout
    cutover"` a query L1b called `not_applicable`.

    Asserted per kind rather than on `terms` alone, because a rule that held for the
    reported shape and not its peers is this project's recurring defect.
    """
    terms = parse("rollout cutover handover")
    assert [c.name for c in terms.constraints] == ["terms"]
    assert [u.fragment for u in terms.decomposition_units] == [
        "rollout",
        "cutover",
        "handover",
    ]

    participants = parse("from:ana@team.example from:bo@team.example")
    assert [c.name for c in participants.constraints] == ["from"]
    assert [u.fragment for u in participants.decomposition_units] == [
        "from:ana@team.example",
        "from:bo@team.example",
    ]

    single = parse("procurement")
    only = single.decomposition_units
    assert len(only) == 1
    # A one-unit constraint is named after itself, so a probe carrying it reports the
    # constraint exactly as it did before this existed.
    assert only[0].label == "terms" and only[0].constraints == ("terms",)
    # A *piece* of a constraint names none, because there is no wire spelling for half of
    # one and claiming the whole would be wider than the query that was sent.
    assert [u.constraints for u in terms.decomposition_units] == [(), (), ()]


def test_a_negated_fragment_is_not_a_decomposition_probe_of_its_own() -> None:
    """The peer defect the `terms` fix opens if the rule is "one unit per fragment".

    `-from:bo@team.example` and `-cutover` are satisfied by nearly every message in a
    mailbox, so a decomposition probe carrying one alone is a whole-mailbox listing wearing
    a fragment of the query as a disguise - which is R-RETR-006's shape one operator to the
    left, arrived at from the opposite direction. A negation excludes; it selects nothing,
    so the intersection can learn nothing from it.

    The last case is the one that shows this is not new caution: a *single* negated
    operator has been an L1b probe since round 15, because a one-fragment constraint planned
    its own render. It is not one now.
    """
    mixed = parse("from:ana@team.example -from:bo@team.example rollout")
    assert [p.query for p in DecompositionRung().plan(mixed)] == [
        "from:ana@team.example -from:bo@team.example",
        "rollout",
    ]

    several = parse("from:a@team.example from:b@team.example -from:c@team.example")
    assert [p.query for p in DecompositionRung().plan(several)] == [
        "from:a@team.example",
        "from:b@team.example",
    ]

    excluded_term = parse("rollout -cutover")
    assert [u.fragment for u in excluded_term.decomposition_units] == ["rollout -cutover"]
    assert DecompositionRung().plan(excluded_term) == ()

    only_negations = parse("-from:ana@team.example rollout")
    assert [c.name for c in only_negations.constraints] == ["from", "terms"]
    assert [u.fragment for u in only_negations.decomposition_units] == ["rollout"]
    assert DecompositionRung().plan(only_negations) == ()


def test_a_mailbox_scope_fragment_is_not_a_decomposition_probe_of_its_own() -> None:
    """The second peer of the same rule, and the one this round got wrong first.

    A negation says what to leave out; a mailbox-scope operator says **where** to look.
    Neither says what to look for, so neither is a probe - and `in:anywhere rollout` is an
    ordinary Gmail query, not a corner case: it is the query L3 composes for itself.

    Before this, `decomposition_units_of` filtered on the negation prefix alone, so the
    scope operator became a unit of its own, `DecompositionRung` planned a probe of it, and
    `Probe.__post_init__` - round 16's own R-RETR-006 refusal, in the next module - rejected
    it with a bare `ValueError` out of `plan_ladder`. Two round-16 fixes, each right about
    the shape it was written for, wrong at their join. That is this project's recurring
    defect committed inside the round that named it, which is why the assertion below is
    over the whole `WIDENING_MAILBOX_OPERATORS` vocabulary rather than over the one spelling
    that was found.
    """
    for operator in sorted(WIDENING_MAILBOX_OPERATORS):
        scoped = parse(f"{operator} rollout cutover")
        assert {c.name for c in scoped.constraints} == {"in", "terms"}, operator
        # The scope operator contributes no unit of its own - and is carried by every unit
        # there is, which is round 17's half of the same join (R-RETR-019). Excluding a
        # fragment from the units and excluding it from the probes are two decisions, and
        # round 16 made only the first: the probes then went out with the flag flipped back
        # to false and the founding bug's shape in spam became unrecoverable.
        assert [u.label for u in scoped.decomposition_units] == [
            "terms[rollout]",
            "terms[cutover]",
        ], operator
        assert [u.fragment for u in scoped.decomposition_units] == [
            f"{operator} rollout",
            f"{operator} cutover",
        ], operator
        planned = DecompositionRung().plan(scoped)
        assert [p.query for p in planned] == [f"{operator} rollout", f"{operator} cutover"]
        # The flag travels with the `q` it was derived from, so carrying the scope carries
        # the request parameter with it - the half `Probe.include_spam_trash` makes
        # structural rather than remembered.
        assert all(probe.include_spam_trash for probe in planned), operator
        # The region really was searched, so each probe may say it enforced that constraint.
        assert all(probe.enforced == ("in",) for probe in planned), operator

        # With one thing left to look for there is nothing to decompose, and the rung says
        # so by planning nothing rather than by planning a listing.
        alone = parse(f"{operator} rollout")
        assert alone.decomposition_units == (
            ConstraintUnit(
                label="terms",
                fragment=f"{operator} rollout",
                constraints=("terms", "in"),
                derived_from=("terms",),
            ),
        ), operator
        assert DecompositionRung().plan(alone) == (), operator

        # And a query that names only where to look decomposes to nothing at all.
        assert parse(operator).decomposition_units == (), operator


def test_a_pair_of_date_operators_that_cross_resolves_to_no_window_not_a_crash() -> None:
    """`newer_than:7d older_than:30d` is typable, and it used to raise out of `analyse`.

    Two bounds that cross describe an empty window. `TimeWindow` refuses to hold one - which
    is right, and is a guard against a programming error - so `window_from_operators` used to
    let a bare `ValueError` ("a time window ends before it starts") escape `analyse` on a
    user's query: not a MailWeave error, not a declared inability, an uncaught exception.

    The resolution is the rule the same function already applies to a date value it cannot
    resolve: claim no window, carry both operators onto the wire verbatim, and let Gmail
    judge them. The ladder then answers it the way it answers any zero-hit query, and L2's
    relaxation is what recovers it - which is a better answer than a refusal.
    """
    crossed = parse("newer_than:7d older_than:30d rollout")
    assert crossed.window is None
    # Both operators are still enforced, and both reach L1's executed `q`.
    assert [c.name for c in crossed.constraints] == ["newer_than", "older_than", "terms"]
    executed = FilteredRung().plan(crossed)[0].query
    assert "newer_than:7d" in executed and "older_than:30d" in executed
    assert crossed.term_coverage(crossed.constraints) == 1.0
    # The relaxation that restores results is planned, which is the recovery a refusal loses.
    assert "newer_than" in RelaxationRung().drop_order(crossed)

    # The order the operators are written in does not change the answer.
    assert parse("older_than:30d newer_than:7d").window is None
    # A window that does not cross still resolves.
    assert parse("newer_than:30d older_than:7d").window is not None


def test_a_date_window_is_one_unit_whether_it_is_written_out_or_derived() -> None:
    """The exception, and the peer the round-16 fix for R-RETR-008 first missed.

    `after:X before:Y` is one condition on one message's timestamp. A thread holding a
    message after `X` and another before `Y` holds no message inside the window, so
    intersecting the halves on `threadId` would name threads nothing in them satisfies -
    the opposite of what the decomposition rung is for.

    **The claim above was already written and the code under it was per-constraint**, which
    is the derived `date_window` and nothing else: a user who writes the window out - the
    ordinary way to write one - produces *two* constraints of one fragment each, each "one
    unit" by that reading, and the halves were intersected exactly as the docstring said
    they must not be. So the assertion is over the **parse**, which is where the claim
    lives, and the two spellings of one window are asserted to produce the same single unit.
    A per-constraint assertion is what let the peer through, and it is not written again.
    """
    written = parse("rollout after:2026/05/01 before:2026/06/01")
    assert [c.name for c in written.constraints] == ["after", "before", "terms"]
    assert [(u.label, u.fragment) for u in written.decomposition_units] == [
        ("after+before", "after:2026/05/01 before:2026/06/01"),
        ("terms", "rollout"),
    ]
    # The unit carries both constraints whole, so a row it admits may claim both: the
    # message really is inside the window.
    assert written.decomposition_units[0].constraints == ("after", "before")

    derived = parse("rollout yesterday")
    window = next(c for c in derived.constraints if c.name == "date_window")
    assert len(window.fragments) == 2
    units = [u for u in derived.decomposition_units if u.label == "date_window"]
    assert len(units) == 1 and units[0].fragment == window.render()

    # A window that only excludes is not a unit at all, for the reason a negated fragment
    # is never one: it selects nothing for an intersection to learn from.
    assert [u.label for u in parse("rollout -after:2026/05/01").decomposition_units] == ["terms"]


def test_the_relaxation_order_covers_every_constraint_kind_this_parser_produces() -> None:
    """A "documented order" that does not name a kind sorts it by accident (ROUTE-03).

    **The population is every operator the lexicon claims, taken from the fidelity table
    rather than from a query somebody wrote out** (round 19). The hand-written query held one
    operator per kind as the kinds stood, so when `OperatorKind.LOCATION` was split into the
    one that selects a region and the one that filters within it, the half nobody had written
    down was produced by no query here and the `==` passed over a kind with no published rank.
    Reading the table means an operator added to the lexicon arrives in this sweep with it.
    """
    written = " ".join(sorted(case for case, _value in FIDELITY_TABLE.values()))
    produced = {
        constraint.kind for constraint in parse(f'{written} "a phrase here" rollout').constraints
    }
    assert produced <= set(RELAXATION_ORDER)
    assert produced == set(RELAXATION_ORDER)


@pytest.mark.parametrize(
    ("constraints", "expected"), [(0, 0), (1, 1), (5, 5), (6, 6), (7, 6), (40, 6)]
)
def test_the_relax_probe_budget_is_min_k_six(constraints: int, expected: int) -> None:
    assert max_relax_probes(constraints) == expected


def test_a_quoted_phrase_containing_a_colon_is_a_phrase_not_an_unknown_operator() -> None:
    """R-RETR-018: `"Re: quarterly plan"` is a reply subject, not an operator called `"Re`.

    `tokenise` partitioned on `:` before its own quoted-phrase branch could see the token, so
    every quoted phrase carrying a colon was classified `UNKNOWN_OPERATOR`. On its own that
    was a mis-classification with a bounded cost - the token rode into the executed `q`
    inside the residual terms and Gmail matched it as a string. Joined to R-RETR-012's fix
    (an unprovable token is kept out of the `q`) and R-RETR-006's (a query no rung can plan
    for is not scanned), it became a **refusal**: the phrase was searched for at no rung, and
    when it was the whole query nothing reached Gmail at all.

    The rule is one clause - a `name:value` token is an operator only when `name` is
    unquoted - and it is asserted over the shapes a user actually types, not over the one
    that was reported. `subject:"note: see below"` is here as the control: it always worked,
    because the operator branch unquotes its tail, and it must keep working.
    """
    reply_subjects = (
        '"Re: quarterly plan"',
        '"9:30 standup"',
        '"note: see below"',
        '"http://docs.example.test/plan"',
        '"ratio 3:1"',
        '"budget: approved"',
        '"Q3: results"',
        '"12:00 handover"',
        '"tel:12345"',
    )
    for written in reply_subjects:
        parsed = parse(written)
        assert parsed.unknown_operators == (), written
        assert parsed.phrases == (written.strip('"'),), written
        assert [c.name for c in parsed.constraints] == ["phrase"], written
        # And it reaches the wire as a Gmail phrase search rather than being dropped.
        assert parsed.render() == written, written
        assert parsed.term_coverage(parsed.constraints) == 1.0, written

    # **A negated phrase is still a phrase, and it is still a negation** (R-RETR-027). Round
    # 17's version of this assertion stopped at the first half, which is the eleventh time a
    # test covered one shape and trusted its peer: `phrases` was `token.value` and
    # `token.negated` was discarded, so `_build_constraints` rendered `"Re: quarterly plan"`
    # and MailWeave searched *for* the phrase the caller asked to exclude - returning the one
    # message that has it as `role: matched`, `constraint_coverage ('phrase',)`,
    # `term_coverage 1.0`, `outcome: answered`. Polarity is now on the constraint, and every
    # consumer of it is asserted here rather than left to be discovered.
    for written in ('-"Re: quarterly plan"', '-"quadrant notice zephyr"'):
        excluded = parse(written)
        value = written[2:-1]
        assert excluded.phrases == (), written
        assert excluded.excluded_phrases == (value,), written
        assert excluded.render() == written, written
        assert excluded.qualifying_phrases == (), written
        assert [c.fragments for c in excluded.constraints] == [(written,)], written
        # It is an exclusion, so it is never a probe of its own: a `q` of nothing but
        # "everything except this phrase" is a mailbox listing (R-RETR-006's shape).
        assert not selects_something(written), written
        assert decomposition_units_of(excluded.constraints) == (), written
    control = parse('subject:"note: see below"')
    assert [o.name.value for o in control.operators] == ["subject"]
    assert control.operators[0].value == "note: see below"

    # The class this rule must not swallow: an unquoted `name:value` whose name is not
    # Gmail's is still an unproven operator, declared and not executed (R-RETR-012).
    unproven = parse("thread:1837abf rollout")
    assert unproven.unknown_operators == ("thread:1837abf",)
    assert unproven.render() == "rollout"


def test_a_repeated_identical_fragment_is_one_unit_and_every_label_is_unique() -> None:
    """R-RETR-025: `ConstraintUnit.label` claimed uniqueness; the claim is now executed.

    `label` was `f"{name}[{fragment}]"`, so two identical fragments produced two identical
    labels. Two costs, and the second is the one that hurt: one of L1b's three A.7 probe
    slots was spent re-sending an identical `q`, and `_after_rung`'s intersection dictionary
    - keyed on the label - kept only the later probe, whose admission delta is empty because
    the earlier identical probe had already admitted everything. So the intersection came out
    empty and L1b's finds were disclosed at `stub` depth rather than `body_clean`.

    A repeated identical fragment is one question asked twice, so it is one unit. The
    uniqueness assertion below is over every shape that can produce a collision, and it is an
    assertion rather than a docstring because that is what the finding was about.
    """
    for query in (
        "from:ana@team.example from:ana@team.example cutover",
        "label:alpha label:alpha",
        "has:attachment has:attachment",
        "subject:vendor subject:vendor rollout",
        '"one two three" "one two three" cutover',
        "rollout rollout cutover",
    ):
        units = parse(query).decomposition_units
        labels = [unit.label for unit in units]
        assert len(labels) == len(set(labels)), (query, labels)
        fragments = [unit.fragment for unit in units]
        assert len(fragments) == len(set(fragments)), (query, fragments)

    repeated = parse("from:ana@team.example from:ana@team.example cutover")
    assert [u.label for u in repeated.decomposition_units] == ["from", "terms"]
    # The duplicate is gone from the probe as well as from the unit list, so the slot is not
    # spent on a token Gmail would have ignored.
    assert repeated.decomposition_units[0].fragment == "from:ana@team.example"

    # Two *different* fragments of one constraint are still two units: the de-duplication
    # must not collapse the case the rung exists for.
    distinct = parse("from:ana@team.example from:bo@team.example cutover")
    assert [u.label for u in distinct.decomposition_units] == [
        "from[from:ana@team.example]",
        "from[from:bo@team.example]",
        "terms",
    ]
