"""One thread's structural map: chronological order, the reply forest, the participants.

AD D.6's four signals, computed live from one `threads.get` and from nothing else - no
persistent graph, no second fetch, no state carried between queries (SC §5, contract §7):

  * **temporal** - order and `position` come from the `internalDate` map the observation
    sealed, never from the order Gmail put the array in (C-02c, STR-03, amendment A3);
  * **reply** - `reply_tree.reconstruct`, from RFC headers alone (C-02a, STR-01);
  * **participants** - `participants.index_participants`, keyed on address, authorship kept
    apart from mention (C-02b, STR-02);
  * **position** - exposed on every row (STR-04), and every position in this map is an
    index into `order`, which is what makes `0 <= p < stated_total` true by construction
    rather than by a check somebody has to remember.

**This module derives nothing it was not given.** It takes the position map off the sealed
observation rather than sorting the rows itself, because `_thread_scalars` already ranked
them to compute those positions and a second sort here would be a second derivation of one
fact (R-ARCH-031) - two derivations that can disagree, which is how a row ends up in an
array slot that contradicts the number printed beside it. If the observation declined to
state positions, `build` raises rather than inventing an order; `assemble` catches that one
thread's disposition, exactly as it already does for a thread whose map disagrees with
itself.

**Text is passed in, never fetched.** Mentions are scanned only in text this response
actually observed - a fetched body, or the `snippet` a `threads.get` returned - and a
message with neither is listed as unscanned rather than reported as mentioning nobody.
PF-2 leaves it open whether `format=metadata` returns `snippet` at all, so this is the
difference between a map that degrades honestly under that branch and one that starts
making negative claims from an absence.

**And "observed" now means the whole of what was observed** (R-RETR-051). The sentence
above was true of this module and false of its caller: `assemble` handed over
`processed.default_view`, which is the `original` spans only, so an address inside a quoted
reply or a forwarded block - the commonest mention shape in real mail - was invisible while
`mentions_not_scanned` reported the row as scanned. The participant index was therefore a
function of the thread **and of which rows this query happened to match**, since a matched
row got a body and a stub row got a snippet. The caller passes `body_clean.text` now, which
is A7's own rule - annotate, do not delete - applied to what is *scanned* as well as to what
is shown. The remaining depth dependence is the snippet, and it is a real one: see
`assemble._observed_text`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from mailweave.constants import auth_record_fits, is_an_address
from mailweave.errors import ThreadStructureError
from mailweave.gmail.models import Message
from mailweave.query.analysis import fold
from mailweave.structure.participants import (
    ADDRESS_HEADERS,
    MessageParticipants,
    ObservedText,
    ParticipantIndex,
    addresses_in_header,
    index_participants,
    participants_of_message,
)
from mailweave.structure.reply_tree import ThreadStructure, header_view, reconstruct


def _headers_of(message: Message) -> Mapping[str, str | None] | None:
    """The address headers of one row, or `None` when this response observed none.

    Values are the raw header text. RFC 2047 encoded-words are deliberately not decoded
    here: an encoded-word can only ever encode a *display name*, never the `addr-spec`
    inside the angle brackets, and this module keeps no display names. Decoding would
    change only the strings that are counted and discarded, at the cost of a second text
    transform on a path that must not grow one.
    """
    payload = message.payload
    if payload is None:
        return None
    return {name: payload.header(name) for name in ADDRESS_HEADERS}


@dataclass(frozen=True)
class ThreadMap:
    """The structural map of one thread, in chronological order throughout.

    `order` is the message ids by `internalDate`; `positions` is the inverse. Every list in
    `structure` and `participants` is in this order too, so a caller reading any of them
    reads the thread as it happened rather than as the array arrived.
    """

    thread_id: str
    order: tuple[str, ...]
    positions: Mapping[str, int]
    structure: ThreadStructure
    participants: ParticipantIndex
    #: Ids whose `internalDate` another row of this thread also carries, so their relative
    #: order was settled by message id rather than by time. Carried from the observation
    #: rather than recomputed - one fact, one derivation.
    tied_on_internal_date: tuple[str, ...] = ()
    #: The widest `Authentication-Results` record any row of this thread will carry (INJ-05),
    #: in characters, by `auth_record_of`'s rule - so the width of a map page is a property
    #: of the thread rather than of the rows a call happens to hold (`disclosure.pages`). A
    #: map served from the LRU holds no rows and still knows this, because it travels with
    #: the map.
    auth_record_chars: int = 0
    #: The widest attribution any row of this thread will carry (2026-09-21): the folded
    #: `From` address plus its display name, by `from_header_of`'s rule, **in characters as
    #: the wire escapes them** (2026-09-22: `json.dumps` of each, without its quotes - a name
    #: full of quotes or non-ASCII costs the structured half more than its length, and the
    #: page probe charges it off this figure). The same reason `auth_record_chars` travels
    #: with the map: a page width is a property of the thread, and a map served from the LRU
    #: has no headers in hand.
    attribution_chars: int = 0
    #: The longest display name any address of this thread presented under, in characters
    #: (INJ-05's `{display_name, address}` pair). A length, never a name: what the page width
    #: needs is a bound on what a page's participant index can cost, and it needs it on a map
    #: served from the LRU too, where no header is in hand.
    display_name_chars: int = 0

    @property
    def stated_total(self) -> int:
        return len(self.order)

    @property
    def unresolved_parent_ids(self) -> tuple[tuple[str, str], ...]:
        """`(child id, the Message-ID it named)` for parents this thread does not hold.

        L4's input. A reply whose parent is missing here very often has that parent in
        another thread, which is what a forward, a split thread or a subject change makes.
        """
        return self.structure.unresolved_parent_ids


def snippet_observed_text(messages: Sequence[Message]) -> dict[str, ObservedText]:
    """The text a map-only observation holds for each message: the `snippet`, nothing else.

    One rule, read by `surface.service._observe_thread`, by `handles.redeem` and by the search
    path when it sizes a page (`disclosure.pages`), so the map a `mailweave_thread_map` call
    observes and the map a search names a page of are scanned over the same text - which is
    what makes the page width a property of the thread rather than of who asked (R-M2-081).
    The snippet is declared a truncation, because it is one (R-RETR-052).
    """
    return {
        message.id: ObservedText(text=message.snippet, truncated_at_end=True)
        for message in messages
        if message.snippet
    }


def from_header_of(message: Message) -> tuple[str, str, int]:
    """`(folded address, display name, addresses stated)` the `From` header named, or
    `("", "", 0)` when the headers were not observed or named no addr-spec (2026-09-21).

    One function, read by the row that carries the attribution (`assemble._attribution_of`),
    by the ladder's charge (`PlannedRow.from_address`/`from_display`) and by the map's
    `attribution_chars`, so the estimate, the wire and the page width cannot disagree about
    what a row's attribution costs - the discipline `auth_record_of` set one field over.
    The first address is the one carried; the count says how many the header stated.
    """
    payload = message.payload
    if payload is None:
        return "", "", 0
    named = [
        (display, fold(address))
        for display, address in addresses_in_header(payload.header("From"))
        if is_an_address(address)
    ]
    if not named:
        return "", "", 0
    display, address = named[0]
    return address, display, len(named)


def auth_record_of(message: Message) -> str:
    """This message's `Authentication-Results`, or `""` when the row will carry none.

    One function, read by the ladder's charge, by the row that carries it and by the map's
    `auth_record_chars`, so the estimate, the wire and the page width cannot disagree about
    what this field costs. A record over `MAX_AUTH_RECORD_CHARS` is declared oversize on the
    row and not carried, so it costs nothing here.
    """
    payload = message.payload
    if payload is None:
        return ""
    raw = payload.header("Authentication-Results")
    if not raw or not auth_record_fits(raw):
        return ""
    return raw


def build(
    *,
    thread_id: str,
    messages: Sequence[Message],
    positions: Mapping[str, int],
    observed_text: Mapping[str, ObservedText] | None = None,
    tied_on_internal_date: Sequence[str] = (),
) -> ThreadMap:
    """Build one thread's map from the rows of a `threads.get` and its sealed positions.

    `positions` must place **every** row: the observation states all of them or none of
    them (amendment A6's all-or-nothing rule for a sealed per-id map), so a partial map
    here would mean a position was invented somewhere between the seal and this call.
    `ThreadStructureError` rather than a silent fallback, on amendment A3's own reasoning
    for out-of-range positions: a fallback ordering presented as chronological moves
    evidence just as quietly as clamping does.

    A key of `observed_text` missing for a message means this response holds no text for
    it, which is not the same as holding empty text; `participants_of_message` carries the
    difference and the index declares it.
    """
    texts: Mapping[str, ObservedText] = {} if observed_text is None else observed_text
    unplaced = sorted(message.id for message in messages if message.id not in positions)
    if unplaced:
        raise ThreadStructureError(
            f"a thread map for {thread_id} was asked for while the observation stated no "
            f"chronological position for {unplaced}. A position is a 0-based index into "
            "the thread's chronological order (amendment A3) and this module will not "
            "invent one: an order presented as chronological that is not is the failure "
            "this project exists to prevent"
        )
    ordered = sorted(messages, key=lambda message: positions[message.id])
    records: list[MessageParticipants] = [
        participants_of_message(
            message_id=message.id,
            headers=_headers_of(message),
            observed_text=texts.get(message.id),
        )
        for message in ordered
    ]
    return ThreadMap(
        thread_id=thread_id,
        order=tuple(message.id for message in ordered),
        positions={message.id: positions[message.id] for message in ordered},
        structure=reconstruct(header_view(message) for message in ordered),
        participants=index_participants(records),
        tied_on_internal_date=tuple(tied_on_internal_date),
        auth_record_chars=max((len(auth_record_of(message)) for message in ordered), default=0),
        attribution_chars=max(
            (
                sum(len(json.dumps(part)) - 2 for part in from_header_of(message)[:2])
                for message in ordered
            ),
            default=0,
        ),
        display_name_chars=max(
            (
                len(name)
                for record in records
                for names in record.display_names.values()
                for name in names
            ),
            default=0,
        ),
    )
