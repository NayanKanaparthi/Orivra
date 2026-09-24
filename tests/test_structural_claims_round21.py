"""Round 21 Part 0: the four things L4 and its neighbours said that were not true.

Everything here is a **claim** defect rather than a reconstruction defect, and that is the
shape of the round. R-RETR attacked WS-05's reply tree over 3,000 generated threads, thirteen
hand-built pathologies and all 24 array permutations and could not make it attach a message
to a parent its own headers do not name. Every over-claim it found was one level out: in what
`Link.evidence` carries, in what `assemble` does with the row L4 brought back, and in what
text the mention scanner is handed while the response reports the row as scanned.

Built like `tests/test_thread_map_round20.py` and standing on the same fixtures: the real
client, the real ledger, real URL construction and retry ladder, with `httpx.MockTransport`
where the socket would be and `tests/conftest.py` denying `socket.connect`.

Addresses use the reserved `.example` / `.invalid` TLDs (RFC 2606/6761) and every subject and
body is invented for the structural property the test is about; no fixture here is real or
realistic personal mail.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from mailweave.envelope import (
    Depth,
    DispositionLedger,
    Linkage,
    MailboxProvenance,
    MessageRow,
    Role,
    ToolName,
)
from mailweave.envelope.reasons import (
    ReasonKind,
    ReplyParentAmbiguous,
    ReplyParentOf,
    ThreadMember,
)
from mailweave.envelope.response import Envelope
from mailweave.gmail.client import GmailClient, StaticToken, _thread_scalars
from mailweave.gmail.meter import CallMeter
from mailweave.gmail.models import Message, Thread
from mailweave.gmail.retry import BackoffPolicy
from mailweave.net.egress import build_client
from mailweave.retrieval.assemble import UNPROBEABLE_IDENTIFIER_RUNG, assemble
from mailweave.retrieval.ladder import LadderRunner
from mailweave.structure.participants import ObservedText, addresses_in_text
from mailweave.structure.reply_tree import MessageHeaderView, reconstruct
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms

NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)
UTC_ZONE = ZoneInfo("UTC")
TOKEN = "ya29.synthetic-round-21-token"

#: The one term the query matches. Invented, like every other string here.
MARKER = "quillevant"
#: A second term matching a *different* row of one thread, so the same thread can be reached
#: at two disclosure depths.
OTHER = "sprindle"


def msgid(name: str) -> str:
    return f"<{name}@mail.invalid>"


def make_client(box: SyntheticMailbox) -> GmailClient:
    return GmailClient(
        token=StaticToken(TOKEN),
        http=build_client(inner=box.transport()),
        meter=CallMeter(),
        policy=BackoffPolicy(),
        sleeper=lambda _seconds: None,
        jitterer=lambda: 0.5,
    )


def answer(query: str, box: SyntheticMailbox) -> Envelope:
    client = make_client(box)
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run(query, now=NOW, zone=UTC_ZONE)
    return assemble(run, client=client, ledger=ledger)


def rows_of(envelope: Envelope, thread_id: str) -> dict[str, object]:
    source = next(s for s in envelope.sources if s.thread_id == thread_id)
    return {row.id: row for row in source.messages}


# --- R-RETR-049: L4 chased the thread root and called it the reply parent ------------------


def ancestry_mailbox() -> SyntheticMailbox:
    """A child whose `References` names three absent ancestors, each in its own thread.

    The shape a forward, a split thread or a list-expanded reply produces routinely: no
    `In-Reply-To`, and a `References` chain whose *rightmost* entry is the nearest ancestor.
    """
    return SyntheticMailbox(
        messages=(
            Msg(
                id="c1",
                thread_id="t-child",
                sender="Ana Ito <ana@team.example>",
                subject="Ordering the racks",
                body=f"the {MARKER} follow-up",
                internal_date_ms=epoch_ms(2026, 5, 10),
                references=f"{msgid('root')} {msgid('middle')} {msgid('near')}",
            ),
            Msg(
                id="r1",
                thread_id="t-root",
                sender="Bo Ng <bo@team.example>",
                subject="Ordering the racks",
                body="the first note of all",
                internal_date_ms=epoch_ms(2026, 5, 1),
                rfc822_message_id=msgid("root"),
            ),
            Msg(
                id="m1",
                thread_id="t-middle",
                sender="Cai Ode <cai@team.example>",
                subject="Re: Ordering the racks",
                body="a note in between",
                internal_date_ms=epoch_ms(2026, 5, 5),
                rfc822_message_id=msgid("middle"),
            ),
            Msg(
                id="n1",
                thread_id="t-near",
                sender="Dee Rho <dee@team.example>",
                subject="Re: Ordering the racks",
                body="the message this reply answers",
                internal_date_ms=epoch_ms(2026, 5, 9),
                rfc822_message_id=msgid("near"),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )


def test_the_id_an_unlinked_child_records_is_the_nearest_ancestor_its_headers_name() -> None:
    """R-RETR-049 at the unit: `References` is right-to-left for the gap as for the link.

    `reconstruct` resolves `References` right-to-left because the rightmost entry is the
    nearest ancestor, and its docstring says so. The id it recorded when nothing resolved was
    `(in_reply_to + references)[0]` - the *leftmost* entry, the thread root, and the last id
    the resolver would have tried. One field, read by the same rule as the branch above it.
    """
    view = MessageHeaderView(
        message_id="c1",
        rfc_message_id=msgid("c1"),
        in_reply_to=(),
        references=(msgid("root"), msgid("middle"), msgid("near")),
        headers_observed=True,
        reply_headers_present=True,
    )
    link = reconstruct([view]).links[0]
    assert link.linkage is Linkage.UNRESOLVED_PARENT
    assert link.evidence == msgid("near")

    # `In-Reply-To` still wins over `References` when both are present, because a child that
    # names its parent directly has named it: the rule is "the nearest ancestor this child's
    # own headers name", not "the last id in the last header".
    with_direct = MessageHeaderView(
        message_id="c2",
        rfc_message_id=msgid("c2"),
        in_reply_to=(msgid("direct"),),
        references=(msgid("root"), msgid("near")),
        headers_observed=True,
        reply_headers_present=True,
    )
    assert reconstruct([with_direct]).links[0].evidence == msgid("direct")


def test_l4_probes_for_the_parent_and_not_for_the_thread_root() -> None:
    """The same fix end to end, which is where the over-claim actually was.

    The recovered row is disclosed as *"reply parent of c1"*, so which thread L4 goes to is
    the difference between a true statement and a false one. Three ancestors are present in
    three separate threads and only the nearest is the parent; before this round the probe
    went to the root, brought back a message three hops up, and called it the parent.
    """
    box = ancestry_mailbox()
    envelope = answer(MARKER, box)
    probes = [query for query, _spam in box.queries if "rfc822msgid:" in query]
    assert probes == [f"rfc822msgid:{msgid('near')}"], probes

    disclosed = {source.thread_id for source in envelope.sources}
    assert disclosed == {"t-child", "t-near"}, disclosed
    assert "t-root" not in disclosed and "t-middle" not in disclosed

    recovered = rows_of(envelope, "t-near")["n1"]
    assert recovered.role is Role.PARENT  # type: ignore[attr-defined]
    assert recovered.reason == ReplyParentOf(child_id="c1")  # type: ignore[attr-defined]
    # And the child's own row is unchanged and still honest: its parent is not in its thread.
    child = rows_of(envelope, "t-child")["c1"]
    assert child.linkage is Linkage.UNRESOLVED_PARENT  # type: ignore[attr-defined]
    assert child.reply_parent_id is None  # type: ignore[attr-defined]


# --- R-RETR-050: one Message-ID in two threads produced two parents for one child ----------


def duplicated_identifier_mailbox() -> SyntheticMailbox:
    """One `Message-ID` carried by messages in two threads - a resend, or a list copy."""
    return SyntheticMailbox(
        messages=(
            Msg(
                id="c1",
                thread_id="t-child",
                sender="Ana Ito <ana@team.example>",
                subject="Rack order",
                body=f"the {MARKER} follow-up",
                internal_date_ms=epoch_ms(2026, 5, 10),
                in_reply_to=msgid("twice"),
            ),
            Msg(
                id="x1",
                thread_id="t-copy-x",
                sender="Bo Ng <bo@team.example>",
                subject="Rack order",
                body="the sender's own copy",
                internal_date_ms=epoch_ms(2026, 5, 9),
                rfc822_message_id=msgid("twice"),
            ),
            Msg(
                id="y1",
                thread_id="t-copy-y",
                sender="Bo Ng <bo@team.example>",
                subject="Rack order",
                body="the list's copy of the same message",
                internal_date_ms=epoch_ms(2026, 5, 9),
                rfc822_message_id=msgid("twice"),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )


def test_one_child_is_never_told_it_has_two_reply_parents() -> None:
    """R-RETR-050: the refusal the reply tree makes inside a thread, applied across threads.

    `_resolve`'s docstring is the standard: *an id carried by two messages resolves to
    nothing: picking either would be a guess dressed as a link.* L4 walked around it by
    asking Gmail, and both returned rows were disclosed as `role: parent`, `reply parent of
    c1`. A child has one reply parent; a response asserting two has stopped being a reading
    of the headers.
    """
    box = duplicated_identifier_mailbox()
    envelope = answer(MARKER, box)
    recovered = [
        row
        for source in envelope.sources
        for row in source.messages
        if row.reason.kind in {ReasonKind.REPLY_PARENT_OF, ReasonKind.REPLY_PARENT_AMBIGUOUS}
    ]
    assert len(recovered) == 2, [row.id for row in recovered]
    assert [row.reason.kind for row in recovered] == [ReasonKind.REPLY_PARENT_AMBIGUOUS] * 2
    assert {row.role for row in recovered} == {Role.CONTEXT}
    for row in recovered:
        assert row.reason == ReplyParentAmbiguous(
            child_id="c1", message_id_header=msgid("twice"), matched_messages=2
        )
        # The ambiguity is a typed parameter, not a sentence: an agent branches on the count.
        assert row.reason_detail["matched_messages"] == 2
    assert not any(
        row.role is Role.PARENT for source in envelope.sources for row in source.messages
    )


def test_an_identifier_that_matches_once_is_still_the_parent_it_always_was() -> None:
    """The other side of the same rule, so the fix is not "never say parent again"."""
    box = ancestry_mailbox()
    envelope = answer(MARKER, box)
    row = rows_of(envelope, "t-near")["n1"]
    assert row.reason.kind is ReasonKind.REPLY_PARENT_OF  # type: ignore[attr-defined]


# --- R-RETR-051 / 052: what the mention scanner is handed, and whether it is whole ---------


def quoted_mention_mailbox() -> SyntheticMailbox:
    """Two rows of one thread, each matching a different term, one quoting an address.

    The commonest mention shape in real mail - an address inside a quoted reply - and the
    shape that makes the participant index a function of the query: whichever row the query
    matched is the row whose body gets fetched.
    """
    return SyntheticMailbox(
        messages=(
            Msg(
                id="w1",
                thread_id="t-quote",
                sender="Ana Ito <ana@team.example>",
                subject="Rack order",
                body=(
                    f"Agreed {MARKER}, let us ship on Friday.\n\n"
                    "On Tue, 2 Jun 2026, Cai wrote:\n"
                    "> please loop in cai@team.example before we commit"
                ),
                internal_date_ms=epoch_ms(2026, 5, 10),
                to=("bo@team.example",),
            ),
            Msg(
                id="w2",
                thread_id="t-quote",
                sender="Bo Ng <bo@team.example>",
                subject="Re: Rack order",
                body=f"noted, the {OTHER} detail is settled",
                internal_date_ms=epoch_ms(2026, 5, 11),
                to=("ana@team.example",),
                in_reply_to=msgid("w1"),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )


def participants_of(envelope: Envelope, thread_id: str) -> dict[str, tuple[tuple[str, ...], ...]]:
    source = next(s for s in envelope.sources if s.thread_id == thread_id)
    return {p.address: (p.authored, p.coauthored, p.mentioned) for p in source.participants}


def test_an_address_inside_a_quoted_block_is_a_mention_the_response_can_see() -> None:
    """R-RETR-051: the scanner is handed the annotated body, not the quote-stripped view.

    `DEFAULT_VIEW_CLASSES` is `{ORIGINAL}`, so quoted and signature spans were excluded from
    what the mention scanner saw - **and the row reported itself scanned**, which is what
    makes this a defect rather than a policy. `mentions_not_scanned` is the field a caller
    reads to know that "no mentions" is not a negative derived from an absence, and here it
    was exactly that. A7's rule is annotate, do not delete, and it applies to what is scanned
    as much as to what is shown.
    """
    envelope = answer(MARKER, quoted_mention_mailbox())
    participants = participants_of(envelope, "t-quote")
    assert "cai@team.example" in participants
    _authored, _coauthored, mentioned = participants["cai@team.example"]
    assert mentioned == ("w1",)
    source = next(s for s in envelope.sources if s.thread_id == "t-quote")
    assert source.structure is not None
    assert source.structure.mentions_not_scanned == ()


def test_a_truncated_snippet_never_mints_an_address_that_is_in_no_message() -> None:
    """R-RETR-052: a truncation boundary is not an address boundary.

    A `snippet` is a cut by construction, so an address straddling the cut becomes a
    *different* address - and it is still address-shaped, so `is_an_address` accepts it, the
    `ThreadParticipant` validator accepts it, and `mentioned_only` reports it as somebody the
    thread talks about. Missing a mention is the direction this module already declares it
    prefers; inventing one is not.
    """
    whole = "please loop in cai@team.example"
    cut = whole[: whole.index("cai@team.example") + len("cai@team.exampl")]
    assert cut.endswith("cai@team.exampl")

    assert addresses_in_text(ObservedText(text=cut, truncated_at_end=True)) == ()
    # The same string read as whole text is a whole address, which is what makes the pair
    # `(text, truncated_at_end)` the thing carrying the fact rather than the string's shape.
    assert addresses_in_text(ObservedText(text=cut)) == ("cai@team.exampl",)
    # And a truncation that does not touch an address leaves it alone.
    assert addresses_in_text(
        ObservedText(text="cai@team.example wrote a thi", truncated_at_end=True)
    ) == ("cai@team.example",)


def test_no_address_reaches_the_wire_that_appears_in_no_message_of_the_mailbox() -> None:
    """The same property stated over the response rather than over the scanner.

    This is the statement a caller cares about, and it holds over whichever rows the query
    happened to match: every address in every participant block is a substring of some
    message this mailbox holds.
    """
    box = quoted_mention_mailbox()
    for query in (MARKER, OTHER):
        envelope = answer(query, box)
        corpus = " ".join(
            f"{m.sender} {m.subject} {m.body} {' '.join(m.to)} {' '.join(m.cc)}"
            for m in box.messages
        ).lower()
        for source in envelope.sources:
            for participant in source.participants:
                assert participant.address in corpus, (participant.address, query)


def test_the_participant_index_still_depends_on_depth_and_the_digest_therefore_excludes_it() -> (
    None
):
    """What R-RETR-051's fix does **not** close, executed rather than assumed.

    Scanning the annotated body removes the quote-stripping narrowing. It does not make the
    index thread-only: a row whose body was fetched is scanned over the whole body, and a row
    that only ever had a `snippet` is scanned over what Gmail chose to send. So two
    redemptions of one handle at different disclosure depths would still disagree about the
    participant block - which is why `mapping_digest` covers the map and not
    `Source.participants`, and why the answer to R-RETR's instruction is *both*: fix the
    narrowing, and keep participants out of the digest.
    """
    box = quoted_mention_mailbox()
    by_query = {query: participants_of(answer(query, box), "t-quote") for query in (MARKER, OTHER)}
    assert by_query[MARKER] != by_query[OTHER], (
        "if these ever agree, the depth dependence is gone and the digest decision in "
        "mailweave.handles.digest should be revisited rather than left as a stale comment"
    )
    # The half that is thread-only agrees under both queries: who wrote what. Only the
    # mention half moves, and it moves by *gaining* an address rather than by disagreeing -
    # the difference is entirely which rows had text to scan.
    authorship = {
        query: {address: facts[:2] for address, facts in block.items() if any(facts[:2])}
        for query, block in by_query.items()
    }
    assert authorship[MARKER] == authorship[OTHER]
    mentions = {query: {a: block[a][2] for a in block} for query, block in by_query.items()}
    assert mentions[MARKER] != mentions[OTHER]


# --- R-RETR-054: D.4a's compensating fact reaches the row ----------------------------------


def no_message_id_mailbox() -> SyntheticMailbox:
    """AD D.4a's own case beside an ordinary reply, and a well-formed child of it."""
    return SyntheticMailbox(
        messages=(
            Msg(
                id="d1",
                thread_id="t-d4a",
                sender="Ana Ito <ana@team.example>",
                subject="Rack order",
                body="the opening note",
                internal_date_ms=epoch_ms(2026, 5, 1),
            ),
            # The query matches **this** row, so it is the one that gets a body - which puts a
            # `can_be_a_parent: false` on the body-bearing branch of `_rows_of` as well as on
            # the stub branch below. The field is set in two places in that function and each
            # can be removed on its own, so a fixture that only reached one of them would
            # leave the other undefended (round 21 replants R46 and R57).
            Msg(
                id="d2",
                thread_id="t-d4a",
                sender="Bo Ng <bo@team.example>",
                subject="Re: Rack order",
                body=f"a {MARKER} reply from a client that sent no Message-ID",
                internal_date_ms=epoch_ms(2026, 5, 2),
                in_reply_to=msgid("d1"),
                omit_message_id=True,
            ),
            Msg(
                id="d3",
                thread_id="t-d4a",
                sender="Cai Ode <cai@team.example>",
                subject="Re: Rack order",
                body="an ordinary reply to the same parent",
                internal_date_ms=epoch_ms(2026, 5, 3),
                in_reply_to=msgid("d1"),
            ),
            Msg(
                id="d4",
                thread_id="t-d4a",
                sender="Dee Rho <dee@team.example>",
                subject="Re: Rack order",
                body="a second client that sent no Message-ID, and no query matches it",
                internal_date_ms=epoch_ms(2026, 5, 4),
                in_reply_to=msgid("d1"),
                omit_message_id=True,
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )


def test_a_message_no_reply_can_ever_name_is_distinguishable_on_the_wire() -> None:
    """R-RETR-054, and the ruling it rests on.

    R-RETR ruled that D.4a's narrow reading **stands** - a link a child's own headers support
    is not the guess D.4a forbids - *conditionally on the compensating fact reaching the
    caller*. It did not: `can_be_a_parent` never left `reply_tree.py`, so `d2` and `d3`
    serialised identically in every field but id and position while `d2` is a message no
    reply can ever name. The reading is unchanged; the fact is now on the row.
    """
    envelope = answer(MARKER, no_message_id_mailbox())
    rows = rows_of(envelope, "t-d4a")
    d2, d3, d4 = rows["d2"], rows["d3"], rows["d4"]
    for row in (d2, d3, d4):
        assert row.linkage is Linkage.IN_REPLY_TO and row.reply_parent_id == "d1"  # type: ignore[attr-defined]
    # `d2` is the matched row and carries a body; `d4` is a stub. `_rows_of` builds the two
    # in separate branches, so both are asserted rather than one standing in for the other.
    assert d2.depth is Depth.BODY_CLEAN and d2.can_be_a_parent is False  # type: ignore[attr-defined]
    assert d4.depth is Depth.STUB and d4.can_be_a_parent is False  # type: ignore[attr-defined]
    assert d3.can_be_a_parent is True  # type: ignore[attr-defined]

    dumped = {
        key: (d4.model_dump(mode="json")[key], d3.model_dump(mode="json")[key])  # type: ignore[attr-defined]
        for key in d4.model_dump(mode="json")  # type: ignore[attr-defined]
    }
    differing = {key for key, (left, right) in dumped.items() if left != right}
    assert "can_be_a_parent" in differing, differing


def test_not_knowing_whether_a_message_can_be_named_is_exactly_one_linkage() -> None:
    """The third state is held to the one linkage that means it, at the model.

    Left as a plain default, `None` would have been the value on most rows - which is the
    state R-RETR-054 filed, arriving through the schema instead of through the module. The
    biconditional is what makes the field impossible to omit from a row whose headers were
    read, and impossible to *state* on a row whose headers nothing observed.
    """

    def row(linkage: Linkage, can_be_a_parent: bool | None) -> MessageRow:
        return MessageRow(
            id="m-1",
            position=0,
            role=Role.STUB,
            reason=ThreadMember(thread_id="t-1", position=0),
            mailbox=MailboxProvenance.unobserved(),
            depth=Depth.STUB,
            linkage=linkage,
            can_be_a_parent=can_be_a_parent,
            unabridged={"tool": ToolName.GET_MESSAGES, "args": {"ids": ["m-1"]}},  # type: ignore[arg-type]
        )

    assert row(Linkage.HEADERS_UNOBSERVED, None).can_be_a_parent is None
    assert row(Linkage.NO_REPLY_HEADERS, True).can_be_a_parent is True
    with pytest.raises(ValidationError):
        row(Linkage.NO_REPLY_HEADERS, None)
    with pytest.raises(ValidationError):
        row(Linkage.HEADERS_UNOBSERVED, True)


# --- R-RETR-053: a lookup L4 declined to make is a lookup the response accounts for --------


def unprobeable_identifier_mailbox() -> SyntheticMailbox:
    """One child whose named parent is probeable and one whose identifier cannot be a `q`."""
    return SyntheticMailbox(
        messages=(
            Msg(
                id="c1",
                thread_id="t-hit",
                sender="Ana Ito <ana@team.example>",
                subject="Rack order",
                body=f"a {MARKER} note",
                internal_date_ms=epoch_ms(2026, 5, 10),
                in_reply_to=msgid("probeable"),
            ),
            Msg(
                id="c2",
                thread_id="t-hit",
                sender="Bo Ng <bo@team.example>",
                subject="Re: Rack order",
                body=f"another {MARKER} note",
                internal_date_ms=epoch_ms(2026, 5, 11),
                in_reply_to='<qu"oted@mail.invalid>',
            ),
            Msg(
                id="p1",
                thread_id="t-parent",
                sender="Cai Ode <cai@team.example>",
                subject="Rack order",
                body="the parent that can be looked up",
                internal_date_ms=epoch_ms(2026, 5, 1),
                rfc822_message_id=msgid("probeable"),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )


def test_a_probe_declined_while_others_ran_is_reported_rather_than_invisible() -> None:
    """R-RETR-053: three facts are reportable about L4 and two were being reported.

    `StructuralPlan.skipped` is documented as "a permanent inability" and was read by
    nothing: a `Message-ID` carrying Gmail's own query punctuation was silently not looked
    for whenever any other probe went out. The child's own row still declared its gap, so no
    message was lost; what was lost is the rung's account of a lookup it chose not to make.
    """
    box = unprobeable_identifier_mailbox()
    envelope = answer(MARKER, box)
    entries = {(e.rung, e.why.value) for e in envelope.retrieval_report.not_tried}
    assert (UNPROBEABLE_IDENTIFIER_RUNG, "not_applicable") in entries, entries
    # L4 itself ran, so it is *not* reported as not_applicable: the two facts are different
    # and reporting the declined identifier as "L4 did not run" would contradict `rungs`.
    assert ("L4", "not_applicable") not in entries
    assert any(query.startswith("rfc822msgid:") for query, _spam in box.queries)


def test_the_declined_entry_is_absent_when_every_identifier_was_probeable() -> None:
    """The complement, so the entry is a fact about this response rather than a constant."""
    envelope = answer(MARKER, ancestry_mailbox())
    entries = {e.rung for e in envelope.retrieval_report.not_tried}
    assert UNPROBEABLE_IDENTIFIER_RUNG not in entries, entries


# --- R-RETR-055: the tie census and the ordering read one number --------------------------


def test_a_tie_settled_by_message_id_is_declared_however_the_stamp_is_spelled() -> None:
    """R-RETR-055: the sort compared integers and the census compared strings.

    `GmailNumericId` accepts a zero-padded stamp, so `"01000"` and `"1000"` are equal as
    integers and unequal as strings: the ordering treated them as a tie and settled them by
    message id, and `tied_on_internal_date` - the one field that exists to stop a position
    claim reading as stronger than the evidence - named neither. Two derivations of one fact,
    which is R-ARCH-031 with a `Counter` key as the second derivation.
    """
    thread = Thread(
        id="t-1",
        messages=(
            Message(id="m1", threadId="t-1", internalDate="01000"),
            Message(id="m2", threadId="t-1", internalDate="1000"),
        ),
    )
    scalars = _thread_scalars(thread)
    assert scalars.positions == {"m1": 0, "m2": 1}
    assert scalars.tied_on_internal_date == ("m1", "m2")

    # The ordinary shapes are unchanged: distinct stamps are not a tie, equal ones are.
    distinct = Thread(
        id="t-2",
        messages=(
            Message(id="a", threadId="t-2", internalDate="2000"),
            Message(id="b", threadId="t-2", internalDate="1000"),
        ),
    )
    assert _thread_scalars(distinct).tied_on_internal_date == ()
    assert _thread_scalars(distinct).positions == {"b": 0, "a": 1}


# --- R-RETR-057: the two narrowings `_resolve` makes, executed ----------------------------


def test_the_two_narrowings_resolve_makes_are_the_ones_its_docstring_states() -> None:
    """R-RETR-057, recorded in the docstring and pinned here so the record is executed.

    Neither narrowing invents a parent - every candidate is an id the child itself named -
    which is why R-RETR filed them LOW and why they are documented rather than changed. What
    a test adds is that the documented behaviour is the behaviour: a docstring nothing
    executes is the class of claim this whole round is about.
    """
    # 1. A multi-id `In-Reply-To` whose ids this thread both holds resolves to the first.
    #    RFC 5322 permits it, and both are parents the child named.
    views = (
        MessageHeaderView("a", msgid("a"), (), (), True, False),
        MessageHeaderView("b", msgid("b"), (), (), True, False),
        MessageHeaderView("child", msgid("child"), (msgid("a"), msgid("b")), (), True, True),
    )
    links = reconstruct(views).by_id
    assert links["child"].parent_id == "a"
    assert links["child"].linkage is Linkage.IN_REPLY_TO

    # 2. An ambiguity seen on the way to a unique candidate is dropped, and no field carries
    #    it. The link that results is header-backed; what a caller cannot see is that a
    #    duplicate `Message-ID` was in the thread.
    duplicated = (
        MessageHeaderView("d1", msgid("dup"), (), (), True, False),
        MessageHeaderView("d2", msgid("dup"), (), (), True, False),
        MessageHeaderView("u", msgid("uniq"), (), (), True, False),
        MessageHeaderView("child", msgid("child"), (msgid("dup"), msgid("uniq")), (), True, True),
    )
    resolved = reconstruct(duplicated).by_id["child"]
    assert resolved.parent_id == "u"
    assert resolved.linkage is Linkage.IN_REPLY_TO
    assert resolved.evidence == msgid("uniq")
