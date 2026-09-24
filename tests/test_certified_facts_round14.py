"""R-ARCH-032: the single authoritative record, and what it takes for it to be one.

Round 13's insight was right - move the facts off the certificate so that a copy of one
states *nothing* rather than something false - and its execution left the record itself
writable:

    facts = envelope.disposition._certified
    vars(facts)["withheld"]  = ()
    vars(facts)["hit_count"] = 1
    envelope.model_copy(update={"withheld": (), "partial": False}).model_dump()

published `withheld: []`, `partial: false` for a response that dropped a message, through the
ordinary constructor with every validator running and passing. That is worse than the finding
it replaced: R-SEC-046 produced a *second, lying* certificate that could in principle be told
apart from the true one, and this rewrites the only record there is, so every cross-check
agrees with the lie and nothing in the process still knows the truth.

The tests here are in three groups, and the middle one is the one that matters:

  * the **fix direction**, executed rather than taken from a review - a `NamedTuple` refuses
    `object.__setattr__` and a `@dataclass(frozen=True, slots=True)` does not;
  * the **property**, over the object graph rather than over the record this round happened to
    change: nothing a certificate hands back can be written through. That is checked by
    walking what the properties return, so a value added in a later round is covered the day
    it exists;
  * the **peers**, which is where the round-13 fix went wrong and where this one could: the
    `WithheldRecord`s inside the immutable record, the mappings behind a `mappingproxy`, and
    the one-shot latch on `FetchedIds`.
"""

from __future__ import annotations

import copy
import gc
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, NamedTuple

import pytest
from pydantic_core import PydanticSerializationError

from mailweave.envelope.disposition import (
    DispositionCertificate,
    DispositionLedger,
    ObservedThread,
)
from mailweave.envelope.reasons import RungId
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import WithheldCap
from mailweave.errors import DispositionInvariantError
from tests.fixtures import envelope_kit as kit
from tests.test_disposition_invariant import build, ledger_with_hits


def honest_envelope() -> Envelope:
    """`m1` disclosed, `m2` withheld: the envelope R-ARCH-032 rewrote the facts of."""
    ledger = ledger_with_hits("m1", "m2", threads={"m1": "t1", "m2": "t9"})
    ledger.note_withheld(
        message_id="m2",
        cap=WithheldCap.MAX_HIT_THREADS,
        why="31 hit-bearing threads; 12 mapped",
        affordance=kit.thread_affordance("t9"),
    )
    return build(ledger, lambda nonce: [kit.source("t1", [kit.row("m1", "t1", 0, nonce=nonce)])])


# --- the fix direction, established here rather than taken on anyone's word -------------------


def test_a_named_tuple_refuses_the_writes_a_frozen_dataclass_allows() -> None:
    """The three shapes and the three writes, run rather than cited.

    R-ARCH reported this and so did the orchestrator, and the work order said explicitly not
    to take it on their word. The row that decides the fix is the middle one: `slots=True`
    removes the instance `__dict__`, so `vars()` stops working and `object.__setattr__` does
    **not** - which would have left the finding open through a different two lines.
    """

    @dataclass(frozen=True)
    class Plain:
        value: int = 0

    @dataclass(frozen=True, slots=True)
    class Slotted:
        value: int = 0

    class Tupled(NamedTuple):
        value: int = 0

    plain, slotted, tupled = Plain(), Slotted(), Tupled()

    # a frozen dataclass keeps a __dict__, and `frozen=True` guards only __setattr__
    assert hasattr(plain, "__dict__")
    vars(plain)["value"] = 99
    assert plain.value == 99
    object.__setattr__(plain, "value", 98)
    assert plain.value == 98

    # slots closes the first write and leaves the second
    assert not hasattr(slotted, "__dict__")
    with pytest.raises(TypeError):
        vars(slotted)
    object.__setattr__(slotted, "value", 97)
    assert slotted.value == 97, "frozen+slots does NOT refuse object.__setattr__"

    # a named tuple refuses all three
    assert not hasattr(tupled, "__dict__")
    with pytest.raises(TypeError):
        vars(tupled)
    written: Any = tupled
    with pytest.raises(AttributeError):
        object.__setattr__(tupled, "value", 96)
    with pytest.raises(AttributeError):
        written.value = 95
    assert tupled.value == 0


def test_a_mapping_proxy_is_read_only_only_to_a_caller_who_does_not_reach_behind_it() -> None:
    """Why the mappings are rebuilt per read instead of wrapped.

    `MappingProxyType` is the obvious way to hand out a read-only view, and it was what the
    certificate used. It is read-only at its own surface; the dict it wraps is one
    `gc.get_referents` away and writing into that changes what the proxy reports. A copy
    nobody else holds has no such referent to reach.
    """
    behind = {"m1": "t1"}
    proxy = MappingProxyType(behind)

    with pytest.raises(TypeError):
        proxy["m1"] = "t9"  # type: ignore[index]

    reached = [item for item in gc.get_referents(proxy) if isinstance(item, dict)]
    assert reached == [behind], "the underlying dict is reachable from the proxy"
    reached[0]["m1"] = "t9"
    assert proxy["m1"] == "t9", "and writing through it changes what the proxy says"


# --- the finding itself, line for line --------------------------------------------------------


def test_r_arch_032_fails_where_it_is_written() -> None:
    """The reviewer's reproduction, verbatim: two plain writes into `vars(facts)`."""
    envelope = honest_envelope()
    facts = envelope.disposition._certified

    assert not hasattr(facts, "__dict__")
    with pytest.raises(TypeError) as raised:
        vars(facts)["withheld"] = ()
    assert "__dict__" in str(raised.value)

    for name in ("withheld", "hit_count", "disclosed_hits", "disclosure_digest"):
        with pytest.raises(AttributeError):
            object.__setattr__(facts, name, ())
        with pytest.raises(AttributeError):
            setattr(facts, name, ())

    assert envelope.disposition.hit_count == 2
    assert envelope.disposition.withheld_ids == {"m2"}
    assert envelope.model_dump(mode="json")["partial"] is True


def test_the_lift_attack_needs_a_write_that_no_longer_lands() -> None:
    """ "A certificate cannot be lifted from one response and attached to another."

    R-ARCH falsified that sentence by rewriting `disclosure_digest`, `observed_threads` and the
    counts on the facts object, after which response A's certificate validated response B's
    payload. The digest is now a field of a named tuple held in the registry, so the write that
    made the lift possible does not land, and the lift is refused by the digest comparison it
    was designed to defeat.
    """
    a = honest_envelope()
    other = ledger_with_hits("b1", "b2", thread="t2")
    b = build(
        other,
        lambda nonce: [
            kit.source(
                "t2",
                [kit.row("b1", "t2", 0, nonce=nonce), kit.row("b2", "t2", 1, nonce=nonce)],
            )
        ],
    )
    facts = a.disposition._certified

    with pytest.raises(AttributeError):
        object.__setattr__(facts, "disclosure_digest", b.disposition.disclosure_digest)

    fields: dict[str, Any] = {name: getattr(b, name) for name in Envelope.model_fields}
    fields["disposition"] = a.disposition
    with pytest.raises(DispositionInvariantError) as raised:
        Envelope(**fields)
    # The first cross-check to notice is the withheld comparison, because A's certificate
    # still certifies `m2` and B's payload withholds nothing. Rewriting *that* was the other
    # half of the lift, and it needs the same write that no longer lands.
    assert "disagrees with the certified set difference" in str(raised.value)


# --- the property, over the graph rather than over the field this round changed ---------------


def _writes_refused(value: object) -> list[str]:
    """Every way this test knows to write into `value` that is **not** refused.

    Deliberately not "is it a `NamedTuple`": the property is that a caller cannot write, not
    that a particular type was chosen, so what is asserted is the behaviour. A mutable
    container is acceptable only if it is a *copy* - handled by the caller below, which reads
    the property twice and checks that a write into the first reading is not visible in the
    second.
    """
    landed: list[str] = []
    for name in getattr(type(value), "_fields", ()):
        try:
            object.__setattr__(value, name, "written")
        except (AttributeError, TypeError):
            continue
        landed.append(f"object.__setattr__({name})")
    if hasattr(value, "__dict__") and not isinstance(value, type):
        landed.append("has an instance __dict__")
    return landed


CERTIFICATE_PROPERTIES = (
    "hit_count",
    "disclosed_hits",
    "withheld",
    "withheld_ids",
    "disclosure_digest",
    "observed_threads",
    "hits_per_rung",
    "observed_positions",
    "observed_internal_dates",
    "observed_thread_facts",
)


@pytest.mark.parametrize("name", CERTIFICATE_PROPERTIES)
def test_every_value_a_certificate_hands_back_refuses_to_be_written(name: str) -> None:
    """The property, asked of each reading rather than of the record behind them.

    Two questions per property, and they are different: is the object handed back writable at
    all, and - if it is a mutable container, which a fresh `dict` is - does writing into it
    change what the certificate says next time. The second is what makes rebuilding the
    mappings per read a defence rather than a style choice.
    """
    certificate = kit_certificate()

    first = getattr(certificate, name)
    landed = _writes_refused(first)
    assert landed == [], f"{name} hands back something writable: {landed}"

    if isinstance(first, dict):
        first["planted"] = "written"
        assert "planted" not in getattr(certificate, name), (
            f"{name} hands back the registry's own mapping: a write into what a caller was "
            "given changed what the certificate states"
        )
    else:
        # A scalar, a frozenset or a tuple of sealed records. Nothing to write into, which
        # `_writes_refused` has just established; asserted here so the parametrisation cannot
        # pass a case by having nothing to check.
        assert isinstance(first, int | str | frozenset | tuple)


def kit_certificate() -> DispositionCertificate:
    ledger = ledger_with_hits("m1", "m2", threads={"m1": "t1", "m2": "t9"})
    ledger.note_withheld(
        message_id="m2",
        cap=WithheldCap.MAX_HIT_THREADS,
        why="one thread over the map cap",
        affordance=kit.thread_affordance("t9"),
    )
    return ledger.certify(["m1"])


def test_the_thread_facts_a_certificate_hands_back_are_named_tuples_not_dataclasses() -> None:
    """`ObservedThread` is handed out and is read by two validators, so it is sealed too.

    Not a redundant restatement of the sweep above: this is the shape the walk would have
    passed over if `_writes_refused` had only asked about the record. A frozen dataclass here
    would let `vars(fact)["stated_total"] = 99` defeat
    `_stated_total_is_the_one_the_observation_stated`, which is A6's whole point.
    """
    ledger = DispositionLedger()
    ledger.record_thread(
        kit.fully_observed_thread(("m1", "m2"), "t1", stated_total=2),
        rung=RungId.L1,
    )
    fact = ledger.certify(["m1", "m2"]).observed_thread_facts["t1"]

    assert isinstance(fact, ObservedThread)
    assert not hasattr(fact, "__dict__")
    with pytest.raises(AttributeError):
        object.__setattr__(fact, "stated_total", 99)


# --- the peers: what is *inside* the immutable record -----------------------------------------


def test_a_withheld_record_rewritten_after_certification_is_refused() -> None:
    """The peer of this round's own fix, and the reason `withheld_seal` exists.

    A `WithheldRecord` is a Pydantic model, so it has an instance `__dict__` and
    `vars(record)["id"] = "m9"` walks past `frozen=True` - the same two lines as R-SEC-046, two
    levels down. Sealing the container and trusting its contents would have been this
    project's own defect for the eleventh time; worse, the envelope compares its records
    against *these same objects*, so both sides would have agreed about the new id and nothing
    would have disagreed with the lie.
    """
    envelope = honest_envelope()
    record = envelope.disposition._certified.withheld[0]

    assert record.id == "m2"
    vars(record)["id"] = "m9"  # lands: the model is not this module's type to seal
    assert record.id == "m9"

    with pytest.raises(DispositionInvariantError) as raised:
        _ = envelope.disposition.withheld
    assert "rewritten since certify minted it" in str(raised.value)

    with pytest.raises(PydanticSerializationError) as at_the_wire:
        envelope.model_dump(mode="json")
    assert "rewritten since certify minted it" in str(at_the_wire.value)


def test_a_rewritten_reason_is_refused_as_well_as_a_rewritten_id() -> None:
    """The seal is over the record's whole wire form, not over the field this test thought of.

    `why` and the affordance are what make a withheld message *reachable* (contract R-06), so
    a response that keeps the id and rewrites the reason is still stating something the ledger
    did not compute. The material is each record's own `model_dump`, so a field added to
    `WithheldRecord` later is covered without anyone remembering this.
    """
    envelope = honest_envelope()
    record = envelope.disposition._certified.withheld[0]
    vars(record)["why"] = "no reason at all"

    with pytest.raises(DispositionInvariantError):
        _ = envelope.disposition.withheld_ids


def test_an_honest_certificate_reads_its_records_as_many_times_as_it_likes() -> None:
    """The seal must not fire on the legitimate case, which it would if it were order- or
    identity-sensitive rather than content-sensitive."""
    certificate = kit_certificate()

    for _ in range(3):
        assert {record.id for record in certificate.withheld} == {"m2"}
        assert certificate.withheld_ids == {"m2"}
    certificate.assert_minted()


# --- the peer one module over: the one-shot latch (R-ARCH-036) --------------------------------


def test_the_one_shot_latch_cannot_be_re_armed() -> None:
    """`object.__setattr__(page, "_consumed", False)` produced the second `scan_scope` entry
    the refusal says it prevents.

    Amendment A1's over-recording residue is about the *public constructor* and is untouched:
    a caller who wants two observations of one call builds two pages. What is closed is the
    claim this refusal makes about *this* object.
    """
    ledger = DispositionLedger()
    page = kit.fetched(("m1",), thread_ids={"m1": "t1"})
    ledger.record_list_page(page, rung=RungId.L1, query="from:amy")
    assert len(ledger.scan_scope) == 1

    object.__setattr__(page, "_consumed", False)
    assert page.recorded is True, "the latch is held where the object cannot restate it"

    with pytest.raises(DispositionInvariantError) as raised:
        ledger.record_list_page(page, rung=RungId.L1, query="from:amy OR from:bob")
    assert "already recorded its ids" in str(raised.value)
    assert len(ledger.scan_scope) == 1


def test_a_copy_of_a_recorded_page_is_still_refused() -> None:
    """The half the registry does **not** buy, which is why the slot is kept beside it.

    A copy is a different object, so it has no registry entry; it does carry `_consumed`,
    which is what refuses it. Removing either half re-opens a route, and the two routes are
    not the same.
    """
    ledger = DispositionLedger()
    page = kit.fetched(("m1",), thread_ids={"m1": "t1"})
    ledger.record_list_page(page, rung=RungId.L1, query="from:amy")

    with pytest.raises(DispositionInvariantError):
        ledger.record_list_page(copy.copy(page), rung=RungId.L1, query="from:amy")
