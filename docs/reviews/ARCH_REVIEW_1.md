# ARCH_REVIEW_1.md — Adversarial review of `ARCHITECTURE_DECISION.md`

**Reviewer:** adversarial reviewer (`AGENT_LOOP.md` §2.4), fresh instance.
**Target:** `docs/ARCHITECTURE_DECISION.md` (866 lines), pre-approval.
**Date:** 2026-08-30.
**Brief:** defeat the architecture before the owner approves it. Findings use the `AGENT_LOOP.md` §4
schema. Ranked BLOCKER → HIGH → MEDIUM → LOW.
**Verdict:** **NEEDS REWORK.** See §4.

---

## 0. Execution record

Per `AGENT_LOOP.md` §4 ("a reviewer reporting no findings must still state what it executed and what
it read"), and because this review's substance is arithmetic rather than test execution.

### 0.1 Read in full

- `docs/ARCHITECTURE_DECISION.md` — all 866 lines (§0 decision summary, §A system architecture,
  §B stack, §C tension table, §D design commitments, §E chosen/deferred/rejected, §F Loop-0 preflight,
  §G falsifiability, §H owner flags).
- `docs/SCOPE_CORRECTION.md` — all sections, incl. §§3–7, §10–§15, Appendix A.1–A.3.
- `docs/PRODUCT_CONTRACT.md` — all sections; §3 C-01…C-11, §4 I-1…I-4, §5.2 R-01…R-10, §5.3, §5.4,
  §6 N-01…N-08, §7 B-01…B-06, §8 H-01…H-08, §9 T-1…T-5.
- `docs/AGENT_LOOP.md` — all sections; §4 schema and severity table applied verbatim, §7 anti-gaming
  rules applied as the probe method for §3 below.
- `SCOPE CORRECTION ADDENDUM` of `RETRIEVAL_OPTIONS.md` (T-RO1…T-RO4, §5.1–§5.3 local-model
  assessment), `ROUTING_OPTIONS.md` (T-RC1…T-RC3), `CONTEXT_DISCLOSURE_OPTIONS.md` (T-CD1…T-CD3),
  `SECURITY_NOTES.md` (T-SN1…T-SN4), `VERIFIED_RESEARCH.md` (T-VR1…T-VR3).

### 0.2 Read selectively, for criteria the architecture claims are satisfiable or measurable

- `RELEASE_RUBRIC.md`: EV-01…EV-06, LEX-01…LEX-04, STR-01, SEM-01…SEM-05, RANK-01…RANK-04,
  AD-01…AD-05, ROUTE-01…ROUTE-04, DISC-01…DISC-06, PART-01…PART-06, MCP-01…MCP-07,
  GMAIL-01…GMAIL-06, FRESH-01…FRESH-04, PERF-01…PERF-04, SEC-01…SEC-07, INJ-01…INJ-06,
  OBS-01…OBS-04, NFR-01…NFR-04, REG-01…REG-04, E2E-01…E2E-04, DOC-01…DOC-05, PROC-01…PROC-06,
  release gate.
- `EVALUATION_PLAN.md`: §4.3 families F1–F10, §4.4 position sweep, §4.5 paraphrase tiers, §4.6
  distractor taxonomy, §4.7 families F11–F16, §7.1–§7.4 coverage, §12 rubric linkage, §13.3 G0
  entry, §13.4 capability gates CG-EP/CG-PD/CG-AD/CG-SEM/CG-STR/CG-RANK/CG-FRESH/CG-REG/CG-REAL,
  §13.5 exit-criteria changes, §14 open questions.

### 0.3 Re-derived independently (not taken from the document)

Executed as arithmetic against the [VERIFIED] published rates in RO F7 (`history.list` 2,
`messages.list` 5, `messages.get` 20, `threads.get` 40; 6,000 u/min/user/project) and the [DESIGN]
caps in A.7 and D.4. Results used in findings ADV-001/003/004, ADV-105/106/108/109, ADV-201.

| Quantity | Re-derived value |
|---|---|
| L0 worst case | 5 + 5×20 = **105 u** |
| L1 worst case, excluding maps | 5 + 10×20 = **205 u** |
| L1b / L2 / L3 / LR | 15 / 15 / 10 / **2 u** |
| L4 | 4×40 = **160 u** |
| L5 pool maps | 25×40 = **1,000 u** (+2 participant probes = 10 u) |
| Full-ladder worst case, `max_map_threads` read as **global** | **1,362 u** |
| Full-ladder worst case, `max_map_threads` read as **per-rung** (4 + 4 + 25 maps) | **1,682 u** |
| Stated budgets | 1,500 normal / 3,000 semantic-escalated |
| Unbatched logical Gmail calls, full ladder | **61** vs stated `max_gmail_calls = 40` |
| Escalated queries per minute before 429 (6,000 u budget) | **3.6 – 4.4** |
| Message-wise 300-row pool (T-RO2's rejected option) | 300×20 = **6,000 u** = the entire minute budget |
| Semantic pool map, D.2's own example (287 rows × 40 tok stub) | **11,480 tokens** vs the 9,000-token hard ceiling |
| 40-message thread, 6 hits, E2 floor ≈ 18 additional bodies, at CD's 300–800 tok planning range (400 used) | 24 bodies = 9,600 tok + 40 stubs = **11,200 tokens** vs the 9,000-token hard ceiling |
| Same, at D.4's `body_clean` 1,000-tok soft cap | **24,000 tokens** |
| Cost of the "recoverability floor" (L0–L3 + report) | ≈ **510 u** — not stated anywhere in the document |

### 0.4 Method for §3 (gameability)

Applied `AGENT_LOOP.md` §7.5 (degenerate-strategy probe) to the architecture's own commitments rather
than to a metric: constructed the dumbest implementation consistent with every sentence of §A/§D, then
walked it through the rubric's guards. Result in §3.

### 0.5 Not done, and why

- No code executed: there is no implementation yet. Every finding is derived from the document's own
  arithmetic, its cited sources, or a traced control-flow scenario, as the brief requires.
- No live Gmail calls: PF-1/PF-2/PF-3 are the project's own instruments for those facts, and this
  review deliberately does not pre-empt them. Where a finding depends on a preflight outcome it says so.
- `MAILWEAVE_CONTEXT.md` and the archived v0 synthesis were not read in full; §CTX citations were
  taken as transcribed by `PRODUCT_CONTRACT.md`.

---

## 1. Findings

### BLOCKER

---

```
ID:            ADV-001
Severity:      BLOCKER
Rubric:        EV-01 (also EV-03, contract I-1, §5.3)
Location:      ARCHITECTURE_DECISION.md A.7 (rung cost table), A.9, D.2 (`"withheld": []`)
```

**Reproduction.** Query `from:amy launch after:2026/05/01`. L1 executes one `messages.list`. Gmail's
default `maxResults` is 100 (RO F1). Suppose it returns 46 message IDs across 31 threads. A.7 caps L1
at `≤10 × 20 u` of `messages.get`, and A.7's global caps set `max_map_threads = 4` (normal). Trace the
remaining 36 hit IDs through §A. They are not fetched, not mapped, not stubbed, and no rule in the
document routes them anywhere.

**Expected.** Contract I-1: `H` = "the set of message IDs returned by the executed Gmail queries";
`R` = IDs present in the response at any depth **plus** IDs explicitly listed as `withheld` with a
reason and an affordance. `H ⊆ R` on every response. EV-01 makes this an exact set assertion with
violations = **0**, verified by joining trace `H` to parsed response IDs.

**Actual.** The word `withheld` appears exactly once in 866 lines — as an empty array in D.2's schema
sketch. No rung, no budget rule, and no representation rule ever populates it. §A.9's five-tier
allocation covers hits, reply-chain floor, query-scored fill, "everything else **in every touched
thread**", and sibling threads — all scoped to threads that already have a map. Hits in unmapped
threads and hits beyond the per-rung `messages.get` cap fall outside all five tiers. The same defect
recurs at L2 and L3 (relaxation and broadening issue further `messages.list` calls, each returning up
to 100 IDs into `H`, against the same fetch caps) and at D.5 pool step (b), whose `from:`/`to:` probes
are `messages.list` calls whose returned IDs are literally "returned by the executed Gmail queries".

This is not a corner case. It is the *modal* shape of a filtered lexical query, and it is the exact
failure class MailWeave exists to prevent — a retrieval stage identifying a message and a later stage
removing it with no marker.

**Required fix.** Specify, in A.7 and A.9, the disposition of every ID entering `H`:
(a) a `withheld` record — `{id, thread_id, why, affordance}` — is mandatory for every hit not
disclosed at any depth, with `why` naming the specific cap; (b) the response declares its **scan
scope** (pages fetched, `maxResults` used, whether more pages exist) as a first-class field, since
GMAIL-04's own guard requires scan scope to be declared once paging stops; (c) state whether `H` is
defined over *all* pages of an executed query or only the pages fetched, and make the ladder's page
budget explicit. Without (a)–(c) EV-01 cannot pass and the response is non-conforming under §5.3.

---

```
ID:            ADV-002
Severity:      BLOCKER
Rubric:        MCP-06 (also FRESH-03, NFR-03, contract N-03, N-MCP-3)
Location:      ARCHITECTURE_DECISION.md A.10, steps 2–3 and the sentence beginning
               "An in-process LRU may serve step 2…"
```

**Reproduction.** MCP-06's acceptance test verbatim: "mutate the underlying thread, then redeem a
stale handle." Mint `map_id` for thread T. Deliver a new message into T. Redeem `map_id`. Per A.10:
step 2 re-fetches `threads.get`; step 3 recomputes `mapping_digest` and raises `handle_stale` on
mismatch. Now enable the optimisation A.10 explicitly permits — the in-process LRU serves step 2.

**Expected.** MCP-06: an expired/invalid handle errors explicitly and "never silently resolves to
different content than it named." N-03/FRESH-03: no response served from local state without a
truthful staleness stamp.

**Actual.** When the LRU serves step 2, step 3 recomputes the digest **from the cached thread map that
produced the original digest**. The comparison is `digest(x) == digest(x)`. It is true by
construction. `handle_stale` can never fire on a cache hit, so MCP-06's mutate-then-redeem test cannot
fail, and the architecture's own justification — "step 3 always runs, so the cache can never change an
answer" — is a non-sequitur: step 3 can never *detect* a change either. The document presents a
tautology as a verification.

Compounding: A.10 does not say which timestamp the response carries when the LRU serves the fetch. If
`fetched_at` is restamped to now, the response asserts a freshness it does not have (FRESH-03: "no
view of the mailbox is served without stating when it was fetched"; violation count required: 0). If
it carries the cache time, no rule bounds how old that may be — the LRU has no stated TTL, no size,
and no invalidation rule anywhere in the document.

**Required fix.** Either (a) delete the LRU from the handle-redemption path and state that step 2 is
always a live `threads.get`, or (b) keep it and specify: the LRU's TTL, that `fetched_at` is the
*cache-entry* time and never restamped, and a second, independent staleness check that does not
consume the cached artifact — the natural one being `history.list(startHistoryId=handle.history_id)`
at 2 u, which detects thread mutation without re-fetching. Also add a test obligation to A.10 that
MCP-06's mutate-then-redeem case is executed **with the cache warm**, not only cold.

---

```
ID:            ADV-003
Severity:      BLOCKER
Rubric:        PART-05, DISC-06 (also C-06, C-07, contract I-2; defeats T-CD2's sole mitigation)
Location:      ARCHITECTURE_DECISION.md A.9(2), A.9(5), A.7 global caps, D.4 budget ladder,
               C table row T-CD2
```

**Reproduction — case 1 (the floor).** A 40-message thread; 6 lexical hits. A.9(1) puts every hit at
`body_clean`; A.9(2) adds each hit's reply parent and direct children at `body_clean` and declares
this tier "not budget-negotiable"; A.9(4) puts the remaining messages in the map as stub rows. With
~3 floor messages per hit that is 24 bodies plus 40 stub rows. At `CONTEXT_DISCLOSURE_OPTIONS`'s
verified 300–800-token planning range for a cleaned business email (400 used): **11,200 tokens**. At
D.4's own `body_clean` soft cap of 1,000 tokens: **24,000 tokens**. D.4's hard per-response ceiling is
**9,000 tokens**.

**Reproduction — case 2 (the map).** A semantic-escalated query. A.7 sets `max_map_threads = 25` for
the semantic pool and `max_embed_texts = 300`. D.2's own worked example carries
`pool.message_count: 287`. A.9(5) says sibling threads "appear as **separate sources**, each with its
own mini-map", "capped by `max_map_threads`". PART-05 requires that wherever a map is present,
**every** message of that thread appears as at least a stub row. 287 stub rows at D.4's ≤40 tok =
**11,480 tokens** of stubs alone, before a single body.

**Expected.** T-CD2's resolution states the E2 floor is "non-optional and not budget-negotiable" and
is "the only mechanism that can surface an objection the query's wording does not match", with
`Reversed by: —` (nothing). DISC-06 requires MailWeave to author its own truncation at a hard
ceiling. PART-05 requires per-message stub visibility wherever a map is claimed.

**Actual.** The three commitments are arithmetically incompatible on routine inputs. A.9(2)'s own
escape — "the response self-truncates *explicitly* rather than dropping the floor" — is a distinction
without a difference for T-CD2's purpose: the reversing message is equally absent whether it was
dropped or truncated; only the label differs. T-CD2's mitigation therefore fails precisely in the
threads large enough for a decision to be reversed later, which is the case it was written for.
Case 2 additionally reveals that `max_map_threads` carries **two different meanings** in one
document — a disclosure cap (4, governing sources and mini-maps in A.9(5)) and a pool-construction
cap (25, governing D.5's embedding pool). A.9(5) cites the name without saying which.

**Required fix.** (a) Rename the pool cap (`max_pool_threads`) and state explicitly that pool
membership is declared by count in `retrieval_report.pool` and does **not** create a `source` or a
map; (b) state the floor's actual precedence rule under the ceiling — which of {hits at body,
floor at body, floor at snippet, map stubs} degrades first, in order, and what the response says when
it does; (c) amend T-CD2 to state honestly that the floor is budget-bounded and that the reversing
message may be reduced to a stub or truncated, with the declared marker as the only guarantee;
(d) add a reversal criterion to T-CD2 — currently `—` — naming the measurement that would show the
floor is not doing its job.

---

```
ID:            ADV-004
Severity:      BLOCKER
Rubric:        SEM-01, AD-05, EV-04 (also RANK-01, SEM-04, LEX-04, contract I-4, C-05)
Location:      ARCHITECTURE_DECISION.md D.3 stopping rule 1; A.7 rung L0; A.8 (`exact_signal_match`
               listed but never defined); C table row T-RC2
```

**Reproduction.** `exact_signal_match` is the pivot of the entire design: it appears in D.3 rule 1
(stop after L0, "**No** structural, semantic or ranking rung may run"), D.3 rule 4, D.5 ("Fires when
rule 4 holds and `exact_signal_match` is false"), D.7 ("never when `exact_signal_match`"), A.8 (signal
list) and A.7 (L0's stop condition). It is **never defined**. A.7 gives L0's *action* as
"exact-operator query (rfc822msgid, quoted phrase, unique token)" — so "unique token" is in scope, but
no rule says what makes a token unique, what hit count qualifies, or whether the match must be in
subject vs body.

Now trace EP's F11 family — "query whose naive lexical translation matches a confident-looking but
wrong message; the true evidence shares no content words with the query", 10 cases, gate-binding under
CG-SEM. Any F11 query containing a distinctive proper noun ("the Meridian renegotiation") produces a
tier-1 parse with an apparently-unique token. Under any definition of `exact_signal_match` broad
enough to include "unique token", L0 matches the decoy and D.3 rule 1 fires: **stop**. `sufficiency`
never re-runs, `answer_type_presence` — A.8's entire answer to T-RC2, and the document's own words,
"the only pre-escalation signal that can see the confident-but-wrong lexical result" — is never
consulted, because D.3's rules are applied "in order" and rule 1 precedes rule 4.

**Expected.** SC §3: "A wrong first route must not cause a false 'not found.'" I-4: no unrecoverable
false negative. CG-SEM: registered `semantic_gain` bars met **on F11**. EP §4.7's stated purpose for
F11: "Tests escalation *triggering*, not just escalation *capability*."

**Actual.** D.3 rule 1 is an unconditional kill-switch for the whole ladder, gated on an undefined
predicate, and it disables the one mechanism the architecture built to satisfy T-RC2. The
architecture is aware of the failure class — T-RC2's own rationale says "confident-but-wrong is
invisible to pre-escalation signals" — and then hard-codes a rule that guarantees invisibility for
a subclass of it.

This is also the document's largest gameability lever; see §3 below.

**Required fix.** (a) Define `exact_signal_match` normatively: which operators, which hit-count band,
which fields, and require it to be a recorded trace field with its firing inputs. (b) Restrict D.3
rule 1's absoluteness to `rfc822msgid:` (the genuine identity primitive) and to `hit_count == 1`;
for quoted-phrase and unique-token matches, make `answer_type_presence` evaluate **before** the stop,
not after. (c) Add a pre-registered bound on `exact_signal_match` firing rate per family, reported at
G0, so a broad definition is visible as a number rather than hidden behind five criteria it makes
easy.

---

### HIGH

---

```
ID:            ADV-101
Severity:      HIGH
Rubric:        FRESH-01, FRESH-02, FRESH-03 (also C-09, contract T-4)
Location:      ARCHITECTURE_DECISION.md D.9 (LR rung), A.7 rung LR ("2 u"), D7, C table row T-4
```

**Reproduction.** Issue a recency-cued query to a freshly started stdio server. D.9: "on recency-cued
queries, `history.list(startHistoryId)` (2 u) yields `messageAdded` IDs". `startHistoryId` must come
from somewhere. The architecture states: MCP is stateless (A.10), there is no persistent index
(D5/T-RO3), no disk (D5), and B-06 forbids a persistent mail-content store. "Stamps and `historyId`
snapshotting ship day one" (D7) does not say **where the snapshot lives**.

**Expected.** T-4's resolution: "`history.list` polling only… the LR rung ships for recency-cued
queries regardless of the MF outcome," as the answer to SC §12's requirement that a lag mitigation be
*built*.

**Actual.** Three defects, any one of which makes LR inert or mispriced:

1. **No watermark.** With in-process-only state, the first query of a process has no
   `startHistoryId`, and subsequent queries have one only minutes old. The failure LR exists to catch
   is mail delivered *before* the query but not yet in the search index — which requires a watermark
   from before delivery. As designed, LR can only see mail that arrived during the current process's
   lifetime, after a previous query. That is close to never.
2. **The cost model is wrong.** `history.list` returns history records whose `messagesAdded[].message`
   carries id/threadId/labelIds — not headers, not bodies. D.9 then says the IDs are "re-checked
   against the query's constraints client-side," which requires fetching each at 20 u
   (`messages.get`). A.7 prices LR at a flat **2 u**. The true cost is `2 + 20n`.
3. **It reimplements Gmail query semantics.** "Re-checked against the query's constraints
   client-side" is exactly the cost `RETRIEVAL_OPTIONS`'s T-RO3 names as option (b)'s "biggest hidden
   cost — reimplementing Gmail's query semantics", which the architecture cites as a reason to reject
   persistent indexes (E.4) and then silently requires on the LR path. A client-side re-check of
   `from:`, `subject:`, `has:attachment`, stemming and phrase semantics will disagree with Gmail's,
   producing results the response attributes to the user's query that Gmail's `q` would not have
   matched — an R-03/T-RC3 provenance problem as well as a correctness one.

**Required fix.** State where `historyId` persists (a small non-content watermark file is compatible
with B-06 and N-03 and should be named as such, with FRESH-03 stamps and a 404-resync path); correct
A.7's LR cost to `2 + 20n` with an `n` cap; and state precisely which constraint subset is re-checked
client-side, with a rule that any message surfaced by LR carries `reason: "history.list messageAdded;
constraints re-checked locally: [...]"` rather than claiming a Gmail `q` match.

---

```
ID:            ADV-102
Severity:      HIGH
Rubric:        SEM-01, SEM-02 (also PF-2's own failure branch; contract C-03)
Location:      ARCHITECTURE_DECISION.md D.5 "Pool text" paragraph; §F PF-2 failure column
```

**Reproduction.** Assume PF-2 (blocking) resolves as the document itself flags is possible: no
per-message `snippet` under `threads.get(format=metadata)`. Follow the stated consequence: "pool text
degrades to subject + participants and stage B fetches `body_clean` for a shorter shortlist at 20 u
each — **a cost change, not a design change**."

**Expected.** A blocking preflight's failure branch must state the honest consequence, since the whole
point of blocking status is that code must not be built on the assumption.

**Actual.** Both halves of that sentence are wrong.

- *Design change, not cost change.* Stage A is the only thing that decides which 25 of 300 rows reach
  the cross-encoder. Its input would become subject + from/to addresses. SEM-01's bar is measured on
  zero-content-word-overlap paraphrase cases (F4-T2) and on F11. SC §4's own worked example — query
  "postpone the launch", evidence "We'll push go-live into Q4" — is invisible from subject and
  participants. Stage A degrades from a weak retriever to a near-random shortlist selector on exactly
  the family that justifies the rung's existence. That is the semantic capability failing, not
  costing more.
- *The cost is not affordable either.* The stated fallback is body fetches at 20 u. Re-deriving:
  a 300-row pool at 20 u = **6,000 u = the entire per-minute per-user budget** — the precise figure
  `RETRIEVAL_OPTIONS` T-RO2 uses to reject message-wise pool construction, and which the architecture
  itself lists in E.4 as a "pure cost rejection". Shrinking the pool to fit (e.g. 50 rows = 1,000 u)
  shrinks the recall the rung exists to buy, and the document sets no floor on pool size.

**Required fix.** Rewrite PF-2's failure branch to state the real consequence and the real decision it
forces: either (i) a different pool-text source that is verified to exist before build (e.g.
`messages.get(format=minimal)` per row, which must then be costed, or `threads.get(format=full)` at
the same 40 u with a bytes/latency cost rather than a quota cost — the document already establishes
quota is per method, not per format), or (ii) an explicit reduced pool-size bound with the recall
consequence declared in every semantic response per T-RO1. Do not carry "cost change, not design
change" into the build.

---

```
ID:            ADV-103
Severity:      HIGH
Rubric:        none — architecture decision quality (bears on SEM-01, NFR-02, and §B.8's own R1)
Location:      ARCHITECTURE_DECISION.md B.3 ("The gap that decides it"), B.7, B.8 and reversal R1/R2
```

**Reproduction.** B.8 states the decision "turns on one asymmetry that is not a matter of taste: the
two-stage local retrieval shape … **requires a static-embedding tier**, and that tier exists only in
Python." Check that claim against the evidence the architecture says it rests on.

**Expected.** A load-bearing single-criterion stack decision should be supported by the cited source
and by a reversal criterion whose evidence the plan actually collects.

**Actual.** Four problems.

1. **The cited source says "or", the architecture reads "requires."**
   `RETRIEVAL_OPTIONS` addendum §5.3(2), which is the source for the two-stage shape, reads:
   "**Static/tiny embeddings (potion-retrieval-32M class) *or* a small bi-encoder** over the whole
   candidate pool → a cross-encoder reranker over a shortlist." Stage A's requirement is *cheap enough
   for the pool*, not *static*. The architecture converts a disjunction in its own evidence base into a
   necessity, and the entire stack decision rests on that conversion.
2. **The cost it attributes to a Node bi-encoder is the wrong cost.** B.3 says a Node build "would have
   to be replaced by a transformer bi-encoder over the whole pool — the exact cost T-RO2 says we cannot
   afford." T-RO2's arithmetic is about **quota** (300 × 20 u body fetches), and the architecture has
   already eliminated that cost by thread-wise pool construction (T-RO2's own resolution row). The
   remaining cost is CPU, and B.7 states plainly that **no CPU latency figure exists for any candidate
   model on a laptop** and that PF-4 "measures only the chosen stack". The deciding asymmetry is
   therefore an unmeasured claim about the option not chosen, attributed to a source that measured
   something else.
3. **R1 is unfirable.** R1 requires *both* "the static tier does not clear its quality bar" **and** "a
   Node-viable bi-encoder over the same pool meets the latency budget." PF-4 never runs the Node arm
   (B.7, fourth bullet, states nobody has measured it and PF-4 will not). So the second conjunct can
   never be established, and R1 cannot fire regardless of what stage A does.
4. **There is no in-Python fallback that preserves the argument.** If `potion-retrieval-32M` fails its
   pre-registered `recall@shortlist` bar, D.5's stated remedies are the opt-in swaps —
   `Qwen3-Embedding-0.6B`, `EmbeddingGemma-300m` — i.e. transformer bi-encoders, which B.3 verifies
   are available in Node with ONNX q4/q8 and MRL truncation. The moment that swap happens, the sole
   stated reason for Python has evaporated and nothing in the document notices.

Note also the quality headroom the architecture treats as reassuring: potion's MTEB Retrieval **35.06**
against all-MiniLM-L6-v2's **42.92** is an ~18% relative deficit *on retrieval*, in a product whose
release invariant is zero false not-found, with stage A required to place true evidence in the top 25
of ~300 rows.

**Required fix.** Do not reopen the stack on this review's say-so — Python is defensible on other
grounds (single API across static/bi-encoder/cross-encoder, `sentence-transformers` release cadence,
harness ecosystem). Do fix the *argument*, because a reversal criterion that cannot fire is worse than
none: (a) restate B.8's asymmetry as "one API covering all three inference jobs" rather than "the
static tier exists only in Python"; (b) rewrite R1 as a single-conjunct criterion on stage-A quality
alone, with the stated consequence being a **design** change (shortlist widening, pool shrinking, or
bi-encoder stage A) rather than a stack change; (c) add PF-4b: one Node arm on the same pool and
hardware, or delete R1 and R2 and say the stack is not reversible on latency evidence.

---

```
ID:            ADV-104
Severity:      HIGH
Rubric:        none — cross-reference defect that voids a tension resolution's evidence
               (affects CG-AD, CG-SEM)
Location:      ARCHITECTURE_DECISION.md A.8 final paragraph; C table row T-RC2 "Settled by" cell
```

**Reproduction.** T-RC2 is the tension the brief flags as most likely waved through. Its resolution
rests entirely on `answer_type_presence`, which A.8 introduces as "a **hypothesis**, pre-registered for
Loop 3" and says "PF-9/CG-EP measure its over-trigger and under-trigger rates against the pure
query-shape trigger." The C-table row names the settling instrument as "CG-EP". Look up both.

**Expected.** A tension resolved by a named future measurement is only as good as the named
measurement.

**Actual.**
- **PF-9** is, in this document's own §F, the check that "Gmail `q` [is] message-scoped … and L1b
  decomposition/intersection recovers it." It has nothing to do with escalation triggering.
- **CG-EP** is, in `EVALUATION_PLAN.md` §13.4, *Evidence preservation*: F1/F3 buried-evidence recall,
  position spread, FNF on F1/F3, recall vs Baseline B, hallucinated-found on F10. It measures no
  escalation trigger at all.
- The instruments that **do** measure this are **CG-AD** ("the escalation confusion table published
  with both off-diagonal cells", over/under-escalation rates, `escalation_cost`) and **CG-SEM**
  ("registered F12 over-escalation ceiling met" and the F11 `semantic_gain` bar). Neither is cited by
  T-RC2.

So the single most load-bearing hypothesis in the design is assigned to two instruments that cannot
test it, in both the prose and the tension table.

Separately, the signal's own discriminative power is asserted and is likely weak. `answer_type_presence`
"check[s] mechanically whether any hit's cleaned body contains a token of the query's answer type
(a date-like token for *when*…)". Ordinary business mail contains date-like tokens in signatures,
scheduling text and — where quote-stripping does not reach — the "On Tue, 3 Sep 2026 … wrote:"
attribution line; numeric tokens are near-ubiquitous. For the two exemplar interrogatives (*when*,
*how much*) the predicate is close to always-true, which makes it inert as a downgrade and makes its
under-trigger rate the thing that matters. A.8 does not acknowledge this.

**Required fix.** Repoint T-RC2's "Settled by" cell and A.8's sentence at **CG-AD** (confusion table,
over/under-escalation) and **CG-SEM** (F11 `semantic_gain`, F12 over-escalation ceiling); delete the
PF-9 reference. Add to A.8 the pre-registered **base rate** of `answer_type_presence == true` on a
random sample of the corpus per interrogative class, measured at G0 — a predicate that is true 97% of
the time is not a signal, and that number must exist before the design leans on it.

---

```
ID:            ADV-105
Severity:      HIGH
Rubric:        ROUTE-04 (also C-08)
Location:      ARCHITECTURE_DECISION.md A.7 rung L2 (`≤3 × 5 u`), global cap `max_probe_rounds = 4`;
               A.2 §"There is never a bare empty result"; D.2 `empty_diagnosis`
```

**Reproduction.** Query with five parsed constraints: `from:amy to:dev-list subject:launch
after:2026/05/01 before:2026/06/01`. Zero hits at L1. L2 "drop ONE constraint per step, enumerable"
is capped at **≤3 probes**. Suppose the constraint whose removal restores results is the fifth
(`before:`). Probes 1–3 exhaust the cap; the restoring constraint is never tried.

**Expected.** ROUTE-04: "On zero-hit outcomes where dropping exactly one constraint restores results,
the report names that constraint and the count it restores; correctness of this diagnosis on
constructed cases = **100%**." No tolerance band.

**Actual.** With `k` constraints and a 3-probe budget, correct diagnosis is impossible for `k > 3`
unless the drop ordering happens to try the right one first. The architecture states no ordering
heuristic, no rule for reporting "diagnosis incomplete: 2 of 5 single-constraint drops untried", and
no relationship between constraint count and probe budget. ROUTE-04's guard ("Dumbest max: always
claim the date filter is at fault") is not what fails here; what fails is that the honest answer —
"unknown" — is not a shape the schema provides (`"empty_diagnosis": null` is used for "no single
constraint restores results", which is a different claim).

**Required fix.** Either scale L2's probe budget with parsed constraint count (`min(k, cap)` with the
cap declared), or add a third `empty_diagnosis` state — `{"status": "incomplete", "untried_drops":
["before","subject"], "affordance": {...}}` — and amend ROUTE-04's acceptance so 100% correctness is
required only over the drops actually attempted, with completeness itself reported. Flag the ROUTE-04
wording to the owner if the criterion is to keep its 100% bar over all constructed cases.

---

```
ID:            ADV-106
Severity:      HIGH
Rubric:        OBS-04, PERF-02, AD-04 (also AD-01, contract C-10)
Location:      ARCHITECTURE_DECISION.md A.5 (batch ≤50, "a batch of n costs n quota units"),
               A.7 (`max_gmail_calls = 40`), A.11/D.10 (`gmail_calls_by_method`), B.9 (counting proxy)
```

**Reproduction.** Re-derived: summing A.7's own per-rung caps as logical API calls gives
`1+5 + 1+10+4 + 3 + 3 + 2 + 1 + 4 + 25+2 = 61` calls against a stated `max_gmail_calls = 40`. The two
caps are mutually inconsistent unless "call" means *HTTP request* and batching collapses the
`messages.get` and `threads.get` fan-outs. The document never says which it means.

**Expected.** OBS-04: "Server-reported Gmail call counts agree with network-level counts within
[tolerance]; persistent mismatch is a finding, not a rounding note." PERF-02: calls counted by the
harness's counting proxy, never from server self-reports. AD-04/CG-AD: "median **network** API calls
≤ 3" on simple families.

**Actual.** A counting proxy at the network layer sees **one** HTTP request per `batch` endpoint call,
whatever `n` is. A server that counts logical calls (which it must, since quota is charged per
sub-request) reports `n`. The disagreement is systematic and unbounded, not a tolerance question, and
OBS-04 will fail permanently or be silently reinterpreted. Simultaneously, AD-04's "≤3 network calls"
becomes trivially satisfiable by batching aggressively — a simple query issuing 1 list + 1 batch of 10
gets + 1 batch of 4 maps counts as **3** at the proxy while costing 5+200+160 = 365 u. The criterion
intended to bound cost bounds nothing.

**Required fix.** Define two distinct counters in A.11/D.10 and in the trace schema:
`http_requests` and `api_calls` (sub-requests), state which one `max_gmail_calls` bounds, state which
one AD-04's bar binds on, and set OBS-04's tolerance against `http_requests` only. Recommend to the
owner that AD-04/CG-AD's "median network API calls ≤ 3" be re-expressed in `api_calls` or in quota
units, since under batching the HTTP-request form is not a cost measure.

---

```
ID:            ADV-107
Severity:      HIGH
Rubric:        GMAIL-05, PERF-01, MCP-02 (also contract C-05, N-07)
Location:      ARCHITECTURE_DECISION.md A.5 (quota accountant scoped to "the query's
               max_quota_units"), A.7 global caps, A.10 (per-process HMAC key, in-process LRU),
               H-6 ("models load lazily")
```

**Reproduction.** Re-derived: a semantic-escalated query costs 1,362–1,682 u. The [VERIFIED] ceiling
is 6,000 u/min/user/project. That is **3.6–4.4 escalated queries per minute** before 429s. Now issue
two `mailweave_search` calls concurrently from one host — MCP's JSON-RPC transport permits it and
MCP-02's acceptance explicitly tests "a second concurrent client."

**Expected.** GMAIL-05: correct behaviour under Gmail's real quota and rate limits, with bounded
retry. MCP-02: concurrent consumption works or fails per MCP-06.

**Actual.** The document specifies **no concurrency model at all**. Consequences that follow directly
from what it does say:

- The `budget_accountant` is scoped per query ("refuses a call that would exceed **the query's**
  `max_quota_units`"). Nothing enforces the per-minute per-user ceiling across queries. Two escalated
  queries in the same minute sit at the limit; a third 429s.
- A.5 specifies "exponential backoff with jitter on 429/5xx" but not whether a retry re-charges the
  accountant, nor what the ladder does when backoff exceeds `max_server_ms = 2000` / `max_semantic_ms
  = 6000` mid-rung. Partial-escalation state on timeout is undefined everywhere in the document.
- H-6 relies on lazy model loading. Two concurrent escalated queries can both trigger a cold load of a
  32M-parameter model plus a 278M cross-encoder; no lock, no single-flight, no RSS bound is stated
  (NFR-02 requires the footprint be measured and documented).
- The in-process LRU (A.10) and the per-process HMAC key have no stated thread/async safety.

**Required fix.** Add a §A.5 subsection: (a) a process-wide token bucket sized to the *measured*
per-minute budget from PF-3, with in-band reporting when a query waits or is refused for
process-level rather than query-level budget (AD-03 already requires the shape); (b) a concurrency
statement — serialized, bounded-parallel, or free — and single-flight model loading; (c) retry
accounting and the mid-rung timeout contract (which partial results are emitted, what `budget_caps_hit`
and `not_tried` say); (d) a suite-level quota budget in §F, since PF-3 drives to 429 by design and
will contend with any other run on the same project.

---

```
ID:            ADV-108
Severity:      HIGH
Rubric:        R-01, PART-01, §5.3 (also AD-04, PERF-01)
Location:      ARCHITECTURE_DECISION.md A.7 rung cost table (L0: "5 u + ≤5×20 u", no maps);
               A.9(4); H-6
```

**Reproduction.** `rfc822msgid:<CAF…@mail.gmail.com>` — the exact-lookup path, EV-05's required case.
D.3 rule 1: stop after L0. A.7 prices L0 at `5 u + ≤5 × 20 u` with **no thread map**. Now check the
response against the response-shape obligations.

**Expected.** R-01: "Every message present carries a stable message identifier … plus its thread id and
**its position within that thread**." R-05/PART-01: every thread represented declares its total
message count as reported by the source, on **100%** of thread-bearing responses. §5.3: a response
omitting R-01 or R-05 is non-conforming "regardless of retrieval quality."

**Actual.** Position within a thread and `stated_total` are both derivable only from a
`threads.get` — the map. A.7's L0 cost model omits it. So either (i) L0 in fact fetches a map, in
which case the published cost model for the cheapest, most common rung is wrong by 40 u and one
network call, and H-6's PERF-01 risk is larger than stated; or (ii) it does not, and the exact-lookup
response violates R-01 and PART-01. The same defect applies at L1 beyond `max_map_threads = 4`: hits
in the 5th and later hit-bearing threads have no map, therefore no position and no `stated_total`.

H-6 acknowledges the latency half of this ("MailWeave adds a `threads.get` for the map that Baseline D
never makes") and even proposes making the map conditional on multi-message threads — but a
single-message thread still needs the fetch to *know* it is single-message, so the conditional does
not remove the call, only the second one.

**Required fix.** Correct A.7's L0 and L1 cost lines to include `+ 40 u × mapped_threads`, state that
`max_map_threads` **never** applies to hit-bearing threads (only to expansion/sibling threads), and
re-derive `max_quota_units` from the corrected model. If the intent is genuinely to cap maps below the
hit-thread count, ADV-001's `withheld` mechanism must carry the excess and R-01/PART-01 must be
flagged to the owner as unachievable for those messages.

---

```
ID:            ADV-109
Severity:      HIGH
Rubric:        EV-01 (H-5's proposed reinterpretation)
Location:      ARCHITECTURE_DECISION.md H-5; D.5 pool construction step (b); A.7 `max_rerank_pairs`
```

**Reproduction.** H-5 asks the owner to read I-1's `H` from a scored retriever as "the candidates that
**pass the retriever's selection threshold** (the shortlist that enters the disclosure candidate set),
not every text that received a score." Test that wording adversarially.

**Expected.** A clarification of a release invariant should not hand the implementer a dial that sets
the size of the set it is measured against.

**Actual.** Two defects.

1. **The threshold is implementer-chosen and unbounded.** Under H-5's wording, an implementation that
   sets the selection threshold at cosine 0.95 has `|H_semantic| ≈ 0` and passes EV-01's exact set
   assertion vacuously on every semantic case. EV-01's guard rules out the *inflationary* degenerate
   ("return every message of every candidate thread") and says nothing about the deflationary one.
   The architecture is asking to legalise the deflationary one.
2. **It does not cover the other half of `H`.** I-1's `H` is "message IDs returned by the executed
   Gmail queries **and** any scored retriever." H-5 narrows only the second clause. D.5's pool
   construction step (b) is "threads of participants parsed from the query (`from:`/`to:` probes,
   5 u each)" — those are `messages.list` calls, so their returned IDs are unambiguously in `H` under
   the *first* clause, and there can be far more of them than the 25-thread / 300-row pool admits.
   Those IDs are neither disclosed nor withheld (see ADV-001). H-5's narrowing leaves this untouched
   while giving the impression the `H` question has been settled.

**Required fix.** Amend H-5's request to: (a) `H` from a scored retriever = the shortlist that enters
the disclosure candidate set, where **the shortlist size is a declared, pre-registered parameter**
(`max_rerank_pairs` and the selection rule), reported in `retrieval_report`, not a free implementer
choice; (b) the full pool is enumerated **by ID in the trace** (not in the response) so EV-01 can be
checked against a real set rather than the implementer's account of one; (c) explicitly state that
step-(b) probe results are covered by the first clause and are handled by ADV-001's `withheld`
mechanism.

---

```
ID:            ADV-110
Severity:      HIGH
Rubric:        RANK-03 (also R-03, C-04c)
Location:      ARCHITECTURE_DECISION.md A.9 "Semantic scoring inside disclosure (T-CD3): reuse only";
               D.2 `score.method`; D.5 "Pool text"
```

**Reproduction.** L5 ran. A.9 says the E4 fill "re-scores at zero marginal cost and says so
(`"semantic cosine 0.81, model potion-retrieval-32M@<rev>"`)". Trace which vectors exist. D.5: pool
text is `subject + from/to addresses + Gmail snippet` per message row, for at most 25 threads / 300
rows. The E4 fill selects among messages in *touched* threads, which include L4 structural expansions
and hit threads that may not be pool members, and it is choosing what to show at `body_clean`.

**Expected.** RANK-03: "no numeric relevance value appears without an adjacent method + model
identifier"; every reason is mechanical and names its mechanism.

**Actual.** Three problems the "reuse, never trigger" resolution does not address:

1. **Coverage.** Vectors exist only for pool rows. Messages in touched-but-not-pooled threads have
   none, so a single E4 fill mixes semantically-scored and mechanically-scored candidates with no
   stated rule for combining or comparing them. Two candidates ranked against each other by different
   scales is exactly the fabricated-comparability RANK-03 exists to prevent.
2. **Provenance is misleading.** The vector was computed over `subject + participants + snippet`. The
   disclosed artifact is `body_clean`. `"semantic cosine 0.81, model potion-retrieval-32M@<rev>"`
   omits *what was embedded*, which is the load-bearing half of the method. A reader will take 0.81 as
   body-level similarity.
3. **"Zero marginal cost" is not general.** It holds only on the intersection (pool rows ∩ fill
   candidates). Outside it the choice is: embed more (which is exactly the "trigger" T-CD3 forbids) or
   fall back to mechanical (see 1).

**Required fix.** Add to D.2's score object a mandatory `basis` field naming the embedded text
(`"subject+participants+snippet"`), forbid mixed-scale ranking within one fill (score all candidates
mechanically, and expose the reused cosine as a *separate, additive* declared component only where it
exists for every candidate in the comparison), and state the fallback rule explicitly in A.9.

---

### MEDIUM

---

```
ID:            ADV-201
Severity:      MEDIUM
Rubric:        AD-01, GMAIL-05
Location:      ARCHITECTURE_DECISION.md A.5 (accountant rate table), A.4 (`users.getProfile`),
               A.5 (six-endpoint list), A.7 global caps
```
**Reproduction.** A.5 says the accountant "charges every call at its published rate ([VERIFIED] RO F7:
`history.list` 2, `messages.list` 5, `messages.get` 20, `threads.get` 40)". Enumerate the endpoints the
server actually calls.
**Expected.** Every endpoint the server calls has a rate in the accountant, and the stated API surface
matches the code paths described.
**Actual.** The rate table covers **four** of the six endpoints A.5 lists: no rate is given for
`labels.list` or `messages.attachments.get`. A **seventh** endpoint, `users.getProfile`, is used at
startup (A.4) and in the harness pinning assertion but is absent from the six-endpoint list and from
the rate table. Conversely `labels.list` appears in the endpoint list and is used nowhere in the
document — no rung, no tool, no signal consumes labels. Separately, re-deriving the ladder gives
worst-case 1,362 u (global `max_map_threads`) or 1,682 u (per-rung), neither of which corresponds to
either stated budget (1,500 / 3,000); the semantic budget has ~1,300 u of unexplained headroom under
one reading and the normal budget is exceeded under the other.
**Required fix.** Complete the rate table for all endpoints actually called; add `users.getProfile` to
the stated surface or state why it is exempt; delete `labels.list` or name the capability that uses it;
show the arithmetic behind 1,500/3,000 or restate them as derived from the corrected worst case.

---

```
ID:            ADV-202
Severity:      MEDIUM
Rubric:        INJ-04, GMAIL-02, DISC-03
Location:      ARCHITECTURE_DECISION.md D.4 ("Quote stripping is heuristic and bypassable; the GPLv3
               `html2text` is excluded on licence grounds")
```
**Reproduction.** INJ-04 requires HTML bodies converted "by a maintained parser to visible text", with
hidden constructs (display:none, zero-size, white-on-white, comments, zero-width characters) removed
and flagged, and zero network calls proven with sockets disabled. Search the architecture for the
chosen parser.
**Expected.** A named, licence-checked component for a criterion with five specific acceptance
conditions.
**Actual.** The document excludes one candidate on licence grounds and names **no replacement**, for
either HTML→text or reply/quote stripping (`CONTEXT_DISCLOSURE_OPTIONS` names `talon` Apache-2.0,
`github/email_reply_parser` and `crisp-oss/email-reply-parser` as candidates; the architecture selects
none). The `hidden_content_removed` flag INJ-04 requires appears nowhere in D.2's schema, though
`reductions[]` is the natural home for it.
**Required fix.** Name the HTML→text parser and the quote stripper with versions and licences; add
`{"kind":"hidden_content","removed_chars":N}` to the `reductions` vocabulary; state the
sockets-disabled test obligation in §F.

---

```
ID:            ADV-203
Severity:      MEDIUM
Rubric:        GMAIL-02
Location:      ARCHITECTURE_DECISION.md A.5 ("Pydantic models hand-written from the REST schema"),
               B.5
```
**Reproduction.** GMAIL-02 requires RFC 2047 encoded-word headers, non-UTF-8 charsets, HTML-only
bodies, nested multiparts, missing/duplicate headers to be represented "without content loss or
crash; anything undecodable is declared, not dropped." Search for the decoding policy.
**Expected.** A stated policy, since Gmail returns `payload.body.data` as base64url and charset lives
in `Content-Type`.
**Actual.** No decoding policy exists: no base64url handling rule, no charset-detection/fallback rule,
no RFC 2047 decode rule, no policy for undecodable bytes, no part-selection rule for
`multipart/alternative` (text vs HTML preference) — the last being directly load-bearing for
`body_clean`. B.5 also overstates the benefit: Gmail parses MIME server-side and returns a structured
payload tree, so the residual risk is *decoding and part selection*, not MIME parsing, which weakens
both the Pydantic-boundary claim and the TypeScript-typing claim it is contrasted with.
**Required fix.** Add a D-section on the content pipeline: part selection, base64url decode, charset
resolution and fallback, RFC 2047 header decode, undecodable-byte declaration (as a `reductions`
entry), and the normalisation applied before embedding.

---

```
ID:            ADV-204
Severity:      MEDIUM
Rubric:        LEX-02, ROUTE-03
Location:      ARCHITECTURE_DECISION.md A.6 ("date references"), D.2 `asked_for.parsed.after`
```
**Reproduction.** Query "what did Amy send last Tuesday?" on a laptop in UTC+13 against a Gmail
account whose date operators resolve in another zone. `after:`/`before:` in Gmail `q` are date-valued,
not instant-valued.
**Expected.** A stated timezone rule, since EP's F2 family deliberately uses "date margins ≥48 h"
because of exactly this ambiguity.
**Actual.** No timezone policy anywhere: not for relative-date resolution ("last Tuesday", "yesterday"),
not for `after:`/`before:` boundary semantics, not for `internalDate` comparison in D.6's temporal
ordering, not for the `fetched_at` stamps. `constraint_drop_depth` and `window_containment` both
depend on it.
**Required fix.** State the reference timezone (account, host, or UTC), the boundary convention for
`after:`/`before:`, and whether relative dates are widened by a margin; declare the resolved absolute
window in `asked_for.parsed`.

---

```
ID:            ADV-205
Severity:      MEDIUM
Rubric:        SEC-06, N-05
Location:      ARCHITECTURE_DECISION.md A.4 "Profile derivation"
```
**Reproduction.** A.4: `SHA-256(salt ‖ address)` compared to the configured `seed_account_hash`;
match ⇒ `seed` profile (full content permitted in traces), else `personal`. Set
`seed_account_hash` to the hash of the personal address.
**Expected.** N-05: "The redaction profile is selected from the *authenticated account*, not from a
config flag."
**Actual.** The *input* is the authenticated account but the *decision* is a comparison against a
config value, so a config edit (or a copied config, or a shared salt) promotes a personal mailbox to
the content-permitting profile. "Fails closed" is true only for the unset case, which is the case the
document tests. Two further gaps: the salt's provenance and storage are unspecified; and the behaviour
when `users.getProfile` fails at startup (network, expired refresh token) is undefined — the profile
cannot be derived, and nothing says the server refuses to start.
**Required fix.** Bind the seed profile to a second independent condition that config cannot fake —
e.g. the seed profile requires the harness OAuth client/token store, which by A.2/B.9 cannot hold the
personal account; specify salt provenance; specify that a failed `getProfile` is fatal at startup, and
add both to PF-8's canary.

---

```
ID:            ADV-206
Severity:      MEDIUM
Rubric:        GMAIL-06, AD-03
Location:      ARCHITECTURE_DECISION.md A.4, A.5, D.2 (no error shape)
```
**Reproduction.** Refresh token expires (the [VERIFIED] 7-day Testing-status clock for the harness;
revocation or password change for the read client). Issue `mailweave_search`.
**Expected.** GMAIL-06: "Failure is a clear re-auth instruction, never a confusing retrieval error."
**Actual.** The document defines no error taxonomy. `handle_expired`, `handle_stale` and the `budget`
block are introduced ad hoc in A.10 and A.7; D.2's schema has no error shape at all. There is no
stated behaviour for token-refresh failure, for a partial-thread fetch failure mid-`threads.get`
fan-out, or for 4xx classes other than 429. A.5's "exponential backoff with jitter on 429/5xx" has no
bound and no interaction rule with `max_server_ms`.
**Required fix.** Add a closed error-code vocabulary to D.2 with the affordance/remediation attached to
each (`auth_reauth_required`, `handle_expired`, `handle_stale`, `budget_exhausted`,
`partial_source_failure`, `upstream_rate_limited`), and state which errors are in-band fields on a
successful response versus tool errors.

---

```
ID:            ADV-207
Severity:      MEDIUM
Rubric:        B-04, E2E-01, SEC-07
Location:      ARCHITECTURE_DECISION.md A.5 (endpoint `messages.attachments.get`), D.1
               (`mailweave_get_attachment(..., mode: "metadata")`)
```
**Reproduction.** Call `mailweave_get_attachment(message_id, part_id, mode="metadata")`. Which
endpoint serves it?
**Expected.** B-04: attachment **metadata** by default; content extraction only if built, sandboxed
and opt-in. E.3 defers attachment content extraction entirely.
**Actual.** Attachment metadata (filename, mimeType, size, partId) lives in the `payload.parts` tree
of `messages.get(format=full)`. `messages.attachments.get` returns the attachment **bytes** — the one
thing B-04 and E.3 exclude. So the endpoint list contains an endpoint that only serves the deferred
capability, and the tool's only supported mode is served by a different endpoint that the tool's
description does not mention. Either the endpoint is dead (and should be removed, since it also widens
the audited call surface for SEC-02/SEC-07) or the tool downloads content it says it does not.
**Required fix.** Remove `messages.attachments.get` from the six-endpoint surface for this release, and
state that `mode:"metadata"` is served from the carrying message's `payload.parts`.

---

```
ID:            ADV-208
Severity:      MEDIUM
Rubric:        DISC-05
Location:      ARCHITECTURE_DECISION.md D4, D.4, H-3
```
**Reproduction.** DISC-05's trigger: "Fires if the shipped design exposes **more than one disclosure
level** beyond the evidence response plus a full-fetch escape hatch." Enumerate the shipped levels:
thread map; segment map; `snippet` view; `body_clean` view; `body_full` (the escape hatch); `raw`.
**Expected.** H-3 declares the trigger met and budgets the depth-*n* vs *n−1* measurement — the honest
move, and correct as far as it goes.
**Actual.** H-3 scopes the commitment to the **segment map only**. The separately-requestable `snippet`
and `raw` views are additional levels under the criterion's plain wording, and D4's defence — that the
content-depth vocabulary is "orthogonal and is not a routing hierarchy" — is a definitional move, not
a measurement. From the agent's side, stub → snippet → `body_clean` → `body_full` is sequential
refinement, which is what 2607.17598 measured. The architecture's claim is defensible for the
*default* path (search returns evidence at `body_clean` in one call, satisfying C-06) but the doc
presents the orthogonality as settling the question rather than as a claim to be tested.
**Required fix.** Either drop `snippet` and `raw` as independently requestable views for this release
(leaving stub / `body_clean` / `body_full`), or extend H-3's DISC-05 commitment to cover the
content-depth vocabulary with a measurement of levels-traversed-to-answer, which
`CONTEXT_DISCLOSURE_OPTIONS` T-CD1 already asks to be instrumented as a first-class metric.

---

```
ID:            ADV-209
Severity:      MEDIUM
Rubric:        PART-01, GMAIL-03
Location:      ARCHITECTURE_DECISION.md H-2
```
**Reproduction.** H-2's requested rewording, contingent on PF-1: "`stated_total` equals what the source
reported at `fetched_at`, and the measured discrepancy against the manifest is published as a
characterised instrument limitation."
**Expected.** A criterion that can still fail.
**Actual.** The flag is **correct** — Gmail has no thread message-count field and no thread operator,
so there is genuinely no second oracle, and the architecture's refusal to infer a count and present it
as the source's report is the right call. But the proposed replacement is self-satisfying: "our number
equals the number we read from the call we made" is true of any implementation, including a broken
one. The falsifying power moves entirely into "the discrepancy is published", and *published* is not a
bar.
**Required fix.** Make the discrepancy rate itself gate-binding under GMAIL-03: a pre-registered
ceiling on `|threads.get count − manifest length| / manifest length`, registered at G0 from PF-1's
measurement, with the criterion failing above it. Otherwise PART-01 becomes a hollow pass exactly as
`AGENT_LOOP` §7 warns.

---

```
ID:            ADV-210
Severity:      MEDIUM
Rubric:        SEC-07, NFR-01, SEM-02
Location:      ARCHITECTURE_DECISION.md D.8 ("Weights are provisioned at setup time, not at query
               time … so the 'only network peers are Gmail and OAuth' property survives model
               loading"), H-4, §F PF-5
```
**Reproduction.** H-4's flag is **correct**: SEC-07 as worded ("connections only to Gmail") cannot hold
because OAuth refresh contacts `oauth2.googleapis.com`, and the requested allowlist fix is right. But
run PF-5's egress-blocked suite against the described implementation.
**Expected.** Zero non-Gmail/non-OAuth egress in the default configuration.
**Actual.** Provisioning weights at setup time is necessary but not sufficient. The
`sentence-transformers` / `transformers` / `huggingface_hub` default load path performs a hub
revalidation request for the model repo unless offline mode is forced
(`local_files_only` / `HF_HUB_OFFLINE`). The architecture asserts the egress property as a consequence
of setup-time provisioning and never states the offline-mode enforcement that actually produces it.
This is a defect of the same class as H-4 that the document did **not** flag, and it lands on three
mandatory criteria.
**Required fix.** Extend H-4's requested allowlist to name the model-hub host **for the setup step
only**, and add to D.8 an explicit runtime requirement: model loading is forced offline
(`local_files_only=True` / `HF_HUB_OFFLINE=1`), verified by PF-5's blocked-egress run, with a
checksum-pinned local path rather than a repo id.

---

```
ID:            ADV-211
Severity:      MEDIUM
Rubric:        OBS-02, PERF-02
Location:      ARCHITECTURE_DECISION.md D8 ("Quota-native budgeting"), A.11 (`quota units` in trace),
               B.9 (counting proxy), §F PF-3
```
**Reproduction.** OBS-02: "Every headline number … derives from harness-measured or manifest-scored
fields; server self-reported fields appear only labeled as diagnostics." Ask how a quota-unit figure
is measured.
**Expected.** Headline numbers measurable externally.
**Actual.** Quota units are not present in any Gmail response header or body; a network proxy can count
requests and classify methods but cannot observe units. Every quota number MailWeave states is
therefore a server-side multiplication of a *published* table by a call count — a self-report by
construction. PF-3 infers the real table once by driving to 429; that calibration cannot be re-run per
gate. So D8's headline framing ("caps denominated in Gmail quota units") produces numbers that OBS-02
forbids as headline claims.
**Required fix.** State in A.11/B.9 that quota units are a **diagnostic** field, that the
harness-derived headline cost metric is `api_calls` by method (proxy-observed, multiplied by the
PF-3-calibrated table at analysis time), and that any published quota figure carries the PF-3
calibration date.

---

```
ID:            ADV-212
Severity:      MEDIUM
Rubric:        MCP-02, MCP-06, AD-03
Location:      ARCHITECTURE_DECISION.md A.10 (per-process HMAC key, TTL 30 min),
               A.7 ("A client may lower budgets but may not lower them below the recoverability floor")
```
**Reproduction.** (a) Restart the server; redeem a `map_id` minted 2 minutes ago. (b) Call
`mailweave_search(budget={max_quota_units: 50})`.
**Expected.** (a) MCP-06: an explicit error naming a re-derivation path — satisfied, but the error
class must be truthful. (b) A defined behaviour at or below the floor.
**Actual.** (a) With a per-process HMAC key, every restart invalidates every outstanding handle and
the failure surfaces as `handle_expired` (A.10 step 1) for a handle that has not expired. The error
misattributes the cause, and no key persistence or rotation policy is stated. (b) The
"recoverability floor" is asserted but never **costed**: re-deriving L0+L1+L1b+L2+L3 gives ≈510 u
(excluding maps). The document does not say whether a sub-floor budget is clamped, refused, or
accepted-and-then-overrun.
**Required fix.** Add a distinct `handle_key_rotated` error class (or persist the key in the 0600 token
store); publish the floor's derived cost as a named constant and state the clamp-or-refuse rule, with
the clamp reported in the `budget` block per AD-03.

---

```
ID:            ADV-213
Severity:      MEDIUM
Rubric:        PROC-03
Location:      ARCHITECTURE_DECISION.md B.9 ("Coupling rules, **enforced by review**")
```
**Reproduction.** PROC-03: the server "cannot read case manifests, seed maps, or the harness repo —
verified **structurally** (working directory/container isolation, dependency graph, grep sweep …),
**not by inspection alone**. A reviewer finding otherwise raises a BLOCKER regardless of behavior."
**Expected.** A structural mechanism named in the architecture.
**Actual.** B.9 names four coupling rules and states they are "enforced by review" — precisely the mode
PROC-03 excludes. AGENT_LOOP §3 repeats the requirement. No isolation mechanism (separate process
working directory, container, filesystem permissions, dependency-graph gate) is specified.
**Required fix.** Name the structural mechanism in B.9: separate top-level directories with the server
process's working directory outside the harness tree, a CI dependency-graph assertion that no server
module imports harness code, and the grep sweep as a CI gate rather than a review habit.

---

```
ID:            ADV-214
Severity:      MEDIUM
Rubric:        none — architecture risk (bears on GMAIL-02, GMAIL-04, GMAIL-05)
Location:      ARCHITECTURE_DECISION.md A.5, B.5, B.8 R4
```
**Reproduction.** A.5 declines `google-api-python-client` in favour of hand-written `httpx` calls plus
hand-written Pydantic payload models, on the grounds that the official clients are "maintenance-mode
generated wrappers", that six endpoints "do not justify a ~50 MB discovery-bundled dependency", and
that hand-rolled HTTP batch is needed anyway.
**Expected.** A correctness-critical dependency choice with a reversal criterion of its own, in a
product whose differentiator is not silently losing mail content.
**Actual.** The decision moves pagination, HTTP batch construction/parsing, retry/backoff, quota
accounting, and payload decoding in-house, against GMAIL-02 (real MIME/header reality without silent
loss), GMAIL-04 (pagination without loss or duplication) and GMAIL-05 (rate-limit behaviour) — all
mandatory. "Maintenance mode" means feature-frozen, not defective; the stated counter-argument is
install size. And R4 — "MIME parsing in Python produces a defect class that typed TS payloads would
have prevented, observed twice" — reverses the **stack**, not the client choice, so a defect in the
hand-rolled client has no reversal path at all.
**Required fix.** Either adopt the official client for transport (keeping the Pydantic models as the
validation boundary at the payload level, which is where B.5's argument actually holds), or add an
explicit reversal criterion for the hand-rolled client — e.g. two GMAIL-02/04/05 findings traceable to
transport code — and name the batch/pagination/backoff implementation as first-class components in
A.5 rather than one-line responsibilities.

---

### LOW

---

```
ID:            ADV-301
Severity:      LOW
Rubric:        none — stale cross-reference
Location:      ARCHITECTURE_DECISION.md C table, T-RC2 "Settled by" cell
```
**Actual.** "the **plausible-but-wrong-lexical-result** family (F11–F16) which EP notes is currently
under-represented." `EVALUATION_PLAN.md` §4.7 **adds** F11–F16 (F11 at n=10) precisely to remove that
under-representation; the "currently under-represented" note is `ROUTING_OPTIONS`'s pre-revision
observation. Also, F11 alone is the plausible-but-wrong-lexical family; F13–F16 are structural,
participant, thread-structure and ranking families.
**Required fix.** Cite F11 (and F12 as its paired negative control); drop the stale "under-represented"
clause.

---

```
ID:            ADV-302
Severity:      LOW
Rubric:        none — a resolution that defers to an artifact that does not exist
Location:      ARCHITECTURE_DECISION.md C table, T-CD2 row ("Reversed by: —"; "Settled by: The
               adversarial 'decision reversed later in the thread' family, **which must be added to
               the suite**")
```
**Actual.** T-CD2 is settled by a benchmark family that does not exist in `EVALUATION_PLAN.md`. The
nearest existing family, F5 (decision evolution: proposal → objection → final confirmation → reminder),
tests *finding the final decision*, not *the low-scoring reply that reverses the high-scoring ones*,
which is T-CD2's canonical case. The row assigns the work to no document, no gate and no owner, and
its `Reversed by` cell is empty, so the resolution can never be shown wrong. Combined with ADV-003 —
which shows the floor is arithmetically unable to hold under the token ceiling — T-CD2 is the tension
this review considers least resolved.
**Required fix.** Raise the family as a concrete change request against `EVALUATION_PLAN.md` §4.7
(name, n, construction, distractor design, and which gate binds on it), and fill T-CD2's `Reversed by`
cell with the measurement that would show the floor failing.

---

```
ID:            ADV-303
Severity:      LOW
Rubric:        none — internal inconsistency in the stack argument
Location:      ARCHITECTURE_DECISION.md B.3 ("Second signal"), B.8 ("Not reversal criteria:
               transformers.js shipping a release")
```
**Actual.** B.3 presents `@huggingface/transformers`'s four-month release gap as a deciding second
signal; B.8 then declares that a transformers.js release is explicitly not a reversal criterion. If
new evidence on the factor cannot change the decision, the factor was not load-bearing; if it was
load-bearing, evidence on it must be able to move it. One of the two sentences should go.
**Required fix.** Delete the "second signal" from B.3, or add a reversal criterion for it. Recommend
deleting it — the single-API argument (ADV-103's suggested restatement) is the honest one and does not
depend on another project's release cadence.

---

```
ID:            ADV-304
Severity:      LOW
Rubric:        R-08, GMAIL-04
Location:      ARCHITECTURE_DECISION.md D.4 (lists "scan-scope limits" among reductions declared in
               place), D.2 response schema
```
**Actual.** D.4 promises scan-scope limits are "declared **in place** with a size count and an
unabridged path", but D.2's schema has no field for it: `reductions[]` is per-message and content-
shaped (`quoted`, `html_to_text`), and `retrieval_report` carries `pool`, `not_tried` and
`budget_caps_hit` but nothing about how much of the result set was scanned. GMAIL-04's guard makes
this load-bearing once the ladder stops paginating.
**Required fix.** Add `retrieval_report.scan_scope: {pages_fetched, page_size, more_pages: bool,
affordance}` per executed query.

---

## 2. Independent verification of the four owner-flagged items

| Flag | Is the flag correct? | Is the proposed handling right? | This review's position |
|---|---|---|---|
| **H-1** `DISC-02` contradicts `SC` §6 | **Yes.** DISC-02's acceptance verbatim: "the shipped policy is the measured winner **or the loss is documented and the simpler policy ships**." SC §6: "Do not treat fixed ±2 as MailWeave's final progressive disclosure policy… implement and review the actual query-aware policy against it." `CONTEXT_DISCLOSURE_OPTIONS` addendum §1 marks H3's ship-the-simpler clause "**genuinely invalidated as a scope decision**." | **Yes**, and the proposed rewording is the right one. | Endorse. Add one clause: on a loss, `EVALUATION_PLAN` §8.7's pre-committed narrowing applies to the **claim**, and Baseline F(±2) stays a permanent fixture — so the outcome is a documented tuning input, never a scope reduction. |
| **H-2** `PART-01` may be unachievable | **Yes.** `threads.get` is the only source; Gmail has no thread operator and no thread message-count field (T-3); VR §6.1/#239 reports `threads.get` truncation. There is genuinely no second oracle. | **Partly.** The rewording is directionally right and the refusal to infer-and-present is exactly correct. But it makes PART-01 self-satisfying. | Endorse **with ADV-209**: the manifest-discrepancy rate must itself be a pre-registered, gate-binding bound under GMAIL-03, not merely "published". |
| **H-4** `SEC-07` unsatisfiable as worded | **Yes.** OAuth refresh contacts `oauth2.googleapis.com`, which is not `gmail.googleapis.com`. The requested allowlist is correct. | **Incomplete.** | Endorse **with ADV-210**: the allowlist must also cover the model-hub host at *setup* time, and D.8 must state runtime offline-mode enforcement — otherwise the property H-4 says is "implemented and testable" fails on the default library load path. |
| **H-5** `I-1`'s `H` needs clarification | **Yes** — a literal reading does collide with DISC-04 and RANK-04, and naming it rather than assuming it is the right instinct. | **No.** | **Reject as worded — see ADV-109.** The proposed wording hands the implementer the dial that sets `|H|`, and it leaves D.5's pool-construction `messages.list` probes (unambiguously in `H` under the first clause) unaddressed. Amend per ADV-109 before the owner rules on it. |
| **H-3** `DISC-05` fires by design | **Yes**, and declaring it up front is the honest move. | **Under-scoped.** | Endorse **with ADV-208**: `snippet` and `raw` are additional separately-requestable levels; either drop them for this release or extend the commitment. |
| **H-6** `PERF-01` at risk | **Yes.** | **Understated.** | See **ADV-108**: A.7's L0/L1 cost models omit the map entirely, so the p50 risk H-6 names is larger than the published cost model implies, and the same omission produces an R-01/PART-01 conformance failure, not just a latency one. |

**Comparable defects the architecture did NOT flag**, in descending order of severity:
**ADV-001** (no `withheld` policy — I-1 fails on the modal lexical query), **ADV-002** (cache-served
handle re-verification is a tautology), **ADV-003** (the "non-negotiable" floor and the 25-thread pool
map both exceed the document's own 9,000-token ceiling), **ADV-004** (`exact_signal_match` undefined
and absolute), **ADV-101** (LR has no watermark and is mispriced), **ADV-102** (PF-2's failure branch
mischaracterised), **ADV-107** (no concurrency model; no process-level quota control),
**ADV-210** (model-hub revalidation on load).

---

## 3. Gameability: the dumbest implementation consistent with this architecture

Per `AGENT_LOOP.md` §7.5, applied to the architecture's own commitments.

**The degenerate build.** Implement §A and §D literally, and make six free choices the document leaves
open:

1. Define `exact_signal_match` broadly — any quoted phrase or any query token with corpus frequency
   below a threshold, with `hit_count ≥ 1` (ADV-004).
2. Never populate `withheld[]`; the document never says to (ADV-001).
3. Set the L5 selection threshold high, so `H_semantic` is near-empty (ADV-109, legalised by H-5).
4. Implement `answer_type_presence` with a permissive token regex (any `\d{1,2}[/-]\d` or month name
   for *when*; any digit for *how much*), so it is almost always `true` and never downgrades (ADV-104).
5. Serve handle redemption from the LRU (ADV-002).
6. Batch everything, so proxy-observed network calls stay at 3 (ADV-106).

**What it passes.** LEX-01, LEX-04 (rungs = 1 on anything token-unique), AD-02, AD-04 (≤3 network
calls, 0 model calls), SEM-04 (zero embeddings on easy families — by making most families "easy"),
RANK-01 (never reranks on exact-signal), PERF-01/PERF-04 (cheap because it stops early), MCP-06
(mutate-then-redeem cannot fail), EV-01 (`H` is small by construction), EV-03, PART-01…PART-05 on
short threads, INJ-01…INJ-06, SEC-01…SEC-06, OBS-01, NFR-01/NFR-03.

**What should catch it, and why it might not.** The intended catchers are AD-05 (≥80% recovery on hard
families), EV-02 (per-position recall), SEM-01 and CG-SEM's F11 `semantic_gain`. Three of the four are
weakened by the same defect:

- **The F11 bar is self-referential.** CG-SEM's `semantic_gain` is a *delta against the G0-measured
  SEM-OFF distribution on the same seed* (`EVALUATION_PLAN` §13.5 explicitly replaced the absolute +15
  with this). SEM-OFF is the same binary with the semantic rung disabled. On every case where D.3 rule
  1 stops at L0, SEM-ON and SEM-OFF behave **identically**, so those cases contribute exactly zero to
  the delta in both arms. The reference distribution is contaminated by the defect it is meant to
  detect. A broad `exact_signal_match` removes F11 cases from the measurement rather than failing it.
- **AD-05's denominator is chosen by the same predicate.** "Of cases where the initial route surfaced
  no evidence, ≥80% recovered" — a build that stops confidently at L0 surfaces *some* evidence (the
  decoy), so those cases never enter the denominator.
- **EV-02 survives.** The position sweep on F3 is the one guard the degenerate build genuinely cannot
  dodge, because F3's evidence is buried in a thread it must map and disclose regardless of routing.

**Conclusion.** The architecture's escalation guarantees are gated on one undefined predicate whose
breadth simultaneously (a) makes six criteria easy, (b) shrinks the denominators of the two criteria
meant to catch that, and (c) contaminates the reference distribution of the third. ADV-004's required
fix — define it, restrict rule 1's absoluteness, and publish its firing rate per family as a
pre-registered number — is the single highest-value change in this review.

---

## 4. Verdict

### **NEEDS REWORK.**

Not "approve with amendments": four findings are BLOCKER-severity under `AGENT_LOOP.md` §4 (violated
product invariant or mandatory criterion), three of them are arithmetic contradictions inside the
document rather than judgement calls, and one (ADV-004) is a structural gameability lever that
weakens the rubric's own guards. `AGENT_LOOP.md` §5 step 6 closes a round only at zero open BLOCKER
and zero open HIGH.

This is a genuinely strong document in most respects, and the rework is bounded. Its number
discipline ([VERIFIED] / [DESIGN] / [PRE-REG] / [TBM]) is honest and I found **no unlabelled latency
claim asserted as measurement** — B.7's admission that no CPU figure exists for any candidate model is
exactly right, and §G's falsifier table is the best part of the document. §E's Deferred list was
checked item-by-item against SC §§3–7 and §15 and **nothing in it belongs to the complete product**;
Chosen contains no gold-plating I would cut, with ADV-214 (the hand-rolled Gmail client) the only
scope item I would push back on. The problems are concentrated in the places the document had to do
arithmetic across sections written at different times, and in two tension rows (T-RC2, T-CD2) that
were resolved by naming instruments that do not measure them.

### Findings by severity

| Severity | Count | IDs |
|---|---|---|
| BLOCKER | 4 | ADV-001, ADV-002, ADV-003, ADV-004 |
| HIGH | 10 | ADV-101 … ADV-110 |
| MEDIUM | 14 | ADV-201 … ADV-214 |
| LOW | 4 | ADV-301 … ADV-304 |
| **Total** | **32** | |

### Required amendments before approval

**Round-blocking (all BLOCKER and HIGH):**

1. **ADV-001** — Specify the disposition of every ID entering `H`: mandatory `withheld` records with
   cap-naming reasons and affordances; a declared scan-scope field; a stated page budget and a
   definition of `H` over pages.
2. **ADV-002** — Remove the LRU from handle redemption, or add an independent
   `history.list`-based staleness check plus a non-restamped `fetched_at`, and require MCP-06's test
   to run cache-warm.
3. **ADV-003** — Rename the pool cap (`max_pool_threads`) and state pool ≠ source; publish the
   degradation precedence order under the 9,000-token ceiling; amend T-CD2 to state the floor is
   budget-bounded; fill T-CD2's empty `Reversed by`.
4. **ADV-004** — Define `exact_signal_match` normatively; restrict D.3 rule 1's absoluteness to
   `rfc822msgid:` and `hit_count == 1`; evaluate `answer_type_presence` before the stop otherwise;
   pre-register its per-family firing rate at G0.
5. **ADV-101** — State where the `historyId` watermark persists; correct LR's cost to `2 + 20n` with a
   capped `n`; state the client-side re-check subset and its provenance string.
6. **ADV-102** — Rewrite PF-2's failure branch: it is a design change, and the stated fallback costs
   the whole per-minute budget. Name the alternative pool-text source or the reduced pool bound.
7. **ADV-103** — Restate B.8's asymmetry as "one API covering all three inference jobs"; rewrite R1 as
   single-conjunct on stage-A quality with a design (not stack) consequence; add a Node arm to PF-4 or
   delete R1/R2.
8. **ADV-104** — Repoint T-RC2 and A.8 at CG-AD and CG-SEM; delete the PF-9 reference; add the
   `answer_type_presence` base-rate measurement at G0.
9. **ADV-105** — Scale L2's probe budget with constraint count, or add an `empty_diagnosis:
   "incomplete"` state; flag ROUTE-04's unconditional 100% bar to the owner.
10. **ADV-106** — Split `http_requests` from `api_calls` in the trace and the caps; bind OBS-04 to the
    former; recommend AD-04's "≤3 network calls" be re-expressed.
11. **ADV-107** — Add a process-wide quota token bucket, a concurrency statement, single-flight model
    loading, retry accounting, and the mid-rung timeout contract; add a suite-level quota budget to §F.
12. **ADV-108** — Correct A.7's L0/L1 cost lines to include map fetches; state that `max_map_threads`
    never applies to hit-bearing threads; re-derive `max_quota_units`.
13. **ADV-109** — Amend H-5's request: declared pre-registered shortlist size, pool enumerated by ID in
    the trace, and explicit coverage of D.5 step-(b) probe results.
14. **ADV-110** — Add a `basis` field to score provenance; forbid mixed-scale ranking within one fill;
    state the fallback rule.

**Recommended in the same pass (MEDIUM, cheap while the document is open):** ADV-201 (rate table and
endpoint list), ADV-202 (name the HTML/quote parsers), ADV-203 (content-decoding pipeline), ADV-204
(timezone policy), ADV-205 (seed-profile second condition), ADV-206 (error taxonomy), ADV-207 (drop
`messages.attachments.get`), ADV-209 (make the PART-01 discrepancy gate-binding), ADV-210 (offline
model loading), ADV-213 (structural harness isolation).

**Escalations to the owner** (`AGENT_LOOP.md` §8 — a criterion unachievable as written, or a change to
a settled principle):

- **H-1 as flagged** — reword DISC-02. Endorsed, with §8.7's narrowing rule added.
- **H-2 as flagged, plus ADV-209** — reword PART-01 *and* attach a gate-binding discrepancy bound.
- **H-4 as flagged, plus ADV-210** — allowlist OAuth **and** the setup-time model host; require
  runtime offline mode.
- **H-5 as amended by ADV-109** — do not adopt H-5's wording as written.
- **ADV-105** — ROUTE-04's unconditional 100% empty-diagnosis correctness is unachievable for queries
  with more constraints than the relaxation probe budget.
- **ADV-106** — AD-04/CG-AD's "median network API calls ≤ 3" does not bound cost under HTTP batching.

### Re-review scope

A fix round should be re-reviewed by **R-RETR** (ADV-001, 004, 101, 105, 108, 109), **R-DISC**
(ADV-003, 208, 209, 304), **R-MCP** (ADV-002, 212), **R-PERF** (ADV-106, 107, 211), **R-SEC**
(ADV-205, 210, 213), **R-ARCH** (ADV-103, 201, 214), and a second adversarial pass on §3's degenerate
build once `exact_signal_match` is defined.
