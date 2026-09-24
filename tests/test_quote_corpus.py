"""The quote/signature **classifier** against a realistic reply-chain corpus (H5).

R-ARCH found two defects in realistic - not adversarial - input: Outlook header blocks and
forwards were removed but declared `kind="signature"`, and a corporate signature with no
`--` delimiter was not removed at all and nothing was declared. Both are failures of the
same obligation: `reductions[].kind` and its count are a statement about what happened to
the body, and a downstream reader has nothing else to go on.

**Under amendment A7 nothing here is a removal any more.** The classifier decides which
spans are outside the *default view*, and the text is present either way. So every
assertion below that used to read "this left `body_clean`" now reads "this is not in
`body_clean.view()`", and the two claims that were separable only under a deleting
pipeline - "the classification is right" and "the text still exists" - are separated:

  * the containment gate is `tests/test_a7_containment.py`, over generated input;
  * default-view quality and the false-negative rate are *reported* in
    `tests/test_a7_default_view_quality.py`, which is also where round 8's
    `test_the_false_positive_rate_is_zero_for_every_corpus_in_every_position` and the
    false-negative rate assertions went - they became reported numbers over four corpora
    rather than a gate over three;
  * what stays here is the **classification** itself: which signal fires on which shape,
    and which kind the resulting reduction record carries.

The corpus lives in `tests/fixtures/reply_chains.py`, where each case declares the regions
it expects to keep, to classify as `quoted`, and to classify as `signature`. Every
assertion below is computed from that declaration, so nothing here restates a number the
implementation also hardcodes.
"""

from __future__ import annotations

import pytest

from mailweave.content.annotate import AnnotatedBody, SpanClass
from mailweave.content.html_text import HtmlParserName, html_to_text
from mailweave.content.normalize import normalise
from mailweave.content.quotes import (
    _ATTRIBUTION_VERBS,
    _ATTRIBUTION_VERBS_BY_LOCALE,
    _client_attribution_template,
    ambiguity_reason,
    ambiguous_lines,
    annotate_body,
    looks_quoted,
)
from tests.fixtures.reply_chains import (
    ASSERTED,
    CLIENT_ATTRIBUTION_LINES,
    CORPUS,
    SENDER_AUTHORED_PROSE,
    ReplyCase,
)

#: Every class the default view does not show. "Removed" is the word round 8 used for these
#: characters; under A7 they are classified and present, so the tests below ask whether a
#: fragment is in the *view* rather than whether it survived.
NOT_IN_THE_DEFAULT_VIEW = (
    SpanClass.QUOTED,
    SpanClass.FORWARDED,
    SpanClass.SIGNATURE,
    SpanClass.UNCERTAIN,
)
#: The classes round 8 counted as `quoted_chars`: prior conversation of any kind, including
#: the unmarked extents it deleted under a quoted label.
PRIOR_CONVERSATION = (SpanClass.QUOTED, SpanClass.FORWARDED, SpanClass.UNCERTAIN)


def classified_signals(body: AnnotatedBody) -> tuple[str, ...]:
    """Every signal that put a span outside the default view, sorted and deduplicated."""
    return body.signals(*NOT_IN_THE_DEFAULT_VIEW)


def rendered(body: AnnotatedBody) -> str:
    """The default view as `content/pipeline.py` renders it, for equality assertions.

    Dropping the classified spans leaves the blank lines that sat on either side of them,
    and the pipeline folds those with the same normaliser that produced the body's
    whitespace. Round 8's `StripResult.reply` was stripped and then normalised, so this is
    the like-for-like comparison - and it is the string a caller actually receives.
    """
    return normalise(body.view()).text


def annotate_case(case: ReplyCase) -> AnnotatedBody:
    body = case.body
    if case.html:
        body = html_to_text(body, HtmlParserName.SELECTOLAX).text
    return annotate_body(body)


@pytest.mark.parametrize("case", ASSERTED, ids=lambda case: case.name)
def test_the_reply_survives_and_the_chain_does_not(case: ReplyCase) -> None:
    result = annotate_case(case)
    for keep in case.keeps:
        assert keep in result.view(), f"{case.name}: lost content that must be kept: {keep!r}"
    for removed in case.removable:
        assert removed not in result.view(), f"{case.name}: leaked {removed!r} into body_clean"


@pytest.mark.parametrize("case", ASSERTED, ids=lambda case: case.name)
def test_each_removal_is_declared_under_the_kind_it_actually_is(case: ReplyCase) -> None:
    """R-ARCH-001/002: the count must sit under the right kind, and must exist at all."""
    result = annotate_case(case)
    if case.quoted:
        assert result.chars(*PRIOR_CONVERSATION) > 0, (
            f"{case.name}: quoted content removed with no quoted count"
        )
    if case.signature:
        assert result.chars(SpanClass.SIGNATURE) > 0, (
            f"{case.name}: signature removed with no count"
        )
    if case.quoted and not case.signature:
        assert result.chars(SpanClass.SIGNATURE) == 0, (
            f"{case.name}: prior conversation declared as a signature "
            f"({result.chars(SpanClass.SIGNATURE)} chars) - a false statement about the "
            "class the text is in"
        )
    if case.signature and not case.quoted:
        assert result.chars(*PRIOR_CONVERSATION) == 0, (
            f"{case.name}: a signature declared as quoted content"
        )
    if not case.quoted and not case.signature:
        assert (result.chars(*PRIOR_CONVERSATION), result.chars(SpanClass.SIGNATURE)) == (0, 0), (
            f"{case.name}: removed something from a message with nothing to remove"
        )


@pytest.mark.parametrize("case", CORPUS, ids=lambda case: case.name)
def test_every_character_is_in_exactly_one_class(case: ReplyCase) -> None:
    """The classifier's classes are exhaustive and disjoint over the input.

    Round 8 reconciled four quantities - reply, quoted, signature and the whitespace that
    folded away while re-joining kept lines - against the input length, because deletion
    made the accounting non-trivial. A7 removes the arithmetic rather than checking it:
    every character is in exactly one span, so the per-class counts sum to the input and
    nothing folds away at all.
    """
    body = case.body
    if case.html:
        body = html_to_text(body, HtmlParserName.SELECTOLAX).text
    annotated = annotate_body(body)
    assert annotated.text == body
    assert sum(annotated.classified_chars.values()) == len(body), (
        f"{case.name}: the classes account for {sum(annotated.classified_chars.values())} "
        f"of {len(body)} characters"
    )
    assert annotated.view(list(SpanClass)) == body


def test_the_undelimited_signature_case_that_previously_removed_nothing() -> None:
    """R-ARCH-002 by name: with a `--` delimiter 86 chars went; without one, zero did."""
    from tests.fixtures.reply_chains import SIGNATURE_NO_DELIMITER, SIGNATURE_WITH_DELIMITER

    with_delimiter = annotate_case(SIGNATURE_WITH_DELIMITER)
    without = annotate_case(SIGNATURE_NO_DELIMITER)
    assert with_delimiter.chars(SpanClass.SIGNATURE) > 0
    assert without.chars(SpanClass.SIGNATURE) > 0
    assert "Dana Whitfield" not in without.view()
    assert rendered(without) == SIGNATURE_NO_DELIMITER.keeps[0]


def test_a_sign_off_at_the_top_of_a_message_is_not_a_signature() -> None:
    """The no-delimiter detector needs body above it, or "Thanks," would eat the mail."""
    result = annotate_body("Thanks,\n\nCan you send the revised deck by Friday?\n")
    assert result.chars(SpanClass.SIGNATURE) == 0
    assert "revised deck" in result.view()


def test_a_long_paragraph_after_a_sign_off_word_is_not_a_signature() -> None:
    """The bound is on line length and line count, so prose below a sign-off survives."""
    body = (
        "Here is the summary you asked for.\n"
        "\n"
        "Thanks\n"
        "for pushing on this - the vendor finally sent the corrected schedule, and it "
        "moves both milestones a week earlier than we assumed in the plan.\n"
    )
    result = annotate_body(body)
    assert result.chars(SpanClass.SIGNATURE) == 0
    assert "corrected schedule" in result.view()


def test_looks_quoted_separates_a_header_block_from_a_sign_off() -> None:
    """The predicate R-ARCH-001's fix rests on, attacked directly."""
    assert looks_quoted("From: a@example.com\nSent: Tuesday\nTo: b@example.com")
    assert looks_quoted("-----Original Message-----")
    assert looks_quoted("On Tue, Aug 25, 2026 at 3:14 PM Priya Shah <p@example.com> wrote:")
    assert looks_quoted("> quoted line")
    assert not looks_quoted("-- \nDana Whitfield\nOperations Lead\n+1 555 0100")
    assert not looks_quoted("Sent from my iPhone")
    # One header line is a form, not a quoted block: "Subject: renewal" in prose is common.
    assert not looks_quoted("Subject: renewal - I will confirm the date tomorrow.")


#: What the corpus admits it does not do, by name. Round 1's entry (R-ARCH-003) was closed
#: in round 5; round 6 declares R-ARCH-015's residue. A gap that is fixed has to leave this
#: list, and a gap that appears has to be added to it, which is the whole mechanism.
DECLARED_GAPS = ("client_attribution_without_an_address",)


def test_the_known_gap_list_is_exactly_what_is_declared_open() -> None:
    """A case that cannot be asserted has to say so, and nothing else may.

    Both directions matter. An entry that quietly appears is a regression nobody declared;
    an entry that stays after the behaviour changes is a claim about the stripper that is
    no longer true. `ASSERTED` is still derived from the flag rather than listed by hand.
    """
    assert [case.name for case in CORPUS if case.known_gap is not None] == list(DECLARED_GAPS)
    assert {case.name for case in ASSERTED} == {case.name for case in CORPUS} - set(DECLARED_GAPS)
    for case in CORPUS:
        if case.known_gap is not None:
            assert "A5" in case.known_gap, f"{case.name} does not name the ruling it rests on"


def test_the_declared_gap_still_behaves_exactly_as_it_is_declared_to() -> None:
    """The measured half: the gap is pinned, so a change to it cannot pass unnoticed.

    Round 6's gap was a false *positive* - a sentence deleted. Amendment A5 closed it, and
    the gap that replaces it is a false *negative*: an Outlook attribution carrying a date
    but no address survives into `body_clean`. That is the direction A5 chooses, and it is
    pinned here so a future change to it cannot pass unnoticed either.
    """
    from tests.fixtures.reply_chains import CLIENT_ATTRIBUTION_WITHOUT_AN_ADDRESS as gap

    result = annotate_case(gap)
    assert "On 25/08/2026 15:14, Priya Shah wrote:" in result.view()
    assert "The freeze starts Friday." not in result.view()
    assert result.chars(*PRIOR_CONVERSATION) > 0
    # The ambiguity is declared, not silent: a kept line the stripper could not identify
    # is what the zero-sized reduction exists to make visible (A5).
    assert ambiguous_lines(result) == 1
    assert ambiguity_reason(result) is not None


def test_round_sixs_declared_gap_is_closed_and_the_sentence_survives() -> None:
    """The false positive round 6 pinned, now kept: A5's whole point in one case."""
    from tests.fixtures.reply_chains import ATTRIBUTION_SHAPED_SENTENCE_KEPT as case

    result = annotate_case(case)
    assert "Following our 15:14 call, here is what the vendor wrote:" in result.view()
    assert result.chars(*PRIOR_CONVERSATION) > 0, "the quoted chain behind it must still be removed"


def test_a_sender_sentence_carrying_an_address_and_a_time_survives_a_real_quote() -> None:
    """R-ARCH-015 by name: every piece of round 5's evidence, and still not an attribution.

    A quoted chain is present, the line ends in a colon, it carries an attribution verb, an
    address *and* a time - and it is the sender's own sentence. What round 5 could not see
    is that the address and the time sit *after* the verb, where an attribution line has
    only the sender's name, and that the verb's subject is "I".
    """
    from tests.fixtures.reply_chains import SENDER_SENTENCE_CARRYING_ATTRIBUTION_EVIDENCE as case

    result = annotate_case(case)
    assert rendered(result) == "\n\n".join(case.keeps)
    assert result.chars(*PRIOR_CONVERSATION) > 0, "the quoted chain behind it must still be removed"
    assert result.chars(SpanClass.SIGNATURE) == 0


#: The same trap without the first-person subject, and the two shapes that made round 5's
#: rule look sufficient. Each is a line above a real quoted chain; the value is whether the
#: line survives.
TRAILING_LINE_ABOVE_A_QUOTE: dict[str, tuple[str, bool]] = {
    "sender_sentence_first_person": (
        "As I wrote earlier, check with devops@example.com at 15:14:",
        True,
    ),
    "sender_sentence_evidence_after_the_verb": (
        "On Tuesday I wrote to devops@example.com at 15:14:",
        True,
    ),
    "no_evidence_at_all": ("This is what the vendor wrote:", True),
    "gmail_attribution": (
        "On Tue, Aug 25, 2026 at 3:14 PM Priya Shah <priya@example.com> wrote:",
        False,
    ),
    "dutch_attribution": ("Op 25 aug. 2026 om 15:14 schreef Priya <p@example.com>:", False),
    "italian_attribution": (
        "Il giorno mar 25 ago 2026 alle ore 15:14 Priya <p@example.com> ha scritto:",
        False,
    ),
    "polish_attribution": ("W dniu 25.08.2026 o 15:14 Priya <p@example.com> napisał:", False),
    "swedish_attribution": ("Den tis 25 aug. 2026 kl 15:14 skrev Priya <p@example.com>:", False),
    "finnish_attribution": ("ti 25. elok. 2026 klo 15.14 Priya <p@example.com> kirjoitti:", False),
    "bare_address_attribution": ("priya@example.com wrote:", False),
}


@pytest.mark.parametrize(("name", "case"), sorted(TRAILING_LINE_ABOVE_A_QUOTE.items()))
def test_the_trailing_line_rule_separates_prose_from_client_headers(
    name: str, case: tuple[str, bool]
) -> None:
    """R-ARCH-015 alongside the locales it must not break, over one shared body shape.

    The four locales below the corpus's three are the ones R-ARCH verified independently in
    round 5; they are here because the narrowing this round applies is structural, and a
    structural rule that only works on the three cases somebody wrote fixtures for is not
    structural. The quoted chain is always removed - what varies is the line above it.
    """
    line, survives = case
    body = f"Two points before Friday.\n\n{line}\n\n> The freeze starts Friday.\n"
    result = annotate_body(body)
    assert result.chars(*PRIOR_CONVERSATION) > 0, f"{name}: the quoted chain itself was not removed"
    assert (line in result.view()) is survives, (
        f"{name}: expected the line to {'survive' if survives else 'be removed'}; "
        f"reply is {result.view()!r}"
    )


def test_the_non_english_attribution_line_no_longer_dangles() -> None:
    """R-ARCH-003 by name, in three locales the parser's English-only pattern cannot see.

    Round 1: `reply == "D'accord, allons-y.\n\nLe mar. 25 aout 2026 a 15:14, Priya Shah
    <...> a ecrit :"` - the quoted body was stripped and the header it belongs to was left
    in `body_clean`, declared as neither quote nor noise.
    """
    from tests.fixtures.reply_chains import (
        FRENCH_ATTRIBUTION,
        GERMAN_ATTRIBUTION,
        SPANISH_ATTRIBUTION,
    )

    for case, marker in (
        (FRENCH_ATTRIBUTION, "a écrit"),
        (GERMAN_ATTRIBUTION, "schrieb"),
        (SPANISH_ATTRIBUTION, "escribio"),
    ):
        result = annotate_case(case)
        assert marker not in result.view(), f"{case.name}: attribution line still dangling"
        assert rendered(result) == case.keeps[0]
        assert result.chars(*PRIOR_CONVERSATION) > 0


def test_an_attribution_shaped_sentence_the_sender_wrote_is_kept() -> None:
    """The false positive the detector is narrowed against, in both its shapes.

    One has no quoted chain behind it at all; the other has a real one, so only the
    missing address/date keeps it. Both must survive intact - a stripper that eats the
    sender's own sentence is worse than one that leaves a header behind.
    """
    from tests.fixtures.reply_chains import (
        SENDER_COLON_LINE_ABOVE_A_QUOTE,
        TRAILING_COLON_LINE_WITH_NO_QUOTE,
    )

    alone = annotate_case(TRAILING_COLON_LINE_WITH_NO_QUOTE)
    assert "this is what Marie wrote:" in alone.view()
    assert alone.chars(*PRIOR_CONVERSATION) == 0

    above_a_quote = annotate_case(SENDER_COLON_LINE_ABOVE_A_QUOTE)
    assert "This is what the vendor wrote:" in above_a_quote.view()
    assert "Delivery slips by a week." not in above_a_quote.view()
    assert above_a_quote.chars(*PRIOR_CONVERSATION) > 0


# --- Amendment A5: classify as prior conversation only on a strong structural signal ------
#
# A5 changed this component's default rather than tuning it, and A7 leaves A5 untouched:
# what changed is that a line the rule catches is *outside the default view* rather than
# deleted. So the gate that used to live here - "zero false positives on sender prose,
# three corpora, two positions" - is gone, because the failure it gated cannot occur. Its
# replacement is in two files: `tests/test_a7_containment.py` gates containment over
# generated input, and `tests/test_a7_default_view_quality.py` *reports* the default-view
# miss rate over four corpora including R-ARCH's fourth. Nothing was dropped; a gate that
# cannot fail was replaced by a gate that can and a number that is allowed to be ugly.


def line_above_a_quote(line: str) -> AnnotatedBody:
    """One line, above a real `>` chain: the shape every one of these findings was found in."""
    body = f"Two points before Friday.\n\n{line}\n\n> The freeze starts Friday.\n"
    return annotate_body(body)


@pytest.mark.parametrize(("name", "line"), SENDER_AUTHORED_PROSE, ids=lambda value: value)
def test_sender_authored_prose_stays_in_the_default_view(name: str, line: str) -> None:
    """A5's rule, still true, now measured against the view instead of against survival.

    Each line is the last one above a genuine quoted chain, which is the position every
    version of this detector has been wrong in. Round 6 measured 6 of the first 15 deleted;
    round 7's tree destroyed 25 of 200 across both positions. The sentence must be shown -
    a default view that hides the sender's own words is a bad view, and under A7 that is
    all it is.
    """
    result = line_above_a_quote(line)
    assert line in result.view(), f"{name}: sender-authored prose is outside the default view"
    assert line in result.text, f"{name}: sender-authored prose is absent from body_clean"
    assert result.chars(*PRIOR_CONVERSATION) > 0, f"{name}: the quoted chain was not classified"


@pytest.mark.parametrize(
    ("locale", "client", "line", "survives"),
    CLIENT_ATTRIBUTION_LINES,
    ids=[f"{locale}_{client}" for locale, client, _, _ in CLIENT_ATTRIBUTION_LINES],
)
def test_each_client_attribution_format_behaves_as_measured(
    locale: str, client: str, line: str, survives: bool
) -> None:
    """The other direction, measured per format rather than asserted in aggregate.

    `survives=True` is a declared false negative: the header stays in `body_clean` and
    costs tokens. A5 accepts that cost by name, and pins it here so a change is visible.
    """
    result = line_above_a_quote(line)
    assert result.chars(*PRIOR_CONVERSATION) > 0, (
        f"{locale}/{client}: the quoted chain was not removed"
    )
    assert (line in result.view()) is survives, (
        f"{locale}/{client}: expected the header to "
        f"{'survive' if survives else 'be removed'}; reply is {result.view()!r}"
    )
    if survives:
        assert ambiguous_lines(result) == 1, (
            f"{locale}/{client}: a kept quote-shaped line must be declared, not silent (A5)"
        )


def test_every_locale_the_verb_list_claims_has_a_worked_example() -> None:
    """R-ARCH-020/021: the "ten locales" claim, made derivable instead of asserted.

    Round 6 found `_ATTRIBUTION_VERBS` carried twelve entries and eleven distinct patterns
    - `"skrev"` twice - and that only nine locales had test coverage, so a sentence in the
    documentation was wrong in two independent ways. Both halves are now computed: the
    patterns must be distinct, and every locale in the mapping must appear in the worked
    corpus below.
    """
    assert len(_ATTRIBUTION_VERBS) == len(set(_ATTRIBUTION_VERBS)), (
        "a duplicate attribution verb adds no coverage and inflates the count"
    )
    claimed = set(_ATTRIBUTION_VERBS_BY_LOCALE)
    covered = {locale for locale, _, _, _ in CLIENT_ATTRIBUTION_LINES}
    assert covered == claimed, (
        f"locales claimed but not exercised: {sorted(claimed - covered)}; "
        f"exercised but not claimed: {sorted(covered - claimed)}"
    )
    assert len(_ATTRIBUTION_VERBS_BY_LOCALE) == 10


def test_the_template_recogniser_names_the_format_it_matched() -> None:
    """A5's rule, attacked directly rather than only through the pipeline."""
    assert (
        _client_attribution_template(
            "On Tue, Aug 25, 2026 at 3:14 PM Priya Shah <priya@example.com> wrote:"
        )
        == "lead_in_date_address_verb"
    )
    assert (
        _client_attribution_template(
            "Am Di., 25. Aug. 2026 um 15:14 Uhr schrieb Priya Shah <priya@example.com>:"
        )
        == "lead_in_date_verb_sender_address"
    )
    assert _client_attribution_template("priya@example.com wrote:") == "display_name_address_verb"
    assert (
        _client_attribution_template("Priya Shah <priya@example.com> wrote:")
        == "display_name_address_verb"
    )
    # A clause is not a display name, which is what keeps the bare template off prose.
    assert _client_attribution_template("and here is what devops@example.com wrote:") is None
    # A first-person pronoun anywhere on the line disqualifies it, adverbs included.
    assert (
        _client_attribution_template(
            "On Tue, Aug 25, 2026 at 3:14 PM I finally wrote to <priya@example.com>:"
        )
        is None
    )
    # A calendar date is required, not merely a year or a clock.
    assert _client_attribution_template("On the 2026 renewal, priya@example.com wrote:") is None


def test_an_apple_mail_forward_separator_is_quoted_and_not_a_signature() -> None:
    """R-ARCH-019/020 by name, in both halves of the finding.

    The separator no longer leaks into `body_clean`, and the isolated `From:`/`Date:`
    header lines below it are counted as `quoted` rather than `signature` - the "prior
    conversation declared as a signature" class R-ARCH-001 closed, which reappeared through
    a fragment the parser never flagged.
    """
    from tests.fixtures.reply_chains import APPLE_FORWARDED_MESSAGE as case

    result = annotate_case(case)
    assert rendered(result) == "FYI see below."
    assert "Begin forwarded message:" not in result.view()
    assert result.chars(SpanClass.SIGNATURE) == 0, (
        f"{result.chars(SpanClass.SIGNATURE)} characters of a forwarded header block were "
        "classified as a signature; a forward separator and its headers are prior conversation"
    )
    assert result.chars(*PRIOR_CONVERSATION) > 0


def test_splitting_at_the_separator_keeps_the_line_the_sender_wrote_above_it() -> None:
    """The fix had to be a split, not a reclassification.

    Declaring the whole merged fragment quoted would close the leak by deleting "FYI see
    below." - trading a false negative for the false positive A5 forbids. This is the test
    that fails if someone reaches for the cheaper fix.
    """
    body = (
        "Please read the note below before Friday.\n"
        "\n"
        "Begin forwarded message:\n"
        "\n"
        "From: a@x.example\n"
        "Date: 24 August 2026\n"
        "\n"
        "The window moves.\n"
    )
    result = annotate_body(body)
    assert "Please read the note below before Friday." in result.view()
    assert "The window moves." not in result.view()


# --- R-ARCH-022: A5 governs every deletion path, in every position ---------------------
#
# Round 7's gate was measured against one corpus in one position and passed. The library
# underneath decided deletions on `On.*wrote:$`, a one-line `From|Sent|To|Subject:` match
# and a dash-plus-word prefix, before A5's rule ran, so the measurement was of a path the
# text did not take. What survives that lesson into A7 is the structural half: every span
# outside the default view has to name the signal that put it there, checked over every
# corpus case rather than asserted. The rate itself moved to
# `tests/test_a7_default_view_quality.py`, where it is reported over four corpora.

from mailweave.content.quotes import (  # noqa: E402
    STRONG_STRUCTURAL_SIGNALS,
    classify_lines,
)
from tests.fixtures.reply_chains import (  # noqa: E402
    PROSE_CORPORA,
    PROSE_POSITIONS,
    above_a_quote,
    standalone,
)


def _place(position: str, line: str) -> str:
    placer, _ = PROSE_POSITIONS[position]
    assert callable(placer)
    return str(placer(line))


def _context(position: str) -> tuple[str, ...]:
    _, context = PROSE_POSITIONS[position]
    return context


# Round 8's `test_the_false_positive_rate_is_zero_for_every_corpus_in_every_position` stood
# here. It gated a failure amendment A7 makes impossible, and it gated it over three of the
# four corpora that now exist - the fourth, R-ARCH's, is the one that destroyed 25.9% of
# itself while that test was green. Both halves of it are now elsewhere and both are
# stronger: containment is gated over generated input in `tests/test_a7_containment.py`,
# and the miss rate is reported over all four corpora and both positions in
# `tests/test_a7_default_view_quality.py`, where it reads 14 of 254 and is allowed to.


def test_the_blocker_reproduction_verbatim() -> None:
    """R-ARCH-022's own reproduction, character for character.

    `annotate_body("Thanks for the update on this.\\n\\nOnce the negotiations
    concluded, the legal team wrote:\\n\\nWe should have a decision by end of week either
    way.\\n")` returned `reply == "Thanks for the update on this."` with `quoted_chars=106`
    and `ambiguous_lines=0`: two paragraphs gone, one of them carrying no attribution shape
    at all, and nothing in the response saying anything had happened.
    """
    body = (
        "Thanks for the update on this.\n"
        "\n"
        "Once the negotiations concluded, the legal team wrote:\n"
        "\n"
        "We should have a decision by end of week either way.\n"
    )
    result = annotate_body(body)
    assert "Once the negotiations concluded, the legal team wrote:" in result.view()
    assert "We should have a decision by end of week either way." in result.view()
    assert result.chars(*PRIOR_CONVERSATION) == 0
    assert result.chars(SpanClass.SIGNATURE) == 0
    assert classified_signals(result) == ()


@pytest.mark.parametrize(
    ("name", "body"),
    sorted(
        {
            # the library's HEADER_REGEX: one `To:` line, and the paragraph below it
            "one_header_line": (
                "Thanks for the update.\n"
                "\n"
                "To: whoever reviews this next, please check the totals.\n"
                "\n"
                "The numbers were revised on Friday.\n"
            ),
            # the library's SIG_REGEX: a line beginning with a dash and a word
            "dash_word_prefix": (
                "Here is the change.\n"
                "\n"
                "-1 day change to the schedule, which moves the freeze.\n"
                "\n"
                "We will confirm on Monday.\n"
            ),
            # two lines of the *same* header field is not a block either
            "one_field_twice": (
                "Two notes.\n"
                "\n"
                "Subject: the renewal, which finance approved.\n"
                "Subject: the migration, which is on track.\n"
                "\n"
                "Both land before the freeze.\n"
            ),
        }.items()
    ),
)
def test_the_other_two_shapes_the_library_deleted_underneath_a5(name: str, body: str) -> None:
    """The `HEADER_REGEX` and `SIG_REGEX` halves of R-ARCH-022, and the field-repeat case.

    Each of these deleted the line **and everything below it** in round 7, filed as
    `signature`, with `ambiguous_lines=0`. A single header field is a form or a sentence;
    two lines of the same field is still not a client's header block, which is why the
    block test counts *distinct* fields.
    """
    result = annotate_body(body)
    assert result.chars(*PRIOR_CONVERSATION) == 0, (
        f"{name}: text removed as quoted with no quote in it"
    )
    assert result.chars(SpanClass.SIGNATURE) == 0, f"{name}: text removed as a signature"
    assert classified_signals(result) == ()


def test_every_removed_line_names_the_structural_signal_that_removed_it() -> None:
    """A5 governs every deletion path, checked over the whole corpus rather than asserted.

    The failure this replaces was structural: a deletion decided somewhere A5's rule was
    not. So the classifier records, per line, which signal put it in the class it is in, and
    `classify_lines` refuses to return a non-`original` line carrying none. Here the same
    property is read directly off every corpus case. A7 does not relax it: a line may not
    leave the default view on anything weaker than it could once have been deleted on.
    """
    for case in CORPUS:
        body = case.body
        if case.html:
            body = html_to_text(body, HtmlParserName.SELECTOLAX).text
        for index, (classification, signal) in enumerate(classify_lines(body.split("\n"))):
            if classification is SpanClass.ORIGINAL:
                continue
            assert signal in STRONG_STRUCTURAL_SIGNALS, (
                f"{case.name}: line {index} classified {classification.value!r} with no "
                "strong structural signal - amendment A5 forbids treating text as prior "
                "conversation on anything else"
            )
        result = annotate_body(body)
        removed = result.chars(*PRIOR_CONVERSATION) + result.chars(SpanClass.SIGNATURE)
        assert bool(removed) == bool(classified_signals(result)), (
            f"{case.name}: classified {removed} characters under signals "
            f"{classified_signals(result)} - a classification with no signal, or a signal "
            "with no classification, is a reduction record that does not describe what "
            "happened"
        )


def test_nothing_leaves_the_default_view_without_a_named_structural_signal() -> None:
    """The whole of A5 as one property: no signal, no classification, whatever the wording.

    Every entry of all **four** corpora, as ordinary prose with the sender's own text above
    and below and no quote anywhere. The property is not "these sentences are never
    classified" - R-ARCH-025's shapes are, wrongly, and that is reported rather than hidden.
    It is the structural one: a classification and a signal exist together or not at all, so
    a future change that starts classifying on a hunch has nowhere to put the result.
    """
    for corpus in PROSE_CORPORA.values():
        for name, line in corpus:
            result = annotate_body(standalone(line))
            classified = result.chars(*NOT_IN_THE_DEFAULT_VIEW)
            assert bool(classified) == bool(classified_signals(result)), (
                f"{name}: {classified} characters classified under signals "
                f"{classified_signals(result)}"
            )
            for signal in classified_signals(result):
                assert signal in STRONG_STRUCTURAL_SIGNALS, (
                    f"{name}: prose left the default view on {signal!r}, which amendment A5 "
                    "does not permit"
                )


def test_an_ambiguous_line_is_kept_and_declared_rather_than_resolved_silently() -> None:
    """A5's third clause: unsure means keep the text *and* say so.

    An attribution-shaped line that matches no client format and sits directly above
    something this module did remove is exactly the case A5 says to declare. The line
    stays, the count is one, and the reason names the rule rather than the text.
    """
    line = "On 25/08/2026 15:14, Priya Shah wrote:"
    result = annotate_body(above_a_quote(line))
    assert line in result.view()
    assert ambiguous_lines(result) == 1
    reason = ambiguity_reason(result)
    assert reason is not None
    assert line not in reason, "the reason may not carry mail text (R-09)"
    # And the same line with nothing removed near it is not "ambiguous" - it is prose.
    alone = annotate_body(standalone(line))
    assert ambiguous_lines(alone) == 0
    assert line in alone.view()


# --- R-ARCH-023: the false-negative rate, measured against a corpus that can falsify it --

from tests.fixtures.reply_chains import (  # noqa: E402
    CORPUS_WEEK,
    DECLARED_FALSE_NEGATIVE_FORMATS,
    WEEKDAY_NAMES,
    client_headers_for_weekday,
)


def _surviving_client_headers() -> dict[str, list[str]]:
    """Which client formats leave a header in `body_clean`, and on which weekdays."""
    surviving: dict[str, list[str]] = {}
    for index in range(len(CORPUS_WEEK)):
        for name, header in client_headers_for_weekday(index).items():
            body = f"Two points before Friday.\n\n{header}\n\n> The window moves to Saturday.\n"
            result = annotate_body(body)
            lines = [line for line in header.split("\n") if line.strip()]
            if any(line in result.view() for line in lines):
                surviving.setdefault(name, []).append(WEEKDAY_NAMES[index])
    return surviving


@pytest.mark.parametrize("weekday", range(len(CORPUS_WEEK)), ids=lambda index: WEEKDAY_NAMES[index])
def test_no_client_format_behaves_differently_on_one_weekday(weekday: int) -> None:
    """R-ARCH-023 by name: the collision, as the property it violated.

    A client attribution's weekday abbreviation is a first-person pronoun in a neighbouring
    locale - `Mon`/`mon`, `Mi.`/`mi`, `ma`/`ma`, `ons`/`ons` - and the first-person check
    that disqualifies prose was reading it. A header dated a Monday in en/nl/fi, or a
    Wednesday in de/sv, was silently kept however well-formed it was, on eight of the
    twenty-three formats below.

    The property that fixes it is not "Monday works now": it is that **which day it is
    cannot matter**, because the calendar expression is masked out of the first-person scan
    (`_calendar_masked`). So this compares every weekday against Tuesday, the only day the
    round 7 corpus ever used.
    """
    reference = client_headers_for_weekday(1)  # Tuesday: the round 7 corpus's only day
    today = client_headers_for_weekday(weekday)
    for name in sorted(today):
        body_today = f"A.\n\n{today[name]}\n\n> The window moves.\n"
        body_reference = f"A.\n\n{reference[name]}\n\n> The window moves.\n"
        removed_today = annotate_body(body_today).chars(*PRIOR_CONVERSATION) > 0
        removed_reference = annotate_body(body_reference).chars(*PRIOR_CONVERSATION) > 0
        survives_today = any(
            line in annotate_body(body_today).view()
            for line in today[name].split("\n")
            if line.strip()
        )
        survives_reference = any(
            line in annotate_body(body_reference).view()
            for line in reference[name].split("\n")
            if line.strip()
        )
        assert (removed_today, survives_today) == (removed_reference, survives_reference), (
            f"{name} behaves differently on {WEEKDAY_NAMES[weekday]} than on Tuesday: a "
            "weekday abbreviation is being read as a first-person pronoun (R-ARCH-023)"
        )


def test_the_false_negative_residue_is_exactly_what_is_declared() -> None:
    """The reported half of A5, pinned to its declared shape in both directions.

    False negatives are reported, not gated - a surviving header costs tokens, it does not
    destroy evidence. What *is* asserted is that the residue is the set named in
    `DECLARED_FALSE_NEGATIVE_FORMATS` and no wider, and that each surviving format survives
    on **all seven** weekdays rather than on some of them, because a format that survives
    on four days out of seven is the collision R-ARCH-023 found coming back.
    """
    surviving = _surviving_client_headers()
    assert set(surviving) == set(DECLARED_FALSE_NEGATIVE_FORMATS), (
        f"surviving formats {sorted(surviving)} do not match the declared residue "
        f"{sorted(DECLARED_FALSE_NEGATIVE_FORMATS)}"
    )
    for name, days in sorted(surviving.items()):
        assert len(days) == len(CORPUS_WEEK), (
            f"{name} survives on {days} but not on every weekday: a weekday-dependent "
            "result is the pronoun/calendar collision, not a structural gap (R-ARCH-023)"
        )


def test_the_false_negative_rate_is_reported_as_a_number() -> None:
    """The rate itself, computed from the corpus so a report cannot quote a stale figure.

    Round 7 reported 12.5% from a Tuesday-only corpus; R-ARCH measured 36.8% against a
    corpus that varied the weekday. This measurement is over 7 weekdays x 23 formats = 161
    cases and is the number `docs/reviews/ROUND_08/HANDOFF.md` quotes.
    """
    surviving = _surviving_client_headers()
    total = len(CORPUS_WEEK) * len(client_headers_for_weekday(0))
    survivors = sum(len(days) for days in surviving.values())
    assert total == 161, "the corpus size changed; the reported rate must be recomputed"
    assert survivors == 28, (
        f"the false-negative residue moved to {survivors} of {total} "
        f"({100 * survivors / total:.1f}%); update the handoff's reported rate rather than "
        "this assertion, and say which formats moved"
    )


# --- What the segmenter still gets wrong, declared rather than left to be found ---------


def test_a_latched_region_is_uncertain_and_present_rather_than_deleted() -> None:
    """R-ARCH-026's shape, and what A7 does to it, in one case.

    Three signals have no end the client wrote: a forward separator, a header block, and a
    recognised attribution line with no `>` run under it. Round 8 ran the removal to the end
    of the message on all three, so **sender-authored text written below such a block went
    with it** - R-ARCH measured 1,251 of 1,251 tagged characters destroyed across sixteen
    cases, and `tests/fixtures/reply_chains.py::LATCH_CORPUS` reproduces that at 1,264.

    A7 does not bound the extent any better. It classifies the judged region `uncertain`
    instead of deleting it, so the postscript below is out of the default view and **in
    `body_clean`**, returned by a view over every span class. For this shape one widening
    reaches it too, because the postscript sits strictly inside the unmarked extent - that is
    a property of the latch and not of default-view misses in general (R-ARCH-029). The full
    corpus is measured in `tests/test_a7_default_view_quality.py`; this is the single
    readable case.
    """
    postscript = "P.S. I also need the invoice number."
    latched = annotate_body(
        "Yes.\n"
        "\n"
        "On Tue, Aug 25, 2026 at 3:14 PM Priya <p@x.example> wrote:\n"
        "\n"
        "Can we confirm the date?\n"
        "\n"
        f"{postscript}\n"
    )
    assert latched.latched is True
    assert "client_attribution_unmarked_extent" in latched.signals(SpanClass.UNCERTAIN)
    assert postscript not in latched.view(), "the declared cost: the default view is wrong here"
    assert postscript in latched.text, "and the text is present, which is A7's whole claim"
    assert postscript in latched.view(tuple(SpanClass)), (
        "the guarantee: a view over every class returns it"
    )
    assert postscript in latched.view((SpanClass.ORIGINAL, SpanClass.UNCERTAIN)), (
        "and for a latched extent specifically, one widening reaches it too"
    )

    bounded = annotate_body(
        "Yes.\n"
        "\n"
        "On Tue, Aug 25, 2026 at 3:14 PM Priya <p@x.example> wrote:\n"
        "\n"
        "> Can we confirm the date?\n"
        "\n"
        f"{postscript}\n"
    )
    assert bounded.latched is False
    assert postscript in bounded.view(), (
        "a quoted block the client marked has an end, and the sender's text after it is "
        "the sender's"
    )


def test_an_inline_reply_keeps_every_answer_between_the_quoted_paragraphs() -> None:
    """Why a `>` run and an attribution line do not latch, as a case rather than a comment.

    The round 7 library marked every fragment below a quote header hidden, so an inline
    reply - the sender answering between the quoted paragraphs, which is ordinary mail -
    lost every answer. This is the shape that forbids the cheap fix.
    """
    result = annotate_body(
        "On Tue, Aug 25, 2026 at 3:14 PM Priya <p@x.example> wrote:\n"
        "> Can we confirm the date?\n"
        "Yes, the 14th.\n"
        "> And the invoice?\n"
        "Paid on Friday.\n"
    )
    assert "Yes, the 14th." in result.view()
    assert "Paid on Friday." in result.view()
    assert "Can we confirm the date?" not in result.view()
    assert "And the invoice?" not in result.view()
    assert result.latched is False


def test_a_reduction_names_the_rule_that_classified_the_text() -> None:
    """The signal reaches the response, not just the annotation (A5's declaration half)."""
    from mailweave.content.pipeline import _classification_detail

    bounded = _classification_detail(SpanClass.QUOTED, ("quote_marker",))
    assert "quote_marker" in bounded
    assert "quoted spans classified on" in bounded
    judged = _classification_detail(SpanClass.UNCERTAIN, ("forward_separator_unmarked_extent",))
    assert "forward_separator_unmarked_extent" in judged
    assert "uncertain spans classified on" in judged
    # Every detail says where the text is, because under A7 it is somewhere.
    for detail in (bounded, judged):
        assert "present in body_clean" in detail
