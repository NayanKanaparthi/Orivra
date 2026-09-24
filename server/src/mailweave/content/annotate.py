"""Amendment A7: the content pipeline annotates, and it does not delete.

`body_clean` is no longer a smaller copy of the body. It is **the full text with
classified spans**, and the disclosure layer decides which spans to show.

## Why the operation changed rather than the rule

Four rounds tried to make a deleting quote-stripper safe. Round 5 fixed it, round 6
defeated the fix with an adverb, round 7 fixed it again and found the protection sat above
a library that had already decided, round 8 removed the library, measured zero false
positives across 200 sentences in three corpora - and a reviewer's fourth corpus destroyed
**14 of 54, 25.9%**, while the latch destroyed **1,251 of 1,251** tagged sender characters
across sixteen cases. Every fix was real and every measurement was honest.

Deciding whether a line is quoted material or the sender's own prose is genuinely
ambiguous. `"To: recap, we need three approvals"` is a sentence *and* a header field
followed by text, and no rule separates those without a corpus containing that shape. The
operation is what fails: **deletion is irreversible**, so every ambiguous case is a coin
flip whose losing face destroys the user's words permanently.

So nothing is deleted. A misclassification now costs a wrong default view, and the text is
one depth step away.

## What this module guarantees, and how

An `AnnotatedBody` **cannot exist** unless its spans tile its text exactly: contiguous,
non-overlapping, starting at 0, ending at `len(text)`, and re-joining to the input
character for character. That check runs in `__post_init__`, so there is no way to build an
annotation that lost a character and no path that skips the check - which is the same move
`withheld := H - disclosed` made for evidence and deriving thread ids made for provenance:
**make the bad state unrepresentable instead of guarding the path to it.**

The gate is therefore one total property, mechanically checkable and not defeatable by a
corpus nobody thought of:

    "".join(text[span.start:span.end] for span in spans) == text

`tests/test_a7_containment.py` states it over arbitrary generated input rather than over
fixtures, because a corpus is only evidence about the shapes somebody thought of - which is
precisely how the last four rounds each passed and were then defeated.

## The five classes, and which of them the default view shows

`original` is the default view. Everything else is present in `body_clean.text` and absent
from `body_clean.view()`.

**The recovery guarantee is `view(list(SpanClass))`, and it is not "one class wider"**
(R-ARCH-029). Widening to *every* class returns the text exactly, always; widening by one
class returns whatever happens to sit in that class, which for a misclassified region is
often nothing. R-ARCH re-ran round 8's corpus against `(ORIGINAL, UNCERTAIN)` and **all
fourteen** misclassified entries still missed a fragment - eight classified `quoted`, six
under a `forwarded` heading line. What makes A7 downgrade content loss from a blocker is
**containment** - the text is present and addressable - not that one widening always
retrieves it. The five classes:

  * `quoted` / `forwarded` / `signature` - a client wrote a marker this module recognises,
    and the marker also says where the region ends;
  * `uncertain` - the region was opened by a signal a client wrote and **no client marked
    its end**, so its extent is this module's judgement. Round 8 deleted exactly these
    characters and called them quoted. A7 keeps them and calls them what they are;
  * `original` - no structural signal. Amendment A5 still governs what counts as a signal:
    prose that merely *looks* like an attribution is the sender's until a recognised client
    format says otherwise. Such a line stays `original` and carries the
    `attribution_shaped_unrecognised` signal, so the shape it was checked against is in the
    annotation rather than in a docstring.

**No classification tuning happened this round.** The regions are exactly the regions round
8's stripper deleted, so the default view reproduces round 8's `body_clean` and today's
token economics, and the default-view quality numbers in `docs/reviews/ROUND_09/HANDOFF.md`
are directly comparable with round 8's destruction numbers. What changed is that the
characters are still there.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from mailweave.errors import AnnotationContainmentError


class SpanClass(StrEnum):
    """What a span of `body_clean` is, per amendment A7. A closed vocabulary.

    `uncertain` is not a failure mode; it is the honest answer where the classification is
    genuinely undetermined, and A7 exists because forcing that answer into a binary is what
    destroyed text for four rounds.
    """

    ORIGINAL = "original"
    QUOTED = "quoted"
    FORWARDED = "forwarded"
    SIGNATURE = "signature"
    UNCERTAIN = "uncertain"


#: What a default view shows (A7). Everything else stays in `body_clean.text`, and
#: `view(list(SpanClass))` returns that text exactly - which is what makes every view
#: reversible. Reversible by widening to *all* classes; not necessarily by widening one
#: class (R-ARCH-029).
DEFAULT_VIEW_CLASSES: Final[frozenset[SpanClass]] = frozenset({SpanClass.ORIGINAL})

#: The signal an `original` span carries when nothing structural was found at all.
NO_STRUCTURAL_SIGNAL: Final = "no_structural_signal"


@dataclass(frozen=True)
class AnnotatedSpan:
    """One classified run of `AnnotatedBody.text`, half-open `[start, end)`.

    It carries the **signal that classified it**, not only the class, because the class
    alone does not say whether the region's extent was marked by a client or judged by this
    module - and that distinction is the whole of R-ARCH-026.
    """

    start: int
    end: int
    classification: SpanClass
    signal: str

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise AnnotationContainmentError(
                f"span [{self.start}, {self.end}) is empty or negative; a span names a run "
                "of real characters"
            )
        if not self.signal:
            raise AnnotationContainmentError(
                f"span [{self.start}, {self.end}) classified {self.classification.value!r} "
                "names no signal; A7 requires every span to carry the signal that "
                "classified it"
            )

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class AnnotatedBody:
    """The full body text, plus a tiling of it into classified spans (amendment A7).

    **This type is the containment gate.** The constructor refuses any span set that does
    not reproduce `text` character for character, so "no input text is absent from the
    annotated output" is a property of the type rather than a test that has to remember to
    run. A caller cannot assemble an annotation that lost a character, in the same way a
    caller cannot assemble an `Envelope` that dropped a hit.
    """

    text: str
    spans: tuple[AnnotatedSpan, ...]

    def __post_init__(self) -> None:
        self._refuse_anything_that_does_not_tile_the_text()

    def _refuse_anything_that_does_not_tile_the_text(self) -> None:
        """A7's gate, executed. Contiguous from 0 to `len(text)`, and re-joining exactly.

        Both halves are asserted even though contiguity implies the join: the join equality
        is the gate as A7 states it, and stating it literally means a future change to the
        contiguity arithmetic cannot quietly change what is being guaranteed.
        """
        if not self.spans:
            if self.text:
                raise AnnotationContainmentError(
                    f"an annotated body of {len(self.text)} characters carries no spans; "
                    "under amendment A7 every character of the input is inside a span"
                )
            return
        cursor = 0
        for span in self.spans:
            if span.start != cursor:
                raise AnnotationContainmentError(
                    f"span [{span.start}, {span.end}) does not continue from character "
                    f"{cursor}: {abs(span.start - cursor)} characters are "
                    f"{'absent from' if span.start > cursor else 'duplicated in'} the "
                    "annotation. Amendment A7 gates on every input character being present "
                    "in the annotated output"
                )
            if span.end > len(self.text):
                raise AnnotationContainmentError(
                    f"span [{span.start}, {span.end}) runs past the end of a "
                    f"{len(self.text)}-character body"
                )
            cursor = span.end
        if cursor != len(self.text):
            raise AnnotationContainmentError(
                f"the annotation stops at character {cursor} of {len(self.text)}: "
                f"{len(self.text) - cursor} characters of the input are absent from the "
                "annotated output, which amendment A7 forbids"
            )
        rejoined = "".join(self.text[span.start : span.end] for span in self.spans)
        if rejoined != self.text:  # pragma: no cover - contiguity above makes this dead
            raise AnnotationContainmentError(
                "re-joining the annotated spans does not reproduce the input text"
            )

    @classmethod
    def empty(cls) -> AnnotatedBody:
        """The annotation of a body with no characters in it."""
        return cls(text="", spans=())

    def text_of(self, span: AnnotatedSpan) -> str:
        return self.text[span.start : span.end]

    def view(self, classes: Iterable[SpanClass] = DEFAULT_VIEW_CLASSES) -> str:
        """The spans of `classes`, in order, concatenated.

        The disclosure layer's choice, expressed as a function rather than as a deletion.
        `view()` with no argument is the default view A7 names - `original` spans only -
        and every other view is reachable from the same object, which is what "reversible"
        means here.
        """
        wanted = frozenset(classes)
        return "".join(self.text_of(span) for span in self.spans if span.classification in wanted)

    def chars(self, *classes: SpanClass) -> int:
        """How many characters are classified as any of `classes`."""
        wanted = frozenset(classes)
        return sum(span.length for span in self.spans if span.classification in wanted)

    def signals(self, *classes: SpanClass) -> tuple[str, ...]:
        """The distinct signals that classified the spans of `classes`, sorted."""
        wanted = frozenset(classes)
        return tuple(sorted({span.signal for span in self.spans if span.classification in wanted}))

    @property
    def classified_chars(self) -> Mapping[SpanClass, int]:
        """Characters per class, for every class that has any. The reported metric's input."""
        counts: dict[SpanClass, int] = {}
        for span in self.spans:
            counts[span.classification] = counts.get(span.classification, 0) + span.length
        return counts

    @property
    def hidden_chars(self) -> int:
        """Characters present in `text` and absent from the default view.

        Under round 8 this number was *deleted*. Under A7 it is the size of the difference
        between the default view and the whole body, which a caller can close by asking for
        a wider view.
        """
        return len(self.text) - len(self.view())

    @property
    def latched(self) -> bool:
        """Whether any region's extent was this module's judgement rather than a marker.

        R-ARCH-026's property, kept as a reported fact. Under A7 a latch is no longer
        destructive - the characters are in `text` - so this says "the default view may be
        wrong here", not "text was lost here".
        """
        return any(span.classification is SpanClass.UNCERTAIN for span in self.spans)


def build_annotation(text: str, classified: Sequence[tuple[SpanClass, str]]) -> AnnotatedBody:
    """Assemble an `AnnotatedBody` from a per-line classification of `text`.

    `classified[i]` is the `(class, signal)` of `text.split("\\n")[i]`. The line's span
    includes its own terminating newline, and the last line has none, which is what makes
    the spans tile the text exactly rather than approximately - the arithmetic that used to
    live in `strip_quotes_and_signature`'s `residual_chars`, where whitespace folded away
    while re-joining kept lines and had to be declared separately. Nothing folds away now.

    Adjacent lines sharing a class *and* a signal merge into one span, so the annotation
    reads as regions rather than as a per-line table.
    """
    lines = text.split("\n")
    if len(classified) != len(lines):
        raise AnnotationContainmentError(
            f"{len(classified)} classifications for {len(lines)} lines; every line of the "
            "input must be classified, which is what makes the spans cover it"
        )
    if text == "":
        return AnnotatedBody.empty()

    spans: list[AnnotatedSpan] = []
    offset = 0
    last = len(lines) - 1
    for index, line in enumerate(lines):
        width = len(line) + (1 if index < last else 0)
        if width == 0:
            # The final line of a text ending in "\n" is empty and occupies no characters.
            continue
        classification, signal = classified[index]
        if spans and spans[-1].classification is classification and spans[-1].signal == signal:
            previous = spans.pop()
            spans.append(
                AnnotatedSpan(
                    start=previous.start,
                    end=offset + width,
                    classification=classification,
                    signal=signal,
                )
            )
        else:
            spans.append(
                AnnotatedSpan(
                    start=offset,
                    end=offset + width,
                    classification=classification,
                    signal=signal,
                )
            )
        offset += width
    return AnnotatedBody(text=text, spans=tuple(spans))
