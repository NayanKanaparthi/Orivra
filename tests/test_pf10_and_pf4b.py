"""The two harness pieces that need no laptop: PF-10's analysis and PF-4b's corpus bridge.

Both are the halves where a mistake would be invisible. PF-10's numbers cannot be
manufactured, but the rules that turn them into a verdict can be written and executed before
the numbers exist - which is the whole property a pre-registered threshold is supposed to
have. PF-4b cannot be run without a Node runtime, but "both arms embedded the same rows" can
be made checkable by digest instead of asserted by two seeded generators agreeing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mailweave_harness.freshness.analysis import (
    FSL_SECONDS,
    STRATA,
    CensoredSample,
    Observation,
    PoolingProhibited,
    Stratum,
    analyse_freshness,
    p90,
)
from mailweave_harness.modelbench.nodearm import (
    CORPUS_SCHEMA,
    NodeArmRefused,
    comparison,
    corpus_payload,
    export_corpus,
    read_node_results,
)


def _obs(stratum: Stratum, lag: float | None, *, mailbox: str = "a", fn: bool = False):  # type: ignore[no-untyped-def]
    return Observation(
        stratum=stratum,
        lag_seconds=lag,
        mailbox=mailbox,
        probe_class="body_term",
        confirmed_false_negative=fn,
    )


# --- OD-1, and the three ways this analysis could quietly be wrong -------------------------


def test_pooling_across_strata_is_unrepresentable_rather_than_forbidden() -> None:
    """OD-1: "Pooling across depths is prohibited."

    A pooled p90 passes whenever the two fast strata outnumber the slow one - which is the
    depth-25 case the design believes is slower. There is no call shape here that computes
    one number over three strata, so an analysis cannot pool by forgetting to separate.
    """
    mixed = [_obs(Stratum.DEPTH_0, 5.0), _obs(Stratum.DEPTH_25, 500.0)]
    with pytest.raises(PoolingProhibited, match="pooling"):
        p90(Stratum.DEPTH_0, mixed)


def test_a_slow_stratum_fails_even_when_the_other_two_are_fast() -> None:
    """The failure a pooled percentile would hide, asserted end to end."""
    observations = (
        [_obs(Stratum.DEPTH_0, 2.0) for _ in range(10)]
        + [_obs(Stratum.DEPTH_5, 3.0) for _ in range(10)]
        + [_obs(Stratum.DEPTH_25, 400.0) for _ in range(10)]
    )
    verdict = analyse_freshness(observations)
    assert verdict.mf2_fires is True
    assert verdict.passes is False
    by_depth = {row.stratum: row for row in verdict.strata}
    assert by_depth[Stratum.DEPTH_0].meets_fsl is True
    assert by_depth[Stratum.DEPTH_25].meets_fsl is False


def test_a_probe_that_never_surfaced_cannot_be_averaged_away() -> None:
    """Dropping a censored observation improves the percentile by removing MF1 itself."""
    with pytest.raises(CensoredSample, match="never surfaced"):
        p90(Stratum.DEPTH_0, [_obs(Stratum.DEPTH_0, 1.0), _obs(Stratum.DEPTH_0, None)])


def test_a_censored_stratum_makes_the_whole_verdict_inconclusive_not_a_pass() -> None:
    """Two computable strata out of three is a different claim from OD-1's question."""
    observations = [
        _obs(Stratum.DEPTH_0, 1.0),
        _obs(Stratum.DEPTH_5, 1.0),
        _obs(Stratum.DEPTH_25, None),
    ]
    verdict = analyse_freshness(observations)
    assert verdict.inconclusive is True
    assert verdict.passes is False
    assert "INCONCLUSIVE" in verdict.rendered()


def test_a_confirmed_false_negative_is_a_defect_regardless_of_percentile() -> None:
    """OD-1's second trigger, stated independently and in the same words."""
    observations = [_obs(stratum, 1.0) for stratum in STRATA for _ in range(5)] + [
        _obs(Stratum.DEPTH_0, 1.0, fn=True)
    ]
    verdict = analyse_freshness(observations)
    assert verdict.mf2_fires is False, "every stratum is well inside the FSL here"
    assert verdict.mf4_fires is True
    assert verdict.passes is False
    assert "regardless of p90" in verdict.rendered()


def test_a_missing_stratum_is_inconclusive_rather_than_a_pass_over_the_two_that_ran() -> None:
    verdict = analyse_freshness([_obs(Stratum.DEPTH_0, 1.0)])
    assert verdict.inconclusive is True
    assert verdict.passes is False


def test_the_percentile_is_nearest_rank_so_it_reports_a_lag_somebody_measured() -> None:
    """An interpolated p90 reports a value nobody observed; OD-1's threshold is about behaviour."""
    lags = [float(value) for value in range(1, 11)]
    observations = [_obs(Stratum.DEPTH_0, lag) for lag in lags]
    assert p90(Stratum.DEPTH_0, observations) == 9.0
    assert p90(Stratum.DEPTH_0, observations) in lags


def test_the_service_level_is_the_owner_decision_and_not_a_local_choice() -> None:
    assert FSL_SECONDS == 60.0
    assert [stratum.value for stratum in STRATA] == [0, 5, 25]


def test_the_two_mailbox_rule_is_reported_rather_than_assumed() -> None:
    """T-VR2: one mailbox is a sample of one environment, not of Gmail."""
    single = analyse_freshness([_obs(stratum, 1.0) for stratum in STRATA])
    assert single.two_mailboxes is False
    paired = analyse_freshness(
        [_obs(stratum, 1.0) for stratum in STRATA]
        + [_obs(stratum, 1.0, mailbox="b") for stratum in STRATA]
    )
    assert paired.two_mailboxes is True


# --- PF-4b's corpus bridge -----------------------------------------------------------------


def test_the_exported_corpus_carries_the_rows_and_not_only_the_seed(tmp_path: Path) -> None:
    """PF-4b's first registered rule, made checkable.

    A Node arm that re-implemented the Python generator would produce *similar* rows and the
    rule would read as satisfied while being false. The rows cross as data instead.
    """
    path = export_corpus(tmp_path / "corpus.json")
    payload = json.loads(path.read_text())
    assert len(payload["rows"]) == max(payload["pool_sizes"])
    assert payload["rerank_candidates"]
    assert payload["digest"]


def test_a_node_result_for_a_different_corpus_is_refused(tmp_path: Path) -> None:
    corpus = corpus_payload()
    results = _node_results(corpus, corpus_digest="0" * 64)
    with pytest.raises(NodeArmRefused, match="same rows"):
        read_node_results(results, corpus)


def test_a_node_result_with_one_pass_per_size_is_refused() -> None:
    """A single ascending pass is what produced PF-4 run 1's falling rerank curve."""
    corpus = corpus_payload()
    results = _node_results(corpus, repeats_per_size=1)
    with pytest.raises(NodeArmRefused, match="repeats_per_size"):
        read_node_results(results, corpus)


def test_a_node_result_that_did_not_record_its_device_is_refused() -> None:
    corpus = corpus_payload()
    results = _node_results(corpus, device="")
    with pytest.raises(NodeArmRefused, match="device"):
        read_node_results(results, corpus)


def test_a_node_result_that_timed_other_sizes_is_refused() -> None:
    corpus = corpus_payload()
    results = _node_results(corpus)
    results["embed_ms_by_pool_size"] = {"7": 1}
    with pytest.raises(NodeArmRefused, match="pool sizes"):
        read_node_results(results, corpus)


def test_r2_fires_only_on_a_material_difference_and_never_on_quality() -> None:
    """Reopening a stack decision on a 5% difference is how a project loses a week."""
    corpus = corpus_payload()
    node = read_node_results(_node_results(corpus), corpus)
    close = comparison({"embed_ms_by_pool_size": dict.fromkeys(corpus["pool_sizes"], 10)}, node)
    assert close["r2_fires"] is False
    faster = comparison({"embed_ms_by_pool_size": dict.fromkeys(corpus["pool_sizes"], 100)}, node)
    assert faster["r2_fires"] is True
    assert "equal quality" in faster["quality_is_not_compared_here"]


def _node_results(corpus: dict[str, object], **overrides: object) -> dict[str, object]:
    sizes = corpus["pool_sizes"]
    rerank = corpus["rerank_sizes"]
    assert isinstance(sizes, list) and isinstance(rerank, list)
    results: dict[str, object] = {
        "corpus_digest": corpus["digest"],
        "runtime_versions": {"@huggingface/transformers": "4.0.0"},
        "device": "cpu",
        "cold_acquire_ms": 4000,
        "warm_acquire_ms": 0,
        "embed_ms_by_pool_size": {str(size): 10 for size in sizes},
        "rerank_ms_by_pairs": {str(size): 50 for size in rerank},
        "repeats_per_size": corpus["repeats"],
        "embedding_dimension": 512,
    }
    results.update(overrides)
    return results


# --- PF-4b's partial arm, and the end-to-end command -----------------------------------------


def test_an_arm_that_measured_one_stage_says_so_and_is_accepted() -> None:
    """A partial arm is a legitimate result. A silent one is not.

    `models-catalog.json` pins a `node-onnx` artifact set for `stage_b_default` and for no
    other model, so a Node arm on this repository's lock has nothing to embed with. Recording
    that as `stages_measured` puts the gap in the record, where R2's condition can see it.
    """
    corpus = corpus_payload()
    results = _node_results(corpus)
    results["stages_measured"] = ["rerank"]
    del results["embed_ms_by_pool_size"]
    arm = read_node_results(results, corpus)
    assert arm.stages_measured == ("rerank",)
    assert arm.embed_ms_by_pool_size == {}
    assert arm.rerank_ms_by_pairs


def test_an_arm_that_omits_a_stage_without_declaring_it_is_still_refused() -> None:
    """The absence has to be a statement. An older file with no `stages_measured` defaults to
    both stages and is refused for the one it left empty, exactly as before the field
    existed."""
    corpus = corpus_payload()
    results = _node_results(corpus)
    del results["embed_ms_by_pool_size"]
    with pytest.raises(NodeArmRefused, match="embed_ms_by_pool_size"):
        read_node_results(results, corpus)


def test_declaring_a_stage_and_reporting_it_anyway_is_refused() -> None:
    """The declaration and the numbers agree or one of them is decoration."""
    corpus = corpus_payload()
    results = _node_results(corpus)
    results["stages_measured"] = ["rerank"]
    with pytest.raises(NodeArmRefused, match="decoration"):
        read_node_results(results, corpus)


def test_r2_is_not_evaluable_on_an_arm_that_did_not_measure_the_embed_stage() -> None:
    """Not `false`: **not evaluable**.

    R2 asks whether the Node stack is materially faster at equal quality, and the cost the
    semantic rung is bounded by at `MAX_POOL_MESSAGES` is stage A. Reporting `r2_fires:
    false` over the reranker alone would answer a smaller question under R2's name, which is
    the shape this repository keeps finding: a check that passes for a reason that does not
    establish what it claims.
    """
    corpus = corpus_payload()
    results = _node_results(corpus)
    results["stages_measured"] = ["rerank"]
    del results["embed_ms_by_pool_size"]
    arm = read_node_results(results, corpus)
    verdict = comparison({"embed_ms_by_pool_size": dict.fromkeys(corpus["pool_sizes"], 100)}, arm)
    assert verdict["r2_evaluable"] is False
    assert verdict["r2_fires"] is False
    assert "stage_b_default" in verdict["why_not_evaluable"]
    assert "equal quality" in verdict["quality_is_not_compared_here"]


def test_the_node_arm_script_exists_and_reads_the_schema_this_export_writes() -> None:
    """The command the owner is given is a file in this repository, not a description of one.

    Checked structurally rather than executed: running it needs Node, an npm install and the
    stage_b ONNX artifacts, all of which are the owner's machine. What can be checked here is
    that the script exists, that it refuses a corpus schema it does not know, that it reads
    the fields this exporter writes, and that it declares the stage it measures.
    """
    script = Path(__file__).resolve().parents[1] / "harness" / "node" / "pf4b-arm.mjs"
    assert script.is_file(), script
    source = script.read_text(encoding="utf-8")
    assert f"corpus.schema !== {CORPUS_SCHEMA}" in source
    for field in ("digest", "rerank_query", "rerank_candidates", "rerank_sizes", "repeats"):
        assert f"corpus.{field}" in source or f'"{field}"' in source, field
    assert 'stages_measured: ["rerank"]' in source
    # Local only: a silent download would make this a measurement of somebody's network.
    assert "allowRemoteModels = false" in source
