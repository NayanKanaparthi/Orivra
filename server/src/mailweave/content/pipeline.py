"""The content pipeline end to end: Gmail payload -> annotated `body_clean` + reductions.

Order is AD D.4a's order with one step reordered by amendment A7: part selection, base64url
decode, charset ladder, header decode, HTML to visible text, NFKC + whitespace, **span
annotation**, and an optional head truncation of the *view*. Every step that removes
anything still emits a `Reduction` with a count.

## What A7 changed here, and what it did not

`body_clean` is no longer a string this module shrinks. It is an `AnnotatedBody`: the full
text, plus spans classifying every character as `quoted`, `signature`, `forwarded`,
`original` or `uncertain`. The annotation stage removes **nothing**, and the reconciliation
below asserts that per message rather than trusting it - `reconcile` is handed a declared
removal of zero, so a stage that started shrinking the text again would fail the pipeline
instead of shipping a body that quietly lost a sentence.

`normalise` moved to *before* annotation. Span offsets have to index the text they are
returned with, and normalisation rewrites that text (NFKC folds ligatures, whitespace runs
collapse), so annotating first and normalising after would leave every span pointing at the
wrong characters. Normalisation is a declared reduction and was one before A7; what A7 gates
is the stage that used to delete sentences, and the honest statement of the gate's reach is
in `tests/test_a7_containment.py` rather than implied here.

Head truncation is A.9a's, and under A7 it is a property of the **view** the disclosure
layer asks for, not of the annotated body: `default_view` is truncated and
`body_clean.text` is whole, so the truncated text is returned exactly by
`body_clean.view(list(SpanClass))` like every other reduction in depth. That - widening to
every class - is the recovery guarantee; widening by one class is not (R-ARCH-029).

Nothing in this module touches the network. The HTML parsers do no I/O and the whole
pipeline is exercised in a suite that disables sockets (RR INJ-04 zero-network condition).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mailweave.constants import HTML_DEPTH_CAP, HTML_SOURCE_CHAR_CAP
from mailweave.content.annotate import AnnotatedBody, SpanClass
from mailweave.content.decode import UndecodableBody, decode_base64url, decode_text
from mailweave.content.headers import DecodedHeader, collect_headers, content_type_charset
from mailweave.content.html_text import (
    HtmlParserName,
    html_to_text,
    strip_invisible_characters,
)
from mailweave.content.mime import AttachmentRow, Selection, select_body, walk
from mailweave.content.normalize import count_tokens, head_truncate, normalise
from mailweave.content.payload import MessagePayload, Part
from mailweave.content.quotes import (
    ambiguity_reason,
    ambiguous_lines,
    annotate_body,
    classifier_version,
)
from mailweave.content.reductions import Reduction, ReductionKind, reconcile
from mailweave.errors import ContentProcessingError


@dataclass(frozen=True)
class ProcessedMessage:
    """What content processing hands to representation.

    `body_clean` is an `AnnotatedBody` rather than a string (amendment A7): the whole body
    text with every character inside a classified span. A consumer asks it for a *view*
    instead of reading a pre-trimmed copy, and `default_view` is the one A7 names -
    `original` spans only, which reproduces the string round 8 called `body_clean` and its
    token economics.

    `body_tokens` counts the default view, unchanged in meaning from round 8, so the
    disclosure budgets it feeds are measured against the text a caller is actually shown.
    What is no longer true is that everything else is gone.
    """

    message_id: str
    thread_id: str
    subject: str | None
    headers: dict[str, DecodedHeader]
    body_clean: AnnotatedBody
    default_view: str
    body_source_mime: str | None
    attachments: tuple[AttachmentRow, ...]
    reductions: tuple[Reduction, ...]
    undecodable: bool = False
    charset_used: str | None = None
    body_tokens: int = 0

    def header_display(self, name: str) -> str | None:
        entry = self.headers.get(name.lower())
        return entry.display if entry else None


@dataclass
class _Accumulator:
    reductions: list[Reduction] = field(default_factory=list)

    def add(self, reduction: Reduction) -> None:
        self.reductions.append(reduction)


def _raw_headers(part: Part) -> list[tuple[str, str]]:
    return [(h.name, h.value) for h in part.headers]


def _declare_charset(acc: _Accumulator, decoded: object, declared: str | None) -> None:
    from mailweave.content.decode import DecodedText

    assert isinstance(decoded, DecodedText)
    if declared and not decoded.charset_known:
        acc.add(
            Reduction(
                kind=ReductionKind.UNKNOWN_CHARSET,
                removed_chars=0,
                charset_declared=declared,
                charset_used=decoded.charset_used,
                detail="declared charset is not a known codec; ladder used instead",
            )
        )
    if decoded.replacements or decoded.fell_back or (declared and not decoded.charset_known):
        acc.add(
            Reduction(
                kind=ReductionKind.CHARSET_REPLACEMENTS,
                removed_chars=0,
                count=decoded.replacements,
                charset_used=decoded.charset_used,
                charset_declared=declared,
            )
        )


def _classification_detail(classification: SpanClass, signals: tuple[str, ...]) -> str:
    """What a `quoted` or `signature` reduction says about *how* it decided (A5, A7).

    Amendment A5 permits treating text as prior conversation only on a strong structural
    signal, and round 8 made this repository's own classifier the only thing that decides
    one. Naming the signal in the reduction is the other half: a reader can then tell a
    region bounded by the client's own markers - a `>` run ends where the markers end - from
    one whose end nobody marked.

    Under A7 the second kind is classified `uncertain` rather than deleted, so this detail
    says what a caller can *do* about it - the characters are in `body_clean` and a view over
    every span class returns them - instead of warning that they are gone. The detail names
    the class, so a caller widening by one class knows which one; it does not promise that
    one step is enough, because for a *mis*classified region it is not (R-ARCH-029).
    """
    named = ", ".join(signals) if signals else "none"
    return (
        f"{classification.value} spans classified on: {named}; the text is present in "
        "body_clean and excluded from the default view, which shows original spans "
        "(amendment A7); count is the number of characters classified"
    )


def process_message(
    message: MessagePayload,
    *,
    html_parser: HtmlParserName = HtmlParserName.SELECTOLAX,
    head_truncate_tokens: int | None = None,
) -> ProcessedMessage:
    """Produce `body_clean` for one message, with every removal declared.

    `head_truncate_tokens` is supplied by the disclosure ladder (A.9a steps 3-4); this
    function never decides to truncate on its own.
    """
    acc = _Accumulator()

    headers, header_reductions = collect_headers(_raw_headers(message.payload))
    for reduction in header_reductions:
        acc.add(reduction)
    subject = headers["subject"].display if "subject" in headers else None

    selection: Selection = select_body(walk(message.payload))
    for reduction in selection.reductions:
        acc.add(reduction)

    if selection.chosen is None:
        return ProcessedMessage(
            message_id=message.id,
            thread_id=message.thread_id,
            subject=subject,
            headers=headers,
            body_clean=AnnotatedBody.empty(),
            default_view="",
            body_source_mime=None,
            attachments=selection.attachments,
            reductions=tuple(acc.reductions),
        )

    leaf = selection.chosen
    encoded = leaf.part.body.data or ""
    try:
        raw = decode_base64url(encoded)
    except UndecodableBody as failure:
        acc.add(
            Reduction(
                kind=ReductionKind.UNDECODABLE_BODY,
                removed_chars=0,
                bytes=failure.byte_length,
                mime=leaf.mime_type,
                detail="base64url decode failed; message disclosed with an empty body",
            )
        )
        return ProcessedMessage(
            message_id=message.id,
            thread_id=message.thread_id,
            subject=subject,
            headers=headers,
            body_clean=AnnotatedBody.empty(),
            default_view="",
            body_source_mime=leaf.mime_type,
            attachments=selection.attachments,
            reductions=tuple(acc.reductions),
            undecodable=True,
        )

    declared_charset = content_type_charset(leaf.part.header("Content-Type"))
    decoded = decode_text(raw, declared_charset)
    _declare_charset(acc, decoded, declared_charset)
    text = decoded.text

    if leaf.mime_type == "text/html":
        extraction = html_to_text(text, html_parser)
        if extraction.size_capped_chars:
            acc.add(
                Reduction(
                    kind=ReductionKind.HTML_SIZE_CAP,
                    removed_chars=extraction.size_capped_chars,
                    parser=extraction.parser,
                    detail=(
                        f"source html exceeded {HTML_SOURCE_CHAR_CAP} characters and was "
                        "truncated before parsing"
                    ),
                )
            )
        if extraction.depth_capped_chars:
            acc.add(
                Reduction(
                    kind=ReductionKind.HTML_DEPTH_CAP,
                    removed_chars=extraction.depth_capped_chars,
                    count=extraction.depth_capped_tags,
                    parser=extraction.parser,
                    detail=(
                        f"markup nested deeper than {HTML_DEPTH_CAP} was flattened "
                        f"(deepest nesting seen: {extraction.max_depth_seen}); the text "
                        "inside it is retained"
                    ),
                )
            )
        # The count that goes on the wire is this pipeline's own measurement of the
        # stage, not the extractor's account of itself.
        acc.add(
            Reduction(
                kind=ReductionKind.HTML_TO_TEXT,
                removed_chars=max(0, len(text) - len(extraction.text)),
                parser=extraction.parser,
                detail="markup removed; visible text retained",
            )
        )
        if extraction.lost_text_chars:
            acc.add(
                Reduction(
                    kind=ReductionKind.HTML_PARSE_LOST_TEXT,
                    removed_chars=extraction.lost_text_chars,
                    parser=extraction.parser,
                    detail=(
                        "the parser produced no visible text from source that contained "
                        "some; the body is disclosed empty and the loss is counted rather "
                        "than absorbed"
                    ),
                )
            )
        if extraction.constructs:
            acc.add(
                Reduction(
                    kind=ReductionKind.HIDDEN_CONTENT,
                    removed_chars=extraction.hidden_removed_chars,
                    count=extraction.nodes_removed,
                    constructs=extraction.constructs,
                    parser=extraction.parser,
                )
            )
        text = extraction.text

    # Every Unicode format character, for every body: the HTML path has already had them
    # removed by the extractor, so this is where a `text/plain` body gets the same
    # treatment (R-SEC-005) rather than reaching `body_clean` unchanged. "Every" is the
    # word round 10 earned - the set is derived from `unicodedata`, where until then it was
    # 16 code points somebody typed out of the 170 that exist (R-SEC-033).
    invisible = strip_invisible_characters(text)
    if invisible.removed_chars:
        acc.add(
            Reduction(
                kind=ReductionKind.HIDDEN_CONTENT,
                removed_chars=reconcile(
                    "invisible-character strip", text, invisible.text, invisible.removed_chars
                ),
                count=invisible.removed_chars,
                constructs=invisible.constructs,
                detail="invisible format characters removed (Unicode general category Cf)",
            )
        )
    text = invisible.text

    # AD D.4a 7 runs before annotation under A7: span offsets index the text they travel
    # with, and normalisation rewrites that text. Normalising after annotating would leave
    # every span pointing at characters that had moved.
    normalised = normalise(text)
    if normalised.removed_chars:
        acc.add(
            Reduction(
                kind=ReductionKind.WHITESPACE_NORMALISED,
                removed_chars=reconcile(
                    "normalisation", text, normalised.text, normalised.removed_chars
                ),
                detail="NFKC + whitespace collapse",
            )
        )
    text = normalised.text

    # Amendment A7's stage. It classifies and removes nothing, and the two checks below say
    # so mechanically rather than in a comment: `annotated.text` must be the text that went
    # in, so a future change that started shrinking the body again fails the pipeline instead
    # of shipping a shorter one. The identity check is the strictly stronger of the two and
    # fires first; `reconcile` stays because it is the shape every other stage of this
    # pipeline is checked in, and a stage that opted out of the common check would be the one
    # a reader stops looking at.
    annotated = annotate_body(text)
    if annotated.text != text:  # pragma: no cover - annotate_body cannot produce this
        raise ContentProcessingError(
            "span annotation returned a body that is not the text it was given; amendment "
            "A7 gates on every input character being present in the annotated output"
        )
    reconcile("span annotation", text, annotated.text, 0)

    for classification in (SpanClass.QUOTED, SpanClass.FORWARDED, SpanClass.UNCERTAIN):
        classified = annotated.chars(classification)
        if classified:
            acc.add(
                Reduction(
                    kind=ReductionKind.QUOTED,
                    removed_chars=0,
                    count=classified,
                    stripper=classifier_version(),
                    detail=_classification_detail(
                        classification, annotated.signals(classification)
                    ),
                )
            )
    signature_chars = annotated.chars(SpanClass.SIGNATURE)
    if signature_chars:
        acc.add(
            Reduction(
                kind=ReductionKind.SIGNATURE,
                removed_chars=0,
                count=signature_chars,
                stripper=classifier_version(),
                detail=_classification_detail(
                    SpanClass.SIGNATURE, annotated.signals(SpanClass.SIGNATURE)
                ),
            )
        )
    ambiguity = ambiguity_reason(annotated)
    if ambiguity is not None:
        # Amendment A5, unchanged by A7: where the classifier is unsure in A5's sense it
        # keeps the line as the sender's own and says so, so the ambiguity is visible in the
        # response instead of being resolved silently. The record is a real reduction record
        # with `removed_chars=0` and a count of the lines involved; `Reduction` accepts a
        # zero removal only when a count is present, which stops this becoming a decorative
        # note.
        acc.add(
            Reduction(
                kind=ReductionKind.QUOTED,
                removed_chars=0,
                count=ambiguous_lines(annotated),
                stripper=classifier_version(),
                detail=ambiguity,
            )
        )

    # The default view A7 names, re-collapsed: dropping the classified spans leaves the
    # blank lines that sat on either side of them, and the same normaliser that produced
    # the body's whitespace folds them. This is a rendering of a view, not a reduction of
    # `body_clean` - every character it folds is still in `annotated.text`.
    view = normalise(annotated.view()).text

    if head_truncate_tokens is not None:
        truncation = head_truncate(view, head_truncate_tokens)
        if truncation.truncated:
            acc.add(
                Reduction(
                    kind=ReductionKind.BODY_HEAD_TRUNCATED,
                    removed_chars=reconcile(
                        "head truncation", view, truncation.text, truncation.removed_chars
                    ),
                    kept_tokens=truncation.kept_tokens,
                    detail=(
                        "A.9a head truncation of the default view; whitespace tokens. The "
                        "annotated body is untouched, so the truncated text is returned by "
                        "a view over every span class (amendment A7)"
                    ),
                )
            )
        view = truncation.text

    return ProcessedMessage(
        message_id=message.id,
        thread_id=message.thread_id,
        subject=subject,
        headers=headers,
        body_clean=annotated,
        default_view=view,
        body_source_mime=leaf.mime_type,
        attachments=selection.attachments,
        reductions=tuple(acc.reductions),
        charset_used=decoded.charset_used,
        body_tokens=count_tokens(view),
    )
