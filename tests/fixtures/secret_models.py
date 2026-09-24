"""Finding every model that touches a secret, by reflection rather than by list (R-SEC-043).

R-SEC-043 was reported against one field of one model. The canary that should have caught it
walked five *flows* and grepped four secrets, so it could only ever find a leak on a path
somebody had thought to walk - and the validation path was not one of them.

A list of secret-bearing models would have the same shape as that canary: correct on the day
it is written, silently incomplete the day a model is added. So the models are **discovered**:
both source trees are imported, every `pydantic.BaseModel` subclass defined in them is
examined, and any that declares a secret type anywhere in a field annotation is a model whose
validation failures the canary must drive. A new secret-bearing model is covered the moment it
exists, and a model that stops carrying a secret drops out on its own.

## R-SEC-050: three shapes the discovery missed, and each of them leaked

The reflection is the right idea and it was narrower than it read. R-SEC planted models and
drove each to a `ValidationError` quoting the planted secret in full:

  * `part is SecretStr` is an **identity** test, so a `SecretStr` *subclass* was not a secret;
  * **`SecretBytes` was not considered at all**, though it is the same Pydantic secret wrapper
    for the same purpose;
  * a model that is **not a module-level name** - nested in a class, or built by a factory -
    is never in `vars(module)`, so it was never examined.

The first two are fixed by asking `issubclass` against both wrappers. The third is fixed for
nested classes by walking each class's own namespace as well as the module's. A model built
*inside a function* remains undiscoverable by any reflection - it is in no namespace until the
function runs - so it is not fixed here; instead
`tests/test_standing_cycle_round13.py::test_no_model_is_defined_where_reflection_cannot_find_it`
refuses one at the source level. Between the two, either a model is discoverable or the build
fails, which is what "covered the moment it exists" has to mean to be worth saying.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterator, Mapping
from types import ModuleType
from typing import Any, Final

from pydantic import BaseModel, SecretBytes, SecretStr

import mailweave
import mailweave_harness
from mailweave.validation import annotation_parts

#: The two source trees. `mailweave_harness` is included because the harness holds the
#: credential that can delete mail, so "no model here carries a secret today" is a fact to
#: be re-established on every run rather than assumed.
PACKAGES = (mailweave, mailweave_harness)


def _modules() -> Iterator[ModuleType]:
    for package in PACKAGES:
        yield package
        for info in pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}."):
            yield importlib.import_module(info.name)


#: Pydantic's secret wrappers. Both, because both hide a value from a `repr` for the same
#: reason, and a canary that knows about one of them is a canary with a `SecretBytes`-shaped
#: hole in it (R-SEC-050).
SECRET_TYPES: Final[tuple[type, ...]] = (SecretStr, SecretBytes)


def _mentions_secret(annotation: Any) -> bool:
    """Whether a secret wrapper appears anywhere in a field annotation, at any generic depth.

    `issubclass`, not `is`: a `SecretStr` subclass is a secret by every argument that makes
    `SecretStr` one, and an identity test said it was not (R-SEC-050).

    `annotation_parts` is the shipped traversal, imported rather than re-walked here: a
    second unwrapper would be a second opinion about what `tuple[SecretStr | None, ...]`
    contains, and the copy that stops matching is always the one nobody is looking at.
    """
    return any(
        isinstance(part, type) and issubclass(part, SECRET_TYPES)
        for part in annotation_parts(annotation)
    )


def secret_fields(model: type[BaseModel]) -> tuple[str, ...]:
    """The names of `model`'s own fields whose annotation mentions `SecretStr`."""
    return tuple(
        name for name, field in model.model_fields.items() if _mentions_secret(field.annotation)
    )


def _classes_in(namespace: Mapping[str, Any], module_name: str) -> Iterator[type]:
    """Every class defined in `module_name` reachable from `namespace`, nested ones included.

    A model nested inside another class is never in `vars(module)` and was therefore never
    examined (R-SEC-050). Recursing through each class's own namespace finds it, at any
    nesting depth, and the `seen` set makes a class that refers to itself terminate.
    """
    seen: set[int] = set()
    pending = [value for value in namespace.values() if isinstance(value, type)]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if current.__module__ != module_name:
            continue
        yield current
        pending.extend(value for value in vars(current).values() if isinstance(value, type))


def models_with_secrets() -> tuple[type[BaseModel], ...]:
    """Every Pydantic model in either source tree that declares a secret-wrapped field."""
    found: dict[str, type[BaseModel]] = {}
    for module in _modules():
        for value in _classes_in(vars(module), module.__name__):
            if issubclass(value, BaseModel) and secret_fields(value):
                found[f"{value.__module__}.{value.__qualname__}"] = value
    return tuple(found[key] for key in sorted(found))
