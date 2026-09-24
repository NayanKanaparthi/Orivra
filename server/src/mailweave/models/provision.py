"""The one code path permitted to contact the model host (AD D.8, ADV-210, PF-5).

Never imported by the server process and never reachable from a query path. The
`no-model-host-at-runtime` guard enforces that rather than asking for it, and PF-5 verifies
the property the only way that counts: a cold start with the model host blocked, running the
whole suite.

## Two commands, and why they are two

**`--pin`** performs a real download. It resolves the repo's current commit, enumerates its
files, streams each one while computing SHA-256, refuses anything that would exceed the
catalog's `max_total_bytes`, and writes `models.lock`. The lock is then committed and
reviewed: a digest is a fact about an artifact, and the diff is where a human sees it.

**Install** (the default) reads that reviewed lock, and verifies every byte it writes
against it. A file already on disk whose digest matches is left alone; one whose digest
differs is refused, not overwritten, because a weights file that changed underneath a pinned
lock is a question and not a cache miss.

Separating them is what makes the install path verifiable. A single command that downloaded
and recorded in one step would compute a digest from whatever arrived and then "verify"
against it, which is the shape of a test that asserts the code's own output.

## Why not `huggingface_hub`

The property under test is which host is contacted, by what, and when. A library that
resolves repos, caches, and revalidates has its own opinions about all three, and D.8's
runtime rule exists precisely because that library's default load path performs a hub
revalidation request. Downloading with the project's own allowlisted transport means the set
of reachable hosts is `SETUP_EGRESS_ALLOWLIST` and nothing else, checked by the same
transport the Gmail client uses.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from mailweave.constants import MODEL_CDN_SUFFIXES, MODEL_HOST, SETUP_EGRESS_ALLOWLIST
from mailweave.models.catalog import ModelCatalog, ModelEntry
from mailweave.models.lock import (
    DEFAULT_LOCK_PATH,
    Lock,
    LockedFile,
    LockedModel,
    LockError,
)
from mailweave.models.paths import DEFAULT_MODELS_DIR, model_dir
from mailweave.models.verify import digest_of, verify_locked
from mailweave.net.egress import build_client

_CHUNK = 1 << 20
_TIMEOUT = httpx.Timeout(30.0, read=300.0)

#: `(file name, bytes received so far, the file's expected size)` - called as bytes arrive, so
#: a caller can show a download moving rather than only that a file finished (2026-09-23, the
#: desktop beta's progress). Receives no path, no URL and no content: a name the lock already
#: states and two counts.
Progress = Callable[[str, int, int], None]


class ProvisionError(RuntimeError):
    """A download refused, a digest mismatch, or a bound exceeded."""


def _client(inner: httpx.BaseTransport | None = None) -> httpx.Client:
    """The one widening of the allowlist in the codebase, named at the call site.

    `MODEL_CDN_SUFFIXES` is passed because large files are served by **redirect** to a
    regional content host: the owner's first pin attempt was refused at
    `us.aws.cdn.hf.co`, which no enumerated list contained. Enumerating that one host would
    have moved the failure to the next person in another region, so the suffix is allowed
    here and nowhere else. The runtime allowlist passes no suffixes at all and is unchanged.
    """
    return build_client(
        inner=inner,
        allowlist=SETUP_EGRESS_ALLOWLIST,
        suffixes=MODEL_CDN_SUFFIXES,
        timeout=_TIMEOUT,
    )


def _stream_to(
    client: httpx.Client,
    url: str,
    destination: Path,
    *,
    budget: int,
    progress: Progress | None = None,
) -> tuple[str, int]:
    """Download to a temp file beside the destination, aborting the moment `budget` is spent.

    The bound is checked **inside the chunk loop**. Checking after each complete file meant a
    single 2 GB file blew a 1.5 GB bound only once all 2 GB were on disk, which is a report
    rather than a limit. `progress`, when given, hears each chunk's running total against
    `budget` after the bound has accepted it.
    """
    if budget <= 0:
        raise ProvisionError(
            f"{url}: the set's max_total_bytes is already spent before this file starts"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.part")
    digest = hashlib.sha256()
    size = 0
    try:
        with client.stream("GET", url, follow_redirects=True) as response:
            if response.status_code != 200:
                raise ProvisionError(f"{url} returned HTTP {response.status_code}")
            with temporary.open("wb") as handle:
                for chunk in response.iter_bytes(_CHUNK):
                    size += len(chunk)
                    if size > budget:
                        raise ProvisionError(
                            f"{url}: this artifact set's max_total_bytes would be exceeded "
                            f"(remaining budget {budget} bytes). Stopped mid-transfer rather "
                            "than after the bytes landed"
                        )
                    handle.write(chunk)
                    digest.update(chunk)
                    if progress is not None:
                        progress(destination.name, size, budget)
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return digest.hexdigest(), size


def _repo_metadata(client: httpx.Client, repo_id: str) -> dict[str, Any]:
    response = client.get(f"https://{MODEL_HOST}/api/models/{repo_id}", follow_redirects=True)
    if response.status_code != 200:
        raise ProvisionError(f"{repo_id}: metadata returned HTTP {response.status_code}")
    payload = response.json()
    if type(payload) is not dict:
        raise ProvisionError(f"{repo_id}: metadata is not an object")
    return payload


def _file_names(metadata: dict[str, Any]) -> tuple[str, ...]:
    siblings = metadata.get("siblings")
    if type(siblings) is not list:
        raise ProvisionError("repo metadata carries no file list")
    names = tuple(
        sorted(
            str(item["rfilename"])
            for item in siblings
            if type(item) is dict and type(item.get("rfilename")) is str
        )
    )
    if not names:
        raise ProvisionError("repo metadata lists no files")
    return names


def assert_host_is_the_declared_one(catalog: ModelCatalog) -> None:
    """The catalog's host must be the one `constants.py` names, checked here.

    Here rather than in `catalog.py` because this is where a request is made: a module that
    can name the model host is a module that could reach it, and the reachability guard
    holds the catalog reader to that.
    """
    if catalog.host != MODEL_HOST:
        raise ProvisionError(
            f"the catalog declares host {catalog.host!r}, which is not the model host this "
            "project provisions from. Nothing is downloaded"
        )


def write_lock(lock: Lock, path: Path | str = DEFAULT_LOCK_PATH) -> Path:
    """Write the reviewed artifact. The one place a lock is serialised."""
    resolved = Path(path)
    resolved.write_text(
        json.dumps(lock.as_payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return resolved


def pin(
    entry: ModelEntry,
    set_name: str,
    *,
    root: Path | str = DEFAULT_MODELS_DIR,
    inner: httpx.BaseTransport | None = None,
) -> LockedModel:
    """Download one artifact set at the repo's current commit and record what arrived.

    Only the set's files are fetched. The first version enumerated the repo and took
    everything, which meant `bge-reranker-base` pulled safetensors, a pytorch .bin and an
    ONNX graph - about 3.36 GB for roughly 1.1 GB any runtime loads - and then failed its own
    size bound after the bytes had already landed.
    """
    artifacts = entry.set_named(set_name)
    key = f"{entry.key}.{set_name}"
    with _client(inner) as client:
        metadata = _repo_metadata(client, entry.repo_id)
        revision = metadata.get("sha")
        if type(revision) is not str:
            raise ProvisionError(f"{entry.repo_id}: metadata carries no commit sha")
        card = metadata.get("cardData")
        license_name = card.get("license") if type(card) is dict else None
        if type(license_name) is str and license_name.lower() != entry.expected_license.lower():
            raise ProvisionError(
                f"{entry.repo_id}: licence is {license_name!r}, the catalog expects "
                f"{entry.expected_license!r}. A licence change is a decision, not a download"
            )
        selected = artifacts.select(_file_names(metadata))
        destination = model_dir(key, revision, root)
        files: list[LockedFile] = []
        total = 0
        for name in selected:
            url = f"https://{MODEL_HOST}/{entry.repo_id}/resolve/{revision}/{name}"
            target = destination / name
            sha256, size = _stream_to(client, url, target, budget=artifacts.max_total_bytes - total)
            total += size
            files.append(LockedFile(name=name, sha256=sha256, bytes=size))
    return LockedModel(
        key=key,
        repo_id=entry.repo_id,
        revision=revision,
        license=entry.expected_license,
        pinned_at=datetime.now(UTC).isoformat(timespec="seconds"),
        files=tuple(files),
        artifact_set=set_name,
        runtime=artifacts.runtime,
    )


def install(
    locked: LockedModel,
    *,
    root: Path | str = DEFAULT_MODELS_DIR,
    inner: httpx.BaseTransport | None = None,
    progress: Progress | None = None,
) -> Iterator[str]:
    """Fetch anything missing and verify everything against the lock, yielding progress.

    A file whose digest differs from the lock is **refused, not overwritten**: weights that
    changed underneath a pinned lock are a question, and answering it by re-downloading
    would make the lock decorative. `progress` is `_stream_to`'s, passed through; the lines
    this yields are unchanged by it.
    """
    directory = model_dir(locked.key, locked.revision, root)
    for entry in locked.files:
        target = directory / entry.name
        if target.is_file():
            sha256, _ = digest_of(target)
            if sha256 == entry.sha256:
                yield f"ok {entry.name}"
                continue
            raise ProvisionError(
                f"{target} does not match the lock. Refusing to overwrite it: a weights "
                "file that changed underneath a pinned lock is a question, not a cache miss"
            )
        with _client(inner) as client:
            url = f"https://{MODEL_HOST}/{locked.repo_id}/resolve/{locked.revision}/{entry.name}"
            sha256, size = _stream_to(client, url, target, budget=entry.bytes, progress=progress)
        if sha256 != entry.sha256 or size != entry.bytes:
            target.unlink(missing_ok=True)
            raise ProvisionError(f"{entry.name}: downloaded bytes do not match the lock")
        yield f"fetched {entry.name} ({size} bytes)"


def installed_models(lock: Lock, *, root: Path | str = DEFAULT_MODELS_DIR) -> dict[str, bool]:
    """Which locked models are present and verified on this machine."""
    state: dict[str, bool] = {}
    for key, locked in lock.models.items():
        try:
            state[key] = not verify_locked(locked, root=root)
        except LockError:  # pragma: no cover - a lock that loaded cannot fail here
            state[key] = False
    return state
