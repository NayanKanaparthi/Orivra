"""`GmailAdapter`: the adapter boundary over the MailWeave stack that already ships.

**Nothing in `mailweave` is renamed, moved or altered by this file.** It imports the public
surfaces v0.1 froze and calls them; where it needs a fact MailWeave already computes, it
reads MailWeave's own structured payload rather than recomputing it. Every method maps as
plan §2.1 says it does:

| method | what it calls |
|---|---|
| `translate` | `mailweave.query.operators`' operator vocabulary |
| `rungs` | `mailweave.retrieval.ladder.LADDER` |
| `search` | `LadderRunner`, which is the ladder's `messages.list` path |
| `container` | `mailweave_thread_map`'s structured payload |
| `items` | `mailweave.content.pipeline.process_message` |
| `changes_since` | `GmailClient.history_additions`, plus D.9's declared 404 re-baseline |
| `version_of` | `(message id, historyId)` |
| `permission_context` | the granted scope set read back at startup |

**One method the plan's protocol does not list, and why.** `answer` runs a whole query and
hands back MailWeave's own `Envelope`. The alternative - having `orivra_ask` compose
`translate`, `search`, `container` and `items` itself - would mean a second implementation of
the ladder, the A.9a disclosure ladder and the envelope builder running beside the first.
Two implementations of one retrieval are two answers to one question, and M1's whole
demonstration is that the two paths agree; a divergence the test is supposed to *detect*
should not be one the design *builds in*. So the Gmail adapter delegates, and Orivra's
response carries MailWeave's container verbatim. A source with no retrieval stack of its own
(Drive, Slack) will compose `answer` from the primitives instead, which is the case that
made the method worth having on the protocol rather than only here.

**The `mailweave_*` tools never come through here.** They keep calling `MailweaveService`
directly with v0.1's defaults, `MAX_SERVER_MS = 7,700` included.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from mailweave.content.payload import MessagePayload
from mailweave.content.pipeline import process_message
from mailweave.envelope.disposition import DispositionLedger
from mailweave.envelope.fence import unfence
from mailweave.envelope.reasons import RequestedById, ThreadMember
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import Depth, Role, WithheldCap
from mailweave.envelope.wire import (
    Affordance,
    CollapsedRun,
    MessageRow,
    Source,
    WithheldGroup,
    WithheldRecord,
    WithheldTail,
)
from mailweave.errors import ContentProcessingError
from mailweave.gmail.client import LivenessProbe
from mailweave.gmail.models import Message
from mailweave.gmail.rates import PUBLISHED_QUOTA_UNITS, GmailEndpoint
from mailweave.policy.budget import BudgetAccountant, BudgetRequest, apply_floor
from mailweave.query.operators import OperatorName
from mailweave.retrieval.ladder import LADDER, LadderRunner
from mailweave.surface.arguments import SearchRequest, ThreadMapRequest
from mailweave.surface.service import MailweaveService
from orivra.adapter import (
    AdapterCapabilities,
    AdapterResult,
    CacheOutcome,
    ChangeSet,
    ContainerMap,
    Hits,
    NativeQuery,
    QueryFacts,
    Resync,
    RungSpec,
)
from orivra.cache import (
    BoundedCache,
    Revalidation,
    RevalidationReason,
    structure_key,
)
from orivra.contracts import (
    REDACTION_POLICY,
    ChangeMarker,
    ConnectorId,
    ContentVersion,
    DerivationMethod,
    Dimension,
    EvidenceNode,
    ExpansionHandle,
    FreshnessState,
    FreshnessStatus,
    Granularity,
    NodeKind,
    OmissionCause,
    OmissionRecord,
    OrivraToolName,
    PermissionContext,
    RefKind,
    SourceReference,
    SourceSpend,
    SourceState,
    Timestamps,
)

#: The depths that need a body fetched for them. The same set `surface/service` uses, by
#: the same name, so "which depths cost a full read" is one fact and not two.
#:
#: `RAW` is here as well as MailWeave's two: it is the fullest depth, and leaving it out - as
#: the first draft did - silently degraded a request for it to metadata (R-M1-017). `RAW` is
#: never disclosed inline on the MailWeave surface (contract R-04), and this method is not
#: that surface; a caller that asks for it here gets the full body it asked for.
_NEEDS_BODY: frozenset[Depth] = frozenset({Depth.BODY_CLEAN, Depth.BODY_FULL, Depth.RAW})

#: Gmail's own container is the thread, and nothing else here is one.
CONTAINER_KIND = "thread"

#: Gmail has no batch `messages.get`, so an id list is a list of sequential calls. The
#: figure is MailWeave's own retry batch cap, reused so the two do not drift apart.
MAX_IDS_PER_FETCH = 50

#: The operators `translate` will actually emit. **Not** the operators Gmail documents -
#: the ones this code produces - so a trace can be read against this tuple and a query
#: carrying anything else is a query something other than `translate` built.
EMITTED_OPERATORS: tuple[str, ...] = (
    OperatorName.FROM.value,
    OperatorName.TO.value,
    OperatorName.AFTER.value,
    OperatorName.BEFORE.value,
    OperatorName.RFC822MSGID.value,
)


def _quote(phrase: str) -> str:
    """A phrase as Gmail's own quoted form, with an embedded quote refused rather than
    escaped - Gmail has no documented escape for one, so escaping it would be inventing
    syntax and the honest outcome is that the phrase is unrepresentable."""
    return f'"{phrase}"'


@dataclass(frozen=True)
class GmailAdapter:
    """One authorised Gmail mailbox, behind the source-independent seam.

    `service` is the *same* `MailweaveService` the `mailweave_*` tools use - held by
    reference, not re-created - so there is exactly one authorised mailbox in the process
    and one place that decides what may be spent against it.
    """

    service: MailweaveService
    granted_scopes: tuple[str, ...]
    connector: ConnectorId = ConnectorId.GMAIL
    #: The bounded cache this adapter may serve **structure** from (plan §5.1's cached
    #: category, §5.4's key). `None` means no caching at all, which is the honest default: a
    #: cache that appears by itself is a cache nobody decided to have. `orivra serve` supplies
    #: one; a test that does not want one simply omits it.
    #:
    #: **Nothing with body text is ever put here.** A thread map returns rows at `stub` depth,
    #: which is why this kind is cacheable at all, and `_cacheable` refuses an entry whose
    #: nodes carry content rather than trusting that to stay true.
    cache: BoundedCache | None = None
    #: The last `historyId` this adapter observed for each container, by native id.
    #:
    #: **Why an index rather than reading it off the graph.** `orivra_expand` used to take the
    #: revision from the thread node in the stored graph, which works only when the branch
    #: being expanded is *in* that graph. The branches a caller actually follows are the ones
    #: the answer left out - a source split off at the ceiling has no node at all - so the
    #: lookup returned `None`, the cache was never consulted, and every round re-read the
    #: thread. That is the defect the Harbor run recorded as "threads.get every round".
    #:
    #: A remembered revision is **not** a licence to serve: it supplies the key, and
    #: `liveness_of_threads` still has to walk `history.list` and come back conclusive and
    #: unchanged before an entry is served. A stale remembered revision therefore costs a walk
    #: and a miss, never a wrong answer.
    observed_revisions: dict[str, str] = field(default_factory=dict, repr=False)

    # -- capabilities and vocabulary ----------------------------------------------------

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            connector=ConnectorId.GMAIL,
            native_search=True,
            search_operators=EMITTED_OPERATORS,
            container_kind=CONTAINER_KIND,
            revisions=False,
            change_feed="history",
            max_ids_per_fetch=MAX_IDS_PER_FETCH,
        )

    def rungs(self) -> tuple[RungSpec, ...]:
        """This source's lexical ladder, read off `LADDER` rather than restated.

        Read off, because a ladder listed twice is a ladder that will be edited once. The
        commonality test in `tests/test_exact_signal_match.py` reads the same tuple by name
        and by count for the same reason.
        """
        return tuple(
            RungSpec(
                rung_id=rung.rung.value,
                why=(rung.__doc__ or "").strip().splitlines()[0] if rung.__doc__ else "",
                widens=rung.rung.value in {"L3", "L4", "L5"},
            )
            for rung in LADDER
        )

    def translate(self, facts: QueryFacts) -> NativeQuery:
        """Source-independent facts as one Gmail `q`.

        Everything `QueryFacts` can hold has a Gmail operator, with one exception that is
        recorded rather than dropped: a phrase containing a double quote. Gmail documents no
        escape for one inside a quoted phrase, so inventing an escape here would be inventing
        syntax - the phrase goes into `unrepresentable` and the response declares the
        narrowing.
        """
        parts: list[str] = []
        unrepresentable: list[str] = []
        for phrase in facts.phrases:
            if '"' in phrase:
                unrepresentable.append(f"phrase:{phrase}")
                continue
            parts.append(_quote(phrase))
        for phrase in facts.excluded_phrases:
            if '"' in phrase:
                unrepresentable.append(f"-phrase:{phrase}")
                continue
            parts.append(f"-{_quote(phrase)}")
        parts.extend(facts.terms)
        parts.extend(f"{OperatorName.FROM.value}:{who}" for who in facts.participants)
        # **`to:` is emitted, or it is not published.** `EMITTED_OPERATORS` listed it and
        # nothing produced it, so `orivra_sources` told a planner a recipient constraint was
        # expressible and `translate` turned every participant into a sender filter
        # (review finding R-M1-019).
        parts.extend(f"{OperatorName.TO.value}:{who}" for who in facts.recipients)
        if facts.after:
            parts.append(f"{OperatorName.AFTER.value}:{facts.after}")
        if facts.before:
            parts.append(f"{OperatorName.BEFORE.value}:{facts.before}")
        parts.extend(f"{OperatorName.RFC822MSGID.value}:{one}" for one in facts.identifiers)
        query = " ".join(part for part in parts if part) or facts.text
        return NativeQuery(
            connector=ConnectorId.GMAIL,
            query=query,
            unrepresentable=tuple(unrepresentable),
        )

    # -- retrieval ----------------------------------------------------------------------

    def answer(self, request: SearchRequest, *, host_chars: int | None = None) -> AdapterResult:
        """A whole query, delegated. See the module docstring for why this exists.

        The envelope that comes back is **MailWeave's own**, built by MailWeave's builder,
        measured against MailWeave's ceilings and sealed by MailWeave's certificate. Orivra
        does not rebuild it, re-measure it or re-order it; it carries it.

        `host_chars` is the one thing Orivra may say about how it is built, and it says only
        *how much room there is*, never what to put in it. The ladder still decides which rungs
        to run, which view to serve and what to account for; it is told the size of the space,
        which is a fact it could not otherwise know, because the response it is building is
        about to be carried inside a larger one. `None` leaves MailWeave's own ceilings exactly
        as the legacy path has them.
        """
        envelope = self.service.search(request, host_chars=host_chars)
        nodes = tuple(
            node for source in envelope.sources for node in self._nodes_of(source, envelope)
        )
        self._remember_revisions(envelope)
        return AdapterResult(
            connector=ConnectorId.GMAIL,
            envelope=envelope,
            nodes=nodes,
            omissions=self._omissions_of(envelope),
            spend=self._spend_of(envelope),
        )

    def _remember_revisions(self, envelope: Envelope) -> None:
        """Record every container revision this response observed, whatever became of it.

        **Every one, including the sources that were omitted.** Those are exactly the threads a
        caller goes on to expand - a source split off at the ceiling leaves an omission record
        with a handle and no node - so an index built only from the sources that survived into
        the graph would be empty for precisely the branches that get followed.

        The seal is the source of truth (amendment A6): `observed_thread_facts` is where the
        `historyId` of the `threads.get` that produced these rows lives.
        """
        for thread_id, fact in envelope.disposition.observed_thread_facts.items():
            revision = getattr(fact, "history_id", None)
            if revision:
                self.observed_revisions[thread_id] = revision

    def answer_thread_map(
        self, request: ThreadMapRequest, *, known_revision: str | None = None
    ) -> AdapterResult:
        """One thread, whole, as evidence nodes - the expansion half of `answer`.

        The same shape and the same builders, because an expansion that produced nodes a
        different way would produce nodes that could not be merged with the ones the answer
        built: two readers of one response, disagreeing about a row's depth or its reason,
        and the merge would see a conflict where there is none.

        **`known_revision` is the key, and the caller supplies it or this adapter remembers
        it.** It is the thread's `historyId` as it was last observed. `orivra_expand` reads it
        off the thread node when the graph holds one; when it does not - which is the usual
        case, because the branches a caller follows are the ones the answer *omitted* -
        `observed_revisions` supplies it from the response that produced the omission.

        A remembered revision is not a licence to serve. It only decides which key is looked
        up; `liveness_of_threads` still has to come back conclusive and unchanged, and a
        revision that has moved costs one walk and a miss rather than a wrong answer.
        """
        revision = known_revision or self.observed_revisions.get(request.thread_id or "")
        served, outcome = self._cached_thread_map(request, revision, supplied=known_revision)
        if served is not None:
            return served
        envelope = self.service.thread_map(request)
        nodes = tuple(
            node for source in envelope.sources for node in self._nodes_of(source, envelope)
        )
        result = AdapterResult(
            connector=ConnectorId.GMAIL,
            envelope=envelope,
            nodes=nodes,
            omissions=self._omissions_of(envelope),
            spend=self._spend_of(envelope),
            cache=outcome,
        )
        self._remember_thread_map(result)
        self._remember_revisions(envelope)
        return result

    # -- the bounded cache, on the one path where its revalidation is independent ---------

    def _cached_thread_map(
        self, request: ThreadMapRequest, known_revision: str | None, *, supplied: str | None
    ) -> tuple[AdapterResult | None, CacheOutcome]:
        """A cached structure entry, or `None` and a fresh read.

        **The revalidation reads a different resource from the one the cache holds**, which is
        ADV-002's rule and the reason this seat is safe: the entry is a `threads.get`, and
        `liveness_of_threads` walks `history.list`. A cache hit cannot make the check pass,
        because the check never looks at the cache.

        The asymmetry is `LivenessProbe`'s own (amendment A10): a walk that **saw** a change
        has established one whatever it did not read, and only the *negative* answer needs a
        conclusive walk. So an entry serves on `conclusive and not saw_a_change`, and both an
        observed change and an inconclusive walk send this back to the source. An expired
        watermark or a walk that ran out of pages is "could not tell", which §5.3 is explicit
        is not a licence to serve.
        """
        if self.cache is None:
            return None, CacheOutcome(
                consulted=False,
                outcome="no_cache",
                reason="not_applicable",
                why="this adapter was built without a cache, so nothing was looked up",
            )
        thread_id = request.thread_id
        if not thread_id:
            # A map addressed by `map_id` is a handle redemption, and MailWeave's own
            # thread-map LRU already governs that path with this same probe. A second cache
            # over it would be two caches with two eviction rules for one resource.
            return None, CacheOutcome(
                consulted=False,
                outcome="not_addressable",
                reason="not_applicable",
                why=(
                    "this map is addressed by map_id, which is a handle redemption; "
                    "MailWeave's own thread-map LRU governs that path with the same probe"
                ),
            )
        if known_revision is None:
            # **The miss the Harbor run recorded, named rather than inferred.** No revision for
            # this container has ever been observed by this process, so there is no
            # `content_version` to key on and no lookup to make. Distinct from a lookup that
            # happened and found nothing: that one is the cache working.
            return None, CacheOutcome(
                consulted=False,
                outcome="no_revision",
                reason="not_applicable",
                why=(
                    f"no historyId has been observed for {thread_id} in this process, so there "
                    "is no content_version to key on. The cache was not consulted"
                ),
            )
        key = structure_key(
            principal=self.service.account_hash,
            connector=ConnectorId.GMAIL.value,
            native_id=thread_id,
            revision=known_revision,
            permission_hash=self.permission_context().hash,
            redaction_policy=REDACTION_POLICY,
        )
        walks: list[LivenessProbe] = []
        read = self.cache.get(
            key, revalidate=lambda _: self._unchanged(thread_id, known_revision, walks)
        )
        source = "the caller's graph" if supplied else "this adapter's observed-revision index"
        if not read.usable:
            if read.rebaseline:
                # **Drop the watermark, not the entry.** An expired `startHistoryId` means this
                # revision can never be walked from again, so keeping it would make every
                # future expansion of this thread pay for a walk that 404s before falling back.
                # The fresh read below re-learns a current one through `_remember_revisions`.
                self.observed_revisions.pop(thread_id, None)
            return None, CacheOutcome(
                consulted=True,
                outcome=read.outcome.value,
                reason=read.reason.value,
                rebaselined=read.rebaseline,
                why=f"keyed on a revision from {source}; {read.why}",
            )
        held: AdapterResult = read.value
        # **Restamped from the revalidation route, not from the original read.** `_fresh` says
        # this is where that lands. The envelope keeps its own `fetched_at` - the instant the
        # content was read - and the node's `verified_at` is the instant this probe confirmed
        # it had not moved. Two facts, both true; rewriting the first would assert a freshness
        # this response does not have.
        verified = FreshnessStatus(verified_at=self.service.now(), state=FreshnessState.FRESH)
        return AdapterResult(
            connector=ConnectorId.GMAIL,
            envelope=held.envelope,
            nodes=tuple(node.model_copy(update={"freshness": verified}) for node in held.nodes),
            omissions=held.omissions,
            # **Not the original read's spend.** Re-reporting it would claim API calls this
            # call did not make, which is the accounting equivalent of restamping `fetched_at`.
            # What this call spent is the liveness probe, and that is what it says.
            spend=self._probe_spend(walks[-1] if walks else None),
            cache=CacheOutcome(
                consulted=True,
                outcome="hit",
                reason=read.reason.value,
                why=f"keyed on a revision from {source}; {read.why}",
            ),
        ), CacheOutcome(
            consulted=True,
            outcome="hit",
            reason=read.reason.value,
            why=f"keyed on a revision from {source}; {read.why}",
        )

    def _remember_thread_map(self, result: AdapterResult) -> None:
        """Write the structure entry, keyed on the revision the fetch actually observed.

        On the revision the *fetch* saw, never the caller's guess: a miss happens precisely
        when the two differ, and keying the new entry on the stale guess would write an entry
        that can never be hit and would shadow nothing.
        """
        if self.cache is None:
            return
        for node in result.nodes:
            if node.kind is not NodeKind.THREAD:
                continue
            revision = node.ref.version.revision
            if not revision:
                # No revision, no key dimension, no entry. A structure entry with nothing in
                # `content_version` is one that survives every change to the thread.
                return
            if not self._cacheable(result.nodes):
                return
            self.cache.put(
                structure_key(
                    principal=self.service.account_hash,
                    connector=ConnectorId.GMAIL.value,
                    native_id=node.ref.native_id,
                    revision=revision,
                    permission_hash=node.ref.permission.hash,
                    redaction_policy=REDACTION_POLICY,
                ),
                result,
            )
            return

    @staticmethod
    def _cacheable(nodes: Sequence[EvidenceNode]) -> bool:
        """No body text goes in the cache, checked rather than assumed (plan §5.1).

        A thread map returns rows at `stub` depth, so this holds today by construction. It is
        asserted anyway because the day it stops holding is the day a depth default changes
        somewhere else entirely, and the failure would be message text in a store whose whole
        safety argument is that it has none.
        """
        return not any(node.content for node in nodes)

    def _unchanged(self, thread_id: str, revision: str, walks: list[LivenessProbe]) -> Revalidation:
        """Has anything touched this thread since `revision`? `history.list`, not the cache.

        **Four answers, not two**, and which one it is decides what the caller should do next:

        * the walk finished and saw nothing - serve;
        * the walk **saw a change** - a positive finding is conclusive whatever the walk did
          not read (amendment A10), so this is a definite no and the counts say what moved;
        * Gmail 404'd the `startHistoryId` - the watermark is older than Gmail retains ([RO
          F6]), so this walk cannot be made to work and the *watermark* is what has to be
          re-baselined. Retrying it is the one thing that certainly will not help;
        * the walk stopped with pages outstanding - it could not establish that nothing
          changed, which is a third thing again.

        All four used to reduce to `False`, and the cache's one sentence for `False` said the
        caller's access had changed. A live run whose history walk simply could not finish was
        told its permissions had moved.

        The probe is kept in `walks` because what it cost is part of what this call cost, and a
        served entry that reported the original fetch's spend would be claiming API calls
        nobody made on this call.
        """
        client = self.service.client_for_call()
        probe = client.liveness_of_threads(since={thread_id: revision}, start_history_id=revision)
        walks.append(probe)
        if probe.saw_a_change:
            change = probe.touched.get(thread_id)
            moved = change.rendered() if change is not None else "a change this walk observed"
            return Revalidation(
                ok=False,
                reason=RevalidationReason.CHANGED,
                detail=(
                    f"the change feed saw this thread move since historyId {revision}: {moved}. "
                    "The stored structure is no longer this thread's, so it is re-read rather "
                    "than served"
                ),
            )
        if probe.expired:
            return Revalidation(
                ok=False,
                reason=RevalidationReason.WATERMARK_EXPIRED,
                detail=(
                    f"Gmail no longer retains history from historyId {revision}, so the feed "
                    "cannot be walked from it. This says nothing about whether the thread "
                    "changed; the watermark is what is stale, and it is re-baselined from the "
                    "fresh read this call now makes"
                ),
            )
        if probe.pages_exhausted:
            return Revalidation(
                ok=False,
                reason=RevalidationReason.INCONCLUSIVE,
                detail=(
                    f"the history walk stopped with pages outstanding after "
                    f"{probe.pages_fetched} page(s), so it did not establish that nothing "
                    "changed. Not a change, and not a clean bill either"
                ),
            )
        return Revalidation(
            ok=True,
            reason=RevalidationReason.UNCHANGED,
            detail=(
                f"a {probe.pages_fetched}-page history walk from historyId {revision} found "
                "nothing touching this thread"
            ),
        )

    def _probe_spend(self, probe: LivenessProbe | None) -> SourceSpend:
        """What a served entry cost: the `history.list` walk that revalidated it.

        Read off the walk rather than assumed to be one call: a probe that paged spent more
        than a probe that did not, and the published rate table turns pages into units so this
        module does not carry a second copy of a cost it does not own.

        `rungs_executed` is empty because no rung ran. The ladder is what spends against a
        query, and this call answered from a store; naming a rung here would put a retrieval
        step in a trace that never executed one.
        """
        pages = 0 if probe is None else probe.pages_fetched
        return SourceSpend(
            connector=ConnectorId.GMAIL,
            state=SourceState.READY,
            rungs_executed=(),
            hits=0,
            api_calls_by_method={"total": pages},
            quota_units=pages * PUBLISHED_QUOTA_UNITS[GmailEndpoint.HISTORY_LIST],
            caps_hit=(),
        )

    def search(self, native: NativeQuery, *, max_ids: int = MAX_IDS_PER_FETCH) -> Hits:
        """Ids only, from the lexical ladder. **Every id returned has entered `H`.**

        The ledger is constructed here and discarded, which is correct for this method and
        would be wrong for `answer`: this returns ids for a caller that will do its own
        accounting, and `answer` returns a sealed envelope whose ledger had to outlive the
        run. `LadderRunner`'s own docstring makes the same point from the other side.
        """
        if native.connector is not ConnectorId.GMAIL:
            raise ValueError(
                f"a {native.connector.value} query reached the Gmail adapter; a translation "
                "is one source's syntax and running it against another is how an after: "
                "ends up in a Slack request"
            )
        client = self.service.client_for_call()
        ledger = DispositionLedger()
        budget = apply_floor(BudgetRequest())
        accountant = BudgetAccountant(
            client.meter, budget, now_ms=self.service.clock_ms, query=native.query
        )
        run = LadderRunner(client, ledger, accountant=accountant).run(
            native.query, now=self.service.now()
        )
        ids = tuple(sorted(ledger.hit_ids))[:max_ids]
        # An origin whose thread the observation did not state is not given a placeholder:
        # a container id invented here would be a thread this call never saw, and the
        # honest answer is that this id has no container in `H` yet.
        containers = tuple(
            sorted(
                {
                    origin.thread_id
                    for origin in ledger.origins.values()
                    if origin.thread_id is not None
                }
            )
        )
        return Hits(
            ids=ids,
            container_ids=containers,
            truncated=len(ledger.hit_ids) > len(ids),
            rungs_executed=tuple(rung.value for rung in run.rungs_run),
        )

    def container(self, ref: SourceReference) -> ContainerMap:
        """One thread, from `mailweave_thread_map`'s **structured payload**.

        Read from the structured payload and never from the text mirror - which closes
        R-DEMO-001 and R-DEMO-004 by construction here rather than by remembering to do it
        in each demo script.
        """
        if ref.kind is not RefKind.THREAD:
            raise ValueError(
                f"Gmail's container is a thread and this reference is a {ref.kind.value}; "
                "asking a message for its members would produce a container of one"
            )
        envelope = self.service.thread_map(
            ThreadMapRequest(thread_id=ref.native_id, map_id=None, segment=None)
        )
        source = next((one for one in envelope.sources if one.thread_id == ref.native_id), None)
        if source is None:
            raise ValueError(
                f"the thread map for {ref.native_id} carries no source for that thread; a "
                "container built from a response that does not describe it would state a "
                "membership nothing observed"
            )
        # **Collapsed runs are members** (review finding R-M1-005). `source.messages` holds
        # only the rows the disclosure ladder disclosed; a thread it compacted has its
        # members in `collapsed_runs` instead, and reading `messages` alone returned a
        # container of eighty with no members and no way to ask for more. A run carries its
        # `member_ids` on the wire precisely so a reader can compute the set from the
        # response alone, which is what this does.
        positions = {row.id: row.position for row in source.messages}
        members = [row.id for row in source.messages]
        for run in source.collapsed_runs:
            start, _end = run.positions
            for offset, message_id in enumerate(run.member_ids):
                if message_id in positions:
                    continue
                positions[message_id] = start + offset
                members.append(message_id)
        return ContainerMap(
            ref=ref,
            member_ids=tuple(sorted(members, key=lambda one: positions[one])),
            stated_total=source.stated_total,
            positions=positions,
        )

    def items(
        self, refs: Sequence[SourceReference], *, depth: str = Depth.BODY_CLEAN.value
    ) -> tuple[EvidenceNode, ...]:
        """The named messages, through the content pipeline, as evidence nodes.

        A body that the pipeline refuses is not a failed call: it is a message with no
        readable text, which comes back at a shallower depth. That is `surface/service`'s own
        rule (`_process` returns `None` and `depth_for` lowers the depth), kept identical
        here so the two paths cannot disagree about what a body is.
        """
        wanted = Depth(depth)
        client = self.service.client_for_call()
        built: list[EvidenceNode] = []
        for ref in refs[:MAX_IDS_PER_FETCH]:
            message = client.get_message(
                ref.native_id,
                message_format=("full" if wanted in _NEEDS_BODY else "metadata"),
            )
            if wanted is Depth.STUB:
                # **Stub is the depth that says no text is here** (`nodes.py`). Returning a
                # snippet for it and raising the declared depth - which the first draft did -
                # discloses text no ceiling measured (review finding R-M1-017).
                built.append(self._node_at(ref, message, Depth.STUB, None))
                continue
            text = self._body_of(message) if wanted in _NEEDS_BODY else None
            reached: Depth = wanted
            if text is None:
                # **A depth is a statement about text that is here.** A body the pipeline
                # refused, or one this format never fetched, lowers the declared depth
                # rather than leaving a claim with nothing behind it - which is
                # `surface/service._process`'s own rule, kept identical so the two paths
                # cannot disagree about what a body is.
                text = message.snippet or None
                reached = Depth.SNIPPET if text else Depth.STUB
            built.append(self._node_at(ref, message, reached, text))
        return tuple(built)

    def _node_at(
        self, ref: SourceReference, message: Message, depth: Depth, text: str | None
    ) -> EvidenceNode:
        return EvidenceNode(
            node_id=ref.node_id,
            ref=ref,
            kind=NodeKind.MESSAGE,
            role=Role.REQUESTED,
            reason=RequestedById(requested_id=ref.native_id),
            depth=depth,
            content=text,
            freshness=self._fresh(),
            timestamps=_timestamps(message.internal_date),
        )

    @staticmethod
    def _body_of(message: Message) -> str | None:
        """One message's default body view, or `None` if there is no readable text.

        `default_view` is amendment A7's `original` spans only, which is the same string the
        disclosure layer budgets against - so a node built here and a row built by
        `assemble` carry the same text for the same message.
        """
        if message.payload is None:
            return None
        try:
            processed = process_message(
                MessagePayload.model_validate(
                    {
                        "id": message.id,
                        "threadId": message.thread_id,
                        "internalDate": message.internal_date,
                        "snippet": message.snippet or "",
                        "payload": message.payload,
                    }
                )
            )
        except ContentProcessingError:
            return None
        return processed.default_view or None

    # -- freshness, versions, permission -------------------------------------------------

    def changes_since(self, marker: ChangeMarker) -> ChangeSet | Resync:
        """`history.list` from a watermark, or D.9's **declared** re-baseline.

        A 404 is not a failure and is not raised: AD D.9 says an expired `startHistoryId`
        means the watermark is older than Gmail's retention, and the answer is a declared
        full re-read. `Resync` is that declaration in the adapter's own vocabulary.
        """
        if marker.connector is not ConnectorId.GMAIL:
            raise ValueError(
                f"a {marker.connector.value} marker reached the Gmail adapter's change feed"
            )
        if marker.marker is None:  # pragma: no cover - ChangeMarker refuses this already
            raise ValueError("a Gmail change marker carries a historyId")
        client = self.service.client_for_call()
        ledger = DispositionLedger()
        run = client.history_additions(ledger, start_history_id=marker.marker)
        if run.rebaseline_required:
            return Resync(
                why=(
                    "Gmail answered history.list with 404: the watermark is older than "
                    "Gmail's history retention, so the only correct answer is a full "
                    "re-read, declared rather than performed silently (AD D.9)"
                ),
                connector=ConnectorId.GMAIL,
            )
        return ChangeSet(
            added=tuple(sorted(ledger.hit_ids)),
            changed=(),
            removed=(),
            marker=ChangeMarker(
                connector=ConnectorId.GMAIL,
                marker=run.latest_history_id or marker.marker,
            ),
        )

    def version_of(self, ref: SourceReference) -> ContentVersion:
        """`(message id, historyId)`.

        **The message's `historyId`, not the mailbox's.** This read
        `client.get_profile().history_id` until a review pointed out that it is the mailbox
        watermark: every message in the account came back with the same revision, so no
        version could distinguish "this message's view changed" from "something else in the
        mailbox did", and at M2 every cached entry in the account would be invalidated by any
        unrelated event. It also cost a second API call for a value the first call already
        returned.

        Gmail message content is immutable, so the `historyId` moves only when the mailbox's
        view of the message changes - a label, most often. That is still a change worth
        invalidating a cache on, because a label is what `mailbox` provenance is computed
        from (OD-5).
        """
        client = self.service.client_for_call()
        message = client.get_message(ref.native_id, message_format="metadata")
        return ContentVersion(
            connector=ConnectorId.GMAIL,
            native_id=message.id,
            revision=message.history_id,
        )

    def permission_context(self, ref: SourceReference | None = None) -> PermissionContext:
        """One account, one granted scope set, read back after consent.

        The *granted* set, never the requested one: `auth/consent.py` reads it back at
        startup precisely because a request for `gmail.readonly` that was granted something
        narrower must not produce a context claiming the wider scope.
        """
        del ref  # Gmail's grant is per account, not per item.
        return PermissionContext(
            connector=ConnectorId.GMAIL,
            principal=self.service.account_hash,
            scope_set=tuple(sorted(set(self.granted_scopes))),
            observed_at=self.service.now(),
        )

    # -- translation of MailWeave's payload into Orivra's contracts ----------------------

    def reference(
        self, native_id: str, *, kind: RefKind = RefKind.MESSAGE, revision: str | None = None
    ) -> SourceReference:
        """One reference, optionally stamped with the revision the response observed.

        **`revision` is what makes a later freshness check mean anything** (2026-09-18). Every
        reference used to carry a `ContentVersion` with no revision at all, so when the graph
        was re-verified on disclosure there was nothing to compare against: `version_of` would
        return the current `historyId`, the stored side was `None`, and the node was reported
        `FRESH` however far the source had moved. A freshness check with nothing to check is
        worse than none, because it reports a verification that did not happen.

        It is taken from the response's own certificate rather than fetched, so stamping it
        costs no call: the thread's `historyId` is a fact of the `threads.get` that returned
        the rows, recorded by amendment A6.
        """
        return SourceReference(
            connector=ConnectorId.GMAIL,
            account=self.service.account_hash,
            kind=kind,
            native_id=native_id,
            version=ContentVersion(
                connector=ConnectorId.GMAIL, native_id=native_id, revision=revision
            ),
            permission=self.permission_context(),
        )

    def _fresh(self) -> FreshnessStatus:
        """Fresh, because it was just read from the source in this call.

        Nothing here is served from a cache in M1 - there is no Orivra cache yet - so the
        only state this can honestly be is `FRESH`. When M2 adds the cache, the state comes
        from the revalidation route instead, and this method is where that lands.
        """
        return FreshnessStatus(verified_at=self.service.now(), state=FreshnessState.FRESH)

    def _nodes_of(self, source: Source, envelope: Envelope) -> tuple[EvidenceNode, ...]:
        """One `Source`'s rows as evidence nodes: the container, then its messages.

        `internalDate` comes off the **certificate**, which is where amendment A6 put it -
        a row's copy was a caller assertion about a fact of a Gmail response, and the seal
        records it now. Reading it from anywhere else would reintroduce the second copy A6
        removed.
        """
        dates = envelope.disposition.observed_internal_dates
        # The thread's `historyId` as the certificate recorded it (A6). Read from the
        # disposition rather than from the wire form, because the wire carries it only as a
        # rendered field and the seal is where the fact lives - the same reason
        # `internal_date` is read from there two lines down.
        observed = envelope.disposition.observed_thread_facts.get(source.thread_id)
        observed_revision = None if observed is None else observed.history_id
        container = EvidenceNode(
            node_id=f"gmail/thread/{source.thread_id}",
            ref=self.reference(source.thread_id, kind=RefKind.THREAD, revision=observed_revision),
            kind=NodeKind.THREAD,
            role=Role.CONTEXT,
            reason=ThreadMember(thread_id=source.thread_id, position=0),
            depth=Depth.STUB,
            stated_total=source.stated_total,
            included=source.included,
            freshness=self._fresh(),
        )
        rows = tuple(
            EvidenceNode(
                node_id=f"gmail/message/{row.id}",
                ref=self.reference(row.id, revision=observed_revision),
                kind=NodeKind.MESSAGE,
                role=row.role,
                reason=row.reason,
                depth=row.depth,
                content=_text_of(row, nonce=envelope.fence_nonce),
                freshness=self._fresh(),
                timestamps=_timestamps(dates.get(row.id)),
            )
            for row in source.messages
        )
        return (container, *rows)

    def _omissions_of(self, envelope: Envelope) -> tuple[OmissionRecord, ...]:
        """MailWeave's **four** accounting shapes as Orivra omission records.

        Four, not three: `Source.collapsed_runs` is the shape the first draft dropped, and
        dropping it left an eighty-message thread with a container node saying `included=80`
        and no record of the eighty (review finding R-M1-004).

        **Round 29's granularity rule is preserved rather than re-derived.** A record
        MailWeave wrote as a `WithheldGroup` stays a container-granularity record here,
        because the granularity *is* the call that recovers it: re-splitting a group into
        forty-five node records would mint forty-five handles for one call, which is the
        23,220-character failure R-MCP-033 recorded. A `WithheldTail` is a region: it names
        no thread, by design, and its recovery is a wider search.

        Each record's handle is MailWeave's own affordance re-labelled, never re-minted -
        the affordance already satisfies R-07 and the suite validates it against the
        published `inputSchema`.
        """
        records: list[OmissionRecord] = []
        for record in envelope.withheld:
            records.append(omission_from_record(record))
        for group in envelope.withheld_groups:
            records.append(omission_from_group(group))
        for tail in envelope.withheld_tail:
            records.append(omission_from_tail(tail))
        for source in envelope.sources:
            for run in source.collapsed_runs:
                records.append(omission_from_collapsed_run(run, thread_id=source.thread_id))
        return tuple(records)

    def _spend_of(self, envelope: Envelope) -> SourceSpend:
        report = envelope.retrieval_report
        return SourceSpend(
            connector=ConnectorId.GMAIL,
            state=SourceState.READY,
            rungs_executed=tuple(rung.value for rung in report.rungs),
            hits=sum(report.hit_count_per_rung),
            api_calls_by_method={"total": report.counters.api_calls},
            quota_units=report.counters.quota_units,
            caps_hit=tuple(cap.value for cap in report.budget_caps_hit),
        )


def omission_from_record(record: WithheldRecord) -> OmissionRecord:
    """One message, named, with the call that returns it."""
    cause = _cause_of(record.cap)
    return OmissionRecord(
        what=f"gmail/message/{record.id}",
        granularity=Granularity.NODE,
        count=1,
        cause=cause,
        cap_name=record.cap.value if cause is OmissionCause.CAP else None,
        why=record.why,
        recover=_handle_of(record.affordance, reduces=Dimension.DEPTH),
        connector=ConnectorId.GMAIL,
    )


def omission_from_group(group: WithheldGroup) -> OmissionRecord:
    """One thread's withheld messages, counted exactly, at the granularity that recovers
    them: a thread map, which is one call however many messages it returns."""
    cause = _cause_of(group.cap)
    return OmissionRecord(
        what=f"gmail/thread/{group.thread_id}",
        granularity=Granularity.CONTAINER,
        count=group.message_count,
        cause=cause,
        cap_name=group.cap.value if cause is OmissionCause.CAP else None,
        why=group.why,
        recover=_handle_of(group.affordance, reduces=Dimension.BREADTH),
        connector=ConnectorId.GMAIL,
    )


def omission_from_collapsed_run(run: CollapsedRun, *, thread_id: str) -> OmissionRecord:
    """A declared run of stub rows: present in the response, not disclosed in it.

    **The fourth accounting shape, and the one this adapter dropped** (review finding
    R-M1-004). MailWeave has four - `WithheldRecord`, `WithheldGroup`, `WithheldTail` and
    `Source.collapsed_runs` - and only the first three were translated. On an eighty-message
    thread the ladder collapsed, MailWeave accounted for all eighty with an executable
    affordance and Orivra emitted a container node claiming `included=80` beside five
    children and no record at all. That is the partiality invariant lost in translation,
    which is worse than never having had it: the container's own numbers said the response
    was complete.

    A **branch**, not a container: the run is a contiguous span of one thread rather than the
    whole of it, and the call that recovers it names the member ids rather than the thread.
    `what` therefore names the span, and the count is the run's own.
    """
    return OmissionRecord(
        what=f"gmail/thread/{thread_id}#{run.positions[0]}-{run.positions[1]}",
        granularity=Granularity.BRANCH,
        count=run.count,
        cause=OmissionCause.CEILING,
        cap_name=None,
        why=run.why,
        recover=_handle_of(run.affordance, reduces=Dimension.DEPTH),
        connector=ConnectorId.GMAIL,
    )


def omission_from_tail(tail: WithheldTail) -> OmissionRecord:
    """The threads past `MAX_WITHHELD_GROUPS_NAMED` under one cap.

    A **region**, not a container: the tail deliberately names no thread - that compaction
    is what it is for - and the call that recovers it is a search at a wider width. `what`
    therefore names the cap rather than an id, and the count is the message count, which is
    the figure `certify()` holds the enumeration to.
    """
    cause = _cause_of(tail.cap)
    return OmissionRecord(
        what=f"gmail/cap/{tail.cap.value}",
        granularity=Granularity.REGION,
        count=tail.message_count,
        cause=cause,
        cap_name=tail.cap.value if cause is OmissionCause.CAP else None,
        why=tail.why,
        recover=_handle_of(tail.affordance, reduces=Dimension.BREADTH),
        connector=ConnectorId.GMAIL,
    )


#: The method that produced a node this adapter built rather than read.
ADAPTER_METHOD = DerivationMethod(name="gmail/adapter", version="1")

#: MailWeave's `WithheldCap` values that name a **budget cap** the caller can raise, as
#: opposed to the two that name something else. `partial_source_failure` is not a cap - it
#: is a source that answered incompletely - and `disclosed_token_ceiling` is a ceiling, which
#: `OmissionCause` keeps separate because widening it is a different action from raising a
#: cap.
_CEILING_CAPS: frozenset[WithheldCap] = frozenset({WithheldCap.DISCLOSED_TOKEN_CEILING})
_NOT_A_CAP: frozenset[WithheldCap] = frozenset({WithheldCap.PARTIAL_SOURCE_FAILURE})


def _cause_of(cap: WithheldCap) -> OmissionCause:
    """Which Orivra cause one MailWeave cap is.

    Three outcomes rather than one, because raising a cap, widening a ceiling and retrying a
    source that answered incompletely are three different actions and a caller told "cap"
    for all three would take the wrong one twice.

    The third of them was `freshness_unverifiable` until a review pointed out that this is a
    fourth wrong action: it tells the caller a version could not be *verified*, and sends
    them to re-verify something that was never fetched. `OmissionCause` gained
    `PARTIAL_SOURCE_FAILURE` for it.
    """
    if cap in _CEILING_CAPS:
        return OmissionCause.CEILING
    if cap in _NOT_A_CAP:
        return OmissionCause.PARTIAL_SOURCE_FAILURE
    return OmissionCause.CAP


def _handle_of(affordance: Affordance, *, reduces: Dimension) -> ExpansionHandle:
    """MailWeave's affordance as Orivra's expansion handle.

    Carried across rather than re-minted: the affordance is already an executable call that
    R-07 and the v0.1 suite validate against the published `inputSchema`, and a handle Orivra
    invented would be a second call with none of that behind it. `OrivraToolName` holds
    MailWeave's four names verbatim, which is what makes this a re-labelling and not a
    translation.
    """
    return ExpansionHandle(
        tool=OrivraToolName(affordance.tool.value),
        args=dict(affordance.args),
        reduces=reduces,
    )


def _timestamps(internal_date: str | None) -> Timestamps:
    """Gmail's `internalDate` as the instant the mailbox received the message.

    `sent` and not `authored`: `internalDate` is what Gmail's own infrastructure recorded,
    and the `Date` header - what the sender claimed - is a different figure. R-DEMO-002
    closes on this field being present at all, including when it is empty.
    """
    if internal_date is None:
        return Timestamps()
    try:
        milliseconds = int(internal_date)
        # `fromtimestamp` is **inside** the `try`: `GmailNumericId` accepts up to twenty
        # digits, and a nineteen-digit `internalDate` is a year Python cannot represent. It
        # used to raise `ValueError`/`OSError` out of here, through `answer` and `ask`, and
        # out of the tool call as an internal error - one odd field taking down the whole
        # response (review finding R-M1-020). An unrepresentable instant is an absent one.
        return Timestamps(sent=datetime.fromtimestamp(milliseconds / 1000, tz=UTC))
    except (ValueError, OverflowError, OSError):
        return Timestamps()


def _text_of(row: MessageRow, *, nonce: str) -> str | None:
    """The row's disclosed text, **with this response's fence removed**.

    `nodes.py` states the rule: a node is not an emission, it outlives the response that
    built it, and fencing it would stamp one response's nonce onto text a later response
    emits under a different one - the fence failing open. The first draft's docstring said
    exactly that and the code returned `row.content.text`, which is already fenced. Two
    consequences, both real: the stated hazard was built in, and every span offset shifted by
    the length of the opening marker, so `QueryGraph`'s span string-match compared fenced
    text against offsets computed over `AnnotatedBody.text` and was 46 characters out of
    register (review finding R-M1-006).

    `unfence` is `envelope/fence.py`'s own inverse, called rather than re-implemented.
    """
    if row.content is None:
        return None
    return unfence(nonce, row.content.text) or None


__all__ = [
    "ADAPTER_METHOD",
    "CONTAINER_KIND",
    "EMITTED_OPERATORS",
    "MAX_IDS_PER_FETCH",
    "GmailAdapter",
    "omission_from_collapsed_run",
    "omission_from_group",
    "omission_from_record",
    "omission_from_tail",
]
