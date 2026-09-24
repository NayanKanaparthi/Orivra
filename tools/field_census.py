"""Enumerate every field of every model in the envelope, ledger and content layers.

The round 7 audit claimed 187 fields "enumerated programmatically ... cannot silently
omit a field somebody forgot to look at". R-ARCH-024 ran the published script and got
**173**: `FetchedIds` and `DispositionCertificate` are plain classes carrying `__slots__`
rather than `BaseModel`s or dataclasses, so the script's two `issubclass`/`is_dataclass`
tests silently skipped both, and their 14 fields reached the audit table by hand. The
fields were accurate; the claim about how they got there was not, and the audit's whole
value rests on that claim.

This module is the corrected enumerator. Two things make the claim true rather than
asserted:

  * **every shape a field can hide in is read**, including a plain class's constructor
    signature - which is the caller-facing surface the audit tabulates for `FetchedIds`
    and `DispositionCertificate`, and the reason `token` appears in that table while the
    private `_consumed` latch does not;
  * **an unrecognised class raises** instead of being skipped. A new class in an audited
    module that is neither an enum, a pydantic model, a dataclass nor a plain class with
    its own `__init__` stops the census rather than quietly shrinking the total. That is
    the property the round 7 script claimed and did not have: silence on a shape it could
    not read.

`tests/test_field_census.py` pins the total, so the number in a review document cannot
drift away from the tree it describes.
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import inspect
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from importlib import import_module
from types import ModuleType
from typing import Final

from pydantic import BaseModel

#: The layers the audit covers: the response envelope, the disposition ledger, and the
#: content-layer model every `MessageRow` carries inside it.
AUDITED_MODULES: Final[tuple[str, ...]] = (
    "mailweave.envelope.wire",
    "mailweave.envelope.response",
    "mailweave.envelope.disposition",
    "mailweave.envelope.reasons",
    "mailweave.content.reductions",
)


class FieldCensusError(RuntimeError):
    """A class in an audited module whose fields this census cannot read.

    Raised rather than skipped. R-ARCH-024's finding is that a skip is invisible: the
    total simply comes out smaller and nothing says which shape was not read.
    """


@dataclass(frozen=True)
class FieldRecord:
    """One field, and which reading found it."""

    module: str
    owner: str
    field: str
    shape: str


def _pydantic_fields(cls: type[BaseModel]) -> Iterator[tuple[str, str]]:
    for name in cls.model_fields:
        yield name, "pydantic-field"
    for name in cls.model_computed_fields:
        yield name, "pydantic-computed"


def _dataclass_fields(cls: type) -> Iterator[tuple[str, str]]:
    for field in dataclasses.fields(cls):
        yield field.name, "dataclass-field"


def _named_tuple_fields(cls: type) -> Iterator[tuple[str, str]]:
    """The fields of a `typing.NamedTuple`, which are its `_fields`.

    Added in round 14, when `ObservedThread` and the certificate's own record became named
    tuples so that what a certificate hands back cannot be written through (R-ARCH-032). A
    named tuple is neither a dataclass nor a pydantic model and defines no `__init__` of its
    own, so the census refused it - correctly, and this is the extension it asked for rather
    than an exemption.
    """
    for name in cls._fields:  # type: ignore[attr-defined]
        yield name, "namedtuple-field"


def _is_named_tuple(cls: type) -> bool:
    return issubclass(cls, tuple) and hasattr(cls, "_fields")


def _constructor_parameters(cls: type) -> Iterator[tuple[str, str]]:
    """The caller-facing fields of a plain class: its own `__init__`'s parameters.

    This is the reading the round 7 audit table already used for `FetchedIds` and
    `DispositionCertificate` by hand, and it is the right one for a class that stores its
    state in private slots: the audit asks, of each field, whether a caller supplies it or
    the system derives it, and the constructor is where a caller supplies anything.
    `DispositionCertificate.token` is a field by that reading (the audit lists it, class D,
    "derived (capability)"); the private `_consumed` latch on `FetchedIds` is not, because
    no caller can state it.
    """
    signature = inspect.signature(vars(cls)["__init__"])
    for name, parameter in signature.parameters.items():
        if name == "self":
            continue
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        yield name, "constructor-parameter"


def _fields_of(cls: type) -> Iterator[tuple[str, str]] | None:
    """Every field of `cls`, or `None` when the class carries no data fields at all."""
    if issubclass(cls, enum.Enum):
        return None
    if issubclass(cls, BaseModel):
        return _pydantic_fields(cls)
    if dataclasses.is_dataclass(cls):
        return _dataclass_fields(cls)
    if _is_named_tuple(cls):
        return _named_tuple_fields(cls)
    if "__init__" in vars(cls):
        return _constructor_parameters(cls)
    raise FieldCensusError(
        f"{cls.__module__}.{cls.__qualname__} is not a pydantic model, a dataclass, an "
        "enum or a plain class with its own __init__, so this census cannot read its "
        "fields. Extend the census rather than leaving the class unread: a class the "
        "enumerator skips is a field the audit never sees, which is R-ARCH-024 exactly."
    )


def _classes(module: ModuleType) -> Iterator[type]:
    for obj in vars(module).values():
        if inspect.isclass(obj) and obj.__module__ == module.__name__:
            yield obj


def census(modules: Sequence[str] = AUDITED_MODULES) -> tuple[FieldRecord, ...]:
    """Every field in every class defined in `modules`, in declaration order."""
    records: list[FieldRecord] = []
    for module_name in modules:
        module = import_module(module_name)
        for cls in _classes(module):
            fields = _fields_of(cls)
            if fields is None:
                continue
            for name, shape in fields:
                records.append(
                    FieldRecord(module=module_name, owner=cls.__qualname__, field=name, shape=shape)
                )
    return tuple(records)


def per_module(records: Sequence[FieldRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.module] = counts.get(record.module, 0) + 1
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list", action="store_true", help="print every field, not only the totals"
    )
    args = parser.parse_args(argv)
    records = census()
    if args.list:
        for record in records:
            print(f"{record.module}\t{record.owner}.{record.field}\t{record.shape}")
    for module, count in per_module(records).items():
        print(f"{module}: {count}")
    print(f"TOTAL FIELDS: {len(records)}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
