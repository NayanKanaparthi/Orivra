"""Digest verification, split from the provisioner so the server can use it.

`provision.py` can contact the model host; this cannot, and the server imports only this
one. The split is what lets `no-model-host-at-runtime` hold the import rule without the
loader losing the ability to check what it is about to load.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

from mailweave.models.lock import LockedModel
from mailweave.models.paths import DEFAULT_MODELS_DIR, model_dir

_CHUNK: Final[int] = 1 << 20


def digest_of(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def verify_locked(locked: LockedModel, *, root: Path | str = DEFAULT_MODELS_DIR) -> list[str]:
    """Problems with what is on disk, as sentences. Empty means installed and verified."""
    directory = model_dir(locked.key, locked.revision, root)
    problems: list[str] = []
    for entry in locked.files:
        path = directory / entry.name
        if not path.is_file():
            problems.append(f"missing: {entry.name}")
            continue
        sha256, size = digest_of(path)
        if sha256 != entry.sha256:
            problems.append(f"digest mismatch: {entry.name}")
        elif size != entry.bytes:
            problems.append(f"size mismatch: {entry.name}")
    return problems
