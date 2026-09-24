# M1 findings ledger — the independent review, and what was done about it

## The M1 commit ledger

**Seven** implementation and correction commits, plus the closure pass that follows them.
Recorded here because an earlier completion report said six, and a count of one's own work
that is wrong by one is the smallest possible instance of the defect this whole ledger is
about.

| # | Commit | What it did |
|---|---|---|
| 1 | `8c9e904` | source-independent contracts, and the gates computed rather than declared |
| 2 | `e14f144` | the adapter boundary, the Gmail adapter, the registry, the budget |
| 3 | `35daaf2` | the Orivra MCP surface, and the replant guard that had stopped guarding |
| 4 | `73fa1f6` | the bounded seeder, and a guard runner that swept one tree of two |
| 5 | `b628b24` | handle compatibility proved by execution; one level-2 comparison for both runs |
| 6 | `74540bc` | fifteen replants for M1's own behaviours — and the one that was MISSED |
| 7 | `803b597` | the correction pass, from the independent review below |
| 8 | this one | the closure pass: the owner's R-M1-016 decision, and two plan/runner corrections |

One implementation owner, one focused reviewer, one correction pass. The reviewer audited
`8c9e904 … 74540bc` against a ten-criterion rubric it was given rather than one it chose, was
barred from editing anything, and was required to reproduce every claimed defect by execution
or label it a hypothesis. It reproduced all but one.

**Its verdict, in its own words: "M1 is green and M1 is not correct."** Four criteria that
mattered most failed: claims matching code, the four gates of a source-stated assertion,
permission and privacy, and error paths. The pattern is worth recording because it is not the
one the implementer expected: the schema layer was strong (30 of the reviewer's 44 mutations
to the pydantic validators were caught), and **everything between the schemas and the wire was
weak**. A contract that cannot be constructed wrongly does not help if nothing constructs it,
and the delivered path — `orivra_ask` — was where the defects were.

## What was fixed in the correction pass

| ID | Severity | What was wrong | What it is now |
|---|---|---|---|
| R-M1-001 | CRITICAL | `orivra_ask` caught 3 of the 10 exception classes `mailweave_call` catches; a `ValidationError` escaped with `input_value=<the node, content included>` — **R-SEC-043 recurring** | `mailweave.surface.server.in_band` is now a function over a thunk and **both** surfaces call it. One partition, so the two cannot drift again |
| R-M1-002 | CRITICAL | `except LookupError` caught every `KeyError`/`IndexError` in a handler and wrote `str(exc)` into the response as an `auth_reauth_required` remediation | `ConnectorUnavailable(RuntimeError)`, caught by name. The message echoed is this repository's own constant |
| R-M1-003 | CRITICAL | `Candidate.matches` was a **bidirectional** subset, so a candidate keyed on one common word matched any phrase containing it, and being the only match made the resolution "unique". The reviewer built a contract-accepted **observed** `supersedes_stated` edge pointing at a document the sentence never named | One direction: the candidate's keys must account for **every** word the reference used. Plus `GENERIC_TOKENS` — a token rule replacing the phrase list, which fired only on an exact whole-phrase match |
| R-M1-004 | CRITICAL | `Source.collapsed_runs` — MailWeave's fourth accounting shape — was not translated. A 300-message thread produced a container node saying `included=300` and **zero** omission records | `omission_from_collapsed_run`, at `BRANCH` granularity, carrying MailWeave's own affordance. A test asserts nodes + omissions ≥ stated |
| R-M1-005 | HIGH | `container()` read `source.messages` only, so a compacted thread came back with no members and no way to ask for more | Collapsed members are members; ordered by position; `len(member_ids) == stated_total` |
| R-M1-006 | HIGH | `nodes.py` says node content is unfenced; the code returned fenced text, shifting every span offset by 46 characters and putting a dead nonce into a cacheable node | `_text_of` unfences with `envelope/fence.py`'s own inverse |
| R-M1-007 | HIGH | The level-2 runner recorded **EQUIVALENT** when `orivra_ask` declined and `mailweave_search` answered — M1's own evidence reporting success on maximal divergence | A missing container is a `Difference` |
| R-M1-008 | HIGH | `version_of` returned `users.getProfile().historyId` — the **mailbox** watermark — and paid an extra call for it | `message.history_id`. Asserted by the calls made, because the fixture cannot distinguish the values |
| R-M1-009 | HIGH | `partial_source_failure` was reported as `freshness_unverifiable`, sending a caller to re-verify something never fetched | `OmissionCause.PARTIAL_SOURCE_FAILURE` |
| R-M1-010 | HIGH | The hand-written `orivra_ask` schema published four `view` values where the parser accepts two, and `additionalProperties: false` while seven argument blocks were honoured | Derived from `mailweave_search`'s own schema plus `sources`, because `ask` forwards to `parse_search` |
| R-M1-011 | HIGH | `ExpansionHandle`'s validator implemented **neither** rule its docstring stated | Both rules, both tested |
| R-M1-012 | HIGH | `equivalence.py` cited an `execute_and_compare` that does not exist, in the sentence covering the one dimension level 2 cannot compare as bytes | The claim now names the test that actually runs them |
| R-M1-013 | HIGH | `cleanup` deleted without the account assertion the module docstring said guarded every write | `assert_seed_account` before the first delete |
| R-M1-014 | HIGH | A different `master_seed` changed thread lengths and evidence positions, and the test named for the claim asserted only that thread **keys** matched — strings identical for every seed by construction | `_shape_rng`, seeded without `master_seed` |
| R-M1-015 | HIGH | `tests/fixtures/source_trees.TREES` listed two trees of three, so every standing-cycle sweep — including the one that exists so R-SEC-043 cannot recur — never read `orivra/src`. **That is why R-M1-001 got through** | Derived from `[tool.uv.workspace] members` |
| R-M1-017 | MEDIUM | `items()` returned a snippet for `stub` and degraded `raw` to metadata | Stub discloses nothing; `raw` fetches a body |
| R-M1-018 | MEDIUM | A connected source the call did not ask for reported `ready` with `hits: 0`, distinguished from "found nothing" only by prose | `asked` is a published field |
| R-M1-019 | MEDIUM | `to:` was published as an emitted operator and never emitted; every participant became a sender filter | `QueryFacts.recipients`, emitted as `to:` |
| R-M1-020 | MEDIUM | `_timestamps` raised on a pattern-valid 19-digit `internalDate`, taking down the whole tool call | An unrepresentable instant is an absent one |
| R-M1-021 | MEDIUM | A refusal echoed `referring_text` — up to 400 characters of message body — into a validation report | The field, never the value |
| R-M1-022 | MEDIUM | `OutcomeRates`' docstring contradicted its own arithmetic, in the paragraph explaining why the three rates must be read together | The docstring; the code was right |
| R-M1-026 | LOW | A validator comparing `len(list(d.values()))` to `len(d)` — always equal, with a `# pragma: no cover` acknowledging it | Checks what a caller can get wrong |
| R-M1-027 | LOW | `DEFAULT_TARGET`, defined and read nowhere, left by the commit that fixed the sweep | Removed |
| R-M1-028 | LOW | A bare `assert` the partition does not catch and that vanishes under `-O`; a filter condition that is always true | A declared internal failure; the filter is gone |

Also fixed, found by the extended sweep rather than by the reviewer: the citation sweep's
pattern had no leading `\b`, so `test_ts` inside Slack's `latest_ts` was read as a citation of
a test nobody had written. A standing sweep that reports prose as a broken citation trains
readers to disbelieve it.

**Eighteen replants (R147–R164) and a re-anchored R134** defend the corrections. Each removes
the *fix* rather than the original behaviour, so a change that reverts one fails the test that
correction shipped with. Two were MISSED on the first run and the **tests** were wrong, not
the rules: R153's asserted a value the synthetic mailbox cannot distinguish, and R154's plant
varied a shape within one process where the test compares two. Both were rewritten to be
decidable.

## R-M1-016 — settled by the owner, and built in the closure pass

The finding: `EvidenceEdge` carried one `PermissionContext`, `PermissionContext.covers` is
false whenever the connectors differ, and the support rule required that single context to
cover every supporting reference — so a Gmail↔Drive edge was **unconstructible**. Orivra v1's
premise is evidence spanning three sources, which made this execution disproving a stated
premise rather than a bug.

**The owner's decision, and what it now is in code:**

- An edge carries a **conjunction of per-source permission requirements** —
  `orivra.contracts.permission.PermissionRequirement`, one per `(connector, principal)`,
  grouped from the references the edge rests on. Not one synthetic context spanning sources,
  which would need a scope vocabulary that does not exist. Not a union, which asks "does the
  caller hold *any* of these?" and lets Drive access stand in for Slack access.
- `requires` is **re-derived from `support` and compared** at construction, so a builder
  cannot understate what an edge needs.
- An edge is returned **only** when `permission.release` passes a **live** probe on every
  requirement *and* every reference — two questions, because a grant can be unchanged while a
  file is unshared or a channel is left. A conjunction over an empty requirement set is
  refused rather than being vacuously true.
- A failure produces `permission_safe_omission`: connector and cause and **nothing else** —
  no id, no count, no handle, no relation, no target. The connector named is the one the
  caller can already see, never the one that failed, because a record saying `drive` to a
  caller with no Drive access discloses that a Drive document exists.
- **A permission hash may take part in cache identity and may never authorise serving.**
  `EvidenceEdge.cache_identity` is a digest over the conjunction; `release` is the only
  function that decides releasability, and it takes a probe rather than a hash.

Tested: Gmail↔Drive and Gmail↔Slack edges constructible; the conjunction is neither a union
nor a synthetic context; loss of access to one endpoint refuses the whole edge; loss of one
source's authorisation refuses the whole edge; the omission record leaks no id, native id,
edge id, relation or connector name; and a matching cache identity does not release a refused
caller.

## Backlog — non-critical, recorded rather than fixed

1. **A nonce-injection seam.** Full two-run byte identity needs an injected nonce source;
   v0.1 exposes one on `EnvelopeBuilder` but not through `MailweaveService` or `assemble`.
   Adding it changes the frozen retrieval path. The exact level-1 check (same envelope object,
   proved with a recording adapter) already establishes what the seam would be used for.
2. **An uncaught exception's text still reaches the SDK.** Both surfaces let a bare
   `KeyError` propagate; whether the SDK renders it is outside this repo. Pre-existing in
   v0.1, not an M1 regression, and it applies to both paths equally — which is why it was not
   fixed on one of them.
3. **Three `SourceState` values are unreachable** (`auth_required`, `degraded`, `unavailable`).
   `_spend_of` hardcodes `READY`. They become reachable when M2 adds the per-source failure
   handling that can produce them; until then the schema publishes a wider vocabulary than the
   code emits.
4. **`AdapterResult.nodes` and `.omissions` are not published.** They are the adapter's
   contract output and M3's graph builder is their consumer. Publishing them now would be a
   second statement of the Gmail container's own accounting; when a second source lands, the
   normalised view is published and **checked against** each container rather than asserted
   beside it.
5. **The clause gate is scope-blind** (R-M1-025). It scans the sentence and the line rather
   than the governing clause, so "the May 2 pricing draft" refuses on the modal `may` and a
   later unrelated question on the same line refuses the assertion. Every failure is in the
   safe direction — no edge rather than a wrong edge — but the positive rate is lower than the
   design believes, and a clause-structured recogniser is M3's work.
6. **`_cause_of`'s cap table and `INTERROGATIVE_OPENERS`** have coverage the manifest does not
   reach individually; the families are tested, the individual cues are not.
7. **Budget stages vs the plan's schedule** (R-M1-031). Plan §2.3 says `cold_start_ms`,
   `retrieval_ms` (Gmail) and `disclosure_ms` are first measured at M1; `m1_budget()` ships all
   eight unmeasured, each stating why. Declared, and a deviation.

## What the reviewer recorded as holding up

`server/src/mailweave/` was byte-identical to `v0.1` before this pass (`git diff v0.1 --stat
-- server/` empty); the one change since is the `in_band` extraction, which moves no behaviour
and is covered by the whole suite and the replant manifest. The four `mailweave_*` `types.Tool`
objects are identical field-for-field to `mailweave serve`'s with no `outputSchema` added. The
`anyio.Lock` covers both tool families. `settle`, `wilson_interval` and `outcome_rates` are
correct against reference values. And R134's self-caught MISS in the first replant round was
the methodology working before any reviewer looked.

---

## M1 closed — 2026-09-10

Closed by owner decision on the live level-2 acceptance at commit `91a2607`, recorded in
`validation-records/M1_LIVE_ACCEPTANCE.md`: verdict `equivalent`, `diverged: []`, four
demonstration queries equivalent through both surfaces, 11 of 11 affordance pairs executed, zero
unexecuted and zero unresolved.

The completion report is `docs/M1_COMPLETION.md`.

The seven backlog items above are **not** reopened. They travel with M2 and are re-triaged there
against M2's own rubric. Non-critical observations about M1 are not grounds to reopen it.
