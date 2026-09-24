"""Quote and signature **classification** (AD D.4a 6), owned end to end by this module.

**Round 9, amendment A7: this module no longer removes anything.** It classifies the lines
of a body, and `content/annotate.py` turns that classification into spans over the full
text. There is no function here that returns a smaller string than it was given.

## Why, in four rounds

Round 5 fixed the stripper. Round 6 defeated the fix with an adverb between the pronoun and
the verb. Round 7 fixed it again under amendment A5 and found the protection sat above
`email_reply_parser`, which had already decided on `On.*wrote:$`. Round 8 removed the
library, took the segmentation into this file, and measured **0 false positives across 200
sentences in three corpora** - and a reviewer's fourth corpus destroyed **14 of 54, 25.9%**
through two ordinary prose shapes, while the latch destroyed **1,251 of 1,251** tagged
sender characters across sixteen cases.

Every fix was real. The operation is what failed: `"To: recap, we need three approvals"` is
a sentence *and* a header field followed by text, and **deletion makes every ambiguous case
irreversible**. So A7 changes the operation. The rules below are round 8's rules, unchanged
and untuned, because a misclassification now costs a wrong default view rather than the
user's words - and tuning the rules until a number looked good is exactly what the last four
rounds did.

## What may be classified as prior conversation, and nothing else

Amendment A5 is unchanged by A7 and still governs: a line only leaves the default view on a
**strong structural signal**, each named on the span that carries it:

  * `quote_marker` - a run of `>`-prefixed lines. The oldest and least ambiguous quote
    signal there is, and the only one that survives every client;
  * `forward_separator` - `-----Original Message-----`, `Begin forwarded message:`,
    `---------- Forwarded message ---------`;
  * `header_block` - **two or more distinct** `From:`/`Sent:`/`To:`/`Cc:`/`Subject:`/`Date:`
    fields on consecutive lines. One such line is a form or a sentence ("To: whoever
    reviews this next, please check the totals") and is left alone, which is precisely what
    the library's one-line `HEADER_REGEX` got wrong;
  * `client_attribution` - a line matching a recognised client attribution **format**
    (`_client_attribution_template`), which requires a lead-in word at the start of the
    line, a full calendar date, an address, and the verb last, with no first-person pronoun
    anywhere outside the date. "Once the negotiations concluded, the legal team wrote:"
    matches none of that;

and signatures, which are their own two signals: `signature_delimiter` (a line that is
*only* `--` or `__`, RFC 3676) and `signature_sign_off` (a recognised sign-off or mobile
footer with body text above it and only a few short lines below).

**MIME boundaries are not a signal here**, although A5 lists them. `content/mime.py`
consumes them before this module is ever called, and a boundary detector over already
decoded text is exactly the `-\\w` shape whose false positives round 8 closed.

## The three unmarked extents, which is where R-ARCH-026 went

A forward separator, a header block, and a recognised attribution with no `>` run under it
are each followed by the whole prior message with no per-line marker, so there is no end
this module can identify. Round 8 ran the deletion to the end of the message and named the
judgement in the reduction. R-ARCH-026 then measured the cost: **every one of 1,251 tagged
sender characters written below such a block, in all sixteen cases tried.**

Under A7 the extent is judged in exactly the same place, on exactly the same signals - and
the region is classified `uncertain` instead of deleted. The characters stay in
`body_clean.text`, and `view(list(SpanClass))` returns them exactly. For *this* shape - a
latched extent - `view((ORIGINAL, UNCERTAIN))` returns them too, measured at 1,264 of
1,264; that is a property of the latch corpus and not a general one, and the guarantee A7
rests on is containment rather than any particular widening step (R-ARCH-029). A `>` run
and an attribution line whose block the client *did* mark still do not latch, because inline
replies are ordinary mail.

## What this module still declares

Where the classifier is unsure in A5's sense - a line with the *shape* of an attribution
that matches no client format, sitting directly above something that was classified - the
span stays `original` (A5: shape alone may not cost a sender their words) and carries the
`attribution_shaped_unrecognised` signal, which the pipeline turns into a `Reduction` of
zero characters with a reason. The ambiguity is visible in the response instead of being
resolved silently in either direction.

## The measured cost, stated rather than glossed

Under-classification is unchanged and still spent freely: an attribution carrying no address
is not recognised, and an unquoted forwarded body under one is `uncertain` rather than
`quoted`. What A7 removes is the catastrophic failure mode, not the need to classify well:
`tests/test_a7_containment.py` gates character-level containment over arbitrary generated
input, and `tests/test_a7_default_view_quality.py` reports default-view quality across four
corpora without gating it, which is exactly how A7 divides the two.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import Final

from mailweave.content.annotate import (
    NO_STRUCTURAL_SIGNAL,
    AnnotatedBody,
    SpanClass,
    build_annotation,
)

#: This module's own detector, named on every reduction it produces. It is deliberately
#: not a distribution name any more: since round 8 no third-party parser decides how
#: `body_clean` is classified, and reporting one would say a library made a decision this
#: file makes. Bump it when the classification changes, so a reduction record identifies
#: the rules that produced it. Round 9 bumps it for amendment A7.
_CLASSIFIER = "mailweave.content.quotes"
_CLASSIFIER_REVISION = "a7-round9"

#: The attribution verb each locale's clients emit, keyed by locale so the coverage claim
#: is *derivable* rather than asserted beside the list (R-ARCH-020/021). Round 6 counted
#: twelve entries and eleven distinct patterns - `"skrev"` appeared twice, verbatim - so
#: "ten locales" was a claim the data did not support. The mapping below is the claim:
#: `tests/test_quote_corpus.py` asserts that every locale here has a worked example and
#: that no pattern repeats, so the number in this comment cannot drift from the code.
#:
#: Each entry is the *verb* only. The date and name formats in front of it differ per
#: client as well as per locale, and are handled by the templates below.
_ATTRIBUTION_VERBS_BY_LOCALE: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "en": (r"wrote",),
        "fr": (r"a\s+écrit",),
        "es": (r"escribió", r"escribio"),
        "pt": (r"escreveu",),
        "de": (r"schrieb",),
        "it": (r"ha\s+scritto",),
        "nl": (r"schreef",),
        "pl": (r"napisał[ay]?",),
        "sv": (r"skrev",),
        "fi": (r"kirjoitti",),
    }
)
_ATTRIBUTION_VERBS: Final[tuple[str, ...]] = tuple(
    pattern for patterns in _ATTRIBUTION_VERBS_BY_LOCALE.values() for pattern in patterns
)
_ATTRIBUTION_VERB_PATTERN = "|".join(_ATTRIBUTION_VERBS)

#: Attribution lines that introduce a quoted chain ("On <date> X wrote:").
#:
#: Used only to decide whether a fragment the parser *already removed* is prior
#: conversation or a signature - a classification question, never a deletion one - so it
#: stays the loose shape it has been since R-ARCH-001. Nothing is deleted on the strength
#: of this pattern; `_client_attribution_template` is what deletion requires (A5).
_ATTRIBUTION_RE = re.compile(rf"^.{{0,200}}\b(?:{_ATTRIBUTION_VERB_PATTERN})\s*:\s*$", re.I | re.M)

#: The same verbs, not necessarily at the end of the line: German and Dutch put the sender
#: *after* the verb. Used **only** to count how many attribution-shaped lines were kept -
#: the ambiguity A5 requires to be visible - and never to remove anything.
_ATTRIBUTION_TAIL_RE = re.compile(
    rf"^.{{0,200}}\b(?:{_ATTRIBUTION_VERB_PATTERN})\b.{{0,200}}:\s*$", re.I
)

#: An RFC-5322-ish address, with or without angle brackets. This is the strong structural
#: signal a client attribution line always carries and prose usually does not.
_ADDRESS_PATTERN = (
    r"(?:<[^<>@\s]{1,64}@[^<>\s]{1,255}>"
    r"|\(?\b[\w.!#$%&'*+/=?^`{|}~-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,8}\b\)?)"
)
_ADDRESS_RE = re.compile(_ADDRESS_PATTERN)

#: A **calendar date**: the "when" half of a client attribution header, in the four
#: spellings the ten locales' clients use. This is deliberately stricter than "a year or a
#: clock somewhere on the line", which round 6 used and which ordinary prose satisfies
#: constantly ("the 2026 roadmap", "the 15:14 bridge call"). A client never writes an
#: attribution without a full date, and a person almost never writes a sentence that
#: carries one *and* an address *and* ends on the verb.
_WHEN_PATTERN = (
    r"(?:"
    r"\b\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*(?:19|20)?\d{2}\b"  # 25.08.2026, 25/08/26
    r"|\b\d{1,2}\s+de\s+[^\W\d_]{2,12}\.?\s+de\s+(?:19|20)\d{2}\b"  # pt: 25 de ago de 2026
    r"|\b\d{1,2}\.?\s+[^\W\d_]{2,12}\.?,?\s+(?:19|20)\d{2}\b"  # 25 aug. 2026, 25. elok. 2026
    r"|\b[^\W\d_]{2,12}\.?\s+\d{1,2},?\s+(?:19|20)\d{2}\b"  # Aug 25, 2026
    r")"
)

#: The word each locale's client opens the attribution line with. Anchored at the start of
#: the line, which is the difference between recognising a *format* and recognising a
#: word order: a sentence is free to contain "wrote" and an address, and almost never
#: begins with the client's lead-in *and* carries a date *and* ends on the verb.
#: The Finnish weekday abbreviations must be followed by a number, because two-letter
#: alternatives that can start an English sentence are otherwise far too cheap to match.
_LEAD_INS: Final[tuple[str, ...]] = (
    r"on",  # en - Gmail, Apple Mail, Outlook
    r"le",  # fr
    r"am",  # de
    r"op",  # nl
    r"il\s+giorno",  # it
    r"w\s+dniu",  # pl
    r"den",  # sv / da / no
    r"el",  # es
    r"em",  # pt
    r"(?:ma|ti|ke|to|pe|la|su)(?=\s+\d)",  # fi weekday abbreviations
)
_LEAD_IN_PATTERN = "|".join(_LEAD_INS)

#: `<lead-in> ... <when> ... <address> ... <verb>:` - the verb-final word order, which is
#: what English, French, Spanish, Portuguese, Italian, Polish and Finnish clients emit.
_TEMPLATE_VERB_FINAL = re.compile(
    rf"^(?:{_LEAD_IN_PATTERN})\b.{{0,160}}{_WHEN_PATTERN}.{{0,120}}"
    rf"{_ADDRESS_PATTERN}.{{0,60}}\b(?:{_ATTRIBUTION_VERB_PATTERN})\s*:\s*$",
    re.I,
)

#: `<lead-in> ... <when> ... <verb> <sender> <address>:` - German, Dutch and Swedish put
#: the sender after the verb, which is why a verb-final pattern alone cannot see them.
_TEMPLATE_VERB_MEDIAL = re.compile(
    rf"^(?:{_LEAD_IN_PATTERN})\b.{{0,160}}{_WHEN_PATTERN}.{{0,120}}"
    rf"\b(?:{_ATTRIBUTION_VERB_PATTERN})\s+[^<>:]{{0,60}}{_ADDRESS_PATTERN}\s*:\s*$",
    re.I,
)

#: `[Display Name] <address> wrote:` with nothing else on the line - the shortest form a
#: client emits. The prefix is checked to be a display name rather than a clause, because
#: "and here is what devops@example.com wrote:" fits every other part of this shape and is
#: a sentence somebody typed.
_TEMPLATE_BARE = re.compile(
    rf"^(?P<name>.{{0,60}}?)\s*{_ADDRESS_PATTERN}\s*"
    rf"\b(?:{_ATTRIBUTION_VERB_PATTERN})\s*:\s*$",
    re.I,
)

#: First-person subjects, in every locale the verb list covers, matched **anywhere on the
#: line** rather than only immediately before the verb (R-ARCH-019). A mail client's
#: attribution names the person who wrote the quoted message; it never says "I", "we" or
#: their translations. Round 6 checked only the token adjacent to the verb, so an adverb
#: between the pronoun and the verb hid the subject, and the plurals were absent entirely.
#: Over-matching here can only cause a *false negative* - a header that survives - which
#: is the direction amendment A5 chooses on purpose.
_FIRST_PERSON_RE = re.compile(
    r"(?<![\w'’])(?:"
    r"i|me|my|mine|we|us|our|ours|"  # en
    r"je|j'|moi|mon|ma|mes|nous|notre|nos|"  # fr
    r"ich|mich|mir|mein|meine|wir|uns|unser|"  # de
    r"yo|mi|mis|nosotros|nuestro|"  # es
    r"eu|meu|minha|nós|nosso|"  # pt
    r"io|mio|mia|noi|nostro|"  # it
    r"ik|mij|mijn|wij|ons|onze|"  # nl
    r"ja|mnie|mój|moje|my|nasz|"  # pl
    r"jag|mig|min|mitt|vi|oss|"  # sv
    r"jeg|"  # da / no
    r"minä|minun|meidän"  # fi
    r")(?![\w'’])",
    re.I,
)

#: Weekday names and abbreviations in the locales the verb list covers, plus Danish and
#: Norwegian. **This list exists to be masked, never to match anything on its own**
#: (R-ARCH-023): several of these tokens are also first-person pronouns in a *different*
#: locale, and a client attribution's weekday collides with the pronoun scan above:
#:
#:   | weekday | collides with |
#:   |---|---|
#:   | en `Mon` (Monday) | fr `mon` ("my") |
#:   | de `Mi.` (Mittwoch) | es `mi` ("my") |
#:   | nl `ma` / fi `ma` (Monday) | fr `ma` ("my", fem.) |
#:   | sv `ons` (onsdag) | nl `ons` ("our") |
#:
#: Round 7 reported the residue as "both English attributions carrying no address" and
#: measured a 12.5% false-negative rate. R-ARCH measured **36.8%**: every worked example in
#: the corpus was dated a **Tuesday**, and a Tuesday collides with nothing, so a corpus of
#: one weekday could not falsify the claim. A header dated a Monday in en/nl/fi, or a
#: Wednesday in de/sv, was silently kept however well-formed it was.
_WEEKDAY_TOKENS: Final[tuple[str, ...]] = (
    # en
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "mon",
    "tue",
    "tues",
    "wed",
    "thu",
    "thur",
    "thurs",
    "fri",
    "sat",
    "sun",
    # fr
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
    "lun",
    "mar",
    "mer",
    "jeu",
    "ven",
    "sam",
    "dim",
    # de
    "montag",
    "dienstag",
    "mittwoch",
    "donnerstag",
    "freitag",
    "samstag",
    "sonnabend",
    "sonntag",
    "mo",
    "di",
    "mi",
    "do",
    "fr",
    "sa",
    "so",
    # es
    "lunes",
    "martes",
    "miércoles",
    "miercoles",
    "jueves",
    "viernes",
    "sábado",
    "sabado",
    "domingo",
    "mié",
    "mie",
    "jue",
    "vie",
    "sáb",
    "sab",
    "dom",
    # pt
    "segunda",
    "terça",
    "terca",
    "quarta",
    "quinta",
    "sexta",
    "seg",
    "ter",
    "qua",
    "qui",
    "sex",
    # it
    "lunedì",
    "lunedi",
    "martedì",
    "martedi",
    "mercoledì",
    "mercoledi",
    "giovedì",
    "giovedi",
    "venerdì",
    "venerdi",
    "sabato",
    "domenica",
    "gio",
    # nl
    "maandag",
    "dinsdag",
    "woensdag",
    "donderdag",
    "vrijdag",
    "zaterdag",
    "zondag",
    "ma",
    "wo",
    "vr",
    "za",
    "zo",
    # pl
    "poniedziałek",
    "wtorek",
    "środa",
    "czwartek",
    "piątek",
    "sobota",
    "niedziela",
    "pon",
    "wt",
    "śr",
    "czw",
    "pt",
    "sob",
    "niedz",
    # sv / da / no
    "måndag",
    "tisdag",
    "onsdag",
    "torsdag",
    "fredag",
    "lördag",
    "söndag",
    "mandag",
    "tirsdag",
    "lørdag",
    "søndag",
    "mån",
    "tis",
    "ons",
    "tors",
    "tor",
    "fre",
    "lör",
    "sön",
    "man",
    "tir",
    "lør",
    "søn",
    # fi
    "maanantai",
    "tiistai",
    "keskiviikko",
    "torstai",
    "perjantai",
    "lauantai",
    "sunnuntai",
    "ti",
    "ke",
    "pe",
    "la",
    "su",
)
_WEEKDAY_PATTERN = "|".join(sorted(set(_WEEKDAY_TOKENS), key=len, reverse=True))

#: The calendar date itself, compiled on its own so the span it occupies can be found and
#: excluded from the first-person scan rather than only matched inside a template.
_WHEN_RE = re.compile(_WHEN_PATTERN, re.I)

#: A weekday token sitting immediately in front of a date, with only punctuation and
#: whitespace between. Anchored to the end of the text it is searched in, which is the
#: slice of the line *before* the date match - so this can only ever consume a token that
#: is part of the calendar expression the date match already found.
_WEEKDAY_BEFORE_A_DATE_RE = re.compile(rf"(?<![\w'’])(?:{_WEEKDAY_PATTERN})\.?\s*,?\s*$", re.I)


def _calendar_masked(line: str) -> str:
    """`line` with its calendar expression blanked out, for the first-person scan only.

    R-ARCH-023's required fix, in one function: *scope the first-person scan off calendar
    tokens already consumed by the date match*. Every client attribution puts the weekday
    immediately in front of the date, so the mask is the date's own span extended left
    across a single weekday token, and **nothing else on the line is touched**.

    Two properties make this safe in the direction that matters. It only runs when a full
    calendar date is present, so a sentence with no date is unaffected; and it can only
    ever remove a *disqualification*, so the lines it changes the answer for are exactly
    the lines that already carry a lead-in word, a full date, an address and a final verb.
    "On Mon, 25 August 2026 I wrote to priya@example.com and she wrote:" keeps its "I":
    the mask covers "Mon, 25 August 2026" and stops there.
    """
    match = _WHEN_RE.search(line)
    if match is None:
        return line
    start, end = match.span()
    weekday = _WEEKDAY_BEFORE_A_DATE_RE.search(line[:start])
    if weekday is not None:
        start = weekday.start()
    return line[:start] + " " * (end - start) + line[end:]


#: How long a line may be and still be considered as a client attribution header. Real
#: ones are one line of metadata; a 400-character line is a paragraph.
_MAX_ATTRIBUTION_LINE_CHARS = 300
#: How many whitespace tokens a display name may have in the bare template.
_MAX_DISPLAY_NAME_TOKENS = 4

#: Client separators that introduce a quoted or forwarded block.
_SEPARATOR_RE = re.compile(
    r"^\s*(?:[-_*]{2,}\s*)?(?:original message|forwarded message|begin forwarded message)"
    r"\s*(?:[-_*]{2,})?\s*:?\s*$",
    re.I | re.M,
)
#: The same, anchored to a single line, for splitting a fragment at the separator.
_SEPARATOR_LINE_RE = re.compile(
    r"^\s*(?:[-_*]{2,}\s*)?(?:original message|forwarded message|begin forwarded message)"
    r"\s*(?:[-_*]{2,})?\s*:?\s*$",
    re.I,
)
#: The Outlook/O365 header block. Two or more of these lines is a quoted header, not prose.
_QUOTE_HEADER_RE = re.compile(
    r"^\s*(from|sent|to|cc|bcc|subject|date|reply-to)\s*:\s*\S", re.I | re.M
)
#: A run of `>` markers: the oldest and least ambiguous quote signal there is.
_QUOTE_MARKER_RE = re.compile(r"^\s*>", re.M)
#: The same three, anchored to one line. The segmenter works line by line, because a
#: region that may be deleted has to have a first line and a last line that can be named.
_QUOTE_MARKER_LINE_RE = re.compile(r"^\s*>")
_QUOTE_HEADER_LINE_RE = re.compile(
    r"^\s*(from|sent|to|cc|bcc|subject|date|reply-to)\s*:\s*\S", re.I
)
#: RFC 3676's signature delimiter, and **only** that: a line whose entire content is `--`
#: or `__`. The library this module replaced used `(--|__|-\w)` as a *prefix* test, so
#: "-1 day change to the schedule" opened a signature and everything below it was deleted.
#: A whole-line match cannot do that, and a person writing a line that is only two dashes
#: is writing the delimiter.
_SIGNATURE_DELIMITER_LINE_RE = re.compile(r"^\s*(?:--|__)\s*$")
#: How many distinct header fields make a run of lines a client's header block rather than
#: a sentence that opens "To: ...". One is a form or an address in prose; two is a block.
_HEADER_BLOCK_MIN_FIELDS = 2

#: Sign-offs that start a signature block when nothing delimits it.
_SIGN_OFF_RE = re.compile(
    r"^\s*(?:"
    r"best regards|kind regards|warm regards|with regards|best wishes|all the best|"
    r"many thanks|thanks again|thanks in advance|thank you|thanks|cheers|regards|best|"
    r"sincerely|yours sincerely|yours truly|yours faithfully|respectfully"
    r")\s*[,.!]?\s*$",
    re.I,
)
#: Mobile client sign-offs, which are signatures with no sign-off line at all.
_MOBILE_SIGN_OFF_RE = re.compile(
    r"^\s*(?:sent from my \S.*|sent from \S+ mail.*|get outlook for \S+.*)$", re.I
)

#: A signature block is short. These two bounds are what keeps the no-delimiter detector
#: from eating a paragraph that happens to begin with "Thanks,".
_MAX_SIGNATURE_LINES = 6
_MAX_SIGNATURE_LINE_CHARS = 60


def classifier_version() -> str:
    """Which detector produced a classification. Since round 8 that is this module.

    It used to report `email-reply-parser@<version>`, which was true while the library
    decided what to delete. It no longer decides anything (R-ARCH-022), so naming it here
    would attribute this module's rules to somebody else's code. Round 9 renames the
    function with amendment A7: nothing here strips any more, so calling it
    `stripper_version` would name an operation this module stopped performing.
    """
    return f"{_CLASSIFIER}@{_CLASSIFIER_REVISION}"


#: The names of the structural signals this module recognises. Every span carries one, and
#: `classify_lines` refuses to hand back a non-`original` line that names none - which is
#: amendment A5's rule (text may only be treated as prior conversation on a strong
#: structural signal) expressed as a runtime invariant rather than as a convention the next
#: change has to remember. A5 survives A7 unchanged: what A7 changes is that a line the
#: rule catches is *hidden from the default view* rather than deleted.
QUOTE_MARKER: Final = "quote_marker"
FORWARD_SEPARATOR: Final = "forward_separator"
HEADER_BLOCK: Final = "header_block"
CLIENT_ATTRIBUTION: Final = "client_attribution"
SIGNATURE_DELIMITER: Final = "signature_delimiter"
SIGNATURE_SIGN_OFF: Final = "signature_sign_off"

#: The signals whose region has **no end any client marked**, so its extent is this
#: module's judgement. Round 8 deleted to the end of the message on all three and named the
#: judgement in the reduction detail; R-ARCH-026 then measured 1,251 of 1,251 tagged sender
#: characters destroyed across sixteen cases, because sender-authored text written *below*
#: an unmarked quoted block is inside the judged extent.
#:
#: Under A7 the extent is still judged - nothing here got better at guessing - but the
#: judgement is recorded as `SpanClass.UNCERTAIN` and the characters stay in
#: `body_clean.text`. That is the whole of R-ARCH-026's dissolution: the same region, the
#: same signal, a different operation.
FORWARD_SEPARATOR_UNMARKED_EXTENT: Final = "forward_separator_unmarked_extent"
HEADER_BLOCK_UNMARKED_EXTENT: Final = "header_block_unmarked_extent"
CLIENT_ATTRIBUTION_UNMARKED_EXTENT: Final = "client_attribution_unmarked_extent"

#: A line kept as the sender's own, whose *shape* is an attribution the templates did not
#: recognise. Amendment A5's declared-uncertainty clause, now carried on the span itself:
#: the class is `original`, because A5 rules that shape alone may not cost a sender their
#: words, and the signal says the shape was seen and rejected rather than never examined.
ATTRIBUTION_SHAPED_UNRECOGNISED: Final = "attribution_shaped_unrecognised"

STRONG_STRUCTURAL_SIGNALS: Final[frozenset[str]] = frozenset(
    {
        QUOTE_MARKER,
        FORWARD_SEPARATOR,
        HEADER_BLOCK,
        CLIENT_ATTRIBUTION,
        SIGNATURE_DELIMITER,
        SIGNATURE_SIGN_OFF,
        FORWARD_SEPARATOR_UNMARKED_EXTENT,
        HEADER_BLOCK_UNMARKED_EXTENT,
        CLIENT_ATTRIBUTION_UNMARKED_EXTENT,
    }
)

#: Which unmarked-extent signal each latching signal opens.
_UNMARKED_EXTENT_OF: Final[Mapping[str, str]] = MappingProxyType(
    {
        FORWARD_SEPARATOR: FORWARD_SEPARATOR_UNMARKED_EXTENT,
        HEADER_BLOCK: HEADER_BLOCK_UNMARKED_EXTENT,
        CLIENT_ATTRIBUTION: CLIENT_ATTRIBUTION_UNMARKED_EXTENT,
    }
)

#: The class each structural signal puts a line in.
_CLASS_OF_SIGNAL: Final[Mapping[str, SpanClass]] = MappingProxyType(
    {
        QUOTE_MARKER: SpanClass.QUOTED,
        HEADER_BLOCK: SpanClass.QUOTED,
        CLIENT_ATTRIBUTION: SpanClass.QUOTED,
        FORWARD_SEPARATOR: SpanClass.FORWARDED,
        SIGNATURE_DELIMITER: SpanClass.SIGNATURE,
        SIGNATURE_SIGN_OFF: SpanClass.SIGNATURE,
        FORWARD_SEPARATOR_UNMARKED_EXTENT: SpanClass.UNCERTAIN,
        HEADER_BLOCK_UNMARKED_EXTENT: SpanClass.UNCERTAIN,
        CLIENT_ATTRIBUTION_UNMARKED_EXTENT: SpanClass.UNCERTAIN,
    }
)


def looks_quoted(text: str) -> bool:
    """True if `text` has the shape of quoted prior conversation rather than a signature.

    Exposed rather than private because this predicate is the whole of R-ARCH-001's fix,
    and a reviewer should be able to attack it directly instead of only through the
    pipeline. It is a **classification** predicate over a whole fragment, and separate from
    `classify_lines`, which is what decides a body's spans.
    """
    if _SEPARATOR_RE.search(text) or _ATTRIBUTION_RE.search(text):
        return True
    if _QUOTE_MARKER_RE.search(text):
        return True
    headers = {match.group(1).lower() for match in _QUOTE_HEADER_RE.finditer(text)}
    return len(headers) >= _HEADER_BLOCK_MIN_FIELDS


def _looks_like_a_display_name(text: str) -> bool:
    """Whether `text` could be the display name in front of an address, or is a clause.

    A display name is a few capitalised tokens. "and here is what" is four tokens too, so
    counting is not enough - each token has to begin with an upper-case letter, which is
    how every client renders a name and how almost nobody writes the middle of a sentence.
    A lower-case display name is a false negative, and A5 spends false negatives freely.
    """
    candidate = text.strip().strip('"').strip("'").strip()
    if not candidate:
        return True
    tokens = candidate.split()
    if len(tokens) > _MAX_DISPLAY_NAME_TOKENS:
        return False
    for token in tokens:
        letters = [character for character in token if character.isalpha()]
        if not letters or not letters[0].isupper():
            return False
    return True


def _client_attribution_template(line: str) -> str | None:
    """Which recognised client attribution format `line` is, or `None` for prose (A5).

    **This is the whole of amendment A5's positive half in one function.** Round 5 and
    round 6 both asked whether a line *looked like* an attribution - a verb, a colon, some
    evidence, a subject that is not first-person - and both were defeated by ordinary
    corporate English, because that description also fits sentences people write. Round 6
    measured 6 of 15 realistic sentences deleted. A5's ruling is that the description is
    the wrong question: the only thing that may cost a sender their own words is a
    **recognised client format**.

    So the line must match one of three anchored templates, each of which is what a real
    client emits rather than what an attribution tends to look like:

      * `<lead-in> <when> ... <address> ... <verb>:` - verb-final, which is English,
        French, Spanish, Portuguese, Italian, Polish and Finnish;
      * `<lead-in> <when> ... <verb> <sender> <address>:` - verb-medial, which is German,
        Dutch and Swedish;
      * `[Display Name] <address> <verb>:` - the bare form, with nothing else on the line.

    Three properties do the work, and each of them is structural rather than lexical:

      * the **lead-in is anchored to the start of the line**, so a sentence that merely
        contains an attribution verb is not a candidate at all;
      * an **address is required**, on the line, in the place the client puts it. Every
        template above carries one. "Per our 15:14 call, the customer wrote:" does not;
      * a **first-person pronoun outside the date disqualifies it**, in every locale the
        verb list covers. No client says "I". This replaces round 6's adjacent-token
        check, which an adverb walked straight past (R-ARCH-019). Round 8 scopes the scan
        off the calendar expression (`_calendar_masked`), because a weekday abbreviation
        is a first-person pronoun in a neighbouring locale and every attribution carries
        one (R-ARCH-023).

    What this gives up, stated rather than discovered later: a client attribution that
    carries no address (some Outlook builds emit `On 25/08/2026 15:14, Priya Shah wrote:`)
    is **not** recognised and survives into `body_clean`. That is the trade A5 makes -
    leaving a header in costs tokens, deleting a sentence destroys evidence - and the
    surviving-header rate is measured and reported in `tests/test_quote_corpus.py`.
    """
    candidate = line.strip()
    if not candidate or len(candidate) > _MAX_ATTRIBUTION_LINE_CHARS:
        return None
    if not candidate.endswith(":"):
        return None
    if _FIRST_PERSON_RE.search(_calendar_masked(candidate)):
        return None
    if _TEMPLATE_VERB_FINAL.match(candidate):
        return "lead_in_date_address_verb"
    if _TEMPLATE_VERB_MEDIAL.match(candidate):
        return "lead_in_date_verb_sender_address"
    bare = _TEMPLATE_BARE.match(candidate)
    if bare is not None and _looks_like_a_display_name(bare.group("name")):
        return "display_name_address_verb"
    return None


def _is_attribution_shaped(line: str) -> bool:
    """Whether a line is the *shape* A5 declines to act on: a verb, and a terminal colon.

    Used only to count the ambiguity, never to remove anything. A line that is
    attribution-shaped and matches no client template is exactly the case A5 says to keep
    and declare, so this predicate is what makes the zero-sized `Reduction` possible.
    """
    candidate = line.strip()
    if not candidate or len(candidate) > _MAX_ATTRIBUTION_LINE_CHARS:
        return False
    return bool(_ATTRIBUTION_TAIL_RE.match(candidate))


def _header_block_runs(lines: Sequence[str]) -> list[tuple[int, int]]:
    """Every client header block, as inclusive `(first, last)` index pairs.

    A block is a run of consecutive lines each of which is `Field: value`, carrying at
    least `_HEADER_BLOCK_MIN_FIELDS` **distinct** field names. The distinctness bar is the
    whole difference between this and the library's `HEADER_REGEX`, which fired on one
    line: "To: whoever reviews this next, please check the totals." was read as a header
    and everything below it was deleted as a signature (R-ARCH-022). One `Subject:` or
    `To:` line is prose or a form; two different fields in a row is a client rendering the
    message it is quoting.

    **R-ARCH-025 lives here and is not fixed by this round.** Two consecutive prose lines
    that happen to open with different field names - "To: recap, we need three
    approvals. / From: what I can tell, the budget already covers this." - satisfy the bar,
    because the bar is about line shape and a person writing memo-style prose can satisfy
    it. Round 8 destroyed both lines and the paragraphs around them. Under A7 the same
    lines are classified `quoted`, hidden from the default view, and **still in
    `body_clean.text`**, so the defect costs a wrong default view instead of the sender's
    words. It is measured in `tests/test_a7_default_view_quality.py` rather than tuned
    away, because tuning is what the last four rounds did.
    """
    runs: list[tuple[int, int]] = []
    index = 0
    while index < len(lines):
        if _QUOTE_HEADER_LINE_RE.match(lines[index]) is None:
            index += 1
            continue
        start = index
        fields: set[str] = set()
        while index < len(lines):
            found = _QUOTE_HEADER_LINE_RE.match(lines[index])
            if found is None:
                break
            fields.add(found.group(1).lower())
            index += 1
        if len(fields) >= _HEADER_BLOCK_MIN_FIELDS:
            runs.append((start, index - 1))
    return runs


def _latch(lines: Sequence[str]) -> tuple[int, str] | None:
    """The first signal after which *everything below* is prior conversation, unmarked.

    Two signals do this, and only two. A forward separator and a header block are each
    followed by the whole quoted message with no per-line marker of its own, so a reader
    who stops at the separator keeps a message body that is not the sender's. Both are
    strings a client writes.

    A `>` run and an attribution line do **not** latch - see `classify_lines`.
    """
    candidates: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if _SEPARATOR_LINE_RE.match(line):
            candidates.append((index, FORWARD_SEPARATOR))
            break
    blocks = _header_block_runs(lines)
    if blocks:
        candidates.append((blocks[0][0], HEADER_BLOCK))
    if not candidates:
        return None
    return min(candidates)


def _quote_marker_runs(lines: Sequence[str]) -> Iterable[tuple[int, int]]:
    """Maximal runs of `>`-prefixed lines, as inclusive `(first, last)` index pairs.

    Blank lines *between* two marked lines belong to the run - clients emit them inside a
    quoted block - and blank lines after the last marked line do not, because they are the
    separation between the quote and whatever the sender wrote next.
    """
    index = 0
    while index < len(lines):
        if not _QUOTE_MARKER_LINE_RE.match(lines[index]):
            index += 1
            continue
        first = index
        last = index
        cursor = index
        while cursor < len(lines):
            if _QUOTE_MARKER_LINE_RE.match(lines[cursor]):
                last = cursor
                cursor += 1
                continue
            if not lines[cursor].strip():
                cursor += 1
                continue
            break
        yield first, last
        index = last + 1


def _original_runs(classes: Sequence[SpanClass]) -> Iterable[tuple[int, int]]:
    """Maximal runs of still-`original` lines, as inclusive `(first, last)` index pairs."""
    index = 0
    while index < len(classes):
        if classes[index] is not SpanClass.ORIGINAL:
            index += 1
            continue
        first = index
        while index < len(classes) and classes[index] is SpanClass.ORIGINAL:
            index += 1
        yield first, index - 1


def _signature_start(
    lines: Sequence[str], classes: Sequence[SpanClass], first: int, last: int
) -> tuple[int, str] | None:
    """Where a signature begins inside the `original` run `first..last`, and on which signal.

    Two signals, in the order they are trusted. The RFC 3676 delimiter is unconditional -
    a line whose whole content is `--` or `__` is the delimiter, and everything below it in
    this run is the signature. The undelimited detector is deliberately conservative: the
    sign-off must have body text above it, and every non-empty line below it must be short,
    and there must be few of them, because a false positive here puts real content outside
    the default view.

    "Above" and "below" are counted over every **`original`** line of the message rather
    than over this run alone. A signature commonly sits below a quoted chain (the run it
    lives in then starts with the sender's sign-off and has nothing above it *in that run*),
    and the bound that keeps this detector off a paragraph has to see the whole reply.
    """
    kept = [index for index, found in enumerate(classes) if found is SpanClass.ORIGINAL]

    def has_body_above(index: int) -> bool:
        return any(lines[above].strip() for above in kept if above < index)

    window = range(first, last + 1)
    for index in window:
        if not _SIGNATURE_DELIMITER_LINE_RE.match(lines[index]):
            continue
        if not has_body_above(index):
            continue
        return index, SIGNATURE_DELIMITER
    for index in window:
        line = lines[index]
        if not (_SIGN_OFF_RE.match(line) or _MOBILE_SIGN_OFF_RE.match(line)):
            continue
        if not has_body_above(index):
            continue
        below = [lines[rest] for rest in kept if rest > index and lines[rest].strip()]
        if len(below) > _MAX_SIGNATURE_LINES:
            continue
        if any(len(rest.strip()) > _MAX_SIGNATURE_LINE_CHARS for rest in below):
            continue
        return index, SIGNATURE_SIGN_OFF
    return None


def classify_lines(lines: Sequence[str]) -> list[tuple[SpanClass, str]]:
    """Classify every line of a body, and name the signal that classified it (A7).

    **Nothing here removes anything.** This function replaces `_segment`, which decided
    deletions; the regions it finds are exactly the regions `_segment` deleted, and what
    changed is that they are now labelled instead. That equality is deliberate and is what
    makes the default view reproduce round 8's `body_clean` and today's token economics, and
    the default-view quality numbers directly comparable with round 8's destruction numbers.

    Order, and why it is this order:

      1. **per-line client evidence first** - a separator line, the lines of a header block,
         a `>` run, a recognised client attribution line. Each of these is a string a client
         wrote, so the line gets the signal that is actually true of it. Round 8 attributed
         a `>` run inside a forwarded block to the forward, which was the right call when
         the question was "which removal is this line inside" and the wrong one now that the
         question is "what is this line";
      2. **then the unmarked extents** - the lines below a latching signal, and the lines
         below a recognised attribution with no `>` run under it. No client marked where
         these end, so they are `uncertain` rather than `quoted`: this module is stating
         what it knows, and it does not know that the sender wrote nothing below an unmarked
         quoted block. R-ARCH-026 measured exactly how often it is wrong there;
      3. **then signatures** over what is still `original`, for the same reason as round 8:
         a signature detector that ran first would read a quoted chain's own sign-off;
      4. **then A5's declared ambiguity** - an attribution-*shaped* line that matched no
         client format and sits directly above something classified. It stays `original`,
         because A5 rules that shape alone may not cost a sender their words, and it carries
         `attribution_shaped_unrecognised` so the near miss is in the annotation.

    An inline reply - the sender answering between quoted paragraphs - keeps every answer,
    because a `>` run and an attribution line whose block *is* marked do not latch.
    """
    classes = [SpanClass.ORIGINAL] * len(lines)
    signals = [NO_STRUCTURAL_SIGNAL] * len(lines)
    decided = [False] * len(lines)

    def mark(index: int, signal: str) -> None:
        if decided[index]:
            return
        decided[index] = True
        classes[index] = _CLASS_OF_SIGNAL[signal]
        signals[index] = signal

    latched = _latch(lines)

    for index, line in enumerate(lines):
        if _SEPARATOR_LINE_RE.match(line):
            mark(index, FORWARD_SEPARATOR)
    for first, last in _header_block_runs(lines):
        for index in range(first, last + 1):
            mark(index, HEADER_BLOCK)
    for first, last in _quote_marker_runs(lines):
        for index in range(first, last + 1):
            mark(index, QUOTE_MARKER)

    # A recognised client attribution line is prior conversation's header, and the region
    # it opens is bounded by what is under it rather than by a guess:
    #
    #   * a `>` run below it anywhere means the client marked its quoted block, so the
    #     header takes **itself and nothing else** - the run is classified on its own
    #     markers, and the sender's paragraphs between the runs are theirs;
    #   * **no** `>` below it means the client emitted the quoted message unmarked, which is
    #     what Outlook, Apple Mail and every HTML body flattened to text look like. An
    #     unmarked block has no other end, so everything below is `uncertain`;
    #   * nothing at all below it means the line is a sentence, not a header, and it stays.
    unmarked_attributions: list[int] = []
    for index, line in enumerate(lines):
        if decided[index]:
            continue
        if _client_attribution_template(line) is None:
            continue
        below = range(index + 1, len(lines))
        if not any(lines[rest].strip() for rest in below):
            continue
        mark(index, CLIENT_ATTRIBUTION)
        if not any(_QUOTE_MARKER_LINE_RE.match(lines[rest]) for rest in below):
            unmarked_attributions.append(index)

    if latched is not None:
        extent = _UNMARKED_EXTENT_OF[latched[1]]
        for index in range(latched[0] + 1, len(lines)):
            mark(index, extent)
    for index in unmarked_attributions:
        for rest in range(index + 1, len(lines)):
            mark(rest, CLIENT_ATTRIBUTION_UNMARKED_EXTENT)

    for first, last in list(_original_runs(classes)):
        found = _signature_start(lines, classes, first, last)
        if found is None:
            continue
        start, signal = found
        for index in range(start, last + 1):
            mark(index, signal)

    for index in _attribution_shaped_kept_lines(lines, classes):
        signals[index] = ATTRIBUTION_SHAPED_UNRECOGNISED

    # A5 governs every classification that moves a line out of the default view: a line may
    # not leave it without a strong structural signal naming why. This is the check, not the
    # claim, and it is what a future change that classifies on a hunch fails against.
    for index, classification in enumerate(classes):
        if classification is SpanClass.ORIGINAL:
            continue
        if signals[index] not in STRONG_STRUCTURAL_SIGNALS:  # pragma: no cover - unreachable
            raise AssertionError(
                f"line {index} was classified {classification.value!r} with signal "
                f"{signals[index]!r}, which is not a strong structural signal; amendment A5 "
                "forbids treating text as prior conversation on anything else"
            )
    return list(zip(classes, signals, strict=True))


def _attribution_shaped_kept_lines(lines: Sequence[str], classes: Sequence[SpanClass]) -> list[int]:
    """`original` lines that look like a quote header and sit above something classified.

    A5's declared-uncertainty clause. The line matched no client template, so A5 keeps it;
    it is directly above something this module *did* classify, so "the sender's own
    sentence" is not certain either. Both facts go in the response: the span stays
    `original` and its signal says the shape was examined.

    A recognised format that survived is a dangling header with nothing under it, which
    `classify_lines` keeps because a lone attribution-shaped line is a sentence. It is not
    *ambiguous* - the template matched - so it is not flagged as such.
    """
    flagged: list[int] = []
    for index, line in enumerate(lines):
        if classes[index] is not SpanClass.ORIGINAL or not line.strip():
            continue
        if not _is_attribution_shaped(line):
            continue
        if _client_attribution_template(line) is not None:
            continue
        following = next(
            (below for below in range(index + 1, len(lines)) if lines[below].strip()), None
        )
        if following is not None and classes[following] is not SpanClass.ORIGINAL:
            flagged.append(index)
    return flagged


def annotate_body(text: str) -> AnnotatedBody:
    """Annotate a plain-text body with classified spans, removing nothing (amendment A7).

    The single entry point that replaces `strip_quotes_and_signature`. There is deliberately
    no function in this module that returns a smaller string than it was given: the deleting
    operation is gone rather than guarded, which is what makes content destruction
    structurally impossible rather than defended against.

    The returned `AnnotatedBody` cannot exist unless its spans tile `text` exactly - the
    containment gate runs in its constructor - so this function either returns every
    character it was given or raises.
    """
    if not text:
        return AnnotatedBody.empty()
    return build_annotation(text, classify_lines(text.split("\n")))


def ambiguous_lines(body: AnnotatedBody) -> int:
    """How many distinct kept lines were attribution-shaped and unrecognised (A5).

    Distinct line *texts* rather than span count, matching round 8's measurement, so the
    number the pipeline puts in a zero-sized `Reduction` means the same thing it did before
    A7 and a change to it is visible as a change.
    """
    seen = {
        line.strip()
        for span in body.spans
        if span.signal == ATTRIBUTION_SHAPED_UNRECOGNISED
        for line in body.text_of(span).split("\n")
        if line.strip()
    }
    return len(seen)


def ambiguity_reason(body: AnnotatedBody) -> str | None:
    """Why a zero-sized reduction is in the payload, in structural terms only.

    Deliberately carries **no mail text**. A reduction record is not fenced, so putting the
    line itself here would place unfenced mail-derived content in the envelope, which
    contract R-09 forbids for exactly the reason it exists.
    """
    if not ambiguous_lines(body):
        return None
    return (
        "attribution-shaped line kept as the sender's own: it matched no recognised client "
        "quote-header format, and amendment A5 keeps text the classifier cannot structurally "
        "identify rather than treating it as prior conversation; 0 characters removed"
    )
