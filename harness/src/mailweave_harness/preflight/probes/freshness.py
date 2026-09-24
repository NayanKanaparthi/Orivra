"""Search-index freshness, as raw observation only (OD-1, AD F PF-10, D.9).

**This probe makes no freshness claim and cannot be made to.** OD-1 fixes the service level
at p90 <= 60 s evaluated independently at thread depths 0, 5 and 25, with pooling across
depths prohibited - and it can only be evaluated by the full stratified experiment (PF-10),
against a pre-registered number, on a corpus that does not exist yet. A percentile computed
here, over an unstratified sample of whatever happened to arrive, would be a number that
looks like that one and is not, which is the most expensive kind of wrong thing to write down.

So `analyse` emits the **raw observed lags** and the counts, computes no percentile, and its
non-failing verdict is `OBSERVATION_ONLY`. A test asserts that the findings contain no key
that reads like a service level.

**It still has a falsifier**, because a probe that cannot fail is not a probe. What it can
show is not "search is slow" but "search does not converge": a message observed arriving via
`history.list` that an **id-exact** `rfc822msgid:` search still does not return at the end of
the observation window has not been indexed late, it has not been indexed. AD D.9's LR rung
is built on the assumption that history-observed mail becomes findable; that is the
assumption this probe can break.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mailweave_harness.preflight.spec import ProbeResult, ProbeSpec, Verdict

SPEC = ProbeSpec(
    id="PF-freshness-raw",
    title="Search-index freshness - raw observation, no claim",
    measures=(
        "for each message first seen through history.list during the window: the seconds "
        "between that sighting and the first time an id-exact rfc822msgid: search returns it, "
        "or the fact that it never did within the window"
    ),
    validates=(
        "AD D.9's LR rung, which assumes a message observed through history.list becomes "
        "findable through search. It validates nothing about OD-1's service level, which "
        "needs PF-10's stratified experiment and a pre-registered number"
    ),
    falsified_when=(
        "a message observed through history.list is still not returned by an id-exact "
        "rfc822msgid: search at the end of the observation window"
    ),
    changes_if_it_fails=(
        "the LR rung's client-side re-check stops being a bridge over a delay and becomes the "
        "only path to those messages, so AD D.9's 'closed, published subset' of re-checkable "
        "constraints has to cover the query classes that would otherwise never resolve - a "
        "scope change to the re-check, and a trigger for the FRESH-02 mitigation regardless "
        "of any percentile"
    ),
    credential="read",
    quota_budget_units=400,
    pre_registered_rules=(
        "no percentile is computed and no aggregate is labelled a service level; OD-1's "
        "number is evaluated by PF-10 and by nothing else",
    ),
)


@dataclass
class FreshnessObservation:
    """One window of arrivals. Ids are salted digests; nothing here is mail text."""

    window_s: float
    #: digest -> seconds from the history sighting to the first search hit
    lag_seconds_by_message: dict[str, float] = field(default_factory=dict)
    #: digests observed arriving that search never returned inside the window
    never_found: list[str] = field(default_factory=list)
    #: how many history sightings there were in total
    arrivals_observed: int = 0


def analyse(observation: FreshnessObservation) -> ProbeResult:
    findings: dict[str, Any] = {
        "window_s": observation.window_s,
        "arrivals_observed": observation.arrivals_observed,
        "found_within_window": len(observation.lag_seconds_by_message),
        "never_found_within_window": len(observation.never_found),
        # Raw, sorted, unsummarised. Deliberately a list of numbers and not a distribution:
        # the summarising is PF-10's, against a stratification this sample does not have.
        "observed_lag_seconds_raw": sorted(
            round(value, 3) for value in observation.lag_seconds_by_message.values()
        ),
    }
    if observation.arrivals_observed == 0:
        return ProbeResult(
            spec=SPEC,
            verdict=Verdict.INCONCLUSIVE,
            findings=findings,
            notes=("no mail arrived during the window, so nothing was observed",),
        )
    if observation.never_found:
        return ProbeResult(
            spec=SPEC,
            verdict=Verdict.FAIL,
            findings=findings,
            notes=(
                "a message observed through history.list was never returned by an id-exact "
                "search inside the window. This is a convergence failure, not a lag "
                "measurement, and it is the one thing this probe is allowed to conclude.",
            ),
        )
    return ProbeResult(
        spec=SPEC,
        verdict=Verdict.OBSERVATION_ONLY,
        findings=findings,
        notes=(
            "raw numbers only. No percentile is computed here and none may be quoted from "
            "here: OD-1's p90 <= 60 s is evaluated at thread depths 0, 5 and 25 separately, "
            "with pooling prohibited, by PF-10's stratified experiment against a "
            "pre-registered figure. This sample is unstratified and opportunistic.",
        ),
    )
