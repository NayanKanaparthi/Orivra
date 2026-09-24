"""Round 28: a surface-efficiency checkpoint, not the thesis.

Five bounded corrections to what the model sees and to one wasteful read, each with the
owner's corrections of 2026-09-07 written into the assertion rather than the docstring:

  * the published `budget` schema and the argument reader are one list, checked with a JSON
    Schema validator against every affordance this server can mint (R-MCP-025, second half);
  * a served search carries at most one recommended expansion call, naming only
    matched/evidence rows that lack the requested depth, never context or map stubs, and
    none at all when nothing is missing - in both halves of the result;
  * `mailweave_search`'s description says `mailweave_get_messages` is the direct,
    identity-preserving way to read a message the response already identified. It does
    **not** say a narrower search cannot recover one: the owner's experiment showed it can;
  * `mailweave_get_messages` issues at most one `messages.get(format=full)` per named id,
    asserted per id, with every endpoint's count reported on its own;
  * the default deadline is derived from PF-21's measurement, in a separate commit, after the
    owner has seen the figures.

Nothing here is evidence about progressive disclosure, query-aware depth, or broad searches,
and no test below claims it. No fixture carries real or realistic personal mail.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

import httpx
import jsonschema
import pytest

from mailweave.constants import HOST_RESULT_CHAR_CAP, MAX_BODY_FETCHES_L0
from mailweave.envelope.measure import recommended_expansion_chars, rendered_chars
from mailweave.envelope.vocab import ToolName
from mailweave.policy.budget import WITHHELD_CAP_OF, _raise_to
from mailweave.surface.arguments import BUDGET_KEYS, parse_search
from mailweave.surface.partition import rendered_of
from mailweave.surface.recovery import narrower_call
from mailweave.surface.rendering import is_the_recommended_expansion
from mailweave.surface.server import call
from mailweave.surface.tools import SPEC_BY_NAME, published_budget_keys
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.test_mcp_surface_round24 import make_service, structured_of
from tests.test_round26 import FILLER, TERM, _thread_mailbox
from tests.test_round27 import multi_thread_mailbox

# =============================================================================================
# Part 1 - one list: the schema and the reader (R-MCP-025, second half)
# =============================================================================================


def _validator_for(tool: ToolName) -> jsonschema.Draft202012Validator:
    schema = SPEC_BY_NAME[tool].input_schema
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def test_the_reader_accepts_exactly_the_budget_keys_the_schema_publishes() -> None:
    """The docstring on `BUDGET_KEYS` claimed a derivation the code did not perform.

    Round 27 added `max_hit_threads` to the reader and not to the schema, so a client that
    validated arguments against `inputSchema` refused the `retry_with` a declined search
    handed back - the same refusal R-MCP-025 was about, one layer earlier. There is now one
    list, and this asserts it is the schema's rather than a copy that happens to match today.
    """
    assert published_budget_keys() == BUDGET_KEYS
    assert "max_hit_threads" in BUDGET_KEYS


def _every_mintable_budget_affordance() -> list[tuple[str, Mapping[str, Any]]]:
    """Every search affordance a builder in this server can produce with a `budget` in it."""
    minted: list[tuple[str, Mapping[str, Any]]] = []
    for cap in WITHHELD_CAP_OF:
        offer = _raise_to(cap, 2, query=TERM)
        minted.append((f"raise:{cap.value}", offer.args))
    step = narrower_call("mailweave_search", {"query": TERM}, top_thread=None)
    assert step is not None
    minted.append(("decline:retry_with", step.affordance.args))
    return minted


@pytest.mark.parametrize(
    ("source", "arguments"),
    _every_mintable_budget_affordance(),
    ids=[name for name, _ in _every_mintable_budget_affordance()],
)
def test_every_budget_cap_this_server_can_mint_validates_against_the_schema(
    source: str, arguments: Mapping[str, Any]
) -> None:
    """Validated with a JSON Schema validator, which is what a strict client does.

    Round 27's test asked the parser. A client that checks `inputSchema` before sending
    never reaches the parser, so a key the parser accepted and the schema lacked passed that
    test and failed the client. Both gates are asked here.
    """
    _validator_for(ToolName.SEARCH).validate(dict(arguments))
    parse_search(dict(arguments))


def test_a_declined_search_hands_back_a_call_a_strict_client_will_send() -> None:
    """Every hop of a real decline's chain validates against the schema of the tool it names.

    Round 29 changed the fixture: twenty one-message threads no longer decline (that was
    R-MCP-033), so the shape that declines is one thread too large for any arrangement, and
    the chain it produces changes tool. The strict-client property has to hold at every hop,
    not only the first, because the hop that changes tool is the one a schema most easily
    refuses - a `segment` key on a thread map, say.
    """
    from mailweave.surface.recovery import MAX_RECOVERY_STEPS

    # Since 2026-09-15 (R-M2-093) a thread the ladder can carry as a collapsed run is served
    # with its hits as run members, so "too large for any arrangement" means too large even
    # as a run: nine hundred messages, whose inventory alone is over the cap.
    box = multi_thread_mailbox(threads=1, per_thread=900, words=5)
    result = call(make_service(box), "mailweave_search", {"query": TERM})
    assert result.is_error
    hops = 0
    while result.is_error:
        retry = structured_of(result)["retry_with"]
        if retry is None:
            break
        hops += 1
        assert hops <= MAX_RECOVERY_STEPS
        _validator_for(ToolName(retry["tool"])).validate(dict(retry["args"]))
        result = call(make_service(box), retry["tool"], dict(retry["args"]))
    assert hops >= 1


# =============================================================================================
# Part 2 - one full read per named id in `mailweave_get_messages` (R-MCP-038)
# =============================================================================================


class _EndpointLedger:
    """Every Gmail request a call made, by endpoint, and every `messages.get` by id and format.

    Wrapped around the fixture's own handler rather than read off `CallMeter`, because the
    meter counts requests and this is about *which* requests: the finding is two `full` reads
    of one id, and a total that merely went down by one would not say which read went.
    """

    def __init__(self, box: SyntheticMailbox) -> None:
        self.by_endpoint: Counter[str] = Counter()
        self.full_reads_by_id: Counter[str] = Counter()
        self.metadata_reads_by_id: Counter[str] = Counter()
        original = box.handler

        def counting(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if "/messages/" in path and not path.endswith("/messages"):
                message_id = path.rsplit("/", 1)[-1]
                if request.url.params.get("format") == "full":
                    self.full_reads_by_id[message_id] += 1
                else:
                    self.metadata_reads_by_id[message_id] += 1
                self.by_endpoint["messages.get"] += 1
            elif path.endswith("/messages"):
                self.by_endpoint["messages.list"] += 1
            elif "/threads/" in path:
                self.by_endpoint["threads.get"] += 1
            elif path.endswith("/profile"):
                self.by_endpoint["getProfile"] += 1
            elif path.endswith("/history"):
                self.by_endpoint["history.list"] += 1
            else:
                self.by_endpoint[path] += 1
            return original(request)

        box.handler = counting  # type: ignore[method-assign]

    def report(self) -> dict[str, Any]:
        """Every endpoint on its own. Profile, history and maps are their own overhead and are
        not folded into one number (the owner's correction of 2026-09-07)."""
        return {
            "getProfile": self.by_endpoint["getProfile"],
            "history.list": self.by_endpoint["history.list"],
            "messages.list": self.by_endpoint["messages.list"],
            "threads.get": self.by_endpoint["threads.get"],
            "messages.get": self.by_endpoint["messages.get"],
            "full_reads_by_id": dict(self.full_reads_by_id),
        }


def _two_thread_box() -> SyntheticMailbox:
    return multi_thread_mailbox(threads=2, per_thread=3, words=30)


@pytest.mark.parametrize("view", ("body_clean", "body_full"))
@pytest.mark.parametrize("how_many", (1, 3))
def test_get_messages_reads_each_named_body_at_most_once(view: str, how_many: int) -> None:
    """**R-MCP-038.** Before this round: two `messages.get(format=full)` per named id.

    `_threads_of` fetched the id in full to learn its thread and kept only `thread_id`;
    `_bodies_for` fetched it in full again to process it. Asserted per id, not as a total:
    the total also contains the thread map and the watermark, which are separate overhead.
    """
    box = _two_thread_box()
    ledger = _EndpointLedger(box)
    ids = [f"m000{i:03d}" + "e" * 9 for i in range(how_many)]
    result = call(make_service(box), "mailweave_get_messages", {"message_ids": ids, "view": view})
    assert not result.is_error, json.dumps(structured_of(result))[:300]
    report = ledger.report()
    for message_id in ids:
        assert report["full_reads_by_id"].get(message_id, 0) == 1, report
    assert report["messages.get"] == how_many, report
    # The rest of the call's reads, each on its own, so the overhead is visible and named.
    assert report["threads.get"] == 1, report
    assert report["getProfile"] >= 1, report
    payload = structured_of(result)
    rows = {row["id"]: row for source in payload["sources"] for row in source["messages"]}
    for message_id in ids:
        assert rows[message_id]["depth"] == view, rows[message_id]


def test_get_messages_at_a_bodiless_view_reads_no_body_at_all() -> None:
    """The other direction of the same rule: a `stub` request pays for no text."""
    box = _two_thread_box()
    ledger = _EndpointLedger(box)
    ids = ["m000000" + "e" * 9, "m000001" + "e" * 9]
    result = call(make_service(box), "mailweave_get_messages", {"message_ids": ids, "view": "stub"})
    assert not result.is_error
    report = ledger.report()
    assert report["full_reads_by_id"] == {}, report
    assert all(ledger.metadata_reads_by_id[i] == 1 for i in ids), dict(ledger.metadata_reads_by_id)


def test_get_messages_by_map_id_and_positions_also_reads_each_body_once() -> None:
    """The handle route learns its thread from the handle and pays its one read in `_bodies_for`."""
    box = _two_thread_box()
    first = structured_of(call(make_service(box), "mailweave_search", {"query": TERM}))
    map_id = first["sources"][0]["map_id"]
    ledger = _EndpointLedger(box)
    result = call(
        make_service(box),
        "mailweave_get_messages",
        {"map_id": map_id, "positions": [0, 2], "view": "body_clean"},
    )
    assert not result.is_error, json.dumps(structured_of(result))[:300]
    report = ledger.report()
    assert all(n == 1 for n in report["full_reads_by_id"].values()), report
    assert len(report["full_reads_by_id"]) == 2, report


# =============================================================================================
# Part 3 - the one recommended expansion, both halves (round 28 item 2)
# =============================================================================================


def _recommendation(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    found = [a for a in payload.get("affordances", ()) if is_the_recommended_expansion(payload, a)]
    assert len(found) <= 1, found
    return found[0] if found else None


def _recommended_line(text: str) -> str | None:
    lines = [
        line for line in text.splitlines() if line.startswith("next call mailweave_get_messages {")
    ]
    assert len(lines) <= 1, lines
    return lines[0] if lines else None


def _one_hit_in_a_long_thread(length: int = 12, hit_at: int = 7) -> SyntheticMailbox:
    rows = [
        Msg(
            id=f"c{i:03d}",
            thread_id="ct",
            sender="ana@team.example",
            subject="quarterly cadence review" if i == 0 else "Re: quarterly cadence review",
            body=" ".join([TERM if i == hit_at else "nothing", *FILLER]),
            internal_date_ms=epoch_ms(2026, 8, 1) + i * 3_600_000,
            to=("rob@team.example",),
            in_reply_to=(f"<c{i - 1:03d}@mail.invalid>" if i else None),
        )
        for i in range(length)
    ]
    return SyntheticMailbox(messages=tuple(rows), now_ms=epoch_ms(2026, 9, 3))


#: The fixture for the recommendation tests: enough hits in one thread that A.9a step 3 leaves
#: some at stub depth, and few enough that step 5 does not then collapse the stubs into a run.
#: **Twelve until round 29, eleven since.** Round 29 charges `retrieval_report.not_tried[]`
#: at its rendered size (R-V01-013(a): its budget entries carry the query), which is ~470
#: characters this fixture's estimate had not been paying; at twelve messages the step-3
#: layout sat 505 characters over the host cap once it did, so the ladder took step 5 and no
#: stub row survived for the recommendation to name. The rendered step-3 response was 23,404
#: characters - inside the cap - so this is the estimate erring high at the edge, which is the
#: direction it may err in; eleven messages sit 657 under the cap after step 3.
RECOMMENDATION_FIXTURE_MESSAGES = 11
RECOMMENDATION_FIXTURE_BELOW_DEPTH = RECOMMENDATION_FIXTURE_MESSAGES - 5

#: **Round 31 moved the body length rather than the message count.** WS-14's INJ-05 adds three
#: per-message identity fields to every row, which the estimate now charges (110 characters and
#: 9 tokens, measured); at 110-word bodies the step-3 layout for eleven messages moved from
#: 24,534 to ~25,990 characters and the ladder took step 5, leaving no row below depth for the
#: recommendation to name. Reducing `messages` again - round 29's move, twelve to eleven -
#: would have taken `RECOMMENDATION_FIXTURE_BELOW_DEPTH` to five, which is
#: `RECOMMENDED_EXPANSION_LIMIT` itself: `len(named) == 5` would then hold because five is all
#: there was, not because the bound held, and the test would pass for a reason that does not
#: establish what it claims. Body length carries no claim in this fixture, so that is the knob
#: this round turns. Measured at eleven messages: 85 words puts the step-3 layout at 23,974
#: characters against the 25,000 cap - 1,026 under, where 95 words leaves 320 - with the
#: pre-ladder layout at 30,740, so step 3 still fires and six matched rows are still left
#: below depth. Below 85 words a sixth body fits inside the ceiling and `below` falls to five,
#: which is the other edge this figure sits between.
#: **Re-measured 2026-09-21, 85 to 62.** Every row grew an attribution block and an
#: always-present chronology pair (~190 characters a row on this fixture: a bare address and
#: no display name), and the estimate now charges both, so at 85 words the step-3 layout for
#: eleven messages moved past the cap and the ladder took step 5 again - five rows, nothing
#: below depth, no recommendation. Measured at eleven messages with the new charge: the window
#: in which step 3 fires and six matched rows sit below depth is 56 to 67 words; at 55 a sixth
#: body fits inside the ceiling and `below` falls to five, at 68 the ladder takes step 5.
#: 62 is the middle of that window, and renders 22,361 characters against the 25,000 cap.
#: **Re-measured 2026-09-22, 62 to 36.** The text mirror gained the attribution and
#: chronology lines on every row and the note at the head of the response, and the estimate
#: charges them (~150 characters a row on this fixture, plus 250 once), so at 62 words the
#: ladder took step 5 again. Measured at eleven messages: the window is now 33 to 40 words -
#: at 32 a sixth body fits inside the ceiling and `below` falls to five, at 41 the ladder
#: takes step 5. 36 is the middle, and renders 22,147 characters against the cap.
RECOMMENDATION_FIXTURE_WORDS = 36


def test_the_recommendation_names_only_matched_rows_below_the_requested_depth() -> None:
    """Eleven hits in one thread: five carried at body depth, six not. It names the six,
    bounded at five, and none of the five already at depth."""
    result = call(
        make_service(
            _thread_mailbox(
                messages=RECOMMENDATION_FIXTURE_MESSAGES, words=RECOMMENDATION_FIXTURE_WORDS
            )
        ),
        "mailweave_search",
        {"query": TERM},
    )
    payload = structured_of(result)
    rows = {row["id"]: row for source in payload["sources"] for row in source["messages"]}
    below = [
        rid
        for rid, row in rows.items()
        if row["role"] == "matched" and row["depth"] != "body_clean"
    ]
    assert len(below) == RECOMMENDATION_FIXTURE_BELOW_DEPTH, below
    offer = _recommendation(payload)
    assert offer is not None
    named = offer["args"]["message_ids"]
    assert offer["args"]["view"] == "body_clean"
    assert len(named) == 5  # RECOMMENDED_EXPANSION_LIMIT = MAX_BODY_FETCHES_L0
    assert set(named) <= set(below)
    for rid in named:
        assert rows[rid]["role"] == "matched"


def test_context_and_map_stubs_are_never_recommended() -> None:
    """One hit at position 7 of a twelve-message thread: eleven stubs and snippets around it,
    and the one match already at depth. Nothing is missing, so nothing is recommended."""
    result = call(make_service(_one_hit_in_a_long_thread()), "mailweave_search", {"query": TERM})
    payload = structured_of(result)
    roles = Counter(row["role"] for source in payload["sources"] for row in source["messages"])
    assert roles["matched"] == 1 and roles["stub"] >= 8, roles
    assert _recommendation(payload) is None
    assert _recommended_line(rendered_of(result).text) is None


def test_no_recommendation_when_every_matched_row_is_already_at_depth() -> None:
    """No row is below depth, so there is nothing to recommend.

    **`words=22` rather than the default 40** (round 31). Nine bodies at the default put the
    pre-ladder layout at 25,978 characters once INJ-05's identity fields are charged - 978 over
    the host cap - so step 3 fired and two matched rows dropped below depth, which is not the
    state this test is about. The precondition is asserted below rather than assumed, so the
    figure carries no claim of its own: at 22 words the layout is 23,686 characters, 1,314
    under the cap, and no ladder step runs at all.

    **Re-measured 2026-09-21, 22 to 12.** The attribution and chronology charge on every row
    moved the same edge again: at 22 words two matched rows dropped below depth, at 16 one
    did, and at 14 and below none does. 12 sits two words inside that edge and renders
    21,912 characters.

    **Re-measured 2026-09-22: nine bodies to six, at the default 40 words.** With the text
    mirror's attribution and chronology lines charged on every row, nine rows at body depth
    across three threads no longer fit at any body length: at 12 words four matched rows
    dropped below depth, at 4 one did, and only empty bodies fit - a fixture with no bodies is
    not one where every match is "at depth". The count carries no claim here either, so the
    shape is three threads of two: every match at body depth from 12 to 60 words with no cap
    hit (at 80 the ladder withholds two matches instead), and at the default 40 the response
    renders 20,671 characters.
    """
    result = call(
        make_service(multi_thread_mailbox(threads=3, per_thread=2, words=40)),
        "mailweave_search",
        {"query": TERM},
    )
    payload = structured_of(result)
    assert all(
        row["depth"] == "body_clean"
        for source in payload["sources"]
        for row in source["messages"]
        if row["role"] == "matched"
    )
    assert _recommendation(payload) is None


def test_the_mirror_carries_the_recommendation_with_its_arguments_and_nothing_else_gains_them() -> (
    None
):
    """Both halves. The recommended call is the one `next call` line that renders arguments;
    every other affordance line is still a tool name, so the mirror does not grow with the
    withheld count (R-MCP-033 is not made worse by this round)."""
    result = call(
        make_service(
            _thread_mailbox(
                messages=RECOMMENDATION_FIXTURE_MESSAGES, words=RECOMMENDATION_FIXTURE_WORDS
            )
        ),
        "mailweave_search",
        {"query": TERM},
    )
    payload = structured_of(result)
    mirrored = rendered_of(result)
    line = _recommended_line(mirrored.text)
    assert line is not None
    offer = _recommendation(payload)
    assert offer is not None
    assert json.loads(line.removeprefix("next call mailweave_get_messages ")) == offer["args"]
    plain = [
        other
        for other in mirrored.text.splitlines()
        if other.startswith("next call ") and other != line
    ]
    assert all(len(other.split()) == 3 for other in plain), plain[:3]
    # And it costs what the estimate charges for it, or less.

    entry_chars = len(json.dumps(offer))
    assert entry_chars + len(line) + 1 <= recommended_expansion_chars(
        offer["args"]["message_ids"], limit=MAX_BODY_FETCHES_L0
    )


def test_the_recommendation_copied_from_the_text_alone_reads_the_missing_bodies() -> None:
    """The acceptance the work order names: a reader who only has the text can make the call."""
    box = _thread_mailbox(
        messages=RECOMMENDATION_FIXTURE_MESSAGES, words=RECOMMENDATION_FIXTURE_WORDS
    )
    first = call(make_service(box), "mailweave_search", {"query": TERM})
    line = _recommended_line(rendered_of(first).text)
    assert line is not None
    tool, _, args_json = line.removeprefix("next call ").partition(" ")
    arguments = json.loads(args_json)
    _validator_for(ToolName(tool)).validate(arguments)
    second = call(make_service(box), tool, arguments)
    assert not second.is_error, json.dumps(structured_of(second))[:300]
    rows = {row["id"]: row for s in structured_of(second)["sources"] for row in s["messages"]}
    for rid in arguments["message_ids"]:
        assert rows[rid]["depth"] == "body_clean", rows[rid]
        assert rows[rid]["content"]["text"], rid


def test_a_search_response_still_fits_and_the_estimate_still_bounds_it_with_the_line() -> None:
    result = call(
        make_service(
            _thread_mailbox(
                messages=RECOMMENDATION_FIXTURE_MESSAGES, words=RECOMMENDATION_FIXTURE_WORDS
            )
        ),
        "mailweave_search",
        {"query": TERM},
    )
    mirrored = rendered_of(result)
    assert rendered_chars(mirrored.structured, mirrored.text) <= HOST_RESULT_CHAR_CAP


# =============================================================================================
# Part 4 - what the description says, and what it must not say (round 28 item 3)
# =============================================================================================


def test_the_search_description_names_get_messages_as_the_direct_way_to_read_a_known_row() -> None:
    from mailweave.surface.tools import SEARCH

    text = " ".join(claim.text for claim in SEARCH.claims)
    assert "mailweave_get_messages" in text
    assert "identity-preserving" in text
    assert "exploratory search" in text


def test_no_description_claims_a_narrower_search_cannot_recover_an_identified_message() -> None:
    """The owner's correction of 2026-09-07: the experiment showed a narrower search can
    recover a message already returned as a stub. The description says `get_messages` is the
    direct way, and does not say the other way is impossible."""
    from mailweave.surface.tools import TOOL_SPECS

    for spec in TOOL_SPECS:
        for claim in spec.claims:
            lowered = claim.text.lower()
            for forbidden in (
                "cannot recover",
                "does not recover",
                "will not recover",
                "never recovers",
            ):
                assert forbidden not in lowered, (spec.name, claim.text)
