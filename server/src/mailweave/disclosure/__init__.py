"""WS-11: representation and query-aware disclosure (AD A.9, A.9a; contract C-06; OD-3).

Five modules, and the split is by what each one is allowed to decide:

  * `weights` - the **published** E4 scoring table and the five mechanical components of
    A.9(3). Nothing here reads a response; it reads a candidate and a query;
  * `floor` - the E2 reply-chain floor and, in one function, **the promotion rule**:
    membership is absolute, depth is earned, and the rule says no more often than yes;
  * `layout` - the immutable shape the ladder shrinks, and the single cost estimate, which
    is the envelope's own;
  * `ladder` - AD A.9a's eight-step precedence as data, with the floor gate applied by the
    driver to every step rather than by each step to itself;
  * `plan` - A.9's four tiers assembled into a layout, for either arm: the shipped
    query-aware selector and Baseline F's fixed ±k window, through one code path so the
    DISC-02 comparison is at equal budget by construction;
  * `segments` - AD §E.2's experimental second navigational level, labelled and removable.

**What this package never does.** It does not fetch, embed, or call a model; it scores what
the response already holds. Where it wants text the run did not fetch, it says so and the
row carries the affordance that gets it (I-4). That is T-CD3's "reuse only, never trigger"
applied to a build with no semantic rung yet: the rule is structural, not a habit.
"""

from mailweave.disclosure.floor import (
    FLOOR_BASE_DEPTH,
    FLOOR_PROMOTED_DEPTH,
    INCORPORATED_SPANS,
    EvidenceFacts,
    FloorMember,
    MemberFacts,
    carries_a_decision_cue,
    dependence_of,
    floor_of,
    incorporates_text_it_did_not_write,
)
from mailweave.disclosure.ladder import (
    DECLARED_OVERFLOW_STEP,
    DISCLOSURE_TOP_K_HITS,
    LADDER_STEPS,
    Ceilings,
    DisclosureLadderExhausted,
    FloorMembershipLost,
    LadderStep,
    Step,
    assert_floor_intact,
    assert_nothing_vanished,
    run_ladder,
)
from mailweave.disclosure.layout import (
    Band,
    Layout,
    PlannedRow,
    PlannedRun,
    PlannedSource,
    layout_tokens,
)
from mailweave.disclosure.plan import (
    Disclosure,
    Efficiency,
    FixedWindow,
    PlannedThread,
    QueryAwareFill,
    Selector,
    ThreadInput,
    depth_for,
    disclose,
    efficiency,
    floor_members,
    floor_obligations,
    full_dump_tokens,
    plan_thread,
)
from mailweave.disclosure.segments import (
    FLAT_MAP_MESSAGE_BOUNDARY,
    SEGMENT_MAP_IS_EXPERIMENTAL,
    segment_boundaries,
    segment_of,
)
from mailweave.disclosure.weights import (
    ADMITTING_COMPONENTS,
    E4_ADJACENCY_POSITIONS,
    E4_MINIMUM_FILL_SCORE,
    E4_TEMPORAL_PROXIMITY_SECONDS,
    E4_WEIGHTS,
    QUERY_DERIVED_COMPONENTS,
    QUERY_INDEPENDENT_COMPONENTS,
    FillCandidate,
    FillScore,
    QueryFacts,
    anchoring_components,
    components_of,
    rank,
    score,
    score_of,
)

__all__ = [
    "ADMITTING_COMPONENTS",
    "DECLARED_OVERFLOW_STEP",
    "DISCLOSURE_TOP_K_HITS",
    "E4_ADJACENCY_POSITIONS",
    "E4_MINIMUM_FILL_SCORE",
    "E4_TEMPORAL_PROXIMITY_SECONDS",
    "E4_WEIGHTS",
    "FLAT_MAP_MESSAGE_BOUNDARY",
    "FLOOR_BASE_DEPTH",
    "FLOOR_PROMOTED_DEPTH",
    "INCORPORATED_SPANS",
    "LADDER_STEPS",
    "QUERY_DERIVED_COMPONENTS",
    "QUERY_INDEPENDENT_COMPONENTS",
    "SEGMENT_MAP_IS_EXPERIMENTAL",
    "Band",
    "Ceilings",
    "Disclosure",
    "DisclosureLadderExhausted",
    "Efficiency",
    "EvidenceFacts",
    "FillCandidate",
    "FillScore",
    "FixedWindow",
    "FloorMember",
    "FloorMembershipLost",
    "LadderStep",
    "Layout",
    "MemberFacts",
    "PlannedRow",
    "PlannedRun",
    "PlannedSource",
    "PlannedThread",
    "QueryAwareFill",
    "QueryFacts",
    "Selector",
    "Step",
    "ThreadInput",
    "anchoring_components",
    "assert_floor_intact",
    "assert_nothing_vanished",
    "carries_a_decision_cue",
    "components_of",
    "dependence_of",
    "depth_for",
    "disclose",
    "efficiency",
    "floor_members",
    "floor_obligations",
    "floor_of",
    "full_dump_tokens",
    "incorporates_text_it_did_not_write",
    "layout_tokens",
    "plan_thread",
    "rank",
    "run_ladder",
    "score",
    "score_of",
    "segment_boundaries",
    "segment_of",
]
