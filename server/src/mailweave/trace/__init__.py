"""AD D.10's trace pipeline: the schema, the redaction type, and the one writer.

Importing this package touches no disk. A `TraceSink` creates its directory when it first
writes, and a process that never traces never makes one.
"""

from __future__ import annotations

from mailweave.trace.redaction import (
    DIGEST_CHARS,
    Redacted,
    RedactionPolicy,
    query_features,
    redact,
)
from mailweave.trace.schema import TRACE_SCHEMA_VERSION, PersonalTrace
from mailweave.trace.sink import TraceRefused, TraceSink, new_trace_id

__all__ = [
    "DIGEST_CHARS",
    "TRACE_SCHEMA_VERSION",
    "PersonalTrace",
    "Redacted",
    "RedactionPolicy",
    "TraceRefused",
    "TraceSink",
    "new_trace_id",
    "query_features",
    "redact",
]
