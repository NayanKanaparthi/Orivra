"""M1's compatibility claims, each made falsifiable.

Three claims are on the table and they are not the same claim:

1. **Handle compatibility.** Every recovery call Orivra emits is one the *legacy* MailWeave
   surface accepts and executes. Orivra mints no handles of its own - it carries MailWeave's
   affordances re-labelled - so the claim is checked the only way it can be trusted: parse
   the call with MailWeave's own parser, validate it against the published `inputSchema` with
   a real JSON Schema validator, and then **run it** and look at what comes back.
2. **Level 1 equivalence**, in `test_orivra_surface.py`: the `gmail` block is the rendering of
   the same envelope object MailWeave built.
3. **Level 2 equivalence**, live. The comparison itself lives here and is exercised offline
   against the fixture mailbox, so the function the live run depends on is not first exercised
   on the day of the live run. The live case is marked `network` and is not in the default
   suite.

The plan's instruction for claim 1 was explicit: *if it does not hold, drop the claim rather
than widen the parser.* It holds, and it holds for a stronger reason than the plan
anticipated - Orivra never mints one, so there is nothing for the parser to be widened for.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import jsonschema
import mcp.types as types
import pytest

from mailweave.envelope.vocab import Depth, ToolName
from mailweave.policy.budget import BudgetRequest
from mailweave.surface.arguments import (
    SearchRequest,
    parse_get_attachment,
    parse_get_messages,
    parse_search,
    parse_thread_map,
)
from mailweave.surface.service import MailweaveService
from mailweave.surface.tools import SPEC_BY_NAME
from orivra.adapter import AdapterResult
from orivra.budget import m1_budget
from orivra.contracts import ConnectorId, OrivraToolName
from orivra.equivalence import (
    compare,
    compare_affordances,
    compare_ask,
    offers_of,
    semantic_view,
)
from orivra.gmail_adapter import GmailAdapter
from orivra.registry import ConnectorRegistry
from orivra.surface.server import call
from orivra.surface.service import OrivraService
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.test_mcp_surface_round24 import mailbox, make_service

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

#: A fixture query that really does withhold, so the handle tests have handles to run.
WITHHOLDING = ("note", BudgetRequest(max_hit_threads=1))

_PARSERS = {
    ToolName.SEARCH: parse_search,
    ToolName.THREAD_MAP: parse_thread_map,
    ToolName.GET_MESSAGES: parse_get_messages,
    ToolName.GET_ATTACHMENT: parse_get_attachment,
}


@dataclass(frozen=True)
class RecordingGmailAdapter(GmailAdapter):
    recorded: list[AdapterResult] = field(default_factory=list)

    def answer(self, request: SearchRequest, *, host_chars: int | None = None) -> AdapterResult:
        result = super().answer(request, host_chars=host_chars)
        self.recorded.append(result)
        return result


@pytest.fixture
def box() -> SyntheticMailbox:
    return mailbox()


@pytest.fixture
def service(box: SyntheticMailbox) -> MailweaveService:
    return make_service(box)


@pytest.fixture
def adapter(service: MailweaveService) -> RecordingGmailAdapter:
    return RecordingGmailAdapter(service=service, granted_scopes=(SCOPE,))


@pytest.fixture
def orivra(adapter: RecordingGmailAdapter) -> OrivraService:
    return OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}),
        budget=m1_budget(),
        mint_query_id=lambda: "q-fixed",
    )


def _validator(tool: ToolName) -> jsonschema.Draft202012Validator:
    schema = dict(SPEC_BY_NAME[tool].input_schema)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def structured_of(result: types.CallToolResult) -> dict[str, Any]:
    payload = result.structured_content
    assert isinstance(payload, dict)
    return payload


def _withholding_result(adapter: RecordingGmailAdapter) -> AdapterResult:
    query, budget = WITHHOLDING
    return adapter.answer(
        SearchRequest(
            query=query,
            view=Depth.SNIPPET,
            scan_max_pages=None,
            budget=budget,
            disclosed_token_request=None,
        )
    )


# -- claim 1: handle compatibility ---------------------------------------------------------


def test_orivra_mints_no_handle_of_its_own(adapter: RecordingGmailAdapter) -> None:
    """The strongest form of the compatibility claim: there is nothing to be compatible.

    Every recovery call Orivra emits names one of MailWeave's four tools and carries
    MailWeave's own arguments. A handle Orivra invented would have neither R-07 nor the v0.1
    suite behind it, and the parser would have to be widened for it - which the plan said to
    refuse.
    """
    result = _withholding_result(adapter)
    assert result.omissions, "the chosen fixture query no longer withholds; pick another"
    for record in result.omissions:
        assert record.recover is not None
        assert record.recover.tool.is_mailweave, record.recover.tool


def test_every_orivra_recovery_call_parses_under_mailweaves_own_parser(
    adapter: RecordingGmailAdapter,
) -> None:
    result = _withholding_result(adapter)
    for record in result.omissions:
        assert record.recover is not None
        tool = ToolName(record.recover.tool.value)
        parsed = _PARSERS[tool](record.recover.args)
        assert parsed is not None


def test_every_orivra_recovery_call_validates_against_the_published_input_schema(
    adapter: RecordingGmailAdapter,
) -> None:
    """A real JSON Schema validator, which is what a strict client runs. A call that only
    the server's own parser accepts is a call half the clients will refuse."""
    result = _withholding_result(adapter)
    for record in result.omissions:
        assert record.recover is not None
        _validator(ToolName(record.recover.tool.value)).validate(dict(record.recover.args))


def test_every_orivra_recovery_call_actually_runs_on_the_legacy_surface(
    orivra: OrivraService, adapter: RecordingGmailAdapter
) -> None:
    """Executed, not merely parsed. R-07 is about a call that retrieves something, and a
    call that parses and then declines is a handle that spends the caller's next round."""
    result = _withholding_result(adapter)
    for record in result.omissions:
        assert record.recover is not None
        executed = call(orivra, record.recover.tool.value, dict(record.recover.args))
        assert executed.is_error is False, structured_of(executed)


def test_a_recovery_call_reaches_the_evidence_the_record_named(
    orivra: OrivraService, adapter: RecordingGmailAdapter
) -> None:
    """The recovery contract's substance: following the handle reaches the thing the record
    said was withheld, rather than something else that also parses."""
    result = _withholding_result(adapter)
    container = next(
        record
        for record in result.omissions
        if record.what.startswith("gmail/thread/") and record.recover is not None
    )
    thread_id = container.what.removeprefix("gmail/thread/")
    assert container.recover is not None
    executed = call(orivra, container.recover.tool.value, dict(container.recover.args))
    payload = structured_of(executed)
    assert any(source["thread_id"] == thread_id for source in payload["sources"])


# -- claim 3: the level-2 comparison, exercised offline ------------------------------------


def test_the_semantic_view_keeps_what_level_two_compares_and_drops_what_it_must(
    orivra: OrivraService,
) -> None:
    arguments = {"query": "vendor", "view": "snippet"}
    payload = structured_of(call(orivra, ToolName.SEARCH.value, arguments))
    view = semantic_view(payload)
    assert view["outcome"] == payload["retrieval_report"]["outcome"]
    assert view["partial"] == payload["partial"]
    assert view["evidence_by_depth"], "no evidence survived the view, so it compares nothing"
    # The volatile families are gone, and the identities are not.
    assert "fence_nonce" not in json.dumps(view)
    assert payload["sources"][0]["thread_id"] in json.dumps(view)


def test_the_two_paths_agree_on_the_semantic_view_over_the_fixture_mailbox(
    orivra: OrivraService,
) -> None:
    """The offline rehearsal of level 2. The live run compares the same function's output
    over the real mailbox; exercising it here means the comparison is not first exercised on
    the day it has to be trusted."""
    arguments = {"query": "vendor", "view": "snippet"}
    through = structured_of(call(orivra, OrivraToolName.ASK.value, arguments))["gmail"]
    direct = structured_of(call(orivra, ToolName.SEARCH.value, arguments))
    assert semantic_view(through) == semantic_view(direct)


@pytest.mark.parametrize(
    "query",
    ["vendor", "note", "word1", "orphan"],
)
def test_the_two_paths_agree_across_several_shapes(orivra: OrivraService, query: str) -> None:
    """One query proves the composition works; four prove it is not the one query's shape."""
    arguments = {"query": query, "view": "snippet"}
    through = structured_of(call(orivra, OrivraToolName.ASK.value, arguments))
    direct = structured_of(call(orivra, ToolName.SEARCH.value, arguments))
    if "gmail" not in through:  # pragma: no cover - every fixture query answers today
        pytest.fail("orivra_ask returned no Gmail container for an answerable query")
    assert semantic_view(through["gmail"]) == semantic_view(direct)


def test_a_divergence_in_the_evidence_set_would_be_caught(orivra: OrivraService) -> None:
    """The comparison is only worth running if it can fail. A response with one message
    removed must not compare equal to the response it came from."""
    arguments = {"query": "vendor", "view": "snippet"}
    payload = structured_of(call(orivra, ToolName.SEARCH.value, arguments))
    tampered = json.loads(json.dumps(payload))
    tampered["sources"][0]["messages"] = tampered["sources"][0]["messages"][:-1]
    assert semantic_view(tampered) != semantic_view(payload)


# -- the comparison reports which claim broke, not that "the responses differ" ------------


def test_compare_names_the_field_that_diverged(orivra: OrivraService) -> None:
    arguments = {"query": "vendor", "view": "snippet"}
    payload = structured_of(call(orivra, ToolName.SEARCH.value, arguments))
    tampered = json.loads(json.dumps(payload))
    tampered["partial"] = not tampered["partial"]
    comparison = compare("vendor", tampered, payload)
    assert not comparison.equivalent
    assert [one.field for one in comparison.differences] == ["partial"]
    assert "partial" in comparison.render()


def test_a_payload_with_no_fence_nonce_is_refused_rather_than_normalised() -> None:
    """It is not a MailWeave response, and normalising it would compare something other than
    what was claimed."""
    from orivra.equivalence import normalise

    with pytest.raises(ValueError, match="no fence_nonce"):
        normalise({"sources": []})


def test_the_live_runner_asks_each_query_through_both_surfaces(
    orivra: OrivraService,
) -> None:
    """`python -m orivra` is what produces the live level-2 record. Its per-query step is
    driven here against the fixture mailbox, so the code path the live run depends on is not
    first executed on the day of the live run."""
    from orivra.__main__ import run_one

    comparison, facts = run_one(orivra, "vendor", view="snippet")
    assert comparison.equivalent, comparison.render()
    assert facts["equivalent"] is True
    assert facts["per_source"]
    assert facts["budget_binds"] == [], "no Orivra budget stage is measured at M1"


def test_the_live_runner_reports_a_divergence_rather_than_hiding_it(
    orivra: OrivraService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A runner that only records its successes is not a record."""
    from orivra import __main__ as runner
    from orivra.equivalence import Comparison, Difference

    def diverging(query: str, left: Any, right: Any) -> Comparison:
        return Comparison(
            query=query,
            differences=(Difference(field="outcome", orivra="answered", mailweave="inconclusive"),),
        )

    monkeypatch.setattr(runner, "compare", diverging)
    comparison, facts = runner.run_one(orivra, "vendor", view="snippet")
    assert not comparison.equivalent
    assert facts["equivalent"] is False
    assert facts["differences"] == ["outcome: orivra='answered' mailweave='inconclusive'"]


# -- the closure pass: paired affordances are executed, not listed --------------------------
#
# The plan's level-2 requirement is that following the Orivra affordance and the MailWeave
# affordance reaches the same evidence. The runner recorded the tool NAMES each side offered
# and `equivalence.py` admitted as much in its own docstring - a weaker check than the plan
# asks for, in the one dimension level 2 cannot compare as bytes.


def test_offers_are_gathered_from_every_block_that_carries_one(
    orivra: OrivraService,
) -> None:
    """Affordances, withheld records, groups, tails and collapsed runs all carry one."""
    payload = structured_of(call(orivra, ToolName.SEARCH.value, {"query": "note"}))
    assert (
        payload["withheld_groups"]
        or payload["affordances"]
        or any(source["collapsed_runs"] for source in payload["sources"])
    ), "this query offers nothing, so the gathering proves nothing"
    offers = offers_of(payload)
    assert offers
    assert all(one.tool.startswith("mailweave_") for one in offers)
    assert all(one.subject != "unaddressed" or one.args for one in offers)


def test_offers_are_deterministic_across_two_gatherings(
    orivra: OrivraService,
) -> None:
    """Pairing is only deterministic if the lists are."""
    payload = structured_of(call(orivra, ToolName.SEARCH.value, {"query": "note"}))
    first = [one.key for one in offers_of(payload)]
    second = [one.key for one in offers_of(payload)]
    assert first == second == sorted(first)


def test_a_subject_never_pairs_on_a_signed_handle(orivra: OrivraService) -> None:
    """`map_id` differs between two correct responses, so pairing on it would pair nothing -
    and would put a signature into a record that must carry none."""
    payload = structured_of(call(orivra, ToolName.SEARCH.value, {"query": "note"}))
    for offer in offers_of(payload):
        assert "map_id" not in offer.subject


def test_paired_affordances_are_executed_and_reach_the_same_evidence(
    orivra: OrivraService,
) -> None:
    """The requirement itself. Both sides' offers are run and compared by what they recover."""
    arguments = {"query": "note", "view": "snippet"}
    through = structured_of(call(orivra, OrivraToolName.ASK.value, arguments))["gmail"]
    direct = structured_of(call(orivra, ToolName.SEARCH.value, arguments))

    def run(tool: str, args: Mapping[str, Any]) -> Mapping[str, Any]:
        return structured_of(call(orivra, tool, dict(args)))

    report = compare_affordances(through, direct, execute=run)
    assert report.results, "this query offers no affordances, so the check proves nothing"
    assert report.agreed, [one.render() for one in report.unresolved]
    assert report.complete and report.unexecuted_pairs == 0
    assert any(one.orivra_evidence > 0 for one in report.results), (
        "every executed pair recovered nothing, so equality is vacuous"
    )


def test_an_offer_only_one_side_makes_is_a_divergence(orivra: OrivraService) -> None:
    """Two responses that recovered the same evidence by routes only one of them offers have
    not answered the same question in the same way."""
    arguments = {"query": "note", "view": "snippet"}
    direct = structured_of(call(orivra, ToolName.SEARCH.value, arguments))
    stripped = json.loads(json.dumps(direct))
    stripped["withheld_groups"] = []
    stripped["withheld"] = []
    stripped["withheld_tail"] = []
    stripped["affordances"] = []
    for source in stripped["sources"]:
        source["collapsed_runs"] = []
    assert offers_of(direct) and not offers_of(stripped), "the strip removed nothing"

    def run(tool: str, args: Mapping[str, Any]) -> Mapping[str, Any]:
        return structured_of(call(orivra, tool, dict(args)))

    report = compare_affordances(direct, stripped, execute=run)
    assert any(one.status == "unpaired" for one in report.results), [
        one.render() for one in report.results
    ]


def test_an_offer_naming_a_tool_this_run_may_not_execute_is_invalid_not_run() -> None:
    """Read-only is checked, not assumed: only the four `mailweave_*` tools are executed."""
    forbidden = {
        "affordances": [{"tool": "orivra_expand", "args": {"thread_id": "t-1"}}],
        "sources": [],
    }

    def refuse(tool: str, args: Mapping[str, Any]) -> Mapping[str, Any]:
        raise AssertionError(f"an invalid offer was executed: {tool}")

    report = compare_affordances(forbidden, forbidden, execute=refuse)
    assert [one.status for one in report.results] == ["invalid"]
    assert "may not execute" in report.results[0].detail


def test_an_affordance_that_will_not_execute_is_a_divergence_not_a_crash(
    orivra: OrivraService,
) -> None:
    arguments = {"query": "note", "view": "snippet"}
    payload = structured_of(call(orivra, ToolName.SEARCH.value, arguments))

    def broken(tool: str, args: Mapping[str, Any]) -> Mapping[str, Any]:
        raise RuntimeError("the mailbox refused")

    report = compare_affordances(payload, payload, execute=broken)
    assert report.results
    assert all(one.status == "unexecutable" for one in report.results)
    assert "did not execute" in report.results[0].detail


def test_a_pair_that_lands_on_different_evidence_diverges_and_names_the_difference(
    orivra: OrivraService,
) -> None:
    arguments = {"query": "note", "view": "snippet"}
    payload = structured_of(call(orivra, ToolName.SEARCH.value, arguments))
    answers = iter(
        [
            {"sources": [{"thread_id": "t-1", "messages": [{"id": "m-1"}, {"id": "m-2"}]}]},
            {"sources": [{"thread_id": "t-1", "messages": [{"id": "m-1"}]}]},
        ]
    )

    def drifting(tool: str, args: Mapping[str, Any]) -> Mapping[str, Any]:
        return next(answers)

    report = compare_affordances(payload, payload, execute=drifting, limit=1)
    diverged = [one for one in report.results if one.status == "diverged"]
    assert len(diverged) == 1
    assert diverged[0].only_orivra == ("t-1/m-2",)
    assert "t-1/m-2" in diverged[0].render()


def test_the_comparison_is_bounded(orivra: OrivraService) -> None:
    """A live run's quota bill must not grow with how partial the answer was."""
    arguments = {"query": "note", "view": "snippet"}
    payload = structured_of(call(orivra, ToolName.SEARCH.value, arguments))
    ran: list[str] = []

    def counted(tool: str, args: Mapping[str, Any]) -> Mapping[str, Any]:
        ran.append(tool)
        return structured_of(call(orivra, tool, dict(args)))

    compare_affordances(payload, payload, execute=counted, limit=1)
    assert len(ran) == 2, "one pair is two calls, and no offer of theirs is followed"


def test_the_record_carries_no_body_no_handle_and_no_nonce(orivra: OrivraService) -> None:
    """A live record must not carry mail, a signature or a fence nonce."""
    from orivra.__main__ import run_one

    payload = structured_of(call(orivra, ToolName.SEARCH.value, {"query": "note"}))
    nonce = payload["fence_nonce"]
    maps = [
        source["map_id"] for source in payload["sources"] if isinstance(source.get("map_id"), str)
    ]
    _comparison, facts = run_one(orivra, "note", view="snippet")
    rendered = json.dumps(facts)
    assert nonce not in rendered
    for handle in maps:
        assert handle not in rendered
    assert "<<<" not in rendered


def test_an_unresolved_pair_makes_the_whole_query_diverge(
    orivra: OrivraService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runner's verdict has to move with the affordance result, or executing them is
    decoration."""
    from orivra import __main__ as runner
    from orivra.equivalence import AffordanceComparison, AffordanceReport

    monkeypatch.setattr(
        runner,
        "compare_affordances",
        lambda *_args, **_kwargs: AffordanceReport(
            results=(
                AffordanceComparison(
                    subject="thread_id=t-1",
                    tool="mailweave_thread_map",
                    status="unexecutable",
                    detail="the call did not execute: RuntimeError",
                ),
            ),
            total_pairs=1,
            executed_pairs=1,
            unexecuted_pairs=0,
        ),
    )
    comparison, facts = runner.run_one(orivra, "vendor", view="snippet")
    assert facts["equivalent"] is False
    assert not comparison.equivalent
    assert any(one.field == "affordances" for one in comparison.differences)


# -- the bound fails closed: thirteen pairs cannot pass as twelve ---------------------------
#
# `sorted(set(left) | set(right))[:limit]` truncated silently, so a response offering more
# pairs than the bound could be declared equivalent with the last one never executed. Thirteen
# recovery affordances have been observed live, so this was not a theoretical gap.


def _payload_with_pairs(count: int) -> dict[str, Any]:
    """A response offering exactly `count` distinct, executable recovery affordances."""
    return {
        "affordances": [
            {"tool": "mailweave_thread_map", "args": {"thread_id": f"t-{index:03d}"}}
            for index in range(count)
        ],
        "sources": [],
    }


def test_thirteen_pairs_are_not_declared_equivalent_on_twelve() -> None:
    """The exact condition the owner named. The thirteenth pair is never executed, and the
    report says so rather than reporting agreement."""
    payload = _payload_with_pairs(13)
    executed: list[str] = []

    def run(tool: str, args: Mapping[str, Any]) -> Mapping[str, Any]:
        executed.append(str(args.get("thread_id")))
        return {"sources": [{"thread_id": args["thread_id"], "messages": [{"id": "m-1"}]}]}

    report = compare_affordances(payload, payload, execute=run, limit=12)

    assert report.total_pairs == 13
    assert report.executed_pairs == 12
    assert report.unexecuted_pairs == 1
    assert report.complete is False
    assert report.agreed is False, "thirteen pairs passed on twelve executions"

    # Every executed pair agreed, and that is *not* enough for equivalence.
    agreed = [one for one in report.results if one.status == "agreed"]
    assert len(agreed) == 12
    unchecked = [one for one in report.results if one.status == "unchecked"]
    assert len(unchecked) == 1
    assert report.unresolved == tuple(unchecked)

    # The breach names what went unchecked, so a reader can see which route was skipped.
    assert "13 affordance pairs were offered" in unchecked[0].detail
    assert "t-012" in unchecked[0].detail
    assert "t-012" not in executed, "the pair past the bound was executed after all"
    assert len(executed) == 24, "one pair is two calls; the bound must still hold"


def test_exactly_the_bound_is_complete_and_can_agree() -> None:
    """The rule must not refuse everything: twelve pairs under a bound of twelve is a
    complete check, or the fail-closed rule would make every response diverge."""
    payload = _payload_with_pairs(12)

    def run(tool: str, args: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"sources": [{"thread_id": args["thread_id"], "messages": [{"id": "m-1"}]}]}

    report = compare_affordances(payload, payload, execute=run, limit=12)
    assert report.total_pairs == report.executed_pairs == 12
    assert report.unexecuted_pairs == 0
    assert report.complete and report.agreed


def test_a_bound_breach_makes_the_whole_query_diverge(
    orivra: OrivraService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runner's verdict has to move with the bound, or counting the skipped pairs is
    bookkeeping nobody reads."""
    from orivra import __main__ as runner
    from orivra.equivalence import AffordanceComparison, AffordanceReport

    monkeypatch.setattr(
        runner,
        "compare_affordances",
        lambda *_args, **_kwargs: AffordanceReport(
            results=(
                AffordanceComparison(
                    subject="1 pair(s) past the bound",
                    tool="(bound)",
                    status="unchecked",
                    detail="13 affordance pairs were offered and this run executes at most 12",
                ),
            ),
            total_pairs=13,
            executed_pairs=12,
            unexecuted_pairs=1,
        ),
    )
    comparison, facts = runner.run_one(orivra, "vendor", view="snippet")
    assert facts["equivalent"] is False
    assert facts["affordances"]["total_pairs"] == 13
    assert facts["affordances"]["executed_pairs"] == 12
    assert facts["affordances"]["unexecuted_pairs"] == 1
    assert facts["affordances"]["complete"] is False
    assert not comparison.equivalent
    assert any(one.field == "affordances" for one in comparison.differences)
    rendered = comparison.render()
    assert "13 pairs unresolved" in rendered or "of 13 pairs" in rendered


def test_a_bound_below_one_is_refused_rather_than_disabling_the_check() -> None:
    """A bound of zero would report every query as unchecked, which is a different way of
    not checking."""
    payload = _payload_with_pairs(2)
    with pytest.raises(ValueError, match="not to disable the check"):
        compare_affordances(payload, payload, execute=lambda *_a: {}, limit=0)


def test_a_report_with_unexecuted_pairs_never_reads_as_agreement() -> None:
    """`AffordanceReport.agreed` is a conjunction, and `complete` is the term that is easy to
    drop as redundant.

    Today it looks redundant: `compare_affordances` appends an `unchecked` result whenever it
    skips a pair, so `unresolved` is non-empty anyway. It is not redundant. `AffordanceReport`
    is a public dataclass a caller can construct, and a results list that lost its `unchecked`
    entry - filtered, re-sorted, rebuilt by a future summariser - would otherwise read as
    agreement while `unexecuted_pairs` said one pair was never run. The count is the fact; the
    record is a rendering of it.
    """
    from orivra.equivalence import AffordanceReport

    silent = AffordanceReport(results=(), total_pairs=13, executed_pairs=12, unexecuted_pairs=1)
    assert silent.unresolved == ()
    assert silent.complete is False
    assert silent.agreed is False, (
        "a report with an unexecuted pair and no unchecked record read as agreement"
    )


# -- the amended claim: accounted differences, and nothing else -----------------------------


NEAR_CAP_TERM = "Larch pricing draft"


def _near_cap_orivra() -> OrivraService:
    """A mailbox big enough that the two paths are fitted to different rooms.

    The fixture at the top of this file is small, so both paths land on the same layout and
    `compare` sees nothing - which is why the amendment needs its own fixture rather than a
    new assertion over the old one.

    **Re-measured 2026-09-22, body repeats 8 to 4.** With the text mirror's attribution and
    chronology lines charged on every row, at 8 repeats both rooms held two rows and the paths
    agreed. Measured on the shipped tools: the whole cap holds three rows and the container
    two from 1 to 6 repeats, so the paths diverge there; at 7 and above both hold two. 4 is
    the middle of that window, and the same figure `test_orivra_text_only_protocol`'s
    near-cap fixture was re-measured to.
    """
    base = mailbox()
    rows = [
        Msg(
            id=f"{thread:02x}{index:02x}beef{thread:02x}{index:02x}",
            thread_id=f"t-larch-{thread}",
            sender=f"p{index % 3}@team.example",
            subject=f"Larch pricing draft {thread}",
            body=("The Larch pricing draft needs the revised figures before we publish. " * 4),
            internal_date_ms=epoch_ms(2026, 1 + thread, 1 + index),
            to=("ana@team.example",),
            in_reply_to=(
                f"<{thread:02x}{index - 1:02x}beef{thread:02x}{index - 1:02x}@mail.invalid>"
                if index
                else None
            ),
        )
        for thread in range(8)
        for index in range(3)
    ]
    box = SyntheticMailbox(messages=(*base.messages, *rows), now_ms=base.now_ms)
    adapter = GmailAdapter(service=make_service(box), granted_scopes=(SCOPE,))
    return OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}), max_graph_nodes=14
    )


def test_near_the_cap_the_two_paths_really_do_diverge() -> None:
    """The amendment is only worth having if the thing it permits actually happens.

    If this stops diverging, `compare_ask`'s whole accounted-difference branch is dead code
    that no run exercises, and the test below would pass without ever reaching it.
    """
    service = _near_cap_orivra()
    arguments = {"query": NEAR_CAP_TERM, "view": "body_clean"}
    ask = structured_of(call(service, OrivraToolName.ASK.value, dict(arguments)))
    direct = structured_of(call(service, ToolName.SEARCH.value, dict(arguments)))
    assert compare(NEAR_CAP_TERM, ask["gmail"], direct).differences, (
        "the two paths agree at this size, so the accounted-difference branch is untested"
    )


def test_an_accounted_difference_is_equivalent_and_an_unaccounted_one_is_not() -> None:
    """Both halves, because a check that cannot fail is not a check.

    The first assertion is the amendment: a difference the response declares and accounts for
    does not fail level 2. The rest are the guards on it - strip the declaration, or the
    partiality, or the accounting, or add a message MailWeave never returned, and the same
    comparison reports a divergence again.
    """
    service = _near_cap_orivra()
    arguments = {"query": NEAR_CAP_TERM, "view": "body_clean"}
    ask = structured_of(call(service, OrivraToolName.ASK.value, dict(arguments)))
    direct = structured_of(call(service, ToolName.SEARCH.value, dict(arguments)))

    assert compare_ask(NEAR_CAP_TERM, ask, direct).equivalent, (
        "a declared, subset, partial, fully accounted difference failed level 2"
    )

    undeclared = json.loads(json.dumps(ask))
    undeclared.pop("allocation", None)
    assert not compare_ask(NEAR_CAP_TERM, undeclared, direct).equivalent, (
        "a difference with no allocation declared was accepted"
    )

    at_full_cap = json.loads(json.dumps(ask))
    at_full_cap["allocation"]["container_chars"] = at_full_cap["allocation"]["host_cap_chars"]
    assert not compare_ask(NEAR_CAP_TERM, at_full_cap, direct).equivalent, (
        "a difference was accepted from a response claiming it had the whole cap"
    )

    whole = json.loads(json.dumps(ask))
    whole["gmail"]["partial"] = False
    assert not compare_ask(NEAR_CAP_TERM, whole, direct).equivalent, (
        "a response that dropped evidence and called itself whole was accepted"
    )

    unaccounted = json.loads(json.dumps(ask))
    unaccounted["gmail"]["omission"] = {
        "withheld_messages": 0,
        "withheld_threads": 0,
        "not_included_sources": 0,
        "withheld_by_cap": {},
    }
    assert not compare_ask(NEAR_CAP_TERM, unaccounted, direct).equivalent, (
        "evidence that vanished with nothing accounting for it was accepted"
    )

    extra = json.loads(json.dumps(ask))
    borrowed = json.loads(json.dumps(direct["sources"][0]))
    borrowed["thread_id"] = "t-nowhere"
    extra["gmail"]["sources"] = [*extra["gmail"]["sources"], borrowed]
    assert not compare_ask(NEAR_CAP_TERM, extra, direct).equivalent, (
        "a response holding evidence mailweave_search never returned was accepted as narrower"
    )
