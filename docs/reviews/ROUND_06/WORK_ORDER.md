# ROUND 06 — Work Order (fix round)

**Issued by:** orchestrator, 2026-08-31
**Protocol:** `docs/AGENT_LOOP.md` §5. Round 5 did not gate: 1 HIGH open.
**Input:** `docs/reviews/ROUND_05/CONSOLIDATED.md` and the three Round 5 reviewer reports.

## The one HIGH

| ID | Fix | Acceptance |
|----|-----|------------|
| **R-DISC-009** | `WithheldRecord.thread_id` is caller-supplied and never cross-checked against the `HitOrigin.thread_id` actually observed, so a map for thread A can claim completeness by borrowing a real withheld id belonging to thread B. **Derive the thread from the observation, do not accept it from the caller** | R-DISC's cross-thread borrowing reproduction raises. A withheld record whose thread disagrees with its id's recorded origin is rejected at certification. Property test generates ids and threads independently |

This is the same shape the project keeps finding: a claim asserted alongside an enumeration
instead of derived from it. Apply the rule that has worked five times now.

## Mediums

| ID | Defect |
|----|--------|
| **R-DISC-008 / R-ARCH-014** | The A4 pinning test's docstring still says no ruling exists. The ruling was issued and `ARCHITECTURE_DECISION.md` §D.2 is now corrected; update the docstring to record that A4 decided it, and keep the test |
| **R-ARCH-015** | Quote stripper deletes a sender's **own** sentence when it happens to carry an attribution verb, an email address and a time immediately before a real quoted chain. Silent content loss, which is the failure class this project exists to prevent, so treat it above its severity |
| **R-ARCH-016** | `refuse_unbounded_payload` walks only raw `dict` nodes; a `Part` tree built by direct model construction bypasses it through all three entry points including `parse_payload()`. Demonstrated at 2,000 levels, 16× the cap. The docstring claims every construction path is covered; make that true or make the docstring true |
| **R-ARCH-017** | A3's bound rejects ~71% of generated cases before they reach R-RETR-002's occupancy property, leaving ~85 of 300 examples per run actually testing it. Split the generators so each property is exercised at full strength |
| **R-ARCH-018** | The participation test asserts "value changed, output changed" but not field placement; a `ThreadMember` position/thread_id swap passes all 50 tests. Assert placement |
| **R-SEC-021** | `MappingProxyType` skips the shape bound via an `isinstance(data, dict)` gate; 32,000-part payload built in 0.15s |
| **R-SEC-022** | The new seventh guard is defeated by `import httpx._client as hc; hc.Client()` — the identical class object, unwrapped, with a real transport and no allowlist. Undocumented |
| **R-SEC-023** | Chained assignment `a = b = os.write` bypasses both guards because the third pass skips multi-target `Assign`. An entirely ordinary idiom, undocumented |
| **R-SEC-024** | LOW: class-inheritance attribute access unresolved; `field(default_factory=lambda: os.write)` missed while only a form that crashes at construction is "caught" |

## A note on R-SEC-021 and R-ARCH-016

These are the same defect in two places: a bound that inspects one concrete input shape and is
silently absent for every other way of building the same structure. Fix them together and check
whether the pattern appears anywhere else, rather than patching two instances of it.

## Standing rules

A guard may close a finding by catching the bypass or by honestly documenting that it does not.
Never by implying coverage it lacks — R-SEC-022 and R-SEC-023 are both undocumented, and
R-SEC-020's Round 5 claim overstated what was caught, so be precise about what you actually
close. Every fix needs a test that fails before and passes after, verified by reintroducing the
defect.

## Constraints

OD-1..OD-4 binding. Invariants I-1..I-4. Amendments A1..A4 binding; **A1 is still not yours to
build**. No personal mail in fixtures or logs. No fabricated thresholds. Do not mark any rubric
criterion PASS and do not add rows to `RUBRIC_TRANSITIONS.md` or `FINDINGS_LEDGER.md`. No Gmail
retrieval logic, rungs, ranking or MCP surface. Eight criteria now pass; do not regress them.

## Note for reviewers next round

R-ARCH found a stale-editable-install trap: tests run from a `/tmp` copy can silently execute
against `/root/mailweave` instead. Wipe `.venv` and caches and resync in any scratch copy before
trusting its results.

## Gating reviewers

`R-DISC` (R-DISC-009, R-DISC-008), `R-ARCH` (the R-ARCH findings and test quality),
`R-SEC` (the R-SEC findings).

## Exit condition

Zero open BLOCKER and zero open HIGH, each verified by a reviewer who did not write it, with no
regression in the eight passing criteria.
