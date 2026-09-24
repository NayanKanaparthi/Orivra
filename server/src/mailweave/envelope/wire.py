"""Wire models of the response envelope, below the top-level `Envelope` (AD D.2).

Every obligation the contract states mechanically is a validator here, so a
non-conforming response is unconstructible rather than merely undesirable.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Final

from pydantic import (
    AfterValidator,
    ConfigDict,
    Field,
    JsonValue,
    SerializationInfo,
    computed_field,
    field_serializer,
    model_validator,
)

from mailweave.constants import (
    FLOOR_QUOTA_UNITS,
    MAX_ATTACHMENT_FILENAME_CHARS,
    MAX_ATTACHMENT_ID_CHARS,
    MAX_AUTH_RECORD_CHARS,
    MAX_MIME_TYPE_CHARS,
    MAX_PART_ID_CHARS,
    NORMAL_CEILING_TOKENS,
    auth_record_fits,
    is_an_address,
    is_one_line,
    mailbox_regions_of,
)
from mailweave.content.reductions import Reduction
from mailweave.envelope.fence import fenced_text
from mailweave.envelope.reasons import Reason, RungId, ThreadMember
from mailweave.envelope.vocab import (
    BLOCKING_NOT_TRIED,
    RESOLVED_LINKAGES,
    BudgetCapName,
    Completeness,
    ContentSource,
    Depth,
    EmptyDiagnosisStatus,
    Linkage,
    NotTriedWhy,
    Outcome,
    Role,
    Sufficiency,
    ToolName,
    Trust,
    WithheldCap,
)
from mailweave.errors import IN_BAND_CODES, ErrorCode
from mailweave.sealed_model import SealedModel


def parse_instant(field: str, value: str) -> datetime:
    """An RFC 3339 instant, or a `ValueError` naming the field (R-DISC-005).

    **The field, never the value.** This refusal used to read `f"{field}={value!r} is not
    an RFC 3339 instant"`, and one of its callers is `StoredCredentials.obtained_at`: a
    credential file corrupted so that the refresh token landed in the timestamp field put
    the token, whole and untruncated, into the `ValidationError`'s `msg` and from there
    into `TokenStoreError`. That is the second of R-SEC-043's three channels and no amount
    of care at the *rendering* end closes it, because the value is already inside the
    report by then (`mailweave.validation`). What the caller needs is which field failed,
    which is what it now gets.

    `fetched_at` and `verified_at` are contract R-08's freshness stamps and were typed
    `str, min_length=1`, so `fetched_at="not-a-real-timestamp-at-all"` was a conforming
    response. A stamp a reader cannot compare to the current time is not a freshness
    stamp; it is a string in the shape of one.

    Two conditions, both mechanical. It must parse as an ISO-8601 date **and** time, and
    it must carry a UTC offset - an instant with no timezone is ambiguous by exactly the
    amount that matters to a freshness claim.

    Deliberately *not* checked: whether the instant is plausibly recent. A "not in the
    future" or "not before Gmail existed" rule would make a valid response depend on the
    checking machine's clock, and clock skew failing a response is a worse defect than the
    one it would catch. The bound that matters and is knowable in-process is the ordering
    between the two stamps, which `Source` checks.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as failure:
        raise ValueError(
            f"{field} is not an RFC 3339 instant: a freshness stamp a reader cannot "
            "compare against the current time states nothing (contract R-08). The value "
            "is not quoted here: this same check runs on a field of the credential file"
        ) from failure
    if parsed.tzinfo is None:
        raise ValueError(
            f"{field} carries no UTC offset; an instant without one is ambiguous by "
            "exactly the amount a freshness claim is about (contract R-08). The value is "
            "not quoted here: this same check runs on a field of the credential file"
        )
    return parsed


class Frozen(SealedModel):
    """The wire schema's base: frozen, closed to extra fields, and self-checking.

    The self-checking half - re-establishing every invariant of this model and everything
    inside it where the wire form is produced, and refusing a subclass that would put a
    different reader in its place - is `SealedModel`'s, in `mailweave.sealed_model`, because
    two of the models in a response live outside this module and a base they could not import
    would cover only the ones that could.

    What is here is the configuration every wire model shares: frozen, and closed to fields the
    schema does not declare.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class Affordance(Frozen):
    """A concrete, executable call (contract R-07): tool name plus arguments.

    Executability against a live server is PART-04's job. What is enforced here is that
    an affordance names one of the four constant tools and carries arguments - an
    affordance with no arguments cannot retrieve anything specific.
    """

    tool: ToolName
    args: dict[str, JsonValue] = Field(min_length=1)

    def mentions(self, *values: str) -> bool:
        """True if any of `values` appears in the arguments, at any nesting depth."""
        wanted = {value for value in values if value}

        def walk(node: JsonValue) -> bool:
            if isinstance(node, str):
                return node in wanted
            if isinstance(node, list):
                return any(walk(item) for item in node)
            if isinstance(node, dict):
                return any(walk(item) for item in node.values())
            return False

        return walk(dict(self.args))


class WithheldRecord(Frozen):
    """AD A.7a's record shape - never a bare number (contract R-06)."""

    id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    cap: WithheldCap
    why: str = Field(min_length=1)
    affordance: Affordance


class Continuation(Frozen):
    """Access to the **remainder** of something this response started (navigation redesign).

    A continuation is not a narrowing. A `narrowing` travels on a *decline* and is the failed
    call with one dimension reduced - a change of scope. A continuation travels on a *served*
    response and preserves access to what that response did not carry: the rest of a batch of
    requested messages (`scope: "requested"`), or the other pages of a thread's structure
    (`scope: "thread"`). Following it makes progress by construction: the remainder is
    strictly smaller than the request and never contains what this response carried.

    `message_ids` is the batch form: the ids are the caller's own vocabulary and need no
    signing key. `positions` is the thread form, and its affordance is the **handle** form
    of the map call, `mailweave_thread_map(map_id, page)` (continuation correctness,
    2026-09-15): the page after this one is served only after the handle redeems - the
    thread untouched or unverifiable-and-unchanged by digest, and paged at the width the
    handle signed - so a thread that moved, or a paging that moved, is `handle_stale` with
    page 0 as the restart, never a page from a different starting position. A response that
    minted no handle offers no `thread` continuation. `remaining` is stated so a reader can
    see the size of what is left without executing it.
    """

    scope: str = Field(min_length=1)
    thread_id: str | None = None
    positions: tuple[int, int] | None = None
    message_ids: tuple[str, ...] = ()
    remaining: int = Field(gt=0)
    affordance: Affordance

    @model_validator(mode="after")
    def _the_remainder_is_stated_consistently(self) -> Continuation:
        if self.scope not in {"requested", "thread"}:
            raise ValueError(f"continuation scope {self.scope!r} is not requested | thread")
        if self.message_ids and self.remaining != len(self.message_ids):
            raise ValueError(
                f"continuation names {len(self.message_ids)} ids and says {self.remaining} remain"
            )
        if self.positions is not None:
            start, end = self.positions
            if end < start or start < 0:
                raise ValueError(f"continuation positions {self.positions} are not a range")
            if not self.message_ids and self.remaining != end - start + 1:
                raise ValueError(
                    f"continuation spans {end - start + 1} positions and says "
                    f"{self.remaining} remain"
                )
        if self.scope == "thread" and self.thread_id is None:
            raise ValueError("a thread continuation names its thread")
        return self


class WithheldGroup(Frozen):
    """Messages withheld from one thread, counted exactly, with the call that recovers them.

    **Round 29, R-MCP-033.** A thread `max_hit_threads` capped away has no map, so it has no
    stub row to carry (AD A.7a's own table says as much, and hands the caller
    `mailweave_thread_map{thread_id}`). Before this existed the response emitted one full
    record per observed message in such a thread, each naming the same thread and the same
    recovery call: at forty-five messages that was 23,220 characters of bookkeeping against a
    25,000-character host cap, and the response was refused with no mail in it at all.

    `message_count` is exact. It is derived from the same set difference every other number in
    a response is derived from - `certify()` asserts that the individual records plus these
    counts sum to `|withheld|` - so this is a count of a known enumeration, not an estimate and
    not a floor. Contract R-06 forbids *"a bare number"*: this is not bare. It names the thread,
    the cap that fired, why, and a call that returns the messages.
    """

    thread_id: str = Field(min_length=1)
    cap: WithheldCap
    why: str = Field(min_length=1)
    message_count: int = Field(gt=0)
    affordance: Affordance
    #: The retrieval rank this thread held when the response was assembled, so a client walks
    #: the groups best first (R-M2-096, 2026-09-15). `None` for a thread retrieval never
    #: ranked - one only the semantic pool's probes listed - which the wire writes after
    #: every ranked group. Never derived from what the caller is looking for.
    rank: int | None = Field(default=None, ge=0)


class WithheldTail(Frozen):
    """Threads withheld under one cap beyond the ones named, counted exactly (round 29).

    The response names `MAX_WITHHELD_GROUPS_NAMED` groups; this is the rest of them under one
    cap, as two exact counts and the call that widens the cap. The threads are not named here,
    and that is the compaction; they are not lost - `certify()` holds every id, the counts are
    the size of that set, and the affordance is a search at a wider width that maps them.
    """

    cap: WithheldCap
    why: str = Field(min_length=1)
    thread_count: int = Field(gt=0)
    message_count: int = Field(gt=0)
    affordance: Affordance


class OmissionSummary(Frozen):
    """Every omission this response made, as counts a client can read without parsing prose.

    **Round 29, R-MCP-033, requirement 2.** The refusal that started this said *"what is left is
    0 row(s), 0 source(s) and 45 withheld record(s)"* - in English, inside a remediation string.
    A client that wants to know how much it did not get had to parse a sentence. These are the
    same numbers as fields. The prose keeps saying it; the prose stops being the only place.
    """

    #: Messages in `H` that this response did not disclose. Equals
    #: `len(withheld) + sum(g.message_count for g in withheld_groups)`, asserted at mint time.
    withheld_messages: int = Field(ge=0)
    #: The same total, split by the cap that caused it. Sums to `withheld_messages`.
    withheld_by_cap: Mapping[str, int] = Field(default_factory=dict)
    #: Threads accounted for at thread granularity - one `withheld_groups[]` entry each,
    #: plus the threads counted inside `withheld_tail[]` without being named.
    withheld_threads: int = Field(ge=0)
    #: `not_included_sources[]` entries: whole sources this response did not carry.
    not_included_sources: int = Field(ge=0)
    #: **The ceiling that bound, explained once** (round 29). Every `withheld` record, group and
    #: not-included block that A.9a produced used to embed the same 206-character sentence
    #: about which cap forced the reduction and why the host cannot be handed truncation.
    #: Forty-five records carried it forty-five times. It is here once; the records say "see
    #: omission.bound" and keep the part that is theirs - which message, which thread, which
    #: cap, which call. `None` when the ladder reduced nothing.
    bound: str | None = None

    @model_validator(mode="after")
    def _the_split_sums_to_the_total(self) -> OmissionSummary:
        if self.withheld_by_cap and sum(self.withheld_by_cap.values()) != self.withheld_messages:
            raise ValueError(
                "withheld_by_cap does not sum to withheld_messages; a summary that does not "
                "add up is worse than no summary, because a client will trust it"
            )
        return self


class ScanScopeEntry(Frozen):
    """Per executed Gmail query (GMAIL-04, ADV-304).

    `H` is defined over the pages actually fetched, so an entry with `more_pages: true`
    and no widening affordance is non-conforming and is rejected here.
    """

    q: str = Field(min_length=1)
    rung: RungId
    page_size: int = Field(gt=0)
    pages_fetched: int = Field(ge=0)
    ids_returned: int = Field(ge=0)
    more_pages: bool
    affordance: Affordance | None = None

    @model_validator(mode="after")
    def _more_pages_needs_affordance(self) -> ScanScopeEntry:
        if self.more_pages and self.affordance is None:
            raise ValueError("more_pages=true without a widening affordance is non-conforming")
        return self


class PoolBlock(Frozen):
    """The scored retriever's candidate pool, disclosed by rule and size (I-1, EV-01 ii)."""

    scope_rule: str = Field(min_length=1)
    thread_count: int = Field(ge=0)
    message_count: int = Field(ge=0)
    why: str = Field(min_length=1)
    note: str = "pool membership creates no source and no stub rows (A.7a)"


class Shortlist(Frozen):
    """The declared, pre-registered selection rule that defines `H` from a scored retriever."""

    rule: str = Field(min_length=1)
    k: int = Field(gt=0)
    size: int = Field(ge=0)

    @model_validator(mode="after")
    def _size_within_k(self) -> Shortlist:
        if self.size > self.k:
            raise ValueError(f"shortlist size {self.size} exceeds declared k={self.k}")
        return self


class SemanticCost(Frozen):
    """AD D.5's cost disclosure. What the semantic escalation cost, and which model it used.

    **This block is the answer to "which tier decided this order?"** Without it a response
    whose every row was selected by Gmail's `q` - and which therefore carries no numeric
    score, per D.7 - was indistinguishable from one a cross-encoder had reordered: the rows
    were byte-identical and only their order differed. `rerank_pairs` being non-zero is what
    says a model looked at them, and `model_id` is what says which one.

    **`escalated` is not `rerank_pairs > 0`.** A query can escalate to L5, build a pool,
    embed it and have the D.7 gate decline the second tier; that is an escalation whose cost
    the caller paid and whose second tier did not run. Two fields, because they are two
    facts.

    D.5 also requires that public latency claims quote the escalated path as well as the easy
    one (T-RO2). This block is what makes that checkable from a response rather than from a
    benchmark.
    """

    escalated: bool
    embed_texts: int = Field(ge=0)
    rerank_pairs: int = Field(ge=0)
    #: Warm work only. The model load is per process and is reported separately, never folded
    #: into a per-query figure (PF-4's own registered rule).
    semantic_ms: int = Field(ge=0)
    #: The load, when *this* query was the one that paid it. `None` on every warm query.
    cold_load_ms: int | None = None
    #: `model@revision`, or `None` when no model was reached. AD D.8: a model change silently
    #: changes ranking, so the identity travels with the numbers.
    model: str | None = None
    #: Which of D.7's two tiers ordered the response.
    ordering_method: str = Field(min_length=1)

    @model_validator(mode="after")
    def _a_rerank_implies_a_model(self) -> SemanticCost:
        if self.rerank_pairs and self.model is None:
            raise ValueError(
                "a response reporting reranked pairs and no model identity cannot be "
                "reproduced, and AD D.8 requires the identity beside the numbers"
            )
        return self


class NotTriedEntry(Frozen):
    """A rung that did not run, and why (AD D.2 field note; AD-03)."""

    rung: str = Field(min_length=1)
    why: NotTriedWhy
    affordance: Affordance | None = None

    @property
    def blocks_not_found(self) -> bool:
        return self.why in BLOCKING_NOT_TRIED

    @model_validator(mode="after")
    def _blocking_needs_affordance(self) -> NotTriedEntry:
        if self.blocks_not_found and self.affordance is None:
            raise ValueError(
                f"not_tried[{self.rung}] why={self.why.value} must carry the affordance "
                "that would reach it (AD-03)"
            )
        return self


class EmptyDiagnosis(Frozen):
    """ADV-105's three states, made structurally distinct.

      * `status=complete, restores="before"` - a named restoring constraint;
      * `status=complete, restores=None`     - no single dropped constraint restores results;
      * `status=incomplete`                  - the probe budget ran out before all drops were tried.

    Conflating the last two was the defect: "unknown" was not a shape the schema could express.
    """

    status: EmptyDiagnosisStatus
    tried: tuple[str, ...]
    untried_drops: tuple[str, ...]
    restores: str | None = None
    affordance: Affordance | None = None

    @model_validator(mode="after")
    def _states_are_distinct(self) -> EmptyDiagnosis:
        if self.status is EmptyDiagnosisStatus.COMPLETE and self.untried_drops:
            raise ValueError("a complete diagnosis cannot have untried drops")
        if self.status is EmptyDiagnosisStatus.INCOMPLETE:
            if not self.untried_drops:
                raise ValueError("an incomplete diagnosis must name the drops it did not try")
            if self.restores is not None:
                raise ValueError(
                    "an incomplete diagnosis cannot also name a restoring constraint; "
                    "if a restore was found the probe was not budget-limited"
                )
        if self.restores is not None and self.affordance is None:
            raise ValueError("a named restoring constraint must carry the call that restores it")
        return self


class Counters(Frozen):
    """AD D.10's counter split. `quota_units` is diagnostic and says so."""

    http_requests: int = Field(ge=0)
    api_calls: int = Field(ge=0)
    quota_units: int = Field(ge=0)
    quota_units_label: str = "diagnostic; calibrated at G0 (PF-3)"


class RetrievalReport(Frozen):
    """Always present, hits or not (C-08, ROUTE-01)."""

    outcome: Outcome
    rungs: tuple[RungId, ...]
    hit_count_per_rung: tuple[int, ...]
    scan_scope: tuple[ScanScopeEntry, ...] = ()
    pool: PoolBlock | None = None
    shortlist: Shortlist | None = None
    semantic_cost: SemanticCost | None = None
    not_tried: tuple[NotTriedEntry, ...] = ()
    empty_diagnosis: EmptyDiagnosis | None = None
    budget_caps_hit: tuple[BudgetCapName, ...] = ()
    sufficiency: Sufficiency
    counters: Counters

    @property
    def blocking_not_tried(self) -> tuple[NotTriedEntry, ...]:
        return tuple(entry for entry in self.not_tried if entry.blocks_not_found)

    @model_validator(mode="after")
    def _rung_counts_align(self) -> RetrievalReport:
        if len(self.rungs) != len(self.hit_count_per_rung):
            raise ValueError(
                f"hit_count_per_rung has {len(self.hit_count_per_rung)} entries for "
                f"{len(self.rungs)} rungs"
            )
        if len(set(self.rungs)) != len(self.rungs):
            raise ValueError("a rung may appear in `rungs` only once")
        return self

    @model_validator(mode="after")
    def _od2_outcome_rule(self) -> RetrievalReport:
        """OD-2, enforced rather than documented.

        `not_found` is permitted only when no applicable rung is untried for budget, cap,
        timeout or error **and** `budget_caps_hit` is empty. Otherwise the honest outcome
        is `inconclusive`: we ran out of budget, we did not look everywhere applicable.
        """
        if self.outcome is not Outcome.NOT_FOUND:
            return self
        blockers = self.blocking_not_tried
        if blockers:
            names = ", ".join(f"{e.rung}:{e.why.value}" for e in blockers)
            raise ValueError(
                f"outcome=not_found is not permitted while rungs remain untried for "
                f"budget/cap/timeout/error ({names}); the honest outcome is inconclusive (OD-2)"
            )
        if self.budget_caps_hit:
            caps = ", ".join(cap.value for cap in self.budget_caps_hit)
            raise ValueError(
                f"outcome=not_found is not permitted while budget_caps_hit is non-empty "
                f"({caps}); the honest outcome is inconclusive (OD-2)"
            )
        return self

    @model_validator(mode="after")
    def _shortlist_implies_pool(self) -> RetrievalReport:
        if self.shortlist is not None and self.pool is None:
            raise ValueError(
                "a shortlist without a pool block: a scored retriever ran and its pool "
                "was not declared (EV-01 ii)"
            )
        return self

    @model_validator(mode="after")
    def _a_shortlist_implies_a_cost(self) -> RetrievalReport:
        """A scored retriever that ran and did not say what it cost is half a disclosure."""
        if self.shortlist is not None and self.semantic_cost is None:
            raise ValueError(
                "a shortlist without a semantic_cost block: the scored retriever ran and "
                "the response does not say what it cost or which model it used (AD D.5)"
            )
        return self


class Content(Frozen):
    """Mail-derived text, fenced and labelled untrusted (contract R-09)."""

    trust: Trust
    source: ContentSource
    text: str


class Score(Frozen):
    value: float
    method: str = Field(min_length=1)
    model: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    ordering_effect: bool


class SenderAuthentication(Frozen):
    """What the **receiving** server recorded about this message's authentication (INJ-05).

    **Receiver-recorded data, never MailWeave's verdict**, and the shape says so: there is no
    `passed` field and no `spf: bool`. `Authentication-Results` is a header a receiving MTA
    writes, and this server neither re-verifies it nor knows which MTA in the chain wrote the
    copy it is looking at. Reducing it to a boolean would turn somebody else's record into
    this connector's claim, in the one field a reader would most want to trust - which is
    exactly the connector-voiced surface INJ-02 forbids mail text from reaching, arriving the
    other way round.

    So the header travels fenced and verbatim, and this block asserts nothing beside it.

    **Whether the headers were read at all is `MessageRow.headers_observed`, and this block
    does not restate it.** An earlier draft carried an `observed: bool` here, which made a
    message with no `Authentication-Results` an `{observed: false, recorded: null}` object -
    a second spelling of the fact the row already states, on every row, at 50 characters
    each. `_identity_claims_rest_on_an_observation` refuses this block on a row that observed
    no headers, so the distinction is preserved without the duplicate: `authentication: null`
    beside `headers_observed: true` is "the headers were read and carried no record", and
    beside `headers_observed: false` it is "the headers were not read". A message that failed
    an authentication check is neither: it has a record, and the record is here.
    """

    recorded: Content | None = None
    #: The header was there and is longer than `MAX_AUTH_RECORD_CHARS`. **Not truncated** -
    #: this response refuses to rewrite a record it did not write, for `_sender_chosen_scalar`'s
    #: reason - so the row states that it exists and is oversize, and the caller reads the
    #: message directly. A bound is what lets the disclosure estimate charge this field at all;
    #: an `Authentication-Results` header has no length limit.
    oversize: bool = False

    @model_validator(mode="after")
    def _a_record_implies_an_observation(self) -> SenderAuthentication:
        if self.recorded is None and not self.oversize:
            raise ValueError(
                "an authentication block that discloses no record and declares none oversize "
                "states nothing this row's headers_observed does not already state; the way "
                "to say it is authentication: null"
            )
        if self.oversize and self.recorded is not None:
            raise ValueError(
                "a record that is both disclosed and declared oversize says two things; the "
                "bound is the reason it is not disclosed"
            )
        if self.recorded is None:
            return self
        # The bound is on the record, not on the fence around it: the producer and the
        # estimate both measure the header as written, and a check on the fenced text
        # refused every record within 46 characters of the bound (2026-09-23).
        record = fenced_text(self.recorded.text)
        if record is None:
            raise ValueError(
                "an authentication record is mail-derived text and travels fenced; this one "
                "is not inside a fence"
            )
        if not auth_record_fits(record):
            raise ValueError(
                f"an authentication record of {len(record)} characters exceeds the "
                f"{MAX_AUTH_RECORD_CHARS} the disclosure estimate charges for it; a header "
                "this response cannot charge is a header it cannot bound"
            )
        return self


class AttributionProvenance(StrEnum):
    """Where a row's `from_address` came from, stated on every row (2026-09-21).

    * `from_header` - the observed `From` header named exactly one address; it is the one.
    * `from_header_multiple` - the header named more than one; the first is given and the
      count says so. RFC 5322 allows this and it is rare; a reader who cares reads the map.
    * `from_header_absent` - the headers were observed and carried no parseable `From`.
    * `headers_not_observed` - this response did not read the message's headers at all, so
      whether it has a `From` is not a fact this response holds.

    The last two are different statements and the row keeps them apart for the reason
    `MailboxProvenance` and `SenderAuthentication` keep theirs: a negative derived from an
    absence is not a fact.
    """

    FROM_HEADER = "from_header"
    FROM_HEADER_MULTIPLE = "from_header_multiple"
    FROM_HEADER_ABSENT = "from_header_absent"
    HEADERS_NOT_OBSERVED = "headers_not_observed"


class Attribution(Frozen):
    """Who the message's own `From` header said sent it. **Not who sent it** (2026-09-21).

    **Why this exists.** Five exploratory runs on 2026-09-21 attributed every decision,
    approval and commitment to a named person, and every one of those attributions was read
    out of body text - "From fictional X" lines in the message - because the row carried no
    sender at all. Sender identity lived only in the thread-level participant index, which
    is address-keyed and deliberately has no display name. So the one thing a reader most
    wants per message, "who said this", was answerable only from the fenced, untrusted body,
    and the runs presented the answer as an explicit statement. This block is the per-message
    fact the row was missing, with its provenance beside it.

    **What it is not, and the shape says so.** `From` is a header the sender chose. It is
    not an authenticated identity, it is not a verified person, and no field here claims one:
    there is no `sender`, no `author`, no `verified`. `address` is the addr-spec the header
    stated, checked for shape and folded for comparison, and it is *not* fenced because an
    addr-spec that passes `is_an_address` cannot carry a sentence. `display_name` is the
    free text the sender put beside it, and it **is** fenced as untrusted third-party text
    from a header, exactly as a body is, because it is exactly as trustworthy as a body.
    What a receiving server recorded about authentication is `MessageRow.authentication`,
    beside this block and never folded into it. A signature line inside the body is body
    text and is not read here at all.

    `provenance` is on every row, including the ones with no address, so "this response did
    not look" and "this response looked and found none" are different rows.
    """

    provenance: AttributionProvenance
    #: The addr-spec the `From` header stated, folded (`query.analysis.fold`). `None`
    #: unless `provenance` is one of the two `from_header*` values.
    address: str | None = None
    #: The display name beside it, fenced (INJ-01, INJ-05). `None` when the header had none
    #: or was not observed. Sender-chosen text: as trustworthy as a body, labelled as such.
    display_name: Content | None = None
    #: How many addresses the header named. `1` for `from_header`, `> 1` for
    #: `from_header_multiple`, `0` otherwise.
    stated_addresses: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _the_address_rests_on_the_header(self) -> Attribution:
        named = self.provenance in (
            AttributionProvenance.FROM_HEADER,
            AttributionProvenance.FROM_HEADER_MULTIPLE,
        )
        if named and (self.address is None or not is_an_address(self.address)):
            raise ValueError(
                f"attribution {self.provenance.value} names no addr-spec, or names text that "
                "is not one; an address field is not a route for a sentence (R-SEC-030/032)"
            )
        if not named and (self.address is not None or self.display_name is not None):
            raise ValueError(
                f"attribution {self.provenance.value} carries an address or a display name; "
                "with no From observed neither is a fact this response holds"
            )
        if self.provenance is AttributionProvenance.FROM_HEADER and self.stated_addresses != 1:
            raise ValueError("from_header states exactly one address")
        if (
            self.provenance is AttributionProvenance.FROM_HEADER_MULTIPLE
            and self.stated_addresses < 2
        ):
            raise ValueError("from_header_multiple states more than one address")
        if not named and self.stated_addresses != 0:
            raise ValueError("no From observed, so no addresses were stated")
        untrusted = Trust.UNTRUSTED_THIRD_PARTY
        if self.display_name is not None and self.display_name.trust is not untrusted:
            raise ValueError("a display name is sender-chosen text and travels as untrusted")
        return self


class MailboxProvenance(Frozen):
    """Where in the mailbox this message lives, from the labels Gmail stated for it (OD-5).

    **The row says which region it came from, so a spam or trash result is identifiable
    without reading a reason string.** Before this field, a calling agent that received
    `outcome: answered` and a `role: matched` row had, as its only signal that the message
    sat in spam, the substring of the widening operator buried inside `reason` - a query-level
    declaration standing in for a row-level disclosure. The two are different statements and
    only one of them is about this message (R-RETR round 17, priority 4; OD-5 point 1).

    **`regions` is computed, not accepted.** `labels` is what the observation stated;
    `regions` is `constants.mailbox_regions_of` applied to it, so a caller cannot hand this
    model a provenance that disagrees with the labels the same model reports. That is the
    defect class OD-5 names - *"a value accepted from the caller when the same value is
    already derivable from what was observed"* - refused by construction rather than by a
    validator that compares two caller-supplied values. Deriving it from the **query** would
    be the same defect one layer out: the query says where MailWeave looked, the labels say
    where the message is, and only the second is a fact about the row.

    **`labels` is on the wire for the reason `CollapsedRun.member_ids` is**: without it a
    reader cannot check `regions` against anything, and a derived claim whose input the
    response withholds is a claim taken on trust. Gmail states label **ids**; a user's own
    label is an opaque `Label_N` id and its display name lives behind `users.labels.list`,
    which this server does not call, so no mail-derived text reaches the wire through this
    field.

    **`observed` is a third state and not a flag, and the two derived fields are absent when
    it is false.** A row whose labels no observation stated - Gmail returns them on
    `messages.get` and `threads.get`, not on `messages.list` - reports `observed: false`,
    `regions: null` and `outside_the_default_mailbox: null`, which says "this response does
    not know" rather than "this message is in neither region". It is the same distinction
    `observed_internal_dates` draws by *absence* for an id no observation placed (amendment
    A6).

    **Round 18 wrote that paragraph and the code contradicted it in two places** (R-RETR-039).
    `unobserved()` had no product caller at all - `Message.label_ids` defaulted to `()`, so an
    absent `labelIds` and a stated empty list were one value - and even when it was
    constructed, `outside_the_default_mailbox` computed `bool(())` and reported **false**: a
    field a caller branches on, stating "not spam" about a message whose labels were never
    seen. A field that reports a negative from an absence is worse than no field, because the
    caller cannot tell the two apart. So the third state is now producible - `assemble` calls
    `unobserved()` exactly when the observation stated no labels - and it is not
    representable as a negative, because `None` is not `False`.
    """

    observed: bool
    labels: tuple[str, ...] = ()

    @classmethod
    def of(cls, label_ids: tuple[str, ...]) -> MailboxProvenance:
        """The provenance of a message an observation stated the labels of."""
        return cls(observed=True, labels=label_ids)

    @classmethod
    def unobserved(cls) -> MailboxProvenance:
        """The provenance of a message no observation stated the labels of."""
        return cls(observed=False)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def regions(self) -> tuple[str, ...] | None:
        """The regions outside the default mailbox these labels place the message in.

        `None`, not `()`, when nothing was observed: an empty list is the claim "the labels
        place this message in neither region", and that claim needs labels to have been
        stated.
        """
        if not self.observed:
            return None
        return mailbox_regions_of(self.labels)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def outside_the_default_mailbox(self) -> bool | None:
        """The one field a caller needs to branch on: is this a spam or trash result?

        A caller that wants to know *which* reads `regions`; a caller that wants to know
        *whether* reads this, and neither has to parse a string to find out. `None` is the
        third answer and it is not a negative: no observation stated this message's labels,
        so this response cannot say.
        """
        regions = self.regions
        return None if regions is None else bool(regions)

    @model_validator(mode="after")
    def _labels_are_stated_ids_and_imply_an_observation(self) -> MailboxProvenance:
        for label in self.labels:
            if not label.strip() or not is_one_line(label):
                raise ValueError(f"label id {label!r} is not a stated Gmail label id")
        if self.labels and not self.observed:
            raise ValueError(
                "a provenance carrying labels was observed: `observed=False` means no "
                "observation stated this message's labels, which is not the same fact as "
                "an observation that stated none"
            )
        return self


class ThreadParticipant(Frozen):
    """One address and every message of this thread in which it took each role (C-02b).

    **Five disjoint lists, not one membership list with a role beside it.** An address can
    author one message of a thread and be merely named in the next, and a shape that can hold
    only one role per address would force a choice between those two facts - which is exactly
    how a mention comes to be reported as authorship, the failure STR-02 scores.

    **There is no `display_name` field, and its absence is the point.** A display name is
    mail-derived free text a sender chooses, so `From: "Ana Lee" <mallory@elsewhere.invalid>`
    is authored by `mallory@elsewhere.invalid` and by nobody called Ana. Putting the name on
    this model beside the address would put a spoofable string where a reader looks for an
    identity, which is INJ-05's whole subject. What survives is `distinct_display_names`, a
    count, which answers the one question a display name can honestly answer here: did this
    address present itself under more than one name in this thread?

    Contract STR-02 additionally requires From/To/Cc/Reply-To to be **exposed** as
    `{display_name, address}` pairs, never pre-joined. That is a header-disclosure obligation
    on the row, which is WS-11's surface and does not exist yet; this model is the retrieval
    index, and it is address-keyed, which is the half WS-05 owns.
    """

    address: str = Field(min_length=1)
    authored: tuple[str, ...] = ()
    coauthored: tuple[str, ...] = ()
    addressed: tuple[str, ...] = ()
    reply_to: tuple[str, ...] = ()
    mentioned: tuple[str, ...] = ()
    distinct_display_names: int = Field(default=0, ge=0)
    #: The names this address presented itself under, each fenced (INJ-01, INJ-05). This is
    #: STR-02's `{display_name, address}` pair, never pre-joined: the address is this model's
    #: key and the names sit beside it, so a renderer cannot put the name where a reader looks
    #: for the identity. `distinct_display_names` counts them and this lists them; the count
    #: is what a reader branches on ("did this address use more than one name?") and the list
    #: is what makes the count checkable.
    display_names: tuple[Content, ...] = ()

    @model_validator(mode="after")
    def _the_names_and_their_count_agree(self) -> ThreadParticipant:
        """A count beside an enumeration is a second claim about one fact (R-DISC-011)."""
        if self.display_names and len(self.display_names) != self.distinct_display_names:
            raise ValueError(
                f"{self.address} lists {len(self.display_names)} display names and counts "
                f"{self.distinct_display_names}"
            )
        for name in self.display_names:
            if name.trust is not Trust.UNTRUSTED_THIRD_PARTY:
                raise ValueError(
                    "a display name is a string the sender typed; it is untrusted "
                    "third-party data whatever else this response says (INJ-01, INJ-05)"
                )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def wrote_here(self) -> bool:
        """The predicate "what did X say" selects on: authorship only, never mention.

        Computed rather than accepted, for the reason `MailboxProvenance.regions` is: a
        caller-supplied "this person wrote in the thread" flag could disagree with the lists
        printed beside it, and this is the one field on this model an agent will branch on.
        """
        return bool(self.authored or self.coauthored)

    @model_validator(mode="after")
    def _the_address_is_an_address_and_the_roles_are_disjoint(self) -> ThreadParticipant:
        if not is_an_address(self.address):
            raise ValueError(
                "a participant key is an addr-spec and nothing else. `getaddresses` returns "
                "the whole header value for a header that is really prose, so a field named "
                "`address` that accepted it would be a route for mail text onto the wire "
                "under a name that says it is metadata (R-SEC-030/032)"
            )
        if set(self.authored) & set(self.coauthored):
            raise ValueError(
                "a message cannot be both solely authored and co-authored by one address"
            )
        overlap = (set(self.authored) | set(self.coauthored)) & set(self.mentioned)
        if overlap:
            raise ValueError(
                f"{sorted(overlap)} are listed as both authored by and merely mentioning "
                f"{self.address}. A mention is an address in text that this message's own "
                "address headers do not account for; the two sets are disjoint by "
                "construction and a response in which they are not has stopped "
                "distinguishing hearsay from authorship (contract C-02b, rubric STR-02)"
            )
        return self


#: The five role lists a `ThreadParticipant` carries, named once. Read by
#: `participants_within` and by `envelope.measure.citations_of`, so a sixth role added to the
#: model is a role both of them see rather than one they each have to be told about.
PARTICIPANT_ROLES: Final[tuple[str, ...]] = (
    "authored",
    "coauthored",
    "addressed",
    "reply_to",
    "mentioned",
)


def participants_within(
    participants: Sequence[ThreadParticipant], present: AbstractSet[str]
) -> tuple[ThreadParticipant, ...]:
    """The participant index narrowed to the messages a source actually discloses.

    `Source` refuses a participant record citing a message the source does not carry, so a
    collapse, a segment or a withheld row has to narrow the index rather than the source being
    made to accept a wider claim. An address whose every citation was removed drops out
    entirely, which is the honest result: this response says nothing about it.

    **One rule, in one place** (round 26, R-DISC-032). The expansion path had this narrowing
    and the search path did not, and the disclosure ladder had neither - which is what made a
    per-participant charge impossible to state without the ladder's number and the envelope's
    number disagreeing. `present` is a source's `disclosed_ids`: a message inside a declared
    collapsed run **is** disclosed and reachable, so an index entry citing one is a claim this
    response can still support.
    """
    kept: list[ThreadParticipant] = []
    for participant in participants:
        narrowed = participant.model_copy(
            update={
                role: tuple(mid for mid in getattr(participant, role) if mid in present)
                for role in PARTICIPANT_ROLES
            }
        )
        if any(getattr(narrowed, role) for role in PARTICIPANT_ROLES):
            kept.append(narrowed)
    return tuple(kept)


class ThreadStructureReport(Frozen):
    """What this thread's structural reconstruction could and could not establish (STR-01).

    Every field here is a **declared gap**. The reply tree itself is on the rows, one
    `linkage` each; this is the thread-level account of what the reconstruction did not
    reach, and it exists so that "could not be reconstructed" is a value a caller reads
    rather than a silence it has to infer from rows that look ordinary.

    `name_only_mentions_resolved` is a constant `false`, and it is on the wire for the reason
    `PoolBlock.note` is: a reader cannot otherwise tell whether an empty `mentioned` list
    means nobody was named or means MailWeave does not resolve names. It does not - a bare
    display name in a body is not mapped to an address, because that mapping needs a
    directory this product does not have and inventing one is the same class of guess as
    re-parenting an orphan by date.
    """

    linked: int = Field(ge=0)
    unlinked: int = Field(ge=0)
    #: Messages with no readable `From`. Their author is not inferred from anything.
    authorship_unknown: tuple[str, ...] = ()
    #: Messages whose text this response never observed, so mentions were not looked for in
    #: them. Not "no mentions": nothing looked.
    mentions_not_scanned: tuple[str, ...] = ()
    #: Messages sharing an `internalDate` with another row, whose relative position was
    #: therefore settled by message id rather than by time (STR-03, amendment A3).
    tied_on_internal_date: tuple[str, ...] = ()
    name_only_mentions_resolved: bool = False

    @model_validator(mode="after")
    def _the_one_claim_this_block_may_not_make(self) -> ThreadStructureReport:
        if self.name_only_mentions_resolved:
            raise ValueError(
                "name_only_mentions_resolved is false in every response this product can "
                "build: a display name in a body is not resolved to an address. A response "
                "asserting otherwise would be claiming a directory lookup that never "
                "happened (contract C-02b)"
            )
        return self


def _sender_chosen_scalar(value: str) -> str:
    r"""A scalar whose value a **sender** picked. One line, and nothing invisible in it.

    **Why this exists** (round 26, R-MCP-016). `envelope/reasons.py` states the rule for every
    metadata scalar - *"a multi-line value under any of these names is mail text taking a
    metadata field's route to the wire"* - and applies it through `ReasonScalar` to every
    reason parameter. `AttachmentMetadata` is the one model on this wire whose fields a sender
    chooses outright, and it was the one model the rule had never been applied to. A filename
    carrying a single `\n` therefore walked around the nonce fence entirely: the text mirror
    interpolates `filename`, `mime_type` and `part_id` into a line of MailWeave's own
    composing, so four attacker-chosen lines reached `split_fenced`'s residue - a forged
    `withheld` record, a forged source claiming `stated_total: 400`, an affordance MailWeave
    never offered, and a forged row line that reset the mirror's current id, so a **real**
    message body was re-attributed to a message that does not exist.
    `content.mime`'s `strip_invisible_characters` does not stop it: it removes Unicode format
    characters (category Cf), and a line feed is a C0 control (Cc).

    Refusal rather than escaping, for `envelope.fence`'s reason: a value this response cannot
    render honestly is refused, never quietly rewritten into something a caller would read as
    the sender's own. The cost is named in the round report - a message whose filename carries
    a control character makes `mailweave_get_attachment` decline for that message rather than
    disclose a filename MailWeave silently altered - and it is the right way round.
    """
    if not is_one_line(value):
        raise ValueError(
            "a sender-chosen scalar carries a line break. The text mirror writes this value "
            "into a line of its own composing, so a value spanning two lines is mail text "
            "outside the fence, in this connector's voice (R-MCP-016, contract R-09). Every "
            "boundary `str.splitlines()` recognises counts, not only \\n and \\r"
        )
    if any(not character.isprintable() and character != " " for character in value):
        raise ValueError(
            "a sender-chosen scalar carries a non-printable character. A filename, a MIME "
            "type and a part id are things a reader reads; a control character in one is a "
            "construct aimed at whatever renders it, never a fact about the attachment"
        )
    return value


#: A scalar a sender chose, bounded at the wire boundary. Named rather than repeated so that a
#: field added to this model - or to the next model built out of what a sender wrote - gets the
#: check by being annotated at all, which is the half `ReasonScalar` got right and this file
#: had not applied anywhere.
SenderScalar = Annotated[str, AfterValidator(_sender_chosen_scalar)]


class AttachmentMetadata(Frozen):
    """One attachment of a message, as B-04 permits it to be disclosed: metadata only.

    Every field is a fact of the carrying message's own `payload.parts` tree, read by the
    content pipeline through `messages.get(format=full)`. `users.messages.attachments.get`
    is off the surface (ADV-207), so there is no path in this build by which attachment
    *bytes* could reach this model - which is why there is no field for them, rather than a
    field that is always empty.

    `filename` has already had zero-width and bidi controls stripped by `content.mime`: an
    attachment filename is the canonical Trojan-Source target, and this model disclosing the
    raw string would undo that one layer after it was done.

    **Every field here is a string a sender chose**, which is what `SenderScalar` is for: this
    is the only model on this wire of which that is true, and until round 26 it was the only
    one carrying no bound of any kind. See `_sender_chosen_scalar`.

    `attachment_id` is Gmail's own handle for the bytes. It is disclosed because it is a
    fact the observation stated and a caller with a different client may want it; it is
    **not** an affordance, because no tool on this surface accepts it (B-04, E.3).
    """

    filename: SenderScalar = Field(max_length=MAX_ATTACHMENT_FILENAME_CHARS)
    mime_type: SenderScalar = Field(min_length=1, max_length=MAX_MIME_TYPE_CHARS)
    size: int = Field(ge=0)
    part_id: SenderScalar = Field(max_length=MAX_PART_ID_CHARS)
    attachment_id: SenderScalar | None = Field(default=None, max_length=MAX_ATTACHMENT_ID_CHARS)


class MessageRow(Frozen):
    """One message at one depth (contract R-01..R-04).

    **There is no `internal_date` parameter either** (amendment A6, round 8). A message's
    `internalDate` is a fact of the Gmail response that returned it, and since A6 the
    sealed observation records it, so the row had a caller-supplied copy of something the
    ledger already knew. The wire field D.2 documents is unchanged: `Envelope` writes it
    onto each row's wire form from the certificate's `observed_internal_dates`, which is
    the same route `thread_id` takes one level down. A row whose id no observation placed
    carries no `internal_date` on the wire, which is the honest answer - the alternative is
    a timestamp with nothing behind it.

    **`mailbox` is not a claim about the query** (OD-5, round 18). It is derived from the
    labels the observation that returned this message stated, which is why
    `MailboxProvenance` computes it rather than accepting it: a provenance read off the `q`
    that found the row would be a value accepted from the caller when it was already
    derivable from what was observed, and that is the defect this repository has now found
    more than a dozen times. `assemble` builds it from `Message.label_ids` of the
    `threads.get` response the row comes out of, and from nothing else.

    **There is no `thread_id` parameter** (R-DISC-011, round 7). A row lives inside
    exactly one `Source`, and that source already states the thread; the row's copy was a
    second statement of the same fact, and round 6 could only compare the two and refuse a
    disagreement. Comparing is not the same as not being able to disagree: `Source` now
    writes the thread onto every row's wire form from its own `thread_id`, so the wire
    field D.2 documents is still there and there is no longer a place to put a different
    value. Which thread the *source* is entitled to claim is checked one layer up, against
    the observation that returned each id (`Envelope._disclosed_rows_sit_in_the_thread_
    they_were_observed_in`).
    """

    id: str = Field(min_length=1)
    position: int = Field(ge=0)
    role: Role
    reason: Reason
    constraint_coverage: tuple[str, ...] = ()
    #: Where the mailbox holds this message, from its own observed labels (OD-5, A9-A1).
    #: Required rather than defaulted: a row that omitted it would be a row whose provenance
    #: a reader has to infer, which is the state this field exists to end.
    mailbox: MailboxProvenance
    depth: Depth
    #: How this message's reply parent was determined, or which gap stands in its place
    #: (AD D.6, contract C-02a). Required rather than defaulted, and for the reason
    #: `mailbox` is: a row that omitted it would be a row whose linkage a reader has to
    #: infer, and the inference every reader makes is the one C-02a forbids - that a row
    #: printed after another is a reply to it.
    linkage: Linkage
    #: The message id of the reply parent, when there is one. `None` for every declared
    #: gap, which the validator below holds to rather than trusting the caller to pair the
    #: two consistently.
    reply_parent_id: str | None = None
    #: Whether this message carries a `Message-ID` of its own, so a reply to it can name it
    #: (AD D.4a, R-RETR-054). A fact about *other* messages' prospects rather than about
    #: this one's link, and the compensating half of D.4a's narrow reading: a message with
    #: no `Message-ID` whose own `In-Reply-To` resolves is stated as linked, and without
    #: this field it was byte-identical on the wire to an ordinary reply while its own
    #: well-formed child reported "named parent is not in this thread" about a parent that
    #: is in this thread. `None` is the third state - no headers were observed, so whether
    #: this message can be named is not known - and the validator below holds it to exactly
    #: the linkage that says so, which is what stops the default from becoming a silence.
    can_be_a_parent: bool | None = None
    reductions: tuple[Reduction, ...] = ()
    #: The attachments the carrying message declares, metadata only (B-04, ADV-207).
    #: Empty on a row whose body this response never fetched, because the parts tree comes
    #: from `messages.get(format=full)` and an empty tuple beside an unfetched body would be
    #: the claim "this message has no attachments" made by a response that never looked.
    #: `mailweave_get_attachment` is the tool that narrows it to one part.
    attachments: tuple[AttachmentMetadata, ...] = ()
    #: Whether this message's own headers were observed at all. The two identity fields
    #: below are `None` without it, because with no headers seen neither is a fact this
    #: response holds - the absence-is-not-a-negative rule `MailboxProvenance` established.
    headers_observed: bool = False
    #: Whether the headers named a `Reply-To` that is not the `From` address (INJ-05, SN
    #: §7.2). `None` when no observation stated this message's headers: a `false` there would
    #: be a negative claim derived from an absence, which is the shape OD-5 ended for
    #: `MailboxProvenance` and this field inherits.
    reply_to_differs: bool | None = None
    #: What the receiving server recorded about authentication. Never this server's verdict.
    authentication: SenderAuthentication | None = None
    #: Who the `From` header said sent this message, with where that came from (2026-09-21).
    #: Required, on every row: the default is the honest one for a row built with no
    #: observation behind it, and a row whose headers were read replaces it with what they
    #: said. See `Attribution` for what this is not.
    attribution: Attribution = Field(
        default_factory=lambda: Attribution(provenance=AttributionProvenance.HEADERS_NOT_OBSERVED)
    )
    unabridged: Affordance
    score: Score | None = None
    content: Content | None = None

    @property
    def rendered_reason(self) -> str:
        return self.reason.render()

    @field_serializer("reason")
    def _render_reason(self, reason: Reason) -> str:
        """AD D.2 carries `reason` as a mechanical string; the typed form is kept beside it.

        The string is what a reading agent sees; `reason_detail` is what a harness joins
        on, so PART-07's "mechanical, never decorative" is checkable without regex-ing
        prose.
        """
        return reason.render()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def reason_detail(self) -> dict[str, JsonValue]:
        return dict(self.reason.model_dump(mode="json"))

    @model_validator(mode="after")
    def _depth_and_content_agree(self) -> MessageRow:
        if self.depth is Depth.RAW:
            raise ValueError("raw is never inline (AD D.1/D.4)")
        if self.depth is Depth.STUB and self.content is not None:
            raise ValueError("a stub row carries no content by definition")
        if self.depth is not Depth.STUB and self.content is None:
            raise ValueError(f"depth={self.depth.value} requires content")
        if self.role is Role.STUB and self.depth is not Depth.STUB:
            raise ValueError("role=stub cannot carry a body; use the depth field to declare depth")
        return self

    @model_validator(mode="after")
    def _a_parent_is_named_exactly_when_one_was_found(self) -> MessageRow:
        """The link and the gap cannot disagree, because only one of them is expressible.

        A `linkage` of `in-reply-to` or `references` **is** the statement "a parent was found
        in this thread from this message's own headers", so a row carrying one and no
        `reply_parent_id` claims a link it does not name. The inverse is the one that
        matters more: a `reply_parent_id` beside a declared gap would be a parent asserted
        while the same row says none was determined, which is C-02a's silent re-parenting
        arriving through the schema instead of through the reconstruction.

        A row is also never its own parent. That shape is a real one - a message whose
        `References` names its own `Message-ID` - and `reply_tree` refuses it as the
        one-node case of a cycle; refusing it here as well is the second layer, because this
        model is reachable from callers `reply_tree` is not on the path of.
        """
        linked = self.linkage in RESOLVED_LINKAGES
        if linked and self.reply_parent_id is None:
            raise ValueError(
                f"message {self.id} declares linkage={self.linkage.value}, which says a "
                "parent was found in this thread, and names none. A link that cannot say "
                "which message it points at is not a link (contract C-02a)"
            )
        if not linked and self.reply_parent_id is not None:
            raise ValueError(
                f"message {self.id} names reply_parent_id={self.reply_parent_id!r} while "
                f"declaring linkage={self.linkage.value}, which is a declared gap. A parent "
                "beside a declared gap is exactly the silent re-parenting C-02a forbids, "
                "arriving through the schema rather than through the reconstruction"
            )
        if self.reply_parent_id == self.id:
            raise ValueError(f"message {self.id} is named as its own reply parent")
        return self

    @model_validator(mode="after")
    def _not_knowing_whether_a_message_can_be_named_is_exactly_one_linkage(self) -> MessageRow:
        """R-RETR-054: the third state of `can_be_a_parent` is not a spare default.

        `can_be_a_parent is None` means *this response observed no headers for this message*,
        and that is the same fact `Linkage.HEADERS_UNOBSERVED` states - `reply_tree` computes
        both from the one `headers_observed` flag. Tying them here is what makes the field
        impossible to omit: a row that declares any other linkage has had its headers read,
        so whether it carries a `Message-ID` is something this response knows and must say.
        Left as a plain default it would have been absent from most rows, which is the state
        R-RETR-054 filed - the compensating half of D.4a's reading not reaching the caller.
        """
        unobserved = self.linkage is Linkage.HEADERS_UNOBSERVED
        if unobserved and self.can_be_a_parent is not None:
            raise ValueError(
                f"message {self.id} declares linkage={self.linkage.value}, which says this "
                "response observed none of its headers, and then states "
                f"can_be_a_parent={self.can_be_a_parent}: whether a message carries a "
                "`Message-ID` is read off the headers, so a row that saw none cannot know it"
            )
        if not unobserved and self.can_be_a_parent is None:
            raise ValueError(
                f"message {self.id} declares linkage={self.linkage.value} - so its headers "
                "were observed - and leaves can_be_a_parent unstated. A message with no "
                "`Message-ID` is one no reply can ever name, and without this field it is "
                "indistinguishable on the wire from an ordinary reply while its own child "
                "reports a parent it cannot find (AD D.4a, R-RETR-054)"
            )
        return self

    @model_validator(mode="after")
    def _constraint_coverage_is_a_set_of_named_constraints(self) -> MessageRow:
        """R-DISC-006: the field was live, unvalidated and referenced by nothing.

        It is query-conditioning evidence WS-04 has not built yet, which is the reason to
        constrain it now rather than later: the first producer of an unvalidated field
        decides what it means, and by then a response claiming to have matched a
        constraint the user never wrote is already on the wire. Two things are checkable
        without WS-04 - the entries are named and distinct here, and `Envelope` checks
        them against the constraints `asked_for` says the query actually carried.
        """
        if any(not name.strip() for name in self.constraint_coverage):
            raise ValueError(
                f"constraint_coverage on message {self.id} carries an unnamed constraint"
            )
        if len(set(self.constraint_coverage)) != len(self.constraint_coverage):
            raise ValueError(
                f"constraint_coverage on message {self.id} names the same constraint twice; "
                "it is the set of constraints this message satisfies, not a tally"
            )
        return self

    @model_validator(mode="after")
    def _identity_claims_rest_on_an_observation(self) -> MessageRow:
        """INJ-05's fields say what was observed, never what was absent.

        Both rules refuse a **negative claim derived from an absence** - the shape OD-5 ended
        for `MailboxProvenance` and that this block would otherwise reintroduce in the one
        place a reader most wants a positive answer. With no headers observed, "the Reply-To
        is the From" is not something this response knows, and `Authentication-Results` is one
        of the headers it did not see.
        """
        if self.reply_to_differs is not None and not self.headers_observed:
            raise ValueError(
                f"row {self.id} states reply_to_differs with no headers observed; with none "
                "seen, whether the Reply-To differs from the From is not a fact this response "
                "holds"
            )
        if self.authentication is not None and not self.headers_observed:
            raise ValueError(
                f"row {self.id} states an authentication record and observed no headers at "
                "all; Authentication-Results is one of this message's headers"
            )
        unobserved = AttributionProvenance.HEADERS_NOT_OBSERVED
        observed_from = self.attribution.provenance is not unobserved
        if observed_from and not self.headers_observed:
            raise ValueError(
                f"row {self.id} states an attribution of {self.attribution.provenance.value} "
                "and observed no headers at all; From is one of this message's headers"
            )
        if not observed_from and self.headers_observed:
            raise ValueError(
                f"row {self.id} observed headers and states headers_not_observed for its "
                "attribution; with the headers read, whether they carried a From is known"
            )
        return self

    @model_validator(mode="after")
    def _a_thread_member_reason_names_this_rows_own_position(self) -> MessageRow:
        """R-DISC-011 sweep: `ThreadMember` restated the row's place, unchecked.

        `reason` is the mechanical account of *why* this row is here, and for a thread map
        row the mechanism is "it sits at position p of thread t". Both halves are facts the
        payload already carries - `position` on this row, `thread_id` on the enclosing
        `Source` - and neither was compared with the reason's copy, so a row at position 3
        could render "thread map row: position 41 of thread t9" and every validator agreed.
        A reason that misstates the mechanism is the decorative rationale PART-07 forbids,
        wearing a mechanical shape.

        The position half is checkable here; `Source` checks the thread half, which is the
        only place the thread is known. The parameters are not removed because `render()`
        is what a reading agent sees and it has no access to the row - which is recorded in
        the round 7 audit as a *checked* restatement rather than a derived one.
        """
        if isinstance(self.reason, ThreadMember) and self.reason.position != self.position:
            raise ValueError(
                f"message {self.id} sits at position {self.position} but its thread_member "
                f"reason renders position {self.reason.position}: the reason is the "
                "mechanical account of the row it is attached to, not a second, "
                "independent claim about where the message sits (PART-07, R-DISC-011)"
            )
        return self

    @model_validator(mode="after")
    def _reductions_have_an_unabridged_path(self) -> MessageRow:
        # `unabridged` is required by the type, so this checks the remaining half of
        # DISC-03: a reduction must be a *declared* removal, with a count.
        #
        # **Round 27, R-MCP-023.** This asked the question itself and got a different answer
        # from `Reduction`'s own validator, which exempts the kinds that are declarations
        # rather than removals - so an ordinary `multipart/alternative` message built a
        # `Reduction` the content layer accepted and a `MessageRow` the wire layer refused,
        # and the tool answered `-32603`. It now asks the record, which is where the rule is.
        for reduction in self.reductions:
            if reduction.is_a_silent_reduction:
                raise ValueError(
                    f"reduction {reduction.kind.value} on message {self.id} declares no size"
                )
        return self


#: How many clashing positions an occupancy error names before it summarises the rest.
_CLASHES_SHOWN = 4


class CollapsedRun(Frozen):
    """A declared run of stub rows (contract R-06, AD D.2).

    `member_ids` is carried on the wire in addition to D.2's positions/count. Without it
    a reviewer cannot compute the disclosed set from the response alone, and EV-01's
    "a member of a declared collapsed run counts" becomes an assertion about data the
    response does not contain. IDs carry no mail content.
    """

    positions: tuple[int, int]
    count: int = Field(gt=0)
    member_ids: tuple[str, ...]
    why: str = Field(min_length=1)
    affordance: Affordance

    @model_validator(mode="after")
    def _run_is_self_consistent(self) -> CollapsedRun:
        start, end = self.positions
        if end < start:
            raise ValueError(f"collapsed run positions {self.positions} are reversed")
        if start < 0:
            # Amendment A3's lower half. `MessageRow.position` has carried `ge=0` since
            # WS-03; a run's positions carried no bound in either direction, so a run
            # could begin before the thread it claims to describe. The upper half needs
            # `stated_total` and so lives on `Source`, where the thread's length is known.
            raise ValueError(
                f"collapsed run positions {self.positions} begin before the start of the "
                "thread: a position is a 0-based index into chronological message order, "
                "so the first message of a thread is at 0 (amendment A3)"
            )
        span = end - start + 1
        if span != self.count:
            raise ValueError(
                f"collapsed run spans {span} positions but declares count={self.count}"
            )
        if len(self.member_ids) != self.count:
            raise ValueError(
                f"collapsed run declares count={self.count} but lists "
                f"{len(self.member_ids)} member ids"
            )
        if len(set(self.member_ids)) != len(self.member_ids):
            raise ValueError("collapsed run lists a member id twice")
        return self


class Source(Frozen):
    """One thread as represented in this response (contract R-05, R-08).

    `map_id` is a claim - "this is a map of the thread" - and R-DISC-001 found it could be
    made while 88% of the thread was represented nowhere at all: not as a row, not inside
    a collapsed run, not as a withheld record. The claim is now derived from the
    enumeration in `_a_claimed_map_accounts_for_every_message`: a source carrying a
    `map_id` must account for every one of `stated_total` positions, and the accounting is
    computed from the payload rather than asserted beside it.

    **There is no `history_id` parameter** (amendment A6, round 8). A thread's `historyId`
    is a fact of the response that returned the thread and nothing in this model reads it,
    so it was a caller assertion with no check and no consumer. Since A6 the seal records
    it, and `Envelope` writes it onto this source's wire form from the certificate. The
    wire field is unchanged; the place to put a wrong value is gone.
    """

    thread_id: str = Field(min_length=1)
    stated_total: int = Field(ge=0)
    included: int = Field(ge=0)
    included_as_stub: int = Field(ge=0)
    completeness: Completeness = Completeness.AS_REPORTED_BY_SOURCE
    source: str = "gmail.threads.get"
    fetched_at: str = Field(min_length=1)
    verified_at: str | None = None
    map_id: str | None = None
    messages: tuple[MessageRow, ...] = ()
    collapsed_runs: tuple[CollapsedRun, ...] = ()
    #: Messages of *this* thread that this response accounts for as `WithheldRecord`s.
    #: Listing an id here is not what withholds it - the disposition ledger decides that -
    #: and `Envelope` refuses a source naming an id no withheld record backs, so this
    #: cannot become a second, divergent claim about the same fact.
    withheld_here: tuple[str, ...] = ()
    #: **Which page of the thread's structure this source carries as rows** (navigation
    #: redesign, 2026-09-14). A thread map is served in pages of `page_size` positions;
    #: `page` is the zero-based page whose positions are rows here, `pages` how many there
    #: are. All three are stated so a reader can reach any page in one call without a
    #: listed affordance for each: `mailweave_thread_map(thread_id, page=k)` for the k-th.
    #: `None` on a source that is not a page - a search source, or a read - and the three
    #: travel together or not at all.
    page: int | None = None
    page_size: int | None = None
    pages: int | None = None
    #: The address-keyed participant index for this thread (C-02b, STR-02). Empty for a
    #: source whose rows carried no readable address header at all, which the structural
    #: report below distinguishes from a thread nobody wrote in.
    participants: tuple[ThreadParticipant, ...] = ()
    #: What the structural reconstruction could not establish about this thread (STR-01).
    #: `None` only where no map was built; every mapped source carries one, so an absent
    #: block is never a way of saying "nothing was missing".
    structure: ThreadStructureReport | None = None

    @field_serializer("messages")
    def _rows_carry_this_sources_thread(
        self, messages: tuple[MessageRow, ...], info: SerializationInfo
    ) -> list[dict[str, JsonValue]]:
        """Write D.2's `thread_id` onto each row's wire form from the source's own (R-DISC-011).

        The field a reader sees is unchanged; what changed is that there is no longer a
        second place to put it. `MessageRow` has no `thread_id` parameter, so a row cannot
        be given a thread that disagrees with the source it is inside - round 6 could only
        compare the two and raise, which leaves the wrong value expressible right up to the
        moment of construction and requires the check to be remembered forever.

        Emitted in D.2's order (`id`, `thread_id`, `position`, ...) rather than appended,
        because a computed field serialises last and this one belongs where the schema
        sketch puts it.
        """
        mode = "json" if info.mode_is_json() else "python"
        rendered: list[dict[str, JsonValue]] = []
        for row in messages:
            dumped: dict[str, JsonValue] = row.model_dump(mode=mode)
            with_thread: dict[str, JsonValue] = {"id": dumped["id"], "thread_id": self.thread_id}
            with_thread.update({key: value for key, value in dumped.items() if key != "id"})
            rendered.append(with_thread)
        return rendered

    @property
    def disclosed_ids(self) -> frozenset[str]:
        """Every message ID present at any depth, collapsed-run members included (A.7a `R`)."""
        ids = {row.id for row in self.messages}
        for run in self.collapsed_runs:
            ids.update(run.member_ids)
        return frozenset(ids)

    @property
    def complete_as_reported(self) -> bool:
        return self.included == self.stated_total

    @property
    def collapsed_member_ids(self) -> tuple[str, ...]:
        """Every collapsed-run member, in order, repeats included.

        Returned with repeats so a validator can *see* them. `_counts_match_the_payload`
        refuses any, which is what makes the deduplicated count below equal to the length
        of this tuple for every `Source` that exists (R-RETR-001).
        """
        return tuple(mid for run in self.collapsed_runs for mid in run.member_ids)

    @property
    def accounted_for(self) -> int:
        """Positions this source accounts for: rows, collapsed-run members, withheld records.

        The three dispositions AD A.7a allows a message to have. Nothing else counts, and
        in particular a `stated_total` a thread never enumerated does not.
        """
        return self.included + len(set(self.withheld_here))

    @model_validator(mode="after")
    def _freshness_stamps_are_instants_in_order(self) -> Source:
        """R-DISC-005: both R-08 stamps must be instants, and a re-check follows the fetch."""
        fetched = parse_instant("fetched_at", self.fetched_at)
        if self.verified_at is None:
            return self
        verified = parse_instant("verified_at", self.verified_at)
        if verified < fetched:
            raise ValueError(
                f"verified_at={self.verified_at!r} is before fetched_at={self.fetched_at!r}: "
                "a freshness re-check cannot precede the fetch it re-checks (contract R-08)"
            )
        return self

    @model_validator(mode="after")
    def _the_structure_this_source_states_is_about_this_source(self) -> Source:
        """Every structural claim names a message this source actually carries (WS-05).

        Three ways a structural block can be wider than the payload it describes, and all
        three are the same defect - a claim about messages that are not here:

          * a `reply_parent_id` pointing outside this thread. A parent is a message of the
            **same** thread by construction: `reply_tree` resolves only against the ids of
            the thread it was given, and a reference it cannot resolve there becomes
            `UNRESOLVED_PARENT` with the named `Message-ID` for L4 to chase. A row naming a
            parent this source does not *account for* would be a link asserted across a
            boundary the reconstruction never crossed. **Accounting for is not disclosing**
            (R-M2-077): a parent listed in `withheld_here` is referenced - the withheld record
            carries the call that fetches it - and its content is not here, and both of those
            are true at once. Reading this as "the parent must be a row" made every
            `mailweave_get_messages` for a reply whose ancestors were not also requested
            unbuildable;
          * a participant record citing a message id this source does not disclose;
          * a declared gap - unknown authorship, unscanned text, a tied timestamp - naming
            one.

        `linked`/`unlinked` are checked against the rows rather than accepted, so the summary
        cannot disagree with the rows it summarises. Round 18's lesson stated as a rule: a
        count beside an enumeration is a second claim about one fact, and the enumeration is
        the one with evidence behind it.
        """
        present = self.disclosed_ids
        # A reply parent may be referenced through any disposition this source gives it -
        # row, collapsed-run member, or withheld record (R-M2-077). The participant and gap
        # checks below stay on `present`: a citation is a claim about content this source
        # shows, which a withheld record does not.
        accounted = present | frozenset(self.withheld_here)
        for row in self.messages:
            if row.reply_parent_id is not None and row.reply_parent_id not in accounted:
                raise ValueError(
                    f"message {row.id} names reply parent {row.reply_parent_id!r}, which "
                    f"source {self.thread_id} neither carries nor withholds. A reply parent "
                    "is a message of the same thread; a reference this source does not "
                    "account for is a declared gap with the named Message-ID, never a link "
                    "across a boundary the reconstruction never crossed (contract C-02a)"
                )
        for participant in self.participants:
            cited = set(
                participant.authored
                + participant.coauthored
                + participant.addressed
                + participant.reply_to
                + participant.mentioned
            )
            outside = sorted(cited - present)
            if outside:
                raise ValueError(
                    f"participant {participant.address} is recorded in {outside}, which "
                    f"thread {self.thread_id} does not disclose. A participant index is an "
                    "index of this thread's own messages"
                )
        if len({participant.address for participant in self.participants}) != len(
            self.participants
        ):
            raise ValueError(
                "a participant index lists one address twice; it is keyed on the address, "
                "so two entries for one address are two answers to one question"
            )
        report = self.structure
        if report is None:
            return self
        declared = set(
            report.authorship_unknown + report.mentions_not_scanned + report.tied_on_internal_date
        )
        outside = sorted(declared - present)
        if outside:
            raise ValueError(
                f"the structural report for thread {self.thread_id} declares gaps about "
                f"{outside}, which this source does not disclose"
            )
        linked = sum(1 for row in self.messages if row.linkage in RESOLVED_LINKAGES)
        if (report.linked, report.unlinked) != (linked, len(self.messages) - linked):
            raise ValueError(
                f"the structural report says linked={report.linked}/"
                f"unlinked={report.unlinked} while the rows of thread {self.thread_id} say "
                f"{linked}/{len(self.messages) - linked}. A summary that can disagree with "
                "the enumeration beside it is a second claim about one fact"
            )
        return self

    @model_validator(mode="after")
    def _counts_match_the_payload(self) -> Source:
        """PART-01/PART-02: the response's own account of what it contains must be accurate.

        Note on `included`: contract R-05 defines it as "the count included in this
        response", with `included_as_stub` the subset carried as stubs only - so a
        42-message thread shown as 7 bodies and 35 stubs reports `included=42`. AD D.2's
        worked example originally read the two as disjoint (`included=7`). Amendment A4
        (round 5) ruled R-05 correct and changed the worked example, on the grounds this
        module already encodes elsewhere: a stub row is disclosed, not omitted, which is
        why the ledger refuses a withheld record for one. The divergence is settled, not
        merely recorded.
        """
        collapsed_ids = self.collapsed_member_ids
        # R-RETR-001: `CollapsedRun` refuses a member listed twice *within itself*, and
        # nothing compared two runs against each other. Summing the run lengths then
        # counted one message once per run it appears in, so `included` could reach
        # `stated_total` - "this map is complete" - while a real message was represented
        # nowhere. The count is taken from the deduplicated union, and a cross-run repeat
        # is refused outright rather than quietly collapsed: two runs claiming the same
        # message disagree about where it sits in the thread, and a map that cannot say
        # where a message sits is not a map.
        repeated_across_runs = sorted(
            mid for mid, times in Counter(collapsed_ids).items() if times > 1
        )
        if repeated_across_runs:
            raise ValueError(
                f"messages appear in more than one collapsed run: {repeated_across_runs}. "
                "A message has one position and one disposition (A.7a); counting it once "
                "per run inflates included/accounted_for and lets a map claim completeness "
                "while a message is unaccounted for anywhere (PART-05, R-06)"
            )
        collapsed_members = len(set(collapsed_ids))
        row_ids = [row.id for row in self.messages]
        if len(set(row_ids)) != len(row_ids):
            raise ValueError("a message appears twice in the same source")
        overlap = set(row_ids) & set(collapsed_ids)
        if overlap:
            raise ValueError(f"messages both present as rows and inside a collapsed run: {overlap}")

        present = len(set(row_ids) | set(collapsed_ids))
        if self.included != present:
            raise ValueError(
                f"included={self.included} but {present} messages are present in the payload"
            )
        stubs = sum(1 for row in self.messages if row.depth is Depth.STUB) + collapsed_members
        if self.included_as_stub != stubs:
            raise ValueError(
                f"included_as_stub={self.included_as_stub} but {stubs} messages are stubs"
            )
        if self.included > self.stated_total:
            raise ValueError(
                f"included={self.included} exceeds stated_total={self.stated_total}: "
                "stated_total is what the source reported, not a guess"
            )
        return self

    @model_validator(mode="after")
    def _a_thread_member_reason_names_this_thread(self) -> Source:
        """The thread half of the `ThreadMember` check (R-DISC-011 sweep).

        The row can check the position it renders because it knows its own; only the source
        knows the thread. Without this, `reason` was the one remaining field able to name a
        thread other than the source's, now that `MessageRow.thread_id` is gone - and it is
        the field a reading agent is shown, so a wrong value there misleads the reader even
        while every count in the payload is right.
        """
        wrong = [
            (row.id, row.reason.thread_id)
            for row in self.messages
            if isinstance(row.reason, ThreadMember) and row.reason.thread_id != self.thread_id
        ]
        if wrong:
            shown = "; ".join(f"{mid} renders thread {thread!r}" for mid, thread in wrong)
            raise ValueError(
                f"source {self.thread_id} carries thread_member reasons naming another "
                f"thread: {shown}. The rendered reason is what the reading agent is shown, "
                "so a thread named there and nowhere else is a claim no count in this "
                "payload contradicts (PART-07, R-DISC-011)"
            )
        return self

    @model_validator(mode="after")
    def _one_position_holds_one_disposition(self) -> Source:
        """PART-05, R-06: no two dispositions may claim the same slot in the thread.

        R-RETR-001 was closed at the level of *identity* - a message may not appear in two
        collapsed runs - and `_counts_match_the_payload` still enforces that. R-RETR-002 is
        the same defect at the level of *place*, which that check cannot see: two runs with
        entirely disjoint member ids, both declaring `positions=(1, 5)`, agree about nothing
        except that five messages sit in the same five slots. `included` reaches
        `stated_total`, the map reports itself complete, and half of what it claims to
        enumerate is backed by no thread position at all.

        The rationale R-RETR-001 was fixed under says it in one line - "a message has one
        position and one disposition" - and only the second half was checked. A position is
        occupied by a row or by one collapsed run, never by both and never twice, so the
        occupancy is computed from the payload here rather than trusted alongside it.

        Rows are included because a row is a disposition like any other: a stub row at
        position 4 and a collapsed run spanning 3-6 make contradictory claims about slot 4,
        and which one the reader believes changes what the thread contains.
        """
        occupant: dict[int, str] = {}
        clashes: dict[int, tuple[str, str]] = {}

        def claim(position: int, by: str) -> None:
            held = occupant.get(position)
            if held is None:
                occupant[position] = by
            else:
                clashes[position] = (held, by)

        for row in self.messages:
            claim(row.position, f"message {row.id}")
        for run in self.collapsed_runs:
            start, end = run.positions
            for position in range(start, end + 1):
                claim(position, f"collapsed run {run.positions}")

        if clashes:
            shown = "; ".join(
                f"position {position}: {held} and {other}"
                for position, (held, other) in sorted(clashes.items())[:_CLASHES_SHOWN]
            )
            if len(clashes) > _CLASHES_SHOWN:
                shown += f"; and {len(clashes) - _CLASHES_SHOWN} more"
            raise ValueError(
                f"two dispositions claim the same thread position in source "
                f"{self.thread_id}: {shown}. A message has one position and one "
                "disposition (A.7a); two runs over the same slots let a map count the "
                "same positions twice and report itself complete while a real message is "
                "represented nowhere (PART-05, R-06, R-RETR-002)"
            )
        return self

    @model_validator(mode="after")
    def _every_position_lies_inside_the_thread(self) -> Source:
        """Amendment A3: `0 <= p < stated_total` for every row and every run position.

        Round 4 closed occupancy - no two dispositions may claim one slot - and stopped
        there, so nothing required the slots to be *inside* the thread. R-RETR's executed
        proof was a `map_id`-bearing source with `stated_total=5` carrying a run at
        positions 900-904: five messages, five distinct slots, occupancy satisfied,
        `accounted_for == stated_total`, and a "complete map" of a five-message thread
        placed at positions no five-message thread has. R-ARCH-013 reproduced the same
        thing one disposition to the left, with a single row.

        A position is a 0-based index into the thread's chronological message order, and
        the range is bound to `stated_total` rather than to a separately declared length
        so that the completeness claim and the position claim are checked against the same
        number.

        Out-of-range positions **raise**. Clamping them into range would silently move
        evidence to a slot it was never at, which is the failure class this project exists
        to prevent - and a reader has no way to tell a moved position from a real one.

        Ordered after `_one_position_holds_one_disposition` so a shape that violates both
        still reports the occupancy clash first: the Round 4 check and its error text are
        unchanged.
        """
        outside: list[str] = []
        for row in self.messages:
            if not 0 <= row.position < self.stated_total:
                outside.append(f"message {row.id} at position {row.position}")
        for run in self.collapsed_runs:
            start, end = run.positions
            if start < 0 or end >= self.stated_total:
                outside.append(f"collapsed run {run.positions}")
        if outside:
            shown = "; ".join(outside[:_CLASHES_SHOWN])
            if len(outside) > _CLASHES_SHOWN:
                shown += f"; and {len(outside) - _CLASHES_SHOWN} more"
            raise ValueError(
                f"source {self.thread_id} places evidence outside the thread it describes: "
                f"{shown}. A position is a 0-based index into chronological order and must "
                f"satisfy 0 <= p < stated_total (here 0 <= p < {self.stated_total}); a "
                "source claiming to describe a thread cannot place part of that claim "
                "where the thread has no message. Out-of-range positions are refused "
                "rather than clamped, because clamping moves evidence silently "
                "(amendment A3, R-RETR-005, R-ARCH-013)"
            )
        return self

    @model_validator(mode="after")
    def _withheld_here_is_a_disposition_not_a_duplicate(self) -> Source:
        """A message has exactly one disposition (A.7a): present, or withheld, not both."""
        if len(set(self.withheld_here)) != len(self.withheld_here):
            raise ValueError("a message is listed twice in withheld_here")
        both = set(self.withheld_here) & self.disclosed_ids
        if both:
            raise ValueError(
                f"messages are both present in source {self.thread_id} and listed as "
                f"withheld from it: {sorted(both)}"
            )
        return self

    @model_validator(mode="after")
    def _a_page_is_stated_whole_or_not_at_all(self) -> Source:
        stated = (self.page, self.page_size, self.pages)
        if any(one is None for one in stated) and any(one is not None for one in stated):
            raise ValueError(
                f"source {self.thread_id} states a page partially ({stated}); page, "
                "page_size and pages travel together"
            )
        if self.page is not None and self.page_size is not None and self.pages is not None:
            if self.page_size < 1 or self.pages < 1 or not (0 <= self.page < self.pages):
                raise ValueError(
                    f"source {self.thread_id} states page {self.page} of {self.pages} at "
                    f"{self.page_size} per page, which is not a page"
                )
            if (self.pages - 1) * self.page_size >= self.stated_total > 0:
                raise ValueError(
                    f"source {self.thread_id} states {self.pages} pages of {self.page_size} "
                    f"over {self.stated_total} messages; the last page would be empty"
                )
        return self

    @model_validator(mode="after")
    def _a_claimed_map_accounts_for_every_message(self) -> Source:
        """PART-05, R-06: a thread map enumerates the thread or it is not a map.

        `map_id` says this source is the thread's map. A map that shows five of
        forty-two messages and says nothing about the other thirty-seven is the exact
        defect MailWeave exists to fix, reproduced inside MailWeave (R-DISC-001). So the
        map claim is checked against what the payload actually enumerates: every position
        must be a row, a collapsed-run member, or a withheld record. A source *without*
        `map_id` is a search view and carries no such obligation - which is the
        distinction the schema previously could not express.
        """
        if self.map_id is None:
            return self
        if self.accounted_for != self.stated_total:
            missing = self.stated_total - self.accounted_for
            raise ValueError(
                f"source {self.thread_id} claims map_id={self.map_id!r} but accounts for "
                f"{self.accounted_for} of {self.stated_total} messages "
                f"({len(self.messages)} rows + "
                f"{len(set(self.collapsed_member_ids))} collapsed + "
                f"{len(set(self.withheld_here))} withheld); {missing} are represented "
                "nowhere. A map must show every message as a row, a collapsed run member "
                "or a withheld record (contract R-06, PART-05)"
            )
        return self


class NotIncludedSource(Frozen):
    """One whole source this response does not carry, with the call that fetches it.

    **Round 29, R-MCP-033.** The `why` moved up to the block. Sixteen sources split off by
    A.9a step 7 shared one 253-character sentence and repeated it sixteen times, in the entry,
    in the mirror line, and again for every one of them - 12,736 characters at T=16 to say one
    thing sixteen times, against a 25,000-character host cap, which is the same
    bookkeeping-overflow the withheld records had. Nothing was lost by hoisting it: every
    thread, every count and every recovery call is still here, one per source.
    """

    thread_id: str = Field(min_length=1)
    stated_total: int | None = None
    affordance: Affordance
    #: The retrieval rank of the source this entry stands for (R-M2-096): a source A.9a
    #: step 7 split off keeps the rank it was mapped at, so the entries are written best
    #: first rather than in the order the ladder removed them, which was worst first.
    rank: int | None = Field(default=None, ge=0)


class NotIncludedBlock(Frozen):
    """Sources left out for one reason, with that reason stated once.

    One block per distinct explanation, so two different reasons stay two different
    statements - the deduplication is of repetition, not of meaning. A block with no sources
    would be an explanation of nothing and is refused.
    """

    why: str = Field(min_length=1)
    sources: tuple[NotIncludedSource, ...] = Field(min_length=1)

    @property
    def thread_ids(self) -> tuple[str, ...]:
        return tuple(source.thread_id for source in self.sources)


class Ceiling(Frozen):
    """AD A.9a: the overflow ceiling exists only for E2 floor membership, and says so."""

    normal: int = Field(gt=0)
    applied: int = Field(gt=0)
    why: str | None = None

    @model_validator(mode="after")
    def _every_departure_from_the_published_ceiling_is_declared(self) -> Ceiling:
        """`normal` is the published figure; `applied` is what this response was held to.

        **A departure in either direction needs a stated reason** (round 25). Until this round
        the model refused `applied < normal` outright - "an applied ceiling below the normal
        ceiling is not a ceiling" - which made AD D.1's published `budget.max_disclosed_tokens`
        argument unrepresentable: every value in [1, 8999] raised a `ValidationError` that
        reached the caller as `-32602 INVALID_PARAMS`, so a schema-valid call was answered
        with "your request was malformed" (R-MCP-004). A caller-lowered ceiling **is** a
        ceiling; what it must not be is silent, and `why` is where it stops being silent.

        `normal` stays pinned to the published constant so a reader always sees the figure the
        architecture publishes beside the figure this response was actually held to.
        """
        if self.applied != self.normal and not self.why:
            raise ValueError(
                "a response held to something other than the published ceiling must say why"
            )
        if self.applied == self.normal and self.why:
            raise ValueError(
                "a reason without a departure from the published ceiling is decorative"
            )
        if self.normal != NORMAL_CEILING_TOKENS:
            raise ValueError(
                f"normal ceiling must be the published constant {NORMAL_CEILING_TOKENS}"
            )
        return self


class BudgetClamp(Frozen):
    """AD A.7 recoverability floor: a budget below the floor is clamped up and declared."""

    requested: int = Field(ge=0)
    applied: int = Field(ge=0)
    why: str = Field(min_length=1)

    @model_validator(mode="after")
    def _clamp_is_upward_to_the_floor(self) -> BudgetClamp:
        if self.applied < self.requested:
            raise ValueError("a clamp that lowers the applied budget is not the floor clamp")
        if self.applied < FLOOR_QUOTA_UNITS:
            raise ValueError(
                f"applied budget {self.applied} is below the published recoverability "
                f"floor {FLOOR_QUOTA_UNITS}"
            )
        return self


class BudgetBlock(Frozen):
    clamped: BudgetClamp | None = None


class ErrorEntry(Frozen):
    """The in-band half of D.11's closed vocabulary."""

    code: ErrorCode
    scope: str = Field(min_length=1)
    message_ids: tuple[str, ...] = ()
    affordance: Affordance | None = None

    @model_validator(mode="after")
    def _code_is_in_band(self) -> ErrorEntry:
        if self.code not in IN_BAND_CODES:
            raise ValueError(
                f"{self.code.value} is not an in-band code; D.11 makes it a tool error"
            )
        return self


class ParsedQuerySummary(Frozen):
    operators: dict[str, str] = Field(default_factory=dict)
    terms: tuple[str, ...] = ()
    timezone: str | None = None
    window_utc: dict[str, str] | None = None


class DroppedConstraint(Frozen):
    constraint: str = Field(min_length=1)
    why: str = Field(min_length=1)


class AskedFor(Frozen):
    """T-RC3: what was asked, what was enforced, what was dropped."""

    parsed: ParsedQuerySummary
    enforced: tuple[str, ...] = ()
    dropped: tuple[DroppedConstraint, ...] = ()
    term_coverage: float = Field(ge=0.0, le=1.0)
    constraint_drop_depth: int = Field(ge=0)

    @model_validator(mode="after")
    def _drop_depth_matches_dropped(self) -> AskedFor:
        if self.constraint_drop_depth != len(self.dropped):
            raise ValueError(
                f"constraint_drop_depth={self.constraint_drop_depth} but "
                f"{len(self.dropped)} constraints are listed as dropped"
            )
        return self
