"""M2's two-arm evaluation harness: the case interface, the arms, and the hypothesis verdicts.

`mailweave_harness.seed` builds the corpus and says, in its own docstring, that the F1-F29 case
content is not there and that each milestone adds the families it needs - M2 the Gmail ones.
This package is that addition, and it is deliberately **generic**: it holds the schema, the
joins, the arms and the falsification conditions, and no query and no answer. A campaign hands
it a case file; it hands back per-case measurements and three verdicts.
"""

from __future__ import annotations

from mailweave_harness.evaluation.arms import (
    BOTH_OFF,
    FIXED_WINDOW,
    FULL,
    MAX_RECOVERY_ROUNDS,
    SEM_OFF,
    SPECS,
    Arm,
    ArmSpec,
    CaseRun,
    CountingBackend,
    Factor,
    Measured,
    Reach,
    TraceCursor,
    as_json,
    follow,
    run_all,
    run_case,
)
from mailweave_harness.evaluation.cases import (
    DISTRACTOR_TYPES,
    FAMILIES,
    FAMILY_LABELS,
    REGISTERED_N,
    SWEEP_POSITIONS,
    Case,
    CaseFile,
    EvidenceRef,
    RefUnresolvable,
    ResolvedCase,
    check_against,
    load_cases,
    resolve_against,
)
from mailweave_harness.evaluation.hypotheses import (
    Clause,
    CutLoss,
    FamilyRecall,
    HypothesisResult,
    Stage,
    Verdict,
    evaluate,
    family_recall,
    mean_cut_loss,
    position_spread,
    recoverability,
)
from mailweave_harness.evaluation.observe import FetchLog, FetchObserver
from mailweave_harness.evaluation.report import (
    Difference,
    StillFailing,
    differences,
    render,
    still_failing,
)

__all__ = [
    "BOTH_OFF",
    "DISTRACTOR_TYPES",
    "FAMILIES",
    "FAMILY_LABELS",
    "FIXED_WINDOW",
    "FULL",
    "MAX_RECOVERY_ROUNDS",
    "REGISTERED_N",
    "SEM_OFF",
    "SPECS",
    "SWEEP_POSITIONS",
    "Arm",
    "ArmSpec",
    "Case",
    "CaseFile",
    "CaseRun",
    "Clause",
    "CountingBackend",
    "CutLoss",
    "Difference",
    "EvidenceRef",
    "Factor",
    "FamilyRecall",
    "FetchLog",
    "FetchObserver",
    "HypothesisResult",
    "Measured",
    "Reach",
    "RefUnresolvable",
    "ResolvedCase",
    "Stage",
    "StillFailing",
    "TraceCursor",
    "Verdict",
    "as_json",
    "check_against",
    "differences",
    "evaluate",
    "family_recall",
    "follow",
    "load_cases",
    "mean_cut_loss",
    "position_spread",
    "recoverability",
    "render",
    "resolve_against",
    "run_all",
    "run_case",
    "still_failing",
]
