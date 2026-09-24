"""The listing seam: the HTTP call and the ledger write are one call (R-ORCH-001).

Round 1's ledger was correct about everything except its input. `H` was whatever a caller
chose to pass to `record_list_page`, so the probe that defines this finding - fetch 100
IDs from `messages.list`, record 10 - produced a valid certificate with `H=10`,
`withheld=0` and ninety retrieved messages invisible to every check downstream. The set
difference `withheld := H - disclosed` was never wrong; it was answering a question about
a set that had already been shrunk.

The fix is the same inversion applied one layer earlier: **the claim (`H`) is derived from
the enumeration (what the transport actually fetched), never asserted beside it.**

  * A page fetcher returns `FetchedIds` - a sealed observation carrying the endpoint that
    produced it (amendment A2) - which has no public way to read the IDs.
  * `RecordingListTransport.list_messages` performs the fetch and the ledger write in one
    call, and returns `RecordedListing` - a scan-scope entry, a continuation token and
    counts. There is no code path through this module that yields a message ID.
  * The only readable enumeration is `ledger.hit_ids`, and that *is* `H`.

So a rung which under-records is not merely discouraged, it has nothing to write down: to
record ten of a hundred it would have to obtain the hundred first, and the supported API
never hands them over. What remains reachable is the same narrow, documented exception the
mint token already carries: code that deliberately reaches into a private attribute in the
same process. That is stated rather than defended against, exactly as `disposition.py`
states it for `_MINT_TOKEN`.

**Scope.** This module is the seam, not WS-02. It contains no Gmail URL, no HTTP client,
no auth and no pagination policy: a fetcher is supplied by the caller, and the Gmail
client that will supply one does not exist yet.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mailweave.constants import GMAIL_NUMERIC_ID_RE, MAX_GMAIL_NUMERIC_ID_DIGITS
from mailweave.envelope.disposition import DispositionLedger, FetchedIds, ObservedEndpoint
from mailweave.envelope.reasons import RungId
from mailweave.envelope.wire import Affordance, ScanScopeEntry

#: What a `messages.list` wrapper must look like: it returns a sealed page, never a list.
FetchListPage = Callable[..., FetchedIds]
#: The same contract for `history.list`'s `messagesAdded[].message.id`.
FetchHistoryPage = Callable[..., FetchedIds]
#: And for `threads.get`, whose message rows enter `H` under clause H-thr (amendment A2).
FetchThread = Callable[..., FetchedIds]


@dataclass(frozen=True)
class RecordedListing:
    """What a caller gets back from one recorded list call.

    Every member is a count, a declaration or an opaque continuation token. None of them
    is a message ID, and none of them can be turned into one - which is the whole point.
    `ids_recorded` is read off the page the transport fetched, so a caller cannot report
    a smaller page than the one that entered `H`.
    """

    scan_scope: ScanScopeEntry
    ids_recorded: int
    next_page_token: str | None

    @property
    def more_pages(self) -> bool:
        return self.scan_scope.more_pages


class RecordingListTransport:
    """Wraps a page fetcher so that fetching and recording cannot be separated.

    WS-02's `GmailClient` is expected to *be* one of these (or to hold one): its
    `messages.list` wrapper becomes the `fetch_page` argument, and its public listing
    method is `list_messages` below. Two obligations come with that, and they are the
    part this module cannot enforce for a client that does not exist yet:

      * no method on the client may return `list[str]` or any other bare ID collection;
      * the raw fetcher must stay private to the client. Whoever holds it can call it and
        decline to record the page - the page is still unreadable, so no IDs escape, but
        those messages never enter `H` at all. Constructing the transport is therefore
        the client's job, not a caller's;
      * a listing fetcher must carry the `threadId` Gmail returns beside each id into
        `FetchedIds(thread_ids=...)`. That argument is optional only because no real
        client exists yet to supply it, and omitting it is not cosmetic: a withheld
        record's thread is derived from the observation (R-DISC-009), so ids observed
        without one can be disclosed but can never be withheld.
    """

    __slots__ = ("_fetch_history", "_fetch_page", "_fetch_thread")

    def __init__(
        self,
        fetch_page: FetchListPage,
        *,
        fetch_history: FetchHistoryPage | None = None,
        fetch_thread: FetchThread | None = None,
    ) -> None:
        self._fetch_page = fetch_page
        self._fetch_history = fetch_history
        self._fetch_thread = fetch_thread

    def list_messages(
        self,
        ledger: DispositionLedger,
        *,
        rung: RungId,
        query: str,
        page_size: int,
        page_token: str | None = None,
        affordance: Affordance | None = None,
        pages_fetched: int = 1,
    ) -> RecordedListing:
        """Execute one `messages.list` page and record all of it into `ledger`.

        The ledger write happens before this returns and cannot be skipped, reordered or
        given a subset: the page is sealed and `record_list_page` is the only thing that
        can open it.
        """
        page = self._fetch_page(query=query, page_size=page_size, page_token=page_token)
        if not isinstance(page, FetchedIds):
            raise TypeError(
                "a list-page fetcher must return FetchedIds, so that the ids it fetched "
                f"enter H at the moment of the call; got {type(page).__name__}"
            )
        entry = ledger.record_list_page(
            page,
            rung=rung,
            query=query,
            affordance=affordance,
            pages_fetched=pages_fetched,
        )
        return RecordedListing(
            scan_scope=entry,
            ids_recorded=entry.ids_returned,
            next_page_token=page.next_page_token,
        )

    def list_history_additions(
        self,
        ledger: DispositionLedger,
        *,
        start_history_id: str,
        page_token: str | None = None,
    ) -> int:
        """Execute one `history.list` page and record every addition. Returns the count.

        Clause H-hist takes the same seal: additions are messages that were retrieved, and
        an addition a caller forgot to record is a hit that vanishes exactly as a list
        page's would.

        `start_history_id` is shape-checked against the same pattern the seal and the
        `HistoryAddition` reason use. It is the **third** place this field name appears and
        the third that was unchecked; the first two each put a sentence somewhere it did not
        belong (R-SEC-030, R-SEC-032). This one is an *outbound* parameter, so the cost of a
        wrong value is a Gmail 400 rather than a disclosure - it is checked anyway, because
        "the two disclosed ones are checked and the third is trusted" is the exact habit
        those two findings are about, and because a caller that has a sentence in this
        variable has a bug worth failing on rather than sending.
        """
        if GMAIL_NUMERIC_ID_RE.match(start_history_id) is None:
            raise ValueError(
                f"start_history_id={start_history_id!r} is not the shape Gmail returns: a "
                "`historyId` is an unsigned 64-bit integer rendered as at most "
                f"{MAX_GMAIL_NUMERIC_ID_DIGITS} ASCII decimal digits (R-SEC-032)"
            )
        if self._fetch_history is None:
            raise ValueError(
                "this transport was built without a history fetcher; history additions "
                "cannot be recorded through it"
            )
        page = self._fetch_history(
            start_history_id=start_history_id,
            page_token=page_token,
        )
        if not isinstance(page, FetchedIds):
            raise TypeError(
                "a history fetcher must return FetchedIds, so that every messagesAdded id "
                f"enters H at the moment of the call; got {type(page).__name__}"
            )
        recorded = page.size
        ledger.record_history_additions(page)
        return recorded

    def get_thread(self, ledger: DispositionLedger, *, thread_id: str, rung: RungId) -> int:
        """Execute one `threads.get` and record every message row it returned (A2).

        The seam exists for the same reason the listing one does. AD D.5's pool is built
        thread-wise, so without this a rung would have to construct the observation itself -
        which is the ordinary way to under-record, and the shape R-ORCH-001 attacked. The
        thread's rows enter `H` under clause H-thr before this returns.

        Returns the number of ids recorded. A count is not an ID, and no method here yields
        one.
        """
        if self._fetch_thread is None:
            raise ValueError(
                "this transport was built without a thread fetcher; a threads.get "
                "observation cannot be recorded through it"
            )
        observation = self._fetch_thread(thread_id=thread_id)
        if not isinstance(observation, FetchedIds):
            raise TypeError(
                "a thread fetcher must return FetchedIds, so that every message row the "
                "thread returned enters H at the moment of the call; got "
                f"{type(observation).__name__}"
            )
        if observation.endpoint is not ObservedEndpoint.THREADS_GET:
            raise TypeError(
                "a thread fetcher must return an observation of threads.get; got "
                f"{observation.endpoint.value}, which would enter H under the wrong clause"
            )
        return ledger.record_thread(observation, rung=rung)
