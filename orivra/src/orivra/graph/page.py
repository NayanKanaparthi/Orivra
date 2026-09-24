"""Paging a stored graph through tool calls, because resources are optional and tools are not.

Plan §4: *every `orivra://` URI is readable through `orivra_expand`; a client that ignores
resources entirely loses nothing*. The full projection does not fit inside the host's result
cap, so the resource serves it whole and this pages it. Same shapes either way - `project`'s
node and edge forms, not reduced ones - because a client that took the tool route and one that
took the resource route must be able to compare notes.

Three rules make a page trustworthy, and each exists because its absence is a silent failure:

**Bounded by characters, not by count.** A node with three supporting references is not the
size of a person node, and a fixed page size either wastes the budget or blows the cap.

**An item that cannot fit is named, not dropped and not shipped.** The first version always
returned at least one item, on the reasoning that a page returning nothing is a cursor that
never advances. That is true and it was the wrong fix: it shipped an item over the cap, and the
host cuts an oversized response where nothing can declare the cut. Now an item larger than the
whole budget yields a page with **no items and an explicit `oversized` result** naming it, plus
a cursor past it, so the caller can step over it and keep going. It is a terminal fact about
that item and a recoverable one about the page.

**A continuation is bound to the view it came from.** Positions are indices into an ordered
list, and that list changes: an expansion adds nodes, and the live access gate can withhold
different rows on the next call than it did on this one. A bare index carried across either
would skip or repeat evidence, silently. Every page therefore carries a `view` token over the
revision **and the disclosed content**, and a cursor presented with a different token is
refused rather than honoured.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

#: How much of the host's result cap one page of graph content may spend. The rest is the
#: envelope around it - the query id, the counts, the cursor, the mirror text - and a page
#: that filled the whole cap would leave no room for the thing that says where to go next.
PAGE_CHAR_BUDGET: int = 16_000


class Selection(StrEnum):
    """Which part of the graph a page is of."""

    NODES = "nodes"
    EDGES = "edges"
    OMISSIONS = "omissions"
    #: The links the bodies carried that no node represents. A selection of its own because it
    #: is the one list `orivra_ask` may compact out of its block, and a list with no page to
    #: serve it cannot be compacted without losing it.
    LINKS = "links"


class PageState(StrEnum):
    """What happened to this page, in the caller's own terms."""

    #: Items were returned. `next_cursor` continues, or is `None` at the end.
    OK = "ok"
    #: One item is larger than the whole page budget, so no page can carry it. **Recoverable**:
    #: the cursor is past it and the rest of the selection is reachable. The item is named so
    #: the caller can fetch it another way rather than discovering a hole.
    OVERSIZED = "oversized"
    #: The continuation was taken against a different view of the graph. **Terminal for this
    #: cursor**: the caller restarts the selection rather than resuming into a list that has
    #: moved underneath them.
    STALE_CURSOR = "stale_cursor"


class StaleCursor(ValueError):
    """A continuation presented against a view it was not taken from.

    Refused rather than honoured. An index into a list that has changed length or content is a
    cursor that skips or repeats rows, and both failures are silent - the caller assembles a
    set that looks complete and is not. Restarting the selection is cheap; a wrong answer a
    caller believes is not.
    """


def view_token(revision: int, identities: Sequence[str]) -> str:
    """A short digest over what this view actually holds.

    The revision alone is not enough, and that gap is the point. A graph's revision moves when
    an expansion merges, but the **disclosed** content can change with no merge at all: the
    live access gate asks the source on every page, and a message deleted or a grant narrowed
    between two calls changes which rows a cursor indexes into. The digest is over the item
    identities in order, so any of those shows up as a different token.
    """
    digest = hashlib.sha256(f"r{revision}".encode())
    for identity in identities:
        digest.update(b"\x1f")
        digest.update(identity.encode())
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class Page:
    """One page, the cursor that continues it, and the view both belong to."""

    select: Selection
    items: tuple[dict[str, Any], ...]
    #: Index of the first item **not** in this page, or `None` when the page is the last one.
    #: An index rather than an opaque token: the order is stable within a view, and the `view`
    #: field below is what makes presenting it back safe.
    next_cursor: int | None
    total: int
    returned_from: int
    revision: int
    #: The digest of the view this page was taken from. A caller passes it back with the
    #: cursor; a mismatch is refused.
    view: str
    state: PageState = PageState.OK
    #: Set when `state` is `OVERSIZED`: which item, and how big it was against the budget.
    oversized: dict[str, Any] | None = None

    @property
    def complete(self) -> bool:
        return self.next_cursor is None


def paginate(
    items: Sequence[Any],
    *,
    select: Selection,
    render: Callable[[Any], dict[str, Any]],
    identity: Callable[[Any], str],
    cursor: int,
    revision: int,
    expect_view: str | None = None,
    budget: int = PAGE_CHAR_BUDGET,
    cost: Callable[[dict[str, Any]], int] | None = None,
) -> Page:
    """Take items from `cursor` until the next would not fit, or say why none could.

    `expect_view` is the token the caller received with the cursor. `None` means a first page,
    where there is nothing to check against. Any other value must equal this view's token or
    the call is refused: resuming into a list that has changed is how a caller silently skips
    or repeats evidence, and it cannot be detected from the outside.

    `cost` is what one rendered item spends, and it exists because **a page is charged for
    what the host is handed, not for one projection of it**. The default is the serialised
    JSON, which was right while the text mirror was empty. A caller that also renders these
    items as text passes a cost covering both; the page then holds fewer items and the rest
    stay reachable through the continuation, which is what a page is for. The alternative -
    leaving the budget measuring half the response - spends characters no budget knows about
    and pushes a full page past a cap that cannot then declare the cut.
    """
    view = view_token(revision, [identity(one) for one in items])
    if expect_view is not None and expect_view != view:
        raise StaleCursor(
            f"this cursor was taken against view {expect_view} and the graph now reads "
            f"{view}. Between the two calls the graph was extended, or the live access check "
            "disclosed a different set - either way the positions have moved. Start this "
            "selection again rather than resuming into a list that shifted underneath it"
        )
    if cursor < 0 or cursor > len(items):
        raise ValueError(
            f"cursor {cursor} is outside this selection, which holds {len(items)} item(s)"
        )

    taken: list[dict[str, Any]] = []
    spent = 0
    index = cursor
    while index < len(items):
        rendered = render(items[index])
        size = len(json.dumps(rendered, default=str)) if cost is None else cost(rendered)
        if not taken and size > budget:
            # **Named, not shipped and not dropped.** Returning it would hand the host a
            # response it cuts where nothing can declare the cut; dropping it would leave a
            # hole the caller has no way to see. The cursor steps past so the rest stays
            # reachable, and the item is identified so it can be fetched another way.
            return Page(
                select=select,
                items=(),
                next_cursor=index + 1 if index + 1 < len(items) else None,
                total=len(items),
                returned_from=cursor,
                revision=revision,
                view=view,
                state=PageState.OVERSIZED,
                oversized={
                    "identity": identity(items[index]),
                    "position": index,
                    "chars": size,
                    "budget": budget,
                    "why": (
                        "this single item is larger than a whole page, so no page can carry "
                        "it without exceeding the response cap. The cursor has stepped past "
                        "it; the rest of this selection is still reachable"
                    ),
                },
            )
        if taken and spent + size > budget:
            break
        taken.append(rendered)
        spent += size
        index += 1
    return Page(
        select=select,
        items=tuple(taken),
        next_cursor=index if index < len(items) else None,
        total=len(items),
        returned_from=cursor,
        revision=revision,
        view=view,
    )


__all__ = [
    "PAGE_CHAR_BUDGET",
    "Page",
    "PageState",
    "Selection",
    "StaleCursor",
    "paginate",
    "view_token",
]
