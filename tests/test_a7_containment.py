"""Amendment A7's gate: **no input text is absent from the annotated output.**

This is the only content gate this round, and it replaces "zero false positives on sender
prose". It is character-level, total, and mechanically checkable, and it is stated here over
**generated** input rather than over fixtures - because the last four rounds each passed a
corpus and were then defeated by a corpus nobody had thought of:

| round | measured | then |
|---|---|---|
| 5 | fixed the stripper | round 6 defeated it with an adverb |
| 6 | narrowed the rule | round 7 found the library decided first |
| 7 | 0 false positives | the measurement was of a path the text did not take |
| 8 | 0/200 across three corpora | a fourth corpus destroyed 14/54, and the latch 1,251/1,251 |

A corpus is evidence about the shapes somebody thought of. A property over arbitrary input
is not, which is why the gate is written this way and why the corpus checks below are
*restatements* of it rather than the gate itself.

## What is gated here, and what is not

Gated: the annotation stage is **total over its input**. Every character handed to
`annotate_body` is present, in order, exactly once, in the `AnnotatedBody` it returns; and
`process_message` hands `body_clean` a body no shorter than the text that reached that
stage.

Not gated, and said plainly rather than implied: the stages *upstream* of annotation still
remove things and still declare each removal with a count - markup becomes visible text,
zero-width and bidi controls are stripped (R-SEC-005), NFKC folds ligatures, whitespace runs
collapse. A7 replaces the operation that used to delete **sentences**; it does not claim the
charset ladder is lossless. `test_the_whole_pipeline_keeps_every_visible_character` states
the strongest whole-pipeline property that is actually true - for a `text/plain` body of
NFKC-stable, visible characters, the pipeline's output carries every non-whitespace
character of its input, in order - and it is a real check rather than a restatement of the
stage-level one.
"""

from __future__ import annotations

import unicodedata

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mailweave.content.annotate import (
    AnnotatedBody,
    AnnotatedSpan,
    SpanClass,
    build_annotation,
)
from mailweave.content.html_text import HtmlParserName, html_to_text
from mailweave.content.pipeline import process_message
from mailweave.content.quotes import annotate_body
from mailweave.errors import AnnotationContainmentError
from tests.fixtures import mime_kit as kit
from tests.fixtures.reply_chains import (
    CORPUS,
    LATCH_CORPUS,
    PROSE_CORPORA,
    PROSE_POSITIONS,
)


def contains_everything(text: str) -> None:
    """A7's gate, written once, as the single assertion every case below makes."""
    body = annotate_body(text)
    assert body.text == text, "the annotated body is not the text it was given"
    rejoined = "".join(text[span.start : span.end] for span in body.spans)
    assert rejoined == text, (
        f"re-joining the spans lost or duplicated characters: {len(rejoined)} of {len(text)}"
    )
    cursor = 0
    for span in body.spans:
        assert span.start == cursor, f"span {span} does not continue from character {cursor}"
        assert span.end > span.start, f"span {span} is empty"
        cursor = span.end
    assert cursor == len(text), f"the annotation stops at {cursor} of {len(text)}"


# --- the gate itself, over generated input ----------------------------------------------

#: A wide alphabet: every ASCII character including the control range, the five non-`\n`
#: Unicode line boundaries `str.splitlines()` recognises, and characters from scripts whose
#: normalisation and casing rules differ. Nothing here is chosen to be *easy*.
ARBITRARY_TEXT = st.text(
    alphabet=st.one_of(
        st.characters(min_codepoint=0, max_codepoint=0x7F),
        st.sampled_from("  ​‮﻿ "),
        st.characters(min_codepoint=0x80, max_codepoint=0x2FFF),
        st.characters(min_codepoint=0x4E00, max_codepoint=0x9FFF),
        st.sampled_from(">-_:@.\n \t"),
    ),
    max_size=400,
)

#: The same gate over input shaped like mail, so the generator explores the *structures*
#: the classifier reacts to rather than only random noise. Random text almost never contains
#: a header block or a recognised attribution line; this strategy contains little else.
MAIL_FRAGMENTS = st.sampled_from(
    [
        "",
        "Two points before Friday.",
        "Thanks for the update on this.",
        "> The freeze starts Friday.",
        ">> nested quote",
        "-----Original Message-----",
        "Original Message",
        "Begin forwarded message:",
        "---------- Forwarded message ---------",
        "From: Priya Shah <priya@example.com>",
        "Sent: Monday, August 24, 2026 9:02 AM",
        "To: Dana Whitfield <dana@example.com>",
        "Subject: Renewal pricing",
        "Cc: finance@example.com",
        "On Tue, Aug 25, 2026 at 3:14 PM Priya <p@x.example> wrote:",
        "Am Di., 25. Aug. 2026 um 15:14 schrieb Priya <p@x.example>:",
        "On 25/08/2026 15:14, Priya Shah wrote:",
        "Once the negotiations concluded, the legal team wrote:",
        "To: recap, we need three approvals before Friday.",
        "From: what I can tell, the budget already covers this.",
        "--",
        "__",
        "-1 day change to the schedule",
        "Thanks,",
        "Best regards,",
        "Sent from my iPhone",
        "Dana Whitfield",
        "P.S. I also need the invoice number.",
        "   ",
        "\t",
    ]
)
MAIL_SHAPED_TEXT = st.lists(MAIL_FRAGMENTS, max_size=25).map("\n".join)


@settings(max_examples=400, suppress_health_check=[HealthCheck.too_slow])
@given(ARBITRARY_TEXT)
def test_no_input_character_is_absent_from_the_annotated_output(text: str) -> None:
    """**The gate.** Arbitrary input, character for character, in order, exactly once.

    Not defeatable by a corpus nobody thought of, because it is not measured against a
    corpus. The alphabet deliberately includes the control range, the Unicode line
    boundaries that are not `\\n`, and CJK, so an implementation that assumed "lines are
    separated by newlines and characters are one column wide" fails here.
    """
    contains_everything(text)


@settings(max_examples=400, suppress_health_check=[HealthCheck.too_slow])
@given(MAIL_SHAPED_TEXT)
def test_the_gate_holds_over_generated_mail_shapes(text: str) -> None:
    """The same gate where the classifier is actually doing something.

    Random text rarely trips a structural signal, so a gate measured only over it would be
    measuring the empty branch. These fragments are the signals themselves, in every order
    and nesting the generator can assemble - including the two shapes R-ARCH-025 found and
    the three that latch.
    """
    contains_everything(text)


@settings(max_examples=200)
@given(st.lists(MAIL_FRAGMENTS, max_size=15).map("\n".join))
def test_the_annotation_hides_text_but_never_lacks_it(text: str) -> None:
    """The default view may be as small as it likes; the body may not be.

    This is A7's economics and its guarantee stated as one property: whatever the classifier
    decides, `view()` is a subsequence of `text` and `text` is the whole input. A round that
    makes the default view worse cannot make the body lossy.
    """
    body = annotate_body(text)
    assert body.text == text
    assert len(body.view()) <= len(body.text)
    assert body.hidden_chars == len(body.text) - len(body.view())
    widest = body.view(list(SpanClass))
    assert widest == text, "showing every class must reproduce the whole body"


# --- the gate is live, not decorative ---------------------------------------------------


def test_an_annotation_that_loses_a_character_cannot_be_constructed() -> None:
    """The containment check runs in `AnnotatedBody.__post_init__`, so there is no path past it.

    Each of these is a different way to lose or duplicate a character, and every one of them
    is refused at construction rather than reported later. This is what makes the gate a
    property of the type rather than a test somebody has to remember to run - the same move
    that made `withheld := H - disclosed` structural for evidence.
    """
    text = "alpha\nbeta\n"
    original = SpanClass.ORIGINAL

    def span(start: int, end: int) -> AnnotatedSpan:
        return AnnotatedSpan(
            start=start, end=end, classification=original, signal="no_structural_signal"
        )

    # a gap: the middle of the body is in no span at all
    with pytest.raises(AnnotationContainmentError, match="absent from"):
        AnnotatedBody(text=text, spans=(span(0, 3), span(5, len(text))))
    # a short tiling: the tail of the body is in no span
    with pytest.raises(AnnotationContainmentError, match="absent from the"):
        AnnotatedBody(text=text, spans=(span(0, 6),))
    # an overlap: a character counted twice
    with pytest.raises(AnnotationContainmentError, match="duplicated"):
        AnnotatedBody(text=text, spans=(span(0, 6), span(4, len(text))))
    # a span running past the end
    with pytest.raises(AnnotationContainmentError, match="past the end"):
        AnnotatedBody(text=text, spans=(span(0, len(text) + 3),))
    # no spans at all for a body with characters in it
    with pytest.raises(AnnotationContainmentError, match="carries no spans"):
        AnnotatedBody(text=text, spans=())
    # an empty span names no characters
    with pytest.raises(AnnotationContainmentError, match="empty or negative"):
        span(2, 2)
    # a span with no signal: A7 requires every span to say what classified it
    with pytest.raises(AnnotationContainmentError, match="names no signal"):
        AnnotatedSpan(start=0, end=1, classification=original, signal="")
    # and the honest case is accepted
    assert AnnotatedBody(text=text, spans=(span(0, len(text)),)).view() == text


def test_a_classification_that_skips_a_line_is_refused() -> None:
    """The assembler cannot be handed a classification that does not cover the lines."""
    with pytest.raises(AnnotationContainmentError, match="every line of the input"):
        build_annotation("one\ntwo\n", [(SpanClass.ORIGINAL, "no_structural_signal")])


def test_there_is_no_deleting_entry_point_left_in_the_content_package() -> None:
    """A7 removed the operation rather than guarding it.

    Round 8's fix was that `strip_quotes_and_signature` was the *sole* writer of
    `body_clean`, with a runtime assertion above it. That is a guard on a path. A7's claim
    is stronger and this is how it is checked: the path does not exist. A future change that
    reintroduces a deleting function has to reintroduce it by name, in a diff, rather than
    reach for one that is still sitting there.
    """
    import mailweave.content as content
    import mailweave.content.quotes as quotes

    assert not hasattr(quotes, "strip_quotes_and_signature")
    assert not hasattr(quotes, "StripResult")
    assert not hasattr(content, "strip_quotes_and_signature")
    assert "strip_quotes_and_signature" not in content.__all__


# --- the corpora, as restatements of the gate rather than as the gate --------------------


def _every_corpus_body() -> list[tuple[str, str]]:
    bodies: list[tuple[str, str]] = []
    for case in CORPUS:
        body = case.body
        if case.html:
            body = html_to_text(body, HtmlParserName.SELECTOLAX).text
        bodies.append((f"corpus/{case.name}", body))
    for corpus_name, corpus in sorted(PROSE_CORPORA.items()):
        for position, (placer, _context) in sorted(PROSE_POSITIONS.items()):
            assert callable(placer)
            for name, line in corpus:
                bodies.append((f"{corpus_name}/{position}/{name}", str(placer(line))))
    for name, body, _tagged in LATCH_CORPUS:
        bodies.append((f"latch/{name}", body))
    return bodies


@pytest.mark.parametrize(("name", "body"), _every_corpus_body(), ids=lambda value: str(value)[:60])
def test_every_corpus_body_survives_annotation_whole(name: str, body: str) -> None:
    """All four prose corpora in both positions, the reply-chain corpus, and the latch corpus.

    These do not gate anything the property above does not already gate. They are here
    because a reviewer reproducing R-ARCH-025 or R-ARCH-026 should find the exact case they
    wrote, passing, rather than have to trust that a generated string covered it.
    """
    contains_everything(body)


def test_the_pipeline_stage_that_used_to_delete_now_declares_zero() -> None:
    """The stage's own accounting, per message, in the production path.

    `content/pipeline.py` hands `reconcile` a declared removal of **zero** for the annotation
    stage, so a change that started shrinking the body again fails the pipeline rather than
    shipping a shorter one. This exercises that path end to end for every reply-chain case.
    """
    for case in CORPUS:
        payload = kit.message(kit.part("text/plain", data=case.body.encode(), charset="utf-8"))
        processed = process_message(payload)
        annotated_input = processed.body_clean.text
        assert processed.body_clean.view(list(SpanClass)) == annotated_input
        for reduction in processed.reductions:
            if reduction.stripper is not None:
                assert reduction.removed_chars == 0, (
                    f"{case.name}: the classifier declared a removal of "
                    f"{reduction.removed_chars} characters; under A7 it removes nothing"
                )


# --- the whole pipeline, not only the stage ---------------------------------------------

#: Visible characters that NFKC leaves alone and the invisible-character strip does not
#: touch, so the only thing the pipeline may do to them is whitespace folding. Deliberately
#: not "printable ASCII": accented Latin and CJK are included because a pipeline that indexes
#: by byte rather than by character passes the ASCII-only version of this test.
VISIBLE_TEXT = st.text(
    alphabet=st.sampled_from(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        " \n\t.,:;!?'\"()[]<>@/\\-_+=*&%$#>éàüñçöß日本語한글"
    ),
    max_size=600,
)


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(VISIBLE_TEXT)
def test_the_whole_pipeline_keeps_every_visible_character(text: str) -> None:
    """From the decoded body to `body_clean.text`, for the `text/plain` path.

    The stage-level gate above says annotation loses nothing. This says the *pipeline* loses
    nothing visible: every non-whitespace character of the decoded body appears in
    `body_clean.text`, in the same order, with the same multiplicity. Whitespace is excluded
    because AD D.4a 7's collapse is a declared reduction that predates A7 and is not what A7
    replaced; NFKC is applied to the expectation rather than assumed away, because folding a
    ligature is a real transformation and pretending otherwise would be the overclaim this
    file exists to avoid.
    """
    payload = kit.message(kit.part("text/plain", data=text.encode("utf-8"), charset="utf-8"))
    processed = process_message(payload)
    expected = "".join(
        character for character in unicodedata.normalize("NFKC", text) if not character.isspace()
    )
    actual = "".join(
        character for character in processed.body_clean.text if not character.isspace()
    )
    assert actual == expected, (
        "the pipeline lost or reordered visible characters between the decoded body and body_clean"
    )


def test_a_disclosed_row_outside_every_claimed_set_is_context_not_a_stub() -> None:
    """R-M2-056, pinned at the seam it broke.

    `_rows_of` takes a row's role from which set claimed the message and its depth from the
    plan. The last branch - the plan included this message and nothing above claimed it -
    answered `Role.STUB` whatever the depth was, so a message the plan had decided to disclose
    arrived as `role=stub` at snippet depth. `MessageRow` refuses that pairing, correctly, and
    the search raised instead of answering. It is reachable whenever the plan discloses beyond
    the hit, structural and fill sets, which a query matching nothing does - EP §4.3's F10
    unanswerable control, so the campaign met it on every control case.

    The test asserts the invariant rather than the branch: **no row may pair `role=stub` with a
    depth that is not `stub`**, and a query that matches nothing must answer rather than raise.
    """
    from mailweave.envelope.vocab import Depth, Role
    from mailweave.surface.arguments import parse_search
    from tests.fixtures.eval_dummy import dummy_arms, dummy_manifest, mailbox_of

    manifest = dummy_manifest()
    box, _report = mailbox_of(manifest)
    arm = dummy_arms(manifest, box)[0]

    envelope = arm.service.search(
        parse_search({"query": "zzzq-no-such-token-anywhere-in-this-corpus"})
    )
    rows = [row for source in envelope.sources for row in source.messages]
    assert rows, "a query that matches nothing still names what it looked at"
    for row in rows:
        assert not (row.role is Role.STUB and row.depth is not Depth.STUB), (
            f"{row.id}: role=stub at depth={row.depth.value}"
        )
