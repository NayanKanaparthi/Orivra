"""The harness-credential login and the seeding run, as code rather than as instructions.

Everything either side of this module was already built: `substrate.seed`, `verify`, `settle`
and `cleanup`; `GmailSeedTransport`; `pinning.verify_seed_account`. What was missing was the
thing that holds a real credential and calls them in order, and its absence was being handed
to the operator as a script to assemble. A destructive first run is the last place to ask
somebody to wire four pieces together from a document.

**Four refusals stand before the first write**, and they are here rather than in the caller
because a caller is what gets edited:

  1. **the client file may not be the server's.** `mailweave-server-oauth.json` holds a
     `gmail.readonly` client for the owner's real mailbox; a seeding run pointed at it would
     be asking for `https://mail.google.com/` on the personal account. The client id is
     compared and the run aborts on a match, before any network call.
  2. **the token store may not be the server's.** Two grants with different scopes in one
     file is how a read-only server acquires a destructive token by accident.
  3. **the requested scope set is exactly `SEEDER_SCOPES`.** Not a superset, not a subset.
  4. **the authenticated address is the declared seed address**, checked by
     `verify_seed_account` against a real `getProfile` - and re-checked inside `substrate`
     before the first insert and again before the first delete.

**`--approve-writes-to` is typed by a person, names the account, and is compared.** It is not
a `--yes`: an approval that does not name what it approves is a keystroke, and this one has to
match the seed address the run is configured for or nothing happens.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from mailweave.auth.consent import (
    InstalledClient,
    LoginReport,
    StoredTokenProvider,
    read_installed_client,
    run_login,
)
from mailweave.auth.tokenstore import TokenStore
from mailweave.gmail.client import GmailClient, StaticToken
from mailweave.net.egress import build_client
from mailweave_harness.pinning import verify_seed_account
from mailweave_harness.scopes import SEEDER_SCOPES, assert_seed_account
from mailweave_harness.seed.corpus import rfc2822
from mailweave_harness.seed.gmail_transport import GmailSeedTransport
from mailweave_harness.seed.manifest import Manifest
from mailweave_harness.seed.substrate import (
    SETTLE_INTERVAL_SECONDS,
    SETTLE_SENTINELS,
    SETTLE_TIMEOUT_SECONDS,
    CleanupResult,
    Discrepancy,
    InsertedMessage,
    VerificationReport,
    cleanup,
    seed,
    sentinels_unique,
    settle,
)


class SeedingRefused(RuntimeError):
    """A precondition for touching a mailbox did not hold. Nothing was sent."""


@dataclass(frozen=True)
class SeedingPlan:
    """Exactly what a run would do, printable without doing any of it."""

    seed_address: str
    client_path: Path
    client_id: str
    token_path: Path
    scopes: tuple[str, ...]
    messages: int
    threads: int
    sentinels: int
    approved: bool
    #: How many of `messages` a partial report says are already in the mailbox.
    already_inserted: int = 0

    def lines(self) -> tuple[str, ...]:
        return (
            f"  seed account:      {self.seed_address}",
            f"  harness client:    {self.client_id} ({self.client_path})",
            f"  token store:       {self.token_path}",
            f"  requested scopes:  {' '.join(self.scopes)}",
            (
                f"  will insert:       {self.messages - self.already_inserted} message(s) in "
                f"{self.threads} thread(s)"
                + (
                    f" ({self.already_inserted} already inserted by the resumed run, "
                    f"{self.messages} in the corpus)"
                    if self.already_inserted
                    else ""
                )
            ),
            f"  settle gate polls: {min(self.sentinels, SETTLE_SENTINELS)} sentinel(s) until "
            f"each matches its manifest count twice in a row, {SETTLE_INTERVAL_SECONDS:.0f}s "
            f"apart, giving up after {SETTLE_TIMEOUT_SECONDS / 60:.0f} minutes",
            f"  writes approved:   {'yes' if self.approved else 'NO - nothing will be sent'}",
            "  cleanup:           every inserted id is recorded in the verification report; "
            "`--cleanup REPORT` deletes exactly those ids and nothing matched by a query",
        )


def _refuse_shared_credential(client: InstalledClient, server_client_path: Path) -> None:
    """Refusal 1: the harness client may not be the server's."""
    if not server_client_path.exists():
        return
    try:
        server = read_installed_client(server_client_path)
    except Exception:  # pragma: no cover - an unreadable server file is not this run's problem
        return
    if server.client_id == client.client_id:
        raise SeedingRefused(
            f"the client at {client.path} has the same client id as the server credential at "
            f"{server_client_path}. A seeding run against it would request "
            f"{' '.join(SEEDER_SCOPES)} on the client the server uses for the owner's real "
            "mailbox. Refusing before any network call"
        )


def _refuse_shared_store(token_path: Path, server_token_path: Path | None) -> None:
    """Refusal 2: the harness grant may not land in the server's store."""
    if server_token_path is None:
        return
    if token_path.expanduser().resolve() == server_token_path.expanduser().resolve():
        raise SeedingRefused(
            f"the harness token store ({token_path}) is the server's. Two grants with "
            "different scopes in one file is how a read-only server acquires a destructive "
            "token by accident. Refusing"
        )


def plan(
    manifest: Manifest,
    *,
    seed_address: str,
    client_path: Path,
    token_path: Path,
    approved: bool,
    server_client_path: Path = Path("mailweave-server-oauth.json"),
    server_token_path: Path | None = None,
    resume_from: Path | None = None,
) -> SeedingPlan:
    """Every refusal that can fire without a network call, then the plan. Nothing is sent."""
    client = read_installed_client(client_path)
    _refuse_shared_credential(client, server_client_path)
    _refuse_shared_store(token_path, server_token_path)
    already = 0 if resume_from is None else len(report_from(resume_from).inserted)
    return SeedingPlan(
        seed_address=seed_address.strip().lower(),
        client_path=client_path,
        client_id=client.client_id,
        token_path=token_path,
        scopes=SEEDER_SCOPES,
        messages=len(manifest.messages),
        threads=len(manifest.answer_key.threads),
        sentinels=len(manifest.sentinels),
        approved=approved,
        already_inserted=already,
    )


def login(
    *,
    client_path: Path,
    token_path: Path,
    seed_address: str,
    wait_for_code: Callable[[str, str], str],
    port: int,
    server_client_path: Path = Path("mailweave-server-oauth.json"),
    server_token_path: Path | None = None,
    http: httpx.Client | None = None,
) -> LoginReport:
    """The harness credential's consent flow, at `SEEDER_SCOPES`, into its own store.

    `run_login` is the server's - imported rather than re-implemented, because the granted
    scopes are read back and compared there and a second copy of that comparison is the one
    nobody updates. What this function adds is the two refusals above and the scope set.
    """
    client = read_installed_client(client_path)
    _refuse_shared_credential(client, server_client_path)
    _refuse_shared_store(token_path, server_token_path)
    store = TokenStore(token_path)
    session = http if http is not None else build_client(timeout=30.0)

    def fetch_address(token: str) -> str:
        return GmailClient(token=StaticToken(token), http=session).get_profile().email_address

    return run_login(
        client=client,
        store=store,
        fetch_address=fetch_address,
        announce=lambda _url: None,
        wait_for_code=wait_for_code,
        requested_scopes=SEEDER_SCOPES,
        http=session,
        expected_account=seed_address,
        port=port,
    )


def transport_for(
    *,
    client_path: Path,
    token_path: Path,
    seed_address: str,
    approved: bool,
    http: httpx.Client | None = None,
) -> GmailSeedTransport:
    """A transport bound to a credential that has been observed to be the seed account.

    Refusals 3 and 4. `verify_seed_account` calls `getProfile` and aborts on a mismatch or on
    an address it could not observe; the session it returns is bound to the credential that
    produced it, and every write re-checks that binding.
    """
    client = read_installed_client(client_path)
    store = TokenStore(token_path)
    store.verify_permissions()
    session = http if http is not None else build_client(timeout=30.0)
    provider = StoredTokenProvider(client=client, store=store, http=session)
    credential = GmailClient(token=provider, http=session)
    bound = verify_seed_account(credential, seed_address=seed_address, scopes=SEEDER_SCOPES)
    return GmailSeedTransport(
        http=session,
        session=bound,
        credential=credential,
        access_token=provider.access_token(),
        approved_by_owner=approved,
    )


@dataclass(frozen=True)
class Survey:
    """What is already in the mailbox, read-only, before anything is written.

    "Isolated from existing test mail" is a claim, and this is the measurement behind it.
    Two numbers matter: how much mail is already there (the corpus is added to it, not into
    an empty box), and whether any of the manifest's sentinels already matches something
    (which would break the settle gate and, worse, would make a recall metric join on a row
    the seeder did not insert - EP's reason for checking sentinel uniqueness against the
    *mailbox* rather than against the manifest).
    """

    address: str
    existing_messages: int
    colliding_sentinels: tuple[str, ...]

    @property
    def safe(self) -> bool:
        return not self.colliding_sentinels

    def lines(self) -> tuple[str, ...]:
        head = (
            f"  account:            {self.address}",
            f"  already in it:      {self.existing_messages} message(s), spam and trash included",
            f"  sentinel collisions: {len(self.colliding_sentinels)}",
        )
        if self.safe:
            return (
                *head,
                "  -> no manifest sentinel matches anything already in this mailbox. The "
                "corpus can be distinguished from existing mail, and cleanup will remove "
                "only the ids this run inserts.",
            )
        return (
            *head,
            "  -> REFUSE. A sentinel that already matches makes the settle gate pass early "
            "and a recall metric join on a row the seeder did not insert. Regenerate at a "
            "different --seed, or empty the account first: "
            + ", ".join(self.colliding_sentinels[:5]),
        )


def survey(transport: GmailSeedTransport, manifest: Manifest, *, sentinels: int = 10) -> Survey:
    """Read-only. Counts what is there and checks the sentinels against it. Writes nothing."""
    existing = transport.count_everything()
    colliding = tuple(
        token for token in manifest.sentinels[:sentinels] if transport.count_matching(token) > 0
    )
    return Survey(
        address=transport.authenticated_address(),
        existing_messages=existing,
        colliding_sentinels=colliding,
    )


@dataclass(frozen=True)
class Rehearsal:
    """What a live threading rehearsal established, in facts rather than in a verdict."""

    thread_key: str
    inserted: tuple[InsertedMessage, ...]
    conversation: str
    members_from_gmail: tuple[str, ...]
    #: Every `threadId` the inserts asked for, in order. The first is `None` by construction.
    asked_for: tuple[str | None, ...]

    @property
    def one_conversation(self) -> bool:
        return len({one.thread_id for one in self.inserted}) == 1

    @property
    def gmail_agrees(self) -> bool:
        """`threads.get` reports exactly the messages this rehearsal inserted, and no others.

        Read back from Gmail rather than from what `insert` returned, because the whole defect
        was trusting the second.
        """
        return set(self.members_from_gmail) == {one.gmail_id for one in self.inserted}

    @property
    def passed(self) -> bool:
        return self.one_conversation and self.gmail_agrees

    def lines(self) -> tuple[str, ...]:
        head = (
            f"  thread:            {self.thread_key}",
            f"  inserted:          {len(self.inserted)} message(s)",
            f"  conversation:      {self.conversation}",
            f"  threadId asked for: {['(none)' if one is None else one for one in self.asked_for]}",
            f"  threads.get says:  {len(self.members_from_gmail)} message(s) in that conversation",
        )
        if self.passed:
            return (
                *head,
                "  -> PASS. Every inserted reply is in one Gmail conversation, and Gmail's own "
                "read of that conversation contains exactly these messages and nothing else.",
            )
        return (
            *head,
            "  -> FAIL. "
            + (
                "the inserts landed in more than one conversation"
                if not self.one_conversation
                else "Gmail's read of the conversation does not match what was inserted"
            )
            + ". Do not run a bulk seeding.",
        )


def rehearse_threading(
    transport: GmailSeedTransport,
    manifest: Manifest,
    *,
    seed_address: str,
    messages: int = 4,
) -> Rehearsal:
    """Insert the first few messages of one thread and ask Gmail whether they are one thread.

    **The smallest live write that can answer the question R-M2-033 answered wrongly.** The
    unit under test is the three conditions in Gmail's threading guide, and no amount of
    offline modelling settles whether this corpus meets them: the double is my model of the
    API, and the model was what was wrong. So a handful of real messages, read back through
    `threads.get`, and a verdict that does not depend on what `insert` claimed.

    The account is asserted before the first write, as everywhere else. The inserted ids are
    returned so they can be recorded and cleaned up under the same approval as anything else.
    """
    assert_seed_account(
        authenticated_address=transport.authenticated_address(), seed_address=seed_address
    )
    first_key = manifest.messages[0].thread_key
    chosen = [one for one in manifest.messages if one.thread_key == first_key][:messages]
    if len(chosen) < 2:
        raise SeedingRefused(
            "a threading rehearsal needs at least two messages in one thread; this corpus's "
            f"first thread has {len(chosen)}"
        )
    records: list[InsertedMessage] = []
    asked: list[str | None] = []
    conversation: str | None = None
    for message in chosen:
        asked.append(conversation)
        record = transport.insert(rfc2822(message), thread_id=conversation)
        records.append(record)
        conversation = conversation or record.thread_id
    assert conversation is not None
    return Rehearsal(
        thread_key=first_key,
        inserted=tuple(records),
        conversation=conversation,
        members_from_gmail=transport.get_thread(conversation),
        asked_for=tuple(asked),
    )


def run_seeding(
    transport: GmailSeedTransport,
    manifest: Manifest,
    *,
    seed_address: str,
    out: Path,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
    prior: Sequence[InsertedMessage] = (),
) -> VerificationReport:
    """Insert, check the structure, settle, then check the index. In that order.

    **The order is the point.** `verify` makes three checks and two of them read the insert
    results - every message present, every thread one conversation - and answer correctly the
    instant the inserts return. The third asks Gmail's *search index* whether each sentinel
    matches exactly one message, and a search index is eventually consistent: asked straight
    after a bulk insert it answers 0 for almost every token, and a run that asked it there
    would report a discrepancy per sentinel on every successful seeding. EP §3.6's settle gate
    is the thing that knows when the index has caught up, so the index question is asked after
    it, and the report carries both halves.

    `prior` resumes a run that died partway: those messages are not inserted again and they
    count as present. Pass the `inserted` list of the partial report the failed run wrote.
    """
    # **The insert results are recorded as they happen, not after the run succeeds.** A bulk
    # write of a few thousand messages can fail partway - a rate limit that outlasts the
    # retries, a revoked token, a laptop that sleeps - and a run that raised without writing
    # its record would leave a half-seeded mailbox with no list of what to delete. Cleanup is
    # driven from insert results and never from a query (a query-driven cleanup on a shared
    # test account removes somebody else's mail), so the results have to survive the failure.
    recorded: list[InsertedMessage] = list(prior)
    watched = _Recording(transport, recorded)
    try:
        structural = seed(
            watched,
            manifest,
            seed_address=seed_address,
            check_mailbox=False,
            prior=prior,
        )
    except BaseException:
        _write(out, recorded, (), partial=True)
        raise
    # From here the mailbox holds the corpus, so every remaining failure still has to leave the
    # record behind: a settle gate that times out is not a reason to lose the cleanup list.
    try:
        result = settle(transport, manifest, sleep=sleep, clock=clock)
    except BaseException:
        _write(out, structural.inserted, structural.discrepancies, partial=True)
        raise
    indexed = sentinels_unique(transport, manifest)
    report = VerificationReport(
        inserted=structural.inserted,
        discrepancies=(*structural.discrepancies, *indexed),
        thread_ids=structural.thread_ids,
    )
    _write(
        out,
        report.inserted,
        report.discrepancies,
        settle_seconds=result.settle_seconds,
        settle_polls=result.polls,
    )
    return report


@dataclass
class _Recording:
    """Delegates to the transport and keeps every `InsertedMessage` as it is returned."""

    inner: GmailSeedTransport
    seen: list[InsertedMessage]

    def authenticated_address(self) -> str:
        return self.inner.authenticated_address()

    def count_matching(self, query: str) -> int:
        return self.inner.count_matching(query)

    def delete(self, gmail_id: str) -> None:
        self.inner.delete(gmail_id)

    def insert(self, raw: str, *, thread_id: str | None = None) -> InsertedMessage:
        record = self.inner.insert(raw, thread_id=thread_id)
        self.seen.append(record)
        return record


def _write(
    out: Path,
    inserted: Sequence[InsertedMessage],
    discrepancies: Sequence[Discrepancy],
    *,
    settle_seconds: float | None = None,
    settle_polls: int | None = None,
    partial: bool = False,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    body: dict[str, Any] = {
        "inserted": [
            {
                "rfc822_message_id": one.rfc822_message_id,
                "gmail_id": one.gmail_id,
                "thread_id": one.thread_id,
            }
            for one in inserted
        ],
        "discrepancies": [
            {"what": one.what, "expected": one.expected, "observed": one.observed}
            for one in discrepancies
        ],
    }
    if partial:
        body["partial"] = True
        body["note"] = (
            "the seeding run did not complete. Every id above was inserted and is still in "
            "the mailbox; `--cleanup` on this file removes exactly those and nothing else. "
            "This corpus is NOT seeded and must not be scored against."
        )
    if settle_seconds is not None:
        body["settle_seconds"] = round(settle_seconds, 2)
    if settle_polls is not None:
        body["settle_polls"] = settle_polls
    out.write_text(json.dumps(body, indent=2), encoding="utf-8")


def run_cleanup(
    transport: GmailSeedTransport,
    report: VerificationReport,
    *,
    seed_address: str,
    out: Path | None = None,
) -> CleanupResult:
    """Delete exactly the ids this record holds, and write down what happened to each.

    **`messages.delete` is permanent**: not the trash, no bin, no undo. `out` is where the
    record of the deletion goes, and it is worth writing precisely because the step cannot be
    reversed - the input record says what was targeted, and this says what was actually done.
    """
    result = cleanup(transport, report, seed_address=seed_address)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "permanent": True,
                    "note": (
                        "users.messages.delete removes the message outright. It does not go "
                        "to the trash and cannot be recovered."
                    ),
                    "targeted": len(report.inserted),
                    "deleted": [one.gmail_id for one in result.deleted],
                    "already_gone": [one.gmail_id for one in result.already_gone],
                    "failed": [one.gmail_id for one in result.failed],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return result


def report_from(path: Path) -> VerificationReport:
    """Read back the report `run_seeding` wrote, for a later `--cleanup`."""
    body = json.loads(path.read_text(encoding="utf-8"))
    return VerificationReport(
        inserted=tuple(InsertedMessage(**one) for one in body.get("inserted", ())),
        discrepancies=tuple(Discrepancy(**one) for one in body.get("discrepancies", ())),
    )


__all__ = [
    "Rehearsal",
    "SeedingPlan",
    "SeedingRefused",
    "Survey",
    "login",
    "plan",
    "rehearse_threading",
    "report_from",
    "run_cleanup",
    "run_seeding",
    "survey",
    "transport_for",
]
