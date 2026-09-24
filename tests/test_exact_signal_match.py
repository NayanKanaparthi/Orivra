"""`exact_signal_match`, per the three enumerated branches of AD A.8a.

A.8a calls this predicate "the pivot of the design" and "the document's largest gameability
lever": D.3 rules 1 and 1b, D.5's firing condition, D.7's prohibition and A.7's L0 stop all
turn on it, and a broad reading does not fail the rubric - it *removes cases from* the
denominators of AD-05 and CG-SEM. So this file tests three things, not one:

  1. the unit table, per branch, firing and not firing;
  2. the **closure** - exactly three branches, no frequency input, no rarity threshold;
  3. what every branch has in common - a candidate that was not *executed* never fires -
     asserted over all three at once rather than three times over one case each.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from mailweave.constants import (
    EXACT_IDENTIFIER_MAX_HITS,
    EXACT_MSGID_HITS,
    EXACT_PHRASE_MAX_HITS,
    EXACT_PHRASE_MIN_TOKENS,
)
from mailweave.query import IdentifierKind, ParsedQuery, analyse, classify_identifier
from mailweave.retrieval.signals import ExactBranch, evaluate_exact_signal

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
UTC_ZONE = ZoneInfo("UTC")

#: A.8a's sentence, quoted rather than imported, so a change to the enum cannot silently
#: redefine what this file is checking.
DOCUMENTED_BRANCHES = {"E-a", "E-b", "E-c"}

MSGID = "<a1@mail.invalid>"
PHRASE = "the rollout window slipped"
IDENTIFIER = "INV-2026-0041"


def parse(query: str) -> ParsedQuery:
    return analyse(query, now=NOW, zone=UTC_ZONE)


def test_the_exact_signal_definition_is_closed_at_three_branches() -> None:
    """A.8a is "true iff exactly one of three enumerated branches holds"."""
    assert {branch.value for branch in ExactBranch} == DOCUMENTED_BRANCHES
    assert len(ExactBranch) == 3


def test_the_evaluator_takes_no_frequency_input() -> None:
    """ "corpus frequency is never consulted, and no frequency threshold may create an
    exact-signal match" - checked at the only place such a dial could be wired in."""
    parameters = set(inspect.signature(evaluate_exact_signal).parameters)

    assert parameters == {"parsed", "executed_query", "hit_count", "hit_texts"}
    forbidden = {"corpus", "frequency", "counts", "idf", "rarity", "threshold", "min_score"}
    assert not (parameters & forbidden)


# --- branch E-a: rfc822msgid ------------------------------------------------------------


def test_branch_ea_fires_on_an_executed_message_id_with_exactly_one_hit() -> None:
    signal = evaluate_exact_signal(
        parse(f"rfc822msgid:{MSGID}"),
        executed_query=f"rfc822msgid:{MSGID}",
        hit_count=EXACT_MSGID_HITS,
        hit_texts=("anything at all",),
    )

    assert signal.fired is True
    assert signal.branch is ExactBranch.E_A
    assert signal.hit_count == 1


@pytest.mark.parametrize("hits", [0, 2, 5])
def test_branch_ea_does_not_fire_at_any_hit_count_but_one(hits: int) -> None:
    """Identity means one message. Two hits is not identity, whatever the operator says."""
    signal = evaluate_exact_signal(
        parse(f"rfc822msgid:{MSGID}"),
        executed_query=f"rfc822msgid:{MSGID}",
        hit_count=hits,
        hit_texts=(),
    )

    assert signal.fired is False
    assert signal.branch is None


# --- branch E-b: verbatim phrase ---------------------------------------------------------


def test_branch_eb_fires_on_a_three_token_phrase_verified_locally() -> None:
    signal = evaluate_exact_signal(
        parse(f'"{PHRASE}"'),
        executed_query=f'"{PHRASE}"',
        hit_count=1,
        hit_texts=(f"Notes\nWe were told {PHRASE} by a week.",),
    )

    assert signal.fired is True
    assert signal.branch is ExactBranch.E_B
    assert signal.verified_locally is True
    assert signal.phrase_tokens >= EXACT_PHRASE_MIN_TOKENS


def test_branch_eb_does_not_take_gmails_word_for_the_phrase_match() -> None:
    """A.8a: "Gmail's phrase matching is not documented as literal; we do not take its word".

    This is the case that separates a real local verification from a comment claiming one:
    Gmail returns a hit, MailWeave looks, the phrase is not there, and the branch does not
    fire even though every other condition holds.
    """
    signal = evaluate_exact_signal(
        parse(f'"{PHRASE}"'),
        executed_query=f'"{PHRASE}"',
        hit_count=1,
        hit_texts=("A message about something else entirely.",),
    )

    assert signal.fired is False
    assert signal.verified_locally is False
    assert signal.phrase_tokens >= EXACT_PHRASE_MIN_TOKENS


def test_branch_eb_verification_folds_case_width_and_whitespace() -> None:
    """NFKC + case-folding + whitespace collapse, as A.8a specifies the comparison."""
    signal = evaluate_exact_signal(
        parse(f'"{PHRASE}"'),
        executed_query=f'"{PHRASE}"',
        hit_count=1,
        hit_texts=("...THE   ROLLOUT\nWINDOW  SLIPPED...",),
    )

    assert signal.fired is True
    assert signal.verified_locally is True


def test_a_phrase_shorter_than_the_published_minimum_is_not_a_candidate_at_all() -> None:
    parsed = parse('"rollout window"')

    assert parsed.qualifying_phrases == ()
    signal = evaluate_exact_signal(
        parsed,
        executed_query='"rollout window"',
        hit_count=1,
        hit_texts=("the rollout window is open",),
    )
    assert signal.fired is False


def test_stopwords_do_not_count_towards_the_three_token_bar() -> None:
    """ "a phrase of >=3 tokens **after stopword removal**"."""
    parsed = parse('"it is the of and"')

    assert parsed.qualifying_phrases == ()


@pytest.mark.parametrize("hits", [0, EXACT_PHRASE_MAX_HITS + 1, 9])
def test_branch_eb_does_not_fire_outside_its_published_hit_band(hits: int) -> None:
    signal = evaluate_exact_signal(
        parse(f'"{PHRASE}"'),
        executed_query=f'"{PHRASE}"',
        hit_count=hits,
        hit_texts=(f"...{PHRASE}...",) * max(hits, 1),
    )

    assert signal.fired is False


# --- branch E-c: structured identifier ----------------------------------------------------


def test_branch_ec_fires_on_a_published_identifier_shape_executed_as_a_quoted_token() -> None:
    signal = evaluate_exact_signal(
        parse(IDENTIFIER),
        executed_query=f'"{IDENTIFIER}"',
        hit_count=1,
        hit_texts=("a message",),
    )

    assert signal.fired is True
    assert signal.branch is ExactBranch.E_C


@pytest.mark.parametrize("hits", [0, EXACT_IDENTIFIER_MAX_HITS + 1])
def test_branch_ec_does_not_fire_outside_its_published_hit_band(hits: int) -> None:
    signal = evaluate_exact_signal(
        parse(IDENTIFIER), executed_query=f'"{IDENTIFIER}"', hit_count=hits, hit_texts=()
    )

    assert signal.fired is False


def test_the_identifier_lexicon_has_exactly_the_four_published_kinds() -> None:
    """A.8a's sentence enumerates four shapes; the enum is held to the sentence."""
    assert {kind.value for kind in IdentifierKind} == {
        "rfc822_message_id",
        "reference_code",
        "tracking_number",
        "iban",
    }


@pytest.mark.parametrize(
    ("token", "kind"),
    [
        ("<a1@mail.invalid>", IdentifierKind.RFC822_MESSAGE_ID),
        ("1Z999AA10123456784", IdentifierKind.TRACKING_NUMBER),
        ("LX123456789NZ", IdentifierKind.TRACKING_NUMBER),
        ("GB82WEST12345698765432", IdentifierKind.IBAN),
        ("INV-2026-0041", IdentifierKind.REFERENCE_CODE),
        ("PO/2026/7781", IdentifierKind.REFERENCE_CODE),
    ],
)
def test_every_identifier_kind_is_reached_by_a_case_of_its_own(
    token: str, kind: IdentifierKind
) -> None:
    identifier = classify_identifier(token)

    assert identifier is not None
    assert identifier.kind is kind


@pytest.mark.parametrize("token", ["rollout", "vendor", "quarter2", "the", "september2026"])
def test_an_ordinary_word_is_not_an_identifier(token: str) -> None:
    assert classify_identifier(token) is None


# --- closure and precedence ----------------------------------------------------------------


def test_branch_precedence_is_ea_then_eb_then_ec() -> None:
    """One query carrying all three candidates fires exactly one branch, the strongest.

    Only branch E-a may stop the ladder unconditionally (D.3 rule 1), so which branch is
    reported is not cosmetic - it decides whether `answer_type_presence` can veto the stop.
    """
    query = f'rfc822msgid:{MSGID} "{PHRASE}" {IDENTIFIER}'
    parsed = parse(query)

    assert parsed.rfc822msgid is not None
    assert parsed.qualifying_phrases
    assert parsed.identifiers

    assert (
        evaluate_exact_signal(parsed, executed_query=query, hit_count=1, hit_texts=(PHRASE,)).branch
        is ExactBranch.E_A
    )


BRANCH_CASES = {
    ExactBranch.E_A: (f"rfc822msgid:{MSGID}", f"rfc822msgid:{MSGID}", 1, (PHRASE,)),
    ExactBranch.E_B: (f'"{PHRASE}"', f'"{PHRASE}"', 1, (PHRASE,)),
    ExactBranch.E_C: (IDENTIFIER, f'"{IDENTIFIER}"', 1, ("a message",)),
}


def test_the_branch_case_table_covers_every_branch() -> None:
    assert set(BRANCH_CASES) == set(ExactBranch)


@pytest.mark.parametrize("branch", list(ExactBranch), ids=lambda b: b.value)
def test_no_branch_fires_on_a_candidate_that_was_never_executed(branch: ExactBranch) -> None:
    """The property all three share: A.8a requires the candidate to have been *executed*.

    Every branch's condition contains "was executed verbatim" / "was executed as a Gmail
    quoted phrase" / "executed as a quoted single-token query". A predicate that fired on a
    *parsed* candidate would let a rung claim identity for a query it never sent - the
    shape of a stop signal without a retrieval behind it. Asserted once over all three
    rather than three times over one, which is this project's recurring defect.
    """
    query, executed, hits, texts = BRANCH_CASES[branch]
    parsed = parse(query)

    assert (
        evaluate_exact_signal(
            parsed, executed_query=executed, hit_count=hits, hit_texts=texts
        ).branch
        is branch
    )
    assert (
        evaluate_exact_signal(
            parsed, executed_query="something else entirely", hit_count=hits, hit_texts=texts
        ).fired
        is False
    )


@pytest.mark.parametrize("branch", list(ExactBranch), ids=lambda b: b.value)
def test_the_trace_field_is_emitted_whether_or_not_the_branch_fires(
    branch: ExactBranch,
) -> None:
    """A.8a: "It is emitted whether it fires or not", with its firing inputs."""
    query, executed, hits, texts = BRANCH_CASES[branch]
    parsed = parse(query)
    for executed_query in (executed, "not the query"):
        fields = evaluate_exact_signal(
            parsed, executed_query=executed_query, hit_count=hits, hit_texts=texts
        ).as_trace_fields()
        assert set(fields) == {
            "fired",
            "branch",
            "phrase_tokens",
            "hit_count",
            "verified_locally",
        }
        assert fields["hit_count"] == hits


def test_false_in_every_other_case() -> None:
    """A.8a's closing sentence. A rare-looking word is not a signal; rarity was withdrawn."""
    parsed = parse("zeugmatic")

    assert parsed.identifiers == ()
    for hits in (1, 2, 3):
        assert (
            evaluate_exact_signal(
                parsed, executed_query="zeugmatic", hit_count=hits, hit_texts=("zeugmatic",)
            ).fired
            is False
        )
