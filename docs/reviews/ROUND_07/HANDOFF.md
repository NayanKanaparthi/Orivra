# ROUND 07 — Implementer handoff

**Implementer, 2026-08-31.** Scope: `docs/reviews/ROUND_07/WORK_ORDER.md`, three parts.
Amendments A1..A5 binding, A5 built this round. OD-1..OD-4 binding. A1 not built.

## Verification state

| | Baseline (round 6 tree) | This tree |
|---|---|---|
| `ruff check` / `ruff format --check` | clean, 88 files | clean, 88 files |
| `mypy --strict` | clean, 62 source files | clean, 62 source files |
| `pytest -m "not network"` | **656 passed** | **775 passed** |
| `python -m tools.guards` | 7 guards clean | 7 guards clean |
| `rubric_status.py --check` | 8 PASS / 105 NOT TESTED / 10 transitions | unchanged |
| `make check` | exit 0 | exit 0 |

No rubric criterion marked PASS. No rows added to `RUBRIC_TRANSITIONS.md` or
`FINDINGS_LEDGER.md`. Every count below was obtained by running the suite and reading its
last line, not by recalling — the round-6 handoff's "7 tests" was measured as 8 and 9 by two
reviewers, and that is the failure mode this note exists to avoid.

---

# Part 1 — the class audit

## Method and scope

Every model field in the envelope and ledger layers was enumerated **programmatically**
(pydantic `model_fields` + `model_computed_fields`, dataclass fields, and the two
hand-written constructors), so the table below cannot silently omit a field somebody forgot
to look at. The enumerator is reproducible:

```
uv run python - <<'PY'
import dataclasses, inspect
from pydantic import BaseModel
import mailweave.envelope.wire as wire, mailweave.envelope.response as response
import mailweave.envelope.disposition as disposition, mailweave.envelope.reasons as reasons
import mailweave.content.reductions as reductions
for mod in (wire, response, disposition, reasons, reductions):
    for name, obj in vars(mod).items():
        if inspect.isclass(obj) and obj.__module__ == mod.__name__:
            if issubclass(obj, BaseModel):
                print(mod.__name__, name, list(obj.model_fields), list(obj.model_computed_fields))
            elif dataclasses.is_dataclass(obj):
                print(mod.__name__, name, [f.name for f in dataclasses.fields(obj)])
PY
```

**174 fields** across `envelope/wire.py`, `envelope/response.py`, `envelope/disposition.py`
and `envelope/reasons.py`, plus **13** on `content/reductions.Reduction` — the content-layer
model the envelope carries inside every `MessageRow` — audited too, for **187 in total**.

## The headline result: the binary in the work order is not sufficient

The work order asks for two classes. The audit needs **three**, and the third is the finding:

| Class | Meaning | Count |
|---|---|---|
| **D — derivable** | the fact is available from a sealed observation, or from another field computed off one | **52** |
| **C — caller-owned** | the caller is genuinely the only source of truth | **103** |
| **O — observed but unsealed** | the fact *is* a fact of the Gmail response, and the sealed observation does not record it, so there is nothing to derive it from | **20** |
| **S — the seal itself** | `FetchedIds`'s constructor parameters, which are the boundary rather than a field inside it | **7** |
| **I — ledger-internal** | accumulators with no caller path at all | **5** |

52 + 103 + 20 + 7 + 5 = **187**, which is 174 envelope-and-ledger fields plus `Reduction`'s
13. The counts were read out of the table below by a script rather than tallied by eye — the
table is the source and these five numbers are derived from it, which is the same discipline
the round is about. A 53rd D row, `MessageRow.thread_id`, appears struck through: it existed
at the start of this round and does not exist now.

**Class O is the reason the defect keeps recurring.** Six of the seven prior instances, and
R-DISC-011, are all the same mechanism: the envelope states a fact of a Gmail response, and
the seal — `FetchedIds` — records only a *subset* of what that response said. Where the seal
happens to carry the fact (`thread_id`, `page_size`, `more_pages`, the id set, the endpoint)
the fix is available and this round takes it. Where it does not (`stated_total`, a row's
`position`, `internal_date`, `history_id`, `fetched_at`) there is no observed value to derive
from, so "derive it and remove the parameter" degenerates into "check one caller assertion
against another caller assertion", which is not a fix and would read like one.

## Can the class be closed by field-level derivation alone? **No.**

Three independent reasons, in increasing order of how much they cost to fix.

**1. The seal is narrower than the response.** Every class-O field above is a fact Gmail
states and `FetchedIds` throws away. Field-level derivation cannot reach them because the
value does not exist anywhere in the process. **What would close it:** the observation
records the *whole* response it saw — one `ObservedMessage` per id carrying `threadId`,
`internalDate`, its index within the thread, the thread's own message count and `historyId` —
and every envelope field that states one of those facts becomes a projection of the ledger
rather than a parameter. That is a single structural change, not five field fixes, and it
retires class O by construction. It is also a real piece of work (`FetchedIds`, `HitOrigin`,
`record_thread`, the transport seam, and every fixture that mints an observation) and it
changes what a transport must supply, which is why it is named here rather than half-built.

**2. Even a complete seal is a caller assertion one layer down.** `FetchedIds(...)` is an
ordinary public constructor, and `disposition.py`'s own docstring has said since round 3 that
`|H|` is *bounded below by what the transport fetched and bounded above by nothing*. Deriving
a field moves the assertion from the envelope to the observation; it reduces the number of
places a lie can be told and the number of people who can tell it, and it does not make the
statement checkable. **What would close it:** amendment **A1**'s content witness, outside the
process, recording the exact id set of every observed response. Nothing in-process
substitutes for it, and this round did not build it (A1 is not mine).

**3. Where the value *is* derivable, removing the parameter has a real cost in this
codebase, and the two available mechanisms each reintroduce a defect this project has already
fixed.** Both are worth stating because they are why several class-D fields below are
*checked* rather than *removed*:

  * `computed_field` removes the parameter and keeps the field on the wire — but pydantic
    serialises computed fields **last**. Applying it to `Envelope.partial` would move the
    partiality signal to the end of the payload, which is exactly the defect R-DISC-003 was
    filed for and `test_the_partiality_signals_are_serialised_before_the_bulk_content` exists
    to prevent;
  * a `mode="before"` validator removes the parameter and keeps field order — but it sees
    *unnormalised* input, so it must interpret the payload in every spelling a caller might
    use, which is precisely the shape-bounds defect class R-SEC-021 / R-ARCH-016 closed
    (instance six of this very list).

The route this round used for `MessageRow.thread_id` avoids both: the field is removed from
the row and written onto the row's wire form by the **enclosing `Source`**, at serialisation,
from validated objects, in D.2's position. That works wherever exactly one parent owns the
fact. It does not generalise to `Source.included`, whose parent is the `Envelope` two levels
up, without nesting serialisers through the whole tree.

**The honest summary.** Field-level derivation closes the instances where the seal already
carries the value — which is R-DISC-011, `ThreadMember`'s parameters, and
`hit_count_per_rung`, all fixed below. It cannot close the class. The class closes when the
observation becomes the single record of everything the response said (removing class O), and
the class becomes *trustworthy* only under A1's witness.

## The complete table

Legend — **Class**: D derivable, C caller-owned, O observed-but-unsealed, S seal boundary,
I ledger-internal. **State**: `derived` (no parameter to get wrong), `checked` (parameter
exists, a total validator refuses any wrong value), `bounded` (partial check), `open`
(nothing checks it), `n/a`.

### `envelope/wire.py`

| Model.field | Class | Basis | State |
|---|---|---|---|
| `Affordance.tool` | C | the caller chooses which follow-up call to offer; closed `ToolName` enum | checked (enum) |
| `Affordance.args` | C | the arguments of an offer, not a record of anything observed | bounded (`mentions()` must name the source it is offered for) |
| `WithheldRecord.id` | D | `certify`'s set difference `H − disclosed` | derived (minted only by `_record_for`; envelope compares record-for-record) |
| `WithheldRecord.thread_id` | D | `HitOrigin.thread_id` | derived (R-DISC-009, round 6) |
| `WithheldRecord.cap` | C | which cap fired is the caller's own event | checked (enum) |
| `WithheldRecord.why` | C | the cap's reason; nothing observed it | derived-at-producer (from `_WithheldNote`) |
| `WithheldRecord.affordance` | C | the call that would fetch it | derived-at-producer |
| `ScanScopeEntry.q` | C | the query string that was executed | open (by nature) |
| `ScanScopeEntry.rung` | C | which rung executed it | open (by nature) |
| `ScanScopeEntry.page_size` | D | `FetchedIds.page_size` | derived |
| `ScanScopeEntry.pages_fetched` | D | one sealed observation is one page, so this is 1 per entry | **open — not fixed this round**, see "not fixed" |
| `ScanScopeEntry.ids_returned` | D | `len(materialised)` | derived |
| `ScanScopeEntry.more_pages` | D | `FetchedIds.more_pages` | derived |
| `ScanScopeEntry.affordance` | C | the widening call offered | checked (required when `more_pages`) |
| `PoolBlock.scope_rule` | C | pre-registered pool rule (EV-01 ii) | open (by nature) |
| `PoolBlock.thread_count` | O | a fact of the retriever's pool; WS-08 unbuilt, ledger models no pool | open |
| `PoolBlock.message_count` | O | as above | open |
| `PoolBlock.why` | C | prose reason | open (by nature) |
| `PoolBlock.note` | D | constant default string | derived (default) |
| `Shortlist.rule` | C | pre-registered selection rule | open (by nature) |
| `Shortlist.k` | C | pre-registered cap | open (by nature) |
| `Shortlist.size` | D | deduplicated selection size | derived at the only production producer (`record_shortlist`); `builder` takes the shortlist from the ledger, never from a caller |
| `NotTriedEntry.rung` | C | a route that did **not** execute leaves no observation | open (by nature) |
| `NotTriedEntry.why` | C | as above | checked (enum) |
| `NotTriedEntry.affordance` | C | as above | checked (required for blocking reasons) |
| `EmptyDiagnosis.status` | D | fully determined by `untried_drops` | checked (total, `_states_are_distinct`) |
| `EmptyDiagnosis.tried` | C | the probes the diagnosis loop ran | open (by nature) |
| `EmptyDiagnosis.untried_drops` | C | as above | open (by nature) |
| `EmptyDiagnosis.restores` | C | as above | checked (against `status`) |
| `EmptyDiagnosis.affordance` | C | as above | checked (required with `restores`) |
| `Counters.http_requests` | O | a fact of the transport; nothing counts calls in-process | open — **A1's counting proxy is the fix** |
| `Counters.api_calls` | O | as above; bounded below by the number of sealed observations, which the ledger does not count today | open |
| `Counters.quota_units` | O | as above; diagnostic and labelled so | open |
| `Counters.quota_units_label` | D | constant default | derived (default) |
| `RetrievalReport.outcome` | C | the response's account of what happened | checked (OD-2 rules at report and envelope level) |
| `RetrievalReport.rungs` | C | a rung that executed and found nothing leaves no trace in `H` | bounded — a rung that *did* admit ids may not be omitted (**new this round**) |
| `RetrievalReport.hit_count_per_rung` | D | `Counter(HitOrigin.rung)` | **derived this round** — parameter removed from `EnvelopeBuilder.build`; envelope re-derives |
| `RetrievalReport.scan_scope` | D | `ledger.scan_scope` | derived (builder reads the ledger) |
| `RetrievalReport.pool` | O | see `PoolBlock` | open |
| `RetrievalReport.shortlist` | D | `ledger.shortlist` | derived (builder reads the ledger) |
| `RetrievalReport.not_tried` | C | routes not executed | open (by nature) |
| `RetrievalReport.empty_diagnosis` | C | the relaxation probe's own result | checked (required for zero-evidence and `not_found`) |
| `RetrievalReport.budget_caps_hit` | C | which caps fired | checked (against `not_found`) |
| `RetrievalReport.sufficiency` | C | a judgement about the answer | checked (enum) |
| `RetrievalReport.counters` | O | see `Counters` | open |
| `Content.trust` | C | a labelling decision, not an observation | checked (enum) |
| `Content.source` | O | which part of the Gmail payload the text came from | checked (enum) |
| `Content.text` | O | the mail text itself — it *is* the payload; nothing to derive | checked (must be fenced with this response's nonce) |
| `Score.value` / `.method` / `.model` / `.basis` / `.ordering_effect` | C ×5 | the scorer's own outputs; WS-08 unbuilt | open |
| `MessageRow.id` | C | which messages to disclose is a disclosure decision | bounded — must be a real id if it is in `H`; an id outside `H` is A1's residue |
| ~~`MessageRow.thread_id`~~ | D | the enclosing `Source.thread_id`, itself now held to `HitOrigin` | **removed this round** — the parameter no longer exists |
| `MessageRow.position` | O | the index of the row in the `threads.get` response's message order; `FetchedIds` preserves the order and `HitOrigin` does not record it | bounded (A3: `0 <= p < stated_total`) — **the clearest class-O case** |
| `MessageRow.internal_date` | O | a Gmail field the seal does not carry | open |
| `MessageRow.role` | C | MailWeave's own classification | checked (enum, and against `depth`) |
| `MessageRow.reason` | C | the mechanism that put the row here | checked — closed union; `ThreadMember`'s parameters now checked (below) |
| `MessageRow.constraint_coverage` | C | per-message query evidence | checked (against `asked_for`, R-DISC-006) |
| `MessageRow.depth` | C | a disclosure decision | checked (against `content`) |
| `MessageRow.reductions` | D | each removal's size is the measured delta (`reductions.reconcile`) | derived at producer |
| `MessageRow.unabridged` | C | the call that fetches the full form | checked (required) |
| `MessageRow.score` | C | see `Score` | open |
| `MessageRow.content` | O | see `Content` | checked (fenced, and against `depth`) |
| `MessageRow.reason_detail` (computed) | D | `reason.model_dump()` | derived |
| `CollapsedRun.positions` | O | thread indices, as `MessageRow.position` | bounded (A3, and occupancy) |
| `CollapsedRun.count` | D | `end − start + 1` **and** `len(member_ids)` | checked (total) |
| `CollapsedRun.member_ids` | C | which messages the run collapses | checked (distinct, disjoint from rows, cross-run) |
| `CollapsedRun.why` | C | the cap that caused the collapse | open (by nature) |
| `CollapsedRun.affordance` | C | the call that expands it | checked (required) |
| `Source.thread_id` | D | `HitOrigin[id].thread_id` for every disclosed id observed with a thread | **derived-and-refused this round (R-DISC-011)**; a source with no observed ids has no derivation, which is stated in the validator |
| `Source.stated_total` | O | the thread's message count as Gmail reported it; no observation records it | **bounded below this round** by the number of ids observed in that thread |
| `Source.included` | D | `len(rows ∪ collapsed members)` | checked (total) — parameter retained; removal costs are in "the honest summary" above |
| `Source.included_as_stub` | D | stub rows + collapsed members | checked (total) |
| `Source.completeness` | C | a declared label | checked (enum) |
| `Source.source` | D | the endpoint the observation came from | open — cosmetic, see "not fixed" |
| `Source.fetched_at` | O | when the call was made; the seal records no time | checked (must parse as an instant with an offset, R-DISC-005) |
| `Source.verified_at` | O | as above | checked (ordering against `fetched_at`) |
| `Source.history_id` | O | a Gmail field the seal does not carry | open |
| `Source.map_id` | C | the *claim* "this is the thread's map" | checked (against the enumeration, R-DISC-001) |
| `Source.messages` | C | the payload | checked (many) |
| `Source.collapsed_runs` | C | the payload | checked (many) |
| `Source.withheld_here` | D | `{r.id for r in envelope.withheld if r.thread_id == this thread}` | checked exactly for a `map_id` source; a non-map source may under-list — see "not fixed" |
| `NotIncludedSource.thread_id` | C | a thread split off; may never have been observed | open |
| `NotIncludedSource.stated_total` | O | as `Source.stated_total` | **bounded below this round** |
| `NotIncludedSource.why` | C | the ladder step that split it off | open (by nature) |
| `NotIncludedSource.affordance` | C | the call that fetches it | checked (required) |
| `Ceiling.normal` | D | the published constant `NORMAL_CEILING_TOKENS` | checked (total) |
| `Ceiling.applied` | C | a budget decision | checked (≥ normal; reason required above normal) |
| `Ceiling.why` | C | as above | checked (both directions) |
| `BudgetClamp.requested` | C | the caller's budget request | open (by nature) |
| `BudgetClamp.applied` | C | the clamped budget | checked (≥ requested, ≥ floor) |
| `BudgetClamp.why` | C | as above | checked (required) |
| `BudgetBlock.clamped` | C | whether a clamp happened | open (by nature) |
| `ErrorEntry.code` | C | an error the caller met | checked (in-band vocabulary) |
| `ErrorEntry.scope` / `.message_ids` / `.affordance` | C ×3 | as above | bounded |
| `ParsedQuerySummary.operators` / `.terms` / `.timezone` / `.window_utc` | C ×4 | **the query string is the user's**, and the parser is the only source | open (by nature) |
| `DroppedConstraint.constraint` / `.why` | C ×2 | a relaxation decision | checked (against `constraint_drop_depth`) |
| `AskedFor.parsed` | C | see `ParsedQuerySummary` | open (by nature) |
| `AskedFor.enforced` | C | which constraints survived relaxation | bounded (rows may only cite these) |
| `AskedFor.dropped` | C | as above | bounded |
| `AskedFor.term_coverage` | C | the parser's own ratio | open |
| `AskedFor.constraint_drop_depth` | D | `len(dropped)` | checked (total) |

### `envelope/response.py`

| Field | Class | Basis | State |
|---|---|---|---|
| `Envelope.schema_version` | D | `Literal[2]` | derived (constant) |
| `Envelope.fence_nonce` | C | minted per response | derived at producer (`mint_nonce`) |
| `Envelope.asked_for` | C | the user's query | open (by nature) |
| `Envelope.partial` | D | withheld ∪ incomplete sources ∪ split-off sources ∪ unfetched pages ∪ self-truncation | checked (total, I-2) |
| `Envelope.withheld` | D | the certificate, record-for-record | checked (total, R-DISC-009) |
| `Envelope.retrieval_report` | C | composite | checked (many) |
| `Envelope.sources` | C | the payload | checked (many) |
| `Envelope.not_included_sources` | C | the ladder's split-offs | checked (against completeness) |
| `Envelope.affordances` | C | the calls offered | bounded (must reach every incomplete source) |
| `Envelope.ceiling` | C | see `Ceiling` | checked |
| `Envelope.errors` | C | errors met | bounded |
| `Envelope.budget` | C | see `BudgetBlock` | bounded |
| `Envelope.truncated_by` | D | the presence of A.9a ladder artifacts + the measured size | checked (total, DISC-06) |
| `Envelope.disposition` | D | mintable only by `certify`, digest-bound to this disclosed set | derived |

### `envelope/disposition.py`

| Field | Class | Basis | State |
|---|---|---|---|
| `HitOrigin.clause` | D | `CLAUSE_BY_ENDPOINT[endpoint]` | derived (A2) |
| `HitOrigin.endpoint` | D | `FetchedIds.endpoint` | derived (A2) |
| `HitOrigin.rung` | C | which rung executed the call | derived at producer (intake argument) |
| `HitOrigin.query` | C | the query string executed | derived at producer |
| `HitOrigin.thread_id` | D | `FetchedIds._thread_of(id)` | derived (R-DISC-009) |
| `_WithheldNote.cap` / `.why` / `.affordance` | C ×3 | the cap's own reason and remedy | derived at producer |
| `DispositionLedger._origins` / `._notes` / `._scan_scope` / `._shortlist` / `._shortlist_ids` | I ×5 | ledger accumulators, no caller path | n/a |
| `DispositionCertificate.token` | D | `_MINT_TOKEN` | derived (capability) |
| `DispositionCertificate.hit_count` | D | `len(H)` | derived |
| `DispositionCertificate.disclosed_hits` | D | `len(H ∩ disclosed)` | derived |
| `DispositionCertificate.withheld` | D | `H − disclosed`, minted per id | derived |
| `DispositionCertificate.digest` | D | sha256 of the disclosed set | derived |
| `DispositionCertificate.observed_threads` | D | `{id: HitOrigin.thread_id}` | **derived, new this round** |
| `DispositionCertificate.hits_per_rung` | D | `Counter(HitOrigin.rung)` | **derived, new this round** |
| `FetchedIds.ids` | S | **the seal**: asserted by the transport at the moment of the call | bounded below only — A1 |
| `FetchedIds.endpoint` | S | as above | A1 |
| `FetchedIds.page_size` | S | as above | checked (required for `messages.list`) |
| `FetchedIds.more_pages` | S | as above | A1 |
| `FetchedIds.next_page_token` | S | as above | A1 |
| `FetchedIds.thread_id` | S | as above | checked (required for `threads.get`; may not coexist with `thread_ids`) |
| `FetchedIds.thread_ids` | S | as above | checked (must cover exactly the ids the observation returned) |

### `envelope/reasons.py`

| Field | Class | Basis | State |
|---|---|---|---|
| `*.kind` (10 models) | D ×10 | `Literal` discriminator | derived |
| `GmailQueryMatch.query` / `.rung` | C ×2 | the query and rung that matched | open — derivable against `scan_scope`; see "not fixed" |
| `Rfc822MsgId.message_id_header` | O | a mail header | open |
| `ReplyParentOf.child_id` | C | reply structure from `References`/`In-Reply-To`; not sealed | open |
| `ReplyChildOf.parent_id` | C | as above | open |
| `ThreadMember.thread_id` | D | the enclosing `Source.thread_id` | **checked this round** (total, at `Source`) |
| `ThreadMember.position` | D | the row's own `position` | **checked this round** (total, at `MessageRow`) |
| `SemanticScore.cosine` / `.model` | C ×2 | the scorer's outputs | open |
| `HistoryAddition.history_id` | O | a Gmail field the seal does not carry | open |
| `RequestedById.requested_id` | C | a tool argument | open (by nature) |
| `SnippetContains.term` | C | a query term | open |
| `WindowOffset.offset` / `.anchor_id` | C ×2 | a windowing decision | open |

### `content/reductions.py` (carried by every `MessageRow`)

| Field | Class | Basis | State |
|---|---|---|---|
| `Reduction.kind` | D | closed discriminator | checked (enum) |
| `Reduction.removed_chars` | D | the **measured** shrinkage (`reconcile`) | derived at producer, reconciled |
| `Reduction.count` | C | how many items were removed | checked (required for a zero-size removal) |
| `Reduction.detail` | C | prose | open (by nature) |
| `Reduction.mime` / `.bytes` / `.parser` / `.stripper` / `.charset_used` / `.charset_declared` / `.constructs` / `.kept_tokens` / `.header` | C ×9 | kind-specific descriptors of what was removed | bounded (kind-specific obligations) |

---

## What Part 1 changed, with failing-test-first evidence

Every count below was produced by editing the file, running the full suite, reading the last
line, and restoring the file with a `sha256sum` comparison.

### R-DISC-011 — the disclosed side of the borrowing (HIGH)

`DispositionCertificate` now carries `observed_threads` — the thread each id in `H` was
observed under — and `Envelope` holds every **disclosed** id to it:

* an id whose observation named thread B may not be disclosed under a source for thread A,
  in a row **or inside a collapsed run** (both are `R` under A.7a);
* a `map_id`-bearing source may not count an id whose observation named **no** thread — the
  disclosed twin of `_record_for`'s refusal to withhold an unthreaded id;
* an id with no `HitOrigin` at all is left alone: the ledger has no opinion about a parent or
  context message no recorded retrieval returned, and inventing one would hide A1's residue.

`MessageRow.thread_id` is **gone as a parameter**. `Source` writes it onto each row's wire
form from its own `thread_id`, in D.2's position (`id`, `thread_id`, `position`, …), so the
field a reader needs is unchanged and there is no second place to put a value.

R-DISC's original reproduction (`probe_disclosed_side_borrowing.py`, rebuilt verbatim: t1
observed with a1/a2/a3, x1 genuinely observed under t5 via a real `threads.get`, `map_id` set,
`stated_total=4`) now raises `DispositionInvariantError` naming `x1`, `t5` and `t1`.

| Reintroduction | Failing tests, by running |
|---|---|
| `_disclosed_rows_sit_in_the_thread_they_were_observed_in` → `return self` | **5** (4 in `test_disposition_invariant.py`, 1 property test) |
| `MessageRow` regains a `thread_id` parameter the serialiser prefers | **2** |

### `Source.stated_total`, bounded below

A thread cannot hold fewer messages than the number of its own messages the ledger saw.
Applied to `Source` and to `NotIncludedSource`. Stated as a **bound**, not a derivation — the
seal records no thread total, which is the class-O problem in one line.

| Reintroduction | Failing tests |
|---|---|
| `_stated_total_is_not_below_what_was_observed_in_the_thread` → `return self` | **1** |

### `ThreadMember.thread_id` / `.position` — an unfound instance the audit surfaced

A row at position 3 of thread `t1` could carry `reason=ThreadMember(thread_id="t9",
position=41)` and render *"thread map row: position 41 of thread t9"* to the reading agent
with every count in the payload correct. Nothing compared the reason's copy of either fact
with the payload's. Position is checked on the row (which knows its own); thread is checked on
the `Source` (the only layer that knows it). The parameters are **checked, not removed**,
because `render()` is what the agent sees and has no access to the row — recorded here rather
than glossed, and it is the same "checked duplicate" shape the audit flags elsewhere.

| Reintroduction | Failing tests |
|---|---|
| both `ThreadMember` checks neutered | **2** |

### `RetrievalReport.hit_count_per_rung` — a second unfound instance

Round 6's `_rung_counts_align` compared the tuple's **length** against `rungs` and never
compared its **values** with anything, so the one block a reader consults to see whether the
numbers add up was the one block nothing derived. Every id in `H` carries the rung whose
observation admitted it, so:

* `EnvelopeBuilder.build` **no longer takes `hit_count_per_rung`** — it reads
  `certificate.hits_per_rung`;
* `Envelope` re-derives it, and also refuses a `rungs` tuple that omits a rung which did admit
  ids (a route that produced evidence and is not listed is a route the reader cannot see).

`rungs` stays a parameter: a rung that executed and found nothing is real and leaves no trace
in `H`.

| Reintroduction | Failing tests |
|---|---|
| envelope-level check → `return self` | **2** |
| builder emits `(0, 0, …)` instead of the ledger's counts | **30** |

### Property tests, generated independently

`test_a_disclosed_row_may_only_sit_in_the_thread_it_was_observed_in` draws the **observed**
thread and the **placement** thread from two separate `hypothesis` lists, so neither is a
function of the other or of the message id. Measured, not asserted:

* message-id and thread-id alphabets are disjoint by character class — **0 collisions in 5,000
  generated pairs**;
* branch coverage over 2,000 sampled examples: **37.1% borrowed / 62.9% clean**. The first
  draft reached the clean branch on **1 of 2,000** examples, which would have made it a
  detector test wearing a property test's clothes; a per-id "move or leave" flag fixed it, and
  the assertion still reads the *relation* rather than the flag, so an independently drawn
  thread that happens to coincide is handled as agreement;
* clean on three reviewer-style fresh seeds (`20260831`, `314159265`, `999999937`).

---

# Part 2 — amendment A5, the quote stripper

## What changed

The detector no longer asks whether a line *looks like* an attribution. It asks whether the
line **matches a recognised client format**, and nothing else may cost a sender their words.
Three anchored templates, each a shape a real client emits:

| Template | Shape | Locales |
|---|---|---|
| `lead_in_date_address_verb` | `<lead-in> … <calendar date> … <address> … <verb>:` | en, fr, es, pt, it, pl, fi |
| `lead_in_date_verb_sender_address` | `<lead-in> … <calendar date> … <verb> <sender> <address>:` | de, nl, sv |
| `display_name_address_verb` | `[Display Name] <address> <verb>:` and nothing else on the line | en (bare form) |

Four structural requirements do the work, and each of them is a shape rather than a word:

1. the client's **lead-in word is anchored to the start of the line**, so a sentence that
   merely contains an attribution verb is not a candidate at all;
2. an **email address** must be on the line, in the place the client puts it;
3. a **calendar date** must sit between the lead-in and the address — deliberately stricter
   than round 6's "a year or a clock somewhere", which "the 2026 roadmap" and "the 15:14
   bridge call" both satisfy;
4. a **first-person pronoun anywhere on the line disqualifies it**, in all ten locales. This
   replaces round 6's adjacent-token check, which R-ARCH-019 walked past with an adverb and
   which had no plurals at all.

**A5 also reaches through this module.** `email_reply_parser` folds *any* line matching
`On … wrote:` into its quoted fragment, and that alone deleted three of the sentences measured
for A5 before this module had a decision to make. Narrowing only our own detector would have
left the same deletion happening one layer down. So an unrecognised head line of a quoted
fragment is handed back to the reply (`_reclaim_unrecognised_attribution_head`).

**The ambiguity is declared.** A kept attribution-shaped line that matched no template sets
`StripResult.ambiguous_lines`, and the pipeline emits a real
`Reduction(kind=quoted, removed_chars=0, count=n)` with a structural reason. The reason
carries **no mail text** — a reduction record is not fenced, and putting the line in it would
place unfenced mail-derived content in the envelope.

## Measured rates

Corpus in `tests/fixtures/reply_chains.py`; every line invented for this repository, no
personal mail content anywhere. Each prose line is measured in the position every version of
this defect was found in: the last line above a genuine `>` chain.

| Metric | Value |
|---|---|
| **False positives on sender-authored prose** — *gated at zero* | **0 / 36 = 0.0%** |
| False negatives on client attribution formats — measured, not gated | **2 / 16 = 12.5%** |
| Ambiguity records emitted on the prose corpus | 32 / 36 |
| Corpus regressions (content lost, or declared content leaked) across all 23 cases | 0 |

The 36 prose lines are the fifteen R-ARCH described in round 6 (attribution verb + address /
time / year, "per our call…", "following up on…", "the customer wrote:"), plus 21 written
against the round-7 rule itself: both R-ARCH-019 defeats (an adverb between the pronoun and
the verb; a first-person **plural** subject), five lines that open with a client's own lead-in
word, a lower-case lead-in clause carrying an address, and six non-English prose lines using
the same verbs.

The two false negatives are both English attributions carrying **no address**
(`On 25/08/2026 15:14, Priya Shah wrote:` and the Gmail form with the address stripped). They
are the direct price of requirement 2, and dropping that requirement puts `On 25 August 2026
the vendor wrote:` — a sentence a person writes — back in range. Both survive into
`body_clean`, cost their own tokens, and are declared with a zero-sized reduction. One is
pinned as the corpus's single `known_gap`.

**Round 6's rule, measured against the same corpus by reintroducing it into this tree:**
**22 of 36 sentences deleted (61.1%)**, **0 of 16 client formats missed (0.0%)**, and **29
failing tests**. That pair is the amendment in one line: round 6 caught every header and
destroyed 61% of a realistic sentence class; round 7 destroys nothing and misses 12.5% of
headers. A5 says which of those two is the correct default, and why.

## R-ARCH-019 / R-ARCH-020 — the Apple Mail forward

*(Numbering note: `CONSOLIDATED.md` and the work order call the Apple Mail leak R-ARCH-019 and
the duplicate verb R-ARCH-020; `ROUND_06/R-ARCH.md` itself numbers them 020 and 021, with 019
being the first-person false positive. Both are fixed, whichever number is authoritative.)*

`email_reply_parser` merges `Begin forwarded message:` into the *reply* fragment above it, so
the separator leaked into `body_clean` and the isolated `From:` / `Date:` lines below it — one
header field each, below the two-field bar `looks_quoted` uses — were filed as `signature`:
the "quoted prior conversation declared as a signature" class R-ARCH-001 closed, reappearing
through a fragment the parser never flagged.

Fixed by **splitting** the fragment at the separator, not by reclassifying it. Reclassifying
the whole fragment would have deleted the sender's own line above the separator — closing a
false negative by creating exactly the false positive A5 forbids. There is a test that fails
if someone reaches for the cheaper fix.

| Reintroduction | Failing tests |
|---|---|
| `_text_above_a_forward_separator` → `return None` | **3** |

## R-ARCH-020 / R-ARCH-021 — the duplicate verb and the "ten locales" claim

`_ATTRIBUTION_VERBS` is now generated from `_ATTRIBUTION_VERBS_BY_LOCALE`, a locale → verbs
mapping, so the coverage claim is **derivable rather than asserted beside the list**: 10
locales, 11 distinct patterns (Spanish carries an accented and an unaccented spelling), zero
duplicates. A test asserts the patterns are distinct **and** that every locale in the mapping
has a worked example in the corpus. Portuguese was the missing tenth — `escreveu` had been in
the list since round 5 with no example, which is how a duplicated `skrev` could make nine
locales look like ten.

| Reintroduction | Failing tests |
|---|---|
| `"skrev"` listed twice | **1** |
| Portuguese example removed from the corpus | **1** |

---

# Part 3 — the Round 6 mediums

Both false positives were treated at bypass weight, per the work order: a noisy guard gets
switched off and then protects nothing.

### R-SEC-026 — comprehensions and lambdas are scopes

`_calls_in` walked every descendant of an expression against one scope, on the stated ground
that "an expression opens no scope this pass models". In Python it does. Comprehension targets
and lambda parameters are now bound in the comprehension's / lambda's own scope, following
Python's actual rule rather than approximating it: the **outermost** iterable is evaluated in
the enclosing scope, everything else inside. Approximating it — binding the target first —
would have hidden a real write in the one expression the comprehension's scope does not cover,
and there is a test for that.

Controls, so the fix is not a blanket suppression inside every comprehension: a genuine
`os.replace(src, dst)` inside a comprehension and a non-shadowing lambda are both still caught.
The `unwrapped-http-client` guard shares the engine and shared the false positive; it is
covered too.

| Reintroduction | Failing tests |
|---|---|
| `_calls_in` reverted to one-scope `ast.walk` | **6** |

### R-SEC-027 — an English word is not an open mode

The unresolved-receiver fallback tested `_WRITE_MODE_CHARS & set(mode)` — any of `w`, `a`, `x`,
`+` **anywhere** in the string. It now requires the string to look like a mode at all: at most
four characters, all drawn from `rwaxbt+U`. `Parser().open("readonly")`, `"manual"`, `"active"`,
`"auto"`, `"exclusive"` and `"append-only"` all pass; every real write mode
(`w`, `a`, `x`, `wb`, `r+`, `xb+`, `rb+t`) is still caught, every real read mode still is not,
and an unreadable mode is still reported rather than assumed. The residue — a third-party
`open`-alike spelling a write mode as a long word — is added to the guard's own "Does not
catch" list.

| Reintroduction | Failing tests |
|---|---|
| mode-token check removed | **6** |

### R-SEC-028 — the ground-truth guard compares words, not substrings

`token in name.lower()` flagged `is_manifestly_invalid` and `harnessed_load`. Identifiers are
now split into words (`snake_case`, `camelCase`, `PascalCase`, digit runs) and a token matches
only as a contiguous run of whole words. `seed_map`, `seedMap`, `load_ground_truth`,
`case_manifest`, `GroundTruth` and `harness_client` are all still caught.

**Declared, not hidden:** `harness_the_energy` — R-SEC's other example — contains the whole
word `harness` and is *still* flagged. A word-boundary rule cannot tell that from a real
reference, and the rule that could would be a list of allowed phrasings. The function's
docstring says so, and a test asserts that it says so.

| Reintroduction | Failing tests |
|---|---|
| substring match restored | **4** |

### Fresh false-positive sweep

Ten ordinary code shapes, independent of the ones above (nested comprehension shadowing, a
comprehension inside a lambda, a walrus inside a comprehension, `Session().open("interactive")`,
`webbrowser.open(url, 2)`, `is_manifestly_wrong` / `harnessed_energy` in the same file, a
read-mode `.open`, a header-lowering dict comprehension, a lambda default reading an outer
module, an `.open()` with a defaulted read mode): **0 violations across all seven guards**.

---

# What I did NOT fix, and why

**Class-O fields (21).** `stated_total`, `MessageRow.position`, `CollapsedRun.positions`,
`internal_date`, `history_id`, `fetched_at`, `verified_at`, the `Counters` triple, the
`PoolBlock` counts, `Content.source`/`text`, `Rfc822MsgId.message_id_header`,
`HistoryAddition.history_id`. None has an observed value to derive from, because the seal does
not record it. Bounding `stated_total` from below is the only one of these the current seal
supports, and that is done. Fixing the rest means widening the observation, which is the
structural change described at the top and is a round of work in itself.

**`ScanScopeEntry.pages_fetched`.** Derivable — one sealed observation is one page, so an
entry's value should always be 1, or entries for one query should be merged. I did not change
it because both readings change what `scan_scope` *means* (per call, or per query), and
`transport.py` already threads the parameter through the seam. That is a decision about the
retrieval report's shape, not an implementation detail, and I should not take it unilaterally
in a round whose brief is explicitly "no retrieval logic".

**`Source.source`** (the `"gmail.threads.get"` string). Derivable from the observation's
endpoint. Cosmetic, unchecked, and low value beside the rest; named so it is not an eighth
instance in disguise.

**`Source.withheld_here` on a non-`map_id` source.** Exactly checked when `map_id` is set; a
search view may still under-list. Making it exact everywhere is a one-line change and a
behaviour change for search views, which I did not want to make blind.

**`GmailQueryMatch.query` / `.rung` on a row.** A row could claim it matched a query that was
never executed. The obvious check — the query must appear in `scan_scope` — is *probably*
right, but "which rung justified this row" and "which rung admitted this id into `H`" are not
the same question, and I could not convince myself the equality holds in the reply-chain and
promotion cases OD-3 describes. Named, not guessed at.

**`Source.included` / `included_as_stub` / `CollapsedRun.count` /
`AskedFor.constraint_drop_depth` / `EmptyDiagnosis.status` / `Envelope.partial`.** All class D
with **total** validators, so a shipped envelope cannot carry a wrong one. The parameters
remain because both mechanisms for removing them cost something this project has already paid
for once — see "the honest summary" in Part 1. I think that is defensible, and I also think it
is the weakest claim in this handoff, so it is stated as an argument rather than as a fact.

**A1's content witness.** Not mine, still the thing that bounds `|H|` from above.

---

# Where this work is weakest

1. **The class is not closed, and the fix that would close it is described rather than built.**
   Part 1's real product is a diagnosis. A reviewer is entitled to ask why I did not widen the
   observation this round; the answer is that it touches the transport seam and every fixture
   that mints an observation, and doing it badly in the same round as A5 would have been worse
   than doing it next. That is a judgement, not a proof.

2. **A5's zero false-positive rate is measured against a corpus I largely wrote.** Fifteen
   sentences reproduce R-ARCH's description; I did not have R-ARCH's exact fifteen, so the
   reproduction is faithful in shape and not verbatim. The other 21 are written by the same
   person who wrote the rule, which is the classic way a detector looks better than it is.
   **The single most valuable thing R-ARCH can do this round is write its own prose corpus and
   re-measure.** I expect the rule to hold — it requires a lead-in word, a calendar date and an
   address in client order — but "I expect" is what round 5 and round 6 both said.

3. **A5's requirements are a conjunction, and a conjunction is brittle in one direction.** Any
   client that omits the address, or writes a date the four `_WHEN_PATTERN` spellings do not
   cover, is a silent false negative. I measured 2 of 16; the true rate against real mail is
   unknown and unknowable until real mail exists, which is exactly what A5's measurement clause
   says. The zero-sized reduction makes each one visible, which is the mitigation, not a fix.

4. **`_reclaim_unrecognised_attribution_head` overrides an upstream library's classification.**
   It hands back one line, only when something remains below it, and only when the line matches
   no template — but it is still this module second-guessing `email_reply_parser`, and if the
   parser's fragmenting changes, the interaction changes with it. It is pinned by tests in both
   directions; it is not pinned against a library upgrade.

5. **The R-SEC-026 fix rewrote the call-walking core that all three code guards share.** The
   suite is green and a fresh ten-shape sweep is clean, but this is the most load-bearing
   change in Part 3 and the one where a subtle miss would be a *false negative* — the direction
   no test in this repository is well placed to notice. The controls I added
   (an unshadowed write inside a comprehension, a non-shadowing lambda, the outermost iterable)
   are the three I could think of; a fourth is what a reviewer should look for.

6. **`test_a_map_may_not_count_a_message_no_observation_placed_in_any_thread` is a rule nothing
   in the existing suite previously exercised.** It passed on the first run, which means no
   existing fixture builds a map from unthreaded observations. That is either evidence the rule
   is natural or evidence the rule is untested by anything but its own test. I believe the
   former — a map is built from a `threads.get`, whose constructor requires a thread — but the
   only proof is the one test.
