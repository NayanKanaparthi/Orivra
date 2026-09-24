# ROUND 09 — Work Order

**Issued by:** orchestrator, 2026-08-31
**Protocol:** `docs/AGENT_LOOP.md` §5. Round 8 did not gate: 1 BLOCKER, 3 HIGH.
**Input:** `docs/reviews/ROUND_08/CONSOLIDATED.md`, `R-ARCH.md`, `R-DISC-SEC.md`, amendment A7.

Round 8 was meant to be the last foundation round. It found that one component cannot be fixed
by the approach it uses, so this round changes the approach rather than attempting a fifth fix.

## Part 1 — amendment A7. Read it before writing anything.

`docs/ARCHITECTURE_AMENDMENTS.md` A7 is binding and it replaces an operation, not a rule.

**The content pipeline annotates. It does not delete.**

- `body_clean` becomes the **full text with classified spans**, not a smaller copy of the body.
- Spans are classified `quoted`, `signature`, `forwarded`, `original`, or `uncertain`, each
  carrying the signal that classified it.
- **No text is removed, ever.** A span the pipeline is unsure about is `uncertain` and present.
- The disclosure layer chooses which spans to *show*, using its existing budgets and depth
  vocabulary. Showing only `original` spans is the default view and reproduces today's token
  economics.
- Because nothing is deleted, every view is reversible and the full text is one depth step away.

### The new gate, and it replaces the old one

| Gated | |
|---|---|
| **No input text is absent from the annotated output.** Character-level, total, mechanically checkable, and not defeatable by a corpus nobody thought of | **Yes** |
| Default-view quality (what used to be "false positives on sender prose") | Reported, **not** gated |
| False negatives | Reported, **not** gated |

Measure default-view quality against all four existing corpora, including R-ARCH's fourth, and
report it. A misclassification is now a wrong default view rather than lost words, so report it
honestly instead of tuning until a number looks good. The number that matters is the gate above.

**The latch (R-ARCH-026) dissolves under A7** — a latch that annotates to end-of-message is fine,
because the text is still there. Verify that it does, rather than assuming it.

## Part 2 — A6's retention holes

The Round 8 exit condition "mail text provably excluded" does not hold.

| ID | Fix |
|----|-----|
| **R-SEC-029** | The newline refusal checks only `\n` and `\r`. Refuse every Unicode line boundary: U+2028, U+2029, U+0085, U+000B, U+000C. Use a definition that matches what `str.splitlines()` treats as a break rather than a hand-listed set, so the next boundary character is covered too |
| **R-SEC-030** | `history_id` and `internal_date` accept any 64-character string with no format validation. Validate them to their real formats, as `fetched_at` already is. A reviewer put a real sentence on the wire disguised as metadata, **including on a stub row** |
| **R-SEC-031** | The seal's pre-existing id fields carry no bound, and the reflection test silently exempts them while claiming broader protection. Bound them, or make the test's claim honest about what it covers |

R-SEC-030 is the instructive one: `fetched_at` was validated and the other two were not, which is
the same "one shape checked, the rest silently absent" pattern this project has now hit four
times. When you fix these, check whether any other field validates one representation and trusts
the others.

## Standing rules

A guard may close a finding by catching the bypass or honestly documenting it, never by implying
coverage it lacks. Every fix needs a test that fails before and passes after. Count failing tests
by running them.

## Constraints

OD-1..OD-4 binding. Invariants I-1..I-4. Amendments A1..A7 binding; **A1 is still not yours to
build**. No personal mail in fixtures or logs. No fabricated thresholds. Do not mark any rubric
criterion PASS, and do not add rows to `RUBRIC_TRANSITIONS.md` or `FINDINGS_LEDGER.md`. No Gmail
retrieval logic, rungs, ranking or MCP surface. Eight criteria pass; do not regress them.

## A note on scope discipline

A7 touches `body_clean`'s consumers, which is real surgery. Do not take the opportunity to
improve anything adjacent. If A7 reveals a defect elsewhere, record it in the handoff and leave
it; an unrelated change riding along in a structural refactor is how a round stops being
reviewable.

## Gating reviewers

`R-ARCH` (A7, and write a **fifth** corpus — yours found the last two BLOCKERs, and under A7 the
question changes from "what gets destroyed" to "what does the default view get wrong"),
`R-SEC` (Part 2 and a fresh retention attack), `R-DISC` (whether A7's spans compose with the
disclosure layer's depth vocabulary and budgets without breaking Round 5's field ordering).

## Exit condition

Zero open BLOCKER and zero open HIGH. The character-level containment gate holds against every
corpus, including new ones written this round. No mail text reachable in a seal by any encoding.
