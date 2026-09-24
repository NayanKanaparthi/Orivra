"""Content properties of a generated corpus, as distinct from its structure.

Every test here names a defect an independent evaluator found in the corpus this generator
replaces, so a regression reads as the original finding rather than as an abstract assertion.
The coverage rules themselves are exercised in `test_coverage_rules.py`, which supplies one
negative fixture per rule; this module checks the corpus the rules are run against.
"""

from __future__ import annotations

import email
import email.utils
import re

import pytest

from mailweave_harness.seed.corpus import PROFILES, SizeProfile, generate, rfc2822
from mailweave_harness.seed.coverage import EVIDENCE_ROLES, audit, coverage
from mailweave_harness.seed.families import REGISTERED_N, SWEEP_FRACTIONS, sweep_position
from mailweave_harness.seed.manifest import MESSAGE_ROLES, Manifest, SeededMessage
from mailweave_harness.seed.world import BY_KEY, jaccard


@pytest.fixture(scope="module")
def sample() -> Manifest:
    return generate(master_seed=4311, size_profile="sample")


def strip(body: str) -> str:
    return re.sub(r"\n-- \n.*$", "", body, flags=re.S).strip()


def when(message: SeededMessage) -> float:
    return email.utils.parsedate_to_datetime(message.date_rfc2822).timestamp()


def test_bodies_are_not_all_the_same_shape(sample: Manifest) -> None:
    """R-M2-055: 2,452 messages held 345 distinct bodies once the boilerplate was stripped."""
    texts = [strip(one.body) for one in sample.messages]
    assert len(set(texts)) / len(texts) > 0.55
    assert sum(1 for one in texts if len(one) < 60) / len(texts) < 0.20


def test_every_message_declares_what_it_was_planted_to_be(sample: Manifest) -> None:
    assert {one.role for one in sample.messages} <= MESSAGE_ROLES
    assert len({one.role for one in sample.messages}) >= 10


def test_every_message_carries_the_same_kind_of_marker(sample: Manifest) -> None:
    """R-M2-046. The marker used to be on the answers and nowhere else, so `grep` solved eight
    families. It is now on everything, which is the only shape that carries no information."""
    assert all(len(one.sentinels) == 1 for one in sample.messages)
    evidence = [one for one in sample.messages if one.role in EVIDENCE_ROLES]
    assert evidence
    assert all(one.sentinels for one in evidence)
    assert all(one.sentinels for one in sample.messages)


def test_no_word_in_any_body_predicts_that_it_is_the_evidence(sample: Manifest) -> None:
    """The detector, run as a test. A word reaching most of the evidence at high precision is
    an answer oracle; `Reference token` reached 100% at 100%."""
    assert not [
        one for one in audit(sample) if one.rule == "no_discriminating_token"
    ]


def test_dates_advance_with_position_in_every_thread(sample: Manifest) -> None:
    """R-M2-048: this failed in 84 threads of 84, taking F2, F5, F13 and F17 with it."""
    assert not [one for one in audit(sample) if one.rule == "dates_advance"]


def test_a_decision_chain_runs_proposal_objection_confirmation_reminder(sample: Manifest) -> None:
    truth = next(one for one in sample.answer_key.threads if one.family == "F5")
    assert {"proposal", "objection", "confirmation", "reminder"} <= set(truth.roles_at)
    messages = [one for one in sample.messages if one.thread_key == truth.thread_key]
    at = {one.position: one for one in messages}
    confirmation = at[truth.roles_at["confirmation"][0]]
    reminder = at[truth.roles_at["reminder"][-1]]
    assert when(reminder) > when(confirmation)
    assert truth.answer in strip(confirmation.body)
    assert truth.older_value in strip(reminder.body)


def test_a_reversal_is_late_and_is_not_the_top_lexical_hit(sample: Manifest) -> None:
    """R-M2-047. The old corpus marked the first reinforcement as the evidence in eight threads
    of eight, and the reversal was the highest-scoring message in all eight."""
    from mailweave_harness.seed import lexical

    for truth in [one for one in sample.answer_key.threads if one.family == "F17"]:
        at = int(truth.facts["reversal_at"])
        assert truth.evidence_positions == (at,)
        bodies = [
            strip(one.body) for one in sample.messages if one.thread_key == truth.thread_key
        ]
        query = truth.facts["construction_query"]
        spots = [int(one) for one in truth.facts["reinforcements_at"].split(",")]
        assert min(lexical.rank_of(bodies, query, one) for one in spots) < lexical.rank_of(
            bodies, query, at
        )


def test_a_paraphrase_thread_states_its_fact_in_a_disjoint_vocabulary(sample: Manifest) -> None:
    for truth in [one for one in sample.answer_key.threads if one.family == "F4"]:
        evidence = next(
            one for one in sample.messages
            if one.thread_key == truth.thread_key
            and one.position == int(truth.facts["evidence_at"])
        )
        assert truth.paraphrase_of_fact
        assert jaccard(truth.paraphrase_of_fact, strip(evidence.body)) == 0.0


def test_a_hearsay_message_names_the_person_it_reports(sample: Manifest) -> None:
    """R-M2-052: the old generator emitted the literal string `participant 0` in all eight."""
    for truth in [one for one in sample.answer_key.threads if one.family == "F6"]:
        author = BY_KEY[truth.facts["author"]]
        reports = [
            one for one in sample.messages
            if one.thread_key == truth.thread_key and one.role == "hearsay"
        ]
        assert reports
        for one in reports:
            assert author.display in strip(one.body)
            assert one.sender != author.address
        assert not re.search(r"participant \d", " ".join(one.body for one in sample.messages))


def test_near_duplicates_differ_in_one_decisive_detail(sample: Manifest) -> None:
    """R-M2-053: the old candidates announced themselves with a `Superseded draft: ` prefix and
    were dated after the answer."""
    for truth in [one for one in sample.answer_key.threads if one.family == "F16"]:
        candidates = [
            one for one in sample.messages
            if one.thread_key == truth.thread_key and one.role == "near_duplicate"
        ]
        assert len(candidates) >= 4
        # Compared unframed and with the declared values masked. Every message is framed the
        # same way now, so two candidates that open differently are still near-duplicates; what
        # has to be identical is what is left once the shared frame and the value are removed.
        from mailweave_harness.seed.coverage import _unframed, _values

        skeletons = set()
        for one in candidates:
            text = _unframed(one.body)
            for value in sorted(_values(truth), key=len, reverse=True):
                text = text.replace(value, "<value>")
            # R-M2-068: no ordinal normalisation. The figures are the only difference.
            skeletons.add(text)
        assert len(skeletons) == 1, skeletons
        adopted = next(one for one in candidates if one.position == int(truth.facts["adopted_at"]))
        assert when(adopted) < max(when(one) for one in candidates)


def test_the_sweep_fractions_land_on_seven_distinct_positions(sample: Manifest) -> None:
    """At length 90 they land on EP §4.4's own rescaled list."""
    landed = sorted({sweep_position(90, one) for one in SWEEP_FRACTIONS})
    assert landed == [2, 6, 18, 33, 46, 75, 89]


def test_an_attachment_case_has_a_carrying_file_and_a_same_named_wrong_version(
    sample: Manifest,
) -> None:
    """The answer names the file; the figure the case turns on is inside it and in no body.

    EP §4.3 scores F8 as retrieving the carrying message and signalling the attachment, and
    scores extraction only if MailWeave claims it - which it does not (`AttachmentRow` is
    metadata only, `users.messages.attachments.get` is off the release surface, ADV-207).
    """
    truth = next(
        one for one in sample.answer_key.threads
        if one.family == "F8" and not one.continues
    )
    cover = next(
        one for one in sample.messages
        if one.thread_key == truth.thread_key and one.position == int(truth.facts["cover_at"])
    )
    carrier = next(one for one in cover.attachments if one.carries_the_fact)
    assert truth.answer == carrier.filename
    assert truth.facts["extraction_claimed"] == "no"
    inside = truth.facts["value_in_attachment"]
    assert inside in carrier.content
    assert all(inside not in strip(one.body) for one in sample.messages)
    assert len(carrier.content) > 100
    elsewhere = [
        part for one in sample.messages for part in one.attachments
        if part.filename == carrier.filename and one.rfc822_message_id != cover.rfc822_message_id
    ]
    assert elsewhere and all(part.content != carrier.content for part in elsewhere)


def test_the_wrong_version_conversation_declares_no_answer(sample: Manifest) -> None:
    """A decoy that inherits the situation's answer makes the corrupt copy look authoritative."""
    decoys = [
        one for one in sample.answer_key.threads if one.family == "F8" and one.continues
    ]
    assert decoys
    for truth in decoys:
        assert truth.answer == "", truth.thread_key
        assert truth.facts["is_the_wrong_version"] == "yes"


def test_an_attachment_survives_being_rendered_as_rfc2822(sample: Manifest) -> None:
    message = next(one for one in sample.messages if one.attachments)
    raw = rfc2822(message)
    assert "multipart/mixed" in raw
    parsed = email.message_from_string(raw)
    payloads = [
        part.get_payload(decode=True).decode("utf-8")
        for part in parsed.walk() if part.get_filename()
    ]
    assert payloads == [one.content for one in message.attachments]


def test_a_message_with_no_attachment_is_still_a_plain_single_part(sample: Manifest) -> None:
    message = next(one for one in sample.messages if not one.attachments)
    raw = rfc2822(message)
    assert "multipart" not in raw
    assert 'Content-Type: text/plain; charset="utf-8"' in raw


def test_every_registered_family_is_authorable_from_the_gate_profile() -> None:
    gate = generate(master_seed=5309, size_profile="gate")
    short = [one for one in coverage(gate) if one.shortfall]
    assert not short, [(one.family, one.registered, one.authorable) for one in short]


def test_the_small_profile_still_spans_every_family_and_every_sweep_position(
    sample: Manifest,
) -> None:
    built = {one.family for one in sample.answer_key.threads if one.family}
    assert built == set(REGISTERED_N)
    fractions = {
        int(one.facts["fraction"]) for one in sample.answer_key.threads if one.family == "F3"
    }
    assert fractions == set(SWEEP_FRACTIONS)


def test_a_profile_cannot_omit_a_registered_family() -> None:
    with pytest.raises(ValueError, match="no count for"):
        SizeProfile(
            name="partial",
            family_counts={"F1": 1},
            long_length=90,
            filler_threads=1,
            short_threads=1,
            situations=40,
        )


def test_a_profile_cannot_ask_for_more_than_a_family_is_registered_for() -> None:
    with pytest.raises(ValueError, match="exceed their registered counts"):
        SizeProfile(
            name="greedy",
            family_counts=dict(REGISTERED_N) | {"F1": REGISTERED_N["F1"] + 1},
            long_length=90,
            filler_threads=1,
            short_threads=1,
            situations=40,
        )


def test_the_sample_profile_is_not_the_smoke_profile() -> None:
    assert PROFILES["sample"].family_counts != PROFILES["smoke"].family_counts
    assert len(generate(master_seed=3, size_profile="sample").messages) < len(
        generate(master_seed=3, size_profile="smoke").messages
    )
