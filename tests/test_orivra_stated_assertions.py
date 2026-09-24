"""The §4.5 adversarial fixtures, run against the recogniser that decides the gates.

`test_orivra_contracts.py` proves the *contract* refuses a malformed source-stated edge.
That is not enough on its own: the contract's inputs are written by the same code that would
be wrong, so a builder filling the check in optimistically passes every test there. These
tests drive `orivra.recognise.stated`, which computes the gates from the message text and
the candidate set, and they are the ones that would catch a recogniser that cleared a
sentence it should not have.

The six fixtures the design names, plus three the design's own reasoning implies:

    negated withdrawal          quoted withdrawal        hypothetical withdrawal
    interrogative withdrawal    ambiguous-target         verbatim-but-wrong-document
    deictic with one candidate  hedged assertion         a language the cues do not cover

Each must produce **no edge**, or an inferred edge with the ambiguity stated. The two
positive cases at the end exist so that a recogniser which refused everything would fail
here rather than look maximally careful.
"""

from __future__ import annotations

import pytest

from orivra.contracts import StatedAssertionCheck
from orivra.recognise.stated import (
    Candidate,
    Cleared,
    Refused,
    check,
    clause_of,
    clear_clause,
    match_span,
    resolve_target,
)
from tests.orivra_build import NODE_A, NODE_B, body

#: Three drafts in scope, which is what makes "the earlier version" ambiguous.
CANDIDATES: tuple[Candidate, ...] = (
    Candidate(NODE_B, ("July 3 pricing draft",)),
    Candidate("gmail/message/mC", ("June 12 pricing draft",)),
    Candidate("gmail/message/mD", ("May 2 pricing draft",)),
)


def run(
    text: str,
    cue: str,
    referring: str,
    *,
    quoted_from: int | None = None,
    candidates: tuple[Candidate, ...] = CANDIDATES,
    language: str = "en",
) -> StatedAssertionCheck | Refused:
    start = text.index(cue)
    return check(
        body=body(text, quoted_from),
        start=start,
        end=start + len(cue),
        quoted=cue,
        asserting_node_id=NODE_A,
        referring_text=referring,
        candidates=candidates,
        language=language,
    )


# -- the six fixtures §4.5 names --------------------------------------------------------


def test_a_negated_withdrawal_produces_no_edge() -> None:
    outcome = run(
        "We are not withdrawing the July 3 pricing draft approval.",
        "not withdrawing the July 3 pricing draft",
        "the July 3 pricing draft",
    )
    assert isinstance(outcome, Refused)
    assert outcome.gate == "clause"
    assert "negation:not" in outcome.cues


def test_a_quoted_withdrawal_is_not_this_senders_assertion() -> None:
    """The span matches verbatim and belongs to somebody else."""
    text = "Thanks.\nOn Tue, Ada wrote: This supersedes the July 3 pricing draft."
    outcome = run(
        text,
        "supersedes the July 3 pricing draft",
        "the July 3 pricing draft",
        quoted_from=len("Thanks.\n"),
    )
    assert isinstance(outcome, Refused)
    assert outcome.gate == "quotation"
    assert outcome.cues == ("span_class:quoted",)


def test_a_hypothetical_withdrawal_produces_no_edge() -> None:
    outcome = run(
        "If certification fails we would withdraw the July 3 pricing draft.",
        "withdraw the July 3 pricing draft",
        "the July 3 pricing draft",
    )
    assert isinstance(outcome, Refused)
    assert outcome.gate == "clause"
    assert "hypothetical:if" in outcome.cues
    assert "hypothetical:would" in outcome.cues


def test_an_interrogative_withdrawal_produces_no_edge() -> None:
    outcome = run(
        "Should we withdraw the July 3 pricing draft?",
        "withdraw the July 3 pricing draft",
        "the July 3 pricing draft",
    )
    assert isinstance(outcome, Refused)
    assert outcome.gate == "clause"
    assert "interrogative:?" in outcome.cues


def test_an_ambiguous_target_produces_no_observed_edge_and_names_the_candidates() -> None:
    outcome = run(
        "This supersedes the earlier pricing draft.",
        "supersedes the earlier pricing draft",
        "the earlier pricing draft",
    )
    assert isinstance(outcome, Refused)
    assert outcome.gate == "target"
    assert set(outcome.candidates) == {candidate.node_id for candidate in CANDIDATES}


def test_a_span_that_matches_verbatim_while_pointing_at_nothing_produces_no_edge() -> None:
    """Verbatim is not enough: with no candidate matching, there is no node to point at."""
    outcome = run(
        "This supersedes the July 3 pricing draft.",
        "supersedes the July 3 pricing draft",
        "the July 3 pricing draft",
        candidates=(Candidate("gmail/message/mZ", ("Q4 headcount plan",)),),
    )
    assert isinstance(outcome, Refused)
    assert outcome.gate == "target"


# -- three the design's own reasoning implies -------------------------------------------


def test_a_deictic_phrase_does_not_resolve_even_with_one_candidate_in_scope() -> None:
    """Uniqueness that comes from the smallness of the candidate set is not identification.

    This is the failure `considered` was kept to expose: a resolver that sees one candidate
    resolves 'uniquely' every time.

    **The candidate's keys are chosen so that the deictic rule is the only thing refusing.**
    The first draft of this test used a candidate whose keys shared no words with the
    referring phrase, so it passed because the word overlap failed - and replant R134, which
    removes the deictic rule, was MISSED. A test that passes for a reason other than the one
    it names defends nothing, which is what the replant manifest exists to find.
    """
    would_match = Candidate(NODE_B, ("the earlier version",))
    assert would_match.matches("the earlier version"), (
        "the candidate must be one the resolver would otherwise match, or this test is not "
        "about the deictic rule"
    )
    outcome = run(
        "This supersedes the earlier version.",
        "supersedes the earlier version",
        "the earlier version",
        candidates=(would_match,),
    )
    assert isinstance(outcome, Refused)
    assert outcome.gate == "target"
    assert outcome.candidates == (NODE_B,)


def test_a_hedged_assertion_is_not_an_assertion() -> None:
    """Reporting 'the source states X' for 'this apparently supersedes X' overstates by
    exactly the hedge."""
    outcome = run(
        "This apparently supersedes the July 3 pricing draft.",
        "supersedes the July 3 pricing draft",
        "the July 3 pricing draft",
    )
    assert isinstance(outcome, Refused)
    assert outcome.cues == ("hedge:apparently",)


def test_a_clause_the_recogniser_cannot_read_is_refused_rather_than_cleared() -> None:
    outcome = run(
        "Dies ersetzt den Entwurf vom 3. Juli.",
        "ersetzt den Entwurf",
        "den Entwurf",
        language="de",
    )
    assert isinstance(outcome, Refused)
    assert outcome.gate == "language"


# -- the gates in isolation --------------------------------------------------------------


def test_a_span_that_does_not_string_match_its_source_is_refused() -> None:
    outcome = match_span(body(), 0, 4, "XXXX", node_id=NODE_A)
    assert isinstance(outcome, Refused)
    assert outcome.gate == "span"


def test_offsets_outside_the_body_are_refused() -> None:
    outcome = match_span(body(), 0, 9_000, "whatever", node_id=NODE_A)
    assert isinstance(outcome, Refused)
    assert outcome.gate == "span"


def test_the_clause_is_the_sentence_the_span_sits_in_and_never_splits_the_span() -> None:
    text = "Ship on Friday. This supersedes the July 3 pricing draft. Reply by noon."
    start = text.index("supersedes")
    left, right = clause_of(body(text), start, start + len("supersedes the July 3 draft"))
    clause = text[left:right]
    assert "Ship on Friday" not in clause
    assert "Reply by noon" not in clause


def test_a_neighbouring_sentences_cues_do_not_refuse_this_one() -> None:
    """The clause rule has to be narrow enough to be useful, or every long mail refuses."""
    outcome = run(
        "This supersedes the July 3 pricing draft. If anything changes I will resend.",
        "supersedes the July 3 pricing draft",
        "the July 3 pricing draft",
    )
    assert not isinstance(outcome, Refused)


def test_signature_and_forwarded_regions_are_not_assertable() -> None:
    text = "Regards,\nOn Mon, Bo wrote: This supersedes the July 3 pricing draft."
    outcome = clear_clause(body(text, quoted_from=len("Regards,\n")), 26, 61, language="en")
    assert isinstance(outcome, Refused)
    assert outcome.gate == "quotation"


def test_a_resolution_records_every_candidate_it_considered() -> None:
    resolution = resolve_target("the July 3 pricing draft", CANDIDATES)
    assert resolution.resolved_to == NODE_B
    assert len(resolution.considered) == 3


def test_two_matching_candidates_resolve_to_neither() -> None:
    twins = (
        Candidate(NODE_B, ("pricing draft",)),
        Candidate("gmail/message/mC", ("pricing draft",)),
    )
    resolution = resolve_target("the pricing draft", twins)
    assert resolution.resolved_to is None
    assert len(resolution.considered) == 2


# -- and the cases that must produce an edge --------------------------------------------


def test_a_plain_unambiguous_supersession_produces_a_usable_check() -> None:
    outcome = run(
        "This supersedes the July 3 pricing draft.",
        "supersedes the July 3 pricing draft",
        "the July 3 pricing draft",
    )
    assert isinstance(outcome, StatedAssertionCheck)
    assert outcome.target.resolved_to == NODE_B
    assert outcome.asserted_by == NODE_A
    assert outcome.clearance.cues_found == ()
    assert outcome.span.text == "supersedes the July 3 pricing draft"


def test_a_cleared_clause_records_the_signal_that_classified_the_region() -> None:
    outcome = clear_clause(body(), 5, 40, language="en")
    assert isinstance(outcome, Cleared)
    assert outcome.clearance.span_class_signals == ("no_structural_signal",)


@pytest.mark.parametrize(
    "sentence",
    [
        "We cannot accept the July 3 pricing draft.",
        "This replaces nothing in the July 3 pricing draft.",
        "Do we supersede the July 3 pricing draft?",
        "I think this supersedes the July 3 pricing draft.",
        "We plan to supersede the July 3 pricing draft.",
    ],
)
def test_every_cue_family_refuses_a_sentence_that_carries_it(sentence: str) -> None:
    """One sentence per family, so removing a family's cue list fails a named test."""
    cue = "the July 3 pricing draft"
    outcome = run(sentence, cue, cue)
    assert isinstance(outcome, Refused)
    assert outcome.gate == "clause"


# -- R-M1-003: the target gate, which a review defeated -------------------------------------
#
# The rule was a bidirectional subset - a match when the key's words were inside the
# reference OR the reference's words were inside the key. The first half is a hole: a
# candidate whose only key is a common word is a subset of every phrase containing it, so a
# document called "Pricing" matched "the July 3 pricing draft", and being the only match made
# the resolution "unique". A reviewer built an observed supersedes_stated edge from it,
# pointing at a document the sentence never named.


def test_a_candidate_whose_key_is_a_common_word_does_not_match_a_specific_phrase() -> None:
    """The exploit, as its own test. The reference carries "July" and "3"; a candidate that
    cannot account for them does not name it, whatever else it shares."""
    resolution = resolve_target(
        "the July 3 pricing draft", (Candidate("gmail/message/mZ", ("Draft",)),)
    )
    assert resolution.resolved_to is None
    assert resolution.considered == ("gmail/message/mZ",)


def test_a_common_word_key_does_not_win_against_an_unrelated_candidate() -> None:
    resolution = resolve_target(
        "the July 3 pricing draft",
        (
            Candidate("gmail/message/attacker", ("Pricing",)),
            Candidate("gmail/message/other", ("Q4 hiring loop notes",)),
        ),
    )
    assert resolution.resolved_to is None


def test_the_exploit_cannot_be_carried_through_the_gate_into_an_edge() -> None:
    """End to end: the reviewer's reproduction, run against the fixed recogniser."""
    text = "This supersedes the July 3 pricing draft."
    cue = "supersedes the July 3 pricing draft"
    start = text.index(cue)
    outcome = check(
        body=body(text),
        start=start,
        end=start + len(cue),
        quoted=cue,
        asserting_node_id=NODE_A,
        referring_text="the July 3 pricing draft",
        candidates=(Candidate("gmail/message/mZ", ("Pricing",)),),
        language="en",
    )
    assert isinstance(outcome, Refused)
    assert outcome.gate == "target"


def test_a_phrase_of_only_generic_words_identifies_nothing_however_it_is_spelled() -> None:
    """`DEICTIC_PHRASES` fired only on an exact whole-phrase match, so "the earlier pricing
    version" fell through it. The rule is now over tokens, so a phrase built entirely from
    stopwords and generic nouns refuses whatever its wording."""
    for phrase in (
        "the earlier version",
        "the previous draft",
        "the last document",
        "the older one",
        "that earlier file",
    ):
        resolution = resolve_target(phrase, (Candidate(NODE_B, (phrase,)),))
        assert resolution.resolved_to is None, phrase


def test_a_phrase_with_one_distinguishing_word_still_identifies() -> None:
    """The rule must not refuse everything: "the pricing draft" does identify the one
    pricing draft in scope, and a recogniser that refused it would have a positive rate of
    zero and look maximally careful."""
    resolution = resolve_target("the pricing draft", (Candidate(NODE_B, ("Q3 pricing draft v2",)),))
    assert resolution.resolved_to == NODE_B


def test_what_a_resolution_identifies_is_relative_to_the_candidate_set() -> None:
    """Stated rather than claimed away. The same phrase resolves with one pricing draft in
    scope and refuses with two, which is why `considered` is published beside the answer."""
    one = Candidate(NODE_B, ("Q3 pricing draft",))
    two = Candidate("gmail/message/mC", ("Q4 pricing draft",))
    assert resolve_target("the pricing draft", (one,)).resolved_to == NODE_B
    assert resolve_target("the pricing draft", (one, two)).resolved_to is None
