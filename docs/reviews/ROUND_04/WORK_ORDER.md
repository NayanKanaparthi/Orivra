# ROUND 04 — Work Order (fix round)

**Issued by:** orchestrator, 2026-08-31
**Protocol:** `docs/AGENT_LOOP.md` §5. Round 3 did not gate: 3 HIGH open.
**Input:** `docs/reviews/ROUND_03/CONSOLIDATED.md`, `R-RETR.md`, `R-SEC.md`, and
`docs/ARCHITECTURE_AMENDMENTS.md` (A1 and A2, both binding).

## Context

The core evidence-preservation work closed this round. `H1b` and `H2b` survived a combined
sixteen attacks. What remains is adjacent: one position-level gap the id-level fix did not
cover, one architecture amendment that must land before WS-08, and the guard family that keeps
finding new bypasses.

## Required fixes

| ID | Fix | Acceptance |
|----|-----|------------|
| **R-RETR-002** | `_counts_match_the_payload` compares collapsed runs by member id but never by `positions`. Two runs with disjoint ids claiming the same thread slot build cleanly through a full `map_id`-bearing envelope. Enforce the "one position, one disposition" property the fix's own rationale states | R-RETR's two-run same-slot envelope raises. Property test generates position sets so nothing hands the checker the right answer |
| **R-RETR-004 / amendment A2** | Generalise the sealed page to a sealed **observation** carrying its source endpoint. Add `threads.get` as a first-class `H` clause (`H-thr`) alongside `H-lex` and `H-hist` | The single-writer property survives: still exactly one writer of `_origins`, still admits only sealed observations, still no path accepting a bare id list. The AST single-writer test still passes. A `threads.get`-sourced shortlist is now legal |
| **R-SEC-013** | 7 of 9 constant-obfuscation idioms defeat all four content-matching guards: `bytes.fromhex().decode()`, `"".join()`, `%`-formatting, `.format()`, `str.translate()`, reversed slicing, `int.to_bytes()`. Fold what folds; document the rest precisely | Each of the nine is either caught, or named in the guard's "Does not catch" section. No silent gap |
| **R-SEC-014** | Class-attribute dispatch (`class W: handler = os.write`) bypasses the disk-write guard | Caught or documented |
| **R-SEC-015** | The scope-blind alias index **false-positives on ordinary code**: two unrelated functions reusing a local name flag an innocent call. Fix the scope blindness | R-SEC's reproduction no longer fires, and the true positives from Round 3 still do |
| **R-SEC-016** | The open-position fix is a 5-module allowlist, not structural. `tarfile.open`, `shelve.open`, `zipfile.ZipFile` reproduce the original bug | Structural handling, or an honest statement of the allowlist's boundary |

## On R-SEC-015 specifically

This one matters more than its severity suggests. A guard that fires on innocent code gets
switched off by the next engineer, and then it protects nothing. Treat a false positive here as
seriously as a missed bypass.

## Standing rule on guards, unchanged

A guard may close a finding by **catching** the bypass or by **honestly documenting** that it
does not. Never by implying coverage it lacks. Four documented bypasses were accepted on that
basis in Round 3; keep that discipline and keep the "Does not catch" sections true.

## Amendment A1 — note, no code this round

The counting proxy becoming a content witness is WS-13/WS-16 work and is not in scope here.
Do not build it. Do not weaken anything on the assumption it exists. If you touch EV-01's
acceptance wording, stop and escalate instead.

## Orchestrator-modified test — audit this

`tests/test_rubric_status.py::test_no_criterion_is_currently_claimed_as_pass` asserted that
**no** criterion was PASS. That was true only while Round 1 was the newest round, and it went
red the moment reviewers legitimately promoted nine criteria.

I replaced it with `test_every_passing_criterion_was_moved_by_a_reviewer_with_evidence`, which
asserts the rule the placeholder was gesturing at: every PASS has a transition row, from a
recognised AGENT_LOOP §2.3 reviewer domain, carrying reproduction evidence.

**R-ARCH must audit this specifically** and judge whether the replacement is genuinely
stronger or whether the orchestrator relaxed a failing test to make its own change pass. That
is exactly the move the loop exists to catch, and it should not get a pass for being mine.

## Constraints

Unchanged: OD-1..OD-4 binding, invariants I-1..I-4, no personal mail in fixtures or logs, no
fabricated thresholds, `[UNSET]` stays unset, no criterion marked PASS by the implementer.
Still a fix round: no Gmail retrieval logic, no rungs, no ranking, no MCP surface.

Every fix needs a test that fails before and passes after, verified by reintroducing the
defect. For R-RETR-002 and A2 the test must demonstrate the structural property, not a happy
path.

## Gating reviewers

`R-RETR` (R-RETR-002, A2), `R-SEC` (the four security findings).

## Exit condition

Zero open BLOCKER and zero open HIGH, each verified by a reviewer who did not write it, with
no regression in the nine criteria now passing or in what Rounds 2 and 3 closed.
