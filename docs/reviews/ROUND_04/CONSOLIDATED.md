# ROUND 04 — Consolidated findings and gate decision

**Orchestrator, 2026-08-31.** Reviewers: R-RETR, R-SEC, R-ARCH.

## Gate decision: **the implementation side of Round 04 CLOSES. The process side does not.**

Every finding assigned to the implementer this round was verified closed by a reviewer that
did not write it. That is the first time this has happened.

| Finding | Verdict | Verified by |
|---|---|---|
| R-RETR-002 position occupancy | **CLOSED** | R-RETR: verbatim two-run same-slot shape, partial overlap, row-vs-run, nested runs all blocked; abutting and single-position runs correctly build |
| Amendment A2 sealed observations | **CLOSED, seal not regressed** | R-RETR: both Round 3 probes re-run unmodified and still blocked; all six off-diagonal endpoint relabelings blocked; AST single-writer test still passes and genuinely covers the new intake |
| R-SEC-013/014/015/016 | **CLOSED as scoped** | R-SEC: nine idioms fold, class-attribute dispatch caught, both false-positive reproductions clear, opener handling structural across nine modules |

R-SEC also ran a realistic false-positive sweep, reusing common names across ten functions, a
comprehension, a nested function, a class body and a parameter, and found **zero** false
positives while still catching the two real writes. That was the failure mode most likely to
get the guards switched off, and it is gone.

## Three HIGH findings against the ORCHESTRATOR, not the implementer

R-ARCH audited the test the orchestrator edited and cleared it as a genuine strengthening,
then found three things wrong with the orchestrator's own record-keeping.

| ID | Defect | Resolution |
|----|--------|-----------|
| **R-ARCH-009** | `INJ-04` recorded as an unqualified PASS when the reviewer said "ready for PASS on the bidi/zero-width scope specifically" | **Reverted to NOT TESTED.** The rubric has no half-pass |
| **R-ARCH-010** | `PART-07` recorded as a flat PASS when the reviewer said "structural half only", with companion finding R-DISC-004 open for three rounds | **Reverted to NOT TESTED** |
| **R-ARCH-011** | `FINDINGS_LEDGER.md` empty across four rounds, against `AGENT_LOOP.md` §9 which requires every finding recorded | **Populated.** 122 findings |

Both reversals are recorded in `RUBRIC_TRANSITIONS.md` rather than deleted. Seven promotions
stand. The pattern in both errors was the same: a reviewer recommended a *scoped* pass and the
orchestrator recorded an *unqualified* one.

## What populating the ledger revealed

Worse than the finding that ordered it. **Fifteen Round 1 findings were never independently
re-verified**, because Round 2 shipped no `R-ARCH.md` and no `R-DISC.md` despite both being
named gating reviewers in the Round 1 work order. Their fixes were accepted on the
implementer's own account.

That is precisely what `AGENT_LOOP.md` §1 forbids, and it went unnoticed for three rounds
because nothing was tracking findings across rounds. The ledger existing is what surfaced it.
Those fifteen are marked `OPEN`, not `CLOSED`, and Round 5 carries them.

This is not new breakage. It is newly visible debt, which is the better of the two.

## Escalated and decided

`R-RETR-005` and `R-ARCH-013`, the same defect found independently: positions are unbounded
against `stated_total`, so a "complete" map can place part of itself outside the thread it
describes. Decided as **amendment A3**: positions are 0-based indices into chronological order,
bounded `0 <= p < stated_total`, raising rather than clamping.

## Ledger state

122 findings recorded. 92 closed, 23 open, 3 partially closed, 2 escalated (now decided), 1
deferred, 1 accepted as a documented residue.

## Criteria

7 stand at PASS after the two reversals. R-RETR recommends `EV-01` **bounded-below half** as
PASS; that is held until the rubric carries the A1 split explicitly, because recording an
unqualified PASS for a split criterion is the exact error R-ARCH-009 and R-ARCH-010 just
caught.
