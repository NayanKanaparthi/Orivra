"""PF-10's analysis half: the part where a mistake is invisible.

The observations PF-10 needs - real mail arriving in two real mailboxes - cannot be
manufactured, and none of this module produces them. What it does is hold the pre-registered
rules that turn observations into a verdict, so those rules exist *before* the numbers do.
That ordering is the whole property a pre-registered threshold is supposed to have, and it is
also the only defence against the failure this project keeps finding: a check that passes for
a reason that does not establish what it claims.
"""

from __future__ import annotations

from mailweave_harness.freshness.analysis import (
    FSL_SECONDS,
    STRATA,
    FreshnessVerdict,
    Observation,
    PoolingProhibited,
    Stratum,
    analyse_freshness,
    p90,
)

__all__ = [
    "FSL_SECONDS",
    "STRATA",
    "FreshnessVerdict",
    "Observation",
    "PoolingProhibited",
    "Stratum",
    "analyse_freshness",
    "p90",
]
