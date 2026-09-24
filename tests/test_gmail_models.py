"""The response models, and the standing check on every new validator (round 11).

The standing check, carried from the foundation: **"one shape validated, peers trusted" has
appeared six times.** Each time, one field of an external system's shape was checked and the
identically-shaped field beside it was not, because the second check was written by hand and
then not written again.

WS-02 is where that pattern would recur most easily: `historyId` appears on a message, on a
thread, on a history record, on a history page and on a profile - five fields, one shape,
five chances to check four of them. So the checks here are **enumerated by mechanism**: the
tests below walk the models' own field annotations and fail if a field of that shape is
missing the shared validator, which means the sixth field cannot be added without it.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, cast, get_args, get_origin

import pytest
from annotated_types import MaxLen
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from mailweave.constants import GMAIL_NUMERIC_ID_RE
from mailweave.envelope.disposition import MAX_SEALED_ID_CHARS, MAX_SEALED_PAGE_TOKEN_CHARS
from mailweave.gmail.models import (
    RESPONSE_MODELS,
    GmailNumericId,
    GmailResponseMalformed,
    HistoryPage,
    HistoryRecord,
    Message,
    MessageListPage,
    MessageRef,
    Profile,
    Thread,
    parse_response,
)

#: The one checker object, pulled off the shared annotation rather than re-created. If the
#: models ever grow a *second* numeric checker, this marker will not be on it and the
#: partition test below will report the field as unbounded content - which is the failure
#: mode worth having, since a second hand-written copy of one external shape is the exact
#: defect this project has now found three times.
NUMERIC_CHECKER = get_args(GmailNumericId)[1]

#: String-typed fields that carry mail-derived text and are bounded by nothing. This set is
#: asserted **exactly**, so adding a fourth is a deliberate line in a diff.
DECLARED_CONTENT_FIELDS = {
    ("Message", "snippet"),
    ("Thread", "snippet"),
    ("Profile", "email_address"),
    ("Message", "label_ids"),
}


def _metadata(annotation: Any, info: Any) -> list[Any]:
    """Every constraint attached to a field, wherever pydantic put it.

    Pydantic flattens `Annotated[...]` metadata onto `FieldInfo.metadata` for a required
    field and leaves it inside the union for an optional one. A test that read only
    `info.metadata` would report every optional field as unconstrained - and would therefore
    pass while checking nothing, which is the shape of vacuous guard this suite keeps
    finding.
    """
    found: list[Any] = list(info.metadata)
    stack = [annotation]
    while stack:
        node = stack.pop()
        if get_origin(node) is Annotated:
            arguments = get_args(node)
            found.extend(arguments[1:])
            stack.append(arguments[0])
            continue
        if get_origin(node) is not None:
            stack.extend(get_args(node))
    # A `Field(...)` inside an `Annotated` arrives as a nested `FieldInfo` holding its own
    # constraint list, so the constraints on `GmailPageToken` sit one level deeper than the
    # ones on `GmailId`. Writing this walker without that step made an optional bounded field
    # look unbounded - the same "the shape I checked is not the shape it is stored in"
    # mistake this test exists to catch, committed inside the test itself on the first pass.
    for item in list(found):
        nested = getattr(item, "metadata", None)
        if nested and not isinstance(item, MaxLen):
            found.extend(nested)
    return found


def _is_string_typed(annotation: Any) -> bool:
    stack = [annotation]
    while stack:
        node = stack.pop()
        if node is str:
            return True
        if get_origin(node) is not None:
            stack.extend(get_args(node))
    return False


def every_field() -> list[tuple[type[BaseModel], str, Any]]:
    found: list[tuple[type[BaseModel], str, Any]] = []
    for model in RESPONSE_MODELS:
        for name, info in model.model_fields.items():
            found.append((model, name, info))
    return found


def test_every_string_field_is_numeric_shaped_bounded_or_declared_content() -> None:
    """The standing check, mechanised as a **total partition** rather than a name match.

    "One shape validated, peers trusted" has appeared six times, and every instance was a
    field that a name-based sweep did not think to look at - `HistoryRecord.id` in these very
    models carries Gmail's numeric shape under a name that ends in neither `history_id` nor
    `internal_date`. So the check does not ask "are the fields I thought of checked?". It
    asks of **every string-typed field in every response model**: is it numeric-shaped, is it
    length-bounded, or is it on the declared-content list? A new field is in exactly one of
    those three buckets or this test fails, whatever it is called.
    """
    numeric: set[tuple[str, str]] = set()
    bounded: set[tuple[str, str]] = set()
    unclassified: set[tuple[str, str]] = set()
    for model, name, info in every_field():
        if not _is_string_typed(info.annotation):
            continue
        key = (model.__name__, name)
        metadata = _metadata(info.annotation, info)
        if any(item is NUMERIC_CHECKER for item in metadata):
            numeric.add(key)
        elif any(isinstance(item, MaxLen) for item in metadata):
            bounded.add(key)
        else:
            unclassified.add(key)

    assert unclassified == DECLARED_CONTENT_FIELDS, (
        "a string field is neither numeric-shaped nor length-bounded nor declared content: "
        f"{sorted(unclassified - DECLARED_CONTENT_FIELDS)}"
    )
    # And the two checked buckets are not empty, so the partition is not passing vacuously.
    assert len(numeric) >= 6
    assert len(bounded) >= 5


def test_the_numeric_bucket_holds_every_field_of_that_shape_including_the_odd_name() -> None:
    """`HistoryRecord.id` is the peer a name-based sweep misses. It is named here on purpose."""
    numeric = {
        (model.__name__, name)
        for model, name, info in every_field()
        if any(item is NUMERIC_CHECKER for item in _metadata(info.annotation, info))
    }
    assert numeric == {
        ("Message", "history_id"),
        ("Message", "internal_date"),
        ("Thread", "history_id"),
        ("HistoryRecord", "id"),
        ("HistoryPage", "history_id"),
        ("Profile", "history_id"),
    }


def test_the_numeric_shape_is_the_same_object_the_seal_and_the_seam_use() -> None:
    """Not an equal pattern - the same one. Two copies are how the third layer got missed."""
    import mailweave.gmail.models as models_module

    # Read out of the module's namespace rather than imported: it is deliberately not
    # re-exported, and the assertion here is about object identity, not about the import.
    assert models_module.__dict__["GMAIL_NUMERIC_ID_RE"] is GMAIL_NUMERIC_ID_RE


@pytest.mark.parametrize(
    ("model", "payload", "field"),
    [
        (Message, {"id": "m", "threadId": "t", "historyId": "not a number"}, "historyId"),
        (Message, {"id": "m", "threadId": "t", "internalDate": "17356896e5"}, "internalDate"),
        (Thread, {"id": "t", "historyId": "12\n34"}, "historyId"),
        (HistoryRecord, {"id": "Please review the attached NDA."}, "id"),
        (HistoryPage, {"historyId": "١٣"}, "historyId"),  # Arabic-Indic digits: isdigit() is True
        (Profile, {"emailAddress": "a@b.example", "historyId": "-1"}, "historyId"),
    ],
)
def test_prose_and_near_misses_are_refused_wherever_the_shape_appears(
    model: type[BaseModel], payload: dict[str, Any], field: str
) -> None:
    with pytest.raises(GmailResponseMalformed):
        parse_response(model, payload, endpoint="test")  # type: ignore[type-var]


def test_ids_are_bounded_at_the_same_width_the_seal_bounds_them() -> None:
    """Sharing the constant means the refusal happens once, at the parse edge.

    If the bound were restated here, a 65-character id would parse and then be refused by
    `_sealed_id` as a `DispositionInvariantError` - an *internal* error class, raised because
    a remote system sent something unexpected. That is the wrong error for the wrong reason
    in the wrong place.
    """
    too_long = "x" * (MAX_SEALED_ID_CHARS + 1)
    with pytest.raises(GmailResponseMalformed):
        parse_response(MessageRef, {"id": too_long, "threadId": "t"}, endpoint="test")
    with pytest.raises(GmailResponseMalformed):
        parse_response(
            MessageListPage,
            {"messages": [], "nextPageToken": "t" * (MAX_SEALED_PAGE_TOKEN_CHARS + 1)},
            endpoint="test",
        )


def test_a_malformed_response_names_the_field_path_and_never_the_value() -> None:
    """AD A.11: a Gmail response is mail-derived, so no value from it reaches an error."""
    with pytest.raises(GmailResponseMalformed) as raised:
        parse_response(
            Thread,
            {"id": "t1", "messages": [{"id": "m1", "threadId": "t1", "snippet": 4711}]},
            endpoint="users.threads.get",
        )
    rendered = str(raised.value)
    assert "messages.0.snippet" in rendered
    assert "4711" not in rendered


def test_unknown_fields_are_ignored_rather_than_refused() -> None:
    """Gmail adds fields without a version bump; refusing one breaks the client on a Tuesday."""
    page = parse_response(
        MessageListPage,
        {"messages": [{"id": "m", "threadId": "t", "aNewFieldGoogleAdded": 1}], "future": True},
        endpoint="users.messages.list",
    )
    assert page.messages[0].id == "m"


def test_every_response_model_is_frozen_and_alias_populated() -> None:
    for model in RESPONSE_MODELS:
        assert model.model_config.get("frozen") is True, model.__name__
        assert model.model_config.get("populate_by_name") is True, model.__name__


def test_the_camel_case_aliases_match_the_discovery_document_spelling() -> None:
    """A wrong alias is silent: the field defaults and the data is dropped on the floor."""
    expected = {
        (MessageRef, "thread_id", "threadId"),
        (MessageListPage, "next_page_token", "nextPageToken"),
        (MessageListPage, "result_size_estimate", "resultSizeEstimate"),
        (Message, "label_ids", "labelIds"),
        (Message, "internal_date", "internalDate"),
        (Message, "size_estimate", "sizeEstimate"),
        (HistoryRecord, "messages_added", "messagesAdded"),
        (Profile, "email_address", "emailAddress"),
        (Profile, "messages_total", "messagesTotal"),
        (Profile, "threads_total", "threadsTotal"),
    }
    for model, field, alias in expected:
        declared = cast(type[BaseModel], model)
        assert declared.model_fields[field].alias == alias, f"{model.__name__}.{field}"


def test_a_field_with_no_default_is_a_field_gmail_always_sends() -> None:
    """Optionality is a claim about the API, so the required set is asserted rather than read.

    Each of these is required because the reference documents it as always present on the
    resource; anything whose presence depends on `format` has a default, which is how PF-2's
    open questions stay open in the type system instead of being answered by a `Field(...)`.
    """
    required = {
        (model.__name__, name)
        for model in RESPONSE_MODELS
        for name, info in model.model_fields.items()
        if info.default is PydanticUndefined and info.default_factory is None
    }
    assert required == {
        ("MessageRef", "id"),
        ("MessageRef", "thread_id"),
        ("Message", "id"),
        ("Message", "thread_id"),
        ("Thread", "id"),
        ("HistoryMessageAdded", "message"),
        # WS-06: the three other `history[]` change lists. A record that names no message is
        # not a change this probe can attribute to a thread, so `message` is required for the
        # same reason it is required on an addition.
        ("HistoryMessageEvent", "message"),
        ("HistoryRecord", "id"),
        ("Profile", "email_address"),
    }


def test_the_numeric_regex_refuses_a_trailing_newline() -> None:
    """`\\A`/`\\Z` rather than `^`/`$`, and the reason is the round-10 finding it came from."""
    assert GMAIL_NUMERIC_ID_RE.match("99120034\n") is None
    assert re.compile(r"^[0-9]{1,20}$").match("99120034\n") is not None
