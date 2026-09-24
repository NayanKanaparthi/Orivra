"""Facts about an object, held where the object cannot carry them (R-SEC-045, R-SEC-046).

Twice now this project has written a capability check against a value the object states
about itself, and twice the value turned out to be forgeable by ordinary code:

  * `SeedSession`'s proof bound `str(id(credential))`. An `id` is a memory address, and a
    memory address is *reused* the moment the object at it is freed - so an attacker who
    read a session's public fields, let the honest session go, and allocated credentials
    until one landed on the freed address held a session the use-site check authorised, for
    a credential that reports a different mailbox. Reproduced at 59/60 and 60/60 trials with
    no private name, no `object.__setattr__`, and the ordinary public constructor
    (R-SEC-045);
  * `DispositionCertificate` kept its certified numbers in its own slots and checked the
    mint token in `__init__`. `copy.copy` rebuilds the object without running `__init__`,
    and the slots behind read-only properties are writable, so two plain attribute
    assignments produced a certificate that stated `withheld = ()` for a ledger that had
    recorded a withheld hit - and `Envelope` accepted it (R-SEC-046).

Both defects have one shape: **the object was asked to vouch for itself**. What is needed is
a fact that the object cannot restate, that a copy of it does not inherit, and that a later
object landing on the same address cannot pick up.

## What this registry is

A side table, private to the process, keyed on **object identity** and holding whatever the
minting code established at the moment it established it. It is not a cache and not a weak
dictionary of convenience: it is where the *authority* lives, so that

  * an object that was never minted has no entry - which is what closes the id-reuse class,
    because an entry belongs to the object that was observed and dies with it;
  * a copy, a `pickle` round trip, a `__reduce_ex__` rebuild or an `object.__new__` shell is
    a **different object**, so it inherits nothing, whatever it copied out of `__dict__` or
    a `__slots__` layout. No construction path has to be enumerated, including the ones
    CPython has not shipped yet;
  * writing an attribute onto an object changes nothing the registry says.

`recall` is deliberately identity-based twice over: the dictionary is keyed by `id`, and the
entry then has to prove it belongs to *this* object (`ref() is subject`). The second check is
the one that matters. An `id` may be recycled while a stale entry is still in the table - the
weak-reference callback normally removes it first, but "normally" is not a property - and a
recycled `id` therefore finds an entry whose weak reference no longer resolves to the caller's
object. That returns `None`, which every caller treats as "never minted".

Note what the registry deliberately does **not** use: the subject's `__hash__` or `__eq__`.
A `WeakKeyDictionary` would consult both, so a second object that merely compares *equal* to
the minted one would inherit its authority - the same defect one axis over, on a value the
subject's own class controls.

## What it does not do

**It says nothing about a subclass, and that is not a small residue.** A registry makes the
facts unreachable except by asking it; it cannot make a caller ask. A subclass of the sealed
type overrides the properties that do the asking and answers whatever it likes, so the
registry is never consulted and nothing raises - which is R-RETR's round-3 attack on this
project's disposition token, one level up from where it was first met. The round-13
implementer found exactly that against `DispositionCertificate` **after** moving its facts in
here, by attacking its own fix. So both users of this registry refuse subclassing outright
(`SeedSession.__init_subclass__`, `DispositionCertificate.__init_subclass__`), and a third
user must do the same: keeping the facts here is half of the property and the other half is
that only this type can be the one reading them.

It is not a defence against code that imports the owning module and calls `remember` itself.
In process, no object can be made unforgeable by code running beside it, and nothing here
claims otherwise; what it removes is every route that *rebuilds or rewrites* a sealed object -
copying, reconstruction by any protocol, attribute writing, and allocation onto a freed
address - which is the class both findings came from.

It is per-process by construction. A subject that arrives from another process - unpickled,
handed over by a worker, read out of a cache - has no entry here and fails closed. That is
the intended behaviour and not an oversight: authority established in one process is not a
fact about another.
"""

from __future__ import annotations

import weakref
from typing import Any


class CannotBeSealed(TypeError):
    """The subject cannot be given a sealed identity, so no authority may rest on it.

    Raised for an object that does not support weak references - `object()` and instances of
    `__slots__` classes without `__weakref__` among them. Such an object cannot be told apart
    from a later object at the same address, which is exactly the defect this module exists
    to close, so it is refused at the mint rather than admitted with a weaker guarantee.
    """


class IdentityRegistry[Fact]:
    """What was established about an object, keyed by *that object* and dying with it.

    One instance per kind of authority, named at construction so a refusal can say which
    mint the subject is not in.
    """

    __slots__ = ("_entries", "_purpose")

    def __init__(self, purpose: str) -> None:
        self._purpose = purpose
        #: `id(subject) -> (weak reference to that subject, what was established)`. The
        #: weak reference is what makes the key mean the object rather than the address.
        self._entries: dict[int, tuple[weakref.ref[Any], Fact]] = {}

    @property
    def purpose(self) -> str:
        return self._purpose

    def remember(self, subject: object, fact: Fact) -> Fact:
        """Record `fact` against `subject`, and return it. Re-minting replaces the entry.

        Raises `CannotBeSealed` if the subject cannot be weakly referenced, because then the
        entry could outlive the object and be inherited by whatever is allocated next.
        """
        key = id(subject)
        entries = self._entries

        def forget(dead: weakref.ref[Any]) -> None:
            # Only if the entry is still *this* one: by the time a callback runs, the id
            # may have been re-registered by a later object, and deleting that object's
            # entry would silently revoke an authority nobody asked to revoke.
            current = entries.get(key)
            if current is not None and current[0] is dead:
                del entries[key]

        try:
            reference = weakref.ref(subject, forget)
        except TypeError as failure:
            raise CannotBeSealed(
                f"{type(subject).__name__} cannot be sealed for {self._purpose}: it does "
                "not support weak references, so this process cannot tell it apart from a "
                "later object allocated at the same address (R-SEC-045)"
            ) from failure
        entries[key] = (reference, fact)
        return fact

    def recall(self, subject: object) -> Fact | None:
        """What was established about *this* object, or `None` if nothing ever was.

        `None` is the answer for a subject that was never minted, for a copy or a rebuild of
        one that was, and for an object that happens to occupy the address of a dead entry.
        Callers must treat all three the same way, because they are the same fact: nothing
        was established about the object in hand.
        """
        entry = self._entries.get(id(subject))
        if entry is None:
            return None
        reference, fact = entry
        return fact if reference() is subject else None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"IdentityRegistry({self._purpose!r}, sealed={len(self._entries)})"
