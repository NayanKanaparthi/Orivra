# Loop-0 preflight record

Run at 2026-09-11T08:40:01.938669+00:00. One section per probe. A verdict of `fail` is a **result**, not
an error: the consequence it forces is written in the probe and was written before
the run.

| Probe | Verdict | Validates |
|---|---|---|
| `PF-4-model-latency` | **pass** | AD D.5's semantic rung inside MAX_SEMANTIC_MS = 6000 ms at MAX_POOL_MESSAGES = 300 and MAX_RERANK_PAIRS = 25, and AD D.8's claim that the server process loads its models once rather than per query |

## PF-4-model-latency - Local model cost on this machine, cold load separated from warm work

**Verdict:** `pass`

- **Measures:** on this machine, CPU only: the wall clock of the FIRST backend acquire (cold load), the wall clock of a SECOND acquire in the same process (reuse), embed wall clock at pool sizes [100, 200, 300, 400] on synthetic rows of real pool-row length, rerank wall clock at [5, 10, 25] pairs, the device the weights were loaded onto and the accelerators present but unused, the runtime versions, and peak resident set size. Every timed size is warmed once and then run 5 times; the record carries the median and every sample
- **Validates:** AD D.5's semantic rung inside MAX_SEMANTIC_MS = 6000 ms at MAX_POOL_MESSAGES = 300 and MAX_RERANK_PAIRS = 25, and AD D.8's claim that the server process loads its models once rather than per query
- **Falsified when:** warm embed at MAX_POOL_MESSAGES plus warm rerank at MAX_RERANK_PAIRS exceeds MAX_SEMANTIC_MS; or the second acquire is not materially cheaper than the first, which means the process is reloading the model per use and every query pays the cold cost
- **Changes if it fails:** the per-query sum failing re-derives max_pool_messages downward to the largest measured size that fits inside MAX_SEMANTIC_MS, declared per T-RO1 in every semantic response, rather than MAX_SEMANTIC_MS being raised to whatever was measured. Reuse failing is an architecture defect in the registry, not a tuning result, and is fixed before any latency number from this run is quoted
- **Credential:** `read`; budget 0 u (published, uncalibrated)
- **Pre-registered decision rules:**
  - each stage is warmed with a discarded call before timing, and every size is run 5 times with the median recorded. A single ascending pass charges the first size for initialisation the rest inherit, which is how run 1 produced a rerank curve that fell as the work grew
  - the device is named by the loader, never left to the library's default, and is recorded in the finding. AD F PF-4 registers this measurement as CPU-only, and a library that quietly selects MPS would be measuring a different machine from the one the plan describes
  - a rerank or embed median curve that is not non-decreasing in size makes the verdict INCONCLUSIVE, not PASS: constants derived from a curve nobody can read are constants with no warrant
  - the per-query budget is WARM work only - embed(pool) + rerank(k). The cold load is paid once per process and is reported separately, never folded into a per-query figure
  - a re-derivation picks the largest measured k whose rerank fits 50% of MAX_SEMANTIC_MS, then the largest measured pool that fits the remainder. The split is arbitrary and is declared as arbitrary; the full curve is recorded so a reviewer can apply a different split without a re-run
  - if no measured k fits its share, the finding is that the cross-encoder does not fit this budget on this machine at any shortlist size measured, which is a D.7 design question and not a constant to lower quietly
  - reuse holds when the second acquire costs less than 5% of the first AND less than 1000 ms, so a uniformly slow machine cannot satisfy it by making both numbers large
  - the cold load is measured on the first acquire of a fresh process. The OS page cache is not controlled and cannot be from here, so a cold reading is an upper bound on warm-disk cost and a lower bound on first-ever-run cost, and is reported as such rather than as the cold cost
  - max_model_rss_mb is REPORTED as a measured peak plus a stated margin. It is a candidate bound, not adopted by this probe; adoption is the owner's after seeing the figure, the same treatment PF-21 gave max_server_ms
  - this probe says nothing about retrieval quality. Synthetic text of the right length is a sound instrument for latency and an unsound one for relevance; H1/H2/H3 measure quality on F1-F17
  - a two-item smoke check is not a measurement and none of its numbers appear here

```json
{
  "accelerators_available_but_unused": [
    "mps"
  ],
  "candidate_is_a_bound_not_a_default": true,
  "candidate_max_model_rss_mb": 1700,
  "candidate_max_pool_messages": 400,
  "candidate_max_rerank_pairs": 25,
  "cold_acquire_ms": 5410,
  "device": "cpu",
  "embed_curve_is_non_decreasing": true,
  "embed_ms_by_pool_size": {
    "100": 15,
    "200": 15,
    "300": 24,
    "400": 30
  },
  "embed_samples_by_pool_size": {
    "100": [
      15,
      14,
      55,
      18,
      9
    ],
    "200": [
      15,
      18,
      15,
      16,
      15
    ],
    "300": [
      27,
      25,
      24,
      22,
      22
    ],
    "400": [
      31,
      30,
      30,
      30,
      30
    ]
  },
  "embedding_dimension": 512,
  "max_pool_messages": 300,
  "max_rerank_pairs": 25,
  "max_semantic_ms": 6000,
  "model_id": "minishlab/potion-retrieval-32M+BAAI/bge-reranker-base",
  "model_revision": "6fc8051fab2a+2cfc18c9415c",
  "peak_rss_mb": 1360,
  "pool_text_branch": "snippet",
  "published_max_pool_messages": 300,
  "published_max_semantic_ms": 6000,
  "repeats_per_size": 5,
  "rerank_budget_share": 0.5,
  "rerank_curve_is_non_decreasing": true,
  "rerank_ms": 226,
  "rerank_ms_by_pairs": {
    "10": 101,
    "25": 226,
    "5": 59
  },
  "rerank_pairs": 25,
  "rerank_samples_by_pairs": {
    "10": [
      103,
      101,
      99,
      98,
      102
    ],
    "25": [
      225,
      233,
      226,
      225,
      226
    ],
    "5": [
      61,
      60,
      59,
      59,
      59
    ]
  },
  "reuse_holds": true,
  "runtime_versions": {
    "sentence_transformers": "5.7.0",
    "torch": "2.14.0",
    "transformers": "5.17.0"
  },
  "single_call_embed_ms": 0,
  "warm_acquire_ms": 0,
  "warm_per_query_ms_at_published_pool": 250
}
```

> cold_acquire_ms is paid once per process and is NOT part of the per-query figure; warm_acquire_ms is the second acquire in the same process and is what makes that separation legitimate.
> the OS page cache is not controlled here, so cold_acquire_ms is an upper bound on warm-disk cost and a lower bound on a first-ever run.
> single_call_embed_ms is ONE call carrying ONE row: call overhead plus a row, not the marginal cost of a row. Multiplying it by a pool size is a category error; the pool curve is what prices a pool.
> these are latency numbers on synthetic rows of real length. They say nothing about retrieval quality, which H1/H2/H3 measure on F1-F17.
> the published bounds hold on this machine and are recorded as measured. max_model_rss_mb is a candidate only; adoption is the owner's.
