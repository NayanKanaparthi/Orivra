"""Every `ReasonKind` renderer, and the OD-3 reply-chain floor shape (R-DISC-004).

R-DISC-004: of the ten `ReasonKind` variants, the round-1 suite constructed two.
`GmailQueryMatch` and `ThreadMember` were exercised; the other eight `.render()` methods -
each its own f-string, and `render()` is precisely the mechanism PART-07 grades - were
never called by any test. The round's headline capability, OD-3's reply-parent/child stub
floor, was likewise built only by the reviewer's own probe.

Coverage here is not "each one was called once". Three properties are asserted, and each
is a way the mechanism could be hollow:

  * **completeness** - the variant table is checked against `ReasonKind` itself, so an
    eleventh kind added without a render test fails this module rather than passing
    silently;
  * **participation** - every field of every reason is mutated in turn and the render must
    change. A renderer that ignores its parameters, or returns a constant, fails. This is
    PART-07's "mechanical, never decorative" stated as a property rather than as a
    spot-check on one string;
  * **distinctness** - no two kinds render the same text, so the degenerate strategy
    PART-07 names (one reason on every message) is visible rather than hidden in prose.

Nothing here restates a format string. The expected values are the parameters the test
constructed, and the assertions are about the relation between them and the output.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

import pytest
from pydantic import Field, ValidationError

from mailweave.envelope import (
    Affordance,
    Content,
    ContentSource,
    Depth,
    DispositionLedger,
    EnvelopeBuilder,
    Linkage,
    MailboxProvenance,
    MessageRow,
    Outcome,
    Role,
    RungId,
    Source,
    Sufficiency,
    ToolName,
    Trust,
)
from mailweave.envelope.fence import fence, mint_nonce
from mailweave.envelope.reasons import (
    ALL_REASON_KINDS,
    FloorPromoted,
    GmailQueryMatch,
    HistoryAddition,
    QueryScoredFill,
    Reason,
    ReasonKind,
    ReasonScalar,
    RecencyContext,
    ReplyChildOf,
    ReplyParentAmbiguous,
    ReplyParentOf,
    RequestedById,
    Rfc822MsgId,
    SemanticScore,
    SnippetContains,
    ThreadMember,
    WindowOffset,
    _ReasonBase,
)
from mailweave.envelope.vocab import (
    FillComponent,
    FloorDependence,
    FloorRelation,
    RecheckedOperator,
)
from tests.fixtures import envelope_kit as kit

#: One constructed instance per kind. Values are deliberately distinctive strings so a
#: renderer that drops a parameter is visible rather than plausible.
VARIANTS: tuple[Reason, ...] = (
    GmailQueryMatch(query="from:amy after:2026/08/01 launch", rung=RungId.L2),
    Rfc822MsgId(message_id_header="<CAF9x8Q=launch-thread@mail.example>"),
    ReplyParentOf(child_id="msg-child-0091"),
    ReplyParentAmbiguous(
        child_id="msg-child-0091",
        message_id_header="<CAF9x8Q=resent-twice@mail.example>",
        matched_messages=2,
    ),
    ReplyChildOf(parent_id="msg-parent-0044"),
    ThreadMember(thread_id="thread-quarterly-review", position=17),
    SemanticScore(cosine=0.8712, model="bge-small-en-v1.5"),
    # Digits, not `"hist-99120034"`: R-SEC-032 gave this parameter Gmail's own shape, so a
    # `historyId`-looking-but-not is no longer constructible. The value is still distinctive
    # enough for the participation and placement tests below to see it move.
    HistoryAddition(history_id="99120034"),
    RecencyContext(
        history_id="99120034",
        rechecked=(RecheckedOperator.PARTICIPANT, RecheckedOperator.DATE),
    ),
    RequestedById(requested_id="msg-requested-0007"),
    SnippetContains(term="legal has not signed off"),
    WindowOffset(offset=-3, anchor_id="msg-anchor-0500"),
    # WS-11. Two components rather than one, so `mutate` has something to drop and the
    # rendered list is visibly a list; a single-component fill is legal and is what most
    # filled rows carry.
    QueryScoredFill(
        components=(FillComponent.PARTICIPANT_MATCH, FillComponent.TERM_OVERLAP),
        score=9,
    ),
    FloorPromoted(
        relation=FloorRelation.PARENT,
        anchor_id="msg-evidence-0012",
        dependence=FloorDependence.QUOTATION,
    ),
)

IDS = [variant.kind.value for variant in VARIANTS]

#: Words a reason may not be made of. PART-07's own examples of a decorative rationale.
DECORATIVE = ("relevant", "you may find this useful", "interesting", "important", "related")


def mutate(reason: Reason, field: str, value: Any) -> Any:
    if isinstance(value, tuple):
        # WS-11's `QueryScoredFill.components` is the first sequence-valued parameter any
        # reason carries. A sequence participates in its rendering exactly when *dropping a
        # member changes the string*, which is the same question this function asks of every
        # other type; the one-member case appends instead, because a reason with an empty
        # component list is unconstructible by design.
        member = value[0]
        changed = (
            value[:-1]
            if len(value) > 1
            else (*value, next(other for other in type(member) if other is not member))
        )
        return reason.model_copy(update={field: changed})
    if isinstance(value, Enum):
        other = next(member for member in type(value) if member is not value)
        return reason.model_copy(update={field: other})
    if isinstance(value, str):
        return reason.model_copy(update={field: value + "-changed"})
    if isinstance(value, bool):  # pragma: no cover - no reason carries a bool today
        return reason.model_copy(update={field: not value})
    if isinstance(value, int):
        return reason.model_copy(update={field: value + 1})
    if isinstance(value, float):  # pragma: no cover - cosine is the only float, an int-safe path
        return reason.model_copy(update={field: value + 0.5})
    return None


# --- completeness -------------------------------------------------------------------------


def test_every_reason_kind_has_a_variant_under_test() -> None:
    """The mechanism against this finding coming back: a new kind must arrive with a test."""
    assert {variant.kind for variant in VARIANTS} == set(ReasonKind) == ALL_REASON_KINDS
    assert len(VARIANTS) == len(ReasonKind)


# --- render ---------------------------------------------------------------------------------


@pytest.mark.parametrize("reason", VARIANTS, ids=IDS)
def test_every_reason_renders_a_non_empty_mechanical_string(reason: Reason) -> None:
    rendered = reason.render()
    assert rendered.strip(), f"{reason.kind.value} renders nothing"
    assert rendered == rendered.strip()
    lowered = rendered.lower()
    for word in DECORATIVE:
        assert word not in lowered, f"{reason.kind.value} renders a decorative rationale"


@pytest.mark.parametrize("reason", VARIANTS, ids=IDS)
def test_every_parameter_of_every_reason_participates_in_its_rendering(reason: Reason) -> None:
    """A renderer that ignores a parameter, or returns a constant, fails here.

    `kind` is excluded because it is the discriminator, not evidence; every other field is
    something the reason claims about the message, and a claim that does not reach the
    string an agent reads is a claim the agent cannot check.
    """
    fields = {name: value for name, value in reason if name != "kind"}
    assert fields, f"{reason.kind.value} carries no parameters at all"
    baseline = reason.render()
    for name, value in fields.items():
        changed = mutate(reason, name, value)
        assert changed is not None, f"{reason.kind.value}.{name} has an untestable type"
        assert changed.render() != baseline, (
            f"{reason.kind.value} renders the same string with {name} changed from "
            f"{value!r} to {getattr(changed, name)!r}: the parameter is not in the output"
        )


#: Which caption introduces which parameter in a rendered reason. This is a statement about
#: *meaning* - the number after "position" is the position, the name after "thread" is the
#: thread - and it is deliberately not a copy of any format string: it names one word per
#: field and says nothing about the rest of the sentence.
#:
#: R-ARCH-018: the participation test above asks only "does changing this field change the
#: output", which a renderer that puts the right values in the wrong places satisfies. R-ARCH
#: swapped `position` and `thread_id` in `ThreadMember.render()` - a real mislabelling, not a
#: no-op - and all 50 tests passed. An agent reading "position thread-quarterly-review of
#: thread 17" is being told something false about the message.
CAPTIONS: dict[ReasonKind, dict[str, str]] = {
    ReasonKind.GMAIL_QUERY_MATCH: {"rung": "at", "query": ":"},
    ReasonKind.RFC822_MSGID: {"message_id_header": "rfc822msgid"},
    ReasonKind.REPLY_PARENT_OF: {"child_id": "of"},
    ReasonKind.REPLY_PARENT_AMBIGUOUS: {
        "child_id": "of",
        "message_id_header": "Message-ID",
        "matched_messages": "by",
    },
    ReasonKind.REPLY_CHILD_OF: {"parent_id": "of"},
    ReasonKind.THREAD_MEMBER: {"position": "position", "thread_id": "thread"},
    ReasonKind.SEMANTIC_SCORE: {"cosine": "cosine", "model": "model"},
    ReasonKind.HISTORY_ADDITION: {"history_id": "historyId"},
    ReasonKind.RECENCY_CONTEXT: {"history_id": "since", "rechecked": "re-checked locally"},
    ReasonKind.REQUESTED_BY_ID: {"requested_id": "id"},
    ReasonKind.SNIPPET_CONTAINS: {"term": "contains"},
    ReasonKind.WINDOW_OFFSET: {"offset": "window", "anchor_id": "around"},
    ReasonKind.QUERY_SCORE_FILL: {"score": "score", "components": "from"},
    ReasonKind.FLOOR_PROMOTED: {
        "relation": "reply",
        "anchor_id": "of",
        "dependence": "it",
    },
}

#: What may sit between a caption and the value it introduces: whitespace and the punctuation
#: a renderer uses to set a value off. Anything else means the caption introduces something
#: other than that value. `[` joined the set with `RecencyContext`, whose rendered list is
#: bracketed in AD D.9's own verbatim sentence - `constraints re-checked locally: [from,
#: after]` - so a renderer setting a *list* off is setting a value off like any other.
_BETWEEN = r"[\s:'\",\[]*"


def rendered_position_of(reason: Reason, field: str, caption: str) -> bool:
    """Whether `caption` introduces `field`'s value in this reason's rendered string.

    Floats are matched by value rather than by text, because a renderer may legitimately
    round (`cosine` renders to two places); everything else must appear as written, which is
    what makes a swapped placement visible.
    """
    rendered = reason.render()
    value = getattr(reason, field)
    if isinstance(value, tuple):
        # A sequence-valued parameter is *placed* when the caption introduces its first
        # member; that its later members matter is the participation test's question, and
        # asserting the joined form here would copy the renderer's separator into the table,
        # which is the one thing this table is written not to do.
        first = value[0]
        head = first.value if isinstance(first, Enum) else str(first)
        return re.search(rf"{re.escape(caption)}{_BETWEEN}{re.escape(head)}", rendered) is not None
    if isinstance(value, float):
        found = re.search(rf"{re.escape(caption)}{_BETWEEN}(-?\d+(?:\.\d+)?)", rendered)
        return found is not None and abs(float(found.group(1)) - value) < 0.01
    text = value.value if isinstance(value, Enum) else str(value)
    return re.search(rf"{re.escape(caption)}{_BETWEEN}{re.escape(text)}", rendered) is not None


def test_every_parameter_of_every_reason_has_a_declared_caption() -> None:
    """A new kind, or a new field on an existing one, arrives with a placement statement.

    Without this the table below silently stops covering what it is named for - which is the
    same "the mechanism exists but nothing keeps it complete" shape R-DISC-004 filed.
    """
    assert set(CAPTIONS) == set(ReasonKind)
    for variant in VARIANTS:
        fields = {name for name, _ in variant if name != "kind"}
        assert fields == set(CAPTIONS[variant.kind]), (
            f"{variant.kind.value}: fields {sorted(fields)} but captions "
            f"{sorted(CAPTIONS[variant.kind])}"
        )


@pytest.mark.parametrize("reason", VARIANTS, ids=IDS)
def test_every_parameter_is_rendered_in_the_place_that_names_it(reason: Reason) -> None:
    """R-ARCH-018: participation is not placement. Both are asserted, separately.

    The captions are an independent statement of which parameter is which, so a renderer
    that emits both values in the wrong order fails here while still passing every
    participation, distinctness and round-trip check.
    """
    for field, caption in CAPTIONS[reason.kind].items():
        assert rendered_position_of(reason, field, caption), (
            f"{reason.kind.value}: {field}={getattr(reason, field)!r} is not the value "
            f"introduced by {caption!r} in {reason.render()!r}"
        )


def test_the_placement_check_catches_the_swap_that_passed_all_fifty_tests() -> None:
    """R-ARCH's own probe, kept as a test rather than as a claim about a test.

    A renderer with `position` and `thread_id` traded still changes its output when either
    field changes, still renders a distinct non-decorative string, and still round-trips -
    so every other test in this module passes. This is the one that does not, which is what
    makes the placement assertion load-bearing rather than decorative itself.

    **Written as a twin rather than as a subclass since round 14.** It used to subclass
    `ThreadMember`, and a model that reaches the wire may no longer be extended: a subclass of
    one replaces the reader that re-establishes the response's invariants, which is what
    R-ARCH-033 was filed for. The probe is about a *renderer* with two parameters traded, and a
    twin declaring the same fields on the same fieldless base is exactly that - it just cannot
    also be substituted into a payload.
    """

    class SwappedThreadMember(_ReasonBase):
        kind: Literal[ReasonKind.THREAD_MEMBER] = ReasonKind.THREAD_MEMBER
        thread_id: ReasonScalar
        position: int = Field(ge=0)

        def render(self) -> str:
            return f"thread map row: position {self.thread_id} of thread {self.position}"

    swapped = SwappedThreadMember(thread_id="thread-quarterly-review", position=17)
    honest = ThreadMember(thread_id="thread-quarterly-review", position=17)

    # It passes participation: every field still reaches the output. `swapped` is a twin of
    # `ThreadMember` rather than a member of the `Reason` union, so the two helpers are called
    # through `Any` - they are duck-typed over `render()` and `getattr`, which is what makes
    # the probe possible at all.
    probe: Any = swapped
    for name, value in ((name, value) for name, value in swapped if name != "kind"):
        assert mutate(probe, name, value).render() != swapped.render()
    # And it fails placement, on both of the two fields it traded.
    for field, caption in CAPTIONS[ReasonKind.THREAD_MEMBER].items():
        assert rendered_position_of(honest, field, caption)
        assert not rendered_position_of(probe, field, caption)


def test_two_reasons_of_different_kinds_never_render_the_same_string() -> None:
    """PART-07's degenerate strategy - one constant reason everywhere - is visible."""
    rendered = [variant.render() for variant in VARIANTS]
    assert len(set(rendered)) == len(rendered)


@pytest.mark.parametrize("reason", VARIANTS, ids=IDS)
def test_the_rendered_reason_and_the_typed_detail_both_reach_the_wire(reason: Reason) -> None:
    """AD D.2 carries the string; `reason_detail` is what a harness joins on."""
    nonce = mint_nonce()
    row = MessageRow(
        mailbox=MailboxProvenance.of(("INBOX",)),
        id="m1",
        # A thread_member reason renders the row's own position, and since R-DISC-011 the
        # row refuses a reason that renders a different one, so the row is built where the
        # reason says it is rather than at an unrelated slot.
        position=reason.position if isinstance(reason, ThreadMember) else 0,
        role=Role.MATCHED,
        reason=reason,
        depth=Depth.BODY_CLEAN,
        unabridged=kit.unabridged("m1"),
        content=Content(
            trust=Trust.UNTRUSTED_THIRD_PARTY,
            source=ContentSource.GMAIL_BODY,
            text=fence(nonce, "body"),
        ),
        linkage=Linkage.HEADERS_UNOBSERVED,
    )
    wire = row.model_dump(mode="json")
    assert wire["reason"] == reason.render()
    assert wire["reason_detail"]["kind"] == reason.kind.value
    for name, _ in reason:
        if name == "kind":
            continue
        assert name in wire["reason_detail"], f"{name} is not on the wire"
    assert row.rendered_reason == reason.render()


@pytest.mark.parametrize("reason", VARIANTS, ids=IDS)
def test_every_reason_round_trips_through_the_discriminated_union(reason: Reason) -> None:
    """A kind that serialises but cannot be read back is a kind no harness can use."""
    row = MessageRow(
        mailbox=MailboxProvenance.of(("INBOX",)),
        id="m1",
        position=reason.position if isinstance(reason, ThreadMember) else 0,
        role=Role.MATCHED,
        reason=reason,
        depth=Depth.STUB,
        unabridged=kit.unabridged("m1"),
        linkage=Linkage.HEADERS_UNOBSERVED,
    )
    wire = row.model_dump(mode="json")
    # `reason_detail` is a computed field: it is on the wire for a harness to join on, and
    # the model refuses it as an input, which is itself the right shape - a caller cannot
    # supply a detail block that disagrees with the reason.
    wire.pop("reason_detail")
    # `mailbox.regions` and `mailbox.outside_the_default_mailbox` are computed for the same
    # reason and are refused as inputs for the same reason: a caller cannot hand the model a
    # provenance that disagrees with the labels the model reports (OD-5).
    wire["mailbox"] = {
        key: value for key, value in wire["mailbox"].items() if key in {"observed", "labels"}
    }
    restored = MessageRow.model_validate({**wire, "reason": reason.model_dump(mode="json")})
    assert restored.reason == reason
    assert restored.reason.render() == reason.render()


def test_a_reason_of_the_wrong_shape_for_its_kind_is_refused() -> None:
    """The union discriminates on `kind`; the parameters are not interchangeable."""
    with pytest.raises(ValidationError):
        MessageRow.model_validate(
            {
                "id": "m1",
                "thread_id": "t1",
                "position": 0,
                "role": "matched",
                "reason": {"kind": "reply_parent_of", "parent_id": "m2"},  # wrong field
                "depth": "stub",
                "unabridged": {"tool": "mailweave_get_messages", "args": {"message_ids": ["m1"]}},
            }
        )


# --- OD-3: the reply-chain floor, end to end -------------------------------------------------


def floor_envelope() -> Any:
    """A matched message with its reply parent and child present as stubs.

    OD-3's decided shape: membership is guaranteed, depth is earned. The parent and child
    are *disclosed* - they are rows in the response, with a role saying why they are here
    and an affordance saying how to get the rest - not withheld records and not a count.
    """
    ledger = DispositionLedger()
    ledger.record_list_page(kit.fetched(["m14"]), rung=RungId.L1, query="subject:launch")
    ledger.record_thread(kit.observed_thread(["m12", "m14", "m20"], thread_id="t1"), rung=RungId.L1)
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    nonce = builder.fence_nonce

    reversal = MessageRow(
        mailbox=MailboxProvenance.of(("INBOX",)),
        id="m14",
        position=13,
        role=Role.MATCHED,
        reason=SnippetContains(term="legal has not signed off"),
        depth=Depth.BODY_CLEAN,
        unabridged=kit.unabridged("m14"),
        content=Content(
            trust=Trust.UNTRUSTED_THIRD_PARTY,
            source=ContentSource.GMAIL_BODY,
            text=fence(nonce, "hold - legal has not signed off on the launch date"),
        ),
        linkage=Linkage.HEADERS_UNOBSERVED,
    )
    parent = MessageRow(
        mailbox=MailboxProvenance.of(("INBOX",)),
        id="m12",
        position=11,
        role=Role.PARENT,
        reason=ReplyParentOf(child_id="m14"),
        depth=Depth.STUB,
        unabridged=kit.unabridged("m12"),
        linkage=Linkage.HEADERS_UNOBSERVED,
    )
    child = MessageRow(
        mailbox=MailboxProvenance.of(("INBOX",)),
        id="m20",
        position=19,
        role=Role.CHILD,
        reason=ReplyChildOf(parent_id="m14"),
        depth=Depth.STUB,
        unabridged=kit.unabridged("m20"),
        linkage=Linkage.HEADERS_UNOBSERVED,
    )
    builder.add_source(
        Source(
            thread_id="t1",
            stated_total=42,
            included=3,
            included_as_stub=2,
            fetched_at=kit.FETCHED_AT,
            messages=(parent, reversal, child),
        )
    )
    builder.add_affordance(kit.thread_affordance("t1"))
    return builder.build(
        outcome=Outcome.ANSWERED,
        rungs=(RungId.L1,),
        sufficiency=Sufficiency.SUFFICIENT,
        counters=kit.counters(),
    )


def test_the_od3_reply_chain_floor_shape_builds_end_to_end() -> None:
    """R-DISC-004's second half: the round's headline capability, exercised by a test."""
    envelope = floor_envelope()
    assert envelope.disclosed_ids == {"m12", "m14", "m20"}
    assert envelope.withheld == ()
    assert envelope.partial is True  # 3 of 42 stated


def test_the_floor_members_are_disclosed_rows_not_withheld_records() -> None:
    """A.7a's confusion, named: a stub is present at a shallow depth, not absent."""
    envelope = floor_envelope()
    stubs = {
        row.id for source in envelope.sources for row in source.messages if row.depth is Depth.STUB
    }
    assert stubs == {"m12", "m20"}
    assert stubs & envelope.withheld_ids == set()
    assert stubs <= envelope.disclosed_ids


def test_each_floor_member_says_why_it_is_here_and_how_to_get_the_rest() -> None:
    """Role answers "why", depth answers "how much", the affordance answers "and then?"."""
    envelope = floor_envelope()
    rows = {row.id: row for source in envelope.sources for row in source.messages}
    assert rows["m12"].role is Role.PARENT
    assert rows["m20"].role is Role.CHILD
    assert "m14" in rows["m12"].rendered_reason
    assert "m14" in rows["m20"].rendered_reason
    for stub_id in ("m12", "m20"):
        assert rows[stub_id].unabridged.mentions(stub_id)
        assert rows[stub_id].unabridged.tool is ToolName.GET_MESSAGES


def test_role_and_depth_are_independent_so_a_parent_can_be_promoted() -> None:
    """OD-3: "structurally necessary parents are promoted to deeper content".

    Nothing in the schema pins `PARENT` to `STUB`; if it did, the promotion OD-3 decided on
    would be unexpressible and the floor would be a ceiling.
    """
    nonce = mint_nonce()
    promoted = MessageRow(
        mailbox=MailboxProvenance.of(("INBOX",)),
        id="m12",
        position=11,
        role=Role.PARENT,
        reason=ReplyParentOf(child_id="m14"),
        depth=Depth.BODY_CLEAN,
        unabridged=kit.unabridged("m12"),
        content=Content(
            trust=Trust.UNTRUSTED_THIRD_PARTY,
            source=ContentSource.GMAIL_BODY,
            text=fence(nonce, "we are shipping on the 14th"),
        ),
        linkage=Linkage.HEADERS_UNOBSERVED,
    )
    assert promoted.role is Role.PARENT
    assert promoted.depth is Depth.BODY_CLEAN


def test_a_stub_row_carrying_a_body_is_refused() -> None:
    """The other direction: `role=stub` may not smuggle content past the depth field."""
    with pytest.raises(ValidationError):
        MessageRow(
            mailbox=MailboxProvenance.of(("INBOX",)),
            id="m12",
            position=11,
            role=Role.STUB,
            reason=ReplyParentOf(child_id="m14"),
            depth=Depth.BODY_CLEAN,
            unabridged=kit.unabridged("m12"),
            content=Content(
                trust=Trust.UNTRUSTED_THIRD_PARTY,
                source=ContentSource.GMAIL_BODY,
                text=fence(mint_nonce(), "body"),
            ),
            linkage=Linkage.HEADERS_UNOBSERVED,
        )


def test_the_floor_survives_serialisation_with_its_reasons_intact() -> None:
    """PART-07 grades what an agent reads, which is the wire form, not the object."""
    envelope = floor_envelope()
    wire = envelope.model_dump(mode="json")
    rows = {row["id"]: row for row in wire["sources"][0]["messages"]}
    assert rows["m12"]["reason"] == ReplyParentOf(child_id="m14").render()
    assert rows["m20"]["reason_detail"] == {"kind": "reply_child_of", "parent_id": "m14"}
    assert rows["m12"]["content"] is None
    assert rows["m14"]["depth"] == "body_clean"


def test_every_role_in_the_closed_set_is_carried_by_a_row_that_builds() -> None:
    """PART-07 scores all seven roles; round 1 only checked the enum had seven members."""
    nonce = mint_nonce()
    built = set()
    for index, role in enumerate(Role):
        depth = Depth.STUB if role is Role.STUB else Depth.BODY_CLEAN
        content = (
            None
            if depth is Depth.STUB
            else Content(
                trust=Trust.UNTRUSTED_THIRD_PARTY,
                source=ContentSource.GMAIL_BODY,
                text=fence(nonce, "body"),
            )
        )
        row = MessageRow(
            mailbox=MailboxProvenance.of(("INBOX",)),
            id=f"m{index}",
            position=index,
            role=role,
            reason=RequestedById(requested_id=f"m{index}"),
            depth=depth,
            unabridged=Affordance(tool=ToolName.GET_MESSAGES, args={"message_ids": [f"m{index}"]}),
            content=content,
            linkage=Linkage.HEADERS_UNOBSERVED,
        )
        built.add(row.role)
    assert built == set(Role)
