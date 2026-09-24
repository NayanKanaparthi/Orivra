"""PF-21 - what one Gmail call costs in wall-clock time, from the owner's machine.

AD A.7 publishes `max_server_ms = 2,000` as the deadline over rungs L0-L4 and
`max_http_requests = 24` as the request cap of the same query. Those two are consistent only
if a request completes in 2,000 / 24 = 83 ms including TLS and the round trip, and no number
in the project was ever measured against a real network: every test drives a zero-latency
`MockTransport`. This probe is the measurement. It does nothing else - it does not choose the
new deadline, because a deadline chosen by the same run that measured it is a deadline chosen
to look right. The candidate formula is registered below and the owner decides.

Numbers only: per-endpoint sample counts and millisecond percentiles. No id, no text.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mailweave.constants import MAX_HTTP_REQUESTS, MAX_SERVER_MS
from mailweave.gmail import GmailEndpoint, GmailFault
from mailweave_harness.preflight.spec import ProbeResult, ProbeSpec, Verdict

#: Ten sequential samples per endpoint. Enough for a p90 that is an observed value rather than
#: an interpolation, and cheap: at the published rates the whole probe is 10 x (1 + 5 + 20 +
#: 40) = 660 units, well inside one minute's budget with nothing else running.
SAMPLES_PER_ENDPOINT = 10

#: The endpoints a search actually spends its deadline on, in the order a query spends them.
MEASURED: tuple[GmailEndpoint, ...] = (
    GmailEndpoint.GET_PROFILE,
    GmailEndpoint.MESSAGES_LIST,
    GmailEndpoint.MESSAGES_GET,
    GmailEndpoint.THREADS_GET,
)

SPEC = ProbeSpec(
    id="PF-21-endpoint-latency",
    title="Wall-clock latency per Gmail endpoint, from the owner's machine",
    measures=(
        f"{SAMPLES_PER_ENDPOINT} sequential calls each of users.getProfile, messages.list "
        "(one id), messages.get(format=full) and threads.get(format=metadata), over the "
        "owner's own network; per endpoint the sample count and the p50, p90 and max in "
        "milliseconds, with the first sample reported separately as the cold-connection reading"
    ),
    validates=(
        f"AD A.7's max_server_ms = {MAX_SERVER_MS} as a deadline that can actually spend the "
        f"same table's max_http_requests = {MAX_HTTP_REQUESTS}: the two agree only if one "
        f"request completes in {MAX_SERVER_MS // MAX_HTTP_REQUESTS} ms"
    ),
    falsified_when=(
        "max_http_requests multiplied by the slowest endpoint's p90 exceeds max_server_ms - "
        "the published deadline cannot spend the published request cap on this network"
    ),
    changes_if_it_fails=(
        "max_server_ms is re-derived from this measurement rather than asserted. The "
        "registered candidate is max_http_requests x the slowest p90, rounded up to the "
        "hundred; it is an upper-bound formula and not the default by itself - the proposed "
        "default is validated on neutral end-to-end searches before adoption, and the constant "
        "then carries the figures and the date of this run (AD A.11)"
    ),
    credential="read",
    quota_budget_units=SAMPLES_PER_ENDPOINT * (1 + 5 + 20 + 40),
    pre_registered_rules=(
        "the candidate formula (max_http_requests x slowest p90) is registered as a bound, "
        "not adopted by this probe; adoption is the owner's decision after seeing the figures",
        "p90 is the observed 9th of 10 sorted samples, not an interpolation; the cold first "
        "sample is included in the percentiles and also reported on its own",
        "a call that fails for any reason other than rate limiting ends that endpoint's "
        "series and is reported as a short series, never as a zero-millisecond sample",
    ),
)


@dataclass(frozen=True)
class EndpointLatency:
    """One endpoint's timed series, in milliseconds. Numbers only."""

    endpoint: GmailEndpoint
    samples_ms: tuple[float, ...]
    stopped_early: bool = False

    @property
    def count(self) -> int:
        return len(self.samples_ms)

    def percentile(self, fraction: float) -> float | None:
        """The observed sample at `fraction` of the sorted series; `None` on an empty one."""
        if not self.samples_ms:
            return None
        ordered = sorted(self.samples_ms)
        index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
        return ordered[index]


@dataclass
class LatencyObservation:
    per_endpoint: list[EndpointLatency] = field(default_factory=list)


def time_endpoint(
    endpoint: GmailEndpoint, make_call: Callable[[], None], *, samples: int = SAMPLES_PER_ENDPOINT
) -> EndpointLatency:
    """Time `samples` sequential calls. A non-rate-limit fault ends the series early."""
    timings: list[float] = []
    stopped_early = False
    for _ in range(samples):
        started = time.monotonic()
        try:
            make_call()
        except GmailFault:
            stopped_early = True
            break
        timings.append((time.monotonic() - started) * 1000.0)
    return EndpointLatency(
        endpoint=endpoint, samples_ms=tuple(timings), stopped_early=stopped_early
    )


def candidate_deadline_ms(slowest_p90_ms: float) -> int:
    """The registered candidate: `max_http_requests` x the slowest p90, rounded up to 100 ms."""
    raw = MAX_HTTP_REQUESTS * slowest_p90_ms
    return int(-(-raw // 100) * 100)


def analyse(observation: LatencyObservation) -> ProbeResult:
    findings: dict[str, Any] = {"samples_per_endpoint": SAMPLES_PER_ENDPOINT, "endpoints": {}}
    slowest_p90: float | None = None
    incomplete = False
    for series in observation.per_endpoint:
        p50, p90 = series.percentile(0.5), series.percentile(0.9)
        findings["endpoints"][series.endpoint.value] = {
            "count": series.count,
            "cold_first_ms": round(series.samples_ms[0]) if series.samples_ms else None,
            "p50_ms": round(p50) if p50 is not None else None,
            "p90_ms": round(p90) if p90 is not None else None,
            "max_ms": round(max(series.samples_ms)) if series.samples_ms else None,
            "stopped_early": series.stopped_early,
        }
        if series.count < SAMPLES_PER_ENDPOINT:
            incomplete = True
        if p90 is not None and (slowest_p90 is None or p90 > slowest_p90):
            slowest_p90 = p90
    findings["published_max_server_ms"] = MAX_SERVER_MS
    findings["published_max_http_requests"] = MAX_HTTP_REQUESTS
    findings["ms_per_request_the_published_pair_assumes"] = MAX_SERVER_MS // MAX_HTTP_REQUESTS
    if slowest_p90 is None:
        return ProbeResult(
            spec=SPEC,
            verdict=Verdict.INCONCLUSIVE,
            findings=findings,
            notes=("no endpoint produced a sample; nothing was measured",),
        )
    findings["slowest_p90_ms"] = round(slowest_p90)
    findings["candidate_deadline_ms"] = candidate_deadline_ms(slowest_p90)
    findings["candidate_is_a_bound_not_a_default"] = True
    verdict = (
        Verdict.INCONCLUSIVE
        if incomplete
        else (Verdict.FAIL if MAX_HTTP_REQUESTS * slowest_p90 > MAX_SERVER_MS else Verdict.PASS)
    )
    notes: tuple[str, ...] = ()
    if incomplete:
        notes = ("at least one endpoint's series ended early; the percentiles are partial",)
    return ProbeResult(spec=SPEC, verdict=verdict, findings=findings, notes=notes)
