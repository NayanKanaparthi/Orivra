"""`models.lock`: what a real download actually contained (AD D.8).

The catalog says which repo. The lock says which **commit**, which files, and what each
file's SHA-256 is, recorded by the code that downloaded it. Installing verifies against the
lock and refuses a mismatch; nothing installs from the catalog alone.

This module **reads**. `write_lock` lives in `provision.py` because pinning is the only
thing that writes a lock, and the disk-write allowlist should hold the smallest set of files
it can rather than one per module that happens to serialise something.

Two properties the shape enforces rather than requests:

  * **A locked model names a commit, never a branch.** `main` moves, so a lock pinned to it
    would verify a different artifact tomorrow and report success both times. A revision
    that is not a 40-character hex commit is refused at load.
  * **A file entry carries a digest or it is not an entry.** An optional digest would make
    "verified" mean "verified where someone remembered to record one", which is the shape
    of every guard in this project that stopped covering what it named.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

LOCK_SCHEMA: Final[int] = 1
DEFAULT_LOCK_PATH: Final[str] = "models.lock"

_COMMIT = re.compile(r"\A[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z")
#: A repo-relative path. No absolute paths and no traversal: a lock is read from the repo
#: and drives writes onto the owner's disk, so a `../` in a filename is an arbitrary write.
_SAFE_NAME = re.compile(r"\A(?!\.)[A-Za-z0-9._/-]{1,255}\Z")


class LockError(ValueError):
    """The lock is absent, malformed, or names something that cannot be verified."""


@dataclass(frozen=True, slots=True)
class LockedFile:
    name: str
    sha256: str
    bytes: int

    def __post_init__(self) -> None:
        if not _SAFE_NAME.fullmatch(self.name) or ".." in self.name.split("/"):
            raise LockError(f"{self.name!r} is not a safe repo-relative file name")
        if not _SHA256.fullmatch(self.sha256):
            raise LockError(f"{self.name}: sha256 is not a hex digest")
        if type(self.bytes) is not int or self.bytes < 0:
            raise LockError(f"{self.name}: bytes must be a non-negative int")


@dataclass(frozen=True, slots=True)
class LockedModel:
    #: `<model key>.<artifact set>`, e.g. `stage_b_default.node-onnx`. Keyed by the pair
    #: because one repo yields more than one set and PF-4b's arm must stay separately
    #: identifiable from the Python arm's.
    key: str
    repo_id: str
    revision: str
    license: str
    pinned_at: str
    files: tuple[LockedFile, ...]
    artifact_set: str = ""
    runtime: str = ""

    def __post_init__(self) -> None:
        if not _COMMIT.fullmatch(self.revision):
            raise LockError(
                f"{self.key}: revision {self.revision!r} is not a 40-hex commit. A branch "
                "moves, so a lock pinned to one verifies a different artifact tomorrow and "
                "reports success both times"
            )
        if not self.files:
            raise LockError(f"{self.key}: a locked model with no files verifies nothing")

    @property
    def total_bytes(self) -> int:
        return sum(entry.bytes for entry in self.files)


@dataclass(frozen=True, slots=True)
class Lock:
    models: dict[str, LockedModel]

    def entry(self, key: str) -> LockedModel:
        try:
            return self.models[key]
        except KeyError as exc:
            raise LockError(
                f"{key!r} is not in the lock. Run `mailweave setup-models --pin {key}` and "
                "commit the resulting models.lock for review"
            ) from exc

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema": LOCK_SCHEMA,
            "models": {
                key: {
                    "repo_id": model.repo_id,
                    "revision": model.revision,
                    "license": model.license,
                    "artifact_set": model.artifact_set,
                    "runtime": model.runtime,
                    "pinned_at": model.pinned_at,
                    "total_bytes": model.total_bytes,
                    "files": [
                        {"name": f.name, "sha256": f.sha256, "bytes": f.bytes} for f in model.files
                    ],
                }
                for key, model in sorted(self.models.items())
            },
        }


def load_lock(path: Path | str = DEFAULT_LOCK_PATH) -> Lock:
    resolved = Path(path)
    if not resolved.exists():
        raise LockError(
            f"no lock at {resolved}. Nothing installs from the catalog alone: run "
            "`mailweave setup-models --pin` on a machine that may reach the model host, "
            "then commit models.lock so a reviewer sees the digests"
        )
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LockError(f"{resolved} is not readable JSON") from exc
    if type(payload) is not dict or payload.get("schema") != LOCK_SCHEMA:
        raise LockError(f"{resolved}: unknown lock schema {payload.get('schema')!r}")
    raw = payload.get("models")
    if type(raw) is not dict or not raw:
        raise LockError(f"{resolved}: no models locked")
    models: dict[str, LockedModel] = {}
    for key, entry in raw.items():
        if type(entry) is not dict:
            raise LockError(f"{resolved}: {key!r} is not an object")
        raw_files = entry.get("files")
        if type(raw_files) is not list:
            raise LockError(f"{key}: files must be a list")
        files = tuple(
            LockedFile(name=str(item["name"]), sha256=str(item["sha256"]), bytes=int(item["bytes"]))
            for item in raw_files
            if type(item) is dict
        )
        models[key] = LockedModel(
            key=key,
            repo_id=str(entry.get("repo_id", "")),
            revision=str(entry.get("revision", "")),
            license=str(entry.get("license", "")),
            pinned_at=str(entry.get("pinned_at", "")),
            files=files,
            artifact_set=str(entry.get("artifact_set", "")),
            runtime=str(entry.get("runtime", "")),
        )
    return Lock(models=models)
