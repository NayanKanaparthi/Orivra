"""Gmail's documented operator set, and the tokeniser that finds it in a query (AD A.6).

**The lexicon is closed and it is Gmail's, not ours.** RO F3 enumerates the operators the
query language documents, and rubric LEX-02 requires that "operators used are limited to
Gmail's documented set". So `OperatorName` *is* that list, and a `name:value` token whose
name is not a member is not an operator here: it is recorded in
`ParsedQuery.unknown_operators`, kept **out** of the executed `q`, and declared dropped
under `unproven_operator` by `dropped_declarations`, so a reader of the response can see
that MailWeave declined to prove it rather than silently reinterpreting it.

That last clause is a correction (R-RETR-012, R-RETR-014). The token used to be conjoined
into the `q` as a residual term - narrowing the search on a meaning nobody had established -
and `unknown_operators` had no consumer on the wire, so "a reader can see" was true of a
reader of this process's memory and of nobody else.

What this module does **not** do is as load-bearing as what it does, so it is stated here
rather than discovered later:

  * it does not parse Gmail's boolean and grouping syntax - `OR`, `AND`, `(...)`, `{...}`.
    Those tokens are classified `passthrough` and are **not re-emitted** into the executed
    `q`, and they are declared dropped so no part of MailWeave claims to have understood
    them. `ParsedQuery.render`'s docstring is where the reason lives: a composed `q`
    regroups the query by constraint, so a boolean token put back elsewhere would execute a
    query nobody wrote. This paragraph used to say the opposite - "carried into the executed
    `q` byte for byte, so Gmail's own parser sees exactly what the user wrote" - which is
    false at the wire (`rollout OR escalation` is sent as `rollout escalation`) and was one
    of two round-15 docstrings contradicting each other about one behaviour (R-RETR-014);
  * it is not a Gmail query *evaluator*. Nothing here decides whether a message matches.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from mailweave.constants import (
    NEGATION_PREFIX,
    PHRASE_QUOTE,
    matchable_content_of,
    operator_token,
    query_tokens,
)


class OperatorName(StrEnum):
    """The operators RO F3 records from Gmail's own documentation, and no others.

    Adding a member is a claim that Gmail documents the operator, and the fidelity table in
    `tests/test_query_analysis.py` parses every member of this enum - so a member added
    without a parse is a failing test rather than an unproven claim in a docstring.
    """

    FROM = "from"
    TO = "to"
    CC = "cc"
    BCC = "bcc"
    DELIVEREDTO = "deliveredto"
    SUBJECT = "subject"
    AFTER = "after"
    BEFORE = "before"
    OLDER_THAN = "older_than"
    NEWER_THAN = "newer_than"
    LABEL = "label"
    CATEGORY = "category"
    IN = "in"
    IS = "is"
    HAS = "has"
    LIST = "list"
    FILENAME = "filename"
    SIZE = "size"
    LARGER = "larger"
    SMALLER = "smaller"
    RFC822MSGID = "rfc822msgid"


class OperatorKind(StrEnum):
    """What an operator **does** to the search. The one place that fact is written down.

    Two things are decided from this enum and they are different in kind. The relaxation
    order (AD A.7 L2) is written over these, which is a policy about which constraint to
    give up first. And the region asymmetry (OD-5 point 3, A9-A2) is decided by `REGION`
    alone, which is a statement about what Gmail is being asked: an operator either selects
    the region the search runs over or filters within whatever region is being searched.

    **`REGION` and `ATTRIBUTE` were one member called `LOCATION` until round 19, and that
    conflation is the finding this enum exists to close** (R-RETR-036). The predicate that
    decides whether a fragment declares the search region asked a *spelling* question -
    "does this token start with Gmail's location prefix?" - because the declared data could
    not answer it: `LOCATION` held the operator that names a mailbox region *and* the ones
    that name a message's state, its attachments, its list header and its filenames. A
    reviewer registered a new region-selecting operator exactly as an implementer would and
    2,274 tests stayed green while every probe dropped it, relaxed it away and widened out of
    it. The member is split rather than annotated so that the fact lives at the one place an
    operator is registered: `KIND_BY_OPERATOR` is total over `OperatorName`, so a member
    added without a kind fails a test, and the kind it is given is the answer.

    The old name is **removed** rather than kept as an alias. An operator registered against
    a name that no longer exists raises `AttributeError` at import; an operator registered
    against a name that still exists but no longer means what it meant would be classified
    as a filter in silence, which is the failure this split is repairing.

    `IDENTITY` is its own kind rather than a member of `ATTRIBUTE` because A.8a branch E-a
    turns on it alone: `rfc822msgid:` is an identity claim about a token, and grouping it
    with the attribute operators would put the ladder's strongest stop signal in a bucket
    the relaxation order is entitled to drop early.
    """

    PARTICIPANT = "participant"
    TEXT = "text"
    DATE = "date"
    #: Selects **which region of the mailbox** the search runs over. A fragment written with
    #: one of these is the region declaration, in either polarity, and no probe composed from
    #: a subset of the query's fragments may leave it out (`declares_the_search_region`).
    REGION = "region"
    #: Filters **within** whatever region is being searched, by a property of the message
    #: rather than by where it is filed. Omitting one widens the match inside the region,
    #: which costs precision and never recall, so a composed probe may leave it out.
    ATTRIBUTE = "attribute"
    SIZE = "size"
    IDENTITY = "identity"


KIND_BY_OPERATOR: Final[Mapping[OperatorName, OperatorKind]] = MappingProxyType(
    {
        OperatorName.FROM: OperatorKind.PARTICIPANT,
        OperatorName.TO: OperatorKind.PARTICIPANT,
        OperatorName.CC: OperatorKind.PARTICIPANT,
        OperatorName.BCC: OperatorKind.PARTICIPANT,
        OperatorName.DELIVEREDTO: OperatorKind.PARTICIPANT,
        OperatorName.SUBJECT: OperatorKind.TEXT,
        OperatorName.AFTER: OperatorKind.DATE,
        OperatorName.BEFORE: OperatorKind.DATE,
        OperatorName.OLDER_THAN: OperatorKind.DATE,
        OperatorName.NEWER_THAN: OperatorKind.DATE,
        # --- the three that say **where a message is filed** -------------------------
        # `label:` is here on the conservative reading and it is a decision, not an
        # oversight (R-RETR-036). A label can be a user's own and it can be one of Gmail's
        # system mailboxes, and telling the two apart needs a vocabulary of Gmail's system
        # label names that nothing in this repository can establish (R-GMAIL, A.6). The two
        # errors are not symmetrical: reading a region as a filter lets a probe search mail
        # the caller excluded and disclose it as a match, which is not recoverable; reading
        # a filter as a region withholds a relaxation, which costs recall and is recovered
        # by the caller taking the offer the response now carries. So every `label:` value
        # declares the region, and the recall it costs is paid back as an affordance.
        OperatorName.LABEL: OperatorKind.REGION,
        # `category:` names one of Gmail's inbox tabs, which is a place a message is filed
        # exactly as a mailbox is. Same reading, same reason.
        OperatorName.CATEGORY: OperatorKind.REGION,
        OperatorName.IN: OperatorKind.REGION,
        # --- and the four that describe **the message**, wherever it is filed ----------
        OperatorName.IS: OperatorKind.ATTRIBUTE,
        OperatorName.HAS: OperatorKind.ATTRIBUTE,
        OperatorName.LIST: OperatorKind.ATTRIBUTE,
        OperatorName.FILENAME: OperatorKind.ATTRIBUTE,
        OperatorName.SIZE: OperatorKind.SIZE,
        OperatorName.LARGER: OperatorKind.SIZE,
        OperatorName.SMALLER: OperatorKind.SIZE,
        OperatorName.RFC822MSGID: OperatorKind.IDENTITY,
    }
)
"""Every operator has exactly one kind. Checked by execution, not by reading.

Total over `OperatorName` - `test_the_kind_map_is_total_over_the_lexicon`
fails on a member with no entry - which is what makes this the registration point for
*what an operator does*. A region-selecting operator added tomorrow is carried by every
probe, refused to L2 and refused to the broadening step the moment this mapping says
`OperatorKind.REGION`, with no edit to a predicate and no edit to a test's oracle.
"""

#: The boolean and grouping tokens Gmail's query language carries and this module does not
#: parse. A token that is one of these, or that opens or closes a group, is `passthrough`.
UNPARSED_SYNTAX: Final[frozenset[str]] = frozenset({"OR", "AND", "|"})

#: Characters that open or close one of Gmail's groupings.
GROUP_OPENERS: Final[str] = "({"
GROUP_CLOSERS: Final[str] = ")}"


class TokenRole(StrEnum):
    """What one whitespace-delimited token of a query turned out to be."""

    OPERATOR = "operator"
    PHRASE = "phrase"
    TERM = "term"
    PASSTHROUGH = "passthrough"
    UNKNOWN_OPERATOR = "unknown_operator"


@dataclass(frozen=True)
class Token:
    """One whitespace-delimited token, with the quotes it carried recorded.

    `text` is the token exactly as written, so a `passthrough` token can be re-emitted byte
    for byte. Everything derived from it - the operator name, the unquoted value - is a
    separate field, because a normalised value that has replaced the original is a value no
    reader can check against what they typed.
    """

    text: str
    negated: bool
    role: TokenRole
    name: OperatorName | None = None
    value: str = ""
    quoted: bool = False


@dataclass(frozen=True)
class ParsedOperator:
    """One provable Gmail operator: a documented name, its value, and its polarity."""

    name: OperatorName
    value: str
    negated: bool = False
    quoted: bool = False

    @property
    def kind(self) -> OperatorKind:
        return KIND_BY_OPERATOR[self.name]

    def render(self) -> str:
        """The operator as it goes onto the wire in `q`.

        A value carrying whitespace is re-quoted, because Gmail separates operators by
        whitespace and an unquoted multi-word value would become two tokens - one of which
        would silently become a free-text term. That is a mis-execution of a constraint the
        response would still report as enforced (LEX-02).
        """
        value = (
            f'"{self.value}"'
            if (self.quoted or any(c.isspace() for c in self.value))
            else self.value
        )
        return f"{'-' if self.negated else ''}{self.name.value}:{value}"


def _unquote(value: str) -> tuple[str, bool]:
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        return value[1:-1], True
    return value, False


def _is_group_token(raw: str) -> bool:
    stripped = raw.strip("-")
    return bool(stripped) and (stripped[0] in GROUP_OPENERS or stripped[-1] in GROUP_CLOSERS)


#: `(` closes with `)` and `{` with `}`. A token opened with one and closed with the other is
#: not a group this module will read; it stays `passthrough` and is declared dropped.
_GROUP_CLOSER_FOR: Final[Mapping[str, str]] = MappingProxyType(
    dict(zip(GROUP_OPENERS, GROUP_CLOSERS, strict=True))
)


def _sole_operator_of_a_group(raw: str) -> tuple[str, bool] | None:
    """The one operator a grouped token holds, and its polarity - or `None`.

    **A group holding exactly one operator is that operator**, so it is re-emitted as one
    rather than dropped as syntax this module cannot regroup (round 19, R-RETR-035).
    `constants.operator_token` has assumed exactly this since round 13 - it strips Gmail's
    grouping punctuation before comparing - and the two disagreeing is what let a grouped
    region declaration through: the predicate family read a grouped, negated region
    operator as a region and the
    parser read it as unparsable syntax, so the fragment never became a constraint, the
    broadening gate never saw a region, and the published whole-mailbox step ran over a query
    that had excluded a region.

    Three things are refused rather than guessed, and each is a place a guess would invert
    the caller's meaning:

      * a group holding **more than one** token. `-(a OR b)` is `-a AND -b` and `(a OR b)` is
        neither of them; distributing a negation over a group is regrouping a boolean, which
        `tokenise` deliberately does not do. Such a token stays `passthrough`, is declared
        dropped, and `analysis.region_declarations_of` reads the region off the raw token so
        no rung widens out of it;
      * a **double negation**. `-(-x)` is `x` by a rule about negation nobody wrote down here;
      * an opener closed by the **other** grouping's closer.
    """
    outer_negated = raw.startswith(NEGATION_PREFIX) and len(raw) > 1
    body = raw[1:] if outer_negated else raw
    if len(body) < 2 or body[0] not in GROUP_OPENERS or body[-1] != _GROUP_CLOSER_FOR[body[0]]:
        return None
    inner = body[1:-1]
    if not inner or any(character in GROUP_OPENERS + GROUP_CLOSERS for character in inner):
        return None
    inner_negated = inner.startswith(NEGATION_PREFIX) and len(inner) > 1
    if inner_negated and outer_negated:
        return None
    return (inner[1:] if inner_negated else inner), (outer_negated or inner_negated)


def _documented_operator(raw: str, body: str, *, negated: bool) -> Token | None:
    """`body` read as one of Gmail's documented operators, or `None` when it is not one.

    One reading, used twice: for a bare token and for the one operator a group holds. The
    two used to be two code paths and a grouped operator went down neither of them.
    """
    head, separator, tail = body.partition(":")
    if not separator or not head or head.startswith(PHRASE_QUOTE):
        return None
    try:
        name = OperatorName(head.casefold())
    except ValueError:
        return None
    value, quoted = _unquote(tail)
    return Token(
        text=raw, negated=negated, role=TokenRole.OPERATOR, name=name, value=value, quoted=quoted
    )


def tokenise(query: str) -> tuple[Token, ...]:
    """Classify every whitespace-delimited token of `query`, losing none of them.

    **Total by construction**: every token gets exactly one `TokenRole`, and
    `test_every_token_of_every_fidelity_case_is_classified_exactly_once` executes that over
    the whole fidelity table rather than the docstring asserting it. A token that vanished
    here would be a constraint the response could report as neither enforced nor dropped,
    which is the silent drop LEX-02 counts.

    **The splitter is `constants.query_tokens`, not a copy of one** (round 18). This module
    used to carry its own `_split_outside_quotes`, and `constants`' predicate family split on
    whitespace - so `constants` and this module disagreed about how many tokens
    `-from:"Amy Smith"` is, and a negated participant with a quoted value became a
    whole-mailbox decomposition probe while the same constraint with an unquoted value was
    correctly refused. One splitter, read by both.

    **`name:value` is an operator only when `name` is unquoted** (R-RETR-018). The operator
    split used to run over the whole token before the quoted-phrase branch at the end of the
    loop could see it, so `"Re: quarterly plan"` - a reply subject, the most ordinary thing a
    user types - was read as an operator called `"Re`, rejected by `OperatorName`, and
    recorded as an unknown operator. R-RETR-012's fix then kept it out of the executed `q`,
    and R-RETR-006's fix then refused the whole query with zero Gmail calls: a phrase search
    that worked before those two fixes met, and eight of fifty plausible queries in the
    round-16 review's audit. A colon inside quotes is content, exactly as it already is
    inside `subject:"note: see below"`, which never broke because the operator branch
    unquotes its tail. `constants.operator_token` has said the same thing about the leading
    quote since round 13 - a quoted widening scope operator "is a phrase search rather than
    an operator, and
    reading it as one would be a false refusal" - and this is that sentence applied where the
    reading is done rather than where the scope coupling compares. Executed by
    `test_a_quoted_phrase_containing_a_colon_is_a_phrase_not_an_unknown_operator`.
    """
    classified: list[Token] = []
    for raw in query_tokens(query):
        if not raw:
            continue
        if raw in UNPARSED_SYNTAX:
            classified.append(Token(text=raw, negated=False, role=TokenRole.PASSTHROUGH))
            continue
        if _is_group_token(raw):
            sole = _sole_operator_of_a_group(raw)
            grouped = None if sole is None else _documented_operator(raw, sole[0], negated=sole[1])
            classified.append(
                grouped
                if grouped is not None
                else Token(text=raw, negated=False, role=TokenRole.PASSTHROUGH)
            )
            continue
        negated = raw.startswith(NEGATION_PREFIX) and len(raw) > 1
        body = raw[1:] if negated else raw
        operator = _documented_operator(raw, body, negated=negated)
        if operator is not None:
            classified.append(operator)
            continue
        head, separator, _tail = body.partition(":")
        if separator and head and not head.startswith(PHRASE_QUOTE):
            classified.append(
                Token(text=raw, negated=negated, role=TokenRole.UNKNOWN_OPERATOR, value=body)
            )
            continue
        value, quoted = _unquote(body)
        classified.append(
            Token(
                text=raw,
                negated=negated,
                role=TokenRole.PHRASE if quoted else TokenRole.TERM,
                value=value,
                quoted=quoted,
            )
        )
    return tuple(classified)


def operator_of(fragment: str) -> OperatorName | None:
    """The documented operator this `q` fragment writes, or `None` when it writes none.

    **The reading here is deliberately wider than `tokenise`'s, and the direction matters.**
    `tokenise` decides what MailWeave will *execute*, so it reads a token as the user wrote
    it. This decides what a fragment *asks Gmail for*, and it is read by the region rules -
    so it normalises first, through `constants.operator_token`: NFKC, then Gmail's grouping
    punctuation off both ends, then case-folded. A token the parser could not read as an
    operator is still a token Gmail may read as one, and the two errors are not symmetrical.
    Classifying a region declaration as an ordinary token lets a composed probe leave it out
    and search mail the caller excluded; classifying an ordinary token as a region
    declaration withholds a relaxation. Only the first is unrecoverable, so this side reads
    generously and the executed `q` does not.

    The leading quote of a phrase is **not** stripped and a quoted head is refused, for the
    reason `tokenise` gives at the same test: `"9:30 standup"` is a phrase, and reading it as
    an operator called `"9` would be a false refusal.
    """
    token = operator_token(fragment)
    body = token[1:] if token.startswith(NEGATION_PREFIX) else token
    head, separator, _tail = body.partition(":")
    if not separator or not head or head.startswith(PHRASE_QUOTE):
        return None
    try:
        return OperatorName(head)
    except ValueError:
        return None


def declares_the_search_region(fragment: str) -> bool:
    """Whether this fragment says **which region of the mailbox** the search runs over.

    ---

    **The asymmetry rule, stated once, in terms of what an operator does** (OD-5, A9).

        A fragment of a query either **declares the region** the search runs over - which
        messages Gmail will consider at all, and with them whether `includeSpamTrash` is
        set - or it **filters within** whatever region is being searched. A probe composed
        from a subset of a query's fragments may leave out a *filter*: omitting one can only
        widen the match **inside** the region, which costs precision and never recall, and
        is the direction such a probe is allowed to be wrong in. It may **not** leave out a
        region declaration: omitting one widens nothing, it moves the probe to a *different*
        region, where it can match messages the query excluded and miss messages the query
        asked for. **Polarity decides which region a declaration names. It never decides
        whether a fragment is one.**

    Round 17 stated that asymmetry over three token classes and put every negation in the
    "may be left out" class, on the reasoning that "and not this, removed" is a superset.
    True of `-from:x`, which filters within a region. False of a negated mailbox region,
    which **is** the region declaration: "everywhere but spam" is a region exactly as "spam"
    is one, so dropping it does not widen within the region, it replaces the region with a
    different one (R-RETR-026).

    ---

    **This predicate lives here, in the module that registers the operators, because the
    question it asks is answered by the registry** (round 19, R-RETR-036). Round 18 wrote
    the rule above correctly and then implemented it as
    `token.startswith(MAILBOX_LOCATION_PREFIX)` - the spelling of one operator, not the
    behaviour of any. The docstring claimed "a scope operator added tomorrow is covered the
    moment it is a location"; a reviewer registered one exactly as an implementer would and
    the whole suite stayed green while every probe dropped it, L2 relaxed it away and L3
    widened out of it. What generalised was *a new value under one prefix*, which is not what
    A9-A2 binds. So the question is now put to `KIND_BY_OPERATOR`, which is the field that
    records what an operator constrains and is total over `OperatorName`: an operator
    declared `OperatorKind.REGION` is covered by every rule below the moment it is
    registered, and one declared anything else is a filter, in both polarities, with no
    predicate to edit and no test oracle to extend.

    Two residues round 18 named honestly and this round decides rather than re-names:

      * **`label:`** - it can name a user's own label or one of Gmail's system mailboxes, and
        nothing here can tell them apart (R-GMAIL, A.6). It is registered `REGION`, so every
        `label:` value declares the region. That is the conservative half of an asymmetric
        choice, and `KIND_BY_OPERATOR` carries the reasoning beside the entry;
      * **grouping and fullwidth spellings** - `operator_token` normalises both away here, so
        the predicate reads a grouped or fullwidth spelling as the operator it is.
        Whether the *parser* should too is a normalisation policy question (A.6, WS-10); what
        closes the boundary meanwhile is that `analysis.region_declarations_of` asks this
        predicate of the query's raw tokens as well as of its parsed fragments, so a region
        the parse could not carry still stops the broadening step.

    A fragment carrying no matchable content declares nothing: `label:` with no value names
    no region, exactly as it names nothing to search for.
    """
    name = operator_of(fragment)
    return (
        name is not None
        and KIND_BY_OPERATOR[name] is OperatorKind.REGION
        and bool(matchable_content_of(fragment))
    )
