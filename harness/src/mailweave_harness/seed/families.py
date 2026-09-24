"""One builder per registered family.

The generator this replaces had a single `generate()` that produced every thread the same way
and a `GATE_ALLOCATION` naming nine families against the seventeen EP §4.3 and §4.7 register
(R-M2-054). Every family here states its own construction, its own chronology and its own
ground truth, because the families do not have a shape in common: F17 needs a late reply that
scores *badly*, F12 needs an exact match that scores *well*, F16 needs five messages that
differ in one detail, and no shared template produces all three.

Three rules hold across every builder.

*No marker distinguishes evidence from anything else.* The old corpus appended `Reference
token: <sentinel>` to exactly the ninety-six messages that carried an answer and to no
distractor, so `grep` solved eight families (R-M2-046). Indexing verification is still needed,
so `corpus.py` now gives **every** message a reference of the same shape. A uniform marker
carries no information. Nothing in a body says what a message is; that lives in the manifest.

*Chronology is stated by whoever knows what it means.* Dates increase with position in every
thread. Where a family needs a specific ordering - a reminder after a confirmation, revisions
before an adoption, a reversal at the end, evidence on the far side of a named event - the
builder sets it, and `drafts.Chronology` refuses to emit anything that runs backwards.

*Lexical checks are construction checks.* `_assert_ranks` fails generation when the text does
not have the relationship the family is registered to have. It says nothing about retrieval.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from random import Random
from typing import Callable, Final

from . import chatter, lexical, voice
from .drafts import EVIDENCE_ROLES, Line, ThreadDraft, offset_of
from .manifest import Attachment
from .situations import NUMERIC_KINDS, Situation, mint_situations, mint_values
from .world import (
    BY_ENTITY,
    BY_KEY,
    CHANGED_ADDRESS_PAIR,
    EPOCH,
    PEOPLE,
    SAME_NAME_PAIR,
)

#: EP §4.3 and §4.7, per seed. F9 is out of the core suite by §4.3 and has no entry.
REGISTERED_N: Final[dict[str, int]] = {
    "F1": 10, "F2": 10, "F3": 84, "F4": 12, "F5": 8, "F6": 8, "F7": 6, "F8": 6,
    "F10": 10, "F11": 10, "F12": 10, "F13": 8, "F14": 8, "F15": 8, "F16": 8, "F17": 8,
}

FAMILY_NAMES: Final[dict[str, str]] = {
    "F1": "exact_lookup", "F2": "sender_date", "F3": "buried_evidence",
    "F4": "semantic_paraphrase", "F5": "decision_evolution", "F6": "participant_reasoning",
    "F7": "multi_thread", "F8": "attachment", "F10": "unanswerable_control",
    "F11": "semantic_lexical_trap", "F12": "semantic_negative_control",
    "F13": "temporal_structural", "F14": "participant_graph",
    "F15": "thread_structure_reality", "F16": "ranking_stress", "F17": "decision_reversal",
}

#: EP §4.4. Normative as fractions; the absolute index is computed against the thread's length.
SWEEP_FRACTIONS: Final[tuple[int, ...]] = (2, 7, 20, 37, 51, 83, 99)


class Exhausted(RuntimeError):
    """Raised when a profile asks for more distinct facts than the world can mint."""


@dataclass
class Context:
    """Everything a builder needs, and a situation pool it cannot draw from twice.

    **Two generators, and which one a decision comes from is the decision.** EP §5.3's
    anti-gaming lever requires the *shape* of the corpus to hold across seeds while the
    *surface* re-randomises: a system tuned to one seed's thread lengths or evidence positions
    must gain nothing on the next seed, and a system tuned to one seed's wording must lose
    everything. So `shape` is seeded from the generator version and the profile alone and
    decides how long a thread is, where the roles sit and how far apart the messages are;
    `rng` is seeded from the master seed and decides which situation, which words and which
    people. R-M2-044 was this contract broken in one direction; drawing everything from one
    generator, as the first draft of this rewrite did, breaks it in the other.
    """

    rng: Random
    shape: Random
    long_length: int
    pool: list[Situation]
    foil_pool: tuple[Situation, ...] = ()
    """Matters no thread is built on, used by `chatter` to plant decisive sentences about
    something else. Kept separate from `pool` on purpose: a foil drawn from a situation another
    thread answers would state that thread's answer in a conversation that is not its own, and
    the case author would have two correct messages to choose between."""

    used: int = 0

    def take(self, topic: str | None = None) -> Situation:
        for index in range(self.used, len(self.pool)):
            if topic is None or self.pool[index].topic == topic:
                self.pool[self.used], self.pool[index] = self.pool[index], self.pool[self.used]
                self.used += 1
                return self.pool[self.used - 1]
        raise Exhausted(
            f"no unused situation left{'' if topic is None else f' for topic {topic!r}'}. "
            "Handing one out twice would put the same fact in two threads, which is the "
            "cross-thread ambiguity of R-M2-051"
        )

    #: The second Morgan Reid and Dana Okafor's new address exist for F14's identity traps.
    #: They used to be drawn into ordinary conversations too, so one display name appeared at
    #: two addresses in twenty unrelated threads with nothing saying which case it was - an
    #: identity rule that is not learnable anywhere it is not being tested.
    reserved: tuple[str, ...] = (SAME_NAME_PAIR[1], CHANGED_ADDRESS_PAIR[1])

    def cast(self, count: int, *, require: tuple[str, ...] = ()) -> tuple[str, ...]:
        """At least `count` distinct people, with `require` included first.

        **At least, and drawn.** R-M2-070. Every builder asked for a fixed number and got it,
        so the number of people on a conversation was constant inside every family - four for
        F1, five for F2, six for F3 - and the count alone named the family in nine threads of
        the corpus. A builder still gets everyone it indexes; what varies is how many others
        are also on the thread, which is what varies in real mail.
        """
        chosen = list(require)
        others = [
            one.key for one in PEOPLE
            if one.key not in chosen and one.key not in self.reserved
        ]
        self.rng.shuffle(others)
        room = len(chosen) + len(others)
        want = min(count + self.shape.randrange(0, 2), room)
        chosen.extend(others[: max(0, want - len(chosen))])
        return tuple(chosen)


def _before(
    ctx: Context, target: int, length: int, avoid: tuple[int, ...] = ()
) -> int:
    """A drawn position earlier in the conversation than `target`.

    Earlier, because a decoy dated after the evidence and marked as firmly is not a decoy - it
    reads as superseding the answer, and an audit found six F3 threads of seven and both F11
    threads in exactly that state. Drawn, because fixed offsets made the evidence position
    recoverable by arithmetic.
    """
    taken = {target, *avoid}
    room = [one for one in range(1, max(2, target)) if one not in taken]
    if not room:
        # Nothing fits before `target` - the anchor is the thread's second message. The caller
        # is told, by the position it gets back, that its decoy now sits *after* whatever it
        # was meant to precede, and F3 hedges it for exactly that reason. What the fallback
        # must not do is land on a position the caller reserved: `avoid` carries the evidence
        # position, and dropping it here is what let a trap overwrite the answer at `t0041`.
        room = [one for one in range(1, length) if one not in taken]
    if not room:
        raise ValueError(
            f"no position in a thread of {length} is free of {sorted(taken)}"
        )
    return room[ctx.shape.randrange(len(room))]


def quoted_fragment(situation: Situation) -> str:
    """The stretch of the evidence sentence a person would actually put in quotes.

    R-M2-073. F12's construction query was `situation.formal_true` - the evidence sentence
    complete and verbatim, answer value included. Two things follow from that and both are
    wrong. The rule that says the exact match outranks the paraphrase is then asking whether a
    sentence outranks its neighbours on *itself*, which no corpus can fail. And the query hands
    over the value the case is asking for, so anyone reading it has the answer without
    retrieving anything.

    The fragment is the longest run of the sentence that survives deleting the answer, so it is
    still present in the evidence word for word - which is what F12's exact-match mechanism
    needs - and contains none of the declared values. Deterministic: no RNG, so this does not
    move the shape stream.
    """
    text = situation.formal_true
    for value in sorted(
        {situation.answer, situation.wrong, situation.older} - {""}, key=len, reverse=True
    ):
        text = text.replace(value, "\x00")
    runs = [one.strip(" .,;:") for one in text.split("\x00")]
    best = max(runs, key=lambda one: (len(one.split()), len(one)))
    if len(best.split()) < 3:
        raise ValueError(
            f"situation {situation.key!r} leaves no quotable run once its values are removed: "
            f"{runs!r}. F12 cannot be built on it"
        )
    return best


def _other_subject(situation: Situation, ctx: Context) -> str:
    """A different phrasing of the same matter, for a sibling conversation.

    Sibling threads used to be distinguished by a suffix - " - costing", " - my copy" - and
    each of those suffixes named the family and the half. The topic's subject bank lets two
    conversations about one matter differ without either saying what it is.
    """
    from .situations import BY_TOPIC
    from .world import BY_ENTITY

    entity = BY_ENTITY[situation.entity]
    options = [
        one.format(formal=entity.formal, plain=entity.plain)
        for one in BY_TOPIC[situation.topic].subject.split("|")
    ]
    others = [one for one in options if one != situation.subject] or options
    return others[ctx.rng.randrange(len(others))]


def sweep_position(length: int, fraction: int) -> int:
    return min(length - 1, max(0, round(length * fraction / 100)))


def _filler_line(
    situation: Situation, ctx: Context, cast: tuple[str, ...],
    avoid: frozenset[str] = frozenset(),
    forbid: tuple[str, ...] = (),
    force: str | None = None,
    barred: tuple[str, ...] = (),
) -> Line:
    who = cast[ctx.rng.randrange(len(cast))]
    others = tuple(one for one in cast if one != who) or cast
    return Line(
        "filler",
        chatter.filler(
            situation, ctx.rng, who, others, ctx.foil_pool, avoid, forbid, force, barred
        ),
        who,
        gap_hours=ctx.shape.randrange(2, 60),
    )


def _slots(situation: Situation, **extra: object) -> dict[str, object]:
    entity = BY_ENTITY[situation.entity]
    return {
        "fact": situation.formal_true,
        "value": situation.answer,
        "formal": entity.formal,
        "plain": entity.plain,
        "reason": situation.reason,
        "plain_fact": situation.plain_decoy,
        "token": "",
        "on": "",
        "event": "",
        "name": "",
        "left": "",
        "right": "",
        "left_team": "",
        "right_team": "",
        "who": "",
        "number": 1,
        **extra,
    }


def avoid_for(situation: Situation, families: tuple[str, ...] = ()) -> frozenset[str]:
    """The question's content words, for conversations where the frame must not contain them."""
    from .world import content_words

    return content_words(situation.plain_question)


def say(ctx: Context, kind: str, situation: Situation, **extra: object) -> str:
    """A decisive sentence, framed exactly the way every other message in the corpus is framed.

    Roles used to carry their own wording - `Settled, and this is the version to quote` on F5's
    confirmation, `and has been since this morning` on F17's reversal - and each of those was
    unique in the corpus, so a five-gram selected the answer in twenty of twenty evidence-bearing
    threads. The phrasings now come from `voice.CORES`, which ordinary traffic draws from too.
    """
    avoid = extra.pop("avoid", frozenset())
    tentative = bool(extra.pop("tentative", False))
    assert isinstance(avoid, frozenset)
    return voice.say(kind, ctx.rng, avoid, tentative, **_slots(situation, **extra))


def scaffold(
    situation: Situation, length: int, ctx: Context, cast: tuple[str, ...],
    avoid: frozenset[str] = frozenset(),
    forbid: tuple[str, ...] = (),
) -> list[Line]:
    """A conversation of `length` on-topic messages carrying no decisive content.

    Position 0 opens the matter without answering it, so the thread reads as a conversation
    someone started rather than a pile of replies to nothing.
    """
    entity = BY_ENTITY[situation.entity]
    opener = Line(
        "filler",
        voice.compose(
            f"Starting a thread on {entity.formal} so this stops being decided in corridors. "
            f"{situation.reason}",
            ctx.rng,
            avoid,
        ),
        cast[0],
        gap_hours=24,
    )
    chatter.assert_no_value_leak(opener.text, situation)
    return [opener] + [
        _filler_line(situation, ctx, cast, avoid, forbid) for _ in range(length - 1)
    ]


def place(lines: list[Line], position: int, line: Line) -> None:
    """Write `line` at `position`, refusing the two placements that silently break a case.

    The second refusal is the repair for the F3 defect the gate profile reproduced at `t0041`:
    a distractor drawn without excluding the evidence position overwrote the answer, and the
    thread shipped with a declared `evidence_at` and no evidence at it. That failure is
    invisible at the call site - `place` had done exactly what it was told - and only a
    family-specific coverage rule caught it, on the one family that happens to have such a
    rule. Refusing here makes it a generation-time error in every family instead, whether or
    not that family's rule would have looked.

    A builder that deliberately rewrites a planted answer (the `_redraw_*` closures) assigns
    into `lines` directly and is unaffected.
    """
    if not 0 <= position < len(lines):
        raise ValueError(f"position {position} outside a thread of {len(lines)}")
    if position == 0:
        raise ValueError(
            "position 0 is the thread opener. Putting evidence there makes the sweep's lowest "
            "fraction structurally different from the other six"
        )
    if lines[position].role in EVIDENCE_ROLES and line.role not in EVIDENCE_ROLES:
        raise ValueError(
            f"position {position} already holds a {lines[position].role!r} message and a "
            f"{line.role!r} would overwrite it. A thread whose declared answer position holds "
            "a distractor has no answer; draw the distractor somewhere else"
        )
    lines[position] = line


def _ranks_ok(lines: list[Line], query: str, *, above: int, below: int) -> bool:
    bodies = [one.text for one in lines]
    return lexical.rank_of(bodies, query, above) < lexical.rank_of(bodies, query, below)


def _assert_ranks(
    lines: list[Line], query: str, *, above: int, below: int, why: str
) -> None:
    """Fail generation unless `above` outscores `below` on a proxy query.

    The proxy is written by the generator from the situation's own vocabulary. It is not the
    case author's query, which this code must never see, and the check is a statement about the
    constructed text only.
    """
    bodies = [one.text for one in lines]
    high = lexical.rank_of(bodies, query, above)
    low = lexical.rank_of(bodies, query, below)
    if not high < low:
        raise AssertionError(
            f"{why}: the message at {above} ranks {high} and the one at {below} ranks {low} on "
            f"the construction query {query!r}. The family is registered on that relationship "
            "holding, so a corpus where it does not hold cannot host the family"
        )


def unnamed_by(cast: tuple[str, ...], situation: Situation) -> tuple[str, ...]:
    """Cast members whose display name is not one of this situation's values.

    The `approval` topic's answer *is* a person, so a hearsay message about the participant who
    happens to be that person puts the answer in a distractor. The gate profile found it.
    """
    values = (situation.answer, situation.wrong, situation.older)
    return tuple(one for one in cast if BY_KEY[one].display not in values) or cast


def redraw_until_ranked(
    ctx: Context,
    lines: list[Line],
    query: str,
    *,
    above: int,
    below: int,
    redraw: "Callable[[], None]",
    why: str,
    tries: int = 40,
) -> None:
    """Redraw the phrasings until the family's registered rank relationship holds.

    The relationship is the family - F11's trap has to out-score its own evidence, F17's
    reinforcements have to out-score the reversal - and now that every sentence is drawn from a
    shared bank, whether a particular draw satisfies it varies. Refusing to generate on the
    first bad draw is right in the sense that the corpus would be wrong; refusing on *every*
    draw is wrong, because the shape is achievable and the generator simply has to keep
    looking. It raises only when forty draws have failed, which means the family cannot be
    built from these phrasings rather than that this one was unlucky.
    """
    for _ in range(tries):
        if _ranks_ok(lines, query, above=above, below=below):
            return
        redraw()
    _assert_ranks(lines, query, above=above, below=below, why=why)


def redraw_until_top(
    ctx: Context,
    lines: list[Line],
    query: str,
    *,
    winner: int,
    redraw: "Callable[[], None]",
    why: str,
    tries: int = 60,
) -> None:
    """Redraw until `winner` is the **top** hit in its own thread, not merely above one rival.

    R-M2-067. F11 was built to the weaker relationship - the trap outranks its own evidence -
    and one of its two instances shipped with the trap at rank 5, behind four ordinary filler
    messages. The family is registered to show that a system escalating only on weak lexical
    hits does not escalate here, and that claim is about the best hit in the conversation, not
    about a pair. A trap sitting fifth is a thread whose top hit is filler, which tests the
    opposite of what the family registers.
    """
    for _ in range(tries):
        bodies = [one.text for one in lines]
        if lexical.rank_of(bodies, query, winner) == 1:
            return
        redraw()
    bodies = [one.text for one in lines]
    rank = lexical.rank_of(bodies, query, winner)
    raise ValueError(
        f"{why}: position {winner} ranks {rank} of {len(bodies)} on the construction query "
        f"after {tries} redraws, so this family cannot be built from these phrasings"
    )


def spread(
    ctx: Context,
    anchors: list[Line],
    filler_of: "Callable[[], Line]",
    *,
    lead: tuple[int, int] = (0, 4),
    between: tuple[int, int] = (0, 2),
) -> tuple[list[Line], list[int]]:
    """Lay `anchors` out in order with a drawn number of ordinary messages around them.

    R-M2-072. A builder that writes its conversation as a literal list puts every planted role
    at the same index in every instance it makes: F14's answer was at 7 in all eight of its
    conversations and F2's at 2, 4 and 6 in all ten of theirs, so the *whole* role-position map
    was one tuple and "index 7 of an F14-shaped thread" named the answer with no query. §4.7
    asks a family to draw its positions from the §4.4 grid, and this is how the hand-written
    builders do it.

    Returns the lines and, in order, the index each anchor ended up at. The first anchor can
    land at 0, so a builder whose first anchor is planted rather than filler passes a `lead`
    that cannot draw zero.
    """
    lines: list[Line] = []
    at: list[int] = []
    for index, line in enumerate(anchors):
        low, high = lead if index == 0 else between
        for _ in range(ctx.shape.randrange(low, high)):
            lines.append(filler_of())
        at.append(len(lines))
        lines.append(line)
    return lines, at


def _hearsay(ctx: Context, situation: Situation, about: str, claim: str, who: str,
             gap: int) -> Line:
    """A second-hand report, naming the person it is about by display name.

    The old generator emitted the literal string `participant 0` here and never substituted it,
    so all eight F6 threads named nobody and the family's scoring rule - cite X's own message -
    could not be applied (R-M2-052).
    """
    return Line(
        "hearsay",
        say(ctx, "hearsay", situation, who=BY_KEY[about].display, value=claim.rstrip(".")),
        who,
        gap_hours=gap,
        is_distractor=True,
    )


# --------------------------------------------------------------------------------------- F1

def build_f1(ctx: Context, count: int) -> list[ThreadDraft]:
    """A unique business identifier in exactly one message, with near collisions elsewhere.

    The near collisions are in *other* threads and are real identifiers of real other things,
    so the family measures precise matching rather than the presence of a rare string.
    """
    # Identifiers and their near collisions are minted together and checked against each
    # other. The first draft derived a collision by reversing the next thread's digits, which
    # at the gate size produced a "collision" that *was* another thread's real identifier, so
    # one identifier occurred in two messages. The coverage rule caught it.
    out: list[ThreadDraft] = []
    stems = ctx.rng.sample(range(1000, 4999), count)
    identifiers = [f"A{one}" for one in stems]
    collisions: list[str] = []
    for one in identifiers:
        digits = one[1:]
        near = [
            "A" + digits[:left] + digits[left + 1] + digits[left] + digits[left + 2:]
            for left in range(len(digits) - 1)
        ] + [
            "A" + digits[:at] + str(swap) + digits[at + 1:]
            for at in range(1, len(digits)) for swap in range(10)
        ]
        # A9213 for A9231 is EP §4.3's example, so transpositions come first; a repdigit like
        # A8888 has no distinct transposition at all, which the gate profile found, so a
        # single-digit substitution is the fallback.
        chosen = next(
            (one_near for one_near in near
             if one_near != one and one_near not in identifiers and one_near not in collisions),
            "",
        )
        if not chosen:  # pragma: no cover - fifty candidates cannot all collide
            raise Exhausted(f"no distinct near collision for {one}")
        collisions.append(chosen)
    for index in range(count):
        situation = ctx.take()
        entity = BY_ENTITY[situation.entity]
        cast = ctx.cast(4)
        token = identifiers[index]
        # **The near collision belongs to the *next* thread**, not this one. EP §4.3 places the
        # near-collision tokens "in other threads"; the first version put each beside its own
        # answer in a message that said the reference belonged to a different job, so the
        # distractor disqualified itself and the family measured nothing.
        neighbour = identifiers[(index + 1) % count]
        mine = collisions[index]
        lines = scaffold(situation, ctx.shape.randrange(9, 15), ctx, cast)
        target = ctx.shape.randrange(2, len(lines) - 1)
        place(lines, target, Line(
            "evidence",
            say(ctx, "invoice", situation, token=token), cast[1], gap_hours=18,
        ))
        # **Which side of the evidence the second reference is raised on is drawn** (R-M2-072,
        # 2026-09-16). It always sat *before*, so the evidence was the newest message in the
        # thread carrying an identifier and "the latest reference anyone quoted" answered the
        # family with no query: F1 scored 2 of 2 against a query-free solver. Someone raising
        # the other job's number later in the same conversation is ordinary mail, and the
        # family is untouched - the question still names one identifier exactly and exact
        # matching still resolves it.
        after = ctx.shape.random() < 0.5
        other_at = target + 1 if after else target - 1
        if other_at >= len(lines) - 1 or other_at < 2:
            other_at = target - 1 if after else target + 1
        other_at = min(max(other_at, 2), len(lines) - 1)
        place(lines, other_at, Line(
            "near_duplicate",
            say(ctx, "invoice", situation, token=mine), cast[2], gap_hours=9,
            is_distractor=True,
        ))
        out.append(ThreadDraft(
            family="F1", subject=situation.subject,
            situation_key=situation.key, lines=lines,
            start_offset_days=40 + index * 7, participants=cast,
            answer_override=token,
            facts={"identifier": token, "near_collision": neighbour,
                   "same_thread_neighbour": mine},
            answer_note=(
                f"The message quoting invoice {token}. {neighbour} is a different job in "
                f"another conversation, and {mine} is a second reference raised in this one; "
                "neither is the answer."
            ),
        ))
    return out


# --------------------------------------------------------------------------------------- F2

def build_f2(ctx: Context, count: int) -> list[ThreadDraft]:
    """"What did X send between these dates?" with EP §1.2.2's 48-hour margins honoured.

    Three qualifying messages sit at least three days inside each edge, the same sender has a
    message at least three days outside each edge, and other senders write inside the window.
    Margins are why `day_offsets` exists: accumulating gaps to land near an edge is how a
    stated 48-hour margin quietly becomes a 40-hour one.
    """
    out: list[ThreadDraft] = []
    for index in range(count):
        situation = ctx.take()
        entity = BY_ENTITY[situation.entity]
        cast = ctx.cast(5)
        subject_person, other_a, other_b = cast[0], cast[1], cast[2]
        window_open = 60 + index * 21
        window_close = window_open + 14
        # **Nothing in the prose says which side of the window a message is on.** The first
        # version had the qualifying messages announce themselves - "First of my three",
        # "now the window has closed" - so the family was solved by reading rather than by
        # filtering on a date, which is the one thing it is registered to test.
        plan: list[tuple[int, str, str, str, bool]] = [
            (window_open - 6, other_a, "filler",
             say(ctx, "assert", situation, fact=f"{entity.formal} is back on the agenda."),
             False),
            # R-M2-073. The superseded value goes *before* the window and the merely wrong
            # one after it. The two used to be the other way round, which put the value the
            # key calls `older_value` on the thread's chronologically newest message - a
            # conversation whose most recent word is the superseded position reads as one
            # where the position was never superseded.
            (window_open - 4, subject_person, "near_duplicate",
             say(ctx, "assert", situation, fact=situation.formal_older, tentative=True), True),
            (window_open + 3, subject_person, "evidence",
             say(ctx, "assert", situation), False),
            (window_open + 5, other_b, "filler",
             chatter.filler(situation, ctx.rng, other_b, (other_a,), ctx.foil_pool), False),
            (window_open + 7, subject_person, "evidence",
             say(ctx, "assert", situation,
                 fact=f"The reason behind the {entity.formal} position is that "
                      f"{situation.reason[0].lower()}{situation.reason[1:]}"), False),
            (window_open + 9, other_a, "filler",
             chatter.filler(situation, ctx.rng, other_a, (other_b,), ctx.foil_pool), False),
            (window_open + 11, subject_person, "evidence",
             say(ctx, "nochange", situation), False),
            (window_close + 4, subject_person, "near_duplicate",
             say(ctx, "assert", situation, fact=situation.formal_wrong, tentative=True), True),
        ]
        # R-M2-072. Ordinary traffic drawn in around the fixed skeleton, so the planted roles
        # do not sit at the same indices in every instance. All ten of these conversations used
        # to put the qualifying messages at 2, 4 and 6 and the two out-of-window decoys at 1
        # and 7. The inserted messages are from other senders, so the §1.2.2 margin check -
        # which reads the subject person's messages only - is untouched, and every day is
        # distinct so the order is total.
        others = (cast[3], cast[4])
        before = [
            (window_open - 6 - 3 * (lead - one), others[one % len(others)], "filler",
             chatter.filler(situation, ctx.rng, others[one % len(others)], cast, ctx.foil_pool),
             False)
            for lead in (ctx.shape.randrange(0, 4),)
            for one in range(lead)
        ]
        room = [window_open + 4, window_open + 6, window_open + 8, window_open + 10,
                window_open + 12]
        inside = [
            (day, others[index % len(others)], "filler",
             chatter.filler(situation, ctx.rng, others[index % len(others)], cast,
                            ctx.foil_pool),
             False)
            for index, day in enumerate(
                sorted(ctx.shape.sample(room, ctx.shape.randrange(0, 4)))
            )
        ]
        plan = sorted(before + plan + inside, key=lambda row: row[0])
        lines = [
            Line(role, text, who, gap_hours=24, is_distractor=distractor)
            for _, who, role, text, distractor in plan
        ]
        out.append(ThreadDraft(
            family="F2", subject=situation.subject,
            situation_key=situation.key, lines=lines,
            start_offset_days=plan[0][0], participants=cast,
            day_offsets=tuple(day for day, _, _, _, _ in plan),
            facts={
                # Dates, not offsets. The first version recorded day numbers against an epoch
                # the manifest does not state, and a reader resolving them against the corpus's
                # own earliest message placed the first qualifying message outside its own
                # declared window.
                "window_open": (EPOCH + dt.timedelta(days=window_open)).isoformat(),
                "window_close": (EPOCH + dt.timedelta(days=window_close)).isoformat(),
                "window_open_day": str(window_open),
                "window_close_day": str(window_close),
                "subject_person": subject_person,
                # R-M2-073. Where the superseded rendering was planted. Declared rather than
                # inferred, because every rendering of this situation names the old figure as
                # its own reference point and no text rule can tell the two uses apart.
                "older_at": str(
                    next(index for index, row in enumerate(plan)
                         if row[0] == window_open - 4)
                ),
            },
            answer_override="",
            answer_note=(
                f"All three messages from {BY_KEY[subject_person].display} between day "
                f"{window_open} and day {window_close} after the corpus epoch, and no others. "
                "The same sender also writes four days before the window opens and four days "
                "after it closes; other senders write inside it. all_of."
            ),
        ))
    return out


# --------------------------------------------------------------------------------------- F3

def build_f3(ctx: Context, count: int) -> list[ThreadDraft]:
    """Twelve templates at all seven sweep fractions, one long thread per case.

    Each of the eighty-four threads gets its **own** situation, so no two sweep positions carry
    the same sentence. The old corpus planted twelve facts across twenty-four evidence messages
    and its coverage report multiplied thread capacity by seven to claim 567 (R-M2-045, -049).
    """
    from .situations import TOPICS

    # Interleaved so that a small profile still spans all seven fractions: case n takes
    # fraction n mod 7 and template n div 7, which at the registered 84 is every template at
    # every fraction exactly once, and at 7 is one template at all seven positions.
    out: list[ThreadDraft] = []
    for made in range(count):
        fraction = SWEEP_FRACTIONS[made % len(SWEEP_FRACTIONS)]
        topic = TOPICS[(made // len(SWEEP_FRACTIONS)) % len(TOPICS)]
        if True:
            situation = ctx.take(topic.key)
            entity = BY_ENTITY[situation.entity]
            cast = ctx.cast(6)
            lines = scaffold(situation, ctx.long_length, ctx, cast)
            target = sweep_position(ctx.long_length, fraction)
            if target == 0:
                target = 1
            place(lines, target, Line(
                "evidence", say(ctx, "assert", situation), cast[1], gap_hours=14,
            ))
            # **Drawn offsets, and the near miss sits before the evidence.** Two findings from
            # one audit. The distractors used to sit at exactly +7, +17 and +29 from the target
            # in every thread, so the evidence position was recoverable by arithmetic from any
            # one of them - precision 1.000 at ninety times the base rate, on the family whose
            # whole purpose is to measure position-independence. And the near miss was the
            # evidence sentence with a different number, dated *later* and marked as firmly: in
            # six threads of seven the text read as superseding the answer, whatever the key
            # said. EP §4.6 defines a same-thread near miss as proposal against decision, so
            # that is what it is now.
            room = [one for one in range(1, ctx.long_length) if one != target]
            spread = sorted(ctx.shape.sample(room, 3))
            earlier = [one for one in spread if one < target]
            near_miss_at = earlier[-1] if earlier else max(1, target - 1)
            place(lines, near_miss_at, Line(
                "paraphrase_decoy",
                say(ctx, "propose", situation, value=situation.wrong),
                cast[2], gap_hours=11, is_distractor=True))
            # The trap sits before the evidence too. It is written in the query's own words, so
            # a later one reads as superseding the answer: an audit found it dated after the
            # evidence in five threads of seven and a careful reader with a live case for the
            # wrong value.
            trap_at = _before(ctx, near_miss_at, ctx.long_length, avoid=(target,))
            # At the lowest sweep fractions the evidence is the second message and nothing can
            # precede it, so the trap has to sit after the answer. It is hedged when it does,
            # from a bank ordinary traffic draws on too, because an unhedged later
            # contradiction in the query's own words reads as superseding the answer.
            trap_text = voice.compose(situation.plain_decoy, ctx.rng)
            if trap_at > target:
                trap_text = (
                    f"{trap_text} {voice.HEDGES[ctx.rng.randrange(len(voice.HEDGES))]}"
                )
            place(lines, trap_at, Line(
                "trap_decoy", trap_text, cast[4], gap_hours=8, is_distractor=True))
            hearsay_at = next(
                (one for one in spread if one not in (near_miss_at, trap_at, target)),
                max(1, (target + 5) % ctx.long_length or 1),
            )
            place(lines, hearsay_at, _hearsay(
                ctx, situation, unnamed_by(cast, situation)[0],
                situation.wrong, unnamed_by(cast, situation)[-1], 13))
            out.append(ThreadDraft(
                family="F3", subject=situation.subject, situation_key=situation.key,
                lines=lines, start_offset_days=5 + made * 3, participants=cast,
                paraphrase_of_fact=situation.plain_question,
                facts={"fraction": str(fraction), "evidence_at": str(target)},
                answer_note=(
                    f"Position {target} of {ctx.long_length} (fraction {fraction}). The answer "
                    f"is {situation.answer!r}. Three distractors: a same-thread near miss in "
                    "the evidence's own vocabulary, a hearsay report of a different value, and "
                    "a confident wrong statement in the colloquial register."
                ),
            ))
    return out


# --------------------------------------------------------------------------------------- F4

def build_f4(ctx: Context, count: int) -> list[ThreadDraft]:
    """Query and evidence share no content word; the decoy shares the query's words and lies."""
    out: list[ThreadDraft] = []
    for index in range(count):
        situation = ctx.take()
        entity = BY_ENTITY[situation.entity]
        cast = ctx.cast(5)
        length = ctx.shape.randrange(14, 30)
        avoid = avoid_for(situation)
        lines = scaffold(situation, length, ctx, cast, avoid)
        target = max(3, sweep_position(length, SWEEP_FRACTIONS[(index * 3 + 2) % len(SWEEP_FRACTIONS)]))
        place(lines, target, Line(
            "evidence", say(ctx, "assert", situation, avoid=avoid), cast[1], gap_hours=16))
        decoy_at = _before(ctx, target, length)
        place(lines, decoy_at, Line(
            "trap_decoy", voice.compose(situation.plain_decoy, ctx.rng), cast[2],
            gap_hours=7, is_distractor=True))
        bridge_at = next(
            (one for one in range(1, length) if one not in (target, decoy_at)), 1
        )
        place(lines, bridge_at, Line(
            "filler", chatter.alias_bridge(situation, ctx.rng), cast[3], gap_hours=5))
        def _redraw_f4() -> None:
            lines[target] = Line(
                "evidence", say(ctx, "assert", situation, avoid=avoid), cast[1], gap_hours=16)
            lines[decoy_at] = Line(
                "trap_decoy", voice.compose(situation.plain_decoy, ctx.rng), cast[2],
                gap_hours=7, is_distractor=True)

        redraw_until_ranked(
            ctx, lines, situation.plain_question, above=decoy_at, below=target,
            redraw=_redraw_f4,
            why="F4's decoy must be the lexical hit and the evidence must not be",
        )
        out.append(ThreadDraft(
            family="F4", subject=situation.subject, situation_key=situation.key, lines=lines,
            start_offset_days=90 + index * 5, participants=cast,
            paraphrase_of_fact=situation.plain_question,
            facts={"evidence_at": str(target), "decoy_at": str(decoy_at)},
            answer_note=(
                f"Answer {situation.answer!r}, at position {target}. The question is written "
                "in the colloquial register and shares no content word with the evidence "
                f"(measured jaccard 0.00). The message at {decoy_at} is in the question's own "
                "register and is false."
            ),
        ))
    return out


# --------------------------------------------------------------------------------------- F5

def build_f5(ctx: Context, count: int) -> list[ThreadDraft]:
    """Proposal, objection, confirmation, then a later reminder that restates the proposal.

    The reminder is the temporal decoy of EP §4.6: newer than the confirmation and weaker,
    which is only a trap if the dates actually put it later. They now do.
    """
    out: list[ThreadDraft] = []
    for index in range(count):
        situation = ctx.take()
        entity = BY_ENTITY[situation.entity]
        cast = ctx.cast(5)
        length = ctx.shape.randrange(16, 28)
        lines = scaffold(situation, length, ctx, cast)
        spots = sorted(ctx.shape.sample(range(2, length - 2), 3))
        proposal_at, objection_at, confirmation_at = spots
        # **The stale reminder is drawn from the tail of the thread, not pinned to its end**
        # (R-M2-072, 2026-09-16). At `length - 1` it was the final message in every F5 thread,
        # which is a fixed role position and is the shape signal the fifth read measured. It
        # still has to be *after* the confirmation - that is what makes it stale, and the
        # family is registered on it - so it is drawn from the span between them.
        reminder_at = ctx.shape.randrange(confirmation_at + 1, length)
        place(lines, proposal_at, Line(
            "proposal",
            say(ctx, "propose", situation, value=situation.older),
            cast[1], gap_hours=20, is_distractor=True))
        place(lines, objection_at, Line(
            "objection",
            say(ctx, "object", situation, value=situation.older),
            cast[2], gap_hours=26, is_distractor=True))
        place(lines, confirmation_at, Line(
            "confirmation",
            say(ctx, "assert", situation), cast[1], gap_hours=30))
        lines[reminder_at] = Line(
            "reminder",
            say(ctx, "remind", situation, value=situation.older),
            cast[3], gap_hours=200, is_distractor=True)
        out.append(ThreadDraft(
            family="F5", subject=situation.subject, situation_key=situation.key, lines=lines,
            start_offset_days=120 + index * 6, participants=cast,
            paraphrase_of_fact=situation.plain_question,
            facts={"confirmation_at": str(confirmation_at), "reminder_at": str(reminder_at),
                   "proposal_at": str(proposal_at)},
            answer_note=(
                f"The confirmation at {confirmation_at} carrying {situation.answer!r}. The "
                f"proposal at {proposal_at} and the reminder at {reminder_at} both carry "
                f"{situation.older!r}; the reminder is the newest message in the thread, so "
                "recency alone selects the wrong one. any_of {confirmation}; reminder-only fails."
            ),
        ))
    return out


# --------------------------------------------------------------------------------------- F6

def build_f6(ctx: Context, count: int) -> list[ThreadDraft]:
    """X's own message is the evidence; two second-hand reports about X are the traps.

    One of the reports is *right* and still not the answer, which is the sharp case: a system
    that matches on "X said" without checking authorship passes on the wrong message.
    """
    out: list[ThreadDraft] = []
    for index in range(count):
        situation = ctx.take()
        entity = BY_ENTITY[situation.entity]
        cast = ctx.cast(5)
        subject_person = unnamed_by(cast, situation)[0]
        length = ctx.shape.randrange(15, 26)
        lines = scaffold(situation, length, ctx, cast)
        target = max(4, sweep_position(length, SWEEP_FRACTIONS[(index * 3 + 5) % len(SWEEP_FRACTIONS)]))
        place(lines, target, Line(
            "authored_claim",
            say(ctx, "assert", situation), subject_person, gap_hours=18))
        wrong_at = (target + 4) % length or 2
        right_at = (target + 8) % length or 5
        reporter = next(
            one for one in unnamed_by(cast, situation) if one != subject_person
        )
        for spot, claim in ((wrong_at, situation.wrong), (right_at, situation.answer)):
            if spot in (0, target):
                spot = (spot + 1) % length or 6
            place(lines, spot, _hearsay(ctx, situation, subject_person, claim, reporter, 12))
        out.append(ThreadDraft(
            family="F6", subject=situation.subject, situation_key=situation.key, lines=lines,
            start_offset_days=150 + index * 6, participants=cast,
            facts={"author": subject_person, "evidence_at": str(target),
                   "reporter": reporter},
            answer_note=(
                f"{BY_KEY[subject_person].display}'s own message at {target}. Two second-hand "
                f"reports by {BY_KEY[reporter].display} name them: one at {wrong_at} reports "
                f"{situation.wrong!r} and one reports {situation.answer!r} correctly. The "
                "correct second-hand report is still not the answer, because the family scores "
                "authorship."
            ),
        ))
    return out


# --------------------------------------------------------------------------------------- F7

def build_f7(ctx: Context, count: int) -> list[ThreadDraft]:
    """One fact in halves, in two conversations, with two vocabulary-sharing decoy threads.

    The old corpus put a *complete* fact in each of three threads that shared a subject line,
    so the halves contradicted rather than combined (R-M2-050). Here the decision lives in one
    thread and the figure it depends on lives in the other, and neither answers alone.
    """
    out: list[ThreadDraft] = []
    for index in range(count):
        situation = ctx.take()
        entity = BY_ENTITY[situation.entity]
        cast = ctx.cast(6)
        charge = f"{ctx.rng.randrange(200, 980)}"
        decision_len = ctx.shape.randrange(10, 18)
        decision = scaffold(situation, decision_len, ctx, cast[:4])
        at = decision_len // 2
        place(decision, at, Line("evidence", say(ctx, "assert", situation), cast[1],
                                 gap_hours=22))
        # A competing assertion of the same matter, earlier: §4.6 asks every scored family for
        # at least one distractor on the answer itself, and an audit found F7's answer value
        # uncontested anywhere in scope.
        place(decision, _before(ctx, at, decision_len), Line(
            "paraphrase_decoy", say(ctx, "propose", situation, value=situation.wrong),
            cast[2], gap_hours=17, is_distractor=True))
        out.append(ThreadDraft(
            family="F7", subject=situation.subject,
            situation_key=situation.key, lines=decision,
            start_offset_days=180 + index * 9, participants=cast[:4],
            facts={"half": "decision", "evidence_at": str(at), "charge": charge},
            answer_note=(
                f"Half one of two: the decision, {situation.answer!r}, at position {at}. The "
                "figure it depends on is only in the sibling conversation. all_of."
            ),
        ))
        figure_len = ctx.shape.randrange(8, 14)
        figure = scaffold(situation, figure_len, ctx, cast[2:])
        figure_at = figure_len // 2
        place(figure, figure_at, Line(
            "evidence",
            say(ctx, "charge", situation, value=charge), cast[3], gap_hours=19))
        # R-M2-073. EP §4.3 asks every case for at least one distractor, and F7's figure half
        # carried none: the charge was uncontested in the only conversation that states it, so
        # the half was answerable by finding the single message with a number in it. The
        # competitor is a tabled figure, marked as not settled, so the case stays unambiguous.
        estimate = str(ctx.rng.randrange(200, 980))
        while estimate == charge:
            estimate = str(ctx.rng.randrange(200, 980))
        place(figure, _before(ctx, figure_at, figure_len), Line(
            "paraphrase_decoy", say(ctx, "propose", situation, value=estimate), cast[2],
            gap_hours=10, is_distractor=True))
        out.append(ThreadDraft(
            family="F7", subject=_other_subject(situation, ctx),
            situation_key=f"{situation.key}::figure", lines=figure,
            start_offset_days=182 + index * 9, participants=cast[2:],
            continues=situation.key, answer_override=charge, follows_parent=True,
            facts={"half": "figure", "evidence_at": str(figure_at), "charge": charge,
                   "tabled_estimate": estimate},
            answer_note=(
                f"Half two of two: the charge {charge!r} at position {figure_at}. Answering "
                f"the case needs this and {situation.answer!r} from the sibling."
            ),
        ))
        for which in range(2):
            # **Same topic, different entity.** EP §4.3 asks for threads that "share vocabulary
            # with 2 unrelated threads"; drawing any situation gave decoys whose only shared
            # words were filler boilerplate, and whose subject line ended in the word
            # "unrelated", which labelled all four of them.
            noise = ctx.take(situation.topic)
            noise_cast = ctx.cast(3)
            length = ctx.shape.randrange(6, 11)
            out.append(ThreadDraft(
                family="F7", subject=noise.subject,
                situation_key=f"{noise.key}::decoy{which}",
                lines=scaffold(noise, length, ctx, noise_cast),
                start_offset_days=184 + index * 9 + which, participants=noise_cast,
                cross_thread_decoy_for=situation.key, answer_override="",
                answer_note="Cross-thread decoy: same topic vocabulary, different matter.",
            ))
    return out


# --------------------------------------------------------------------------------------- F8

def _csv(situation: Situation, rows: list[tuple[str, str]]) -> str:
    """A schedule file, in the same shape every file in the corpus uses.

    **The header used to name the family.** Four CSVs in 1,709 messages carried
    `entity,measure,value,recorded` and all four were F8's covers and decoys, so the schema
    alone selected them at 427 times the base rate - and among those four, the authoritative
    copy was the one whose `prior` and `review` rows agreed, which picked it two times out of
    two from the bytes with no message and no query. One schema for every file in the corpus
    now, and the rows carry four distinct values on both sides.
    """
    return "entity,kind,count,recorded\n" + "\n".join(
        f"{BY_ENTITY[situation.entity].formal},{name},{value},2026-02-0{index + 1}"
        for index, (name, value) in enumerate(rows)
    )


def build_f8(ctx: Context, count: int) -> list[ThreadDraft]:
    """The fact is in the attachment; the covering message points at it without saying it.

    A same-named file with a different version lives in another conversation, which is EP
    §4.3's F8 decoy. The old fixtures were 44 to 77 bytes with one row (R-M2-055); these carry
    several rows so that finding the file is not the same as reading it.
    """
    out: list[ThreadDraft] = []
    for index in range(count):
        situation = ctx.take()
        entity = BY_ENTITY[situation.entity]
        cast = ctx.cast(4)
        filename = f"{entity.formal.lower().replace(' ', '-')}-schedule-v3.csv"
        # Four distinct values on both sides, in an order drawn per pair, so neither file is
        # identifiable from its own contents.
        labels = ["prior", "proposed", "agreed", "review"]
        spare_true = mint_values(
            situation.value_kind, ctx.rng, 2,
            avoid=(situation.answer, situation.wrong, situation.older),
        )
        true_rows = [
            ("prior", situation.older), ("proposed", spare_true[0]),
            ("agreed", situation.answer), ("review", spare_true[1]),
        ]
        del labels
        # Four distinct values in both files. The decoy used to repeat its `agreed` value in
        # three of four rows while the authentic file's was unique to its row, so the corrupt
        # copy was identifiable from its own contents without comparing the two.
        spare = mint_values(
            situation.value_kind, ctx.rng, 2,
            avoid=(situation.answer, situation.wrong, situation.older),
        )
        wrong_rows = [
            ("prior", situation.older), ("proposed", spare[0]),
            ("agreed", situation.wrong), ("review", spare[1]),
        ]
        length = ctx.shape.randrange(10, 18)
        lines = scaffold(situation, length, ctx, cast)
        at = length // 2
        place(lines, at, Line(
            "attachment_cover",
            voice.compose(
                f"{voice.core('attach', ctx.rng, tentative=False, **_slots(situation))} The agreed row is the "
                "one that matters.",
                ctx.rng,
            ),
            cast[1], gap_hours=21,
            attachments=(Attachment(filename=filename, media_type="text/csv",
                                    content=_csv(situation, true_rows), carries_the_fact=True),),
        ))
        out.append(ThreadDraft(
            family="F8", subject=situation.subject, situation_key=situation.key,
            lines=lines, start_offset_days=210 + index * 8, participants=cast,
            # **The answer is the file, not the figure inside it.** EP §4.3 defines an F8 pass
            # as "retrieving the carrying message + signalling the attachment; content
            # extraction is scored only if MailWeave claims it", and MailWeave does not claim
            # it: `content/mime.AttachmentRow` is metadata only and
            # `users.messages.attachments.get` is off the release surface (ADV-207). Declaring
            # the CSV cell as the answer made the whole family unanswerable through the product
            # surface, which an independent case author found when the cases would not verify.
            answer_override=filename,
            facts={"filename": filename, "cover_at": str(at),
                   "value_in_attachment": situation.answer,
                   "extraction_claimed": "no"},
            answer_note=(
                f"The covering message at {at}, and the attachment {filename} named on it. "
                "That is the whole pass: EP §4.3 scores F8 as retrieving the carrying message "
                "and signalling the attachment, and scores content extraction **only if "
                "MailWeave claims it**, which it does not - `AttachmentRow` is metadata only "
                "and `users.messages.attachments.get` is off the release surface (ADV-207).\n\n"
                f"The decisive figure {situation.answer!r} is in the file's `agreed` row and in "
                "no message body, so a system that answers with the figure has done something "
                "the product does not claim and should be recorded as such rather than scored. "
                "A file of the same name, with different rows, is attached in the sibling "
                "conversation; the covering message there hedges its own currency, which is "
                "what separates them."
            ),
        ))
        sibling_cast = ctx.cast(3)
        sibling_len = ctx.shape.randrange(6, 10)
        sibling = scaffold(situation, sibling_len, ctx, sibling_cast)
        sibling_at = sibling_len // 2
        place(sibling, sibling_at, Line(
            "attachment_wrong_version",
            voice.compose(
                f"{voice.core('attach', ctx.rng, tentative=False, **_slots(situation))} "
                + voice.core("stale", ctx.rng, tentative=False, **_slots(situation)),
                ctx.rng,
            ),
            sibling_cast[1], gap_hours=15, is_distractor=True,
            attachments=(Attachment(filename=filename, media_type="text/csv",
                                    content=_csv(situation, wrong_rows), carries_the_fact=False),),
        ))
        out.append(ThreadDraft(
            family="F8", subject=_other_subject(situation, ctx),
            situation_key=f"{situation.key}::wrongversion", lines=sibling,
            # Half the pairs put the stale copy *after* the authoritative one. It was always
            # later before, so "take the newer file" solved the family without reading either.
            # Half the pairs put the stale copy *after* the authoritative one and half before.
            # It was always later, then always earlier; either way "take the newer file" or
            # "take the older file" solved the family without opening either.
            start_offset_days=(216 if index % 2 else 204) + index * 8,
            participants=sibling_cast,
            continues=situation.key,
            # **The decoy conversation has no answer.** It used to inherit the situation's
            # default, so the manifest declared the authentic figure as the truth of the
            # thread that does not contain it - a case author joining on `answer` would have
            # pointed a case at the corrupt copy and scored the right figure as retrieved
            # from the wrong file.
            answer_override="",
            facts={"filename": filename, "cover_at": str(sibling_at),
                   "value_in_attachment": situation.wrong,
                   "is_the_wrong_version": "yes"},
            answer_note=(
                f"Decoy: {filename} again, with {situation.wrong!r} in the `agreed` row "
                f"instead of {situation.answer!r}. This conversation answers nothing; it "
                "exists so that finding a file of the right name is not the same as finding "
                "the right file."
            ),
        ))
    return out


# -------------------------------------------------------------------------------------- F10

def build_f10(ctx: Context, count: int) -> list[ThreadDraft]:
    """A decision proposed, argued about, and never taken. The answer is "not found".

    EP §3.1 names the failure this guards: a system that games false-not-found by never saying
    not-found. So the thread has to look exactly like an F5 thread up to the point where the
    confirmation would be, and then not have one. `answer_note` states the absence, and the
    coverage rule checks it, because a confirmation accidentally planted here turns a control
    into a case with an answer.
    """
    out: list[ThreadDraft] = []
    for index in range(count):
        situation = ctx.take()
        entity = BY_ENTITY[situation.entity]
        cast = ctx.cast(4)
        length = ctx.shape.randrange(12, 22)
        lines = scaffold(situation, length, ctx, cast)
        proposal_at = ctx.shape.randrange(2, max(3, length // 2))
        objection_at = min(length - 3, proposal_at + ctx.shape.randrange(2, 5))
        place(lines, proposal_at, Line(
            "proposal",
            say(ctx, "propose", situation, value=situation.wrong),
            cast[1], gap_hours=20, is_distractor=True))
        place(lines, objection_at, Line(
            "objection",
            say(ctx, "object", situation, value=situation.wrong),
            cast[2], gap_hours=28, is_distractor=True))
        lines[length - 1] = Line(
            "reminder",
            say(ctx, "chase", situation), cast[3], gap_hours=300, is_distractor=True)
        out.append(ThreadDraft(
            family="F10", subject=situation.subject, situation_key=situation.key, lines=lines,
            start_offset_days=240 + index * 5, participants=cast,
            # **No answer, because the correct output is a grounded not-found.** Declaring the
            # situation's answer on a control invites a harness to score against a string the
            # corpus deliberately does not contain; the value that must be absent is recorded
            # separately so the coverage rule can still check the absence.
            answer_override="",
            facts={"proposal_at": str(proposal_at), "objection_at": str(objection_at),
                   "absent_claim": situation.formal_true,
                   "absent_value": situation.answer},
            answer_note=(
                "Unanswerable control. A proposal and an objection are present and nothing "
                "anywhere in the corpus settles this matter: no message states "
                f"{situation.formal_true!r} or any other agreed position on "
                f"{BY_ENTITY[situation.entity].formal}. The correct output is a grounded "
                f"not-found; the proposal at {proposal_at} is the near miss that makes a "
                "confident wrong answer available. The bare value may occur elsewhere in the "
                "corpus about other matters, which is realistic and not an answer."
            ),
        ))
    return out


# -------------------------------------------------------------------------------------- F11

def build_f11(ctx: Context, count: int) -> list[ThreadDraft]:
    """F4's shape with a decoy built to win.

    The decoy repeats the colloquial vocabulary, comes from someone senior, names the right
    people and states a false answer flatly. `_assert_ranks` requires it to outrank the
    evidence on the construction query, because a trap that does not out-score its evidence is
    not testing escalation *triggering*, which is what SCOPE §3 registers this family for.
    """
    out: list[ThreadDraft] = []
    for index in range(count):
        situation = ctx.take()
        entity = BY_ENTITY[situation.entity]
        cast = ctx.cast(5)
        length = ctx.shape.randrange(16, 30)
        avoid = avoid_for(situation)
        lines = scaffold(situation, length, ctx, cast, avoid)
        target = max(3, sweep_position(length, SWEEP_FRACTIONS[(index * 3 + 4) % len(SWEEP_FRACTIONS)]))
        place(lines, target, Line(
            "evidence", say(ctx, "assert", situation, avoid=avoid), cast[1], gap_hours=17))
        decoy_at = _before(ctx, target, length)
        witnesses = unnamed_by(cast, situation)
        place(lines, decoy_at, Line(
            "trap_decoy",
            voice.compose(
                f"{situation.plain_decoy} "
                + voice.core(
                    "concur", ctx.rng, tentative=False,
                    **_slots(situation, who=BY_KEY[witnesses[0]].display),
                ),
                ctx.rng,
            ),
            witnesses[-1], gap_hours=6, is_distractor=True))
        # R-M2-067. Three trap forms, cycled, not two. The rank the family needs is now "best
        # in the conversation", and ordinary traffic in an F11 thread legitimately names the
        # same entity - the foil pool is built that way on purpose. A loop that can only
        # lengthen the trap has no lever against a short on-topic filler, because BM25
        # normalises by length. The terse form is the lever: the colloquial decoy alone, no
        # corroboration clause. Nothing here weakens the trap's content; it varies its length.
        attempt = [0]

        def _redraw_f11() -> None:
            attempt[0] += 1
            lines[target] = Line(
                "evidence", say(ctx, "assert", situation, avoid=avoid), cast[1], gap_hours=17)
            if attempt[0] % 4 == 3:
                # **The trap answers the question in the question's own words.** This is what
                # the family says its decoy is - "the colloquial vocabulary, stated flatly" -
                # and quoting what was asked before answering it is how people write. It is
                # also the only form that reliably tops a conversation whose ordinary traffic
                # is about the same project, which is what R-M2-067 asks for. Nothing here
                # weakens the surrounding messages.
                text = voice.compose(
                    f"On {situation.plain_question.rstrip('?').lower()} - "
                    f"{situation.plain_decoy}",
                    ctx.rng,
                )
            elif attempt[0] % 4 == 0:
                text = voice.compose(situation.plain_decoy, ctx.rng)
            elif attempt[0] % 4 == 1:
                text = voice.compose(
                    f"{situation.plain_decoy} I checked with {BY_KEY[witnesses[0]].display} "
                    f"and {BY_KEY[witnesses[1]].display} and we are agreed.",
                    ctx.rng,
                )
            else:
                text = voice.compose(
                    f"{situation.plain_decoy} "
                    + voice.core(
                        "concur", ctx.rng, tentative=False,
                        **_slots(situation, who=BY_KEY[witnesses[0]].display),
                    ),
                    ctx.rng,
                )
            lines[decoy_at] = Line(
                "trap_decoy", text, witnesses[-1], gap_hours=6, is_distractor=True)

        # R-M2-067. The tail goes on **before** the rank is established, not after. A thread
        # that left this builder with the trap at rank 1 of 21 used to arrive with it at rank 2
        # of 30, because `with_tail` appended five more messages afterwards and one of them
        # outscored it. A family registered on a rank relationship has to hold that
        # relationship in the conversation it ships.
        append_tail(ctx, lines, situation, cast)
        # Not "above the evidence" - **top of the thread**. The weaker relationship let
        # `t0031` ship with the trap at rank 5 behind four fillers.
        redraw_until_top(
            ctx, lines, situation.plain_question, winner=decoy_at,
            redraw=_redraw_f11, tries=240,
            why="F11's trap must be the best lexical hit in its own conversation",
        )
        out.append(ThreadDraft(
            family="F11", subject=situation.subject, situation_key=situation.key, lines=lines,
            start_offset_days=260 + index * 5, participants=cast, tail_done=True,
            paraphrase_of_fact=situation.plain_question,
            facts={"construction_query": situation.plain_question,
                   "evidence_at": str(target), "decoy_at": str(decoy_at)},
            answer_note=(
                f"Answer {situation.answer!r} at position {target}. The message at {decoy_at} "
                "is confident, names the right people, uses the question's own vocabulary and "
                "is false. It outranks the evidence on a BM25 construction query, so a system "
                "that escalates only when lexical hits are weak will not escalate here."
            ),
        ))
    return out


# -------------------------------------------------------------------------------------- F12

def build_f12(ctx: Context, count: int) -> list[ThreadDraft]:
    """The exact lexical match is right and the paraphrase-shaped neighbour is wrong.

    The mirror of F11, and the reason both are registered: together they bound the failure in
    both directions, so neither "never escalate" nor "always escalate" is a winning strategy.
    """
    out: list[ThreadDraft] = []
    for index in range(count):
        situation = ctx.take()
        entity = BY_ENTITY[situation.entity]
        cast = ctx.cast(4)
        length = ctx.shape.randrange(12, 22)
        avoid = avoid_for(situation)
        lines = scaffold(situation, length, ctx, cast, avoid)
        target = max(3, sweep_position(length, SWEEP_FRACTIONS[(index * 3 + 1) % len(SWEEP_FRACTIONS)]))
        place(lines, target, Line(
            "evidence", say(ctx, "assert", situation, avoid=avoid), cast[1], gap_hours=16))
        neighbour_at = _before(ctx, target, length)
        place(lines, neighbour_at, Line(
            "paraphrase_decoy", voice.compose(situation.plain_decoy, ctx.rng), cast[2],
            gap_hours=9, is_distractor=True))
        def _redraw_f12() -> None:
            lines[target] = Line(
                "evidence", say(ctx, "assert", situation, avoid=avoid), cast[1], gap_hours=16)
            lines[neighbour_at] = Line(
                "paraphrase_decoy", voice.compose(situation.plain_decoy, ctx.rng), cast[2],
                gap_hours=9, is_distractor=True)

        # The tail first, for the reason given in `build_f11`: this family's registered
        # property is a rank, and a rank is a property of the whole conversation.
        append_tail(ctx, lines, situation, cast)
        # R-M2-073. The query is a fragment someone would quote, not the evidence sentence
        # entire: a sentence cannot fail to outrank its neighbours on itself.
        quoted = quoted_fragment(situation)
        redraw_until_ranked(
            ctx, lines, quoted, above=target, below=neighbour_at,
            redraw=_redraw_f12,
            why="F12's exact match must be the top lexical hit, or the control does not control",
        )
        out.append(ThreadDraft(
            family="F12", subject=situation.subject, situation_key=situation.key, lines=lines,
            start_offset_days=280 + index * 5, participants=cast, tail_done=True,
            facts={"construction_query": quoted,
                   "evidence_at": str(target), "decoy_at": str(neighbour_at)},
            answer_note=(
                f"Answer {situation.answer!r} at position {target}, reachable by exact lexical "
                f"match. The paraphrase-shaped message at {neighbour_at} is the nearest "
                "neighbour in meaning-space and is false. Escalating to semantic search here "
                "moves away from the answer."
            ),
        ))
    return out


# -------------------------------------------------------------------------------------- F13

def build_f13(ctx: Context, count: int) -> list[ThreadDraft]:
    """"What did we settle after the September review?" - ordering, not date filtering.

    Messages before the named event match the query lexically and sit inside any plausible
    date window around it. The distinction is *which side of the event* a message is on, and
    the event is named in the thread so the ordering is readable rather than assumed.
    """
    from .world import BY_EVENT, EVENTS

    out: list[ThreadDraft] = []
    for index in range(count):
        situation = ctx.take()
        event = EVENTS[index % len(EVENTS)]
        anchor = offset_of(event.key)
        cast = ctx.cast(4)
        # **No message announces which side of the event it is on**, and two of the messages
        # that restate the superseded position sit *after* the event. The first version put a
        # filler at the boundary saying "everything above this line is superseded", and the
        # three candidates labelled themselves "working position before" and "writing up what
        # the review settled" - so the family was solved by reading one sentence, and a date
        # filter left exactly one non-filler message. It is registered for ordering plus
        # reply-relationship reasoning, and now needs both: the answer is the message the
        # objector accepted, and three of its competitors share its date window.
        # **The stale restatements are hedged and the reply relation carries the answer.**
        # Two findings from one audit. A post-event restatement of the superseded value used to
        # draw a finality lead-in - one of them opened "Settled, and this is the version to
        # quote" - so the most firmly stated thing in the thread was the wrong value, dated
        # after the evidence. They are tentative now: no finality opener, and a hedge.
        #
        # And the note claimed "the reply order and the stated supersession" separated the
        # answer from its competitors while the thread was a strict chain, so reply order was
        # the position vector written twice. The evidence answers the objection and the
        # acceptance answers the evidence, which is what makes "what did the objector settle
        # on" a question about the graph rather than about the dates.
        # **The parent is named by day, not by index.** R-M2-072. Ordinary traffic is drawn in
        # around this skeleton and the rows are then sorted by date, so any index written here
        # would point at the wrong message the moment an insertion landed ahead of it. Days are
        # unique within the conversation, which makes them a stable name for a row.
        lead = ctx.shape.randrange(0, 4)
        plan: list[tuple[int, str, str, str, bool, int | None]] = [
            (anchor - 24 - one * 3, cast[one % len(cast)], "filler",
             chatter.filler(situation, ctx.rng, cast[one % len(cast)], cast, ctx.foil_pool),
             False, None)
            for one in range(lead, 0, -1)
        ]
        plan += [
            (anchor - 21, cast[0], "filler",
             chatter.filler(situation, ctx.rng, cast[0], cast[1:], ctx.foil_pool), False, None),
            (anchor - 14, cast[1], "near_duplicate",
             say(ctx, "assert", situation, fact=situation.formal_wrong), True, None),
            (anchor - 9, cast[2], "objection",
             say(ctx, "object", situation, value=situation.wrong), True, anchor - 14),
            (anchor - 3, cast[1], "near_duplicate",
             say(ctx, "reinforce", situation, fact=situation.formal_wrong), True, None),
            (anchor + 1, cast[0], "filler",
             say(ctx, "dated_event", situation, event=event.label,
                 on=event.on.strftime("%d %B %Y")), False, None),
            (anchor + 4, cast[1], "evidence", say(ctx, "assert", situation), False, anchor - 9),
            # R-M2-071. Drawn from the shared `accept` bank, not written here. The inline
            # version occurred in exactly one family, so the sentence named F13.
            (anchor + 5, cast[2], "filler",
             say(ctx, "accept", situation, event=event.label), False, anchor + 4),
            (anchor + 6, cast[3], "near_duplicate",
             say(ctx, "remind", situation, value=situation.wrong, tentative=True), True, None),
            (anchor + 9, cast[3], "filler",
             chatter.filler(situation, ctx.rng, cast[3], cast[:3], ctx.foil_pool), False, None),
            (anchor + 13, cast[2], "near_duplicate",
             say(ctx, "remind", situation, value=situation.older, tentative=True), True, None),
            (anchor + 16, cast[2], "filler",
             chatter.filler(situation, ctx.rng, cast[2], cast[:2], ctx.foil_pool), False, None),
        ]
        # R-M2-072. Ordinary traffic in the gaps, so the planted roles do not sit at the same
        # indices in every instance. `lead` alone varied the offset and left the spacing fixed,
        # and both instances drawing the same lead put the whole layout back at one tuple.
        room = [anchor - 18, anchor - 12, anchor - 6, anchor + 2, anchor + 7, anchor + 11,
                anchor + 15]
        plan += [
            (day, cast[index % len(cast)], "filler",
             chatter.filler(situation, ctx.rng, cast[index % len(cast)], cast, ctx.foil_pool),
             False, None)
            for index, day in enumerate(
                sorted(ctx.shape.sample(room, ctx.shape.randrange(0, 4)))
            )
        ]
        plan.sort(key=lambda row: row[0])
        index_of = {row[0]: index for index, row in enumerate(plan)}
        working_at = index_of[anchor - 14]
        objection_at = index_of[anchor - 9]
        restated_at = index_of[anchor - 3]
        answer_at = index_of[anchor + 4]
        acceptance_at = index_of[anchor + 5]
        pack_at = index_of[anchor + 6]
        tracker_at = index_of[anchor + 13]
        lines = [
            Line(role, text, who, gap_hours=24, is_distractor=flag,
                 replies_to=None if parent is None else index_of[parent])
            for _, who, role, text, flag, parent in plan
        ]
        out.append(ThreadDraft(
            family="F13", subject=situation.subject,
            situation_key=situation.key, lines=lines,
            start_offset_days=anchor - 21, participants=cast,
            day_offsets=tuple(day for day, _, _, _, _, _ in plan),
            facts={"event": event.key, "event_on": event.on.isoformat(),
                   "evidence_at": str(answer_at), "objection_at": str(objection_at),
                   "acceptance_at": str(acceptance_at), "older_at": str(tracker_at),
                   "stale_after_event_at": f"{pack_at},{tracker_at}"},
            answer_note=(
                f"The answer is at position {answer_at}, four days after {event.label} "
                f"({event.on.isoformat()}), carrying {situation.answer!r}.\n\n"
                f"Competitors, and what separates them. Positions {working_at} and "
                f"{restated_at} carry {situation.wrong!r} and sit before the event. Positions "
                f"{pack_at} and {tracker_at} sit **after** it and restate {situation.wrong!r} "
                f"and {situation.older!r}: they are pack and tracker entries, each hedged in "
                "its own text, and they are the reason a date filter alone does not isolate "
                "the answer - four messages survive `date > event` and three of them are "
                "wrong.\n\n"
                f"The reply graph is what settles it. The objection at {objection_at} answers "
                f"the working position at {working_at}; the answer at {answer_at} answers that "
                f"objection; and the objector's own acceptance at {acceptance_at} answers the "
                "answer. Neither the dates nor the positions carry that; the References "
                "headers do."
            ),
        ))
    return out


# -------------------------------------------------------------------------------------- F14

def build_f14(ctx: Context, count: int) -> list[ThreadDraft]:
    """Who else was on it, and what did the objector say later.

    Carries three identity traps at once: two different people who share a display name, one
    person who has changed address mid-thread, and a participant who is on every message and
    never writes. Relations are computed from the thread rather than from a stored graph, which
    is what SCOPE §5 registers the family for.
    """
    out: list[ThreadDraft] = []
    first_morgan, second_morgan = SAME_NAME_PAIR
    old_dana, new_dana = CHANGED_ADDRESS_PAIR
    for index in range(count):
        situation = ctx.take()
        cast = ctx.cast(
            6, require=(first_morgan, old_dana, new_dana, second_morgan)
        )
        bystander = cast[4]
        anchors = [
            # R-M2-071. The roster line and the address-change line below come from shared
            # banks that ordinary traffic draws on. Written inline they were F14's signature.
            Line("filler", say(ctx, "roster", situation), cast[5], gap_hours=24),
            Line("proposal", say(ctx, "propose", situation, value=situation.older),
                 old_dana, gap_hours=20, is_distractor=True),
            Line("objection", say(ctx, "object", situation, value=situation.older),
                 first_morgan, gap_hours=26, is_distractor=True),
            Line("filler",
                 chatter.filler(situation, ctx.rng, cast[5], cast[:4], ctx.foil_pool),
                 cast[5], gap_hours=18),
            Line("near_duplicate",
                 say(ctx, "assert", situation, fact=situation.formal_wrong),
                 second_morgan, gap_hours=14, is_distractor=True),
            Line("filler", say(ctx, "address_change", situation), new_dana, gap_hours=22),
            # **The two-people case is stated, because the one-person case is.** An audit found
            # the corpus explaining Dana's two addresses and saying nothing about the two
            # Morgan Reids, so a reader who learned the rule from one applied it to the other
            # and concluded the finance Morgan was the objector. Two identical surface facts
            # resolving in opposite directions, one of them undocumented, is not a hard case.
            Line("filler",
                 say(ctx, "identity", situation,
                     name=BY_KEY[first_morgan].display,
                     left=BY_KEY[first_morgan].address, left_team=BY_KEY[first_morgan].team,
                     right=BY_KEY[second_morgan].address,
                     right_team=BY_KEY[second_morgan].team),
                 cast[5], gap_hours=15),
            Line("evidence", say(ctx, "assert", situation), first_morgan, gap_hours=40),
            Line("filler",
                 chatter.filler(situation, ctx.rng, new_dana, cast[:4], ctx.foil_pool),
                 new_dana, gap_hours=16),
        ]
        # R-M2-072. The layout is drawn, not written. Every one of these conversations used to
        # put the proposal at 1, the objection at 2, the near duplicate at 4 and the answer at
        # 7. The anchors keep their order - the family is an ordering claim - and ordinary
        # traffic is drawn in around them.
        lines, at = spread(
            ctx, anchors,
            lambda: _filler_line(situation, ctx, tuple(one for one in cast if one != bystander)),
        )
        out.append(ThreadDraft(
            family="F14", subject=situation.subject, situation_key=situation.key, lines=lines,
            start_offset_days=300 + index * 7, participants=cast,
            never_sends=(bystander,),
            facts={"objector": first_morgan, "same_name_decoy": second_morgan,
                   "bystander": bystander, "changed_address": f"{old_dana}/{new_dana}",
                   "evidence_at": str(at[7]), "identity_note_at": str(at[6])},
            answer_note=(
                f"Two shapes from one conversation. Who else was on it: all of {cast}, "
                f"including {BY_KEY[bystander].display}, who is a recipient throughout and "
                f"never sends. What the objector said later: the message at position {at[7]} "
                f"by {BY_KEY[first_morgan].display} <{BY_KEY[first_morgan].address}>, carrying "
                f"{situation.answer!r}. The message at position {at[4]} is a different person "
                f"of the same display name at <{BY_KEY[second_morgan].address}> stating "
                f"{situation.wrong!r}; positions {at[1]} and {at[5]} are one person under two "
                "addresses."
            ),
        ))
    return out


# -------------------------------------------------------------------------------------- F15

def build_f15(ctx: Context, count: int) -> list[ThreadDraft]:
    """Four ways the conversation someone means is not the conversation Gmail assigned.

    Two instances of each shape: a conversation renamed and continued under a new subject, a
    forward that opens a new conversation, a reply whose headers were lost so it lives outside
    its own thread, and a conversation that outgrew its thread and was continued in a second
    one. Two qualifications are recorded rather than papered over. A rename splits the
    conversation here because `messages.insert` requires a matching Subject, which is how the
    mailbox will hold it. And the split shape is built at the profile's long length rather than
    forced by the §3.8 ceiling, because the largest conversation the live mailbox has been
    shown to thread is 90 and risk S6 is open: the retrieval shape is reproduced, its cause is
    not. The old generator built none of
    these and no profile setting could add them (R-M2-054). They are structural, not temporal:
    every one of these threads still runs forwards in time.
    """
    out: list[ThreadDraft] = []
    shapes = ("subject_change", "forward", "orphan", "ceiling_split")
    for index in range(count):
        shape = shapes[index % len(shapes)]
        shape_fact = {"shape": shape}
        situation = ctx.take()
        cast = ctx.cast(4)
        start = 330 + index * 11
        if shape == "subject_change":
            # **Two conversations, because that is what Gmail does with this.** The first
            # version kept the rename inside one thread and the seeding double refused to
            # associate ten of its messages: `users.messages.insert` honours a supplied
            # `threadId` only when the Subject also matches, so a genuinely renamed message
            # opens a new conversation. That refusal *is* the family - the conversation a
            # person means is not the one Gmail assigned - so the corpus represents it the way
            # the mailbox will actually hold it rather than the way the plan sketched it.
            length = ctx.shape.randrange(10, 16)
            lines = scaffold(situation, length, ctx, cast)
            place(lines, length - 3, Line(
                "near_duplicate",
                say(ctx, "remind", situation, value=situation.older),
                cast[1], gap_hours=18, is_distractor=True))
            lines[length - 1] = Line(
                "filler",
                chatter.filler(situation, ctx.rng, cast[1], cast[2:], ctx.foil_pool),
                cast[1], gap_hours=20)
            out.append(ThreadDraft(
                family="F15", subject=situation.subject, situation_key=situation.key,
                lines=lines, start_offset_days=start, participants=cast,
                facts=shape_fact,
                answer_note=(
                    f"The conversation under the original subject. It ends on "
                    f"{situation.older!r} and announces the rename without carrying the answer."
                ),
            ))
            renamed = _other_subject(situation, ctx)
            continued = scaffold(situation, ctx.shape.randrange(7, 12), ctx, cast)
            continued[0] = Line(
                "filler",
                chatter.filler(situation, ctx.rng, cast[1], cast[2:], ctx.foil_pool),
                cast[1], gap_hours=24)
            place(continued, len(continued) - 2, Line(
                "evidence", say(ctx, "assert", situation), cast[2], gap_hours=20))
            out.append(ThreadDraft(
                family="F15", subject=renamed,
                situation_key=f"{situation.key}::renamed", lines=continued,
                start_offset_days=start + 5, participants=cast,
                continues=situation.key, facts=shape_fact, follows_parent=True,
                answer_note=(
                    f"The renamed conversation, carrying {situation.answer!r}. It shares the "
                    "participants and the matter with the original and shares neither its "
                    "subject line nor its threadId, and it carries no Re: or Fwd: prefix to "
                    "join them by."
                ),
            ))
        elif shape == "forward":
            length = ctx.shape.randrange(8, 14)
            origin = scaffold(situation, length, ctx, cast[:3])
            place(origin, length - 2, Line(
                "near_duplicate",
                say(ctx, "remind", situation, value=situation.older),
                cast[1], gap_hours=19, is_distractor=True))
            out.append(ThreadDraft(
                family="F15", subject=situation.subject, situation_key=situation.key,
                lines=origin, start_offset_days=start, participants=cast[:3],
                facts=shape_fact,
                answer_note=(
                    f"The original conversation. Its last substantive message carries "
                    f"{situation.older!r} and is the obvious sibling that is not the "
                    "continuation."
                ),
            ))
            forwarded = [
                # R-M2-071. "Original below." was F15's alone; it is a shared bank now.
                Line("filler", say(ctx, "forwarded", situation), cast[1], gap_hours=24),
                Line("filler",
                     chatter.filler(situation, ctx.rng, cast[3], (cast[1],), ctx.foil_pool),
                     cast[3], gap_hours=20),
                Line("evidence", say(ctx, "assert", situation), cast[3], gap_hours=26),
                Line("filler",
                     chatter.filler(situation, ctx.rng, cast[1], (cast[3],), ctx.foil_pool),
                     cast[1], gap_hours=18),
            ]
            out.append(ThreadDraft(
                family="F15", subject=f"Fwd: {situation.subject}",
                situation_key=f"{situation.key}::forward", lines=forwarded,
                start_offset_days=start + 6, participants=(cast[1], cast[3]),
                facts=shape_fact,
                continues=situation.key, follows_parent=True,
                answer_note=(
                    f"The forward is a separate conversation and the answer {situation.answer!r} "
                    "is only here. Gmail files it under its own threadId."
                ),
            ))
        elif shape == "orphan":
            length = ctx.shape.randrange(9, 15)
            origin = scaffold(situation, length, ctx, cast)
            place(origin, length - 2, Line(
                "near_duplicate",
                say(ctx, "remind", situation, value=situation.older),
                cast[1], gap_hours=17, is_distractor=True))
            out.append(ThreadDraft(
                family="F15", subject=situation.subject, situation_key=situation.key,
                lines=origin, start_offset_days=start, participants=cast,
                facts=shape_fact,
                answer_note=(
                    "The conversation Gmail will group. Its last substantive message carries "
                    f"{situation.older!r} and is wrong."
                ),
            ))
            out.append(ThreadDraft(
                family="F15", subject=f"Re: {situation.subject}",
                situation_key=f"{situation.key}::orphan",
                lines=[
                    Line("evidence", say(ctx, "assert", situation), cast[2], gap_hours=24),
                    Line("filler",
                         chatter.filler(situation, ctx.rng, cast[0], (cast[2],), ctx.foil_pool),
                         cast[0], gap_hours=20),
                ],
                start_offset_days=start + 4, participants=(cast[0], cast[2]),
                facts=shape_fact,
                orphan=True, continues=situation.key, follows_parent=True,
                answer_note=(
                    f"The answer {situation.answer!r} is in a message that is a reply in "
                    "content and a new conversation in fact: it carries no reference headers, "
                    "so it sits outside the threadId a reader would follow."
                ),
            ))
        else:
            first = scaffold(situation, ctx.long_length, ctx, cast)
            place(first, ctx.long_length - 2, Line(
                "near_duplicate",
                say(ctx, "remind", situation, value=situation.older),
                cast[1], gap_hours=12, is_distractor=True))
            out.append(ThreadDraft(
                family="F15", subject=situation.subject, situation_key=situation.key,
                lines=first, start_offset_days=start, participants=cast,
                facts=shape_fact,
                answer_note=(
                    # R-M2-073. The old note called this "the {n}-message ceiling of EP §3.8",
                    # which was wrong three ways: §3.8's ceiling is 100, {n} is §4.4's thread
                    # length, and this corpus carries unsplit conversations of that length, so
                    # nothing here was forced by a ceiling. The shape is reproduced on purpose
                    # and its cause is not; risk S6 stays open and the note now says so.
                    "Part one of a conversation split at the profile's §4.4 thread length. "
                    "This reproduces the *shape* EP §3.8's 100-message ceiling produces in "
                    "the live mailbox; it is not caused by that ceiling, and this corpus "
                    "contains unsplit conversations at least as long. It ends on the "
                    "superseded position."
                ),
            ))
            second_len = ctx.shape.randrange(8, 14)
            second = scaffold(situation, second_len, ctx, cast)
            second[0] = Line(
                "filler",
                chatter.filler(situation, ctx.rng, cast[0], cast[1:], ctx.foil_pool),
                cast[0], gap_hours=24)
            place(second, second_len - 2, Line(
                "evidence", say(ctx, "assert", situation), cast[2], gap_hours=20))
            out.append(ThreadDraft(
                family="F15", subject=situation.subject,
                situation_key=f"{situation.key}::continued", lines=second,
                start_offset_days=start + 7, participants=cast, continues=situation.key,
                follows_parent=True, facts=shape_fact,
                answer_note=(
                    f"Part two, same subject line, carrying {situation.answer!r}. The two parts "
                    "are one conversation to a person and two to Gmail."
                ),
            ))
    return out


# -------------------------------------------------------------------------------------- F16

def build_f16(ctx: Context, count: int) -> list[ThreadDraft]:
    """Five revisions that differ in one value, and a confirmation that names one of them.

    The old corpus prefixed its wrong candidates with the literal string `Superseded draft: `
    and dated them after the answer, so a regex removed the family and recency inverted it
    (R-M2-053). Here the revisions are identical in form, ascending in date, and the adopted
    one is **not** the last, so neither string matching nor recency selects it. The decisive
    detail is which revision number the confirmation names.
    """
    out: list[ThreadDraft] = []
    for index in range(count):
        situation = ctx.take()
        entity = BY_ENTITY[situation.entity]
        cast = ctx.cast(4)
        # The entity's own names are barred, exactly as they are when a situation is minted:
        # every revision body names the schedule's subject, so drawing "Harlow" as the adopted
        # figure for the Harlow schedule put the answer in all five candidates.
        # A figure, not a place name. The revision sentence says "the figure stands at X", and
        # an audit reported five revisions of an Atlas schedule whose figure was a town.
        kind = situation.value_kind if situation.value_kind in NUMERIC_KINDS else "index"
        values = list(mint_values(
            kind, ctx.rng, 5, avoid=(entity.formal, entity.plain)
        ))
        # Drawn, not fixed. The first draft adopted revision 3 at position 5 in every thread,
        # so "always take the third revision" would have passed the family without reading the
        # confirmation - the same class of regularity as the answer marker itself.
        adopted_index = ctx.shape.randrange(1, len(values) - 1)
        template = voice.CORES["revision"][ctx.rng.randrange(len(voice.CORES["revision"]))]
        # No revision-shaped ordinary traffic *inside* an F16 conversation: an audit found a
        # filler message asserting "The adopted one is revision 3" in a thread whose entire
        # mechanism is that exactly one revision is the answer. Elsewhere in the corpus that
        # shape is ordinary, which is what stops it marking the family.
        forbid = ("revision", "adopt")
        lines: list[Line] = [Line(
            "filler",
            voice.compose(
                f"Starting the revision run for the {entity.formal} schedule.", ctx.rng
            ),
            cast[0], gap_hours=24)]
        # **The adoption note is not the last word.** R-M2-069. Moving the figure out of the
        # ordinal and into the confirmation made the confirmation the newest message in the
        # conversation carrying a value, and "the latest message that states a value" is
        # exactly what the frozen query-free solver falls back on - F16 went to 100% on two
        # seeds of six. A revision run does not stop the moment something is signed: at least
        # one more draft circulates afterwards, and it carries a figure that was not adopted.
        room = list(range(adopted_index + 1, len(values) - 1)) or [len(values) - 2]
        confirm_after = room[ctx.shape.randrange(len(room))]
        confirmation_at = -1
        revision_at: list[int] = []
        for number, value in enumerate(values, start=1):
            revision_at.append(len(lines))
            # **One phrasing for all five revisions of a conversation**, drawn per thread.
            # The family needs candidates that are maximally similar and differ in one
            # decisive detail; five different phrasings would be five different sentences.
            # Drawing the template per thread keeps them alike inside a conversation while
            # no single wording selects F16's candidates across the corpus.
            lines.append(Line(
                "near_duplicate",
                voice.compose(
                    template.format(**_slots(situation, number=number, value=value)),
                    ctx.rng,
                ),
                cast[1], gap_hours=30, is_distractor=number - 1 != adopted_index))
            del number  # R-M2-068: the ordinal survives as a loop counter, not as text.
            for _ in range(ctx.shape.randrange(1, 4)):
                # R-M2-068. The five figures are minted for this conversation, so they are not
                # in the situation and the ordinary value-leak check could not see them. A foil
                # that minted the adopted figure put it on a filler message, and the family's
                # mechanism is that the confirmation is the only thing naming one candidate.
                lines.append(_filler_line(
                    situation, ctx, cast, forbid=forbid, barred=tuple(values)))
            if len(revision_at) - 1 == confirm_after:
                confirmation_at = len(lines)
                lines.append(Line(
                    "confirmation",
                    say(ctx, "adopt", situation, value=values[adopted_index]),
                    cast[2], gap_hours=36))
        if confirmation_at < 0:  # pragma: no cover - `room` always names a candidate
            raise ValueError(
                f"F16 {situation.key}: the confirmation was never placed (adopted "
                f"{adopted_index}, after {confirm_after}, of {len(values)} revisions)"
            )
        lines.append(_filler_line(
            situation, ctx, cast, forbid=forbid, barred=tuple(values)))
        out.append(ThreadDraft(
            family="F16", subject=situation.subject,
            situation_key=situation.key, lines=lines,
            start_offset_days=360 + index * 9, participants=cast,
            answer_override=values[adopted_index],
            wrong_override=values[(adopted_index + 1) % len(values)],
            older_override=values[(adopted_index + 2) % len(values)],
            barred_values=tuple(values),
            evidence_at=(revision_at[adopted_index], confirmation_at),
            facts={
                # Kept as the sequence index for anyone reading the manifest. It is no
                # longer written in any message: R-M2-068.
                "adopted_revision": str(adopted_index + 1),
                "adopted_at": str(revision_at[adopted_index]),
                "revisions_at": ",".join(str(one) for one in revision_at),
                "confirmation_at": str(confirmation_at),
                "adopted_value": values[adopted_index],
                # Recorded so the coverage rule can mask them exactly rather than guess at
                # them with a regex over prose, which is how it came to report candidates as
                # "differing in more than their value" when only the value differed.
                "revision_values": "|".join(values),
            },
            answer_note=(
                f"Five revisions of one sentence differing only in the figure, at positions "
                f"{revision_at}, ascending in date. The adopted one is revision "
                f"{adopted_index + 1} at position {revision_at[adopted_index]}, carrying "
                f"{values[adopted_index]!r}. It is not the newest revision, and once the "
                "figures are masked the five are the same sentence: nothing else separates "
                f"them. The confirmation at {confirmation_at} names the figure it signed, and "
                "is the only message that does. At least one further revision circulates "
                "after it, so the newest message carrying a figure is not the answer."
            ),
        ))
    return out


# -------------------------------------------------------------------------------------- F17

def build_f17(ctx: Context, count: int) -> list[ThreadDraft]:
    """Three messages make the wrong answer look well evidenced; a terse late reply overturns it.

    Two defects are being repaired at once. The ground truth used to mark the *first
    reinforcement* as the evidence, so the answer key pointed at the message the family exists
    to catch systems returning, in eight threads of eight. And the reversal was the top BM25 hit
    in eight of eight, so a query-score-only selector passed (R-M2-047). Here the reversal is
    written the way real reversals are written - short, without the topic's vocabulary, assuming
    the reader has the thread - and `_assert_ranks` refuses to emit a thread where the
    reinforcements do not outrank it.
    """
    out: list[ThreadDraft] = []
    for index in range(count):
        situation = ctx.take()
        entity = BY_ENTITY[situation.entity]
        cast = ctx.cast(5)
        length = ctx.shape.randrange(18, 30)
        lines = scaffold(situation, length, ctx, cast)
        reinforcement_at = sorted(ctx.shape.sample(range(2, length // 2), 3))
        for spot in reinforcement_at:
            place(lines, spot, Line(
                "reinforcement",
                say(ctx, "reinforce", situation, fact=situation.formal_wrong),
                cast[1], gap_hours=22, is_distractor=True))
        reversal_at = length - 2
        place(lines, reversal_at, Line(
            "reversal",
            say(ctx, "reverse", situation), cast[2], gap_hours=48))
        for trailing in range(reversal_at + 1, length):
            lines[trailing] = _filler_line(situation, ctx, cast)
        def _redraw_f17() -> None:
            for spot in reinforcement_at:
                lines[spot] = Line(
                    "reinforcement",
                    say(ctx, "reinforce", situation, fact=situation.formal_wrong),
                    cast[1], gap_hours=22, is_distractor=True)
            lines[reversal_at] = Line(
                "reversal", say(ctx, "reverse", situation), cast[2], gap_hours=48)

        # The tail first, for the reason given in `build_f11`.
        append_tail(ctx, lines, situation, cast)
        redraw_until_ranked(
            ctx, lines, situation.formal_true, above=reinforcement_at[0], below=reversal_at,
            redraw=_redraw_f17,
            why="F17's reinforcements must outscore the reversal, or query-score-only selection "
                "passes and the family stops being the falsifier for the reply-chain floor",
        )
        # R-M2-068. **The reversal answers the reinforcement a query-score selector returns.**
        # It used to carry no `replies_to` at all, so `corpus.py` threaded it onto whatever
        # message preceded it - an ordinary filler in both instances. F17 is registered as the
        # falsifier for the non-negotiable E2 reply-chain floor, and the chain that floor is
        # supposed to follow, from the trap to the thing that overturns it, was not in the
        # headers. The parent is chosen after the redraw loop, on the same query the loop
        # ranks on, so it is the best-scoring reinforcement rather than an arbitrary one.
        ranked = [one.text for one in lines]
        answered = min(
            reinforcement_at,
            key=lambda one: lexical.rank_of(ranked, situation.formal_true, one),
        )
        lines[reversal_at] = replace(lines[reversal_at], replies_to=answered)
        out.append(ThreadDraft(
            family="F17", subject=situation.subject, situation_key=situation.key, lines=lines,
            start_offset_days=400 + index * 8, participants=cast, tail_done=True,
            facts={"reversal_at": str(reversal_at),
                   "reinforcements_at": ",".join(str(one) for one in reinforcement_at),
                   "reversal_answers": str(answered),
                   # The text of a message the corpus actually contains. It used to be the
                   # bare template rendering, which occurs nowhere once the sentence is
                   # framed, so the note's ranking claim was about a string that did not
                   # exist.
                   "construction_query": lines[reinforcement_at[0]].text},
            answer_note=(
                f"The answer is {situation.answer!r}, in the reversal at position "
                f"{reversal_at}. The three reinforcements at {reinforcement_at} carry "
                f"{situation.wrong!r}, outrank the reversal on a BM25 construction query, and "
                "are the trap. A system that selects on query score alone returns the "
                "overturned answer with more evidence behind it the harder it tries. The "
                f"reversal replies to the reinforcement at {answered}, which is the one that "
                "scores best on that query: the References header is the only thing in the "
                "conversation that connects the message a ranker returns to the message that "
                "overturns it."
            ),
        ))
    return out


# ------------------------------------------------------------------------------------ noise

def build_short(ctx: Context, count: int) -> list[ThreadDraft]:
    """Brief exchanges: three to six messages, one sentence each.

    EP §4.2's corpus shape asks for about twelve short threads alongside the long and medium
    ones and this generator never built them, so every conversation in the corpus was at least
    eight messages of two or three sentences. That is not what a mailbox looks like, and it had
    a measurable consequence: the fixed-window baseline stopped emitting a filled row anywhere
    in the corpus, because no conversation was small enough to be disclosed whole.

    The sentences come from the same pools as everything else, so "short" is a property of the
    conversation and not a separate vocabulary.
    """
    out: list[ThreadDraft] = []
    for index in range(count):
        situation = ctx.take()
        cast = ctx.cast(3)
        length = ctx.shape.randrange(3, 7)
        lines = [
            Line(
                "filler",
                chatter.terse(situation, ctx.rng, cast[position % len(cast)], cast),
                cast[position % len(cast)],
                gap_hours=ctx.shape.randrange(2, 30),
            )
            for position in range(length)
        ]
        out.append(ThreadDraft(
            family="", subject=situation.subject, situation_key=f"{situation.key}::short",
            lines=lines, start_offset_days=ctx.shape.randrange(0, 430), participants=cast,
            answer_override="",
            answer_note="A brief exchange. Carries no evidence for any family.",
        ))
    return out


def build_bridges(ctx: Context, entities: set[str], conversations: int) -> list[ThreadDraft]:
    """Ordinary conversations that happen to pair an entity's two names.

    **A tier-2 query is written against the colloquial name.** If the corpus never pairs that
    name with the formal one, the case is not hard, it is unanswerable: an audit measured the
    F3 paraphrase query ranking its own evidence 63rd of 90 in-thread while the trap decoy
    ranked 1st, because six of seven aliases were never introduced anywhere. Every entity a
    paraphrase-consuming family uses gets a bridge, in a filler conversation rather than in the
    scored one, and the manifest records which - a bridge is also a two-hop lexical route to
    the evidence, which the case author has to know about.
    """
    # **Shape-stable.** How many of these conversations exist, and how long they are, must not
    # move with the seed: EP §5.3's lever is that a system tuned to one corpus's geometry gains
    # nothing on the next. Which entities need bridging does move with the seed, so the batch
    # count is computed from a stable number - three per conversation over a fixed-size list -
    # and any short final batch is padded rather than dropped.
    # **The conversation count is passed in, not derived.** How many entities need bridging
    # moves with the seed - which entity a thread draws is a surface choice - and EP §5.3
    # requires the corpus's geometry to hold across seeds. The caller computes the count from
    # the profile's family counts, which do not move, and the entity list is cycled to fill it.
    out: list[ThreadDraft] = []
    pending = sorted(entities)
    per_thread = 6
    for index in range(conversations):
        batch = [
            pending[(index * per_thread + offset) % len(pending)]
            for offset in range(per_thread)
        ] if pending else []
        anchor = ctx.take()
        cast = ctx.cast(4)
        lines = scaffold(anchor, 3 + per_thread * 2, ctx, cast)
        for offset, key in enumerate(batch):
            twin = next(
                (one for one in ctx.foil_pool if one.entity == key),
                None,
            ) or next((one for one in ctx.pool if one.entity == key), None)
            if twin is None:  # pragma: no cover - every entity in use has a situation
                continue
            place(lines, 1 + offset * 2, Line(
                "filler", chatter.alias_bridge(twin, ctx.rng), cast[offset % len(cast)],
                gap_hours=14))
        out.append(ThreadDraft(
            family="", subject=anchor.subject, situation_key=f"{anchor.key}::glossary",
            lines=lines, start_offset_days=ctx.shape.randrange(0, 430), participants=cast,
            answer_override="",
            answer_note=(
                "Filler that introduces colloquial names: "
                + ", ".join(sorted(batch))
                + ". Carries no evidence."
            ),
        ))
    return out


def build_filler(ctx: Context, count: int) -> list[ThreadDraft]:
    """Census-calibrated noise (EP §4.2): conversations with no scored content at all.

    Filler threads are not decoration. They are what makes a corpus-wide search return more
    than the scored threads, and they carry the cross-thread vocabulary overlap EP §4.6
    requires. No message in them is evidence for anything.
    """
    out: list[ThreadDraft] = []
    for index in range(count):
        situation = ctx.take()
        cast = ctx.cast(ctx.shape.randrange(3, 6))
        length = ctx.shape.randrange(4, 22)
        lines = scaffold(situation, length, ctx, cast)
        if index % 3 == 0:
            place(lines, length // 2, Line(
                "filler", chatter.alias_bridge(situation, ctx.rng), cast[1], gap_hours=12))
        out.append(ThreadDraft(
            family="", subject=situation.subject, situation_key=f"{situation.key}::noise",
            lines=lines, start_offset_days=ctx.shape.randrange(0, 430), participants=cast,
            answer_override="",
            answer_note="Filler. Carries no evidence for any family.",
        ))
    return out


def with_tail(ctx: Context, drafts: list[ThreadDraft]) -> list[ThreadDraft]:
    """Append a drawn number of ordinary messages after every conversation's last decisive one.

    **An audit found the answer at exactly `length - 2` in twelve threads of twelve**, across
    F2, F14, F15, F16 and F17 - a rule that needs no query and defeats precisely the mechanisms
    those families exist to test. The builders each ended their conversation a message or two
    after the thing that mattered because that is how one writes a thread by hand; drawing the
    tail from the shape generator removes the regularity while keeping it stable across seeds.
    """
    for draft in drafts:
        if draft.day_offsets or draft.tail_done:
            continue
        situation = next(
            (one for one in ctx.pool + list(ctx.foil_pool)
             if one.key == "::".join(draft.situation_key.split("::")[:2])),
            None,
        )
        if situation is None:
            continue
        cast = tuple(
            one for one in (draft.participants or tuple({x.sender for x in draft.lines}))
            if one not in draft.never_sends
        )
        if not cast:
            continue
        # **One of the trailing messages decides something** (R-M2-069, 2026-09-16). The tail
        # removed "the answer is at `length - 2`"; it did not remove "the answer is the last
        # decisive thing anyone said", which a query-free solver exploits through its recency
        # tie-break. A conversation does not stop having other business after the matter is
        # settled, so exactly one tail message states a settled position **about a different
        # matter** - drawn at a position inside the tail rather than pinned to the end, because
        # a decisive last message would be the next regularity.
        append_tail(ctx, draft.lines, situation, cast, barred=draft.barred_values)
        draft.tail_done = True
    return drafts


def append_tail(
    ctx: Context, lines: list[Line], situation: Situation, cast: tuple[str, ...],
    barred: tuple[str, ...] = (),
) -> None:
    """The trailing ordinary traffic, drawn. See `with_tail` for why it exists.

    Separated so a family registered on a rank relationship can append its own tail *before*
    its redraw loop and establish that relationship against the conversation it ships
    (R-M2-067). The draw sequence is identical either way, so a builder that calls this takes
    the same values from the shape stream `with_tail` would have taken.
    """
    tail = ctx.shape.randrange(1, 7)
    decisive_at = ctx.shape.randrange(tail)
    for index in range(tail):
        lines.append(
            _filler_line(
                situation, ctx, cast,
                force="assert" if index == decisive_at else None, barred=barred,
            )
        )


def with_routine_attachments(ctx: Context, drafts: list[ThreadDraft]) -> list[ThreadDraft]:
    """Put small, decision-free files on ordinary messages.

    Attachments existed on four messages in 1,555 and all four were F8's pair, so "the message
    with an attachment" retrieved the carrying message with no retrieval at all.
    """
    for draft in drafts:
        situation = next(
            (one for one in ctx.pool + list(ctx.foil_pool)
             if one.key == "::".join(draft.situation_key.split("::")[:2])),
            None,
        )
        if situation is None:
            continue
        for index, line in enumerate(draft.lines):
            if line.role != "filler" or line.attachments:
                continue
            if ctx.shape.random() >= chatter.ATTACHMENT_SHARE:
                continue
            name, content = chatter.routine_attachment(situation, ctx.rng)
            draft.lines[index] = Line(
                line.role, line.text, line.sender, gap_hours=line.gap_hours,
                is_distractor=line.is_distractor,
                attachments=(Attachment(
                    filename=name, media_type="text/csv", content=content,
                    carries_the_fact=False,
                ),),
                subject_override=line.subject_override,
            )
    return drafts


Builder = Callable[[Context, int], list[ThreadDraft]]

BUILDERS: Final[dict[str, Builder]] = {
    "F1": build_f1, "F2": build_f2, "F3": build_f3, "F4": build_f4, "F5": build_f5,
    "F6": build_f6, "F7": build_f7, "F8": build_f8, "F10": build_f10, "F11": build_f11,
    "F12": build_f12, "F13": build_f13, "F14": build_f14, "F15": build_f15,
    "F16": build_f16, "F17": build_f17,
}

_missing = sorted(set(REGISTERED_N) - set(BUILDERS))
if _missing:  # pragma: no cover - import-time guard
    raise AssertionError(
        f"families {_missing} are registered in EP §4.3/§4.7 and have no builder. Nine of "
        "seventeen were in exactly this state and the coverage report still passed them "
        "(R-M2-054)"
    )


def make_context(
    seed: int, *, situations_needed: int, long_length: int = 90, shape_key: str = ""
) -> Context:
    """`shape_key` is deliberately **not** the master seed - see `Context`."""
    rng = Random(seed)
    minted = list(mint_situations(rng, situations_needed))
    # A quarter reserved as foils, and because `mint_situations` is topic-balanced the reserve
    # spans every topic. It has to: a foil of a different topic shares no vocabulary with the
    # conversation it sits in, and an audit found the evidence sentence's own topic tail pure
    # to evidence because ordinary traffic never used that topic.
    reserved = max(24, situations_needed // 4)
    # **The reserve covers every entity the pool uses, where the mint allows it** (R-M2-069,
    # 2026-09-16). Taking the last `reserved` left 17 of 37 entities with no foil of their own,
    # and `chatter.filler`'s same-entity branch is the only way ordinary traffic states a
    # settled position about *this conversation's project*. In those threads the answer was the
    # only firmly stated thing about the project, which is the register shortcut itself: F5
    # scored 2 of 2 against a query-free solver with the confirmation the single positively
    # scored message in the thread.
    #
    # Chosen from the tail inward so the pool keeps the topic-major order `mint_situations`
    # built for F3's seven-per-topic requirement, and an entity is only reserved when the pool
    # keeps one of its own - a reserve that emptied an entity would trade one gap for another.
    by_entity: dict[str, list[int]] = {}
    for index, one in enumerate(minted):
        by_entity.setdefault(one.entity, []).append(index)
    chosen: list[int] = []
    for entity in sorted(by_entity):
        places = by_entity[entity]
        if len(places) >= 2:
            chosen.append(places[-1])
    chosen = sorted(set(chosen), reverse=True)[:reserved]
    for index in reversed(range(len(minted))):
        if len(chosen) >= reserved:
            break
        if index not in chosen:
            chosen.append(index)
    reserve = {index for index in chosen}
    return Context(
        rng=rng,
        shape=Random(shape_key),
        long_length=long_length,
        pool=[one for index, one in enumerate(minted) if index not in reserve],
        foil_pool=tuple(one for index, one in enumerate(minted) if index in reserve),
    )


__all__ = [
    "BUILDERS", "FAMILY_NAMES", "REGISTERED_N", "SWEEP_FRACTIONS", "Builder", "Context",
    "Exhausted", "build_bridges", "build_filler", "build_short", "make_context", "place",
    "append_tail",
    "spread",
    "quoted_fragment",
    "scaffold", "with_routine_attachments", "with_tail",
    "sweep_position",
    "unnamed_by",
]
