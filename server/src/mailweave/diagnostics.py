"""Call lifecycle diagnostics: one line when a tool call starts, one when it ends (2026-09-21).

**Why a fourth writer.** On 2026-09-21 a `mailweave_get_messages` call on the Desktop surface
produced nothing for four minutes: no result, no refusal, no error. Nothing in either server
could say whether the request arrived. The trace sink is built, wired and never constructed
by `runtime.start`; the tool that would surface a trace is unpublished; and both servers
write only a startup banner to stderr. So the question "did the server receive this call, and
if so where did it stop?" had no artifact that could answer it, in either direction. A start
line with no end line is that answer. No start line is the other answer.

**What a line carries, and what it never does.** The tool name, the surface, an opaque call
id, a wall-clock timestamp, and on the end line the elapsed milliseconds, the allowance the
call bound and how far past it the call ran, and the outcome: served, declined (with the D.11
code, `terminal` and `recovery`), or a protocol or internal error, with the exception's class
name. Of the arguments it carries the **shape** only: which published keys were present, the
length of a list, whether a string was there. Never the string. So a query is `"query": "str"`,
a message id list is `"message_ids": "list[4]"`, a handle is `"map_id": "str"`.

**The shape is read off the tool's published schema, not off the arguments** (second repair,
same day). The start line is written before the arguments are validated - that is the point
of a start line - so the arguments it sees are whatever the caller sent. The first draft
named every key the caller used and carried the value of any key it took for an enum, which
made two things the caller writes into content: a key (`{"<mail text>": 1}`) and a string
under a known key (`{"view": "<mail text>"}`). Now a key is named only when the schema
publishes it, and everything else is a count of unknown keys; a string is carried only when
the schema publishes an `enum` for that key **and the value is one of its members**, and is
`"str"` otherwise; a boolean is carried only where the schema says `boolean`; every integer
is `"int"`. A caller can put nothing into this file but the names the server already
publishes. No body, no subject, no address, no identifier, no credential and no query text
can reach it, and `test_repairs_2026_09_21.py` holds that by writing markers through both
surfaces, valid and malformed, and asserting their absence.

**What this is not.** It is not a record of what the tools returned, and it cannot verify a
citation. A claim that a message said something is checked against the message, and the
message is in the tool result the client received, not here. Preserving tool results is the
client's job and this file does not try to do it; a redacted trace that "proves" content is
exactly the confusion `USER_TASK_PILOT.md` names. This file proves that a call happened, when,
and how it ended.

**Opt-in, by path.** `MAILWEAVE_DIAGNOSTICS=<file>` in the server's environment enables it;
unset, `lifecycle()` is a no-op object and no file is touched. A path rather than a flag so
the owner chooses where the record lands, and an environment variable rather than a config
key because the config's schema is `extra="forbid"` and a diagnostic switch is not a
security-relevant setting the config file should be able to widen. The file is `0600` inside
a `0700` directory, appended and fsynced per line, like the other three writers.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any, Final

from mailweave.constants import TOKEN_DIR_MODE, TOKEN_FILE_MODE

#: The environment variable that names the file. Unset means off.
ENV_VAR: Final[str] = "MAILWEAVE_DIAGNOSTICS"

#: How deep into nested objects a shape is taken. One level - `budget`, `pool`, `scan` are
#: objects of scalars - and anything deeper is a count.
_SHAPE_DEPTH: Final[int] = 1

#: What the start line records for a tool it was handed no schema for. Both surfaces refuse
#: an unknown tool name before the partition, so this is defence rather than a path; the
#: name is not written, because an unvalidated name is a caller's string.
UNREGISTERED_TOOL: Final[str] = "unregistered"


@dataclass(frozen=True)
class Shape:
    """The arguments' shape against a schema, and how many keys the schema did not know."""

    fields: dict[str, Any]
    unknown_keys: int


def _properties(schema: Mapping[str, Any] | None) -> Mapping[str, Any]:
    published = schema.get("properties") if isinstance(schema, Mapping) else None
    return published if isinstance(published, Mapping) else {}


def _shape_value(value: Any, spec: Mapping[str, Any], depth: int) -> Any:
    """One value's shape under the property schema the tool publishes for its key."""
    if isinstance(value, bool):
        return value if spec.get("type") == "boolean" else "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, str):
        members = spec.get("enum")
        if isinstance(members, list | tuple) and value in members:
            return value
        return "str"
    if isinstance(value, list | tuple):
        return f"list[{len(value)}]"
    if isinstance(value, Mapping):
        if depth < _SHAPE_DEPTH and _properties(spec):
            nested = shape_of(value, spec, depth=depth + 1)
            fields: dict[str, Any] = dict(nested.fields)
            if nested.unknown_keys:
                fields["<unknown>"] = nested.unknown_keys
            return fields
        return f"object[{len(value)}]"
    if value is None:
        return None
    return type(value).__name__


def shape_of(
    arguments: Mapping[str, Any], schema: Mapping[str, Any] | None, *, depth: int = 0
) -> Shape:
    """The arguments' shape, read off `schema`. Never a string from the caller.

    A key is named only when `schema` publishes it under `properties`; every other key is
    counted, not named. A string value is carried only when the property publishes an `enum`
    and the value is one of its members. With no schema nothing is named at all.
    """
    published = _properties(schema)
    fields: dict[str, Any] = {}
    unknown = 0
    for key, value in arguments.items():
        if not isinstance(key, str) or key not in published:
            unknown += 1
            continue
        spec = published[key]
        fields[key] = _shape_value(value, spec if isinstance(spec, Mapping) else {}, depth)
    return Shape(fields=fields, unknown_keys=unknown)


def surface_of(tool: str) -> str:
    return "orivra" if tool.startswith("orivra_") else "mailweave"


@dataclass(frozen=True)
class CallRecord:
    """One call in flight: what `start` wrote, held until `end`."""

    call_id: str
    surface: str
    tool: str
    started_ms: float


class Lifecycle:
    """The writer. `path=None` is the no-op the process runs with when nothing asked for it."""

    def __init__(self, path: Path | None, *, clock_ms: Callable[[], float] | None = None) -> None:
        self._path = path
        self._clock_ms = clock_ms if clock_ms is not None else (lambda: monotonic() * 1000.0)
        #: The call in flight, and the allowances it has bound so far. One call at a time
        #: (A.5c's lock), so a slot rather than a map.
        self._current: CallRecord | None = None
        self._allowance_ms: float = 0.0
        self._deadlines: int = 0
        self._cold_load_ms: int = 0
        self._socket_figures: dict[str, int] = {}
        #: When the request now being served reached the server, before it waited for the
        #: one-call-at-a-time lock; set by `queued_since`, consumed by the next `start`.
        self._arrived_ms: float | None = None

    @property
    def enabled(self) -> bool:
        return self._path is not None

    @property
    def path(self) -> Path | None:
        return self._path

    def start(
        self, tool: str, arguments: Mapping[str, Any], *, schema: Mapping[str, Any] | None
    ) -> CallRecord:
        """Write the start line. `schema` is the tool's published input schema, and it is
        what decides which keys are named and which values are carried; `None` names nothing,
        not even the tool."""
        named = tool if schema is not None else UNREGISTERED_TOOL
        record = CallRecord(
            call_id=uuid.uuid4().hex,
            surface=surface_of(named),
            tool=named,
            started_ms=self._clock_ms(),
        )
        self._current = record
        self._allowance_ms = 0.0
        self._deadlines = 0
        self._cold_load_ms = 0
        self._socket_figures = {}
        arrived = self._arrived_ms
        self._arrived_ms = None
        shape = shape_of(arguments, schema)
        line: dict[str, Any] = {
            "event": "start",
            "call": record.call_id,
            "surface": record.surface,
            "tool": record.tool,
            "shape": shape.fields,
        }
        if shape.unknown_keys:
            line["unknown_keys"] = shape.unknown_keys
        if arrived is not None:
            # The wait between the request reaching the server and this call starting: the
            # one-call-at-a-time lock (A.5c), which `elapsed_ms` does not include because it
            # is not this call's work. A client's clock runs through it all the same.
            line["queued_ms"] = max(0, int(record.started_ms - arrived))
        self._write(line)
        return record

    @contextmanager
    def queued_since(self, arrived_ms: float) -> Iterator[None]:
        """Tell the next `start` when its request arrived, so the start line can say how
        long it queued. Entered by the server inside the call lock, immediately before the
        call, so one arrival is consumed by exactly the call it belongs to."""
        self._arrived_ms = arrived_ms
        try:
            yield
        finally:
            self._arrived_ms = None

    def allowance(self, budget_ms: float) -> None:
        """Record that the call in flight bound a deadline of `budget_ms`.

        Summed, because one Orivra call can run several MailWeave retrievals in sequence and
        each binds its own; the sum is what the call's elapsed time is honestly measured
        against. The end line carries it as `allowance_ms`, with `overrun_ms` beside it, so
        a late `budget_exhausted` is visible as late rather than passing because it declined.
        """
        if self._current is not None:
            self._allowance_ms += max(0.0, float(budget_ms))
            self._deadlines += 1

    def observe(
        self,
        *,
        cold_load_ms: int | None = None,
        connect_ms: int | None = None,
        tls_ms: int | None = None,
        write_ms: int | None = None,
        read_ms: int | None = None,
        sockets: int | None = None,
    ) -> None:
        """Record a closed-vocabulary figure about the call in flight, for its end line.

        Numbers only, keyed by names this module declares; there is no general
        `note(key, value)` here, deliberately, because a free key is a channel and this file
        has none. `cold_load_ms` is the model load a first semantic query pays, which PF-4
        keeps outside every per-query budget. The four socket figures (2026-09-22) are where a
        call's wall clock went at the transport, summed over every socket operation of the
        call: `connect_ms` (which includes name resolution, the one wait nothing bounds),
        `tls_ms`, `write_ms` and `read_ms` (waiting for bytes); `sockets` counts the
        connections the call opened. They exist so that a late call says where it was late.
        """
        if self._current is None:
            return
        if cold_load_ms is not None:
            self._cold_load_ms += max(0, int(cold_load_ms))
        for key, value in (
            ("connect_ms", connect_ms),
            ("tls_ms", tls_ms),
            ("write_ms", write_ms),
            ("read_ms", read_ms),
            ("sockets", sockets),
        ):
            if value is not None:
                self._socket_figures[key] = self._socket_figures.get(key, 0) + max(0, int(value))

    def end(
        self,
        record: CallRecord,
        *,
        outcome: str,
        code: str | None = None,
        terminal: bool | None = None,
        recovery: str | None = None,
        fault: str | None = None,
    ) -> None:
        elapsed = max(0, int(self._clock_ms() - record.started_ms))
        line: dict[str, Any] = {
            "event": "end",
            "call": record.call_id,
            "surface": record.surface,
            "tool": record.tool,
            "elapsed_ms": elapsed,
            "outcome": outcome,
        }
        if self._current is not None and self._current.call_id == record.call_id:
            if self._allowance_ms > 0.0:
                allowance = int(self._allowance_ms)
                line["allowance_ms"] = allowance
                line["overrun_ms"] = max(0, elapsed - allowance)
                # How many retrievals bound one: an `orivra_ask` that ran a search and then
                # the adapter's own ladder, probes and fetches is several allowances in
                # sequence, and the sum alone would hide that the client waited for all of
                # them.
                line["deadlines"] = self._deadlines
            if self._cold_load_ms:
                line["cold_load_ms"] = self._cold_load_ms
            for key in ("sockets", "connect_ms", "tls_ms", "write_ms", "read_ms"):
                if key in self._socket_figures:
                    line[key] = self._socket_figures[key]
            self._current = None
            self._allowance_ms = 0.0
            self._deadlines = 0
            self._cold_load_ms = 0
            self._socket_figures = {}
        if code is not None:
            line["code"] = code
        if terminal is not None:
            line["terminal"] = terminal
        if recovery is not None:
            line["recovery"] = recovery
        if fault is not None:
            line["fault"] = fault
        self._write(line)

    def _write(self, line: Mapping[str, Any]) -> None:
        """Append and fsync one line. A disk that will not take it costs the line and nothing
        else: a diagnostic that could fail a tool call would be less safe than none."""
        path = self._path
        if path is None:
            return
        payload = {"ts": datetime.now(UTC).isoformat(timespec="milliseconds"), **line}
        try:
            directory = path.parent
            directory.mkdir(mode=TOKEN_DIR_MODE, parents=True, exist_ok=True)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, TOKEN_FILE_MODE)
            try:
                os.fchmod(descriptor, TOKEN_FILE_MODE)
                text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                os.write(descriptor, (text + "\n").encode("utf-8"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            return


_PROCESS: Lifecycle | None = None


def lifecycle() -> Lifecycle:
    """The process-wide writer, built once from the environment. Off unless asked for."""
    global _PROCESS
    if _PROCESS is None:
        named = os.environ.get(ENV_VAR, "").strip()
        _PROCESS = Lifecycle(Path(named).expanduser() if named else None)
    return _PROCESS


def use(writer: Lifecycle | None) -> None:
    """Replace the process-wide writer. For tests, and for `serve` when it resolves the path
    itself; passing `None` re-reads the environment on the next `lifecycle()`."""
    global _PROCESS
    _PROCESS = writer


__all__ = [
    "ENV_VAR",
    "UNREGISTERED_TOOL",
    "CallRecord",
    "Lifecycle",
    "Shape",
    "lifecycle",
    "shape_of",
    "surface_of",
    "use",
]
