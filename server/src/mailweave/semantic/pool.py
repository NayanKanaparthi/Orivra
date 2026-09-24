"""The L5 candidate pool: what gets embedded, and what the pool is *not* (AD D.5, A.7a).

**The pool is a reading list, not a result set.** Three rules hold it apart from disclosure,
and each one is the answer to a way the rung could have become a second, unaccountable
retrieval path:

  * **Pool membership creates no `source`, no mini-map and no stub row.** It is disclosed by
    its *scoping rule* and its size in `retrieval_report.pool`, and enumerated by id in the
    trace (`semantic.pool_ids[]`) so EV-01 can be joined against a real set. 300 stub rows
    would blow the token ceiling and say nothing; the rule and the count say what was looked
    at, and the trace says which.
  * **The pool is still inside `H`.** Step (b)'s participant probes are `messages.list`
    calls and step (a)/(c)'s thread reads are `threads.get` calls, so every id either one
    returns is admitted by the ledger at the moment of the call, under clauses H-lex and
    H-thr. Nothing here can look at a message without the disposition owing an account of
    it - which is why this module never takes an id from anywhere but a recorded call.
  * **The pool is bounded before it is built, not while it is being built.** `plan_pool` is
    a pure function of the parse and of what the lexical ladder already touched; it names
    every thread the pool *would* read before a single one is read, which is the same
    enumerability property `plan_ladder` gives the lexical rungs.

**Priority order is the design, not an optimisation.** Threads the ladder already touched
come first because they are the ones the query's own routes produced; participant threads
next because the query named those people; recency last because it is the weakest claim on
relevance of the three. When `max_pool_threads` cuts, it cuts from the weakest end, and the
threads it cut are declared with `cap: "max_pool_threads"` and a widening call rather than
dropped.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from mailweave.gmail.client import RecordedThread
from mailweave.gmail.models import Message
from mailweave.query.analysis import ParsedQuery, fold
from mailweave.query.operators import OperatorName
from mailweave.semantic.profile import POOL_BODY_HEAD_CHARS, PoolTextMode, SemanticProfile
from mailweave.structure.participants import addresses_in_header

#: The address headers a pool row states, in the order it states them. `Cc` is deliberately
#: absent: PF-2 recorded that `format=metadata` did not return `Cc` for the sampled thread,
#: and a pool row whose text depends on a header the fetch may not carry would embed
#: different text for the same message depending on which arm fetched it.
POOL_ADDRESS_HEADERS: Final[tuple[str, ...]] = ("From", "To")

#: How many days back the default recency window reaches when the query named no window.
#: A *window*, not a ranking: step (c) is "most-recent threads in the query's date window,
#: or a default recency window if none" (D.5), and a default that reached the whole mailbox
#: would make the pool's scoping rule unfalsifiable.
DEFAULT_RECENCY_DAYS: Final[int] = 90


class PoolStep(StrEnum):
    """Which of D.5's three steps put a thread in the pool. Priority order is declaration order."""

    #: (a) threads already touched by L0-L3.
    LADDER = "ladder"
    #: (b) threads of participants the query named.
    PARTICIPANT = "participant"
    #: (c) most-recent threads in the query's date window, or a default recency window.
    RECENCY = "recency"


@dataclass(frozen=True)
class PoolProbe:
    """One `messages.list` the pool would send, named before it is sent."""

    step: PoolStep
    query: str
    #: What this probe is looking for, for the scope rule. Never mail-derived text: a
    #: participant operator's value is the *user's own query*, which the response already
    #: echoes in `asked_for`.
    label: str


@dataclass(frozen=True)
class PoolPlan:
    """Every thread the pool would read and every probe it would send, before any of it runs.

    The same property `plan_ladder` gives the lexical rungs: a reviewer can list what the
    pool will look at without letting it look at anything, and the scope rule the response
    declares is rendered from this object rather than from what happened to come back.
    """

    seed_threads: tuple[str, ...]
    probes: tuple[PoolProbe, ...]
    max_threads: int
    max_messages: int
    text_mode: PoolTextMode
    window_label: str

    @property
    def scope_rule(self) -> str:
        """T-RO1's verbatim declaration of how this pool was scoped."""
        parts = [f"threads touched by L0-L3 ({len(self.seed_threads)})"]
        participants = [p.label for p in self.probes if p.step is PoolStep.PARTICIPANT]
        if participants:
            parts.append("threads of participants named by the query: " + ", ".join(participants))
        if any(p.step is PoolStep.RECENCY for p in self.probes):
            parts.append(f"most-recent threads in {self.window_label}")
        return (
            "union, in priority order, of "
            + "; ".join(parts)
            + f"; capped at max_pool_threads={self.max_threads} threads and "
            f"max_pool_messages={self.max_messages} message rows; pool text is "
            f"{self.text_mode.value}"
        )


def _recency_query(parsed: ParsedQuery, *, now: datetime) -> tuple[str, str]:
    """The step-(c) probe and the human label for its window.

    The query's own window when it named one - a pool scoped wider than the question would
    be reading mail the user did not ask about - and otherwise a bounded default. `after:`
    takes Gmail's epoch-seconds form, which A.6a rule 4 already uses everywhere else.
    """
    window = parsed.window
    if window is not None and window.start is not None:
        start = window.start
        label = f"the query's own date window (from {start.date().isoformat()})"
    else:
        start = datetime.fromtimestamp(now.timestamp() - DEFAULT_RECENCY_DAYS * 86_400, tz=UTC)
        label = f"the default recency window ({DEFAULT_RECENCY_DAYS} days)"
    clause = f"after:{int(start.timestamp())}"
    if window is not None and window.end is not None:
        clause += f" before:{int(window.end.timestamp())}"
    return clause, label


def plan_pool(
    parsed: ParsedQuery,
    *,
    touched_threads: Sequence[str],
    profile: SemanticProfile,
    now: datetime,
) -> PoolPlan:
    """What the pool would read for this query. Pure: nothing here calls Gmail.

    `touched_threads` arrives in the caller's own priority order (the ladder's), and is
    **not** re-sorted here: the ladder ranked those threads by the rung that found them, and
    a second ordering of one set is two answers to one question.
    """
    probes: list[PoolProbe] = []
    for participant in parsed.participants:
        if participant.negated:
            # A negated participant says who the answer is *not* from. Probing for them
            # would fill the pool with exactly the messages the query excluded.
            continue
        value = participant.address or participant.display
        if not value:
            continue
        role = "from" if participant.role is OperatorName.FROM else participant.role.value
        probes.append(
            PoolProbe(step=PoolStep.PARTICIPANT, query=f"{role}:{value}", label=f"{role}:{value}")
        )
    recency, window_label = _recency_query(parsed, now=now)
    probes.append(PoolProbe(step=PoolStep.RECENCY, query=recency, label=window_label))
    return PoolPlan(
        seed_threads=tuple(dict.fromkeys(touched_threads)),
        probes=tuple(probes),
        max_threads=profile.max_pool_threads,
        max_messages=profile.max_pool_messages,
        text_mode=profile.pool_text_mode,
        window_label=window_label,
    )


@dataclass(frozen=True)
class PoolRow:
    """One message in the pool, and the exact text that was embedded for it.

    `basis` is the string D.7 requires beside every numeric score: *the text that was
    actually embedded*, named rather than described, so a reader can tell a snippet-branch
    score from a body-head-branch one without consulting the profile.
    """

    message_id: str
    thread_id: str
    step: PoolStep
    text: str
    basis: str


def pool_row_text(
    message: Message, *, mode: PoolTextMode, body_head: Callable[[str], str | None] | None = None
) -> str:
    """The text D.5 embeds for one message row, on whichever branch PF-2 settled.

    Three branches and they are not interchangeable - the branch is what PF-2 decided and
    what the profile carries, and it travels onto every score as `basis` because a cosine
    over `subject+participants` alone answers a different question from one over
    `subject+participants+snippet`. See D.5's own worked example: "postpone the launch"
    against "We'll push go-live into Q4" is invisible without the snippet.
    """
    payload = message.payload
    subject = (payload.header("Subject") if payload is not None else None) or ""
    addresses: list[str] = []
    if payload is not None:
        for name in POOL_ADDRESS_HEADERS:
            # `(display name, address)` - see `_addresses_of`, which had this backwards.
            for _display, address in addresses_in_header(payload.header(name)):
                folded = fold(address)
                if folded not in addresses:
                    addresses.append(folded)
    head = [subject.strip(), " ".join(addresses)]
    if mode is PoolTextMode.SNIPPET:
        head.append((message.snippet or "").strip())
    elif mode is PoolTextMode.BODY_HEAD:
        text = body_head(message.id) if body_head is not None else None
        head.append((text or "")[:POOL_BODY_HEAD_CHARS].strip())
    return "\n".join(part for part in head if part)


@dataclass
class PoolBuild:
    """What the pool actually read, as opposed to what it planned to.

    **`capped_by` names a cause per thread rather than one cause for the build**, because
    three different things keep a thread out and they have three different remedies: the
    pool's own width cap (`max_pool_threads`), its row cap (`max_pool_messages`), and a
    budget breach that stopped the query altogether. A single `stopped_by` would have made
    every excluded thread carry the first cap that fired, which is how a `withheld` record
    ends up offering a call that cannot recover it.
    """

    plan: PoolPlan
    rows: tuple[PoolRow, ...] = ()
    threads_read: tuple[str, ...] = ()
    #: `{thread id: the observation the pool made of it}`, so a thread the pool read and the
    #: response later discloses is **fetched once** (I-3). Without this the pool's read and
    #: the map's read were two `threads.get` calls on one thread, which cost 40 u twice and -
    #: because each call stamps its own `fetched_at` - produced a source whose freshness
    #: stamp was not the one the ledger sealed. `Envelope` refused that, loudly, which is the
    #: design working: a response that can restate a fetch time can claim an old answer is
    #: new (contract R-08, amendment A6).
    observations: Mapping[str, RecordedThread] = field(default_factory=dict)
    #: `{thread id: cap name}` for every candidate the build did not read, in the order it
    #: would have read them. A thread whose own fetch failed is **not** here and is not in
    #: `threads_read` either: nothing was recorded for it, so it never entered `H`.
    capped_by: Mapping[str, str] = field(default_factory=dict)
    #: Threads whose `threads.get` failed. Named so the scope rule's counts can be checked
    #: against the candidate list without the difference looking like a silent drop.
    threads_unfetchable: tuple[str, ...] = ()
    probes_sent: int = 0
    #: Threads known to the plan and its probes, in priority order, before any cap.
    candidates: tuple[str, ...] = ()
    by_step: Mapping[str, int] = field(default_factory=dict)

    @property
    def threads_capped(self) -> tuple[str, ...]:
        return tuple(self.capped_by)

    @property
    def thread_count(self) -> int:
        return len(self.threads_read)

    @property
    def message_count(self) -> int:
        return len(self.rows)

    @property
    def texts(self) -> tuple[str, ...]:
        return tuple(row.text for row in self.rows)


__all__ = [
    "DEFAULT_RECENCY_DAYS",
    "POOL_ADDRESS_HEADERS",
    "PoolBuild",
    "PoolPlan",
    "PoolProbe",
    "PoolRow",
    "PoolStep",
    "plan_pool",
    "pool_row_text",
]
