"""JWZ / IMAP-REFERENCES reply-tree reconstruction (AD D.6, contract C-02a, WS-05).

**The one rule this module exists to keep: a parent is a fact read off the child's own
RFC 5322 reply headers, or there is no parent.** Gmail's thread membership is looser than
RFC threading - it will file a forward, a subject-changed reply or a message it merely
believes related into one thread - so a thread routinely contains messages the reply
headers cannot link. Those are *declared*, never attached to whatever happened to arrive
before them. A guess that looks like a fact is the defect this project exists to prevent,
one level down from the message omission it started with (STR-01's own named "dumbest
max" is exactly the guess: link everything to the previous message by date).

**`reconstruct` never sees a date.** Not "does not use dates" as a discipline, but as a
signature: `MessageHeaderView` carries ids and header values and nothing else, so
date-adjacent re-parenting is not something this function declines to do, it is something
it cannot do. `test_the_reconstruction_cannot_see_the_order_it_is_given` executes that by
permuting the input and comparing the whole result, over generated threads rather than one
hand-written one, and `test_the_reconstruction_is_not_given_anything_it_could_order_by`
reads the same claim off the type, so it fails when such a field is *added* rather than
when something starts using it.

**What every shape has in common** - and this is the property the tests assert, rather than
a list of cases (broken headers, subject change mid-thread, forwards, orphans, cycles,
self-references, duplicate `Message-ID`s, a reference to a message not in the thread):

  1. every message of the thread gets **exactly one** `Link`, and its `linkage` is one
     member of the closed `Linkage` vocabulary;
  2. a link either **names a parent that is a message of this same thread**, under a
     `Message-ID` that (a) literally appears among this child's own `In-Reply-To` /
     `References` values and (b) is the `Message-ID` that parent carries - or it names **no
     parent at all** and its `linkage` says which gap it is;
  3. following `parent_id` upward from any message terminates: the result is a forest;
  4. the whole result is invariant under permutation of the input.

`test_every_reply_tree_shape_keeps_the_four_properties_that_make_it_not_a_guess` asserts
all four over generated threads, so they hold for shapes nobody wrote a fixture for - which
is this project's answer to "one shape validated, peers trusted".

**The gap vocabulary is derived from what the headers said, never from where the message
sits.** `Linkage.NO_REPLY_HEADERS` carries AD D.6's published string verbatim -
`"date-adjacent (no RFC reply headers)"` - and it covers the thread's genuine root and a
message Gmail added by subject alike, because *by RFC headers those two are the same
message*: neither names a parent. MailWeave does not distinguish them, and a caller that
wants to can read `position == 0`. Inventing the distinction would be the guess.

**AD D.4a's missing-`Message-ID` case, and the one place this module reads it narrowly.**
D.4a says a missing `Message-ID` "yields `linkage: 'no Message-ID'` ... never a guessed
parent". `Linkage.NO_MESSAGE_ID` is that value, and it is given to the message about which
that sentence is the whole story: no `Message-ID` observed *and* no parent named. Where a
message carries no `Message-ID` but its own `In-Reply-To` names a parent this thread holds,
the link is stated and `Link.can_be_a_parent` is `False` beside it. That is a deliberate
reading, recorded rather than glossed: refusing a link the child's own headers support
would discard evidence that was actually read, and D.4a's clause forbids *guessing* a
parent, which stating a header-backed one is not. `can_be_a_parent` is the other half of
the same fact - it says that any reply to this message will arrive unlinked however
well-formed the reply is.

**And that half now reaches the caller** (R-RETR-054). It said "is the half a caller needs"
while the field never left this module: on the wire a `Message-ID`-less message was
byte-identical to an ordinary linked reply, and its own well-formed child reported *"named
parent is not in this thread"* about a parent that is in this thread. `MessageRow` carries
`can_be_a_parent` with its third state, and `MessageRow`'s validator holds `None` to
`Linkage.HEADERS_UNOBSERVED` exactly, so the field cannot be quietly omitted from a row
whose headers were read. The reading is the one R-RETR ruled for; what changed is that the
fact it rests on is now readable.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from mailweave.envelope.vocab import RESOLVED_LINKAGES, Linkage
from mailweave.errors import ThreadStructureError
from mailweave.gmail.models import Message

#: An RFC 5322 `msg-id`, as it appears inside `In-Reply-To` and `References`. Angle
#: brackets are required: a bare token in one of those headers is not a `msg-id`, and
#: accepting one would let arbitrary header text become a link target.
MSG_ID_RE: Final[re.Pattern[str]] = re.compile(r"<[^<>\s]{1,900}>")

#: The two headers a reply names its parent in. `References` is right-to-left: the
#: rightmost entry is the nearest ancestor (RFC 5322 s3.6.4).
IN_REPLY_TO: Final[str] = "in-reply-to"
REFERENCES: Final[str] = "references"
MESSAGE_ID: Final[str] = "message-id"


def message_ids_in(value: str | None) -> tuple[str, ...]:
    """Every `<msg-id>` token in one header value, in wire order, deduplicated.

    Written as an extraction rather than a parse because these headers arrive broken in
    the field: comma-separated, wrapped, carrying a client's commentary, or empty. What is
    extractable is extractable; what is not yields an empty tuple and the caller declares
    the gap instead of guessing at the remainder.
    """
    if value is None:
        return ()
    seen: dict[str, None] = {}
    for match in MSG_ID_RE.findall(value):
        seen.setdefault(match, None)
    return tuple(seen)


@dataclass(frozen=True)
class MessageHeaderView:
    """The threading headers of one message, exactly as one Gmail response stated them.

    `headers_observed` is the third state, and it is here for the reason
    `MailboxProvenance.observed` is (round 19, R-RETR-039): a `threads.get` that returned
    no `payload` for a row - which is what PF-2 suspects `format=metadata` may do - has
    said nothing about that message's reply headers, and "this response did not see them"
    is a different fact from "this message names no parent". Collapsing the two would let
    the response report `no RFC reply headers` about a message whose headers nothing read.

    `reply_headers_present` is a **presence** fact and is carried separately because it
    cannot be recovered from the extracted tuples: a header whose value no `msg-id` can be
    extracted from yields `()`, and that is not the same fact as a header that is absent.
    Merging them would report AD D.6's "no RFC reply headers" about a message that carried
    them and wrote them badly, which is a different defect with a different repair.
    """

    message_id: str
    rfc_message_id: str | None
    in_reply_to: tuple[str, ...]
    references: tuple[str, ...]
    headers_observed: bool
    reply_headers_present: bool

    @property
    def names_a_parent(self) -> bool:
        return bool(self.in_reply_to or self.references)


def header_view(message: Message) -> MessageHeaderView:
    """The threading headers of one `threads.get` message row.

    A row with no `payload` has had **no** header observed, which is not the same as a row
    whose headers were read and carried no `In-Reply-To`. The first cannot be linked *or*
    declared unlinked honestly; the second can.
    """
    payload = message.payload
    if payload is None:
        return MessageHeaderView(
            message_id=message.id,
            rfc_message_id=None,
            in_reply_to=(),
            references=(),
            headers_observed=False,
            reply_headers_present=False,
        )
    own = message_ids_in(payload.header(MESSAGE_ID))
    return MessageHeaderView(
        message_id=message.id,
        rfc_message_id=own[0] if own else None,
        in_reply_to=message_ids_in(payload.header(IN_REPLY_TO)),
        references=message_ids_in(payload.header(REFERENCES)),
        headers_observed=True,
        reply_headers_present=(
            payload.header(IN_REPLY_TO) is not None or payload.header(REFERENCES) is not None
        ),
    )


@dataclass(frozen=True)
class Link:
    """One message's place in the reconstructed reply tree.

    `evidence` is the `Message-ID` the link was made from, or - when no parent was found -
    **the nearest ancestor this child's own headers name**: `In-Reply-To`'s first entry when
    it has one, else the *last* `References` entry, which is the same right-to-left reading
    of `References` that `_resolve` uses one branch above (RFC 5322 s3.6.4).

    It said "the one it was looked for under" and held `(in_reply_to + references)[0]`,
    which for a `References`-only child is the **leftmost** entry - the thread root, the
    farthest ancestor, and the *last* id `_resolve` would have tried rather than the first
    (R-RETR-049). That mattered one level out rather than here: this field is what
    `unresolved_parent_ids` hands L4, and the message L4 brought back was disclosed as the
    child's *reply parent*. A docstring wider than the code is the defect class this project
    is about, and this one was wider by three hops.

    It is a `msg-id` token and nothing else - single-line, angle-bracketed, bounded - which
    is what keeps a header field from becoming a route for mail text onto the wire
    (R-SEC-030/032, the same rule `reasons.py` applies).

    `can_be_a_parent` is whether this message carries a `Message-ID` of its own. It is a
    fact about *other* messages' prospects rather than about this one's link: a message with
    no `Message-ID` cannot be named by any reply, so every reply to it arrives unlinked and
    the response should say why (AD D.4a). `None` when no headers were observed at all,
    which is the third state again - not knowing is not the same as not having one.
    """

    message_id: str
    parent_id: str | None
    linkage: Linkage
    evidence: str | None
    can_be_a_parent: bool | None

    @property
    def linked(self) -> bool:
        return self.linkage in RESOLVED_LINKAGES


@dataclass(frozen=True)
class ThreadStructure:
    """The reconstructed forest of one thread: one `Link` per message, in input order."""

    links: tuple[Link, ...]

    @property
    def by_id(self) -> Mapping[str, Link]:
        return {link.message_id: link for link in self.links}

    @property
    def linked(self) -> int:
        return sum(1 for link in self.links if link.linked)

    @property
    def unlinked(self) -> int:
        return len(self.links) - self.linked

    @property
    def children_of(self) -> Mapping[str, tuple[str, ...]]:
        """Each parent's children, in input order. The other direction of `parent_id`.

        Derived rather than stored, so the two directions of one edge cannot disagree -
        the same rule `Source` follows when it writes its own `thread_id` onto every row.
        """
        children: dict[str, list[str]] = {}
        for link in self.links:
            if link.parent_id is not None:
                children.setdefault(link.parent_id, []).append(link.message_id)
        return {parent: tuple(ids) for parent, ids in children.items()}

    @property
    def unresolved_parent_ids(self) -> tuple[tuple[str, str], ...]:
        """`(child id, the Message-ID it names)` for every parent this thread does not hold.

        This is the input L4's structural expansion probes with: a reply whose parent is
        not in this thread very often has that parent in *another* thread, which is what a
        forward, a split thread or a subject change produces. The pair is returned rather
        than the bare id so the row the expansion is *for* travels with it and the
        recovered message can carry a mechanical `reply parent of <child>` reason.
        """
        return tuple(
            (link.message_id, link.evidence)
            for link in self.links
            if link.linkage is Linkage.UNRESOLVED_PARENT and link.evidence is not None
        )

    @property
    def gaps(self) -> tuple[tuple[str, Linkage], ...]:
        """`(message id, the gap)` for every message this thread could not link.

        The declared-gap enumeration, in input order. `assemble` puts each message's own
        entry on its own row; this is the thread-level view of the same facts, derived from
        the same links so the two cannot say different things.
        """
        return tuple((link.message_id, link.linkage) for link in self.links if not link.linked)


def _resolve(
    named: Sequence[str], holders: Mapping[str, tuple[str, ...]]
) -> tuple[str | None, str | None, bool]:
    """The first named `msg-id` this thread holds exactly one message under.

    Returns `(parent id, the msg-id it was found under, whether an ambiguous id was seen)`.
    An id carried by **two** messages resolves to nothing: picking either would be a guess
    dressed as a link, and duplicate `Message-ID`s are a real shape (a resend, a mailing
    list, a client bug). The ambiguity is reported so the caller can declare it rather than
    report the weaker "not in this thread", which would be false.

    **Two narrower readings this function makes, recorded rather than left to be
    rediscovered** (R-RETR-057). Neither invents a parent - every candidate considered is an
    id this child's own headers name - and both are executed by
    `test_the_two_narrowings_resolve_makes_are_the_ones_its_docstring_states`:

      * an `In-Reply-To` naming **two different** ids that this thread holds resolves to the
        **first**, silently. RFC 5322 s3.6.4 permits a multi-id `In-Reply-To`, and both ids
        are parents the child itself named, so taking the earliest is a reading of the
        headers in the order the sender wrote them rather than a choice between two
        candidates the headers do not rank. It is *not* the same question as one id carried
        by two messages, where the thread - not the child - is what supplies the second
        candidate, and where the child's headers therefore say nothing about which;
      * an `ambiguous` raised by an earlier candidate is **dropped** when a later candidate
        resolves uniquely. The link that results is header-backed and correct; what a caller
        cannot see is that a duplicate `Message-ID` was seen on the way to it. Carrying that
        out would need a field on `Link` and on `ThreadStructureReport`, which is a
        disclosure change rather than a reconstruction one.
    """
    ambiguous = False
    for candidate in named:
        held = holders.get(candidate, ())
        if len(held) == 1:
            return held[0], candidate, ambiguous
        if len(held) > 1:
            ambiguous = True
    return None, None, ambiguous


def _members_of_a_cycle(parents: Mapping[str, str]) -> frozenset[str]:
    """Every node that lies **on** a cycle of the parent map.

    A node that merely leads into a cycle keeps its parent: its own link is backed by its
    own headers and is not the false one. Which edge *inside* a cycle is false is not
    knowable from the headers, so every edge on the cycle is refused rather than one of
    them being picked - the same answer this module gives everywhere else it cannot tell.
    A self-reference is the one-node case and needs no separate rule.
    """
    on_cycle: set[str] = set()
    settled: set[str] = set()
    for start in parents:
        if start in settled:
            continue
        path: list[str] = []
        seen: dict[str, int] = {}
        node: str | None = start
        while node is not None and node not in settled and node not in seen:
            seen[node] = len(path)
            path.append(node)
            node = parents.get(node)
        if node is not None and node in seen:
            on_cycle.update(path[seen[node] :])
        settled.update(path)
    return frozenset(on_cycle)


def _gap_before_resolution(view: MessageHeaderView) -> Linkage | None:
    """The gap this message is in before any lookup is attempted, or `None` to look.

    Three refusals ahead of the lookup, in the order the facts become available:

      * headers nothing observed - neither linkable nor declarable parentless;
      * no reply header at all - AD D.6's orphan, narrowed to `NO_MESSAGE_ID` when this
        message carries no `Message-ID` either, since then nothing structural is known
        about it in either direction (AD D.4a);
      * reply headers present and no `<msg-id>` readable in them.
    """
    if not view.headers_observed:
        return Linkage.HEADERS_UNOBSERVED
    if not view.reply_headers_present:
        return Linkage.NO_MESSAGE_ID if view.rfc_message_id is None else Linkage.NO_REPLY_HEADERS
    if not view.names_a_parent:
        return Linkage.UNPARSEABLE_REPLY_HEADERS
    return None


def reconstruct(views: Iterable[MessageHeaderView]) -> ThreadStructure:
    """Reconstruct one thread's reply tree from RFC headers alone.

    The resolution order is IMAP-REFERENCES': `In-Reply-To` first, then `References`
    right-to-left, since the rightmost reference is the nearest ancestor. A `Message-ID`
    this thread does not hold is **not** a parent, and the message is declared unlinked
    with the id it named - which is both the honest disposition and the input L4 needs to
    go and look for that parent in another thread.

    Three refusals at resolution time, and they are the shapes a naive JWZ implementation
    silently mangles:

      * an id **two** messages carry resolves to neither (`AMBIGUOUS_PARENT`);
      * a link that closes a cycle - including a message referencing itself - is refused
        for every member of that cycle (`REPLY_CYCLE`), because the headers do not say
        which edge is the false one;
      * a message whose headers were **not observed** is neither linked nor declared
        parentless (`HEADERS_UNOBSERVED`); this response saw nothing to say either.

    Raises `ThreadStructureError` when two views carry the same Gmail message id. Every
    guarantee above is per message, and two rows under one id have no single answer to any
    of them; the caller decides that thread's disposition rather than this function quietly
    collapsing the pair.
    """
    ordered = tuple(views)
    distinct = {view.message_id for view in ordered}
    if len(distinct) != len(ordered):
        raise ThreadStructureError(
            f"a reply tree was asked for over {len(ordered)} message rows carrying "
            f"{len(distinct)} distinct Gmail message ids. Every guarantee this module "
            "makes is per message - exactly one link, one linkage, one parent - and two "
            "rows under one id have no single answer to any of them"
        )
    holders: dict[str, list[str]] = {}
    for view in ordered:
        if view.rfc_message_id is not None:
            holders.setdefault(view.rfc_message_id, []).append(view.message_id)
    held: Mapping[str, tuple[str, ...]] = {msg_id: tuple(ids) for msg_id, ids in holders.items()}

    drafts: dict[str, Link] = {}
    for view in ordered:
        parentable = None if not view.headers_observed else view.rfc_message_id is not None
        gap = _gap_before_resolution(view)
        if gap is not None:
            drafts[view.message_id] = Link(
                message_id=view.message_id,
                parent_id=None,
                linkage=gap,
                evidence=None,
                can_be_a_parent=parentable,
            )
            continue
        # **The nearest ancestor this child's own headers name**, which is the same
        # right-to-left rule `_resolve` applies one branch below: `In-Reply-To` first, else
        # the *last* `References` entry (RFC 5322 s3.6.4). It used to be `named[0]` - the
        # *leftmost* reference, which for a `References`-only child is the thread root, the
        # farthest ancestor (R-RETR-049). That id is what `unresolved_parent_ids` hands L4,
        # so L4 probed for the root and `assemble` then disclosed what came back as the
        # child's *reply parent*: a relation the headers do not state, at the one place
        # C-02d requires the relation to be named exactly.
        nearest = view.in_reply_to[0] if view.in_reply_to else view.references[-1]
        parent, found_under, ambiguous = _resolve(view.in_reply_to, held)
        kind = Linkage.IN_REPLY_TO
        if parent is None:
            parent, found_under, from_refs = _resolve(tuple(reversed(view.references)), held)
            ambiguous = ambiguous or from_refs
            kind = Linkage.REFERENCES
        if parent is not None:
            drafts[view.message_id] = Link(
                message_id=view.message_id,
                parent_id=parent,
                linkage=kind,
                evidence=found_under,
                can_be_a_parent=parentable,
            )
            continue
        drafts[view.message_id] = Link(
            message_id=view.message_id,
            parent_id=None,
            linkage=Linkage.AMBIGUOUS_PARENT if ambiguous else Linkage.UNRESOLVED_PARENT,
            evidence=nearest,
            can_be_a_parent=parentable,
        )

    parents = {
        link.message_id: link.parent_id for link in drafts.values() if link.parent_id is not None
    }
    for member in _members_of_a_cycle(parents):
        drafts[member] = Link(
            message_id=member,
            parent_id=None,
            linkage=Linkage.REPLY_CYCLE,
            evidence=drafts[member].evidence,
            can_be_a_parent=drafts[member].can_be_a_parent,
        )
    return ThreadStructure(links=tuple(drafts[view.message_id] for view in ordered))
