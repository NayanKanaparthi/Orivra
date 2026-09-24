"""Content processing (WS-07): Gmail payload -> annotated `body_clean` (amendment A7).

`body_clean` is the full body text with classified spans, not a smaller copy of it. The
deleting entry point is gone rather than deprecated: there is no export here that returns
less text than it was given.
"""

from mailweave.content.annotate import (
    DEFAULT_VIEW_CLASSES,
    AnnotatedBody,
    AnnotatedSpan,
    SpanClass,
)
from mailweave.content.decode import DecodedText, UndecodableBody, decode_base64url, decode_text
from mailweave.content.headers import DecodedHeader, collect_headers, decode_encoded_words
from mailweave.content.html_text import HtmlExtraction, HtmlParserName, html_to_text
from mailweave.content.mime import AttachmentRow, Leaf, Selection, select_body, walk
from mailweave.content.normalize import count_tokens, head_truncate, normalise
from mailweave.content.payload import Body, Header, MessagePayload, Part
from mailweave.content.pipeline import ProcessedMessage, process_message
from mailweave.content.quotes import annotate_body, classify_lines
from mailweave.content.reductions import HiddenConstruct, Reduction, ReductionKind

__all__ = [
    "DEFAULT_VIEW_CLASSES",
    "AnnotatedBody",
    "AnnotatedSpan",
    "AttachmentRow",
    "Body",
    "DecodedHeader",
    "DecodedText",
    "Header",
    "HiddenConstruct",
    "HtmlExtraction",
    "HtmlParserName",
    "Leaf",
    "MessagePayload",
    "Part",
    "ProcessedMessage",
    "Reduction",
    "ReductionKind",
    "Selection",
    "SpanClass",
    "UndecodableBody",
    "annotate_body",
    "classify_lines",
    "collect_headers",
    "count_tokens",
    "decode_base64url",
    "decode_encoded_words",
    "decode_text",
    "head_truncate",
    "html_to_text",
    "normalise",
    "process_message",
    "select_body",
    "walk",
]
