"""M2's acceptance as executable status: what has support here, and what is waiting."""

from __future__ import annotations

from mailweave_harness.acceptance.runner import (
    CheckResult,
    ItemResult,
    Status,
    resolve,
    run,
    unresolved,
)
from mailweave_harness.acceptance.spec import ITEMS, Check, Item

__all__ = [
    "ITEMS",
    "Check",
    "CheckResult",
    "Item",
    "ItemResult",
    "Status",
    "resolve",
    "run",
    "unresolved",
]
