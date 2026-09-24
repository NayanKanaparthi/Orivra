"""What a family builder produces, before any of it becomes mail.

A builder returns `ThreadDraft`s made of `Line`s. A line says who wrote it, what it says, what
it was planted to be, and **how long after the previous line it was sent**. That last field is
the repair for R-M2-048: chronology is not decorated onto a finished thread, it is stated by
the builder that knows what the ordering has to mean, and `Chronology.stamp` turns the gaps
into dates that strictly increase with position. A family that needs an ordering across threads
- F13's "after the September review", F16's successive revisions, F15's split conversation -
anchors on `world.EVENTS` and says so in `anchor`.

The structural anomalies EP §4.7 F15 requires are *not* chronological, and the model keeps them
apart on purpose: `subject_change_at` and `orphan` describe how a conversation is threaded and
titled, not when it happened. Removing date disorder therefore does not remove the anomalies a
family is built on, which is the distinction the repair brief asked for.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field
from typing import Final

from .manifest import MESSAGE_ROLES, Attachment
from .world import BY_KEY, EPOCH

#: Office hours, so consecutive messages on one day still order strictly and a reader can tell
#: a same-day reply from a next-day one.
DAY_START: Final[int] = 9
DAY_END: Final[int] = 18

#: Roles that carry the answer a case is scored against, as against the roles that carry a
#: distractor or ordinary traffic. `place` refuses to overwrite one of these, and `coverage`
#: uses the same set to decide what counts as evidence, so the generator and the checker cannot
#: drift apart on what an answer-bearing message is.
EVIDENCE_ROLES: Final[frozenset[str]] = frozenset(
    {"evidence", "authored_claim", "confirmation", "reversal", "attachment_cover"}
)


@dataclass(frozen=True)
class Line:
    """One message, as the family that needs it describes it."""

    role: str
    text: str
    sender: str
    """A `world.PEOPLE` key. Identity is a key rather than an address so the same-name and
    changed-address pairs stay joinable by the coverage rules that check them."""

    gap_hours: int = 20
    """Hours after the previous line. Must be > 0: two messages in one conversation sharing a
    timestamp leave the ordering undefined, and F5, F16 and F17 are all ordering claims."""

    is_distractor: bool = False
    attachments: tuple[Attachment, ...] = ()
    subject_override: str | None = None
    """Set on the message where a conversation's subject changes (F15)."""

    replies_to: int | None = None
    """The position this message answers, where the reply relation carries meaning.

    F13 is registered for "ordering **plus reply-relationship** reasoning, not date filtering
    alone", and an audit found its threads were strict chains - reply order was the position
    vector again and carried nothing. Where a builder knows what answers what, it says so."""

    def __post_init__(self) -> None:
        if self.role not in MESSAGE_ROLES:
            raise ValueError(f"role {self.role!r} is not in MESSAGE_ROLES")
        if self.sender not in BY_KEY:
            raise ValueError(f"sender {self.sender!r} is not in world.PEOPLE")
        if self.gap_hours <= 0:
            raise ValueError(
                f"gap_hours must be positive; {self.gap_hours} would let two messages in one "
                "conversation share a timestamp, and every ordering family reads that order"
            )


@dataclass
class ThreadDraft:
    """One conversation a builder intends, with the ground truth it is being built to carry."""

    family: str
    subject: str
    situation_key: str
    lines: list[Line]
    start_offset_days: int
    """Days after `EPOCH` for the first message. Builders that must sit either side of a named
    event compute this from `world.BY_EVENT` rather than guessing."""

    participants: tuple[str, ...] = ()
    """Everyone on the conversation, including people who never send. F14's reply-all bystander
    is exactly a participant with no line of their own, so recipients are stated, not derived
    from who happened to write."""

    paraphrase_of_fact: str = ""
    answer_note: str = ""
    """Prose for the case author: what the correct answer is and what makes a wrong one wrong.
    It is written into the manifest, never into a message body."""

    orphan: bool = False
    """True when this conversation is structurally a continuation of another but carries no
    reference headers, so Gmail files it separately (F15). Its first line is a reply in content
    and a new conversation in fact."""

    continues: str = ""
    """The `situation_key` of the conversation this one continues, for F15's forward, orphan
    and ceiling-split shapes. Recorded so a case author can state both halves."""

    answer_override: str | None = None
    """The case's answer, when it is not the situation's. F16 adopts one of five revisions and
    the adopted one is drawn, so the situation's own value is sometimes a *wrong* revision; F7's
    second half answers with a figure. Without this the manifest declared an answer the thread
    did not have, and the rule that checks distractors flagged four threads a seed."""

    never_sends: tuple[str, ...] = ()
    """Participants who must remain recipients only. F14's bystander is the family's whole
    first half - "who else was on the thread" is answerable from the senders alone if everyone
    on it writes - and appending ordinary traffic gave them a message."""

    evidence_at: tuple[int, ...] = ()
    """Positions the case's answer actually rests on, when the roles do not say it.

    F16's answer is carried by one of five messages that are all planted as near-duplicates,
    and the confirmation that names it carries no value. Deriving evidence from roles pointed
    the key at the confirmation, and the answer string was not in it - which an independent
    reader reported as the key not naming the message that holds the answer."""

    follows_parent: bool = False
    """True when this conversation continues `continues` **in time** as well as in subject.

    F15's forward, orphan and split all do; F8's "my copy" does not, and forcing it to made the
    stale attachment the later file in every pair - the exact date oracle the alternation was
    added to remove."""

    wrong_override: str | None = None
    older_override: str | None = None
    """Set where a family's competitors are not the situation's own values. F16's five
    revisions are minted for the thread, so declaring the situation's `wrong` alongside them
    named a value no candidate carried."""

    facts: dict[str, str] = field(default_factory=dict)
    """Family-specific structured ground truth the coverage rules read: F2's window edges,
    F15's structural shape, F16's adopted revision, F1's identifier. Prose in `answer_note` is
    for the case author; a rule that had to parse that prose would be measuring my writing."""

    cross_thread_decoy_for: str = ""
    """Set on a filler thread planted to share vocabulary with a scored thread (EP §4.6)."""

    barred_values: tuple[str, ...] = ()
    """Values this conversation mints for itself that ordinary traffic must not state.

    F16 draws five figures per thread and the answer is one of them, so none of them appears in
    the situation and the standing value-leak check cannot see them. The trailing traffic
    `with_tail` appends is generated after the builder has returned, which is where a foil
    minted the adopted figure and put it on a filler message."""

    tail_done: bool = False
    """True when the builder appended the trailing ordinary traffic itself.

    R-M2-067. A family registered on a *rank* relationship has to establish it against the
    conversation it actually ships - and `with_tail` runs after the builder, so a thread that
    left the builder with its trap at rank 1 of 21 arrived at the mailbox with it at rank 2 of
    30. Those builders append the tail before their redraw loop and set this, and `with_tail`
    leaves them alone."""

    day_offsets: tuple[int, ...] = ()
    """Absolute day offsets from EPOCH, one per line, when a family needs its messages on
    particular dates rather than at particular intervals. F2 filters on a window and needs its
    §1.2.2 margin of at least 48 hours from each edge; F13 has to sit either side of a named
    event. Stated rather than accumulated, because accumulating gaps to land on a date is how a
    margin silently becomes 47 hours."""

    def __post_init__(self) -> None:
        if not self.lines:
            raise ValueError(f"{self.family}/{self.situation_key}: a thread with no messages")
        if self.orphan and not self.continues:
            raise ValueError("an orphan conversation must name what it continues")
        if self.start_offset_days < 0 or any(one < 0 for one in self.day_offsets):
            raise ValueError(
                f"{self.family}/{self.situation_key}: a negative day offset puts messages "
                "before the corpus epoch, which makes the corpus's own start date a lie and "
                "any window a family filters on ambiguous"
            )


def working_hour(situation_key: str, index: int) -> int:
    """The clock time of one message, drawn from the thread's identity rather than its shape.

    **R-M2-072, second half.** The hour used to be `DAY_START + (index * 5 + 3) % 9` - a
    function of the message's *position*. Positions are where a family puts its roles, so the
    clock time tracked the role through the position: at seed 4311 every one of eleven
    `trap_decoy` messages and all eight `objection` messages landed after 13:00, against a base
    rate of 0.61, and `near_duplicate` landed there 7 times in 30. A reader who never opened a
    body could sort by the clock.

    Deriving it per (thread, index) from a stable digest removes the coupling to position
    without reintroducing the one it replaced: the hour is a function of neither the role nor
    the gap, and an audit can recompute it. `blake2b` rather than `hash()` because §3.7's
    regeneration contract is a claim about a function - the same inputs must give the same
    corpus in another process, and `hash()` is salted per process.
    """
    digest = hashlib.blake2b(f"{situation_key}:{index}".encode(), digest_size=8).digest()
    return DAY_START + int.from_bytes(digest, "big") % (DAY_END - DAY_START)


@dataclass
class Chronology:
    """Turns gaps into timestamps, and refuses to produce a thread that runs backwards."""

    epoch: dt.date = EPOCH
    _cursor: dt.datetime = field(
        default_factory=lambda: dt.datetime.combine(EPOCH, dt.time(DAY_START))
    )

    def stamp(self, draft: ThreadDraft) -> tuple[dt.datetime, ...]:
        """One timestamp per line, strictly increasing, starting at the draft's own offset.

        Gaps roll across nights and weekends rather than being clamped into the working day,
        because clamping is how the old generator produced a thread whose tenth message was
        dated before its ninth.
        """
        if draft.day_offsets:
            if len(draft.day_offsets) != len(draft.lines):
                raise ValueError(
                    f"{draft.situation_key}: {len(draft.day_offsets)} day offsets for "
                    f"{len(draft.lines)} lines"
                )
            fixed: list[dt.datetime] = []
            for index, day in enumerate(draft.day_offsets):
                at = dt.datetime.combine(
                    self.epoch + dt.timedelta(days=day),
                    dt.time(working_hour(draft.situation_key, index)),
                )
                if fixed and at <= fixed[-1]:
                    at = fixed[-1] + dt.timedelta(hours=1)
                fixed.append(at)
            if any(fixed[i] >= fixed[i + 1] for i in range(len(fixed) - 1)):
                raise AssertionError(  # pragma: no cover - the bump above prevents it
                    f"{draft.situation_key}: fixed dates are not strictly increasing"
                )
            return tuple(fixed)
        # **The opener's hour is drawn too.** R-M2-072, second half. It used to be `DAY_START`
        # in every conversation, and position 0 is filler in every conversation, so filler
        # carried one guaranteed nine-o'clock message per thread and its share of afternoon
        # messages sat below the uniform 5/9 by exactly that much. Every planted role then
        # looked late *relative to filler* - `evidence` measured 65% against filler's 54% while
        # the drawn distribution says 56% - and the comparison a solver makes is precisely that
        # one. Nothing about a thread's first message says it is sent at nine.
        when = dt.datetime.combine(
            self.epoch + dt.timedelta(days=draft.start_offset_days),
            dt.time(working_hour(draft.situation_key, 0)),
        )
        out: list[dt.datetime] = [when]
        for index, line in enumerate(draft.lines[1:], start=1):
            when = when + dt.timedelta(hours=line.gap_hours)
            # **The hour is a fact of the thread, not of the message's role or its position.**
            # Gaps were once chosen per role - a reversal waited 48 hours, a decoy 6 - so the
            # clock tracked the role directly. Deriving the hour from the position fixed that
            # and left a second coupling, because a family puts its roles at the same positions
            # (R-M2-072); `working_hour` removes both.
            hour = working_hour(draft.situation_key, index)
            when = when.replace(hour=hour)
            # **A collision rolls to the next day at the same drawn hour**, rather than adding
            # an hour. R-M2-072, second half. Adding an hour is what left time-of-day tracking
            # role after the hour itself stopped doing so: a role written with a short gap -
            # `trap_decoy` waits six hours - lands on its predecessor more often, gets bumped
            # more often, and each bump moves it later in the day. `trap_decoy` was 78% after
            # 13:00 against a corpus base rate of 58% with the hour already drawn. Rolling the
            # date keeps the hour the one that was drawn, so the number of collisions a role
            # has stops changing what time of day it is written at.
            while when <= out[-1]:
                when = dt.datetime.combine(
                    when.date() + dt.timedelta(days=1), dt.time(hour)
                )
            out.append(when)
        strictly_increasing = all(out[i] < out[i + 1] for i in range(len(out) - 1))
        if not strictly_increasing:  # pragma: no cover - the loop above cannot produce this
            raise AssertionError(
                f"{draft.situation_key}: stamped dates are not strictly increasing. Every "
                "ordering family reads this order, and R-M2-048 was 84 threads of 84 where it "
                "ran backwards"
            )
        return tuple(out)


def days_before(event_offset: int, days: int) -> int:
    return max(0, event_offset - days)


def offset_of(event_key: str) -> int:
    from .world import BY_EVENT

    return (BY_EVENT[event_key].on - EPOCH).days


__all__ = [
    "DAY_END",
    "DAY_START",
    "EVIDENCE_ROLES",
    "Chronology",
    "Line",
    "ThreadDraft",
    "days_before",
    "offset_of",
    "working_hour",
]
