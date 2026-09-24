# ROUND 05 — Consolidated findings and gate decision

**Orchestrator, 2026-08-31.** Reviewers: R-DISC, R-ARCH, R-SEC. All four domains were named;
R-RETR's items (A3, R-RETR-003) were verified within the other three reports.

## Gate decision: **ROUND 05 DOES NOT CLOSE.** One HIGH open.

## What the debt round actually found

Part 2 existed because fifteen Round 1 findings were never independently verified. The result
is the strongest argument yet for the ledger:

| | |
|---|---|
| Genuinely fixed and tested | **4** of 15 |
| No fix at all | **8** of 15 |
| Fixture and docstring but no code | **1** (the French reply still dangled verbatim) |
| Needed a ruling nobody had made | **2** |

Eight findings quietly rotted for four rounds because they were non-blocking and nothing
tracked them. All are now fixed, failing-test-first, and independently verified this round.

## Verified closed

R-DISC-002, 003, 004, 005, 006 — each confirmed by the reviewer reintroducing the exact defect
and watching the predicted tests fail. R-ARCH-001, 002, 003, 004, 006 — same method, and 003's
locale fix generalises correctly to seven locales the implementer never tested. R-SEC-004
(egress: seven malformed-punycode hosts all failed closed with zero requests reaching the
transport), R-SEC-007 (depth cap 120 verified below the real interpreter limit of 255),
R-SEC-017, 018, 019.

R-DISC-003's field reorder is a real usability win, not a schema tidy: `partial`, `withheld`
and `retrieval_report` now land at bytes 395 to 830, against `sources` at byte 2127 of 5677.
An agent reading top to bottom meets the partiality signal before any message body.

R-DISC-004, which blocks PART-07, was scrutinised hardest and holds: all ten renderers, all
seven roles, the OD-3 floor end to end, with per-field mutation so a renderer that ignores a
parameter fails.

## Open HIGH

**R-DISC-009.** `WithheldRecord.thread_id` is caller-supplied and never cross-checked against
the `HitOrigin.thread_id` actually observed. A map for thread A can therefore claim completeness
by borrowing a real withheld id belonging to thread B. R-DISC built and executed it. This is not
adversarial-only; an ordinary caller bug reproduces it silently. Blocks PART-05.

It is the same shape as everything else this project keeps finding: a claim (`thread_id` on the
record) asserted alongside an enumeration (the observed origin) instead of derived from it.

## The orchestrator was caught again

**A4's follow-through was never done.** I wrote an amendment stating that
`ARCHITECTURE_DECISION.md` §D.2's worked example changes, and then did not change it. Both
R-DISC and R-ARCH found it independently, and the Round 5 work order had explicitly told
reviewers to check exactly this. Fixed now: §D.2 reads `included: 42` with the amendment note
inline. The pinning test's docstring is still stale and goes to Round 6, since tests are the
implementer's to edit.

That is three rounds running where a reviewer has caught the orchestrator's record-keeping
rather than the implementer's code. The pattern is consistent: I write the decision and skip
the propagation.

**INJ-04 re-promoted, at full scope.** R-SEC established that the Round 4 revert was correct in
form but wrong in substance: the criterion genuinely passes across three rounds of evidence, and
what was defective was my ledger citation, not R-SEC's claim. The row now cites all three
rounds. 8 criteria pass.

## New findings for Round 6

| ID | Sev | Defect |
|----|-----|--------|
| R-DISC-009 | HIGH | cross-thread withheld-record borrowing defeats a completeness claim |
| R-DISC-008 / R-ARCH-014 | MED | A4's pinning-test docstring still says no ruling exists |
| R-ARCH-015 | MED | quote stripper deletes a sender's own sentence when it carries an attribution verb, an email and a time before a real quoted chain |
| R-ARCH-016 | MED | `refuse_unbounded_payload` walks only raw `dict` nodes; a `Part` tree built by direct model construction bypasses it through all three entry points, demonstrated at 2,000 levels |
| R-ARCH-017 | LOW-MED | A3's bound rejects ~71% of generated cases before they reach R-RETR-002's occupancy property, diluting it to ~85 of 300 examples per run |
| R-SEC-021 | MED | `MappingProxyType` skips the shape bound; 32,000-part payload built in 0.15s |
| R-SEC-022 | MED | the new seventh guard is defeated by `import httpx._client as hc; hc.Client()`, the identical class object, unwrapped |
| R-SEC-023 | MED | chained assignment `a = b = os.write` bypasses both guards; the third pass skips multi-target `Assign` |
| R-SEC-024 | LOW | class-inheritance attribute access unresolved; `field(default_factory=lambda: os.write)` missed |
| R-ARCH-018 | MED | the participation test checks "value changed, output changed" but not field placement; a position/thread_id swap passes all 50 |

## Independent false-positive sweeps

Both R-SEC and R-ARCH wrote their own ordinary-code sweeps, different from the implementer's:
167 lines and ~100 lines respectively, covering closures over loop variables, `functools.wraps`
decorators, generators, context managers, class hierarchies, comprehension shadowing and
`except ... as`. **Zero false positives** in both. R-SEC-017's fix holds.
