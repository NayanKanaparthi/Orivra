"""PF-4 and PF-4b: local model cost, measured off the mailbox entirely.

Separate from `preflight/` because these need no credential and no Gmail. Folding them into
that runner would make `--run` demand a token to time a CPU.
"""

from __future__ import annotations

from mailweave_harness.modelbench.corpus import pool_rows, rerank_pairs
from mailweave_harness.modelbench.measure import (
    PythonArm,
    analyse,
    measure_python_arm,
    peak_rss_mb,
)
from mailweave_harness.modelbench.spec import PF4, PF4B, POOL_SIZES

__all__ = [
    "PF4",
    "PF4B",
    "POOL_SIZES",
    "PythonArm",
    "analyse",
    "measure_python_arm",
    "peak_rss_mb",
    "pool_rows",
    "rerank_pairs",
]
