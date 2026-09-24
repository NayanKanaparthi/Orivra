"""The wire form of the envelope (AD D.2).

Two properties: the JSON carries the field names the schema sketch names, and the proof
object that made the envelope constructible is not part of the payload.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from mailweave.envelope import (
    Affordance,
    Depth,
    DispositionLedger,
    EnvelopeBuilder,
    Outcome,
    Role,
    RungId,
    Sufficiency,
    ToolName,
    WithheldCap,
)
from mailweave.envelope.response import Envelope
from tests.fixtures import envelope_kit as kit


def built_envelope() -> Envelope:
    ledger = DispositionLedger()
    ledger.record_list_page(
        kit.fetched(
            ["m1", "m2", "m3"],
            more_pages=True,
            thread_ids={"m1": "t1", "m2": "t1", "m3": "t2"},
        ),
        rung=RungId.L1,
        query="from:amy launch after:2026/05/01",
        affordance=Affordance(tool=ToolName.SEARCH, args={"scan": {"max_pages": 3}}),
    )
    ledger.note_withheld(
        message_id="m3",
        cap=WithheldCap.MAX_HIT_THREADS,
        why="31 hit-bearing threads; 12 mapped",
        affordance=kit.thread_affordance("t2"),
    )
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    nonce = builder.fence_nonce
    builder.add_source(
        kit.source(
            "t1",
            [
                kit.row("m1", "t1", 0, nonce=nonce),
                kit.row("m2", "t1", 1, nonce=nonce, depth=Depth.STUB, role=Role.STUB),
            ],
            stated_total=7,
        )
    )
    builder.add_affordance(kit.thread_affordance("t1"))
    return builder.build(
        outcome=Outcome.INCONCLUSIVE,
        rungs=(RungId.L0, RungId.L1),
        sufficiency=Sufficiency.AMBIGUOUS,
        counters=kit.counters(),
        empty_diagnosis=kit.empty_diagnosis_complete(),
    )


def test_the_wire_form_carries_the_documented_top_level_fields() -> None:
    payload = json.loads(built_envelope().model_dump_json())
    assert {
        "schema_version",
        "fence_nonce",
        "asked_for",
        "sources",
        "not_included_sources",
        "partial",
        "affordances",
        "retrieval_report",
        "withheld",
        "ceiling",
        "errors",
        "budget",
        "truncated_by",
    } <= set(payload)
    assert payload["schema_version"] == 2


def test_the_disposition_proof_is_not_part_of_the_payload() -> None:
    payload = json.loads(built_envelope().model_dump_json())
    assert "disposition" not in payload
    assert "certificate" not in json.dumps(payload)


def test_the_withheld_record_carries_its_cap_reason_and_executable_call() -> None:
    payload = json.loads(built_envelope().model_dump_json())
    record = payload["withheld"][0]
    assert set(record) == {"id", "thread_id", "cap", "why", "affordance"}
    assert record["affordance"]["tool"] == "mailweave_thread_map"
    assert record["affordance"]["args"]["thread_id"] == record["thread_id"]


def test_the_report_carries_the_scan_scope_the_ledger_accumulated() -> None:
    """The response's account of what it scanned comes from the ledger, not from the caller."""
    payload = json.loads(built_envelope().model_dump_json())
    scan = payload["retrieval_report"]["scan_scope"]
    assert len(scan) == 1
    assert scan[0]["ids_returned"] == 3
    assert scan[0]["more_pages"] is True
    assert scan[0]["affordance"]["args"]["scan"]["max_pages"] == 3


def test_an_envelope_cannot_be_constructed_without_a_disposition_certificate() -> None:
    with pytest.raises(ValidationError):
        Envelope(  # type: ignore[call-arg]
            fence_nonce="mw-deadbeef",
            asked_for=kit.asked_for(),
            partial=False,
            retrieval_report=built_envelope().retrieval_report,
            ceiling=built_envelope().ceiling,
        )


def test_stub_rows_and_body_rows_declare_their_depth_on_the_wire() -> None:
    payload = json.loads(built_envelope().model_dump_json())
    depths = {row["id"]: row["depth"] for row in payload["sources"][0]["messages"]}
    assert depths == {"m1": "body_clean", "m2": "stub"}
    roles = {row["id"]: row["role"] for row in payload["sources"][0]["messages"]}
    assert set(roles.values()) <= {
        "matched",
        "context",
        "parent",
        "child",
        "requested",
        "stub",
        "derived",
    }
    # AD D.2 carries `reason` as a mechanical string, with the typed form beside it.
    reasons = [row["reason"] for row in payload["sources"][0]["messages"]]
    assert all(isinstance(reason, str) and reason for reason in reasons)
    kinds = {row["reason_detail"]["kind"] for row in payload["sources"][0]["messages"]}
    assert kinds == {"gmail_query_match", "thread_member"}
    assert "from:amy launch" in " ".join(reasons)


def test_the_rendered_reason_is_mechanical_for_every_message() -> None:
    envelope = built_envelope()
    for source in envelope.sources:
        for row in source.messages:
            rendered = row.rendered_reason
            assert rendered and any(
                marker in rendered
                for marker in ("gmail q matched", "thread map row", "reply", "semantic", "rfc822")
            )


# --- R-DISC-003: the partiality signals precede the bulk content on the wire ---------------


#: Fields a reader must reach before `sources`, which is unbounded. `partial` says the
#: response is incomplete, `withheld` says what is missing, `retrieval_report` carries the
#: outcome and the routes not tried.
#: Round 29 adds two: a response whose omissions are written compactly is no less partial,
#: and the counts a client reads instead of parsing prose qualify the content just as the
#: records do, so both sit before it.
PARTIALITY_SIGNALS = (
    "partial",
    "withheld",
    "withheld_groups",
    "withheld_tail",
    "omission",
    "retrieval_report",
)


def test_the_partiality_signals_are_serialised_before_the_bulk_content() -> None:
    """R-DISC-003: `sources` was third, before every field saying the response is partial.

    A model reading the payload linearly, or a client that renders or truncates
    sequentially, met 60% of the payload's lines before anything told it the answer was
    incomplete. Field order is not a correctness property for a machine that parses the
    whole document; it is one for the reader this response is written for.
    """
    payload = json.loads(built_envelope().model_dump_json())
    order = list(payload)
    assert "sources" in order
    for field in PARTIALITY_SIGNALS:
        assert order.index(field) < order.index("sources"), (
            f"{field} is serialised after the bulk content it qualifies"
        )


def test_a_reader_truncated_mid_payload_has_already_seen_the_partiality_signals() -> None:
    """The failure mode stated at the level it happens: bytes, not parsed keys.

    A client that renders or truncates the response as it arrives never parses a whole
    document. What matters to it is where in the *text* each field sits, so that is what
    is measured here rather than the key order of an already-parsed dict.
    """
    text = built_envelope().model_dump_json()
    content_at = text.index('"sources"')
    for field in PARTIALITY_SIGNALS:
        assert text.index(f'"{field}"') < content_at


def test_the_reordering_did_not_drop_or_rename_a_field() -> None:
    """Reordering is a wire change; this is what keeps it from being a schema change."""
    payload = json.loads(built_envelope().model_dump_json())
    assert set(payload) == {
        "schema_version",
        "fence_nonce",
        "asked_for",
        "partial",
        "withheld",
        "withheld_groups",
        "withheld_tail",
        "omission",
        "retrieval_report",
        "sources",
        "not_included_sources",
        "affordances",
        "continuations",
        "ceiling",
        "errors",
        "budget",
        "truncated_by",
    }
