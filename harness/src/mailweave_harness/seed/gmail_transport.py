"""The concrete `SeedTransport` against Gmail - built, tested, and unable to write yet.

**Writes are off by default and that is the safety property, not a placeholder.** The four
methods are here, exercised against a mock transport, and `insert` and `delete` raise
`WritesNotApproved` **before issuing any request** unless the caller passes
`approved_by_owner=True`. There is no configuration file, no environment variable and no
default that turns them on: the flag is an argument a human has to type, in the command that
seeds, after reading what it will do. A first run that cannot be taken back is the one kind of
code that should not arrive quietly with the rest of a build.

**Three controls stand between this capability and the owner's mailbox**, and only one is here
(`mailweave_harness.pinning` documents all three). Google's own test-user allowlist on the
harness OAuth client means the personal mailbox cannot hold a token for it at all; a CI guard
means `server/**` cannot import this package, so no MCP tool reaches a write path even
indirectly; and this module re-checks the binding **at the point of use** - every write calls
`SeedSession.assert_bound_to` against the credential in hand, rather than trusting a check that
ran when the session was made. That last one is amendment A7's move, and `pinning`'s docstring
records the three times a weaker version of it was found insufficient.

**`count_matching` pages and counts rather than reading `resultSizeEstimate`.** Gmail's estimate
is an estimate; the settle gate compares a count against the manifest and would wait forever, or
stop early, on a number that is allowed to be wrong.
"""

from __future__ import annotations

import base64
import contextlib
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

import httpx

from mailweave_harness.pinning import SeedSession
from mailweave_harness.preflight.scope import MailboxScope
from mailweave_harness.seed.substrate import AlreadyGone, InsertedMessage

#: Gmail's v1 base. One constant, so a test asserts the exact URL a write would go to.
GMAIL_BASE: Final[str] = "https://gmail.googleapis.com/gmail/v1/users/me"

#: How many list pages `count_matching` will walk before refusing. A settle gate polling a
#: query that matches the whole mailbox is a mistake in the query, not a reason to page for
#: an hour.
MAX_COUNT_PAGES: Final[int] = 40


#: How long a single request will keep retrying a rate limit or a 5xx. **Not the server's
#: `BackoffPolicy`**, deliberately: that one caps total backoff at 1,500 ms because it is a
#: per-query budget inside a tool call a caller is waiting on. Seeding is a bulk write of
#: thousands of messages against a per-user rate limit, and riding one out takes minutes. Two
#: different jobs, two different numbers, and reusing the query-budget figure here would fail
#: a seeding run partway through - which is the one failure that leaves a mailbox half full.
SEED_MAX_ATTEMPTS: Final[int] = 6
SEED_BASE_SECONDS: Final[float] = 2.0
SEED_FACTOR: Final[float] = 2.0
SEED_MAX_SLEEP_SECONDS: Final[float] = 64.0

#: Statuses worth trying again. 429 is the rate limit a bulk insert will certainly meet; 500,
#: 502, 503 and 504 are Gmail's transient failures. Nothing else is retried: a 400 means the
#: message is wrong and retrying it is a loop, and a 403 means the grant is wrong and
#: retrying it is a loop that also looks like an attack.
RETRYABLE: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})


class WritesNotApproved(RuntimeError):
    """A write was attempted on a transport nobody approved for writing."""


class SeedTransportError(RuntimeError):
    """Gmail refused, or answered something this transport will not guess at."""


class ThreadingRefused(SeedTransportError):
    """Gmail put the message in a different thread than the one the insert asked for."""


#: Raised by `delete` for a message the mailbox does not have. Declared in `substrate`, beside
#: the protocol it is part of, and re-exported here so a reader of this module can find it.
#:
#: Deleting 2,252 messages one at a time can stop partway - a rate limit that outlasts its
#: retries, a token that expires - and the record naming all of them is the only safe input to
#: a second attempt. Without this, that attempt reports every message the first one already
#: removed as an error, which is the least useful possible output from a step whose whole job
#: is to say what is left.
AlreadyGone = AlreadyGone


@dataclass
class GmailSeedTransport:
    """`substrate.SeedTransport` over the real API, with writes gated.

    `credential` is whatever `verify_seed_account` observed the profile through; it is passed
    back to `assert_bound_to` on every write, so a session minted while authenticated as the
    seed account cannot be used by an operation running on a different client.
    """

    http: httpx.Client
    session: SeedSession
    credential: object
    access_token: str
    approved_by_owner: bool = False
    #: Injected so the offline tests drive every retry path - including the exhaustion - in
    #: no time at all, and so a real run's waiting is this object's and not a module's.
    sleeper: Callable[[float], None] = time.sleep
    jitterer: Callable[[], float] = random.random
    max_attempts: int = SEED_MAX_ATTEMPTS
    #: What the transport actually waited, in seconds. A seeding run that took an hour should
    #: be able to say how much of that was Gmail telling it to slow down.
    slept_seconds: float = 0.0
    retries: int = 0

    # --- reads ---------------------------------------------------------------------------

    def authenticated_address(self) -> str:
        """The address the session was bound to. Observed once, by `verify_seed_account`."""
        return self.session.address

    def count_matching(self, query: str) -> int:
        """An exact count of the messages matching `query`, by paging the id list.

        Scoped **without spam and trash**, explicitly rather than by Gmail's default. The
        settle gate is counting messages this run inserted with `neverMarkSpam=true`, so the
        scope that answers "is it indexed yet" is the one a mailbox owner means by their mail.
        """
        return self._count(query, scope=MailboxScope.WITHOUT_SPAM_AND_TRASH)

    def count_everything(self) -> int:
        """Every message Gmail will show, spam and trash included.

        For the pre-seeding survey, where the question is how much is already in the account
        and the honest answer includes the parts the default scope hides.
        """
        scope = MailboxScope.WHOLE_MAILBOX
        return self._count(scope.query, scope=scope)

    def _count(self, query: str, *, scope: MailboxScope) -> int:
        total = 0
        page: str | None = None
        for _ in range(MAX_COUNT_PAGES):
            params: dict[str, str] = {
                "q": query,
                "maxResults": "500",
                # **The `q` spelling never travels without this** (round 12's standing rule).
                # A count scoped one way by the operator and another by the parameter is a
                # number nobody can read.
                "includeSpamTrash": "true" if scope.include_spam_trash else "false",
            }
            if page is not None:
                params["pageToken"] = page
            body = self._json("GET", f"{GMAIL_BASE}/messages", params=params)
            total += len(body.get("messages") or ())
            page = body.get("nextPageToken")
            if not page:
                return total
        raise SeedTransportError(
            f"{query!r} still had pages after {MAX_COUNT_PAGES}; a settle gate polling a query "
            "this broad is a mistake in the query rather than a reason to keep paging"
        )

    # --- writes, gated -------------------------------------------------------------------

    def insert(self, raw: str, *, thread_id: str | None = None) -> InsertedMessage:
        """`users.messages.insert` with `internalDateSource=dateHeader`, into `thread_id`.

        `dateHeader` rather than the default, because the corpus's dates are the measurement:
        the position sweep and every temporal family are built on `internalDate`, and letting
        Gmail stamp the insert time would collapse a corpus spanning months into one minute.

        **`thread_id` is requirement 1 of three, and it is not optional for a reply.** Gmail's
        threading guide states the three conditions for adding a message to an existing thread:
        the target `threadId` is part of the `messages` resource you supply, the `References`
        and `In-Reply-To` headers comply with RFC 2822, and the `Subject` headers match. The
        corpus satisfies the second and third; without the first, Gmail opens a new thread per
        message and says nothing about it. R-M2-033 is what that cost.
        """
        self._refuse_unless_approved("insert")
        payload: dict[str, Any] = {
            "raw": base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")
        }
        if thread_id is not None:
            payload["threadId"] = thread_id
        body = self._json(
            "POST",
            f"{GMAIL_BASE}/messages",
            params={"internalDateSource": "dateHeader", "neverMarkSpam": "true"},
            json=payload,
        )
        gmail_id = body.get("id")
        assigned = body.get("threadId")
        if not isinstance(gmail_id, str) or not isinstance(assigned, str):
            raise SeedTransportError(
                f"insert returned no id/threadId ({body!r}); the manifest cannot be joined to "
                "a message the API did not name"
            )
        # **The association is checked, not assumed.** When Gmail declines to add a message to
        # the requested thread - the subject does not match, the references name nothing in it
        # - it does not fail the call: it creates the message in a **new** thread and returns
        # that id. A seeder that trusted the request would discover its corpus was 2,248
        # separate conversations only at the end, which is exactly how R-M2-033 happened.
        if thread_id is not None and assigned != thread_id:
            raise ThreadingRefused(
                f"insert asked Gmail for threadId {thread_id} and the message was created in "
                f"{assigned}. Gmail declined the association, which it does silently: check "
                "that the Subject matches the thread's and that In-Reply-To/References name a "
                "message already in it (the three conditions in Gmail's threading guide). "
                "Stopping here rather than seeding a corpus of single-message threads"
            )
        return InsertedMessage(
            rfc822_message_id=_message_id_of(raw), gmail_id=gmail_id, thread_id=assigned
        )

    def get_thread(self, thread_id: str) -> tuple[str, ...]:
        """The message ids `users.threads.get` reports for one thread, at metadata format.

        Read-only, and the only way to answer "did these messages end up in one conversation"
        from Gmail's own side rather than from what `insert` returned.
        """
        body = self._json(
            "GET",
            f"{GMAIL_BASE}/threads/{thread_id}",
            params={"format": "metadata"},
        )
        rows = body.get("messages") or ()
        return tuple(one["id"] for one in rows if isinstance(one, dict) and "id" in one)

    def delete(self, gmail_id: str) -> None:
        """`users.messages.delete` - **permanent, not trash**. Driven from insert results.

        `messages.delete` bypasses the trash entirely: the message is gone, not recoverable
        from the bin, and there is no undo. `AlreadyGone` for a 404 or 410, because a second
        pass over the same record should report what is left rather than what it repeated.
        """
        self._refuse_unless_approved("delete")
        try:
            self._request("DELETE", f"{GMAIL_BASE}/messages/{gmail_id}")
        except SeedTransportError as failure:
            if " returned 404" in str(failure) or " returned 410" in str(failure):
                raise AlreadyGone(f"{gmail_id} is not in the mailbox") from failure
            raise

    # --- the gate ------------------------------------------------------------------------

    def _refuse_unless_approved(self, what: str) -> None:
        if not self.approved_by_owner:
            raise WritesNotApproved(
                f"{what} was attempted on a transport built without approved_by_owner=True. "
                "Seeding a mailbox is irreversible, so the approval is an argument a human "
                "types after reading what the run will do - there is no setting that turns "
                "it on by default"
            )
        # **Re-checked here, at the point of use** (amendment A7). A session minted while
        # authenticated as the seed account must not be usable by an operation running on a
        # different credential, and a check that ran at construction cannot see that.
        self.session.assert_bound_to(self.credential)

    # --- plumbing ------------------------------------------------------------------------

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        what = url.rsplit("/", 1)[-1]
        for attempt in range(1, self.max_attempts + 1):
            response = self.http.request(
                method,
                url,
                params=dict(params or {}),
                json=dict(json) if json is not None else None,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            if response.status_code < 400:
                return response
            retryable = response.status_code in RETRYABLE
            if not retryable or attempt == self.max_attempts:
                tried = f" on attempt {attempt} of {self.max_attempts}" if retryable else ""
                raise SeedTransportError(f"{method} {what} returned {response.status_code}{tried}")
            self._wait(attempt, response.headers.get("Retry-After"))
        raise SeedTransportError(f"{method} {what} exhausted its attempts")  # pragma: no cover

    def _wait(self, attempt: int, retry_after: str | None) -> None:
        """Sleep before the next attempt. **`Retry-After` wins where Gmail sent one.**

        Gmail knows how long its own limit has left to run and this transport does not, so a
        header it sent is obeyed rather than averaged with a guess - capped, because a header
        is also a thing a proxy can get wrong.
        """
        delay = SEED_BASE_SECONDS * (SEED_FACTOR ** (attempt - 1))
        if retry_after is not None:
            # A header a proxy mangled is not a reason to stop retrying, so a value that will
            # not parse falls back to the computed delay rather than raising.
            with contextlib.suppress(ValueError):
                delay = max(delay, float(retry_after.strip()))
        delay = min(delay, SEED_MAX_SLEEP_SECONDS)
        delay *= 1.0 + 0.25 * self.jitterer()
        self.retries += 1
        self.slept_seconds += delay
        self.sleeper(delay)

    def _json(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = self._request(method, url, params=params, json=json).json()
        if not isinstance(body, dict):
            what = type(body).__name__
            raise SeedTransportError(f"{method} {url} answered {what}, not an object")
        return body


def _message_id_of(raw: str) -> str:
    """The `Message-ID` the corpus wrote, read back off the raw message.

    Read rather than passed in, so the id this transport reports is the one that actually went
    over the wire. A mismatch between the manifest's id and the inserted message's is exactly
    what `substrate.verify` exists to catch, and it cannot catch it if the transport echoes the
    manifest's copy back.
    """
    for line in raw.splitlines():
        if not line.strip():
            break
        if line.lower().startswith("message-id:"):
            return line.split(":", 1)[1].strip()
    raise SeedTransportError(
        "the raw message carries no Message-ID header; Gmail threads on it, so a corpus "
        "without one would collapse conversations the manifest describes as separate"
    )


__all__ = [
    "GMAIL_BASE",
    "MAX_COUNT_PAGES",
    "GmailSeedTransport",
    "SeedTransportError",
    "WritesNotApproved",
]
