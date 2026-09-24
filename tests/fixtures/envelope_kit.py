"""Minimal valid envelope parts, so a test can vary one thing at a time.

Nothing here asserts anything. It exists so that a test about (say) the OD-2 outcome rule
does not have to restate twenty unrelated fields, and so that the *shape* under test is
built by the production types rather than by a dict the test invented.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from mailweave.envelope import (
    Affordance,
    AskedFor,
    CollapsedRun,
    Content,
    ContentSource,
    Counters,
    Depth,
    EmptyDiagnosis,
    EmptyDiagnosisStatus,
    Linkage,
    MailboxProvenance,
    MessageRow,
    ParsedQuerySummary,
    Role,
    RungId,
    Source,
    ToolName,
    Trust,
)
from mailweave.envelope.disposition import FetchedIds, ObservedEndpoint
from mailweave.envelope.fence import fence
from mailweave.envelope.reasons import GmailQueryMatch, Reason, ThreadMember

FETCHED_AT = "2026-08-30T14:02:11Z"


def _thread_map(
    ids: Sequence[str], thread: str | None, thread_ids: Mapping[str, str] | None
) -> Mapping[str, str] | None:
    """The `threadId` a listing response carried per item, as a fixture states it.

    `thread="t1"` is the common case - every id on this page belongs to one thread - and
    `thread_ids` is how a test says otherwise. Both spell the same fact: what the Gmail
    response said about each id (R-DISC-009). Omitting both leaves the observation with no
    thread for its ids, which is a real state a test may want - those ids can be hits and
    can be disclosed, but they cannot be named in a withheld record.
    """
    if thread_ids is not None:
        return thread_ids
    return dict.fromkeys(ids, thread) if thread is not None else None


def fetched(
    ids: Iterable[str],
    *,
    page_size: int = 100,
    more_pages: bool = False,
    next_page_token: str | None = None,
    thread: str | None = None,
    thread_ids: Mapping[str, str] | None = None,
) -> FetchedIds:
    """A sealed `messages.list` observation, as a transport would hand one to the ledger.

    Tests build these directly because there is no Gmail client yet; the point of the
    seal is that *production* callers cannot read the ids back out, not that an
    observation is hard to construct.

    The endpoint is fixed here rather than defaulted in `FetchedIds` itself: which call
    was executed decides which A.7a clause the ids enter under (amendment A2), so a
    default in production code would be a guess about provenance. In a fixture whose whole
    job is to stand in for one named endpoint it is a statement, and the two sibling
    helpers below are how a test asks for either of the others.
    """
    materialised = list(ids)
    return FetchedIds(
        ids=materialised,
        endpoint=ObservedEndpoint.MESSAGES_LIST,
        page_size=page_size,
        more_pages=more_pages,
        next_page_token=next_page_token,
        thread_ids=_thread_map(materialised, thread, thread_ids),
    )


def history_additions(
    ids: Iterable[str],
    *,
    thread: str | None = None,
    thread_ids: Mapping[str, str] | None = None,
) -> FetchedIds:
    """A sealed `history.list` observation: clause H-hist."""
    materialised = list(ids)
    return FetchedIds(
        ids=materialised,
        endpoint=ObservedEndpoint.HISTORY_LIST,
        thread_ids=_thread_map(materialised, thread, thread_ids),
    )


def observed_thread(
    ids: Iterable[str],
    thread_id: str = "t1",
    *,
    stated_total: int | None = None,
    positions: Mapping[str, int] | None = None,
    internal_dates: Mapping[str, str] | None = None,
    history_id: str | None = None,
    fetched_at: str | None = None,
) -> FetchedIds:
    """A sealed `threads.get` observation: clause H-thr (amendment A2).

    The keyword arguments are amendment A6's named scalars. They are optional here for the
    same reason they are optional on `FetchedIds`: no Gmail client exists yet to supply
    them, and a test that does not care about them should not have to state them. A test
    that *does* care states them, and the envelope then checks the payload against them
    exactly rather than merely bounding it.
    """
    return FetchedIds(
        ids=ids,
        endpoint=ObservedEndpoint.THREADS_GET,
        thread_id=thread_id,
        stated_total=stated_total,
        positions=positions,
        internal_dates=internal_dates,
        history_id=history_id,
        fetched_at=fetched_at,
    )


def fully_observed_thread(
    ids: Sequence[str],
    thread_id: str = "t1",
    *,
    stated_total: int | None = None,
) -> FetchedIds:
    """A `threads.get` observation carrying every named scalar amendment A6 seals.

    Positions are the ids' order in `ids`, which is what "the response's chronological
    message order" means for a fixture, and `internalDate` is a plausible epoch-millisecond
    string per id. This is the shape a real Gmail client will hand the ledger, and it is
    what the A6 tests build so that the derivation is exercised rather than skipped.
    """
    materialised = tuple(ids)
    return observed_thread(
        materialised,
        thread_id,
        stated_total=stated_total if stated_total is not None else len(materialised),
        positions={message_id: index for index, message_id in enumerate(materialised)},
        internal_dates={
            message_id: str(1756557731000 + index * 60_000)
            for index, message_id in enumerate(materialised)
        },
        history_id="99120034",
        fetched_at=FETCHED_AT,
    )


def asked_for(terms: Sequence[str] = ("launch",)) -> AskedFor:
    return AskedFor(
        parsed=ParsedQuerySummary(operators={"from": "amy@x.example"}, terms=tuple(terms)),
        enforced=("from", "terms"),
        dropped=(),
        term_coverage=1.0,
        constraint_drop_depth=0,
    )


def counters(http: int = 3, api: int = 12, quota: int = 480) -> Counters:
    return Counters(http_requests=http, api_calls=api, quota_units=quota)


def query_reason(query: str = "from:amy launch", rung: RungId = RungId.L1) -> Reason:
    return GmailQueryMatch(query=query, rung=rung)


def stub_reason(thread_id: str, position: int) -> Reason:
    return ThreadMember(thread_id=thread_id, position=position)


def unabridged(message_id: str) -> Affordance:
    return Affordance(
        tool=ToolName.GET_MESSAGES,
        args={"message_ids": [message_id], "view": "body_full"},
    )


def thread_affordance(thread_id: str) -> Affordance:
    return Affordance(tool=ToolName.THREAD_MAP, args={"thread_id": thread_id})


def row(
    message_id: str,
    thread_id: str,
    position: int,
    *,
    nonce: str,
    depth: Depth = Depth.BODY_CLEAN,
    role: Role = Role.MATCHED,
    text: str = "synthetic body text",
    reason: Reason | None = None,
    labels: tuple[str, ...] | None = ("INBOX",),
    linkage: Linkage = Linkage.HEADERS_UNOBSERVED,
    reply_parent_id: str | None = None,
    #: `None` is the third state, and it is the default here because `linkage` defaults to
    #: `HEADERS_UNOBSERVED` - `MessageRow` holds the two to each other (R-RETR-054), so a
    #: caller that passes any other linkage must say whether that message can be named.
    can_be_a_parent: bool | None = None,
) -> MessageRow:
    # `thread_id` is still a parameter of this helper, and no longer a parameter of
    # `MessageRow`: it is what a stub row's `ThreadMember` reason renders, and `Source`
    # writes the row's wire `thread_id` from its own (R-DISC-011).
    content = (
        None
        if depth is Depth.STUB
        else Content(
            trust=Trust.UNTRUSTED_THIRD_PARTY,
            source=ContentSource.GMAIL_BODY,
            text=fence(nonce, text),
        )
    )
    return MessageRow(
        id=message_id,
        position=position,
        role=role,
        reason=reason
        or (stub_reason(thread_id, position) if depth is Depth.STUB else query_reason()),
        mailbox=(
            MailboxProvenance.unobserved() if labels is None else MailboxProvenance.of(labels)
        ),
        depth=depth,
        linkage=linkage,
        reply_parent_id=reply_parent_id,
        can_be_a_parent=can_be_a_parent,
        unabridged=unabridged(message_id),
        content=content,
    )


def source(
    thread_id: str,
    rows: Iterable[MessageRow],
    *,
    stated_total: int | None = None,
    collapsed_runs: Sequence[CollapsedRun] = (),
) -> Source:
    materialised = tuple(rows)
    collapsed_members = sum(len(run.member_ids) for run in collapsed_runs)
    included = len(materialised) + collapsed_members
    stubs = sum(1 for r in materialised if r.depth is Depth.STUB) + collapsed_members
    return Source(
        thread_id=thread_id,
        stated_total=stated_total if stated_total is not None else included,
        included=included,
        included_as_stub=stubs,
        fetched_at=FETCHED_AT,
        messages=materialised,
        collapsed_runs=tuple(collapsed_runs),
    )


def collapsed_run(start: int, member_ids: Sequence[str], thread_id: str) -> CollapsedRun:
    members = tuple(member_ids)
    return CollapsedRun(
        positions=(start, start + len(members) - 1),
        count=len(members),
        member_ids=members,
        why="disclosed_token_ceiling",
        affordance=Affordance(
            tool=ToolName.THREAD_MAP, args={"thread_id": thread_id, "segment": 2}
        ),
    )


def empty_diagnosis_complete() -> EmptyDiagnosis:
    return EmptyDiagnosis(
        status=EmptyDiagnosisStatus.COMPLETE,
        tried=("from", "after"),
        untried_drops=(),
        restores=None,
    )
