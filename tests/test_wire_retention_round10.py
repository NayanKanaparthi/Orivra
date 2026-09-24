"""Round 10: the reason layer's parameters, and the two credential-store sweep items.

**R-SEC-032, HIGH.** `HistoryAddition.history_id` was `Field(min_length=1)`, and
`MessageRow` renders a reason straight onto the disclosed JSON wire through a
`field_serializer`. A reviewer built a real `Envelope` and read

    payload["sources"][0]["messages"][0]["reason"]
    'history.list messagesAdded since historyId Please review the attached NDA before end of day.'

This is R-SEC-030 unfinished rather than adjacent work: the same field name, the same
missing check, one layer up, and **more** exposed than the seal's copy because no seal sits
in between. The fix is the shape check round 9 already wrote, imported rather than
rewritten - two separately written copies of one shape is how the second layer went
unchecked in the first place.

**The sweep the finding asked for.** Running the reviewer's probe across the other nine
string parameters in `reasons.py` accepted the same multi-line body in every one of them:
`query`, `message_id_header`, `child_id`, `parent_id`, `thread_id`, `model`,
`requested_id`, `term`, `anchor_id`. Ten of ten. So the floor is applied to all ten and
tested over the vocabulary rather than over the one field that was reported - a test that
walks `ReasonKind` fails when an eleventh kind arrives without the check.

**R-SEC-034 / R-SEC-035**, both LOW, both in `auth/tokenstore.py`: `obtained_at` was the
only unvalidated timestamp beside two `parse_instant`-checked peers, and
`sweep_orphaned_temporaries` crashed on a filename `int()` rejects while its own docstring
promised "every error is swallowed".

No personal mail content appears here. Every sentence is invented for this repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast, get_args

import pytest
from pydantic import BaseModel, SecretStr, ValidationError

from mailweave.auth.tokenstore import StoredCredentials, TokenStore, _process_is_alive
from mailweave.constants import MAX_GMAIL_NUMERIC_ID_DIGITS
from mailweave.envelope import (
    DispositionLedger,
    EnvelopeBuilder,
    Outcome,
    RungId,
    Sufficiency,
)
from mailweave.envelope.reasons import ALL_REASON_KINDS, HistoryAddition, Reason
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import (
    FillComponent,
    FloorDependence,
    FloorRelation,
    RecheckedOperator,
)
from mailweave.envelope.wire import MessageRow
from mailweave.errors import SecretDocumentMalformed
from mailweave.retrieval.transport import RecordingListTransport
from tests.fixtures import envelope_kit as kit

#: The reviewer's payload, unchanged from round 9: one line, 49 characters, no `\n` or `\r`.
#: It cleared every check on the way to the disclosed wire under a metadata field name.
SNIPPET = "Please review the attached NDA before end of day."

#: Three lines of prose. Round 9 used this shape against the seal's id fields; round 10's
#: sweep put it through every reason parameter, and all ten accepted it.
MAIL_TEXT = (
    "Thanks for the update on this.\n"
    "Once the negotiations concluded, the legal team wrote:\n"
    "We should have a decision by end of week either way.\n"
)

#: A single U+2028 is enough. It is a line break `str.splitlines()` knows about and a scan
#: for `\n`/`\r` does not, which is why the check asks the runtime (R-SEC-029).
TWO_SENTENCES = "Line one Line two - the real second sentence"


def _envelope_with_reason(reason: Reason) -> Envelope:
    """One disclosed row carrying `reason`, built through the production types.

    Deliberately a whole `Envelope` rather than a bare `render()` call: the finding is that
    the sentence reaches `model_dump_json`, and a test that stops at `render()` is testing
    one layer short of the claim.
    """
    ledger = DispositionLedger()
    ledger.record_list_page(
        kit.fetched(["m1"], thread="t1"), rung=RungId.L1, query="from:amy launch"
    )
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    builder.add_source(
        kit.source("t1", [kit.row("m1", "t1", 0, nonce=builder.fence_nonce, reason=reason)])
    )
    return builder.build(
        outcome=Outcome.ANSWERED,
        rungs=(RungId.L1,),
        sufficiency=Sufficiency.SUFFICIENT,
        counters=kit.counters(),
    )


def _reason_models() -> tuple[type[BaseModel], ...]:
    """Every member of the `Reason` union, read off the union rather than listed.

    The annotation is `Annotated[A | B | ..., Field(discriminator=...)]`, so the members are
    `get_args(get_args(Reason)[0])`. Reading them this way is what makes the sweep below
    cover an eleventh reason kind the day it is added instead of the day someone remembers.
    """
    union = get_args(Reason)[0]
    return tuple(get_args(union))


def _string_parameters(model: type[BaseModel]) -> tuple[str, ...]:
    """The string-typed parameters of one reason kind, `kind` excluded.

    `kind` is the discriminator - a `Literal` - not a parameter, and it is the one string
    on these models that cannot carry a caller's value.
    """
    return tuple(
        name
        for name, info in model.model_fields.items()
        if name != "kind" and info.annotation is str
    )


#: Parameter types through which no caller-supplied text can reach the disclosed wire: an
#: integer, a float, or a closed vocabulary. A reason kind built only from these is
#: text-free by construction, which is what `test_the_sweep_covers_every_reason_kind_and_
#: every_string_parameter` asserts of the kinds it has no string parameter to sweep.
_TEXT_FREE_ANNOTATIONS: tuple[object, ...] = (
    int,
    float,
    RungId,
    FloorRelation,
    FloorDependence,
    tuple[FillComponent, ...],
    # AD D.9's closed local re-check subset, carried by `RecencyContext`. A closed enum for
    # the same reason `FillComponent` is one: it is a place no caller value can reach.
    tuple[RecheckedOperator, ...],
)


def _other_parameters(model: type[BaseModel], omit: str) -> dict[str, Any]:
    """Valid values for every parameter of `model` except `omit`, so one can be attacked."""
    filled: dict[str, Any] = {}
    for name, info in model.model_fields.items():
        if name in {"kind", omit}:
            continue
        annotation = info.annotation
        if name == "history_id":
            filled[name] = "99120034"
        elif name == "score":
            # `QueryScoredFill` exists only for a row at least one published component
            # reached, so its own model floors the score above zero (DISC-01). A generic `0`
            # would make every probe here fail on the wrong field, exactly as it would for
            # `matched_messages` below.
            filled[name] = 4
        elif name == "matched_messages":
            # `ReplyParentAmbiguous` exists only for the shape where an identifier named more
            # than one message, so its own model floors this at 2 (R-RETR-050). A generic `0`
            # would make every probe here fail on the wrong field.
            filled[name] = 2
        elif name == "thread_id":
            # `ThreadMember` is what a stub row's reason is, and `Source` checks the row's
            # thread against its own (R-DISC-011), so this one has to be the fixture's thread.
            filled[name] = "t1"
        elif annotation is str:
            filled[name] = "m1"
        elif annotation is int:
            filled[name] = 0
        elif annotation is float:
            filled[name] = 0.5
        elif annotation is RungId:
            filled[name] = RungId.L1
        elif annotation is FloorRelation:
            filled[name] = FloorRelation.PARENT
        elif annotation is FloorDependence:
            filled[name] = FloorDependence.QUOTATION
        elif annotation == tuple[RecheckedOperator, ...]:
            # `RecencyContext.rechecked`. Closed, like `components` below.
            filled[name] = (RecheckedOperator.PARTICIPANT,)
        elif annotation == tuple[FillComponent, ...]:
            # WS-11's `QueryScoredFill.components`. A closed vocabulary rather than a
            # string, which is the point: this parameter is a place no caller value can
            # reach, and the sweep below asserts that rather than skipping it.
            filled[name] = (FillComponent.TERM_OVERLAP,)
        else:  # pragma: no cover - a parameter type this helper has not met
            raise AssertionError(f"{model.__name__}.{name}: {annotation!r} has no probe value")
    return filled


def _a_dead_pid() -> int:
    """A PID that names no live process right now, found rather than assumed.

    Hard-coding a large number would make this test depend on the host's PID space: the
    sweep's whole rule is "only collect a leftover whose writer is gone", so the fixture has
    to actually be gone.
    """
    for candidate in range(4_194_303, 4_000_000, -1):
        if not _process_is_alive(candidate):
            return candidate
    raise AssertionError("no free PID found")  # pragma: no cover - a saturated PID space


# --- R-SEC-032: the reviewer's reproduction, end to end ------------------------------------


def test_the_reviewers_sentence_cannot_be_made_into_a_history_addition_reason() -> None:
    """The reproduction, at its first door. Before the fix this constructed cleanly."""
    with pytest.raises(ValidationError, match="not the shape Gmail returns"):
        HistoryAddition(history_id=SNIPPET)


def test_the_reviewers_sentence_cannot_reach_the_disclosed_wire_by_the_deserialised_route() -> None:
    """A reason arriving as JSON goes through the same validator as one constructed in code.

    Worth its own case: the constructor is not the only door into a Pydantic model, and a
    check that only guards the keyword form guards half the field.
    """
    with pytest.raises(ValidationError, match="not the shape Gmail returns"):
        MessageRow.model_validate(
            {
                "id": "m1",
                "position": 0,
                "role": "matched",
                "reason": {"kind": "history_addition", "history_id": SNIPPET},
                "depth": "stub",
                "unabridged": {
                    "tool": "mailweave_get_messages",
                    "args": {"message_ids": ["m1"], "view": "body_full"},
                },
            }
        )


def test_a_history_addition_that_is_a_real_history_id_still_reaches_the_wire() -> None:
    """The check closes a channel; it must not close the field.

    The number Gmail returns is what the reason is *for*, so the positive case is asserted
    against the disclosed payload rather than assumed from the negative ones.
    """
    envelope = _envelope_with_reason(HistoryAddition(history_id="99120034"))
    payload = json.loads(envelope.model_dump_json())
    assert payload["sources"][0]["messages"][0]["reason"].endswith("historyId 99120034")


@pytest.mark.parametrize(
    "value",
    [
        SNIPPET,
        TWO_SENTENCES,
        "99120034 and a sentence after it",
        "12.34",
        "-1",
        "0x1f",
        " 99120034",
        "99120034 ",
        "99120034\n",
        "١٣",
        "²",
        "１２３",
        "9" * (MAX_GMAIL_NUMERIC_ID_DIGITS + 1),
    ],
    ids=lambda v: repr(v)[:24],
)
def test_the_reason_refuses_every_near_miss_the_seal_refuses(value: str) -> None:
    """The same eleven near-misses round 9 wrote for the seal, plus prose, against the reason.

    Two of these are the point rather than padding. `"99120034\\n"` is accepted by
    `^[0-9]{1,20}$`, because Python's `$` also matches before a trailing newline - in the
    seal that quirk is pre-filtered by `_sealed_scalar` running first, so the shared pattern
    is anchored with `\\A`/`\\Z` and does not depend on its caller's ordering. And `"١٣"`,
    `"²"` and `"１２３"` are all `str.isdigit() is True`: writing the check as "digits" would
    have put this project's own recurring defect inside the fix for it.
    """
    with pytest.raises(ValidationError, match="not the shape Gmail returns"):
        HistoryAddition(history_id=value)


# --- the sweep: every reason parameter, not the one that was reported ----------------------


def test_the_sweep_covers_every_reason_kind_and_every_string_parameter() -> None:
    """The coverage claim, checked rather than asserted.

    Without this the two probes below silently stop covering the vocabulary the moment an
    eleventh `ReasonKind` is added - the same "the mechanism exists but nothing keeps it
    complete" shape R-DISC-004 filed against the render tests.
    """
    models = _reason_models()
    assert {model.model_fields["kind"].default for model in models} == ALL_REASON_KINDS
    swept = {model.__name__: _string_parameters(model) for model in models}
    # **A kind with no string parameter is not skipped; it is a stronger statement, and it
    # is asserted as one** (WS-11). `QueryScoredFill` carries a closed component vocabulary
    # and an integer, so there is no field on it a caller's text can reach at all - which is
    # what the two probes below are trying to establish for the kinds that *do* carry
    # strings. Round 10's version asserted `all(params)`, which would have made a
    # text-free reason kind fail a test written to catch text-carrying ones.
    for model in models:
        if swept[model.__name__]:
            continue
        for name, info in model.model_fields.items():
            if name == "kind":
                continue
            assert info.annotation in _TEXT_FREE_ANNOTATIONS, (
                f"{model.__name__}.{name} is neither a swept string parameter nor one of the "
                f"closed types no caller text can travel through: {info.annotation!r}"
            )
    # 13 until `RecencyContext` arrived with a `history_id` of its own; its `rechecked`
    # list is a closed enum and is not a string parameter, which is the point of the enum.
    assert sum(len(params) for params in swept.values()) == 14


@pytest.mark.parametrize("model", _reason_models(), ids=lambda m: m.__name__)
def test_no_reason_parameter_accepts_a_multi_line_mail_body(model: type[BaseModel]) -> None:
    """The reviewer's probe, run at every string parameter of every reason kind.

    Before this round all ten accepted `MAIL_TEXT` and rendered it verbatim onto the wire.
    Only `history_id` was reported, because only `history_id` had been found unchecked at
    another layer; the finding's own instruction was to sweep for the same missing check
    anywhere else, and here it was, nine more times in the same file.
    """
    for parameter in _string_parameters(model):
        for probe in (MAIL_TEXT, TWO_SENTENCES):
            with pytest.raises(ValidationError) as refusal:
                model(**{parameter: probe}, **_other_parameters(model, parameter))
            assert parameter in str(refusal.value), (
                f"{model.__name__}.{parameter} was refused without naming the field"
            )


@pytest.mark.parametrize("model", _reason_models(), ids=lambda m: m.__name__)
def test_every_reason_parameter_is_still_empty_refusing(model: type[BaseModel]) -> None:
    """The round-1 `min_length=1` floor survives being re-annotated, per parameter."""
    for parameter in _string_parameters(model):
        with pytest.raises(ValidationError):
            model(**{parameter: ""}, **_other_parameters(model, parameter))


@pytest.mark.parametrize("model", _reason_models(), ids=lambda m: m.__name__)
def test_no_reason_kind_puts_a_line_break_on_the_disclosed_wire(model: type[BaseModel]) -> None:
    """The property stated over the payload rather than over the constructor.

    A reason is the only free-text-shaped thing a `MessageRow` renders, so "no rendered
    reason spans two lines" is a statement about the wire a reader can check without knowing
    which validator produced it - and it is asserted for every kind, through a real
    `Envelope`, not for the one kind the finding named.
    """
    reason = cast(Reason, model(**_other_parameters(model, omit="")))
    payload = json.loads(_envelope_with_reason(reason).model_dump_json())
    rendered = payload["sources"][0]["messages"][0]["reason"]
    assert rendered.splitlines() == [rendered]
    assert rendered.strip()


# --- the third layer the sweep found: the transport seam's outbound history id -------------


@pytest.mark.parametrize(
    "value",
    [SNIPPET, MAIL_TEXT, "", "hist-99120034", "99120034\n"],
    ids=lambda v: repr(v)[:24],
)
def test_the_transport_seam_refuses_a_start_history_id_that_is_not_one(value: str) -> None:
    """The same field name, a third time, in a third module.

    `history_id` was found unchecked in the seal (R-SEC-030, round 9) and in the reason that
    renders to the wire (R-SEC-032, round 10). The work order's instruction was to assume a
    third until it had been looked for: `RecordingListTransport.list_history_additions` takes
    one as a parameter and passed it straight to the fetcher.

    Lower stakes than the other two and said so plainly: this value goes **out** to Gmail, not
    onto the disclosed wire, so a wrong one costs an HTTP 400. It is checked because "two of
    the three are checked" is the pattern, not because this one is a disclosure route.
    """
    transport = RecordingListTransport(
        lambda *, query, page_size, page_token: kit.fetched(["m1"]),
        fetch_history=lambda *, start_history_id, page_token: kit.history_additions(["m1"]),
    )
    with pytest.raises(ValueError, match="not the shape Gmail returns"):
        transport.list_history_additions(DispositionLedger(), start_history_id=value)


def test_the_transport_seam_still_records_a_real_history_page() -> None:
    """The check must not close the seam."""
    ledger = DispositionLedger()
    transport = RecordingListTransport(
        lambda *, query, page_size, page_token: kit.fetched(["m1"]),
        fetch_history=lambda *, start_history_id, page_token: kit.history_additions(
            ["m1", "m2"], thread="t1"
        ),
    )
    assert transport.list_history_additions(ledger, start_history_id="9001") == 2
    assert ledger.hit_ids == {"m1", "m2"}


# --- R-SEC-034: the unvalidated timestamp beside two validated ones ------------------------


@pytest.mark.parametrize(
    "value",
    [SNIPPET, "not-a-real-timestamp-at-all", "2026-08-30T14:02:11", ""],
    ids=lambda v: repr(v)[:28],
)
def test_the_credential_stores_obtained_at_is_an_instant_like_its_peers(value: str) -> None:
    """`Source.fetched_at` and `Source.verified_at` are `parse_instant`-checked; this was not.

    The fifth appearance of "one shape validated, its peers trusted" in this project. Lower
    stakes than R-SEC-032 - the credential file is local, never disclosed, and nothing reads
    this field back today - which is exactly why it is the kind of field that stays
    unchecked until it has a consumer.

    A value with no UTC offset is refused too: an instant without one is ambiguous by the
    amount a "when did we obtain this" stamp is about.

    **Round 12: the exception type changed and the check did not.** `StoredCredentials` is a
    `SecretBearingModel` since R-SEC-043, so every construction path - `model_validate`,
    `model_validate_json` and this keyword constructor - converts Pydantic's report, which
    quotes the input it refused, into a `SecretDocumentMalformed` that names the field and
    the error type only. The field is still refused for the same four values; what is gone
    is the rendering that would have printed a refresh token mistakenly stored here.
    """
    with pytest.raises(SecretDocumentMalformed):
        StoredCredentials(
            client_id="client",
            refresh_token=SecretStr("refresh"),  # a placeholder, not a credential
            salt_hex="ab" * 32,
            obtained_at=value,
        )


def test_a_real_instant_is_still_accepted_and_still_round_trips(tmp_path: Path) -> None:
    """The check must not close the field: a stored credential still saves and loads."""
    store = TokenStore(path=tmp_path / "credentials.json")
    credentials = StoredCredentials(
        client_id="client",
        refresh_token=SecretStr("refresh"),  # a placeholder, not a credential
        salt_hex="ab" * 32,
        obtained_at=kit.FETCHED_AT,
    )
    store.save(credentials)
    assert store.load().obtained_at == kit.FETCHED_AT


# --- R-SEC-035: the sweep that crashed while promising it could not ------------------------


#: Digit systems `str.isdigit()` accepts and `_temporary_name` never writes. The first
#: raises inside `int()`; the other two are *accepted* by `int()`, which is why the guard is
#: ASCII rather than merely crash-free - see the test below.
NON_ASCII_DIGIT_OFFSETS = {"superscript": None, "arabic-indic": 0x0660, "fullwidth": 0xFF10}


def _in_digits(number: int, offset: int | None) -> str:
    """`number` spelled in a non-ASCII digit system, or the superscript that `int()` refuses."""
    if offset is None:
        return "\u00b2"
    return "".join(chr(offset + int(digit)) for digit in str(number))


@pytest.mark.parametrize("system", sorted(NON_ASCII_DIGIT_OFFSETS), ids=lambda s: s)
def test_the_orphan_sweep_survives_a_pid_field_that_int_rejects(
    tmp_path: Path, system: str
) -> None:
    """`"².isdigit()"` is `True` and `int("²")` raises: the guard and the use disagreed.

    Reproduced live against a real store, not at the interpreter: the file sits in the
    credential directory, `sweep_orphaned_temporaries` is called from `save()`, and the
    `ValueError` came out of a method whose docstring says "every error is swallowed".

    Arabic-Indic and fullwidth digits are the same class and `int()` *accepts* both, so they
    would have been swept as if they named a PID. They are not PIDs this store ever wrote,
    which is why the check is now ASCII rather than merely non-crashing.
    """
    store = TokenStore(path=tmp_path / "credentials.json")
    store.ensure_directory()
    # Spelled from a PID that is genuinely dead, so the two systems `int()` *accepts* would
    # be swept if the guard were only crash-free: the outcome does not depend on which PIDs
    # this host happens to be running.
    suffix = _in_digits(_a_dead_pid(), NON_ASCII_DIGIT_OFFSETS[system])
    intruder = tmp_path / f".credentials.json.{suffix}.abcd"
    intruder.write_text("not a credential")

    assert store.sweep_orphaned_temporaries() == 0
    assert intruder.exists(), "a name this store never wrote must be left for a human"

    store.save(
        StoredCredentials(
            client_id="client",
            refresh_token=SecretStr("refresh"),  # a placeholder, not a credential
            salt_hex="ab" * 32,
            obtained_at=kit.FETCHED_AT,
        )
    )
    assert store.load().client_id == "client"


def test_the_orphan_sweep_still_collects_a_real_orphan(tmp_path: Path) -> None:
    """The guard must not close the sweep: a dead PID's leftover still goes."""
    store = TokenStore(path=tmp_path / "credentials.json")
    store.ensure_directory()
    dead = tmp_path / f".credentials.json.{_a_dead_pid()}.abcd"
    dead.write_text("stale")
    assert store.sweep_orphaned_temporaries() == 1
    assert not dead.exists()
