# ROUND 23 — WS-11: representation and query-aware disclosure. The thesis.

**Issued by:** orchestrator, 2026-09-05
**Protocol:** `docs/AGENT_LOOP.md` §5, gate per §5a **and OD-6's urgency rule**.
Fourth of OD-6's five workstreams to the usable milestone.

## Read this before the parts, because this round is different in kind

Every round so far built machinery. **This one builds the claim.** MailWeave's thesis is
*query-aware adaptive retrieval with progressive context disclosure*: that what a response
discloses about a thread should depend on what was asked, and that a fixed window around a hit
(the ±2 baseline every prior system uses) is the thing to beat. WS-04 through WS-10 exist so this
can be measured honestly. WS-16 will measure it. **You are building the thing being measured.**

Two consequences. First, the adversarial evidence is real and is kept on purpose: arXiv 2607.17598
(July 2026) finds progressive disclosure buys approximately nothing against a strong agent harness.
That paper is a permanent benchmark arm that could falsify this project, and nothing you build may be
shaped to make it harder to run. Second, the degenerate-strategy guards in `RELEASE_RUBRIC.md` for
DISC-01..06 are the rubric's own defence against a disclosure policy that looks adaptive and is not.
Read them before you design.

## The reply-chain floor, and the honest limit under it (OD-3)

**Membership is absolute; depth is declared.** Parents and direct children of every evidence
message are always *present* in the response. What is *not* promised is that they are present at
full text — a routine 40-message thread with six hits needs roughly 11,200 tokens to show every hit
and the whole chain at readable length, against a 9,000-token ceiling. The arithmetic does not close,
and OD-3 records that as an acceptance rather than a choice. The floor guarantees a later message that
*reverses* a decision cannot be silently dropped while earlier, more confident-looking messages are
shown. It does not guarantee you can read all of it. Promotion to deeper content happens **when the
evidence depends on it**, and that dependence is a judgement you must make explicit and testable.

## What you are building — `docs/IMPLEMENTATION_PLAN.md` WS-11 row is normative

* **E2 reply-chain floor** as above: parents and direct children always present; promoted to deeper
  content when the evidence depends on them.
* **E4 query-scored fill** with **fixed published weights** and reason strings. Fixed and published
  because a weight that moves is a weight that can be tuned to a benchmark, and WS-17 sweeps for that.
* **The A.9a degradation precedence 1–8, executed in that order**, each step recorded in
  `reductions[]` and named in `budget_caps_hit`. Order is the contract: the reader must be able to
  reconstruct what was sacrificed first.
* `body_clean` **600-token soft cap**, **250-token head-truncation step**. Every truncation is a
  `reductions[]` record with a count (A7: annotate, never silently delete).
* **9,000-token normal ceiling**, the **12,000-token overflow only for floor membership**, declared
  in `ceiling{}`. The overflow is not a budget; it is a promise that membership is never the thing
  cut.
* **Collapsed runs** (A3 positions, 0-based chronological, bounded, raising rather than clamping),
  `not_included_sources[]`, affordance minting as concrete `{tool, args}` (I-4: every affordance
  must execute).
* The **segment map** at AD §E.2's experimental level — clearly labelled experimental.

## What this round must NOT do, stated up front

* **Do not make disclosure depend on the query in a way that only helps the fixtures.** The
  degenerate-strategy guard for DISC-01 is exactly this: a policy that keys on fixture features is
  not query-aware, it is fixture-aware. Your weights are fixed and published; your reason strings are
  from a closed vocabulary; and the policy must be explainable for a query nobody has written yet.
* **Do not let the floor become the whole response.** If every row is promoted to full text "because
  the evidence might depend on it", you have built ±∞, not query-aware disclosure. The promotion
  rule must sometimes say no, and the test must show it saying no on a case where saying yes would
  have been easier.
* **Do not shape anything to disadvantage the fixed ±2 baseline.** WS-16 runs it as Baseline F. A
  thesis that cannot lose is not a thesis.

## Acceptance, from the plan's own column

* The **ladder-termination test on the 40-message / 6-hit case** — the case OD-3 was written about.
* **Floor membership survives every degradation step**, 1 through 8. This is the one property that
  must hold unconditionally; plant each step's removal of a floor member and show it refused.
* **F17 decision-reversal family scored at each depth tier** against Baseline F(±2). You build the
  scoring hook; WS-16 runs the family.
* **Query-aware versus fixed window at equal budget** — the comparison must be possible at *equal*
  token budget, or it measures budget rather than policy.
* **Context efficiency versus full dump.**
* **Self-truncation before host truncation.** The response never exceeds the ceiling it declares;
  the host never has to cut it.

## What exists — use it, do not rebuild it

`DispositionLedger` (withheld accounting is not yours — a row you cut becomes a withheld record with
an affordance, computed by the ledger), `mailweave.query` + `mailweave.retrieval` (A9 scope),
`mailweave.structure` (WS-05's map: reply tree, positions, participants), `mailweave.handles`
(WS-06: `map_id` for affordances), `mailweave.policy` (WS-10: budget, stopping, `outcome_of`),
`MailboxProvenance` on every row (OD-5), `mailweave.content` (A7 annotation; `body_clean` with
classified spans is the text you disclose from). Network-free pattern:
`tests/test_lexical_ladder.py`, `tests/test_thread_map_round20.py`.

## The two defects this project keeps producing

Eighteen instances of **"one shape validated, peers trusted."** Eight degradation steps times two
ceilings times floor-member-or-not is the shape space; find the commonality and test **that** — and
after R-RETR-058, prove your matrix reaches every shape it asserts about.

**A claim wider than the code**: every sentence you write about what disclosure guarantees is
executed. "Floor membership always survives" is the biggest claim in the project; it gets the
biggest test.

## Constraints

OD-1..OD-6; I-1..I-4; A1..A10 (A1 not yours). No LLM call, no embedding — E4's scoring is
mechanical, `generative_llm_calls = 0` is CI-enforced. No network in tests. No real or realistic
personal mail text. Do not touch retry/backoff. Do not mark any rubric criterion PASS; do not
restore ROUTE-01; do not edit `FINDINGS_LEDGER.md` or `RUBRIC_TRANSITIONS.md`. Do not tune against
any reviewer's probe set (`/tmp/rretr15..22/`).

Gates clean: ruff, ruff format, mypy --strict, `python -m tools.guards`,
`pytest -q -m "not network"` (**2,474** currently pass). Rubric stays **6 PASS / 0 FAIL / 0 BLOCKER
/ 107 NOT TESTED**.

Reintroduction: assert every anchor matched, every file changed, `mailweave`/`tests`/
`mailweave_harness` all resolving into your scratch tree (whole tree incl. `docs/`), and every
`caught_by` citation catching **individually**.

## Deliverable

`docs/reviews/ROUND_23/IMPLEMENTER.md`: per part, what changed, what each test establishes, what you
could **not** establish. Then: the commonality across the disclosure shapes and proof the matrix
reaches them; **the promotion rule stated once, and the case where it says no**; the published E4
weights and why each is what it is; every docstring claim about what disclosure guarantees, executed;
your answer to "have I trusted a peer?"; and anything unreachable, with workstream and whether it
blocks integration.

## Gating reviewer

`R-DISC` — the disclosure domain, which has not reviewed since round 9 and owns DISC-01..06 — with
findings by severity **and** urgency. R-DISC is told to attack the degenerate-strategy guards first.

## Exit condition

A response never exceeds the ceiling it declares. Every floor member is present at every
degradation step. What is disclosed depends on the query in a way that is explainable for a query
nobody has written, and the fixed ±2 baseline can be run against it at equal budget.
