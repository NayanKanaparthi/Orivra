"""Amendment A7's **reported** half: how good is the default view, and where is it wrong.

A7 splits one number into two, and the split is the point:

  * **gated**, in `tests/test_a7_containment.py`: no input character is absent from the
    annotated output. Total, character-level, stated over generated input;
  * **reported, not gated**, here: how often the default view - `original` spans only -
    shows the wrong thing. A misclassification now costs a **view**, not the sentence: the
    text is in `body_clean.text` and `view(list(SpanClass))` returns it exactly.

**It does not cost "one widening", and that framing is wrong** (R-ARCH-029). A reviewer
re-ran round 8's corpus against `ONE_WIDENING` and found all fourteen misclassified entries
still missing a fragment. `test_one_class_wider_does_not_recover_the_misclassified_entries`
below is that measurement, in the suite, so the corrected statement is a number rather than
a paragraph. **What makes A7 downgrade content loss from a blocker is containment - the text
is present and addressable - not that one widening always retrieves it.**

Every number below is asserted at the value it currently measures, with a message saying to
**update the reported figure rather than tune the classifier**. That is deliberate: round 5,
6, 7 and 8 each tuned a rule until a number looked good, and each was defeated by the next
corpus. A moved number here is a fact to report, not a test to make green.

## The numbers this file pins, and how to read them

| measurement | round 8 | round 9 (A7) |
|---|---|---|
| sender prose **destroyed**, four corpora, two positions | 14/254 | **0/254** |
| sender prose **absent from the default view** | 14/254 (same 14, gone) | **14/254 = 5.5%** |
| R-ARCH-026 tagged sender characters destroyed | 1,264/1,264 | **0/1,264** |
| ... absent from the default view | 1,264/1,264 | 1,264/1,264 |
| ... one class wider, **latch corpus only** | not possible | **1,264/1,264** |
| the 14 misclassified prose entries, recovered one class wider | not possible | **0/14** |
| ... recovered by `view(list(SpanClass))` | not possible | **14/14** |
| client headers still shown (false negatives) | 28/161 = 17.4% | 28/161 = 17.4% |

The two 14s are the same fourteen cases: R-ARCH-025's two shapes are **not fixed** this
round and are not claimed to be. What changed is the cost. Nothing was tuned - the classifier
finds exactly the regions round 8's stripper deleted, which is why the default view is
byte-identical to round 8's `body_clean` on all 293 bodies these corpora contain.
"""

from __future__ import annotations

from collections import Counter

import pytest

from mailweave.content.annotate import SpanClass
from mailweave.content.quotes import annotate_body
from tests.fixtures.reply_chains import (
    CORPUS_WEEK,
    DECLARED_FALSE_NEGATIVE_FORMATS,
    LATCH_CORPUS,
    PROSE_CORPORA,
    PROSE_POSITIONS,
    WEEKDAY_NAMES,
    client_headers_for_weekday,
)

#: The view a caller gets one widening past the default. `uncertain` is where the extents no
#: client marked live, so this is the single step that answers "was the sender's text below
#: that unmarked quote?".
#:
#: **Not the recovery guarantee.** It answers that one question, for the latch shape, and it
#: is measured below at 1,264/1,264 for `LATCH_CORPUS` and at **0 of 14** for the
#: misclassified prose entries. The guarantee is `EVERY_CLASS` (R-ARCH-029).
ONE_WIDENING = (SpanClass.ORIGINAL, SpanClass.UNCERTAIN)

#: The recovery guarantee itself: a view over every class returns `body_clean.text` exactly.
#: Built from `SpanClass` rather than listed, so a sixth class cannot silently fall outside
#: the guarantee.
EVERY_CLASS = tuple(SpanClass)


def _place(position: str, line: str) -> str:
    placer, _context = PROSE_POSITIONS[position]
    assert callable(placer)
    return str(placer(line))


def _context(position: str) -> tuple[str, ...]:
    _placer, context = PROSE_POSITIONS[position]
    return context


def _fragments(entry: str) -> list[str]:
    """The non-blank lines of a corpus entry. Entries are multi-line where the shape needs it."""
    return [line for line in entry.split("\n") if line.strip()]


# --- what A7 makes impossible, measured over every corpus rather than argued -------------


@pytest.mark.parametrize("corpus_name", sorted(PROSE_CORPORA))
@pytest.mark.parametrize("position", sorted(PROSE_POSITIONS))
def test_no_sender_sentence_is_destroyed_in_any_corpus_in_any_position(
    corpus_name: str, position: str
) -> None:
    """Four corpora written by three hands, both positions: **zero destroyed.**

    This is the containment gate restated where the last four rounds' failures were
    measured, so the comparison is like for like. Round 8's tree destroyed 14 of these 254;
    R-ARCH-022's tree destroyed 25 of 200; round 6's destroyed 6 of 15.
    """
    corpus = PROSE_CORPORA[corpus_name]
    destroyed = [
        name
        for name, entry in corpus
        if any(
            fragment not in annotate_body(_place(position, entry)).text
            for fragment in _fragments(entry)
        )
    ]
    assert destroyed == [], (
        f"{len(destroyed)} of {len(corpus)} sender-authored entries were destroyed in "
        f"corpus {corpus_name!r}, position {position!r}: {destroyed}. Under amendment A7 no "
        "input text may be absent from the annotated output"
    )


# --- the reported number: default-view quality -------------------------------------------

#: What the default view hides, per corpus and position, measured rather than asserted.
#: The three round-7/8 corpora read zero because A7 changed no classification rule; the
#: fourth reads 7 in each position, which is R-ARCH-025's two shapes and nothing else.
DEFAULT_VIEW_MISSES: dict[tuple[str, str], int] = {
    ("implementer_round_7", "above_quote"): 0,
    ("implementer_round_7", "standalone"): 0,
    ("r_arch_round_7", "above_quote"): 0,
    ("r_arch_round_7", "standalone"): 0,
    ("implementer_round_8", "above_quote"): 0,
    ("implementer_round_8", "standalone"): 0,
    ("r_arch_round_8", "above_quote"): 7,
    ("r_arch_round_8", "standalone"): 7,
}


@pytest.mark.parametrize("corpus_name", sorted(PROSE_CORPORA))
@pytest.mark.parametrize("position", sorted(PROSE_POSITIONS))
def test_the_default_view_miss_rate_is_reported_per_corpus_and_position(
    corpus_name: str, position: str
) -> None:
    """The number itself, per cell, so a move is legible as *which* cell moved.

    A cell that moves is a report to update, **not** a rule to tune. If a later round makes
    `r_arch_round_8` read 0 by narrowing `_header_block_runs`, that is a real improvement and
    the number here changes with it - but a round that narrows the rule to make this green
    and thereby widens some other shape has done exactly what rounds 5 to 8 did.
    """
    corpus = PROSE_CORPORA[corpus_name]
    missed = [
        name
        for name, entry in corpus
        if any(
            fragment not in annotate_body(_place(position, entry)).view()
            for fragment in _fragments(entry)
        )
    ]
    expected = DEFAULT_VIEW_MISSES[(corpus_name, position)]
    assert len(missed) == expected, (
        f"the default view hides {len(missed)} of {len(corpus)} entries in corpus "
        f"{corpus_name!r}, position {position!r} (was {expected}): {missed}. This is a "
        "reported metric - update the figure and say which entries moved, rather than tuning "
        "the classifier until it is green"
    )


def test_the_default_view_miss_rate_is_reported_as_one_number() -> None:
    """5.5% across all four corpora in both positions, and it is not a gate.

    Stated as a whole-corpus rate because that is the form the round-8 comparison takes: the
    same fourteen cases were **destroyed** at 25.9% of R-ARCH's fourth corpus. They are now
    hidden from a view a caller can widen, and the number is here so nobody has to trust a
    handoff for it.
    """
    missed = total = 0
    for corpus in PROSE_CORPORA.values():
        for position in PROSE_POSITIONS:
            total += len(corpus)
            for _name, entry in corpus:
                view = annotate_body(_place(position, entry)).view()
                if any(fragment not in view for fragment in _fragments(entry)):
                    missed += 1
    assert (missed, total) == (14, 254), (
        f"the default-view miss rate moved to {missed} of {total} "
        f"({100 * missed / total:.1f}%); update the reported figure in "
        "docs/reviews/ROUND_09/HANDOFF.md rather than this assertion"
    )


def test_the_collateral_damage_is_reported_and_recovered_by_one_widening() -> None:
    """Round 8 destroyed the paragraph *around* the sentence too. A7 hides it, one class deep.

    R-ARCH-022 and R-ARCH-025 both took the sentence **and** the unrelated paragraph after
    it, which is why the surrounding text is measured separately. Seven of those neighbours
    are outside the default view; every one of them is in the `uncertain` class, so widening
    the view by exactly one class returns all seven.

    **Scope, because the general form of this sentence is false.** This holds for these seven
    *neighbouring* paragraphs. It does **not** hold for the fourteen misclassified entries
    themselves - the test below measures those at 0 of 14 - and the two claims were read
    together as one general guarantee, which R-ARCH-029 corrected.
    """
    default = widened = 0
    for corpus in PROSE_CORPORA.values():
        for position in PROSE_POSITIONS:
            for _name, entry in corpus:
                body = annotate_body(_place(position, entry))
                for neighbour in _context(position):
                    default += neighbour not in body.view()
                    widened += neighbour not in body.view(ONE_WIDENING)
    assert (default, widened) == (7, 0), (
        f"surrounding sentences outside the default view moved to {default} (was 7), and "
        f"{widened} of them are still outside a view widened to include uncertain spans "
        "(was 0)"
    )


# --- R-ARCH-026: does the latch dissolve? -------------------------------------------------


def test_the_latch_no_longer_destroys_anything_it_used_to_destroy() -> None:
    """R-ARCH-026, re-run: **1,264 of 1,264 destroyed becomes 0 of 1,264.**

    Sixteen cases across all three latching signals, in reply-below, sign-off, interleaved
    and postscript positions. Round 8 removed every tagged character; the extent of that
    removal was this repository's judgement rather than a boundary any client wrote, which
    is exactly why it was wrong so consistently.

    A7 does not make the judgement better. It changes what a wrong judgement costs.
    """
    tagged = present = 0
    for name, body_text, fragments in LATCH_CORPUS:
        body = annotate_body(body_text)
        for fragment in fragments:
            tagged += len(fragment)
            if fragment in body.text:
                present += len(fragment)
            else:  # pragma: no cover - the gate makes this unreachable
                pytest.fail(f"{name}: {fragment!r} is absent from body_clean")
    assert (present, tagged) == (1264, 1264), (
        f"{tagged - present} of {tagged} tagged sender characters written below a latching "
        "signal are absent from body_clean; A7 gates this at zero"
    )


def test_the_latch_still_gets_the_default_view_wrong_and_that_is_the_honest_number() -> None:
    """The half of R-ARCH-026 that did **not** dissolve, reported rather than glossed.

    The extent is still judged, on the same three signals, in the same place. So the default
    view of all sixteen cases is still missing the sender's reply - 0 of 1,264 tagged
    characters shown. What changed is that the characters are *present*, which is the
    difference between a wrong view and a lost sentence. One widening happens to return all
    of them **for this corpus**, because every tagged character sits strictly inside an
    unmarked extent by construction; that is a property of the latch shape and not a general
    guarantee, and the test below measures where it does not hold (R-ARCH-029).

    This is the number a reviewer should attack next: it says the classifier's judgement
    about *where a quoted block ends* is wrong in 16 of 16 realistic cases, and A7 makes that
    survivable rather than correct.
    """
    tagged = shown_default = shown_widened = 0
    latched_cases = 0
    for _name, body_text, fragments in LATCH_CORPUS:
        body = annotate_body(body_text)
        latched_cases += body.latched
        for fragment in fragments:
            tagged += len(fragment)
            shown_default += len(fragment) if fragment in body.view() else 0
            shown_widened += len(fragment) if fragment in body.view(ONE_WIDENING) else 0
    assert latched_cases == len(LATCH_CORPUS), "every case in this corpus latches, by construction"
    assert (shown_default, tagged) == (0, 1264), (
        f"the default view now shows {shown_default} of {tagged} tagged characters (was 0); "
        "update the reported figure"
    )
    assert shown_widened == tagged, (
        f"widening the view by one class shows {shown_widened} of {tagged} tagged "
        "characters; for the latch shape specifically this is 1,264/1,264, and it is a "
        "measurement of that shape rather than of A7's guarantee, which is that "
        "view(list(SpanClass)) returns the text (R-ARCH-029)"
    )


def test_one_class_wider_does_not_recover_the_misclassified_entries() -> None:
    """R-ARCH-029, as a measurement rather than as a correction in a document.

    Round 9's handoff claimed "recoverable one class wider" for the seven collateral
    neighbours and for `LATCH_CORPUS`, and both claims are true and both are tested above.
    The **general** reading - that a default-view miss is always one widening from being
    fixed - is false, and the reviewer measured it: re-running round 8's corpus against
    `ONE_WIDENING`, all fourteen misclassified entries still miss a fragment.

    Reproduced here, with the classes named. Eight sit wholly in `quoted` spans, which
    `ONE_WIDENING` was never built to reach. The other six are split by a `forwarded`
    heading line the classifier put in the middle of them, so no *single* widening restores
    the entry whole.

    And the guarantee that **does** hold, asserted in the same test so the two cannot drift
    apart: `view(EVERY_CLASS)` returns all fourteen. That is the basis A7 rests on.
    """
    missed_default = missed_one_wider = recovered_by_every_class = 0
    span_classes: Counter[tuple[str, ...]] = Counter()
    for corpus in PROSE_CORPORA.values():
        for position in PROSE_POSITIONS:
            for _name, entry in corpus:
                body = annotate_body(_place(position, entry))
                if entry in body.view():
                    continue
                missed_default += 1
                if entry not in body.view(ONE_WIDENING):
                    missed_one_wider += 1
                    start = body.text.find(entry)
                    span_classes[
                        tuple(
                            sorted(
                                {
                                    span.classification.value
                                    for span in body.spans
                                    if span.start < start + len(entry) and span.end > start
                                }
                            )
                        )
                    ] += 1
                recovered_by_every_class += entry in body.view(EVERY_CLASS)

    assert (missed_default, missed_one_wider) == (14, 14), (
        f"{missed_one_wider} of {missed_default} default-view misses are still missing one "
        "class wider (was 14 of 14); update the reported figure rather than tuning"
    )
    assert recovered_by_every_class == missed_default, (
        "a view over every span class must return every entry the default view missed; that "
        "is A7's containment guarantee and the only recovery claim that generalises"
    )
    assert span_classes == Counter({("quoted",): 8, ("forwarded", "original", "uncertain"): 6}), (
        f"the shape of the fourteen misses moved: {dict(span_classes)}"
    )


def test_every_latched_region_is_classified_uncertain_rather_than_quoted() -> None:
    """The classifier states what it knows, which is that it does not know where this ends.

    Round 8 called these characters `quoted` and deleted them. Calling them `quoted` and
    keeping them would still be a claim the measurement above shows is wrong 16 times out of
    16. `uncertain` is the honest label, and it is the one that carries a signal naming which
    latching signal opened the region.
    """
    extents = {
        "forward_separator_unmarked_extent",
        "header_block_unmarked_extent",
        "client_attribution_unmarked_extent",
    }
    for name, body_text, fragments in LATCH_CORPUS:
        body = annotate_body(body_text)
        for fragment in fragments:
            covering = [
                span
                for span in body.spans
                if fragment in body.text_of(span)
                or (
                    span.start < body.text.index(fragment) + len(fragment)
                    and span.end > body.text.index(fragment)
                )
            ]
            assert covering, f"{name}: no span covers {fragment!r}"
            for span in covering:
                assert span.classification is SpanClass.UNCERTAIN, (
                    f"{name}: sender text below a latch is classified "
                    f"{span.classification.value!r} on {span.signal!r}; the extent of that "
                    "region was judged, not marked, and the class should say so"
                )
                assert span.signal in extents, f"{name}: unexpected signal {span.signal!r}"


# --- the other reported number: false negatives -------------------------------------------


def _headers_still_shown() -> dict[str, list[str]]:
    """Which client formats leave a header in the default view, and on which weekdays."""
    surviving: dict[str, list[str]] = {}
    for index in range(len(CORPUS_WEEK)):
        for name, header in client_headers_for_weekday(index).items():
            body = f"Two points before Friday.\n\n{header}\n\n> The window moves to Saturday.\n"
            view = annotate_body(body).view()
            lines = [line for line in header.split("\n") if line.strip()]
            if any(line in view for line in lines):
                surviving.setdefault(name, []).append(WEEKDAY_NAMES[index])
    return surviving


def test_the_false_negative_rate_is_unchanged_by_a7_and_still_reported() -> None:
    """28 of 161 = 17.4%, the same four formats, on all seven weekdays.

    A7 changed no detection rule, so this number should not have moved, and a moved number
    here would mean the classification *did* change - which is worth knowing either way.
    Round 7 reported 12.5% from a Tuesday-only corpus and R-ARCH measured 36.8%; the corpus
    spans all seven weekdays precisely so a rate measured against it can be wrong.

    A surviving header costs tokens in the default view. Under A7 it does not cost anything
    else, which is why this stays reported rather than gated.
    """
    surviving = _headers_still_shown()
    assert set(surviving) == set(DECLARED_FALSE_NEGATIVE_FORMATS), (
        f"surviving formats {sorted(surviving)} do not match the declared residue "
        f"{sorted(DECLARED_FALSE_NEGATIVE_FORMATS)}"
    )
    for name, days in sorted(surviving.items()):
        assert len(days) == len(CORPUS_WEEK), (
            f"{name} survives on {days} but not on every weekday: a weekday-dependent result "
            "is the pronoun/calendar collision, not a structural gap (R-ARCH-023)"
        )
    total = len(CORPUS_WEEK) * len(client_headers_for_weekday(0))
    survivors = sum(len(days) for days in surviving.values())
    assert (survivors, total) == (28, 161), (
        f"the false-negative residue moved to {survivors} of {total} "
        f"({100 * survivors / total:.1f}%); update the reported rate rather than this "
        "assertion, and say which formats moved"
    )
