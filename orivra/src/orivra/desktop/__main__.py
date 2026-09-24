"""`python -m orivra.desktop` - what the extension's launcher script runs.

Takes no arguments in an installation: the launcher names the bundle in
`ORIVRA_DESKTOP_BUNDLE`. `--bundle` and `--home` exist for tests and for the clean-install
proof, which runs an unpacked bundle as a fresh user.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from orivra.desktop.paths import resolve
from orivra.desktop.server import run
from orivra.desktop.setup import Setup


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orivra-beta")
    parser.add_argument("--bundle", type=Path, default=None)
    parser.add_argument("--home", type=Path, default=None)
    arguments = parser.parse_args(argv)
    run(Setup(resolve(arguments.bundle, arguments.home)))
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
