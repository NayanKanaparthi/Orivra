"""`ParsedQuery`: AD A.2 step 1 and A.6, deterministic and model-free.

    "`query_analysis` produces a `ParsedQuery`: Gmail operators it can prove, residual
    terms, participant entities (address-normalised), date references, interrogative type,
    an answer-type lexicon, a confidence tier and a `paraphrase_risk` heuristic. **No model
    runs here.**"

Every table this module decides from is a module-level constant with a name, so the whole
of what MailWeave "understands" about a query is enumerable and testable. There is no
frequency count, no corpus, no learned weight and no dial: `paraphrase_risk` is a sum over
a published tuple of factors, and a test executes each factor rather than the total.

**The one claim worth pinning down before it is made.** Nothing here decides whether a
message matches. Parsing produces a `q` and a set of named constraints; Gmail judges the
`q`, and the local verification A.8a branch E-b requires is a *substring* check over text
MailWeave has already fetched, which is in `mailweave.retrieval.signals` and not here.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from zoneinfo import ZoneInfo

from mailweave.constants import (
    NEGATION_PREFIX,
    carriage_token,
    carries_no_content,
    matchable_content_of,
    operator_token,
    query_tokens,
)
from mailweave.query.identifiers import StructuredIdentifier, classify_identifier
from mailweave.query.operators import (
    KIND_BY_OPERATOR,
    OperatorKind,
    OperatorName,
    ParsedOperator,
    Token,
    TokenRole,
    declares_the_search_region,
    tokenise,
)
from mailweave.query.timepolicy import (
    TimeWindow,
    find_relative_expression,
    reference_zone,
    resolve_relative,
    strip_relative_expression,
    widening_declaration,
    window_from_operators,
)


class Interrogative(StrEnum):
    """The question a query is asking, from a closed table (A.8b).

    Three of these carry an **answer type** and drive `answer_type_presence`; the rest are
    recorded and carry none. A.8b names exactly those three - *when*, *how much*, *did we
    decide* - and the others exist so that "this query is a question with no answer-type
    cue" is a state the parse can express rather than a silence.
    """

    WHEN = "when"
    HOW_MUCH = "how_much"
    DID_WE_DECIDE = "did_we_decide"
    WHO = "who"
    WHERE = "where"
    WHY = "why"
    WHICH = "which"
    HOW = "how"
    WHAT = "what"
    NONE = "none"


class AnswerType(StrEnum):
    """The token class an answer to an interrogative query would contain (A.8b)."""

    DATE_LIKE = "date_like"
    NUMERIC_CURRENCY = "numeric_currency"
    DECISION_VERB = "decision_verb"


class ConfidenceTier(StrEnum):
    """AD A.2 step 1's tier. `non_lexical` is D.3 rule 4's escalation trigger."""

    EXACT = "exact"
    FILTERED = "filtered"
    WEAK = "weak"
    NON_LEXICAL = "non_lexical"


#: Read in order; the first pattern that matches decides the class. Ordered so that the
#: three answer-type-bearing classes are tested before the generic ones, because "when did
#: we decide" is a *when* question and a naive scan for "did we decide" would take it for a
#: decision question and look for the wrong token class (A.8b).
INTERROGATIVE_PATTERNS: Final[tuple[tuple[Interrogative, str], ...]] = (
    (Interrogative.WHEN, r"\bwhen\b|\bwhat (?:time|date|day)\b|\bwhat's the date\b"),
    (Interrogative.HOW_MUCH, r"\bhow (?:much|many)\b|\bwhat (?:price|cost|amount|total)\b"),
    (
        Interrogative.DID_WE_DECIDE,
        r"\bdid (?:we|they|you|i) (?:decide|agree|approve|settle|choose|pick|sign off)\b"
        r"|\bwas it (?:decided|agreed|approved)\b"
        r"|\bwhat did (?:we|they) (?:decide|agree|choose)\b",
    ),
    (Interrogative.WHO, r"\bwho\b|\bwhom\b"),
    (Interrogative.WHERE, r"\bwhere\b"),
    (Interrogative.WHY, r"\bwhy\b"),
    (Interrogative.WHICH, r"\bwhich\b"),
    (Interrogative.HOW, r"\bhow\b"),
    (Interrogative.WHAT, r"\bwhat\b"),
)

#: Which answer type each interrogative class expects. A.8b names three; the remaining
#: classes map to none, which is what makes "carries no answer-type cue" (D.3 rule 1b)
#: a value rather than an absence.
ANSWER_TYPE_BY_INTERROGATIVE: Final[dict[Interrogative, AnswerType | None]] = {
    Interrogative.WHEN: AnswerType.DATE_LIKE,
    Interrogative.HOW_MUCH: AnswerType.NUMERIC_CURRENCY,
    Interrogative.DID_WE_DECIDE: AnswerType.DECISION_VERB,
    Interrogative.WHO: None,
    Interrogative.WHERE: None,
    Interrogative.WHY: None,
    Interrogative.WHICH: None,
    Interrogative.HOW: None,
    Interrogative.WHAT: None,
    Interrogative.NONE: None,
}

#: The published decision-verb lexicon for `AnswerType.DECISION_VERB`. Closed, and short on
#: purpose: a long list of near-synonyms would make the predicate true of almost any thread,
#: and A.8b's own warning (ADV-104) is that a predicate true 97 % of the time is a constant
#: rather than a signal. PF-13 measures the base rate before the design leans on it.
DECISION_VERBS: Final[frozenset[str]] = frozenset(
    {
        "agreed",
        "approved",
        "cancelled",
        "canceled",
        "chose",
        "chosen",
        "confirmed",
        "decided",
        "declined",
        "rejected",
        "resolved",
        "settled",
        "signed",
    }
)

_DATE_LIKE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b\d{1,4}[/-]\d{1,2}[/-]\d{1,4}\b"
    r"|\b\d{1,2}:\d{2}\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b"
    r"|\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b"
    r"|\b(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*day\b"
    r"|\b(?:today|tomorrow|yesterday)\b",
    re.IGNORECASE,
)

_NUMERIC_CURRENCY_RE: Final[re.Pattern[str]] = re.compile(
    r"[$£€¥]\s?\d"
    r"|\b\d[\d,]*(?:\.\d+)?\s?(?:usd|eur|gbp|nzd|aud|cad|jpy|chf|sek|dollars?|euros?|pounds?)\b"
    r"|\b\d[\d,]*\.\d{2}\b",
    re.IGNORECASE,
)

#: Words removed before a phrase is measured against A.8a's ">=3 tokens" bar, and before a
#: query is judged to carry no content terms at all. Published and closed.
STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "can",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "his",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "she",
        "should",
        "so",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "to",
        "up",
        "us",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
    }
)

#: The constraint name residual free-text terms travel under, and the one quoted phrases do.
TERMS_CONSTRAINT: Final[str] = "terms"
PHRASE_CONSTRAINT: Final[str] = "phrase"
#: The constraint a *resolved relative* date reference travels under. Named distinctly from
#: `after`/`before` because dropping it drops something the user never literally wrote.
DATE_WINDOW_CONSTRAINT: Final[str] = "date_window"

#: AD A.7's L2 relaxation order, published so the sequence is reproducible (ROUTE-03).
#: Dates first because a mis-parsed window is the commonest wrong route (I-4's "wrong date
#: window"); free-text terms last because dropping them abandons the query's subject.
RELAXATION_ORDER: Final[tuple[str, ...]] = (
    OperatorKind.DATE.value,
    OperatorKind.PARTICIPANT.value,
    # `REGION` keeps the position the single `LOCATION` kind held before round 19 split it,
    # and `ATTRIBUTE` follows it, so the published sequence is unchanged for every query that
    # writes one of them. A region drop is refused by `RelaxationRung._relaxed_query` whatever
    # its rank - it moves the search rather than widening it - so the rank decides only the
    # order in which the rung considers and declines it.
    OperatorKind.REGION.value,
    OperatorKind.ATTRIBUTE.value,
    OperatorKind.SIZE.value,
    OperatorKind.TEXT.value,
    PHRASE_CONSTRAINT,
    TERMS_CONSTRAINT,
    OperatorKind.IDENTITY.value,
)


def fold(text: str) -> str:
    """NFKC + case-fold + whitespace collapse: the comparison form A.8a branch E-b names."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


#: Trailing punctuation a token may end a sentence with. `.` and `-` are word characters to
#: the token regex - deliberately, so `2026-01-05`, `ops@team.example` and `co-ordinate`
#: survive whole - and that made a **trailing** one part of the word: `decided,` folded to
#: `decided` and `decided.` did not (round 25, R-DISC-027). A decision verb at the end of a
#: sentence is where a decision verb usually sits, so the lexicon match that
#: `DECISION_CUE`, the promotion rule's `CONTRADICTION` clause and `TERM_OVERLAP` all depend
#: on was invisible for the commonest position of the word it was looking for.
_TRAILING_PUNCTUATION: Final[str] = ".-"


def _trim(word: str) -> str:
    """Strip sentence punctuation a token merely ends with, and nothing else.

    A token that is *itself* a date, an address or a decimal keeps every character: those
    shapes end in an alphanumeric, so stripping from the right cannot reach inside them.
    `weights._tokens`' own docstring - "a lexicon match that depended on the punctuation next
    to a word would fire on the corpus somebody wrote and not on the mailbox" - is the rule,
    and this is the half of it that was missing.
    """
    return word.rstrip(_TRAILING_PUNCTUATION)


def content_tokens(text: str) -> tuple[str, ...]:
    """The word tokens of `text` with stopwords removed, in order, folded."""
    return tuple(
        trimmed
        for word in re.findall(r"[\w'/@.-]+", fold(text))
        if (trimmed := _trim(word)) not in STOPWORDS and any(char.isalnum() for char in trimmed)
    )


#: The reply and forward markers a mail client writes **in front of** a subject it did not
#: choose. Published as a closed set, folded, without the colon.
#:
#: **Why this exists at all** (round 26, R-DISC-031). Gmail sends `Subject: S` on a thread's
#: root and `Re: S` on every reply, so those two characters are the one difference between
#: the subjects of a thread Gmail itself created. Amendment A11 asks whether a fact
#: *separates one candidate of a thread from another*; a marker the mail client wrote is not
#: a fact about which message, so a subject that differs only by one is the same subject as
#: far as that question goes. Leaving it in made `subject` message-discriminating on **every**
#: multi-message Gmail thread, which is exactly the fact A11's own defect paragraph is about.
#:
#: The English forms are Gmail's own. The localised ones are what other clients put on a reply
#: to a thread this mailbox is in - a thread is not monolingual because its owner is - and they
#: are listed rather than matched by pattern, because a pattern that stripped any short word
#: before a colon would eat `budget: q3` and silently change what a subject says. Adding one is
#: an edit to this constant and to nothing else.
REPLY_PREFIXES: Final[frozenset[str]] = frozenset(
    {
        "re",  # English reply; Gmail's own
        "aw",  # German reply (Antwort)
        "antw",  # Dutch/German reply
        "sv",  # Swedish/Danish/Norwegian reply
        "vs",  # Finnish reply
        "odp",  # Polish reply
        "res",  # Portuguese/Spanish reply
        "rif",  # Italian reply
        "ref",  # reply, some clients
        "fw",  # English forward, short
        "fwd",  # English forward; Gmail's own
        "wg",  # German forward (Weitergeleitet)
        "tr",  # French forward (Transfere)
        "doorst",  # Dutch forward (Doorgestuurd)
        "enc",  # Portuguese forward (Encaminhada)
        "rv",  # Spanish forward (Reenviar)
        "pd",  # Spanish forward, some clients
    }
)

#: One marker, optionally carrying the repeat counter clients write as `Re[2]:` or `Re(3):`,
#: anchored at the start and consuming the colon and the space after it. Applied repeatedly by
#: `strip_reply_prefixes`, because `Re: Fwd: Re: S` is an ordinary thing to receive.
_REPLY_PREFIX_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:" + "|".join(sorted(re.escape(prefix) for prefix in REPLY_PREFIXES)) + r")"
    r"(?:\s*[\[(]\s*\d+\s*[\])])?\s*:\s*",
    re.IGNORECASE,
)


def strip_reply_prefixes(subject: str) -> str:
    """A subject with every leading reply/forward marker removed. Nothing else touched.

    `"Re: Fwd: quarterly plan"` and `"quarterly plan"` are the same subject to this function,
    and `"budget: q3"` is untouched because `budget` is not a published marker.

    **This is a comparison form, not a disclosure form.** Nothing rendered to a caller passes
    through here: a row's reason, the published E4 score and every wire field carry the subject
    Gmail sent. What this decides is whether two candidates of one thread carry the *same*
    subject when amendment A11 asks whether a fact separates one of them from another.
    """
    stripped = subject
    while True:
        shortened = _REPLY_PREFIX_RE.sub("", stripped, count=1)
        if shortened == stripped:
            return stripped
        stripped = shortened


def matches_answer_type(answer_type: AnswerType, text: str) -> bool:
    """Whether `text` carries a token of `answer_type` (A.8b), mechanically."""
    if answer_type is AnswerType.DATE_LIKE:
        return _DATE_LIKE_RE.search(text) is not None
    if answer_type is AnswerType.NUMERIC_CURRENCY:
        return _NUMERIC_CURRENCY_RE.search(text) is not None
    folded = set(re.findall(r"[a-z]+", fold(text)))
    return bool(folded & DECISION_VERBS)


def classify_interrogative(text: str) -> Interrogative:
    """The first class of `INTERROGATIVE_PATTERNS` whose pattern is present."""
    folded = fold(text)
    for interrogative, pattern in INTERROGATIVE_PATTERNS:
        if re.search(pattern, folded) is not None:
            return interrogative
    return Interrogative.NONE


@dataclass(frozen=True)
class Participant:
    """A person named by a participant operator, address-normalised where there is one.

    A bare name is **not** turned into an address. `from:amy` is a legitimate Gmail
    operator that matches on display name as well as address, and inventing
    `amy@<something>` would be a constraint the user did not write appearing in a response
    that says it enforced what they asked for.
    """

    role: OperatorName
    address: str | None
    display: str | None
    negated: bool = False


_ANGLE_ADDRESS_RE: Final[re.Pattern[str]] = re.compile(r"<([^<>]+)>")


def normalise_participant(role: OperatorName, value: str, *, negated: bool) -> Participant:
    """`Amy Smith <Amy.SMITH@Example.Test>` -> address `amy.smith@example.test`.

    Case-folded whole, which is stricter than the RFC (a local part is formally
    case-sensitive) and correct for the comparison being made here: Gmail's own matching is
    case-insensitive, and two spellings of one address must not become two participants.
    """
    inner = _ANGLE_ADDRESS_RE.search(value)
    if inner is not None:
        display = value[: inner.start()].strip().strip('"') or None
        return Participant(
            role=role, address=fold(inner.group(1)), display=display, negated=negated
        )
    if "@" in value:
        return Participant(role=role, address=fold(value), display=None, negated=negated)
    return Participant(role=role, address=None, display=value.strip() or None, negated=negated)


#: Constraint kinds whose fragments bind **one** message jointly rather than independently,
#: and which therefore decompose into a single unit however many fragments they carry **and
#: however many constraints they are written as**.
#:
#: A date window is the whole of this set today: `after:X before:Y` is one condition on one
#: message's timestamp, and a thread holding a message after `X` and another before `Y`
#: holds no message inside the window - so intersecting the two halves on `threadId` would
#: name threads nothing in them satisfies. Every other kind conjoins fragments that
#: *different messages of one thread* can satisfy separately, which is the case RO F2 makes
#: unmatchable at L1 and L1b exists to recover.
#:
#: **The grouping is across constraints, not inside one, and that is a round-16 correction
#: to a round-16 fix.** The sentence above was already written, and the code under it read
#: `constraint.kind in JOINTLY_BINDING_KINDS` per constraint - which is the derived
#: `date_window` constraint and nothing else. A user who writes the window out, which is the
#: ordinary way to write one, produces **two** constraints of one fragment each, each of
#: them "one unit" by that reading, and L1b then intersected the halves exactly as the
#: sentence says it must not: on a thread holding one message in 2025 and one in 2027,
#: `after:2026/01/01 before:2026/12/31` returned both as `role: matched` under
#: `outcome: answered`, for a window neither is in. One shape validated, its peer trusted -
#: in the fix for the previous instance of the same thing, which is where this project has
#: put it three rounds running. Executed by
#: `test_a_date_window_is_one_unit_whether_it_is_written_out_or_derived`.
JOINTLY_BINDING_KINDS: Final[frozenset[str]] = frozenset({OperatorKind.DATE.value})


@dataclass(frozen=True)
class ConstraintUnit:
    """One independently-satisfiable piece of a constraint: what L1b probes for.

    **Relaxation and decomposition are different questions and this is what separates them**
    (R-RETR-008). `terms` is one *relaxation* unit - dropping the query's subject is one
    step, not one step per word - and it was therefore also one *decomposition* unit, so
    `"rollout cutover"`, two words spread across two messages of one thread, parsed to k=1,
    L1b reported itself `not_applicable`, and the founding bug's commonest shape had no
    recovery rung at all. A constraint now says both things: it is dropped whole and it is
    probed piece by piece.

    `constraints` are the names a probe carrying this unit may report having enforced, and
    it is **empty** for a piece of a constraint the probe does not carry whole. That is
    deliberate and it is the conservative direction: `constraint_coverage` is the claim
    "this message satisfied that part of the query", the wire vocabulary for it is
    constraint names (`Envelope._constraint_coverage_names_constraints_the_query_carried`
    refuses anything else), and there is no spelling in it for *half* of `terms`. A row
    admitted by a piece therefore carries no coverage and lets its `reason` - the `q` that
    admitted it, mechanically - say what matched. Understating cannot be false; naming the
    whole constraint would be.

    **It is a tuple rather than an optional name** because a unit can carry more than one
    constraint whole: a written-out `after:X before:Y` is two constraints and one unit, and
    a probe that sends both fragments enforces both. `str | None` could say "one" and
    "none" and had no way to say "these two", so the joint case would have had to under- or
    over-state itself. Nothing else changes: a one-constraint unit is `(name,)`, which is
    what every rung already read.

    `derived_from` is the constraint - or, for the joint date unit, the constraints - this
    unit is a piece **of**, whether or not a probe carrying it enforces them whole. It is
    what lets a reader ask "did the ladder probe every piece of `terms`?", which is the
    question the A.7 cap makes answerable-and-unanswered: at four units and three probes,
    one piece of `terms` was never sent, so the response must not report `terms` enforced
    (R-RETR-024). `constraints` cannot answer it, because for a piece it is deliberately
    empty. Read by `retrieval.assemble._decomposition_enforced`.

    `label` is unique within a parse and never reaches the wire: it keys L1b's intersection
    so two pieces of one constraint are two probes rather than one dictionary key.
    **Uniqueness is now executed rather than asserted** (R-RETR-025): it was
    `f"{name}[{fragment}]"`, so `from:a@x from:a@x` produced two identical labels, L1b spent
    one of its three A.7 slots re-sending an identical `q`, and the intersection dictionary
    kept the second probe's admission delta - empty, because the first had already admitted
    everything - which emptied the intersection. A repeated identical fragment is now **one**
    unit, which makes the labels unique and the wasted probe impossible by the same change.
    `test_a_repeated_identical_fragment_is_one_unit_and_every_label_is_unique` executes both
    halves.
    """

    label: str
    fragment: str
    constraints: tuple[str, ...]
    derived_from: tuple[str, ...] = ()


@dataclass(frozen=True)
class Constraint:
    """One droppable unit of the query, named as `constraint_coverage` names it.

    `fragments` are the `q` fragments this constraint contributes, already rendered, so a
    rung composes a query by joining fragments rather than by re-deriving them - which is
    how the executed `q` and the reported constraint set stay one statement.
    """

    name: str
    kind: str
    fragments: tuple[str, ...]
    written: bool = True

    def render(self) -> str:
        return " ".join(self.fragments)


def carries_nothing_to_select_by(query: str) -> bool:
    """Whether every token of `q` only says *where* to look or *what to leave out*.

    The whole-`q` rule every rung that composes a probe out of a subset of the query's
    fragments reads, and `selects_something` below is the same sentence asked of one
    fragment - a fragment is just the shortest `q` there is.

    `constants.carries_nothing_but_mailbox_scope` refuses a `q` of nothing but the widening
    operator; it does not refuse that operator with `-cutover` attached, which is the same
    request with a fragment of the query as a disguise - Gmail answers it with the whole
    mailbox, spam and trash included, minus the few messages that say "cutover". Executed:
    for a mailbox whose inbox all mentions the term, `mailweave_search("-cutover")` returned
    eight spam messages as `role: matched` under `outcome: answered` and
    `term_coverage: 1.0` (R-RETR-006).

    **A region declaration says where; a negation says what not; a content-free token says
    nothing at all; none of the three says what.** A `q` made only of those names nothing to
    find, so it is a listing rather than a probe.

    **The first clause reads `declares_the_search_region`, not a membership test against
    three named operators** (round 18, A9), and since round 19 that predicate reads the
    operator registry rather than one lexical prefix (R-RETR-036) - so an operator declared
    `OperatorKind.REGION` tomorrow is a "says where" token here without an edit.

    **The third clause is round 17's** (R-RETR-017). The two it joins are named-shape tests -
    is this one of three operators, does it begin with a minus - and a shape nobody had named
    walked between them: an empty quoted phrase, an operator written with no value, a token
    of zero-width characters. `matchable_content_of` is the structural question those two do
    not ask.

    **This function lives here rather than in `constants` since round 19**, because its first
    clause reads the operator registry and `constants` is the module the registry imports.
    Nothing about the rule changed in the move; `test_a_negated_operator_with_a_quoted_value_
    is_not_a_probe_of_its_own` and the ladder's own sweep hold it either way.

    Tokenised through `query_tokens` and `operator_token` like its neighbours, so a quoted
    value stays one token and the fullwidth, grouped and capitalised spellings that defeated
    the scope coupling twice cannot defeat this one either. A query with no tokens at all is
    not this shape - it is the empty `q`, refused by its own rule with its own message.
    """
    tokens = query_tokens(query)
    return bool(tokens) and all(
        declares_the_search_region(token)
        or operator_token(token).startswith(NEGATION_PREFIX)
        or not matchable_content_of(token)
        for token in tokens
    )


def selects_something(fragment: str) -> bool:
    """Whether this `q` fragment names something to **find**, rather than where or what-not.

    The one predicate behind every "this is a listing, not a probe" decision in the parse
    layer, so the rule has one spelling. `carries_nothing_to_select_by` is the same sentence
    written for a whole `q` in `mailweave.constants`, where the rungs that compose a `q` out
    of a subset of the query's fragments already read it; a fragment is just the shortest
    `q` there is.

    Three token classes fail it and they fail it for one reason: a negation (`-cutover`,
    `-from:b`) says what to leave out, a fragment that `declares_the_search_region` says
    where to look, and a token with no matchable content (`""`, `subject:`, a run of
    zero-width characters) says nothing at all. None of them says what to look for, so a
    probe carrying one alone is a mailbox listing rather than a question. The operators
    themselves are **not spelled here**: `mailweave.constants` is the one module that writes
    them, and `test_no_module_spells_a_mailbox_scope_operator_outside_the_scope_enum` reads
    prose too.

    **Failing this predicate is not one fact but two, and round 16 read it as one.** A
    fragment excluded from the units is excluded because a probe carrying it *alone* would be
    a listing; that says nothing about whether the probe's **siblings** may leave it out.
    That second question is the asymmetry rule, and it is decided by what the fragment does
    rather than by how it is spelled: a *filter* may be left out, because omitting one widens
    the match inside the region; a *region declaration* may not, in either polarity, because
    omitting one changes which region is searched. The rule is stated once, in
    `constants.declares_the_search_region`; the region is derived once, by
    `search_region_of`; and it is carried by every unit - see `decomposition_units_of`
    (R-RETR-019, R-RETR-026).
    """
    return bool(fragment.strip()) and not carries_nothing_to_select_by(fragment)


def search_region_of(constraints: Sequence[Constraint]) -> tuple[str, ...]:
    """The fragments of a parse that declare **which region** the search runs over.

    The one derivation of "the region this query named". Every rung that composes a probe
    out of a subset of the query's fragments reads it, and every such probe carries all of
    it: `decomposition_units_of` states the invariant, `ExactOperatorRung._in_scope` and
    `BroadeningRung` apply it, and one membership test over `LADDER` enforces it.

    **Every fragment `declares_the_search_region` accepts, in written order, whatever its
    polarity** - which is round 18's correction and is why this function was renamed rather
    than edited in place (OD-5, A9-A2). It used to be `mailbox_scope_of`, it returned the
    members of `WIDENING_MAILBOX_OPERATORS` only, and it said in its own docstring that a
    negated one "is not carried: it excludes, and omitting an exclusion widens rather than
    narrows, which is the direction a decomposition probe is allowed to be wrong in". That
    sentence is false, and the reason it is false is the asymmetry rule stated in
    `declares_the_search_region`: omitting a **negated spam scope** does not widen *within*
    the region, because a negated spam scope **is** the region. Executed, a query excluding
    the spam mailbox and naming one word reached the widening operator with
    `includeSpamTrash=true` and returned the excluded spam message as `role: matched`
    (R-RETR-026; the reproduction is in the comment on `BroadeningRung._anywhere`, where the
    operator vocabulary may be written).

    Two consequences follow from the same change and neither is a separate rule. A
    *narrowing* location - `in:inbox`, `in:sent`, and any location Gmail names later - is a
    region declaration too, so it is carried onto every probe instead of being probed alone
    as though it were something to look for. And a query that declares a region, positively
    or negatively, is one whose region no rung may widen: `BroadeningRung` reads this
    function to decide whether its published whole-mailbox step applies at all (OD-5 point 2).
    """
    return tuple(
        fragment
        for constraint in constraints
        for fragment in constraint.fragments
        if declares_the_search_region(fragment)
    )


def region_declarations_of(parsed: ParsedQuery) -> tuple[str, ...]:
    """Every way this query declared the search region: its parsed fragments **and its own
    tokens**.

    `search_region_of` answers "what must every composed probe carry?", and it can only
    answer it from constraint fragments, because a fragment is what a rung has to compose
    with. This answers the different question the broadening step asks - *did the caller name
    a region at all?* - and that one must be asked of the query as the caller wrote it.

    **The two are not the same set, and round 18 used the first for both** (R-RETR-035,
    R-RETR-037). A token this module does not parse is still a token that declares a region:

      * a negated region operator written inside Gmail's grouping punctuation, as
        `-(...)` or `(-...)` - such a token is classified
        `passthrough` and never becomes a constraint, so the parse handed the gate nothing
        and the published broadening ran. `tokenise` now re-emits a group that holds exactly
        one operator, which covers the single-operator spellings; a group holding **several**
        tokens still cannot be parsed, because regrouping a boolean is a parser this module
        deliberately is not, and for those the raw token read here is what stops the step;
      * a fullwidth spelling - `operator_token` NFKC-normalises and `tokenise` does not, so
        the predicate reads the operator and the parser reads two terms. Which of them should
        change is a normalisation policy question for A.6 (WS-10); until it is answered, this
        is the conservative reading and it closes the boundary rather than the disagreement.

    Both sources are read rather than one, and the union is deliberate: this is not two
    derivations of one fact that could disagree, it is one question asked of two
    representations of the same query, and the answer is "yes" if either says so. A false
    *refusal to widen* costs recall and the response says so; a false widening reads mail the
    caller excluded.
    """
    return (
        *search_region_of(parsed.constraints),
        *(token for token in query_tokens(parsed.raw) if declares_the_search_region(token)),
    )


def region_constraint_names(constraints: Sequence[Constraint]) -> tuple[str, ...]:
    """The constraints **every** fragment of which declares the region, in written order.

    A probe carrying the whole region therefore carries these constraints whole, so it may
    name them in `enforced` and a row it admitted may name them in `constraint_coverage`:
    the message really is in the region the query asked for. Written here, beside the region
    derivation itself, because a second copy of "which constraint is the region one?" is how
    the two came to disagree at L0 and L1b (R-ARCH-031).
    """
    return tuple(
        constraint.name
        for constraint in constraints
        if constraint.fragments and all(declares_the_search_region(f) for f in constraint.fragments)
    )


def constraints_carried_whole(query: str, constraints: Sequence[Constraint]) -> tuple[str, ...]:
    """The constraints of a parse this `q` carries **whole**, in written order.

    ---

    **`enforced` is derived here, once, rather than declared by each rung** (OD-5 point 5,
    work order Part 3). A probe enforces a constraint exactly when its own `q` carries every
    fragment of it; a probe that carries some fragments of a constraint has not enforced that
    constraint, and a row it admitted has not satisfied it. That is one sentence about the
    string a rung is about to send, so it is answered from the string - which is what makes a
    rung added later inherit it instead of restating it.

    **The defect this closes.** Round 17 established the rule at L1b and L3 and wrote it into
    each of them separately; L0 kept its own hand-declared value. So `PO-2026-0041 zephyr`
    executed `"PO-2026-0041"`, halted under D.3 rule 1b - which forbids any later rung from
    correcting the claim - and reported `enforced ('terms',)`, `term_coverage 1.0`,
    `sufficiency: sufficient` and `constraint_coverage ('terms',)` over a row that does not
    contain "zephyr" (R-RETR-028). The same shape at branch E-b claimed the whole `phrase`
    constraint from the first of two phrases. Nothing in the suite asserted the old value -
    the reviewer planted the honest one and all 2,248 tests stayed green - so this arrives
    with `test_a_probe_enforces_only_the_constraints_its_own_q_carries_whole`, which sweeps
    the rule over every rung of `LADDER` and fails when any rung stops deriving it.

    **It reproduces every hand-written value it replaces**, which is how it was checked
    rather than asserted: L1 carries the whole render; L2 carries everything but its declared
    drop; an L1b piece probe carries the region whole and its own constraint in part; L3's
    widening step carries an unwidenable date and a negated participant unchanged while a
    `{from:x to:x}` disjunction is not the `from:x` the caller wrote; L3's whole-mailbox step
    carries the region constraint only when the caller had already written the widening
    operator themselves. Each of those was a separate paragraph of a separate docstring, and
    each is now the same sentence read from the `q`.

    Fragment comparison is `constants.carriage_token`, which reduces the spelling differences
    that do not change what Gmail matches and keeps the one that does - polarity.
    """
    carried = {carriage_token(token) for token in query_tokens(query)}
    return tuple(
        constraint.name
        for constraint in constraints
        if constraint.fragments
        and all(
            all(carriage_token(piece) in carried for piece in query_tokens(fragment))
            for fragment in constraint.fragments
        )
    )


def _units_of_one(constraint: Constraint) -> tuple[ConstraintUnit, ...]:
    """The pieces of one **independently-binding** constraint, for `decomposition_units_of`.

    One unit per **selecting** fragment. A constraint with at most one selecting fragment is
    one unit **named after itself**, carrying the whole constraint including its negations -
    so nothing about a probe's account of itself changes for the shapes that already worked.
    The several-fragment case is what this adds, and it adds it for every kind at once
    rather than for the `terms` constraint that was reported.

    **A fragment that selects nothing is never a unit of its own**, and that exclusion is
    the difference between decomposing a query and asking for the mailbox. A decomposition
    probe asks Gmail "which threads have a message satisfying this part?"; `-from:b` and
    `-cutover` are satisfied by nearly every message there is, and a widening mailbox-scope
    operator is satisfied by every message there is - so a probe carrying one alone is a
    whole-mailbox listing wearing a fragment of the query as a disguise, which is the same
    defect `Probe.__post_init__` refuses one operator to the left (R-RETR-006). Dropping
    such a fragment from the units widens the candidate set, which is a superset and costs
    precision rather than recall - the direction this rung is already allowed to be wrong in.
    **That sentence is true of a filter and false of a region declaration**, which is what
    round 16 did not separate and round 17 got half right: dropping the region changes which
    region is searched, in either polarity, so `decomposition_units_of` carries every region
    fragment onto every unit (R-RETR-019, R-RETR-026).

    **A repeated identical fragment is one unit** (R-RETR-025). `from:a@x from:a@x` is one
    question asked twice: two units of it spent two of the three A.7 probe slots on the same
    `q`, and their labels - `f"{name}[{fragment}]"` - collided, so L1b's intersection
    dictionary kept only the second, whose admission delta is empty because the first probe
    had already admitted everything. `dict.fromkeys` de-duplicates in written order.

    **The scope half is a round-16 correction to a round-16 fix, and it is this project's
    recurring defect committed at the join of its own two repairs.** The paragraph above
    was written about negations only, and the code under it tested only for the negation
    prefix. So a query naming the widening scope operator and a term - an ordinary Gmail
    query, and the very shape L3 composes for itself - planned an L1b probe of the scope
    operator alone, which the round-16 `Probe` refusal then rejected with a bare `ValueError`
    out of `plan_ladder`. Measured over a 2,300-query cross-product of ordinary operator
    spellings: **757 raised rather than answered, 712 of them at this rung**, and every one
    of the 757 was a query naming a member of `WIDENING_MAILBOX_OPERATORS`. One shape
    validated, its peer trusted - and the peer was the fix in the next module. Executed by
    `test_a_negated_fragment_is_not_a_decomposition_probe_of_its_own` and
    `test_a_mailbox_scope_fragment_is_not_a_decomposition_probe_of_its_own`.

    This function is deliberately **not** a method on `Constraint`: whether a fragment can
    be probed alone is a question about the parse, not about one constraint of it, and a
    per-constraint answer is what let a written-out date window decompose into its halves.
    `decomposition_units_of` is the only caller and the only place that knows the rule.
    """
    fragments = tuple(dict.fromkeys(constraint.fragments))
    positive = tuple(f for f in fragments if selects_something(f))
    if not positive:
        return ()
    if len(positive) == 1:
        return (
            ConstraintUnit(
                label=constraint.name,
                fragment=" ".join(fragments),
                constraints=(constraint.name,),
                derived_from=(constraint.name,),
            ),
        )
    return tuple(
        ConstraintUnit(
            label=f"{constraint.name}[{fragment}]",
            fragment=fragment,
            constraints=(),
            derived_from=(constraint.name,),
        )
        for fragment in positive
    )


def decomposition_units_of(constraints: Sequence[Constraint]) -> tuple[ConstraintUnit, ...]:
    """Every independently-satisfiable piece of a parse, in written order. L1b plans on this.

    Three rules. The second is the round-16 correction and the third is round 17's, which is
    the **invariant at the join of decomposition and scope**:

      * a constraint whose fragments bind **separately** contributes one unit per positive
        fragment (`_units_of_one`), which is what makes `"rollout cutover"` recoverable;
      * every constraint of a **jointly binding** kind contributes to **one** unit between
        them all, carrying every fragment of every one of them. `after:X before:Y` is one
        condition on one message's timestamp whether the user wrote it as two operators or
        MailWeave derived it from `newer_than:`, and the halves must not be intersected -
        see `JOINTLY_BINDING_KINDS`, which carries the executed counterexample;
      * **every unit carries the query's search region.**

    ---

    **The invariant, stated once because it arrived three times.**

        A probe composed from a subset of a query's fragments searches the region the query
        named. The fragments it may leave out are exactly the **filters** - the fragments
        that constrain messages *within* whatever region is being searched - because omitting
        one can only widen the match inside that region, which costs precision and never
        recall. It may not leave out a fragment that **declares the region**, in either
        polarity, because omitting one widens nothing: it moves the probe to a different
        region, where it can match messages the query excluded and miss messages the query
        asked for. The only rung allowed to change the region is the one whose published step
        is to replace it (AD A.7 L3), it replaces it wholesale, it declares the replacement,
        and it runs **only when the query declared no region at all** (OD-5 point 2).

    Round 16 excluded a scope fragment from the units - correctly, since a probe of
    the widening operator alone is a listing - and read that exclusion as also excluding it
    from the probes, which is a second and different decision. So a query naming the widening
    operator and two bare words, with the split thread in spam, sent each word on its own
    with `includeSpamTrash=false`:
    `|H| = 0`, the founding bug's own shape made unrecoverable in exactly the place a user
    goes after the default search failed (R-RETR-019). The same join produced R-RETR-021 at
    L3, where a broadening probe conjoined the widening operator with the narrowing scope it was
    supposed to replace and searched the narrower one while declaring that it had widened.

    **And round 17 committed the third instance inside its own repair.** The invariant above
    used to classify the fragments a probe may leave out as "a negation", which put a
    **negated spam scope** in the permitted class - so a query excluding the spam mailbox was
    sent to the widening operator with `includeSpamTrash=true` and returned the excluded spam
    message as a match (R-RETR-026: 201 probes in a 5,979-query sweep, 47 of 600 randomised
    trials). The class is now **filter versus region declaration**, which is a statement
    about what an operator *does*, so it holds for a scope operator nobody has added yet;
    enumerating the location operators by name here would have been the fourteenth instance
    of the defect that produced A9.

    Three instances at one join is the join being under-specified, not three rungs being
    unlucky - so the region is derived once, by `search_region_of`, the asymmetry is derived
    once, by `constants.declares_the_search_region`, and
    `test_every_probe_the_ladder_composes_searches_the_region_the_query_named` executes the
    invariant over every rung of `LADDER` and over the whole operator family.

    ---

    The joint unit takes the position of the **first** jointly-binding constraint, so the
    units stay in the order the query wrote them and L1b's probe order is still a function
    of the query alone (the `reproducible` property of the ladder's commonality test).

    A joint unit with no selecting fragment at all is not a unit, for the same reason a
    negated fragment is never one: `-after:2026/01/01` excludes and selects nothing.
    Executed by `test_a_date_window_is_one_unit_whether_it_is_written_out_or_derived`.
    """
    units: list[ConstraintUnit] = []
    joint: list[Constraint] = []
    joint_at: int | None = None
    for constraint in constraints:
        if constraint.kind in JOINTLY_BINDING_KINDS:
            if joint_at is None:
                joint_at = len(units)
            joint.append(constraint)
            continue
        units.extend(_units_of_one(constraint))
    if joint and joint_at is not None:
        fragments = tuple(fragment for c in joint for fragment in c.fragments)
        if any(selects_something(fragment) for fragment in fragments):
            units.insert(
                joint_at,
                ConstraintUnit(
                    label="+".join(c.name for c in joint),
                    fragment=" ".join(fragments),
                    constraints=tuple(c.name for c in joint),
                    derived_from=tuple(c.name for c in joint),
                ),
            )
    region = search_region_of(constraints)
    if not region:
        return tuple(units)
    # A scope constraint every fragment of which is carried is enforced **whole** by each
    # unit, so it joins `constraints` and a row admitted by such a probe may name it in
    # `constraint_coverage`: the message really is in the region the query asked for. It
    # does **not** join `derived_from`, which answers a different question - "was every
    # piece of this constraint probed?" - and the scope is carried by pieces that were never
    # sent as well as by the ones that were, so counting it there would report the A.7 cap
    # as binding on a constraint the cap cannot bind on.
    carried = " ".join(region)
    region_names = region_constraint_names(constraints)
    return tuple(
        ConstraintUnit(
            label=unit.label,
            fragment=f"{carried} {unit.fragment}",
            constraints=(*unit.constraints, *region_names),
            derived_from=unit.derived_from,
        )
        for unit in units
    )


@dataclass(frozen=True)
class RiskFactor:
    """One published contributor to `paraphrase_risk`, with the weight it carries."""

    name: str
    weight: float
    fired: bool


#: The whole of `paraphrase_risk`: a sum over these, clamped to [0, 1]. Published as data
#: so a test can execute each factor separately instead of asserting the total, and so a
#: reader can see that there is no learned weight and no corpus behind any of them.
RISK_FACTORS: Final[tuple[tuple[str, float], ...]] = (
    ("no_provable_operator", 0.35),
    ("interrogative_intent", 0.25),
    ("no_exact_signal_candidate", 0.20),
    ("few_content_terms", 0.20),
)


@dataclass(frozen=True)
class ParsedQuery:
    """The whole model-free analysis of one user query."""

    raw: str
    tokens: tuple[Token, ...]
    operators: tuple[ParsedOperator, ...]
    terms: tuple[str, ...]
    search_terms: tuple[str, ...]
    removed_stopwords: tuple[str, ...]
    #: The phrases the query asks Gmail to **match**. A phrase the query wrote behind the
    #: negation prefix is not one of these - it is in `excluded_phrases` - because polarity
    #: is part of what a phrase constraint says, and this field is read by A.8a branch E-b,
    #: by the confidence tier and by the risk factors, all three of which ask "what is there
    #: to look for?" (R-RETR-027).
    phrases: tuple[str, ...]
    #: The phrases the query asks Gmail to **exclude**, in written order. Carried into `q`
    #: with the negation prefix by `_build_constraints`; never a decomposition unit, never a
    #: branch E-b candidate, and never something a row can be said to have satisfied.
    excluded_phrases: tuple[str, ...]
    passthrough: tuple[str, ...]
    unknown_operators: tuple[str, ...]
    #: Tokens the parse read that name nothing for Gmail to match: an empty quoted phrase,
    #: an operator written with no value, a token of nothing but zero-width characters.
    #: Kept out of `constraints` so no rung can compose one into a `q`, and declared dropped
    #: by `dropped_declarations` so `term_coverage` falls for them (R-RETR-017).
    vacuous_tokens: tuple[str, ...]
    participants: tuple[Participant, ...]
    identifiers: tuple[StructuredIdentifier, ...]
    constraints: tuple[Constraint, ...]
    interrogative: Interrogative
    answer_type: AnswerType | None
    confidence: ConfidenceTier
    risk_factors: tuple[RiskFactor, ...]
    timezone: str
    window: TimeWindow | None

    @property
    def paraphrase_risk(self) -> float:
        """The sum of the fired factors, clamped to [0, 1]. Nothing else contributes."""
        return min(
            1.0, max(0.0, sum(factor.weight for factor in self.risk_factors if factor.fired))
        )

    @property
    def constraint_names(self) -> tuple[str, ...]:
        return tuple(constraint.name for constraint in self.constraints)

    @property
    def decomposition_units(self) -> tuple[ConstraintUnit, ...]:
        """Every independently-satisfiable piece of every constraint, in written order.

        This is what L1b plans over. It differs from `constraints` in two directions:
        upward, when a constraint carries several fragments that different messages of one
        thread can satisfy separately - the case the rung exists for and the one the
        constraint list could not express (R-RETR-008); and downward, when several
        constraints state one condition on one message and must be probed as one. The rule
        for both is in `decomposition_units_of`, which is the only place that knows it.
        """
        return decomposition_units_of(self.constraints)

    @property
    def unproven(self) -> tuple[str, ...]:
        """Tokens the query wrote that no constraint carries, so no probe can execute them.

        Three classes today and they fail the same way: Gmail's boolean and grouping syntax,
        which `render` explains cannot be regrouped; a `name:value` token whose name is not
        in Gmail's documented set; and a token that names nothing to match at all
        (R-RETR-017). All three are things the user wrote that the executed `q` does not
        carry, which is why `term_coverage` counts them (see there) and
        `dropped_declarations` names them.

        The third is dropped-and-declared rather than refused with the rest of the query,
        and that is a deliberate choice between the two R-RETR-017 offered. `report "" 2026`
        is a paste artefact around a real question, and searching for `report 2026` while
        saying plainly that `""` was not executed answers it; refusing the whole query would
        turn one meaningless token into a whole refusal. When the vacuous token is *all*
        there is, no constraint survives, `carries_nothing_searchable` becomes true, and the
        query is reported as unsearchable by that rule rather than by this one.
        """
        return (*self.passthrough, *self.unknown_operators, *self.vacuous_tokens)

    @property
    def carries_nothing_searchable(self) -> bool:
        """The query wrote something and the parse turned none of it into a constraint.

        A **parse failure**, and named as one: `"(rollout OR escalation)"`, `"the and of"`
        and `"?"` all reach here. There is nothing to search for, so there is no probe to
        send and no rung that could have helped - which is an honest inability, and is not
        the same as an empty query (`""`, `"   "`), where the user asked for nothing at all.
        Distinguishing them is what keeps `term_coverage` from reporting 1.0 over a query
        none of whose content was executed (R-RETR-006).
        """
        return not self.constraints and bool(self.raw.strip())

    def constraint(self, name: str) -> Constraint | None:
        for candidate in self.constraints:
            if candidate.name == name:
                return candidate
        return None

    @property
    def rfc822msgid(self) -> ParsedOperator | None:
        """The `rfc822msgid:` operator, which A.8a branch E-a turns on. At most one."""
        for operator in self.operators:
            if operator.name is OperatorName.RFC822MSGID and not operator.negated:
                return operator
        return None

    @property
    def qualifying_phrases(self) -> tuple[str, ...]:
        """Phrases long enough for A.8a branch E-b: >=3 tokens after stopword removal."""
        from mailweave.constants import EXACT_PHRASE_MIN_TOKENS

        return tuple(
            phrase
            for phrase in self.phrases
            if len(content_tokens(phrase)) >= EXACT_PHRASE_MIN_TOKENS
        )

    def render(self, constraints: Sequence[Constraint] | None = None) -> str:
        """Compose a Gmail `q` from `constraints`. Unproven tokens are **not** re-emitted.

        This is the one place the parser gives something up, so it is stated here rather
        than discovered from a recall number. MailWeave does not parse `OR`, `AND` or
        Gmail's `(...)`/`{...}` grouping, and a composed `q` regroups the query by
        constraint - so a boolean token cannot be put back in the position that gave it its
        meaning. Re-emitting it somewhere else would execute a query nobody wrote.

        The tokens are therefore carried in `passthrough` and **declared dropped** by
        `dropped_declarations`, which names them and the reason. The executed query is
        narrower than the user's (an `OR` becomes an implicit `AND`), which is a false
        negative the ladder is built to recover from - L2 drops the terms constraint and L3
        broadens - and which LEX-02 requires be reported rather than absorbed.

        **An unknown `name:value` token is treated the same way, and used not to be**
        (R-RETR-012). It rode inside the residual terms, so it reached Gmail conjoined with
        the rest of the query - where it can only *reduce* recall, since Gmail either judges
        an operator MailWeave could not prove or matches the literal string - and appeared
        nowhere in `asked_for`: not as an operator, not as a term, not as a drop. The rule
        this module already applies to a boolean it cannot regroup is the right one for an
        operator it cannot prove: do not execute what you cannot account for, and say so.
        """
        chosen = self.constraints if constraints is None else tuple(constraints)
        parts = [fragment for constraint in chosen for fragment in constraint.fragments]
        return " ".join(part for part in parts if part)

    def term_coverage(self, enforced: Sequence[Constraint]) -> float:
        """Fraction of **what the query asked for** that the executed `q` carried (LEX-02).

        The denominator is the constraints *plus* `unproven` - the tokens the parse could
        not turn into a constraint at all. Counting only constraints made the number
        structurally incapable of falling: a query the parser produced nothing from divided
        zero by zero and reported **1.0**, over a whole-mailbox scan that executed none of
        its content (R-RETR-006), and a query carrying an operator MailWeave cannot prove
        reported 1.0 while that operator reached nobody (R-RETR-012). A signal LEX-02
        counts as dropped now moves the number it is counted by.

        Two degenerate cases, and they are the same arithmetic rather than two rules: a
        query that asked for nothing - empty or whitespace - has coverage 1.0, because
        nothing was dropped; a query that asked for something none of which became a
        constraint has coverage 0.0, because all of it was.
        """
        asked = len(self.constraints) + len(self.unproven)
        if asked == 0:
            return 0.0 if self.carries_nothing_searchable else 1.0
        return len(enforced) / asked


def _participants(operators: Sequence[ParsedOperator]) -> tuple[Participant, ...]:
    return tuple(
        normalise_participant(operator.name, operator.value, negated=operator.negated)
        for operator in operators
        if KIND_BY_OPERATOR[operator.name] is OperatorKind.PARTICIPANT
    )


def _build_constraints(
    operators: Sequence[ParsedOperator],
    phrases: Sequence[tuple[str, bool]],
    terms: Sequence[str],
    window: TimeWindow | None,
    window_is_derived: bool,
) -> tuple[Constraint, ...]:
    """Group the parse into droppable, named units, in the order the query wrote them."""
    built: list[Constraint] = []
    seen: dict[str, list[str]] = {}
    order: list[str] = []
    for operator in operators:
        name = operator.name.value
        if name not in seen:
            seen[name] = []
            order.append(name)
        seen[name].append(operator.render())
    for name in order:
        built.append(
            Constraint(
                name=name,
                kind=KIND_BY_OPERATOR[OperatorName(name)].value,
                fragments=tuple(seen[name]),
            )
        )
    if window is not None and window_is_derived:
        built.append(
            Constraint(
                name=DATE_WINDOW_CONSTRAINT,
                kind=OperatorKind.DATE.value,
                fragments=tuple(operator.render() for operator in window.operators()),
                written=False,
            )
        )
    if phrases:
        # **A negated phrase is rendered as an exclusion, because that is what it is**
        # (R-RETR-027). The polarity used to be discarded at the parse - `phrases` was
        # `token.value` and nothing carried `token.negated` - so a query asking for messages
        # *without* a phrase executed a search *for* it, and the one message that has it came
        # back `role: matched` with `constraint_coverage ('phrase',)`, `term_coverage 1.0` and
        # `outcome: answered`. That is LEX-02's silently-dropped signal in its worst form: not
        # an omission but an inversion, reported as enforcement.
        built.append(
            Constraint(
                name=PHRASE_CONSTRAINT,
                kind=PHRASE_CONSTRAINT,
                fragments=tuple(
                    f'{NEGATION_PREFIX if negated else ""}"{phrase}"' for phrase, negated in phrases
                ),
            )
        )
    if terms:
        built.append(
            Constraint(name=TERMS_CONSTRAINT, kind=TERMS_CONSTRAINT, fragments=tuple(terms))
        )
    return tuple(built)


def _confidence(
    operators: Sequence[ParsedOperator],
    identifiers: Sequence[StructuredIdentifier],
    phrases: Sequence[str],
    content: Sequence[str],
) -> ConfidenceTier:
    """AD A.2 step 1's four tiers, as a closed decision over what the parse found.

    Order is precedence and each branch names what it is about:

      * `exact` - the query carries a candidate for one of A.8a's three branches. It is a
        statement about the *query*, not about a result: whether the signal fires depends
        on the hit count, which no parse knows;
      * `filtered` - at least one provable Gmail operator, so the first rung is a filter;
      * `weak` - no operator, but content-bearing terms remain after stopword removal;
      * `non_lexical` - nothing to search for lexically at all. D.3 rule 4 escalates on it.
    """
    from mailweave.constants import EXACT_PHRASE_MIN_TOKENS

    qualifying = [p for p in phrases if len(content_tokens(p)) >= EXACT_PHRASE_MIN_TOKENS]
    has_msgid = any(o.name is OperatorName.RFC822MSGID and not o.negated for o in operators)
    if has_msgid or identifiers or qualifying:
        return ConfidenceTier.EXACT
    if operators:
        return ConfidenceTier.FILTERED
    if content:
        return ConfidenceTier.WEAK
    return ConfidenceTier.NON_LEXICAL


def _risk_factors(
    operators: Sequence[ParsedOperator],
    interrogative: Interrogative,
    identifiers: Sequence[StructuredIdentifier],
    phrases: Sequence[str],
    content: Sequence[str],
) -> tuple[RiskFactor, ...]:
    from mailweave.constants import EXACT_PHRASE_MIN_TOKENS

    qualifying = [p for p in phrases if len(content_tokens(p)) >= EXACT_PHRASE_MIN_TOKENS]
    has_msgid = any(o.name is OperatorName.RFC822MSGID and not o.negated for o in operators)
    fired = {
        "no_provable_operator": not operators,
        "interrogative_intent": interrogative is not Interrogative.NONE,
        "no_exact_signal_candidate": not (has_msgid or identifiers or qualifying),
        "few_content_terms": len(content) <= 1,
    }
    return tuple(
        RiskFactor(name=name, weight=weight, fired=fired[name]) for name, weight in RISK_FACTORS
    )


def analyse(
    query: str,
    *,
    now: datetime,
    zone: ZoneInfo | None = None,
) -> ParsedQuery:
    """Parse one user query. Deterministic in `(query, now, zone)` and nothing else.

    `now` is required rather than defaulted to the clock: a relative expression resolves
    against it, so a parse that read the clock would produce a `q` that cannot be replayed,
    and ROUTE-03 requires the sequence to be reproducible for the same input.
    """
    resolved_zone = zone if zone is not None else reference_zone()
    tokens = tokenise(query)
    # A token that names nothing for Gmail to match becomes **no constraint at all**
    # (R-RETR-017). The filter is here, at the one place a `Token` becomes something a rung
    # can compose with, rather than at each of the four places a constraint is built: an
    # empty quoted phrase, `subject:` with no value and a run of zero-width characters are
    # one shape, not three, and `matchable_content_of` is where that shape is defined. Round
    # 15 sent an empty phrase to Gmail and L3 composed the widening operator beside it with
    # `includeSpamTrash=true`, disclosing spam and trash as `role: matched` under
    # `outcome: answered` and `term_coverage: 1.0`.
    matchable = tuple(token for token in tokens if not carries_no_content(token.text))
    vacuous = tuple(
        token.text
        for token in tokens
        if token.role
        in {TokenRole.OPERATOR, TokenRole.PHRASE, TokenRole.TERM, TokenRole.UNKNOWN_OPERATOR}
        and carries_no_content(token.text)
    )
    operators = tuple(
        ParsedOperator(
            name=token.name,
            value=token.value,
            negated=token.negated,
            quoted=token.quoted,
        )
        for token in matchable
        if token.role is TokenRole.OPERATOR and token.name is not None
    )
    written_phrases = tuple(
        (token.value, token.negated) for token in matchable if token.role is TokenRole.PHRASE
    )
    phrases = tuple(value for value, negated in written_phrases if not negated)
    excluded_phrases = tuple(value for value, negated in written_phrases if negated)
    unknown = tuple(token.text for token in matchable if token.role is TokenRole.UNKNOWN_OPERATOR)
    passthrough = tuple(token.text for token in tokens if token.role is TokenRole.PASSTHROUGH)
    written_terms = [token.text for token in matchable if token.role is TokenRole.TERM]

    relative = find_relative_expression(" ".join(written_terms))
    window = window_from_operators(operators, now=now, zone=resolved_zone)
    window_is_derived = False
    if relative is not None:
        window = resolve_relative(relative, now=now, zone=resolved_zone)
        window_is_derived = True
        remaining = strip_relative_expression(" ".join(written_terms), relative)
        written_terms = [word for word in remaining.split() if word]

    terms = tuple(written_terms)
    # Stopwords are removed from what goes onto the wire and **named** where they went
    # (`enforced_declarations`), never dropped in silence: Gmail's `q` is a conjunction, so
    # leaving "the" in it additionally requires the message to contain the word "the", which
    # is a constraint the user did not state and a false negative waiting to happen. The
    # words removed are reported, which is the difference LEX-02 counts.
    search_terms = content_tokens(" ".join(terms))
    kept = set(search_terms)
    removed = tuple(word for word in (fold(term) for term in terms) if word not in kept)
    identifiers = tuple(
        identifier
        for identifier in (classify_identifier(term) for term in terms)
        if identifier is not None
    )
    content = content_tokens(" ".join((*terms, *phrases)))
    interrogative = classify_interrogative(query)
    return ParsedQuery(
        raw=query,
        tokens=tokens,
        operators=operators,
        terms=terms,
        search_terms=search_terms,
        removed_stopwords=removed,
        phrases=phrases,
        excluded_phrases=excluded_phrases,
        passthrough=passthrough,
        unknown_operators=unknown,
        vacuous_tokens=vacuous,
        participants=_participants(operators),
        identifiers=identifiers,
        constraints=_build_constraints(
            operators,
            written_phrases,
            search_terms,
            window,
            window_is_derived,
        ),
        interrogative=interrogative,
        answer_type=ANSWER_TYPE_BY_INTERROGATIVE[interrogative],
        confidence=_confidence(operators, identifiers, phrases, content),
        risk_factors=_risk_factors(operators, interrogative, identifiers, phrases, content),
        timezone=str(resolved_zone),
        window=window,
    )


def enforced_declarations(parsed: ParsedQuery, enforced: Sequence[Constraint]) -> tuple[str, ...]:
    """`asked_for.enforced`: the constraint names, plus A.6a rule 3's widening declaration.

    A.6a names `asked_for.enforced` as the place the widening is declared, so it goes there
    rather than into a field of our own invention. It is appended last so the constraint
    names stay a prefix of the tuple and `constraint_coverage` - which is checked against
    this same tuple - reads the same list a relaxation reads.
    """
    names = [constraint.name for constraint in enforced]
    declaration = widening_declaration(parsed.window)
    if declaration is not None and parsed.window is not None:
        date_names = {
            OperatorName.AFTER.value,
            OperatorName.BEFORE.value,
            OperatorName.NEWER_THAN.value,
            OperatorName.OLDER_THAN.value,
            DATE_WINDOW_CONSTRAINT,
        }
        if date_names & set(names):
            names.append(declaration)
    if parsed.removed_stopwords and TERMS_CONSTRAINT in {c.name for c in enforced}:
        names.append(f"stopwords_removed:{','.join(parsed.removed_stopwords)}")
    return tuple(names)


#: The constraint name an unparsed boolean or grouping token is declared under.
UNPARSED_SYNTAX_CONSTRAINT: Final[str] = "unparsed_syntax"
#: The constraint name a `name:value` token outside Gmail's documented set is declared under.
UNPROVEN_OPERATOR_CONSTRAINT: Final[str] = "unproven_operator"
#: The constraint name a parse that produced no constraint at all is declared under.
UNSEARCHABLE_QUERY_CONSTRAINT: Final[str] = "unsearchable_query"
#: The constraint name a token that names nothing for Gmail to match is declared under.
VACUOUS_TOKEN_CONSTRAINT: Final[str] = "selects_nothing"


def dropped_declarations(parsed: ParsedQuery) -> tuple[tuple[str, str], ...]:
    """`(constraint, why)` pairs for everything the parse could not carry into `q`.

    Four classes, and the last two are the ones that used to be silent:

      * **passthrough** - Gmail's boolean and grouping syntax, which `render` explains
        cannot be regrouped;
      * **unproven operator** - a `name:value` token outside Gmail's documented set
        (R-RETR-012). It used to ride into the executed `q` inside the residual terms and
        be named in no part of `asked_for` at all;
      * **a token that selects nothing** - an empty quoted phrase, an operator written with
        no value, a token of nothing but zero-width characters (R-RETR-017). It used to
        become an ordinary constraint, be probed on its own by L1b, and be composed by L3
        beside the widening scope operator with `includeSpamTrash=true`;
      * **an unsearchable query** - a parse that produced no constraint from a query that
        wrote something. That is a parse *failure*, and the honest answer to it is a
        declared inability. It used to be a whole-mailbox scan reported as `answered` with
        `term_coverage: 1.0` (R-RETR-006, BLOCKER).

    A tuple of pairs rather than of `DroppedConstraint` models so that this module - which
    knows about queries - does not import the response schema, which knows about
    disclosure. The ladder assembles the wire form.
    """
    declared: list[tuple[str, str]] = []
    if parsed.passthrough:
        tokens = " ".join(parsed.passthrough)
        declared.append(
            (
                UNPARSED_SYNTAX_CONSTRAINT,
                f"MailWeave does not parse Gmail's boolean and grouping syntax; {tokens!r} "
                "was not re-emitted, because a composed q regroups the query by constraint "
                "and a boolean token put back elsewhere would execute a query nobody wrote "
                "(RO F3)",
            )
        )
    for token in parsed.unknown_operators:
        declared.append(
            (
                UNPROVEN_OPERATOR_CONSTRAINT,
                f"{token!r} is a name:value token outside Gmail's documented operator set "
                "(RO F3, LEX-02), so MailWeave cannot prove what it would mean and does not "
                "execute it: conjoined into the q it could only narrow the search on a "
                "meaning nobody established. The search ran without it",
            )
        )
    for token in parsed.vacuous_tokens:
        declared.append(
            (
                VACUOUS_TOKEN_CONSTRAINT,
                f"{token!r} names nothing for Gmail to match - an empty quoted phrase, an "
                "operator written with no value, or a token of characters that carry no "
                "content - so it selects nothing and was not executed. A fragment that "
                "cannot narrow must not be widened to the whole mailbox instead "
                "(AD A.7 L3, R-RETR-017). The search ran without it",
            )
        )
    if parsed.carries_nothing_searchable:
        declared.append(
            (
                UNSEARCHABLE_QUERY_CONSTRAINT,
                f"the parse produced no constraint from {parsed.raw.strip()!r}, so there is "
                "nothing to search for. No rung ran: a query with nothing to narrow by "
                "cannot be widened to the whole mailbox instead, because the mailbox is not "
                "an answer to it (AD A.7 L3, R-RETR-006)",
            )
        )
    return tuple(declared)
