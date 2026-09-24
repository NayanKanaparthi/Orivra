# ROUND 10 — Work Order

**Issued by:** orchestrator, 2026-08-31
**Protocol:** `docs/AGENT_LOOP.md` §5. Round 9 did not gate: one HIGH.
**Input:** `docs/reviews/ROUND_09/CONSOLIDATED.md`, `R-ARCH.md`, `R-SEC-DISC.md`.

**This round should be short.** A7 landed and containment survived a 5,000-example attack. What
remains is one unfinished fix, one criterion to re-establish, and three sweep items. If it gates,
the foundation is done and the project moves to WS-02 and real mail.

## Part 1 — R-SEC-032, the HIGH

`HistoryAddition.history_id` puts a sentence **verbatim onto the disclosed JSON wire** through the
`reason` field. This is R-SEC-030 unfinished: same field name, same missing check, one layer up,
*more* exposed because no seal sits in between. The fix is the `^[0-9]{1,20}$` shape check that
already exists and is already tested.

Acceptance: R-SEC's envelope reproduction no longer carries the sentence. Then **sweep for the
same field name and the same missing check anywhere else**, because this is the second time this
exact field has been found unvalidated at a different layer.

## Part 2 — re-establish INJ-04

`strip_invisible_characters` lists 16 code points where Unicode defines roughly 170, so U+061C,
soft hyphen and the entire tag block survive. INJ-04 was reverted to `NOT TESTED` because of it.

Fix it the way R-SEC-029 was fixed: **derive the set from Unicode's own categories** rather than
listing code points by hand, so the next character added to the standard is covered without a
code change. Then the criterion can be re-verified on its full scope rather than a narrow one.

## Part 3 — the two remaining sweep items

- **`obtained_at`** is unvalidated beside two `parse_instant` peers. Same "one shape validated,
  peers trusted" pattern, now found five times.
- **A credential-store cleanup crash** that contradicts its own "every error is swallowed" claim.
  R-SEC found this independently; reproduce and fix.

## Part 4 — one honesty correction, no code

`docs/reviews/ROUND_09/HANDOFF.md` frames the default-view misses as "recoverable one class
wider". R-ARCH re-ran Round 8's corpus and found all fourteen misclassified entries still miss
something under one widening. The handoff's narrow claim was accurate; the general framing is
not, and it will end up in a write-up if left standing.

Correct the framing where it appears in the handoffs and in any docstring that repeats it. **The
basis for A7 downgrading content loss from a blocker is containment — the text is present and
addressable — not that one widening always retrieves it.**

## Not in scope, deliberately

Integrating A7 with the disclosure layer. R-SEC confirmed no code in `envelope/` references
`AnnotatedBody` yet. That integration belongs with WS-11 when the disclosure policy is built, and
R-DISC's two conditions travel with it: the `uncertain` signal must be **structured rather than
prose-only**, and widening must be **floor-message-specific rather than a global default**.

Record those two conditions somewhere they will be found when WS-11 starts.

## Standing rules

A guard may close a finding by catching the bypass or honestly documenting it, never by implying
coverage it lacks. Every fix needs a test that fails before and passes after, counted by running.

## Constraints

OD-1..OD-4 binding. Invariants I-1..I-4. Amendments A1..A7 binding; **A1 is still not yours to
build**. No personal mail in fixtures or logs. No fabricated thresholds. Do not mark any rubric
criterion PASS and do not add rows to `RUBRIC_TRANSITIONS.md` or `FINDINGS_LEDGER.md`. No Gmail
retrieval logic, rungs, ranking or MCP surface. Seven criteria pass; do not regress them.

## Gating reviewers

`R-SEC` (Parts 1, 2 and 3 — and re-verify INJ-04 on its **full** scope, not a narrow one, since
a narrow citation is what caused both of its reverts).

One reviewer is sufficient for a round this size. If the diff grows beyond the four parts, say so
and I will add domains.

## Exit condition

Zero open BLOCKER and zero open HIGH. INJ-04 re-verifiable on full scope with the invisible-set
derived rather than listed. No mail text on the wire by any route. Then the foundation gates and
WS-02 begins.
