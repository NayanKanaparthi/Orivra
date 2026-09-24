"""WS-15: the MCP server surface (AD D.1, D.11; contract MCP-01..07).

Seven modules, split by what each one is allowed to decide:

  * `tools` - the four compile-time-constant tools, and every sentence a caller's model
    reads about MailWeave, each one a `Claim` naming the test that executes it;
  * `arguments` - the caller's mapping into typed requests, and the first place D.11's
    partition bites (`view: "raw"` is a declared refusal; a malformed call is a protocol
    error);
  * `rendering` - one serialisation through the envelope's own chokepoint, and the text
    mirror projected from it, with a round-trip table so the two cannot drift;
  * `partition` - D.11's in-band / tool-error split, read from `ERROR_SURFACE` and never
    restated;
  * `expansion` - one disclosure path shared by the three tools that expand something
    already named;
  * `service` - the four handlers, which own no policy of their own;
  * `runtime` - startup, and the refusals that happen before a byte of MCP is spoken;
  * `server` - the protocol itself: `mcp.server.lowlevel.Server` over stdio.

**Nothing here re-decides anything.** Depth is `mailweave.disclosure`'s, budgets are
`mailweave.policy`'s, handle validity is `mailweave.handles`', and whether a response may be
emitted at all is `mailweave.envelope`'s. This package chooses which of those to call and
how to say the answer twice without the two answers differing.
"""

from mailweave.surface.arguments import ArgumentInvalid, ToolRefused
from mailweave.surface.partition import declared_result, declined
from mailweave.surface.rendering import Rendered, disagreements, render, text_of
from mailweave.surface.runtime import Runtime, StartupReport, announce, start
from mailweave.surface.server import build_server, call, run_stdio, serve_stdio, tool_list
from mailweave.surface.service import MailweaveService
from mailweave.surface.tools import TOOL_SPECS, UNTRUSTED_DATA_WARNING, Claim, ToolSpec

__all__ = [
    "TOOL_SPECS",
    "UNTRUSTED_DATA_WARNING",
    "ArgumentInvalid",
    "Claim",
    "MailweaveService",
    "Rendered",
    "Runtime",
    "StartupReport",
    "ToolRefused",
    "ToolSpec",
    "announce",
    "build_server",
    "call",
    "declared_result",
    "declined",
    "disagreements",
    "render",
    "run_stdio",
    "serve_stdio",
    "start",
    "text_of",
    "tool_list",
]
