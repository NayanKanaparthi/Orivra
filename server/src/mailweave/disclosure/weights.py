"""E4 query-scored fill: the **published** weights, and the components they weight (AD A.9(3)).

**Why the weights are constants and why they are published here.** A weight that can move
is a weight that can be tuned to a benchmark, and WS-17 sweeps for exactly that. So the
five components of A.9(3) are an enum, their weights are a frozen mapping in this module,
and the reason string a filled row carries is built out of the enum rather than written as
prose - which is what makes the policy explainable for a query nobody has written yet
(RR DISC-01's degenerate-strategy guard: *a policy that keys on fixture features is not
query-aware, it is fixture-aware*).

**Why these five and no others.** A.9(3) names them: participant match (address-keyed),
subject/snippet term overlap, temporal proximity to a hit or to a query date-ref,
thread-position adjacency, and decision-cue lexicon match. `FillComponent` is that list and
`E4_WEIGHTS` is total over it, so a component added later has to be given a weight and a
reason in the same edit.

**Why the ordering of the weights is what it is.** Read the table top to bottom; each line
is a reason, not a preference:

1. `PARTICIPANT_MATCH` (5) is the only component computed from a header **Gmail states**
   about this message - its own `From`/`To`/`Cc` - matched against an address the *query
   named*. It is the most query-driven and the least text-dependent signal available, and
   it is available on a row this response holds only as a stub, so it does not become
   stronger merely because a message happened to have its body fetched.
2. `TERM_OVERLAP` (4) is the query's own words, which is as query-driven as (1), and it
   ranks below it for one mechanical reason: a term can land in text this message
   **quoted** from another message, so a term match is evidence about the thread as often
   as about the message. (1) cannot be borrowed that way.
3. `TEMPORAL_PROXIMITY` (3) is partly query-driven - it fires on the query's own parsed
   date window as well as on nearness to a hit - and partly structural. Below the two that
   are wholly query-driven, above the one that is wholly structural.
4. `POSITION_ADJACENCY` (2) is structural, and query-*conditioned* only through the hit it
   measures distance from. Its radius is deliberately Baseline F(±2)'s own radius: see
   `E4_ADJACENCY_POSITIONS`.
5. `DECISION_CUE` (1) is the **only** component that fires identically for every query
   against a given mailbox. A query-independent component that could outrank a
   query-derived one would be a way for the policy to look adaptive while behaving like a
   constant, which is precisely DISC-01's guard. It therefore carries strictly the least
   weight of any component, so it can break a tie and can never by itself order one
   candidate ahead of another that the query reached.
   `test_no_query_independent_component_can_outrank_a_query_derived_one` executes that
   sentence rather than trusting this paragraph.

The weights are small integers because the score is compared and rendered, never
interpolated: integer arithmetic makes ties exact rather than float-adjacent, so the
ordering of two candidates cannot depend on the platform's rounding.

**Amendment A11, in one sentence, because it is the round-25 change to this module.** A
component that fires identically on every candidate of a thread ranks but does not admit on
that thread, and a candidate's rank may not be decided by query-independent components
alone. That is A.9(3)'s existing `POSITION_ADJACENCY` rule generalised from *the component*
to *the component's behaviour on this thread*. It adds no weight and moves none;
`E4_WEIGHTS` is byte-identical to what round 23 published. What it changes is which fired
components may **admit** (`message_discriminating_facts`, `rank`) and what the ordering key
is allowed to contain (`rank`, `FillScore.anchored_value`).

**Nothing here reads a model, an embedding or a corpus.** `generative_llm_calls = 0` is a
hard constant (AD D.8) and every predicate below is a table lookup, a set intersection or a
subtraction of two integers.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final

from mailweave.envelope.vocab import FillComponent
from mailweave.query.analysis import (
    DECISION_VERBS,
    content_tokens,
    fold,
    strip_reply_prefixes,
)

#: The published weights. Frozen, total over `FillComponent`, and asserted total by
#: `test_every_published_component_carries_a_published_weight`.
E4_WEIGHTS: Final[Mapping[FillComponent, int]] = MappingProxyType(
    {
        FillComponent.PARTICIPANT_MATCH: 5,
        FillComponent.TERM_OVERLAP: 4,
        FillComponent.TEMPORAL_PROXIMITY: 3,
        FillComponent.POSITION_ADJACENCY: 2,
        FillComponent.DECISION_CUE: 1,
    }
)

#: The components whose firing depends on what the caller asked. Four of the five: the
#: decision lexicon is the same for every query, which is why it carries the least weight.
#: Derived as a complement rather than listed, so a component added later is treated as
#: query-independent until somebody argues otherwise - the safe default, and the opposite
#: of the one a hand-written list produces.
QUERY_INDEPENDENT_COMPONENTS: Final[frozenset[FillComponent]] = frozenset(
    {FillComponent.DECISION_CUE}
)
QUERY_DERIVED_COMPONENTS: Final[frozenset[FillComponent]] = (
    frozenset(FillComponent) - QUERY_INDEPENDENT_COMPONENTS
)

#: One calendar day, in seconds. **Published, and here is the derivation.** Gmail's own
#: date operators are day-granular - `after:`/`before:`/`newer_than:` take dates, not
#: instants (AD A.6) - so a day is the finest interval a user's query can express. A
#: proximity window finer than the query language's own resolution would be a threshold
#: nobody could have written, and one coarser would make "near a hit" mean "in this
#: thread". It is one day because that is the unit the query is written in.
E4_TEMPORAL_PROXIMITY_SECONDS: Final[int] = 86_400

#: **Two, because Baseline F is ±2.** The fixed-window baseline this policy is measured
#: against at equal budget (RR DISC-02, EP §8.8) takes the two positions either side of a
#: hit for free. Giving the adjacency component the *same* radius means the query-aware
#: arm gets no more structural reach than the baseline does, so any measured win is
#: attributable to the four other components rather than to a wider window - and the
#: comparison cannot be won by quietly widening this number. It is the one weight-table
#: constant a reviewer should attack first, and it is pinned to the baseline on purpose.
E4_ADJACENCY_POSITIONS: Final[int] = 2

#: A candidate scoring this or less is not filled. **Zero, and the zero is the rule**: a
#: row no component of the query reached carries no query-specific reason, and DISC-01
#: requires every inclusion to carry one.
E4_MINIMUM_FILL_SCORE: Final[int] = 0

#: **The components that may *admit* a row, as opposed to rank one.** A score above zero is
#: necessary and is not sufficient, and this set is why.
#:
#: `POSITION_ADJACENCY` fires on nearness to a hit and `TEMPORAL_PROXIMITY`'s first disjunct
#: fires on nearness in time to a hit. Neither reads anything the caller wrote: for a query
#: that names one term and nothing else, admitting on those two alone would fill exactly the
#: positions within `E4_ADJACENCY_POSITIONS` of every hit - which **is** Baseline F(±2),
#: emitted under the query-aware policy's name. That is DISC-01's degenerate strategy
#: precisely ("a fixed ±2 policy fails DISC-01 by construction"), and it would have shipped
#: unnoticed because the two arms would agree on the easy cases and the score would look
#: query-derived in the reason string.
#:
#: So a row is filled only when at least one component **anchored in what the query wrote**
#: fired: an address it named, a term it wrote, or its own date window. The other components
#: still contribute their published weight to the *ordering* of admitted rows, which is what
#: they are good for - they say which of the query's own matches to read first, not which
#: messages are worth reading. `WindowOffset` remains the reason kind for a positional
#: inclusion, and it belongs to Baseline F.
#:
#: `TEMPORAL_PROXIMITY` is in this set **conditionally**: it anchors on the query's parsed
#: date window and not on nearness to a hit, which is why `anchoring_components` takes the
#: candidate and the query rather than only the fired set.
#:
#: **Membership here is necessary and not sufficient (amendment A11).** Round 23 shipped this
#: set as the whole of the repair and it fixed half of one: `TERM_OVERLAP` reads the subject,
#: Gmail sends one subject per thread, so on the modal query class - a term that appears in
#: the subject - the anchored component fired on *every* candidate. It admitted everything
#: and separated nothing, which left `POSITION_ADJACENCY` as the only thing ordering the
#: admitted rows, and the E4 top class was Baseline F's ±2 window position for position. Six
#: materially different queries against one thread produced zero differing pairs.
#:
#: So a component in this set admits on a thread only where it also **separates** one of that
#: thread's candidates from another: see `message_discriminating_facts` and `rank`. The rule
#: is computed from the thread rather than written against the subject, because the same
#: degeneracy arrives through a participant on every recipient list and through a date window
#: the whole thread sits inside, and it will arrive again through a fact nobody has added yet.
ADMITTING_COMPONENTS: Final[frozenset[FillComponent]] = frozenset(
    {
        FillComponent.PARTICIPANT_MATCH,
        FillComponent.TERM_OVERLAP,
        FillComponent.TEMPORAL_PROXIMITY,
    }
)


@dataclass(frozen=True)
class FillCandidate:
    """Everything the five predicates read about one message, and nothing else.

    A frozen record rather than the row itself, for `StopInputs`' reason: a predicate that
    can reach past its inputs into the payload acquires dependencies the published policy
    does not have, and then the policy is no longer the thing the document describes.
    """

    message_id: str
    position: int
    #: Addresses this message's own `From`/`To`/`Cc`/`Reply-To` carry, folded.
    addresses: frozenset[str]
    #: The subject, and whatever text this response observed for this message - a fetched
    #: body's default view, or the `threads.get` snippet. Never text this response did not
    #: see: a candidate with neither is scored on the components that do not need text.
    subject: str
    observed_text: str | None
    internal_date_ms: int | None
    #: Distance in thread positions to the nearest hit of this thread, or `None` when this
    #: thread has no hit (a sibling source recovered structurally).
    positions_from_nearest_hit: int | None
    #: Seconds between this message's `internalDate` and the nearest hit's, or `None`.
    seconds_from_nearest_hit: int | None
    #: Whether this message's `internalDate` lies inside the query's parsed date window.
    inside_query_date_window: bool


@dataclass(frozen=True)
class QueryFacts:
    """The part of a `ParsedQuery` the fill reads. Folded once, here, not per candidate."""

    #: Addresses the query named through a participant operator, folded.
    participants: frozenset[str]
    #: The query's content tokens, folded and stopword-stripped.
    terms: frozenset[str]
    #: Whether the query carried a date window at all. Used only to keep the temporal
    #: component honest about which half of its disjunction fired.
    has_date_window: bool

    @classmethod
    def of(
        cls,
        *,
        participants: Iterable[str],
        terms: Iterable[str],
        has_date_window: bool,
    ) -> QueryFacts:
        return cls(
            participants=frozenset(fold(value) for value in participants if value),
            terms=frozenset(fold(value) for value in terms if value),
            has_date_window=has_date_window,
        )


def _tokens(text: str) -> frozenset[str]:
    """The comparison tokens of a piece of text, from the parser's own tokenizer.

    `content_tokens` rather than `str.split` so that `"decided,"` and `"decided"` are one
    token: a lexicon match that depended on the punctuation next to a word would fire on
    the corpus somebody wrote and not on the mailbox.
    """
    return frozenset(content_tokens(text))


#: The name of every **fact** a component reads about one candidate. Named rather than
#: implied because amendment A11's rule is about facts: a fact whose value is the same on
#: every candidate of a thread cannot separate one candidate from another, whatever the
#: component that reads it is worth. Gmail decides which facts those are - it sends one
#: subject per thread - so the set is *computed from the thread*, never listed here.
SUBJECT: Final[str] = "subject"
OBSERVED_TEXT: Final[str] = "observed_text"
ADDRESSES: Final[str] = "addresses"
INSIDE_QUERY_DATE_WINDOW: Final[str] = "inside_query_date_window"
SECONDS_FROM_NEAREST_HIT: Final[str] = "seconds_from_nearest_hit"
POSITIONS_FROM_NEAREST_HIT: Final[str] = "positions_from_nearest_hit"

#: Every fact the five predicates read, as a closed set, so `fact_values` and
#: `components_of` cannot drift apart: a predicate reading a fact that is not here would be
#: invisible to A11's rule, which is exactly the failure the rule exists to catch.
CANDIDATE_FACTS: Final[frozenset[str]] = frozenset(
    {
        SUBJECT,
        OBSERVED_TEXT,
        ADDRESSES,
        INSIDE_QUERY_DATE_WINDOW,
        SECONDS_FROM_NEAREST_HIT,
        POSITIONS_FROM_NEAREST_HIT,
    }
)


def fact_values(candidate: FillCandidate) -> Mapping[str, object]:
    """This candidate's value for every fact the components read, comparably.

    Token sets rather than raw strings for the two text facts, because that is what the
    predicates compare: two messages whose subjects differ only in a `Re:` prefix carry the
    same subject *as the components read it*, and A11's question is whether the component
    can tell them apart.

    **The `Re:` sentence above was false of this function until round 26** (R-DISC-031).
    `content_tokens` keeps `re` as a content token, so `S` tokenised to seven tokens and
    `Re: S` to eight, and `subject` came out message-discriminating on every Gmail thread
    of more than one message - the exact fact A11 was written about, readmitted by two
    characters Gmail wrote. `strip_reply_prefixes` is applied **here and nowhere else**: the
    published score, the row's reason and every wire field still carry the subject Gmail
    sent, and what changes is only whether A11 counts two of them as different.
    """
    return {
        SUBJECT: _tokens(strip_reply_prefixes(candidate.subject)),
        OBSERVED_TEXT: (
            None if candidate.observed_text is None else _tokens(candidate.observed_text)
        ),
        ADDRESSES: candidate.addresses,
        INSIDE_QUERY_DATE_WINDOW: candidate.inside_query_date_window,
        SECONDS_FROM_NEAREST_HIT: candidate.seconds_from_nearest_hit,
        POSITIONS_FROM_NEAREST_HIT: candidate.positions_from_nearest_hit,
    }


def message_discriminating_facts(candidates: Sequence[FillCandidate]) -> frozenset[str]:
    """Which facts differ between at least two candidates of this thread (amendment A11).

    A fact with one value across the whole candidate set is a **thread-level fact**, and a
    component that fired only from thread-level facts fired identically on every candidate:
    it says nothing about *which* message, so under A11 it ranks and does not admit. The
    modal instance is the subject - Gmail sends one per thread, so a query term that appears
    in it fires `TERM_OVERLAP` on every message - and the rule is computed rather than
    written against that instance, so it holds for the participant on every recipient list,
    the date window the whole thread sits inside, and the fact nobody has added yet.

    A thread with fewer than two candidates has no fact that separates one candidate from
    another, and this returns the empty set for it. That is A11's sentence read literally
    ("separates at least one candidate from another") and it is the right answer: with one
    candidate there is no selection being made, and the E2 floor and the map already carry it.
    """
    if len(candidates) < 2:
        return frozenset()
    first = fact_values(candidates[0])
    return frozenset(
        name
        for name in CANDIDATE_FACTS
        if any(fact_values(candidate)[name] != first[name] for candidate in candidates[1:])
    )


def components_of(
    candidate: FillCandidate, query: QueryFacts, *, facts: frozenset[str] = CANDIDATE_FACTS
) -> tuple[FillComponent, ...]:
    """Which of the five components fire for this candidate, in published order.

    Every branch is a set intersection or an integer comparison. A component whose input
    this response does not hold - no observed text, no `internalDate` - does **not** fire,
    and does not fire *negatively* either: an absence is an absence, which is the same rule
    `MailboxProvenance.unobserved()` states one layer down.

    `facts` narrows which of the candidate's facts a predicate may read. The **published
    score** is always computed over `CANDIDATE_FACTS`, all of them, and is what a row's
    reason names; the narrowed call is how A11's admission rule is evaluated, by asking the
    same predicates what they would say if they could see only the facts that differ within
    this thread. One set of predicates, asked twice - not a second policy.
    """
    fired: list[FillComponent] = []
    if ADDRESSES in facts and query.participants and candidate.addresses & query.participants:
        fired.append(FillComponent.PARTICIPANT_MATCH)
    if query.terms:
        haystack: frozenset[str] = frozenset()
        if SUBJECT in facts:
            haystack |= _tokens(candidate.subject)
        if OBSERVED_TEXT in facts and candidate.observed_text is not None:
            haystack |= _tokens(candidate.observed_text)
        if haystack & query.terms:
            fired.append(FillComponent.TERM_OVERLAP)
    near_in_time = (
        SECONDS_FROM_NEAREST_HIT in facts
        and candidate.seconds_from_nearest_hit is not None
        and candidate.seconds_from_nearest_hit <= E4_TEMPORAL_PROXIMITY_SECONDS
    )
    inside_window = INSIDE_QUERY_DATE_WINDOW in facts and candidate.inside_query_date_window
    if inside_window or near_in_time:
        fired.append(FillComponent.TEMPORAL_PROXIMITY)
    if (
        POSITIONS_FROM_NEAREST_HIT in facts
        and candidate.positions_from_nearest_hit is not None
        and candidate.positions_from_nearest_hit <= E4_ADJACENCY_POSITIONS
    ):
        fired.append(FillComponent.POSITION_ADJACENCY)
    if (
        OBSERVED_TEXT in facts
        and candidate.observed_text is not None
        and _tokens(candidate.observed_text) & DECISION_VERBS
    ):
        fired.append(FillComponent.DECISION_CUE)
    return tuple(fired)


def score_of(components: Sequence[FillComponent]) -> int:
    """The published sum. No normalisation, no decay, no per-query rescaling."""
    return sum(E4_WEIGHTS[component] for component in components)


def anchoring_components(
    candidate: FillCandidate, query: QueryFacts, fired: Sequence[FillComponent]
) -> tuple[FillComponent, ...]:
    """Which of the fired components are anchored in something the caller wrote.

    The temporal component is the only conditional member: it fires on two disjuncts and only
    one of them - the query's own parsed date window - is anchored. Nearness to a hit is
    nearness to something *this system* found, which is a fact about the thread and not about
    the request.
    """
    anchored: list[FillComponent] = []
    for component in fired:
        if component not in ADMITTING_COMPONENTS:
            continue
        if component is FillComponent.TEMPORAL_PROXIMITY and not (
            query.has_date_window and candidate.inside_query_date_window
        ):
            continue
        anchored.append(component)
    return tuple(anchored)


@dataclass(frozen=True)
class FillScore:
    """One candidate's score and the components behind it, ready to become a reason."""

    message_id: str
    components: tuple[FillComponent, ...]
    value: int
    #: The subset of `components` that both anchor in what the query wrote **and** separate
    #: this candidate from another candidate of the same thread (amendment A11). Empty means
    #: nothing the caller wrote picked this message out of its thread, which is not a reason
    #: to disclose it - whether because no anchored component fired at all, or because the one
    #: that fired fired on every message of the thread and so chose none of them.
    anchored: tuple[FillComponent, ...] = ()

    @property
    def anchored_value(self) -> int:
        """The part of the score the query's own evidence is responsible for.

        A11's ordering half is enforced against this rather than against `value`: a
        candidate's **rank** may not be decided by query-independent components alone, so the
        query-anchored, thread-discriminating weight decides first and the published score
        only orders candidates the query reached equally.
        """
        return score_of(self.anchored)

    @property
    def fills(self) -> bool:
        return self.value > E4_MINIMUM_FILL_SCORE and bool(self.anchored)


def score(
    candidate: FillCandidate,
    query: QueryFacts,
    *,
    discriminating: frozenset[str] = CANDIDATE_FACTS,
) -> FillScore:
    """One candidate's published score, plus what of it may admit on this thread.

    `components` and `value` are the published policy, computed over every fact - unchanged,
    and unchanged deliberately: A11 is not a new weight and a row's reason still names what
    actually fired. `anchored` is the admission question, and it is asked of the same
    predicates over the facts that differ within the thread.
    """
    fired = components_of(candidate, query)
    separating = components_of(candidate, query, facts=discriminating)
    return FillScore(
        message_id=candidate.message_id,
        components=fired,
        value=score_of(fired),
        anchored=anchoring_components(
            candidate, query, tuple(c for c in fired if c in frozenset(separating))
        ),
    )


def a11_scores(
    candidates: Sequence[FillCandidate], query: QueryFacts
) -> tuple[tuple[FillCandidate, FillScore], ...]:
    """**Amendment A11's two guards over one pool, stated once.** Both callers read this.

    *The narrowing.* `message_discriminating_facts` removes the thread-level facts a
    component may have fired from, so a component reading only facts identical across the
    pool has nothing anchored left.

    *The all-or-none sweep.* A component whose surviving fire still covers **every** member
    of the pool, or none, is removed from every member's `anchored` set - because a component
    that admits everything separates nothing, and DISC-01 is a claim about *which* messages a
    query selected.

    **Why this is a function rather than two copies** (round 26, R-DISC-034). `rank` had both
    guards and `plan.hit_ranks` had only the first, so on Gmail's own `Re:` shape the subject
    was mis-classified as discriminating, the sweep was not there to catch it, and every hit
    scored the same nonzero value - which makes `_top_k_hit_ids`' position tie-break the whole
    selection, i.e. oldest-K, the degenerate strategy EV-02's second guard names by
    construction. One rule in one place, so a third pool added later inherits both halves
    rather than half of them.

    The pool order is preserved; `rank` sorts, `hit_ranks` does not.
    """
    pool = tuple(candidates)
    discriminating = message_discriminating_facts(pool)
    scored = [
        (candidate, score(candidate, query, discriminating=discriminating)) for candidate in pool
    ]
    admitted_by: dict[FillComponent, set[str]] = {}
    for _candidate, result in scored:
        for component in result.anchored:
            admitted_by.setdefault(component, set()).add(result.message_id)
    separating = frozenset(
        component for component, reached in admitted_by.items() if 0 < len(reached) < len(pool)
    )
    return tuple(
        (candidate, replace(result, anchored=tuple(c for c in result.anchored if c in separating)))
        for candidate, result in scored
    )


def rank(candidates: Iterable[FillCandidate], query: QueryFacts) -> tuple[FillScore, ...]:
    """Every candidate the query separated from its thread, best first, ties by position.

    **Amendment A11, both halves.** The admission half is `a11_scores`, which `plan.hit_ranks`
    calls too; what is here is the ordering half and the fill's own admission threshold.

    *Ordering.* The key is the **anchored** score and then the thread position, and the
    query-independent components are not in it at all. A11's second sentence is the reason:
    *a candidate's rank may not be decided by query-independent components alone*, and for
    any two candidates the query reached equally they would decide alone - which is not a
    corner case but the modal one. Round 23 repaired admission and left the ordering, and on
    the modal query class the ordering **was** Baseline F: every candidate scored 4 from a
    subject-carried `TERM_OVERLAP`, the only component left to separate them was the ±2
    adjacency, and the top score class of the "query-aware" ranking was the ±2 window
    position for position (R-DISC-018).

    **Said plainly, because it is a consequence worth seeing:** `POSITION_ADJACENCY` and
    `DECISION_CUE` keep their published weights and their place in a row's reason and score,
    and after A11 they order nothing. A11 forbids exactly that ordering role, and a weight
    whose only remaining effect is descriptive is a question for WS-17's sweep and for the
    owner, not something this module may quietly answer by keeping them in the key.

    The last key is the thread position rather than the id, and that is deliberate: two
    candidates the query reached equally are ordered by where they sit in the conversation,
    which is a fact of the thread. Ordering them by id would order them by an opaque Gmail
    string, which is a coin flip presented as a ranking (RANK-03).
    """
    keeping = [pair for pair in a11_scores(tuple(candidates), query) if pair[1].fills]
    keeping.sort(key=lambda pair: (-pair[1].anchored_value, pair[0].position))
    return tuple(result for _, result in keeping)
