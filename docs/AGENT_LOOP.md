# AGENT_LOOP.md — The Implementer/Reviewer Loop

**Status:** authoritative process definition.
**Governed by:** `docs/SCOPE_CORRECTION.md` §17.
**Criteria authority:** `docs/RELEASE_RUBRIC.md`. This document defines the *machinery*;
the rubric defines *what must be true*. Neither may be relaxed by an agent inside a loop.

---

## 1. The core rule

> **No agent may certify its own work.**

An implementer's claim that something is done is an unverified hypothesis. Rubric criteria
move to `PASS` only when a reviewer that did not write the code reproduces the evidence.
This is the single property the whole loop exists to protect.

---

## 2. Roles

### 2.1 Orchestrator (the main session)

Owns the round. Issues work orders, dispatches reviewers, consolidates findings, updates
the rubric status table, decides round exit, escalates to the human. Never writes
production code itself during a review-governed workstream — otherwise it becomes an
implementer reviewing itself.

### 2.2 Implementer agent

Receives: the work order, `PRODUCT_CONTRACT.md`, `ARCHITECTURE_DECISION.md`,
`RELEASE_RUBRIC.md` (the criteria it must satisfy), the open findings ledger, and the
codebase. Writes code and tests. Runs the full local suite before handing back. Produces a
`HANDOFF.md` describing what changed and **what it did not do or could not verify** —
honest gaps are part of the deliverable, not a failure.

An implementer may never edit: the rubric, the contract, the findings ledger's severity
fields, or any reviewer's report.

### 2.3 Reviewer agents

Independent auditors, one per domain. Each receives the rubric criteria in its domain, the
diff, the codebase, and the ability to execute tests. Each is explicitly instructed **not**
to trust `HANDOFF.md` claims and to verify by execution.

Minimum reviewer set (per `SCOPE_CORRECTION.md` §17):

| ID | Domain |
|----|--------|
| R-RETR | Retrieval correctness — evidence preservation, escalation, ranking, false-negative behavior |
| R-DISC | Progressive disclosure and context representation — partiality, map integrity, budgets |
| R-ARCH | Architecture and code quality — structure, contracts, dead abstractions, test quality |
| R-SEC  | Security and privacy — scopes, secrets, trace redaction, injection handling |
| R-PERF | Performance — latency, API call counts, quota behavior, adaptive-cost invariant |
| R-MCP  | MCP protocol and tool quality — schema correctness, handle discipline, client usability |
| R-GMAIL| Real Gmail integration — E2E against live mail, MIME/header reality, freshness |
| R-DOC  | Documentation accuracy and claim discipline — README and public claims against the measured numbers and the experiment log, unbundled claims, stated limitations, prior art |

Not every round needs all eight. The work order names the required reviewers; any reviewer
whose domain the diff touches is mandatory.

### 2.4 Adversarial reviewer (periodic)

At minimum before any release gate: one reviewer whose sole brief is to **defeat** the
rubric — find a way the implementation passes every criterion while being wrong, hollow, or
gamed. Its findings are treated as BLOCKER-eligible.

---

## 3. Isolation

- The implementer works in a dedicated git worktree/branch. Reviewers read that branch.
- Reviewers are read-only with respect to source: they may run tests and write only to
  `docs/reviews/`.
- Ground truth for benchmarks (case manifests, seed maps) is never readable from the server
  source tree. A reviewer that finds the server able to read ground truth files must raise a
  BLOCKER regardless of behavior.
- Reviewer instances are **fresh per round**. A reviewer never sees its own previous
  approval, which removes the incentive to defend an earlier verdict.

---

## 4. Finding schema

Every finding is a record, not a comment. Free-form review prose without these fields is
rejected and the reviewer is re-run.

```
ID:            R-RETR-003
Severity:      BLOCKER | HIGH | MEDIUM | LOW
Rubric:        <criterion ID from RELEASE_RUBRIC.md, or "none — out-of-rubric defect">
Location:      <file:line or tool/endpoint>
Reproduction:  <exact command, test name, or MCP call sequence>
Expected:      <what the contract/rubric requires>
Actual:        <what was observed, with output>
Required fix:  <what must change; not necessarily how>
```

**Severity definitions**

| Severity | Meaning |
|----------|---------|
| BLOCKER | Violates a product invariant, a mandatory rubric criterion, or a privacy/security constraint. Release-blocking and round-blocking. |
| HIGH | Materially wrong behavior, missing mandatory capability, or a test that passes for the wrong reason. Round-blocking. |
| MEDIUM | Real defect with a bounded workaround; may be scheduled to a later round by explicit orchestrator decision recorded in the ledger. |
| LOW | Quality, clarity, or maintainability. Never blocks, never silently dropped. |

A reviewer reporting **no findings** must still state what it executed and what it read.
"Looks good" with no execution record is itself treated as a failed review and re-run.

---

## 5. Round protocol

```
1. WORK ORDER      orchestrator: scope, target rubric criteria, required reviewers,
                   open findings assigned to this round
2. IMPLEMENT       implementer agent: code + tests, full local suite green
3. HANDOFF         implementer: HANDOFF.md incl. explicit "not done / not verified"
4. REVIEW          required reviewers run IN PARALLEL, independently, fresh instances
5. CONSOLIDATE     orchestrator: merge findings, dedupe, resolve reviewer disagreement,
                   update docs/reviews/ROUND_N/ and the findings ledger
6. GATE            round closes only if: zero open BLOCKER, zero **reachable** open
                   HIGH, every criterion this round targeted is PASS (reviewer-
                   confirmed), and no criterion regressed from PASS
7. FIX             if gate fails: findings go back to the implementer as the next
                   work order. Return to step 2.
```

Fix rounds are re-reviewed by the **same domains** that raised the findings, plus a
regression pass over previously-PASSed criteria the diff could plausibly affect.

### 5a. Reachability — the gate's stopping rule (added after round 14)

A finding is **reachable** when code that exists today can trigger it. A finding the
reviewer who raised it describes as *inert*, *having no consumer*, *not reachable via any
path*, or *not yet live* is **DEFERRED** in the ledger to the workstream that would make it
reachable, and returns there with its reproduction attached.

**Why this rule exists.** Rounds 12-14 closed twelve findings; nineteen were described by
their own reviewers as unreachable. `envelope/` was touched by eleven review rounds and
`retrieval/` by one, while fourteen of twenty workstreams stood unbuilt. Round 11's R-SEC
wrote "Don't gate on R-SEC-039/040 — neither reaches an actual write today. Treat both as a
hard precondition on WS-16's design"; the orchestrator fixed them immediately instead, and
three rounds followed from that.

The old gate has no fixed point. Adversarial reviewers pointed at in-process Python objects
will always find another reconstruction path and always another claim slightly wider than its
code — so "no open finding" is not a condition that can be met, only approached. Reviewers
also look hardest at whatever changed most recently, so re-reviewing a sealed module
manufactures the findings that justify re-reviewing it again.

**What this rule is not.** It is not permission to defer anything inconvenient.

  * Severity is never downgraded to make a finding deferrable. Reachability and severity are
    separate axes and both are recorded.
  * Only the reviewer who raised a finding can characterise it as inert. The orchestrator may
    not infer it, and an implementer may never assert it.
  * A deferred finding is **blocking** in the round it returns to, and that round may not
    close without it.
  * Anything reachable today is fixed today, whatever its severity.

**Review effort follows new code.** A fix round re-reviews what it changed. It does not
re-review a module that has already passed its gate unless the diff touches it.


---

## 6. Rubric status discipline

Every criterion in `RELEASE_RUBRIC.md` carries exactly one status:

- `PASS` — a reviewer reproduced the acceptance evidence. Only a reviewer may set this.
- `FAIL` — measured and does not meet the criterion.
- `BLOCKER` — fails and blocks release; also used for a violated invariant.
- `NOT TESTED` — not yet evaluated. **`NOT TESTED` blocks release exactly like `FAIL`.**
  It may never be presented as a soft pass, and no criterion may reach release in this
  state.

The status table lives in the rubric, is updated by the orchestrator from reviewer
reports only, and every transition records the round number and the reviewer ID.

---

## 7. Anti-gaming rules

These exist because a sufficiently motivated implementer can satisfy tests without
satisfying reality. Each is a reviewer obligation.

1. **Execution over assertion.** Reviewers run the tests themselves. A green CI badge in
   `HANDOFF.md` is not evidence.
2. **Read the test, not just the result.** A test that hardcodes an expected message ID,
   special-cases a benchmark query string, or asserts a tautology is a HIGH finding even
   if the feature works.
3. **Fresh-seed obligation.** Any benchmark claim must reproduce on a seed the implementer
   never ran. Reviewers pick the seed.
4. **No ground-truth leakage.** Verified structurally (§3), not by inspection alone.
5. **Degenerate-strategy probe.** For every metric, the reviewer asks: what is the dumbest
   implementation that maxes this number, and does the current code differ from it? Recall
   maxed by returning everything is not recall.
6. **Baselines stay live.** Full-thread dump, fixed-K, plain lexical, and strong-agent-with-
   primitives remain runnable every round. A win that only exists in prose is not a win.
7. **Claims match measurement.** README/docs statements are checked against the latest
   measured numbers. An overstated claim is a BLOCKER at the release gate, per
   `SCOPE_CORRECTION.md` §17.

---

## 8. Deadlock and escalation to the human

The orchestrator escalates, rather than deciding, when:

- an implementer and reviewer disagree on the same finding across **two** consecutive
  rounds;
- a rubric criterion appears unachievable as written, or achievable only by violating
  another criterion;
- satisfying a finding would change `PRODUCT_CONTRACT.md` or a settled principle in
  `SCOPE_CORRECTION.md` §15;
- a real-Gmail behavior contradicts a load-bearing assumption in
  `ARCHITECTURE_DECISION.md`;
- cost or quota limits make a required measurement impractical.

Escalation carries: the finding, both positions, the options, and a recommendation.
Silent self-resolution of any of the above is a process violation.

---

## 9. Records

```
docs/reviews/
  FINDINGS_LEDGER.md        every finding ever raised, with status and closing evidence
  ROUND_01/
    WORK_ORDER.md
    HANDOFF.md              implementer's own account, incl. gaps
    R-RETR.md  R-DISC.md  R-SEC.md  ...
    CONSOLIDATED.md         merged findings + gate decision + rubric transitions
  ROUND_02/
    ...
experiments/                empirical results, incl. failures, per MAILWEAVE_CONTEXT §56
```

A finding is closed only with closing evidence: the reviewer report and round in which it
was re-verified. Findings are never deleted, and MEDIUM findings deferred by the
orchestrator remain open with an explicit deferral note naming the round they return in.

---

## 10. Release gate

MailWeave is releasable when all of the following hold simultaneously, each
reviewer-confirmed:

1. Zero open BLOCKER and zero open HIGH findings.
2. Every mandatory rubric criterion is `PASS`. No criterion is `NOT TESTED`.
3. All required real-Gmail E2E tests pass against the live account.
4. Benchmark and performance thresholds pass on reviewer-selected held-out seeds.
5. Baseline comparisons are current and the documented claims match the measured numbers.
6. The adversarial reviewer's latest pass produced no BLOCKER-eligible finding.
7. README and public claims state exactly what was measured, what was not, and which
   problem is solved — representation omission, freshness, or semantic retrieval — with no
   bundled unproven claims (`MAILWEAVE_CONTEXT.md` §58).

Nothing on this list is waivable by an agent. Waiving any of it is a human decision,
recorded in the ledger with the reason.
