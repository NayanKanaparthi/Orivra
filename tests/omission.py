"""Readers for the round-29 omission shapes, shared by the tests that inspect them.

`not_included_sources[]` is a list of blocks - one reason, stated once, over the sources it
applies to - and `withheld` is complemented by `withheld_groups[]`. Tests that want the flat
list of sources or the flat set of withheld threads read them through here, so the block
shape is known in one place and the tests keep saying what they assert about rather than how
the wire nests it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def not_included_entries(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every not-included source, with its block's `why` copied onto it for convenience."""
    out: list[dict[str, Any]] = []
    for block in payload.get("not_included_sources") or ():
        for source in block.get("sources") or ():
            out.append({**source, "why": block.get("why")})
    return out


def not_included_whys(payload: Mapping[str, Any]) -> list[str]:
    return [str(block.get("why")) for block in payload.get("not_included_sources") or ()]


def withheld_threads(payload: Mapping[str, Any]) -> set[str]:
    """Threads named by any withheld record **or** group."""
    named = {str(record["thread_id"]) for record in payload.get("withheld") or ()}
    named |= {str(group["thread_id"]) for group in payload.get("withheld_groups") or ()}
    return named


def withheld_message_count(payload: Mapping[str, Any]) -> int:
    """Messages withheld, counting each group's `message_count` once."""
    return len(payload.get("withheld") or ()) + sum(
        int(group["message_count"]) for group in payload.get("withheld_groups") or ()
    )


def affordances_of_omissions(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for record in payload.get("withheld") or ():
        yield record["affordance"]
    for group in payload.get("withheld_groups") or ():
        yield group["affordance"]
    for entry in not_included_entries(payload):
        yield entry["affordance"]
