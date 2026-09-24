"""Register a new Gmail operator in a scratch tree, exactly as an implementer adding one would.

**This is the acceptance test for A9-A2, and it is a reviewer's method rather than mine.**
R-RETR did not argue that round 18's region predicate was a spelling check; it registered a
new operator with `OperatorKind.LOCATION` - enum member, kind, fidelity table, family values,
the mailbox double - and found that 2,274 tests stayed green while every probe dropped the new
operator, L2 relaxed it away and L3 widened out of it. What generalised was *a new value under
one prefix*, which is not what A9-A2 binds.

So the question this module asks is the same one, of this round's code: **register a
region-selecting operator and a filtering one, and are both covered without editing a test?**
"Registration" means writing the operator down everywhere an operator is written down, which
includes three files under `tests/` - the fidelity table, the family values and the double's
implemented set. Those are registration sites, not oracles: they say *what the operator is*,
not *what the code should do with it*. No assertion, no expected value and no population is
edited by anything here, which is the property under test.

The scratch-tree discipline is `tests/fixtures/replants.py`'s and for the same reason: the venv
installs `mailweave` as an editable `.pth`, so a subprocess with a merely-prepended
`PYTHONPATH` can import the working tree and report a green run over code it never changed.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tests.fixtures.replants import (
    _environment,
    _run,
    assert_imports_resolve_into_the_scratch_tree,
    make_scratch_tree,
)


@dataclass(frozen=True)
class Registration:
    """One operator, written down everywhere an operator is written down."""

    member: str
    #: The `name:` an author types.
    spelling: str
    #: The `OperatorKind` member it is registered under - the fact this round makes load-bearing.
    kind: str
    #: A value for it, used by the fidelity table, the family sweep and the probes below.
    value: str


#: A region-selecting operator nobody has added, and a filtering one as the control. The
#: control matters: R-RETR's filtering operator was *already* covered by round 18, so a fix
#: that made everything a region would pass the first half of this test and fail the point of
#: it.
SCOPE_OPERATOR = Registration(member="MAILBOX", spelling="mailbox", kind="REGION", value="spam")
FILTER_OPERATOR = Registration(member="PRIORITY", spelling="priority", kind="TEXT", value="high")


def _edit(path: Path, anchor: str, replacement: str) -> None:
    text = path.read_text()
    matches = text.count(anchor)
    if matches != 1:
        raise AssertionError(f"{path.name}: anchor matched {matches} times, expected 1")
    path.write_text(text.replace(anchor, replacement))


def register(scratch: Path, operator: Registration) -> None:
    """Write `operator` into every place this repository registers an operator."""
    operators = scratch / "server/src/mailweave/query/operators.py"
    fidelity = scratch / "tests/test_query_analysis.py"
    ladder = scratch / "tests/test_lexical_ladder.py"
    double = scratch / "tests/fixtures/mailbox.py"

    _edit(
        operators,
        '    RFC822MSGID = "rfc822msgid"',
        f'    RFC822MSGID = "rfc822msgid"\n    {operator.member} = "{operator.spelling}"',
    )
    _edit(
        operators,
        "        OperatorName.RFC822MSGID: OperatorKind.IDENTITY,",
        "        OperatorName.RFC822MSGID: OperatorKind.IDENTITY,\n"
        f"        OperatorName.{operator.member}: OperatorKind.{operator.kind},",
    )
    _edit(
        fidelity,
        '    OperatorName.RFC822MSGID: ("rfc822msgid:<a1@mail.invalid>", "<a1@mail.invalid>"),',
        '    OperatorName.RFC822MSGID: ("rfc822msgid:<a1@mail.invalid>", "<a1@mail.invalid>"),\n'
        f"    OperatorName.{operator.member}: "
        f'("{operator.spelling}:{operator.value}", "{operator.value}"),',
    )
    _edit(fidelity, "    assert len(FIDELITY_TABLE) == 21", "    assert len(FIDELITY_TABLE) == 22")
    _edit(
        ladder,
        '    "rfc822msgid": "<a1@mail.invalid>",',
        f'    "rfc822msgid": "<a1@mail.invalid>",\n    "{operator.spelling}": "{operator.value}",',
    )
    _edit(double, '        "is",', f'        "is",\n        "{operator.spelling}",')


#: What a newly registered **region-selecting** operator must do, asked of the plan layer in
#: the scratch tree. Written as a script because it has to run in a subprocess that imports the
#: planted tree; every assertion is about the new operator, which no test in the tree names.
SCOPE_PROBE = """
import os, sys
import mailweave, tests
here = os.path.realpath({scratch!r})
assert os.path.realpath(mailweave.__file__).startswith(here), mailweave.__file__
assert os.path.realpath(tests.__file__).startswith(here), tests.__file__
assert not os.path.realpath(mailweave.__file__).startswith("/root/mailweave/"), mailweave.__file__
assert not os.path.realpath(tests.__file__).startswith("/root/mailweave/"), tests.__file__

from datetime import UTC, datetime
from zoneinfo import ZoneInfo
from mailweave.query import analyse, declares_the_search_region
from mailweave.retrieval.ladder import plan_ladder

NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)
ZONE = ZoneInfo("UTC")
fragment = "-{spelling}:{value}"

assert declares_the_search_region(fragment) is True, "the new operator is not read as a region"
assert declares_the_search_region("{spelling}:{value}") is True

for body in ("quillon", "quillon vellichor", "from:ana@team.example quillon"):
    query = fragment + " " + body
    probes = plan_ladder(analyse(query, now=NOW, zone=ZONE))
    assert probes, query
    for probe in probes:
        assert fragment in probe.query, (query, probe.rung, probe.query)
        assert probe.include_spam_trash is False, (query, probe.rung, probe.query)
        assert "in:anywhere" not in probe.query, (query, probe.rung, probe.query)
print("SCOPE OPERATOR COVERED", mailweave.__file__)
"""

#: And what a newly registered **filtering** operator must do. The control R-RETR ran, kept so
#: that "everything is a region" cannot pass this file.
FILTER_PROBE = """
import os, sys
import mailweave, tests
here = os.path.realpath({scratch!r})
assert os.path.realpath(mailweave.__file__).startswith(here), mailweave.__file__
assert os.path.realpath(tests.__file__).startswith(here), tests.__file__
assert not os.path.realpath(mailweave.__file__).startswith("/root/mailweave/"), mailweave.__file__

from datetime import UTC, datetime
from zoneinfo import ZoneInfo
from mailweave.query import analyse, declares_the_search_region
from mailweave.retrieval.ladder import RelaxationRung, plan_ladder

NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)
ZONE = ZoneInfo("UTC")
fragment = "{spelling}:{value}"

assert declares_the_search_region(fragment) is False, "a filter is read as a region"
parsed = analyse(fragment + " quillon", now=NOW, zone=ZONE)
dropped = {{name for probe in RelaxationRung().plan(parsed) for name in probe.dropped}}
assert "{spelling}" in dropped, dropped
units = [unit.label for unit in parsed.decomposition_units]
assert "{spelling}" in units, units
widened = [p.query for p in plan_ladder(parsed) if "in:anywhere" in p.query]
assert widened, "a query naming no region is still broadened"
print("FILTER OPERATOR COVERED", mailweave.__file__)
"""


def probe(scratch: Path, source: str, operator: Registration) -> str:
    """Run one probe script inside the scratch tree, raising with its output on failure."""
    script = source.format(scratch=str(scratch), spelling=operator.spelling, value=operator.value)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=scratch,
        env=_environment(scratch),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"{operator.spelling}: {result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def register_and_check(
    destination: Path, operator: Registration, source: str, tests_to_run: list[str]
) -> tuple[str, str]:
    """Register `operator` into a fresh scratch tree, probe it, and run `tests_to_run` there.

    Returns the probe's own output and the pytest summary line, so a caller can print both.
    """
    scratch = make_scratch_tree(destination)
    assert_imports_resolve_into_the_scratch_tree(scratch)
    register(scratch, operator)
    behaviour = probe(scratch, source, operator)
    result = _run(scratch, ["-m", "not network and not replant", *tests_to_run], timeout=1800)
    if result.returncode != 0:
        tail = "\n".join(result.stdout.strip().splitlines()[-25:])
        raise AssertionError(f"registering {operator.spelling!r} broke the suite:\n{tail}")
    summary = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    return behaviour, summary
