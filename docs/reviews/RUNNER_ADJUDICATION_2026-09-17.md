# Runner review: reproduction and adjudication

Every one of the fifteen findings in `RUNNER_REVIEW_RESULT_2026-09-17.md` was reproduced on the
current tree with the reviewer's own probes before anything was changed. The probes are in
`docs/reviews/runner-review-2026-09-17/probes/` and both review snapshots are preserved
read-only under `docs/reviews/_snapshots/` with hashes in `REVIEW_SNAPSHOTS.sha256`.

**The runner is not fit to grade M2 and C4 is NO.** Neither of those is in question here. What
this file settles is which findings are defects in the instrument, which are decisions about
protocol that needed making rather than fixing, and which are concerns nobody has demonstrated.

## The two adjudications that changed what got built

**A sample-size floor does not go on an absolute invariant.** The review asked for registered-n
floors on four clauses. Two of them are existence falsifiers as registered:
`ORIVRA_V1_PLAN.md:877` says H1 is falsified if "embedding calls appear on F1/F2 traces" and
`:878` says H2 is falsified if "F1 ordering changes". One embedding call on one exact-lookup
case is the event the hypothesis says does not happen, and a floor there would mean the runner
observed the forbidden thing and reported NOT_EVALUABLE because it had not observed enough of
it. Floors were added to the two clauses that are rate comparisons and withheld from the two
that are not, and each clause now says in its own text which kind it is.

**Non-execution is not inferred from identical outputs.** The review read H3's wire-identical
arms as evidence the selection factor never fired. Two arms can produce identical output
because the factor did nothing, and that null effect is a result a campaign exists to find; a
rule that calls it non-execution throws the result away. So the runner requires **positive**
evidence from an instrument - `factor_ran` reads counters and nothing else - and where no
instrument exists it says so rather than assuming either way. That is why the repair adds a
counting proxy at the selection seam: there was no way to tell the two apart, and now there is.

## Adjudication

| id | reproduced | class | what was done |
|---|---|---|---|
| RR-01 | yes, `p11` | **demonstrated defect** | F17's clause was scored with H1's "does not rise" operator against a "drops" falsifier, so equal recall falsified H3. `_compare` takes the direction from the registered falsifier |
| RR-02 | yes, `p2` (a)-(d) | **split: defect on two clauses, protocol decision on two** | floors added to `F12-does-not-regress` and `F3-flatness-improves`; deliberately withheld from `no-embedding-on-F1-F2` and `F1-ordering-unchanged`, which are existence falsifiers, and each now says so in its detail |
| RR-03 | yes, `p4` | **demonstrated defect** | `None` counters recorded as `None`, never 0; `counter_state`; a clause reading an absent instrument is NOT_EVALUABLE; `semantic_cost` recorded per case and cross-checked with the seam, a disagreement making the clause NOT_EVALUABLE |
| RR-04 | yes, `p11` | **demonstrated defect, with the review's proposed test rejected** | every clause now requires positive instrument evidence that its factor executed. The selection seam had no instrument at all, so one was added |
| RR-05 | yes, code-read | **demonstrated defect** | `evaluate`'s baselines and the comparison table are both derived from `HYPOTHESIS_PAIRS`; the `full vs no-rerank` block exists; asserted through `main(["--dry-run"])`, not through `evaluate` |
| RR-06 | yes, code-read | **demonstrated defect** | one `build_arm` constructor for the campaign and the dry run. The dry run also honours `--out` now, so the record writer is exercised offline |
| RR-07 | yes, `p9` | **demonstrated defect** | per-arm watermark under the traces root. The production state directory is no longer touched, in either direction |
| RR-08 | yes, `p2` P3 | **demonstrated defect** | one negative per-case `cut_loss` makes the metric INCONCLUSIVE; it is an instrument fault and no other case can average it away |
| RR-09 | yes, `p6` (96 foreign ids) | **demonstrated defect** | the exception path drains the fetch log and the trace cursor |
| RR-10 | yes | **protocol decision** | `python -m mailweave_harness.evaluation` is the canonical versioned entry point. Every record now carries `entry_point` and `SCOPE`, which names the plan baselines and metrics this command does **not** compute and states that `boundary`/`queryfree` are not run by it. The brief and package are corrected in place |
| RR-11 | yes, `p2` P9 | **demonstrated defect** | controls excluded from every recoverability term, with their own report including whether a control was answered. Reported, not graded |
| RR-12 | yes, `p10` | **demonstrated defect** | `any_of` scored any-of, threaded from the case file through `evaluate` to `family_recall` |
| RR-13 | yes, `p5` (3 of 5 arms) | **demonstrated defect** | `TraceCursor` starts at the file's current end |
| RR-14 | yes, `p7` | **unverified concern, recorded** | the `follow` state rule on partial recovery is arguable and no clause reads the after-expansion stage. Left as it is, with the reviewer's own LOW rating; a change here needs a registered rule, not a patch |
| RR-15 | partly | **unverified concerns, recorded; one trivial defect fixed** | expansion-record pool is PLAUSIBLE and unreached on the dummy corpus; `report.Difference` sign disagreement is code-read; `SEM_OFF.cross_encoder=True` is a spec-vs-behaviour gap in a test, not in the runner; the A16 manifest provenance is outside the grading path. The dry run's "six dummy cases" text said the wrong number and now counts them |

Three findings the review recorded as HIGH produce a verdict the evidence does not support on
the default path - RR-01, RR-02 and RR-03 - and all three are fixed. RR-04 is the fourth HIGH
and is fixed in a different way from the one proposed, for the reason given above.

## What the repair does not do

* It does not add the plan's missing baselines (B, C, D, E, F at other N) or its missing
  metrics. Those are a scope question, not an instrument defect, and they are in
  `EVALUATION_SCOPE_DECISION_2026-09-17.md`.
* It does not touch the corpus, the criteria, the frozen gate, the product's behaviour or any
  existing record. The one product-adjacent change is the runner wrapping the shipped
  `QueryAwareFill` in a counting proxy, which counts and delegates.
* It does not re-open RR-14 or the RR-15 items. They are recorded as open with their evidence.

## Gates

* `tests/test_runner_repair_2026_09_17.py` - 21 tests, one per finding that produced a defect,
  each written from the reviewer's probe. Five of them go through `main(["--dry-run"])`.
* the runner's own suite, unchanged in intent: `test_acceptance_runner.py`,
  `test_evaluation_harness.py`, `test_evaluation_cli.py`, `test_h2_rerank_arm.py`,
  `test_h2_verdict_follows_the_rerank_arm.py`. Four fixtures needed updating and the note on
  each says why: they asserted properties of runs whose factor was never instrumented.
* `mypy harness/src server/src`: clean, 176 files.
