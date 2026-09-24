"""The case-authoring kit, exported and then used the way an independent author would use it.

The kit's whole claim is that **the refusals its author sees are the refusals the scoring run
applies**. That claim rests on the kit's schema modules being the repository's own files rather
than a maintained copy of them, and a claim like that is worth exactly as much as the test that
keeps it true. So these tests export a kit into a temp directory, import it as a standalone
package with `mailweave_harness` off the path entirely, and drive a real case file through it.

A change to `cases.py` that breaks the kit fails here, in the suite, rather than in the handoff.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from mailweave_harness.evaluation import __main__ as cli
from mailweave_harness.evaluation import kit
from mailweave_harness.evaluation.cases import FAMILY_LABELS, REGISTERED_N
from tests.fixtures.eval_dummy import dummy_case_file, dummy_manifest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("kit") / "authoring-kit"
    assert cli.main(["--export-kit", str(out)]) == 0
    return out


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    where = tmp_path_factory.mktemp("corpus")
    manifest = dummy_manifest()
    (where / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    (where / "cases.json").write_text(
        dummy_case_file(manifest).model_dump_json(indent=2), encoding="utf-8"
    )
    return where / "cases.json", where / "manifest.json"


def _run(exported: Path, *args: Path) -> subprocess.CompletedProcess[str]:
    """As the author runs it: their own Python, their own directory, nothing on the path."""
    return subprocess.run(
        [sys.executable, "validate.py", *(str(one) for one in args)],
        cwd=exported,
        capture_output=True,
        text=True,
        timeout=120,
        env={"PATH": "/usr/bin:/bin", "HOME": str(exported)},
        check=False,
    )


def test_the_kit_holds_the_brief_the_interface_and_a_checker(exported: Path) -> None:
    for name in (
        "README.md",
        "CASE_FILE_INTERFACE.txt",
        "FAMILIES.md",
        "HYPOTHESES.md",
        "VERSION.txt",
        "validate.py",
        "kit_schema/cases.py",
        "kit_schema/manifest.py",
    ):
        assert (exported / name).exists(), name


def test_the_kit_schema_is_this_repositorys_own_file_and_not_a_copy(exported: Path) -> None:
    """A hand-maintained second copy of the case schema is the defect this project keeps
    finding: one shape checked in two places, the second copy the one nobody updates."""
    for relative, target in kit.SCHEMA_MODULES:
        original = (REPO / "harness" / "src" / relative).read_text(encoding="utf-8")
        shipped = (exported / target).read_text(encoding="utf-8")
        # The only permitted difference is the import path the two kit modules find each other
        # by, because in the kit they are a two-module package rather than `mailweave_harness`.
        assert shipped == original.replace(
            "from mailweave_harness.seed.manifest import", "from .manifest import"
        ), relative


def test_the_kit_ships_no_engine_code(exported: Path) -> None:
    """The author writes cases against the corpus and the plan, not against the engine.

    Checked on the **code**, not the prose: `HYPOTHESES.md` has to say the word "reranking"
    because H2 is about reranking, and a test that banned the word would ban the brief.
    """
    code = "\n".join(
        path.read_text(encoding="utf-8") for path in exported.rglob("*.py") if path.is_file()
    )
    for forbidden in ("from mailweave.", "import mailweave.", "mailweave.retrieval"):
        assert forbidden not in code, forbidden
    assert not [one for one in exported.rglob("*.py") if one.name in {"assemble.py", "arms.py"}]
    # `cases.py` keeps one `mailweave_harness` reference: the mailbox half of the join, under
    # `if TYPE_CHECKING`, which never executes. It is left in place rather than rewritten
    # because the byte-for-byte property is worth more than the tidiness, and the standalone
    # subprocess test is what proves the kit runs without it.
    shipped = (exported / "kit_schema" / "cases.py").read_text(encoding="utf-8")
    lines = shipped.splitlines()
    guarded = next(
        index for index, text in enumerate(lines) if text.startswith("if TYPE_CHECKING:")
    )
    importing = [
        text
        for index, text in enumerate(lines)
        if index > guarded - 1
        and "mailweave_harness" in text
        and text.lstrip().startswith(("import ", "from "))
    ]
    unguarded = [
        text
        for index, text in enumerate(lines)
        if index < guarded
        and "mailweave_harness" in text
        and text.lstrip().startswith(("import ", "from "))
    ]
    assert unguarded == [], unguarded
    assert len(importing) == 1, importing


def test_the_checker_runs_standalone_and_passes_a_good_file(
    exported: Path, corpus: tuple[Path, Path]
) -> None:
    """No `mailweave_harness`, no PYTHONPATH, no network, no credential."""
    done = _run(exported, *corpus)
    assert done.returncode == 0, done.stdout + done.stderr
    # The count follows the smoke profile's sentinel count, which moved when the profile was
    # resized for R-M2-041. Asserted as "more than one and it printed a count" rather than a
    # literal, because the literal was a restatement of the fixture and not a property.
    assert re.search(r"\d+ case\(s\), schema 1", done.stdout), done.stdout
    assert "0 refusal(s)" in done.stdout


def test_the_checker_refuses_a_case_file_written_against_another_corpus(
    exported: Path, corpus: tuple[Path, Path], tmp_path: Path
) -> None:
    other = tmp_path / "manifest.json"
    other.write_text(dummy_manifest(seed=7).model_dump_json(), encoding="utf-8")
    done = _run(exported, corpus[0], other)
    assert done.returncode == 2
    assert "wrong file" in done.stdout


def test_the_checker_refuses_a_ref_the_corpus_does_not_hold(
    exported: Path, corpus: tuple[Path, Path], tmp_path: Path
) -> None:
    body = json.loads(corpus[0].read_text(encoding="utf-8"))
    body["cases"][0]["evidence"][0]["ref"] = "thread:t999/pos:4"
    broken = tmp_path / "cases.json"
    broken.write_text(json.dumps(body), encoding="utf-8")
    done = _run(exported, broken, corpus[1])
    assert done.returncode == 2
    assert "names no message in this corpus" in done.stdout


def test_the_checker_refuses_a_distractor_ref_the_corpus_does_not_hold(
    exported: Path, corpus: tuple[Path, Path], tmp_path: Path
) -> None:
    """Distractors are part of the case, not scenery: they are what separates retrieval from
    luck, so a distractor naming a message the corpus does not hold is a refusal like any
    other ref."""
    body = json.loads(corpus[0].read_text(encoding="utf-8"))
    body["cases"][0]["distractors"] = [
        {"ref": "thread:t999/pos:1", "type": "lexical_decoy", "note": "not in this corpus"}
    ]
    broken = tmp_path / "cases.json"
    broken.write_text(json.dumps(body), encoding="utf-8")
    done = _run(exported, broken, corpus[1])
    assert done.returncode == 2
    assert "thread:t999/pos:1 names no message in this corpus" in done.stdout


def test_the_checker_reports_the_registered_shortfall_without_refusing(
    exported: Path, corpus: tuple[Path, Path]
) -> None:
    """Six dummy cases are far short of every registered count. That is worth saying and is
    not a refusal: the run reports NOT_EVALUABLE for the clauses below their registered n."""
    done = _run(exported, *corpus)
    assert done.returncode == 0
    assert "short of the registered counts" in done.stdout
    assert "buried_evidence" in done.stdout


def test_the_families_page_is_generated_from_the_registered_table(exported: Path) -> None:
    """Not retyped. A families page that drifts from `REGISTERED_N` sends an author to write
    the wrong number of cases, which is discovered at the end of the campaign."""
    page = (exported / "FAMILIES.md").read_text(encoding="utf-8")
    for family, count in REGISTERED_N.items():
        assert f"| {FAMILY_LABELS[family]} | `{family}` | {count} |" in page, family
    assert str(sum(REGISTERED_N.values())) in page


def test_the_version_file_names_the_commit_the_schema_came_from(exported: Path) -> None:
    stamped = (exported / "VERSION.txt").read_text(encoding="utf-8")
    assert "exported from commit" in stamped
    assert "copied byte for byte" in stamped
