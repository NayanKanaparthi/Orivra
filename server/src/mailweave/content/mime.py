"""MIME walk, part selection and attachment metadata (AD D.4a 1).

Gmail already parsed the MIME; this module decides which leaf becomes `body_clean`, and
declares every leaf it did not use. Both caps (depth 12, parts 64) are declared when they
bite, never applied silently.
"""

from __future__ import annotations

from dataclasses import dataclass

from mailweave.constants import MIME_DEPTH_CAP, MIME_PART_CAP
from mailweave.content.html_text import strip_invisible_characters
from mailweave.content.payload import Part
from mailweave.content.reductions import Reduction, ReductionKind, reconcile


@dataclass(frozen=True)
class Leaf:
    """A non-multipart part, with where it sat in the tree."""

    part: Part
    depth: int
    path: tuple[str, ...]

    @property
    def mime_type(self) -> str:
        return self.part.mime_type.split(";")[0].strip().lower()

    @property
    def is_attachment(self) -> bool:
        return bool(self.part.filename) or self.part.body.attachment_id is not None


@dataclass(frozen=True)
class AttachmentRow:
    """Attachment metadata (B-04). Metadata only: no extraction path exists.

    `filename` has had zero-width and bidi controls stripped (R-SEC-011). An attachment
    filename is the *canonical* Trojan-Source target - it is the string a user reads to
    decide what a file is - so it gets the same treatment as the body rather than being
    disclosed as it arrived.
    """

    filename: str
    mime_type: str
    size: int
    part_id: str
    attachment_id: str | None


@dataclass(frozen=True)
class WalkResult:
    leaves: tuple[Leaf, ...]
    reductions: tuple[Reduction, ...]
    depth_capped: bool
    count_capped: bool


def walk(root: Part, depth_cap: int = MIME_DEPTH_CAP, part_cap: int = MIME_PART_CAP) -> WalkResult:
    """Depth-first walk to the leaves, honouring and declaring both caps."""
    leaves: list[Leaf] = []
    visited = 0
    depth_capped = False
    count_capped = False
    skipped_by_depth = 0
    skipped_by_count = 0

    stack: list[tuple[Part, int, tuple[str, ...]]] = [(root, 0, (root.part_id,))]
    while stack:
        part, depth, path = stack.pop(0)
        visited += 1
        if visited > part_cap:
            count_capped = True
            skipped_by_count += 1
            continue
        if part.is_multipart:
            if depth + 1 > depth_cap:
                depth_capped = True
                skipped_by_depth += len(part.parts)
                continue
            for child in part.parts:
                stack.append((child, depth + 1, (*path, child.part_id)))
            continue
        leaves.append(Leaf(part=part, depth=depth, path=path))

    reductions: list[Reduction] = []
    if depth_capped:
        reductions.append(
            Reduction(
                kind=ReductionKind.PART_DEPTH_CAP,
                removed_chars=0,
                count=skipped_by_depth,
                detail=f"MIME nesting deeper than {depth_cap} not walked",
            )
        )
    if count_capped:
        reductions.append(
            Reduction(
                kind=ReductionKind.PART_COUNT_CAP,
                removed_chars=0,
                count=skipped_by_count,
                detail=f"more than {part_cap} parts; the remainder was not walked",
            )
        )
    return WalkResult(
        leaves=tuple(leaves),
        reductions=tuple(reductions),
        depth_capped=depth_capped,
        count_capped=count_capped,
    )


@dataclass(frozen=True)
class Selection:
    """Which leaf becomes the body, and what that choice left unused."""

    chosen: Leaf | None
    chosen_mime: str | None
    unused_alternatives: tuple[Leaf, ...]
    attachments: tuple[AttachmentRow, ...]
    reductions: tuple[Reduction, ...]


def _body_bytes(leaf: Leaf) -> int:
    return leaf.part.body.size or (len(leaf.part.body.data or "") * 3) // 4


def select_body(walked: WalkResult) -> Selection:
    """Prefer `text/plain`; fall back to `text/html`; declare the part not used.

    "Absent or empty" is decided on the encoded body length, because deciding it on the
    decoded text would require decoding a part we may never use.
    """
    text_parts = [
        leaf for leaf in walked.leaves if leaf.mime_type == "text/plain" and not leaf.is_attachment
    ]
    html_parts = [
        leaf for leaf in walked.leaves if leaf.mime_type == "text/html" and not leaf.is_attachment
    ]
    attachments: list[AttachmentRow] = []
    filename_reductions: list[Reduction] = []
    for leaf in walked.leaves:
        if not leaf.is_attachment:
            continue
        cleaned = strip_invisible_characters(leaf.part.filename)
        if cleaned.removed_chars:
            filename_reductions.append(
                Reduction(
                    kind=ReductionKind.HIDDEN_CONTENT,
                    removed_chars=reconcile(
                        "attachment filename invisible-character strip",
                        leaf.part.filename,
                        cleaned.text,
                        cleaned.removed_chars,
                    ),
                    count=cleaned.removed_chars,
                    constructs=cleaned.constructs,
                    # The part id, never the filename: a reduction record is disclosed and
                    # must not become the second copy of what it just removed.
                    detail=(
                        f"invisible format characters (Unicode general category Cf) removed "
                        f"from the filename of part {leaf.part.part_id or '<root>'}"
                    ),
                )
            )
        attachments.append(
            AttachmentRow(
                filename=cleaned.text,
                mime_type=leaf.mime_type,
                size=leaf.part.body.size,
                part_id=leaf.part.part_id,
                attachment_id=leaf.part.body.attachment_id,
            )
        )

    non_empty_text = [leaf for leaf in text_parts if (leaf.part.body.data or "").strip()]
    non_empty_html = [leaf for leaf in html_parts if (leaf.part.body.data or "").strip()]

    chosen: Leaf | None = None
    unused: list[Leaf] = []
    if non_empty_text:
        chosen = non_empty_text[0]
        unused = [*non_empty_text[1:], *non_empty_html]
    elif non_empty_html:
        chosen = non_empty_html[0]
        unused = list(non_empty_html[1:])

    reductions = [
        Reduction(
            kind=ReductionKind.ALTERNATIVE_PART_UNUSED,
            removed_chars=0,
            mime=leaf.mime_type,
            bytes=_body_bytes(leaf),
            detail=f"part {leaf.part.part_id or '<root>'} not used for body_clean",
        )
        for leaf in unused
    ]
    return Selection(
        chosen=chosen,
        chosen_mime=chosen.mime_type if chosen else None,
        unused_alternatives=tuple(unused),
        attachments=tuple(attachments),
        reductions=(*walked.reductions, *filename_reductions, *reductions),
    )
