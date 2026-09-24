# ROUND 03 — Work Order (fix round)

**Issued by:** orchestrator, 2026-08-31
**Protocol:** `docs/AGENT_LOOP.md` §5. Round 2 did not gate.
**Input:** `docs/reviews/ROUND_02/R-RETR.md` and `docs/reviews/ROUND_02/R-SEC.md`.

## Status carried forward

| Finding | Verdict | Why |
|---------|---------|-----|
| H4 HTML caps | **CLOSED** | 122.36s → 0.47s verified independently; no silent loss |
| M2 atomic token save | **CLOSED** | crash window reproduced and confirmed shut |
| M3 bidi | **CLOSED as scoped** | but see R-SEC-011: only `body_clean` is covered |
| H1 transport seal | **PARTIALLY CLOSED** | H-lex and H-hist airtight under 7 attacks; `record_shortlist` still a bare-list intake |
| H2 map accounting | **PARTIALLY CLOSED** | 5 direct attacks blocked, but defeated *through* the shortlist hole |
| H3 AST guards | **PARTIALLY CLOSED** | old attacks now caught; new undocumented bypasses found |

## The one thing that matters this round

`record_shortlist` is the last unsealed intake into `H`, and R-RETR proved it is not a
loose end but a working bypass of both fixes: they injected 37 fabricated IDs straight
into `H` with self-issued withheld notes and **rebuilt R-DISC's exact 5-of-42 dishonest
map as a valid envelope**, end to end, with real evidence for 12% of what it claimed.

The principle from Round 2 has not changed, it just has not been finished:
**derive the claim from the enumeration; never assert it alongside.** One intake was
left asserting, and it reopened everything downstream of it.

## Required fixes

| ID | Fix | Acceptance |
|----|-----|------------|
| **H1b** | Seal `record_shortlist`. A shortlist may only be formed from IDs that already entered `H` through a sealed page or a history addition. IDs of unknown provenance must be rejected at intake, not at certification | R-RETR's 50-fabricated-ID probe raises. The 37-ID map reconstruction becomes impossible |
| **H2b** | Re-verify H2 once H1b lands: the 5-of-42 reconstruction must fail | R-RETR's end-to-end envelope build raises |
| **R-RETR-001** | Deduplicate IDs across `CollapsedRun`s. A repeat across two runs currently inflates `included`/`accounted_for` by naive sum, letting a map claim 100% completeness while a real message is unaccounted for | Cross-run repeats rejected; the demonstrated envelope build raises |
| **R-SEC-008** | Constant-fold byte-string literals (`b"...".decode()`), which currently evade all four content-matching guards at once | The probe file registers violations on all four |
| **R-SEC-009** | Disk-write guard: catch `from os import write as w` + bare call, `_writer = os.write`, and `functools.partial(os.write)` | Each shape caught, or each honestly documented as uncaught |
| **R-SEC-010** | `io.open(path, "w")` is missed because the guard assumes `Path.open`'s mode-first signature and checks the wrong argument position. This contradicts the guard's own documented claim | Correct the position handling, or correct the claim |
| **R-SEC-011** | Bidi/dangerous-unicode stripping currently covers only `body_clean`. The identical RLO spoof reaches `Subject` and attachment `filename` unstripped | Both covered, declared as `Reduction`s |
| **R-SEC-012** | LOW: a SIGKILL mid-`save()` leaves an orphaned 0600 temp file holding the secret. Not a disclosure; sweep it | Stale temp files swept on next save |

## Standing rule on the guards

A guard may close a finding by *catching* the bypass or by *honestly documenting* that it
does not. It may not close one by implying coverage it lacks. R-SEC accepted four
documented bypasses (`import os as o`, `getattr`, `eval`/`exec`, third-party writes) on
exactly that basis — keep that discipline.

## Constraints

Unchanged: OD-1..OD-4 binding, invariants I-1..I-4, no personal mail in fixtures or logs,
no fabricated thresholds, `[UNSET]` stays unset, no criterion marked PASS by the
implementer. Still a fix round: no Gmail retrieval logic, rungs, ranking or MCP surface.

Every fix needs a test that fails before and passes after, verified by reintroducing the
defect. For H1b, H2b and R-RETR-001 the test must demonstrate impossibility.

## Gating reviewers

`R-RETR` (H1b, H2b, R-RETR-001), `R-SEC` (the four security findings).

## Exit condition

Zero open BLOCKER and zero open HIGH, each verified by a reviewer who did not write it,
with no regression in what Round 2 closed.
