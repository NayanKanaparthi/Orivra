"""One serialisation, two renderings that cannot disagree (MCP-03).

**The structured form is produced by the envelope's own serialiser and by nothing else.**
`Envelope.model_dump` is the wire chokepoint rounds 13 and 14 built: it re-establishes every
after-validator of the whole model tree, produces the mapping, and then reads I-1's and
I-2's claims back out of that mapping and compares them with the certificate. So a payload
that reaches a client has already been checked, and this module adds no second path around
it - `structured_content` is that mapping, unmodified.

**The text form is a projection of the structured form.** `text_of` takes the mapping, never
the `Envelope`, so there is no route by which the text could state a fact the structured
content does not carry: the only thing it can read is the thing the client is also getting.
That is what makes "they cannot drift" a property of the shape of the code rather than a
discipline. `render` is the only public way to build both, and it builds the text out of the
structured mapping it just produced.

**And the projection is round-tripped, not merely asserted.** `MIRRORS` is a table of the
facts the text is required to carry; each entry knows how to `extract` its fact from the
structured mapping *and* how to `read_back` the same fact out of the rendered text. The
parity property is `read_back(text_of(s)) == extract(s)` for every mirror over generated
responses - a real round-trip, so a renderer that omits a fact, renders a different value, or
rounds one, fails rather than passing because both sides were computed the same way.

The rendering is prose because a model reads it, and it is line-oriented and regular because
the round-trip has to be able to read it. Both halves of that are load-bearing.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from mailweave.constants import is_one_line
from mailweave.envelope.response import Envelope
from mailweave.errors import MailweaveError

Structured = Mapping[str, Any]


@dataclass(frozen=True)
class Rendered:
    """What one tool call hands to the protocol layer."""

    structured: dict[str, Any]
    text: str


def _rows(structured: Structured) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    out: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for source in structured.get("sources") or ():
        for row in source.get("messages") or ():
            out.append((source, row))
    return out


def _yes(value: object) -> str:
    return "yes" if value else "no"


def _flag(word: str) -> bool:
    return word == "yes"


# --- the rendering -------------------------------------------------------------------------


def _header_lines(structured: Structured) -> list[str]:
    report = structured.get("retrieval_report") or {}
    ceiling = structured.get("ceiling") or {}
    lines = [
        f"outcome: {report.get('outcome')}; partial: {_yes(structured.get('partial'))}; "
        f"truncated_by: {structured.get('truncated_by') or 'nothing'}",
        f"ceiling: applied {ceiling.get('applied')} of normal {ceiling.get('normal')} tokens",
        f"rungs run: {', '.join(report.get('rungs') or ()) or 'none'}",
        f"sufficiency: {report.get('sufficiency')}; caps hit: "
        f"{', '.join(report.get('budget_caps_hit') or ()) or 'none'}",
    ]
    clamp = (structured.get("budget") or {}).get("clamped")
    if clamp is not None:
        lines.append(
            f"budget clamped: requested {clamp.get('requested')}, applied {clamp.get('applied')}"
        )
    if structured.get("sources"):
        lines.append(ATTRIBUTION_NOTE)
    return lines


#: One sentence, once per response that carries rows, saying what the per-row `attribution`
#: and `internal_date` lines are and are not (2026-09-22). The structured form says it by
#: shape - there is no `sender`, `author` or `verified` field, and the provenance tokens name
#: a header - and a reader of the text alone was given no shape to read: the first live runs
#: presented "X said" as an explicit statement on the strength of body text, and the retest
#: that carried the new fields in the structured form carried nothing of them in the text.
#: A constant, so it costs the same on every response and the estimate charges it once.
ATTRIBUTION_NOTE: Final[str] = (
    "attribution on each row is the message's From header as Gmail returned it (an address "
    "and, fenced, a display name): who the header names, not an authenticated identity; "
    "internal_date is when Gmail received the message, in epoch milliseconds"
)


#: How the text mirror spells a row's `mailbox` provenance (R-MCP-010, OD-6 criterion 4).
#: Three states and not two, because `MailboxProvenance` has three: a row whose labels no
#: observation stated says so rather than reporting a negative. `outside_the_default_mailbox`
#: is not spelled separately - it is `bool(regions)` in the model, so a second spelling could
#: only ever disagree with the first.
MAILBOX_UNOBSERVED: Final[str] = "unobserved"
MAILBOX_DEFAULT: Final[str] = "default"


def mailbox_token(provenance: Mapping[str, Any] | None) -> str:
    """One word for where the mailbox holds this message, round-trippable by `_read_rows`."""
    if not provenance or not provenance.get("observed"):
        return MAILBOX_UNOBSERVED
    regions = provenance.get("regions") or ()
    return "+".join(str(region) for region in regions) if regions else MAILBOX_DEFAULT


#: The exact prefix a fenced content line opens with. Written once and used by both the
#: composer and `_every_line_is_one_record`'s exemption, so the exemption is keyed on
#: something this module wrote rather than on a pattern an interpolated value could imitate.
CONTENT_LINE_PREFIX: Final[str] = "    content ("
#: The same, for a row's fenced `From` display name (2026-09-22). A second fenced line and
#: not a second `content (` line, because the content mirror pairs one block with one row
#: and a display name is not the message's text. It is fenced for the reason the body is:
#: a display name is sender-chosen text, and unfenced it would be a line in this
#: connector's voice that the sender wrote (R-MCP-002's class).
DISPLAY_NAME_LINE_PREFIX: Final[str] = "    display_name ("
#: The two fenced-line prefixes `split_fenced` recognises, keyed by the kind it reports.
FENCED_LINE_PREFIXES: Final[tuple[tuple[str, str], ...]] = (
    ("content", CONTENT_LINE_PREFIX),
    ("display_name", DISPLAY_NAME_LINE_PREFIX),
)


def _source_lines(structured: Structured) -> list[str]:
    lines: list[str] = []
    for source in structured.get("sources") or ():
        lines.append(
            f"source thread {source.get('thread_id')}: included {source.get('included')} "
            f"of stated_total {source.get('stated_total')}, "
            f"as_stub {source.get('included_as_stub')}, "
            f"map_id {source.get('map_id') or 'none'}"
        )
        for row in source.get("messages") or ():
            # **`reason` stays last** (R-MCP-010). It is the only free-text field on the line
            # and the only one whose value can contain a comma, so every field a reader parses
            # sits in front of it and the reader takes the rest of the line as the reason.
            lines.append(
                f"  message {row.get('id')} at position {row.get('position')}: "
                f"role {row.get('role')}, depth {row.get('depth')}, "
                f"linkage {row.get('linkage')}, "
                f"reply_parent {row.get('reply_parent_id') or 'none'}, "
                f"mailbox {mailbox_token(row.get('mailbox'))}, "
                f"reason {row.get('reason')}"
            )
            # **Attribution and chronology, with their provenance, on every row**
            # (2026-09-22). The structured form gained them on 2026-09-21 and this mirror
            # did not, so a text-only client - the Desktop surface reads the text - saw no
            # sender and no timestamp on any row and read both out of body text again.
            # The address is a bare token (`is_an_address` admits no whitespace); the
            # display name is fenced, like content, because it is sender-chosen text; the
            # provenance tokens are the closed vocabulary the structured form carries.
            lines.extend(_attribution_lines(row))
            for reduction in row.get("reductions") or ():
                lines.append(
                    f"    reduction {reduction.get('kind')} removed "
                    f"{reduction.get('removed_chars') or 0} chars"
                )
            for attachment in row.get("attachments") or ():
                lines.append(
                    f"    attachment part {attachment.get('part_id')}: "
                    f"{attachment.get('filename')} "
                    f"({attachment.get('mime_type')}, {attachment.get('size')} bytes)"
                )
            content = row.get("content")
            if content is not None:
                lines.append(f"{CONTENT_LINE_PREFIX}{content.get('trust')}) {content.get('text')}")
        for collapsed in source.get("collapsed_runs") or ():
            positions = collapsed.get("positions") or [0, 0]
            lines.append(
                f"  collapsed positions {positions[0]}-{positions[1]}: "
                f"{collapsed.get('count')} messages not shown, expand with "
                f"{(collapsed.get('affordance') or {}).get('tool')}"
            )
    return lines


def _attribution_lines(row: Mapping[str, Any]) -> list[str]:
    """The lines - up to three - one row's `attribution` and `internal_date` fields mirror to.

    A row the structured form carries **without** these fields gets no line for them: the
    text is a projection and states nothing the mapping does not. Every row `Envelope`
    serialises carries both (their model defaults are the unobserved states), so on the wire
    the lines are always there; the omission exists for mappings built by hand.
    """
    lines: list[str] = []
    attribution = row.get("attribution")
    if isinstance(attribution, Mapping):
        lines.append(
            f"    attribution {attribution.get('provenance')}: "
            f"address {attribution.get('address') or 'none'}, "
            f"stated_addresses {attribution.get('stated_addresses') or 0}"
        )
        display = attribution.get("display_name")
        if display is not None:
            lines.append(f"{DISPLAY_NAME_LINE_PREFIX}{display.get('trust')}) {display.get('text')}")
    if "internal_date_provenance" in row:
        lines.append(
            f"    internal_date {row.get('internal_date') or 'none'} "
            f"({row.get('internal_date_provenance')})"
        )
    return lines


def _residue_lines(structured: Structured) -> list[str]:
    lines: list[str] = []
    for record in structured.get("withheld") or ():
        lines.append(
            f"withheld {record.get('id')} from thread {record.get('thread_id')}: "
            f"cap {record.get('cap')}, reachable with "
            f"{(record.get('affordance') or {}).get('tool')}"
        )
    for group in structured.get("withheld_groups") or ():
        # **Round 29.** The compact half of the omission list, rendered the same way the
        # named half is: what is missing, from where, under which cap, and the call that
        # gets it. The count is the only difference, and it is the point.
        lines.append(
            f"withheld {group.get('message_count')} message(s) from thread "
            f"{group.get('thread_id')}: cap {group.get('cap')}, reachable with "
            f"{(group.get('affordance') or {}).get('tool')}"
        )
    for tail in structured.get("withheld_tail") or ():
        lines.append(
            f"withheld {tail.get('message_count')} message(s) from "
            f"{tail.get('thread_count')} more thread(s): cap {tail.get('cap')}, widen with "
            f"{(tail.get('affordance') or {}).get('tool')}"
        )
    for block in structured.get("not_included_sources") or ():
        # **Round 29.** The reason once, then the threads it applies to. Sixteen sources used
        # to repeat one 253-character sentence sixteen times in this mirror alone.
        sources = block.get("sources") or ()
        lines.append(f"{len(sources)} source(s) not included: {block.get('why')}")
        for split in sources:
            total = split.get("stated_total")
            said = f" ({total} messages)" if total is not None else ""
            lines.append(
                f"  thread {split.get('thread_id')}{said}, reachable with "
                f"{(split.get('affordance') or {}).get('tool')}"
            )
    for continuation in structured.get("continuations") or ():
        # **A remainder, not a narrowing** (navigation redesign, 2026-09-14). What this
        # response started and did not finish, how much is left, and the call that continues
        # it. Rendered with its arguments like the recommended expansion, because it is the
        # call a reader who only sees the text is expected to make next.
        offer = continuation.get("affordance") or {}
        compact = json.dumps(offer.get("args"), separators=(",", ":"))
        where = (
            f" of thread {continuation.get('thread_id')}" if continuation.get("thread_id") else ""
        )
        lines.append(
            f"continue {continuation.get('scope')}{where}: {continuation.get('remaining')} "
            f"remaining, next {offer.get('tool')} {compact}"
        )
    for entry in structured.get("errors") or ():
        lines.append(f"note {entry.get('code')} for {entry.get('scope')}")
    report = structured.get("retrieval_report") or {}
    for entry in report.get("not_tried") or ():
        lines.append(f"rung {entry.get('rung')} not tried: {entry.get('why')}")
    for offer in structured.get("affordances") or ():
        if is_the_recommended_expansion(structured, offer):
            # **The one affordance the mirror renders with its arguments** (round 28): the
            # call that reads the matched rows this response could not carry at the depth
            # asked. Every other affordance is rendered by tool name only, as before, and
            # its arguments live in the structured half; this one is the one a reader who
            # only sees the text is expected to make, so the text has to carry the call.
            compact = json.dumps(offer.get("args"), separators=(",", ":"))
            lines.append(f"next call {offer.get('tool')} {compact}")
            continue
        lines.append(f"next call {offer.get('tool')}")
    return lines


def is_the_recommended_expansion(structured: Structured, offer: Mapping[str, Any]) -> bool:
    """Whether `offer` is the response's recommended expansion, read off the payload alone.

    Identified by what it names rather than by where it sits: a `mailweave_get_messages`
    affordance every one of whose ids is a **matched row present in this response**. A
    withheld record's affordance names an id that is not a row; a collapsed run's names a
    thread or positions; nothing else on the surface names present matched rows by id. So the
    mirror can tell the recommendation apart without a field saying so, and a forged entry
    that merely sat first in the list would not be rendered as one.
    """
    if offer.get("tool") != "mailweave_get_messages":
        return False
    args = offer.get("args") or {}
    ids = args.get("message_ids")
    if not isinstance(ids, list) or not ids:
        return False
    matched = {row.get("id") for _source, row in _rows(structured) if row.get("role") == "matched"}
    return all(message_id in matched for message_id in ids)


class MirrorLineBreak(MailweaveError):
    """A value interpolated into the text mirror spans more than one line.

    **The structural half of R-MCP-016** (round 26). Bounding `AttachmentMetadata`'s four
    fields closes the field the attack came through; this closes the *shape*, for a field
    nobody has written yet. Every line this module composes is a line MailWeave wrote and a
    reader parses as one record - `_read_sources`, `_read_withheld`, `_read_affordances` and
    `_ROW_LINE` all read line by line - so a value carrying a break inside it does not produce
    a longer line, it produces a **second record in this connector's voice**. There is exactly
    one exception, and it is what the fence is for: the block a `content (...)` line opens is
    mail text, is multi-line by nature, and carries the per-response nonce that says where it
    ends.

    Raised rather than escaped, for `FenceViolation`'s reason: MailWeave does not quietly
    rewrite a value and then present the result as the sender's own. `surface/server.py` turns
    it into a declared internal failure rather than a `-32603` with an empty body.
    """


def _every_line_is_one_record(lines: Sequence[str]) -> None:
    """Every composed line is one line, except inside a fenced content block.

    Checked over the *composed* lines rather than at each interpolation site, so it covers
    every field this module renders today and every field added to it later - which is the
    difference between fixing an instance and closing a shape.
    """
    for line in lines:
        if any(line.startswith(prefix) for _kind, prefix in FENCED_LINE_PREFIXES):
            # The multi-line values on this surface, and the only ones that carry their own
            # end marker: `envelope.fence` has already refused text able to close it. The
            # exemption is keyed on the prefixes **this module writes**, at the start of the
            # composed line, so no interpolated value can claim it - a field whose value began
            # `content (` would still sit behind `  message ...` or `    attachment part ...`.
            continue
        # `is_one_line('')` is False - `''.splitlines()` is `[]` - and an empty line is
        # not a forged record, so the emptiness is checked first.
        if line and not is_one_line(line):
            raise MirrorLineBreak(
                "a value interpolated into the text mirror carries a line break, so the "
                "mirror would state a record MailWeave did not write. The value is not "
                "quoted here: it is mail-derived (R-SEC-043's rule), and the structured form "
                "beside this text carries it in the field it belongs to"
            )


def text_of(structured: Structured) -> str:
    """The text mirror of one already-serialised response.

    Takes the mapping rather than the `Envelope`, so this function cannot read anything the
    client is not also receiving. That restriction is the mechanism behind MCP-03, and it is
    why the signature is what it is.
    """
    lines = [*_header_lines(structured), *_source_lines(structured), *_residue_lines(structured)]
    _every_line_is_one_record(lines)
    return "\n".join(lines)


def render(envelope: Envelope) -> Rendered:
    """Serialise once through the chokepoint, then mirror the result into text."""
    structured = envelope.model_dump(mode="json")
    return Rendered(structured=structured, text=text_of(structured))


# --- the mirrors, and their round trip ------------------------------------------------------


@dataclass(frozen=True)
class Mirror:
    """One fact the text is required to carry, with both directions of the mirror."""

    name: str
    extract: Callable[[Structured], object]
    read_back: Callable[[str], object]


_CONTENT_LINE = re.compile(r"^\s*(content|display_name) \((\S+)\) (.*)$")
_ROW_LINE = re.compile(r"^\s*message (\S+) at position \d+: role ")
#: The opening marker `envelope.fence.fence` writes, with the nonce captured. Anchored at the
#: start of the block, which is where `fence` puts it and where mail text cannot reach: the
#: body follows the marker, so the first nonce on a content line is always this response's.
_FENCE_OPEN = re.compile(r"^<<<(mw-[0-9a-f]+) ")


def split_fenced(text: str, nonce: str | None = None) -> tuple[list[str], list[tuple[str, str]]]:
    """`(the lines that are not mail text, [(row id, the fenced content block)])`.

    The content blocks only; a row's fenced display name is kept out of the residue exactly
    as a body is, and is reported by `split_fenced_blocks`, which tags each block with the
    kind of line that opened it.
    """
    residue, blocks = split_fenced_blocks(text, nonce)
    return residue, [(row_id, block) for kind, row_id, block in blocks if kind == "content"]


def split_fenced_blocks(
    text: str, nonce: str | None = None
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """`(the lines that are not mail text, [(kind, row id, the fenced block)])`.

    Every reader below runs on the first half, so a body that contains a line shaped like
    one of this rendering's own lines cannot be read as one.

    **The block closes on the nonce, never on a literal** (round 25, R-MCP-002). Until this
    round the loop ran `while not block.endswith(">>>")`, and `>>>` is three ASCII characters
    any sender can type: a body whose first line ended in `>>>` closed the fence early and
    every line after it was read as one of *this rendering's own* lines. Executed, that put a
    forged `withheld` record, a fabricated source with a false `stated_total`, a fabricated
    message row and a fabricated `next call` into the text a model reads, in the connector's
    voice, chosen by whoever sent the mail. The round-24 test that was supposed to rule this
    out planted a body containing no `>>>` at all.

    The closing sequence is ` {nonce}>>>`, and the nonce is **read off the block's own
    opening marker** rather than taken on trust from the caller. Two properties make that
    sound: `fence()` refuses to fence text that contains the nonce, so the content between
    the markers provably cannot spell the closer; and `fence()` writes the opener at the
    start of the block, so the first marker on a content line is the real one however many
    well-formed-looking markers the body goes on to contain. A `nonce` argument is accepted
    and, when given, must be the one the block opens with - a caller holding the response's
    own `fence_nonce` gets the stronger check for free.

    A content line whose block does not open with a marker is not a fence and is left in the
    residue whole: an unopened block may not swallow the lines beneath it.
    """
    residue: list[str] = []
    blocks: list[tuple[str, str, str]] = []
    current = ""
    raw_lines = text.split("\n")
    index = 0
    while index < len(raw_lines):
        line = raw_lines[index]
        row = _ROW_LINE.match(line)
        if row is not None:
            current = row.group(1)
            residue.append(line)
            index += 1
            continue
        content = _CONTENT_LINE.match(line)
        if content is None:
            residue.append(line)
            index += 1
            continue
        kind = content.group(1)
        block = content.group(3)
        index += 1
        opened = _FENCE_OPEN.match(block)
        if opened is None or (nonce is not None and opened.group(1) != nonce):
            residue.append(line)
            continue
        closer = f" {opened.group(1)}>>>"
        while not block.endswith(closer) and index < len(raw_lines):
            block = f"{block}\n{raw_lines[index]}"
            index += 1
        if not block.endswith(closer):
            # The fence never closed. The block is mail text to the end of the response and
            # is emphatically not rendering: hand it back as one block so no reader below
            # mistakes any of it for a line this connector wrote.
            blocks.append((kind, current, block))
            continue
        blocks.append((kind, current, block))
    return residue, blocks


def _lines(text: str, pattern: str) -> list[re.Match[str]]:
    compiled = re.compile(pattern)
    residue, _ = split_fenced(text)
    return [match for line in residue if (match := compiled.match(line.strip()))]


def _one(text: str, pattern: str) -> re.Match[str] | None:
    found = _lines(text, pattern)
    return found[0] if found else None


def _extract_outcome(structured: Structured) -> object:
    report = structured.get("retrieval_report") or {}
    return (report.get("outcome"), bool(structured.get("partial")), structured.get("truncated_by"))


def _read_outcome(text: str) -> object:
    match = _one(text, r"outcome: (\S+); partial: (\S+); truncated_by: (\S+)$")
    if match is None:
        return None
    return (
        match.group(1),
        _flag(match.group(2)),
        None if match.group(3) == "nothing" else match.group(3),
    )


def _extract_ceiling(structured: Structured) -> object:
    ceiling = structured.get("ceiling") or {}
    return (ceiling.get("applied"), ceiling.get("normal"))


def _read_ceiling(text: str) -> object:
    match = _one(text, r"ceiling: applied (\d+) of normal (\d+) tokens$")
    return None if match is None else (int(match.group(1)), int(match.group(2)))


def _extract_rungs(structured: Structured) -> object:
    return tuple((structured.get("retrieval_report") or {}).get("rungs") or ())


def _read_rungs(text: str) -> object:
    match = _one(text, r"rungs run: (.+)$")
    if match is None or match.group(1) == "none":
        return ()
    return tuple(part.strip() for part in match.group(1).split(","))


def _extract_sources(structured: Structured) -> object:
    return tuple(
        (
            source.get("thread_id"),
            source.get("included"),
            source.get("stated_total"),
            source.get("included_as_stub"),
        )
        for source in structured.get("sources") or ()
    )


def _read_sources(text: str) -> object:
    pattern = (
        r"source thread (\S+): included (\d+) of stated_total (\d+), as_stub (\d+), map_id (\S+)$"
    )
    return tuple(
        (m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)))
        for m in _lines(text, pattern)
    )


def _extract_map_ids(structured: Structured) -> object:
    return tuple(
        (source.get("thread_id"), source.get("map_id"))
        for source in structured.get("sources") or ()
    )


def _read_map_ids(text: str) -> object:
    pattern = r"source thread (\S+): included \d+ of stated_total \d+, as_stub \d+, map_id (\S+)$"
    return tuple(
        (m.group(1), None if m.group(2) == "none" else m.group(2)) for m in _lines(text, pattern)
    )


def _extract_rows(structured: Structured) -> object:
    """Every fact a reader acts on, per row (R-MCP-010).

    Round 24 mirrored `id`, `position`, `role` and `depth` and stopped there, so `reason`,
    `linkage`, `mailbox` and `reply_parent_id` were **rendered and never round-tripped**: a
    rendering that wrote `reason semantic cosine 0.99` on every row - a mechanism this system
    does not have - passed 2,615 tests. `mailbox` was not even rendered, which is OD-6
    criterion 4's Spam/Trash provenance missing from the form a text-only client reads.
    """
    return tuple(
        (
            row.get("id"),
            row.get("position"),
            row.get("role"),
            row.get("depth"),
            row.get("linkage"),
            row.get("reply_parent_id"),
            mailbox_token(row.get("mailbox")),
            row.get("reason"),
        )
        for _source, row in _rows(structured)
    )


def _read_rows(text: str) -> object:
    pattern = (
        r"message (\S+) at position (\d+): role (\S+), depth (\S+), linkage (.+), "
        r"reply_parent (\S+), mailbox (\S+), reason (.*)$"
    )
    return tuple(
        (
            m.group(1),
            int(m.group(2)),
            m.group(3),
            m.group(4),
            m.group(5),
            None if m.group(6) == "none" else m.group(6),
            m.group(7),
            m.group(8),
        )
        for m in _lines(text, pattern)
    )


def _extract_attribution(structured: Structured) -> object:
    """Per row: who the `From` header named, and where that came from (2026-09-22)."""
    return tuple(
        (
            row.get("id"),
            row["attribution"].get("provenance"),
            row["attribution"].get("address"),
            row["attribution"].get("stated_addresses") or 0,
        )
        for _source, row in _rows(structured)
        if isinstance(row.get("attribution"), Mapping)
    )


def _read_attribution(text: str) -> object:
    out: list[tuple[Any, ...]] = []
    current: str | None = None
    line_re = re.compile(r"attribution (\S+): address (\S+), stated_addresses (\d+)$")
    residue, _ = split_fenced(text)
    for raw in residue:
        row = _ROW_LINE.match(raw)
        if row is not None:
            current = row.group(1)
            continue
        match = line_re.match(raw.strip())
        if match is not None and current is not None:
            address = None if match.group(2) == "none" else match.group(2)
            out.append((current, match.group(1), address, int(match.group(3))))
    return tuple(out)


def _extract_display_names(structured: Structured) -> object:
    """Per row with a named sender: the fenced display name, exactly as the structured form
    fences it - the same round trip `content` gets, for the same reason."""
    return tuple(
        (row.get("id"), ((row.get("attribution") or {}).get("display_name") or {}).get("text"))
        for _source, row in _rows(structured)
        if (row.get("attribution") or {}).get("display_name") is not None
    )


def _read_display_names(text: str) -> object:
    _residue, blocks = split_fenced_blocks(text)
    return tuple((row_id, block) for kind, row_id, block in blocks if kind == "display_name")


def _extract_internal_dates(structured: Structured) -> object:
    """Per row: when Gmail received the message, or `None`, and which it is."""
    return tuple(
        (row.get("id"), row.get("internal_date"), row.get("internal_date_provenance"))
        for _source, row in _rows(structured)
        if "internal_date_provenance" in row
    )


def _read_internal_dates(text: str) -> object:
    out: list[tuple[Any, ...]] = []
    current: str | None = None
    line_re = re.compile(r"internal_date (\S+) \((\S+)\)$")
    residue, _ = split_fenced(text)
    for raw in residue:
        row = _ROW_LINE.match(raw)
        if row is not None:
            current = row.group(1)
            continue
        match = line_re.match(raw.strip())
        if match is not None and current is not None:
            stamp = None if match.group(1) == "none" else match.group(1)
            out.append((current, stamp, match.group(2)))
    return tuple(out)


def _extract_withheld(structured: Structured) -> object:
    return tuple(
        (record.get("id"), record.get("thread_id"), record.get("cap"))
        for record in structured.get("withheld") or ()
    )


def _read_withheld(text: str) -> object:
    pattern = r"withheld (\S+) from thread (\S+): cap (\S+),"
    return tuple((m.group(1), m.group(2), m.group(3)) for m in _lines(text, pattern))


def _extract_runs(structured: Structured) -> object:
    return tuple(
        (
            source.get("thread_id"),
            (collapsed.get("positions") or [None, None])[0],
            (collapsed.get("positions") or [None, None])[1],
            collapsed.get("count"),
        )
        for source in structured.get("sources") or ()
        for collapsed in source.get("collapsed_runs") or ()
    )


def _read_runs(text: str) -> object:
    out: list[tuple[Any, ...]] = []
    thread: str | None = None
    source_line = re.compile(r"source thread (\S+): included")
    run_line = re.compile(r"collapsed positions (\d+)-(\d+): (\d+) messages not shown")
    residue, _ = split_fenced(text)
    for raw in residue:
        line = raw.strip()
        header = source_line.match(line)
        if header is not None:
            thread = header.group(1)
            continue
        run = run_line.match(line)
        if run is not None:
            out.append((thread, int(run.group(1)), int(run.group(2)), int(run.group(3))))
    return tuple(out)


def _extract_errors(structured: Structured) -> object:
    return tuple(
        (entry.get("code"), entry.get("scope")) for entry in structured.get("errors") or ()
    )


def _read_errors(text: str) -> object:
    return tuple((m.group(1), m.group(2)) for m in _lines(text, r"note (\S+) for (\S+)$"))


def _extract_affordances(structured: Structured) -> object:
    return tuple(offer.get("tool") for offer in structured.get("affordances") or ())


def _read_affordances(text: str) -> object:
    return tuple(m.group(1) for m in _lines(text, r"next call (\S+)"))


def _extract_content(structured: Structured) -> object:
    return tuple(
        (row.get("id"), (row.get("content") or {}).get("text"))
        for _source, row in _rows(structured)
        if row.get("content") is not None
    )


def _read_content(text: str) -> object:
    _residue, blocks = split_fenced(text)
    return tuple(blocks)


def _extract_attachments(structured: Structured) -> object:
    return tuple(
        (row.get("id"), part.get("part_id"), part.get("filename"), part.get("size"))
        for _source, row in _rows(structured)
        for part in row.get("attachments") or ()
    )


def _read_attachments(text: str) -> object:
    out: list[tuple[Any, ...]] = []
    current: str | None = None
    part_line = re.compile(r"attachment part (\S*): (.+) \((\S+), (\d+) bytes\)$")
    residue, _ = split_fenced(text)
    for raw in residue:
        line = raw.strip()
        row = _ROW_LINE.match(raw)
        if row is not None:
            current = row.group(1)
            continue
        part = part_line.match(line)
        if part is not None and current is not None:
            out.append((current, part.group(1), part.group(2), int(part.group(4))))
    return tuple(out)


def _extract_continuations(structured: Structured) -> object:
    return tuple(
        (one.get("scope"), one.get("remaining"), (one.get("affordance") or {}).get("tool"))
        for one in structured.get("continuations") or ()
    )


def _read_continuations(text: str) -> object:
    return tuple(
        (m.group(1), int(m.group(2)), m.group(3))
        for m in _lines(text, r"continue (\S+)(?: of thread \S+)?: (\d+) remaining, next (\S+) ")
    )


def _extract_clamp(structured: Structured) -> object:
    clamp = (structured.get("budget") or {}).get("clamped")
    return None if clamp is None else (clamp.get("requested"), clamp.get("applied"))


def _read_clamp(text: str) -> object:
    match = _one(text, r"budget clamped: requested (\d+), applied (\d+)$")
    return None if match is None else (int(match.group(1)), int(match.group(2)))


def _extract_not_tried(structured: Structured) -> object:
    report = structured.get("retrieval_report") or {}
    return tuple((entry.get("rung"), entry.get("why")) for entry in report.get("not_tried") or ())


def _read_not_tried(text: str) -> object:
    return tuple((m.group(1), m.group(2)) for m in _lines(text, r"rung (\S+) not tried: (\S+)$"))


#: The facts the text mirror must carry. Adding a field to the response schema does not
#: automatically add a mirror - and that is the honest position rather than a gap, because
#: what MCP-03 requires is that the two forms never *disagree*, which is guaranteed by the
#: projection, plus that the facts a reader acts on are present, which is this table. The
#: table is asserted non-empty and every entry is round-tripped over generated responses.
MIRRORS: Final[tuple[Mirror, ...]] = (
    Mirror("outcome", _extract_outcome, _read_outcome),
    Mirror("ceiling", _extract_ceiling, _read_ceiling),
    Mirror("rungs", _extract_rungs, _read_rungs),
    Mirror("sources", _extract_sources, _read_sources),
    Mirror("map_ids", _extract_map_ids, _read_map_ids),
    Mirror("rows", _extract_rows, _read_rows),
    Mirror("attribution", _extract_attribution, _read_attribution),
    Mirror("display_names", _extract_display_names, _read_display_names),
    Mirror("internal_dates", _extract_internal_dates, _read_internal_dates),
    Mirror("collapsed_runs", _extract_runs, _read_runs),
    Mirror("withheld", _extract_withheld, _read_withheld),
    Mirror("errors", _extract_errors, _read_errors),
    Mirror("not_tried", _extract_not_tried, _read_not_tried),
    Mirror("affordances", _extract_affordances, _read_affordances),
    Mirror("content", _extract_content, _read_content),
    Mirror("attachments", _extract_attachments, _read_attachments),
    Mirror("budget_clamp", _extract_clamp, _read_clamp),
    Mirror("continuations", _extract_continuations, _read_continuations),
)


def fence_disagreements(structured: Structured, text: str) -> list[str]:
    """Every fenced block in the text that is not this response's own fence.

    The one check that reads `fence_nonce` **out of the structured mapping the client also
    receives** rather than off the text (round 25). `split_fenced` derives the nonce from each
    block's own opening marker, which is sound because `fence()` refuses to fence text
    containing the nonce; this is the independent second statement, and it is the one that
    fails if a rendering ever writes a block under a nonce the response did not mint.
    """
    nonce = structured.get("fence_nonce")
    if not isinstance(nonce, str) or not nonce:
        return ["fence_nonce: the structured form carries no nonce to check the text against"]
    out: list[str] = []
    _residue, blocks = split_fenced_blocks(text)
    for kind, row_id, block in blocks:
        if not (block.startswith(f"<<<{nonce} ") and block.endswith(f" {nonce}>>>")):
            out.append(
                f"fence: the {kind} block rendered for row {row_id!r} is not closed by this "
                "response's own nonce"
            )
    return out


def disagreements(structured: Structured, text: str) -> list[str]:
    """Every mirror whose fact the text does not carry back. Empty is the passing state."""
    out: list[str] = list(fence_disagreements(structured, text))
    for mirror in MIRRORS:
        wanted = mirror.extract(structured)
        got = mirror.read_back(text)
        if wanted != got:
            out.append(f"{mirror.name}: structured={wanted!r} text={got!r}")
    return out


def sequence_of(value: object) -> Sequence[object]:
    """Narrow a mirror's value for a caller that wants to count it."""
    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()
