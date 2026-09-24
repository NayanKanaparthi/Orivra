"""The reader half of the seal: a model that re-establishes itself where it is emitted.

`mailweave.sealing` holds what a sealed *object* is - facts kept where the object cannot
restate them. This module holds the other half of the same property, the one round 13 stated
and did not build: **only this type may be the one reading them.**

    "keeping the facts here is half of the property and the other half is that only this type
    can be the one reading them" - `sealing.py`

The type that reads a `DispositionCertificate` is `Envelope`, and it was an ordinary Pydantic
model. Three public routes each published `partial: false`, `withheld: []` for a certificate
that still certified a withheld id, and a fourth was found while closing them (R-ARCH-033). One
level down, the wire form re-established seventeen of the envelope tree's forty-one
after-validators, so a message could be placed at position 900 of a two-message thread
(R-ARCH-034). Both are the same defect at different scopes: something other than the class this
repository declared decided what reached the wire.

It lives at the top of the package, beside `sealing.py`, because the models that reach the
wire do not share one - `mailweave.envelope.wire`, `mailweave.envelope.reasons` and
`mailweave.content.reductions` all put models in a response - and a base that only some of them
could import would be a base that covered only some of them, which is the shape of the defect
rather than a fix for it. Inside `mailweave.envelope` it would also be a circular import, since
`content.reductions` is below `envelope` in the import order.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from typing import Any

from pydantic import BaseModel, SerializerFunctionWrapHandler, model_serializer

#: Cached per class: `_after_validators_of` walks an MRO and reads decorator tables, and it
#: is called on every model of every payload that is serialised.
_AFTER_VALIDATORS: dict[type[BaseModel], tuple[Callable[[Any], Any], ...]] = {}


def _after_validators_of(model_class: type[BaseModel]) -> tuple[Callable[[Any], Any], ...]:
    """Every `mode="after"` model validator declared by `model_class` **or any base of it**.

    Discovery, not a list - a validator added in a later round is covered the day it exists.
    What changed in round 14 is *where* the discovery reads from. It used to read
    `type(self).__pydantic_decorators__`, which is the **merged** table: a subclass method of
    the same name **replaces** the base's entry there, so the loop faithfully ran the
    attacker's no-op and the original was gone (R-ARCH-033, route (a)). Discovery off the
    runtime class is a strength against forgetting and, read that way, a weakness against
    overriding.

    Each class in the MRO owns a `__pydantic_decorators__` in its own `__dict__`, holding the
    functions *it* declared, so collecting across the MRO and de-duplicating by function
    identity gives a rule that is easy to state and hard to get around: **a subclass may add
    a validator; it cannot remove one.** The subclass's own entries run first, because that
    is MRO order, and running an extra no-op costs nothing.
    """
    cached = _AFTER_VALIDATORS.get(model_class)
    if cached is not None:
        return cached
    found: list[Callable[[Any], Any]] = []
    seen: set[int] = set()
    for klass in model_class.__mro__:
        decorators = klass.__dict__.get("__pydantic_decorators__")
        if decorators is None:
            continue
        for validator in decorators.model_validators.values():
            if validator.info.mode != "after":
                continue
            function = validator.func
            if id(function) in seen:
                continue
            seen.add(id(function))
            found.append(function)
    collected = tuple(found)
    _AFTER_VALIDATORS[model_class] = collected
    return collected


#: The containers this walk descends into. Anything else is a leaf, which is a real residue
#: and is why `test_the_walk_reaches_every_model_the_annotations_can_hold` exists: it decomposes
#: every field annotation in the envelope tree and fails if a model is ever declared inside a
#: container not in this tuple. Enumerating what a walk *can* enter and pinning the schema to
#: it is the move `preflight/record.py` made for the same reason (R-SEC-048).
_DESCENDED = (Mapping, Sequence, AbstractSet)


def _models_within(value: object, found: list[BaseModel]) -> None:
    """Every `BaseModel` instance reachable from `value` through the containers above."""
    if isinstance(value, BaseModel):
        found.append(value)
        return
    if isinstance(value, str | bytes | bytearray):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _models_within(key, found)
            _models_within(item, found)
        return
    if isinstance(value, Sequence | AbstractSet):
        for item in value:
            _models_within(item, found)


def re_establish(model: BaseModel) -> None:
    """Run every after-validator of `model`'s class and its bases against `model`."""
    for validator in _after_validators_of(type(model)):
        validator(model)


def re_establish_tree(root: BaseModel) -> None:
    """Re-establish the invariants of `root` **and of every model inside it** (R-ARCH-034).

    Round 13 put the re-establishment in a `mode="wrap"` model serializer on `Envelope` and
    ran `type(self).__pydantic_decorators__` - seventeen of the forty-one after-validators in
    the envelope tree, and none of `Source`'s seven, `MessageRow`'s four or
    `RetrievalReport`'s three. `envelope.model_copy(update={"sources": (...)})` - R-SEC-047's
    own reproduction line, one field over - therefore put a message at position 900 of a
    two-message thread on the wire, which is exactly what amendment A3 says must raise rather
    than be clamped, "because clamping would silently move evidence".

    That was the project's tenth "one shape validated, peers trusted", inside the fix for the
    ninth. The answer is not to list the nested models: it is to walk what is actually about
    to be emitted. The walk is driven from the top rather than left to each nested model's own
    serializer, so a payload still gets checked when a node's serializer is not the one this
    module wrote.
    """
    seen: set[int] = set()
    pending: list[BaseModel] = [root]
    while pending:
        model = pending.pop()
        if id(model) in seen:
            continue
        seen.add(id(model))
        re_establish(model)
        nested: list[BaseModel] = []
        for value in vars(model).values():
            _models_within(value, nested)
        pending.extend(nested)


class SealedModel(BaseModel):
    """A model that re-establishes its own invariants where it is emitted, and cannot be
    replaced by another class in the payload.

    **A wire model may not be extended** (R-ARCH-033). Round 13 sealed
    `DispositionCertificate` against subclassing on an argument it stated in terms - "keeping
    the facts here is half of the property and the other half is that only this type can be
    the one reading them" - and did not carry it to the type that does the reading. `Envelope`
    was an ordinary Pydantic model, and three public routes each published `partial: false`,
    `withheld: []` for a certificate that still certified a withheld id: redefine an
    after-validator by name, override the method that discovers them, or replace the wrap
    serializer by name. A fourth, found here rather than filed by a reviewer: a subclass
    `field_serializer` rewrites a field on the way out *after* every check has passed.

    None of the four is defeated by defending the previous one, and enumerating them is the
    habit this project keeps paying for. What they share is that a *substituted class*
    reaches the wire in place of the one this repository declared, so that is what is refused:
    a subclass of a model that declares fields is refused at class creation. Extending a base
    that declares none - `wire.Frozen`, `reasons._ReasonBase`, and this class - is how the
    schema itself is written and stays allowed.

    The rule is enforced in `__init_subclass__` rather than `__pydantic_init_subclass__`
    because `type.__new__` invokes the first and not the second, and supplying
    `__init_subclass__` in the new class's own namespace does not help: CPython looks the hook
    up with `super(type, type)`, which skips the class being created. Both are executed in
    `tests/test_reader_seal_round14.py` rather than assumed.

    What it is **not**: a defence against code in this process that reaches for this module
    and edits it. That residue is `sealing.py`'s, unchanged and unclosable in-process.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        extended = [
            base.__name__
            for base in cls.__mro__[1:]
            if isinstance(base, type)
            and issubclass(base, BaseModel)
            and base is not BaseModel
            and getattr(base, "model_fields", {})
        ]
        if extended:
            raise TypeError(
                f"{cls.__name__} may not extend {extended[0]}: a wire model that declares "
                "fields is the class this repository put on the wire, and a subclass of it is "
                "a different reader in its place - it can replace an after-validator by name, "
                "the model serializer that re-establishes them, or a field serializer that "
                "rewrites the value after every check has passed. Each of those published "
                "`partial: false` for a response missing a message (R-ARCH-033). Add a field "
                "to the model itself, or build a new one on a base that declares none"
            )

    @model_serializer(mode="wrap")
    def _the_wire_form_states_only_what_still_holds(
        self, handler: SerializerFunctionWrapHandler
    ) -> Any:
        """The chokepoint, for every model that reaches the wire (R-SEC-047, R-ARCH-034).

        Whatever produced the object - the builder, `model_copy`, `model_construct`, a write
        into `__dict__` past `frozen=True` - what a caller sends is what this returns, and it
        returns nothing for a payload whose own contents no longer support what it says.

        `re_establish_tree` rather than "this model's own validators": a model is checked with
        everything inside it, so serialising a `Source` re-establishes its rows' invariants
        too. `Envelope` overrides this with the same shape plus a check on the *emitted* form.

        The refusal surfaces as Pydantic's `PydanticSerializationError` wrapping the invariant
        error, because Pydantic wraps whatever a serializer raises. The wrapped message
        carries the invariant's own text; the type does not survive, which is a real cost of
        checking here rather than in a hand-written `to_wire`, taken deliberately: a method
        callers must remember to call is a check the next consumer skips.
        """
        re_establish_tree(self)
        return handler(self)
