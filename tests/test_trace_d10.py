"""D.10 executed: redaction as a type, the policy as a field, and `pool_ids` in one place.

**The claim this file is about is a negative one**, which is why it is executed rather than
asserted. "No mail-derived text reaches a trace" cannot be shown by writing one trace and
grepping it: the leak that matters is the one on the path nobody wrote a test for, which is
the error path. So there are two kinds of test here.

  * *Type-level.* A walk of the whole `PersonalTrace` model tree that refuses any field
    whose type could hold a free string, with the exceptions named one at a time and each
    one argued. This is the test that a field added next round has to pass.
  * *Canary.* A sentinel seeded into the query and into the mailbox, a real served call, and
    a grep of what was actually written - including through a forced exception's `repr`.
"""

from __future__ import annotations

import json
import types
import typing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from mailweave.envelope.reasons import RungId
from mailweave.envelope.vocab import BudgetCapName
from mailweave.gmail import BackoffPolicy, CallMeter, GmailClient, StaticToken
from mailweave.handles.cache import ThreadMapCache
from mailweave.handles.keys import HandleKey
from mailweave.net.egress import build_client
from mailweave.surface.arguments import parse_search
from mailweave.surface.service import MailweaveService
from mailweave.trace.redaction import Redacted, RedactionPolicy, query_features
from mailweave.trace.schema import TRACE_SCHEMA_VERSION, PersonalTrace
from mailweave.trace.sink import TraceRefused, TraceSink, new_trace_id
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms

TOKEN = "ya29.SECRET-ACCESS-TOKEN-NEVER-IN-A-TRACE-FIXTURE"
ACCOUNT = "sha256:0f1e2d3c4b5a69788796a5b4c3d2e1f0"
SENTINEL = "zqxjkbwv"


# --- the type-level claim ---------------------------------------------------------------


#: Field types a trace may carry, and why each one cannot hold mail text.
_CLOSED: tuple[object, ...] = (int, bool, float, RungId, BudgetCapName, RedactionPolicy)

#: `str` fields that are permitted, each with the reason it is not mail-derived. A `str`
#: field absent from here fails the sweep - which is the point: a new one has to be argued.
_PERMITTED_STRINGS: dict[str, str] = {
    "trace_id": "a random uuid this process minted; encodes nothing about the query",
    "tool": "one of four compile-time tool names (AD D.1)",
    "hash": "a salted short digest of the query, which is what replaces the query text",
    "query_hash": "a salted short digest of an executed q, for the same reason",
    "pool_scope_hash": "a salted short digest of the pool's scope sentence",
    "quota_units_label": "a constant string this module owns",
    "watermark_source": "one of two words this module chooses between",
    "history_id": "a Gmail synchronisation stamp: an unsigned integer as a string",
    "sufficiency_verdict": "a closed A.8 vocabulary value",
    "answer_class": "a closed A.8b vocabulary value",
    "fallback_reason": "a `NotTriedWhy` value, which is a closed vocabulary",
    "diagnose_finding": "a finding id the operator passed on the command line (AD A.3)",
    "eval_join": "an evaluation-harness key, never mail-derived",
    "code": "a closed D.11 error code",
    "exception": "an exception class name: a fact about the program",
    "id": "an opaque Gmail message id; A.11's type policy persists ids by default",
    "cap": "a closed `WithheldCap` value",
    "role": "a closed contract R-02 role value",
    "reason_kind": "a closed `ReasonKind` value - never the rendered sentence",
    "depth": "a closed contract R-04 depth value",
    "rule": "the shortlist's pre-registered rule, a constant this server owns",
    "branch": "one of A.8a's three branch names",
    "model_id": "a model identifier from the pinned catalogue",
    "model_revision": "a pinned git revision",
    # Tuple and mapping members reach this sweep by their element type, so these are argued
    # here for the same reason the scalars are.
    "constraints_dropped": (
        "`Constraint.name` values - `from`, `terms` - which the parser assigns from a fixed "
        "vocabulary. The token the user wrote lives beside it in the response's `dropped` "
        "block and does not come here"
    ),
    "api_calls_by_method": "Gmail method names, keyed; the values are counts",
    "hit_count_per_rung": "`RungId` values, keyed; the values are counts",
    "latency_ms_per_rung": "`RungId` values, keyed; the values are milliseconds",
    "pool_ids": (
        "opaque Gmail message ids. A.11's type policy persists ids and metadata by default "
        "and bodies and subjects never; this is the list D.5 puts in the trace and nowhere "
        "else so EV-01 can be joined against a real set"
    ),
}


def _models(
    model: type[BaseModel], seen: set[type[BaseModel]] | None = None
) -> list[type[BaseModel]]:
    seen = set() if seen is None else seen
    if model in seen:
        return []
    seen.add(model)
    found = [model]
    for info in model.model_fields.values():
        for candidate in _unwrap(info.annotation):
            if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                found.extend(_models(candidate, seen))
    return found


def _unwrap(annotation: object) -> list[object]:
    """Every type inside an annotation, however many layers of Optional/tuple/dict deep."""
    origin = typing.get_origin(annotation)
    if origin is None:
        return [annotation]
    if origin in (typing.Union, types.UnionType):
        return [item for arg in typing.get_args(annotation) for item in _unwrap(arg)]
    return [item for arg in typing.get_args(annotation) for item in _unwrap(arg)]


def test_no_trace_field_can_hold_mail_derived_text() -> None:
    """A.11: "The `PersonalTrace` type has *no field* whose type can hold mail-derived text."

    Walked rather than asserted, so a field added to any block of the schema has to appear in
    `_PERMITTED_STRINGS` with a sentence saying why it is not mail text. A filter would have
    to be remembered at every call site; a type has to be argued once, here.
    """
    unexplained: list[str] = []
    for model in _models(PersonalTrace):
        for name, info in model.model_fields.items():
            for candidate in _unwrap(info.annotation):
                if candidate in _CLOSED or candidate is type(None):
                    continue
                if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                    continue
                if isinstance(candidate, str):
                    # **An unresolved forward reference, and the sweep refuses it.** Pydantic
                    # leaves an annotation as a string when the class it names is defined
                    # later in the module, and a walk that skipped those could be defeated by
                    # moving a block down the file - a whole sub-tree of the schema silently
                    # unchecked. This caught exactly that: `ScanScopeTrace` and
                    # `AnswerTypeTrace` sat below the model referencing them and neither was
                    # being walked.
                    unexplained.append(f"{model.__name__}.{name} (unresolved {candidate!r})")
                    continue
                if candidate is str and name in _PERMITTED_STRINGS:
                    continue
                if candidate is str:
                    unexplained.append(f"{model.__name__}.{name}")
    assert unexplained == [], (
        f"these string fields are not argued in _PERMITTED_STRINGS: {unexplained}. A trace "
        "field that can hold a free string is a field mail text can reach."
    )


def test_the_permitted_string_list_names_only_fields_that_exist() -> None:
    """The other direction: a stale exemption is an argument for a field nobody has."""
    present = {name for model in _models(PersonalTrace) for name in model.model_fields}
    assert set(_PERMITTED_STRINGS) <= present, sorted(set(_PERMITTED_STRINGS) - present)


# --- the redaction type -------------------------------------------------------------------


def test_every_formatting_path_renders_the_placeholder() -> None:
    """Four paths, and the error path is the one SEC-06 is about.

    A filter runs where somebody remembered to call it, and the place mail text reaches a log
    is almost never that place: it is an exception's `repr`, an f-string in an error message,
    a padded field in a log line. All four go through this type.
    """
    value = Redacted(f"the {SENTINEL} slipped to Thursday")
    assert SENTINEL not in str(value)
    assert SENTINEL not in repr(value)
    assert SENTINEL not in f"{value}"
    assert SENTINEL not in f"{value:>40}"
    assert SENTINEL not in repr(ValueError(f"refused: {value}"))
    assert "<redacted:len=" in str(value)


def test_the_placeholder_carries_a_length_and_a_digest_and_nothing_else() -> None:
    value = Redacted("abcdef")
    assert value.placeholder == f"<redacted:len=6:sha8={value.digest}>"
    assert len(value.digest) == 8


def test_the_digest_is_salted_so_it_is_not_a_stable_key_for_a_short_value() -> None:
    """An unsalted eight-hex digest of an address is a rainbow-table key with extra steps."""
    import hashlib

    address = "ana@team.example"
    unsalted = hashlib.sha256(address.encode()).hexdigest()[:8]
    assert Redacted(address).digest != unsalted


def test_two_equal_values_share_a_digest_within_one_process() -> None:
    """The one thing the digest is for: joining two fields without knowing the value."""
    assert Redacted("x").digest == Redacted("x").digest
    assert Redacted("x").digest != Redacted("y").digest


def test_query_features_describe_the_shape_and_never_the_text() -> None:
    features = query_features(f'from:ana@team.example "{SENTINEL} slipped" -draft')
    assert SENTINEL not in json.dumps(features)
    assert features["has_operator"] is True
    assert features["has_phrase"] is True
    assert features["has_negation"] is True


# --- the sink -----------------------------------------------------------------------------


def test_the_sink_refuses_a_record_whose_policy_is_not_its_own(tmp_path: Path) -> None:
    """A file whose contents contradict the directory it is in is worse than either."""
    sink = TraceSink(tmp_path, policy=RedactionPolicy.PERSONAL)
    trace = _minimal_trace(policy=RedactionPolicy.SEED)
    with pytest.raises(TraceRefused, match="seed"):
        sink.write(trace)


def test_a_diagnose_sink_names_the_finding_it_was_opened_for(tmp_path: Path) -> None:
    """AD A.3: an escape hatch with no reason attached is the shape that stops being temporary."""
    with pytest.raises(TraceRefused, match="finding"):
        TraceSink(tmp_path, policy=RedactionPolicy.DIAGNOSE)
    sink = TraceSink(tmp_path, policy=RedactionPolicy.DIAGNOSE, diagnose_finding="R-SEC-099")
    assert sink.directory.name == "R-SEC-099"
    assert "diagnose" in str(sink.directory)


def test_the_trace_file_and_its_directory_are_owner_only(tmp_path: Path) -> None:
    sink = TraceSink(tmp_path)
    sink.write(_minimal_trace())
    assert sink.directory.stat().st_mode & 0o777 == 0o700
    assert sink.path.stat().st_mode & 0o777 == 0o600


def test_records_append_as_jsonl_and_read_back(tmp_path: Path) -> None:
    sink = TraceSink(tmp_path)
    sink.write(_minimal_trace())
    sink.write(_minimal_trace())
    assert len(sink.path.read_text().splitlines()) == 2
    assert len(sink.read_all()) == 2
    assert all(record.schema_version == TRACE_SCHEMA_VERSION for record in sink.read_all())


def _minimal_trace(policy: RedactionPolicy = RedactionPolicy.PERSONAL) -> PersonalTrace:
    from mailweave.trace.schema import (
        CostTrace,
        Disposition,
        QueryFeatures,
        RetrievalOutcome,
        Routing,
    )

    return PersonalTrace(
        trace_id=new_trace_id(),
        redaction=policy,
        tool="mailweave_search",
        query_features=QueryFeatures(**query_features("cutover")),
        routing=Routing(),
        retrieval_outcome=RetrievalOutcome(
            rounds=0, http_requests=0, quota_units=0, term_coverage_final=1.0
        ),
        disposition=Disposition(hit_ids_count=0, disclosed_count=0),
        cost=CostTrace(latency_ms_total=1),
    )


# --- the canary, through a real served call ------------------------------------------------


def test_a_served_call_writes_a_trace_that_holds_no_sentinel(tmp_path: Path) -> None:
    """PF-8's shape, run here rather than only against a real mailbox.

    The sentinel is in the query, the subject and the body. The response carries it - it is
    the answer - and the trace must not, at any depth, including inside the scope rule and
    the executed `q`.
    """
    box = SyntheticMailbox(
        messages=(
            Msg(
                id="s-1",
                thread_id="t-s",
                sender="ana@team.example",
                subject=f"Cutover {SENTINEL}",
                body=f"The {SENTINEL} slipped to Thursday.",
                internal_date_ms=epoch_ms(2026, 8, 1),
                to=("bo@team.example",),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )
    sink = TraceSink(tmp_path)
    service = _service(box, sink=sink, tmp_path=tmp_path)
    envelope = service.search(parse_search({"query": SENTINEL}))

    assert SENTINEL in json.dumps(envelope.model_dump(mode="json")), (
        "the sentinel is meant to be the answer; if the response lost it this proves nothing"
    )
    written = sink.path.read_text()
    assert written, "no trace was written"
    assert SENTINEL not in written
    assert "ana@team.example" not in written, "an address reached a personal-profile trace"
    assert "Cutover" not in written, "a subject reached a personal-profile trace"

    record = sink.read_all()[0]
    assert record.redaction is RedactionPolicy.PERSONAL
    assert record.query_features.hash != SENTINEL


def test_pool_ids_live_in_the_trace_and_never_in_the_response(tmp_path: Path) -> None:
    """AD D.5 / §H-5(b): it is what lets EV-01 join against a real set instead of an account."""
    from tests.test_semantic_rung import counting_registry, measured_profile, paraphrase_mailbox

    box = paraphrase_mailbox()
    sink = TraceSink(tmp_path)
    registry, _built = counting_registry()
    service = _service(
        box, sink=sink, tmp_path=tmp_path, registry=registry, profile=measured_profile()
    )
    envelope = service.search(parse_search({"query": "postpone the launch"}))

    payload = json.dumps(envelope.model_dump(mode="json"))
    assert "pool_ids" not in payload, "the pool's id list reached the wire"

    record = sink.read_all()[0]
    assert record.semantic is not None
    assert record.semantic.pool_ids, "the trace carries no pool ids, so EV-01 joins nothing"
    assert record.semantic.pool_messages == len(record.semantic.pool_ids)


def test_a_trace_that_cannot_be_written_does_not_fail_the_call(tmp_path: Path) -> None:
    """A forensic record of a correct response is not worth failing that response over."""
    box = SyntheticMailbox(
        messages=(
            Msg(
                id="w-1",
                thread_id="t-w",
                sender="ana@team.example",
                subject="Cutover",
                body="soon",
                internal_date_ms=epoch_ms(2026, 8, 1),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")
    service = _service(box, sink=TraceSink(blocked), tmp_path=tmp_path)
    envelope = service.search(parse_search({"query": "cutover"}))
    assert envelope.sources, "the response was lost to a trace that could not be written"


def _service(
    box: SyntheticMailbox,
    *,
    sink: TraceSink,
    tmp_path: Path,
    registry: object | None = None,
    profile: object | None = None,
) -> MailweaveService:
    def open_client() -> GmailClient:
        return GmailClient(
            token=StaticToken(TOKEN),
            http=build_client(inner=box.transport()),
            meter=CallMeter(),
            policy=BackoffPolicy(),
            sleeper=lambda _s: None,
            jitterer=lambda: 0.5,
        )

    extra = {}
    if registry is not None:
        extra["registry"] = registry
    if profile is not None:
        extra["semantic_profile"] = profile
    return MailweaveService(
        open_client=open_client,
        account_hash=ACCOUNT,
        handle_key=HandleKey(material=b"k" * 32, epoch=0),
        cache=ThreadMapCache(),
        now=lambda: datetime.now(UTC),
        watermark_path=tmp_path / "state" / "watermark.json",
        trace_sink=sink,
        **extra,  # type: ignore[arg-type]
    )
