# Independent review of the acceptance runner: result

**Reviewer:** independent (did not write the runner). **Date:** 2026-09-17.
**Brief:** `RUNNER_REVIEW_BRIEF_2026-09-16.md` (R1-R8). **Package:** `RUNNER_REVIEW_PACKAGE_2026-09-16.md`.
**Verdict: the runner is not fit to grade M2 yet.** 4 HIGH, 8 MEDIUM, 3 LOW. Three of the HIGHs produce a
verdict the evidence does not support on the default command path. R2 (the bypass) passes.

Nothing in the product, generator, criteria, existing records, the ledger or the Mac `.venv` was modified.
New files only: this report and `docs/reviews/runner-review-2026-09-17/` (probes, hashes, dry-run output).
Ledger rows are proposed in section 5 for the owner to enter; ids RR-01..RR-15 are local to this review.

---

## 1. What was reviewed, exactly

| | |
|---|---|
| Checkout | HEAD `9a03eb42c0f928d4ce72f371215538378dc71b49` **plus an uncommitted working tree**. The H2 repair itself is uncommitted: `arms.py`, `hypotheses.py`, `__main__.py` are modified and both `tests/test_h2_*.py` are untracked |
| Working-tree identity | `git diff HEAD --binary \| sha256sum` = `6927bf648a3eb156...` ; per-file sha256 of all 32 reviewed files in `runner-review-2026-09-17/rr_manifest.sha256` (e.g. `arms.py` `bb67d319...`, `hypotheses.py` `ac176ec0...`, `__main__.py` `289f6052...`, `ranking.py` `bc2b1b15...`) |
| Unchanged during review | re-hashed the live tree against the manifest after the last probe: identical; diff hash identical |
| Frozen corpus | `tools/gate/freeze_corpus.py --check benchmarks/gate/corpus-freeze-round2.json` -> `{"frozen": true}` (run on the snapshot copy, which is byte-identical) |
| Isolation | copy of the tree outside the repo (excluding `.git`, `.venv`, OAuth files, `marketing`), fresh `uv sync --frozen --all-packages --all-extras` into a separate venv. Python 3.12 from `uv.lock`. No credential, no network to Gmail |
| Also read, because the brief's R3/R6 point at it | `benchmarks/paired-a16-runner.py` (sha256 in manifest). It is **gitignored** and outside the table in brief §1; see RR-10 |

Commands (from the snapshot root, `PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:.`):

```
python -m pytest tests/test_acceptance_runner.py tests/test_evaluation_harness.py tests/test_h2_rerank_arm.py tests/test_h2_verdict_follows_the_rerank_arm.py   # 56 passed
python -m pytest tests/test_evaluation_cli.py            # 14 passed (run in two -k halves for a 180 s shell limit)
python -m mailweave_harness.evaluation --dry-run --traces T   # exit 0, output in runner-review-2026-09-17/dry-run-output.txt
python runner-review-2026-09-17/probes/pN_*.py           # each finding cites its probe
```

**All 70 of the runner's own tests pass. Every HIGH below passes them too.**

---

## 2. Findings

### RR-01 HIGH (R5) - F17's clause is evaluated with the wrong operator: equal recall FALSIFIES "recall drops"

`hypotheses.py:517-525` scores F17 through `_compare`, whose rule is `HOLDS if left.mean_recall > right.mean_recall else FALSIFIED` (`:280-285`). That rule is H1's "does not rise". F17's quoted falsifier is **"reversal recall drops in the query-aware arm"**. Equal recall is not a drop, and the clause reports FALSIFIED.

```
$ python probes/p11_unexercised_factor.py
H3 falsified F17-reversal-holds falsified | F17 first-response recall: candidate 0.750 mean / 0.750 strict over 8 case(s)
```

**Why it matters:** R-M2-098 says `fixed-window` is wire-identical to `full` on this corpus. At n>=8 F17 recall is therefore equal by construction and **H3 will be reported FALSIFIED on the first real campaign**, and `__main__` exits 2. The clause text and its arithmetic are two artefacts and only the text was reviewed.

### RR-02 HIGH (R4, R5) - clauses with no registered-n floor decide hypotheses on one case

Floors exist only in `_compare` and `_cut_loss_clause`. `no-embedding-on-F1-F2` (`:375-393`), `F1-ordering-unchanged` (`:426-447`), `F12-does-not-regress` (`:448-469`) and `F3-flatness-improves` (`:495-516`, needs only two positions) carry none, and `HypothesisResult.verdict` returns FALSIFIED if **any** clause falsifies (`:67`).

```
$ python probes/p2_floors.py
== (a) one F1 case, ordering differs | total cases: 1
  H2 -> falsified   F16-cut-loss-falls=not_evaluable; F1-ordering-unchanged=falsified; F12-does-not-regress=not_evaluable
  _present exit code: 2 | printed: ['[H1] NOT_EVALUABLE', '[H2] FALSIFIED', '[H3] NOT_EVALUABLE']
== (b) one F1 case, one embed call | total cases: 1
  H1 -> falsified
== (c) two F3 cases, two positions | total cases: 2          (REGISTERED_N buried_evidence = 84)
  H3 -> falsified   F3-flatness-improves=falsified; F17-reversal-holds=not_evaluable
== (d) H2 with 8 F16, 1 F1, 1 F12 | total cases: 10          (REGISTERED_N exact_lookup = 10, semantic_negative_control = 10)
  H2 -> holds   F16-cut-loss-falls=holds; F1-ordering-unchanged=holds; F12-does-not-regress=holds
```

The package says "a reviewer who sees a verdict [in the dry run] has found R4". The dry run prints two clause-level verdicts on n=2 (`holds no-embedding-on-F1-F2`, `holds F1-ordering-unchanged 0 of 2`); the hypothesis-level NOT_EVALUABLE there is carried by *other* clauses' floors, not by these. (d) is a HOLDS on 1 F1 and 1 F12 case. One could argue an embedding call on F1 is an existence falsifier that needs no n; if so that must be a stated rule, and it cannot apply to ordering or F12 regress, which are noisy comparisons.

### RR-03 HIGH (R7, R8) - the embedding/rerank count has one source, and an absent instrument reads as zero

`_run` (`__main__.py:344-384`) creates each `CountingBackend` lazily inside the registry factory and captures `counters.get(spec.name)` when it builds the `Arm`. The factory only runs if `REGISTRY.acquire()` succeeds during `runtime.start`'s `warm_semantic_backend()` (`runtime.py:195`), whose `False` is discarded. On a machine where the models do not load, every semantic arm is silently lexical, `Arm.counter` is `None`, `run_case` records `embed_calls=0` (`arms.py:780-783`), and the clauses read that zero as a measurement. Probe mirrors `_run` line for line, substituting only `runtime.start` with the fixture service plus the same warm call:

```
$ python probes/p4_counter_absent.py
full                   warmed=False counter=None
...
H1 no-embedding-on-F1-F2 holds | 0 embed/rerank call(s) counted at the seam across F1 and F2
H2 F1-ordering-unchanged holds | 0 of 2 F1 cases ordered differently: []
full identical to sem-off on every case: True
```

Brief R7 says counts come from the proxy **and** `semantic_cost` and are compared. They are not compared anywhere in the runner: `semantic_cost` appears in `tests/test_h2_rerank_arm.py:143,164` and nowhere under `harness/src` (grep). `as_json` records neither `semantic_cost` nor `rerank_pairs`/`embed_texts`, so a campaign record cannot be cross-checked afterwards either. The test holds the property; the instrument does not have it. Required: refuse to run (or mark UNMEASURED) a semantic arm whose backend did not load; carry `semantic_cost` per case and fail the case on disagreement with the seam; `None` counter must be UNMEASURED, never 0.

### RR-04 HIGH (R1, R7) - a pair whose factor never executed gets a verdict instead of NOT_EVALUABLE

The runner holds the evidence that a comparison was not exercised (`rerank_calls` on `full`; for H3, identical wire output) and `evaluate` reads none of it. A null *effect* and an unexercised *factor* are reported identically.

```
$ python probes/p11_unexercised_factor.py
rerank calls on full across F16: 0
H2 falsified F16-cut-loss-falls falsified | F16 cut_loss: candidate 0.375 vs baseline 0.375
```

**I disagree with brief §4's framing** that H3's wire-identical arms are "a corpus/case-design problem, not a runner defect". The corpus problem is that the factor never fires; the runner defect is that it grades that as H3 FALSIFIED (with RR-01, twice over). Same for H2 under R-M2-093: "the instrument still has to be able to measure a null effect" is right, but a cross-encoder called zero times on the F16 cases is not a null effect of reranking. Each clause should require evidence the factor executed on the candidate arm for the cases it scores.

### RR-05 MEDIUM (R1) - the H2 wiring failure's shape is still present: the declaration is still not the wiring, and the failure site is still untested

* `HYPOTHESIS_PAIRS` is read by one test and by nothing in `harness/src` (grep). `_present` hand-wires `evaluate(semantic_baseline_arm=SEM_OFF.name, selection_baseline_arm=FIXED_WINDOW.name, rerank_baseline_arm=NO_RERANK.name)` (`__main__.py:223-230`) and a separate hand-written `comparisons` tuple (`:199-204`).
* That tuple has **no `full vs no-rerank` block**, so H2's verdict is printed with no comparison table for its own baseline, in stdout or in the `--out` record (`:255-263`). Visible in `dry-run-output.txt`: blocks for sem-off, fixed-window and both floors only.
* The regression test for the repair (`test_h2_verdict_follows_the_rerank_arm.py`) calls `evaluate` with explicit kwargs. It never goes through `_present`. The CLI test `test_the_live_run_and_the_dry_run_share_their_presentation` asserts `"_present(" in inspect.getsource(...)`, a string match. The line that was wrong last time (`__main__` passing `SEM_OFF`) would pass every current test if it regressed.

Required: derive both `evaluate`'s baselines and `comparisons` from `HYPOTHESIS_PAIRS`, and test the verdict through `_present` on runs where the baselines disagree.

### RR-06 MEDIUM (R8) - the dry run does not exercise the live arm construction; "differs in exactly two places" is false

`_present`'s docstring (`__main__.py:190-195`) says the live run differs from the dry run only in `runtime.start` and the case file. The arms are built by two independent copies: `_run` (`:344-384`) and `tests/fixtures/eval_dummy.dummy_arms` (`:317-362`). Observable differences: counter eager in the fixture vs lazy and conditional live (RR-03); no `watermark_path` in the fixture so LR never runs offline (RR-07); `FetchObserver` wraps `httpx.HTTPTransport` once per arm live vs per `open_client` in the fixture. `test_the_dummy_fixture_and_the_live_check_build_the_same_thing` holds the case file, not the arms. Every property the dry run is cited for in the handoff ("including `no-rerank`") is a property of the fixture's arms.

### RR-07 MEDIUM (R8) - live arms share one watermark file, so LR's state on a case depends on arm order

`runtime.start` gives every arm `settings.watermark_path` (`runtime.py:177`); `_advance_watermark` writes it after every search (`service.py:497-523`). Arms run interleaved in fixed `SPECS` order, so `full` always runs first against whatever the previous arm or process left. Probe gives the fixture's arms one shared file, as `runtime.start` does:

```
$ python probes/p9_watermark.py
== dry-run arms (as shipped)
   selftest-00 full=absent/... | sem-off=absent/... | no-rerank=absent/... (LR never runs)
== arms sharing one watermark file (as runtime.start builds them)
   selftest-00 full=not_tried:not_applicable/inconclusive | sem-off=ran/inconclusive | no-rerank=ran/inconclusive | ...
```

On a static seeded mailbox I observed the divergence in LR's state only, on the first case, with no outcome change. Not verified: whether LR's history walk adds ids to the FetchLog (the lexical arm's pool) or spends budget differently enough to move a response, and what happens on a mailbox that changes mid-campaign. It is also the production state directory `mailweave serve` uses, so a Claude Desktop session on the same account between runs changes the campaign's starting state, and the campaign changes the server's.

### RR-08 MEDIUM (R4) - a negative per-case `cut_loss` is averaged away

`mean_cut_loss` (`hypotheses.py:215-237`) tests `mean < 0` only. The docstring's own model says `pool_recall >= recall` per case, so one negative case is an instrument fault; it is diluted by the others and the result is `MEASURED`.

```
$ python probes/p2_floors.py
== P3 per-case losses: seven +1.0, one -1.0 (forbidden by the metric) -> measured 0.75 cases 8
```

RR-09 and RR-13 are two ways such a case arises in practice.

### RR-09 MEDIUM (R4, R8) - a first search that raises leaks its fetches into the next case's pool

`run_case`'s exception path (`arms.py:705-722`) returns without draining `arm.fetch_log` or advancing the cursor. The next case's `fetch_log.take()` (`:728`) includes the failed case's traffic, and that is the lexical arm's EP §6.4 pool.

```
$ python probes/p6_failed_case_leak.py        # raise simulated after the real search; the channel is the unchanged code path
case B pool, clean arm : 96 ids observed at the network layer
case B pool, after fail: 192 ids observed at the network layer
ids in B's pool that only A fetched: 96
```

### RR-10 MEDIUM (R3, R6, scope) - the baselines and the controls the rubric names are not in the runner

* `boundary` and `queryfree` are never imported by `__main__`, `report` or `__init__` (grep). The package §4 puts "whether the two baselines (`boundary`, `queryfree`) are computed and presented as baselines" in scope: **they are not computed or presented by `python -m mailweave_harness.evaluation` at all.** They are used by gitignored `benchmarks/*.py` scripts and `tools/gate/content_gate.py`.
* R3's `evidence_after`/`tier present`/`content rows`/`run members` and R6's "13 answerable + `DIAG-UNANS-01/02`" exist only in `benchmarks/paired-a16-runner.py` and `run-diagnostic-4311.py`, which are gitignored and not in brief §1's table. The rubric grades code that neither the review surface nor version control holds.
* In that script, controls are a hard-coded id tuple (`paired-a16-runner.py:70, 249-252`); any other control is counted with the answerable cases.

The owner has to decide which program grades M2. If it is `-m mailweave_harness.evaluation`, R3/R6 as written do not apply to it and RR-11 does; if the benchmark scripts are part of it, they need to be versioned and reviewed as the runner.

### RR-11 MEDIUM (R6) - in the campaign runner, controls are aggregated into recoverability and never read for leakage

Controls have an empty required set, so `family_recall` and `still_failing` skip them silently; nothing reports whether an `unanswerable_control` was answered. `recoverability` (`hypotheses.py:549-574`) counts every run on the arm, controls included. The dry run's `"cases": 11` is 10 answerable plus 1 control.

```
$ python probes/p2_floors.py
== P9 recoverability with one control (answered, 5 levels): {'cases': 2, ..., 'mean_levels_traversed': 3.0}
```

### RR-12 MEDIUM (R3) - `evidence_cardinality: any_of` is accepted, advertised and never scored

`cases.py:285` validates it, `--schema` prints it, `ResolvedCase.any_of` is computed (`:371, 448-461`), and nothing in `arms`/`hypotheses`/`report`/`primitive` reads either (grep). Every case is scored all-of.

```
$ python probes/p10_any_of.py
seed metric with any_of: True
runner family_recall: 0.5 strict 0.0
```

### RR-13 MEDIUM (R4) - a reused `--traces` root feeds the previous campaign's pool to this run's first case

`TraceSink` opens with `O_APPEND` (`trace/sink.py:108`); `TraceCursor.offset` starts at 0 (`arms.py:313`) and the first case takes every record in the file and breaks on the first with `pool_ids` (`:761-766`). The CLI default root is the fixed `benchmarks/traces`.

```
$ python probes/p5_trace_reuse.py             # earlier run into the same root, cases in another order
runs whose pool differs from a clean root: 3
  ('selftest-00', 'full')       clean: g-t0007-000..095   reused: g-t0060-000 .. g-t0065-095
  ('selftest-00', 'no-rerank')  same
  ('selftest-00', 'fixed-window') same
```

`pool_source` still says "semantic pool exposed in the trace". Refuse a non-empty root or start the cursor at the file's current end.

### RR-14 LOW (R7) - the R-M2-078 FAILED/INCONCLUSIVE state is mis-set on partial recovery and read by nothing in the campaign report

`follow` (`arms.py:675-682`) returns MEASURED whenever any required message arrived, even with a raised recovery call or a spent budget on the rest:

```
$ python probes/p7_follow_state.py
raise, m1 NOT in hand (only m2 required): state=failed
raise, m1 in hand, m2 out           : state=measured     exceptions=['mailweave_get_messages: RuntimeError']
budget 0, m1 in hand, m2 surfaced   : state=measured     stopped=call_budget
```

And `Reach.state` is read only by two benchmark scripts; `hypotheses`, `report.still_failing` and `as_json` read `CaseRun.state`, which is MEASURED whenever the first search returned, so an expansion that raised is reported as `surfaced_never_carried`. Rated LOW because no clause reads the after-expansion stage.

### RR-15 LOW - code-read only, not demonstrated

* **Pool from an expansion call.** `run_case` drains the FetchLog before `follow` (`:728`) but reads the trace cursor after it (`:761`), taking the first record *of the case* with a pool. If the first search exposed none and a followed `force_rungs` search did, that pool is paired with the first response's disclosure. Not reached on the dummy corpus (no search affordance was followed, `probes/p8_expansion_search.py`), so PLAUSIBLE.
* **`report.Difference`** decides `separated` on strict-rate intervals and direction on the mean delta (`report.py:53-62`); on all-of cases they can disagree in sign.
* **`SEM_OFF` declares `cross_encoder=True`** while its service has no cross-encoder; `test_the_two_arms_differ_in_exactly_one_factor` compares spec booleans, not observed execution, so it cannot fail for H1's pair.
* **Paired A16 runner provenance** (`paired-a16-runner.py:190-193, 466-513`): without `--overwrite` existing legs are kept while `manifest.json` is rewritten with the current tree's product digest, and the output directory is keyed on HEAD's short sha, not the tree digest. A dirty-tree rerun can pair old records with a new digest. Outside the M2 grading path, same shape.
* The dry run's closing text says "Six dummy cases"; it runs 11.

---

## 3. R2 - the bypass is an absence: passes

What was tried, none of which found a defect:

* Read `ranking.rank` (`ranking.py:172-306`): mechanical tier first; `prohibited_by` returns `NOT_APPLICABLE` before the `cross_encoder` check; the bypass returns `MECHANICAL_ONLY` with `rerank=None` before `registry.acquire()` and before `rerank_shortlist`; it precedes the `forced` branch, so `force_rungs` cannot reach the tier. `score_for` returns `None` when `rerank is None`. `.rerank(` is called only from `semantic/interface.py:139`, reached only through `rerank_shortlist`.
* Observed, dry-run fixture (`probes/p1_dryrun_instrumentation.py`): `no-rerank` seam `embed=2`, `rerank=0`, wire `rerank_pairs=0`, `ordering_method=mailweave/mechanical-v1` on both ranked responses; `full` seam `rerank=2`, wire pairs 50, one `+cross-encoder`.
* Defaults `True` on `rank`, `assemble`, `runtime.start`, `MailweaveService`, `ArmSpec`, `eval_dummy._service`.

One qualification: the dry-run fixture reaches the cross-encoder on 2 of 11 cases, so the offline evidence for the pair is thin. That is a property of the fixture, not a defect in the bypass.

## 4. Also tried, no finding

* Missing baseline for H2/H3 -> all clauses NOT_EVALUABLE, no substitution (`evaluate` with `rerank_baseline_arm=None`; covered by an existing test, re-read).
* Hypothesis-level HOLDS with any NOT_EVALUABLE clause: impossible (`HypothesisResult.verdict`). R5's existing test is correct as far as it goes; RR-01 and RR-02 are the ways round it.
* `Measured.UNMEASURED` for no pool is not zero: `mean_cut_loss` skips `pool_ids is None` and returns UNMEASURED when none remain. Confirmed; the gap is RR-08.
* Duplicate case ids are refused at load (`cases.py:345-349`), so n cannot be inflated that way.
* `first_response` recall reads only `_content_by_id` of the first envelope; stubs and snippets excluded. `evidence_tokens`/`distractor_tokens` count carried content only.
* Floor comparisons are labelled as against a fixed primitive policy, not an agent, and the floor's `after_expansion == first_response` is stated.
* Per-arm trace roots are separate (`__main__.py:374`); no interleaving between arms' files.

## 5. Proposed ledger rows (not entered; the ledger is an existing record)

| id | sev | one line | fix before numbers |
|---|---|---|---|
| RR-01 | HIGH | F17 "recall drops" scored with "must rise"; equal recall falsifies H3 | yes |
| RR-02 | HIGH | F1-ordering, F12, F1/F2-embedding and F3 clauses have no floor; H2 FALSIFIED/HOLDS and H1/H3 FALSIFIED on 1-2 cases | yes |
| RR-03 | HIGH | counter absent reads 0 (backend not loaded -> H1 embedding clause HOLDS); `semantic_cost` never cross-checked or recorded | yes |
| RR-04 | HIGH | unexercised factor (0 rerank calls, wire-identical selector) graded as null effect | yes |
| RR-05 | MEDIUM | `HYPOTHESIS_PAIRS` not the wiring; no `full vs no-rerank` report; H2 repair test bypasses `_present` | yes |
| RR-06 | MEDIUM | dry run's arms are a separate copy of `_run`'s | yes |
| RR-07 | MEDIUM | shared production watermark across arms; LR state order-dependent | yes |
| RR-08 | MEDIUM | negative per-case cut_loss hidden by the mean | yes |
| RR-09 | MEDIUM | failed first search leaks fetches into next case's pool | yes |
| RR-10 | MEDIUM | `boundary`/`queryfree` not in the runner; R3/R6 structures live in gitignored scripts | decision + fix |
| RR-11 | MEDIUM | controls aggregated in recoverability, no leak readout | yes |
| RR-12 | MEDIUM | `any_of` accepted and never scored | yes |
| RR-13 | MEDIUM | reused `--traces` root poisons first case's pool | yes |
| RR-14 | LOW | follow state rule on partial recovery; `Reach.state` unread | record |
| RR-15 | LOW | expansion-record pool (plausible), report sign, spec-vs-behaviour factor test, A16 manifest provenance, dry-run text | record |

**Re-review scope after repair:** RR-01..RR-13 each with a test that fails on the current tree. Per the brief's own lesson, tests for RR-02, RR-03, RR-05 and RR-11 should go through `_present` or `main(["--dry-run"])`, not through `evaluate` alone.
