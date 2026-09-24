"""Loop-0 preflight probes (AD F, IMPLEMENTATION_PLAN 3).

Runnable code producing a written record, so the live phase is execution and not authoring.
Nothing here runs by importing it, and nothing here can start a consent.
"""

from mailweave_harness.preflight.record import (
    RecordWouldCarryContent,
    assert_record_is_content_free,
    write_records,
)
from mailweave_harness.preflight.runner import PLAN, REGISTRY, plan_text
from mailweave_harness.preflight.spec import ProbeResult, ProbeSpec, Verdict

__all__ = [
    "PLAN",
    "REGISTRY",
    "ProbeResult",
    "ProbeSpec",
    "RecordWouldCarryContent",
    "Verdict",
    "assert_record_is_content_free",
    "plan_text",
    "write_records",
]
