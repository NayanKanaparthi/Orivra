"""The query-free baseline is frozen, and these tests are the freeze.

The arm exists to be published beside the others, so a number from the full system is read
against what a system with no retrieval already gets. That only works if the baseline is fixed
*before* the cases it will be run on are authored: a baseline tuned after seeing the cases
measures the tuning. These tests pin the version string, the cue vocabularies and the weights,
so changing any of them is deliberate and visible, and invalidates comparisons against the old
version by failing here first.
"""

from __future__ import annotations

from mailweave_harness.evaluation import queryfree


def test_the_version_and_the_weights_are_the_frozen_ones() -> None:
    assert queryfree.VERSION == "qf-1"
    assert queryfree.WEIGHTS == {
        "assertion": 2, "hearsay": -3, "proposal": -3, "objection": -3, "reminder": -2,
        "hedge": -1,
    }


def test_the_cue_vocabularies_are_the_frozen_ones() -> None:
    sizes = {
        "ASSERTION": 8, "HEARSAY": 8, "PROPOSAL": 8, "REMINDER": 7, "HEDGE": 16, "OBJECTION": 6,
    }
    for name, count in sizes.items():
        assert len(getattr(queryfree, name)) == count, name
    assert "that is the position" in queryfree.ASSERTION
    assert "going from memory" in queryfree.HEARSAY
    assert "unless corrected" in queryfree.HEDGE


def test_it_never_sees_a_query_or_an_answer_key() -> None:
    """The type is the guarantee: a candidate carries text, subject, position and a timestamp.

    No role, no `is_distractor`, no sentinel, no query. A baseline that could see any of those
    would be measuring the manifest rather than the writing.
    """
    fields = set(queryfree.Candidate.__dataclass_fields__)
    assert fields == {"message_id", "position", "subject", "body", "epoch_ms"}
    import inspect

    source = inspect.getsource(queryfree)
    for forbidden in ("role", "is_distractor", "sentinel", "answer_key", "query"):
        assert f".{forbidden}" not in source, forbidden


def test_a_hedged_restatement_loses_to_an_unhedged_assertion() -> None:
    terms = ("Meridian",)
    firm = queryfree.Candidate(
        message_id="a", position=3, subject="Terms review: Meridian",
        body="Meridian notice stands at 63 days. That is the position.", epoch_ms=1_000,
    )
    stale = queryfree.Candidate(
        message_id="b", position=9, subject="Terms review: Meridian",
        body="Pack says Meridian at 41. Flagging in case that moved.", epoch_ms=9_000,
    )
    assert queryfree.score(firm, terms) is not None
    assert queryfree.score(stale, terms) is not None
    assert queryfree.score(firm, terms) > queryfree.score(stale, terms)
    assert queryfree.select_within_thread([firm, stale]) == "a"
    # And the trivial contrast does take the newest, which is what makes it a contrast.
    assert queryfree.select_latest_value_bearing([firm, stale]) == "b"


def test_a_message_that_names_nothing_in_the_subject_is_not_a_candidate() -> None:
    off_topic = queryfree.Candidate(
        message_id="c", position=1, subject="Terms review: Meridian",
        body="The Cobalt rota has 14 people on it.", epoch_ms=5_000,
    )
    assert queryfree.score(off_topic, ("Meridian",)) is None
