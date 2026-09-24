"""CI guards. Each guard is a pure function over a source tree returning violations.

Being pure functions rather than shell greps, each one is unit-tested against a
deliberately planted violation, which is what the implementation plan requires of the
gates: "CI gates fail on a deliberately planted violation of each sweep".
"""

from tools.guards.sweeps import (
    GUARDS,
    Violation,
    forbidden_imports,
    generative_client_sweep,
    gmail_path_sweep,
    ground_truth_sweep,
    listening_socket_sweep,
    run_all,
    scope_literal_sweep,
    unaudited_disk_write_sweep,
)

__all__ = [
    "GUARDS",
    "Violation",
    "forbidden_imports",
    "generative_client_sweep",
    "gmail_path_sweep",
    "ground_truth_sweep",
    "listening_socket_sweep",
    "run_all",
    "scope_literal_sweep",
    "unaudited_disk_write_sweep",
]
