"""Model provisioning: declared intent, a reviewed lock, and the one path to the host."""

from __future__ import annotations

from mailweave.models.catalog import (
    DEFAULT_CATALOG_PATH,
    CatalogError,
    ModelCatalog,
    ModelEntry,
    load_catalog,
)
from mailweave.models.lock import (
    DEFAULT_LOCK_PATH,
    Lock,
    LockedFile,
    LockedModel,
    LockError,
    load_lock,
)
from mailweave.models.paths import DEFAULT_MODELS_DIR, model_dir
from mailweave.models.provision import (
    ProvisionError,
    assert_host_is_the_declared_one,
    install,
    installed_models,
    pin,
    write_lock,
)
from mailweave.models.verify import verify_locked

__all__ = [
    "DEFAULT_CATALOG_PATH",
    "DEFAULT_LOCK_PATH",
    "DEFAULT_MODELS_DIR",
    "CatalogError",
    "Lock",
    "LockError",
    "LockedFile",
    "LockedModel",
    "ModelCatalog",
    "ModelEntry",
    "ProvisionError",
    "assert_host_is_the_declared_one",
    "install",
    "installed_models",
    "load_catalog",
    "load_lock",
    "model_dir",
    "pin",
    "verify_locked",
    "write_lock",
]
