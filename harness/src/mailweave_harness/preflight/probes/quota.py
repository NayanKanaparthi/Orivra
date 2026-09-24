"""PF-3 - what a Gmail call actually costs, against the published table (AD A.5, A.5c, F).

No Gmail response carries a quota figure, so the only way to measure a unit cost is
indirectly: drive one endpoint at a controlled rate until the per-minute budget refuses, and
divide the published per-minute budget by the number of calls that fitted. That inference
rests on assumptions the probe states rather than hides - one bucket, one project, nothing
else consuming it (PF-16's exclusive window) - and it is why the primary falsifier is the
**rank order**, which survives all three assumptions being slightly wrong.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mailweave.gmail import (
    PUBLISHED_PER_MINUTE_UNITS,
    PUBLISHED_QUOTA_UNITS,
    RATE_CALIBRATION,
    GmailEndpoint,
    GmailFault,
    GmailRateLimited,
)
from mailweave_harness.preflight.spec import ProbeResult, ProbeSpec, Verdict

SPEC = ProbeSpec(
    id="PF-3-quota-units",
    title="Quota units actually charged per endpoint",
    measures=(
        "calls of one endpoint issued back to back until the per-minute budget refuses, per "
        "endpoint, with the status and machine-readable reason of the refusal recorded"
    ),
    validates=(
        "AD A.5's rate table (5 / 20 / 40 / 2 u), which every cost figure in the project is "
        "a multiplication of, and A.5c's governor budget of 6,000 u/min"
    ),
    falsified_when=(
        "the inferred per-call costs are not in the published rank order "
        "(history.list < messages.list < messages.get < threads.get), or any endpoint's "
        "inferred cost differs from its published figure by a factor of two or more"
    ),
    changes_if_it_fails=(
        "AD A.5c's stated consequence executes: max_hit_threads 12 -> 6, max_source_threads "
        "4 -> 2, max_pool_threads 25 -> 12, max_quota_units halved and re-derived rather than "
        "asserted, the reduced pool bound declared in every semantic response, and the "
        "governor's per-minute budget re-set from the measurement. Every published quota "
        "number then carries this run's calibration date (AD A.11)"
    ),
    credential="read",
    quota_budget_units=PUBLISHED_PER_MINUTE_UNITS * 4,
    pre_registered_rules=(
        "factor-of-two agreement bound, chosen before the run; AD A.5c's own consequence "
        "table is written against a '~4x tighter reality', so two is the tighter trigger",
        "rank order is the primary falsifier because it survives the inference's assumptions "
        "(one bucket, one project, an exclusive window) being approximately rather than "
        "exactly true",
    ),
)


@dataclass(frozen=True)
class EndpointObservation:
    """One endpoint driven to refusal."""

    endpoint: GmailEndpoint
    calls_completed: int
    elapsed_s: float
    refused: bool
    refusal_status: int | None = None
    refusal_reason: str | None = None


@dataclass
class QuotaObservation:
    per_endpoint: list[EndpointObservation] = field(default_factory=list)


def measure_endpoint(
    endpoint: GmailEndpoint, make_call: Callable[[], None], *, max_calls: int
) -> EndpointObservation:
    """Issue calls until one is rate limited or `max_calls` is reached.

    `make_call` is a zero-argument callable that performs exactly one call of `endpoint`, so
    this loop is the same code whether the call is real or a test double - which is how the
    measurement loop itself gets tested with no network.

    Any other `GmailFault` stops the loop and is reported as *not refused*: an endpoint that
    failed for another reason has measured nothing, and reporting it as a budget observation
    would put a fabricated number into a calibration.
    """
    started = time.monotonic()
    completed = 0
    while completed < max_calls:
        try:
            make_call()
        except GmailRateLimited as limited:
            return EndpointObservation(
                endpoint=endpoint,
                calls_completed=completed,
                elapsed_s=time.monotonic() - started,
                refused=True,
                refusal_status=limited.status,
                refusal_reason=limited.reason,
            )
        except GmailFault:
            break
        completed += 1
    return EndpointObservation(
        endpoint=endpoint,
        calls_completed=completed,
        elapsed_s=time.monotonic() - started,
        refused=False,
    )


def inferred_units(observation: EndpointObservation) -> float | None:
    """Published per-minute budget divided by the calls that fitted inside one minute.

    `None` when the endpoint was never refused: without a refusal there is no bucket edge to
    divide by, and an unrefused run bounds the cost from above at best.
    """
    if not observation.refused or observation.calls_completed <= 0:
        return None
    return PUBLISHED_PER_MINUTE_UNITS / observation.calls_completed


PUBLISHED_RANK = (
    GmailEndpoint.HISTORY_LIST,
    GmailEndpoint.MESSAGES_LIST,
    GmailEndpoint.MESSAGES_GET,
    GmailEndpoint.THREADS_GET,
)

AGREEMENT_FACTOR = 2.0


def analyse(observation: QuotaObservation) -> ProbeResult:
    findings: dict[str, Any] = {
        "published_table": {
            endpoint.value: PUBLISHED_QUOTA_UNITS[endpoint] for endpoint in PUBLISHED_RANK
        },
        "published_per_minute_units": PUBLISHED_PER_MINUTE_UNITS,
        "calibration_before_this_run": RATE_CALIBRATION,
        "observed": {},
    }
    inferred: dict[GmailEndpoint, float] = {}
    for entry in observation.per_endpoint:
        units = inferred_units(entry)
        findings["observed"][entry.endpoint.value] = {
            "calls_completed": entry.calls_completed,
            "elapsed_s": round(entry.elapsed_s, 3),
            "refused": entry.refused,
            "refusal_status": entry.refusal_status,
            "refusal_reason": entry.refusal_reason,
            "inferred_units_per_call": None if units is None else round(units, 2),
        }
        if units is not None:
            inferred[entry.endpoint] = units

    measured_rank = [endpoint for endpoint in PUBLISHED_RANK if endpoint in inferred]
    if len(measured_rank) < 2:
        return ProbeResult(
            spec=SPEC,
            verdict=Verdict.INCONCLUSIVE,
            findings=findings,
            notes=(
                "fewer than two endpoints reached a refusal, so neither the rank order nor "
                "the agreement bound can be evaluated. An inconclusive preflight leaves the "
                "rate table unvalidated; it is not a pass.",
            ),
        )

    ordered = sorted(measured_rank, key=lambda endpoint: inferred[endpoint])
    rank_holds = ordered == measured_rank
    disagreements = [
        endpoint.value
        for endpoint in measured_rank
        if not (
            1 / AGREEMENT_FACTOR
            <= inferred[endpoint] / PUBLISHED_QUOTA_UNITS[endpoint]
            <= AGREEMENT_FACTOR
        )
    ]
    findings["rank_order_holds"] = rank_holds
    findings["outside_agreement_factor"] = disagreements
    findings["agreement_factor"] = AGREEMENT_FACTOR
    verdict = Verdict.PASS if (rank_holds and not disagreements) else Verdict.FAIL
    return ProbeResult(
        spec=SPEC,
        verdict=verdict,
        findings=findings,
        notes=(
            "the inference assumes one token bucket, one project and an exclusive window "
            "(PF-16). Contention makes the apparent limit tighter than the real one, which "
            "is the safe direction for a cost bound and the wrong direction for a governor "
            "budget - so a FAIL here is re-run under a confirmed exclusive window before its "
            "consequence is executed.",
        ),
    )
