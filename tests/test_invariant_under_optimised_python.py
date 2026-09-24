"""The invariant must hold in an optimised build.

AD A.7a writes the rule as `assert H == disclosed ∪ withheld`. A literal `assert` is
removed by `python -O`, which would silently disable the one check the architecture calls
the structural fix. The implementation therefore raises explicitly; this test proves it,
by running the failing case in a real `-O` subprocess rather than by reading the source.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

PROGRAM = textwrap.dedent(
    """
    from mailweave.envelope import DispositionLedger, FetchedIds, ObservedEndpoint, RungId
    from mailweave.errors import DispositionInvariantError

    ledger = DispositionLedger()
    ledger.record_list_page(
        FetchedIds(
            ids=["kept", "lost"], endpoint=ObservedEndpoint.MESSAGES_LIST, page_size=100
        ),
        rung=RungId.L1,
        query="q",
    )
    try:
        ledger.certify(disclosed=["kept"])
    except DispositionInvariantError as failure:
        assert_stripped = __debug__ is False
        print("RAISED", "lost" in str(failure), assert_stripped)
    else:
        print("SILENT")
    """
)


def test_a_forgotten_hit_still_fails_under_python_O() -> None:
    result = subprocess.run(
        [sys.executable, "-O", "-c", PROGRAM],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "RAISED True True", result.stderr


def test_the_same_case_fails_in_a_normal_build_too() -> None:
    result = subprocess.run(
        [sys.executable, "-c", PROGRAM],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "RAISED True False", result.stderr
