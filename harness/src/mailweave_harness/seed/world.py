"""The fictional company the corpus is about, and the calendar it runs on.

Three things live here that used to live nowhere, and each of them is a finding:

*Aliases.* EP §4.5 tier 2 requires a query and its evidence to share **no content word**. An
entity's name is a content word, so a paraphrase family is impossible unless the same thing has
two names. Every `Entity` therefore carries a `formal` name and a `plain` alias, and the corpus
plants messages that establish the pairing, because a query written against an alias the corpus
never introduces is not a hard case, it is an unanswerable one.

*Two registers.* `FORMAL` and `PLAIN` are disjoint vocabularies. A topic renders its fact in
both, so F4's evidence can be written in one and its query in the other with a measurable
jaccard of zero, and F11's trap decoy can be written in the query's own register while saying
something false.

*A calendar.* R-M2-048 was 84 threads out of 84 whose dates ran backwards against position.
Dates are not decoration here: F2 filters on them, F5's reminder has to come after the
confirmation it reminds about, F13 asks what was settled *after* a named review, F16's
superseded drafts have to precede the answer and F17's reversal has to be late. So the world
owns a timeline with named events, and every builder derives its dates from it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Final

DOMAIN: Final[str] = "team.example"


@dataclass(frozen=True)
class Person:
    """One participant. `display` and `address` are separate because F14 needs them to be.

    `SECURITY_NOTES.md` §7.2 and EP §4.7's F14 both turn on a system not confusing a display
    name with an identity, which cannot be tested unless the corpus contains two people who
    share a name and one person who has changed address.
    """

    key: str
    display: str
    address: str
    team: str


@dataclass(frozen=True)
class Entity:
    """A thing the company argues about, under the two names it is argued about by."""

    key: str
    formal: str
    plain: str
    kind: str


@dataclass(frozen=True)
class Event:
    """A dated thing everyone can refer to. F13's queries are anchored on these."""

    key: str
    label: str
    on: dt.date


#: Four people use an initial-and-surname address alongside the two identity traps. Those two
#: were the only short-form addresses in the corpus, which identified F14's traps from the
#: headers without reading the thread.
#: The cast. Two Morgan Reids (different addresses, different teams) are the same-name decoy
#: F14 names; `dana.okafor` and `d.okafor` are one person whose address changed, which is the
#: reply-all bystander problem from the other direction.
PEOPLE: Final[tuple[Person, ...]] = (
    Person("priya", "Priya Raman", f"priya.raman@{DOMAIN}", "operations"),
    Person("marco", "Marco Beltran", f"marco.beltran@{DOMAIN}", "operations"),
    Person("ines", "Ines Duarte", f"ines.duarte@{DOMAIN}", "quality"),
    Person("tomas", "Tomas Novak", f"t.novak@{DOMAIN}", "quality"),
    Person("yuki", "Yuki Hara", f"yuki.hara@{DOMAIN}", "procurement"),
    Person("dana", "Dana Okafor", f"dana.okafor@{DOMAIN}", "procurement"),
    Person("dana_new", "Dana Okafor", f"d.okafor@{DOMAIN}", "procurement"),
    Person("rafi", "Rafi Haddad", f"rafi.haddad@{DOMAIN}", "logistics"),
    Person("lena", "Lena Fischer", f"l.fischer@{DOMAIN}", "logistics"),
    Person("morgan_ops", "Morgan Reid", f"morgan.reid@{DOMAIN}", "operations"),
    Person("morgan_fin", "Morgan Reid", f"m.reid@{DOMAIN}", "finance"),
    Person("sanjay", "Sanjay Iyer", f"sanjay.iyer@{DOMAIN}", "finance"),
    Person("bea", "Bea Lindqvist", f"b.lindqvist@{DOMAIN}", "finance"),
    Person("omar", "Omar Sadiq", f"o.sadiq@{DOMAIN}", "engineering"),
    Person("hana", "Hana Kovac", f"hana.kovac@{DOMAIN}", "engineering"),
    Person("pieter", "Pieter Vos", f"pieter.vos@{DOMAIN}", "engineering"),
)

BY_KEY: Final[dict[str, Person]] = {one.key: one for one in PEOPLE}

#: The two people who share a display name, and the one person with two addresses. Named here
#: rather than rediscovered by string comparison, so the F14 builder and the coverage rule that
#: checks it are reading the same fact.
SAME_NAME_PAIR: Final[tuple[str, str]] = ("morgan_ops", "morgan_fin")
CHANGED_ADDRESS_PAIR: Final[tuple[str, str]] = ("dana", "dana_new")


#: Suppliers, product lines and sites, each under a formal name and the name people actually
#: use in the corridor. The pairing is what makes a zero-overlap paraphrase possible at all.
ENTITIES: Final[tuple[Entity, ...]] = (
    Entity("meridian", "Meridian", "the blue-label line", "product"),
    Entity("cobalt", "Cobalt", "the heavy crate range", "product"),
    Entity("lantern", "Lantern", "the small-batch range", "product"),
    Entity("atlas", "Atlas", "the export pallets", "product"),
    Entity("quarry", "Quarry", "the stoneware run", "product"),
    Entity("pennant", "Pennant", "the retail cartons", "product"),
    Entity("verge", "Verge", "the chilled boxes", "product"),
    Entity("quince", "Quince", "the seasonal packs", "product"),
    Entity("alder", "Alder", "our northern supplier", "supplier"),
    Entity("rowan", "Rowan", "the yard on the river", "supplier"),
    Entity("sorrel", "Sorrel", "the family firm", "supplier"),
    Entity("larch", "Larch", "the new bidder", "supplier"),
    Entity("hazel", "Hazel", "the incumbent", "supplier"),
    Entity("marsden", "Marsden", "the works out west", "site"),
    Entity("calder", "Calder", "the old mill", "site"),
    Entity("fenwick", "Fenwick", "the depot by the bridge", "site"),
    Entity("brightwell", "Brightwell", "the yard we lease", "site"),
    Entity("northdock", "North Dock", "the quayside shed", "site"),
    Entity("tarnbrook", "Tarnbrook", "the hill site", "site"),
    Entity("ashgrove", "Ashgrove", "the unit off the ring road", "site"),
    Entity("dunmore", "Dunmore", "the second warehouse", "site"),
    Entity("everleigh", "Everleigh", "the shared apron", "site"),
    Entity("foxton", "Foxton", "the overflow store", "site"),
    Entity("gilbey", "Gilbey", "the hire yard", "site"),
    Entity("harlow", "Harlow", "the packing hall", "site"),
    Entity("ilminster", "Ilminster", "the cold store", "site"),
    Entity("jarrow", "Jarrow", "the unit we sublet", "site"),
    Entity("kelby", "Kelby", "the third-party shed", "site"),
    Entity("linford", "Linford", "the bonded warehouse", "site"),
    Entity("mowbray", "Mowbray", "the trial floor", "site"),
    Entity("thorne", "Thorne", "the second bidder", "supplier"),
    Entity("wexford", "Wexford", "the firm we dropped", "supplier"),
    Entity("nettleby", "Nettleby", "the annex", "site"),
    Entity("oakfield", "Oakfield", "the long shed", "site"),
    Entity("padstow", "Padstow", "the coastal store", "site"),
    Entity("quenby", "Quenby", "the loading yard", "site"),
    Entity("ryedale", "Ryedale", "the upper floor", "site"),
    Entity("selby", "Selby", "the transit point", "site"),
    Entity("tarlton", "Tarlton", "the firm across the water", "supplier"),
    Entity("ulverton", "Ulverton", "the outside contractor", "supplier"),
)

BY_ENTITY: Final[dict[str, Entity]] = {one.key: one for one in ENTITIES}

#: The timeline. Every date the corpus uses is derived from `EPOCH` plus an offset, so a
#: regenerated corpus is byte-identical and a reader can check an ordering by arithmetic.
EPOCH: Final[dt.date] = dt.date(2025, 7, 1)

EVENTS: Final[tuple[Event, ...]] = (
    Event("september_review", "the September review", dt.date(2025, 9, 18)),
    Event("q4_freeze", "the Q4 change freeze", dt.date(2025, 11, 14)),
    Event("january_audit", "the January audit", dt.date(2026, 1, 22)),
    Event("spring_renewal", "the spring renewal round", dt.date(2026, 3, 12)),
    Event("may_handover", "the May handover", dt.date(2026, 5, 7)),
)

BY_EVENT: Final[dict[str, Event]] = {one.key: one for one in EVENTS}


#: Disjoint registers. Nothing enforces this by construction, so `_the_registers_do_not_overlap`
#: below asserts it at import: a single shared word here would silently make every F4 case a
#: tier-1 case and the family would stop being a falsifier for semantic search.
FORMAL: Final[frozenset[str]] = frozenset(
    {
        "termination", "notice", "period", "agreement", "contractual", "days",
        "inspection", "relocated", "facility", "designated", "site",
        "expenditure", "allocation", "budget", "line", "increased", "revised",
        "certification", "lapsed", "reissued", "compliance", "valid",
        "tolerance", "threshold", "exceeded", "specification", "measured",
        "consignment", "dispatched", "scheduled", "delivery", "window",
        "liability", "indemnity", "clause", "amended", "executed",
        "throughput", "capacity", "constrained", "rated", "utilisation",
        "defect", "attributable", "root", "cause", "determined",
        "escalation", "authorised", "approval", "signatory", "countersigned",
    }
)

PLAIN: Final[frozenset[str]] = frozenset(
    {
        "long", "tell", "walk", "away", "before", "warning", "quit",
        "look", "over", "checking", "moved", "place", "somewhere", "else",
        "spending", "money", "went", "up", "cost", "more", "pay",
        "paperwork", "ran", "out", "sorted", "again", "fine", "good",
        "too", "big", "wide", "off", "outside", "allowed", "reading",
        "boxes", "sent", "arrive", "turn", "late", "early", "when",
        "blame", "fault", "who", "pays", "goes", "wrong", "trouble",
        "how", "much", "fit", "through", "day", "squeeze", "handle",
        "broke", "why", "happened", "started", "traced", "back",
        "say", "yes", "signs", "allowed", "asks", "needs", "boss",
    }
)


def _the_registers_do_not_overlap() -> None:
    shared = FORMAL & PLAIN
    if shared:  # pragma: no cover - import-time guard
        raise AssertionError(
            f"FORMAL and PLAIN share {sorted(shared)}. EP §4.5 tier 2 requires zero "
            "content-word overlap between a query and its evidence, and the paraphrase "
            "families are built by writing one in each register. A shared word makes those "
            "cases tier 1 while the manifest still claims tier 2"
        )


def _people_are_distinct_where_they_must_be() -> None:  # pragma: no cover - import-time guard
    addresses = [one.address for one in PEOPLE]
    if len(set(addresses)) != len(addresses):
        raise AssertionError("two people share an address; F14 joins identity on the address")
    left, right = (BY_KEY[k] for k in SAME_NAME_PAIR)
    if left.display != right.display or left.address == right.address:
        raise AssertionError("SAME_NAME_PAIR must share a display name and differ in address")
    left, right = (BY_KEY[k] for k in CHANGED_ADDRESS_PAIR)
    if left.display != right.display or left.address == right.address:
        raise AssertionError("CHANGED_ADDRESS_PAIR must be one person under two addresses")


def _events_are_ordered() -> None:  # pragma: no cover - import-time guard
    dates = [one.on for one in EVENTS]
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise AssertionError("EVENTS must be strictly increasing; F13 anchors ordering on them")
    # A family that has to open a conversation *before* a named event needs room in front of
    # the earliest one. F13 opens three weeks before its anchor, and with the first event at
    # EPOCH+17 that put a message four days before the corpus began.
    if (EVENTS[0].on - EPOCH).days < 60:
        raise AssertionError(
            "the first event is less than 60 days after EPOCH, leaving no room for a family "
            "that must open a conversation before it"
        )


_the_registers_do_not_overlap()
_people_are_distinct_where_they_must_be()
_events_are_ordered()


def content_words(text: str) -> frozenset[str]:
    """Lowercased alphabetic words of three or more letters, minus a small stoplist.

    Used by the construction checks that assert a paraphrase really is disjoint. It is a
    deliberately crude lemmatiser-free measure: EP §4.5 records `content_word_jaccard` as a
    *measured* property of the generated text, and a measure the generator can reason about
    exactly is worth more here than a better one it cannot.
    """
    import re

    stop = {
        "the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "has", "had",
        "was", "were", "with", "that", "this", "from", "they", "will", "would", "there",
        "their", "what", "about", "which", "been", "have", "our", "your", "his", "her",
        "its", "one", "two", "into", "them", "then", "than", "some", "just", "also", "get",
        "got", "put", "let", "see", "now", "new", "old", "per", "via", "yet", "ref",
    }
    return frozenset(
        word for word in re.findall(r"[a-z]{3,}", text.lower()) if word not in stop
    )


def states(value: str, text: str) -> bool:
    """Whether `text` actually asserts `value`, rather than merely containing its characters.

    Raw containment was wrong in both directions and both showed up. `"20" in "05 August 2026"`
    is true, so a thread whose answer was 20 could mint no date at all; and a decoy carrying
    "143" was read as stating an answer of "43". Every check that asks whether a message states
    a value goes through here.
    """
    import re

    if not value:
        return False
    return re.search(
        rf"(?<![0-9A-Za-z]){re.escape(value)}(?![0-9A-Za-z])", text
    ) is not None


def jaccard(left: str, right: str) -> float:
    a, b = content_words(left), content_words(right)
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


__all__ = [
    "BY_ENTITY", "BY_EVENT", "BY_KEY", "CHANGED_ADDRESS_PAIR", "DOMAIN", "ENTITIES", "EPOCH",
    "EVENTS", "FORMAL", "PEOPLE", "PLAIN", "SAME_NAME_PAIR", "Entity", "Event", "Person",
    "content_words", "jaccard", "states",
]
