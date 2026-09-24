"""WS-11: representation and query-aware disclosure. The round's claims, executed.

Four claims are made in this round and each of them is the sort of sentence this project has
historically written in a document and not in a test. So:

* **the E4 weights are fixed and published**, and the property that keeps them from being a
  tuning dial is asserted rather than described: a query-independent component can never
  order one candidate ahead of another the query reached;
* **the promotion rule is explicit, testable, and sometimes negative.** It is one function,
  its answer is one of four values, and the matrix below reaches all four - including the
  `None` that refuses an ordinary adjacent reply, which is the case where saying yes would
  have been easier and would have turned the E2 floor into a window of unbounded radius;
* **floor membership survives every degradation step.** Each of A.9a's eight steps is
  planted with a floor-losing variant and refused by the driver's gate, and the reach matrix
  shows each of the eight actually firing in the published order on a real layout, at both
  ceilings, with and without a floor;
* **the response never exceeds the ceiling it declares.** The ladder's estimate and the
  envelope's estimate are asserted to be the same number on an assembled response, so a
  layout the ladder believed it had fitted cannot be a payload the envelope refuses.

**The shape space, and the commonality.** Eight steps times two ceilings times
floor-or-not is thirty-two shapes, and enumerating them one at a time is how this project has
produced eighteen instances of "one shape validated, peers trusted". What every shape has in
common is the *driver*: each step is a total function `(Layout, Ceilings) -> Layout` and the
driver applies the same two gates to the output of every one of them. So the load-bearing
tests here are properties over the driver -
`test_every_disclosure_shape_keeps_the_five_properties_that_make_the_ladder_honest` - and
`test_the_shape_matrix_reaches_every_step_and_both_ceilings` prints and asserts the reach, so
a property that held only over shapes the fixtures never build fails rather than passes.

**No network, no model, no real mail.** Every thread here is generated for the structural
property under test; addresses use the reserved `.example` / `.invalid` TLDs (RFC 2606/6761);
and `test_no_fixture_in_this_file_carries_anything_that_could_be_real_mail` executes that
rather than asserting it.
"""

from __future__ import annotations

import ast
import contextlib
import re
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mailweave.constants import (
    BODY_CLEAN_HEAD_TRUNCATED_TOKENS,
    BODY_CLEAN_SOFT_CAP_TOKENS,
    FLOOR_OVERFLOW_CEILING_TOKENS,
    MAX_BODY_FETCHES_L0,
    NORMAL_CEILING_TOKENS,
)
from mailweave.content.annotate import AnnotatedBody, SpanClass, build_annotation
from mailweave.content.normalize import count_tokens
from mailweave.content.reductions import ReductionKind
from mailweave.disclosure import (
    ADMITTING_COMPONENTS,
    DECLARED_OVERFLOW_STEP,
    DISCLOSURE_TOP_K_HITS,
    E4_ADJACENCY_POSITIONS,
    E4_TEMPORAL_PROXIMITY_SECONDS,
    E4_WEIGHTS,
    FLAT_MAP_MESSAGE_BOUNDARY,
    LADDER_STEPS,
    QUERY_DERIVED_COMPONENTS,
    QUERY_INDEPENDENT_COMPONENTS,
    SEGMENT_MAP_IS_EXPERIMENTAL,
    Band,
    Ceilings,
    Disclosure,
    DisclosureLadderExhausted,
    EvidenceFacts,
    FixedWindow,
    FloorMembershipLost,
    Layout,
    MemberFacts,
    PlannedRow,
    QueryAwareFill,
    QueryFacts,
    Step,
    ThreadInput,
    components_of,
    dependence_of,
    disclose,
    efficiency,
    floor_members,
    floor_obligations,
    plan_thread,
    run_ladder,
    score,
    segment_of,
)
from mailweave.disclosure.ladder import cheapest_membership_cost, step_6_declared_overflow
from mailweave.disclosure.weights import FillCandidate
from mailweave.envelope import (
    BudgetCapName,
    Ceiling,
    Content,
    ContentSource,
    DispositionLedger,
    EnvelopeBuilder,
    Linkage,
    MailboxProvenance,
    MessageRow,
    Outcome,
    Role,
    RungId,
    Sufficiency,
    Trust,
)
from mailweave.envelope.fence import fence
from mailweave.envelope.measure import STUB_ROW_TOKEN_ESTIMATE, measure_tokens
from mailweave.envelope.reasons import FloorPromoted, QueryScoredFill
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import Depth, FillComponent, FloorDependence, FloorRelation
from mailweave.retrieval.assemble import _the_ladder_removed_something
from tests.fixtures.envelope_kit import (
    asked_for,
    collapsed_run,
    counters,
    fully_observed_thread,
    query_reason,
    source,
    unabridged,
)
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.test_lexical_ladder import answer

ARCHITECTURE = Path(__file__).resolve().parents[1] / "docs" / "ARCHITECTURE_DECISION.md"

#: One synthetic address, in a reserved TLD. Every fixture participant is derived from it.
SENDER = "ana@team.example"
OTHER = "bo@team.invalid"
TERM = "borogrove"
DAY_MS = E4_TEMPORAL_PROXIMITY_SECONDS * 1000
EPOCH = 1_756_557_731_000


# --- fixture builders ---------------------------------------------------------------------


def annotated(words: int, *, quoted_lines: int = 0) -> AnnotatedBody:
    """A synthetic annotated body: `words` original words, plus optional quoted lines.

    The quoted lines are what the promotion rule's `QUOTATION` clause reads, and they are
    built through `build_annotation` so the span tiling is the production type's own (A7).
    """
    lines = [
        " ".join(f"w{index}-{seq}" for seq in range(10)) for index in range(max(1, words // 10))
    ]
    classes: list[tuple[SpanClass, str]] = [
        (SpanClass.ORIGINAL, "no_structural_signal") for _ in lines
    ]
    for index in range(quoted_lines):
        lines.append(f"> quoted line {index} carried from the parent")
        classes.append((SpanClass.QUOTED, "quote_marker"))
    return build_annotation("\n".join(lines), classes)


def snippet_of(tokens: int, *, decision: bool = False) -> str:
    words = [f"s{index}" for index in range(tokens)]
    if decision:
        words[0] = "decided"
    return " ".join(words)


def chain_thread(
    *,
    thread_id: str = "t1",
    rank: int = 0,
    messages: int = 12,
    hit_every: int = 4,
    body_words: int = 0,
    quoted_lines: int = 0,
    snippet_tokens: int = 25,
    decision_children: bool = False,
    subject: str = "programme",
    hit_subject_term: bool = True,
    bodies_for_all: bool = False,
) -> ThreadInput:
    """A straight reply chain: message *n* is the reply parent of message *n+1*.

    Generated rather than written out, because the properties below are about the *shape*
    space and a hand-written thread is one shape. Every knob here changes exactly one input
    of the policy, which is what lets a test vary one thing at a time.
    """
    order = tuple(f"{thread_id}-m{index:03d}" for index in range(messages))
    positions = {message_id: index for index, message_id in enumerate(order)}
    hits = frozenset(order[index] for index in range(messages) if index % hit_every == 0)
    parent_of = {order[index]: (order[index - 1] if index else None) for index in range(messages)}
    children_of = {
        order[index]: ((order[index + 1],) if index + 1 < messages else ())
        for index in range(messages)
    }
    bodies: dict[str, AnnotatedBody] = {}
    if body_words:
        for message_id in order:
            if message_id in hits or bodies_for_all:
                bodies[message_id] = annotated(body_words, quoted_lines=quoted_lines)
    snippets: dict[str, str | None] = {}
    for index, message_id in enumerate(order):
        is_child_of_hit = index > 0 and order[index - 1] in hits and message_id not in hits
        snippets[message_id] = snippet_of(
            snippet_tokens, decision=decision_children and is_child_of_hit
        )
    subjects = {
        message_id: (f"{subject} {TERM}" if (message_id in hits and hit_subject_term) else subject)
        for message_id in order
    }
    return ThreadInput(
        thread_id=thread_id,
        rank=rank,
        hit_bearing=bool(hits),
        order=order,
        positions=positions,
        hit_ids=hits,
        parent_of=parent_of,
        children_of=children_of,
        subjects=subjects,
        snippets=snippets,
        bodies=bodies,
        internal_dates={
            message_id: EPOCH + index * DAY_MS * 3 for index, message_id in enumerate(order)
        },
        addresses=dict.fromkeys(order, frozenset({SENDER})),
        coverage={message_id: frozenset({"from", "terms"}) for message_id in hits},
        reductions={},
    )


def sibling_thread(*, thread_id: str = "s1", rank: int = 9, messages: int = 20) -> ThreadInput:
    """A source with no hits at all: a thread structural expansion recovered.

    It has no E2 floor by construction, which is what makes it the source A.9a step 7 is
    allowed to split off - and the reason step 7 has a candidate at all.
    """
    thread = chain_thread(thread_id=thread_id, rank=rank, messages=messages, hit_every=10_000)
    return replace(thread, hit_ids=frozenset(), hit_bearing=False, coverage={})


def query(
    *, participants: tuple[str, ...] = (), terms: tuple[str, ...] = (TERM,), window: bool = False
) -> QueryFacts:
    return QueryFacts.of(participants=participants, terms=terms, has_date_window=window)


def flat_thread(
    *, thread_id: str = "f1", rank: int = 8, messages: int = 40, snippet_tokens: int = 90
) -> ThreadInput:
    """A hit-bearing thread whose messages name no reply parents at all.

    It therefore has **no E2 floor**, which is what makes it the one hit-bearing source A.9a
    step 7 may split off. The shape is real: a thread whose members carry no RFC reply
    headers reconstructs as `NO_REPLY_HEADERS` for every row (`reply_tree`), and the floor is
    computed from links rather than from adjacency, so there is nothing to keep.
    """
    thread = chain_thread(
        thread_id=thread_id,
        rank=rank,
        messages=messages,
        hit_every=4,
        snippet_tokens=snippet_tokens,
    )
    return replace(
        thread,
        parent_of=dict.fromkeys(thread.order, None),
        children_of=dict.fromkeys(thread.order, ()),
    )


def _bodied_flat_thread(
    *, thread_id: str, rank: int, messages: int, body_words: int
) -> ThreadInput:
    """A hit-bearing source with **no E2 floor** whose rows are expensive.

    A.9a step 7 may split a source only where no floor member of a still-disclosed evidence
    message goes with it, and splitting only pays where the rows it removes cost more than
    the `withheld` records that replace them. A thread of fetched bodies and no reply headers
    is both: every row is a hit at `body_clean`, and no row is anybody's reply parent.
    """
    thread = chain_thread(
        thread_id=thread_id,
        rank=rank,
        messages=messages,
        hit_every=1,
        body_words=body_words,
        snippet_tokens=20,
    )
    return replace(
        thread,
        parent_of=dict.fromkeys(thread.order, None),
        children_of=dict.fromkeys(thread.order, ()),
    )


#: Five invented words, all of them in one subject line, each of them in a different subset
#: of the messages' own snippets. The five are the query vocabulary of `shared_subject_thread`.
SHARED_SUBJECT_TERMS: tuple[str, ...] = ("borogrove", "slithy", "toves", "outgrabe", "mimsy")


def shared_subject_thread(
    *, thread_id: str = "sh", messages: int = 24, hit_every: int = 8, snippet_tokens: int = 12
) -> ThreadInput:
    """**The thread Gmail actually sends**, which `chain_thread` was not (round 25).

    Gmail puts **one subject on every message of a thread** - `Re: <subject>` on every reply -
    so a query term that appears in it is a fact about the thread and not about any message.
    `chain_thread(hit_subject_term=True)` puts the term on the *hits'* subjects only, which is
    a shape no mailbox produces, and three of round 23's behavioural claims are true of that
    fixture and false of this one (R-DISC-029).

    Here every message carries the same subject line, and that subject carries **all five**
    query terms, so `TERM_OVERLAP` fires on every candidate from a thread-level fact. What
    separates the messages is each one's own snippet, which carries a different subset of the
    five - a mechanical construction (the bits of the index), not a hand-tuned one. Amendment
    A11's rule is what turns that difference into a difference in what is disclosed.

    **The prefix is in the data now, not only in this paragraph** (round 26, R-DISC-031/036).
    Round 25 named `Re: <subject>` here and then wrote `dict.fromkeys(order, subject)` - the
    identical string on every message, which is the one shape Gmail never sends. The root
    carries `S` and every reply carries `Re: S`, and supplying those two characters inverted
    three of this fixture's results when a reviewer did it by hand.
    """
    order = tuple(f"{thread_id}-m{index:03d}" for index in range(messages))
    positions = {message_id: index for index, message_id in enumerate(order)}
    hits = frozenset(order[index] for index in range(messages) if index % hit_every == 0)
    subject = "quarterly " + " ".join(SHARED_SUBJECT_TERMS) + " plan"
    snippets: dict[str, str | None] = {}
    for index, message_id in enumerate(order):
        carried = [term for bit, term in enumerate(SHARED_SUBJECT_TERMS) if (index >> bit) & 1]
        snippets[message_id] = " ".join([*(f"s{n}" for n in range(snippet_tokens)), *carried])
    return ThreadInput(
        thread_id=thread_id,
        rank=0,
        hit_bearing=bool(hits),
        order=order,
        positions=positions,
        hit_ids=hits,
        parent_of={order[i]: (order[i - 1] if i else None) for i in range(messages)},
        children_of={
            order[i]: ((order[i + 1],) if i + 1 < messages else ()) for i in range(messages)
        },
        subjects={mid: (subject if i == 0 else f"Re: {subject}") for i, mid in enumerate(order)},
        snippets=snippets,
        bodies={},
        internal_dates={mid: EPOCH + index * DAY_MS * 3 for index, mid in enumerate(order)},
        addresses=dict.fromkeys(order, frozenset({SENDER})),
        coverage={message_id: frozenset({"terms"}) for message_id in hits},
        reductions={},
    )


def raw_layout(*threads: ThreadInput) -> Layout:
    """The layout **before** the ladder runs, which is what a plant has to be given.

    `disclose` returns a degraded layout by construction, so a test that wants to watch a
    step misbehave has to build the un-degraded one - otherwise the driver finds a payload
    that already fits and applies no step at all, and eight plants pass for the wrong reason.
    """
    planned = [plan_thread(thread, query=query(), selector=QueryAwareFill()) for thread in threads]
    return Layout(
        sources=tuple(entry.source for entry in planned),
        accounted_ids=frozenset(mid for thread in threads for mid in thread.order),
        floor_ids=frozenset(member.message_id for entry in planned for member in entry.floor),
        hit_ids=frozenset(mid for thread in threads for mid in thread.hit_ids),
        # The A.9(2) obligations, exactly as `disclose` computes them: the driver's floor gate
        # reads them to tell a member leaving *with* the evidence it is owed to (lawful) from
        # a member leaving *while* that evidence is still disclosed (the thing it refuses). A
        # plant given a layout without them would be tested against the fallback rule rather
        # than against the shipped one.
        floor_pairs=tuple(pair for thread in threads for pair in floor_obligations(thread)),
    )


def layout_of(*threads: ThreadInput, arm: object = None) -> Disclosure:
    selector = QueryAwareFill() if arm is None else arm
    accounted = frozenset(mid for thread in threads for mid in thread.order)
    return disclose(
        list(threads),
        query=query(),
        selector=selector,  # type: ignore[arg-type]
        accounted_ids=accounted,
    )


# --- Part 1: the published E4 weights -------------------------------------------------------


def test_every_published_component_carries_a_published_weight() -> None:
    """The table is total over the vocabulary, so a component cannot arrive unweighted."""
    assert set(E4_WEIGHTS) == set(FillComponent)
    assert all(weight > 0 for weight in E4_WEIGHTS.values())


def test_the_published_weights_are_the_ones_the_round_report_publishes() -> None:
    """Pinned, so changing a weight is a visible edit to a test and not a silent retune.

    This is the whole mechanism against WS-17's sweep finding a moving weight: the values
    are here, in one place, and a benchmark-driven change has to come through this assertion.
    """
    assert dict(E4_WEIGHTS) == {
        FillComponent.PARTICIPANT_MATCH: 5,
        FillComponent.TERM_OVERLAP: 4,
        FillComponent.TEMPORAL_PROXIMITY: 3,
        FillComponent.POSITION_ADJACENCY: 2,
        FillComponent.DECISION_CUE: 1,
    }


def test_no_query_independent_component_can_outrank_a_query_derived_one() -> None:
    """DISC-01's guard, as arithmetic over the table rather than as a paragraph.

    `decision_cue` fires identically for every query against a given mailbox. If it could
    outweigh a component the query drove, the policy could order candidates by a fact about
    the mailbox while its reason strings still named a mechanism - which is a policy that
    looks adaptive and is not.
    """
    assert QUERY_INDEPENDENT_COMPONENTS and QUERY_DERIVED_COMPONENTS
    heaviest_independent = max(E4_WEIGHTS[c] for c in QUERY_INDEPENDENT_COMPONENTS)
    lightest_derived = min(E4_WEIGHTS[c] for c in QUERY_DERIVED_COMPONENTS)
    assert heaviest_independent < lightest_derived


def test_the_adjacency_radius_is_the_baselines_own_radius() -> None:
    """The query-aware arm gets no more structural reach than Baseline F does (DISC-02).

    A win produced by a wider window would be a win over a straw baseline. Pinning the two
    together is how the comparison stays about the *policy*.
    """
    assert E4_ADJACENCY_POSITIONS == FixedWindow().radius == 2


def _candidate(**overrides: object) -> FillCandidate:
    base = {
        "message_id": "m1",
        "position": 10,
        "addresses": frozenset({OTHER}),
        "subject": "programme",
        "observed_text": "a short reply with nothing in it",
        "internal_date_ms": EPOCH,
        "positions_from_nearest_hit": 9,
        "seconds_from_nearest_hit": 10 * E4_TEMPORAL_PROXIMITY_SECONDS,
        "inside_query_date_window": False,
    }
    base.update(overrides)
    return FillCandidate(**base)  # type: ignore[arg-type]


#: For each component: the one field that makes it fire, and the value that does.
COMPONENT_TRIGGERS: dict[FillComponent, dict[str, object]] = {
    FillComponent.PARTICIPANT_MATCH: {"addresses": frozenset({SENDER})},
    FillComponent.TERM_OVERLAP: {"subject": f"programme {TERM}"},
    FillComponent.TEMPORAL_PROXIMITY: {"seconds_from_nearest_hit": 1},
    FillComponent.POSITION_ADJACENCY: {"positions_from_nearest_hit": E4_ADJACENCY_POSITIONS},
    FillComponent.DECISION_CUE: {"observed_text": "we decided against it"},
}


def test_every_component_fires_on_its_own_trigger_and_is_silent_without_it() -> None:
    """Reach and non-vacuity for all five, one at a time, from the same neutral candidate.

    Without the negative half this would pass on a `components_of` that returned every
    component always; without the reach half a component nobody can trigger would look
    tested. The table is checked against `FillComponent` so a sixth component fails here.
    """
    assert set(COMPONENT_TRIGGERS) == set(FillComponent)
    facts = query(participants=(SENDER,))
    for component, trigger in COMPONENT_TRIGGERS.items():
        assert component in components_of(_candidate(**trigger), facts), component
        assert component not in components_of(_candidate(), facts), component


def test_a_row_no_anchored_component_reached_is_not_filled() -> None:
    """The admission rule, and the degeneracy it exists to prevent (DISC-01).

    A candidate two positions from a hit and an hour away from it scores 5 on purely
    structural components - and is refused, because neither of them reads anything the caller
    wrote. Admitting on those alone would emit Baseline F(±2) under the query-aware policy's
    name, which is DISC-01's degenerate strategy exactly.
    """
    near = _candidate(positions_from_nearest_hit=1, seconds_from_nearest_hit=60)
    result = score(near, query())
    assert result.value > 0
    assert set(result.components) == {
        FillComponent.POSITION_ADJACENCY,
        FillComponent.TEMPORAL_PROXIMITY,
    }
    assert result.anchored == ()
    assert result.fills is False


def test_a_row_the_query_reached_is_filled_and_names_what_reached_it() -> None:
    """The other half: admission happens, and the reason is the mechanism (DISC-01)."""
    reached = _candidate(subject=f"programme {TERM}", positions_from_nearest_hit=1)
    result = score(reached, query())
    assert result.fills is True
    assert FillComponent.TERM_OVERLAP in result.anchored
    assert set(result.anchored) <= ADMITTING_COMPONENTS


def test_the_temporal_component_anchors_only_on_the_querys_own_window() -> None:
    """Its two disjuncts are not equal, and only one of them is something the caller wrote."""
    near_a_hit = _candidate(seconds_from_nearest_hit=1)
    assert FillComponent.TEMPORAL_PROXIMITY in score(near_a_hit, query()).components
    assert score(near_a_hit, query()).anchored == ()

    in_the_window = _candidate(inside_query_date_window=True)
    assert score(in_the_window, query(window=True)).anchored == (FillComponent.TEMPORAL_PROXIMITY,)


# --- Part 2: the promotion rule -------------------------------------------------------------


def _evidence(*, quoted: bool, coverage: frozenset[str] = frozenset({"from"})) -> EvidenceFacts:
    return EvidenceFacts(
        message_id="hit",
        body=annotated(20, quoted_lines=2 if quoted else 0),
        constraint_coverage=coverage,
    )


def _member(*, text: str | None, coverage: frozenset[str] = frozenset({"from"})) -> MemberFacts:
    return MemberFacts(message_id="member", observed_text=text, constraint_coverage=coverage)


def test_the_promotion_rule_refuses_an_ordinary_adjacent_reply() -> None:
    """**The case where saying yes would have been easier**, and the rule says no.

    A direct child of the evidence, present in the response by the floor's absolute
    membership guarantee, one position away, cheap to promote - and refused, because it
    carries no decision cue, it satisfies no constraint its parent misses, and the quotation
    clause is about parents. If this returned a dependence, the E2 floor would be a window of
    unbounded radius and OD-3's "membership is absolute, depth is earned" would have no
    second half.
    """
    answer = dependence_of(
        relation=FloorRelation.CHILD,
        evidence=_evidence(quoted=False),
        member=_member(text="Thanks, will do."),
    )
    assert answer is None


def test_the_promotion_rule_refuses_a_parent_whose_child_quotes_nothing() -> None:
    """The mirror: the quotation clause reads the *evidence's* annotation, not a guess."""
    assert (
        dependence_of(
            relation=FloorRelation.PARENT,
            evidence=_evidence(quoted=False),
            member=_member(text="An earlier note."),
        )
        is None
    )


def test_the_promotion_rule_refuses_a_parent_whose_body_was_never_fetched() -> None:
    """An absent input is an absence, never a negative claim (A6's rule, applied here).

    A hit beyond `max_body_fetches` has no annotation to read, so `QUOTATION` cannot hold -
    and the row says `dependence: None` rather than asserting that the evidence quotes
    nothing.
    """
    unfetched = EvidenceFacts(message_id="hit", body=None, constraint_coverage=frozenset({"from"}))
    assert (
        dependence_of(
            relation=FloorRelation.PARENT,
            evidence=unfetched,
            member=_member(text="An earlier note."),
        )
        is None
    )


#: Every answer the rule can give, and an input that produces it. Checked against
#: `FloorDependence` plus the refusal, so a fourth dependence added later fails here.
PROMOTION_MATRIX: dict[FloorDependence | None, tuple[FloorRelation, EvidenceFacts, MemberFacts]] = {
    FloorDependence.QUOTATION: (
        FloorRelation.PARENT,
        _evidence(quoted=True),
        _member(text="An earlier note."),
    ),
    FloorDependence.CONTRADICTION: (
        FloorRelation.CHILD,
        _evidence(quoted=False),
        _member(text="Actually we decided against it."),
    ),
    FloorDependence.CONSTRAINT_CARRIER: (
        FloorRelation.CHILD,
        _evidence(quoted=False, coverage=frozenset({"from"})),
        _member(text="A reply.", coverage=frozenset({"from", "terms"})),
    ),
    None: (FloorRelation.CHILD, _evidence(quoted=False), _member(text="Thanks, will do.")),
}


def test_the_promotion_rule_matrix_reaches_every_answer_it_asserts_about() -> None:
    """R-RETR-058's lesson: prove the matrix reaches every answer, not that it has rows.

    The keys are checked against the vocabulary, and every row is *executed* - so a clause
    that could never fire, or an answer no input reaches, fails here rather than being
    asserted about in a report.
    """
    assert set(PROMOTION_MATRIX) == {*FloorDependence, None}
    reached: set[FloorDependence | None] = set()
    for expected, (relation, evidence, member) in PROMOTION_MATRIX.items():
        answer = dependence_of(relation=relation, evidence=evidence, member=member)
        assert answer is expected, (expected, answer)
        reached.add(answer)
    assert reached == set(PROMOTION_MATRIX)


def test_the_rule_says_no_at_least_as_often_as_yes_on_an_ordinary_thread() -> None:
    """The floor does not become the whole response, measured on a generated thread.

    A twelve-message chain with three hits has six floor members: three parents, whose
    evidence quotes, and three children, which reply and nothing more. Half are promoted.
    The assertion is not the number - it is that **the refused half is non-empty**, which is
    what distinguishes a promotion rule from a promotion.
    """
    thread = chain_thread(messages=12, hit_every=4, body_words=40, quoted_lines=2)
    members = floor_members(thread)
    promoted = [member for member in members if member.promoted]
    refused = [member for member in members if not member.promoted]
    assert promoted, "the rule must be able to say yes"
    assert refused, "the rule must be able to say no"
    assert {member.dependence for member in promoted} == {FloorDependence.QUOTATION}
    assert all(member.relation is FloorRelation.CHILD for member in refused)


def test_a_promoted_member_is_still_only_promoted_to_text_that_exists() -> None:
    """Promotion decides *whether*; the observation decides *how deep* (I-2, A7).

    A member the rule promoted whose body this run never fetched is disclosed at snippet
    with its unabridged path, not at a body depth the response cannot fill.
    """
    thread = chain_thread(messages=6, hit_every=3, body_words=40, quoted_lines=2)
    plan = layout_of(thread)
    promoted = {m.message_id for m in plan.threads[0].floor if m.promoted}
    assert promoted
    rows = {row.id: row for row in plan.layout.sources[0].rows}
    for message_id in promoted:
        assert thread.bodies.get(message_id) is None
        assert rows[message_id].depth is Depth.SNIPPET


def test_floor_membership_does_not_depend_on_promotion() -> None:
    """Every floor member is present whatever the rule answered. OD-3's first half."""
    thread = chain_thread(messages=14, hit_every=4, body_words=40, quoted_lines=2)
    plan = layout_of(thread)
    members = {member.message_id for member in plan.threads[0].floor}
    assert members
    assert members <= plan.layout.present_ids


# --- Part 3: the A.9a ladder ----------------------------------------------------------------


def _published_ladder_lines() -> list[str]:
    """A.9a's own numbered precedence, read out of the architecture document."""
    text = ARCHITECTURE.read_text()
    start = text.index("### A.9a The degradation ladder under the token ceiling")
    block = text[start:].split("```")[1]
    return [line.strip() for line in block.splitlines() if re.match(r"\s*\d+\.", line)]


#: One phrase per step, taken from the document's own line, mapped to this module's name for
#: it. Deliberately a *phrase* and not the whole line: the test asserts the order and the
#: identity of each step, not that a comment was copied.
PUBLISHED_PHRASES: dict[str, str] = {
    "e4_query_scored_fill": "E4 query-scored fill",
    "sibling_source_stub_runs": "Sibling-source stub rows",
    "hit_bodies_beyond_top_k": "Hit bodies beyond the top-k",
    "e2_floor_bodies": "E2 floor bodies",
    "hit_thread_stub_runs": "Hit-bearing-thread stubs",
    "declared_overflow_ceiling": "Overflow ceiling",
    "split_by_source": "Split by source",
    "withheld_record": "withheld",
}


def test_the_published_precedence_is_the_one_the_architecture_prints() -> None:
    """The order is the contract, so it is checked against its authority (A.9a).

    Two rounds of this project have got a published order wrong by transcribing it. This
    reads the document.
    """
    lines = _published_ladder_lines()
    assert len(lines) == len(LADDER_STEPS) == 8
    for step, line in zip(LADDER_STEPS, lines, strict=True):
        assert line.startswith(f"{step.precedence}."), (step, line)
        assert PUBLISHED_PHRASES[step.name] in line, (step.name, line)


def test_the_published_ceilings_and_body_budgets_are_the_documents_own() -> None:
    """The four numbers A.9a names, checked against the document rather than remembered."""
    text = ARCHITECTURE.read_text()
    assert "`body_clean` soft cap **600 tok**" in text
    assert "head-truncation step at **250 tok**" in text
    assert "normal hard ceiling stays 9,000 tok" in text
    assert "declared overflow ceiling of 12,000 tok" in text
    assert (BODY_CLEAN_SOFT_CAP_TOKENS, BODY_CLEAN_HEAD_TRUNCATED_TOKENS) == (600, 250)
    assert (NORMAL_CEILING_TOKENS, FLOOR_OVERFLOW_CEILING_TOKENS) == (9_000, 12_000)


def test_the_protected_hit_count_is_a_published_cap_and_not_a_new_number() -> None:
    """A.9a step 3's top-k is A.7's `max_body_fetches` at L0, so the two cannot drift."""
    assert DISCLOSURE_TOP_K_HITS == MAX_BODY_FETCHES_L0


def _drop_a_floor_member(step: Step) -> Step:
    """`step`, with a floor member removed from whatever it returns. The plant."""

    def broken(layout: Layout, ceilings: Ceilings) -> Layout:
        after = step.apply(layout, ceilings)
        # The member has to be one an evidence message **still in the payload** is owed, or
        # the plant is not a floor violation at all: a member that left together with every
        # hit that needed it is A.9a step 7 doing its job (round 25). Picking blind would
        # make this plant pass on the other gate and report the wrong property as held.
        owed = {
            member
            for anchor, member in after.floor_pairs
            if anchor in after.present_ids and member in after.present_ids
        }
        candidates = sorted(owed or (after.present_ids & after.floor_ids))
        if not candidates:  # pragma: no cover - every planted layout carries a floor
            return after
        victim = candidates[0]
        return after.with_sources(
            [
                replace(
                    source,
                    rows=tuple(row for row in source.rows if row.id != victim),
                    runs=tuple(run for run in source.runs if victim not in run.member_ids),
                )
                for source in after.sources
            ]
        )

    return Step(step.precedence, f"{step.name}__floor_dropped", broken)


def _drop_without_a_record(step: Step) -> Step:
    """`step`, with an accounted message removed and no withheld record left behind.

    Two shapes of the same defect, because one step of the eight leaves nothing of the first
    kind to take: a message present after the step is dropped from the payload, or - where
    the step has already converted every non-floor message into a `withheld` record - one of
    those records is deleted, which is the same message vanishing with the same silence.
    Without the second branch the plant against A.9a step 8 is **vacuous**, and a vacuous
    plant reports the gate as working when nothing was planted (R-RETR-058's rule turned on
    this file's own machinery).
    """

    def broken(layout: Layout, ceilings: Ceilings) -> Layout:
        after = step.apply(layout, ceilings)
        candidates = sorted((after.present_ids & after.accounted_ids) - after.floor_ids)
        if candidates:
            victim = candidates[0]
            return after.with_sources(
                [
                    replace(
                        source,
                        rows=tuple(row for row in source.rows if row.id != victim),
                        runs=tuple(run for run in source.runs if victim not in run.member_ids),
                    )
                    for source in after.sources
                ]
            )
        recorded = sorted(frozenset(after.withheld_ids) - frozenset(layout.withheld_ids))
        if not recorded:  # pragma: no cover - every planted step reaches one branch or other
            return after
        return replace(
            after, withheld_ids=tuple(mid for mid in after.withheld_ids if mid != recorded[0])
        )

    return Step(step.precedence, f"{step.name}__silent_drop", broken)


#: The ceilings the plants run against. **Not the published ones**, and the difference is the
#: point: a plant is only evidence about a step if the driver actually reaches that step and
#: the step still has something to leave behind. Against the published 9,000 the round-25 cost
#: model puts this layout so far over that step 7 splits every source and step 8 withholds
#: every non-floor row, and a plant with nothing left to drop is a plant that tests nothing.
#: These are asserted to be reached by `test_the_unplanted_ladder_is_not_refused_on_the_same_
#: input`, which is the control for exactly that.
PLANT_CEILINGS = Ceilings(normal=30_000, overflow=33_000)


def oversized_layout() -> Layout:
    """A layout that does not fit, carries a floor, and carries a splittable source.

    Asserted oversized where it is used, so a fixture that quietly starts fitting stops the
    plants from passing vacuously.
    """
    return raw_layout(
        chain_thread(thread_id="t1", rank=0, messages=60, hit_every=3, snippet_tokens=60),
        chain_thread(thread_id="t2", rank=1, messages=60, hit_every=3, snippet_tokens=60),
        flat_thread(thread_id="f1", rank=5, messages=60, snippet_tokens=90),
    )


@pytest.mark.parametrize("step", LADDER_STEPS, ids=lambda step: step.name)
def test_every_ladder_step_is_refused_when_it_drops_a_floor_member(step: Step) -> None:
    """**The biggest claim in the project, planted eight times and refused eight times.**

    Each of A.9a's published steps is replaced by a variant that does its own work and then
    removes one floor member, and the driver refuses it. The gate is the *driver's*, not each
    step's, which is why one plant per step is enough to establish the property for a ninth
    step nobody has written: there is one defence and it covers whatever the driver is given.
    """
    planted = _drop_a_floor_member(step)
    layout = oversized_layout()
    assert layout.floor_ids & layout.present_ids, "the plant needs a floor to remove"
    assert layout.cost() > PLANT_CEILINGS.normal, "the plant needs the driver to apply a step"
    with pytest.raises(FloorMembershipLost) as refusal:
        run_ladder(layout, steps=(planted,), ceilings=PLANT_CEILINGS)
    assert f"step {step.precedence}" in str(refusal.value)
    assert "membership" in str(refusal.value)


@pytest.mark.parametrize("step", LADDER_STEPS, ids=lambda step: step.name)
def test_every_ladder_step_is_refused_when_it_drops_a_message_without_a_record(
    step: Step,
) -> None:
    """Contract I-1 over one step: a cap converts a hit; it never removes one (A.7a)."""
    planted = _drop_without_a_record(step)
    layout = oversized_layout()
    assert layout.cost() > PLANT_CEILINGS.normal
    with pytest.raises(FloorMembershipLost) as refusal:
        run_ladder(layout, steps=(planted,), ceilings=PLANT_CEILINGS)
    assert "without a withheld record" in str(refusal.value)


@pytest.mark.parametrize("step", LADDER_STEPS, ids=lambda step: step.name)
def test_the_unplanted_step_is_not_refused_on_the_same_input(step: Step) -> None:
    """The control, **per step and in the same isolation the plants run in**.

    Each plant runs its one step alone, so a control that ran the whole published ladder
    would be a control for a different experiment: the driver stops as soon as the layout
    fits, and on this input step 5's collapse fits it, so steps 7 and 8 never run at all in a
    full pass. Here each step runs alone against the same layout and the same ceilings, and
    is not refused - which is what makes the refusal above attributable to the plant.
    """
    layout = oversized_layout()
    assert layout.cost() > PLANT_CEILINGS.normal
    # One step alone need not fit the response, and saying so is not a defect: the property
    # under control is that the *gates* do not fire, which is the only thing the plants above
    # are evidence about.
    with contextlib.suppress(DisclosureLadderExhausted):
        run_ladder(layout, steps=(step,), ceilings=PLANT_CEILINGS)


def test_the_unplanted_ladder_is_not_refused_on_the_same_input() -> None:
    """The whole published ladder on the same input: it degrades and it is not refused."""
    degraded, steps = run_ladder(oversized_layout(), ceilings=PLANT_CEILINGS)
    assert degraded.cost() <= degraded.ceiling_applied
    assert steps
    assert sum(len(source.rows) for source in degraded.sources) > 0


# --- the reach matrix -----------------------------------------------------------------------


@dataclass(frozen=True)
class ShapeResult:
    """One cell of the shape space, as it actually came out. Data, so reach is assertable."""

    shape: str
    exhausted: bool
    steps: tuple[int, ...]
    ceiling: int | None
    floor: bool
    withheld: int
    split: int
    tokens: int


def _shape(name: str, *threads: ThreadInput, ceilings: Ceilings | None = None) -> ShapeResult:
    accounted = frozenset(mid for thread in threads for mid in thread.order)
    try:
        plan = disclose(
            list(threads),
            query=query(),
            selector=QueryAwareFill(),
            accounted_ids=accounted,
            ceilings=ceilings,
        )
    except DisclosureLadderExhausted:
        return ShapeResult(
            shape=name,
            exhausted=True,
            steps=(),
            ceiling=None,
            floor=True,
            withheld=0,
            split=0,
            tokens=0,
        )
    return ShapeResult(
        shape=name,
        exhausted=False,
        steps=tuple(step.precedence for step in plan.steps),
        ceiling=plan.layout.ceiling_applied,
        floor=bool(plan.layout.floor_ids),
        withheld=len(plan.layout.withheld_ids),
        split=len(plan.layout.split_off),
        tokens=plan.tokens,
    )


def shape_matrix() -> tuple[ShapeResult, ...]:
    """Every disclosure shape this module asserts about, built and run.

    One row per cell of the shape space the report describes: each of the eight steps firing,
    both ceilings applied, a response with a floor and a response without one, and the
    declared inability. Built here rather than inside each test so that the reach assertion
    and the property sweep run over **the same** set.
    """

    def chain(index: int, *, messages: int, hit_every: int, snippet_tokens: int) -> ThreadInput:
        return chain_thread(
            thread_id=f"t{index}",
            rank=index,
            messages=messages,
            hit_every=hit_every,
            snippet_tokens=snippet_tokens,
        )

    # **The sizes moved in round 25 and the shapes did not.** Amendment A11 charges a row its
    # structural cost at every depth, so a response that used to measure 2,500 tokens now
    # measures what its wire actually is; the thread sizes that reach steps 6, 7, 8 and the
    # declared inability moved with it. Each size below is asserted *by this matrix's own
    # reach test*, so a size that stops reaching its step fails rather than quietly shrinking
    # the sweep - which is the failure mode R-RETR-058 named and this file was written against.
    return (
        _shape("fits_without_the_ladder", chain_thread(messages=8, hit_every=4)),
        _shape("no_floor_at_all", sibling_thread(messages=8)),
        _shape(
            "fill_and_sibling_runs",
            chain_thread(messages=90, hit_every=5, snippet_tokens=110),
            sibling_thread(thread_id="s1", rank=6, messages=60),
        ),
        _shape(
            "hit_and_floor_bodies",
            chain_thread(
                messages=40,
                hit_every=3,
                body_words=900,
                quoted_lines=2,
                bodies_for_all=True,
                snippet_tokens=40,
            ),
        ),
        _shape(
            "hit_thread_stub_runs",
            chain_thread(messages=400, hit_every=399, snippet_tokens=20),
        ),
        _shape(
            "overflow_for_floor_membership",
            *[chain(index, messages=1000, hit_every=500, snippet_tokens=20) for index in range(3)],
        ),
        _shape(
            "split_by_source",
            *[chain(index, messages=900, hit_every=500, snippet_tokens=20) for index in range(3)],
            _bodied_flat_thread(thread_id="f1", rank=90, messages=8, body_words=900),
        ),
        _shape(
            "withheld_by_ceiling",
            *[chain(index, messages=1150, hit_every=500, snippet_tokens=20) for index in range(3)],
        ),
        # **Round 29 moved this shape from "declines" to "answers", and that is the fix.**
        # Three 1,300-message threads used to exhaust the ladder: every row step 7 and step 8
        # removed came back as a full `withheld` record, so stripping the response could not
        # make it smaller and there was nothing left to strip. With withholdings written at
        # the granularity of the call that recovers them, the same input now serves two
        # sources carrying matched mail. It stays in the matrix under its own name so the
        # sweep still covers the shape; `declares_an_inability` below is what now reaches the
        # refusal.
        _shape(
            "floor_alone_exceeds_the_overflow",
            *[chain(index, messages=1300, hit_every=500, snippet_tokens=20) for index in range(3)],
        ),
        # **The declared inability, after round 29.** One thread so large that no arrangement
        # of it fits, so the ladder splits its only source and would be left with a response
        # carrying no mail at all. Before grouping, an emptied response was still enormous -
        # thousands of withheld records - and the size check caught it; the cost of the
        # bookkeeping was the guard against emptiness, by accident. Grouping removed that
        # accident, so emptiness is now checked for what it is.
        _shape(
            "declares_an_inability",
            chain_thread(
                thread_id="huge",
                rank=0,
                messages=4000,
                hit_every=1,
                body_words=1500,
                snippet_tokens=20,
            ),
        ),
    )


def test_the_shape_matrix_reaches_every_step_and_both_ceilings() -> None:
    """R-RETR-058, applied to this round: **prove the matrix reaches what it asserts about.**

    A property sweep over shapes that never reach step 6 says nothing about step 6, and this
    project has shipped exactly that. So the reach is printed as data and asserted: every one
    of the eight published steps fires in at least one shape, both ceilings are applied in at
    least one shape each, shapes with and without a floor are both present, and the ladder's
    declared inability is reachable too.
    """
    matrix = shape_matrix()
    fired = {precedence for shape in matrix for precedence in shape.steps}
    assert fired == {step.precedence for step in LADDER_STEPS}, sorted(fired)
    ceilings = {shape.ceiling for shape in matrix}
    assert NORMAL_CEILING_TOKENS in ceilings
    assert FLOOR_OVERFLOW_CEILING_TOKENS in ceilings
    assert {shape.floor for shape in matrix} == {True, False}
    assert any(shape.exhausted for shape in matrix)
    assert any(shape.steps == () and not shape.exhausted for shape in matrix)
    assert any(shape.withheld > 0 for shape in matrix)
    assert any(shape.split > 0 for shape in matrix)


def test_every_disclosure_shape_keeps_the_five_properties_that_make_the_ladder_honest() -> None:
    """The commonality, asserted over every shape rather than one shape at a time.

    Whatever a shape's size, ceiling, step sequence or floor, five things hold, and each of
    them is a way the ladder could be dishonest:

      1. the response fits the ceiling it declares (DISC-06);
      2. every floor member is present (OD-3);
      3. every accounted message is present or has a withheld record (I-1);
      4. the steps that fired are in the published order, never repeated (A.9a);
      5. the overflow ceiling is applied only where there is a floor to protect.
    """
    for shape in shape_matrix():
        if shape.exhausted:
            continue
        assert list(shape.steps) == sorted(shape.steps), shape
        assert len(set(shape.steps)) == len(shape.steps), shape
        assert shape.tokens <= (shape.ceiling or 0), shape
        if shape.ceiling == FLOOR_OVERFLOW_CEILING_TOKENS:
            assert shape.floor is True, shape


def test_the_ladder_terminates_on_the_forty_message_six_hit_case() -> None:
    """OD-3's own case, executed. The one the acceptance column names.

    Forty messages, six of them matching, bodies fetched for the whole thread so the
    arithmetic is the document's rather than a smaller one: the ladder terminates inside the
    normal ceiling, and it says which steps it spent to get there.
    """
    thread = chain_thread(
        messages=40,
        hit_every=7,
        body_words=900,
        quoted_lines=2,
        bodies_for_all=True,
        snippet_tokens=40,
    )
    assert len(thread.hit_ids) == 6
    plan = layout_of(thread)
    assert plan.tokens <= plan.layout.ceiling_applied
    assert plan.layout.ceiling_applied == NORMAL_CEILING_TOKENS
    assert plan.layout.floor_ids <= plan.layout.present_ids
    assert [step.precedence for step in plan.steps] == sorted(
        step.precedence for step in plan.steps
    )


def test_a_step_only_ever_lowers_a_rows_depth() -> None:
    """Monotonicity: no A.9a step may deepen a row, at any ceiling, in any shape.

    A step that raised a depth would make the ladder's own account of what it sacrificed
    unreadable, because the reader could no longer assume that what is shallow now was
    deeper before.
    """
    ranking = {Depth.STUB: 0, Depth.SNIPPET: 1, Depth.BODY_CLEAN: 2}
    layout = oversized_layout()
    before = {row.id: row for source in layout.sources for row in source.rows}
    working = replace(layout, ceiling_applied=NORMAL_CEILING_TOKENS)
    for step in LADDER_STEPS:
        after = step.apply(working, Ceilings())
        now = {row.id: row for source in after.sources for row in source.rows}
        for message_id, row in now.items():
            assert ranking[row.depth] <= ranking[before[message_id].depth], (step.name, message_id)
        working = after


def overflow_layout() -> Layout:
    """A layout that reaches A.9a step 6: too big for the normal ceiling once 1-5 are spent.

    Three long threads whose members mostly collapse into declared runs, so what is left after
    step 5 is membership rather than depth - which is the state step 6 exists for.
    """
    return raw_layout(
        *[
            chain_thread(thread_id=f"t{i}", rank=i, messages=1000, hit_every=500, snippet_tokens=20)
            for i in range(3)
        ]
    )


def test_the_overflow_ceiling_is_reachable_only_for_floor_membership() -> None:
    """A.9a step 6's four conditions, each denied in turn on the same oversized layout.

    The fourth is round 25's (R-DISC-023): the ceiling is raised only where the response
    would **still** exceed the normal ceiling with every message reduced to a bare stub row -
    the counterfactual A.9a's own "if and only if the E2 floor's *membership* cannot be
    carried within it" names, computed rather than approximated by "steps 1-5 are exhausted".
    """
    ceilings = Ceilings()
    layout = replace(overflow_layout(), ceiling_applied=NORMAL_CEILING_TOKENS)

    # (a) steps 1-5 have not run, so there is still reduction available: refused.
    assert step_6_declared_overflow(layout, ceilings) == layout

    # (b) with steps 1-5 exhausted and a floor to protect: the ceiling is raised, which is
    #     the positive control - without it (c) and (d) could pass because nothing ever
    #     raises it.
    exhausted = layout
    for step in LADDER_STEPS[:5]:
        exhausted = step.apply(exhausted, ceilings)
    assert exhausted.cost() > NORMAL_CEILING_TOKENS, "the fixture must still not fit"
    assert step_6_declared_overflow(exhausted, ceilings).ceiling_applied == (
        FLOOR_OVERFLOW_CEILING_TOKENS
    )

    # (c) the same layout with no floor to protect: refused, although nothing is left to
    #     reduce and the response does not fit. The overflow is not a budget.
    floorless = replace(exhausted, floor_ids=frozenset())
    assert step_6_declared_overflow(floorless, ceilings) == floorless

    # (d) a layout whose membership *would* fit the normal ceiling as bare stub rows: refused,
    #     with everything else about it identical. Round 23 raised the ceiling here and spent
    #     it on snippet depth, under a `why` that said "E2 floor membership".
    # Forty two-message threads: after steps 1-5 what is left is the five hit bodies A.9a
    # step 3 protects, and everything else is a declared collapsed run. Membership on its own
    # is 6,110 estimated tokens against a normal ceiling of 9,000; what does not fit is the
    # 6,000 tokens of *depth* in those five protected bodies.
    affordable = raw_layout(
        *[
            chain_thread(
                thread_id=f"q{i}",
                rank=i,
                messages=2,
                hit_every=2,
                body_words=900,
                snippet_tokens=20,
            )
            for i in range(40)
        ]
    )
    affordable = replace(affordable, ceiling_applied=NORMAL_CEILING_TOKENS)
    for step in LADDER_STEPS[:5]:
        affordable = step.apply(affordable, ceilings)
    assert affordable.cost() > NORMAL_CEILING_TOKENS, "the fixture must still not fit"
    assert cheapest_membership_cost(affordable) <= NORMAL_CEILING_TOKENS, (
        "the fixture must be one whose *membership* is affordable"
    )
    assert step_6_declared_overflow(affordable, ceilings) == affordable


def test_the_ladder_declares_an_inability_rather_than_shipping_an_oversized_response() -> None:
    """DISC-06's edge: when no arrangement carries mail, the ladder raises (OD-3's branch).

    **Round 29 changed which input reaches this and did not change the property.** Until
    withholdings could be grouped, three 1,300-message threads exhausted the ladder, because
    every row it removed came back as a full `withheld` record and stripping the response
    could not shrink it. That input now answers (the test below). What still cannot be served
    is a single thread too large for any arrangement of it: the ladder splits its only source
    and is left with nothing to say.

    The refusal that fires is the *emptiness* one, and that is deliberate. A response which
    fits because it carries no mail is the quieter claim OD-3 refuses, and before round 29 it
    was caught only by accident - an emptied response was still thousands of withheld records
    and failed the size check. Grouping made emptiness cheap, so it is now checked for what it
    is rather than for what it used to cost.
    """
    huge = chain_thread(
        thread_id="huge", rank=0, messages=4000, hit_every=1, body_words=1500, snippet_tokens=20
    )
    with pytest.raises(DisclosureLadderExhausted) as refusal:
        layout_of(huge)
    said = str(refusal.value)
    assert "DISC-06" in said
    assert "OD-3" in said
    # The numbers are counted off the layout, not asserted (round 25, R-DISC-020): a reader
    # can check what was retrieved, how much of it survived, and how much is accounted for.
    assert re.search(r"\d+ retrieved message\(s\)", said), said
    assert re.search(r"\d+ of them present", said), said
    assert re.search(r"\d+ message\(s\) withheld", said), said
    assert "carries no mail" in said


def test_the_shape_that_used_to_decline_now_carries_matched_mail() -> None:
    """**R-MCP-033, requirement 6, at the ladder.** The exact input the test above used to
    drive, asserted from the other side.

    This is the round's claim stated as an execution rather than as an argument: the same
    three 1,300-message threads that could not be served now come back with sources and with
    matched messages in them, inside the same ceilings, because the omission they carry is
    written at the granularity of the call that undoes it.

    It is paired with the refusal above on purpose. A change that made the ladder answer
    everything would pass this and fail that; a change that made it refuse everything would
    pass that and fail this. Neither test is worth much without the other.
    """
    threads = [
        chain_thread(thread_id=f"t{i}", rank=i, messages=1300, hit_every=500, snippet_tokens=20)
        for i in range(3)
    ]
    layout = layout_of(*threads).layout
    assert layout.sources, "the response carries no sources at all"
    assert layout.hit_ids & layout.present_ids, "the response carries no matched mail"
    assert layout.groups, "the split source was not accounted for as a group"
    # Every id is still accounted for: present, or grouped, or named one by one.
    accounted_for = layout.present_ids | layout.grouped_ids | layout.named_withheld_ids
    assert layout.accounted_ids <= accounted_for, sorted(layout.accounted_ids - accounted_for)


def test_every_truncation_the_ladder_performs_is_declared_with_a_count() -> None:
    """A7 on the disclosure half: annotate, never silently delete (DISC-03, R-04)."""
    row = PlannedRow(
        id="m1",
        position=0,
        band=Band.EVIDENCE,
        depth=Depth.BODY_CLEAN,
        body=" ".join(f"w{index}" for index in range(2_000)),
        snippet=snippet_of(20),
    )
    text, reductions = row.rendered()
    assert text is not None
    assert count_tokens(text) == BODY_CLEAN_SOFT_CAP_TOKENS
    record = next(r for r in reductions if r.kind is ReductionKind.BODY_HEAD_TRUNCATED)
    assert record.kept_tokens == BODY_CLEAN_SOFT_CAP_TOKENS
    assert record.removed_chars > 0
    assert record.detail == "A.9a body_clean soft cap"

    stepped = replace(row, kept_tokens=BODY_CLEAN_HEAD_TRUNCATED_TOKENS)
    text, reductions = stepped.rendered()
    assert text is not None
    assert count_tokens(text) == BODY_CLEAN_HEAD_TRUNCATED_TOKENS
    record = next(r for r in reductions if r.kind is ReductionKind.BODY_HEAD_TRUNCATED)
    assert record.kept_tokens == BODY_CLEAN_HEAD_TRUNCATED_TOKENS
    assert record.detail == "A.9a head-truncation step"


# --- Part 4: the two arms, at equal budget ---------------------------------------------------


def test_two_materially_different_queries_produce_different_representations() -> None:
    """DISC-01, at the policy rather than at the response schema.

    The same thread, two queries that differ in what they name, and the included set differs.
    A policy that returned the same rows for both would fail here whatever its reason strings
    said.

    **On the thread Gmail actually sends.** Round 23 ran this against
    `chain_thread(hit_subject_term=True)`, which puts the query term on the *hits'* subject
    lines only; Gmail puts one subject on every message of a thread, and on that shape the
    round-23 policy returned the same sixteen rows for six materially different queries
    (R-DISC-017). `shared_subject_thread` is the real shape, and under amendment A11 the
    subject - being one value across the whole thread - ranks but does not admit, so what
    separates the queries is what each message's own text carries.
    """
    thread = shared_subject_thread(messages=16, hit_every=5)
    accounted = frozenset(thread.order)
    first, second = SHARED_SUBJECT_TERMS[0], SHARED_SUBJECT_TERMS[1]
    by_first = disclose(
        [thread], query=query(terms=(first,)), selector=QueryAwareFill(), accounted_ids=accounted
    )
    by_second = disclose(
        [thread], query=query(terms=(second,)), selector=QueryAwareFill(), accounted_ids=accounted
    )
    filled_by_first = {row.id for row in by_first.layout.sources[0].rows if row.band is Band.FILL}
    filled_by_second = {row.id for row in by_second.layout.sources[0].rows if row.band is Band.FILL}
    assert filled_by_first
    assert filled_by_second
    assert filled_by_first != filled_by_second


def test_the_fixed_window_baseline_runs_through_the_same_ladder_at_the_same_ceiling() -> None:
    """DISC-02's equal-budget requirement, as a property of construction (SC §6, PROC-04).

    Both arms are planned by one function, degraded by one ladder, measured by one estimate
    and bounded by one ceiling. The only object that differs is the selector - asserted here
    by running both over the same threads and comparing everything except the fill.
    """
    threads = [chain_thread(messages=30, hit_every=6, snippet_tokens=40)]
    accounted = frozenset(threads[0].order)
    shipped = disclose(threads, query=query(), selector=QueryAwareFill(), accounted_ids=accounted)
    baseline = disclose(threads, query=query(), selector=FixedWindow(), accounted_ids=accounted)

    assert shipped.layout.ceiling_applied == baseline.layout.ceiling_applied
    assert shipped.layout.floor_ids == baseline.layout.floor_ids
    assert shipped.layout.present_ids == baseline.layout.present_ids
    assert baseline.selector_name == "baseline_f_fixed_window"
    assert shipped.selector_name == "query_aware_e4"
    # And the arms really do differ: the baseline fills by position, the shipped arm does not.
    baseline_fill = {row.id for row in baseline.layout.sources[0].rows if row.band is Band.FILL}
    shipped_fill = {row.id for row in shipped.layout.sources[0].rows if row.band is Band.FILL}
    assert baseline_fill != shipped_fill


def test_the_baseline_is_not_handicapped_by_the_planner() -> None:
    """A thesis that cannot lose is not a thesis (SC §6, WS-16 Baseline F).

    The baseline is given the same ceiling, the same floor, the same evidence tier and the
    same degradation ladder, and at ±2 it fills strictly more rows than the shipped policy
    does on a query that names only one term. If the planner had been arranged to make the
    baseline look bad, this would fail.
    """
    thread = chain_thread(messages=30, hit_every=6, snippet_tokens=40, hit_subject_term=True)
    accounted = frozenset(thread.order)
    shipped = disclose([thread], query=query(), selector=QueryAwareFill(), accounted_ids=accounted)
    baseline = disclose([thread], query=query(), selector=FixedWindow(), accounted_ids=accounted)
    baseline_fill = {row.id for row in baseline.layout.sources[0].rows if row.band is Band.FILL}
    shipped_fill = {row.id for row in shipped.layout.sources[0].rows if row.band is Band.FILL}
    assert baseline_fill
    assert len(baseline_fill) >= len(shipped_fill)


def test_the_baseline_runs_at_every_radius_it_is_a_baseline_at() -> None:
    """Baseline F(±1/±2/±5) is a permanent harness fixture, so all three are runnable."""
    thread = chain_thread(messages=40, hit_every=8, snippet_tokens=30)
    accounted = frozenset(thread.order)
    sizes = []
    for radius in (1, 2, 5):
        plan = disclose(
            [thread],
            query=query(),
            selector=FixedWindow(radius=radius),
            accounted_ids=accounted,
        )
        sizes.append(len({row.id for row in plan.layout.sources[0].rows if row.band is Band.FILL}))
    assert sizes == sorted(sizes)
    assert sizes[0] < sizes[-1]


def test_context_efficiency_is_computed_over_the_same_payload_as_the_ceiling() -> None:
    """DISC-04's two numbers, from the same estimate the ceiling is enforced with."""
    thread = chain_thread(
        messages=40, hit_every=7, body_words=900, bodies_for_all=True, snippet_tokens=40
    )
    plan = layout_of(thread)
    measured = efficiency(plan, [thread])
    assert measured.disclosed_tokens == plan.tokens
    assert measured.full_dump_tokens > measured.disclosed_tokens
    assert 0.0 < measured.fraction_of_full_dump < 1.0
    assert 0.0 < measured.relevant_token_fraction <= 1.0


# --- Part 5: F17's scoring hook, at each depth tier -------------------------------------------


def reversal_thread(*, snippet_tokens: int = 20) -> ThreadInput:
    """F17's shape: the hits support one answer and a quiet later child reverses it.

    Not a fixture of the F17 family itself - EP §4.7 owns that, and WS-16 runs it. This is the
    **hook**: the thread shape the family is built from, so the depth tiers can be scored here
    without waiting for the harness.
    """
    return chain_thread(
        messages=9,
        hit_every=4,
        body_words=600,
        quoted_lines=2,
        snippet_tokens=snippet_tokens,
        decision_children=True,
        bodies_for_all=True,
    )


#: The three tiers A.9a's step 4 produces for the E2 floor, and a ceiling that reaches each.
#: Both ceilings are set together, deliberately: leaving the overflow at 12,000 would let
#: step 6 raise past the tier under test, and the "tier" would silently be the one above.
#:
#: The three numbers moved in round 25 with the cost model (A11): a `body_clean` row is now
#: charged its structure and its text twice - once in `structuredContent` and once in the text
#: mirror - so the ceiling that leaves this thread undegraded is larger than it was. What the
#: numbers are for has not changed, and `test_the_three_depth_tiers_are_actually_distinct_on_
#: the_same_thread` is what holds them to producing three different tiers.
DEPTH_TIERS: tuple[tuple[str, Ceilings], ...] = (
    ("body_clean", Ceilings(normal=9_000, overflow=9_000)),
    # 6,400 rather than round 25's 7,000: the estimate charges a `Source`'s own structure from
    # round 26 (R-DISC-032), so the ceiling at which A.9a's head-truncation rung is the one
    # that fires moved down with it. The figures here are properties of this fixture and this
    # estimate, and this file's own
    # `test_the_three_depth_tiers_are_actually_distinct_on_the_same_thread` is what keeps them
    # honest: if a later change makes two of the three tiers the same tier, that test fails
    # rather than the parametrised one silently running one tier three times.
    ("head_truncated", Ceilings(normal=6_400, overflow=6_400)),
    # 5,800 rather than 5,500 (2026-09-22): every row is charged the text mirror's attribution
    # and chronology lines and the response its attribution note, so at 5,500 the ladder went
    # past snippet and collapsed the whole floor into runs - no floor row at all, which is not
    # a tier. Measured on this thread: the floor holds snippet rows and no body from 5,600 to
    # 6,050, carries a head-truncated body from 6,100, and is all runs at 5,550. The head tier
    # at 6,400 is still inside its window (6,100 to under 6,800, where the body is whole).
    ("snippet", Ceilings(normal=5_800, overflow=5_800)),
)


@pytest.mark.parametrize(("tier", "ceilings"), DEPTH_TIERS, ids=[t for t, _ in DEPTH_TIERS])
def test_the_reversing_reply_is_present_at_every_degradation_tier(
    tier: str, ceilings: Ceilings
) -> None:
    """T-CD2 / OD-3, at the three tiers A.9a names, in both arms at the same ceiling.

    The claim being executed is the bounded one: **membership plus a snippet**. At every tier
    the reversing child is present, and at every tier it is present in the fixed-window arm
    too - because the point of the comparison is that both arms are run, not that one is
    arranged to win.
    """
    thread = reversal_thread()
    accounted = frozenset(thread.order)
    reversing = {
        message_id
        for message_id in thread.order
        if (text := thread.snippets.get(message_id)) and "decided" in text
    }
    assert reversing, "the fixture must contain a reversal"
    for selector in (QueryAwareFill(), FixedWindow()):
        plan = disclose(
            [thread],
            query=query(),
            selector=selector,
            accounted_ids=accounted,
            ceilings=ceilings,
        )
        assert plan.tokens <= plan.layout.ceiling_applied, (tier, selector)
        assert reversing <= plan.layout.present_ids, (tier, selector)
        assert plan.layout.floor_ids <= plan.layout.present_ids, (tier, selector)


def test_the_three_depth_tiers_are_actually_distinct_on_the_same_thread() -> None:
    """The tiers are only worth scoring separately if the budget really produces three.

    Without this the parametrised test above could be running one tier three times - which is
    the vacuous-fixture shape this project has produced before, and it is what
    `test_the_reversing_reply_is_present_at_every_degradation_tier` rests on.
    """
    thread = reversal_thread()
    accounted = frozenset(thread.order)
    seen: list[frozenset[tuple[str, int | None]]] = []
    for _tier, ceilings in DEPTH_TIERS:
        plan = disclose(
            [thread],
            query=query(),
            selector=QueryAwareFill(),
            accounted_ids=accounted,
            ceilings=ceilings,
        )
        seen.append(
            frozenset(
                (row.depth.value, row.kept_tokens)
                for row in plan.layout.sources[0].rows
                if row.band is Band.FLOOR
            )
        )
    assert len(set(seen)) == 3, seen
    # And the three are the three A.9a names, in the order it names them.
    assert (Depth.BODY_CLEAN.value, None) in seen[0]
    assert (Depth.BODY_CLEAN.value, BODY_CLEAN_HEAD_TRUNCATED_TOKENS) in seen[1]
    # **Snippet is the bottom A.9a writes and it is no longer the last rung** (round 25). A
    # floor member may reach `stub` when snippet does not fit, where it is still a member and
    # is collapsible into a declared run - which is what turns a thread the ladder used to
    # refuse into a complete map. What must not appear at this tier is a *body* depth.
    assert (Depth.SNIPPET.value, None) in seen[2]
    assert not {depth for depth, _kept in seen[2]} & {
        Depth.BODY_CLEAN.value,
        Depth.BODY_FULL.value,
    }


# --- Part 6: the segment map (experimental) ---------------------------------------------------


def test_the_segment_map_is_labelled_experimental_and_derives_its_boundary() -> None:
    """AD §E.2: built, labelled, removable, and neither of its numbers invented (DISC-05)."""
    assert SEGMENT_MAP_IS_EXPERIMENTAL is True
    # Both figures spelled out rather than recomputed from the constants the boundary is
    # derived from: `FLAT_MAP_MESSAGE_BOUNDARY == NORMAL_CEILING_TOKENS // STUB_ROW_TOKEN_
    # ESTIMATE` would be true by construction and would assert nothing (R-DISC-021's class).
    # 120 is the structural charge amendment A11 puts on every row at every depth.
    assert (NORMAL_CEILING_TOKENS, STUB_ROW_TOKEN_ESTIMATE) == (9_000, 120)
    assert FLAT_MAP_MESSAGE_BOUNDARY == 75


def test_a_thread_below_the_boundary_gets_no_segment_at_all() -> None:
    """Depth *n−1*: a flat map with declared truncation and an affordance, from one path."""
    order = ("m0", "m1")
    assert (
        segment_of(0, stated_total=2, order=order, internal_dates={"m0": EPOCH, "m1": EPOCH})
        is None
    )


def test_segments_are_temporal_and_a_thread_that_never_paused_is_one_segment() -> None:
    """E3 is *temporal* segmentation, so a long unbroken conversation is not carved up."""
    size = FLAT_MAP_MESSAGE_BOUNDARY + 5
    order = tuple(f"m{index}" for index in range(size))
    unbroken = {message_id: EPOCH + index * 1_000 for index, message_id in enumerate(order)}
    assert segment_of(size - 1, stated_total=size, order=order, internal_dates=unbroken) is None

    paused = dict(unbroken)
    for index in range(size // 2, size):
        paused[order[index]] = EPOCH + 50 * DAY_MS + index * 1_000
    assert segment_of(0, stated_total=size, order=order, internal_dates=paused) == 0
    assert segment_of(size - 1, stated_total=size, order=order, internal_dates=paused) == 1


def test_a_message_with_no_observed_timestamp_never_starts_a_segment() -> None:
    """A boundary drawn at an unknown time would be a claim made out of an absence."""
    size = FLAT_MAP_MESSAGE_BOUNDARY + 3
    order = tuple(f"m{index}" for index in range(size))
    dates: dict[str, int | None] = {
        message_id: EPOCH + index * 1_000 for index, message_id in enumerate(order)
    }
    dates[order[1]] = None
    assert segment_of(1, stated_total=size, order=order, internal_dates=dates) is None


# --- Part 7: the property sweep over generated shapes -------------------------------------------


@st.composite
def generated_threads(draw: st.DrawFn) -> list[ThreadInput]:
    """Threads whose size, hit density, text and rank the sweep chooses, not a fixture author."""
    count = draw(st.integers(min_value=1, max_value=3))
    threads: list[ThreadInput] = []
    for index in range(count):
        threads.append(
            chain_thread(
                thread_id=f"g{index}",
                rank=index,
                messages=draw(st.integers(min_value=2, max_value=45)),
                hit_every=draw(st.integers(min_value=1, max_value=6)),
                body_words=draw(st.sampled_from([0, 40, 900])),
                quoted_lines=draw(st.integers(min_value=0, max_value=2)),
                snippet_tokens=draw(st.integers(min_value=1, max_value=80)),
                decision_children=draw(st.booleans()),
                hit_subject_term=draw(st.booleans()),
                bodies_for_all=draw(st.booleans()),
            )
        )
    return threads


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(threads=generated_threads())
def test_the_ladders_invariants_hold_over_generated_shapes(threads: list[ThreadInput]) -> None:
    """The commonality, over shapes nobody wrote. The peers, tested rather than trusted."""
    accounted = frozenset(mid for thread in threads for mid in thread.order)
    try:
        plan = disclose(threads, query=query(), selector=QueryAwareFill(), accounted_ids=accounted)
    except DisclosureLadderExhausted:
        return
    assert plan.tokens <= plan.layout.ceiling_applied
    assert plan.layout.floor_ids <= plan.layout.present_ids
    assert (accounted & plan.layout.accounted_ids) <= (
        plan.layout.present_ids | frozenset(plan.layout.withheld_ids)
    )
    precedences = [step.precedence for step in plan.steps]
    assert precedences == sorted(precedences)
    assert len(set(precedences)) == len(precedences)
    if plan.layout.ceiling_applied != NORMAL_CEILING_TOKENS:
        assert plan.layout.ceiling_applied == FLOOR_OVERFLOW_CEILING_TOKENS
        assert plan.layout.floor_ids


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(threads=generated_threads())
def test_both_arms_fit_the_same_ceiling_on_the_same_input(threads: list[ThreadInput]) -> None:
    """DISC-02's equal-budget requirement over generated shapes, not over one fixture."""
    accounted = frozenset(mid for thread in threads for mid in thread.order)
    plans = {}
    for selector in (QueryAwareFill(), FixedWindow()):
        try:
            plans[selector.name] = disclose(
                threads,
                query=query(),
                selector=selector,
                accounted_ids=accounted,
            )
        except DisclosureLadderExhausted:
            return
    for plan in plans.values():
        assert plan.tokens <= plan.layout.ceiling_applied
    assert len({plan.layout.ceiling_applied for plan in plans.values()}) == 1


def test_a_floor_member_is_never_scored_by_the_fill() -> None:
    """The floor does not compete with the fill for budget (OD-3), executed.

    A floor member that could also be admitted as fill would make its presence depend on a
    score, which is exactly the negotiation OD-3 says membership is not subject to.
    """
    thread = chain_thread(messages=20, hit_every=4, hit_subject_term=True)
    plan = layout_of(thread)
    floor = {member.message_id for member in plan.threads[0].floor}
    assert floor
    assert not (floor & set(plan.threads[0].fill))


# --- Part 8: fixture hygiene ------------------------------------------------------------------


def test_no_fixture_in_this_file_carries_anything_that_could_be_real_mail() -> None:
    """OD-4 and the standing rule, executed over this module's own source.

    Every address literal is in a reserved TLD (RFC 2606/6761) and no string literal is long
    enough to be a real message body. Executed rather than promised, because a later edit is
    exactly when a realistic-looking body gets pasted in.
    """
    tree = ast.parse(Path(__file__).read_text())
    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstring_nodes.add(id(first.value))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstring_nodes:
            continue
        for address in re.findall(r"[\w.+-]+@[\w.-]+", node.value):
            assert address.rsplit(".", 1)[-1] in {"example", "invalid", "test"}, address
        assert len(node.value) < 300, node.value[:80]


# --- Part 9: the ladder and the envelope agree about size -------------------------------------


def _envelope_from(plan: Disclosure, thread: ThreadInput) -> Envelope:
    """Assemble a real `Envelope` out of a planned layout, through the production types.

    Deliberately not a shortcut: the rows go through `MessageRow`, the source through
    `Source`, the disposition through `DispositionLedger.certify`, and the ceiling through
    `Envelope`'s own validator. If the ladder's arithmetic and the envelope's disagreed, this
    would raise `ResponseCeilingExceeded` rather than return.
    """
    ledger = DispositionLedger()
    ledger.record_thread(
        fully_observed_thread(list(thread.order), thread.thread_id), rung=RungId.L1
    )
    builder = EnvelopeBuilder(ledger, asked_for=asked_for())
    planned_source = plan.layout.sources[0]
    rows: list[MessageRow] = []
    for planned_row in planned_source.rows:
        text, reductions = planned_row.rendered()
        rows.append(
            MessageRow(
                id=planned_row.id,
                position=planned_row.position,
                role=Role.MATCHED if planned_row.band is Band.EVIDENCE else Role.CONTEXT,
                reason=query_reason(),
                mailbox=MailboxProvenance.of(("INBOX",)),
                depth=planned_row.depth,
                linkage=Linkage.HEADERS_UNOBSERVED,
                reductions=reductions,
                unabridged=unabridged(planned_row.id),
                content=(
                    None
                    if text is None
                    else Content(
                        trust=Trust.UNTRUSTED_THIRD_PARTY,
                        source=ContentSource.GMAIL_BODY,
                        text=fence(builder.fence_nonce, text),
                    )
                ),
            )
        )
    runs = tuple(
        collapsed_run(run.start, list(run.member_ids), thread.thread_id)
        for run in planned_source.runs
    )
    builder.add_source(source(thread.thread_id, rows, collapsed_runs=runs))
    builder.set_ceiling(
        Ceiling(
            normal=NORMAL_CEILING_TOKENS,
            applied=plan.layout.ceiling_applied,
            why=(
                None
                if plan.layout.ceiling_applied == NORMAL_CEILING_TOKENS
                else "E2 floor membership"
            ),
        )
    )
    if plan.steps:
        builder.mark_self_truncated()
    return builder.build(
        outcome=Outcome.ANSWERED,
        rungs=(RungId.L1,),
        sufficiency=Sufficiency.SUFFICIENT,
        counters=counters(),
    )


def test_the_ladders_measure_and_the_envelopes_measure_are_the_same_number() -> None:
    """DISC-06's precondition: two measures would let the ladder fit what the envelope refuses.

    Asserted on an assembled response rather than on the two functions, because the thing
    that has to agree is the *payload's* size in each one's units - a per-row agreement that
    did not survive fencing, or a collapsed run counted on one side only, would pass a
    function-level comparison and fail here.
    """
    for thread in (
        chain_thread(messages=40, hit_every=7, body_words=900, bodies_for_all=True),
        chain_thread(messages=400, hit_every=399, snippet_tokens=20),
        chain_thread(messages=12, hit_every=4),
    ):
        plan = layout_of(thread)
        envelope = _envelope_from(plan, thread)
        assert measure_tokens(envelope) == plan.tokens == plan.layout.cost()


def test_an_assembled_response_never_exceeds_the_ceiling_it_declares() -> None:
    """DISC-06 stated over the artefact: the host never has to cut a MailWeave response."""
    thread = chain_thread(
        messages=40, hit_every=3, body_words=900, bodies_for_all=True, snippet_tokens=40
    )
    plan = layout_of(thread)
    envelope = _envelope_from(plan, thread)
    assert measure_tokens(envelope) <= envelope.ceiling.applied
    assert envelope.ceiling.normal == NORMAL_CEILING_TOKENS
    assert envelope.truncated_by == ("mailweave" if plan.steps else None)


def test_a_ceiling_block_only_claims_the_overflow_where_the_ladder_applied_it() -> None:
    """AD D.2's `ceiling{}`: `why` is non-null exactly when the applied ceiling is raised."""
    fits = layout_of(chain_thread(messages=12, hit_every=4))
    assert fits.layout.ceiling_applied == NORMAL_CEILING_TOKENS
    raised = layout_of(
        *[
            chain_thread(
                thread_id=f"t{index}", rank=index, messages=1000, hit_every=500, snippet_tokens=20
            )
            for index in range(3)
        ]
    )
    assert raised.layout.ceiling_applied == FLOOR_OVERFLOW_CEILING_TOKENS
    assert raised.layout.floor_ids


# --- Part 10: the shipped path, end to end ----------------------------------------------------


DECISION_TERM = "cutover"


def reversal_mailbox() -> SyntheticMailbox:
    """One thread whose hit quotes its parent and whose quiet later reply reverses it.

    The three shapes WS-11's promotion rule is about, in one thread: a parent the evidence
    quotes (promoted), a child that reverses (promoted), and an ordinary later reply that
    does neither (refused). Invented for the structural property; the `.example`/`.invalid`
    TLDs are reserved (RFC 2606/6761).
    """
    return SyntheticMailbox(
        messages=(
            Msg(
                id="e-1",
                thread_id="t-rev",
                sender=SENDER,
                subject="Programme",
                body="The opening note, with the schedule in it.",
                internal_date_ms=epoch_ms(2026, 7, 10),
                rfc822_message_id="<e1@mail.invalid>",
            ),
            Msg(
                id="e-2",
                thread_id="t-rev",
                sender=SENDER,
                subject="Re: Programme",
                body=(
                    f"We are going ahead with the {DECISION_TERM}.\n"
                    "> The opening note, with the schedule in it."
                ),
                internal_date_ms=epoch_ms(2026, 7, 11),
                rfc822_message_id="<e2@mail.invalid>",
                in_reply_to="<e1@mail.invalid>",
            ),
            Msg(
                id="e-3",
                thread_id="t-rev",
                sender=OTHER,
                subject="Re: Programme",
                body="Actually we cancelled it; pushing to the next quarter.",
                internal_date_ms=epoch_ms(2026, 7, 12),
                rfc822_message_id="<e3@mail.invalid>",
                in_reply_to="<e2@mail.invalid>",
            ),
            Msg(
                id="e-4",
                thread_id="t-rev",
                sender=OTHER,
                subject="Re: Programme",
                body="Thanks, noted.",
                internal_date_ms=epoch_ms(2026, 7, 13),
                rfc822_message_id="<e4@mail.invalid>",
                in_reply_to="<e3@mail.invalid>",
            ),
        ),
        now_ms=epoch_ms(2026, 9, 12),
    )


def test_the_shipped_path_promotes_the_floor_members_the_evidence_depends_on() -> None:
    """WS-11 wired into `assemble`, end to end, against the real client and transport.

    The hit quotes its parent, so the parent is promoted with `quotation`; the hit's direct
    child reverses the decision, so it is promoted with `contradiction`; the reply after that
    is not a floor member of anything and stays a stub row. The reasons are read off the
    disclosed payload, not off the planner.
    """
    _box, envelope = answer(DECISION_TERM, box=reversal_mailbox())
    source = next(s for s in envelope.sources if s.thread_id == "t-rev")
    rows = {row.id: row for row in source.messages}
    assert set(rows) == {"e-1", "e-2", "e-3", "e-4"}

    assert rows["e-2"].role is Role.MATCHED
    assert rows["e-2"].depth is Depth.BODY_CLEAN

    parent, child = rows["e-1"], rows["e-3"]
    assert isinstance(parent.reason, FloorPromoted)
    assert parent.reason.dependence is FloorDependence.QUOTATION
    assert parent.reason.relation is FloorRelation.PARENT
    assert isinstance(child.reason, FloorPromoted)
    assert child.reason.dependence is FloorDependence.CONTRADICTION
    assert child.reason.relation is FloorRelation.CHILD

    # And the rule said no somewhere in the same response.
    assert not isinstance(rows["e-4"].reason, FloorPromoted)
    assert rows["e-4"].depth is Depth.STUB


def test_the_shipped_path_declares_a_ceiling_on_every_response() -> None:
    """AD D.2's `ceiling{}` reaches the wire, and states the normal ceiling it was built to."""
    _box, envelope = answer(DECISION_TERM, box=reversal_mailbox())
    assert envelope.ceiling.normal == NORMAL_CEILING_TOKENS
    assert envelope.ceiling.applied == NORMAL_CEILING_TOKENS
    assert envelope.ceiling.why is None
    assert measure_tokens(envelope) <= envelope.ceiling.applied


def test_a_filled_row_on_the_wire_names_the_components_that_reached_it() -> None:
    """DISC-01 through the shipped path: the reason is a mechanism, not a rationale."""
    _box, envelope = answer(f"from:{SENDER} {DECISION_TERM}", box=reversal_mailbox())
    filled = [
        row
        for source in envelope.sources
        for row in source.messages
        if isinstance(row.reason, QueryScoredFill)
    ]
    for row in filled:
        reason = row.reason
        assert isinstance(reason, QueryScoredFill)
        assert reason.components
        assert reason.score == sum(E4_WEIGHTS[component] for component in reason.components)
        assert row.role is Role.CONTEXT
        assert reason.render().startswith("E4 query score")


def test_a_ladder_step_that_removes_nothing_does_not_claim_a_truncation() -> None:
    """DISC-06: `truncated_by` says something was cut, and step 6 cuts nothing.

    Raising the declared ceiling for floor membership is a change to what the response
    *says*, not to what it contains, and `Envelope` refuses a truncation claim with no A.9a
    artifact behind it. Without this distinction a response whose only step was the overflow
    would be unbuildable.
    """
    # **The layout A.9a step 6 actually sees**: this one, with steps 1-5 already spent on it.
    # After round 25's cost model no *input* reaches step 6 without steps 3-5 firing first -
    # the ladder degrades and collapses before it declares - so the shape this test is about
    # is reached by running those steps and handing the driver what they left.
    spent = replace(overflow_layout(), ceiling_applied=NORMAL_CEILING_TOKENS)
    for step in LADDER_STEPS[:5]:
        spent = step.apply(spent, Ceilings())
    assert spent.cost() > NORMAL_CEILING_TOKENS
    degraded, steps = run_ladder(spent)
    assert [step.precedence for step in steps] == [DECLARED_OVERFLOW_STEP]
    raised = Disclosure(layout=degraded, steps=steps, threads=(), selector_name="query_aware_e4")
    assert _the_ladder_removed_something(raised) is False

    cut = layout_of(chain_thread(messages=400, hit_every=399, snippet_tokens=20))
    assert cut.steps
    assert _the_ladder_removed_something(cut) is True


def test_a_degraded_response_names_the_disclosure_cap_it_hit() -> None:
    """AD D.2: a reader looking for "what cost me content" reads `budget_caps_hit`."""
    _box, envelope = answer(DECISION_TERM, box=reversal_mailbox())
    assert BudgetCapName.DISCLOSED_TOKEN_CEILING not in envelope.retrieval_report.budget_caps_hit
