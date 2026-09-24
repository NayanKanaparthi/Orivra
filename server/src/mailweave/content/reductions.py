"""Declared reductions: the record every content removal must leave behind.

AD D.4a and contract R-04: every reduction is declared *in place* with a size count and
a path to the unabridged form. `ReductionKind` is closed, so a removal that has no kind
cannot be recorded, and a removal that is not recorded cannot happen without failing a
test that counts characters in against characters out.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import ConfigDict, Field, model_validator

from mailweave.errors import ContentProcessingError
from mailweave.sealed_model import SealedModel


class ReductionKind(StrEnum):
    """Closed vocabulary. Adding a member is a schema change."""

    # Part selection (D.4a 1)
    ALTERNATIVE_PART_UNUSED = "alternative_part_unused"
    PART_DEPTH_CAP = "part_depth_cap"
    PART_COUNT_CAP = "part_count_cap"
    # Decoding (D.4a 2-3)
    UNDECODABLE_BODY = "undecodable_body"
    CHARSET_REPLACEMENTS = "charset_replacements"
    UNKNOWN_CHARSET = "unknown_charset"
    # Headers (D.4a 4)
    UNDECODABLE_ENCODED_WORD = "undecodable_encoded_word"
    DUPLICATE_HEADERS = "duplicate_headers"
    # HTML (D.4a 5)
    HTML_TO_TEXT = "html_to_text"
    HIDDEN_CONTENT = "hidden_content"
    HTML_DEPTH_CAP = "html_depth_cap"
    HTML_SIZE_CAP = "html_size_cap"
    HTML_PARSE_LOST_TEXT = "html_parse_lost_text"
    # Quote / signature (D.4a 6)
    QUOTED = "quoted"
    SIGNATURE = "signature"
    # Normalisation and disclosure depth (D.4a 7, A.9a)
    WHITESPACE_NORMALISED = "whitespace_normalised"
    BODY_HEAD_TRUNCATED = "body_head_truncated"


class HiddenConstruct(StrEnum):
    """The hiding techniques INJ-04 requires to be removed and counted.

    Most are HTML constructs. Three - `ZERO_WIDTH`, `BIDI_OVERRIDE` and `INVISIBLE_FORMAT` -
    are character-level: text that renders differently from the sequence it is made of. All
    three apply to `text/plain` bodies as well as to HTML, and to Subject, From and
    attachment filenames (R-SEC-011).

    The three together are **exactly** Unicode's `Cf` (format) category, and the split
    between them is Unicode's `Bidi_Class`; neither is a list anybody typed. Round 9 found
    the old hand-list covered 16 of the 170 format characters that exist, so U+061C, soft
    hyphen and the U+E0000 tag block - an invisible ASCII payload channel - all passed
    unflagged (R-SEC-033). `strip_invisible_characters` derives all three sets from
    `unicodedata` now, which is what makes this vocabulary a statement about Unicode rather
    than about what somebody remembered:

      * `BIDI_OVERRIDE` - a format character carrying a directional bidi class. The
        "Trojan Source" family (U+202A-U+202E, U+2066-U+2069) and the directional marks
        (U+200E, U+200F, and U+061C, which the old list missed).
      * `ZERO_WIDTH` - a format character Unicode classes as boundary-neutral: invisible and
        taking no width. U+200B-U+200D, U+2060 and U+FEFF, and also U+00AD SOFT HYPHEN and
        the tag block.
      * `INVISIBLE_FORMAT` - the remainder, which is neither: the Arabic number signs and
        the interlinear annotation characters. Removed and counted like the other two, filed
        separately because calling them "zero width" would be describing them wrongly.
    """

    SCRIPT = "script"
    STYLE = "style"
    HEAD = "head"
    COMMENT = "comment"
    DISPLAY_NONE = "display_none"
    VISIBILITY_HIDDEN = "visibility_hidden"
    FONT_SIZE_ZERO = "font_size_zero"
    TINY_BOX = "tiny_box"
    ZERO_WIDTH = "zero_width"
    COLOUR_EQUALS_BACKGROUND = "colour_equals_background"
    BIDI_OVERRIDE = "bidi_override"
    INVISIBLE_FORMAT = "invisible_format"


class Reduction(SealedModel):
    """One declared removal.

    `removed_chars` is the count DISC-03 requires. It is 0 only for kinds that declare a
    *choice* rather than a removal (an unused alternative part is still reachable through
    the unabridged path), and those kinds are enumerated below rather than assumed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ReductionKind
    removed_chars: int = Field(ge=0)
    detail: str | None = None
    # kind-specific, all optional, all mechanical
    mime: str | None = None
    bytes: int | None = None
    parser: str | None = None
    stripper: str | None = None
    charset_used: str | None = None
    charset_declared: str | None = None
    count: int | None = Field(default=None, ge=0)
    constructs: tuple[HiddenConstruct, ...] = ()
    kept_tokens: int | None = Field(default=None, ge=0)
    header: str | None = None

    _ZERO_REMOVAL_KINDS = frozenset(
        {
            ReductionKind.ALTERNATIVE_PART_UNUSED,
            ReductionKind.UNDECODABLE_BODY,
            ReductionKind.CHARSET_REPLACEMENTS,
            ReductionKind.UNKNOWN_CHARSET,
            ReductionKind.DUPLICATE_HEADERS,
            ReductionKind.UNDECODABLE_ENCODED_WORD,
            ReductionKind.PART_DEPTH_CAP,
            ReductionKind.PART_COUNT_CAP,
            ReductionKind.BODY_HEAD_TRUNCATED,
            ReductionKind.HTML_TO_TEXT,
        }
    )

    @property
    def is_a_silent_reduction(self) -> bool:
        """Whether this record declares nothing: no removal, no count, and no exemption.

        **The rule lives here and nowhere else** (round 27, R-MCP-023). It was written twice -
        once here with `_ZERO_REMOVAL_KINDS`, once in `MessageRow` without it - and the two
        copies disagreed about exactly the kinds this one exempts. An ordinary
        `multipart/alternative` message (plain text plus HTML, which is most real mail) emits
        `alternative_part_unused` with `removed_chars=0` and no count; this layer accepted it
        and the row one layer up refused it, so `mailweave_search` and `mailweave_get_messages`
        answered `-32603 "this is a defect in this server"` on the commonest message format
        there is. Unknown declared charsets (`ISO-8859-8-I`, `unicode`, `UNKNOWN-8BIT`) and
        undecodable bodies emit exempt kinds the same way and failed the same way.

        A caller that wants the rule asks for it rather than restating it.
        """
        return (
            self.removed_chars == 0
            and self.kind not in self._ZERO_REMOVAL_KINDS
            and self.count in (None, 0)
        )

    @model_validator(mode="after")
    def _kind_specific_obligations(self) -> Reduction:
        if self.kind is ReductionKind.HIDDEN_CONTENT and not self.constructs:
            raise ValueError("hidden_content reduction must name the constructs it removed")
        if self.kind is ReductionKind.BODY_HEAD_TRUNCATED and self.kept_tokens is None:
            raise ValueError("body_head_truncated reduction must state kept_tokens")
        if self.kind is ReductionKind.CHARSET_REPLACEMENTS and self.charset_used is None:
            raise ValueError("charset_replacements reduction must name the charset used")
        if self.is_a_silent_reduction:
            raise ValueError(
                f"reduction {self.kind} declares no removal and no count; "
                "a reduction record with nothing in it is a silent reduction"
            )
        return self


def reconcile(stage: str, before: str, after: str, declared: int) -> int:
    """Check a stage's declared removal against the shrinkage it actually produced.

    This is `DispositionLedger.certify`'s shape applied to characters instead of IDs
    (R-ARCH-004): the number that goes into the `Reduction` is the *measured* delta, and a
    stage whose own declaration disagrees with it fails loudly instead of shipping a
    reduction record that understates what it removed. The measured delta is returned, so
    the caller declares what happened rather than what the stage said would happen.

    A stage may legitimately grow the text (NFKC expands ligatures), which is why the
    measured removal is floored at zero on both sides of the comparison.

    It lives here rather than in `pipeline.py` because the pipeline is no longer the only
    caller: headers and attachment filenames are stripped too (R-SEC-011), and a second
    copy of this check is a second copy that can drift.
    """
    actual = max(0, len(before) - len(after))
    if declared != actual:
        raise ContentProcessingError(
            f"{stage} declared {declared} removed characters but the text shrank by "
            f"{actual} ({len(before)} -> {len(after)}); a declared reduction whose "
            "magnitude does not match the shrinkage is a silent reduction (DISC-03)"
        )
    return actual
