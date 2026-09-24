"""The identity registry: what it establishes, and the two defects it exists to close.

`mailweave.sealing` is the answer to R-SEC-045 and R-SEC-046, which are one defect wearing two
hats: **an object was asked to vouch for itself**, once through a memory address it happened to
occupy and once through slots behind read-only properties. The tests here are about the
primitive rather than about either caller, because the primitive is what both rest on and a
property proved once at each call site is a property proved twice by accident.
"""

from __future__ import annotations

import copy
import gc
import pickle
import weakref
from collections.abc import Callable

import pytest

from mailweave.sealing import CannotBeSealed, IdentityRegistry


class Subject:
    """An ordinary object: weak-referenceable, and hashable and comparable by identity."""

    def __init__(self, name: str = "a") -> None:
        self.name = name


def test_what_was_established_comes_back_for_the_object_it_was_established_for() -> None:
    registry: IdentityRegistry[str] = IdentityRegistry("subjects under test")
    subject = Subject()

    assert registry.recall(subject) is None
    assert registry.remember(subject, "fact") == "fact"
    assert registry.recall(subject) == "fact"
    assert registry.recall(Subject()) is None


def test_a_copy_of_a_sealed_object_inherits_nothing() -> None:
    """R-SEC-046's shape: `copy.copy` rebuilds an object without running `__init__`.

    Whatever a copy carried out of `__dict__` or a `__slots__` layout, it is a different
    object, so it is not in the registry. This is why no construction path has to be
    enumerated - and the list would have to include `pickle` and `__reduce_ex__`, which are
    checked here beside `copy`, plus the ones CPython has not shipped.
    """
    registry: IdentityRegistry[str] = IdentityRegistry("subjects under test")
    subject = Subject()
    registry.remember(subject, "fact")

    rebuilds: tuple[Callable[[Subject], Subject], ...] = (
        copy.copy,
        copy.deepcopy,
        lambda item: pickle.loads(pickle.dumps(item)),
        lambda item: pickle.loads(pickle.dumps(item, 2)),
    )
    for rebuild in rebuilds:
        rebuilt = rebuild(subject)
        assert rebuilt is not subject
        assert registry.recall(rebuilt) is None, f"{rebuild} inherited the seal"

    shell = object.__new__(Subject)
    shell.__dict__.update(subject.__dict__)
    assert registry.recall(shell) is None


def test_writing_attributes_onto_a_sealed_object_changes_nothing_it_recalls() -> None:
    registry: IdentityRegistry[str] = IdentityRegistry("subjects under test")
    subject = Subject()
    registry.remember(subject, "fact")

    subject.name = "rewritten"
    object.__setattr__(subject, "name", "rewritten again")

    assert registry.recall(subject) == "fact"


def test_the_entry_dies_with_its_subject() -> None:
    registry: IdentityRegistry[str] = IdentityRegistry("subjects under test")
    subject = Subject()
    registry.remember(subject, "fact")
    key = id(subject)

    del subject
    gc.collect()

    assert key not in registry._entries


def test_an_object_at_a_dead_entrys_address_recalls_nothing() -> None:
    """The R-SEC-045 state, reached deterministically rather than through the allocator.

    A recycled address produces exactly this: an entry keyed by an id that a *different*
    object now occupies. The weak reference is what tells the two apart, and it is the check
    that matters - the dictionary key is an address and an address is not an identity.
    """
    registry: IdentityRegistry[str] = IdentityRegistry("subjects under test")
    successor = Subject("successor")
    collected = Subject("collected")
    stale = weakref.ref(collected)
    del collected
    gc.collect()

    registry._entries[id(successor)] = (stale, "the collected subject's fact")

    assert registry.recall(successor) is None


def test_re_minting_replaces_the_entry_rather_than_keeping_two() -> None:
    registry: IdentityRegistry[str] = IdentityRegistry("subjects under test")
    subject = Subject()

    registry.remember(subject, "first")
    registry.remember(subject, "second")

    assert registry.recall(subject) == "second"
    assert len(registry._entries) == 1


def test_a_late_callback_does_not_revoke_a_later_subjects_seal() -> None:
    """A dead subject's callback must not delete an entry a *successor* legitimately holds.

    The callback fires when the interpreter gets round to it, which may be after another
    object has been sealed at the same address. Deleting that object's entry would revoke an
    authority nobody asked to revoke - a fail-open in the other direction, where a real
    certificate silently stops being one.
    """
    registry: IdentityRegistry[str] = IdentityRegistry("subjects under test")
    first = Subject("first")
    registry.remember(first, "first fact")
    key = id(first)
    dead_reference, _ = registry._entries[key]

    successor = Subject("successor")
    registry._entries[key] = (weakref.ref(successor), "successor fact")
    del first
    gc.collect()

    assert registry._entries.get(key, (None, None))[1] == "successor fact"
    assert dead_reference() is None


def test_an_object_that_cannot_be_weakly_referenced_is_refused() -> None:
    """Refused at the mint rather than sealed against an address.

    `object()` is the case R-SEC's reproduction reached for: it has no `__weakref__`, so this
    process could not tell it apart from whatever is allocated at its address next, and a seal
    that cannot do that is the defect rather than a weaker version of the fix.
    """
    registry: IdentityRegistry[str] = IdentityRegistry("subjects under test")

    with pytest.raises(CannotBeSealed) as raised:
        registry.remember(object(), "fact")
    assert "weak references" in str(raised.value)
    assert "subjects under test" in str(raised.value)


def test_the_registry_does_not_consult_the_subjects_own_equality() -> None:
    """A `WeakKeyDictionary` would, and a class controls both `__eq__` and `__hash__`.

    So a second object that merely compares equal to a sealed one would inherit its
    authority - the same defect one axis over, on a value the subject's own class decides.
    """

    class SaysItIsEveryone:
        def __eq__(self, other: object) -> bool:
            return True

        def __hash__(self) -> int:
            return 0

    registry: IdentityRegistry[str] = IdentityRegistry("subjects under test")
    sealed = SaysItIsEveryone()
    registry.remember(sealed, "fact")

    assert registry.recall(sealed) == "fact"
    assert registry.recall(SaysItIsEveryone()) is None
