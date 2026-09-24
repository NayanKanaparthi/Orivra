"""R-M2-078: the recovery driver reads every response it obtains, and says why it stopped.

`arms.follow()` executed affordances from the first response only. A search that named the
evidence's thread in `not_included_sources`, whose thread map then surfaced the evidence and
offered the call that fetches it, stopped one hop short every time and reported the evidence
as never reached. `_execute` swallowed every raise as `None`, so a follow-up that raised on
every reply (R-M2-077) was scored identically to a follow-up that returned nothing.

These tests drive `follow()` against a **fake service** that returns envelope-shaped objects,
because the properties under test - breadth-first over obtained responses, no call twice, a
hard total call budget, a hop budget, raises recorded by class, the stop reason stated - are
properties of the driver and not of any mailbox. One integration test at the end runs the
real service over the real sample corpus and checks the shape the diagnostic found.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from mailweave.envelope.vocab import Depth, ToolName
from mailweave.envelope.wire import Affordance
from mailweave_harness.evaluation import arms
from mailweave_harness.evaluation.arms import MAX_RECOVERY_CALLS, MAX_RECOVERY_ROUNDS, Measured, follow

NONCE = "nonce-0000"


def _fence(text: str) -> str:
    from mailweave.envelope.fence import fence

    return fence(NONCE, text)


def _row(message_id: str, *, text: str | None, unabridged: bool = False) -> Any:
    """A `MessageRow`-shaped object: only the attributes the driver reads."""
    return SimpleNamespace(
        id=message_id,
        position=0,
        depth=SimpleNamespace(value="body_clean" if text is not None else "stub"),
        content=None if text is None else SimpleNamespace(text=_fence(text)),
        unabridged=(
            Affordance(tool=ToolName.GET_MESSAGES, args={"message_ids": [message_id], "view": "body_clean"})
            if unabridged else None
        ),
    )


def _env(
    *,
    rows: list[Any] = (),
    thread_id: str = "t1",
    not_included: list[str] = (),
    affordances: list[Affordance] = (),
    run_members: list[str] = (),
) -> Any:
    """An `Envelope`-shaped object with exactly what `_surfaced_ids`, `_content_by_id` and
    `_recovery_calls` read."""
    runs = []
    if run_members:
        runs.append(SimpleNamespace(
            positions=(0, len(run_members) - 1),
            member_ids=tuple(run_members),
            affordance=Affordance(tool=ToolName.GET_MESSAGES,
                                  args={"message_ids": list(run_members), "view": "snippet"}),
        ))
    return SimpleNamespace(
        fence_nonce=NONCE,
        sources=[SimpleNamespace(messages=list(rows), collapsed_runs=runs, thread_id=thread_id)],
        withheld=[],
        withheld_groups=[],
        not_included_entries=[
            SimpleNamespace(affordance=Affordance(tool=ToolName.THREAD_MAP, args={"thread_id": one}))
            for one in not_included
        ],
        affordances=list(affordances),
    )


@dataclass
class FakeService:
    """Answers each tool from a script keyed by the call's arguments, and records the calls."""

    maps: dict[str, Any] = field(default_factory=dict)
    gets: dict[str, Any] = field(default_factory=dict)
    raises: dict[str, Exception] = field(default_factory=dict)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def thread_map(self, request: Any) -> Any:
        self.calls.append(("thread_map", {"thread_id": request.thread_id}))
        if request.thread_id in self.raises:
            raise self.raises[request.thread_id]
        return self.maps[request.thread_id]

    def get_messages(self, request: Any) -> Any:
        key = ",".join(request.message_ids)
        self.calls.append(("get_messages", {"message_ids": list(request.message_ids)}))
        if key in self.raises:
            raise self.raises[key]
        return self.gets[key]

    def search(self, request: Any) -> Any:  # pragma: no cover - no script offers a search
        raise AssertionError("no test here offers a search affordance")


QUOTE = "the agreed figure is forty"


def _three_hop_script() -> tuple[FakeService, Any]:
    """The diagnostic's shape: search names the thread; the map surfaces the evidence in a
    run and offers snippets; the snippet response offers the body; the body carries it."""
    first = _env(not_included=["t9"])
    the_map = _env(thread_id="t9", run_members=["e1", "e2", "e3"])
    snippets = _env(thread_id="t9", rows=[_row("e1", text=None, unabridged=True),
                                          _row("e2", text=None, unabridged=True),
                                          _row("e3", text=None, unabridged=True)])
    body = _env(thread_id="t9", rows=[_row("e2", text=QUOTE)])
    service = FakeService(
        maps={"t9": the_map},
        gets={"e1,e2,e3": snippets, "e2": body},
    )
    return service, first


def test_the_driver_follows_what_a_later_response_offers() -> None:
    service, first = _three_hop_script()
    reach, merged = follow(service, first, required=frozenset({"e2"}),
                           first_content={}, quotes={"e2": QUOTE})
    assert reach.after_expansion == frozenset({"e2"})
    assert reach.first_response == frozenset()
    assert reach.stopped == "evidence_in_hand"
    assert reach.levels == 4, "search, map, snippets, body: four disclosure levels"
    assert [tool for tool, _ in service.calls] == ["thread_map", "get_messages", "get_messages"]
    assert "e2" in merged


def test_the_previous_driver_shape_stops_one_hop_short() -> None:
    """With `rounds=1` the driver is the old one, and the old one never reached hop 2."""
    service, first = _three_hop_script()
    reach, _ = follow(service, first, required=frozenset({"e2"}),
                      first_content={}, quotes={"e2": QUOTE}, rounds=1)
    assert reach.after_expansion == frozenset()
    assert reach.surfaced_only == frozenset({"e2"}), "the map named it and the driver stopped"
    assert reach.stopped == "hop_budget"
    assert reach.state is Measured.INCONCLUSIVE


def test_no_call_is_made_twice_even_when_two_responses_offer_it() -> None:
    first = _env(not_included=["t9", "t9"])
    the_map = _env(thread_id="t9", not_included=["t9"], run_members=["e1"])
    service = FakeService(maps={"t9": the_map}, gets={"e1": _env(rows=[_row("e1", text=None)])})
    reach, _ = follow(service, first, required=frozenset({"zz"}), first_content={}, quotes={"zz": "x"})
    assert [args for _, args in service.calls].count({"thread_id": "t9"}) == 1
    assert reach.stopped in {"no_new_affordances", "hop_budget"}


def test_a_cycle_of_offers_terminates_under_the_call_budget() -> None:
    """A map that offers a snippet fetch whose rows offer the map again, forever."""
    first = _env(not_included=["t9"])
    the_map = _env(thread_id="t9", run_members=["e1"], not_included=["t9"])
    snippets = _env(thread_id="t9", rows=[_row("e1", text=None, unabridged=True)], not_included=["t9"])
    service = FakeService(maps={"t9": the_map}, gets={"e1": snippets})
    reach, _ = follow(service, first, required=frozenset({"never"}), first_content={}, quotes={"never": "x"})
    assert reach.rounds <= MAX_RECOVERY_CALLS
    assert reach.stopped in {"no_new_affordances", "hop_budget", "call_budget"}


def test_the_total_call_budget_is_a_hard_stop_and_is_named() -> None:
    """Many offers in one hop: the driver stops at the budget and says so."""
    many = [f"m{index}" for index in range(MAX_RECOVERY_CALLS + 10)]
    first = _env(rows=[_row(one, text=None, unabridged=True) for one in many])
    service = FakeService(gets={one: _env(rows=[_row(one, text=None)]) for one in many})
    reach, _ = follow(service, first, required=frozenset(many), first_content={},
                      quotes={one: "absent" for one in many})
    assert reach.rounds == MAX_RECOVERY_CALLS
    assert reach.stopped == "call_budget"
    assert reach.state is Measured.INCONCLUSIVE


def test_a_follow_up_that_raises_is_recorded_by_class_and_scored_as_a_failure() -> None:
    """R-M2-077's shape: the map surfaces the evidence, the body fetch raises."""
    first = _env(not_included=["t9"])
    the_map = _env(thread_id="t9", rows=[_row("e2", text=None, unabridged=True)])
    service = FakeService(maps={"t9": the_map}, raises={"e2": ValueError("C-02a")})
    reach, _ = follow(service, first, required=frozenset({"e2"}), first_content={}, quotes={"e2": QUOTE})
    assert reach.exceptions == ("mailweave_get_messages: ValueError",)
    assert reach.after_expansion == frozenset()
    assert reach.state is Measured.FAILED, "a raise is the product failing, not empty evidence"
    assert reach.surfaced_only == frozenset({"e2"})


def test_a_raise_does_not_stop_the_other_offers_of_the_same_hop() -> None:
    """Two required messages, the first fetch raises, the second carries: partial reach,
    the raise on record, and the state is MEASURED because something was measured."""
    first = _env(rows=[_row("bad", text=None, unabridged=True), _row("good", text=None, unabridged=True)])
    service = FakeService(gets={"good": _env(rows=[_row("good", text=QUOTE)])},
                          raises={"bad": RuntimeError("boom")})
    reach, _ = follow(service, first, required=frozenset({"bad", "good"}), first_content={},
                      quotes={"bad": "absent", "good": QUOTE})
    assert reach.after_expansion == frozenset({"good"})
    assert reach.exceptions == ("mailweave_get_messages: RuntimeError",)
    assert reach.surfaced_only == frozenset({"bad"})
    assert reach.state is Measured.MEASURED


def test_evidence_already_in_hand_makes_no_calls() -> None:
    service, first = _three_hop_script()
    reach, _ = follow(service, first, required=frozenset({"e2"}),
                      first_content={"e2": QUOTE}, quotes={"e2": QUOTE})
    assert service.calls == []
    assert reach.stopped == "evidence_in_hand"
    assert reach.first_response == reach.after_expansion == frozenset({"e2"})


def test_the_budget_constants_are_the_ones_the_suite_already_enforced() -> None:
    """Named, not raised: the harness test bounded `rounds` at four times eight before."""
    assert MAX_RECOVERY_ROUNDS == 4
    assert MAX_RECOVERY_CALLS == MAX_RECOVERY_ROUNDS * 8


def test_execute_returns_the_exception_rather_than_none() -> None:
    service = FakeService(raises={"t9": KeyError("gone")})
    got = arms._execute(service, Affordance(tool=ToolName.THREAD_MAP, args={"thread_id": "t9"}))  # type: ignore[arg-type]
    assert isinstance(got, KeyError)


# --- the real thing, once ------------------------------------------------------------------


def test_on_the_sample_corpus_the_driver_reads_the_map_it_obtained() -> None:
    """The shape the diagnostic found, on the generator's own corpus and the no-backend arm.

    A long F3 conversation reached by its entity name: the first response names the thread in
    `not_included_sources`, the map names the message, and the map's own affordance is the
    second hop. Under `rounds=1` - the previous driver - the second hop is never taken; under
    the repaired driver it is, and the driver says why it stopped. Whether the body is ever
    *reached* is a property of what the product offers, which the diagnostic rerun reports
    per case; what this asserts is that the driver follows what it is given.
    """
    import re

    from mailweave.surface.arguments import parse_search
    from mailweave_harness.seed.corpus import generate
    from tests.fixtures import eval_dummy

    manifest = generate(master_seed=4311, size_profile="sample")
    box, report = eval_dummy.mailbox_of(manifest)
    arm = next(one for one in eval_dummy.dummy_arms(manifest, box) if one.name == "sem-off")
    truths = [one for one in manifest.answer_key.threads if one.family == "F3" and one.evidence_positions]
    examined = 0
    for truth in truths:
        if examined >= 6:
            break
        position = truth.evidence_positions[0]
        message = next(one for one in manifest.messages
                       if one.thread_key == truth.thread_key and one.position == position)
        message_id = eval_dummy._gmail_id(message)
        quote = message.body.split("\n-- ")[0].splitlines()[0][:60]
        entity = next((re.sub(r"[^A-Za-z]", "", word) for word in truth.subject.split()
                       if word[:1].isupper() and len(word) > 3), None)
        if not entity:
            continue
        try:
            envelope = arm.service.search(parse_search({"query": entity}))
        except Exception:
            continue
        named = {entry.affordance.args.get("thread_id") for entry in envelope.not_included_entries}
        if f"t-{truth.thread_key}" not in named:
            continue
        examined += 1
        first = arms._content_by_id(envelope)
        old, _ = follow(arm.service, envelope, required=frozenset({message_id}),
                        first_content=first, quotes={message_id: quote}, rounds=1)
        new, _ = follow(arm.service, envelope, required=frozenset({message_id}),
                        first_content=first, quotes={message_id: quote})
        # Hop 1 on both: the map is executed and the message is named by it.
        assert "mailweave_thread_map" in old.calls and message_id in (old.surfaced_only | old.after_expansion)
        # Hop 2 only on the repaired driver: the map's own offer is executed. Since 2026-09-15
        # (R-M2-093) the first response itself recommends a read of the hits it carries as
        # collapsed-run members, so a read can appear at hop 1 on both drivers; what only the
        # repaired driver adds is the map's own read, one more than the first response offered.
        assert new.calls.count("mailweave_get_messages") > old.calls.count(
            "mailweave_get_messages"
        ), (old.calls, new.calls)
        assert new.rounds > old.rounds
        assert new.stopped in {"evidence_in_hand", "no_new_affordances", "call_budget", "hop_budget"}
        assert old.stopped == "hop_budget"
        return
    raise AssertionError(
        "no F3 conversation in the first six was named in not_included_sources by its entity, "
        "so the shape this test is about could not be reached on this corpus"
    )
