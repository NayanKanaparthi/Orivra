"""The runtime egress allowlist, enforced in code (AD D.8, RR SEC-07).

Exactly two runtime hosts: `gmail.googleapis.com` and `oauth2.googleapis.com` (token
refresh only). The model host is reachable from `mailweave setup-models` alone, which is
a separate command and not part of the server process.

Enforcement is a transport wrapper rather than a convention, and it refuses **before**
the connection is attempted, so a blocked host produces no DNS lookup and no socket.
A network capture proves the property empirically (SEC-07); this makes the property hold
by construction between captures.

**One rejection this module cannot type (R-SEC-004, residue).** `check_url` now raises
`EgressBlocked` for a host it cannot parse, so the direct-call contract holds. Through an
`httpx` *client*, though, a malformed internationalised host
(`https://xn--gmailgoogleapis-3ye.com/`) is decoded while the `Request` object is built,
which happens before any transport - and therefore before any MailWeave code - is
consulted. That path raises `idna`'s own exception and there is no seam here at which to
convert it. It still fails closed: nothing is sent, and the recording-transport tests in
`tests/test_egress.py` assert exactly that, and assert the exception type is `idna`'s
rather than pretending otherwise.
"""

from __future__ import annotations

from collections.abc import Iterable

import httpx

from mailweave.constants import RUNTIME_EGRESS_ALLOWLIST
from mailweave.errors import EgressBlocked
from mailweave.net.deadline import bounded_transport


def check_url(
    url: httpx.URL | str,
    allowlist: Iterable[str] = RUNTIME_EGRESS_ALLOWLIST,
    suffixes: Iterable[str] = (),
) -> None:
    """Raise `EgressBlocked` unless `url`'s host is on the allowlist and the scheme is https.

    `EgressBlocked` is the *only* failure this function raises, which is what lets a caller
    wrap a request in one `except` clause. R-SEC-004 found that was not true: `httpx`
    decodes an internationalised host lazily, so reading `.host` on
    `https://xn--gmailgoogleapis-3ye.com/` raised `idna.core.InvalidCodepoint` straight
    through this function. The request never reached the transport - it failed closed -
    but a caller following the docstring saw an unhandled third-party exception rather
    than a refusal.

    A host this process cannot even parse is refused for that reason. It is not on the
    allowlist, since the allowlist holds two exactly-spelled hosts, and the parse failure
    is reported rather than absorbed so a malformed host never reads as an ordinary
    allowlist miss.

    `suffixes` defaults to **empty**, so every runtime call behaves exactly as before: the
    runtime allowlist is exactly-spelled hosts and nothing else. It exists for one caller,
    `models/provision.py`, because large model files are served by redirect to a regional
    content host and the region is the caller's, not ours. A suffix is a weaker rule than an
    exact match, which is precisely why it is passed at a call site rather than added to a
    constant: the pair the server runs against never acquires one.

    A suffix must start with a dot and carry at least two more labels, so `.co` and `.com`
    cannot be passed. A host matches only if it *ends with* the suffix and is longer than it,
    so `evilhf.co` does not match `.hf.co` while `us.aws.cdn.hf.co` does.
    """
    parsed = url if isinstance(url, httpx.URL) else httpx.URL(url)
    allowed = frozenset(allowlist)
    try:
        scheme, host = parsed.scheme, parsed.host
    except Exception as failure:
        raise EgressBlocked(
            f"refusing an outbound request whose host could not be parsed ({failure!r}): "
            "a host this process cannot decode is not one of the two allowlisted hosts, "
            "and an unparseable host is refused rather than guessed at (AD D.8)"
        ) from failure
    if scheme != "https":
        raise EgressBlocked(
            f"refusing a non-https request to {host or url!s}: MailWeave speaks only "
            "https to its two allowlisted hosts"
        )
    permitted_suffixes = tuple(
        suffix
        for suffix in suffixes
        if suffix.startswith(".") and suffix.count(".") >= 2 and len(suffix) > 4
    )
    if host in allowed:
        return
    if host is not None and any(
        host.endswith(suffix) and len(host) > len(suffix) for suffix in permitted_suffixes
    ):
        return
    # Name the allowlist accurately rather than generically. Saying "runtime" for the setup
    # allowlist would be false, and dropping the word entirely loses what
    # `test_the_unparseable_host_path_does_not_swallow_a_real_allowlist_decision` is
    # actually checking: that a refusal says which allowlist refused.
    which = "runtime " if allowed == frozenset(RUNTIME_EGRESS_ALLOWLIST) else ""
    raise EgressBlocked(
        f"refusing an outbound request to {host!r}: the {which}egress allowlist is exactly "
        f"{sorted(allowed)}"
        + (f" plus hosts under {sorted(permitted_suffixes)}" if permitted_suffixes else "")
        + " (AD D.8). The model host is reachable only from `mailweave setup-models`, "
        "never from the server process."
    )


class AllowlistTransport(httpx.BaseTransport):
    """Synchronous transport that fails closed on any host outside the allowlist."""

    def __init__(
        self,
        inner: httpx.BaseTransport | None = None,
        allowlist: Iterable[str] = RUNTIME_EGRESS_ALLOWLIST,
        suffixes: Iterable[str] = (),
    ) -> None:
        # **The socket-opening transport honours the call's deadline** (2026-09-21, second
        # repair). `bounded_transport` is `httpx.HTTPTransport` with its sockets' timeouts
        # clamped to what is left of the deadline `GmailClient.bind_deadline` publishes; see
        # `net/deadline.py`. An injected `inner` is a test's `MockTransport` and opens no
        # socket, so there is nothing there to clamp and it is used as given.
        self._inner = inner if inner is not None else bounded_transport()
        self._allowlist = frozenset(allowlist)
        self._suffixes = tuple(suffixes)

    @property
    def inner(self) -> httpx.BaseTransport:
        return self._inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        check_url(request.url, self._allowlist, self._suffixes)
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


class AsyncAllowlistTransport(httpx.AsyncBaseTransport):
    """Asynchronous counterpart, used by the server's request path."""

    def __init__(
        self,
        inner: httpx.AsyncBaseTransport | None = None,
        allowlist: Iterable[str] = RUNTIME_EGRESS_ALLOWLIST,
        suffixes: Iterable[str] = (),
    ) -> None:
        self._inner = inner if inner is not None else httpx.AsyncHTTPTransport()
        self._allowlist = frozenset(allowlist)
        self._suffixes = tuple(suffixes)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        check_url(request.url, self._allowlist, self._suffixes)
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def build_client(
    *,
    inner: httpx.BaseTransport | None = None,
    allowlist: Iterable[str] = RUNTIME_EGRESS_ALLOWLIST,
    suffixes: Iterable[str] = (),
    **kwargs: object,
) -> httpx.Client:
    """The only supported way to get an HTTP client in server code.

    `allowlist` defaults to the runtime pair and is widened by exactly one caller:
    `models/provision.py`, which passes `SETUP_EGRESS_ALLOWLIST` so `mailweave
    setup-models` can reach the model host. Naming the set at the call site rather than
    adding two hosts to the runtime constant is what keeps PF-5 meaningful - a cold server
    start with the model host blocked has to complete, and it could not fail that test if
    the host were on the allowlist the server itself uses.

    "Only supported" was a docstring and nothing else until round 5 (R-ARCH-006). The
    `unwrapped-http-client` guard now refuses `httpx.Client(...)` /
    `httpx.AsyncClient(...)` anywhere in `server/**` except this module, so the adoption of
    the allowlist transport is enforced rather than requested. The guard states its own
    limits in `tools/guards/sweeps.py`.

    `inner` replaces the socket-opening transport underneath the allowlist - an
    `httpx.MockTransport` in the WS-02 tests. It exists so that a test of the Gmail client
    exercises the **real** URL construction, headers and allowlist check and stops only at
    the socket, rather than faking the client's own methods and testing nothing. A fake
    handed in here is still wrapped: an inner transport does not bypass `check_url`, and
    `test_a_mock_transport_is_still_behind_the_allowlist` is what holds that.
    """
    return httpx.Client(
        transport=AllowlistTransport(inner, allowlist=allowlist, suffixes=suffixes),
        **kwargs,  # type: ignore[arg-type]
    )


def build_async_client(
    *,
    inner: httpx.AsyncBaseTransport | None = None,
    allowlist: Iterable[str] = RUNTIME_EGRESS_ALLOWLIST,
    suffixes: Iterable[str] = (),
    **kwargs: object,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=AsyncAllowlistTransport(inner, allowlist=allowlist, suffixes=suffixes),
        **kwargs,  # type: ignore[arg-type]
    )
