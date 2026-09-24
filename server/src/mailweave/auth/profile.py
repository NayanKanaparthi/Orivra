"""Redaction-profile derivation (AD A.4, RR SEC-06).

Profile is `seed` only if **both** conditions hold:

  (i)  `SHA-256(salt || address)` equals the configured `seed_account_hash`; and
  (ii) the credential in use carries `client_id == seed_client_id`, i.e. the process is
       running on the harness OAuth client.

Editing `seed_account_hash` to the personal address's digest satisfies (i) and cannot
satisfy (ii), because the personal mailbox cannot hold a token for the harness client at
all - the control is Google-side. Either condition failing, or either being unset, yields
`personal`. A failure to observe the address at all is fatal: an underivable profile
cannot be made safe by defaulting.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum

from mailweave.errors import AuthProfileUnderivable


class Profile(StrEnum):
    PERSONAL = "personal"
    SEED = "seed"


def normalise_address(address: str) -> str:
    return address.strip().lower()


def account_digest(salt: bytes, address: str) -> str:
    """`SHA-256(salt || address)`, hex. Rotating or losing the salt fails closed to personal."""
    if not salt:
        raise ValueError("an empty salt would make every digest guessable")
    return hashlib.sha256(salt + normalise_address(address).encode("utf-8")).hexdigest()


def derive_profile(
    *,
    observed_address: str | None,
    salt: bytes,
    configured_seed_hash: str | None,
    credential_client_id: str | None,
    seed_client_id: str | None,
) -> Profile:
    """Return the redaction profile, or refuse to start.

    `observed_address is None` models a failed startup `users.getProfile` call: D.11 makes
    that a startup failure, not a defaulted profile.
    """
    if observed_address is None:
        raise AuthProfileUnderivable(
            "users.getProfile failed at startup, so the redaction profile cannot be "
            "derived; the server refuses to start rather than guess a profile "
            "(auth_profile_underivable). Check network and credentials."
        )
    if not configured_seed_hash or not seed_client_id or not credential_client_id:
        return Profile.PERSONAL
    digest_matches = account_digest(salt, observed_address) == configured_seed_hash
    client_matches = credential_client_id == seed_client_id
    return Profile.SEED if (digest_matches and client_matches) else Profile.PERSONAL
