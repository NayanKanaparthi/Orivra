"""The command path, tested offline, because it is the thing that gets handed over.

A campaign command that is only checked by being read is a command that fails on the operator's
machine. `--dry-run` runs the whole pipeline against the dummy corpus - four MailWeave arms,
both floor budgets, traces written and read back, every comparison rendered and every clause
computed - and the tests here assert the properties that make that exercise worth anything:

  * it exits **0** and needs no credential, no mailbox and no network;
  * it goes through the **same presentation** the live run uses, so what it proves is what will
    run - the live path differs only in `runtime.start` and in reading case files from disk;
  * it says, in its own output, that none of its numbers are evidence about retrieval.

What it cannot establish is the two things it does not do, and no test here pretends otherwise.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from mailweave_harness.evaluation import __main__ as cli


def test_the_dry_run_executes_the_whole_path_offline_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--dry-run", "--traces", str(tmp_path / "traces")]) == 0
    out = capsys.readouterr().out
    for arm in ("full", "sem-off", "fixed-window", "sem-off+fixed-window"):
        assert f"arm {arm}" in out, arm
    for budget in ("primitive-floor-tight", "primitive-floor-generous"):
        assert budget in out, budget
    for hypothesis in ("[H1]", "[H2]", "[H3]"):
        assert hypothesis in out, hypothesis


def test_the_dry_run_disclaims_its_own_numbers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run on sentinel-token queries that read as a result would be worse than no run."""
    cli.main(["--dry-run", "--traces", str(tmp_path / "traces")])
    out = capsys.readouterr().out
    assert "Nothing above is evidence about retrieval" in out
    assert "NOT_EVALUABLE" in out


def test_the_dry_run_writes_one_trace_tree_per_arm(tmp_path: Path) -> None:
    """Two arms sharing a root would interleave, and `cut_loss` would read the wrong rungs."""
    traces = tmp_path / "traces"
    cli.main(["--dry-run", "--traces", str(traces)])
    written = {path.parents[2].name for path in traces.rglob("trace.jsonl")}
    assert {"full", "sem-off", "fixed-window", "sem-off+fixed-window"} <= written


def test_the_live_run_and_the_dry_run_share_their_presentation() -> None:
    """The dry run's claim is "this path executes"; that is only worth making if it is the
    same path. Both entry points must reach the report and the verdicts through `_present`."""
    assert "_present(" in inspect.getsource(cli._run)
    assert "_present(" in inspect.getsource(cli._dry_run)
    for name in ("report.render", "evaluate("):
        assert name not in inspect.getsource(cli._dry_run), name


def test_the_schema_prints_the_case_interface_without_touching_anything(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main([]) == 0
    assert "case-file interface" in capsys.readouterr().out


def test_a_run_without_its_inputs_names_every_missing_one_at_once() -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["--run"])
    message = str(caught.value)
    for flag in ("--cases", "--manifest", "--verification"):
        assert flag in message, flag


def test_validate_refuses_a_case_file_written_against_another_corpus(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.fixtures.eval_dummy import dummy_case_file, dummy_manifest

    manifest = dummy_manifest()
    cases = tmp_path / "cases.json"
    cases.write_text(dummy_case_file(manifest).model_dump_json(), encoding="utf-8")
    other = tmp_path / "manifest.json"
    other.write_text(dummy_manifest(seed=7).model_dump_json(), encoding="utf-8")
    assert cli.main(["--validate", str(cases), "--manifest", str(other)]) == 2
    assert "REFUSED" in capsys.readouterr().out


def test_the_out_record_carries_the_arms_the_cases_and_the_rendered_report(
    tmp_path: Path,
) -> None:
    """`--out` is the artifact a reviewer re-reads, so it must stand alone."""
    from mailweave_harness.evaluation import resolve_against, run_all
    from tests.fixtures.eval_dummy import dummy_arms, dummy_case_file, dummy_manifest, mailbox_of

    manifest = dummy_manifest()
    box, verification = mailbox_of(manifest)
    resolved = [
        resolve_against(case, manifest=manifest, report=verification)
        for case in dummy_case_file(manifest).cases
    ]
    runs = list(run_all(dummy_arms(manifest, box, traces=tmp_path / "t"), resolved))
    out = tmp_path / "record.json"
    cli._present(runs, resolved, out=out)
    record = json.loads(out.read_text())
    assert {"cases", "runs", "arms", "per_case", "report", "recoverability", "hypotheses"} <= set(
        record
    )
    assert any("does_not_isolate" in one for one in record["arms"])
    assert any("pool_source" in one for one in record["per_case"])
    assert any("isolates" in text for text in record["report"].values())


def test_live_check_needs_the_corpus_but_not_the_cases() -> None:
    """Its whole point is to exercise the live path **before** the cases exist."""
    with pytest.raises(SystemExit) as caught:
        cli.main(["--live-check"])
    message = str(caught.value)
    assert "--manifest" in message and "--verification" in message
    assert "--cases" not in message


def test_the_live_check_case_file_is_built_from_the_corpus_not_loaded_from_disk() -> None:
    """Nobody hands it cases, so nobody can hand it the wrong ones, and it cannot be mistaken
    for the campaign."""
    import inspect

    source = inspect.getsource(cli._run)
    assert "sentinel_case_file(manifest)" in source
    assert "if args.live_check:" in source


def test_the_live_check_writes_no_record(  # the campaign's --out is for the campaign
) -> None:
    import inspect

    assert "out=None if args.live_check else args.out" in inspect.getsource(cli._run)


def test_every_self_test_query_is_a_sentinel_with_exactly_one_owner() -> None:
    """The property that makes these cases incapable of distinguishing arms, asserted rather
    than assumed: a sentinel occurs in one message and nowhere else in the corpus."""
    from mailweave_harness.evaluation.selftest import sentinel_case_file
    from tests.fixtures.eval_dummy import dummy_manifest

    manifest = dummy_manifest()
    owners = manifest.answer_key.sentinel_owner
    built = sentinel_case_file(manifest)
    sentinel_cases = [one for one in built.cases if one.query in owners]
    assert sentinel_cases, "the file is built from the sentinels"
    for case in sentinel_cases:
        bodies = [one for one in manifest.messages if case.query in one.body]
        assert len(bodies) == 1, case.query
        assert bodies[0].rfc822_message_id == owners[case.query]


def test_the_self_test_file_says_in_every_case_that_it_proves_nothing_about_retrieval() -> None:
    """A number from this file that got read as a result would be worse than no number."""
    from mailweave_harness.evaluation.selftest import sentinel_case_file
    from tests.fixtures.eval_dummy import dummy_manifest

    for case in sentinel_case_file(dummy_manifest()).cases:
        assert "SELF TEST" in case.expected_behavior.notes, case.case_id


def test_the_dummy_fixture_and_the_live_check_build_the_same_thing() -> None:
    """One construction. Two copies of it is the shape where the second stops being updated.

    The fixture now *chooses* two anchors that the builder cannot: whether a message is
    surfaced-and-not-disclosed until expansion carries it, and whether a hit fills a window,
    are properties of the mailbox and the disclosure ceiling rather than of the corpus. So the
    contract this test holds is the same one, restated exactly: given the same anchors, the
    fixture and the live check produce the identical file, and the fixture builds nothing of
    its own.
    """
    import inspect

    from mailweave_harness.evaluation.selftest import sentinel_case_file
    from tests.fixtures import eval_dummy
    from tests.fixtures.eval_dummy import dummy_case_file, dummy_manifest

    manifest = dummy_manifest()
    escalation, window = eval_dummy._probe_anchors(manifest)
    assert escalation, "the fixture found no message with the surfaced-then-carried shape"
    # `window` is allowed to be None. Baseline F fills no window anywhere in the current
    # corpus - conversations are long enough and their messages carry enough text that the
    # ladder never discloses one whole, so the fill stage is not reached. That is recorded as
    # an observation in the findings ledger, and `test_baseline_f_executes_and_its_rows_say_why
    # _they_are_there` asserts the rendering directly instead. What this test holds is the
    # one-construction contract, which does not depend on an anchor being found.
    assert (
        dummy_case_file(manifest).model_dump_json()
        == sentinel_case_file(
            manifest, escalation=escalation, window=window
        ).model_dump_json()
    )
    source = inspect.getsource(eval_dummy.dummy_case_file)
    assert "sentinel_case_file(" in source
    assert "cases.append" not in inspect.getsource(eval_dummy)
