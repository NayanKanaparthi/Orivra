"""The semantic rung's machinery (AD D.5, D.7, D.8; SEM-02, SEM-03).

Importing this package registers nothing that touches the network. `local` registers a
factory; the factory only loads weights when a rung actually asks for a backend, and it
loads them offline from a checksum-pinned path or declines.
"""

from __future__ import annotations

from mailweave.semantic.interface import (
    REGISTRY,
    BackendContractError,
    BackendRegistry,
    BackendUnavailable,
    SemanticBackend,
    SemanticError,
    Vector,
    checked_embed,
    checked_rerank,
)
from mailweave.semantic.local import register_default
from mailweave.semantic.profile import (
    Basis,
    PoolTextMode,
    Provenance,
    SemanticProfile,
    unmeasured_profile,
)
from mailweave.semantic.records import PreflightRecord, load_records
from mailweave.semantic.resolve import resolve_profile

__all__ = [
    "REGISTRY",
    "BackendContractError",
    "BackendRegistry",
    "BackendUnavailable",
    "Basis",
    "PoolTextMode",
    "PreflightRecord",
    "Provenance",
    "SemanticBackend",
    "SemanticError",
    "SemanticProfile",
    "Vector",
    "checked_embed",
    "checked_rerank",
    "load_records",
    "register_default",
    "resolve_profile",
    "unmeasured_profile",
]

# Registering costs nothing: the factory runs only when a rung asks for a backend, and only
# then are weights verified and loaded. Importing this package touches no disk and no model.
register_default()
