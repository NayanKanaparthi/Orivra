"""One negative fixture per coverage rule.

The previous coverage report passed a corpus that an independent reader found unauthorable,
because seven of its seventeen rules had no failing case: they counted the same ninety-six
messages three times, or counted a property every thread had, or multiplied capacity by seven
(R-M2-045). A rule nobody has seen fail is not a check.

So every rule in `coverage.RULES` gets an entry here. Each mutates a real generated corpus to
remove exactly the property the rule names, and asserts the rule then reports it. Several of
the mutations are the historical defect itself, restated: `f17_points_at_the_reinforcement`
is R-M2-047, `f6_unsubstituted_placeholder` is R-M2-052, `no_discriminating_token` is
R-M2-046, and `dates_advance` is R-M2-048. If any of those stops failing, the corpus has
regressed to the state an independent evaluator rejected.

`test_every_rule_has_a_negative_fixture` is the gate on the gate: a rule added without a
fixture fails the suite.
"""

from __future__ import annotations

import datetime as dt
import email.utils
from typing import Callable

import pytest

from mailweave_harness.seed import coverage
from mailweave_harness.seed.corpus import generate
from mailweave_harness.seed.manifest import Manifest


@pytest.fixture(scope="module")
def corpus() -> Manifest:
    return generate(master_seed=4311, size_profile="sample")


def _edit(manifest: Manifest, messages=None, threads=None) -> Manifest:
    """A manifest with parts replaced and no re-validation.

    Deliberate: these fixtures build corpora the model would reject, which is the point - the
    rule has to be the thing that catches them, not pydantic.
    """
    key = manifest.answer_key.model_copy(
        update={"threads": tuple(threads)} if threads is not None else {}
    )
    update: dict[str, object] = {"answer_key": key}
    if messages is not None:
        update["messages"] = tuple(messages)
    return manifest.model_copy(update=update)


def _threads(manifest: Manifest, family: str):
    return [
        one for one in manifest.answer_key.threads
        if one.family == family and not one.continues and not one.cross_thread_decoy_for
    ]


def _swap(manifest: Manifest, thread_key: str, position: int, **fields) -> Manifest:
    out = []
    for one in manifest.messages:
        if one.thread_key == thread_key and one.position == position:
            one = one.model_copy(update=fields)
        out.append(one)
    return _edit(manifest, messages=out)


def _retruth(manifest: Manifest, thread_key: str, **fields) -> Manifest:
    out = [
        one.model_copy(update=fields) if one.thread_key == thread_key else one
        for one in manifest.answer_key.threads
    ]
    return _edit(manifest, threads=out)


def _shift(stamp: str, days: int) -> str:
    when = email.utils.parsedate_to_datetime(stamp) + dt.timedelta(days=days)
    return email.utils.format_datetime(when)


# --------------------------------------------------------------------------------- mutations

def break_uniform_reference(manifest: Manifest) -> Manifest:
    """The marker only on the answers - the shape of R-M2-046."""
    out = [
        one if one.role in coverage.EVIDENCE_ROLES else one.model_copy(update={"sentinels": ()})
        for one in manifest.messages
    ]
    return _edit(manifest, messages=out)


def break_no_discriminating_token(manifest: Manifest) -> Manifest:
    """`Reference token` back on the evidence and nowhere else. This is R-M2-046 exactly."""
    # Prepended, not appended: the rule reads the body with the signature block stripped, so
    # a marker placed after it would be invisible - which the first version of this fixture was.
    out = [
        one.model_copy(update={"body": "Reference token: marker\n" + one.body})
        if one.role in coverage.EVIDENCE_ROLES else one
        for one in manifest.messages
    ]
    return _edit(manifest, messages=out)


def break_shape_carries_no_signal(manifest: Manifest) -> Manifest:
    """Strip the frame from every planted message and leave it on filler.

    This is the defect an independent evaluator found after the first rebuild: filler was
    opener-topic-closer and everything decisive was a bare assertion, so counting sentences
    separated them with recall 0.98 and a ninety-message thread became four candidates.
    """
    from mailweave_harness.seed import voice

    out = []
    for one in manifest.messages:
        if one.role != "filler":
            text = coverage._strip_reference(one.body)
            for phrase in voice.LEAD_INS:
                if text.startswith(phrase):
                    text = text[len(phrase):].strip()
            for phrase in voice.CLOSERS:
                if text.endswith(phrase):
                    text = text[: -len(phrase)].strip()
            one = one.model_copy(
                update={"body": f"{text}\n-- \nx\nRef {one.sentinels[0]}"}
            )
        out.append(one)
    return _edit(manifest, messages=out)


def break_f10_extra(manifest: Manifest) -> Manifest:
    return break_f10(manifest)


def break_dates_advance(manifest: Manifest) -> Manifest:
    """A thread whose replies precede their parents - R-M2-048, in one thread instead of 84."""
    key = manifest.answer_key.threads[0].thread_key
    out = [
        one.model_copy(update={"date_rfc2822": _shift(one.date_rfc2822, -3 * one.position)})
        if one.thread_key == key else one
        for one in manifest.messages
    ]
    return _edit(manifest, messages=out)


def break_body_diversity(manifest: Manifest) -> Manifest:
    """Every filler message identical - the corpus R-M2-055 described."""
    out = [
        one.model_copy(update={"body": f"Noted.\n-- \nx\nRef {one.sentinels[0]}"})
        if one.role == "filler" else one
        for one in manifest.messages
    ]
    return _edit(manifest, messages=out)


def break_distractors_are_wrong(manifest: Manifest) -> Manifest:
    truth = next(one for one in manifest.answer_key.threads if one.family == "F5" and one.answer)
    victim = next(
        one for one in manifest.messages
        if one.thread_key == truth.thread_key and one.is_distractor and one.role != "hearsay"
    )
    return _swap(
        manifest, truth.thread_key, victim.position,
        body=f"Actually it is {truth.answer}.\n-- \nx\nRef {victim.sentinels[0]}",
    )


def break_siblings_agree(manifest: Manifest) -> Manifest:
    """Two unrelated conversations under one subject, disagreeing - R-M2-050."""
    pair = [one for one in manifest.answer_key.threads if one.family and one.answer][:2]
    out = [
        one.model_copy(update={"subject": "Shared subject"}) if one in pair else one
        for one in manifest.answer_key.threads
    ]
    return _edit(manifest, threads=out)


def break_f1(manifest: Manifest) -> Manifest:
    truth = _threads(manifest, "F1")[0]
    token = truth.facts["identifier"]
    victim = next(one for one in manifest.messages if one.role == "filler")
    return _swap(
        manifest, victim.thread_key, victim.position,
        body=f"Also see {token} on this.\n-- \nx\nRef {victim.sentinels[0]}",
    )


def break_f2(manifest: Manifest) -> Manifest:
    truth = _threads(manifest, "F2")[0]
    facts = dict(truth.facts) | {"subject_person": "pieter"}
    return _retruth(manifest, truth.thread_key, facts=facts)


def break_f3(manifest: Manifest) -> Manifest:
    """The evidence not where the answer key says it is."""
    truth = _threads(manifest, "F3")[0]
    facts = dict(truth.facts) | {"evidence_at": "1"}
    return _retruth(manifest, truth.thread_key, facts=facts)


def break_f4(manifest: Manifest) -> Manifest:
    """Evidence written in the query's own words, so tier 2 is not tier 2."""
    truth = _threads(manifest, "F4")[0]
    at = int(truth.facts["evidence_at"])
    message = next(
        one for one in manifest.messages
        if one.thread_key == truth.thread_key and one.position == at
    )
    return _swap(
        manifest, truth.thread_key, at,
        body=f"{truth.paraphrase_of_fact} It is {truth.answer}.\n-- \nx\nRef "
             f"{message.sentinels[0]}",
    )


def break_f5(manifest: Manifest) -> Manifest:
    """The reminder before the confirmation, so recency is no longer a trap."""
    truth = _threads(manifest, "F5")[0]
    at = int(truth.facts["reminder_at"])
    message = next(
        one for one in manifest.messages
        if one.thread_key == truth.thread_key and one.position == at
    )
    return _swap(
        manifest, truth.thread_key, at,
        date_rfc2822=_shift(message.date_rfc2822, -400),
    )


def break_f6(manifest: Manifest) -> Manifest:
    """The literal unsubstituted placeholder. This is R-M2-052."""
    truth = _threads(manifest, "F6")[0]
    victim = next(
        one for one in manifest.messages
        if one.thread_key == truth.thread_key and one.role == "hearsay"
    )
    return _swap(
        manifest, truth.thread_key, victim.position,
        body=f"participant 0 said it is fine.\n-- \nx\nRef {victim.sentinels[0]}",
    )


def break_f7(manifest: Manifest) -> Manifest:
    """One conversation carrying both halves, so nothing is cross-thread - R-M2-050."""
    truth = _threads(manifest, "F7")[0]
    at = int(truth.facts["evidence_at"])
    message = next(
        one for one in manifest.messages
        if one.thread_key == truth.thread_key and one.position == at
    )
    return _swap(
        manifest, truth.thread_key, at,
        body=f"{message.body.splitlines()[0]} The charge is {truth.facts['charge']}."
             f"\n-- \nx\nRef {message.sentinels[0]}",
    )


def break_f8(manifest: Manifest) -> Manifest:
    """The covering body states the fact, so the attachment is decoration.

    What has to appear in the body is the *figure inside the file*, not the declared answer:
    since the F8 answer became the filename, a body repeating the answer repeats the name of
    an attachment it already names, which is not the defect this fixture stands for.
    """
    truth = next(
        one for one in _threads(manifest, "F8")
        if one.facts.get("value_in_attachment") and not one.continues
    )
    at = int(truth.facts["cover_at"])
    inside = truth.facts["value_in_attachment"]
    message = next(
        one for one in manifest.messages
        if one.thread_key == truth.thread_key and one.position == at
    )
    return _swap(
        manifest, truth.thread_key, at,
        body=f"The agreed figure is {inside}.\n-- \nx\nRef {message.sentinels[0]}",
    )


def break_f10(manifest: Manifest) -> Manifest:
    """A control that was settled after all."""
    truth = _threads(manifest, "F10")[0]
    victim = next(
        one for one in manifest.messages
        if one.thread_key == truth.thread_key and one.role == "objection"
    )
    return _swap(manifest, truth.thread_key, victim.position, role="confirmation")


def break_f11(manifest: Manifest) -> Manifest:
    """The trap no longer outranks its evidence, so nothing has to escalate."""
    truth = _threads(manifest, "F11")[0]
    at = int(truth.facts["decoy_at"])
    message = next(
        one for one in manifest.messages
        if one.thread_key == truth.thread_key and one.position == at
    )
    return _swap(
        manifest, truth.thread_key, at,
        body=f"Fine by me.\n-- \nx\nRef {message.sentinels[0]}",
    )


def break_f11_top(manifest: Manifest) -> Manifest:
    """The trap still beats its evidence, but an ordinary filler beats them both.

    This is `t0031` restated: the pair relationship `f11` checks held while the thread's best
    lexical hit was filler. Written so `f11` itself still passes on the result - otherwise the
    fixture would prove only that the old rule works.
    """
    truth = _threads(manifest, "F11")[0]
    decoy_at = int(truth.facts["decoy_at"])
    evidence_at = int(truth.facts["evidence_at"])
    query = truth.facts["construction_query"]
    group = [one for one in manifest.messages if one.thread_key == truth.thread_key]
    spare = next(
        one for one in group
        if one.position not in {0, decoy_at, evidence_at} and one.role == "filler"
    )
    # The query three times over: enough term frequency to top a BM25 ranking without touching
    # either of the two messages the pair rule reads.
    return _swap(
        manifest, truth.thread_key, spare.position,
        body=f"{query} {query} {query}\n-- \nx\nRef {spare.sentinels[0]}",
    )


def break_f12(manifest: Manifest) -> Manifest:
    """The exact match stops being the top hit, so escalating is no longer punished."""
    truth = _threads(manifest, "F12")[0]
    at = int(truth.facts["evidence_at"])
    message = next(
        one for one in manifest.messages
        if one.thread_key == truth.thread_key and one.position == at
    )
    return _swap(
        manifest, truth.thread_key, at,
        body=f"Yes.\n-- \nx\nRef {message.sentinels[0]}",
    )


def break_f13(manifest: Manifest) -> Manifest:
    """The answer moved to before the event it is supposed to follow."""
    truth = _threads(manifest, "F13")[0]
    at = int(truth.facts["evidence_at"])
    message = next(
        one for one in manifest.messages
        if one.thread_key == truth.thread_key and one.position == at
    )
    return _swap(
        manifest, truth.thread_key, at, date_rfc2822=_shift(message.date_rfc2822, -60)
    )


def break_f14(manifest: Manifest) -> Manifest:
    """The same-name decoy replaced by someone with a different name."""
    truth = _threads(manifest, "F14")[0]
    facts = dict(truth.facts) | {"same_name_decoy": "sanjay"}
    return _retruth(manifest, truth.thread_key, facts=facts)


def break_f15(manifest: Manifest) -> Manifest:
    """The orphan given reference headers, so Gmail files it with the thread after all."""
    orphan = next(one for one in manifest.answer_key.threads if one.orphan)
    parent = next(
        one for one in manifest.messages if one.thread_key != orphan.thread_key
    ).rfc822_message_id
    return _swap(
        manifest, orphan.thread_key, 0, in_reply_to=parent, references=(parent,)
    )


def break_f16_key(manifest: Manifest) -> Manifest:
    """The key back on the confirmation, which names the revision and carries no value."""
    truth = _threads(manifest, "F16")[0]
    return _retruth(
        manifest, truth.thread_key,
        evidence_positions=(int(truth.facts["confirmation_at"]),),
    )


def break_f16(manifest: Manifest) -> Manifest:
    """The adopted revision becomes the newest, so recency wins - R-M2-053's inversion."""
    truth = _threads(manifest, "F16")[0]
    spots = [int(one) for one in truth.facts["revisions_at"].split(",")]
    facts = dict(truth.facts) | {"adopted_at": str(spots[-1])}
    return _retruth(manifest, truth.thread_key, facts=facts)


def break_f17(manifest: Manifest) -> Manifest:
    """The answer key back on the first reinforcement. This is R-M2-047 exactly."""
    truth = _threads(manifest, "F17")[0]
    first = int(truth.facts["reinforcements_at"].split(",")[0])
    return _retruth(manifest, truth.thread_key, evidence_positions=(first,))


def break_older_value_is_older(manifest: Manifest) -> Manifest:
    """Declare the superseded rendering at the newest position. This is F2's shipped state."""
    truth = next(
        one for one in manifest.answer_key.threads
        if one.facts.get("older_at") and one.family == "F2"
    )
    group = sorted(
        (one for one in manifest.messages if one.thread_key == truth.thread_key),
        key=lambda one: email.utils.parsedate_to_datetime(one.date_rfc2822),
    )
    facts = dict(truth.facts) | {"older_at": str(group[-1].position)}
    return _retruth(manifest, truth.thread_key, facts=facts)


def break_f7_halves_each_contested(manifest: Manifest) -> Manifest:
    """Turn the figure half's competing estimate back into ordinary traffic."""
    primary = _threads(manifest, "F7")[0]
    other = next(
        one for one in manifest.answer_key.threads
        if one.continues == primary.scenario_key
    )
    out = []
    for one in manifest.messages:
        if one.thread_key == other.thread_key and one.role in coverage._DISTRACTOR_ROLES:
            one = one.model_copy(update={"role": "filler"})
        out.append(one)
    return _edit(manifest, messages=out)


def break_f12_query(manifest: Manifest) -> Manifest:
    """The construction query back to the evidence sentence entire, answer value and all."""
    truth = _threads(manifest, "F12")[0]
    evidence = next(
        one for one in manifest.messages
        if one.thread_key == truth.thread_key and one.position == int(truth.facts["evidence_at"])
    )
    facts = dict(truth.facts)
    facts["construction_query"] = coverage._unframed(evidence.body)
    return _retruth(manifest, truth.thread_key, facts=facts)


def break_f15_split_cause(manifest: Manifest) -> Manifest:
    """The old note back, claiming a ceiling this corpus holds unsplit conversations past."""
    truth = next(
        one for one in manifest.answer_key.threads
        if one.family == "F15" and one.facts.get("shape") == "ceiling_split"
        and not one.continues
    )
    return _retruth(
        manifest, truth.thread_key,
        answer_note=(
            "Part one of a conversation that reached the 90-message ceiling of EP §3.8. It "
            "ends on the superseded position."
        ),
    )


def break_f16_mechanism(manifest: Manifest) -> Manifest:
    """Number the candidates again, which is the second differing detail and an exact key."""
    truth = _threads(manifest, "F16")[0]
    spots = [int(one) for one in truth.facts["revisions_at"].split(",")]
    out = []
    for one in manifest.messages:
        if one.thread_key == truth.thread_key and one.position in spots:
            ordinal = spots.index(one.position) + 1
            one = one.model_copy(update={"body": f"Revision {ordinal}. " + one.body})
        out.append(one)
    return _edit(manifest, messages=out)


def break_f17_chain(manifest: Manifest) -> Manifest:
    """The reversal replies to the message before it instead of to a reinforcement.

    This is the shipped state: `corpus.py` threads a line with no declared parent onto its
    predecessor, and in both instances that predecessor was ordinary filler.
    """
    truth = _threads(manifest, "F17")[0]
    at = int(truth.facts["reversal_at"])
    group = sorted(
        (one for one in manifest.messages if one.thread_key == truth.thread_key),
        key=lambda one: one.position,
    )
    return _swap(
        manifest, truth.thread_key, at, in_reply_to=group[at - 1].rfc822_message_id,
    )


def break_f13_chain(manifest: Manifest) -> Manifest:
    """The acceptance says what it accepted, so the References header carries nothing."""
    truth = _threads(manifest, "F13")[0]
    at = int(truth.facts["acceptance_at"])
    message = next(
        one for one in manifest.messages
        if one.thread_key == truth.thread_key and one.position == at
    )
    return _swap(
        manifest, truth.thread_key, at,
        body=(
            f"Accepting that. {truth.answer} is what I take the position to be now.\n-- \nx\n"
            f"Ref {message.sentinels[0]}"
        ),
    )


def break_scaffolding_not_family_exclusive(manifest: Manifest) -> Manifest:
    """A scaffolding sentence written inline by one builder, in one family and nowhere else.

    This is the shape of the shipped state: `grep "Everyone on this list is on it for the
    duration"` returned every F14 conversation and no other message in the corpus. The
    sentence here is invented rather than borrowed, because the repair put F14's real one into
    a bank that ordinary traffic draws on everywhere - so reusing it would test the repair
    instead of the rule.
    """
    # F15, because the rule's floor is three conversations and its null is the family's share
    # of messages: F15 has eight short conversations in this profile and a tenth of the text,
    # which is the shape of a real marker. F14 has two, which the rule cannot see and says so.
    keys = {
        one.thread_key for one in manifest.answer_key.threads if one.family == "F15"
    }
    out = []
    for one in manifest.messages:
        if one.thread_key in keys:
            one = one.model_copy(update={
                "body": "Filed under the standing arrangement for this group. " + one.body
            })
        out.append(one)
    return _edit(manifest, messages=out)


def break_role_positions_vary(manifest: Manifest) -> Manifest:
    """Give every F14 conversation the same role-position map. This is the shipped layout."""
    threads = [one for one in manifest.answer_key.threads if one.family == "F14"]
    assert len(threads) >= 2, "the profile must build more than one F14 conversation"
    shared = dict(threads[0].roles_at)
    out = [
        one.model_copy(update={"roles_at": dict(shared)}) if one.family == "F14" else one
        for one in manifest.answer_key.threads
    ]
    return _edit(manifest, threads=out)


def break_hour_independent_of_role(manifest: Manifest) -> Manifest:
    """Send every trap after 13:00 and everything else before it.

    The shipped corpus was 11 of 11 after 13:00 for `trap_decoy`; this is that, sharpened
    enough that the test's own floor of thirty messages is cleared by the roles either side.
    """
    out = []
    for one in manifest.messages:
        when = email.utils.parsedate_to_datetime(one.date_rfc2822)
        hour = 16 if one.role in coverage._DISTRACTOR_ROLES else 10
        out.append(one.model_copy(
            update={"date_rfc2822": email.utils.format_datetime(when.replace(hour=hour))}
        ))
    return _edit(manifest, messages=out)


NEGATIVES: dict[str, Callable[[Manifest], Manifest]] = {
    "uniform_reference": break_uniform_reference,
    "no_discriminating_token": break_no_discriminating_token,
    "shape_carries_no_signal": break_shape_carries_no_signal,
    "dates_advance": break_dates_advance,
    "body_diversity": break_body_diversity,
    "distractors_are_wrong": break_distractors_are_wrong,
    "siblings_agree": break_siblings_agree,
    "f1": break_f1,
    "f2": break_f2,
    "f3": break_f3,
    "f4": break_f4,
    "f5": break_f5,
    "f6": break_f6,
    "f7": break_f7,
    "f8": break_f8,
    "f10": break_f10,
    "f11": break_f11,
    "f11_top": break_f11_top,
    "f12": break_f12,
    "f13": break_f13,
    "f14": break_f14,
    "f15": break_f15,
    "f16": break_f16,
    "f17": break_f17,
    "older_value_is_older": break_older_value_is_older,
    "f7_halves_each_contested": break_f7_halves_each_contested,
    "f12_query": break_f12_query,
    "f15_split_cause": break_f15_split_cause,
    "f16_mechanism": break_f16_mechanism,
    "f17_chain": break_f17_chain,
    "f13_chain": break_f13_chain,
    "scaffolding_not_family_exclusive": break_scaffolding_not_family_exclusive,
    "role_positions_vary": break_role_positions_vary,
    "hour_independent_of_role": break_hour_independent_of_role,
}


def test_every_rule_has_a_negative_fixture() -> None:
    named = {one.name for one in coverage.RULES}
    assert named == set(NEGATIVES), (
        f"rules without a negative fixture: {sorted(named - set(NEGATIVES))}; fixtures without "
        f"a rule: {sorted(set(NEGATIVES) - named)}. A rule nobody has seen fail is not a check, "
        "and that is what R-M2-045 was"
    )
    assert coverage.RULES_WITHOUT_NEGATIVES == ()


def test_the_clean_corpus_passes_every_rule(corpus: Manifest) -> None:
    assert coverage.audit(corpus) == ()


def test_f8_rejects_a_decoy_that_declares_an_answer(corpus: Manifest) -> None:
    """The wrong-version conversation must not claim the authentic figure as its truth.

    It inherited the situation's default answer once, so the manifest declared the right
    figure as the truth of the thread holding the corrupt copy. A case author joining on
    `answer` would have pointed a case at the decoy and scored a figure it does not contain.
    """
    view = coverage.View(corpus)
    decoy = next(one for one in view.family("F8") if one not in view.primary("F8"))
    broken = _retruth(corpus, decoy.thread_key,
                      answer=decoy.facts.get("value_in_attachment", "9.4mm"))
    found = [one for one in coverage._f8(coverage.View(broken))
             if one.rule == "f8_decoy_declares_no_answer"]
    assert found, (
        "the F8 rule accepted a decoy conversation declaring an answer, which is the shape "
        "the manifest actually had"
    )


@pytest.mark.parametrize("name", sorted(NEGATIVES))
def test_each_rule_rejects_a_corpus_without_its_property(corpus: Manifest, name: str) -> None:
    rule = next(one for one in coverage.RULES if one.name == name)
    broken = NEGATIVES[name](corpus)
    found = rule.check(coverage.View(broken))
    assert found, (
        f"{name} passed a corpus with the property it names removed. Its assertion - "
        f"{rule.asserts!r} - is therefore not being checked"
    )


@pytest.mark.parametrize("name", sorted(NEGATIVES))
def test_a_broken_family_loses_its_authorable_count(corpus: Manifest, name: str) -> None:
    """A finding has to move the number the report publishes, not just print a line."""
    rule = next(one for one in coverage.RULES if one.name == name)
    broken = NEGATIVES[name](corpus)
    reported = {one.family for one in rule.check(coverage.View(broken))}
    if "corpus" in reported:
        assert all(one.authorable == 0 for one in coverage.coverage(broken)), (
            "a defect the rule attributes to the corpus leaves every family unauthorable, "
            "because it applies to all of them"
        )
        return
    # Several rules are corpus-wide in scope and thread-specific in attribution: a thread whose
    # dates run backwards spoils that thread, not the corpus. Those must still move the number
    # their finding names.
    before = {one.family: one.authorable for one in coverage.coverage(corpus)}
    after = {one.family: one.authorable for one in coverage.coverage(broken)}
    moved = [key for key in reported if key in after and after[key] < before[key]]
    assert moved, (
        f"the rule reported against {sorted(reported)} and none of those counts moved: "
        f"before {({k: before[k] for k in reported if k in before})}, after "
        f"{({k: after[k] for k in reported if k in after})}"
    )
