# Runner review package: what to read, what to run, in what order

**Hand this to a reviewer who did not write the runner.** The rubric is
`RUNNER_REVIEW_BRIEF_2026-09-16.md`; this file is the package around it - the exact commands,
what each one proves, and the boundary of the review.

**This review does not wait for the corpus.** The instrument and the corpus fail independently
and are reviewed independently. The corpus's own state is
`CORPUS_REPAIR_ROUND2_RESULT_2026-09-16.md`: its content gate **fails**, it was frozen on
2026-09-17 with generator repairs stopped, and it is now with its own independent reader
(`CORPUS_REVIEW_PACKAGE_2026-09-17.md`). The separate case-authoring package is commissioned
only after that read. Nothing in this package depends on any of it - start now.

---

## 1. Everything runs offline, with no credential and no mailbox

```
# from the repository root, with an isolated interpreter
export PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:.

python -m mailweave_harness.evaluation --schema             # the case-file contract
python -m mailweave_harness.evaluation --export-kit KIT      # the authoring kit, 5 files
python -m mailweave_harness.evaluation --validate CASES.json # a case file against a corpus
python -m mailweave_harness.evaluation --dry-run --traces T  # the whole pipeline, dummy corpus
```

`--dry-run` is the one to start from: it runs every arm, the hypothesis evaluation and the
report over a dummy corpus, writes one trace tree per arm under `T/`, and prints
`NOT_EVALUABLE` for every hypothesis - **which is the correct output**, because six dummy cases
cannot reach any registered n. A reviewer who sees a verdict there has found R4.

Its own tests, all offline:

```
python -m pytest tests/test_acceptance_runner.py tests/test_evaluation_harness.py \
                 tests/test_evaluation_cli.py tests/test_h2_rerank_arm.py \
                 tests/test_h2_verdict_follows_the_rerank_arm.py
```

`tests/test_evaluation_cli.py` takes about three minutes; the rest are seconds.

## 2. Reading order

1. `arms.py` - `Factor`, `ArmSpec`, `SPECS`, `HYPOTHESIS_PAIRS`. R1 and R8 live here.
2. `hypotheses.py` - `evaluate` and its clause structure. R1, R5.
3. `ranking.py` - the `MECHANICAL_ONLY` bypass and where it sits relative to the prohibition
   check and the backend acquire. R2.
4. `report.py` and `primitive.py` - what the numbers count. R3, R4, R6.
5. `boundary.py` and `queryfree.py` - the two baselines the report carries beside the arms.
6. `__main__.py` last, because it is where the wiring failure below actually lived.

## 3. The failure this instrument has already had, and what it means for the review

H2's pairing was declared in `HYPOTHESIS_PAIRS`, the `no-rerank` arm existed, the campaign ran
it - and `evaluate` computed H2 against `semantic_baseline_arm` while `__main__` passed
`SEM_OFF`. **A test asserting the declaration passed throughout.** The repair added an
end-to-end verdict regression on a fixture where the two baselines disagree, so the reported
verdict has to follow `no-rerank`.

The lesson for the review is not "check H2". It is: **a declaration and the thing it declares
are two artefacts here, and only one of them was tested.** Assume the same shape elsewhere.

## 4. Scope boundary

| In scope | Out of scope |
|---|---|
| the runner, its arms, its hypothesis evaluation, its report, its instrumentation | the corpus's content, its families, its register or shape leakage |
| whether a verdict can be produced that the evidence does not support | whether the corpus can support M2 acceptance |
| ~~whether the two baselines (`boundary`, `queryfree`) are computed and presented as baselines~~ **withdrawn 2026-09-17, RR-10: this command imports neither** | the query-free solver's *score*, which is the corpus's problem and is frozen |
| the five test files above | `tests/test_coverage_rules.py` and `tests/test_corpus_content.py`, which are the corpus's gate |

## 5. What a finding looks like

Numbered, with a severity, the exact evidence - `file:line`, the command, its output - and why
it matters. Findings go to `docs/reviews/FINDINGS_LEDGER.md`. HIGH and MEDIUM are fixed before
any campaign number is read.

A review that finds nothing is acceptable **only if it shows what was tried**. Include that
section.

## 6. Already known - do not spend time re-finding

Section 4 of `RUNNER_REVIEW_BRIEF_2026-09-16.md` lists these in full. In short: `SPECS` is
deliberately not a full factorial; H3's arms are wire-identical on this corpus because no
`Band.FILL` row survives the ladder (R-M2-098); the cross-encoder currently moves nothing
(R-M2-093), so H2 may measure a null effect and the instrument still has to be able to measure
it; lint and types were red at HEAD before this work (R-M2-107); the corpus generator's `B023`
diagnostics are demonstrated safe (R-M2-114); PF-4b measures reranking only, so R2 of the
broader comparison is not evaluable (R-M2-118).
