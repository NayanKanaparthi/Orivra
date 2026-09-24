# ROUND 22 — WS-10 escalation policy, over a handle that reports what it saw

**Issued by:** orchestrator, 2026-09-05
**Protocol:** `docs/AGENT_LOOP.md` §5, gate per §5a **and OD-6's urgency rule**.
Third of OD-6's five workstreams to the usable milestone.

## What round 21 established, and what it did not

WS-06's redemption order **survived attack**. R-RETR could not get around it: the liveness probe is
unconditional, reads a resource the cache does not hold, and `cache_tautology` is computed from
content provenance rather than a flag anyone sets. `fetched_at` is never restamped on any path. The
five error classes stayed distinct under every corruption, replay, rotation and restart it built,
and 300 randomised mutation sequences against an external oracle produced **0 false-clean and 0
false-stale**. That is settled; you are not re-opening it.

What did not survive is the **evidence**. Read Part 0 before Part 1.

## Part 0 — three findings, two of which block your own workstream

**R-RETR-058 (MEDIUM). The load-bearing test is four-eighths vacuous.** The commonality property —
*every field of the answer is produced by the step that produced it, and a step that did not run
leaves its field at its "not reached" value* — runs over a matrix containing **no cache-served
answer and no clean redemption**. So four of its eight clauses assert nothing, including clause (d),
which exists for BLOCKER ADV-002. **Planting ADV-002's own defect leaves the test green.** Round
21's report claims the matrix "adds the clean redemption as the eighth answer"; that is false on
execution. Fix the matrix, then plant each of the eight clauses and show each fails.

**R-RETR-059 (MEDIUM, blocks you).** When the liveness walk stops with pages outstanding,
`handle_stale` collapses into `handle_stale_unverifiable`: content is served while the response says
the change could not be verified. It was verified — the walk *saw* it. Amendment **A10** now states
the rule: a walk that saw a change and ran out of pages reports `handle_stale`;
`handle_stale_unverifiable` is for a walk that observed nothing and could not finish. The one-line
fix leaves the suite green, and so does the defect. Pin it.

**R-RETR-060 (MEDIUM, blocks your budgets).** The watermark is the *thread's* own `historyId`, so
the walk starts arbitrarily far back. With Gmail's 100-record page default and
`max_liveness_pages = 1`, 150 unrelated changes make **every** redemption unverifiable with the LRU
permanently bypassed at two calls, forever. **A10 amends the derivation**: `history_id` is the
mailbox watermark observed at fetch, not `min(thread_history_ids)`. The field itself is accepted.

You cannot account for budget honestly on top of a handle path that spends two calls per redemption
forever and mislabels what it found. That is why these come first.

**R-RETR-061/062**: `caught_by` citations are read collectively, so two name a test that does not
catch; and the `elsewhere=True` column is an artefact of the manifest's own anchor-integrity test.
Measured honestly, R49/R51/R54/R56 are defended by exactly one test each. Fix the accounting; do not
inflate it.

R-RETR-063/064 as filed.

## Part 1 — WS-10: escalation policy, budgets, stopping, outcome

From `docs/IMPLEMENTATION_PLAN.md`, whose WS-10 row is normative:

* The ladder state machine **L0→L6 + LR** under a per-query `budget_accountant` nested in the
  process-wide governor.
* AD **§A.7**'s caps enforced in code, and **§D.3**'s stopping rules **in their published order**.
  Order is not decoration: round 16 imported rule 1b's escape into rule 2 and switched L1b off for
  ordinary queries.
* `floor_quota_units = 845` clamp-up, with `budget_clamped{requested, applied, why}`.
* **The mid-rung timeout contract**: emit what was retrieved, unfinished work becomes `not_tried`,
  and undisclosed members of `H` become **withheld**. A timeout is not permission to forget.
* **OD-2's three-way `outcome`**, and this is the round's honesty centre: `not_found` **only** when
  no applicable rung is untried for budget, cap, timeout or error *and* `budget_caps_hit` is empty.
  Otherwise `inconclusive`. MailWeave never claims a mailbox does not contain something when it
  simply stopped looking.
* `not_tried[].why` from its closed vocabulary — `not_applicable` versus
  `budget | cap | timeout | error`.

Round 15 left a live question here, and it is now yours: the vocabulary has **no value for "the
policy declined to run this rung because evidence already existed."** Round 15 used
`not_applicable` and never emitted `not_found`, so OD-2's machine-checkable rule was never violated.
Decide it: either a fourth value with its reasoning, or an argument that `not_applicable` is
correct. State which and why. This is a vocabulary question, so make the case rather than assuming.

## What exists — use it, do not rebuild it

`DispositionLedger` (you do not do the accounting), `mailweave.query` + `mailweave.retrieval`
(scope preserved across every probe, A9), `mailweave.structure` (WS-05's map),
`mailweave.handles` (WS-06), `MailboxProvenance` on every row including stubs (OD-5),
`mailweave.content` (A7). Network-free test pattern:
`tests/test_lexical_ladder.py`, `tests/test_thread_map_round20.py`.

## The two defects this project keeps producing

Seventeen instances of **"one shape validated, peers trusted."** Seven rungs times three outcomes
times the timeout contract is a large shape space; find the commonality and test **that** — and
after R-RETR-058, check your own commonality test's *matrix* covers the shapes it claims, because
that is exactly how the last one came to assert nothing.

And **a claim wider than the code**: every docstring claim about what the budget guarantees or what
an outcome means gets executed.

## Constraints

OD-1..OD-6; I-1..I-4; A1..A10 (A1 not yours). No LLM call, no embedding. No network in tests. No
real or realistic personal mail text. **Do not touch the retry/backoff constants** — still an open
owner decision, and it is adjacent to your budget work, so be careful. Do not mark any rubric
criterion PASS; do not restore ROUTE-01; do not edit `FINDINGS_LEDGER.md` or
`RUBRIC_TRANSITIONS.md`. Do not tune against any reviewer's probe set (`/tmp/rretr15..21/`).

Gates clean: ruff, ruff format, mypy --strict, `python -m tools.guards`,
`pytest -q -m "not network"` (**2,439** currently pass). Rubric stays **6 PASS / 0 FAIL / 0 BLOCKER
/ 107 NOT TESTED**.

Reintroduction: assert every anchor matched, every file changed, and `mailweave`, `tests` and
`mailweave_harness` all resolving into your scratch tree — copy the **whole** tree including
`docs/`. And per R-RETR-061: a `caught_by` citation must name a test that **individually** catches
its plant, verified by deselecting the rest.

## Deliverable

`docs/reviews/ROUND_22/IMPLEMENTER.md`: per part, what changed, what each test establishes, what you
could **not** establish. Then: the commonality across the ladder's shapes, the test covering it, and
**proof its matrix reaches every shape it claims**; your ruling on the `not_tried[].why` vocabulary
question with its reasoning; every docstring claim about budgets or outcomes with executed evidence;
your answer to "have I trusted a peer?"; and anything unreachable, with its workstream and whether
it blocks integration.

## Gating reviewer

`R-RETR`, findings classified by severity **and** urgency.

## Exit condition

No response says `not_found` when it stopped looking. A timeout emits what it retrieved and
withholds what it did not. A handle that saw a change says so. And the round's own commonality test
runs over a matrix that reaches every shape it asserts about.
