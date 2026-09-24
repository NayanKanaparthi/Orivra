"""What a generated corpus says about itself, written at generation time.

**The manifest is written by the generator, not derived from the mailbox afterwards.** That
ordering is the whole point: a manifest read back from Gmail would agree with whatever Gmail
did, including with a message that failed to insert, and a recall metric scored against it
would be scored against the system it is measuring. The generator states what it intends to
put there; verification then checks the mailbox against this, and a disagreement is a failure
of the substrate rather than a manifest that quietly moved.

`answer_key` is deliberately **not** case content. It is the ground truth *about the corpus* -
which message carries which sentinel token, how long each thread is, where each evidence
message sits in its thread - and the F1-F29 case families are built on top of it by the
milestones that need them (M2 for Gmail, M4 for Drive, M5 for Slack). Building the families
now would be building the thing the measurement is supposed to be free to change.
"""

from __future__ import annotations

from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


#: What one message was planted to be. **A closed vocabulary**, because the coverage report
#: and the case author both join on it, and a role nobody declared is a role nobody can find.
#: `filler` is on-topic traffic; everything else is a family's raw material.
MESSAGE_ROLES: Final[frozenset[str]] = frozenset(
    {
        "filler",
        "evidence",
        "proposal",
        "objection",
        "confirmation",
        "reminder",
        "reversal",
        "reinforcement",
        "authored_claim",
        "hearsay",
        "paraphrase_decoy",
        "trap_decoy",
        "attachment_cover",
        "attachment_wrong_version",
        "near_duplicate",
    }
)


class Attachment(Frozen):
    """A file the message carries. Small and textual, because the corpus must stay checkable.

    EP §4.3's F8 defines a pass as retrieving the carrying message **and signalling the
    attachment**; content extraction is scored only if MailWeave claims it. So what matters
    here is that the filename and the part exist in the mailbox and are joinable, not that the
    payload is elaborate.
    """

    filename: str = Field(min_length=1, max_length=200)
    media_type: str = Field(min_length=3, max_length=100)
    content: str = Field(min_length=1, max_length=8000)
    carries_the_fact: bool = False
    """True on the attachment the answer depends on, false on the same-named wrong version.
    F8's decoy is a file with the *same name* and different contents elsewhere in the corpus."""


class SeededMessage(Frozen):
    """One message the generator intends to insert, and everything scoring needs about it."""

    rfc822_message_id: str = Field(min_length=3, max_length=400)
    thread_key: str = Field(min_length=1, max_length=64)
    """The generator's own name for the conversation. Gmail's `threadId` is assigned on
    insert and is recorded separately by verification - a generator that predicted one would
    be predicting a server-side value."""

    position: int = Field(ge=0)
    sender: str = Field(min_length=3, max_length=320)
    recipients: tuple[str, ...] = Field(min_length=1)
    subject: str = Field(min_length=1, max_length=400)
    date_rfc2822: str = Field(min_length=10, max_length=64)
    body: str = Field(min_length=1)
    sentinels: tuple[str, ...] = ()
    """Tokens that occur in this message's body and nowhere else in the corpus. They are what
    the settle gate polls for and what a recall metric joins on."""

    is_distractor: bool = False
    in_reply_to: str | None = Field(default=None, max_length=400)
    references: tuple[str, ...] = ()

    role: str = "filler"
    """What this message was planted to be, from `MESSAGE_ROLES`. The generator used to plant
    every message identically, so a message meant to carry a decision was textually a message
    meant to carry nothing and six families had no substrate (R-M2-041). This field is how a
    coverage report can say what the corpus actually contains."""

    scenario_key: str = ""
    """Which situation in `scenarios.SCENARIOS` this message belongs to. Threads are built
    around one, so filler stays on topic instead of being noise."""

    attachments: tuple[Attachment, ...] = ()

    @model_validator(mode="after")
    def _the_role_is_one_the_vocabulary_names(self) -> Self:
        if self.role not in MESSAGE_ROLES:
            raise ValueError(
                f"{self.rfc822_message_id}: role {self.role!r} is not in the closed set "
                f"{sorted(MESSAGE_ROLES)}. An undeclared role cannot be counted by the "
                "coverage report, so a family would silently look unsupported"
            )
        return self

    @model_validator(mode="after")
    def _every_sentinel_is_actually_in_the_body(self) -> Self:
        missing = [token for token in self.sentinels if token not in self.body]
        if missing:
            raise ValueError(
                f"{self.rfc822_message_id}: sentinels {missing} are declared and absent from "
                "the body. A sentinel the corpus does not contain makes the settle gate wait "
                "forever and a recall metric score against nothing"
            )
        return self

    @model_validator(mode="after")
    def _a_reply_names_its_parent(self) -> Self:
        if self.position == 0:
            if self.in_reply_to is not None:
                raise ValueError(
                    f"{self.rfc822_message_id}: the first message of a thread names a reply "
                    "parent; threading would then depend on a message the corpus does not have"
                )
            return self
        if self.in_reply_to is None:
            raise ValueError(
                f"{self.rfc822_message_id}: position {self.position} and no In-Reply-To. "
                "Gmail threads on the reference headers, so a reply without one is a new "
                "conversation and the thread's stated total is wrong before anything is asked"
            )
        if self.in_reply_to not in self.references:
            raise ValueError(
                f"{self.rfc822_message_id}: In-Reply-To is not in References; a client that "
                "reads only References would place this message outside its own thread"
            )
        return self


class ThreadTruth(Frozen):
    """What is true of one conversation, which is what P1a and the position sweep score."""

    thread_key: str = Field(min_length=1, max_length=64)
    length: int = Field(gt=0)
    subject: str = Field(min_length=1, max_length=400)
    evidence_positions: tuple[int, ...] = ()

    family: str = ""
    """The EP §4.3 family this thread was built to support. One primary family per thread, so
    the structure a family needs is actually present rather than hoped for."""

    scenario_key: str = ""

    roles_at: dict[str, tuple[int, ...]] = Field(default_factory=dict)
    """Role to the positions carrying it. This is what makes a family's support checkable:
    F5 needs proposal, objection, confirmation and reminder all present in one thread, and
    this says whether they are."""

    participants: tuple[str, ...] = ()
    """Everyone on the conversation, including recipients who never send. F14's reply-all
    bystander is a participant with no message, so deriving this from senders loses it."""

    answer_note: str = ""
    """Prose ground truth for the case author: what the answer is, where it is, and what makes
    each distractor wrong. It lives here and never in a message body - a note in a body would
    be the answer-revealing marker R-M2-046 was."""

    answer: str = ""
    wrong_value: str = ""
    older_value: str = ""
    """The situation's three values, filled in by the generator from the situation this thread
    was built on. Structured, because every content coverage rule needs to ask whether a
    particular message states a particular value, and none of them should be parsing prose."""

    facts: dict[str, str] = Field(default_factory=dict)
    """Family-specific structured ground truth (F2's window, F15's shape, F16's adopted
    revision, F1's identifier)."""

    continues: str = ""
    """The thread_key of the conversation this one continues (F7's other half, F15's forward,
    orphan and split)."""

    follows_parent: bool = False
    """True when this conversation continues `continues` in time as well as in subject, so its
    first message is dated after the other's last. False on a sibling that merely shares a
    matter - F8's second copy of a file is not a continuation."""

    orphan: bool = False
    """A reply in content that carries no reference headers, so it is a separate conversation
    (F15). Its first message is deliberately not a reply at the header level."""

    cross_thread_decoy_for: str = ""
    has_alias_bridge: bool = False
    """True when a message in this thread pairs an entity's formal and colloquial names. The
    paraphrase families are written against the colloquial name, so whether the corpus bridges
    it is something the case author has to know: it is the difference between a hard case and
    an unanswerable one, and it is also a two-hop lexical route to the evidence."""

    first_date: str = ""
    last_date: str = ""

    paraphrase_of_fact: str = ""
    """The thread's fact restated with **no content word in common** with the evidence message.
    Ground truth about the corpus, not a query: F4 and F11 exist because a query written from
    this must not lexically match the evidence, and the author writes that query. Recording it
    here is how the corpus can be checked to *have* the disjoint restatement available."""
    """Positions carrying a sentinel. The position sweep needs these to be spread rather
    than clustered at the ends, and `Manifest` checks that they are in range."""

    @model_validator(mode="after")
    def _evidence_sits_inside_the_thread(self) -> Self:
        outside = [one for one in self.evidence_positions if not 0 <= one < self.length]
        if outside:
            raise ValueError(
                f"{self.thread_key}: evidence positions {outside} are outside a thread of "
                f"{self.length}"
            )
        return self


class AnswerKey(Frozen):
    """Ground truth about the corpus. **Not case content.**

    `sentinel_owner` is the join a recall metric uses: a token, and the one message that
    contains it. `thread_lengths` is what P1a compares `stated_total` against.
    """

    sentinel_owner: dict[str, str]
    threads: tuple[ThreadTruth, ...]

    settle_probe: tuple[str, ...] = ()
    """The bounded subset the settle gate polls and the index check asks about.

    Every message now carries a reference, because a marker only *some* messages carry is
    evidence about which ones they are (R-M2-046). That makes `sentinel_owner` a complete join
    table with one row per message, and polling ten thousand tokens against a live mailbox is
    not a gate, it is an outage. So verification runs against this subset instead.

    **It is chosen by position, never by role.** Two messages per conversation, the opener and
    the last reply, which is a rule that cannot correlate with what a message was planted to
    be. A probe set drawn from the evidence would put the answer key back in the mailbox
    through the side door."""

    @model_validator(mode="after")
    def _the_index_is_not_empty_and_every_owner_is_named(self) -> Self:
        """The first draft compared `len(list(d.values()))` to `len(d)`, which is always
        equal - a validator that could not fire, with a `# pragma: no cover` acknowledging
        it (review finding R-M1-026). What is worth checking is what a caller can actually
        get wrong: an empty index, and an owner that is not a message id.
        """
        if not self.sentinel_owner:
            raise ValueError(
                "an answer key with no sentinels can be joined on by nothing, and the settle "
                "gate it feeds would poll an empty list and pass immediately"
            )
        blank = [token for token, owner in self.sentinel_owner.items() if not owner.strip()]
        if blank:
            raise ValueError(f"sentinels {sorted(blank)} name no owner")
        unknown = [one for one in self.settle_probe if one not in self.sentinel_owner]
        if unknown:
            raise ValueError(
                f"the settle probe names {unknown[:3]}, which no message owns; the gate would "
                "poll for a token the corpus never contained and wait forever"
            )
        return self

    @property
    def thread_lengths(self) -> dict[str, int]:
        return {thread.thread_key: thread.length for thread in self.threads}


class Manifest(Frozen):
    """One generated corpus, whole, plus the inputs that reproduce it.

    `generator_version` and `master_seed` are here because §3.7's regeneration contract is a
    claim about a *function*: same inputs, byte-identical corpus. A manifest that did not
    carry its inputs would leave that claim uncheckable a month later.
    """

    generator_version: str = Field(min_length=1, max_length=40)
    master_seed: int = Field(ge=0)
    size_profile: str = Field(min_length=1, max_length=40)
    messages: tuple[SeededMessage, ...] = Field(min_length=1)
    answer_key: AnswerKey

    @model_validator(mode="after")
    def _the_answer_key_describes_these_messages(self) -> Self:
        by_id = {message.rfc822_message_id: message for message in self.messages}
        if len(by_id) != len(self.messages):
            raise ValueError(
                "two messages share an rfc822 Message-ID; Gmail threads on these, so the "
                "corpus would collapse conversations that the manifest says are separate"
            )
        # Every message now carries a reference of the same shape, so this check runs over
        # thousands of tokens rather than dozens and the original nested scan was quadratic.
        # Sentinels are single lowercase-alphanumeric words by construction, so one tokenising
        # pass over each body finds every occurrence of every sentinel at once.
        import re as _re

        holders: dict[str, list[str]] = {}
        declared = set(self.answer_key.sentinel_owner)
        for message in self.messages:
            for word in set(_re.findall(r"[a-z0-9]{6,}", message.body)):
                if word in declared:
                    holders.setdefault(word, []).append(message.rfc822_message_id)
        for token, owner in self.answer_key.sentinel_owner.items():
            if owner not in by_id:
                raise ValueError(f"sentinel {token!r} is owned by {owner!r}, which is not here")
            where = holders.get(token, [])
            if owner not in where:
                raise ValueError(
                    f"sentinel {token!r} is not in the body of its declared owner; the "
                    "settle gate would poll for a token the corpus never contained"
                )
            elsewhere = [one for one in where if one != owner]
            if elsewhere:
                raise ValueError(
                    f"sentinel {token!r} also occurs in {elsewhere[:3]}; a token with two "
                    "owners cannot be joined on, and the settle gate's expected count is wrong"
                )
        lengths = self.answer_key.thread_lengths
        actual: dict[str, int] = {}
        for message in self.messages:
            actual[message.thread_key] = actual.get(message.thread_key, 0) + 1
        if lengths != actual:
            raise ValueError(
                f"the answer key states thread lengths {lengths} and the corpus holds "
                f"{actual}; P1a scores stated_total against the key, so a key that disagrees "
                "with its own corpus makes every partiality number wrong"
            )
        return self

    @property
    def sentinels(self) -> tuple[str, ...]:
        """What verification polls. The complete table is `answer_key.sentinel_owner`."""
        return self.answer_key.settle_probe or tuple(sorted(self.answer_key.sentinel_owner))

    @property
    def all_references(self) -> tuple[str, ...]:
        return tuple(sorted(self.answer_key.sentinel_owner))

    @property
    def thread_keys(self) -> tuple[str, ...]:
        return tuple(thread.thread_key for thread in self.answer_key.threads)


__all__ = [
    "MESSAGE_ROLES",
    "AnswerKey",
    "Attachment",
    "Manifest",
    "SeededMessage",
    "ThreadTruth",
]
