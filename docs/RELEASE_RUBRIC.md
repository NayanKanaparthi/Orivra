# RELEASE_RUBRIC.md — The objective definition of done

**Status:** authoritative completion criteria. Required by `docs/SCOPE_CORRECTION.md` §16.
**Contract authority:** `docs/PRODUCT_CONTRACT.md` (clause IDs `C-…`, `I-…`, `R-…`, `N-…`, `B-…`,
`H-…` are cited below). **Process authority:** `docs/AGENT_LOOP.md`.
**Nothing here is waivable by an agent.** Waiving any criterion is a human decision recorded in the
findings ledger with a reason (AGENT_LOOP §10).

## How to use this document

- **Status values:** `PASS` / `FAIL` / `BLOCKER` / `NOT TESTED`. Only a **reviewer who did not write
  the code** may set `PASS`, and only by reproducing the acceptance evidence itself (AGENT_LOOP §1,
  §6). Every transition records round number and reviewer ID.
- **`NOT TESTED` blocks release exactly like `FAIL`.** It is never a soft pass (PROC-01).
- **Flags.** `M` = mandatory. `C` = mandatory once its stated trigger fires. `O` = optional; never
  blocks, never silently dropped.
- **Verification** names the reviewer domain (R-RETR, R-DISC, R-ARCH, R-SEC, R-PERF, R-MCP, R-GMAIL,
  plus the adversarial reviewer) and the artifact that proves it.
- **Guard** = the degenerate-strategy guard. For every metric-based criterion it names the dumbest
  implementation that would max the metric and the companion condition that fails that
  implementation (AGENT_LOOP §7.5).
- **Numeric bars carry one of three class markers**, adopted from `EVALUATION_PLAN.md` §13.2 so a
  reviewer can tell which numbers already bind and which genuinely block (CONS-017):
  - **`[DEFINITIONAL]`** — structural or binary; settable now, measurement only checks it (zero
    non-Google egress; no unexplained `not_found`; provenance labelling; violations = 0).
  - **`[INHERITED — EP §13.4 <gate>]`** — carried forward from Revision 1's proposals **unchanged and
    already binding**. These are the CG-EP / CG-PD / CG-AD numbers. A reviewer does **not** re-derive
    them at G0; EP §13.5 closes by naming them "unchanged and still binding".
  - **`[UNSET — register at G0 per EP §13.2 against <named reference distribution>]`** — genuinely not
    yet knowable. It must be written into experiment log 001, as a delta or bound against the named
    G0-measured distribution, **before any implementation is reviewed against it**. Fabricating a
    threshold is worse than deferring one; **a criterion reviewed against an unregistered UNSET number
    is itself a BLOCKER.** That rule applies to UNSET only — an inherited bar is already registered.
- **EP citations are to `EVALUATION_PLAN.md` Revision 2.** Revision-1 numbering is stale and resolves
  to unrelated material (e.g. old "§8.2" now lands on *Baseline B — full-thread dump*), so all
  citations here were re-pointed (CONS-009).
- **Criterion IDs are independent of EP assertion IDs.** In particular `PART-0n` ≠ EP §6.2's `P-n`.
  The mapping is: PART-01 → P1/P1a, PART-02 → P2, PART-03 → P3, PART-04 → O3 + the P-follow driver,
  PART-05 → contract R-06 (EP has no P-n for it), PART-06 → EP §6.2's end-to-end partiality probe,
  PART-07 → P4 + P6. Reading "P4 ≥ 0.95" against PART-04 applies a bar belonging to a different
  assertion (CONS-011).
- **Canonical vocabulary (CONS-033).** `stated_total` is the wire field; `claimed_total` is only the
  harness-normalised name for it in EP §6.2 (one quantity, two contexts, no second field). Depth
  vocabulary is `stub / snippet / body_clean / body_full / raw`. Roles are the seven values of
  contract R-02. Cross-call state is a server-minted `map_id`; "cursor" is retired. Coverage is
  `asked_for.term_coverage`. Substrates are Tier 1/2/3; execution modes M1/M2; gates G0 + `CG-*`;
  preflights `PF-n`. "Loop *n*" survives only as `AGENT_LOOP.md` §5's round loop, and every former
  "Loop *n*" bar reference below now names its gate.
- Source shorthand as in the contract: `CTX`, `SC`, `RO`, `CD`, `SN`, `RT`, `VR`, `EP`.

---

## Status summary

| ID | Criterion | Flag | Status |
|---|---|---|---|
| EV-01 | Retrieved-hit containment | M | NOT TESTED |
| EV-02 | Position-independent evidence recall | M | NOT TESTED |
| EV-03 | Withheld-record discipline | M | NOT TESTED |
| EV-04 | Zero false "not found" on answerable cases | M | NOT TESTED |
| EV-05 | Issue #296 signature is non-reproducible | M | NOT TESTED |
| EV-06 | Recall against the full-dump ceiling | M | NOT TESTED |
| LEX-01 | Message-level search is the first rung | M | NOT TESTED |
| LEX-02 | Operator-parse fidelity and coverage reporting | M | NOT TESTED |
| LEX-03 | Multi-constraint decomposition | M | NOT TESTED |
| LEX-04 | Exact-signal stop | M | NOT TESTED |
| STR-01 | Reply-tree reconstruction with declared gaps | M | NOT TESTED |
| STR-02 | Participant retrieval keyed on address; authorship vs hearsay | M | NOT TESTED |
| STR-03 | Temporal ordering from internalDate | M | NOT TESTED |
| STR-04 | Thread position exposed | M | NOT TESTED |
| STR-05 | Multi-thread evidence assembly | M | NOT TESTED |
| SEM-01 | Semantic escalation resolves paraphrase misses | M | NOT TESTED |
| SEM-02 | Local, zero-cost default semantic path | M | NOT TESTED |
| SEM-03 | Provider-agnostic semantic interface | M | NOT TESTED |
| SEM-04 | Semantic path stays off easy queries | M | NOT TESTED |
| SEM-05 | Semantic adopt/reject decision is measured and logged | M | NOT TESTED |
| SEM-06 | Selection provenance and pool disclosure | M | NOT TESTED |
| RANK-01 | Ranking is ambiguity-gated | M | NOT TESTED |
| RANK-02 | Ranking beats recency and random controls | M | NOT TESTED |
| RANK-03 | No fabricated scores or reasons | M | NOT TESTED |
| RANK-04 | Bounded candidate disclosure | M | NOT TESTED |
| AD-01 | Escalation ladder with enforced budget caps | M | NOT TESTED |
| AD-02 | Stop on strong evidence | M | NOT TESTED |
| AD-03 | Budget exhaustion is reported in-band | M | NOT TESTED |
| AD-04 | Cheap queries stay cheap | M | NOT TESTED |
| AD-05 | Escalation actually fires when needed | M | NOT TESTED |
| ROUTE-01 | No bare empty response | M | NOT TESTED |
| ROUTE-02 | Mis-parse recovery | M | NOT TESTED |
| ROUTE-03 | Relaxation is systematic and enumerable | M | NOT TESTED |
| ROUTE-04 | Empty-result diagnosis | M | NOT TESTED |
| DISC-01 | Output is conditioned on the query | M | NOT TESTED |
| DISC-02 | Query-aware policy vs fixed window at equal budget | M | NOT TESTED |
| DISC-03 | Depth vocabulary and declared reductions | M | NOT TESTED |
| DISC-04 | Context efficiency against full dump | M | NOT TESTED |
| DISC-05 | Disclosure depth is justified by measurement | C | NOT TESTED |
| DISC-06 | Self-truncation before host truncation | M | NOT TESTED |
| PART-01 | Stated total present and correct | M | NOT TESTED |
| PART-02 | Included set matches the payload | M | PASS |
| PART-03 | More-available signalled iff partial | M | PASS |
| PART-04 | Affordances are executable | M | NOT TESTED |
| PART-05 | Unexpanded content is visible as stubs | M | NOT TESTED |
| PART-06 | Partiality survives into agent understanding | M | NOT TESTED |
| PART-07 | Role and reason on every message | M | NOT TESTED |
| MCP-01 | Spec-revision conformance; no Sampling | M | NOT TESTED |
| MCP-02 | Stateless server-minted handles | M | NOT TESTED |
| MCP-03 | Structured/text output parity | M | NOT TESTED |
| MCP-04 | Truthful annotations | M | NOT TESTED |
| MCP-05 | Tool metadata is compile-time constant | M | NOT TESTED |
| MCP-06 | Handle invalidation fails loudly | M | NOT TESTED |
| MCP-07 | Real client completes the loop | M | NOT TESTED |
| GMAIL-01 | Live-mailbox smoke suite | M | NOT TESTED |
| GMAIL-02 | MIME and header reality | M | NOT TESTED |
| GMAIL-03 | Thread-completeness semantics validated | M | NOT TESTED |
| GMAIL-04 | Pagination correctness | M | NOT TESTED |
| GMAIL-05 | Quota and rate-limit behavior | M | NOT TESTED |
| GMAIL-06 | Auth lifecycle exercised | M | NOT TESTED |
| GMAIL-07 | Reality-tier oracles clean | M | NOT TESTED |
| FRESH-01 | Freshness protocol executed and published | M | NOT TESTED |
| FRESH-02 | Mitigation built if lag exceeds the bar | C | NOT TESTED |
| FRESH-03 | Staleness stamps everywhere | M | NOT TESTED |
| FRESH-04 | No freshness claim without an entry | M | NOT TESTED |
| FRESH-05 | FSL registered before the probe run | M | NOT TESTED |
| FRESH-06 | Temporal partiality field | M | NOT TESTED |
| PERF-01 | Simple-family latency ceiling | M | NOT TESTED |
| PERF-02 | Network-level API call accounting | M | NOT TESTED |
| PERF-03 | No cross-round performance regression | M | NOT TESTED |
| PERF-04 | Cost tracks ambiguity | M | NOT TESTED |
| SEC-01 | Exactly one Gmail scope | M | NOT TESTED |
| SEC-02 | No write path reachable from any tool | M | NOT TESTED |
| SEC-03 | Harness isolation and account pinning | M | NOT TESTED |
| SEC-04 | Token storage hygiene | M | PASS |
| SEC-05 | No mail content at rest by default | M | NOT TESTED |
| SEC-06 | Trace redaction canary | M | NOT TESTED |
| SEC-07 | No telemetry; two-host egress; no listening socket | M | NOT TESTED |
| SEC-08 | No learned routing policy | M | NOT TESTED |
| INJ-01 | Untrusted envelope on all mail-derived text | M | NOT TESTED |
| INJ-02 | Mail text never reaches connector-voiced surfaces | M | NOT TESTED |
| INJ-03 | Injection fixtures neither steer nor disappear | M | NOT TESTED |
| INJ-04 | HTML pipeline: visible text, flagged hiding, no network | M | NOT TESTED |
| INJ-05 | Identity fields split; auth results labeled | M | NOT TESTED |
| INJ-06 | Internal model outputs are closed-typed | M | NOT TESTED |
| OBS-01 | Trace schema completeness | M | NOT TESTED |
| OBS-02 | Headline metrics come from harness measurement | M | NOT TESTED |
| OBS-03 | Traces support post-hoc replay | O | NOT TESTED |
| OBS-04 | Self-reported counters cross-check | M | NOT TESTED |
| NFR-01 | Full suite passes with no paid API key | M | PASS |
| NFR-02 | Local operation footprint documented | M | NOT TESTED |
| NFR-03 | Gmail remains the source of truth | M | NOT TESTED |
| NFR-04 | Clean-machine reproducible setup | M | PASS |
| REG-01 | Every real failure yields a regression test | M | NOT TESTED |
| REG-02 | Regression tests fail against the pre-fix commit | M | NOT TESTED |
| REG-03 | No benchmark special-casing in tests or code | M | NOT TESTED |
| REG-04 | Fixtures sanitized; suite runs offline | M | PASS |
| E2E-01 | Required real-Gmail E2E set is green | M | NOT TESTED |
| E2E-02 | Corpus regenerated from a fresh seed each gate | M | NOT TESTED |
| E2E-03 | Reviewer-selected held-out seed | M | NOT TESTED |
| E2E-04 | Both mailbox profiles exercised | M | NOT TESTED |
| DOC-01 | Every claim maps to a measurement | M | NOT TESTED |
| DOC-02 | Problems stated unbundled | M | NOT TESTED |
| DOC-03 | Limitations and not-measured section | M | NOT TESTED |
| DOC-04 | Prior art cited honestly | M | NOT TESTED |
| DOC-05 | Read-only wording and untrusted-content disclosure | M | NOT TESTED |
| DOC-06 | §58 minimum-proof bundle complete before the headline claim | M | NOT TESTED |
| PROC-01 | NOT TESTED blocks release | M | NOT TESTED |
| PROC-02 | No criterion certified by its implementer | M | NOT TESTED |
| PROC-03 | Ground truth unreadable by the server | M | NOT TESTED |
| PROC-04 | Baselines still runnable | M | NOT TESTED |
| PROC-05 | Degenerate-strategy probe recorded per metric | M | NOT TESTED |
| PROC-06 | Adversarial reviewer pass before the gate | M | NOT TESTED |

**Totals:** **113 criteria** across 21 categories — **110 `M`**, **2 `C`** (DISC-05, FRESH-02),
**1 `O`** (OBS-03). Release requires every `M` and every triggered `C` at `PASS`, and no criterion at
`NOT TESTED`.

*Change from the pre-repair table (Round 1):* seven criteria added — SEM-06, PART-07, GMAIL-07,
FRESH-05, FRESH-06, SEC-08, DOC-06 — each closing a contract MUST or a gate requirement that had no
criterion; and INJ-05 promoted `O` → `M` (CONS-028), so 102 `M` + 7 + 1 = 110 `M`, and `O` falls from
2 to 1. **DISC-05's trigger is declared met by the architecture (§H-3)**, so in practice 111 criteria
bind today and FRESH-02 is the only genuinely conditional one. IDs are stable and append-only
(PROC-01): nothing was renumbered or removed.

---

## 1. Evidence preservation — contract I-1, C-01

**EV-01 · Retrieved-hit containment · M · NOT TESTED**
*Statement.* Every message identified by an executed retrieval stage appears in the response, at some
depth, or in an explicit withheld record.
*Acceptance.* For every case in the full suite: `H ⊆ R`, where — identically to contract I-1 —
`H` (the **hit set**) = (a) every message ID returned by an **executed Gmail query**, including the
relaxation/broadening `messages.list` calls and the participant `from:`/`to:` probes that build a
semantic candidate pool, **plus** (b) from any scored retriever, the candidates that **pass the
retriever's selection threshold** — the shortlist that enters the disclosure candidate set — **not**
every scored pool row; and `R` = IDs present in the response at any depth (a stub counts) plus IDs
listed in `withheld` with a reason naming the specific cap and a working retrieval affordance.
Violations: **0**. This is an exact set assertion, not a rate.
Additionally: (i) the shortlist size and selection rule are **declared and pre-registered** and
reported in the retrieval report — an implementation may not shrink `|H|` at review time to pass this
criterion; (ii) whenever a scored retriever ran, the response's
`pool{scope_rule, thread_count, message_count, why}` is present and correct, and the **full pool is
enumerated by ID in the trace** so `H` is checked against a real set rather than the server's account
of one; (iii) the response declares its **scan scope** (pages fetched, `maxResults`, whether unfetched
pages remain), so `H` is closed rather than open-ended.
*Verify.* R-RETR, scripted M1 driver joining trace `H` to parsed response IDs; plus a code read of
the retrieval→representation boundary showing no unlogged filter, and a read of the cap-handling paths
showing every cap emits a `withheld` record rather than dropping.
*Guard.* Two directions, both required. **Inflationary** dumbest max: return every message of every
candidate thread — ruled out by DISC-04's token ceiling and PERF-01's call ceiling, which EV-01 must
pass simultaneously. **Deflationary** dumbest max (the one the shortlist reading would otherwise
legalise): set the retriever's selection threshold so high that `H_semantic ≈ ∅` and the set assertion
passes vacuously — ruled out by the declared, pre-registered shortlist size, by SEM-01's gain bar and
EV-06's recall bar on the same run, and by SEM-06's pool declaration being checked against the
trace-enumerated pool.

**EV-02 · Position-independent evidence recall · M · NOT TESTED**
*Statement.* Recall of buried evidence does not depend on where the evidence sits in the thread.
*Acceptance.* On the position sweep (7 positions across a ~100-message thread, EP §4.4): evidence
recall ≥ `[INHERITED — EP §13.4 CG-EP: ≥0.98]` overall, ≥ `[INHERITED — EP §13.4 CG-EP: ≥0.95]` at
**every** position, and max−min spread ≤ `[INHERITED — EP §13.4 CG-EP: ≤0.05]`. Bars bind per
position, never on the mean.
*Verify.* R-RETR on a reviewer-chosen HOLDOUT seed; two fresh seeds must agree within CI (EP §13.1).
*Guard.* Dumbest max: full-thread dump makes recall position-flat trivially. Ruled out by requiring
DISC-04 and PERF-01 to pass on the same run. Second guard: a fixed newest-K or oldest-K policy passes
the mean but fails the per-position bar by construction.

**EV-03 · Withheld-record discipline · M · NOT TESTED**
*Statement.* Nothing may be dropped between retrieval and representation without a record.
*Acceptance.* Any hit not disclosed at body depth appears as a stub or a withheld record carrying:
message ID, why it was not expanded (budget, depth policy, dedup), and an executable affordance.
Responses containing an undocumented drop: **0**.
*Verify.* R-DISC by response-schema assertion over the full suite; R-ARCH by code read of every code
path that can remove a candidate.
*Guard.* Dumbest max: never drop anything (dump). Same pairing as EV-01. Inverse guard: a policy that
labels everything "withheld" and discloses nothing fails EV-06 and DISC-04's recall pairing.

**EV-04 · Zero false "not found" on answerable cases · M · NOT TESTED**
*Statement.* MailWeave never reports that retrievable evidence does not exist.
*Acceptance.* False-not-found rate = **0** over all answerable cases in the exact-lookup and
buried-evidence families. Classification per EP §6.1 (explicit machine-readable field preferred;
pinned blind classifier otherwise, agreement ≥0.9 validated once).
*Verify.* R-RETR from terminal responses; adversarial reviewer re-runs on its own seed.
*Guard.* Dumbest max: never say "not found" — always return something. Ruled out by the **paired**
hallucinated-found rate on unanswerable controls ≤ `[INHERITED — EP §13.4 CG-EP: ≤0.10]`; the two rates
are always reported together and neither may be reported alone.

**EV-05 · Issue #296 signature is non-reproducible · M · NOT TESTED**
*Statement.* The documented failure cannot occur through MailWeave.
*Acceptance.* For a deep message *m* in a long thread: `rfc822msgid:<m>` through MailWeave returns a
response in which *m* is present at body depth; and a `newer_than:1d`-style recency query returns only
messages consistent with the filter, or explicitly declares the ones that are not and why (VR §1.1).
Both assertions pass on the live account and on the seeded corpus.
*Verify.* R-GMAIL against the live mailbox; recorded transcript in the experiment log.
*Guard.* Dumbest max: special-case `rfc822msgid:` queries. Ruled out by REG-03's grep sweep for
query-pattern special-casing and by requiring the same behavior for the non-ID buried-evidence family.

**EV-06 · Recall against the full-dump ceiling · M · NOT TESTED**
*Statement.* MailWeave's evidence recall is at or near the full-thread-dump ceiling.
*Acceptance.* Overall evidence recall within `[INHERITED — EP §13.4 CG-EP: ≤2 points below
Baseline B]` on the same corpus instance, paired scoring (McNemar).
*Verify.* R-RETR; Baseline B run in the same interleaved session (PROC-04).
*Guard.* Dumbest max: *be* Baseline B. Ruled out by DISC-04's token ceiling on the same run; a system
that matches B's recall at B's token cost fails the gate.

---

## 2. Lexical / deterministic retrieval — contract C-01

**LEX-01 · Message-level search is the first rung · M · NOT TESTED**
*Statement.* The default first path is `users.messages.list(q=…)` at message granularity, never a
thread preview.
*Acceptance.* Traces for every case show the first Gmail call is `messages.list` with a `q`; no code
path derives the primary hit set from a thread-level listing. Message-level hit IDs are carried
end-to-end (RO F1).
*Verify.* R-RETR trace inspection + R-ARCH code read.
*Guard.* Not metric-based.

**LEX-02 · Operator-parse fidelity and coverage reporting · M · NOT TESTED**
*Statement.* Parsed query signals are either enforced in the executed `q` or reported as dropped.
*Acceptance.* For every response, `asked_for.term_coverage` is computed and reported; every dropped
signal is named with the rung that dropped it. Cases where a signal was silently dropped: **0**.
Operators used are limited to Gmail's documented set (RO F3). Additionally, every response carries a
complete `asked_for` block — parsed constraints, which were enforced, which were dropped and why,
`term_coverage`, `constraint_drop_depth` — and **every disclosed message carries
`constraint_coverage`** naming which of the user's parsed constraints it satisfies. This is the whole
of tension T-RC3's resolution, which until now nothing required and nothing tested (CONS-024).
*Verify.* R-RETR against adversarial parse cases (ambiguous dates, name-only senders, quoted phrases).
*Guard.* Dumbest max: never drop anything, so coverage is always 1 and the report is trivially true.
Ruled out by ROUTE-02's recovery-rate bar, which requires relaxation to occur on mis-parse cases.

**LEX-03 · Multi-constraint decomposition · M · NOT TESTED**
*Statement.* Queries whose constraints are satisfied jointly by different messages of a thread are not
silently missed.
*Acceptance.* On the sender/date and split-evidence families, MailWeave retrieves evidence that Gmail
`q` cannot match within a single message (RO F2), via decomposition and client-side thread-ID
intersection/union or an equivalent documented mechanism; recall on that family ≥ `[UNSET — register
at G0 per EP §13.2 against the G0-measured Baseline D (plain single-`q`) distribution on the same
family]`.
*Verify.* R-RETR; Baseline D provides the single-`q` floor for the same cases.
*Guard.* Dumbest max: issue one `messages.list` per query word and union everything. Ruled out by
PERF-01's per-family call ceiling and by DISC-04's token ceiling.

**LEX-04 · Exact-signal stop · M · NOT TESTED**
*Statement.* Exact-signal queries resolve on the cheapest rung.
*Acceptance.* On exact-lookup cases: rungs executed = 1, embedding calls = 0, model calls = 0,
reranker invocations = 0, network Gmail calls ≤ `[INHERITED — EP §13.4 CG-AD: median ≤3]`.
*Verify.* R-PERF from network-level counts (PERF-02), not self-reports.
*Guard.* Dumbest max: never escalate at all, making every query cheap. Ruled out by AD-05 and
ROUTE-02, which require escalation to fire and recover on hard families.

---

## 3. Structural retrieval — contract C-02

**STR-01 · Reply-tree reconstruction with declared gaps · M · NOT TESTED**
*Statement.* Reply relationships are reconstructed, and messages that cannot be linked say so.
*Acceptance.* Parent/child links derived from `In-Reply-To`/`References`; every unlinked message is
marked unlinked and ordered by `internalDate` rather than being attached to a guessed parent. On the
seeded corpus with known threading, link accuracy = **100%** against the manifest; on the live
mailbox, unlinked counts are reported, not hidden.
*Verify.* R-RETR against manifest; R-GMAIL on live threads including forwarded and subject-changed
chains.
*Guard.* Dumbest max: link everything to the previous message by date, which scores well on simple
threads. Ruled out by requiring 100% on manifest-known interleaved sub-threads and by the unlinked
declaration.

**STR-02 · Participant retrieval keyed on address; authorship vs hearsay · M · NOT TESTED**
*Statement.* "What did X say" returns what X wrote, not what others said about X.
*Acceptance.* On the participant family (hearsay distractor planted), the disclosed evidence is the
X-authored message; matching keys on the address, never the display name — From/To/Cc/Reply-To are
exposed as `{display_name, address}` pairs and never pre-joined, so a display name cannot spoof
identity; case accuracy ≥ `[UNSET — register at G0 per EP §13.2 against the G0-measured Baseline D
accuracy on the same family]`.
*Verify.* R-RETR against manifest; R-SEC confirms display-name/address separation (INJ-05, now `M` —
this criterion no longer depends on an optional one, CONS-028).
*Guard.* Dumbest max: return every message in which the string "X" appears. Ruled out by scoring
hearsay distractors as failures and by DISC-04's token ceiling.

**STR-03 · Temporal ordering from internalDate · M · NOT TESTED**
*Statement.* Chronology never depends on API array order.
*Acceptance.* All ordering, position numbering and temporal windows derive from `internalDate`; a
test that shuffles the API response array produces an identical representation. Date windows use
epoch-second bounds where timezone accuracy matters (RO F2).
*Verify.* R-ARCH via shuffle test; R-GMAIL against real timezone-boundary cases.
*Guard.* Not metric-based.

**STR-04 · Thread position exposed · M · NOT TESTED**
*Statement.* Every message carries its position and the thread's total, so the agent can aim.
*Acceptance.* R-01/R-05 fields present on 100% of thread-bearing responses; positions are contiguous
and consistent with the map.
*Verify.* R-DISC schema assertion over the full suite.
*Guard.* Not metric-based.

**STR-05 · Multi-thread evidence assembly · M · NOT TESTED**
*Statement.* Evidence split across threads is returned as multiple sources, each individually
navigable.
*Acceptance.* On the multi-thread family, all required evidence messages are disclosed within the
round budget, each with its own thread identity, total, and map affordance; strict case accuracy ≥
`[UNSET — register at G0 per EP §13.2 against the G0-measured Baseline F(±2) and Baseline C curves on
F7]`.
*Verify.* R-RETR + R-DISC on the same transcripts.
*Guard.* Dumbest max: dump the top *N* threads whole. Ruled out by the per-response token ceiling
(DISC-06) and DISC-04's efficiency bar computed across all disclosed threads, not just the focal one.

---

## 4. Semantic retrieval — contract C-03

**SEM-01 · Semantic escalation resolves paraphrase misses · M · NOT TESTED**
*Statement.* Conceptual/paraphrased queries that lexical retrieval cannot resolve are resolved by the
semantic rung.
*Acceptance.* On zero-content-word-overlap paraphrase cases (F4-T2, F4-T3, F11), recall with the
semantic rung enabled exceeds the SEM-OFF ablation by ≥ `[UNSET-empirical `semantic_gain`; registered
at G0 as a delta against the G0-measured SEM-OFF distribution on the same HOLDOUT seed, per EP §13.2]`.
Both arms are run on the same corpus instance in the same session, paired scoring (McNemar).
**There is no entry condition.** Semantic retrieval is unconditional product scope (SC §4), so this
criterion may not be excused — nor satisfied — by the lexical-only arm's score. Revision 1's "+15
points" adopt bar was **retired** by EP §13.5 ("the +15 was calibrated to an adopt/reject decision that
no longer exists; keeping the number would be borrowing authority it never had") and does not appear
here (CONS-015).
*Verify.* R-RETR, paired ablation run against SEM-OFF; result recorded in the experiment log either
way; the registered `semantic_gain` value must exist in experiment log 001 before this criterion is
reviewed, or the review itself is a BLOCKER.
*Guard.* Dumbest max: run semantic retrieval over the entire mailbox for every query. Ruled out by
SEM-04 (zero embedding calls on easy families) and PERF-01 (simple-family latency unchanged within
`[INHERITED — EP §13.4 CG-AD: p50 ≤1.25× Baseline D]`, cheap-path non-regression, EP §7.4 bar 2).

**SEM-02 · Local, zero-cost default semantic path · M · NOT TESTED**
*Statement.* The default semantic path is local and free (Appendix A.1, contract N-01/N-02).
*Acceptance.* With no API keys configured and outbound network restricted at runtime to exactly two
hosts — `gmail.googleapis.com` and `oauth2.googleapis.com` (token refresh only), **no other host** —
the semantic rung executes and SEM-01's measurement is reproducible. Mailbox content sent to any host
other than those two in the default configuration: **0 bytes** `[DEFINITIONAL]`. Model weights are
provisioned **at setup time only** from a declared model-host, and runtime loading is forced offline
(`local_files_only=True` / `HF_HUB_OFFLINE=1`) from a checksum-pinned local path — the hub
revalidation request the default library load path would otherwise make is what makes "setup-time
provisioning" insufficient on its own (ARCH_REVIEW ADV-210).
*Verify.* R-SEC via egress capture on a full suite run in the two-host allowlisted container
(EP §7.1 bar 2, S14); R-PERF re-runs SEM-01 in that configuration.
*Guard.* Dumbest max: declare a local path that silently no-ops. Ruled out by requiring SEM-01's
paraphrase recall to be met *in this configuration*.

**SEM-03 · Provider-agnostic semantic interface · M · NOT TESTED**
*Statement.* The semantic backend is pluggable; hosted providers are opt-in, never required.
*Acceptance.* A single interface with at least the local implementation behind it; a second
implementation can be registered without touching retrieval logic (demonstrated by a test double).
No code path makes a hosted provider a precondition for any core capability of contract §3.
*Verify.* R-ARCH code read + interface test.
*Guard.* Not metric-based. (Hosted backends themselves are optional; the interface is not.)

**SEM-04 · Semantic path stays off easy queries · M · NOT TESTED**
*Statement.* Semantic retrieval does not run when the cheap path is confident.
*Acceptance.* Embedding calls on the exact-lookup and sender/date families = **0**; on all families,
semantic invocation correlates with a recorded ambiguity signal, never with a fixed policy.
*Verify.* R-PERF from network/instrumented counts; R-RETR reads the gate condition in code.
*Guard.* Dumbest max: disable semantic retrieval entirely. Ruled out by SEM-01's improvement bar.

**SEM-05 · Semantic adopt/reject decision is measured and logged · M · NOT TESTED**
*Statement.* Whether semantic retrieval earns its cost is decided by measurement, and the decision —
including a rejection — is published.
*Acceptance.* An experiment log entry exists containing: the SEM-OFF ablation measurement, the
semantic arm's recall delta, latency delta, and privacy/storage delta, and an explicit adopt or reject
decision. **Scope note:** the reject branch survives only for *backend and architecture* choices —
which local model, on-demand vs persistent index, hosted opt-in — never for the semantic **capability**,
which SC §4 makes unconditional (EP §13.5 row 2). A rejection of a *backend* is a valid pass for this
criterion (EP §13.4 CG-SEM).
*Verify.* R-RETR + orchestrator; entry must predate the release gate.
*Guard.* Dumbest max: adopt semantic retrieval without measuring, because it "sounds advanced".
Ruled out by requiring the entry's numbers to exist and be reproducible on a fresh seed.

**SEM-06 · Selection provenance and pool disclosure · M · NOT TESTED**
*Statement.* A message says how it was found, and a scored retriever declares the pool it drew from.
*Acceptance.* (a) Every disclosed message names its selection method from the closed set
`lexical_hit / structural / semantic_similarity / thread_context`; (b) a semantically selected message
is **never** presented as a Gmail search hit; (c) any similarity value is labelled *similarity*, never
*confidence*, and names its method and `model_id@revision`; (d) whenever a scored retriever ran, the
response carries `pool{scope_rule, thread_count, message_count, why}` and the trace enumerates the
pool **by ID**. Violations: **0** `[DEFINITIONAL]`. (d) is contract C-03's pool-bound observable,
which the architecture implements (`retrieval_report.pool`, T-RO1) and which no criterion asserted
until now (CONS-003 orphan, CONS-013).
*Verify.* R-RETR + R-DISC schema sweep over the full suite (EP §6.4 P6); R-ARCH reads the pool
construction path and confirms the trace enumeration matches the declared size.
*Guard.* Dumbest max: label everything `lexical_hit`, which is always true of the first rung and
always cheap. Ruled out by SEM-01 — a run with a measured `semantic_gain` must contain
semantically-selected messages — and by the trace-to-response join, which catches a message that the
trace shows was scored by the retriever and the response labels a search hit.

---

## 5. Candidate ranking — contract C-04

**RANK-01 · Ranking is ambiguity-gated · M · NOT TESTED**
*Statement.* Ranking/reranking runs only when a recorded ambiguity signal fires.
*Acceptance.* Reranker invocations on exact-signal cases = **0**; every invocation elsewhere names the
firing signal (hit-count band, coverage < 1, thread concentration, score margin — RT §5.1) in the
trace.
*Verify.* R-RETR trace + code read.
*Guard.* Dumbest max: always rerank (maximizes ordering quality). Ruled out by the zero-invocation
assertion on exact cases and by PERF-01.

**RANK-02 · Ranking beats recency and random controls · M · NOT TESTED**
*Statement.* The ranker demonstrably orders better than trivial orderings.
*Acceptance.* On ambiguous families, mean target rank (and recall@k for the disclosed prefix) is
better than both a recency-ordered control and a seeded random-order control by ≥ `[UNSET — register
at G0 per EP §13.2 against the G0-measured recency and seeded-random control distributions on F16]`,
on paired cases with CIs reported.
*Verify.* R-RETR; the two controls are permanent harness fixtures alongside the baselines (PROC-04).
*Guard.* Dumbest max: return all candidates at body depth so target rank is meaningless. Ruled out by
RANK-04's disclosure cap, which fixes the prefix length the metric is computed over.

**RANK-03 · No fabricated scores or reasons · M · NOT TESTED**
*Statement.* Every reason is mechanical; every number names its method (CTX §20).
*Acceptance.* Sampling 100% of responses in a full suite run: no numeric relevance value appears
without an adjacent method + model identifier; results selected by Gmail `q` say exactly that; no
free-text rationale is generated for a lexical hit. Violations: **0**.
*Verify.* R-DISC schema sweep; R-ARCH code read of every field that can carry a score.
*Guard.* Dumbest max: emit no reasons at all. Ruled out by **PART-07**, which asserts a non-empty
mechanical `reason` on 100% of messages — reasons must be present *and* mechanical. (The former
pointer to DISC-03 was wrong: DISC-03 is about depth and declared reductions and contains no presence
requirement, CONS-008.)

**RANK-04 · Bounded candidate disclosure · M · NOT TESTED**
*Statement.* Ranking narrows; it does not become a pretext for disclosing everything.
*Acceptance.* Candidates disclosed at body depth per response ≤ `[UNSET — register at G0 per EP
§13.2 against the G0-measured budget–recall curve (EP §7.2) and the CD §6.3 budget ladder]`; the
remainder appears as ranked stubs with reasons **or as `withheld` records** (EV-01) — a cap may never
silently drop a hit.
*Verify.* R-DISC assertion over the suite.
*Guard.* This criterion *is* the guard for RANK-02; its own inverse degenerate (disclose 1 candidate
always) is ruled out by EV-06 and EV-02.

---

## 6. Adaptive escalation and stopping — contract C-05, invariant I-3

**AD-01 · Escalation ladder with enforced budget caps · M · NOT TESTED**
*Statement.* The ladder exists in code with per-rung and global caps.
*Acceptance.* Named rungs with documented caps (per-rung call budgets, max rounds, max Gmail calls,
server-side latency budget); caps are enforced in code, not by convention; a test drives each cap to
exhaustion and observes the enforced stop.
*Verify.* R-ARCH code read + cap-exhaustion tests; R-PERF confirms caps hold under live latency.
*Guard.* Not metric-based.

**AD-02 · Stop on strong evidence · M · NOT TESTED**
*Statement.* Retrieval stops when the evidence is strong enough.
*Acceptance.* On exact-signal cases the ladder terminates at the first rung with a recorded stop
reason; no further Gmail calls occur after the stop condition is met.
*Verify.* R-RETR trace; R-PERF network counts.
*Guard.* Dumbest max: always stop at rung 1 (cheapest possible). Ruled out by AD-05 and EV-02.

**AD-03 · Budget exhaustion is reported in-band · M · NOT TESTED**
*Statement.* Hitting a cap is visible to the agent, never silent.
*Acceptance.* Every response produced under an exhausted cap names the cap, what was not tried, and
the affordance that would try it. Silent cap hits: **0**.
*Verify.* R-DISC by forcing caps low and asserting the response fields.
*Guard.* Not metric-based.

**AD-04 · Cheap queries stay cheap · M · NOT TESTED**
*Statement.* Simple queries do not pay for machinery they do not need.
*Acceptance.* On exact-lookup and sender/date families: p50 latency ≤ `[INHERITED — EP §13.4 CG-AD:
≤1.25× Baseline D]`, model+embedding calls = 0 `[DEFINITIONAL]`, and **both call counters bound
separately** (ARCH_REVIEW ADV-106; ARCHITECTURE §A.5b, §H-8):
(i) median `http_requests` ≤ `[INHERITED — EP §13.4 CG-AD: ≤3]` — one per HTTP request whatever a
batch contains; this is the preserved Revision-1 figure and the counter OBS-04 cross-checks against
network observation;
(ii) median `api_calls` ≤ `[UNSET — register at G0 per EP §13.2 against the G0-measured Baseline D
`api_calls` distribution on the same families]` — one per Gmail **sub-request**, which is what quota
and cost are actually charged on. `quota_units` is reported alongside as diagnostic (ARCH A.11).
*Why both, and why nothing here is relaxed.* Under HTTP batching a counting proxy sees **one** request
per `batch` call whatever *n* is, so a query issuing 1 list + 1 batch of 10 gets + 1 batch of 12 maps
reads as 3 at the proxy while costing ~665 quota units: the ≤3 figure bounds HTTP chatter, not cost.
This criterion's own statement — "simple queries do not pay for machinery they do not need" — is a
**cost** claim, so it now also binds the counter that tracks cost. Neither bar replaces the other; a
system that passed the old form while fanning out inside batches was always over cost and now fails
(ARCHITECTURE §I O-2, deferred to G0 registration rather than to an owner ruling; no number was
invented here).
*Verify.* R-PERF, interleaved runs with Baseline D, cold/warm separated (EP §8.6); the two counters are
read from the trace and cross-checked against the egress capture (OBS-04).
*Guard.* Dumbest max: never escalate, making everything fast and cheap. Ruled out by AD-05's recovery
bar and EV-02's per-position recall, which must pass on the same run.

**AD-05 · Escalation actually fires when needed · M · NOT TESTED**
*Statement.* The adaptive loop rescues hard queries rather than merely being cheap.
*Acceptance.* Of hard-family cases where the initial route surfaced no evidence, ≥ `[INHERITED —
EP §13.4 CG-AD: ≥80%]` are recovered by escalation, cross-checked against externally visible rounds
rather than self-reported flags alone. Fallback triggered on ≤ `[INHERITED — EP §13.4 CG-AD: ≤10%]` of
simple cases. **The escalation trigger itself is measured, not assumed:** the over-trigger and
under-trigger rates of the shipped trigger (query shape ∨ `answer_type_presence`) are published from
the trigger ablation of EP §7.4, and the composite ships only if it reduces under-escalation without
breaching the F12 over-escalation ceiling or PERF-01. An unmeasured trigger hypothesis on the default
path is a FAIL of this criterion (CONS-016; architecture T-RC2).
*Verify.* R-RETR joins trace fields to harness-observed rounds (OBS-04); the trigger-ablation table
(EP §7.4) is in the experiment log.
*Guard.* Dumbest max: escalate on everything, guaranteeing recovery. Ruled out by the paired
simple-family fallback ceiling in the same acceptance condition and by AD-04.

---

## 7. Router recoverability — contract C-08, invariant I-4

**ROUTE-01 · No bare empty response · M · NOT TESTED**
*Statement.* A no-evidence outcome is a structured report, never an empty set or a nonexistence claim.
*Acceptance.* 100% of zero-evidence responses carry: queries executed, constraints dropped with
reasons, per-rung hit counts, what was not tried, and affordances. Bare empty responses: **0**.
*Verify.* R-RETR over the unanswerable-control family and forced-failure cases.
*Guard.* Dumbest max: return a report that is always the same boilerplate. Ruled out by ROUTE-04's
requirement that the report's diagnosis be case-specific and correct.

**ROUTE-02 · Mis-parse recovery · M · NOT TESTED**
*Statement.* A wrong first route does not cause a false negative.
*Acceptance.* On adversarial mis-parse cases (wrong sender guess, wrong date window, wrong operator
class), evidence is recovered within budget in ≥ `[UNSET — register at G0 per EP §13.2 against the
G0-measured cheap-path recovery distribution; the CG-AD ≥80% recovery figure is the starting proposal]`
of cases;
false-not-found on those cases = **0**.
*Verify.* R-RETR with a dedicated mis-parse case set built by the reviewer, not the implementer.
*Guard.* Dumbest max: ignore the parse and always run the broadest query. Ruled out by AD-04's
simple-family cost ceiling and LEX-02's coverage reporting.

**ROUTE-03 · Relaxation is systematic and enumerable · M · NOT TESTED**
*Statement.* Constraint relaxation is dumb, ordered, and logged — which is what makes it recoverable.
*Acceptance.* Relaxation drops one constraint at a time in a documented order; every step is logged
with the constraint dropped and the resulting hit count; the sequence is reproducible for the same
input.
*Verify.* R-ARCH code read + R-RETR replay of a relaxation trace.
*Guard.* Not metric-based.

**ROUTE-04 · Empty-result diagnosis · M · NOT TESTED**
*Statement.* "Not found" is always qualified by what was searched.
*Acceptance.* On zero-hit outcomes where dropping exactly one constraint restores results **and that
drop was among the drops actually probed**, the report names that constraint and the count it restores;
correctness over probed drops on constructed cases = **100%**. Where the probe budget ran out before all
single-constraint drops were tried, `empty_diagnosis.status` is `incomplete`, `untried_drops` is complete
and the response `outcome` is `inconclusive` (ARCH D.2). Incomplete-diagnosis rate ≤ `[UNSET — register
at G0 per EP §13.2 against the G0-measured constraint-count distribution]` (EP §13.4 CG-AD).
*Verify.* R-RETR against constructed cases whose restoring constraint is known.
*Guard.* Dumbest max: always claim the date filter is at fault. Ruled out by the 100% correctness
requirement across constructed cases that vary which constraint is responsible.
*Decided — `docs/OWNER_DECISIONS.md` **OD-2**: the promise is over what was actually probed, and the
shortfall is disclosed.* With `k` parsed constraints and a probe budget `b`, correct
diagnosis over *untried* drops is unreachable for `k > b` at any budget short of `k`, and an unbounded
probe budget is a quota decision (ARCHITECTURE §H-7, ADV-105). The architecture has built
`max_relax_probes = min(k, 6)` and a third `empty_diagnosis` state
(`{"status":"incomplete", tried, untried_drops, affordance}`) distinct from `null` ("no single drop
restores results"), so the shortfall is **disclosed** rather than mis-stated. OD-2 selects the first of
the two honest forms — 100 % **over the drops actually attempted** plus a registered ceiling on the
incomplete-diagnosis rate — so EP §4's constructed relaxation cases stay **uncapped**.

---

## 8. Progressive disclosure — contract C-06

**DISC-01 · Output is conditioned on the query · M · NOT TESTED**
*Statement.* Two materially different queries against the same thread produce different
representations.
*Acceptance.* For a fixed thread and a set of ≥5 differing queries, the included message sets differ
in ≥ `[UNSET — register at G0 per EP §13.2 against the G0-measured Baseline F(±2) included-set
distribution on the same threads]` of pairs, and each inclusion carries a query-specific reason.
Identical output for materially different queries: flagged and investigated.
*Verify.* R-DISC on constructed multi-query thread cases, **and on family F17 (decision-reversal,
EP §4.7)** — the only test of the non-negotiable E2 reply-chain floor, which exists precisely because
query-scored selection can hide the message that reverses the answer (T-CD2; CONS-007).
*Guard.* Dumbest max: vary output randomly. Ruled out by requiring each inclusion's reason to name a
mechanism traceable to the query, and by EV-02 recall holding across all those queries.

**DISC-02 · Query-aware policy vs fixed window at equal budget · M · NOT TESTED**
*Statement.* The shipped **query-aware** policy is measured against the fixed ±2 baseline (Baseline F,
EP §8.8) at equal token budget, and the result is published either way (SC §6).
*Acceptance.* Both arms run on the same corpus instance under the same total token budget — asserted
by the harness from measured tokens, not from configuration — and the comparison table (strict case
accuracy on split-evidence and interleaved-subthread cases, tokens, rounds, over ≥3 matched budget
levels as a budget–recall curve, EP §7.2) is in the experiment log. **A loss is a reported finding and
a tuning input for the query-aware policy, not a scope reduction: fixed ±2 remains a baseline only and
may never ship as the disclosure policy** (SC §6; contract C-06 "the shipped policy MUST be
query-aware"; CD addendum §1 marks the ship-the-simpler-policy clause "genuinely invalidated as a
scope decision"). On a loss, EP §8.7's pre-committed narrowing rule applies to the **claim**, and
Baseline F(±2) stays a permanent harness fixture (PROC-04).
*Verify.* R-DISC; arms are permanent harness fixtures. (The former acceptance — "…or the loss is
documented and the simpler policy ships", with a CTX §55 citation — asserted the opposite of the
authority it cited, and was internally inconsistent with DISC-01, which a fixed ±2 policy fails by
construction. CTX §55 is about *adding* features, not about deleting contracted ones, so the citation
is dropped: CONS-001, ARCHITECTURE §H-1.)
*Guard.* Dumbest max: give the query-aware arm a larger budget. Ruled out by the equal-budget
requirement, asserted by the harness from measured tokens rather than configuration.

**DISC-03 · Depth vocabulary and declared reductions · M · NOT TESTED**
*Statement.* Every message declares its disclosure depth, and every content reduction is declared in
place with a path to the unabridged form.
*Acceptance.* 100% of disclosed messages carry a depth value from the closed set
`stub` / `snippet` / `body_clean` / `body_full` / `raw` (contract R-04); every
quote-stripped, HTML-converted or truncated body carries a size count of what was removed and an
executable full-content affordance (contract R-04; CD §5.4). Silent reductions: **0**.
*Verify.* R-DISC schema sweep plus a diff check against `format=raw` for a sample of messages.
*Guard.* Dumbest max: never strip anything, so nothing needs declaring. Ruled out by DISC-04's token
ceiling, which is unreachable without stripping.

**DISC-04 · Context efficiency against full dump · M · NOT TESTED**
*Statement.* MailWeave answers with materially fewer irrelevant tokens than a full-thread dump.
*Acceptance.* On buried-evidence threads: median disclosed content tokens ≤ `[INHERITED — EP §13.4
CG-PD: ≤30% of Baseline B]` and median relevant-token fraction ≥ `[INHERITED — EP §13.4 CG-PD: ≥3×
Baseline B's]`, computed with a pinned tokenizer over the whole transcript including follow-up rounds.
The ceiling is a **budget**, not a licence to drop: a hit excluded to stay under it becomes a
`withheld` record (EV-01), never a silent omission.
*Verify.* R-PERF + R-DISC on interleaved paired runs.
*Guard.* Dumbest max: return stubs only and disclose nothing (tokens → minimal). Ruled out by
requiring EV-02 and EV-06 recall bars — measured at body depth within the round budget — on the same
run; stub-only surfacing counts as `surfaced_not_disclosed`, not recall (EP §6.1).

**DISC-05 · Disclosure depth is justified by measurement · C · NOT TESTED**
*Trigger.* Fires if the shipped design exposes more than one disclosure level beyond the evidence
response plus a full-fetch escape hatch.
*Statement.* Extra disclosure depth is benchmarked, not assumed, because controlled evidence says a
second routing level "never helps and sometimes breaks accuracy" (VR §8.1).
*Acceptance.* An experiment log entry compares depth *n* against depth *n−1* on the same cases, same
budget, and shows a measured win; otherwise the deeper level is removed. Concretely, the comparison is
**EP §7.5.1's large-thread depth arm**: threads at and above the measured flat-map token boundary
(PF-6), run twice — flat map + declared truncation + affordance (depth *n−1*) versus segment map
(depth *n*) — reporting strict case accuracy, rounds, tokens and `levels_traversed_to_answer`
(EP §6.4). The comparison is published whichever way it comes out.
*Scope of the trigger.* The architecture declares the trigger **met by design** (§H-3: the segment map
for very long threads), so this criterion is live, not hypothetical. Separately-requestable `snippet`
and `raw` views are additional levels under this criterion's plain wording. **Resolved in the
measure-don't-remove direction (Round-1 reconciliation), and no longer an owner item:** `raw` is
already not independently requestable (ARCH D.1, ADV-208); `snippet` **stays** and the depth
measurement **is extended to the content-depth vocabulary**, `levels_traversed_to_answer` instrumenting
`stub → snippet → body_clean → body_full` as well as the segment map (EP §6.4, §7.5.1; ARCH §H-3). The
other branch — dropping a shipped level — is a scope reduction no agent may make (SC §1, §6), whereas
extending the measurement adds an obligation and weakens nothing. Any level that does not win at
matched budget is removed under ARCH E.2, which is this criterion's own remedy.
*Verify.* R-DISC against EP §7.5.1's depth arm and EP §13.4 CG-PD's depth-comparison line; adversarial
reviewer at the gate. `NOT TESTED` here blocks release exactly like FAIL (PROC-01) — which is why the
measurement, not a waiver, was added (CONS-006).
*Guard.* Dumbest max: add levels because they look sophisticated. Ruled out by requiring the
comparison to exist before the level ships.

**DISC-06 · Self-truncation before host truncation · M · NOT TESTED**
*Statement.* MailWeave is the author of its own truncation.
*Acceptance.* A hard per-response size ceiling is enforced; a response that would exceed it is
truncated by MailWeave with explicit markers and affordances. Responses truncated by the host in the
interop test (MCP-07): **0** `[DEFINITIONAL]`. The server additionally enforces a **documented
request-rate limit** — the MCP spec's "servers MUST rate limit" obligation (SN §10 P4) — and the limit
and its behaviour on breach are documented (CONS-038).
*Verify.* R-MCP with an oversized-thread case against a real client; R-ARCH reads the ceiling
enforcement.
*Guard.* Dumbest max: set the ceiling so low that nothing useful is ever returned. Ruled out by
EV-02/EV-06 recall bars on the same configuration.

---

## 9. Explicit partiality — contract C-07, invariant I-2

**PART-01 · Stated total present and correct · M · NOT TESTED**
*Statement.* Every thread representation states how many messages the thread contains.
*Acceptance.* `stated_total` is extractable on **100%** of thread-bearing responses `[DEFINITIONAL]`
and equals **what the source reported at `fetched_at`** on **100%** of cases `[DEFINITIONAL]` — never
a claim of absolute completeness, and never a count inferred from a second call and presented as the
source's report (that inference is itself a T-3 violation). The **measured discrepancy between
source-reported totals and manifest truth is a property of the instrument, not of the server**: it is
published under GMAIL-03 per PF-1, and the residual disagreement rate must stay ≤ `[UNSET — register
at G0 per EP §13.2 from PF-1's measured `|threads.get count − manifest length| / manifest length`
distribution]`, which is **gate-binding under GMAIL-03**, not merely published (ARCH_REVIEW ADV-209).
*Rationale for the rewrite.* Gmail has no thread operator and no thread message-count field, and
`threads.get` truncation on long threads is reported (VR §6.1, #239). MailWeave's only source for the
number is the instrument the old wording scored it against, so "equals manifest truth on ≥0.98" was
unsatisfiable by any conforming implementation and the honest response would have failed it
(CONS-004; ARCHITECTURE §H-2). The manifest-equality assertion is not weakened — it is **moved to
GMAIL-03**, where it measures the instrument, and given a bar that can fail.
*Verify.* R-DISC via the frozen extraction adapter (EP §6.2 P1/P1a; the adapter's `claimed_total` is
the response's `stated_total`, one quantity), reviewed at gate time; R-GMAIL supplies the GMAIL-03
discrepancy row.
*Guard.* Dumbest max: hardcode a plausible constant or echo the included count. Ruled out by O2 on
real threads (`stated_total` vs `threads.get(format=metadata)` message count, EP §2.4.5), by GMAIL-03's
gate-binding discrepancy bound against manifest truth on the seeded corpus, and by PART-02's
included-set assertion, which a constant cannot satisfy across threads of varying length.

**PART-02 · Included set matches the payload · M · PASS**
*Statement.* The response's own account of what it contains is accurate.
*Acceptance.* Extracted `included` set == the set of messages actually present in the payload, on
**100%** of responses `[DEFINITIONAL]` (EP §6.2 P2). This is a mechanical self-consistency assertion,
not a statistical one, so the bar is 1.00 and EP's CG-PD bar was **raised** to match rather than this
one lowered (CONS-011).
*Verify.* R-DISC mechanical assertion.
*Guard.* Not metric-based.

**PART-03 · More-available signalled iff partial · M · PASS**
*Statement.* Partiality is announced when true and not claimed when false.
*Acceptance.* If included < total, a machine-actionable affordance is present; if included == total,
the response declares completeness and offers no phantom remainder. Both directions asserted; failure
rate 0 on the complete-thread direction `[DEFINITIONAL]` (EP §6.2 P3; CG-PD raised to 1.00 to match,
CONS-011).
*Verify.* R-DISC over cases constructed to be both partial and complete.
*Guard.* Dumbest max: emit `"complete": false` and a generic affordance on every response. Ruled out
by the complete-direction assertion and by PART-01's exact totals.

**PART-04 · Affordances are executable · M · NOT TESTED**
*Statement.* Every "get more" path actually works and returns what it names.
*Acceptance.* A scripted driver invokes every advertised affordance in a full suite run; each returns
the content it described, through ordinary tool calls, in a client with no resource support. Failed or
mismatched affordances: **0**.
*Verify.* R-MCP + R-DISC via the P-follow driver policy (EP §10.1), cross-checked against oracle O3
(reachability) on real threads.
*Guard.* Dumbest max: advertise affordances that are never exercised in testing. This criterion is
that guard; it must run on every gate.

**PART-05 · Unexpanded content is visible as stubs · M · NOT TESTED**
*Statement.* Withheld content is a shape, not a number.
*Acceptance.* Wherever a thread map is present, every message of that thread appears as at least a
stub row with position, sender, date and reply parent; collapsed stub runs are themselves declared
with an expansion affordance. Bare "N omitted" with no per-message index: **0** occurrences where a
map is claimed.
*Verify.* R-DISC assertion; R-RETR confirms the split-evidence case is solvable by the agent aiming at
a stub.
*Guard.* Dumbest max: emit a map so large it dominates the budget. Ruled out by DISC-04's token
ceiling, which counts map tokens.

**PART-06 · Partiality survives into agent understanding · M · NOT TESTED**
*Statement.* The metadata is not merely present; an agent reading the response can state it.
*Acceptance.* In agent-in-the-loop runs, the scripted follow-up ("how many messages does that thread
contain in total, and how many did you actually see?") yields both numbers correctly or an explicit
"unknown" in ≥ `[INHERITED — EP §13.4 CG-PD: ≥0.9]` of cases; confidently-wrong or
claims-completeness-while-partial answers are failures (EP §6.2).
*Verify.* R-DISC with a pinned agent model, system identity blinded.
*Guard.* Dumbest max: make the agent always say "unknown". Ruled out by scoring "unknown" as a pass
only when the response genuinely lacks the data — which PART-01/PART-03 forbid — so persistent
unknowns imply a PART-01 failure.

**PART-07 · Role and reason on every message · M · NOT TESTED**
*Statement.* Every message MailWeave discloses says what it is and why it is there. Two of the six
fields of the contract's minimum conformance set (§5.3) had no criterion at all until this one
(CONS-008).
*Acceptance.* 100% of messages in every response carry (a) a `role` from the **closed seven-value set**
`{matched, context, parent, child, requested, stub, derived}` (contract R-02) and (b) a **non-empty
mechanical `reason`** naming the mechanism that put it there — "gmail q matched", "rfc822msgid",
"reply parent of m37", "window ±1", "snippet contains 'october'", "semantic cosine 0.81, model
potion-retrieval-32M@<rev>" (contract R-03; CTX §20). Violations: **0** `[DEFINITIONAL]`. A role
outside the closed set, an empty reason, or a decorative rationale ("relevant", "you may find this
useful") each count as a violation. Scored across all seven role values, not a three-value subset.
*Verify.* R-DISC schema sweep over the full suite (EP §6.2 P4, widened from three values to the
contract's seven, plus P6's selection provenance); R-MCP confirms structured/text parity carries both
fields (MCP-03).
*Guard.* Dumbest max: emit a constant role and a constant reason on every message, which passes a
presence check trivially. Ruled out by DISC-01's requirement that each inclusion's reason be
query-traceable to a mechanism, by RANK-03's no-fabrication rule (a number without a method is a
violation), and by SEM-06, which requires the reason to name the *actual* selection method and forbids
a semantically-selected message from being labelled a Gmail search hit.

---

## 10. MCP correctness — contract §5.4

**MCP-01 · Spec-revision conformance; no Sampling · M · NOT TESTED**
*Statement.* The server conforms to the targeted MCP revision and builds nothing on the deprecated Sampling mechanism.
*Acceptance.* The server declares and conforms to MCP revision 2026-07-28; grep confirms no
`sampling/createMessage` usage anywhere; no capability depends on client-side model borrowing
(RT §4.1b; VR §7).
*Verify.* R-MCP protocol conformance run + code grep.
*Guard.* Not metric-based.

**MCP-02 · Stateless server-minted handles · M · NOT TESTED**
*Statement.* Cross-call progressive-retrieval state travels as explicit server-minted handles, never hidden sessions.
*Acceptance.* All cross-call state travels as explicit handles in tool arguments; no hidden session
state; a fresh process (or a second concurrent client) can consume a handle minted earlier, or the
handle fails per MCP-06.
*Verify.* R-MCP restart/concurrency test.
*Guard.* Not metric-based.

**MCP-03 · Structured/text output parity · M · NOT TESTED**
*Statement.* The structured and text forms of the same result never disagree.
*Acceptance.* Structured content and its serialized text form carry the same totals, roles, reasons
and affordances; a diff test asserts field-level parity on every response shape.
*Verify.* R-MCP parity test.
*Guard.* Dumbest max: emit text only, or structured only. Ruled out by the parity test requiring both.

**MCP-04 · Truthful annotations · M · NOT TESTED**
*Statement.* Tool annotations describe what the server actually does.
*Acceptance.* `readOnlyHint: true` on every tool while B-01 holds, and it is *true* — confirmed by
SEC-02. No annotation overstates or understates behavior.
*Verify.* R-MCP + R-SEC jointly.
*Guard.* Not metric-based.

**MCP-05 · Tool metadata is compile-time constant · M · NOT TESTED**
*Statement.* Nothing an email author can write ever reaches the protocol surface.
*Acceptance.* Tool names, descriptions and schemas are constants; a grep gate proves no mail-derived
variable flows into tool metadata or error strings (SN §10 I2).
*Verify.* R-SEC grep gate in CI + R-ARCH read.
*Guard.* Not metric-based.

**MCP-06 · Handle invalidation fails loudly · M · NOT TESTED**
*Statement.* A stale handle errors clearly instead of silently resolving to different content.
*Acceptance.* An expired/invalid handle returns an explicit error naming a re-derivation path; it
never silently resolves to different content than it named. Test: mutate the underlying thread, then
redeem a stale handle.
*Verify.* R-MCP.
*Guard.* Dumbest max: never expire handles. Ruled out by FRESH-03's stamp requirement — a handle that
never expires must still return correctly stamped, currently-fetched content.

**MCP-07 · Real client completes the loop · M · NOT TESTED**
*Statement.* An ordinary MCP client, not only the harness driver, can drive MailWeave end to end.
*Acceptance.* At least one real MCP client (not the harness driver) completes a search → inspect map →
expand → answer loop against the live mailbox, transcript recorded (CTX §58.6).
*Verify.* R-MCP + R-GMAIL, transcript in the experiment log.
*Guard.* Not metric-based.

---

## 11. Real Gmail reliability — contract C-01, SC §13

**GMAIL-01 · Live-mailbox smoke suite · M · NOT TESTED**
*Statement.* A live-mailbox smoke suite runs every round, not only at the end.
*Acceptance.* A documented smoke suite runs against the real account each round: search, map, expand,
attachment metadata, long thread, empty result, non-ASCII subject; all green. The suite runs **under
EP §2.5's D8 wrapper**, so every oracle O1–O9 is evaluated on every response it produces and any
violation auto-opens a REALITY-FINDING (GMAIL-07 gates the oracle results themselves).
*Verify.* R-GMAIL executes it; results dated.
*Guard.* Not metric-based.

**GMAIL-02 · MIME and header reality · M · NOT TESTED**
*Statement.* Real-world MIME and header irregularities are handled without silent loss.
*Acceptance.* Real-mailbox messages with multipart alternatives, nested multiparts, RFC 2047
encoded-word headers, non-UTF-8 charsets, missing/duplicate headers, and HTML-only bodies are
represented without content loss or crash; anything undecodable is declared, not dropped.
*Verify.* R-GMAIL on a curated live sample plus sanitized fixtures.
*Guard.* Dumbest max: fall back to `raw` for anything hard, blowing the token budget. Ruled out by
DISC-04's ceiling.

**GMAIL-03 · Thread-completeness semantics validated · M · NOT TESTED**
*Statement.* Completeness claims mean only what the source can actually support.
*Acceptance.* Completeness is defined and implemented as "as reported by the source at `fetched_at`"
(contract R-08, T-3). **This criterion carries the manifest-equality assertion moved out of PART-01
(CONS-004):** a G0 validation (PF-1) compares REST `threads.get` message counts against manifest truth
on the seeded corpus across threads of varying length, publishes the discrepancy distribution, **and
the discrepancy rate `|threads.get count − manifest length| / manifest length` must stay ≤ `[UNSET —
register at G0 per EP §13.2 from PF-1's measured distribution]`**. The bound is gate-binding: above it
this criterion FAILS. "Published" is not a bar, and a criterion that cannot fail is not a criterion
(ARCH_REVIEW ADV-209).
*Verify.* R-GMAIL; result recorded even if no discrepancy is found; the registered bound must exist in
experiment log 001 before this criterion is reviewed.
*Guard.* Dumbest max: assert `complete: true` unconditionally, or define the discrepancy bound after
seeing PF-1's result. Ruled out by the registration-before-review rule (EP §13.2 step 4 makes
post-hoc amendment an escalation), by O2 on real threads, and by requiring the validation record to
exist independently of its outcome.

**GMAIL-04 · Pagination correctness · M · NOT TESTED**
*Statement.* Multi-page result sets are traversed without loss or duplication.
*Acceptance.* Result sets larger than one page are handled via `pageToken` without duplication or
loss; `resultSizeEstimate` is never used as a truth source for any count MailWeave states (RO F1).
*Verify.* R-GMAIL against a query with >`maxResults` matches; R-ARCH grep for estimate misuse.
*Guard.* Dumbest max: always fetch every page. Ruled out by AD-01's caps and PERF-01's call ceiling —
and when a cap stops paging, the **scan scope** (pages fetched, `maxResults`, whether unfetched pages
remain) must be declared per contract R-08, and any already-returned-but-undisclosed ID becomes a
`withheld` record per EV-01.

**GMAIL-05 · Quota and rate-limit behavior · M · NOT TESTED**
*Statement.* The server behaves correctly under Gmail's real quota and rate limits.
*Acceptance.* An empirical quota probe is recorded at G0 (the published unit table is internally
disputed, and the two figures in circulation are **both true and differently scoped**: RO F7's ~10×
concerns bulk-index feasibility, while RO addendum §6.9 / PF-3's ~4× concerns the semantic-pool
ceiling — so the resolution moves the semantic-pool ceiling ~4× and bulk-index feasibility ~10×,
CONS-034); the server applies
bounded retry with backoff on 429/5xx, never unbounded retry; batch sizes stay within documented
guidance (≤50 recommended, 100 hard limit — RO F5).
*Verify.* R-PERF + R-GMAIL under induced rate limiting.
*Guard.* Not metric-based.

**GMAIL-06 · Auth lifecycle exercised · M · NOT TESTED**
*Statement.* OAuth acquisition, refresh and expiry are exercised rather than assumed.
*Acceptance.* Loopback + PKCE(S256) + state flow; token refresh, expiry and re-auth paths are
exercised in a test or documented runbook, including the 7-day refresh-token expiry that applies while
the OAuth project is in Testing status (RO F8; SN §2.2). Failure is a clear re-auth instruction, never
a confusing retrieval error.
*Verify.* R-SEC + R-GMAIL.
*Guard.* Not metric-based.

**GMAIL-07 · Reality-tier oracles clean · M · NOT TESTED**
*Statement.* The reality tier — the correction's headline methodology change — is enforced at the
gate, not merely described in the evaluation plan.
*Acceptance.* The round's Tier-1 run executed protocols D1/D2/D4/D5/D8 and oracles O1–O9 against the
personal mailbox under the redacting profile; **O1, O2, O3, O5, O8 and O9 report zero unresolved
violations with denominators published**; D2 signature coverage ≥ its registered floor `[UNSET —
register at G0 per EP §13.2 from D2's measured signature-frequency distribution]`, with a
corpus-extension ticket for every uncovered signature above that floor; and every D4 `found-wrong` /
`missed-but-exists` verdict is triaged (EP §2.4.5, §2.5, §13.4 CG-REAL). Oracle counts are gate
evidence, never headline metrics (EP §2.7).
*Verify.* R-GMAIL executes the tier; R-SEC certifies O9 (the redaction canary) independently.
*Guard.* Dumbest max: run the oracles only on the seeded account, where everything is well-formed and
nothing is private. Ruled out by the personal-profile requirement here and by E2E-04, which requires
both mailbox profiles in the same gate.

---

## 12. Freshness — contract C-09

**FRESH-01 · Freshness protocol executed and published · M · NOT TESTED**
*Statement.* Freshness is measured against real delivered mail before anything is said about it.
*Acceptance.* The CG-FRESH protocol (EP §11.1) has run against real delivered mail (not inserted
fixtures) with ≥ `[INHERITED — EP §13.4 CG-FRESH: N≥30 per stratum, ≥5 calendar days, ≥3 times of
day]`, covering all arms (H0–H5: direct Gmail API, MailWeave, hosted connector where attachable) —
**per depth stratum (0 / 5 / 25), on both mailboxes**, with per-stratum ECDFs and censoring counts
published. **Pooling across strata is a failure of this criterion, not a presentation choice**
(EP §11.2.1: "pooling is exactly what would hide the effect"), and a negative result on one mailbox
licenses no freshness sentence (T-VR2). A run that pools strata or uses one mailbox does not satisfy
this criterion however large its N (CONS-012).
*Verify.* R-GMAIL; entry dated and reproducible; per-stratum tables present.
*Guard.* Dumbest max: measure on seeded inserts, which have different indexing behaviour — ruled out
by requiring real delivered mail (EP §11.1 "why not inserts"). Second guard: pool the strata and
report one flattering median, which would hide precisely the depth-specific failure the protocol
exists to find — ruled out by the per-stratum requirement above.

**FRESH-02 · Mitigation built if lag exceeds the bar · C · NOT TESTED**
*Statement.* Measured lag above the bar produces an implemented mitigation, not a future research idea.
*Trigger.* Fires if **any** of EP §11.2.3's six mitigation-forcing triggers fires — not only the 60 s
gap this criterion used to quote in isolation (CONS-010):
**MF1** any probe censored at 72 h in a depended-on arm; **MF2** p90 lag of the depended-on arm above
the FSL in **any** stratum; **MF3** depth divergence (paired depth-25 vs depth-0 lag with the 95% CI of
the difference excluding zero); **MF4** any confirmed Tier-1 D6 real-mail false negative (an O7/O1
violation on the personal mailbox); **MF5** a bimodal lag ECDF with a mode beyond the FSL;
**MF6** MailWeave's median lag exceeding direct-API lag by > 60 s `[INHERITED — EP §11.2.3 MF6]`.
Five of the six need no invented number. As previously worded, a message that never becomes findable
(MF1) or a depth-25-only failure (MF3) — the exact signature VR §1.3 reports — would not have made
this mandatory mitigation fire.
*Acceptance.* A mitigation (history-based reconciliation or another defensible mechanism) is
implemented and re-measured, and **it removes the specific trigger that fired** — censored probes now
surface; p90 ≤ FSL; the depth-divergence CI now includes zero — verified by **arm H6 on the identical
protocol, same strata, same N, same schedule** (EP §11.2.4), **without regressing AD-04 or PERF-01**.
The mitigation must do its own matching (`history.list` returns arrival events, not query matches),
carry staleness metadata on every response, ship the 404-on-expired-`historyId` full-resync path, and
add no paid or hosted dependency to the core path (contract N-01, T-4). MF6 is fixed regardless of
what the mitigation decision is.
*Verify.* R-GMAIL re-runs the identical protocol as arm H6 + R-ARCH review of the mechanism.
*Guard.* Dumbest max: full-resync on every query. Ruled out by AD-04/PERF-01 cost ceilings, which must
still pass.

**FRESH-03 · Staleness stamps everywhere · M · NOT TESTED**
*Statement.* No view of the mailbox is served without stating when it was fetched.
*Acceptance.* Every map, body and any cached artifact carries its fetch time; if any persistent store
exists, responses served from it also carry sync time and `historyId`, and a 404-on-expired-history
full-resync path exists (RO F6; SN §4.2). Unstamped served content: **0**.
*Verify.* R-DISC schema sweep; R-ARCH reads the cache path if one exists.
*Guard.* Not metric-based.

**FRESH-04 · No freshness claim without an entry · M · NOT TESTED**
*Statement.* No public sentence about freshness exists without a measurement behind it.
*Acceptance.* Grep of README and all public material finds no freshness/staleness claim unless
FRESH-01's entry exists and the claim is bounded to the measured arms and conditions (contract H-04).
*Verify.* R-ARCH + adversarial reviewer at the release gate.
*Guard.* Not metric-based.

**FRESH-05 · Freshness Service Level registered before the probe run · M · NOT TESTED**
*Statement.* The threshold several freshness triggers depend on is a product decision, made and
recorded before the measurement that would be judged against it.
*Acceptance.* The **FSL** — a lag bound, the arm it applies to, and the depth strata it applies to —
is written by the owner into experiment log 001 **before the FRESH-01 probe run starts**, and frozen
thereafter (amendable only via EP §13.2's logged-amendment procedure, which retains the original
value; amendment after seeing the result it would change is an escalation under `AGENT_LOOP.md` §8).
EP §11.2.2 makes this blocking and no criterion carried it (CONS-010). This criterion is `PASS` only
on the existence and timestamp of that entry; the *value* is the owner's, and nothing in this rubric
proposes one.
*Verify.* R-GMAIL + orchestrator check the log entry's timestamp against the probe run's start.
*Guard.* Dumbest max: set the FSL after the data is in, at whatever value the data clears. Ruled out
by the timestamp check and by the amendment procedure's escalation rule.

**FRESH-06 · Temporal partiality field · M · NOT TESTED**
*Statement.* A result that depends on the search index says so, whatever the freshness numbers turned
out to be.
*Acceptance.* When a result depends on the search index, the response says so in a machine-readable
field, in **100%** of such cases `[DEFINITIONAL]` — **whatever the freshness measurement showed**
(EP §6.4 P7; CG-FRESH requires it "present and correct in all cases"). A measured median is a sample,
not a per-query guarantee, so a good freshness result does not retire this field. Honest degradation is
a product property, not a consolation prize for bad numbers (EP §11.2.5). This is the P7 assertion,
which the gate required and no criterion carried (CONS-013).
*Verify.* R-DISC schema sweep over the full suite; R-GMAIL confirms the field is set on
index-dependent paths and unset on index-independent ones (`rfc822msgid:` direct fetch).
*Guard.* Dumbest max: set the flag on every response, making it uninformative. Ruled out by requiring
it to be *correct*, not merely present: index-independent retrieval paths must not carry it.

---

## 13. Performance — invariant I-3

**PERF-01 · Simple-family latency ceiling · M · NOT TESTED**
*Statement.* Simple queries are not materially slower than the primitive baseline they replace.
*Acceptance.* p50 and p95 latency on simple families within `[INHERITED — EP §13.4 CG-AD: p50 ≤1.25×
Baseline D]`, measured at the MCP client boundary, interleaved round-robin with baselines, cold and
warm reported separately (EP §8.6).
*Verify.* R-PERF.
*Guard.* Dumbest max: skip escalation to win latency. Ruled out by AD-05 and EV-02 passing on the same
run.

**PERF-02 · Network-level API call accounting · M · NOT TESTED**
*Statement.* Retrieval cost is measured externally, not self-declared.
*Acceptance.* Gmail API calls are counted at the network level by the harness, not from server
self-reports; per-family call counts published.
*Verify.* R-PERF via the counting proxy (EP §6.1).
*Guard.* Dumbest max: report favorable self-counts. This criterion is that guard; OBS-04 pairs with it.

**PERF-03 · No cross-round performance regression · M · NOT TESTED**
*Statement.* Performance does not silently decay between rounds.
*Acceptance.* No family's p95 latency or median call count regresses by more than `[INHERITED —
EP §13.4 CG-AD: >20%]` versus the previous gate run, or the regression is explained and accepted in
the ledger.
*Verify.* R-PERF against the retained history of gate runs.
*Guard.* Not metric-based.

**PERF-04 · Cost tracks ambiguity · M · NOT TESTED**
*Statement.* Retrieval cost varies with query difficulty instead of being uniform.
*Acceptance.* Per-case cost (calls, latency, model/embedding invocations) correlates with recorded
ambiguity signals rather than being uniform: the simple-family and hard-family cost distributions are
separated, and the separation is reported with CIs.
*Verify.* R-PERF + R-RETR jointly.
*Guard.* Dumbest max: uniform cheap pipeline (fails AD-05) or uniform expensive pipeline (fails
AD-04). Both are excluded by requiring AD-04 and AD-05 to pass together.

---

## 14. OAuth, security and privacy — contract N-04, N-05, B-01

**SEC-01 · Exactly one Gmail scope · M · NOT TESTED**
*Statement.* The server holds the minimum viable Gmail scope and nothing else.
*Acceptance.* The server requests exactly `gmail.readonly`; a CI string-search gate finds no other
`googleapis.com/auth/` scope literal in server code (SN §10 S1).
*Verify.* R-SEC; gate must be in CI, not run by hand.
*Guard.* Not metric-based.

**SEC-02 · No write path reachable from any tool · M · NOT TESTED**
*Statement.* The read-only posture is structural, not a matter of which tools happen to be listed.
*Acceptance.* No send/draft/modify/label/trash/delete call exists in the server's reachable call
graph; proven by call-graph analysis or an equivalent structural check, not by reading the tool list
(SN §10 S2). **And no attachment-content extraction path is reachable from any tool**: attachments are
metadata-only by default, and any extraction path, if ever built, is sandboxed, size- and depth-capped
and opt-in (contract B-04; SN §7.3) — previously mentioned only inside GMAIL-01/E2E-01 smoke lists and
asserted by no criterion (CONS-021).
*Verify.* R-SEC + R-ARCH.
*Guard.* Not metric-based.

**SEC-03 · Harness isolation and account pinning · M · NOT TESTED**
*Statement.* Destructive harness capability can never reach the personal mailbox.
*Acceptance.* Seeding/teardown scopes exist only in harness code, under a separate OAuth client, and
the harness aborts unless the authenticated address equals the configured seed account; a test proves
destructive calls are unreachable otherwise (Appendix A.2; SN §10 S3).
*Verify.* R-SEC executes the abort test.
*Guard.* Not metric-based.

**SEC-04 · Token storage hygiene · M · PASS**
*Statement.* Credentials are stored so that a leak requires more than reading a log.
*Acceptance.* Tokens in an OS keyring or 0600 files under 0700 directories; startup refuses
over-permissive files; no token or client secret in env vars, argv, logs, or git history; secret
scanning in CI (SN §10 T1–T2).
*Verify.* R-SEC.
*Guard.* Not metric-based.

**SEC-05 · No mail content at rest by default · M · NOT TESTED**
*Statement.* The default posture leaves no mail content on disk.
*Acceptance.* A full suite run leaves no message body, subject, or address on disk outside the
declared trace policy; if any persistent store is introduced, it ships with encryption-at-rest
posture, a purge command, and deletion tombstones (SN §4.1–4.2).
*Verify.* R-SEC via filesystem diff before/after a run.
*Guard.* Dumbest max: write nothing at all, including traces. Ruled out by OBS-01's trace
completeness requirement.

**SEC-06 · Trace redaction canary · M · NOT TESTED**
*Statement.* Personal mailbox content never reaches traces or logs, including on error paths.
*Acceptance.* A personal-profile run seeded with sentinel strings in query text and message bodies
produces traces and logs — **including error paths** — containing zero sentinels; the redaction
profile is selected from the authenticated account, not a config flag; raw query text is stored as
features or a salted hash (Appendix A.3; SN §4.3, §10 T3).
*Verify.* R-SEC runs the canary itself on a fresh run.
*Guard.* Dumbest max: disable tracing on the personal profile. Ruled out by requiring the required
trace fields of OBS-01 to be present in the same run.

**SEC-07 · No telemetry; egress is Gmail-only by default · M · NOT TESTED**
*Statement.* MailWeave reports to nobody, and it listens to nobody.
*Acceptance.* Egress capture over a full suite run in the default configuration shows connections to
**exactly two hosts — `gmail.googleapis.com` and `oauth2.googleapis.com` (token refresh only) — and no
other host** `[DEFINITIONAL]`; no analytics, no crash reporting, no update checks, no query-time model
download, and zero mailbox bytes to any non-Google host (contract N-06). Model weights are provisioned
at **setup time only** from a declared model-host, and **runtime model loading is forced offline**
(`local_files_only=True` / `HF_HUB_OFFLINE=1`) from a checksum-pinned local path — without that, the
`sentence-transformers` / `huggingface_hub` default load path issues a hub revalidation request and
this criterion fails on the default path (ARCH_REVIEW ADV-210).
**And the default configuration opens no listening socket**, asserted by a port scan of the running
server; default transport is **stdio** (contract N-07; SN §10 P1) — a contract MUST that had no
criterion at all (CONS-018).
*Rationale for the rewrite.* "Connections only to Gmail" was unsatisfiable: OAuth token refresh
contacts `oauth2.googleapis.com`, so any long-running conforming server failed this criterion as
worded, and a container built to the old EP §7.1 bar could not refresh a token or complete the suite
(CONS-002; ARCHITECTURE §H-4).
*Verify.* R-SEC via network capture in the two-host allowlisted container (EP §7.1 bar 2, S14) plus a
port scan of the running default configuration.
*Guard.* Dumbest max: widen the allowlist until nothing is blocked, or run the capture with the model
already warm so the hub request never happens. Ruled out by the exact two-host assertion and by
requiring the capture to include a **cold start** (model load) inside the allowlisted container.

**SEC-08 · No learned routing policy · M · NOT TESTED**
*Statement.* Routing is deterministic and heuristic; nothing in the server has been trained on
retrieval traces.
*Acceptance.* No model weights, training code, or learned scorer participates in **routing**: the
route/escalate/stop decisions are deterministic or heuristic functions of recorded signals, and a
learned policy would be caught before it shipped (contract B-05; SC §9, §15). Violations: **0**
`[DEFINITIONAL]`. This does **not** forbid the embedding model — semantic *retrieval* is required
capability (C-03) and its model is not a router; the boundary is that no scorer trained on MailWeave's
own traces or labels decides which rung runs. Note also the Limited Use constraint SN's addendum
records: a future learned router could only ever be trained on synthetic seed-account traces or
strictly per-user personalized data, never pooled real-mailbox content.
*Verify.* R-ARCH by code read of the routing decision path plus a CI grep gate for training/fit APIs
and checkpoint loading inside the routing module.
*Guard.* Not metric-based. (Inverse degenerate: declare the router "heuristic" while a learned scorer
supplies its threshold — ruled out by the code read of every input to the decision, and by OBS-03's
requirement that a routing decision be reconstructable from its trace alone.)

---

## 15. Prompt injection and untrusted content — contract C-11

**INJ-01 · Untrusted envelope on all mail-derived text · M · NOT TESTED**
*Statement.* Every string that came from an email arrives labeled as untrusted third-party data.
*Acceptance.* 100% of mail-derived strings (body, snippet, subject, display name, filename) are inside
nonce-delimited fences with `source`/`trust` provenance fields; the nonce is per-response and
unguessable so mail cannot close its own fence (SN §6.3).
*Verify.* R-SEC schema sweep over a full suite run including injection fixtures.
*Guard.* Dumbest max: fence the entire response including connector fields, making the output
unparseable. Ruled out by MCP-03 parity and PART-01..04 extraction, which must still succeed.

**INJ-02 · Mail text never reaches connector-voiced surfaces · M · NOT TESTED**
*Statement.* Email content can never speak in MailWeave's own voice.
*Acceptance.* No mail-derived string appears in tool names, descriptions, schemas, error messages, or
any field expressing MailWeave's own semantics (counts, roles, reasons, affordances). Occurrences: 0.
*Verify.* R-SEC grep gate (MCP-05) plus a fixture whose subject is crafted to look like connector
metadata.
*Guard.* Not metric-based.

**INJ-03 · Injection fixtures neither steer nor disappear · M · NOT TESTED**
*Statement.* Adversarial email neither steers retrieval nor gets silently suppressed.
*Acceptance.* With adversarial fixtures seeded (instructions in body, subject, display name, filename,
hidden HTML, **and the `I1-bait` class of EP §5.1 — embedding-bait and keyword-stuffing messages
crafted to score highly against many queries**): (a) routing, ranking and expansion decisions are
unchanged versus the same corpus without the injected text — compared by trace diff; (b) **the injected
message is still retrieved and disclosed when it legitimately matches the query**, fenced and labeled;
(c) a bait message does not displace true evidence from the disclosed prefix, paired against the same
corpus without it, and its selection reason and `model_id@revision` are visible (SEM-06). The bait
class is the standing consequence of putting semantic retrieval on the default path (T-SN3); it was
named in ARCHITECTURE and SECURITY_NOTES and existed in no EP fixture inventory (CONS-014).
*Verify.* R-SEC + R-RETR jointly, on a fixture set the reviewer may extend.
*Guard.* Dumbest max: filter or drop suspicious mail, which trivially prevents steering. Ruled out by
clause (b) — dropping matching evidence is an EV-01 violation and a BLOCKER.

**INJ-04 · HTML pipeline: visible text, flagged hiding, no network · M · NOT TESTED**
*Statement.* HTML becomes visible text safely, with hiding declared and no network access.
*Acceptance.* HTML bodies are converted by a maintained parser to visible text; hidden constructs
(display:none, zero-size, white-on-white, comments, zero-width characters) are removed with a
`hidden_content_removed` flag; the parser makes zero network calls, proven by running it with sockets
disabled (SN §7.1, §10 I4).
*Verify.* R-SEC.
*Guard.* Dumbest max: strip all HTML content aggressively, losing evidence. Ruled out by EV-02 recall
on HTML-bodied cases and by DISC-03's declared-reduction requirement.

**INJ-05 · Identity fields split; auth results labeled · M · NOT TESTED**
*Statement.* Sender identity is exposed in a form a display name cannot spoof.
*Acceptance.* From/To/Cc/Reply-To exposed as `{display_name, address}` pairs, never pre-joined;
`reply_to_differs` surfaced; `Authentication-Results` exposed as receiver-recorded data, never as
MailWeave's verdict (SN §7.2).
*Verify.* R-SEC with a spoofed-display-name fixture.
*Guard.* Not metric-based. (**Promoted from `O` to `M` (CONS-028):** STR-02's verification depends on
this criterion's display-name/address separation, and address-keyed participant matching is a contract
MUST (C-02b; SN §7.2). A mandatory criterion's evidence may not depend on one that never blocks.)

**INJ-06 · Internal model outputs are closed-typed · M · NOT TESTED**
*Statement.* Any internal model is quarantined behind closed output types.
*Acceptance.* If any internal model call exists, its output is validated against a closed type (enum,
ID list, numeric score, boolean) before use; free text it produces is treated as untrusted and fenced;
expansion parameters are never parsed out of mail content (SN §6.3.6).
*Verify.* R-SEC + R-ARCH.
*Guard.* Not metric-based. (Vacuously satisfied if no internal model call exists — reviewer records
which.)

---

## 16. Observability — contract C-10

**OBS-01 · Trace schema completeness · M · NOT TESTED**
*Statement.* Every top-level query leaves a complete, schema-valid trace.
*Acceptance.* Every top-level query emits one trace containing all required fields of contract C-10;
missing-field rate over a full suite run: **0**. Schema is versioned.
*Verify.* R-ARCH validates traces against the schema.
*Guard.* Dumbest max: log everything verbatim including bodies. Ruled out by SEC-06.

**OBS-02 · Headline metrics come from harness measurement · M · NOT TESTED**
*Statement.* Published numbers come from measurement, not from the server's account of itself.
*Acceptance.* Every headline number in the experiment log and public material derives from
harness-measured or manifest-scored fields; server self-reported fields appear only labeled as
diagnostics (EP §6.3).
*Verify.* R-PERF + adversarial reviewer trace the provenance of each published number.
*Guard.* Not metric-based.

**OBS-03 · Traces support post-hoc replay · O · NOT TESTED**
*Statement.* A past routing decision can be reconstructed from its trace alone.
*Acceptance.* A routing decision can be reconstructed from its trace alone, without re-running against
Gmail: rungs, signals, thresholds and the branch taken are all recoverable.
*Verify.* R-ARCH replays 5 random traces and 100% of failure traces.
*Guard.* Not metric-based.

**OBS-04 · Self-reported counters cross-check · M · NOT TESTED**
*Statement.* The server's own counters are checked against reality.
*Acceptance.* Server-reported Gmail call counts agree with network-level counts within `[UNSET —
register at G0 per EP §13.2 against the G0-measured retry-behaviour distribution at the counting
proxy]`; persistent mismatch is a finding, not a rounding note.
*Verify.* R-PERF.
*Guard.* This criterion is the guard for AD-05 and PERF-02, which otherwise could be satisfied by
optimistic self-reporting.

---

## 17. Non-functional — contract §6

**NFR-01 · Full suite passes with no paid API key · M · PASS**
*Statement.* Core MailWeave works with no paid API dependency at all.
*Acceptance.* With no provider keys configured, the entire mandatory rubric run completes and every
capability of contract §3 is exercised — including the semantic rung (Appendix A.1).
*Verify.* R-ARCH + R-RETR run the gate in key-free configuration; this is the *default* gate
configuration, not a variant.
*Guard.* Dumbest max: mark the semantic rung "unavailable" in key-free mode. Ruled out by SEM-01's
paraphrase bar being measured in this configuration (SEM-02).

**NFR-02 · Local operation footprint documented · M · NOT TESTED**
*Statement.* The cost of running MailWeave locally is measured and documented.
*Acceptance.* Install size, model download (if any), memory and cold-start cost of the local semantic
path are measured and documented; the server runs with outbound access restricted to Gmail.
*Verify.* R-PERF measures; R-ARCH checks the doc matches.
*Guard.* Not metric-based.

**NFR-03 · Gmail remains the source of truth · M · NOT TESTED**
*Statement.* Local state never becomes an unacknowledged second source of truth.
*Acceptance.* No response is served solely from local state without a staleness stamp (FRESH-03); no
persistent mail index exists unless a logged measured failure justified it (SC §11; contract N-03).
*Verify.* R-ARCH.
*Guard.* Not metric-based.

**NFR-04 · Clean-machine reproducible setup · M · PASS**
*Statement.* A reviewer can stand the system up from the documentation alone.
*Acceptance.* A reviewer follows the documented setup on a clean environment and reaches a working
server plus a green offline test suite; dependencies pinned.
*Verify.* R-ARCH performs the install itself.
*Guard.* Not metric-based.

---

## 18. Regression tests — AGENT_LOOP §7.2, §9

**REG-01 · Every real failure yields a regression test · M · NOT TESTED**
*Statement.* Every real failure that gets fixed becomes a test that would catch it again.
*Acceptance.* Every closed BLOCKER/HIGH finding has a named regression test derived from the actual
failure, with a sanitized deterministic fixture where the failure came from real mail (SC §13).
Findings closed without one: **0**.
*Verify.* R-ARCH cross-checks the findings ledger against the test suite.
*Guard.* Not metric-based.

**REG-02 · Regression tests fail against the pre-fix commit · M · NOT TESTED**
*Statement.* A regression test that cannot fail is not a regression test.
*Acceptance.* Each regression test is demonstrated to **fail** when run against the commit prior to
its fix (or an equivalent injected-defect harness). A test that passes both before and after does not
count.
*Verify.* R-ARCH executes the check for a reviewer-chosen sample plus all tests added this round.
*Guard.* Dumbest max: write tests that assert tautologies to raise coverage. This criterion is that
guard; REG-03 covers the complementary case.

**REG-03 · No benchmark special-casing in tests or code · M · NOT TESTED**
*Statement.* Neither code nor tests are tuned to the benchmark's surface forms.
*Acceptance.* Diff audit and grep sweep find no hardcoded benchmark message IDs, case IDs, persona or
subject literals, template tokens, branches keyed on thread length 100 or on the sweep positions, or
special-cased query strings (EP §9 G6).
*Verify.* R-ARCH + adversarial reviewer on every round's diff.
*Guard.* Not metric-based.

**REG-04 · Fixtures sanitized; suite runs offline · M · PASS**
*Statement.* Committed test material contains no personal mail and needs no credentials.
*Acceptance.* Committed fixtures contain no personal email content (Appendix A.3); the non-E2E suite
runs with no Gmail credentials and no network.
*Verify.* R-SEC reviews fixtures; R-ARCH runs the suite offline.
*Guard.* Not metric-based.

---

## 19. Real-Gmail end-to-end testing — SC §13, §17

**E2E-01 · Required real-Gmail E2E set is green · M · NOT TESTED**
*Statement.* The named real-Gmail end-to-end set passes against the live account at every gate.
*Acceptance.* The named E2E set (search→map→expand→answer on a long live thread; exact-ID retrieval;
zero-hit report; attachment metadata; recency query; oversized-thread self-truncation) passes against
the live account at the gate, with transcripts retained.
*Verify.* R-GMAIL executes; not accepted from the implementer's log (AGENT_LOOP §7.1).
*Guard.* Not metric-based.

**E2E-02 · Corpus regenerated from a fresh seed each gate · M · NOT TESTED**
*Statement.* Each gate runs on a corpus the implementation has never seen.
*Acceptance.* The seeded corpus is regenerated per gate with redrawn evidence positions, re-realized
paraphrase surfaces and re-randomized names/dates/tokens; the generator version and seed are in the
run header (EP §9 G3).
*Verify.* R-GMAIL + orchestrator.
*Guard.* Dumbest max: cache Gmail message IDs or memorize positions. Ruled out by regeneration, which
makes memorization worthless by construction.

**E2E-03 · Reviewer-selected held-out seed · M · NOT TESTED**
*Statement.* The reviewer, not the implementer, chooses the seed that claims are made on.
*Acceptance.* Gate claims come only from full-profile runs on HOLDOUT seeds the implementer never ran,
chosen by the reviewer; two fresh seeds agree within CI or a third is run and the variance
investigated (EP §9 G4–G5, §13.1).
*Verify.* R-GMAIL/R-RETR; seed choice recorded.
*Guard.* Not metric-based.

**E2E-04 · Both mailbox profiles exercised · M · NOT TESTED**
*Statement.* Both the measurement mailbox and the real personal mailbox are exercised.
*Acceptance.* Each gate exercises the seeded ground-truth account (measurement) *and* the personal
mailbox read-only (realism: real MIME, real wording, real thread depth), with the personal run under
the redacting trace profile (SC §13; Appendix A.3).
*Verify.* R-GMAIL.
*Guard.* Dumbest max: run only the seeded corpus, where everything is well-formed. Ruled out by
requiring the personal-mailbox run and by GMAIL-02's reality cases.

---

## 20. Documentation accuracy — contract §8

**DOC-01 · Every claim maps to a measurement · M · NOT TESTED**
*Statement.* Nothing is claimed publicly that was not measured.
*Acceptance.* A claim→measurement table exists; every capability or performance sentence in the README
and any public post maps to an experiment log entry containing the number; unmapped claims: **0**. An
overstated claim is a BLOCKER at the gate (AGENT_LOOP §7.7). **And every rejected capability has a
published negative result with its numbers**, given the same experiment-log treatment as a win and
kept in the index permanently (contract H-07) — enforced until now only for the semantic path, by
SEM-05 (CONS-021).
*Verify.* **R-DOC** (documentation and claim accuracy) + R-ARCH in the ordinary round, with the
adversarial reviewer re-checking at the gate (CONS-019).
*Guard.* Dumbest max: delete all claims so none can be overstated. Ruled out by DOC-02/DOC-03, which
require the problem statement, the measured results and the limitations to be present.

**DOC-02 · Problems stated unbundled · M · NOT TESTED**
*Statement.* The three problems are never allowed to borrow each other's evidence.
*Acceptance.* Public material states separately which of representation omission, freshness, and
semantic retrieval is solved, with each backed only by its own evidence (contract H-02; CTX §58.7).
*Verify.* **R-DOC** in the ordinary round; adversarial reviewer at the gate (CONS-019).
*Guard.* Not metric-based.

**DOC-03 · Limitations and not-measured section · M · NOT TESTED**
*Statement.* What was not measured is stated as plainly as what was.
*Acceptance.* Public material names what was not measured, what remains untested, the baselines it was
compared against — including the strong-agent-with-primitives comparison (contract H-06) — and the
domain-transfer limits of cited prior art.
*Verify.* **R-DOC** in the ordinary round; adversarial reviewer at the gate (CONS-019).
*Guard.* Not metric-based.

**DOC-04 · Prior art cited honestly · M · NOT TESTED**
*Statement.* Prior art and third-party evidence are cited and labeled honestly.
*Acceptance.* Cites the vendor tool-description acknowledgment and the public issues as provenance
(labeled as third-party evidence, not our measurement), arXiv 2607.17598, the routing baseline study,
Anthropic's context-engineering guidance, and the existing Gmail MCP servers including the archived
most-popular one (VR §8, §11; contract H-05).
*Verify.* **R-DOC** in the ordinary round; adversarial reviewer at the gate (CONS-019).
*Guard.* Not metric-based.

**DOC-05 · Read-only wording and untrusted-content disclosure · M · NOT TESTED**
*Statement.* Read-only is described as this release's intent, and untrusted content is disclosed.
*Acceptance.* Documentation states "the first MailWeave retrieval release is intentionally read-only"
(SC §10) — never framing MailWeave as permanently incapable of Gmail actions — and plainly discloses
that output carries untrusted third-party content that hosts should gate consequential actions against
(SN §10 P3), plus the no-telemetry statement — which must state the **two-host** runtime egress
posture accurately (SEC-07), not "Gmail only".
*Verify.* R-SEC + **R-DOC**; adversarial reviewer at the gate.
*Guard.* Not metric-based.

**DOC-06 · §58 minimum-proof bundle complete before the headline claim · M · NOT TESTED**
*Statement.* The sentence "MailWeave fixes the Gmail MCP problem" is gated on a complete bundle, not on
a majority of it.
*Acceptance.* Before that claim (or any equivalent) appears in public material, **all seven** CTX §58
items exist as experiment-log entries: a faithful reproduction or labelled reconstruction of the
reported failure; buried-evidence tests; evidence-preservation results; comparison against full-thread
and fixed-K baselines; latency and context-size measurements; a real MCP client successfully using
MailWeave; and an explicit statement of which problem is solved. The **claim→item map is published**,
and a missing item blocks the claim, not the release of the rest (contract H-03). The parts were
covered piecewise by EV-05, EV-02, EV-06, PROC-04, PERF-01/02, MCP-07 and DOC-02; nothing asserted the
bundle was complete (CONS-021).
*Verify.* **R-DOC** assembles the map from the experiment log; adversarial reviewer re-derives it
independently at the gate.
*Guard.* Dumbest max: make the claim vaguer until no single item is missing for it. Ruled out by
DOC-02's unbundling requirement — a vaguer claim that spans problems is a DOC-02 failure — and by
DOC-03's limitations section, which must name what was not measured.

---

## 21. Process and anti-gaming integrity — AGENT_LOOP §3, §7

**PROC-01 · NOT TESTED blocks release · M · NOT TESTED**
*Statement.* An untested criterion is treated exactly like a failed one.
*Acceptance.* At the release gate, zero criteria are `NOT TESTED`; no criterion has ever been presented
as a soft pass; every status transition records round and reviewer ID (AGENT_LOOP §6).
*Verify.* **Adversarial reviewer**, from the records in `docs/reviews/`; the orchestrator supplies the
audit trail but does **not** set this status — it is the agent that maintains the status table, and
"no agent may certify its own work" (AGENT_LOOP §1) applies to process criteria too (CONS-019b,
CONS-032).
*Guard.* Dumbest max: delete inconvenient criteria. Ruled out by PROC-06 and by this rubric's criterion
IDs being stable and append-only.

**PROC-02 · No criterion certified by its implementer · M · NOT TESTED**
*Statement.* No agent certifies its own work.
*Acceptance.* Every `PASS` traces to a reviewer report from an agent that did not write the code, with
an execution record; reviewer instances are fresh per round (AGENT_LOOP §1, §3).
*Verify.* **Adversarial reviewer**, from the records in `docs/reviews/`; the orchestrator supplies the
audit trail but does not set the status (CONS-019b, CONS-032).
*Guard.* Not metric-based.

**PROC-03 · Ground truth unreadable by the server · M · NOT TESTED**
*Statement.* The system under test cannot read the answers.
*Acceptance.* The server process cannot read case manifests, seed maps, or the harness repo —
verified structurally (working directory/container isolation, dependency graph, grep sweep for case
IDs and template literals), not by inspection alone. A reviewer finding otherwise raises a BLOCKER
regardless of behavior (AGENT_LOOP §3; EP §9 G1–G2).
*Verify.* R-ARCH + adversarial reviewer.
*Guard.* Not metric-based.

**PROC-04 · Baselines still runnable · M · NOT TESTED**
*Statement.* Every comparison MailWeave claims is re-run, not remembered.
*Acceptance.* All of these execute and produce metric rows in the current gate run: full-thread dump
(Baseline B), fixed oldest-K/newest-K (C), plain message-level search (D), the hosted or
labelled-reconstructed preview (A / A′), the strong-agent-with-primitives arms (**E-matched and
E-generous**, EP §8.7), **Baseline F(±1/±2/±5) — the hit-centred SC §6 baseline DISC-02 is entirely
built on (EP §8.8)** — and **RANK-02's recency-ordered and seeded-random ordering controls**, which
name this criterion as their home. F and the two controls were absent from the inventory, so the one
baseline the correction explicitly demands need not have been runnable at the gate (CONS-020). A win
that exists only in prose is not a win (AGENT_LOOP §7.6).
*Verify.* R-PERF/R-RETR execute them in the same interleaved session.
*Guard.* Dumbest max: let baselines rot and quote last quarter's numbers. This criterion is that guard.

**PROC-05 · Degenerate-strategy probe recorded per metric · M · NOT TESTED**
*Statement.* Each metric is explicitly checked against the dumbest way to max it.
*Acceptance.* For every metric-based criterion, the round's review record names the dumbest
implementation that would max it and states how the current code differs — with evidence, not
assertion (AGENT_LOOP §7.5).
*Verify.* Each domain reviewer for its own criteria; adversarial reviewer spot-checks.
*Guard.* Not metric-based.

**PROC-06 · Adversarial reviewer pass before the gate · M · NOT TESTED**
*Statement.* Someone whose only job is to defeat this rubric tries, before release.
*Acceptance.* An adversarial reviewer whose sole brief is to defeat this rubric — pass every criterion
while being wrong, hollow, or gamed — has run on the release candidate and produced no BLOCKER-eligible
finding (AGENT_LOOP §2.4, §10.6).
*Verify.* **Adversarial reviewer** records its own pass; the orchestrator supplies the retained report
in `docs/reviews/` but does not set the status (CONS-019b, CONS-032).
*Guard.* Not metric-based.

---

## Release gate

MailWeave is releasable only when, simultaneously and reviewer-confirmed (AGENT_LOOP §10): every `M`
criterion and every triggered `C` criterion is `PASS`; no criterion is `NOT TESTED`; zero open BLOCKER
or HIGH findings; all required real-Gmail E2E tests pass live; benchmark and performance bars pass on
reviewer-selected held-out seeds; baselines are current — including Baseline F and RANK-02's two
ordering controls (PROC-04); every `[UNSET]` bar this rubric names is registered in experiment log 001
**before** the criterion carrying it was reviewed; the adversarial pass is clean; and public claims
state exactly what was measured, what was not, and which problem is solved.

**Reviewer-domain note.** DOC-01…DOC-06 are verified by **R-DOC**, an eighth reviewer domain
(documentation and claim accuracy: README/public claims vs the experiment log, unbundling, limitations,
prior art). `AGENT_LOOP.md` §2.3's minimum reviewer set previously listed seven domains and none of them
was documentation, which left three mandatory criteria owned solely by the adversarial reviewer — an
agent that runs only at the gate and whose brief is to *defeat* this rubric, i.e. an attacker, not a
certifier (CONS-019). **`AGENT_LOOP.md` §2.3 now carries R-DOC as its eighth domain** (added by the
Round-1 reconciliation pass, the one edit it made to that file), so DOC-01…DOC-06 have an
ordinary-round owner and no longer wait for the gate. This is no longer an owner item.


---

## For owner decision — reconciled after Round 1

*(Rewritten by the Round-1 **reconciliation** pass, which cross-checked this list against
`ARCHITECTURE_DECISION.md` §I's O-1…O-8 and against the original findings in `docs/reviews/`. Items 1,
2, 3, 5 and 6 are **settled** and are recorded below with where they were settled, so no document
presents a closed item as open. The genuinely-owner items — and two this rubric never raised — live in
one place: **`docs/OWNER_DECISIONS.md`**. Numbering with `PRODUCT_CONTRACT.md` §10 and
`EVALUATION_PLAN.md` §16 remains shared.)*

**Settled — removed from the open list:**

1. ~~Completeness semantics (CONS-004; ARCH §H-2, ADV-209).~~ **RESOLVED.** PART-01 asserts
   `stated_total` = "what the source reported at `fetched_at`" at 100 %, and manifest equality lives in
   **GMAIL-03** with a residual-discrepancy bound that is `[UNSET — registered at G0 from PF-1]` and
   **gate-binding**, not merely published. This is exactly what ARCH §H-2 requested and the contract and
   plan carry the same two halves. What remains is PF-1's *number*, produced at G0 — a measurement, not
   a ruling.
2. ~~DISC-02 (CONS-001; ARCH §H-1).~~ **RESOLVED.** DISC-02 now runs the comparison at equal budget over
   ≥3 budget levels and publishes it either way; a loss is a reported finding and a tuning input, never
   a scope reduction; fixed ±2 stays a permanent baseline (PROC-04) and may never ship as the policy
   (SC §6; contract C-06). ARCH §H-1's requested wording is in force.
3. ~~The hit set `H` (CONS-003; ARCH §H-5 as amended by ADV-109).~~ **RESOLVED.** EV-01 and contract I-1
   carry one clause word-for-word; the shortlist size **and selection rule** are declared and
   pre-registered; `pool{…}` is required in the response and enumerated by ID in the trace (SEM-06);
   pool-construction probes stay inside `H` and are handled by `withheld`. `ARCHITECTURE_DECISION.md`
   A.7a now quotes the clause rather than paraphrasing it, and names its instantiation
   (`rule: "top-k by stage-A cosine"`, `k = 25`). EV-01's guard runs in both directions, so the
   deflationary degenerate is ruled out by the criterion itself.
5. ~~DISC-05's scope (ADV-208).~~ **RESOLVED in the measure-don't-remove direction.** `raw` is no longer
   independently requestable (ARCH D.1); `snippet` stays and the depth measurement is extended to the
   content-depth vocabulary (EP §6.4, §7.5.1; ARCH §H-3). Dropping a shipped level would be a scope
   reduction an agent may not make; extending the measurement adds an obligation. See DISC-05 itself.
6. ~~R-DOC (CONS-019).~~ **RESOLVED.** `AGENT_LOOP.md` §2.3 now carries **R-DOC — documentation accuracy
   and claim discipline** as an eighth reviewer domain, added by the reconciliation pass, so
   DOC-01…DOC-06 have an ordinary-round owner and can transition without waiting for the gate.

**DECIDED (2026-08-30) — see `docs/OWNER_DECISIONS.md`:**

4. **Forensics access (CONS-005).** May an implementer agent run `mailweave inspect` against the
   personal mailbox, or the human owner only? → **OD-4: owner-approved per incident** whenever real
   message text is surfaced; metadata/ID/timing/structure-only diagnostics stay autonomous (EP §2.4.6).
   Plus two the rubric had not listed: **OD-1**, the **Freshness Service Level** that FRESH-05 requires
   to be registered before the probe run (EP §11.2.2 states in terms that the plan may not set it), and
   **OD-2**, **ROUTE-04's 100 % empty-diagnosis bar** (ARCH §H-7 / §I O-1), now re-scoped to the drops
   actually probed with a registered incomplete-diagnosis ceiling (ROUTE-04). **OD-3** is the owner's
   acceptance of the E2 reply-chain floor's membership-not-full-text narrowing (ARCH §H-9 / §I O-6),
   decided in measurement by F17.

**Genuinely unachievable, marked rather than relaxed.** Unchanged from the Round-1 repair: none found.
The four criteria the audit called unsatisfiable or unmeasurable were unsatisfiable because of *wording
or a missing measurement*, and each was repaired by correcting the wording or adding the measurement.
The one real limit — Gmail offers no independent oracle for thread completeness — is handled by naming
the limit (PART-01) and putting a failable bound on the instrument (GMAIL-03). The Round-1
reconciliation added one honest correction of the same kind: **AD-04's ≤3 network-call bar bounded HTTP
chatter rather than cost**, so the cost bound now binds `api_calls`, registered at G0 (ARCH §H-8, §I
O-2) — a strengthening, not a relaxation.

---

## REPAIR LOG (Round 1)

Against `docs/reviews/CONSISTENCY_AUDIT_1.md` and the rubric-implicating findings of
`docs/reviews/ARCH_REVIEW_1.md`. **Criterion count 106 → 113** (110 `M`, 2 `C`, 1 `O`), 21 categories
unchanged, IDs stable and append-only.

### BLOCKERs

| Finding | What changed | Where |
|---|---|---|
| **CONS-001** DISC-02 licensed the scope reduction SC §6 forbids | Statement and acceptance rewritten: the shipped **query-aware** policy is measured against Baseline F(±2) at equal token budget over ≥3 budget levels and **the result is published either way**; a loss is a reported finding and a tuning input, **not** a scope reduction; fixed ±2 remains a baseline only and may never ship as the policy. The CTX §55 citation is dropped (it is about adding features, not deleting contracted ones) | DISC-02 |
| **CONS-002** egress unsatisfiable | SEC-07 and SEM-02 now name the **two-host runtime allowlist** (`gmail.googleapis.com` + `oauth2.googleapis.com`, refresh only) and add the ADV-210 requirement that runtime model loading is **forced offline** from a checksum-pinned path with setup-time-only provisioning; SEC-07's verification requires a **cold** start inside the allowlisted container | SEC-07, SEM-02 |
| **CONS-003** EV-01's `H` made the semantic rung unimplementable | EV-01 restated identically to contract I-1: `H` = executed-Gmail-query IDs (including relaxation/broadening calls and participant probes) **plus the retriever's threshold-passing shortlist**, not every scored row; shortlist size **declared and pre-registered**; `pool{…}` present and correct whenever a scored retriever ran, enumerated by ID in the trace; scan scope declared. Guard gained its **deflationary** direction, which is the degenerate ADV-109 says H-5's wording would otherwise legalise | EV-01 |
| **CONS-004** PART-01 unachievable / self-satisfying | PART-01 → `stated_total` extractable at 100% and equal to **what the source reported at `fetched_at`** at 100%, with the rationale recorded; **manifest equality moved to GMAIL-03** with a **gate-binding** residual-discrepancy bound registered from PF-1 (ADV-209), so the criterion can still fail; PART-01's guard re-based on O2, GMAIL-03 and PART-02 | PART-01, GMAIL-03 |
| **CONS-006** DISC-05 unmeasurable | DISC-05's acceptance now names EP §7.5.1's **large-thread depth arm** (flat map + declared truncation + affordance vs segment map, same cases, same budget, reporting accuracy, rounds, tokens and `levels_traversed_to_answer`) and EP §13.4 CG-PD's depth line; the trigger's declared-met status and the ADV-208 scope question are stated in the criterion | DISC-05 |
| **CONS-008** R-02 and R-03 had no criterion | Added **PART-07 · Role and reason on every message · M**: 100% of messages carry a `role` from the closed **seven-value** set and a non-empty mechanical `reason`; violations 0; guard rules out the constant-role/constant-reason degenerate via DISC-01, RANK-03 and SEM-06. **RANK-03's guard cross-reference repaired** — it cited DISC-03, which contains no presence requirement — and now points at PART-07 | PART-07 (new), RANK-03 |
| **CONS-015** SEM-01 reinstated a retired bar and a deleted gate | The "+15 points" and the "conditional on the lexical-only arm scoring below its entry threshold" clause are **gone**. Replaced by `[UNSET-empirical semantic_gain; registered at G0 against the G0-measured SEM-OFF distribution on the same HOLDOUT seed, EP §13.2]`, with "**There is no entry condition**" stated explicitly and EP §13.5's retirement quoted. SEM-05's stale `EP §8.2 Loop 4` pointer → `EP §13.4 CG-SEM`, with the reject branch scoped to backends only | SEM-01, SEM-05 |

### HIGHs

| Finding | What changed | Where |
|---|---|---|
| **CONS-009** stale Revision-1 citations | **All 39 EP citations re-pointed to Revision 2** (§8.2 → §13.4 naming the gate; §3.1→§6.1; §3.2→§6.2; §3.3→§6.3; §2.4→§4.4; §4.6→§8.6; §5 G*→§9 G*; §6.1→§10.1; §7→§11.1; §8.1→§13.1), and "EP citations are to Revision 2" added to How-to-use. Every "Loop *n*" bar reference now names its gate | throughout; How to use |
| **CONS-010** FRESH-02 carried 1 of 6 triggers | Trigger replaced by **any of MF1–MF6**, each spelled out; acceptance now requires the mitigation to remove **the specific trigger that fired**, verified by **arm H6 on the identical protocol, same strata, same N**, without regressing AD-04/PERF-01. Added **FRESH-05 · FSL registered before the probe run · M** | FRESH-02, FRESH-05 (new) |
| **CONS-011** 100% vs ≥0.98 | Aligned **deliberately, upward**: PART-02/PART-03 keep 1.00 and EP's CG-PD bar was raised to match, because these are mechanical self-consistency assertions, not statistical ones. The PART-0n ↔ P-n mapping is stated in How-to-use (and in EP §6.2) | PART-02, PART-03, How to use |
| **CONS-012** FRESH-01 omitted strata | Acceptance now requires results **per depth stratum (0/5/25) on both mailboxes**, with per-stratum ECDFs and censoring counts, and states that **pooling is a failure of the criterion, not a presentation choice**; second guard added for pooling | FRESH-01 |
| **CONS-013** four EP assertions had no criterion | Added **SEM-06 · Selection provenance and pool disclosure · M** (P6 + contract C-03's pool bound + T-RO1) and **FRESH-06 · Temporal partiality field · M** (P7, required in 100% of index-dependent cases whatever the measurement showed). P4/P5 are carried by PART-07 | SEM-06, FRESH-06 (new) |
| **CONS-007** T-CD2 untested | DISC-01's *Verify* now names **family F17 (decision-reversal)**, added to EP §4.7 | DISC-01 |
| **CONS-016** escalation trigger unmeasured | AD-05 now requires the trigger's over-/under-trigger rates to be **published from EP §7.4's trigger ablation**, and makes an unmeasured trigger hypothesis on the default path a FAIL | AD-05 |
| **CONS-017** blanket `[PRE-REG]` hid which numbers block | Replaced by EP §13.2's **three classes** — `[DEFINITIONAL]`, `[INHERITED — EP §13.4 <gate>]`, `[UNSET — register at G0 … against <named reference distribution>]` — and **every bracket in the document re-marked** accordingly (zero `[PRE-REG]` markers remain). The BLOCKER rule now applies to UNSET only, since inherited bars are already registered | How to use; all bracketed bars |
| **CONS-018** N-07 had no criterion | SEC-07 now asserts **no listening socket in the default configuration** (port scan) and stdio transport | SEC-07 |
| **CONS-019 / CONS-032** process self-certification | DOC-01…DOC-06 verified by **R-DOC** in the ordinary round with the adversarial reviewer at the gate; **PROC-01, PROC-02 and PROC-06 re-pointed to the adversarial reviewer**, with the orchestrator supplying the audit trail but not setting the status. Adding R-DOC to `AGENT_LOOP.md` §2.3 is recorded as a recommendation — this rubric does not own that file *(since applied by the Round-1 reconciliation pass; see that log below)* | DOC-01…06, PROC-01/02/06, Release gate |
| **CONS-020** PROC-04's inventory incomplete | Extended to A/A′, B, C, D, **E-matched and E-generous**, **Baseline F(±1/±2/±5)** and **RANK-02's recency and seeded-random ordering controls** | PROC-04 |
| **CONS-021** four contract clauses had no criterion | Added **SEC-08 · No learned routing policy · M** (B-05) and **DOC-06 · §58 minimum-proof bundle · M** (H-03); DOC-01 extended with H-07's published-negative-results rule; SEC-02 extended with "no attachment-content extraction path reachable from any tool" (B-04) | SEC-08, DOC-06 (new), DOC-01, SEC-02 |
| **CONS-022** CG-REAL had no criterion | Added **GMAIL-07 · Reality-tier oracles clean · M**: D1/D2/D4/D5/D8 executed against the personal mailbox under the redacting profile; O1/O2/O3/O5/O8/O9 zero unresolved violations with denominators; D2 signature coverage ≥ its registered floor with tickets above it. GMAIL-01 now names D8 as its wrapper | GMAIL-07 (new), GMAIL-01 |
| **CONS-014** embedding-bait fixtures | INJ-03's acceptance now names EP §5.1's **`I1-bait`** class and adds the non-displacement + visible-provenance assertion | INJ-03 |
| **CONS-025** content-processing components | **CLOSED in Round 1 by the architecture agent, confirmed by the reconciliation pass.** `ARCHITECTURE_DECISION.md` **D.4a** names every component with its licence — selectolax (MIT) with an lxml (BSD) fallback for HTML→visible text plus an explicit hidden-construct filter, talon (Apache-2.0, MIT fallback) for quote/signature stripping, stdlib `email` + RFC 2047 decoding + a declared charset ladder, and a sockets-disabled test obligation under PF-5. INJ-04, GMAIL-02 and DISC-03 no longer rest on an unselected component | ARCH D.4a |

### MEDIUM / LOW closed here

**CONS-023** `stated_total` canonical, `claimed_total` named as the adapter's normalisation (How-to-use).
**CONS-024** LEX-02 now requires the full `asked_for` block and `constraint_coverage` on every disclosed
message — the whole of T-RC3's resolution, previously required by nothing. **CONS-028** INJ-05 promoted
`O` → `M` so STR-02 no longer depends on an optional criterion; totals corrected. **CONS-033** canonical
names applied (`stated_total`, depth tokens, `map_id`, `asked_for.term_coverage`, Tier/M/CG/PF
vocabulary, seven-value roles) and recorded in How-to-use. **CONS-034** GMAIL-05 now states that the
~10× and ~4× figures are both true and differently scoped. **CONS-035** §18's header cites
`AGENT_LOOP §7.2, §9`.

### Not closed, and why

- **CONS-025, CONS-031(a), CONS-029, CONS-036, CONS-037** — all required edits to
  `ARCHITECTURE_DECISION.md`, which another agent was reworking this round. Escalated, not silently
  dropped. **All five have since landed there** (CONS-025 → D.4a; CONS-031(a) → E.2's LR row with its
  removal gate and the `H5-LRoff` arm; CONS-029 → B.6; CONS-036 → A.7's L1 stop rule; CONS-037 → §C
  T-RC2), verified by the reconciliation pass against that document.
- **CONS-027** — spec-revision status; the `CONTEXT_DISCLOSURE_OPTIONS.md` half is outside this
  repair's file ownership.
- **CONS-033 rows 4 and 7** — the mapping notes that belong *inside* the research documents
  (`CONTEXT_DISCLOSURE_OPTIONS.md`'s `role_reason` → `reason`, and `ROUTING_OPTIONS.md`'s "L7 = the
  semantic rung", which collides with `ARCHITECTURE_DECISION.md` A.7's L7 = disclosure assembly). Those
  documents are preserved-by-design and outside this repair's ownership; the canonical names are
  recorded here, in the contract's §0 and in `EVALUATION_PLAN.md` §6.2/§7.5, so no reviewer working
  from the governing set is sent to the wrong rung. **The L-number collision is the drift row most able
  to make a reviewer test the wrong thing and should be fixed in `ROUTING_OPTIONS.md`'s addendum next
  round.** The `SECURITY_NOTES.md` half is appended to that document's addendum. This
  rubric's MCP-01 already cites 2026-07-28 correctly and needed no change.
- **CONS-019's `AGENT_LOOP.md` edit** — was a recommendation only; **since applied** by the Round-1
  reconciliation pass, which added **R-DOC** to `AGENT_LOOP.md` §2.3 and changed nothing else in that
  file.
- **Items 1–6 of "For owner decision"** — owner rulings, not agent-closable defects. **Reconciled after
  Round 1:** items 1, 2, 3, 5 and 6 are now settled (see that section); item 4 and two further items
  are consolidated in `docs/OWNER_DECISIONS.md`.

---

## REPAIR LOG — Round 1 — reconciliation

*Applied by the reconciliation pass after `ARCHITECTURE_DECISION.md`'s parallel repair landed. Scope:
close escalations the other half settled, correct one criterion whose counter did not measure what the
criterion claims, and hand only genuine owner questions to `docs/OWNER_DECISIONS.md`. **Criterion count
unchanged at 113**; no criterion was weakened, retired or renumbered.*

| # | What changed | Where |
|---|---|---|
| **R-1** | **AD-04 re-expressed on the counter that tracks cost.** The bar now binds `http_requests` (median ≤3, the preserved figure, cross-checked by OBS-04) **and** `api_calls` (median ≤ `[UNSET — register at G0 against the G0-measured Baseline D `api_calls` distribution]`), with `quota_units` diagnostic. Rationale recorded in the criterion: under HTTP batching a proxy sees one request per batch whatever *n* is, so ≤3 bounded chatter, not cost, while AD-04's own statement is a cost claim. Strengthening, not relaxation — and no number was invented (ARCH §H-8, §I O-2; ADV-106) | AD-04 |
| **R-2** | **ROUTE-04 left binding at 100 %** and given an explicit *Owner decision pending* note naming `OWNER_DECISIONS.md` **OD-2**, the built mechanism (`max_relax_probes = min(k, 6)`, the third `incomplete` `empty_diagnosis` state) and the two honest forms the bar can take. **Superseded by OD-2 (2026-08-30):** the bar is now 100 % over drops *actually probed*, plus an `[UNSET — register at G0]` incomplete-diagnosis ceiling (ARCH §H-7, §I O-1) | ROUTE-04 |
| **R-3** | **DISC-05's scope question resolved in the measure-don't-remove direction** and removed from the owner list: `raw` is already not independently requestable, `snippet` stays, and the depth measurement is extended to the content-depth vocabulary. Dropping a shipped level would be the scope reduction SC §1/§6 forbids. Section pointer corrected **EP §7.5 → §7.5.1** in both the acceptance and the *Verify* line | DISC-05 |
| **R-4** | **"For owner decision" rewritten.** Items 1, 2, 3, 5 and 6 recorded as **RESOLVED** with the location of each settlement (PART-01+GMAIL-03; DISC-02; EV-01+contract I-1+SEM-06; DISC-05; `AGENT_LOOP.md` §2.3's new R-DOC domain). Item 4 (forensics access) stays open as **OD-4**, and the two items this rubric had never raised — the **Freshness Service Level** (OD-1) and **ROUTE-04's bar** (OD-2) — are named, with **OD-3** (E2 floor acceptance) cross-referenced | For owner decision |
| **R-5** | **CONS-025 marked closed** in the Round-1 log, pointing at `ARCHITECTURE_DECISION.md` **D.4a**, which names each content-processing component with its licence and the sockets-disabled test obligation. INJ-04, GMAIL-02 and DISC-03 no longer rest on an unselected component. The "Not closed" bullet is updated: CONS-025, CONS-031(a), CONS-029, CONS-036 and CONS-037 have all since landed in the architecture, each verified against that document rather than taken on report | REPAIR LOG (Round 1) |

**Checked and deliberately not changed.** DISC-02, PART-01, GMAIL-03, EV-01, SEM-06, SEC-07 and SEM-02
already carry the canonical wording the architecture built to; the reconciliation pass copied *into* the
architecture rather than editing them, so the two halves land identically. **FRESH-05 is unchanged** —
it requires the FSL to be registered before the probe run and deliberately does not name a value, which
is why the value is an owner decision (OD-1) and not a rubric bar.
