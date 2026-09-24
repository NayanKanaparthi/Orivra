"""SEM-03: the seam, and the two things it will not pass through.

AD D.8 rests INJ-06 on embeddings and cross-encoder scores being closed types by
construction - float vectors and floats - so no free-text injection surface exists on the
default path. That argument is about what a backend *returns*, and a backend is foreign code
by design, so the seam checks the shape rather than trusting the annotation.
"""

from __future__ import annotations

import pytest

from mailweave.semantic import (
    BackendContractError,
    BackendRegistry,
    BackendUnavailable,
    checked_embed,
    checked_rerank,
)


class _Backend:
    """A minimal conforming backend whose two methods are supplied per test."""

    def __init__(self, embed_result: object = None, rerank_result: object = None) -> None:
        self._embed_result = embed_result
        self._rerank_result = rerank_result

    @property
    def model_id(self) -> str:
        return "test/backend"

    @property
    def model_revision(self) -> str:
        return "rev0"

    def embed(self, texts):
        return self._embed_result

    def rerank(self, query, candidates):
        return self._rerank_result


class TestEmbedReturnsClosedTypes:
    def test_a_conforming_result_passes_through_as_tuples_of_float(self) -> None:
        backend = _Backend(embed_result=[[1.0, 0.0], [0.0, 1.0]])
        assert checked_embed(backend, ["a", "b"]) == [(1.0, 0.0), (0.0, 1.0)]

    def test_a_short_result_is_refused_rather_than_zipped_against_the_inputs(self) -> None:
        # Silently zipping would misattribute every vector after the gap: a structurally
        # valid value pointing at the wrong thing, which is R-M1-003's shape.
        backend = _Backend(embed_result=[[1.0, 0.0]])
        with pytest.raises(BackendContractError, match="for 2 texts"):
            checked_embed(backend, ["a", "b"])

    def test_vectors_of_differing_width_are_refused(self) -> None:
        # Cosine between different dimensions is not a smaller number; it is wrong, or it
        # is right only after somebody zero-pads to make it run.
        backend = _Backend(embed_result=[[1.0, 0.0], [1.0, 0.0, 0.0]])
        with pytest.raises(BackendContractError, match="differing width"):
            checked_embed(backend, ["a", "b"])

    def test_a_non_finite_component_is_refused(self) -> None:
        backend = _Backend(embed_result=[[float("nan"), 0.0]])
        with pytest.raises(BackendContractError, match="non-finite"):
            checked_embed(backend, ["a"])

    def test_a_string_where_a_component_belongs_is_refused(self) -> None:
        backend = _Backend(embed_result=[["0.9", 0.0]])
        with pytest.raises(BackendContractError, match="non-finite or non-numeric"):
            checked_embed(backend, ["a"])

    def test_zero_width_vectors_are_refused(self) -> None:
        backend = _Backend(embed_result=[[], []])
        with pytest.raises(BackendContractError, match="zero-width"):
            checked_embed(backend, ["a", "b"])


class TestRerankReturnsOneFiniteScorePerCandidate:
    def test_a_conforming_result_passes_through(self) -> None:
        backend = _Backend(rerank_result=[0.9, 0.1, 0.5])
        assert checked_rerank(backend, "q", ["a", "b", "c"]) == [0.9, 0.1, 0.5]

    def test_a_missing_score_is_refused(self) -> None:
        backend = _Backend(rerank_result=[0.9])
        with pytest.raises(BackendContractError, match="for 3 candidates"):
            checked_rerank(backend, "q", ["a", "b", "c"])

    def test_a_bool_is_not_a_score(self) -> None:
        # `bool` is an `int`, so a numeric check admits `True` and it becomes 1.0 - a
        # maximal relevance score produced by a backend that returned a flag.
        backend = _Backend(rerank_result=[True, 0.2])
        with pytest.raises(BackendContractError, match="non-finite or non-numeric"):
            checked_rerank(backend, "q", ["a", "b"])

    def test_an_infinite_score_is_refused(self) -> None:
        backend = _Backend(rerank_result=[float("inf"), 0.2])
        with pytest.raises(BackendContractError, match="non-finite"):
            checked_rerank(backend, "q", ["a", "b"])


class TestTheRegistryDeclinesRatherThanNoOps:
    def test_an_empty_registry_declines_and_the_type_says_it_is_a_fallback(self) -> None:
        # SEM-02 makes a silent no-op a BLOCKER by construction. `BackendUnavailable` is
        # the deterministic-fallback condition, distinct from a contract defect.
        registry = BackendRegistry()
        with pytest.raises(BackendUnavailable):
            registry.acquire()

    def test_an_unknown_name_declines_rather_than_falling_back_to_the_default(self) -> None:
        # A caller that asked for a specific model and silently got another would have its
        # scores attributed to a model that never produced them.
        registry = BackendRegistry()
        registry.register("local", lambda: _Backend(embed_result=[[1.0]]))
        with pytest.raises(BackendUnavailable, match="hosted"):
            registry.acquire("hosted")

    def test_a_factory_producing_a_non_backend_is_a_contract_error_not_a_fallback(self) -> None:
        registry = BackendRegistry()
        registry.register("broken", lambda: object())
        with pytest.raises(BackendContractError):
            registry.acquire("broken")

    def test_registering_the_same_name_twice_is_refused(self) -> None:
        registry = BackendRegistry()
        registry.register("local", lambda: _Backend())
        with pytest.raises(ValueError, match="already registered"):
            registry.register("local", lambda: _Backend())

    def test_a_second_implementation_registers_without_touching_retrieval(self) -> None:
        # AD D.5's claim, as a test: two backends coexist and are chosen by name.
        registry = BackendRegistry()
        registry.register("local", lambda: _Backend(rerank_result=[0.1]), default=True)
        registry.register("swap", lambda: _Backend(rerank_result=[0.9]))
        assert registry.names() == ("local", "swap")
        assert checked_rerank(registry.acquire(), "q", ["a"]) == [0.1]
        assert checked_rerank(registry.acquire("swap"), "q", ["a"]) == [0.9]
