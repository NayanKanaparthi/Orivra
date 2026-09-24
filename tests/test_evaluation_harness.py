"""The two-arm harness executes end to end, and refuses every case it cannot score.

**What this file establishes and what it does not.** It establishes that the case interface
loads EP §4.1's object, that the ref joins resolve through a real generated manifest to the ids
a mailbox assigned, that both arms run through the shipped `MailweaveService`, and that the
three hypothesis clauses compute their own falsification conditions. It establishes **nothing**
about retrieval quality: the dummy cases' queries are sentinel tokens, so a lexical exact match
answers every one of them and the semantic arm has nothing to add. That is the point. A
development fixture that produced an interesting H1 verdict would be a fixture somebody would
be tempted to quote.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from mailweave.constants import HOST_RESULT_CHAR_CAP
from mailweave.envelope.measure import rendered_chars
from mailweave_harness.evaluation import (
    BOTH_OFF,
    FIXED_WINDOW,
    FULL,
    MAX_RECOVERY_ROUNDS,
    SEM_OFF,
    SPECS,
    Arm,
    Case,
    CaseFile,
    EvidenceRef,
    Factor,
    Measured,
    RefUnresolvable,
    Verdict,
    evaluate,
    load_cases,
    mean_cut_loss,
    position_spread,
    recoverability,
    resolve_against,
    run_all,
    run_case,
)
from mailweave_harness.evaluation.cases import FAMILIES, FAMILY_LABELS, ResolvedCase
from mailweave_harness.seed.manifest import Manifest
from mailweave_harness.seed.metrics import outcome_rates, surfaced_not_disclosed
from mailweave_harness.seed.substrate import VerificationReport
from tests.fixtures.eval_dummy import (
    dummy_arms,
    dummy_case_file,
    dummy_manifest,
    mailbox_of,
)
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms


class Fixture(NamedTuple):
    """The dummy corpus, the mailbox built from it, and the case file written against it."""

    manifest: Manifest
    box: SyntheticMailbox
    report: VerificationReport
    cases: CaseFile

    def resolved(self) -> list[ResolvedCase]:
        return [
            resolve_against(case, manifest=self.manifest, report=self.report)
            for case in self.cases.cases
        ]


@pytest.fixture(scope="module")
def corpus() -> Fixture:
    manifest = dummy_manifest()
    box, report = mailbox_of(manifest)
    return Fixture(manifest, box, report, dummy_case_file(manifest))


# --- the interface -------------------------------------------------------------------------


def test_every_family_this_harness_knows_carries_the_plans_own_label() -> None:
    """A family string with no `F<n>` beside it is one a report cannot name to a reader."""
    assert set(FAMILY_LABELS) == FAMILIES


def test_a_reference_round_trips_and_a_malformed_one_is_refused() -> None:
    assert EvidenceRef.parse("thread:A07/pos:37").render() == "thread:A07/pos:37"
    for bad in ("A07/37", "thread:A07", "thread:A07/pos:x", ""):
        with pytest.raises(RefUnresolvable):
            EvidenceRef.parse(bad)


def _case(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "case_id": "c1",
        "template_id": "T1",
        "family": "exact_lookup",
        "seed": 1,
        "query": "q",
        "evidence": [{"ref": "thread:a/pos:0", "role": "primary", "quote": "hello"}],
        "evidence_cardinality": "single",
        "expected_behavior": {"must_retrieve": ["primary"], "notes": "n/a for this unit"},
        "scoring": {"recall_rule": "quote disclosed"},
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"family": "invented_family"}, "not one this harness knows"),
        ({"evidence": []}, "cannot be scored"),
        (
            {"expected_behavior": {"must_retrieve": ["secondary"], "notes": "x"}},
            "names roles",
        ),
        ({"evidence_cardinality": "some_of"}, "single | all_of | any_of"),
        (
            {"family": "unanswerable_control"},
            "not a control",
        ),
    ],
)
def test_a_case_that_cannot_be_scored_is_refused_at_load(
    overrides: dict[str, object], message: str
) -> None:
    """Each refusal is here because scoring it would publish a number nobody could read."""
    with pytest.raises(ValueError, match=message):
        Case.model_validate(_case(**overrides))


def test_a_required_note_cannot_be_empty() -> None:
    """EP §4.1 makes `expected_behavior.notes` required: it states what would make a pass
    hollow, and the gate reviewer reads it."""
    with pytest.raises(ValueError):
        Case.model_validate(_case(expected_behavior={"must_retrieve": ["primary"], "notes": ""}))


def test_a_position_whose_fraction_lies_is_refused() -> None:
    """§4.4 makes the fraction normative, so the two disagreeing would report the sweep at a
    depth nobody ran."""
    with pytest.raises(ValueError, match="does not describe position"):
        Case.model_validate(_case(position={"thread_len": 100, "target_pos": 37, "fraction": 0.90}))


def test_a_paraphrase_tier_that_contradicts_its_own_overlap_is_refused() -> None:
    with pytest.raises(ValueError, match="zero content-word overlap"):
        Case.model_validate(_case(paraphrase={"tier": 2, "content_word_jaccard": 0.5}))


def test_the_dummy_case_file_loads_from_disk_unchanged(corpus: Fixture, tmp_path: Path) -> None:
    case_file = corpus.cases
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(case_file.model_dump(mode="json")), encoding="utf-8")
    assert load_cases(path) == case_file


# --- the joins -----------------------------------------------------------------------------


def test_every_dummy_case_resolves_through_the_manifest_to_mailbox_ids(
    corpus: Fixture,
) -> None:
    manifest, report, case_file = corpus.manifest, corpus.report, corpus.cases
    for case in case_file.cases:
        resolved = resolve_against(case, manifest=manifest, report=report)
        assert set(resolved.required) <= {one.gmail_id for one in report.inserted}
        if case.answerable:
            assert resolved.required, case.case_id


def test_a_case_written_against_another_corpus_is_refused_rather_than_scored(
    corpus: Fixture,
) -> None:
    """The join that silently succeeds is the one that credits a retrieval that never
    happened, and nothing downstream can see it."""
    manifest, report, case_file = corpus.manifest, corpus.report, corpus.cases
    answerable = next(one for one in case_file.cases if one.answerable)
    wrong = answerable.model_copy(
        update={
            "evidence": (
                answerable.evidence[0].model_copy(
                    update={"rfc_message_id": "<not-in-this-corpus@mail.invalid>"}
                ),
            )
        }
    )
    with pytest.raises(RefUnresolvable, match="written against a different corpus"):
        resolve_against(wrong, manifest=manifest, report=report)


def test_a_reference_to_a_position_the_corpus_does_not_have_is_refused(
    corpus: Fixture,
) -> None:
    manifest, report, case_file = corpus.manifest, corpus.report, corpus.cases
    answerable = next(one for one in case_file.cases if one.answerable)
    wrong = answerable.model_copy(
        update={
            "evidence": (
                answerable.evidence[0].model_copy(
                    update={"ref": "thread:no-such-thread/pos:0", "rfc_message_id": None}
                ),
            )
        }
    )
    with pytest.raises(RefUnresolvable, match="names no message in this corpus"):
        resolve_against(wrong, manifest=manifest, report=report)


# --- both arms, end to end -------------------------------------------------------------------


def test_both_arms_run_every_case_and_the_semantic_one_is_the_only_one_that_embeds(
    corpus: Fixture,
) -> None:
    """The development loop's whole claim: the pipeline executes on both arms.

    And one property worth asserting while it does: the lexical arm makes **no** call at the
    SEM-03 seam, measured by the counting proxy rather than read off `rungs`. That is the
    instrument H1's second clause depends on, so a run where it silently counted nothing would
    make that clause hold for free.
    """
    manifest, box = corpus.manifest, corpus.box
    resolved = corpus.resolved()
    arms = dummy_arms(manifest, box)
    semantic, sem_off = arms[0], arms[1]
    runs = run_all([semantic, sem_off], resolved)
    assert len(runs) == 2 * len(resolved)
    assert {one.arm for one in runs} == {"full", "sem-off"}
    assert all(one.declined is None for one in runs), [
        (one.case_id, one.arm, one.declined) for one in runs if one.declined
    ]
    # RR-03: an uninstrumented run records `None`, not 0, so the two facts stay apart.
    # `sem-off` registers no semantic backend at all, so it has no seam to instrument and
    # UNMEASURED there is the design rather than a fault - "it did not embed" is true of it by
    # construction, which is a stronger statement than a count of zero. The arm that has to be
    # instrumented is the semantic one, and it has to have actually embedded, or the pair
    # establishes nothing about the semantic rungs.
    lexical = [one for one in runs if one.arm == "sem-off"]
    assert all(one.counter_state is Measured.UNMEASURED for one in lexical), (
        "sem-off carried a semantic counter; that arm is supposed to have no backend"
    )
    semantic_runs = [one for one in runs if one.arm == "full"]
    assert all(one.counter_state is Measured.MEASURED for one in semantic_runs), (
        "the semantic arm carried no instrument, so nothing here is a measurement of it"
    )
    assert sum((one.embed_calls or 0) for one in semantic_runs) > 0, (
        "the semantic arm never reached the seam, so this fixture does not exercise it"
    )


def test_the_outcome_rates_need_both_halves_and_this_fixture_supplies_them(
    corpus: Fixture,
) -> None:
    """EP §6.1's three rates are one object because each can be improved by making another
    worse. A case set with no unanswerable control cannot produce them at all, which is why
    the dummy file carries one."""
    manifest, box, case_file = corpus.manifest, corpus.box, corpus.cases
    resolved = corpus.resolved()
    semantic = dummy_arms(manifest, box)[0]
    runs = run_all([semantic], resolved)
    by_id = {one.case_id: one for one in runs}
    answerable = [by_id[c.case_id].terminal for c in case_file.cases if c.answerable]
    controls = [by_id[c.case_id].terminal for c in case_file.cases if not c.answerable]
    rates = outcome_rates(answerable=answerable, unanswerable=controls)
    assert 0.0 <= rates.false_not_found <= 1.0
    assert "FNF" in rates.render()


def test_the_hypotheses_compute_their_own_clauses_and_report_what_was_not_evaluable(
    corpus: Fixture,
) -> None:
    """Every clause carries its own state, and H3 is NOT_EVALUABLE without its own baseline.

    H3 compares query-aware selection against **position-based** selection - a third arm - so
    answering it against the lexical arm would answer a different question under H3's name.
    """
    manifest, box = corpus.manifest, corpus.box
    resolved = corpus.resolved()
    arms = dummy_arms(manifest, box)
    semantic, sem_off = arms[0], arms[1]
    runs = run_all([semantic, sem_off], resolved)
    required = {one.case.case_id: dict(one.required) for one in resolved}
    results = evaluate(
        runs, required=required, candidate_arm="full", semantic_baseline_arm="sem-off"
    )
    assert [one.id for one in results] == ["H1", "H2", "H3"]
    h3 = results[2]
    assert h3.verdict is Verdict.NOT_EVALUABLE
    assert all(one.verdict is Verdict.NOT_EVALUABLE for one in h3.clauses)
    assert "fixed +/-2 window" in h3.clauses[0].detail
    # Every clause quotes the falsification condition it implements, so a report cannot drift
    # from plan §8.2 without this failing.
    for result in results:
        for clause in result.clauses:
            assert clause.quoted.strip(), (result.id, clause.name)


def test_a_hypothesis_is_never_reported_as_holding_on_an_unevaluated_clause(
    corpus: Fixture,
) -> None:
    """The defect class this repository keeps finding, in the one place it would be most
    expensive: a hypothesis that holds on two of three clauses is not a hypothesis that holds."""
    manifest, box = corpus.manifest, corpus.box
    resolved = corpus.resolved()
    arms = dummy_arms(manifest, box)
    semantic, sem_off = arms[0], arms[1]
    runs = run_all([semantic, sem_off], resolved)
    required = {one.case.case_id: dict(one.required) for one in resolved}
    results = evaluate(
        runs, required=required, candidate_arm="full", semantic_baseline_arm="sem-off"
    )
    for result in results:
        states = {one.verdict for one in result.clauses}
        if Verdict.NOT_EVALUABLE in states and Verdict.FALSIFIED not in states:
            assert result.verdict is Verdict.NOT_EVALUABLE, result.id


def test_a_spread_over_one_position_is_not_a_spread() -> None:
    """§4.4's sweep exists to catch oldest-K and newest-K behaviour, and both score a spread
    of zero when only one position ran."""
    assert position_spread([], arm="full", required={}) is None


def test_a_snippet_row_is_surfaced_and_not_disclosed_and_the_harness_says_which(
    corpus: Fixture,
) -> None:
    """**The most consequential reading rule here, asserted rather than left implicit.**

    EP §6.1: a stub or snippet-only row is not a disclosure. MailWeave's default path answers
    a broad query with snippet rows, so without this distinction every such answer would score
    as a retrieval failure - when what actually happened is progressive disclosure working:
    the evidence is named, reachable and one call away, and its content is not yet in hand.
    `surfaced_not_disclosed` is where that state is reported, and it is reported *beside*
    recall rather than inside it.

    The consequence for the campaign is stated here because it is where a reader will look: a
    recall figure over the default view is a figure about what one call put in the reader's
    hands. `levels_traversed_to_answer` (EP §6.4) is the metric for what a driver following
    the affordances would have reached, and driving the affordances is not what this harness
    does.
    """
    manifest, box, case_file = corpus.manifest, corpus.box, corpus.cases
    case = next(one for one in case_file.cases if one.case_id == "selftest-escalates")
    resolved = resolve_against(case, manifest=manifest, report=corpus.report)
    semantic = dummy_arms(manifest, box)[0]
    run = run_all([semantic], [resolved])[0]
    required = set(resolved.required)
    assert required, case.case_id
    assert required <= run.disclosure.surfaced_ids, "the evidence was not even named"
    assert not (required & set(run.disclosure.content_by_id)), (
        "this fixture's evidence arrives at snippet depth; if it ever arrives deeper, this "
        "test is the place to notice, because the recall figures move with it"
    )
    assert surfaced_not_disclosed(run.disclosure, required) == frozenset(required)


def test_the_semantic_rungs_run_only_where_the_lexical_ones_found_nothing(
    corpus: Fixture,
) -> None:
    """The adaptive cost invariant, measured at the seam rather than read off `rungs`.

    Every sentinel-token case is an exact lexical hit, so the ladder stops on evidence and the
    backend is never asked for anything. That is H1's second clause holding on this fixture -
    and it is asserted here as a property of the *instrument* too: a counting proxy that
    silently counted nothing would make that clause hold for free on any corpus.
    """
    manifest, box = corpus.manifest, corpus.box
    resolved = corpus.resolved()
    semantic = dummy_arms(manifest, box)[0]
    runs = {one.case_id: one for one in run_all([semantic], resolved)}
    exact = [one for one in runs.values() if one.family == "exact_lookup"]
    assert exact, "no exact-lookup case ran"
    assert all(one.embed_calls == 0 and one.rerank_calls == 0 for one in exact)
    # ...and the instrument is live: at least one case did reach the seam.
    assert any(one.embed_calls > 0 for one in runs.values()), (
        "no case reached the semantic seam, so the zero above is not evidence of anything"
    )


# --- the factorial, and what each arm isolates -----------------------------------------------


def test_each_single_factor_arm_differs_from_full_in_exactly_one_thing() -> None:
    """The labels have to be true, because they are what a reader attributes a result to.

    `sem-off` differs in the semantic rungs and nothing else; `fixed-window` differs in the
    disclosure selector and nothing else; the corner arm differs in both and therefore
    isolates neither, which its own `isolates` string says in those words.
    """
    assert FULL.factors == frozenset()
    assert SEM_OFF.factors == {Factor.SEMANTIC}
    assert FIXED_WINDOW.factors == {Factor.SELECTION}
    assert BOTH_OFF.factors == {Factor.SEMANTIC, Factor.SELECTION}
    assert "nothing on its own" in BOTH_OFF.isolates


def test_no_arm_claims_to_be_the_released_v0_1() -> None:
    """The correction that occasioned the factorial, asserted so it cannot quietly revert.

    Every arm's `does_not_isolate` names what a no-backend run still carries that v0.1 did
    not - the LR rung, mechanical ranking, the nine-rung ladder, R-M2-001's participant fix,
    the re-measured estimate - and no arm is named after the release.
    """
    for spec in SPECS:
        assert "v0.1" not in spec.name
    for spec in (SEM_OFF, FIXED_WINDOW, BOTH_OFF):
        assert "no arm here is the released v0.1" in spec.does_not_isolate
        for carried in ("LR freshness rung", "mechanical ranking", "R-M2-001"):
            assert carried in spec.does_not_isolate, (spec.name, carried)


def test_turning_the_backend_off_does_not_turn_ranking_off(corpus: Fixture) -> None:
    """The claim behind `sem-off`'s label, verified against the server rather than a docstring.

    Mechanical ranking runs on every query whatever the backend does, so a no-backend run
    still names `L6` in `rungs`. If that ever stops being true the label is wrong, and the
    label is what a reader attributes an H1 result to.
    """
    from mailweave.surface.arguments import parse_search

    manifest, box = corpus.manifest, corpus.box
    sem_off = next(one for one in dummy_arms(manifest, box) if one.name == "sem-off")
    # The longest word of the *prose*, not of the whole body: every message now ends with a
    # uniform reference trailer, and that token is both the longest word in every body and
    # identifier-shaped, so a query built from it is resolved at L0 and the ladder never
    # reaches the rung this test is about.
    import re as _re

    # And the *rarest* prose word rather than the longest, because the corpus is now a
    # population: the longest word in a body is typically an entity name occurring in sixty
    # others, and a query that broad exhausts the disclosure ladder before any rung is
    # reported. The rung this test names is about mechanical ranking, not about breadth.
    def _prose(message: object) -> list[str]:
        return _re.findall(r"[A-Za-z]{5,}", _re.sub(r"\n-- \n.*$", "", message.body, flags=_re.S))

    frequency: dict[str, int] = {}
    for message in manifest.messages:
        for term in set(_prose(message)):
            frequency[term] = frequency.get(term, 0) + 1
    # And a word whose search actually completes. The corpus is a population now, so a broad
    # term exhausts the disclosure ladder before any rung is reported - which says something
    # about breadth and nothing about the rung this test names. The first word that returns a
    # report is the one used, and the test fails loudly if none does.
    report = None
    for word in sorted(
        set(_prose(manifest.messages[0])), key=lambda one: (frequency[one], -len(one))
    ):
        try:
            report = sem_off.service.search(parse_search({"query": word})).retrieval_report
        except Exception:
            continue
        break
    assert report is not None, "no query over the first message's words completed at all"
    assert "L6" in {rung.value for rung in report.rungs}, report.rungs


# --- Baseline F's +/-2 window: where it fits, and where it is traded for room -------------------

#: The conversation Baseline F's fill is exercised on (2026-09-22). Seven messages in one reply
#: chain with one hit in the middle, short ordinary bodies, and one unrelated thread beside it:
#: small enough that the whole response fits the **unchanged** production ceilings, so no ladder
#: step reaches the fill and what is observed is the mechanism rather than what the ladder left
#: of it. The hit sits at position 3 so every edge of the window is informative - 1 and 5 are
#: the +/-2 fill, 2 and 4 are the reply floor that outranks it, and 0 and 6 are outside any
#: +/-2 window (a radius of 1 would miss 1 and 5; a radius of 3 would reach 0 and 6).
#: Deterministic: fixed ids, fixed dates, fixed text, no generator.
WINDOW_TOKEN = "quillmark"
WINDOW_MESSAGES = 7
WINDOW_HIT = 3
_WINDOW_BODIES = (
    "Opening the thread about the loading dock schedule for next week.",
    "Thanks, the morning slots look better for the carriers.",
    "Agreed on mornings; the afternoon crew is short on Thursdays.",
    "Moving the dock inspection to Tuesday keeps the carriers on time.",
    "Tuesday works for facilities if the forklift is serviced first.",
    "Forklift service is booked for Monday afternoon.",
    "Confirmed with the carriers, nothing else changes this week.",
)


def _window_id(position: int) -> str:
    return f"bf-{position:03d}"


def window_conversation() -> SyntheticMailbox:
    """The seven-message conversation above, and one thread the query does not reach."""
    start = epoch_ms(2026, 4, 6)
    chain = [
        Msg(
            id=_window_id(position),
            thread_id="t-window",
            sender=f"person{position % 3}@dock.example",
            subject="Dock schedule" if position == 0 else "Re: Dock schedule",
            body=_WINDOW_BODIES[position]
            + (f" Reference {WINDOW_TOKEN} for the audit." if position == WINDOW_HIT else ""),
            internal_date_ms=start + position * 3_600_000,
            to=("team@dock.example",),
            rfc822_message_id=f"<{_window_id(position)}@dock.example>",
            in_reply_to=None if position == 0 else f"<{_window_id(position - 1)}@dock.example>",
            references=None
            if position == 0
            else " ".join(f"<{_window_id(earlier)}@dock.example>" for earlier in range(position)),
        )
        for position in range(WINDOW_MESSAGES)
    ]
    other = [
        Msg(
            id=f"ot-{index:03d}",
            thread_id="t-other",
            sender="someone@elsewhere.example",
            subject="Lunch",
            body="Lunch on Friday at noon works.",
            internal_date_ms=epoch_ms(2026, 4, 1) + index * 60_000,
            to=("team@dock.example",),
        )
        for index in range(3)
    ]
    return SyntheticMailbox(messages=(*chain, *other), now_ms=epoch_ms(2026, 4, 10))


def test_baseline_f_executes_and_its_rows_say_why_they_are_there(corpus: Fixture) -> None:
    """**Baseline F could not run at all before round 32**, and this is the regression guard.

    `Selector` and `FixedWindow` have existed since WS-11, `_score_of` already inverted the
    offset so both arms degrade in the same order, and `plan.py` called the baseline "a
    permanent harness fixture (PROC-04), runnable here at the same ceiling". The first filled
    row it produced raised `DispositionInvariantError`, because `_fill_reason` knew only the
    query-aware mechanism. The published comparison fixture could not execute - the same shape
    as R-M2-008.

    What a fixed-window row carries now is `window +/-k around <hit>`: a real mechanism, and
    one that is *not* traceable to the query, which is exactly why DISC-01 says a +/-2 policy
    fails that criterion by construction. Rendering it honestly is what makes the comparison
    readable.

    **Two halves since 2026-09-22.** The arm executes over every case of the dummy corpus, and
    every row it produces there states a reason. The window fill itself is observed on
    `window_conversation()`, through the same arm constructor the campaign uses and the
    shipped search, at the unchanged ceilings. It used to be observed on the corpus, which
    held one conversation near enough to the cap that the fill survived; when the text mirror
    gained each row's attribution lines that conversation went over the cap and the ladder
    traded the fill for declared runs - kept on record by the test below, not hidden. A
    conversation that fits is the only fixture on which "the fill happened" is a statement
    about the mechanism rather than about how much room a corpus happened to leave.
    """
    from mailweave.envelope.reasons import ReplyChildOf, ReplyParentOf, WindowOffset
    from mailweave.surface.arguments import parse_search
    from mailweave.surface.partition import rendered_of
    from mailweave.surface.server import call

    manifest, box = corpus.manifest, corpus.box
    fixed = next(one for one in dummy_arms(manifest, box, specs=(FIXED_WINDOW,)))
    rows = 0
    # **No `except Exception: continue` here, and that absence is the test.** It had one, to
    # tolerate cases that could not complete against an older fixture, and the effect was that
    # the exact regression named above - baseline F raising instead of answering - was skipped
    # rather than reported: R232 could be planted (`_fill_reason`'s window branch disabled) and
    # this test still passed, because the searches that would have raised were the ones being
    # swallowed. A search that raises here is the defect, so it is left to raise.
    for case in corpus.cases.cases:
        envelope = fixed.service.search(parse_search({"query": case.query}))
        for source in envelope.sources:
            for row in source.messages:
                rows += 1
                assert row.reason is not None, "a row with no stated reason"
                assert row.reason.render(), "a reason that renders to nothing"
                if isinstance(row.reason, WindowOffset):
                    assert row.reason.anchor_id
                    assert "window" in row.reason.render()
    assert rows, "Baseline F produced no rows at all, which is the regression this guards"

    # The window-fill half, observed rather than constructed: the rows below are the ones the
    # shipped search produced, and a hand-made `WindowOffset` would prove nothing.
    fixed, shipped = dummy_arms(manifest, window_conversation(), specs=(FIXED_WINDOW, FULL))
    envelope = fixed.service.search(parse_search({"query": WINDOW_TOKEN}))
    assert envelope.truncated_by is None, (
        "a ladder step reduced the conversation, so what is observed is not the fill"
    )
    by_position = {row.position: row for source in envelope.sources for row in source.messages}
    hit = _window_id(WINDOW_HIT)
    assert {row.id for row in by_position.values() if row.role.value == "matched"} == {hit}
    assert set(by_position) == set(range(WINDOW_MESSAGES)), "every position is carried as a row"
    filled: dict[int, WindowOffset] = {}
    for position, row in by_position.items():
        if not isinstance(row.reason, WindowOffset):
            continue
        filled[position] = row.reason
        assert row.reason.anchor_id == hit, (position, row.reason)
        assert row.reason.offset == position - WINDOW_HIT, (position, row.reason)
        assert row.reason.render() == f"window {position - WINDOW_HIT:+d} around {hit}"
        assert row.content is not None, "a filled row carries text; a map stub is not a fill"
    assert sorted(filled) == [WINDOW_HIT - 2, WINDOW_HIT + 2], (
        "Baseline F did not fill exactly the +/-2 window around the hit: " + repr(filled)
    )
    # The reply floor outranks the fill: the +/-1 neighbours are there as parent and child.
    assert isinstance(by_position[WINDOW_HIT - 1].reason, ReplyParentOf)
    assert isinstance(by_position[WINDOW_HIT + 1].reason, ReplyChildOf)

    # The same rows through the tool boundary: under the host's cap, and the reason is the
    # last field of the row's line in the text a model reads.
    mirrored = rendered_of(call(fixed.service, "mailweave_search", {"query": WINDOW_TOKEN}))
    assert rendered_chars(mirrored.structured, mirrored.text) <= HOST_RESULT_CHAR_CAP
    lines = mirrored.text.split("\n")
    for position in filled:
        line = next(one for one in lines if one.startswith(f"  message {_window_id(position)} "))
        assert line.endswith(f"reason window {position - WINDOW_HIT:+d} around {hit}"), line

    # And the rows are the fixed window's, not something every arm does: the query-aware arm,
    # on the same conversation and ceilings, fills neither position.
    query_aware = shipped.service.search(parse_search({"query": WINDOW_TOKEN}))
    assert not [
        row.id
        for source in query_aware.sources
        for row in source.messages
        if isinstance(row.reason, WindowOffset)
    ]


#: The near-cap conversation Baseline F filled on 2026-09-21 and no longer does, pinned so the
#: size trade-off stays on record (2026-09-22). The smoke profile's ten-message conversation
#: `t0071` with three hits for `dropped`, which the case-file probe chose then because its +/-2
#: fill survived: its estimate was 594 characters under the host cap. The text mirror's
#: attribution and chronology lines took it 1,278 over, and the ladder now collapses the fill
#: into declared runs. Pinned by thread and query, and both are checked against the corpus.
NEAR_CAP_WINDOW_THREAD = "t0071"
NEAR_CAP_WINDOW_QUERY = "dropped"


def test_baseline_f_near_the_cap_trades_its_window_for_declared_recoverable_runs(
    corpus: Fixture,
) -> None:
    """The real size trade-off, kept as evidence: near the cap the window gives way, and says so.

    What must hold when it does: the response is served under the cap and declares itself
    partial and reduced, in both halves; the hits survive at body depth; every position of the
    thread is a row or a member of a declared run, never neither; a window position still
    carried states a real reason; every traded one sits in a run whose line the text prints
    and whose own call returns it at its position; and that row's own call reads its content.
    Nothing here asserts how much room there is - only that what did not fit is accounted for
    and recoverable.
    """
    from mailweave.surface.partition import rendered_of
    from mailweave.surface.server import call

    thread_id = f"t-{NEAR_CAP_WINDOW_THREAD}"
    pinned = [one for one in corpus.manifest.messages if one.thread_key == NEAR_CAP_WINDOW_THREAD]
    assert pinned and any(NEAR_CAP_WINDOW_QUERY in one.body for one in pinned), (
        "the pin no longer names the conversation it was taken from"
    )
    (fixed,) = dummy_arms(corpus.manifest, corpus.box, specs=(FIXED_WINDOW,))
    result = call(fixed.service, "mailweave_search", {"query": NEAR_CAP_WINDOW_QUERY})
    assert not result.is_error, result.content
    mirrored = rendered_of(result)
    payload, text = mirrored.structured, mirrored.text
    lines = text.split("\n")
    assert rendered_chars(payload, text) <= HOST_RESULT_CHAR_CAP

    # The trade is declared, in the structured half and in the text.
    assert payload["partial"] is True
    assert payload["truncated_by"] == "mailweave"
    assert "disclosed_token_ceiling" in payload["retrieval_report"]["budget_caps_hit"]
    assert f"{HOST_RESULT_CHAR_CAP}-character result cap" in payload["omission"]["bound"]
    assert lines[0].endswith("partial: yes; truncated_by: mailweave"), lines[0]

    source = next(one for one in payload["sources"] if one["thread_id"] == thread_id)
    total = source["stated_total"]
    rows = {row["position"]: row for row in source["messages"]}
    members: dict[int, tuple[dict[str, Any], str]] = {}
    for run in source["collapsed_runs"]:
        first, last = run["positions"]
        assert len(run["member_ids"]) == run["count"] == last - first + 1, run
        for position, member in zip(range(first, last + 1), run["member_ids"], strict=True):
            members[position] = (run, member)
    assert sorted([*rows, *members]) == list(range(total)), "a position is neither row nor run"

    hits = {position for position, row in rows.items() if row["role"] == "matched"}
    assert hits, "the evidence did not survive the trade"
    assert all(rows[position]["depth"] == "body_clean" for position in hits)
    window = {
        position
        for hit in hits
        for position in range(hit - 2, hit + 3)
        if 0 <= position < total and position not in hits
    }
    for position in sorted(window & set(rows)):
        kind = rows[position]["reason_detail"]["kind"]
        assert kind in ("window_offset", "reply_parent_of", "reply_child_of"), (position, kind)
    traded = sorted(window - set(rows))
    assert traded, "every window position is still carried; this is no longer the near-cap case"

    by_run: dict[tuple[int, int], list[int]] = {}
    for position in traded:
        run, _member = members[position]
        assert run["why"] == "disclosed_token_ceiling", run
        first, last = run["positions"]
        tool = run["affordance"]["tool"]
        assert (
            f"  collapsed positions {first}-{last}: {run['count']} messages not shown, "
            f"expand with {tool}"
        ) in lines
        by_run.setdefault((first, last), []).append(position)
    for positions in by_run.values():
        run = members[positions[0]][0]
        recovered = call(fixed.service, run["affordance"]["tool"], run["affordance"]["args"])
        assert not recovered.is_error, recovered.content
        page = rendered_of(recovered)
        assert rendered_chars(page.structured, page.text) <= HOST_RESULT_CHAR_CAP
        by_id = {row["id"]: row for one in page.structured["sources"] for row in one["messages"]}
        for position in positions:
            member = members[position][1]
            assert by_id[member]["position"] == position, (member, by_id.get(member))
            follow = by_id[member]["unabridged"]
            read = call(fixed.service, follow["tool"], follow["args"])
            assert not read.is_error, read.content
            carried = [
                row
                for one in (read.structured_content or {})["sources"]
                for row in one["messages"]
                if row["id"] == member
            ]
            assert carried and carried[0]["content"] is not None, member


def test_every_arm_runs_every_case_without_failing(corpus: Fixture) -> None:
    """A `FAILED` run is the product failing, and it is counted rather than averaged away."""
    resolved = corpus.resolved()
    runs = run_all(dummy_arms(corpus.manifest, corpus.box), resolved)
    failed = [(one.arm, one.case_id, one.declined) for one in runs if one.state is Measured.FAILED]
    assert failed == [], failed
    assert {one.arm for one in runs} == {spec.name for spec in SPECS}


# --- first response versus expansion-reached -------------------------------------------------


def test_first_response_and_expansion_reached_are_measured_separately(corpus: Fixture) -> None:
    """A message being named or reachable is not the caller having read it.

    The escalating dummy case is the shape: its evidence arrives at snippet depth in the first
    response - surfaced, not disclosed - and following the response's own `unabridged`
    affordance carries it. Reporting one number would either credit MailWeave for evidence
    nobody received, or blame it for evidence one call away.
    """
    resolved = corpus.resolved()
    full = dummy_arms(corpus.manifest, corpus.box)[0]
    runs = {one.case_id: one for one in run_all([full], resolved)}
    escalating = runs["selftest-escalates"]
    assert escalating.reach.first_response == frozenset()
    assert escalating.reach.after_expansion, "expansion reached nothing"
    assert escalating.reach.expansion_gained == escalating.reach.after_expansion
    assert escalating.reach.levels > 1
    assert escalating.reach.calls, "levels rose without a call being executed"


def test_the_recovery_driver_only_executes_calls_the_response_offered(corpus: Fixture) -> None:
    """R-07 is measured, not the harness's ingenuity.

    Every call followed is one the response put on the wire - a row's `unabridged`, a
    collapsed run's affordance, a withheld record's, a group's, a split source's, or an
    `affordances[]` entry. A driver that constructed its own calls would measure whether this
    harness can guess Gmail ids.
    """
    from mailweave.surface.arguments import parse_search
    from mailweave_harness.evaluation.arms import _recovery_calls

    resolved = corpus.resolved()
    full = dummy_arms(corpus.manifest, corpus.box)[0]
    case = next(one for one in resolved if one.case.case_id == "selftest-escalates")
    envelope = full.service.search(parse_search({"query": case.case.query}))
    offered = _recovery_calls(envelope, frozenset(case.required))
    assert offered, "the response offered no way back to evidence it did not carry"
    run = run_case(full, case)
    for name in run.reach.calls:
        assert name in {one.tool.value for one in offered}, name


def test_expansion_is_bounded_and_never_repeats_a_call(corpus: Fixture) -> None:
    """An unbounded driver measures the harness's patience rather than the product."""
    resolved = corpus.resolved()
    full = dummy_arms(corpus.manifest, corpus.box)[0]
    for run in run_all([full], resolved):
        assert run.reach.rounds <= MAX_RECOVERY_ROUNDS * 8, run.case_id
        assert run.reach.levels <= run.reach.rounds + 1


def test_the_four_measurement_states_are_kept_apart() -> None:
    """They license different conclusions, and collapsing any two says more than is known."""
    assert {one.value for one in Measured} == {
        "measured",
        "failed",
        "inconclusive",
        "unmeasured",
    }


def test_cut_loss_is_unmeasured_with_no_instrument_attached_rather_than_zero(
    corpus: Fixture,
) -> None:
    """A reranker is justified by the `cut_loss` it removes and by nothing else, so a cut loss
    of zero for a run that measured no pool would justify one on an absence."""
    resolved = corpus.resolved()
    full = dummy_arms(corpus.manifest, corpus.box)[0]
    blind = Arm(spec=full.spec, service=full.service, counter=full.counter)
    runs = run_all([blind], resolved)
    assert all(one.pool_state is Measured.UNMEASURED for one in runs)
    assert all(one.pool_source is None for one in runs)
    got = mean_cut_loss(
        runs,
        family="ranking_stress",
        arm="full",
        required={one.case.case_id: dict(one.required) for one in resolved},
    )
    assert got.value is None and got.state is Measured.UNMEASURED


def test_an_empty_semantic_block_is_not_read_as_a_pool(corpus: Fixture, tmp_path: Path) -> None:
    """Every search emits a `semantic` block whether or not the semantic rungs ran.

    Reading the empty one as the candidate set scores `pool_recall = 0` against a recall of 1
    and produces a **negative** `cut_loss`, which the metric's own model forbids: the shortlist
    is a subset of the pool. EP §6.4's second clause - the ids observed at the network layer -
    is what a lexically-answered case has instead, and it is what makes `cut_loss` measurable
    on the lexical arm the reranker has to beat.
    """
    resolved = corpus.resolved()
    arms = dummy_arms(corpus.manifest, corpus.box, traces=tmp_path)
    runs = run_all(arms, resolved)
    required = {one.case.case_id: dict(one.required) for one in resolved}
    sources = {one.pool_source for one in runs if one.pool_source}
    assert any("network layer" in one for one in sources), sources
    for arm in ("full", "sem-off"):
        got = mean_cut_loss(runs, family="ranking_stress", arm=arm, required=required)
        assert got.state is Measured.MEASURED, (arm, got)
        assert got.value is not None and got.value >= 0.0, (arm, got)


def test_one_f16_case_cannot_decide_whether_a_reranker_is_justified(
    corpus: Fixture, tmp_path: Path
) -> None:
    """EP §4.3 registers 8 F16 cases per seed; the dummy corpus has one.

    H2's own baseline is passed, because without it the clause reports the *missing arm*
    instead and this test would pass for the wrong reason - which is what it did for one run
    after `rerank_baseline_arm` was added (2026-09-16). The floor is what is under test here.
    """
    resolved = corpus.resolved()
    runs = run_all(dummy_arms(corpus.manifest, corpus.box, traces=tmp_path), resolved)
    results = {
        one.id: one
        for one in evaluate(
            runs,
            required={one.case.case_id: dict(one.required) for one in resolved},
            candidate_arm="full",
            semantic_baseline_arm="sem-off",
            selection_baseline_arm="fixed-window",
            rerank_baseline_arm="no-rerank",
        )
    }
    clause = next(one for one in results["H2"].clauses if one.name == "F16-cut-loss-falls")
    assert clause.verdict is Verdict.NOT_EVALUABLE
    # RR-04 now gates this clause on the cross-encoder having executed, and on the dummy
    # corpus it does not reach F16 at all - so the *reason* is the unexercised factor and the
    # floor is never reached. Both are NOT_EVALUABLE and the distinction matters: one says
    # "too few cases", the other says "this pair did not vary what it claims to vary". The
    # floor itself is held on a fixture that does exercise the factor, in
    # `tests/test_runner_repair_2026_09_17.py`.
    assert "did not exercise the factor" in clause.detail


def test_the_recoverability_report_separates_the_two_stages(corpus: Fixture) -> None:
    resolved = corpus.resolved()
    full = dummy_arms(corpus.manifest, corpus.box)[0]
    runs = run_all([full], resolved)
    report = recoverability(runs, arm="full")
    for key in (
        "evidence_in_first_response",
        "evidence_gained_by_expansion",
        "surfaced_never_carried_after_expansion",
        "never_named_at_all",
        "mean_levels_traversed",
        "failed_runs",
    ):
        assert key in report, key
    assert report["evidence_gained_by_expansion"] >= 1
