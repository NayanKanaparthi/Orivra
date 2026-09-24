"""RFC 2047 header decoding and duplicate-header accounting (AD D.4a 4).

Two rules the spec makes non-negotiable:
  * an undecodable encoded-word is kept **verbatim** and flagged, never dropped;
  * duplicate headers retain every value, the first is used for display, the count is
    declared.

And one that M3 left half-applied (R-SEC-011). The Trojan-Source spoof M3 exists to stop -
`"Invoice_" + RLO + "exe.cod" + PDF + "_final.pdf"`, which renders as `Invoice_dpf.exe`
reversed into something ending `.pdf` - was stripped from `body_clean` and reached
`ProcessedMessage.subject` byte-for-byte. A `Subject` is handed to the same agent, on the
same surface, with the same trust label as the body; a display-order spoof is not less of
one for arriving in a header. So the decoded *display* value of every header gets the same
strip and the same declared `hidden_content` reduction the body gets.

`DecodedHeader.values` keeps the raw wire text unstripped on purpose: it is the unabridged
form D.4a requires every reduction to leave a path to, and nothing discloses it. `display`
is the value that travels.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.header import decode_header

from mailweave.content.html_text import strip_invisible_characters
from mailweave.content.reductions import Reduction, ReductionKind, reconcile


@dataclass(frozen=True)
class DecodedHeader:
    name: str
    display: str  # the first value, RFC 2047 decoded
    values: tuple[str, ...]  # every raw value, in wire order
    undecodable_words: int


def decode_encoded_words(value: str) -> tuple[str, int]:
    """Decode RFC 2047 encoded-words. Returns (text, undecodable_word_count).

    A word whose charset is unknown or whose payload will not decode is re-emitted
    exactly as it arrived, so the caller can still see what the sender sent.
    """
    try:
        chunks = decode_header(value)
    except (ValueError, UnicodeDecodeError):
        return value, 1

    out: list[str] = []
    undecodable = 0
    for payload, charset in chunks:
        if isinstance(payload, str):
            out.append(payload)
            continue
        if charset is None:
            try:
                out.append(payload.decode("ascii", errors="strict"))
            except UnicodeDecodeError:
                out.append(payload.decode("utf-8", errors="replace"))
                undecodable += 1
            continue
        try:
            out.append(payload.decode(charset, errors="strict"))
        except (UnicodeDecodeError, LookupError):
            # Keep the raw encoded-word verbatim rather than guessing.
            out.append(payload.decode("latin-1", errors="replace"))
            undecodable += 1
    return "".join(out), undecodable


def _join(parts: list[str]) -> str:
    """Join decoded chunks the way `make_header` would, without its lossy str() path."""
    return "".join(parts)


def collect_headers(
    raw: list[tuple[str, str]],
) -> tuple[dict[str, DecodedHeader], list[Reduction]]:
    """Group raw (name, value) pairs case-insensitively and decode them.

    Returns the header table keyed by lowercase name, plus the reductions that declare
    duplicates and undecodable encoded-words.
    """
    grouped: dict[str, list[str]] = {}
    order: list[str] = []
    for name, value in raw:
        key = name.lower()
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(value)

    table: dict[str, DecodedHeader] = {}
    reductions: list[Reduction] = []
    for key in order:
        values = tuple(grouped[key])
        decoded, undecodable = decode_encoded_words(values[0])
        cleaned = strip_invisible_characters(decoded)
        if cleaned.removed_chars:
            reductions.append(
                Reduction(
                    kind=ReductionKind.HIDDEN_CONTENT,
                    removed_chars=reconcile(
                        f"header {key} invisible-character strip",
                        decoded,
                        cleaned.text,
                        cleaned.removed_chars,
                    ),
                    count=cleaned.removed_chars,
                    constructs=cleaned.constructs,
                    header=key,
                    detail=(
                        "invisible format characters (Unicode general category Cf) removed "
                        "from the header value; the raw value is retained"
                    ),
                )
            )
        display = cleaned.text
        table[key] = DecodedHeader(
            name=key,
            display=display,
            values=values,
            undecodable_words=undecodable,
        )
        if len(values) > 1:
            reductions.append(
                Reduction(
                    kind=ReductionKind.DUPLICATE_HEADERS,
                    removed_chars=0,
                    header=key,
                    count=len(values),
                    detail=f"{len(values)} values retained; first used for display",
                )
            )
        if undecodable:
            reductions.append(
                Reduction(
                    kind=ReductionKind.UNDECODABLE_ENCODED_WORD,
                    removed_chars=0,
                    header=key,
                    count=undecodable,
                    detail="encoded-word kept verbatim",
                )
            )
    return table, reductions


def content_type_charset(content_type: str | None) -> str | None:
    """Extract `charset=` from a Content-Type header value, or None."""
    if not content_type:
        return None
    for param in content_type.split(";")[1:]:
        key, _, value = param.partition("=")
        if key.strip().lower() == "charset":
            return value.strip().strip("\"'") or None
    return None
