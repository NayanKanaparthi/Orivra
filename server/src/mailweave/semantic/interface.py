"""SEM-03 - the semantic interface, and the two things it refuses to let an implementer do.

AD D.5 specifies exactly two operations::

    embed(texts: list[str]) -> list[Vector]
    rerank(query: str, candidates: list[str]) -> list[float]

A local implementation is registered by default; a second registers without touching
retrieval logic. That is the whole point of the interface: SEM-02's "hosted is never
required" is a property of the *wiring*, and a wiring claim is only checkable if there is
one seam to check.

Two properties are enforced here rather than left to whoever writes a backend.

**A backend returns closed types, and the shape is checked at the seam.** AD D.8 rests
INJ-06 on the observation that embeddings and cross-encoder scores are float vectors and
floats - closed by construction, so no free-text injection surface exists on the default
path. That reasoning holds only if what comes *back* is actually those types. A backend is
foreign code by design (the whole point is that a second one can be dropped in), so the
registry checks the return shape at the boundary instead of trusting the annotation. A
backend that returns a string where a float belongs is refused with `BackendContractError`,
not passed on to a ranker that will format it into a response.

**A missing backend is a declined rung, never a silent no-op.** SEM-02 makes a silent no-op
a BLOCKER by construction, so `BackendUnavailable` is a distinct type from
`BackendContractError`: the first is D.5's deterministic fallback (the ladder continues and
says why), the second is a defect in a backend and is not something to degrade past.

## Why the arity check is here and not in the caller

`rerank` returns one score per candidate. A backend that returns a shorter list would let a
caller zip scores against candidates and silently misattribute every score after the first
gap - the same class of defect as R-M1-003, where a structurally valid value pointed at the
wrong thing. Length is checked against the input here, once, rather than at each call site.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Sequence
from typing import Final, Protocol, runtime_checkable

#: A dense embedding. Deliberately a plain tuple of floats rather than a numpy array: the
#: type must be closed for D.8's INJ-06 argument, and `ndarray` carries `dtype=object`,
#: which can hold anything at all.
Vector = tuple[float, ...]


class SemanticError(Exception):
    """Base for the two failure modes, so a caller can catch the pair deliberately."""


class BackendUnavailable(SemanticError):
    """No usable backend: weights absent, runtime missing, or none registered.

    This is D.5's deterministic fallback condition. The rung emits `not_tried` with this
    reason and the ladder continues. It is **not** an error the caller reports as a
    failure, because a machine without model weights is a supported configuration.
    """


class BackendContractError(SemanticError):
    """A registered backend returned something the interface does not permit.

    Distinct from `BackendUnavailable` on purpose: this is a defect, and degrading past it
    would mean a ranker consuming values whose type was never checked.
    """


@runtime_checkable
class SemanticBackend(Protocol):
    """SEM-03. Two methods, and an identity that reaches every score's provenance."""

    @property
    def model_id(self) -> str:
        """Stable identifier, e.g. ``minishlab/potion-retrieval-32M``."""

    @property
    def model_revision(self) -> str:
        """The pinned revision. AD D.8: a model change silently changes ranking, so this
        appears in every trace and every score provenance string."""

    def embed(self, texts: Sequence[str]) -> list[Vector]: ...

    def rerank(self, query: str, candidates: Sequence[str]) -> list[float]: ...


def _finite(value: object) -> bool:
    # `bool` is an `int` and would pass a numeric check; a backend returning `True` for a
    # score is a contract error, not a score of 1.0. Same reasoning as the exact-typing in
    # the preflight record walk (R-SEC-055): `isinstance` admits subclasses, and here the
    # subclass means something different from its base.
    if type(value) is not float and type(value) is not int:
        return False
    return math.isfinite(float(value))


def checked_embed(backend: SemanticBackend, texts: Sequence[str]) -> list[Vector]:
    """Call `embed` and refuse anything that is not a list of equal-length float vectors.

    Equal length matters: cosine similarity between vectors of different dimension is not
    a smaller number, it is a `ValueError` at best and a wrong number at worst if someone
    zero-pads to make it work.
    """
    raw = backend.embed(list(texts))
    if not isinstance(raw, list) or len(raw) != len(texts):
        raise BackendContractError(
            f"{backend.model_id}: embed returned {type(raw).__name__} of "
            f"{len(raw) if isinstance(raw, list) else 'unknown'} for {len(texts)} texts"
        )
    out: list[Vector] = []
    width: int | None = None
    for index, vector in enumerate(raw):
        if not isinstance(vector, (list, tuple)):
            raise BackendContractError(
                f"{backend.model_id}: embed item {index} is {type(vector).__name__}, not a vector"
            )
        if width is None:
            width = len(vector)
        elif len(vector) != width:
            raise BackendContractError(
                f"{backend.model_id}: embed returned vectors of differing width "
                f"({width} then {len(vector)} at item {index})"
            )
        if not all(_finite(component) for component in vector):
            raise BackendContractError(
                f"{backend.model_id}: embed item {index} carries a "
                "non-finite or non-numeric component"
            )
        out.append(tuple(float(component) for component in vector))
    if width == 0:
        raise BackendContractError(f"{backend.model_id}: embed returned zero-width vectors")
    return out


def checked_rerank(backend: SemanticBackend, query: str, candidates: Sequence[str]) -> list[float]:
    """Call `rerank` and refuse a result that is not one finite float per candidate."""
    raw = backend.rerank(query, list(candidates))
    if not isinstance(raw, list) or len(raw) != len(candidates):
        raise BackendContractError(
            f"{backend.model_id}: rerank returned {type(raw).__name__} of "
            f"{len(raw) if isinstance(raw, list) else 'unknown'} for {len(candidates)} candidates"
        )
    if not all(_finite(score) for score in raw):
        raise BackendContractError(
            f"{backend.model_id}: rerank returned a non-finite or non-numeric score"
        )
    return [float(score) for score in raw]


class BackendRegistry:
    """Where the default local backend and any opt-in swap are registered.

    A registry rather than an import so that AD D.5's "a second implementation registers
    without touching retrieval logic" is literally true: retrieval asks the registry, and
    nothing in the ladder names a model.

    ## The backend is built once per process, and that is not an optimisation

    `acquire` memoises. The first version built a backend on every call, and the owner's
    smoke run priced that mistake: **36,543 ms to load** potion-retrieval-32M and
    bge-reranker-base on the dev laptop. `MAX_SEMANTIC_MS` is 6,000. A per-call load means
    the semantic rung can never complete inside its own budget, on any machine, for any
    query - not "is slow", cannot run. The rung would have declined on every query and the
    reason would have read as a timeout rather than as an architecture mistake.

    The server is one long-lived process per stdio session (`run_stdio`), so per-process is
    the right lifetime: the load is paid once at first use and every later query sees a
    warm model. PF-4 measures the two separately for exactly this reason, and reports the
    second acquire's cost as evidence that the reuse is real rather than assumed.

    **A decline is remembered too.** A machine with no weights is a supported
    configuration, and retrying a failing load on every query would spend the failure over
    and over. The consequence is stated rather than hidden: installing models into a
    running server does not take effect until the process restarts, which for an stdio
    session means the next session.
    """

    def __init__(self) -> None:
        self._factories: dict[str, object] = {}
        self._default: str | None = None
        self._built: dict[str, SemanticBackend] = {}
        self._declined: dict[str, SemanticError] = {}
        self._lock = threading.Lock()

    def register(self, name: str, factory: object, *, default: bool = False) -> None:
        if name in self._factories:
            raise ValueError(f"a backend is already registered as {name!r}")
        self._factories[name] = factory
        if default or self._default is None:
            self._default = name

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def acquire(self, name: str | None = None) -> SemanticBackend:
        """The named backend, or the default, **built at most once per process**.

        Raises `BackendUnavailable` when nothing is registered or the factory declines,
        which is the deterministic-fallback condition and not an error path.
        """
        chosen = name or self._default
        if chosen is None:
            raise BackendUnavailable("no semantic backend is registered")
        factory = self._factories.get(chosen)
        if factory is None:
            raise BackendUnavailable(f"no semantic backend registered as {chosen!r}")
        # The lock is held across the build, not only around the dictionary. Two concurrent
        # queries are permitted (`MAX_CONCURRENT_QUERIES`), and a check-then-build without
        # it would load the model twice and pay the cold cost twice.
        with self._lock:
            cached = self._built.get(chosen)
            if cached is not None:
                return cached
            remembered = self._declined.get(chosen)
            if remembered is not None:
                raise remembered
            try:
                backend = factory()  # type: ignore[operator]
                if not isinstance(backend, SemanticBackend):
                    raise BackendContractError(
                        f"{chosen!r} produced {type(backend).__name__}, which is not a "
                        "SemanticBackend"
                    )
            except SemanticError as failure:
                self._declined[chosen] = failure
                raise
            self._built[chosen] = backend
            return backend

    def is_built(self, name: str | None = None) -> bool:
        """Whether this process has already paid the load cost for `name`."""
        chosen = name or self._default
        return chosen is not None and chosen in self._built

    def reset(self) -> None:
        """Forget what was built and what declined. For tests and for `PF-4`'s cold arm."""
        with self._lock:
            self._built.clear()
            self._declined.clear()


#: The process-wide registry. Populated by `mailweave.semantic.local` on import of the
#: package; a swap registers against this same object.
REGISTRY: Final[BackendRegistry] = BackendRegistry()
