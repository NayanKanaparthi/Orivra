"""The address-keyed participant index: authorship, and the three things that are not it.

**Someone quoted in a thread did not write in it.** A retrieval system that confuses the two
answers "who decided this?" wrongly, which is the question the product is for, so this
module keeps four roles apart that a naive index merges into one bag of "people in this
thread" (contract C-02b, AD D.6, rubric STR-02):

  * **author** - the address is the *sole* address of this message's `From`. This is the
    only role that says a person wrote something;
  * **coauthor** - `From` named this address **and others**. RFC 5322 §3.6.2 permits a
    multi-mailbox `From`, and which of them held the pen is not something the headers say.
    Kept as its own role rather than promoted to authorship, because promoting it would
    attribute one person's words to another on the strength of a header shape;
  * **recipient** / **reply_to** - addressed, not authoring. `Reply-To` is a routing
    directive the *sender* asserts, and treating it as authorship would let a sender
    attribute their own message to somebody else by writing one header;
  * **mention** - the address appears in text this response actually observed for the
    message, and in none of that message's address headers. This is hearsay: named,
    quoted or forwarded. STR-02's planted distractor is exactly this row, and scoring it as
    authorship is the failure that criterion exists to catch.

**Identity is the address, never the display name** (C-02b, SN §7.2, INJ-05). A display name
is mail-derived free text a sender chooses, so `From: "Ana Lee" <mallory@elsewhere.invalid>`
is a message authored by `mallory@elsewhere.invalid` and by nobody called Ana. No display
name is ever joined to an address here, matched against a query, or put on the wire: what
survives is `distinct_display_names`, a count, which answers the one question a display name
can honestly answer - *did this address present itself under more than one name?* - without
putting the string anywhere a reader might take it for identity.

**Three things this index says it cannot tell, rather than guessing at them.**

  1. **A bare name in text is not resolved to an address.** "Ana said we should ship" names
     nobody this module will attribute a mention to; only an address-shaped token is a
     mention. Mapping a name to an address needs a directory MailWeave does not have, and
     inventing one is the same class of guess as re-parenting an orphan by date.
     `name_only_mentions_are_not_resolved` is that statement as a constant.
  2. **A message a mention could not be looked for in is not scanned**, and is listed in
     `mentions_unscanned` rather than reported as mentioning nobody. Two ways that happens
     and both are declared the same: no text arrived (PF-2 leaves even `snippet` open), or
     no address headers arrived - and without those a mention is not computable at all,
     since a mention is defined by what this message's own headers do *not* account for.
     "No mention found" would otherwise be a negative derived from an absence, which is the
     defect OD-5 and R-RETR-039 have already found twice on other fields.
  3. **A message with no readable `From` has no author**, and is listed in
     `authorship_unknown`. Not attributed to the previous message's sender, not attributed
     to the thread's root, not attributed at all.

No fixture, header or body text reaches this module's output. Addresses are shape-checked
before they are kept - one line, one `@`, no whitespace, bounded - so a header value that is
really prose cannot travel out of here under a field named `address`, which is the rule
`reasons.py` and the disposition seal already apply to every scalar they carry.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from email.utils import getaddresses
from typing import Final

from mailweave.constants import is_an_address
from mailweave.envelope.vocab import ParticipantRole

#: The address headers this index reads, mapped to the role they confer. `bcc` is absent
#: because Gmail does not return it for a received message and a role nothing can populate
#: is a role a later reader will trust.
FROM: Final[str] = "from"
TO: Final[str] = "to"
CC: Final[str] = "cc"
REPLY_TO: Final[str] = "reply-to"

#: Every header this module reads. Named once so the "which headers were unreadable"
#: declaration below is over the same set the roles are derived from, rather than a second
#: hand-written list that can drift from it.
ADDRESS_HEADERS: Final[tuple[str, ...]] = (FROM, TO, CC, REPLY_TO)

#: An address-shaped token in free text. Deliberately conservative: it will miss obfuscated
#: spellings ("ana at team dot example"), and missing a mention is a smaller error than
#: inventing one, since a mention that is missed is declared nowhere as authorship while a
#: mention invented from prose would put a name on a role it did not earn.
#: The group is non-capturing on purpose: `re.findall` returns the *group* when a pattern
#: has exactly one, so a capturing group here would have matched whole addresses and handed
#: back their domain tails - a defect invisible in any test whose fixture address has a
#: one-label domain.
TEXT_ADDRESS_RE: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9.-]{0,253}[A-Za-z0-9])?"
)

#: Stated as a constant so the claim is executable rather than only written down. A bare
#: display name in text is never resolved to an address (see this module's docstring, 1).
name_only_mentions_are_not_resolved: Final[bool] = True


def addresses_in_header(value: str | None) -> tuple[tuple[str, str], ...]:
    """`(display name, address)` pairs of one address header, lowercased on the address.

    The pair is returned *unjoined*, which is contract C-02b's own word: nothing downstream
    receives a rendered `Ana Lee <ana@team.example>` string it might key on. The display name
    travels only as far as `_index`, which counts distinct names per address and discards
    them.

    Addresses are compared case-insensitively. The domain is case-insensitive by RFC 5321
    and the local part is formally not, but every mail system in practice treats it so, and
    treating `Ana@x` and `ana@x` as two authors would split one person's messages in exactly
    the family STR-02 scores.
    """
    if value is None:
        return ()
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for display, address in getaddresses([value]):
        lowered = address.strip().lower()
        if not is_an_address(lowered) or lowered in seen:
            continue
        seen.add(lowered)
        pairs.append((display.strip(), lowered))
    return tuple(pairs)


@dataclass(frozen=True)
class ObservedText:
    """Text this response holds for one message, and whether it is a **truncation**.

    The pair exists because `addresses_in_text` used to be handed a bare string and treated
    every string as whole (R-RETR-052). A `snippet` is a truncation by construction, so an
    address straddling the cut becomes a *different* address - `cai@team.exampl` for
    `cai@team.example` - which is still address-shaped, so `is_an_address` accepts it, the
    `ThreadParticipant` validator accepts it, and `mentioned_only` reports it as somebody
    the thread talks about. That is a participant identity minted out of a cut string and
    present in no message of the mailbox.

    A truncation boundary is not an address boundary. `truncated_at_end` says the text may
    stop mid-token, and the scanner discards any match that touches the end. Missing a
    mention is the direction this module already declares it prefers; inventing one is not.
    """

    text: str
    #: Whether this text may stop in the middle of a token. True for a `snippet`, which
    #: Gmail cuts at a length rather than at a word, and for any head-truncated view.
    truncated_at_end: bool = False


def addresses_in_text(text: ObservedText | None) -> tuple[str, ...]:
    """Every address-shaped token in observed message text, deduplicated, lowercased.

    This is the mention side, and it reads *text* rather than headers on purpose: a name in
    a body is not an address and is not resolved to one (see this module's docstring). What
    is address-shaped is a fact about the string; what a name refers to is not.

    **A match that touches the end of a truncated text is discarded** (R-RETR-052). The
    regex has no way to know the string it was handed is a prefix of a longer one, so the
    caller carries that fact and this function acts on it. `finditer` rather than `findall`
    for exactly that: the match's *position* is the evidence, and `findall` throws it away.
    """
    if text is None or not text.text:
        return ()
    found: dict[str, None] = {}
    end_of_text = len(text.text)
    for match in TEXT_ADDRESS_RE.finditer(text.text):
        if text.truncated_at_end and match.end() == end_of_text:
            continue
        candidate = match.group().strip(".").lower()
        if is_an_address(candidate):
            found.setdefault(candidate, None)
    return tuple(found)


@dataclass(frozen=True)
class MessageParticipants:
    """What one message's own headers and observed text said about who took part in it.

    `headers_observed` and `text_observed` are the third states this repository now writes
    by reflex: neither "no author" nor "no mentions" is a claim that can be made from an
    absence of observation.
    """

    message_id: str
    authors: tuple[str, ...]
    recipients: tuple[str, ...]
    reply_to: tuple[str, ...]
    mentions: tuple[str, ...]
    headers_observed: bool
    from_header_present: bool
    text_observed: bool

    @property
    def mentions_scanned(self) -> bool:
        """Whether a mention could be looked for in this message at all.

        **Both** facts are needed, and the second one is the subtle half. A mention is an
        address in text that *this message's own address headers do not account for*, so
        without the headers the predicate is not computable: every address in the body would
        look like hearsay, the sender's own included. A row whose headers were never observed
        therefore has its mentions declared unscanned even when a snippet arrived with it -
        which is a narrower statement than "no text", and the two are kept apart rather than
        one standing in for the other.
        """
        return self.headers_observed and self.text_observed

    #: Address headers whose value was present and yielded no address at all. A separate
    #: fact from an absent header, for the reason `reply_headers_present` is.
    unreadable_headers: tuple[str, ...]
    #: How many distinct display names each address presented under, in this message.
    display_names: Mapping[str, frozenset[str]]

    @property
    def author_role(self) -> ParticipantRole | None:
        """`AUTHOR` for a sole `From` address, `COAUTHOR` for several, `None` for neither."""
        if len(self.authors) == 1:
            return ParticipantRole.AUTHOR
        return ParticipantRole.COAUTHOR if self.authors else None


@dataclass(frozen=True)
class ParticipantFacts:
    """Every message of one thread in which one address took each role.

    Five disjoint lists rather than one membership list with a "role" beside it: an address
    can author one message of a thread and be merely mentioned in the next, and a shape that
    cannot express both would force a choice between them - which is how a mention comes to
    be reported as authorship.
    """

    address: str
    authored: tuple[str, ...] = ()
    coauthored: tuple[str, ...] = ()
    addressed: tuple[str, ...] = ()
    reply_to: tuple[str, ...] = ()
    mentioned: tuple[str, ...] = ()
    #: How many distinct display names this address presented under across the thread. One
    #: is ordinary; more than one is the signal INJ-05 is about, and it is reported as a
    #: count because the names themselves are mail-derived text that cannot key an identity.
    distinct_display_names: int = 0

    @property
    def wrote_anything(self) -> bool:
        """The predicate "what did X say" must select on. Authorship only - never mention."""
        return bool(self.authored or self.coauthored)

    def roles_in(self, message_id: str) -> frozenset[ParticipantRole]:
        """Every role this address held in one message. Often more than one.

        The reason `ParticipantRole` exists as a vocabulary rather than only as five field
        names: a caller asking "what was this address, in this message?" gets an answer it
        can branch on. A sender who Ccs themselves is `AUTHOR` and `RECIPIENT` at once, and
        collapsing that to one value would need a precedence rule nobody has a reason for.

        Written against the five lists rather than beside them, so a role this object records
        and this method forgot is not expressible - which is the shape of the defect a second
        hand-maintained mapping would eventually be.
        """
        held = {
            ParticipantRole.AUTHOR: self.authored,
            ParticipantRole.COAUTHOR: self.coauthored,
            ParticipantRole.RECIPIENT: self.addressed,
            ParticipantRole.REPLY_TO: self.reply_to,
            ParticipantRole.MENTION: self.mentioned,
        }
        return frozenset(role for role, messages in held.items() if message_id in messages)


@dataclass(frozen=True)
class ParticipantIndex:
    """One thread's participants, keyed on address, with what could not be told declared."""

    by_address: Mapping[str, ParticipantFacts]
    per_message: tuple[MessageParticipants, ...]
    #: Messages with no readable `From`. Their author is not inferred from anything.
    authorship_unknown: tuple[str, ...]
    #: Messages in which a mention could not be looked for - no text, or no address headers
    #: to tell a mention apart from a participant. Not "no mentions": nothing looked.
    mentions_unscanned: tuple[str, ...]

    @property
    def authors(self) -> tuple[str, ...]:
        """Every address that wrote at least one message of this thread, sorted."""
        return tuple(
            sorted(address for address, facts in self.by_address.items() if facts.wrote_anything)
        )

    @property
    def mentioned_only(self) -> tuple[str, ...]:
        """Addresses this thread only ever *talks about*, sorted. The hearsay set.

        The complement of `authors` restricted to addresses that appear at all, which makes
        it the set STR-02's distractor lands in. Derived from the same records as `authors`
        so no message can be counted in both by two independent derivations.
        """
        return tuple(
            sorted(
                address
                for address, facts in self.by_address.items()
                if facts.mentioned and not facts.wrote_anything
            )
        )

    def wrote(self, address: str) -> tuple[str, ...]:
        """The messages `address` actually authored, in thread order. Empty for a mention."""
        facts = self.by_address.get(address.strip().lower())
        return () if facts is None else facts.authored + facts.coauthored


def participants_of_message(
    *,
    message_id: str,
    headers: Mapping[str, str | None] | None,
    observed_text: ObservedText | None,
) -> MessageParticipants:
    """One message's participation record, from its headers and whatever text was observed.

    `headers is None` means no header was observed for this message at all - the row a
    `threads.get` returned without a `payload` - which is neither "no author" nor "no
    recipients"; it is the third state, and both derived roles are empty with
    `headers_observed=False` beside them saying why.

    `observed_text is None` means this response holds no text for this message, so mentions
    were not looked for. That is not the same as looking and finding none, and the two are
    not merged into one empty tuple: `text_observed` carries the difference.
    """
    if headers is None:
        return MessageParticipants(
            message_id=message_id,
            authors=(),
            recipients=(),
            reply_to=(),
            mentions=(),
            headers_observed=False,
            from_header_present=False,
            # Truthful about the text even though nothing was scanned in it: `text_observed`
            # is a fact about this response, and `mentions_scanned` is the derived question
            # a caller actually has. Reporting `False` here would have made the field say
            # "no text arrived" about a row a snippet arrived with.
            text_observed=observed_text is not None,
            unreadable_headers=(),
            display_names={},
        )
    parsed = {name: addresses_in_header(headers.get(name)) for name in ADDRESS_HEADERS}
    unreadable = tuple(
        name for name in ADDRESS_HEADERS if headers.get(name) is not None and not parsed[name]
    )
    names: dict[str, set[str]] = {}
    for pairs in parsed.values():
        for display, address in pairs:
            if display:
                names.setdefault(address, set()).add(display)
    authors = tuple(address for _display, address in parsed[FROM])
    recipients = tuple(
        dict.fromkeys(address for name in (TO, CC) for _display, address in parsed[name])
    )
    reply_to = tuple(address for _display, address in parsed[REPLY_TO])
    # A mention is an address in the *text* that this message's own address headers do not
    # already account for. Subtracting the headers is what keeps the sender of a message
    # that quotes their own address out of the hearsay set, and it is done here rather than
    # at aggregation time so the per-message record is already disjoint by role.
    in_headers = set(authors) | set(recipients) | set(reply_to)
    mentions = tuple(
        address for address in addresses_in_text(observed_text) if address not in in_headers
    )
    return MessageParticipants(
        message_id=message_id,
        authors=authors,
        recipients=recipients,
        reply_to=reply_to,
        mentions=mentions,
        headers_observed=True,
        from_header_present=headers.get(FROM) is not None,
        text_observed=observed_text is not None,
        unreadable_headers=unreadable,
        display_names={address: frozenset(values) for address, values in names.items()},
    )


def _append(bucket: dict[str, list[str]], address: str, message_id: str) -> None:
    bucket.setdefault(address, []).append(message_id)


def index_participants(records: Iterable[MessageParticipants]) -> ParticipantIndex:
    """Aggregate per-message participation into one address-keyed index for a thread.

    Message order is the caller's - `assemble` passes chronological order - and every list
    in the result preserves it, so `wrote(address)` reads as a sequence of contributions
    rather than a set.
    """
    ordered: tuple[MessageParticipants, ...] = tuple(records)
    authored: dict[str, list[str]] = {}
    coauthored: dict[str, list[str]] = {}
    addressed: dict[str, list[str]] = {}
    replies_to: dict[str, list[str]] = {}
    mentioned: dict[str, list[str]] = {}
    names: dict[str, set[str]] = {}
    for record in ordered:
        role = record.author_role
        for address in record.authors:
            if role is ParticipantRole.AUTHOR:
                _append(authored, address, record.message_id)
            else:
                _append(coauthored, address, record.message_id)
        for address in record.recipients:
            _append(addressed, address, record.message_id)
        for address in record.reply_to:
            _append(replies_to, address, record.message_id)
        for address in record.mentions:
            _append(mentioned, address, record.message_id)
        for address, values in record.display_names.items():
            names.setdefault(address, set()).update(values)
    every: Sequence[str] = sorted(
        set(authored) | set(coauthored) | set(addressed) | set(replies_to) | set(mentioned)
    )
    by_address = {
        address: ParticipantFacts(
            address=address,
            authored=tuple(authored.get(address, ())),
            coauthored=tuple(coauthored.get(address, ())),
            addressed=tuple(addressed.get(address, ())),
            reply_to=tuple(replies_to.get(address, ())),
            mentioned=tuple(mentioned.get(address, ())),
            distinct_display_names=len(names.get(address, ())),
        )
        for address in every
    }
    return ParticipantIndex(
        by_address=by_address,
        per_message=ordered,
        authorship_unknown=tuple(record.message_id for record in ordered if not record.authors),
        mentions_unscanned=tuple(
            record.message_id for record in ordered if not record.mentions_scanned
        ),
    )
