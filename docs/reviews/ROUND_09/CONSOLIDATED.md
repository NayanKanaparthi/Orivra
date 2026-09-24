# ROUND 09 — Consolidated findings and gate decision

**Orchestrator, 2026-08-31.** Reviewers: R-ARCH, and a combined R-SEC/R-DISC review.

## Gate decision: **ROUND 09 DOES NOT CLOSE.** One HIGH.

R-ARCH recommended gating. R-SEC found a HIGH that R-ARCH's scope did not cover. The stricter
verdict governs.

## A7 worked, and it worked the way it was supposed to

**Containment cannot be defeated.** R-ARCH attacked it with overlapping, zero-length,
out-of-order and gapped spans, duplicate spans, a spoofed `__eq__` string subclass, NFD combining
characters, ZWJ emoji, bidi overrides, astral characters, lone surrogates, empty and
whitespace-only bodies, a wrong-length classification list, and a **5,000-example Hypothesis run
over the full Unicode range** — wider than the suite's own 400. Everything through the real
constructor was refused correctly or reconstructed exactly. Reintroducing deletion fails 339 of
1,168 tests, exactly as claimed, and fails at construction rather than silently.

**Destruction is zero.** R-ARCH's fifth corpus, 32 new entries across 64 position pairs, none
copied from existing fixtures: **0 destroyed**. Round 8's same reviewer measured 14 of 54
destroyed. The catastrophic failure mode is gone, and it is gone structurally rather than by
tuning.

The remaining LOW caveat is that `object.__setattr__` and forged pickles can bypass any Python
dataclass, which is generic and unexercised anywhere in the repo.

## Two claims that did not survive review, and both matter

**The 5.5% default-view miss rate is corpus-specific, not a ceiling.** R-ARCH's fifth corpus,
written to target under-tested signals, measured **50%**. That is nine times the reported figure.
It is not a contradiction of A7 — nothing was destroyed in either case — but the reported number
should not be read as a bound on default-view quality.

**"Recoverable one class wider" does not hold as a blanket claim.** R-ARCH re-ran Round 8's
corpus against the one-widening view and found all fourteen misclassified entries still miss
something. The handoff itself was precise, claiming it only for the seven collateral neighbours
and the latch corpus, but the general framing does not generalise. **The basis for downgrading
this from a blocker is containment, not one-widening-always-suffices**, and future write-ups must
say it that way.

Also unverifiable: the byte-identical-to-Round-8 claim. Round 8's code no longer exists in the
tree and the container has no git, so the 293-body count checks out but the character comparison
cannot be re-run. Not a finding, a limitation of how we work.

## R-SEC-032 — HIGH, and the reason it blocks

R-SEC-029, 030 and 031 are all genuinely fixed and verified. `_is_one_line` now delegates to
`str.splitlines()` itself, which is definitionally complete rather than a hand-list.

But `HistoryAddition.history_id` still puts a sentence **verbatim onto the disclosed JSON wire**
via the `reason` field. R-SEC built the envelope and confirmed it.

The reviewer's ruling, which I accept: this is not adjacent work that scope discipline protects.
It is **R-SEC-030 unfinished** — same field name, same missing check, found while executing the
work order's own sweep instruction, *more* exposed than what R-SEC-031 fixed because there is no
seal in between, and the fix is a regex that already exists and is already tested.

Scope discipline is there to keep a refactor reviewable, not to let a known defect one layer up
survive the round that fixed it one layer down.

## INJ-04 reverted, for the second time

R-SEC found `strip_invisible_characters` lists 16 code points where Unicode defines about 170, so
U+061C, soft hyphen and the whole tag block survive, and flagged it as bearing on INJ-04's
"flagged hiding" clause.

They did not ask for a revert. I am reverting anyway: a criterion whose evidence a reviewer has
called into question should not sit at PASS while that is unresolved. Seven stand.

This is the second INJ-04 revert and the third time the orchestrator has had to unwind its own
promotion. The lesson is consistent — promote late, not early.

## A7 has not been integrated with disclosure

R-SEC confirmed by grep and execution that **no code in `envelope/` references `AnnotatedBody` or
`SpanClass`.** Nothing was smuggled into a second depth hierarchy, which was the risk. But
nothing is wired up either, so whether A7 composes with the depth vocabulary, the token budgets
and OD-3's floor is genuinely unanswerable this round. Field ordering, token-counting units and
truncation shape were verified compatible.

That is expected — the disclosure layer is not built yet — but it means A7's integration is an
open item rather than a settled one.

## The `uncertain` default: ruled

R-DISC ruled to keep `original` as the default view. The wide alternative's cost is unbounded, as
it would show entire unclosed quote chains in roughly 17% of real threads, while the narrow
default's residual risk is bounded and cheap to close later. It mirrors OD-3's already-settled
tension.

Two conditions attach for whoever wires it up: the `uncertain` signal must be **structured rather
than prose-only**, and widening must be **floor-message-specific rather than a global default**.

## Criteria

7 pass, after the INJ-04 revert.
