"""The network-touching half of each probe. Written now; run by the owner, later.

Everything here needs a live mailbox, which is the point of the round-11 split: the probes
are authored, reviewed and unit-tested against synthetic observations now, so the live phase
is execution rather than authoring. Each function returns the probe's *observation* type, and
the pure `analyse` in `probes/` turns that into a verdict - so the judgement is testable
without a socket and the measurement is a thin, readable shell.

Clocks and sleeps are injected for the same reason.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from mailweave.content.decode import decode_base64url, decode_text
from mailweave.content.html_text import strip_invisible_characters
from mailweave.content.mime import select_body, walk
from mailweave.content.payload import MessagePayload, parse_payload
from mailweave.envelope import DispositionLedger, RungId
from mailweave.envelope.vocab import ToolName
from mailweave.envelope.wire import Affordance
from mailweave.gmail import GmailClient, GmailEndpoint, GmailFault, ListingRun, Thread
from mailweave_harness.preflight.probes import (
    freshness,
    headers,
    invisible,
    latency,
    quota,
    threads,
)
from mailweave_harness.preflight.record import digest
from mailweave_harness.preflight.scope import MailboxScope

#: The widening affordance a listing run is required to carry. The probes are not the MCP
#: surface, so this is a placeholder in the same shape the real one will have - a concrete
#: `{tool, args}` pair - rather than a `None` the client would refuse anyway.
WIDEN = Affordance(tool=ToolName.SEARCH, args={"scan": {"max_pages": "next"}})


def walk_mailbox(
    client: GmailClient,
    ledger: DispositionLedger,
    *,
    scope: MailboxScope,
    page_size: int = 100,
    max_pages: int = 5,
) -> ListingRun:
    """The one place a probe asks Gmail to list a mailbox, and the one place a scope is split.

    Both halves of the scope leave from here in the same call, so the `q` spelling and the
    `includeSpamTrash` parameter cannot disagree: there is no caller holding two values to
    pass to two places. `MailboxScope`'s docstring has the reasoning; the sweep in
    `tests/test_standing_cycle_round12.py` is what keeps this the only such call.

    The rung is `L0` and is not a parameter: every listing walk a probe makes is a broad
    first-rung scan, and a parameter no caller ever varies is a branch nothing exercises -
    which is the finding this function exists to answer, so it is not one to reintroduce
    two lines below the fix.
    """
    return client.list_messages(
        ledger,
        rung=RungId.L0,
        query=scope.query,
        widening_affordance=WIDEN,
        page_size=page_size,
        max_pages=max_pages,
        include_spam_trash=scope.include_spam_trash,
    )


@dataclass(frozen=True)
class Sampled:
    """What one listing walk yielded, as counts and a thread map read off the ledger."""

    thread_by_message: dict[str, str]
    pages_fetched: int
    more_pages: bool


def sample_mailbox(
    client: GmailClient,
    ledger: DispositionLedger,
    *,
    scope: MailboxScope = MailboxScope.WITHOUT_SPAM_AND_TRASH,
    max_pages: int = 5,
    page_size: int = 100,
) -> Sampled:
    """Walk listing pages and read the id -> thread map back off the ledger.

    The client hands back no ids, by construction. `ledger.origins` is the readable
    enumeration the architecture provides, and reading it here is the supported path rather
    than a way around the seam.

    There is no `query` parameter. A caller with its own query string is a caller that can
    put the `q` spelling and `includeSpamTrash` out of step, and the round-11 version's
    `query=None` default - meaning "the whole mailbox" - was never passed by anything, so
    the escape hatch had no user and one failure mode.
    """
    run = walk_mailbox(client, ledger, scope=scope, page_size=page_size, max_pages=max_pages)
    mapping = {
        message_id: origin.thread_id
        for message_id, origin in ledger.origins.items()
        if origin.thread_id is not None
    }
    return Sampled(
        thread_by_message=mapping, pages_fetched=run.pages_fetched, more_pages=run.more_pages
    )


# --- PF-3 --------------------------------------------------------------------------------


def measure_quota(
    client: GmailClient,
    *,
    message_id: str,
    thread_id: str,
    start_history_id: str,
    max_calls: int = 4_000,
) -> quota.QuotaObservation:
    """Drive each endpoint to refusal, in the published-cheapest-first order.

    PF-16: this drives to 429 by design and needs an exclusive window on the project. The
    runner refuses to start it without `--exclusive-window`, which is a declaration by the
    person running it and not something this code can verify.

    The listing scope is not a parameter here. PF-3 measures what a call *costs*, and the
    published table prices `messages.list` per call rather than per result, so which mailbox
    the call names cannot change the number - and a parameter whose second value would never
    be passed is the shape part 6 of this round exists to remove.
    """
    observation = quota.QuotaObservation()
    calls: list[tuple[GmailEndpoint, Callable[[], None]]] = [
        (
            GmailEndpoint.HISTORY_LIST,
            lambda: _drop(
                client.history_additions(DispositionLedger(), start_history_id=start_history_id)
            ),
        ),
        (
            GmailEndpoint.MESSAGES_LIST,
            # The same `min_length=1` constraint, the second of the two call sites that
            # violated it. This one is not reached until PF-3 runs, so it would have
            # survived a fix aimed only at the crash the runner shows first - and it goes
            # through `walk_mailbox` for the same reason: a second way to spell a listing
            # call is a second place the two scope settings can drift apart.
            lambda: _drop(
                walk_mailbox(
                    client,
                    DispositionLedger(),
                    scope=MailboxScope.WITHOUT_SPAM_AND_TRASH,
                    page_size=1,
                    max_pages=1,
                )
            ),
        ),
        (GmailEndpoint.MESSAGES_GET, lambda: _drop(client.get_message(message_id))),
        (
            GmailEndpoint.THREADS_GET,
            lambda: _drop(
                client.get_thread(DispositionLedger(), thread_id=thread_id, rung=RungId.L4)
            ),
        ),
    ]
    for endpoint, make_call in calls:
        observation.per_endpoint.append(
            quota.measure_endpoint(endpoint, make_call, max_calls=max_calls)
        )
    return observation


def measure_latency(
    client: GmailClient,
    *,
    message_id: str,
    thread_id: str,
    samples: int = latency.SAMPLES_PER_ENDPOINT,
) -> latency.LatencyObservation:
    """PF-21: time each endpoint a search spends its deadline on, sequentially.

    Sequential on purpose - the server is stdio-serial and spends its deadline one call at a
    time, so a concurrent measurement would be a measurement of something the server never
    does. The listing goes through `walk_mailbox` for the reason `measure_quota`'s does.
    """
    observation = latency.LatencyObservation()
    calls: list[tuple[GmailEndpoint, Callable[[], None]]] = [
        (GmailEndpoint.GET_PROFILE, lambda: _drop(client.get_profile())),
        (
            GmailEndpoint.MESSAGES_LIST,
            lambda: _drop(
                walk_mailbox(
                    client,
                    DispositionLedger(),
                    scope=MailboxScope.WITHOUT_SPAM_AND_TRASH,
                    page_size=1,
                    max_pages=1,
                )
            ),
        ),
        (
            GmailEndpoint.MESSAGES_GET,
            lambda: _drop(client.get_message(message_id, message_format="full")),
        ),
        (
            GmailEndpoint.THREADS_GET,
            lambda: _drop(
                client.get_thread(DispositionLedger(), thread_id=thread_id, rung=RungId.L4)
            ),
        ),
    ]
    for endpoint, make_call in calls:
        observation.per_endpoint.append(latency.time_endpoint(endpoint, make_call, samples=samples))
    return observation


def _drop(_result: object) -> None:
    """Discard a result. The probe measures the *call*, not what it returned."""


# --- PF-2 --------------------------------------------------------------------------------


#: How many candidate threads the selector will fetch before giving up. Each is one
#: `threads.get(format=full)` at 40 u, and the chosen candidate's full arm is *reused* as the
#: probe's own full arm rather than fetched twice. Registered in the SPEC's quota budget
#: before the rerun, per PF-16.
MAX_SELECTION_PROBES: Final[int] = 4


@dataclass(frozen=True)
class ThreadChoice:
    """Which thread PF-2 will measure, how it was chosen, and what that cost.

    `full_arm` travels with the choice because the selector had to fetch it to answer "does
    this thread carry a reply-linking header at all". Refetching it inside the probe would
    double the cost of every selection and, worse, would sample the mailbox twice at two
    instants - so a message delivered between the two calls would appear in one arm only.
    """

    thread_id: str
    full_arm: Thread | None
    selection: str
    candidates_probed: int


def _carries_reply_header(thread: Thread) -> bool:
    wanted = {name.lower() for name in headers.REPLY_LINKING}
    for message in thread.messages:
        if message.payload is None:
            continue
        if {header.name.lower() for header in message.payload.headers} & wanted:
            return True
    return False


def choose_reply_bearing_thread(
    client: GmailClient,
    *,
    thread_by_message: Mapping[str, str],
    max_probes: int = MAX_SELECTION_PROBES,
) -> ThreadChoice | None:
    """Pick a thread that can actually answer PF-2's reply-header question.

    Deterministic, and deliberately so: candidates are ordered by **message count
    descending, then thread id ascending**, and the first one carrying `In-Reply-To` or
    `References` wins. The old selector took `sorted(thread_ids)[0]`, which is the
    lexicographically smallest id in the sample and has nothing to do with whether the
    thread can exhibit the property under test. Run 1 drew a one-message thread that way
    and reported PASS on a question it never asked.

    Message counts come from the listing walk the runner has already done, so the ordering
    costs nothing. Only the reply-header check costs calls, and it is bounded.

    Returns `None` when there are no candidates at all. When candidates exist but none of
    the probed ones carries a reply-linking header, the largest is returned with a selection
    token saying so - the probe then reports the reply question as INCONCLUSIVE, which is
    the true answer, rather than the runner silently picking something else.
    """
    if not thread_by_message:
        return None
    sizes: dict[str, int] = {}
    for thread_id in thread_by_message.values():
        sizes[thread_id] = sizes.get(thread_id, 0) + 1
    candidates = sorted(sizes, key=lambda thread_id: (-sizes[thread_id], thread_id))
    probed = 0
    first_full: Thread | None = None
    for thread_id in candidates[:max_probes]:
        full_arm: Thread = client.get_thread(
            DispositionLedger(), thread_id=thread_id, rung=RungId.L4, message_format="full"
        ).thread
        probed += 1
        if first_full is None:
            first_candidate = thread_id
            first_full = full_arm
        if _carries_reply_header(full_arm):
            return ThreadChoice(
                thread_id=thread_id,
                full_arm=full_arm,
                selection="deterministic-largest-first-reply-bearing",
                candidates_probed=probed,
            )
    if first_full is None:
        return None
    return ThreadChoice(
        thread_id=first_candidate,
        full_arm=first_full,
        selection="deterministic-largest-first-none-reply-bearing",
        candidates_probed=probed,
    )


def measure_metadata_headers(
    client: GmailClient,
    *,
    thread_id: str,
    requested: Sequence[str] | None = None,
    full_arm: Thread | None = None,
    selection: str = "unrecorded",
    candidates_probed: int = 0,
) -> headers.HeaderObservation:
    """Fetch the two arms and reduce them. `full_arm` may be supplied by the selector.

    Reusing the selector's full arm is not only a saving. Two `threads.get` calls are two
    instants, and a message delivered between them lands in one arm and not the other, which
    the comparison would read as a header the metadata arm dropped.
    """
    from mailweave.gmail import THREAD_MAP_HEADERS

    wanted = tuple(requested) if requested is not None else THREAD_MAP_HEADERS
    metadata_arm: Thread = client.get_thread(
        DispositionLedger(),
        thread_id=thread_id,
        rung=RungId.L4,
        message_format="metadata",
        metadata_headers=wanted,
    ).thread
    if full_arm is None:
        full_arm = client.get_thread(
            DispositionLedger(), thread_id=thread_id, rung=RungId.L4, message_format="full"
        ).thread
    observation = headers.observe(
        metadata_arm=metadata_arm, full_arm=full_arm, requested_headers=wanted
    )
    observation.selection = selection
    observation.candidates_probed = candidates_probed
    return observation


# --- PF-1 and the ceiling ------------------------------------------------------------------


def measure_threads(
    client: GmailClient,
    *,
    salt: bytes,
    scope: MailboxScope = MailboxScope.WITHOUT_SPAM_AND_TRASH,
    max_pages: int = 5,
    threads_to_fetch: int = 12,
) -> threads.ThreadObservation:
    """Compare `threads.get`'s row count with the listing arm's, on the longest threads.

    The longest threads are chosen because a truncation is only visible where there is
    something to truncate, and that choice is recorded: this is a targeted sample, not a
    random one, and it bounds what a pass here means.
    """
    ledger = DispositionLedger()
    sampled = sample_mailbox(client, ledger, scope=scope, max_pages=max_pages)
    listing_rows: dict[str, int] = {}
    for thread_id in sampled.thread_by_message.values():
        listing_rows[thread_id] = listing_rows.get(thread_id, 0) + 1
    observation = threads.ThreadObservation(
        scope=scope,
        pages_fetched=sampled.pages_fetched,
        listing_incomplete=sampled.more_pages,
    )
    longest = sorted(listing_rows, key=lambda key: listing_rows[key], reverse=True)
    for thread_id in longest[:threads_to_fetch]:
        try:
            recorded = client.get_thread(DispositionLedger(), thread_id=thread_id, rung=RungId.L4)
        except GmailFault:
            continue
        key = digest(thread_id, salt)
        observation.threads_get_rows[key] = len(recorded.thread.messages)
        observation.listing_rows[key] = listing_rows[thread_id]
    return observation


# --- freshness ------------------------------------------------------------------------------


def measure_freshness(
    client: GmailClient,
    *,
    start_history_id: str,
    salt: bytes,
    window_s: float,
    poll_s: float = 30.0,
    find_by_id: Callable[[str], bool],
    now: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> freshness.FreshnessObservation:
    """Watch `history.list` for arrivals and time how long each takes to become findable.

    `find_by_id` performs the id-exact `rfc822msgid:` search for one message and says whether
    it returned anything. It is a parameter because it needs the message's RFC822 `Message-ID`
    header, which costs a `messages.get`, and because injecting it makes this loop testable
    with no network.
    """
    observation = freshness.FreshnessObservation(window_s=window_s)
    started = now()
    seen_at: dict[str, float] = {}
    watermark = start_history_id
    while now() - started < window_s:
        ledger = DispositionLedger()
        run = client.history_additions(ledger, start_history_id=watermark)
        if run.rebaseline_required:
            break
        watermark = run.latest_history_id or watermark
        for message_id in ledger.hit_ids:
            if message_id not in seen_at:
                seen_at[message_id] = now()
                observation.arrivals_observed += 1
        for message_id, first_seen in list(seen_at.items()):
            key = digest(message_id, salt)
            if key in observation.lag_seconds_by_message:
                continue
            if find_by_id(message_id):
                observation.lag_seconds_by_message[key] = now() - first_seen
        sleep(poll_s)
    observation.never_found = [
        digest(message_id, salt)
        for message_id in seen_at
        if digest(message_id, salt) not in observation.lag_seconds_by_message
    ]
    return observation


# --- the Cf strip ---------------------------------------------------------------------------


def body_before_and_after_stripping(payload: MessagePayload) -> tuple[str, str] | None:
    """Decode one body and strip it, returning both forms. Neither is retained by a caller.

    Composed from the shipped content API rather than reimplemented: `walk` + `select_body`
    choose the part exactly as the pipeline does, so the probe measures the operation the
    product performs and not a second one written to resemble it.
    """
    selection = select_body(walk(payload.payload))
    if selection.chosen is None:
        return None
    encoded = selection.chosen.part.body.data
    if not encoded:
        return None
    decoded = decode_text(decode_base64url(encoded), None)
    return decoded.text, strip_invisible_characters(decoded.text).text


def measure_invisible(
    client: GmailClient, *, message_ids: Sequence[str], salt: bytes
) -> invisible.InvisibleObservation:
    observation = invisible.InvisibleObservation()
    for message_id in message_ids:
        try:
            message = client.get_message(message_id, message_format="full")
        except GmailFault:
            continue
        if message.payload is None:
            continue
        payload = parse_payload(
            {"id": message.id, "threadId": message.thread_id, "payload": message.payload}
        )
        pair = body_before_and_after_stripping(payload)
        if pair is None:
            continue
        observation.bodies_examined += 1
        raw, stripped = pair
        observation.messages.append(
            invisible.observe_message(digest(message_id, salt), raw, stripped)
        )
    return observation
