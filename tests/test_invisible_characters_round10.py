"""INJ-04's hidden-character clause, re-established on its full scope (R-SEC-033).

INJ-04 has now been reverted twice, and both reverts were about the same thing: a `PASS`
resting on evidence narrower than the criterion. Round 4 reverted it because the ledger row
cited only the bidi/zero-width scope. Round 9 reverted it because the bidi/zero-width
evidence itself turned out to be narrow - `strip_invisible_characters` held **16 hand-listed
code points** where Unicode defines **170** in category `Cf`, so:

  * **U+061C ARABIC LETTER MARK** survived - a bidi control, the direct sibling of the
    eleven that *were* listed;
  * **U+00AD SOFT HYPHEN** survived - invisible in every renderer;
  * the whole **U+E0000-U+E007F tag block** survived, which encodes an invisible ASCII
    payload. The reviewer spelled "HIDDEN" in it and got `removed_chars=0`.

The fix is not a longer list. A list is a snapshot of what one person knew on one day, and
this repository has now been defeated by that shape three times: the `\\n`/`\\r` line-break
scan (R-SEC-029), the `isdigit()` guard against `int()` (R-SEC-035), and this. The set is
derived from `unicodedata` - Unicode's own general category for membership, Unicode's own
bidi class for which cause a removal is filed under - so a format character the standard
adds tomorrow is covered without a code change.

**That claim is what this module tests**, and it tests it the way it has to be tested: not
"these three characters are now handled", which is what a longer list would also satisfy,
but "the handled set is *exactly* what the runtime says the category is", over the whole
code point space, in both directions. A hand-list cannot pass
`test_the_stripped_set_is_exactly_unicodes_format_category`.

**Scope, so this is not a third narrow citation.** What is established here is the
hidden-*character* clause. It is not the whole of INJ-04, and the other clauses - the
maintained parser, hidden HTML constructs, the nesting bound, the zero-network condition -
are covered by `test_content_units.py`, `test_content_pipeline.py` and `conftest.py`'s socket
block, unchanged this round. This module deliberately does not claim them.

No personal mail content appears here. Every string is invented for this repository.
"""

from __future__ import annotations

import sys
import unicodedata

import pytest

from mailweave.content.html_text import (
    _KEPT_FORMAT_CHARACTERS,
    invisible_character_patterns,
    strip_invisible_characters,
)
from mailweave.content.pipeline import process_message
from mailweave.content.reductions import HiddenConstruct, ReductionKind
from tests.fixtures import mime_kit

#: The size of one probe string. The exhaustive walks below batch code points rather than
#: calling the stripper 1.1 million times: the assertion is the same and the suite stays fast.
CHUNK = 4096

#: Unicode's twelve `Bidi_Control` characters. Written out **as test data**, deliberately -
#: this is the set R-SEC-005 named plus the U+061C the round-9 review found missing, and the
#: test's job is to ask whether the derived implementation agrees with it. `unicodedata` does
#: not expose `Bidi_Control`, which is exactly why the implementation must not try to.
BIDI_CONTROLS = (
    "؜",  # ARABIC LETTER MARK - the one the hand-list missed
    "‎",  # LEFT-TO-RIGHT MARK
    "‏",  # RIGHT-TO-LEFT MARK
    "‪",  # LEFT-TO-RIGHT EMBEDDING
    "‫",  # RIGHT-TO-LEFT EMBEDDING
    "‬",  # POP DIRECTIONAL FORMATTING
    "‭",  # LEFT-TO-RIGHT OVERRIDE
    "‮",  # RIGHT-TO-LEFT OVERRIDE
    "⁦",  # LEFT-TO-RIGHT ISOLATE
    "⁧",  # RIGHT-TO-LEFT ISOLATE
    "⁨",  # FIRST STRONG ISOLATE
    "⁩",  # POP DIRECTIONAL ISOLATE
)

#: The reviewer's covert channel: "HIDDEN" spelled in the U+E0000 tag block, which renders as
#: nothing at all. Before this round it reached `body_clean` intact with `removed_chars=0`.
TAG_PAYLOAD = "".join(chr(0xE0000 + ord(letter)) for letter in "HIDDEN")


def format_characters() -> tuple[str, ...]:
    """Every `Cf` code point, computed here and not imported from the implementation.

    The test derives the expected set independently of the code under test. Importing the
    implementation's own set would make every assertion below a tautology.
    """
    return tuple(
        chr(code) for code in range(sys.maxunicode + 1) if unicodedata.category(chr(code)) == "Cf"
    )


def handled_characters() -> frozenset[str]:
    """The set the implementation actually strips, read back off its compiled patterns."""
    return frozenset(
        character
        for _, pattern in invisible_character_patterns()
        for character in format_characters()
        if pattern.fullmatch(character)
    )


# --- the property a longer hand-list could not satisfy --------------------------------------


def test_the_stripped_set_is_exactly_unicodes_format_category() -> None:
    """Set equality, both directions, over the whole code point space.

    This is the assertion R-SEC-033 asks for. "U+061C is handled now" would be satisfied by
    a seventeen-element list; "the handled set is what `unicodedata.category` says it is"
    cannot be. It also survives a CPython Unicode-data upgrade without editing: if the next
    version defines a 171st format character, both sides of this equality move together,
    which is the whole point of deriving rather than listing.
    """
    expected = frozenset(format_characters()) - _KEPT_FORMAT_CHARACTERS
    assert handled_characters() == expected
    assert not _KEPT_FORMAT_CHARACTERS, (
        "the keep-list is empty by decision; a character added to it needs its own "
        "measurement of what keeping it costs, and its own case here"
    )


def test_the_category_is_far_wider_than_the_list_it_replaced() -> None:
    """The size of the hole, measured rather than quoted from the review.

    Round 9 reported 16 handled of about 170. The 16 is history; the ratio is asserted
    against the runtime so the number in the handoff is a number a test produced.
    """
    assert len(format_characters()) == len(handled_characters())
    assert len(handled_characters()) > 16 * 5


@pytest.mark.parametrize("base", range(0, sys.maxunicode + 1, CHUNK), ids=lambda b: f"U+{b:05X}")
def test_no_character_outside_the_format_category_is_ever_removed(base: int) -> None:
    """The false-positive half, also exhaustive: the fix must not eat visible text.

    Widening a stripper is where content loss gets introduced, so the widening is bounded in
    the same breath it is made. Every non-`Cf` code point in the space goes through the
    stripper and none of them is counted as removed.
    """
    probe = "".join(
        chr(code)
        for code in range(base, min(base + CHUNK, sys.maxunicode + 1))
        if unicodedata.category(chr(code)) != "Cf"
    )
    assert strip_invisible_characters(probe).removed_chars == 0


def test_every_format_character_is_removed_and_counted_exactly_once() -> None:
    """The removal and the *count* are one statement, not two.

    DISC-03's rule is that a reduction declares its own magnitude. A stripper that removed
    170 characters and reported 16 would be a silent reduction of 154, which is a different
    defect from the one being fixed and just as real.
    """
    characters = format_characters()
    probe = "a" + "a".join(characters) + "a"
    result = strip_invisible_characters(probe)
    assert result.removed_chars == len(characters)
    assert result.text == "a" * (len(characters) + 1)
    assert result.zero_width_removed + result.bidi_removed + result.format_removed == (
        result.removed_chars
    )


# --- the three misses the reviewer named, each as its own reproduction ----------------------


def test_the_arabic_letter_mark_no_longer_survives() -> None:
    """U+061C: a bidi control, sibling of the eleven that were listed, and absent from them."""
    result = strip_invisible_characters("Pay؜now")
    assert result.text == "Paynow"
    assert result.removed_chars == 1
    assert HiddenConstruct.BIDI_OVERRIDE in result.constructs


def test_the_soft_hyphen_no_longer_survives() -> None:
    """U+00AD: invisible in every renderer, and not a bidi control, so neither list held it."""
    result = strip_invisible_characters("Pay­now")
    assert result.text == "Paynow"
    assert result.removed_chars == 1
    assert HiddenConstruct.ZERO_WIDTH in result.constructs


def test_the_tag_block_payload_no_longer_survives() -> None:
    """The reviewer's covert ASCII channel, spelled out and stripped.

    Worth its own case rather than folding into the exhaustive walk: this is not one stray
    code point, it is a documented technique for carrying a whole readable string past a
    reader's eyes, and 128 of the block's characters were reaching `body_clean`.
    """
    result = strip_invisible_characters(f"Please approve.{TAG_PAYLOAD}")
    assert result.text == "Please approve."
    assert result.removed_chars == len(TAG_PAYLOAD)
    assert HiddenConstruct.ZERO_WIDTH in result.constructs


def test_the_reviewers_combined_probe_returns_nothing_hidden() -> None:
    """All three misses in one string, which is how the review reported it."""
    result = strip_invisible_characters(f"Pay؜now­{TAG_PAYLOAD}")
    assert result.text == "Paynow"
    assert result.removed_chars == 2 + len(TAG_PAYLOAD)


# --- the old evidence must still hold: nothing that passed before may regress ---------------


@pytest.mark.parametrize("control", BIDI_CONTROLS, ids=lambda c: f"U+{ord(c):04X}")
def test_every_bidi_control_is_still_declared_as_a_bidi_override(control: str) -> None:
    """R-SEC-005's set, plus U+061C, still filed under the cause that names the technique.

    The derived split must not quietly relabel the Trojan Source characters: a consumer
    filtering on `bidi_override` would stop seeing them, which would be a regression dressed
    as a widening. `Bidi_Control` is written out in this file as *test data* because
    `unicodedata` does not expose it - and the implementation must not transcribe it, which
    is why the check lives here and the derivation lives there.
    """
    result = strip_invisible_characters(f"a{control}b")
    assert result.text == "ab"
    assert result.bidi_removed == 1
    assert result.constructs == (HiddenConstruct.BIDI_OVERRIDE,)


@pytest.mark.parametrize(
    "text",
    ["שלום", "مرحبا", "naïve café", "日本語のテキスト"],
    ids=["hebrew", "arabic", "latin-diacritics", "japanese"],
)
def test_ordinary_right_to_left_and_non_latin_text_is_untouched(text: str) -> None:
    """The defect a widened stripper would introduce, asserted against rather than hoped for."""
    result = strip_invisible_characters(text)
    assert result.text == text
    assert result.removed_chars == 0


# --- and the same thing through the pipeline, which is what INJ-04 is about -----------------


@pytest.mark.parametrize("mime_type", ["text/plain", "text/html"])
def test_a_tag_block_payload_does_not_reach_body_clean(mime_type: str) -> None:
    """The end-to-end statement: the payload is gone from the body and the loss is declared.

    Both body paths, because `text/plain` never passes through the HTML extractor - which is
    how R-SEC-005's original bidi finding reached `body_clean` in the first place.
    """
    raw = f"Please approve the invoice.{TAG_PAYLOAD}"
    body = raw if mime_type == "text/plain" else f"<p>{raw}</p>"
    processed = process_message(
        mime_kit.message(mime_kit.part(mime_type, charset="utf-8", data=body.encode()))
    )

    assert TAG_PAYLOAD not in processed.body_clean.text
    assert "Please approve the invoice." in processed.body_clean.text

    hidden = [r for r in processed.reductions if r.kind is ReductionKind.HIDDEN_CONTENT]
    assert hidden, "INJ-04 requires a hidden_content record with a count"
    declared = sum(r.removed_chars for r in hidden)
    assert declared >= len(TAG_PAYLOAD)


def test_an_arabic_letter_mark_in_a_subject_is_stripped_and_declared() -> None:
    """R-SEC-011's paths, re-run against the sibling character the hand-list missed.

    `headers.py` imports this exact function for Subject and From, and `mime.py` for
    attachment filenames, so the hole was not confined to the body. The declared reduction
    must also not quote the value back - a reduction that names what it removed is a second
    copy of the thing it removed.
    """
    spoof = "Invoice؜_final.pdf"
    processed = process_message(
        mime_kit.message(
            mime_kit.part("text/plain", charset="utf-8", data=b"body", headers=[("Subject", spoof)])
        )
    )
    assert processed.subject is not None
    assert "؜" not in processed.subject
    assert processed.headers["subject"].display == "Invoice_final.pdf"
    # D.4a's unabridged path: the raw value is retained untouched, and that is deliberate.
    assert processed.headers["subject"].values == (spoof,)
    declared = [
        r
        for r in processed.reductions
        if r.kind is ReductionKind.HIDDEN_CONTENT and HiddenConstruct.BIDI_OVERRIDE in r.constructs
    ]
    assert declared, "a stripped Subject must declare the removal"
    assert spoof not in (declared[0].detail or "")
