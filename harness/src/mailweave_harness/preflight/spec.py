"""What a preflight probe is, as a type (AD F, IMPLEMENTATION_PLAN 3).

Every probe declares four things and a runner refuses one that does not:

  * **what it measures** - the observation, in terms of real API responses;
  * **what design commitment it validates** - the named clause that rests on the answer;
  * **what would falsify it** - the condition under which the probe reports FAIL. A probe
    with no such condition is not a probe, and `ProbeSpec` will not construct without one;
  * **what changes if it fails** - the architecture edit the failure forces. Written before
    the run, because a consequence chosen after seeing the data is a consequence chosen to
    be affordable.

`Verdict.OBSERVATION_ONLY` exists for exactly one probe - the search-index freshness one -
and is not a way to opt out of falsifiability: that probe still has a FAIL condition, and
what `OBSERVATION_ONLY` means is that its *non*-failing output is raw numbers and never a
claim, because OD-1 reserves any freshness statement for the full stratified experiment.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    #: The probe ran but the observation cannot decide the question - too few threads in the
    #: mailbox, no mail arrived in the window. Never a pass: an inconclusive preflight leaves
    #: the design commitment it guards unvalidated, and the runner reports it as such.
    INCONCLUSIVE = "inconclusive"
    #: Raw numbers, deliberately not a verdict about the product (OD-1).
    OBSERVATION_ONLY = "observation_only"


@dataclass(frozen=True)
class ProbeSpec:
    """The declaration a probe cannot omit."""

    id: str
    title: str
    measures: str
    validates: str
    falsified_when: str
    changes_if_it_fails: str
    #: Which credential the probe needs: `read` (the owner's mailbox, read-only) or `seed`.
    credential: str = "read"
    #: What it costs, at the published (uncalibrated) rates, so the suite's own budget can be
    #: declared before PF-3 drives anything to 429 (PF-16).
    quota_budget_units: int = 0
    #: Decision rules registered *before* the run. Each is a threshold chosen without having
    #: seen data; listing them separately is what makes that visible rather than buried.
    pre_registered_rules: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "id",
            "title",
            "measures",
            "validates",
            "falsified_when",
            "changes_if_it_fails",
        ):
            if not getattr(self, name):
                raise ValueError(
                    f"a probe must declare {name}: a probe that cannot state what would "
                    "falsify it, or what changes when it does, is not a probe (AD F)"
                )
        if self.credential not in {"read", "seed"}:
            raise ValueError("a probe runs on the read credential or the seed credential")


#: The record keys whose values are this repository's own prose - a probe's declaration of
#: what it measures and what would falsify it - rather than anything observed in a mailbox,
#: **each with the shape `as_record` writes it in**: the number of list levels between the key
#: and the sentence.
#:
#: `record.assert_record_is_content_free` exempts these from its length and single-line
#: bounds, and it imports the mapping from here rather than restating it: the producer of the
#: record is the only place that knows which of its keys are prose, and a copy in the checker
#: is a copy that stops matching the day `as_record` grows a field (R-ARCH-031's shape).
#:
#: **The depth is here because the names alone were not enough (R-SEC-048).** Round 12's
#: exemption was "one prose key, then nothing but list indices", with no bound on how many -
#: so a body buried in nested lists (`notes[0][0]`, and deeper) inherited the exemption at any
#: depth and was written to disk intact. Five of these keys are written as a plain string and
#: two as a list of strings, so `notes[0]` is prose and `notes[0][0]` is a shape nobody has
#: ever written; the exemption is now exactly the producer's shape and no wider.
#: `test_the_exempt_set_is_the_producers_own_list_and_still_matches_it` derives the shape from
#: `as_record()` itself and fails if this mapping drifts from it.
PROSE_FIELDS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "title": 0,
        "measures": 0,
        "validates": 0,
        "falsified_when": 0,
        "changes_if_it_fails": 0,
        "pre_registered_rules": 1,
        "notes": 1,
    }
)


@dataclass(frozen=True)
class ProbeResult:
    """A probe's written record. Findings are numbers, counts and closed-vocabulary tokens."""

    spec: ProbeSpec
    verdict: Verdict
    findings: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def as_record(self) -> dict[str, Any]:
        return {
            "probe": self.spec.id,
            "title": self.spec.title,
            "verdict": self.verdict.value,
            "measures": self.spec.measures,
            "validates": self.spec.validates,
            "falsified_when": self.spec.falsified_when,
            "changes_if_it_fails": self.spec.changes_if_it_fails,
            "pre_registered_rules": list(self.spec.pre_registered_rules),
            "credential": self.spec.credential,
            "quota_budget_units": self.spec.quota_budget_units,
            "findings": self.findings,
            "notes": list(self.notes),
        }
