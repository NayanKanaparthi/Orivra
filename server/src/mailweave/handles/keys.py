"""The HMAC key a `map_id` is signed with, and where it lives (AD A.10, ADV-212).

**The key is in the token store, not in process memory** — a `0600` file inside a `0700`
directory, beside the refresh token and the profile salt, because those are the two
properties it needs: it is a secret, and it must outlive the process. A key held only in
memory makes every restart invalidate every outstanding handle, and the previous design's
`handle_expired`-on-a-fresh-handle is what that looks like from the caller's side: a
truthful-sounding error class attached to the wrong cause.

**A rotation is deliberate and it is announced.** `rotate` writes new key material and bumps
`StoredCredentials.key_epoch`, and a handle minted under an older epoch is refused as
`handle_key_rotated` — a distinct class from `handle_expired`, because the two have
different causes and different remedies and collapsing them would tell the operator that
time passed when what happened is that they rotated a key. Old key material is **not**
retained: a keyring that kept the previous epoch's key would make rotation a no-op for
exactly the handles rotation exists to invalidate.

**Nothing here renders the key.** `HandleKey.__repr__` is redacted for the reason
`StaticToken.__repr__` is: a credential in a traceback is a credential leaked, and the
default dataclass `__repr__` prints every field.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Final

from pydantic import SecretStr

from mailweave.auth.tokenstore import StoredCredentials, TokenStore
from mailweave.errors import TokenStoreError

#: Bytes of key material. 32 is HMAC-SHA256's block-optimal length: shorter buys nothing an
#: attacker cares about, longer is hashed down before use.
HANDLE_KEY_BYTES: Final[int] = 32


@dataclass(frozen=True)
class HandleKey:
    """One epoch of handle-signing key material.

    `epoch` travels **inside** the signed payload so a handle names the key it was signed
    with. That is what lets redemption say `handle_key_rotated` rather than
    `handle_invalid`: with the key gone the signature cannot verify either way, so the
    distinction has to be readable before the signature is checked, and it is read from a
    field that is then checked *against the key the reader holds* rather than trusted.
    """

    material: bytes
    epoch: int

    def __repr__(self) -> str:
        """Never render the key. Only its length and epoch, which are not secrets."""
        return f"HandleKey(material=<redacted:len={len(self.material)}>, epoch={self.epoch})"


def _material_of(hex_value: str) -> bytes:
    try:
        material = bytes.fromhex(hex_value)
    except ValueError as failure:
        raise TokenStoreError(
            "the handle-signing key in the credential store is not hexadecimal. The value "
            "is not reproduced here: it is a secret, and no part of one - not a fragment, "
            "not a truncation - appears in an error string (RR SEC-04)"
        ) from failure
    if len(material) != HANDLE_KEY_BYTES:
        raise TokenStoreError(
            f"the handle-signing key in the credential store is {len(material)} bytes; "
            f"{HANDLE_KEY_BYTES} are required. The value is not reproduced here (RR SEC-04)"
        )
    return material


def ensure_handle_key(store: TokenStore) -> HandleKey:
    """The key this server signs handles with, generated and persisted on first use.

    First run has no key: a store written before handles existed carries `map_key_hex: null`,
    which is the honest representation of "this server has never minted a handle". Generating
    one here rather than at `auth login` keeps the key's lifecycle with its use, and the
    generated key is written back through `TokenStore.save`, which is the one atomic
    `0600`-creating path.

    `key_epoch` is **not** bumped by a first generation. Bumping it would report a rotation
    to an operator who did not perform one, and there are no outstanding handles to
    invalidate on a store that has never held a key.
    """
    credentials = store.load()
    if credentials.map_key_hex is not None:
        return HandleKey(
            material=_material_of(credentials.map_key_hex.get_secret_value()),
            epoch=credentials.key_epoch,
        )
    material = secrets.token_bytes(HANDLE_KEY_BYTES)
    store.save(_with_key(credentials, material, credentials.key_epoch))
    return HandleKey(material=material, epoch=credentials.key_epoch)


def rotate_handle_key(store: TokenStore) -> HandleKey:
    """New key material under the next `key_epoch`. Every outstanding handle is invalidated.

    Invalidated *and named*: a handle carrying the previous epoch redeems as
    `handle_key_rotated`, which names the re-derivation call, rather than as
    `handle_invalid` (which would say the caller sent a bad handle) or `handle_expired`
    (which would say time passed). One cause, one class.
    """
    credentials = store.load()
    material = secrets.token_bytes(HANDLE_KEY_BYTES)
    epoch = credentials.key_epoch + 1
    store.save(_with_key(credentials, material, epoch))
    return HandleKey(material=material, epoch=epoch)


def _with_key(credentials: StoredCredentials, material: bytes, epoch: int) -> StoredCredentials:
    """The same credentials carrying new key material, **rebuilt rather than copied**.

    `model_copy(update=...)` would skip every validator on the way through, which on a
    secret-bearing document is the one place a shortcut is not worth taking: the shape checks
    that keep a refresh token out of a timestamp field are the same ones a copy would bypass.
    Constructing the model puts the whole document back through `SecretBearingModel.__init__`,
    which is the funnel every other write to this file uses.
    """
    return StoredCredentials(
        client_id=credentials.client_id,
        refresh_token=credentials.refresh_token,
        scopes=credentials.scopes,
        salt_hex=credentials.salt_hex,
        obtained_at=credentials.obtained_at,
        key_epoch=epoch,
        map_key_hex=SecretStr(material.hex()),
    )
