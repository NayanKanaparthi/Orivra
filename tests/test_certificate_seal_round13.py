"""The disposition seal, attacked the way R-SEC-046 and R-SEC-047 attacked it.

Both findings are the shape this project keeps rediscovering - **a capability checked where
the object is built, in a language with several ways to build one** - and both were live in
the seal invariant I-1 rests on:

  * `DispositionCertificate` checked `_MINT_TOKEN` in `__init__` only. `copy.copy` never runs
    `__init__`, and the slots behind read-only properties are ordinary writable slots, so two
    plain assignments produced a certificate stating `withheld = ()` for a ledger that had
    recorded a withheld hit - and `Envelope` accepted it, publishing `withheld: []` and
    `partial: false` for a response missing a message (R-SEC-046);
  * one layer up, `envelope.model_copy(update={"withheld": (), "partial": False})` skips every
    `model_validator`, including the one whose docstring says an envelope may not restate the
    certificate's conclusion differently, and the result serialises to the wire (R-SEC-047).

Neither is fixed by naming the construction paths. The certificate's facts now live off the
certificate, so a copy of one has nothing to state; and the envelope's invariants are
re-established where the wire form is produced, so what a caller sends is checked whatever
built the object it was sent from.
"""

from __future__ import annotations

import copy
import pickle
import types
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError, model_validator
from pydantic_core import PydanticSerializationError

from mailweave.envelope.disposition import (
    DispositionCertificate,
    DispositionLedger,
    FetchedIds,
    ObservedEndpoint,
)
from mailweave.envelope.reasons import RungId
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import WithheldCap
from mailweave.envelope.wire import Frozen
from mailweave.errors import DispositionInvariantError
from tests.fixtures import envelope_kit as kit
from tests.test_disposition_invariant import build, ledger_with_hits


def honest_envelope() -> Envelope:
    """`m1` disclosed, `m2` withheld: the truthful envelope R-SEC forged its copy from."""
    ledger = ledger_with_hits("m1", "m2", threads={"m1": "t1", "m2": "t9"})
    ledger.note_withheld(
        message_id="m2",
        cap=WithheldCap.MAX_HIT_THREADS,
        why="31 hit-bearing threads; 12 mapped",
        affordance=kit.thread_affordance("t9"),
    )
    return build(ledger, lambda nonce: [kit.source("t1", [kit.row("m1", "t1", 0, nonce=nonce)])])


def a_certificate() -> DispositionCertificate:
    ledger = DispositionLedger()
    ledger.record_list_page(
        kit.fetched(("m1", "m2"), thread_ids={"m1": "t1", "m2": "t1"}),
        rung=RungId.L1,
        query="from:amy",
    )
    return ledger.certify(["m1", "m2"])


#: Every way this interpreter rebuilds an object without running `__init__`. The point is not
#: that the list is complete - it cannot be, which is the whole argument - but that a fix
#: which had to name them would already be behind.
REBUILDS: dict[str, Callable[[DispositionCertificate], DispositionCertificate]] = {
    "copy.copy": copy.copy,
    "copy.deepcopy": copy.deepcopy,
    "pickle, default protocol": lambda item: pickle.loads(pickle.dumps(item)),
    "pickle, protocol 2": lambda item: pickle.loads(pickle.dumps(item, 2)),
    "object.__new__": lambda item: object.__new__(DispositionCertificate),
}


# --- R-SEC-046: a certificate no ledger minted states nothing --------------------------------


def test_direct_construction_is_still_refused() -> None:
    with pytest.raises(DispositionInvariantError) as raised:
        DispositionCertificate(
            object(),
            hit_count=1,
            disclosed_hits=1,
            withheld=(),
            withheld_groups=(),
            withheld_tail=(),
            grouped_ids=(),
            digest="d",
            observed_threads={},
            hits_per_rung={},
            observed_scalars={},
            observed_thread_facts={},
        )
    assert "may only be minted" in str(raised.value)


@pytest.mark.parametrize("rebuild", sorted(REBUILDS))
def test_a_rebuilt_certificate_certifies_nothing_at_all(rebuild: str) -> None:
    """Not a *different* disposition - none. There is nothing on the object to rewrite.

    `copy.deepcopy` and `pickle` used to raise on a `mappingproxy` in the slots. That was an
    artefact and it protected nothing: `copy.copy` went straight past it, which is the route
    R-SEC used. They now succeed and produce an object that answers no question, which is the
    property rather than an accident of what happens to be picklable.
    """
    certificate = a_certificate()
    rebuilt = REBUILDS[rebuild](certificate)

    assert rebuilt is not certificate
    readings: tuple[Callable[[DispositionCertificate], object], ...] = (
        lambda item: item.hit_count,
        lambda item: item.disclosed_hits,
        lambda item: item.withheld,
        lambda item: item.withheld_ids,
        lambda item: item.disclosure_digest,
        lambda item: item.observed_threads,
        lambda item: item.hits_per_rung,
        lambda item: item.observed_positions,
        lambda item: item.observed_internal_dates,
        lambda item: item.observed_thread_facts,
        lambda item: item.assert_minted(),
    )
    for reading in readings:
        with pytest.raises(DispositionInvariantError) as raised:
            reading(rebuilt)
        assert "certifies nothing" in str(raised.value)


def test_the_slots_r_sec_rewrote_do_not_exist_to_be_rewritten() -> None:
    """R-SEC's forgery, line for line: `forged._withheld = ()`, `forged._hit_count = 1`.

    The properties were read-only and the slots behind them were not. There are no such slots
    now - the numbers are not on the object - so the assignment fails where it is written
    rather than producing an internally consistent lie.
    """
    forged = copy.copy(a_certificate())

    for name in ("_withheld", "_hit_count", "_disclosed_hits", "_disclosure_digest"):
        with pytest.raises(AttributeError):
            setattr(forged, name, ())
        with pytest.raises(AttributeError):
            object.__setattr__(forged, name, ())


def test_a_forged_certificate_cannot_reach_an_envelope() -> None:
    """The finding end to end: the forged certificate reaching `Envelope` is what made it a HIGH.

    Before this round the envelope below was built and stated `withheld: []`, `partial: false`
    for a response whose ledger had recorded a hit no record accounted for. Every one of
    `Envelope`'s cross-checks passed, because the forged certificate was internally consistent
    and the disclosure digest was untouched.
    """
    honest = honest_envelope()
    forged = copy.copy(honest.disposition)

    fields: dict[str, Any] = {name: getattr(honest, name) for name in Envelope.model_fields}
    fields["withheld"] = ()
    fields["partial"] = False
    fields["disposition"] = forged

    with pytest.raises(DispositionInvariantError) as raised:
        Envelope(**fields)
    assert "certifies nothing" in str(raised.value)


# --- the route holding the facts off the object does NOT close, found by attacking the fix ----


SUBCLASS_ROUTES: dict[str, Callable[[type], type]] = {
    "the class statement": lambda base: type("Forged", (base,), {}),
    "types.new_class": lambda base: types.new_class("Forged", (base,)),
    "type.__new__ directly": lambda base: type.__new__(type, "Forged", (base,), {}),
}


@pytest.mark.parametrize("route", sorted(SUBCLASS_ROUTES))
def test_the_certificate_cannot_be_subclassed(route: str) -> None:
    """R-RETR's round-3 attack 8, which this module's own token lost to and never re-checked.

    Moving the facts into the registry closes every route that *rebuilds* a certificate. It
    closes none that **replaces the reader**: a subclass overriding `withheld` and
    `withheld_ids` never consults `_certified`, so nothing raises, and `Envelope`'s field is
    an `isinstance` check a subclass passes. Found by this round's implementer attacking its
    own fix; `SeedSession` has refused subclassing since round 12 for exactly this reason.
    """
    with pytest.raises(TypeError) as raised:
        SUBCLASS_ROUTES[route](DispositionCertificate)
    assert "may not be subclassed" in str(raised.value)


def test_reassigning_bases_onto_the_certificate_is_refused_too() -> None:
    """The fourth route, which `__init_subclass__` does not see - CPython's layout check does.

    Asserted rather than assumed, because it is refused by the interpreter and not by us: if a
    future CPython allowed it, this test is where that shows up rather than in a review.
    """

    class Plain:
        __slots__ = ()

    with pytest.raises(TypeError) as raised:
        Plain.__bases__ = (DispositionCertificate,)
    assert "__bases__" in str(raised.value)


@pytest.mark.parametrize("route", sorted(SUBCLASS_ROUTES))
def test_the_fetched_page_cannot_be_subclassed_either(route: str) -> None:
    """Amendment A1 named this move in terms and it stayed possible for ten rounds.

    "Even a capability token is defeated by subclassing and overriding `_release`" - so a
    subclass hands the ledger ids the observation it claims to be never carried, and never
    presents `_RECORD_TOKEN` at all. Closing it also makes `retrieval/transport.py`'s three
    `isinstance(page, FetchedIds)` checks mean the class rather than anything shaped like it.

    It does **not** close A1's over-recording residue, which is about the *public constructor*
    and is unclosable in-process; the residual case in `tests/test_disposition_invariant.py`
    (`...a_hand_built_page_is_accepted...`) is where that stays recorded.
    """
    with pytest.raises(TypeError) as raised:
        SUBCLASS_ROUTES[route](FetchedIds)
    assert "may not be subclassed" in str(raised.value)


def test_a_certificate_impostor_that_is_not_a_subclass_is_refused_by_the_envelope() -> None:
    """With subclassing closed, the remaining shape is a duck, and the envelope's type sees it.

    Stated as a fact about `Envelope` rather than about the certificate, because that is what
    it is: the field is `DispositionCertificate`, so Pydantic runs an `isinstance` check. A
    future consumer that typed its parameter structurally would not inherit this.
    """
    honest = honest_envelope()
    certificate = honest.disposition

    class Duck:
        withheld = ()
        withheld_ids = frozenset[str]()
        hit_count = 1
        disclosed_hits = 1
        disclosure_digest = certificate.disclosure_digest
        observed_threads = certificate.observed_threads
        hits_per_rung = certificate.hits_per_rung
        observed_positions = certificate.observed_positions
        observed_internal_dates = certificate.observed_internal_dates
        observed_thread_facts = certificate.observed_thread_facts

    fields: dict[str, Any] = {name: getattr(honest, name) for name in Envelope.model_fields}
    fields["withheld"] = ()
    fields["partial"] = False
    fields["disposition"] = Duck()

    with pytest.raises(ValidationError) as raised:
        Envelope(**fields)
    assert "DispositionCertificate" in str(raised.value)


def test_a_certificate_the_ledger_minted_is_unaffected_by_a_copy_of_itself() -> None:
    """The legitimate case must not be closed: copying a certificate does not damage it."""
    certificate = a_certificate()
    copy.copy(certificate)
    copy.deepcopy(certificate)

    assert certificate.hit_count == 2
    assert certificate.disclosed_hits == 2
    certificate.assert_minted()


def test_the_repr_of_an_unminted_certificate_does_not_raise_or_pretend() -> None:
    """A debugging aid that raised would be a debugging aid nobody could use."""
    rendered = repr(copy.copy(a_certificate()))

    assert "certifies nothing" in rendered
    assert "H=" not in rendered


def test_the_facts_a_certificate_states_are_the_ones_the_ledger_computed() -> None:
    """The seal is not only a refusal: what it does answer must still be the ledger's answer."""
    ledger = ledger_with_hits("m1", "m2", threads={"m1": "t1", "m2": "t9"})
    ledger.note_withheld(
        message_id="m2",
        cap=WithheldCap.MAX_HIT_THREADS,
        why="one thread over the map cap",
        affordance=kit.thread_affordance("t9"),
    )
    certificate = ledger.certify(["m1"])

    assert certificate.hit_count == 2
    assert certificate.disclosed_hits == 1
    assert certificate.withheld_ids == {"m2"}
    assert certificate.observed_threads == {"m1": "t1", "m2": "t9"}
    assert certificate.hits_per_rung == {RungId.L1: 2}


def test_the_seal_on_a_fetched_page_is_still_one_shot_after_a_copy() -> None:
    """`FetchedIds` is the other capability object in this module, and it holds.

    Checked here rather than assumed: its token is compared in `_release`, which is a *use*
    site, so the shape R-SEC-046 was about was never present in it. A copy of a consumed page
    is refused because the latch is part of what was copied.
    """
    ledger = DispositionLedger()
    page = kit.fetched(("m1",), thread_ids={"m1": "t1"})
    assert page.endpoint is ObservedEndpoint.MESSAGES_LIST
    ledger.record_list_page(page, rung=RungId.L1, query="from:amy")

    with pytest.raises(DispositionInvariantError):
        ledger.record_list_page(page, rung=RungId.L1, query="from:amy")
    with pytest.raises(DispositionInvariantError):
        ledger.record_list_page(copy.copy(page), rung=RungId.L1, query="from:amy")


# --- R-SEC-047: the wire form re-derives what construction derived ----------------------------


def test_model_copy_cannot_restate_the_disposition() -> None:
    """One documented, ordinary line of Pydantic, which skipped every validator."""
    honest = honest_envelope()

    with pytest.raises(DispositionInvariantError) as raised:
        honest.model_copy(update={"withheld": (), "partial": False})
    assert "disagrees with the certified set difference" in str(raised.value)


def test_a_legitimate_model_copy_still_works() -> None:
    """The check must not close the door on the copy that changes nothing it may not change."""
    honest = honest_envelope()

    same = honest.model_copy()
    assert same.withheld_ids == honest.withheld_ids

    relabelled = honest.model_copy(update={"truncated_by": None})
    assert relabelled.partial is True


def test_model_construct_reaches_no_wire_form_either() -> None:
    """The peer a `model_copy`-only fix would have missed, which is why the check is at the wire.

    `model_construct` is Pydantic's documented way to build a model with **no** validation at
    all, so an envelope built with it never met a validator in the first place. It is refused
    when it is serialised, which is where it would have mattered.
    """
    honest = honest_envelope()
    fields: dict[str, Any] = {name: getattr(honest, name) for name in Envelope.model_fields}
    fields["withheld"] = ()
    fields["partial"] = False

    unvalidated = Envelope.model_construct(**fields)

    assert unvalidated.withheld == ()
    # Pydantic wraps whatever a serializer raises, so the invariant's type does not
    # survive; its message does, and that is what a caller sees.
    with pytest.raises(PydanticSerializationError) as raised:
        unvalidated.model_dump(mode="json")
    assert "disagrees with the certified set difference" in str(raised.value)


def test_a_field_written_past_frozen_is_refused_at_the_wire() -> None:
    """`frozen=True` guards `__setattr__` and not the instance `__dict__`.

    Which is a route round 12's R-SEC used on `SeedSession` (`vars(session)["address"] = ...`)
    and which needs no private name here either. The envelope's own validators are what catch
    it, at the point the answer is turned into a response.
    """
    honest = honest_envelope()
    vars(honest)["withheld"] = ()
    vars(honest)["partial"] = False

    # Pydantic wraps whatever a serializer raises, so the invariant's type does not
    # survive; its message does, and that is what a caller sees.
    with pytest.raises(PydanticSerializationError) as raised:
        honest.model_dump_json()
    assert "disagrees with the certified set difference" in str(raised.value)


SERIALISATION_ROUTES: dict[str, Callable[[Envelope], object]] = {
    "model_dump()": lambda item: item.model_dump(),
    "model_dump(mode='json')": lambda item: item.model_dump(mode="json"),
    "model_dump_json()": lambda item: item.model_dump_json(),
    "model_dump(include=...)": lambda item: item.model_dump(include={"withheld"}),
    "model_dump(exclude=...)": lambda item: item.model_dump(exclude={"sources"}),
    "model_dump(warnings=False)": lambda item: item.model_dump(warnings=False),
    "a TypeAdapter over a list": lambda item: TypeAdapter(list[Envelope]).dump_python([item]),
}


@pytest.mark.parametrize("route", sorted(SERIALISATION_ROUTES))
def test_every_serialisation_route_re_derives_the_disposition(route: str) -> None:
    """ "At the wire" has to mean every route through the serializer, not the one that was tried.

    `model_dump(mode="json")` is the route the round-13 tests were first written against.
    `include`, `exclude`, `by_alias`, `warnings=False`, the python mode, and this envelope
    inside a `TypeAdapter` are all the same serializer with different arguments - but "all the
    same" is the assumption this project keeps finding to be false, so each is driven.
    """
    tampered = honest_envelope()
    vars(tampered)["withheld"] = ()
    vars(tampered)["partial"] = False

    with pytest.raises(PydanticSerializationError) as raised:
        SERIALISATION_ROUTES[route](tampered)
    assert "disagrees with the certified set difference" in str(raised.value)


def test_a_tampered_envelope_nested_in_another_model_is_refused_at_construction() -> None:
    """One layer out: a model that holds an envelope validates it, so the refusal is earlier."""

    class Wrapper(BaseModel):
        model_config = ConfigDict(arbitrary_types_allowed=True)
        inner: Envelope

    tampered = honest_envelope()
    vars(tampered)["withheld"] = ()
    vars(tampered)["partial"] = False

    with pytest.raises(DispositionInvariantError):
        Wrapper(inner=tampered)


def test_the_attribute_read_residue_is_what_the_docstring_says() -> None:
    """The honest half, asserted so it cannot quietly become an overstatement.

    `dict(envelope)` is Pydantic's field-iteration convenience: a bulk attribute read, not a
    serialisation, so it hands back whatever the fields hold exactly as `envelope.withheld`
    does. A caller who assembles a payload out of that has left the supported path, and no
    check on this class can follow them there - the same residue `pinning.py` records for a
    use site that never calls `assert_bound_to`.

    This test asserts the residue **still exists**. If a later round closes `__iter__`, this
    fails, and whoever does it must decide whether the docstring's paragraph is still true
    rather than discovering later that it is not.
    """
    tampered = honest_envelope()
    vars(tampered)["withheld"] = ()

    assert dict(tampered)["withheld"] == ()
    assert tampered.withheld == ()
    # R-ARCH-038: the residue is every read of the object, including the ones a human reads.
    # `repr` renders the tampered value into any log line or error message that formats an
    # envelope, and the object silently disagrees with its own certificate while doing it.
    # The docstring says so since round 14; this is what keeps that sentence honest.
    assert "withheld=()" in repr(tampered)
    assert tampered.disposition.withheld_ids == {"m2"}
    with pytest.raises(PydanticSerializationError):
        tampered.model_dump(mode="json")


def test_an_honest_envelope_serialises_unchanged() -> None:
    """The re-derivation must be invisible when there is nothing wrong.

    Both modes, and the JSON form compared against the python one, because a serializer that
    quietly changed the payload while checking it would be a worse defect than the one it
    closes.
    """
    honest = honest_envelope()

    dumped = honest.model_dump(mode="json")
    assert dumped["withheld"][0]["id"] == "m2"
    assert dumped["partial"] is True
    assert "disposition" not in dumped

    import json

    assert json.loads(honest.model_dump_json()) == dumped


def test_every_after_validator_is_re_run_at_the_wire_rather_than_a_chosen_few() -> None:
    """The list is read off the class, so a validator added later is covered the day it exists.

    Asserted rather than trusted: this is the same reflection the secret canary uses, and the
    reason neither has a list to fall behind. A validator that stopped being re-run would make
    the wire form's guarantee narrower than the constructor's without anything saying so.
    """
    after = {
        name
        for name, validator in Envelope.__pydantic_decorators__.model_validators.items()
        if validator.info.mode == "after"
    }
    assert len(after) >= 12, f"only {len(after)} after-validators discovered: {sorted(after)}"

    ran: list[str] = []
    honest = honest_envelope()
    for name, validator in Envelope.__pydantic_decorators__.model_validators.items():
        if validator.info.mode == "after":
            validator.func(honest)
            ran.append(name)

    assert set(ran) == after


def test_a_validator_added_after_this_round_is_re_run_at_the_wire_without_being_listed() -> None:
    """The claim itself, driven rather than inferred from the discovery being a loop.

    The test above establishes that the discovery finds every `mode="after"` validator; it
    does not establish that the **serializer** runs the ones it finds, and the reintroduction
    battery showed the difference: replacing the discovery with a hand-written call to one
    chosen validator left that test green. So a validator that did not exist when this check
    was written is added here, and the assertion is that serialising ran it.

    **Re-expressed in round 14, and the reason is worth reading.** This test used to subclass
    `Envelope`, which meant one file held a test that *depended on* the envelope being
    subclassable with validator-substitution semantics and, next door, a class sealed against
    subclassing for exactly that reason (R-ARCH-033 §4a). Sealing the reader resolved that in
    the direction the finding asked for, and the property this test is about does not need a
    subclass of a concrete model at all: it is a property of `Frozen`'s serializer, which is
    the one `Envelope` inherits its shape from and the one every nested wire model uses. The
    model below is built on `Frozen`, which declares no fields and is therefore the base the
    schema itself extends.
    """
    seen: list[str] = []

    class WithALaterValidator(Frozen):
        value: int = 1

        @model_validator(mode="after")
        def _a_validator_nobody_listed(self) -> WithALaterValidator:
            seen.append("ran")
            return self

    later = WithALaterValidator(value=2)
    seen.clear()

    later.model_dump(mode="json")

    assert seen == ["ran"], (
        "the wire form did not run a validator added after the check was written, so the "
        "guarantee is a list somebody maintains rather than a property of the class"
    )
