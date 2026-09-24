"""WS-06: `map_id` handles and staleness (AD A.10, contract MCP-02/MCP-06, NFR-03).

Four modules, and the split is the design rather than tidiness:

  * `keys` - the HMAC key, in the `0600` token store so a restart does not invalidate
    outstanding handles, with a `key_epoch` a deliberate rotation bumps;
  * `mint` - the payload, the signature, and step 1 of redemption (`verify`), which touches
    no network and therefore establishes nothing about the mailbox;
  * `cache` - the LRU A.10 specifies: key `(thread_id, history_id_at_fetch)`, 60 s TTL, 64
    entries, evicted on any staleness. Never consulted by the liveness probe;
  * `redeem` - the order: verify -> independent liveness probe -> fetch -> digest recompute.

`digest` sits beside them and carries the one design decision a reviewer should look at
first: what `mapping_digest` covers, and why `Source.participants` is not in it.
"""

from mailweave.handles.cache import (
    CACHE_TTL_SECONDS,
    MAX_CACHED_THREAD_MAPS,
    CachedThreadMap,
    ThreadMapCache,
)
from mailweave.handles.digest import DIGEST_SCHEMA, mapping_digest
from mailweave.handles.keys import HandleKey, ensure_handle_key, rotate_handle_key
from mailweave.handles.mint import (
    HANDLE_TTL_SECONDS,
    HANDLE_VERSION,
    MIN_HANDLE_TTL_SECONDS,
    HandleMinter,
    HandlePayload,
    mint,
    verify,
)
from mailweave.handles.redeem import (
    DigestCheck,
    Liveness,
    Redemption,
    RedemptionTrace,
    ServedThread,
    Step,
    redeem,
    redeem_or_raise,
)

__all__ = [
    "CACHE_TTL_SECONDS",
    "DIGEST_SCHEMA",
    "HANDLE_TTL_SECONDS",
    "HANDLE_VERSION",
    "MAX_CACHED_THREAD_MAPS",
    "MIN_HANDLE_TTL_SECONDS",
    "CachedThreadMap",
    "DigestCheck",
    "HandleKey",
    "HandleMinter",
    "HandlePayload",
    "Liveness",
    "Redemption",
    "RedemptionTrace",
    "ServedThread",
    "Step",
    "ThreadMapCache",
    "ensure_handle_key",
    "mapping_digest",
    "mint",
    "redeem",
    "redeem_or_raise",
    "rotate_handle_key",
    "verify",
]
