"""WS-06: `map_id` handles and staleness, driven end to end against a mailbox that moves.

Same standing as `tests/test_lexical_ladder.py` and `tests/test_thread_map_round20.py`: the
real client, the real ledger, real URL construction, real retry ladder and real egress
allowlist, with `httpx.MockTransport` where the socket would be and `tests/conftest.py`
denying `socket.connect` for every test here.

**What is common to every redemption shape, and why that is the load-bearing test.** Five
error classes (`handle_invalid`, `handle_key_rotated`, `handle_expired`, `handle_stale`,
`handle_stale_unverifiable`) plus the clean redemption, across the cache states and the steps
that can reach each of them, are the eleven shapes `redemption_shapes` builds. Eleven separate
tests would be eleven chances to have missed the twelfth - this project's most repeated
defect, found sixteen times. So the load-bearing test here is
`test_every_handle_outcome_only_claims_what_the_step_that_ran_produced`, and what it asserts
is the one property all seven share:

    every field of a redemption's answer is produced by the step that produced it, and a step
    that did not run leaves its field at its "not reached" value.

That single sentence rules out the whole family: content served without a liveness probe, a
`verified_at` on a thread nothing verified, `fetched_at` restamped to now, a warm digest
recompute labelled as a cold one, and a refusal from step 1 that nevertheless spent a Gmail
call. It is asserted over shapes built from a matrix of conditions rather than from a list,
and **the matrix is asserted against the answers it produced rather than against the names it
built them under** - which is R-RETR-058's lesson, learned here the expensive way: the seven-
shape version of this matrix served nothing from the cache and never came back clean, so four
of its eight clauses could not fail and planting BLOCKER ADV-002's own defect left it green.
Widening the matrix then falsified three more clauses that had been asserting things untrue of
the reachable space. A property is evidence only over a population that reaches it.

**PF-15 has two arms and they are two tests**, `test_pf15_...cache_cold` and
`test_pf15_...cache_warm`, because a warm-only pass is not a pass and a cold-only pass is not
either. The warm arm is the one ADV-002 was about: the previous design recomputed
`mapping_digest` from the very cached map that produced it, so `handle_stale` could never
fire on a cache hit.

No fixture here carries real or realistic personal mail: addresses use the reserved
`.example` / `.invalid` TLDs (RFC 2606/6761) and every subject and body is invented.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import SecretStr

from mailweave.auth.tokenstore import StoredCredentials, TokenStore
from mailweave.constants import DEFAULT_PAGE_SIZE, MAX_LIVENESS_PAGES
from mailweave.envelope import DispositionLedger, ToolName
from mailweave.envelope.response import Envelope
from mailweave.errors import ERROR_SURFACE, HANDLE_ERROR_CODES, ErrorCode, HandleRefused, Surface
from mailweave.gmail.client import GmailClient, StaticToken
from mailweave.gmail.meter import CallMeter
from mailweave.gmail.retry import BackoffPolicy
from mailweave.handles import (
    CACHE_TTL_SECONDS,
    HANDLE_TTL_SECONDS,
    MAX_CACHED_THREAD_MAPS,
    MIN_HANDLE_TTL_SECONDS,
    CachedThreadMap,
    DigestCheck,
    HandleKey,
    HandleMinter,
    HandlePayload,
    Liveness,
    Redemption,
    Step,
    ThreadMapCache,
    ensure_handle_key,
    mapping_digest,
    mint,
    redeem,
    redeem_or_raise,
    rotate_handle_key,
    verify,
)
from mailweave.handles.redeem import REDEMPTION_RUNG
from mailweave.net.egress import build_client
from mailweave.policy import BudgetAccountant, BudgetRequest, apply_floor
from mailweave.retrieval.assemble import assemble
from mailweave.retrieval.ladder import LadderRunner
from mailweave.structure.participants import ObservedText
from mailweave.structure.threadmap import build as build_thread_map
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms
from tests.fixtures.secret_models import models_with_secrets, secret_fields

NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)
UTC_ZONE = ZoneInfo("UTC")
TOKEN = "ya29.synthetic-handle-token"
ACCOUNT = "sha256:d0d0d0d0d0d0d0d0"
MARKER = "quillevant"


def msgid(name: str) -> str:
    return f"<{name}@mail.invalid>"


# --- the mailbox --------------------------------------------------------------------------


def corpus() -> tuple[Msg, ...]:
    """Two threads, one of which the query matches. Ordinary, well-formed reply headers."""
    return (
        Msg(
            id="a1",
            thread_id="t-alpha",
            sender="Ana Ito <ana@team.example>",
            subject="Rack order",
            body=f"the {MARKER} opening note",
            internal_date_ms=epoch_ms(2026, 5, 1),
            to=("bo@team.example",),
        ),
        Msg(
            id="a2",
            thread_id="t-alpha",
            sender="Bo Ng <bo@team.example>",
            subject="Re: Rack order",
            body="a reply that settles it",
            internal_date_ms=epoch_ms(2026, 5, 2),
            in_reply_to=msgid("a1"),
            to=("ana@team.example",),
        ),
        Msg(
            id="b1",
            thread_id="t-beta",
            sender="Cai Ode <cai@team.example>",
            subject="Unrelated matter",
            body="a thread the query never touches",
            internal_date_ms=epoch_ms(2026, 5, 3),
        ),
    )


def mailbox(**overrides: object) -> SyntheticMailbox:
    return SyntheticMailbox(messages=corpus(), now_ms=epoch_ms(2026, 9, 3), **overrides)  # type: ignore[arg-type]


def make_client(box: SyntheticMailbox) -> GmailClient:
    return GmailClient(
        token=StaticToken(TOKEN),
        http=build_client(inner=box.transport()),
        meter=CallMeter(),
        policy=BackoffPolicy(),
        sleeper=lambda _seconds: None,
        jitterer=lambda: 0.5,
    )


def store_in(directory: Path) -> TokenStore:
    """A real `TokenStore`, written through the real atomic 0600 path."""
    store = TokenStore(path=directory / "state" / "credentials.json")
    store.save(
        StoredCredentials(
            client_id="synthetic-client-id",
            refresh_token=SecretStr("synthetic-refresh-token"),
            salt_hex="ab" * 16,
            obtained_at="2026-09-01T00:00:00+00:00",
        )
    )
    return store


# --- minting through the real assembly ----------------------------------------------------


@dataclass(frozen=True)
class Minted:
    """One response with handles on its sources, and what it took to make."""

    envelope: Envelope
    box: SyntheticMailbox
    key: HandleKey

    def map_id(self, thread_id: str = "t-alpha") -> str:
        source = next(s for s in self.envelope.sources if s.thread_id == thread_id)
        assert source.map_id is not None, "this source carries no handle"
        return source.map_id


def mint_over(box: SyntheticMailbox, key: HandleKey, *, query: str = MARKER) -> Minted:
    client = make_client(box)
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run(query, now=NOW, zone=UTC_ZONE)
    envelope = assemble(
        run,
        client=client,
        ledger=ledger,
        minter=HandleMinter(key=key, account_hash=ACCOUNT),
    )
    return Minted(envelope=envelope, box=box, key=key)


@dataclass(frozen=True)
class Redeemed:
    outcome: Redemption
    api_calls: int


def redeem_against(
    box: SyntheticMailbox,
    map_id: str,
    key: HandleKey,
    *,
    cache: ThreadMapCache,
    now: datetime | None = None,
    account_hash: str = ACCOUNT,
    max_liveness_pages: int = 1,
) -> Redeemed:
    client = make_client(box)
    before = client.meter.reading().api_calls
    # Default to "one second after the observation this handle was minted over", so a test
    # that does not care about time is never accidentally testing a clock skew.
    when = now if now is not None else _default_instant(map_id)
    outcome = redeem(
        map_id,
        key=key,
        account_hash=account_hash,
        client=client,
        ledger=DispositionLedger(),
        cache=cache,
        now=when,
        max_liveness_pages=max_liveness_pages,
    )
    return Redeemed(outcome=outcome, api_calls=client.meter.reading().api_calls - before)


def _default_instant(map_id: str) -> datetime:
    try:
        return at_age(map_id, 1)
    except (ValueError, KeyError, TypeError, IndexError):
        # A deliberately broken handle has no readable payload, and step 1 refuses it before
        # any clock is consulted. Any instant will do, and the real one is the honest choice.
        return datetime.now(UTC)


@pytest.fixture
def key(tmp_path: Path) -> HandleKey:
    return ensure_handle_key(store_in(tmp_path))


# --- the property every one of the seven shapes shares ------------------------------------


#: How many shapes `redemption_shapes` returns. Written beside the builder rather than as a
#: literal at the call site, and it is deliberately **not** the evidence that the matrix is
#: wide enough - the answer-level assertions in the property test are. A count is a check
#: that the builder still runs; a check on the answers is a check that they reach anywhere.
REDEMPTION_SHAPE_COUNT = 11


def redemption_shapes(key: HandleKey, tmp_path: Path) -> dict[str, Redeemed]:
    """One redemption in each reachable shape, built from conditions rather than listed.

    Three of the five error classes are settled at step 1, before any network call, so they
    have no cache state; `handle_stale_unverifiable` has both; the **clean** redemption -
    `outcome is None`, which is not an error class and is the answer the whole mechanism
    exists to produce - has both; and `handle_stale` has four, because it is reached from
    two different steps and step 2 reaches it from two different walks.

    **It used to be seven, and every shape it was missing was one the property test needed**
    (R-RETR-058). Both "warm" shapes in the seven were warm only in how they were *built*:
    `handle_stale` refuses before step 3 and `handle_stale_unverifiable` bypasses the LRU by
    design, so no shape in the matrix ever served a thread from the cache and none was a
    clean redemption. Four of the property's eight clauses therefore had no witness -
    including clause (d), which exists for BLOCKER ADV-002, so planting ADV-002's own defect
    left the property green.

    Two more shapes arrive with amendment A10, and they are the ones that made two clauses
    *false* rather than vacuous - R-RETR found both by execution and neither was in the
    matrix: a `handle_stale` whose liveness is `unverifiable` because step 4 rather than
    step 2 caught the change, and a `handle_stale` from a walk that saw a change and ran out
    of pages. Clauses (e) and (g) are written against what those actually produce.

    A property asserted over a matrix is evidence only where the matrix witnesses both sides
    of each clause, so the assertions at the end of that test are over the **answers** and
    never over the names these keys are built from.
    """
    shapes: dict[str, Redeemed] = {}

    # 0. The clean redemption, cold and warm - the two shapes the seven did not reach. Warm
    #    is a second redemption of the same handle inside the cache ttl, so the LRU really
    #    serves it and `from_cache` is really true: without this shape, "the warm path never
    #    wears the cold path's label" is asserted over a population with no warm path in it.
    for state in ("cold", "warm"):
        quiet = mailbox()
        handle = mint_over(quiet, key).map_id()
        cache = ThreadMapCache()
        if state == "warm":
            assert redeem_against(quiet, handle, key, cache=cache).outcome.outcome is None
            assert len(cache) == 1
        shapes[f"clean/{state}"] = redeem_against(quiet, handle, key, cache=cache)

    # 1. handle_invalid - a handle this server did not mint. One bit of the signature moved.
    box = mailbox()
    minted = mint_over(box, key)
    good = minted.map_id()
    shapes["handle_invalid"] = redeem_against(
        box, with_one_signature_bit_flipped(good), key, cache=ThreadMapCache()
    )

    # 2. handle_key_rotated - the operator rotated the signing key.
    store = store_in(tmp_path / "rotated")
    first = ensure_handle_key(store)
    rotated_box = mailbox()
    handle_under_first = mint_over(rotated_box, first).map_id()
    second = rotate_handle_key(store)
    shapes["handle_key_rotated"] = redeem_against(
        rotated_box, handle_under_first, second, cache=ThreadMapCache()
    )

    # 3. handle_expired - the observation behind the handle has aged out.
    shapes["handle_expired"] = redeem_against(
        box, good, key, cache=ThreadMapCache(), now=at_age(good, HANDLE_TTL_SECONDS + 1)
    )

    # 4/5. handle_stale, cold and warm. Warm means the cache holds an entry that *would* be
    #      served, so the probe is the only thing that can catch the change.
    for state in ("cold", "warm"):
        moved = mailbox()
        handle = mint_over(moved, key).map_id()
        cache = ThreadMapCache()
        if state == "warm":
            assert redeem_against(moved, handle, key, cache=cache).outcome.outcome is None
            assert len(cache) == 1
        moved.add_message(
            Msg(
                id="a3",
                thread_id="t-alpha",
                sender="Ana Ito <ana@team.example>",
                subject="Re: Rack order",
                body="a message that arrived after the handle was minted",
                internal_date_ms=epoch_ms(2026, 5, 4),
                in_reply_to=msgid("a2"),
            )
        )
        shapes[f"handle_stale/{state}"] = redeem_against(moved, handle, key, cache=cache)

    # 6/7. handle_stale_unverifiable, cold and warm. Gmail no longer holds history from this
    #      handle's watermark, so the probe could not tell - which is not "nothing changed".
    for state in ("cold", "warm"):
        blind = mailbox()
        handle = mint_over(blind, key).map_id()
        cache = ThreadMapCache()
        if state == "warm":
            assert redeem_against(blind, handle, key, cache=cache).outcome.outcome is None
            assert len(cache) == 1
        blind.history_is_expired = True
        shapes[f"handle_stale_unverifiable/{state}"] = redeem_against(
            blind, handle, key, cache=cache
        )

    # 8. handle_stale reached by step **4** rather than step 2: the watermark expired, so the
    #    probe could not look, and the digest recompute caught the change the probe missed.
    #    `liveness` is honestly `unverifiable` on a `handle_stale` answer, which is the shape
    #    that makes clause (e)'s "unverifiable implies handle_stale_unverifiable" false - it
    #    was asserted for a whole round over a matrix that never produced it (R-RETR).
    late = mailbox()
    handle = mint_over(late, key).map_id()
    late.add_message(
        Msg(
            id="a3",
            thread_id="t-alpha",
            sender="Ana Ito <ana@team.example>",
            subject="Re: Rack order",
            body="a change the probe will not be allowed to see",
            internal_date_ms=epoch_ms(2026, 5, 4),
            in_reply_to=msgid("a2"),
        )
    )
    late.history_is_expired = True
    shapes["handle_stale/caught_by_the_digest"] = redeem_against(
        late, handle, key, cache=ThreadMapCache()
    )

    # 9. handle_stale from a walk that **saw** the change and then ran out of pages
    #    (amendment A10, R-RETR-059). The shape whose absence let the collapse of
    #    `handle_stale` into `handle_stale_unverifiable` sit green for a round.
    partial = mailbox(history_page_size=1)
    handle = mint_over(partial, key).map_id()
    for thread_id, message_id, day, parent in (
        ("t-alpha", "a3", 4, "a2"),
        ("t-beta", "b2", 5, "b1"),
    ):
        partial.add_message(
            Msg(
                id=message_id,
                thread_id=thread_id,
                sender="Ana Ito <ana@team.example>",
                subject="Re: a subject",
                body="a change",
                internal_date_ms=epoch_ms(2026, 5, day),
                in_reply_to=msgid(parent),
            )
        )
    shapes["handle_stale/pages_outstanding"] = redeem_against(
        partial, handle, key, cache=ThreadMapCache(), max_liveness_pages=1
    )
    return shapes


#: The three classes that are settled before any network call, so they have no cache state.
SETTLED_AT_STEP_ONE = frozenset(
    {ErrorCode.HANDLE_INVALID, ErrorCode.HANDLE_KEY_ROTATED, ErrorCode.HANDLE_EXPIRED}
)


def test_every_handle_outcome_only_claims_what_the_step_that_ran_produced(
    key: HandleKey, tmp_path: Path
) -> None:
    """The one property all nine shapes share, asserted over all nine at once.

    Nine separate tests would be nine chances to have missed the tenth. What every shape has
    in common is not its code and not its cache state: it is that **a redemption's answer is
    assembled step by step, and no field may say something the step that would have produced
    it did not do.** Each clause below is one way that could be false, and between them they
    rule out the whole family - content without a probe, a `verified_at` on a thread nothing
    verified, a restamped `fetched_at`, a warm recompute wearing the cold path's label, and
    a refusal that spent a Gmail call it did not need.

    **The matrix is checked against the answers, not against its own keys** (R-RETR-058).
    The previous version asserted `{"handle_stale/warm", ...} <= set(shapes)` - a statement
    about how the shapes were *built* - while no shape it built ever served from the cache or
    came back clean. Four clauses were vacuous under it, and one of them is ADV-002's. The
    assertions below the loop now read `outcome`, `threads_from_cache`, `digest_check` and
    `ServedThread.from_cache` off the results themselves, so a matrix that stops reaching a
    shape fails here rather than quietly asserting nothing.
    """
    shapes = redemption_shapes(key, tmp_path)
    assert len(shapes) == REDEMPTION_SHAPE_COUNT, sorted(shapes)

    for name, result in shapes.items():
        outcome, trace = result.outcome, result.outcome.trace
        because = f"shape {name}"

        # (a) The answer is in the closed vocabulary, and its surface is D.11's.
        assert outcome.outcome is None or outcome.outcome in HANDLE_ERROR_CODES, because
        assert outcome.surface == (
            None if outcome.outcome is None else ERROR_SURFACE[outcome.outcome]
        ), because

        # (b) Content is served exactly on the two answers that carry content, and content
        #     is never served without both content-producing steps having run.
        #
        #     **The converse is deliberately not asserted, and the widened matrix is why.**
        #     This clause used to read `served == (FETCH in steps and DIGEST in steps)`, a
        #     biconditional, and it is false on the shape where step 2 could not look and
        #     step 4 caught the change: all four steps ran, the recompute disagreed, and the
        #     map was refused. That is step 4 doing exactly its job. Asserting the
        #     biconditional would have forbidden the defence-in-depth branch from refusing
        #     anything - and the old matrix never produced that branch, so nobody found out.
        served = outcome.content_was_served
        assert served == (outcome.outcome in {None, ErrorCode.HANDLE_STALE_UNVERIFIABLE}), because
        if served:
            assert Step.FETCH in trace.steps and Step.DIGEST in trace.steps, because
        elif Step.DIGEST in trace.steps:
            assert trace.digest_check is DigestCheck.MISMATCH, because

        # (c) A step that did not run leaves its field at "not reached" - and a refusal at
        #     step 1 spends nothing, because step 1 reads a string and a key on disk.
        settled_early = outcome.outcome in SETTLED_AT_STEP_ONE
        assert (trace.liveness is Liveness.NOT_REACHED) == settled_early, because
        assert (trace.steps == (Step.VERIFY,)) == settled_early, because
        assert (result.api_calls == 0) == settled_early, because

        # (d) The digest label is a fact about where the content came from, never a claim.
        assert (trace.digest_check is DigestCheck.CACHE_TAUTOLOGY) == bool(
            trace.threads_from_cache
        ), because
        if not served:
            assert trace.digest_check in {DigestCheck.NOT_REACHED, DigestCheck.MISMATCH}, because

        # (e) A probe that could not tell never serves from the cache: the LRU is bypassed
        #     whole, because "it failed to look" is not a reason to keep serving what it was
        #     going to check. And it never comes back clean - but it is **not** always
        #     `handle_stale_unverifiable`, which is what this clause used to assert and what
        #     R-RETR falsified by execution: when step 2 could not look and step 4 caught the
        #     change, the honest answer is `handle_stale` with an `unverifiable` liveness,
        #     and the pair names which step found it.
        if trace.liveness is Liveness.UNVERIFIABLE:
            assert trace.threads_from_cache == (), because
            assert outcome.outcome in {
                ErrorCode.HANDLE_STALE_UNVERIFIABLE,
                ErrorCode.HANDLE_STALE,
            }, because
            if outcome.outcome is ErrorCode.HANDLE_STALE:
                assert trace.digest_check is DigestCheck.MISMATCH, because

        # (f) Per served thread: `fetched_at` is the read that produced the content and is
        #     never `now`; `verified_at` exists exactly for the cache case and follows it.
        for thread in outcome.served:
            fetched = datetime.fromisoformat(thread.fetched_at)
            assert (thread.verified_at is not None) == thread.from_cache, because
            if thread.from_cache:
                assert thread.verified_at is not None
                verified = datetime.fromisoformat(thread.verified_at)
                assert verified >= fetched, because
                assert fetched < verified, f"{because}: fetched_at was restamped"

        # (g) A stale answer names what moved, **through whichever step found it**. This
        #     clause used to read `if handle_stale: assert trace.changed`, which is false on
        #     the digest-recompute branch: step 4 finds that the maps no longer digest to the
        #     handle's value and has no per-thread record to list, because step 2 is the only
        #     step that reads history. R-RETR reached that shape and the matrix did not, so
        #     the clause asserted a falsehood over a population that could not contain it.
        #     The account is now required from the step that produced the finding.
        if outcome.outcome is ErrorCode.HANDLE_STALE:
            if trace.liveness is Liveness.CHANGED:
                assert trace.changed, because
            else:
                assert trace.digest_check is DigestCheck.MISMATCH, because
                assert trace.changed == {}, because
        assert outcome.detail.strip(), because

        # (h) D.11's re-derivation call is carried exactly where one can honestly be minted:
        #     after the signature verified. The two classes decided before it read an
        #     unverified document, and nothing in one may fill a connector-voiced field.
        decided_unverified = outcome.outcome in {
            ErrorCode.HANDLE_INVALID,
            ErrorCode.HANDLE_KEY_ROTATED,
        }
        if decided_unverified or outcome.outcome is None:
            assert outcome.affordance is None, because
        else:
            assert outcome.affordance is not None, because
            assert outcome.affordance.tool is ToolName.THREAD_MAP, because

    # --- the matrix reaches every shape the clauses above assert about ---------------
    #
    # Every assertion here is over a **produced answer**. Each one names the clause it
    # keeps honest, so a later change that stops reaching a shape reports which half of
    # which biconditional has just gone vacuous.
    results = tuple(shapes.values())
    reached = {result.outcome.outcome for result in results}
    assert reached == HANDLE_ERROR_CODES | {None}, sorted(
        str(code) for code in (HANDLE_ERROR_CODES | {None}) - reached
    )
    # (b), (c): a redemption that came back clean, and one settled at step 1 spending nothing.
    assert any(r.outcome.outcome is None for r in results), "clause (b)'s `outcome is None`"
    assert any(r.outcome.content_was_served for r in results), "clause (b)'s served half"
    assert any(not r.outcome.content_was_served for r in results), "clause (b)'s refused half"
    assert any(
        not r.outcome.content_was_served and Step.DIGEST in r.outcome.trace.steps for r in results
    ), "clause (b)'s elif - all four steps ran and the answer was still refused"
    assert any(r.api_calls == 0 for r in results), "clause (c)'s zero-call half"
    assert any(r.api_calls > 0 for r in results), "clause (c)'s other half"
    # (d): both sides of the digest-label biconditional. Without the second of these,
    #      planting `check = RECOMPUTED_FROM_FETCH` unconditionally leaves the clause true.
    assert any(
        r.outcome.trace.digest_check is DigestCheck.RECOMPUTED_FROM_FETCH for r in results
    ), "clause (d)'s cold side"
    assert any(r.outcome.trace.digest_check is DigestCheck.CACHE_TAUTOLOGY for r in results), (
        "clause (d)'s warm side - the one BLOCKER ADV-002 is about"
    )
    assert any(r.outcome.trace.threads_from_cache for r in results), "clause (e)'s cache half"
    # (e): and an unverifiable probe, so the clause has a shape to be false on.
    assert any(r.outcome.trace.liveness is Liveness.UNVERIFIABLE for r in results), "clause (e)"
    # (f): a thread actually served from the LRU, so `from_cache` reaches both values and the
    #      `fetched_at` / `verified_at` arm has something to compare.
    assert any(t.from_cache for r in results for t in r.outcome.served), "clause (f)'s warm half"
    assert any(not t.from_cache for r in results for t in r.outcome.served), "clause (f)'s cold"
    assert any(t.verified_at is not None for r in results for t in r.outcome.served), "(f)"
    # (e), (g): both ways a `handle_stale` is reached, so neither branch of either clause is
    #           asserted over an empty set. Without the second of these, clause (g) reads
    #           `assert trace.changed` over a population with no digest-caught staleness in
    #           it - which is how it came to assert something false.
    assert any(
        r.outcome.outcome is ErrorCode.HANDLE_STALE and r.outcome.trace.liveness is Liveness.CHANGED
        for r in results
    ), "clause (g)'s step-2 branch"
    assert any(
        r.outcome.outcome is ErrorCode.HANDLE_STALE
        and r.outcome.trace.liveness is Liveness.UNVERIFIABLE
        for r in results
    ), "clause (g)'s step-4 branch, and clause (e)'s handle_stale case"
    # And amendment A10's own shape: a walk that saw a change and ran out of pages.
    assert any(
        r.outcome.outcome is ErrorCode.HANDLE_STALE and r.outcome.trace.liveness_pages == 1
        for r in results
    ), "A10's incomplete-walk-that-saw-something shape"


def test_every_handle_error_class_is_one_this_product_can_actually_produce(
    key: HandleKey, tmp_path: Path
) -> None:
    """The closed-vocabulary sweep, as equality rather than containment.

    The same question round 20 asked of `Linkage`: a vocabulary wider than the code is a claim
    wider than the code. `HANDLE_ERROR_CODES` is derived from `ErrorCode` by prefix rather
    than listed, so a sixth handle class added to D.11 is in this set the moment it exists -
    and this assertion then fails until something produces it.
    """
    produced = {
        result.outcome.outcome
        for result in redemption_shapes(key, tmp_path).values()
        if result.outcome.outcome is not None
    }
    assert produced == HANDLE_ERROR_CODES


# --- PF-15, both arms ---------------------------------------------------------------------


def test_pf15_mutate_then_redeem_cache_cold(key: HandleKey) -> None:
    """PF-15 arm 1. A handle over a thread that then gained a message is refused.

    Cold means nothing was cached, so the change would also have been caught by the digest
    recompute. That is the arm that has always been easy; it is here because a pass on the
    warm arm alone would not tell us the cold path works either.
    """
    box = mailbox()
    handle = mint_over(box, key).map_id()
    box.add_message(
        Msg(
            id="a3",
            thread_id="t-alpha",
            sender="Ana Ito <ana@team.example>",
            subject="Re: Rack order",
            body="an arrival after the mint",
            internal_date_ms=epoch_ms(2026, 5, 4),
            in_reply_to=msgid("a2"),
        )
    )
    result = redeem_against(box, handle, key, cache=ThreadMapCache())
    assert result.outcome.outcome is ErrorCode.HANDLE_STALE
    assert result.outcome.trace.liveness is Liveness.CHANGED
    assert result.outcome.trace.changed == {"t-alpha": "1 messages added"}
    # The probe caught it, so the fetch never ran: a refused handle does not pay for a map.
    assert result.outcome.trace.steps == (Step.VERIFY, Step.LIVENESS)
    assert result.outcome.served == ()


def test_pf15_mutate_then_redeem_cache_warm(key: HandleKey) -> None:
    """PF-15 arm 2, and the one ADV-002 was about.

    The cache holds an entry for this exact `(thread_id, history_id_at_fetch)` and it would be
    served. If staleness were checked by recomputing `mapping_digest` over that cached map -
    which is what the previous design did - the comparison would be `digest(x) == digest(x)`,
    true by construction, and `handle_stale` could never fire on a cache hit. It fires,
    because step 2 reads `history.list`: a different resource, which the cache knows nothing
    about and cannot make pass.
    """
    box = mailbox()
    handle = mint_over(box, key).map_id()
    cache = ThreadMapCache()
    warm = redeem_against(box, handle, key, cache=cache)
    assert warm.outcome.outcome is None
    assert len(cache) == 1, "the first redemption did not warm the cache, so arm 2 is vacuous"

    box.add_message(
        Msg(
            id="a3",
            thread_id="t-alpha",
            sender="Ana Ito <ana@team.example>",
            subject="Re: Rack order",
            body="an arrival after the mint",
            internal_date_ms=epoch_ms(2026, 5, 4),
            in_reply_to=msgid("a2"),
        )
    )
    # The entry is still there and still live, so it is genuinely a warm redemption.
    assert (
        cache.get(thread_id="t-alpha", history_id=_handle_history(handle), now=at_age(handle, 1))
        is not None
    )

    result = redeem_against(box, handle, key, cache=cache)
    assert result.outcome.outcome is ErrorCode.HANDLE_STALE
    assert result.outcome.trace.liveness is Liveness.CHANGED
    assert result.outcome.served == ()
    # And the entry the probe just contradicted is gone.
    assert len(cache) == 0


def test_a_warm_redemption_labels_its_digest_check_a_cache_tautology(key: HandleKey) -> None:
    """AD A.10: on a cache hit the recompute is tautological and the trace says so.

    This is the label that stops the warm path claiming the cold path's guarantee - which
    would be exactly the over-claim defect Part 0 of this round is about, committed inside the
    round that fixes it. It is derived from where the content came from, so a warm redemption
    cannot be made to report `recomputed_from_fetch` by any caller.
    """
    box = mailbox()
    handle = mint_over(box, key).map_id()
    cache = ThreadMapCache()

    cold = redeem_against(box, handle, key, cache=cache)
    assert cold.outcome.outcome is None
    assert cold.outcome.trace.digest_check is DigestCheck.RECOMPUTED_FROM_FETCH
    assert cold.outcome.trace.threads_from_cache == ()
    assert cold.outcome.trace.threads_fetched == ("t-alpha",)

    warm = redeem_against(box, handle, key, cache=cache)
    assert warm.outcome.outcome is None
    assert warm.outcome.trace.digest_check is DigestCheck.CACHE_TAUTOLOGY
    assert warm.outcome.trace.threads_from_cache == ("t-alpha",)
    assert warm.outcome.trace.threads_fetched == ()
    # The saving is real - the warm redemption did not re-fetch the thread - and the probe
    # still ran, which is the point: the cache saves step 3, never step 2.
    assert warm.api_calls == 1 < cold.api_calls
    assert warm.outcome.trace.liveness is Liveness.VERIFIED_UNCHANGED


def with_one_signature_bit_flipped(map_id: str) -> str:
    """The same handle with one bit of its signature moved, and it really is one bit.

    Flipping the last *character* of the base64url signature is not a corruption: the final
    character of a 32-byte encoding carries only two significant bits, so several characters
    decode to the same byte and the "corrupted" handle verifies. This decodes, flips a bit of
    the first byte, and re-encodes - which is a difference `hmac.compare_digest` must see.
    """
    encoded, _dot, signature = map_id.partition(".")
    raw = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
    moved = bytes([raw[0] ^ 0x01]) + raw[1:]
    assert moved != raw
    return f"{encoded}.{base64.urlsafe_b64encode(moved).decode('ascii').rstrip('=')}"


def _payload_of(map_id: str) -> dict[str, object]:
    """A handle's payload, decoded without verifying it. Tests only."""
    encoded = map_id.partition(".")[0]
    return dict(json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))))


def _handle_history(map_id: str) -> str:
    """The per-thread `historyId` a handle carries."""
    return str(_payload_of(map_id)["thread_history_ids"][0])  # type: ignore[index]


def at_age(map_id: str, seconds: float) -> datetime:
    """A redemption instant `seconds` after the observation this handle was minted over.

    Every expiry and every TTL in this module is measured from `fetched_at`, and `fetched_at`
    is the wall clock the `threads.get` read - not the fixture's `NOW`, which is the query's
    time policy. Deriving the redemption instant from the handle itself is what makes these
    tests statements about the handle's own age rather than about two clocks agreeing.
    """
    fetched = datetime.fromisoformat(str(_payload_of(map_id)["fetched_at"]))
    return fetched + timedelta(seconds=seconds)


# --- fetched_at is never restamped --------------------------------------------------------


def test_a_cached_map_keeps_the_stamp_of_the_read_that_produced_it(key: HandleKey) -> None:
    """`fetched_at` is the cache entry's own fetch time and is never restamped (AD A.10).

    Two fields, both true: this content was read at T0; it was verified unchanged at T1.
    Restamping would assert a freshness the response does not have - and, the sharper half,
    would make a handle that cannot expire, because expiry is measured from `fetched_at`.
    """
    box = mailbox()
    handle = mint_over(box, key).map_id()
    cache = ThreadMapCache()
    cold = redeem_against(box, handle, key, cache=cache)
    first_stamp = cold.outcome.served[0].fetched_at
    assert cold.outcome.served[0].verified_at is None

    later = at_age(handle, 30)
    warm = redeem_against(box, handle, key, cache=cache, now=later)
    served = warm.outcome.served[0]
    assert served.from_cache is True
    assert served.fetched_at == first_stamp
    assert served.verified_at == later.isoformat()
    assert datetime.fromisoformat(served.fetched_at) < datetime.fromisoformat(served.verified_at)


def test_a_handle_in_continuous_use_still_expires(key: HandleKey) -> None:
    """The consequence of the rule above, stated as the thing it protects.

    A handle whose age restarted whenever it was served is a handle that cannot expire. This
    redeems the same handle repeatedly across the whole TTL and then once past it, and the
    last one is refused - which is only true because nothing along the way rewrote the stamp
    expiry is measured from.
    """
    box = mailbox()
    handle = mint_over(box, key).map_id()
    cache = ThreadMapCache()
    for offset in range(0, HANDLE_TTL_SECONDS, CACHE_TTL_SECONDS // 2):
        result = redeem_against(box, handle, key, cache=cache, now=at_age(handle, offset))
        assert result.outcome.outcome is None, offset
    past = redeem_against(box, handle, key, cache=cache, now=at_age(handle, HANDLE_TTL_SECONDS))
    assert past.outcome.outcome is ErrorCode.HANDLE_EXPIRED


# --- the three step-1 classes are distinct, and stay distinct ------------------------------


def test_a_deliberate_key_rotation_is_reported_as_a_rotation_and_not_as_age(
    tmp_path: Path,
) -> None:
    """The plan's own acceptance line: rotation yields `handle_key_rotated`, not `handle_expired`.

    They have different causes and different remedies, and the handle in this test is
    *seconds* old - so a server that reported `handle_expired` would be telling an operator
    that time had passed when what happened is that they rotated a key.
    """
    store = store_in(tmp_path)
    first = ensure_handle_key(store)
    box = mailbox()
    handle = mint_over(box, first).map_id()

    second = rotate_handle_key(store)
    assert second.epoch == first.epoch + 1
    assert second.material != first.material

    result = redeem_against(box, handle, second, cache=ThreadMapCache())
    assert result.outcome.outcome is ErrorCode.HANDLE_KEY_ROTATED
    assert result.api_calls == 0
    # And the old key is genuinely gone: the store holds one epoch, not a keyring.
    assert ensure_handle_key(store).material == second.material


def test_a_restart_does_not_invalidate_an_outstanding_handle(tmp_path: Path) -> None:
    """ADV-212: the key is on disk, so a restart is not a rotation.

    Modelled as a restart really is - the process's `HandleKey` object is discarded and a new
    one is loaded from the same `0600` store - which is the whole of why the key lives there
    rather than in memory. The previous design's `handle_expired`-on-a-fresh-handle was this.
    """
    store = store_in(tmp_path)
    before_restart = ensure_handle_key(store)
    box = mailbox()
    handle = mint_over(box, before_restart).map_id()

    del before_restart
    after_restart = ensure_handle_key(TokenStore(path=store.path))
    result = redeem_against(box, handle, after_restart, cache=ThreadMapCache())
    assert result.outcome.outcome is None
    assert result.outcome.trace.liveness is Liveness.VERIFIED_UNCHANGED


def test_a_refusal_carries_the_re_derivation_call_only_once_it_has_verified(
    key: HandleKey, tmp_path: Path
) -> None:
    """AD D.11's affordance column, and the one narrowing of it this module makes.

    `handle_expired`, `handle_stale` and `handle_stale_unverifiable` are decided after the
    signature verified, so the threads a handle names are this server's own statement and an
    executable `mailweave_thread_map` call over them is honest. `handle_invalid` and
    `handle_key_rotated` are decided while the payload is still unverified - the epoch has to
    be read before the signature, because with the rotated key gone the signature cannot
    verify either way - so their arguments would be caller-supplied strings in a
    connector-voiced field, which is the route R-SEC-030/032 closed on the disclosure side.
    Those two name the call in words and carry none.
    """
    box = mailbox()
    handle = mint_over(box, key).map_id()
    expired = redeem_against(
        box, handle, key, cache=ThreadMapCache(), now=at_age(handle, HANDLE_TTL_SECONDS + 1)
    ).outcome
    assert expired.outcome is ErrorCode.HANDLE_EXPIRED
    assert expired.affordance is not None
    assert expired.affordance.mentions("t-alpha")

    invalid = redeem_against(
        box, with_one_signature_bit_flipped(handle), key, cache=ThreadMapCache()
    ).outcome
    assert invalid.affordance is None
    assert ToolName.THREAD_MAP.value in invalid.detail

    store = store_in(tmp_path / "rotated")
    first = ensure_handle_key(store)
    under_first = mint_over(mailbox(), first).map_id()
    rotated = redeem_against(
        box, under_first, rotate_handle_key(store), cache=ThreadMapCache()
    ).outcome
    assert rotated.outcome is ErrorCode.HANDLE_KEY_ROTATED
    assert rotated.affordance is None
    assert ToolName.THREAD_MAP.value in rotated.detail


def test_a_thread_id_inside_an_unverified_handle_is_bounded_like_every_other_id() -> None:
    """A caller-supplied document with a megabyte "thread id" is refused at the shape.

    Without a per-element bound, `thread_ids` is `tuple[str, ...]`: whatever is in it would
    reach a refusal message, and - if an affordance were minted before verification - a
    connector-voiced field. It is bounded at the length the disposition seal bounds an id at,
    imported rather than restated.
    """
    with pytest.raises(ValueError):
        HandlePayload(
            v=1,
            key_epoch=0,
            account_hash=ACCOUNT,
            thread_ids=("t" * 5000,),
            thread_history_ids=("99120034",),
            fetched_at=NOW.isoformat(),
            history_id="99120034",
            mapping_digest="0" * 32,
            page_sizes=(1,),
            ttl=HANDLE_TTL_SECONDS,
        )


def test_a_handle_minted_for_another_mailbox_is_invalid_here(key: HandleKey) -> None:
    """The account is inside the signed payload, so this is not a handle that went wrong."""
    box = mailbox()
    handle = mint_over(box, key).map_id()
    result = redeem_against(
        box, handle, key, cache=ThreadMapCache(), account_hash="sha256:someone-else"
    )
    assert result.outcome.outcome is ErrorCode.HANDLE_INVALID
    assert result.api_calls == 0


@pytest.mark.parametrize(
    "mangle",
    [
        pytest.param(lambda handle: "", id="empty"),
        pytest.param(lambda handle: "not-a-handle", id="no separator"),
        pytest.param(lambda handle: f"...{handle}", id="too many separators"),
        pytest.param(lambda handle: handle.partition(".")[0], id="payload only"),
        pytest.param(lambda handle: f"%%%.{handle.partition('.')[2]}", id="payload not base64"),
        pytest.param(lambda handle: f"{handle}x" * 4000, id="unbounded"),
    ],
)
def test_a_handle_that_is_not_one_is_refused_without_quoting_it(
    key: HandleKey, mangle: object
) -> None:
    """`handle_invalid`, and the refusal names nothing the caller sent.

    A `map_id` is the one tool argument an agent will paste from somewhere else, so a report
    that renders `input_value=...` renders whatever was sent - the same channel R-SEC-043
    closed for the credential file, arriving on a caller-supplied document instead of a
    secret-bearing one. `HandlePayload` carries `hide_input_in_errors` and the refusal is
    built from `failure_summary`, which prints field paths and error types only.
    """
    box = mailbox()
    handle = mint_over(box, key).map_id()
    broken = mangle(handle)  # type: ignore[operator]
    result = redeem_against(box, broken, key, cache=ThreadMapCache())
    assert result.outcome.outcome is ErrorCode.HANDLE_INVALID
    assert result.api_calls == 0
    if broken:
        assert broken[: min(len(broken), 40)] not in result.outcome.detail


def test_a_payload_re_signed_under_another_key_does_not_verify(
    key: HandleKey, tmp_path: Path
) -> None:
    """The signature is over the encoded bytes as received, and it is compared constantly."""
    box = mailbox()
    handle = mint_over(box, key).map_id()
    other = ensure_handle_key(store_in(tmp_path / "other"))
    assert other.material != key.material
    encoded = handle.partition(".")[0]
    forged = mint(
        other,
        account_hash=ACCOUNT,
        history_id_at_fetch={"t-alpha": "99120034"},
        mailbox_history_id="99120034",
        fetched_at=NOW.isoformat(),
        mapping_digest="0" * 32,
        page_sizes={"t-alpha": 1},
    )
    hybrid = f"{encoded}.{forged.partition('.')[2]}"
    assert redeem_against(box, hybrid, key, cache=ThreadMapCache()).outcome.outcome is (
        ErrorCode.HANDLE_INVALID
    )


# --- the liveness probe is independent, and asks about all four change types --------------


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        pytest.param(
            lambda box: box.delete_message("a2"), "1 messages deleted", id="messageDeleted"
        ),
        pytest.param(
            lambda box: box.relabel_message("a1", add=("SPAM",)),
            "1 label additions",
            id="labelAdded",
        ),
        pytest.param(
            lambda box: box.relabel_message("a1", remove=("INBOX",)),
            "1 label removals",
            id="labelRemoved",
        ),
    ],
)
def test_a_handle_notices_every_way_the_mailbox_can_move_under_it(
    key: HandleKey, mutate: object, expected: str
) -> None:
    """All four `historyTypes`, because a handle's claim covers all four.

    A map carries provenance from a message's own labels (OD-5) and an enumeration of the
    thread's messages, so a deletion and a relabel both invalidate it. Asking `history.list`
    only about `messageAdded` - which is what the LR rung needs and what this client did
    before WS-06 - would make `handle_stale` a claim about one of the four ways a mailbox
    moves, stated as though it covered all four.
    """
    box = mailbox()
    handle = mint_over(box, key).map_id()
    mutate(box)  # type: ignore[operator]
    result = redeem_against(box, handle, key, cache=ThreadMapCache())
    assert result.outcome.outcome is ErrorCode.HANDLE_STALE
    assert result.outcome.trace.changed == {"t-alpha": expected}


def test_a_change_to_another_thread_does_not_make_this_handle_stale(key: HandleKey) -> None:
    """The probe is about the threads the handle names, and only those."""
    box = mailbox()
    handle = mint_over(box, key).map_id()
    box.add_message(
        Msg(
            id="b2",
            thread_id="t-beta",
            sender="Cai Ode <cai@team.example>",
            subject="Re: Unrelated matter",
            body="a change somewhere else entirely",
            internal_date_ms=epoch_ms(2026, 5, 5),
            in_reply_to=msgid("b1"),
        )
    )
    result = redeem_against(box, handle, key, cache=ThreadMapCache())
    assert result.outcome.outcome is None
    assert result.outcome.trace.liveness is Liveness.VERIFIED_UNCHANGED


def test_a_history_walk_that_stopped_early_is_unverifiable_rather_than_clean(
    key: HandleKey,
) -> None:
    """The second way a probe fails to be conclusive, and it is not a 404.

    A walk that stopped with a continuation token outstanding has not seen the pages it did
    not fetch, so "nothing changed" is a claim about a window it did not read. Folding that
    into "clean" is the confident-but-wrong answer a handle exists to prevent, and the class
    for it is the same one the 404 gets: the probe could not tell.

    **This arm mutates a thread the handle does not name, and that is only half the case**
    (R-RETR-059, amendment A10). The peer - the same pagination with a change to the *named*
    thread on the page the walk did read - is
    `test_a_walk_that_saw_a_change_and_ran_out_of_pages_reports_what_it_saw`, and it is the
    one that was wrong: `probe.touched` was discarded and the served response said the
    change could not be verified.
    """
    box = mailbox(history_page_size=1)
    handle = mint_over(box, key).map_id()
    # Two changes to a thread the handle does not name, so a one-page walk stops with pages
    # outstanding while nothing about the named thread has moved.
    for index in (2, 3):
        box.add_message(
            Msg(
                id=f"b{index}",
                thread_id="t-beta",
                sender="Cai Ode <cai@team.example>",
                subject="Re: Unrelated matter",
                body="another change elsewhere",
                internal_date_ms=epoch_ms(2026, 5, 4 + index),
                in_reply_to=msgid("b1"),
            )
        )
    result = redeem_against(box, handle, key, cache=ThreadMapCache(), max_liveness_pages=1)
    assert result.outcome.outcome is ErrorCode.HANDLE_STALE_UNVERIFIABLE
    assert result.outcome.trace.liveness is Liveness.UNVERIFIABLE
    # Content is still served - the class is in band - and it is a live read, not the cache.
    assert result.outcome.served and result.outcome.trace.threads_from_cache == ()


def test_a_walk_that_saw_a_change_and_ran_out_of_pages_reports_what_it_saw(
    key: HandleKey,
) -> None:
    """Amendment A10's second rule, and the honesty class this round exists inside.

    The walk reads page 1, finds the named thread moved, and stops with a continuation token
    outstanding. `pages_exhausted` devalues the *absence* of a record; it says nothing about
    a record already read. The answer is `handle_stale`, naming what moved, with content
    refused and the re-derivation call attached.

    Before A10 this shape fell through into `handle_stale_unverifiable`: `trace.changed` was
    emptied, the map was served, and the response asserted that whether these threads changed
    could not be verified from history - which this same probe had already determined. Two
    assertions below are that sentence's absence and this one's presence.
    """
    box = mailbox(history_page_size=1)
    handle = mint_over(box, key).map_id()
    # Page 1: the named thread moves. Page 2: something else does, so the walk stops short.
    box.add_message(
        Msg(
            id="a3",
            thread_id="t-alpha",
            sender="Ana Ito <ana@team.example>",
            subject="Re: Rack order",
            body="a change to the named thread, on the page the walk does read",
            internal_date_ms=epoch_ms(2026, 5, 4),
            in_reply_to=msgid("a2"),
        )
    )
    box.add_message(
        Msg(
            id="b2",
            thread_id="t-beta",
            sender="Cai Ode <cai@team.example>",
            subject="Re: Unrelated matter",
            body="a change elsewhere, on the page the walk does not reach",
            internal_date_ms=epoch_ms(2026, 5, 5),
            in_reply_to=msgid("b1"),
        )
    )
    result = redeem_against(box, handle, key, cache=ThreadMapCache(), max_liveness_pages=1)
    outcome = result.outcome
    assert outcome.outcome is ErrorCode.HANDLE_STALE
    assert outcome.trace.liveness is Liveness.CHANGED
    assert outcome.trace.changed == {"t-alpha": "1 messages added"}
    assert outcome.served == ()
    assert outcome.affordance is not None
    # The refusal spends nothing beyond the probe: a change seen is a change seen, and the
    # map is not fetched to confirm it.
    assert outcome.trace.steps == (Step.VERIFY, Step.LIVENESS)
    assert "could not be verified" not in outcome.detail
    # ...and the incompleteness of the *list* is declared, which is a different claim from
    # the incompleteness of the finding.
    assert "at least what moved" in outcome.detail


def test_an_unverifiable_probe_is_reserved_for_a_walk_that_observed_nothing(
    key: HandleKey,
) -> None:
    """The partition A10 draws, asserted as a partition rather than as two examples.

    Over both ways a walk can fail to finish - the 404 and the outstanding page - and both
    ways it can end - having seen a change to a named thread or not - the class is decided by
    what was *observed*, never by whether the walk finished. Each cell records the pair
    `(outcome, liveness)`, because the pair is what says **which step** decided, and three
    different steps decide these four cells.

    The 404 row is the one that would be mis-read as a duplicate. Gmail's 404 returns
    `touched={}` whatever moved, so step 2 cannot see the change and the honest liveness
    value is `unverifiable` in both cells; the change is then caught one step later by the
    digest recompute, which is the defence-in-depth branch and reports itself as such. That
    is a different mechanism from the row above it and the pair makes the difference visible
    rather than collapsing the two into one `handle_stale`.
    """

    def move(box: SyntheticMailbox, thread_id: str, message_id: str, day: int) -> None:
        box.add_message(
            Msg(
                id=message_id,
                thread_id=thread_id,
                sender="Cai Ode <cai@team.example>",
                subject="Re: a subject",
                body="a change",
                internal_date_ms=epoch_ms(2026, 5, day),
                in_reply_to=msgid("a2" if thread_id == "t-alpha" else "b1"),
            )
        )

    cells: dict[tuple[str, bool], tuple[ErrorCode | None, Liveness]] = {}
    for how in ("pages_outstanding", "watermark_expired"):
        for saw_a_change in (True, False):
            box = mailbox(history_page_size=1 if how == "pages_outstanding" else None)
            handle = mint_over(box, key).map_id()
            if saw_a_change:
                move(box, "t-alpha", "a3", 4)
            move(box, "t-beta", "b2", 5)
            move(box, "t-beta", "b3", 6)
            if how == "watermark_expired":
                box.history_is_expired = True
            result = redeem_against(box, handle, key, cache=ThreadMapCache(), max_liveness_pages=1)
            cells[(how, saw_a_change)] = (result.outcome.outcome, result.outcome.trace.liveness)

    assert cells == {
        # Step 2 saw it, on the page it did read. The unread page changes nothing.
        ("pages_outstanding", True): (ErrorCode.HANDLE_STALE, Liveness.CHANGED),
        # Step 2 saw nothing and could not finish. This is the class's whole population.
        ("pages_outstanding", False): (
            ErrorCode.HANDLE_STALE_UNVERIFIABLE,
            Liveness.UNVERIFIABLE,
        ),
        # Step 2 could not look at all; step 4 caught it. `unverifiable` is still the honest
        # liveness value, and the outcome is not this class's, which is the point.
        ("watermark_expired", True): (ErrorCode.HANDLE_STALE, Liveness.UNVERIFIABLE),
        ("watermark_expired", False): (
            ErrorCode.HANDLE_STALE_UNVERIFIABLE,
            Liveness.UNVERIFIABLE,
        ),
    }


def test_an_unverifiable_probe_bypasses_the_cache_and_evicts_what_it_could_not_check(
    key: HandleKey,
) -> None:
    """AD A.10: on `handle_stale_unverifiable` the LRU is bypassed and step 3 is forced live.

    A probe that failed to look is not a reason to keep serving what it was going to check -
    which is the same reasoning as ADV-002's, one branch over.
    """
    box = mailbox()
    handle = mint_over(box, key).map_id()
    cache = ThreadMapCache()
    assert redeem_against(box, handle, key, cache=cache).outcome.outcome is None
    assert len(cache) == 1

    box.history_is_expired = True
    result = redeem_against(box, handle, key, cache=cache)
    assert result.outcome.outcome is ErrorCode.HANDLE_STALE_UNVERIFIABLE
    assert result.outcome.trace.threads_from_cache == ()
    assert result.outcome.trace.threads_fetched == ("t-alpha",)
    assert result.outcome.trace.evicted == 1
    assert result.outcome.served[0].from_cache is False


def test_the_liveness_probe_is_charged_before_the_fetch_and_the_fetch_is_skipped(
    key: HandleKey,
) -> None:
    """The order is the design: probe first, and a refused handle never pays for a map."""
    box = mailbox()
    handle = mint_over(box, key).map_id()
    box.calls.clear()
    box.call_log.clear()
    box.add_message(
        Msg(
            id="a3",
            thread_id="t-alpha",
            sender="Ana Ito <ana@team.example>",
            subject="Re: Rack order",
            body="an arrival after the mint",
            internal_date_ms=epoch_ms(2026, 5, 4),
            in_reply_to=msgid("a2"),
        )
    )
    redeem_against(box, handle, key, cache=ThreadMapCache())
    assert box.call_log == ["history.list"], box.call_log


# --- the LRU, as specified ----------------------------------------------------------------


def cached(thread_id: str, history_id: str, *, stored_at: datetime = NOW) -> CachedThreadMap:
    return CachedThreadMap(
        thread_map=build_thread_map(thread_id=thread_id, messages=(), positions={}),
        fetched_at=stored_at.isoformat(),
        history_id=history_id,
        stored_at=stored_at,
    )


def test_the_lru_is_keyed_on_the_thread_and_the_history_id_it_was_fetched_at() -> None:
    """The `historyId` is *in the key*, so an entry is never a claim about "this thread now"."""
    cache = ThreadMapCache()
    cache.put(cached("t-alpha", "100"))
    assert cache.get(thread_id="t-alpha", history_id="100", now=NOW) is not None
    assert cache.get(thread_id="t-alpha", history_id="101", now=NOW) is None
    assert cache.get(thread_id="t-beta", history_id="100", now=NOW) is None


def test_a_cache_entry_expires_on_read_rather_than_only_on_write() -> None:
    """A cache that expires only on write keeps serving a quiet mailbox's stale entry."""
    cache = ThreadMapCache()
    cache.put(cached("t-alpha", "100"))
    just_inside = NOW + timedelta(seconds=CACHE_TTL_SECONDS - 1)
    assert cache.get(thread_id="t-alpha", history_id="100", now=just_inside) is not None
    just_outside = NOW + timedelta(seconds=CACHE_TTL_SECONDS)
    assert cache.get(thread_id="t-alpha", history_id="100", now=just_outside) is None
    assert len(cache) == 0


def test_the_cache_holds_sixty_four_thread_maps_and_evicts_the_least_recently_used() -> None:
    cache = ThreadMapCache()
    for index in range(MAX_CACHED_THREAD_MAPS):
        cache.put(cached(f"t-{index}", "100"))
    assert len(cache) == MAX_CACHED_THREAD_MAPS
    # Touch the oldest so it is no longer the least recently *used*.
    assert cache.get(thread_id="t-0", history_id="100", now=NOW) is not None
    cache.put(cached("t-new", "100"))
    assert len(cache) == MAX_CACHED_THREAD_MAPS
    assert cache.get(thread_id="t-0", history_id="100", now=NOW) is not None
    assert cache.get(thread_id="t-1", history_id="100", now=NOW) is None


def test_eviction_on_staleness_drops_every_entry_for_that_thread() -> None:
    """At any `historyId`: the thread moved, so no view of it that predates the move survives."""
    cache = ThreadMapCache()
    cache.put(cached("t-alpha", "100"))
    cache.put(cached("t-alpha", "101"))
    cache.put(cached("t-beta", "100"))
    assert cache.evict_thread("t-alpha") == 2
    assert cache.keys == (("t-beta", "100"),)


def test_the_cache_ttl_is_never_longer_than_a_handles_own() -> None:
    """AD A.10: the LRU's TTL is "always <= the handle TTL", asserted rather than intended.

    Held from both sides: `MIN_HANDLE_TTL_SECONDS` is the floor `HandlePayload` refuses a
    smaller ttl against, so no handle - not even one minted with an explicit ttl - can outlive
    the cache that serves it.
    """
    assert CACHE_TTL_SECONDS <= MIN_HANDLE_TTL_SECONDS <= HANDLE_TTL_SECONDS
    with pytest.raises(ValueError):
        mint(
            HandleKey(material=b"k" * 32, epoch=0),
            account_hash=ACCOUNT,
            history_id_at_fetch={"t-alpha": "100"},
            mailbox_history_id="100",
            fetched_at=NOW.isoformat(),
            mapping_digest="0" * 32,
            page_sizes={"t-alpha": 1},
            ttl_seconds=MIN_HANDLE_TTL_SECONDS - 1,
        )


# --- the digest ---------------------------------------------------------------------------


def test_the_digest_is_a_function_of_the_thread_and_not_of_the_order_it_is_given_in(
    key: HandleKey,
) -> None:
    """Two redemptions that fetched the same threads in a different order saw one mailbox."""
    box = mailbox()
    minted = mint_over(box, key)
    source = next(s for s in minted.envelope.sources if s.thread_id == "t-alpha")
    assert source.map_id is not None
    payload = verify(source.map_id, key=key, account_hash=ACCOUNT, now=NOW)

    client = make_client(box)
    ledger = DispositionLedger()
    recorded = client.get_thread(ledger, thread_id="t-alpha", rung=REDEMPTION_RUNG)
    positions = {
        message.id: ledger.origins[message.id].position for message in recorded.thread.messages
    }
    rebuilt = build_thread_map(
        thread_id="t-alpha",
        messages=recorded.thread.messages,
        positions={k: v for k, v in positions.items() if v is not None},
        tied_on_internal_date=recorded.tied_on_internal_date,
    )
    assert mapping_digest([rebuilt]) == payload.mapping_digest
    # And the same maps in either order digest identically.
    assert mapping_digest([rebuilt, rebuilt]) == mapping_digest([rebuilt, rebuilt])


def test_the_digest_does_not_cover_the_participant_block(key: HandleKey) -> None:
    """The R-RETR-051 decision, executed.

    The participant index is not a function of the thread: the mention half depends on how
    much text each row contributed, and that is a function of disclosure depth. A digest
    covering it would report `handle_stale` for a thread nothing changed in, whenever the
    same handle were redeemed at two depths. The map is thread-only and is what is digested.
    """
    box = mailbox()
    client = make_client(box)
    ledger = DispositionLedger()
    recorded = client.get_thread(ledger, thread_id="t-alpha", rung=REDEMPTION_RUNG)
    positions = {
        message.id: at
        for message in recorded.thread.messages
        if (at := ledger.origins[message.id].position) is not None
    }
    without_text = build_thread_map(
        thread_id="t-alpha", messages=recorded.thread.messages, positions=positions
    )
    with_text = build_thread_map(
        thread_id="t-alpha",
        messages=recorded.thread.messages,
        positions=positions,
        observed_text={
            "a1": ObservedText(text="an address nobody else saw: dee@team.example"),
        },
    )
    assert without_text.participants.by_address != with_text.participants.by_address
    assert mapping_digest([without_text]) == mapping_digest([with_text])


def test_the_digest_changes_when_the_map_does(key: HandleKey) -> None:
    """The complement, so the exclusion above is not the digest ignoring everything."""
    box = mailbox()
    client = make_client(box)
    ledger = DispositionLedger()
    recorded = client.get_thread(ledger, thread_id="t-alpha", rung=REDEMPTION_RUNG)
    positions = {
        message.id: at
        for message in recorded.thread.messages
        if (at := ledger.origins[message.id].position) is not None
    }
    whole = build_thread_map(
        thread_id="t-alpha", messages=recorded.thread.messages, positions=positions
    )
    shorter = build_thread_map(
        thread_id="t-alpha",
        messages=recorded.thread.messages[:1],
        positions={recorded.thread.messages[0].id: 0},
    )
    assert mapping_digest([whole]) != mapping_digest([shorter])


# --- the handle on the wire ---------------------------------------------------------------


def test_a_source_carries_a_handle_that_redeems_back_to_the_same_thread(key: HandleKey) -> None:
    """`Source.map_id` is populated, and what it names is what comes back.

    STR-05 requires each source to carry a map affordance, and until this round `map_id` was
    `None` on every source the product could build.
    """
    box = mailbox()
    minted = mint_over(box, key)
    source = next(s for s in minted.envelope.sources if s.thread_id == "t-alpha")
    assert source.map_id is not None
    assert source.included == source.stated_total

    result = redeem_against(box, source.map_id, key, cache=ThreadMapCache())
    assert result.outcome.outcome is None
    assert [thread.thread_map.thread_id for thread in result.outcome.served] == ["t-alpha"]
    assert result.outcome.served[0].thread_map.order == ("a1", "a2")


def test_a_response_built_without_a_key_carries_no_handle_rather_than_a_placeholder() -> None:
    """The honest value for a server that cannot mint is no claim at all."""
    box = mailbox()
    client = make_client(box)
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run(MARKER, now=NOW, zone=UTC_ZONE)
    envelope = assemble(run, client=client, ledger=ledger)
    assert [source.map_id for source in envelope.sources] == [None] * len(envelope.sources)


def test_the_tool_error_classes_raise_and_the_in_band_one_does_not(key: HandleKey) -> None:
    """D.11's partition, read out of `ERROR_SURFACE` rather than written into the wrapper."""
    box = mailbox()
    handle = mint_over(box, key).map_id()
    client = make_client(box)
    with pytest.raises(HandleRefused) as refusal:
        redeem_or_raise(
            handle,
            key=key,
            account_hash="sha256:someone-else",
            client=client,
            ledger=DispositionLedger(),
            cache=ThreadMapCache(),
            now=NOW,
        )
    assert refusal.value.code is ErrorCode.HANDLE_INVALID
    assert ERROR_SURFACE[refusal.value.code] is Surface.TOOL_ERROR

    box.history_is_expired = True
    served = redeem_or_raise(
        handle,
        key=key,
        account_hash=ACCOUNT,
        client=make_client(box),
        ledger=DispositionLedger(),
        cache=ThreadMapCache(),
        now=NOW,
    )
    assert served.outcome is ErrorCode.HANDLE_STALE_UNVERIFIABLE
    assert ERROR_SURFACE[served.outcome] is Surface.IN_BAND
    assert served.content_was_served


# --- the key is a secret -------------------------------------------------------------------


def test_the_handle_key_is_covered_by_the_reflection_canary_the_moment_it_exists() -> None:
    """R-SEC-043's canary discovers the field; nothing here had to be added to it.

    The canary imports both source trees, finds every model declaring a secret wrapper at any
    generic depth, and generates its corruption shapes from each model's own `model_fields`.
    `map_key_hex` is a `SecretStr | None` on a model already in that set, so it arrived with
    four new corruption shapes across six entry points and no edit to the canary. This test
    asserts that rather than assuming it.
    """
    assert "map_key_hex" in secret_fields(StoredCredentials)
    assert StoredCredentials in models_with_secrets()


def test_the_handle_key_is_never_rendered(tmp_path: Path) -> None:
    """A credential in a traceback is a credential leaked - the `StaticToken` rule, reapplied.

    The default dataclass `__repr__` prints every field, which for this one is the key.
    """
    key = ensure_handle_key(store_in(tmp_path))
    assert key.material.hex() not in repr(key)
    assert "redacted" in repr(key)
    stored = TokenStore(path=(tmp_path / "state" / "credentials.json")).load()
    assert stored.map_key_hex is not None
    assert stored.map_key_hex.get_secret_value() not in repr(stored)
    assert stored.map_key_hex.get_secret_value() not in str(stored)


def test_the_signing_key_never_reaches_a_handle_or_a_response(key: HandleKey) -> None:
    """A `map_id` is a signature over a payload, not a copy of what signed it."""
    box = mailbox()
    minted = mint_over(box, key)
    serialised = minted.envelope.model_dump_json()
    assert key.material.hex() not in serialised
    assert base64.urlsafe_b64encode(key.material).decode("ascii").rstrip("=") not in serialised


def test_the_key_written_to_the_store_is_the_key_read_back(tmp_path: Path) -> None:
    """`model_dump` renders a `SecretStr` as asterisks; the store unwraps every one of them.

    A field added later and not unwrapped would be persisted as `**********` and read back as
    a key that verifies nothing - which would look exactly like `handle_invalid` on every
    outstanding handle after a restart. The unwrapping is a sweep over the model's own secret
    fields rather than a second named line, and this is that asserted end to end.
    """
    store = store_in(tmp_path)
    first = ensure_handle_key(store)
    raw = json.loads((tmp_path / "state" / "credentials.json").read_text())
    assert raw["map_key_hex"] == first.material.hex()
    assert "*" not in raw["map_key_hex"]
    assert ensure_handle_key(TokenStore(path=store.path)).material == first.material


# --- what a handle does not claim -----------------------------------------------------------


def test_verifying_a_handle_establishes_nothing_about_the_mailbox(key: HandleKey) -> None:
    """Step 1 reads a string and a key on disk. It is not a liveness check and does not say so.

    Executed here because the docstring on `verify` makes exactly this claim, and a handle
    that verified its own cached copy - or that treated a good signature as evidence about
    Gmail - is the tautology ADV-002 filed.
    """
    box = mailbox()
    handle = mint_over(box, key).map_id()
    box.add_message(
        Msg(
            id="a3",
            thread_id="t-alpha",
            sender="Ana Ito <ana@team.example>",
            subject="Re: Rack order",
            body="a change the signature knows nothing about",
            internal_date_ms=epoch_ms(2026, 5, 4),
            in_reply_to=msgid("a2"),
        )
    )
    box.calls.clear()
    payload = verify(handle, key=key, account_hash=ACCOUNT, now=NOW)
    assert isinstance(payload, HandlePayload)
    assert box.calls == {}, "step 1 made a network call"
    # The mailbox has moved and the signature still verifies, which is the point.
    assert redeem_against(box, handle, key, cache=ThreadMapCache()).outcome.outcome is (
        ErrorCode.HANDLE_STALE
    )


def test_a_handles_watermark_is_the_mailbox_watermark_and_not_the_named_threads_own(
    key: HandleKey,
) -> None:
    """Amendment A10: the walk starts at the mailbox's watermark, not the thread's.

    A thread's own `historyId` is the id of the last change that touched *that thread*, so a
    handle over a quiet thread walked from arbitrarily far back - R-RETR-060's unbounded
    window. The mailbox watermark is at most one handle ttl old at redemption, which is what
    makes the walk terminate for a reason rather than by luck.

    Both halves are still asserted: the walk start is the mailbox's, and the per-thread floor
    is still the thread's own, which is what stops a freshly minted handle refusing itself.
    """
    box = mailbox()
    # Move the mailbox well past the named thread's own watermark, without touching it.
    for index in (2, 3, 4):
        box.add_message(
            Msg(
                id=f"b{index}",
                thread_id="t-beta",
                sender="Cai Ode <cai@team.example>",
                subject="Re: Unrelated matter",
                body="a change to a thread this handle does not name",
                internal_date_ms=epoch_ms(2026, 5, 4 + index),
                in_reply_to=msgid("b1"),
            )
        )
    watermark_before_the_mint = str(box.history_id)
    alphas_own = box.history_id_of("t-alpha")
    assert int(watermark_before_the_mint) > int(alphas_own), (
        "the fixture must put the mailbox ahead of the named thread, or this test asserts "
        "nothing: the two values would be equal and either derivation would pass"
    )

    payload = verify(mint_over(box, key).map_id(), key=key, account_hash=ACCOUNT, now=NOW)
    assert payload.history_id == watermark_before_the_mint
    assert payload.history_id != alphas_own
    assert payload.history_id_at_fetch == {"t-alpha": alphas_own}

    # And the changes already inside that window - t-beta's three - do not make this handle
    # stale, because the floor is per thread and t-beta is not one of the threads it names.
    client = make_client(box)
    probe = client.liveness_of_threads(
        since=payload.history_id_at_fetch, start_history_id=payload.history_id
    )
    assert probe.touched == {}
    assert probe.conclusive


def test_a_quiet_thread_redeems_clean_at_the_shipped_page_budget(key: HandleKey) -> None:
    """R-RETR-060's own reproduction, at every shipped default. It used to be unverifiable.

    150 changes to another thread **before** the handle is minted, Gmail's own 100-record
    page default, one page per redemption, and the named thread untouched throughout. Under
    the thread's-own watermark the walk started 150 records back and could not finish, so
    every redemption answered `handle_stale_unverifiable` with the LRU bypassed at two API
    calls - permanently, for any thread that is not freshly touched. Under A10 the walk
    starts after them and there is nothing to page through.

    "Before the mint" is what makes this test discriminate, and it is worth saying because
    the obvious arrangement does not: on a mailbox that has never moved, a single-thread
    handle's `min(thread_history_ids)` and the mailbox watermark are the *same number*, so
    churn added afterwards costs both derivations the same walk. The difference between them
    is precisely the history the mailbox accumulated before the handle existed.

    The second redemption is the half that matters for WS-10's budget: the class that used to
    be returned bypasses the cache, so the cost this round registers depends on this test's
    second assertion and not only on its first.
    """
    box = mailbox(history_page_size=DEFAULT_PAGE_SIZE)
    for index in range(150):
        box.add_message(
            Msg(
                id=f"c{index}",
                thread_id="t-beta",
                sender="Cai Ode <cai@team.example>",
                subject="Re: Unrelated matter",
                body="one of a hundred and fifty unrelated changes",
                internal_date_ms=epoch_ms(2026, 5, 5) + index,
                in_reply_to=msgid("b1"),
            )
        )
    handle = mint_over(box, key).map_id()
    payload = verify(handle, key=key, account_hash=ACCOUNT, now=NOW)
    assert int(payload.history_id) - int(payload.thread_history_ids[0]) == 150, (
        "the fixture must leave the named thread 150 records behind the mailbox, or the two "
        "derivations agree and this test discriminates nothing"
    )

    cache = ThreadMapCache()
    cold = redeem_against(box, handle, key, cache=cache, max_liveness_pages=MAX_LIVENESS_PAGES)
    assert cold.outcome.outcome is None
    assert cold.outcome.trace.liveness is Liveness.VERIFIED_UNCHANGED
    assert cold.outcome.trace.liveness_pages == 1
    assert cold.api_calls == 2

    warm = redeem_against(box, handle, key, cache=cache, max_liveness_pages=MAX_LIVENESS_PAGES)
    assert warm.outcome.outcome is None
    assert warm.outcome.trace.threads_from_cache == ("t-alpha",)
    assert warm.api_calls == 1


def test_the_mailbox_watermark_is_observed_before_the_first_thread_is_fetched() -> None:
    """The ordering A10's soundness rests on, read off the transport's own call log.

    A watermark is safe exactly when it was observed no later than the reads it covers. That
    is not a property of a number, so no validator on `HandlePayload` can check it and the
    docstrings do not claim one does. It is a property of *when the call was made*, and the
    only place it is observable is here.
    """
    box = mailbox()
    client = make_client(box)
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run(MARKER, now=NOW, zone=UTC_ZONE)
    key = HandleKey(material=b"k" * 32, epoch=0)
    assemble(run, client=client, ledger=ledger, minter=HandleMinter(key=key, account_hash=ACCOUNT))

    assert "profile" in box.call_log
    assert box.call_log.index("profile") < box.call_log.index("threads.get")


def test_a_response_that_cannot_mint_handles_does_not_pay_for_the_watermark() -> None:
    """`_mailbox_watermark`'s cost claim, executed: one `getProfile`, and only with a minter.

    The watermark exists so a handle's liveness walk is bounded. A response with no handle
    key mints no handle, so the call would buy nothing - and a quota unit spent for nothing
    is the sort of cost that gets registered against a budget and never noticed again.
    """
    without = mailbox()
    client = make_client(without)
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run(MARKER, now=NOW, zone=UTC_ZONE)
    assemble(run, client=client, ledger=ledger)
    assert "profile" not in without.call_log

    with_key = mailbox()
    keyed = make_client(with_key)
    keyed_ledger = DispositionLedger()
    keyed_run = LadderRunner(keyed, keyed_ledger).run(MARKER, now=NOW, zone=UTC_ZONE)
    assemble(
        keyed_run,
        client=keyed,
        ledger=keyed_ledger,
        minter=HandleMinter(key=HandleKey(material=b"k" * 32, epoch=0), account_hash=ACCOUNT),
    )
    assert with_key.call_log.count("profile") == 1, "once per response, not once per source"


def test_a_budget_that_cannot_afford_the_watermark_mints_no_handle() -> None:
    """A handle whose walk cannot be bounded is worse than no handle (amendment A10, WS-10).

    The mailbox watermark is a Gmail call and is charged like every other one. When the
    budget cannot afford it, the honest answer is the one `_map_id_for` already gave for a
    thread with no `historyId`: no `map_id`. The alternative - spend the query's last unit on
    a watermark, or fall back to the per-thread minimum - either buys a field the response
    cannot honestly fill or restores exactly the unbounded walk A10 removed.
    """
    box = mailbox()
    client = make_client(box)
    ledger = DispositionLedger()
    accountant = BudgetAccountant(
        client.meter, apply_floor(BudgetRequest(max_api_calls=0)), now_ms=lambda: 0.0
    )
    run = LadderRunner(client, ledger, accountant=accountant).run(MARKER, now=NOW, zone=UTC_ZONE)
    envelope = assemble(
        run,
        client=client,
        ledger=ledger,
        accountant=accountant,
        minter=HandleMinter(key=HandleKey(material=b"k" * 32, epoch=0), account_hash=ACCOUNT),
    )
    assert "profile" not in box.call_log
    assert all(source.map_id is None for source in envelope.sources)


def test_a_watermark_taken_after_the_fetch_can_hide_a_change_the_handle_should_see() -> None:
    """Why the ordering is the rule, and why `max(thread_history_ids)` is not the check.

    R-RETR proposed replacing the old `history_id == min(...)` validator with
    `history_id >= max(thread_history_ids)`. This executes what that would require. A
    watermark at or above the newest named thread's own is a watermark taken after that
    thread's read, and a change to a *different* named thread in between then sits below the
    walk's start: invisible to the probe, and absent from the map the handle carries.

    The probe is driven directly rather than through a minted handle, because the payload no
    longer permits the unsound value - which is the point: the arithmetic check would have
    made it the only permitted one.
    """
    box = mailbox()
    before_any_read = str(box.history_id)
    client = make_client(box)
    ledger = DispositionLedger()
    alpha = client.get_thread(ledger, thread_id="t-alpha", rung=REDEMPTION_RUNG)
    assert alpha.thread.history_id is not None
    # t-alpha moves after its own read...
    box.add_message(
        Msg(
            id="a9",
            thread_id="t-alpha",
            sender="Ana Ito <ana@team.example>",
            subject="Re: Rack order",
            body="a change to a named thread, after that thread was read",
            internal_date_ms=epoch_ms(2026, 5, 7),
            in_reply_to=msgid("a2"),
        )
    )
    # ...and t-beta is read afterwards, so max(thread ids) is now above that change.
    box.add_message(
        Msg(
            id="b9",
            thread_id="t-beta",
            sender="Cai Ode <cai@team.example>",
            subject="Re: Unrelated matter",
            body="a change elsewhere, later still",
            internal_date_ms=epoch_ms(2026, 5, 8),
            in_reply_to=msgid("b1"),
        )
    )
    beta = client.get_thread(ledger, thread_id="t-beta", rung=REDEMPTION_RUNG)
    assert beta.thread.history_id is not None
    per_thread = {"t-alpha": alpha.thread.history_id, "t-beta": beta.thread.history_id}
    newest = str(max(int(value) for value in per_thread.values()))

    hidden = client.liveness_of_threads(since=per_thread, start_history_id=newest)
    assert hidden.touched == {}, "the change to t-alpha fell under a post-fetch watermark"
    assert hidden.conclusive, "and the probe would have called that clean"

    # The watermark A10 requires - observed before the first read - sees it.
    sound = client.liveness_of_threads(since=per_thread, start_history_id=before_any_read)
    assert set(sound.touched) == {"t-alpha"}


def test_a_clean_redemption_is_never_issued_by_an_incomplete_walk(key: HandleKey) -> None:
    """`redeem`'s docstring says the walk ran "to the end of Gmail's history". Executed.

    An incomplete walk that saw nothing cannot produce `outcome is None`, whatever the
    digest recompute would have said - and the digest here would have agreed, because
    nothing about the named thread changed.
    """
    box = mailbox(history_page_size=1)
    handle = mint_over(box, key).map_id()
    for index in (2, 3):
        box.add_message(
            Msg(
                id=f"b{index}",
                thread_id="t-beta",
                sender="Cai Ode <cai@team.example>",
                subject="Re: Unrelated matter",
                body="a change elsewhere, on a page the walk will not reach",
                internal_date_ms=epoch_ms(2026, 5, 4 + index),
                in_reply_to=msgid("b1"),
            )
        )
    result = redeem_against(box, handle, key, cache=ThreadMapCache(), max_liveness_pages=1)
    assert result.outcome.outcome is ErrorCode.HANDLE_STALE_UNVERIFIABLE
    assert result.outcome.trace.digest_check is DigestCheck.RECOMPUTED_FROM_FETCH


# --- the vocabularies this round adds, swept as equality ----------------------------------


def test_every_value_of_every_redemption_vocabulary_is_one_the_product_can_produce(
    key: HandleKey, tmp_path: Path
) -> None:
    """The `Linkage` sweep's question, asked of the three enums WS-06 adds.

    A closed vocabulary wider than the code is a claim wider than the code: a caller reading
    `DigestCheck` is entitled to assume every member is a state this server can reach. The
    assertions are **equality**, so a member added later with no producer fails here rather
    than sitting on the wire as a value nothing means.

    `DigestCheck.MISMATCH` is the one that needs its own construction: it is step 4's
    defence-in-depth branch, reached only when the liveness probe found nothing and the maps
    nevertheless digest to something else - which is a cold-fetch bug, so the way to reach it
    is a handle minted over a digest the threads do not make.
    """
    shapes = redemption_shapes(key, tmp_path)
    steps = {step for result in shapes.values() for step in result.outcome.trace.steps}
    liveness = {result.outcome.trace.liveness for result in shapes.values()}
    digest = {result.outcome.trace.digest_check for result in shapes.values()}

    box = mailbox()
    client = make_client(box)
    ledger = DispositionLedger()
    recorded = client.get_thread(ledger, thread_id="t-alpha", rung=REDEMPTION_RUNG)
    assert recorded.thread.history_id is not None
    wrong = mint(
        key,
        account_hash=ACCOUNT,
        history_id_at_fetch={"t-alpha": recorded.thread.history_id},
        mailbox_history_id=recorded.thread.history_id,
        fetched_at=recorded.fetched_at,
        mapping_digest="0" * 32,
        page_sizes={"t-alpha": 1},
    )
    mismatched = redeem_against(box, wrong, key, cache=ThreadMapCache()).outcome
    assert mismatched.outcome is ErrorCode.HANDLE_STALE
    assert mismatched.trace.liveness is Liveness.VERIFIED_UNCHANGED
    assert "defence-in-depth" in mismatched.detail
    digest.add(mismatched.trace.digest_check)
    steps.update(mismatched.trace.steps)
    liveness.add(mismatched.trace.liveness)

    # The two clean shapes, cold and warm. `CACHE_TAUTOLOGY` and `VERIFIED_UNCHANGED` belong
    # to the answers that *serve* something, and none of the seven refusal shapes reaches
    # them - which is the sweep doing its job rather than a gap in it.
    clean_box = mailbox()
    clean_handle = mint_over(clean_box, key).map_id()
    clean_cache = ThreadMapCache()
    for _pass in range(2):
        served = redeem_against(clean_box, clean_handle, key, cache=clean_cache).outcome
        assert served.outcome is None
        digest.add(served.trace.digest_check)
        liveness.add(served.trace.liveness)
        steps.update(served.trace.steps)

    assert steps == set(Step), sorted(step.value for step in set(Step) - steps)
    assert liveness == set(Liveness), sorted(v.value for v in set(Liveness) - liveness)
    assert digest == set(DigestCheck), sorted(v.value for v in set(DigestCheck) - digest)


# --- what the handle carries, and what it does not -----------------------------------------


def test_the_digest_carries_no_identifier_it_was_computed_over(key: HandleKey) -> None:
    """A `map_id` is a string a caller holds, so the digest must not be a channel."""
    box = mailbox()
    handle = mint_over(box, key).map_id()
    digest = str(_payload_of(handle)["mapping_digest"])
    assert len(digest) == 32 and all(c in "0123456789abcdef" for c in digest)
    for identifier in ("t-alpha", "a1", "a2", "ana@team.example", MARKER):
        assert identifier not in digest


def test_the_signature_covers_the_bytes_as_received_and_not_a_re_encoding(
    key: HandleKey,
) -> None:
    """A second canonicalisation is a second opinion about what was signed.

    Verifying a re-encoding of the *parsed* payload would accept two byte sequences under one
    signature: whitespace, key order and unicode escaping are all free in JSON, so a handle
    could be rewritten into a different document that still verified. The HMAC is taken over
    the encoded segment exactly as it arrived.
    """
    box = mailbox()
    handle = mint_over(box, key).map_id()
    encoded, _dot, signature = handle.partition(".")
    document = _payload_of(handle)
    # The same fields, re-serialised with the keys in a different order and a space after
    # each separator: a different byte sequence carrying the identical object.
    rewritten = json.dumps(dict(reversed(list(document.items()))), separators=(", ", ": "))
    re_encoded = base64.urlsafe_b64encode(rewritten.encode("utf-8")).decode("ascii").rstrip("=")
    assert re_encoded != encoded
    assert (
        redeem_against(
            box, f"{re_encoded}.{signature}", key, cache=ThreadMapCache()
        ).outcome.outcome
        is ErrorCode.HANDLE_INVALID
    )


def test_the_liveness_probe_records_nothing_into_the_disposition_ledger(key: HandleKey) -> None:
    """A liveness probe is not a retrieval, so no id it observed owes a disposition.

    The seam's rule is that a listing layer may not hand back ids it did not record. This
    method keeps it by having no id to hand back: what comes out is a per-thread tally over
    thread ids the caller already named in its own handle. `history_additions` remains the
    recorded path, for the LR rung that really does disclose what it finds.
    """
    box = mailbox()
    handle = mint_over(box, key).map_id()
    box.add_message(
        Msg(
            id="a3",
            thread_id="t-alpha",
            sender="Ana Ito <ana@team.example>",
            subject="Re: Rack order",
            body="an arrival the probe will see and must not record",
            internal_date_ms=epoch_ms(2026, 5, 4),
            in_reply_to=msgid("a2"),
        )
    )
    client = make_client(box)
    ledger = DispositionLedger()
    payload = verify(handle, key=key, account_hash=ACCOUNT, now=at_age(handle, 1))
    probe = client.liveness_of_threads(
        since=payload.history_id_at_fetch, start_history_id=payload.history_id
    )
    assert probe.touched == {"t-alpha": probe.touched["t-alpha"]}
    assert probe.touched["t-alpha"].messages_added == 1
    assert ledger.hit_ids == frozenset()
    # And what the probe returns is counts: no message id is reachable from it.
    assert set(probe.touched) <= set(payload.thread_ids)


def test_a_thread_that_comes_back_unmappable_is_refused_rather_than_half_served(
    key: HandleKey,
) -> None:
    """PF-2's branch where a thread has no chronological order, met at redemption.

    A handle names a map. If the live fetch comes back in a shape no map can describe - the
    observation stated no position for every row - then the map this handle names cannot be
    reproduced, and serving the rows anyway would be serving something other than what the
    handle named. `handle_stale` with the fetch step recorded and the digest not reached.
    """
    box = mailbox()
    handle = mint_over(box, key).map_id()
    box.metadata_returns_internal_date = False
    result = redeem_against(box, handle, key, cache=ThreadMapCache())
    assert result.outcome.outcome is ErrorCode.HANDLE_STALE
    assert result.outcome.trace.digest_check is DigestCheck.NOT_REACHED
    assert Step.FETCH in result.outcome.trace.steps
    assert result.outcome.served == ()
