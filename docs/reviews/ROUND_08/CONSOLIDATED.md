# ROUND 08 — Consolidated findings and gate decision

**Orchestrator, 2026-08-31.** Reviewers: R-ARCH, and a combined R-DISC/R-SEC review of A6.

## Gate decision: **ROUND 08 DOES NOT CLOSE.** One BLOCKER, three HIGH.

Round 8 was declared the last foundation round. It is not, and the reason is worth the delay.

## What genuinely closed

**The layering fix holds.** `email_reply_parser` is verifiably gone — not importable, absent
from the lockfile. `strip_quotes_and_signature` is the sole writer of `body_clean`, called from
exactly one site, with a runtime assertion enforcing the six-signal rule. All three reintroduction
counts reproduced exactly. Round 7's BLOCKER sentence now survives whole.

**The false-negative re-measurement is confirmed exactly:** 28 of 161, 17.4%, uniform across all
seven weekdays. The weekday-dependence that caused the original mis-measurement is gone.

**The field census reproduces**, and is test-pinned so the claim cannot drift.

**A6 is correct on the R-DISC side.** Both parameter removals are real with no `model_construct`
bypass. The three fields that stayed compose correctly with A3, A4 and the Round 6/7 thread
derivation, verified by attacks the reviewer wrote rather than reran, including one branch the
shipped suite never tests and which is nonetheless correct.

## R-ARCH-025 — BLOCKER

The implementer measured **0 false positives across 200 sentences** in three corpora, in both
positions. R-ARCH reproduced that exactly. Then R-ARCH wrote a **fourth** corpus, as this round's
work order required, and found **14 of 54 destroyed — 25.9%**.

Two shapes do it. Consecutive prose lines that happen to begin with header-field names
(*"To: recap, we need three approvals... / From: what I can tell, the budget already covers
this."*), and a bare dashless *"Original Message"* used as a person's own section heading. Both
trip a latching signal and silently destroy sender text plus surrounding paragraphs.

That rate is **worse than the 12.5% A5 was written to fix.**

## R-ARCH-026 — HIGH, and the implementer asked for this attack

They disclosed the latch as their weakest point and said their corpora never test text positioned
*below* an unmarked quote. R-ARCH built sixteen cases across all three latching signals and
measured **1,251 of 1,251 tagged sender characters destroyed. Every case.** A real
"-----Original Message-----" block followed by the sender's own reply collapses `body_clean` to
"Hi team,".

It is honestly flagged (`latched=True`, named in the `Reduction` detail) rather than silent like
Round 7's. The sentence is still gone.

## R-SEC-029, R-SEC-030 — HIGH. A6's exit condition does not hold.

The work order gated on "A6 landed with mail text provably excluded". It is not excluded.

- **R-SEC-029.** The newline refusal the handoff calls "what stops the interesting attempt" checks
  only literal `\n` and `\r`. Five other Unicode line boundaries — U+2028, U+2029, U+0085, U+000B,
  U+000C, all of which Python's own `str.splitlines()` treats as breaks — pass untouched.
- **R-SEC-030.** `history_id` and `internal_date` accept any 64-character single-line string with
  **no format validation at all**, unlike `fetched_at` which is instant-checked. The reviewer put
  a real sentence on the JSON wire disguised as Gmail metadata — *including on a stub row, whose
  entire architectural purpose is to disclose nothing.*
- **R-SEC-031, MEDIUM.** The seal's pre-existing id fields carry no bound, and the round's
  reflection test silently exempts them while claiming broader protection.

## The decision this round forces

Four rounds on one component. Round 5 fixed it, Round 6 defeated the fix, Round 7 fixed it again
and found the protection sat above a library that had already decided, Round 8 removed the
library and still lost a quarter of a fresh corpus.

Every fix was real. Every measurement was honest. **The approach is what keeps failing**, because
deciding whether a line is quoted material or the sender's prose is genuinely ambiguous, and
deletion makes every ambiguous case a coin flip whose losing face is permanent.

Decided as **amendment A7**: the content pipeline **annotates rather than deletes**. `body_clean`
becomes the full text with classified spans, disclosure chooses which spans to show, and no text
is ever removed. Content destruction becomes structurally impossible instead of defended against,
which is the move that has worked every other time here.

The gate changes with it. "Zero false positives on sender prose" stops being gated, because the
failure it gated cannot occur. The new gate is one total property: **no input text is absent from
the annotated output.** A classifier error then costs a wrong default view, not the user's words.

## Also worth recording

R-ARCH confirmed that its own Round 7 table listed 35 sentences under a "0/36" headline. The
implementer transcribed 35 and **said so** rather than inventing a sentence to reach 36. That is
the behaviour this loop is supposed to produce.

## Criteria

8 pass, unchanged.
