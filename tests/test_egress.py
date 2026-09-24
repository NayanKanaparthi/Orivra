"""The two-host runtime egress allowlist (AD D.8, RR SEC-07).

The property tested is that a blocked request never reaches the inner transport at all -
no DNS, no socket - so a network capture would see nothing rather than a failed attempt.
"""

from __future__ import annotations

import httpx
import pytest

from mailweave.constants import RUNTIME_EGRESS_ALLOWLIST
from mailweave.errors import EgressBlocked
from mailweave.net import (
    AllowlistTransport,
    AsyncAllowlistTransport,
    build_async_client,
    build_client,
    check_url,
)


class RecordingTransport(httpx.BaseTransport):
    """Stands in for the real transport so a blocked request is observably not attempted."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, text="ok")


class RecordingAsyncTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, text="ok")


def test_the_allowlist_is_exactly_the_two_runtime_hosts() -> None:
    """SEC-07 is an exact set assertion: adding a third host is a code change and a review."""
    assert {"gmail.googleapis.com", "oauth2.googleapis.com"} == RUNTIME_EGRESS_ALLOWLIST


@pytest.mark.parametrize("host", sorted(RUNTIME_EGRESS_ALLOWLIST))
def test_allowlisted_hosts_reach_the_inner_transport(host: str) -> None:
    inner = RecordingTransport()
    client = httpx.Client(transport=AllowlistTransport(inner))
    assert client.get(f"https://{host}/gmail/v1/users/me/profile").status_code == 200
    assert [str(r.url.host) for r in inner.requests] == [host]


@pytest.mark.parametrize(
    "url",
    [
        "https://huggingface.co/models/potion-retrieval-32M",  # the model host: setup only
        "https://cdn-lfs.huggingface.co/weights.bin",
        "https://telemetry.example/collect",
        "https://accounts.google.com/o/oauth2/token",  # a Google host, still not allowed
        "https://gmail.googleapis.com.evil.example/",  # suffix attack
    ],
)
def test_a_blocked_host_never_reaches_the_transport(url: str) -> None:
    inner = RecordingTransport()
    client = httpx.Client(transport=AllowlistTransport(inner))
    with pytest.raises(EgressBlocked):
        client.get(url)
    assert inner.requests == []


def test_plain_http_is_refused_even_to_an_allowlisted_host() -> None:
    inner = RecordingTransport()
    client = httpx.Client(transport=AllowlistTransport(inner))
    with pytest.raises(EgressBlocked):
        client.get("http://gmail.googleapis.com/gmail/v1/users/me/profile")
    assert inner.requests == []


def test_the_async_transport_enforces_the_same_rule() -> None:
    import asyncio

    async def run() -> tuple[int, list[str]]:
        inner = RecordingAsyncTransport()
        async with httpx.AsyncClient(transport=AsyncAllowlistTransport(inner)) as client:
            response = await client.get("https://gmail.googleapis.com/gmail/v1/users/me/profile")
            with pytest.raises(EgressBlocked):
                await client.get("https://huggingface.co/x")
            return response.status_code, [str(r.url.host) for r in inner.requests]

    status, hosts = asyncio.run(run())
    assert status == 200
    assert hosts == ["gmail.googleapis.com"]


def test_the_default_client_factories_install_the_allowlist() -> None:
    """A client built any other way is a review finding; these are the supported constructors."""
    with build_client() as client:
        assert isinstance(client._transport, AllowlistTransport)
    async_client = build_async_client()
    assert isinstance(async_client._transport, AsyncAllowlistTransport)


def test_check_url_accepts_a_string_or_a_url_object() -> None:
    check_url("https://oauth2.googleapis.com/token")
    check_url(httpx.URL("https://gmail.googleapis.com/gmail/v1/users/me/messages"))
    with pytest.raises(EgressBlocked):
        check_url(httpx.URL("https://example.invalid/"))


# --- R-SEC-004: every rejection path is `EgressBlocked`, including the ones idna raises ---

#: Hosts whose punycode is syntactically an A-label but decodes to something IDNA refuses.
#: `httpx` decodes the host lazily, so the failure surfaces on attribute access inside
#: `check_url` rather than at URL construction.
MALFORMED_PUNYCODE = (
    "https://xn--gmailgoogleapis-3ye.com/",  # R-SEC-004's own reproduction: U+01E8
    "https://xn--a-ecp.ru/",  # U+2488, a digit-with-full-stop lookalike
    "https://xn--0.pt/",  # not a valid A-label at all
)


@pytest.mark.parametrize("url", MALFORMED_PUNYCODE)
def test_a_malformed_punycode_host_is_blocked_with_the_documented_error_type(url: str) -> None:
    """R-SEC-004: `idna.core.InvalidCodepoint` escaped `check_url` uncaught.

    The module's docstring promises `EgressBlocked` is the failure mode, so a caller that
    follows the contract and catches only `EgressBlocked` saw an unhandled third-party
    exception instead. Not a live bypass - the request never reached the transport - but
    an untyped error surface, and the assertion below is on the *type*, which is the whole
    of the finding.
    """
    with pytest.raises(EgressBlocked) as failure:
        check_url(url)
    assert "could not be parsed" in str(failure.value)


@pytest.mark.parametrize("url", MALFORMED_PUNYCODE)
def test_a_malformed_punycode_host_still_never_reaches_the_transport(url: str) -> None:
    """The safety half: failing closed was already true and must stay true.

    Note what this test does *not* claim. Through a client, `httpx` decodes the host while
    building the `Request` - before any transport is consulted - so the caller sees
    `idna`'s exception, not `EgressBlocked`, and MailWeave has no seam at which to convert
    it. The fix in `check_url` covers the direct-call path the finding named; the
    client-level residue is real and is documented in `egress.py` rather than papered
    over. What both paths share, and what this asserts, is that nothing is sent.
    """
    inner = RecordingTransport()
    client = httpx.Client(transport=AllowlistTransport(inner))
    with pytest.raises(Exception):  # noqa: B017 - the type is the point of the docstring
        client.get(url)
    assert inner.requests == []


@pytest.mark.parametrize("url", MALFORMED_PUNYCODE)
def test_the_client_level_residue_is_exactly_what_egress_documents(url: str) -> None:
    """The residue, pinned: if `httpx` ever starts raising `EgressBlocked`-compatible
    errors here, or MailWeave grows a seam that converts them, this test fails and the
    documentation is updated with it rather than drifting."""
    client = httpx.Client(transport=AllowlistTransport(RecordingTransport()))
    with pytest.raises(Exception) as failure:
        client.get(url)
    assert not isinstance(failure.value, EgressBlocked)
    assert type(failure.value).__module__.startswith("idna")


def test_the_unparseable_host_path_does_not_swallow_a_real_allowlist_decision() -> None:
    """The catch is narrow: a host that parses is still decided on the allowlist."""
    check_url("https://gmail.googleapis.com/gmail/v1/users/me/messages")
    with pytest.raises(EgressBlocked) as failure:
        check_url("https://evil.example/steal")
    assert "runtime egress allowlist" in str(failure.value)
