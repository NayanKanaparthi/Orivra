"""Per-response fencing of mail-derived text (AD D.2 `fence_nonce`, contract R-09).

The nonce is minted per response and mail text cannot close its own fence: fencing text
that already contains the nonce is refused rather than escaped, because escaping would
put the decision of what counts as a delimiter back inside untrusted content.

The full injection posture (trust labelling everywhere, connector-voiced fields, identity
splitting) is WS-14. What lives here is only what AD D.2 makes part of the envelope schema.
"""

from __future__ import annotations

import re
import secrets

_PREFIX = "mw-"
#: `secrets.token_hex(8)` is sixteen lowercase hex digits. Named, because `fenced_text` reads
#: the nonce back out of a fence and must recognise exactly what `mint_nonce` makes.
_NONCE_BYTES = 8
_FENCED = re.compile(
    rf"<<<({re.escape(_PREFIX)}[0-9a-f]{{{2 * _NONCE_BYTES}}}) (.*) \1>>>", flags=re.DOTALL
)


class FenceViolation(ValueError):
    """Mail-derived text contained the response nonce."""


def mint_nonce() -> str:
    """A per-response, unguessable fence nonce."""
    return _PREFIX + secrets.token_hex(_NONCE_BYTES)


def open_marker(nonce: str) -> str:
    return f"<<<{nonce} "


def close_marker(nonce: str) -> str:
    return f" {nonce}>>>"


def fence(nonce: str, text: str) -> str:
    """Wrap `text` in this response's fence."""
    if nonce in text:
        raise FenceViolation(
            "mail-derived text contains the response fence nonce; it cannot be fenced "
            "without letting the content close its own fence"
        )
    return f"{open_marker(nonce)}{text}{close_marker(nonce)}"


def is_fenced(nonce: str, text: str) -> bool:
    return (
        text.startswith(open_marker(nonce))
        and text.endswith(close_marker(nonce))
        and nonce not in unfence(nonce, text)
    )


def fenced_text(text: str) -> str | None:
    """The text inside a well-formed fence, or `None` when `text` is not exactly one.

    For a model that holds a fenced `Content` and has to measure **what it fences** without
    knowing which response minted the nonce - `SenderAuthentication`, whose bound is on the
    header as the receiving server wrote it. The markers are this module's, so the fence's
    own characters are never counted as the record's (2026-09-23: they were, and a header of
    467 to 512 characters passed the producer's bound and failed the model's by exactly the
    46 the fence adds). Text whose nonce also appears inside it is not a fence `fence` could
    have made, and is refused here as `fence` refuses it.
    """
    match = _FENCED.fullmatch(text)
    if match is None or match.group(1) in match.group(2):
        return None
    return match.group(2)


def unfence(nonce: str, text: str) -> str:
    """Inverse of `fence`, for tests and for size measurement."""
    return text.removeprefix(open_marker(nonce)).removesuffix(close_marker(nonce))
