"""The four tool handlers, over one authorised mailbox.

This module is where the retrieval stack built since round 15 becomes reachable from
outside a test. It owns no policy of its own: every decision it makes is delegated to the
module that already owns it - `mailweave.query`/`retrieval` for what to fetch,
`mailweave.policy` for what it may spend, `mailweave.disclosure` for how deep to say it,
`mailweave.handles` for whether a handle may be honoured, `mailweave.envelope` for whether
the result may be emitted at all. What is decided here is only which of those to call.

**One shape for every outcome.** Every handler returns an `Envelope` or raises. There is no
third return type, no partial dict, and no path that reaches a client without going through
`Envelope.model_dump` - the wire chokepoint of rounds 13-14, which re-establishes every
invariant of the whole model tree and reads I-1's and I-2's claims back out of the mapping
it is about to hand over. `mailweave.surface.partition` turns a raise into a declared
refusal and an `Envelope` into a declared result, and it is the only place that decides
which.

**Concurrency, stated rather than assumed.** AD A.5c specifies a single event loop with no
threads and `max_concurrent_queries = 2`. The retrieval stack is synchronous, so this build
serves **one query at a time**: `mailweave.surface.server` holds a lock across a whole tool
call. That is narrower than A.5c and it is named as narrower - the second concurrent query
waits rather than running beside the first, and nothing in the response claims otherwise.
What A.5c's concurrency guarantee actually protects, MCP-02's "a second concurrent client
can consume a handle minted earlier", does not depend on it: a handle carries its own state
and is verified against the mailbox, so a second `MailweaveService` over the same key
redeems it without any shared object at all.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from mailweave.constants import (
    FLOOR_OVERFLOW_CEILING_TOKENS,
    HOST_RESULT_CHAR_CAP,
    MAX_PAGES_PER_QUERY,
    MAX_SERVER_MS,
    NORMAL_CEILING_TOKENS,
)
from mailweave.content.mime import AttachmentRow
from mailweave.content.payload import MessagePayload
from mailweave.content.pipeline import ProcessedMessage, process_message
from mailweave.diagnostics import lifecycle
from mailweave.disclosure import Ceilings, Selector
from mailweave.disclosure.pages import page_size
from mailweave.envelope.disposition import DispositionLedger
from mailweave.envelope.reasons import RungId
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import Depth, ToolName
from mailweave.envelope.wire import AttachmentMetadata, Counters, ErrorEntry
from mailweave.errors import (
    ContentProcessingError,
    ErrorCode,
    HandleRefused,
    QueryNotSearchable,
)
from mailweave.freshness.recency import RecencyRun, RecencyRunner, RecencyState
from mailweave.freshness.watermark import WatermarkFile
from mailweave.gmail.client import GmailClient
from mailweave.gmail.models import Message
from mailweave.gmail.retry import Deadline
from mailweave.handles.cache import ThreadMapCache
from mailweave.handles.keys import HandleKey
from mailweave.handles.mint import HandleMinter, re_derivation_of
from mailweave.handles.redeem import Redemption, ServedThread, redeem_or_raise
from mailweave.policy.budget import BudgetAccountant, apply_floor
from mailweave.query.analysis import ParsedQuery
from mailweave.retrieval.assemble import assemble
from mailweave.retrieval.ladder import LadderRunner
from mailweave.retrieval.semantic import SemanticRun, SemanticRunner
from mailweave.retrieval.structural import MAX_STRUCTURAL_PROBES
from mailweave.semantic.interface import REGISTRY, BackendRegistry, SemanticError
from mailweave.semantic.profile import SemanticProfile
from mailweave.semantic.resolve import resolve_profile
from mailweave.structure.threadmap import ThreadMap, snippet_observed_text
from mailweave.structure.threadmap import build as build_thread_map
from mailweave.surface.arguments import (
    ArgumentInvalid,
    GetAttachmentRequest,
    GetMessagesRequest,
    SearchRequest,
    ThreadMapRequest,
)
from mailweave.surface.expansion import EXPANSION_RUNG, Observation, Wanted, expand
from mailweave.trace.emit import trace_of
from mailweave.trace.sink import TraceSink, new_trace_id

#: The depths that need a body fetched for them, so `messages.get` is asked for `full` only
#: where the answer will actually carry one.
_NEEDS_BODY: frozenset[Depth] = frozenset({Depth.BODY_CLEAN, Depth.BODY_FULL})


def _now() -> datetime:
    return datetime.now(UTC)


def _monotonic_ms() -> float:
    import time

    return time.monotonic() * 1000.0


def _counters(client: GmailClient) -> Counters:
    reading = client.meter.reading()
    return Counters(
        http_requests=reading.http_requests,
        api_calls=reading.api_calls,
        quota_units=reading.quota_units_diagnostic,
    )


def _attachment(row: AttachmentRow) -> AttachmentMetadata:
    return AttachmentMetadata(
        filename=row.filename,
        mime_type=row.mime_type,
        size=row.size,
        part_id=row.part_id,
        attachment_id=row.attachment_id,
    )


def process_gmail_message(message: Message) -> ProcessedMessage | None:
    """The content pipeline over one `messages.get(format=full)` response, or `None`.

    **Public because the primitive-tools floor calls it.** A baseline that reached the
    same bytes through a different decoder would be measuring two things at once - the
    retrieval policy and the content pipeline - and the comparison's whole claim is that
    only the policy differs. So the floor reads bodies through this function, not a
    second copy of it.

    `None` for a message with no payload and for one the pipeline refused - both are "this
    response holds no body for this message", which `depth_for` turns into a shallower
    declared depth rather than into a failed call. A body that cannot be processed is a
    reduction in what one row can say; it is not a reason to refuse the whole request.
    """
    if message.payload is None:
        return None
    try:
        return process_message(
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


@dataclass
class MailweaveService:
    """One authorised mailbox, and the four calls that may be made against it.

    `open_client` returns a **fresh** `GmailClient` per call over whatever transport the
    runtime configured. Fresh, because `CallMeter` is per query and the response's
    `counters` block is a statement about *this* call; the transport underneath is shared,
    so the freshness costs a small object and not a TLS handshake.
    """

    open_client: Callable[[], GmailClient]
    account_hash: str
    handle_key: HandleKey | None = None
    cache: ThreadMapCache | None = None
    now: Callable[[], datetime] = _now
    clock_ms: Callable[[], float] = _monotonic_ms
    #: The semantic bounds this server declares, resolved once from the preflight records
    #: rather than per query: `resolve_profile` reads files off disk, and re-reading them on
    #: every call would let one process answer two queries under two different declared
    #: bounds if a record were rewritten between them.
    semantic_profile: SemanticProfile = field(default_factory=resolve_profile)
    #: The disclosure selector (WS-11's `Selector`). `None` is the shipped `QueryAwareFill`;
    #: `FixedWindow` is Baseline F, the fixed +/-2 policy DISC-02 measures "conditioned on the
    #: query" *against*. A field rather than a parameter for the registry's reason: an
    #: evaluation arm built by some other path is an arm nobody ships.
    selector: Selector | None = None
    #: D.7's second tier, the cross-encoder. `True` is the shipped server. `False` is the H2
    #: bypass arm: L5's embedding still runs and still shortlists, the mechanical tier still
    #: orders every candidate, and the cross-encoder is simply not there - no backend acquired
    #: for it, no pair scored, no score invented. A field for `selector`'s reason: an
    #: evaluation arm assembled by some other path is an arm nobody ships.
    cross_encoder: bool = True
    #: The backend registry. A field so a test can hand in its own; production takes the
    #: process-wide one, which is what makes the model load once per process rather than
    #: once per query - see `warm_semantic_backend` and `BackendRegistry.acquire`.
    registry: BackendRegistry = REGISTRY
    #: Where the `historyId` watermark lives (AD D.9). `None` disables LR entirely, which is
    #: the honest configuration for a caller that has no state directory: the rung then
    #: records `not_applicable` rather than silently doing nothing. `mailweave serve` passes
    #: the configured path.
    watermark_path: Path | None = None

    #: Where traces go (AD A.11, D.10). `None` writes none, which is the honest default for
    #: a caller that did not ask for them: a trace is a file about somebody's mailbox, and a
    #: server that wrote one nobody configured would be making that decision for them.
    trace_sink: TraceSink | None = None

    @property
    def watermark(self) -> WatermarkFile | None:
        return None if self.watermark_path is None else WatermarkFile(self.watermark_path)

    def warm_semantic_backend(self) -> bool:
        """Load the semantic backend now, before any query asks for it.

        **Called by `mailweave serve` at startup, and the reason is a measurement.** PF-4
        records `cold_acquire_ms = 5410` on the owner's laptop against a `MAX_SEMANTIC_MS`
        of 6,000: a first query that paid the load inside its own budget would have 590 ms
        left for work PF-4 measures at 250 ms, and a machine a fifth slower than that one
        would have nothing left at all. The load is per process, so paying it at startup
        costs one query nothing and costs the process the same five seconds either way.

        Returns whether the backend is now loaded. **A `False` is not an error and does not
        stop the server**: a machine with no weights is a supported configuration, and L5
        declines in band on it (D.5's deterministic fallback, D.11 `semantic_unavailable`).
        Nothing is logged about the failure here - the rung's own `not_tried` entry carries
        it, where a caller can see it.
        """
        try:
            self.registry.acquire()
        except SemanticError:
            return False
        return True

    # -- shared -------------------------------------------------------------------------

    @property
    def minter(self) -> HandleMinter | None:
        """The handle minter, or `None` for a server that has no key.

        `None` produces sources with `map_id: null`, which is the honest value for a server
        that cannot mint one - not an error, and not a handle nothing could verify.
        """
        if self.handle_key is None:
            return None
        return HandleMinter(key=self.handle_key, account_hash=self.account_hash)

    def _watermark(self, client: GmailClient) -> str | None:
        """The mailbox `historyId` a handle minted in this call must be anchored to (A10)."""
        if self.handle_key is None:
            return None
        return client.get_profile().history_id

    def _observe_thread(
        self, client: GmailClient, ledger: DispositionLedger, thread_id: str
    ) -> Observation:
        recorded = client.get_thread(ledger, thread_id=thread_id, rung=EXPANSION_RUNG)
        # **Positions come from the sealed observation, never from a sort performed here.**
        # `assemble._map_of` takes the same route and for the same reason (amendment A3,
        # R-ARCH-031): a second ordering of one thread is two answers to one question, and
        # the one that disagrees is always the one nobody is looking at.
        positions = {
            message_id: origin.position
            for message_id, origin in ledger.origins.items()
            if origin.thread_id == thread_id and origin.position is not None
        }
        if len(positions) != len(recorded.thread.messages):
            # The observation stated positions for all rows or for none (A6's all-or-nothing
            # rule). `build_thread_map` refuses the partial case with its own message, which
            # is the honest failure: this call cannot map a thread whose chronological order
            # the observation declined to state, and inventing one is the failure this
            # project exists to prevent.
            positions = {}
        thread_map: ThreadMap = build_thread_map(
            thread_id=thread_id,
            messages=recorded.thread.messages,
            positions=positions,
            observed_text=snippet_observed_text(recorded.thread.messages),
            tied_on_internal_date=recorded.tied_on_internal_date,
        )
        return Observation(
            thread_id=thread_id,
            thread_map=thread_map,
            fetched_at=recorded.fetched_at,
            history_id=recorded.thread.history_id,
            messages=tuple(recorded.thread.messages),
        )

    def _redeem(
        self, client: GmailClient, ledger: DispositionLedger, map_id: str
    ) -> tuple[Redemption, tuple[Observation, ...], tuple[ErrorEntry, ...]]:
        """Step 1 of every handle-bearing call: verify, probe, fetch, digest (AD A.10).

        `redeem_or_raise` reads D.11's partition out of `ERROR_SURFACE`, so the four handle
        classes that are tool errors raise and the one that is in band comes back on a
        served response. Nothing about that split is decided here.
        """
        outcome = redeem_or_raise(
            map_id,
            key=_require_key(self.handle_key),
            account_hash=self.account_hash,
            client=client,
            ledger=ledger,
            cache=self.cache if self.cache is not None else ThreadMapCache(),
            now=self.now(),
        )
        in_band: tuple[ErrorEntry, ...] = ()
        if outcome.outcome is ErrorCode.HANDLE_STALE_UNVERIFIABLE:
            in_band = tuple(
                ErrorEntry(
                    code=ErrorCode.HANDLE_STALE_UNVERIFIABLE,
                    scope=f"thread:{served.thread_map.thread_id}",
                    affordance=outcome.affordance,
                )
                for served in outcome.served
            )
        return outcome, tuple(_observed(served) for served in outcome.served), in_band

    # -- the four tools -----------------------------------------------------------------

    def _open_client_for_call(self, budget_ms: float | None = None) -> GmailClient:
        """A client for one tool call, with that call's wall-clock allowance bound to it.

        **Every tool, not only search** (2026-09-21). `max_server_ms` was applied by the
        search accountant when deciding which rungs to run and by nothing at all on the read
        paths: `thread_map`, `get_messages` and `get_attachment` opened a client with no
        clock and made their `threads.get` and `messages.get` calls with no bound but the
        transport's own 30 s per attempt. The `Deadline` is the same published figure, bound
        to the client so every request of the call - including each message of a sequential
        read, and each retry of each request - is measured against what is left of it.
        """
        allowance = float(MAX_SERVER_MS if budget_ms is None else budget_ms)
        client = self.open_client()
        client.bind_deadline(Deadline(budget_ms=allowance, clock_ms=self.clock_ms))
        # The diagnostics end line measures the call against what it bound, so a late
        # decline is recorded as late rather than passing because it declined.
        lifecycle().allowance(allowance)
        return client

    def client_for_call(self, budget_ms: float | None = None) -> GmailClient:
        """`_open_client_for_call`, for the adapter that runs Gmail requests of its own.

        **Every client that makes a request inside a tool call binds an allowance**
        (2026-09-22). The Orivra adapter opened `open_client()` directly for its ids-only
        ladder, its liveness probes, its history walks and its per-message fetches, so those
        requests ran under no deadline at all - the one class of call the first repair said
        it had covered ("every tool, not only search") and had not - and, until the socket
        clamp was scoped per request, under whichever deadline the previous client had left
        in the call's context. This is the same construction the four tools use; it is
        public so the adapter can reach it without reaching into this class.
        """
        return self._open_client_for_call(budget_ms)

    def search(self, request: SearchRequest, *, host_chars: int | None = None) -> Envelope:
        """`mailweave_search`: the whole ladder, the whole disclosure, one envelope.

        **`host_chars` is room, not policy, and it can only ever lower.** `Ceilings.host_chars`
        is documented on its own field as "a property of the *host this response is being
        handed to*", and a response that is about to be *embedded in a larger one* is being
        handed to a host that has less room for it than the cap suggests. Orivra's `ask`
        composes MailWeave's container with a block of its own; before this argument existed
        the ladder fitted the container to the whole cap, Orivra's block then spent characters
        the ladder had already promised away, and the composed response was refused - a refusal
        reachable from the plainest possible ask.

        Nothing on the four `mailweave_*` paths passes it. `surface.server` calls
        `service.search(parse_search(raw))` exactly as it did, so `mailweave_search` is still
        fitted to `SERVED_CEILINGS` and its wire contract is untouched. `None` is therefore not
        merely the default but the whole of the legacy behaviour.

        A value at or above the published cap is not an error and does not raise it: it is
        simply not a narrowing, and the published cap stands. The same direction
        `_lowered_ceilings` runs in, for the same reason.
        """
        started_ms = self.clock_ms()
        budget = apply_floor(request.budget)
        # The search's allowance is both published clocks together: the accountant charges
        # RTT-bound rungs to `max_server_ms` and CPU-bound semantic work to `max_semantic_ms`
        # *without* charging the first for the second (`BudgetAccountant.leave_semantic`),
        # and a Gmail request made after the semantic tier ran is measured against the sum a
        # caller was told the call could take, not against the one cap that does not count
        # the time in between. The reads bind `MAX_SERVER_MS` alone: they run no semantic
        # tier.
        client = self._open_client_for_call(budget.max_server_ms + budget.max_semantic_ms)
        ledger = DispositionLedger()
        accountant = BudgetAccountant(
            client.meter, budget, now_ms=self.clock_ms, query=request.query
        )
        runner = LadderRunner(
            client,
            ledger,
            max_pages=(
                request.scan_max_pages
                if request.scan_max_pages is not None
                else MAX_PAGES_PER_QUERY
            ),
            accountant=accountant,
            forced=request.forced,
            relax_max_probes=request.relax_max_probes,
        )
        try:
            run = runner.run(request.query, now=self.now())
        except QueryNotSearchable as refusal:
            # Unreachable from the protocol surface - the schema requires a non-empty
            # `query` and the reader refuses a whitespace-only one before this is called -
            # and handled anyway, as a protocol error, because a query with nothing in it
            # is a malformed call and not a retrieval that failed.
            raise ArgumentInvalid(f"{ToolName.SEARCH.value}: {refusal}") from refusal
        # **L5 runs between the ladder and assembly, and it runs on the same ledger.** Its
        # probes are `messages.list` calls and its thread reads are `threads.get` calls, so
        # every id it sees is admitted by the ledger at the moment of the call and is owed a
        # disposition like any other. It is *not* inside `assemble`, because `assemble`'s
        # first act is to read the hit-bearing threads off the ledger and the pool has to
        # have contributed its threads by then.
        semantic = SemanticRunner(
            client,
            ledger,
            profile=self.semantic_profile.narrowed(
                max_threads=request.pool.max_threads,
                max_messages=request.pool.max_messages,
            ),
            registry=self.registry,
            accountant=accountant,
            clock_ms=self.clock_ms,
        ).run(run, now=self.now(), forced=RungId.L5 in request.forced)

        # **LR, after the lexical ladder and the pool, before the response is assembled.**
        # Its `history.list` walk records every `messagesAdded` id into the same ledger under
        # clause H-hist, so a candidate it declines to fetch is still owed an account - which
        # `assemble` files under `max_recency_fetch`.
        recency = self._reconcile_recent(client, ledger, run.parsed, accountant)
        envelope = assemble(
            run,
            client=client,
            ledger=ledger,
            minter=self.minter,
            accountant=accountant,
            extra_errors=request.declarations,
            evidence_view=request.view,
            semantic=semantic,
            # L6 acquires the same backend L5 did, from the same process-wide registry, so a
            # rerank never pays a second load.
            registry=self.registry,
            selector=self.selector,
            cross_encoder=self.cross_encoder,
            clock_ms=self.clock_ms,
            forced=request.forced,
            recency=recency,
            # Round 27, R-MCP-025: the caller's own narrowing, already clamped downward by
            # `apply_floor`. Passing the applied figure rather than the request is what makes
            # the `retry_with` a decline mints do the thing it says it will do.
            max_hit_threads=budget.max_hit_threads,
            structural_max_probes=(
                request.structural_max_probes
                if request.structural_max_probes is not None
                else MAX_STRUCTURAL_PROBES
            ),
            # **`max_disclosed_tokens` can only lower.** The published ceiling is the
            # maximum a response may reach, so a caller asking for more gets the published
            # one and a caller asking for less gets what they asked for - the same direction
            # `force_rungs` runs in, inverted because this argument spends the *reader's*
            # budget rather than the server's.
            #
            # **Both ceilings move together, or the model refuses the response** (round 25,
            # R-MCP-004). `Ceiling` refuses `applied < normal` - an applied ceiling below the
            # normal one is not a ceiling - and the envelope's `normal` is the published
            # figure, so lowering only the ladder's `normal` made every value in [1, 8999]
            # raise a `ValidationError` that reached the caller as `-32602 INVALID_PARAMS`:
            # a published D.1 argument was broken for every value that did anything, and the
            # client was told its own request was malformed. The overflow is lowered to the
            # request too, so a caller asking for less than the published ceiling cannot be
            # handed the published *overflow* through A.9a step 6.
            ceilings=_with_room(
                SERVED_CEILINGS
                if request.disclosed_token_request is None
                else _lowered_ceilings(request.disclosed_token_request),
                host_chars,
            ),
        )
        # **The watermark moves after the response is built, never before the walk**
        # (amendment A10's ordering). A watermark advanced first would sit above changes this
        # query never looked at, and the next query would start from a place nobody
        # reconciled - a gap that is invisible because each individual response looks whole.
        self._advance_watermark(client, recency)
        # **The trace is written after the response is built, from the response.** Every
        # field of it is a projection of what the envelope already states plus the two things
        # the envelope may not carry - `pool_ids[]` and the query's shape - so a trace cannot
        # report a run the caller was not told about.
        self._trace(
            envelope,
            tool=ToolName.SEARCH.value,
            query=request.query,
            semantic=semantic,
            recency=recency,
            started_ms=started_ms,
        )
        return envelope

    def _trace(
        self,
        envelope: Envelope,
        *,
        tool: str,
        query: str,
        semantic: SemanticRun | None = None,
        recency: RecencyRun | None = None,
        started_ms: float = 0.0,
    ) -> None:
        """Write one trace, or none. **Never fails the call it is about.**

        A trace is a forensic record of a response that has already been produced and is
        already correct. A disk that will not take it costs observability and nothing else,
        and turning that into a failed tool call would make the instrumentation less safe
        than no instrumentation - which is the failure mode A.11's "a rule that is expensive
        to obey is a rule that gets bypassed" is about, arriving from the other side.
        """
        sink = self.trace_sink
        if sink is None:
            return
        try:
            sink.write(
                trace_of(
                    envelope,
                    trace_id=new_trace_id(),
                    tool=tool,
                    query=query,
                    semantic=semantic,
                    recency=recency,
                    latency_ms=max(0, int(self.clock_ms() - started_ms)),
                    policy=sink.policy,
                )
            )
        except (OSError, ValueError):
            return

    # -- LR ------------------------------------------------------------------------------

    def _reconcile_recent(
        self,
        client: GmailClient,
        ledger: DispositionLedger,
        parsed: ParsedQuery,
        accountant: BudgetAccountant,
    ) -> RecencyRun | None:
        """Run LR, or `None` when this server has nowhere to keep a watermark.

        `None` rather than a `not_applicable` run, because the two are different facts and
        `assemble` reads the difference: a server with no state directory has no account of
        LR to give at all, and `outcome_of` then declines `not_found` on the "a rung with no
        account" clause - which is the honest answer. A server *with* a watermark file and no
        stored watermark yet does have an account, and gives it.
        """
        file = self.watermark
        if file is None:
            return None
        return RecencyRunner(
            client,
            ledger,
            watermark=file,
            identity=self.account_hash,
            accountant=accountant,
            max_fetch=accountant.budget.max_recency_fetch,
        ).run(parsed)

    def _advance_watermark(self, client: GmailClient, recency: RecencyRun | None) -> None:
        """Record the `historyId` this query observed, so the next one has a place to walk from.

        Three cases and they are three different sentences. A run that walked records what it
        walked to. A run that found no stored watermark records the mailbox's current one, so
        the *next* query has a floor - which is what makes a fresh install converge instead of
        never running LR at all. A re-baseline records the current one too, which is what
        re-baselining means.
        """
        file = self.watermark
        if file is None or recency is None:
            return
        history_id = recency.latest_history_id
        if history_id is None and recency.state in {
            RecencyState.NO_WATERMARK,
            RecencyState.REBASELINED,
        }:
            history_id = client.get_profile().history_id
        if history_id is None:
            return
        try:
            file.observe_identity(identity=self.account_hash, history_id=history_id)
        except OSError:
            # The watermark is an optimisation for the *next* query and this one is already
            # answered. A disk that will not take it costs freshness on the next call and
            # nothing on this one, so it is not a reason to fail a response that is correct.
            return

    def thread_map(self, request: ThreadMapRequest) -> Envelope:
        """`mailweave_thread_map`: one thread, whole, however the caller named it."""
        client = self._open_client_for_call()
        ledger = DispositionLedger()
        watermark = self._watermark(client)
        if request.map_id is not None:
            outcome, observations, in_band = self._redeem(client, ledger, request.map_id)
            if request.page:
                _the_paging_is_the_handles(outcome, observations)
        else:
            assert request.thread_id is not None  # the parser refuses neither and both
            observations, in_band = (
                (self._observe_thread(client, ledger, request.thread_id),),
                (),
            )
        return expand(
            observations,
            wanted=Wanted(named=frozenset(), segment=request.segment, page=request.page),
            bodies={},
            ledger=ledger,
            tool=ToolName.THREAD_MAP,
            counters=_counters(client),
            minter=self.minter,
            mailbox_history_id=watermark,
            in_band=in_band,
            ceilings=SERVED_CEILINGS,
        )

    def get_messages(self, request: GetMessagesRequest) -> Envelope:
        """`mailweave_get_messages`: the named messages, at the named depth, inside their maps."""
        client = self._open_client_for_call()
        ledger = DispositionLedger()
        watermark = self._watermark(client)
        in_band: Sequence[ErrorEntry] = ()
        fetched: Mapping[str, Message] = {}
        if request.map_id is not None:
            _outcome, observations, in_band = self._redeem(client, ledger, request.map_id)
            order = _ids_at(observations, request.positions)
        else:
            order = tuple(request.message_ids)
            observations, fetched = self._threads_of(
                client, ledger, request.message_ids, request.view
            )
        named = frozenset(order)
        bodies = self._bodies_for(client, named, request.view, observations, fetched)
        return expand(
            observations,
            # In the order the caller named them: the order a batch is served in and the
            # order its continuation keeps (navigation redesign, 2026-09-14).
            wanted=Wanted(named=named, view=request.view, order=order),
            bodies=bodies,
            ledger=ledger,
            tool=ToolName.GET_MESSAGES,
            counters=_counters(client),
            minter=self.minter,
            mailbox_history_id=watermark,
            in_band=in_band,
            ceilings=SERVED_CEILINGS,
        )

    def get_attachment(self, request: GetAttachmentRequest) -> Envelope:
        """`mailweave_get_attachment`: one part's metadata, on the message that carries it.

        The carrying message comes back at snippet depth with **every** part its MIME tree
        declares, narrowed to the one named when that part exists. A `part_id` the tree does
        not contain therefore comes back as the parts that do exist, which is a truthful
        partial answer and needs no code D.11 does not have: the caller can see their part
        is not among them rather than being told a part exists that does not.
        """
        client = self._open_client_for_call()
        ledger = DispositionLedger()
        watermark = self._watermark(client)
        carrier = client.get_message(request.message_id, message_format="full")
        processed = process_gmail_message(carrier)
        parts = () if processed is None else processed.attachments
        named = [row for row in parts if row.part_id == request.part_id]
        shown = named or list(parts)
        observations = (self._observe_thread(client, ledger, carrier.thread_id),)
        return expand(
            observations,
            wanted=Wanted(
                named=frozenset({request.message_id}),
                view=Depth.SNIPPET,
                attachments={request.message_id: tuple(_attachment(row) for row in shown)},
            ),
            bodies={},
            ledger=ledger,
            tool=ToolName.GET_ATTACHMENT,
            counters=_counters(client),
            minter=self.minter,
            mailbox_history_id=watermark,
            ceilings=SERVED_CEILINGS,
        )

    # -- fetching -----------------------------------------------------------------------

    def _threads_of(
        self,
        client: GmailClient,
        ledger: DispositionLedger,
        message_ids: Sequence[str],
        view: Depth,
    ) -> tuple[tuple[Observation, ...], Mapping[str, Message]]:
        """Every thread that carries one of the named messages, mapped once each - and the
        messages that were fetched to find them, so nothing fetches them again.

        One `messages.get` per named id - the only way to learn a bare message id's thread -
        and one `threads.get` per distinct thread. The `messages.get` asks for `metadata`
        unless the requested view needs a body, so a `view: "stub"` request never pays for
        text it will not disclose.

        **Round 28, R-MCP-038.** When the view did need a body this asked for `full`, kept
        only `thread_id` from the answer, and `_bodies_for` then asked for the same id in
        `full` again: two full reads per named message on every `body_clean` or `body_full`
        call, the first one thrown away. The fetched messages are now returned beside the
        observations and `_bodies_for` processes what is already in hand.
        """
        threads: list[str] = []
        fetched: dict[str, Message] = {}
        for message_id in message_ids:
            message = client.get_message(
                message_id,
                message_format="full" if view in _NEEDS_BODY else "metadata",
            )
            fetched[message_id] = message
            if message.thread_id not in threads:
                threads.append(message.thread_id)
        observations = tuple(
            self._observe_thread(client, ledger, thread_id) for thread_id in threads
        )
        return observations, fetched

    def _bodies_for(
        self,
        client: GmailClient,
        named: frozenset[str],
        view: Depth,
        observations: Sequence[Observation],
        fetched: Mapping[str, Message] | None = None,
    ) -> Mapping[str, ProcessedMessage]:
        """The processed bodies the requested depth actually needs, and no others.

        A depth is a statement about text that exists, so a view that shows no body fetches
        none: `stub` and `snippet` are answered out of the thread map this call already
        holds, and only `body_clean` and `body_full` reach `messages.get(format=full)`.

        `fetched` is what `_threads_of` already read in full; a message in it is processed
        rather than fetched a second time (round 28, R-MCP-038). The `map_id` route arrives
        with nothing fetched, because it learned its threads from the handle, and pays one
        full read per named id here - which is still one.
        """
        if view not in _NEEDS_BODY:
            return {}
        in_hand_by_id = fetched or {}
        present = {message_id for one in observations for message_id in one.thread_map.order}
        bodies: dict[str, ProcessedMessage] = {}
        for message_id in sorted(named & present):
            in_hand = in_hand_by_id.get(message_id)
            message = (
                in_hand
                if in_hand is not None and in_hand.payload is not None
                else client.get_message(message_id, message_format="full")
            )
            processed = process_gmail_message(message)
            if processed is not None:
                bodies[message_id] = processed
        return bodies


#: **The ceilings every served response is held to** (round 26, R-DISC-033, R-MCP-021).
#: The two published token figures, plus the host's character cap - because this module is the
#: one place where a response stops being a measurement and becomes something handed to a
#: host. Every handler below passes it, and `surface.partition.declared_result` measures the
#: rendered result against the same constant whatever was planned, so a handler that forgot it
#: would decline rather than hand the host a result it will silently cut.
SERVED_CEILINGS: Final[Ceilings] = Ceilings(host_chars=HOST_RESULT_CHAR_CAP)


def _lowered_ceilings(requested: int) -> Ceilings:
    """`budget.max_disclosed_tokens` as a pair of ceilings the wire model will accept.

    It can only lower: the published ceiling is the maximum a response may reach, so a caller
    asking for more gets the published one and a caller asking for less gets what they asked
    for - the same direction `force_rungs` runs in, inverted because this argument spends the
    *reader's* budget rather than the server's. Both figures move, because `Ceiling` refuses
    an applied ceiling below its normal one and A.9a step 6 may raise to the overflow.

    The host's character cap rides along unchanged: a caller may lower what MailWeave spends
    of their context, and may not raise what the host will accept.
    """
    normal = min(requested, NORMAL_CEILING_TOKENS)
    return Ceilings(
        normal=normal,
        overflow=min(FLOOR_OVERFLOW_CEILING_TOKENS, max(normal, requested)),
        host_chars=HOST_RESULT_CHAR_CAP,
    )


def _with_room(ceilings: Ceilings, host_chars: int | None) -> Ceilings:
    """`ceilings` with its character cap narrowed to the room actually available.

    Lowering only, and by `min` rather than by assignment, so a caller asking for more room
    than the host will accept gets the host's figure. The token ceilings do not move: they are
    AD D.4's policy figures and how much room this particular response has been given says
    nothing about them.
    """
    if host_chars is None:
        return ceilings
    if host_chars < 1:
        raise ValueError(
            f"host_chars={host_chars} leaves no room for a response at all; a container with "
            "no characters is not a narrowing, it is an empty allocation"
        )
    published = HOST_RESULT_CHAR_CAP if ceilings.host_chars is None else ceilings.host_chars
    return replace(ceilings, host_chars=min(published, host_chars))


def _observed(served: ServedThread) -> Observation:
    return Observation(
        thread_id=served.thread_map.thread_id,
        thread_map=served.thread_map,
        fetched_at=served.fetched_at,
        verified_at=served.verified_at,
        history_id=served.history_id_at_fetch,
        messages=served.messages,
    )


def _ids_at(observations: Sequence[Observation], positions: Sequence[int]) -> tuple[str, ...]:
    """The message ids at the named positions of the redeemed threads, in position order.

    A position outside a thread's order simply names nothing here; the response then carries
    the thread's map with no requested row in it, and the map itself shows the caller which
    positions exist. Raising would be the wrong answer for an argument that is well formed
    and merely out of date - the handle was honoured, so the mailbox has not moved, and what
    the caller has is an off-by-one rather than a stale handle.
    """
    named: dict[str, None] = {}
    for position in positions:
        for observation in observations:
            if 0 <= position < len(observation.thread_map.order):
                named.setdefault(observation.thread_map.order[position], None)
    return tuple(named)


def _the_paging_is_the_handles(outcome: Redemption, observations: Sequence[Observation]) -> None:
    """A page after the first is served only at the width the handle was minted at.

    Page *k* of a map is positions `k * width` onward, so `thread_map(map_id, page=k)` is a
    claim about a width as much as about a thread. The redemption verified the thread - its
    messages and their order digest to the handle's - and this verifies the paging: the
    width is recomputed from the served map (`disclosure.pages.page_size`, the one arithmetic)
    and compared with the width the handle signed (`HandlePayload.page_sizes`). They differ
    only when the server's own paging changed under an outstanding handle - a deploy that
    moved a measure constant within the ttl - since every input to the width is a function
    of the thread's messages, which the digest already fixed. Refused as `handle_stale` with
    the re-derivation, exactly as a thread that moved is: page *k* of this handle is not page
    *k* of the map, and a page served from a different starting position is a silent gap or
    repeat in a traversal (continuation correctness, 2026-09-15). Page 0 is page 0 at any
    width, so a handle without a page, or with page 0, is not checked here.
    """
    payload = outcome.payload
    assert payload is not None  # a served or in-band redemption always carries its payload
    minted = payload.page_size_at_mint
    for observation in observations:
        was = minted.get(observation.thread_id)
        now = page_size(observation.thread_map)
        if was is not None and was != now:
            raise HandleRefused(
                code=ErrorCode.HANDLE_STALE,
                message=(
                    f"thread {observation.thread_id} is paged differently now: its map is "
                    f"{now} positions a page where this map_id was minted at {was}. The "
                    "thread itself is unchanged - the server's paging moved under the handle "
                    "- so page k of this map_id is not page k of the thread's map, and "
                    "serving it would start from a different position. Re-derive the map"
                ),
                affordance=re_derivation_of(payload),
            )


def _require_key(key: HandleKey | None) -> HandleKey:
    if key is None:
        raise HandleRefused(
            code=ErrorCode.HANDLE_INVALID,
            message=(
                "this server holds no handle signing key, so no map_id can be verified as "
                "one it minted. Re-derive the map with mailweave_thread_map(thread_id=...)"
            ),
        )
    return key


__all__ = ["MailweaveService"]
