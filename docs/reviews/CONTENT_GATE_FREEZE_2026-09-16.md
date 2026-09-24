# The content gate, frozen before the repair

**2026-09-16, recorded before a single line of the generator was edited.** This is the
pre-registration. Everything it fixes was fixed while the corpus was still the one the fifth
independent read said NO to.

## What is frozen

| | |
|---|---|
| Gate | `tools/gate/content_gate.py`, `gate-1`, sha256 `3e08991c78eb5182…` |
| Solver | `mailweave_harness.evaluation.queryfree`, `qf-1`, sha256 `afc77fcb5a0f3eb7…` |
| Population | **every `ThreadTruth` in the manifest with a non-empty `family` and a non-empty `answer`**, at generator 3 / seed 4311 / profile `sample`. Not the diagnostic cases, not a sample |
| Scoring | **1 if the position of the message the solver picks is in that thread's `evidence_positions`, else 0.** No partial credit, no ranking credit |
| Denominators | per family, published in every record: F1 2, F3 7, F4 2, F5 2, F6 2, F7 4, F8 2, F11 2, F12 2, F13 2, F14 2, F15 8, F16 2, F17 2 — **41 threads** |
| C1 | every `(length, participants, senders, distinct hours)` maps to ≥ 2 families |
| C2 | the solver scores **below 100%** on every family with at least one scored thread |
| C3 | the solver scores **≤ 40%** over the population |
| C4 | the independent content read returns YES — a human judgement, not computed |

## Three things the gate states about itself

**The solver is handed the correct conversation.** `select_within_thread` receives the thread
the declared evidence is in and answers within it. The retrieval half is done for it. Its score
is an **upper bound on register leakage given perfect retrieval**, not a lower bound on any
system's difficulty.

**40% is a provisional engineering threshold for this repair. It is not a statistically
established validity threshold.** No power analysis stands behind it. Passing it is not evidence
that the corpus is free of shortcuts; it means this solver, on this population, under this
scoring rule, came in below a line drawn before the work started.

**Three numbers, three populations, never differenced.** The fifth read's **24 of 39** was its
own population and its own rule. The diagnostic runner's **6 of 13** is `qf-1` over the thirteen
authored diagnostic cases. This gate's baseline is **18 of 41** over the corpus threads above.
None of the three is comparable with either of the others, and no difference between them means
anything. Only gate-1 against gate-1 is a comparison.

## Round 0: the baseline, measured under the frozen spec

`benchmarks/gate/content-gate-round0-baseline.json`.

| criterion | result |
|---|---|
| **C1** shape | **FAIL** — 40 of 44 distinct shape values map to a single family, and all 16 families are named by at least one unique shape |
| **C2** no family solved outright | **FAIL** — F1 at 2/2 |
| **C3** residual | **FAIL** — 18/41 = **43.9%** against the 40% ceiling |
| **C4** independent read | not run |

Per family: F1 2/2, F3 5/7, F7 2/4, F15 3/8, and F4, F5, F6, F11, F13, F14 each 1/2; F8, F12,
F16, F17 each 0/2.

## What C1 measures, recorded now rather than discovered later

The tuple includes `length` exactly, and thread lengths range from 14 to 94. A tuple that
carries an exact length is close to a fingerprint of the *thread*, so some values will be unique
whatever the family layout does — that is thread granularity, not family leakage. **C1 stays as
frozen and is judged as written**; a coarsened diagnostic is reported beside it, gating nothing,
so the repair's real effect on shape leakage is visible even where C1 cannot move. If C1 as
written turns out to be the wrong instrument, that is a finding to report, not a bar to move
after seeing a score.
