# CONSISTENCY_AUDIT_1.md — Cross-document consistency audit of the MailWeave planning set

**Auditor:** consistency reviewer (independent; wrote none of the audited documents)
**Date:** 2026-08-30
**Brief:** internal consistency only — contradictions, gaps, orphans. Design quality and adversarial
attack are a separate reviewer's job (`AGENT_LOOP.md` §2.4).
**Authority order used:** `SCOPE_CORRECTION.md` (authoritative) > `PRODUCT_CONTRACT.md` >
`RELEASE_RUBRIC.md` / `ARCHITECTURE_DECISION.md` / `EVALUATION_PLAN.md` / `AGENT_LOOP.md`.
Where a document contradicts `SCOPE_CORRECTION.md`, that document is the defect.

**Documents audited (all of):** `SCOPE_CORRECTION.md` (388 l), `PRODUCT_CONTRACT.md` (544 l),
`RELEASE_RUBRIC.md` (1161 l), `ARCHITECTURE_DECISION.md` (865 l), `EVALUATION_PLAN.md` Rev 2
(1464 l), `AGENT_LOOP.md` (230 l), the five research `SCOPE CORRECTION ADDENDUM` sections
(`VERIFIED_RESEARCH.md`, `RETRIEVAL_OPTIONS.md`, `ROUTING_OPTIONS.md`,
`CONTEXT_DISCLOSURE_OPTIONS.md`, `SECURITY_NOTES.md`), and `MAILWEAVE_CONTEXT.md` §§20, 39, 55, 58.

**Structural checks that passed.** The rubric's own arithmetic is correct: 106 criteria in the status
table, 106 detail blocks, IDs identical in both, 21 numbered categories, 102 `M` + 2 `C` + 2 `O`.
All 22 tension IDs raised anywhere in the corpus appear in `ARCHITECTURE_DECISION.md` §C.

---

## 1. Traceability matrix

Legend: **ORPHAN↑** = contract obligation with no rubric criterion. **ORPHAN↓** = rubric criterion or
architecture component that nothing requires. **UNMEASURED** = criterion with no protocol in
`EVALUATION_PLAN.md`. Section references to EP use **Revision-2** numbering (see BLOCKER/HIGH finding
CONS-009 — the rubric and contract cite Revision-1 numbers throughout).

### 1.1 Capabilities C-01 … C-11

| Contract | Rubric criteria | Architecture | Evaluation protocol | Flags |
|---|---|---|---|---|
| **C-01** lexical first rung | LEX-01, LEX-02, LEX-03, LEX-04, EV-01, GMAIL-04 | A.5 (gmail_client), A.6 (query_analysis), A.7 L0–L3 + L1b, D.3 | §4.3 F1/F2, §8.4 Baseline D, §13.4 CG-EP; PF-9 | clean |
| **C-02** structural | STR-01…STR-05 | A.2 step 4, A.7 L4, A.9(5), D.6 | §7.2, F5/F6/F7/F13/F14/F15, §13.4 CG-STR | clean |
| **C-03** semantic escalation | SEM-01…SEM-05 | D5, A.7 L5, A.9, §C T-RO1/2/3 | §7.1 arms SEM-OFF/LOCAL-DEFAULT/LOCAL-ALT/HOSTED, F4/F11/F12, S14, CG-SEM | **ORPHAN↑**: C-03's observable *"whatever candidate pool the semantic rung embeds is bounded **and the bound is reported**"* — the architecture implements it (`retrieval_report.pool`, T-RO1) but **no rubric criterion asserts it** and no EP assertion checks it |
| **C-04** ranking | RANK-01…RANK-04 | D.7, A.7 L6 | §7.3 `pool_recall`/`rank_of_evidence`/`cut_loss`, F16, CG-RANK | clean |
| **C-05** adaptive escalation | AD-01…AD-05, PERF-04 | A.7 (ladder + caps), A.8 (sufficiency), D.3 | §7.4, §6.4 escalation confusion table, CG-AD | `answer_type_presence` is **ORPHAN↓ + UNMEASURED** (CONS-016) |
| **C-06** query-aware disclosure | DISC-01…DISC-06 | A.9, D.4, §C T-1/T-CD1 | §7.2 budget–recall curve, §8.8 Baseline F, CG-PD | DISC-02 contradicts SC §6 (CONS-001); DISC-05 **UNMEASURED** (CONS-006) |
| **C-07** explicit partiality | PART-01…PART-06 | A.9(4), D.2 response schema | §6.2 P1–P5, §10.2 partiality probe, CG-PD | PART-01 conditionally unachievable (CONS-004); PART-02/03 bars disagree with EP (CONS-011) |
| **C-08** recoverable routing | ROUTE-01…ROUTE-04, EV-04 | A.2 (RetrievalReport always), A.7 L2/L3, D.3(6) | §6.1 FNF + paired hallucinated-found, §7.4 bar 1, CG-AD | clean |
| **C-09** freshness | FRESH-01…FRESH-04 | D.9, D7, A.10 stamps | §11.1 protocol, §11.2 strata + MF1–MF6, CG-FRESH | FRESH-01 omits depth stratification; FRESH-02 trigger narrower than EP/architecture (CONS-010, CONS-012) |
| **C-10** observability | OBS-01…OBS-04 | A.11, D.10 schema v2 | §6.3 trace schema, §6.4, §9 G8, counting proxy | clean |
| **C-11** untrusted content | INJ-01…INJ-06 | A.2 step 6, D.2 fence/nonce, D.8 | O8 taint oracle, injection fixtures, §12 row | C-11(d) derived-text labelling has no criterion (vacuous while summaries are deferred — LOW) |

### 1.2 Response obligations R-01 … R-10

| Obligation | Rubric criteria | Architecture | Evaluation | Flags |
|---|---|---|---|---|
| **R-01** hit identity | STR-04, PART-02, EV-01 | D.2 `id`/`thread_id`/`position` | §6.2 P2, O4 | clean |
| **R-02** role (closed set) | **none** | D.2 `role` enum (7 values) | §6.2 P4 (3-value set only) | **ORPHAN↑ — BLOCKER (CONS-008).** §5.3 makes a role-less response non-conforming; nothing measures it |
| **R-03** mechanical reason | RANK-03 (no *fabricated* reasons only); DISC-01 (constructed multi-query cases only) | D.2 `reason` + `constraint_coverage` | §7.5 (adapters must expose reason), P6 | **ORPHAN↑ — BLOCKER (CONS-008).** Reason *presence on every message* is asserted nowhere; RANK-03's guard cites DISC-03 for a requirement DISC-03 does not contain |
| **R-04** depth + declared reductions | DISC-03 | D.4 depth vocabulary, A.9 | §6.2, O5 parse fidelity | clean |
| **R-05** totals vs included | PART-01, PART-02, STR-04 | D.2 `stated_total`/`included`/`included_as_stub` | §6.2 P1/P1a/P2, O2 | field-name drift `stated_total`↔`claimed_total` (CONS-023) |
| **R-06** stubs not numbers | PART-05 | A.9(4), D.2 `withheld[]` | §6.2 P3 | clean |
| **R-07** executable affordance | PART-04 | A.10 (`map_id`, bare-ID fallback), D.2 `affordances[]` | §6.1 P-follow driver, O3 | clean |
| **R-08** completeness + freshness stamps | FRESH-03, GMAIL-03 | D.2 `completeness`/`fetched_at`/`history_id`, D.9 | §6.4 P7, §11 | P7 has no rubric criterion (CONS-013) |
| **R-09** untrusted envelope | INJ-01, INJ-02, DOC-05 | D.2 `fence_nonce`, D.8 | O8 | clean |
| **R-10** self-truncation | DISC-06 | D.4 9,000-token ceiling, A.2 step 6 | PF-6, MCP-07 interop | clean |

### 1.3 Invariants and the remaining clause families

| Clause | Rubric | Architecture | Evaluation | Flags |
|---|---|---|---|---|
| **I-1** evidence preservation | EV-01…EV-06 | A.2, A.9, D.2 `withheld` | §13.4 CG-EP, O1 | **BLOCKER (CONS-003)** — `H` defined so the semantic rung cannot satisfy it |
| **I-2** explicit partiality | PART-01…PART-06 | A.9, D.2 | §6.2 P1–P5 | see C-07 |
| **I-3** adaptive cost | AD-04, PERF-01…PERF-04, LEX-04, SEM-04, RANK-01 | A.7 budgets, D.8 | §7.4, §6.1 latency/call protocol | clean |
| **I-4** recoverability | ROUTE-01…04, EV-04, AD-05 | A.3 seam (c), D.3(6) | §6.1 FNF+control, §7.4 bar 1 | clean |
| **N-01/N-02** zero-paid-API, local default | NFR-01, SEM-02, SEM-03 | D5, D6, D.8, B.8 | §7.1 bars 1–3, S14 | egress wording unsatisfiable (CONS-002) |
| **N-03** Gmail source of truth | NFR-03, FRESH-03 | T-RO3, A.10 step 2 | §7.1 closing note | clean |
| **N-04** minimum scope | SEC-01 | A.4 | §3.2.9 scope matrix | clean |
| **N-05** trace/privacy | SEC-05, SEC-06 | A.11 `Redacted[str]`, D10, T-5/T-SN1/2 | O9 canary, §2.4.7 | **BLOCKER (CONS-005)** — EP §2.4.6 Stage 1 persists unredacted bodies |
| **N-06** no telemetry | SEC-07 | A.1 peers, D.8 | §6.4 `non_google_egress_bytes` | **BLOCKER (CONS-002)** |
| **N-07** local-first (stdio, no listening socket) | **none** | A.1 (stdio) | — | **ORPHAN↑ (CONS-018)**; SN §10 P1 exists as a checklist item only |
| **N-08** reproducible setup | NFR-04 | B.6 `uv` (mis-cited as "NFR-08") | — | LOW citation error (CONS-029) |
| **B-01** read-only | SEC-02, MCP-04, DOC-05 | A.4, D.1 | — | clean |
| **B-02/B-03** Gmail-only, single mailbox | none | E.3 | — | scope statements; acceptable |
| **B-04** attachments metadata-only | none (GMAIL-01/E2E-01 mention attachment metadata) | D.1 `mode:"metadata"` only | §4.3 F8, S13 | **ORPHAN↑ (CONS-021)** |
| **B-05** no trained router | none | D.10 note, E.3 | — | **ORPHAN↑ (CONS-021)** — a settled SC §9/§15 principle with no gate |
| **B-06** no persistent store | SEC-05, NFR-03 | T-RO3, E.4 | §7.1 | clean |
| **H-01** claim→measurement | DOC-01 | G, E.2 | §9 G7 | clean |
| **H-02** unbundled | DOC-02 | — | §11.2.5, §0 rule 3 | adversarial-only ownership (CONS-019) |
| **H-03** §58 minimum proof bundle | none as a bundle (EV-05, EV-02, EV-06, PROC-04, PERF-*, MCP-07, DOC-02 cover the parts) | — | — | **ORPHAN↑ (CONS-021)** |
| **H-04** no freshness claim | FRESH-04 | D.9 | §11.2.5 | clean |
| **H-05** baseline honesty | DOC-04 | E.2, G | §8.1 | clean |
| **H-06** comparison completeness | DOC-03, PROC-04 | G, B.9 | §8.7 E-matched/E-generous | PROC-04's inventory is incomplete (CONS-020) |
| **H-07** negative results published | SEM-05 (semantic only) | E.2, G | §9 G7 | **ORPHAN↑** partial (CONS-021); contract's example numbers are a claim-discipline risk (CONS-026) |
| **H-08** limitations | DOC-03 | G | §15 | clean |
| **N-MCP-1…5** | MCP-01, MCP-02, MCP-06, MCP-04; N-MCP-5 → PART-04 | D.1, A.10, D.3 | PF-7; no EP protocol | MCP-02/03/05/06 are reviewer-executed with no EP protocol (accepted: they are structural, not statistical — noted, not a finding) |

### 1.4 Orphan register (consolidated)

**Contract obligations with no rubric criterion (ORPHAN↑):** R-02, R-03 (presence), C-03's pool-bound
disclosure, N-07, B-04, B-05, H-03 (as a bundle), H-07 (beyond semantic), C-11(d).

**Rubric criteria with no measurement in EVALUATION_PLAN (UNMEASURED):** DISC-05 (depth *n* vs *n−1*
— and it is a `C` criterion the architecture declares will fire), FRESH-01's depth stratification
(EP has it, the rubric does not — inverse gap), and the whole of EP's CG-REAL gate (Tier-1 D1–D8 /
O1–O9) which no rubric criterion names.

**EP measurements with no rubric criterion (ORPHAN↓ measurement):** P4 (role marking), P5 (no silent
derivation), P6 (selection provenance), P7 (temporal partiality — required by CG-FRESH "in all cases,
whatever the measurement showed"), `cut_loss`, `backend_parity`, the escalation confusion table's
over-/under-escalation cells, D2 signature-coverage floor, structural reproduction rate (§5.3).

**Architecture components nothing requires (ORPHAN↓):** the **LR recency rung** (ships
unconditionally, no contract clause, no criterion, no EP arm); `answer_type_presence` (the entire
resolution of T-RC2); the `asked_for` / `constraint_coverage` block (the entire resolution of T-RC3);
the segment map (self-declared under DISC-05, which is unmeasured).

**Baselines/controls required by criteria but missing from PROC-04's inventory:** Baseline F(±N) — the
SC §6 baseline DISC-02 is built on — and RANK-02's recency and seeded-random controls, which cite
PROC-04 as their home.

---

## 2. Tension closure

Every tension ID raised anywhere in the corpus. All 22 appear in `ARCHITECTURE_DECISION.md` §C with a
decision; the columns below record whether the decision is *closed* (decision + reversal criterion +
a settling measurement that exists) or only nominally closed.

| ID | Source | Decision recorded | Reversal criterion | Settling measurement exists | Verdict |
|---|---|---|---|---|---|
| T-1 disclosure depth | contract §9 | yes (D4: one nav level + escape hatch) | yes (DISC-05 shows depth *n* > *n−1*) | **no — EP defines no depth comparison** | **Open (unmeasurable)** — CONS-006 |
| T-2 structural cost | contract §9 | yes (D8 quota-native, caps 4/25) | yes (PF-3, or re-fetch dominance → Option F) | yes (PF-3) | Closed |
| T-3 what "complete" means | contract §9 | yes (`as_reported_by_source`) | "nothing — API ceiling" (acceptable) | yes (PF-1/GMAIL-03) | **Resolved inconsistently** with rubric PART-01 — CONS-004 |
| T-4 freshness vs zero-dependency | contract §9 | yes (`history.list` only, no Pub/Sub) | yes (MF1/MF5 only) | yes (PF-10 → MF1–MF6) | Closed; rubric FRESH-02 does not carry the same trigger set — CONS-010 |
| T-5 debuggability vs A.3 | contract §9 | yes (ID-based re-fetch, memory only) | "nothing" | yes (PF-8) | Closed in architecture; **EP contradicts it** — CONS-005 |
| T-VR1 PD required vs near-null gain | VR add. §4 | yes (claim on honest-partiality axis) | claim narrows, implementation does not reverse | yes (CG-PD + E-generous every gate) | Closed |
| T-VR2 one mailbox cannot settle freshness | VR add. §4 | yes (two mailboxes, strata separated) | — | yes (PF-10, EP §11.2.1) | **Resolved by restatement in the rubric**: FRESH-01 requires neither two mailboxes nor strata — CONS-012 |
| T-VR3 `get_thread` may truncate | VR add. §4 | yes (PF-1 blocking, Baseline B relabelled if lossy) | — | yes (PF-1) | Closed in architecture; **collides with PART-01** — CONS-004 |
| T-RO1 pool must be query-independent | RO add. §4 | yes (declared `pool{scope_rule,…}` in every response) | yes (a recall target needing an unbounded pool) | CG-SEM | **Nominally closed** — no rubric criterion or EP assertion checks the pool declaration (C-03 ORPHAN↑) |
| T-RO2 quota + CPU cap the pool | RO add. §4 | yes (thread-wise pool, 25×40 u) | yes (PF-3/PF-4) | yes | Closed |
| T-RO3 stale index vs required semantic | RO add. §4 | yes (bounded-and-declared, in-process LRU) | yes (measured recall/latency win + C-09 budgeted) | yes (CG-SEM, SEM-05) | Closed |
| T-RO4 TS premise void | RO add. §4 | yes (Python, §B.8) | yes (R1–R4) | yes (PF-4, PF-7) | Closed |
| T-RC1 escalation cannot be client-hostage | RT add. §4 | yes (seam (c), server-enforced floor) | "nothing while I-4 is release-blocking" | — | Closed |
| T-RC2 trigger not computable pre-escalation | RT add. §4 | yes (`answer_type_presence` + query shape, accept over-trigger) | yes (over-/under-trigger blowing PERF-01/SEM-04/SEM-01) | **no** — cited as "PF-9/CG-EP", but PF-9 is the Gmail-`q` scoping check and CG-EP has no trigger arm | **Open (unmeasurable)** — CONS-016 |
| T-RC3 rungs erode "I asked for X" | RT add. §4 | yes (`asked_for` + `constraint_coverage`) | — | cited as ROUTE-03/RANK-03, neither of which mentions the fields | **Nominally closed** — CONS-024 |
| T-CD1 compression ladder is multi-level | CD add. §4 | yes (flat map; segment map is the one exception, trips DISC-05) | yes (DISC-05 comparison fails ⇒ level removed) | **no** (same gap as T-1) | **Open (unmeasurable)** — CONS-006 |
| T-CD2 query-aware selection hides the reversing message | CD add. §4 | yes (E2 reply-chain floor non-negotiable) | — | **no — the "decision reversed later in the thread" family does not exist in EP §4.3 or §4.7** | **Open (unmeasurable)** — CONS-007 |
| T-CD3 beating ±2 may force embeddings into disclosure | CD add. §4 | yes (reuse, never trigger) | — | yes (pre-registered Loop-2 arm; EP §7.2 curve) | Closed |
| T-SN1 strictest profile governs debugging | SN add. §4 | yes (ID-based forensics in Loop 0) | — | yes (PF-8) | Closed in architecture; **EP §2.4.6 builds the opposite mechanism** — CONS-005 |
| T-SN2 A.3 more permissive than SN §4.3 | SN add. §4 | yes (SN §4.3 stricter list is the default; A.3 exception is code-gated) | yes (an owner decision, recorded) | yes (SEC-06) | Closed — and consistent with SC A.3, which *permits* rather than requires snippets |
| T-SN3 local-first puts injection + bait on the default path | SN add. §4 | yes (D6: embeddings + cross-encoder only, closed types by construction) | yes (a failure only a generative model fixes) | INJ-03, INJ-06, PF-5 | Closed; embedding-bait fixtures are named in architecture but **not added to any EP fixture list** (MEDIUM, folded into CONS-014) |
| T-SN4 dedicated seed account costs 7-day re-consent | SN add. §4 | yes (harness Testing + seed-only allowlist; read client Production-unverified) | yes (re-consent blocking a gate) | yes (PF-12) | Closed |

**Summary:** 15 closed, 3 nominally closed (T-RO1, T-RC3, plus T-SN3's fixture gap), 4 open because
their settling measurement does not exist (T-1, T-CD1, T-RC2, T-CD2), 1 resolved inconsistently
between architecture and rubric (T-3 / T-VR3 vs PART-01), 1 contradicted outright by another document
(T-5 / T-SN1 vs EP §2.4.6).

---

## 3. Findings

Schema per `AGENT_LOOP.md` §4, with one added field — **Change** — naming the document that must be
edited. Per `SCOPE_CORRECTION.md`'s preamble, the document that contradicts it is the one that
changes. "Reproduction" for a document audit is the exact read that exposes the defect.

### BLOCKER

```
ID:            CONS-001
Severity:      BLOCKER
Rubric:        DISC-02 (and DISC-01, which it contradicts)
Location:      RELEASE_RUBRIC.md:489-497 (statement l.491, acceptance l.495)
Reproduction:  Read DISC-02's statement beside SCOPE_CORRECTION.md §6 and
               CONTEXT_DISCLOSURE_OPTIONS.md:508 (addendum §1).
Expected:      SC §6: "Do not treat fixed +/-2 as MailWeave's final progressive disclosure policy…
               implement and review the actual query-aware policy against it." Contract C-06: "the
               shipped policy MUST be query-aware". CD addendum: the ship-the-simpler-policy clause
               (CD §9 H3) is "genuinely invalidated as a scope decision".
Actual:        DISC-02 reads "…the shipped disclosure policy is measured against the fixed ±2 baseline
               at equal token budget, and the simpler policy ships if it wins (SC §6; CTX §55)", and
               its acceptance ends "…or the loss is documented and the simpler policy ships." It cites
               SC §6 while asserting SC §6's opposite, having imported CD §9 H3 verbatim. It is also
               internally inconsistent with DISC-01 (M), which a fixed ±2 policy fails by construction.
Required fix:  Replace DISC-02's statement and the tail of its acceptance with: "*Statement.* The
               shipped query-aware policy is measured against the fixed ±2 baseline (Baseline F) at
               equal token budget and the result is published either way. *Acceptance.* …the
               comparison table is in the experiment log; a loss is a reported finding and a tuning
               input for the query-aware policy, **not** a scope reduction — fixed ±2 remains a
               baseline only (SC §6)." Drop the CTX §55 citation, which is about adding features, not
               about deleting contracted ones.
Change:        RELEASE_RUBRIC.md. (ARCHITECTURE_DECISION.md §H-1 already requests exactly this; the
               request is unactioned, so the defect is live.)
```

```
ID:            CONS-002
Severity:      BLOCKER
Rubric:        SEC-07, SEM-02, NFR-01 (and contract N-06)
Location:      RELEASE_RUBRIC.md:846-852 (SEC-07); :319-327 (SEM-02);
               PRODUCT_CONTRACT.md:433-434 (N-06); EVALUATION_PLAN.md:897-899 (§7.1 bar 2) and
               :585 (S14); SECURITY_NOTES.md §4.3 closing line.
Reproduction:  Read SEC-07's acceptance ("Egress capture over a full suite run in the default
               configuration shows connections only to Gmail") and SEM-02's ("outbound network
               restricted to gmail.googleapis.com") against ARCHITECTURE_DECISION.md A.1, whose peer
               list is "gmail.googleapis.com + oauth2.googleapis.com (refresh only)".
Expected:      A mandatory criterion must be satisfiable by a conforming implementation.
Actual:        OAuth token refresh contacts oauth2.googleapis.com, which is not gmail.googleapis.com.
               Any long-running conforming server fails SEC-07 and SEM-02 as worded; a container built
               to EP §7.1 bar 2 / S14 cannot refresh a token and cannot complete the suite. Four
               documents carry the same wording; only ARCHITECTURE (A.1, PF-5) is correct.
Required fix:  Everywhere, replace "only to Gmail" / "gmail.googleapis.com only" with an explicit
               two-host allowlist: "`gmail.googleapis.com` and `oauth2.googleapis.com` (token refresh
               only); no other host." Keep the substantive assertions unchanged (no analytics, no crash
               reporting, no update checks, no query-time model download, zero mailbox bytes to any
               non-Google host). Concretely: RELEASE_RUBRIC.md SEC-07 acceptance; SEM-02 acceptance;
               PRODUCT_CONTRACT.md N-06 ("The only network peers are Gmail, Google's OAuth token
               endpoint, and, under N-01's explicit opt-in, a user-configured provider");
               EVALUATION_PLAN.md §7.1 bar 2 and S14; SECURITY_NOTES.md §4.3 telemetry line.
Change:        RELEASE_RUBRIC.md, PRODUCT_CONTRACT.md, EVALUATION_PLAN.md, SECURITY_NOTES.md.
```

```
ID:            CONS-003
Severity:      BLOCKER
Rubric:        EV-01 (and the invariant it encodes, contract I-1)
Location:      PRODUCT_CONTRACT.md:265-275 (I-1 testable form); RELEASE_RUBRIC.md:151-162 (EV-01)
Reproduction:  Apply I-1's definition of `H` to the architecture's semantic rung: D5 embeds a pool of
               up to `max_embed_texts = 300` message rows and scores every one of them.
Expected:      `H ⊆ R` on every response, with `R` = IDs present at any depth plus IDs in `withheld`.
Actual:        `H` is defined as "the set of message IDs returned by the executed Gmail queries **and
               any scored retriever**". Read literally, all 300 scored pool rows enter `H` and must
               therefore appear in every response as stubs or withheld records. That collides head-on
               with DISC-04's ≤30%-of-Baseline-B token ceiling, RANK-04's body-depth cap and PERF-01's
               latency ceiling — all of which EV-01's own guard says must pass on the same run. The
               semantic rung is unimplementable under the literal reading, and the pool is better
               disclosed by the architecture's declared `pool` block than by 300 stub rows.
Required fix:  Amend both places identically. I-1: "`H` = the set of message IDs returned by the
               executed Gmail queries, plus, from any scored retriever, **the candidates that pass the
               retriever's selection threshold — the shortlist that enters the disclosure candidate
               set**. The scored pool itself is disclosed by its scoping rule and size under R-08 (the
               `pool` block), not by enumeration." EV-01: same wording, and add to its acceptance "the
               response's `pool{scope_rule, thread_count, message_count}` is present and correct
               whenever a scored retriever ran."
Change:        PRODUCT_CONTRACT.md and RELEASE_RUBRIC.md. (ARCHITECTURE §H-5 requests this and states
               it has built to the amended reading; the amendment does not exist yet.)
```

```
ID:            CONS-004
Severity:      BLOCKER (conditional on PF-1, but the decision is required before implementation)
Rubric:        PART-01, GMAIL-03
Location:      RELEASE_RUBRIC.md:546-554 (PART-01); :678-687 (GMAIL-03);
               PRODUCT_CONTRACT.md:532-537 (T-3); VERIFIED_RESEARCH.md §6.1/§11.2 (#239)
Reproduction:  Read PART-01's acceptance and guard against contract T-3 and architecture §C row T-3.
Expected:      One completeness semantics across the set.
Actual:        PART-01 requires `stated_total` to equal "the seeded manifest's true length" on ≥98% of
               cases and its guard requires "exact equality against manifest truth", while T-3,
               GMAIL-03 and architecture T-3 all say MailWeave can only assert "complete as reported by
               the source at time T" because Gmail has no thread operator, no count field, and
               `threads.get` truncation on long threads is reported. MailWeave's only source for the
               number is the instrument PART-01 would score it against. If PF-1 confirms truncation, no
               implementation can pass PART-01 and the honest response (inferring a count from a second
               call and presenting it as the source's report) is itself a T-3 violation.
Required fix:  Rewrite PART-01 now, unconditionally, as: "*Acceptance.* `stated_total` is extractable
               on 100% of thread-bearing responses and equals **what the source reported at
               `fetched_at`** on 100% of cases; the measured discrepancy between source-reported totals
               and manifest truth is published per PF-1/GMAIL-03 as a characterised instrument
               limitation, with the residual disagreement rate ≤ [PRE-REG, set from PF-1]." Move the
               manifest-equality assertion into GMAIL-03 where it belongs (it measures the instrument,
               not the server). Record the owner decision in the findings ledger either way, since
               ARCHITECTURE §H-2 escalated it and no answer exists in the set.
Change:        RELEASE_RUBRIC.md (PART-01 and GMAIL-03).
```

```
ID:            CONS-005
Severity:      BLOCKER (privacy constraint; SCOPE_CORRECTION Appendix A.3 is binding)
Rubric:        SEC-05, SEC-06 (and contract N-05)
Location:      EVALUATION_PLAN.md:292-305, esp. l.299 (§2.4.6 forensic escalation ladder, Stage 1);
               EVALUATION_PLAN.md:1296-1298 (G0 requires the forensic buffer) and §14 Q17
Reproduction:  Read EP §2.4.6 Stage 1 against SC Appendix A.3, contract N-05 and
               ARCHITECTURE_DECISION.md §C row T-5 / A.11.
Expected:      A.3 (binding): "No full personal email bodies in traces/logs. Short aggressively-redacted
               snippets may be persisted **only** when required to diagnose a specific real-mailbox
               failure. Full bodies remain memory-only during normal execution." Contract N-05 repeats
               it. Architecture resolves T-5/T-SN1 with "ID-based re-fetch into memory
               (`mailweave inspect`), never disk", and gates A.3's snippet exception behind
               `--diagnose=<finding-id>` with code-applied redaction.
Actual:        EP §2.4.6 Stage 1 persists "the offending raw message(s) and full trace, **unredacted**"
               to `~/.local/state/mailweave/forensics/<RF-id>/`, **automatically on oracle fire**, and
               EP §13.3 makes that buffer a G0 exit requirement. Encryption, 0600 modes, gitignoring
               and a TTL do not make it compliant: A.3 permits persistence of redacted snippets only.
               EP §14 Q17 concedes "a conservative reading of Appendix A.3 favours human-only", i.e.
               the plan knows the mechanism is not authorised. It also contradicts SEC-05 ("A full
               suite run leaves no message body, subject, or address on disk outside the declared trace
               policy") and architecture's D10 type-level redaction, under which a `PersonalTrace`
               has no field that can hold mail text at all.
Required fix:  Delete Stage 1 from EP §2.4.6 and replace it with architecture's mechanism: "Stage 1 —
               `mailweave inspect <trace_id>`: re-fetches the trace's message IDs live from Gmail into
               memory and prints to the terminal only; nothing is written to disk." Keep Stage 2
               (≤200-char code-redacted snippet, owner-approved, gitignored) and Stage 3 unchanged.
               Remove "forensic buffer encrypted with a TTL agreed by the owner" from the G0 list in
               §13.3 and replace with "`mailweave inspect` built and PF-8 green". Resolve §14 Q17 as
               "no buffer exists".
Change:        EVALUATION_PLAN.md.
```

```
ID:            CONS-006
Severity:      BLOCKER (a `C` criterion whose trigger is declared met, with no measurement defined)
Rubric:        DISC-05 (and T-1, T-CD1)
Location:      RELEASE_RUBRIC.md:521-530 (DISC-05); ARCHITECTURE_DECISION.md §H-3, D4, E.2 row 1;
               EVALUATION_PLAN.md §7.5 (l.949-953) and §6.4 — neither defines the comparison
Reproduction:  grep EVALUATION_PLAN.md for a depth-*n* vs depth-*n−1* arm, a `levels_traversed`
               metric, or a segment-map case set. There is none (only l.211, an unrelated use of
               "segment" in a quote-depth oracle).
Expected:      DISC-05 fires whenever more than one disclosure level beyond the evidence response plus
               escape hatch ships; architecture §H-3 declares the trigger met by design (segment map
               for ~500-message threads) and commits to satisfying it "with a measurement, not a
               waiver". CD addendum T-CD1 additionally requires "instrument levels-traversed-to-answer
               as a first-class metric".
Actual:        EVALUATION_PLAN.md defines no arm, no case set, no metric and no gate cell for this
               comparison. CG-PD's bars do not include it. A mandatory-once-triggered criterion is
               therefore unmeasurable, and per PROC-01 `NOT TESTED` blocks release.
Required fix:  Add to EVALUATION_PLAN.md §7.5: (a) metric `levels_traversed_to_answer` and
               `map_tokens` in §6.4; (b) a **large-thread depth arm** — threads at and above the
               measured flat-map token boundary (PF-6), run twice: flat map + declared truncation +
               affordance (depth *n−1*) vs segment map (depth *n*), same cases, same budget, reporting
               strict case accuracy, rounds, tokens and levels traversed; (c) a CG-PD line: "the depth
               comparison is published; the segment level ships only on a measured win, else it is
               removed (E.2)." Cross-reference it from RELEASE_RUBRIC.md DISC-05's *Verify* field.
Change:        EVALUATION_PLAN.md (primary); RELEASE_RUBRIC.md DISC-05 *Verify* pointer (secondary).
```

```
ID:            CONS-008
Severity:      BLOCKER
Rubric:        none — the minimum partiality contract of PRODUCT_CONTRACT.md §5.3 has no criterion for
               two of its six fields
Location:      PRODUCT_CONTRACT.md:356-361 (R-02, R-03), :364-367 (§5.3);
               RELEASE_RUBRIC.md:375-383 (RANK-03, incl. its guard)
Reproduction:  grep -n "role" RELEASE_RUBRIC.md → two hits, neither an acceptance condition on role
               presence (MCP-03 parity; INJ-02 negative assertion). No criterion asserts reason
               presence on every message either.
Expected:      §5.3: "A response that carries mail content and omits any of: hit identity (R-01), role
               (R-02), reason (R-03), totals-vs-included (R-05), an executable affordance while partial
               (R-07), or the untrusted envelope (R-09) is non-conforming regardless of retrieval
               quality." Every MUST has at least one rubric criterion (contract §0).
Actual:        R-02 and R-03 have none. RANK-03 asserts only that reasons are not *fabricated*, and its
               guard says the presence requirement is carried by "R-03's presence requirement in
               PART/DISC criteria (DISC-03)" — DISC-03 is about depth and reductions and contains no
               such requirement. DISC-01 requires reasons only on constructed multi-query cases. The
               closed role vocabulary (7 values) is asserted nowhere; EP's P4 adapter recognises only
               three values (matched/context/derived), so even the measurement that exists is narrower
               than the contract.
Required fix:  Add one criterion to RELEASE_RUBRIC.md §9 (partiality): "**PART-07 · Role and reason on
               every message · M**. *Acceptance.* 100% of messages in every response carry (a) a `role`
               from the closed set {matched, context, parent, child, requested, stub, derived} and (b) a
               non-empty mechanical `reason` naming the mechanism; violations 0. *Verify.* R-DISC schema
               sweep over the full suite. *Guard.* Dumbest max: emit a constant role/reason — ruled out
               by DISC-01's requirement that reasons be query-traceable and by RANK-03's no-fabrication
               rule." Update EVALUATION_PLAN.md §6.2 P4 to score the full 7-value set, and repair
               RANK-03's guard cross-reference to point at PART-07 instead of DISC-03.
Change:        RELEASE_RUBRIC.md (add PART-07, fix RANK-03 guard); EVALUATION_PLAN.md (§6.2 P4).
```

```
ID:            CONS-015
Severity:      BLOCKER
Rubric:        SEM-01
Location:      RELEASE_RUBRIC.md:307-318 (SEM-01 acceptance);
               EVALUATION_PLAN.md:1364-1366 (§13.5 rows deleting the entry condition and the +15 bar),
               :28-42 (change-log rows 3 and 7)
Reproduction:  Read SEM-01's acceptance against EP §13.5's "Loop 4 adopt rule" and "Loop 4 entry
               condition" rows.
Expected:      SC §4: semantic retrieval is part of the complete product, unconditional. EP deleted the
               lexical-recall entry condition and explicitly retired the +15-point adopt bar: "The +15
               was calibrated to an adopt/reject decision that no longer exists; keeping the number
               would be borrowing authority it never had."
Actual:        SEM-01's acceptance reads "…exceeds the lexical-only ablation by ≥ [PRE-REG — improvement
               bar; EP §8.2 proposes ≥+15 points, **conditional on the lexical-only arm scoring below
               its entry threshold**]". It resurrects both the retired number and the deleted entry
               condition, and attributes the number to an EP section that no longer proposes it — a
               claim-discipline breach under MAILWEAVE_CONTEXT §58 and contract H-01 (a number
               presented as a proposal that its own source withdrew). As written, a semantic rung could
               be failed or excused by an entry gate SC §4 forbids.
Required fix:  Replace SEM-01's bracket with: "≥ [UNSET-empirical `semantic_gain`; registered at G0 as
               a delta against the G0-measured SEM-OFF distribution on the same HOLDOUT seed, per EP
               §13.2]". Delete the "conditional on the lexical-only arm scoring below its entry
               threshold" clause entirely. Same treatment for SEM-05's "(EP §8.2 Loop 4)" pointer →
               "(EP §13.4 CG-SEM)".
Change:        RELEASE_RUBRIC.md.
```

### HIGH

```
ID:            CONS-009
Severity:      HIGH
Rubric:        every criterion carrying a [PRE-REG] citation (21 of them), plus 14 other EP pointers
Location:      RELEASE_RUBRIC.md — 21 occurrences of "EP §8.2", plus EP §2.4, §3.1 ×3, §3.2 ×4,
               §3.3, §4.6 ×2, §5 G1/G3/G4/G6, §6.1, §7, §8.1; PRODUCT_CONTRACT.md — EP §3.3, §4.1,
               §4.5, §5 G7
Reproduction:  `grep -o "EP §[0-9.]*" RELEASE_RUBRIC.md | sort | uniq -c`, then open the cited
               sections in EVALUATION_PLAN.md Revision 2.
Expected:      A reviewer following a citation lands on the evidence it names.
Actual:        Every EP citation in the rubric and contract uses **Revision-1** numbering. EP Rev 2
               renumbered (its own map, EP l.59-75): §3→§6 (metrics), §4→§8 (baselines), §5→§9
               (anti-gaming), §7→§11.1 (freshness), §8.1→§13.1, §8.2→§13.3-13.5, §2→§4 (suite),
               §6→§10 (M1/M2). So "EP §8.2 proposes ≥0.98" resolves to *Baseline B — full-thread dump*,
               which proposes nothing; "EP §2.4" (cited for the position sweep) resolves to the
               redaction toolkit; "EP §3.2 P1/P2/P3" resolve to seeding mechanics. The rubric's own
               PRE-REG rule ("a criterion reviewed against an unregistered number is itself a BLOCKER")
               is therefore unusable as written, because no reviewer can find the register.
Required fix:  Rewrite all 35 citations to Rev-2 numbering: §8.2→§13.4 (CG-EP/CG-PD/CG-AD, naming the
               gate); §3.1→§6.1; §3.2→§6.2; §3.3→§6.3; §2.4→§4.4; §4.1→§8.1; §4.5→§8.5+§8.7;
               §4.6→§8.6; §5 G*→§9 G*; §6.1→§10.1; §7→§11.1; §8.1→§13.1. Add to the rubric's "How to
               use" block: "EP citations are to EVALUATION_PLAN.md Revision 2."
Change:        RELEASE_RUBRIC.md, PRODUCT_CONTRACT.md.
```

```
ID:            CONS-010
Severity:      HIGH
Rubric:        FRESH-02
Location:      RELEASE_RUBRIC.md:729-740; EVALUATION_PLAN.md:1184-1196 (§11.2.3 MF1–MF6);
               ARCHITECTURE_DECISION.md D.9
Reproduction:  Compare FRESH-02's *Trigger* line with EP §11.2.3's table and architecture D.9's "The
               full mitigation (FRESH-02) is built if any of MF1–MF6 fires."
Expected:      One trigger set across the three documents.
Actual:        FRESH-02 fires only "if FRESH-01 shows MailWeave-vs-direct-API or direct-API-vs-mailbox
               lag above the pre-registered bar [… median gap ≤60 s]". EP defines six triggers, five of
               which need no invented number: MF1 (any probe censored at 72 h), MF2 (p90 > FSL in any
               stratum), MF3 (depth divergence with the CI excluding zero), MF4 (a confirmed real-mail
               false negative on the personal mailbox), MF5 (bimodal ECDF), MF6 (the 60 s gap the
               rubric quotes). As written, a message that never becomes findable (MF1) or a
               depth-25-only failure (MF3) — the exact signature VR §1.3 reports — would not make the
               mandatory mitigation fire.
Required fix:  Replace FRESH-02's *Trigger* with: "Fires if **any** of EP §11.2.3's MF1–MF6 fires."
               Add to its acceptance: "the mitigation removes the specific trigger that fired,
               verified by arm H6 on the identical protocol, same strata, same N (EP §11.2.4), without
               regressing AD-04/PERF-01." Add an `M` criterion FRESH-05: "the FSL is registered by the
               owner in experiment log 001 before the probe run" (EP §11.2.2 makes it blocking and no
               criterion carries it).
Change:        RELEASE_RUBRIC.md.
```

```
ID:            CONS-011
Severity:      HIGH
Rubric:        PART-01…PART-05
Location:      RELEASE_RUBRIC.md:546-590; EVALUATION_PLAN.md:797-812 (§6.2 P-table),
               :1319-1325 (CG-PD bars)
Reproduction:  Line up rubric PART-0n against EP P-n.
Expected:      Shared IDs mean the same thing and carry the same bar.
Actual:        Two defects. (a) **Numeric disagreement**: PART-02 demands the included-set match "on
               100% of responses" and PART-03 demands "failure rate 0 on the complete-thread
               direction", while CG-PD sets "P1a, P2, P3 pass ≥ 0.98". (b) **ID collision**: rubric
               PART-04 is "affordances are executable" and PART-05 is "unexpanded content is visible as
               stubs", whereas EP's P4 is "match-role marking" and P5 is "no silent derivation", both
               barred at ≥0.95. A reviewer reading "P4 ≥ 0.95" against PART-04 would apply a bar
               belonging to a different assertion, and EP's actual P4/P5 have no rubric home (CONS-013).
Required fix:  (a) Align the numbers: either raise CG-PD's P2/P3 to 1.00 (they are mechanical
               self-consistency assertions, not statistical ones — this is the honest choice and the
               one the rubric already makes) or lower PART-02/03 to ≥0.98. Recommend raising EP.
               (b) Add to the rubric's "How to use" block: "PART-0n criterion IDs are independent of
               EVALUATION_PLAN §6.2's P-n assertion IDs; the mapping is PART-01→P1/P1a, PART-02→P2,
               PART-03→P3, PART-04→O3 + the P-follow driver, PART-05→R-06, PART-06→§6.2's end-to-end
               probe." And in EP §6.2, add the same mapping note.
Change:        EVALUATION_PLAN.md (P2/P3 bars, mapping note) and RELEASE_RUBRIC.md (mapping note).
```

```
ID:            CONS-012
Severity:      HIGH
Rubric:        FRESH-01
Location:      RELEASE_RUBRIC.md:719-728; EVALUATION_PLAN.md:1170-1182 (§11.2.1)
Reproduction:  Read FRESH-01's acceptance for the words "stratum", "depth", "two mailboxes".
Expected:      T-VR2 and EP §11.2.1: probes replicated across depth strata 0/5/25, results reported
               per stratum, "pooling across strata is prohibited", and two mailboxes minimum, because
               "a negative result on one mailbox licenses no freshness sentence".
Actual:        FRESH-01 requires only "N≥30 over ≥5 days, covering all arms, with lag distributions
               and censoring published". A run that pools strata and uses one mailbox satisfies it —
               and would hide precisely the depth-specific failure the protocol exists to find.
Required fix:  Extend FRESH-01's acceptance: "…per **depth stratum (0 / 5 / 25)**, on **both**
               mailboxes, with per-stratum ECDFs and censoring counts; pooling across strata is a
               failure of this criterion, not a presentation choice (EP §11.2.1)." Extend its guard
               with the pooling case.
Change:        RELEASE_RUBRIC.md.
```

```
ID:            CONS-013
Severity:      HIGH
Rubric:        none — four EP assertions have no criterion
Location:      EVALUATION_PLAN.md:807-808 (P4, P5), :865-866 (P6, P7); CG-FRESH bullet 4
Reproduction:  grep the rubric for "provenance", "derived", "temporal partiality", "P6", "P7".
Expected:      Each mandatory measurement moves a criterion (EP §12's stated purpose).
Actual:        P4 (role marking) and P5 (no silent derivation) have no criterion (see CONS-008); P6
               (selection provenance — "a semantically-selected message is never presented as a Gmail
               search hit") is only partially implied by RANK-03; P7 (temporal partiality, "required
               **regardless** of what the freshness experiment finds") has no criterion at all, though
               CG-FRESH requires it "present and correct in all cases". These are honesty properties
               the architecture implements (D.2 `score.method/model`, D.9 stamps) and the gate cannot
               check.
Required fix:  Add two `M` criteria to RELEASE_RUBRIC.md: "**SEM-06 · Selection provenance and pool
               disclosure**. *Acceptance.* Every disclosed message names how it was selected
               (lexical_hit / structural / semantic_similarity / thread_context); a semantically
               selected message is never labelled a Gmail search hit; any similarity value is labelled
               similarity, never confidence; and whenever a scored retriever ran, `pool{scope_rule,
               thread_count, message_count, why}` is present (EP P6; contract C-03; T-RO1)." And
               "**FRESH-05 · Temporal partiality field**. *Acceptance.* When a result depends on the
               search index, the response says so in a machine-readable field, in 100% of such cases,
               whatever the freshness measurement showed (EP P7)." (If FRESH-05 is used for the FSL
               per CONS-010, number these FRESH-05/FRESH-06.)
Change:        RELEASE_RUBRIC.md.
```

```
ID:            CONS-007
Severity:      HIGH
Rubric:        DISC-01, DISC-02, EV-02 (the E2 floor they depend on is untested)
Location:      ARCHITECTURE_DECISION.md §C row T-CD2 ("Settled by: the adversarial 'decision reversed
               later in the thread' family, **which must be added to the suite**");
               CONTEXT_DISCLOSURE_OPTIONS.md addendum T-CD2; EVALUATION_PLAN.md §4.3, §4.7
Reproduction:  Read EP's family inventory (F1–F10, F11–F16). No family constructs a thread in which
               the query-scored-highest messages support one answer and a low-scoring later reply
               reverses it. F5 (decision evolution) scores the *confirmation* as the answer — the
               opposite shape.
Expected:      Architecture makes the E2 reply-chain floor "non-optional and not budget-negotiable"
               precisely because query-scored selection can hide the disconfirming message; that
               mitigation's only named test is this family.
Actual:        The family does not exist anywhere. The single shipped risk that the corrected scope
               introduces on the default path (CD addendum: "now shipped risks on the default path")
               has no measurement, and the E2 floor's budget cost is therefore unjustifiable and
               untestable.
Required fix:  Add to EVALUATION_PLAN.md §4.7: "**F17 decision-reversal (adversarial to query-aware
               selection)**, n = 8. A thread whose highest query-scoring messages support answer A and
               whose low-scoring later reply reverses it to B; distractors reinforce A. Correct answer
               = B. Scored strictly. Purpose: the only test of the non-negotiable E2 reply-chain floor
               (T-CD2); run in both the query-aware and Baseline F(±2) arms." Cite F17 from
               ARCHITECTURE §C row T-CD2 and from DISC-01's *Verify*.
Change:        EVALUATION_PLAN.md (primary); ARCHITECTURE_DECISION.md §C pointer (secondary).
```

```
ID:            CONS-016
Severity:      HIGH
Rubric:        AD-05, SEM-04, PERF-04 (all cite escalation triggering; none tests the trigger)
Location:      ARCHITECTURE_DECISION.md A.8 (`answer_type_presence`), §C row T-RC2, D.3 rule 4,
               E.2 row 5; EVALUATION_PLAN.md §13.4 CG-EP
Reproduction:  Follow A.8's own pointer: "PF-9/CG-EP measure its over-trigger and under-trigger
               rates". PF-9 (§F) is "Confirm Gmail `q` message-scoped semantics on the seed corpus" —
               unrelated. CG-EP's bars are recall, FNF, Baseline-B proximity and hallucinated-found —
               no trigger measurement.
Expected:      `answer_type_presence` is the architecture's entire answer to T-RC2 (the
               confident-but-wrong lexical result), is explicitly labelled "a hypothesis,
               pre-registered for Loop 3", and E.2 lists it as removable if it over/under-triggers.
Actual:        No document measures it. The citation is wrong, EP has no arm, and no rubric criterion
               exists. An unmeasured hypothesis is on the shipped default path deciding when to
               escalate.
Required fix:  (a) ARCHITECTURE_DECISION.md A.8 and §C row T-RC2: replace "PF-9/CG-EP" with
               "CG-EP + the F11/F12 trigger ablation (EP §7.4)". (b) EVALUATION_PLAN.md §7.4: add
               "**Trigger ablation** — run F11 (lexical trap) and F12 (semantic negative control) with
               the trigger set to (i) query-shape only and (ii) query-shape ∨ `answer_type_presence`;
               report over-escalation (F12) and under-escalation (F11) for each; the composite ships
               only if it reduces under-escalation without breaching the F12 ceiling or PERF-01."
               (c) RELEASE_RUBRIC.md AD-05: add "the escalation trigger's over-/under-trigger rates are
               published from the ablation of EP §7.4".
Change:        EVALUATION_PLAN.md, ARCHITECTURE_DECISION.md, RELEASE_RUBRIC.md.
```

```
ID:            CONS-017
Severity:      HIGH
Rubric:        all 21 [PRE-REG]-carrying criteria
Location:      RELEASE_RUBRIC.md:20-27 ("How to use", the [PRE-REG] rule);
               EVALUATION_PLAN.md:1272-1278 (§13.2 three-class table), :1391 (§13.5 closing line)
Reproduction:  Read the rubric's PRE-REG rule against EP §13.2's class table.
Expected:      One doctrine on which numbers are already set.
Actual:        The rubric says every bracketed number "must be pre-registered from Loop 0 measurement…
               before any implementation is reviewed against it" and that EP's values are "cited as a
               proposal, never as an adopted bar". EP §13.2 classifies bars into **Definitional**
               (settable now), **Inherited** (carried forward unchanged — explicitly the CG-EP/CG-PD/
               CG-AD numbers the rubric brackets: 0.98/0.95/0.05, ≤30%, ≥3×, ≤1.25×, ≤3 calls, ≥80%,
               ≤10%, >20%, ≤0.10, ≥0.9, 60 s, N≥30/5 days) and **UNSET-empirical** (needs G0). EP
               §13.5 closes: "Unchanged and still binding: … the CG-EP / CG-PD / CG-AD numeric
               proposals exactly as Revision 1 wrote them." So the rubric would send a reviewer to
               re-derive at G0 numbers EP treats as already binding, and — worse — treats genuinely
               unset bars (semantic_gain, F13/F14/F15, cut_loss, budget levels, FSL) identically to
               inherited ones, hiding which ones actually block.
Required fix:  Adopt EP's three classes in the rubric. Replace the single `[PRE-REG]` marker with
               `[INHERITED — EP §13.4 <gate>]`, `[DEFINITIONAL]` and `[UNSET — register at G0 per EP
               §13.2 against <named reference distribution>]`, and re-mark each of the 21 brackets
               accordingly. Keep the rule "a criterion reviewed against an unregistered UNSET number is
               itself a BLOCKER"; it should not apply to inherited bars.
Change:        RELEASE_RUBRIC.md.
```

```
ID:            CONS-022
Severity:      HIGH
Rubric:        GMAIL-01, E2E-04 (under-specified); EP's CG-REAL gate has no criterion at all
Location:      RELEASE_RUBRIC.md:663-669 (GMAIL-01), :1043-1051 (E2E-04);
               EVALUATION_PLAN.md §2.4.5 (O1–O9), §2.5 (D1–D8), §13.4 CG-REAL
Reproduction:  grep the rubric for "oracle", "O1", "D1", "census", "Tier 1". No hits.
Expected:      SC §13 makes real Gmail primary and requires "the evaluation methodology [to] make
               real-mailbox behavior a first-class source of engineering failures"; EP implements that
               with nine content-free oracles, eight discovery protocols and a CG-REAL gate whose
               bullets include "zero open BLOCKER findings from Tier 1", "O1/O2/O3/O5/O8/O9 clean with
               denominators", "D2 signature coverage at or above the registered floor" and "a D4
               session executed this round".
Actual:        The rubric's only real-mailbox criteria are a smoke suite (GMAIL-01) and "both profiles
               exercised" (E2E-04). Nothing at the gate requires the oracles to run or to be clean, so
               the reality tier — the correction's headline methodology change — is unenforceable, and
               EP §12's promise that a reviewer can move a criterion on this evidence has no target.
Required fix:  Add a `M` criterion: "**GMAIL-07 · Reality-tier oracles clean**. *Acceptance.* The
               round's Tier-1 run executed protocols D1/D2/D4/D5/D8 and oracles O1–O9 against the
               personal mailbox under the redacting profile; O1, O2, O3, O5, O8 and O9 report zero
               unresolved violations with denominators published; D2 signature coverage ≥ its
               registered floor, with a corpus-extension ticket for every uncovered signature above it
               (EP §2.4.5, §2.5, §13.4 CG-REAL). *Verify.* R-GMAIL + R-SEC (O9). *Guard.* Dumbest max:
               run the oracles only on the seeded account — ruled out by the personal-profile
               requirement and by E2E-04." Extend GMAIL-01's acceptance to name D8 as the wrapper.
Change:        RELEASE_RUBRIC.md.
```

```
ID:            CONS-025
Severity:      HIGH
Rubric:        INJ-04, GMAIL-02, DISC-03
Location:      ARCHITECTURE_DECISION.md D.4 ("Quote stripping is heuristic and bypassable; the GPLv3
               `html2text` is excluded on licence grounds"), A.5; RELEASE_RUBRIC.md:884-893 (INJ-04),
               :670-677 (GMAIL-02); CONTEXT_DISCLOSURE_OPTIONS.md §3 (talon / email_reply_parser /
               html2text licence analysis)
Reproduction:  grep ARCHITECTURE_DECISION.md for an HTML-to-text library, a quote-stripping library,
               or an RFC 2047 / charset decoding mechanism. The only named library is excluded.
Expected:      The architecture's declared scope is "components, seams, **technology selection**, tool
               names, algorithms, budgets". INJ-04 requires "a **maintained parser**" plus hidden-
               construct removal and a sockets-disabled proof; GMAIL-02 requires RFC 2047 encoded-words,
               non-UTF-8 charsets and HTML-only bodies handled without loss; DISC-03 requires every
               reduction declared with a byte count.
Actual:        No parser, stripper or charset-decoding component is selected anywhere. Three mandatory
               criteria rest on an unspecified component, and the one candidate the architecture
               mentions is ruled out on licence grounds with no replacement.
Required fix:  Add to ARCHITECTURE_DECISION.md §D a subsection "D.4a Content processing": name the
               HTML→visible-text parser (permissive licence, maintained, no network — e.g. the
               selectolax/lxml + explicit hidden-construct filter path), the quote/signature stripper
               (talon, Apache-2.0, per CD §3) with its declared-and-bypassable rule, the MIME/charset
               decoding boundary (stdlib `email` + explicit RFC 2047 decode + charset fallback ladder,
               all failures declared not dropped), and state that hidden-construct removal emits
               `hidden_content_removed` and that the parser is tested with sockets disabled (INJ-04).
               Add the licence of each pick, since `html2text` was excluded on exactly that basis.
Change:        ARCHITECTURE_DECISION.md.
```

```
ID:            CONS-018
Severity:      HIGH
Rubric:        none — contract N-07 has no criterion
Location:      PRODUCT_CONTRACT.md:435-436 (N-07); SECURITY_NOTES.md §10 P1;
               RELEASE_RUBRIC.md §14 (no transport criterion)
Reproduction:  grep -i "stdio\|listening socket\|transport" RELEASE_RUBRIC.md → no hits.
Expected:      Every contract MUST has at least one rubric criterion.
Actual:        "Default transport is stdio; no listening socket in the default configuration" is
               unenforced at the gate, although it is a security posture item (SN §10 P1) and the whole
               local-first story depends on it.
Required fix:  Extend SEC-07's acceptance with "…and the default configuration opens no listening
               socket (asserted by a port scan of the running server); default transport is stdio
               (contract N-07; SN §10 P1)", or add a one-line criterion NFR-05. Also add SN §10 P4's
               per-call size ceiling / rate-limit obligation to DISC-06's acceptance (see CONS-038).
Change:        RELEASE_RUBRIC.md.
```

```
ID:            CONS-019
Severity:      HIGH
Rubric:        DOC-02, DOC-03, DOC-04 (and PROC-02, PROC-06)
Location:      RELEASE_RUBRIC.md:1067-1096, :1112-1120, :1145-1152; AGENT_LOOP.md §2.3, §2.4, §6;
               EVALUATION_PLAN.md §12 "Documentation accuracy" row
Reproduction:  Read the *Verify* field of DOC-02/03/04 ("Adversarial reviewer") against AGENT_LOOP
               §2.3's minimum reviewer set (seven domains, none of them documentation) and §2.4 (the
               adversarial reviewer is periodic, runs "at minimum before any release gate", and its
               brief is to *defeat* the rubric).
Expected:      Every mandatory criterion can be moved to PASS by a named reviewer domain with named
               evidence, in an ordinary round.
Actual:        Three mandatory criteria are owned solely by an agent that does not run in ordinary
               rounds and whose findings are BLOCKER-eligible by construction — it is an attacker, not
               a certifier. They can therefore only ever transition at the gate, and the round protocol
               (§5 step 6: "every criterion this round targeted is PASS") cannot target them.
               Separately, PROC-02 ("no criterion certified by its implementer") and PROC-06
               ("adversarial pass happened") are verified by the **orchestrator**, which is also the
               agent that updates the status table (§6) — process self-certification.
Required fix:  (a) Add an eighth domain to AGENT_LOOP.md §2.3: "**R-DOC** — documentation and claim
               accuracy: README/public claims vs the experiment log, unbundling, limitations, prior
               art." Re-point DOC-01…DOC-05's *Verify* to "R-DOC (+ adversarial reviewer at the
               gate)", and update EP §12's Documentation-accuracy row's Reviewer cell to R-DOC.
               (b) Re-point PROC-02 and PROC-06's *Verify* to "adversarial reviewer, from the records
               in docs/reviews/; orchestrator supplies the audit trail but does not set the status".
Change:        AGENT_LOOP.md, RELEASE_RUBRIC.md, EVALUATION_PLAN.md §12.
```

```
ID:            CONS-020
Severity:      HIGH
Rubric:        PROC-04 (and DISC-02, RANK-02, which depend on it)
Location:      RELEASE_RUBRIC.md:1128-1136; EVALUATION_PLAN.md §8 (baselines A/A′, B, C, D, E-matched,
               E-generous, F(±1/±2/±5)); ARCHITECTURE_DECISION.md B.9
Reproduction:  Read PROC-04's inventory against EP §8's and against RANK-02's "the two controls are
               permanent harness fixtures alongside the baselines (PROC-04)".
Expected:      PROC-04 is the criterion that keeps every comparison runnable.
Actual:        PROC-04 lists "full-thread dump, fixed oldest-K/newest-K, plain message-level search,
               the hosted or labeled-reconstructed preview baseline, and the strong-agent-with-
               primitives baseline". It omits **Baseline F(±N)** — the SC §6 hit-centred baseline that
               DISC-02 is entirely built on — and RANK-02's **recency-ordered and seeded-random
               controls**, which name PROC-04 as their home. As written, the one baseline the
               correction explicitly demands need not be runnable at the gate.
Required fix:  Extend PROC-04's acceptance to "Full-thread dump (B), fixed oldest-K/newest-K (C),
               plain message-level search (D), the hosted or labelled-reconstructed preview (A/A′),
               the strong-agent-with-primitives arms (E-matched and E-generous), **Baseline F(±1/±2/±5)
               (SC §6)**, and RANK-02's **recency and seeded-random ordering controls** all execute and
               produce metric rows in the current gate run."
Change:        RELEASE_RUBRIC.md.
```

```
ID:            CONS-021
Severity:      HIGH
Rubric:        none — four contract clauses have no criterion
Location:      PRODUCT_CONTRACT.md B-04 (:470), B-05 (:472), H-03 (:497), H-07 (:506)
Reproduction:  grep the rubric for "trained router", "attachment content", "minimum proof".
Expected:      Contract §0: "Every MUST has at least one rubric criterion"; AGENT_LOOP §10.7 makes the
               §58 bundle a release-gate condition.
Actual:        **B-05** (no trained router — an SC §9/§15 settled principle) has no criterion; nothing
               would catch a learned policy appearing in the server. **B-04** (attachments metadata
               only; no extraction path) is mentioned only inside GMAIL-01/E2E-01 smoke lists. **H-03**
               (the seven-item §58 minimum-proof bundle) is covered piecewise by EV-05, EV-02, EV-06,
               PROC-04, PERF-01/02, MCP-07 and DOC-02, but no criterion asserts the bundle is complete
               before the sentence "MailWeave fixes the Gmail MCP problem" may be written. **H-07**
               (negative results published) is enforced only for the semantic path (SEM-05).
Required fix:  Add to RELEASE_RUBRIC.md §20/§14: "**SEC-08 · No learned routing policy · M**. No model
               weights, training code or learned scorer participates in routing; routing is
               deterministic/heuristic (contract B-05, SC §9). Verify R-ARCH by code read + CI grep."
               "**DOC-06 · §58 minimum-proof bundle · M**. Before any 'fixes the Gmail MCP problem'
               claim, all seven CTX §58 items exist as experiment-log entries; the claim→item map is
               published (contract H-03)." Extend DOC-01's acceptance with "every rejected capability
               has a published negative result with its numbers (contract H-07)". Extend B-04's
               coverage by adding "no attachment-content extraction path is reachable from any tool" to
               SEC-02's acceptance.
Change:        RELEASE_RUBRIC.md.
```

```
ID:            CONS-014
Severity:      HIGH
Rubric:        INJ-03, INJ-01
Location:      ARCHITECTURE_DECISION.md §C row T-SN3 ("Embedding-bait and keyword-stuffing fixtures
               are added to the I1 suite"); SECURITY_NOTES.md addendum §5.3; EVALUATION_PLAN.md §5.1
               fixture classes, §4.7
Reproduction:  grep EVALUATION_PLAN.md for "embedding bait", "keyword stuffing". No hits.
Expected:      T-SN3's resolution rests on fixtures that assert a bait message "does not dominate
               results and that its selection reason is visible" — the standing consequence of putting
               semantic retrieval on the default path.
Actual:        The fixture class is named in ARCHITECTURE and SECURITY_NOTES but exists in no EP
               inventory, so INJ-03's fixture set (body/subject/display-name/filename/hidden-HTML) does
               not include the attack the local semantic default introduces.
Required fix:  Add to EVALUATION_PLAN.md §5.1: "**I1-bait** — embedding-bait and keyword-stuffing
               fixtures: a message crafted to score highly against many queries. Assertions: it does
               not displace true evidence from the disclosed prefix (paired against the same corpus
               without it), its selection reason and `model_id@revision` are visible, and it is neither
               dropped nor unfenced." Cite it from RELEASE_RUBRIC.md INJ-03's acceptance.
Change:        EVALUATION_PLAN.md (primary); RELEASE_RUBRIC.md INJ-03 (secondary).
```

### MEDIUM

```
ID:            CONS-023
Severity:      MEDIUM
Rubric:        PART-01, PART-02
Location:      PRODUCT_CONTRACT.md R-05; RELEASE_RUBRIC.md:546-561; EVALUATION_PLAN.md:797-812;
               ARCHITECTURE_DECISION.md D.2
Reproduction:  Compare `stated_total` (contract/rubric/architecture) with `claimed_total` (EP P1/P1a,
               O2).
Expected:      One name, or an explicit mapping.
Actual:        Two names for the same quantity across the measurement boundary, with no statement that
               the extraction adapter normalises one to the other. Since PART-01 is scored "via the
               frozen extraction adapter", the mismatch is exactly where an adapter bug hides.
Required fix:  Canonical: **`stated_total`** in the response schema (contract R-05, architecture D.2);
               `claimed_total` is the harness-normalised field name. State the mapping once in EP §6.2
               ("`claimed_total` := the response's `stated_total`") and once in the rubric's How-to-use.
Change:        EVALUATION_PLAN.md, RELEASE_RUBRIC.md.
```

```
ID:            CONS-024
Severity:      MEDIUM
Rubric:        ROUTE-03, RANK-03 (cited as T-RC3's settlement; neither mentions the fields)
Location:      ARCHITECTURE_DECISION.md §C row T-RC3, D.2 (`asked_for`, `constraint_coverage`)
Reproduction:  grep the rubric for "asked_for" or "constraint_coverage". No hits.
Expected:      A tension resolved by a response-format commitment needs a criterion that checks the
               format.
Actual:        T-RC3's whole resolution — "every message carries … a `constraint_coverage` field naming
               which of the user's own constraints it satisfies" plus the `asked_for` block — is
               required by nothing and tested by nothing.
Required fix:  Extend LEX-02's acceptance: "…and every response carries an `asked_for` block
               (parsed constraints, enforced, dropped-with-reason, `term_coverage`,
               `constraint_drop_depth`), and every disclosed message carries `constraint_coverage`
               naming which parsed constraints it satisfies (T-RC3)." Alternatively fold into PART-07
               from CONS-008.
Change:        RELEASE_RUBRIC.md.
```

```
ID:            CONS-026
Severity:      MEDIUM (claim discipline, CTX §58 / contract H-01)
Rubric:        DOC-01
Location:      PRODUCT_CONTRACT.md:506-508 (H-07); cf. ARCHITECTURE_DECISION.md §G, which writes the
               same example as "+x recall, +y ms p95"
Reproduction:  Read H-07's parenthetical: (e.g. "semantic index rejected: +2.1 recall, +80% p95").
Expected:      No measured-sounding number anywhere in the document set that was never measured;
               DOC-01 makes an unmapped number a BLOCKER at the gate.
Actual:        The contract carries a quotable, specific, entirely invented pair of numbers inside
               quotation marks in the very clause about publishing measurements. The architecture,
               writing the same example, correctly uses placeholders.
Required fix:  Replace with placeholders: (e.g. "semantic index rejected: +x points recall, +y % p95").
Change:        PRODUCT_CONTRACT.md.
```

```
ID:            CONS-027
Severity:      MEDIUM
Rubric:        MCP-01
Location:      SECURITY_NOTES.md §5 ("Current stable spec revision is **2025-11-25**; a 2026-07-28
               release candidate exists") and its "could not verify" list ("All normative citations
               here are to the stable 2025-11-25 revision"); CONTEXT_DISCLOSURE_OPTIONS.md §1
               ("Verified against the 2025-06-18 spec … a 2026-07-28 release candidate exists");
               vs VERIFIED_RESEARCH.md §7 and RETRIEVAL_OPTIONS.md §4.1 ("Current MCP spec revision is
               2026-07-28"), PRODUCT_CONTRACT.md N-MCP-1, RELEASE_RUBRIC.md MCP-01
Reproduction:  Read the four documents' spec-status sentences side by side.
Expected:      One spec status. The contract mandates conformance to 2026-07-28 and the rubric gates on
               it.
Actual:        Two research documents still describe 2026-07-28 as a release candidate and anchor their
               normative citations to an older revision; neither addendum corrects this, although both
               addenda were written after VR re-verified the revision. A reviewer using SN or CD as the
               protocol reference would check the wrong revision's rules (e.g. sessions, elicitation).
Required fix:  Add one line to each addendum's "Facts that survive untouched": "**Superseded fact:**
               spec revision 2026-07-28 is the current revision (VR §7, RO §4.1, re-verified
               2026-08-30); citations in the body to 2025-06-18/2025-11-25 as 'current' are historical.
               Nothing else in this document's protocol analysis changes."
Change:        SECURITY_NOTES.md and CONTEXT_DISCLOSURE_OPTIONS.md (addendum sections only — bodies are
               preserved by design).
```

```
ID:            CONS-028
Severity:      MEDIUM
Rubric:        STR-02 (M) depends on INJ-05 (O)
Location:      RELEASE_RUBRIC.md:269-277 (STR-02 *Verify*: "R-SEC confirms display-name/address
               separation (INJ-05)"); :894-902 (INJ-05, flag `O`)
Reproduction:  Read STR-02's verification requirement against INJ-05's optional flag.
Expected:      A mandatory criterion's evidence cannot depend on a criterion that "never blocks".
Actual:        If INJ-05 is skipped (its flag permits it), STR-02's stated verification cannot be
               performed as written, though address-keyed participant matching is a contract MUST
               (C-02b).
Required fix:  Either promote INJ-05 to `M` (its content — split identity fields, `reply_to_differs`,
               `Authentication-Results` as receiver-recorded data — is required by C-02b and SN §7.2
               anyway), or move the display-name/address separation assertion into STR-02's own
               acceptance and leave INJ-05 optional for the spoofing fixture only. Recommend promoting
               INJ-05 to `M` and correcting the totals line (102→103 `M`, 2→1 `O`).
Change:        RELEASE_RUBRIC.md.
```

```
ID:            CONS-030
Severity:      MEDIUM
Rubric:        PART-05, DISC-06
Location:      PRODUCT_CONTRACT.md §5.1 (thread_map row: "every message of the thread as at least a
               stub row"); ARCHITECTURE_DECISION.md D.4 (9,000-token hard ceiling; stub row ≤40 tok)
               and A.9(6)/T-CD1 (segment map)
Reproduction:  Arithmetic: a 500-message thread at ≤40 tokens/stub is ~20,000 tokens against a 9,000
               token ceiling.
Expected:      Contract obligations must be satisfiable under the architecture's own budgets.
Actual:        Contract §5.1 admits no collapsing, while PART-05 does ("collapsed stub runs are
               themselves declared with an expansion affordance") and the architecture relies on
               collapsing plus a segment map. The contract row is the only one of the three that a
               conforming large-thread response violates.
Required fix:  Amend contract §5.1's thread_map row to "every message of the thread as at least a stub
               row, **or inside a declared collapsed run carrying an expansion affordance** (R-06)."
Change:        PRODUCT_CONTRACT.md.
```

```
ID:            CONS-031
Severity:      MEDIUM
Rubric:        none — the LR rung is required by no clause and tested by no criterion
Location:      ARCHITECTURE_DECISION.md D7 ("a 2-unit recency rung ships on recency-cued queries
               regardless of the MF outcome"), A.7 row LR, D.9
Reproduction:  grep the rubric and contract for "recency rung" / "history.list rung". Only FRESH-03
               (stamps) and FRESH-02 (conditional mitigation) exist.
Expected:      Components either serve a clause or are declared experimental with a gate (E.2 does this
               for five other items; LR is not among them).
Actual:        LR ships unconditionally and unmeasured. It also partly pre-empts FRESH-02's trigger:
               shipping a reconciliation rung *before* the freshness measurement risks making the
               measured lag a property of the mitigation rather than of Gmail, which is exactly the
               confound EP §11's arm separation exists to avoid.
Required fix:  Either (a) move LR into ARCHITECTURE §E.2 with its gate ("removed if the freshness
               protocol shows no recency-query benefit"), and add an EP arm that runs the freshness
               protocol with LR **off** for the MailWeave arm so MF6 measures the server, not the
               mitigation; or (b) add a contract clause under C-09 requiring a recency reconciliation
               path on recency-cued queries plus a rubric criterion testing it. Recommend (a).
Change:        ARCHITECTURE_DECISION.md and EVALUATION_PLAN.md §11.1 (arm definition).
```

```
ID:            CONS-032
Severity:      MEDIUM
Rubric:        PROC-01, PROC-02, PROC-06
Location:      RELEASE_RUBRIC.md:1104-1152; AGENT_LOOP.md §2.1, §6
Reproduction:  Read the *Verify* fields against AGENT_LOOP §6 ("The status table … is updated by the
               orchestrator from reviewer reports only").
Expected:      "No agent may certify its own work" (AGENT_LOOP §1) applied to process criteria too.
Actual:        The orchestrator both maintains the status table and certifies the criteria that audit
               the status table's integrity (PROC-01), the no-self-certification rule (PROC-02) and the
               adversarial pass (PROC-06). See also CONS-019.
Required fix:  As CONS-019(b): the adversarial reviewer certifies PROC-01/02/06 from the records; the
               orchestrator supplies the audit trail. Record the transition with both IDs.
Change:        RELEASE_RUBRIC.md.
```

```
ID:            CONS-033
Severity:      MEDIUM
Rubric:        cross-cutting (see §5 for the full drift table and canonical names)
Location:      §5 of this audit
Reproduction:  §5.
Expected:      One name per concept across the set.
Actual:        Eight concepts carry two or three names, including two that collide semantically
               ("Tier 1" = execution mode in preserved EP text vs reality substrate in Rev-2; "L7" =
               semantic rung in ROUTING_OPTIONS vs disclosure assembly in ARCHITECTURE).
Required fix:  Apply the canonical names in §5's table; the two collisions (Tier-n, L-n) are the ones
               that can cause a reviewer to test the wrong thing and should be fixed first.
Change:        as listed per row in §5.
```

### LOW

```
ID:            CONS-029 · LOW · Rubric: NFR-04
ARCHITECTURE_DECISION.md B.6 cites "NFR-08", which does not exist (contract clause is N-08; rubric
criterion is NFR-04). Fix: "…for contract N-08 / rubric NFR-04." Change: ARCHITECTURE_DECISION.md.
```

```
ID:            CONS-034 · LOW · Rubric: GMAIL-05
GMAIL-05 says the published quota table "is internally disputed — RO F7 flags a ~10× discrepancy",
while ARCHITECTURE PF-3's failure branch says "~4× tighter". Both are in RETRIEVAL_OPTIONS (F7's ~10×
is bulk-index feasibility; the addendum §6.9's ~4× is the semantic-pool ceiling). Fix: in GMAIL-05 say
"a disputed table whose resolution moves the semantic-pool ceiling ~4× and bulk-index feasibility ~10×
(RO F7; RO addendum §6.9)". Change: RELEASE_RUBRIC.md.
```

```
ID:            CONS-035 · LOW · Rubric: REG-01…REG-04
The §18 header cites "AGENT_LOOP §7.2", which is the read-the-test rule; the regression-test
obligations live in §7.2 (test quality) and §9 (records/closing evidence). Fix: cite "AGENT_LOOP §7.2,
§9". Change: RELEASE_RUBRIC.md.
```

```
ID:            CONS-036 · LOW · Rubric: AD-02
ARCHITECTURE A.7's L1 stop rule is "hit_count∈[1,5] ∧ coverage=1 ∧ drop_depth=0"; D.3 rule 2 adds
"∧ answer_type_presence". Internal inconsistency in the same document. Fix: add the conjunct to A.7.
Change: ARCHITECTURE_DECISION.md.
```

```
ID:            CONS-037 · LOW
ARCHITECTURE §C row T-RC2 says the plausible-but-wrong-lexical family is "currently under-represented"
in EP. EP Rev-2 §4.7 added F11 (n=10) and F12 (n=10) for exactly this. Fix: "…addressed by EP §4.7
F11/F12; the trigger ablation is still missing (CONS-016)." Change: ARCHITECTURE_DECISION.md.
```

```
ID:            CONS-038 · LOW · Rubric: DISC-06
SECURITY_NOTES §10 P4 ("rate limiting / per-call size ceilings on tool responses; spec 'servers MUST
rate limit'") has no contract clause and no criterion; DISC-06 covers only the size ceiling. Fix: add
"…and the server enforces a documented request-rate limit (SN §10 P4; MCP spec)" to DISC-06 or to
N-07's new criterion (CONS-018). Change: RELEASE_RUBRIC.md.
```

```
ID:            CONS-039 · LOW
EVALUATION_PLAN.md §6.1 (preserved verbatim) reads "the driver issued for the case (Tier-1 driver
policies fix the maximum, §6.1)" — a self-reference, and "Tier-1" here means the Rev-1 execution mode,
now M1, colliding with Rev-2's Tier 1 = reality substrate. Fix: "(M1 driver policies fix the maximum,
§10.1)", with a preserved-block footnote. Change: EVALUATION_PLAN.md.
```

```
ID:            CONS-040 · LOW
EVALUATION_PLAN.md §12 is keyed to SC §16 *areas* because "its criterion IDs are not knowable here".
The rubric now exists with stable IDs. Fix: re-key §12's rows to criterion IDs (or add an ID column),
so "which measurement moves which criterion" is literal rather than approximate. Change:
EVALUATION_PLAN.md.
```

---

## 4. Numeric and factual agreement

Facts cited by two or more documents were checked pairwise. **Agreements** (no action) are listed as
briefly as the check allows, because their absence from a finding list is itself a claim.

| Fact | Values found | Locations | Verdict |
|---|---|---|---|
| Gmail quota units | `messages.list` 5, `messages.get` 20, `threads.get` 40, `history.list` 2 | RO F7; CD §1; ARCH A.5/D8/A.7; EP §3.2.7; contract T-2 | **Agree** |
| Per-user rate limit | 6,000 u/min/user/project | RO F7; CD §1; ARCH A.5; EP §3.2.7 | **Agree** (EP notes older 15,000 material; treats 6,000 as planning truth — consistent with RO's flag) |
| Other seeding costs | insert 25, import 25, modify 5, delete 10, batchDelete 50, labels.create 5, send 100, threads.list 10 | EP §3.2.7; CD §1 (threads.list 10) | **Agree** |
| Quota-table dispute magnitude | "~10×" (bulk indexing) vs "~4×" (pool ceiling) | RO §1 F7 vs RO addendum §6.9 / ARCH PF-3 / rubric GMAIL-05 | **Both true, differently scoped** — rubric wording is misleading (CONS-034) |
| HTTP batch limits | hard 100/batch, >50 not recommended, batch of *n* = *n* quota | RO F5; ARCH A.5; rubric GMAIL-05 | **Agree** |
| `resultSizeEstimate` | an estimate, never a stated count | RO F1; RT §1; VR §4.1; ARCH A.5; rubric GMAIL-04 | **Agree** |
| Gmail `q` semantics | message-scoped; no thread operator; unusable under `gmail.metadata` | RO F2/F3/F8; VR §4.1; SN §1; contract C-01/N-04; ARCH A.6/E.4 | **Agree** |
| `threads.get` | whole threads only, no intra-thread pagination; quota is per method, not per format | RO F4; CD §1/§8; ARCH A.5/T-2 | **Agree** |
| `historyId` expiry | invalid/expired → HTTP 404 → full resync; "typically ≥1 week, rarely hours" | RO F6; VR §4.4; ARCH D.9; contract C-09; rubric FRESH-03 | **Agree** |
| OAuth Testing-status token life | 7 days | RO F8; SN §2; EP §3.2.9; ARCH A.4/B.9/T-SN4; rubric GMAIL-06 | **Agree** |
| Scope required for teardown | `https://mail.google.com/` only, harness-only, account-pinned | SN §1/§2.5; EP §3.2.8-9; SC A.2; contract N-04; ARCH B.9; rubric SEC-03 | **Agree** |
| Host output cap | Claude Code 25,000 tokens default, 10,000 warning, `_meta` raise ≤500,000 chars | CD §1/§8; ARCH D.4/T-CD1/PF-6; contract R-10 | **Agree**; ARCH's 9,000-token ceiling is declared [DESIGN] and set by PF-6 |
| MCP spec revision | 2026-07-28 (VR, RO, contract, rubric, ARCH) vs "RC; stable is 2025-11-25" (SN) vs "verified against 2025-06-18" (CD) | see CONS-027 | **Mismatch** (CONS-027) |
| Sampling | deprecated in 2026-07-28 (SEP-2577), never supported on Claude surfaces | VR §7; RO §4.1; RT §4.1b; contract N-MCP-1; rubric MCP-01; ARCH E.4 | **Agree** |
| Hosted connector preview | ~5 oldest messages per thread, no truncation marker, vendor-documented | VR §0.1/§3.4; contract §2; ARCH G | **Agree** |
| `get_thread` truncation | reported (#239), unverified, PF-1 blocking | VR §6.1/§11.2/T-VR3; contract T-3; ARCH T-3/PF-1; rubric GMAIL-03 | **Agree** on the fact; **PART-01 does not honour it** (CONS-004) |
| Local model facts | potion-retrieval-32M: 32.3M params, MIT, ungated, MTEB Retrieval 35.06 vs MiniLM 42.92 (81.69%); Qwen3-Embedding-0.6B Apache-2.0, 32K ctx; EmbeddingGemma 308M, gated | RO §5.1; ARCH B.2/D.5 | **Agree**, including the "EdgeTPU not CPU" caveat on the 15 ms figure |
| MCP SDK versions | TS `@modelcontextprotocol/server` 2.0.0 (2026-07-27); Python `mcp` 2.1.1 (2026-08-25) | RO §4.4; ARCH B.3/B.4 | **Agree** |
| Seeding mechanics | `insert` + `internalDateSource=dateHeader`; threading needs matching References/In-Reply-To/Subject; ~100-message conversation ceiling unverified (S6) | EP §3.2; SN §9; ARCH B.9 | **Agree** |
| Freshness protocol size | N ≥ 30 per stratum, ≥5 days, ≥3 times of day | EP §11.1/§13.4; rubric FRESH-01 (as [PRE-REG]) | **Agree on value**; class mismatch (CONS-017) and strata omitted (CONS-012) |
| MailWeave-vs-direct-API gap | 60 s | EP MF6; ARCH D.9; rubric FRESH-02 | **Agree on value**; trigger set differs (CONS-010) |
| Partiality bars | 0.98 / 0.95 (EP) vs 100% / 0 (rubric) for the same assertions | EP §13.4 CG-PD; rubric PART-02/03 | **Mismatch** (CONS-011) |
| Semantic improvement bar | "+15 points" (rubric SEM-01) vs deleted (EP §13.5) | see CONS-015 | **Mismatch — retired number in use** |
| Position sweep | 7 positions across a ~100-message thread; recall ≥0.98 / ≥0.95 per position / spread ≤0.05 | EP §4.4, §13.4 CG-EP; rubric EV-02 | **Agree on values**; citation stale (CONS-009) |

**Claim-discipline sweep (CTX §58, contract §8).** Three defects, all listed above: the retired +15
bar in SEM-01 (CONS-015); the invented "+2.1 recall, +80% p95" example in contract H-07 (CONS-026);
and the rubric's blanket `[PRE-REG]` marking, which obscures which numbers are genuinely unregistered
(CONS-017). No document was found bundling representation omission with freshness or semantic
retrieval: contract §2, EP §0 rule 3 and §11.2.5, ARCH §G and rubric DOC-02 all keep them separate,
and the architecture's `[VERIFIED] / [DESIGN] / [PRE-REG] / [TBM]` number discipline holds throughout
§§A–D. No case was found of a PRE-REG threshold quietly filled with an invented value; the failures
run the other way (a retired bar reinstated, and settled bars mislabelled as unregistered).

---

## 5. Terminology drift and canonical names

| # | Concept | Names in use | Canonical recommendation | Where to edit |
|---|---|---|---|---|
| 1 | Tool names | contract «search_mail» / «thread_map» / «get_messages» / «get_attachment»; ARCH `mailweave_search` / `mailweave_thread_map` / `mailweave_get_messages` / `mailweave_get_attachment`; RO §2 sketches `search` / `fetch_evidence` / `expand` | **`mailweave_*` (ARCH D.1)** — the contract itself assigns naming to architecture | Add one line to contract §5.1: "Names are now fixed by ARCHITECTURE_DECISION D.1; the provisional forms below are retained only to show the obligation each name carries." |
| 2 | Content depth vocabulary | contract R-04 "stub / snippet / cleaned body / full body / raw"; ARCH `stub\|snippet\|body_clean\|body_full\|raw`; rubric "a closed set" (unnamed) | **`stub / snippet / body_clean / body_full / raw`** | contract R-04 (use the tokens); rubric DISC-03 (name the set) |
| 3 | Role vocabulary | contract R-02 and ARCH D.2: 7 values; EP §6.2 P4: 3 values (matched/context/derived) | **The 7-value closed set** | EP §6.2 P4 (CONS-008) |
| 4 | Reason field | CD §5 `role_reason`; contract R-03 / ARCH D.2 `reason`; EP §7.5 "the *reason* a message was included" | **`reason`** (with `role` as its sibling) | CD is preserved-by-design; note the mapping in EP §7.5 |
| 5 | Total-count field | `stated_total` (contract/rubric/ARCH) vs `claimed_total` (EP P1/P1a, O2) | **`stated_total`** in the wire schema; `claimed_total` only as the adapter-normalised name, stated explicitly | CONS-023 |
| 6 | Handle terminology | contract "map handle / server-minted handle / cursor"; ARCH `map_id`; CD `map_id`; EP P3 "cursor / named tool / explicit flag" | **`map_id`, a server-minted handle**; drop "cursor", which no design produces | contract N-MCP-2 and §5.1; EP §6.2 P3 |
| 7 | Ladder rung labels | RT §5.2 and its addendum: L0–L3 cheap, **L7 = semantic**; ARCH A.7: L0–L3 lexical, **L4 structural, L5 semantic, L6 ranking, L7 disclosure**, plus **LR** recency | **ARCH A.7's numbering** — a genuine collision: "L7" means two different rungs | one line in the ROUTING_OPTIONS addendum: "rung numbering is superseded by ARCHITECTURE A.7; this document's L7 is A.7's L5" |
| 8 | Tier / loop / gate names | SC, contract and rubric: "Loop 0 / Loop 2 / Loop 3 / Loop 6", "Tier-1 driver"; EP Rev-2: **G0** + **CG-EP/CG-PD/CG-AD/CG-SEM/CG-STR/CG-RANK/CG-FRESH/CG-REG/CG-REAL**, execution modes **M1/M2**, and **Tier 1/2/3** = reality/controlled/regression substrates; ARCH: "Loop 0" + PF-1…PF-12 + CG-* | **Substrates = Tier 1/2/3; execution modes = M1/M2; gates = G0 + CG-\*; preflight = PF-n.** "Loop N" survives only as the round-loop of AGENT_LOOP §5 | rubric (every "Loop n" → the gate name), contract C-09 ("Loop 6 protocol" → "the CG-FRESH protocol, EP §11"), EP §6.1 (CONS-039), ARCH (PF-n retained, "Loop 0" → "G0 preflight") |
| 9 | Coverage field | contract/RT `query_term_coverage`; ARCH D.2 `asked_for.term_coverage`; rubric LEX-02 `query_term_coverage` | **`term_coverage`** inside `asked_for`, with the long name retired | ARCH D.2 keeps it; rubric LEX-02 and contract C-04 note the location |
| 10 | Reviewer domains | AGENT_LOOP §2.3 seven domains; rubric additionally uses "orchestrator" and "adversarial reviewer" as verifiers; no documentation domain | **Eight domains incl. R-DOC**, plus the adversarial reviewer as an attacker that may certify only process criteria | CONS-019 |

---

## 6. Verdict

### Safe to proceed to implementation planning?

**No — not until the eight BLOCKERs are closed.** The set is unusually coherent for its size: the
architecture resolves all 22 tensions, the rubric's structure is sound and self-auditing, and every
load-bearing external fact that two documents share agrees. But four mandatory criteria are
**unsatisfiable or unmeasurable as written** (SEC-07/SEM-02 egress, EV-01/I-1's hit set, PART-01's
manifest equality, DISC-05's missing measurement), one criterion **licenses the exact scope reduction
the authoritative document forbids** (DISC-02), one reinstates a **deleted conditional gate and a
retired number** (SEM-01), half of the contract's own six-field minimum conformance contract has
**no criterion at all** (R-02/R-03), and the evaluation plan specifies a forensic mechanism that
**violates binding owner direction A.3** and contradicts the architecture (EP §2.4.6). Implementation
started against this set would build to a rubric a reviewer could not honestly pass, and would ship a
privacy mechanism the owner did not authorise.

Note that four of these were already raised by ARCHITECTURE §H (H-1 DISC-02, H-2 PART-01, H-4 SEC-07,
H-5 I-1) as owner escalations under AGENT_LOOP §8. They remain open: the architecture flagged them and
built to its own reading, which means the code and the rubric would currently disagree by design. That
is precisely the state AGENT_LOOP §8 says must not be self-resolved, so these need an owner decision
recorded in the findings ledger, not just an edit.

**Counts:** 8 BLOCKER · 15 HIGH · 9 MEDIUM · 8 LOW (40 findings).
**Documents needing edits** (a finding may touch more than one): RELEASE_RUBRIC.md (27),
EVALUATION_PLAN.md (13), ARCHITECTURE_DECISION.md (7), PRODUCT_CONTRACT.md (5), SECURITY_NOTES.md (2),
AGENT_LOOP.md (1), CONTEXT_DISCLOSURE_OPTIONS.md (1), ROUTING_OPTIONS.md (1, via §5 row 7).
`SCOPE_CORRECTION.md` needs none.

### Ordered repairs required before implementation planning

**Gate 1 — owner decisions (cannot be made by an agent; AGENT_LOOP §8).**
1. **CONS-004** PART-01 completeness semantics (ARCH §H-2's escalation). Decide now, not after PF-1.
2. **CONS-001** DISC-02 (ARCH §H-1). Confirm that a fixed-±2 win is a tuning input, never a scope
   reduction.
3. **CONS-003** I-1's `H` (ARCH §H-5). Confirm the shortlist reading plus declared-pool disclosure.
4. **CONS-005** the forensic buffer: confirm that A.3 permits no unredacted body at rest, and that
   `mailweave inspect` is the only forensics path (EP §14 Q17 closes as "no buffer").

**Gate 2 — edits that unblock the rubric (mechanical once Gate 1 lands).**
5. **CONS-002** egress allowlist wording in four documents.
6. **CONS-015** SEM-01: strike the entry condition and the retired +15 bar.
7. **CONS-008** add PART-07 (role + reason presence); fix RANK-03's guard; widen EP P4.
8. **CONS-006** add the depth-level measurement to EP; point DISC-05 at it.
9. **CONS-009** re-cite all 35 EP references to Revision-2 numbering.
10. **CONS-017** re-mark the 21 brackets as DEFINITIONAL / INHERITED / UNSET.

**Gate 3 — coverage repairs (before the first gate run, not before coding starts).**
11. **CONS-010, CONS-012** freshness: MF1–MF6 trigger set, depth strata, two mailboxes, FSL criterion.
12. **CONS-013, CONS-021, CONS-018, CONS-020** the remaining orphans: SEM-06 (provenance + pool),
    FRESH temporal-partiality, SEC-08 (no learned router), DOC-06 (§58 bundle), N-07 transport,
    PROC-04's baseline inventory.
13. **CONS-007, CONS-016, CONS-014** the three missing measurements: F17 decision-reversal,
    the escalation-trigger ablation, the embedding-bait fixtures.
14. **CONS-022** GMAIL-07 (reality-tier oracles) so SC §13's methodology is gate-enforced.
15. **CONS-025** name the content-processing components in ARCHITECTURE §D.
16. **CONS-019, CONS-032** add R-DOC to AGENT_LOOP; re-point DOC-* and PROC-01/02/06.
17. **CONS-011, CONS-023, CONS-024, CONS-028, CONS-030, CONS-031** the remaining MEDIUMs.

**Gate 4 — hygiene.** CONS-026, CONS-027, CONS-033 (§5 drift table, starting with the two collisions),
and the eight LOWs. None blocks implementation; all should land before the first release gate, because
each is a place a reviewer could be sent to the wrong evidence.

**What does not need to change.** `SCOPE_CORRECTION.md` (authoritative and internally consistent);
the five research bodies (correctly preserved, with their addenda doing the scope work);
`ARCHITECTURE_DECISION.md`'s capability set, tension table, stack decision and Loop-0 preflight;
`AGENT_LOOP.md` apart from the missing R-DOC domain; and every external fact in §4's agreement table.
