"""The gates a source-stated assertion has to pass, computed rather than declared.

`contracts/edges.py` refuses a `obs.said.*` edge that arrives without a
`StatedAssertionCheck`, and refuses a check whose parts disagree with each other. That stops
a *malformed* claim. It does not stop a builder that fills the check in optimistically, and
"the model would have caught it" is not true of a model whose inputs the same code writes.

This module is where the four gates are actually decided, from the message text and the
candidate set:

1. **the span matches** - the quotation is the source content at those offsets, character
   for character (`match_span`);
2. **the target is identified** - the referring words pick out exactly one candidate, and a
   phrase that could only be unique because the candidate set is small picks out none
   (`resolve_target`);
3. **the clause is clear** - no negation, quotation, hypothetical, conditional, hedge or
   interrogative cue governs the span (`clear_clause`);
4. **the asserter is named** - the node whose content carries the span, which the caller
   supplies and `StatedAssertionCheck` checks against the edge's endpoints.

Every refusal is a `Refused` with the gate that refused and what it saw, so a caller can do
the honest thing with it: emit an inferred relation carrying the ambiguity, or emit nothing.

**Scope, stated rather than implied.** The cue sets are English. `content/quotes.py`
recognises client attribution lines in ten locales, and a negation recogniser for ten
locales is not a claim this module can support, so `clear_clause` refuses any language but
`en` outright rather than clearing a clause it cannot read. A non-English body can still
produce inferred relations; it produces no source-stated ones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from mailweave.content.annotate import AnnotatedBody, AnnotatedSpan, SpanClass
from orivra.contracts.edges import ClauseClearance, StatedAssertionCheck, TargetResolution
from orivra.contracts.nodes import Span

#: The only language whose cues this module knows. See the module docstring.
SUPPORTED_LANGUAGE: Final[str] = "en"

#: Span classes a source-stated assertion may rest on. **`ORIGINAL` only.**
#:
#: `QUOTED` and `FORWARDED` are somebody else's words, and attributing them to this message's
#: sender is the quotation failure of §4.5 rule 3. `SIGNATURE` is boilerplate. `UNCERTAIN` is
#: A7's honest "the classification is undetermined here", and asserting on undetermined text
#: is asserting on text that may be quoted - the gate must fail closed on it.
ASSERTABLE_CLASSES: Final[frozenset[SpanClass]] = frozenset({SpanClass.ORIGINAL})

#: Negation cues. Matched as whole words on the folded clause.
#:
#: `n't` is handled separately by the pattern below rather than listed per verb, so a
#: contraction this list never anticipated ("shan't") is still caught.
NEGATION_CUES: Final[tuple[str, ...]] = (
    "not",
    "no",
    "never",
    "nor",
    "neither",
    "none",
    "nothing",
    "nobody",
    "nowhere",
    "cannot",
    "without",
    "rather than",
    "instead of",
    "no longer",
    "decline",
    "declines",
    "declined",
)

#: Hypothetical, conditional and modal cues.
#:
#: `would`, `could`, `might` and `may` are here because "we would withdraw" is a statement
#: about a world that does not obtain. `should` is here twice over: modal in "we should
#: withdraw", interrogative in "should we withdraw?".
HYPOTHETICAL_CUES: Final[tuple[str, ...]] = (
    "if",
    "unless",
    "would",
    "could",
    "should",
    "might",
    "may",
    "were to",
    "in case",
    "in the event",
    "provided that",
    "assuming",
    "suppose",
    "hypothetically",
    "propose",
    "proposes",
    "proposed",
    "proposal",
    "plan to",
    "planning to",
    "intend to",
    "going to",
)

#: Hedges. A source that hedged its own claim did not assert it, and reporting "the source
#: states X" for "this apparently supersedes X" overstates by exactly the hedge.
HEDGE_CUES: Final[tuple[str, ...]] = (
    "perhaps",
    "maybe",
    "possibly",
    "probably",
    "presumably",
    "apparently",
    "seems",
    "seem",
    "appears",
    "appear",
    "i think",
    "i believe",
    "arguably",
    "effectively",
    "more or less",
)

#: Clause-initial words that make a clause a question even without a question mark.
INTERROGATIVE_OPENERS: Final[tuple[str, ...]] = (
    "should",
    "shall",
    "do",
    "does",
    "did",
    "is",
    "are",
    "was",
    "were",
    "can",
    "could",
    "would",
    "will",
    "who",
    "what",
    "which",
    "when",
    "where",
    "why",
    "how",
)

#: Referring expressions that point without identifying, as whole phrases.
#:
#: A fast path only. The rule that does the work is `_distinguishing` below, because a list
#: of phrases catches "the earlier version" and misses "the earlier pricing version" - and a
#: review found exactly that: the list fired only when the *entire* referring text equalled
#: one of these, so every other phrase fell through to the matcher.
DEICTIC_PHRASES: Final[tuple[str, ...]] = (
    "it",
    "this",
    "that",
    "the above",
    "the below",
    "the former",
    "the one before",
)

#: Nouns and modifiers that point at a position rather than at a thing.
#:
#: A referring phrase built only from these identifies nothing, whatever the candidate count:
#: "the earlier version", "the previous draft", "the last document" are each satisfied by
#: whichever candidate happens to be in scope, which is the scope identifying the target
#: rather than the sentence. This is `DEICTIC_PHRASES` generalised from phrases to tokens,
#: and it is the mechanism `considered` was kept to expose the absence of.
GENERIC_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "above",
        "attachment",
        "below",
        "copy",
        "document",
        "draft",
        "earlier",
        "email",
        "file",
        "former",
        "item",
        "last",
        "later",
        "mail",
        "message",
        "note",
        "old",
        "older",
        "one",
        "preceding",
        "previous",
        "prior",
        "recent",
        "revision",
        "thing",
        "thread",
        "update",
        "version",
    }
)

#: Words carrying no identifying force, removed before a referring phrase is compared.
_STOPWORDS: Final[frozenset[str]] = frozenset(
    {"the", "a", "an", "of", "our", "your", "my", "their", "its", "this", "that", "those"}
)

_WORD = re.compile(r"[a-z0-9']+")
_CONTRACTED_NOT = re.compile(r"\b\w+n't\b")
_SENTENCE_END = re.compile(r"[.!?;]")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Refused:
    """A gate said no, and what it saw. The caller's honest options are an inferred relation
    carrying this, or no edge at all."""

    gate: str
    why: str
    cues: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()

    @property
    def cleared(self) -> bool:
        return False


@dataclass(frozen=True)
class Cleared:
    """A gate said yes, carrying the evidence the contract will want."""

    clearance: ClauseClearance

    @property
    def cleared(self) -> bool:
        return True


def _fold(text: str) -> str:
    return _WHITESPACE.sub(" ", text.casefold()).strip()


def _words(text: str) -> list[str]:
    return _WORD.findall(text.casefold())


def _phrase_hits(folded: str, cues: tuple[str, ...], label: str) -> list[str]:
    """Every cue in `cues` present in `folded` as a whole word or whole phrase."""
    found: list[str] = []
    for cue in cues:
        pattern = r"\b" + re.escape(cue) + r"\b"
        if re.search(pattern, folded):
            found.append(f"{label}:{cue}")
    return found


def match_span(
    body: AnnotatedBody, start: int, end: int, quoted: str, *, node_id: str
) -> Span | Refused:
    """Gate 1: the quotation is the source content at those offsets, character for character.

    Offsets are half-open `[start, end)` over `AnnotatedBody.text`, which is
    `content/annotate.py`'s own convention - the two are compared directly and an off-by-one
    at the boundary would be a quotation that silently shifted by a character.
    """
    if start < 0 or end > len(body.text) or end <= start:
        return Refused(
            gate="span",
            why=(
                f"offsets [{start}, {end}) do not name a run of characters inside a "
                f"{len(body.text)}-character body"
            ),
        )
    actual = body.text[start:end]
    if actual != quoted:
        return Refused(
            gate="span",
            why=(
                "the quotation is not the source content at those offsets; a span that does "
                "not string-match its source is an extraction nobody can check"
            ),
        )
    return Span(node_id=node_id, start=start, end=end, text=quoted)


def _spans_over(body: AnnotatedBody, start: int, end: int) -> list[AnnotatedSpan]:
    """Every classified span the candidate offsets touch, in body order."""
    return [span for span in body.spans if span.start < end and span.end > start]


def clause_of(body: AnnotatedBody, start: int, end: int) -> tuple[int, int]:
    """The sentence containing `[start, end)`, as offsets into `body.text`.

    Sentences are bounded by `.`, `!`, `?`, `;` and newlines. **A terminator inside the span
    never splits it**: the span is the unit being asserted, and a clause that stops in the
    middle of it is a clause that could clear on half the sentence.

    Residue, stated rather than hidden: an abbreviation ("Dr.", "e.g.") splits a sentence
    early, which makes the scanned clause *smaller* than the real one and could in principle
    drop a cue that governs the span. The alternative - taking the whole line - makes false
    refusals routine on long paragraphs. The abbreviation case is covered because the
    terminator that matters for cue-bearing prose is almost always a real one, and because
    the interrogative gate also reads the whole line's final character.
    """
    left = 0
    for match in _SENTENCE_END.finditer(body.text, 0, start):
        left = match.end()
    for index in range(start - 1, -1, -1):
        if body.text[index] == "\n":
            left = max(left, index + 1)
            break
    right = len(body.text)
    for match in _SENTENCE_END.finditer(body.text, end):
        right = match.end()
        break
    newline = body.text.find("\n", end)
    if newline != -1:
        right = min(right, newline)
    return left, max(right, end)


def clear_clause(body: AnnotatedBody, start: int, end: int, *, language: str) -> Cleared | Refused:
    """Gates 2 and 3: the span is original content, and its clause carries no cue.

    Four sentences must each fail here, and each does for its own reason:

    * "we are **not** withdrawing the approval" - `NEGATION_CUES`;
    * a quoted block reproducing someone else's withdrawal - the span class gate, because
      `content/quotes.py` already classified that region as `QUOTED`;
    * "**if** certification fails we **would** withdraw" - `HYPOTHETICAL_CUES`;
    * "**should we** withdraw?" - `INTERROGATIVE_OPENERS` and the question mark.
    """
    if language != SUPPORTED_LANGUAGE:
        return Refused(
            gate="language",
            why=(
                f"the cue sets are {SUPPORTED_LANGUAGE!r} and this clause is {language!r}; a "
                "clause in a language the recogniser does not read would clear because no "
                "cue was recognised rather than because none is there"
            ),
        )
    overlapped = _spans_over(body, start, end)
    if not overlapped:
        return Refused(
            gate="quotation",
            why="the span lies outside every classified region of the body",
        )
    disallowed = sorted(
        {
            span.classification.value
            for span in overlapped
            if span.classification not in ASSERTABLE_CLASSES
        }
    )
    if disallowed:
        return Refused(
            gate="quotation",
            why=(
                f"the span overlaps {', '.join(disallowed)} content; those are somebody "
                "else's words, boilerplate, or a region whose classification is undetermined, "
                "and attributing any of them to this message's sender is the quotation "
                "failure the rule exists to catch"
            ),
            cues=tuple(f"span_class:{name}" for name in disallowed),
        )
    left, right = clause_of(body, start, end)
    clause = body.text[left:right]
    folded = _fold(clause)
    cues: list[str] = []
    cues += _phrase_hits(folded, NEGATION_CUES, "negation")
    if _CONTRACTED_NOT.search(folded):
        cues.append("negation:n't")
    cues += _phrase_hits(folded, HYPOTHETICAL_CUES, "hypothetical")
    cues += _phrase_hits(folded, HEDGE_CUES, "hedge")
    line_end = body.text.find("\n", end)
    line = body.text[left : line_end if line_end != -1 else len(body.text)].rstrip()
    if clause.rstrip().endswith("?") or line.endswith("?"):
        cues.append("interrogative:?")
    opening = _words(clause)
    if opening and opening[0] in INTERROGATIVE_OPENERS:
        cues.append(f"interrogative:{opening[0]}")
    if cues:
        return Refused(
            gate="clause",
            why=(
                "the clause governing the span carries a negation, quotation, hypothetical "
                "or interrogative cue, so the source did not assert this relationship"
            ),
            cues=tuple(sorted(set(cues))),
        )
    signals = tuple(sorted({span.signal for span in overlapped}))
    return Cleared(
        ClauseClearance(
            clause=clause.strip() or clause,
            language=language,
            cues_found=(),
            span_class_signals=signals,
        )
    )


@dataclass(frozen=True)
class Candidate:
    """One node the referring words could be pointing at, with its identifying surface forms.

    `keys` are what a writer would use to name it: the subject line, a document title, a
    date spelling, an RFC-5322 message id. Display names of people are deliberately not
    keys - `structure/participants.py`'s rule that identity is an address and never a
    display name applies here too.
    """

    node_id: str
    keys: tuple[str, ...]

    def matches(self, folded_reference: str) -> bool:
        """Whether this candidate's identifying text **accounts for every word** the
        reference used.

        One direction, and it is the direction a review had to find. The rule was a
        *bidirectional* subset - a match when the key's words were inside the reference or
        the reference's words were inside the key - and the first half of that is a hole: a
        candidate whose only key is a common word ("Draft", "Pricing") is a subset of every
        phrase containing it, so "the July 3 pricing draft" matched a document called
        "Pricing", and when that was the only candidate the resolution was reported as
        *unique*. An observed `supersedes_stated` edge was constructible against a document
        the sentence never named.

        So: the reference's content words must be a subset of the key's. A reference
        carrying distinguishing content the candidate cannot account for - "July", "3" -
        does not name that candidate, whatever else it shares. The reverse
        under-specification is still a match, and legitimately: "the pricing draft" does
        identify the one pricing draft in scope. What it identifies is relative to the
        candidate set the caller supplied, which is a fact about the caller and is why
        `considered` is published beside the resolution rather than discarded.
        """
        reference_words = {word for word in _words(folded_reference) if word not in _STOPWORDS}
        if not reference_words:
            return False
        for key in self.keys:
            key_words = {word for word in _words(key) if word not in _STOPWORDS}
            if key_words and reference_words <= key_words:
                return True
        return False


def _distinguishing(folded_reference: str) -> bool:
    """Whether a referring phrase says anything that could pick one thing out.

    A phrase built only from stopwords and `GENERIC_TOKENS` - "the earlier version", "the
    previous draft" - names a position in a sequence, not a document. It is satisfied by
    whichever candidate is in scope, so a resolver that accepted it would report a unique
    resolution whose uniqueness came from the size of the candidate set.
    """
    return any(
        word not in _STOPWORDS and word not in GENERIC_TOKENS for word in _words(folded_reference)
    )


def resolve_target(referring_text: str, candidates: tuple[Candidate, ...]) -> TargetResolution:
    """Gate 2: which node the referring words identify, or none.

    Two ways to fail, and they are different failures:

    * **Nothing distinguishing was said.** "This supersedes the earlier version" names no
      node; it points. A phrase built only from stopwords and `GENERIC_TOKENS` never
      resolves, *whatever the candidate count*, because a phrase that is unique only when one
      candidate is in scope was made unique by the scope and not by the sentence. This is the
      rule `considered` exists to expose - a token rule rather than a phrase list, because a
      phrase list fired on "the earlier version" and not on "the earlier pricing version".
    * **Several candidates match.** Three earlier versions, one phrase: an observed edge
      would have to pick one, and picking is inference wearing an observation's label.

    Both come back as a `TargetResolution` with `resolved_to=None` and the full candidate
    set, which is exactly what an `inf.potentially_supersedes` edge needs to record the
    ambiguity honestly.
    """
    considered = tuple(candidate.node_id for candidate in candidates)
    folded = _fold(referring_text).strip(" .,;:\"'")
    stripped = folded.rstrip(" .,;:")
    if stripped in {_fold(phrase) for phrase in DEICTIC_PHRASES} or not _distinguishing(folded):
        return TargetResolution(
            resolved_to=None, considered=considered, referring_text=referring_text
        )
    matched = [candidate.node_id for candidate in candidates if candidate.matches(folded)]
    resolved = matched[0] if len(matched) == 1 else None
    return TargetResolution(
        resolved_to=resolved, considered=considered, referring_text=referring_text
    )


def check(
    *,
    body: AnnotatedBody,
    start: int,
    end: int,
    quoted: str,
    asserting_node_id: str,
    referring_text: str,
    candidates: tuple[Candidate, ...],
    language: str,
) -> StatedAssertionCheck | Refused:
    """All four gates, in order, over one candidate assertion.

    Returns the check a `obs.said.*` edge needs, or the first `Refused` - first, because a
    caller that has one reason not to emit does not need the rest, and because running a
    resolver over a span that failed its own string match would be work spent on a
    quotation that is not in the source.
    """
    span = match_span(body, start, end, quoted, node_id=asserting_node_id)
    if isinstance(span, Refused):
        return span
    clearance = clear_clause(body, start, end, language=language)
    if isinstance(clearance, Refused):
        return clearance
    target = resolve_target(referring_text, candidates)
    if not target.unique:
        return Refused(
            gate="target",
            why=(
                "the span identifies the relationship but not which node it points at; the "
                "honest outcomes are an inferred relation with the ambiguity recorded, or no "
                "edge"
            ),
            candidates=target.considered,
        )
    return StatedAssertionCheck(
        span=span,
        target=target,
        clearance=clearance.clearance,
        asserted_by=asserting_node_id,
    )


__all__ = [
    "ASSERTABLE_CLASSES",
    "DEICTIC_PHRASES",
    "GENERIC_TOKENS",
    "HEDGE_CUES",
    "HYPOTHETICAL_CUES",
    "INTERROGATIVE_OPENERS",
    "NEGATION_CUES",
    "SUPPORTED_LANGUAGE",
    "Candidate",
    "Cleared",
    "Refused",
    "check",
    "clause_of",
    "clear_clause",
    "match_span",
    "resolve_target",
]
