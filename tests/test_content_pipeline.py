"""End-to-end content processing against deliberately hostile inputs (WS-07).

The pipeline runs here with sockets disabled by the suite's default fixture, which is how
INJ-04's zero-network condition is demonstrated rather than asserted: one test attempts a
connection in the same process to show the block is live, and the rest exercise the
parsers under it.
"""

from __future__ import annotations

import socket

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mailweave.content import (
    HtmlParserName,
    ProcessedMessage,
    Reduction,
    ReductionKind,
    decode_text,
    process_message,
)
from mailweave.content.payload import MessagePayload
from mailweave.content.reductions import HiddenConstruct
from tests.conftest import NetworkAccessDenied
from tests.fixtures import mime_kit


def reductions_of(processed: ProcessedMessage, kind: ReductionKind) -> list[Reduction]:
    return [r for r in processed.reductions if r.kind is kind]


# --- the zero-network condition -------------------------------------------------------------


def test_the_pipeline_runs_with_networking_denied() -> None:
    """If the block were not live this test would pass vacuously, so it proves the block first."""
    with pytest.raises(NetworkAccessDenied):
        socket.create_connection(("example.invalid", 80))

    for parser in HtmlParserName:
        processed = process_message(mime_kit.html_only_message(), html_parser=parser)
        assert "1,240.50 EUR" in processed.default_view

    processed = process_message(mime_kit.nested_multipart_message())
    assert processed.default_view


# --- nested multipart, mixed charsets, encoded-word subject ------------------------------------


def test_a_three_level_multipart_message_is_processed_without_loss() -> None:
    processed = process_message(mime_kit.nested_multipart_message())

    assert processed.subject == "Résumé of the café meeting"
    assert processed.body_source_mime == "text/plain"
    assert processed.charset_used == "iso-8859-1"
    assert "Yes, ship it on the 14th." in processed.default_view
    # The quoted chain and the signature are outside the default view...
    assert "Can we confirm the date?" not in processed.default_view
    assert "Operations, Northwind" not in processed.default_view
    # ...and still in `body_clean`, because amendment A7 deletes nothing.
    assert "Can we confirm the date?" in processed.body_clean.text
    assert "Operations, Northwind" in processed.body_clean.text
    # ...and each classification is declared with a count and the detector that made it,
    # declaring a removal of **zero** because none happened.
    quoted = reductions_of(processed, ReductionKind.QUOTED)
    assert quoted and quoted[0].removed_chars == 0 and quoted[0].count and quoted[0].stripper
    signature = reductions_of(processed, ReductionKind.SIGNATURE)
    assert signature and signature[0].removed_chars == 0 and signature[0].count
    # The HTML alternative was not used, and says so rather than vanishing.
    unused = reductions_of(processed, ReductionKind.ALTERNATIVE_PART_UNUSED)
    assert [r.mime for r in unused] == ["text/html"]
    # The attachment is metadata only.
    assert [(a.filename, a.attachment_id) for a in processed.attachments] == [
        ("proposal.pdf", "att-1")
    ]


def test_a_non_utf8_body_declares_the_charset_it_actually_used() -> None:
    raw = "Übergabe am Dienstag".encode("iso-8859-1")
    payload = mime_kit.part("text/plain", charset="utf-8", data=raw)  # declared wrongly
    processed = process_message(mime_kit.message(payload))

    assert processed.default_view == raw.decode("cp1252")
    declared = reductions_of(processed, ReductionKind.CHARSET_REPLACEMENTS)
    assert declared and declared[0].charset_declared == "utf-8"
    assert declared[0].charset_used == processed.charset_used != "utf-8"


def test_an_unknown_charset_is_declared_rather_than_assumed() -> None:
    payload = mime_kit.part("text/plain", charset="x-made-up-1", data=b"ascii body")
    processed = process_message(mime_kit.message(payload))
    assert reductions_of(processed, ReductionKind.UNKNOWN_CHARSET)
    assert processed.default_view == "ascii body"


# --- HTML-only, hostile ------------------------------------------------------------------------


@pytest.mark.parametrize("parser", list(HtmlParserName))
def test_an_html_only_body_keeps_its_evidence_and_declares_what_it_hid(
    parser: HtmlParserName,
) -> None:
    processed = process_message(mime_kit.html_only_message(), html_parser=parser)

    assert "1,240.50 EUR" in processed.default_view
    assert "Ignore previous instructions" not in processed.body_clean.text
    assert "attacker@evil.invalid" not in processed.body_clean.text

    hidden = reductions_of(processed, ReductionKind.HIDDEN_CONTENT)
    assert hidden, "INJ-04 requires a hidden_content record with a count"
    assert hidden[0].removed_chars > 0
    assert HiddenConstruct.DISPLAY_NONE in hidden[0].constructs
    conversions = reductions_of(processed, ReductionKind.HTML_TO_TEXT)
    assert conversions and conversions[0].parser


# --- undecodable and degenerate payloads ---------------------------------------------------------


def test_an_undecodable_body_is_declared_and_the_message_is_still_disclosed() -> None:
    payload = mime_kit.part("text/plain", charset="utf-8", encoded="!!!! not base64 !!!!", size=19)
    processed = process_message(mime_kit.message(payload))

    assert processed.undecodable is True
    assert processed.body_clean.text == "" and processed.default_view == ""
    declared = reductions_of(processed, ReductionKind.UNDECODABLE_BODY)
    assert declared and declared[0].bytes
    # GMAIL-02: declared, never dropped - the message still has an identity to disclose.
    assert processed.message_id == "m1"


def test_a_message_with_no_text_part_yields_an_empty_body_and_its_attachments() -> None:
    payload = mime_kit.part(
        "multipart/mixed",
        parts=[
            mime_kit.part(
                "image/png", part_id="0", filename="chart.png", attachment_id="att-9", size=9001
            )
        ],
    )
    processed = process_message(mime_kit.message(payload))
    assert processed.body_clean.text == "" and processed.default_view == ""
    assert [a.filename for a in processed.attachments] == ["chart.png"]


def test_missing_headers_are_absent_rather_than_invented() -> None:
    payload = mime_kit.part("text/plain", charset="utf-8", data=b"body only")
    processed = process_message(mime_kit.message(payload))
    assert processed.subject is None
    assert processed.header_display("message-id") is None


def test_duplicate_headers_are_declared_and_the_first_is_used() -> None:
    payload = mime_kit.part(
        "text/plain",
        charset="utf-8",
        data=b"body",
        headers=[("Subject", "First subject"), ("Subject", "Second subject")],
    )
    processed = process_message(mime_kit.message(payload))
    assert processed.subject == "First subject"
    duplicates = reductions_of(processed, ReductionKind.DUPLICATE_HEADERS)
    assert duplicates and duplicates[0].count == 2


def test_head_truncation_is_declared_when_the_ladder_asks_for_it() -> None:
    body = " ".join(f"word{i}" for i in range(400)).encode()
    payload = mime_kit.part("text/plain", charset="utf-8", data=body)
    processed = process_message(mime_kit.message(payload), head_truncate_tokens=50)
    declared = reductions_of(processed, ReductionKind.BODY_HEAD_TRUNCATED)
    assert declared and declared[0].kept_tokens == 50
    assert processed.body_tokens == 50
    assert declared[0].removed_chars > 0


# --- the no-silent-reduction invariant ------------------------------------------------------------


ALL_FIXTURES = {
    "nested_multipart": mime_kit.nested_multipart_message,
    "html_only": mime_kit.html_only_message,
}


@pytest.mark.parametrize("name", sorted(ALL_FIXTURES))
def test_no_fixture_loses_characters_without_declaring_a_reduction(name: str) -> None:
    processed = process_message(ALL_FIXTURES[name]())
    source_length = _source_length(ALL_FIXTURES[name]())
    if len(processed.body_clean.text) < source_length:
        declared = sum(r.removed_chars for r in processed.reductions)
        assert declared > 0, "content shrank with no declared reduction (DISC-03)"


def _source_length(message: MessagePayload) -> int:
    from mailweave.content.decode import decode_base64url
    from mailweave.content.headers import content_type_charset
    from mailweave.content.mime import select_body, walk

    selection = select_body(walk(message.payload))
    if selection.chosen is None:
        return 0
    raw = decode_base64url(selection.chosen.part.body.data or "")
    charset = content_type_charset(selection.chosen.part.header("Content-Type"))
    return len(decode_text(raw, charset).text)


@settings(max_examples=75, deadline=None)
@given(
    body=st.text(max_size=400),
    charset=st.sampled_from(["utf-8", "iso-8859-1", "cp1252", None, "x-unknown"]),
    as_html=st.booleans(),
)
def test_arbitrary_bodies_never_crash_the_pipeline_and_never_shrink_silently(
    body: str, charset: str | None, as_html: bool
) -> None:
    try:
        encoded = body.encode(charset if charset in {"iso-8859-1", "cp1252"} else "utf-8")
    except UnicodeEncodeError:
        encoded = body.encode()
    payload = mime_kit.part("text/html" if as_html else "text/plain", charset=charset, data=encoded)
    processed = process_message(mime_kit.message(payload))

    decoded_length = len(decode_text(encoded, charset).text)
    if len(processed.body_clean.text) < decoded_length:
        assert any(r.removed_chars > 0 or (r.count or 0) > 0 for r in processed.reductions), (
            "content shrank with no declared reduction"
        )


# --- M1 / R-ARCH-004: a declared reduction must match the shrinkage it caused -----------------


def test_an_annotation_stage_that_loses_text_fails_the_pipeline() -> None:
    """R-ARCH-004's monkeypatch, in its A7 form: the stage that must never shrink, shrinking.

    Round 1 asserted a reduction was *present*, never that its magnitude matched, and
    R-ARCH-004 showed a stripper could remove 220 characters and declare 1. The pipeline
    reconciles each stage against the shrinkage it produced.

    Under amendment A7 the quote/signature stage declares **zero**, so the same
    reconciliation becomes the containment check in the production path: an annotation that
    returns less text than it was given fails the pipeline instead of shipping a body that
    quietly lost a sentence. This patches exactly that, and the honest run is unaffected.
    """
    from mailweave.content import pipeline as pipeline_module
    from mailweave.content.annotate import AnnotatedBody, AnnotatedSpan, SpanClass
    from mailweave.content.quotes import annotate_body
    from mailweave.errors import ContentProcessingError

    honest = process_message(mime_kit.nested_multipart_message())
    honest_classified = sum(
        r.count or 0
        for r in honest.reductions
        if r.kind in (ReductionKind.QUOTED, ReductionKind.SIGNATURE)
    )

    def losing(text: str) -> AnnotatedBody:
        """An annotation of the default view rather than of the whole body."""
        kept = annotate_body(text).view()
        return AnnotatedBody(
            text=kept,
            spans=(
                AnnotatedSpan(
                    start=0,
                    end=len(kept),
                    classification=SpanClass.ORIGINAL,
                    signal="no_structural_signal",
                ),
            ),
        )

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(pipeline_module, "annotate_body", losing)
        with pytest.raises(ContentProcessingError) as failure:
            process_message(mime_kit.nested_multipart_message())

    message = str(failure.value)
    assert "span annotation" in message
    assert "every input character being present in the annotated output" in message
    # The honest run is unaffected, and its declaration is not a token non-zero number: it
    # classifies over a hundred characters out of the default view and removes none of them,
    # which is the round-8-to-round-9 change stated as an assertion rather than a claim.
    assert honest_classified > 100
    assert all(
        r.removed_chars == 0
        for r in honest.reductions
        if r.kind in (ReductionKind.QUOTED, ReductionKind.SIGNATURE)
    )


def test_the_declared_total_tracks_the_actual_shrinkage_across_the_whole_pipeline() -> None:
    """Magnitude, not presence: the numbers on the wire are the measured deltas."""
    processed = process_message(mime_kit.nested_multipart_message())
    source_length = _source_length(mime_kit.nested_multipart_message())
    shrinkage = source_length - len(processed.body_clean.text)
    declared = sum(r.removed_chars for r in processed.reductions)
    assert shrinkage > 0
    assert declared == shrinkage


@settings(max_examples=75, deadline=None)
@given(body=st.text(max_size=300), as_html=st.booleans())
def test_declared_removals_never_understate_the_shrinkage(body: str, as_html: bool) -> None:
    """The property R-ARCH-004 said the two round-1 tests only pretended to check.

    HTML is allowed to over-declare (hidden text is counted both as markup removal and as
    hidden content), so the bound is one-sided for that path; nothing may under-declare.
    """
    encoded = body.encode()
    payload = mime_kit.part("text/html" if as_html else "text/plain", charset="utf-8", data=encoded)
    processed = process_message(mime_kit.message(payload))
    shrinkage = len(decode_text(encoded, "utf-8").text) - len(processed.body_clean.text)
    declared = sum(r.removed_chars for r in processed.reductions)
    if shrinkage > 0:
        assert declared >= shrinkage, f"declared {declared} for a shrinkage of {shrinkage}"


# --- M3 / R-SEC-005: unicode bidi overrides are removed and declared --------------------------


BIDI_SPOOF = "Invoice_‮exe.cod‬_final.pdf"


@pytest.mark.parametrize("mime_type", ["text/plain", "text/html"])
def test_a_bidi_override_does_not_reach_body_clean(mime_type: str) -> None:
    """`normalise(rlo).text == rlo` was True in round 1: the spoof passed through untouched."""
    raw = BIDI_SPOOF if mime_type == "text/plain" else f"<p>{BIDI_SPOOF}</p>"
    processed = process_message(
        mime_kit.message(mime_kit.part(mime_type, charset="utf-8", data=raw.encode()))
    )
    assert "‮" not in processed.body_clean.text
    assert "‬" not in processed.body_clean.text
    assert "Invoice_" in processed.body_clean.text and "_final.pdf" in processed.body_clean.text

    hidden = reductions_of(processed, ReductionKind.HIDDEN_CONTENT)
    constructs = {c for r in hidden for c in r.constructs}
    assert HiddenConstruct.BIDI_OVERRIDE in constructs
    declared = sum(r.removed_chars for r in hidden if HiddenConstruct.BIDI_OVERRIDE in r.constructs)
    assert declared >= 2


def test_every_bidi_control_the_finding_names_is_covered() -> None:
    """U+202A-E, U+2066-2069, U+200E/F - the Trojan Source set, not just the two demoed."""
    from mailweave.content.html_text import strip_invisible_characters

    controls = "‪‫‬‭‮⁦⁧⁨⁩‎‏"
    stripped = strip_invisible_characters(f"a{controls}b")
    assert stripped.text == "ab"
    assert stripped.bidi_removed == len(controls)
    assert HiddenConstruct.BIDI_OVERRIDE in stripped.constructs


def test_ordinary_right_to_left_text_is_not_stripped() -> None:
    """Only the *controls* go. Removing Arabic or Hebrew letters would be the real defect."""
    from mailweave.content.html_text import strip_invisible_characters

    hebrew = "שלום"
    stripped = strip_invisible_characters(hebrew)
    assert stripped.text == hebrew
    assert stripped.bidi_removed == 0


# --- R-SEC-011: the same spoof on the Subject and on an attachment filename -------------------
#
# M3 closed the body paths and left these two open. R-SEC put `BIDI_SPOOF` verbatim into a
# `Subject` header and into an attachment's `filename` and found both reaching
# `ProcessedMessage.subject` / `AttachmentRow.filename` byte-for-byte, unstripped and
# unflagged - the canonical form of the very attack M3 cites as its rationale, since a
# filename that reads `....pdf` is what a person looks at to decide what a file is.


def test_a_bidi_override_does_not_reach_the_subject() -> None:
    processed = process_message(
        mime_kit.message(
            mime_kit.part(
                "text/plain",
                charset="utf-8",
                data=b"body",
                headers=[("Subject", BIDI_SPOOF)],
            )
        )
    )
    assert processed.subject is not None
    assert "‮" not in processed.subject
    assert "‬" not in processed.subject
    assert processed.subject.startswith("Invoice_"), "the readable text must survive the strip"

    declared = [
        r for r in reductions_of(processed, ReductionKind.HIDDEN_CONTENT) if r.header == "subject"
    ]
    assert declared, "the subject strip was not declared as a Reduction"
    assert HiddenConstruct.BIDI_OVERRIDE in declared[0].constructs
    assert declared[0].removed_chars == 2


def test_a_bidi_override_does_not_reach_an_attachment_filename() -> None:
    processed = process_message(
        mime_kit.message(
            mime_kit.part(
                "multipart/mixed",
                part_id="0",
                parts=[
                    mime_kit.part("text/plain", part_id="0.0", charset="utf-8", data=b"body"),
                    mime_kit.part(
                        "application/pdf",
                        part_id="0.1",
                        filename=BIDI_SPOOF,
                        attachment_id="att-1",
                        size=1024,
                    ),
                ],
            )
        )
    )
    (attachment,) = processed.attachments
    assert "‮" not in attachment.filename
    assert "‬" not in attachment.filename
    assert attachment.filename.startswith("Invoice_")

    declared = [
        r
        for r in reductions_of(processed, ReductionKind.HIDDEN_CONTENT)
        if r.detail is not None and "filename" in r.detail
    ]
    assert declared, "the filename strip was not declared as a Reduction"
    assert HiddenConstruct.BIDI_OVERRIDE in declared[0].constructs
    assert "0.1" in (declared[0].detail or "")
    assert BIDI_SPOOF not in (declared[0].detail or ""), (
        "a reduction record must not re-disclose what it removed"
    )


def test_an_rfc_2047_encoded_subject_is_decoded_before_it_is_stripped() -> None:
    """Order matters: strip the wire form and the control is still there after decoding."""
    import base64

    encoded = base64.b64encode(BIDI_SPOOF.encode("utf-8")).decode("ascii")
    processed = process_message(
        mime_kit.message(
            mime_kit.part(
                "text/plain",
                charset="utf-8",
                data=b"body",
                headers=[("Subject", f"=?utf-8?B?{encoded}?=")],
            )
        )
    )
    assert processed.subject is not None
    assert "‮" not in processed.subject


def test_the_raw_header_value_is_still_retained_unstripped() -> None:
    """D.4a: every reduction leaves a path to the unabridged form, and this is that path."""
    processed = process_message(
        mime_kit.message(
            mime_kit.part(
                "text/plain", charset="utf-8", data=b"body", headers=[("Subject", BIDI_SPOOF)]
            )
        )
    )
    assert processed.headers["subject"].values == (BIDI_SPOOF,)


def test_ordinary_headers_and_filenames_are_left_alone() -> None:
    """No reduction may be declared where nothing was removed, or the signal means nothing."""
    processed = process_message(
        mime_kit.message(
            mime_kit.part(
                "multipart/mixed",
                part_id="0",
                parts=[
                    mime_kit.part("text/plain", part_id="0.0", charset="utf-8", data=b"body"),
                    mime_kit.part(
                        "application/pdf",
                        part_id="0.1",
                        filename="proposal.pdf",
                        attachment_id="att-1",
                        size=10,
                    ),
                ],
                headers=[("Subject", "Q3 planning"), ("From", "amy@x.example")],
            )
        )
    )
    assert processed.subject == "Q3 planning"
    assert processed.attachments[0].filename == "proposal.pdf"
    assert reductions_of(processed, ReductionKind.HIDDEN_CONTENT) == []


def test_hebrew_in_a_subject_and_a_filename_survives() -> None:
    """The strip removes controls, not right-to-left writing. This is the regression that
    would make the fix worse than the finding."""
    hebrew = "שלום עולם"
    processed = process_message(
        mime_kit.message(
            mime_kit.part(
                "multipart/mixed",
                part_id="0",
                parts=[
                    mime_kit.part("text/plain", part_id="0.0", charset="utf-8", data=b"body"),
                    mime_kit.part(
                        "application/pdf",
                        part_id="0.1",
                        filename=f"{hebrew}.pdf",
                        attachment_id="att-1",
                        size=10,
                    ),
                ],
                headers=[("Subject", hebrew)],
            )
        )
    )
    assert processed.subject == hebrew
    assert processed.attachments[0].filename == f"{hebrew}.pdf"
