# ROUND 18 — a negated scope is the region, not a filter inside it

**Issued by:** orchestrator, 2026-09-03
**Protocol:** `docs/AGENT_LOOP.md` §5, gate per §5a.

Round 17 did the right thing and did it well. It closed the blocker structurally
(`matchable_content_of` holds for spellings nobody enumerated), fixed the quoted-colon
regression, and — most importantly — **stated the decomposition/scope invariant once instead of
patching a third instance of the same defect**. R-RETR confirmed the invariant test is not
vacuous: it planted six violations, and emptying the very derivation the test reads still fails
it. Eight findings closed. The report/raise line survived 338 adversarial inputs. 600 randomised
trials plus 120 forced-overflow cases: zero evidence-preservation violations.

Then the reviewer found the thirteenth instance of this project's recurring defect **inside the
invariant's own asymmetry clause**.

## Part 0 — the owner decided. `MessageRow` gains mailbox provenance. (OD-5, A9)

The question round 17 escalated has been answered: **make the schema change.** `docs/OWNER_DECISIONS.md`
OD-5 carries the authority, `docs/ARCHITECTURE_AMENDMENTS.md` A9 the mechanics. Both are binding and
you should read them before writing anything.

Every `MessageRow` carries machine-readable mailbox provenance, **derived from the message's observed
labels** — not from the query that found it, and not as a prose mention. A caller must be able to
branch on it, so spam and trash results are explicitly identified as what they are.

Deriving it from the query would be *"a value accepted from the caller when the same value is already
derivable from what was observed"* — the defect class this project has now found more than a dozen
times. The label set is what was actually observed. Use it.

This makes round 17's open question moot rather than deferred: no future round may answer *"the probe
was declared in `scan_scope`"* to a question about what a **row** discloses.

## Part 1 — R-RETR-026 (HIGH). MailWeave reads mail the user explicitly excluded.

The invariant says a negation may be omitted from a probe because it *"widens within the same
region."* That is true for `-from:x`. It is **false for `-in:spam` and `-in:trash`**, because a
negated scope operator is not a filter inside a region — **it is the region declaration.**

Orchestrator-reproduced across four shapes: `-in:spam -in:trash borogrove`, `-in:spam borogrove`,
`-in:trash rollout cutover`, `-in:spam rollout cutover` — every one sends `in:anywhere` with
`includeSpamTrash=true`. R-RETR measured 201 such probes in a 5,979-query sweep, and 47 of 600
randomised trials disclosing a SPAM or TRASH row as `role: matched`, `outcome: answered`.

**This is the most serious thing found since round 15's blocker**, and not because of the recall
cost. A user who types `-in:spam` has stated a boundary. Crossing it is a different kind of wrong
from returning too little: MailWeave read mail it was told not to read, and reported success.

The fix is not a special case for two operator names. **The asymmetry clause needs a reason that
is true**: what distinguishes a fragment whose omission widens *within* a region from one whose
omission *changes* the region. Derive it from what the operator does, so it holds for scope
operators nobody has added yet. And note R-RETR's observation that the current fix is
**unasserted** — planting the defect back leaves all 2,248 tests green.

## Part 2 — R-RETR-027 (HIGH). A negated phrase is searched *for*.

`-"quadrant notice zephyr"` loses its polarity: the matching message comes back `role: matched`
with `constraint_coverage ('phrase',)` and `term_coverage 1.0`. The user asked for messages
*without* that phrase and got the one message that has it, reported as a match.

Pre-existing for colon-free phrases; **newly reached this round** for colon-carrying ones, which
R-RETR measured by planting Part 2 out. Round 17's own test asserts only the half that works —
the eleventh time a test has covered one shape and trusted its peer.

## Part 3 — R-RETR-028 (HIGH). Part 4's honesty rule never reached L0.

`PO-2026-0041 zephyr` executes `"PO-2026-0041"`, halts under D.3-1b, and reports
`enforced ('terms',)`, `term_coverage 1.0`, `sufficiency: sufficient` over a row that does not
contain "zephyr". Round 17 fixed `enforced` for the rungs it was looking at and L0 kept the old
behaviour. Also unasserted — planting it back leaves the suite green.

Fix `enforced` where it is *derived*, not per rung, so a rung added later inherits it.

## Part 4 — the two unasserted fixes are their own finding

R-RETR reports that planting back both R-RETR-026's and R-RETR-028's fixes leaves 2,248 tests
green. A fix no test defends is a fix the next round can silently undo. Every behaviour this round
changes gets a test that **fails when the behaviour is removed** — and say in your report which
existing round-17 fixes you found similarly unasserted, because a sweep for that is more valuable
than the two the reviewer happened to check.

## Part 5 — ROUTE-01 is one finding from restorable

R-RETR recommends **not** restoring it this round on one named ground: the acceptance enumerates
five things and the fifth — **affordances** — is absent from every zero-evidence response it
produced (R-RETR-032, LOW). The regression that caused the revert is fully closed and measured.
Close R-RETR-032 and ROUTE-01 is one reviewer-run from PASS at full scope. Do not mark it
yourself.

## Part 6 — the remaining MEDIUMs and LOWs

R-RETR-029..034 as filed. Where a fix is genuine, take it; where it is not, leave it open with the
reason and the workstream.

## The owner's other four instructions, verbatim in effect

Alongside OD-5's provenance field, the owner named four things this round must ensure. They map onto
the parts above; they are restated here so none is treated as optional:

1. **Explicit positive or negative scope is preserved across every probe. `-in:spam` must never
   search spam.** (Part 1, A9-A2.)
2. **Negated phrases remain exclusions.** (Part 2.)
3. **L0 uses the corrected truthful `enforced` semantics.** (Part 3.)
4. **Regression and mutation tests that fail when any of these defects are replanted, including an
   operator-family sweep.** (Part 4 — and note the sweep is over the *family*, not per operator.
   Enumerating `in:` and `label:` by name would be the fourteenth instance of the pattern that
   produced A9.)

L3's `in:anywhere` broadening **stays**, reached only when the query named no scope at all and only
after nothing was found. That is A.7's published step and R-RETR's reasoned verdict.

## Constraints

OD-1..OD-4; I-1..I-4; A1..A8 (A1 not yours). No LLM call, no embedding. No network in tests. No
real or realistic personal mail text. Do not touch retry/backoff. Do not mark any rubric criterion
PASS, do not restore ROUTE-01, do not edit `FINDINGS_LEDGER.md` or `RUBRIC_TRANSITIONS.md`.

**Do not tune against any reviewer's probe set** (`/tmp/rretr15/`, `/tmp/rretr16/`, `/tmp/rretr17/`).
Build your own and report your own numbers.

Gates clean: ruff, ruff format, mypy --strict, `python -m tools.guards`,
`pytest -q -m "not network"` (2,248 currently pass). Rubric stays **6 PASS / 0 FAIL / 0 BLOCKER /
107 NOT TESTED**.

Reintroduction: assert every anchor matched, every file changed, and `mailweave.__file__` resolving
into your scratch tree.

## Gating reviewer

`R-RETR`, on what this round changes.

## Exit condition

Every `MessageRow` states its mailbox provenance from observed labels, so a spam or trash result is
identifiable without reading a reason string. No probe reaches a region the query excluded —
`-in:spam` never searches spam. No negation is searched for as though it were a term. No response
claims coverage of a constraint the row it returned does not satisfy. And **every behaviour this
round changes fails a test when it is removed**, with the scope rule swept over the operator family
rather than per operator.
