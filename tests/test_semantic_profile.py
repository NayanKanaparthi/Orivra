"""The semantic profile: where every operating parameter came from, and what happens without one.

The property under test is narrow and load-bearing: **no guessed constant reaches the
semantic path, and a value never claims a warrant it does not have.** Three ways that can
break, one test class each:

  * the reader drifts from the producer's file format and silently reads nothing;
  * a verdict is used where findings were needed, so the wrong branch is selected;
  * a partly-measured profile calls itself measured.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mailweave import constants
from mailweave.semantic import (
    Basis,
    PoolTextMode,
    Provenance,
    SemanticProfile,
    load_records,
    resolve_profile,
    unmeasured_profile,
)
from mailweave.semantic.profile import FALLBACK_MAX_POOL_THREADS, METADATA_ROWS_MAX_POOL_MESSAGES
from mailweave.semantic.records import (
    FINDINGS_KEY,
    MEASURED_VERDICTS,
    PROBE_ID_KEY,
    RECORDED_AT_KEY,
    VERDICT_KEY,
)
from mailweave.semantic.resolve import (
    PF2_METADATA_HEADERS,
    PF4_MODEL_LATENCY,
    reply_chain_needs_full,
)


def _write(tmp_path: Path, name: str, payload: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _pf2(**findings: object) -> dict[str, object]:
    base: dict[str, object] = {
        "messages_compared": 12,
        "messages_losing_snippet_under_metadata": 0,
        "messages_losing_internal_date_under_metadata": 0,
        "reply_linking_headers_dropped": [],
        # Per-question verdicts, added 2026-09-11. A record without them answered neither
        # question, whatever its overall verdict said.
        "snippet_verdict": "pass",
        "reply_header_verdict": "pass",
        "reply_header_bearing_messages_compared": 9,
        "snippet_bearing_messages_compared": 12,
    }
    base.update(findings)
    return {
        PROBE_ID_KEY: PF2_METADATA_HEADERS,
        VERDICT_KEY: "pass",
        RECORDED_AT_KEY: "2026-09-10T00:00:00Z",
        FINDINGS_KEY: base,
    }


class TestTheReaderMatchesItsProducer:
    """The reader was written against a format it does not own. It is tested against it."""

    def test_the_reader_uses_the_key_names_the_producer_actually_writes(self) -> None:
        # Derived from the producer, not restated. The first draft of the reader looked for
        # `id` and `observed_at`; the producer writes `probe` and the writer adds
        # `recorded_at`. Every record on disk would have been skipped as malformed and the
        # profile would have said "assumed" forever, with nothing failing.
        from mailweave_harness.preflight.spec import ProbeResult, ProbeSpec, Verdict

        spec = ProbeSpec(
            id="PF-0-example",
            title="t",
            measures="m",
            validates="v",
            falsified_when="f",
            changes_if_it_fails="c",
        )
        written = ProbeResult(spec=spec, verdict=Verdict.PASS, findings={"n": 1}).as_record()

        assert PROBE_ID_KEY in written
        assert VERDICT_KEY in written
        assert FINDINGS_KEY in written

    def test_only_a_pass_counts_as_measured_and_the_vocabulary_has_not_drifted(self) -> None:
        from mailweave_harness.preflight.spec import Verdict

        assert {Verdict.PASS.value} == MEASURED_VERDICTS
        # Every other verdict the producer can emit must read as absent.
        others = {v.value for v in Verdict} - MEASURED_VERDICTS
        assert others == {"fail", "inconclusive", "observation_only"}

    def test_a_record_the_writer_actually_wrote_is_readable(self, tmp_path: Path) -> None:
        # The one record on disk, read through the real loader.
        real = json.loads(Path("preflight-records/PF-21-endpoint-latency.json").read_text())
        _write(tmp_path, "PF-21.json", real)
        found = load_records(tmp_path)
        assert set(found) == {real[PROBE_ID_KEY]}

    def test_a_corrupt_record_is_absent_rather_than_fatal(self, tmp_path: Path) -> None:
        (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
        assert load_records(tmp_path) == {}
        assert resolve_profile(directory=str(tmp_path)).measured is False

    def test_a_record_missing_its_probe_id_is_not_a_record(self, tmp_path: Path) -> None:
        _write(tmp_path, "x.json", {VERDICT_KEY: "pass", FINDINGS_KEY: {}})
        assert load_records(tmp_path) == {}


class TestTheBranchComesFromFindingsNotFromTheVerdict:
    """PF-2 fails if *either* the snippet or a reply header is lost. They are different branches."""

    def test_with_no_record_the_declared_fallback_is_taken_and_says_so(
        self, tmp_path: Path
    ) -> None:
        profile = resolve_profile(directory=str(tmp_path))
        assert profile.pool_text_mode is PoolTextMode.BODY_HEAD
        assert profile.max_pool_threads == FALLBACK_MAX_POOL_THREADS
        assert profile.pool_text_provenance.basis is Basis.ASSUMED
        assert "PF-2 has not run" in profile.pool_text_provenance.detail

    def test_a_clean_pf2_puts_the_pool_on_the_snippet_path_at_the_full_bound(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "pf2.json", _pf2())
        profile = resolve_profile(directory=str(tmp_path))
        assert profile.pool_text_mode is PoolTextMode.SNIPPET
        assert profile.max_pool_threads == constants.MAX_POOL_THREADS
        assert profile.pool_text_provenance.basis is Basis.MEASURED

    def test_a_lost_snippet_moves_the_pool_to_the_fallback_and_it_is_measured_not_assumed(
        self, tmp_path: Path
    ) -> None:
        # The distinction this whole module exists for: the fallback was *measured* to be
        # necessary. Reporting it as assumed would understate what is known.
        _write(
            tmp_path,
            "pf2.json",
            _pf2(messages_losing_snippet_under_metadata=7, snippet_verdict="fail")
            | {VERDICT_KEY: "fail"},
        )
        profile = resolve_profile(directory=str(tmp_path))
        assert profile.pool_text_mode is PoolTextMode.BODY_HEAD
        assert profile.max_pool_threads == FALLBACK_MAX_POOL_THREADS
        assert profile.pool_text_provenance.basis is Basis.MEASURED
        assert "7 lost their snippet" in profile.pool_text_provenance.detail

    def test_a_dropped_reply_header_does_not_move_the_pool_off_the_snippet_path(
        self, tmp_path: Path
    ) -> None:
        # Reading the FAIL verdict alone would send the pool to the fallback for a reason
        # that has nothing to do with the pool.
        _write(
            tmp_path,
            "pf2.json",
            _pf2(reply_linking_headers_dropped=["in-reply-to"], reply_header_verdict="fail")
            | {VERDICT_KEY: "fail"},
        )
        profile = resolve_profile(directory=str(tmp_path))
        assert profile.pool_text_mode is PoolTextMode.SNIPPET
        needs_full, provenance = reply_chain_needs_full(directory=str(tmp_path))
        assert needs_full is True
        assert provenance.basis is Basis.MEASURED

    def test_an_inconclusive_record_decides_nothing(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pf2.json",
            {
                PROBE_ID_KEY: PF2_METADATA_HEADERS,
                VERDICT_KEY: "inconclusive",
                RECORDED_AT_KEY: "2026-09-10T00:00:00Z",
                FINDINGS_KEY: {"messages_compared": 0},
            },
        )
        profile = resolve_profile(directory=str(tmp_path))
        assert profile.pool_text_provenance.basis is Basis.ASSUMED

    def test_a_true_where_a_count_belongs_is_not_read_as_one(self, tmp_path: Path) -> None:
        # `bool` is an `int`. A `True` here would read as "one message lost its snippet",
        # which is a claim the producer never made.
        _write(
            tmp_path,
            "pf2.json",
            _pf2(messages_losing_snippet_under_metadata=True),
        )
        profile = resolve_profile(directory=str(tmp_path))
        assert profile.pool_text_mode is PoolTextMode.SNIPPET


class TestAProfileNeverClaimsAWarrantItDoesNotHave:
    def test_measured_requires_both_the_branch_and_the_bounds(self, tmp_path: Path) -> None:
        _write(tmp_path, "pf2.json", _pf2())
        profile = resolve_profile(directory=str(tmp_path))
        assert profile.pool_text_provenance.basis is Basis.MEASURED
        assert profile.bounds_provenance.basis is Basis.ASSUMED
        assert profile.measured is False

    def test_a_passing_pf4_supplies_the_bounds(self, tmp_path: Path) -> None:
        _write(tmp_path, "pf2.json", _pf2())
        _write(
            tmp_path,
            "pf4.json",
            {
                PROBE_ID_KEY: PF4_MODEL_LATENCY,
                VERDICT_KEY: "pass",
                RECORDED_AT_KEY: "2026-09-10T00:00:00Z",
                FINDINGS_KEY: {
                    "max_semantic_ms": 4200,
                    "max_pool_messages": 240,
                    "max_rerank_pairs": 20,
                    # A PF-4 record has to say what it measured on and how many times, and
                    # its curve has to be readable. Run 1 said none of the three.
                    "device": "cpu",
                    "repeats_per_size": 5,
                    "rerank_curve_is_non_decreasing": True,
                },
            },
        )
        profile = resolve_profile(directory=str(tmp_path))
        assert (profile.max_semantic_ms, profile.max_pool_messages, profile.max_rerank_pairs) == (
            4200,
            240,
            20,
        )
        assert profile.measured is True

    def test_a_pf4_missing_one_constant_leaves_all_three_assumed(self, tmp_path: Path) -> None:
        # Taking the two it has and leaving the third assumed would produce a profile whose
        # `bounds_provenance` cites a record for a number that record does not contain.
        _write(tmp_path, "pf2.json", _pf2())
        _write(
            tmp_path,
            "pf4.json",
            {
                PROBE_ID_KEY: PF4_MODEL_LATENCY,
                VERDICT_KEY: "pass",
                RECORDED_AT_KEY: "2026-09-10T00:00:00Z",
                FINDINGS_KEY: {
                    "max_semantic_ms": 4200,
                    "max_pool_messages": 240,
                    "device": "cpu",
                    "repeats_per_size": 5,
                    "rerank_curve_is_non_decreasing": True,
                },
            },
        )
        profile = resolve_profile(directory=str(tmp_path))
        assert profile.bounds_provenance.basis is Basis.ASSUMED
        assert profile.max_semantic_ms == constants.MAX_SEMANTIC_MS

    def test_a_failing_pf4_is_evidence_about_the_model_not_parameters_to_run_under(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "pf2.json", _pf2())
        _write(
            tmp_path,
            "pf4.json",
            {
                PROBE_ID_KEY: PF4_MODEL_LATENCY,
                VERDICT_KEY: "fail",
                RECORDED_AT_KEY: "2026-09-10T00:00:00Z",
                FINDINGS_KEY: {
                    "max_semantic_ms": 99000,
                    "max_pool_messages": 12,
                    "max_rerank_pairs": 4,
                    "device": "cpu",
                    "repeats_per_size": 5,
                    "rerank_curve_is_non_decreasing": True,
                },
            },
        )
        profile = resolve_profile(directory=str(tmp_path))
        assert profile.bounds_provenance.basis is Basis.ASSUMED
        assert profile.max_semantic_ms == constants.MAX_SEMANTIC_MS

    def test_every_declaration_names_the_basis_of_both_halves(self, tmp_path: Path) -> None:
        for directory in (tmp_path, None):
            profile = (
                resolve_profile(directory=str(directory)) if directory else unmeasured_profile()
            )
            declaration = profile.declaration()
            assert profile.pool_text_provenance.basis.value in declaration
            assert profile.bounds_provenance.basis.value in declaration
            assert str(profile.max_pool_threads) in declaration


class TestTheProfileRefusesShapesThatCannotBeTrue:
    def test_a_provenance_with_no_detail_explains_nothing(self) -> None:
        with pytest.raises(ValueError):
            Provenance(basis=Basis.ASSUMED, source="AD D.5", detail="")

    def test_the_metadata_rows_fallback_keeps_its_hard_quota_bound(self) -> None:
        good = unmeasured_profile()
        with pytest.raises(ValueError, match="hard-bounded"):
            SemanticProfile(
                pool_text_mode=PoolTextMode.METADATA_ROWS,
                pool_text_provenance=good.pool_text_provenance,
                max_pool_threads=good.max_pool_threads,
                max_pool_messages=METADATA_ROWS_MAX_POOL_MESSAGES + 1,
                max_rerank_pairs=good.max_rerank_pairs,
                max_semantic_ms=good.max_semantic_ms,
                bounds_provenance=good.bounds_provenance,
            )

    def test_a_non_positive_bound_is_refused(self) -> None:
        good = unmeasured_profile()
        with pytest.raises(ValueError, match="max_rerank_pairs"):
            SemanticProfile(
                pool_text_mode=good.pool_text_mode,
                pool_text_provenance=good.pool_text_provenance,
                max_pool_threads=good.max_pool_threads,
                max_pool_messages=good.max_pool_messages,
                max_rerank_pairs=0,
                max_semantic_ms=good.max_semantic_ms,
                bounds_provenance=good.bounds_provenance,
            )


class TestARecordCannotAnswerAQuestionItNeverAsked:
    """PF-2 run 1 returned PASS from a sample that could not exhibit reply-header survival.

    The fix is non-destructive by design: the file on disk is untouched, and the reader
    stops being able to draw the conclusion because the record does not carry a per-question
    verdict. Invalidation by absence rather than by editing evidence.
    """

    def test_an_inconclusive_sub_verdict_is_not_an_answer(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pf2.json",
            _pf2(reply_header_verdict="inconclusive", reply_header_bearing_messages_compared=0),
        )
        # The snippet question was answered, so the pool branch is measured...
        assert resolve_profile(directory=str(tmp_path)).pool_text_provenance.basis is Basis.MEASURED
        # ...and the reply question was not, so it stays on the safe assumed branch.
        needs_full, provenance = reply_chain_needs_full(directory=str(tmp_path))
        assert needs_full is True
        assert provenance.basis is Basis.ASSUMED

    def test_the_two_questions_are_read_independently(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pf2.json",
            _pf2(snippet_verdict="inconclusive", snippet_bearing_messages_compared=0),
        )
        assert resolve_profile(directory=str(tmp_path)).pool_text_provenance.basis is Basis.ASSUMED
        _, provenance = reply_chain_needs_full(directory=str(tmp_path))
        assert provenance.basis is Basis.MEASURED


def test_the_preserved_run_one_record_decides_neither_question(tmp_path: Path) -> None:
    """PF-2 run 1 returned PASS from a sample that could not exhibit reply-header survival.

    Module level rather than in the class above because a replant cites this test by name,
    and the citation checker resolves `file::name` against `def name(` - a class-qualified
    id names nothing it can find.

    The fix under test is non-destructive: the file on disk is untouched, and the reader
    stops being able to draw the conclusion because the record carries no per-question
    verdict. Invalidation by absence rather than by editing evidence.
    """
    raw = Path("preflight-records/raw/PF-2-run1-2026-09-11-UNDER-EXERCISED.json")
    record = json.loads(raw.read_text())
    assert record[VERDICT_KEY] == "pass"
    assert "reply_header_verdict" not in record[FINDINGS_KEY]
    assert "snippet_verdict" not in record[FINDINGS_KEY]

    _write(tmp_path, "pf2.json", record)

    assert resolve_profile(directory=str(tmp_path)).pool_text_provenance.basis is Basis.ASSUMED
    needs_full, provenance = reply_chain_needs_full(directory=str(tmp_path))
    assert needs_full is True
    assert provenance.basis is Basis.ASSUMED
    assert "could not exhibit" in provenance.detail
