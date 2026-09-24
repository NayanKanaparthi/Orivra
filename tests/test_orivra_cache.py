"""The bounded cache: every key dimension invalidates, and a key is never permission to serve.

Plan §5.4 says no dimension of the key is optional, and §5.3 says the key alone never
authorises a serve. Both are properties whose absence is silent - a cache that ignores a
dimension returns a plausible wrong answer, and one that trusts its own `permission_hash`
serves a user data they lost access to - so both are tested by construction rather than by
reading the code.

The dimension sweep is written as a loop over the key's own fields rather than as one test per
field, so a dimension added later is covered the day it is added rather than the day someone
remembers to add a test for it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from orivra.cache import (
    BoundedCache,
    CacheKey,
    CacheKind,
    Revalidation,
    RevalidationReason,
    Serve,
)
from orivra.cache.store import TTL_BY_KIND

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
YES = lambda key: Revalidation(  # noqa: E731
    ok=True, reason=RevalidationReason.UNCHANGED, detail="nothing moved"
)
NO = lambda key: Revalidation(  # noqa: E731
    ok=False, reason=RevalidationReason.ACCESS_CHANGED, detail="the caller may no longer see it"
)


def _key(**overrides) -> CacheKey:
    fields = {
        "principal": "sha256:account-a",
        "connector": "gmail",
        "native_id": "m-1",
        "content_version": "99120034",
        "permission_hash": "perm-1",
        "extraction_schema_version": "v1",
        "redaction_policy": "default",
        "kind": CacheKind.METADATA,
        "model_id": None,
    }
    fields.update(overrides)
    return CacheKey(**fields)  # type: ignore[arg-type]


@pytest.fixture
def cache() -> BoundedCache:
    return BoundedCache(now=lambda: NOW)


# -- the key is the whole identity --------------------------------------------------------------


def test_every_key_dimension_changes_the_entry_it_addresses(cache: BoundedCache) -> None:
    """**The sweep.** One entry is written; every dimension is then varied one at a time and
    must miss. A dimension that did not change the key is a dimension that lets an entry be
    served for a question it does not answer - a vector from another model, structure from
    another revision, anything at all belonging to another user."""
    cache.put(_key(), "written under the original key")
    variations = {
        "principal": "sha256:account-b",
        "connector": "drive",
        "native_id": "m-2",
        "content_version": "99120099",
        "permission_hash": "perm-2",
        "extraction_schema_version": "v2",
        "redaction_policy": "strict",
        "kind": CacheKind.STRUCTURE,
        "model_id": "text-embed@3",
    }
    assert set(variations) == set(CacheKey.__dataclass_fields__), (
        "a key dimension exists that this sweep does not vary; it would be uncovered"
    )
    for name, value in variations.items():
        read = cache.get(_key(**{name: value}), revalidate=YES)
        assert read.outcome is Serve.MISS, f"varying {name} still hit the original entry"
    assert cache.get(_key(), revalidate=YES).usable, "the original entry was disturbed"


def test_the_key_tuple_is_readable_beside_its_hash() -> None:
    """A key you cannot read back is a key nobody can audit, and the first question after a
    wrong serve is always what it was keyed on."""
    key = _key()
    assert key.tuple_form["principal"] == "sha256:account-a"
    assert key.tuple_form["kind"] == CacheKind.METADATA.value
    assert len(key.hash) == 64
    assert _key().hash == key.hash
    assert _key(native_id="other").hash != key.hash


def test_no_dimension_may_be_empty() -> None:
    for name in (
        "principal",
        "connector",
        "native_id",
        "content_version",
        "permission_hash",
        "extraction_schema_version",
        "redaction_policy",
    ):
        with pytest.raises(ValueError):
            _key(**{name: ""})


def test_a_vector_without_a_model_is_refused() -> None:
    """`None` is a value meaning "no model was involved". For a vector that is false, and an
    entry claiming it would be read back after an upgrade as though the new model made it."""
    with pytest.raises(ValueError):
        _key(kind=CacheKind.VECTOR, model_id=None)
    assert _key(kind=CacheKind.VECTOR, model_id="text-embed@3").hash


# -- a key is never permission to serve ---------------------------------------------------------


def test_a_matching_key_still_does_not_serve_without_a_live_yes(cache: BoundedCache) -> None:
    """§5.3. The `permission_hash` proves the entry *was written* under an access state; access
    can be revoked with nothing here noticing."""
    cache.put(_key(), "sensitive")
    refused = cache.get(_key(), revalidate=NO)
    assert refused.outcome is Serve.UNVERIFIED
    assert refused.value is None
    # The reason is the revalidator's own, carried rather than replaced. This one really is
    # about access; `test_an_unsuccessful_revalidation_keeps_its_own_reason` covers the ones
    # that are not and used to be described as though they were.
    assert refused.reason is RevalidationReason.ACCESS_CHANGED
    assert refused.why == "the caller may no longer see it"
    assert cache.get(_key(), revalidate=YES).value == "sensitive"


def test_a_revalidation_that_cannot_complete_is_not_a_yes(cache: BoundedCache) -> None:
    """The degradation order is fresh read, resync, explicit inconclusive. The cached value is
    not on that list, so a check that raised must not fall through to it."""

    def exploding(key: CacheKey) -> bool:
        raise ConnectionError("the source did not answer")

    cache.put(_key(), "sensitive")
    read = cache.get(_key(), revalidate=exploding)
    assert read.outcome is Serve.UNVERIFIED
    assert read.value is None
    assert "did not finish is not a yes" in read.why


def test_the_revalidation_callable_is_required_by_the_signature() -> None:
    """Not a flag and not optional: a signature that let a caller omit the check would make
    the safe path the one you have to remember."""
    import inspect

    parameter = inspect.signature(BoundedCache.get).parameters["revalidate"]
    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_the_revalidator_is_handed_the_key_it_is_deciding_about(cache: BoundedCache) -> None:
    seen: list[CacheKey] = []
    cache.put(_key(), "v")
    cache.get(_key(), revalidate=lambda key: seen.append(key)
        or Revalidation(ok=True, reason=RevalidationReason.UNCHANGED, detail='ok'))
    assert seen and seen[0].native_id == "m-1"


# -- invalidation: time, feed, and purge ---------------------------------------------------------


def test_each_kind_expires_on_its_own_bound(cache: BoundedCache) -> None:
    """Bounded even when nothing upstream changed, so an abandoned workspace decays."""
    for kind, ttl in TTL_BY_KIND.items():
        model = "text-embed@3" if kind is CacheKind.VECTOR else None
        key = _key(kind=kind, model_id=model)
        store = BoundedCache(now=lambda: NOW)
        store.put(key, "v")
        assert store.get(key, revalidate=YES).usable
        store.now = lambda ttl=ttl: NOW + ttl
        read = store.get(key, revalidate=YES)
        assert read.outcome is Serve.EXPIRED, kind


def test_a_negative_result_expires_in_minutes_not_hours() -> None:
    """Absence is the most expensive thing to be wrong about."""
    assert TTL_BY_KIND[CacheKind.NEGATIVE] <= timedelta(minutes=15)
    assert TTL_BY_KIND[CacheKind.NEGATIVE] < TTL_BY_KIND[CacheKind.VECTOR]


def test_a_change_feed_drops_every_entry_for_the_item_whatever_its_version(
    cache: BoundedCache,
) -> None:
    """The feed reports an id, not the version the cache happens to hold, so a keyed lookup
    would miss exactly the stale entries the feed is telling us about."""
    cache.put(_key(content_version="v1", kind=CacheKind.METADATA), "old metadata")
    cache.put(_key(content_version="v2", kind=CacheKind.STRUCTURE), "old structure")
    cache.put(
        _key(content_version="v1", kind=CacheKind.VECTOR, model_id="text-embed@3"), [0.1]
    )
    cache.put(_key(native_id="untouched"), "a different message")
    assert cache.invalidate_native(connector="gmail", native_id="m-1") == 3
    assert cache.get(_key(content_version="v1"), revalidate=YES).outcome is Serve.MISS
    assert cache.get(_key(native_id="untouched"), revalidate=YES).usable


def test_invalidation_is_scoped_to_one_connector(cache: BoundedCache) -> None:
    cache.put(_key(connector="gmail"), "gmail entry")
    cache.put(_key(connector="drive"), "drive entry")
    assert cache.invalidate_native(connector="gmail", native_id="m-1") == 1
    assert cache.get(_key(connector="drive"), revalidate=YES).usable


def test_purge_removes_everything(cache: BoundedCache) -> None:
    for index in range(5):
        cache.put(_key(native_id=f"m-{index}"), index)
    assert cache.purge() == 5
    assert len(cache) == 0


def test_the_cache_is_bounded_by_count_and_drops_the_oldest(cache: BoundedCache) -> None:
    small = BoundedCache(now=lambda: NOW, capacity=3)
    for index in range(4):
        small.now = lambda index=index: NOW + timedelta(seconds=index)
        small.put(_key(native_id=f"m-{index}"), index)
    assert len(small) == 3
    assert small.get(_key(native_id="m-0"), revalidate=YES).outcome is Serve.MISS
    assert small.get(_key(native_id="m-3"), revalidate=YES).usable


# -- what may not be cached at all ----------------------------------------------------------------


def test_the_kinds_are_the_plans_cached_category_and_carry_no_text() -> None:
    """§5.1: no message bodies, no document bodies, no derived summaries, no inferred edges.
    v1 avoids the encrypted-index question by not persisting text at all, so there is no kind
    that could hold any."""
    assert {kind.value for kind in CacheKind} == {
        "vector",
        "metadata",
        "structure",
        "observed_edge",
        "entity_candidate",
        "negative",
    }
    assert not [kind for kind in CacheKind if "body" in kind.value or "text" in kind.value]
    assert not [kind for kind in CacheKind if "summary" in kind.value]
    assert "inferred_edge" not in {kind.value for kind in CacheKind}


# -- the reason a revalidation gave, not a single sentence for every no -------------------------


@pytest.mark.parametrize(
    ("reason", "rebaseline"),
    [
        (RevalidationReason.CHANGED, False),
        (RevalidationReason.INCONCLUSIVE, False),
        (RevalidationReason.WATERMARK_EXPIRED, True),
        (RevalidationReason.ACCESS_CHANGED, False),
    ],
)
def test_an_unsuccessful_revalidation_keeps_its_own_reason(
    cache: BoundedCache, reason: RevalidationReason, rebaseline: bool
) -> None:
    """Four ways a check can decline, and only one of them is about access.

    They were all reported as "written under an access state that no longer holds", so a live
    run whose change feed could not finish walking was told its permissions had moved. The
    reason now travels, and `rebaseline` says which of them means the *watermark* is what went
    stale rather than the entry.
    """
    cache.put(_key(), "sensitive")
    read = cache.get(
        _key(),
        revalidate=lambda key: Revalidation(
            ok=False, reason=reason, detail=f"because {reason.value}"
        ),
    )
    assert read.outcome is Serve.UNVERIFIED
    assert read.value is None, "a declined revalidation served the value anyway"
    assert read.reason is reason
    assert read.why == f"because {reason.value}"
    assert read.rebaseline is rebaseline


def test_a_probe_that_raises_is_its_own_reason_and_not_an_access_finding(
    cache: BoundedCache,
) -> None:
    cache.put(_key(), "sensitive")

    def exploding(key: CacheKey) -> Revalidation:
        raise TimeoutError("the feed did not answer")

    read = cache.get(_key(), revalidate=exploding)
    assert read.outcome is Serve.UNVERIFIED
    assert read.reason is RevalidationReason.PROBE_FAILED
    assert "access" not in read.why, "a check that raised was reported as an access decision"


def test_a_yes_may_only_carry_the_one_reason_that_licenses_serving() -> None:
    """`ok=True` with any reason but `unchanged` would be a serve nothing established."""
    with pytest.raises(ValueError, match="only reason to serve"):
        Revalidation(ok=True, reason=RevalidationReason.CHANGED, detail="served anyway")
