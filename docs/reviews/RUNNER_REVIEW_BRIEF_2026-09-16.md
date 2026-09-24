# Independent review of the acceptance runner: brief

**For a reviewer who did not write this code.** The instrument that will grade M2 has been
written, extended and tested entirely by its implementer. This brief hands it over before its
numbers are read, on the same footing as the disclosure and navigation reviews.

**Do not review the corpus.** Its defects are known, open and separately scoped
(`CORPUS_REPAIR_PROPOSAL_2026-09-16.md`). This is about the instrument.

---

## 1. What you are reviewing

| | |
|---|---|
| Runner | `harness/src/mailweave_harness/evaluation/` - `__main__.py`, `arms.py`, `hypotheses.py`, `report.py`, `boundary.py`, `primitive.py`, `queryfree.py`, `cases.py` |
| Product seam it varies | `MailweaveService.selector`, `MailweaveService.cross_encoder`, the backend registry |
| Its own tests | `tests/test_acceptance_runner.py`, `tests/test_evaluation_harness.py`, `tests/test_evaluation_cli.py`, `tests/test_h2_rerank_arm.py`, `tests/test_h2_verdict_follows_the_rerank_arm.py` |
| Runnable, offline, no credential | `python -m mailweave_harness.evaluation --dry-run` runs the whole pipeline on a dummy corpus; `--schema`, `--export-kit DIR`, `--validate` are also offline |

## 2. Rubric

**R1 - one hypothesis, one factor, one baseline.** `arms.HYPOTHESIS_PAIRS` declares H1 against
`sem-off`, H2 against `no-rerank`, H3 against `fixed-window`. Check that each pair differs in
exactly one `Factor`, that `evaluate` reads each hypothesis's own baseline for **every** clause,
and that a missing baseline yields `NOT_EVALUABLE` rather than a substitution.

*This is where the instrument most recently failed and the failure survived its own test.* The
pairing was declared, the arm existed and the campaign ran it, while `evaluate` computed H2
against `semantic_baseline_arm` and `__main__` passed `SEM_OFF`. A test asserting the
declaration passed throughout. Assume the same shape exists elsewhere and look for it.

**R2 - the bypass is an absence.** `no-rerank` must not simulate a disabled cross-encoder.
Confirm that `ranking.rank` returns `MECHANICAL_ONLY` after the prohibition check and before any
backend is acquired or any pair scored; that no `Score` is attached; that the ordering is the
registered `mailweave/mechanical-v1`; and that `force_rungs` cannot resurrect it. Confirm the
default is `True` on every path that can construct it.

> **Correction, 2026-09-17 (RR-10).** R3 and R6 below describe `evidence_after`, `tier` /
> `tier present` / `content rows` / `run members`, and "13 answerable cases and the two
> `DIAG-UNANS-01/02` controls". **Those structures are not in
> `python -m mailweave_harness.evaluation`.** They exist in `benchmarks/paired-a16-runner.py`
> and `benchmarks/run-diagnostic-4311.py`, which are gitignored (`.gitignore:46`) and were
> never in §1's table. The same goes for the package's "whether the two baselines (`boundary`,
> `queryfree`) are computed and presented as baselines": neither module is imported anywhere
> under `harness/src`, so that command never runs them. The rubric described capabilities the
> program under review does not have. The command now states its own scope in every record it
> writes (`__main__.SCOPE`), and that statement is the thing to review against.

**R3 - what the numbers count.** `evidence_after` is the case's own **required** set, complete.
Check nothing conflates it with rows delivered, tier membership, or `answer_after`. The
first-response trace distinguishes `tier`, `tier present`, `content rows` and `run members`;
check the report never sums across them.

**R4 - the floors are real.** `REGISTERED_N` gates `cut_loss` at EP §4.3's 8 F16 cases;
`Measured.UNMEASURED` is not zero; a negative `cut_loss` is `INCONCLUSIVE`, not a figure. Try to
get a verdict out of the runner on fewer cases than the plan registers, or out of an unmeasured
pool.

**R5 - a hypothesis never holds on an unevaluated clause.** Existing test, worth attacking.

**R6 - the controls are kept apart.** The 13 answerable cases and the 2 controls
(`DIAG-UNANS-01/02`) must never be aggregated. A control that is answered is a corpus leak, not
a delivery.

**R7 - the instrumentation proves what executed.** Embedding and reranking counts come from a
proxy at the backend seam *and* from the response's `semantic_cost`. Check they are compared and
that neither is trusted alone.

**R8 - the arms are held constant in everything else.** Corpus, candidate generation, disclosure
policy and configured budgets. A factor that leaks between arms invalidates the pair.

## 3. How to report

The project's convention: numbered findings, severity, the exact evidence (file:line, the
command and its output), and why it matters. A finding you can demonstrate beats a finding you
can argue. Findings land in `docs/reviews/FINDINGS_LEDGER.md`; HIGH and MEDIUM are fixed before
any campaign number is read.

**A review that finds nothing is acceptable only if it shows what was tried.** Include that
section.

## 4. Things already known, so you do not spend time re-finding them

  * `arms.SPECS` runs five arms and is deliberately not a full factorial (three factors would be
    eight); the interactions nobody has a hypothesis about are not run.
  * H3 has arms but no *exercised* comparison on this corpus: zero `Band.FILL` rows survive the
    ladder, so the `fixed-window` arms are wire-identical to their twins (R-M2-098). That is a
    corpus/case-design problem, not a runner defect - but say so if you disagree.
  * The cross-encoder currently "admits no ids, feeds neither `hit_ranks` nor the top-k, and
    moves no lexical thread" (R-M2-093). H2 may therefore measure a null effect. The instrument
    still has to be able to measure it.
  * `make lint` and `make types` are red at HEAD and were before this work (R-M2-107); the 38
    `B023` in the corpus generator are not a defect and are demonstrated not to be (R-M2-114).
  * PF-4b measures reranking only, so R2 is not evaluable (R-M2-118).
