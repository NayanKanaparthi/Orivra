# ROUND 08 — Work Order

**Issued by:** orchestrator, 2026-08-31
**Protocol:** `docs/AGENT_LOOP.md` §5. Round 7 did not gate: one BLOCKER.
**Input:** `docs/reviews/ROUND_07/CONSOLIDATED.md`, `R-ARCH.md`, `R-DISC.md`, amendment A6 final.

**This is the last foundation round.** After it gates, the project moves to WS-02 and the Gmail
client. Round 7 established that the remaining evidence-preservation gap is structural and needs
the external witness, not more validation code, so there is nothing left to harden here once
these items close.

## Part 1 — R-ARCH-022, the BLOCKER

Amendment A5 is applied at the wrong layer. The `email_reply_parser` library applies its own
`QUOTE_HDR_REGEX`, `HEADER_REGEX` and `SIG_REGEX` **before A5's protection runs**, so a sentence
matching one of them is marked `hidden` by the library and deleted wholesale, with no A5 check
and no ambiguity flag. R-ARCH's reproduction: *"Once the negotiations concluded, the legal team
wrote:"* destroys that sentence and the unrelated one after it, silently.

| Requirement | |
|---|---|
| **A5 must govern every deletion path**, including anything the library decides on its own. No text leaves `body_clean` without passing the strong-structural-signal rule | Gated |
| **Zero** false positives on sender-authored prose, measured against R-ARCH's corpus, the implementer's corpus, and a third you write. All three, in both the above-a-quote-chain and standalone positions | Gated |
| Every deletion carries a `Reduction`; ambiguous cases keep the text with a zero-sized `Reduction` and a reason | Gated |

If the honest way to satisfy this is to stop delegating the decision to the library and own the
detection entirely, do that and say so. A dependency that silently deletes user text is not a
dependency this component can keep in the deletion path.

## Part 2 — the false-negative correction

R-ARCH measured **36.8%** headers surviving (7 of 19) against Gmail, Outlook, Apple Mail,
Android, Yahoo, ProtonMail, mailing lists and bare `>` chains — not the 12.5% reported. The
cause is a pronoun and weekday-abbreviation collision (`Mon` against French `mon`, and peers)
that a Tuesday-only corpus could not expose.

Fix the collision and re-measure across a corpus spanning **all seven weekdays** and every
client format R-ARCH used. False negatives remain **reported, not gated** per A5 — but report a
number measured against a corpus that can actually falsify it.

## Part 3 — amendment A6, final form

Widen sealed observations to carry the **named scalar fields** the class-O audit identified:
`stated_total`, `position`, `internal_date`, `history_id`, `fetched_at` and their peers. **Not**
whole response bodies. Mail text is explicitly excluded from what a seal retains, so this does
not become a place bodies persist under OD-4 and Appendix A.3.

Then derive the class-O fields from the widened seal and remove their caller-supplied
parameters, as Round 6 and 7 did for `thread_id`.

**State plainly in your handoff what A6 does not buy.** It closes *misstatement*. It does
nothing about *fabrication*, which is A1's problem and is not yours this round.

## Part 4 — the audit's enumeration claim

The Round 7 audit reported 187 fields "programmatically enumerated"; the published script
produces 173, with 14 hand-added. The additions are accurate but the claim is not, and that
audit's value rests entirely on its completeness. Fix the script so it genuinely enumerates all
187, and make the count assertable by a test so the claim cannot drift again.

## Standing rules

A guard may close a finding by catching the bypass or honestly documenting it, never by implying
coverage it lacks. Every fix needs a test that fails before and passes after. Count failing
tests by running them — Round 7's counts matched exactly, keep that.

## Constraints

OD-1..OD-4 binding. Invariants I-1..I-4. Amendments A1..A6 binding; **A1 is still not yours to
build**. No personal mail in fixtures or logs. No fabricated thresholds. Do not mark any rubric
criterion PASS, and do not add rows to `RUBRIC_TRANSITIONS.md` or `FINDINGS_LEDGER.md`. No Gmail
retrieval logic, rungs, ranking or MCP surface. Eight criteria pass; do not regress them.

## Gating reviewers

`R-ARCH` (Parts 1, 2 and 4 — and write a fresh prose corpus again; yours is the one that found
the BLOCKER), `R-DISC` (Part 3), `R-SEC` (retention check on the widened seal: confirm no mail
text is retained and no new write path appears).

## Exit condition

Zero open BLOCKER and zero open HIGH. Zero false positives across all three prose corpora in
both positions. A6 landed with mail text provably excluded. The enumeration claim true and
test-asserted.
