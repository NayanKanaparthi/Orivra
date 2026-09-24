"""Insert, verify, settle and remove: the substrate operations, behind one narrow seam.

**The substrate is load-bearing** (EP §3.3). Every recall number is scored against the
manifest, so a corpus that is not in the mailbox the way the manifest says makes every
downstream figure wrong in a way no downstream test can see. Verification is therefore not
optional and not a warning: `verify` returns a report, and a report with any discrepancy in
it is a refusal to proceed.

**Destructive capability is bounded twice over.** The scope literal lives in
`mailweave_harness.scopes` and nowhere else, and `assert_seed_account` refuses to run unless
the authenticated address is the configured seed account (AD B.9, RR SEC-03). Both are
checked here before a single write, and `SeedTransport` is a protocol so the offline tests
drive the whole procedure without a credential, a socket or a mailbox.

**Nothing in this module reads or writes the server's credential.** The seeder holds the
harness client, which is the only one with the destructive scope; the server credential is
`gmail.readonly` and must never authenticate this code path.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from mailweave_harness.scopes import assert_seed_account
from mailweave_harness.seed.corpus import rfc2822
from mailweave_harness.seed.manifest import Manifest

#: How many sentinel queries the settle gate polls (EP §3.6).
SETTLE_SENTINELS: int = 10

#: How long between the two agreeing polls the gate requires, in seconds (EP §3.6).
SETTLE_INTERVAL_SECONDS: float = 60.0

#: How long the gate will wait before giving up. A gate with no bound is a run that hangs
#: rather than a run that reports the substrate was not ready.
SETTLE_TIMEOUT_SECONDS: float = 1_800.0


@dataclass(frozen=True)
class InsertedMessage:
    """What the mailbox assigned to one inserted message.

    `thread_id` is Gmail's, not the generator's: a generator that predicted a server-side id
    would be predicting the thing the verification exists to check.
    """

    rfc822_message_id: str
    gmail_id: str
    thread_id: str


class SeedTransport(Protocol):
    """The three operations the seeder needs, and no others.

    Narrow on purpose. A transport that could also label, forward or send would put
    capabilities inside the seeder that nothing here uses and that a mistake could reach;
    the destructive scope is wide enough already, and the seam is where that width stops.
    """

    def authenticated_address(self) -> str: ...

    def insert(self, raw: str, *, thread_id: str | None = None) -> InsertedMessage: ...

    def count_matching(self, query: str) -> int: ...

    def delete(self, gmail_id: str) -> None: ...


@dataclass(frozen=True)
class Discrepancy:
    """One way the mailbox and the manifest disagree. Every field is a fact, not a guess."""

    what: str
    expected: str
    observed: str

    def render(self) -> str:
        return f"{self.what}: expected {self.expected}, observed {self.observed}"


@dataclass(frozen=True)
class VerificationReport:
    """What the mailbox holds, checked against what the manifest said it would.

    **`ok` is a conjunction and not a judgement call.** A report with any discrepancy is not
    ok, whatever the discrepancy is: the substrate is either what the manifest describes or
    it is not, and a run that proceeded on "mostly" would produce numbers nobody could read.
    """

    inserted: tuple[InsertedMessage, ...]
    discrepancies: tuple[Discrepancy, ...]
    thread_ids: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.discrepancies

    def raise_if_unsound(self) -> None:
        if self.ok:
            return
        lines = "\n  ".join(one.render() for one in self.discrepancies)
        raise SubstrateUnsound(
            "the seeded corpus is not what the manifest describes, so every metric scored "
            f"against it would be wrong in a way no later test can see:\n  {lines}"
        )


class AlreadyGone(RuntimeError):
    """A delete found nothing to delete. For a cleanup that is the goal, not a failure.

    Declared here, beside the `SeedTransport` protocol, rather than in the Gmail transport:
    it is part of what `delete` means to the seeder, and `cleanup` deciding by the *name* of
    somebody else's exception class would be a string comparison standing in for a contract.
    """


class SubstrateUnsound(RuntimeError):
    """The mailbox and the manifest disagree. Nothing downstream may run."""


class SettleTimedOut(RuntimeError):
    """The sentinel queries never agreed with the manifest twice in a row."""


@dataclass(frozen=True)
class SettleResult:
    """What the gate established, and how long it took.

    `settle_seconds` goes in the run header (EP §3.6) because it is the number that separates
    "Gmail has not indexed the seed yet" from a genuine retrieval failure. Without it every
    recall number is confounded, and the confound is invisible.
    """

    settle_seconds: float
    polls: int
    sentinels_polled: tuple[str, ...]


def seed(
    transport: SeedTransport,
    manifest: Manifest,
    *,
    seed_address: str,
    check_mailbox: bool = True,
    prior: Sequence[InsertedMessage] = (),
) -> VerificationReport:
    """Insert the corpus, then check the mailbox against the manifest.

    The account check runs **before the first write**, not after: a destructive scope pointed
    at the wrong mailbox is not something to discover from a verification report.

    `check_mailbox` is passed through to `verify`; a bulk run wants `False` here and the
    mailbox check after its settle gate. `prior` is what an earlier partial run of this
    same seeding already inserted: those messages are not inserted again **and they count as
    present**, which is how a run that died at message 2,000 resumes instead of inserting those
    two thousand a second time and instead of reporting them absent.
    """
    assert_seed_account(
        authenticated_address=transport.authenticated_address(), seed_address=seed_address
    )
    inserted: list[InsertedMessage] = []
    discrepancies: list[Discrepancy] = []
    inserted.extend(prior)
    already = frozenset(one.rfc822_message_id for one in prior)
    # **The conversation each thread landed in, learned from its first message and then asked
    # for by every later one.** Gmail assigns the thread; the generator cannot predict it. A
    # resumed run rebuilds this from the partial report rather than starting empty, because a
    # resume that forgot it would open a second conversation for every thread it continues.
    conversation: dict[str, str] = thread_map(manifest, prior)
    for message in manifest.messages:
        if message.rfc822_message_id in already:
            continue
        record = transport.insert(rfc2822(message), thread_id=conversation.get(message.thread_key))
        if record.rfc822_message_id != message.rfc822_message_id:
            discrepancies.append(
                Discrepancy(
                    what=f"insert of {message.rfc822_message_id}",
                    expected=message.rfc822_message_id,
                    observed=record.rfc822_message_id,
                )
            )
        conversation.setdefault(message.thread_key, record.thread_id)
        inserted.append(record)
    return verify(
        transport,
        manifest,
        inserted=tuple(inserted),
        found=tuple(discrepancies),
        check_mailbox=check_mailbox,
    )


def thread_map(manifest: Manifest, inserted: Sequence[InsertedMessage]) -> dict[str, str]:
    """`thread_key` to the Gmail conversation its messages are in, from insert results.

    The join is through the RFC message id, which is the identity the manifest and the mailbox
    share. Where a thread's records disagree about the conversation - which is the shape
    R-M2-033 produced, every message its own - the **earliest** is kept, because that is the
    one a later insert has to ask for and because the alternative is picking arbitrarily.
    """
    by_rfc = {one.rfc822_message_id: one.thread_key for one in manifest.messages}
    out: dict[str, str] = {}
    for record in inserted:
        key = by_rfc.get(record.rfc822_message_id)
        if key is not None:
            out.setdefault(key, record.thread_id)
    return out


def verify(
    transport: SeedTransport,
    manifest: Manifest,
    *,
    inserted: Sequence[InsertedMessage],
    found: Sequence[Discrepancy] = (),
    check_mailbox: bool = True,
) -> VerificationReport:
    """Three checks, each of which has failed for somebody: every message is there, every
    thread is one conversation, and every sentinel is unique in the mailbox.

    The third is the one that is easy to skip and expensive to get wrong: a sentinel that
    also matches a message the seeder did not insert makes the settle gate pass early and a
    recall metric join on the wrong row. It is checked against the *mailbox*, not against the
    manifest, because the manifest already guaranteed uniqueness within the corpus and the
    question here is whether the mailbox held something else first.

    `check_mailbox=False` runs only the two structural checks, which read the insert results
    and answer correctly the instant the inserts return. **A bulk seeding run needs that**,
    because the third check asks Gmail's search index and the index has not caught up yet - see
    `sentinels_unique`. The default is `True` so a caller checking an already-settled mailbox
    gets all three.
    """
    discrepancies = list(found)
    by_rfc = {record.rfc822_message_id: record for record in inserted}
    for message in manifest.messages:
        if message.rfc822_message_id not in by_rfc:
            discrepancies.append(
                Discrepancy(
                    what=f"message {message.rfc822_message_id}",
                    expected="inserted",
                    observed="absent from the insert results",
                )
            )

    threads: dict[str, set[str]] = {}
    for message in manifest.messages:
        record = by_rfc.get(message.rfc822_message_id)
        if record is None:
            continue
        threads.setdefault(message.thread_key, set()).add(record.thread_id)
    thread_ids: dict[str, str] = {}
    for thread_key, seen in sorted(threads.items()):
        if len(seen) != 1:
            discrepancies.append(
                Discrepancy(
                    what=f"thread {thread_key}",
                    expected="one Gmail conversation",
                    observed=f"{len(seen)} conversations",
                )
            )
            continue
        thread_ids[thread_key] = next(iter(seen))

    if check_mailbox:
        discrepancies.extend(sentinels_unique(transport, manifest))

    return VerificationReport(
        inserted=tuple(inserted),
        discrepancies=tuple(discrepancies),
        thread_ids=thread_ids,
    )


def sentinels_unique(transport: SeedTransport, manifest: Manifest) -> tuple[Discrepancy, ...]:
    """Every sentinel matches exactly one message in the mailbox. **A search-index question.**

    Separated from the structural checks because it is the only one that asks Gmail's *index*
    rather than the insert results, and an index is eventually consistent. Asked straight after
    a bulk insert it answers 0 for almost every token - not because anything is wrong but
    because nothing has been indexed yet - and a caller that ran it there would report a
    discrepancy per sentinel on every successful seeding. It belongs **after** the settle gate,
    which is the thing that exists to know when the index has caught up (EP §3.6).
    """
    out: list[Discrepancy] = []
    for token in manifest.sentinels:
        matched = transport.count_matching(token)
        if matched != 1:
            out.append(
                Discrepancy(
                    what=f"sentinel {token}",
                    expected="1 matching message in the mailbox",
                    observed=f"{matched}",
                )
            )
    return tuple(out)


def settle(
    transport: SeedTransport,
    manifest: Manifest,
    *,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
    sentinels: int = SETTLE_SENTINELS,
    interval: float = SETTLE_INTERVAL_SECONDS,
    timeout: float = SETTLE_TIMEOUT_SECONDS,
) -> SettleResult:
    """EP §3.6's gate: poll sentinel queries until they match their expected counts **twice
    in a row, `interval` apart**.

    Twice in a row rather than once, because Gmail's index is eventually consistent and a
    single agreeing poll can be followed by a disagreeing one. The interval is what makes the
    second poll evidence rather than a repeat of the first.

    `sleep` and `clock` are injected so the offline tests drive the whole gate - including its
    timeout - without waiting sixty seconds, and so `settle_seconds` is measured rather than
    estimated. **No metric run starts before this returns.**
    """
    polled = manifest.sentinels[:sentinels]
    if not polled:
        raise ValueError("a settle gate with no sentinels polls nothing and passes always")
    started = clock()
    agreements = 0
    polls = 0
    while True:
        polls += 1
        matched = all(transport.count_matching(token) == 1 for token in polled)
        agreements = agreements + 1 if matched else 0
        if agreements == 2:
            return SettleResult(
                settle_seconds=clock() - started,
                polls=polls,
                sentinels_polled=polled,
            )
        if clock() - started >= timeout:
            raise SettleTimedOut(
                f"the sentinel queries did not agree with the manifest twice in a row within "
                f"{timeout:.0f}s ({polls} polls). Every recall number taken now would be "
                "measuring Gmail's indexing delay rather than retrieval, so no metric run "
                "starts"
            )
        sleep(interval)


@dataclass(frozen=True)
class CleanupResult:
    """What an irreversible step actually did, as three disjoint lists.

    `already_gone` is separated from `deleted` and from `failed` because it means something
    different from both: the id was in the record and the mailbox does not have it, which is
    the expected state on a second pass over a cleanup that stopped partway.
    """

    deleted: tuple[InsertedMessage, ...] = ()
    already_gone: tuple[InsertedMessage, ...] = ()
    failed: tuple[InsertedMessage, ...] = ()

    @property
    def removed(self) -> int:
        """Ids the mailbox no longer has, whoever removed them."""
        return len(self.deleted) + len(self.already_gone)

    @property
    def complete(self) -> bool:
        return not self.failed


def cleanup(
    transport: SeedTransport, report: VerificationReport, *, seed_address: str
) -> CleanupResult:
    """Remove every message this seeding inserted, and report exactly what happened to each.

    Driven from the **insert results**, not from a query: a query-driven cleanup deletes
    whatever currently matches, which on a shared test account is how a seeder removes
    somebody else's mail. Every id here was returned by an insert this process performed.

    **The account is asserted here too** (review finding R-M1-013). The module docstring said
    "both are checked here before a single write", and `assert_seed_account` was called only
    by `seed`. A report from a run against one account, replayed against a transport
    authenticated as another - a refreshed credential, a second invocation, a retry after
    re-auth - would have deleted the second account's messages by ids recorded against the
    first. Deletion is the one operation where being wrong is not recoverable, so it is the
    one that least deserved the missing check.

    **`messages.delete` is permanent.** It does not move the message to the trash; there is no
    bin to recover it from and no undo. That is why the result is returned in full rather than
    as a count: an irreversible step should leave a record of what it touched.
    """
    assert_seed_account(
        authenticated_address=transport.authenticated_address(), seed_address=seed_address
    )
    deleted: list[InsertedMessage] = []
    gone: list[InsertedMessage] = []
    failed: list[InsertedMessage] = []
    for record in report.inserted:
        try:
            transport.delete(record.gmail_id)
        except Exception as failure:
            (gone if isinstance(failure, AlreadyGone) else failed).append(record)
            continue
        deleted.append(record)
    return CleanupResult(tuple(deleted), tuple(gone), tuple(failed))


__all__ = [
    "SETTLE_INTERVAL_SECONDS",
    "SETTLE_SENTINELS",
    "SETTLE_TIMEOUT_SECONDS",
    "CleanupResult",
    "Discrepancy",
    "InsertedMessage",
    "SeedTransport",
    "SettleResult",
    "SettleTimedOut",
    "SubstrateUnsound",
    "VerificationReport",
    "cleanup",
    "seed",
    "sentinels_unique",
    "settle",
    "thread_map",
    "verify",
]
