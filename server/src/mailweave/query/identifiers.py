"""AD A.8a branch E-c's lexicon: "a closed, published, testable list".

E-c fires on "a token matching the **published structured-identifier lexicon** - an RFC-822
message id, an invoice/order/ticket/PO/SKU-shaped token (>=6 chars, >=2 digits, no
dictionary hit), a tracking number, or an IBAN-shaped token". Those four are the whole of
it, they are `IdentifierKind`'s four members, and `test_the_identifier_lexicon_has_exactly
_the_four_published_kinds` holds the enum to the sentence.

**Two things this list deliberately is not.** It is not a *rarity* test: A.8a withdraws
"unique token" as a qualifying signal and forbids consulting corpus frequency, so nothing
here counts anything. And `no dictionary hit` is implemented as a **published word list**,
not as a dictionary - `PUBLISHED_NON_IDENTIFIER_WORDS` below is the whole of it, it is
short, and a word absent from it that also carries two digits will be read as an
identifier. That is the honest scope of the check, and it is bounded on the other side by
E-c's own `hit_count in [1,3]` requirement: a token this list reads too generously cannot
fire the branch unless it also happens to match at most three messages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from mailweave.constants import (
    STRUCTURED_IDENTIFIER_MIN_CHARS,
    STRUCTURED_IDENTIFIER_MIN_DIGITS,
)


class IdentifierKind(StrEnum):
    """The four shapes A.8a's sentence enumerates, and no fifth."""

    RFC822_MESSAGE_ID = "rfc822_message_id"
    REFERENCE_CODE = "reference_code"
    TRACKING_NUMBER = "tracking_number"
    IBAN = "iban"


_RFC822_RE: Final[re.Pattern[str]] = re.compile(r"\A<[^<>@\s]+@[^<>@\s]+>\Z")

#: An IBAN is two country letters, two check digits, then up to 30 alphanumerics (ISO 13616).
_IBAN_RE: Final[re.Pattern[str]] = re.compile(r"\A[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}\Z")

#: Carrier tracking shapes, published individually so a reader can see which carriers are
#: covered and which are not. Absent: DHL, Royal Mail domestic, and every national post
#: that does not use the UPU S10 form - those tokens fall through to `REFERENCE_CODE` if
#: they are long enough and carry digits, and are simply not identifiers if they are not.
_TRACKING_RES: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("ups", re.compile(r"\A1Z[0-9A-Z]{16}\Z")),
    ("fedex12", re.compile(r"\A[0-9]{12}\Z")),
    ("fedex15", re.compile(r"\A[0-9]{15}\Z")),
    ("usps", re.compile(r"\A[0-9]{20,22}\Z")),
    ("upu_s10", re.compile(r"\A[A-Z]{2}[0-9]{9}[A-Z]{2}\Z")),
)

#: The "no dictionary hit" half of E-c's reference-code shape, as a published closed list.
#: Every entry is a word that reaches six characters and can carry digits in ordinary mail
#: without being an identifier. Compared case-folded, with digits stripped.
PUBLISHED_NON_IDENTIFIER_WORDS: Final[frozenset[str]] = frozenset(
    {
        "budget",
        "calendar",
        "contract",
        "covid",
        "document",
        "friday",
        "invoice",
        "meeting",
        "monday",
        "number",
        "october",
        "president",
        "project",
        "quarter",
        "release",
        "report",
        "review",
        "saturday",
        "schedule",
        "september",
        "sprint",
        "sunday",
        "thursday",
        "tuesday",
        "update",
        "version",
        "wednesday",
        "windows",
    }
)

#: Punctuation stripped from both ends of a token before it is measured. Not from the
#: middle: a hyphen inside `PO-2026-0041` is part of the identifier, and removing it would
#: change the token E-c would execute.
_EDGE_PUNCTUATION: Final[str] = ".,;:!?()[]{}\"'"


@dataclass(frozen=True)
class StructuredIdentifier:
    """One token that matched the lexicon, with which shape matched it."""

    token: str
    kind: IdentifierKind


def _looks_like_a_word(token: str) -> bool:
    """Whether the token is a published word with digits attached rather than an id."""
    letters = "".join(char for char in token if char.isalpha()).casefold()
    return letters in PUBLISHED_NON_IDENTIFIER_WORDS


def classify_identifier(raw: str) -> StructuredIdentifier | None:
    """The lexicon, applied to one token. `None` when the token is not an identifier.

    Order is precedence, and it is fixed rather than incidental: the narrow shapes are
    tested before the broad reference-code shape, so `1Z999AA10123456784` is reported as a
    tracking number rather than as a reference code that happens to be long enough.
    """
    token = raw.strip(_EDGE_PUNCTUATION)
    if not token:
        return None
    if _RFC822_RE.match(token) is not None:
        return StructuredIdentifier(token=token, kind=IdentifierKind.RFC822_MESSAGE_ID)
    upper = token.upper()
    for _carrier, pattern in _TRACKING_RES:
        if pattern.match(upper) is not None:
            return StructuredIdentifier(token=token, kind=IdentifierKind.TRACKING_NUMBER)
    if _IBAN_RE.match(upper) is not None:
        return StructuredIdentifier(token=token, kind=IdentifierKind.IBAN)
    digits = sum(1 for char in token if char.isdigit())
    if (
        len(token) >= STRUCTURED_IDENTIFIER_MIN_CHARS
        and digits >= STRUCTURED_IDENTIFIER_MIN_DIGITS
        and not _looks_like_a_word(token)
    ):
        return StructuredIdentifier(token=token, kind=IdentifierKind.REFERENCE_CODE)
    return None
