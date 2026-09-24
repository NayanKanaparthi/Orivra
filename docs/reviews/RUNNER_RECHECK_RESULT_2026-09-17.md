# Focused recheck of the runner repair: result

**Reviewer:** the independent runner reviewer, who did not write the repair. **Brief:** `RUNNER_RECHECK_BRIEF_2026-09-17.md`.
**Baseline:** `RUNNER_REVIEW_RESULT_2026-09-17.md` (snapshot hash verified). **Scope:** RR-01..RR-13 and the two adjudications. Not a new audit.

**Verdict: still not fit to grade M2.** 5 fixed, 7 partly fixed, 0 not fixed, RR-10 closed as a recorded decision. The repair also opened
4 new HIGH defects, three of them caused by the RR-04 change. Adjudication 2 is right in principle, but the instruments that
carry it out count the wrong events. Adjudication 1 is right for FALSIFIED and wrong for HOLDS.

Nothing in the product, corpus, criteria, ledger, existing records or Mac `.venv` was changed. New files only: this report and
`docs/reviews/runner-recheck-2026-09-17/` (probes `q1`-`q4`, the dry-run output and `--out` record, hashes).

## 1. What was rechecked

| | |
|---|---|
| Tree | HEAD `9a03eb4` plus uncommitted working tree, diff sha256 `b8ccd98c0fe046f4...`; per-file hashes in `runner-recheck-2026-09-17/rr2_manifest.sha256` (`arms.py` `d94c918e...`, `hypotheses.py` `7952f27a...`, `__main__.py` `4739faaf...`, `eval_dummy.py` `8eb2267b...`, `test_runner_repair_2026_09_17.py` `e36c1252...`). Re-hashed at the end: unchanged |
| Isolation | fresh copy outside the repo; the separate review venv from the first pass; no credential, no mailbox |
| Snapshots | `REVIEW_SNAPSHOTS.sha256`: all match except `runner-review-2026-09-17/probes/p2_floors.py`, which was edited in place after it was hashed (one `print` changed so it survives `cl.value is None`). Harmless, but the probe no longer matches its recorded hash |
| Tests | the five fast files: **77 passed**; `test_evaluation_cli.py`: **14 passed** (two `-k` halves) |
| Dry run | `--dry-run --traces T --out record.json`: exit 0, all three hypotheses NOT_EVALUABLE, five comparison blocks including `full vs no-rerank` |

`PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:.` for every command below.

## 2. Status per finding

| id | status | evidence |
|---|---|---|
| RR-01 | **fixed** | `q1` J2: equal recall HOLDS, candidate above HOLDS, candidate below FALSIFIED (`hypotheses.py:858`, `direction="not_below"`). N-2 explains why a correct F17 operator can still grade an unexercised pair |
| RR-02 | **partly fixed** | F12 and F3 floors are in and hold: `p2` (c) two F3 cases -> NOT_EVALUABLE, (d) one F12 case -> NOT_EVALUABLE. Existence clauses: FALSIFIED on one case is correct and I agree with the adjudication. HOLDS on one case is not; see N-3 |
| RR-03 | **partly fixed** | `None` is no longer 0: `p4` now gives `no-embedding-on-F1-F2 not_evaluable`, "0 of 2 ... carried an instrument". But the same unloaded-backend run still reaches a verdict through H1's recall clauses (N-4), and the `semantic_cost` cross-check exists in name only (N-5) |
| RR-04 | **partly fixed** | the rerank instrument works: `p11` gives F16 NOT_EVALUABLE, "called 0 times on full across 8 instrumented case(s)". Four gaps remain: N-1, N-2, N-4, N-6 |
| RR-05 | **partly fixed** | the table follows `HYPOTHESIS_PAIRS`; `evaluate` does not fully (N-8) |
| RR-06 | **partly fixed** | one `build_arm` (`arms.py:825`) for both paths. Counter construction is still two copies: eager in `eval_dummy`, lazy and conditional on the model loading in `_run` (`__main__.py` factory), and neither refuses a semantic arm whose backend did not load. That is the path N-4 runs on |
| RR-07 | **fixed** | `build_arm` sets `watermark_path` to `<traces>/<arm>/watermark.json` (`arms.py:853`), and `_run` always passes `traces_root`. The production watermark is no longer read or written by the campaign. `runtime.start` still reads, and on refresh writes, the shared token store; that is credentials, not arm state |
| RR-08 | **fixed** | `p2` P3: seven +1.0 and one -1.0 -> `inconclusive`, "1 of 8 case(s) have a negative cut_loss". Exactly-zero cases are unaffected. Residual, not demonstrated wrong: a mean mixing semantic-pool and network-fallback cases is still MEASURED, with both sources joined in the note |
| RR-09 | **fixed** | `p6`: 0 foreign ids (was 96). A raise inside `follow` is already caught by `_execute`. Residual LOW: N-10 |
| RR-10 | **closed as decision** | `ENTRY_POINT` and `SCOPE` appear in the `--out` record and say what the command does not compute. I accept the decision. It is a scope choice, not a fix |
| RR-11 | **partly fixed** | controls are out of `recoverability` (`p2` P9: `cases: 1`, was 2), out of `report.render`, and not aggregated in `--out`. The readout is weak (N-9) |
| RR-12 | **partly fixed** | `evaluate` -> `family_recall` scores any-of (`q3`: 1.0). `mean_cut_loss`, `position_spread`, `report.differences` and `report.render` take no `any_of`, so the printed table and F16 `cut_loss` still score all-of (N-7) |
| RR-13 | **fixed** | `p5`: 0 of 5 arms diverge on a reused root (was 3). `TraceCursor.__post_init__` seeks to the end. Residual LOW: N-10 |

## 3. New findings

### N-1 HIGH (RR-04 regression) - H2 cannot HOLD on a correct product, and an F1 reorder no longer falsifies

`F1-ordering-unchanged` now requires `factor_ran(families=("exact_lookup",), factor="rerank")` (`hypotheses.py:660`). The product's gate forbids the cross-encoder on exactly that family: `ranking/gate.py:113` returns `prohibited_by=EXACT_SIGNAL_MATCH` when `exact.fired`. A correct server therefore always records 0 rerank calls on F1, and the clause is NOT_EVALUABLE on every campaign.

```
$ python probes/q1_judgements.py
== J1a: F1 on a correct product (rerank=0), ordering unchanged, 10 F1 cases
   not_evaluable | the cross-encoder was called 0 times on full across 10 instrumented case(s), so this pair did not exercise the factor it
== J1b: same, but ordering changed on 1 case (rerank=0 on F1)
   not_evaluable
```

The dry run shows the same thing on its own F1 cases (`dry-run-output.txt`, H2). Because `HypothesisResult.verdict` needs every clause evaluable to HOLD, **H2 can never HOLD**. J1b is worse: an exact-lookup reorder between `full` and `no-rerank` is reported as an isolation note, not as the falsifier. H2's claim is "without changing exact-match families". The gate not firing is the mechanism that keeps F1 unchanged, not missing evidence. The factor-execution precondition belongs on the family the reranker is meant to act on (F16). For F1, the registered falsifier is read as written. Plausibly the same problem affects F12 (`:703-747`, also gated on rerank running on F12), but I have not demonstrated it.

### N-2 HIGH (adjudication 2) - the selection instrument counts the selector being consulted, not selection reaching the response

`CountingSelector.select_calls` increments on every `select()` call. `plan_thread` calls `selector.select(thread, query)` unconditionally for every planned thread (`disclosure/plan.py:363`), before the ladder decides whether any FILL row survives. So `select_calls > 0` on every case of every arm, including a query-aware selector that admitted nothing.

```
$ python probes/q2_selection_seam.py                     # dry-run arms, all 11 cases
('full', 'select_calls') 18
('full', 'rows_admitted_by_selector') 0
('full', 'fill_rows_on_wire') 0
('fixed-window', 'select_calls') 18
('fixed-window', 'rows_admitted_by_selector') 65
('fixed-window', 'fill_rows_on_wire') 1
cases with identical message rows on full vs fixed-window: 10/11
```

On H3's candidate arm, `factor_ran("selection")` returns "ran" for a selector that admitted zero rows. With RR-01's correct operator, that makes identical arms a HOLD:

```
$ python probes/q1_judgements.py
== J2: selection 'ran' (select_calls>0) but arms identical; F17 at n=8
   equal            holds H3: not_evaluable
```

This is R-M2-098 exactly: no FILL row survives, and the runner now reads that as a null effect and grades F17 HOLDS. The principle, "read an instrument, never infer from identical outputs", is sound, and I withdraw my original proposal. But this instrument does not measure the factor. `rows_admitted` already exists, and a count of FILL-band rows on the response is also an instrument reading, not an output comparison. Either would separate "the selector acted and the result was null" from "the selector's output never reached the plan". The repair's own test (`test_identical_outputs_with_the_factor_exercised_are_a_result_not_a_gap`) builds `select=1` runs by hand, so it cannot catch this.

### N-3 HIGH (adjudication 1) - existence clauses need no floor to FALSIFY, but they HOLD on a single case

I agree that one embedding call on F1/F2, or one reordered F1 case, falsifies without a floor. The converse is not symmetric. "No embedding call appeared" on one F1 case and zero F2 cases is not evidence of "zero cost on exact-lookup families".

```
$ python probes/q4_existence_holds.py                    # 12 F4, 10 F11 at the floor; ONE F1 case, zero F2
H1: holds {'F4-recall-rises': 'holds', 'F11-recall-rises': 'holds', 'no-embedding-on-F1-F2': 'holds'}
   0 embed/rerank call(s) counted at the seam across F1 and F2 on 1 instrumented case(s), ...
```

The floor belongs on the HOLDS branch only: FALSIFIED on any observed occurrence, HOLDS only when the registered F1 and F2 cases (10 + 10) all ran instrumented. The same applies to `F1-ordering-unchanged` once N-1 is fixed. Answering the brief's question directly: with the floor on HOLDS only, the falsifier means exactly what `ORIVRA_V1_PLAN.md:877-878` says, and a pass means the plan's corpus was inspected.

### N-4 HIGH (RR-03/RR-04 not closed for H1) - an unloaded backend still yields H1 FALSIFIED

`factor_ran` is applied to H2 and H3 clauses and never to H1's F4/F11 recall clauses (`hypotheses.py:521-529`, unchanged `_compare`). Uninstrumented or unexercised semantic arms produce identical recall, and "does not rise" falsifies:

```
$ python probes/q1_judgements.py
== backend never loaded (counter None on both arms), 12 F4 cases, identical recall
   F4: falsified | F4 first-response recall: candidate 0.500 ... over 12 case(s)
== instrumented, embed=0 on every F4 case (L5 never ran), identical recall
   F4: falsified
```

This is the original RR-03 scenario (`p4`, "full identical to sem-off on every case: True") with the verdict moved from one clause to another. `_run` still does not refuse an arm whose backend did not load (RR-06).

### N-5 MEDIUM (RR-03) - the semantic_cost cross-check is nominal where it matters

`cost_disagreement` (`arms.py:512-530`) compares only `bool(rerank_pairs)`. It never compares embeddings, and it returns `None` whenever `semantic_cost` is `None`. The wire block is `None` on every response that did not escalate. That covers every F1/F2 case, the only cases the embedding clause reads (`dry-run-record.json`: `semantic_cost: null` on all 8 non-escalating `full` cases). Yet the clause detail says "cross-checked against the responses' own semantic_cost" (`hypotheses.py:579`).

```
$ python probes/q1_judgements.py
== seam 0 embed, wire says 50 embedded texts (F1)
   holds | 0 embed/rerank call(s) ... cross-checked against the responses' own semantic_cost
== wire semantic_cost None (not escalated) on every F1 case
   holds | ... cross-checked against the responses' own semantic_cost
```

There is also a structural mismatch (code-read): the seam counter spans the first response and every expansion call, while `semantic_cost` is the first response's alone. A reranking expansion search would register as a disagreement on a correct run.

### N-6 MEDIUM (RR-04) - one instrumented case licenses a family

`factor_ran` filters to instrumented runs and asks whether any of them ran (`hypotheses.py:367-440`). One instrumented case with a rerank call opens the clause for seven uninstrumented ones:

```
$ python probes/q1_judgements.py
== 8 F16 cases, only 1 instrumented and reranked, 7 uninstrumented
   falsified | F16 cut_loss: candidate 0.500 vs baseline 0.500
```

`embedding_calls` already marks the whole count UNMEASURED unless every case is instrumented. `factor_ran` should apply the same rule.

### N-7 MEDIUM (RR-12) - any_of stops at family_recall

```
$ python probes/q3_wiring_anyof_cursor.py
RR-12 family_recall with any_of: 1.0
RR-12 mean_cut_loss accepts any_of: False | value: 0.5 (any-of semantics: 0.0)
RR-12 position_spread accepts any_of: False
RR-12 report.render/differences accept any_of: False False
RR-12 report line: ['F16 ranking_stress  first response 0.500 vs 0.500 (delta +0.000, n=8)']
```

For any-of cases, the verdict path and the printed table now disagree, and F16 `cut_loss` counts a satisfied any-of case as a 0.5 loss.

### N-8 MEDIUM (RR-05) - evaluate still takes hand-keyed slots, and one candidate for all three

`_present` passes `candidate_arm=HYPOTHESIS_PAIRS["H1"][0]` plus the H1, H2 and H3 baselines by literal key. Change H2's pair, or add a fourth:

```
$ python probes/q3_wiring_anyof_cursor.py
RR-05 table blocks: ['full vs sem-off', 'fixed-window vs no-rerank', 'full vs fixed-window', 'no-rerank vs sem-off', ...]
RR-05 evaluate got candidate_arm = full (H2 pair now says fixed-window); H4 verdict printed: False
```

The table follows the declaration and the verdict does not. This is the declared-versus-wired shape again, one step smaller. `evaluate` should take the pairs mapping.

### N-9 LOW (RR-11) - the control readout counts the wrong signal

`answered_with_content` counts controls whose first response carried any message content (`hypotheses.py:904`) and ignores the terminal outcome. A control that returns `answered` with stub rows reads 0; a correct `not_found` that carries a body row reads 1. `declined` counts only harness exceptions (`CaseRun.declined`), not product declines. Code-read; reported, not graded, so LOW.

### N-10 LOW - residuals in the cursor and drain

* Deleting an arm's `trace.jsonl` mid-run leaves `TraceCursor.offset` past the new end. When the file grows back past it, `take()` seeks into the middle of a line and raises. That happens outside `run_case`'s try, so `run_all` aborts: `q3` gives "sink deleted before case 7: run_case raised ValidationError".
* Recorded in section 1: the preserved `p2_floors.py` no longer matches its snapshot hash.

## 4. The two judgements, answered directly

1. **Floors on existence falsifiers.** Correct for FALSIFIED and wrong for HOLDS (N-3). Separately, the RR-04 precondition put on the F1 existence clause makes it permanently unevaluable (N-1). The floor is not wrongly absent on any rate clause: F4, F11, F12, F3, F16 and F17 all carry one.
2. **Execution from instruments only.**
   * *Does the selection instrument count what it says?* No. It counts consultations (N-2).
   * *Can a pair whose factor did not run still be graded?* Yes, three ways: H1 has no execution check (N-4), selection "runs" when nothing was selected (N-2), and one instrumented case licenses the rest (N-6).
   * *Present instrument, correct execution, wrongly NOT_EVALUABLE?* Yes: F1 ordering on every correct product (N-1), and possibly F12.

## 5. Also tried, no finding

* `build_arm` called twice on one service: both proxies count and the decision still comes from the inner selector (`q2`). Harmless nesting.
* `select_calls` and seam counters are reset at the top of every `run_case` (`arms.py:879-882`). The shipped `QueryAwareFill` is wrapped as well as the injected `FixedWindow` (`arms.py:864`; `q2` shows `full` counting).
* RR-01 at equal, above and below the baseline; RR-08 with an exactly-zero case; RR-09 with a raise inside `follow` (already caught).
* A reused trace root (`p5`); the per-arm watermark with traces attached; `_run` no longer carries the production watermark.
* RR-14/RR-15 left open: I agree with recording them rather than patching.

## 6. Proposed ledger rows (not entered)

| id | sev | line |
|---|---|---|
| N-1 | HIGH | F1-ordering gated on reranking a family the gate prohibits: H2 cannot HOLD, and F1 reorders are not falsifiers |
| N-2 | HIGH | `select_calls` counts consultations; F17 HOLDS on wire-identical arms (R-M2-098) |
| N-3 | HIGH | existence clauses HOLD on 1 case; H1 HOLDS with 1 F1 and 0 F2 |
| N-4 | HIGH | H1 recall clauses have no execution check; an unloaded backend gives H1 FALSIFIED |
| N-5 | MEDIUM | semantic_cost cross-check compares rerank presence only, is absent on F1/F2, and the detail claims otherwise |
| N-6 | MEDIUM | `factor_ran` accepts partial instrumentation |
| N-7 | MEDIUM | any_of missing from cut_loss, position_spread and report |
| N-8 | MEDIUM | `evaluate` keyed by hand; a changed or added pair reaches the table but not the verdict |
| N-9 | LOW | control readout ignores outcome |
| N-10 | LOW | deleted sink aborts the campaign; edited probe vs recorded hash |

Recheck after repair: N-1..N-8, each with a test that fails on this tree. N-1 and N-2 should be tested against the shipped gate and the shipped `plan_thread`, not against hand-built `CaseRun`s, because hand-built runs are how both got past 21 new tests.
