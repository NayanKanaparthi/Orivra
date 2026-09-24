# The R1-R4 integration repair (2026-09-15): what changed, what was checked, what it shows

The owner authorised, from the causal diagnosis of the backend-on regression
(`docs/reviews/DIAG_SEMANTIC_REGRESSION_2026-09-15.md`, R-M2-093 to R-M2-098), one scoped
integration repair in four parts, with corpus-independent regressions for the causal
mechanisms, one focused independent review, the unchanged diagnostic rerun in both driver
modes under new filenames, and paired gains and losses. This is that record. Contract text:
`docs/ARCHITECTURE_AMENDMENTS.md` A15. Ledger: R-M2-093 to R-M2-097 REPAIRED, R-M2-099 added.

Kept unchanged, as required: the two models and `models.lock`; every default budget
(`MAX_HIT_THREADS`, the pool's 25 / 300 / k=25, `MAX_SERVER_MS`, both token ceilings, the host
cap, the driver's `MAX_RECOVERY_ROUNDS = 4` and `TOTAL_CALLS = 33`); the corpus (generator 3,
seed 4311) and the thirteen answerable cases; the acceptance criteria of M2. No mailbox was
contacted. Every earlier record under `benchmarks/` is untouched; every run here wrote to a
new name. `marketing/` was not edited; the working tree's unrelated changes are preserved.

## 0. The model-dependent uncertainty, and why the model-independent work went ahead

The diagnosis named one residual only a real-backend trace could settle: the per-thread
distribution of the real shortlist's 25 hits, and the walk order of the pool's unselected
threads under the real model (§4, §8 there). The smallest targeted trace is
`benchmarks/trace-first-response-4311.py` (first searches of the seven lost or moved cases on
`full` and `sem-off`, with spies on the ladder and the semantic runner; verified with
`--stand-in`). This environment cannot load the installed models (no torch; the models
directory is not mounted), so that trace is the one command handed back in §7, and the repair
proceeded on the model-independent structure the diagnosis established - which the stand-in
reproduces on every outcome the real records state (§4.1 below: 5/13 and 4/13 on `full`,
11/13 and 9/13 on `sem-off`, the same cases).

## 1. What changed

**R1 - one arrangement for sizing and wire** (`envelope/grouping.py`; `disclosure/layout.py`
`Layout.groups`, `foldable_caps`, `ranks`, `CostTerms`; `retrieval/assemble.py`
`_undisclosed_caps`, `TAIL_RECOVERY_CAPS`; `envelope/disposition.py` `_write_down`). The layout
carries the `(thread, cap)` keys it will file and the caps whose groups may fold; one
function, `arrange_groups`, decides for the estimate and for the ledger which groups are
named, which fold, and in what order - by the same ranks. A thread is under one cap; a mapped
thread is never grouped; the pool's caps name only what nothing else accounts for. The
round-27 estimate matrix runs with a backend registered. The two counts the layout used to
carry (`grouped_threads`, `foldable_grouped_threads`) are gone. `layout_chars` and
`layout_tokens` are now the totals of `CostTerms`, so a refusal reports the terms it fitted.

**R2 - the last resort collapses before it empties** (`disclosure/ladder.py`
`_last_source_to_runs`, `_collapse_whole`, `_split_a_source_whose_floor_does_not_fit`;
`step_8_withheld_record`). When the only evidence-bearing source of a search does not fit,
its rows - protected top-k and floor included - go to stub depth and collapse into declared
runs; only if that still does not fit is it split and the response refused as empty. Step 8
keeps the last matched message present (the review's F2: it used to withhold a last source's
non-floor hits one record at a time and hand the emptiness gate a response the collapse would
have served). Declared as step 7's `message(s) collapsed into declared runs` and
`row(s) reduced in depth`, `truncated_by: mailweave`, `partial: true`; the run's map call and
the recommended `mailweave_get_messages` read (now naming collapsed hits, bounded by
`RECOMMENDED_EXPANSION_LIMIT`) are the executable ways back; run membership is not content
(EP §6.1, unchanged in the harness). Never on an expansion (`evidence_is_the_map`); never a
`Band.REQUESTED` row. A thread too large even as a run still refuses.

**R3 - the refusal says what it was made of, and the retry reduces that**
(`disclosure/ladder.py` `RefusalKind`, `RefusalCause`, `refusal_cause`, `_initial_at_width`,
`run_ladder(explain=)`, `Layout.last_evidence_source`, `PlannedSource.mapped_at`;
`surface/recovery.py` `NarrowingKind`, `widest_width_that_fits`, `narrower_call(cause=)`,
`SEARCH_CHAIN_STEPS`, `MAX_RECOVERY_STEPS`; `surface/server.py`, `surface/partition.py`
`cause`). The decline carries `cause`: kind (`size`/`empty`), the binding unit and cap, the
refused layout's cost by term, the named groups by cap, the width in effect, the top thread,
the last source's smallest inventory, and `fits_at`/`refused_at` - the ladder itself run at
every narrower `max_hit_threads` over the same retrieval, demoting by the producer's cut
order (the review's F1). The retry is the widest width that fits (`narrowing.kind:
narrower`, every other argument carried), or - when no width fits - the map hop declared
`scope_change`, with the threads it does not account for named in the remediation. Without a
cause the halving schedule is unchanged. `MAX_RECOVERY_STEPS` is 12 (7 before), derived: one
strict width reduction per hop from 12 to 1, then the tool change; held tight by
`test_following_the_pure_schedule_from_the_top_ends_within_the_bound` on both schedules.
Narrowing the pool is not offered: a smaller pool reads fewer candidates and groups more.

**R4 - retrieval's rank on the offers, and a walk that follows it** (`envelope/wire.py`
`WithheldGroup.rank`, `NotIncludedSource.rank`; `envelope/disposition.py` `note_rank`;
`retrieval/assemble.py` `rank_of`, `_record_ladder_dispositions`; harness
`arms.in_retrieval_order`, `_recovery_calls`, `boundary.Served.offers`). Both entry kinds
carry the retrieval's own order for the threads that had one; the wire writes ranked entries
in that order, unranked after by thread id and cap; the driver walks both blocks as one
sequence by rank, the unranked after in the order listed. Known-target offers come first and
separately. Nothing reads an expected evidence id, a corpus position or a case label.

`schema_version` stays 2; the new fields are optional and additive (`rank` twice, `cause`,
`narrowing.kind`). `tests/test_field_census.py` counts 306 (+3, stated there).

## 2. Regressions and gates

`tests/test_integration_repair_2026_09_15.py` - 67 tests, corpus-independent, on generated
mailboxes (the round-27 matrix, wide-pool shapes with overlapping overflow/pool sets, a
thirty-thread last-source shape, a broad-query shape that declines at the published width,
an inventory-too-large shape, the review's two shapes). They hold: the arrangement's
properties; estimate ≥ render with and without a backend and groups/tails charged = written;
pool-only threads under pool caps, overflow under the width cap; the last source served as
run members with the depth reduction declared and the recovery executable, membership
surfaced but not content, explicit reads and requested rows untouched, and - with the collapse
switched off - the same shape emptying the answer (the branch is the one exercised); the
cause's terms and table, **the table against the real call at every width it names**, the
widest-fitting retry with every other argument carried, the declared scope change when no
width fits, one directed hop where the halving needed more at the same budgets; the wire's
ranks and their order, unranked pool groups after, the driver's merged walk on a hand-made
wire with the known-target offers first; the review's F1 (cut order, not rank), F2 (step 8
keeps the last hit; the collapse is reached), F4 (the estimate arranges by the ledger's ranks).

Re-shaped, not weakened, with the reason in each: `test_r_mcp_033_round29.py`
(`test_no_compression_lets_an_empty_answer_be_served_as_success` now uses a thread too large
even as a run, nine hundred messages; the old three-hundred-message shape is kept as the
positive case it has become), `test_round27.py` and `test_round28.py` (the same fixture),
`test_recovery_chain_round29.py` (the bound's new derivation, both schedules held tight),
`test_r_m2_078_recovery_driver.py` (the first response now recommends a read of collapsed
hits, so the hop-2 assertion counts reads), `test_r_mcp_039_round29.py` (`narrowing.kind`),
`tests/fixtures/replants.py` (R97, R124 re-anchored; R232's second citation removed because
that test no longer discriminates - verified both ways by the reviewer).

Gates, this tree: the full suite, 102 files, 0 failures (`-m "not network and not
replant"`); `mypy --strict server/src harness/src`: clean (176 files); `ruff check
server/src`: clean; replants on every touched file: 67 run, all CAUGHT (R232 after its
citation change), and the 46 on the four files the review's fixes touched run again after
them, all CAUGHT; `test_replants.py::test_every_replant_anchor_matches_exactly_once_in_the_tree`
passes.

## 3. The independent review

One focused review of the uncommitted change against the owner's rubric, by an agent with
the code, the tests and a shell but no authority to change anything. Verdicts before repair:
R1 MET, R2 MET WITH FINDINGS, R3 NOT MET, R4 MET. Findings and their disposition:

* **F1 (BLOCKER)** - `fits_at` demoted sources by the ranking's `rank`, but `max_hit_threads`
  cuts the producer's pre-ranking order, so the table disagreed with the real call whenever the
  ranking reordered (a many-hit thread with a late id), in both directions, including terminal
  map hops where five narrower widths served. **Repaired**: `PlannedSource.mapped_at` carries
  the cut order; the hypothetical demotes by it and removes the demoted threads' hits and floor
  obligations as the producer would. Held by
  `test_the_table_follows_the_producers_cut_order_not_the_rankings_order` and
  `test_a_source_outside_the_cut_is_never_demoted_and_a_layout_without_a_cut_has_no_table`.
* **F2 (HIGH)** - step 8 could withhold the last source's non-floor hits one by one and reach
  the emptiness gate before the collapse was tried. **Repaired**: step 8 keeps the last matched
  message present. Held by
  `test_step_8_never_withholds_the_last_matched_message_and_the_collapse_is_reached` and
  `test_step_8_alone_keeps_one_hit_present_on_the_layout`.
* **F3 (MEDIUM)** - this record did not yet exist. **This file.**
* **F4 (LOW, latent)** - the estimate arranged groups without the ledger's ranks; with two
  foldable caps the tail count could differ. **Repaired**: `Layout.ranks`, passed by the
  producer, used by `named_groups`/`tail_entries`. Held by
  `test_the_estimate_arranges_the_groups_by_the_rank_the_ledger_writes_them_by`.
* **F5 (LOW)** - step 7's detail counted a run delta and could read "-5 collapsed run(s)".
  **Repaired**: counted in members, with the run re-cut stated.
* **F6 (INFO)** - a narrower width can drop the ranking's top thread, because the cut is the
  producer's order. Pre-existing producer semantics; **recorded** as R-M2-099, not changed.

The reviewer's own fuzz (900 random mailboxes; 3,000 random sources through the collapse)
found no estimate under render, no over-cap serve, no membership lost, no `certify` failure;
its measured decline latency with the table was 105 ms median against 27 ms without, inside
`MAX_SERVER_MS`.

## 4. Results, paired

Every number below is **[word]**: the unchanged diagnostic run with the deterministic
bag-of-words stand-in (`tests.fixtures.eval_dummy._WordBackend`) in place of the models, via
`benchmarks/_patches/run-diagnostic-wordbackend.py` (the runner's own `main()` with
`preflight` replaced; the same cases, driver, budgets and report), before (`git archive`
of `d4ab767`, exported outside the tree) and after, both driver modes. Records:
`benchmarks/diagnostic-run-boundary-wordbackend-{d4ab767,repair}-{named,listed}-4311.{txt,json}`.
The stand-in decides everything the real models decide *except* which 25 pool rows the
shortlist selects and their order; §4.1 says how far that carries.

### 4.1 The stand-in against the real records, before the repair

| | real, commit 07b9f9c (listed / named) | stand-in at d4ab767 (listed / named) |
|---|---|---|
| `full` delivered | 4/13 / 5/13 | 4/13 / 5/13 |
| `sem-off` delivered | 9/13 / 11/13 | 9/13 / 11/13 |
| `full` declines per run | 32 | 32 |
| `sem-off` declines per run | 9 | 9 |

The same totals, the same declines, and the same per-case outcomes on `full` (the five lost
cases plus EXP-02 in named mode). This is agreement on outcomes, not on the shortlist's
membership; the model-dependent residual of §0 stands.

### 4.2 The diagnostic, before → after, both modes

Delivered of 13 answerable; declines summed over the run; calls summed over the run.

| arm | mode | delivered | declines | calls | gains | losses |
|---|---|---|---|---|---|---|
| `full` | named | 5 → **11** | 32 → 7 | 180 → 308 | SEM-01, RANK-02, RANK-03, EXP-02, EXP-03, REV-03 | none |
| `full` | listed | 4 → **9** | 32 → 7 | 181 → 323 | SEM-01, RANK-02, RANK-03, EXP-03, REV-03 | none |
| `sem-off` | named | 11 → 11 | 9 → 4 | 258 → 279 | none | none |
| `sem-off` | listed | 9 → 9 | 9 → 4 | 277 → 299 | none | none |
| `fixed-window` | both | as `full` | as `full` | as `full` | as `full` | none |
| `sem-off+fixed-window` | both | as `sem-off` | as `sem-off` | as `sem-off` | as `sem-off` | none |

The `fixed-window` arms remain call-for-call identical to their twins (R-M2-098: the fill
never reaches the wire on this corpus; unchanged, and no claim about query-aware selection
follows from any of this).

Per case on `full`, named mode (delivered; calls; declines; why the driver stopped):

| case | before | after |
|---|---|---|
| SEM-01 | no; 33; 0; call_budget | **yes**; 28; 0; evidence_in_hand |
| SEM-02 | yes; 19; 0 | yes; 19; 0 |
| SEM-03 | yes; 5; 3 (served at width 1) | yes; 3; 0 (served first) |
| RANK-01 | yes; 30; 2 | yes; 30; 2 (first declines; retry at 9 serves) |
| RANK-02 | no; 24; 3; hop_budget | **yes**; 22; 0 |
| RANK-03 | no; 5; 4; hop_budget | **yes**; 27; 0 |
| RANK-04 | yes; 29; 2 | yes; 29; 2 (first declines; retry at 6 serves) |
| EXP-01 | yes; 12; 0 | yes; 12; 0 |
| EXP-02 | no; 5; 4; hop_budget | **yes**; 29; 1 (first declines; retry at 11 serves) |
| EXP-03 | no; 5; 4; hop_budget | **yes**; 25; 0 |
| REV-01 | no; 5; 4; hop_budget | no; 27; 0; no_new_affordances (never offered, R-M2-084) |
| REV-02 | no; 5; 4; hop_budget | no; 28; 2; no_new_affordances (never offered, R-M2-084) |
| REV-03 | no; 3; 2; no_new_affordances | **yes**; 29; 0 |

Listed mode differs on EXP-01 and EXP-02 only (both undelivered on both arms in listed
mode, before and after: the evidence is a listed id, which that mode does not read).

**Costs, stated.** Calls per run on `full` rose from 180 to 308 (named) and 181 to 323
(listed): a served first response is walked, a refused one was not. SEM-03 in listed mode
went from 5 calls to 13 for the same delivery (it used to be served at width 1 after three
declines, with a smaller walk). On `sem-off` the calls rose 258 → 279 and 277 → 299 for the
same deliveries: EXP-02 and REV-02's first responses are now served and walked (REV-02 to
`no_new_affordances`, its evidence never offered). Budgets are unchanged; every run stayed
inside `TOTAL_CALLS = 33` per case.

### 4.3 The first response, before → after (word backend, `benchmarks/_patches/first-response-anatomy.py`)

Records `benchmarks/first-response-anatomy-wordbackend-{d4ab767,repair}.json`. "offer *i* of
*n*": the evidence thread's position in the driver's discovery walk.

| case | evidence | `sem-off` before → after | `full` before → after |
|---|---|---|---|
| SEM-01 | t-t0011 | served; offer 10 of 35 → offer 2 of 35 | served; offer 9 of 41 → offer 3 of 35 |
| SEM-02 | t-t0031 | served; offer 11 of 22 → offer 1 of 22 | served; offer 11 of 27 → offer 1 of 27 |
| SEM-03 | t-t0004 | served; source → source | declined (0 present) → served; source |
| RANK-01 | t-t0047 | declined → declined | declined → declined |
| RANK-02 | t-t0036 | served; offer 2 of 24 → offer 9 of 24 | declined → served; offer 10 of 30 |
| RANK-03 | t-t0048 | served; offer 25 of 29 → offer 25 of 29 | declined → served; offer 23 of 31 |
| RANK-04 | t-t0035 | declined → declined | declined → declined |
| EXP-01 | t-t0010 | served; source → source | served; offer 3 of 10 → offer 1 of 10 |
| EXP-02 | t-t0009 | declined → served; offer 5 of 31 | declined → declined (retry at 11 serves) |
| EXP-03 | t-t0046 | served; offer 29 of 31 → offer 29 of 31 | declined → served; offer 29 of 33 |
| REV-01 | t-t0049 | served; not offered → not offered | declined → served; not offered |
| REV-02 | t-t0050 | declined → served; not offered | declined → declined (retry at 7 serves) |
| REV-03 | t-t0013 | served; offer 23 of 35 → offer 23 of 35 | refused on render → served; offer 23 of 35 |

Offer positions moved both ways: SEM-01 and SEM-02 forward (the rank order), RANK-02 on
`sem-off` from 2 to 9 (its evidence thread was second in the not-included block, which used
to be walked as a block; it is ninth by rank). Delivery and call count on RANK-02 `sem-off`
are unchanged (18 calls) because the walk completes within the budget either way; the
position matters where it does not - SEM-01 on `full`, which used to run out of calls.

### 4.4 The `sem-off` reruns (no backend), the owner's standing comparison

`benchmarks/rerun-boundary-4311.py --tag semoff-repair-listed --no-named-reads` and
`--tag semoff-repair`, against `semoff-cont-listed` / `semoff-cont` (07b9f9c): delivered
9 → 9 (listed) and 11 → 11 (named); no gains, no losses; declines 9 → 4 in both. EXP-02's
first response is now served (one decline fewer); REV-02's chain (5 calls, 4 declines,
`hop_budget`) became a served first response walked to `no_new_affordances` (27 calls, 0
declines) with the evidence still never offered.

## 5. What this does and does not show

* Backend-on, on this corpus and with the stand-in, delivers no fewer cases than backend-off,
  in both modes, with no case lost on any arm. That is a **diagnostic check on these thirteen
  cases**, not a universal guarantee and not formal acceptance: the acceptance criteria of M2
  are unchanged and unmet by anything here.
* Nothing here is a claim about the models' quality, about a reranking benefit, or about a
  query-aware selection benefit. The reranker still admits no ids and moves no lexical thread;
  the selector's fill still never reaches the wire on this corpus (R-M2-098).
* The real-model result is unknown until §7 runs. The stand-in reproduced the real records'
  outcomes before the repair; whether the real shortlist's hit distribution or the real
  unselected-thread order changes any of the after-numbers is exactly the model-dependent
  residual the trace command exists to measure.
* **R-M2-076 stays open and is made explicit here.** RANK-01 and RANK-04 - the broadest
  first responses (26 hits with 12 sources split off and 792 messages accounted; 59 hits, 9
  split off, 667 accounted) - still decline at the published width on every arm, before and
  after; so do EXP-02 and REV-02 on `full`. What changed is the chain: one directed hop to a
  served response at the widest width that fits (RANK-01 at 9, RANK-04 at 6, EXP-02 at 11,
  REV-02 at 7), instead of three narrowings and a map. The first response's bookkeeping
  overflow on broad searches is the same design question it was.
* R-M2-084 (REV-01, REV-02: the evidence thread never offered) is untouched and still costs
  both cases on every arm.
* A thread whose inventory alone exceeds the cap still declines on its map (A14's limit); the
  chain reaches it in one hop now and says it is a change of scope.
* `MAX_RECOVERY_STEPS` rose from 7 to 12. In practice a directed chain is one hop; the bound
  is what holds if the ladder's answer at a narrower width were ever wrong. It is the server's
  promise about chain length, not a harness budget; the harness's rounds and calls are unchanged.
* M3 is not begun.

## 6. Files

New: `server/src/mailweave/envelope/grouping.py`, `tests/test_integration_repair_2026_09_15.py`,
this record, A15 in `docs/ARCHITECTURE_AMENDMENTS.md`. Changed: `disclosure/{ladder,layout,plan}.py`,
`envelope/{disposition,wire}.py`, `retrieval/assemble.py`, `surface/{expansion,partition,recovery,server}.py`,
harness `evaluation/{arms,boundary}.py`, the tests named in §2, `docs/V0_1_DEMO.md` (the bound),
`docs/reviews/FINDINGS_LEDGER.md`. Scratch (gitignored, kept): `benchmarks/_patches/run-diagnostic-wordbackend.py`,
`benchmarks/_patches/first-response-anatomy.py` (output name now an environment variable), the
records named above. `benchmarks/trace-first-response-4311.py` was updated against this
commit's `Layout` (it read `grouped_threads`, which R1 removed, and crashed at the first
snapshot when the models were loaded): it now records the total group keys, the named groups
and the folded tails separately from one call of the shared arrangement with the ledger's own
ranks; it names the depth census `rows_above_stub` and records A.9a step 3's real protection
set beside it from the product's own `_top_k_hit_ids`; it counts R3's hypothetical ladder runs
without filing their steps as the response's; it records the decline's `cause`, the groups'
and entries' `rank`, and the driver's walk order through the harness's own rule; and it refuses
to overwrite an existing record, suffixes a `--stand-in` run's record with `-standin`, and
stamps the git revision actually executed beside the `--tag`. Verified end to end with
`--stand-in` against this commit (13 served and 1 declined of the 14 case/arm pairs, record at
`benchmarks/trace-first-response-7224b86-standin.json`), including a check that the same
fourteen searches return identical wire results with the instrumentation installed and without
it. No product code was changed for it.

## 7. The laptop commands (real models; this environment cannot load them)

From the repository root on the Mac, with the provisioned models and the project `.venv`.
Each writes only to a new name. First the targeted trace the diagnosis asked for, after this
commit (`<commit>` is its short hash):

```
cd /Users/nayankanaparthi/Desktop/Nayan/MailWeave && \
PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:. \
  .venv/bin/python benchmarks/trace-first-response-4311.py \
  --models-root ~/.local/share/mailweave/models --device cpu --tag <commit>
```

The trace refuses to overwrite an existing record, so `<commit>` must be a tag no record
carries yet; a `--stand-in` rehearsal writes `…-standin.json` and cannot be mistaken for it.

Then the unchanged diagnostic, both modes:

```
cd /Users/nayankanaparthi/Desktop/Nayan/MailWeave && \
PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:. \
  .venv/bin/python benchmarks/run-diagnostic-4311.py \
  --models-root ~/.local/share/mailweave/models --device cpu \
  --out benchmarks/diagnostic-run-boundary-repair-listed-<commit>.txt \
  --json benchmarks/diagnostic-run-boundary-repair-listed-<commit>.json \
  --no-named-reads && \
PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:. \
  .venv/bin/python benchmarks/run-diagnostic-4311.py \
  --models-root ~/.local/share/mailweave/models --device cpu \
  --out benchmarks/diagnostic-run-boundary-repair-named-<commit>.txt \
  --json benchmarks/diagnostic-run-boundary-repair-named-<commit>.json
```

Compare against `benchmarks/diagnostic-run-boundary-cont-{listed,named}-07b9f9c.{txt,json}`
(the pre-repair real-model records) case by case, gains and losses both; the claim to test
is "backend-on delivers no fewer cases than backend-off on these cases", nothing wider.

---

## 8. The real-model runs (2026-09-15, commit `ba99c7a`)

The three commands of §7 ran on the owner's Mac against the provisioned models
(`minishlab/potion-retrieval-32M` + `BAAI/bge-reranker-base`, revisions `6fc8051fab2a` /
`2cfc18c9415c`, CPU, torch 2.14.0). Records, preserved and checksummed:

| record | sha256 (first 16) |
|---|---|
| `benchmarks/diagnostic-run-boundary-cont-listed-07b9f9c.json` (before) | `aefedee3e8734702` |
| `benchmarks/diagnostic-run-boundary-cont-named-07b9f9c.json` (before) | `3338aa3b4a3e2a3e` |
| `benchmarks/diagnostic-run-boundary-repair-listed-ba99c7a.json` (after) | `60f6c4404b3fbc3f` |
| `benchmarks/diagnostic-run-boundary-repair-named-ba99c7a.json` (after) | `e3a217aa1658a04c` |
| `benchmarks/trace-first-response-ba99c7a.json` (real backend) | `c003fe0f82952ac8` |
| `benchmarks/trace-first-response-ba99c7a-standin.json` (stand-in) | `7e9facc84773e5e8` |

The two pre-repair records are the ones the diagnosis was written from; they are unchanged.

### 8.1 The paired outcome [real]

| arm | mode | delivered | declines | calls (mean) | gains | losses |
|---|---|---|---|---|---|---|
| `full` | listed | 4 → **9** /13 | 32 → 7 | 13.9 → **24.8** | SEM-01, RANK-02, RANK-03, EXP-03, REV-03 | none |
| `full` | named | 5 → **11** /13 | 32 → 7 | 13.8 → **23.7** | the five above plus EXP-02 | none |
| `sem-off` | listed | 9 → 9 | 9 → 4 | 21.3 → 23.0 | none | none |
| `sem-off` | named | 11 → 11 | 9 → 4 | 19.8 → 21.5 | none | none |

The `fixed-window` arms are call-for-call identical to their semantic-state twins, before and
after, as they were on the stand-in (R-M2-098: the fill never reaches the wire on this corpus).

**The word-backend run predicted this exactly.** Every figure in §4.2 of this report, taken
from the bag-of-words stand-in, is reproduced by the real models: the same four arm totals
before and after, the same declines, the same summed calls (180→308, 181→323, 258→279,
277→299), and the same thirteen per-case outcomes on `full` in both modes, down to the call
count and the driver's stopping reason on each. Nothing in the paired table needed the models
to be known.

### 8.2 The cost, recorded beside the gains

Backend-on now costs **more per case than backend-off for the same delivery**: 24.8 against
23.0 calls in listed mode and 23.7 against 21.5 in named mode, with 7 declines against 4 and
4 recoveries against 2, while both arms deliver 9/13 and 11/13. The repair did not make the
semantic arm cheaper than the lexical one; it made it stop losing cases, and it raised its
call cost by about 78% (13.9 → 24.8) and 72% (13.8 → 23.7) in the process.

That rise is the mechanism the diagnosis named, working in the direction it predicted: a
refused first response offers one call and a served one offers twenty to forty, so the cases
that used to decline out at the hop budget now walk. Where the calls went, on `full`:

| mode | total | on newly delivered cases | on cases already delivered | on cases still undelivered |
|---|---|---|---|---|
| listed | +142 | +65 (5 cases) | +8 (SEM-03) | **+69** (EXP-02, REV-01, REV-02) |
| named | +128 | +85 (6 cases) | −2 | **+45** (REV-01, REV-02) |

So roughly half the added calls in listed mode, and a third in named mode, buy nothing:
REV-01 and REV-02 go from declining at 5 calls to walking 27 and 28 and still not reaching
their evidence, which is R-M2-084 and not this repair. What changed for them is the *kind* of
failure: `hop_budget` became `no_new_affordances`, so the failure is now attributable to the
offers rather than masked by a depth limit. Every run stayed inside `TOTAL_CALLS = 33`.

### 8.3 Reconciling the trace with the diagnosis

The trace (`trace-first-response-ba99c7a.json`, seven cases × two arms) settles the residual
§4 and §8 of the diagnosis named. Read against the stand-in trace of the same commit:

**Confirmed as observations, having been asserted or inferred before.**

* *The pool is model-independent.* On all seven cases the real and stand-in runs read the same
  pool: identical `seed_threads`, `candidates`, `threads_read` and `messages_embedded` (300 on
  every case). `plan_pool` is pure in the parse and the ladder's touches, as claimed.
* *The hit set's size is fixed by rule.* `|hit_ids|` is identical between backends on every
  case (132, 121, 22, 72, 125, 114, 74). The shortlist selects exactly 25 either way.
* *The reranker admits nothing.* `hit_count_per_rung` shows `L6: 0` on every served response,
  both backends, as the diagnosis said; nothing in these records implicates it.
* *The regression was structural.* The shortlist's membership differs substantially between the
  real model and a bag of words (SEM-01: five threads against two; EXP-03: 20 of 25 in
  `t-t0008` where the stand-in put 17 in `t-t0006`; RANK-03: 24 in `t-t0048` where the stand-in
  put none), and **every disclosure outcome is identical**: the same served/declined verdict,
  the same group keys, named groups and folded tails, the same final sources and character
  counts. Embedding quality is not implicated, now by measurement rather than by argument.

**Corrected.** The diagnosis attributed limb (i) - hit concentration in the top-ranked source -
to D.5 step (a) seeding putting the *shortlist's 25* into already-hit-bearing threads. The
trace shows that is not the mechanism. `SemanticRunner._build_pool` sends its probes as
`list_messages(..., rung=RungId.L5, ...)`, so **every id a pool probe returns enters `H` as an
L5 hit**, whatever the shortlist later thinks of it: `hit_count_per_rung` reports L5 at 334 to
462 ids on these cases against a shortlist of 25. Those ids are hits, hence E2 floor members,
and they land in the mapped lexical sources: the rank-0 source's present hits go 4 → 57 on
RANK-03, 5 → 56 on SEM-03, 2 → 13 on REV-03 and 3 → 8 on EXP-03 when the backend is on. The
shortlist's own choice touches only which pool-only threads survive as `unselected` groups.
This is why a bag of words predicted the models exactly, and it means the semantic rung's cost
to the first response is set by `plan_pool`'s probe set, which no model changes. R-M2-101.

> **Qualified 2026-09-16 — R-M2-110. The record above is preserved unchanged; this is what it
> now means.** Every figure in this project that counts what D.5 step (c)'s probe admitted was
> produced through `SyntheticMailbox`, whose `_date_value` matched `YYYY/MM/DD` only. The
> server writes that probe as `after:<epoch>` (A.6a rule 4), the double returned "cannot judge"
> for it, and "cannot judge" is implemented as **matching every message**. So the probe had no
> window in any run recorded here — **including the real-model runs**: the models decide which
> pool rows the shortlist selects and in what order, not whether the double filters by date.
> Real models did not make the synthetic date filtering correct.
>
> What survives: the **mechanism**. A pool probe's `messages.list` admits its whole result set
> to `H` at L5, and A.9 then spends the evidence tier and the E2 floor on it. That is a reading
> of the code and the contract and is unaffected.
>
> What does not survive: the **magnitude**. "334 to 462 ids" is a windowless probe's result set,
> not the probe the server sends to Gmail. Re-measured under the corrected double, the same
> mechanism leaves three demoted ids inside mapped threads on DIAG-SEM-03, not hundreds
> (`docs/reviews/A16_RECENCY_POOL_2026-09-15.md` §5.2, ledger R-M2-112). The size of this
> finding is unestablished until it is re-measured, and no work should be justified by the
> old number.

**New, and only visible under the real model.** On RANK-03 the embedding worked: the five
highest cosines in the pool are all in the evidence thread `t-t0048` (0.419, 0.418, 0.384,
0.376, 0.375) and 24 of the 25 shortlisted messages are in it. The response mapped `t-t0004`
and wrote `t-t0048` as a `max_hit_threads` group at rank 13, one place past the width cap;
`sem-off`, which scored nothing, wrote the same thread as a group at rank 14. The semantic
score moved the evidence thread by one position in the offer order and did not change whether
it was mapped, because `max_hit_threads` cuts `plans` in the pre-ranking order and the D.7
ranking reorders only what survived that cut. Both arms then delivered the case by walking.
**On this corpus the semantic rung has no path by which a correct retrieval becomes a better
response.** R-M2-102.

**Still not established, and not claimed.** Nothing here says the models are good, that
reranking helps, or that query-aware selection helps. The one case where the embedding clearly
identified the right thread delivered identically without it. A second interaction is recorded
and not pursued: L1b returns fewer ids with the backend on (815 → 541 on RANK-03, 811 → 393 on
REV-03, 645 → 289 on SEM-03), because the pool's HTTP spend comes out of the same budget.

### 8.4 What this closes

The backend-on delivery regression is **closed within the demonstrated diagnostic scope**:
thirteen answerable cases, one synthetic corpus at one seed, known-target reachability, both
driver modes, real models. Backend-on delivers no fewer cases than backend-off in either mode
and loses none, and its 32 declines per run are 7. That is a diagnostic check on these cases.
It is not M2 acceptance, which has not run, and it is not a claim that the semantic rung earns
its cost; §8.2 and §8.3 say the opposite of the second. R-M2-100.
