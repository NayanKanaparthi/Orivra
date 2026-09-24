"""WS-05: the thread map, driven end to end against a whole mailbox behind the real client.

Same standing as `tests/test_lexical_ladder.py` and built the same way - real URL
construction, real bearer header, real retry ladder, real egress allowlist, real
`DispositionLedger`, with an `httpx.MockTransport` where the socket would be and
`tests/conftest.py` denying `socket.connect` for every test here.

**The reply tree is tested by what every shape has in common, not one shape at a time.**
This project's recurring defect is "one shape validated, peers trusted", found fifteen times,
five of them inside the fix for the previous one. A reply tree has many shapes - broken
headers, a subject change mid-thread, forwards, orphans, cycles, self-references, duplicate
`Message-ID`s, a message referencing one that is absent, a message with no `Message-ID` at
all - and a list of nine tests is nine chances to have missed the tenth. So the load-bearing
test here is
`test_every_reply_tree_shape_keeps_the_four_properties_that_make_it_not_a_guess`, a property
run over *generated* threads, and the four properties are the ones that make a reconstruction
a reading rather than a guess:

  1. every message gets exactly one `Link` and one closed-vocabulary `linkage`;
  2. a link names a parent **of this same thread**, found under a `Message-ID` that appears
     in this child's own `In-Reply-To`/`References` **and** is the one that parent carries -
     or it names no parent and says which gap it is in;
  3. the parent map is a forest: following it upward from anywhere terminates;
  4. the whole result is invariant under permutation of the input.

The named shapes are still here, in `SHAPES`, and they are there to prove the generator is
not vacuous: every one of them is asserted to be *reachable*, so a property that held only
over trees the generator never built would fail.

**Ordering.** `test_the_array_order_gmail_returns_does_not_change_the_representation` runs
one query twice against the same mailbox, once with `threads.get` returning its array in
`internalDate` order and once reversed, and compares the whole response. Gmail does not
promise the array is sorted (STR-03, C-02c), and every earlier fixture in this repository
returned it sorted - which is precisely how an array-order dependence survives: with the two
orders always equal, code that reads the array index and code that reads `internalDate` are
indistinguishable.

No fixture here carries real or realistic personal mail: addresses use the reserved
`.example` and `.invalid` TLDs (RFC 2606/6761) and every subject and body is invented for the
structural property the test is about.
`test_no_fixture_in_this_file_carries_anything_that_could_be_real_mail` executes that rather
than asserting it.
"""

from __future__ import annotations

import ast
import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from mailweave.envelope import (
    Depth,
    DispositionLedger,
    Linkage,
    MailboxProvenance,
    MessageRow,
    Role,
    Source,
    ThreadParticipant,
    ThreadStructureReport,
    ToolName,
    WithheldCap,
)
from mailweave.envelope.fence import unfence
from mailweave.envelope.reasons import ReplyChildOf, ReplyParentOf, RungId, ThreadMember
from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import (
    DECLARED_GAP_LINKAGES,
    RESOLVED_LINKAGES,
    ParticipantRole,
    Trust,
)
from mailweave.errors import ThreadStructureError
from mailweave.gmail.client import GmailClient, StaticToken
from mailweave.gmail.meter import CallMeter
from mailweave.gmail.retry import BackoffPolicy
from mailweave.net.egress import build_client
from mailweave.query.analysis import analyse
from mailweave.retrieval.assemble import STRUCTURAL_SIMILARITY_RUNG, assemble
from mailweave.retrieval.ladder import LadderRunner
from mailweave.retrieval.structural import (
    MAX_STRUCTURAL_PROBES,
    is_probeable,
    plan_structural_expansion,
)
from mailweave.structure.participants import (
    ObservedText,
    addresses_in_header,
    addresses_in_text,
    index_participants,
    name_only_mentions_are_not_resolved,
    participants_of_message,
)
from mailweave.structure.reply_tree import MessageHeaderView, reconstruct
from mailweave.structure.threadmap import build as build_thread_map
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.test_lexical_ladder import REGION_DECLARING_FRAGMENTS

NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)
UTC_ZONE = ZoneInfo("UTC")
TOKEN = "ya29.synthetic-thread-map-token"

#: The one term every shape thread carries exactly once, so a single query maps all of them
#: and the sweeps below run over the whole corpus rather than over the thread a test author
#: had in mind.
MARKER = "borogrove"

#: A term that appears in no message. Used where a test needs the empty case.
ABSENT = "vellichor"


def msgid(name: str) -> str:
    return f"<{name}@mail.invalid>"


# --- the corpus: one thread per reply-tree shape ------------------------------------------
#
# Every thread below carries exactly one message containing `MARKER`, so `answer(MARKER)`
# maps all of them in one response. `t-elsewhere` deliberately does not, because it must be
# reachable only through L4's structural expansion.


def plain_thread() -> tuple[Msg, ...]:
    """A well-formed chain: root, an `In-Reply-To` reply, a `References` reply."""
    return (
        Msg(
            id="p1",
            thread_id="t-plain",
            sender="Ana Ito <ana@team.example>",
            subject="Cutover window",
            body="opening note",
            internal_date_ms=epoch_ms(2026, 5, 1),
            to=("bo@team.example",),
        ),
        Msg(
            id="p2",
            thread_id="t-plain",
            sender="Bo Ng <bo@team.example>",
            subject="Re: Cutover window",
            body=f"the {MARKER} question",
            internal_date_ms=epoch_ms(2026, 5, 2),
            to=("ana@team.example",),
            in_reply_to=msgid("p1"),
        ),
        Msg(
            id="p3",
            thread_id="t-plain",
            sender="Ana Ito <ana@team.example>",
            subject="Re: Cutover window",
            body="closing note",
            internal_date_ms=epoch_ms(2026, 5, 3),
            references=f"{msgid('p1')} {msgid('p2')}",
        ),
    )


def broken_thread() -> tuple[Msg, ...]:
    """Reply headers present and unreadable - a real client bug, not an absent header."""
    return (
        Msg(
            id="b1",
            thread_id="t-broken",
            sender="Cai Ode <cai@team.example>",
            subject="Vendor list",
            body="first",
            internal_date_ms=epoch_ms(2026, 5, 4),
        ),
        Msg(
            id="b2",
            thread_id="t-broken",
            sender="Dee Rho <dee@team.example>",
            subject="Re: Vendor list",
            body=f"a {MARKER} follow-up",
            internal_date_ms=epoch_ms(2026, 5, 5),
            in_reply_to="see my previous mail",
            references="",
        ),
    )


def subject_change_thread() -> tuple[Msg, ...]:
    """The subject changes mid-thread and the headers stay intact: the link survives.

    Gmail also files a message here by subject alone; that one names no parent and is
    declared, never attached to the message printed above it.
    """
    return (
        Msg(
            id="s1",
            thread_id="t-subject",
            sender="Ana Ito <ana@team.example>",
            subject="Weekly sync",
            body="agenda",
            internal_date_ms=epoch_ms(2026, 5, 6),
        ),
        Msg(
            id="s2",
            thread_id="t-subject",
            sender="Bo Ng <bo@team.example>",
            subject="Re: Weekly sync -> parts ordering",
            body=f"renamed, and {MARKER}",
            internal_date_ms=epoch_ms(2026, 5, 7),
            in_reply_to=msgid("s1"),
        ),
        Msg(
            id="s3",
            thread_id="t-subject",
            sender="Cai Ode <cai@team.example>",
            subject="Weekly sync",
            body="filed here by subject alone",
            internal_date_ms=epoch_ms(2026, 5, 8),
        ),
    )


def forward_thread() -> tuple[Msg, ...]:
    """A forward whose `References` names a message living in a different thread."""
    return (
        Msg(
            id="f1",
            thread_id="t-forward",
            sender="Dee Rho <dee@team.example>",
            subject="Fwd: parts ordering",
            body=f"forwarding the {MARKER} thread",
            internal_date_ms=epoch_ms(2026, 5, 9),
            references=msgid("e1"),
        ),
    )


def elsewhere_thread() -> tuple[Msg, ...]:
    """The forward's parent, in its own thread, carrying no marker of its own.

    Reachable only by L4's `rfc822msgid:` lookup, which is the point: if it were reachable
    lexically, a test asserting that structural expansion recovered it would pass without
    structural expansion.
    """
    return (
        Msg(
            id="e1",
            thread_id="t-elsewhere",
            sender="Eve Lin <eve@team.example>",
            subject="parts ordering",
            body="the original decision",
            internal_date_ms=epoch_ms(2026, 4, 28),
        ),
        Msg(
            id="e2",
            thread_id="t-elsewhere",
            sender="Ana Ito <ana@team.example>",
            subject="Re: parts ordering",
            body="acknowledged",
            internal_date_ms=epoch_ms(2026, 4, 29),
            in_reply_to=msgid("e1"),
        ),
    )


def cycle_thread() -> tuple[Msg, ...]:
    """Two messages naming each other, and nothing in the headers says which is wrong."""
    return (
        Msg(
            id="c1",
            thread_id="t-cycle",
            sender="Ana Ito <ana@team.example>",
            subject="Loop",
            body=f"one, with {MARKER}",
            internal_date_ms=epoch_ms(2026, 5, 10),
            in_reply_to=msgid("c2"),
        ),
        Msg(
            id="c2",
            thread_id="t-cycle",
            sender="Bo Ng <bo@team.example>",
            subject="Re: Loop",
            body="two",
            internal_date_ms=epoch_ms(2026, 5, 11),
            in_reply_to=msgid("c1"),
        ),
    )


def self_reference_thread() -> tuple[Msg, ...]:
    """A message whose `In-Reply-To` names its own `Message-ID`. The one-node cycle."""
    return (
        Msg(
            id="r1",
            thread_id="t-self",
            sender="Cai Ode <cai@team.example>",
            subject="Self",
            body=f"a {MARKER} self-reference",
            internal_date_ms=epoch_ms(2026, 5, 12),
            in_reply_to=msgid("r1"),
        ),
    )


def duplicate_message_id_thread() -> tuple[Msg, ...]:
    """Two messages carrying one `Message-ID`, and a reply that names it."""
    return (
        Msg(
            id="d1",
            thread_id="t-dup",
            sender="Ana Ito <ana@team.example>",
            subject="Resent",
            body="first copy",
            internal_date_ms=epoch_ms(2026, 5, 13),
            rfc822_message_id=msgid("shared"),
        ),
        Msg(
            id="d2",
            thread_id="t-dup",
            sender="Ana Ito <ana@team.example>",
            subject="Resent",
            body="second copy",
            internal_date_ms=epoch_ms(2026, 5, 14),
            rfc822_message_id=msgid("shared"),
        ),
        Msg(
            id="d3",
            thread_id="t-dup",
            sender="Bo Ng <bo@team.example>",
            subject="Re: Resent",
            body=f"replying to {MARKER}",
            internal_date_ms=epoch_ms(2026, 5, 15),
            in_reply_to=msgid("shared"),
        ),
    )


def no_message_id_thread() -> tuple[Msg, ...]:
    """A message with no `Message-ID` at all (AD D.4a), and a reply naming an absent one."""
    return (
        Msg(
            id="n1",
            thread_id="t-nomsgid",
            sender="Dee Rho <dee@team.example>",
            subject="Headerless",
            body="no Message-ID on this one",
            internal_date_ms=epoch_ms(2026, 5, 16),
            omit_message_id=True,
        ),
        Msg(
            id="n2",
            thread_id="t-nomsgid",
            sender="Eve Lin <eve@team.example>",
            subject="Re: Headerless",
            body=f"a {MARKER} reply to nothing this thread holds",
            internal_date_ms=epoch_ms(2026, 5, 17),
            in_reply_to=msgid("never-delivered"),
        ),
    )


def tied_timestamp_thread() -> tuple[Msg, ...]:
    """Two messages stamped in the same millisecond. Chronology cannot separate them."""
    stamp = epoch_ms(2026, 5, 18)
    return (
        Msg(
            id="w1",
            thread_id="t-tie",
            sender="Ana Ito <ana@team.example>",
            subject="Simultaneous",
            body=f"a {MARKER} pair, first written",
            internal_date_ms=stamp,
        ),
        Msg(
            id="w2",
            thread_id="t-tie",
            sender="Bo Ng <bo@team.example>",
            subject="Simultaneous",
            body="a pair, second written",
            internal_date_ms=stamp,
        ),
    )


def hearsay_thread() -> tuple[Msg, ...]:
    """STR-02's family: one message *by* an address, one merely *about* it.

    `mallory@elsewhere.invalid` presents itself under Ana's display name, which is INJ-05's
    shape: identity is the address, so this message is authored by mallory and by nobody
    called Ana.
    """
    return (
        Msg(
            id="h1",
            thread_id="t-hearsay",
            sender='"Ana Ito" <mallory@elsewhere.invalid>',
            subject="Who decided",
            body=f"eve@team.example said we should ship the {MARKER}",
            internal_date_ms=epoch_ms(2026, 5, 19),
            to=("bo@team.example",),
            cc=("Cai Ode <cai@team.example>",),
            reply_to="fin@team.example",
        ),
        Msg(
            id="h2",
            thread_id="t-hearsay",
            sender="Eve Lin <eve@team.example>",
            subject="Re: Who decided",
            body="I did not say that",
            internal_date_ms=epoch_ms(2026, 5, 20),
            in_reply_to=msgid("h1"),
        ),
        Msg(
            id="h3",
            thread_id="t-hearsay",
            sender="ops list, no address here",
            subject="Re: Who decided",
            body="an automated note with no readable From",
            internal_date_ms=epoch_ms(2026, 5, 21),
            in_reply_to=msgid("h1"),
        ),
        Msg(
            id="h4",
            thread_id="t-hearsay",
            sender="Ana Ito <ana@team.example>, Bo Ng <bo@team.example>",
            subject="Re: Who decided",
            body="written jointly",
            internal_date_ms=epoch_ms(2026, 5, 22),
            in_reply_to=msgid("h1"),
        ),
    )


#: Every shape, named, so a test can say which one it is exercising and the reachability
#: sweep can assert none of them has quietly stopped being produced.
SHAPES: dict[str, Linkage] = {
    "well-formed In-Reply-To": Linkage.IN_REPLY_TO,
    "well-formed References": Linkage.REFERENCES,
    "thread root / filed by subject": Linkage.NO_REPLY_HEADERS,
    "reply headers unreadable": Linkage.UNPARSEABLE_REPLY_HEADERS,
    "parent in another thread": Linkage.UNRESOLVED_PARENT,
    "two messages carry the named id": Linkage.AMBIGUOUS_PARENT,
    "reply headers form a cycle": Linkage.REPLY_CYCLE,
    "no Message-ID and no parent named": Linkage.NO_MESSAGE_ID,
}


def corpus() -> tuple[Msg, ...]:
    return (
        *plain_thread(),
        *broken_thread(),
        *subject_change_thread(),
        *forward_thread(),
        *elsewhere_thread(),
        *cycle_thread(),
        *self_reference_thread(),
        *duplicate_message_id_thread(),
        *no_message_id_thread(),
        *tied_timestamp_thread(),
        *hearsay_thread(),
    )


def mailbox(**overrides: object) -> SyntheticMailbox:
    """One mailbox, rebuilt per test so a call log is never shared between assertions."""
    return SyntheticMailbox(messages=corpus(), now_ms=epoch_ms(2026, 9, 3), **overrides)  # type: ignore[arg-type]


def make_client(box: SyntheticMailbox) -> GmailClient:
    """The shipped client. Only the socket is replaced."""
    return GmailClient(
        token=StaticToken(TOKEN),
        http=build_client(inner=box.transport()),
        meter=CallMeter(),
        policy=BackoffPolicy(),
        sleeper=lambda _seconds: None,
        jitterer=lambda: 0.5,
    )


def answer(query: str, *, box: SyntheticMailbox | None = None) -> tuple[SyntheticMailbox, Envelope]:
    """Run the whole ladder and assemble the envelope: WS-04 plus this round's WS-05."""
    box = mailbox() if box is None else box
    client = make_client(box)
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run(query, now=NOW, zone=UTC_ZONE)
    return box, assemble(run, client=client, ledger=ledger)


def rows_of(envelope: Envelope, thread_id: str) -> dict[str, MessageRow]:
    source = next(s for s in envelope.sources if s.thread_id == thread_id)
    return {row.id: row for row in source.messages}


def every_row(envelope: Envelope) -> dict[str, MessageRow]:
    return {row.id: row for source in envelope.sources for row in source.messages}


# --- the commonality: what holds for every shape, including the ones nobody wrote ----------


#: Gmail message ids the generator draws from. Small and fixed, so a generated thread reuses
#: ids across roles and the interesting collisions actually happen.
GENERATED_IDS: tuple[str, ...] = ("g1", "g2", "g3", "g4", "g5")

#: `Message-ID` header values the generator draws from, including one no message will carry.
GENERATED_MSG_IDS: tuple[str, ...] = (
    "<x1@mail.invalid>",
    "<x2@mail.invalid>",
    "<x3@mail.invalid>",
    "<absent@mail.invalid>",
)


@st.composite
def header_views(draw: st.DrawFn) -> tuple[MessageHeaderView, ...]:
    """Arbitrary threads, including every shape `SHAPES` names and many it does not.

    The generator is written over the *facts a Gmail response states* - which ids it
    returned, which of them carried a `Message-ID`, what their reply headers named, and
    whether the headers were observed at all - rather than over the shapes a fixture author
    thought of. Duplicate `Message-ID`s, cycles, self-references, references to absent
    messages, unobserved headers and empty reply headers all arise from those choices
    without being enumerated, which is the whole point: a property that holds here holds for
    a shape nobody has written down.
    """
    ids = draw(st.lists(st.sampled_from(GENERATED_IDS), min_size=1, max_size=5, unique=True))
    views: list[MessageHeaderView] = []
    for message_id in ids:
        observed = draw(st.booleans())
        if not observed:
            views.append(
                MessageHeaderView(
                    message_id=message_id,
                    rfc_message_id=None,
                    in_reply_to=(),
                    references=(),
                    headers_observed=False,
                    reply_headers_present=False,
                )
            )
            continue
        own = draw(st.one_of(st.none(), st.sampled_from(GENERATED_MSG_IDS)))
        in_reply_to = tuple(
            draw(st.lists(st.sampled_from(GENERATED_MSG_IDS), max_size=2, unique=True))
        )
        references = tuple(
            draw(st.lists(st.sampled_from(GENERATED_MSG_IDS), max_size=3, unique=True))
        )
        present = draw(st.booleans()) or bool(in_reply_to or references)
        views.append(
            MessageHeaderView(
                message_id=message_id,
                rfc_message_id=own,
                in_reply_to=in_reply_to if present else (),
                references=references if present else (),
                headers_observed=True,
                reply_headers_present=present,
            )
        )
    return tuple(views)


def _terminates(parents: dict[str, str | None], start: str) -> bool:
    seen: set[str] = set()
    node: str | None = start
    while node is not None:
        if node in seen:
            return False
        seen.add(node)
        node = parents.get(node)
    return True


@settings(max_examples=400, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(views=header_views())
def test_every_reply_tree_shape_keeps_the_four_properties_that_make_it_not_a_guess(
    views: tuple[MessageHeaderView, ...],
) -> None:
    """The commonality, over generated threads rather than over a list of cases.

    Nine named shapes is nine chances to have missed the tenth, and this repository has
    missed the tenth fifteen times. What every shape shares is that the reconstruction is a
    *reading of the child's own headers*, so the four properties below are the ones that
    distinguish a reading from a guess, and they are asserted over threads nobody wrote:

      1. one `Link` per message, one closed-vocabulary `linkage`;
      2. a resolved link names a parent of this same thread, under a `Message-ID` that is in
         this child's own headers **and** is the one that parent carries; a declared gap
         names no parent at all;
      3. the parent map is a forest - following it upward terminates from every node;
      4. `can_be_a_parent` is a fact about the message's own `Message-ID` and nothing else.

    Property 2's second half is the one that catches the guess: a reconstruction that
    attached a message to its predecessor would satisfy "the parent is in this thread" and
    fail "under an id the child named".
    """
    structure = reconstruct(views)
    by_view = {view.message_id: view for view in views}

    assert len(structure.links) == len(views)
    assert [link.message_id for link in structure.links] == [view.message_id for view in views]
    assert all(isinstance(link.linkage, Linkage) for link in structure.links)
    assert structure.linked + structure.unlinked == len(views)

    for link in structure.links:
        view = by_view[link.message_id]
        if link.linkage in RESOLVED_LINKAGES:
            assert link.parent_id in by_view, link
            assert link.evidence is not None
            assert link.evidence in view.in_reply_to + view.references, link
            assert by_view[link.parent_id].rfc_message_id == link.evidence, link
        else:
            assert link.linkage in DECLARED_GAP_LINKAGES
            assert link.parent_id is None, link

    parents = {link.message_id: link.parent_id for link in structure.links}
    assert all(_terminates(parents, message_id) for message_id in parents)

    for link in structure.links:
        view = by_view[link.message_id]
        expected = None if not view.headers_observed else view.rfc_message_id is not None
        assert link.can_be_a_parent is expected, link


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(views=header_views(), seed=st.integers(min_value=0, max_value=10_000))
def test_the_reconstruction_cannot_see_the_order_it_is_given(
    views: tuple[MessageHeaderView, ...], seed: int
) -> None:
    """Property 4, and the reason it is a property of the *signature*.

    `MessageHeaderView` carries ids and header values and nothing else - no date, no array
    index, no position - so date-adjacent re-parenting is not a thing `reconstruct` declines
    to do, it is a thing it cannot do. This permutes the input and compares the whole result
    keyed by message, which is the assertion that survives when somebody adds a field later.
    """
    rotated = views[seed % max(len(views), 1) :] + views[: seed % max(len(views), 1)]
    first = {link.message_id: link for link in reconstruct(views).links}
    second = {link.message_id: link for link in reconstruct(rotated).links}
    assert first == second


def test_the_reconstruction_is_not_given_anything_it_could_order_by() -> None:
    """The same claim read off the type, so it survives a change to the generator.

    A field named for a date or a position on `MessageHeaderView` would make the property
    above a statement about today's implementation rather than about what the function can
    see. This fails on the field being *added*, which is the moment to think about it.
    """
    fields = set(MessageHeaderView.__dataclass_fields__)
    assert fields == {
        "message_id",
        "rfc_message_id",
        "in_reply_to",
        "references",
        "headers_observed",
        "reply_headers_present",
    }
    forbidden = {"date", "internal_date", "position", "index", "order", "received"}
    assert not {word for field in fields for word in field.split("_")} & forbidden


def test_the_orphan_linkage_carries_the_string_the_architecture_published() -> None:
    """AD D.6 publishes the label verbatim, and a paraphrase is a different contract.

    `linkage: "date-adjacent (no RFC reply headers)"` is the string C-02a and D.6 both quote.
    It is the value a caller branches on, so it is pinned here rather than left to whoever
    next edits the enum - and the *word* in it describes where such a message is displayed,
    in `internalDate` order beside its neighbours, never a parent it was given.
    """
    assert Linkage.NO_REPLY_HEADERS.value == "date-adjacent (no RFC reply headers)"
    assert Linkage.NO_MESSAGE_ID.value == "no Message-ID"
    assert set(Linkage) == RESOLVED_LINKAGES | DECLARED_GAP_LINKAGES
    assert not RESOLVED_LINKAGES & DECLARED_GAP_LINKAGES


def test_a_message_with_no_message_id_still_gets_the_link_its_own_headers_support() -> None:
    """The one place this round reads AD D.4a narrowly, executed so it can be reviewed.

    D.4a says a missing `Message-ID` "yields `linkage: 'no Message-ID'` ... never a guessed
    parent". `NO_MESSAGE_ID` is given to the message that sentence is the whole story for -
    no `Message-ID` and no parent named. Where such a message's own `In-Reply-To` names a
    parent this thread holds, the link is stated and `can_be_a_parent` is `False` beside it,
    because refusing a link the child's own headers support would discard evidence that was
    actually read, and D.4a forbids *guessing* a parent, which this is not.
    """
    root = MessageHeaderView(
        message_id="g1",
        rfc_message_id=msgid("g1"),
        in_reply_to=(),
        references=(),
        headers_observed=True,
        reply_headers_present=False,
    )
    anonymous_child = MessageHeaderView(
        message_id="g2",
        rfc_message_id=None,
        in_reply_to=(msgid("g1"),),
        references=(),
        headers_observed=True,
        reply_headers_present=True,
    )
    links = {link.message_id: link for link in reconstruct((root, anonymous_child)).links}
    assert links["g2"].linkage is Linkage.IN_REPLY_TO
    assert links["g2"].parent_id == "g1"
    assert links["g2"].can_be_a_parent is False
    assert links["g1"].can_be_a_parent is True
    # And the shape D.4a's sentence is actually about: no Message-ID and no parent named.
    orphan = replace(anonymous_child, in_reply_to=(), reply_headers_present=False)
    only = {link.message_id: link for link in reconstruct((root, orphan)).links}
    assert only["g2"].linkage is Linkage.NO_MESSAGE_ID


def test_the_generator_reaches_every_shape_this_round_names() -> None:
    """A property over generated input is worth nothing if the generator is narrow.

    `SHAPES` is the list this round would otherwise have written nine tests for. Each one is
    asserted **reachable** from the real corpus, so the commonality property above is known
    to be running over them and not only over trees the generator found convenient.
    """
    _box, envelope = answer(MARKER)
    seen = {row.linkage for row in every_row(envelope).values()}
    missing = {name: gap for name, gap in SHAPES.items() if gap not in seen}
    assert missing == {}, missing


def test_every_value_of_the_linkage_vocabulary_is_one_the_product_can_produce() -> None:
    """A closed vocabulary wider than the code is a claim wider than the code.

    Eight of the nine members arrive from the ordinary corpus. The ninth,
    `HEADERS_UNOBSERVED`, needs PF-2's third branch - a `threads.get` row carrying
    `internalDate` and no `payload` - which is a shape no earlier fixture in this repository
    could produce and is exactly the sort of member that ends up written down and never
    reached. Both runs are here, together, so the enum is covered by execution rather than
    by declaration.
    """
    _box, ordinary = answer(MARKER)
    headerless = SyntheticMailbox(
        messages=corpus(), now_ms=epoch_ms(2026, 9, 3), metadata_returns_headers=False
    )
    _box2, unobserved = answer(MARKER, box=headerless)
    reached = {row.linkage for row in every_row(ordinary).values()} | {
        row.linkage for row in every_row(unobserved).values()
    }
    assert reached == set(Linkage), set(Linkage) - reached
    # The headerless run maps its threads and orders them; what it loses is the tree, and it
    # says so on every row rather than presenting an unlinked thread as an ordinary one.
    plain = next(s for s in unobserved.sources if s.thread_id == "t-plain")
    assert plain.included == plain.stated_total == 3
    assert plain.structure is not None
    assert plain.structure.linked == 0
    assert plain.structure.authorship_unknown == ("p1", "p2", "p3")
    assert plain.structure.mentions_not_scanned == ("p1", "p2", "p3")


def test_every_participant_role_is_one_an_index_can_actually_report() -> None:
    """The same question of the other closed vocabulary this round adds.

    `ParticipantRole` names five things an address can be in one message, and a vocabulary
    whose members no code path produces is documentation wearing an enum's clothes.
    `ParticipantFacts.roles_in` is the producer, and `t-hearsay` exercises all five: mallory
    authored `h1`, bo was one of its recipients, fin was its `Reply-To`, eve is named in its
    body, and `h4`'s two-address `From` makes ana and bo co-authors.

    An address can hold more than one role in one message, which is why this returns a set:
    collapsing it would need a precedence rule nobody has a reason for, and the first thing
    such a rule would lose is the distinction STR-02 scores.
    """
    box = mailbox()
    client = make_client(box)
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run(MARKER, now=NOW, zone=UTC_ZONE)
    envelope = assemble(run, client=client, ledger=ledger)
    thread = next(s for s in envelope.sources if s.thread_id == "t-hearsay")
    index = index_participants(
        [
            participants_of_message(
                message_id=message.id,
                headers={
                    "from": message.sender,
                    "to": ", ".join(message.to) or None,
                    "cc": ", ".join(message.cc) or None,
                    "reply-to": message.reply_to,
                },
                observed_text=ObservedText(text=message.body),
            )
            for message in box.thread("t-hearsay")
        ]
    )
    reached = {
        role
        for facts in index.by_address.values()
        for row in thread.messages
        for role in facts.roles_in(row.id)
    }
    assert reached == set(ParticipantRole), set(ParticipantRole) - reached
    assert index.by_address["mallory@elsewhere.invalid"].roles_in("h1") == {ParticipantRole.AUTHOR}
    assert index.by_address["eve@team.example"].roles_in("h1") == {ParticipantRole.MENTION}
    assert index.by_address["bo@team.example"].roles_in("h4") == {ParticipantRole.COAUTHOR}
    assert index.by_address["fin@team.example"].roles_in("h1") == {ParticipantRole.REPLY_TO}
    assert index.by_address["bo@team.example"].roles_in("h1") == {ParticipantRole.RECIPIENT}
    # And the response's own participant block is keyed on the same addresses, so the roles
    # above are roles of the people the response actually reports.
    assert {entry.address for entry in thread.participants} == set(index.by_address)


def test_a_message_row_carries_exactly_one_linkage_and_it_is_never_absent() -> None:
    """STR-01 at the wire: "messages that cannot be linked say so", on every row.

    Required by declaration rather than defaulted, for the reason `mailbox` is (OD-5): a row
    that omitted it would be a row whose linkage a reader has to infer, and the inference a
    reader makes from a thread printed in order is the one C-02a forbids.
    """
    _box, envelope = answer(MARKER)
    rows = every_row(envelope)
    assert rows
    assert all(isinstance(row.linkage, Linkage) for row in rows.values())

    payload = {
        "id": "m-1",
        "position": 0,
        "role": Role.STUB.value,
        "reason": {"kind": "thread_member", "thread_id": "t-1", "position": 0},
        "mailbox": {"observed": False},
        "depth": Depth.STUB.value,
        "unabridged": {"tool": ToolName.GET_MESSAGES.value, "args": {"ids": ["m-1"]}},
    }
    with pytest.raises(ValidationError):
        MessageRow.model_validate(payload)
    with_linkage = {**payload, "linkage": Linkage.HEADERS_UNOBSERVED.value}
    assert MessageRow.model_validate(with_linkage).linkage is Linkage.HEADERS_UNOBSERVED


def test_no_row_is_attached_to_a_parent_its_own_headers_do_not_name() -> None:
    """C-02a end to end: no silent re-parenting, over every shape in the corpus at once.

    The check is made against the mailbox's own message ids rather than against the
    reconstruction's output, so it is an independent statement: for every linked row, the
    parent it names is a message whose `Message-ID` appears in that row's own `In-Reply-To`
    or `References`. The "dumbest max" STR-01 warns about - link everything to the previous
    message by date - fails this on `t-broken`, `t-subject`, `t-cycle` and `t-nomsgid`.
    """
    box, envelope = answer(MARKER)
    source_of = {message.id: message for message in box.messages}
    linked = 0
    for row in every_row(envelope).values():
        message = source_of[row.id]
        named = f"{message.in_reply_to or ''} {message.references or ''}"
        if row.linkage in RESOLVED_LINKAGES:
            assert row.reply_parent_id is not None
            parent = source_of[row.reply_parent_id]
            assert parent.message_id_header is not None
            assert parent.message_id_header in named, (row.id, named)
            linked += 1
        else:
            assert row.reply_parent_id is None, row.id
    assert linked >= 4, "the sweep found almost no links; it is not exercising the tree"


@pytest.mark.parametrize(
    ("thread_id", "message_id", "gap"),
    [
        ("t-broken", "b2", Linkage.UNPARSEABLE_REPLY_HEADERS),
        ("t-subject", "s3", Linkage.NO_REPLY_HEADERS),
        ("t-forward", "f1", Linkage.UNRESOLVED_PARENT),
        ("t-cycle", "c1", Linkage.REPLY_CYCLE),
        ("t-cycle", "c2", Linkage.REPLY_CYCLE),
        ("t-self", "r1", Linkage.REPLY_CYCLE),
        ("t-dup", "d3", Linkage.AMBIGUOUS_PARENT),
        ("t-nomsgid", "n1", Linkage.NO_MESSAGE_ID),
        ("t-nomsgid", "n2", Linkage.UNRESOLVED_PARENT),
    ],
)
def test_each_declared_gap_is_the_one_the_headers_actually_produce(
    thread_id: str, message_id: str, gap: Linkage
) -> None:
    """The gap vocabulary discriminates: these nine rows are in nine states, not one.

    A reconstruction could satisfy every property above by declaring *every* message
    unlinked under one value, so the value has to be checked too. It is derived from what
    the headers said and never from where the message sits: `s3` and `b2` are adjacent rows
    of similar-looking threads and land in different gaps because one carried no reply
    header and the other carried an unreadable one.
    """
    _box, envelope = answer(MARKER)
    row = rows_of(envelope, thread_id)[message_id]
    assert row.linkage is gap
    assert row.reply_parent_id is None


def test_a_subject_change_mid_thread_does_not_break_a_link_the_headers_support() -> None:
    """The other half of the subject-change shape, and the one a heuristic gets wrong.

    A reconstruction that grouped by normalised subject would split `s2` off from `s1`,
    because `s2` renamed the thread. The headers say otherwise and the headers decide.
    """
    _box, envelope = answer(MARKER)
    rows = rows_of(envelope, "t-subject")
    assert rows["s2"].linkage is Linkage.IN_REPLY_TO
    assert rows["s2"].reply_parent_id == "s1"


def test_a_reply_tree_over_two_rows_under_one_gmail_id_is_refused_rather_than_collapsed() -> None:
    """Every guarantee here is per message, and two rows under one id have no single answer.

    Raised rather than deduplicated, on amendment A3's reasoning for an out-of-range
    position: collapsing two rows into one moves evidence exactly as quietly as clamping
    does. The product never reaches this - `_thread_scalars` already refuses to seal
    positions for such a thread and `assemble` withholds it whole - which is why the refusal
    is asserted here, at the function a later caller will reach for.
    """
    twin = MessageHeaderView(
        message_id="g1",
        rfc_message_id=msgid("g1"),
        in_reply_to=(),
        references=(),
        headers_observed=True,
        reply_headers_present=False,
    )
    with pytest.raises(ThreadStructureError):
        reconstruct((twin, replace(twin, rfc_message_id=msgid("other"))))


# --- ordering: chronological, never the array Gmail sent ----------------------------------


def _comparable(envelope: Envelope) -> list[tuple[str, str, int, str, str | None]]:
    """The part of a response that must not depend on the order Gmail sent its array in."""
    return [
        (source.thread_id, row.id, row.position, row.linkage.value, row.reply_parent_id)
        for source in envelope.sources
        for row in source.messages
    ]


def test_the_array_order_gmail_returns_does_not_change_the_representation() -> None:
    """STR-03, on a mailbox where the two orders genuinely differ.

    Gmail does not promise `threads.get` returns `messages[]` sorted, and every fixture in
    this repository before this round returned it in `internalDate` order - which is exactly
    how an array-order dependence survives a suite: with the two orders always equal, code
    that reads the array index and code that reads `internalDate` are indistinguishable.
    Here the second run reverses every thread's array and the whole representation is
    compared.
    """
    _forward, chronological = answer(MARKER)
    _reversed_box, reversed_array = answer(
        MARKER, box=mailbox(thread_array_order=lambda rows: tuple(reversed(rows)))
    )
    assert _comparable(chronological) == _comparable(reversed_array)
    rows = rows_of(chronological, "t-plain")
    assert [rows[message_id].position for message_id in ("p1", "p2", "p3")] == [0, 1, 2]


def test_two_messages_stamped_in_the_same_millisecond_order_the_same_way_either_way() -> None:
    """The shape the array-index tie-break hid, and the declaration that replaces it.

    Positions used to break an `internalDate` tie by array index, so a thread with two
    messages stamped in the same millisecond - a self-copy, a list expansion, a resend -
    ordered itself by the order Gmail happened to send. The tie-break is now the message id,
    which is a fact of the response rather than of its ordering, and the response *declares*
    the tie: with equal timestamps every relative order is chronologically valid, and saying
    nothing would let the position claim read as stronger than the evidence behind it.
    """
    _box, chronological = answer(MARKER)
    _reversed_box, reversed_array = answer(
        MARKER, box=mailbox(thread_array_order=lambda rows: tuple(reversed(rows)))
    )
    for envelope in (chronological, reversed_array):
        rows = rows_of(envelope, "t-tie")
        assert [rows[message_id].position for message_id in ("w1", "w2")] == [0, 1]
    tie = next(s for s in chronological.sources if s.thread_id == "t-tie")
    assert tie.structure is not None
    assert set(tie.structure.tied_on_internal_date) == {"w1", "w2"}
    plain = next(s for s in chronological.sources if s.thread_id == "t-plain")
    assert plain.structure is not None
    assert plain.structure.tied_on_internal_date == ()


def test_a_position_is_an_index_into_chronological_order_and_the_rows_are_in_it() -> None:
    """STR-04/A3: positions are 0-based, contiguous, and the rows arrive in that order."""
    _box, envelope = answer(MARKER)
    for source in envelope.sources:
        positions = [row.position for row in source.messages]
        assert positions == sorted(positions)
        assert positions == list(range(source.stated_total))
        assert source.included == source.stated_total


def test_a_thread_map_will_not_invent_a_position_the_observation_declined_to_state() -> None:
    """The map raises rather than sorting for itself, which is A3's rule one layer up.

    `assemble` never lets this happen - a thread whose observation stated no chronological
    order is withheld whole - so the refusal is asserted at the function, where the next
    caller will meet it.
    """
    box = mailbox()
    client = make_client(box)
    ledger = DispositionLedger()
    recorded = client.get_thread(ledger, thread_id="t-plain", rung=RungId.L1)
    with pytest.raises(ThreadStructureError):
        build_thread_map(
            thread_id="t-plain",
            messages=recorded.thread.messages,
            positions={"p1": 0},
        )


# --- authorship is not mention ------------------------------------------------------------


def _participants(envelope: Envelope, thread_id: str) -> dict[str, ThreadParticipant]:
    source = next(s for s in envelope.sources if s.thread_id == thread_id)
    return {entry.address: entry for entry in source.participants}


def test_an_address_a_message_only_names_is_not_an_address_that_wrote_it() -> None:
    """STR-02's whole subject, with the distractor planted in the corpus.

    `h1` is authored by `mallory@elsewhere.invalid` and its body names
    `eve@team.example`. A system that answered "what did eve say" with `h1` would be
    answering "who decided this?" with the person the message talks *about*. The two facts
    live in different fields and `wrote_here` is computed from the authorship lists rather
    than accepted beside them.
    """
    _box, envelope = answer(MARKER)
    people = _participants(envelope, "t-hearsay")
    mallory = people["mallory@elsewhere.invalid"]
    eve = people["eve@team.example"]

    assert mallory.authored == ("h1",)
    assert mallory.wrote_here is True
    assert "h1" in eve.mentioned
    assert "h1" not in eve.authored and "h1" not in eve.coauthored
    # Eve did write in this thread - h2 - which is what makes the distinction non-trivial:
    # the same address is an author of one message and hearsay in another.
    assert eve.authored == ("h2",)
    assert eve.wrote_here is True


def test_a_display_name_cannot_make_someone_the_author_of_a_message() -> None:
    """C-02b/INJ-05: identity is the address, and a display name is disclosed beside it.

    `h1` presents itself as "Ana Ito" and is sent from `mallory@elsewhere.invalid`. Ana's
    real address authored nothing in this thread, and the response says so.

    **Round 31 changed what this test asserts, and towards the requirement.** Until INJ-05
    the check was that the string "Ana" appeared nowhere in the index, on the reasoning that
    there was no field a display name could arrive in - which was true and is no longer the
    posture the work order asks for. Suppressing the name protects the *index* and leaves the
    reader with no way to see the impersonation at all: the row named Mallory's address and
    the mail client the reader is looking at says "Ana Ito". The requirement is that the name
    is *split from* the identity, not hidden: it is disclosed, it is fenced as untrusted
    third-party text, it hangs off each address that actually used it, and it confers nothing.

    The sharpest form of that last clause is in this fixture already: "Ana Ito" is used by
    two different addresses in one thread - Mallory's, on `h1`, and Ana's own, on `h4` - so
    the index shows the same name under both records while authorship stays where the
    addresses put it. A design that joined the name to an identity would have had to pick one
    of them, and picking is the failure. So this asserts that *both* records carry the name,
    that neither gains a message from it, and that it appears in no other field of any record.
    """
    _box, envelope = answer(MARKER)
    people = _participants(envelope, "t-hearsay")
    assert "ana@team.example" not in {a for a, p in people.items() if p.authored}
    assert people["mallory@elsewhere.invalid"].authored == ("h1",)
    # Singular: there is still no scalar a display name can be joined to an identity in.
    assert "display_name" not in ThreadParticipant.model_fields
    mallory = people["mallory@elsewhere.invalid"]
    assert [unfence(envelope.fence_nonce, name.text) for name in mallory.display_names] == [
        "Ana Ito"
    ]
    assert all(name.trust is Trust.UNTRUSTED_THIRD_PARTY for name in mallory.display_names)
    dumped = next(s for s in envelope.sources if s.thread_id == "t-hearsay").model_dump(
        mode="json"
    )["participants"]
    carrying = {entry["address"] for entry in dumped if "Ana Ito" in repr(entry["display_names"])}
    assert carrying == {"mallory@elsewhere.invalid", "ana@team.example"}, carrying
    # The name is shared; the authorship is not.
    assert people["mallory@elsewhere.invalid"].authored == ("h1",)
    assert "h1" not in people["ana@team.example"].authored
    # And nowhere but `display_names`: no role list, no scalar, no reason string.
    for entry in dumped:
        without = {key: value for key, value in entry.items() if key != "display_names"}
        assert "Ana" not in repr(without), entry["address"]


def test_a_from_naming_two_people_is_coauthorship_and_is_not_promoted_to_authorship() -> None:
    """RFC 5322 permits a multi-mailbox `From`, and the headers do not say who held the pen.

    Promoting either address to sole authorship would attribute one person's words to
    another on the strength of a header shape. Both are recorded, in a role that says what
    is actually known.
    """
    _box, envelope = answer(MARKER)
    people = _participants(envelope, "t-hearsay")
    assert people["ana@team.example"].coauthored == ("h4",)
    assert people["ana@team.example"].authored == ()
    assert people["bo@team.example"].coauthored == ("h4",)
    assert len({role.value for role in ParticipantRole}) == len(list(ParticipantRole))
    assert ParticipantRole.COAUTHOR in set(ParticipantRole) - {ParticipantRole.AUTHOR}


def test_a_message_with_no_readable_from_has_no_author_and_the_response_says_so() -> None:
    """The case where authorship cannot be told: it is declared, never inferred.

    Not attributed to the previous message's sender, not to the thread's root, not at all.
    `h3` carries a `From` that is prose, so no address is extractable from it and the
    structural report lists the message under `authorship_unknown`.
    """
    _box, envelope = answer(MARKER)
    source = next(s for s in envelope.sources if s.thread_id == "t-hearsay")
    assert source.structure is not None
    assert "h3" in source.structure.authorship_unknown
    for entry in source.participants:
        assert "h3" not in entry.authored and "h3" not in entry.coauthored


def test_reply_to_is_a_routing_directive_and_never_authorship() -> None:
    """A sender that writes one header must not be able to attribute their message elsewhere."""
    _box, envelope = answer(MARKER)
    people = _participants(envelope, "t-hearsay")
    assert people["fin@team.example"].reply_to == ("h1",)
    assert people["fin@team.example"].wrote_here is False


def test_when_no_text_was_observed_mentions_are_declared_unscanned_rather_than_absent() -> None:
    """PF-2's branch, and the negative-from-an-absence defect this repository keeps finding.

    With no body and no snippet for a row, "no mentions" would be a claim derived from
    nothing having looked. The index lists the message under `mentions_not_scanned` instead,
    which is the same third state `MailboxProvenance.observed` draws.
    """
    record = participants_of_message(
        message_id="m-1",
        headers={"from": "Ana Ito <ana@team.example>"},
        observed_text=None,
    )
    assert record.mentions == ()
    assert record.text_observed is False
    assert record.mentions_scanned is False
    index = index_participants([record])
    assert index.mentions_unscanned == ("m-1",)
    scanned = participants_of_message(
        message_id="m-1",
        headers={"from": "Ana Ito <ana@team.example>"},
        observed_text=ObservedText(text="nobody is named here"),
    )
    assert index_participants([scanned]).mentions_unscanned == ()
    # And the other way a mention cannot be looked for, which is the narrower one: a snippet
    # arrived and the headers did not, so there is nothing to tell a mention apart from a
    # participant. `text_observed` stays true - it is a fact about this response - and
    # `mentions_scanned` is the derived question a caller actually has.
    headerless = participants_of_message(
        message_id="m-2", headers=None, observed_text=ObservedText(text="ana@team.example was here")
    )
    assert headerless.text_observed is True
    assert headerless.mentions_scanned is False
    assert headerless.mentions == ()
    assert index_participants([headerless]).mentions_unscanned == ("m-2",)


def test_under_pf2s_no_snippet_branch_the_unscanned_rows_are_named_end_to_end() -> None:
    """The same third state, reached through the real client rather than at the unit.

    PF-2 leaves it open whether `format=metadata` returns `snippet` at all. Under the branch
    where it does not, a row this response fetched no body for has no text, and the two
    kinds of row in one thread are the point: `h1`'s body was fetched because it matched, so
    its mentions were scanned and `eve@team.example` is recorded as named in it; `h2`-`h4`
    were not, so they are listed as unscanned rather than reported as mentioning nobody.
    """
    box = SyntheticMailbox(
        messages=corpus(), now_ms=epoch_ms(2026, 9, 3), metadata_returns_snippet=False
    )
    _box, envelope = answer(MARKER, box=box)
    source = next(s for s in envelope.sources if s.thread_id == "t-hearsay")
    assert source.structure is not None
    assert source.structure.mentions_not_scanned == ("h2", "h3", "h4")
    people = _participants(envelope, "t-hearsay")
    assert people["eve@team.example"].mentioned == ("h1",)
    # And the whole thread is still mapped and ordered: losing the snippet costs mentions,
    # not the map.
    assert source.included == source.stated_total == 4


def test_a_bare_name_in_text_is_never_resolved_to_an_address() -> None:
    """The second thing the index says it cannot tell, executed rather than written down.

    Mapping "Ana said so" to `ana@team.example` needs a directory this product does not
    have, and inventing one is the same class of guess as re-parenting an orphan by date.
    The response carries the statement, so an empty `mentioned` list cannot be misread as
    "nobody was named".
    """
    assert name_only_mentions_are_not_resolved is True
    assert addresses_in_text(ObservedText(text="Ana said we should ship, and Bo agreed")) == ()
    assert addresses_in_text(ObservedText(text="ana@team.example said so")) == ("ana@team.example",)
    _box, envelope = answer(MARKER)
    for source in envelope.sources:
        assert source.structure is not None
        assert source.structure.name_only_mentions_resolved is False
    with pytest.raises(ValidationError):
        ThreadStructureReport(linked=0, unlinked=0, name_only_mentions_resolved=True)


def test_header_text_that_is_really_prose_never_becomes_an_address() -> None:
    """`getaddresses` hands back the whole value for a header it cannot parse (R-SEC-030/032).

    Its output is a candidate, not a result, and a field named `address` that accepted prose
    would be a route for mail text onto the wire under a name that says it is metadata.
    """
    assert addresses_in_header("Please review the attached NDA before end of day.") == ()
    assert addresses_in_header("ops list, no address here") == ()
    assert addresses_in_header("Ana Ito <ana@team.example>") == (("Ana Ito", "ana@team.example"),)
    with pytest.raises(ValidationError):
        ThreadParticipant(address="Please review the attached NDA before end of day.")


def test_an_address_that_used_two_display_names_is_counted_rather_than_quoted() -> None:
    """The one question a display name can honestly answer, answered as a number."""
    records = [
        participants_of_message(
            message_id="m-1",
            headers={"from": '"Ana Ito" <ana@team.example>'},
            observed_text=ObservedText(text=""),
        ),
        participants_of_message(
            message_id="m-2",
            headers={"from": '"A. Ito (mobile)" <ana@team.example>'},
            observed_text=ObservedText(text=""),
        ),
    ]
    index = index_participants(records)
    assert index.by_address["ana@team.example"].distinct_display_names == 2
    assert index.by_address["ana@team.example"].authored == ("m-1", "m-2")


def test_the_participant_index_cannot_cite_a_message_the_source_does_not_disclose() -> None:
    """A structural claim is about the payload beside it, and is checked against it."""
    with pytest.raises(ValidationError):
        Source(
            thread_id="t-1",
            stated_total=0,
            included=0,
            included_as_stub=0,
            fetched_at="2026-09-03T09:00:00Z",
            participants=(ThreadParticipant(address="ana@team.example", authored=("m-9",)),),
        )


def test_one_address_cannot_be_both_the_author_and_the_hearsay_of_one_message() -> None:
    """The two sets are disjoint by construction, and the model refuses a response where not.

    A mention is an address in text that this message's own address headers do not account
    for, so the sender quoting their own address is not hearsay about themselves. Enforced
    at the model as well as computed correctly, because this is the one distinction STR-02
    scores and a second producer would otherwise be free to get it wrong.
    """
    with pytest.raises(ValidationError):
        ThreadParticipant(address="ana@team.example", authored=("m-1",), mentioned=("m-1",))
    record = participants_of_message(
        message_id="m-1",
        headers={"from": "Ana Ito <ana@team.example>"},
        observed_text=ObservedText(text="writing from ana@team.example about bo@team.example"),
    )
    assert record.mentions == ("bo@team.example",)


# --- declared gaps travel in the response -------------------------------------------------


def test_the_structural_report_cannot_disagree_with_the_rows_it_summarises() -> None:
    """A count beside an enumeration is a second claim about one fact (round 18's lesson)."""
    _box, envelope = answer(MARKER)
    for source in envelope.sources:
        assert source.structure is not None
        linked = sum(1 for row in source.messages if row.linkage in RESOLVED_LINKAGES)
        assert source.structure.linked == linked
        assert source.structure.unlinked == len(source.messages) - linked

    kit_row = MessageRow(
        id="m-1",
        position=0,
        role=Role.STUB,
        reason=ThreadMember(thread_id="t-1", position=0),
        mailbox=MailboxProvenance.unobserved(),
        depth=Depth.STUB,
        linkage=Linkage.NO_REPLY_HEADERS,
        can_be_a_parent=True,
        unabridged={"tool": ToolName.GET_MESSAGES, "args": {"ids": ["m-1"]}},  # type: ignore[arg-type]
    )
    with pytest.raises(ValidationError):
        Source(
            thread_id="t-1",
            stated_total=1,
            included=1,
            included_as_stub=1,
            fetched_at="2026-09-03T09:00:00Z",
            messages=(kit_row,),
            structure=ThreadStructureReport(linked=1, unlinked=0),
        )


def test_a_parent_beside_a_declared_gap_is_not_representable() -> None:
    """C-02a's silent re-parenting, refused at the schema as well as at the reconstruction.

    Two layers because this model is reachable from callers `reply_tree` is not on the path
    of, and one of them is WS-11's disclosure ladder, which does not exist yet.
    """
    base = {
        "id": "m-1",
        "position": 0,
        "role": Role.STUB.value,
        "reason": {"kind": "thread_member", "thread_id": "t-1", "position": 0},
        "mailbox": {"observed": False},
        "depth": Depth.STUB.value,
        # Round 21: every linkage below says this row's headers were observed, so
        # `can_be_a_parent` has to be stated (R-RETR-054). Without it these documents are
        # refused by *that* validator and this test passes while asserting nothing about the
        # one it is named for - which the replant harness reported as R40 MISSED.
        "can_be_a_parent": True,
        "unabridged": {"tool": ToolName.GET_MESSAGES.value, "args": {"ids": ["m-1"]}},
    }
    with pytest.raises(ValidationError):
        MessageRow.model_validate(
            {**base, "linkage": Linkage.NO_REPLY_HEADERS.value, "reply_parent_id": "m-0"}
        )
    with pytest.raises(ValidationError):
        MessageRow.model_validate({**base, "linkage": Linkage.IN_REPLY_TO.value})
    with pytest.raises(ValidationError):
        MessageRow.model_validate(
            {**base, "linkage": Linkage.IN_REPLY_TO.value, "reply_parent_id": "m-1"}
        )


def test_a_reply_parent_outside_the_thread_is_not_representable() -> None:
    """A parent is a message of the same thread; a reference elsewhere is a declared gap."""
    row = MessageRow(
        id="m-2",
        position=1,
        role=Role.STUB,
        reason=ThreadMember(thread_id="t-1", position=1),
        mailbox=MailboxProvenance.unobserved(),
        depth=Depth.STUB,
        linkage=Linkage.IN_REPLY_TO,
        reply_parent_id="m-elsewhere",
        can_be_a_parent=True,
        unabridged={"tool": ToolName.GET_MESSAGES, "args": {"ids": ["m-2"]}},  # type: ignore[arg-type]
    )
    with pytest.raises(ValidationError):
        Source(
            thread_id="t-1",
            stated_total=1,
            included=1,
            included_as_stub=1,
            fetched_at="2026-09-03T09:00:00Z",
            messages=(row,),
            structure=ThreadStructureReport(linked=1, unlinked=0),
        )


def test_a_structurally_included_row_names_the_relation_that_put_it_there() -> None:
    """C-02d/R-03: a mechanical reason naming the relation, never "relevant".

    `ReplyParentOf` and `ReplyChildOf` have existed in `reasons.py` since WS-03 with nothing
    able to produce them; this round is the producer, so the reason vocabulary stops being
    wider than the code.
    """
    _box, envelope = answer(MARKER)
    rendered = {
        row.id: (row.role, row.rendered_reason)
        for source in envelope.sources
        for row in source.messages
    }
    assert rendered["p1"] == (Role.PARENT, "reply parent of p2")
    assert rendered["p3"] == (Role.CHILD, "reply child of p2")
    assert isinstance(rows_of(envelope, "t-plain")["p1"].reason, ReplyParentOf) and isinstance(
        rows_of(envelope, "t-plain")["p3"].reason, ReplyChildOf
    )
    assert all(reason for _role, reason in rendered.values())


# --- L4: structural expansion into another thread -----------------------------------------


def test_a_reply_whose_parent_is_in_another_thread_recovers_it_as_its_own_source() -> None:
    """STR-05/C-02e: evidence split across threads comes back as multiple sources.

    `f1` forwards a message that lives in `t-elsewhere`, which carries no marker of its own,
    so a lexical rung cannot reach it. L4 asks Gmail for it by `rfc822msgid:` - an exact
    identifier lookup, not a resemblance - and the thread arrives as a separate source with
    its own map and its own total.
    """
    _box, envelope = answer(MARKER)
    threads = {source.thread_id for source in envelope.sources}
    assert "t-elsewhere" in threads
    sibling = next(s for s in envelope.sources if s.thread_id == "t-elsewhere")
    assert sibling.stated_total == 2
    assert sibling.included == 2
    assert sibling.structure is not None
    assert RungId.L4 in envelope.retrieval_report.rungs


def test_no_row_of_a_recovered_thread_claims_the_query_matched_it() -> None:
    """The mechanical reason for a row no query matched (R-03, C-02d).

    The probe that found `e1` is a `Message-ID` lookup **MailWeave composed** out of `f1`'s
    headers, so `gmail q matched at L4: rfc822msgid:<e1@mail.invalid>` would name the
    mechanism and not the relation - and `role: matched` on a message the caller's query
    never touched is exactly the confident-looking over-claim this project exists to
    prevent. `e1` says `reply parent of f1`, which is the relation that put it here; `e2`
    says `reply child of e1`, which is *its* relation and not a copy of `e1`'s, because
    copying one row's claim onto its neighbours is the decorative reason PART-07 forbids
    wearing a mechanical shape.
    """
    _box, envelope = answer(MARKER)
    rows = rows_of(envelope, "t-elsewhere")
    assert rows["e1"].role is Role.PARENT
    assert rows["e1"].rendered_reason == "reply parent of f1"
    assert rows["e2"].role is Role.CHILD
    assert rows["e2"].rendered_reason == "reply child of e1"
    assert Role.MATCHED not in {row.role for row in rows.values()}


@pytest.mark.parametrize("fragment", REGION_DECLARING_FRAGMENTS)
def test_structural_expansion_carries_the_region_the_query_named(fragment: str) -> None:
    """A9-A2/OD-5 point 3, over the operator family rather than over a list of operators.

    Anything this repository composes inherits the region rule by *calling*
    `search_region_of`, not by restating it, so a region operator nobody has added yet is
    carried onto L4's probes too. The population is read from the registry
    (`REGION_DECLARING_FRAGMENTS`), which is why this is one test rather than a sweep that
    has to be extended when the lexicon grows.
    """
    parsed = analyse(f"{fragment} {MARKER}", now=NOW, zone=UTC_ZONE)
    plan = plan_structural_expansion(parsed, [("f1", msgid("e1"))])
    assert plan.probes, fragment
    for structural in plan.probes:
        assert fragment in structural.probe.query, (fragment, structural.probe.query)
        assert "in:anywhere" not in structural.probe.query or "anywhere" in fragment


def test_an_unprobeable_message_id_is_declared_rather_than_pasted_into_a_query() -> None:
    """A `Message-ID` carrying query punctuation would change the query it is pasted into.

    Skipped and declared, never truncated: `rfc822msgid:` is an exact-match operator, so a
    shortened identifier is a different identifier and a probe for it would be a probe for
    something else.
    """
    parsed = analyse(MARKER, now=NOW, zone=UTC_ZONE)
    hostile = '<a"b{c}@mail.invalid>'
    huge = "<" + "z" * 400 + "@mail.invalid>"
    assert not is_probeable(hostile) and not is_probeable(huge)
    assert is_probeable(msgid("e1"))
    plan = plan_structural_expansion(parsed, [("f1", hostile), ("f2", huge)])
    assert plan.probes == ()
    assert {pair[1] for pair in plan.skipped} == {hostile, huge}


def test_two_children_of_one_absent_parent_are_one_lookup() -> None:
    """I-3: the cheap path stays cheap, and a duplicate probe is quota with no new answer."""
    parsed = analyse(MARKER, now=NOW, zone=UTC_ZONE)
    plan = plan_structural_expansion(parsed, [("f1", msgid("e1")), ("f2", msgid("e1"))])
    assert len(plan.probes) == 1
    assert plan.probes[0].for_child_id == "f1"


def test_more_unresolved_parents_than_the_probe_cap_are_declared_not_dropped() -> None:
    """OD-2's distinction at L4: a cap is `cap`, and it carries a way to ask for more."""
    parsed = analyse(MARKER, now=NOW, zone=UTC_ZONE)
    pairs = [(f"c{index}", msgid(f"p{index}")) for index in range(MAX_STRUCTURAL_PROBES + 3)]
    plan = plan_structural_expansion(parsed, pairs)
    assert len(plan.probes) == MAX_STRUCTURAL_PROBES
    assert len(plan.over_cap) == 3


def test_sibling_threads_beyond_the_cap_are_withheld_rather_than_dropped() -> None:
    """`max_source_threads` converts a thread into withheld records, never into silence.

    Driven with the cap at zero rather than by building five sibling threads: the question
    is what the cap *does*, and a corpus large enough to trip the real value would make the
    test about the corpus. Every id L4 admitted is still in `H`, so the disposition ledger
    would refuse the response outright if one of them had no disposition - which is the
    check underneath this assertion and the reason it is worth making.
    """
    box = mailbox()
    client = make_client(box)
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run(MARKER, now=NOW, zone=UTC_ZONE)
    envelope = assemble(run, client=client, ledger=ledger, max_source_threads=0)

    assert "t-elsewhere" not in {source.thread_id for source in envelope.sources}
    # Round 29: a thread the cap withholds is recovered by one `mailweave_thread_map` call,
    # so it is written at that granularity - one group naming the thread, not one record
    # per message. The message id is still accounted for (`withheld_ids` spans both forms).
    assert "e1" in envelope.withheld_ids
    assert "e1" not in {record.id for record in envelope.withheld}
    groups = {group.thread_id: group for group in envelope.withheld_groups}
    assert "t-elsewhere" in groups
    assert groups["t-elsewhere"].cap is WithheldCap.MAX_SOURCE_THREADS
    assert groups["t-elsewhere"].affordance.tool is ToolName.THREAD_MAP
    assert groups["t-elsewhere"].message_count == 1
    assert envelope.partial is True


def test_the_similarity_signals_this_round_did_not_build_are_named_in_the_response() -> None:
    """AD D.6 lists four sibling-discovery signals and this round implements one.

    The other three are similarity judgements rather than identifier lookups. An absent
    source would otherwise read as an absent relationship, which is the false half of the
    OD-2 distinction arriving through a different field.
    """
    _box, envelope = answer(MARKER)
    named = {entry.rung: entry.why for entry in envelope.retrieval_report.not_tried}
    assert STRUCTURAL_SIMILARITY_RUNG in named
    assert named[STRUCTURAL_SIMILARITY_RUNG].value == "not_applicable"


def test_l4_reports_itself_not_applicable_when_no_thread_held_an_unresolved_parent() -> None:
    """The honest `not_applicable`: the rung exists, and there was nothing for it to chase."""
    box = SyntheticMailbox(messages=plain_thread(), now_ms=epoch_ms(2026, 9, 3))
    _box, envelope = answer(MARKER, box=box)
    report = envelope.retrieval_report
    assert RungId.L4 not in report.rungs
    entry = next(e for e in report.not_tried if e.rung == RungId.L4.value)
    assert entry.why.value == "not_applicable"


# --- the ledger still accounts for everything ---------------------------------------------


def test_every_message_the_ladder_and_the_expansion_saw_is_still_accounted_for() -> None:
    """I-1 with a second route putting ids into `H`.

    The disposition ledger computes `withheld := H - disclosed` at envelope time and refuses
    a residue with no cap note, so this assertion is a statement that the *response built at
    all* - and it is worth making because L4 is the first route since WS-04 to add ids to
    `H` outside the lexical ladder. A cap that enumerated only what it knew about would
    under-count by exactly the ids the newer route contributed.
    """
    for query in (MARKER, f"{MARKER} {ABSENT}", ABSENT, f"-in:spam {MARKER}"):
        box = mailbox()
        client = make_client(box)
        ledger = DispositionLedger()
        run = LadderRunner(client, ledger).run(query, now=NOW, zone=UTC_ZONE)
        envelope = assemble(run, client=client, ledger=ledger)
        disclosed = {row.id for source in envelope.sources for row in source.messages}
        accounted = disclosed | {record.id for record in envelope.withheld}
        assert ledger.hit_ids <= accounted, query


def test_the_expansion_never_leaves_the_region_the_query_named_at_the_wire() -> None:
    """The same invariant as the plan-level sweep, executed against the real transport.

    `-in:spam` must never search spam, and an L4 probe is a `messages.list` like any other,
    so it is one of the probes that has to carry the exclusion. Read off the double's own
    record of what it was asked, which is the content witness this harness can be.
    """
    box = mailbox()
    client = make_client(box)
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run(f"-in:spam {MARKER}", now=NOW, zone=UTC_ZONE)
    assemble(run, client=client, ledger=ledger)
    assert box.queries
    for query, include_spam_trash in box.queries:
        assert "-in:spam" in query, query
        assert include_spam_trash is False, query


def test_one_threads_get_per_thread_and_never_two() -> None:
    """AD A.7/I-3: one `threads.get` per hit-bearing thread, deduped per query.

    The map is carried from the fetch pass to the row-building pass rather than re-fetched,
    and L4's sibling threads are fetched once each too.
    """
    box, envelope = answer(MARKER)
    disclosed = {source.thread_id for source in envelope.sources}
    assert box.calls["threads.get"] == len(disclosed) + len(envelope.not_included_sources)


# --- fixture hygiene ----------------------------------------------------------------------


def test_no_fixture_in_this_file_carries_anything_that_could_be_real_mail() -> None:
    """OD-4 and the work order's own constraint, executed rather than promised.

    Every address literal in this module is under a reserved TLD (RFC 2606/6761), so nothing
    here can be a real mailbox, and no subject or body was copied from one.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    addresses = {
        match
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        for match in re.findall(r"[\w.+-]+@[\w.-]+", node.value)
    }
    assert addresses, "the sweep found no addresses; it is reading the wrong thing"
    for address in addresses:
        domain = address.rsplit("@", 1)[1].rstrip(">.")
        assert domain.endswith((".example", ".invalid", ".test", ".localhost")), address
