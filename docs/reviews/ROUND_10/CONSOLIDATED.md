# ROUND 10 — Consolidated findings and gate decision

**Orchestrator, 2026-08-31.** Reviewers: R-SEC, R-ARCH.

## Gate decision: **ROUND 10 CLOSES. The foundation is done.**

Zero BLOCKER. Zero HIGH. Both reviewers independently recommend gating. This is the first round
in ten to close, and it closes the foundation phase.

## What closed

**R-SEC-032 and the sweep.** `history_id` turned out to be unvalidated at a **third** layer, in
the transport seam. All three now import one shape from `constants.py`, anchored `\A`/`\Z` rather
than `^`/`$`. That anchoring matters: `"99120034\n"` passes `^…$`, and it only failed to reach
the wire before because `_sealed_scalar` happened to run first. A latent bug, found by fixing a
different one.

The implementer then swept **by mechanism rather than by field name** and found all ten string
parameters in `reasons.py` accepted a three-line mail body verbatim onto the wire. They fixed all
ten and flagged the scope expansion as a judgement call.

**R-SEC ruled the expansion correct**, on the grounds that leaving nine reproducible instances of
the same defect in the file being fixed would repeat their own ruling from Round 9. I agree.

**The invisible-character set is genuinely derived**, not listed: membership is
`unicodedata.category(c) == "Cf"`, with the declared causes from `unicodedata.bidirectional`.
R-SEC verified 170 of 170 stripped and 272 chunks of every non-`Cf` code point removing zero.

**Harness residue: none.** R-ARCH verified the tree is clean after the implementer disclosed that
their reintroduction harness had briefly left nine fields reverted. R-ARCH built its own harness
from scratch and reproduced 5 of 8 counts exactly; the one discrepancy was traced to rows being
captured incrementally as the suite grew from 1,168 to 1,529, not to residue.

## INJ-04 stays NOT TESTED, deliberately

R-SEC recommends PASS on the **hidden-character clause only**, and says plainly that the parser
and HTML-hiding clauses were not this round's subject.

So it stays `NOT TESTED`. This criterion has been reverted twice, both times because a scoped
recommendation was recorded as an unqualified pass. Recording a third partial pass would be the
same mistake a third time. It gets promoted when a reviewer establishes the whole criterion.

## The cycle continues, inside this round's own diff

R-ARCH's ruling on the shared floor is the most useful thing in this round.

The `GMAIL_NUMERIC_ID_RE` constant is architecturally right — an objective external-system fact,
genuinely single-sourced across three layers. But in the same file, in the same round,
`reasons.py`'s new `_one_line` **independently reimplements** `disposition.py`'s existing
`_is_one_line`, using the same `splitlines()` primitive, written twice.

So the round that diagnosed "one shape validated, peers trusted" for the fifth time produced a
sixth instance of it in its own diff. One shape was fixed for good structural reasons. The
general cycle is not broken.

That is worth carrying into WS-02 as a standing check rather than as a finding.

## Carried findings, none blocking

| ID | Sev | Item |
|----|-----|------|
| R-SEC-036 | MEDIUM | The handoff claims `MessageRow.id` / `Source.thread_id` are "closed transitively by an invariant". They are not; this is A1's residue, which Round 7's census already named. A documentation-accuracy defect, not a fresh hole |
| R-SEC-037 | LOW | Credential-store cleanup still crashes on an oversized-but-ASCII PID string, an uncaught `OverflowError`, same class as the R-SEC-035 that was called fixed |
| R-SEC-038 | LOW | Two off-by-one errors in the handoff's own Unicode counts |
| R-ARCH-031 | LOW | `_one_line` duplicates `_is_one_line` — the cycle, in this round's diff |
| R-ARCH-032 | LOW | `auth` now pulls the whole content and envelope stack into the credential store, costing 0.155s import time, more than the handoff's "one layering consequence" discloses |

## A named open condition for WS-02

The blanket `Cf` strip is precise and fail-safe, and every removal is counted. But whether it
damages legitimate Arabic, Indic or Syriac mail — where Arabic number signs and hieroglyph
joiners are genuine content — **cannot be settled without real mail**. Both R-SEC and the
implementer flagged it independently.

Ship as-is. Do not block on it. Measure it as soon as a real mailbox is connected, because it is
exactly the class of question that only reality answers, and reality is the next phase.

## Where the foundation stands

10 rounds. 1,529 tests. 7 of 113 criteria passing, which is low by design: most of the rest need
a Gmail client, an MCP surface or the harness to exist before they can be evaluated at all.

What the foundation actually established:

- Evidence preservation is enforced structurally and survived sixteen distinct attacks.
- The recurring "caller asserts what the system observed" defect was found seven times, audited
  across 187 fields, and its two halves separated: misstatement is closed, fabrication is
  provably not closeable in-process and needs the external witness.
- Content destruction is structurally impossible after A7, verified by a 5,000-example
  Hypothesis attack over the full Unicode range.
- Seven amendments, each forced by a measured failure rather than a preference.

**Next: WS-02, the Gmail client, and real mail.**
