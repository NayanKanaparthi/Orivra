"""EP §6.4's pool, both clauses, and the `cut_loss` that rests on it.

`cut_loss = pool_recall - recall` is the only thing EP §6.4 lets a reranker be justified by,
which makes the definition of "pool" an acceptance question rather than a detail. Two failures
are possible and both are tested here:

  * reading a pool that is not one - every search emits a `semantic` block whether or not the
    semantic rungs ran, and an empty one scored as a pool gives a **negative** cut_loss, which
    the metric's own model forbids;
  * having no pool at all on the arm the reranker must beat - the lexical baseline exposes no
    candidate set, so without EP's network-layer clause `cut_loss` is permanently unmeasurable
    there and the justification rule can never be satisfied *or* refused.
"""

from __future__ import annotations

import gzip
import json

import httpx
import pytest

from mailweave.net.egress import build_client
from mailweave_harness.evaluation.arms import CaseRun, Measured
from mailweave_harness.evaluation.hypotheses import mean_cut_loss
from mailweave_harness.evaluation.observe import FetchLog, FetchObserver
from mailweave_harness.seed.metrics import Disclosure, Terminal

BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _client(handler: object, log: FetchLog) -> httpx.Client:
    inner = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return build_client(inner=FetchObserver(inner, log))


def test_a_list_response_records_its_ids_as_listed_not_fetched() -> None:
    log = FetchLog()
    body = {"messages": [{"id": "m1"}, {"id": "m2"}], "resultSizeEstimate": 2}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    _client(handler, log).get(f"{BASE}/messages", params={"q": "invoice"})
    assert log.listed == {"m1", "m2"}
    assert log.fetched == set()


def test_a_message_get_records_the_id_from_the_path() -> None:
    log = FetchLog()
    _client(lambda request: httpx.Response(200, json={"id": "m9"}), log).get(
        f"{BASE}/messages/m9", params={"format": "full"}
    )
    assert log.fetched == {"m9"}


def test_an_attachment_path_is_not_read_as_a_message_id() -> None:
    log = FetchLog()
    _client(lambda request: httpx.Response(200, json={"data": ""}), log).get(
        f"{BASE}/messages/m9/attachments/a1"
    )
    assert log.fetched == set(), "the id in an attachment path is the attachment's parent"
    assert log.listed == set()


def test_a_thread_get_at_full_is_a_fetch_and_at_metadata_is_a_listing() -> None:
    log = FetchLog()
    body = {"id": "t1", "messages": [{"id": "a"}, {"id": "b"}]}
    client = _client(lambda request: httpx.Response(200, json=body), log)
    client.get(f"{BASE}/threads/t1", params={"format": "metadata"})
    assert log.listed == {"a", "b"} and log.fetched == set()
    client.get(f"{BASE}/threads/t1", params={"format": "full"})
    assert log.fetched == {"a", "b"}


def test_a_gzipped_body_is_parsed_and_reaches_the_caller_undamaged() -> None:
    """The observer must not decode on the caller's behalf, and must still read the ids."""
    log = FetchLog()
    payload = json.dumps({"messages": [{"id": "z1"}]}).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=gzip.compress(payload),
            headers={"content-encoding": "gzip", "content-type": "application/json"},
        )

    got = _client(handler, log).get(f"{BASE}/messages")
    assert log.listed == {"z1"}
    assert got.json() == {"messages": [{"id": "z1"}]}


def test_a_body_that_will_not_parse_costs_the_measurement_and_not_the_request() -> None:
    log = FetchLog()
    got = _client(lambda request: httpx.Response(200, content=b"\x00 not json"), log).get(
        f"{BASE}/messages"
    )
    assert got.status_code == 200
    assert log.observed == frozenset()


def test_the_observer_does_not_widen_the_egress_allowlist() -> None:
    log = FetchLog()
    client = _client(lambda request: httpx.Response(200, json={}), log)
    with pytest.raises(Exception) as caught:
        client.get("https://example.invalid/whatever")
    assert "example.invalid" in str(caught.value) or "allow" in str(caught.value).lower()


def test_take_drains_so_one_cases_pool_is_not_the_next_cases_pool() -> None:
    log = FetchLog()
    client = _client(lambda request: httpx.Response(200, json={"messages": [{"id": "a"}]}), log)
    client.get(f"{BASE}/messages")
    assert log.take() == frozenset({"a"})
    assert log.take() == frozenset()


def _run(
    case_id: str, *, arm: str, pool: frozenset[str] | None, carried: dict[str, str]
) -> CaseRun:
    return CaseRun(
        case_id=case_id,
        family="ranking_stress",
        arm=arm,
        terminal=Terminal.ANSWERED,
        disclosure=Disclosure(content_by_id=carried),
        pool_ids=pool,
        pool_source=None if pool is None else "test",
    )


def test_cut_loss_is_unmeasured_without_a_pool_and_never_zero() -> None:
    runs = [_run("a", arm="x", pool=None, carried={"m": "the quote"})]
    got = mean_cut_loss(runs, family="ranking_stress", arm="x", required={"a": {"m": "the quote"}})
    assert got.value is None
    assert got.state is Measured.UNMEASURED


def test_evidence_in_the_pool_and_disclosed_is_a_cut_loss_of_zero() -> None:
    runs = [_run("a", arm="x", pool=frozenset({"m", "d"}), carried={"m": "the quote"})]
    got = mean_cut_loss(runs, family="ranking_stress", arm="x", required={"a": {"m": "the quote"}})
    assert got.value == pytest.approx(0.0)
    assert got.state is Measured.MEASURED


def test_evidence_in_the_pool_and_cut_before_disclosure_is_the_loss_the_metric_is_for() -> None:
    runs = [_run("a", arm="x", pool=frozenset({"m", "d"}), carried={"d": "a distractor"})]
    got = mean_cut_loss(runs, family="ranking_stress", arm="x", required={"a": {"m": "the quote"}})
    assert got.value == pytest.approx(1.0)


def test_a_negative_cut_loss_is_inconclusive_rather_than_a_number() -> None:
    """Disclosed-but-not-in-pool means the pool read is not the pool the answer came from."""
    runs = [_run("a", arm="x", pool=frozenset({"other"}), carried={"m": "the quote"})]
    got = mean_cut_loss(runs, family="ranking_stress", arm="x", required={"a": {"m": "the quote"}})
    assert got.value is None
    assert got.state is Measured.INCONCLUSIVE
    assert "negative" in got.note
