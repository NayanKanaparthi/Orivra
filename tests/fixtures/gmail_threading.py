"""A mailbox double that threads the way Gmail documents, and refuses the way Gmail refuses.

**This file exists because the previous double was wrong in the one way that mattered.** It
assigned each inserted message the thread id of its manifest `thread_key`, which is to say it
handed itself the answer to the question the seeding run was there to ask. Every threading test
passed, and the real run produced 2,248 single-message conversations (R-M2-033).

So this double models the API instead of the intent. Gmail's threading guide states three
conditions for adding a message to an existing thread:

  1. the target `threadId` is part of the `messages` resource supplied with the request;
  2. `References` and `In-Reply-To` comply with RFC 2822;
  3. the `Subject` headers match.

`_Gmail` enforces all three, and - the part that makes the double useful - it enforces them the
way the API does: **a request that fails them is not an error.** The message is created in a new
thread and the new id is returned, silently. A seeder that does not compare the id it asked for
against the id it got cannot tell the two outcomes apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from mailweave_harness.seed.substrate import InsertedMessage

# **`[^\r\n]*` and not `\S+`.** `rfc2822` emits CRLF, and in MULTILINE mode `$` matches before
# a `\n` - which is *after* the `\r`, so a `\S+` group can never reach it. The first version of
# this file used `\S+`, read no Message-ID off any real corpus message, and quietly fell back to
# the Gmail id. A double that misreads its input is a double that answers a different question.
#: A reply prefix Gmail normalises away before comparing subjects: "Re: X" and "X" are one
#: subject as far as threading is concerned.
_REPLY_PREFIX = re.compile(r"^\s*(?:re|fwd|fw)\s*:\s*", re.IGNORECASE)


def _headers(raw: str) -> dict[str, str]:
    """The header block, parsed by splitting lines rather than by regex.

    **Written this way after two regex attempts got it wrong.** `rfc2822` emits CRLF, and in
    `re.MULTILINE` the `$` anchor matches before the `\n`, which is *after* the `\r`; a group
    that cannot consume `\r` can never reach it. Both attempts silently matched nothing, read
    no Message-ID off any real corpus message, and made the double answer a question nobody
    asked. Splitting on universal newlines and stopping at the blank line is what a header
    parser does anyway, and it cannot fail quietly.
    """
    out: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip():
            break
        name, _, value = line.partition(":")
        if _:
            out.setdefault(name.strip().lower(), value.strip())
    return out


def _normalised_subject(raw: str) -> str:
    subject = _headers(raw).get("subject", "")
    while _REPLY_PREFIX.match(subject):
        subject = _REPLY_PREFIX.sub("", subject, count=1).strip()
    return subject


@dataclass
class _Stored:
    gmail_id: str
    thread_id: str
    rfc822_message_id: str
    subject: str


@dataclass
class Gmail:
    """A mailbox that assigns ids, threads by the documented rules, and never explains itself."""

    messages: dict[str, _Stored] = field(default_factory=dict)
    threads: dict[str, list[str]] = field(default_factory=dict)
    address: str = "mailweave.test@example.test"
    counter: int = 0
    #: Every `threadId` an insert asked for, in order. A test asserts the seeder asks at all.
    requested: list[str | None] = field(default_factory=list)
    inserted_raw: list[str] = field(default_factory=list)
    counted: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    # -- the API ---------------------------------------------------------------------------

    def authenticated_address(self) -> str:
        return self.address

    def insert(self, raw: str, *, thread_id: str | None = None) -> InsertedMessage:
        self.requested.append(thread_id)
        self.inserted_raw.append(raw)
        self.counter += 1
        gmail_id = f"g{self.counter:06d}"
        rfc = _headers(raw).get("message-id") or gmail_id
        subject = _normalised_subject(raw)
        assigned = thread_id if self._may_join(thread_id, raw, subject) else gmail_id
        self.messages[gmail_id] = _Stored(gmail_id, assigned, rfc, subject)
        self.threads.setdefault(assigned, []).append(gmail_id)
        return InsertedMessage(rfc822_message_id=rfc, gmail_id=gmail_id, thread_id=assigned)

    def get_thread(self, thread_id: str) -> tuple[str, ...]:
        return tuple(self.threads.get(thread_id, ()))

    def count_matching(self, query: str) -> int:
        self.counted.append(query)
        return 1

    def count_everything(self) -> int:
        self.counted.append("<whole mailbox>")
        return len(self.messages)

    def delete(self, gmail_id: str) -> None:
        self.deleted.append(gmail_id)
        stored = self.messages.pop(gmail_id, None)
        if stored is not None and gmail_id in self.threads.get(stored.thread_id, []):
            self.threads[stored.thread_id].remove(gmail_id)

    # -- the three conditions --------------------------------------------------------------

    def _may_join(self, thread_id: str | None, raw: str, subject: str) -> bool:
        """Condition 1 is `thread_id`; 2 and 3 are checked against what is already there.

        A `False` here is **not** an error. Gmail creates the message in a thread of its own and
        returns that id, which is the behaviour that made R-M2-033 silent.
        """
        if thread_id is None:
            return False
        existing = self.threads.get(thread_id)
        if not existing:
            return False
        if any(self.messages[one].subject != subject for one in existing):
            return False  # condition 3
        known = {self.messages[one].rfc822_message_id for one in existing}
        headers = _headers(raw)
        parent = headers.get("in-reply-to")
        references = headers.get("references", "").split()
        if parent is None and not references:
            return False  # condition 2: nothing ties it to the thread
        return (parent in known) or any(one in known for one in references)


__all__ = ["Gmail"]
