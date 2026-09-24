"""The three counters of AD A.5b, kept separate because they measure different things.

| Counter | What it counts | Who can observe it |
|---|---|---|
| `http_requests` | HTTP requests leaving the process | the harness counting proxy, **exactly** |
| `api_calls` | logical Gmail sub-requests sent upstream | server-side count |
| `quota_units` | `api_calls` x the published rate table | nobody: it is a multiplication |

A network proxy sees one HTTP request per `batch` call whatever *n* is, while quota is
charged per sub-request. ADV-106 found the architecture using one word for both, and the
whole point of this module is that the two cannot be conflated again: they are separate
fields with separate increment paths.

**A retried call increments `api_calls` once per attempt**, which is worth stating because
"logical sub-request" could be read either way. AD A.5a settles it: *every HTTP attempt is
charged to the accountant, including the attempt that 429'd, because the upstream quota was
spent.* A retry is a second sub-request as far as Gmail's meter is concerned, so it is a
second one here. Counting it once would make MailWeave's own cost report quietly cheaper
than the reality it is meant to describe.

**`quota_units` is a diagnostic, never a headline** (ADV-211, OBS-02). `CallMeter.reading()`
therefore refuses to hand out a bare integer: it returns a `MeterReading` carrying the
calibration string with it, so a unit figure cannot be quoted without the sentence saying
PF-3 has not run.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from types import MappingProxyType

from mailweave.gmail.rates import PUBLISHED_QUOTA_UNITS, RATE_CALIBRATION, GmailEndpoint


@dataclass(frozen=True)
class MeterReading:
    """A snapshot of the three counters, with the provenance of the derived one attached."""

    http_requests: int
    api_calls: int
    quota_units_diagnostic: int
    calibration: str
    api_calls_by_endpoint: MappingProxyType[GmailEndpoint, int]
    http_requests_by_endpoint: MappingProxyType[GmailEndpoint, int]

    def as_trace_fields(self) -> dict[str, object]:
        """The A.11 / D.10 trace shape for these counters.

        `quota_units` is emitted under a name that says what it is. AD A.11 requires every
        published quota figure to carry its PF-3 calibration date; there is no date yet, so
        it carries the sentence that says so.
        """
        return {
            "http_requests": self.http_requests,
            "api_calls": self.api_calls,
            "api_calls_by_method": {
                endpoint.value: count for endpoint, count in self.api_calls_by_endpoint.items()
            },
            "quota_units": self.quota_units_diagnostic,
            "quota_units_label": "diagnostic",
            "quota_units_calibration": self.calibration,
        }


class CallMeter:
    """Counts what one process, or one query, spent upstream.

    It is deliberately not a budget: nothing here refuses a call. The per-query
    `budget_accountant` and the process-wide governor (AD A.5c) are WS-10's, and they read
    a meter rather than being one. Building the refusal here would put the ladder's policy
    inside the transport, where no reviewer of the ladder would look for it.
    """

    __slots__ = ("_api_calls", "_http_requests")

    def __init__(self) -> None:
        self._http_requests: Counter[GmailEndpoint] = Counter()
        self._api_calls: Counter[GmailEndpoint] = Counter()

    def record_attempt(self, endpoint: GmailEndpoint, *, sub_requests: int = 1) -> None:
        """One HTTP request leaving the process, carrying `sub_requests` logical calls.

        `sub_requests` is 1 for every call this round makes and exists so that a batcher
        (AD A.5a, not built in this round) increments the two counters correctly by
        construction rather than by remembering to.
        """
        if sub_requests < 1:
            raise ValueError("an HTTP request carries at least one logical sub-request")
        self._http_requests[endpoint] += 1
        self._api_calls[endpoint] += sub_requests

    def reading(self) -> MeterReading:
        units = sum(
            count * PUBLISHED_QUOTA_UNITS[endpoint] for endpoint, count in self._api_calls.items()
        )
        return MeterReading(
            http_requests=sum(self._http_requests.values()),
            api_calls=sum(self._api_calls.values()),
            quota_units_diagnostic=units,
            calibration=RATE_CALIBRATION,
            api_calls_by_endpoint=MappingProxyType(dict(self._api_calls)),
            http_requests_by_endpoint=MappingProxyType(dict(self._http_requests)),
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        reading = self.reading()
        return (
            f"CallMeter(http_requests={reading.http_requests}, "
            f"api_calls={reading.api_calls}, quota_units_diagnostic="
            f"{reading.quota_units_diagnostic})"
        )
