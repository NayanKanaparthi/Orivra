"""`python -m mailweave_harness.preflight` - list, plan, or run the Loop-0 probes.

`--list` and `--plan` need nothing: no credential, no network, no mailbox. `--plan` is the
reviewable artefact, printing every probe's falsification condition and its consequence, and
it is what should be read before anything touches a real mailbox.

`--run` needs the owner's credential and the owner's machine. It reads the refresh token the
consent flow stored and exchanges it for an access token; there is no path here that can start
a consent, so this cannot be run from an environment that has never had one.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mailweave.auth.consent import StoredTokenProvider, read_installed_client
from mailweave.auth.tokenstore import TokenStore
from mailweave.config import DEFAULT_STATE_DIR
from mailweave.gmail import GmailClient
from mailweave_harness.preflight.runner import PLAN, plan_text, record_results, run_probes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mailweave-preflight", description=__doc__)
    parser.add_argument("--list", action="store_true", help="probe ids, one per line")
    parser.add_argument("--plan", action="store_true", help="the full run plan")
    parser.add_argument("--run", action="store_true", help="execute against a live mailbox")
    parser.add_argument("--probe", action="append", default=None, help="run only these ids")
    parser.add_argument("--out", type=Path, default=Path("preflight-records"))
    parser.add_argument("--client", type=Path, default=Path("mailweave-server-oauth.json"))
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument(
        "--exclusive-window",
        action="store_true",
        help="declare that no other run is in flight on this project (PF-16); required by PF-3",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help=(
            "PF-2 only: measure this thread instead of letting the runner select one. "
            "Use when you know a thread that actually carries In-Reply-To/References; "
            "without it the runner probes up to 4 candidates, largest thread first"
        ),
    )
    parser.add_argument(
        "--freshness-window-s",
        type=float,
        default=0.0,
        help="how long to watch for arrivals; 0 skips the watch and reports inconclusive",
    )
    parser.add_argument(
        "--freshness-poll-s",
        type=float,
        default=30.0,
        help="seconds between history.list polls inside the freshness window",
    )
    args = parser.parse_args(argv)

    if args.list:
        for probe in PLAN.probes:
            print(probe.id)
        return 0
    if not args.run:
        print(plan_text())
        return 0

    client = GmailClient(
        token=StoredTokenProvider(
            client=read_installed_client(args.client),
            store=TokenStore(args.state_dir.expanduser() / "credentials.json"),
        )
    )
    try:
        results = run_probes(
            client,
            selected=args.probe,
            exclusive_window=args.exclusive_window,
            freshness_window_s=args.freshness_window_s,
            freshness_poll_s=args.freshness_poll_s,
            headers_thread_id=args.thread_id,
        )
    finally:
        client.close()
    summary = record_results(results, args.out)
    for result in results:
        print(f"{result.spec.id}: {result.verdict.value}")
    print(f"\nrecord written to {summary}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
