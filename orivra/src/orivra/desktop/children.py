"""The product's own setup commands, run as child processes and read as events.

`mailweave auth login --events` and `mailweave setup-models --events` are the self-managed
path's commands with one flag: they print one JSON object per line. Running them as children
rather than calling their functions in this process is what keeps two properties of the
server process true in the extension as well - it has no listening socket (the consent
listener is the child's), and its import graph never reaches out to the model host (the
download is the child's).

A reader thread per stream turns lines into events. stdout carries only events; a line that
is not one is ignored rather than guessed at. stderr is forwarded to this process's stderr,
which Claude Desktop keeps in the extension's log, and is never put in front of the person:
it is where a traceback would go, and a traceback is not an explanation.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from typing import IO, Any, Protocol


class Child(Protocol):
    """What the setup flow needs from a running command. A test supplies a scripted one."""

    def events(self) -> list[dict[str, Any]]: ...

    def returncode(self) -> int | None: ...

    def terminate(self) -> None: ...


class EventChild:
    """A `subprocess.Popen` whose stdout is a stream of `emit` lines."""

    def __init__(self, process: subprocess.Popen[str], label: str) -> None:
        self._process = process
        self._label = label
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        assert process.stdout is not None and process.stderr is not None
        self._readers = (
            threading.Thread(target=self._read_events, args=(process.stdout,), daemon=True),
            threading.Thread(target=self._forward, args=(process.stderr,), daemon=True),
        )
        for reader in self._readers:
            reader.start()

    def _read_events(self, stream: IO[str]) -> None:
        for line in stream:
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if isinstance(parsed, dict) and isinstance(parsed.get("event"), str):
                with self._lock:
                    self._events.append(parsed)

    def _forward(self, stream: IO[str]) -> None:
        for line in stream:
            sys.stderr.write(f"[{self._label}] {line}")
            sys.stderr.flush()

    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def returncode(self) -> int | None:
        code = self._process.poll()
        if code is not None:
            # The process has exited; let the reader finish the last lines it buffered, so a
            # final `granted` or `done` is not read as a silent exit.
            self._readers[0].join(timeout=2.0)
        return code

    def terminate(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._process.kill()


Spawner = Callable[[Sequence[str], str], Child]


def spawn_mailweave(arguments: Sequence[str], label: str) -> Child:
    """`python -m mailweave.cli <arguments>` with this process's own interpreter.

    The same interpreter, so the child runs the same installed product this server does: in
    the extension that is the bundled Python, never whatever `python3` a machine has.
    """
    # The same isolation the launcher started this process with: `-I` ignores `PYTHON*`
    # variables and the user's site directory, so the child cannot import anything the
    # extension did not ship.
    isolation = ["-I"] if sys.flags.isolated else []
    process = subprocess.Popen(
        [sys.executable, *isolation, "-m", "mailweave.cli", *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=dict(os.environ),
    )
    return EventChild(process, label)
