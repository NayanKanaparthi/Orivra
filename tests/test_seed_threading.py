"""Threading: the defect that reached a live mailbox, and the double that would have caught it.

R-M2-033. The seeder inserted 2,248 messages and produced 2,248 conversations. Gmail's threading
guide names three conditions for adding a message to an existing thread - the target `threadId`
in the supplied resource, RFC 2822 `References`/`In-Reply-To`, and matching `Subject` - and the
corpus satisfied the second and third. The first was never sent.

**It went undetected because the old double assigned thread ids from the manifest's own
`thread_key`.** It was asked "do these messages end up in one conversation" and answered from
the thing that defined the intent rather than from anything the API does. Every test passed.

`tests/fixtures/gmail_threading.Gmail` models the API instead: no `threadId`, no association;
a `threadId` whose subject or references do not line up, no association - and in both cases **no
error**, just a new thread id returned quietly. Every test here runs against that.
"""

from __future__ import annotations

import pytest

from mailweave_harness.seed.corpus import generate, rfc2822
from mailweave_harness.seed.manifest import Manifest
from mailweave_harness.seed.substrate import seed, thread_map
from tests.fixtures.gmail_threading import Gmail

SEED = "mailweave.test@example.test"


@pytest.fixture
def manifest() -> Manifest:
    return generate(master_seed=1042, size_profile="smoke")


# --- the double itself, which is now load-bearing ------------------------------------------


def test_the_double_opens_a_new_thread_when_no_thread_id_is_asked_for() -> None:
    """Condition 1. This is the behaviour the old double did not have, and the whole defect."""
    box = Gmail()
    first = box.insert("Message-ID: <a@x>\r\nSubject: Plan\r\n\r\nbody\r\n")
    second = box.insert(
        "Message-ID: <b@x>\r\nSubject: Re: Plan\r\nIn-Reply-To: <a@x>\r\n\r\nbody\r\n"
    )
    assert second.thread_id != first.thread_id
    assert second.thread_id == second.gmail_id


def test_the_double_joins_a_thread_when_all_three_conditions_hold() -> None:
    box = Gmail()
    first = box.insert("Message-ID: <a@x>\r\nSubject: Plan\r\n\r\nbody\r\n")
    second = box.insert(
        "Message-ID: <b@x>\r\nSubject: Re: Plan\r\nIn-Reply-To: <a@x>\r\nReferences: <a@x>\r\n"
        "\r\nbody\r\n",
        thread_id=first.thread_id,
    )
    assert second.thread_id == first.thread_id
    assert box.get_thread(first.thread_id) == (first.gmail_id, second.gmail_id)


@pytest.mark.parametrize(
    ("raw", "why"),
    [
        (
            "Message-ID: <b@x>\r\nSubject: Different\r\nIn-Reply-To: <a@x>\r\n\r\nbody\r\n",
            "condition 3: the subjects do not match",
        ),
        (
            "Message-ID: <b@x>\r\nSubject: Re: Plan\r\n\r\nbody\r\n",
            "condition 2: nothing ties it to the thread",
        ),
        (
            "Message-ID: <b@x>\r\nSubject: Re: Plan\r\nIn-Reply-To: <nobody@x>\r\n\r\nbody\r\n",
            "condition 2: the reference names no message in the thread",
        ),
    ],
)
def test_a_refused_association_is_silent_and_returns_a_new_thread(raw: str, why: str) -> None:
    """The refusal mode that matters: **not an error**. A seeder that trusted the request it
    sent could not tell this apart from success, which is how 2,248 of them went by."""
    box = Gmail()
    first = box.insert("Message-ID: <a@x>\r\nSubject: Plan\r\n\r\nbody\r\n")
    second = box.insert(raw, thread_id=first.thread_id)
    assert second.thread_id != first.thread_id, why
    assert box.get_thread(first.thread_id) == (first.gmail_id,)


# --- the corpus, through the real seeder ---------------------------------------------------


def test_the_corpus_lands_in_one_conversation_per_manifest_thread(manifest: Manifest) -> None:
    """The claim the run made and did not check."""
    box = Gmail(address=SEED)
    report = seed(box, manifest, seed_address=SEED, check_mailbox=False)
    assert report.discrepancies == (), [one.what for one in report.discrepancies]
    conversations = {one.thread_id for one in report.inserted}
    assert len(conversations) == len(manifest.answer_key.threads)
    assert len(report.inserted) == len(manifest.messages)


def test_every_thread_after_the_first_message_asks_for_a_thread_id(manifest: Manifest) -> None:
    """Position 0 opens the conversation and cannot ask for one; every later message must."""
    box = Gmail(address=SEED)
    seed(box, manifest, seed_address=SEED, check_mailbox=False)
    openers = sum(1 for one in box.requested if one is None)
    assert openers == len(manifest.answer_key.threads)
    assert len(box.requested) == len(manifest.messages)


def test_the_thread_check_passes_where_it_previously_reported_forty_conversations(
    manifest: Manifest,
) -> None:
    """`verify`'s second check is the one the live run failed, 40 times."""
    box = Gmail(address=SEED)
    report = seed(box, manifest, seed_address=SEED, check_mailbox=False)
    assert not [one for one in report.discrepancies if one.what.startswith("thread ")]
    assert len(report.thread_ids) == len(manifest.answer_key.threads)


def test_the_seed_loop_does_not_swallow_a_refused_association(manifest: Manifest) -> None:
    """The transport raises (`test_seed_gmail_transport.py` holds that); this is the other
    half: the loop lets it out rather than recording a discrepancy and inserting 2,243 more.

    A corpus of single-message threads is worth less than a mailbox with two messages in it.
    """
    from mailweave_harness.seed.gmail_transport import ThreadingRefused

    class _Declines(Gmail):
        def insert(self, raw: str, *, thread_id: str | None = None):  # type: ignore[no-untyped-def]
            record = super().insert(raw, thread_id=thread_id)
            if thread_id is not None and record.thread_id != thread_id:
                raise ThreadingRefused("Gmail declined the association")
            return record

        def _may_join(self, thread_id: str | None, raw: str, subject: str) -> bool:
            return False

    box = _Declines(address=SEED)
    with pytest.raises(ThreadingRefused):
        seed(box, manifest, seed_address=SEED, check_mailbox=False)
    assert len(box.messages) < len(manifest.messages), "it stopped instead of finishing"
    assert len(box.messages) == 2, "the opener, then the first reply that could not join"


# --- resume, which is where a thread map is easiest to lose --------------------------------


def test_thread_map_rebuilds_the_conversation_for_each_thread(manifest: Manifest) -> None:
    box = Gmail(address=SEED)
    report = seed(box, manifest, seed_address=SEED, check_mailbox=False)
    rebuilt = thread_map(manifest, report.inserted)
    assert set(rebuilt) == set(manifest.answer_key.thread_lengths)
    for record in report.inserted:
        key = next(
            one.thread_key
            for one in manifest.messages
            if one.rfc822_message_id == record.rfc822_message_id
        )
        assert rebuilt[key] == record.thread_id


def test_a_resumed_run_continues_the_conversations_it_already_opened(manifest: Manifest) -> None:
    """The failure this guards: a resume that forgot the map would open a second conversation
    for every thread it continues, and the report would look fine until `verify` ran."""
    stop_after = 5

    class _FailsPartway(Gmail):
        def insert(self, raw: str, *, thread_id: str | None = None):  # type: ignore[no-untyped-def]
            if len(self.messages) >= stop_after:
                raise RuntimeError("429 after every retry")
            return super().insert(raw, thread_id=thread_id)

    box = _FailsPartway(address=SEED)
    partial: list = []
    try:
        seed(box, manifest, seed_address=SEED, check_mailbox=False)
    except RuntimeError:
        partial = [box.messages[one] for one in sorted(box.messages)]
    assert len(partial) == stop_after

    from mailweave_harness.seed.substrate import InsertedMessage

    prior = tuple(
        InsertedMessage(one.rfc822_message_id, one.gmail_id, one.thread_id) for one in partial
    )
    resumed = Gmail(address=SEED)
    # The resumed transport is a fresh mailbox in this test; what is carried across is the
    # thread map, which is the thing a resume must not lose.
    resumed.threads = dict(box.threads)
    resumed.messages = dict(box.messages)
    resumed.counter = box.counter
    report = seed(resumed, manifest, seed_address=SEED, check_mailbox=False, prior=prior)
    assert report.discrepancies == ()
    assert len({one.thread_id for one in report.inserted}) == len(manifest.answer_key.threads)


def test_a_resume_with_no_thread_map_would_split_the_threads_it_continues(
    manifest: Manifest,
) -> None:
    """The counterfactual, asserted so the guarantee is not taken on trust: continuing a
    partially seeded thread **without** asking for its conversation splits it, and asking for
    it does not."""
    opener, reply = manifest.messages[0], manifest.messages[1]
    assert reply.thread_key == opener.thread_key

    blind = Gmail(address=SEED)
    first = blind.insert(rfc2822(opener))
    assert blind.insert(rfc2822(reply)).thread_id != first.thread_id

    carried = Gmail(address=SEED)
    opened = carried.insert(rfc2822(opener))
    assert carried.insert(rfc2822(reply), thread_id=opened.thread_id).thread_id == opened.thread_id


# --- the live rehearsal, driven offline -----------------------------------------------------


def test_the_rehearsal_reads_the_conversation_back_from_gmail_not_from_insert(
    manifest: Manifest,
) -> None:
    """The defect was trusting what `insert` returned. The rehearsal's verdict comes from
    `threads.get`, which is Gmail's own answer to the question being asked."""
    from mailweave_harness.seed import driver

    box = Gmail(address=SEED)
    found = driver.rehearse_threading(box, manifest, seed_address=SEED, messages=4)  # type: ignore[arg-type]
    assert found.passed
    assert found.one_conversation and found.gmail_agrees
    assert len(found.inserted) == 4
    assert found.asked_for[0] is None, "the first message opens the conversation"
    assert set(found.asked_for[1:]) == {found.conversation}
    assert set(found.members_from_gmail) == {one.gmail_id for one in found.inserted}
    assert "PASS" in "\n".join(found.lines())


def test_the_rehearsal_fails_when_gmail_declines_the_association(manifest: Manifest) -> None:
    from mailweave_harness.seed import driver

    class _Declines(Gmail):
        def _may_join(self, thread_id: str | None, raw: str, subject: str) -> bool:
            return False

    box = _Declines(address=SEED)
    found = driver.rehearse_threading(box, manifest, seed_address=SEED, messages=4)  # type: ignore[arg-type]
    assert not found.passed
    assert not found.one_conversation
    assert "FAIL" in "\n".join(found.lines())
    assert "Do not run a bulk seeding" in "\n".join(found.lines())


def test_the_rehearsal_fails_when_gmail_reports_a_conversation_it_did_not_insert(
    manifest: Manifest,
) -> None:
    """`threads.get` returning a stranger means the corpus would not be isolated."""
    from mailweave_harness.seed import driver

    class _Contaminated(Gmail):
        def get_thread(self, thread_id: str) -> tuple[str, ...]:
            return (*super().get_thread(thread_id), "g-somebody-elses-mail")

    found = driver.rehearse_threading(  # type: ignore[arg-type]
        _Contaminated(address=SEED), manifest, seed_address=SEED, messages=3
    )
    assert found.one_conversation
    assert not found.gmail_agrees
    assert not found.passed


def test_the_rehearsal_refuses_an_account_that_is_not_the_seed_account(
    manifest: Manifest,
) -> None:
    from mailweave_harness.scopes import SeedAccountMismatch
    from mailweave_harness.seed import driver

    with pytest.raises(SeedAccountMismatch):
        driver.rehearse_threading(  # type: ignore[arg-type]
            Gmail(address="the.owner@example.test"), manifest, seed_address=SEED
        )


def test_the_rehearsal_writes_far_fewer_messages_than_a_bulk_run(manifest: Manifest) -> None:
    """Its whole point is that being wrong costs four messages rather than 2,248."""
    from mailweave_harness.seed import driver

    box = Gmail(address=SEED)
    driver.rehearse_threading(box, manifest, seed_address=SEED, messages=4)  # type: ignore[arg-type]
    assert len(box.messages) == 4
    assert len(box.messages) < len(manifest.messages)


# --- the generator and the seeder together, on the dev fixture -----------------------------


def test_the_sample_corpus_seeds_into_one_conversation_per_thread() -> None:
    """Generator and seeder exercised together against a double, on a profile kept separate
    from the one byte-identity is asserted against (R-M2-041's fourth precondition)."""
    manifest = generate(master_seed=4242, size_profile="sample")
    box = Gmail(address=SEED)
    report = seed(box, manifest, seed_address=SEED, check_mailbox=False)
    assert report.discrepancies == (), [one.what for one in report.discrepancies]
    assert len({one.thread_id for one in report.inserted}) == len(manifest.answer_key.threads)
    assert len(report.inserted) == len(manifest.messages)


def test_an_attachment_survives_the_seeder_and_is_still_joinable() -> None:
    """F8 needs the file to exist in the mailbox under its name. The seeder renders through
    `rfc2822`, so a multipart message that the transport mangled would lose the family."""
    import email

    manifest = generate(master_seed=4242, size_profile="sample")
    box = Gmail(address=SEED)
    seed(box, manifest, seed_address=SEED, check_mailbox=False)
    carrying = [
        one for one in manifest.messages if any(a.carries_the_fact for a in one.attachments)
    ]
    assert carrying
    for message in carrying:
        raw = next(one for one in box.inserted_raw if message.rfc822_message_id in one)
        parsed = email.message_from_string(raw)
        assert parsed.is_multipart()
        names = [part.get_filename() for part in parsed.walk() if part.get_filename()]
        assert names == [one.filename for one in message.attachments]


def test_the_sample_corpus_keeps_every_sentinel_unique_in_the_mailbox() -> None:
    """The property the settle gate depends on, checked against the corpus the seeder built
    rather than against the manifest that described it."""
    manifest = generate(master_seed=4242, size_profile="sample")
    box = Gmail(address=SEED)
    seed(box, manifest, seed_address=SEED, check_mailbox=False)
    for token in manifest.sentinels:
        carriers = [one for one in box.inserted_raw if token in one]
        assert len(carriers) == 1, (token, len(carriers))
