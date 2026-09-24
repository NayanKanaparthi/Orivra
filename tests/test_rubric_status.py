"""Gate integrity: a criterion cannot reach PASS without a reviewer (WS-19).

The tool is exercised against synthetic rubrics, so these tests do not depend on the
current state of the real rubric - and one test does read the real rubric, to check the
parser still understands the document it is pointed at.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import rubric_status
from tools.rubric_status import (
    REPO_ROOT,
    REVIEWER_DOMAINS,
    RUBRIC_PATH,
    Status,
    check,
    gate_blockers,
    load,
    main,
    parse_rubric,
    parse_transitions,
    report,
)

SUMMARY = """
## Status summary

| ID | Criterion | Flag | Status |
|---|---|---|---|
| EV-01 | Retrieved-hit containment | M | {ev01} |
| PART-05 | Unexpanded content is visible as stubs | M | {part05} |
| DISC-05 | Disclosure depth is justified | C | NOT TESTED |

**EV-01 · Retrieved-hit containment · M · {ev01}**
*Statement.* ...

**PART-05 · Unexpanded content is visible as stubs · M · {part05}**
*Statement.* ...

**DISC-05 · Disclosure depth is justified · C · NOT TESTED**
*Statement.* ...
"""

TRANSITIONS_HEADER = (
    "| Criterion | Round | Reviewer | From | To | Evidence |\n|---|---|---|---|---|---|\n"
)


def write(tmp_path: Path, *, ev01: str, part05: str, rows: str = "") -> tuple[Path, Path]:
    rubric = tmp_path / "RELEASE_RUBRIC.md"
    rubric.write_text(SUMMARY.format(ev01=ev01, part05=part05), encoding="utf-8")
    transitions = tmp_path / "RUBRIC_TRANSITIONS.md"
    transitions.write_text(TRANSITIONS_HEADER + rows, encoding="utf-8")
    return rubric, transitions


def test_a_pass_without_a_reviewer_transition_is_a_gate_integrity_failure(tmp_path: Path) -> None:
    view = load(*write(tmp_path, ev01="PASS", part05="NOT TESTED"))
    problems = check(view)
    assert any("EV-01 is marked PASS with no reviewer transition" in p for p in problems)


def test_a_pass_with_a_reviewer_transition_is_accepted(tmp_path: Path) -> None:
    row = (
        "| EV-01 | 3 | R-RETR | NOT TESTED | PASS | tests/test_disposition_invariant.py::test_x |\n"
    )
    view = load(*write(tmp_path, ev01="PASS", part05="NOT TESTED", rows=row))
    assert check(view) == []


def test_a_transition_signed_by_a_non_reviewer_is_rejected(tmp_path: Path) -> None:
    row = "| EV-01 | 3 | R-IMPL | NOT TESTED | PASS | I ran the tests |\n"
    view = load(*write(tmp_path, ev01="PASS", part05="NOT TESTED", rows=row))
    assert any("not a reviewer domain" in p for p in check(view))


def test_a_transition_without_reproduction_evidence_is_rejected(tmp_path: Path) -> None:
    row = "| EV-01 | 3 | R-RETR | NOT TESTED | PASS | - |\n"
    view = load(*write(tmp_path, ev01="PASS", part05="NOT TESTED", rows=row))
    assert any("no reproduction evidence" in p for p in check(view))


def test_a_transition_for_an_unknown_criterion_is_rejected(tmp_path: Path) -> None:
    row = "| ZZ-99 | 3 | R-RETR | NOT TESTED | PASS | tests/test_x.py |\n"
    view = load(*write(tmp_path, ev01="NOT TESTED", part05="NOT TESTED", rows=row))
    assert any("unknown criterion" in p for p in check(view))


def test_a_summary_that_disagrees_with_its_criterion_block_is_caught(tmp_path: Path) -> None:
    rubric = tmp_path / "RELEASE_RUBRIC.md"
    text = SUMMARY.format(ev01="PASS", part05="NOT TESTED").replace(
        "**EV-01 · Retrieved-hit containment · M · PASS**",
        "**EV-01 · Retrieved-hit containment · M · FAIL**",
    )
    rubric.write_text(text, encoding="utf-8")
    transitions = tmp_path / "RUBRIC_TRANSITIONS.md"
    transitions.write_text(TRANSITIONS_HEADER, encoding="utf-8")
    problems = check(load(rubric, transitions))
    assert any("status summary says" in p for p in problems)


def test_not_tested_blocks_the_gate_exactly_like_fail(tmp_path: Path) -> None:
    """PROC-01: NOT TESTED is never a soft pass."""
    view = load(*write(tmp_path, ev01="NOT TESTED", part05="FAIL"))
    assert set(gate_blockers(view)) == {"EV-01", "PART-05", "DISC-05"}


def test_a_conditional_criterion_still_blocks_but_an_optional_one_does_not(tmp_path: Path) -> None:
    rubric = tmp_path / "RELEASE_RUBRIC.md"
    text = (
        SUMMARY.format(ev01="PASS", part05="NOT TESTED")
        .replace(
            "| DISC-05 | Disclosure depth is justified | C | NOT TESTED |",
            "| DISC-05 | Disclosure depth is justified | O | NOT TESTED |",
        )
        .replace(
            "**DISC-05 · Disclosure depth is justified · C · NOT TESTED**",
            "**DISC-05 · Disclosure depth is justified · O · NOT TESTED**",
        )
    )
    rubric.write_text(text, encoding="utf-8")
    transitions = tmp_path / "RUBRIC_TRANSITIONS.md"
    transitions.write_text(TRANSITIONS_HEADER, encoding="utf-8")
    assert "DISC-05" not in gate_blockers(load(rubric, transitions))


def test_the_cli_fails_when_a_pass_is_uncertified(tmp_path: Path) -> None:
    rubric, transitions = write(tmp_path, ev01="PASS", part05="NOT TESTED")
    assert main(["--rubric", str(rubric), "--transitions", str(transitions), "--check"]) == 1
    assert main(["--rubric", str(rubric), "--transitions", str(transitions)]) == 0


def test_the_cli_gate_flag_fails_while_criteria_are_untested(tmp_path: Path) -> None:
    rubric, transitions = write(tmp_path, ev01="NOT TESTED", part05="NOT TESTED")
    assert main(["--rubric", str(rubric), "--transitions", str(transitions), "--gate"]) == 1


# --- against the real document -------------------------------------------------------------


def test_the_parser_understands_the_shipped_rubric() -> None:
    summary, detail = parse_rubric(RUBRIC_PATH.read_text(encoding="utf-8"))
    assert len(summary) > 100
    assert set(summary) == set(detail), "every summary row must have a criterion block"
    assert {"EV-01", "PART-07", "SEC-07", "PROC-01"} <= set(summary)


def test_the_shipped_records_are_internally_consistent() -> None:
    view = load()
    assert check(view) == []
    assert "gate-blocking criteria" in report(view)


def test_every_passing_criterion_was_moved_by_a_reviewer_with_evidence() -> None:
    """AGENT_LOOP §1 and §6: only a reviewer domain may set PASS, and it must cite evidence.

    This replaced an earlier assertion that *no* criterion was PASS, which was true only
    while Round 1 was the newest round and became a placeholder the moment reviewers began
    promoting criteria legitimately. The rule it was gesturing at is the one asserted here,
    and it holds for the life of the project rather than for one round.
    """
    view = load()
    passing = {cid for cid, c in view.criteria.items() if c.status is Status.PASS}
    promoted = {t.criterion: t for t in view.transitions if t.to_status is Status.PASS}

    unbacked = sorted(passing - set(promoted))
    assert not unbacked, f"PASS with no transition row: {unbacked}"

    for cid in sorted(passing):
        row = promoted[cid]
        assert row.reviewer in REVIEWER_DOMAINS, (
            f"{cid} promoted by {row.reviewer!r}, which is not an AGENT_LOOP §2.3 reviewer "
            f"domain. The orchestrator recording its own probes as PASS is the "
            f"self-certification §1 forbids."
        )
        assert row.evidence.strip(), f"{cid} promoted with no reproduction evidence"


def test_transition_rows_parse_from_the_shipped_ledger() -> None:
    parsed = parse_transitions(
        TRANSITIONS_HEADER
        + "| EV-01 | 2 | R-DISC | FAIL | PASS | docs/reviews/ROUND_02/R-DISC.md |\n"
    )
    assert parsed[0].reviewer == "R-DISC" and parsed[0].round == 2
    assert parsed[0].to_status is Status.PASS


@pytest.mark.parametrize("bad_row", ["| EV-01 | R-RETR | PASS |\n", "not a table row\n"])
def test_malformed_transition_rows_are_ignored_rather_than_half_parsed(bad_row: str) -> None:
    assert parse_transitions(TRANSITIONS_HEADER + bad_row) == ()


# --- R-ARCH-012: the gate's structural ceiling, stated and demonstrated -------------------


def test_a_row_citing_evidence_that_does_not_exist_passes_the_check(tmp_path: Path) -> None:
    """R-ARCH-012, demonstrated rather than asserted in prose.

    This is not a defect being left open; it is the boundary of what a markdown-parsing
    check can do, and the point of the test is that the boundary is where the docstring
    says it is. A transition citing a test file that does not exist - and a reviewer
    domain that anyone could have typed - is structurally perfect, so `check` reports
    nothing. Only a reader who re-runs the citation can tell.

    If a future version of the tool *did* start verifying citations, this test fails and
    the docstring's ceiling paragraph is corrected with it.
    """
    rubric = tmp_path / "RELEASE_RUBRIC.md"
    rubric.write_text(
        "| ID | Criterion | Flag | Status |\n"
        "|---|---|---|---|\n"
        "| EV-01 | Hit containment | M | PASS |\n"
        "\n"
        "**EV-01 · Hit containment · M · PASS**\n",
        encoding="utf-8",
    )
    transitions = tmp_path / "RUBRIC_TRANSITIONS.md"
    transitions.write_text(
        "| Criterion | Round | Reviewer | From | To | Evidence |\n"
        "|---|---|---|---|---|---|\n"
        "| EV-01 | 5 | R-SEC | NOT TESTED | PASS | "
        "tests/test_nothing_of_the_kind.py::test_invented_by_this_row |\n",
        encoding="utf-8",
    )
    view = load(rubric, transitions)
    assert check(view) == []
    assert not (REPO_ROOT / "tests" / "test_nothing_of_the_kind.py").exists()


def test_the_docstring_states_the_ceiling_it_cannot_check_past() -> None:
    """The standing rule: a mechanism may catch a defect or document that it does not."""
    doc = " ".join((rubric_status.__doc__ or "").split())
    assert "What this check cannot do" in doc
    assert 'not "every PASS is earned"' in doc
    for shape in (
        "nothing here opens the file it names",
        "signature is a string in a markdown cell",
        "does not support the criterion",
    ):
        assert shape in doc, f"the ceiling paragraph no longer names {shape!r}"
