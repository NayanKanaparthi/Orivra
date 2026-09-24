"""Where a trace goes: JSONL on disk, under the profile-bound type (AD A.11, D.10).

**One writer, audited like the other two.** The `unaudited-disk-write` guard refuses a write
from any module but a named few, and this is the third. What it buys is that "what does this
process write to disk?" has a three-line answer: the token store, the freshness watermark,
and this.

**The path is bound to the policy, not chosen per call.** `traces/personal/` for the personal
profile; `traces/personal/diagnose/<finding-id>/` for A.3's gated escape hatch, which is
gitignored. A sink constructed under the personal profile cannot be asked to write a seed
trace, because the directory is decided when the sink is built and the record's own
`redaction` field is checked against it before anything is written - a mismatch raises rather
than writing to the wrong tree.

**Appending, and fsync'd.** A trace is a forensic record; one whose last line is half-written
because the process exited is a record that cannot be parsed. Each line is written and
flushed under `0600` inside a `0700` directory, the same permissions the watermark uses and
for the same reason: these files are about one person's mailbox even when they hold none of
its text.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Final

from mailweave.trace.redaction import RedactionPolicy
from mailweave.trace.schema import PersonalTrace

#: Directory mode: owner only. A trace holds no mail text and is still nobody else's.
_DIR_MODE: Final[int] = 0o700
#: File mode: owner read/write.
_FILE_MODE: Final[int] = 0o600


class TraceRefused(RuntimeError):
    """A trace could not be written, and the caller is told rather than left guessing."""


def new_trace_id() -> str:
    """An opaque id for one top-level call. Random, so it encodes nothing about the query."""
    return uuid.uuid4().hex


class TraceSink:
    """Appends `PersonalTrace` records as JSONL under one policy's directory."""

    def __init__(
        self,
        root: Path,
        *,
        policy: RedactionPolicy = RedactionPolicy.PERSONAL,
        diagnose_finding: str | None = None,
    ) -> None:
        if policy is RedactionPolicy.DIAGNOSE and not diagnose_finding:
            raise TraceRefused(
                "the diagnose policy names the finding it was opened for (AD A.3); a "
                "diagnostic trace with no finding id is an escape hatch with no reason "
                "attached, which is the shape that stops being temporary"
            )
        self._root = root.expanduser()
        self._policy = policy
        self._finding = diagnose_finding

    @property
    def policy(self) -> RedactionPolicy:
        return self._policy

    @property
    def directory(self) -> Path:
        """`traces/<policy>/`, with A.3's diagnostic output in its own named subtree."""
        base = self._root / "traces" / self._policy.value
        if self._policy is RedactionPolicy.DIAGNOSE:
            assert self._finding is not None  # refused in `__init__`
            return base / self._finding
        return base

    @property
    def path(self) -> Path:
        return self.directory / "trace.jsonl"

    def ensure_directory(self) -> Path:
        directory = self.directory
        directory.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
        directory.chmod(_DIR_MODE)
        return directory

    def write(self, trace: PersonalTrace) -> Path:
        """Append one record. Raises `TraceRefused` rather than writing to the wrong tree.

        **The record's own policy is checked against the sink's.** A `PersonalTrace` carries
        `redaction` as a first-class field, and a sink bound to the personal profile writing
        a record that says `seed` would produce a file whose contents contradict the
        directory they are in - which is worse than either, because a reader trusts the path.
        """
        if trace.redaction is not self._policy:
            raise TraceRefused(
                f"a trace declaring redaction={trace.redaction.value} cannot be written to "
                f"the {self._policy.value} sink"
            )
        if self._policy is RedactionPolicy.DIAGNOSE and trace.diagnose_finding != self._finding:
            raise TraceRefused("a diagnostic trace must name the finding its sink was opened for")
        self.ensure_directory()
        line = json.dumps(trace.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, _FILE_MODE)
        try:
            os.fchmod(descriptor, _FILE_MODE)
            os.write(descriptor, (line + "\n").encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return self.path

    def read_all(self) -> tuple[PersonalTrace, ...]:
        """Every record written here, for `mailweave inspect` and for tests."""
        if not self.path.exists():
            return ()
        records = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(PersonalTrace.model_validate_json(line))
        return tuple(records)


__all__ = ["TraceRefused", "TraceSink", "new_trace_id"]
