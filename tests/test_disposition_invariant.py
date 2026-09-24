"""The withheld invariant: `withheld := H - disclosed`, and the ways it must fail loudly.

These tests are the reason the project exists. A suite that only shows the happy path has
not tested the assertion, so every residue the ledger can detect gets its own failing case.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from mailweave.envelope import (
    Depth,
    DispositionLedger,
    EnvelopeBuilder,
    Linkage,
    Outcome,
    Role,
    RungId,
    Sufficiency,
    ToolName,
    WithheldCap,
)
from mailweave.envelope.disposition import (
    CLAUSE_BY_ENDPOINT,
    DispositionCertificate,
    FetchedIds,
    ObservedEndpoint,
)
from mailweave.envelope.reasons import ThreadMember
from mailweave.envelope.response import Envelope
from mailweave.envelope.wire import (
    Affordance,
    MailboxProvenance,
    MessageRow,
    Source,
)
from mailweave.errors import DispositionInvariantError
from tests.fixtures import envelope_kit as kit


def cap_affordance(thread_id: str) -> Affordance:
    return Affordance(tool=ToolName.THREAD_MAP, args={"thread_id": thread_id})


def ledger_with_hits(
    *ids: str,
    rung: RungId = RungId.L1,
    thread: str | None = None,
    threads: Mapping[str, str] | None = None,
) -> DispositionLedger:
    """A ledger holding `ids`, optionally recording the thread the page put each one in.

    `thread`/`threads` are what the `messages.list` response said in its `threadId` field.
    A test that withholds an id has to supply one, because `certify` derives the withheld
    record's thread from the observation and refuses to invent it (R-DISC-009).
    """
    ledger = DispositionLedger()
    ledger.record_list_page(
        kit.fetched(ids, thread=thread, thread_ids=threads), rung=rung, query="from:amy launch"
    )
    return ledger


def build_answered(builder: EnvelopeBuilder, **kwargs: Any) -> Envelope:
    """Finish a builder a test has already loaded, with the boilerplate a report needs."""
    return builder.build(
        outcome=Outcome.ANSWERED,
        rungs=(RungId.L1,),
        sufficiency=Sufficiency.SUFFICIENT,
        counters=kit.counters(),
        **kwargs,
    )


def build(
    ledger: DispositionLedger,
    sources: Callable[[str], list[Source]],
    **kwargs: Any,
) -> Envelope:
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    for src in sources(builder.fence_nonce):
        builder.add_source(src)
    for affordance in kwargs.pop("affordances", ()):
        builder.add_affordance(affordance)
    return builder.build(
        outcome=kwargs.pop("outcome", Outcome.ANSWERED),
        rungs=(RungId.L1,),
        sufficiency=Sufficiency.SUFFICIENT,
        counters=kit.counters(),
        **kwargs,
    )


def test_all_hits_disclosed_yields_an_empty_withheld_list_and_a_full_certificate() -> None:
    """An empty `withheld` is a positive assertion, so the certificate must show H accounted for."""
    ledger = ledger_with_hits("m1", "m2")
    envelope = build(
        ledger,
        lambda nonce: [
            kit.source(
                "t1",
                [kit.row("m1", "t1", 0, nonce=nonce), kit.row("m2", "t1", 1, nonce=nonce)],
            )
        ],
    )

    assert envelope.withheld == ()
    assert ledger.hit_ids <= envelope.represented_ids
    assert envelope.disposition.hit_count == len(ledger.hit_ids)
    assert envelope.disposition.disclosed_hits == len(ledger.hit_ids)


def test_a_cap_that_records_its_reason_produces_a_derived_withheld_record() -> None:
    ledger = ledger_with_hits("m1", "m2", "m3", threads={"m1": "t1", "m2": "t1", "m3": "t9"})
    ledger.note_withheld(
        message_id="m3",
        cap=WithheldCap.MAX_HIT_THREADS,
        why="31 hit-bearing threads; 12 mapped",
        affordance=cap_affordance("t9"),
    )
    envelope = build(
        ledger,
        lambda nonce: [
            kit.source(
                "t1",
                [kit.row("m1", "t1", 0, nonce=nonce), kit.row("m2", "t1", 1, nonce=nonce)],
            )
        ],
    )

    assert envelope.withheld_ids == {"m3"}
    record = envelope.withheld[0]
    assert record.cap is WithheldCap.MAX_HIT_THREADS
    assert record.affordance.mentions("t9")
    # H is contained in R: nothing retrieved left the response unaccounted for.
    assert ledger.hit_ids <= envelope.represented_ids


def test_a_cap_that_forgets_to_record_a_dropped_hit_fails_loudly() -> None:
    """The whole point: forgetting produces an error, not a quietly shorter response."""
    ledger = ledger_with_hits("m1", "m2", "m3")  # m3 will simply vanish

    with pytest.raises(DispositionInvariantError) as failure:
        build(
            ledger,
            lambda nonce: [
                kit.source(
                    "t1",
                    [kit.row("m1", "t1", 0, nonce=nonce), kit.row("m2", "t1", 1, nonce=nonce)],
                )
            ],
        )

    assert "m3" in str(failure.value)
    assert "no withheld record" in str(failure.value)


def test_a_withheld_record_for_a_message_that_is_disclosed_is_rejected() -> None:
    """Depth reduction is not omission (A.7a).

    A stub row is disclosed, so a withheld record naming it is false.
    """
    ledger = ledger_with_hits("m1", thread="t1")
    ledger.note_withheld(
        message_id="m1",
        cap=WithheldCap.DISCLOSED_TOKEN_CEILING,
        why="did not fit",
        affordance=cap_affordance("t1"),
    )

    with pytest.raises(DispositionInvariantError) as failure:
        build(
            ledger,
            lambda nonce: [
                kit.source(
                    "t1",
                    [kit.row("m1", "t1", 0, nonce=nonce, depth=Depth.STUB, role=Role.STUB)],
                )
            ],
        )

    assert "disclosed" in str(failure.value)


def test_a_withheld_record_for_an_id_never_recorded_as_a_hit_is_rejected() -> None:
    """The deflationary bug: if H is under-counted the invariant would pass vacuously."""
    ledger = ledger_with_hits("m1", thread="t1")
    ledger.note_withheld(
        message_id="ghost",
        cap=WithheldCap.MAX_RECENCY_FETCH,
        why="beyond n",
        affordance=cap_affordance("t2"),
    )

    with pytest.raises(DispositionInvariantError) as failure:
        build(ledger, lambda nonce: [kit.source("t1", [kit.row("m1", "t1", 0, nonce=nonce)])])

    assert "not in H" in str(failure.value)


def test_collapsed_run_members_count_as_disclosed() -> None:
    """A.7a: a member of a declared collapsed run counts as present, so it is not withheld."""
    ledger = ledger_with_hits("m1", "m2", "m3")
    run = kit.collapsed_run(1, ["m2", "m3"], "t1")
    envelope = build(
        ledger,
        lambda nonce: [
            kit.source("t1", [kit.row("m1", "t1", 0, nonce=nonce)], collapsed_runs=[run])
        ],
    )

    assert envelope.withheld == ()
    assert {"m2", "m3"} <= envelope.disclosed_ids


def test_participant_probes_and_history_additions_enter_the_hit_set() -> None:
    """EV-01 names the L5 participant probes and history additions explicitly (ADV-109).

    Since H1b the shortlist is a *selection* out of those two clauses rather than a third
    intake, so `s1` here is one of the ids the L5 probe already returned. `hit_ids` is
    therefore unchanged by shortlisting, which is the property this file's H1b section
    tests directly.
    """
    ledger = DispositionLedger()
    ledger.record_list_page(kit.fetched(["p1", "s1"]), rung=RungId.L5, query="from:amy@x.example")
    ledger.record_history_additions(kit.history_additions(["h1"]))
    ledger.record_shortlist(ids=["s1"], rule="top-k by stage-A cosine", k=25)

    assert ledger.hit_ids == {"p1", "h1", "s1"}
    assert {origin.clause for origin in ledger.origins.values()} == {"H-lex", "H-hist"}
    assert ledger.shortlist_ids == {"s1"}

    with pytest.raises(DispositionInvariantError):
        # None of the three is disclosed and none is explained: three residues, one failure.
        ledger.certify(disclosed=[])


def test_a_shortlist_larger_than_its_declared_k_is_refused() -> None:
    """EV-01(i): |H| may not be shrunk *or* stretched away from the declared rule.

    Every id here is in `H` first, so the refusal under test is the `k` bound and not
    H1b's provenance check standing in for it.
    """
    ledger = DispositionLedger()
    candidates = [f"s{i}" for i in range(5)]
    ledger.record_list_page(kit.fetched(candidates), rung=RungId.L5, query="pool probe")
    with pytest.raises(DispositionInvariantError, match="exceeds the declared k=3"):
        ledger.record_shortlist(ids=candidates, rule="top-k", k=3)


def test_a_certificate_cannot_be_minted_outside_the_ledger() -> None:
    """The envelope demands proof; the proof cannot be forged by constructing it directly."""
    with pytest.raises(DispositionInvariantError):
        DispositionCertificate(
            object(),
            hit_count=0,
            disclosed_hits=0,
            withheld=(),
            withheld_groups=(),
            withheld_tail=(),
            grouped_ids=(),
            digest="0" * 64,
            observed_threads={},
            hits_per_rung={},
            observed_scalars={},
            observed_thread_facts={},
        )


def test_disclosed_ids_are_read_from_the_payload_not_from_the_caller() -> None:
    """A caller cannot declare a message disclosed without putting it in the response."""
    ledger = ledger_with_hits("m1", "m2")
    ledger.certify(["m1", "m2"])  # the ledger alone would be satisfied

    with pytest.raises(DispositionInvariantError):
        # ... but the builder recomputes `disclosed` from the sources it is shipping.
        build(ledger, lambda nonce: [kit.source("t1", [kit.row("m1", "t1", 0, nonce=nonce)])])


def test_a_certificate_cannot_be_lifted_from_another_response() -> None:
    """The proof binds to one disclosed set, not merely to a withheld list.

    Without this, a caller could certify a small, honest response and attach that
    certificate to a larger payload assembled from a different ledger.
    """
    from mailweave.constants import NORMAL_CEILING_TOKENS
    from mailweave.envelope.response import Envelope
    from mailweave.envelope.wire import Ceiling, Counters, RetrievalReport

    honest_ledger = ledger_with_hits("m1")
    honest = build(
        honest_ledger, lambda nonce: [kit.source("t1", [kit.row("m1", "t1", 0, nonce=nonce)])]
    )

    other_ledger = ledger_with_hits("m9")
    stolen = other_ledger.certify(["m9"])

    with pytest.raises(DispositionInvariantError) as failure:
        Envelope(
            fence_nonce=honest.fence_nonce,
            asked_for=kit.asked_for(),
            sources=honest.sources,
            partial=False,
            retrieval_report=RetrievalReport(
                outcome=Outcome.ANSWERED,
                rungs=(RungId.L1,),
                hit_count_per_rung=(1,),
                sufficiency=Sufficiency.SUFFICIENT,
                counters=Counters(http_requests=1, api_calls=1, quota_units=5),
            ),
            ceiling=Ceiling(normal=NORMAL_CEILING_TOKENS, applied=NORMAL_CEILING_TOKENS),
            disposition=stolen,
        )
    assert "different disclosed set" in str(failure.value)


# --- H1b: the shortlist is a selection out of H, never an intake into it ---------------------
#
# R-RETR (round 2) proved `record_shortlist` was not a loose end but a working bypass of
# both H1 and H2: 50 ids nothing ever fetched went straight into `H`, and 37 of them were
# then dressed up as R-DISC-001's dishonest 5-of-42 map. These tests reproduce that probe
# verbatim and then generalise it, because one blocked example is not impossibility.


def test_the_fifty_fabricated_id_shortlist_probe_is_refused_at_intake() -> None:
    """R-RETR's probe, unchanged: 50 ids, zero transport calls, `k` deliberately generous.

    The refusal has to happen here rather than at `certify`. At certification a fabricated
    id is indistinguishable from a real one a cap dropped, so the only remaining question
    is whether a withheld note was filed - and the attacker files the note (that is exactly
    how the 5-of-42 map was rebuilt). At intake the question is answered from the ledger's
    own enumeration.
    """
    ledger = DispositionLedger()
    fabricated = [f"fabricated-{i}" for i in range(50)]

    with pytest.raises(DispositionInvariantError) as failure:
        ledger.record_shortlist(ids=fabricated, rule="my-own-ranking", k=50)

    assert "never entered H through an executed retrieval" in str(failure.value)
    assert ledger.hit_ids == frozenset()
    assert ledger.shortlist is None
    assert ledger.shortlist_ids == frozenset()


def test_a_shortlist_naming_one_unfetched_id_among_real_ones_names_exactly_that_id() -> None:
    """The refusal is specific, so a real caller can fix it; it is not a blanket "no"."""
    ledger = DispositionLedger()
    ledger.record_list_page(
        kit.fetched(["pool-1", "pool-2", "pool-3"]), rung=RungId.L5, query="from:amy@x.example"
    )

    with pytest.raises(DispositionInvariantError) as failure:
        ledger.record_shortlist(ids=["pool-1", "pool-2", "smuggled"], rule="top-k", k=25)

    assert "['smuggled']" in str(failure.value)
    assert ledger.hit_ids == {"pool-1", "pool-2", "pool-3"}


def test_a_shortlist_over_ids_a_sealed_page_returned_is_accepted() -> None:
    """The seal has to be passable by the rung that will really run, or it gets removed.

    A gate nobody can satisfy is a gate someone deletes, so the legitimate shape - pool
    probes recorded through the transport, then the top-k selected out of them - is
    asserted alongside the refusals.
    """
    ledger = DispositionLedger()
    pool = [f"pool-{i}" for i in range(30)]
    ledger.record_list_page(kit.fetched(pool), rung=RungId.L5, query="from:amy@x.example")

    shortlist = ledger.record_shortlist(ids=pool[:25], rule="top-k by stage-A cosine", k=25)

    assert shortlist.size == 25
    assert ledger.shortlist_ids == set(pool[:25])
    assert ledger.hit_ids == set(pool), "shortlisting neither added to nor removed from H"


def test_a_shortlist_may_select_a_history_addition() -> None:
    """Both sealed clauses count as provenance, not just H-lex."""
    ledger = DispositionLedger()
    ledger.record_history_additions(kit.history_additions(["h1"]))
    assert ledger.record_shortlist(ids=["h1"], rule="top-k", k=25).size == 1


def test_a_shortlist_that_lists_the_same_id_twice_is_refused() -> None:
    """R-RETR-001's arithmetic in a second place: one candidate counted twice."""
    ledger = DispositionLedger()
    ledger.record_list_page(kit.fetched(["a", "b"]), rung=RungId.L5, query="q")
    with pytest.raises(DispositionInvariantError) as failure:
        ledger.record_shortlist(ids=["a", "b", "a"], rule="top-k", k=25)
    assert "same id more than once: ['a']" in str(failure.value)


@settings(max_examples=200, deadline=None)
@given(
    fetched=st.lists(st.from_regex(r"[a-z]{1,6}", fullmatch=True), unique=True, max_size=10),
    claimed=st.lists(st.from_regex(r"[a-z]{1,6}", fullmatch=True), unique=True, max_size=10),
)
def test_no_shortlist_of_any_shape_can_grow_the_hit_set(
    fetched: list[str], claimed: list[str]
) -> None:
    """Impossibility, not one blocked example.

    For *any* sealed page and *any* list a caller hands `record_shortlist`, there are only
    two outcomes: the call raises, or `H` is exactly what the sealed pages returned. There
    is no input for which the shortlist adds a message id. `k` is set to the length of the
    claim so the size bound can never be what fires - the provenance seal has to carry it.
    """
    ledger = DispositionLedger()
    ledger.record_list_page(kit.fetched(fetched), rung=RungId.L5, query="pool probe")
    before = ledger.hit_ids
    assert before == set(fetched)

    try:
        ledger.record_shortlist(ids=claimed, rule="top-k", k=max(len(claimed), 1))
    except DispositionInvariantError:
        assert ledger.hit_ids == before
        assert not set(claimed) <= before, "a refusal must name a real provenance gap"
        return

    assert ledger.hit_ids == before
    assert set(claimed) <= before
    assert ledger.shortlist is not None
    assert ledger.shortlist.size == len(set(claimed))


def test_the_hit_set_has_exactly_one_writer_and_it_demands_a_sealed_page() -> None:
    """The structural claim behind H1b, checked against the source rather than asserted.

    Every test above is one input. This one is the reason there is no other input: read
    `disposition.py` with `ast` and confirm that `self._origins` - the dict that *is* `H` -
    is mutated in exactly one method, and that the method takes a `FetchedIds`. A future
    intake that forgets the seal fails here, in the same way the guards fail a new writer
    that forgets the allowlist.
    """
    import ast
    import inspect

    from mailweave.envelope import disposition as module

    tree = ast.parse(inspect.getsource(module))
    mutators = {"setdefault", "update", "pop", "popitem", "clear", "__setitem__"}
    writers: set[str] = set()

    def mutating_uses(node: ast.AST) -> bool:
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr in mutators
                and isinstance(inner.func.value, ast.Attribute)
                and inner.func.value.attr == "_origins"
            ):
                return True
            targets: list[ast.expr] = []
            if isinstance(inner, ast.Assign):
                targets = list(inner.targets)
            elif isinstance(inner, ast.AugAssign | ast.AnnAssign):
                targets = [inner.target]
            elif isinstance(inner, ast.Delete):
                targets = list(inner.targets)
            for target in targets:
                base = target.value if isinstance(target, ast.Subscript) else target
                if isinstance(base, ast.Attribute) and base.attr == "_origins":
                    return True
        return False

    ledger_class = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "DispositionLedger"
    )
    for member in ledger_class.body:
        if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef) and mutating_uses(member):
            writers.add(member.name)

    assert writers == {"_admit"}, f"H may now be written from {sorted(writers)}"

    admit = next(
        node
        for node in ledger_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "_admit"
    )
    annotations = [
        ast.unparse(arg.annotation) for arg in admit.args.args if arg.annotation is not None
    ]
    assert "FetchedIds" in annotations, "the one writer of H does not require a sealed page"


def test_a_hand_built_page_is_accepted_and_that_is_the_documented_residual() -> None:
    """H1b's sibling hole, pinned so it cannot be rediscovered as a surprise.

    Sealing `record_shortlist` stops a caller *naming* ids into `H`. It does not stop a
    caller *minting* them: `FetchedIds` is an ordinary public constructor, so R-RETR's
    thirty-seven fabricated ids reach `H` through `record_list_page` instead, in two lines
    rather than one. This test asserts the gap and asserts that the module says so, on the
    same discipline the guards hold - a seal may be narrow, but it may not imply a reach
    it does not have.

    It is deliberately not "fixed": within one process a page's provenance is the claim "I
    executed this call", and every constructor the real Gmail wrapper can reach a fake one
    can reach too. Closing it needs the out-of-process counting proxy WS-13 already owns.
    """
    from mailweave.envelope.disposition import FetchedIds, ObservedEndpoint

    ledger = DispositionLedger()
    ledger.record_list_page(
        FetchedIds(
            ids=[f"fabricated-{i}" for i in range(37)],
            endpoint=ObservedEndpoint.MESSAGES_LIST,
            page_size=50,
        ),
        rung=RungId.L1,
        query="a call that never happened",
    )
    assert len(ledger.hit_ids) == 37, "if this now raises, the residual is closed - say so"

    # And once they are in H, the H1b seal accepts them: it checks provenance against H,
    # which is the strongest check available at this layer and no stronger.
    assert ledger.record_shortlist(ids=sorted(ledger.hit_ids)[:25], rule="mine", k=25).size == 25

    doc = FetchedIds.__doc__ or ""
    assert "does not bound" in doc and "over*-recording" in doc, (
        "the page seal no longer states the direction it does not bound"
    )


# --- amendment A2: an id enters H through any observed Gmail response ----------------------


def test_a_shortlist_may_select_a_threads_get_candidate() -> None:
    """R-RETR-004, which is why A2 exists: the seal used to reject WS-08's own input.

    AD D.5 builds the semantic pool thread-wise and its first-priority source is threads
    already touched by earlier rungs, which arrive through `threads.get` - never
    `messages.list`, never `history.list`. Under the round-3 seal a legitimate top-k drawn
    from that pool named ids that had entered no sealed clause, so `record_shortlist`
    refused it. The rung would then have been built against a contract that rejects its
    own inputs, and the pressure would have been to reopen the seal.
    """
    ledger = DispositionLedger()
    rows = [f"thr-{index}" for index in range(6)]
    recorded = ledger.record_thread(kit.observed_thread(rows, "t-42"), rung=RungId.L5)

    assert recorded == len(rows)
    assert ledger.hit_ids == set(rows)
    assert {origin.clause for origin in ledger.origins.values()} == {"H-thr"}
    assert {origin.thread_id for origin in ledger.origins.values()} == {"t-42"}

    shortlist = ledger.record_shortlist(ids=rows[:3], rule="top-k by stage-A cosine", k=25)
    assert shortlist.size == 3
    assert ledger.shortlist_ids == set(rows[:3])
    assert ledger.hit_ids == set(rows), "shortlisting neither added to nor removed from H"


def test_a_threads_get_observation_appends_no_scan_scope_entry() -> None:
    """`scan_scope` is per executed *query*, and a `threads.get` has none.

    Inventing a `q` and a `page_size` to make the new clause fit the listing shape would
    put a query in the response that no call ever made - a smaller version of exactly what
    this module refuses everywhere else.
    """
    ledger = DispositionLedger()
    ledger.record_thread(kit.observed_thread(["a", "b"], "t1"), rung=RungId.L5)
    assert ledger.scan_scope == ()
    assert ledger.hit_ids == {"a", "b"}


INTAKES: dict[ObservedEndpoint, Callable[[DispositionLedger, FetchedIds], object]] = {
    ObservedEndpoint.MESSAGES_LIST: lambda ledger, observation: ledger.record_list_page(
        observation, rung=RungId.L1, query="from:amy"
    ),
    ObservedEndpoint.HISTORY_LIST: lambda ledger, observation: ledger.record_history_additions(
        observation
    ),
    ObservedEndpoint.THREADS_GET: lambda ledger, observation: ledger.record_thread(
        observation, rung=RungId.L5
    ),
}


def observation_from(endpoint: ObservedEndpoint) -> FetchedIds:
    if endpoint is ObservedEndpoint.MESSAGES_LIST:
        return kit.fetched(["m1"])
    if endpoint is ObservedEndpoint.HISTORY_LIST:
        return kit.history_additions(["m1"])
    return kit.observed_thread(["m1"], "t1")


@pytest.mark.parametrize("observed", list(ObservedEndpoint))
@pytest.mark.parametrize("intake", list(ObservedEndpoint))
def test_each_intake_admits_its_own_endpoint_and_no_other(
    intake: ObservedEndpoint, observed: ObservedEndpoint
) -> None:
    """The whole 3x3 matrix, not the three diagonal cases.

    A2 generalises the seal by adding a clause, and the way that generalisation could go
    wrong is by letting the *caller* choose the clause: record a `threads.get` response
    through `record_list_page` and the ledger mints a `scan_scope` entry for a
    `messages.list` query that never ran. So the endpoint travels on the observation, the
    clause is derived from it, and an intake refuses anything but its own endpoint.
    """
    ledger = DispositionLedger()
    call = INTAKES[intake]

    if intake is observed:
        call(ledger, observation_from(observed))
        assert ledger.hit_ids == {"m1"}
        origin = ledger.origins["m1"]
        assert origin.endpoint is observed
        assert origin.clause == CLAUSE_BY_ENDPOINT[observed]
        return

    with pytest.raises(DispositionInvariantError) as failure:
        call(ledger, observation_from(observed))
    assert observed.value in str(failure.value)
    assert ledger.hit_ids == frozenset(), "a refused observation must not have entered H"
    assert ledger.scan_scope == ()


def test_every_endpoint_that_can_enter_the_hit_set_names_its_clause_and_has_an_intake() -> None:
    """Adding a member to `ObservedEndpoint` is an amendment, not a refactor.

    A future endpoint added without a clause would fall through `CLAUSE_BY_ENDPOINT` with a
    `KeyError` at runtime; one added without an intake would be unreachable and quietly
    useless. Both are caught here, at the point where A.7a's clause list and the code that
    implements it are supposed to agree.
    """
    assert set(CLAUSE_BY_ENDPOINT) == set(ObservedEndpoint)
    assert set(INTAKES) == set(ObservedEndpoint)
    assert len(set(CLAUSE_BY_ENDPOINT.values())) == len(ObservedEndpoint), (
        "clauses must be distinct"
    )


@settings(max_examples=200, deadline=None)
@given(
    lex=st.lists(st.from_regex(r"[a-z]{1,5}", fullmatch=True), unique=True, max_size=6),
    hist=st.lists(st.from_regex(r"[a-z]{1,5}", fullmatch=True), unique=True, max_size=6),
    thr=st.lists(st.from_regex(r"[a-z]{1,5}", fullmatch=True), unique=True, max_size=6),
    claimed=st.lists(st.from_regex(r"[a-z]{1,5}", fullmatch=True), unique=True, max_size=8),
)
def test_no_shortlist_of_any_shape_can_grow_a_hit_set_built_from_all_three_clauses(
    lex: list[str], hist: list[str], thr: list[str], claimed: list[str]
) -> None:
    """H1b's impossibility property, restated over the clause A2 added.

    A2 widens *what may be observed*, and the risk in widening is that the seal starts
    accepting what was never observed at all. So the round-3 property is re-run with `H`
    accumulated across all three endpoints at once: for any observations and any list a
    caller hands `record_shortlist`, either the call raises or the claim was already a
    subset of what the sealed observations returned. There is still no input that adds an
    id, and `k` is set to the length of the claim so the size bound can never be what fires.
    """
    ledger = DispositionLedger()
    ledger.record_list_page(kit.fetched(lex), rung=RungId.L5, query="pool probe")
    ledger.record_history_additions(kit.history_additions(hist))
    ledger.record_thread(kit.observed_thread(thr, "t1"), rung=RungId.L5)

    observed = set(lex) | set(hist) | set(thr)
    assert ledger.hit_ids == observed

    try:
        ledger.record_shortlist(ids=claimed, rule="top-k", k=max(len(claimed), 1))
    except DispositionInvariantError:
        assert ledger.hit_ids == observed
        assert not set(claimed) <= observed, "a refusal must name a real provenance gap"
        return

    assert ledger.hit_ids == observed
    assert set(claimed) <= observed


# --- R-RETR-003: an observation is one executed call, and may be recorded once ------------


def test_the_same_page_cannot_be_recorded_twice() -> None:
    """R-RETR-003: `_release` set `_consumed` and never read it.

    The second `record_list_page` minted a `ScanScopeEntry` claiming a second query
    returned those ids, from one real call. `H` is unaffected - `setdefault` is idempotent
    - but `scan_scope` is the response's account of *what was executed*, and two entries
    for one call is a false account of the retrieval, not of the hit set.
    """
    ledger = DispositionLedger()
    page = kit.fetched(["a1", "a2"])
    ledger.record_list_page(page, rung=RungId.L1, query="from:amy")
    with pytest.raises(DispositionInvariantError) as failure:
        ledger.record_list_page(page, rung=RungId.L2, query="from:amy OR from:sam")
    assert "already recorded" in str(failure.value)
    assert len(ledger.scan_scope) == 1
    assert ledger.scan_scope[0].q == "from:amy"
    assert ledger.hit_ids == {"a1", "a2"}


def test_the_replay_is_refused_across_every_intake_not_just_the_one_it_used() -> None:
    """A page consumed by one intake is consumed, whichever intake sees it next."""
    ledger = DispositionLedger()
    thread = kit.observed_thread(["b1", "b2"], thread_id="t9")
    ledger.record_thread(thread, rung=RungId.L1)
    with pytest.raises(DispositionInvariantError):
        ledger.record_thread(thread, rung=RungId.L5)

    history = kit.history_additions(["c1"])
    ledger.record_history_additions(history)
    with pytest.raises(DispositionInvariantError):
        ledger.record_history_additions(history)


def test_recorded_is_the_flag_the_refusal_reads() -> None:
    """`recorded` was already public and already meant this; nothing consulted it."""
    page = kit.fetched(["d1"])
    assert page.recorded is False
    DispositionLedger().record_list_page(page, rung=RungId.L1, query="q")
    assert page.recorded is True


def test_two_distinct_pages_with_the_same_ids_are_still_two_calls() -> None:
    """The refusal is about the object, not the ids: a real repeat query really happened."""
    ledger = DispositionLedger()
    ledger.record_list_page(kit.fetched(["e1"]), rung=RungId.L1, query="from:amy")
    ledger.record_list_page(kit.fetched(["e1"]), rung=RungId.L2, query="from:amy after:2026/08")
    assert len(ledger.scan_scope) == 2
    assert ledger.hit_ids == {"e1"}


# --- R-DISC-009: the thread a withheld record names is observed, not asserted --------------
#
# R-DISC's reproduction: four ids observed for thread t1 and one real id ("t2-only") for an
# unrelated t2. A map of t1 with `stated_total=5` listed the t2 id in `withheld_here`,
# reached `accounted_for == stated_total`, and shipped as a complete map of a thread it was
# one message short of. Every check involved compared the record against the caller's own
# `thread_id`, so all of them agreed. These tests are about where the thread comes from.


def two_threads_one_of_them_short() -> DispositionLedger:
    """t1 observed with four rows, t2 with one. Nothing here is fabricated: both are real."""
    ledger = DispositionLedger()
    ledger.record_thread(kit.observed_thread(["a1", "a2", "a3", "a4"], "t1"), rung=RungId.L1)
    ledger.record_thread(kit.observed_thread(["t2-only"], "t2"), rung=RungId.L1)
    return ledger


def borrowing_map(builder: EnvelopeBuilder, nonce: str) -> Source:
    """A `map_id`-bearing source for t1 whose fifth position is another thread's message."""
    return Source(
        thread_id="t1",
        stated_total=5,
        included=4,
        included_as_stub=0,
        fetched_at=kit.FETCHED_AT,
        map_id="mw1.t1-complete",
        messages=tuple(
            kit.row(mid, "t1", position, nonce=nonce)
            for position, mid in enumerate(["a1", "a2", "a3", "a4"])
        ),
        withheld_here=("t2-only",),
    )


def test_a_map_cannot_account_for_itself_with_another_threads_withheld_message() -> None:
    """R-DISC-009's reproduction, executed rather than described.

    The id is real, in `H`, genuinely undisclosed and genuinely backed by a cap note - the
    four things every earlier check asks about. What makes the map false is that the id was
    observed in t2, and that fact now travels with the record.
    """
    ledger = two_threads_one_of_them_short()
    ledger.note_withheld(
        message_id="t2-only",
        cap=WithheldCap.MAX_HIT_THREADS,
        why="13 hit-bearing threads found; max_hit_threads=12",
        affordance=cap_affordance("t1"),
    )
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    builder.add_source(borrowing_map(builder, builder.fence_nonce))
    builder.add_affordance(kit.thread_affordance("t1"))

    with pytest.raises(DispositionInvariantError) as failure:
        builder.build(
            outcome=Outcome.ANSWERED,
            rungs=(RungId.L1,),
            sufficiency=Sufficiency.SUFFICIENT,
            counters=kit.counters(),
        )
    assert "t2-only" in str(failure.value)


def test_the_thread_on_a_withheld_record_is_the_one_the_observation_recorded() -> None:
    """The positive half: the record names t2 because the `threads.get` said t2.

    Asserted against the ledger's own `origins` rather than against a literal, so the test
    states the relation ("the record's thread is the observed thread") and not the value.
    """
    ledger = two_threads_one_of_them_short()
    ledger.note_withheld(
        message_id="t2-only",
        cap=WithheldCap.MAX_HIT_THREADS,
        why="ranked 13th by recency",
        affordance=cap_affordance("t2"),
    )
    certificate = ledger.certify(["a1", "a2", "a3", "a4"])

    (record,) = certificate.withheld
    assert record.id == "t2-only"
    assert record.thread_id == ledger.origins["t2-only"].thread_id
    assert record.thread_id != "t1"


def test_the_same_derivation_holds_for_an_id_observed_through_a_listing_page() -> None:
    """`messages.list` carries `threadId` per item, so H-lex derives its threads too.

    Without this the fix would close the shape R-DISC executed and leave the identical hole
    open for the endpoint most ids actually arrive through.
    """
    ledger = DispositionLedger()
    ledger.record_list_page(
        kit.fetched(["m1", "m2"], thread_ids={"m1": "t1", "m2": "t7"}),
        rung=RungId.L1,
        query="from:amy launch",
    )
    ledger.note_withheld(
        message_id="m2",
        cap=WithheldCap.MAX_HIT_THREADS,
        why="beyond the map cap",
        affordance=cap_affordance("t7"),
    )
    (record,) = ledger.certify(["m1"]).withheld
    assert record.thread_id == "t7"


def test_an_id_observed_without_a_thread_cannot_be_withheld_at_all() -> None:
    """The honest refusal: no observed thread, no record - never a guessed one.

    A source that wanted to count this id would supply the only other candidate thread in
    the room, which is exactly the borrowing above. So certification stops instead, and the
    error says which observation needs to carry the `threadId` Gmail returned.
    """
    ledger = ledger_with_hits("m1", "m2")  # no thread recorded for either
    ledger.note_withheld(
        message_id="m2",
        cap=WithheldCap.DISCLOSED_TOKEN_CEILING,
        why="ceiling reached",
        affordance=cap_affordance("t1"),
    )
    with pytest.raises(DispositionInvariantError) as failure:
        ledger.certify(["m1"])
    message = str(failure.value)
    assert "no thread was observed" in message
    assert "m2" in message
    # It is a refusal to *withhold* it, not a refusal to use it: the same observation
    # certifies cleanly when both of its ids are disclosed.
    assert ledger_with_hits("m1", "m2").certify(["m1", "m2"]).withheld == ()


def test_a_withheld_record_rewritten_after_certification_is_refused() -> None:
    """The last editable point: the envelope may not restate the record with another thread.

    The certificate is the finding. An envelope shipping the certified ids under threads of
    its own is the same borrowing performed one layer up - and round 5's check compared the
    id sets only, so it would have accepted this. The records are now compared whole.
    """
    from mailweave.envelope.wire import Ceiling, RetrievalReport

    ledger = two_threads_one_of_them_short()
    ledger.note_withheld(
        message_id="t2-only",
        cap=WithheldCap.MAX_HIT_THREADS,
        why="ranked 13th by recency",
        affordance=cap_affordance("t2"),
    )
    honest = build(
        ledger,
        lambda nonce: [
            kit.source(
                "t1",
                [
                    kit.row(mid, "t1", position, nonce=nonce)
                    for position, mid in enumerate(["a1", "a2", "a3", "a4"])
                ],
                stated_total=5,
            )
        ],
        affordances=(kit.thread_affordance("t1"),),
    )
    (certified,) = honest.withheld
    forged = certified.model_copy(update={"thread_id": "t1"})
    assert forged.id == certified.id  # same id, same cap, same reason: only the thread moved

    with pytest.raises(DispositionInvariantError) as failure:
        Envelope(
            fence_nonce=honest.fence_nonce,
            asked_for=honest.asked_for,
            partial=honest.partial,
            withheld=(forged,),
            retrieval_report=RetrievalReport.model_validate(honest.retrieval_report.model_dump()),
            sources=honest.sources,
            affordances=honest.affordances,
            ceiling=Ceiling.model_validate(honest.ceiling.model_dump()),
            disposition=honest.disposition,
        )
    assert "rewritten after certification" in str(failure.value)


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        pytest.param(
            {"thread_ids": {"m1": "t1", "ghost": "t9"}},
            "did not return",
            id="a thread for an id the response never carried",
        ),
        pytest.param(
            {"thread_ids": {"m1": "t1"}},
            "some of its ids",
            id="a thread for some ids and not others",
        ),
    ],
)
def test_an_observation_cannot_record_a_thread_the_response_did_not_carry(
    kwargs: dict[str, Any], fragment: str
) -> None:
    """The per-id thread map is an account of one response, so it matches that response.

    Both refusals exist because the map is the *source* of the withheld record's thread
    now: a map that names ids the call never returned, or covers only some of the ids it
    did return, is the caller writing threads by hand again with an extra step.
    """
    with pytest.raises(DispositionInvariantError) as failure:
        FetchedIds(
            ids=["m1", "m2"],
            endpoint=ObservedEndpoint.MESSAGES_LIST,
            page_size=100,
            **kwargs,
        )
    assert fragment in str(failure.value)


def test_a_threads_get_observation_may_not_also_carry_a_per_id_thread_map() -> None:
    """One thread per `threads.get`, stated once. Two statements of it could disagree."""
    with pytest.raises(DispositionInvariantError) as failure:
        FetchedIds(
            ids=["m1"],
            endpoint=ObservedEndpoint.THREADS_GET,
            thread_id="t1",
            thread_ids={"m1": "t2"},
        )
    assert "divergent statement" in str(failure.value)


def test_a_later_observation_may_supply_the_thread_an_earlier_one_did_not_carry() -> None:
    """The ordinary ladder: a `messages.list` hit, then the `threads.get` that maps it.

    An id's origin is where it entered `H` and a second sighting does not move it - but the
    thread is a fact the first response may simply not have carried, and refusing to learn
    it would leave the id un-withholdable for the rest of the response even though a real
    Gmail call named its thread.
    """
    ledger = DispositionLedger()
    ledger.record_list_page(kit.fetched(["m1", "m2"]), rung=RungId.L1, query="from:amy")
    assert ledger.origins["m2"].thread_id is None

    ledger.record_thread(kit.observed_thread(["m2", "m3"], "t4"), rung=RungId.L1)

    assert ledger.origins["m2"].clause == "H-lex", "the origin is still where it entered H"
    assert ledger.origins["m2"].thread_id == "t4"
    ledger.note_withheld(
        message_id="m2",
        cap=WithheldCap.MAX_HIT_THREADS,
        why="beyond the map cap",
        affordance=cap_affordance("t4"),
    )
    (record,) = ledger.certify(["m1", "m3"]).withheld
    assert (record.id, record.thread_id) == ("m2", "t4")


def test_two_observations_that_disagree_about_an_ids_thread_are_refused() -> None:
    """A message is in one thread. Two responses that say otherwise cannot both be real.

    Picking one - first or last - would be the ledger inventing the answer to the question
    the disagreement raises, which is the shape R-DISC-009 is about in the first place.
    """
    ledger = DispositionLedger()
    ledger.record_thread(kit.observed_thread(["m1"], "t1"), rung=RungId.L1)
    with pytest.raises(DispositionInvariantError) as failure:
        ledger.record_thread(kit.observed_thread(["m1"], "t2"), rung=RungId.L1)
    message = str(failure.value)
    assert "disagree about which thread" in message
    assert "t1" in message and "t2" in message


# --- R-DISC-011: the same borrowing on the DISCLOSED side ---------------------------------
#
# R-DISC-009 closed the withheld half: a record's thread is read off the observation. The
# disclosed half was still asserted. R-DISC's executed proof built a "complete" four-message
# map of t1 whose fourth row was a real message a real `threads.get` had observed in t5,
# with `partial=False` and `accounted_for == stated_total`. Nothing compared the row against
# `HitOrigin`, because nothing outside `disposition.py` could read it.
#
# The certificate now carries `observed_threads`, so the comparison happens against the same
# enumeration the set difference was computed from. `MessageRow` has also lost its
# `thread_id` parameter entirely: a row inside a source cannot be given a thread at all, so
# the intra-payload half of the restatement is gone rather than merely checked.


def two_real_threads_one_borrowable() -> DispositionLedger:
    """t1 observed with three rows; x1 observed, genuinely, in t5. Nothing fabricated."""
    ledger = DispositionLedger()
    ledger.record_thread(kit.observed_thread(["a1", "a2", "a3"], "t1"), rung=RungId.L1)
    ledger.record_thread(kit.observed_thread(["x1"], "t5"), rung=RungId.L1)
    return ledger


def test_a_map_cannot_reach_completeness_with_a_message_observed_in_another_thread() -> None:
    """R-DISC-011's reproduction, executed.

    Every earlier check passes: x1 is real, in `H`, disclosed exactly once, at a free
    position inside the thread's range, and the arithmetic closes. What makes the map false
    is that a `threads.get` observed x1 in t5, and until now nothing on the disclosed side
    read that.
    """
    ledger = two_real_threads_one_borrowable()
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    nonce = builder.fence_nonce
    builder.add_source(
        Source(
            thread_id="t1",
            stated_total=4,
            included=4,
            included_as_stub=0,
            fetched_at=kit.FETCHED_AT,
            map_id="mw1.t1-complete",
            messages=tuple(
                kit.row(mid, "t1", position, nonce=nonce)
                for position, mid in enumerate(["a1", "a2", "a3", "x1"])
            ),
        )
    )
    builder.add_affordance(kit.thread_affordance("t1"))
    with pytest.raises(DispositionInvariantError) as failure:
        build_answered(builder)
    message = str(failure.value)
    assert "x1" in message and "t5" in message and "t1" in message


def test_the_borrowing_is_refused_even_when_the_source_claims_no_map() -> None:
    """A search view borrows nothing either: the row is still false about its thread.

    Restricting the check to `map_id`-bearing sources would leave the ordinary caller bug -
    the wrong source inside a loop over threads - producing a response that shows a message
    under a conversation it is not part of, which is a claim a reading agent acts on.
    """
    ledger = DispositionLedger()
    ledger.record_thread(kit.observed_thread(["x1"], "t5"), rung=RungId.L1)
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    nonce = builder.fence_nonce
    builder.add_source(kit.source("t1", [kit.row("x1", "t1", 0, nonce=nonce)], stated_total=3))
    builder.add_affordance(kit.thread_affordance("t1"))
    with pytest.raises(DispositionInvariantError) as failure:
        build_answered(builder)
    assert "x1 was observed in thread t5" in str(failure.value)


def test_the_borrowing_is_refused_when_it_arrives_inside_a_collapsed_run() -> None:
    """A collapsed-run member is disclosed (A.7a `R`), so it is checked like a row.

    Checking only `messages` would leave the identical borrowing available through the one
    disposition that never renders an id in a row - which is where a reviewer is least
    likely to look for it.
    """
    ledger = two_real_threads_one_borrowable()
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    nonce = builder.fence_nonce
    builder.add_source(
        kit.source(
            "t1",
            [kit.row("a1", "t1", 0, nonce=nonce)],
            stated_total=4,
            collapsed_runs=(kit.collapsed_run(1, ["a2", "a3", "x1"], "t1"),),
        )
    )
    builder.add_affordance(kit.thread_affordance("t1"))
    with pytest.raises(DispositionInvariantError) as failure:
        build_answered(builder)
    assert "x1 was observed in thread t5" in str(failure.value)


def test_a_map_may_not_count_a_message_no_observation_placed_in_any_thread() -> None:
    """The withheld rule, applied to the disclosed side (`_record_for`'s twin).

    An id whose observation recorded no `threadId` cannot be withheld, because no honest
    sentence names the thread that is short of a message. A map is the same sentence in the
    positive: "these are all of t1's messages". Counting an id toward that total with
    nothing observed placing it in t1 is the borrowing with the evidence missing rather
    than contrary.
    """
    ledger = DispositionLedger()
    ledger.record_list_page(kit.fetched(["u1"]), rung=RungId.L1, query="from:amy")
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    nonce = builder.fence_nonce
    builder.add_source(
        Source(
            thread_id="t1",
            stated_total=1,
            included=1,
            included_as_stub=0,
            fetched_at=kit.FETCHED_AT,
            map_id="mw1.t1-complete",
            messages=(kit.row("u1", "t1", 0, nonce=nonce),),
        )
    )
    with pytest.raises(DispositionInvariantError) as failure:
        build_answered(builder)
    assert "no observation placed in its thread" in str(failure.value)
    assert "u1" in str(failure.value)


def test_an_unthreaded_id_is_still_disclosable_in_a_source_that_claims_no_map() -> None:
    """The negative control: silence is not contradiction.

    An observation that recorded no thread says nothing about where the id belongs, so a
    search view showing it is not making a claim the ledger can refute. Refusing here too
    would make the check unable to distinguish "we know this is wrong" from "we do not
    know", which is the distinction the module exists to keep.
    """
    ledger = DispositionLedger()
    ledger.record_list_page(kit.fetched(["u1"]), rung=RungId.L1, query="from:amy")
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    nonce = builder.fence_nonce
    builder.add_source(kit.source("t1", [kit.row("u1", "t1", 0, nonce=nonce)]))
    envelope = build_answered(builder)
    assert envelope.disclosed_ids == {"u1"}


def test_a_row_for_an_id_that_never_entered_the_hit_set_is_left_alone() -> None:
    """A1's residue, stated as a test rather than as prose.

    A parent or context message fetched outside any recorded retrieval has no `HitOrigin`,
    so the ledger has no opinion about its thread and this check must not invent one. What
    bounds *that* id is the content witness A1 requires, not anything in this process.
    """
    ledger = DispositionLedger()
    ledger.record_thread(kit.observed_thread(["a1"], "t1"), rung=RungId.L1)
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    nonce = builder.fence_nonce
    builder.add_source(
        kit.source(
            "t1",
            [kit.row("a1", "t1", 0, nonce=nonce), kit.row("never-fetched", "t1", 1, nonce=nonce)],
        )
    )
    envelope = build_answered(builder)
    assert "never-fetched" in envelope.disclosed_ids


def test_a_message_row_has_no_thread_id_to_get_wrong() -> None:
    """The parameter is gone, not cross-checked (R-DISC-011, the `note_withheld` pattern).

    Round 6 removed `thread_id` from `note_withheld` for exactly this reason: a parameter
    that exists can be passed a wrong value, and the check that catches it has to be
    remembered by every future reader. `Source` writes the row's wire `thread_id` from its
    own, so the wire form AD D.2 documents is unchanged and there is nowhere to disagree.
    """
    with pytest.raises(ValidationError) as failure:
        MessageRow(
            mailbox=MailboxProvenance.of(("INBOX",)),
            id="m1",
            thread_id="t9",  # type: ignore[call-arg]
            position=0,
            role=Role.STUB,
            reason=ThreadMember(thread_id="t1", position=0),
            depth=Depth.STUB,
            unabridged=kit.unabridged("m1"),
            linkage=Linkage.HEADERS_UNOBSERVED,
        )
    assert "thread_id" in str(failure.value)
    assert "thread_id" not in MessageRow.model_fields


def test_the_row_on_the_wire_still_carries_the_thread_its_source_names() -> None:
    """Removing the parameter did not remove the field a reader needs (AD D.2)."""
    ledger = DispositionLedger()
    ledger.record_thread(kit.observed_thread(["a1", "a2"], "t1"), rung=RungId.L1)
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    nonce = builder.fence_nonce
    builder.add_source(
        kit.source("t1", [kit.row("a1", "t1", 0, nonce=nonce), kit.row("a2", "t1", 1, nonce=nonce)])
    )
    payload = json.loads(build_answered(builder).model_dump_json())
    rows = payload["sources"][0]["messages"]
    assert [row["thread_id"] for row in rows] == ["t1", "t1"]
    # D.2's order: the thread sits beside the id, not appended after the content.
    assert list(rows[0])[:3] == ["id", "thread_id", "position"]


def test_a_source_may_not_state_a_total_below_what_was_observed_in_its_thread() -> None:
    """`stated_total` is caller-owned, and the ledger can still bound it from below.

    Four ids were observed in t1, so t1 has at least four messages. A source claiming three
    would report itself complete with three rows, and `partial` is derived from that - so
    understating the total is how an incomplete answer becomes a confident one.
    """
    ledger = DispositionLedger()
    ledger.record_thread(kit.observed_thread(["a1", "a2", "a3", "a4"], "t1"), rung=RungId.L1)
    for dropped in ("a3", "a4"):
        ledger.note_withheld(
            message_id=dropped,
            cap=WithheldCap.DISCLOSED_TOKEN_CEILING,
            why="ceiling reached after the degradation ladder",
            affordance=cap_affordance("t1"),
        )
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    nonce = builder.fence_nonce
    builder.add_source(
        Source(
            thread_id="t1",
            stated_total=3,
            included=2,
            included_as_stub=0,
            fetched_at=kit.FETCHED_AT,
            messages=tuple(
                kit.row(mid, "t1", position, nonce=nonce)
                for position, mid in enumerate(["a1", "a2"])
            ),
            withheld_here=("a3", "a4"),
        )
    )
    builder.add_affordance(kit.thread_affordance("t1"))
    with pytest.raises(DispositionInvariantError) as failure:
        build_answered(builder)
    assert "4 distinct messages were observed" in str(failure.value)


def test_a_thread_member_reason_may_not_render_a_position_the_row_is_not_at() -> None:
    """PART-07: a mechanical reason that misstates its own mechanism is decorative."""
    with pytest.raises(ValidationError) as failure:
        MessageRow(
            mailbox=MailboxProvenance.of(("INBOX",)),
            id="m1",
            position=3,
            role=Role.STUB,
            reason=ThreadMember(thread_id="t1", position=41),
            depth=Depth.STUB,
            unabridged=kit.unabridged("m1"),
            linkage=Linkage.HEADERS_UNOBSERVED,
        )
    assert "renders position 41" in str(failure.value)


def test_a_thread_member_reason_may_not_name_a_thread_other_than_its_source() -> None:
    """The thread half of the same check, at the only layer that knows the thread."""
    row = MessageRow(
        mailbox=MailboxProvenance.of(("INBOX",)),
        id="m1",
        position=0,
        role=Role.STUB,
        reason=ThreadMember(thread_id="t9", position=0),
        depth=Depth.STUB,
        unabridged=kit.unabridged("m1"),
        linkage=Linkage.HEADERS_UNOBSERVED,
    )
    with pytest.raises(ValidationError) as failure:
        Source(
            thread_id="t1",
            stated_total=1,
            included=1,
            included_as_stub=1,
            fetched_at=kit.FETCHED_AT,
            messages=(row,),
        )
    assert "naming another thread" in str(failure.value)


# --- R-DISC-011 sweep: hit_count_per_rung is counted, not stated ---------------------------


def two_rungs_with_different_yields() -> DispositionLedger:
    """L1 admits three ids, L5 admits one. Both are real observations."""
    ledger = DispositionLedger()
    ledger.record_list_page(
        kit.fetched(["m1", "m2", "m3"], thread="t1"), rung=RungId.L1, query="from:amy launch"
    )
    ledger.record_list_page(
        kit.fetched(["m9"], thread="t1"), rung=RungId.L5, query="pool participant probe"
    )
    return ledger


def envelope_over_two_rungs() -> Envelope:
    ledger = two_rungs_with_different_yields()
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    nonce = builder.fence_nonce
    builder.add_source(
        kit.source(
            "t1",
            [
                kit.row(mid, "t1", position, nonce=nonce)
                for position, mid in enumerate(["m1", "m2", "m3", "m9"])
            ],
        )
    )
    return builder.build(
        outcome=Outcome.ANSWERED,
        rungs=(RungId.L0, RungId.L1, RungId.L5),
        sufficiency=Sufficiency.SUFFICIENT,
        counters=kit.counters(),
    )


def test_the_per_rung_hit_counts_are_counted_from_the_hit_set() -> None:
    """`hit_count_per_rung` has no parameter left to get wrong.

    Round 6 checked only that the tuple was the same *length* as `rungs`. The values were
    never compared with anything, so the one block a reader consults to see whether the
    numbers add up was the one block nothing derived. Every id in `H` carries the rung
    whose observation admitted it, so the counts are a read of the enumeration - and a rung
    that executed and found nothing still appears, with zero, because `rungs` is separate.
    """
    envelope = envelope_over_two_rungs()
    report = envelope.retrieval_report
    assert report.hit_count_per_rung == (0, 3, 1)
    assert sum(report.hit_count_per_rung) == envelope.disposition.hit_count
    with pytest.raises(TypeError):
        EnvelopeBuilder(DispositionLedger(), asked_for=kit.asked_for()).build(
            outcome=Outcome.ANSWERED,
            rungs=(RungId.L1,),
            hit_count_per_rung=(41,),  # type: ignore[call-arg]
            sufficiency=Sufficiency.SUFFICIENT,
            counters=kit.counters(),
        )


def test_a_report_that_misstates_a_rungs_yield_is_refused() -> None:
    """The mechanical half: assembling the envelope by hand does not buy the number back."""
    honest = envelope_over_two_rungs()
    with pytest.raises(DispositionInvariantError) as failure:
        Envelope(
            fence_nonce=honest.fence_nonce,
            asked_for=honest.asked_for,
            sources=honest.sources,
            partial=honest.partial,
            retrieval_report=honest.retrieval_report.model_copy(
                update={"hit_count_per_rung": (0, 1, 3)}
            ),
            ceiling=honest.ceiling,
            disposition=honest.disposition,
        )
    assert "reported 1, ledger counted 3" in str(failure.value)


def test_a_rung_that_admitted_ids_may_not_be_missing_from_the_report() -> None:
    """A route that produced evidence and is not listed is a route the reader cannot see."""
    honest = envelope_over_two_rungs()
    with pytest.raises(DispositionInvariantError) as failure:
        Envelope(
            fence_nonce=honest.fence_nonce,
            asked_for=honest.asked_for,
            sources=honest.sources,
            partial=honest.partial,
            retrieval_report=honest.retrieval_report.model_copy(
                update={"rungs": (RungId.L0, RungId.L1), "hit_count_per_rung": (0, 3)}
            ),
            ceiling=honest.ceiling,
            disposition=honest.disposition,
        )
    assert "L5" in str(failure.value)
