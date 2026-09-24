"""`python -m mailweave_harness.validation` - run a live validation against the test mailbox.

Read-only. It starts the server exactly as `mailweave serve` does, drives the shipped `call`
path in process, and writes a record of numbers. It never edits a constant: the deadline under
test is passed as a `budget` argument, which `apply_floor` clamps from below only.

The queries are the caller's. Nothing here reads an evaluator file, and `--query` is required
precisely so this cannot ship with a query somebody chose after seeing an answer key.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mailweave.config import DEFAULT_STATE_DIR
from mailweave.surface.runtime import start
from mailweave_harness.validation import deadline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mailweave-validation", description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--client", type=Path, default=Path("mailweave-server-oauth.json"))
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help=(
            "an additional neutral search, run under every arm; repeatable. The "
            "pre-registered structural query always runs and cannot be removed from here"
        ),
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=deadline.DEFAULT_REPEATS,
        help="how many counterbalanced passes (default 3: every arm in every position once)",
    )
    parser.add_argument(
        "--name",
        default="deadline-validation-run2.json",
        help="record filename; a new run must not overwrite an earlier one's evidence",
    )
    parser.add_argument("--out", type=Path, default=Path("validation-records"))
    parser.add_argument(
        "--no-execute-recommendation",
        action="store_true",
        help="do not call the recommended expansion (it costs one extra tool call per arm)",
    )
    args = parser.parse_args(argv)

    runtime = start(config_path=args.config, client_path=args.client)
    try:
        specs = (
            *deadline.PRE_REGISTERED,
            *(deadline.QuerySpec(query) for query in args.query),
        )
        comparison = deadline.compare(
            runtime.service,
            specs=specs,
            repeats=args.repeats,
            execute_recommendation=not args.no_execute_recommendation,
        )
    finally:
        runtime.close()
    verdict = deadline.judge(comparison)
    print(deadline.render(comparison, verdict))
    written = deadline.write_record(comparison, verdict, args.out, name=args.name)
    print(f"\nrecord written to {written}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
