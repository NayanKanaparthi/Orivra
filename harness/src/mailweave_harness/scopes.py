"""Harness OAuth scopes and account pinning (AD B.9, RR SEC-03).

The destructive scope literal lives here and only here. A CI sweep fails the build if it
appears in `server/**`.
"""

from __future__ import annotations

from typing import Final

SEEDER_SCOPE: Final[str] = "https://mail.google.com/"
SEEDER_SCOPES: Final[tuple[str, ...]] = (SEEDER_SCOPE,)


class SeedAccountMismatch(RuntimeError):
    """The authenticated address is not the configured seed account. Abort, do not proceed."""


def assert_seed_account(*, authenticated_address: str, seed_address: str) -> None:
    """The harness aborts unless the authenticated address equals the seed account."""
    if authenticated_address.strip().lower() != seed_address.strip().lower():
        raise SeedAccountMismatch(
            "harness refuses to run: authenticated address does not match the configured "
            "seed account. Destructive capability may never reach another mailbox (SEC-03)."
        )
