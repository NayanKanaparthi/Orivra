"""What artifacts this project is willing to install, and from where (AD D.8, ADV-210).

The catalog is **declared intent**, reviewed by a human and committed. It names a host, a
repo, an expected licence, and one or more **artifact sets**. It deliberately pins nothing: a
revision and a per-file digest are facts about a download, and this file has never performed
one.

## Why a set rather than a file list

A repo ships the same weights in several formats. `BAAI/bge-reranker-base` carries
`model.safetensors`, `pytorch_model.bin` and `onnx/model.onnx`, which is about 3.36 GB of
download for roughly 1.1 GB of weights any one runtime loads. The first version of this
module enumerated the repo and took everything, which blew its own size bound and would have
cost the owner three downloads of the same thing.

So a set names the format its runtime loads. The Python arm and PF-4b's Node/ONNX arm are
separate sets, locked separately, and stay separately identifiable afterwards: a measurement
that cites "bge-reranker-base" without saying which artifacts it ran against is a
measurement whose difference from the other arm nobody recorded.

## Patterns, and why `required` is not `optional`

Patterns are `fnmatch` over the repo-relative path. A file is selected when it matches a
`required` or `optional` pattern and matches no `exclude` pattern.

**The include list is what does the work.** With the sets as shipped, no include pattern
matches `pytorch_model.bin` or `onnx/model.onnx` for the Python set, so the excludes never
fire - a replant that disabled the exclude check changed nothing and was recorded MISSED
until it was re-aimed at the includes. The excludes stay as a second line for the day
someone widens an `optional` pattern, and `__post_init__` refuses the one shape that would
make them incoherent: an exclude that contradicts a requirement.

**Every `required` pattern must match at least one file at pin time, or the pin fails.** A
pattern that silently matches nothing is how a tokenizer goes missing, and a missing
tokenizer does not present as a missing tokenizer: it presents as a loader failure weeks
later, and gets read as evidence about the model.

This module reads the declared `host` and **does not check it**. The check belongs where a
request is made, which is `provision.py`, and the `no-model-host-at-runtime` guard is why: a
module that can name the model host is a module that could reach it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Final

CATALOG_SCHEMA: Final[int] = 2
DEFAULT_CATALOG_PATH: Final[str] = "models-catalog.json"

#: The runtimes a set may declare. A closed vocabulary: an unknown runtime is a set nothing
#: knows how to load, and locking one would produce weights no arm can use.
KNOWN_RUNTIMES: Final[frozenset[str]] = frozenset({"sentence-transformers", "node-transformers-js"})


class CatalogError(ValueError):
    """The catalog is absent, malformed, or declares a set nothing can load."""


@dataclass(frozen=True, slots=True)
class ArtifactSet:
    """One runtime's view of a repo: what to take, what to leave, and how big it may get."""

    name: str
    runtime: str
    max_total_bytes: int
    required: tuple[str, ...]
    optional: tuple[str, ...]
    exclude: tuple[str, ...]
    why: str

    def __post_init__(self) -> None:
        if self.runtime not in KNOWN_RUNTIMES:
            raise CatalogError(f"{self.name}: unknown runtime {self.runtime!r}")
        if type(self.max_total_bytes) is not int or self.max_total_bytes <= 0:
            raise CatalogError(f"{self.name}: max_total_bytes must be a positive int")
        if not self.required:
            raise CatalogError(
                f"{self.name}: a set with no required pattern would accept an empty repo"
            )
        if not self.why:
            raise CatalogError(f"{self.name}: a set with no stated reason is one nobody chose")
        contradictory = sorted(set(self.required) & set(self.exclude))
        if contradictory:
            raise CatalogError(
                f"{self.name}: {contradictory} is both required and excluded. A set that "
                "asks for a file and refuses it selects nothing and says nothing"
            )

    def select(self, names: tuple[str, ...]) -> tuple[str, ...]:
        """The files this set takes, in a stable order, refusing an unmatched requirement."""
        kept = tuple(
            sorted(
                name
                for name in names
                if any(fnmatch(name, pattern) for pattern in self.required + self.optional)
                and not any(fnmatch(name, pattern) for pattern in self.exclude)
            )
        )
        unmatched = [
            pattern for pattern in self.required if not any(fnmatch(name, pattern) for name in kept)
        ]
        if unmatched:
            raise CatalogError(
                f"{self.name}: required pattern(s) {unmatched} matched nothing in this repo. "
                "A requirement that matches nothing is not satisfied by there being nothing "
                "to satisfy it: the set's runtime would fail to load and the failure would "
                "read as a model problem"
            )
        return kept


@dataclass(frozen=True, slots=True)
class ModelEntry:
    key: str
    role: str
    repo_id: str
    expected_license: str
    why: str
    artifact_sets: dict[str, ArtifactSet]

    def __post_init__(self) -> None:
        if self.role not in {"bi-encoder", "cross-encoder"}:
            raise CatalogError(f"{self.key}: unknown role {self.role!r}")
        if "/" not in self.repo_id or self.repo_id.startswith("/"):
            raise CatalogError(f"{self.key}: {self.repo_id!r} is not an org/name repo id")
        if not self.why:
            raise CatalogError(
                f"{self.key}: an entry with no stated reason is a dependency nobody chose"
            )
        if not self.artifact_sets:
            raise CatalogError(f"{self.key}: no artifact sets declared")

    def set_named(self, name: str) -> ArtifactSet:
        try:
            return self.artifact_sets[name]
        except KeyError as exc:
            raise CatalogError(
                f"{self.key}: no artifact set {name!r}; it has {sorted(self.artifact_sets)}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    host: str
    models: dict[str, ModelEntry]

    def entry(self, key: str) -> ModelEntry:
        try:
            return self.models[key]
        except KeyError as exc:
            raise CatalogError(f"no model named {key!r} in the catalog") from exc

    def targets(self) -> tuple[tuple[str, str], ...]:
        """Every `(model key, set name)` pair, which is what a lock is keyed by."""
        return tuple(
            (key, set_name)
            for key, entry in sorted(self.models.items())
            for set_name in sorted(entry.artifact_sets)
        )


def _require(payload: dict[str, Any], key: str, kind: type, where: str) -> Any:
    value = payload.get(key)
    if type(value) is not kind:
        raise CatalogError(f"{where}: {key} must be {kind.__name__}, got {type(value).__name__}")
    return value


def _patterns(payload: dict[str, Any], key: str, where: str) -> tuple[str, ...]:
    value = payload.get(key, [])
    if type(value) is not list or any(type(item) is not str for item in value):
        raise CatalogError(f"{where}: {key} must be a list of strings")
    return tuple(value)


def load_catalog(path: Path | str = DEFAULT_CATALOG_PATH) -> ModelCatalog:
    resolved = Path(path)
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogError(f"no catalog at {resolved}") from exc
    except ValueError as exc:
        raise CatalogError(f"{resolved} is not JSON") from exc
    if type(payload) is not dict:
        raise CatalogError(f"{resolved} is not a JSON object")
    if payload.get("schema") != CATALOG_SCHEMA:
        raise CatalogError(f"{resolved}: unknown catalog schema {payload.get('schema')!r}")
    host = _require(payload, "host", str, str(resolved))
    raw_models = _require(payload, "models", dict, str(resolved))
    models: dict[str, ModelEntry] = {}
    for key, entry in raw_models.items():
        if type(entry) is not dict:
            raise CatalogError(f"{resolved}: model {key!r} is not an object")
        raw_sets = _require(entry, "artifact_sets", dict, key)
        sets: dict[str, ArtifactSet] = {}
        for set_name, raw in raw_sets.items():
            if type(raw) is not dict:
                raise CatalogError(f"{key}: artifact set {set_name!r} is not an object")
            where = f"{key}.{set_name}"
            sets[set_name] = ArtifactSet(
                name=where,
                runtime=_require(raw, "runtime", str, where),
                max_total_bytes=_require(raw, "max_total_bytes", int, where),
                required=_patterns(raw, "required", where),
                optional=_patterns(raw, "optional", where),
                exclude=_patterns(raw, "exclude", where),
                why=_require(raw, "why", str, where),
            )
        models[key] = ModelEntry(
            key=key,
            role=_require(entry, "role", str, key),
            repo_id=_require(entry, "repo_id", str, key),
            expected_license=_require(entry, "expected_license", str, key),
            why=_require(entry, "why", str, key),
            artifact_sets=sets,
        )
    if not models:
        raise CatalogError(f"{resolved}: no models declared")
    return ModelCatalog(host=host, models=models)
