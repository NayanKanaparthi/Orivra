"""Hand-written Pydantic models for the four Gmail responses WS-02 parses (AD A.5, B.5).

Shapes are taken from the Gmail API v1 discovery document (`gmail.googleapis.com/$discovery
/rest?version=v1`) and the reference pages for `users.messages.list`, `users.messages.get`,
`users.threads.get`, `users.history.list` and `users.getProfile`. Where a field's *presence*
depends on the `format` requested, this module models it as optional and the question is
registered as a preflight probe rather than answered here - see
`docs/reviews/ROUND_11/HANDOFF.md` for the list. Guessing at a shape and asserting it is
how a fixture suite comes to test the API we imagined.

**One shape, one checker.** Every field that carries a Gmail unsigned-64-bit decimal -
`historyId` on a message, on a thread, on a history record, on a history page and on a
profile; `internalDate` on a message - is annotated with the *same* `GmailNumericId`, which
is `constants.GMAIL_NUMERIC_ID_RE`, which is the identical object the disposition seal and
the transport seam use. This is the round-10 standing check applied at the moment of
writing rather than after: `history_id` has now been found unchecked at three separate
layers, each time because a second copy of one external system's shape was written by hand.
`tests/test_gmail_models.py` enumerates every model field whose name ends `history_id` or
`internal_date` and fails if one of them is not annotated with this type, so the *next*
field of that name cannot be added without the check.
"""

from __future__ import annotations

from typing import Annotated, Any, Final

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError
from pydantic import ValidationInfo as _ValidationInfo

from mailweave.constants import GMAIL_NUMERIC_ID_RE, MAX_GMAIL_NUMERIC_ID_DIGITS
from mailweave.content.payload import Part
from mailweave.envelope.disposition import MAX_SEALED_ID_CHARS, MAX_SEALED_PAGE_TOKEN_CHARS
from mailweave.errors import MailweaveError
from mailweave.validation import failure_summary


class GmailResponseMalformed(MailweaveError):
    """A Gmail response did not have the shape the API documents.

    Raised instead of letting `pydantic.ValidationError` cross the layer (the same rule
    `content/payload.py` follows for `parse_payload`). The message names the endpoint, the
    error count and the failing field *paths* - never the offending values, because a value
    in a Gmail response is mail-derived and AD A.11 keeps mail-derived text out of every
    error string.
    """


def _numeric_id(value: str, info: _ValidationInfo) -> str:
    if GMAIL_NUMERIC_ID_RE.match(value) is None:
        raise ValueError(
            f"{info.field_name} is not the shape Gmail returns: a `historyId` is an "
            "unsigned 64-bit integer and an `internalDate` is milliseconds since the "
            f"epoch, both rendered as at most {MAX_GMAIL_NUMERIC_ID_DIGITS} ASCII decimal "
            "digits (R-SEC-030/032)"
        )
    return value


#: The one checker, shared by every field of this shape in this module.
GmailNumericId = Annotated[str, AfterValidator(_numeric_id)]

#: A Gmail message or thread id, bounded exactly where the disposition seal bounds it.
#:
#: The bound is imported rather than restated. If it were restated, a response whose id was
#: 65 characters would parse here and then be refused by `_sealed_id` as a
#: `DispositionInvariantError` - an *internal* error class, raised because a remote system
#: sent something unexpected. Sharing the constant makes the refusal happen once, at the
#: parse boundary, as a transport error.
GmailId = Annotated[str, Field(min_length=1, max_length=MAX_SEALED_ID_CHARS)]

#: Same reasoning for the opaque continuation token: the seal's floor, at the parse edge.
GmailPageToken = Annotated[str, Field(min_length=1, max_length=MAX_SEALED_PAGE_TOKEN_CHARS)]


class _GmailModel(BaseModel):
    """Frozen, alias-populated, unknown fields ignored.

    `extra="ignore"` rather than `extra="forbid"`: Gmail adds fields to its responses
    without a version bump, and a client that refuses a response because it grew a field is
    a client that breaks on a Tuesday. What matters for this project is that no *unmodelled*
    field can reach anything downstream, which ignoring gives us and forbidding does not
    improve on.

    `hide_input_in_errors` makes the "no mail-derived text in an error" rule true of the
    `ValidationError` itself and not only of the message `parse_response` writes. That
    exception is chained as the cause, so its own rendering reaches a traceback; the
    failing paths and types survive, the response body does not (R-SEC-043's third
    channel, `mailweave.validation`).
    """

    model_config = ConfigDict(
        frozen=True, extra="ignore", populate_by_name=True, hide_input_in_errors=True
    )


class MessageRef(_GmailModel):
    """A row of a `users.messages.list` page.

    The discovery document types these as full `Message` resources, and the reference page
    states that list returns them with **only** `id` and `threadId` populated. Modelled as
    the two fields it documents: a `historyId` here would be a field this project has never
    seen and would be trusted the moment it appeared.
    """

    id: GmailId
    thread_id: GmailId = Field(alias="threadId")


class MessageListPage(_GmailModel):
    """`users.messages.list`.

    `resultSizeEstimate` is modelled because it is in the response and omitting it would
    make the model a claim that it is absent. It is **never used as a truth source**
    (GMAIL-04, RO F1); nothing in this package reads it, and
    `test_result_size_estimate_is_never_read` keeps that true.
    """

    messages: tuple[MessageRef, ...] = ()
    next_page_token: GmailPageToken | None = Field(default=None, alias="nextPageToken")
    result_size_estimate: int | None = Field(default=None, alias="resultSizeEstimate")


class Message(_GmailModel):
    """`users.messages.get`, and a row of a `users.threads.get` response.

    Which fields are populated depends on `format`, and the reference documents that
    dependence only loosely. `historyId`, `internalDate`, `snippet` and `payload` are
    therefore all optional, and **PF-2 exists to find out which of them `format=metadata`
    actually returns** - the Format enum's own text says METADATA returns "only email
    message ID, labels, and email headers" and does not mention `snippet` or `internalDate`,
    while AD D.5's pool design assumes both. That contradiction is a preflight question, not
    something to settle by picking one.
    """

    id: GmailId
    thread_id: GmailId = Field(alias="threadId")
    #: **`None` is "this response stated no labels", which is not "this message has none"**
    #: (round 19, R-RETR-039). It used to default to `()`, so an absent `labelIds` and a
    #: stated empty list were one value by the time `assemble` read it - and every row the
    #: product could produce therefore reported `observed: true`, including rows whose labels
    #: nothing had observed. The response then stated `outside_the_default_mailbox: false`
    #: about a message it knew nothing about, which is a positive claim derived from an
    #: absence and is the class OD-5 exists to end, arriving one layer under the field
    #: written to end it. This is the same absence-versus-zero discipline amendment A6 gives
    #: `observed_internal_dates`, and `MailboxProvenance` has the third state ready for it.
    #:
    #: Whether Gmail ever omits `labelIds` for a message that has labels is a fact about
    #: Gmail (**R-GMAIL**, PF-2 for `format=metadata`). This makes the distinction
    #: representable either way, which is what stops the response from guessing.
    label_ids: tuple[str, ...] | None = Field(default=None, alias="labelIds")
    snippet: str | None = None
    history_id: GmailNumericId | None = Field(default=None, alias="historyId")
    internal_date: GmailNumericId | None = Field(default=None, alias="internalDate")
    size_estimate: int | None = Field(default=None, alias="sizeEstimate")
    payload: Part | None = None


class Thread(_GmailModel):
    """`users.threads.get`.

    `messages` is the whole of PF-1: issue #239 reports that this array can be shorter than
    the thread, and AD F PF-1 makes that a blocking preflight because the evaluation plan
    uses it as ground truth. Nothing in this module can detect the truncation - a short
    array and a short thread look identical from here - which is precisely why it is a probe
    against a real mailbox and not a validator.
    """

    id: GmailId
    snippet: str | None = None
    history_id: GmailNumericId | None = Field(default=None, alias="historyId")
    messages: tuple[Message, ...] = ()


class HistoryMessageAdded(_GmailModel):
    """One `messagesAdded[]` entry. Its `message` carries id / threadId / labelIds."""

    message: MessageRef


class HistoryMessageEvent(_GmailModel):
    """One `messagesDeleted[]`, `labelsAdded[]` or `labelsRemoved[]` entry.

    All three carry the same thing the handle liveness probe reads - *which message, in
    which thread, was touched* - so they are one model rather than three identical ones.
    `messagesAdded` keeps `HistoryMessageAdded` because it has a second, older consumer (the
    LR rung, AD D.9) and merging them would make one model answer to two callers with
    different questions.

    **`labelIds` is deliberately not modelled**, which is this module's own rule applied to
    the field that most invites an exception: the label-change entries carry the ids that
    changed, the liveness probe reports *counts* rather than labels, and a modelled field
    with no consumer is a field the first caller who finds it will trust. `Message.labelIds`
    exists because `MailboxProvenance` reads it; nothing reads these.
    """

    message: MessageRef


class HistoryRecord(_GmailModel):
    """One `history[]` record.

    **All four change types are modelled, and each has a consumer** (WS-06). Until round 21
    only `messagesAdded` was here, because the LR rung (AD D.9) consumes additions and
    nothing else, and a modelled field with no consumer is a field the first caller who
    finds it will trust. The consumer for the other three is AD A.10's handle liveness
    probe, which asks `history.list` for `messageAdded`, `messageDeleted`, `labelAdded` and
    `labelRemoved` together: a handle says "these threads have not changed", and a thread
    whose message was deleted or whose labels moved *has* changed. Reading only additions
    would make `handle_stale` a claim about one of the four ways the mailbox can move under
    a handle, stated as though it covered all four.
    """

    id: GmailNumericId
    messages_added: tuple[HistoryMessageAdded, ...] = Field(default=(), alias="messagesAdded")
    messages_deleted: tuple[HistoryMessageEvent, ...] = Field(default=(), alias="messagesDeleted")
    labels_added: tuple[HistoryMessageEvent, ...] = Field(default=(), alias="labelsAdded")
    labels_removed: tuple[HistoryMessageEvent, ...] = Field(default=(), alias="labelsRemoved")


class HistoryPage(_GmailModel):
    """`users.history.list`.

    The top-level `historyId` is the watermark to store for the next call (AD D.9). An
    expired `startHistoryId` produces a 404, which is a *declared re-baseline*, not a
    failure - handled in `client.py`, not here.
    """

    history: tuple[HistoryRecord, ...] = ()
    next_page_token: GmailPageToken | None = Field(default=None, alias="nextPageToken")
    history_id: GmailNumericId | None = Field(default=None, alias="historyId")


class Profile(_GmailModel):
    """`users.getProfile`. The account-pinning and profile-derivation input (AD A.4, B.9)."""

    email_address: str = Field(alias="emailAddress", min_length=1)
    messages_total: int | None = Field(default=None, alias="messagesTotal")
    threads_total: int | None = Field(default=None, alias="threadsTotal")
    history_id: GmailNumericId | None = Field(default=None, alias="historyId")


#: Every model this module parses a *response* into. `parse_response` is generic over it and
#: the reflection test in `tests/test_gmail_models.py` walks it, so a model added here
#: without the shared numeric-id annotation fails the suite.
RESPONSE_MODELS: Final[tuple[type[_GmailModel], ...]] = (
    MessageRef,
    MessageListPage,
    Message,
    Thread,
    HistoryMessageAdded,
    HistoryMessageEvent,
    HistoryRecord,
    HistoryPage,
    Profile,
)


def parse_response[ModelT: _GmailModel](model: type[ModelT], raw: Any, *, endpoint: str) -> ModelT:
    """Validate one Gmail response body, or raise `GmailResponseMalformed`.

    The only supported way to turn a decoded Gmail JSON body into a model in this package.
    It exists so that no `pydantic.ValidationError` - a third-party exception shape nothing
    here catches - crosses the client boundary, which is the same rule `parse_payload`
    already applies one layer down.
    """
    try:
        return model.model_validate(raw)
    except ValidationError as failure:
        raise GmailResponseMalformed(
            f"{endpoint} returned a body that does not match the documented shape: "
            f"{failure.error_count()} validation error(s) at "
            f"{failure_summary(model, failure)}. "
            "Values are omitted from this message on purpose: a Gmail response is "
            "mail-derived and no mail-derived text appears in an error (AD A.11)"
        ) from failure
