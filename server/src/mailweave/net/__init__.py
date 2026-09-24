"""Network posture: the two-host runtime egress allowlist."""

from mailweave.net.egress import (
    AllowlistTransport,
    AsyncAllowlistTransport,
    build_async_client,
    build_client,
    check_url,
)

__all__ = [
    "AllowlistTransport",
    "AsyncAllowlistTransport",
    "build_async_client",
    "build_client",
    "check_url",
]
