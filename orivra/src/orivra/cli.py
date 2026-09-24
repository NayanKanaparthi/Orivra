"""`orivra` - the command line, which is deliberately almost nothing.

**Configuration, credentials and the token store are MailWeave's**, unchanged and unmoved.
`orivra serve` starts the MailWeave runtime that `mailweave serve` starts - the same config
path, the same credential file, the same `~/.local/state/mailweave/` store, the same startup
refusals - and then serves the Orivra tool surface over it. There is no `orivra auth`, no
`orivra config` and no second store: a second credential path would be a second refresh
clock against one mailbox, and the first symptom of that is two watermarks disagreeing.

So this module has one command, and everything else the operator needs is `mailweave`'s:
`mailweave auth login`, `mailweave doctor`, `mailweave config`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from mailweave.surface.runtime import announce, start
from orivra import __version__
from orivra.registry import ConnectorRegistry
from orivra.surface.server import run_stdio, tool_list
from orivra.surface.service import OrivraService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orivra",
        description=(
            "Orivra: source-independent evidence retrieval. Credentials, configuration and "
            "the token store are MailWeave's - use `mailweave auth login`, `mailweave "
            "doctor` and `mailweave config` for those."
        ),
    )
    parser.add_argument("--version", action="version", version=f"orivra {__version__}")
    subcommands = parser.add_subparsers(dest="command", required=True)
    serve = subcommands.add_parser("serve", help="serve the Orivra MCP surface over stdio")
    serve.add_argument(
        "--client",
        type=Path,
        required=True,
        help="path to the installed OAuth client JSON, as `mailweave serve` takes it",
    )
    serve.add_argument("--config", type=Path, default=None, help="path to the config file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """`orivra serve`, and nothing else yet.

    The startup banner goes to **stderr**, because stdout is the MCP transport and a byte
    written there is a malformed JSON-RPC frame. That is `mailweave.surface.runtime`'s rule
    and `announce` is its function, called rather than reimplemented.
    """
    arguments = build_parser().parse_args(argv)
    runtime = start(config_path=arguments.config, client_path=arguments.client)
    try:
        announce(runtime.report)
        print(
            f"orivra serve: ready on stdio ({len(tool_list().tools)} read-only tools, "
            "four of them MailWeave's, unchanged)",
            file=sys.stderr,
        )
        service = OrivraService(registry=ConnectorRegistry.from_runtime(runtime))
        run_stdio(service)
    finally:
        runtime.close()
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
