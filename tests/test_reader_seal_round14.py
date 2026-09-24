"""R-SEC-054 and R-ARCH-033: a sealed object read by an unsealed reader is not sealed.

Two findings, one problem, and they are treated as one here.

R-SEC-054: `disposition.py` said a duck-typed impostor "is refused by `Envelope`'s field type,
which is an `isinstance` check". `isinstance` consults `obj.__class__` when `type(obj)` does not
match, so a plain object with a `__class__` property passed it, the envelope accepted it, and
`withheld: []` / `partial: false` went on the wire **with no `DispositionLedger` in the process
at all**. The covering test planted a duck that did not declare `__class__`, so it passed
without ever exercising the property its own name asserts - the failure mode this project has
hit more than any other, and the reason every duck in this file declares one.

R-ARCH-033: the certificate was sealed against subclassing, on the stated argument that "only
this type can be the one reading them", and the reading type was an ordinary Pydantic model.
Three public routes each produced the same wire output, and a fourth - a subclass
`field_serializer` that rewrites a field after every check has passed - was found while fixing
the first three.

The tests are written so that each *route* is driven rather than each *name* being checked: a
route that stops being refused fails here even if the mechanism that refuses it is replaced.
"""

from __future__ import annotations

import copy
import types
from collections.abc import Callable
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel, ConfigDict, field_serializer, model_serializer, model_validator

from mailweave.envelope.disposition import (
    DispositionCertificate,
    FetchedIds,
    ObservedThread,
    assert_is_a_minted_certificate,
    disclosure_digest,
)
from mailweave.envelope.reasons import RungId
from mailweave.envelope.response import (
    Envelope,
    _the_emitted_disposition_is_the_certified_one,
)
from mailweave.envelope.vocab import WithheldCap
from mailweave.envelope.wire import Frozen, MessageRow, Source
from mailweave.errors import DispositionInvariantError
from tests.fixtures import envelope_kit as kit
from tests.test_disposition_invariant import build, ledger_with_hits


def honest_envelope() -> Envelope:
    ledger = ledger_with_hits("m1", "m2", threads={"m1": "t1", "m2": "t9"})
    ledger.note_withheld(
        message_id="m2",
        cap=WithheldCap.MAX_HIT_THREADS,
        why="31 hit-bearing threads; 12 mapped",
        affordance=kit.thread_affordance("t9"),
    )
    return build(ledger, lambda nonce: [kit.source("t1", [kit.row("m1", "t1", 0, nonce=nonce)])])


def impostor_for(certificate: DispositionCertificate) -> Any:
    """R-SEC's impostor, with the `__class__` property that is the whole point of it."""

    class Impostor:
        @property  # type: ignore[misc]
        def __class__(self) -> type:
            return DispositionCertificate

        withheld = ()
        withheld_ids = frozenset[str]()
        hit_count = 1
        disclosed_hits = 1
        disclosure_digest = certificate.disclosure_digest
        observed_threads: ClassVar[Any] = dict(certificate.observed_threads)
        hits_per_rung: ClassVar[Any] = dict(certificate.hits_per_rung)
        observed_positions: ClassVar[Any] = dict(certificate.observed_positions)
        observed_internal_dates: ClassVar[Any] = dict(certificate.observed_internal_dates)
        observed_thread_facts: ClassVar[Any] = dict(certificate.observed_thread_facts)

        def assert_minted(self) -> None:
            """A forgery answers questions the way a real one does. That is what it is."""
            return None

    return Impostor()


# --- R-SEC-054: the duck that declares `__class__` ---------------------------------------------


def test_isinstance_really_is_defeated_by_a_class_property() -> None:
    """First: establish that the hole is real, or the test below proves nothing.

    Round 13's covering test planted a duck *without* `__class__` and asserted the envelope
    refused it - true, and about a weaker object than the one its name described. Asserting
    that `isinstance` is defeated is what makes the next test a test of the fix rather than a
    restatement of the type annotation.
    """
    impostor = impostor_for(honest_envelope().disposition)

    assert isinstance(impostor, DispositionCertificate) is True
    assert type(impostor) is not DispositionCertificate
    assert type(impostor).__name__ == "Impostor"


def test_a_class_property_impostor_is_refused_by_the_envelope() -> None:
    """The finding, end to end: it was ACCEPTED and it SERIALISED."""
    honest = honest_envelope()
    fields: dict[str, Any] = {name: getattr(honest, name) for name in Envelope.model_fields}
    fields["withheld"] = ()
    fields["partial"] = False
    fields["disposition"] = impostor_for(honest.disposition)

    with pytest.raises(DispositionInvariantError) as raised:
        Envelope(**fields)
    assert "is not a DispositionCertificate" in str(raised.value)


def test_a_class_property_impostor_is_refused_with_no_ledger_in_the_process() -> None:
    """R-SEC's sharper version: `disclosure_digest` is public and the attacker owns the payload.

    Nothing here builds a `DispositionLedger` at all, which is what made the original a forgery
    rather than a tampering: there was no certified set difference anywhere for the impostor to
    disagree with.
    """
    honest = honest_envelope()
    disclosed = honest.disclosed_ids

    class NoLedger:
        @property  # type: ignore[misc]
        def __class__(self) -> type:
            return DispositionCertificate

        withheld = ()
        withheld_ids = frozenset[str]()
        hit_count = 1
        disclosed_hits = 1
        disclosure_digest = disclosure_digest(disclosed)
        observed_threads: ClassVar[dict[str, str | None]] = {"m1": "t1"}
        hits_per_rung: ClassVar[dict[RungId, int]] = {RungId.L1: 1}
        observed_positions: ClassVar[dict[str, int]] = {}
        observed_internal_dates: ClassVar[dict[str, str]] = {}
        observed_thread_facts: ClassVar[dict[str, ObservedThread]] = {}

    fields: dict[str, Any] = {name: getattr(honest, name) for name in Envelope.model_fields}
    fields["withheld"] = ()
    fields["partial"] = False
    fields["disposition"] = NoLedger()

    with pytest.raises(DispositionInvariantError):
        Envelope(**fields)


def test_the_check_is_the_mint_and_not_the_objects_own_answer() -> None:
    """Both halves of `assert_is_a_minted_certificate`, and neither is redundant.

    A real certificate of the exact type that `certify` did not mint - a `copy.copy` - passes
    the type half and fails the registry half. An impostor that answers `assert_minted()`
    politely fails the type half. Asking the candidate anything would have let the second one
    through, which is why nothing here does.
    """
    honest = honest_envelope()

    assert assert_is_a_minted_certificate(honest.disposition) is honest.disposition

    with pytest.raises(DispositionInvariantError) as rebuilt:
        assert_is_a_minted_certificate(copy.copy(honest.disposition))
    assert "certifies nothing" in str(rebuilt.value)

    with pytest.raises(DispositionInvariantError) as duck:
        assert_is_a_minted_certificate(impostor_for(honest.disposition))
    assert "is not a DispositionCertificate" in str(duck.value)


def test_the_round_thirteen_duck_without_a_class_property_is_still_refused() -> None:
    """The weaker shape must not become reachable while the stronger one is being closed."""
    honest = honest_envelope()

    class Duck:
        withheld = ()
        withheld_ids = frozenset[str]()

    fields: dict[str, Any] = {name: getattr(honest, name) for name in Envelope.model_fields}
    fields["withheld"] = ()
    fields["partial"] = False
    fields["disposition"] = Duck()

    with pytest.raises(Exception) as raised:
        Envelope(**fields)
    assert "DispositionCertificate" in str(raised.value)


def test_an_isinstance_check_is_not_a_type_check_for_this_class_either() -> None:
    """`FetchedIds`, whose docstring made the same claim about `transport.py`'s checks.

    Not a defect there - those two `isinstance` calls guard against a fetcher returning the
    wrong thing, and the ledger rests on `_release` rather than on them - but the sentence said
    they "mean the class rather than anything shaped like it", and this is what that sentence
    is worth. It is pinned so the narrowed claim cannot drift back.
    """

    class DuckPage:
        @property  # type: ignore[misc]
        def __class__(self) -> type:
            return FetchedIds

    duck: object = DuckPage()
    assert isinstance(duck, FetchedIds) is True
    assert type(duck) is not FetchedIds


# --- R-ARCH-033: every route that puts a different reader on the wire --------------------------


SUBSTITUTION_ROUTES: dict[str, Callable[[type, dict[str, Any]], type]] = {
    "the class statement": lambda base, body: types.new_class(
        "Substituted", (base,), {}, lambda namespace: namespace.update(body)
    ),
    "types.new_class": lambda base, body: types.new_class("Substituted", (base,)),
    "type() with the model metaclass": lambda base, body: type(base)("Substituted", (base,), body),
}


@pytest.mark.parametrize("route", sorted(SUBSTITUTION_ROUTES))
@pytest.mark.parametrize("target", ["Envelope", "Source", "MessageRow"])
def test_a_wire_model_cannot_be_substituted_by_any_route(route: str, target: str) -> None:
    """The reader must be as unsubstitutable as the thing it reads.

    Driven for three models, not only for `Envelope`: R-ARCH-034 showed that what reaches the
    wire is a tree, so "the reader" is every class in it. `Source` and `MessageRow` are where
    A3's position bound and R-RETR-002's occupancy rule live.
    """
    base = {"Envelope": Envelope, "Source": Source, "MessageRow": MessageRow}[target]

    with pytest.raises(TypeError) as raised:
        SUBSTITUTION_ROUTES[route](base, {})
    assert "may not extend" in str(raised.value)


def test_the_three_routes_r_arch_filed_are_each_refused() -> None:
    """The finding's own three, spelled the way it spelled them.

    Each of these produced `partial: false`, `withheld: []` for a certificate that still
    certified `m2` withheld. They are refused at class creation now, so the assertion is that
    the class cannot come into being rather than that its output is caught - which is the
    stronger place for it, since (c) replaced the check that would have caught the output.
    """
    with pytest.raises(TypeError):

        class Quiet(Envelope):  # (a) redefine an after-validator by name
            @model_validator(mode="after")
            def _withheld_matches_the_certificate(self) -> Quiet:
                return self

    with pytest.raises(TypeError):

        class Deaf(Envelope):  # (b) override the method that discovers them
            def _re_establish_every_invariant(self) -> None:
                return None

    with pytest.raises(TypeError):

        class Loud(Envelope):  # (c) replace the wrap serializer by name
            @model_serializer(mode="wrap")
            def _the_wire_form_states_only_what_still_holds(self, handler: Any) -> Any:
                return handler(self)


def test_the_fourth_route_nobody_filed_is_refused_too() -> None:
    """A subclass `field_serializer` rewrites a field **after** every check has passed.

    Found while fixing the other three, and it is why the rule is "a wire model may not be
    extended" rather than a list of the members a subclass may not replace. Every object-level
    check passes for this class; only the emitted form differs, and by then round 13's
    chokepoint had already run.
    """
    with pytest.raises(TypeError) as raised:

        class Sneaky(Envelope):
            @field_serializer("withheld")
            def _empty_on_the_way_out(self, withheld: tuple[Any, ...]) -> list[Any]:
                return []

    assert "may not extend" in str(raised.value)


def test_reassigning_bases_onto_a_wire_model_is_refused_by_the_interpreter() -> None:
    """The route `__init_subclass__` does not see. Asserted because it is CPython's refusal
    and not ours: if a future version allowed it, this is where that shows up."""

    class Plain(BaseModel):
        model_config = ConfigDict(frozen=True)

    with pytest.raises(TypeError):
        Plain.__bases__ = (Envelope,)


def test_the_base_that_declares_no_fields_is_still_extensible() -> None:
    """The rule must not close the door the schema itself walks through.

    `Frozen` declares no fields, so extending it is how every wire model is written and how a
    later round adds one. That distinction - extend a base, do not extend a *reader* - is the
    whole of the rule, and a rule that refused both would be unusable and would get removed.
    """

    class Later(Frozen):
        value: int = 1

    assert Later(value=2).model_dump() == {"value": 2}

    with pytest.raises(TypeError):

        class Deeper(Later):
            more: int = 1


# --- the emitted form -------------------------------------------------------------------------


def test_the_emitted_form_is_compared_with_the_certificate_not_only_the_object() -> None:
    """The check on what is handed out, driven directly.

    Every other check in `response.py` is a check on the object; this one reads I-1's and I-2's
    two claims back out of the mapping that is about to be returned. It is driven here by
    handing it a doctored mapping, because the routes that would produce one in the wild - a
    substituted serializer - are refused at class creation, and a check nothing can reach is a
    check nothing has tested.
    """
    honest = honest_envelope()
    certificate = honest.disposition
    truthful = honest.model_dump(mode="json")

    _the_emitted_disposition_is_the_certified_one(truthful, certificate, honest.partial)

    for doctored, expected in (
        ({**truthful, "withheld": []}, "not the certified set difference"),
        ({**truthful, "partial": False}, "for an envelope whose partial is"),
        ({**truthful, "withheld": [{"id": "m9"}]}, "not the certified set difference"),
        ({**truthful, "withheld": ["m2"]}, "not a mapping carrying an id"),
    ):
        with pytest.raises(DispositionInvariantError) as raised:
            _the_emitted_disposition_is_the_certified_one(doctored, certificate, honest.partial)
        assert expected in str(raised.value)

    with pytest.raises(DispositionInvariantError) as not_a_mapping:
        _the_emitted_disposition_is_the_certified_one(["not", "a", "mapping"], certificate, True)
    assert "is not a mapping" in str(not_a_mapping.value)


def test_the_emitted_form_check_is_actually_wired_into_the_serializer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """That the check exists is not that the check runs. The battery made the difference.

    This round's reintroduction battery reported `NOT CAUGHT` for deleting the call to
    `_the_emitted_disposition_is_the_certified_one` from the serializer: the test above drives
    the function directly, which establishes what the function does and nothing at all about
    whether anything calls it. That is precisely the shape round 13 was caught by - a test that
    discovered the validators and then ran them itself - and it was in this round's own work.

    So the wiring is observed: the module global is replaced, one dump is driven, and what the
    replacement received is compared with what the dump returned. A check on the emitted form
    that is handed something other than the emitted form would pass every other test here.
    """
    seen: list[tuple[Any, Any, bool]] = []

    def recording(dumped: Any, certificate: Any, stated_partial: bool) -> None:
        seen.append((dumped, certificate, stated_partial))

    monkeypatch.setattr(
        "mailweave.envelope.response._the_emitted_disposition_is_the_certified_one", recording
    )

    honest = honest_envelope()
    produced = honest.model_dump(mode="json")

    assert len(seen) == 1, "the serializer did not call the emitted-form check exactly once"
    handed, certificate, stated = seen[0]
    assert handed == produced, "the check was handed something other than the wire form"
    assert certificate is honest.disposition
    assert stated is honest.partial


def test_the_emitted_form_check_refuses_from_inside_the_serializer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """And what it raises reaches the caller, wrapped, rather than being swallowed."""

    def always_refuses(dumped: Any, certificate: Any, stated_partial: bool) -> None:
        raise DispositionInvariantError("the emitted form was checked and refused")

    monkeypatch.setattr(
        "mailweave.envelope.response._the_emitted_disposition_is_the_certified_one",
        always_refuses,
    )

    with pytest.raises(Exception) as raised:
        honest_envelope().model_dump(mode="json")
    assert "the emitted form was checked and refused" in str(raised.value)


def test_a_partial_dump_is_not_treated_as_a_missing_disposition() -> None:
    """`model_dump(include=...)` legitimately emits one field, and must not be refused.

    The narrowness is the claim: a key that is absent is not checked. Stated here as a test so
    that "this function checks two fields and only two" is a property somebody can read off the
    suite rather than a sentence in a docstring.
    """
    honest = honest_envelope()

    assert honest.model_dump(include={"partial"}) == {"partial": True}
    narrowed = honest.model_dump(include={"withheld", "partial"})
    assert set(narrowed) == {"withheld", "partial"}
    assert [record["id"] for record in narrowed["withheld"]] == ["m2"]


def test_a_certificate_a_second_ledger_minted_is_still_refused_by_the_digest() -> None:
    """The mint check must not have replaced the binding to *this* payload.

    Both are needed and they answer different questions: the mint says `certify` made this
    object, the digest says it was computed against this disclosed set. A round that added the
    first and dropped the second would pass every test above.
    """
    honest = honest_envelope()

    # A second ledger that agrees with the first about everything the envelope cross-checks -
    # the same H, the same per-rung counts, the same withheld record - and was certified
    # against a *different disclosed set*. That leaves the digest as the only thing that can
    # refuse it, which is what makes this a test of the digest rather than of whichever
    # validator happens to run first.
    other = ledger_with_hits("m1", "m2", threads={"m1": "t1", "m2": "t9"})
    other.note_withheld(
        message_id="m2",
        cap=WithheldCap.MAX_HIT_THREADS,
        why="31 hit-bearing threads; 12 mapped",
        affordance=kit.thread_affordance("t9"),
    )
    foreign = other.certify(["m1", "an-id-this-response-does-not-carry"])

    assert foreign.withheld_ids == honest.disposition.withheld_ids
    assert foreign.hits_per_rung == honest.disposition.hits_per_rung
    assert foreign.disclosure_digest != honest.disposition.disclosure_digest

    fields: dict[str, Any] = {name: getattr(honest, name) for name in Envelope.model_fields}
    fields["disposition"] = foreign

    assert_is_a_minted_certificate(foreign)  # it *was* minted; that is not the question
    with pytest.raises(DispositionInvariantError) as raised:
        Envelope(**fields)
    assert "different disclosed set" in str(raised.value)
