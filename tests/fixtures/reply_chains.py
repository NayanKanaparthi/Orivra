"""A realistic reply-chain corpus for the quote/signature stripper (WS-07, DISC-03).

Every byte here is invented for this repository. No personal email content appears, and
nothing was sanitised from a real mailbox: the shapes are reconstructed from the client
conventions themselves (Gmail attribution lines, Outlook `From:/Sent:/To:/Subject:`
header blocks, `-----Original Message-----`, forward separators, mobile sign-offs) so the
corpus can be published in the repository and re-measured by a reviewer.

Each case declares three regions, and that declaration is what the tests and the
before/after measurement are computed from:

  * `keeps`   - substrings that must survive into `reply`;
  * `quoted`  - substrings that must be removed **and declared `kind="quoted"`**;
  * `signature` - substrings that must be removed and declared `kind="signature"`.

`known_gap` marks a case whose current behaviour is measured and reported rather than
asserted, so the corpus states what is not fixed instead of quietly omitting it. Round 1's
only entry was R-ARCH-003 (non-English attribution lines), closed in round 5; round 6's is
R-ARCH-015's residue, which is a *narrowed* version of the same false positive rather than
a new one. `test_the_known_gap_list_is_exactly_what_is_declared_open` is what stops the
list drifting in either direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReplyCase:
    name: str
    body: str
    keeps: tuple[str, ...]
    quoted: tuple[str, ...] = ()
    signature: tuple[str, ...] = ()
    html: bool = False
    known_gap: str | None = None
    notes: str = ""

    @property
    def removable(self) -> tuple[str, ...]:
        return self.quoted + self.signature


GMAIL_TOP_POST = ReplyCase(
    name="gmail_top_post",
    body=(
        "Yes, ship it on the 14th.\n"
        "\n"
        "On Tue, Aug 25, 2026 at 3:14 PM Priya Shah <priya@example.com> wrote:\n"
        "\n"
        "> Can we confirm the date with the vendor first?\n"
        "> The contract says the 14th but the invoice says the 21st.\n"
    ),
    keeps=("Yes, ship it on the 14th.",),
    quoted=(
        "Can we confirm the date with the vendor first?",
        "The contract says the 14th but the invoice says the 21st.",
    ),
)

OUTLOOK_HEADER_BLOCK = ReplyCase(
    name="outlook_header_block",
    body=(
        "Approved - go ahead and book the room.\n"
        "\n"
        "From: Dana Whitfield <dana@example.com>\n"
        "Sent: Tuesday, 25 August 2026 15:14\n"
        "To: Operations <ops@example.com>\n"
        "Subject: RE: Quarterly review room booking\n"
        "\n"
        "Do we still need the large room for the quarterly review?\n"
        "Facilities want an answer by Thursday.\n"
    ),
    keeps=("Approved - go ahead and book the room.",),
    quoted=(
        "From: Dana Whitfield <dana@example.com>",
        "Do we still need the large room for the quarterly review?",
        "Facilities want an answer by Thursday.",
    ),
    notes="R-ARCH-001: previously removed but declared kind=signature.",
)

ORIGINAL_MESSAGE_SEPARATOR = ReplyCase(
    name="original_message_separator",
    body=(
        "No objection from finance.\n"
        "\n"
        "-----Original Message-----\n"
        "From: Accounts Payable <ap@example.com>\n"
        "Sent: 24 August 2026 09:02\n"
        "To: Finance <finance@example.com>\n"
        "Subject: Invoice 4417\n"
        "\n"
        "Please confirm invoice 4417 can be paid this cycle.\n"
    ),
    keeps=("No objection from finance.",),
    quoted=(
        "-----Original Message-----",
        "Please confirm invoice 4417 can be paid this cycle.",
    ),
)

FORWARDED_MESSAGE = ReplyCase(
    name="forwarded_message",
    body=(
        "Sharing this for visibility.\n"
        "\n"
        "---------- Forwarded message ---------\n"
        "From: Vendor Support <support@vendor.example>\n"
        "Date: Mon, 24 Aug 2026 at 09:02\n"
        "Subject: Maintenance window\n"
        "To: Operations <ops@example.com>\n"
        "\n"
        "The maintenance window moves to Saturday 02:00 UTC.\n"
    ),
    keeps=("Sharing this for visibility.",),
    quoted=(
        "---------- Forwarded message ---------",
        "The maintenance window moves to Saturday 02:00 UTC.",
    ),
    notes="R-ARCH-001: previously removed but declared kind=signature.",
)

MOBILE_SIGNATURE = ReplyCase(
    name="mobile_signature",
    body=(
        "Works for me, book it.\n"
        "\n"
        "Sent from my iPhone\n"
        "\n"
        "On Tue, Aug 25, 2026 at 3:14 PM Priya Shah <priya@example.com> wrote:\n"
        "\n"
        "> Are you free at 11:00 on Thursday?\n"
    ),
    keeps=("Works for me, book it.",),
    quoted=("Are you free at 11:00 on Thursday?",),
    signature=("Sent from my iPhone",),
)

FOUR_LEVEL_NESTING = ReplyCase(
    name="four_level_nesting",
    body=(
        "Confirmed, the 14th it is.\n"
        "\n"
        "On Tue, Aug 25, 2026 at 3:14 PM Priya Shah <priya@example.com> wrote:\n"
        "> Sam, do you agree with the 14th?\n"
        ">\n"
        "> > On Mon, Aug 24, 2026 Sam Okoro <sam@example.com> wrote:\n"
        "> > I would rather we said the 14th.\n"
        "> >\n"
        "> > > Rey Alvarez <rey@example.com> wrote:\n"
        "> > > The vendor proposed the 21st.\n"
        "> > >\n"
        "> > > > The original request named the 7th.\n"
    ),
    keeps=("Confirmed, the 14th it is.",),
    quoted=(
        "Sam, do you agree with the 14th?",
        "I would rather we said the 14th.",
        "The vendor proposed the 21st.",
        "The original request named the 7th.",
    ),
)

SIGNATURE_WITH_DELIMITER = ReplyCase(
    name="signature_with_delimiter",
    body=(
        "Thanks - I have added it to the agenda.\n"
        "\n"
        "-- \n"
        "Dana Whitfield\n"
        "Operations Lead, Northwind Traders\n"
        "+1 555 0100\n"
    ),
    keeps=("Thanks - I have added it to the agenda.",),
    signature=("Dana Whitfield", "Operations Lead, Northwind Traders", "+1 555 0100"),
)

SIGNATURE_NO_DELIMITER = ReplyCase(
    name="signature_no_delimiter",
    body=(
        "The revised numbers are attached; the variance is under two percent.\n"
        "\n"
        "Best regards,\n"
        "Dana Whitfield\n"
        "Operations Lead, Northwind Traders\n"
        "+1 555 0100\n"
        "dana@example.com\n"
    ),
    keeps=("The revised numbers are attached; the variance is under two percent.",),
    signature=(
        "Best regards,",
        "Dana Whitfield",
        "Operations Lead, Northwind Traders",
        "+1 555 0100",
    ),
    notes="R-ARCH-002: previously zero characters removed and nothing declared.",
)

SIGNATURE_NO_DELIMITER_AFTER_QUOTE = ReplyCase(
    name="signature_no_delimiter_after_quote",
    body=(
        "Approved.\n"
        "\n"
        "Kind regards\n"
        "Sam Okoro\n"
        "Facilities\n"
        "\n"
        "On Tue, Aug 25, 2026 at 3:14 PM Priya Shah <priya@example.com> wrote:\n"
        "\n"
        "> Can facilities sign off on the room change?\n"
    ),
    keeps=("Approved.",),
    quoted=("Can facilities sign off on the room change?",),
    signature=("Kind regards", "Sam Okoro", "Facilities"),
)

BARE_QUOTE_NO_ATTRIBUTION = ReplyCase(
    name="bare_quote_no_attribution",
    body=(
        "Agreed on all three points.\n"
        "\n"
        "> We should freeze the schema on Friday.\n"
        "> Migrations land the week after.\n"
    ),
    keeps=("Agreed on all three points.",),
    quoted=(
        "We should freeze the schema on Friday.",
        "Migrations land the week after.",
    ),
)

GREATER_THAN_IN_PROSE = ReplyCase(
    name="greater_than_in_prose",
    body=(
        "The rollout gate is simple:\n"
        "\n"
        "if error_rate > 0.02 we stop, otherwise we continue to the next region.\n"
        "\n"
        "I will write it up tomorrow.\n"
    ),
    keeps=(
        "The rollout gate is simple:",
        "if error_rate > 0.02 we stop",
        "I will write it up tomorrow.",
    ),
    notes="A '>' that is arithmetic, not a quote marker: nothing may be removed here.",
)

HTML_GMAIL_BLOCKQUOTE = ReplyCase(
    name="html_gmail_blockquote",
    body=(
        '<div dir="ltr">Yes, the 14th works.</div>'
        '<div class="gmail_quote">'
        '<div dir="ltr" class="gmail_attr">On Tue, Aug 25, 2026 at 3:14 PM Priya Shah '
        "&lt;priya@example.com&gt; wrote:<br></div>"
        '<blockquote class="gmail_quote">'
        '<div dir="ltr">Can we confirm the date with the vendor first?</div>'
        "</blockquote></div>"
    ),
    keeps=("Yes, the 14th works.",),
    quoted=("Can we confirm the date with the vendor first?",),
    html=True,
)

FRENCH_ATTRIBUTION = ReplyCase(
    name="french_attribution",
    body=(
        "D'accord, allons-y.\n"
        "\n"
        "Le mar. 25 août 2026 à 15:14, Priya Shah <priya@example.com> a écrit :\n"
        "\n"
        "> Peux-tu confirmer la date avec le fournisseur ?\n"
    ),
    keeps=("D'accord, allons-y.",),
    quoted=(
        "Le mar. 25 août 2026 à 15:14",
        "Peux-tu confirmer la date avec le fournisseur ?",
    ),
    notes=(
        "R-ARCH-003: the attribution line used to be left dangling in the reply, "
        "undeclared as either quote or noise. Closed in round 5."
    ),
)

GERMAN_ATTRIBUTION = ReplyCase(
    name="german_attribution",
    body=(
        "Passt, dann machen wir das so.\n"
        "\n"
        "Am Di., 25. Aug. 2026 um 15:14 Uhr schrieb Priya Shah <priya@example.com>:\n"
        "\n"
        "> Koennen wir den Termin bestaetigen?\n"
    ),
    keeps=("Passt, dann machen wir das so.",),
    quoted=("schrieb Priya Shah", "Koennen wir den Termin bestaetigen?"),
    notes="R-ARCH-003: a second locale, so the fix is not a one-language special case.",
)

SPANISH_ATTRIBUTION = ReplyCase(
    name="spanish_attribution",
    body=(
        "De acuerdo, seguimos.\n"
        "\n"
        "El mar, 25 ago 2026 a las 15:14, Priya Shah <priya@example.com> escribio:\n"
        "\n"
        "> Puedes confirmar la fecha con el proveedor?\n"
    ),
    keeps=("De acuerdo, seguimos.",),
    quoted=("escribio:", "Puedes confirmar la fecha con el proveedor?"),
)

ATTRIBUTION_VERB_IN_PROSE = ReplyCase(
    name="attribution_verb_in_prose",
    body=(
        "Two things before Friday.\n"
        "\n"
        "Here is what the policy says about the deadline, in full:\n"
        "\n"
        "Requests arriving after the cutoff move to the following cycle.\n"
    ),
    keeps=(
        "Two things before Friday.",
        "Here is what the policy says about the deadline, in full:",
        "Requests arriving after the cutoff move to the following cycle.",
    ),
    notes=(
        "R-ARCH-003 false-positive guard: a colon-terminated line that introduces text "
        "the sender wrote themselves. Nothing may be removed here."
    ),
)

TRAILING_COLON_LINE_WITH_NO_QUOTE = ReplyCase(
    name="trailing_colon_line_with_no_quote",
    body=("I asked the vendor and this is what Marie wrote:\n"),
    keeps=("this is what Marie wrote:",),
    notes=(
        "R-ARCH-003 false-positive guard: an attribution-shaped last line with no quoted "
        "chain behind it is the sender's own sentence, and stripping it would delete the "
        "only content in the message."
    ),
)

SENDER_COLON_LINE_ABOVE_A_QUOTE = ReplyCase(
    name="sender_colon_line_above_a_quote",
    body=(
        "Two points before Friday.\n"
        "\n"
        "This is what the vendor wrote:\n"
        "\n"
        "> Delivery slips by a week.\n"
    ),
    keeps=("Two points before Friday.", "This is what the vendor wrote:"),
    quoted=("Delivery slips by a week.",),
    notes=(
        "R-ARCH-003 false-positive guard, the hard one: a quoted chain *is* present, so "
        "the caller's guard does not fire, and only the missing address/date keeps the "
        "sender's own line."
    ),
)

SENDER_SENTENCE_CARRYING_ATTRIBUTION_EVIDENCE = ReplyCase(
    name="sender_sentence_carrying_attribution_evidence",
    body=(
        "Two points before Friday.\n"
        "\n"
        "As I wrote earlier, check with devops@example.com at 15:14:\n"
        "\n"
        "> The freeze starts Friday.\n"
    ),
    keeps=(
        "Two points before Friday.",
        "As I wrote earlier, check with devops@example.com at 15:14:",
    ),
    quoted=("The freeze starts Friday.",),
    notes=(
        "R-ARCH-015: the hardest false positive of the three. A real quoted chain is "
        "present, so the caller's `quoted` guard does not fire, and the sender's own "
        "sentence carries an attribution verb, an address and a time - every piece of "
        "evidence round 5 asked for. The whole line was deleted and counted as `quoted`. "
        "What separates it from a client's header is where the evidence sits: an "
        "attribution names when and by whom *before* the verb, and never has a "
        "first-person subject."
    ),
)

ATTRIBUTION_SHAPED_SENTENCE_KEPT = ReplyCase(
    name="attribution_shaped_sentence_kept",
    body=(
        "Two points before Friday.\n"
        "\n"
        "Following our 15:14 call, here is what the vendor wrote:\n"
        "\n"
        "> The freeze starts Friday.\n"
    ),
    keeps=(
        "Two points before Friday.",
        "Following our 15:14 call, here is what the vendor wrote:",
    ),
    quoted=("The freeze starts Friday.",),
    notes=(
        "Round 6's declared gap, closed by amendment A5. The time in the sentence's first "
        "clause sits where a client header puts its date, which is why every word-order "
        "rule removed it. A5 stops asking about word order: the line carries no address "
        "and does not begin with a client's lead-in word, so it is not a recognised "
        "format and the sender keeps their sentence."
    ),
)

PORTUGUESE_ATTRIBUTION = ReplyCase(
    name="portuguese_attribution",
    body=(
        "Confirmado, pode seguir.\n"
        "\n"
        "Em ter., 25 de ago de 2026 às 15:14, Priya Shah <priya@example.com> escreveu:\n"
        "\n"
        "> Podemos confirmar a data com o fornecedor?\n"
    ),
    keeps=("Confirmado, pode seguir.",),
    quoted=(
        "escreveu:",
        "Podemos confirmar a data com o fornecedor?",
    ),
    notes=(
        "R-ARCH-020/021: the tenth locale. `escreveu` was in the verb list from round 5 "
        "and had no worked example, which is how a duplicate `skrev` could make the list "
        "look like ten locales while nine were covered."
    ),
)

APPLE_FORWARDED_MESSAGE = ReplyCase(
    name="apple_forwarded_message",
    body=(
        "FYI see below.\n"
        "\n"
        "Begin forwarded message:\n"
        "\n"
        "From: Vendor Support <support@vendor.example>\n"
        "Date: 24 August 2026 at 09:02:11 BST\n"
        "To: Operations <ops@example.com>\n"
        "Subject: Maintenance window\n"
        "\n"
        "Do we still need the room?\n"
    ),
    keeps=("FYI see below.",),
    quoted=(
        "Begin forwarded message:",
        "From: Vendor Support <support@vendor.example>",
        "Date: 24 August 2026 at 09:02:11 BST",
        "Do we still need the room?",
    ),
    notes=(
        "R-ARCH-019/020: `email_reply_parser` merges the separator into the *reply* "
        "fragment, so the separator leaked into body_clean and the isolated From:/Date: "
        "lines - one header field each, below the two-field bar `looks_quoted` uses - were "
        "filed as `signature`. Fixed by splitting the fragment at the separator rather "
        "than reclassifying it whole, which would have deleted 'FYI see below.'"
    ),
)

CLIENT_ATTRIBUTION_WITHOUT_AN_ADDRESS = ReplyCase(
    name="client_attribution_without_an_address",
    body=(
        "Two points before Friday.\n"
        "\n"
        "On 25/08/2026 15:14, Priya Shah wrote:\n"
        "\n"
        "> The freeze starts Friday.\n"
    ),
    keeps=("Two points before Friday.",),
    quoted=("The freeze starts Friday.",),
    known_gap=(
        "Amendment A5's accepted false negative, measured rather than hidden. Some Outlook "
        "builds emit an attribution carrying a date but no address. A5 requires an address "
        "on the line before anything may be deleted, because dropping that requirement is "
        "what puts 'On 25 August 2026 the vendor wrote:' - a sentence a person writes - "
        "back in range. The header survives into body_clean, the quoted chain below it is "
        "still removed, and the response carries a zero-sized `quoted` reduction saying a "
        "line was kept because no client format matched. Costs tokens; destroys nothing."
    ),
)

CORPUS: tuple[ReplyCase, ...] = (
    GMAIL_TOP_POST,
    OUTLOOK_HEADER_BLOCK,
    ORIGINAL_MESSAGE_SEPARATOR,
    FORWARDED_MESSAGE,
    MOBILE_SIGNATURE,
    FOUR_LEVEL_NESTING,
    SIGNATURE_WITH_DELIMITER,
    SIGNATURE_NO_DELIMITER,
    SIGNATURE_NO_DELIMITER_AFTER_QUOTE,
    BARE_QUOTE_NO_ATTRIBUTION,
    GREATER_THAN_IN_PROSE,
    HTML_GMAIL_BLOCKQUOTE,
    FRENCH_ATTRIBUTION,
    GERMAN_ATTRIBUTION,
    SPANISH_ATTRIBUTION,
    ATTRIBUTION_VERB_IN_PROSE,
    TRAILING_COLON_LINE_WITH_NO_QUOTE,
    SENDER_COLON_LINE_ABOVE_A_QUOTE,
    SENDER_SENTENCE_CARRYING_ATTRIBUTION_EVIDENCE,
    ATTRIBUTION_SHAPED_SENTENCE_KEPT,
    PORTUGUESE_ATTRIBUTION,
    APPLE_FORWARDED_MESSAGE,
    CLIENT_ATTRIBUTION_WITHOUT_AN_ADDRESS,
)

#: Amendment A5's gated corpus: sentences a person writes, each carrying an attribution
#: verb and the "evidence" every earlier rule keyed on - an address, a time, a year, or
#: several. **Zero** of these may be removed. The first fifteen reproduce the shape
#: R-ARCH measured in round 6, where 6 of 15 were deleted; the rest are written against
#: the round-7 rule itself, including the two shapes that defeated round 6's first-person
#: check (an adverb between the pronoun and the verb, and a first-person *plural* subject)
#: and four that begin with a client's own lead-in word.
#:
#: Every line here is invented for this repository. No personal mail content appears.
SENDER_AUTHORED_PROSE: tuple[tuple[str, str], ...] = (
    ("per_our_call", "Per our 15:14 call, here is what the customer wrote:"),
    ("following_up", "Following up on the 09:02 handover, the vendor wrote:"),
    ("as_agreed", "As agreed on 12 August 2026, the auditor wrote:"),
    (
        "quoting_a_ticket",
        "Quoting the ticket that ops@example.com raised at 11:30, the customer wrote:",
    ),
    ("for_the_record", "For the record, at 15:14 the supplier wrote:"),
    ("attaching_a_note", "Attaching the note finance@example.com wrote:"),
    ("below_is_the_paragraph", "Below is the paragraph legal wrote at 09:45:"),
    ("renewal_thread", "In the 2026 renewal thread, the account manager wrote:"),
    (
        "after_the_escalation",
        "After the 15:14 escalation to support@vendor.example, the duty engineer wrote:",
    ),
    ("exact_wording", "Here is the exact wording the PMO wrote on 25 August 2026:"),
    (
        "summarising",
        "Summarising what procurement@example.com wrote earlier today at 16:20:",
    ),
    ("closing_the_loop", "To close the loop on the 2026 audit, the reviewer wrote:"),
    ("recapping_standup", "Recapping the 08:30 stand-up, the release manager wrote:"),
    ("copying_in", "Copying in what the customer wrote to billing@example.com at 14:05:"),
    ("roadmap_thread", "On the 2026 roadmap thread, the product lead wrote:"),
    # R-ARCH-019's two defeats of round 6's first-person check.
    (
        "adverb_between_subject_and_verb",
        "I checked with devops@example.com at 15:14 and then wrote back:",
    ),
    (
        "adverb_and_reordered_clause",
        "Yesterday at 15:14 I emailed devops@example.com and later wrote a follow-up:",
    ),
    ("first_person_plural", "At 15:14 we wrote to devops@example.com confirming the freeze:"),
    ("first_person_adjacent", "As I wrote earlier, check with devops@example.com at 15:14:"),
    ("first_person_lead_in", "On Tuesday I wrote to devops@example.com at 15:14:"),
    # Lines that open with a client's own lead-in word.
    ("lead_in_with_a_year", "On 25 August 2026 the vendor wrote:"),
    ("lead_in_with_a_clock_and_address", "On the 15:14 bridge call, priya@example.com wrote:"),
    ("lead_in_with_a_year_and_address", "On the 2026 renewal, priya@example.com wrote:"),
    ("lower_case_lead_in_clause", "and here is what devops@example.com wrote:"),
    # The two round-5 fixtures, restated as bare lines.
    ("no_evidence_at_all", "This is what the vendor wrote:"),
    ("vendor_hearsay", "I asked the vendor and this is what Marie wrote:"),
    # Non-English prose using the same verbs, with first-person subjects and evidence.
    ("french_prose", "Le point important que Marie a écrit à 15:14 est le suivant :"),
    ("german_prose", "Am Dienstag um 15:14 schrieb ich an devops@example.com:"),
    ("dutch_prose", "Op verzoek van ops@example.com schreef ik om 15:14 het volgende:"),
    ("spanish_prose", "El resumen que escribio el proveedor a las 15:14 es este:"),
    ("swedish_prose", "Vi skrev till support@vendor.example klockan 15:14 om detta:"),
    ("italian_prose", "Il giorno 25 ago 2026 ho scritto a support@vendor.example questo:"),
    # Round 6's declared gap, and two ordinary colon-terminated lines.
    ("following_our_call", "Following our 15:14 call, here is what the vendor wrote:"),
    ("policy_quote", "Here is what the policy says about the deadline, in full:"),
    ("rollout_gate", "The rollout gate is simple:"),
    ("two_points", "Two points before Friday, both from the 2026 plan:"),
)

#: The other direction: one worked attribution line per locale the verb list claims, plus
#: the English variants clients actually emit. `survives=True` marks A5's accepted false
#: negatives - measured and reported, never gated (amendment A5's measurement clause).
CLIENT_ATTRIBUTION_LINES: tuple[tuple[str, str, str, bool], ...] = (
    (
        "en",
        "gmail",
        "On Tue, Aug 25, 2026 at 3:14 PM Priya Shah <priya@example.com> wrote:",
        False,
    ),
    ("en", "apple_mail", "On 25 Aug 2026, at 15:14, Priya Shah <priya@example.com> wrote:", False),
    ("en", "bare_address", "priya@example.com wrote:", False),
    ("en", "display_name", "Priya Shah <priya@example.com> wrote:", False),
    ("en", "outlook_no_address", "On 25/08/2026 15:14, Priya Shah wrote:", True),
    ("en", "gmail_no_address", "On Tue, Aug 25, 2026 at 3:14 PM Priya Shah wrote:", True),
    (
        "fr",
        "gmail",
        "Le mar. 25 août 2026 à 15:14, Priya Shah <priya@example.com> a écrit :",
        False,
    ),
    (
        "es",
        "gmail",
        "El mar, 25 ago 2026 a las 15:14, Priya Shah <priya@example.com> escribió:",
        False,
    ),
    (
        "pt",
        "gmail",
        "Em ter., 25 de ago de 2026 às 15:14, Priya Shah <priya@example.com> escreveu:",
        False,
    ),
    (
        "es",
        "gmail_unaccented",
        "El mar, 25 ago 2026 a las 15:14, Priya Shah <priya@example.com> escribio:",
        False,
    ),
    (
        "de",
        "gmail",
        "Am Di., 25. Aug. 2026 um 15:14 Uhr schrieb Priya Shah <priya@example.com>:",
        False,
    ),
    (
        "it",
        "gmail",
        "Il giorno mar 25 ago 2026 alle ore 15:14 Priya <priya@example.com> ha scritto:",
        False,
    ),
    ("nl", "gmail", "Op 25 aug. 2026 om 15:14 schreef Priya <priya@example.com>:", False),
    ("pl", "gmail", "W dniu 25.08.2026 o 15:14 Priya <priya@example.com> napisał:", False),
    ("sv", "gmail", "Den tis 25 aug. 2026 kl 15:14 skrev Priya <priya@example.com>:", False),
    ("fi", "gmail", "ti 25. elok. 2026 klo 15.14 Priya <priya@example.com> kirjoitti:", False),
)


ASSERTED: tuple[ReplyCase, ...] = tuple(case for case in CORPUS if case.known_gap is None)


@dataclass(frozen=True)
class CaseMeasurement:
    """What one corpus case produced, in numbers a report can print."""

    name: str
    quoted_chars: int
    signature_chars: int
    leaked_chars: int
    dropped_chars: int
    misclassified: tuple[str, ...] = field(default_factory=tuple)

    @property
    def clean(self) -> bool:
        return self.leaked_chars == 0 and self.dropped_chars == 0 and not self.misclassified


# --- Amendment A5, round 8: three independent prose corpora in two positions -----------
#
# Round 7 gated on "zero false positives on sender-authored prose" and measured 0 of 36.
# R-ARCH wrote its own corpus, measured 0 of 36 as well - and then tried a position the
# harness never tried, and destroyed five ordinary sentences with no ambiguity flag
# (R-ARCH-022). Both measurements were right about the path this repository built and
# wrong about the path the text actually travelled, because `email_reply_parser` decided
# the deletion before amendment A5's rule ran.
#
# So the measurement now takes three corpora written by three different hands and runs
# each of them in **both** positions. One corpus and one position is what the round 7
# result was, and it is exactly the shape of evidence that failed.

#: R-ARCH's round 7 corpus, transcribed from `docs/reviews/ROUND_07/R-ARCH.md` §1a.
#:
#: **A discrepancy, recorded rather than smoothed over.** That section reports "0/36" and
#: "72/72 kept", and its table lists **35** distinct sentences (8 corporate + 5 meeting
#: notes + 5 address/time + 5 forward-described + 6 first-person-with-adverbs + 6
#: non-English). Every sentence published there is below; the missing 36th is not
#: recoverable from the report, and inventing one to make the arithmetic close would be
#: the kind of tidying this project exists to refuse. The rate is therefore reported over
#: 35, and it is zero.
R_ARCH_ROUND_7_PROSE: tuple[tuple[str, str], ...] = (
    # corporate prose
    (
        "ra_vendor_mentioned",
        "The vendor mentioned in their reply that the shipment would arrive a week early.",
    ),
    (
        "ra_marketing_flagged",
        "Marketing flagged a concern about the launch date during yesterday's sync.",
    ),
    (
        "ra_legal_noted",
        "Legal noted that the indemnification clause needs another look before signing.",
    ),
    (
        "ra_customer_wrote_back",
        "The customer wrote back this morning to confirm the renewal terms.",
    ),
    ("ra_account_manager", "Our account manager replied to say the invoice had already been paid."),
    ("ra_it_confirmed", "IT confirmed the migration window will not affect production traffic."),
    ("ra_auditor_raised", "The auditor raised a question about the Q3 numbers during the call."),
    (
        "ra_procurement_responded",
        "Procurement responded that the new vendor contract is still under review.",
    ),
    # meeting notes quoting a colleague
    ("ra_standup", "In standup, Priya noted that the API changes are blocking two other teams."),
    ("ra_retro", "During the retro, Sam mentioned the deploy pipeline had been flaky all week."),
    (
        "ra_planning",
        "Dana pointed out in the planning meeting that the estimate was too optimistic.",
    ),
    ("ra_notes_say", "The notes say Rey flagged the schema migration as risky before the freeze."),
    (
        "ra_minutes",
        "According to the meeting minutes, finance asked for the revised budget by Friday.",
    ),
    # an address and a time mid-paragraph
    (
        "ra_ops_window",
        "I checked with ops@example.com around 15:14 and they confirmed the window holds.",
    ),
    (
        "ra_ticket_reassigned",
        "The ticket was reassigned to support@vendor.example just after 09:02 this morning.",
    ),
    ("ra_billing_loop", "We looped in billing@example.com at 14:05 to clarify the discrepancy."),
    (
        "ra_procurement_called",
        "Someone from procurement@example.com called around 11:30 about the renewal.",
    ),
    (
        "ra_escalation",
        "The escalation went to devops@example.com at 15:14, and they are on it now.",
    ),
    # a forward or a reply described in passing
    ("ra_forwarding", "I'm forwarding this thread so you have the full context before Monday."),
    ("ra_sharing_reply", "Sharing the vendor's reply below in case it's useful for the audit."),
    ("ra_looping_in", "Looping you in on the earlier exchange with finance about the invoice."),
    ("ra_passing_along", "Passing along the note from support since it affects our rollout plan."),
    ("ra_replying_all", "Replying all here so the rest of the team sees the updated timeline."),
    # first person and first-person plural, adverbs intervening
    (
        "ra_quickly_checked",
        "I quickly checked with devops@example.com and then replied with the all-clear.",
    ),
    (
        "ra_carefully_reviewed",
        "We carefully reviewed the contract yesterday and eventually signed off on it.",
    ),
    (
        "ra_briefly_spoke",
        "Earlier today I briefly spoke with the vendor and immediately followed up in writing.",
    ),
    (
        "ra_already_discussed",
        "We had already discussed this on Tuesday and subsequently agreed to the new date.",
    ),
    (
        "ra_circled_back",
        "I later circled back with legal and promptly confirmed the clause was fine.",
    ),
    (
        "ra_jointly_reviewed",
        "We jointly reviewed the proposal this morning and quietly flagged two issues.",
    ),
    # non-English
    ("ra_romanian", "Am verificat rapid cu furnizorul si apoi am raspuns echipei."),
    ("ra_french", "J'ai verifie rapidement avec le fournisseur avant de repondre a l'equipe."),
    (
        "ra_german",
        "Wir haben gestern kurz mit dem Kunden gesprochen und danach schriftlich geantwortet.",
    ),
    ("ra_italian", "Ho controllato velocemente con il fornitore e poi ho risposto al team."),
    ("ra_spanish", "Hemos revisado cuidadosamente el contrato y luego confirmamos por escrito."),
    ("ra_portuguese", "Verificamos rapidamente com o fornecedor antes de responder a equipa."),
)

#: The round 8 corpus, written against the segmenter this round replaced the library with
#: rather than against the one that failed. Three things it attacks that neither earlier
#: corpus does:
#:
#:   * the three shapes the library deleted underneath amendment A5 - a sentence opening
#:     `On`, a paragraph opening `To:`/`From:`/`Subject:`, and a line opening with a dash
#:     or an underscore (R-ARCH-022's reproduction, plus variants);
#:   * the calendar mask this round added for R-ARCH-023: prose carrying a real weekday, a
#:     real date, a real address, a terminal colon **and** a first-person subject outside
#:     the date, in five locales. If the mask reached past the calendar expression these
#:     would be deleted;
#:   * sign-off words and quote markers used as ordinary vocabulary.
#:
#: Every line is invented for this repository. No personal mail content appears.
ROUND_8_PROSE: tuple[tuple[str, str], ...] = (
    # R-ARCH-022: what the library's QUOTE_HDR_REGEX 'On.*wrote:$' destroyed.
    ("r8_negotiations", "Once the negotiations concluded, the legal team wrote:"),
    ("r8_third_follow_up", "Only after the third follow-up, the vendor finally wrote:"),
    ("r8_incident_bridge", "One of the engineers on the incident bridge wrote:"),
    (
        "r8_reseller_chapter",
        "Ongoing talks with the reseller wrote a new chapter for the account, the rep wrote:",
    ),
    ("r8_on_balance", "On balance, and after two revisions, the steering group wrote:"),
    ("r8_only_yesterday", "Only yesterday the account manager wrote:"),
    # R-ARCH-022: what the library's one-line HEADER_REGEX destroyed.
    ("r8_to_whoever", "To: whoever reviews this next, please check the totals before Friday."),
    ("r8_subject_renewal", "Subject: renewal - I will confirm the date with the vendor tomorrow."),
    ("r8_from_the_look", "From: the look of the numbers, the variance is a rounding difference."),
    ("r8_sent_by_courier", "Sent: the contract by courier this morning, so it lands on Thursday."),
    # R-ARCH-022: what the library's SIG_REGEX prefix test destroyed.
    (
        "r8_minus_one_day",
        "-1 day on the schedule moves the freeze to the Thursday before the break.",
    ),
    ("r8_dash_aside", "-- the reseller's words, not mine -- the migration is on track for Friday."),
    (
        "r8_dunder_init",
        "__init__ raised before the retry ran, which is why the overnight job stalled.",
    ),
    (
        "r8_sent_from_dublin",
        "Sent from the Dublin office, the revised totals are attached to this note.",
    ),
    # R-ARCH-023: a full calendar date, an address, a terminal colon, first person.
    (
        "r8_monday_first_person",
        "On Mon, 24 Aug 2026 I wrote to priya@example.com and this is what came back:",
    ),
    (
        "r8_wednesday_first_person_plural",
        "On Wed, 26 Aug 2026 we emailed support@vendor.example with the following:",
    ),
    (
        "r8_german_wednesday",
        "Am Mi., 26. Aug. 2026 um 15:14 schrieb ich an devops@example.com Folgendes:",
    ),
    (
        "r8_dutch_monday",
        "Op ma 24 aug. 2026 om 15:14 schreef ik aan ops@example.com het volgende:",
    ),
    (
        "r8_swedish_wednesday",
        "Den ons 26 aug. 2026 kl 15:14 skrev vi till support@vendor.example detta:",
    ),
    (
        "r8_finnish_monday",
        "ma 24. elok. 2026 klo 15.14 meidän tiimi kirjoitti ops@example.com seuraavaa:",
    ),
    # Ordinary prose that carries every piece of evidence a client header carries.
    (
        "r8_summary_colon",
        "Here is the summary from 25 August 2026, sent to ops@example.com, in full:",
    ),
    (
        "r8_plan_colon",
        "The 2026 plan, as agreed on 12 August 2026 with finance@example.com, says:",
    ),
    ("r8_two_dates", "Two dates matter here, 24 Aug 2026 and 26 Aug 2026, for this reason:"),
    # Sign-off words and quote markers as ordinary vocabulary.
    ("r8_thanks_to", "Thanks to the vendor's engineer, the migration finished two hours early."),
    ("r8_best_of_three", "Best of the three options is the one procurement recommended on Friday."),
    ("r8_regards_from", "Regards from the Dublin office are attached to the summary below."),
    ("r8_error_rate", "The gate is simple: if error_rate > 0.02 we stop and page the on-call."),
    ("r8_shipped_after_delays", "We shipped -- after two delays -- on the 14th, as the plan said."),
    # The ordinal-date spelling this round declares as a gap rather than closing: if a
    # later round teaches `_WHEN_PATTERN` to read "24th August 2026", this is the sentence
    # it has to keep, and it is here before the change rather than after it.
    ("r8_ordinal_date_call", "On the 24th August 2026 call, priya@example.com wrote:"),
)

#: R-ARCH's round-8 fourth corpus, **reconstructed** from `docs/reviews/ROUND_08/R-ARCH.md`
#: §3 and §6. The reviewer's own file lived outside this tree
#: (`/tmp/mailweave-review/latch/r_arch_round8_corpus.py`) and was never committed, so this
#: is written from the published description rather than copied: 27 entries, the two shapes
#: R-ARCH names as destructive (two consecutive prose lines opening with different
#: header-field names; a bare, dash-free "Original Message"/"Forwarded Message" used as a
#: person's own section heading), the calendar-masked first-person attacks in the locales
#: R-ARCH says round 8's corpus does not cover, and the vocabulary collisions it lists
#: (`cc'd`, `subject to`, `reply-to`, `cheers`, `date night`).
#:
#: **The reconstruction was validated before it was trusted.** Run against round 8's
#: stripper it destroys **14 of 54 = 25.9%** - R-ARCH's exact published figure - through
#: exactly 7 entries in both positions, matching "the other 20 of 27 sentences survive
#: correctly". Two entries carry the reviewer's verbatim reproductions. It is not
#: character-identical to R-ARCH's file and does not claim to be; what it reproduces is the
#: measurement, which is what the corpus is for.
#:
#: Entries are multi-line where the shape needs it: one header-field-shaped line is prose
#: and correctly survives, and it takes two consecutive ones to trip the block detector.
#:
#: Every line is invented for this repository. No personal mail content appears.
R_ARCH_ROUND_8_PROSE: tuple[tuple[str, str], ...] = (
    # -- two consecutive prose lines that begin with header-field names -----------------
    (
        "ra8_recap_to_from",
        "To: recap, we need three approvals before Friday.\n"
        "From: what I can tell, the budget already covers this.",
    ),
    (
        "ra8_memo_subject_date",
        "Subject: the renewal, which finance signed off yesterday.\n"
        "Date: still to be confirmed with the vendor's account team.",
    ),
    (
        "ra8_notes_cc_to",
        "Cc: everyone on the steering group, so nobody is surprised.\n"
        "To: be clear, the migration window has not moved.",
    ),
    (
        "ra8_checklist_from_sent",
        "From: the numbers alone this looks like a rounding difference.\n"
        "Sent: the corrected sheet to procurement this morning.",
    ),
    # -- a bare, dashless section heading a person wrote themselves ---------------------
    (
        "ra8_bare_original_message_heading",
        "Recap below.\n"
        "\n"
        "Original Message\n"
        "\n"
        "We agreed to renew at the same rate, and I still think that was the right call.",
    ),
    (
        "ra8_bare_forwarded_message_heading",
        "Here is the shape of it.\n"
        "\n"
        "Forwarded Message\n"
        "\n"
        "The vendor moved the freeze to the Thursday before the break.",
    ),
    (
        "ra8_bare_begin_forwarded_heading",
        "Two notes on process.\n"
        "\n"
        "Begin forwarded message:\n"
        "\n"
        "We should write the summary before the review rather than after it.",
    ),
    # -- calendar-masked first person in locales the round-8 corpus does not cover ------
    (
        "ra8_italian_first_person",
        "Il giorno mar 25 ago 2026 alle ore 15:14 io ho scritto a priya@example.com questo:",
    ),
    (
        "ra8_polish_first_person",
        "W dniu 25.08.2026 o 15:14 ja napisałem do priya@example.com nastepujace:",
    ),
    (
        "ra8_portuguese_first_person",
        "Em 25 de ago de 2026, eu escrevi para priya@example.com o seguinte:",
    ),
    (
        "ra8_spanish_first_person_plural",
        "El 25/08/2026 nosotros escribimos a priya@example.com lo siguiente:",
    ),
    # -- vocabulary collisions -----------------------------------------------------------
    ("ra8_ccd_the_team", "I cc'd the whole team on the vendor's last note about the freeze."),
    ("ra8_subject_to", "The discount is subject to the volume commitment finance agreed."),
    ("ra8_reply_to", "There is no reply-to address on that alias, so responses bounce."),
    ("ra8_cheers_from_dublin", "Cheers from the Dublin office reached us before the numbers did."),
    ("ra8_date_night", "The date night joke in the standup notes was not about the deadline."),
    # -- ordinary memo prose --------------------------------------------------------------
    (
        "ra8_three_approvals",
        "Three approvals are outstanding and all of them are with procurement.",
    ),
    ("ra8_budget_covers", "The budget already covers the extra seats we discussed on Tuesday."),
    ("ra8_push_back", "I think we should push back on the price before signing anything."),
    ("ra8_same_rate", "We agreed to renew at the same rate, which was the right call."),
    ("ra8_legal_signoff", "Can we get legal's sign-off before this goes out on Thursday?"),
    ("ra8_marketing_line", "The marketing line item still looks too low against last year."),
    ("ra8_timeline_agree", "I agree with the timeline but the staffing assumption is thin."),
    ("ra8_window_moves", "The migration window moves a week earlier than the plan assumed."),
    ("ra8_invoice_number", "I also need the invoice number before finance can close the month."),
    ("ra8_totals_checked", "Whoever reviews this next should check the totals against the sheet."),
    ("ra8_decision_friday", "A decision by end of week either way would unblock the schedule."),
)


#: The four corpora, by the hand that wrote each. Under amendment A7 none of them gates
#: anything: no sentence in any of them can be destroyed, because nothing is deleted. What
#: they measure now is **default-view quality** - which of these sentences the default view
#: gets wrong - and that number is reported in `tests/test_a7_default_view_quality.py`
#: rather than gated, because a wrong default view costs a **view** and not the sentence: the
#: text is in `body_clean.text` and `view(list(SpanClass))` returns it. Deliberately not "a
#: widening" - all fourteen of the entries the default view gets wrong are still incomplete
#: one class wider, measured in that file (R-ARCH-029).
PROSE_CORPORA: dict[str, tuple[tuple[str, str], ...]] = {
    "implementer_round_7": SENDER_AUTHORED_PROSE,
    "r_arch_round_7": R_ARCH_ROUND_7_PROSE,
    "implementer_round_8": ROUND_8_PROSE,
    "r_arch_round_8": R_ARCH_ROUND_8_PROSE,
}


def above_a_quote(line: str) -> str:
    """`line` as the last thing above a real `>` chain - round 7's only tested position."""
    return f"Two points before Friday.\n\n{line}\n\n> The freeze starts Friday.\n"


def standalone(line: str) -> str:
    """`line` as ordinary prose, sender's text above **and** below, no quote anywhere.

    The position R-ARCH tried and the round 7 harness never did. It is the more common
    shape of the two, and it is where the library's own regexes destroyed the sentence and
    the unrelated paragraph after it (R-ARCH-022).
    """
    return (
        "Thanks for the update on this.\n"
        "\n"
        f"{line}\n"
        "\n"
        "We should have a decision by end of week either way.\n"
    )


#: The two placements every corpus is measured in. The value is the surrounding text that
#: must survive alongside the sentence itself, which is what caught R-ARCH-022: the library
#: deleted the sentence *and* the paragraph below it.
PROSE_POSITIONS: dict[str, tuple[object, tuple[str, ...]]] = {
    "above_quote": (above_a_quote, ("Two points before Friday.",)),
    "standalone": (
        standalone,
        ("Thanks for the update on this.", "We should have a decision by end of week either way."),
    ),
}


# --- Amendment A5's reported half: the false-negative corpus (round 8, part 2) ----------
#
# Round 7 reported a 12.5% false-negative rate and named the residue as "both English
# attributions carrying no address". R-ARCH measured **36.8%** against its own 19 headers
# and found the cause: `_FIRST_PERSON_RE` unions pronouns across ten locales and collides
# with the weekday abbreviations those same locales' clients emit - en `Mon` against fr
# `mon`, de `Mi.` against es `mi`, nl/fi `ma` against fr `ma`, sv `ons` against nl `ons`.
# **Every worked example in this file was dated a Tuesday**, and a Tuesday collides with
# nothing, so the corpus could not falsify the claim it was cited for.
#
# The corpus below spans all seven weekdays. A rate measured against it can be wrong, which
# is the only kind of rate worth reporting.

#: 2026-08-24 .. 2026-08-30 is exactly Monday to Sunday, so one calendar week indexes the
#: seven weekdays with real dates rather than with invented ones.
CORPUS_WEEK: tuple[int, ...] = (24, 25, 26, 27, 28, 29, 30)
WEEKDAY_NAMES: tuple[str, ...] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_EN_ABBR = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_FR_ABBR = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")
_DE_ABBR = ("Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So.")
_NL_ABBR = ("ma", "di", "wo", "do", "vr", "za", "zo")
_SV_ABBR = ("mån", "tis", "ons", "tors", "fre", "lör", "sön")
_FI_ABBR = ("ma", "ti", "ke", "to", "pe", "la", "su")
_ES_ABBR = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
_PT_ABBR = ("seg.", "ter.", "qua.", "qui.", "sex.", "sáb.", "dom.")
_IT_ABBR = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")
_PL_ABBR = ("pon.", "wt.", "śr.", "czw.", "pt.", "sob.", "niedz.")


def client_headers_for_weekday(index: int) -> dict[str, str]:
    """One header per client format, dated the `index`-th day of `CORPUS_WEEK`.

    Every format R-ARCH used, reconstructed from the client's own convention rather than
    copied from anywhere: Gmail in ten locales, Outlook desktop with and without an
    address, an Outlook Web header block, Apple Mail on macOS and iOS, Gmail for Android,
    a Yahoo forwarded block, ProtonMail's ordinal date, Thunderbird's US numeric date, a
    mailing list's parenthesised address, and bare `>` / `>>` chains.

    Formats that print no weekday still move through the week by date, so a rate measured
    here cannot be an artefact of one day for any format.
    """
    day = CORPUS_WEEK[index]
    return {
        "gmail_en": (
            f"On {_EN_ABBR[index]}, Aug {day}, 2026 at 3:14 PM "
            "Priya Shah <priya@example.com> wrote:"
        ),
        "gmail_en_no_address": (
            f"On {_EN_ABBR[index]}, Aug {day}, 2026 at 3:14 PM Priya Shah wrote:"
        ),
        "gmail_fr": (
            f"Le {_FR_ABBR[index]} {day} août 2026 à 15:14, "
            "Priya Shah <priya@example.com> a écrit :"
        ),
        "gmail_de": (
            f"Am {_DE_ABBR[index]}, {day}. Aug. 2026 um 15:14 Uhr "
            "schrieb Priya Shah <priya@example.com>:"
        ),
        "gmail_nl": (
            f"Op {_NL_ABBR[index]} {day} aug. 2026 om 15:14 schreef Priya <priya@example.com>:"
        ),
        "gmail_sv": (
            f"Den {_SV_ABBR[index]} {day} aug. 2026 kl 15:14 skrev Priya <priya@example.com>:"
        ),
        "gmail_fi": (
            f"{_FI_ABBR[index]} {day}. elok. 2026 klo 15.14 Priya <priya@example.com> kirjoitti:"
        ),
        "gmail_es": (
            f"El {_ES_ABBR[index]}, {day} ago 2026 a las 15:14, "
            "Priya Shah <priya@example.com> escribió:"
        ),
        "gmail_pt": (
            f"Em {_PT_ABBR[index]}, {day} de ago de 2026 às 15:14, "
            "Priya Shah <priya@example.com> escreveu:"
        ),
        "gmail_it": (
            f"Il giorno {_IT_ABBR[index]} {day} ago 2026 alle ore 15:14 "
            "Priya <priya@example.com> ha scritto:"
        ),
        "gmail_pl": (
            f"W dniu {_PL_ABBR[index]}, {day}.08.2026 o 15:14 Priya <priya@example.com> napisał:"
        ),
        "outlook_desktop": f"On {day}/08/2026 15:14, Priya Shah <priya@example.com> wrote:",
        "outlook_no_address": f"On {day}/08/2026 15:14, Priya Shah wrote:",
        "owa_block": (
            "From: Priya Shah <priya@example.com>\n"
            f"Sent: {WEEKDAY_NAMES[index]}, {day} August 2026 15:14\n"
            "To: Operations <ops@example.com>\n"
            "Subject: RE: Schema freeze"
        ),
        "apple_mail_macos": f"On {day} Aug 2026, at 15:14, Priya Shah <priya@example.com> wrote:",
        "apple_mail_ios": (
            f"On {_EN_ABBR[index]}, {day} Aug 2026, at 15:14, Priya Shah <priya@example.com> wrote:"
        ),
        "android_gmail": (
            f"On {_EN_ABBR[index]}, {day} Aug 2026, 3:14 PM Priya Shah <priya@example.com> wrote:"
        ),
        "yahoo_block": (
            "----- Forwarded Message -----\n"
            "From: Priya Shah <priya@example.com>\n"
            "To: Operations <ops@example.com>\n"
            f"Sent: {WEEKDAY_NAMES[index]}, August {day}, 2026, 03:14 PM GMT+1\n"
            "Subject: Schema freeze"
        ),
        "protonmail": (
            f"On {WEEKDAY_NAMES[index]}, {day}th August 2026 at 15:14, "
            "Priya Shah <priya@example.com> wrote:"
        ),
        "thunderbird": f"On 8/{day}/2026 3:14 PM, Priya Shah wrote:",
        "mailing_list_paren": (
            f"On {_EN_ABBR[index]}, Aug {day}, 2026 at 3:14 PM "
            "Priya Shah (priya@example.com) wrote:"
        ),
        "bare_gt_chain": "> The freeze starts Friday.\n> Migrations land the week after.",
        "bare_gt_gt_chain": ">> The freeze starts Friday.\n>> Migrations land the week after.",
    }


#: The formats whose headers are **expected** to survive into `body_clean`, with the
#: structural reason each one survives. A5 spends false negatives on purpose, so these are
#: reported rather than gated - but they are named, and `tests/test_quote_corpus.py`
#: asserts that the measured residue is exactly this set and no wider.
DECLARED_FALSE_NEGATIVE_FORMATS: dict[str, str] = {
    "gmail_en_no_address": "no address on the line (amendment A5's declared gap)",
    "outlook_no_address": "no address on the line (amendment A5's declared gap)",
    "thunderbird": "no address on the line (amendment A5's declared gap)",
    "protonmail": (
        "an ordinal calendar date ('24th August 2026'), which `_WHEN_PATTERN` does not "
        "read. Declared rather than closed this round: adding the spelling would put "
        "'On the 24th August 2026 call, priya@example.com wrote:' - a sentence a person "
        "writes, and now in the round 8 prose corpus - inside the deletable set, and that "
        "trade needs its own false-positive measurement, which amendment A5 requires "
        "before anything new becomes deletable"
    ),
}


# --- R-ARCH-026: sender-authored text written *below* a latching signal ------------------
#
# Round 8's three latching signals ran their removal to the end of the message, and R-ARCH
# built sixteen cases across all three in reply-below, sign-off and interleaved positions:
# **1,251 of 1,251 tagged sender characters destroyed, every case.** The reviewer's file was
# never committed either, so the sixteen cases below are reconstructed from the shapes
# `docs/reviews/ROUND_08/R-ARCH.md` §1 names, including its two verbatim reproductions.
# Against round 8's stripper they destroy 1,264 of 1,264 tagged characters - the same 100%,
# on 16 cases, at the reviewer's scale.
#
# Under amendment A7 this corpus measures two different things, and they are reported
# separately because they are not the same claim: **containment** (how many tagged
# characters survive in `body_clean`, which must be all of them) and **default-view
# quality** (how many of them the default view shows, which is a number, not a gate).
#
# Every line is invented for this repository. No personal mail content appears.

_FORWARD_SEPARATOR_BLOCK = (
    "-----Original Message-----\n"
    "From: Priya Shah\n"
    "Sent: Monday, August 24, 2026 9:02 AM\n"
    "To: Dana Whitfield\n"
    "Subject: Renewal pricing\n"
    "\n"
    "We can hold the current rate if the term goes to three years.\n"
)
_HEADER_BLOCK = (
    "From: Priya Shah <priya@example.com>\n"
    "Sent: Monday, August 24, 2026 9:02 AM\n"
    "To: Dana Whitfield <dana@example.com>\n"
    "Subject: Renewal pricing\n"
    "\n"
    "We can hold the current rate if the term goes to three years.\n"
)
_UNMARKED_ATTRIBUTION_BLOCK = (
    "On Monday, August 24, 2026, Priya Shah <priya@example.com> wrote:\n"
    "We should finalize the budget by end of week and circulate it to finance.\n"
)
_LATCHING_BLOCKS: dict[str, str] = {
    "forward_separator": _FORWARD_SEPARATOR_BLOCK,
    "header_block": _HEADER_BLOCK,
    "client_attribution_unmarked": _UNMARKED_ATTRIBUTION_BLOCK,
}


def _latch_cases() -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """`(name, body, sender-authored fragments written below the latch)`.

    The tagged fragments are the ones *below* the latching signal only, matching how R-ARCH
    counted: text above a latch was never at risk and counting it would flatter the number.
    """
    built: list[tuple[str, str, tuple[str, ...]]] = []
    for signal, block in _LATCHING_BLOCKS.items():
        reply_below = "I reviewed this and I think we should push back on the price before signing."
        built.append(
            (f"{signal}__reply_below", f"Hi team,\n\n{block}\n{reply_below}\n", (reply_below,))
        )
        signoff = "Thanks for turning this round so quickly."
        built.append(
            (f"{signal}__signoff_below", f"Hi team,\n\n{block}\n{signoff}\n\nDana\n", (signoff,))
        )
        first = "I agree with the timeline but the marketing line item still looks too low."
        second = "Also, can we get legal's sign-off before we send this out on Thursday?"
        built.append((f"{signal}__interleaved", f"{block}\n{first}\n\n{second}\n", (first, second)))
        postscript = "P.S. I also need the invoice number before finance closes the month."
        built.append((f"{signal}__postscript", f"Yes.\n\n{block}\n{postscript}\n", (postscript,)))
    built.append(
        (
            "combined_forward_then_signoff",
            "Hi team,\n\n"
            + _FORWARD_SEPARATOR_BLOCK
            + "\nI reviewed this and I want to push back on the price before signing anything.\n"
            + "\nThanks,\nDana\n",
            ("I reviewed this and I want to push back on the price before signing anything.",),
        )
    )
    built.append(
        (
            "attribution_then_forward",
            "Short note first.\n\n"
            + _UNMARKED_ATTRIBUTION_BLOCK
            + "\n"
            + _FORWARD_SEPARATOR_BLOCK
            + "\nMy own conclusion is that we renew for one year and revisit in the spring.\n",
            ("My own conclusion is that we renew for one year and revisit in the spring.",),
        )
    )
    built.append(
        (
            "header_block_then_reply_and_signoff",
            "Hi team,\n\n"
            + _HEADER_BLOCK
            + "\nThe pricing looks wrong to me; the volume tier should already apply.\n"
            + "\nBest regards,\nDana Whitfield\n",
            ("The pricing looks wrong to me; the volume tier should already apply.",),
        )
    )
    built.append(
        (
            "forward_with_a_note_at_the_bottom",
            "FYI.\n\n"
            + _FORWARD_SEPARATOR_BLOCK
            + "\nNote for the file: we never agreed to the three-year term.\n",
            ("Note for the file: we never agreed to the three-year term.",),
        )
    )
    return tuple(built)


LATCH_CORPUS: tuple[tuple[str, str, tuple[str, ...]], ...] = _latch_cases()
