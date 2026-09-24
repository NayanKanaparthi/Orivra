"""Negative fixtures for the situation-level construction checks.

`situations.check_situation` and `check_topic` run at import and during minting, so a template
that cannot support a family fails the build rather than the gate. They are checks, so the same
standard applies as to the coverage rules: each one is shown rejecting a situation built
without its property.
"""

from __future__ import annotations

from dataclasses import replace
from random import Random

import pytest

from mailweave_harness.seed import situations
from mailweave_harness.seed.situations import (
    Situation,
    audit_topics,
    check_situation,
    check_topic,
    mint_situations,
    mint_values,
)


@pytest.fixture(scope="module")
def good() -> Situation:
    return mint_situations(Random(4311), 1)[0]


def test_every_shipped_topic_renders_cleanly_against_every_entity() -> None:
    assert audit_topics() == ()


def test_a_question_sharing_a_word_with_its_evidence_is_rejected(good: Situation) -> None:
    """EP §4.5 tier 2. Without this the paraphrase families are tier 1 wearing a tier-2 label."""
    broken = replace(good, plain_question=good.formal_true + " Really?")
    assert any(one.rule == "T2_disjoint" for one in check_situation(broken))


def test_a_decoy_that_shares_nothing_with_the_question_is_rejected(good: Situation) -> None:
    broken = replace(good, plain_decoy="Unrelated remark about nothing whatsoever.")
    assert any(one.rule == "decoy_is_a_trap" for one in check_situation(broken))


def test_a_question_that_gives_away_the_answer_is_rejected(good: Situation) -> None:
    broken = replace(good, plain_question=f"Is it {good.answer}?")
    assert any(
        one.rule in {"question_withholds_the_answer", "T2_disjoint"}
        for one in check_situation(broken)
    )


def test_a_decoy_that_states_the_true_answer_is_rejected(good: Situation) -> None:
    """A distractor that happens to be right is not a distractor: picking it is not an error."""
    broken = replace(good, plain_decoy=f"It is {good.answer}, obviously.")
    assert any(one.rule == "decoys_are_wrong" for one in check_situation(broken))


def test_colliding_values_are_rejected(good: Situation) -> None:
    broken = replace(good, wrong=good.answer)
    assert any(one.rule == "values_are_distinct" for one in check_situation(broken))


def test_evidence_that_omits_its_own_answer_is_rejected(good: Situation) -> None:
    broken = replace(good, formal_true="Nothing to report on this at all.")
    assert any(one.rule == "evidence_carries_the_answer" for one in check_situation(broken))


def test_a_template_that_never_names_its_subject_is_rejected() -> None:
    """The defect itself: `defect_cause` did not name its entity, so two situations about
    different things rendered the same evidence sentence and two sweep threads shared one."""
    topic = replace(situations.TOPICS[0], formal="The figure is {answer}.")
    assert any(one.rule == "evidence_names_its_subject" for one in check_topic(topic))


def test_a_template_whose_question_never_names_its_subject_is_rejected() -> None:
    topic = replace(situations.TOPICS[0], question="What is it now?")
    assert any(one.rule == "question_names_its_subject" for one in check_topic(topic))


def test_a_template_carrying_no_value_is_rejected() -> None:
    topic = replace(situations.TOPICS[0], formal="Something changed on {formal}.")
    assert any(one.rule == "evidence_carries_a_value" for one in check_topic(topic))


def test_minting_refuses_to_hand_out_a_pair_twice() -> None:
    minted = mint_situations(Random(7), 300)
    assert len({one.key for one in minted}) == 300


def test_minting_is_balanced_across_topics_so_the_sweep_can_be_built() -> None:
    """A uniform draw left some topic short of the seven situations F3 needs, often enough that
    the small profile failed to build on the second seed tried."""
    for seed in (1, 2, 3, 4, 5):
        counts: dict[str, int] = {}
        for one in mint_situations(Random(seed), 120):
            counts[one.topic] = counts.get(one.topic, 0) + 1
        assert min(counts.values()) >= 7, (seed, counts)


def test_minted_values_never_contain_one_another() -> None:
    """"11" drawn against a taken "113" makes every decoy read as stating the answer."""
    for kind in ("days", "index", "rate", "measure", "date"):
        values = mint_values(kind, Random(3), 5)
        assert len(values) == 5
        for left in values:
            assert not any(left != right and left in right for right in values)


def test_asking_for_more_situations_than_exist_is_refused() -> None:
    with pytest.raises(ValueError, match="Reusing a"):
        mint_situations(Random(1), 100_000)
