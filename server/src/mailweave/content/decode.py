"""Base64url body decode and the charset resolution ladder (AD D.4a 2-3)."""

from __future__ import annotations

import base64
import binascii
import codecs
from dataclasses import dataclass

from mailweave.constants import CHARSET_LADDER

REPLACEMENT_CHAR = "�"


class UndecodableBody(Exception):
    """base64url decode failed. The message is still disclosed, with the failure declared."""

    def __init__(self, byte_length: int) -> None:
        super().__init__(f"undecodable base64url body ({byte_length} chars of input)")
        self.byte_length = byte_length


def decode_base64url(data: str) -> bytes:
    """Decode Gmail's unpadded base64url, restoring padding first.

    Gmail returns `-`/`_` alphabet with padding stripped; `base64.urlsafe_b64decode`
    rejects unpadded input, so padding restoration is not optional.
    """
    compact = "".join(data.split())
    padding = (-len(compact)) % 4
    try:
        return base64.urlsafe_b64decode(compact + "=" * padding)
    except (binascii.Error, ValueError) as exc:
        raise UndecodableBody(len(data)) from exc


@dataclass(frozen=True)
class DecodedText:
    """Result of the charset ladder, with everything a reduction record needs."""

    text: str
    charset_used: str
    charset_declared: str | None
    charset_known: bool
    replacements: int
    fell_back: bool


def _normalise_charset(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = name.strip().strip("\"'").lower()
    return cleaned or None


def charset_is_known(name: str | None) -> bool:
    normalised = _normalise_charset(name)
    if normalised is None:
        return False
    try:
        codecs.lookup(normalised)
    except LookupError:
        return False
    return True


def decode_text(
    raw: bytes,
    declared_charset: str | None,
    ladder: tuple[str, ...] = CHARSET_LADDER,
) -> DecodedText:
    """Resolve bytes to text: declared -> `ladder` (default UTF-8, cp1252, latin-1).

    Each candidate is attempted strictly, in order; the first that succeeds is the
    charset *used*, and it is named in the result so the caller can declare it. If no
    candidate decodes strictly, the first known candidate is re-run with
    ``errors="replace"`` and the substitutions are counted, so a lossy decode is a
    declared number rather than a silent mangling.

    `ladder` is a parameter, not a hardcoded chain, so the replacement path can be
    exercised by a test with a ladder that can actually fail.
    """
    declared = _normalise_charset(declared_charset)
    known = declared is not None and charset_is_known(declared)

    candidates: list[str] = []
    if known and declared is not None:
        candidates.append(declared)
    for name in ladder:
        if name not in candidates and charset_is_known(name):
            candidates.append(name)

    for candidate in candidates:
        try:
            text = raw.decode(candidate, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
        return DecodedText(
            text=text,
            charset_used=candidate,
            charset_declared=declared,
            charset_known=known,
            replacements=0,
            fell_back=known and candidate != declared,
        )

    fallback = candidates[0] if candidates else "utf-8"
    text = raw.decode(fallback, errors="replace")
    return DecodedText(
        text=text,
        charset_used=fallback,
        charset_declared=declared,
        charset_known=known,
        replacements=text.count(REPLACEMENT_CHAR),
        fell_back=known and fallback != declared,
    )
