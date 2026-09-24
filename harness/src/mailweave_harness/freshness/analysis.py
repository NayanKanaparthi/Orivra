"""OD-1's freshness service level, evaluated. Pooling is prohibited *by construction*.

**The three ways this analysis could quietly be wrong, and what stops each.**

  * **Pooling.** OD-1: "p90 <= 60 seconds ... evaluated independently at thread depths 0, 5
    and 25. Pooling across depths is prohibited." A pooled p90 over three strata passes
    whenever the two fast strata outnumber the slow one, which is exactly the depth-25 case
    the design believes is slower. So `p90` refuses a sample that mixes strata - it takes a
    `Stratum` and a list of that stratum's observations, and there is no function here that
    takes all of them at once. A pooled number is not computed and then rejected; it is
    unrepresentable.
  * **Censoring.** A probe that never surfaced is MF1, and dropping it from the sample makes
    the percentile better. A censored observation carries no lag by construction (`lag` is
    `None`), and `p90` refuses to be computed while any censored observation is in the
    stratum - because the honest p90 of a sample with an unbounded value in it is unbounded.
  * **The second trigger.** OD-1 states a confirmed real-mail false negative as a defect
    *regardless of percentile*, a second and independent trigger. A verdict that reported
    only p90 would let a passing percentile stand beside a false negative, which is the one
    thing OD-1 says it may not do.

**What this module does not do.** It does not decide whether a false negative is *confirmed*
- that is "the message is present and should match", which needs a human looking at real
mail. It takes the confirmation as an input and refuses to average it away.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import Final


class Stratum(IntEnum):
    """OD-1's three thread depths. There is no fourth and there is no "all"."""

    DEPTH_0 = 0
    DEPTH_5 = 5
    DEPTH_25 = 25


#: The three strata, in the order OD-1 names them.
STRATA: Final[tuple[Stratum, ...]] = (Stratum.DEPTH_0, Stratum.DEPTH_5, Stratum.DEPTH_25)

#: OD-1, binding, 2026-08-30. Seconds, from H0/history-confirmed arrival.
FSL_SECONDS: Final[float] = 60.0

#: The percentile OD-1 names. A constant so no analysis can quietly use a different one.
FSL_PERCENTILE: Final[float] = 0.90


class PoolingProhibited(ValueError):
    """An analysis tried to compute one number over more than one stratum (OD-1)."""


class CensoredSample(ValueError):
    """A percentile was asked for over a sample containing a probe that never surfaced."""


@dataclass(frozen=True)
class Observation:
    """One probe: arrival, first surfacing, the stratum, and whether it surfaced at all."""

    stratum: Stratum
    #: Seconds from H0/history-confirmed arrival to first surfacing. `None` when the probe
    #: never surfaced within the observation window - which is MF1, not a missing value.
    lag_seconds: float | None
    #: Which mailbox this arm observed, so T-VR2's two-mailbox rule is enforceable.
    mailbox: str
    probe_class: str
    #: A human confirmed the message was present and should have matched, and MailWeave did
    #: not surface it. OD-1's second trigger; never inferred from a long lag.
    confirmed_false_negative: bool = False

    @property
    def censored(self) -> bool:
        return self.lag_seconds is None


def p90(stratum: Stratum, observations: Sequence[Observation]) -> float:
    """The 90th-percentile lag of **one** stratum, in seconds.

    Takes the stratum it is about, and refuses every observation that is not in it. That is
    what makes pooling unrepresentable rather than merely forbidden: there is no call shape
    that computes one number over three strata, so an analysis cannot pool by forgetting to
    separate.

    The percentile is the nearest-rank one - the smallest observed value at or above which
    90% of the sample lies - rather than an interpolation between two observations. An
    interpolated p90 reports a lag nobody measured, and OD-1's threshold is a claim about
    observed behaviour.
    """
    mine = [row for row in observations if row.stratum is stratum]
    foreign = len(observations) - len(mine)
    if foreign:
        raise PoolingProhibited(
            f"{foreign} of {len(observations)} observations are not in stratum "
            f"{stratum.value}; OD-1 prohibits pooling across depths, so a percentile is "
            "computed per stratum or not at all"
        )
    if not mine:
        raise PoolingProhibited(f"stratum {stratum.value} has no observations to summarise")
    if any(row.censored for row in mine):
        raise CensoredSample(
            f"stratum {stratum.value} contains a probe that never surfaced. Dropping it "
            "would improve the percentile by removing the worst case, which is MF1 itself; "
            "the honest p90 of a sample with an unbounded value in it is unbounded"
        )
    lags = sorted(row.lag_seconds for row in mine if row.lag_seconds is not None)
    rank = max(1, math.ceil(FSL_PERCENTILE * len(lags)))
    return lags[rank - 1]


@dataclass(frozen=True)
class StratumVerdict:
    """One stratum's own verdict. Never combined with another's into a single number."""

    stratum: Stratum
    observations: int
    censored: int
    p90_seconds: float | None
    meets_fsl: bool | None
    why: str


@dataclass(frozen=True)
class FreshnessVerdict:
    """The whole of OD-1, which is two triggers and not one."""

    strata: tuple[StratumVerdict, ...]
    confirmed_false_negatives: int
    mailboxes: tuple[str, ...]

    @property
    def mf2_fires(self) -> bool:
        """p90 over the FSL in **any** stratum, each evaluated on its own."""
        return any(verdict.meets_fsl is False for verdict in self.strata)

    @property
    def mf4_fires(self) -> bool:
        """A confirmed real-mail false negative: a defect regardless of percentile."""
        return self.confirmed_false_negatives > 0

    @property
    def inconclusive(self) -> bool:
        """A stratum whose verdict could not be computed leaves the whole thing undecided.

        Not "the strata we could compute passed". OD-1 asks for a p90 at each of three
        depths; two out of three is a different claim, and reporting it as a pass would be
        the vacuous-check failure this project keeps finding, in the one measurement whose
        threshold was registered in advance precisely to prevent it.
        """
        return any(verdict.meets_fsl is None for verdict in self.strata)

    @property
    def passes(self) -> bool:
        return not (self.mf2_fires or self.mf4_fires or self.inconclusive)

    @property
    def two_mailboxes(self) -> bool:
        """T-VR2: one mailbox is a sample of one environment, not of Gmail."""
        return len(self.mailboxes) >= 2

    def rendered(self) -> str:
        lines = [
            f"OD-1 freshness service level: p90 <= {FSL_SECONDS:.0f} s at depths "
            f"{[s.value for s in STRATA]}, evaluated independently. Pooling prohibited.",
            "",
        ]
        for verdict in self.strata:
            measured = (
                "not computed" if verdict.p90_seconds is None else f"{verdict.p90_seconds:.1f} s"
            )
            lines.append(
                f"  depth {verdict.stratum.value:>2}: n={verdict.observations} "
                f"censored={verdict.censored} p90={measured} - {verdict.why}"
            )
        lines.append("")
        lines.append(f"  confirmed real-mail false negatives: {self.confirmed_false_negatives}")
        lines.append(f"  mailboxes observed: {len(self.mailboxes)} (T-VR2 asks for two)")
        lines.append("")
        if self.mf4_fires:
            lines.append("MF4 FIRES: a confirmed false negative is a defect regardless of p90.")
        if self.mf2_fires:
            lines.append("MF2 FIRES: p90 exceeds the FSL in at least one stratum.")
        if self.inconclusive:
            lines.append(
                "INCONCLUSIVE: a stratum has no computable verdict, so OD-1's question was "
                "not answered at all three depths."
            )
        if self.passes:
            lines.append("PASSES: every stratum meets the FSL and no false negative was confirmed.")
        return "\n".join(lines)


def analyse_freshness(observations: Sequence[Observation]) -> FreshnessVerdict:
    """Evaluate OD-1 over a set of observations, one stratum at a time."""
    verdicts: list[StratumVerdict] = []
    for stratum in STRATA:
        mine = [row for row in observations if row.stratum is stratum]
        censored = sum(1 for row in mine if row.censored)
        try:
            measured = p90(stratum, mine)
        except (PoolingProhibited, CensoredSample) as refusal:
            verdicts.append(
                StratumVerdict(
                    stratum=stratum,
                    observations=len(mine),
                    censored=censored,
                    p90_seconds=None,
                    meets_fsl=None,
                    why=str(refusal).split(";")[0],
                )
            )
            continue
        verdicts.append(
            StratumVerdict(
                stratum=stratum,
                observations=len(mine),
                censored=0,
                p90_seconds=measured,
                meets_fsl=measured <= FSL_SECONDS,
                why=(
                    f"nearest-rank p90 of {len(mine)} observations"
                    if measured <= FSL_SECONDS
                    else f"p90 {measured:.1f} s exceeds the {FSL_SECONDS:.0f} s FSL"
                ),
            )
        )
    return FreshnessVerdict(
        strata=tuple(verdicts),
        confirmed_false_negatives=sum(1 for row in observations if row.confirmed_false_negative),
        mailboxes=tuple(sorted({row.mailbox for row in observations})),
    )


__all__ = [
    "FSL_PERCENTILE",
    "FSL_SECONDS",
    "STRATA",
    "CensoredSample",
    "FreshnessVerdict",
    "Observation",
    "PoolingProhibited",
    "Stratum",
    "StratumVerdict",
    "analyse_freshness",
    "p90",
]
