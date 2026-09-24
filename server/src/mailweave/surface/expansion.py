"""One disclosure path for the three tools that expand something already named.

`mailweave_thread_map`, `mailweave_get_messages` and `mailweave_get_attachment` differ in
exactly three things: which messages the caller named, what depth they asked for them at,
and whether attachment metadata is attached. Everything else - the map-carrier row set, the
positions, the reply structure, the participants, the provenance, the fence, the A.9a
degradation ladder, the ceiling, the disposition certificate - is one function, `expand`.

**That is this round's answer to "one shape validated, peers trusted".** Three tools sharing
one builder means a property proved of the builder is proved of all three, and a fourth
expansion tool would inherit it rather than needing its own defence. The tools that follow
`expand` are thin enough to read in one sitting, and the tests assert the shared properties
over the whole tool population rather than over one tool at a time.

**Nothing here decides a depth on its own.** `disclosure.depth_for` answers "what depth can
the text this response holds support", and `disclosure.run_ladder` answers "what fits the
ceiling" - both are WS-11's, imported rather than restated, so an expansion response and a
search response shrink by the same published precedence and are measured by the same
estimate. A second ceiling arithmetic here would be host truncation arriving from inside,
which is exactly what DISC-06 forbids.

**And nothing here is disclosed that the response did not observe.** A thread served warm
from WS-06's LRU carries a map and no `threads.get` rows, so its provenance is
*unobserved* and its rows have no snippet - not because the disclosure is careless, but
because "this response holds no labels for this row" and "Gmail says this row carries no
labels" are different statements and only the first one is true (R-RETR-039).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from mailweave.constants import HOST_RESULT_CHAR_CAP, NORMAL_CEILING_TOKENS
from mailweave.content.pipeline import ProcessedMessage
from mailweave.disclosure import (
    Band,
    Ceilings,
    DisclosureLadderExhausted,
    LadderStep,
    Layout,
    PlannedRow,
    PlannedRun,
    PlannedSource,
    depth_for,
    run_ladder,
    segment_of,
)
from mailweave.disclosure.ladder import HOST_CAP_WHY, over_budget
from mailweave.disclosure.layout import a_ceiling_bound
from mailweave.disclosure.pages import next_page, page_of, page_size, pages_of
from mailweave.envelope.builder import EnvelopeBuilder
from mailweave.envelope.disposition import DispositionLedger
from mailweave.envelope.measure import (
    affordance_echo_chars,
    continuation_chars,
    rendered_chars,
    request_echo_chars,
)
from mailweave.envelope.reasons import Reason, RequestedById, RungId, ThreadMember
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import (
    BudgetCapName,
    ContentSource,
    Depth,
    Outcome,
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
    AttachmentMetadata,
    Ceiling,
    CollapsedRun,
    Continuation,
    Counters,
    ErrorEntry,
    MailboxProvenance,
    MessageRow,
    NotIncludedSource,
    ParsedQuerySummary,
    Source,
    ThreadParticipant,
    participants_within,
)
from mailweave.errors import DispositionInvariantError
from mailweave.gmail.models import Message
from mailweave.handles.digest import mapping_digest
from mailweave.handles.mint import HandleMinter
from mailweave.retrieval.assemble import (
    _attribution_of,
    _auth_record_of,
    _authentication_of,
    _display_names_of,
    _reply_to_differs,
    participants_block,
    structure_block,
    thread_map_affordance,
    unabridged_affordance,
)
from mailweave.structure.threadmap import ThreadMap, from_header_of
from mailweave.surface.arguments import ArgumentInvalid
from mailweave.surface.rendering import render

#: The rung an expansion records its reads under. `L4` is the structural rung: an expansion
#: is a structural retrieval - the caller named a thread or a message and this call fetches
#: the structure around it - and inventing a sixth rung id for the surface would put a value
#: in `retrieval_report.rungs` that AD A.7's table does not contain.
EXPANSION_RUNG: RungId = RungId.L4


@dataclass(frozen=True)
class Observation:
    """One thread this call holds, however it came to hold it.

    `messages` is empty exactly when the thread came from WS-06's LRU rather than from a
    `threads.get` in this call, and every field that reads a `Message` degrades to its
    unobserved form in that case rather than being filled from somewhere else.
    """

    thread_id: str
    thread_map: ThreadMap
    fetched_at: str
    verified_at: str | None = None
    history_id: str | None = None
    messages: tuple[Message, ...] = ()

    @property
    def by_id(self) -> Mapping[str, Message]:
        return {message.id: message for message in self.messages}


@dataclass(frozen=True)
class Wanted:
    """What the caller named, and how deep. The only per-tool input `expand` takes."""

    #: Message ids the caller named. Everything else in the thread is inventory: compact
    #: runs pointing at pages of the map (navigation redesign, 2026-09-14).
    named: frozenset[str] = frozenset()
    #: The depth the named messages are asked for. Unnamed rows are map rows.
    view: Depth = Depth.STUB
    #: The depth a map row gets on AD E.2's segment path, the one path that still plans map
    #: rows for the ladder. **`stub`, and it is not a knob**: a map row is a map row, and the
    #: text is one `mailweave_get_messages` call away, named on every row by its `unabridged`
    #: affordance. The page and read paths plan no map rows at all.
    map_view: Depth = Depth.STUB
    #: Attachment metadata to attach, per message id, already narrowed by the tool.
    attachments: Mapping[str, tuple[AttachmentMetadata, ...]] = field(default_factory=dict)
    #: Only this segment of a long thread is disclosed as rows, when a segment was asked for.
    segment: int | None = None
    #: The named ids **in the order the caller named them** (navigation redesign). `named` is
    #: the set; this is the order a batch is served in and the order its continuation keeps.
    order: tuple[str, ...] = ()
    #: Which page of a thread map to carry as rows. `None` on a read; `None` on a map means
    #: page 0. Mutually exclusive with `segment`, which is AD E.2's temporal experiment.
    page: int | None = None

    def ordered(self) -> tuple[str, ...]:
        """`named`, in request order where one was given, else sorted for determinism."""
        seen = [one for one in self.order if one in self.named]
        rest = sorted(self.named - frozenset(seen))
        return (*seen, *rest)


def _provenance(message: Message | None) -> MailboxProvenance:
    if message is None or message.label_ids is None:
        return MailboxProvenance.unobserved()
    return MailboxProvenance.of(message.label_ids)


def _snippet_of(message: Message | None) -> str | None:
    return None if message is None else (message.snippet or None)


def _plan_source(
    observation: Observation,
    wanted: Wanted,
    bodies: Mapping[str, ProcessedMessage],
    *,
    keep: frozenset[str] | None = None,
    page_size: int | None = None,
    inventory: bool = True,
) -> tuple[tuple[PlannedRow, ...], tuple[PlannedRun, ...]]:
    """The requested content as rows, and the rest of the thread as compact runs.

    **This is the whole of the read/map distinction from search** (navigation redesign,
    2026-09-14). A search plans every message of a hit thread as a row and lets the ladder
    degrade and collapse; an expansion has no evidence to select - the caller named it - so it
    plans only what was asked for as rows, `Band.REQUESTED`, and states the rest of the thread
    as runs from the start: positions, ids once, a page call each. Nothing here is for the
    ladder to collapse, so nothing the caller asked for can be collapsed.

    `keep` narrows the requested rows to the prefix the fit loop is trying; `None` keeps all.
    `page_size` is the thread's page width when this is a map page; a read points its runs at
    pages too, so it is computed for both. `inventory=False` plans the rows alone - a *scoped*
    read, whose thread did not fit beside them and is accounted for as records and a group
    by the caller.

    AD E.2's `segment` is untouched: a segment map is every position of the segment as a
    `Band.MAP` row and nothing for the rest, exactly as before.
    """
    by_id = observation.by_id
    order = observation.thread_map.order
    positions = observation.thread_map.positions
    named = wanted.named if keep is None else (wanted.named & keep)

    def row_for(message_id: str, band: Band, asked: Depth) -> PlannedRow:
        message = by_id.get(message_id)
        processed = bodies.get(message_id)
        body = processed.body_clean if processed is not None else None
        snippet = _snippet_of(message)
        text = body.text if body is not None else snippet
        return PlannedRow(
            id=message_id,
            position=positions[message_id],
            band=band,
            depth=depth_for(text, body, asked),
            body=processed.default_view if processed is not None else None,
            snippet=snippet,
            base_reductions=processed.reductions if processed is not None else (),
            attachments=wanted.attachments.get(message_id, ()),
            auth_record="" if message is None else _auth_record_of(message),
            from_address="" if message is None else from_header_of(message)[0],
            from_display="" if message is None else from_header_of(message)[1],
        )

    if wanted.segment is not None:
        segment_rows = tuple(
            row_for(
                mid,
                Band.EVIDENCE if mid in named else Band.MAP,
                wanted.view if mid in named else wanted.map_view,
            )
            for mid in order
            if _segment_at(observation, positions[mid]) in (None, wanted.segment)
        )
        return segment_rows, ()

    as_rows: set[str] = set(named)
    if not wanted.named and page_size is not None:
        page = wanted.page or 0
        window = order[page * page_size : (page + 1) * page_size]
        as_rows.update(window)
    rows = tuple(
        row_for(mid, Band.REQUESTED, wanted.view if mid in named else Depth.STUB)
        for mid in order
        if mid in as_rows
    )
    if not inventory:
        return rows, ()
    runs: list[PlannedRun] = []
    block: list[str] = []
    for mid in order:
        if mid in as_rows:
            if block:
                runs.append(
                    PlannedRun(
                        start=positions[block[0]], end=positions[block[-1]], member_ids=tuple(block)
                    )
                )
                block = []
            continue
        block.append(mid)
    if block:
        runs.append(
            PlannedRun(start=positions[block[0]], end=positions[block[-1]], member_ids=tuple(block))
        )
    return rows, tuple(runs)


def _segment_at(observation: Observation, position: int) -> int | None:
    """Which segment of AD §E.2's experimental map this position falls in, or `None`.

    `None` for every thread below `FLAT_MAP_MESSAGE_BOUNDARY` and for every thread that
    never paused - that is the depth-*n-1* arm, and it is the reason a `segment` argument
    against such a thread returns the map **whole** rather than nothing. A second
    navigational level that does not exist for this thread cannot be indexed into, and an
    empty response would be this server reporting that a thread has no messages in a
    segment it has no segments in.
    """
    return segment_of(
        position,
        stated_total=observation.thread_map.stated_total,
        order=observation.thread_map.order,
        internal_dates={
            message_id: _stamp(observation, message_id)
            for message_id in observation.thread_map.order
        },
    )


def _stamp(observation: Observation, message_id: str) -> int | None:
    message = observation.by_id.get(message_id)
    if message is None or message.internal_date is None:
        return None
    try:
        return int(message.internal_date)
    except ValueError:  # pragma: no cover - Gmail states epoch milliseconds
        return None


def _collapsed(
    planned: PlannedSource, *, page_size: int, why: str = WithheldCap.MAP_PAGE.value
) -> tuple[CollapsedRun, ...]:
    """The thread's other pages as wire runs: positions, ids once, one page call each.

    **The affordance is a page of structure, never the ids again** (navigation redesign,
    2026-09-14). It used to be `get_messages(member_ids=<all of them>, view=snippet)` - the
    ids a third time on the wire, and a call whose answer collapsed into the same run and
    offered itself again (R-M2-080). A run now names the page its first position falls in,
    and following that call returns that page's positions as rows, each with its own
    `unabridged` read. A run that spans several pages names its first; the source's `page`,
    `page_size` and `pages` say how to reach the others directly.

    `why` is `map_page` for a run the response planned as a page boundary, and the ladder's
    ceiling cap for one a step produced; the two are different facts and a reader can tell
    them apart.
    """
    return tuple(
        CollapsedRun(
            positions=(run.start, run.end),
            count=len(run.member_ids),
            member_ids=run.member_ids,
            why=why,
            affordance=Affordance(
                tool=ToolName.THREAD_MAP,
                args={"thread_id": planned.thread_id, "page": page_of(run.start, page_size)},
            ),
        )
        for run in planned.runs
    )


def _headers_observed(message: Message | None) -> bool:
    return message is not None and message.payload is not None


def _rows_of(
    observation: Observation,
    planned: PlannedSource,
    wanted: Wanted,
    builder: EnvelopeBuilder,
    *,
    accounted: frozenset[str],
) -> list[MessageRow]:
    """The rows of one source, each naming its reply parent when this source accounts for it.

    **Referencing a parent is not disclosing it** (R-M2-077). A row's `reply_parent_id` is a
    reference, and a reference is followable whenever the source *accounts* for the parent -
    as a row, as a collapsed-run member, or as a withheld record carrying an affordance. Only
    a row discloses content, and nothing here changes which rows do.

    `present` used to mean *rows only*, so a parent the ladder had collapsed into a run or
    withheld had its pointer cleared while `linkage` still said one was found - the pair
    `MessageRow` refuses under C-02a. Every `mailweave_get_messages` for a reply whose
    ancestors were not also requested raised, by id and by map position alike, and the
    harness's recovery driver read the raise as "expansion reached nothing".
    """
    by_id = observation.by_id
    links = observation.thread_map.structure.by_id
    rows: list[MessageRow] = []
    for planned_row in planned.rows:
        message_id = planned_row.id
        text, reductions = planned_row.rendered()
        link = links[message_id]
        named = message_id in wanted.named
        reason: Reason = (
            RequestedById(requested_id=message_id)
            if named
            else ThreadMember(thread_id=observation.thread_id, position=planned_row.position)
        )
        rows.append(
            MessageRow(
                id=message_id,
                position=planned_row.position,
                role=Role.REQUESTED if named or text is not None else Role.STUB,
                reason=reason,
                mailbox=_provenance(by_id.get(message_id)),
                depth=planned_row.depth,
                linkage=link.linkage,
                reply_parent_id=(link.parent_id if link.parent_id in accounted else None),
                can_be_a_parent=link.can_be_a_parent,
                reductions=reductions,
                attachments=wanted.attachments.get(message_id, ()),
                # INJ-05, on this surface too: `mailweave_get_messages` and
                # `mailweave_thread_map` disclose the same per-message identity facts
                # `mailweave_search` does, and the ladder charges them on every path.
                headers_observed=_headers_observed(by_id.get(message_id)),
                reply_to_differs=(
                    None
                    if (message := by_id.get(message_id)) is None
                    else _reply_to_differs(message)
                ),
                authentication=(
                    None
                    if (found := by_id.get(message_id)) is None
                    else _authentication_of(found, builder)
                ),
                attribution=_attribution_of(by_id.get(message_id), builder),
                unabridged=unabridged_affordance(message_id),
                content=(
                    None
                    if text is None
                    else builder.fence_content(
                        text,
                        trust=Trust.UNTRUSTED_THIRD_PARTY,
                        source=(
                            ContentSource.GMAIL_BODY
                            if planned_row.depth in (Depth.BODY_CLEAN, Depth.BODY_FULL)
                            else ContentSource.GMAIL_SNIPPET
                        ),
                    )
                ),
            )
        )
    return rows


def _asked_for(tool: ToolName, named: Sequence[str]) -> AskedFor:
    """What this call asked for, in the schema's own terms.

    An expansion has no Gmail query and therefore no term coverage to report, so
    `term_coverage` is 1.0: every constraint the caller stated - the ids - was enforced, and
    nothing was dropped. That is the truthful reading of the field for a call that named its
    own answer, and it is stated here rather than left as a default nobody argued for.
    """
    return AskedFor(
        parsed=ParsedQuerySummary(operators={tool.value: ", ".join(named) or "whole thread"}),
        enforced=tuple(named) or (tool.value,),
        dropped=(),
        term_coverage=1.0,
        constraint_drop_depth=0,
    )


def _reply_parent_gap_is_declared(rows: Sequence[MessageRow], accounted: frozenset[str]) -> None:
    """Every named reply parent is one this source accounts for.

    Called for its refusal: `Source` refuses a parent it does not account for, and this
    asserts `_rows_of` agrees with that rule rather than trusting the order they run in.
    `accounted` is rows, collapsed-run members and withheld records together - the three
    dispositions A.7a allows - because a reference is followable through any of them
    (R-M2-077). It is *not* the rows alone: that reading cleared the pointer on every reply
    whose parent the ladder had collapsed or withheld, and `MessageRow` then refused the row.
    """
    orphaned = sorted(
        row.id
        for row in rows
        if row.reply_parent_id is not None and row.reply_parent_id not in accounted
    )
    if orphaned:  # pragma: no cover - `_rows_of` names only accounted parents
        raise AssertionError(
            f"rows {orphaned} name a reply parent this source does not account for"
        )


@dataclass(frozen=True)
class Arrangement:
    """One arrangement of an explicit read the fit loop tried, and what it decided.

    The two dimensions the loop moves along, in the order it sacrifices them (navigation
    redesign, 2026-09-14): which kept threads carry their inventory beside the rows
    (`inventoried`; a kept thread not in it is *scoped* - the rows, their reply parents as
    withheld records, and one thread-granular group under the map call for everything else),
    and which requested rows stay (`keep`, a prefix of the request in request order - the
    rest goes to a `requested` continuation). Nothing here is decided by a constant: each is
    the outcome of the estimate and then of the rendered measurement.

    A row is never cut below the depth asked for. A single requested body that does not fit
    even alone and scoped is declined with the `view` narrowing R-MCP-039 certified (`body_full`
    → `body_clean`); a head-truncated `body_full` would be a `body_full` that is not full, and
    the tail of a message longer than the cap is a declared limit of the inline surface.
    """

    keep: tuple[str, ...]
    inventoried: frozenset[str]

    def scoped(self, thread_id: str) -> bool:
        return thread_id not in self.inventoried


@dataclass(frozen=True)
class _Planned:
    """The layout of one arrangement, with the dispositions it implies filed by thread."""

    layout: Layout
    #: Threads whose named messages are all in the continuation: not carried at all, their
    #: ids one thread-granular group each, the group's call the thread's share of the batch.
    deferred: Mapping[str, tuple[str, ...]]
    #: Threads carried as rows without their inventory: the rest of the thread is one group
    #: under the map call, and the rows' direct reply parents are withheld records.
    scoped_rest: Mapping[str, tuple[str, ...]]
    scoped_parents: Mapping[str, tuple[str, ...]]
    #: The requested ids this response does not carry as rows, in request order.
    rest: tuple[str, ...]
    view: Depth

    @property
    def cut(self) -> bool:
        """Whether this arrangement carries less than the whole of what was asked for."""
        return bool(
            self.rest
            or self.deferred
            or any(self.scoped_rest.values())
            or any(self.scoped_parents.values())
        )


def _requested_in(observations: Sequence[Observation], wanted: Wanted) -> tuple[str, ...]:
    """The named ids an observed thread actually holds, in request order.

    An id that no observed thread lists is not deliverable by this response and not by a
    continuation of it either - it is neither a row nor an omission of this response, and it
    stays where it always was: echoed in `asked_for.enforced` and absent from the payload.
    """
    held = frozenset(mid for one in observations for mid in one.thread_map.order)
    return tuple(mid for mid in wanted.ordered() if mid in held)


def _batch_affordance(ids: Sequence[str], view: Depth) -> Affordance:
    return Affordance(
        tool=ToolName.GET_MESSAGES, args={"message_ids": list(ids), "view": view.value}
    )


def _continuation_for(rest: Sequence[str], view: Depth) -> Continuation | None:
    if not rest:
        return None
    return Continuation(
        scope="requested",
        message_ids=tuple(rest),
        remaining=len(rest),
        affordance=_batch_affordance(rest, view),
    )


def _planned_source(
    observation: Observation,
    wanted: Wanted,
    bodies: Mapping[str, ProcessedMessage],
    *,
    rank: int,
    keep: frozenset[str] | None,
    page_size: int,
    inventory: bool,
) -> PlannedSource:
    rows, runs = _plan_source(
        observation, wanted, bodies, keep=keep, page_size=page_size, inventory=inventory
    )
    return PlannedSource(
        thread_id=observation.thread_id,
        rank=rank,
        hit_bearing=bool(wanted.named & frozenset(observation.thread_map.order)),
        rows=rows,
        runs=runs,
        participants=participants_block(observation.thread_map),
    )


def _plan_read(
    observations: Sequence[Observation],
    wanted: Wanted,
    bodies: Mapping[str, ProcessedMessage],
    ledger: DispositionLedger,
    arrangement: Arrangement,
    *,
    requested: tuple[str, ...],
    page_sizes: Mapping[str, int],
    echo: int,
    bounds: Ceilings,
) -> _Planned:
    """The layout one arrangement of an explicit read produces, dispositions decided.

    **Every accounted id has exactly one disposition here, before anything is built.** A
    kept thread with its inventory carries every message as a row or a run member. A kept
    thread without it (scoped) carries its requested rows, withholds their direct reply
    parents one record each - so the reference on each row is followable (R-M2-077) - and
    groups the rest under the thread's map call. A deferred thread carries nothing and is one
    group under the call that reads its share of the batch, which is the continuation's call
    restricted to that thread. The layout charges all of it - rows, runs, records, groups,
    the not-included block and the continuation itself - so what the estimate admits is what
    the wire will carry.
    """
    keep = frozenset(arrangement.keep)
    rest = tuple(mid for mid in requested if mid not in keep)
    continuation = _continuation_for(rest, wanted.view)
    sources: list[PlannedSource] = []
    deferred: dict[str, tuple[str, ...]] = {}
    scoped_rest: dict[str, tuple[str, ...]] = {}
    scoped_parents: dict[str, tuple[str, ...]] = {}
    withheld: list[str] = []
    grouped: set[str] = set()
    split_off: list[str] = []
    deferred_calls = 0
    for rank, observation in enumerate(observations):
        order = observation.thread_map.order
        held = frozenset(order)
        named_here = wanted.named & held
        if named_here and not (named_here & keep):
            share = tuple(mid for mid in rest if mid in held)
            deferred[observation.thread_id] = share
            # The call that reads this thread's share renders three times - the not-included
            # entry, the group, and the twin in `affordances[]` - and a share is a list of ids.
            deferred_calls += 3 * affordance_echo_chars(_batch_affordance(share, wanted.view))
            split_off.append(observation.thread_id)
            withheld.extend(order)
            grouped.update(order)
            continue
        scoped = arrangement.scoped(observation.thread_id)
        source = _planned_source(
            observation,
            wanted,
            bodies,
            rank=rank,
            keep=keep,
            page_size=page_sizes[observation.thread_id],
            inventory=not scoped,
        )
        if scoped:
            links = observation.thread_map.structure.by_id
            row_ids = frozenset(row.id for row in source.rows)
            # A parent this thread does not hold is a declared gap on the row, never a
            # record here: a note for an id outside `H` would be refused at certification.
            parents = tuple(
                sorted(
                    {
                        parent
                        for row in source.rows
                        if (parent := links[row.id].parent_id) is not None
                        and parent not in row_ids
                        and parent in held
                    }
                )
            )
            others = tuple(mid for mid in order if mid not in row_ids and mid not in parents)
            scoped_parents[observation.thread_id] = parents
            scoped_rest[observation.thread_id] = others
            withheld.extend(parents)
            withheld.extend(others)
            grouped.update(others)
        sources.append(source)
    layout = Layout(
        sources=tuple(sources),
        accounted_ids=frozenset(ledger.origins),
        # **No E2 floor, and that is a statement rather than an omission.** The floor is the
        # reply chain of an *evidence* message a query found (A.9, OD-3); an expansion has no
        # query and its evidence is exactly what the caller named. There is therefore nothing
        # for A.9a step 6's declared overflow to protect, so an expansion response is bounded
        # by the normal ceiling and never reaches the 12,000-token overflow - which is the
        # right answer, because the overflow is not a budget.
        floor_ids=frozenset(),
        hit_ids=frozenset(wanted.named),
        split_off=tuple(split_off),
        withheld_ids=tuple(withheld),
        grouped_ids=frozenset(grouped),
        # One group per deferred thread and per scoped thread with a rest, each filed under
        # the ceiling cap by `_record_read_dispositions`; none folds (no widening call).
        groups=frozenset(
            (thread_id, WithheldCap.DISCLOSED_TOKEN_CEILING)
            for thread_id in (
                *deferred,
                *(thread_id for thread_id, ids in scoped_rest.items() if ids),
            )
        ),
        foldable_caps=frozenset(),
        accounted_thread_id_chars=max((len(one.thread_id) for one in observations), default=0),
        # R-V01-004: `asked_for` echoes every named id; charged at what it renders to. The
        # continuation is charged beside it because it is the other block that repeats the
        # request, and it is known before the ladder runs.
        request_echo_chars=echo + continuation_chars(continuation) + deferred_calls,
        # R-V01-006: an expansion's evidence is what it was asked for; an emptied map is
        # a refusal, never `-32603`.
        evidence_is_the_map=True,
        segmented=False,
        ceiling_applied=bounds.normal,
    )
    return _Planned(
        layout=layout,
        deferred=deferred,
        scoped_rest=scoped_rest,
        scoped_parents=scoped_parents,
        rest=rest,
        view=wanted.view,
    )


def _largest(upper: int, fits: Callable[[int], bool], *, lower: int = 1) -> int | None:
    """The largest `n` in `[lower, upper]` for which `fits(n)`, assuming `fits` is monotone.

    `None` when even `lower` does not fit. Bisection, so a batch of forty ids costs six
    trials rather than forty; the monotonicity it assumes is the estimate's (a kept row costs
    at least what its replacement as a run member, a record or a group does) and the render's.
    """
    if upper < lower:
        return None
    if fits(upper):
        return upper
    if not fits(lower):
        return None
    low, high = lower, upper  # fits(low) and not fits(high)
    while high - low > 1:
        mid = (low + high) // 2
        if fits(mid):
            low = mid
        else:
            high = mid
    return low


def expand(
    observations: Sequence[Observation],
    *,
    wanted: Wanted,
    bodies: Mapping[str, ProcessedMessage],
    ledger: DispositionLedger,
    tool: ToolName,
    counters: Counters,
    minter: HandleMinter | None = None,
    mailbox_history_id: str | None = None,
    in_band: Sequence[ErrorEntry] = (),
    ceilings: Ceilings | None = None,
) -> Envelope:
    """Disclose what the caller named, sized to fit, with the remainder one call away.

    Two shapes share this function and everything below it (navigation redesign,
    2026-09-14):

    * **a thread map** (`wanted.named` empty) is served as a *page*: `page_size` rows of
      the thread at stub depth, the other pages as compact runs whose affordances name a
      page, and a `thread` continuation for the next page. `page_size` is not a constant -
      `_page_size` finds the widest page whose estimate fits beside the inventory of the
      rest - so pages tile the thread whichever one is asked for first;
    * **an explicit read** (`wanted.named` non-empty) is served *request first*: the named
      rows at the requested depth, as many whole ones as fit in request order, and the
      thread each is in as a compact inventory when that fits beside them. When it does not,
      `_fit` finds the arrangement by a published order of sacrifice: inventories go before
      requested rows do (a thread without its inventory is *scoped*: rows, their reply
      parents withheld one record each, the rest one group under the map call); rows leave
      for a `requested` continuation before the last one is head-truncated; and the last one
      is truncated with its reduction declared before the response declines. Every
      arrangement is checked on the estimate and then **measured as rendered** against the
      host's cap before it is served.

    The response is a map carrier wherever it carries a map: every message of a thread whose
    inventory is here is a row or a declared run member, so `included == stated_total` and a
    reader can compute what is missing from the response alone. A scoped or deferred thread
    says what it does not carry as records and counted groups, each with its executable call,
    and the continuation names the remainder of the request id by id.

    AD E.2's `segment` keeps its own path, `_expand_segment`, untouched: a temporal segment
    of a long thread as map rows, degraded by the ladder as before.

    Raises nothing of its own: `Envelope` refuses an oversized or unaccounted response, and
    that refusal is the one this function wants. It does not catch it, because a response
    this module could not make honest is not a response to serve.
    """
    bounds = ceilings or Ceilings()
    page_sizes = {one.thread_id: page_size(one.thread_map) for one in observations}
    if wanted.segment is not None:
        return _expand_segment(
            observations,
            wanted=wanted,
            bodies=bodies,
            ledger=ledger,
            tool=tool,
            counters=counters,
            minter=minter,
            mailbox_history_id=mailbox_history_id,
            in_band=in_band,
            bounds=bounds,
            page_sizes=page_sizes,
        )
    asked_for = _asked_for(tool, wanted.ordered())
    echo = request_echo_chars(asked_for, ledger.scan_scope)
    if not wanted.named:
        return _expand_map(
            observations,
            wanted=wanted,
            ledger=ledger,
            asked_for=asked_for,
            tool=tool,
            counters=counters,
            minter=minter,
            mailbox_history_id=mailbox_history_id,
            in_band=in_band,
            bounds=bounds,
            page_sizes=page_sizes,
            echo=echo,
        )
    requested = _requested_in(observations, wanted)
    filed: set[str] = set()
    every = frozenset(one.thread_id for one in observations)

    def planned(arrangement: Arrangement) -> _Planned:
        return _plan_read(
            observations,
            wanted,
            bodies,
            ledger,
            arrangement,
            requested=requested,
            page_sizes=page_sizes,
            echo=echo,
            bounds=bounds,
        )

    def estimated(arrangement: Arrangement) -> bool:
        return not over_budget(planned(arrangement).layout, bounds)

    # **Which unit bound, decided on the whole request** (the independent review, finding 3):
    # the arrangement that is served fits by construction, so its own layout cannot say why
    # the whole did not. The token ceiling bound only if the whole request exceeded it in
    # tokens while fitting the host's cap in characters; otherwise - including the case where
    # only the *render* was over - the characters did.
    whole = planned(Arrangement(keep=requested, inventoried=every)).layout
    chars_bound = bounds.host_chars is not None and not (
        whole.cost() > bounds.normal and whole.chars() <= bounds.host_chars
    )

    def served(arrangement: Arrangement) -> Envelope | None:
        """The envelope, or `None` when it renders over the host's cap (M6's measurement)."""
        plan = planned(arrangement)
        # The ladder runs on every arrangement, and on one `_fit` accepted it has nothing to
        # do: every step of the published precedence is a no-op on `Band.REQUESTED` rows and
        # pre-planned runs, and the arrangement already fits. It still runs, so a layout that
        # somehow reached here over budget declines through the same refusal as every other
        # producer rather than through a second arithmetic of this module's own.
        shrunk, steps = run_ladder(plan.layout, ceilings=bounds)
        builder = EnvelopeBuilder(
            ledger,
            asked_for=asked_for,
            ceiling=Ceiling(normal=NORMAL_CEILING_TOKENS, applied=NORMAL_CEILING_TOKENS),
        )
        # The notes the previous trial filed are withdrawn before this one files its own: a
        # note for an id this arrangement discloses would be refused at certification, which
        # is the check doing its job, and nothing is filed for good until the arrangement is.
        ledger.withdraw_notes(filed)
        filed.clear()
        envelope = _assemble_read(
            observations,
            wanted=wanted,
            plan=plan,
            shrunk=shrunk,
            steps=steps,
            arrangement=arrangement,
            builder=builder,
            ledger=ledger,
            counters=counters,
            minter=minter,
            mailbox_history_id=mailbox_history_id,
            in_band=in_band,
            page_sizes=page_sizes,
            filed=filed,
            chars_bound=chars_bound,
        )
        if bounds.host_chars is None:
            return envelope
        mirrored = render(envelope)
        if rendered_chars(mirrored.structured, mirrored.text) > bounds.host_chars:
            return None
        return envelope

    served_envelope = _fit(
        requested,
        threads=tuple(one.thread_id for one in observations),
        estimated=estimated,
        served=served,
    )
    if served_envelope is None:
        raise DisclosureLadderExhausted(
            f"no arrangement of this read fits: {len(requested)} requested message(s), and "
            "the first of them cannot be carried at the depth asked for within the host's "
            "character cap even alone and without its thread's inventory. Declining rather than "
            "serving a response that carries none of what was asked for (DISC-06, OD-3); where a "
            "narrower view exists the retry beside this names it, and the row is never cut",
            top_thread=None,
            hit_threads=len(observations),
            segmented=False,
        )
    return served_envelope


def _fit(
    requested: tuple[str, ...],
    *,
    threads: tuple[str, ...],
    estimated: Callable[[Arrangement], bool],
    served: Callable[[Arrangement], Envelope | None],
) -> Envelope | None:
    """The served envelope of the arrangement that fits, by the published order of sacrifice.

    1. every requested row, every kept thread's inventory;
    2. every requested row, inventories kept thread by thread in rank order while the
       estimate still fits (a thread that loses its inventory is scoped);
    3. no inventories, the longest prefix of requested rows that fits, the rest in the
       `requested` continuation.

    Each level is searched on the estimate (`estimated`, cheap) and its result is then
    **measured as rendered** (`served`); where the render disagrees with the estimate the
    search continues downward on the render itself, so the response served is one whose
    actual serialised size was checked. The order is the design's: requested content before
    context. `None` means not even the first requested row fits alone and scoped, and the
    caller declines with the `view` narrowing (R-MCP-039) rather than cutting the row.
    """
    every = frozenset(threads)
    whole = Arrangement(keep=requested, inventoried=every)
    if estimated(whole) and (envelope := served(whole)) is not None:
        return envelope
    if not requested:
        return None

    kept: set[str] = set()
    for thread_id in threads:
        if estimated(Arrangement(keep=requested, inventoried=frozenset(kept | {thread_id}))):
            kept.add(thread_id)
    if kept and kept != every:
        envelope = served(Arrangement(keep=requested, inventoried=frozenset(kept)))
        if envelope is not None:
            return envelope

    def scoped(n: int) -> Arrangement:
        return Arrangement(keep=requested[:n], inventoried=frozenset())

    n = _largest(len(requested), lambda k: estimated(scoped(k)))
    while n is not None:
        if (envelope := served(scoped(n))) is not None:
            return envelope
        n = _largest(n - 1, lambda k: estimated(scoped(k)))
    return None


def _expand_map(
    observations: Sequence[Observation],
    *,
    wanted: Wanted,
    ledger: DispositionLedger,
    asked_for: AskedFor,
    tool: ToolName,
    counters: Counters,
    minter: HandleMinter | None,
    mailbox_history_id: str | None,
    in_band: Sequence[ErrorEntry],
    bounds: Ceilings,
    page_sizes: Mapping[str, int],
    echo: int,
) -> Envelope:
    """One page of each observed thread's structure, the rest as runs and a continuation.

    A map is planned to fit by construction: `_page_size` bisected the widest page whose
    estimate fits beside the inventory of the rest, a second run and a continuation, so the
    ladder has nothing to do, and the render is measured by `partition.declared_result` as it
    is for every served response. A page the estimate admits and the wire refuses is an
    estimate defect - certified against by the shape matrix - and declines rather than
    shrinks: shrinking a page would change `page_size`, and with it which positions every
    other page holds.

    **The continuation carries this response's handle** (continuation correctness,
    2026-09-15): `mailweave_thread_map(map_id, page + 1)`, minted here before the
    continuation is built so the two name one state. Following it redeems the handle, and a
    thread that moved is `handle_stale` with page 0 as the restart rather than a page of a
    different state. A response that mints no handle - no key, no thread `historyId`, no
    mailbox watermark - offers no continuation; its runs still point at every page.
    """
    builder = EnvelopeBuilder(
        ledger,
        asked_for=asked_for,
        ceiling=Ceiling(normal=NORMAL_CEILING_TOKENS, applied=NORMAL_CEILING_TOKENS),
    )
    by_thread = {observation.thread_id: observation for observation in observations}
    page = wanted.page or 0
    for observation in observations:
        width = page_sizes[observation.thread_id]
        pages = pages_of(len(observation.thread_map.order), width)
        if page >= pages:
            raise ArgumentInvalid(
                f"{tool.value}: page {page} is outside thread {observation.thread_id}, which "
                f"has {pages} page(s) of {width} position(s); pages are 0 to {pages - 1}"
            )
    map_ids = {
        observation.thread_id: _map_id_for(
            observation,
            minter,
            mailbox_history_id,
            page_size=page_sizes[observation.thread_id],
        )
        for observation in observations
    }
    continuations = tuple(
        continuation
        for observation in observations
        if (
            continuation := next_page(
                observation.thread_id,
                len(observation.thread_map.order),
                page,
                page_sizes[observation.thread_id],
                map_id=map_ids[observation.thread_id],
            )
        )
        is not None
    )
    layout = Layout(
        sources=tuple(
            _planned_source(
                observation,
                wanted,
                {},
                rank=rank,
                keep=None,
                page_size=page_sizes[observation.thread_id],
                inventory=True,
            )
            for rank, observation in enumerate(observations)
        ),
        accounted_ids=frozenset(ledger.origins),
        floor_ids=frozenset(),
        hit_ids=frozenset(),
        request_echo_chars=echo + sum(continuation_chars(one) for one in continuations),
        evidence_is_the_map=True,
        segmented=False,
    )
    shrunk, steps = run_ladder(layout, ceilings=bounds)
    for planned_source in shrunk.sources:
        observation = by_thread[planned_source.thread_id]
        here = _withheld_here(observation, shrunk)
        accounted = planned_source.present_ids | frozenset(here)
        rows = _rows_of(observation, planned_source, wanted, builder, accounted=accounted)
        _reply_parent_gap_is_declared(rows, accounted)
        width = page_sizes[observation.thread_id]
        builder.add_source(
            _source_of(
                observation,
                rows=rows,
                runs=_collapsed(planned_source, page_size=width),
                here=here,
                builder=builder,
                map_id=map_ids[observation.thread_id],
                page=(page, width, pages_of(len(observation.thread_map.order), width)),
            )
        )
    for continuation in continuations:
        builder.add_continuation(continuation)
    _record_ladder_dispositions(
        shrunk, ledger=ledger, builder=builder, by_thread=by_thread, reduced=bool(steps)
    )
    return _finish(
        builder,
        shrunk=shrunk,
        layout=layout,
        steps=steps,
        in_band=in_band,
        counters=counters,
        cut=False,
        remainder=False,
    )


def _source_of(
    observation: Observation,
    *,
    rows: Sequence[MessageRow],
    runs: Sequence[CollapsedRun],
    here: tuple[str, ...],
    builder: EnvelopeBuilder,
    map_id: str | None,
    page: tuple[int, int, int] | None = None,
) -> Source:
    rows = tuple(rows)
    runs = tuple(runs)
    return Source(
        thread_id=observation.thread_id,
        stated_total=observation.thread_map.stated_total,
        included=len(rows) + sum(run.count for run in runs),
        included_as_stub=sum(1 for row in rows if row.depth is Depth.STUB)
        + sum(run.count for run in runs),
        fetched_at=observation.fetched_at,
        verified_at=observation.verified_at,
        messages=rows,
        collapsed_runs=runs,
        withheld_here=here,
        participants=_participants_here(observation, rows, runs, builder),
        structure=structure_block(observation.thread_map, rows=rows),
        map_id=map_id,
        page=None if page is None else page[0],
        page_size=None if page is None else page[1],
        pages=None if page is None else page[2],
    )


def _assemble_read(
    observations: Sequence[Observation],
    *,
    wanted: Wanted,
    plan: _Planned,
    shrunk: Layout,
    steps: Sequence[LadderStep],
    arrangement: Arrangement,
    builder: EnvelopeBuilder,
    ledger: DispositionLedger,
    counters: Counters,
    minter: HandleMinter | None,
    mailbox_history_id: str | None,
    in_band: Sequence[ErrorEntry],
    page_sizes: Mapping[str, int],
    filed: set[str],
    chars_bound: bool,
) -> Envelope:
    """Build the envelope of one arrangement: sources, dispositions, continuation, verdicts."""
    by_thread = {observation.thread_id: observation for observation in observations}
    grouped = frozenset(shrunk.grouped_ids)
    for planned_source in shrunk.sources:
        observation = by_thread[planned_source.thread_id]
        # What this source accounts for as *records*: the ids withheld out of it that are
        # not written as a group. A grouped id is accounted for by the group, and naming it
        # here would claim a record the response does not carry.
        here = tuple(mid for mid in _withheld_here(observation, shrunk) if mid not in grouped)
        accounted = planned_source.present_ids | frozenset(here)
        rows = _rows_of(observation, planned_source, wanted, builder, accounted=accounted)
        _reply_parent_gap_is_declared(rows, accounted)
        # A scoped thread is not a map: it carries the requested rows and says, id by id and
        # as a counted group, what it does not carry. It therefore mints no `map_id` - the
        # claim "this is the thread's map" would be false of it - and the map is the group's
        # own affordance away.
        builder.add_source(
            _source_of(
                observation,
                rows=rows,
                runs=_collapsed(planned_source, page_size=page_sizes[observation.thread_id]),
                here=here,
                builder=builder,
                map_id=(
                    None
                    if arrangement.scoped(observation.thread_id)
                    else _map_id_for(
                        observation,
                        minter,
                        mailbox_history_id,
                        page_size=page_sizes[observation.thread_id],
                    )
                ),
            )
        )
    continuation = _continuation_for(plan.rest, plan.view)
    if continuation is not None:
        builder.add_continuation(continuation)
    _record_read_dispositions(
        plan,
        shrunk,
        ledger=ledger,
        builder=builder,
        by_thread=by_thread,
        filed=filed,
        chars_bound=chars_bound,
    )
    return _finish(
        builder,
        shrunk=shrunk,
        layout=plan.layout,
        steps=steps,
        in_band=in_band,
        counters=counters,
        cut=plan.cut,
        remainder=bool(plan.rest),
    )


def _finish(
    builder: EnvelopeBuilder,
    *,
    shrunk: Layout,
    layout: Layout,
    steps: Sequence[LadderStep],
    in_band: Sequence[ErrorEntry],
    counters: Counters,
    cut: bool,
    remainder: bool,
) -> Envelope:
    """The verdicts every expansion states the same way, then the envelope."""
    builder.set_ceiling(
        Ceiling(
            normal=NORMAL_CEILING_TOKENS,
            applied=shrunk.ceiling_applied or NORMAL_CEILING_TOKENS,
            why=None,
        )
    )
    # `truncated_by: mailweave` is the claim that this server shortened the response so the
    # host would not: the ladder removed text, or the fit loop deferred, scoped or truncated
    # part of what was asked for. Each leaves an artifact the envelope checks the claim
    # against; a response served whole makes no such claim.
    if cut or (
        steps and (shrunk.withheld_ids or shrunk.split_off or _rows_lost_depth(layout, shrunk))
    ):
        builder.mark_self_truncated()
    for declaration in in_band:
        builder.add_error(declaration)
    # **What the response carries is rows *plus* collapsed-run members** (amendment A4). A
    # message inside a declared run is present and reachable, so counting only rows would
    # let a fully-collapsed thread map report `not_found` about a thread it just returned
    # whole. And a response the ladder had to degrade is `inconclusive` rather than
    # `not_found` even when it carries nothing, because a cap fired (OD-2, D.2's rule) -
    # `RetrievalReport` refuses the other reading, which is how this was found.
    caps = (BudgetCapName.DISCLOSED_TOKEN_CEILING,) if (steps or cut) else ()
    present = sum(
        len(source.messages) + sum(run.count for run in source.collapsed_runs)
        for source in builder.sources
    )
    outcome = Outcome.ANSWERED if present else (Outcome.INCONCLUSIVE if caps else Outcome.NOT_FOUND)
    # A batch with a remainder is not yet the evidence that was asked for: sufficient when
    # every requested row is here, ambiguous while the continuation still names some.
    sufficiency = Sufficiency.SUFFICIENT if present and not remainder else Sufficiency.AMBIGUOUS
    return builder.build(
        outcome=outcome,
        rungs=(EXPANSION_RUNG,),
        sufficiency=sufficiency,
        counters=counters,
        not_tried=(),
        budget_caps_hit=caps,
    )


def _record_read_dispositions(
    plan: _Planned,
    layout: Layout,
    *,
    ledger: DispositionLedger,
    builder: EnvelopeBuilder,
    by_thread: Mapping[str, Observation],
    filed: set[str],
    chars_bound: bool,
) -> None:
    """File what a read arrangement does not carry, each id under the call that gets it.

    Three kinds, three reasons, each written at the granularity of its recovery call (round
    29's rule): a deferred thread's messages are one group whose call is that thread's share
    of the continuation; a scoped thread's reply parents are records whose call reads the
    parent; a scoped thread's other messages are one group whose call is the thread's map.
    `filed` collects every id noted, so a later trial of the fit loop can withdraw them.
    """
    if plan.cut or a_ceiling_bound(layout, reduced=False):
        builder.state_the_binding_ceiling(
            HOST_CAP_WHY.format(cap=HOST_RESULT_CHAR_CAP)
            if chars_bound
            else "the response reached its declared token ceiling"
        )
    deferred_why = (
        "deferred: the requested messages of this thread did not fit this response and are "
        "named by its continuation; the call beside it reads them"
    )
    for thread_id, share in plan.deferred.items():
        observation = by_thread[thread_id]
        affordance = (
            _batch_affordance(share, plan.view) if share else thread_map_affordance(thread_id)
        )
        builder.add_not_included_source(
            NotIncludedSource(
                thread_id=thread_id,
                stated_total=observation.thread_map.stated_total,
                affordance=affordance,
            ),
            why=deferred_why,
        )
        for message_id in observation.thread_map.order:
            ledger.note_withheld(
                message_id=message_id,
                cap=WithheldCap.DISCLOSED_TOKEN_CEILING,
                why=deferred_why,
                affordance=affordance,
                granularity=WithheldGranularity.THREAD,
            )
            filed.add(message_id)
    for parents in plan.scoped_parents.values():
        for parent in parents:
            affordance = _batch_affordance((parent,), plan.view)
            ledger.note_withheld(
                message_id=parent,
                cap=WithheldCap.DISCLOSED_TOKEN_CEILING,
                why=(
                    "scoped: this response carries the requested messages of the thread "
                    "without its inventory; this one is a requested message's reply parent, "
                    "referenced by the row and read by the call beside it"
                ),
                affordance=affordance,
            )
            builder.add_affordance(affordance)
            filed.add(parent)
    for thread_id, others in plan.scoped_rest.items():
        affordance = thread_map_affordance(thread_id)
        for message_id in others:
            ledger.note_withheld(
                message_id=message_id,
                cap=WithheldCap.DISCLOSED_TOKEN_CEILING,
                why=(
                    "scoped: this response carries the requested messages of the thread "
                    "without its inventory, which did not fit beside them; the thread's "
                    "structure is the map call beside it, and a requested message among "
                    "these is named by the continuation"
                ),
                affordance=affordance,
                granularity=WithheldGranularity.THREAD,
            )
            filed.add(message_id)
    # Anything the ladder did on top - on an arrangement the fit loop accepted, nothing - is
    # filed exactly as the other producers file it.
    already = frozenset(plan.layout.withheld_ids)
    for message_id in sorted(frozenset(layout.withheld_ids) - already):
        affordance = _batch_affordance((message_id,), Depth.BODY_CLEAN)
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
        filed.add(message_id)
    for thread_id in layout.split_off:
        if thread_id in plan.deferred:
            continue
        observation = by_thread[thread_id]
        affordance = thread_map_affordance(thread_id)
        builder.add_not_included_source(
            NotIncludedSource(
                thread_id=thread_id,
                stated_total=observation.thread_map.stated_total,
                affordance=affordance,
            ),
            why=(
                "A.9a step 7: this source was split off to fit the ceiling stated in omission.bound"
            ),
        )
        builder.add_affordance(affordance)


def _expand_segment(
    observations: Sequence[Observation],
    *,
    wanted: Wanted,
    bodies: Mapping[str, ProcessedMessage],
    ledger: DispositionLedger,
    tool: ToolName,
    counters: Counters,
    minter: HandleMinter | None,
    mailbox_history_id: str | None,
    in_band: Sequence[ErrorEntry],
    bounds: Ceilings,
    page_sizes: Mapping[str, int],
) -> Envelope:
    """AD E.2's experimental segment map, on the ladder, as it was before the redesign."""
    asked_for = _asked_for(tool, sorted(wanted.named))
    builder = EnvelopeBuilder(
        ledger,
        asked_for=asked_for,
        ceiling=Ceiling(normal=NORMAL_CEILING_TOKENS, applied=NORMAL_CEILING_TOKENS),
    )
    by_thread = {observation.thread_id: observation for observation in observations}
    layout = Layout(
        sources=tuple(
            PlannedSource(
                thread_id=observation.thread_id,
                rank=rank,
                hit_bearing=bool(wanted.named & frozenset(observation.thread_map.order)),
                rows=_plan_source(observation, wanted, bodies)[0],
                participants=participants_block(observation.thread_map),
            )
            for rank, observation in enumerate(observations)
        ),
        accounted_ids=frozenset(ledger.origins),
        floor_ids=frozenset(),
        hit_ids=frozenset(wanted.named),
        request_echo_chars=request_echo_chars(asked_for, ledger.scan_scope),
        evidence_is_the_map=True,
        # R-V01-010: a `segment: 0` retry is a narrowing only for a thread that has segments.
        segmented=any(_segment_at(observation, 0) is not None for observation in observations),
    )
    shrunk, steps = run_ladder(layout, ceilings=bounds)
    for planned_source in shrunk.sources:
        observation = by_thread[planned_source.thread_id]
        here = _withheld_here(observation, shrunk)
        accounted = planned_source.present_ids | frozenset(here)
        rows = _rows_of(observation, planned_source, wanted, builder, accounted=accounted)
        _reply_parent_gap_is_declared(rows, accounted)
        # A segment's runs are the ladder's own collapses of its map rows: they carry the
        # ceiling's reason and point at the thread's first page.
        runs = _collapsed(
            planned_source,
            page_size=max(len(observation.thread_map.order), 1),
            why=WithheldCap.DISCLOSED_TOKEN_CEILING.value,
        )
        builder.add_source(
            _source_of(
                observation,
                rows=rows,
                runs=runs,
                here=here,
                builder=builder,
                map_id=_map_id_for(
                    observation,
                    minter,
                    mailbox_history_id,
                    page_size=page_sizes[observation.thread_id],
                ),
            )
        )
    _record_ladder_dispositions(
        shrunk, ledger=ledger, builder=builder, by_thread=by_thread, reduced=bool(steps)
    )
    return _finish(
        builder,
        shrunk=shrunk,
        layout=layout,
        steps=steps,
        in_band=in_band,
        counters=counters,
        cut=False,
        remainder=False,
    )


def _rows_lost_depth(before: Layout, after: Layout) -> bool:
    """Whether the ladder actually removed text, as distinct from raising a ceiling."""
    was = {row.id: row.depth for source in before.sources for row in source.rows}
    now = {row.id: row.depth for source in after.sources for row in source.rows}
    return any(now.get(message_id) != depth for message_id, depth in was.items())


def _participants_here(
    observation: Observation,
    rows: Sequence[MessageRow],
    runs: Sequence[CollapsedRun],
    builder: EnvelopeBuilder,
) -> tuple[ThreadParticipant, ...]:
    """The participant index, narrowed to the messages this response actually discloses.

    **The narrowing rule moved to `envelope.wire.participants_within`** (round 26,
    R-DISC-032), because the search path needed the identical one and the A.9a ladder now
    charges the block it produces: three copies of a filter is three chances for the ladder's
    number and the envelope's number to disagree, which is host truncation arriving from
    inside.

    The narrowing set is the source's **rows**, which is what this path already used and what
    the search path now uses too. A message inside a declared collapsed run is present and
    reachable and it is not a row, and `assemble.structure_block` counts rows for the same
    reason: a summary that described messages the enumeration beside it does not show would be
    the two disagreeing. `PlannedSource.emitted_participants` applies the identical rule, so
    what the A.9a ladder charged is what the wire carries.
    """
    del runs  # kept in the signature so the narrowing rule is visible at the call site
    present = frozenset(row.id for row in rows)
    return participants_within(
        participants_block(
            observation.thread_map,
            display_names=_display_names_of(observation.messages),
            builder=builder,
        ),
        present,
    )


def _map_id_for(
    observation: Observation,
    minter: HandleMinter | None,
    mailbox_history_id: str | None,
    *,
    page_size: int,
) -> str | None:
    """This source's redeemable handle, or `None` when one cannot honestly be minted.

    The three `None` cases are `assemble._map_id_for`'s, unchanged and for its reasons: no
    key, no thread `historyId`, or no mailbox watermark to walk a liveness probe from. A
    handle missing any of them could never be verified against anything. `page_size` is the
    width this response paged the thread at, signed into the handle so a later
    `thread_map(map_id, page)` can refuse a page the width no longer places.
    """
    if minter is None or observation.history_id is None or mailbox_history_id is None:
        return None
    return minter.for_one_thread(
        thread_id=observation.thread_id,
        history_id=observation.history_id,
        mailbox_history_id=mailbox_history_id,
        fetched_at=observation.fetched_at,
        digest=mapping_digest([observation.thread_map]),
        page_size=page_size,
    )


def _withheld_here(observation: Observation, shrunk: Layout) -> tuple[str, ...]:
    """The ids A.9a step 8 withheld out of this thread, for the map's own accounting.

    The expansion path always carries a `map_id`, so every one of `stated_total` positions
    must be a row, a collapsed-run member or a withheld record - and a message step 8 removed
    is the third. Without this the source names two dispositions out of three and
    `Source._a_claimed_map_accounts_for_every_message` refuses the response the server just
    built, which is R-V01-014: a latent refusal that only surfaces once step 8 fires on this
    path. `assemble._ceiling_withheld_here` is the same rule for the search path, and both
    read the one `Layout.withheld_ids` so the two accounts cannot diverge.
    """
    return tuple(sorted(frozenset(shrunk.withheld_ids) & frozenset(observation.thread_map.order)))


def _record_ladder_dispositions(
    layout: Layout,
    *,
    ledger: DispositionLedger,
    builder: EnvelopeBuilder,
    by_thread: Mapping[str, Observation],
    reduced: bool,
) -> None:
    """File every id A.9a's last two steps removed, exactly as `assemble` files them.

    The same cap, the same reason vocabulary and the same executable affordance, because a
    reader must not have to learn a second account of what a token ceiling did depending on
    which tool produced the response.
    """
    # Round 30: only when a ceiling actually bound - see `assemble._a_ceiling_bound`.
    if a_ceiling_bound(layout, reduced=reduced):
        builder.state_the_binding_ceiling(_binding_ceiling(layout))
    for thread_id in layout.split_off:
        observation = by_thread[thread_id]
        affordance = thread_map_affordance(thread_id)
        builder.add_not_included_source(
            NotIncludedSource(
                thread_id=thread_id,
                stated_total=observation.thread_map.stated_total,
                affordance=affordance,
            ),
            why=(
                "A.9a step 7: this source was split off to fit the ceiling stated in omission.bound"
            ),
        )
        builder.add_affordance(affordance)
    # **R-V01-001.** This loop filed every withheld id at message granularity while the shared
    # `_split_off` had charged step-7 ids as groups - the layout said eighteen groups and the
    # wire carried fifty-four records, an under-estimate of up to 21,005 characters and a
    # `terminal: true` refusal for a read that serves at eleven ids. It now files exactly as
    # `assemble._record_ladder_dispositions` does, which is what its docstring always claimed:
    # an id that left inside a split source is thread-granular, carries step 7's reason and
    # the thread's map call (R-V01-012); an id step 8 removed on its own is a record.
    grouped = layout.grouped_ids
    for message_id in sorted(frozenset(layout.withheld_ids)):
        if message_id in grouped:
            ledger.note_withheld(
                message_id=message_id,
                cap=WithheldCap.DISCLOSED_TOKEN_CEILING,
                why=(
                    "A.9a step 7: this source was split off to fit the ceiling stated in "
                    "omission.bound"
                ),
                affordance=thread_map_affordance(_thread_of(ledger, message_id)),
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
    """The thread the ledger observed this id in - `assemble._thread_of`'s rule, one module on."""
    origin = ledger.origins.get(message_id)
    thread_id = origin.thread_id if origin is not None else None
    if thread_id is None:
        raise DispositionInvariantError(
            f"no thread was observed for withheld id {message_id!r}, so this response cannot "
            "say which thread A.9a step 7 split off (R-DISC-009, R-MCP-033)"
        )
    return thread_id


def _binding_ceiling(layout: Layout) -> str:
    """Which ceiling reduced this response - `assemble._binding_ceiling`'s rule, one module on.

    Duplicated in wording nowhere: both call `HOST_CAP_WHY`, which is the one place the
    sentence lives, and both fall back to the same phrase for the token ceiling. A reader must
    not have to learn a second account of what a cap did depending on which tool answered.
    """
    if layout.host_capped:
        return HOST_CAP_WHY.format(cap=HOST_RESULT_CHAR_CAP)
    return "the response reached its declared token ceiling"
