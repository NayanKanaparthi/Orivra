"""What the network layer actually yielded, which is EP §6.4's pool when nothing exposes one.

EP §6.4 defines `pool_recall` over "the system's **pre-disclosure candidate set** (where the
system exposes one; otherwise **the union of messages it fetched, observable at the network
layer**)". Both halves of that sentence are load-bearing here, and the second half is the one
that makes `cut_loss` a usable instrument at all:

  * MailWeave exposes a candidate set only when the semantic rungs run. A query answered at
    L1 emits a `semantic` block with an **empty** `pool_ids`, and the lexical baseline arm
    never fills one at all. Reading an empty block as a pool scores `pool_recall = 0` against
    a recall of 1 and produces a **negative** `cut_loss` - which is impossible under the
    metric's own model, since the shortlist is a subset of the pool.
  * A `cut_loss` that is structurally unmeasurable on the no-reranker arm would make EP
    §6.4's reranker justification rule - "a reranker is justified by the `cut_loss` it
    removes, and by nothing else" - impossible to satisfy or to refuse. The rule would then
    be decided by the instrument rather than by the run.

So this module is the second half of the sentence, implemented at the seam it names. It wraps
the transport *underneath* the egress allowlist (`build_client(inner=...)`), so it observes
what was actually sent and received and cannot widen what the server is allowed to reach.

**Listed and fetched are recorded separately and never merged in the record**, because they
are different claims: an id returned by `messages.list` is one the system *had* and could
have disclosed, and a `messages.get(format=full)` is one whose content it actually took.
`observed` unions them, and a reader who disagrees with that choice can recompute from the
two fields rather than from nothing.

Nothing here can fail a run. A body that will not decode or will not parse is skipped, for
the same reason `MailweaveService._trace` swallows an unwritable disk: instrumentation that
can break the thing it measures is worse than no instrumentation.
"""

from __future__ import annotations

import contextlib
import gzip
import json
import re
import zlib
from dataclasses import dataclass, field
from typing import Any

import httpx

#: `.../users/{user}/messages/{id}` - a body actually fetched. The trailing group refuses a
#: further path segment so `/messages/{id}/attachments/{aid}` does not read as a message id.
_MESSAGE = re.compile(r"/gmail/v1/users/[^/]+/messages/([^/?]+)$")
_THREAD = re.compile(r"/gmail/v1/users/[^/]+/threads/([^/?]+)$")
_LIST = re.compile(r"/gmail/v1/users/[^/]+/messages$")


def _decoded(raw: bytes, encoding: str) -> bytes | None:
    try:
        if encoding == "gzip":
            return gzip.decompress(raw)
        if encoding == "deflate":
            return zlib.decompress(raw)
        if encoding in {"", "identity"}:
            return raw
    except (OSError, zlib.error, EOFError):
        return None
    return None


def _ids_in(node: Any) -> list[str]:
    """Every `id` on a message object in a Gmail response, at any nesting this API uses."""
    found: list[str] = []
    if isinstance(node, dict):
        for key in ("messages", "threads"):
            entries = node.get(key)
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                        found.append(entry["id"])
    return found


@dataclass
class FetchLog:
    """One arm's network observations, drained per case by `take`."""

    listed: set[str] = field(default_factory=set)
    fetched: set[str] = field(default_factory=set)
    #: Every observation ever made, kept so a drained log can still be audited after a run.
    total_listed: int = 0
    total_fetched: int = 0

    @property
    def observed(self) -> frozenset[str]:
        return frozenset(self.listed | self.fetched)

    def take(self) -> frozenset[str]:
        """What was observed since the last call, and reset. Per case, like the trace cursor."""
        out = self.observed
        self.listed.clear()
        self.fetched.clear()
        return out

    def record(self, request: httpx.Request, body: bytes, headers: httpx.Headers) -> None:
        path = request.url.path
        message = _MESSAGE.search(path)
        if message is not None:
            self.fetched.add(message.group(1))
            self.total_fetched += 1
            return
        if not (_LIST.search(path) or _THREAD.search(path)):
            return
        raw = _decoded(body, headers.get("content-encoding", "").strip().lower())
        if raw is None:
            return
        try:
            parsed = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return
        ids = _ids_in(parsed)
        # A `threads.get` at `format=full` returns bodies; at any other format it returns
        # names. The first is a fetch, the second is a listing, and calling both the same
        # thing would credit the pool with content the system never held.
        full = request.url.params.get("format") == "full"
        target = self.fetched if (full and _THREAD.search(path)) else self.listed
        target.update(ids)
        if full and _THREAD.search(path):
            self.total_fetched += len(ids)
        else:
            self.total_listed += len(ids)


class FetchObserver(httpx.BaseTransport):
    """`build_client(inner=...)`'s inner transport, recording as it passes bytes through.

    The response is rebuilt around the **undecoded** bytes with the original headers, so the
    client above decodes exactly as it would have. Decoding happens only for this module's own
    parsing and never reaches the caller.
    """

    def __init__(self, inner: httpx.BaseTransport, log: FetchLog) -> None:
        self._inner = inner
        self._log = log

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._inner.handle_request(request)
        stream = response.stream
        assert isinstance(stream, httpx.SyncByteStream)  # a sync transport, by construction
        raw = b"".join(stream)
        response.close()
        # Instrumentation never fails a run: a body that will not parse costs one case's
        # pool measurement, and `pool_state` reports that as UNMEASURED rather than as zero.
        with contextlib.suppress(Exception):
            self._log.record(request, raw, response.headers)
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            stream=httpx.ByteStream(raw),
            extensions=response.extensions,
        )

    def close(self) -> None:
        self._inner.close()


__all__ = ["FetchLog", "FetchObserver"]
