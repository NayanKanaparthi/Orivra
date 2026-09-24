"""The graph-reason extension is additive in Orivra and invisible in MailWeave.

`EvidenceNode.reason` widened from MailWeave's closed `Reason` union to `Reason | GraphReason`
so a `PERSON` node - which MailWeave never returns a row for and has no vocabulary to
describe - can say why it is in the graph. This file is the compatibility half of that change:
every claim the widening rests on, asserted rather than asserted-about.

The one that matters most is `test_mailweaves_own_wire_refuses_a_graph_reason`. A union
widened in one direction is only safe if it is widened in *one* direction, and the way that
goes wrong is silently: nothing errors, a graph reason reaches a `MessageRow`, and a Gmail
caller receives a `kind` its schema never declared.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from mailweave.envelope.reasons import (
    ALL_REASON_KINDS,
    GmailQueryMatch,
    ReasonKind,
    RungId,
    ThreadMember,
)
from mailweave.envelope.vocab import Depth, Linkage, Role
from mailweave.envelope.wire import Affordance, MailboxProvenance, MessageRow
from orivra.contracts import (
    ALL_GRAPH_REASON_KINDS,
    EvidenceNode,
    GraphReasonKind,
    NodeKind,
    ParticipantIn,
    RefKind,
)
from tests.orivra_build import fresh, reference

ADDRESS = "ana@team.example"
THREAD = "t-vendor"


def _person(**kwargs: object) -> EvidenceNode:
    fields: dict[str, object] = {
        "node_id": f"gmail/person/{ADDRESS}",
        "ref": reference(ADDRESS, kind=RefKind.PERSON),
        "kind": NodeKind.PERSON,
        "role": Role.CONTEXT,
        "reason": ParticipantIn(address=ADDRESS, thread_id=THREAD, roles=("authored",)),
        "depth": Depth.STUB,
        "freshness": fresh(),
    }
    fields.update(kwargs)
    return EvidenceNode(**fields)  # type: ignore[arg-type]


# -- the two vocabularies cannot collide -----------------------------------------------------


def test_the_two_reason_vocabularies_are_disjoint() -> None:
    """Namespacing is the guarantee, not a convention: MailWeave's kinds are bare identifiers
    and Orivra's carry an `orivra.` prefix, so a discriminated union over both stays
    unambiguous however either side grows, without either knowing about the other."""
    mailweave = {kind.value for kind in ALL_REASON_KINDS}
    graph = {kind.value for kind in ALL_GRAPH_REASON_KINDS}
    assert graph
    assert not (mailweave & graph)
    assert all(kind.startswith("orivra.") for kind in graph)
    assert not any(kind.startswith("orivra.") for kind in mailweave)


def test_mailweaves_reason_vocabulary_did_not_change() -> None:
    """The fourteen, by name. A test that counted them would pass a rename."""
    assert {kind.value for kind in ALL_REASON_KINDS} == {
        "gmail_query_match",
        "rfc822msgid",
        "reply_parent_of",
        "reply_parent_ambiguous",
        "reply_child_of",
        "thread_member",
        "semantic_score",
        "history_addition",
        "recency_context",
        "requested_by_id",
        "snippet_contains",
        "window_offset",
        "query_score_fill",
        "floor_promoted",
    }
    assert GraphReasonKind.PARTICIPANT_IN.value not in {k.value for k in ALL_REASON_KINDS}


# -- the widening goes one way ---------------------------------------------------------------


def test_a_node_still_accepts_every_mailweave_reason() -> None:
    """The regression the widening could cause and must not: a union that gained a member and
    lost one. Asserted on both a discriminated instance and a round-trip through validation."""
    for reason in (
        GmailQueryMatch(query="vendor", rung=RungId.L1),
        ThreadMember(thread_id=THREAD, position=2),
    ):
        node = _person(reason=reason, kind=NodeKind.MESSAGE, role=Role.MATCHED)
        assert node.reason == reason
        assert EvidenceNode.model_validate(node.model_dump()).reason == reason


def test_a_node_accepts_the_graph_reason_and_keeps_its_type_through_validation() -> None:
    node = _person()
    assert isinstance(node.reason, ParticipantIn)
    revalidated = EvidenceNode.model_validate(node.model_dump())
    assert isinstance(revalidated.reason, ParticipantIn)
    assert revalidated.reason.address == ADDRESS


def test_mailweaves_own_wire_refuses_a_graph_reason() -> None:
    """**The direction that must stay closed.** `MessageRow` is what a Gmail caller receives,
    and its `reason` is MailWeave's union. If widening Orivra's node had widened this too, a
    caller reading `mailweave_search` would get a `kind` the published schema never declared -
    and nothing would have errored to say so."""
    with pytest.raises(ValidationError):
        MessageRow(
            id="m-1",
            position=0,
            role=Role.MATCHED,
            reason=ParticipantIn(address=ADDRESS, thread_id=THREAD),  # type: ignore[arg-type]
            mailbox=MailboxProvenance(in_mailbox=True, labels_observed=True),
            depth=Depth.STUB,
            linkage=Linkage.NO_REPLY_HEADERS,
            unabridged=Affordance(
                tool="mailweave_get_messages", arguments={"message_ids": ["m-1"]}
            ),
        )


# -- the parameters take the same discipline as MailWeave's ----------------------------------


def test_a_graph_reason_parameter_refuses_a_line_break() -> None:
    """R-SEC-032's rule, inherited rather than re-decided. An address is a string a sender
    influenced and it reaches a reader, so a multi-line value is content taking a metadata
    field's route to the wire - the same failure, at a field MailWeave's own sweep does not
    cover because the field is not MailWeave's."""
    for bad in ("ana@team.example\nX-Injected: yes", "ana @team.example"):
        with pytest.raises(ValidationError):
            ParticipantIn(address=bad, thread_id=THREAD)


def test_a_graph_reason_renders_a_single_mechanical_line() -> None:
    """Every reason renders; PART-07 wants the render mechanical rather than decorative."""
    rendered = ParticipantIn(
        address=ADDRESS, thread_id=THREAD, roles=("authored", "addressed")
    ).render()
    assert ADDRESS in rendered
    assert THREAD in rendered
    assert "authored" in rendered and "addressed" in rendered
    assert rendered.splitlines() == [rendered]


def test_a_graph_reason_is_frozen_and_forbids_unknown_fields() -> None:
    """It extends `_ReasonBase`, so it inherits the sealed config rather than restating it -
    and this asserts the inheritance actually took."""
    reason = ParticipantIn(address=ADDRESS, thread_id=THREAD)
    with pytest.raises(ValidationError):
        ParticipantIn(address=ADDRESS, thread_id=THREAD, smuggled="x")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        reason.address = "other@team.example"  # type: ignore[misc]


def test_the_discriminator_selects_the_graph_member_by_value_alone() -> None:
    """A union discriminated on a string only works if the string is the whole key. This
    validates from a plain dict, which is what a cached or serialised graph comes back as."""
    node = EvidenceNode.model_validate(
        {
            **_person().model_dump(),
            "reason": {
                "kind": GraphReasonKind.PARTICIPANT_IN.value,
                "address": ADDRESS,
                "thread_id": THREAD,
                "roles": ("authored",),
            },
        }
    )
    assert isinstance(node.reason, ParticipantIn)


def test_an_unknown_orivra_namespaced_kind_is_refused_rather_than_accepted_loosely() -> None:
    with pytest.raises(ValidationError):
        EvidenceNode.model_validate(
            {**_person().model_dump(), "reason": {"kind": "orivra.invented", "address": ADDRESS}}
        )


# -- the Gmail tool surface is untouched ------------------------------------------------------


def test_no_mailweave_tool_schema_mentions_the_graph_vocabulary() -> None:
    """The user-visible half: `mailweave_*` names and schemas are what a Gmail caller has
    already integrated against, and this change must be invisible to them."""
    from mailweave.surface.tools import GET_ATTACHMENT, GET_MESSAGES, SEARCH, THREAD_MAP

    specs = (SEARCH, THREAD_MAP, GET_MESSAGES, GET_ATTACHMENT)
    assert {spec.name.value for spec in specs} == {
        "mailweave_search",
        "mailweave_thread_map",
        "mailweave_get_messages",
        "mailweave_get_attachment",
    }, "a mailweave_* tool was renamed, which this change had no business doing"
    for spec in specs:
        blob = json.dumps(
            {
                "name": spec.name.value,
                "title": spec.title,
                "description": spec.description,
                "input_schema": spec.input_schema,
            },
            default=str,
        )
        assert "orivra." not in blob
        assert "participant_in" not in blob


def test_the_reason_kind_enum_is_not_reachable_from_mailweave_by_the_new_name() -> None:
    """A belt-and-braces check that the extension did not land in the wrong module: importing
    the graph kind from MailWeave must fail."""
    with pytest.raises((ImportError, AttributeError)):
        from mailweave.envelope.reasons import (
            GraphReasonKind,  # type: ignore[attr-defined] # noqa: F401
        )
    assert not hasattr(ReasonKind, "PARTICIPANT_IN")
