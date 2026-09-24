"""Turn one lexical ladder run into a response envelope (AD A.2 steps 4-6).

This began as the narrowest assembly that makes the exit condition of WS-04 a real statement
- "MailWeave answers a query against a mailbox" - round 20 added WS-05's thread map to it,
and round 23 wired **WS-11's disclosure layer** into it. What it does:

  * maps every hit-bearing thread with one `threads.get`, up to `MAX_HIT_THREADS`, and
    turns the threads beyond that cap into `withheld` records with a `mailweave_thread_map`
    affordance - which is A.7a's worked example, executed;
  * carries every message of a mapped thread as at least a stub row, so `included ==
    stated_total` and the map-carrier guarantee is a number rather than a promise - each at
    **the position the observation sealed**, never at one computed here, because a position
    is a claim about chronological order (amendment A3) and this module has no evidence for
    one the seal declined to state;
  * carries the hits whose bodies were fetched at `body_clean`, and the hits beyond
    `max_body_fetches` at the depth the text this response holds supports - a snippet where
    the observation carried one, a stub where it did not. **Disclosed at reduced depth,
    never withheld**, which is the distinction A.7a warns is the one that makes withheld
    lists meaningless;
  * **decides every row's depth through `mailweave.disclosure`** (WS-11): A.9's four tiers -
    hits at body depth, the E2 reply-chain floor present and promoted where the evidence
    depends on it (OD-3), the E4 query-scored fill with published weights, everything else a
    stub row - and then A.9a's eight-step degradation precedence over the whole response,
    with `ceiling{}`, `collapsed_runs[]`, `not_included_sources[]` and the
    `disclosed_token_ceiling` withheld records it produces. Nothing about depth is decided
    in this module; it projects each mapped thread down to a `ThreadInput`, hands the whole
    set to `disclose`, and materialises what comes back;
  * **refuses to map a thread whose `threads.get` cannot describe it** - one that omits a
    hit its own `messages.list` returned (the issue-#296 signature arriving from Gmail), or
    that states no chronological order for its messages. Neither becomes a `Source`; both
    become `partial_source_failure` withheld records with a retrieval affordance per id,
    which is A.7a's own disposition and needs no schema change.
    `_why_this_thread_cannot_be_mapped` carries the reasoning. Round 15 raised instead, and
    the raise denied the **whole response**: five healthy threads lost because a sixth
    disagreed with itself. What remains genuinely inexpressible is one number and is named
    at `_total_this_thread_can_state`;
  * **builds each mapped thread's structural map** (WS-05): the reply forest from RFC
    headers alone, the address-keyed participant index, and the declared gaps of both. Every
    row carries its `linkage` and its reply parent or the gap that stands in its place, and a
    row the tree explains - a parent or a direct child of a hit - carries the mechanical
    reason naming that relation (C-02a, C-02b, C-02d);
  * **runs L4** between the two passes: a reply naming a `Message-ID` its own thread does
    not hold is an exact `rfc822msgid:` lookup, and each thread that recovers becomes a
    separate `source` capped at `max_source_threads` (C-02e). Similarity-based sibling
    discovery is not built and the response says so;
  * lets `DispositionLedger.certify` compute `withheld := H - disclosed`. Nothing here
    assembles that set, and nothing here can: it is a set difference over the ids the
    ladder's transport recorded.

**What it deliberately does not do, so nothing here overclaims.**

  * It never emits `outcome: not_found`. OD-2 permits that only when no applicable rung is
    untried, and L5/L6/LR are still not built - so an empty result is `inconclusive`, with
    the `empty_diagnosis` saying which single-constraint drops were probed. That is the
    honest outcome and it is also why this round cannot demonstrate the `not_found` branch
    of the OD-2 rule; WS-10 owns that.
  * It computes no score. Gmail-`q`-selected rows carry no numeric score (RANK-03), and
    ranking is L6.
  * It fetches nothing for the disclosure layer. A floor member the promotion rule promoted
    whose body this run never fetched is disclosed at `snippet` with its unabridged
    affordance, not at a depth the response cannot fill: `max_body_fetches` is a published
    cap (A.7) and disclosure never initiates a fetch of its own, which is T-CD3's
    "reuse only, never trigger" applied structurally rather than as a habit.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from time import monotonic
from typing import Final

from pydantic import JsonValue

from mailweave.constants import (
    HOST_RESULT_CHAR_CAP,
    MAX_BODY_FETCHES_L0,
    MAX_HIT_THREADS,
    MAX_RECENCY_FETCH,
    MAX_SOURCE_THREADS,
    NEGATION_PREFIX,
    NORMAL_CEILING_TOKENS,
    QUERY_GROUPING_PUNCTUATION,
    auth_record_fits,
    operator_token,
    query_tokens,
)
from mailweave.disclosure.ladder import (
    DECLARED_OVERFLOW_STEP as _DECLARED_OVERFLOW_STEP,
)
from mailweave.disclosure.ladder import (
    HOST_CAP_WHY,
    Ceilings,
    cheapest_membership_cost,
)
from mailweave.disclosure.layout import Band, PlannedRow, PlannedSource, a_ceiling_bound
from mailweave.disclosure.pages import page_of, page_size
from mailweave.disclosure.plan import (
    Disclosure,
    PlannedThread,
    QueryAwareFill,
    Selector,
    ThreadInput,
    disclose,
)
from mailweave.disclosure.weights import FillScore, QueryFacts
from mailweave.envelope.builder import EnvelopeBuilder
from mailweave.envelope.disposition import DispositionLedger, ObservedEndpoint
from mailweave.envelope.measure import json_string_chars, request_echo_chars
from mailweave.envelope.reasons import (
    FloorPromoted,
    GmailQueryMatch,
    QueryScoredFill,
    Reason,
    ReasonKind,
    RecencyContext,
    ReplyChildOf,
    ReplyParentAmbiguous,
    ReplyParentOf,
    RungId,
    SemanticScore,
    ThreadMember,
    WindowOffset,
)
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import (
    RESOLVED_LINKAGES,
    BudgetCapName,
    ContentSource,
    Depth,
    EmptyDiagnosisStatus,
    NotTriedWhy,
    Role,
    Sufficiency,
    ToolName,
    Trust,
    WithheldCap,
    WithheldGranularity,
)
from mailweave.envelope.wire import (
    Affordance,
    AskedFor,
    Attribution,
    AttributionProvenance,
    Ceiling,
    CollapsedRun,
    Counters,
    DroppedConstraint,
    EmptyDiagnosis,
    ErrorEntry,
    MailboxProvenance,
    MessageRow,
    NotIncludedSource,
    NotTriedEntry,
    ParsedQuerySummary,
    Score,
    SemanticCost,
    SenderAuthentication,
    Source,
    ThreadParticipant,
    ThreadStructureReport,
    participants_within,
)
from mailweave.errors import DispositionInvariantError, ErrorCode
from mailweave.freshness.recency import RecencyRun, recency_widening
from mailweave.gmail.client import GmailClient, RecordedThread
from mailweave.gmail.models import Message
from mailweave.gmail.rates import GmailEndpoint
from mailweave.handles.digest import mapping_digest
from mailweave.handles.mint import HandleMinter
from mailweave.policy.account import (
    LADDER as PUBLISHED_LADDER,
)
from mailweave.policy.account import (
    LadderAccount,
    RungAccount,
    RungState,
    outcome_of,
)
from mailweave.policy.budget import WITHHELD_CAP_OF, BudgetAccountant, CapBreach
from mailweave.query.analysis import (
    ParsedQuery,
    carries_nothing_to_select_by,
    dropped_declarations,
    enforced_declarations,
    fold,
    region_constraint_names,
    region_declarations_of,
)
from mailweave.query.operators import UNPARSED_SYNTAX
from mailweave.ranking.mechanical import MECHANICAL_METHOD, Candidate
from mailweave.retrieval.ladder import (
    ExecutedProbe,
    LadderRun,
    RelaxationRung,
    why_this_q_is_not_a_probe,
    widen_scan,
)
from mailweave.retrieval.ranking import RankingRun, RankingState
from mailweave.retrieval.ranking import rank as rank_candidates
from mailweave.retrieval.semantic import SemanticRun, SemanticState
from mailweave.retrieval.signals import constraint_coverage_of
from mailweave.retrieval.structural import (
    MAX_STRUCTURAL_PROBES,
    StructuralPlan,
    plan_structural_expansion,
)
from mailweave.semantic.interface import REGISTRY, BackendRegistry
from mailweave.semantic.pool import PoolStep
from mailweave.structure.participants import ADDRESS_HEADERS, ObservedText, addresses_in_header
from mailweave.structure.threadmap import (
    ThreadMap,
    auth_record_of,
    from_header_of,
    snippet_observed_text,
)
from mailweave.structure.threadmap import build as build_thread_map


def _monotonic_ms() -> float:
    """The default clock for L6's own timing. Injected everywhere it matters; see `rank`."""
    return monotonic() * 1000.0


#: The `not_tried` name for the sibling-discovery signals AD D.6 lists that this round does
#: not implement - normalised subject, participant overlap, forward detection. They are
#: similarity judgements rather than identifier lookups (see `retrieval.structural`), and the
#: response says so rather than letting an absent source read as an absent relationship.
STRUCTURAL_SIMILARITY_RUNG: Final[str] = "structural_similarity"

#: The `not_tried` name for an L4 lookup declined because the `Message-ID` the child named
#: cannot be put into a Gmail `q` at all - it carries the query language's own punctuation,
#: or it is longer than a legible operator value (R-RETR-053). Named apart from `L4` itself
#: because the rung *ran*: reporting it as `L4 not_applicable` beside probes that went out
#: would contradict `rungs`, and reporting nothing - which is what happened - leaves a lookup
#: MailWeave chose not to make invisible in a response that accounts for everything else.
UNPROBEABLE_IDENTIFIER_RUNG: Final[str] = "L4:unprobeable_identifier"


def thread_map_affordance(thread_id: str) -> Affordance:
    return Affordance(tool=ToolName.THREAD_MAP, args={"thread_id": thread_id})


def unabridged_affordance(message_id: str) -> Affordance:
    return Affordance(
        tool=ToolName.GET_MESSAGES,
        args={"message_ids": [message_id], "view": Depth.BODY_FULL.value},
    )


#: The depths in disclosure order, so "below the requested depth" is one comparison.
_DEPTH_ORDER: Final[tuple[Depth, ...]] = (
    Depth.STUB,
    Depth.SNIPPET,
    Depth.BODY_CLEAN,
    Depth.BODY_FULL,
)


def _shallower_than(depth: Depth, wanted: Depth) -> bool:
    return _DEPTH_ORDER.index(depth) < _DEPTH_ORDER.index(wanted)


#: How many evidence rows one recommended expansion may name. **Not a new number**: A.7's
#: `max_body_fetches` at L0 (`MAX_BODY_FETCHES_L0`), the figure the architecture already gives
#: for "how many messages is it worth reading in full at the cheapest tier", and the same one
#: A.9a step 3 protects (`DISCLOSURE_TOP_K_HITS`). A recommendation is one more step-3's worth.
RECOMMENDED_EXPANSION_LIMIT: Final[int] = MAX_BODY_FETCHES_L0  # also `disclosure.layout`'s


def recommended_expansion(
    sources: Sequence[Source], *, evidence_ids: frozenset[str], evidence_view: Depth
) -> Affordance | None:
    """The one call that reads the evidence this response could not carry at the depth asked.

    **Round 28.** A response's rows are either evidence the query produced or the thread
    around it, and only the first kind is worth a recommendation: a reader that needs the
    text of a matched message should ask for that message by id, which preserves its identity
    and costs one read, rather than search again and hope the same message comes back. So
    this names **matched/evidence rows below the requested depth, and nothing else** - never
    a context row, never a map stub, and nothing at all when every evidence row is already at
    depth. Bounded by `RECOMMENDED_EXPANSION_LIMIT`, in wire order.

    It says nothing about which message answers the question; it is the rows the query
    matched, at the depth the caller asked for, that the ladder could not fit.
    """
    missing = [
        row.id
        for source in sources
        for row in source.messages
        if row.id in evidence_ids and _shallower_than(row.depth, evidence_view)
    ]
    # **A hit carried as a collapsed-run member is evidence below the depth asked for too**
    # (2026-09-15, R-M2-093): A.9a 7's last resort now collapses the last evidence-bearing
    # source rather than emptying the response, and the executable way back to those hits'
    # text is this read, named here in wire order after the rows.
    missing += [
        member
        for source in sources
        for run in source.collapsed_runs
        for member in run.member_ids
        if member in evidence_ids and member not in missing
    ]
    if not missing:
        return None
    named: list[JsonValue] = list(missing[:RECOMMENDED_EXPANSION_LIMIT])
    return Affordance(
        tool=ToolName.GET_MESSAGES,
        args={"message_ids": named, "view": evidence_view.value},
    )


def _why_this_thread_cannot_be_mapped(
    plan: ThreadPlan, recorded: RecordedThread, positions: Mapping[str, int | None]
) -> str | None:
    """Whether this `threads.get` can support a `Source` at all, and if not, why.

    Two shapes reach here, both of them the source failing to describe its own thread, and
    both answered the same way by A.7a: **do not map the thread; withhold every id observed
    in it, with the reason and a retrieval affordance.**

      * **it omits a hit its own `messages.list` returned.** The issue-#296 signature
        arriving *from Gmail*: search says message `m` is in thread `t`, and `threads.get(t)`
        comes back without it. MailWeave must not repeat that;
      * **it states no chronological order** (R-RETR-009). `_thread_scalars` refuses to
        invent positions when a message row carries no `internalDate` - PF-2's suspected
        `format=metadata` shape - and records why. Round 15's assembly then invented them
        anyway, from a sort key that degenerates to alphabetical-by-id with every date
        missing, and presented the result as amendment A3's "0-based index into the thread's
        **chronological** order". A3 refuses to clamp an out-of-range position "because
        clamping would silently move evidence"; an alphabetical order presented as
        chronological moves it just as silently while staying in range.

    **This function used to raise, and the raise denied the whole response.** Five healthy
    threads plus one self-disagreeing thread produced no envelope at all (R-RETR-010): safe
    about that thread, and unsafe about every other query the mailbox could have answered.
    A source that cannot describe itself is now one thread's disposition rather than the
    response's.

    What is genuinely inexpressible is narrower than round 15 recorded, and amendment A8's
    text has been corrected to say so: a **`Source`** for the disagreeing thread, which
    would have to state `stated_total` as exactly what the observation stated (amendment A6)
    *and* at least the distinct ids the ledger observed in it - nine and at-least-ten have no
    common value. Withholding the thread needs no such value and no schema change, which
    `test_one_self_disagreeing_thread_does_not_deny_the_other_five` executes.
    """
    # **Counts, not lists** (round 29, R-MCP-033). Both sentences used to enumerate the ids
    # they were about, and each sentence is then copied onto every `withheld` record for the
    # thread - so a thread with forty unplaced messages produced forty records each carrying
    # a forty-id list, which is the bookkeeping overflow in its worst form and one no sizing
    # constant can bound. The ids are not lost: every one of them gets its own record, which
    # is what a record is for (R-06). The sentence says how many; the records say which.
    # **Bounded, and written for the caller** (round 29). The citations that used to sit in
    # these sentences - issue #296, AD A.7a, amendment A3, PF-2 - are for a reviewer reading
    # this file, and this file is where they now live. A caller reading the response needs
    # what happened, how many, and what to do; each sentence is under 200 characters and its
    # length no longer depends on the thread, so a sizing constant can bound it.
    omitted = sorted(plan.listed - {message.id for message in recorded.thread.messages})
    if omitted:
        # The issue-#296 shape arriving from the source: the thread came back without the
        # message that caused the match, so no map of it can be shown that does not repeat
        # the omission (AD A.7a).
        return (
            f"the source returned this thread without {len(omitted)} of its matching "
            f"message(s), out of {len(recorded.thread.messages)} it enumerated, so no map of "
            "it can be shown; the withheld records name the messages"
        )
    unplaced = sorted(message_id for message_id, at in positions.items() if at is None)
    if unplaced:
        # A position is a 0-based index into the thread's chronological order (amendment A3);
        # inventing one would present an order the observation refused to state. The client
        # recorded why the scalars are absent (A6, PF-2); it is reported as a count here.
        return (
            f"the source stated no chronological position for {len(unplaced)} of this "
            "thread's messages, so it cannot be shown in order; the withheld records name "
            "the messages"
        )
    return None


def _withhold_the_whole_thread(
    ledger: DispositionLedger, plan: ThreadPlan, recorded: RecordedThread
) -> None:
    """A.7a's disposition for a source that cannot describe itself, executed.

    Every id the ledger observed **in this thread** - the hits `messages.list` put there and
    the rows `threads.get` returned, whichever the seal recorded - becomes a
    `partial_source_failure` withheld record carrying `why` and a `mailweave_get_messages`
    affordance for that id. Nothing is disclosed from the thread, so no position, order or
    completeness is claimed about it, and `H = disclosed union withheld` still holds because
    every observed id has a disposition. Amendment A8 said this answer was "not expressible
    in the shipped schema"; it is, and A8's text now says so.

    The cost is real and is not hidden: the thread's healthy messages arrive as withheld
    records with a retrieval path rather than as rows. That is a worse answer about this
    thread than a `Source` would be, and a much better one than either denying the whole
    response or shipping an order the observation refused to state.
    """
    observed_here = {
        message_id
        for message_id, origin in ledger.origins.items()
        if origin.thread_id == plan.thread_id
    }
    charged = sorted(
        observed_here | {message.id for message in recorded.thread.messages} | set(plan.hit_ids)
    )
    for message_id in charged:
        ledger.note_withheld(
            message_id=message_id,
            cap=WithheldCap.PARTIAL_SOURCE_FAILURE,
            # **Stated once, on the thread's `not_included_sources[]` block** (round 29).
            # `why` is that sentence; every record for the thread used to carry its own copy.
            why=(
                f"this thread could not be mapped; not_included_sources says why for thread "
                f"{plan.thread_id}"
            ),
            affordance=unabridged_affordance(message_id),
            # **Not grouped.** The affordance here names the message, because a thread whose
            # map disagreed with itself can still have its individual messages read - which is
            # the whole point of offering the unabridged call rather than another map. A cap
            # whose remedy names a message keeps a record per message (round 29).
        )


def _total_this_thread_can_state(
    ledger: DispositionLedger, plan: ThreadPlan, recorded: RecordedThread
) -> int | None:
    """The `threads.get` enumeration, or `None` when it disagrees with what was observed.

    **This is the whole of what amendment A8 correctly identified as inexpressible**, in one
    line. A completeness number below the number of ids the ledger observed in that thread
    "makes an incomplete answer report itself complete", and `Envelope` refuses it for a
    `Source` and for a `NotIncludedSource` alike. There is no value that is both what the
    source said and at least what was seen, so MailWeave states neither and says so in `why`
    - which is `None`'s meaning on this field and is the answer a schema that cannot hold
    two completeness claims can still give. The thread whose order is underivable has no
    such disagreement and states its total normally.
    """
    seen = {
        message_id
        for message_id, origin in ledger.origins.items()
        if origin.thread_id == plan.thread_id
    } | set(plan.hit_ids)
    enumerated = len(recorded.thread.messages)
    return enumerated if enumerated >= len(seen) else None


@dataclass(frozen=True)
class ThreadPlan:
    """One hit-bearing thread and the rung that found it, in the order threads are mapped."""

    thread_id: str
    rung: RungId
    hit_ids: frozenset[str]
    #: Every id a listing rung put in this thread, before A16's evidence narrowing (review
    #: finding F6). `hit_ids` is what the response treats as evidence; this is what the
    #: source was asked about, and the issue-#296 integrity check reads it - a `threads.get`
    #: that comes back without a message `messages.list` returned is the source disagreeing
    #: with itself whether or not that message is evidence. Defaults to `hit_ids` so a plan
    #: built elsewhere (L4's siblings, LR's arrivals) is unchanged.
    listed_ids: frozenset[str] | None = None

    @property
    def listed(self) -> frozenset[str]:
        return self.hit_ids if self.listed_ids is None else self.listed_ids


def recency_probe_queries(semantic: SemanticRun | None) -> frozenset[str]:
    """The queries D.5 step (c) sent for this run, and nothing else (A16).

    Read off the pool's own plan rather than recognised from the query text: step (c) writes
    `after:<epoch>` and so may a caller, and A16 turns on *which probe listed the message*,
    not on what the clause looks like. A user's own date-filtered search is a lexical rung's
    query and never appears here.
    """
    if semantic is None or semantic.plan is None:
        return frozenset()
    return frozenset(
        probe.query for probe in semantic.plan.probes if probe.step is PoolStep.RECENCY
    )


def pool_listed_only(
    ledger: DispositionLedger,
    *,
    shortlisted: Collection[str],
    queries: Collection[str] | None = None,
) -> frozenset[str]:
    """Ids whose **every** `messages.list` route is an L5 pool probe, minus the shortlist.

    With `queries`, only probes whose query is one of those count - which is how A16 asks
    about D.5 step (c) alone and leaves step (b)'s participant probes where they are.

    **Read off `routes`, not `origins`** (A16). An id's origin is its *first* admission and
    does not move, so a message a pool probe listed before a lexical rung matched it carries
    an L5 origin for ever; asking the origin would strip a lexical match of its protection on
    an accident of ordering. Asking every route answers the question that was meant: was this
    id ever reached by anything but the pool's own probe? A repeat sighting counts, an
    overlapping route counts, and the shortlist - the one part of the rung that selects
    rather than lists - counts most of all.

    `threads.get` routes are deliberately not consulted: thread membership is not a listing
    and has never made a row evidence (`hit_threads` reads `messages.list` alone), so an id
    the pool both listed and read is still pool-listed. A **`history.list`** route is the
    opposite case and does rescue an id: LR surfaces a real arrival on its own route, its ids
    are hits of their own thread plan (`_recency_plans`), and the ninety-day window the pool
    probes overlaps the freshness window by construction - so without this an LR arrival
    would lose its tier whenever the pool happened to list the same thread (review finding
    F4), which is the common case rather than an edge.
    """
    selected = frozenset(shortlisted)
    wanted = None if queries is None else frozenset(queries)
    found: set[str] = set()
    for message_id, routes in ledger.routes.items():
        if message_id in selected:
            continue
        if any(route.endpoint is ObservedEndpoint.HISTORY_LIST for route in routes):
            continue
        listings = [route for route in routes if route.endpoint is ObservedEndpoint.MESSAGES_LIST]
        if not listings:
            continue
        if all(
            route.rung is RungId.L5 and (wanted is None or route.query in wanted)
            for route in listings
        ):
            found.add(message_id)
    return frozenset(found)


def hit_threads(
    ledger: DispositionLedger,
    *,
    prefer: Collection[str] = (),
    semantic_order: Sequence[str] = (),
    not_evidence: Collection[str] = (),
    selected: Collection[str] = (),
) -> tuple[ThreadPlan, ...]:
    """Every thread a listing rung put a hit in, ranked so the cap is deterministic.

    **`not_evidence` and `selected` are A16's separation of accounting from evidence, and
    they are one rule: the evidence tier is what the *query* selected.** `not_evidence` is
    the ids an internal step-(c) recency probe listed and nothing else reached - they stay in
    `H` and keep every disposition they had, and lose the tier. `selected` is the shortlist,
    which the owner's decision makes eligible semantic evidence "however it was listed".

    **The second half is not decoration, and the first review of A16 shipped without it.**
    This function builds a thread's hits from `messages.list` observations, and D.5's pool
    embeds *every row of a thread it reads* - so the shortlist routinely selects a message
    the step-(c) probe never listed (it is outside the window, or past the probe's single
    page). Before A16 such a thread was hit-bearing anyway, through the recency-only rows
    beside it; after the subtraction alone it was hit-bearing through nothing, while
    `_split_off_unselected_pool_threads` still kept it as a source because the shortlist had
    selected in it. A source with the decisive message in it and an empty `hit_ids` turns
    `_carries_nothing` to its "there was never any evidence" branch and lets step 7 drop the
    source freely - the exact overclaim A16 exists to prevent, one layer down. Demonstrated
    on a two-message thread (independent review, finding 1).

    The union is applied to threads this function already plans and to their `hit_ids` only:
    `rung_of`, the ranking and `listed_ids` are computed from the listings alone, so nothing
    about ordering, rung attribution or the issue-#296 integrity check moves.

    Ranked by the ladder position of the earliest rung that admitted a hit in the thread,
    then by whether the thread is in `prefer`, then by its position in `semantic_order`,
    then by thread id. The first two halves are facts of the ledger and of the run rather
    than of this function: the rung travels on `HitOrigin`, written by the observation that
    admitted the id, and `prefer` is L1b's intersection - the decomposition rung's own
    answer, which would otherwise sort level with the broad single-constraint matches its
    probes also pulled in.

    **The order is the published ladder's, not the lexical five.** It used to be
    `retrieval.ladder.LADDER_RUNGS`, which has five members, and `rank` for anything outside
    it fell through to `len(order)` and was then re-read as `LADDER_RUNGS[-1]` - so a thread
    an L5 probe found would have been *reported as L3*: a rung attribution invented by an
    index clamp, in the field a reader uses to see which route produced the evidence. The
    nine-rung `policy.account.LADDER` is the one the response's own `rungs` list is built
    against, so this reads the same one.

    **`semantic_order` is the one place relevance enters this ordering, and only inside
    L5.** Without it the pool's threads would be mapped in thread-id order, which for a
    25-thread pool and `max_hit_threads = 12` means the shortlist - the entire output of the
    scored retriever - would be cut by an alphabetical accident. Lexical threads are
    unaffected: none of them appears in `semantic_order`, so they all take the same default
    rank and keep the ordering they had. At L0-L3 there is still nothing to rank by (RO F1
    gives `id` and `threadId` and nothing else), which is why this is not a general relevance
    key but a rung-local one.
    """
    order = {rung: index for index, rung in enumerate(PUBLISHED_LADDER)}
    demoted = frozenset(not_evidence)
    # The shortlist's own ids, by the thread the ledger recorded them in. Read from
    # `origins` because a thread id is a fact of the observation and not of a route; which
    # *route* reached the message is what `not_evidence` decides, and these are exempt from
    # that decision by construction (`pool_listed_only` never returns a shortlisted id).
    chosen: dict[str, set[str]] = {}
    for message_id in selected:
        origin = ledger.origins.get(message_id)
        if origin is None or origin.thread_id is None:
            continue
        chosen.setdefault(origin.thread_id, set()).add(message_id)
    # **Membership is decided on routes, not on the first admission** (R-M2-108, 2026-09-18).
    #
    # `HitOrigin` records where an id *entered* `H` and a second sighting deliberately does
    # not move it, so an id whose first admission was a `threads.get` and which a later
    # `messages.list` also listed used to be skipped here entirely: it joined no thread, its
    # thread could go unplanned, and `listed_ids` under-reported what the ladder had listed.
    # The demotion predicate directly above (`pool_listed_only`) was rewritten onto
    # `AdmissionRoute` for exactly this reason and the grouping was left behind, so the two
    # halves of one rule read two different provenance records.
    #
    # `thread_id` still comes from the origin, and that is not an inconsistency: a route
    # records *how* an id was reached and carries no thread, while the thread an id sits in
    # is a fact of the observation. Which route reached it is the membership question; which
    # thread it is in is not.
    #
    # The rung likewise becomes the earliest **listing** rung across the id's routes rather
    # than the rung of its first admission. That is what this function's own contract already
    # says the number is - "the ladder position of the earliest rung that admitted a hit in
    # the thread" - and reading it off a first-admission artefact could report a thread an L1
    # probe listed as L5, in the field a reader uses to see which route produced the evidence.
    grouped: dict[str, set[str]] = {}
    rung_of: dict[str, int] = {}
    for message_id, origin in ledger.origins.items():
        if origin.thread_id is None:
            continue
        listings = [
            route
            for route in ledger.routes.get(message_id, ())
            if route.endpoint is ObservedEndpoint.MESSAGES_LIST
        ]
        if not listings:
            continue
        grouped.setdefault(origin.thread_id, set()).add(message_id)
        rank = min(
            order.get(route.rung, len(order)) if route.rung is not None else len(order)
            for route in listings
        )
        rung_of[origin.thread_id] = min(rung_of.get(origin.thread_id, rank), rank)
    preferred = frozenset(prefer)
    # **The semantic rank applies inside L5 and nowhere else, and the first version's
    # safety argument for that was false.** It said no lexical thread appears in
    # `semantic_order` - but D.5's pool step (a) *seeds the pool with the threads L0-L3
    # touched*, so lexical threads are shortlisted routinely, and the stage-A cosine was
    # deciding which lexical hits `max_hit_threads` mapped. That is a comparison the cosine
    # cannot make: the threads the shortlist's `k` cut off have no cosine at all, which is
    # ADV-110's mixed scale one layer out. So the key is guarded by the rung rather than by
    # an argument about who ends up in the list.
    l5_rank = {rung: index for index, rung in enumerate(PUBLISHED_LADDER)}.get(RungId.L5)
    semantic_rank = {thread: index for index, thread in enumerate(semantic_order)}
    unranked = len(semantic_rank)

    def _semantic_key(thread: str) -> int:
        if l5_rank is None or rung_of[thread] != l5_rank:
            return unranked
        return semantic_rank.get(thread, unranked)

    ranked = sorted(
        grouped,
        key=lambda thread: (
            rung_of[thread],
            0 if thread in preferred else 1,
            _semantic_key(thread),
            thread,
        ),
    )
    plans: list[ThreadPlan] = []
    for thread in ranked:
        index = rung_of[thread]
        plans.append(
            ThreadPlan(
                thread_id=thread,
                rung=PUBLISHED_LADDER[index] if index < len(PUBLISHED_LADDER) else RungId.L6,
                # **The thread stays in the list even when nothing is left** (A16). Its ids
                # are still in `H` and still owed a disposition, and the one that fits them
                # is the pool's own: `_split_off_unselected_pool_threads` takes an L5 thread
                # the shortlist passed over and `_undisclosed_caps` files its cap. Dropping
                # the thread here instead left those ids with no note at all, which
                # `certify` refused - correctly, and immediately.
                hit_ids=(frozenset(grouped[thread]) - demoted) | frozenset(chosen.get(thread, ())),
                listed_ids=frozenset(grouped[thread]),
            )
        )
    return tuple(plans)


def _decomposition_enforced(run: LadderRun) -> frozenset[str]:
    """What L1b's rung as a whole enforced, which is not what any one of its probes carried.

    Two contributions, and they are different facts:

      * whatever every executed decomposition probe carried **whole** - today the query's
        mailbox scope, which `decomposition_units_of` puts on every unit (R-RETR-019);
      * a constraint **every** unit of which was probed. A decomposed constraint is enforced
        by the rung rather than by any single probe: `rollout cutover` is answered by the
        intersection of two probes, neither of which carried `terms` on its own.

    The second is where the A.7 cap becomes visible at response level (R-RETR-024). At four
    units and `MAX_DECOMPOSITION_PROBES` of three, one piece of `terms` is never sent, so
    the intersection is a **superset** of the true one and a thread carrying no message with
    the fourth word is disclosed. That is the documented precision cost of the cap; what was
    missing is that the response went on reporting `enforced=('from','terms')` and
    `term_coverage: 1.0` over it. Now `terms` is not enforced, and the cap is a drop with a
    rung beside it rather than an inference a reader has to make from `scan_scope`.
    """
    probed: set[str] = set()
    carried: set[str] = set()
    for execution in run.executions:
        if execution.rung is not RungId.L1B:
            continue
        for entry in execution.executed:
            if entry.probe.unit is not None:
                probed.add(entry.probe.unit)
            carried |= set(entry.probe.enforced)
    if not probed:
        return frozenset()
    units = run.parsed.decomposition_units
    for constraint in run.parsed.constraints:
        pieces = [unit for unit in units if constraint.name in unit.derived_from]
        if pieces and all(unit.label in probed for unit in pieces):
            carried.add(constraint.name)
    return frozenset(carried)


def _routes(run: LadderRun) -> tuple[ExecutedProbe, ...]:
    """The probes whose results this response rests on: those whose **page returned rows**.

    The count read is `ids_returned` - the page's own hit count - and **not**
    `ids_admitted`, which is the delta of ids this probe was the first to record. The
    distinction is the one `_asked_for` has always drawn for a relaxation and it is
    load-bearing in both directions: the transport hands back counts rather than ids, so a
    probe that returned a row an earlier probe had already admitted reports an empty delta
    while having contributed to exactly what is disclosed. Keying on the delta would drop
    such a probe out of the account - and with it the drop a relaxation declared, which is
    ROUTE-03's log line.

    When **no** probe returned rows, every executed probe is a route, because a zero-hit
    response rests on all of them equally: "the whole query was executed and matched
    nothing" is a stronger and different statement from "part of it was", and the reader
    needs to know which one they have.
    """
    producing = tuple(entry for entry in run.executed_probes if entry.ids_returned)
    return producing or run.executed_probes


def _asked_for(run: LadderRun, *, disclosed_threads: Collection[str]) -> AskedFor:
    """T-RC3's block: what was parsed, what was enforced, what was dropped and why.

    **`enforced` is derived from what the executed rungs actually enforced** (R-RETR-020). It
    used to be "the parse, minus the constraints an L2 relaxation gave up", so every rung
    except L2 was assumed to have carried everything - and two ordinary shapes made that
    false. A query answered only by L3's whole-mailbox probe reported `enforced=('from',
    'terms')`, `dropped=[]` and `term_coverage: 1.0` for a spam message from a different
    sender, because L3's abandonment of `from:` was not a *relaxation*. A D.3 rule 1b stop at
    L0 reported `enforced=('phrase','terms')` for a run whose only executed `q` was the
    phrase, because a rung that never ran cannot have dropped anything. Both are the class of
    the round-15 blocker: not the wrong rows, but the response lying about them.

    A constraint is therefore enforced when **some route the response rests on carried it**,
    and dropped otherwise, named with the rung of a route that lacked it. Union rather than
    intersection, because the routes are alternatives: L1 finding rows while a broad L1b
    piece-probe also admits some does not make L1's enforcement untrue. What the union cannot
    do is invent an enforcement nobody performed, which is the failure being fixed.

    `_routes` decides which probes those are, and L1b contributes at the rung level through
    `_decomposition_enforced` rather than per probe, because a decomposition probe carries
    one piece and its siblings carry the rest. The one rule that is **unchanged** from round
    16 is the relaxation's: a probe that relaxed a constraint and matched something gave that
    constraint up, read off the page's own count. Extending the account to the other rungs
    must not weaken the one rung that already had one.

    `dropped` therefore has three sources, all named rather than merged into a number:

      * parse-time - the boolean and grouping tokens `ParsedQuery.render` cannot regroup, the
        `name:value` tokens it cannot prove, and the tokens that name nothing to match;
      * ladder-time relaxation - a constraint an L2 probe gave up, named with L2, which is
        ROUTE-03's log line at response level;
      * ladder-time non-enforcement - a constraint no route the response rests on carried:
        L3 replaced it with something wider, or the ladder halted before any rung sent it.

    `constraint_drop_depth` is `len(dropped)`, which the wire model enforces. With more than
    one route contributing evidence, that is the number of *distinct* constraints some route
    did not carry, which is at least the depth of any single route - stated here because the
    alternative reading (the depth of one route) would understate it.
    """
    parsed = run.parsed
    dropped = [
        DroppedConstraint(constraint=name, why=why) for name, why in dropped_declarations(parsed)
    ]
    decomposed = _decomposition_enforced(run)
    intersection = run.decomposition.intersection if run.decomposition is not None else frozenset()
    # L1b enforces a decomposed constraint through its **intersection**, not through any one
    # probe: `rollout cutover` is answered by two probes neither of which carried `terms`
    # alone. So the rung-level set counts only when a thread in that intersection is among
    # the ones being disclosed. A row a piece-probe put into a thread the intersection does
    # not contain satisfied that piece and nothing more, and crediting the rung for it is the
    # R-RETR-024 over-claim: twelve threads disclosed under `term_coverage: 1.0` when eleven
    # of them carry one word of two.
    decomposition_answered = bool(intersection & frozenset(disclosed_threads))
    # A relaxation that **matched something** gave its constraint up, and this reads the
    # page's own count rather than the admission delta for the reason `_routes` gives.
    relaxed_away = {
        name
        for entry in run.executed_probes
        if entry.probe.relaxes and entry.probe.dropped and entry.ids_returned
        for name in entry.probe.dropped
    }
    carried: set[str] = set()
    dropped_by: dict[str, RungId] = {}
    # **R-RETR-030's required fix is not computable from what the seam records, and that is a
    # property of the seal rather than of this function.** The reviewer asks that `enforced`
    # be intersected over "the routes that admitted a **disclosed** row" instead of unioned
    # over the routes that returned rows, and the union really does over-claim: a query with a
    # `label:` constraint reports it enforced over a disclosure containing a row admitted by a
    # route that did not carry it. But "which routes admitted a disclosed row" is unanswerable
    # here: `ExecutedProbe.ids_admitted` is the **delta** of ids a probe was the first to
    # record, because the transport hands back counts rather than ids precisely so that a
    # probe cannot report ids an earlier one recorded (`Decomposition`, `_routes`). A probe
    # that returned exactly the disclosed rows an earlier probe had already admitted has an
    # empty delta, so intersecting over "routes with a disclosed admission" drops it - which
    # is what `test_a_probe_whose_rows_an_earlier_probe_admitted_still_counts_as_a_route`
    # exists to forbid, and it fails when the change is made. Executed in round 18 and
    # recorded as open rather than closed by a fix that trades one over-claim for a
    # narrower under-count: it needs the seam to hand back the ids of a page, which is
    # WS-16's counting proxy (amendment A1's content witness), not a change here.
    for entry in _routes(run):
        this_route = (
            decomposed
            if (entry.probe.rung is RungId.L1B and decomposition_answered)
            else frozenset(entry.probe.enforced)
        )
        carried |= this_route
        for constraint in parsed.constraints:
            if constraint.name not in this_route:
                dropped_by.setdefault(constraint.name, entry.probe.rung)
    carried -= relaxed_away
    for name in relaxed_away:
        dropped_by[name] = RungId.L2
    enforced = tuple(c for c in parsed.constraints if c.name in carried)
    for constraint in parsed.constraints:
        if constraint.name in carried:
            continue
        rendered = constraint.render()
        if not run.rungs_run:
            # No rung executed at all - the Part-5 report. There is no rung to name as
            # having dropped the constraint, so the reason is why nothing could be planned,
            # which is the one honest thing the response can say about it.
            why = (
                why_this_q_is_not_a_probe(parsed.render())
                or f"no rung had a probe to send for {parsed.raw.strip()!r}"
            )
        elif constraint.name not in dropped_by:
            continue
        elif constraint.name in relaxed_away:
            why = (
                f"relaxation at {dropped_by[constraint.name].value} executed without "
                f"{rendered!r} (AD A.7 L2, ROUTE-03)"
            )
        else:
            why = (
                f"no route this response rests on carried {rendered!r}: the evidence came "
                f"from {dropped_by[constraint.name].value}, which executed without it "
                "(AD A.7, LEX-02)"
            )
        dropped.append(DroppedConstraint(constraint=constraint.name, why=why))
    summary = ParsedQuerySummary(
        operators={operator.name.value: operator.render() for operator in parsed.operators},
        terms=parsed.search_terms,
        timezone=parsed.timezone,
        window_utc=None if parsed.window is None else parsed.window.as_wire(),
    )
    return AskedFor(
        parsed=summary,
        enforced=enforced_declarations(parsed, enforced),
        dropped=tuple(dropped),
        term_coverage=parsed.term_coverage(enforced),
        constraint_drop_depth=len(dropped),
    )


def report_affordances(parsed: ParsedQuery) -> tuple[Affordance, ...]:
    """The concrete calls a zero-evidence **report** can offer, minted from its own drops.

    ROUTE-01's acceptance enumerates five things a zero-evidence response must carry, and the
    fifth is affordances. Over every zero-evidence response R-RETR produced - including the
    report class round 17 created, whose whole purpose is to tell a calling agent what to do
    instead - `envelope.affordances` was `[]` and `empty_diagnosis.affordance` was `None`
    (R-RETR-032). Affordances were minted only by `_empty_diagnosis`, from a restoring drop or
    a budget-bound one, and neither exists when no rung ran.

    **Each offer is derived from the declaration that produced it**, so an offer exists
    exactly when a different call would reach a rung:

      * `unproven_operator` - a `name:value` token outside Gmail's documented set is kept off
        the wire. Quoting it makes it a phrase, which L1 will execute: `thread:1837abf` is not
        an operator MailWeave can prove, `"thread:1837abf"` is a string Gmail can match;
      * `unparsed_syntax` - MailWeave does not regroup Gmail's booleans, so a grouped query
        executes nothing. The same query with the boolean and grouping tokens removed is what
        `render` would have executed, and it is a real search: `(zephyr OR borogrove)` becomes
        `zephyr borogrove`, which is narrower than the caller's `OR` and is the direction the
        ladder recovers from.

    **The third kind is gone, because it did not execute** (round 19, R-RETR-040). A query
    naming only where to look used to be offered `{"query": <the region>, "terms": []}` - the
    same refused query with a decorative empty slot beside it. Executed, it reaches no rung
    and sends no request: no tool in this tree takes a `terms` argument, and the region alone
    is the listing `why_this_q_is_not_a_probe` refuses under its own name. AD-03 says an
    affordance is a concrete call that would reach the untried rung, and an affordance that
    cannot be executed is worse than an absent one - contract I-4 is recoverability, and a
    promise of it the response cannot keep is the confident-but-wrong shape I-4 is about. The
    honest reading is R-RETR-023's own rule: the only thing that would help is a different
    question, and MailWeave does not invent one.

    **R-RETR-023's rule is kept: nothing is offered where nothing would help.** An empty
    query, a query of nothing but stopwords, a lone `?`, an operator written with no value -
    for each of those the only call that helps is a different question, and minting an offer
    that changes nothing is what that finding removed. Executed by
    `test_a_zero_evidence_report_offers_the_call_that_would_reach_a_rung`, which executes
    **every** offer every branch here mints rather than three that were listed, and by
    `test_a_report_with_nothing_to_offer_offers_nothing`.
    """
    offers: list[Affordance] = []
    if parsed.unknown_operators:
        quoted = parsed.raw
        for token in parsed.unknown_operators:
            quoted = quoted.replace(token, f'"{token}"', 1)
        offers.append(Affordance(tool=ToolName.SEARCH, args={"query": quoted}))
    if parsed.passthrough and not region_declarations_of(parsed):
        # **Not when the query declared a region** (round 19, R-RETR-035). Stripping the
        # grouping off `-(a OR b)` yields `-a b`, which negates the first and *asserts* the
        # second - so for a grouped region declaration the offer would be a call into the
        # region the caller excluded, minted by MailWeave rather than written by the caller.
        # Distributing a negation over a group is regrouping a boolean, which is the parser
        # this module does not have; where it matters, `tokenise` re-emits a group holding
        # one operator and no stripping is needed at all.
        stripped = " ".join(
            token.strip(QUERY_GROUPING_PUNCTUATION)
            for token in query_tokens(parsed.raw)
            if token not in UNPARSED_SYNTAX
        )
        plain = " ".join(part for part in stripped.split() if part)
        if plain and plain != parsed.raw.strip() and not carries_nothing_to_select_by(plain):
            offers.append(Affordance(tool=ToolName.SEARCH, args={"query": plain}))
    return tuple(offers)


def without_the_region_it_named(parsed: ParsedQuery) -> str | None:
    """The caller's own query minus the region it named, or `None` when there is no such call.

    **The recovery the region rule owes the caller** (round 19, R-RETR-040/041). A region
    declaration is not relaxable - dropping it moves the search rather than widening it - so a
    scoped query that finds nothing reports `untried_drops` naming a drop no budget can reach,
    and round 18 offered nothing beside it. That is the recall this round's conservative
    reading costs, and I-4 says a response that cannot answer must say what would: the call
    that would is the same search without the scope, and the caller makes it or does not.

    **Never for an exclusion.** A negated region declaration is the caller saying *not there*.
    Offering the query without it would be MailWeave proposing to read what it was told not to
    read - and the proposal is not idle, because the call it names is scope-free and A.7 L3's
    published step widens a scope-free query to the whole mailbox. So a query carrying any
    negated region declaration is offered nothing here, and the response says instead that the
    drop was not tried. If that is judged too conservative, the change belongs with the
    orchestrator and not in this function.

    `None` when the query named no region, when one of them is an exclusion, or when what is
    left is not a probe - a query of nothing but its own scope leaves nothing to search for,
    which is the listing `why_this_q_is_not_a_probe` refuses.
    """
    regions = region_constraint_names(parsed.constraints)
    if not regions:
        return None
    fragments = [f for c in parsed.constraints if c.name in regions for f in c.fragments]
    if any(operator_token(fragment).startswith(NEGATION_PREFIX) for fragment in fragments):
        return None
    kept = tuple(c for c in parsed.constraints if c.name not in regions)
    rendered = parsed.render(kept)
    if not rendered.strip() or carries_nothing_to_select_by(rendered):
        return None
    if why_this_q_is_not_a_probe(rendered) is not None or rendered == parsed.render():
        return None
    return rendered


def recovery_affordances(run: LadderRun) -> tuple[Affordance, ...]:
    """The concrete calls a zero-evidence response can offer **after** rungs have run.

    `report_affordances` covers the response class where nothing ran at all. This covers the
    commoner one: the ladder ran, found nothing, and named drops it did not try. R-RETR
    measured 729 of 822 zero-evidence responses carrying no affordance at all, with
    `in:sent <term>` - two untried drops and four untried rungs - among the examples
    (R-RETR-040).

    One offer kind, because one is what is executable today: the query without the region it
    named, for a query that named one positively. The other untried drops are structurally
    unprobeable at any budget - dropping the only content of a query leaves a listing - and
    R-RETR-023's rule is that an offer which reaches nothing is not minted. A budget-bound
    drop keeps its own offer, which `_empty_diagnosis` mints because that is where the budget
    is known.
    """
    recovered = without_the_region_it_named(run.parsed)
    if recovered is None:
        return ()
    return (Affordance(tool=ToolName.SEARCH, args={"query": recovered}),)


def _empty_diagnosis(run: LadderRun, *, disclosed: int) -> EmptyDiagnosis | None:
    """ADV-105's three states, decided from what L2 actually probed.

    * a probed drop produced hits -> `complete`, `restores` names it, with the call that
      re-runs the search without it. `untried_drops` is empty because the diagnosis
      question is answered; what was probed stays visible in `tried`;
    * every drop probed, none restored -> `complete`, `restores=None`. A real finding;
    * a drop was not probed - the `min(k, 6)` budget cut it, or L2 never ran - >
      `incomplete`, with `untried_drops` naming every drop that was not reached.

    **`None` on a response that answered the query**, which is not a fourth state: ROUTE-04
    scopes this field to "zero-hit outcomes", and a diagnosis of an empty result that was not
    empty is a sentence with no subject. Emitting `{"status":"complete","restores":null}`
    there would say *no single dropped constraint restores results* about a query whose
    constraints were never relaxed because they did not need to be - a claim wider than
    anything the ladder executed, which is this project's other recurring defect.

    The number read is `unrelaxed_evidence_count`, and two things would be wrong with any
    other. Disclosure alone counts the threads a broad L1b probe obliged the ledger to carry,
    which suppresses the diagnosis on exactly the queries that need it - the ones whose
    constraints matched separately and nothing matched them together. And `evidence_count`
    counts L2's own hits, which suppresses it the moment a relaxation *succeeds* - the
    ROUTE-04 case itself, where the whole point is to say which drop restored results.

    **A budget affordance is minted only when a budget is what stands in the way**
    (R-RETR-023). `incomplete` used to ship `{"relax": {"max_probes": k}}` unconditionally,
    and for the commonest query shape there is - one bare word, one quoted phrase - that
    offered exactly the budget the run already had: `max_relax_probes(1) == 1` and
    `RelaxationRung.plan` declines the probe at *any* budget, because dropping the only
    constraint renders an empty `q`. AD-03 requires an affordance to be a concrete call that
    would reach the untried rung; that one reaches nothing, so following it changes nothing.
    A drop the rung will never plan is still reported in `untried_drops` - it was not tried,
    and saying so is the point of the field - but it is reported without an offer.

    **What this does not do, and why.** ADV-105's schema distinguishes "the budget ran out"
    from "no single drop restores results"; there is a third case, "this drop is structurally
    unprobeable at any budget", and it is still carried by `incomplete` rather than by a
    status of its own. `EmptyDiagnosisStatus` is a closed wire vocabulary and adding a member
    is a contract change (WS-10); what a reader can see today is `untried_drops` naming the
    drop, no affordance offering to reach it, and `not_tried` naming L2 `not_applicable`.
    Recorded as open with this reproduction rather than closed by inventing a vocabulary
    value.
    """
    if disclosed and run.unrelaxed_evidence_count:
        return None
    tried = tuple(step.dropped for step in run.relaxation)
    if not run.rungs_run:
        # The report class: no rung executed, so there is no drop to diagnose and the only
        # honest offer is the call that would let a rung run at all (R-RETR-032).
        offers = report_affordances(run.parsed)
        return EmptyDiagnosis(
            status=EmptyDiagnosisStatus.COMPLETE,
            tried=tried,
            untried_drops=(),
            restores=None,
            affordance=offers[0] if offers else None,
        )
    restoring = next((step for step in run.relaxation if step.hit_count > 0), None)
    if restoring is not None:
        return EmptyDiagnosis(
            status=EmptyDiagnosisStatus.COMPLETE,
            tried=tried,
            untried_drops=(),
            restores=restoring.dropped,
            affordance=Affordance(
                tool=ToolName.SEARCH, args={"constraints": {restoring.dropped: None}}
            ),
        )
    if run.untried_drops:
        reachable = RelaxationRung().plannable_drops(run.parsed)
        budget_bound = tuple(name for name in run.untried_drops if name in reachable)
        # **A drop the budget cut is offered the budget; a drop the region rule refused is
        # offered the call itself** (round 19, R-RETR-040/041). The second class is the one
        # this project created when it made the region unrelaxable, and until then it was
        # reported with nothing beside it: `in:sent <term>` named two untried drops, four
        # untried rungs and no way onward. `recovery_affordances` mints the caller's own
        # query without the scope it named, and mints nothing when that call would undo an
        # exclusion the caller wrote. What is left after both - a drop no probe exists for at
        # any budget - is still reported without an offer, which is R-RETR-023's rule.
        onward = recovery_affordances(run)
        return EmptyDiagnosis(
            status=EmptyDiagnosisStatus.INCOMPLETE,
            tried=tried,
            untried_drops=run.untried_drops,
            restores=None,
            # **Round 24 put the caller's own query into this offer.** `{"relax":
            # {"max_probes": k}}` named a probe budget no code accepted - `max_relax_probes`
            # was `min(k, 6)` with no ceiling parameter - and it named no query, so it was
            # not a call `mailweave_search` would take either. Both halves are fixed
            # together: the ceiling is now an argument that can only raise the cap, and the
            # query travels with it, so this is an executable call in the sense contract
            # R-07 means (`test_every_affordance_this_server_mints_is_a_valid_argument`).
            affordance=(
                Affordance(
                    tool=ToolName.SEARCH,
                    args={
                        "query": run.parsed.raw,
                        "relax": {"max_probes": len(run.parsed.constraints)},
                    },
                )
                if budget_bound
                else (onward[0] if onward else None)
            ),
        )
    return EmptyDiagnosis(
        status=EmptyDiagnosisStatus.COMPLETE, tried=tried, untried_drops=(), restores=None
    )


def _not_tried(run: LadderRun) -> tuple[NotTriedEntry, ...]:
    """The lexical rungs that did not run, each under the reason it did not run for.

    **Three reasons, not one** (WS-10, and the vocabulary question round 15 left open). This
    function used to write `not_applicable` over all of them, which said "this rung could not
    have helped" about rungs that were applicable and merely unnecessary. `RungExecution`
    now carries the reason the runner recorded:

      * `not_applicable` - the rung had no plan for this query. No call reaches it, so no
        affordance;
      * `stopped_on_evidence` - a D.3 stop rule had settled the query, or the escalation gate
        found evidence. Carries `force_rungs`, which is the call that reaches it;
      * `budget` / `cap` / `timeout` - the accountant refused. Carries the call that raises
        the cap it named.

    **L4 is no longer among the absent ones** (round 20): it is built, so it reports itself
    through `_l4_not_tried`. Rungs L5/L6/LR remain absent rather than listed: they are not
    built, and there is no honest value for "this rung does not exist yet" - the two
    candidates would say either that it could not have helped or that a budget would reach
    it, and both are false. The consequence is carried, as before, by never emitting
    `not_found` from a response whose ladder is incomplete; `_unbuilt_rungs_forbid_not_found`
    is where that is enforced rather than remembered.
    """
    entries: list[NotTriedEntry] = []
    for execution in run.executions:
        if execution.skipped is None:
            continue
        entries.append(
            NotTriedEntry(
                rung=execution.rung.value,
                why=execution.skipped,
                affordance=execution.affordance,
            )
        )
    return tuple(entries)


def coverage(run: LadderRun, message_id: str) -> tuple[str, ...]:
    """LEX-02's `constraint_coverage`, through the one function that computes it.

    `mailweave.retrieval.signals.constraint_coverage_of` filters the admitting probe's
    `enforced` list down to names the parse actually produced, so a row can never name a
    constraint the user did not write. Reading `run.admitted_by` here instead would be a
    second, unfiltered copy of the same derivation - and this repository's rule is that a
    fact has one derivation (R-ARCH-031).
    """
    return constraint_coverage_of(run.parsed, admitted_by=run.admitted_by, message_id=message_id)


def _reason(message_id: str, ledger: DispositionLedger) -> Reason | None:
    """The mechanical account of why a hit is here: the `q` that admitted it, and its rung.

    Read off `HitOrigin`, which the observation wrote. A reason assembled from what this
    function believes about the message would be a second, independent claim about the
    mechanism - the decorative rationale PART-07 forbids, wearing a mechanical shape.
    """
    origin = ledger.origins.get(message_id)
    if origin is None or origin.query is None or origin.rung is None:
        return None
    return GmailQueryMatch(query=origin.query, rung=origin.rung)


def _sufficiency(run: LadderRun, disclosed: int) -> Sufficiency:
    """A.8's per-rung evidence verdict, which is not the response's `outcome` (D.2).

    Keyed on `evidence_count` rather than on how many rows the disclosure carried, for the
    same reason `_empty_diagnosis` is: a thread mapped because a broad decomposition probe
    touched it is disclosure the ledger obliged, not evidence the query produced.
    """
    if run.stop_rule is not None:
        return Sufficiency.SUFFICIENT
    if disclosed == 0 or run.evidence_count == 0:
        return Sufficiency.INSUFFICIENT
    return Sufficiency.AMBIGUOUS


# --- WS-05: the thread map, and the rows it makes possible ---------------------------------


@dataclass(frozen=True)
class RecoveredParent:
    """What one L4 probe was for, and how many messages its identifier turned out to name.

    `matched_messages` is the count of ids that one `rfc822msgid:` probe put into `H`. One
    is the ordinary case and the row it produces is disclosed as `reply parent of <child>`.
    More than one is R-RETR-050's shape: the `Message-ID` the child named is carried by
    several messages, so which of them the child named is not something anything here knows,
    and the rows say that instead of each claiming to be the parent.
    """

    for_child_id: str
    message_id_header: str
    matched_messages: int

    @property
    def names_one_message(self) -> bool:
        return self.matched_messages == 1


@dataclass(frozen=True)
class MappedThread:
    """One thread that was fetched, and either mapped or found undescribable.

    Carried from the fetch pass to the row-building pass rather than re-fetched, which is
    what keeps `threads.get` at one call per thread (I-3). `structure is None` and
    `unmappable is not None` are the same fact seen from two sides, and the constructor is
    the only place they are set together, so they cannot drift apart.
    """

    plan: ThreadPlan
    recorded: RecordedThread
    placed: dict[str, int | None]
    unmappable: str | None
    structure: ThreadMap | None
    #: What L4 recovered this thread for, when L4 recovered it. `None` for a thread the
    #: query's own rungs found.
    recovered: RecoveredParent | None = None


def _observed_text(run: LadderRun, message: Message) -> ObservedText | None:
    """The text this response actually holds for one message, or `None` for none at all.

    The **annotated body** when a body was fetched, else the `snippet` the observation
    carried, else nothing. `None` is the third state and it is what the participant index
    declares as `mentions_not_scanned`: PF-2 leaves it open whether `format=metadata` returns
    a snippet, so a thread mapped under that branch has no text for most of its rows, and
    reporting "no mentions" about them would be a negative derived from an absence.

    **`body_clean.text`, not `default_view`** (R-RETR-051). The default view is the
    `original` spans only, so quoted and forwarded blocks were excluded from what the mention
    scanner saw - the commonest mention shape in real mail - while `mentions_not_scanned`
    reported the row as scanned. Worse, it made the participant index a function of *which
    rows this query matched*: the same thread answered "who is named here" two different ways
    under two queries, because a different row got its body fetched. A7's rule is annotate,
    do not delete, and it applies to what is scanned as much as to what is shown; the default
    view remains what is *disclosed*, which is a separate decision and is unchanged.

    **The snippet is declared a truncation, because it is one.** Gmail cuts it at a length
    rather than at a word, so an address straddling the cut becomes a different address that
    is in no message (R-RETR-052). `ObservedText.truncated_at_end` carries that to the
    scanner, which discards a match touching the end. A short body whose snippet is really
    the whole of it is treated as truncated too - this cannot be told apart from here, and
    the cost is at most a mention missed at the very last character, which is the direction
    the participant index already declares it prefers.

    **What this does not close, and it is named rather than left to be found.** A row whose
    body was fetched is scanned over the whole body; a row that only ever had a snippet is
    scanned over ~200 characters. So the *mention* half of the participant index still
    depends on disclosure depth, and that is why `mapping_digest` (WS-06) covers the map and
    not `Source.participants`: see `mailweave.handles.digest`.
    """
    processed = run.bodies.get(message.id)
    if processed is not None:
        return ObservedText(text=processed.body_clean.text, truncated_at_end=False)
    if message.snippet is None:
        return None
    return ObservedText(text=message.snippet, truncated_at_end=True)


def _map_of(
    plan: ThreadPlan, recorded: RecordedThread, placed: Mapping[str, int | None], run: LadderRun
) -> ThreadMap:
    """The structural map of one mappable thread (WS-05, AD D.6).

    Positions come from the sealed observation, never from a sort performed here; the caller
    has already refused any thread the observation left unplaced, so the narrowing to `int`
    is a fact rather than an assumption.
    """
    positions = {message_id: at for message_id, at in placed.items() if at is not None}
    return build_thread_map(
        thread_id=plan.thread_id,
        messages=recorded.thread.messages,
        positions=positions,
        observed_text={
            message.id: text
            for message in recorded.thread.messages
            if (text := _observed_text(run, message)) is not None
        },
        tied_on_internal_date=recorded.tied_on_internal_date,
    )


def _structural_roles(
    structure: ThreadMap, hits: Collection[str]
) -> dict[str, tuple[Role, Reason]]:
    """`role` and the mechanical reason for each non-hit row the reply tree explains.

    Contract C-02d: *every structurally included message carries a mechanical reason naming
    the relation used*. `reply parent of <child>` and `reply child of <parent>` are those
    names, and both reason kinds have existed in `reasons.py` since WS-03 with nothing able
    to produce them - this is the producer.

    A row that is a parent of one hit and a child of another gets **parent**, because the
    parent is the message the reply chain needs in order not to lose the thing being replied
    to (OD-3's floor is about ancestors). Ties inside one role are broken by thread order,
    which is chronological, so the citation is the earliest hit the relation holds for and is
    a fact of the thread rather than of a set's iteration order.
    """
    order = {message_id: index for index, message_id in enumerate(structure.order)}
    ranked = sorted(hits, key=lambda message_id: order.get(message_id, len(order)))
    links = structure.structure.by_id
    children = structure.structure.children_of
    roles: dict[str, tuple[Role, Reason]] = {}
    for hit in ranked:
        parent = links[hit].parent_id if hit in links else None
        if parent is not None and parent not in hits and parent not in roles:
            roles[parent] = (Role.PARENT, ReplyParentOf(child_id=hit))
    for hit in ranked:
        for child in children.get(hit, ()):
            if child not in hits and child not in roles:
                roles[child] = (Role.CHILD, ReplyChildOf(parent_id=hit))
    return roles


def participants_block(
    structure: ThreadMap,
    *,
    display_names: Mapping[str, tuple[str, ...]] | None = None,
    builder: EnvelopeBuilder | None = None,
) -> tuple[ThreadParticipant, ...]:
    """The address-keyed index as wire rows, in address order (C-02b, STR-02).

    **`display_names` is INJ-05's other half.** The index was address-keyed and carried a
    *count* of the names each address used; the criterion asks for the pair itself, never
    pre-joined. Keyed on the address with the names beside it is that pair: a renderer cannot
    put the name where a reader looks for the identity, because the identity is the key.

    Both arguments are optional together, because this function is also called by the thread
    map surface, which builds its index from a map and has no envelope to fence with. A call
    that supplies neither produces what it always produced - the count alone - and the
    validator on `ThreadParticipant` holds a list, when there is one, to agreeing with it.
    """
    names = display_names or {}
    return tuple(
        ThreadParticipant(
            address=facts.address,
            authored=facts.authored,
            coauthored=facts.coauthored,
            addressed=facts.addressed,
            reply_to=facts.reply_to,
            mentioned=facts.mentioned,
            distinct_display_names=facts.distinct_display_names,
            display_names=(
                ()
                if builder is None
                else tuple(
                    builder.fence_content(
                        name,
                        trust=Trust.UNTRUSTED_THIRD_PARTY,
                        source=ContentSource.GMAIL_HEADER,
                    )
                    for name in names.get(facts.address, ())
                )
            ),
        )
        for _address, facts in sorted(structure.participants.by_address.items())
    )


def structure_block(
    structure: ThreadMap, *, rows: Sequence[MessageRow] = ()
) -> ThreadStructureReport:
    """The declared-gap block for one mapped thread (STR-01).

    Every number here is counted off the same links the rows carry, so the summary cannot
    disagree with the enumeration - which `Source` re-checks, because a count beside an
    enumeration is a second claim about one fact.

    **`linked`/`unlinked` count the rows this source ships**, not the whole map, because
    that is what `Source._the_structure_this_source_states_is_about_this_source` compares
    them against - and after A.9a's collapse steps the two differ. A message inside a
    declared collapsed run is present and reachable, and it is not a row; counting it here
    would be the summary disagreeing with the enumeration beside it, in the direction that
    is hardest to see.
    """
    linked = sum(1 for row in rows if row.linkage in RESOLVED_LINKAGES)
    return ThreadStructureReport(
        linked=linked,
        unlinked=len(rows) - linked,
        authorship_unknown=structure.participants.authorship_unknown,
        mentions_not_scanned=structure.participants.mentions_unscanned,
        tied_on_internal_date=structure.tied_on_internal_date,
    )


def _rungs_run(
    run: LadderRun,
    plan: StructuralPlan,
    sent: int | None = None,
    semantic: SemanticRun | None = None,
    recency: RecencyRun | None = None,
    ranking: RankingRun | None = None,
    semantic_admitted: bool = False,
) -> tuple[RungId, ...]:
    """The rungs this response's evidence came out of, L4 and L5 included when they ran.

    `rungs` is a parameter of `EnvelopeBuilder.build` rather than something the ledger can
    supply, because a rung that executed and returned nothing leaves no trace in `H` -
    and `Envelope` refuses a `rungs` that omits a rung which *did* admit ids. So L4 has to
    be added here, and it is added on **having sent a probe**, not on having found anything:
    the second reading would make a fruitless expansion invisible, which is the same
    silence the `not_tried` block exists to break.

    L5 is added on the same reading and for the same reason: a semantic rung that built a
    pool, embedded it and shortlisted nothing still *ran*, and a response that omitted it
    would be claiming the rung was never reached.
    """
    executed = len(plan.probes) if sent is None else sent
    # **A rung that admitted ids ran** (R-M2-113). `SemanticState.RAN` describes the rung
    # *completing*, and D.5's failure states are reached after `_build_pool` has already sent
    # the pool's `messages.list` probes at L5 - so their ids are in `H` under L5 while the
    # state says the rung never ran. `Envelope._the_per_rung_hit_counts_are_the_ledgers_own`
    # then finds a rung that produced hits and is absent from `rungs`, and refuses the
    # response: the caller got no answer at all where D.5 promises a fallback. The validator
    # is right and this is the rule it was reading. The ids themselves are untouched - they
    # stay in `H`, keep their origins and are disposed of exactly as before.
    ran_semantic = semantic is not None and (
        semantic.state is SemanticState.RAN or semantic_admitted
    )
    ran_recency = recency is not None and recency.ran
    # **L6 was absent from this list for one draft, and the omission was the whole of a
    # finding.** A cross-encoder decided the response's source order, `_l6_not_tried` emitted
    # nothing because a tier had run, and `rungs` did not name L6 - so the rung was claimed
    # neither run nor not-tried, and a reader could not tell a reranked response from a build
    # with no L6 in it. The mechanical tier always runs when there are candidates, so L6 is
    # named whenever the ranking produced an ordering at all.
    ran_ranking = ranking is not None and ranking.state in {
        RankingState.RERANKED,
        RankingState.MECHANICAL_ONLY,
    }
    return (
        run.rungs_run
        + ((RungId.L4,) if executed else ())
        + ((RungId.L5,) if ran_semantic else ())
        + ((RungId.LR,) if ran_recency else ())
        + ((RungId.L6,) if ran_ranking else ())
    )


def _l4_not_tried(
    plan: StructuralPlan,
    executed: int,
    breach: CapBreach | None = None,
    *,
    run: LadderRun,
    cap: int = MAX_STRUCTURAL_PROBES,
) -> tuple[NotTriedEntry, ...]:
    """What L4 did not do, in AD D.2's closed vocabulary.

    **Three facts are reportable here, and two of them were being reported** (R-RETR-053).
    The rung sent no probe - it had nothing to expand on, or every unresolved parent named a
    `Message-ID` it cannot put into a query - which is `not_applicable`, because asking again
    would not help. Or it had more unresolved parents than `MAX_STRUCTURAL_PROBES`, which is
    `cap` and carries an executable way to raise it. The third is a *probe declined while
    others ran*: `StructuralPlan.skipped` holds the `(child, identifier)` pairs whose
    `Message-ID` carries Gmail's own query punctuation or is too long to be a legible
    operator value, and where at least one other probe went out, the mixed case emitted no
    L4 entry at all - a lookup MailWeave chose not to make, invisible in the response.
    Nothing was lost at the *message* level (the child's own row still declares its gap);
    what was missing is the rung's account of itself, which is what `not_tried` is for.

    The declined pairs are `not_applicable` rather than `cap`: `is_probeable` is a permanent
    inability of this identifier, not a budget this response ran out of, and marking it `cap`
    would put an affordance beside it that cannot help.

    **The other cap is not reported here, and that is deliberate.** A sibling thread past
    `max_source_threads` is not a rung that did not run: the probe ran, the ids entered `H`,
    and the disposition is a `withheld` record with a thread-map affordance -
    `_withhold_undisclosed_threads` files it and `DispositionLedger.certify` computes the
    set. Listing it as `not_tried` as well would be two accounts of one fact, and the
    withheld record is the one with the ids in it.

    `structural_similarity` is appended unconditionally: the sibling-discovery signals D.6
    lists that this round does not implement are `not_applicable` in every response, and an
    absent entry would let an absent source read as an absent relationship.
    """
    entries: list[NotTriedEntry] = []
    if breach is not None:
        # The budget stopped L4 before it finished its plan. Reported under the cap's own
        # reason, with the call that raises it, exactly as a lexical rung would be - and
        # ahead of `over_cap`, because the probe cap is not what stopped this one.
        return (NotTriedEntry(rung=RungId.L4.value, why=breach.why, affordance=breach.affordance),)
    if plan.over_cap:
        entries.append(
            NotTriedEntry(
                rung=RungId.L4.value,
                why=NotTriedWhy.CAP,
                affordance=Affordance(
                    tool=ToolName.SEARCH,
                    args={
                        "query": run.parsed.raw,
                        "structural": {"max_probes": cap * 2},
                    },
                ),
            )
        )
    elif not executed:
        entries.append(NotTriedEntry(rung=RungId.L4.value, why=NotTriedWhy.NOT_APPLICABLE))
    if plan.skipped and executed:
        entries.append(
            NotTriedEntry(rung=UNPROBEABLE_IDENTIFIER_RUNG, why=NotTriedWhy.NOT_APPLICABLE)
        )
    entries.append(NotTriedEntry(rung=STRUCTURAL_SIMILARITY_RUNG, why=NotTriedWhy.NOT_APPLICABLE))
    return tuple(entries)


def _fetch_and_map(
    plan: ThreadPlan,
    *,
    client: GmailClient,
    ledger: DispositionLedger,
    run: LadderRun,
    recovered: RecoveredParent | None = None,
    observed: RecordedThread | None = None,
) -> MappedThread:
    """One `threads.get`, its mappability verdict, and its structural map when it has one.

    The position map is read off the observation, never computed here: `_thread_scalars`
    already ranked the thread chronologically to seal those positions, and a second sort
    would be a second derivation of one fact (R-ARCH-031) - two derivations that can
    disagree, which is how a row lands in an array slot contradicting the number beside it.

    **`observed` is an observation this query already made of this thread, and passing it is
    not a cache.** The L5 pool reads its threads with `threads.get(format=metadata)` and the
    same header set a map needs, so a pool thread that reaches disclosure has already been
    fetched by *this* query. Re-fetching it would cost 40 u a second time (I-3) and - because
    each call stamps its own `fetched_at` while the ledger seals the first - would produce a
    source whose freshness stamp disagreed with the observation behind it, which `Envelope`
    refuses under contract R-08. The ledger is untouched either way: the ids were admitted
    when the pool made the call.
    """
    recorded = (
        client.get_thread(ledger, thread_id=plan.thread_id, rung=plan.rung)
        if observed is None
        else observed
    )
    origins = ledger.origins
    placed = {
        message.id: (None if (origin := origins.get(message.id)) is None else origin.position)
        for message in recorded.thread.messages
    }
    unmappable = _why_this_thread_cannot_be_mapped(plan, recorded, placed)
    return MappedThread(
        plan=plan,
        recorded=recorded,
        placed=placed,
        unmappable=unmappable,
        structure=None if unmappable is not None else _map_of(plan, recorded, placed, run),
        recovered=recovered,
    )


def _execute_structural_expansion(
    prepared: Sequence[MappedThread],
    *,
    run: LadderRun,
    client: GmailClient,
    ledger: DispositionLedger,
    accountant: BudgetAccountant | None = None,
    cap: int = MAX_STRUCTURAL_PROBES,
) -> tuple[StructuralPlan, dict[str, RecoveredParent], CapBreach | None, int]:
    """Run L4's probes and report what each recovered thread was recovered for.

    Returns the plan (so the response can declare what L4 did not do) and a
    `{thread id: RecoveredParent}` map, in probe order. Every id these probes return entered
    `H` before this function saw it - `list_messages` records the page into the ledger and
    hands back counts - so a thread this map does not name still has a disposition owed,
    which `_withhold_undisclosed_threads` files.

    **How many messages the probe matched travels with it** (R-RETR-050). A
    `rfc822msgid:` lookup is exact and usually returns one message; when it returns more
    than one - a resend, a list copy filed apart from the sender's own, a re-delivered
    message - the identifier the child named is carried by several messages and MailWeave
    cannot tell which one the child meant. The reply tree refuses exactly that shape inside a
    thread; counting the matches here is what lets `_rows_of` refuse it across threads
    instead of asserting two parents for one child.
    """
    unresolved: list[tuple[str, str]] = []
    for entry in prepared:
        if entry.structure is not None:
            unresolved.extend(entry.structure.unresolved_parent_ids)
    plan = plan_structural_expansion(run.parsed, unresolved, cap=cap)
    recovered: dict[str, RecoveredParent] = {}
    breach: CapBreach | None = None
    sent = 0
    for structural in plan.probes:
        # **L4's probes are charged like every other probe** (WS-10). A.7's caps are per
        # *query*, so a rung that spent nothing on `messages.list` at L0-L3 and then sent
        # four structural probes has still spent them. This is the third place the
        # accountant is consulted and it is consulted the same way in all three: before the
        # call, with the probes that already ran kept.
        if accountant is not None:
            breach = accountant.check((GmailEndpoint.MESSAGES_LIST,))
            if breach is not None:
                break
        before = ledger.hit_ids
        sent += 1
        client.list_messages(
            ledger,
            rung=structural.probe.rung,
            query=structural.probe.query,
            widening_affordance=widen_scan(structural.probe.query),
            include_spam_trash=structural.probe.include_spam_trash,
        )
        origins = ledger.origins
        returned = sorted(ledger.hit_ids - before)
        found = RecoveredParent(
            for_child_id=structural.for_child_id,
            message_id_header=structural.message_id_header,
            matched_messages=len(returned),
        )
        for message_id in returned:
            thread_id = origins[message_id].thread_id
            if thread_id is not None:
                recovered.setdefault(thread_id, found)
    return plan, recovered, breach, sent


def _query_facts(parsed: ParsedQuery) -> QueryFacts:
    """The part of the parse the E4 fill reads, folded once (AD A.9(3)).

    Participants come from the participant operators the query wrote, terms from its search
    terms. Neither is widened here: the fill scores against **what the caller asked**, and a
    fill that scored against a broadened form of the query would be scoring against a
    mechanism rather than against the user.
    """
    return QueryFacts.of(
        participants=[
            participant.address
            for participant in parsed.participants
            if participant.address is not None and not participant.negated
        ],
        terms=parsed.search_terms,
        has_date_window=parsed.window is not None,
    )


def _addresses_of(message: Message) -> frozenset[str]:
    """Every address this message's own address headers carry, folded.

    The E4 `participant_match` component's input, and it is read off the headers Gmail
    stated rather than out of any text: an address found in a body is a mention, and STR-02
    is the criterion that says a mention is not a participant.

    **The pair is `(display name, address)`, and this function unpacked it backwards.**
    `addresses_in_header`'s own docstring says so in its first line; the loop here read
    `for address, _display in ...`, so it collected display names - and for a bare
    `bo@team.example`, whose display name is the empty string, it collected `''`. The E4
    fill's highest-weighted component has therefore been matching the query's addresses
    against `{'', 'ana'}` rather than `{'ana@team.example', 'bo@team.example'}`: a
    query-derived signal that could only fire by coincidence, in the component A.9(3) ranks
    first precisely because it is the most query-driven one available. Found while writing
    LR's local re-check, which needs the same fact and copied the same mistake.
    """
    payload = message.payload
    if payload is None:
        return frozenset()
    found: set[str] = set()
    for name in ADDRESS_HEADERS:
        for _display, address in addresses_in_header(payload.header(name)):
            found.add(fold(address))
    return frozenset(found)


def _inside_the_query_window(run: LadderRun, message: Message) -> bool:
    """Whether this message's `internalDate` lies inside the window the query parsed.

    `False` when the query named no window, and `False` when this response observed no
    `internalDate`: an absence is an absence, never a negative claim.
    """
    window = run.parsed.window
    if window is None or message.internal_date is None:
        return False
    stamp = datetime.fromtimestamp(int(message.internal_date) / 1000, tz=UTC)
    if window.start is not None and stamp < window.start:
        return False
    return not (window.end is not None and stamp >= window.end)


def _subject_of(message: Message) -> str:
    """This message's `Subject` as the observation stated it, or the empty string."""
    payload = message.payload
    if payload is None:
        return ""
    return payload.header("Subject") or ""


def _stamp_of(message: Message) -> int | None:
    """`internalDate` as an integer, or `None` when the observation stated none (A6)."""
    if message.internal_date is None:
        return None
    return int(message.internal_date)


def _thread_input(
    entry: MappedThread, *, run: LadderRun, rank: int, mapped_at: int | None = None
) -> ThreadInput:
    """One mapped thread, projected down to what the disclosure layer is allowed to read.

    Every field is a fact of the `threads.get` that produced this map or of the run that
    fetched its bodies. Nothing is fetched here and nothing is derived twice: the positions
    and the reply tree come from the map WS-05 already built.
    """
    structure = entry.structure
    assert structure is not None  # only a mapped thread reaches here
    recovered = _recovered_parents(entry) if entry.recovered is not None else frozenset()
    by_id = {message.id: message for message in entry.recorded.thread.messages}
    links = structure.structure.by_id
    bodies = {
        message_id: processed.body_clean
        for message_id, processed in run.bodies.items()
        if message_id in by_id
    }
    return ThreadInput(
        thread_id=structure.thread_id,
        rank=rank,
        mapped_at=mapped_at,
        hit_bearing=bool(frozenset(entry.plan.hit_ids) - recovered),
        order=structure.order,
        positions=structure.positions,
        hit_ids=frozenset(entry.plan.hit_ids) - recovered,
        parent_of={message_id: links[message_id].parent_id for message_id in structure.order},
        children_of=structure.structure.children_of,
        subjects={message_id: _subject_of(by_id[message_id]) for message_id in structure.order},
        snippets={
            message_id: (by_id[message_id].snippet or None) for message_id in structure.order
        },
        bodies=bodies,
        internal_dates={message_id: _stamp_of(by_id[message_id]) for message_id in structure.order},
        addresses={message_id: _addresses_of(by_id[message_id]) for message_id in structure.order},
        auth_records={
            message_id: record
            for message_id in structure.order
            if (record := _auth_record_of(by_id[message_id]))
        },
        from_headers={
            message_id: (named[0], named[1])
            for message_id in structure.order
            if (named := from_header_of(by_id[message_id]))[0]
        },
        coverage={
            message_id: frozenset(coverage(run, message_id)) for message_id in structure.order
        },
        reductions={
            message_id: processed.reductions
            for message_id, processed in run.bodies.items()
            if message_id in by_id
        },
        participants=participants_block(structure),
        inside_query_window=frozenset(
            message_id
            for message_id in structure.order
            if _inside_the_query_window(run, by_id[message_id])
        ),
    )


def _page_width_of(entry: MappedThread, thread_id: str) -> int:
    """The width a `thread_map` call would page this thread at, sized on the map it observes.

    **Sized on the map a `thread_map` call will observe**, not on this search's own map
    (R-M2-081, the independent review): this map's participant index was scanned over fetched
    bodies, the served map's over snippets, and the `mentioned` citations differ - so the same
    thread would have had two widths. The snippet map is rebuilt here from the same
    `threads.get` rows and the same sealed positions. Computed once per source: the runs point
    at pages of it and the source's handle carries it (`HandlePayload.page_sizes`).
    """
    page_map = build_thread_map(
        thread_id=thread_id,
        messages=entry.recorded.thread.messages,
        positions={mid: at for mid, at in entry.placed.items() if at is not None},
        observed_text=snippet_observed_text(entry.recorded.thread.messages),
        tied_on_internal_date=entry.recorded.tied_on_internal_date,
    )
    return page_size(page_map)


def _collapsed_runs(
    planned: PlannedSource, entry: MappedThread, *, width: int
) -> tuple[CollapsedRun, ...]:
    """A.9a steps 2 and 5 as wire records: declared runs with an expansion affordance.

    **Each run points at the page of the thread's map its first position falls in**
    (navigation redesign, 2026-09-14): `mailweave_thread_map(thread_id, page)`, the same
    call a map's own runs and a read's inventory runs make, sized by the one arithmetic in
    `disclosure.pages`. It used to name AD §E.2's temporal segment, and following that call
    on a long thread declined terminally - a segment is every position of a span as rows and
    the ladder has no step below a stub - which is where the 2026-09-13 diagnostic's
    `DIAG-EXP-01` stopped. The segment map is still there for a caller who asks for it.
    """
    structure = entry.structure
    assert structure is not None
    records: list[CollapsedRun] = []
    for run_block in planned.runs:
        args: dict[str, JsonValue] = {
            "thread_id": planned.thread_id,
            "page": page_of(run_block.start, width),
        }
        records.append(
            CollapsedRun(
                positions=(run_block.start, run_block.end),
                count=len(run_block.member_ids),
                member_ids=run_block.member_ids,
                why=WithheldCap.DISCLOSED_TOKEN_CEILING.value,
                affordance=Affordance(tool=ToolName.THREAD_MAP, args=args),
            )
        )
    return tuple(records)


def _ceiling_withheld_here(entry: MappedThread, disclosure: Disclosure) -> tuple[str, ...]:
    """The ids A.9a step 8 withheld out of this source, for the map's own accounting.

    A map claims to enumerate its thread, and A.7a allows exactly three dispositions for a
    message: a row, a collapsed-run member, or a withheld record. Step 8 produces the third,
    so the source has to name them or `Source._a_claimed_map_accounts_for_every_message`
    refuses the map - which is the check doing its job.
    """
    structure = entry.structure
    assert structure is not None
    withheld = frozenset(disclosure.layout.withheld_ids)
    return tuple(sorted(withheld & frozenset(structure.order)))


def _the_ladder_removed_something(disclosure: Disclosure) -> bool:
    """Whether any A.9a step actually shortened the payload, as opposed to redeclaring it.

    Step 6 raises the declared ceiling and removes nothing; every other step reduces a
    depth, collapses a run, splits a source or files a withheld record. `truncated_by` is a
    statement about the second kind (DISC-06, `Envelope._self_truncation_is_verified_
    against_the_ceiling`).
    """
    return any(step.precedence != _DECLARED_OVERFLOW_STEP for step in disclosure.steps)


def _ceiling_of(disclosure: Disclosure) -> Ceiling:
    """AD D.2's `ceiling{}` block, derived from what the ladder actually applied.

    `why` is non-null exactly when the applied ceiling is the overflow, and the only reason
    it can carry is floor membership, because step 6 is the only thing that raises it and it
    raises it for nothing else.
    """
    applied = disclosure.layout.ceiling_applied
    if applied <= NORMAL_CEILING_TOKENS:
        return _declared_ceiling(applied)
    # **`why` states the number step 6 computed, not a sentence selected by `applied`**
    # (round 25, R-DISC-023). Step 6 raises the ceiling only when the response would exceed
    # the normal one with every message reduced to a bare stub row; that counterfactual is
    # the reason, so the field carries the figure a reader can check the payload against.
    floor_only = cheapest_membership_cost(disclosure.layout)
    carried = disclosure.layout.cost()
    binding = (
        "membership: this response cannot carry every message it accounts for within the "
        "normal ceiling even as bare stub rows"
        if floor_only > NORMAL_CEILING_TOKENS
        else (
            "disclosure depth: membership alone would fit the normal ceiling, and A.9a's "
            "rungs 3 and 4 stop at snippet, so no published step can reach that form"
        )
    )
    return Ceiling(
        normal=NORMAL_CEILING_TOKENS,
        applied=applied,
        why=(
            f"A.9a 6: steps 1-5 are exhausted and this response carries E2 floor membership. "
            f"It estimates {carried} tokens as carried and {floor_only} with every message "
            f"reduced to a bare stub row, against a normal ceiling of "
            f"{NORMAL_CEILING_TOKENS}. "
            f"What binds is {binding}"
        ),
    )


def _declared_ceiling(applied: int) -> Ceiling:
    """The `ceiling{}` block for a response held to `applied`, with the departure declared.

    A caller may lower the response's own ceiling through AD D.1's
    `budget.max_disclosed_tokens`. `normal` stays the published figure so a reader sees both,
    and `why` names the caller's request - because a response smaller than the architecture
    would have allowed is a response that left something out for a reason, and D.2's `why` is
    where that reason goes (round 25, R-MCP-004).

    **The host's character cap does not appear here** (round 26, R-DISC-033). It is a second
    ceiling in a second unit, not a lowering of this one, so a response the host cap reduced
    still declares the token ceiling it was held to - and says what the cap took in the place
    a reader looks for what was taken: the `why` on each `withheld` record, and the
    `not_included_sources[]` entry for each source that left whole.
    """
    if applied == NORMAL_CEILING_TOKENS:
        return Ceiling(normal=NORMAL_CEILING_TOKENS, applied=applied, why=None)
    return Ceiling(
        normal=NORMAL_CEILING_TOKENS,
        applied=applied,
        why=(
            f"the caller asked for a disclosed-token ceiling of {applied} through "
            f"budget.max_disclosed_tokens; the published ceiling is {NORMAL_CEILING_TOKENS} "
            "and this argument can only lower it"
        ),
    )


def _record_ladder_dispositions(
    disclosure: Disclosure,
    *,
    ledger: DispositionLedger,
    builder: EnvelopeBuilder,
    by_thread: Mapping[str, MappedThread],
    rank_of: Mapping[str, int] | None = None,
) -> None:
    """File the A.9a steps that removed something: split sources, and ceiling-withheld hits.

    Every id either step took becomes a `withheld` record naming `disclosed_token_ceiling`
    with an executable affordance, which is the only way a hit may leave the payload (A.7a,
    contract I-1). The ledger computes the disposition; this function reports which cap
    caused it.
    """
    # **Stated once** (round 29): every record, group and block this function files used to
    # embed this sentence. It goes on `omission.bound`; they refer to it.
    #
    # **And stated only when something refers to it** (round 30, live acceptance). The call
    # was unconditional, so a response the ladder never reduced still asserted "the response
    # reached its declared token ceiling". The live 5.1 record is the proof: 8,748 characters
    # of a 25,000 cap, `budget_caps_hit` without `disclosed_token_ceiling` - by the response's
    # own accounting no step ran - and `omission.bound` naming the token ceiling anyway, over
    # 45 messages withheld by `max_hit_threads` and `max_server_ms`. A reader told the wrong
    # cap reaches for the wrong argument, which is the defect `_binding_ceiling` was written
    # for one layer up. `bound` is optional on the wire; absent is the honest value when no
    # ceiling bound, and nothing this function files can refer to it in that case either.
    if a_ceiling_bound(disclosure.layout, reduced=bool(disclosure.steps)):
        builder.state_the_binding_ceiling(_binding_ceiling(disclosure))
    ranks = dict(rank_of or {})
    # Written best first (R-M2-096): step 7 splits the lowest-ranked source first, so the
    # order it removed them in was worst first, and a client walking the entries walked
    # away from the evidence.
    split_off = sorted(
        disclosure.layout.split_off,
        key=lambda thread_id: (ranks.get(thread_id) is None, ranks.get(thread_id, 0), thread_id),
    )
    for thread_id in split_off:
        entry = by_thread[thread_id]
        affordance = thread_map_affordance(thread_id)
        builder.add_not_included_source(
            NotIncludedSource(
                thread_id=thread_id,
                stated_total=len(entry.recorded.thread.messages),
                affordance=affordance,
                rank=ranks.get(thread_id),
            ),
            why=(
                "A.9a step 7: this source was split off to fit the ceiling stated in omission.bound"
            ),
        )
        builder.add_affordance(affordance)
    withheld_by_ceiling = frozenset(disclosure.layout.withheld_ids)
    grouped = disclosure.layout.grouped_ids
    for message_id in sorted(withheld_by_ceiling):
        if message_id in grouped:
            # **Round 29.** This id left inside a whole source that A.9a step 7 split off, and
            # the response already names that thread in `not_included_sources[]` with a map
            # call beside it. Its note is thread-granular and its affordance is that map: a
            # per-message call would be a second way to say the same thing, and forty of them
            # beside one entry is what made step 7 grow the response it was meant to shrink.
            # The map call is already in `affordances[]` from the not-included entry filed
            # above (R-V01-002: it was added once more per message here, four hundred times
            # for a four-hundred-message source, and charged once). `add_affordance` is
            # idempotent now as well, so a producer that forgets cannot repeat it either.
            affordance = thread_map_affordance(_thread_of(ledger, message_id))
            ledger.note_withheld(
                message_id=message_id,
                cap=WithheldCap.DISCLOSED_TOKEN_CEILING,
                why=(
                    "A.9a step 7: this source was split off to fit the ceiling stated in "
                    "omission.bound"
                ),
                affordance=affordance,
                granularity=WithheldGranularity.THREAD,
            )
            continue
        affordance = Affordance(
            tool=ToolName.GET_MESSAGES,
            args={"message_ids": [message_id], "view": Depth.BODY_CLEAN.value},
        )
        ledger.note_withheld(
            message_id=message_id,
            cap=WithheldCap.DISCLOSED_TOKEN_CEILING,
            why=(
                "A.9a step 8: this message could not be carried even as a collapsed-run "
                "member within the ceiling stated in omission.bound"
            ),
            affordance=affordance,
        )
        builder.add_affordance(affordance)


def _thread_of(ledger: DispositionLedger, message_id: str) -> str:
    """The thread the ledger observed this id in, or a refusal.

    Read off `HitOrigin` for the same reason `certify` reads it there (R-DISC-009): the thread
    on an omission record is derived from where the id was seen, never supplied beside it. A
    grouped note whose thread had to be guessed would be a guess the reader cannot tell from
    an observation, so this raises instead - and `certify` would refuse the response anyway.
    """
    origin = ledger.origins.get(message_id)
    thread_id = origin.thread_id if origin is not None else None
    if thread_id is None:
        raise DispositionInvariantError(
            f"no thread was observed for withheld id {message_id!r}, so this response cannot "
            "say which thread A.9a step 7 split off (R-DISC-009, R-MCP-033)"
        )
    return thread_id


def _binding_ceiling(disclosure: Disclosure) -> str:
    """Which of the two ceilings this response was actually reduced to fit (round 26).

    A reader who is told "the declared token ceiling" about a response that was well inside
    its token ceiling and over the **host's** character cap has been given the wrong reason,
    and the wrong reason sends them to the wrong argument: lowering
    `budget.max_disclosed_tokens` does nothing about a cap measured in characters. So the
    sentence names the cap that bound, and the record it goes on still carries the same
    executable affordance.
    """
    if disclosure.layout.host_capped:
        return HOST_CAP_WHY.format(cap=HOST_RESULT_CHAR_CAP)
    return "the response reached its declared token ceiling"


def _candidate_of(entry: MappedThread, *, run: LadderRun) -> Candidate:
    """One mapped thread, projected down to the facts `mailweave/mechanical-v1` reads.

    Every field is something an observation stated or a rung recorded, which is what makes
    the score reproducible from the response itself (C-04b). Nothing here is text and
    nothing here is derived from a model.
    """
    plan = entry.plan
    messages = entry.recorded.thread.messages
    wanted = {
        fold(participant.address)
        for participant in run.parsed.participants
        if participant.address and not participant.negated
    }
    participants: set[str] = set()
    for message in messages:
        participants |= _addresses_of(message)
    return Candidate(
        key=plan.thread_id,
        hit_messages=len(plan.hit_ids),
        participant_match=bool(wanted & participants),
        inside_query_window=any(_inside_the_query_window(run, message) for message in messages),
        # A thread reached by L0, L1 or L1b was reached by a route that carried every
        # constraint of the query; L2 dropped one and L3 widened the rest, so their hits
        # answer a question the user did not ask (see `LadderRun.unrelaxed_evidence_count`).
        unrelaxed_route=plan.rung in {RungId.L0, RungId.L1, RungId.L1B},
    )


def _semantic_reason(
    message_id: str,
    shortlisted: Mapping[str, object],
    semantic: SemanticRun | None,
    ledger: DispositionLedger,
) -> Reason | None:
    """A shortlisted row's reason: the cosine that selected it (AD D.5).

    **Never the probe's `q`.** L5's step-(b) and step-(c) probes are `messages.list` calls, so
    their ids carry a `HitOrigin` with the probe's own query - `after:<epoch>` for the recency
    probe - and `_reason` would render that as `gmail q matched at L5: after:1781346105` on
    every row of a semantic answer. That is a Gmail match this server never observed (R-03,
    T-RC3), and because D.7 suppresses the score on a `q`-selected row it also silenced the
    cosine that actually chose the row.

    **And only where a lexical rung did not also reach it.** A row the user's own `q` matched
    keeps that reason even when the shortlist also selected it: D.7 says results selected by
    Gmail `q` say exactly that, and it is the stronger statement of the two. The origin's rung
    is the test, because `HitOrigin` belongs to whichever observation admitted the id first
    and the ladder runs before the pool.
    """
    scored = shortlisted.get(message_id)
    if scored is None:
        return None
    origin = ledger.origins.get(message_id)
    if origin is None or origin.rung is not RungId.L5:
        return None
    cosine = getattr(scored, "cosine", None)
    if cosine is None:  # pragma: no cover - `Scored` always carries one
        return None
    model = (semantic.model_id if semantic is not None else None) or "unknown"
    return SemanticScore(cosine=float(cosine), model=model)


def _score_for(message_id: str, reason: Reason | None, ranking: RankingRun | None) -> Score | None:
    """The `Score` this row carries, or `None` - and `None` is the commoner answer.

    **A row Gmail's `q` selected carries no numeric score** (D.7). Its provenance is an exact
    statement about what Gmail matched, and a similarity number beside it would invite a
    reader to compare the two on one scale - which is the fabricated comparability RANK-03
    exists to prevent, arriving through the field meant to prevent it. The check is on the
    row's own `reason`, because that is the fact "selected by Gmail q" is recorded as.
    """
    if ranking is None or reason is None:
        return None
    if reason.kind in _Q_SELECTED_REASONS:
        return None
    return ranking.score_for(message_id)


#: The reason kinds that mean "Gmail's `q` selected this row". A score on one of these is
#: refused by `_score_for`; derived as a set here so a reason kind added later is a visible
#: decision about whether it is a `q` match rather than a silent inheritance.
_Q_SELECTED_REASONS: Final[frozenset[ReasonKind]] = frozenset(
    {ReasonKind.GMAIL_QUERY_MATCH, ReasonKind.RFC822_MSGID}
)


#: `Reply-To` is a routing directive the sender asserts; the rest are the address headers the
#: participant index is already built on.
_IDENTITY_HEADERS: Final[tuple[str, ...]] = ("From", "To", "Cc", "Reply-To")


def _display_names_of(messages: Sequence[Message]) -> dict[str, tuple[str, ...]]:
    """`{address: the distinct names it presented itself under}` across one thread (INJ-05).

    **Never pre-joined** (STR-02): `From: "Ana Lee" <mallory@elsewhere.invalid>` is authored by
    `mallory@elsewhere.invalid`, and a renderer handed the joined string will put the name
    first. Keyed on the address, so the pair on the wire has the identity as its key and the
    spoofable half beside it.

    Thread-level rather than per row, because that is where the index already is and where
    `distinct_display_names` already counts them - and because an address that used two names
    across a thread is exactly the fact worth seeing, which a per-row list would scatter.
    """
    found: dict[str, list[str]] = {}
    for message in messages:
        payload = message.payload
        if payload is None:
            continue
        for header in _IDENTITY_HEADERS:
            for display, address in addresses_in_header(payload.header(header)):
                if not display:
                    continue
                names = found.setdefault(fold(address), [])
                if display not in names:
                    names.append(display)
    return {address: tuple(names) for address, names in found.items()}


#: The rule moved to `structure.threadmap.auth_record_of` (navigation redesign, 2026-09-14)
#: so the map can carry its widest record; the name is kept for the callers that read it here.
_auth_record_of = auth_record_of


def _reply_to_differs(message: Message) -> bool | None:
    """Whether a `Reply-To` names an address the `From` does not (INJ-05, SN §7.2).

    `None` with no headers observed, because with none seen this response does not know - a
    `false` there would be a negative claim derived from an absence, the shape OD-5 ended one
    model over.
    """
    payload = message.payload
    if payload is None:
        return None
    authors = {fold(address) for _d, address in addresses_in_header(payload.header("From"))}
    replies = {fold(address) for _d, address in addresses_in_header(payload.header("Reply-To"))}
    return bool(replies - authors)


def _authentication_of(message: Message, builder: EnvelopeBuilder) -> SenderAuthentication | None:
    """What the receiving server recorded, fenced and verbatim. Never a verdict.

    There is no `passed` field here and this function computes none: `Authentication-Results`
    is written by a receiving MTA, this server neither re-verifies it nor knows which MTA in
    the chain wrote the copy it sees, and reducing it to a boolean would turn somebody else's
    record into this connector's claim - the connector-voiced surface INJ-02 forbids mail text
    from reaching, arriving the other way round.
    """
    payload = message.payload
    if payload is None:
        return None
    raw = payload.header("Authentication-Results")
    if not raw:
        # `None`, not an empty block: the row's `headers_observed` already says the headers
        # were read, so "read them and there was no record" needs nothing more on the wire.
        return None
    if not auth_record_fits(raw):
        # Declared, not truncated: this response does not rewrite a record it did not write.
        return SenderAuthentication(oversize=True)
    return SenderAuthentication(
        recorded=builder.fence_content(
            raw, trust=Trust.UNTRUSTED_THIRD_PARTY, source=ContentSource.GMAIL_HEADER
        ),
    )


def _attribution_of(message: Message | None, builder: EnvelopeBuilder) -> Attribution:
    """What the `From` header said, with where that came from (2026-09-21).

    One implementation for every row this server builds - the search rows here and the
    read rows in `surface/expansion.py` - so the two surfaces cannot disagree about who a
    header named. The address is folded the way the participant index folds it, so a
    row's `from_address` and the index's `address` compare equal for the same sender.
    """
    if message is None or message.payload is None:
        return Attribution(provenance=AttributionProvenance.HEADERS_NOT_OBSERVED)
    address, display, stated = from_header_of(message)
    if not stated:
        return Attribution(provenance=AttributionProvenance.FROM_HEADER_ABSENT)
    return Attribution(
        provenance=(
            AttributionProvenance.FROM_HEADER
            if stated == 1
            else AttributionProvenance.FROM_HEADER_MULTIPLE
        ),
        address=address,
        display_name=(
            None
            if not display
            else builder.fence_content(
                display, trust=Trust.UNTRUSTED_THIRD_PARTY, source=ContentSource.GMAIL_HEADER
            )
        ),
        stated_addresses=stated,
    )


def _rows_of(
    entry: MappedThread,
    *,
    run: LadderRun,
    ledger: DispositionLedger,
    builder: EnvelopeBuilder,
    planned: PlannedThread,
    ranking: RankingRun | None = None,
    recency: RecencyRun | None = None,
    semantic: SemanticRun | None = None,
) -> list[MessageRow]:
    """Every message of one mapped thread that survived the A.9a ladder, as a row.

    Three things each row gets that WS-05 added, and each of them is a fact of the
    observation rather than of this function: its `linkage` and `reply_parent_id` from the
    reply tree; a structural `role` and a mechanical `reply parent of` / `reply child of`
    reason when the tree explains why it is here (C-02d); and, unchanged, the provenance
    read off its own labels (OD-5).

    **What WS-11 added is the depth, and this function does not decide it.** `planned` is
    the disclosure layer's answer for this thread after A.9a's precedence has run over the
    whole response, so the depth, the disclosed text and every truncation record are read
    off it. A message the ladder collapsed into a run or converted into a `withheld` record
    is **absent from `planned.source.rows`** and therefore absent here; the caller carries
    it as a run member or a record, which are the other two dispositions A.7a allows.

    Two reasons are overridden against WS-05's structural pair, and both are narrowings
    rather than replacements: a floor member the promotion rule promoted carries
    `FloorPromoted`, which says the evidence *depends* on it and not merely how it is
    attached; and a row the E4 fill reached carries `QueryScoredFill`, which names the
    published components that fired (DISC-01: an inclusion carries a reason naming a
    mechanism traceable to the query).
    """
    structure = entry.structure
    assert structure is not None  # only a mapped thread reaches here
    plan = entry.plan
    links = structure.structure.by_id
    structural = _structural_roles(structure, plan.hit_ids)
    by_id = {message.id: message for message in entry.recorded.thread.messages}
    # **A row an L4 probe returned is not a row the query matched.** The probe is a
    # `Message-ID` lookup MailWeave composed out of another thread's headers, so
    # `gmail q matched at L4: rfc822msgid:<...>` would name the mechanism and not the
    # *relation*, which is what C-02d requires of a structurally included message - and
    # `role: matched` on a message the caller's query never touched is the confident-looking
    # over-claim this project exists to prevent. Those rows take `reply parent of <child>`
    # below instead.
    found = entry.recovered
    recovered = _recovered_parents(entry) if found is not None else frozenset()
    disclosed = {row.id: row for row in planned.source.rows}
    promoted = {
        member.message_id: member for member in planned.floor if member.dependence is not None
    }
    # **What LR surfaced, and the sentence each of those rows must carry.** D.9 fixes both
    # the role and the provenance string: `context`, never `matched`, and a reason that ends
    # by saying Gmail's `q` did not match this message. A row that took the ordinary hit
    # branch would claim a query match this server never observed.
    surfaced = {} if recency is None else {row.id: row for row in recency.surfaced}
    # **What the scored retriever selected, and what its probes merely listed.** L5's step-(b)
    # and step-(c) probes are `messages.list` calls, so their ids carry a `HitOrigin` with the
    # probe's own `q` - `after:<epoch>` for the recency probe - and the ordinary hit branch
    # rendered that as `gmail q matched at L5: after:1781346105`. The response was claiming a
    # Gmail match to a ninety-day window the user never wrote, on every row of a semantic
    # answer, and because that reason is a `q` match D.7 then suppressed the score as well. A
    # shortlisted row is evidence *from the retriever* and says so with its cosine; a pool row
    # the shortlist passed over is not evidence at all and is a thread-member stub.
    shortlisted = (
        {}
        if semantic is None or semantic.result is None
        else {row.message_id: row for row in semantic.result.selected}
    )
    # **Left exactly as it was by A16, deliberately** (review finding F2). Rewriting this to
    # read every route widened it: `_rows_of` runs *after* L4, so an id whose origin is the
    # pool's own probe and which L4 later listed would stop being `pooled_only` and start
    # reporting `matched` with the pool's internal `from:` probe as the Gmail `q` that
    # matched it - an over-claim `_semantic_reason` exists to prevent, and a widening where
    # A16 authorises only a narrowing. A16's demoted ids need no help from this rule: they
    # are not in `plan.hit_ids`, so `is_hit` is already false for them.
    pooled_only = frozenset(
        message_id
        for message_id, origin in ledger.origins.items()
        if origin.rung is RungId.L5 and message_id not in shortlisted
    )
    rows: list[MessageRow] = []
    for message_id in structure.order:
        if message_id not in disclosed:
            continue
        planned_row = disclosed[message_id]
        disclosed_text, disclosed_reductions = planned_row.rendered()
        message = by_id[message_id]
        position = structure.positions[message_id]
        link = links[message_id]
        is_hit = (
            message_id in plan.hit_ids
            and message_id not in recovered
            and message_id not in pooled_only
        )
        processed = run.bodies.get(message_id)
        # **A shortlisted row's reason is its cosine, not the probe's `q`.** Both branches
        # below read `reason`, so overriding it here is what stops the first one - the
        # body-bearing branch, which is where most evidence rows go - from rendering
        # `gmail q matched at L5: after:<epoch>` over a semantic answer.
        reason = _semantic_reason(message_id, shortlisted, semantic, ledger) or (
            _reason(message_id, ledger) if is_hit else None
        )
        # **Provenance is read off this message's own labels** (OD-5, A9-A1). The
        # `threads.get` response that produced this row states `labelIds`, so the region
        # the message lives in is a fact of the observation, not an inference from the
        # `q` that found it. Every row gets it - matched, stub and thread-map alike -
        # because a thread map can carry a spam reply into an otherwise ordinary thread
        # and a reader has to be able to see that without reading a reason string.
        #
        # **And when the observation stated no labels, the row says so** (round 19,
        # R-RETR-039). `Message.label_ids` is `None` for a response that carried no
        # `labelIds` and `()` for one that carried an empty list, which are different
        # facts: the first is "this response does not know", the second is "Gmail says
        # this message carries no labels". Reading them as one value made `observed` a
        # constant `true` over every row the product could produce, and made the response
        # state `outside_the_default_mailbox: false` about a message nothing had observed.
        provenance = (
            MailboxProvenance.unobserved()
            if message.label_ids is None
            else MailboxProvenance.of(message.label_ids)
        )
        if is_hit and processed is not None and reason is not None and disclosed_text is not None:
            rows.append(
                MessageRow(
                    id=message_id,
                    position=position,
                    role=Role.MATCHED,
                    reason=reason,
                    constraint_coverage=coverage(run, message_id),
                    mailbox=provenance,
                    depth=planned_row.depth,
                    linkage=link.linkage,
                    reply_parent_id=link.parent_id,
                    can_be_a_parent=link.can_be_a_parent,
                    reductions=disclosed_reductions,
                    unabridged=unabridged_affordance(message_id),
                    content=builder.fence_content(
                        disclosed_text,
                        trust=Trust.UNTRUSTED_THIRD_PARTY,
                        source=_content_source(planned_row),
                    ),
                    score=_score_for(message_id, reason, ranking),
                    headers_observed=message.payload is not None,
                    reply_to_differs=_reply_to_differs(message),
                    authentication=_authentication_of(message, builder),
                    attribution=_attribution_of(message, builder),
                )
            )
            continue
        if is_hit and reason is not None:
            role, row_reason = Role.MATCHED, reason
        elif message_id in shortlisted:
            assert reason is not None  # `_semantic_reason` returns one for every shortlisted id
            role, row_reason = Role.MATCHED, reason
        elif message_id in surfaced:
            # **AD D.9, verbatim, and this branch is the whole of the rule.** An `is_hit`
            # guard against `surfaced` stood here for one draft and was dead: `_reason` reads
            # `HitOrigin.query`, a `history.list` observation records none, and the origin
            # belongs to whichever observation admitted the id *first* - the ladder, when
            # both saw it. So a message Gmail's `q` really did match keeps `matched` and its
            # own query, and a message only LR saw arrives here. The guard would have
            # downgraded the first case, which is the one honest `matched` there is.
            #
            # The watermark and the re-checked operator list are the two facts that vary;
            # `RecencyContext.render` fixes the rest of the sentence.
            row = surfaced[message_id]
            assert recency is not None and recency.started_from is not None
            role, row_reason = (
                Role.CONTEXT,
                RecencyContext(
                    history_id=recency.started_from.history_id,
                    rechecked=row.verdict.checked,
                ),
            )
        elif found is not None and message_id in recovered:
            # **One child has one reply parent** (R-RETR-050). When the identifier lookup
            # returned exactly one message, this row is that message and `reply parent of
            # <child>` is what the child's own headers say. When it returned more, the rows
            # are context carrying a `Message-ID` the child named and an explicit count of
            # how many messages carry it - never two rows each asserting to be the parent.
            role, row_reason = (
                (Role.PARENT, ReplyParentOf(child_id=found.for_child_id))
                if found.names_one_message
                else (
                    Role.CONTEXT,
                    ReplyParentAmbiguous(
                        child_id=found.for_child_id,
                        message_id_header=found.message_id_header,
                        matched_messages=found.matched_messages,
                    ),
                )
            )
        elif message_id in structural:
            role, row_reason = structural[message_id]
            member = promoted.get(message_id)
            if member is not None and member.dependence is not None:
                row_reason = FloorPromoted(
                    relation=member.relation,
                    anchor_id=member.anchor_id,
                    dependence=member.dependence,
                )
        elif planned_row.band is Band.FILL:
            role, row_reason = Role.CONTEXT, _fill_reason(planned, message_id, hit_ids=plan.hit_ids)
        else:
            # **The role has to agree with the depth the plan chose (R-M2-056).** This branch
            # is "the plan included this message and nothing above claimed it": not a hit, not
            # structural, not a fill. It used to answer `Role.STUB` unconditionally while the
            # row still took `depth=planned_row.depth` from the plan, so a message the plan had
            # decided to disclose arrived as `role=stub` at snippet depth and `MessageRow`'s own
            # validator refused the pair - the search raised instead of answering. Reachable
            # whenever the plan discloses beyond the hit, structural and fill sets, which a
            # query matching nothing does, so EP §4.3's F10 control met it every time.
            #
            # A disclosed message is context; a named one is a stub. The depth already says
            # which, so the role reads it rather than guessing.
            role, row_reason = (
                Role.STUB if planned_row.depth is Depth.STUB else Role.CONTEXT,
                ThreadMember(thread_id=plan.thread_id, position=position),
            )
        rows.append(
            MessageRow(
                id=message_id,
                position=position,
                role=role,
                reason=row_reason,
                constraint_coverage=coverage(run, message_id) if is_hit else (),
                mailbox=provenance,
                depth=planned_row.depth,
                linkage=link.linkage,
                reply_parent_id=link.parent_id,
                can_be_a_parent=link.can_be_a_parent,
                reductions=disclosed_reductions,
                unabridged=unabridged_affordance(message_id),
                score=_score_for(message_id, row_reason, ranking),
                headers_observed=message.payload is not None,
                reply_to_differs=_reply_to_differs(message),
                authentication=_authentication_of(message, builder),
                attribution=_attribution_of(message, builder),
                content=(
                    None
                    if disclosed_text is None
                    else builder.fence_content(
                        disclosed_text,
                        trust=Trust.UNTRUSTED_THIRD_PARTY,
                        source=_content_source(planned_row),
                    )
                ),
            )
        )
    return rows


def _content_source(row: PlannedRow) -> ContentSource:
    """Which Gmail field this row's text came out of. A row says where its text is from."""
    if row.depth is Depth.BODY_CLEAN:
        return ContentSource.GMAIL_BODY
    return ContentSource.GMAIL_SNIPPET


def _fill_reason(
    planned: PlannedThread, message_id: str, *, hit_ids: Collection[str] = ()
) -> QueryScoredFill | WindowOffset:
    """The reason for one filled row, naming the mechanism whichever selector produced it.

    Two selectors, two mechanisms, and each row says which one reached it.

      * The shipped `QueryAwareFill` returns a `FillScore`, and the row carries
        `QueryScoredFill` naming the published components that fired and their sum, so a
        reader can recompute the decision from `mailweave.disclosure.weights`.
      * **Baseline F's `FixedWindow` returns a signed offset**, and the row carries
        `WindowOffset` naming the offset and the hit it is measured from. That is DISC-01's
        point rather than an exception to it: a fixed window's reason is a real mechanism and
        it is *not* traceable to the query, which is exactly why the criterion says a +/-2
        policy fails it by construction. Rendering it honestly is what makes the comparison
        readable; refusing to render it is what made the comparison **unrunnable**.

    Baseline F could not execute before this (round 32). `Selector` and `FixedWindow` have
    existed since WS-11, `_score_of` already inverted the offset so both arms degrade in the
    same order, and `plan.py`'s own docstring called the baseline "a permanent harness fixture
    (PROC-04), runnable here at the same ceiling" - and the first filled row it produced
    raised `DispositionInvariantError`. The same shape as R-M2-008: a published comparison
    fixture that cannot run.

    Still raises where the fill has no value at all: a row nothing selected is a row neither
    mechanism reached, and inventing a reason for it is the decorative rationale PART-07
    forbids.
    """
    result = planned.fill.get(message_id)
    if isinstance(result, FillScore):
        return QueryScoredFill(components=result.components, score=result.value)
    if isinstance(result, int):
        positions = {row.id: row.position for row in planned.source.rows}
        here = positions.get(message_id)
        anchor = None
        if here is not None:
            candidates = [
                (abs(positions[hit] - here), hit)
                for hit in hit_ids
                if hit in positions and hit != message_id
            ]
            if candidates:
                anchor = min(candidates)[1]
        if anchor is not None:
            return WindowOffset(offset=result, anchor_id=anchor)
    raise DispositionInvariantError(
        f"message {message_id} was banded as E4 fill and carries no component score. A "
        "filled row's reason names the mechanism that put it there (DISC-01, PART-07); a "
        "fill with nothing behind it is the decorative rationale PART-07 forbids"
    )


def _recovered_parents(entry: MappedThread) -> frozenset[str]:
    """The ids in a sibling thread that an L4 probe actually returned.

    Read off the plan's own hit set, which for a sibling thread is what the `rfc822msgid:`
    probe put there. A row that merely shares the recovered parent's thread is an ordinary
    thread-map stub and says so, because `reply parent of <child>` is a claim about one
    message and copying it onto the rest of the thread would be the decorative reason
    PART-07 forbids wearing a mechanical shape.
    """
    return frozenset(entry.plan.hit_ids)


#: The `WithheldCap` values a *budget* produces, as opposed to a width cap of the pool's
#: own. Derived from the accountant's own table so a cap added to the budget layer is
#: handled here the day it exists rather than falling through to a pool-widening call that
#: could not recover it.
_BUDGET_WITHHELD_CAPS: Final[frozenset[WithheldCap]] = frozenset(WITHHELD_CAP_OF.values())


def _semantic_cost(semantic: SemanticRun | None, ranking: RankingRun | None) -> SemanticCost | None:
    """AD D.5's cost disclosure, or `None` when no semantic rung ran.

    **The block the reviewer's second finding was about.** Two responses over one mailbox,
    with byte-identical rows and opposite source order, were indistinguishable on the wire:
    every row was a `q` match so D.7 suppressed every score, and nothing else said a
    cross-encoder had been involved. `rerank_pairs` and `ordering_method` are what say it now,
    and they say it without a score on any row - which is the combination D.5's "Cost
    disclosure" paragraph and D.7's "no numeric score on a `q`-selected row" together require.
    """
    if semantic is None or semantic.state is not SemanticState.RAN:
        return None
    build = semantic.build
    rerank = None if ranking is None else ranking.rerank
    model = None
    if rerank is not None and rerank.failed is None:
        model = f"{rerank.model_id}@{rerank.model_revision}"
    elif semantic.model_id is not None:
        model = f"{semantic.model_id}@{semantic.model_revision}"
    return SemanticCost(
        escalated=True,
        embed_texts=0 if build is None else len(build.rows),
        rerank_pairs=0 if rerank is None or rerank.failed is not None else rerank.pairs,
        semantic_ms=semantic.semantic_ms + (0 if ranking is None else ranking.ms),
        cold_load_ms=semantic.cold_load_ms,
        model=model,
        ordering_method=(MECHANICAL_METHOD if ranking is None else ranking.ordering_method),
    )


def _shortlisted_ids(semantic: SemanticRun | None) -> frozenset[str]:
    """The ids the shortlist selected: evidence from the retriever, whatever listed them."""
    if semantic is None or semantic.result is None:
        return frozenset()
    return frozenset(semantic.result.selected_ids)


def _semantic_order(semantic: SemanticRun | None) -> tuple[str, ...]:
    """The shortlist's threads, best first, each named once.

    A thread carrying two shortlisted messages takes the rank of its best one, which is the
    only rule that makes the order a function of the scores rather than of which of a
    thread's rows happened to be visited first.
    """
    if semantic is None or semantic.result is None:
        return ()
    order: list[str] = []
    for row in semantic.result.selected:
        if row.thread_id not in order:
            order.append(row.thread_id)
    return tuple(order)


def _split_off_unselected_pool_threads(
    plans: Sequence[ThreadPlan], semantic: SemanticRun | None
) -> tuple[tuple[ThreadPlan, ...], tuple[ThreadPlan, ...]]:
    """Separate the threads only an L5 probe found and the shortlist did not select.

    A thread whose earliest admitting rung is L5 is one *no lexical rung reached*: it is in
    `H` because a pool probe listed it, and nothing else. If the shortlist selected one of
    its messages it is evidence and is mapped like any other hit-bearing thread; if it did
    not, it is pool membership and nothing more.

    Threads L0-L3 also found stay on the left whatever the shortlist thought of them: they
    are lexical hits, and the semantic rung does not get to un-find them.
    """
    if semantic is None or semantic.result is None:
        # No semantic run, or one that produced no shortlist: there is nothing to select
        # *with*, so nothing is un-selected. A rung that declined must not silently shrink
        # a response the lexical ladder produced.
        return tuple(plans), ()
    selected = _semantic_order(semantic)
    keep: list[ThreadPlan] = []
    drop: list[ThreadPlan] = []
    for plan in plans:
        if plan.rung is RungId.L5 and plan.thread_id not in selected:
            drop.append(plan)
        else:
            keep.append(plan)
    return tuple(keep), tuple(drop)


def _why_the_shortlist_passed_over(semantic: SemanticRun | None) -> str:
    """The sentence a shortlist exclusion carries: the counts, not the cap's own name."""
    if semantic is None or semantic.result is None:  # pragma: no cover - guarded by the caller
        return "the semantic shortlist did not select any message in this thread"
    result = semantic.result
    return (
        f"{len(result.scored)} pool rows scored; the shortlist selected {result.size} at "
        f"k=max_rerank_pairs={result.k} and no message in this thread was among them"
    )


def _recency_plans(
    recency: RecencyRun | None, *, already: Collection[str]
) -> tuple[ThreadPlan, ...]:
    """One `ThreadPlan` per thread LR surfaced a message in, excluding threads already planned.

    A thread the lexical ladder or the pool already reached keeps the rung that reached it:
    `ThreadPlan.rung` is what the response reports as the route the evidence came out of,
    and a thread L1 matched does not become an LR thread because a later message arrived in
    it. The LR row inside it still carries its own `role: context` and its own reason.
    """
    if recency is None or not recency.surfaced:
        return ()
    seen = set(already)
    plans: list[ThreadPlan] = []
    for row in recency.surfaced:
        if row.thread_id in seen:
            continue
        seen.add(row.thread_id)
        plans.append(
            ThreadPlan(
                thread_id=row.thread_id,
                rung=RungId.LR,
                hit_ids=frozenset(
                    other.id for other in recency.surfaced if other.thread_id == row.thread_id
                ),
            )
        )
    return tuple(plans)


def _lr_not_tried(recency: RecencyRun | None, *, query: str) -> tuple[NotTriedEntry, ...]:
    """LR's `not_tried[]` entry, or nothing when the rung ran (a re-baseline is a run)."""
    if recency is None:
        return ()
    entry = recency.entry(query=query)
    return () if entry is None else (entry,)


def _l6_not_tried(ranking: RankingRun | None, *, query: str) -> tuple[NotTriedEntry, ...]:
    """L6's `not_tried[]` entry, or nothing when a tier of it ran.

    `mechanical_only` is a rung that ran: D.7's first tier *is* L6, and the response's
    ordering is `mailweave/mechanical-v1`. See `RankingRun.entry`.
    """
    if ranking is None:
        return ()
    entry = ranking.entry(query=query)
    return () if entry is None else (entry,)


def _pool_caps(semantic: SemanticRun | None) -> dict[str, str]:
    """`{thread id: cap name}` for every pool candidate the pool itself did not read."""
    if semantic is None or semantic.build is None:
        return {}
    return dict(semantic.build.capped_by)


def _pool_cap_note(
    thread_id: str, cap_name: str, semantic: SemanticRun
) -> tuple[WithheldCap, str, Affordance]:
    """One `withheld` record's cap, sentence and recovering call, for a pool exclusion.

    The sentence states the two counts that make the cap checkable - how many threads the
    pool had in front of it and how many it read - rather than restating the cap's name,
    which the record already carries. `build` and `plan` are non-`None` by construction: the
    only source of `capped_by` entries is a build, and a build has its plan.
    """
    cap = WithheldCap(cap_name)
    build = semantic.build
    plan = semantic.plan
    assert build is not None and plan is not None  # a cap entry implies the build that made it
    why = (
        f"{len(build.candidates)} threads in the semantic candidate pool; "
        f"{len(build.threads_read)} read at max_pool_threads={plan.max_threads} "
        f"and max_pool_messages={plan.max_messages}"
    )
    if cap is WithheldCap.PARTIAL_SOURCE_FAILURE:
        # The thread's own fetch failed; widening the pool would not help and a thread map
        # is the call that retries it (D.11 `partial_source_failure`).
        return (cap, f"{why}; this thread's own fetch failed", thread_map_affordance(thread_id))
    if cap in _BUDGET_WITHHELD_CAPS:
        # A budget stopped the pool rather than the pool's own width: the remedy is the
        # accountant's raise-this-cap call, not a wider pool.
        breach = semantic.breach
        assert breach is not None  # a budget cap entry is only written from a breach
        return (cap, f"{why}; {breach.rendered()}", breach.affordance)
    # **A thread map, not a wider pool** (AD-03, R-MCP-025's lesson). The first version minted
    # `pool: {max_threads: <double>}` and `SemanticProfile.narrowed` only *lowers*, so at the
    # declared bound the call was clamped straight back and the same id came back withheld
    # under the same cap: an affordance that cannot execute, which is the I-2
    # proof-of-violation shape this project has now produced twice. `pool{}` remains a real
    # argument for a caller who wants a *narrower* pool; it is not a way out of this cap,
    # because there is no way out upward - the bound is what PF-4 measured. The call that
    # actually reaches this thread's content is its map, which is exactly what round 29's
    # granularity rule says a thread-level withholding should carry.
    return (cap, why, thread_map_affordance(thread_id))


def _l5_not_tried(
    semantic: SemanticRun | None, *, query: str, admitted: bool = False
) -> tuple[NotTriedEntry, ...]:
    """L5's `not_tried[]` entry, or nothing when the rung ran.

    **`semantic is None` produces nothing at all, and that is deliberate.** A caller that
    reached `assemble` without a semantic runner - every unit test of the lexical ladder, and
    the `thread_map` / `get_messages` tools - has no account of L5 to give, and inventing one
    would be the claim wider than the code that `_ladder_account`'s docstring already refuses
    for the rungs this build does not have. `outcome_of` then declines `not_found` on the
    "a rung with no account at all" clause, which is the honest answer.
    """
    if semantic is None or semantic.state is SemanticState.RAN:
        return ()
    if admitted:
        # **Ran, and then failed** (R-M2-113). Its probes are in `H` and `_rungs_run` names it,
        # so a `not_tried` entry beside that would have the response claim one rung both ran
        # and was never tried. The reason does not disappear with the entry: an embedding
        # failure travels as an in-band `errors[]` entry (`semantic_unavailable`, D.11's
        # in-band half) and a pool budget breach travels as its own named cap in
        # `budget_caps_hit`, which is where it already travelled.
        return ()
    why = semantic.not_tried_why
    if why is None:  # pragma: no cover - `RAN` is the only state with no reason
        return ()
    entry = NotTriedEntry(
        rung=RungId.L5.value, why=why, affordance=semantic.affordance(query=query)
    )
    return (entry,)


#: The caps a tail recovery is filed for: the caps whose groups may fold past the naming
#: bound. One constant, read where the layout is seeded and where the ledger is told.
TAIL_RECOVERY_CAPS: Final[frozenset[WithheldCap]] = frozenset({WithheldCap.MAX_HIT_THREADS})


def _undisclosed_caps(
    run: LadderRun,
    *,
    ledger: DispositionLedger,
    plans: Sequence[ThreadPlan],
    mapped: Sequence[ThreadPlan],
    overflow: Sequence[ThreadPlan],
    max_hit_threads: int,
    unmapped_by_budget: Sequence[ThreadPlan],
    map_breach: CapBreach | None,
    siblings: Sequence[str],
    within_cap: Sequence[str],
    beyond_cap: Sequence[str],
    max_source_threads: int,
    recency: RecencyRun | None,
    unselected: Sequence[ThreadPlan],
    semantic: SemanticRun | None,
) -> dict[str, tuple[WithheldCap, str, Affordance]]:
    """`{thread id: (cap, why, recovering call)}` for every thread this response will not
    disclose as a source - decided once, before the ladder, for the estimate and the filing.

    **Precedence, and why it is the reverse of what it was** (R-M2-094). The table used to be
    written after the ladder with the pool's caps last, "because they are the more specific
    claim", and a later entry overwrote an earlier one. A thread beyond `max_hit_threads` that
    the pool had also listed but never read therefore lost its width cap - the cap that
    actually stopped it, whose groups fold - for a pool cap that never folds; on a wide
    recency window forty-five of a response's fifty groups were written that way and the
    response was refused at the host cap. The pool's caps are now the *fallback*: they apply
    to a thread only the pool's probes listed. A thread the ladder found and a width or budget
    cap stopped keeps that cap. A thread that was mapped is never here at all - it is a source,
    or step 7 split it off and filed it - so a pool note can no longer overwrite the ladder's
    own disposition of it.
    """
    caps: dict[str, tuple[WithheldCap, str, Affordance]] = {}
    was_mapped = frozenset(plan.thread_id for plan in mapped)
    # The pool's two classes first, so that anything below overrides them.
    for plan in unselected:
        caps[plan.thread_id] = (
            WithheldCap.MAX_RERANK_PAIRS,
            _why_the_shortlist_passed_over(semantic),
            thread_map_affordance(plan.thread_id),
        )
    if semantic is not None:
        for thread_id, cap_name in _pool_caps(semantic).items():
            caps[thread_id] = _pool_cap_note(thread_id, cap_name, semantic)
    for message_id in () if recency is None else recency.beyond_cap:
        thread = ledger.origins[message_id].thread_id
        if thread is None:
            continue
        caps[thread] = (
            WithheldCap.MAX_RECENCY_FETCH,
            (
                f"history.list reported more recent arrivals than max_recency_fetch="
                f"{MAX_RECENCY_FETCH} allows this query to fetch"
            ),
            recency_widening(run.parsed.raw, fetches=MAX_RECENCY_FETCH * 2),
        )
    for message_id in () if recency is None else recency.contradicted:
        thread = ledger.origins[message_id].thread_id
        if thread is None:
            continue
        caps[thread] = (
            WithheldCap.RECENCY_RECHECK_EXCLUDED,
            (
                "a recent arrival whose local re-check contradicted a constraint this query "
                "stated; it is not attributed to the query and is not disclosed"
            ),
            Affordance(
                tool=ToolName.GET_MESSAGES,
                args={"message_ids": [message_id], "view": Depth.SNIPPET.value},
            ),
        )
    for thread_id in beyond_cap:
        caps[thread_id] = (
            WithheldCap.MAX_SOURCE_THREADS,
            f"{len(siblings)} threads recovered by structural expansion; "
            f"{len(within_cap)} mapped at max_source_threads={max_source_threads}",
            thread_map_affordance(thread_id),
        )
    for plan in overflow:
        caps[plan.thread_id] = (
            WithheldCap.MAX_HIT_THREADS,
            f"{len(plans)} hit-bearing threads; {len(mapped)} mapped at "
            f"max_hit_threads={max_hit_threads}",
            thread_map_affordance(plan.thread_id),
        )
    for plan in unmapped_by_budget:
        assert map_breach is not None
        caps[plan.thread_id] = (
            map_breach.withheld_cap,
            f"{map_breach.rendered()}; this thread's map was not fetched",
            map_breach.affordance,
        )
    for thread_id in was_mapped:
        # A mapped thread is a source or a split-off source; the ladder accounts for it.
        # `unmapped_by_budget` threads are in `mapped` too and are the one exception: their
        # map was never fetched, so nothing else accounts for them.
        if thread_id not in {plan.thread_id for plan in unmapped_by_budget}:
            caps.pop(thread_id, None)
    return caps


def _withhold_undisclosed_threads(
    ledger: DispositionLedger,
    *,
    disclosed_threads: Collection[str],
    cap_of: Mapping[str, tuple[WithheldCap, str, Affordance]],
) -> None:
    """File a cap note for every observed id whose thread this response does not disclose.

    **Written as a sweep over the ledger rather than as a loop over the caps**, and that is
    the whole reason it exists. Round 19's assembly withheld `plan.hit_ids` for a capped
    thread, which was every id in that thread while `messages.list` was the only thing
    putting ids there. L4 puts ids in threads by a second route, so a cap that enumerates
    what *it* knows about now under-counts by exactly the ids the newer route contributed -
    and `DispositionLedger.certify` would refuse the response, loudly, which is the design
    working. This asks the ledger what it observed instead, so a third route inherits the
    disposition without editing this function.
    """
    for message_id, origin in sorted(ledger.origins.items()):
        thread_id = origin.thread_id
        if thread_id is None or thread_id in disclosed_threads:
            continue
        note = cap_of.get(thread_id)
        if note is None:
            continue
        cap, why, affordance = note
        ledger.note_withheld(
            message_id=message_id,
            cap=cap,
            why=why,
            affordance=affordance,
            # **Round 29.** Read off the affordance, not off the cap: this sweep files notes
            # for width caps, which offer a thread map, and for budget and clock caps, which
            # offer a wider search. Only the first is a thread-granular remedy, and grouping
            # the second would attach a count to a call that cannot use one.
            granularity=WithheldGranularity.of(affordance.tool),
        )


def _mailbox_watermark(
    client: GmailClient, minter: HandleMinter | None, accountant: BudgetAccountant | None
) -> str | None:
    """The mailbox `historyId` every handle this response mints walks from (amendment A10).

    **Read here, at the top of `assemble`, and that position is the correctness argument.**
    A watermark is safe exactly when it was observed no later than the reads it covers: a
    change to a named thread after its `threads.get` then necessarily carries an id above
    it, so the liveness walk sees it. Observed *after* the fetches - which is what
    `max(thread_history_ids)` amounts to - it can sit above a change that happened between
    a thread's read and the observation, and that change is invisible to the walk and
    absent from the map. So this call goes before `_fetch_and_map`, and
    `test_the_mailbox_watermark_is_observed_before_the_first_thread_is_fetched` reads the
    transport's own call log rather than this docstring.

    One `users.getProfile`, 1 quota unit, and **only when a minter exists**: a response that
    cannot mint handles does not pay for the watermark they would have walked from.

    **It is charged like every other call.** A budget already exhausted before the maps buys
    no watermark, and then no handle: a `map_id` whose walk could not be bounded is worse
    than no `map_id`, and spending the query's last unit on a field the response then cannot
    honestly fill is the shape A.7's caps exist to stop. This is the fourth place the
    accountant is consulted, and it is consulted the same way as the other three.

    `None` when the profile states no `historyId`, and then no source carries a `map_id`.
    That is the same rule `_map_id_for` already applied to a thread with no `historyId`, for
    the same reason: a handle whose walk cannot be bounded is a handle that answers
    `handle_stale_unverifiable` for ever, and `Source.map_id` is a claim rather than a
    field that must be filled. Falling back to the per-thread minimum would keep the field
    populated by restoring exactly the unbounded walk A10 removed, silently.
    """
    if minter is None:
        return None
    if accountant is not None and accountant.check((GmailEndpoint.GET_PROFILE,)) is not None:
        return None
    return client.get_profile().history_id


def _map_id_for(
    entry: MappedThread,
    structure: ThreadMap,
    minter: HandleMinter | None,
    mailbox_history_id: str | None,
    *,
    page_size: int,
) -> str | None:
    """This source's redeemable handle, or `None` when one cannot honestly be minted (WS-06).

    Three ways it is `None`, and they are different facts that happen to have one value:
    this server was called without a handle key (no `minter`); the `threads.get` that
    produced this map stated no `historyId`; or `users.getProfile` stated no mailbox
    watermark for the walk to start from. All three are the same sentence at different
    depths - a handle's liveness probe walks `history.list` from a watermark and floors each
    thread at its own `historyId`, so a handle missing either could never be verified
    against anything, and would redeem by saying `handle_stale_unverifiable` every time.
    `Source.map_id` is a claim, and the honest value for a map nothing can re-verify is no
    claim at all.
    """
    history_id = entry.recorded.thread.history_id
    if minter is None or history_id is None or mailbox_history_id is None:
        return None
    return minter.for_one_thread(
        thread_id=structure.thread_id,
        history_id=history_id,
        mailbox_history_id=mailbox_history_id,
        fetched_at=entry.recorded.fetched_at,
        digest=mapping_digest([structure]),
        page_size=page_size,
    )


def _ladder_account(
    run: LadderRun,
    plan: StructuralPlan,
    not_tried: Sequence[NotTriedEntry],
    sent: int,
    semantic: SemanticRun | None = None,
    recency: RecencyRun | None = None,
    ranking: RankingRun | None = None,
    semantic_admitted: bool = False,
) -> LadderAccount:
    """One `RungAccount` per rung the response has an account of, and no rung twice.

    Built from what the run and the structural plan recorded, and from the `not_tried`
    entries the response is actually shipping, so the account and the wire cannot disagree
    about a rung's state. A rung this build does not have is **absent** rather than present
    with an invented reason, which is what makes `LadderAccount.covers(LADDER)` false and
    `outcome_of` decline `not_found`.

    **L5 is present exactly when a semantic runner was passed**, which is the honest reading
    of "this response has an account of that rung": a caller that ran no semantic rung has
    nothing to say about it, and saying `not_applicable` on its behalf would be the invented
    reason this docstring refuses. L6 and LR are still absent for every caller.
    """
    by_reason = {entry.rung: entry for entry in not_tried}
    accounts: list[RungAccount] = []
    for rung in PUBLISHED_LADDER:
        entry = by_reason.get(rung.value)
        if entry is not None:
            accounts.append(
                RungAccount(
                    rung=rung,
                    state=(
                        RungState.NOT_APPLICABLE
                        if entry.why is NotTriedWhy.NOT_APPLICABLE
                        else RungState.BLOCKED
                    ),
                    why=entry.why,
                    affordance=entry.affordance,
                )
            )
        elif rung in _rungs_run(run, plan, sent, semantic, recency, ranking, semantic_admitted):
            accounts.append(RungAccount(rung=rung, state=RungState.RAN))
    return LadderAccount(accounts=tuple(accounts))


def _ids_in_threads(ledger: DispositionLedger, threads: Collection[str]) -> frozenset[str]:
    """Every observed id sitting in one of `threads`, read off the ledger.

    The same sweep-the-ledger rule `_withhold_undisclosed_threads` runs on, and for the same
    reason: a cap that enumerates what it knows about under-counts by exactly the ids a newer
    retrieval route contributed. Asking the ledger keeps the charge and the records built from
    the same enumeration.
    """
    return frozenset(
        message_id
        for message_id, origin in ledger.origins.items()
        if origin.thread_id is not None and origin.thread_id in threads
    )


def _widest_accounted_thread_id(ledger: DispositionLedger) -> int:
    """The longest thread id any accounted message sits in, in characters.

    `HitOrigin.thread_id` is what `envelope.withheld` charges a record's thread against, so
    the estimate reads the width from the same field rather than from a second source that
    could disagree with it. An origin with no thread contributes nothing, which is right: a
    record for it names no thread either.
    """
    return max(
        (len(origin.thread_id) for origin in ledger.origins.values() if origin.thread_id),
        default=0,
    )


def assemble(
    run: LadderRun,
    *,
    client: GmailClient,
    ledger: DispositionLedger,
    max_hit_threads: int = MAX_HIT_THREADS,
    max_source_threads: int = MAX_SOURCE_THREADS,
    minter: HandleMinter | None = None,
    accountant: BudgetAccountant | None = None,
    extra_errors: Sequence[ErrorEntry] = (),
    evidence_view: Depth = Depth.BODY_CLEAN,
    structural_max_probes: int = MAX_STRUCTURAL_PROBES,
    ceilings: Ceilings | None = None,
    semantic: SemanticRun | None = None,
    registry: BackendRegistry | None = None,
    #: D.7's second tier. `False` is the H2 bypass arm: the cross-encoder is absent, the
    #: mechanical tier's ordering stands, and no pair is scored. Never `False` in production.
    cross_encoder: bool = True,
    clock_ms: Callable[[], float] | None = None,
    forced: Collection[RungId] = (),
    recency: RecencyRun | None = None,
    selector: Selector | None = None,
) -> Envelope:
    """Map the hit-bearing threads, expand structurally, build the rows, close the disposition.

    **The thread maps are fetched before the `asked_for` block is built**, in one pass whose
    results the row-building pass reads, and that ordering is load-bearing rather than
    incidental. `asked_for.enforced` is a statement about the routes the response's evidence
    came out of (R-RETR-020, see `_asked_for`), so it cannot be computed until it is known
    which hits will actually be disclosed - and a thread whose map disagrees with itself is
    withheld whole, so `plan.hit_ids` alone would over-state the disclosure and therefore
    over-state the enforcement. `client.get_thread` is called exactly once per thread either
    way: the map is carried from the first pass to the second rather than re-fetched (I-3).

    **L4 runs between the two passes** (WS-05). It has to: its probes are composed from the
    unresolved reply parents the maps found, and the sibling threads it recovers are sources
    of their own. `asked_for` is still computed from the *hit* threads alone - a sibling
    thread is not evidence the query's own routes produced, and crediting a route for it
    would be the R-RETR-024 over-claim arriving through a new door.

    **Every disposition is filed after L4, not before.** A thread capped away holds whatever
    ids the ledger observed in it, and L4 is a second route that puts ids in threads, so a
    cap note written before it ran would cover the ids one route contributed and miss the
    other's. `_withhold_undisclosed_threads` sweeps the ledger instead.
    """
    # Amendment A10: **before** the first `threads.get`, or the watermark can sit above a
    # change no walk will then see. See `_mailbox_watermark`.
    mailbox_history_id = _mailbox_watermark(client, minter, accountant)
    preferred = run.decomposition.intersection if run.decomposition is not None else frozenset()
    # **The shortlist's own order, carried into the mapping order** (AD D.5, §H-5). Without
    # it a 25-thread pool against `max_hit_threads = 12` would map twelve threads chosen by
    # thread id, and the entire output of the scored retriever would be cut alphabetically.
    # It ranks *within* L5 only - see `hit_threads` - so no lexical thread moves.
    # **A16: exhaustive accounting, separated from evidence protection.** An id the internal
    # step-(c) recency probe listed and nothing else reached - no lexical match, no
    # participant probe, no shortlist selection - is in `H`, is disposed of like any other id
    # and is disclosed if its thread is mapped, but it is not evidence: it anchors no E2
    # floor, takes no top-k protection, makes no thread a source on its own and does not
    # count as query evidence surviving. It entered because a ninety-day window returned it.
    # **Gated exactly where `_split_off_unselected_pool_threads` is gated** (review finding
    # F3): on `semantic.result`, not on the plan. A rung that sent its probes and produced no
    # shortlist must not silently shrink a response the lexical ladder produced, and demoting
    # while the split-off stands down would map the pool's own threads as sources carrying no
    # evidence at all.
    not_evidence = (
        frozenset()
        if semantic is None or semantic.result is None
        else pool_listed_only(
            ledger,
            shortlisted=_shortlisted_ids(semantic),
            queries=recency_probe_queries(semantic),
        )
    )
    plans = hit_threads(
        ledger,
        prefer=preferred,
        semantic_order=_semantic_order(semantic),
        not_evidence=not_evidence,
        # The same set `pool_listed_only` exempts, passed a second time because exemption
        # from the demotion is not membership of the tier: a shortlisted message the probe
        # never listed was never in `hit_ids` to begin with.
        selected=_shortlisted_ids(semantic),
    )
    # **A pool thread the shortlist did not select is not a source** (AD D.5, A.7a). Its ids
    # reached `H` because a step-(b) or step-(c) probe is a `messages.list` call like any
    # other - and that is the whole of what they are. Left in `plans` they would be mapped
    # like lexical hits, and a query with no lexical answer would return every thread in its
    # own ninety-day recency window as a full `source`: the pool creating sources, which is
    # the one thing D.5 says it must never do. They are withheld instead, under the
    # shortlist's own cap, each with the thread map that reaches it.
    plans, unselected = _split_off_unselected_pool_threads(plans, semantic)
    # **LR's surfaced messages arrive by a route `hit_threads` cannot see.** Their ids came
    # from `history.list`, which the ledger records under clause H-hist and under its own
    # `ObservedEndpoint`; `hit_threads` reads `messages.list` origins because that is what a
    # lexical hit *is*. So the threads LR surfaced are appended here, after the lexical and
    # semantic ones, which is also their priority: a message the query's own `q` matched
    # outranks one the index has not caught up with and which was only re-checked locally.
    plans = plans + _recency_plans(recency, already={plan.thread_id for plan in plans})
    mapped, overflow = plans[:max_hit_threads], plans[max_hit_threads:]

    # **The map stage under the budget, and this is where the mid-rung timeout contract is
    # visible in the response** (WS-10). The accountant is asked before each `threads.get`;
    # the maps already fetched are kept and disclosed, and every thread the budget stopped
    # us from mapping becomes a `withheld` record naming the cap, with the call that raises
    # it. Nothing observed is dropped, and the response says which cap cost it.
    # What L5 already fetched for its pool. A thread in here is not fetched again.
    pooled = {} if semantic is None else dict(semantic.observations)
    prepared: list[MappedThread] = []
    unmapped_by_budget: list[ThreadPlan] = []
    map_breach: CapBreach | None = None
    for plan in mapped:
        if map_breach is None and accountant is not None and plan.thread_id not in pooled:
            map_breach = accountant.check((GmailEndpoint.THREADS_GET,))
        if map_breach is not None:
            unmapped_by_budget.append(plan)
            continue
        prepared.append(
            _fetch_and_map(
                plan,
                client=client,
                ledger=ledger,
                run=run,
                observed=pooled.get(plan.thread_id),
            )
        )
    disclosed_hit_threads = frozenset(
        entry.plan.thread_id for entry in prepared if entry.unmappable is None
    )

    structural_plan, recovered, structural_breach, structural_sent = _execute_structural_expansion(
        prepared,
        run=run,
        client=client,
        ledger=ledger,
        accountant=accountant,
        cap=structural_max_probes,
    )
    map_breach = map_breach or structural_breach
    already = {plan.thread_id for plan in plans}
    siblings = [thread_id for thread_id in recovered if thread_id not in already]
    within_cap, beyond_cap = siblings[:max_source_threads], siblings[max_source_threads:]
    origins = ledger.origins
    prepared += [
        _fetch_and_map(
            ThreadPlan(
                thread_id=thread_id,
                rung=RungId.L4,
                hit_ids=frozenset(
                    message_id
                    for message_id, origin in origins.items()
                    if origin.thread_id == thread_id and origin.rung is RungId.L4
                ),
            ),
            client=client,
            ledger=ledger,
            run=run,
            recovered=recovered[thread_id],
        )
        for thread_id in within_cap
    ]

    # **Clause H-sem, filed before anything is disclosed.** `record_shortlist` refuses an id
    # no executed retrieval admitted, which is what makes "the shortlist is a selection out
    # of `H`, never an intake into it" a property of the code rather than of this comment.
    if semantic is not None and semantic.result is not None:
        ledger.record_shortlist(
            ids=sorted(semantic.result.selected_ids),
            rule=semantic.result.rule,
            k=semantic.result.k,
        )

    asked_for = _asked_for(run, disclosed_threads=disclosed_hit_threads)
    builder = EnvelopeBuilder(
        ledger,
        asked_for=asked_for,
        ceiling=_declared_ceiling(
            ceilings.normal if ceilings is not None else NORMAL_CEILING_TOKENS
        ),
    )

    mappable: list[MappedThread] = []
    unmappable_threads = 0
    for entry in prepared:
        plan = entry.plan
        if entry.unmappable is not None:
            _withhold_the_whole_thread(ledger, plan, entry.recorded)
            builder.add_not_included_source(
                NotIncludedSource(
                    thread_id=plan.thread_id,
                    stated_total=_total_this_thread_can_state(ledger, plan, entry.recorded),
                    affordance=thread_map_affordance(plan.thread_id),
                ),
                why=entry.unmappable,
            )
            builder.add_affordance(thread_map_affordance(plan.thread_id))
            unmappable_threads += 1
            continue
        mappable.append(entry)

    # **L6, over the threads that will actually be disclosed** (AD D.7). The mechanical tier
    # runs whatever happens and orders every candidate; the cross-encoder runs only if an
    # ambiguity signal fires and only over the shortlist L5 already selected. It is here
    # rather than before the maps because D.7 ranks *disclosed candidates*, and half the
    # mechanical components - a thread's own participants, its newest message's date - are
    # facts of the map.
    ranking = rank_candidates(
        run,
        candidates=[_candidate_of(entry, run=run) for entry in mappable],
        semantic=semantic,
        registry=REGISTRY if registry is None else registry,
        clock_ms=clock_ms if clock_ms is not None else _monotonic_ms,
        thread_count=len(mappable),
        forced=RungId.L6 in forced,
        accountant=accountant,
        cross_encoder=cross_encoder,
    )
    # The ordering the ranking produced, applied to the list the disclosure layer ranks by.
    # `_thread_input(..., rank=...)` is what carries it into A.9's fill, so ordering here is
    # what makes the ranking visible rather than decorative.
    position_of = {key: index for index, key in enumerate(ranking.order)}
    mappable.sort(key=lambda entry: position_of.get(entry.plan.thread_id, len(position_of)))
    # **One rank scale for everything the wire orders** (R-M2-096): the sources in the order
    # the ranking put them - which is the `rank` each `PlannedSource` carries into A.9a - and
    # after them the hit-bearing threads `max_hit_threads` left unmapped, in the order the
    # ladder held them. Read by the ledger when it writes the groups and by the split-off
    # entries; a thread absent here was never ranked and is written after every ranked one.
    rank_of: dict[str, int] = {entry.plan.thread_id: index for index, entry in enumerate(mappable)}
    for offset, plan in enumerate(overflow):
        rank_of.setdefault(plan.thread_id, len(mappable) + offset)

    # **The threads the wire will account for a thread at a time, known before the ladder
    # runs** (round 29). `max_hit_threads` and `max_source_threads` are the two width caps
    # whose remedy is a thread map, so they are the two whose withholdings become groups;
    # `_withhold_undisclosed_threads` files those notes later, from the same affordance.
    #
    # Deliberately **not** here: threads unmapped by a budget or clock cap, whose remedy is a
    # wider search, and threads whose own map contradicted itself, whose remedy is a
    # per-message read. Both keep a record each. Seeding either would make the estimate
    # cheaper than the response it is estimating, which is the one direction it may never err
    # in - an over-estimate declines something that would have fitted, an under-estimate hands
    # a host more than it accepts.
    # **One cap table, built once, read by the estimate and by the filing** (R-M2-094,
    # 2026-09-15). Every thread this response will not disclose is assigned the cap that
    # stopped it here, before the ladder runs; the layout is seeded with exactly the
    # `(thread, cap)` groups that table implies, and `_withhold_undisclosed_threads` files the
    # notes from the same table after the ladder. There is no second arithmetic: the estimate
    # asks `envelope.grouping.arrange_groups` how many of these groups the wire will name and
    # fold, and the ledger asks the same function when it writes them.
    cap_of = _undisclosed_caps(
        run,
        ledger=ledger,
        plans=plans,
        mapped=mapped,
        overflow=overflow,
        max_hit_threads=max_hit_threads,
        unmapped_by_budget=unmapped_by_budget,
        map_breach=map_breach,
        siblings=siblings,
        within_cap=within_cap,
        beyond_cap=beyond_cap,
        max_source_threads=max_source_threads,
        recency=recency,
        unselected=unselected,
        semantic=semantic,
    )
    groups = frozenset(
        (thread_id, cap)
        for thread_id, (cap, _why, affordance) in cap_of.items()
        if WithheldGranularity.of(affordance.tool) is WithheldGranularity.THREAD
    )
    thread_granular = frozenset(thread_id for thread_id, _cap in groups)
    # **The records that carry the query** (round 29, R-V01-013(a)): every message in a thread
    # a budget or clock cap stopped the server mapping is filed with the caller's own search
    # at a raised cap as its affordance, and that call renders the query once per record.
    # Seeded here so the ladder charges it; the notes themselves are filed later from the
    # same `caps` table, by `_withhold_undisclosed_threads`.
    query_bearing = _ids_in_threads(
        ledger, frozenset(plan.thread_id for plan in unmapped_by_budget)
    )
    # **Did L5's probes admit anything?** (R-M2-113). Read off the ledger, which is the same
    # enumeration the envelope's validator reads, so the two cannot disagree about whether the
    # rung produced hits. This decides one thing only - whether the rung is reported as having
    # run - and touches no id, no disposition and no cap.
    semantic_admitted = ledger.hits_per_rung.get(RungId.L5, 0) > 0
    # `not_tried` is built here rather than at the end because its budget entries carry the
    # search that would run the rung - query included - and the estimate charges what the
    # wire will render (R-V01-013(a)). Everything it reads is settled before the ladder runs.
    not_tried = (
        _not_tried(run)
        + _l4_not_tried(
            structural_plan,
            len(structural_plan.probes),
            structural_breach,
            run=run,
            cap=structural_max_probes,
        )
        + _l5_not_tried(semantic, query=run.parsed.raw, admitted=semantic_admitted)
        + _l6_not_tried(ranking, query=run.parsed.raw)
        + _lr_not_tried(recency, query=run.parsed.raw)
    )
    # `add_affordance` lists a call once, so a breach shared by both stages is charged once.
    breach_affordances: tuple[Affordance, ...] = ()
    for breach in (map_breach, structural_breach):
        if breach is not None and breach.affordance not in breach_affordances:
            breach_affordances += (breach.affordance,)

    # **WS-11.** A.9's four tiers and A.9a's precedence, over the whole response at once,
    # because the ceiling is per response: a per-thread ladder would let two threads each
    # fit and the response not. The planner never fetches; it decides depth over what this
    # run already holds, which is what keeps disclosure off the escalation path (T-CD3).
    # The order `max_hit_threads` cut (`plans`), carried onto each mapped source so a refusal
    # can ask what a narrower width would have mapped (R-M2-095): a prefix of this order,
    # which the ranking's `rank` does not preserve.
    cut_index = {plan.thread_id: index for index, plan in enumerate(plans)}
    disclosure = disclose(
        [
            _thread_input(entry, run=run, rank=rank, mapped_at=cut_index.get(entry.plan.thread_id))
            for rank, entry in enumerate(mappable)
        ],
        query=_query_facts(run.parsed),
        # **The one thing that differs between the shipped arm and Baseline F** (DISC-02,
        # EP §8.8). `Selector` has existed since WS-11 and `FixedWindow` with it, so that the
        # equal-budget comparison is a property of construction; until now nothing could
        # actually hand the baseline in, which made the comparison unrunnable rather than
        # merely unrun. `None` is the shipped policy, which is what `mailweave serve` gets.
        selector=QueryAwareFill() if selector is None else selector,
        accounted_ids=frozenset(ledger.origins),
        evidence_view=evidence_view,
        ceilings=ceilings,
        # The `not_included_sources[]` entries already filed above, which never became layout
        # sources - so the ladder charges the block the envelope will actually emit.
        not_included_before=unmappable_threads,
        # Round 27, R-MCP-024: the widest thread a `withheld` record can name, read off the
        # ledger the records are built from rather than off the layout, which cannot see a
        # thread `max_hit_threads` capped away before the ladder ran.
        accounted_thread_id_chars=_widest_accounted_thread_id(ledger),
        # **Round 29, R-MCP-033.** The threads this response will account for a thread at a
        # time, seeded before the ladder runs: the ones `max_hit_threads` capped away and the
        # ones whose map disagreed with itself. Neither has a map, so neither can carry a
        # stub, and the estimate has to charge what the wire will emit - one counted group
        # each, not one record per observed message. This is what makes `max_hit_threads`
        # reduce the response instead of merely moving ids from disclosed to withheld.
        grouped_ids=_ids_in_threads(ledger, thread_granular),
        groups=groups,
        # The caps a tail recovery is filed for below, and so the only caps whose groups the
        # ledger folds: `max_hit_threads`, the one published width key. `max_source_threads`
        # is not caller-settable and the pool's caps have no widening call (AD-03), so their
        # groups are always named - and charged as named, which is the correction R-M2-094
        # is: the previous seeding counted the pool's groups as foldable and the wire named
        # every one of them.
        foldable_caps=TAIL_RECOVERY_CAPS,
        # The rank the ledger writes the groups by, so the estimate arranges them the same way.
        ranks=rank_of,
        # R-V01-004: the query's echoes, measured off the blocks that carry them.
        request_echo_chars=request_echo_chars(
            asked_for, ledger.scan_scope, not_tried, breach_affordances
        ),
        # Round 29: the tail's widening call carries the query twice, and each record in
        # `query_bearing_ids` once - at the query's JSON-escaped length, which is what renders.
        query_chars=json_string_chars(run.parsed.raw),
        query_bearing_ids=query_bearing,
    )
    by_thread = {entry.plan.thread_id: entry for entry in mappable}
    planned_by_thread = {entry.source.thread_id: entry for entry in disclosure.threads}

    sources: list[Source] = []
    for planned_source in disclosure.layout.sources:
        entry = by_thread[planned_source.thread_id]
        structure = entry.structure
        assert structure is not None  # `unmappable is None` is exactly `structure is not None`
        # **The rows the ladder left, not the rows the planner wanted** (round 25). `disclose`
        # returns the *pre-ladder* plan in `threads` and the *degraded* layout in `layout`;
        # reading depths and membership off the first meant every A.9a step was computed,
        # declared in `truncated_by`, and then discarded before the wire - so a thread that
        # reached step 5 emitted its collapsed members as rows as well, and `Source` refused
        # the response. `replace` carries the planner's floor and fill decisions (which the
        # ladder does not change) onto the source the ladder actually produced.
        planned = replace(planned_by_thread[planned_source.thread_id], source=planned_source)
        rows = _rows_of(
            entry,
            run=run,
            ledger=ledger,
            builder=builder,
            planned=planned,
            ranking=ranking,
            recency=recency,
            semantic=semantic,
        )
        width = _page_width_of(entry, planned_source.thread_id)
        runs = _collapsed_runs(planned_source, entry, width=width)
        here = _ceiling_withheld_here(entry, disclosure)
        source_ids = frozenset(row.id for row in rows)
        source = Source(
            thread_id=planned_source.thread_id,
            stated_total=len(entry.recorded.thread.messages),
            included=len(rows) + sum(run.count for run in runs),
            included_as_stub=sum(1 for row in rows if row.depth is Depth.STUB)
            + sum(run.count for run in runs),
            fetched_at=entry.recorded.fetched_at,
            messages=tuple(rows),
            collapsed_runs=runs,
            withheld_here=here,
            # **The index this response can still support, not the whole one** (round 26,
            # R-DISC-032). `Source` refuses a participant record citing a message this source
            # does not carry, so a step-8 withholding used to be a `ValidationError` waiting
            # to happen here; and the A.9a ladder now charges the participant block, which it
            # can only do honestly if it charges the same narrowing the wire will carry.
            # `participants_within` is that one rule, called here and by `PlannedSource.cost`.
            participants=participants_within(
                participants_block(
                    structure,
                    display_names=_display_names_of(entry.recorded.thread.messages),
                    builder=builder,
                ),
                source_ids,
            ),
            structure=structure_block(structure, rows=rows),
            map_id=_map_id_for(entry, structure, minter, mailbox_history_id, page_size=width),
        )
        sources.append(source)
        builder.add_source(source)
        for run_block in runs:
            builder.add_affordance(run_block.affordance)

    _record_ladder_dispositions(
        disclosure, ledger=ledger, builder=builder, by_thread=by_thread, rank_of=rank_of
    )
    builder.set_ceiling(_ceiling_of(disclosure))
    # **`truncated_by` is a claim that something was removed, so step 6 alone does not set
    # it.** Raising the declared ceiling for floor membership takes nothing out of the
    # payload, and `Envelope` refuses a truncation claim with no artifact of the ladder
    # behind it (DISC-06) - correctly, because a flag with nothing removed is a false
    # statement about what was done.
    if _the_ladder_removed_something(disclosure):
        builder.mark_self_truncated()

    disclosed_threads = frozenset(source.thread_id for source in sources)
    if unmapped_by_budget:
        assert map_breach is not None
        builder.add_affordance(map_breach.affordance)
    # **The tail's way out** (round 29, R-V01-007). A cap that folds groups past the naming
    # bound needs a call that widens it: the same search at the published width. Filed
    # before `certify` decides whether anything folds; a cap with no call filed never folds,
    # by the ledger's own rule - and the layout was seeded with the same set
    # (`foldable_caps=TAIL_RECOVERY_CAPS`), so the estimate charged the arrangement the
    # ledger now writes.
    for cap in TAIL_RECOVERY_CAPS:
        ledger.note_tail_recovery(
            cap,
            Affordance(
                tool=ToolName.SEARCH,
                args={"query": run.parsed.raw, "budget": {"max_hit_threads": MAX_HIT_THREADS}},
            ),
        )
    # **Retrieval rank on the wire** (R-M2-096): every thread the ladder held a rank for
    # tells the ledger, so the groups and the not-included entries are written best first;
    # a thread with no rank - one only the pool's probes listed - is written after every
    # ranked one, by thread id.
    for thread_id, rank in rank_of.items():
        ledger.note_rank(thread_id, rank)
    _withhold_undisclosed_threads(ledger, disclosed_threads=disclosed_threads, cap_of=cap_of)

    reading = client.meter.reading()
    disclosed = sum(len(source.messages) for source in sources)
    # **The affordances of a zero-evidence response, from whichever class it is in**
    # (ROUTE-01's fifth element; round 19, R-RETR-040). Round 18 minted them only for the
    # report class - the one where no rung ran at all - which is 11.3% of the zero-evidence
    # responses R-RETR measured. A response that ran the ladder, found nothing and named a
    # drop it did not try is the commoner class and it is the one a caller is stuck in.
    for offer in (
        (report_affordances(run.parsed) if not run.rungs_run else recovery_affordances(run))
        if not disclosed
        else ()
    ):
        builder.add_affordance(offer)
    # **The one expansion this response recommends** (round 28): the evidence rows the
    # ladder could not carry at the depth the caller asked for, by id. Emitted only when such
    # rows exist, and never for the thread around the evidence.
    expansion = recommended_expansion(
        sources, evidence_ids=run.evidence_ids, evidence_view=evidence_view
    )
    if expansion is not None:
        builder.add_affordance(expansion)
    # `answered` is a claim that the query was answered, so it needs three things, and
    # each one is a different way of being wrong without them.
    #
    #   * rows in the payload, and
    #   * evidence the *query* produced - a response carrying only the threads a broad L1b
    #     probe obliged the ledger to disclose has the first and not the second, and calling
    #     that answered is the confident-but-wrong shape I-4 is about;
    #   * a scan that was not declared incomplete (R-RETR-016). A run in which probes report
    #     `more_pages` has already said, in `scan_scope`, that pages it did not fetch may
    #     hold the answer - `partial` reads the same fact - so `answered` beside it is the
    #     response contradicting its own declaration. WS-10 owns `outcome` policy in full;
    #     this is the narrow case where the field is emitted this round and the run's own
    #     account already refutes it.
    truncated = any(entry.more_pages for entry in run.executed_probes)
    caps_hit: tuple[BudgetCapName, ...] = () if accountant is None else accountant.caps_hit
    if map_breach is not None and map_breach.cap not in caps_hit:
        caps_hit = (*caps_hit, map_breach.cap)
    # **A.9a names its own cap.** A response the disclosure ladder had to degrade says so in
    # `budget_caps_hit` as well as in `ceiling{}`, because a reader looking for "what cost me
    # content" reads the cap list, and the ladder is a cap like any other (A.9a, D.2).
    # **The semantic caps, which no other sweep can see.** L5's embed overrun and L6's
    # rerank overrun are wall-clock facts the accountant records only when it refuses a
    # *spend*, and neither rung spends a Gmail call at the moment it overruns. A reader
    # asking "what cost me content" would otherwise be told nothing about the six seconds.
    for named in (
        None if semantic is None else semantic.cap,
        None if ranking is None else ranking.cap,
    ):
        if named is not None and named not in caps_hit:
            caps_hit = (*caps_hit, named)
    if disclosure.steps and BudgetCapName.DISCLOSED_TOKEN_CEILING not in caps_hit:
        caps_hit = (*caps_hit, BudgetCapName.DISCLOSED_TOKEN_CEILING)
    # **And so does every width cap** (round 30, from the live v0.1 acceptance run). The
    # argument above is the whole argument, and it was applied to the ladder and not to the
    # two caps that withhold the most: the acceptance record shows `budget_caps_hit:
    # ["max_server_ms"]` beside `withheld_by_cap: {"max_hit_threads": 44, "max_server_ms":
    # 1}` - forty-four of forty-five messages withheld by a published budget key that the
    # cap list does not mention. A reader asking "what cost me content" was told about the
    # one message and not the forty-four.
    #
    # **Swept from `cap_of`, not enumerated a second time**, for the reason
    # `_withhold_undisclosed_threads` gives: `cap_of` is the one table the notes themselves are
    # filed from, so a cap that starts withholding threads through a new route inherits its
    # entry here without editing this function. `WithheldCap` and `BudgetCapName` share their
    # values where a cap is both; `partial_source_failure` is a source that failed rather
    # than a budget that ran out, and has no `BudgetCapName` - it is skipped, and the record
    # that names it still carries its own cap and its own executable call.
    for withheld_cap, _why, _affordance in cap_of.values():
        try:
            named = BudgetCapName(withheld_cap.value)
        except ValueError:
            continue
        if named not in caps_hit:
            caps_hit = (*caps_hit, named)
    if accountant is not None:
        builder.set_budget(accountant.budget.block)
    # **Declarations the surface knows and the ladder cannot** (WS-15). A caller can ask for
    # something this build does not contain - a semantic pool to bound, a rung whose runtime
    # was never written - and the honest place for that is an in-band `errors[]` entry on a
    # response that is otherwise complete, because the query still ran and its answer is
    # still true. They arrive as a parameter rather than being minted here for the reason
    # every other fact in this module arrives that way: `assemble` reports what a run did,
    # and what a caller *asked for* is not something a `LadderRun` records. `ErrorEntry`
    # refuses any code D.11 puts on the tool-error side, so this parameter cannot be used to
    # smuggle a refusal into a successful response.
    for declaration in extra_errors:
        builder.add_error(declaration)
    # **The reason an admitted-then-failed rung gives** (R-M2-113). `_l5_not_tried` stands down
    # for a rung whose probes are in `H`, so the failure needs the other half of D.11's
    # vocabulary: `semantic_unavailable` is already an in-band code, and this is the condition
    # it names. Only for `UNAVAILABLE` - a pool budget breach is `BLOCKED`, and its cap is
    # already named in `budget_caps_hit` through `semantic.cap`, so minting a second record of
    # it here would be the response reporting one event twice.
    if semantic is not None and semantic_admitted and semantic.state is SemanticState.UNAVAILABLE:
        builder.add_error(
            ErrorEntry(
                code=ErrorCode.SEMANTIC_UNAVAILABLE,
                scope=semantic.why,
                affordance=semantic.affordance(query=run.parsed.raw),
            )
        )
    # **OD-2's three-way outcome, computed by WS-10's one function.** The `account` is built
    # from what the run recorded rather than re-derived here, and `applicable` is the ladder
    # this build actually has: L5, L6 and LR are unbuilt, so `outcome_of` refuses
    # `not_found` on the "a rung with no account at all" clause and the response stays
    # `inconclusive` - which is the honest answer and is now a rule rather than an omission.
    envelope = builder.build(
        outcome=outcome_of(
            account=_ladder_account(
                run,
                structural_plan,
                not_tried,
                structural_sent,
                semantic,
                recency,
                ranking,
                semantic_admitted,
            ),
            disclosed=disclosed,
            evidence=run.evidence_count,
            hits=len(ledger.hit_ids),
            caps_hit=caps_hit,
            unfetched_pages=truncated,
        ),
        rungs=_rungs_run(
            run, structural_plan, structural_sent, semantic, recency, ranking, semantic_admitted
        ),
        sufficiency=_sufficiency(run, disclosed),
        counters=Counters(
            http_requests=reading.http_requests,
            api_calls=reading.api_calls,
            quota_units=reading.quota_units_diagnostic,
        ),
        not_tried=not_tried,
        budget_caps_hit=caps_hit,
        empty_diagnosis=_empty_diagnosis(run, disclosed=disclosed),
        pool=None if semantic is None else semantic.pool_block(),
        semantic_cost=_semantic_cost(semantic, ranking),
    )
    return envelope
