"""Mechanical reasons, as closed types (contract R-03, RR PART-07).

PART-07 forbids a decorative rationale ("relevant", "you may find this useful"). A free
string cannot forbid one, so `reason` is not a free string: it is a discriminated union
of mechanisms, each carrying the parameters that make it checkable, rendered to the wire
string at serialisation time. A decorative reason is unconstructible, and PART-07's
degenerate strategy - a constant reason on every message - is visible as a constant
`kind` with constant parameters rather than hidden inside prose.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, ConfigDict, Field

from mailweave.constants import GMAIL_NUMERIC_ID_RE, MAX_GMAIL_NUMERIC_ID_DIGITS, is_one_line
from mailweave.envelope.vocab import (
    FillComponent,
    FloorDependence,
    FloorRelation,
    RecheckedOperator,
)
from mailweave.sealed_model import SealedModel


class RungId(StrEnum):
    """The rungs of AD A.7. `LR` is recency reconciliation."""

    L0 = "L0"
    L1 = "L1"
    L1B = "L1b"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"
    L6 = "L6"
    LR = "LR"


class ReasonKind(StrEnum):
    GMAIL_QUERY_MATCH = "gmail_query_match"
    RFC822_MSGID = "rfc822msgid"
    REPLY_PARENT_OF = "reply_parent_of"
    REPLY_PARENT_AMBIGUOUS = "reply_parent_ambiguous"
    REPLY_CHILD_OF = "reply_child_of"
    THREAD_MEMBER = "thread_member"
    SEMANTIC_SCORE = "semantic_score"
    HISTORY_ADDITION = "history_addition"
    RECENCY_CONTEXT = "recency_context"
    REQUESTED_BY_ID = "requested_by_id"
    SNIPPET_CONTAINS = "snippet_contains"
    WINDOW_OFFSET = "window_offset"
    QUERY_SCORE_FILL = "query_score_fill"
    FLOOR_PROMOTED = "floor_promoted"


# --- what a reason parameter may be (R-SEC-032, round 10) ---------------------------------
#
# Every field below rendered onto the **disclosed JSON wire** verbatim through `render()`,
# and every one of them was `Field(min_length=1)`: a whole multi-line mail body fitted in
# each of the ten. R-SEC-032 filed the `history_id` case as HIGH because that field name had
# by then been found unchecked at two layers; the same probe run across the file's other
# nine string fields accepted the same body, so the check is written once and applied to all
# of them rather than to the one that was reported.
#
# This is R-SEC-030's finding at the layer above the seal, and it is *more* exposed than the
# seal's version: no seal sits between a `Reason` and `MessageRow`'s `field_serializer`.


def _one_line(value: str) -> str:
    """Refuse a parameter carrying a line break. The predicate is `constants.is_one_line`.

    R-ARCH-031 (round 10, LOW, carried): this function used to contain its own
    `value.splitlines() != [value]`, written out by hand beside `disposition.py`'s identical
    one - in the very round that diagnosed "one shape validated, peers trusted" for the fifth
    time. Round 11 needed the same predicate a third time, in the harness package, and closed
    it: there is one implementation, in the module every layer already imports for the Gmail
    numeric-id shape, and this is the wrapper that turns it into a Pydantic validator.

    Every reason parameter is a single-line scalar by nature - a Gmail query, an id, a header
    value, a model name, a search term. None of them is prose, and a multi-line value under
    any of these names is mail text taking a metadata field's route to the wire. This is the
    floor, not the whole check: a field with a *known shape* gets that shape checked too,
    which is what `_gmail_numeric_id` is.
    """
    if not is_one_line(value):
        raise ValueError(
            "a reason parameter carries a line break. A reason is a mechanism with named "
            "parameters (contract R-03, RR PART-07), and every one of them is a "
            "single-line scalar; a multi-line value is content taking a parameter's route "
            "to the disclosed wire (R-SEC-032, OD-4). Every boundary `str.splitlines()` "
            "recognises counts, not only \\n and \\r (R-SEC-029)"
        )
    return value


def _gmail_numeric_id(value: str) -> str:
    """The decimal shape Gmail actually returns, from the one copy of it (R-SEC-032).

    The regex is imported rather than restated. Round 9 wrote this check for the *seal's*
    `history_id` and round 10 found the reason's field of the same name still taking
    anything - "Please review the attached NDA before end of day." reached
    `model_dump_json()["sources"][0]["messages"][0]["reason"]` verbatim. A second, separately
    written copy of one shape is how the second layer went unchecked, so both layers now
    read the same compiled pattern out of `mailweave.constants`.
    """
    if GMAIL_NUMERIC_ID_RE.match(value) is None:
        raise ValueError(
            f"history_id={value!r} is not the shape Gmail returns. A `historyId` is an "
            "unsigned 64-bit integer rendered as at most "
            f"{MAX_GMAIL_NUMERIC_ID_DIGITS} ASCII decimal digits. This reason renders "
            "straight onto the disclosed wire, so a parameter that accepts prose is a "
            "place mail text is disclosed under a name that says it is metadata "
            "(R-SEC-032, R-SEC-030, OD-4)"
        )
    return value


#: A reason parameter: non-empty and single-line. Named rather than repeated so that a
#: parameter added to a future reason kind gets the check by being annotated at all.
ReasonScalar = Annotated[str, Field(min_length=1), AfterValidator(_one_line)]

#: A reason parameter that is a Gmail numeric id, checked against Gmail's own shape.
GmailNumericId = Annotated[str, Field(min_length=1), AfterValidator(_gmail_numeric_id)]


class _ReasonBase(SealedModel):
    """The base every reason kind extends. Declares no fields, so extending it is allowed.

    `SealedModel` rather than `BaseModel` since round 14: a `Reason` is part of the payload
    that reaches the wire, so a substituted reason class is a substituted reader exactly as a
    substituted `Source` is (R-ARCH-033, R-ARCH-034). It is easy to miss precisely because
    these models live outside `wire.py` - which is what "one shape validated, peers trusted"
    looks like from the inside, and why the sweep in
    `tests/test_standing_cycle_round14.py` walks the tree rather than the module.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    def render(self) -> str:  # pragma: no cover - overridden by every member
        raise NotImplementedError


class GmailQueryMatch(_ReasonBase):
    kind: Literal[ReasonKind.GMAIL_QUERY_MATCH] = ReasonKind.GMAIL_QUERY_MATCH
    query: ReasonScalar
    rung: RungId

    def render(self) -> str:
        return f"gmail q matched at {self.rung.value}: {self.query}"


class Rfc822MsgId(_ReasonBase):
    kind: Literal[ReasonKind.RFC822_MSGID] = ReasonKind.RFC822_MSGID
    message_id_header: ReasonScalar

    def render(self) -> str:
        return f"rfc822msgid: {self.message_id_header}"


class ReplyParentOf(_ReasonBase):
    kind: Literal[ReasonKind.REPLY_PARENT_OF] = ReasonKind.REPLY_PARENT_OF
    child_id: ReasonScalar

    def render(self) -> str:
        return f"reply parent of {self.child_id}"


class ReplyParentAmbiguous(_ReasonBase):
    """The identifier lookup for one child's named parent matched more than one message.

    R-RETR-050. `reply_tree._resolve` already refuses this shape *inside* a thread - "an id
    carried by two messages resolves to nothing: picking either would be a guess dressed as
    a link" - and L4 walked around that refusal by asking Gmail instead: one `Message-ID`
    carried by messages in two threads produced two rows, each disclosed as `reply parent
    of <child>`, and a caller was told two different messages are the parent of one message.

    A child has one reply parent. Where the lookup returns the identifier from more than one
    message, MailWeave cannot tell which one the child named, so the row says what is true -
    it carries the `Message-ID` the child named, and it is one of N that do - and takes
    `Role.CONTEXT` rather than `Role.PARENT`. The ambiguity is a typed parameter rather than
    a sentence, so a reading agent can branch on it.
    """

    kind: Literal[ReasonKind.REPLY_PARENT_AMBIGUOUS] = ReasonKind.REPLY_PARENT_AMBIGUOUS
    child_id: ReasonScalar
    message_id_header: ReasonScalar
    #: How many messages the one `rfc822msgid:` probe returned. Two or more by construction:
    #: a single match is an unambiguous parent and takes `ReplyParentOf`.
    matched_messages: int = Field(ge=2)

    def render(self) -> str:
        return (
            f"named parent of {self.child_id}: Message-ID {self.message_id_header} is "
            f"carried by {self.matched_messages} messages, so which one this reply names "
            "is not determined"
        )


class ReplyChildOf(_ReasonBase):
    kind: Literal[ReasonKind.REPLY_CHILD_OF] = ReasonKind.REPLY_CHILD_OF
    parent_id: ReasonScalar

    def render(self) -> str:
        return f"reply child of {self.parent_id}"


class ThreadMember(_ReasonBase):
    kind: Literal[ReasonKind.THREAD_MEMBER] = ReasonKind.THREAD_MEMBER
    thread_id: ReasonScalar
    position: int = Field(ge=0)

    def render(self) -> str:
        return f"thread map row: position {self.position} of thread {self.thread_id}"


class SemanticScore(_ReasonBase):
    kind: Literal[ReasonKind.SEMANTIC_SCORE] = ReasonKind.SEMANTIC_SCORE
    cosine: float
    model: ReasonScalar

    def render(self) -> str:
        return f"semantic cosine {self.cosine:.2f}, model {self.model}"


class HistoryAddition(_ReasonBase):
    kind: Literal[ReasonKind.HISTORY_ADDITION] = ReasonKind.HISTORY_ADDITION
    history_id: GmailNumericId

    def render(self) -> str:
        return f"history.list messagesAdded since historyId {self.history_id}"


class RecencyContext(_ReasonBase):
    """AD D.9's verbatim provenance for a message LR surfaced.

    **The sentence is fixed by the architecture and is built rather than stored**, out of
    the two facts that vary: the watermark the walk started from, and the constraints the
    closed local re-check actually evaluated. Storing it as a free string would let a caller
    - or a future edit - ship a *paraphrase*, and the half a paraphrase loses is the last
    clause: "free-text terms NOT re-checked - Gmail q did not match this message". Without
    it the row reads as a query match this server never observed (R-03, T-RC3).

    `rechecked` is a closed enum of operator families - not a string tuple - so there is no
    parameter here that caller-derived or mail-derived text can travel through at all, which
    is the shape R-SEC-032 closed for every other reason kind.
    """

    kind: Literal[ReasonKind.RECENCY_CONTEXT] = ReasonKind.RECENCY_CONTEXT
    history_id: GmailNumericId
    rechecked: tuple[RecheckedOperator, ...] = ()

    def render(self) -> str:
        checked = ", ".join(op.value for op in self.rechecked) if self.rechecked else "none"
        return (
            f"history.list messageAdded since {self.history_id}; "
            f"constraints re-checked locally: [{checked}]; "
            "free-text terms NOT re-checked - Gmail q did not match this message"
        )


class RequestedById(_ReasonBase):
    kind: Literal[ReasonKind.REQUESTED_BY_ID] = ReasonKind.REQUESTED_BY_ID
    requested_id: ReasonScalar

    def render(self) -> str:
        return f"requested by id: {self.requested_id}"


class SnippetContains(_ReasonBase):
    kind: Literal[ReasonKind.SNIPPET_CONTAINS] = ReasonKind.SNIPPET_CONTAINS
    term: ReasonScalar

    def render(self) -> str:
        return f"snippet contains '{self.term}'"


class WindowOffset(_ReasonBase):
    kind: Literal[ReasonKind.WINDOW_OFFSET] = ReasonKind.WINDOW_OFFSET
    offset: int
    anchor_id: ReasonScalar

    def render(self) -> str:
        return f"window {self.offset:+d} around {self.anchor_id}"


class QueryScoredFill(_ReasonBase):
    """A.9(3)'s E4 fill: this message is here because the query's own score reached it.

    The row's reason names **which** published components fired and what they summed to, so
    a reader can recompute the decision from `mailweave.disclosure.weights` without trusting
    it. That is DISC-01's requirement stated as a type: an inclusion carries a reason naming
    a mechanism traceable to the query, and the mechanism is an enum rather than prose.

    A fill reason cannot be constructed with no components, because a row no component
    reached is a row the query did not reach, and filling it would be filling by position -
    the fixed window wearing the query-aware policy's name.
    """

    kind: Literal[ReasonKind.QUERY_SCORE_FILL] = ReasonKind.QUERY_SCORE_FILL
    components: tuple[FillComponent, ...] = Field(min_length=1)
    score: int = Field(gt=0)

    def render(self) -> str:
        return (
            f"E4 query score {self.score} from "
            f"{' + '.join(component.value for component in self.components)}"
        )


class FloorPromoted(_ReasonBase):
    """An E2 floor member the promotion rule promoted, and the dependence that promoted it.

    Distinct from `ReplyParentOf` / `ReplyChildOf`, which every floor member carries whether
    or not it was promoted. The difference is the claim: those two say *how this message is
    attached to the evidence*, and this one says *the evidence cannot be read without it*.
    Collapsing them would lose the only visible difference between the floor's absolute half
    and its earned half (OD-3).
    """

    kind: Literal[ReasonKind.FLOOR_PROMOTED] = ReasonKind.FLOOR_PROMOTED
    relation: FloorRelation
    anchor_id: ReasonScalar
    dependence: FloorDependence

    def render(self) -> str:
        return (
            f"reply {self.relation.value} of {self.anchor_id}, and the evidence "
            f"depends on it: {self.dependence.value}"
        )


Reason = Annotated[
    GmailQueryMatch
    | Rfc822MsgId
    | ReplyParentOf
    | ReplyParentAmbiguous
    | ReplyChildOf
    | ThreadMember
    | SemanticScore
    | HistoryAddition
    | RecencyContext
    | RequestedById
    | SnippetContains
    | WindowOffset
    | QueryScoredFill
    | FloorPromoted,
    Field(discriminator="kind"),
]

ALL_REASON_KINDS: frozenset[ReasonKind] = frozenset(ReasonKind)
