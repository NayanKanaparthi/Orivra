"""Pydantic models for the Gmail `message.payload` tree.

Gmail parses MIME server-side, so the residual risk is decoding and part selection, not
MIME parsing (AD D.4a preamble, B.8 R4). These models are the validation boundary at the
payload level: everything downstream of here works on typed parts, never on raw dicts.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from mailweave.constants import PAYLOAD_DEPTH_CAP, PAYLOAD_PART_CAP
from mailweave.errors import ContentProcessingError
from mailweave.validation import failure_summary


class Header(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    value: str


class Body(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    size: int = 0
    data: str | None = None  # base64url, unpadded (RFC 4648 s5)
    attachment_id: str | None = Field(default=None, alias="attachmentId")


class Part(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    part_id: str = Field(default="", alias="partId")
    mime_type: str = Field(default="text/plain", alias="mimeType")
    filename: str = ""
    headers: tuple[Header, ...] = ()
    body: Body = Body()
    parts: tuple[Part, ...] = ()

    def header(self, name: str) -> str | None:
        """First value of `name`, case-insensitively. Duplicates are handled in `headers.py`."""
        lowered = name.lower()
        for h in self.headers:
            if h.name.lower() == lowered:
                return h.value
        return None

    @property
    def is_multipart(self) -> bool:
        return self.mime_type.lower().startswith("multipart/") or bool(self.parts)


def _child_parts(node: object) -> Iterable[object]:
    """The `parts` of one payload node, however that node is spelled.

    Round 5 read `node["parts"]` and only when `node` was a literal `dict`, so the bound
    measured `(1, 1)` for every tree built any other way. Two ways were demonstrated, and
    they are the same defect: R-SEC-021 wrapped the payload in `types.MappingProxyType`,
    which pydantic accepts and `isinstance(..., dict)` does not; R-ARCH-016 built the tree
    out of `Part` models bottom-up, which pydantic also accepts and which has no
    subscriptable node at any level. A bound that reads one concrete spelling of the
    structure is absent for every other spelling of the same structure.

    So the children are read the way the *model* reads them - a mapping key or an
    attribute, holding any sequence - which is the set of shapes that actually reach
    `MessagePayload`. A node this cannot read contributes no children and is counted once,
    which is the same conservative direction the original had.
    """
    parts = node.get("parts") if isinstance(node, Mapping) else getattr(node, "parts", None)
    return parts if isinstance(parts, list | tuple) else ()


def _declared_payload(data: object) -> object:
    """The `payload` member of whatever `MessagePayload` is being asked to build.

    Same rule as `_child_parts`, at the root: a mapping key for JSON-shaped input, an
    attribute for a model or namespace handed to `model_validate` directly. The keyword
    form (`MessagePayload(id=..., payload=part)`) arrives here as a mapping whose value is
    already a `Part`, which is R-ARCH-016's entry point and why both halves are needed.
    """
    if isinstance(data, Mapping):
        return data.get("payload")
    return getattr(data, "payload", None)


def measure_raw_shape(payload: object) -> tuple[int, int]:
    """`(part_count, max_depth)` of a payload tree, building no models.

    Iterative rather than recursive, so measuring a hostile shape cannot itself be the
    thing that blows the stack. It reads only `parts`, so it costs one lookup per node and
    allocates nothing per node beyond the traversal stack.
    """
    total = 0
    deepest = 0
    stack: list[tuple[object, int]] = [(payload, 1)]
    while stack:
        node, depth = stack.pop()
        total += 1
        deepest = max(deepest, depth)
        for child in _child_parts(node):
            stack.append((child, depth + 1))
    return total, deepest


def refuse_unbounded_payload(payload: object) -> None:
    """Refuse a payload tree too large or too deep to be worth building (R-SEC-006).

    Called from a `mode="before"` validator, so it runs on every construction path:
    `parse_payload(...)`, a direct `MessagePayload.model_validate(...)` and the keyword
    constructor. A bound that only the convenience wrapper applied would be a bound the
    next caller walks around.

    That claim was false for two of the three until round 6 - not because a path skipped
    the validator, but because the *measurement* only recognised one spelling of the tree
    (see `_child_parts`). Both halves are now measured by shape rather than by type, and
    `tests/test_content_units.py` builds each spelling at the cap and one past it.

    **Not covered, stated rather than implied:** this bounds what reaches `MessagePayload`.
    A caller that builds a 2,000-deep `Part` tree and never hands it to `MessagePayload`
    has already done that work, and `Part.model_validate(<deep raw dict>)` builds without
    passing through here - `Part` is the leaf model, not the boundary, and putting the walk
    on it would re-measure the whole subtree at every level of an ordinary parse.

    `ContentProcessingError` is not a `ValueError`, so Pydantic propagates it rather than
    folding it into a `ValidationError`: the refusal keeps this module's error type all
    the way out to the caller.
    """
    parts, depth = measure_raw_shape(payload)
    if parts > PAYLOAD_PART_CAP:
        raise ContentProcessingError(
            f"refusing a message payload of {parts} parts: the parse bound is "
            f"{PAYLOAD_PART_CAP} parts, a hundred times the {PAYLOAD_PART_CAP // 100} the "
            "pipeline will ever consider. The tree is refused whole rather than truncated, "
            "because a truncated payload would be a silent reduction with nothing to "
            "declare it (R-SEC-006)"
        )
    if depth > PAYLOAD_DEPTH_CAP:
        raise ContentProcessingError(
            f"refusing a message payload nested {depth} levels deep: the parse bound is "
            f"{PAYLOAD_DEPTH_CAP}. Beyond it the interpreter's own recursion guard decides "
            "the outcome, and it reports a foreign exception shape rather than this "
            "module's (R-SEC-007)"
        )


class MessagePayload(BaseModel):
    """The subset of `users.messages.get(format=full)` content processing consumes."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    id: str
    thread_id: str = Field(default="", alias="threadId")
    internal_date: str | None = Field(default=None, alias="internalDate")
    snippet: str = ""
    payload: Part

    @model_validator(mode="before")
    @classmethod
    def _shape_is_bounded_before_it_is_built(cls, data: Any) -> Any:
        """R-SEC-006: the caps applied before the walk that builds the tree.

        No type gate. Round 5 wrote `isinstance(data, dict)`, and pydantic-core has no such
        restriction: a `types.MappingProxyType` - stdlib, one line, not a contrived class -
        validated fine and skipped the bound entirely (R-SEC-021, 32,000 parts in 0.15s).
        Whatever pydantic will accept, `_declared_payload` reads.
        """
        refuse_unbounded_payload(_declared_payload(data))
        return data


def parse_payload(raw: object) -> MessagePayload:
    """The supported way to turn a Gmail `messages.get` body into a `MessagePayload`.

    Adds one thing to `model_validate`: R-SEC-007's other half. A malformed payload -
    wrong types, a missing `id`, anything Pydantic refuses - reached a caller as
    `pydantic.ValidationError`, a third-party exception shape that nothing in this
    codebase is built to catch. Here it arrives as `ContentProcessingError`, with
    Pydantic's own report preserved as the cause.

    The report is rendered by `validation.failure_summary`, the same one the Gmail client
    uses, rather than by reading the first error's `msg`. A `msg` belongs to whichever
    validator refused and a validator is free to quote what it refused - which is exactly
    how a refresh token reached an error message through `parse_instant` (R-SEC-043). This
    payload is mail-derived rather than secret-bearing, so the reason differs and the rule
    does not (AD A.11).
    """
    try:
        return MessagePayload.model_validate(raw)
    except ValidationError as failure:
        raise ContentProcessingError(
            f"a Gmail message payload could not be parsed: {failure.error_count()} "
            f"validation error(s) at {failure_summary(MessagePayload, failure)}"
        ) from failure
