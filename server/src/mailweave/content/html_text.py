"""HTML to visible text, with hidden constructs removed and counted (AD D.4a 5, RR INJ-04).

Parser: `selectolax` (MIT, Lexbor/Modest C parser). Pinned fallback: `lxml.html` (BSD),
constructed with `no_network=True` and `huge_tree=False` so no parse can reach the network
or expand an unbounded entity. `html2text` stays excluded (GPLv3).

Every construct this module drops is counted into a single `hidden_content` reduction, so
INJ-04's `hidden_content_removed` signal is a number with a list of causes rather than a
boolean.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from html import unescape
from typing import Any, Final

from mailweave.constants import HTML_DEPTH_CAP, HTML_SOURCE_CHAR_CAP
from mailweave.content.reductions import HiddenConstruct

#: **Every** Unicode format character, derived from the runtime's own tables (R-SEC-033).
#:
#: Until round 10 this module held two hand-written strings: five zero-width characters and
#: eleven bidi controls, sixteen code points against the **170** Unicode actually defines as
#: category `Cf`. U+061C ARABIC LETTER MARK - the direct sibling of the eleven that *were*
#: listed - survived, so did U+00AD SOFT HYPHEN, and so did the whole U+E0000 tag block,
#: which encodes an invisible ASCII payload: a reviewer spelled "HIDDEN" in it and
#: `strip_invisible_characters` returned `removed_chars=0`.
#:
#: That is the same defect as R-SEC-029 one module over, and it is fixed the same way: ask
#: the runtime instead of transcribing what somebody knew. `unicodedata` is maintained by
#: CPython against the Unicode data files, so the next format character the standard defines
#: is covered here without a code change - which is the property a list can never have.
_FORMAT_CATEGORY: Final = "Cf"

#: Format characters deliberately **kept**. Empty, and empty is a decision rather than an
#: oversight: a `Cf` character has no glyph of its own by definition, so keeping one would be
#: keeping something a reader cannot see, and every removal here is counted and declared as a
#: `hidden_content` reduction rather than applied silently. This is the extension point if a
#: future measurement shows a `Cf` character whose removal changes what a message *says* -
#: the join controls U+200C/U+200D are the likeliest candidates, and they were already being
#: stripped before this round, so removing them is not a change this round introduced.
_KEPT_FORMAT_CHARACTERS: Final[frozenset[str]] = frozenset()

#: Which declared cause a removed format character is filed under, derived from Unicode's
#: `Bidi_Class` rather than from a second hand-list.
#:
#: The nine **explicit directional formatting** classes are the Trojan Source mechanism
#: proper. The three strong classes are how the directional *marks* are spelled: LRM is `L`,
#: RLM is `R`, ALM is `AL` - and U+061C ALM is exactly the sibling the old hand-list missed.
#:
#: Stated rather than glossed: including the strong classes captures **18 code points beyond
#: Unicode's 12-member `Bidi_Control` property** - the Syriac abbreviation mark, two Kaithi
#: number signs and fifteen Egyptian hieroglyph joiners - because `unicodedata` does not
#: expose `Bidi_Control` and transcribing its twelve members is precisely the hand-list this
#: change exists to remove. Those eighteen are stripped either way; the classification only
#: decides which cause their declared removal is filed under, and every one of them does
#: carry a directional class in the bidi algorithm.
_DIRECTIONAL_BIDI_CLASSES: Final[frozenset[str]] = frozenset(
    {"LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI"} | {"L", "R", "AL"}
)

#: Unicode's own name for a format character that is invisible and takes no width: the class
#: holding U+200B, U+200C, U+200D, U+2060 and U+FEFF - the five the old list named - together
#: with U+00AD and the entire tag block, which it did not.
_BOUNDARY_NEUTRAL_BIDI_CLASS: Final = "BN"

_NBSP = "\u00a0"

#: Tags with no closing form; they never open a nesting level.
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "basefont",
        "br",
        "col",
        "embed",
        "frame",
        "hr",
        "img",
        "input",
        "isindex",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_TAG_NAME_RE = re.compile(r"</?\s*([a-zA-Z][a-zA-Z0-9:-]*)")

# Tags whose content is never visible text.
_INVISIBLE_TAGS: dict[str, HiddenConstruct] = {
    "script": HiddenConstruct.SCRIPT,
    "noscript": HiddenConstruct.SCRIPT,
    "template": HiddenConstruct.SCRIPT,
    "style": HiddenConstruct.STYLE,
    "head": HiddenConstruct.HEAD,
}
_COMMENT_TAG = "_comment"

_DISPLAY_NONE_RE = re.compile(r"display\s*:\s*none", re.I)
_VISIBILITY_HIDDEN_RE = re.compile(r"visibility\s*:\s*hidden", re.I)
_FONT_SIZE_ZERO_RE = re.compile(r"font-size\s*:\s*0(?:\.0+)?\s*(?:px|pt|em|rem|%)?\s*(?:;|$)", re.I)
_SIZE_RE = re.compile(r"(?:^|;)\s*(width|height)\s*:\s*(\d+(?:\.\d+)?)\s*px", re.I)
_COLOUR_RE = re.compile(r"(?:^|;)\s*(background-color|background|color)\s*:\s*([^;]+)", re.I)

_NAMED_COLOURS = {
    "white": "#ffffff",
    "black": "#000000",
    "transparent": "transparent",
}


class HtmlParserName(StrEnum):
    SELECTOLAX = "selectolax"
    LXML = "lxml.html"


@dataclass(frozen=True)
class HtmlExtraction:
    """Visible text plus the accounting the reduction records need."""

    text: str
    parser: str
    hidden_removed_chars: int
    constructs: tuple[HiddenConstruct, ...]
    source_chars: int
    nodes_removed: int = 0
    #: Characters of source dropped by `HTML_SOURCE_CHAR_CAP`, before any parse.
    size_capped_chars: int = 0
    #: Characters of *markup* removed by `HTML_DEPTH_CAP`. Text inside it is kept.
    depth_capped_chars: int = 0
    #: Tags flattened away by the depth cap; 0 when the cap did not bite.
    depth_capped_tags: int = 0
    #: Deepest nesting seen in the source, before flattening. Reported, not a claim.
    max_depth_seen: int = 0
    #: Source characters that were visible text and did not survive the parse. Non-zero
    #: only when a parser returned nothing from a document that contained something -
    #: the silent-drop case R-SEC-002 found in the lxml fallback.
    lost_text_chars: int = 0


@dataclass(frozen=True)
class BoundedHtml:
    """`html` reduced to something a parser can walk in bounded time, with the counts."""

    html: str
    size_capped_chars: int
    depth_capped_chars: int
    depth_capped_tags: int
    max_depth_seen: int


def _tag_spans(html: str) -> Iterator[tuple[int, int, str | None, bool, bool]]:
    """Yield `(start, end, tag_name, is_close, is_self_closing)` for every `<...>` token.

    This is a scanner, not a parser: it is deliberately cruder than the real parsers that
    run afterwards, because its only job is to bound what they are handed. Comments,
    doctypes and processing instructions are yielded with `tag_name=None` and never change
    the nesting level. An attribute value containing a literal `>` ends the token early
    here; the consequence is a slightly conservative depth estimate, never an unbounded
    one.
    """
    index = 0
    length = len(html)
    while index < length:
        start = html.find("<", index)
        if start == -1:
            return
        if html.startswith("<!--", start):
            end = html.find("-->", start + 4)
            end = length if end == -1 else end + 3
            yield start, end, None, False, False
            index = end
            continue
        end = html.find(">", start + 1)
        if end == -1:
            return
        end += 1
        token = html[start:end]
        match = _TAG_NAME_RE.match(token)
        if match is None:  # `<!doctype ...>`, `<?xml ...?>`, or a stray `<`
            yield start, end, None, False, False
        else:
            yield (
                start,
                end,
                match.group(1).lower(),
                token.startswith("</"),
                token.rstrip().endswith("/>"),
            )
        index = end


def bound_markup(
    html: str,
    *,
    max_depth: int = HTML_DEPTH_CAP,
    max_chars: int = HTML_SOURCE_CHAR_CAP,
) -> BoundedHtml:
    """Bound a body's size and nesting *before* it reaches a DOM parser (R-SEC-002).

    Two bounds, in order:

      * source longer than `max_chars` is truncated - the only bound here that can lose
        text, and it is counted;
      * markup nested deeper than `max_depth` is flattened away. The tags go, the text
        inside them stays, so the depth bound removes markup and not content.

    Both counts are returned so the caller can declare them. Nothing is dropped quietly:
    the pipeline turns each non-zero count into a `Reduction`.
    """
    size_capped = 0
    if len(html) > max_chars:
        kept = html[:max_chars]
        # Do not hand a parser half a tag: cut back to the last complete token.
        opened = kept.rfind("<")
        if opened > kept.rfind(">"):
            kept = kept[:opened]
        size_capped = len(html) - len(kept)
        html = kept

    pieces: list[str] = []
    cursor = 0
    depth = 0
    suppressed = 0
    max_seen = 0
    removed_chars = 0
    removed_tags = 0
    for start, end, name, is_close, self_closing in _tag_spans(html):
        pieces.append(html[cursor:start])
        cursor = end
        token = html[start:end]
        if name is None or self_closing or name in _VOID_TAGS:
            pieces.append(token)
            continue
        if is_close:
            if suppressed:
                suppressed -= 1
                removed_chars += len(token)
                removed_tags += 1
            else:
                pieces.append(token)
                depth = max(0, depth - 1)
            continue
        max_seen = max(max_seen, depth + suppressed + 1)
        if depth >= max_depth:
            suppressed += 1
            removed_chars += len(token)
            removed_tags += 1
        else:
            pieces.append(token)
            depth += 1
    pieces.append(html[cursor:])
    return BoundedHtml(
        html="".join(pieces),
        size_capped_chars=size_capped,
        depth_capped_chars=removed_chars,
        depth_capped_tags=removed_tags,
        max_depth_seen=max_seen,
    )


def _canonical_colour(value: str) -> str | None:
    token = value.strip().lower().rstrip(";").strip()
    if token in _NAMED_COLOURS:
        return _NAMED_COLOURS[token]
    match = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", token)
    if match:
        digits = match.group(1)
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        return f"#{digits}"
    match = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,[^)]*)?\)", token)
    if match:
        r, g, b = (int(match.group(i)) for i in (1, 2, 3))
        return f"#{r:02x}{g:02x}{b:02x}"
    return None


def _style_constructs(style: str) -> list[HiddenConstruct]:
    found: list[HiddenConstruct] = []
    if _DISPLAY_NONE_RE.search(style):
        found.append(HiddenConstruct.DISPLAY_NONE)
    if _VISIBILITY_HIDDEN_RE.search(style):
        found.append(HiddenConstruct.VISIBILITY_HIDDEN)
    if _FONT_SIZE_ZERO_RE.search(style):
        found.append(HiddenConstruct.FONT_SIZE_ZERO)
    for _, size in _SIZE_RE.findall(style):
        if float(size) <= 1.0:
            found.append(HiddenConstruct.TINY_BOX)
            break
    colours: dict[str, str] = {}
    for prop, value in _COLOUR_RE.findall(style):
        canonical = _canonical_colour(value)
        if canonical:
            colours["background" if prop.lower().startswith("background") else "color"] = canonical
    if (
        "color" in colours
        and "background" in colours
        and colours["color"] == colours["background"]
        and colours["color"] != "transparent"
    ):
        found.append(HiddenConstruct.COLOUR_EQUALS_BACKGROUND)
    return found


def _attribute_constructs(attrs: dict[str, str | None]) -> list[HiddenConstruct]:
    found: list[HiddenConstruct] = []
    if "hidden" in attrs:
        found.append(HiddenConstruct.DISPLAY_NONE)
    for dimension in ("width", "height"):
        raw = attrs.get(dimension)
        if raw is None:
            continue
        try:
            if float(str(raw).strip().rstrip("px")) <= 1.0:
                found.append(HiddenConstruct.TINY_BOX)
                break
        except ValueError:
            continue
    return found


@cache
def invisible_character_patterns() -> tuple[tuple[HiddenConstruct, re.Pattern[str]], ...]:
    """One pattern per declared cause, built by walking Unicode's own tables.

    Computed once per process and cached, not at import: the walk over the whole code point
    space costs about a tenth of a second, which is a cost worth paying once by the first
    message processed and not worth putting on every `import mailweave`.

    The membership rule is the general category. The split into causes is `Bidi_Class`. Both
    come out of `unicodedata`, so neither is a snapshot of what anybody knew: this is the
    same move `_is_one_line` made when it stopped scanning for `\n`/`\r` and started asking
    `str.splitlines()` (R-SEC-029), applied to the defect R-SEC-033 found in this module.
    """
    buckets: dict[HiddenConstruct, list[str]] = {
        HiddenConstruct.ZERO_WIDTH: [],
        HiddenConstruct.BIDI_OVERRIDE: [],
        HiddenConstruct.INVISIBLE_FORMAT: [],
    }
    for code_point in range(sys.maxunicode + 1):
        character = chr(code_point)
        if unicodedata.category(character) != _FORMAT_CATEGORY:
            continue
        if character in _KEPT_FORMAT_CHARACTERS:
            continue
        bidi_class = unicodedata.bidirectional(character)
        if bidi_class in _DIRECTIONAL_BIDI_CLASSES:
            buckets[HiddenConstruct.BIDI_OVERRIDE].append(character)
        elif bidi_class == _BOUNDARY_NEUTRAL_BIDI_CLASS:
            buckets[HiddenConstruct.ZERO_WIDTH].append(character)
        else:
            buckets[HiddenConstruct.INVISIBLE_FORMAT].append(character)
    return tuple(
        (construct, re.compile(f"[{''.join(re.escape(c) for c in characters)}]"))
        for construct, characters in buckets.items()
        if characters
    )


@dataclass(frozen=True)
class InvisibleStrip:
    """What `strip_invisible_characters` removed, per construct."""

    text: str
    zero_width_removed: int
    bidi_removed: int
    format_removed: int

    @property
    def constructs(self) -> tuple[HiddenConstruct, ...]:
        found: list[HiddenConstruct] = []
        if self.zero_width_removed:
            found.append(HiddenConstruct.ZERO_WIDTH)
        if self.bidi_removed:
            found.append(HiddenConstruct.BIDI_OVERRIDE)
        if self.format_removed:
            found.append(HiddenConstruct.INVISIBLE_FORMAT)
        return tuple(found)

    @property
    def removed_chars(self) -> int:
        return self.zero_width_removed + self.bidi_removed + self.format_removed


def strip_invisible_characters(text: str) -> InvisibleStrip:
    """Remove every Unicode format character, counting each declared cause separately.

    Used by both body paths and by the header path: the HTML extractor calls it on the text
    it recovered, the pipeline calls it on `text/plain` bodies, which never pass through a
    parser (R-SEC-005: an unstripped RLO reached `body_clean` byte-for-byte before this), and
    `headers.py`/`mime.py` call it on Subject, From and attachment filenames (R-SEC-011).

    **Scope, stated rather than implied.** This removes characters that render as nothing.
    It does not make a message safe to trust, and it is not a homoglyph or confusable
    defence: `раypal` spelled with Cyrillic letters is *visible* text and passes through here
    untouched, as it should - INJ-04's mechanism is fencing and provenance, and this function
    is the narrower claim that what a reader sees is what the bytes say.
    """
    counts = dict.fromkeys(HiddenConstruct, 0)
    stripped = text
    for construct, pattern in invisible_character_patterns():
        shortened = pattern.sub("", stripped)
        counts[construct] = len(stripped) - len(shortened)
        stripped = shortened
    return InvisibleStrip(
        text=stripped.replace(_NBSP, " "),
        zero_width_removed=counts[HiddenConstruct.ZERO_WIDTH],
        bidi_removed=counts[HiddenConstruct.BIDI_OVERRIDE],
        format_removed=counts[HiddenConstruct.INVISIBLE_FORMAT],
    )


def _extract_selectolax(html: str) -> tuple[str, int, list[HiddenConstruct], int]:
    from selectolax.parser import HTMLParser  # local import keeps the fallback path honest

    tree = HTMLParser(html)
    removed_chars = 0
    constructs: list[HiddenConstruct] = []
    doomed: list[tuple[Any, list[HiddenConstruct]]] = []

    for node in tree.root.traverse(include_text=False) if tree.root else []:
        tag = node.tag
        causes: list[HiddenConstruct] = []
        if tag == _COMMENT_TAG:
            causes.append(HiddenConstruct.COMMENT)
        elif tag in _INVISIBLE_TAGS:
            causes.append(_INVISIBLE_TAGS[tag])
        else:
            attrs = dict(node.attributes)
            style = attrs.get("style") or ""
            causes.extend(_style_constructs(style))
            causes.extend(_attribute_constructs(attrs))
        if causes:
            doomed.append((node, causes))

    nodes_removed = 0
    for node, causes in doomed:
        text = ""
        try:
            if node.tag == _COMMENT_TAG:
                raw = node.html or ""
                text = raw.removeprefix("<!--").removesuffix("-->")
            else:
                text = node.text(deep=True) or ""
        except (AttributeError, ValueError):  # pragma: no cover - defensive
            text = ""
        # A construct that removed nothing readable is not hidden content: an HTML parser
        # inserts an empty <head> into every document, and declaring that as concealment
        # would make the INJ-04 signal fire on every message and mean nothing.
        if text.strip():
            removed_chars += len(text.strip())
            constructs.extend(causes)
            nodes_removed += 1
        try:
            node.decompose()
        except (AttributeError, ValueError):  # pragma: no cover - already detached
            continue

    body = tree.body if tree.body is not None else tree.root
    text = body.text(separator="\n", deep=True) if body is not None else ""
    return text, removed_chars, constructs, nodes_removed


def _extract_lxml(html: str) -> tuple[str, int, list[HiddenConstruct], int]:
    from lxml import etree
    from lxml import html as lxml_html

    # `no_network=True` forbids any external fetch during parse; `huge_tree=False` keeps
    # the entity/expansion limits on. lxml's HTML parser does not resolve external
    # entities at all (that is an XML parser feature), so there is no DTD to disable.
    parser = lxml_html.HTMLParser(no_network=True, huge_tree=False, recover=True)
    try:
        tree = lxml_html.document_fromstring(html or "<html></html>", parser=parser)
    except (etree.ParserError, etree.XMLSyntaxError):
        return "", 0, [], 0

    removed_chars = 0
    constructs: list[HiddenConstruct] = []
    doomed: list[tuple[Any, list[HiddenConstruct]]] = []

    for node in tree.iter():
        tag = node.tag
        causes: list[HiddenConstruct] = []
        if not isinstance(tag, str):  # comments and processing instructions
            causes.append(HiddenConstruct.COMMENT)
        elif tag in _INVISIBLE_TAGS:
            causes.append(_INVISIBLE_TAGS[tag])
        else:
            try:
                attrs = dict(node.attrib)
            except ValueError:
                # lxml refuses to hand back attributes whose name or value contains a
                # control character, raising `ValueError` from inside `dict()`. Found by
                # the round-2 property test over malformed markup; a crafted body used to
                # crash the fallback parser with an untyped exception. The node's own
                # attributes cannot be inspected at all in this case, so style-based
                # hiding on *that node* is not detected - stated here rather than left
                # for a reader to infer.
                attrs = {}
            causes.extend(_style_constructs(attrs.get("style", "")))
            causes.extend(_attribute_constructs(attrs))
        if causes:
            doomed.append((node, causes))

    nodes_removed = 0
    for node, causes in doomed:
        # For a comment or processing instruction the node's own text is the payload.
        text = node.text_content() if isinstance(node.tag, str) else (node.text or "")
        if str(text).strip():
            removed_chars += len(str(text).strip())
            constructs.extend(causes)
            nodes_removed += 1
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)

    return tree.text_content(), removed_chars, constructs, nodes_removed


def html_to_text(html: str, parser: HtmlParserName = HtmlParserName.SELECTOLAX) -> HtmlExtraction:
    """Convert an HTML body to visible text.

    Neither parser performs I/O: selectolax has no network code at all, and the lxml
    fallback is constructed with `no_network=True`. INJ-04's
    zero-network condition is asserted by running the whole pipeline with sockets
    disabled, which is the default for this repo's unit suite.

    The body is bounded before it reaches either parser (`bound_markup`), because parse
    cost grows with nesting depth and because lxml discards content below its own
    internal depth limit without saying so. Whatever the bounds removed is returned in
    the extraction's counts for the pipeline to declare.

    If a parse consumes visible text and produces none - the silent-loss case R-SEC-002
    found in the lxml fallback on deeply nested input, and which malformed markup can
    still cause in both parsers - the extraction carries `lost_text_chars`, and the
    pipeline turns it into an `html_parse_lost_text` reduction. An empty body that a
    removed hidden construct explains is not a loss and is not counted as one.
    """
    source_chars = len(html)
    bounded = bound_markup(html)
    if parser is HtmlParserName.SELECTOLAX:
        text, removed, constructs, nodes = _extract_selectolax(bounded.html)
        parser_name = HtmlParserName.SELECTOLAX
    else:
        text, removed, constructs, nodes = _extract_lxml(bounded.html)
        parser_name = HtmlParserName.LXML

    invisible = strip_invisible_characters(text)
    text = invisible.text
    if invisible.removed_chars:
        removed += invisible.removed_chars
        nodes += 1
        constructs.extend(invisible.constructs)

    # A parser that consumed visible text and produced none has lost content. Nothing in
    # `ReductionKind` used to be able to say so, so the loss was simply absent from the
    # accounting (R-SEC-002). It is now counted, and the pipeline declares it. Emptiness
    # that a removed hidden construct explains is not a loss and is not counted here.
    lost = 0
    if not text.strip() and removed == 0:
        lost = len(_visible_text_estimate(bounded.html))

    ordered = tuple(dict.fromkeys(constructs))
    return HtmlExtraction(
        text=text,
        parser=parser_version(parser_name),
        hidden_removed_chars=removed,
        constructs=ordered,
        source_chars=source_chars,
        nodes_removed=nodes,
        lost_text_chars=lost,
        size_capped_chars=bounded.size_capped_chars,
        depth_capped_chars=bounded.depth_capped_chars,
        depth_capped_tags=bounded.depth_capped_tags,
        max_depth_seen=bounded.max_depth_seen,
    )


def _visible_text_estimate(html: str) -> str:
    """The text outside tags, ignoring the tags that hide their own content.

    Used only to tell "this document had nothing to show" apart from "the parser lost
    it". Crude on purpose - it is a witness, not an extractor. Entities are unescaped
    before the test, so a body whose whole content is `&nbsp;` counts as empty rather
    than as text a parser lost.
    """
    pieces: list[str] = []
    cursor = 0
    skip_until: str | None = None
    for start, end, name, is_close, _self_closing in _tag_spans(html):
        if skip_until is None:
            pieces.append(html[cursor:start])
        elif name == skip_until and is_close:
            skip_until = None
        cursor = end
        if skip_until is None and name in _INVISIBLE_TAGS and not is_close:
            skip_until = name
    if skip_until is None:
        pieces.append(html[cursor:])
    return unescape("".join(pieces)).strip()


def parser_version(parser: HtmlParserName) -> str:
    """`name@version` for the reduction record. The version is read, never hardcoded."""
    from importlib.metadata import PackageNotFoundError, version

    distribution = "selectolax" if parser is HtmlParserName.SELECTOLAX else "lxml"
    try:
        return f"{parser.value}@{version(distribution)}"
    except PackageNotFoundError:  # pragma: no cover - only if installed from source
        return f"{parser.value}@unknown"
