"""Redeeming a `map_id`, in AD A.10's order — and the order is the design (ADV-002).

    verify  ->  independent `history.list` liveness probe  ->  fetch  ->  digest recompute

**Step 2 is the verification. Steps 1 and 4 are not, and this module will not let either
pretend to be.**

  * Step 1 establishes that *this server* minted this handle, for *this mailbox*, recently
    enough to be worth re-verifying. It reads a string the caller sent and a key on disk. It
    says nothing about the mailbox, and it cannot: no network call has been made.
  * Step 2 asks Gmail whether anything has touched the named threads since the handle's
    watermark - the **mailbox** watermark observed before this response's first fetch, so
    the window it walks is bounded by the handle's own ttl rather than by how long ago the
    named thread last moved (amendment A10). It reads a **different resource** from the one
    the cache holds, so a cache hit cannot make it pass. That is the whole of ADV-002: the
    previous design recomputed
    `mapping_digest` from the very cached map that had produced it - `digest(x) == digest(x)`,
    true by construction - so `handle_stale` could never fire on a cache hit and MCP-06's
    mutate-then-redeem test could not fail.
  * Step 3 fetches. The LRU may serve it **only** when step 2 came back clean, and a
    `handle_stale_unverifiable` bypasses the cache entirely: a probe that failed to look is
    not a reason to serve what it was going to check. **A probe that *did* look and saw a
    change never reaches step 3 at all**, however many pages it left unread - amendment
    A10's second rule, and the difference between the two `handle_stale*` classes.
  * Step 4 recomputes the digest, as defence-in-depth against a cold-fetch bug. **On any
    cache-served thread the comparison is tautological** and the trace says
    `digest_check: cache_tautology` rather than claiming a check that did not happen. The
    label is set from where the content came from, not from a flag a caller passes.

**Seven shapes, one object.** Five error classes and two cache states, and every one of them
comes back as a `Redemption`: `outcome` is `None` or one of AD D.11's five handle codes,
`trace` says which step each field came from, and `served` is empty unless content was
actually obtained. There is no path through this module that returns content without a trace
saying how it was verified, and no path that fills a field a step which did not run would
have produced. `redeem_or_raise` is the thin wrapper that turns the four `Surface.TOOL_ERROR`
classes into an exception, and it reads the partition out of `ERROR_SURFACE` rather than
listing them - so a class that moves surface moves here with it.

**`fetched_at` is never restamped.** A cache-served thread carries the stamp of the read that
produced it and, beside it, `verified_at` - the instant of *this* call's liveness probe. Two
fields, both true: this content was read at T0; it was verified unchanged at T1. Restamping
would assert a freshness the response does not have, and would make a handle that cannot
expire, since expiry is measured from `fetched_at`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from mailweave.constants import MAX_LIVENESS_PAGES
from mailweave.envelope.disposition import DispositionLedger
from mailweave.envelope.reasons import RungId
from mailweave.envelope.wire import Affordance
from mailweave.errors import ERROR_SURFACE, ErrorCode, HandleRefused, Surface
from mailweave.gmail.client import GmailClient, LivenessProbe, RecordedThread
from mailweave.gmail.models import Message
from mailweave.handles.cache import CachedThreadMap, ThreadMapCache
from mailweave.handles.digest import mapping_digest
from mailweave.handles.keys import HandleKey
from mailweave.handles.mint import HandlePayload, re_derivation_of, verify
from mailweave.structure.participants import ObservedText
from mailweave.structure.threadmap import ThreadMap, snippet_observed_text
from mailweave.structure.threadmap import build as build_thread_map

#: The rung a redemption's `threads.get` is charged to. A handle redemption is not a ladder
#: run; the fetch is the same structural lookup L4 makes, by identifier rather than by query.
REDEMPTION_RUNG: Final[RungId] = RungId.L4


class Step(StrEnum):
    """AD A.10's four steps, named so a trace can say which one an outcome came out of."""

    VERIFY = "verify"
    LIVENESS = "liveness_probe"
    FETCH = "fetch"
    DIGEST = "digest_recompute"


class Liveness(StrEnum):
    """What step 2 established. Four values, and only one of them is a guarantee."""

    #: The probe ran, walked to the end of its history, and nothing had touched the named
    #: threads since their own `historyId`s. This is the only value that licenses "unchanged".
    VERIFIED_UNCHANGED = "verified_unchanged"
    #: Something touched a named thread. `handle_stale`.
    CHANGED = "changed"
    #: Gmail 404'd the watermark, or the walk stopped with pages outstanding. The probe did
    #: not find "no change": it failed to look. `handle_stale_unverifiable`.
    UNVERIFIABLE = "unverifiable"
    #: Step 1 refused, so step 2 never ran. Not a finding about the mailbox at all.
    NOT_REACHED = "not_reached"


class DigestCheck(StrEnum):
    """What step 4's comparison was worth."""

    #: Every served thread was fetched live and the recomputed digest matched.
    RECOMPUTED_FROM_FETCH = "recomputed_from_fetch"
    #: At least one served thread came from the LRU, so the recompute compares a digest with
    #: the digest of the map that produced it. AD A.10 requires this label; it is set from
    #: where the content came from and is never a caller's word.
    CACHE_TAUTOLOGY = "cache_tautology"
    #: The recomputed digest differs from the handle's. `handle_stale`.
    MISMATCH = "mismatch"
    #: An earlier step refused, so nothing was recomputed.
    NOT_REACHED = "not_reached"


@dataclass(frozen=True)
class ServedThread:
    """One thread a redemption produced, and where its content came from."""

    thread_map: ThreadMap
    #: The stamp of the read that produced this content. **Never `now`** for a cached entry.
    fetched_at: str
    #: This call's liveness-probe instant, on a thread served from the LRU. `None` for a
    #: thread fetched live, whose `fetched_at` is already this call's own read.
    verified_at: str | None
    from_cache: bool
    history_id_at_fetch: str
    #: The rows of the `threads.get` this map was built from, or `()` on a thread served
    #: from the LRU (WS-15). The cache stores a map and not the response it came from, so a
    #: warm redemption genuinely holds no `labelIds`, no `snippet` and no MIME tree - and
    #: `()` is the honest representation of that rather than a shape the caller has to
    #: guess at. A disclosure built from a warm redemption therefore reports each row's
    #: mailbox provenance as *unobserved*, which is the true statement, instead of
    #: inheriting the labels of a read that happened up to a minute ago in another call.
    messages: tuple[Message, ...] = ()


@dataclass(frozen=True)
class RedemptionTrace:
    """What each step did, in the order they ran (AD A.11, D.10).

    Every field is set by the step that produced it and left at its "not reached" value
    otherwise, so the trace cannot describe work that did not happen. There is no call
    counter here: `CallMeter` is the one authority on how many calls were made (A.5b), and a
    second tally kept beside it would be a second claim about one fact.
    """

    steps: tuple[Step, ...]
    liveness: Liveness
    digest_check: DigestCheck
    threads_from_cache: tuple[str, ...] = ()
    threads_fetched: tuple[str, ...] = ()
    #: `{thread id: the change the probe saw}` - populated only on `Liveness.CHANGED`.
    changed: Mapping[str, str] = field(default_factory=dict)
    liveness_pages: int = 0
    evicted: int = 0


@dataclass(frozen=True)
class Redemption:
    """One redemption, in whichever of the seven shapes it took.

    `outcome is None` is a clean redemption. Otherwise it is one of the five handle classes,
    and `served` is empty for every one of them **except** `handle_stale_unverifiable`, which
    AD D.11 puts in band precisely because content is still served: the threads were fetched
    live and the response says the staleness could not be verified from history.
    """

    outcome: ErrorCode | None
    detail: str
    trace: RedemptionTrace
    payload: HandlePayload | None = None
    served: tuple[ServedThread, ...] = ()
    #: AD D.11's "the re-derivation call", where one can honestly be minted. `None` for
    #: `handle_invalid` and `handle_key_rotated`, which are decided while the payload is
    #: still unverified - see `mint.re_derivation_of`.
    affordance: Affordance | None = None

    @property
    def surface(self) -> Surface | None:
        """Which side of D.11's partition this outcome sits on. Read, never written here."""
        return None if self.outcome is None else ERROR_SURFACE[self.outcome]

    @property
    def content_was_served(self) -> bool:
        return bool(self.served)


def _refused(
    code: ErrorCode,
    detail: str,
    trace: RedemptionTrace,
    affordance: Affordance | None = None,
) -> Redemption:
    return Redemption(outcome=code, detail=detail, trace=trace, affordance=affordance)


def _observed_text_of(recorded: RecordedThread) -> dict[str, ObservedText]:
    """The text a redemption observed, which is the `snippet` and nothing else.

    A redemption fetches maps, not bodies, so the only text it holds is whatever the
    `threads.get` returned - and that is a truncation by construction, which is carried
    rather than assumed away (R-RETR-052).
    """
    return snippet_observed_text(recorded.thread.messages)


def _map_of(recorded: RecordedThread, ledger: DispositionLedger) -> ThreadMap | None:
    """The map of one fetched thread, or `None` when the observation left it unplaceable.

    Positions come off the sealed observation, exactly as `assemble` takes them: a second
    sort here would be a second derivation of one fact (R-ARCH-031).
    """
    origins = ledger.origins
    positions = {
        message.id: origin.position
        for message in recorded.thread.messages
        if (origin := origins.get(message.id)) is not None and origin.position is not None
    }
    if len(positions) != len(recorded.thread.messages):
        return None
    return build_thread_map(
        thread_id=recorded.thread.id,
        messages=recorded.thread.messages,
        positions=positions,
        observed_text=_observed_text_of(recorded),
        tied_on_internal_date=recorded.tied_on_internal_date,
    )


def _probe(client: GmailClient, payload: HandlePayload, *, max_pages: int) -> LivenessProbe:
    return client.liveness_of_threads(
        since=payload.history_id_at_fetch,
        start_history_id=payload.history_id,
        max_pages=max_pages,
    )


def redeem(
    map_id: str,
    *,
    key: HandleKey,
    account_hash: str,
    client: GmailClient,
    ledger: DispositionLedger,
    cache: ThreadMapCache,
    now: datetime,
    max_liveness_pages: int = MAX_LIVENESS_PAGES,
) -> Redemption:
    """AD A.10's redemption, whole, returning one `Redemption` in every shape.

    **What a clean redemption guarantees, stated exactly.** That this server minted the
    handle for this mailbox; that a `history.list` walk from the **mailbox** watermark this
    handle carries - observed before the response that minted it read any thread (amendment
    A10) - **to the end of Gmail's history** returned no `messageAdded`, `messageDeleted`,
    `labelAdded` or `labelRemoved` record touching a named thread at a `historyId` above that
    thread's own; and that the maps handed back digest to the value the handle carries.

    "To the end" is a real conjunct rather than a flourish: a walk that stopped early is
    `pages_exhausted`, and a `Redemption` whose `outcome` is `None` is one this walk never
    reached, because `not probe.conclusive` sends it to `handle_stale_unverifiable`
    instead. `test_a_clean_redemption_is_never_issued_by_an_incomplete_walk` executes that
    conjunct.

    It does **not** guarantee that Gmail's history is complete, that the `threads.get` array
    was the whole thread (PF-1), or - on a cache-served thread - anything at all from step 4.
    """
    started_at = now.astimezone(UTC)
    verifying = RedemptionTrace(
        steps=(Step.VERIFY,), liveness=Liveness.NOT_REACHED, digest_check=DigestCheck.NOT_REACHED
    )
    try:
        payload = verify(map_id, key=key, account_hash=account_hash, now=started_at)
    except HandleRefused as refusal:
        offered = refusal.affordance
        assert offered is None or isinstance(offered, Affordance)
        return _refused(refusal.code, str(refusal), verifying, offered)

    probe = _probe(client, payload, max_pages=max_liveness_pages)
    probed = (Step.VERIFY, Step.LIVENESS)
    # **Amendment A10, second rule (R-RETR-059).** A walk that *saw* a change reports
    # `handle_stale`, whatever remains unread. The condition here used to also require
    # `not probe.pages_exhausted`, so a probe that read page 1, found a named thread had
    # moved, and stopped with a continuation token outstanding fell through into the
    # `unverifiable` branch below - which throws the observation away, serves the map, and
    # attaches a sentence saying whether these threads changed could not be verified. It
    # had been verified, by this probe, one branch earlier. `pages_exhausted` devalues the
    # *absence* of a record and nothing else, which is why `LivenessProbe` now carries two
    # properties rather than one.
    if probe.saw_a_change:
        evicted = sum(cache.evict_thread(thread_id) for thread_id in payload.thread_ids)
        changed = {
            thread_id: change.rendered() for thread_id, change in sorted(probe.touched.items())
        }
        named = "; ".join(f"{thread_id}: {what}" for thread_id, what in changed.items())
        # The counts are what this walk read. When the walk stopped with pages outstanding
        # the *refusal* is unaffected - a change that was seen was seen - but the itemised
        # list may be short, and saying so is the difference between "at least this moved"
        # and a completeness claim nobody made.
        partial = (
            " The history walk stopped with pages outstanding, so this is at least what "
            "moved rather than all of it; the refusal does not depend on the remainder."
            if probe.pages_exhausted
            else ""
        )
        return _refused(
            ErrorCode.HANDLE_STALE,
            f"the mailbox has moved under this map_id since it was minted - {named}.{partial} "
            "The map it describes is no longer the thread's, so it is refused rather than "
            "served with a caveat. Re-derive the map",
            RedemptionTrace(
                steps=probed,
                liveness=Liveness.CHANGED,
                digest_check=DigestCheck.NOT_REACHED,
                changed=changed,
                liveness_pages=probe.pages_fetched,
                evicted=evicted,
            ),
            re_derivation_of(payload),
        )

    # Reached only when the walk **observed nothing**, because the branch above has already
    # taken every walk that saw something. That is amendment A10's partition of the two
    # classes: `handle_stale` for a walk that saw a change, `handle_stale_unverifiable` for
    # a walk that saw nothing and could not finish looking.
    unverifiable = not probe.conclusive
    evicted = 0
    if unverifiable:
        # **The LRU is bypassed, whole.** The probe did not establish that nothing changed;
        # it failed to look, and serving a cached map on that basis would be serving content
        # nothing is checking - which is the shape ADV-002 was.
        evicted = sum(cache.evict_thread(thread_id) for thread_id in payload.thread_ids)

    verified_at = started_at.isoformat()
    from_cache: list[str] = []
    fetched: list[str] = []
    served: list[ServedThread] = []
    at_fetch = payload.history_id_at_fetch
    for thread_id in payload.thread_ids:
        history_id = at_fetch[thread_id]
        hit = (
            None
            if unverifiable
            else cache.get(thread_id=thread_id, history_id=history_id, now=started_at)
        )
        if hit is not None:
            from_cache.append(thread_id)
            served.append(
                ServedThread(
                    thread_map=hit.thread_map,
                    # Carried verbatim. This is the read that produced the content, and it
                    # is the moment the handle's own expiry is measured from.
                    fetched_at=hit.fetched_at,
                    verified_at=verified_at,
                    from_cache=True,
                    history_id_at_fetch=hit.history_id,
                )
            )
            continue
        recorded = client.get_thread(ledger, thread_id=thread_id, rung=REDEMPTION_RUNG)
        thread_map = _map_of(recorded, ledger)
        if thread_map is None:
            return _refused(
                ErrorCode.HANDLE_STALE,
                f"thread {thread_id} came back from a live fetch in a shape no map can "
                "describe - the observation stated no chronological position for every row - "
                "so the map this handle names cannot be reproduced. Re-derive the map",
                RedemptionTrace(
                    steps=(*probed, Step.FETCH),
                    liveness=(
                        Liveness.UNVERIFIABLE if unverifiable else Liveness.VERIFIED_UNCHANGED
                    ),
                    digest_check=DigestCheck.NOT_REACHED,
                    threads_from_cache=tuple(from_cache),
                    threads_fetched=tuple(fetched),
                    liveness_pages=probe.pages_fetched,
                    evicted=evicted,
                ),
                re_derivation_of(payload),
            )
        fetched.append(thread_id)
        live_history_id = recorded.thread.history_id or history_id
        cache.put(
            CachedThreadMap(
                thread_map=thread_map,
                fetched_at=recorded.fetched_at,
                history_id=live_history_id,
                stored_at=started_at,
            )
        )
        served.append(
            ServedThread(
                thread_map=thread_map,
                messages=tuple(recorded.thread.messages),
                fetched_at=recorded.fetched_at,
                # A live fetch's `fetched_at` *is* this call's read, so a `verified_at` beside
                # it would be a second stamp for one event. `verified_at` exists for the cache
                # case, where the two really are different moments (AD A.10).
                verified_at=None,
                from_cache=False,
                history_id_at_fetch=live_history_id,
            )
        )

    recomputed = mapping_digest([one.thread_map for one in served])
    # **The label is a fact about where the content came from**, and it is computed here
    # rather than passed in. A warm redemption that reported `recomputed_from_fetch` would be
    # claiming the cold path's guarantee on the warm path, which is the exact defect this
    # round's Part 0 is about, committed inside the round that fixes it.
    check = DigestCheck.CACHE_TAUTOLOGY if from_cache else DigestCheck.RECOMPUTED_FROM_FETCH
    if recomputed != payload.mapping_digest:
        for thread_id in payload.thread_ids:
            evicted += cache.evict_thread(thread_id)
        return _refused(
            ErrorCode.HANDLE_STALE,
            "the threads this map_id names no longer digest to the value it carries, so the "
            "map it describes is not the map they now make. The liveness probe did not see "
            "the change, which makes this the defence-in-depth branch rather than the "
            "verification. Re-derive the map",
            RedemptionTrace(
                steps=(*probed, Step.FETCH, Step.DIGEST),
                liveness=(Liveness.UNVERIFIABLE if unverifiable else Liveness.VERIFIED_UNCHANGED),
                digest_check=DigestCheck.MISMATCH,
                threads_from_cache=tuple(from_cache),
                threads_fetched=tuple(fetched),
                liveness_pages=probe.pages_fetched,
                evicted=evicted,
            ),
            re_derivation_of(payload),
        )
    trace = RedemptionTrace(
        steps=(*probed, Step.FETCH, Step.DIGEST),
        liveness=Liveness.UNVERIFIABLE if unverifiable else Liveness.VERIFIED_UNCHANGED,
        digest_check=check,
        threads_from_cache=tuple(from_cache),
        threads_fetched=tuple(fetched),
        liveness_pages=probe.pages_fetched,
        evicted=evicted,
    )
    if unverifiable:
        why = (
            "Gmail no longer holds history from this handle's watermark"
            if probe.expired
            else "the history walk stopped with pages outstanding"
        )
        return Redemption(
            outcome=ErrorCode.HANDLE_STALE_UNVERIFIABLE,
            detail=(
                f"{why}, so whether these threads changed could not be verified from "
                "history. The maps below were fetched live rather than served from the "
                "cache, and they are what Gmail returns now - not evidence that nothing "
                "changed since this handle was minted"
            ),
            trace=trace,
            payload=payload,
            served=tuple(served),
            affordance=re_derivation_of(payload),
        )
    return Redemption(
        outcome=None,
        detail=(
            "no messageAdded, messageDeleted, labelAdded or labelRemoved record touched "
            "these threads above their own historyId at fetch"
        ),
        trace=trace,
        payload=payload,
        served=tuple(served),
    )


def redeem_or_raise(
    map_id: str,
    *,
    key: HandleKey,
    account_hash: str,
    client: GmailClient,
    ledger: DispositionLedger,
    cache: ThreadMapCache,
    now: datetime,
    max_liveness_pages: int = MAX_LIVENESS_PAGES,
) -> Redemption:
    """`redeem`, with D.11's tool-error classes raised as `HandleRefused`.

    The partition is read out of `ERROR_SURFACE` rather than written here, so a code that
    moves from one surface to the other moves here with it. `handle_stale_unverifiable` is
    in band and comes back on a served response; the other four end the call.
    """
    outcome = redeem(
        map_id,
        key=key,
        account_hash=account_hash,
        client=client,
        ledger=ledger,
        cache=cache,
        now=now,
        max_liveness_pages=max_liveness_pages,
    )
    if outcome.surface is Surface.TOOL_ERROR:
        assert outcome.outcome is not None  # `surface` is None exactly when `outcome` is
        raise HandleRefused(
            code=outcome.outcome, message=outcome.detail, affordance=outcome.affordance
        )
    return outcome
