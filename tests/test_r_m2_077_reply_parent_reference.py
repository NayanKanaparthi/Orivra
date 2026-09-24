"""R-M2-077: a reply can be fetched without its ancestors, and still names its parent.

`mailweave_get_messages` raised for every reply whose parent was not also in the response.
`surface/expansion.py::_rows_of` cleared `reply_parent_id` whenever the parent was not a
*row* of this response - while `linkage` still said a parent had been found - and
`MessageRow` refused the pair under C-02a. The ladder collapses every non-requested message
of a long thread into a run, so the parent was never a row, so every reply raised: by id, by
map position, at every content view. The harness's recovery driver swallowed the raise and
scored it as "expansion reached nothing" (M2 diagnostic, 2026-09-13).

The repair keeps the distinction the owner asked to keep. **A parent is referenced when this
source accounts for it** - as a row, a collapsed-run member, or a withheld record with an
affordance - and **its content is disclosed only when it is a row with content.** These tests
hold both halves at once: the reply names its parent, and the parent's body is not here.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mailweave.envelope.vocab import Depth, Linkage
from mailweave.envelope.wire import Source
from mailweave.surface.arguments import parse_get_messages, parse_thread_map
from mailweave.surface.service import MailweaveService
from tests.fixtures import envelope_kit as kit
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.test_mcp_surface_round24 import make_service

#: Long enough that the A.9a ladder collapses the non-requested messages into a run, which
#: is the shape every real `get_messages` on a long thread has and the shape that raised.
THREAD_LENGTH = 40
WORDS = ("brillig", "slithy", "toves", "outgrabe", "mimsy", "borogrove", "mome", "raths")


def _long_thread(length: int = THREAD_LENGTH) -> SyntheticMailbox:
    subject = "cadence review"
    rows = [
        Msg(
            id=f"r-m{index:03d}",
            thread_id="r-th",
            sender=f"a{index % 3}@team.example",
            subject=subject if index == 0 else f"Re: {subject}",
            body=f"message {index} " + " ".join(WORDS[(index + k) % len(WORDS)] for k in range(60)),
            internal_date_ms=epoch_ms(2026, 8, 1) + index * 3_600_000,
            to=("r0@team.example",),
            in_reply_to=(f"<r-m{index - 1:03d}@mail.invalid>" if index else None),
        )
        for index in range(length)
    ]
    return SyntheticMailbox(messages=tuple(rows), now_ms=epoch_ms(2026, 9, 3))


@pytest.fixture
def service() -> MailweaveService:
    return make_service(_long_thread())


def _only_source(envelope):
    assert len(envelope.sources) == 1, [source.thread_id for source in envelope.sources]
    return envelope.sources[0]


def _row(source: Source, message_id: str):
    return next(row for row in source.messages if row.id == message_id)


# --- direct message-id reads -------------------------------------------------------------


@pytest.mark.parametrize("view", ["body_clean", "body_full", "snippet"])
def test_a_reply_fetched_by_id_names_its_parent_and_does_not_disclose_it(
    service: MailweaveService, view: str
) -> None:
    """The failing call, at every content view: position 7, ancestors not requested."""
    envelope = service.get_messages(
        parse_get_messages({"message_ids": ["r-m007"], "view": view})
    )
    source = _only_source(envelope)
    row = _row(source, "r-m007")
    # Referenced: the link is real and it names its parent.
    assert row.linkage is Linkage.IN_REPLY_TO
    assert row.reply_parent_id == "r-m006"
    # Accounted for, so the reference is followable: a row, a run member, or withheld.
    assert "r-m006" in source.disclosed_ids | frozenset(source.withheld_here)
    # Not disclosed: the parent's content is not in this response.
    parent_rows = [one for one in source.messages if one.id == "r-m006"]
    assert all(one.content is None for one in parent_rows), "the parent's body was disclosed"
    # And the requested message is the only one carrying content.
    carrying = [one.id for one in source.messages if one.content is not None]
    assert carrying == ["r-m007"]


def test_two_replies_with_a_gap_between_them_both_name_their_parents(
    service: MailweaveService,
) -> None:
    """Position 4 and position 9, neither parent requested. Before: raised on the first."""
    envelope = service.get_messages(
        parse_get_messages({"message_ids": ["r-m004", "r-m009"], "view": "body_clean"})
    )
    source = _only_source(envelope)
    assert _row(source, "r-m004").reply_parent_id == "r-m003"
    assert _row(source, "r-m009").reply_parent_id == "r-m008"
    assert {one.id for one in source.messages if one.content is not None} == {"r-m004", "r-m009"}


def test_the_root_is_unchanged(service: MailweaveService) -> None:
    envelope = service.get_messages(parse_get_messages({"message_ids": ["r-m000"], "view": "body_clean"}))
    row = _row(_only_source(envelope), "r-m000")
    assert row.linkage is Linkage.NO_REPLY_HEADERS
    assert row.reply_parent_id is None


# --- map-position reads ------------------------------------------------------------------


@pytest.mark.parametrize("view", ["body_clean", "snippet"])
def test_a_reply_fetched_by_map_position_names_its_parent_and_does_not_disclose_it(
    service: MailweaveService, view: str
) -> None:
    """The second hop a reader takes after a thread map, which is the hop that raised."""
    mapped = service.thread_map(parse_thread_map({"thread_id": "r-th"}))
    map_id = _only_source(mapped).map_id
    assert map_id, "the map minted no handle, so positions cannot be read against it"
    envelope = service.get_messages(
        parse_get_messages({"map_id": map_id, "positions": [31], "view": view})
    )
    source = _only_source(envelope)
    row = _row(source, "r-m031")
    assert row.linkage is Linkage.IN_REPLY_TO
    assert row.reply_parent_id == "r-m030"
    assert "r-m030" in source.disclosed_ids | frozenset(source.withheld_here)
    assert [one.id for one in source.messages if one.content is not None] == ["r-m031"]


def test_the_map_itself_still_accounts_for_every_position(service: MailweaveService) -> None:
    """R-06 is untouched: the repair widened what a *reference* may point at, not a map."""
    mapped = service.thread_map(parse_thread_map({"thread_id": "r-th"}))
    source = _only_source(mapped)
    assert source.accounted_for == source.stated_total == THREAD_LENGTH


# --- the wire contract, held at the model ------------------------------------------------


def test_a_source_accepts_a_parent_it_withholds_and_refuses_one_it_never_names() -> None:
    """`Source` distinguishes accounting for a parent from disclosing it.

    A parent in `withheld_here` is referenced - its record carries the call that fetches it -
    and its content is absent, and the source is valid. A parent named nowhere in the source
    is still refused: that is the boundary C-02a exists to hold.
    """
    nonce = "n" * 12
    child = kit.row(
        "c1", "t1", 1, nonce=nonce,
        linkage=Linkage.IN_REPLY_TO, reply_parent_id="p0", can_be_a_parent=True,
    )
    referenced = Source(
        thread_id="t1", stated_total=2, included=1, included_as_stub=0,
        fetched_at=kit.FETCHED_AT, messages=(child,), withheld_here=("p0",),
    )
    assert referenced.messages[0].reply_parent_id == "p0"
    assert "p0" not in referenced.disclosed_ids
    with pytest.raises(ValidationError) as refused:
        Source(
            thread_id="t1", stated_total=2, included=1, included_as_stub=0,
            fetched_at=kit.FETCHED_AT, messages=(child,),
        )
    assert "neither carries nor withholds" in str(refused.value)


def test_a_withheld_parent_is_not_a_disclosed_one() -> None:
    """The other half of the distinction, as a rule and not a coincidence of the fixture."""
    nonce = "n" * 12
    child = kit.row(
        "c1", "t1", 1, nonce=nonce, depth=Depth.BODY_CLEAN,
        linkage=Linkage.IN_REPLY_TO, reply_parent_id="p0", can_be_a_parent=True,
    )
    source = Source(
        thread_id="t1", stated_total=2, included=1, included_as_stub=0,
        fetched_at=kit.FETCHED_AT, messages=(child,), withheld_here=("p0",),
    )
    assert source.accounted_for == 2
    assert {row.id for row in source.messages if row.content is not None} == {"c1"}
