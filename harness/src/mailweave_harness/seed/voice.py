"""One bank of sentences, shared by every message the corpus contains.

**This module exists because of a specific finding.** An independent evaluator, told not to
trust anything in this repository, separated the answer-bearing messages from the distractor
population *without labels*: filler was always an opener, a topic sentence and a closer, and
every message planted to be something was a bare one- or two-sentence assertion. Counting
sentences after stripping the signature gave precision 0.76 and recall 0.98, and a ninety-
message conversation collapsed to four candidates before any retrieval happened. The position
sweep measures nothing once that filter exists.

The same audit found the second half of it: each family's role carried a phrase unique in the
corpus. `Settled, and this is the version to quote` occurred exactly twice and both were F5
confirmations; `My own view, for the thread` selected F6's authored claim; `and has been since
this morning` selected F17's reversal. Twenty of twenty evidence-bearing threads were solved by
a five-gram.

Both are the R-M2-046 defect one level further out: not a marker somebody added, but a
regularity nobody removed. So the repair is structural rather than cosmetic.

*Every* message is composed the same way - a lead-in, a core sentence, sometimes a closer - and
draws its lead-in and closer from the same pools whatever it was planted to be. The role cores
live here too, in banks, and `chatter` plants the **same cores about other matters** as ordinary
traffic: a conversation about Alder's notice period contains confirmations, reversals and
second-hand reports concerning Rowan and Cobalt, which are true, decisive and irrelevant. A
phrase that appears on forty messages of which two are the answer is not a marker.

What remains discoverable is that the answer-bearing message is about the matter the question
asks about. That is not a shortcut; that is the task.
"""

from __future__ import annotations

from random import Random
from typing import Final

#: Openers. Used by filler, by evidence, by decoys - by everything, drawn the same way.
LEAD_INS: Final[tuple[str, ...]] = (
    "Settled, and this is the version to quote.",
    "For the avoidance of doubt.",
    "My own view, for the thread.",
    "Writing this up while it is fresh.",
    "Coming back to this after the standup.",
    "Short version.",
    "For the record.",
    "Chasing this one again.",
    "Apologies for the delay here.",
    "Two things on this.",
    "Just so nobody duplicates work.",
    "Following up on the earlier note.",
    "Noted, and confirmed.",
    "Correcting myself from earlier.",
    "Picking this up while others are out.",
    "Adding what I have.",
    "Straight to it.",
    "Before anyone asks.",
    "This supersedes what I said before.",
    "Same position as last week.",
    "Sorry, late to the thread.",
    "Quick one.",
    "Reading back over this.",
    "Confirming where we landed.",
    "Putting a marker down.",
    "Coming back to the point raised earlier.",
    "One more on this and then I will stop.",
    "Filing this so it is findable.",
    "Attaching what I have on it.",
    "Revisiting this after the review.",
)

#: Closers that undercut the sentence they follow. Used wherever a distractor has to sit after
#: the message it competes with - at the lowest sweep fractions the evidence is the second
#: message of the conversation and nothing can precede it - so that a later contradiction does
#: not read as superseding the answer. Ordinary traffic uses them too.
HEDGES: Final[tuple[str, ...]] = (
    "Going from memory, so check before quoting it.",
    "That was my understanding a while ago; it may have moved.",
    "Do not hold me to that.",
    "I have not checked recently.",
    "Someone with the file should confirm.",
    "Working from an old note here.",
)

#: Lead-ins that assert finality. A distractor competing with an answer in the same
#: conversation must not draw one: an audit found "Settled, and this is the version to quote"
#: opening a stale restatement dated after the evidence, which made the wrong value the most
#: firmly stated thing in the thread.
FINAL_LEAD_INS: Final[frozenset[str]] = frozenset({
    "Settled, and this is the version to quote.",
    "For the avoidance of doubt.",
    "Noted, and confirmed.",
    "This supersedes what I said before.",
    "Confirming where we landed.",
    "Putting a marker down.",
    "As agreed:",
})

CLOSERS: Final[tuple[str, ...]] = (
    "Shout if that is wrong.",
    "Happy to be corrected.",
    "I will put it in the pack.",
    "No action needed from anyone else.",
    "Let me know before Friday.",
    "I will chase them and report back.",
    "Parking it until we hear.",
    "Flagging rather than fixing.",
    "Will confirm once I have seen it in writing.",
    "Leaving it there for now.",
    "Not urgent, just visible.",
    "Say if you want this raised higher.",
    "That is all from me on it.",
    "I would rather we agreed this in the thread than in a call.",
    "Treat that as the position unless someone objects.",
    "The file is in the usual place.",
)

#: The decisive sentence shapes, by what the message is doing. Families draw from these and so
#: does ordinary traffic, about other matters - which is the point. `{fact}` is a rendered
#: statement, `{value}` a bare value, `{formal}` and `{plain}` an entity's two names.
CORES: Final[dict[str, tuple[str, ...]]] = {
    "assert": (
        "{fact}",
        "{fact} That is the position.",
        "Position: {fact}",
        "{fact} Please quote that and not the older figure.",
        "As agreed: {fact}",
        "{fact} I have updated the record.",
    ),
    "propose": (
        "Proposing {value} on {formal}. Nothing is settled.",
        "Suggestion, not a decision: {value} for {formal}.",
        "Could we go with {value} on {formal}? Open to being told no.",
        "Putting {value} on the table for {formal}.",
        "Tabling {value} for {formal} so we have something to argue with.",
        "Straw man for {formal}: {value}.",
    ),
    "object": (
        "I do not think {value} survives contact with the facts. {reason}",
        "I would want to see the numbers before we did that to {formal}. {reason}",
        "Not comfortable with {value} on {formal} as things stand. {reason}",
        "That reads wrong to me for {formal}. {reason}",
        "Pushing back on {value}. {reason}",
        "I have a problem with that for {formal}. {reason}",
    ),
    "remind": (
        "{formal} is down as {value} in tomorrow's pack. Someone tell me if that is stale.",
        "The tracker still shows {value} for {formal}.",
        "Carrying {value} for {formal} into the board pack unless corrected.",
        "For the agenda: {formal} at {value}.",
        "Pack says {value} on {formal}. Flagging in case that moved.",
        "Reminder that {formal} sits at {value} on the current sheet.",
    ),
    "reverse": (
        "Scrap that. {formal} is {value} now.",
        "Change of position on {formal}: {value}, as of this morning.",
        "That is out of date already - {formal} is {value}.",
        "Ignore the above. {formal} stands at {value}.",
        "We have moved on {formal}. {value} is where it sits.",
        "Reversing what I said about {formal}. It is {value}.",
    ),
    "reinforce": (
        "To restate the position on {formal}: {fact}",
        "Confirming again for the record that {fact}",
        "Third time on {formal}, and I would rather this were the last: {fact}",
        "Repeating because it keeps being missed: {fact}",
        "Still true, still the position: {fact}",
        "Saying it again so it is in the thread twice: {fact}",
    ),
    "hearsay": (
        "I spoke to {who} about this and my note says {value}.",
        "{who} told me {value} when I caught them.",
        "Second hand from {who}: {value}.",
        "{who} said {value}, though I am going from memory.",
        "My note from a conversation with {who} says {value}.",
        "Passing on what {who} told me: {value}.",
    ),
    # R-M2-068. These used to number themselves - "Revision 3 of the Harlow schedule: the
    # figure stands at 81" - and the answer key named that ordinal verbatim. Two details then
    # separated the candidates, and the second one was a unique exact-match key: "which
    # revision was adopted" resolved by searching for the string "revision 3". That is F1's
    # mechanism, and while it was there F16 could not show whether a failure was a ranking
    # failure or a retrieval failure. The candidates now differ in the figure and in nothing
    # else, and the confirmation names the figure it signed.
    "revision": (
        "The figure on the {formal} schedule stands at {value}.",
        "{formal} schedule: {value}.",
        "Carrying {value} for {formal}.",
        "{formal} - {value} on the schedule.",
        "Putting {formal} at {value}.",
        "The {formal} schedule figure is {value}.",
    ),
    "adopt": (
        "{value} is the one we adopted for signature on {formal}.",
        "We signed {value} for {formal}. The others were drafted and not taken forward.",
        "{value} went to signature on {formal}; disregard the rest.",
        "The adopted figure for {formal} is {value}.",
        "Signature went on {value} for {formal}.",
        "{value} is the executed figure for {formal}.",
    ),
    "invoice": (
        "Invoice {token} has been raised against {formal} and is sitting in approvals.",
        "{token} is in the approvals queue against {formal}.",
        "Raising {token} against {formal} for this stage.",
        "{formal}: invoice {token} is with finance.",
        "I have put {token} through against {formal}.",
        "{token} covers the {formal} work and is awaiting sign-off.",
    ),
    "nochange": (
        "Nothing on {formal} has moved since my note.",
        "{formal} is where it was last time I wrote.",
        "No change on {formal} to report.",
        "{formal} unchanged since the last update.",
        "Still nothing new on {formal}.",
        "{formal} has not shifted since I last looked.",
    ),
    "charge": (
        "The per-consignment charge that follows from the {formal} decision is {value}.",
        "{formal} works out at {value} per consignment under the new arrangement.",
        "Costing {formal}: {value} a consignment.",
        "That puts {formal} at {value} per consignment.",
        "{value} per consignment is what the {formal} position produces.",
        "The figure that falls out of {formal} is {value} a consignment.",
    ),
    # Every phrasing below names the entity for the same reason: an audit found four
    # reversal-shaped messages in one F17 conversation, three of them ordinary traffic about
    # other matters, and the declared reversal distinguishable only by being the last of them.
    # A decisive sentence that does not say what it is about is not decisive.
    "concur": (
        "I checked with {who} and we are agreed on {formal}.",
        "{who} and I have been over {formal} and we say the same thing.",
        "Spoke to {who}; no daylight between us on {formal}.",
        "{who} agrees with me about {formal}.",
        "Checked with {who}. We are of one mind on {formal}.",
        "{who} has seen this and is content on {formal}.",
    ),
    "stale": (
        "Mine may be behind - I have not synced since the move.",
        "This copy could be out of date; I have not refreshed it.",
        "Caveat: I may not have the latest of these.",
        "Not certain this is current, so check before quoting.",
        "I have not pulled a fresh copy in a while.",
        "Treat this as indicative until someone confirms it is current.",
    ),
    "dated_event": (
        "{event} ran on {on}. Actions out of it are with the owners named on the day.",
        "{event} was held on {on}; the write-ups follow.",
        "We had {event} on {on}. Notes to come.",
        "{event} took place on {on}.",
        "{on} was {event}. Anything agreed there supersedes what came before it.",
        "For the diary: {event} was {on}.",
    ),
    "identity": (
        "Worth saying for anyone new: there are two {name}s here. <{left}> is in {left_team} "
        "and <{right}> is in {right_team}. They are different people.",
        "Careful with {name} - <{left}> and <{right}> are two different people, {left_team} "
        "and {right_team}.",
        "Two {name}s on this list: <{left}> ({left_team}) and <{right}> ({right_team}).",
        "Note for the address book: {name} at <{left}> is {left_team}; {name} at <{right}> is "
        "{right_team}. Not the same person.",
        "We have two people called {name}. <{left}> is {left_team}, <{right}> is {right_team}.",
        "Do not merge these: <{left}> and <{right}> are both {name}, in {left_team} and "
        "{right_team}.",
    ),
    # R-M2-071. Four sentence shapes that used to be written inline by a single builder, and
    # so occurred inside exactly one family in the whole corpus: F14's roster line and its
    # address-change line, F15's forward marker, F13's acceptance. A sentence that only ever
    # appears in one family names that family, whatever else the repair did to the values and
    # the frames. They are banks now, and `chatter.FOIL_KINDS` draws them into ordinary
    # traffic everywhere, which is the same repair the register cues got.
    "roster": (
        "Kicking off {formal}. Everyone on this list is on it for the duration.",
        "{formal}: this is the list, and it does not change while the work runs.",
        "Setting up {formal} with the people who need to be on it throughout.",
        "Everyone copied on {formal} stays copied until it closes.",
        "The distribution for {formal} is fixed from here - nobody drops off partway.",
        "Starting {formal}. Keep the whole list on replies, please.",
    ),
    "address_change": (
        "My address has changed since the start of this thread. The old one is still "
        "receiving and I am not reading it.",
        "New address for me from today; mail to the old one will sit there unread.",
        "I have moved mailbox. The previous address still accepts mail and I do not check it.",
        "Please update me in your address book - the old one is live but unattended.",
        "Writing from the new address. The old one is not dead, it is just not watched.",
        "Note my address changed mid-thread; anything sent to the old one will be missed.",
    ),
    "forwarded": (
        "Original below.",
        "Forwarding on. Original follows.",
        "Passing this along - the original is underneath.",
        "Sending this over, original attached below.",
        "Over to you. Original text below this line.",
        "As received. Original below my note.",
    ),
    "accept": (
        "Accepting that, having raised the objection before {event}. I have no further "
        "concern on {formal}.",
        "That answers what I raised before {event}. Nothing further from me on {formal}.",
        "Content with that. My objection predated {event} and it is addressed.",
        "Withdrawing what I said before {event}; I am satisfied on {formal}.",
        "That settles it for me. I raised it before {event} and I am content now.",
        "Happy with that. The concern I put before {event} is closed on {formal}.",
    ),
    "chase": (
        "Did we ever land this one? I cannot find anything that says we agreed a position on "
        "{formal}.",
        "Has {formal} been settled? I cannot find it written down anywhere.",
        "Where did {formal} get to? There is nothing in the thread that reads like a decision.",
        "Chasing {formal} again - is there an agreed position or not?",
        "Nobody seems to know where {formal} landed. Is it decided?",
        "Still looking for the {formal} decision. Point me at it if it exists.",
    ),
    "plain": (
        "{plain_fact}",
        "{plain_fact} That is where it stands.",
        "Just so it is written down: {plain_fact}",
        "{plain_fact} Nobody has told me otherwise.",
        "Checked this morning - {plain_fact}",
        "{plain_fact} Happy to be told I am behind.",
    ),
    "attach": (
        "Attaching the current schedule for {formal}.",
        "Here is the {formal} sheet as it stands.",
        "{formal} schedule attached. The agreed row is the one that matters.",
        "Sending the {formal} file over.",
        "Attached: {formal}. I am not retyping the figures into the thread.",
        "The {formal} file is attached rather than pasted.",
    ),
}

#: How many sentences a body has, drawn from the same distribution whatever the message is.
#: Filler used to be three sentences and everything decisive one or two, which was itself the
#: label.
SHAPES: Final[tuple[tuple[bool, bool], ...]] = (
    (True, True),
    (True, False),
    (False, True),
    (True, True),
    (False, False),
    (True, True),
    (True, False),
)


def compose(
    core: str,
    rng: Random,
    avoid: frozenset[str] = frozenset(),
    tentative: bool = False,
) -> str:
    """A message body: a core sentence, framed the way every other message is framed.

    `avoid` exists for the paraphrase families. EP §4.5 tier 2 requires a query and its evidence
    to share **no content word**, and the frame is prose: a lead-in like "Confirming where we
    landed" puts the question's own vocabulary into the evidence body and the tier collapses.
    So in those conversations the frame is drawn from the phrasings that share nothing with the
    question - applied to **every** message in the thread, not only the evidence, or the frame
    would start predicting which message is the answer.
    """
    from .world import content_words

    def _usable(pool: tuple[str, ...]) -> tuple[str, ...]:
        if not avoid:
            return pool
        kept = tuple(one for one in pool if not content_words(one) & avoid)
        return kept or pool

    import re

    leads, tails = _usable(LEAD_INS), _usable(CLOSERS)
    if tentative:
        leads = tuple(one for one in leads if one not in FINAL_LEAD_INS) or leads
    lead, tail = SHAPES[rng.randrange(len(SHAPES))]
    parts = []
    if lead:
        parts.append(leads[rng.randrange(len(leads))])
    parts.append(core.strip())
    if tail:
        parts.append(tails[rng.randrange(len(tails))])
    # Colloquial aliases begin with "the", so any template supplying its own article doubles
    # it. Fixed once, here, rather than in each of the seventy-two places a template lives: a
    # generator artefact appearing on one population and not the other is a marker, whichever
    # population it lands on.
    if tentative:
        parts.append(HEDGES[rng.randrange(len(HEDGES))])
    text = re.sub(r"\b([Tt])he the\b", r"\1he", " ".join(parts))
    # A sentence beginning in lower case is a fingerprint: exactly two messages in a corpus had
    # one and both were trap decoys, which an audit reported at precision 1.0.
    return re.sub(
        r"(^|(?<=[.?!]) )([a-z])", lambda one: one.group(1) + one.group(2).upper(), text
    )


#: Core phrasings that claim finality in the sentence itself, not in the opener. A tentative
#: message must avoid these too: an audit found "Please quote that and not the older figure" on
#: a stale restatement whose *opener* had already been made non-final, which put the firmest
#: claim in the thread on the wrong value anyway.
FINAL_CORES: Final[frozenset[str]] = frozenset({
    "{fact} That is the position.",
    "{fact} Please quote that and not the older figure.",
    "As agreed: {fact}",
    "{fact} I have updated the record.",
    "Position: {fact}",
})


def core(kind: str, rng: Random, tentative: bool = False, **slots: object) -> str:
    bank = CORES[kind]
    if tentative:
        bank = tuple(one for one in bank if one not in FINAL_CORES) or bank
    return bank[rng.randrange(len(bank))].format(**slots)


def say(
    kind: str,
    rng: Random,
    avoid: frozenset[str] = frozenset(),
    tentative: bool = False,
    **slots: object,
) -> str:
    return compose(core(kind, rng, tentative, **slots), rng, avoid, tentative)


__all__ = ["CLOSERS", "CORES", "FINAL_CORES", "FINAL_LEAD_INS", "HEDGES", "LEAD_INS", "SHAPES", "compose", "core", "say"]
