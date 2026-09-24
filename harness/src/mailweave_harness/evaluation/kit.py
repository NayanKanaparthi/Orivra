"""The case-authoring kit: everything an independent author needs, and nothing from the engine.

**Exported rather than maintained.** The two schema modules in the kit are copied from the
repository at export time, byte for byte, and stamped with the commit that produced them. A
hand-maintained second copy of the case schema would be this project's own recurring defect -
one shape checked in two places, the second copy the one nobody updates - committed in the
artifact whose entire job is that the author's refusals are the scoring run's refusals.
`tests/test_authoring_kit.py` exports a kit into a temp directory, imports it as the author
would, and validates a case file through it, so a drift that breaks the kit fails the suite
rather than the handoff.

**What the kit deliberately does not contain.** No retrieval code, no ladder, no ranking, no
disclosure selector, no arms - nothing about how MailWeave answers a query. The author writes
cases against the corpus and the plan, not against the implementation, because a case written
with the implementation in view is a case that tests what the implementation already does.

**What it does not contain for the other reason.** It carries no queries and no answers. Those
are the author's to write, and they must not come back into this repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Final

from mailweave_harness.evaluation.cases import FAMILY_LABELS, REGISTERED_N, SWEEP_POSITIONS

#: The two modules the validator needs, as paths relative to `harness/src`. `cases.py` imports
#: `Manifest` and `SeededMessage` from `manifest.py` and, at runtime, nothing else - which is
#: why `VerificationReport` moved under `TYPE_CHECKING`: the mailbox half of the join is not the
#: author's half, and a kit that dragged in the seeding substrate would drag in the credential
#: handling behind it.
SCHEMA_MODULES: Final[tuple[tuple[str, str], ...]] = (
    ("mailweave_harness/seed/manifest.py", "kit_schema/manifest.py"),
    ("mailweave_harness/evaluation/cases.py", "kit_schema/cases.py"),
)


#: The kit's own text and its checker, kept as files rather than as string literals. A markdown
#: document inside a Python string is a document nobody proofreads, and a script inside one is a
#: script no editor will show you.
TEMPLATES: Final[Path] = Path(__file__).parent


def _template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def _commit(root: Path) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - git absent
        return "unknown"
    return done.stdout.strip() or "unknown"


def families_table() -> str:
    """The registered families, their labels and their per-seed counts, read from the code."""
    lines = [
        "| Label | family | cases per seed |",
        "|---|---|---|",
    ]
    for family, label in sorted(FAMILY_LABELS.items(), key=lambda one: (len(one[1]), one[1])):
        registered = REGISTERED_N.get(family)
        lines.append(f"| {label} | `{family}` | {registered if registered else '-'} |")
    total = sum(REGISTERED_N.values())
    lines.append("")
    lines.append(f"**{total} cases in total per seed.** F3's figure is the position sweep's:")
    lines.append(
        f"12 templates at the {len(SWEEP_POSITIONS)} normative positions "
        f"{', '.join(str(one) for one in SWEEP_POSITIONS)} (percentages of thread length, "
        "EP §4.4)."
    )
    return "\n".join(lines)


def export(destination: Path, *, source_root: Path, schema: str) -> tuple[Path, ...]:
    """Write the kit. Returns every path written, so a caller can list what it handed over."""
    written: list[Path] = []
    package = destination / "kit_schema"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text(
        '"""The repository\'s own case schema, copied at export time. Do not edit."""\n',
        encoding="utf-8",
    )
    written.append(package / "__init__.py")
    for relative, target in SCHEMA_MODULES:
        body = (source_root / relative).read_text(encoding="utf-8")
        # The kit is two files, so the package path they import each other by is the kit's.
        body = body.replace("from mailweave_harness.seed.manifest import", "from .manifest import")
        out = destination / target
        out.write_text(body, encoding="utf-8")
        written.append(out)
    registered = (
        "{\n"
        + "".join(f"    {family!r}: {count},\n" for family, count in sorted(REGISTERED_N.items()))
        + "}"
    )
    (destination / "validate.py").write_text(
        _template("kit_validate.py.txt").replace("__REGISTERED__", registered), encoding="utf-8"
    )
    written.append(destination / "validate.py")
    (destination / "CASE_FILE_INTERFACE.txt").write_text(schema + "\n", encoding="utf-8")
    written.append(destination / "CASE_FILE_INTERFACE.txt")
    (destination / "README.md").write_text(_template("kit_readme.md"), encoding="utf-8")
    written.append(destination / "README.md")
    (destination / "FAMILIES.md").write_text(
        "# The registered families\n\nTaken from `EVALUATION_PLAN.md` §4.3 and §4.7, and printed "
        "here from the same table the\nscoring run reads. A clause answered by fewer cases than "
        "the plan registered reports\n`NOT_EVALUABLE` rather than a verdict.\n\n"
        + families_table()
        + "\n",
        encoding="utf-8",
    )
    written.append(destination / "FAMILIES.md")
    (destination / "HYPOTHESES.md").write_text(_template("kit_hypotheses.md"), encoding="utf-8")
    written.append(destination / "HYPOTHESES.md")
    (destination / "VERSION.txt").write_text(
        f"exported from commit {_commit(source_root.parent.parent)}\n"
        "kit_schema/*.py are that commit's files, copied byte for byte\n",
        encoding="utf-8",
    )
    written.append(destination / "VERSION.txt")
    return tuple(written)


__all__ = ["SCHEMA_MODULES", "export", "families_table"]
