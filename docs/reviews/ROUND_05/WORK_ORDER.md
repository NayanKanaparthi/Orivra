# ROUND 05 — Work Order

**Issued by:** orchestrator, 2026-08-31
**Protocol:** `docs/AGENT_LOOP.md` §5
**Input:** `docs/reviews/ROUND_04/CONSOLIDATED.md`, `docs/reviews/FINDINGS_LEDGER.md`
("Currently open"), `docs/ARCHITECTURE_AMENDMENTS.md` A3.

## What this round is

Round 4 was the first round where every implementer finding closed under independent
verification. This round is the debt round: it clears what the newly-populated ledger exposed,
lands amendment A3, and gets the foundation to a genuinely clean state before WS-02 and the
Gmail client begin.

There are no HIGH findings against the code right now. Do not treat that as license to hurry;
it means the remaining work is exactness rather than firefighting.

## Part 1 — amendment A3 (position bounds)

| ID | Fix | Acceptance |
|----|-----|------------|
| **A3** | Positions are 0-based indices into chronological order, bounded `0 <= p < stated_total`, for both `MessageRow.position` and every position in a `CollapsedRun`. Raise on violation, never clamp; clamping silently moves evidence | R-RETR's `stated_total=5` with a run at `positions=(900, 904)` raises. Property test generates positions independently of `stated_total` so nothing hands the checker the answer. Occupancy checks from Round 4 still pass unchanged |

`PART-05` cannot pass until this lands.

## Part 2 — the fifteen never-verified Round 1 findings

`FINDINGS_LEDGER.md` shows these were fixed per the implementer's own account but **never
re-verified**, because Round 2 shipped no `R-ARCH.md` or `R-DISC.md` despite both being named
gating reviewers. Under `AGENT_LOOP.md` §1 they are open.

R-ARCH-001, R-ARCH-002, R-ARCH-003, R-ARCH-004, R-ARCH-006, R-ARCH-008,
R-DISC-002, R-DISC-003, R-DISC-004, R-DISC-005, R-DISC-006, R-DISC-007,
R-SEC-004, R-SEC-006, R-SEC-007.

**For each:** read the original finding, determine whether the current code actually addresses
it, and either fix it or state precisely why it needs no change. Do not assume a fix exists
because a HANDOFF once claimed one. Where a fix is already present, add the test that proves it
if none exists, because an unverified fix and an untested fix fail for the same reason.

R-DISC-004 specifically: 8 of 10 `Reason.render()` variants and the OD-3 parent/child stub
shape have never been exercised. That one blocks `PART-07` from being re-promoted.

## Part 3 — Round 4 MEDIUM findings

| ID | Defect |
|----|--------|
| **R-SEC-017** | A closure called before a later rebind of its free variable in an enclosing *function* scope is misclassified as an unconditional write. The "last binding wins regardless of line" rule is implemented generically though its justification only reasons about module scope |
| **R-SEC-019** | Nested-class attribute dispatch (`Outer.Inner.handler = os.write`) bypasses; the resolver handles only a bare-`Name` receiver, not a chained one |
| **R-SEC-020** | Dataclass fields (`handler: Callable = os.write`, plain and via `field(default=...)`) bypass entirely; `AnnAssign` targets are never resolved, only `Assign` |
| **R-SEC-018** | LOW, documentation precision: class-attribute, dict/list element and function-return indirection defeat the constant fold but are not literally covered by the "travels through a variable" wording |
| **R-ARCH-012** | MEDIUM, documented not fixed: the mechanical gate cannot detect a transition row citing plausible but fabricated evidence. Structural ceiling of a markdown-parsing check. Document the ceiling explicitly rather than leaving it implied |
| **R-RETR-003** | Carried from Round 3, still open |

## Standing rules, unchanged

A guard may close a finding by catching the bypass or by honestly documenting that it does
not, never by implying coverage it lacks. Every fix needs a test that fails before and passes
after, verified by reintroducing the defect. No tautologies, no values hardcoded in both test
and source.

## Constraints

OD-1..OD-4 binding. Invariants I-1..I-4. No personal mail in fixtures or logs. No fabricated
thresholds; `[UNSET]` stays unset. Do not mark any rubric criterion PASS and do not add rows to
`RUBRIC_TRANSITIONS.md` or `FINDINGS_LEDGER.md`; both are orchestrator-only. Do not build
amendment A1. Still no Gmail retrieval logic, rungs, ranking or MCP surface.

## Gating reviewers

`R-RETR` (A3, R-RETR-003), `R-DISC` (all R-DISC findings, especially R-DISC-004),
`R-ARCH` (the R-ARCH findings and test quality across the whole round), `R-SEC` (the R-SEC
findings).

**All four run this round.** Round 2 skipping two of them is what created Part 2.

## Exit condition

Zero open BLOCKER and zero open HIGH, every Part 1 and Part 2 item either fixed-and-verified or
explicitly justified as needing no change, and no regression in the seven passing criteria.


---

## Addendum — orchestrator ruling issued mid-round

**R-ARCH-008 / R-DISC-007** are now decided as **amendment A4**: `included` counts every
message present at any depth, stubs included, per contract R-05. `ARCHITECTURE_DECISION.md`
§D.2's worked example is wrong and changes; the code was already right.

Reviewers: verify the ruling is applied consistently and that the Round 5 test pinning the
shipped reading has its docstring updated to say a ruling exists rather than that one is owed.
