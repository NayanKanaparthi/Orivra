"""WS-10: escalation policy, budgets, stopping and outcome.

Three modules, and the split is by what each one reads:

  * `budget` reads a meter and a clock, and refuses **before** a spend;
  * `stopping` reads signals that have already been computed, and holds AD D.3's rules in
    their published order - the order two separate rounds have got wrong;
  * `account` reads neither. It holds the record every rung appears in exactly once, and
    the response's `rungs`, `not_tried`, `budget_caps_hit` and `outcome` are read off it.

Nothing here computes a disposition. `withheld := H - disclosed` is `DispositionLedger`'s,
over the ids every observation recorded, and a second computation would be the shape the
seal exists to prevent. This layer reads the ledger's answer and refuses to say `not_found`
over it.
"""

from __future__ import annotations

from mailweave.policy.account import (
    LADDER,
    LadderAccount,
    RungAccount,
    RungState,
    blocked_by,
    force_rungs,
    not_applicable,
    outcome_of,
    ran,
    stopped_on_evidence,
)
from mailweave.policy.budget import (
    AppliedBudget,
    BudgetAccountant,
    BudgetRefused,
    BudgetRequest,
    CapBreach,
    Governor,
    apply_floor,
)
from mailweave.policy.stopping import (
    HALTING_RULES,
    PUBLISHED_ORDER,
    StopInputs,
    StopRule,
    first_rule_that_fires,
    rule_1_stops,
    rule_1b_stops,
    rule_2_stops,
    rule_3_stops,
    rule_4_escalates,
    rule_5_stops,
)

__all__ = [
    "HALTING_RULES",
    "LADDER",
    "PUBLISHED_ORDER",
    "AppliedBudget",
    "BudgetAccountant",
    "BudgetRefused",
    "BudgetRequest",
    "CapBreach",
    "Governor",
    "LadderAccount",
    "RungAccount",
    "RungState",
    "StopInputs",
    "StopRule",
    "apply_floor",
    "blocked_by",
    "first_rule_that_fires",
    "force_rungs",
    "not_applicable",
    "outcome_of",
    "ran",
    "rule_1_stops",
    "rule_1b_stops",
    "rule_2_stops",
    "rule_3_stops",
    "rule_4_escalates",
    "rule_5_stops",
    "stopped_on_evidence",
]
