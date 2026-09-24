"""Orivra: source-independent evidence retrieval.

MailWeave is Orivra's Gmail engine, and it is not renamed by anything here. The `mailweave`
Python packages, the `mailweave` CLI, its configuration paths and the four `mailweave_*` MCP
wire tools keep the names and the behaviour v0.1 froze at tag `v0.1`; Orivra is a layer
above them that adds sources, and a layer that renamed the thing underneath it would break
every client that already speaks to it.

What this package holds, in the order it was built:

* `orivra.contracts` - the source-independent schemas (plan §4);
* `orivra.recognise` - the gates a source-stated assertion has to pass, computed;
* `orivra.adapter` - the boundary a connector implements;
* `orivra.gmail_adapter` - that boundary over the existing MailWeave stack;
* `orivra.registry` - which connectors this installation has, and their state;
* `orivra.surface` - the MCP server, mounting the four `mailweave_*` tools unchanged.
"""

from __future__ import annotations

__version__ = "0.2.0b1"

__all__ = ["__version__"]
