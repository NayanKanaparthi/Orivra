"""Model provisioning: a reviewed lock, one host, and a loader that cannot reach it.

Three properties, and each is the kind that is usually asserted in prose:

  * nothing installs from the catalog alone, and a digest is never invented;
  * the model host is reachable from exactly one module, and the runtime allowlist does not
    hold it, so a cold start with that host blocked cannot secretly succeed by reaching it;
  * the loader declines rather than downloading, and a weights file that changed underneath
    a pinned lock is refused rather than re-fetched.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from mailweave.cli import main
from mailweave.constants import (
    MODEL_CDN_SUFFIXES,
    MODEL_HOST,
    RUNTIME_EGRESS_ALLOWLIST,
    SETUP_EGRESS_ALLOWLIST,
)
from mailweave.models import (
    CatalogError,
    Lock,
    LockedFile,
    LockedModel,
    LockError,
    ProvisionError,
    assert_host_is_the_declared_one,
    install,
    load_catalog,
    model_dir,
    pin,
    verify_locked,
    write_lock,
)
from mailweave.net.egress import EgressBlocked, build_client
from mailweave.semantic import BackendUnavailable
from mailweave.semantic.local import (
    OFFLINE_ENVIRONMENT,
    build_local_backend,
    force_offline,
    resolve_paths,
)

COMMIT = "a" * 40
BODY = b"weights-bytes"
DIGEST = hashlib.sha256(BODY).hexdigest()


def _repo_transport(files: dict[str, bytes], *, sha: str = COMMIT) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/models/"):
            return httpx.Response(
                200,
                json={
                    "sha": sha,
                    "cardData": {"license": "mit"},
                    "siblings": [{"rfilename": name} for name in sorted(files)],
                },
            )
        name = request.url.path.split(f"/resolve/{sha}/", 1)[-1]
        if name in files:
            return httpx.Response(200, content=files[name])
        return httpx.Response(404)

    return httpx.MockTransport(handler)


#: A repo shaped like BAAI/bge-reranker-base: the same weights in three formats.
THREE_FORMATS: dict[str, bytes] = {
    "config.json": b"{}",
    "tokenizer.json": b"{}",
    "sentencepiece.bpe.model": b"spm",
    "model.safetensors": b"safetensors-weights",
    "pytorch_model.bin": b"the-same-weights-again",
    "onnx/model.onnx": b"and-again-as-a-graph",
}


def _locked(
    files: dict[str, bytes] | None = None, key: str = "stage_a_default.python-st"
) -> LockedModel:
    payload = files if files is not None else {"model.safetensors": BODY}
    return LockedModel(
        key=key,
        repo_id="minishlab/potion-retrieval-32M",
        revision=COMMIT,
        license="MIT",
        pinned_at="2026-09-11T00:00:00+00:00",
        files=tuple(
            LockedFile(name=name, sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
            for name, body in sorted(payload.items())
        ),
        artifact_set="python-st",
        runtime="sentence-transformers",
    )


# --- the catalog declares, the lock proves ----------------------------------------------


def test_the_shipped_catalog_loads_and_states_a_reason_for_every_entry_and_set() -> None:
    catalog = load_catalog("models-catalog.json")
    assert_host_is_the_declared_one(catalog)
    assert set(catalog.models) >= {"stage_a_default", "stage_b_default"}
    for entry in catalog.models.values():
        assert entry.why, entry.key
        for artifacts in entry.artifact_sets.values():
            assert artifacts.why, artifacts.name


def test_pf4b_alternative_artifacts_stay_separately_identifiable() -> None:
    # Two arms measuring "bge-reranker-base" without saying which artifacts they ran
    # against is two numbers whose difference nobody recorded.
    catalog = load_catalog("models-catalog.json")
    sets = catalog.entry("stage_b_default").artifact_sets
    assert set(sets) == {"python-st", "node-onnx"}
    assert sets["python-st"].runtime == "sentence-transformers"
    assert sets["node-onnx"].runtime == "node-transformers-js"
    assert ("stage_b_default", "node-onnx") in catalog.targets()


def test_a_set_takes_one_weight_format_and_leaves_the_duplicates() -> None:
    catalog = load_catalog("models-catalog.json")
    entry = catalog.entry("stage_b_default")
    names = tuple(sorted(THREE_FORMATS))

    python = entry.set_named("python-st").select(names)
    onnx = entry.set_named("node-onnx").select(names)

    assert "model.safetensors" in python
    assert "pytorch_model.bin" not in python and "onnx/model.onnx" not in python
    assert "onnx/model.onnx" in onnx
    assert "model.safetensors" not in onnx and "pytorch_model.bin" not in onnx
    # The tokenizer travels with both, because a runtime that cannot tokenise cannot run.
    assert "tokenizer.json" in python and "tokenizer.json" in onnx


def test_a_required_pattern_that_matches_nothing_fails_the_pin() -> None:
    # A missing tokenizer does not present as a missing tokenizer. It presents as a loader
    # failure weeks later and gets read as evidence about the model.
    catalog = load_catalog("models-catalog.json")
    artifacts = catalog.entry("stage_a_default").set_named("python-st")
    with pytest.raises(CatalogError, match="matched nothing"):
        artifacts.select(("config.json", "model.safetensors"))  # no modules.json


def test_potions_module_config_is_required_not_optional() -> None:
    # Revision 6fc8051 declares StaticEmbedding and Normalize in modules.json; without it
    # SentenceTransformer takes a transformer-style path this repo cannot satisfy.
    catalog = load_catalog("models-catalog.json")
    artifacts = catalog.entry("stage_a_default").set_named("python-st")
    assert "modules.json" in artifacts.required


def test_an_entry_with_no_stated_reason_is_refused(tmp_path: Path) -> None:
    # A dependency nobody wrote a reason for is a dependency nobody chose.
    path = tmp_path / "c.json"
    path.write_text(
        json.dumps(
            {
                "schema": 2,
                "host": MODEL_HOST,
                "models": {
                    "x": {
                        "role": "bi-encoder",
                        "repo_id": "a/b",
                        "expected_license": "MIT",
                        "why": "",
                        "artifact_sets": {
                            "python-st": {
                                "runtime": "sentence-transformers",
                                "max_total_bytes": 10,
                                "required": ["config.json"],
                                "why": "a reason",
                            }
                        },
                    }
                },
            }
        )
    )
    with pytest.raises(CatalogError, match="no stated reason"):
        load_catalog(path)


def test_a_lock_pinned_to_a_branch_is_refused() -> None:
    # `main` moves, so a lock pinned to it verifies a different artifact tomorrow and
    # reports success both times.
    with pytest.raises(LockError, match="not a 40-hex commit"):
        LockedModel(
            key="k",
            repo_id="a/b",
            revision="main",
            license="MIT",
            pinned_at="2026-09-11T00:00:00+00:00",
            files=(LockedFile(name="f", sha256="0" * 64, bytes=1),),
        )


def test_a_lock_entry_without_a_digest_is_not_an_entry() -> None:
    with pytest.raises(LockError, match="sha256"):
        LockedFile(name="f", sha256="", bytes=1)


def test_a_traversing_file_name_is_refused() -> None:
    # A lock drives writes onto the owner's disk, so `../` in a name is an arbitrary write.
    with pytest.raises(LockError, match="safe repo-relative"):
        LockedFile(name="../../etc/passwd", sha256="0" * 64, bytes=1)


def test_nothing_installs_from_the_catalog_alone(tmp_path: Path, capsys) -> None:
    assert main(["setup-models", "--lock", str(tmp_path / "absent.lock")]) == 1
    assert "Nothing installs from the catalog alone" in capsys.readouterr().out


# --- the host is reachable from one place, and not at runtime ---------------------------


def test_the_runtime_allowlist_does_not_hold_the_model_host() -> None:
    # The property PF-5 verifies by running the suite cold with that host blocked. If it
    # were on the runtime allowlist, that test could not fail even with a hidden
    # revalidation call in the load path.
    assert MODEL_HOST not in RUNTIME_EGRESS_ALLOWLIST
    assert MODEL_HOST in SETUP_EGRESS_ALLOWLIST
    assert not (RUNTIME_EGRESS_ALLOWLIST & SETUP_EGRESS_ALLOWLIST)


def test_a_runtime_client_refuses_the_model_host() -> None:
    with build_client() as client, pytest.raises(EgressBlocked):
        client.get(f"https://{MODEL_HOST}/api/models/x")


def test_the_loader_declines_instead_of_reaching_out(tmp_path: Path) -> None:
    # The egress-blocked condition, in software: every socket refused. A loader that
    # declines here is one that cannot be the source of a hidden revalidation call.
    lock = Lock(
        models={"stage_a_default.python-st": _locked(), "stage_b_default.python-st": _locked()}
    )

    def exploding(_path: str) -> object:
        raise AssertionError("the loader must not be reached when nothing is installed")

    with pytest.raises(BackendUnavailable, match="not installed or does not match"):
        build_local_backend(lock, root=tmp_path, loaders=(exploding, exploding))


def test_offline_is_forced_and_names_the_flags_a_hub_library_reads() -> None:
    environ: dict[str, str] = {}
    force_offline(environ)
    assert environ["HF_HUB_OFFLINE"] == "1"
    assert set(OFFLINE_ENVIRONMENT) >= {"HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"}


# --- pinning and installing --------------------------------------------------------------


def test_pin_records_what_actually_arrived(tmp_path: Path) -> None:
    catalog = load_catalog("models-catalog.json")
    entry = catalog.entry("stage_a_default")
    repo = {"config.json": b"{}", "modules.json": b"[]", "model.safetensors": BODY}
    locked = pin(entry, "python-st", root=tmp_path, inner=_repo_transport(repo))
    assert locked.revision == COMMIT
    assert locked.key == "stage_a_default.python-st"
    assert locked.artifact_set == "python-st"
    assert DIGEST in {f.sha256 for f in locked.files}
    assert not verify_locked(locked, root=tmp_path)


def test_pin_downloads_only_the_sets_files(tmp_path: Path) -> None:
    catalog = load_catalog("models-catalog.json")
    entry = catalog.entry("stage_b_default")
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/models/"):
            return httpx.Response(
                200,
                json={
                    "sha": COMMIT,
                    "cardData": {"license": "mit"},
                    "siblings": [{"rfilename": n} for n in sorted(THREE_FORMATS)],
                },
            )
        name = request.url.path.split(f"/resolve/{COMMIT}/", 1)[-1]
        fetched.append(name)
        return httpx.Response(200, content=THREE_FORMATS[name])

    pin(entry, "python-st", root=tmp_path, inner=httpx.MockTransport(handler))

    assert "pytorch_model.bin" not in fetched
    assert "onnx/model.onnx" not in fetched
    assert "model.safetensors" in fetched


def test_the_two_sets_of_one_repo_do_not_share_a_directory(tmp_path: Path) -> None:
    catalog = load_catalog("models-catalog.json")
    entry = catalog.entry("stage_b_default")
    transport = _repo_transport(THREE_FORMATS)
    python = pin(entry, "python-st", root=tmp_path, inner=transport)
    onnx = pin(entry, "node-onnx", root=tmp_path, inner=transport)
    assert model_dir(python.key, python.revision, tmp_path) != model_dir(
        onnx.key, onnx.revision, tmp_path
    )
    assert not verify_locked(python, root=tmp_path)
    assert not verify_locked(onnx, root=tmp_path)


def test_the_bound_stops_a_transfer_mid_file(tmp_path: Path) -> None:
    # Checking after each complete file meant a 2 GB file blew a 1.5 GB bound only once all
    # 2 GB were on disk, which is a report rather than a limit.
    catalog = load_catalog("models-catalog.json")
    entry = catalog.entry("stage_a_default")
    artifacts = entry.set_named("python-st")
    oversize = b"x" * (artifacts.max_total_bytes + (1 << 20))
    repo = {"config.json": b"{}", "modules.json": b"[]", "big.safetensors": oversize}

    with pytest.raises(ProvisionError, match="Stopped mid-transfer"):
        pin(entry, "python-st", root=tmp_path, inner=_repo_transport(repo))

    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert not any(p.name.startswith(".") and p.name.endswith(".part") for p in written)


def test_pin_refuses_a_licence_change(tmp_path: Path) -> None:
    catalog = load_catalog("models-catalog.json")
    entry = catalog.entry("stage_a_default")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "sha": COMMIT,
                "cardData": {"license": "cc-by-nc-4.0"},
                "siblings": [{"rfilename": "model.safetensors"}],
            },
        )

    with pytest.raises(ProvisionError, match="licence is"):
        pin(entry, "python-st", root=tmp_path, inner=httpx.MockTransport(handler))


def test_install_verifies_every_byte_against_the_lock(tmp_path: Path) -> None:
    locked = _locked()
    lines = list(install(locked, root=tmp_path, inner=_repo_transport({"model.safetensors": BODY})))
    assert any(line.startswith("fetched") for line in lines)
    assert not verify_locked(locked, root=tmp_path)


def test_a_file_that_changed_underneath_the_lock_is_refused_not_refetched(
    tmp_path: Path,
) -> None:
    locked = _locked()
    list(install(locked, root=tmp_path, inner=_repo_transport({"model.safetensors": BODY})))
    target = tmp_path / "stage_a_default.python-st" / COMMIT / "model.safetensors"
    target.write_bytes(b"tampered")

    with pytest.raises(ProvisionError, match="Refusing to overwrite"):
        list(install(locked, root=tmp_path, inner=_repo_transport({"model.safetensors": BODY})))


def test_a_download_that_does_not_match_the_lock_is_deleted(tmp_path: Path) -> None:
    locked = _locked()
    with pytest.raises(ProvisionError, match="do not match the lock"):
        list(install(locked, root=tmp_path, inner=_repo_transport({"model.safetensors": b"other"})))
    target = tmp_path / "stage_a_default.python-st" / COMMIT / "model.safetensors"
    assert not target.exists()


def test_a_verified_install_loads_by_path_and_never_by_repo_id(tmp_path: Path) -> None:
    locked = _locked()
    list(install(locked, root=tmp_path, inner=_repo_transport({"model.safetensors": BODY})))
    lock = Lock(models={"stage_a_default.python-st": locked, "stage_b_default.python-st": locked})
    seen: list[str] = []

    def loader(path: str) -> object:
        seen.append(path)
        return object()

    build_local_backend(lock, root=tmp_path, loaders=(loader, loader))

    assert seen and all(Path(p).is_dir() for p in seen)
    assert not any(p == locked.repo_id for p in seen)


def test_resolve_paths_names_which_model_is_missing(tmp_path: Path) -> None:
    lock = Lock(
        models={"stage_a_default.python-st": _locked(), "stage_b_default.python-st": _locked()}
    )
    with pytest.raises(BackendUnavailable, match="potion-retrieval-32M"):
        resolve_paths(lock, root=tmp_path)


def test_the_status_command_touches_nothing(tmp_path: Path, capsys) -> None:
    locked = _locked()
    lock_path = tmp_path / "models.lock"
    write_lock(Lock(models={"stage_a_default.python-st": locked}), lock_path)

    assert (
        main(
            [
                "setup-models",
                "--status",
                "--lock",
                str(lock_path),
                "--models-dir",
                str(tmp_path / "weights"),
            ]
        )
        == 0
    )
    assert "MISSING" in capsys.readouterr().out


def test_the_setup_client_follows_a_redirect_to_the_regional_content_host() -> None:
    # The owner's first pin attempt was refused at us.aws.cdn.hf.co, which no enumerated
    # list contained. Enumerating that one host moves the failure to the next region.
    from mailweave.net.egress import check_url

    for host in ("us.aws.cdn.hf.co", "eu.aws.cdn.hf.co", "cdn-lfs.huggingface.co"):
        check_url(f"https://{host}/f", SETUP_EGRESS_ALLOWLIST, MODEL_CDN_SUFFIXES)


def test_a_suffix_does_not_admit_a_lookalike_host() -> None:
    from mailweave.net.egress import check_url

    for host in ("evilhf.co", "hf.co.attacker.test", "notcdn.hf.co.evil.test"):
        with pytest.raises(EgressBlocked):
            check_url(f"https://{host}/f", SETUP_EGRESS_ALLOWLIST, MODEL_CDN_SUFFIXES)


def test_the_runtime_client_takes_no_suffixes_at_all() -> None:
    # A suffix is weaker than an exact match, and it does not get to weaken the pair the
    # server itself runs against.
    with build_client() as client, pytest.raises(EgressBlocked):
        client.get("https://us.aws.cdn.hf.co/f")


def test_a_set_that_requires_and_excludes_the_same_file_is_refused() -> None:
    # The one shape that would make the second-line excludes incoherent.
    from mailweave.models.catalog import ArtifactSet

    with pytest.raises(CatalogError, match="both required and excluded"):
        ArtifactSet(
            name="x",
            runtime="sentence-transformers",
            max_total_bytes=10,
            required=("config.json",),
            optional=(),
            exclude=("config.json",),
            why="a reason",
        )
