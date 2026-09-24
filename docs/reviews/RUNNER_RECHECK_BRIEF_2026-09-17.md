# Focused independent recheck of the runner repair

**Scope: RR-01 to RR-13 only, and whether each is actually fixed.** Not a fresh review of the
runner - that review happened and its result stands as the baseline. You are checking one
bounded repair against fifteen findings, plus two adjudications that changed what got built.

You did not write the repair. Take nothing in the adjudication as settled because it is written
down; the point of this pass is that one of its two judgements could be wrong.

## What to read

| | |
|---|---|
| the findings | `docs/reviews/RUNNER_REVIEW_RESULT_2026-09-17.md` (preserved read-only at `_snapshots/`, hashes in `REVIEW_SNAPSHOTS.sha256`) |
| the adjudication | `docs/reviews/RUNNER_ADJUDICATION_2026-09-17.md` - what was classed defect, decision, or unverified, and why |
| the repair | `harness/src/mailweave_harness/evaluation/{arms,hypotheses,__main__}.py`, `tests/fixtures/eval_dummy.py` |
| the regressions | `tests/test_runner_repair_2026_09_17.py`, 21 tests, five of them through `main(["--dry-run"])` |
| the original probes | `docs/reviews/runner-review-2026-09-17/probes/` - run them again |

```
export PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:.
python -m pytest tests/test_runner_repair_2026_09_17.py tests/test_acceptance_runner.py \
                 tests/test_evaluation_harness.py tests/test_h2_rerank_arm.py \
                 tests/test_h2_verdict_follows_the_rerank_arm.py
python -m pytest tests/test_evaluation_cli.py          # ~3 min, split with -k if your shell caps
python -m mailweave_harness.evaluation --dry-run --traces T --out record.json
python docs/reviews/runner-review-2026-09-17/probes/pN_*.py
```

## The two judgements to attack first

**1. Floors were withheld from two clauses on purpose.** `no-embedding-on-F1-F2` and
`F1-ordering-unchanged` carry no registered-n floor, because `ORIVRA_V1_PLAN.md:877-878`
registers them as existence falsifiers - "embedding calls appear", "F1 ordering changes". If
you think a floor belongs there, say so and say what the falsifier then means. If you think a
floor is wrongly *absent* somewhere else, that is the same finding in reverse.

**2. Factor execution is read from instruments, never inferred from identical outputs.** The
original review proposed reading an unexercised factor off two arms producing the same wire
output. That was rejected: a null effect looks the same from outside, and a rule that calls it
non-execution discards the result. `hypotheses.factor_ran` reads counters only, and a counting
proxy was added at the selection seam because none existed. Attack this three ways: is the new
selection instrument counting the thing it says it counts; can a clause still be graded on a
pair whose factor did not run; and is there a case where an instrument is present, the factor
ran, and the clause is *wrongly* NOT_EVALUABLE.

## Per finding

For each of RR-01..RR-13: run the probe, then try to make the old behaviour come back. A fix
that holds on the probe and not on a neighbouring input is not a fix. Specifically worth
trying:

* **RR-01** - make F17 recall equal, above, and below the baseline. All three verdicts right?
* **RR-02** - the floors on F12 and F3 flatness: can you get a verdict below the registered n
  by another route (a different stage, `any_of`, a family with mixed cardinality)?
* **RR-03** - `None` counters. Can you still get a HOLDS out of an arm whose backend did not
  load? Does a `semantic_cost` disagreement reach the verdict?
* **RR-04** - the new `select_calls`. Is it reset per case; does it count the shipped
  `QueryAwareFill` and not just the injected `FixedWindow`; does it survive `build_arm` being
  called twice on one service?
* **RR-05** - `HYPOTHESIS_PAIRS` now drives both the baselines and the table. Add a fourth pair
  and check both follow. Is there any remaining path where a hand-written name reaches
  `evaluate`?
* **RR-06** - one `build_arm`. What still differs between the dry run and `_run`? The docstring
  claims are now testable; test them.
* **RR-07** - per-arm watermark. Does anything still write the production state directory?
* **RR-08** - one negative case makes it INCONCLUSIVE. What about a case that is exactly zero,
  or a pool read from the network fallback while the disclosure came from a semantic pool?
* **RR-09 / RR-13** - the drain and the cursor. Two campaigns into one root; a case that raises
  inside `follow` rather than in the first search; an arm whose sink file is deleted mid-run.
* **RR-11** - controls excluded. Is `answered_with_content` the right readout, and does the
  exclusion hold in `report.render` and the `--out` record as well as in `recoverability`?
* **RR-12** - `any_of`. Is it threaded everywhere a metric reads `required`, including
  `mean_cut_loss` and `report`?

**RR-14 and RR-15 were not repaired.** They are recorded open with the reviewer's own ratings.
Say if you think that is wrong, but they are not the subject of this pass.

## Out of scope

The corpus (frozen, C4 = NO, its own review is done), the criteria, the evaluation-scope
proposal in `EVALUATION_SCOPE_DECISION_2026-09-17.md`, and anything touching a mailbox.

## How to report

Numbered findings, severity, exact evidence - file:line, command, output - and whether each of
RR-01..RR-13 is **fixed**, **partly fixed**, or **not fixed**. A finding you can demonstrate
beats one you can argue. A recheck that finds nothing is acceptable only if it shows what was
tried, including the two judgements above.
