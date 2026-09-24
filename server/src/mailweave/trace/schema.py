"""Trace schema v2: the record, and the reason no field of it can hold mail text (AD D.10).

**The type is the redaction.** A.11: "The `PersonalTrace` type has *no field* whose type can
hold mail-derived text; the emitter is statically bound at startup by the derived profile."
Every field below is an `int`, a `bool`, a closed enum, an opaque Gmail id, or a structure
of those - and `test_no_trace_field_can_hold_mail_derived_text` walks the model tree and says so, so
a field added later has to be argued rather than merely typed.

**What is here that the response is not allowed to carry.** `semantic.pool_ids[]`. D.5 and
§H-5(b) put it in the trace and nowhere else: it is what lets EV-01 be joined against a real
set instead of against the server's account of one, and it would be 300 stub rows on the
wire. Under the personal profile it is a list of opaque Gmail ids, which the A.11 type
policy already permits - ids and metadata are persisted by default, bodies and subjects are
not.

**And `redaction` is a first-class field, not an inference.** A reader who has to deduce
"this looks redacted" from what is absent cannot tell a redacted trace from a trace of a
query that found nothing.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from mailweave.envelope.reasons import RungId
from mailweave.envelope.vocab import BudgetCapName
from mailweave.trace.redaction import RedactionPolicy

#: D.10's schema version. A field added to any model here is a version bump, not a patch:
#: a reader that joins two traces has to be able to tell which shape it is holding.
TRACE_SCHEMA_VERSION: Final[int] = 2


class _Block(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class QueryFeatures(_Block):
    """A.11: query text is stored as features plus a salted hash. Never the string."""

    chars: int = Field(ge=0)
    tokens: int = Field(ge=0)
    has_operator: bool
    has_phrase: bool
    has_negation: bool
    #: The salted short digest `redaction.Redacted.digest` produces. A within-trace join key.
    hash: str = Field(min_length=1, max_length=16, pattern=r"^[0-9a-f]+$")


class Routing(_Block):
    initial_route: RungId | None = None
    rungs_executed: tuple[RungId, ...] = ()
    #: Constraint **names** (`from`, `terms`), which are the query's grammar rather than its
    #: text: `Constraint.name` is a fixed vocabulary the parser assigns, not a value the user
    #: typed. `test_no_trace_field_can_hold_mail_derived_text` checks that claim against the parser.
    constraints_dropped: tuple[str, ...] = ()
    fallback_triggered: bool = False
    fallback_reason: str | None = None
    escalation_offers_returned: int = Field(default=0, ge=0)


class ExactSignalTrace(_Block):
    fired: bool
    branch: str | None = None
    phrase_tokens: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    verified_locally: bool


class ScanScopeTrace(_Block):
    """One executed probe, by rung and counts. **The `q` is not here** (SN §4.3)."""

    rung: RungId
    pages_fetched: int = Field(ge=0)
    ids_returned: int = Field(ge=0)
    more_pages: bool
    #: The salted digest of the `q` this probe sent, so two probes can be told apart without
    #: the trace holding either one's text.
    query_hash: str = Field(min_length=1, max_length=16, pattern=r"^[0-9a-f]+$")


class AnswerTypeTrace(_Block):
    value: bool | None = None
    answer_class: str | None = None


class RetrievalOutcome(_Block):
    rounds: int = Field(ge=0)
    http_requests: int = Field(ge=0)
    api_calls_by_method: dict[str, int] = Field(default_factory=dict)
    #: A.11, ADV-211: a multiplication of a published table, never a headline. The label
    #: travels with the number so a reader cannot meet one without the other.
    quota_units: int = Field(ge=0)
    quota_units_label: str = "diagnostic; calibrated at G0 (PF-3)"
    hit_count_per_rung: dict[str, int] = Field(default_factory=dict)
    scan_scope: tuple[ScanScopeTrace, ...] = ()
    term_coverage_final: float = Field(ge=0.0, le=1.0)
    exact_signal_match: ExactSignalTrace | None = None
    answer_type_presence: AnswerTypeTrace | None = None
    budget_caps_hit: tuple[BudgetCapName, ...] = ()
    sufficiency_verdict: str | None = None
    false_notfound_guard: bool = False


class WithheldTrace(_Block):
    id: str = Field(min_length=1)
    cap: str = Field(min_length=1)


class Disposition(_Block):
    hit_ids_count: int = Field(ge=0)
    disclosed_count: int = Field(ge=0)
    withheld: tuple[WithheldTrace, ...] = ()


class ShortlistTrace(_Block):
    rule: str = Field(min_length=1)
    k: int = Field(gt=0)
    size: int = Field(ge=0)


class SemanticTrace(_Block):
    """D.10's `semantic` block. `pool_ids[]` lives here and nowhere else."""

    model_id: str | None = None
    model_revision: str | None = None
    embed_texts: int = Field(default=0, ge=0)
    rerank_pairs: int = Field(default=0, ge=0)
    #: The scoping *rule*, which is a sentence this server composes out of its own bounds -
    #: thread counts and cap names. It carries the query's participant operators by value,
    #: so under the personal profile it is emitted as a digest rather than as the sentence.
    pool_scope_hash: str | None = Field(default=None, max_length=16)
    pool_threads: int = Field(default=0, ge=0)
    pool_messages: int = Field(default=0, ge=0)
    #: A.7a / §H-5(b): opaque Gmail ids, in the trace only, so EV-01 joins against a real set.
    pool_ids: tuple[str, ...] = ()
    shortlist: ShortlistTrace | None = None
    #: PF-4's separation, carried to every consumer of a latency figure: the cold model load
    #: is per process and is never part of a per-query number.
    cold_load_ms: int | None = None
    semantic_ms: int = Field(default=0, ge=0)


class PerMessageTrace(_Block):
    id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    #: The reason's **kind**, a closed vocabulary - never `reason.render()`, which composes
    #: the executed `q` into a sentence.
    reason_kind: str = Field(min_length=1)
    depth: str = Field(min_length=1)
    tokens: int = Field(ge=0)


class DisclosureTrace(_Block):
    levels_traversed: int = Field(ge=0)
    levels_traversed_to_answer: int | None = None
    disclosed_tokens_est: int = Field(ge=0)
    ceiling_applied: int | None = None
    per_message: tuple[PerMessageTrace, ...] = ()


class FreshnessTrace(_Block):
    history_id: str | None = None
    watermark_source: str | None = None
    reconciled: bool = False
    rebaselined: bool = False


class ErrorTrace(_Block):
    """An error, by **code and class name**. Never a message: messages carry values.

    R-SEC-043 forbids an error that echoes what it rejected, and A.11 asks that the error
    path be clean - so this records the closed D.11 code and the exception's type, both of
    which are facts about the program rather than about the mailbox.
    """

    code: str = Field(min_length=1)
    exception: str | None = None


class CostTrace(_Block):
    latency_ms_total: int = Field(ge=0)
    latency_ms_per_rung: dict[str, int] = Field(default_factory=dict)
    waited_ms: int = Field(default=0, ge=0)


class PersonalTrace(_Block):
    """One top-level call, under the personal profile. Schema v2 (AD D.10, A.11)."""

    trace_id: str = Field(min_length=1)
    schema_version: int = TRACE_SCHEMA_VERSION
    #: **First-class, per D.10.** Which type policy produced this record.
    redaction: RedactionPolicy = RedactionPolicy.PERSONAL
    #: A.3's gated escape hatch records the finding id it was opened for, so its use is
    #: self-documenting. `None` on every ordinary trace.
    diagnose_finding: str | None = None
    tool: str = Field(min_length=1)
    query_features: QueryFeatures
    routing: Routing
    retrieval_outcome: RetrievalOutcome
    disposition: Disposition
    semantic: SemanticTrace | None = None
    disclosure: DisclosureTrace | None = None
    freshness: FreshnessTrace | None = None
    errors: tuple[ErrorTrace, ...] = ()
    cost: CostTrace
    #: `(query_features, successful_route, cost)` is a training example for a future learned
    #: router (SC §9, B-05) - and the [VERIFIED] Limited Use constraint says such a router may
    #: only ever be trained on synthetic seed traces or strictly per-user personalised data.
    eval_join: str | None = None


__all__ = [
    "TRACE_SCHEMA_VERSION",
    "AnswerTypeTrace",
    "CostTrace",
    "DisclosureTrace",
    "Disposition",
    "ErrorTrace",
    "ExactSignalTrace",
    "FreshnessTrace",
    "PerMessageTrace",
    "PersonalTrace",
    "QueryFeatures",
    "RetrievalOutcome",
    "Routing",
    "ScanScopeTrace",
    "SemanticTrace",
    "ShortlistTrace",
    "WithheldTrace",
]
