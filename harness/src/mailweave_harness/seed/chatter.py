"""On-topic traffic: the population a distractor is drawn from.

Two findings shaped this file, and the second replaced most of it.

The first was volume: 2,452 messages with 345 distinct bodies once boilerplate was stripped
(R-M2-055). Composition fixed that.

The second was shape. An independent evaluator separated decisive messages from filler with no
labels at all, because filler was always opener-topic-closer and everything decisive was a bare
assertion; and because each family's role carried a phrase unique in the corpus. Volume did not
help: a thousand distinct sentences that are all *recognisably filler* leave a ninety-message
thread with four candidates.

So ordinary traffic is now built from the same parts as everything else. `voice.compose` frames
every message identically, and a share of filler carries a **foil**: a decisive sentence - a
confirmation, a reversal, a second-hand report, a numbered revision - about a *different*
matter, true and irrelevant. A conversation about Alder's notice period contains real
reversals concerning Rowan. The sentence shapes stop predicting anything, and what is left to
find is which message is about the matter that was asked about.

`assert_no_value_leak` is unchanged and still the constraint that matters: nothing here states
the thread's own answer, wrong value or superseded value.
"""

from __future__ import annotations

import re
from random import Random
from typing import Final, Sequence

from . import voice
from .situations import NUMERIC_KINDS, Situation, mint_values
from .world import BY_ENTITY, BY_KEY, EVENTS, PEOPLE, Person, states

MIDDLES: Final[dict[str, tuple[str, ...]]] = {
    "notice_period": (
        "The signed copy of the {formal} agreement is in the shared folder, not the draft one.",
        "Legal have asked us to stop quoting the term from memory in emails about {plain}.",
        "There is an older summary of the {formal} terms floating around that nobody has retired.",
        "Whoever answers procurement on {plain} should read the amendment first.",
        "We have two versions of the {formal} schedule and only one of them was executed.",
        "The renewal calendar entry for {plain} is still pointing at the previous owner.",
    ),
    "inspection_site": (
        "The inspection rota for {formal} has not been reissued since the move.",
        "Someone is still booking travel to the old place for {plain}.",
        "Access passes for the {formal} inspections need reprinting.",
        "The checklist we use for {plain} references a floor plan that no longer exists.",
        "Facilities want a week's notice before we send anyone for {formal}.",
        "The inspection photos for {plain} are going into the wrong folder.",
    ),
    "budget_line": (
        "Finance have reopened the {formal} line for questions until the end of the month.",
        "The forecast for {plain} was built before any of this was known.",
        "There are two cost centres carrying {formal} work and it makes reporting a mess.",
        "Nobody has reconciled the accruals on {plain} since the handover.",
        "The board pack shows {formal} under the old heading.",
        "Procurement and finance are quoting different baselines for {plain}.",
    ),
    "certification": (
        "The certificate folder for {formal} needs an owner who is not on leave.",
        "We get a renewal reminder for {plain} and it goes to a mailbox nobody reads.",
        "The auditors asked for the {formal} evidence pack and we sent the index by mistake.",
        "There is a scanned copy of the {plain} paperwork that is missing a page.",
        "Compliance want the {formal} record moved off the shared drive.",
        "The renewal workflow for {plain} has three approvers and two of them have left.",
    ),
    "tolerance": (
        "The gauge used for {formal} has not been calibrated since the line moved.",
        "Two people are recording {plain} readings in different units.",
        "The tolerance sheet for {formal} is pinned to the wall and is out of date.",
        "We should stop reporting {plain} measurements by photograph.",
        "Quality want a second reading on {formal} before anything goes to the customer.",
        "The rig that measures {plain} is booked solid until the end of the week.",
    ),
    "delivery_window": (
        "The carrier portal shows {formal} against a booking reference we do not recognise.",
        "Goods-in are not being told when {plain} is coming.",
        "There is a standing slot for {formal} that nobody has cancelled.",
        "The paperwork travels separately from {plain} and it keeps going astray.",
        "Two of us have been chasing the same carrier about {formal}.",
        "The site cannot take {plain} outside staffed hours.",
    ),
    "liability": (
        "Insurers have asked for the current {formal} wording, not the summary.",
        "We keep describing the {plain} position in slides and it drifts each time.",
        "The claims history for {formal} is split across two systems.",
        "Nobody has told the broker about the {plain} change.",
        "The indemnity summary for {formal} was written by someone who has since left.",
        "Legal want to review anything we say externally about {plain}.",
    ),
    "throughput": (
        "The line data for {formal} is being read off a dashboard that averages overnight.",
        "Shift handovers are not recording stoppages on {plain}.",
        "The rebuild schedule for {formal} keeps moving by a few days at a time.",
        "We are quoting {plain} capacity to customers from a sheet nobody owns.",
        "Maintenance want a full day on {formal} and cannot get one.",
        "The counters on {plain} reset when the power dipped.",
    ),
    "defect_cause": (
        "The failed units from {formal} are still in the quarantine cage.",
        "We have photographs of the {plain} failures but no batch numbers.",
        "The supplier has asked to see our {formal} test method.",
        "Two theories about {plain} are circulating and neither has been written down.",
        "The review actions from the {formal} investigation have no owners.",
        "Customers have started asking about {plain} directly.",
    ),
    "approval": (
        "The delegation matrix still lists the previous owner for {formal}.",
        "Requests about {plain} are being approved by whoever is nearest.",
        "We need one named approver for {formal} before the audit.",
        "The approval mailbox for {plain} forwards to a distribution list.",
        "Nobody knows who countersigns {formal} when the signatory is away.",
        "Two approvals were given on {plain} last month by different people.",
    ),
    "storage_move": (
        "The stock count for {formal} was taken mid-move and is unreliable.",
        "Racking at the new place will not take the {plain} pallets as they are.",
        "There is still signage pointing at the old {formal} bay.",
        "The insurance schedule lists {plain} at an address we have left.",
        "We are paying for two units while {formal} is split across both.",
        "Nobody has updated the pick paths for {plain}.",
    ),
    "handover": (
        "The handover checklist for {formal} has items with no owner.",
        "Documentation for {plain} arrived without the appendices.",
        "The outgoing team's mailbox for {formal} is being closed next week.",
        "We inherited a spreadsheet for {plain} that only one person can open.",
        "There are open actions from the {formal} handover that predate us.",
        "The training sessions for {plain} were cancelled and never rebooked.",
    ),
}


def assert_no_value_leak(
    text: str, situation: Situation, barred: tuple[str, ...] = ()
) -> None:
    """`barred` is for values a *thread* mints rather than the situation carrying them.

    F16 draws five figures per conversation and the answer is one of them, so none of them is
    in `situation.answer/wrong/older` and this check could not see them. A foil minting the
    adopted figure put that figure on an ordinary message, and the family's whole mechanism is
    that the confirmation is the only thing pointing at one candidate.
    """
    for value in tuple(barred) + (situation.answer, situation.wrong, situation.older):
        if states(value, text):
            raise AssertionError(
                f"filler for {situation.key} contains the value {value!r}. Filler that states a "
                "value makes the evidence message optional, and the family stops measuring "
                "whether the evidence was found"
            )


#: How often an ordinary message carries a small file. Attachments used to exist on exactly
#: four messages in 1,555 and all four were F8's pair, so "return the message with an
#: attachment" retrieved the carrying message for free at 389 times the base rate.
ATTACHMENT_SHARE: Final[float] = 0.05


def routine_attachment(situation: Situation, rng: Random) -> tuple[str, str]:
    """A small, true, decision-free file: a filename and its CSV content."""
    entity = BY_ENTITY[situation.entity]
    stem = entity.formal.lower().replace(" ", "-")
    kind = ("notes", "rota", "contacts", "log", "checklist", "schedule")[rng.randrange(6)]
    # Half the routine files use the schedule label set. Otherwise `kind in {prior, proposed,
    # agreed, review}` is the schema tell the header used to be: an attachment whose rows carry
    # those four labels would be an F8 file and nothing else.
    labels = (
        ["prior", "proposed", "agreed", "review"]
        if rng.random() < 0.5
        else [kind] * 4
    )
    rows = "\n".join(
        f"{entity.formal},{labels[index % len(labels)]},"
        f"{mint_values('index', rng, 1)[0]},2026-0{rng.randrange(1, 9)}-{rng.randrange(10, 28)}"
        for index in range(rng.randrange(3, 7))
    )
    return f"{stem}-{kind}.csv", f"entity,kind,count,recorded\n{rows}"


#: Concrete detail that is true, checkable and decides nothing. Ordinary mail is full of
#: numbers, dates and names, and without them "this message contains a digit" separated the
#: planted population from the rest at two and a half times the base rate - a cheaper filter
#: than retrieval, found by measuring rather than by reading.
DETAILS: Final[tuple[str, ...]] = (
    "Last count was {number}.",
    "There are {number} of them outstanding.",
    "That was on {date}.",
    "Diarised for {date}.",
    "{who} has the file if you need it.",
    "Ask {who} before you change anything.",
    "It has been open {number} days.",
    "{number} people are on the distribution list.",
    "I logged it on {date}.",
    "Reference is with {who}.",
    "Roughly {number} either way.",
    "Due back {date}.",
)

#: How often an ordinary message carries a concrete detail of its own.
DETAIL_SHARE: Final[float] = 0.55

#: How often an ordinary message carries a decisive sentence about some other matter. High
#: enough that "this sentence looks like a decision" stops being a signal, low enough that a
#: conversation still reads as being about its own subject.
FOIL_SHARE: Final[float] = 0.34


#: Which decisive shapes ordinary traffic carries. Every core a family uses is in here, because
#: a shape only families use is a shape that identifies a family: an audit found the objection
#: bank selecting F5's and F10's objections with precision 1.0 for exactly that reason.
#:
#: **`assert` is weighted, and that is R-M2-069's repair** (2026-09-16). The register split the
#: fifth read measured on hedges is smaller than the one on *finality*: among the messages a
#: query-free solver actually scores - those naming the conversation's entity and carrying a
#: value - 16 of 25 evidence messages carried a settled-position phrase ("that is the
#: position", "as agreed", "I have updated the record") against 5 of 174 ordinary ones. An odds
#: ratio near 76, and the single largest shortcut in the corpus.
#:
#: The repair is to write ordinary mail the way ordinary mail is written, not to take the
#: phrase away from the evidence: **people state settled positions about routine matters all
#: day**, and a corpus in which only the answer is ever stated firmly is the unrealistic one.
#: The evidence stays unhedged, the question stays natural and the declared answer is
#: unchanged; what changes is that deciding something is no longer rare.
FOIL_KINDS: Final[tuple[str, ...]] = (
    "assert", "assert", "assert", "assert", "assert", "assert",
    "propose", "object", "reverse", "hearsay", "remind", "reinforce", "attach",
    "chase", "revision", "invoice", "nochange", "charge", "concur", "plain", "plain",
    # R-M2-071. The scaffolding kinds. Each of these was written inline by exactly one builder
    # and so occurred inside exactly one family: `grep "Everyone on this list is on it for the
    # duration"` returned every F14 conversation and nothing else, which is a family marker
    # however carefully the values and the frames were re-minted. Ordinary traffic draws them
    # now, so the sentence says what it says and stops saying which family it is in.
    "stale", "dated_event", "identity", "roster", "address_change", "forwarded", "accept",
    "adopt",
)


def _duplicate_name(rng: Random) -> tuple[str, str, str, str, str]:
    """A display name two people in `world.PEOPLE` share, with both addresses and both teams.

    R-M2-071. F14's identity sentences named a real duplicated pair; ordinary traffic carrying
    the same sentence has to name a real one too, or the corpus would be full of messages
    saying two people share a name when they do not. Where the world has no duplicate the
    caller gets a pair that at least exists, and the `identity` bank is then never selected by
    the exclusivity this repair is for - which is a statement about the world, not a fallback
    that quietly writes something false.
    """
    by_display: dict[str, list[Person]] = {}
    for person in PEOPLE:
        by_display.setdefault(person.display, []).append(person)
    pairs = [group for group in by_display.values() if len(group) > 1]
    if not pairs:
        one = PEOPLE[rng.randrange(len(PEOPLE))]
        return (one.display, one.address, one.address, one.team, one.team)
    group = pairs[rng.randrange(len(pairs))]
    left, right = group[0], group[1]
    return (left.display, left.address, right.address, left.team, right.team)


def _fresh(kind: str, rng: Random, avoid: tuple[str, ...]) -> str:
    """A newly minted value of `kind`, from the same generator a family's values come from.

    **This is the repair for a perfect unsupervised oracle.** Filler used to recycle a handful
    of dates and measurements while every planted value was minted fresh, so "this value string
    occurs exactly once in the corpus" selected planted messages at precision 1.000 and lift
    11x - and isolated the F17 reversal, which is the one message that family exists to make
    hard to find. Ordinary mail now mints its values the same way, so a value occurring once is
    ordinary.
    """
    return mint_values(kind, rng, 1, avoid)[0]


def _foil(
    situation: Situation, other: Situation, rng: Random, cast: Sequence[str],
    avoid: frozenset[str] = frozenset(),
    forbid: tuple[str, ...] = (),
) -> str:
    """A decisive sentence about `other`, planted in a conversation about `situation`."""
    entity = BY_ENTITY[other.entity]
    barred = (situation.answer, situation.wrong, situation.older)
    speakers = [one for one in cast if BY_KEY[one].display not in barred] or list(cast)
    allowed = tuple(one for one in FOIL_KINDS if one not in forbid) or FOIL_KINDS
    kind = allowed[rng.randrange(len(allowed))]
    # A "figure" that is a place name, or a per-consignment charge that is a date, is
    # incoherent - and an audit found all nineteen such messages were filler and none was
    # evidence, which makes semantic incoherence a filler fingerprint as well as a realism
    # defect. The numeric-slot shapes draw a numeric value.
    if kind in {"revision", "charge"} and other.value_kind not in NUMERIC_KINDS:
        kind = "assert"
    # Re-minted per use rather than reusing the foil situation's own value, for the same
    # reason: twenty foils reusing twenty values makes those values frequent and every
    # planted value rare.
    # **The foil's own value, not a fresh one.** Re-minting per use meant the same matter was
    # asserted with a different number every time it came up, so a (frame, entity) pair
    # asserted more than once was filler with precision 1.000 and a pair asserted exactly once
    # was answer-bearing at 3.7 times the base rate. Ordinary mail agrees with itself now, the
    # way answer-bearing mail does.
    value = other.answer
    fact = other.formal_true
    # R-M2-071. Slots for the scaffolding kinds. They are drawn from the same world the
    # families draw them from - a real event, the corpus's one genuinely duplicated display
    # name - so an ordinary message carrying one states something true.
    event = EVENTS[rng.randrange(len(EVENTS))]
    twin = _duplicate_name(rng)
    # The colloquial register is a family's decoy vocabulary, so ordinary traffic has to speak
    # it too: an audit found every five-gram of the plain-register sentence pure to
    # `trap_decoy`, which is a marker however the sentence is phrased.
    plain_fact = other.plain_decoy.replace(other.wrong, value)
    return voice.say(
        kind, rng, avoid,
        fact=fact,
        plain_fact=plain_fact,
        value=value,
        formal=entity.formal,
        plain=entity.plain,
        reason=other.reason,
        event=event.label,
        on=event.on.strftime("%d %B %Y"),
        name=twin[0],
        left=twin[1],
        right=twin[2],
        left_team=twin[3],
        right_team=twin[4],
        who=BY_KEY[speakers[rng.randrange(len(speakers))]].display,
        number=rng.randrange(1, 6),
        # Identifier-shaped tokens have to be ordinary too: F1's invoice numbers were the only
        # A#### strings in the corpus, so "carries an identifier" was a planted-message filter.
        # Identical in form to F1's identifiers and drawn from a disjoint band, because a
        # foil that happened to mint an F1 identifier put that identifier in two messages and
        # the family's own rule caught it.
        token=f"A{rng.randrange(5000, 9999)}",
    )


def filler(
    situation: Situation,
    rng: Random,
    who: str,
    others: tuple[str, ...],
    foils: Sequence[Situation] = (),
    avoid: frozenset[str] = frozenset(),
    forbid: tuple[str, ...] = (),
    force: str | None = None,
    barred: tuple[str, ...] = (),
) -> str:
    """One message that says nothing decisive **about this conversation's matter**.

    `force` names a foil kind and makes the foil branch certain rather than drawn. It exists for
    `families.with_tail`, which needs a guaranteed settled-register statement after the evidence:
    an audit found the evidence was the last decisive thing said in a conversation far more often
    than chance, so "the newest message that decides anything" found it with no query
    (R-M2-069). Forcing the *kind* and not the *content* keeps this ordinary traffic - it still
    decides another matter, still cannot state this thread's values, and still goes through the
    collision filter below.
    """
    entity = BY_ENTITY[situation.entity]
    values = tuple(
        one for one in tuple(barred) + (situation.answer, situation.wrong, situation.older)
        if one
    )

    def _collides(other: Situation) -> bool:
        # Containment, not equality: a foil answering "143" states this thread's "43". The
        # generator hit that on the first build, and it is the same substring trap that made
        # every decoy read as stating the answer in `situations._mint_value`.
        return any(
            states(left, right) or states(right, left)
            for left in values
            for right in (other.answer, other.wrong, other.older)
            if left and right
        )

    usable = [one for one in foils if not _collides(one)]
    # Same topic where one is available: that is what makes a cross-thread decoy share the
    # target's vocabulary (EP §4.6) instead of sharing only boilerplate.
    same_topic = [one for one in usable if one.topic == situation.topic]
    # **The thread's own entity, on another matter.** An audit found that in every F3 thread
    # exactly two messages named the thread's project together with a value - the near miss and
    # the evidence - so "assertion-shaped, names the project, carries a number" was a singleton
    # at ninety times the base rate. A conversation about Fenwick's notice period now also
    # carries true, decided statements about Fenwick's storage and its throughput.
    same_entity = [one for one in usable if one.entity == situation.entity]
    text = ""
    if usable and (force is not None or rng.random() < FOIL_SHARE):
        draw = rng.random()
        # **A forced decisive message is about this conversation's own entity where one is
        # available.** `with_tail` asks for it to break "the answer is the last decisive thing
        # said", and a settled statement about some other project does not break it: a solver
        # that filters on the conversation's subject never sees that message at all, so the
        # evidence stays the newest decisive thing *about this matter*. The same draw order is
        # kept for the unforced path so the ordinary mix is unchanged.
        if same_entity and (force is not None or draw < 0.3):
            pool_now = same_entity
        elif same_topic and draw < 0.75:
            pool_now = same_topic
        else:
            pool_now = usable
        candidate = _foil(
            situation,
            pool_now[rng.randrange(len(pool_now))],
            rng,
            (who,) + others,
            avoid,
            forbid if force is None else tuple(one for one in FOIL_KINDS if one != force),
        )
        if not any(states(value, candidate) for value in values):
            text = candidate
    if not text:
        # A person's name can *be* an answer: the `approval` topic asks who countersigns.
        pool = [one for one in (others or (who,)) if BY_KEY[one].display not in values]
        mention = BY_KEY[pool[rng.randrange(len(pool))]].display if pool else "the team"
        # `plain` aliases begin with "the", so a template that supplies its own article
        # produced "the the quayside shed" in fifty-nine messages - a generator artefact that
        # appeared on filler only, which makes it a negative marker as surely as a positive
        # one. The article is dropped when the alias already carries it.
        core = MIDDLES[situation.topic][rng.randrange(6)].format(
            formal=entity.formal, plain=entity.plain, who=mention
        )
        core = re.sub(r"\b([Tt])he the\b", r"\1he", core)
        if rng.random() < DETAIL_SHARE:
            detail = DETAILS[rng.randrange(len(DETAILS))].format(
                number=_fresh("index", rng, values),
                date=_fresh("date", rng, values),
                who=mention,
            )
            if not any(states(value, detail) for value in values):
                core = f"{core} {detail}"
        if rng.random() < 0.12:
            core = f"{core} {voice.HEDGES[rng.randrange(len(voice.HEDGES))]}"
        text = voice.compose(core, rng, avoid)
    assert_no_value_leak(text, situation, barred)
    return text


def terse(
    situation: Situation, rng: Random, who: str, cast: Sequence[str]
) -> str:
    """One sentence, no frame. What a three-message exchange actually looks like."""
    entity = BY_ENTITY[situation.entity]
    values = tuple(one for one in (situation.answer, situation.wrong, situation.older) if one)
    pool = [one for one in cast if BY_KEY[one].display not in values] or list(cast)
    core = MIDDLES[situation.topic][rng.randrange(6)].format(
        formal=entity.formal,
        plain=entity.plain,
        who=BY_KEY[pool[rng.randrange(len(pool))]].display,
    )
    core = re.sub(r"\b([Tt])he the\b", r"\1he", core)
    assert_no_value_leak(core, situation)
    return core


def alias_bridge(situation: Situation, rng: Random) -> str:
    """A message that pairs an entity's two names.

    Planted deliberately and recorded in the manifest. A tier-2 query is written against the
    colloquial name, and if the corpus never pairs it with the formal one the case is not hard,
    it is unanswerable. Recording it also tells the case author that a two-hop lexical route to
    the evidence exists, which is exactly the thing F4 is registered to detect.
    """
    entity = BY_ENTITY[situation.entity]
    return voice.compose(
        f"For anyone new on this: {entity.plain} and {entity.formal} are the same thing. "
        "The old name is still on some of the paperwork.",
        rng,
    )


def reachable_bodies() -> int:
    """Upper bound on distinct bodies before entity, person or foil substitution."""
    frames = len(voice.SHAPES)
    topical = sum(len(one) for one in MIDDLES.values())
    decisive = sum(len(one) for one in voice.CORES.values())
    return frames * len(voice.LEAD_INS) * len(voice.CLOSERS) * (topical + decisive)


__all__ = [
    "DETAILS", "DETAIL_SHARE", "FOIL_KINDS", "FOIL_SHARE", "MIDDLES", "terse", "alias_bridge", "assert_no_value_leak",
    "filler", "reachable_bodies",
]
