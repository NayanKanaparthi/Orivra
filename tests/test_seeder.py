"""The bounded seeder: five things, each tested for the property that makes it load-bearing.

The substrate is the thing every later number is scored against, so a defect here is
invisible downstream: a corpus that is not in the mailbox the way the manifest says produces
recall figures that are wrong in a way no recall test can detect. These tests are therefore
about the substrate's own honesty rather than about retrieval.

`FakeMailbox` is a `SeedTransport` that records what it was asked to do. Offline by
construction - the seeder never opens a socket in this suite, and the whole insert / verify /
settle / clean procedure runs against it, including its failure paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from pydantic import ValidationError

from mailweave_harness.scopes import SeedAccountMismatch
from mailweave_harness.seed.families import REGISTERED_N
from mailweave_harness.seed.corpus import (
    CONVERSATION_CEILING,
    EPOCH,
    PROFILES,
    SizeProfile,
    corpus_bytes,
    generate,
    rfc2822,
)
from mailweave_harness.seed.manifest import AnswerKey, Manifest, SeededMessage, ThreadTruth
from mailweave_harness.seed.metrics import (
    Disclosure,
    Partiality,
    Terminal,
    case_recall_strict,
    disclosed,
    evidence_recall,
    outcome_rates,
    partiality_assertions,
    relevant_token_fraction,
    surfaced_not_disclosed,
    wilson_interval,
)
from mailweave_harness.seed.substrate import (
    Discrepancy,
    InsertedMessage,
    SettleTimedOut,
    SubstrateUnsound,
    VerificationReport,
    cleanup,
    seed,
    settle,
    verify,
)

SEED_ADDRESS = "mailweave.test@example.invalid"


@dataclass
class FakeMailbox:
    """A `SeedTransport` that remembers everything, and can be told to misbehave."""

    address: str = SEED_ADDRESS
    stored: dict[str, str] = field(default_factory=dict)
    deleted: list[str] = field(default_factory=list)
    thread_for: dict[str, str] = field(default_factory=dict)
    extra_matches: dict[str, int] = field(default_factory=dict)
    split_after: int | None = None
    undeletable: frozenset[str] = frozenset()
    _inserted: int = 0

    def authenticated_address(self) -> str:
        return self.address

    def insert(self, raw: str, *, thread_id: str | None = None) -> InsertedMessage:
        """Threads by what the caller asked for, not by what the message id implies.

        **This used to derive the thread from `message_id.split(".")[1]`** - the manifest's own
        naming - so a seeder that asked for nothing still got a perfectly threaded mailbox and
        every test passed. The live run then produced one conversation per message (R-M2-033).
        Now: no `threadId`, new conversation, which is what Gmail does.

        `split_after` keeps its meaning and gains its real one: past that many inserts Gmail
        *declines* the association and returns a new thread id, silently, which is the failure
        mode `verify`'s thread check exists to catch.
        """
        message_id = next(
            line.split(": ", 1)[1].strip()
            for line in raw.splitlines()
            if line.startswith("Message-ID: ")
        )
        self._inserted += 1
        gmail_id = f"g{self._inserted:04d}"
        self.stored[gmail_id] = raw
        declined = self.split_after is not None and self._inserted > self.split_after
        thread = self.thread_for.get(message_id)
        if thread is None:
            thread = gmail_id if (thread_id is None or declined) else thread_id
        return InsertedMessage(rfc822_message_id=message_id, gmail_id=gmail_id, thread_id=thread)

    def count_matching(self, query: str) -> int:
        found = sum(1 for raw in self.stored.values() if query in raw)
        return found + self.extra_matches.get(query, 0)

    def delete(self, gmail_id: str) -> None:
        if gmail_id in self.undeletable:
            raise RuntimeError(f"{gmail_id} could not be deleted")
        self.deleted.append(gmail_id)
        self.stored.pop(gmail_id, None)


@pytest.fixture
def manifest() -> Manifest:
    return generate(master_seed=7, size_profile="smoke")


# -- 1 and 4: deterministic generation, and the regeneration contract ---------------------


def test_the_same_inputs_produce_a_byte_identical_corpus() -> None:
    """EP §3.7: the generator is a pure function. This is that sentence, executed."""
    first = generate(master_seed=11, size_profile="smoke")
    second = generate(master_seed=11, size_profile="smoke")
    assert corpus_bytes(first) == corpus_bytes(second)
    assert first.model_dump() == second.model_dump()


def test_a_different_seed_reshuffles_the_content_and_keeps_the_shape() -> None:
    """EP §5.3's anti-gaming lever: same shapes, re-randomised realisations."""
    first = generate(master_seed=11, size_profile="smoke")
    second = generate(master_seed=12, size_profile="smoke")
    assert corpus_bytes(first) != corpus_bytes(second)
    assert first.thread_keys == second.thread_keys
    assert set(first.sentinels).isdisjoint(second.sentinels)


def test_the_generator_reads_no_clock(manifest: Manifest) -> None:
    """A generator that read `now` would produce a different corpus every run and the
    regeneration contract would be untestable.

    Checked as the property itself - two builds of the same inputs are byte-identical - plus
    the weaker containment check that every date falls inside a window fixed by `EPOCH`. The
    containment check used to name two specific years, which stopped being true when the corpus
    grew to span the registered families rather than a single band of threads.
    """
    import datetime as dt
    import email.utils

    again = generate(
        generator_version=manifest.generator_version,
        master_seed=manifest.master_seed,
        size_profile=manifest.size_profile,
    )
    assert corpus_bytes(again) == corpus_bytes(manifest)
    window = (
        dt.datetime.combine(EPOCH, dt.time(), tzinfo=dt.timezone.utc),
        dt.datetime.combine(EPOCH, dt.time(), tzinfo=dt.timezone.utc) + dt.timedelta(days=1200),
    )
    for message in manifest.messages:
        when = email.utils.parsedate_to_datetime(message.date_rfc2822)
        assert window[0] <= when <= window[1], message.rfc822_message_id


def test_a_profile_that_would_cross_gmails_conversation_ceiling_is_refused() -> None:
    """EP §3.8 risk S6: a thread past the ceiling is split server-side, which moves evidence
    into a conversation the manifest does not describe."""
    with pytest.raises(ValueError, match="ceiling"):
        SizeProfile(
            name="too-long",
            family_counts=dict.fromkeys(REGISTERED_N, 1),
            long_length=CONVERSATION_CEILING,
            filler_threads=1,
            short_threads=1,
            situations=40,
        )


def test_every_shipped_profile_stays_under_the_ceiling() -> None:
    for profile in PROFILES.values():
        assert profile.long_length < CONVERSATION_CEILING


def test_an_unknown_profile_is_refused_rather_than_defaulted() -> None:
    with pytest.raises(ValueError, match="unknown size profile"):
        generate(master_seed=1, size_profile="enormous")


def test_every_reply_names_a_parent_the_corpus_contains(manifest: Manifest) -> None:
    """Gmail threads on the reference headers; a reply without one is a new conversation and
    the thread's stated total is wrong before anything is asked."""
    known = {message.rfc822_message_id for message in manifest.messages}
    for message in manifest.messages:
        if message.position == 0:
            assert message.in_reply_to is None
            continue
        assert message.in_reply_to in known
        assert message.in_reply_to in message.references


def test_the_rendered_message_carries_the_threading_headers(manifest: Manifest) -> None:
    reply = next(message for message in manifest.messages if message.position > 0)
    raw = rfc2822(reply)
    assert f"In-Reply-To: {reply.in_reply_to}" in raw
    assert "References: " in raw
    assert raw.endswith("\r\n")


# -- 2: the manifest and its answer key ---------------------------------------------------


def test_the_answer_key_is_ground_truth_about_the_corpus_and_not_case_content(
    manifest: Manifest,
) -> None:
    """The F1-F29 families are M2's, M4's and M5's. What is here is what they will score
    against: which message owns which sentinel, and how long each thread is."""
    assert manifest.answer_key.sentinel_owner
    assert manifest.answer_key.thread_lengths
    assert not hasattr(manifest.answer_key, "cases")


def test_a_sentinel_with_two_owners_is_refused() -> None:
    """A token with two owners cannot be joined on, and the settle gate's expected count is
    wrong before the first poll."""
    base = generate(master_seed=3, size_profile="smoke")
    token = base.sentinels[0]
    messages = list(base.messages)
    victim = next(one for one in messages if token not in one.body)
    messages[messages.index(victim)] = victim.model_copy(
        update={"body": victim.body + f"\nAlso {token}."}
    )
    with pytest.raises(ValidationError, match="also occurs in"):
        Manifest(
            generator_version=base.generator_version,
            master_seed=base.master_seed,
            size_profile=base.size_profile,
            messages=tuple(messages),
            answer_key=base.answer_key,
        )


def test_an_answer_key_that_disagrees_with_its_own_corpus_is_refused() -> None:
    base = generate(master_seed=3, size_profile="smoke")
    wrong = AnswerKey(
        sentinel_owner=base.answer_key.sentinel_owner,
        threads=tuple(
            ThreadTruth(
                thread_key=thread.thread_key,
                length=thread.length + 1,
                subject=thread.subject,
                evidence_positions=thread.evidence_positions,
            )
            for thread in base.answer_key.threads
        ),
    )
    with pytest.raises(ValidationError, match="thread lengths"):
        Manifest(
            generator_version=base.generator_version,
            master_seed=base.master_seed,
            size_profile=base.size_profile,
            messages=base.messages,
            answer_key=wrong,
        )


def test_a_declared_sentinel_absent_from_its_own_body_is_refused() -> None:
    with pytest.raises(ValidationError, match="declared and absent"):
        SeededMessage(
            rfc822_message_id="<a@x.example>",
            thread_key="t000",
            position=0,
            sender="ana@team.example",
            recipients=("bo@team.example",),
            subject="s",
            date_rfc2822="Mon, 05 Jan 2026 09:00:00 +0000",
            body="nothing here",
            sentinels=("missing0001",),
        )


# -- 3: verification and cleanup ------------------------------------------------------------


def test_seeding_verifies_what_the_mailbox_actually_holds(manifest: Manifest) -> None:
    mailbox = FakeMailbox()
    report = seed(mailbox, manifest, seed_address=SEED_ADDRESS)
    assert report.ok, [one.render() for one in report.discrepancies]
    assert len(report.inserted) == len(manifest.messages)
    assert set(report.thread_ids) == set(manifest.thread_keys)
    report.raise_if_unsound()


def test_a_thread_gmail_split_is_a_discrepancy_and_not_a_warning(manifest: Manifest) -> None:
    mailbox = FakeMailbox(split_after=2)
    report = seed(mailbox, manifest, seed_address=SEED_ADDRESS)
    assert not report.ok
    assert any("conversations" in one.render() for one in report.discrepancies)
    with pytest.raises(SubstrateUnsound, match="not what the manifest describes"):
        report.raise_if_unsound()


def test_a_sentinel_the_mailbox_already_matched_is_a_discrepancy(manifest: Manifest) -> None:
    """Checked against the mailbox, not the manifest: the manifest already guaranteed
    uniqueness within the corpus, and the question is whether the mailbox held something
    else first."""
    mailbox = FakeMailbox(extra_matches={manifest.sentinels[0]: 1})
    report = seed(mailbox, manifest, seed_address=SEED_ADDRESS)
    assert not report.ok
    assert any("sentinel" in one.render() for one in report.discrepancies)


def test_the_account_is_checked_before_the_first_write(manifest: Manifest) -> None:
    """A destructive scope pointed at the wrong mailbox is not something to discover from a
    verification report (AD B.9, RR SEC-03)."""
    mailbox = FakeMailbox(address="someone.else@example.invalid")
    with pytest.raises(SeedAccountMismatch):
        seed(mailbox, manifest, seed_address=SEED_ADDRESS)
    assert mailbox.stored == {}


def test_cleanup_is_driven_from_the_insert_results_and_not_from_a_query(
    manifest: Manifest,
) -> None:
    """A query-driven cleanup deletes whatever currently matches, which on a shared test
    account is how a seeder removes somebody else's mail."""
    mailbox = FakeMailbox()
    mailbox.stored["not-ours"] = "Message-ID: <someone-elses@example.invalid>"
    report = seed(mailbox, manifest, seed_address=SEED_ADDRESS)
    result = cleanup(mailbox, report, seed_address=SEED_ADDRESS)
    assert result.failed == ()
    assert result.complete
    assert "not-ours" in mailbox.stored
    assert set(mailbox.deleted) == {record.gmail_id for record in report.inserted}


def test_cleanup_refuses_to_delete_from_a_mailbox_that_is_not_the_seed_account(
    manifest: Manifest,
) -> None:
    """R-M1-013. The module docstring said every write was guarded; only `seed` was.

    A report recorded against one account, replayed against a transport authenticated as
    another, deleted the second account's messages by the first's ids. Deletion is the one
    operation where being wrong is not recoverable.
    """
    mailbox = FakeMailbox()
    report = seed(mailbox, manifest, seed_address=SEED_ADDRESS)
    elsewhere = FakeMailbox(address="someone.else@example.invalid", stored=dict(mailbox.stored))
    with pytest.raises(SeedAccountMismatch):
        cleanup(elsewhere, report, seed_address=SEED_ADDRESS)
    assert elsewhere.deleted == []


def test_cleanup_reports_what_it_could_not_remove(manifest: Manifest) -> None:
    mailbox = FakeMailbox()
    report = seed(mailbox, manifest, seed_address=SEED_ADDRESS)
    stubborn = report.inserted[0].gmail_id
    mailbox.undeletable = frozenset({stubborn})
    result = cleanup(mailbox, report, seed_address=SEED_ADDRESS)
    assert [record.gmail_id for record in result.failed] == [stubborn]
    assert not result.complete
    assert result.removed == len(report.inserted) - 1


def test_verify_reports_a_message_the_insert_never_returned(manifest: Manifest) -> None:
    mailbox = FakeMailbox()
    inserted = [mailbox.insert(rfc2822(message)) for message in manifest.messages[:-1]]
    report = verify(mailbox, manifest, inserted=tuple(inserted))
    assert not report.ok
    assert any("absent from the insert results" in one.render() for one in report.discrepancies)


def test_a_report_with_any_discrepancy_is_not_ok() -> None:
    """`ok` is a conjunction, not a judgement call: the substrate is either what the manifest
    describes or it is not."""
    report = VerificationReport(
        inserted=(),
        discrepancies=(Discrepancy(what="anything", expected="a", observed="b"),),
    )
    assert report.ok is False


# -- 4: the settle gate ---------------------------------------------------------------------


def test_the_gate_requires_two_agreeing_polls_an_interval_apart(manifest: Manifest) -> None:
    """Once is not evidence: Gmail's index is eventually consistent, so a single agreeing
    poll can be followed by a disagreeing one."""
    mailbox = FakeMailbox()
    seed(mailbox, manifest, seed_address=SEED_ADDRESS)
    elapsed = [0.0]

    def clock() -> float:
        return elapsed[0]

    def sleep(seconds: float) -> None:
        elapsed[0] += seconds

    result = settle(mailbox, manifest, sleep=sleep, clock=clock, interval=60.0)
    assert result.polls == 2
    assert result.settle_seconds == pytest.approx(60.0)
    assert result.sentinels_polled


def test_the_gate_reports_the_settle_seconds_the_run_header_needs(
    manifest: Manifest,
) -> None:
    """Without it, every recall number is confounded by Gmail's indexing delay and the
    confound is invisible (EP §3.6)."""
    mailbox = FakeMailbox()
    seed(mailbox, manifest, seed_address=SEED_ADDRESS)
    ticks = iter([0.0, 0.0, 60.0, 60.0, 120.0, 120.0])
    result = settle(
        mailbox, manifest, sleep=lambda _s: None, clock=lambda: next(ticks), interval=60.0
    )
    assert result.settle_seconds >= 0.0


def test_a_gate_that_never_agrees_times_out_rather_than_hanging(manifest: Manifest) -> None:
    mailbox = FakeMailbox()  # nothing inserted, so no sentinel ever matches
    elapsed = [0.0]

    def clock() -> float:
        return elapsed[0]

    def sleep(seconds: float) -> None:
        elapsed[0] += seconds

    with pytest.raises(SettleTimedOut, match="no metric run starts"):
        settle(mailbox, manifest, sleep=sleep, clock=clock, interval=60.0, timeout=180.0)


def test_a_gate_with_no_sentinels_is_refused(manifest: Manifest) -> None:
    """A gate that polls nothing passes always, which is worse than no gate."""
    mailbox = FakeMailbox()
    with pytest.raises(ValueError, match="polls nothing"):
        settle(mailbox, manifest, sleep=lambda _s: None, clock=lambda: 0.0, sentinels=0)


# -- 5: the scoring primitives ---------------------------------------------------------------


def test_disclosure_joins_by_id_so_a_quote_under_another_row_does_not_count() -> None:
    """A quote that appears under another message's row is that message's content, and
    counting it would credit a retrieval that returned the wrong evidence."""
    disclosure = Disclosure(content_by_id={"m2": "the quote is here"})
    assert disclosed(disclosure, "m2", "quote is here")
    assert not disclosed(disclosure, "m1", "quote is here")


def test_a_stub_is_not_a_disclosure() -> None:
    disclosure = Disclosure(content_by_id={}, surfaced_ids=frozenset({"m1"}))
    assert not disclosed(disclosure, "m1", "anything")
    assert surfaced_not_disclosed(disclosure, ["m1"]) == frozenset({"m1"})


def test_whitespace_is_normalised_but_a_missing_word_is_not_forgiven() -> None:
    disclosure = Disclosure(content_by_id={"m1": "the  quote\n  is here"})
    assert disclosed(disclosure, "m1", "the quote is here")
    assert not disclosed(disclosure, "m1", "the quote is not here")


def test_evidence_recall_over_an_empty_requirement_is_refused() -> None:
    """1.0 over nothing looks like success and measures nothing."""
    with pytest.raises(ValueError, match="empty requirement"):
        evidence_recall(Disclosure(content_by_id={}), {})


def test_evidence_recall_counts_what_was_disclosed() -> None:
    disclosure = Disclosure(content_by_id={"m1": "alpha", "m2": "beta"})
    assert evidence_recall(disclosure, {"m1": "alpha", "m2": "beta", "m3": "gamma"}) == 2 / 3


def test_strict_case_recall_needs_all_of_must_retrieve_and_one_of_any_of() -> None:
    disclosure = Disclosure(content_by_id={"m1": "alpha", "m3": "gamma"})
    assert case_recall_strict(disclosure, must_retrieve={"m1": "alpha"}, any_of={"m3": "gamma"})
    assert not case_recall_strict(disclosure, must_retrieve={"m1": "alpha", "m2": "beta"})
    assert not case_recall_strict(disclosure, must_retrieve={"m1": "alpha"}, any_of={"m9": "nope"})


def test_relevant_token_fraction_of_an_empty_response_is_zero_not_an_error() -> None:
    assert relevant_token_fraction(Disclosure(content_by_id={})) == 0.0
    assert relevant_token_fraction(
        Disclosure(content_by_id={}, tokens_returned=100, evidence_tokens=25)
    ) == pytest.approx(0.25)


def test_the_three_outcome_rates_come_back_together_and_cannot_be_separated() -> None:
    """Each can be improved by making another worse, so EP §6.1 requires all three."""
    rates = outcome_rates(
        answerable=[Terminal.ANSWERED, Terminal.NOT_FOUND, Terminal.INCONCLUSIVE],
        unanswerable=[Terminal.NOT_FOUND, Terminal.ANSWERED],
    )
    assert rates.false_not_found == pytest.approx(1 / 3)
    assert rates.hallucinated_found == pytest.approx(0.5)
    assert rates.inconclusive == pytest.approx(1 / 5)
    assert "hallucinated-found" in rates.render()


def test_inconclusive_is_not_counted_as_a_false_not_found() -> None:
    """It asserts no nonexistence (OD-2), and folding it into FNF would punish the honest
    answer the whole outcome vocabulary exists to allow."""
    rates = outcome_rates(
        answerable=[Terminal.INCONCLUSIVE, Terminal.INCONCLUSIVE],
        unanswerable=[Terminal.NOT_FOUND],
    )
    assert rates.false_not_found == 0.0
    assert rates.inconclusive == pytest.approx(2 / 3)


def test_fnf_cannot_be_reported_without_its_paired_control() -> None:
    with pytest.raises(ValueError, match="paired hallucinated-found"):
        outcome_rates(answerable=[Terminal.ANSWERED], unanswerable=[])


def test_partiality_assertions_score_the_full_seven_value_role_set() -> None:
    """The Revision-1 three-value set was narrower than the contract it measured, so a
    role-less response could pass (CONS-008)."""
    record = Partiality(
        claimed_total=4,
        included_ids=frozenset({"m1", "m2"}),
        payload_ids=frozenset({"m1", "m2"}),
        more_available_signal=True,
        role_tags={"m1": "matched", "m2": "stub"},
        reason_tags={"m1": "gmail q matched at L1", "m2": "thread map row"},
    )
    scored = partiality_assertions(record, true_length=4, evidence_ids=frozenset({"m1"}))
    assert scored == {"P1": True, "P1a": True, "P2": True, "P3": True, "P4": True, "P5": True}


def test_a_row_with_no_reason_fails_p4() -> None:
    record = Partiality(
        claimed_total=2,
        included_ids=frozenset({"m1"}),
        payload_ids=frozenset({"m1"}),
        more_available_signal=True,
        role_tags={"m1": "matched"},
        reason_tags={},
    )
    assert partiality_assertions(record, true_length=2)["P4"] is False


def test_a_complete_response_that_still_signals_more_fails_p3() -> None:
    record = Partiality(
        claimed_total=1,
        included_ids=frozenset({"m1"}),
        payload_ids=frozenset({"m1"}),
        more_available_signal=True,
        role_tags={"m1": "matched"},
        reason_tags={"m1": "why"},
    )
    assert partiality_assertions(record, true_length=1)["P3"] is False


def test_untagged_derived_text_fails_p5() -> None:
    record = Partiality(
        claimed_total=1,
        included_ids=frozenset({"m1"}),
        payload_ids=frozenset({"m1"}),
        more_available_signal=False,
        role_tags={"m1": "derived"},
        reason_tags={"m1": "why"},
        derived_ids=frozenset({"m1"}),
        derived_tagged_ids=frozenset(),
    )
    assert partiality_assertions(record, true_length=1)["P5"] is False


def test_the_wilson_interval_stays_inside_zero_and_one_at_the_extremes() -> None:
    """Where the normal approximation produces bounds outside [0, 1] and a reader concludes
    the harness is broken."""
    low, high = wilson_interval(0, 5)
    assert 0.0 <= low <= high <= 1.0
    low, high = wilson_interval(5, 5)
    assert 0.0 <= low <= high <= 1.0


def test_a_confidence_interval_over_zero_trials_is_refused() -> None:
    with pytest.raises(ValueError, match="zero trials"):
        wilson_interval(0, 0)


# -- R-M1-014: the shape claim, made falsifiable ---------------------------------------------
#
# The docstring promised that a different `master_seed` keeps the shapes and re-randomises the
# surface. The generator drew thread lengths and evidence positions from the same RNG as the
# names, so neither held; and `test_a_different_seed_reshuffles_the_content_and_keeps_the_shape`
# asserted only that the thread KEYS matched, which are `f"t{index:03d}"` and identical for
# every seed by construction. Two generators now enforce the split.


def test_a_different_seed_keeps_the_sizes_and_the_position_grid() -> None:
    first = generate(master_seed=11, size_profile="smoke")
    second = generate(master_seed=12, size_profile="smoke")
    assert first.answer_key.thread_lengths == second.answer_key.thread_lengths
    assert [thread.evidence_positions for thread in first.answer_key.threads] == [
        thread.evidence_positions for thread in second.answer_key.threads
    ]
    assert len(first.messages) == len(second.messages)
    assert [one.is_distractor for one in first.messages] == [
        one.is_distractor for one in second.messages
    ]


def test_a_different_seed_still_re_randomises_everything_a_system_could_tune_to() -> None:
    first = generate(master_seed=11, size_profile="smoke")
    second = generate(master_seed=12, size_profile="smoke")
    assert set(first.sentinels).isdisjoint(second.sentinels)
    assert [one.subject for one in first.messages] != [one.subject for one in second.messages]
    assert corpus_bytes(first) != corpus_bytes(second)


def test_the_shape_generator_does_not_see_the_master_seed() -> None:
    """The mechanism, not just its effect: a shape drawn from a generator that was given the
    seed can move when the seed moves, whatever today's outputs happen to show."""
    import inspect

    from mailweave_harness.seed import corpus as module

    source = inspect.getsource(module._shape_rng)
    assert "master_seed" not in source.split('"""')[-1], source
    # And the call site, which is where the first draft of the family rewrite lost it: the
    # builders drew lengths and positions from the content generator, so the position grid
    # moved with the seed and EP §5.3's lever was gone while this test still passed.
    assert "shape_key=f\"{GENERATOR_VERSION}:{profile.name}\"" in inspect.getsource(
        module._drafts
    )
