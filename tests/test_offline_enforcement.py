"""SEM-02 / NFR-01: hosted is never required, and the test is mechanical (AD D.8, PF-5).

**The claim is an absence, so a passing smoke run does not establish it.** "The server never
contacts a model host at runtime" is not shown by a run that happened not to - a warm HTTP
cache, a machine with the weights already present, or a library that fell back silently all
produce the same green. What shows it is a run in which the model host *cannot* be reached
and the semantic rung works anyway, plus a static guard that no runtime module can name the
host at all.

Three layers, and each catches what the others cannot:

  * **Static.** The `no-model-host-at-runtime` sweep refuses a model-host literal outside the
    one provisioner module, and refuses a runtime import of that provisioner. It catches the
    call site that does not run in this environment.
  * **Environmental.** `HF_HUB_OFFLINE=1` and friends are set *before* any hub-aware library
    is imported, and `local_files_only=True` is passed at the loader. It catches the
    revalidation call a library makes on its own.
  * **Egress.** The runtime allowlist is exactly two Gmail hosts, and the setup-time
    allowlist is disjoint from it. It catches everything else, including a library that
    ignored the first two.

PF-5 runs the whole suite cold with the model host blocked at the socket - that is the live
half. This file is the half that can be executed without a laptop.
"""

from __future__ import annotations

import httpx
import pytest

from mailweave.constants import (
    MODEL_CDN_HOST,
    MODEL_HOST,
    RUNTIME_EGRESS_ALLOWLIST,
    SETUP_EGRESS_ALLOWLIST,
)
from mailweave.errors import EgressBlocked
from mailweave.net.egress import build_client, check_url
from mailweave.semantic.interface import BackendRegistry, BackendUnavailable
from mailweave.semantic.local import OFFLINE_ENVIRONMENT, force_offline


def test_the_runtime_allowlist_and_the_setup_allowlist_are_disjoint() -> None:
    """PF-5 is only meaningful while the two sets do not overlap.

    The model host is reachable at setup time and unreachable at runtime; if a host were in
    both, "blocked at runtime" would be a claim the allowlist does not make.
    """
    assert set(RUNTIME_EGRESS_ALLOWLIST) & set(SETUP_EGRESS_ALLOWLIST) == set()
    assert MODEL_HOST in SETUP_EGRESS_ALLOWLIST
    assert MODEL_HOST not in RUNTIME_EGRESS_ALLOWLIST
    assert MODEL_CDN_HOST not in RUNTIME_EGRESS_ALLOWLIST


@pytest.mark.parametrize(
    "url",
    [
        f"https://{MODEL_HOST}/api/models/minishlab/potion-retrieval-32M",
        f"https://{MODEL_CDN_HOST}/repos/abc/model.safetensors",
        "https://cdn-lfs.hf.co/repos/abc/model.safetensors",
    ],
)
def test_the_runtime_allowlist_refuses_every_model_host_shape(url: str) -> None:
    with pytest.raises(EgressBlocked):
        check_url(url)


def test_a_runtime_client_cannot_reach_the_model_host_at_the_socket() -> None:
    """Not "does not", but "cannot": the transport refuses before a connection is opened."""
    reached: list[str] = []

    def inner(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        reached.append(str(request.url))
        return httpx.Response(200)

    client = build_client(inner=httpx.MockTransport(inner))
    with pytest.raises(EgressBlocked):
        client.get(f"https://{MODEL_HOST}/api/models/x")
    assert reached == [], "a runtime request reached the transport for the model host"


def test_the_offline_flags_are_set_before_any_hub_aware_library_is_imported() -> None:
    """`HF_HUB_OFFLINE` read after import is a flag the library has already ignored."""
    import os

    import mailweave.semantic.local  # noqa: F401  - importing it is the act under test

    for name, value in OFFLINE_ENVIRONMENT.items():
        assert os.environ.get(name) == value, f"{name} was not set by importing the backend"


def test_force_offline_is_idempotent_and_total_over_the_declared_flags() -> None:
    environ: dict[str, str] = {}
    force_offline(environ)
    force_offline(environ)
    assert environ == dict(OFFLINE_ENVIRONMENT)


def test_the_semantic_rung_declines_in_band_rather_than_reaching_for_a_host() -> None:
    """D.5's deterministic fallback (D6). A silent no-op is a BLOCKER by construction.

    On a machine with no weights - which this container is - the local factory must decline
    with `BackendUnavailable` and must not attempt a download to recover. The declining path
    is therefore also the path SEM-02's guard is about: it is where a hopeful `from_pretrained`
    with no `local_files_only` would sit.
    """
    from mailweave.semantic.local import register_default

    registry = BackendRegistry()

    def factory() -> object:
        from mailweave.models.lock import load_lock
        from mailweave.semantic.local import build_local_backend

        lock = load_lock("models.lock")
        return build_local_backend(lock, root="/nonexistent/mailweave-models")

    registry.register("local", factory, default=True)
    assert register_default is not None  # the shipped registration takes the same path
    with pytest.raises(BackendUnavailable):
        registry.acquire()


def test_the_registry_remembers_a_decline_rather_than_retrying_every_query() -> None:
    """A machine with no weights is supported, and retrying the failure costs every query."""
    from mailweave.semantic.interface import SemanticError

    calls: list[int] = []

    def factory() -> object:
        calls.append(1)
        raise BackendUnavailable("no weights here")

    registry = BackendRegistry()
    registry.register("local", factory, default=True)
    for _ in range(3):
        with pytest.raises(SemanticError):
            registry.acquire()
    assert calls == [1], "a declining factory was retried, so the failure is paid per query"


def test_the_guard_that_forbids_a_model_host_at_runtime_is_registered() -> None:
    """The static layer, asserted to exist rather than assumed to have run."""
    from pathlib import Path

    from tools.guards import sweeps

    assert hasattr(sweeps, "model_host_sweep")
    root = Path(__file__).resolve().parent.parent / "server" / "src"
    assert sweeps.model_host_sweep(root) == [], sweeps.model_host_sweep(root)


# -- the mutation harness can actually see this guarantee ---------------------------------------


def test_a_planted_subprocess_does_not_inherit_the_flags_it_is_meant_to_set() -> None:
    """R213's miss, as its own test: the harness handed the child the answer.

    `_environment` built the planted subprocess's environment from `dict(os.environ)`, and
    importing `mailweave.semantic.local` in the parent calls `force_offline()`, which writes
    those flags into the *parent's* process environment. The child therefore inherited exactly
    what the deleted line was supposed to establish, and the plant that deletes it passed.

    It was invisible in isolation and visible only in the full suite, because whether the
    parent had imported the backend yet decided the verdict. A mutation harness whose answer
    depends on what else ran first is not measuring the mutation - which is why this asserts
    the property of the environment rather than re-running the plant.
    """
    import os
    from pathlib import Path

    import mailweave.semantic.local  # noqa: F401  - the import that sets the parent's flags
    from tests.fixtures.replants import _environment, not_inherited

    assert set(OFFLINE_ENVIRONMENT) <= set(os.environ), (
        "this test is only meaningful once the parent process carries the flags"
    )
    planted = _environment(Path("/tmp/not-used-by-this-assertion"))
    leaked = sorted(name for name in OFFLINE_ENVIRONMENT if name in planted)
    assert leaked == [], (
        f"a planted subprocess would inherit {leaked}, so the plant that removes the code "
        "setting them cannot be caught"
    )
    assert not_inherited() == frozenset(OFFLINE_ENVIRONMENT)


def test_the_products_only_environment_writer_is_the_one_this_excludes() -> None:
    """The excluded set is derived, and this is what keeps the derivation complete.

    `not_inherited()` reads `OFFLINE_ENVIRONMENT`, which is right only while `force_offline`
    is the single place this codebase writes the process environment. A second writer would
    open the same hole for a different variable, silently, so it fails here instead.
    """
    import ast
    from pathlib import Path

    writers: list[str] = []
    for root in (Path("server/src"), Path("orivra/src")):
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                target = None
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in {"update", "setdefault", "pop", "clear"}:
                        target = node.func.value
                    elif node.func.attr in {"putenv", "unsetenv"}:
                        writers.append(f"{path}:{node.lineno} os.{node.func.attr}")
                        continue
                elif isinstance(node, ast.Assign):
                    for assigned in node.targets:
                        if isinstance(assigned, ast.Subscript):
                            target = assigned.value
                if target is None:
                    continue
                rendered = ast.unparse(target)
                if rendered in {"os.environ", "environ"}:
                    writers.append(f"{path}:{node.lineno} {rendered}")
    assert writers == ["server/src/mailweave/semantic/local.py:62 target"] or all(
        "semantic/local.py" in one for one in writers
    ), (
        f"the product writes the process environment somewhere new: {writers}. Add it to what "
        "not_inherited() derives, or a planted subprocess inherits that guarantee too"
    )
