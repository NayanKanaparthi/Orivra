"""Running PF-4, and keeping the cold cost out of the per-query number.

The separation this module exists for: **a cold load is paid once per process and a query
pays neither it nor a share of it.** Folding 36 seconds of model load into a per-query
latency figure would make the semantic rung look impossible; leaving the load unmeasured
would hide a real cost the first query of a session actually waits for. So both are
measured, reported apart, and the probe additionally checks that the reuse which justifies
the separation is really happening.

That check is not ceremony. The registry's first version built a backend on every
`acquire`, which nothing would have caught: the rung would have declined on every query
with a timeout, and a timeout reads as "the model is slow" rather than as "the model is
loaded 500 times".
"""

from __future__ import annotations

import itertools
import platform
import resource
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mailweave.constants import MAX_POOL_MESSAGES, MAX_RERANK_PAIRS, MAX_SEMANTIC_MS
from mailweave.models.lock import Lock
from mailweave.models.paths import DEFAULT_MODELS_DIR
from mailweave.semantic.interface import (
    BackendRegistry,
    SemanticBackend,
    checked_embed,
    checked_rerank,
)
from mailweave_harness.modelbench.corpus import pool_rows, rerank_pairs
from mailweave_harness.modelbench.spec import (
    PF4,
    POOL_SIZES,
    REPEATS,
    RERANK_BUDGET_SHARE,
    RERANK_SIZES,
    REUSE_FLOOR_MS,
    REUSE_RATIO,
)
from mailweave_harness.preflight.spec import ProbeResult, Verdict


def peak_rss_mb() -> int:
    """Peak resident set size, in megabytes, on either platform's units.

    `ru_maxrss` is bytes on Darwin and kilobytes on Linux. Reading it without checking is a
    1024x error in whichever direction the reader did not expect, and a model-memory bound
    that is wrong by three orders of magnitude is worse than none.
    """
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(raw / (1024 * 1024)) if platform.system() == "Darwin" else round(raw / 1024)


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _median_ms(samples: list[int]) -> int:
    return int(statistics.median(samples))


def _is_non_decreasing(curve: dict[int, int]) -> bool:
    values = [curve[size] for size in sorted(curve)]
    return all(earlier <= later for earlier, later in itertools.pairwise(values))


@dataclass
class PythonArm:
    """What one run observed. Numbers only; no text, no ids."""

    cold_acquire_ms: int = 0
    warm_acquire_ms: int = 0
    embed_ms_by_pool_size: dict[int, int] = field(default_factory=dict)
    embed_samples_by_pool_size: dict[int, list[int]] = field(default_factory=dict)
    #: One `embed` call carrying one row. This is **call overhead plus one row**, not the
    #: marginal cost of a row, and run 1's label invited exactly that misreading: 18 ms
    #: "per text" beside 100 rows in 12 ms would multiply out to 5.4 s for a 300-row pool.
    single_call_embed_ms: int = 0
    rerank_ms_by_pairs: dict[int, int] = field(default_factory=dict)
    rerank_samples_by_pairs: dict[int, list[int]] = field(default_factory=dict)
    rerank_pairs: int = MAX_RERANK_PAIRS
    repeats: int = REPEATS
    peak_rss_mb: int = 0
    dimension: int = 0
    model_id: str = ""
    model_revision: str = ""
    device: str = ""
    accelerators_unused: tuple[str, ...] = ()
    runtime_versions: dict[str, str] = field(default_factory=dict)
    body_head_branch: bool = False


def measure_python_arm(
    lock: Lock,
    *,
    models_dir: Path | str = DEFAULT_MODELS_DIR,
    pool_sizes: tuple[int, ...] = POOL_SIZES,
    body_head: bool = False,
    device: str | None = None,
    repeats: int = REPEATS,
) -> PythonArm:
    """Load once, time the load, time a second acquire, then do the warm work.

    Each stage gets its own discarded warm-up and each size is run `repeats` times. A single
    ascending pass charges the first size for initialisation every later size inherits,
    which is how run 1 reported rerank getting *faster* as the work grew.
    """
    from mailweave.semantic.local import (
        DEFAULT_DEVICE,
        available_accelerators,
        build_local_backend,
        runtime_versions,
    )

    chosen = device or DEFAULT_DEVICE
    registry = BackendRegistry()
    registry.register("local", lambda: build_local_backend(lock, root=models_dir, device=chosen))

    started = time.perf_counter()
    backend: SemanticBackend = registry.acquire()
    cold = _ms(started)

    # The second acquire is the whole reuse claim, measured rather than asserted.
    started = time.perf_counter()
    again = registry.acquire()
    warm = _ms(started)
    if again is not backend:  # pragma: no cover - the registry's own test covers this
        raise AssertionError("the registry returned a different backend on the second acquire")

    arm = PythonArm(
        cold_acquire_ms=cold,
        warm_acquire_ms=warm,
        model_id=backend.model_id,
        model_revision=backend.model_revision,
        device=getattr(backend, "device", chosen),
        accelerators_unused=available_accelerators(),
        runtime_versions=runtime_versions(),
        repeats=repeats,
        body_head_branch=body_head,
    )

    # Stage A warm-up, discarded.
    checked_embed(backend, pool_rows(8, body_head=body_head))

    for size in pool_sizes:
        rows = pool_rows(size, body_head=body_head)
        samples: list[int] = []
        for _ in range(repeats):
            started = time.perf_counter()
            vectors = checked_embed(backend, rows)
            samples.append(_ms(started))
        arm.embed_samples_by_pool_size[size] = samples
        arm.embed_ms_by_pool_size[size] = _median_ms(samples)
        arm.dimension = len(vectors[0])

    single = pool_rows(1, body_head=body_head)
    single_samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        checked_embed(backend, single)
        single_samples.append(_ms(started))
    arm.single_call_embed_ms = _median_ms(single_samples)

    # Stage B warm-up, discarded, at the largest size so no later run pays for a first
    # forward pass. This is the omission that inverted run 1's curve.
    warm_query, warm_candidates = rerank_pairs(max(RERANK_SIZES))
    checked_rerank(backend, warm_query, warm_candidates)

    for pairs in RERANK_SIZES:
        query, candidates = rerank_pairs(pairs)
        samples = []
        for _ in range(repeats):
            started = time.perf_counter()
            checked_rerank(backend, query, candidates)
            samples.append(_ms(started))
        arm.rerank_samples_by_pairs[pairs] = samples
        arm.rerank_ms_by_pairs[pairs] = _median_ms(samples)

    arm.peak_rss_mb = peak_rss_mb()
    return arm


def analyse(arm: PythonArm) -> ProbeResult:
    """Judge the warm per-query sum and the reuse, and propose the bounds."""
    embed_at_published = arm.embed_ms_by_pool_size.get(MAX_POOL_MESSAGES)
    rerank_at_published = arm.rerank_ms_by_pairs.get(MAX_RERANK_PAIRS)
    per_query_ms = (embed_at_published or 0) + (rerank_at_published or 0)
    fits = (
        embed_at_published is not None
        and rerank_at_published is not None
        and per_query_ms <= MAX_SEMANTIC_MS
    )

    reuse_holds = (
        arm.warm_acquire_ms < REUSE_FLOOR_MS
        and arm.warm_acquire_ms < arm.cold_acquire_ms * REUSE_RATIO
    )

    # Pre-registered: the largest measured k whose rerank fits its declared share, then the
    # largest measured pool that fits what is left. The split is arbitrary and says so.
    rerank_budget = int(MAX_SEMANTIC_MS * RERANK_BUDGET_SHARE)
    affordable_k = [
        pairs for pairs, ms in sorted(arm.rerank_ms_by_pairs.items()) if ms <= rerank_budget
    ]
    candidate_k = max(affordable_k) if affordable_k else 0
    remaining = MAX_SEMANTIC_MS - arm.rerank_ms_by_pairs.get(candidate_k, MAX_SEMANTIC_MS)
    affordable_pool = [
        size for size, ms in sorted(arm.embed_ms_by_pool_size.items()) if ms <= remaining
    ]
    candidate_pool = max(affordable_pool) if (candidate_k and affordable_pool) else 0

    findings: dict[str, Any] = {
        "model_id": arm.model_id,
        "model_revision": arm.model_revision,
        "pool_text_branch": "body-head-400" if arm.body_head_branch else "snippet",
        "cold_acquire_ms": arm.cold_acquire_ms,
        "warm_acquire_ms": arm.warm_acquire_ms,
        "reuse_holds": reuse_holds,
        "embed_ms_by_pool_size": {str(k): v for k, v in sorted(arm.embed_ms_by_pool_size.items())},
        "device": arm.device,
        "accelerators_available_but_unused": list(arm.accelerators_unused),
        "runtime_versions": dict(arm.runtime_versions),
        "repeats_per_size": arm.repeats,
        "single_call_embed_ms": arm.single_call_embed_ms,
        "embed_samples_by_pool_size": {
            str(k): v for k, v in sorted(arm.embed_samples_by_pool_size.items())
        },
        "rerank_samples_by_pairs": {
            str(k): v for k, v in sorted(arm.rerank_samples_by_pairs.items())
        },
        "embed_curve_is_non_decreasing": _is_non_decreasing(arm.embed_ms_by_pool_size),
        "rerank_curve_is_non_decreasing": _is_non_decreasing(arm.rerank_ms_by_pairs),
        "rerank_ms_by_pairs": {str(k): v for k, v in sorted(arm.rerank_ms_by_pairs.items())},
        "rerank_ms": rerank_at_published or 0,
        "rerank_pairs": arm.rerank_pairs,
        "embedding_dimension": arm.dimension,
        "peak_rss_mb": arm.peak_rss_mb,
        "published_max_semantic_ms": MAX_SEMANTIC_MS,
        "published_max_pool_messages": MAX_POOL_MESSAGES,
        "warm_per_query_ms_at_published_pool": per_query_ms,
        "candidate_max_pool_messages": candidate_pool,
        "candidate_max_rerank_pairs": candidate_k,
        "rerank_budget_share": RERANK_BUDGET_SHARE,
        "candidate_max_model_rss_mb": round(arm.peak_rss_mb * 1.25),
        "candidate_is_a_bound_not_a_default": True,
    }

    notes = [
        "cold_acquire_ms is paid once per process and is NOT part of the per-query figure; "
        "warm_acquire_ms is the second acquire in the same process and is what makes that "
        "separation legitimate.",
        "the OS page cache is not controlled here, so cold_acquire_ms is an upper bound on "
        "warm-disk cost and a lower bound on a first-ever run.",
        "single_call_embed_ms is ONE call carrying ONE row: call overhead plus a row, not "
        "the marginal cost of a row. Multiplying it by a pool size is a category error; the "
        "pool curve is what prices a pool.",
        "these are latency numbers on synthetic rows of real length. They say nothing about "
        "retrieval quality, which H1/H2/H3 measure on F1-F17.",
    ]

    curves_readable = _is_non_decreasing(arm.embed_ms_by_pool_size) and _is_non_decreasing(
        arm.rerank_ms_by_pairs
    )

    if not reuse_holds:
        verdict = Verdict.FAIL
        notes.append(
            "REUSE FAILED: the second acquire was not materially cheaper than the first, so "
            "this process reloads the model per use and every query pays the cold cost. "
            "That is an architecture defect in the registry, not a tuning result, and no "
            "latency figure from this run should be quoted until it is fixed."
        )
    elif not curves_readable:
        verdict = Verdict.INCONCLUSIVE
        notes.append(
            "a median curve is not non-decreasing in size, so it cannot be read as a "
            "capacity curve and no constant is derived from it. Run 1 produced 288 / 229 / "
            "137 ms for 5 / 10 / 25 rerank pairs, which is the signature of a missing "
            "warm-up rather than of a model that speeds up under load. Every sample is in "
            "the record so the shape can be inspected without a re-run."
        )
    elif not fits:
        verdict = Verdict.FAIL
        notes.append(
            f"the warm per-query sum at the published sizes is {per_query_ms} ms against "
            f"MAX_SEMANTIC_MS = {MAX_SEMANTIC_MS} ms. The pre-registered consequence is to "
            f"re-derive max_rerank_pairs to {candidate_k} and max_pool_messages downward to "
            f"{candidate_pool}, declared per T-RO1 in every semantic response, rather than "
            "to raise MAX_SEMANTIC_MS to whatever was measured."
        )
        if not candidate_k:
            notes.append(
                "NO measured shortlist size fits its share of the budget. That is not a "
                "constant to lower quietly: it is the finding that the cross-encoder does "
                "not fit this budget on this machine at any k measured, and it is a D.7 "
                "design question for the owner."
            )
    else:
        verdict = Verdict.PASS
        findings["max_semantic_ms"] = MAX_SEMANTIC_MS
        findings["max_pool_messages"] = MAX_POOL_MESSAGES
        findings["max_rerank_pairs"] = MAX_RERANK_PAIRS
        notes.append(
            "the published bounds hold on this machine and are recorded as measured. "
            "max_model_rss_mb is a candidate only; adoption is the owner's."
        )

    return ProbeResult(spec=PF4, verdict=verdict, findings=findings, notes=tuple(notes))
