"""PF-4: the cold load stays out of the per-query number, and the reuse is checked.

The defect this file exists because of: the registry's first version built a backend on
every `acquire`. The owner's smoke run then priced a load at 36,543 ms against a 6,000 ms
`MAX_SEMANTIC_MS`. Nothing would have caught that - the rung would have declined on every
query with a timeout, and a timeout reads as "the model is slow" rather than as "the model
is loaded once per query".
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from mailweave.constants import MAX_POOL_MESSAGES, MAX_RERANK_PAIRS, MAX_SEMANTIC_MS
from mailweave.semantic.interface import (
    BackendContractError,
    BackendRegistry,
    BackendUnavailable,
)
from mailweave_harness.modelbench.corpus import BODY_HEAD_CHARS, pool_rows, rerank_pairs
from mailweave_harness.modelbench.measure import PythonArm, analyse, peak_rss_mb
from mailweave_harness.modelbench.spec import POOL_SIZES
from mailweave_harness.preflight.record import assert_record_is_content_free
from mailweave_harness.preflight.spec import Verdict


class _Backend:
    model_id = "test/a+test/b"
    model_revision = "aaaaaaaaaaaa+bbbbbbbbbbbb"

    def embed(self, texts: Any) -> list[tuple[float, ...]]:
        return [(1.0, 0.0)] * len(texts)

    def rerank(self, query: str, candidates: Any) -> list[float]:
        return [0.5] * len(candidates)


# --- the model is built once per process -------------------------------------------------


def test_two_acquires_build_one_backend() -> None:
    built: list[int] = []
    registry = BackendRegistry()
    registry.register("local", lambda: (built.append(1), _Backend())[1])

    first = registry.acquire()
    second = registry.acquire()

    assert len(built) == 1
    assert first is second
    assert registry.is_built()


def test_a_decline_is_remembered_rather_than_retried_every_query() -> None:
    # A machine with no weights is supported. Retrying a failing load per query would spend
    # the failure over and over, and on this hardware a failing load is not cheap.
    attempts: list[int] = []

    def declining() -> _Backend:
        attempts.append(1)
        raise BackendUnavailable("no weights")

    registry = BackendRegistry()
    registry.register("local", declining)

    for _ in range(5):
        with pytest.raises(BackendUnavailable, match="no weights"):
            registry.acquire()

    assert len(attempts) == 1


def test_a_contract_error_is_also_remembered_and_is_not_a_fallback() -> None:
    registry = BackendRegistry()
    registry.register("broken", lambda: object(), default=True)
    with pytest.raises(BackendContractError):
        registry.acquire()
    with pytest.raises(BackendContractError):
        registry.acquire()


def test_concurrent_acquires_do_not_load_twice() -> None:
    # MAX_CONCURRENT_QUERIES is 2, so a check-then-build without the lock held across the
    # build would pay the cold cost twice on the first two queries of a session.
    built: list[int] = []
    barrier = threading.Barrier(2)

    def slow() -> _Backend:
        built.append(1)
        return _Backend()

    registry = BackendRegistry()
    registry.register("local", slow)
    seen: list[object] = []

    def worker() -> None:
        barrier.wait()
        seen.append(registry.acquire())

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(built) == 1
    assert seen[0] is seen[1]


def test_reset_forgets_what_was_built() -> None:
    built: list[int] = []
    registry = BackendRegistry()
    registry.register("local", lambda: (built.append(1), _Backend())[1])
    registry.acquire()
    registry.reset()
    registry.acquire()
    assert len(built) == 2
    assert BackendRegistry().is_built() is False


# --- PF-4's judgement --------------------------------------------------------------------


def _arm(**overrides: Any) -> PythonArm:
    arm = PythonArm(
        cold_acquire_ms=36_543,
        warm_acquire_ms=0,
        embed_ms_by_pool_size={100: 300, 200: 600, 300: 900, 400: 1200},
        single_call_embed_ms=18,
        rerank_ms_by_pairs={5: 140, 10: 280, 25: 700},
        rerank_samples_by_pairs={5: [140] * 5, 10: [280] * 5, 25: [700] * 5},
        embed_samples_by_pool_size={
            100: [300] * 5,
            200: [600] * 5,
            300: [900] * 5,
            400: [1200] * 5,
        },
        device="cpu",
        accelerators_unused=("mps",),
        runtime_versions={"torch": "2.14.0"},
        repeats=5,
        peak_rss_mb=2_100,
        dimension=512,
        model_id="test/a+test/b",
        model_revision="aaaaaaaaaaaa+bbbbbbbbbbbb",
    )
    for key, value in overrides.items():
        setattr(arm, key, value)
    return arm


def test_a_passing_run_records_the_three_constants_the_server_reads() -> None:
    result = analyse(_arm())
    assert result.verdict is Verdict.PASS
    assert result.findings["max_semantic_ms"] == MAX_SEMANTIC_MS
    assert result.findings["max_pool_messages"] == MAX_POOL_MESSAGES
    assert result.findings["max_rerank_pairs"] == MAX_RERANK_PAIRS


def test_the_cold_load_is_never_folded_into_the_per_query_figure() -> None:
    # 36,543 ms of load against a 6,000 ms budget would make the rung look impossible.
    result = analyse(_arm())
    per_query = result.findings["warm_per_query_ms_at_published_pool"]
    assert per_query == 900 + 700
    assert result.findings["cold_acquire_ms"] == 36_543
    assert per_query < result.findings["cold_acquire_ms"]
    assert any("once per process" in note for note in result.notes)


def test_reuse_failing_is_reported_as_an_architecture_defect_not_a_tuning_result() -> None:
    result = analyse(_arm(warm_acquire_ms=36_000))
    assert result.verdict is Verdict.FAIL
    assert result.findings["reuse_holds"] is False
    assert any("architecture defect" in note for note in result.notes)
    # And no measured constant is offered from a run whose numbers cannot be trusted.
    assert "max_semantic_ms" not in result.findings


def test_a_uniformly_slow_machine_cannot_satisfy_reuse_by_being_slow() -> None:
    # 1,000 ms is 2.7% of a 36-second load, which passes the ratio alone.
    result = analyse(_arm(cold_acquire_ms=36_543, warm_acquire_ms=1_200))
    assert result.findings["reuse_holds"] is False


def test_an_overrun_re_derives_the_pool_downward_rather_than_raising_the_budget() -> None:
    slow = {100: 2_000, 200: 4_000, 300: 9_000, 400: 12_000}  # rerank at 25 is 700 ms
    result = analyse(_arm(embed_ms_by_pool_size=slow))
    assert result.verdict is Verdict.FAIL
    assert result.findings["candidate_max_rerank_pairs"] == 25
    assert result.findings["candidate_max_pool_messages"] == 200
    # The direction is the point: the pool comes down, the budget does not go up. The note
    # has to say the second half out loud, because "we measured 9,700 so the budget is now
    # 9,700" is the tempting move and it is how a bound becomes a description.
    overrun = [note for note in result.notes if "max_pool_messages downward" in note]
    assert overrun, result.notes
    assert "rather than to raise MAX_SEMANTIC_MS" in overrun[0]


def test_the_rss_bound_is_a_candidate_and_says_so() -> None:
    result = analyse(_arm())
    assert result.findings["candidate_max_model_rss_mb"] == round(2_100 * 1.25)
    assert result.findings["candidate_is_a_bound_not_a_default"] is True


def test_the_record_carries_numbers_and_no_text() -> None:
    assert_record_is_content_free(analyse(_arm()).as_record())


def test_the_probe_disclaims_quality_and_the_smoke_check() -> None:
    rules = " ".join(analyse(_arm()).spec.pre_registered_rules)
    assert "says nothing about retrieval quality" in rules
    assert "two-item smoke check is not a measurement" in rules


# --- the rows ----------------------------------------------------------------------------


def test_the_rows_are_deterministic_and_the_right_length() -> None:
    assert pool_rows(4) == pool_rows(4)
    assert all(len(row) > 300 for row in pool_rows(4))
    assert all(len(row) > BODY_HEAD_CHARS for row in pool_rows(4, body_head=True))


def test_both_arms_of_pf4b_would_embed_identical_rows() -> None:
    # Otherwise the Node/Python comparison is between two samples of one distribution.
    assert pool_rows(16, seed=7) == pool_rows(16, seed=7)
    assert rerank_pairs(4, seed=7) == rerank_pairs(4, seed=7)


def test_every_declared_pool_size_is_measurable() -> None:
    for size in POOL_SIZES:
        assert len(pool_rows(size)) == size


def test_peak_rss_is_reported_in_megabytes_on_this_platform() -> None:
    # ru_maxrss is bytes on Darwin and kilobytes on Linux; reading it without checking is a
    # 1024x error, and a model-memory bound wrong by three orders of magnitude is worse
    # than none.
    value = peak_rss_mb()
    assert 1 <= value < 200_000


def test_a_rerank_that_busts_the_budget_alone_proposes_a_smaller_k() -> None:
    # A probe that measures one shortlist size can only ever report that the published one
    # did not fit. AD F PF-4 says this probe *sets* max_rerank_pairs.
    result = analyse(
        _arm(
            embed_ms_by_pool_size={100: 120, 200: 230, 300: 340, 400: 450},
            rerank_ms_by_pairs={5: 1_800, 10: 3_600, 25: 8_900},
        )
    )
    assert result.verdict is Verdict.FAIL
    assert result.findings["candidate_max_rerank_pairs"] == 5
    assert result.findings["candidate_max_pool_messages"] == 400


def test_no_affordable_k_is_a_design_question_not_a_quiet_reduction() -> None:
    result = analyse(_arm(rerank_ms_by_pairs={5: 7_000, 10: 9_000, 25: 20_000}))
    assert result.verdict is Verdict.FAIL
    assert result.findings["candidate_max_rerank_pairs"] == 0
    assert any("D.7 design question" in note for note in result.notes)


def test_the_budget_split_is_declared_as_arbitrary() -> None:
    rules = " ".join(analyse(_arm()).spec.pre_registered_rules)
    assert "arbitrary and is declared as arbitrary" in rules
    assert analyse(_arm()).findings["rerank_budget_share"] == 0.5


# --- the benchmark says what it measured, and on what ------------------------------------


def test_the_device_is_recorded_and_the_unused_accelerators_with_it() -> None:
    # AD F PF-4 registers this as CPU-only. A library that quietly selects MPS measures a
    # different machine from the one the plan describes, and run 1 could not say which.
    findings = analyse(_arm()).findings
    assert findings["device"] == "cpu"
    assert findings["accelerators_available_but_unused"] == ["mps"]
    assert findings["runtime_versions"]["torch"] == "2.14.0"


def test_the_loader_names_a_device_rather_than_letting_the_library_choose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The behaviour, not the constant: a default nobody passes is a default nobody gets."""
    import sys
    import types

    from mailweave.semantic.local import DEFAULT_DEVICE, _default_loaders

    assert DEFAULT_DEVICE == "cpu"

    seen: list[dict[str, Any]] = []

    def _capture(path: str, **kwargs: Any) -> object:
        seen.append({"path": path, **kwargs})
        return object()

    fake = types.ModuleType("sentence_transformers")
    fake.SentenceTransformer = _capture  # type: ignore[attr-defined]
    fake.CrossEncoder = _capture  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)

    encoder, reranker = _default_loaders("cpu")
    encoder("/tmp/a")
    reranker("/tmp/b")

    assert len(seen) == 2
    assert all(call.get("device") == "cpu" for call in seen), seen
    assert all(call.get("local_files_only") is True for call in seen)


def test_a_falling_curve_is_inconclusive_rather_than_a_pass() -> None:
    # Run 1's actual numbers: 288 / 229 / 137 ms for 5 / 10 / 25 pairs. A cross-encoder does
    # not get faster with more pairs, and constants from a curve nobody can read have no
    # warrant.
    result = analyse(_arm(rerank_ms_by_pairs={5: 288, 10: 229, 25: 137}))
    assert result.verdict is Verdict.INCONCLUSIVE
    assert result.findings["rerank_curve_is_non_decreasing"] is False
    assert "max_semantic_ms" not in result.findings
    assert any("missing warm-up" in note for note in result.notes)


def test_a_falling_embed_curve_is_inconclusive_too() -> None:
    result = analyse(_arm(embed_ms_by_pool_size={100: 900, 200: 600, 300: 300, 400: 200}))
    assert result.verdict is Verdict.INCONCLUSIVE
    assert result.findings["embed_curve_is_non_decreasing"] is False


def test_every_sample_is_kept_so_the_shape_can_be_inspected_without_a_rerun() -> None:
    findings = analyse(_arm()).findings
    assert findings["repeats_per_size"] == 5
    assert findings["rerank_samples_by_pairs"]["25"] == [700] * 5
    assert findings["embed_samples_by_pool_size"]["300"] == [900] * 5


def test_the_single_call_figure_is_labelled_so_it_cannot_be_multiplied_out() -> None:
    # 18 ms "per text" beside "100 rows in 12 ms" multiplies out to 5.4 s for a 300-row
    # pool, which is a category error the old field name invited.
    result = analyse(_arm())
    assert "single_call_embed_ms" in result.findings
    assert "per_text_embed_ms" not in result.findings
    assert any("category error" in note for note in result.notes)


def test_a_pf4_record_without_a_device_sets_no_constant(tmp_path: Any) -> None:
    # Invalidation by absence, the same shape PF-2 run 1 got: the file stays on disk and
    # simply stops deciding anything.
    import json

    from mailweave.semantic import resolve_profile
    from mailweave.semantic.profile import Basis

    raw = Path("preflight-records/raw/PF-4-run1-2026-09-11-DEVICE-UNRECORDED-RERANK-UNWARMED.json")
    record = json.loads(raw.read_text())
    assert record["verdict"] == "pass"
    assert "device" not in record["findings"]

    (tmp_path / "pf4.json").write_text(json.dumps(record), encoding="utf-8")
    profile = resolve_profile(directory=str(tmp_path))
    assert profile.bounds_provenance.basis is Basis.ASSUMED
