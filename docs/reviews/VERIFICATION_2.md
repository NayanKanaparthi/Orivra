# VERIFICATION_2.md — Independent verification pass against the four binding owner decisions

**Reviewer:** independent verification agent (did not author any of the documents under review).
**Date:** 2026-08-30.
**Authority applied:** `docs/OWNER_DECISIONS.md` RESOLUTIONS OD-1…OD-4, which are binding and were
decided **after** the Round-1 repairs. Where a document conflicts with a resolution, the document changes.
**Scope discipline:** the owner has ordered the specification to stop growing. Nothing below is proposed
for completeness, symmetry or tidiness. Every proposed edit removes a defect that blocks implementation,
and each is the smallest edit that removes it. **No document was rewritten by this pass.**

---

## BLOCKING findings

### B-1 · OD-2 violation + missing mapping — the response has no state that separates "exhausted" from "gave up", and the evaluation plan explicitly legalises collapsing them

**Class.** Owner-decision violation (OD-2), compounded by a missing mapping (a mandatory response
obligation with no schema field and no measurement).

**Locations.**

- `ARCHITECTURE_DECISION.md` **D.2** (response schema sketch, the `retrieval_report` block, lines ~1096–1113):
  the block carries `rungs`, `hit_count_per_rung`, `scan_scope`, `pool`, `shortlist`, `not_tried[]`,
  `empty_diagnosis`, `budget_caps_hit`, `sufficiency`, `counters`. **There is no field naming the outcome
  of the call.** A zero-evidence response produced after a clean exhaustion of every applicable rung and a
  zero-evidence response produced because `max_quota_units` fired at L2 are **byte-identical in shape**;
  they differ only in whether `budget_caps_hit` happens to be non-empty, which is an inference the caller
  must make, not a state the server asserts.
- `ARCHITECTURE_DECISION.md` **D.3 stopping rules 5 and 6** (lines ~1159–1162): rule 5 says a cap
  exhaustion stops, emits, names the cap and the untried rungs; rule 6 says "**Never** a bare empty
  result." Neither rule states what the *result* is. Nothing forbids a cap-exhausted empty result from
  being presented as a negative finding.
- `ARCHITECTURE_DECISION.md` **D.11** (error taxonomy): `budget_exhausted`, `upstream_rate_limited`,
  `process_quota_refused`, `semantic_unavailable` are all **in-band on a successful response** by the
  partition rule. That is correct for partiality, but it means every one of OD-2's "escalation path not
  executed" causes arrives as a side field on an otherwise ordinary response.
- `EVALUATION_PLAN.md` **§7.4, definitional bar 1** ("No unexplained not-found", line ~969) — the direct
  contradiction: *"For every case whose terminal class is `not_found`, the trace must show either (a) the
  escalation ladder ran to exhaustion, **or (b) an explicit budget cap was hit and the response surfaced
  that fact to the caller**."* Clause (b) is exactly the case OD-2 says must **never** be `NOT_FOUND`.
- `EVALUATION_PLAN.md` **§6.1** (FNF definition) and **§6.3** (`terminal_class(answered|not_found|other)`,
  line ~843): the terminal-class vocabulary is two-valued plus a residual. There is no class for
  `INCONCLUSIVE`, so the distinction OD-2 makes "a first-class, machine-checkable property" cannot be
  measured at all, and a budget-exhausted negative is either miscounted as a false not-found or swept
  into `other` where nothing binds it.

**Why it blocks.** OD-2 is a statement about what MailWeave promises users, and it requires a response
state the server does not have. An implementer building to the current schema cannot emit the required
distinction, a reviewer cannot check it, and the one place in the corpus that defines when a `not_found`
is legitimate (`EVALUATION_PLAN.md` §7.4 bar 1) currently *authorises* the behaviour OD-2 forbids —
and it is a `[DEFINITIONAL]`, BLOCKER-classed bar cited by the rubric's own How-to-use list and by
`EVALUATION_PLAN.md` §12's linkage row for `AD-01…AD-05`. Left as written, an implementation that
returns `not_found` after hitting a quota cap passes the gate.

**Minimal fix (four edits, no new criterion and no new contract clause).**

1. `ARCHITECTURE_DECISION.md` **D.2**: add one field to `retrieval_report` —
   `"outcome": "answered" | "not_found" | "inconclusive"` — with the field note:
   *`not_found` is emitted only when every applicable rung was executed and exhausted: `not_tried[]`
   contains no entry whose `why` is a budget, cap, timeout or error, and `budget_caps_hit` is empty.
   Any applicable rung skipped for budget, cap, timeout or error makes the outcome `inconclusive`.
   `not_found` is a claim about the routes executed, never about the mailbox.*
2. `ARCHITECTURE_DECISION.md` **D.2**: constrain the existing `not_tried[].why` to a closed two-way
   tag — `not_applicable` versus `budget|cap|timeout|error` — so rule 1 is machine-checkable. (The field
   already exists and already carries free text; this only closes its vocabulary.)
3. `ARCHITECTURE_DECISION.md` **D.3**: append to rule 5 — "…and the outcome is `inconclusive`, never
   `not_found`" — and to rule 6 — "…and `not_found` requires an empty applicable-`not_tried` set."
4. `EVALUATION_PLAN.md` **§7.4 bar 1**: delete clause (b) and replace the bar with —
   *"For every case whose terminal class is `not_found`, the trace must show the escalation ladder ran
   to exhaustion over every applicable rung. A `not_found` emitted while an applicable rung was skipped
   for budget, cap, timeout or error is a Recoverability Invariant violation and a BLOCKER; the correct
   terminal class for that case is `inconclusive`, which must be surfaced to the caller with the cap, the
   untried routes and their affordances."* And in **§6.1 / §6.3**, extend the terminal-class vocabulary
   to `answered | not_found | inconclusive | other`, classify from `retrieval_report.outcome` when
   present, and state that `inconclusive` is **not** counted in FNF and is reported as its own rate
   alongside FNF and hallucinated-found.

Rubric `EV-04` ("Classification per EP §6.1, explicit machine-readable field preferred"), `AD-03` and
`ROUTE-01` then bind the new state without amendment. **Do not add a rubric criterion for this.**

---

### B-2 · OD-2 violation + impossible acceptance criterion — ROUTE-04 still binds at absolute 100 %, which OD-2 has now ruled out

**Class.** Impossible acceptance criterion, now also an owner-decision violation.

**Locations.**

- `RELEASE_RUBRIC.md` **§7, ROUTE-04** (lines ~587–606): *"correctness of this diagnosis on constructed
  cases = **100 %**"*, followed by *"Owner decision pending — `OWNER_DECISIONS.md` **OD-2**; the criterion
  above is **unchanged and binding at 100 % until it is answered**"*, and *"This rubric does not pick."*
- `ARCHITECTURE_DECISION.md` **§H-7** (lines ~1810–1822) and **§I O-1**: the arithmetic proof — with `k`
  parsed constraints and `max_relax_probes = min(k, 6)`, correct diagnosis over *untried* drops is
  unreachable for `k > 6` at any budget short of `k`.
- `EVALUATION_PLAN.md` **§13.4** (CG-AD and the other gates): **no registered ceiling on the
  incomplete-diagnosis rate exists anywhere in the plan.**

**Why it blocks.** OD-2 has been answered, and the answer selects the "promise over what we tested and
disclose the rest" form: it mandates `INCONCLUSIVE` whenever an applicable path was skipped for budget or
cap, and mandates that the negative result report routes not tried. The alternative form — keep the
absolute promise and cap the constructed set at six constraints — would need no `INCONCLUSIVE` state at
all, so OD-2's text rules it out. ROUTE-04 as written therefore now (a) contradicts a binding resolution
and (b) remains provably unsatisfiable for `k > 6`, while being flagged `M` — mandatory, `NOT TESTED`,
and `NOT TESTED` blocks release exactly like `FAIL`. A criterion that cannot pass blocks the gate
permanently, and its self-imposed "unchanged until the owner rules" clause has expired.

**Minimal fix (two edits).**

1. `RELEASE_RUBRIC.md` **ROUTE-04 acceptance**: re-scope to the drops actually attempted —
   *"On zero-hit outcomes where dropping exactly one constraint restores results **and that drop was
   among the drops actually probed**, the report names that constraint and the count it restores;
   correctness over probed drops on constructed cases = **100 %**. Where the probe budget ran out before
   all single-constraint drops were tried, `empty_diagnosis.status` is `incomplete`, `untried_drops` is
   complete and the response outcome is `inconclusive` (B-1). The incomplete-diagnosis rate is bounded by
   `[UNSET — register at G0 per EP §13.2 against the G0-measured constraint-count distribution]`."*
   Replace the "Owner decision pending" paragraph with a one-line pointer to OD-2 as decided.
2. `EVALUATION_PLAN.md` **§13.4 CG-AD**: add the one registered cell —
   *"incomplete-diagnosis rate `[UNSET — registered at G0 per §13.2]`"* — which is the single number
   OD-2's chosen option says must be registered before the gate. EP §4's constructed relaxation cases
   stay **uncapped**; capping them belongs to the option OD-2 did not take.

---

### B-3 · OD-4 violation — Stage 1 of the forensic ladder surfaces personal-mail text with no per-incident owner approval, and five documents still present the access question as open

**Class.** Owner-decision violation (OD-4).

**Locations.**

- `EVALUATION_PLAN.md` **§2.4.6**, the ladder table, **Stage 1 row, Gate column**: *"Engineer-initiated,
  never automatic."* Stage 1 is `mailweave inspect <trace_id>`, which re-fetches real message bodies live
  and **prints them to the terminal** — i.e. it *surfaces* actual personal-mail text. OD-4 requires
  explicit, per-incident owner approval for exactly that. "Engineer-initiated" does not distinguish an
  implementer agent from the owner, which is the whole question OD-4 answers. Stage 0 (content-free) and
  Stage 2 (redacted snippet, already carrying "owner approval recorded in the finding") are both correct
  as written; only Stage 1 is unresolved.
- Still-open pointers that OD-4 has now closed and which contradict it by implying no rule exists yet:
  `EVALUATION_PLAN.md` **§14 Q17** (residual question) and **§16 item 4**; `RELEASE_RUBRIC.md`
  **For owner decision, item 4** (line ~1567); `PRODUCT_CONTRACT.md` **§10 item 4** (line ~637);
  `ARCHITECTURE_DECISION.md` **§I** (line ~1887).

**Why it blocks.** `mailweave inspect` must be **built and PF-8 green before G0 closes**
(`EVALUATION_PLAN.md` §13.3), and OD-4 changes what the tool must be: a diagnostic that is
metadata/ID/timing/structure-only may run autonomously, while any mode that persists or surfaces mail
text needs a recorded per-incident owner approval. That is a build-time capability split and an approval
record, neither of which any document specifies. An implementer today reads "open owner decision" in five
places and either builds no gate — in which case an agent surfaces the owner's mail without approval,
a privacy violation the loop classes BLOCKER — or invents one.

**Minimal fix (one table cell plus five pointer closures).**

1. `EVALUATION_PLAN.md` **§2.4.6, Stage 1, Gate column**: replace *"Engineer-initiated, never
   automatic"* with —
   *"Owner-approved **per incident** (OD-4), recorded in the finding, because the session surfaces real
   message text. Metadata / ID / timing / structure-only diagnostics — Stage 0, and any `inspect` mode
   that emits no mail text — need no approval and may be run autonomously by an agent. Never automatic.
   Transient in-memory retrieval during ordinary query execution is unaffected. `mailweave inspect` must
   be built and PF-8 green before G0 closes (§13.3)."*
   The existing write-path audit (§2.4.7) and Stage 2's approval mechanism are unchanged and already
   cover the rest.
2. Close the five "open OD-4" pointers by marking them **DECIDED — see `OWNER_DECISIONS.md` OD-4**. No
   other text moves; no rubric criterion is added (SEC-05/SEC-06 and the §2.4.7 write-path audit already
   carry the mechanism, and OD-4 is an access rule, not a new mechanism).

---

## NON-BLOCKING

**Required registration action, not a document defect — OD-1's number can now be written in.**
The Freshness Service Level is `[UNSET]` in `RELEASE_RUBRIC.md` FRESH-05, `EVALUATION_PLAN.md` §11.2.2
and §13.4 CG-FRESH, all three of which correctly refuse to invent it and require only the owner's entry
plus a timestamp. OD-1 supplies it. The string to write into **experiment log 001, before the FRESH-01
probe run starts**, is: *"FSL = p90 lag ≤ 60 s, measured from H0 / history-confirmed arrival, applying to
arm H5 (and to H6 after any mitigation), evaluated independently in each of the depth strata 0, 5 and 25;
pooling across strata is prohibited. Second, independent trigger: any confirmed real-mail false negative
is a defect regardless of percentile and forces the mitigation build."* No document edit is needed —
FRESH-01 already requires per-stratum measurement with pooling prohibited, FRESH-05 gates on the entry's
timestamp not its value, and MF2/MF5 read the FSL from the log.

- **MF4 is narrower than OD-1's second trigger.** `EVALUATION_PLAN.md` §11.2.3 MF4 and `RELEASE_RUBRIC.md`
  FRESH-02 both scope the real-mail false-negative trigger to "**Tier-1 D6**" instances. OD-1 says *any*
  confirmed real-mail false negative. A `missed-but-exists` verdict from a D4 real query session on
  recent mail is the same evidence and would not fire MF4 as worded. One-word fix when either file is
  next touched: "any Tier-1 instance (D4 `missed-but-exists` or D6)".
- **OD-3 ratifies the existing repair and changes nothing.** The previously-reported token-ceiling
  conflict (ARCH_REVIEW ADV-003, recorded at `ARCHITECTURE_DECISION.md` §C T-CD2, A.9a and §H-9) is
  **resolved, not re-opened**: A.9a already separates floor *membership* (never negotiable) from floor
  *depth* (declared, degradable to `snippet`), which is stricter than OD-3's "at least stubs" floor, and
  the degradation precedence already degrades floor bodies after hit bodies, which is OD-3's "promoted
  when the evidence depends on them". `PRODUCT_CONTRACT.md` C-06 and §10 item OD-3 already state the
  narrowed claim. No edit required.
- **OD-3 did not pre-authorise an F17-failure branch.** `ARCHITECTURE_DECISION.md` §H-9 leaves a three-way
  owner choice (raise the ceiling / disclose fewer hits at body depth / accept the narrower claim) if F17
  shows the floor at the budget-produced depth does not beat Baseline F(±2). OD-3's "structurally
  necessary parents and children are promoted" reads as branch (i), but not explicitly. If F17 fails,
  the gate escalates under `AGENT_LOOP.md` §8 rather than stalling silently. Note it; do not pre-empt it.
- **Stale "open owner item" sections.** `PRODUCT_CONTRACT.md` §10, `RELEASE_RUBRIC.md` "For owner
  decision", `EVALUATION_PLAN.md` §16 and `ARCHITECTURE_DECISION.md` §I all still present OD-1…OD-4 as
  pending. `OWNER_DECISIONS.md`'s own header makes them superseded, so no reader is misled about
  authority, but the four sections will mislead about *status* until they are marked decided. Fold this
  into the B-1…B-3 edits rather than as a separate pass.
- **`sufficiency` is not an outcome.** `ARCHITECTURE_DECISION.md` A.8 / D.2's `sufficiency`
  (`sufficient` / `insufficient` / `ambiguous`) is a per-rung evidence verdict and is easy to mistake for
  the B-1 outcome field. Keep them distinct; do not overload `sufficiency`.

---

## What I read and checked

**Read in full:** `SCOPE_CORRECTION.md`, `AGENT_LOOP.md`, `PRODUCT_CONTRACT.md`, `OWNER_DECISIONS.md`.
**Read in full where load-bearing, section-targeted elsewhere:** `RELEASE_RUBRIC.md` (How-to-use and
class markers; the full 113-criterion status table; §1 EV-01…EV-06, §6 AD-01…AD-05, §7 ROUTE-01…ROUTE-04,
§8 DISC-01…DISC-06, §12 FRESH-01…FRESH-06, §14 SEC-01…SEC-08, the release gate, the "For owner decision"
section and both repair logs); `ARCHITECTURE_DECISION.md` (A.7 ladder and global caps, A.7a hit
disposition, A.8/A.8a/A.8b sufficiency and `exact_signal_match`, A.9 disclosure, A.9a degradation ladder,
D.2 response schema, D.3 stopping rules, D.4 shipped depth and budgets, D.11 error taxonomy, §C T-CD2,
§H-1…§H-10, §I O-1…O-9); `EVALUATION_PLAN.md` (§2.4.4–§2.4.7 redaction and the forensic ladder, §2.5
D1–D8, §6.1–§6.4 metrics and assertions, §7.4 escalation bars and the trigger ablation, §7.5.1 depth arm,
§11.1–§11.2.5 freshness protocol and mitigation triggers, §12 rubric linkage, §13.2–§13.5 pre-registration
and gates, §14 and §16, both repair logs).
**Consulted only to check whether a previously-reported defect is still live:** `ARCH_REVIEW_1.md`,
`CONSISTENCY_AUDIT_1.md` — searched for prior findings on not-found semantics (none exists; B-1 is new
with OD-2) and confirmed ADV-003's token-ceiling conflict is closed by A.9a.
**Not read, per scope:** `RETRIEVAL_OPTIONS.md`, `ROUTING_OPTIONS.md`, `CONTEXT_DISCLOSURE_OPTIONS.md`,
`VERIFIED_RESEARCH.md`, `SECURITY_NOTES.md`, `docs/archive/`.

**Checks performed.** Each of OD-1…OD-4 traced clause-by-clause into every document it touches. Whole-set
searches for the OD-2 vocabulary (`not_found`, `inconclusive`, `exhaust`, `nonexistence`) across all four
large documents — the architecture contains **no** occurrence of any negative-result state, which is the
evidence for B-1. Contract-MUST → rubric-criterion → architecture-mechanism → EP-measurement chains walked
for the freshness, empty-result, disclosure-floor and forensics obligations. The 113-criterion status table
was checked for the criteria the four resolutions touch (EV-04, AD-03, ROUTE-01…04, DISC-01/05,
FRESH-01…06, SEC-05/06).

**Deliberately not raised.** Design choices I would have made differently; gaps that are merely untidy;
anything whose only justification would be completeness or symmetry. Three areas that look like gaps and
are not: `raw` appearing in the depth vocabulary while being non-requestable (deliberate, ADV-208, and
measured under DISC-05); `AD-04`'s two call counters (deliberate, §H-8); pool membership creating no stub
rows (deliberate, A.7a, and the resolution of a prior arithmetic contradiction).

---

## Verdict

**Safe after the listed blocking fixes.**

The Round-1 repairs hold. OD-1 and OD-3 need no document changes at all — the freshness protocol already
stratifies at depths 0/5/25 and prohibits pooling, MF4 already makes a confirmed real-mail false negative
mitigation-forcing, and the reply-chain floor was already restated as membership-plus-declared-depth,
which is stricter than OD-3 requires. OD-1's only outstanding item is registering the now-decided number
in experiment log 001 before the probe run.

OD-2 is the real one, and the review brief's assessment of it is correct: the architecture's response
schema, its stopping rules and its budget-exhaustion paths **do** collapse "we looked everywhere
applicable" and "we ran out of budget" into one indistinguishable negative result, and
`EVALUATION_PLAN.md` §7.4's definitional bar does not merely permit that collapse — it writes it down as
acceptable. Until B-1 is applied there is no state for the implementer to emit and no measurement for the
reviewer to check, and until B-2 is applied a mandatory criterion sits at a bar its own architecture has
proved unreachable. B-3 is smaller in surface but is a privacy control on a G0 deliverable, and the
specification currently tells the implementer that the rule does not exist yet.

All three fixes are local, total roughly a dozen lines across three documents, add **no** new rubric
criterion, **no** new contract clause and **no** new capability, and shrink one criterion's scope rather
than growing it. With them applied, implementation may proceed.

---

## Addressed (2026-08-30)

- **B-1 — ADDRESSED.** `retrieval_report.outcome` (`answered|not_found|inconclusive`) plus the closed `not_tried[].why` vocabulary added at `ARCHITECTURE_DECISION.md` D.2 (schema + field notes), outcomes appended to D.3 stopping rules 5 and 6; `EVALUATION_PLAN.md` §7.4 bar 1 clause (b) deleted (BLOCKER-classed), and `inconclusive` added to the terminal-class vocabulary by preserved-block extension notes in §6.1 and §6.3.
- **B-2 — ADDRESSED.** `RELEASE_RUBRIC.md` ROUTE-04 re-scoped to drops actually probed at 100 % with an `[UNSET — register at G0]` incomplete-diagnosis ceiling and the "pending" note replaced by the OD-2 ruling; the matching registered cell added at `EVALUATION_PLAN.md` §13.4 CG-AD. §4's constructed cases untouched.
- **B-3 — ADDRESSED.** `EVALUATION_PLAN.md` §2.4.6 Stage 1 gate cell now reads owner-approved per incident, recorded in the finding, with structure-only diagnostics autonomous; four of the five stale OD-4 pointers marked decided (EP §14 Q17, EP §16 item 4, `RELEASE_RUBRIC.md` "For owner decision" item 4, `ARCHITECTURE_DECISION.md` §I). The fifth, `PRODUCT_CONTRACT.md` §10 item 4, was outside this pass's permitted file set and is still open in wording only.
