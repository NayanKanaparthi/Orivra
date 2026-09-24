"""PF-4 and PF-4b, declared before they run (AD F, PF-4 / PF-4b).

Reusing `preflight.spec.ProbeSpec` deliberately: these write the same record shape the
server's resolver already reads, and a second record format would be a second thing to keep
in step. They are **not** registered in the Gmail preflight plan, because they need no
credential and no mailbox, and putting them there would make `--run` demand a token to
measure a local CPU.
"""

from __future__ import annotations

from typing import Final

from mailweave.constants import MAX_POOL_MESSAGES, MAX_RERANK_PAIRS, MAX_SEMANTIC_MS
from mailweave_harness.preflight.spec import ProbeSpec

#: Pool sizes measured, so the wall clock is a curve and not one point. AD F names
#: 100/200/400; 300 is added because it is `MAX_POOL_MESSAGES`, the size the published
#: budget is actually asserted about.
POOL_SIZES: Final[tuple[int, ...]] = (100, 200, 300, 400)

#: The second acquire must be materially cheaper than the first, or the process is not
#: reusing the loaded model and every query pays the cold cost. Registered as a ratio and a
#: floor so it cannot be satisfied by a machine that is merely slow.
REUSE_RATIO: Final[float] = 0.05
REUSE_FLOOR_MS: Final[int] = 1_000

#: Shortlist sizes measured, so a failing budget can propose a k as well as a pool size.
#: AD F PF-4 sets `max_rerank_pairs`, and a probe that measures one k can only ever report
#: that the published one did not fit.
RERANK_SIZES: Final[tuple[int, ...]] = (5, 10, MAX_RERANK_PAIRS)

#: Every timed size is run this many times after a discarded warm-up, and the **median** is
#: what the record carries. Run 1 timed each size once, ascending, with no reranker warm-up,
#: and produced 288 / 229 / 137 ms for 5 / 10 / 25 pairs: a curve that falls as the work
#: grows is not a capacity curve, it is the first measurement paying for initialisation the
#: later ones did not.
REPEATS: Final[int] = 5

#: How the budget is split between the two stages when a re-derivation is needed. Arbitrary,
#: chosen before the run, and declared as arbitrary: the full curve is recorded so a reviewer
#: can apply a different split to the same numbers without a re-run.
RERANK_BUDGET_SHARE: Final[float] = 0.5

PF4 = ProbeSpec(
    id="PF-4-model-latency",
    title="Local model cost on this machine, cold load separated from warm work",
    measures=(
        "on this machine, CPU only: the wall clock of the FIRST backend acquire (cold "
        "load), the wall clock of a SECOND acquire in the same process (reuse), embed wall "
        f"clock at pool sizes {list(POOL_SIZES)} on synthetic rows of real pool-row length, "
        f"rerank wall clock at {list(RERANK_SIZES)} pairs, the device the weights were "
        "loaded onto and the accelerators present but unused, the runtime versions, and "
        f"peak resident set size. Every timed size is warmed once and then run {REPEATS} "
        "times; the record carries the median and every sample"
    ),
    validates=(
        f"AD D.5's semantic rung inside MAX_SEMANTIC_MS = {MAX_SEMANTIC_MS} ms at "
        f"MAX_POOL_MESSAGES = {MAX_POOL_MESSAGES} and MAX_RERANK_PAIRS = "
        f"{MAX_RERANK_PAIRS}, and AD D.8's claim that the server process loads its models "
        "once rather than per query"
    ),
    falsified_when=(
        "warm embed at MAX_POOL_MESSAGES plus warm rerank at MAX_RERANK_PAIRS exceeds "
        "MAX_SEMANTIC_MS; or the second acquire is not materially cheaper than the first, "
        "which means the process is reloading the model per use and every query pays the "
        "cold cost"
    ),
    changes_if_it_fails=(
        "the per-query sum failing re-derives max_pool_messages downward to the largest "
        "measured size that fits inside MAX_SEMANTIC_MS, declared per T-RO1 in every "
        "semantic response, rather than MAX_SEMANTIC_MS being raised to whatever was "
        "measured. Reuse failing is an architecture defect in the registry, not a tuning "
        "result, and is fixed before any latency number from this run is quoted"
    ),
    credential="read",
    quota_budget_units=0,
    pre_registered_rules=(
        f"each stage is warmed with a discarded call before timing, and every size is run "
        f"{REPEATS} times with the median recorded. A single ascending pass charges the "
        "first size for initialisation the rest inherit, which is how run 1 produced a "
        "rerank curve that fell as the work grew",
        "the device is named by the loader, never left to the library's default, and is "
        "recorded in the finding. AD F PF-4 registers this measurement as CPU-only, and a "
        "library that quietly selects MPS would be measuring a different machine from the "
        "one the plan describes",
        "a rerank or embed median curve that is not non-decreasing in size makes the "
        "verdict INCONCLUSIVE, not PASS: constants derived from a curve nobody can read are "
        "constants with no warrant",
        "the per-query budget is WARM work only - embed(pool) + rerank(k). The cold load is "
        "paid once per process and is reported separately, never folded into a per-query "
        "figure",
        f"a re-derivation picks the largest measured k whose rerank fits "
        f"{RERANK_BUDGET_SHARE:.0%} of MAX_SEMANTIC_MS, then the largest measured pool that "
        "fits the remainder. The split is arbitrary and is declared as arbitrary; the full "
        "curve is recorded so a reviewer can apply a different split without a re-run",
        "if no measured k fits its share, the finding is that the cross-encoder does not "
        "fit this budget on this machine at any shortlist size measured, which is a D.7 "
        "design question and not a constant to lower quietly",
        f"reuse holds when the second acquire costs less than {REUSE_RATIO:.0%} of the "
        f"first AND less than {REUSE_FLOOR_MS} ms, so a uniformly slow machine cannot "
        "satisfy it by making both numbers large",
        "the cold load is measured on the first acquire of a fresh process. The OS page "
        "cache is not controlled and cannot be from here, so a cold reading is an upper "
        "bound on warm-disk cost and a lower bound on first-ever-run cost, and is reported "
        "as such rather than as the cold cost",
        "max_model_rss_mb is REPORTED as a measured peak plus a stated margin. It is a "
        "candidate bound, not adopted by this probe; adoption is the owner's after seeing "
        "the figure, the same treatment PF-21 gave max_server_ms",
        "this probe says nothing about retrieval quality. Synthetic text of the right "
        "length is a sound instrument for latency and an unsound one for relevance; "
        "H1/H2/H3 measure quality on F1-F17",
        "a two-item smoke check is not a measurement and none of its numbers appear here",
    ),
)

PF4B = ProbeSpec(
    id="PF-4b-node-arm",
    title="The Node/ONNX arm, on the same rows and the same machine",
    measures=(
        "the same wall clocks as PF-4, measured by @huggingface/transformers over the "
        "node-onnx artifact set, on identical synthetic rows from the same seed"
    ),
    validates=(
        "AD B.8 R2, the stack-reversal trigger. Without this arm the project has latency "
        "evidence only about the path it chose, which cannot tell it whether that path was "
        "the slow one"
    ),
    falsified_when=(
        "the Node arm is materially faster at equal quality on the same pool and the same "
        "hardware, which is R2's firing condition and reopens the stack as a finding"
    ),
    changes_if_it_fails=(
        "R2 fires and the stack decision reopens as a finding rather than as a rewrite. "
        "The artifact sets are already locked separately, so the comparison is between two "
        "known sets of bytes rather than between two things both called bge-reranker-base"
    ),
    credential="read",
    quota_budget_units=0,
    pre_registered_rules=(
        "both arms embed the SAME rows, from the same seed, so the comparison is not "
        "between two samples of one distribution",
        "'materially faster' is left unquantified here on purpose: R2's threshold is a "
        "stack decision and belongs to the owner, and a number invented by the arm that "
        "wants to win is not a threshold",
    ),
)
