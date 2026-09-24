"""The call's wall-clock allowance, applied at the socket (2026-09-21, second repair).

**What the first repair bounded, and what it did not.** `GmailClient._request` binds a
`Deadline` per tool call and gives every attempt `httpx.Timeout(min(30 s, remaining))`. An
`httpx` timeout is **per operation**: it is the most one connect, one TLS handshake, one
socket write or one socket *read* may wait. It is not the most a request may take. A response
whose body arrives a few bytes at a time, each chunk inside the read window, reads for as long
as the sender keeps sending; a credential refresh that runs before the first attempt runs
under the token endpoint's own 30 s and no deadline at all. Both are "slow, not stalled", and
both walked past the allowance the first repair enforced.

**Where the bound has to live.** `httpx` has no total-time timeout and its synchronous
client cannot be interrupted from the thread that is waiting in it; the server is one event
loop with no threads (AD A.5c), so a watchdog thread that abandons a late socket is not an
option this architecture allows. What `httpcore` does offer, as public API, is the
`network_backend` a connection pool opens sockets through: every read, write, connect and
handshake passes through it with the timeout `httpx` computed. This module wraps that backend
so each operation's timeout is **the smaller of what `httpx` asked for and what is left of the
bound deadline, read at that moment**. A trickling body is then cut at the deadline by its
next read, a hanging token exchange by its read, and a handshake that stalls by its own step -
each with the transport's ordinary `TimeoutException`, which `_request` already reads as the
deadline's when the deadline is spent. Nothing here interrupts anything; it only shortens the
wait the transport was about to make.

**How the backend learns the deadline.** The pool is built once per process and shared by
every per-call `GmailClient` and by the token provider (`surface/runtime.start`), so the
deadline cannot be a constructor argument. It is a `contextvars.ContextVar` this module owns:
`GmailClient.bind_deadline` publishes the call's deadline into it, and `surface/server.in_band`
- the one function every tool call passes through - enters `call_scope()` so that whatever a
call publishes is reset when the call ends. A stale deadline from a previous call therefore
cannot clamp the next call's first read (it would have refused it: a spent deadline leaves
under `MIN_ATTEMPT_MS`). A path that never binds one - the CLI's one-shot commands, the
preflight probes, `mailweave auth login` - reads `None` here and gets the transport's own
timeouts, exactly as before.

**Two things it cannot bound, stated.** Name resolution inside `socket.create_connection`
runs before the socket exists and honours no timeout; and the wait for a free pool slot is
an `httpcore` event with the `pool` timeout, not a socket operation. The first is a property
of `getaddrinfo`; the second cannot occur with one call in flight at a time (A.5c's lock).

**Private-attribute swap, pinned.** `httpx.HTTPTransport` builds its `httpcore.ConnectionPool`
without exposing `network_backend`, so `bounded_transport` replaces the pool's backend after
construction. The two attributes it touches - `HTTPTransport._pool` and
`ConnectionPool._network_backend` - are asserted to exist and to have the expected types at
construction, so an `httpx`/`httpcore` upgrade that moves them fails the server at start
rather than silently building an unbounded client. `uv.lock` pins `httpx 0.28.1` and
`httpcore 1.0.9`, the versions this was written against.
"""

from __future__ import annotations

import ssl
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum
from time import monotonic
from typing import Any, Final, Protocol

import httpcore
import httpx

from mailweave.diagnostics import lifecycle


class Allowance(Protocol):
    """What the backend needs from a deadline: how much is left, in milliseconds, now."""

    def remaining_ms(self) -> float: ...


_BOUND: ContextVar[Allowance | None] = ContextVar("mailweave.net.deadline", default=None)
_IN_SCOPE: ContextVar[bool] = ContextVar("mailweave.net.deadline.scope", default=False)


def bound_allowance() -> Allowance | None:
    """The deadline published for the call in flight, or `None` when no call bound one."""
    return _BOUND.get()


def publish(allowance: Allowance | None) -> None:
    """Make `allowance` the bound deadline for the rest of the current call scope.

    **Outside a scope this publishes nothing.** The clamp is a property of a tool call, and
    a call is what `call_scope` delimits; a `GmailClient` bound directly - a harness, a test,
    a one-shot command - keeps its own per-attempt bound and leaves the sockets alone, so a
    deadline bound with no call to end it cannot sit in the context and clamp whatever runs
    next.
    """
    if _IN_SCOPE.get():
        _BOUND.set(allowance)


@contextmanager
def published(allowance: Allowance | None) -> Iterator[None]:
    """`allowance` is the bound deadline for the duration of the block, and only then.

    **Per request, not per client** (2026-09-22, the retest's second finding). The first
    version published a deadline when it was bound to a client and left it in the context
    until the call ended. Inside one tool call more than one `GmailClient` can make requests
    - `orivra_ask` runs MailWeave's search and then the adapter's own ladder, probes and
    fetches - and a client opened *without* a deadline was clamped by whichever deadline the
    previous client had published, spent or not, while its own `_request` had no deadline to
    read the cut as. The sockets answered to one clock and the retry loop to another. Now the
    requesting client publishes its own deadline, or `None`, around each request, and what
    was published before is put back afterwards; the clamp always belongs to the client whose
    bytes are on the wire.
    """
    if not _IN_SCOPE.get():
        yield
        return
    token = _BOUND.set(allowance)
    try:
        yield
    finally:
        _BOUND.reset(token)


@contextmanager
def call_scope() -> Iterator[None]:
    """Isolate one tool call's binding: whatever it publishes is reset when it ends."""
    bound = _BOUND.set(None)
    scoped = _IN_SCOPE.set(True)
    try:
        yield
    finally:
        _BOUND.reset(bound)
        _IN_SCOPE.reset(scoped)


class Operation(StrEnum):
    """The socket operations the clamp stands in front of, each with its own typed timeout."""

    CONNECT = "connect"
    TLS = "tls"
    WRITE = "write"
    READ = "read"


#: The transport's own timeout type for each operation - the one `httpcore` itself raises
#: when that operation's socket timeout fires, and the one `httpx` maps to its
#: `TimeoutException` subclass of the same name. Refusing with these and not with anything
#: else is what lets `GmailClient._request` read the refusal as the deadline's.
_REFUSAL: Final[Mapping[Operation, type[httpcore.TimeoutException]]] = {
    Operation.CONNECT: httpcore.ConnectTimeout,
    Operation.TLS: httpcore.ConnectTimeout,
    Operation.WRITE: httpcore.WriteTimeout,
    Operation.READ: httpcore.ReadTimeout,
}


def allowance(operation: Operation, timeout: float | None) -> float | None:
    """`timeout`, or what is left of the bound deadline, whichever is smaller - or a refusal.

    **A spent deadline refuses the operation; it never hands the socket a zero** (2026-09-22,
    the retest's finding). The first version returned `0.0` once nothing was left, on the
    reasoning that a zero socket timeout fires at once. It does not: `settimeout(0.0)` puts a
    socket into *non-blocking* mode, and `ssl.SSLContext.wrap_socket` refuses a non-blocking
    socket with `ValueError: do_handshake_on_connect should not be specified for non-blocking
    sockets` - which is not a timeout, is mapped by nothing in `httpcore` or `httpx`, and
    walked out of `GmailClient._request` as a bare exception: an internal error to the client
    instead of the `budget_exhausted` decline the deadline exists to produce. A read with a
    zero timeout is `BlockingIOError` by the same mechanism.

    So an operation the deadline has no time for is refused **here**, before the transport
    is entered, with the transport's own typed timeout for that operation: `ConnectTimeout`
    for a connect or a handshake, `WriteTimeout`, `ReadTimeout`. `httpx` maps each to its
    `TimeoutException`, and `_request` reads a timeout under a spent deadline as the
    deadline's. Nothing extends the deadline and nothing sleeps: a refusal is immediate.

    `None` from the transport means "wait forever"; under a bound deadline that becomes
    "wait what is left".
    """
    bound = _BOUND.get()
    if bound is None:
        return timeout
    left_s = bound.remaining_ms() / 1000.0
    if left_s <= 0.0:
        raise _REFUSAL[operation](
            f"the call's wall-clock allowance is spent; the {operation.value} was refused "
            "before the socket was touched"
        )
    return left_s if timeout is None else min(timeout, left_s)


def clamp(timeout: float | None) -> float | None:
    """`allowance` for a read, kept under the name the first version published."""
    return allowance(Operation.READ, timeout)


def _elapsed_ms(started: float) -> int:
    return max(0, int((monotonic() - started) * 1000.0))


class DeadlineStream(httpcore.NetworkStream):
    """One socket's stream with every operation refused or clamped by the bound deadline.

    Each operation's wall clock is also reported to the call diagnostic (`observe`), so an
    end line can say where a call's time went: waiting to connect (which includes name
    resolution, the one wait nothing here can bound), in the handshake, writing, or waiting
    for bytes. Numbers only.
    """

    def __init__(self, inner: httpcore.NetworkStream) -> None:
        self._inner = inner

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        bounded = allowance(Operation.READ, timeout)
        started = monotonic()
        try:
            return self._inner.read(max_bytes, timeout=bounded)
        finally:
            lifecycle().observe(read_ms=_elapsed_ms(started))

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        bounded = allowance(Operation.WRITE, timeout)
        started = monotonic()
        try:
            self._inner.write(buffer, timeout=bounded)
        finally:
            lifecycle().observe(write_ms=_elapsed_ms(started))

    def close(self) -> None:
        self._inner.close()

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        bounded = allowance(Operation.TLS, timeout)
        started = monotonic()
        try:
            secured = self._inner.start_tls(
                ssl_context, server_hostname=server_hostname, timeout=bounded
            )
        finally:
            lifecycle().observe(tls_ms=_elapsed_ms(started))
        return DeadlineStream(secured)

    def get_extra_info(self, info: str) -> Any:
        return self._inner.get_extra_info(info)


class DeadlineBackend(httpcore.NetworkBackend):
    """A network backend whose sockets are `DeadlineStream`s over the wrapped backend's."""

    def __init__(self, inner: httpcore.NetworkBackend) -> None:
        self._inner = inner

    @property
    def inner(self) -> httpcore.NetworkBackend:
        return self._inner

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        bounded = allowance(Operation.CONNECT, timeout)
        started = monotonic()
        try:
            stream = self._inner.connect_tcp(
                host,
                port,
                timeout=bounded,
                local_address=local_address,
                socket_options=socket_options,
            )
        finally:
            # Name resolution runs inside this call and honours no timeout; this figure is
            # where it shows up, which is why it is reported apart from the handshake.
            lifecycle().observe(connect_ms=_elapsed_ms(started), sockets=1)
        return DeadlineStream(stream)

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        bounded = allowance(Operation.CONNECT, timeout)
        started = monotonic()
        try:
            stream = self._inner.connect_unix_socket(
                path, timeout=bounded, socket_options=socket_options
            )
        finally:
            lifecycle().observe(connect_ms=_elapsed_ms(started), sockets=1)
        return DeadlineStream(stream)

    def sleep(self, seconds: float) -> None:
        """`httpcore`'s own pause between connection retries. Never past the deadline, and
        never at all once it is spent: the next connect refuses, so there is nothing to
        wait for."""
        bound = _BOUND.get()
        if bound is None:
            self._inner.sleep(seconds)
            return
        left_s = bound.remaining_ms() / 1000.0
        if left_s <= 0.0:
            return
        self._inner.sleep(min(seconds, left_s))


def bounded_transport(
    *, network_backend: httpcore.NetworkBackend | None = None, **kwargs: object
) -> httpx.HTTPTransport:
    """An `httpx.HTTPTransport` whose sockets honour the bound deadline.

    `network_backend` replaces the socket-opening backend underneath the clamp - a scripted
    backend in the tests, so a body that trickles or a token endpoint that never answers can
    be driven through the real `httpx`/`httpcore` stack with no socket. It is wrapped, not
    trusted: the clamp sits above whatever is passed.
    """
    transport = httpx.HTTPTransport(**kwargs)  # type: ignore[arg-type]
    pool = getattr(transport, "_pool", None)
    if not isinstance(pool, httpcore.ConnectionPool):
        raise RuntimeError(
            "httpx.HTTPTransport no longer holds an httpcore.ConnectionPool at `_pool`; the "
            "deadline clamp cannot be installed and this server will not run unbounded. Pin "
            "httpx/httpcore to the locked versions or re-point mailweave.net.deadline"
        )
    current = getattr(pool, "_network_backend", None)
    if not isinstance(current, httpcore.NetworkBackend):
        raise RuntimeError(
            "httpcore.ConnectionPool no longer holds its NetworkBackend at `_network_backend`; "
            "the deadline clamp cannot be installed and this server will not run unbounded"
        )
    # The seam httpx does not expose: see the module docstring for why, and for the pin.
    pool._network_backend = DeadlineBackend(
        network_backend if network_backend is not None else current
    )
    return transport


def installed_backend(transport: httpx.BaseTransport) -> DeadlineBackend | None:
    """The clamp a transport carries, or `None`. For tests and the startup banner."""
    pool = getattr(transport, "_pool", None)
    backend = getattr(pool, "_network_backend", None)
    return backend if isinstance(backend, DeadlineBackend) else None


__all__ = [
    "Allowance",
    "DeadlineBackend",
    "DeadlineStream",
    "Operation",
    "allowance",
    "bound_allowance",
    "bounded_transport",
    "call_scope",
    "clamp",
    "installed_backend",
    "publish",
    "published",
]
