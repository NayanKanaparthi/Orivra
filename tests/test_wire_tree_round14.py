"""R-ARCH-034: the chokepoint re-ran seventeen of the tree's forty-one validators.

Round 13 put the re-establishment where the wire form is produced, which was right, and then
discovered the validators off `type(self).__pydantic_decorators__` - `Envelope`'s own, and none
of the twenty-four on the models inside it. `Source` has seven, `MessageRow` four,
`RetrievalReport` three. So

    envelope.model_copy(update={"sources": (a_source_built_with_model_construct,)})

- R-SEC-047's own reproduction line, one field over - put a message at position 900 of a
two-message thread on the wire, which is precisely what amendment A3 says must raise rather
than be clamped "because clamping would silently move evidence, which is the failure class this
project exists to prevent".

That was this project's **tenth** "one shape validated, peers trusted", and the third round
running in which the instance appeared inside the fix for the previous one. The tests here are
written to make the eleventh visible rather than to close the tenth:

  * the **count** is asserted, both halves of it, so a guarantee that narrows back to the outer
    model fails here and says so;
  * the **reach** is asserted against the annotations rather than against the fixture, so a
    model declared inside a container the walk does not descend fails a test on the day it is
    declared rather than on the day somebody serialises one;
  * the **discovery** is asserted to be additive - a subclass may add a validator and cannot
    remove one - which is the half of R-ARCH-033 that discovery off the runtime class got
    wrong.
"""

from __future__ import annotations

import types
import typing
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel, model_validator
from pydantic_core import PydanticSerializationError

from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import WithheldCap
from mailweave.envelope.wire import Frozen, Source
from mailweave.sealed_model import _after_validators_of, re_establish_tree
from mailweave.validation import annotation_parts
from tests.fixtures import envelope_kit as kit
from tests.test_disposition_invariant import build, ledger_with_hits

#: Every after-validator in the envelope tree, and `Envelope`'s own share of them. The two
#: numbers are asserted separately on purpose: round 13's guarantee was exactly the second
#: number while its docstring claimed the first, and a single total would let the same
#: narrowing happen again behind an unchanged count.
#:
#: Round 18 moves the tree total from 42 to 43: `MailboxProvenance`'s
#: `_labels_are_stated_ids_and_imply_an_observation`, which is the new mailbox-provenance
#: model's own check (OD-5). `Envelope`'s share is unchanged.
#:
#: Round 20 moves it from 43 to 47, all four in the structural schema WS-05 adds and none of
#: them on `Envelope`: `MessageRow._a_parent_is_named_exactly_when_one_was_found`,
#: `Source._the_structure_this_source_states_is_about_this_source`,
#: `ThreadParticipant._the_address_is_an_address_and_the_roles_are_disjoint`, and
#: `ThreadStructureReport._the_one_claim_this_block_may_not_make`. `Envelope`'s share is
#: unchanged again, which is the half of this pair that matters: the structural claims are
#: re-established where the models that make them live, not at the outer boundary.
#:
#: Round 21 moves it from 47 to 48:
#: `MessageRow._not_knowing_whether_a_message_can_be_named_is_exactly_one_linkage`, which
#: holds `can_be_a_parent`'s third state to `Linkage.HEADERS_UNOBSERVED` so the field cannot
#: be quietly omitted from a row whose headers were read (AD D.4a, R-RETR-054). `Envelope`'s
#: share is unchanged for the third round running.
#: Round 29 adds one: `OmissionSummary._the_split_sums_to_the_total`; its repair pass adds
#: `Envelope._the_omission_summary_restates_the_certificate_exactly` (R-V01-011).
#:
#: Round 31 moves it from 52 to 55, all three in WS-14's INJ-05 and none of them on
#: `Envelope`: `SenderAuthentication._a_record_implies_an_observation` (a block that neither
#: discloses a record nor declares one oversize states nothing the row does not already
#: state), `ThreadParticipant._the_names_and_their_count_agree` (the count and the list are
#: one fact), and `MessageRow._identity_claims_rest_on_an_observation` (neither
#: `reply_to_differs` nor `authentication` may be a negative claim derived from headers that
#: were never read - OD-5's shape, refused where the row is built).
#:
#: The navigation redesign (2026-09-14) moves it from 55 to 57, neither on `Envelope`:
#: `Continuation._the_remainder_is_stated_consistently` (a remainder names its scope, its size
#: agrees with the ids or positions it lists, and a thread continuation names its thread) and
#: `Source._a_page_is_stated_whole_or_not_at_all` (page, page size and page count travel
#: together, index a real page, and the last page is not empty).
#: Per-message attribution (2026-09-21): +1, `Attribution._the_address_rests_on_the_header`
#: (an address needs a `From` observed behind it, a display name travels untrusted, and the
#: provenance token and the stated count agree).
TREE_AFTER_VALIDATORS = 58
#: Round 29 repair pass: +1, `_the_omission_summary_restates_the_certificate_exactly`.
ENVELOPE_AFTER_VALIDATORS = 19


def models_in_the_tree() -> set[type[BaseModel]]:
    """Every model reachable from `Envelope`'s field annotations, at any generic depth.

    Discovered rather than listed, and off the *annotations* rather than off an instance, so a
    model that no fixture happens to build is still counted. `annotation_parts` is the same
    traversal the secret canary uses, imported rather than written again.
    """
    seen: set[type[BaseModel]] = set()
    pending: list[type[BaseModel]] = [Envelope]
    while pending:
        model = pending.pop()
        if model in seen:
            continue
        seen.add(model)
        for field in model.model_fields.values():
            pending.extend(
                part
                for part in annotation_parts(field.annotation)
                if isinstance(part, type) and issubclass(part, BaseModel) and part is not BaseModel
            )
    return seen


def a_rich_envelope() -> Envelope:
    """One disclosed row, one withheld message, in a thread the observation described."""
    ledger = ledger_with_hits("m1", "m2", threads={"m1": "t1", "m2": "t9"})
    ledger.note_withheld(
        message_id="m2",
        cap=WithheldCap.MAX_HIT_THREADS,
        why="31 hit-bearing threads; 12 mapped",
        affordance=kit.thread_affordance("t9"),
    )
    return build(ledger, lambda nonce: [kit.source("t1", [kit.row("m1", "t1", 0, nonce=nonce)])])


# --- the count ---------------------------------------------------------------------------------


def test_the_tree_has_more_after_validators_than_the_envelope_does() -> None:
    """The finding as a number, so a fix that narrows to the outer model is visible.

    Both figures are pinned. If a validator is added the total moves and this fails, which is
    the prompt to check that the new one is re-established too; if the *coverage* narrows back
    to `Envelope`'s own, the test below fails instead. One number could not distinguish those.
    """
    counted = {
        model.__name__: sum(
            1
            for validator in model.__pydantic_decorators__.model_validators.values()
            if validator.info.mode == "after"
        )
        for model in models_in_the_tree()
    }
    assert sum(counted.values()) == TREE_AFTER_VALIDATORS, counted
    assert counted["Envelope"] == ENVELOPE_AFTER_VALIDATORS, counted
    # Round 20: `Source` gains `_the_structure_this_source_states_is_about_this_source` and
    # `MessageRow` gains `_a_parent_is_named_exactly_when_one_was_found` (WS-05). Round 21:
    # `MessageRow` gains
    # `_not_knowing_whether_a_message_can_be_named_is_exactly_one_linkage` (R-RETR-054).
    # Round 31: `MessageRow` gains `_identity_claims_rest_on_an_observation`,
    # `ThreadParticipant` gains `_the_names_and_their_count_agree`, and INJ-05's new
    # `SenderAuthentication` arrives with one of its own (WS-14).
    # Navigation redesign (2026-09-14): `Source` gains `_a_page_is_stated_whole_or_not_at_all`.
    assert counted["Source"] == 9 and counted["MessageRow"] == 7, counted
    assert counted["ThreadParticipant"] == 2 and counted["ThreadStructureReport"] == 1, counted
    assert counted["SenderAuthentication"] == 1, counted


def test_every_after_validator_in_the_tree_runs_when_an_envelope_is_serialised() -> None:
    """Not "the discovery finds them" - that the **serializer** runs them, on the whole tree.

    The round-13 suite had a test that discovered the validators and then called them itself,
    which establishes nothing about the serializer; its implementer noticed and added a second
    one for `Envelope`. This is that second test for the tree: every after-validator of every
    model class present in the payload is wrapped in a counter, one `model_dump` is driven, and
    the set that ran is compared with the set that exists.
    """
    envelope = a_rich_envelope()
    present = {type(model) for model in _every_model_in(envelope)}
    ran: set[str] = set()
    expected: set[str] = set()

    patched: list[tuple[type[BaseModel], str, Any]] = []
    for model_class in present:
        for name, validator in model_class.__pydantic_decorators__.model_validators.items():
            if validator.info.mode != "after":
                continue
            expected.add(f"{model_class.__name__}.{name}")
            patched.append((model_class, name, validator.func))

    def counting(label: str, original: Callable[[Any], Any]) -> Callable[[Any], Any]:
        def wrapper(instance: Any) -> Any:
            ran.add(label)
            return original(instance)

        return wrapper

    try:
        for model_class, name, original in patched:
            label = f"{model_class.__name__}.{name}"
            model_class.__pydantic_decorators__.model_validators[name].func = counting(
                label, original
            )
        _after_validators_of.__globals__["_AFTER_VALIDATORS"].clear()
        envelope.model_dump(mode="json")
    finally:
        for model_class, name, original in patched:
            model_class.__pydantic_decorators__.model_validators[name].func = original
        _after_validators_of.__globals__["_AFTER_VALIDATORS"].clear()

    assert expected <= ran, f"never ran at the wire: {sorted(expected - ran)}"
    assert len({label.split(".")[0] for label in ran}) > 1, (
        "only one model's validators ran, which is the defect rather than the fix"
    )


def _every_model_in(root: BaseModel) -> list[BaseModel]:
    found: list[BaseModel] = []
    pending: list[Any] = [root]
    while pending:
        item = pending.pop()
        if isinstance(item, BaseModel):
            found.append(item)
            pending.extend(vars(item).values())
        elif isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list | tuple | set | frozenset):
            pending.extend(item)
    return found


# --- the reach ---------------------------------------------------------------------------------


def test_the_walk_reaches_every_model_the_annotations_can_hold() -> None:
    """The walk descends mappings, sequences and sets. This pins the schema to that.

    The residue of any walk is the container it does not enter, and round 11's record walker
    was found by a reviewer for exactly that (R-SEC-042). Rather than claim the list is
    complete, every field annotation in the tree is decomposed and any model found under an
    origin the walk does not descend fails here - so the day somebody declares
    `sources: MyCustomHolder[Source]`, this test says so instead of the guarantee quietly
    shrinking.
    """
    # Unions and `Optional` are not containers: at runtime the value *is* one of the members,
    # which the walk meets directly. Everything else here is a container the walk enters.
    transparent = {types.UnionType, typing.Union, typing.Literal, typing.Annotated}
    descended = {tuple, list, dict, frozenset, set, *transparent}
    offenders: list[str] = []
    for model in models_in_the_tree():
        for name, field in model.model_fields.items():
            for part in annotation_parts(field.annotation):
                origin = typing.get_origin(part)
                if origin is None or origin in descended:
                    continue
                holds_a_model = any(
                    isinstance(inner, type) and issubclass(inner, BaseModel)
                    for inner in annotation_parts(part)
                )
                if holds_a_model:
                    offenders.append(f"{model.__name__}.{name}: {part}")
    assert offenders == [], (
        f"a model is declared inside a container the wire walk does not descend: {offenders}. "
        "Its validators would not be re-established at the chokepoint, which is R-ARCH-034."
    )


# --- the finding's own reproduction lines --------------------------------------------------------


def a_source_at_position_900(nonce: str) -> Source:
    good = kit.source(
        "t1",
        [
            kit.row("m1", "t1", 0, nonce=nonce),
            kit.row("m2", "t1", 1, nonce=nonce),
        ],
    )
    return Source.model_construct(
        **{
            **{name: getattr(good, name) for name in Source.model_fields},
            "messages": (good.messages[0], good.messages[1].model_copy(update={"position": 900})),
        }
    )


def two_source_envelope() -> Envelope:
    ledger = ledger_with_hits("m1", "m2", threads={"m1": "t1", "m2": "t1"})
    return build(
        ledger,
        lambda nonce: [
            kit.source(
                "t1",
                [kit.row("m1", "t1", 0, nonce=nonce), kit.row("m2", "t1", 1, nonce=nonce)],
            )
        ],
    )


def test_model_copy_with_a_tampered_nested_source_is_refused() -> None:
    """R-ARCH-034's repro line: `model_copy(update={"sources": ...})`, one field over from
    R-SEC-047's own."""
    envelope = two_source_envelope()

    with pytest.raises(ValueError) as raised:
        envelope.model_copy(update={"sources": (a_source_at_position_900(envelope.fence_nonce),)})
    assert "places evidence outside the thread it describes" in str(raised.value)


def test_model_construct_with_a_tampered_nested_source_is_refused_at_the_wire() -> None:
    """`model_construct` skips validation entirely, so the refusal has to be at the wire."""
    envelope = two_source_envelope()
    forged = Envelope.model_construct(
        **{
            **{name: getattr(envelope, name) for name in Envelope.model_fields},
            "sources": (a_source_at_position_900(envelope.fence_nonce),),
        }
    )

    assert forged.sources[0].messages[1].position == 900
    with pytest.raises(PydanticSerializationError) as raised:
        forged.model_dump(mode="json")
    assert "places evidence outside the thread it describes" in str(raised.value)


def test_a_row_moved_past_frozen_on_a_nested_model_is_refused_at_the_wire() -> None:
    """The same write round 13 pinned on the *outer* model, applied one level down.

    `vars(row)["position"] = 900` needs no private name and no construction path at all, and
    it was the shape whose outer-model twin round 13 asserted in its own test file while the
    nested one reached the wire.
    """
    envelope = two_source_envelope()
    vars(envelope.sources[0].messages[1])["position"] = 900

    with pytest.raises(PydanticSerializationError) as raised:
        envelope.model_dump_json()
    assert "places evidence outside the thread it describes" in str(raised.value)


def test_two_rows_landed_on_one_slot_are_refused_at_the_wire() -> None:
    """R-RETR-002's occupancy rule, which is the other thing A3 is about."""
    envelope = two_source_envelope()
    vars(envelope.sources[0].messages[1])["position"] = 0

    with pytest.raises(PydanticSerializationError) as raised:
        envelope.model_dump(mode="json")
    assert "claim the same thread position" in str(raised.value)


def test_a_narrowed_dump_of_a_tampered_envelope_is_refused_even_though_it_omits_the_source() -> (
    None
):
    """The route that makes the **tree walk** load-bearing rather than a second copy of it.

    Found by this round's own reintroduction battery, which reported `NOT CAUGHT` for replacing
    `re_establish_tree(self)` with `re_establish(self)` at both chokepoints. It was right: every
    other test here serialises the nested source, and a nested wire model re-establishes itself
    when it is serialised, so the two mechanisms are indistinguishable on those routes.

    They come apart on a dump that omits the source. `model_dump(include={"partial"})` emits one
    field, so the tampered `Source` is never serialised and never checks itself - and without
    the walk the envelope hands out a narrowed view of a payload that puts a message at position
    900 of a two-message thread. Measured both ways before this test was written: refused with
    the walk, accepted without it.
    """
    envelope = two_source_envelope()
    vars(envelope.sources[0].messages[1])["position"] = 900

    for narrowed in ({"partial"}, {"withheld"}, {"fence_nonce"}):
        with pytest.raises(PydanticSerializationError) as raised:
            envelope.model_dump(include=narrowed)
        assert "places evidence outside the thread it describes" in str(raised.value)


def test_a_row_dumped_on_its_own_states_no_bound_it_does_not_carry() -> None:
    """The honest edge of "every route is refused", named rather than glossed.

    A `MessageRow` dumped by itself is accepted with `position=900`, and that is correct: the
    bound is `0 <= p < stated_total` and a row carries no `stated_total`. The check lives on
    `Source`, which is the model that knows the thread's length. Asserted so that "every
    serialisation route refuses a tampered payload" is read with the scope it actually has -
    the payload is refused wherever the model that can judge it is in the dump.
    """
    envelope = two_source_envelope()
    row = envelope.sources[0].messages[1]
    vars(row)["position"] = 900

    assert row.model_dump(mode="json")["position"] == 900
    with pytest.raises(PydanticSerializationError):
        envelope.sources[0].model_dump(mode="json")


def test_a_nested_model_checks_itself_when_it_is_serialised_on_its_own() -> None:
    """The chokepoint is on every wire model, not only on the envelope.

    Two independent nets, and this is the second: the top-down walk covers a payload whose
    nested serializer is not this module's, and the per-model check covers a `Source` handed to
    a caller that dumps it directly - which nothing does today and which needs no permission.
    """
    source = a_source_at_position_900(two_source_envelope().fence_nonce)

    with pytest.raises(PydanticSerializationError) as raised:
        source.model_dump(mode="json")
    assert "places evidence outside the thread it describes" in str(raised.value)


def test_an_honest_envelope_still_serialises_unchanged() -> None:
    """The re-derivation must be invisible when there is nothing wrong, in both modes."""
    import json

    envelope = a_rich_envelope()
    dumped = envelope.model_dump(mode="json")

    assert dumped["partial"] is True
    assert [record["id"] for record in dumped["withheld"]] == ["m2"]
    assert json.loads(envelope.model_dump_json()) == dumped
    assert dumped["sources"][0]["messages"][0]["position"] == 0


# --- the discovery -------------------------------------------------------------------------------


def test_a_subclass_may_add_a_validator_and_cannot_remove_one() -> None:
    """R-ARCH-033 route (a), as a property of the discovery rather than of the seal.

    `type(self).__pydantic_decorators__` is the *merged* table, so a subclass method of the
    same name replaces the base's entry and the loop faithfully runs the attacker's no-op. Wire
    models cannot be subclassed at all now, so this is asserted on plain models built for the
    purpose - which is the honest way to test a property of the discovery function, and it
    keeps the property true for any future model that is not a `Frozen`.
    """

    class Base(BaseModel):
        @model_validator(mode="after")
        def _the_real_one(self) -> Base:
            raise ValueError("the base validator ran")

    class Quiet(Base):
        @model_validator(mode="after")
        def _the_real_one(self) -> Quiet:
            return self

    merged = Quiet.__pydantic_decorators__.model_validators["_the_real_one"].func
    assert merged.__qualname__.startswith("test_a_subclass_may_add"), (
        "the merged table holds the subclass's function, which is what defeated round 13"
    )

    collected = _after_validators_of(Quiet)
    assert len(collected) == 2, [validator.__qualname__ for validator in collected]
    with pytest.raises(ValueError, match="the base validator ran"):
        re_establish_tree(Quiet.model_construct())


def test_the_discovery_is_read_off_the_class_and_not_from_a_list() -> None:
    """A validator that did not exist when this check was written is covered by existing."""
    seen: list[str] = []

    class Later(Frozen):
        value: int = 1

        @model_validator(mode="after")
        def _nobody_listed_this(self) -> Later:
            seen.append("ran")
            return self

    later = Later(value=2)
    seen.clear()  # construction runs it too; what is under test is the serializer

    later.model_dump(mode="json")
    assert seen == ["ran"]
