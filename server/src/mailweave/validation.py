"""Validation failures that cannot quote what failed (RR SEC-04, AD A.11, R-SEC-043).

Two kinds of document reach a Pydantic model in this project and **neither may be echoed
back**. A Gmail response is mail-derived, so AD A.11 keeps it out of every error string. The
credential file and the config file are secret-bearing, so RR SEC-04 keeps *them* out of
every error string. Same rule, two reasons, and until R-SEC-043 it was implemented once, in
one layer, for one of the two.

**What Pydantic does by default, and why it is a leak.** `str(ValidationError)` renders
`input_value=...` for every failing field, truncated in the middle but with an intact prefix
and suffix. `TokenStore.load()` interpolated that report into `TokenStoreError`, so a
`credentials.json` whose `refresh_token` had been corrupted into a nested structure put a
substantial fragment of the real refresh token into an exception message (R-SEC-043). The
same rendering sits behind `load_config`, where the whole client secret fits inside the
truncation window and is echoed **in full**.

**Three separate channels carry a value out of a validation failure**, which is why fixing
the reported one would have left the class open:

  1. `input_value=...` - the value itself. `hide_input_in_errors`, below, closes the
     **default string rendering** of that error - `str(exc)` and therefore every traceback,
     log line and f-string that formats it - for every caller, not only for the ones we
     edited. It does **not** close `ValidationError.errors()` or `ValidationError.json()`,
     which default to `include_input=True` and carry the value in full with no argument
     passed; `.json()` is a rendering by any reading, since it returns a string. This
     paragraph said "for *every* renderer" for two rounds and that was false (R-SEC-056),
     and the A/B is executed in
     `tests/test_auth_consent.py::test_hide_input_in_errors_closes_the_string_rendering_and_not_the_other_two`.

     What keeps those two out of this tree is not the flag but the round-12 AST sweep, which
     forbids `.errors()` and `.json()` inside a `ValidationError` handler, plus
     `failure_summary` passing `include_input=False` explicitly where it does read errors.
     The one live route to a raw `ValidationError` is
     `Model.__pydantic_validator__.validate_python(<not a mapping>)`, which no code in either
     tree calls: every entry point this module overrides, and every mapping document through
     the raw validator, produces `SecretDocumentMalformed` with `__context__` and `__cause__`
     both `None`.
  2. `msg` - our own validators' text. `parse_instant` spelled its refusal
     `f"{field}={value!r} is not an RFC 3339 instant"`, so a refresh token written into
     `obtained_at` by a corrupt save came out **whole and untruncated**. Closed by the
     validators naming the field and never the value, and by `failure_summary` not reading
     `msg` at all.
  3. `loc` - the field *path*, which for an `extra_forbidden` error is a key the document
     chose. A secret that ends up as a JSON key is reported by name. Closed by
     `failure_summary`, which prints a path segment only when the model declares a field of
     that name and prints `<withheld>` otherwise.

`hide_input_in_errors` does not touch (2) or (3), and `failure_summary` alone does not touch
a `ValidationError` some other code renders. Both are needed, and neither is sufficient.

**And a fourth surface that is not a rendering at all (R-SEC-049).** The refusals below used
to be raised inside their `except` blocks with `from None`. That produces a clean traceback -
`__cause__` is `None` and the context is suppressed - and it leaves `__context__` holding the
`ValidationError`, whose `str()` prints the secret in full when the secret became a JSON key.
"Not printed by default" is not the property this module claims; "not reachable from the
refusal" is. Each refusal is therefore built inside the handler and raised **after** it, where
no exception is being handled and there is no context to attach.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import cache
from typing import Any, Self, get_args

from pydantic import BaseModel, ConfigDict, ValidationError

from mailweave.errors import SecretDocumentMalformed

#: How many failing paths a summary names. A report is a diagnostic, not an inventory.
MAX_REPORTED_PATHS = 5

#: What a path segment becomes when the model declares no field of that name - which means
#: the segment came out of the document rather than out of this source tree.
WITHHELD = "<withheld>"


def annotation_parts(annotation: Any) -> Iterator[Any]:
    """Every type mentioned in a field annotation, at any generic depth, itself included.

    One traversal, exported, because two callers already want it for different questions:
    `declared_names` asks which nested models a report can name, and the canary's model
    discovery asks whether a `SecretStr` is in there anywhere. Written twice they would
    disagree on the day someone adds an annotation shape only one of them unwraps - which is
    this project's most repeated defect, and one this round is specifically not adding to.
    """
    yield annotation
    for argument in get_args(annotation):
        yield from annotation_parts(argument)


def _nested_models(annotation: Any) -> list[type[BaseModel]]:
    """Every `BaseModel` reachable from one field annotation, at any generic depth."""
    return [
        part
        for part in annotation_parts(annotation)
        if isinstance(part, type) and issubclass(part, BaseModel)
    ]


@cache
def declared_names(model: type[BaseModel]) -> frozenset[str]:
    """Every field name and alias in `model`'s graph: the only names a summary may print.

    Collected from the model graph rather than matched against a pattern, because a
    pattern says "this *looks* like a field name" and a secret is free to look like one.
    A name in this set was written in this repository; a name outside it was written by
    whatever produced the document.
    """
    names: set[str] = set()
    seen: set[type[BaseModel]] = set()
    pending: list[type[BaseModel]] = [model]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        for name, field in current.model_fields.items():
            names.add(name)
            if field.alias:
                names.add(field.alias)
            pending.extend(_nested_models(field.annotation))
    return frozenset(names)


def _segment(part: Any, permitted: frozenset[str]) -> str:
    if isinstance(part, int):
        return str(part)
    return part if isinstance(part, str) and part in permitted else WITHHELD


def failure_summary(model: type[BaseModel], failure: ValidationError) -> str:
    """Field paths and error *types* from a validation failure. No values, ever.

    `loc` is a field path and `type` is a fixed Pydantic slug (`string_type`, `missing`,
    `extra_forbidden`, ...); neither can carry a subject, a body or a token - with the one
    exception that an unexpected key's *name* appears in `loc`, which is why every segment
    is checked against `declared_names` before it is printed. `msg` is deliberately not
    read: its text belongs to whichever validator refused, and a validator is free to quote
    what it refused.
    """
    permitted = declared_names(model)
    parts = []
    for error in failure.errors(include_input=False)[:MAX_REPORTED_PATHS]:
        location = ".".join(_segment(item, permitted) for item in error.get("loc", ()))
        parts.append(f"{location or '<root>'}:{error.get('type', 'unknown')}")
    return ", ".join(parts)


class SecretBearingModel(BaseModel):
    """A model whose input document holds a secret. Nothing about its input is renderable.

    Inheriting this is not a convention a new model may forget:
    `tests/test_standing_cycle_round12.py` walks both source trees and fails if a model
    declares a `SecretStr` field without it.

    `hide_input_in_errors` is set on the base rather than repeated per model, and Pydantic
    merges `model_config` down the MRO, so a subclass may set `frozen`/`extra` without
    unsetting it. It matters that the *model* carries this and not the caller: any code
    that renders a `ValidationError` from one of these - ours, a test's, a library's - gets
    a report with no `input_value` in it, whether or not it went through the entry points
    below.
    """

    model_config = ConfigDict(hide_input_in_errors=True)

    def __init__(self, **data: Any) -> None:
        """Keyword construction, refused the same way as document validation.

        Every entry point is covered rather than the one the finding came in through.
        `Model(**raw)` is an ordinary way to build a model out of a parsed file, and an
        `extra_forbidden` error names the *key* the document chose, so a credential file
        whose token had ended up as a key would be reported by name. Leaving this path to
        a convention - "documents go through `model_validate`" - is the pattern this round
        exists to stop: one entry point checked, its peers trusted.
        """
        refusal: str | None = None
        try:
            super().__init__(**data)
        except ValidationError as failure:
            refusal = _refusal(type(self), failure)
        if refusal is not None:
            raise SecretDocumentMalformed(refusal)

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> Self:
        """Validate a document, or raise `SecretDocumentMalformed` naming fields only.

        Overridden rather than wrapped in a helper the callers must remember: a helper
        beside a public entry point is a door beside an open door, which is exactly how
        `SeedSession._issue` came to guard nothing (R-SEC-039).

        **The refusal is raised outside the handler, and that is the point** (R-SEC-049).
        `raise ... from None` used to be enough by inspection: it sets `__cause__` to `None`
        and suppresses the chain, so no traceback carried Pydantic's report. But
        `__suppress_context__` only stops the *rendering*: `__context__` still pointed at the
        raw `ValidationError`, and for a secret that had become a JSON key,
        `str(exc.__context__)` printed the whole thing untruncated. Anything that walks the
        chain - a structured-logging integration, a debugger, a future test - would render it.

        Building the message inside the handler and raising after it leaves nothing to walk:
        by then no exception is being handled, so `__context__` is `None` rather than
        suppressed, and the `ValidationError` itself is unreferenced. This is the same
        distinction the module is about - a value that is merely *not printed* is still
        reachable, and reachable is what matters.
        """
        refusal: str | None = None
        try:
            return super().model_validate(obj, **kwargs)
        except ValidationError as failure:
            refusal = _refusal(cls, failure)
        raise SecretDocumentMalformed(refusal)

    @classmethod
    def model_validate_json(cls, json_data: str | bytes | bytearray, **kwargs: Any) -> Self:
        """The same, for the entry point that skips `json.loads`."""
        refusal: str | None = None
        try:
            return super().model_validate_json(json_data, **kwargs)
        except ValidationError as failure:
            refusal = _refusal(cls, failure)
        raise SecretDocumentMalformed(refusal)


def _refusal(model: type[SecretBearingModel], failure: ValidationError) -> str:
    return (
        f"{model.__name__} could not be validated: {failure.error_count()} error(s) at "
        f"{failure_summary(model, failure)}. Values are omitted from this message on "
        "purpose: this document carries a credential, and no part of one - not a fragment, "
        "not a truncation - appears in an error string (RR SEC-04, R-SEC-043)"
    )
