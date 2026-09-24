"""The Orivra MCP surface, and the compatibility claim it is making.

The claim, in one sentence: **`orivra serve` publishes the four `mailweave_*` tools exactly
as `mailweave serve` publishes them, and a call to one of them does exactly what
`mailweave serve` would do.** Every test in the first section is one half of that, executed.

The second section is M1's **level-1 equivalence check**, and it is done in two parts
because one of them is exact and the other cannot be.

**The exact part.** `orivra_ask`'s `gmail` block is the rendering of *the same envelope
object* MailWeave built - not a re-rendering, not a copy, not a payload assembled from it.
That is byte identity with nothing normalised away, and it is a stronger statement than two
runs agreeing, because it holds for every query rather than for the ones a test happens to
run.

**The two-run part, with three families normalised.** Two calls to the same question are
two responses, and three families of field legitimately differ between them: the per-response
fence nonce (and the markers it puts around every piece of mail text), the freshness stamps
taken from the real clock, and the handle payloads that sign both. `normalise` below
substitutes exactly those three and **asserts that it changed something in each**, so a
normaliser that quietly flattened the whole payload would fail rather than pass.

Full byte identity across two runs would need an injected nonce source, and v0.1 exposes one
on `EnvelopeBuilder` but not through `MailweaveService` or `assemble`. Adding that seam is a
change to the frozen v0.1 retrieval path and is recorded as a backlog item rather than made
incidentally here - particularly since the exact part above already establishes the property
the seam would be used to check.

The live half - semantic equivalence over the real mailbox - is M1's level 2 and runs
against the real account, not here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import mcp.types as types
import pytest
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError

from mailweave.envelope.vocab import ToolName
from mailweave.envelope.wire import MessageRow
from mailweave.surface.arguments import SearchRequest
from mailweave.surface.rendering import Rendered, render
from mailweave.surface.server import call as mailweave_call
from mailweave.surface.server import tool_list as mailweave_tool_list
from mailweave.surface.service import MailweaveService
from mailweave.surface.tools import TOOL_SPECS as MAILWEAVE_TOOL_SPECS
from orivra.adapter import AdapterResult
from orivra.budget import m1_budget
from orivra.contracts import ConnectorId, OrivraToolName, SourceState
from orivra.equivalence import normalise
from orivra.gmail_adapter import GmailAdapter
from orivra.registry import ConnectorRegistry
from orivra.surface.projection import DIVIDER
from orivra.surface.server import build_server, call, orivra_handlers, tool_list
from orivra.surface.service import OrivraService
from orivra.surface.tools import PLANNED
from orivra.surface.tools import TOOL_SPECS as ORIVRA_TOOL_SPECS
from tests.fixtures.mailbox import SyntheticMailbox
from tests.test_mcp_surface_round24 import mailbox, make_service

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

#: A fixed query id, so a response is a function of the mailbox and not of a random draw.
FIXED_QUERY_ID = "q-0000000000000000"


@pytest.fixture
def box() -> SyntheticMailbox:
    return mailbox()


@pytest.fixture
def service(box: SyntheticMailbox) -> MailweaveService:
    return make_service(box)


@dataclass(frozen=True)
class RecordingGmailAdapter(GmailAdapter):
    """The real adapter, plus a note of what it handed back.

    A spy rather than a second call, because the property under test is that the `gmail`
    block **is the rendering of the envelope this very call produced**. Two calls would
    produce two envelopes with two fence nonces and two freshness stamps, and comparing
    those would test the normaliser rather than the composition.
    """

    recorded: list[AdapterResult] = field(default_factory=list)

    def answer(self, request: SearchRequest, *, host_chars: int | None = None) -> AdapterResult:
        result = super().answer(request, host_chars=host_chars)
        self.recorded.append(result)
        return result


@pytest.fixture
def adapter(service: MailweaveService) -> RecordingGmailAdapter:
    return RecordingGmailAdapter(service=service, granted_scopes=(SCOPE,))


@pytest.fixture
def orivra(adapter: RecordingGmailAdapter) -> OrivraService:
    return OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}),
        budget=m1_budget(),
        mint_query_id=lambda: FIXED_QUERY_ID,
    )


def structured_of(result: types.CallToolResult) -> dict[str, Any]:
    payload = result.structured_content
    assert isinstance(payload, dict)
    return payload


#: `normalise` is `orivra.equivalence`'s, imported rather than written here.
#:
#: One implementation, used by this offline check and by the live level-2 run. Two would be
#: two definitions of "what may legitimately differ", and the one that drifted would be
#: whichever the live run used - the one nobody exercises until the day it has to be
#: trusted.

# -- "unchanged" is a claim with a mechanism behind it -----------------------------------


def test_the_four_mailweave_tools_are_published_byte_for_byte_as_mailweave_publishes_them() -> None:
    """Not "equivalently": the same `types.Tool` values, because they come from MailWeave's
    own `as_tool` over MailWeave's own specs."""
    ours = {tool.name: tool for tool in tool_list().tools}
    theirs = {tool.name: tool for tool in mailweave_tool_list().tools}
    assert set(theirs) <= set(ours)
    for name, tool in theirs.items():
        assert ours[name].model_dump() == tool.model_dump()


def test_mailweave_tools_gain_no_output_schema_on_this_surface() -> None:
    """Adding a field to the published v0.1 surface is exactly the silent divergence the
    compatibility claim is about."""
    published = {tool.name: tool for tool in tool_list().tools}
    for spec in MAILWEAVE_TOOL_SPECS:
        assert published[spec.name.value].output_schema is None


def test_a_call_to_a_mailweave_tool_is_the_same_function_mailweave_serve_runs(
    orivra: OrivraService, service: MailweaveService
) -> None:
    """Routed, not re-implemented. The two responses differ only in the three volatile
    families, which is what two runs of one function differ in."""
    arguments = {"query": "vendor"}
    through = structured_of(call(orivra, ToolName.SEARCH.value, arguments))
    direct = structured_of(mailweave_call(service, ToolName.SEARCH.value, arguments))
    assert normalise(through) == normalise(direct)


def test_every_orivra_tool_is_annotated_read_only_and_the_annotation_is_true() -> None:
    for tool in tool_list().tools:
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.idempotent_hint is True
        assert tool.annotations.open_world_hint is False


def test_every_published_tool_has_a_title_and_a_name_the_protocol_accepts() -> None:
    for tool in tool_list().tools:
        assert tool.title
        assert 0 < len(tool.name) <= 64


def test_orivras_own_tools_publish_an_output_schema() -> None:
    published = {tool.name: tool for tool in tool_list().tools}
    for spec in ORIVRA_TOOL_SPECS:
        schema = published[spec.name.value].output_schema
        assert isinstance(schema, dict)
        assert schema["type"] == "object"
        assert schema["required"]


def test_the_planned_tools_are_not_published() -> None:
    """A tool a client can see and this server cannot run is a promise the next call
    breaks."""
    published = {tool.name for tool in tool_list().tools}
    assert PLANNED
    for planned in PLANNED:
        assert planned.value not in published


def test_the_dispatch_table_and_the_declared_surface_agree(orivra: OrivraService) -> None:
    table = orivra_handlers(orivra)
    assert set(table) == {spec.name.value for spec in ORIVRA_TOOL_SPECS}


def test_an_unknown_tool_names_the_whole_surface(orivra: OrivraService) -> None:
    from mcp.shared.exceptions import MCPError

    with pytest.raises(MCPError) as refusal:
        call(orivra, "orivra_send_mail", {})
    assert ToolName.SEARCH.value in str(refusal.value)
    assert OrivraToolName.ASK.value in str(refusal.value)


def test_the_server_builds_and_declares_six_tools(orivra: OrivraService) -> None:
    server = build_server(orivra)
    assert server.name == "orivra"
    assert len(tool_list().tools) == len(MAILWEAVE_TOOL_SPECS) + len(ORIVRA_TOOL_SPECS)


# -- level 1: byte identity, where it is meaningful ---------------------------------------


def test_the_gmail_container_is_byte_identical_to_mailweave_search(
    orivra: OrivraService, adapter: RecordingGmailAdapter
) -> None:
    """M1's level-1 equivalence check, in its exact form.

    `gmail` is the rendering of **the same envelope object** MailWeave built for this
    question - not a re-rendering and not a payload assembled from it - so this is byte
    identity with nothing normalised away. A future change that made the adapter build its
    own response, add a field, reorder a block or re-measure anything would fail here first.
    """
    arguments = {"query": "vendor", "view": "snippet"}
    payload = structured_of(call(orivra, OrivraToolName.ASK.value, arguments))
    assert len(adapter.recorded) == 1, "the ask did not reach the Gmail adapter exactly once"
    envelope = adapter.recorded[0].envelope
    assert envelope is not None
    assert json.dumps(payload["gmail"], sort_keys=True) == json.dumps(
        render(envelope).structured, sort_keys=True
    )


def test_two_runs_of_one_question_agree_once_the_volatile_families_are_normalised(
    orivra: OrivraService,
) -> None:
    """The two-run half. Three families differ between any two correct responses, and
    `normalise` substitutes exactly those three - and asserts it touched each, so a
    normaliser that flattened everything would fail rather than pass."""
    arguments = {"query": "vendor", "view": "snippet"}
    through = structured_of(call(orivra, OrivraToolName.ASK.value, arguments))["gmail"]
    direct = structured_of(call(orivra, ToolName.SEARCH.value, arguments))
    assert through != direct, "two responses that were already identical prove nothing here"
    assert normalise(through) == normalise(direct)


def test_the_normaliser_substitutes_the_three_families_and_nothing_else(
    orivra: OrivraService,
) -> None:
    """The normaliser is the load-bearing part of the test above, so it is itself tested.

    A normaliser that erased a field the two paths could differ in would turn a real
    divergence into a pass, which is the failure mode of every "compare after cleaning"
    test ever written.
    """
    payload = structured_of(
        call(orivra, ToolName.SEARCH.value, {"query": "vendor", "view": "snippet"})
    )
    cleaned = normalise(payload)
    assert cleaned["fence_nonce"] == "<nonce>"
    assert payload["fence_nonce"] != "<nonce>"
    # Everything that is not one of the three families survives untouched.
    assert cleaned["retrieval_report"] == payload["retrieval_report"]
    assert cleaned["partial"] == payload["partial"]
    assert [source["thread_id"] for source in cleaned["sources"]] == [
        source["thread_id"] for source in payload["sources"]
    ]


def test_mailweaves_own_mirror_is_carried_unchanged_below_the_divider(
    orivra: OrivraService, adapter: RecordingGmailAdapter
) -> None:
    """The container's text is **not re-composed**, and now it is not the whole block either.

    Every line of MailWeave's mirror is a record MailWeave wrote, and a line this module wrote
    inside that block would be a second voice in it. So Orivra's own lines go *above* a
    divider and the mirror below it is byte-identical to `render(envelope).text`.

    The block above the divider is the reason this changed. A real Claude Desktop run reached a
    cited answer and could not use the graph, because `orivra_graph` and `orivra_expand`
    returned empty text and that client reads text content. A tool whose text says nothing is
    a tool a text-only client cannot navigate with.
    """
    through = call(orivra, OrivraToolName.ASK.value, {"query": "vendor", "view": "snippet"})
    envelope = adapter.recorded[0].envelope
    assert envelope is not None
    text = through.content[0].text  # type: ignore[union-attr]

    head, divider, mirror = text.partition(DIVIDER)
    assert divider == DIVIDER, "the container's text is no longer separable from Orivra's own"
    assert mirror.lstrip("\n") == render(envelope).text, (
        "MailWeave's mirror was re-composed rather than carried"
    )
    # And Orivra's own half is navigable: the id to carry, and the call that takes it.
    assert "query_id=" in head
    assert "orivra_graph {" in head


def test_orivra_ask_returns_the_gmail_container_and_an_account_of_it(
    orivra: OrivraService,
) -> None:
    payload = structured_of(call(orivra, OrivraToolName.ASK.value, {"query": "vendor"}))
    assert payload["query_id"] == FIXED_QUERY_ID
    assert "gmail" in payload
    assert payload["per_source"]
    assert payload["budget"]["stages"]


def test_content_is_fenced_and_labelled(orivra: OrivraService) -> None:
    """The claim in the tool description, executed: the fence and the trust label are
    MailWeave's, and they survive being carried."""
    payload = structured_of(
        call(orivra, OrivraToolName.ASK.value, {"query": "vendor", "view": "snippet"})
    )
    gmail = payload["gmail"]
    assert gmail["fence_nonce"]
    rows = [row for source in gmail["sources"] for row in source["messages"]]
    bodied = [row for row in rows if row.get("content")]
    assert bodied, "no row carried content, so this test proves nothing"
    for row in bodied:
        assert row["content"]["trust"].startswith("untrusted")


# -- what Orivra adds ----------------------------------------------------------------------


def test_per_source_names_every_connector_including_absent_ones(
    orivra: OrivraService,
) -> None:
    """ "Drive is not configured" and "Drive returned nothing" are different answers to
    "what did you look at?"."""
    payload = structured_of(call(orivra, OrivraToolName.ASK.value, {"query": "vendor"}))
    named = {row["connector"] for row in payload["per_source"]}
    assert named == {connector.value for connector in ConnectorId}
    by_connector = {row["connector"]: row for row in payload["per_source"]}
    assert by_connector["gmail"]["state"] == SourceState.READY.value
    assert by_connector["drive"]["state"] == SourceState.NOT_CONFIGURED.value
    assert by_connector["drive"]["detail"]


def test_the_declared_budget_binds_nothing_and_says_so(orivra: OrivraService) -> None:
    payload = structured_of(call(orivra, OrivraToolName.ASK.value, {"query": "vendor"}))
    stages = payload["budget"]["stages"]
    assert stages
    for stage in stages:
        assert stage["limit_ms"] is None
        assert stage["unmeasured_because"]


def test_naming_a_source_this_installation_lacks_is_not_an_error(
    orivra: OrivraService,
) -> None:
    """A caller who names Drive is entitled to learn Drive is not configured, rather than
    to have their whole question refused."""
    payload = structured_of(
        call(orivra, OrivraToolName.ASK.value, {"query": "vendor", "sources": ["drive"]})
    )
    by_connector = {row["connector"]: row for row in payload["per_source"]}
    assert by_connector["drive"]["state"] == SourceState.NOT_CONFIGURED.value
    assert "gmail" not in payload


def test_an_unknown_source_name_is_a_protocol_error(orivra: OrivraService) -> None:
    from mcp.shared.exceptions import MCPError

    with pytest.raises(MCPError, match="unknown source"):
        call(orivra, OrivraToolName.ASK.value, {"query": "vendor", "sources": ["outlook"]})


def test_orivra_sources_makes_no_request_to_any_source(orivra: OrivraService) -> None:
    """The states come from the registry, built at startup, and the capabilities are
    declared. The offline suite's socket block is what proves "no request" here."""
    payload = structured_of(call(orivra, OrivraToolName.SOURCES.value, {}))
    rows = {row["connector"]: row for row in payload["sources"]}
    assert set(rows) == {connector.value for connector in ConnectorId}
    assert rows["gmail"]["capabilities"]["container_kind"] == "thread"
    assert rows["drive"]["capabilities"] is None


def test_orivra_sources_takes_no_arguments(orivra: OrivraService) -> None:
    from mcp.shared.exceptions import MCPError

    with pytest.raises(MCPError, match="takes no arguments"):
        call(orivra, OrivraToolName.SOURCES.value, {"connector": "gmail"})


def test_the_sources_text_writes_one_record_per_line(orivra: OrivraService) -> None:
    """One line per source, every line one record.

    The discipline the MailWeave mirror lives by: a value carrying a line break would write a
    second record in this server's voice. The states and details are server-authored constants
    and nothing mail-derived reaches this projection at all.
    """
    result = call(orivra, OrivraToolName.SOURCES.value, {})
    text = result.content[0].text  # type: ignore[union-attr]
    lines = [line for line in text.splitlines() if line]
    # One header line naming the tool, then one line per connector.
    assert lines[0] == "orivra_sources"
    assert len(lines) == len(ConnectorId) + 1


def test_a_registry_with_no_gmail_adapter_declines_with_the_remedy() -> None:
    empty = OrivraService(registry=ConnectorRegistry(adapters={}))
    result = call(empty, OrivraToolName.ASK.value, {"query": "vendor"})
    assert result.is_error is True
    assert "mailweave auth login" in json.dumps(result.structured_content)


def test_orivra_uses_mailweaves_own_argument_parser(orivra: OrivraService) -> None:
    """A second parser would apply its own defaults, and two responses that differ because
    their defaults differ would fail an equivalence test for a reason that has nothing to do
    with retrieval."""
    from mcp.shared.exceptions import MCPError

    with pytest.raises(MCPError, match="unknown"):
        call(orivra, OrivraToolName.ASK.value, {"query": "vendor", "nonsense": 1})


# -- the error partition, which used to be three clauses of ten (R-M1-001, R-M1-002) -------
#
# `orivra_ask` runs MailWeave's engine, so every condition MailWeave's own `call()` partitions
# is reachable on this path. It caught three of them, and the seven that escaped included a
# `pydantic.ValidationError` whose report quotes the input it refused - which here is a
# response built out of mail (R-SEC-043). The fix is one partition, not two: MailWeave's
# `in_band` is now a function and both surfaces call it.


def _raising(service: OrivraService, exception: BaseException) -> OrivraService:
    """`service`, with `ask` replaced by one that raises. Frozen, so set past the freeze."""
    stub = OrivraService(registry=service.registry, budget=service.budget)

    def blow_up(_raw: Mapping[str, Any]) -> Rendered:
        raise exception

    object.__setattr__(stub, "ask", blow_up)
    return stub


#: A ValidationError built from a value that looks like mail, so a test can ask whether the
#: value reached the wire rather than whether an exception was caught.
def _validation_error_carrying(value: str) -> ValidationError:
    try:
        MessageRow.model_validate({"id": "m1", "position": value})
    except ValidationError as refused:
        assert value in str(refused), "this probe must carry its value, or it tests nothing"
        return refused
    raise AssertionError("the model accepted a position that is not an integer")


def test_orivra_uses_mailweaves_partition_rather_than_a_second_one() -> None:
    """One partition, so the two surfaces cannot drift the way they had."""
    import orivra.surface.server as orivra_server
    from mailweave.surface.server import in_band

    assert orivra_server.in_band is in_band


def test_a_gmail_fault_on_the_orivra_path_is_declared_not_an_internal_error(
    orivra: OrivraService,
) -> None:
    from mailweave.gmail.faults import GmailAuthExpired
    from mailweave.gmail.rates import GmailEndpoint

    stub = _raising(
        orivra,
        GmailAuthExpired(
            "the grant is gone; run `mailweave auth login`",
            endpoint=GmailEndpoint.MESSAGES_LIST,
            status=401,
        ),
    )
    result = call(stub, OrivraToolName.ASK.value, {"query": "vendor"})
    assert result.is_error is True
    assert "mailweave auth login" in json.dumps(result.structured_content)


def test_an_exhausted_disclosure_ladder_on_the_orivra_path_offers_a_narrower_call(
    orivra: OrivraService,
) -> None:
    from mailweave.disclosure.ladder import DisclosureLadderExhausted

    stub = _raising(orivra, DisclosureLadderExhausted("every arrangement carries no mail"))
    result = call(stub, OrivraToolName.ASK.value, {"query": "vendor"})
    assert result.is_error is True
    assert "budget_exhausted" in json.dumps(result.structured_content)


def test_our_own_model_refusing_our_own_output_does_not_render_the_mail_it_refused(
    orivra: OrivraService,
) -> None:
    """R-SEC-043, on a surface that did not exist when R-SEC-043 was closed.

    Pydantic's report quotes the input it refused. On this path that input is a response
    built out of mail, so the error is chained and never rendered - which is the rule
    MailWeave's own clause states and which Orivra inherits by using the same partition.
    """
    secret = "SECRET BODY TEXT ada@acme.example"
    stub = _raising(orivra, _validation_error_carrying(secret))
    with pytest.raises(MCPError) as refusal:
        call(stub, OrivraToolName.ASK.value, {"query": "vendor"})
    assert secret not in str(refusal.value)
    assert "defect in this server" in str(refusal.value)


def test_a_fence_violation_on_the_orivra_path_is_a_declared_internal_failure(
    orivra: OrivraService,
) -> None:
    from mailweave.envelope.fence import FenceViolation

    stub = _raising(orivra, FenceViolation("text collided with the nonce"))
    with pytest.raises(MCPError, match="fence nonce"):
        call(stub, OrivraToolName.ASK.value, {"query": "vendor"})


def test_a_missing_adapter_is_its_own_condition_and_not_every_lookup_error(
    orivra: OrivraService,
) -> None:
    """R-M1-002. `except LookupError` caught every KeyError and IndexError inside a handler
    and reported it as a credential problem with the exception string as the remedy."""
    from orivra.registry import ConnectorUnavailable

    assert not issubclass(ConnectorUnavailable, LookupError)
    leaky = "gmail/thread/18f3ab77c9e1 - Q3 pricing draft from ada@acme.example"
    stub = _raising(orivra, KeyError(leaky))
    with pytest.raises(KeyError):
        call(stub, OrivraToolName.ASK.value, {"query": "vendor"})

    empty = OrivraService(registry=ConnectorRegistry(adapters={}), budget=m1_budget())
    declined_result = call(empty, OrivraToolName.ASK.value, {"query": "vendor"})
    assert declined_result.is_error is True
    rendered = json.dumps(declined_result.structured_content)
    assert "mailweave auth login" in rendered
    assert leaky not in rendered


def test_the_orivra_path_partitions_every_condition_the_legacy_path_does() -> None:
    """The count, pinned. Three of ten was the defect; a future clause added to one surface
    and not the other is the same defect returning, and this is what would catch it."""
    import ast
    import inspect

    from mailweave.surface.server import _partitioned, in_band

    # `in_band` wraps the partition with the lifecycle diagnostic (2026-09-21); the clauses
    # live in `_partitioned`, and `in_band` is asserted to be the one caller of it so the
    # count below is still the count of the partition both surfaces pass through.
    wrapper = inspect.getsource(in_band)
    assert "_partitioned(name, arguments, produce)" in wrapper
    tree = ast.parse(inspect.getsource(_partitioned))
    handlers = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and node.type is not None
    ]
    caught: set[str] = set()
    for handler in handlers:
        target = handler.type
        names = target.elts if isinstance(target, ast.Tuple) else [target]
        for one in names:
            assert isinstance(one, ast.Name)
            caught.add(one.id)
    assert caught == {
        "ToolRefused",
        "HandleRefused",
        "ArgumentInvalid",
        "GmailFault",
        "ConsentFailed",
        "TokenStoreError",
        "DisclosureLadderExhausted",
        "ValidationError",
        "HostCapExceeded",
        "MirrorLineBreak",
        "FenceViolation",
    }, sorted(caught)


# -- the correction pass: the published surface and the runner ------------------------------


def test_the_published_input_schema_and_the_parser_agree(orivra: OrivraService) -> None:
    """R-M1-010. The hand-written schema published four `view` values where the parser
    accepts two, and `additionalProperties: false` while the parser honours seven other
    argument blocks - so a strict client refused calls the server accepts and the server
    accepted calls the schema forbids, in both directions at once.
    """
    import jsonschema

    from mailweave.surface.arguments import parse_search
    from mailweave.surface.tools import SPEC_BY_NAME
    from orivra.surface.tools import ASK

    schema = dict(ASK.input_schema)
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)

    accepted: list[dict[str, Any]] = [
        {"query": "vendor"},
        {"query": "vendor", "view": "snippet"},
        {"query": "vendor", "budget": {"max_quota_units": 50}},
        {"query": "vendor", "scan": {"max_pages": 1}},
        {"query": "vendor", "sources": ["gmail"]},
    ]
    for arguments in accepted:
        validator.validate(dict(arguments))
        parse_search({k: v for k, v in arguments.items() if k != "sources"})

    # Everything MailWeave publishes, Orivra publishes, and nothing more but `sources`.
    inherited = dict(SPEC_BY_NAME[ToolName.SEARCH].input_schema)["properties"]
    assert isinstance(inherited, dict)
    published = schema["properties"]
    assert isinstance(published, dict)
    assert set(published) == set(inherited) | {"sources"}
    for key, value in inherited.items():
        assert published[key] == value


def test_a_view_the_schema_publishes_is_a_view_the_parser_accepts() -> None:
    """The specific half of the above that was wrong in the visible direction."""
    import jsonschema

    from mailweave.surface.arguments import ArgumentInvalid, parse_search
    from orivra.surface.tools import ASK

    schema = dict(ASK.input_schema)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    view = properties["view"]
    assert isinstance(view, dict)
    for value in view["enum"]:
        jsonschema.Draft202012Validator(schema).validate({"query": "q", "view": value})
        try:
            parse_search({"query": "q", "view": value})
        except ArgumentInvalid as refused:  # pragma: no cover - the point is that it does not
            raise AssertionError(
                f"the schema publishes view={value!r} and the parser refuses it: {refused}"
            ) from refused


def test_a_source_that_was_not_asked_says_so_in_a_field_not_in_prose(
    orivra: OrivraService,
) -> None:
    """R-M1-018. A connected source this call did not ask for was reported `ready` with
    `hits: 0`, distinguished from "searched and found nothing" only by free prose."""
    payload = structured_of(
        call(orivra, OrivraToolName.ASK.value, {"query": "vendor", "sources": ["drive"]})
    )
    rows = {row["connector"]: row for row in payload["per_source"]}
    assert rows["gmail"]["asked"] is False
    asked = structured_of(call(orivra, OrivraToolName.ASK.value, {"query": "vendor"}))
    assert {row["connector"]: row for row in asked["per_source"]}["gmail"]["asked"] is True


def test_the_live_runner_calls_a_missing_container_a_divergence(
    orivra: OrivraService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-M1-007. This returned an empty `Comparison`, which reads as equivalent - so the
    record that is M1's own evidence reported success for a query where one path answered and
    the other declined."""
    from orivra import __main__ as runner

    def no_container(service: object, name: str, arguments: Mapping[str, Any]) -> Any:
        if name == OrivraToolName.ASK.value:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text="declined")],
                structured_content={"query_id": "q", "per_source": [], "budget": {}},
                is_error=True,
            )
        return call(orivra, name, arguments)

    monkeypatch.setattr(runner, "call", no_container)
    comparison, facts = runner.run_one(orivra, "vendor", view="snippet")
    assert not comparison.equivalent
    assert facts["equivalent"] is False
    assert "DIVERGED" in comparison.render()


# -- the room seam, and what stops it reaching the legacy path ----------------------------------


def test_the_room_argument_can_only_ever_lower_the_cap() -> None:
    """`host_chars` is room, not policy, and a caller cannot use it to buy more.

    This is the one lever Orivra has over how MailWeave builds a response, and the whole
    safety of it rests on the direction it runs in. A value above the published cap has to be
    ignored rather than honoured: the cap is the host's, and a server that let a caller raise
    it would hand the host a result it will cut where nothing can declare the cut.
    """
    from mailweave.constants import HOST_RESULT_CHAR_CAP
    from mailweave.disclosure.ladder import Ceilings
    from mailweave.surface.service import _with_room

    published = Ceilings(host_chars=HOST_RESULT_CHAR_CAP)
    assert _with_room(published, None) == published, "the legacy path's ceilings moved"
    assert _with_room(published, HOST_RESULT_CHAR_CAP * 2).host_chars == HOST_RESULT_CHAR_CAP
    assert _with_room(published, 9_000).host_chars == 9_000
    # The token ceilings are AD D.4's policy figures; how much room one response was given
    # says nothing about them, so they must be untouched either way.
    narrowed = _with_room(published, 9_000)
    assert (narrowed.normal, narrowed.overflow) == (published.normal, published.overflow)
    with pytest.raises(ValueError, match="no room"):
        _with_room(published, 0)


def test_no_mailweave_path_passes_the_room_argument() -> None:
    """The legacy wire contract is unchanged because nothing on it reaches this argument.

    Asserted against the source rather than against behaviour, because the behavioural test
    above it - the container rendering byte-for-byte what `mailweave_search` renders - would
    also pass if *both* sides started passing a room, and that is exactly the change this is
    here to catch. A `search(` call anywhere under `mailweave/` that names `host_chars` is a
    legacy path being fitted to somebody else's allocation.
    """
    import ast
    from pathlib import Path

    server = Path(__file__).resolve().parents[1] / "server" / "src" / "mailweave"
    offenders: list[str] = []
    for path in server.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            named = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if named != "search":
                continue
            if any(keyword.arg == "host_chars" for keyword in node.keywords):
                offenders.append(f"{path.relative_to(server)}:{node.lineno}")
    assert not offenders, (
        f"a mailweave path passes host_chars, so it is no longer fitted to SERVED_CEILINGS: "
        f"{offenders}"
    )
