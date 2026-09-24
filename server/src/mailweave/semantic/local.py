"""The local SEM-03 backend, forced offline and loaded from a verified path (AD D.8).

Setup-time provisioning is *necessary but not sufficient*, which is the whole of ADV-210.
The `sentence-transformers` / `transformers` / `huggingface_hub` default load path performs
a **hub revalidation request** for the model repo unless offline mode is forced, so a
process that had every weight on disk would still reach the network on load. The previous
draft of D.8 asserted the egress property as a consequence of provisioning and never stated
the enforcement that produces it. Both halves are here:

  * **offline is forced before the library is imported**, not before it is called.
    `HF_HUB_OFFLINE` is read at import time by `huggingface_hub`, so setting it afterwards
    is setting it too late - the module-level constant is already bound and the flag no
    longer has an effect. This is the mistake the environment variable invites;
  * **weights are loaded from a checksum-verified local directory, never a repo id.** A
    repo id is a lookup, and a lookup is a request. `_load_from` refuses anything that is
    not an existing directory, so "we pass a path" is a property of the call rather than a
    habit of its callers.

Everything that can go wrong here is `BackendUnavailable`, which is D.5's deterministic
fallback and not an error path: a machine with no weights and no ML runtime is a supported
configuration, and the rung says `not_tried` with a reason and the ladder continues.
SEM-02's guard makes a silent no-op a BLOCKER, which is why the reasons are specific.

## What this module refuses to do

It does not download. It does not name the model host - it could not, the
`no-model-host-at-runtime` guard would refuse the file. It does not import
`models/provision.py`, so "setup-models is never invoked from the server process" is a fact
about the import graph rather than about nobody calling a function.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from mailweave.models.lock import Lock, LockedModel
from mailweave.models.paths import DEFAULT_MODELS_DIR, model_dir
from mailweave.semantic.interface import (
    REGISTRY,
    BackendUnavailable,
    Vector,
)

#: Set before any hub-aware library is imported. `huggingface_hub` binds its offline flag at
#: import time, so this is deliberately module-level and deliberately above the imports that
#: would read it.
OFFLINE_ENVIRONMENT: Final[dict[str, str]] = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
}


def force_offline(environ: dict[str, str] | None = None) -> None:
    """Set the offline flags. Idempotent, and called before any model library is imported."""
    target = os.environ if environ is None else environ
    target.update(OFFLINE_ENVIRONMENT)


# **Called here, at import, and the comment above used to claim this without doing it.**
# `OFFLINE_ENVIRONMENT` was module-level and the *call* was not: three functions each invoked
# it immediately before their own import of a hub-aware library, which is correct at those
# three sites and is a property of the sites rather than of the process. Anything else that
# imported `huggingface_hub` first - the harness, a notebook, a library this one does not
# know about - would have bound the flag as unset, and `HF_HUB_OFFLINE` is read at import
# time. Importing `mailweave.semantic` is the first thing the server does with a model, so
# setting it here makes the guarantee process-wide instead of call-site-wide.
# `test_the_offline_flags_are_set_before_any_hub_aware_library_is_imported` found this by
# reading `os.environ` after importing the module and getting `None`.
force_offline()


#: The device the server loads on. AD F PF-4 registers its measurement as "on the actual dev
#: laptop, **CPU only**", and AD D.5's cost model is a CPU cost model. `SentenceTransformer`
#: with no `device` argument picks the best available accelerator, so on an M-series Mac the
#: server would silently run on MPS while every registered number described a CPU - and the
#: benchmark would have measured one thing while the plan claimed another.
#:
#: So the device is named here rather than defaulted by a library, and it travels into the
#: backend's identity so a latency record cannot fail to say which one it measured. Changing
#: it is a decision with a diff, not an environment difference between two machines.
DEFAULT_DEVICE: Final[str] = "cpu"


@dataclass(frozen=True, slots=True)
class LoadedPaths:
    """The two verified directories a backend loads from."""

    bi_encoder: Path
    cross_encoder: Path
    bi_encoder_id: str
    bi_encoder_revision: str
    cross_encoder_id: str
    cross_encoder_revision: str


def _verified_dir(
    locked: LockedModel,
    root: Path | str,
    verifier: Callable[[LockedModel], list[str]],
) -> Path:
    problems = verifier(locked)
    if problems:
        raise BackendUnavailable(
            f"{locked.repo_id}@{locked.revision[:12]} is not installed or does not match the "
            f"lock: {'; '.join(problems[:3])}"
        )
    directory = model_dir(locked.key, locked.revision, root)
    if not directory.is_dir():
        raise BackendUnavailable(f"{directory} is not a directory")
    return directory


def resolve_paths(
    lock: Lock,
    *,
    root: Path | str = DEFAULT_MODELS_DIR,
    bi_encoder_key: str = "stage_a_default.python-st",
    cross_encoder_key: str = "stage_b_default.python-st",
    verifier: Callable[[LockedModel], list[str]] | None = None,
) -> LoadedPaths:
    """The verified local directories for stage A and stage B, or `BackendUnavailable`.

    `verifier` is injected so the digest check is exercised in tests without a gigabyte of
    weights, and so this module never imports the provisioner. It defaults to the real
    digest walk.
    """
    if verifier is None:
        from mailweave.models.verify import verify_locked  # local import, no host names

        verifier = lambda locked: verify_locked(locked, root=root)  # noqa: E731
    try:
        bi = lock.entry(bi_encoder_key)
        cross = lock.entry(cross_encoder_key)
    except Exception as exc:  # LockError, and anything a malformed lock raises
        raise BackendUnavailable(str(exc)) from exc
    return LoadedPaths(
        bi_encoder=_verified_dir(bi, root, verifier),
        cross_encoder=_verified_dir(cross, root, verifier),
        bi_encoder_id=bi.repo_id,
        bi_encoder_revision=bi.revision,
        cross_encoder_id=cross.repo_id,
        cross_encoder_revision=cross.revision,
    )


def _load_from(path: Path, loader: Callable[[str], Any]) -> Any:
    """Load by path, and refuse anything that is not one.

    A repo id is a lookup and a lookup is a request. Checking here rather than trusting the
    caller is what makes "we never pass a repo id" a property of the call.
    """
    if not path.is_dir():
        raise BackendUnavailable(f"{path} is not a local model directory")
    if "/" in path.name and not path.exists():  # pragma: no cover - defensive
        raise BackendUnavailable("a repo id is not a path")
    return loader(str(path))


class LocalBackend:
    """SEM-03 over two locally-loaded models."""

    def __init__(
        self, paths: LoadedPaths, encoder: Any, reranker: Any, device: str = DEFAULT_DEVICE
    ) -> None:
        self._paths = paths
        self._encoder = encoder
        self._reranker = reranker
        self._device = device

    @property
    def device(self) -> str:
        """The device the weights were loaded onto, named rather than inferred."""
        return self._device

    @property
    def model_id(self) -> str:
        return f"{self._paths.bi_encoder_id}+{self._paths.cross_encoder_id}"

    @property
    def model_revision(self) -> str:
        return f"{self._paths.bi_encoder_revision[:12]}+{self._paths.cross_encoder_revision[:12]}"

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        raw = self._encoder.encode(list(texts))
        return [tuple(float(component) for component in row) for row in raw]

    def rerank(self, query: str, candidates: Sequence[str]) -> list[float]:
        pairs = [(query, candidate) for candidate in candidates]
        return [float(score) for score in self._reranker.predict(pairs)]


def available_accelerators() -> tuple[str, ...]:
    """Accelerators this machine offers but the server is not using, for the record.

    Recorded rather than used. A benchmark that says "CPU" while the library quietly chose
    MPS is not wrong by a little; it is measuring a different machine.
    """
    force_offline()
    try:
        import torch
    except ImportError:  # pragma: no cover - the extra is optional
        return ()
    found: list[str] = []
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        found.append("mps")
    if torch.cuda.is_available():
        found.append("cuda")
    return tuple(found)


def runtime_versions() -> dict[str, str]:
    """What actually loaded the weights, so a number can be attributed to a version.

    Three explicit imports rather than a loop over names. `__import__(name)` is a dynamic
    import with a computed argument, and both the forbidden-import and generative-client
    sweeps refuse it for the same reason: an import contract cannot be checked against a
    name no static pass can read. They caught this the first time it was written, which is
    the guard doing its job on convenience code.
    """
    force_offline()
    versions: dict[str, str] = {}
    try:
        import torch

        versions["torch"] = str(getattr(torch, "__version__", "unknown"))
    except ImportError:  # pragma: no cover - the extra is optional
        pass
    try:
        import sentence_transformers

        versions["sentence_transformers"] = str(
            getattr(sentence_transformers, "__version__", "unknown")
        )
    except ImportError:  # pragma: no cover - the extra is optional
        pass
    try:
        import transformers

        versions["transformers"] = str(getattr(transformers, "__version__", "unknown"))
    except ImportError:  # pragma: no cover - the extra is optional
        pass
    return versions


def _default_loaders(
    device: str = DEFAULT_DEVICE,
) -> tuple[Callable[[str], Any], Callable[[str], Any]]:
    """Import the model runtime, offline, and hand back the two constructors.

    The import is inside the function and after `force_offline`, because the flag is read at
    import time. Absence of the runtime is `BackendUnavailable`, not an error: a machine
    without the optional `semantic` extra installed is a supported configuration.

    `device` is passed explicitly. Letting the library choose is how a CPU-only plan ends up
    with MPS numbers and nobody notices, because nothing in the output says which it was.
    """
    force_offline()
    try:
        from sentence_transformers import CrossEncoder, SentenceTransformer
    except ImportError as exc:
        raise BackendUnavailable(
            "the local model runtime is not installed (install the `semantic` extra); "
            "the semantic rung declines and the ladder continues"
        ) from exc

    def encoder(path: str) -> Any:
        return SentenceTransformer(path, device=device, local_files_only=True)

    def reranker(path: str) -> Any:
        return CrossEncoder(path, device=device, local_files_only=True)

    return encoder, reranker


def build_local_backend(
    lock: Lock,
    *,
    root: Path | str = DEFAULT_MODELS_DIR,
    loaders: tuple[Callable[[str], Any], Callable[[str], Any]] | None = None,
    verifier: Callable[[LockedModel], list[str]] | None = None,
    device: str = DEFAULT_DEVICE,
) -> LocalBackend:
    """Verify, force offline, and load. Every failure is `BackendUnavailable`."""
    paths = resolve_paths(lock, root=root, verifier=verifier)
    encoder_loader, reranker_loader = loaders if loaders is not None else _default_loaders(device)
    try:
        encoder = _load_from(paths.bi_encoder, encoder_loader)
        reranker = _load_from(paths.cross_encoder, reranker_loader)
    except BackendUnavailable:
        raise
    except Exception as exc:
        # A load that would touch the network fails here rather than reaching out, because
        # the offline flags are already set. Whatever the library raises, the rung declines.
        raise BackendUnavailable(f"local model load failed: {type(exc).__name__}: {exc}") from exc
    return LocalBackend(paths, encoder, reranker, device)


def register_default(lock_path: Path | str = "models.lock") -> None:
    """Register the local backend as the default, without loading anything.

    Registration is a factory, so importing this module costs no weights and touches no
    disk. The factory runs only when a rung actually asks for a backend.
    """

    def factory() -> LocalBackend:
        from mailweave.models.lock import load_lock

        try:
            lock = load_lock(lock_path)
        except Exception as exc:
            raise BackendUnavailable(str(exc)) from exc
        return build_local_backend(lock)

    if "local" not in REGISTRY.names():
        REGISTRY.register("local", factory, default=True)
